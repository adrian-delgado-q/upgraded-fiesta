"""Persistence and storage helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, inspect, text
from sqlmodel import Session, delete, select

from .db_models import (
    JobAnalysisRow,
    JobListItem,
    JobRow,
    JobScoreRow,
    JobSkillRow,
    JobUpsertResult,
    JobVersionRow,
    PackageListItem,
    PackageRequestRow,
    create_schema,
    create_sqlite_engine,
    initialize_database,
    utc_now_dt,
)
from .enums import JobState, PackageStatus, TriageStatus
from .models import NormalizedJob, PackageRequestRecord, ScoreBreakdown


def _optional_float(value: Any) -> float | None:
    return float(value) if value not in (None, "") else None


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def apply_extraction_payload_to_job(job: Any, extraction_payload: dict[str, Any]) -> Any:
    location = extraction_payload.get("location_interpretation")
    location = location if isinstance(location, dict) else {}
    compensation = extraction_payload.get("compensation")
    compensation = compensation if isinstance(compensation, dict) else {}

    title_normalized = str(extraction_payload.get("normalized_title") or "").strip()
    if title_normalized:
        job.title_normalized = title_normalized
    role_family = str(extraction_payload.get("role_family") or "").strip()
    if role_family:
        job.role_family = role_family
    seniority = str(extraction_payload.get("seniority") or "").strip()
    if seniority:
        job.seniority = seniority
    work_mode = str(extraction_payload.get("work_mode") or "").strip()
    if work_mode:
        job.work_mode = work_mode

    city = str(location.get("city") or "").strip() or None
    region = str(location.get("region") or "").strip() or None
    country = str(location.get("country") or "").strip() or None
    if any((city, region, country)):
        job.location_city = city
        job.location_region = region
        job.location_country = country

    salary_is_explicit = bool(compensation.get("salary_is_explicit"))
    if salary_is_explicit:
        job.salary_min_cad = _optional_float(compensation.get("salary_min"))
        job.salary_max_cad = _optional_float(compensation.get("salary_max"))
        job.salary_currency = str(compensation.get("salary_currency") or "").strip().upper() or None
        job.salary_period = str(compensation.get("salary_period") or "").strip().lower() or None

    return job


class Repository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_sqlite_engine(self.database_path)
        self.ensure_schema()

    def init_db(self) -> None:
        self.engine = initialize_database(self.database_path, reset=True)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        create_schema(self.engine)
        self._ensure_jobs_payload_columns()

    def _ensure_jobs_payload_columns(self) -> None:
        required = {
            "normalized_facets_json": "JSON NOT NULL DEFAULT '{}'",
            "profile_signals_json": "JSON NOT NULL DEFAULT '{}'",
            "extraction_json": "JSON NOT NULL DEFAULT '{}'",
            "scoring_explanation_json": "JSON NOT NULL DEFAULT '{}'",
        }
        inspector = inspect(self.engine)
        existing = {column["name"] for column in inspector.get_columns("jobs")}
        missing = {name: ddl for name, ddl in required.items() if name not in existing}
        if not missing:
            return
        with self.engine.begin() as connection:
            for name, ddl in missing.items():
                connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))

    def _build_job_row(self, job: NormalizedJob) -> JobRow:
        return JobRow(
            source=job.source,
            source_job_id=job.source_job_id,
            canonical_key=job.canonical_key,
            company=job.company,
            title_raw=job.title_raw,
            title_normalized=job.title_normalized,
            role_family=job.role_family,
            seniority=job.seniority,
            location_raw=job.location_raw,
            location_city=job.location_city,
            location_region=job.location_region,
            location_country=job.location_country,
            work_mode=job.work_mode,
            employment_type=job.employment_type,
            salary_min_cad=job.salary_min_cad,
            salary_max_cad=job.salary_max_cad,
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            url=job.url,
            posted_at=_parse_datetime(job.posted_at),
            discovered_at=_parse_datetime(job.discovered_at) or utc_now_dt(),
            last_seen_at=_parse_datetime(job.last_seen_at) or utc_now_dt(),
            current_state=JobState.DISCOVERED.value,
            triage_status=TriageStatus.NEW.value,
            location_source="scraper",
            salary_source="scraper",
            normalized_facets_json=job.normalized_facets,
            profile_signals_json=job.profile_signals,
            extraction_json=job.extraction_payload,
            scoring_explanation_json={},
        )

    def _update_existing_job(
        self,
        session: Session,
        existing: JobRow,
        job: NormalizedJob,
        content_hash: str,
        now: datetime,
    ) -> JobUpsertResult:
        latest_version = session.exec(
            select(JobVersionRow)
            .where(JobVersionRow.job_id == existing.id)
            .order_by(desc(JobVersionRow.id))
            .limit(1)
        ).first()

        if latest_version and latest_version.content_hash == content_hash:
            existing.last_seen_at = now
            existing.is_active = 1
            existing.current_state = JobState.DEDUPED.value
            existing.triage_status = existing.triage_status or TriageStatus.NEW.value
            session.add(existing)
            session.commit()
            return JobUpsertResult(
                job_id=int(existing.id),
                version_id=int(latest_version.id),
                change_type="unchanged",
            )

        existing.company = job.company
        existing.title_raw = job.title_raw
        existing.title_normalized = job.title_normalized
        existing.role_family = job.role_family
        existing.seniority = job.seniority
        existing.location_raw = job.location_raw
        existing.location_city = job.location_city
        existing.location_region = job.location_region
        existing.location_country = job.location_country
        existing.work_mode = job.work_mode
        existing.employment_type = job.employment_type
        existing.salary_min_cad = job.salary_min_cad
        existing.salary_max_cad = job.salary_max_cad
        existing.salary_currency = job.salary_currency
        existing.salary_period = job.salary_period
        existing.url = job.url
        existing.posted_at = _parse_datetime(job.posted_at)
        existing.last_seen_at = now
        existing.current_state = JobState.UPDATED.value
        existing.location_source = "scraper"
        existing.salary_source = "scraper"
        existing.normalized_facets_json = job.normalized_facets
        existing.profile_signals_json = job.profile_signals
        existing.extraction_json = job.extraction_payload
        session.add(existing)
        session.flush()

        version = JobVersionRow(
            job_id=int(existing.id),
            content_hash=content_hash,
            description_text=job.description_text,
            description_html=job.description_html,
            metadata_json=job.metadata,
            fetched_at=now,
            change_type="updated_major",
        )
        session.add(version)
        session.flush()
        existing.latest_version_id = int(version.id)
        session.add(existing)
        session.commit()
        return JobUpsertResult(
            job_id=int(existing.id),
            version_id=int(version.id),
            change_type="updated_major",
        )

    def _insert_new_job(self, session: Session, job: NormalizedJob, content_hash: str, now: datetime) -> JobUpsertResult:
        job_row = self._build_job_row(job)
        session.add(job_row)
        session.flush()

        version = JobVersionRow(
            job_id=int(job_row.id),
            content_hash=content_hash,
            description_text=job.description_text,
            description_html=job.description_html,
            metadata_json=job.metadata,
            fetched_at=now,
            change_type="new",
        )
        session.add(version)
        session.flush()
        job_row.latest_version_id = int(version.id)
        session.add(job_row)
        session.commit()
        return JobUpsertResult(job_id=int(job_row.id), version_id=int(version.id), change_type="new")

    def upsert_job(self, job: NormalizedJob, content_hash: str) -> JobUpsertResult:
        now = utc_now_dt()
        with Session(self.engine) as session:
            existing = session.exec(select(JobRow).where(JobRow.canonical_key == job.canonical_key)).first()
            if existing:
                return self._update_existing_job(session, existing, job, content_hash, now)
            return self._insert_new_job(session, job, content_hash, now)

    def save_job_payloads(
        self,
        job_id: int,
        normalized_facets: dict[str, Any],
        profile_signals: dict[str, Any],
        extraction_payload: dict[str, Any],
        scoring_explanation: dict[str, Any] | None = None,
    ) -> None:
        with Session(self.engine) as session:
            job = session.get(JobRow, job_id)
            if not job:
                return
            job.normalized_facets_json = normalized_facets
            job.profile_signals_json = profile_signals
            job.extraction_json = extraction_payload
            if scoring_explanation is not None:
                job.scoring_explanation_json = scoring_explanation
            job.current_state = JobState.EXTRACTED.value
            session.add(job)
            session.commit()

    def apply_extraction_updates(self, job_id: int, extraction_payload: dict[str, Any]) -> None:
        with Session(self.engine) as session:
            job = session.get(JobRow, job_id)
            if not job:
                return
            had_location_update = any(
                str((extraction_payload.get("location_interpretation") or {}).get(field) or "").strip()
                for field in ("city", "region", "country")
            )
            had_salary_update = bool(
                isinstance(extraction_payload.get("compensation"), dict)
                and extraction_payload["compensation"].get("salary_is_explicit")
            )
            apply_extraction_payload_to_job(job, extraction_payload)
            if had_location_update:
                job.location_source = "llm"
            if had_salary_update:
                job.salary_source = "llm"
            session.add(job)
            session.commit()

    def save_score(self, job_id: int, version_id: int, breakdown: ScoreBreakdown, scoring_version: str) -> int:
        category_scores = breakdown.category_scores
        score = JobScoreRow(
            job_id=job_id,
            version_id=version_id,
            title_score=category_scores.get("title"),
            seniority_score=category_scores.get("seniority"),
            location_score=category_scores.get("location"),
            salary_score=category_scores.get("salary"),
            domain_score=category_scores.get("domain"),
            keyword_score=category_scores.get("keyword"),
            negative_score=category_scores.get("negative"),
            deterministic_score=breakdown.deterministic_score,
            llm_fit_score=breakdown.llm_fit_score,
            llm_risk_penalty=breakdown.llm_risk_penalty,
            final_score=breakdown.final_score,
            recommendation=breakdown.recommendation,
            explanation_json=breakdown.scoring_explanation,
            scoring_version=scoring_version,
        )
        with Session(self.engine) as session:
            session.add(score)
            session.flush()
            job = session.get(JobRow, job_id)
            if job:
                job.deterministic_score = breakdown.deterministic_score
                job.final_score = breakdown.final_score
                job.recommendation = breakdown.recommendation
                job.latest_score_id = int(score.id)
                job.current_state = JobState.SCORED.value
                job.scoring_explanation_json = breakdown.scoring_explanation
                session.add(job)
            session.commit()
            return int(score.id)

    def save_analysis(self, job_id: int, version_id: int, model_name: str, prompt_version: str, analysis_json: dict[str, Any]) -> int:
        with Session(self.engine) as session:
            analysis = JobAnalysisRow(
                job_id=job_id,
                version_id=version_id,
                model_name=model_name,
                prompt_version=prompt_version,
                analysis_json=analysis_json,
            )
            session.add(analysis)
            session.flush()
            job = session.get(JobRow, job_id)
            if job:
                job.latest_analysis_id = int(analysis.id)
                job.current_state = JobState.ANALYZED.value
                session.add(job)
            session.commit()
            return int(analysis.id)

    def replace_job_skills(self, job_id: int, version_id: int, skills: dict[str, Any], source: str) -> None:
        rows: list[JobSkillRow] = []
        seen: set[tuple[str, str]] = set()
        now = utc_now_dt()
        for skill_type, items in skills.items():
            if not isinstance(items, list):
                continue
            for item in items:
                skill_name = str(item or "").strip()
                normalized = skill_name.lower()
                key = (skill_type, normalized)
                if not skill_name or key in seen:
                    continue
                seen.add(key)
                rows.append(
                    JobSkillRow(
                        job_id=job_id,
                        version_id=version_id,
                        skill_name=skill_name,
                        skill_type=skill_type,
                        source=source,
                        created_at=now,
                    )
                )
        with Session(self.engine) as session:
            session.exec(delete(JobSkillRow).where(JobSkillRow.job_id == job_id, JobSkillRow.version_id == version_id))
            session.add_all(rows)
            session.commit()

    def set_triage_status(self, job_id: int, triage_status: str, shortlist_reason: str | None = None) -> None:
        with Session(self.engine) as session:
            job = session.get(JobRow, job_id)
            if not job:
                return
            job.triage_status = triage_status
            job.shortlist_reason = shortlist_reason
            job.is_active = int(triage_status != TriageStatus.REJECTED.value)
            if triage_status == TriageStatus.REJECTED.value:
                job.current_state = JobState.FILTERED_OUT.value
            if triage_status == TriageStatus.SHORTLISTED.value:
                job.current_state = JobState.SHORTLISTED.value
            session.add(job)
            session.commit()

    def queue_package_request(self, record: PackageRequestRecord) -> int | None:
        now = utc_now_dt()
        with Session(self.engine) as session:
            job = session.get(JobRow, record.job_id)
            if not job:
                return None
            existing = session.exec(
                select(PackageRequestRow)
                .where(PackageRequestRow.job_id == record.job_id)
                .where(PackageRequestRow.status.in_((PackageStatus.QUEUED.value, PackageStatus.READY_FOR_REVIEW.value)))
                .order_by(desc(PackageRequestRow.id))
                .limit(1)
            ).first()
            if existing:
                job.triage_status = TriageStatus.QUEUED_FOR_PACKAGE.value
                job.package_requested_at = existing.created_at
                session.add(job)
                session.commit()
                return int(existing.id)

            package_request = PackageRequestRow(
                job_id=record.job_id,
                job_version_id=record.job_version_id,
                package_type=record.package_type,
                status=record.status,
                requested_by=record.requested_by,
                generation_profile=record.generation_profile,
                error_message=record.error_message,
                started_at=_parse_datetime(record.started_at),
                completed_at=_parse_datetime(record.completed_at),
                created_at=now,
            )
            session.add(package_request)
            session.flush()
            job.triage_status = TriageStatus.QUEUED_FOR_PACKAGE.value
            job.package_requested_at = now
            session.add(job)
            session.commit()
            return int(package_request.id)

    def list_jobs(self, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[JobListItem]:
        filters = filters or {}
        statement = select(JobRow, JobVersionRow.description_text).outerjoin(JobVersionRow, JobVersionRow.id == JobRow.latest_version_id)
        requested_triage_status = filters.get("triage_status")

        # Rejected jobs should never be surfaced in the console.
        statement = statement.where(JobRow.triage_status != TriageStatus.REJECTED.value)

        # Inbox-facing default behavior excludes items that already left review.
        if requested_triage_status in (None, ""):
            statement = statement.where(
                JobRow.triage_status.not_in(
                    (
                        TriageStatus.SHORTLISTED.value,
                        TriageStatus.QUEUED_FOR_PACKAGE.value,
                        TriageStatus.PACKAGE_READY.value,
                    )
                )
            )
        elif requested_triage_status == TriageStatus.REJECTED.value:
            statement = statement.where(False)

        for key in ("triage_status", "source", "role_family"):
            if value := filters.get(key):
                statement = statement.where(getattr(JobRow, key) == value)
        if filters.get("salary_known"):
            statement = statement.where(
                (JobRow.salary_min_cad.is_not(None)) | (JobRow.salary_max_cad.is_not(None))
            )
        statement = statement.order_by(
            desc(func.coalesce(JobRow.final_score, JobRow.deterministic_score, 0)),
            desc(JobRow.discovered_at),
        )
        if limit is not None:
            statement = statement.limit(max(1, int(limit)))
        with Session(self.engine) as session:
            rows = session.exec(statement).all()
            return [JobListItem(**job.model_dump(), description_text=description_text) for job, description_text in rows]

    def get_job(self, job_id: int) -> JobRow | None:
        with Session(self.engine) as session:
            return session.get(JobRow, job_id)

    def get_job_score_breakdown(self, job_id: int) -> JobScoreRow | None:
        with Session(self.engine) as session:
            return session.exec(
                select(JobScoreRow)
                .where(JobScoreRow.job_id == job_id)
                .order_by(desc(JobScoreRow.id))
                .limit(1)
            ).first()

    def count_jobs(self) -> int:
        with Session(self.engine) as session:
            row = session.exec(select(func.count()).select_from(JobRow)).one()
            return int(row)

    def count_jobs_by_source(self) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(JobRow.source, func.count()).group_by(JobRow.source).order_by(JobRow.source.asc())
            ).all()
            return {str(source): int(count) for source, count in rows}

    def count_jobs_by_triage_status(self) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(JobRow.triage_status, func.count()).group_by(JobRow.triage_status).order_by(JobRow.triage_status.asc())
            ).all()
            return {str(status): int(count) for status, count in rows}

    def count_packages_by_status(self) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(PackageRequestRow.status, func.count()).group_by(PackageRequestRow.status).order_by(PackageRequestRow.status.asc())
            ).all()
            return {str(status): int(count) for status, count in rows}

    def fetch_next_queued_package(self) -> PackageRequestRow | None:
        with Session(self.engine) as session:
            return session.exec(
                select(PackageRequestRow)
                .where(PackageRequestRow.status == PackageStatus.QUEUED.value)
                .order_by(PackageRequestRow.created_at.asc())
                .limit(1)
            ).first()

    def list_packages(self, statuses: list[str] | None = None, limit: int | None = None) -> list[PackageListItem]:
        statement = (
            select(PackageRequestRow, JobRow)
            .join(JobRow, JobRow.id == PackageRequestRow.job_id)
            .order_by(desc(PackageRequestRow.created_at), desc(PackageRequestRow.id))
        )
        if statuses:
            statement = statement.where(PackageRequestRow.status.in_(tuple(statuses)))
        if limit is not None:
            statement = statement.limit(max(1, int(limit)))
        with Session(self.engine) as session:
            rows = session.exec(statement).all()
            return [
                PackageListItem(
                    package_id=int(package.id),
                    package_type=package.package_type,
                    package_status=package.status,
                    requested_by=package.requested_by,
                    generation_profile=package.generation_profile,
                    created_at=package.created_at,
                    started_at=package.started_at,
                    completed_at=package.completed_at,
                    error_message=package.error_message,
                    job_id=int(job.id),
                    job_version_id=package.job_version_id,
                    company=job.company,
                    title_raw=job.title_raw,
                    title_normalized=job.title_normalized,
                    role_family=job.role_family,
                    seniority=job.seniority,
                    location_raw=job.location_raw,
                    work_mode=job.work_mode,
                    source=job.source,
                    url=job.url,
                    salary_min_cad=job.salary_min_cad,
                    salary_max_cad=job.salary_max_cad,
                    salary_currency=job.salary_currency,
                    salary_period=job.salary_period,
                    deterministic_score=job.deterministic_score,
                    final_score=job.final_score,
                )
                for package, job in rows
            ]
