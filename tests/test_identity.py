from crawler.source_classifier import (
    normalized_identity,
    same_scholarship_identity,
)


def test_normalizes_punctuation_and_common_plural_forms():
    assert normalized_identity("J. N. Tata Endowment — Loan Scholarships") == (
        "j n tata endowment loan scholarship"
    )


def test_same_provider_and_name_merge_across_distinct_urls():
    assert same_scholarship_identity(
        "Tata Trusts",
        "J. N. Tata Endowment Loan Scholarship",
        "https://www.tatatrusts.org/education/grants",
        "Tata Trusts",
        "JN Tata Endowment Loan Scholarship",
        "https://www.tatatrusts.org/education/jntata",
    )


def test_identity_does_not_merge_across_providers():
    assert not same_scholarship_identity(
        "Tata Trusts",
        "National Merit Scholarship for Rural Students",
        "https://www.tatatrusts.org/programme",
        "Sample Government Department",
        "National Merit Scholarship for Rural Students",
        "https://sample.gov.in/programme",
    )


def test_minor_spelling_variant_is_matched_only_with_the_same_provider():
    assert same_scholarship_identity(
        "Sample Department",
        "M Sankaraiah Scholarship for SC Students",
        "https://sample.gov.in/one",
        "Sample Department",
        "M Sankaraiah Scholarhsip for SC Students",
        "https://sample.gov.in/two",
    )
