from crawler.extractor import (
    Candidate,
    extract_page_candidate,
    extract_record,
    is_specific_scholarship_title,
    parse_iitm_scholarships,
    parse_tata_education_grants,
)
from models.scholarship import ScholarshipData


def test_extracts_evidence_and_explicitly_marks_missing_fields():
    html = """
    <html><head><title>Merit Scholarship</title></head><body>
    <h1>Merit Scholarship</h1>
    <p>Eligible students must have passed Class 12.</p>
    <p>Applications close on 31 October 2026.</p>
    <a href="https://sample.gov.in/apply">Apply online</a>
    </body></html>
    """
    candidate = extract_page_candidate(html, "https://sample.gov.in/scholarship", provider_hint="Sample Department")
    assert candidate is not None
    record, evidence, _score = extract_record(
        candidate,
        [(candidate.source_url, candidate.listing_text)],
        current_page_checked=True,
    )
    assert isinstance(record, ScholarshipData)
    assert record.eligibility != "Not specified"
    assert record.closing_date != "Not specified"
    assert record.income_criteria == "Not specified"
    assert any(item["field_name"] == "closing_date" for item in evidence)


def test_missing_fields_never_get_guessed():
    record = ScholarshipData(
        scholarship_name="Published Scholarship",
        official_source_url="https://sample.gov.in/scholarship",
    )
    assert record.amount == "Not specified"
    assert record.age_criteria == "Not specified"


def test_official_university_table_becomes_separate_evidence_backed_records():
    html = """
    <table>
      <tr><th>Scholarship</th><th>Eligibility Criteria</th><th>Amount Of Scholarship</th></tr>
      <tr><td>Institute Merit Scholarship</td><td>Parents' annual income below the published limit.</td><td>67% tuition fee exemption</td></tr>
    </table>
    """
    records = parse_iitm_scholarships(html, "https://www.iitm.ac.in/scholarships")
    assert len(records) == 1
    assert records[0].scholarship_name == "Institute Merit Scholarship"
    assert records[0].evidence["eligibility"]["value"] == "Parents' annual income below the published limit."
    assert records[0].evidence["amount"]["value"] == "67% tuition fee exemption"


def test_foundation_page_states_active_and_closed_programmes_explicitly():
    html = """
    <h3>Means grant</h3>
    <p>The Means Grant Programme provides partial financial assistance based on students' needs.</p>
    <p>The scheme is open to school-going students from Standard VIII onwards.</p>
    <p>Applications are currently being accepted online for the 2026-27 academic year.</p>
    <h3>Medical and Healthcare Scholarship</h3>
    <p>Submission for this scholarship is no longer accepted.</p>
    """
    records = parse_tata_education_grants(html, "https://www.tatatrusts.org/our-work/education/education-grants")
    by_name = {item.scholarship_name: item for item in records}
    assert by_name["Tata Trusts Means Grant Programme"].evidence["current_status"]["value"] == "ACTIVE"
    assert by_name["Medical and Healthcare Scholarship"].evidence["current_status"]["value"] == "EXPIRED"
    assert by_name["Tata Trusts Means Grant Programme"].application_url == "Not specified"


def test_navigation_and_portal_titles_are_not_opportunity_candidates():
    assert not is_specific_scholarship_title("NSP : National Scholarship Portal")
    assert not is_specific_scholarship_title("Scholarship Eligibility")
    assert not is_specific_scholarship_title("All Scholarships")
    assert is_specific_scholarship_title("National Merit Scholarship for Rural Students")


def test_malformed_amount_eligibility_and_deadline_are_not_stored_or_verified():
    url = "https://sample.gov.in/merit-scholarship"
    candidate = Candidate(
        scholarship_name="National Merit Scholarship for Rural Students",
        source_url=url,
        provider="Sample Government Department",
        listing_text="National Merit Scholarship for Rural Students",
        evidence={
            "scholarship_name": {
                "value": "National Merit Scholarship for Rural Students",
                "text": "National Merit Scholarship for Rural Students",
                "url": url,
            },
            "amount": {"value": "Rs.", "text": "Scholarship amount: Rs.", "url": url},
            "eligibility": {
                "value": "2.1 Eligibility and course duration 17",
                "text": "2.1 Eligibility and course duration 17",
                "url": url,
            },
            "closing_date": {
                "value": "October 2026",
                "text": "Applications close in October 2026.",
                "url": url,
            },
        },
    )
    record, evidence, breakdown = extract_record(
        candidate,
        [(url, candidate.listing_text)],
        current_page_checked=True,
    )
    assert record.amount == "Not specified"
    assert record.eligibility == "Not specified"
    assert record.closing_date == "Not specified"
    assert not {"amount", "eligibility", "closing_date"} & {
        item["field_name"] for item in evidence
    }
    assert record.confidence_score < 95
    assert record.verification_status == "REVIEW_REQUIRED"
    assert sum(item["earned"] for item in breakdown) == record.confidence_score


def test_amount_pattern_requires_a_numeric_source_value():
    html = """
    <h1>National Merit Scholarship for Rural Students</h1>
    <p>Scholarship amount: Rs.</p>
    <p>Eligible students must have passed Class 12.</p>
    <p>Applications close on 31 October 2026.</p>
    """
    candidate = extract_page_candidate(html, "https://sample.gov.in/merit")
    assert candidate is not None
    record, evidence, _ = extract_record(
        candidate,
        [(candidate.source_url, candidate.listing_text)],
        current_page_checked=True,
    )
    assert record.amount == "Not specified"
    assert not any(item["field_name"] == "amount" for item in evidence)
    assert record.verification_status == "REVIEW_REQUIRED"
