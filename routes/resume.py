"""Resume API routes - upload, parse, tailor, and manage resumes."""

import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import structlog

from db import Resume, Job
from db.session import async_session
from llm_service import ResumeTailoringService
from job_discovery_service import JobListing

logger = structlog.get_logger(__name__)
router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class TailorResumeRequest(BaseModel):
    resume_id: str
    job_id: str


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload and parse a resume file (PDF or DOCX)."""

    # Accept by both MIME type and file extension
    allowed_mimes = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",  # Streamlit often sends this
    }
    allowed_exts = {".pdf", ".docx"}
    ext = os.path.splitext(file.filename)[1].lower()

    if file.content_type not in allowed_mimes and ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    content_bytes = await file.read()

    with open(file_path, "wb") as f:
        f.write(content_bytes)

    content_text = _extract_text(file_path, file.content_type)
    if not content_text:
        content_text = f"[Binary content: {file.filename}]"

    async with async_session() as db:
        resume = Resume(filename=file.filename, content=content_text)
        db.add(resume)
        await db.commit()
        await db.refresh(resume)

        logger.info("resume_uploaded", resume_id=resume.id, filename=file.filename)

        return {
            "id": resume.id,
            "filename": resume.filename,
            "content_preview": content_text[:500],
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
        }


@router.get("/")
async def list_resumes():
    """List all uploaded resumes."""
    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Resume).order_by(Resume.created_at.desc()))
        resumes = result.scalars().all()

        return {
            "resumes": [
                {
                    "id": r.id,
                    "filename": r.filename,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in resumes
            ],
            "total": len(resumes),
        }


@router.get("/{resume_id}")
async def get_resume(resume_id: str):
    """Get resume by ID with full content."""
    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Resume).where(Resume.id == resume_id))
        resume = result.scalar_one_or_none()

        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        return {
            "id": resume.id,
            "filename": resume.filename,
            "content": resume.content,
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
        }


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str):
    """Delete a resume."""
    async with async_session() as db:
        from sqlalchemy import select, delete

        result = await db.execute(select(Resume).where(Resume.id == resume_id))
        resume = result.scalar_one_or_none()

        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        await db.execute(delete(Resume).where(Resume.id == resume_id))
        await db.commit()

        return {"status": "deleted", "resume_id": resume_id}


@router.post("/tailor")
async def tailor_resume(request: TailorResumeRequest):
    """Generate a tailored resume for a specific job using LLM."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
        resume = result.scalar_one_or_none()
        if not resume or not resume.content:
            raise HTTPException(status_code=404, detail="Resume not found")

        result = await db.execute(select(Job).where(Job.id == request.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    job_listing = JobListing(
        title=job.title,
        company=job.company or "",
        location=job.location or "",
        description=job.description or "",
        url=job.url or "",
        source=job.source or "",
    )

    tailor = ResumeTailoringService()
    tailored = await tailor.generate_tailored_resume(resume.content, job_listing)

    logger.info("resume_tailored", resume_id=resume.id, job_id=job.id)

    return {
        "original_resume_id": resume.id,
        "job_id": job.id,
        "tailored_resume": tailored,
    }


@router.post("/cover-letter")
async def generate_cover_letter(request: TailorResumeRequest):
    """Generate a cover letter for a specific job using LLM."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Resume).where(Resume.id == request.resume_id))
        resume = result.scalar_one_or_none()
        if not resume or not resume.content:
            raise HTTPException(status_code=404, detail="Resume not found")

        result = await db.execute(select(Job).where(Job.id == request.job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    job_listing = JobListing(
        title=job.title,
        company=job.company or "",
        location=job.location or "",
        description=job.description or "",
        url=job.url or "",
        source=job.source or "",
    )

    tailor = ResumeTailoringService()
    cover_letter = await tailor.generate_cover_letter(resume.content, job_listing)

    logger.info("cover_letter_generated", resume_id=resume.id, job_id=job.id)

    return {
        "resume_id": resume.id,
        "job_id": job.id,
        "cover_letter": cover_letter,
    }


def _extract_text(file_path: str, content_type: str) -> str:
    """Extract text from PDF or DOCX."""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        is_pdf = "pdf" in (content_type or "") or ext == ".pdf"
        is_docx = "docx" in (content_type or "") or ext == ".docx"

        if is_pdf:
            import pdfplumber
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        elif is_docx:
            import docx
            doc = docx.Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        logger.error("text_extraction_error", error=str(e), file_path=file_path, content_type=content_type)
    return ""
