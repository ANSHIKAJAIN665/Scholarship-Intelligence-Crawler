from sqlalchemy import select

from crawler.change_detector import record_changes
from database.models import ChangeHistory, Scholarship


def test_change_detection_retains_old_and_new_values(db_session, scholarship_values):
    scholarship = Scholarship(**{**scholarship_values, "closing_date": "31 August 2026"})
    db_session.add(scholarship)
    db_session.commit()
    changed = record_changes(
        db_session,
        scholarship,
        {**scholarship_values, "closing_date": "15 September 2026"},
        [
            {
                "field_name": "closing_date",
                "evidence_text": "Applications close on 15 September 2026.",
                "source_url": "https://test.gov.in/scholarship",
            }
        ],
        scholarship.official_source_url,
    )
    db_session.commit()
    history = db_session.scalar(select(ChangeHistory))
    assert changed == ["closing_date"]
    assert history is not None
    assert (history.old_value, history.new_value) == ("31 August 2026", "15 September 2026")
