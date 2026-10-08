from datetime import date

from crawler.status_detector import detect_status, is_expired, parse_date


def test_date_parsing_and_expiry():
    assert parse_date("31-10-2026") == date(2026, 10, 31)
    assert is_expired("31 August 2026", today=date(2026, 10, 7))
    assert not is_expired("31 October 2026", today=date(2026, 10, 7))


def test_statuses_do_not_assume_unknown_deadlines_are_active():
    today = date(2026, 10, 7)
    assert detect_status("31 August 2026", source_verified=True, scholarship_present=True, today=today) == "EXPIRED"
    assert detect_status("10 October 2026", source_verified=True, scholarship_present=True, today=today) == "EXPIRING_SOON"
    assert detect_status("Not specified", source_verified=True, scholarship_present=True, today=today) == "REVIEW_REQUIRED"
    assert detect_status("Not specified", source_verified=False, scholarship_present=True, today=today) == "REVIEW_REQUIRED"
    assert detect_status("31 December 2026", source_verified=True, scholarship_present=False, today=today) == "NO_LONGER_VERIFIABLE"
    assert detect_status(
        "Not specified",
        source_verified=True,
        scholarship_present=True,
        application_open=True,
        today=today,
    ) == "ACTIVE"
    assert detect_status(
        "Not specified",
        source_verified=True,
        scholarship_present=True,
        application_closed=True,
        today=today,
    ) == "EXPIRED"


def test_stale_and_expired_statuses_are_explicit():
    today = date(2026, 10, 8)
    assert detect_status("01 January 2026", source_verified=True, scholarship_present=True, today=today) == "EXPIRED"
    assert detect_status(
        "31 December 2026",
        source_verified=True,
        scholarship_present=False,
        today=today,
    ) == "NO_LONGER_VERIFIABLE"
    assert detect_status("20 October 2026", source_verified=True, scholarship_present=True, today=today) == "EXPIRING_SOON"
