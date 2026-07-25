"""
Embeddings service — uses Ollama's built-in embeddings API to compute
semantic similarity between resume and job descriptions.
Pre-filters scraped jobs so only the top-N reach the LLM for full scoring.
"""

import json
import structlog
import numpy as np
from typing import List, Optional
from config import settings
from job_discovery_service import JobListing

logger = structlog.get_logger(__name__)

# Embedding model — small/fast, available via `ollama pull nomic-embed-text`
EMBEDDING_MODEL = "nomic-embed-text"


def _get_ollama_client():
    import ollama
    return ollama


def embed_text(text: str) -> List[float]:
    """Get embedding vector for a text string via Ollama."""
    try:
        ollama = _get_ollama_client()
        response = ollama.embeddings(model=EMBEDDING_MODEL, prompt=text[:2000])
        return response["embedding"]
    except Exception as e:
        logger.error("embedding_error", error=str(e), model=EMBEDDING_MODEL)
        raise


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(arr_a)
    norm_b = np.linalg.norm(arr_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))


def compute_resume_embedding(resume_text: str) -> Optional[List[float]]:
    """
    Compute and cache the embedding for the full resume.
    The caller should cache this result per resume version.
    """
    return embed_text(resume_text[:3000])


def compute_job_embedding(job: JobListing) -> List[float]:
    """Compute embedding for a single job."""
    text = f"{job.title} {job.company} {job.location} {job.description[:800]}"
    return embed_text(text)


def rank_jobs_by_similarity(
    resume_embedding: List[float],
    jobs: List[JobListing],
    top_n: int = 30,
) -> List[tuple[int, float]]:
    """
    Rank jobs by cosine similarity to the resume embedding.
    Returns list of (job_index, similarity_score) sorted descending.
    Only returns top_n results.
    """
    if not jobs or not resume_embedding:
        return []

    results: list[tuple[int, float]] = []
    for i, job in enumerate(jobs):
        try:
            job_emb = compute_job_embedding(job)
            sim = cosine_similarity(resume_embedding, job_emb)
            results.append((i, sim))
        except Exception as e:
            logger.debug("job_embedding_failed", index=i, error=str(e))
            results.append((i, 0.0))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]
