from __future__ import annotations

from urllib.parse import urlparse

from crawler.source_classifier import is_official_domain, normalized_host


def _same_official_owner(source_url: str, candidate_url: str, trusted_seed_hosts: set[str]) -> bool:
    if not candidate_url.startswith(("http://", "https://")):
        return False
    source_host = normalized_host(source_url)
    candidate_host = normalized_host(candidate_url)
    if source_host == candidate_host:
        return is_official_domain(candidate_url, trusted_seed_hosts)
    if not is_official_domain(candidate_url, trusted_seed_hosts):
        return False
    # Cross-site destinations are accepted only if both are government/university hosts.
    source_kind = urlparse(source_url).hostname or ""
    candidate_kind = urlparse(candidate_url).hostname or ""
    return any(suffix in source_kind for suffix in (".gov.in", ".nic.in", ".ac.in", ".edu.in")) and any(
        suffix in candidate_kind for suffix in (".gov.in", ".nic.in", ".ac.in", ".edu.in")
    )


def verify_official_source(
    source_url: str,
    page_text: str,
    scholarship_name: str,
    application_url: str,
    evidence: dict[str, str],
    *,
    current_page_checked: bool = True,
    conflicting_information: bool = False,
    trusted_seed_hosts: set[str] | None = None,
) -> dict[str, bool]:
    trusted_seed_hosts = trusted_seed_hosts or set()
    lowered = page_text.casefold()
    name_tokens = [token for token in scholarship_name.casefold().split() if len(token) > 3]
    name_supported = bool(name_tokens) and sum(token in lowered for token in name_tokens) >= min(2, len(name_tokens))
    official = source_url.startswith("https://") and is_official_domain(source_url, trusted_seed_hosts)
    return {
        "official_source_verified": official,
        "scholarship_found_on_official_page": official and name_supported,
        "official_application_url": application_url != "Not specified"
        and _same_official_owner(source_url, application_url, trusted_seed_hosts),
        "eligibility_supported": bool(evidence.get("eligibility")),
        "deadline_supported": bool(evidence.get("closing_date")),
        "current_information_verified": current_page_checked and official,
        "no_conflicting_official_information": not conflicting_information,
    }
