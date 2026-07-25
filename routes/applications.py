"""Applications API routes - submit, track, and manage job applications."""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
import structlog

from db import Application, Job, Resume
from db.session import async_session
from services.application_service import ApplicationSubmitter

logger = structlog.get_logger(__name__)
router = APIRouter()


class ApplyRequest(BaseModel):
    job_id: str
    resume_id: str
    cover_letter: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None


VALID_STATUSES = {
    "discovered", "matched", "pending_approval", "approved",
    "applying", "submitted", "under_review", "interview",
    "rejected", "offer", "failed",
}


@router.get("/")
async def list_applications(
    status: Optional[str] = None,
    company: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """List all applications with optional filters."""
    async with async_session() as db:
        from sqlalchemy import select

        query = select(Application)
        if status:
            query = query.where(Application.status == status)
        if date_from:
            query = query.where(Application.created_at >= date_from)
        query = query.order_by(Application.created_at.desc()).limit(limit)

        result = await db.execute(query)
        apps = result.scalars().all()

        app_data = []
        for a in apps:
            job_result = await db.execute(select(Job).where(Job.id == a.job_id))
            job = job_result.scalar_one_or_none()
            if company and (not job or company.lower() not in (job.company or "").lower()):
                continue
            app_data.append({
                "id": a.id,
                "job_id": a.job_id,
                "job_title": job.title if job else None,
                "company": job.company if job else None,
                "resume_id": a.resume_id,
                "status": a.status,
                "notes": a.notes,
                "cover_letter": a.cover_letter,
                "tailored_resume": a.tailored_resume,
                "applied_at": a.applied_at.isoformat() if a.applied_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        return {"applications": app_data, "total": len(app_data)}


@router.get("/{application_id}")
async def get_application(application_id: str):
    """Get a specific application with full details."""
    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Application).where(Application.id == application_id))
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        job_result = await db.execute(select(Job).where(Job.id == app.job_id))
        job = job_result.scalar_one_or_none()

        return {
            "id": app.id,
            "job_id": app.job_id,
            "job_title": job.title if job else None,
            "company": job.company if job else None,
            "resume_id": app.resume_id,
            "cover_letter": app.cover_letter,
            "tailored_resume": app.tailored_resume,
            "status": app.status,
            "notes": app.notes,
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
            "created_at": app.created_at.isoformat() if app.created_at else None,
        }


@router.post("/apply")
async def submit_application(request: ApplyRequest):
    """Queue a job application for human approval. Does NOT submit automatically."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Job).where(Job.id == request.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        # Check for existing
        result = await db.execute(
            select(Application).where(
                Application.job_id == request.job_id,
                Application.resume_id == request.resume_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.status == "pending_approval":
                return {
                    "status": "pending_approval",
                    "application_id": existing.id,
                    "message": "Already pending your approval",
                }
            elif existing.status in ("submitted", "applying"):
                return {
                    "status": "duplicate",
                    "application_id": existing.id,
                    "message": "Already applied to this job",
                }

        app = Application(
            job_id=request.job_id,
            resume_id=request.resume_id,
            cover_letter=request.cover_letter,
            status="pending_approval",
        )
        db.add(app)
        await db.commit()
        await db.refresh(app)

        logger.info(
            "application_pending_approval",
            application_id=app.id,
            job_title=job.title,
            company=job.company,
        )

        return {
            "status": "pending_approval",
            "application_id": app.id,
            "job_title": job.title,
            "company": job.company,
            "message": "Application queued for your review. Approve it from the dashboard to submit.",
        }


@router.post("/{application_id}/approve")
async def approve_application(application_id: str, background_tasks: BackgroundTasks):
    """Explicit human approval — triggers the actual Playwright submission."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Application).where(Application.id == application_id))
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        if app.status not in ("pending_approval", "approved"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve — current status is '{app.status}'. Must be 'pending_approval'.",
            )

        result = await db.execute(select(Job).where(Job.id == app.job_id))
        job = result.scalar_one_or_none()

        result = await db.execute(select(Resume).where(Resume.id == app.resume_id))
        resume = result.scalar_one_or_none()

        app.status = "approved"
        await db.commit()

    logger.info(
        "application_approved",
        application_id=application_id,
        job_title=job.title if job else None,
    )

    if job and resume:
        background_tasks.add_task(
            _submit_application_bg,
            application_id,
            job,
            resume,
            app.cover_letter,
        )

    return {
        "status": "approved",
        "application_id": application_id,
        "message": "Application approved and submission started.",
    }


@router.post("/{application_id}/reject")
async def reject_application(application_id: str):
    """Reject a pending application without submitting."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Application).where(Application.id == application_id))
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        if app.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Can only reject pending applications")

        app.status = "rejected"
        app.updated_at = datetime.utcnow()
        await db.commit()

    return {"status": "rejected", "application_id": application_id}


@router.post("/approve-all")
async def approve_all_pending(background_tasks: BackgroundTasks):
    """Approve all pending applications at once."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(Application).where(Application.status == "pending_approval")
        )
        pending = result.scalars().all()

        if not pending:
            return {"status": "none_pending", "count": 0}

        approved_count = 0
        for app in pending:
            app.status = "approved"
            app.updated_at = datetime.utcnow()
            approved_count += 1

            job_result = await db.execute(select(Job).where(Job.id == app.job_id))
            job = job_result.scalar_one_or_none()
            resume_result = await db.execute(select(Resume).where(Resume.id == app.resume_id))
            resume = resume_result.scalar_one_or_none()

            if job and resume:
                background_tasks.add_task(
                    _submit_application_bg,
                    app.id,
                    job,
                    resume,
                    app.cover_letter,
                )

        await db.commit()
        logger.info("approve_all", count=approved_count)

    return {"status": "approved", "count": approved_count}


@router.patch("/{application_id}")
async def update_application(application_id: str, update: UpdateStatusRequest):
    """Update application status manually."""

    if update.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Application).where(Application.id == application_id))
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        app.status = update.status
        if update.notes:
            app.notes = update.notes
        app.updated_at = datetime.utcnow()
        await db.commit()

        logger.info("application_updated", application_id=application_id, status=update.status)
        return {"application_id": application_id, "status": update.status, "notes": update.notes}


async def _submit_application_bg(
    application_id: str,
    job: Job,
    resume: Resume,
    cover_letter: Optional[str] = None,
):
    """Background task: submit application via Playwright browser automation."""
    async with async_session() as db:
        from sqlalchemy import select

        try:
            submitter = ApplicationSubmitter()
            result = await submitter.submit_application(job, resume, cover_letter)

            result_db = await db.execute(select(Application).where(Application.id == application_id))
            app = result_db.scalar_one_or_none()
            if app:
                app.status = result.get("status", "failed")
                app.applied_at = datetime.utcnow()
                app.updated_at = datetime.utcnow()
                app.notes = result.get("reason", result.get("platform", ""))
                await db.commit()

            logger.info("application_submitted", application_id=application_id, result=result)

        except Exception as e:
            logger.error("background_submit_error", error=str(e), exc_info=True)

            result_db = await db.execute(select(Application).where(Application.id == application_id))
            app = result_db.scalar_one_or_none()
            if app:
                app.status = "failed"
                app.notes = str(e)[:500]
                app.updated_at = datetime.utcnow()
                await db.commit()
