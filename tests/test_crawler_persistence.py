from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from crawler.crawler import _persist_candidate, cleanup_existing_records
from crawler.extractor import is_portal_or_navigation_page
from crawler.extractor import Candidate
from database.models import ChangeHistory, Scholarship, SourceEvidence
from models.scholarship import utc_now_iso


def _candidate(name: str, url: str) -> Candidate:
    listing = f"{name}. Eligible students must have passed Class 12. Applications close on 30 October 2026."
    return Candidate(
        scholarship_name=name,
        source_url=url,
        provider="Sample Government Department",
        application_url="https://scholarships.gov.in/apply",
        source_type="government",
        listing_text=listing,
        evidence={
            "scholarship_name": {"value": name, "text": listing, "url": url},
            "eligibility": {
                "value": "Eligible students must have passed Class 12.",
                "text": "Eligible students must have passed Class 12.",
                "url": url,
            },
            "closing_date": {
                "value": "Applications close on 30 October 2026.",
                "text": "Applications close on 30 October 2026.",
                "url": url,
            },
            "application_url": {
                "value": "https://scholarships.gov.in/apply",
                "text": "Official apply link.",
                "url": url,
            },
        },
    )


def test_persist_merges_same_identity_from_different_source_urls(db_session):
    first_url = "https://scholarships.gov.in/All-Scholarships"
    second_url = "https://scholarships.gov.in/programmes/merit"
    first = _candidate("Merit Scholarship for Rural Students", first_url)
    second = _candidate("Merit Scholarship for Rural Student!", second_url)

    _persist_candidate(db_session, first, 0, False, [(first_url, first.listing_text)], True)
    _persist_candidate(db_session, second, 1, False, [(second_url, second.listing_text)], True)

    records = list(db_session.scalars(select(Scholarship)).all())
    assert len(records) == 1
    assert records[0].official_source_url == first_url
    source_urls = set(
        db_session.scalars(
            select(SourceEvidence.source_url).where(SourceEvidence.scholarship_id == records[0].id)
        ).all()
    )
    assert {first_url, second_url} <= source_urls


def test_cleanup_merges_existing_rows_and_preserves_evidence_and_history(
    db_session,
    scholarship_values,
):
    now = utc_now_iso()
    first = Scholarship(
        **{
            **scholarship_values,
            "id": "duplicate-a",
            "scholarship_name": "Merit Scholarship for Rural Students",
            "provider": "Sample Government Department",
            "official_source_url": "https://sample.gov.in/first",
            "created_at": "2026-10-01T00:00:00+00:00",
        }
    )
    second = Scholarship(
        **{
            **scholarship_values,
            "id": "duplicate-b",
            "scholarship_name": "Merit Scholarship for Rural Student!",
            "provider": "Sample Government Department",
            "official_source_url": "https://sample.gov.in/second",
            "created_at": "2026-10-02T00:00:00+00:00",
        }
    )
    db_session.add_all([first, second])
    db_session.flush()
    for record in (first, second):
        db_session.add_all(
            [
                SourceEvidence(
                    id=f"name-{record.id}",
                    scholarship_id=record.id,
                    field_name="scholarship_name",
                    extracted_value=record.scholarship_name,
                    evidence_text=record.scholarship_name,
                    source_url=record.official_source_url,
                    captured_at=now,
                ),
                SourceEvidence(
                    id=f"eligibility-{record.id}",
                    scholarship_id=record.id,
                    field_name="eligibility",
                    extracted_value="Students must have passed Class 12.",
                    evidence_text="Students must have passed Class 12.",
                    source_url=record.official_source_url,
                    captured_at=now,
                ),
            ]
        )
    db_session.add(
        ChangeHistory(
            id="duplicate-change",
            scholarship_id=second.id,
            field_changed="closing_date",
            old_value="31 October 2026",
            new_value="30 October 2026",
            date_detected=now,
            source_url=second.official_source_url,
            evidence="Official page excerpt.",
            is_demo=False,
        )
    )
    db_session.flush()

    removed, merged = cleanup_existing_records(
        db_session,
        checked_source_urls=set(),
        fresh_since=datetime.now(timezone.utc).isoformat(),
    )

    records = list(db_session.scalars(select(Scholarship)).all())
    assert removed == 0
    assert merged == 1
    assert len(records) == 1
    assert db_session.scalar(
        select(func.count()).select_from(SourceEvidence).where(
            SourceEvidence.scholarship_id == records[0].id
        )
    ) == 4
    history = db_session.scalar(
        select(ChangeHistory).where(ChangeHistory.scholarship_id == records[0].id)
    )
    assert history is not None
    assert history.old_value == "31 October 2026"


def test_cleanup_removes_portal_pages_kept_as_scholarships(db_session, scholarship_values):
    db_session.add(
        Scholarship(
            **{
                **scholarship_values,
                "id": "portal-home",
                "scholarship_name": "NSP : National Scholarship Portal",
                "official_source_url": "https://scholarships.gov.in/",
                "eligibility": "Students must meet the published criteria.",
            }
        )
    )
    db_session.add(
        SourceEvidence(
            id="portal-eligibility",
            scholarship_id="portal-home",
            field_name="eligibility",
            extracted_value="Students must meet the published criteria.",
            evidence_text="Students must meet the published criteria.",
            source_url="https://scholarships.gov.in/",
            captured_at=utc_now_iso(),
        )
    )
    db_session.flush()
    assert is_portal_or_navigation_page("https://scholarships.gov.in/", "NSP : National Scholarship Portal")
    removed, merged = cleanup_existing_records(
        db_session,
        checked_source_urls=set(),
        fresh_since=datetime.now(timezone.utc).isoformat(),
    )
    assert removed == 1
    assert merged == 0
    assert list(db_session.scalars(select(Scholarship)).all()) == []
