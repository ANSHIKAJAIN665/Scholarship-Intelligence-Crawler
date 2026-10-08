from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ScholarshipData(BaseModel):
    """Structured, deterministic extraction result; absent source facts stay explicit."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scholarship_name: str
    provider: str = "Not specified"
    official_source_url: str
    application_url: str = "Not specified"
    source_type: str = "unknown"
    amount: str = "Not specified"
    benefit: str = "Not specified"
    eligibility: str = "Not specified"
    academic_requirements: str = "Not specified"
    education_level: str = "Not specified"
    course_requirements: str = "Not specified"
    income_criteria: str = "Not specified"
    age_criteria: str = "Not specified"
    gender_criteria: str = "Not specified"
    category_criteria: str = "Not specified"
    domicile_requirements: str = "Not specified"
    institution_requirements: str = "Not specified"
    opening_date: str = "Not specified"
    closing_date: str = "Not specified"
    documents_required: str = "Not specified"
    selection_process: str = "Not specified"
    renewal_requirements: str = "Not specified"
    current_status: str = "REVIEW_REQUIRED"
    confidence_score: int = Field(default=0, ge=0, le=100)
    verification_status: str = "REVIEW_REQUIRED"

    @field_validator("scholarship_name", "official_source_url")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value or value == "Not specified":
            raise ValueError("A scholarship name and source URL are required")
        return value

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "ScholarshipData":
        return cls.model_validate(values)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )


class EvidenceResponse(ApiModel):
    id: str
    field_name: str
    extracted_value: str
    evidence_text: str
    source_url: str
    captured_at: str


class ChangeResponse(ApiModel):
    id: str
    field_changed: str
    old_value: str
    new_value: str
    date_detected: str
    source_url: str
    evidence: str
    is_demo: bool = False


class DemoChangeResponse(ApiModel):
    id: str
    scholarship_name: str
    field_changed: str
    old_value: str
    new_value: str
    date_detected: str
    source_url: str
    evidence: str
    is_demo: bool = True


class ScoreItemResponse(ApiModel):
    label: str
    points: int
    earned: int
    reason: str


class ScholarshipResponse(ApiModel):
    id: str
    scholarship_name: str
    provider: str
    official_source_url: str
    application_url: str
    source_type: str
    amount: str
    benefit: str
    eligibility: str
    academic_requirements: str
    education_level: str
    course_requirements: str
    income_criteria: str
    age_criteria: str
    gender_criteria: str
    category_criteria: str
    domicile_requirements: str
    institution_requirements: str
    opening_date: str
    closing_date: str
    documents_required: str
    selection_process: str
    renewal_requirements: str
    current_status: str
    confidence_score: int
    verification_status: str
    last_verified: str
    created_at: str
    updated_at: str


class ScholarshipDetailResponse(ScholarshipResponse):
    evidence: list[EvidenceResponse]
    change_history: list[ChangeResponse]
    score_breakdown: list[ScoreItemResponse]


class CrawlRunResponse(ApiModel):
    id: str
    started_at: str
    completed_at: str
    discovered_count: int
    new_count: int
    updated_count: int
    changed_count: int
    expired_count: int
    failed_count: int
    status: str
    message: str


class DashboardSummaryResponse(ApiModel):
    total_discovered: int
    verified: int
    review_required: int
    active: int
    expired: int
    recently_updated: int
    average_confidence: float
    latest_run: CrawlRunResponse | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
