from __future__ import annotations

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
