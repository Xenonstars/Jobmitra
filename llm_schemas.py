"""
Pydantic schemas for validating LLM structured output before it touches the database.
Every LLM prompt that requests structured JSON should validate through these models.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class JobScore(BaseModel):
    """A single job score from the LLM matching service."""
    index: int = Field(..., ge=0, description="Job index in the original list")
    score: int = Field(..., ge=0, le=100, description="Relevance score 0-100")
    reasoning: str = Field(..., min_length=1, description="Explanation of the score")
    key_matches: List[str] = Field(default_factory=list, description="Matching skills/requirements")
    concerns: List[str] = Field(default_factory=list, description="Gaps or concerns (if score < 70)")

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        if not v.strip():
            return "No reasoning provided."
        return v.strip()


class JobScoreList(BaseModel):
    """Wrapper for batch job score response."""
    scores: List[JobScore] = Field(default_factory=list)

    @field_validator("scores")
    @classmethod
    def validate_scores(cls, v: List[JobScore]) -> List[JobScore]:
        if not v:
            raise ValueError("At least one job score is required")
        return v


class ExtractedRequirements(BaseModel):
    """Key requirements extracted from a job description."""
    required_skills: List[str] = Field(default_factory=list, description="Must-have skills")
    nice_to_have: List[str] = Field(default_factory=list, description="Preferred/optional skills")
    experience_years: int = Field(default=0, ge=0, description="Years of experience required")
    education: str = Field(default="Not specified", description="Minimum education level")
    soft_skills: List[str] = Field(default_factory=list, description="Soft skills mentioned")
    certifications: List[str] = Field(default_factory=list, description="Required certifications")
    key_responsibilities: List[str] = Field(default_factory=list, description="Main job responsibilities")


class TailoredResumeOutput(BaseModel):
    """Validates that the tailored resume output is non-empty and reasonable."""
    content: str = Field(..., min_length=50, description="Tailored resume text")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 50:
            raise ValueError("Tailored resume content is too short (< 50 chars)")
        return stripped


class CoverLetterOutput(BaseModel):
    """Validates that the cover letter output is non-empty and reasonable."""
    content: str = Field(..., min_length=100, description="Cover letter text")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 100:
            raise ValueError("Cover letter is too short (< 100 chars)")
        return stripped


def validate_job_scores(raw: list[dict]) -> list[JobScore]:
    """
    Validate a list of raw score dicts from the LLM.
    Returns validated JobScore objects or raises on structural failure.
    """
    validated = []
    for item in raw:
        # Coerce string scores to int if possible
        if isinstance(item.get("score"), str):
            try:
                item["score"] = int(item["score"])
            except (ValueError, TypeError):
                item["score"] = 0
        validated.append(JobScore(**item))
    return validated


def validate_requirements(raw: dict) -> ExtractedRequirements:
    """Validate extracted requirements dict from the LLM."""
    return ExtractedRequirements(**raw)
