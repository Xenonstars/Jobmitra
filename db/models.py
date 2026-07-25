"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, DateTime, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.orm import relationship
from db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=True)
    linkedin_authenticated = Column(Boolean, default=False)
    naukri_authenticated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    parsed_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="resumes")
    applications = relationship("Application", back_populates="resume")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    remote_friendly = Column(Boolean, default=False)
    job_type = Column(String(50), nullable=True)
    match_score = Column(Integer, nullable=True)
    match_reasoning = Column(Text, nullable=True)
    key_matches = Column(JSON, nullable=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)

    applications = relationship("Application", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    resume_id = Column(String, ForeignKey("resumes.id"), nullable=True)
    cover_letter = Column(Text, nullable=True)
    tailored_resume = Column(Text, nullable=True)
    status = Column(String(50), default="discovered")
    notes = Column(Text, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")
