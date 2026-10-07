from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from sqlalchemy import func, select

from crawler.crawler import create_crawl_run, execute_crawl_run
from database.database import SessionLocal, init_db
from database.models import ChangeHistory, CrawlRun, Scholarship, SourceEvidence
from models.scholarship import (
    ChangeResponse,
    CrawlRunResponse,
    DashboardSummaryResponse,
    EvidenceResponse,
    ScholarshipDetailResponse,
    ScholarshipResponse,
    ScoreItemResponse,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Scholarship Intelligence API",
    description="Live official-source discovery and evidence-backed scholarship records.",
    version="1.0.0",
    lifespan=lifespan,
)


def _run_response(run: CrawlRun) -> CrawlRunResponse:
    return CrawlRunResponse.model_validate(run)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/scholarships", response_model=list[ScholarshipResponse])
def list_scholarships(
    q: str | None = None,
    source_type: Annotated[str | None, Query(alias="sourceType")] = None,
    status: str | None = None,
    verification_status: Annotated[str | None, Query(alias="verificationStatus")] = None,
    education_level: Annotated[str | None, Query(alias="educationLevel")] = None,
    category: str | None = None,
    domicile: str | None = None,
    min_confidence: Annotated[int | None, Query(alias="minConfidence", ge=0, le=100)] = None,
    max_confidence: Annotated[int | None, Query(alias="maxConfidence", ge=0, le=100)] = None,
) -> list[Scholarship]:
    with SessionLocal() as session:
        statement = select(Scholarship).order_by(Scholarship.updated_at.desc())
        if q:
            like = f"%{q.strip()}%"
            statement = statement.where(
                Scholarship.scholarship_name.ilike(like)
                | Scholarship.provider.ilike(like)
                | Scholarship.eligibility.ilike(like)
            )
        if source_type:
            statement = statement.where(Scholarship.source_type == source_type)
        if status:
            statement = statement.where(Scholarship.current_status == status)
        if verification_status:
            statement = statement.where(Scholarship.verification_status == verification_status)
        if education_level:
            statement = statement.where(Scholarship.education_level.ilike(f"%{education_level}%"))
        if category:
            statement = statement.where(Scholarship.category_criteria.ilike(f"%{category}%"))
        if domicile:
            statement = statement.where(Scholarship.domicile_requirements.ilike(f"%{domicile}%"))
        if min_confidence is not None:
            statement = statement.where(Scholarship.confidence_score >= min_confidence)
        if max_confidence is not None:
            statement = statement.where(Scholarship.confidence_score <= max_confidence)
        return list(session.scalars(statement).all())


@app.get("/scholarships/{scholarship_id}", response_model=ScholarshipDetailResponse)
def get_scholarship(scholarship_id: str) -> dict:
    with SessionLocal() as session:
        scholarship = session.get(Scholarship, scholarship_id)
        if scholarship is None:
            raise HTTPException(status_code=404, detail="Scholarship not found")
        evidence = session.scalars(
            select(SourceEvidence)
            .where(SourceEvidence.scholarship_id == scholarship_id)
            .order_by(SourceEvidence.captured_at.desc())
        ).all()
        changes = session.scalars(
            select(ChangeHistory)
            .where(ChangeHistory.scholarship_id == scholarship_id)
            .order_by(ChangeHistory.date_detected.desc())
        ).all()
        result = ScholarshipResponse.model_validate(scholarship).model_dump()
        result.update(
            evidence=[EvidenceResponse.model_validate(item).model_dump() for item in evidence],
            change_history=[ChangeResponse.model_validate(item).model_dump() for item in changes],
            score_breakdown=[
                ScoreItemResponse.model_validate(item).model_dump()
                for item in json.loads(scholarship.score_breakdown_json or "[]")
            ],
        )
        return result


@app.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary() -> DashboardSummaryResponse:
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(Scholarship)) or 0
        verified = session.scalar(
            select(func.count()).select_from(Scholarship).where(Scholarship.verification_status == "VERIFIED")
        ) or 0
        review = session.scalar(
            select(func.count()).select_from(Scholarship).where(Scholarship.verification_status == "REVIEW_REQUIRED")
        ) or 0
        active = session.scalar(
            select(func.count()).select_from(Scholarship).where(Scholarship.current_status == "ACTIVE")
        ) or 0
        expired = session.scalar(
            select(func.count()).select_from(Scholarship).where(Scholarship.current_status == "EXPIRED")
        ) or 0
        updated = session.scalar(
            select(func.count()).select_from(Scholarship).where(
                Scholarship.updated_at
                >= (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            )
        ) or 0
        average = session.scalar(select(func.avg(Scholarship.confidence_score))) or 0
        latest = session.scalar(select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(1))
        return DashboardSummaryResponse(
            total_discovered=total,
            verified=verified,
            review_required=review,
            active=active,
            expired=expired,
            recently_updated=updated,
            average_confidence=round(float(average), 1),
            latest_run=_run_response(latest) if latest else None,
        )


@app.get("/crawl-runs", response_model=list[CrawlRunResponse])
def list_crawl_runs(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[CrawlRun]:
    with SessionLocal() as session:
        return list(session.scalars(select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(limit)).all())


@app.post("/crawler/run", response_model=CrawlRunResponse, status_code=202)
def run_crawler(background_tasks: BackgroundTasks) -> CrawlRunResponse:
    run = create_crawl_run()
    if run is None:
        raise HTTPException(status_code=409, detail="A crawler run is already in progress")
    background_tasks.add_task(execute_crawl_run, run.id)
    return _run_response(run)
