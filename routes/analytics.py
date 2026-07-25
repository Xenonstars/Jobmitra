"""Analytics routes — application funnel, success metrics, and CSV export."""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import structlog

from db import Application, Job
from db.session import async_session

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/funnel")
async def application_funnel(
    days: int = Query(30, ge=1, le=365),
):
    """
    Returns the application funnel breakdown:
    applied → viewed → interview → offer → rejected
    With breakdowns by job title, company, and resume version.
    """
    async with async_session() as db:
        from sqlalchemy import select, func

        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(Application).where(Application.created_at >= cutoff)
        )
        apps = result.scalars().all()

    total = len(apps)
    funnel = {
        "period_days": days,
        "total": total,
        "pending_approval": sum(1 for a in apps if a.status == "pending_approval"),
        "approved": sum(1 for a in apps if a.status == "approved"),
        "submitted": sum(1 for a in apps if a.status == "submitted"),
        "under_review": sum(1 for a in apps if a.status == "under_review"),
        "interview": sum(1 for a in apps if a.status == "interview"),
        "offer": sum(1 for a in apps if a.status == "offer"),
        "rejected": sum(1 for a in apps if a.status == "rejected"),
        "failed": sum(1 for a in apps if a.status == "failed"),
    }

    # Conversion rates
    if total > 0:
        funnel["submission_rate"] = round(funnel["submitted"] / total * 100, 1)
        funnel["interview_rate"] = round(funnel["interview"] / total * 100, 1)
        funnel["offer_rate"] = round(funnel["offer"] / total * 100, 1)
    else:
        funnel["submission_rate"] = 0.0
        funnel["interview_rate"] = 0.0
        funnel["offer_rate"] = 0.0

    # Top companies by application count
    company_counts = {}
    async with async_session() as db:
        from sqlalchemy import select
        for a in apps:
            if a.job_id:
                jr = await db.execute(select(Job).where(Job.id == a.job_id))
                job = jr.scalar_one_or_none()
                if job and job.company:
                    company_counts[job.company] = company_counts.get(job.company, 0) + 1

    top_companies = sorted(company_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Timeline (daily counts for the period)
    timeline = {}
    for a in apps:
        day = a.created_at.date().isoformat() if a.created_at else "unknown"
        timeline[day] = timeline.get(day, 0) + 1

    return {
        "funnel": funnel,
        "top_companies": [{"company": c, "count": n} for c, n in top_companies],
        "timeline": [{"date": d, "count": n} for d, n in sorted(timeline.items())],
    }


@router.get("/export/csv")
async def export_applications_csv(
    status: Optional[str] = None,
    days: int = Query(365, ge=1, le=3650),
):
    """Export applications as CSV."""
    async with async_session() as db:
        from sqlalchemy import select

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = select(Application).where(Application.created_at >= cutoff)
        if status:
            query = query.where(Application.status == status)
        query = query.order_by(Application.created_at.desc())

        result = await db.execute(query)
        apps = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Application ID", "Status", "Job Title", "Company",
        "Applied Date", "Created Date", "Notes", "Cover Letter Available",
    ])

    async with async_session() as db:
        from sqlalchemy import select
        for a in apps:
            job_title = ""
            company = ""
            if a.job_id:
                jr = await db.execute(select(Job).where(Job.id == a.job_id))
                job = jr.scalar_one_or_none()
                if job:
                    job_title = job.title or ""
                    company = job.company or ""

            writer.writerow([
                a.id,
                a.status,
                job_title,
                company,
                a.applied_at.isoformat() if a.applied_at else "",
                a.created_at.isoformat() if a.created_at else "",
                a.notes or "",
                "Yes" if a.cover_letter else "No",
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )
