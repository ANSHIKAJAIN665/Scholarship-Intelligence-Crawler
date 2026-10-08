from crawler.scorer import calculate_confidence


def test_deterministic_confidence_points_and_threshold():
    signals = {
        "official_source_verified": True,
        "scholarship_found_on_official_page": True,
        "official_application_url": True,
        "eligibility_supported": True,
        "deadline_supported": True,
        "current_information_verified": True,
        "schema_consistent": True,
        "no_conflicting_official_information": True,
    }
    score, status, breakdown = calculate_confidence(signals)
    assert score == 100
    assert status == "VERIFIED"
    assert sum(item["earned"] for item in breakdown) == score

    signals["deadline_supported"] = False
    score, status, _ = calculate_confidence(signals)
    assert score == 90
    assert status == "REVIEW_REQUIRED"


def test_95_point_threshold_is_verified():
    signals = {key: True for _, key, _ in __import__("crawler.scorer", fromlist=["SCORE_RULES"]).SCORE_RULES}
    signals["no_conflicting_official_information"] = False
    score, status, _ = calculate_confidence(signals)
    assert score == 95
    assert status == "VERIFIED"


def test_malformed_critical_evidence_cannot_keep_a_95_plus_score():
    signals = {key: True for _, key, _ in __import__("crawler.scorer", fromlist=["SCORE_RULES"]).SCORE_RULES}
    signals["critical_evidence_valid"] = False
    score, status, breakdown = calculate_confidence(signals)
    assert score == 85
    assert status == "REVIEW_REQUIRED"
    assert sum(item["earned"] for item in breakdown) == score
