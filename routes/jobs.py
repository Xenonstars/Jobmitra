"""Jobs API routes - job discovery, search, and LLM-powered matching."""

import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import structlog

from db import Job, Resume
from db.session import async_session
from job_discovery_service import IndeedCrawler, LinkedInCrawler, JobListing
from llm_service import JobMatchingService, ResumeTailoringService
from config import settings

logger = structlog.get_logger(__name__)
router = APIRouter()


class JobSearchRequest(BaseModel):
    keywords: list[str]
    location: str = "Remote"
    limit: int = 20
    sources: list[str] = ["indeed"]
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    remote_only: bool = True


class JobMatchRequest(BaseModel):
    resume_id: str
    job_ids: Optional[list[str]] = None
    limit: int = 20
    min_score: int = 0


@router.get("/")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = None,
):
    """List discovered jobs from the database."""
    async with async_session() as db:
        from sqlalchemy import select

        query = select(Job)
        if source:
            query = query.where(Job.source == source)
        query = query.order_by(Job.discovered_at.desc()).limit(limit)

        result = await db.execute(query)
        jobs = result.scalars().all()

        return {
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "url": j.url,
                    "source": j.source,
                    "salary_min": j.salary_min,
                    "salary_max": j.salary_max,
                    "remote_friendly": j.remote_friendly,
                    "match_score": j.match_score,
                    "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
                }
                for j in jobs
            ],
            "total": len(jobs),
        }


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get a specific job by ID."""
    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "url": job.url,
            "source": job.source,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "remote_friendly": job.remote_friendly,
            "job_type": job.job_type,
            "match_score": job.match_score,
            "match_reasoning": job.match_reasoning,
            "key_matches": job.key_matches,
            "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
        }


@router.post("/search")
async def search_jobs(request: JobSearchRequest):
    """Search jobs across multiple sources in parallel."""

    logger.info(
        "job_search_start",
        keywords=request.keywords,
        location=request.location,
        sources=request.sources,
    )

    all_jobs: list[JobListing] = []
    crawlers = []

    if "indeed" in request.sources:
        crawlers.append(IndeedCrawler().search(request.keywords, request.location, request.limit))
    if "linkedin" in request.sources and settings.ENABLE_LINKEDIN_APPLY:
        crawlers.append(LinkedInCrawler().search(request.keywords, request.location, request.limit))

    if not crawlers:
        raise HTTPException(status_code=400, detail="No valid job sources selected")

    results = await asyncio.gather(*crawlers, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("crawler_error", error=str(result))
        elif isinstance(result, list):
            all_jobs.extend(result)

    # Deduplicate by URL
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_jobs.append(job)

    # Save to database
    saved_count = 0
    async with async_session() as db:
        from sqlalchemy import select as sa_select
        for jl in unique_jobs:
            existing = await db.execute(sa_select(Job).where(Job.url == jl.url))
            if not existing.scalar_one_or_none():
                db.add(Job(
                    title=jl.title,
                    company=jl.company,
                    location=jl.location,
                    description=jl.description,
                    url=jl.url,
                    source=jl.source,
                    salary_min=jl.salary_min,
                    salary_max=jl.salary_max,
                    remote_friendly=jl.remote_friendly,
                    job_type=jl.job_type,
                ))
                saved_count += 1
        await db.commit()

    logger.info("job_search_complete", found=len(unique_jobs), saved=saved_count)

    return {
        "status": "complete",
        "jobs_found": len(unique_jobs),
        "jobs_saved": saved_count,
        "jobs": [
            {
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "url": j.url,
                "source": j.source,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "remote": j.remote_friendly,
            }
            for j in unique_jobs[:50]
        ],
    }


@router.post("/match")
async def match_jobs(request: JobMatchRequest):
    """Score jobs against a resume using the LLM."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
        resume = result.scalar_one_or_none()
        if not resume or not resume.content:
            raise HTTPException(status_code=404, detail="Resume not found or has no content")

        if request.job_ids:
            result = await db.execute(select(Job).where(Job.id.in_(request.job_ids)))
        else:
            result = await db.execute(
                select(Job).order_by(Job.discovered_at.desc()).limit(request.limit)
            )
        db_jobs = result.scalars().all()

        if not db_jobs:
            return {"matches": [], "total": 0}

        job_listings = [
            JobListing(
                title=j.title,
                company=j.company,
                location=j.location or "",
                description=j.description or "",
                url=j.url or "",
                salary_min=j.salary_min,
                salary_max=j.salary_max,
                source=j.source or "unknown",
                remote_friendly=j.remote_friendly or False,
            )
            for j in db_jobs
        ]

        matcher = JobMatchingService()
        scored = await matcher.get_top_matches(resume.content, job_listings, limit=request.limit)

        if request.min_score > 0:
            scored = [s for s in scored if s.get("score", 0) >= request.min_score]

        for s in scored:
            job_idx = s.get("index", -1)
            if 0 <= job_idx < len(db_jobs):
                db_jobs[job_idx].match_score = s.get("score")
                db_jobs[job_idx].match_reasoning = s.get("reasoning")
                db_jobs[job_idx].key_matches = s.get("key_matches")

        await db.commit()
        return {"matches": scored, "total": len(scored)}
