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


def test_official_university_and_foundation_hosts_are_accepted():
    university = verify_official_source(
        "https://www.iitm.ac.in/scholarships",
        "Institute Merit Scholarship eligibility students",
        "Institute Merit Scholarship",
        "https://www.iitm.ac.in/apply",
        {"eligibility": "Eligible students must have a published income limit."},
    )
    foundation = verify_official_source(
        "https://www.tatatrusts.org/our-work/education/education-grants",
        "J N Tata Endowment loan scholarship eligibility students",
        "J N Tata Endowment loan scholarship",
        "Not specified",
        {"eligibility": "The scheme is open to graduates for overseas studies."},
        trusted_seed_hosts={"tatatrusts.org"},
    )
    assert university["official_source_verified"] is True
    assert foundation["official_source_verified"] is True
    assert foundation["official_application_url"] is False


def test_heading_only_eligibility_is_not_supported_evidence():
    verified = verify_official_source(
        "https://department.gov.in/scholarship",
        "Official Student Scholarship",
        "Official Student Scholarship",
        "https://department.gov.in/apply",
        {"eligibility": "Eligibility:", "closing_date": "deadline:"},
    )
    assert verified["eligibility_supported"] is False
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
