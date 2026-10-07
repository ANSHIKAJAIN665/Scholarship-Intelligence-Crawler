from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from crawler.change_detector import record_changes
from crawler.discovery import (
    SEED_SOURCES,
    TRUSTED_SEED_HOSTS,
    DiscoveryResult,
    RespectfulFetcher,
    discover_candidates,
)
from crawler.extractor import Candidate, extract_pdf_text, extract_record
from crawler.source_classifier import is_official_domain
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
    return " ".join(value.casefold().split())


def _candidate_conflicts(candidates: list[Candidate]) -> set[int]:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for index, candidate in enumerate(candidates):
        deadline = candidate.evidence.get("closing_date", {}).get("value", "")
        grouped.setdefault(_normalized_name(candidate.scholarship_name), []).append((index, deadline))
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
            for item in evidence
        ]
    )


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
            if _normalized_name(item.scholarship_name) == _normalized_name(record.scholarship_name)
            and item.official_source_url == record.official_source_url
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
        if _normalized_name(scholarship.scholarship_name) in seen_names:
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
