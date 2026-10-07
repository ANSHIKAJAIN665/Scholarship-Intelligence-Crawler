from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from crawler.source_classifier import classify_source
from crawler.status_detector import NOT_SPECIFIED, detect_status
from models.scholarship import ScholarshipData

SCHOLARSHIP_TERMS = ("scholarship", "fellowship", "stipend")
GENERIC_OPPORTUNITY_TITLES = {
    "all scholarships",
    "fellowship opportunities",
    "national scholarship portal",
    "nsp national scholarship portal",
    "scholarship and fellowship information",
    "scholarship application",
    "scholarship eligibility",
    "scholarship list",
    "scholarship opportunities",
    "scholarship portal",
    "scholarship scheme",
    "scholarships and grants",
    "student scholarships",
}
FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "amount": (r"₹\s?[\d,.]+(?:\s?(?:lakh|lakhs|crore|per year|monthly|annually))?", r"rs\.?\s?[\d,.]+", r"inr\s?[\d,.]+", r"\b\d+(?:,\d{3})+\s*(?:per annum|per year|monthly)\b"),
    "benefit": (r"\b(?:scholarship amount|maintenance allowance|stipend|tuition fee|fee reimbursement|financial assistance|financial support|award of)\b",),
    "eligibility": (r"\b(?:eligibility|eligible|applicants? must|students? who|student should|students belonging|candidate must)\b",),
    "academic_requirements": (r"\b(?:minimum marks?|percentage|cgpa|grade point|passed in|qualifying examination|merit list|academic year)\b",),
    "education_level": (r"\b(?:class\s*(?:i{1,3}|iv|v|vi{0,3}|ix|x{1,2}|[1-9]|1[0-2])|undergraduate|postgraduate|post-graduate|doctoral|ph\.?d|research scholars?|diploma students?|school students?)\b",),
    "course_requirements": (r"\b(?:degree course|technical course|professional course|engineering|medical|pursuing|enrolled in|course of study|undergraduate course)\b",),
    "income_criteria": (r"\b(?:family income|annual income|income ceiling|parental income|income should not exceed|income limit)\b",),
    "age_criteria": (r"\b(?:age limit|aged between|years of age|age should|age criteria)\b",),
    "gender_criteria": (r"\b(?:girl students?|women candidates?|female candidates?|women students?|gender)\b",),
    "category_criteria": (r"\b(?:scheduled caste|scheduled tribe|other backward classes|obc|sc students?|st students?|minority|ews|economically weaker)\b",),
    "domicile_requirements": (r"\b(?:domicile|resident of|belonging to|native of|state of|union territory)\b",),
    "institution_requirements": (r"\b(?:institution|college|university|institute|accreditation)\b",),
    "opening_date": (r"\b(?:open(?:s|ing)?|application start|commencement date|last date to apply from)\b",),
    "closing_date": (r"\b(?:last date|deadline|closes? on|closing date|applications? close|apply before|student application\s+open till)\b",),
    "documents_required": (r"\b(?:documents? required|upload|certificate|marksheet|bank account|income certificate|caste certificate|proof of)\b",),
    "selection_process": (r"\b(?:selection process|selection criteria|selection will|shortlisted|merit-based|merit list|interview)\b",),
    "renewal_requirements": (r"\b(?:renewal|renewal application|renewed|continuation of scholarship|next academic year)\b",),
}


@dataclass
class Candidate:
    scholarship_name: str
    source_url: str
    provider: str = "Not specified"
    application_url: str = NOT_SPECIFIED
    source_type: str = "unknown"
    listing_text: str = ""
    guideline_url: str = ""
    evidence: dict[str, dict[str, str]] = field(default_factory=dict)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_specific_scholarship_title(value: str) -> bool:
    """Reject portal/navigation headings that mention awards but name no opportunity."""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    if not normalized or normalized in GENERIC_OPPORTUNITY_TITLES:
        return False
    if "faculty fellowship" in normalized:
        return False
    if re.fullmatch(
        r"(?:all )?(?:scholarships?|fellowships?|stipends?)(?: (?:scheme|program|programme|portal|list|details|eligibility|application|opportunities))?",
        normalized,
    ):
        return False
    return any(term in normalized for term in SCHOLARSHIP_TERMS)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _matching_sentence(text: str, patterns: tuple[str, ...]) -> str:
    for sentence in sentences(text):
        if any(re.search(pattern, sentence, re.IGNORECASE) for pattern in patterns):
            return _clean(sentence)[:900]
    return ""


def _evidence_value(text: str, field_name: str) -> str:
    if field_name in ("opening_date", "closing_date"):
        return _clean(text)
    if field_name == "amount":
        matches = [m.group(0) for p in FIELD_PATTERNS[field_name] for m in re.finditer(p, text, re.IGNORECASE)]
        return "; ".join(dict.fromkeys(matches))[:300] if matches else _clean(text)[:900]
    return _clean(text)[:900]


def extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages).strip()
    except Exception:
        return ""


def parse_nsp_listings(html: str, page_url: str) -> list[Candidate]:
    """Read live opportunity cards from NSP's public 2026–27 listing, not a static record set."""
    soup = BeautifulSoup(html, "html.parser")
    application_url = NOT_SPECIFIED
    for link in soup.select("a[href]"):
        if "apply for scholarship" in _clean(link.get_text(" ", strip=True)).casefold():
            application_url = urljoin(page_url, link["href"])
            break

    found: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.select("a[href]"):
        if _clean(anchor.get_text(" ", strip=True)).casefold() != "specifications":
            continue
        row = anchor.find_parent(
            "div",
            class_=lambda classes: classes is not None
            and "row" in classes
            and "border-bottom" in classes,
        )
        if row is None:
            continue
        row_text = _clean(row.get_text(" ", strip=True))
        cutoff = re.search(r"\bScheme\s+Open\s+from\b|\bOpen\s+from\b", row_text, re.IGNORECASE)
        name = row_text[: cutoff.start()] if cutoff else row_text
        name = re.sub(r"\s*\((?:merit|welfare)\s+based\s+scheme\)\s*$", "", name, flags=re.IGNORECASE)
        name = _clean(name)
        if not name or not any(word in name.casefold() for word in SCHOLARSHIP_TERMS):
            continue
        provider = "Not specified"
        ministry = anchor.find_parent(class_="accordion-item")
        if ministry:
            heading = ministry.select_one("button")
            if heading:
                provider = _clean(heading.get_text(" ", strip=True)) or provider
            if provider == "Not specified":
                group_text = _clean(ministry.get_text(" ", strip=True))
                provider_prefix = group_text.split(row_text, maxsplit=1)[0].strip()
                if provider_prefix:
                    provider = provider_prefix
        opening_match = re.search(
            r"Open\s+from(?:\s*\([^)]*\))?\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
            row_text,
            re.IGNORECASE,
        )
        closing_match = re.search(
            r"Student\s+Application\s+Open\s+till(?:\s*\([^)]*\))?\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
            row_text,
            re.IGNORECASE,
        )
        guideline_url = urljoin(page_url, anchor["href"])
        key = (re.sub(r"\W+", "", name.casefold()), guideline_url)
        if key in seen:
            continue
        seen.add(key)
        evidence = {
            "scholarship_name": {"value": name, "text": row_text, "url": page_url},
            "application_url": {
                "value": application_url,
                "text": f"Official NSP listing links to the student scholarship application: {application_url}",
                "url": page_url,
            },
        }
        if opening_match:
            evidence["opening_date"] = {
                "value": opening_match.group(1),
                "text": row_text,
                "url": page_url,
            }
        if closing_match:
            evidence["closing_date"] = {
                "value": closing_match.group(1),
                "text": row_text,
                "url": page_url,
            }
        found.append(
            Candidate(
                scholarship_name=name,
                source_url=page_url,
                provider=provider,
                application_url=application_url,
                source_type="government",
                listing_text=row_text,
                guideline_url=guideline_url,
                evidence=evidence,
            )
        )
    return found


def parse_iitm_scholarships(html: str, page_url: str) -> list[Candidate]:
    """Extract IIT Madras' published scholarship tables as separate, evidence-backed entries."""
    soup = BeautifulSoup(html, "html.parser")
    provider = "Indian Institute of Technology Madras"
    found: list[Candidate] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_cells = rows[0].find_all(["th", "td"], recursive=False) if rows else []
        headers = [_clean(cell.get_text(" ", strip=True)).casefold() for cell in header_cells]
        scholarship_index = next((i for i, value in enumerate(headers) if "scholarship" in value), None)
        eligibility_index = next((i for i, value in enumerate(headers) if "eligibility" in value), None)
        amount_index = next((i for i, value in enumerate(headers) if "amount" in value), None)
        if scholarship_index is None or eligibility_index is None or amount_index is None:
            continue
        for row in rows[1:]:
            cells = row.find_all(["th", "td"], recursive=False)
            if max(scholarship_index, eligibility_index, amount_index) >= len(cells):
                continue
            name = _clean(cells[scholarship_index].get_text(" ", strip=True))
            eligibility = _clean(cells[eligibility_index].get_text(" ", strip=True))
            amount = _clean(cells[amount_index].get_text(" ", strip=True))
            if not name or name.casefold() in {"scholarship", "sl.no scholarship"} or name in seen:
                continue
            seen.add(name)
            row_text = " | ".join((name, eligibility, amount))
            evidence = {
                "scholarship_name": {"value": name, "text": row_text, "url": page_url},
            }
            if eligibility:
                evidence["eligibility"] = {
                    "value": eligibility,
                    "text": eligibility,
                    "url": page_url,
                }
            if amount:
                evidence["amount"] = {"value": amount, "text": amount, "url": page_url}
                evidence["benefit"] = {"value": amount, "text": amount, "url": page_url}
            found.append(
                Candidate(
                    scholarship_name=name,
                    source_url=page_url,
                    provider=provider,
                    source_type="university",
                    listing_text=row_text,
                    evidence=evidence,
                )
            )
    return found


def _text_after_heading(heading: Tag) -> str:
    parts: list[str] = []
    for node in heading.next_elements:
        if isinstance(node, Tag) and node.name in {"h1", "h2", "h3", "h4"}:
            break
        if not isinstance(node, NavigableString) or node.parent is None:
            continue
        if node.parent is heading or heading in node.parent.parents:
            continue
        value = str(node).strip()
        if value:
            parts.append(value)
    return _clean(" ".join(parts))


def parse_tata_education_grants(html: str, page_url: str) -> list[Candidate]:
    """Extract named Tata Trusts education programmes and their published open/closed states."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[Candidate] = []
    for heading in soup.find_all(["h3", "h4"]):
        heading_text = _clean(heading.get_text(" ", strip=True))
        section_text = _text_after_heading(heading)
        title_lower = heading_text.casefold()
        if "jamsetjee nusserwanjee tata endowment" in title_lower and "loan scholarship" in section_text.casefold():
            name = "J N Tata Endowment loan scholarship"
        elif "medical and healthcare scholarship" in title_lower:
            name = heading_text
        elif "means grant" in title_lower and "programme" in section_text.casefold():
            name = "Tata Trusts Means Grant Programme"
        elif "lady meherbai" in title_lower and "scholarship" in title_lower:
            name = heading_text
        else:
            continue

        evidence: dict[str, dict[str, str]] = {
            "scholarship_name": {
                "value": name,
                "text": f"{heading_text}. {section_text}",
                "url": page_url,
            }
        }
        eligibility = _matching_sentence(
            section_text,
            (
                r"\b(?:supports only overseas studies|scheme is open|based on students' needs|merit-based)\b",
                r"\b(?:women graduates|school-going students|college students|masters|postdoctoral)\b",
            ),
        )
        if eligibility:
            evidence["eligibility"] = {
                "value": eligibility,
                "text": eligibility,
                "url": page_url,
            }
        amount_sentence = _matching_sentence(
            section_text,
            (r"\b(?:loan,?\s*a maximum|maximum of)\s*₹", r"₹\s*[\d,.]+\s*(?:lakh|lakhs|crore)?"),
        )
        if amount_sentence:
            amount_match = re.search(r"₹\s*[\d,.]+\s*(?:lakh|lakhs|crore)?", amount_sentence, re.IGNORECASE)
            evidence["amount"] = {
                "value": f"{amount_match.group(0)} maximum loan" if amount_match else amount_sentence,
                "text": amount_sentence,
                "url": page_url,
            }
            evidence["benefit"] = {
                "value": amount_sentence,
                "text": amount_sentence,
                "url": page_url,
            }
        elif "means grant" in title_lower:
            benefit = _matching_sentence(section_text, (r"\bpartial financial assistance\b",))
            if benefit:
                evidence["benefit"] = {
                    "value": benefit,
                    "text": benefit,
                    "url": page_url,
                }

        lowered_text = section_text.casefold()
        if "no longer accepted" in lowered_text:
            source_status = "EXPIRED"
            status_text = _matching_sentence(section_text, (r"\bno longer accepted\b",))
        elif "stands closed for the year" in lowered_text:
            source_status = "EXPIRED"
            status_text = _matching_sentence(section_text, (r"\bstands closed\b",))
        elif "applications are currently being accepted" in lowered_text:
            source_status = "ACTIVE"
            status_text = _matching_sentence(section_text, (r"\bapplications are currently being accepted\b",))
        else:
            source_status = "REVIEW_REQUIRED"
            status_text = ""
        if status_text:
            evidence["current_status"] = {
                "value": source_status,
                "text": status_text,
                "url": page_url,
            }
        if "means grant" in title_lower:
            educational_scope = _matching_sentence(
                section_text,
                (r"\bschool-going students from Standard VIII\b",),
            )
            if educational_scope:
                evidence["education_level"] = {
                    "value": educational_scope,
                    "text": educational_scope,
                    "url": page_url,
                }
        found.append(
            Candidate(
                scholarship_name=name,
                source_url=page_url,
                provider="Tata Trusts",
                source_type="foundation",
                listing_text=f"{heading_text}. {section_text}",
                evidence=evidence,
            )
        )
    return found


def extract_page_candidate(
    html: str,
    page_url: str,
    *,
    title_hint: str = "",
    provider_hint: str = "Not specified",
    application_url: str = NOT_SPECIFIED,
) -> Candidate | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1")
    title = _clean(heading.get_text(" ", strip=True)) if heading else title_hint
    if not title and soup.title:
        title = _clean(soup.title.get_text(" ", strip=True))
    title = re.sub(r"\s*[|–-]\s*(?:official website|home|department.*)$", "", title, flags=re.IGNORECASE)
    text = _clean(soup.get_text(" ", strip=True))
    if not is_specific_scholarship_title(title):
        return None
    candidate = Candidate(
        scholarship_name=title,
        source_url=page_url,
        provider=provider_hint,
        application_url=application_url,
        source_type=classify_source(page_url),
        listing_text=text,
    )
    for field_name, patterns in FIELD_PATTERNS.items():
        snippet = _matching_sentence(text, patterns)
        if snippet:
            candidate.evidence[field_name] = {
                "value": _evidence_value(snippet, field_name),
                "text": snippet,
                "url": page_url,
            }
    for link in soup.select("a[href]"):
        label = _clean(link.get_text(" ", strip=True))
        href = urljoin(page_url, link["href"])
        if re.search(r"\b(apply|application form|apply online|apply now)\b", label, re.IGNORECASE):
            application_url = href
            candidate.application_url = href
            candidate.evidence["application_url"] = {
                "value": href,
                "text": f"Official page link labelled “{label}”: {href}",
                "url": page_url,
            }
            break
    return candidate


def extract_record(
    candidate: Candidate,
    source_segments: list[tuple[str, str]],
    *,
    current_page_checked: bool,
    conflicting_information: bool = False,
) -> tuple[ScholarshipData, list[dict[str, str]], list[dict[str, Any]]]:
    full_text = "\n".join(text for _, text in source_segments)
    field_evidence = dict(candidate.evidence)
    for field_name, patterns in FIELD_PATTERNS.items():
        if field_name in field_evidence:
            continue
        for source_url, text in source_segments:
            snippet = _matching_sentence(text, patterns)
            if snippet:
                field_evidence[field_name] = {
                    "value": _evidence_value(snippet, field_name),
                    "text": snippet,
                    "url": source_url,
                }
                break
    if candidate.application_url != NOT_SPECIFIED:
        field_evidence.setdefault(
            "application_url",
            {
                "value": candidate.application_url,
                "text": f"Official source application link: {candidate.application_url}",
                "url": candidate.source_url,
            },
        )

    values: dict[str, Any] = {
        "scholarship_name": candidate.scholarship_name,
        "provider": candidate.provider,
        "official_source_url": candidate.source_url,
        "application_url": candidate.application_url,
        "source_type": candidate.source_type,
        "current_status": "REVIEW_REQUIRED",
    }
    evidence_rows = []
    for field_name in (
        "amount",
        "benefit",
        "eligibility",
        "academic_requirements",
        "education_level",
        "course_requirements",
        "income_criteria",
        "age_criteria",
        "gender_criteria",
        "category_criteria",
        "domicile_requirements",
        "institution_requirements",
        "opening_date",
        "closing_date",
        "documents_required",
        "selection_process",
        "renewal_requirements",
    ):
        item = field_evidence.get(field_name)
        values[field_name] = item["value"] if item else NOT_SPECIFIED
    explicit_status = field_evidence.get("current_status", {}).get("value")
    values["current_status"] = detect_status(
        values["closing_date"],
        source_verified=True,
        scholarship_present=True,
        application_open=explicit_status == "ACTIVE",
        application_closed=explicit_status == "EXPIRED",
    )

    # Validate before scoring; exact source excerpts are retained independently of the record.
    record = ScholarshipData.model_validate(values)
    serializable = record.model_dump()
    from crawler.scorer import calculate_confidence
    from crawler.verifier import verify_official_source

    evidence_by_field = {key: item["text"] for key, item in field_evidence.items()}
    verification = verify_official_source(
        candidate.source_url,
        full_text,
        candidate.scholarship_name,
        candidate.application_url,
        evidence_by_field,
        current_page_checked=current_page_checked,
        conflicting_information=conflicting_information,
    )
    score, verification_status, breakdown = calculate_confidence(
        {**verification, "schema_consistent": True}
    )
    serializable["confidence_score"] = score
    serializable["verification_status"] = verification_status
    record = ScholarshipData.model_validate(serializable)

    captured_at = datetime.now(timezone.utc).isoformat()
    for field_name, item in field_evidence.items():
        if field_name not in serializable or not item.get("value") or not item.get("text"):
            continue
        evidence_rows.append(
            {
                "field_name": field_name,
                "extracted_value": item["value"],
                "evidence_text": item["text"],
                "source_url": item["url"],
                "captured_at": captured_at,
            }
        )
    return record, evidence_rows, breakdown
