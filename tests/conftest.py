from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.database import Base
from database import models  # noqa: F401


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def scholarship_values():
    return {
        "id": "test-scholarship",
        "scholarship_name": "Official Student Scholarship",
        "provider": "Test Government Department",
        "official_source_url": "https://test.gov.in/scholarship",
        "application_url": "https://test.gov.in/apply",
        "source_type": "government",
        "amount": "Not specified",
        "benefit": "Not specified",
        "eligibility": "Students must meet the published criteria.",
        "academic_requirements": "Not specified",
        "education_level": "Not specified",
        "course_requirements": "Not specified",
        "income_criteria": "Not specified",
        "age_criteria": "Not specified",
        "gender_criteria": "Not specified",
        "category_criteria": "Not specified",
        "domicile_requirements": "Not specified",
        "institution_requirements": "Not specified",
        "opening_date": "Not specified",
        "closing_date": "Not specified",
        "documents_required": "Not specified",
        "selection_process": "Not specified",
        "renewal_requirements": "Not specified",
        "current_status": "REVIEW_REQUIRED",
        "confidence_score": 70,
        "verification_status": "REVIEW_REQUIRED",
        "score_breakdown_json": "[]",
        "last_verified": "2026-10-07T00:00:00+00:00",
        "content_hash": "abc123",
        "created_at": "2026-10-07T00:00:00+00:00",
        "updated_at": "2026-10-07T00:00:00+00:00",
    }
