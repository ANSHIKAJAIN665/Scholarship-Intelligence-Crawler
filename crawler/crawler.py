from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from crawler.change_detector import record_changes
from crawler.discovery import (
    SEED_SOURCES,
    TRUSTED_SEED_HOSTS,
    DiscoveryResult,
    RespectfulFetcher,
    discover_candidates,
)
from crawler.extractor import (
    CRITICAL_FIELDS,
    Candidate,
    extract_pdf_text,
    extract_record,
    is_specific_scholarship_title,
    is_valid_field_value,
)
from crawler.scorer import calculate_confidence
from crawler.source_classifier import (
    is_official_domain,
    normalized_host,
    normalized_identity,
    same_scholarship_identity,
    scholarship_identity_key,
)
from crawler.status_detector import NOT_SPECIFIED, detect_status, parse_date
from crawler.verifier import verify_official_source
from database.database import SessionLocal, init_db
from database.models import ChangeHistory, CrawlRun, Scholarship, SourceEvidence
from models.scholarship import ScholarshipData, utc_now_iso

_run_lock = threading.Lock()
NSP_INDEX_URL = "https://scholarships.gov.in/All-Scholarships"


def create_crawl_run() -> CrawlRun | None:
    """Reserve the single crawler slot and persist a run before background work starts."""
    if not _run_lock.acquire(blocking=False):
        return None
    run = CrawlRun(
        id=str(uuid.uuid4()),
        started_at=utc_now_iso(),
        completed_at="",
        status="RUNNING",
        message="Crawling configured official seed sources.",
    )
    session = SessionLocal()
    try:
        session.add(run)
        session.commit()
        session.refresh(run)
        return run
    except Exception:
        _run_lock.release()
        raise
    finally:
        session.close()


def _content_hash(record: ScholarshipData) -> str:
    payload = record.model_dump(exclude={"current_status", "confidence_score", "verification_status"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _normalized_name(value: str) -> str:
    return normalized_identity(value)


def _candidate_conflicts(candidates: list[Candidate]) -> set[int]:
    grouped: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for index, candidate in enumerate(candidates):
        deadline = candidate.evidence.get("closing_date", {}).get("value", "")
        parsed_deadline = parse_date(deadline)
        normalized_deadline = parsed_deadline.isoformat() if parsed_deadline else _normalized_name(deadline)
        identity = scholarship_identity_key(
            candidate.provider, candidate.scholarship_name, candidate.source_url
        )
        grouped.setdefault(identity, []).append((index, normalized_deadline))
    conflicted: set[int] = set()
    for items in grouped.values():
        different_deadlines = {deadline for _, deadline in items if deadline}
        if len(different_deadlines) > 1:
            conflicted.update(index for index, _ in items)
    return conflicted


def _fetch_guideline(fetcher: RespectfulFetcher, candidate: Candidate) -> tuple[str, str | None]:
    if not candidate.guideline_url or not is_official_domain(candidate.guideline_url, TRUSTED_SEED_HOSTS):
        return "", None
    try:
        response = fetcher.get(candidate.guideline_url)
        if "pdf" not in response.headers.get("content-type", "").casefold() and not candidate.guideline_url.casefold().endswith(".pdf"):
            return "", None
        text = extract_pdf_text(response.content)
        if not text:
            return "", f"{candidate.guideline_url}: PDF downloaded but no selectable text was extracted"
        return text, None
    except Exception as exc:
        return "", f"{candidate.guideline_url}: {type(exc).__name__}: {str(exc)[:240]}"


def _store_evidence(session: Any, scholarship_id: str, evidence: list[dict[str, str]]) -> None:
    existing = {
        (item.field_name, item.extracted_value, item.evidence_text, item.source_url)
        for item in session.scalars(
            select(SourceEvidence).where(SourceEvidence.scholarship_id == scholarship_id)
        ).all()
    }
    new_items = [
        item for item in evidence
        if (item["field_name"], item["extracted_value"], item["evidence_text"], item["source_url"])
        not in existing
    ]
    session.add_all(
        [
            SourceEvidence(
                id=str(uuid.uuid4()),
                scholarship_id=scholarship_id,
                field_name=item["field_name"],
                extracted_value=item["extracted_value"],
                evidence_text=item["evidence_text"],
                source_url=item["source_url"],
                captured_at=item["captured_at"],
            )
            for item in new_items
        ]
    )
    session.flush()


def _is_specialized_source(record: Scholarship) -> bool:
    host = normalized_host(record.official_source_url)
    path = urlparse(record.official_source_url).path.casefold().rstrip("/")
    return (
        (host == "scholarships.gov.in" and path.endswith("/all-scholarships"))
        or (host.endswith("iitm.ac.in") and "scholarship" in path)
        or (host == "tatatrusts.org" and "/education/education-grants" in path)
    )


def _delete_record_tree(
    session: Any,
    record: Scholarship,
    evidence: list[SourceEvidence],
    history: list[ChangeHistory],
) -> None:
    for item in evidence:
        session.delete(item)
    for item in history:
        session.delete(item)
    session.delete(record)


def _record_priority(
    record: Scholarship,
    evidence_count: int,
    history_count: int,
) -> tuple[int, int, int, int, str]:
    path = urlparse(record.official_source_url).path.casefold()
    locale_penalty = int(bool(re.search(r"^/(?:en|hi|ta|te|bn|mr|gu|kn|ml|pa)/", path)))
    fragment_or_query_penalty = int(bool(urlparse(record.official_source_url).query))
    return (
        -evidence_count,
        -history_count,
        locale_penalty,
        fragment_or_query_penalty + len(path),
        record.created_at,
    )


def cleanup_existing_records(
    session: Any,
    *,
    checked_source_urls: set[str],
    fresh_since: str,
    candidate_conflicts: set[tuple[str, str]] | None = None,
) -> tuple[int, int]:
    """Remove non-opportunity rows, sanitize unsupported values, and merge duplicate identities."""
    records = list(session.scalars(select(Scholarship)).all())
    evidence_by_record: dict[str, list[SourceEvidence]] = defaultdict(list)
    history_by_record: dict[str, list[ChangeHistory]] = defaultdict(list)
    for item in session.scalars(select(SourceEvidence)).all():
        evidence_by_record[item.scholarship_id].append(item)
    for item in session.scalars(select(ChangeHistory)).all():
        history_by_record[item.scholarship_id].append(item)

    removed_records = 0
    invalid_fields_by_record: dict[str, set[str]] = defaultdict(set)
    valid_records: list[Scholarship] = []
    for record in records:
        record_evidence = evidence_by_record[record.id]
        record_history = history_by_record[record.id]
        retained_evidence: list[SourceEvidence] = []
        valid_field_names: set[str] = set()
        for item in record_evidence:
            if item.field_name in CRITICAL_FIELDS:
                if not is_valid_field_value(item.field_name, item.extracted_value, item.evidence_text):
                    invalid_fields_by_record[record.id].add(item.field_name)
                    session.delete(item)
                    continue
                valid_field_names.add(item.field_name)
            retained_evidence.append(item)
        evidence_by_record[record.id] = retained_evidence

        for field_name in CRITICAL_FIELDS:
            value = getattr(record, field_name, NOT_SPECIFIED)
            if value == NOT_SPECIFIED:
                continue
            supporting = [
                item for item in retained_evidence
                if item.field_name == field_name
                and is_valid_field_value(field_name, item.extracted_value, item.evidence_text)
            ]
            if not is_valid_field_value(field_name, value, " ".join(item.evidence_text for item in supporting)):
                setattr(record, field_name, NOT_SPECIFIED)
                invalid_fields_by_record[record.id].add(field_name)
            elif not supporting:
                setattr(record, field_name, NOT_SPECIFIED)
                invalid_fields_by_record[record.id].add(field_name)

        has_supported_opportunity_fact = any(
            item.field_name in {"eligibility", "benefit", "amount"}
            and is_valid_field_value(item.field_name, item.extracted_value, item.evidence_text)
            for item in retained_evidence
        )
        is_supported_record = (
            is_specific_scholarship_title(record.scholarship_name)
            and is_official_domain(record.official_source_url)
            and (_is_specialized_source(record) or has_supported_opportunity_fact)
        )
        if not is_supported_record:
            _delete_record_tree(session, record, retained_evidence, record_history)
            removed_records += 1
            continue
        valid_records.append(record)

    session.flush()
    valid_records.sort(
        key=lambda item: _record_priority(
            item,
            len(evidence_by_record[item.id]),
            len(history_by_record[item.id]),
        )
    )
    kept: list[Scholarship] = []
    merged_records = 0
    conflicting_ids: set[str] = set()
    conflict_keys = candidate_conflicts or set()
    for record in valid_records:
        primary = next(
            (
                item for item in kept
                if same_scholarship_identity(
                    item.provider,
                    item.scholarship_name,
                    item.official_source_url,
                    record.provider,
                    record.scholarship_name,
                    record.official_source_url,
                )
            ),
            None,
        )
        if primary is None:
            kept.append(record)
            continue

        left_deadline = parse_date(primary.closing_date)
        right_deadline = parse_date(record.closing_date)
        if left_deadline and right_deadline and left_deadline != right_deadline:
            conflicting_ids.add(primary.id)
        for field_name in ScholarshipData.model_fields:
            if field_name in {"scholarship_name", "official_source_url"}:
                continue
            current_value = getattr(primary, field_name, None)
            other_value = getattr(record, field_name, None)
            if current_value == NOT_SPECIFIED and other_value not in (None, NOT_SPECIFIED):
                if field_name not in CRITICAL_FIELDS or any(
                    item.field_name == field_name
                    and is_valid_field_value(field_name, item.extracted_value, item.evidence_text)
                    for item in evidence_by_record[record.id]
                ):
                    setattr(primary, field_name, other_value)

        for item in evidence_by_record[record.id]:
            item.scholarship = primary
            evidence_by_record[primary.id].append(item)
        for item in history_by_record[record.id]:
            item.scholarship = primary
            history_by_record[primary.id].append(item)
        invalid_fields_by_record[primary.id].update(invalid_fields_by_record[record.id])
        primary.last_verified = max(primary.last_verified, record.last_verified)
        primary.updated_at = max(primary.updated_at, record.updated_at)
        session.delete(record)
        merged_records += 1

    session.flush()
    remaining = list(session.scalars(select(Scholarship)).all())
    fresh_since_dt = datetime.fromisoformat(fresh_since)
    for record in remaining:
        items = sorted(
            evidence_by_record[record.id],
            key=lambda item: item.captured_at,
            reverse=True,
        )
        field_texts: dict[str, str] = {}
        full_text_parts: list[str] = []
        fresh_page_checked = False
        valid_fields: set[str] = set()
        for item in items:
            full_text_parts.append(item.evidence_text)
            if item.field_name in CRITICAL_FIELDS and is_valid_field_value(
                item.field_name, item.extracted_value, item.evidence_text
            ):
                field_texts.setdefault(item.field_name, item.evidence_text)
                valid_fields.add(item.field_name)
            if item.source_url in checked_source_urls:
                try:
                    captured = datetime.fromisoformat(item.captured_at)
                    fresh_page_checked = fresh_page_checked or captured >= fresh_since_dt
                except ValueError:
                    pass

        evidence_quality_valid = not (
            invalid_fields_by_record[record.id] - valid_fields
        ) and any(field in valid_fields for field in ("eligibility", "benefit", "amount"))
        specific_opportunity = is_specific_scholarship_title(record.scholarship_name)
        official = is_official_domain(record.official_source_url)
        verification = verify_official_source(
            record.official_source_url,
            "\n".join(full_text_parts),
            record.scholarship_name,
            record.application_url,
            field_texts,
            current_page_checked=fresh_page_checked,
            conflicting_information=record.id in conflicting_ids
            or scholarship_identity_key(record.provider, record.scholarship_name, record.official_source_url) in conflict_keys,
        )
        verification["critical_evidence_valid"] = evidence_quality_valid
        verification["specific_opportunity"] = specific_opportunity
        score, status, breakdown = calculate_confidence(
            {**verification, "schema_consistent": evidence_quality_valid}
        )
        record.confidence_score = score
        record.verification_status = status
        record.score_breakdown_json = json.dumps(breakdown, ensure_ascii=False)
        explicit_status = next(
            (
                item.extracted_value
                for item in items
                if item.field_name == "current_status"
                and item.extracted_value in {"ACTIVE", "EXPIRED"}
            ),
            None,
        )
        if fresh_page_checked:
            record.current_status = detect_status(
                record.closing_date,
                source_verified=official,
                scholarship_present=specific_opportunity,
                application_open=explicit_status == "ACTIVE",
                application_closed=explicit_status == "EXPIRED",
            )
        elif record.current_status != "NO_LONGER_VERIFIABLE":
            record.current_status = detect_status(
                record.closing_date,
                source_verified=False,
                scholarship_present=specific_opportunity,
            )

    return removed_records, merged_records


def _persist_candidate(
    session: Any,
    candidate: Candidate,
    candidate_index: int,
    conflicting: bool,
    source_segments: list[tuple[str, str]],
    current_page_checked: bool,
) -> tuple[bool, bool, int]:
    record, evidence, score_breakdown = extract_record(
        candidate,
        source_segments,
        current_page_checked=current_page_checked,
        conflicting_information=conflicting,
    )
    values = record.model_dump()
    values["last_verified"] = utc_now_iso()
    score_breakdown_json = json.dumps(score_breakdown, ensure_ascii=False)
    content_hash = _content_hash(record)
    existing = next(
        (
            item
            for item in session.scalars(select(Scholarship)).all()
            if same_scholarship_identity(
                item.provider,
                item.scholarship_name,
                item.official_source_url,
                record.provider,
                record.scholarship_name,
                record.official_source_url,
            )
        ),
        None,
    )
    if existing is None:
        now = utc_now_iso()
        scholarship = Scholarship(
            id=str(uuid.uuid4()),
            **values,
            score_breakdown_json=score_breakdown_json,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )
        session.add(scholarship)
        session.flush()
        _store_evidence(session, scholarship.id, evidence)
        return True, False, 0

    # Keep a stable primary source and do not erase a supported value just because
    # a second official page does not repeat that field.
    values["scholarship_name"] = existing.scholarship_name
    values["official_source_url"] = existing.official_source_url
    if values["provider"] == NOT_SPECIFIED:
        values["provider"] = existing.provider
    for field_name, value in tuple(values.items()):
        if value == NOT_SPECIFIED and getattr(existing, field_name, NOT_SPECIFIED) != NOT_SPECIFIED:
            values[field_name] = getattr(existing, field_name)

    hash_values = {
        field_name: value
        for field_name, value in values.items()
        if field_name in ScholarshipData.model_fields
    }
    content_hash = _content_hash(ScholarshipData.model_validate(hash_values))
    changed_fields = record_changes(session, existing, values, evidence, candidate.source_url)
    values_changed = any(
        getattr(existing, field_name) != value for field_name, value in values.items() if field_name in ScholarshipData.model_fields
    )
    for field_name, value in values.items():
        setattr(existing, field_name, value)
    existing.score_breakdown_json = score_breakdown_json
    existing.last_verified = values["last_verified"]
    if values_changed:
        existing.updated_at = utc_now_iso()
    existing.content_hash = content_hash
    _store_evidence(session, existing.id, evidence)
    return False, bool(changed_fields), len(changed_fields)


def _mark_unlisted_nsp_records(session: Any, discovery: DiscoveryResult, seen_names: set[str]) -> int:
    if NSP_INDEX_URL not in discovery.checked_indexes:
        return 0
    changed = 0
    for scholarship in session.scalars(select(Scholarship).where(Scholarship.official_source_url == NSP_INDEX_URL)).all():
        if _normalized_name(scholarship.scholarship_name) in seen_names or any(
            same_scholarship_identity(
                scholarship.provider,
                scholarship.scholarship_name,
                scholarship.official_source_url,
                candidate.provider,
                candidate.scholarship_name,
                candidate.source_url,
            )
            for candidate in discovery.candidates
        ):
            continue
        if scholarship.current_status == "NO_LONGER_VERIFIABLE":
            continue
        old_status = scholarship.current_status
        scholarship.current_status = "NO_LONGER_VERIFIABLE"
        scholarship.verification_status = "REVIEW_REQUIRED"
        scholarship.updated_at = utc_now_iso()
        session.add(
            ChangeHistory(
                id=str(uuid.uuid4()),
                scholarship_id=scholarship.id,
                field_changed="current_status",
                old_value=old_status,
                new_value="NO_LONGER_VERIFIABLE",
                date_detected=utc_now_iso(),
                source_url=NSP_INDEX_URL,
                evidence="The successfully fetched current official NSP index no longer lists this scholarship. The historical record was retained.",
                is_demo=False,
            )
        )
        changed += 1
    return changed


def execute_crawl_run(run_id: str, discovery: DiscoveryResult | None = None) -> CrawlRun:
    """Execute one live discovery → extraction → verification → score → store → update pass."""
    init_db()
    fetcher = RespectfulFetcher()
    session = SessionLocal()
    try:
        run = session.get(CrawlRun, run_id)
        if run is None:
            raise ValueError(f"Unknown crawl run: {run_id}")
        try:
            discovery = discovery or discover_candidates(fetcher)
            run.discovered_count = len(discovery.candidates)
            run.failed_count = discovery.failed_count
            run.message = "; ".join(discovery.errors[:4]) if discovery.errors else "Official source checks completed."
            conflicted = _candidate_conflicts(discovery.candidates)
            candidate_conflict_keys = {
                scholarship_identity_key(
                    discovery.candidates[index].provider,
                    discovery.candidates[index].scholarship_name,
                    discovery.candidates[index].source_url,
                )
                for index in conflicted
            }
            seen_names: set[str] = set()
            pdf_cache: dict[str, tuple[str, str | None]] = {}
            for index, candidate in enumerate(discovery.candidates):
                segments: list[tuple[str, str]] = []
                if candidate.listing_text:
                    segments.append((candidate.source_url, candidate.listing_text))
                if candidate.guideline_url:
                    if candidate.guideline_url not in pdf_cache:
                        pdf_cache[candidate.guideline_url] = _fetch_guideline(fetcher, candidate)
                    pdf_text, error = pdf_cache[candidate.guideline_url]
                    if error:
                        run.failed_count += 1
                        if not run.message or run.message == "Official source checks completed.":
                            run.message = error
                    if pdf_text:
                        segments.append((candidate.guideline_url, pdf_text))
                if not segments:
                    run.failed_count += 1
                    continue
                official = is_official_domain(candidate.source_url, TRUSTED_SEED_HOSTS)
                if not official:
                    run.failed_count += 1
                    continue
                try:
                    created, updated, changed_count = _persist_candidate(
                        session,
                        candidate,
                        index,
                        index in conflicted,
                        segments,
                        candidate.source_url in discovery.checked_indexes,
                    )
                    run.new_count += int(created)
                    run.updated_count += int(updated)
                    run.changed_count += changed_count
                    if not created:
                        seen_names.add(_normalized_name(candidate.scholarship_name))
                    else:
                        seen_names.add(_normalized_name(candidate.scholarship_name))
                    record = next(
                        item
                        for item in session.scalars(select(Scholarship)).all()
                        if _normalized_name(item.scholarship_name) == _normalized_name(candidate.scholarship_name)
                        and item.official_source_url == candidate.source_url
                    )
                    if record.current_status == "EXPIRED":
                        run.expired_count += 1
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    run = session.get(CrawlRun, run_id)
                    if run is None:
                        raise ValueError(f"Crawl run disappeared during processing: {run_id}")
                    run.failed_count += 1
                    run.message = f"{run.message} Record error: {type(exc).__name__}: {str(exc)[:180]}"
            run.changed_count += _mark_unlisted_nsp_records(session, discovery, seen_names)
            checked_source_urls = set(discovery.checked_indexes)
            checked_source_urls.update(candidate.source_url for candidate in discovery.candidates)
            removed_records, merged_records = cleanup_existing_records(
                session,
                checked_source_urls=checked_source_urls,
                fresh_since=run.started_at,
                candidate_conflicts=candidate_conflict_keys,
            )
            if removed_records or merged_records:
                run.message = (
                    f"{run.message} Data cleanup: removed {removed_records} non-opportunities; "
                    f"merged {merged_records} duplicate records."
                ).strip()
            run.status = "COMPLETED_WITH_ERRORS" if run.failed_count else "COMPLETED"
        except Exception as exc:
            run.status = "FAILED"
            run.message = f"{type(exc).__name__}: {str(exc)[:500]}"
            raise
        finally:
            run.completed_at = utc_now_iso()
            session.commit()
            session.refresh(run)
        return run
    finally:
        session.close()
        if _run_lock.locked():
            _run_lock.release()


def execute_new_crawl() -> CrawlRun:
    run = create_crawl_run()
    if run is None:
        raise RuntimeError("A crawler run is already in progress")
    return execute_crawl_run(run.id)


def crawler_is_running() -> bool:
    return _run_lock.locked()
