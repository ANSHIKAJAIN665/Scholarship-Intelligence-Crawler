from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".ac.in", ".edu.in", ".gov", ".edu")
TRUSTED_PROVIDER_HOSTS = {"tatatrusts.org"}
AGGREGATOR_MARKERS = (
    "buddy4study",
    "scholarshipportal",
    "collegedunia",
    "careers360",
    "shiksha",
    "getmyuni",
    "leverageedu",
)


def normalized_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def normalized_identity(value: str) -> str:
    """Normalize punctuation, accents, and common award plurals for identity checks."""
    value = unicodedata.normalize("NFKD", value.casefold().replace("&", " and "))
    value = "".join(character for character in value if not unicodedata.combining(character))
    tokens = re.findall(r"[a-z0-9]+", value)
    plural_forms = {
        "scholarships": "scholarship",
        "fellowships": "fellowship",
        "stipends": "stipend",
    }
    return " ".join(plural_forms.get(token, token) for token in tokens)


def scholarship_identity_key(provider: str, name: str, source_url: str) -> tuple[str, str]:
    provider_key = normalized_identity(provider)
    if provider_key in {"", "not specified", "unknown"}:
        provider_key = normalized_host(source_url)
    return provider_key, normalized_identity(name)


def same_scholarship_identity(
    provider_a: str,
    name_a: str,
    source_url_a: str,
    provider_b: str,
    name_b: str,
    source_url_b: str,
) -> bool:
    provider_key_a, name_key_a = scholarship_identity_key(provider_a, name_a, source_url_a)
    provider_key_b, name_key_b = scholarship_identity_key(provider_b, name_b, source_url_b)
    if not provider_key_a or provider_key_a != provider_key_b or not name_key_a or not name_key_b:
        return False
    if name_key_a == name_key_b:
        return True
    return min(len(name_key_a), len(name_key_b)) >= 18 and SequenceMatcher(
        None, name_key_a, name_key_b
    ).ratio() >= 0.94


def normalized_page_identity(url: str) -> str:
    """Drop URL fragments and trailing slashes while keeping distinct source URLs."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{normalized_host(url)}{path}{query}".casefold()


def is_aggregator(url: str) -> bool:
    host = normalized_host(url)
    return any(marker in host for marker in AGGREGATOR_MARKERS)


def is_official_domain(url: str, trusted_seed_hosts: set[str] | None = None) -> bool:
    host = normalized_host(url)
    if not host or is_aggregator(url):
        return False
    trusted_hosts = TRUSTED_PROVIDER_HOSTS | {
        item.lower().removeprefix("www.") for item in (trusted_seed_hosts or set())
    }
    if host in trusted_hosts:
        return True
    return host.endswith(OFFICIAL_SUFFIXES)


def classify_source(url: str, trusted_seed_hosts: set[str] | None = None) -> str:
    host = normalized_host(url)
    if not host:
        return "unknown"
    if is_aggregator(url):
        return "aggregator"
    if not is_official_domain(url, trusted_seed_hosts):
        return "unverified"
    if host.endswith((".gov.in", ".nic.in", ".gov")):
        return "government"
    if host.endswith((".ac.in", ".edu.in", ".edu")):
        return "university"
    if host == "tatatrusts.org":
        return "foundation"
    return "official_provider"
