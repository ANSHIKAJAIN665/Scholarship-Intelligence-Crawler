from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scholarship_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    official_source_url: Mapped[str] = mapped_column(Text, nullable=False)
    application_url: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    amount: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    benefit: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    eligibility: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    academic_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    education_level: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    course_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    income_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    age_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    gender_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    category_criteria: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    domicile_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    institution_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    opening_date: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    closing_date: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    documents_required: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    selection_process: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    renewal_requirements: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    current_status: Mapped[str] = mapped_column(String(40), nullable=False, default="REVIEW_REQUIRED")
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False, default="REVIEW_REQUIRED")
    score_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_verified: Mapped[str] = mapped_column(String(40), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)

    evidence: Mapped[list["SourceEvidence"]] = relationship(back_populates="scholarship")
    changes: Mapped[list["ChangeHistory"]] = relationship(back_populates="scholarship")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RUNNING")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SourceEvidence(Base):
    __tablename__ = "source_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scholarship_id: Mapped[str] = mapped_column(ForeignKey("scholarships.id"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extracted_value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)

    scholarship: Mapped["Scholarship"] = relationship(back_populates="evidence")


class ChangeHistory(Base):
    __tablename__ = "change_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scholarship_id: Mapped[str] = mapped_column(ForeignKey("scholarships.id"), nullable=False)
    field_changed: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    date_detected: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    scholarship: Mapped["Scholarship"] = relationship(back_populates="changes")
