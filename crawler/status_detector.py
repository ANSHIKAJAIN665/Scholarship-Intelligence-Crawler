from __future__ import annotations

from datetime import date, datetime, timedelta
from dateutil import parser as date_parser

NOT_SPECIFIED = "Not specified"
STATUSES = {"ACTIVE", "EXPIRING_SOON", "EXPIRED", "REVIEW_REQUIRED", "NO_LONGER_VERIFIABLE"}


def parse_date(value: str) -> date | None:
    if not value or value == NOT_SPECIFIED:
        return None
    try:
        return date_parser.parse(value, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def detect_status(
    closing_date: str,
    *,
    source_verified: bool,
    scholarship_present: bool,
    application_open: bool = False,
    application_closed: bool = False,
    today: date | None = None,
) -> str:
    if not source_verified:
        return "REVIEW_REQUIRED"
    if not scholarship_present:
        return "NO_LONGER_VERIFIABLE"
    today = today or date.today()
    deadline = parse_date(closing_date)
    if deadline is not None and deadline < today:
        return "EXPIRED"
    if application_closed:
        return "EXPIRED"
    if deadline is not None and deadline <= today + timedelta(days=14):
        return "EXPIRING_SOON"
    if deadline is None:
        return "ACTIVE" if application_open else "REVIEW_REQUIRED"
    return "ACTIVE"


def is_expired(closing_date: str, today: date | None = None) -> bool:
    parsed = parse_date(closing_date)
    return parsed is not None and parsed < (today or date.today())
