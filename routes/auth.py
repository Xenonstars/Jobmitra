"""Authentication API routes."""

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from db import User
from db.session import async_session

logger = structlog.get_logger(__name__)
router = APIRouter()


class AuthRequest(BaseModel):
    email: str


@router.post("/login")
async def login(request: AuthRequest):
    """Login or create user by email. Returns a session token."""

    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(User).where(User.email == request.email))
        user = result.scalar_one_or_none()

        if not user:
            user = User(email=request.email)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info("user_created", user_id=user.id, email=user.email)
        else:
            logger.info("user_login", user_id=user.id, email=user.email)

        token = str(uuid.uuid4())

        return {
            "user_id": user.id,
            "token": token,
            "linkedin_authenticated": user.linkedin_authenticated,
            "naukri_authenticated": user.naukri_authenticated,
        }


@router.post("/logout")
async def logout():
    """Logout endpoint."""
    return {"status": "logged_out"}


@router.get("/me/{user_id}")
async def get_user(user_id: str):
    """Get user profile."""
    async with async_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": user.id,
            "email": user.email,
            "linkedin_authenticated": user.linkedin_authenticated,
            "naukri_authenticated": user.naukri_authenticated,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
