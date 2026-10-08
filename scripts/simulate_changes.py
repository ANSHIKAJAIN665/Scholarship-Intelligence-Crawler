#!/usr/bin/env python3
"""Demonstrate change history in an isolated database; never alters live records."""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
demo_db = ROOT / "data" / "demo-changes.db"
demo_db.parent.mkdir(parents=True, exist_ok=True)

os.environ["SCHOLARSHIP_DATABASE_URL"] = f"sqlite:///{demo_db}"

from crawler.change_detector import TRACKED_FIELDS, record_changes  # noqa: E402
from database.database import Base, SessionLocal, engine  # noqa: E402
from database.models import ChangeHistory, Scholarship  # noqa: E402
from models.scholarship import utc_now_iso  # noqa: E402


DEMO_CASES = (
    {
        "name": "DEMO DATA — Controlled deadline change example",
        "field": "closing_date",
        "old": "31 August 2026",
        "new": "15 September 2026",
        "source": "https://example.invalid/DEMO-DATA/deadline-change",
        "evidence": "DEMO DATA: simulated official-page excerpt changed the application deadline.",
    },
    {
        "name": "DEMO DATA — Controlled award amount change example",
        "field": "amount",
        "old": "₹40,000 per year",
        "new": "₹50,000 per year",
        "source": "https://example.invalid/DEMO-DATA/amount-change",
        "evidence": "DEMO DATA: simulated official-page excerpt changed the annual award amount.",
    },
)


def _get_or_create_record(session, case):
    from sqlalchemy import select

    record = session.scalar(
        select(Scholarship).where(Scholarship.scholarship_name == case["name"])
    )
    if record is not None:
        return record
    now = utc_now_iso()
    record = Scholarship(
        id=str(uuid.uuid4()),
        scholarship_name=case["name"],
        provider="DEMO DATA — synthetic example only",
        official_source_url=case["source"],
        application_url="Not specified",
        source_type="demo",
        amount=case["old"] if case["field"] == "amount" else "Not specified",
        benefit="Not specified",
        eligibility="Not specified",
        academic_requirements="Not specified",
        education_level="Not specified",
        course_requirements="Not specified",
        income_criteria="Not specified",
        age_criteria="Not specified",
        gender_criteria="Not specified",
        category_criteria="Not specified",
        domicile_requirements="Not specified",
        institution_requirements="Not specified",
        opening_date="Not specified",
        closing_date=case["old"] if case["field"] == "closing_date" else "Not specified",
        documents_required="Not specified",
        selection_process="Not specified",
        renewal_requirements="Not specified",
        current_status="REVIEW_REQUIRED",
        confidence_score=0,
        verification_status="REVIEW_REQUIRED",
        score_breakdown_json="[]",
        last_verified=now,
        content_hash=hashlib.sha256(case["old"].encode()).hexdigest(),
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.flush()
    return record


def _record_demo_change(session, case) -> bool:
    from sqlalchemy import select

    record = _get_or_create_record(session, case)
    existing_change = session.scalar(
        select(ChangeHistory).where(
            ChangeHistory.scholarship_id == record.id,
            ChangeHistory.field_changed == case["field"],
            ChangeHistory.old_value == case["old"],
            ChangeHistory.new_value == case["new"],
            ChangeHistory.is_demo.is_(True),
        )
    )
    if existing_change:
        setattr(record, case["field"], case["new"])
        return False

    setattr(record, case["field"], case["old"])
    values = {field_name: getattr(record, field_name) for field_name in TRACKED_FIELDS}
    values[case["field"]] = case["new"]
    evidence = [
        {
            "field_name": case["field"],
            "evidence_text": case["evidence"],
            "source_url": case["source"],
        }
    ]
    record_changes(session, record, values, evidence, case["source"])
    for history in session.new:
        if isinstance(history, ChangeHistory) and history.field_changed == case["field"]:
            history.is_demo = True
    setattr(record, case["field"], case["new"])
    record.updated_at = utc_now_iso()
    return True


def main() -> int:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        created = sum(_record_demo_change(session, case) for case in DEMO_CASES)
        session.commit()
        print("DEMO DATA — synthetic examples isolated from the live scholarship database")
        print(f"Recorded {len(DEMO_CASES)} examples; added {created} change-history entries.")
        for case in DEMO_CASES:
            print(f"{case['field']}: {case['old']} → {case['new']}")
            print(f"Source: {case['source']}")
        print(f"Evidence and before/after values are retained in: {demo_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
