"""
Response cache — file-based, keyed on hash(resume_snippet + job_url + operation).
Avoids re-scoring or re-tailoring unchanged job postings.
"""

import hashlib
import json
import os
import structlog
from typing import Optional, Any
from datetime import datetime, timedelta

from config import settings

logger = structlog.get_logger(__name__)

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".llm_cache")
_DEFAULT_TTL = timedelta(hours=settings.JOB_CACHE_TTL if hasattr(settings, 'JOB_CACHE_TTL') else 24)


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_key(resume_snippet: str, job_url: str, operation: str) -> str:
    """Generate a deterministic cache key."""
    raw = f"{resume_snippet[:500]}::{job_url}::{operation}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(key: str) -> str:
    _ensure_cache_dir()
    return os.path.join(_CACHE_DIR, f"{key}.json")


def get(resume_snippet: str, job_url: str, operation: str) -> Optional[Any]:
    """
    Retrieve a cached result if it exists and hasn't expired.
    Returns None if no valid cache entry exists.
    """
    if not job_url or not operation:
        return None

    key = _cache_key(resume_snippet, job_url, operation)
    path = _cache_path(key)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as f:
            entry = json.load(f)

        # Check expiry
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.utcnow() - cached_at > _DEFAULT_TTL:
            os.remove(path)
            return None

        logger.debug(
            "cache_hit",
            operation=operation,
            job_url=job_url[:60],
            age=str(datetime.utcnow() - cached_at).split(".")[0],
        )
        return entry["result"]

    except Exception as e:
        logger.debug("cache_read_error", error=str(e))
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def set(resume_snippet: str, job_url: str, operation: str, result: Any) -> None:
    """Store a result in the cache."""
    if not job_url or not operation:
        return

    key = _cache_key(resume_snippet, job_url, operation)
    path = _cache_path(key)

    try:
        entry = {
            "cached_at": datetime.utcnow().isoformat(),
            "operation": operation,
            "result": result,
        }
        with open(path, "w") as f:
            json.dump(entry, f, indent=2)

        logger.debug("cache_set", operation=operation, job_url=job_url[:60])

    except Exception as e:
        logger.debug("cache_write_error", error=str(e))


def clear() -> None:
    """Clear the entire LLM cache."""
    _ensure_cache_dir()
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith(".json"):
            try:
                os.remove(os.path.join(_CACHE_DIR, fname))
            except Exception:
                pass
    logger.info("cache_cleared")


def clear_for_job(job_url: str) -> None:
    """Remove all cache entries for a specific job URL."""
    _ensure_cache_dir()
    for fname in os.listdir(_CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_CACHE_DIR, fname)
        try:
            with open(path, "r") as f:
                entry = json.load(f)
            result_str = json.dumps(entry.get("result", {}))
            if job_url in result_str:
                os.remove(path)
                logger.debug("cache_cleared_for_job", job_url=job_url[:60])
        except Exception:
            pass
