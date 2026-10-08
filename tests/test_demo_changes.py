from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import _read_demo_changes
from database.database import Base
from database.models import ChangeHistory, Scholarship


def test_demo_change_response_keeps_before_after_date_source_and_evidence(
    tmp_path: Path,
    scholarship_values,
):
    database_path = tmp_path / "isolated-demo.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        record = Scholarship(
            **{
                **scholarship_values,
                "id": "demo-scholarship",
                "scholarship_name": "DEMO DATA — controlled amount change",
                "provider": "DEMO DATA — synthetic only",
                "official_source_url": "https://example.invalid/DEMO-DATA/amount",
            }
        )
        session.add(record)
        session.flush()
        session.add(
            ChangeHistory(
                id="demo-change",
                scholarship_id=record.id,
                field_changed="amount",
                old_value="₹40,000 per year",
                new_value="₹50,000 per year",
                date_detected="2026-10-08T00:00:00+00:00",
                source_url="https://example.invalid/DEMO-DATA/amount",
                evidence="DEMO DATA: synthetic award amount changed.",
                is_demo=True,
            )
        )
        session.commit()

    changes = _read_demo_changes(database_path)
    engine.dispose()
    assert len(changes) == 1
    assert changes[0].is_demo
    assert changes[0].old_value == "₹40,000 per year"
    assert changes[0].new_value == "₹50,000 per year"
    assert changes[0].date_detected == "2026-10-08T00:00:00+00:00"
    assert changes[0].source_url.endswith("/amount")
    assert "DEMO DATA" in changes[0].evidence
