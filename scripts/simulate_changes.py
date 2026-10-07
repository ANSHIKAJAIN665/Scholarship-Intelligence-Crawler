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


def main() -> int:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        old_deadline = "31 August 2026"
        new_deadline = "15 September 2026"
        demo_name = "DEMO DATA — Controlled deadline change example"
        from sqlalchemy import select

        record = session.scalar(select(Scholarship).where(Scholarship.scholarship_name == demo_name))
        if record is None:
            now = utc_now_iso()
            record = Scholarship(
                id=str(uuid.uuid4()),
                scholarship_name=demo_name,
                provider="DEMO DATA — not a real scholarship",
                official_source_url="https://example.invalid/DEMO-DATA",
                application_url="Not specified",
                source_type="demo",
                amount="Not specified",
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
                closing_date=old_deadline,
                documents_required="Not specified",
                selection_process="Not specified",
                renewal_requirements="Not specified",
                current_status="REVIEW_REQUIRED",
                confidence_score=0,
                verification_status="REVIEW_REQUIRED",
                score_breakdown_json="[]",
                last_verified=now,
                content_hash=hashlib.sha256(old_deadline.encode()).hexdigest(),
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()
        existing_change = session.scalar(
            select(ChangeHistory).where(
                ChangeHistory.scholarship_id == record.id,
                ChangeHistory.field_changed == "closing_date",
                ChangeHistory.old_value == old_deadline,
                ChangeHistory.new_value == new_deadline,
                ChangeHistory.is_demo.is_(True),
            )
        )
        if existing_change:
            print("DEMO DATA — isolated from the live scholarship database")
            print(f"CHANGE DETECTED: {existing_change.old_value} → {existing_change.new_value}")
            print(f"Previous value retained in change history; database: {demo_db}")
            return 0
        evidence = [
            {
                "field_name": "closing_date",
                "evidence_text": "DEMO DATA: simulated source text changed the deadline.",
                "source_url": record.official_source_url,
            }
        ]
        values = {field_name: getattr(record, field_name) for field_name in TRACKED_FIELDS}
        values["closing_date"] = new_deadline
        record_changes(session, record, values, evidence, record.official_source_url)
        for history in session.new:
            if isinstance(history, ChangeHistory) and history.field_changed == "closing_date":
                history.is_demo = True
        record.closing_date = new_deadline
        record.updated_at = utc_now_iso()
        session.commit()
        print("DEMO DATA — isolated from the live scholarship database")
        print(f"CHANGE DETECTED: {old_deadline} → {new_deadline}")
        print(f"Previous value retained in change history; database: {demo_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
