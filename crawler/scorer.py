from __future__ import annotations

from typing import Any


SCORE_RULES = [
    ("Official source verified", "official_source_verified", 25),
    ("Scholarship found on official page", "scholarship_found_on_official_page", 20),
    ("Official application URL", "official_application_url", 15),
    ("Eligibility evidence", "eligibility_supported", 10),
    ("Deadline evidence", "deadline_supported", 10),
    ("Current information", "current_information_verified", 10),
    ("Schema consistency", "schema_consistent", 5),
    ("No conflicting official information", "no_conflicting_official_information", 5),
]


def calculate_confidence(signals: dict[str, Any]) -> tuple[int, str, list[dict[str, Any]]]:
    signals = dict(signals)
    if signals.get("critical_evidence_valid") is False:
        signals["schema_consistent"] = False
        signals["current_information_verified"] = False
    if signals.get("specific_opportunity") is False:
        signals["scholarship_found_on_official_page"] = False
        signals["schema_consistent"] = False
        signals["official_application_url"] = False
    breakdown = []
    total = 0
    for label, key, points in SCORE_RULES:
        earned = points if bool(signals.get(key, False)) else 0
        total += earned
        reason = "Supported by the official source and recorded evidence." if earned else {
            "official_source_verified": "The source could not be verified as an official HTTPS domain.",
            "scholarship_found_on_official_page": "The named opportunity was not present in the official page text.",
            "official_application_url": "No verified official application URL was found.",
            "eligibility_supported": "No source excerpt supporting eligibility was captured.",
            "deadline_supported": "No source excerpt supporting the closing date was captured.",
            "current_information_verified": "The official page could not be checked successfully.",
            "schema_consistent": "The record contains malformed or unsupported critical source evidence.",
            "no_conflicting_official_information": "Conflicting official details were detected.",
        }[key]
        breakdown.append({"label": label, "points": points, "earned": earned, "reason": reason})
    return total, "VERIFIED" if total >= 95 else "REVIEW_REQUIRED", breakdown
