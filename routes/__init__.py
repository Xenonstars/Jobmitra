"""Routes package - API endpoint definitions."""

from routes.jobs import router as jobs_router
from routes.applications import router as applications_router
from routes.resume import router as resume_router
from routes.auth import router as auth_router
from routes.analytics import router as analytics_router

__all__ = [
    "jobs_router",
    "applications_router",
    "resume_router",
    "auth_router",
    "analytics_router",
]
