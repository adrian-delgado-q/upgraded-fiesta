from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import PackageStatus, Recommendation


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class NormalizedJob:
    source: str
    company: str
    title_raw: str
    url: str
    canonical_key: str
    description_text: str
    source_job_id: str | None = None
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
    posted_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    description_html: str | None = None
    normalized_facets: dict[str, Any] = field(default_factory=dict)
    profile_signals: dict[str, Any] = field(default_factory=dict)
    extraction_payload: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(default_factory=utc_now)
    last_seen_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class ScoreBreakdown:
    category_scores: dict[str, float] = field(default_factory=dict)
    deterministic_score: float = 0.0
    llm_fit_score: float = 0.0
    llm_risk_penalty: float = 0.0
    final_score: float = 0.0
    recommendation: str = Recommendation.ARCHIVE.value
    hard_rejects: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scoring_explanation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RequirementExtraction:
    job_id: int
    version_id: int
    extractor_version: str
    content_hash: str
    structured_posting: dict[str, Any]
    requirement_signals: dict[str, Any]
    role_profile: dict[str, Any]
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class EvidenceMatch:
    job_id: int
    version_id: int
    match_version: str
    matches: list[dict[str, Any]]
    fit_summary: dict[str, Any]
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class PackageRequestRecord:
    job_id: int
    job_version_id: int
    package_type: str
    requested_by: str
    generation_profile: str
    status: str = PackageStatus.QUEUED.value
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
