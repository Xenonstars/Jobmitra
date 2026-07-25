"""
FastAPI Backend - Job Automation System
Production-ready entry point with middleware, error handling, and route registration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routes import applications_router, auth_router, jobs_router, resume_router, analytics_router
from utils.logger import setup_logging

# Setup structured logging
setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown event handler"""
    logger.info("startup", version=app.version, environment=settings.ENVIRONMENT)

    # Initialize database
    from db.session import init_db
    await init_db()
    logger.info("database_initialized")

    yield

    logger.info("shutdown", version=app.version)


# Initialize FastAPI app
app = FastAPI(
    title="Job Automation API",
    description="Production-ready API for automated job search and application",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)


# =====================
# Middleware Setup
# =====================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)


# =====================
# Exception Handlers
# =====================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    logger.warning(
        "validation_error",
        path=request.url.path,
        method=request.method,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": "Validation failed",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "Internal server error",
            "request_id": request.headers.get("x-request-id", "unknown"),
        },
    )


# =====================
# Health Check Endpoint
# =====================


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """System health check endpoint"""
    return {
        "status": "healthy",
        "version": app.version,
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
    }


@app.get("/ready", tags=["System"])
async def readiness_check() -> dict[str, Any]:
    """Kubernetes readiness probe"""
    # TODO: Check database connectivity
    # TODO: Check Redis connectivity
    return {
        "status": "ready",
        "version": app.version,
    }


# =====================
# Browser Auth Endpoint
# =====================


@app.post("/api/auth/browser/{site}", tags=["Auth"])
async def launch_auth_browser(site: str) -> dict[str, Any]:
    """
    Launch a visible Chrome browser so the user can manually sign in.
    Cookies are saved and reused by headless crawlers.

    Supported sites: linkedin, naukri, indeed
    """
    from browser_auth import launch_auth_browser, SITE_URLS

    if site not in SITE_URLS:
        raise HTTPException(status_code=400, detail=f"Unsupported site: {site}. Options: {list(SITE_URLS.keys())}")

    import asyncio as aio
    try:
        result = await aio.wait_for(launch_auth_browser(site), timeout=360)
        return {
            "status": "ok" if result else "no_cookies",
            "site": site,
            "cookies_saved": result,
        }
    except aio.TimeoutError:
        return {
            "status": "timeout",
            "site": site,
            "message": "Auth browser timed out after 6 minutes",
        }


@app.get("/api/auth/status", tags=["Auth"])
async def auth_status() -> dict[str, Any]:
    """Check which sites have saved auth cookies."""
    from browser_auth import has_cookies, SITE_URLS

    return {
        site: has_cookies(site)
        for site in SITE_URLS
    }


# =====================
# Route Registration
# =====================

# Register all routers with API prefix
app.include_router(
    resume_router,
    prefix="/api/resume",
    tags=["Resume"],
)

app.include_router(
    jobs_router,
    prefix="/api/jobs",
    tags=["Jobs"],
)

app.include_router(
    applications_router,
    prefix="/api/applications",
    tags=["Applications"],
)

app.include_router(
    auth_router,
    prefix="/api/auth",
    tags=["Authentication"],
)

app.include_router(
    analytics_router,
    prefix="/api/analytics",
    tags=["Analytics"],
)


# =====================
# Request/Response Middleware
# =====================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests and responses"""
    import time

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
        client_ip=request.client.host if request.client else None,
    )

    response.headers["X-Process-Time"] = str(duration)
    return response


# =====================
# Root Endpoint
# =====================


@app.get("/", tags=["System"])
async def root() -> dict[str, Any]:
    """Root API endpoint with service information"""
    return {
        "service": "Job Application Automation API",
        "version": app.version,
        "status": "operational",
        "documentation": "/docs",
        "health_check": "/health",
    }


# =====================
# Entry Point
# =====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.ENVIRONMENT == "development",
        log_level="info" if settings.ENVIRONMENT == "production" else "debug",
        access_log=True,
    )
