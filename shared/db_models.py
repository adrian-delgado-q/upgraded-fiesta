from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column, Engine, event
from sqlmodel import Field, SQLModel

from .enums import JobState, PackageStatus, TriageStatus


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def create_sqlite_engine(database_path: str | Path) -> Engine:
    from sqlmodel import create_engine

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def initialize_database(database_path: str | Path, reset: bool = False) -> Engine:
    path = Path(database_path)
    if reset:
        for candidate in (path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm")):
            candidate.unlink(missing_ok=True)
    engine = create_sqlite_engine(path)
    create_schema(engine)
    return engine


class JobRow(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    source: str
    source_job_id: str | None = None
    canonical_key: str = Field(index=True, unique=True)
    company: str
    title_raw: str
    title_normalized: str | None = None
    role_family: str | None = None
    seniority: str | None = None
    location_raw: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    salary_min_cad: float | None = None
    salary_max_cad: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    url: str
    posted_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=utc_now_dt)
    last_seen_at: datetime = Field(default_factory=utc_now_dt)
    is_active: int = Field(default=1)
    latest_version_id: int | None = Field(default=None, foreign_key="job_versions.id")
    latest_score_id: int | None = Field(default=None, foreign_key="job_scores.id")
    latest_analysis_id: int | None = Field(default=None, foreign_key="job_analyses.id")
    current_state: str = Field(default=JobState.DISCOVERED.value, index=True)
    triage_status: str = Field(default=TriageStatus.NEW.value, index=True)
    deterministic_score: float | None = None
    final_score: float | None = None
    recommendation: str | None = None
    shortlist_reason: str | None = None
    package_requested_at: datetime | None = None
    package_ready_at: datetime | None = None
    location_source: str | None = None
    salary_source: str | None = None
    normalized_facets_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    profile_signals_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    extraction_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    scoring_explanation_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )


class JobVersionRow(SQLModel, table=True):
    __tablename__ = "job_versions"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    content_hash: str
    description_text: str
    description_html: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    fetched_at: datetime = Field(default_factory=utc_now_dt)
    change_type: str


class JobAnalysisRow(SQLModel, table=True):
    __tablename__ = "job_analyses"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    version_id: int = Field(foreign_key="job_versions.id")
    model_name: str
    prompt_version: str
    cache_key: str | None = Field(default=None, index=True)
    cache_source: str | None = None
    analysis_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=utc_now_dt)


class JobScoreRow(SQLModel, table=True):
    __tablename__ = "job_scores"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    version_id: int = Field(foreign_key="job_versions.id")
    title_score: float | None = None
    seniority_score: float | None = None
    location_score: float | None = None
    salary_score: float | None = None
    domain_score: float | None = None
    keyword_score: float | None = None
    negative_score: float | None = None
    deterministic_score: float | None = None
    llm_fit_score: float | None = None
    llm_risk_penalty: float | None = None
    final_score: float | None = None
    recommendation: str | None = None
    explanation_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    scoring_version: str
    created_at: datetime = Field(default_factory=utc_now_dt)


class CandidateEvidenceRow(SQLModel, table=True):
    __tablename__ = "candidate_evidence"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    domain: str | None = None
    role_scope: str | None = None
    tools_json: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    systems_json: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    action_text: str
    outcome_text: str
    scale_text: str | None = None
    confidence: float = 0.5
    source_reference: str | None = None
    reusable_bullet_seed: str
    tags_json: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    is_active: int = Field(default=1)
    updated_at: datetime = Field(default_factory=utc_now_dt)


class RequirementExtractionRow(SQLModel, table=True):
    __tablename__ = "requirement_extractions"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    version_id: int = Field(foreign_key="job_versions.id")
    extractor_version: str
    content_hash: str
    structured_posting_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    requirement_signals_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    role_profile_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=utc_now_dt)


class EvidenceMatchRow(SQLModel, table=True):
    __tablename__ = "evidence_matches"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    version_id: int = Field(foreign_key="job_versions.id")
    match_version: str
    matches_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    fit_summary_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=utc_now_dt)


class PackageRequestRow(SQLModel, table=True):
    __tablename__ = "package_requests"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id")
    job_version_id: int = Field(foreign_key="job_versions.id")
    package_type: str
    status: str = Field(default=PackageStatus.QUEUED.value, index=True)
    requested_by: str
    generation_profile: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now_dt)


class PackageArtifactRow(SQLModel, table=True):
    __tablename__ = "package_artifacts"

    id: int | None = Field(default=None, primary_key=True)
    package_request_id: int = Field(foreign_key="package_requests.id")
    artifact_type: str
    version: int
    markdown_path: str | None = None
    docx_path: str | None = None
    source_payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    preview_text: str | None = None
    status: str
    created_at: datetime = Field(default_factory=utc_now_dt)


class ArtifactReviewRow(SQLModel, table=True):
    __tablename__ = "artifact_reviews"

    id: int | None = Field(default=None, primary_key=True)
    artifact_id: int = Field(foreign_key="package_artifacts.id")
    reviewer: str
    status: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now_dt)


class JobSkillRow(SQLModel, table=True):
    __tablename__ = "job_skills"

    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True)
    version_id: int = Field(foreign_key="job_versions.id", index=True)
    skill_name: str
    skill_type: str
    source: str
    created_at: datetime = Field(default_factory=utc_now_dt)


class JobUpsertResult(SQLModel):
    job_id: int
    version_id: int
    change_type: str


class JobListItem(SQLModel):
    id: int
    source: str
    source_job_id: str | None = None
    canonical_key: str
    company: str
    title_raw: str
    title_normalized: str | None = None
    role_family: str | None = None
    seniority: str | None = None
    location_raw: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    salary_min_cad: float | None = None
    salary_max_cad: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    url: str
    posted_at: datetime | None = None
    discovered_at: datetime
    last_seen_at: datetime
    is_active: int
    latest_version_id: int | None = None
    latest_score_id: int | None = None
    latest_analysis_id: int | None = None
    current_state: str
    triage_status: str
    deterministic_score: float | None = None
    final_score: float | None = None
    recommendation: str | None = None
    shortlist_reason: str | None = None
    package_requested_at: datetime | None = None
    package_ready_at: datetime | None = None
    location_source: str | None = None
    salary_source: str | None = None
    normalized_facets_json: dict[str, Any] = Field(default_factory=dict)
    profile_signals_json: dict[str, Any] = Field(default_factory=dict)
    extraction_json: dict[str, Any] = Field(default_factory=dict)
    scoring_explanation_json: dict[str, Any] = Field(default_factory=dict)
    description_text: str | None = None


class PackageListItem(SQLModel):
    package_id: int
    package_type: str
    package_status: str
    requested_by: str
    generation_profile: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    job_id: int
    job_version_id: int
    company: str
    title_raw: str
    title_normalized: str | None = None
    role_family: str | None = None
    seniority: str | None = None
    location_raw: str | None = None
    work_mode: str | None = None
    source: str
    url: str
    salary_min_cad: float | None = None
    salary_max_cad: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    deterministic_score: float | None = None
    final_score: float | None = None


class PackageDetail(SQLModel):
    id: int
    job_id: int
    job_version_id: int
    package_type: str
    status: str
    requested_by: str
    generation_profile: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    artifacts: list[PackageArtifactRow] = Field(default_factory=list)
