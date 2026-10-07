from sqlalchemy import inspect, select

from database.database import Base
from database.models import Scholarship, SourceEvidence


def test_database_creation(db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert {"scholarships", "crawl_runs", "source_evidence", "change_history"} <= tables


def test_scholarship_insertion_and_evidence_storage(db_session, scholarship_values):
    db_session.add(Scholarship(**scholarship_values))
    db_session.add(
        SourceEvidence(
            id="evidence-1",
            scholarship_id="test-scholarship",
            field_name="eligibility",
            extracted_value="Students must meet the published criteria.",
            evidence_text="Students must meet the published criteria.",
            source_url="https://test.gov.in/scholarship",
            captured_at="2026-10-07T00:00:00+00:00",
        )
    )
    db_session.commit()
    stored = db_session.scalar(select(Scholarship).where(Scholarship.id == "test-scholarship"))
    evidence = db_session.scalar(select(SourceEvidence).where(SourceEvidence.id == "evidence-1"))
    assert stored is not None
    assert stored.scholarship_name == "Official Student Scholarship"
    assert evidence is not None and evidence.scholarship_id == stored.id
