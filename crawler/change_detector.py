from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from database.models import ChangeHistory, Scholarship

TRACKED_FIELDS = (
    "amount",
    "benefit",
    "eligibility",
    "closing_date",
    "opening_date",
    "application_url",
    "documents_required",
    "academic_requirements",
    "current_status",
)


def record_changes(
    session: Any,
    existing: Scholarship,
    new_values: dict[str, Any],
    evidence: list[dict[str, str]],
    source_url: str,
) -> list[str]:
    evidence_by_field = {item["field_name"]: item for item in evidence}
    changed_fields: list[str] = []
    detected_at = datetime.now(timezone.utc).isoformat()
    for field_name in TRACKED_FIELDS:
        old_value = getattr(existing, field_name)
        new_value = new_values[field_name]
        if old_value == new_value:
            continue
        excerpt = evidence_by_field.get(field_name, {}).get(
            "evidence_text",
            "The latest successful official-source check returned a different value.",
        )
        evidence_url = evidence_by_field.get(field_name, {}).get("source_url", source_url)
        session.add(
            ChangeHistory(
                id=str(uuid.uuid4()),
                scholarship_id=existing.id,
                field_changed=field_name,
                old_value=old_value,
                new_value=new_value,
                date_detected=detected_at,
                source_url=evidence_url,
                evidence=excerpt,
                is_demo=False,
            )
        )
        changed_fields.append(field_name)
    return changed_fields
