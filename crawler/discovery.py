from __future__ import annotations

import time
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from crawler.extractor import (
    Candidate,
    extract_page_candidate,
    is_specific_scholarship_title,
    parse_iitm_scholarships,
    parse_nsp_listings,
    parse_tata_education_grants,
)
from crawler.source_classifier import (
    classify_source,
    is_official_domain,
    normalized_host,
    normalized_identity,
    normalized_page_identity,
)

USER_AGENT = "ScholarshipIntelligenceCrawler/1.0 (+official-source research; requests are rate-limited)"
REQUEST_TIMEOUT = 18
REQUEST_DELAY_SECONDS = 0.5
MAX_CANDIDATES = 100
SEED_SOURCES = [
    {
        "url": "https://scholarships.gov.in/All-Scholarships",
        "source_type": "government",
        "provider": "National Scholarship Portal",
    },
    {
        "url": "https://www.aicte.gov.in/bureaus/scholarships-and-grants",
        "source_type": "government",
        "provider": "All India Council for Technical Education",
    },
    {
        "url": "https://www.iitm.ac.in/academics/academic-services/scholarships-and-financial-assistance",
        "source_type": "university",
        "provider": "Indian Institute of Technology Madras",
    },
    {
        "url": "https://socialjustice.gov.in/",
        "source_type": "government",
        "provider": "Department of Social Justice and Empowerment",
    },
    {
        "url": "https://www.tatatrusts.org/our-work/education/education-grants",
        "source_type": "foundation",
        "provider": "Tata Trusts",
    },
]
TRUSTED_SEED_HOSTS = {normalized_host(source["url"]) for source in SEED_SOURCES}
SCHOLARSHIP_TERMS = ("scholarship", "fellowship", "stipend", "education grant", "financial assistance")
IGNORED_FILE_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".zip", ".doc", ".docx")


@dataclass
class DiscoveryResult:
    candidates: list[Candidate]
    failed_count: int
    checked_indexes: dict[str, str]
    errors: list[str]


class RespectfulFetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf"})
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlparse(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            robots_url = f"{base}/robots.txt"
            try:
                response = self.session.get(robots_url, timeout=REQUEST_TIMEOUT)
                if response.status_code in (401, 403) or response.status_code >= 500:
                    self._robots[base] = None
                elif response.status_code == 404:
                    self._robots[base] = RobotFileParser()
                    self._robots[base].parse([])
                else:
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                    self._robots[base] = parser
            except requests.RequestException:
                self._robots[base] = None
        parser = self._robots[base]
        return bool(parser and parser.can_fetch(USER_AGENT, url))

    def get(self, url: str) -> requests.Response:
        host = normalized_host(url)
        elapsed = time.monotonic() - self._last_request.get(host, 0)
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        if not self.allowed_by_robots(url):
            raise PermissionError(f"robots.txt disallows crawling {url} or could not be verified")
        response = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        self._last_request[host] = time.monotonic()
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").casefold()
        if "text/html" in content_type and len(response.text.strip()) < 1800:
            rendered = self._render_javascript(url)
            if rendered and len(rendered) > len(response.text):
                return SimpleNamespace(
                    status_code=response.status_code,
                    url=response.url,
                    text=rendered,
                    content=rendered.encode("utf-8"),
                    headers={"content-type": "text/html; charset=utf-8"},
                )
        return response

    @staticmethod
    def _render_javascript(url: str) -> str:
        """Optional Playwright fallback for short JS-shell pages; never bypasses robots or HTTP blocks."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                    page.wait_for_timeout(900)
                    return page.content()
                finally:
                    browser.close()
        except Exception:
            # Static HTTP content remains usable; the crawl log records a page failure only if that also fails.
            return ""


def _candidate_key(candidate: Candidate) -> tuple[str, str]:
    return normalized_identity(candidate.scholarship_name), normalized_page_identity(candidate.source_url)


def discover_candidates(fetcher: RespectfulFetcher | None = None) -> DiscoveryResult:
    fetcher = fetcher or RespectfulFetcher()
    candidates: dict[tuple[str, str], Candidate] = {}
    checked_indexes: dict[str, str] = {}
    errors: list[str] = []
    failed_count = 0
    queue: list[dict[str, str]] = list(SEED_SOURCES)
    seen_urls: set[str] = set()

    while queue and len(seen_urls) < MAX_CANDIDATES:
        source = queue.pop(0)
        url = source["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            response = fetcher.get(url)
            checked_indexes[url] = response.text
            soup = BeautifulSoup(response.text, "html.parser")
            host = normalized_host(response.url)

            is_nsp_listing = host == normalized_host(SEED_SOURCES[0]["url"]) and "All-Scholarships" in response.url
            if is_nsp_listing:
                for candidate in parse_nsp_listings(response.text, response.url):
                    candidates.setdefault(_candidate_key(candidate), candidate)
            elif host == "iitm.ac.in" and "scholarship" in response.url.casefold():
                for candidate in parse_iitm_scholarships(response.text, response.url):
                    candidates.setdefault(_candidate_key(candidate), candidate)
            elif host == "tatatrusts.org" and "education-grants" in response.url.casefold():
                for candidate in parse_tata_education_grants(response.text, response.url):
                    candidates.setdefault(_candidate_key(candidate), candidate)
            elif source.get("is_detail"):
                candidate = extract_page_candidate(
                    response.text,
                    response.url,
                    title_hint=source.get("title_hint", ""),
                    provider_hint=source.get("provider", "Not specified"),
                )
                if candidate:
                    candidate.source_type = classify_source(candidate.source_url, TRUSTED_SEED_HOSTS)
                    if candidate.source_type not in ("aggregator", "unverified"):
                        candidates.setdefault(_candidate_key(candidate), candidate)

            for anchor in soup.select("a[href]"):
                label = " ".join(anchor.get_text(" ", strip=True).split())
                href = urljoin(response.url, anchor.get("href", ""))
                href_parts = urlparse(href)
                if href_parts.scheme not in ("http", "https") or href.lower().split("?")[0].endswith(IGNORED_FILE_SUFFIXES):
                    continue
                if not is_official_domain(href, TRUSTED_SEED_HOSTS):
                    continue
                label_lower = label.casefold()
                path_lower = href_parts.path.casefold()
                if not is_specific_scholarship_title(label):
                    continue
                if any(
                    marker in path_lower
                    for marker in (
                        "announcement",
                        "copyright",
                        "disclaimer",
                        "faq",
                        "helpdesk",
                        "institute",
                        "institution",
                        "login",
                        "nodalofficer",
                        "officer",
                        "otrapplication",
                        "payl",
                        "privacy",
                        "recognitions",
                        "sitemap",
                        "site-map",
                        "terms",
                    )
                ):
                    continue
                if href not in seen_urls and len(seen_urls) + len(queue) < MAX_CANDIDATES:
                    link_provider = source.get("provider", "Not specified")
                    queue.append(
                        {
                            "url": href,
                            "source_type": classify_source(href, TRUSTED_SEED_HOSTS),
                            "provider": link_provider,
                            "title_hint": label,
                            "is_detail": "true",
                        }
                    )

        except (requests.RequestException, PermissionError, ValueError) as exc:
            failed_count += 1
            errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:240]}")

    return DiscoveryResult(
        candidates=list(candidates.values()),
        failed_count=failed_count,
        checked_indexes=checked_indexes,
        errors=errors,
    )
