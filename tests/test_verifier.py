from crawler.verifier import verify_official_source


def test_official_source_and_evidence_are_checked_separately():
    verified = verify_official_source(
        "https://department.gov.in/scholarship",
        "Official Student Scholarship eligibility students",
        "Official Student Scholarship",
        "https://department.gov.in/apply",
        {"eligibility": "Students are eligible"},
    )
    assert verified["official_source_verified"] is True
    assert verified["scholarship_found_on_official_page"] is True
    assert verified["official_application_url"] is True
    assert verified["deadline_supported"] is False


def test_aggregator_is_not_an_authoritative_source():
    verified = verify_official_source(
        "https://buddy4study.com/scholarship",
        "Official Student Scholarship",
        "Official Student Scholarship",
        "Not specified",
        {},
    )
    assert verified["official_source_verified"] is False
