"""Collector orchestration for normalization, extraction, scoring, and persistence."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from shared.config import load_runtime_config
from shared.enums import JobState, TriageStatus
from shared.models import NormalizedJob
from shared.repository import Repository, apply_extraction_payload_to_job

from .extraction import ExtractionArtifacts, extract_profile_data, merge_llm_extraction
from .llm import LLMClient
from .normalization import content_hash as build_content_hash
from .normalization import infer_compensation
from .profiles import ProfileConfig
from .scoring import compute_deterministic_score, merge_llm_analysis
from .scraper.models import ScrapedJobPosting


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreparedJob:
    job: NormalizedJob
    upsert_job_id: int
    version_id: int
    change_type: str
    content_hash: str
    cache_key: str | None
    artifacts: ExtractionArtifacts
    score: Any


@dataclass(slots=True)
class CollectorPipeline:
    repository: Repository
    profile: ProfileConfig
    llm_client: LLMClient | None = None
    scoring_version: str = "framework-v1"

    def __post_init__(self) -> None:
        if self.llm_client is None:
            runtime_config = load_runtime_config()
            self.llm_client = LLMClient(runtime_config.llm_config, self.profile)

    def import_scraped_jobs(self, jobs: list[ScrapedJobPosting]) -> list[dict[str, object]]:
        return self.import_normalized_jobs([job.to_normalized_job(self.profile) for job in jobs])

    def import_normalized_jobs(self, jobs: list[NormalizedJob]) -> list[dict[str, object]]:
        prepared_jobs = [self._prepare_job(job) for job in jobs]
        llm_analyses = self._run_llm_batch(prepared_jobs)
        return [self._finalize_job(prepared_job, llm_analyses.get(index)) for index, prepared_job in enumerate(prepared_jobs)]

    def _process_job(self, job: NormalizedJob) -> dict[str, object]:
        prepared_job = self._prepare_job(job)
        llm_analyses = self._run_llm_batch([prepared_job])
        return self._finalize_job(prepared_job, llm_analyses.get(0))

    def _prepare_job(self, job: NormalizedJob) -> PreparedJob:
        if not (job.salary_min_cad or job.salary_max_cad):
            compensation = infer_compensation(job.description_text)
            if compensation:
                job.salary_min_cad = compensation.salary_min
                job.salary_max_cad = compensation.salary_max
                job.salary_currency = compensation.currency
                job.salary_period = compensation.period
        content_hash = build_content_hash(job)
        logger.debug(
            "Processing normalized job company=%s title=%s profile=%s",
            job.company,
            job.title_normalized or job.title_raw,
            self.profile.profile_name,
        )
        upsert = self.repository.upsert_job(job, content_hash)
        artifacts = extract_profile_data(job, self.profile)
        job.normalized_facets = artifacts.normalized_facets
        job.profile_signals = artifacts.profile_signals
        job.extraction_payload = artifacts.extraction_payload
        self.repository.save_job_payloads(
            upsert.job_id,
            artifacts.normalized_facets,
            artifacts.profile_signals,
            artifacts.extraction_payload,
        )
        self.repository.replace_job_skills(
            upsert.job_id,
            upsert.version_id,
            {
                name: values
                for name, values in artifacts.normalized_facets.items()
                if isinstance(values, list) and values
            },
            "profile-extraction",
        )
        score = compute_deterministic_score(job, self.profile, artifacts)
        return PreparedJob(
            job=job,
            upsert_job_id=upsert.job_id,
            version_id=upsert.version_id,
            change_type=upsert.change_type,
            content_hash=content_hash,
            cache_key=self.llm_client.build_cache_key(content_hash) if self.llm_client and self.llm_client.config.cache_enabled else None,
            artifacts=artifacts,
            score=score,
        )

    def _run_llm_batch(self, prepared_jobs: list[PreparedJob]) -> dict[int, tuple[dict[str, Any], str]]:
        if not self.llm_client:
            return {}
        analyses: dict[int, tuple[dict[str, Any], str]] = {}
        eligible_jobs: dict[int, PreparedJob] = {}
        for index, prepared_job in enumerate(prepared_jobs):
            if not self.llm_client.should_analyze(prepared_job.score.deterministic_score):
                continue
            cache_key = prepared_job.cache_key
            if cache_key:
                cached_analysis = self.repository.get_cached_analysis(cache_key)
                if cached_analysis:
                    analyses[index] = (dict(cached_analysis.analysis_json), "cache")
                    self.repository.attach_analysis_to_job(prepared_job.upsert_job_id, int(cached_analysis.id))
                    continue
            eligible_jobs[index] = prepared_job
        if not eligible_jobs:
            return analyses
        analyses.update(asyncio.run(self._collect_llm_analyses(eligible_jobs)))
        return analyses

    async def _collect_llm_analyses(self, eligible_jobs: dict[int, PreparedJob]) -> dict[int, tuple[dict[str, Any], str]]:
        if not self.llm_client:
            return {}
        semaphore = asyncio.Semaphore(max(1, int(self.llm_client.config.max_concurrent_requests)))

        async def analyze_one(index: int, prepared_job: PreparedJob) -> tuple[int, tuple[dict[str, Any], str]]:
            async with semaphore:
                if hasattr(self.llm_client, "analyze_with_source_async"):
                    analysis, source = await self.llm_client.analyze_with_source_async(
                        prepared_job.job,
                        prepared_job.artifacts,
                        prepared_job.score.deterministic_score,
                    )
                else:
                    analysis = await self.llm_client.analyze_async(
                        prepared_job.job,
                        prepared_job.artifacts,
                        prepared_job.score.deterministic_score,
                    )
                    source = "remote"
                return index, (analysis, source)

        tasks = [analyze_one(index, prepared_job) for index, prepared_job in eligible_jobs.items()]
        completed = await asyncio.gather(*tasks)
        return {index: analysis for index, analysis in completed}

    def _finalize_job(self, prepared_job: PreparedJob, analysis_result: tuple[dict[str, Any], str] | None) -> dict[str, object]:
        upsert_job_id = prepared_job.upsert_job_id
        version_id = prepared_job.version_id
        artifacts = prepared_job.artifacts
        score = prepared_job.score
        analysis = analysis_result[0] if analysis_result else None
        analysis_source = analysis_result[1] if analysis_result else None
        if analysis:
            llm_extraction = analysis.get("extraction", {})
            if isinstance(llm_extraction, dict):
                apply_extraction_payload_to_job(prepared_job.job, llm_extraction)
                artifacts = merge_llm_extraction(prepared_job.job, artifacts, llm_extraction)
                prepared_job.job.normalized_facets = artifacts.normalized_facets
                prepared_job.job.profile_signals = artifacts.profile_signals
                prepared_job.job.extraction_payload = artifacts.extraction_payload
                score = compute_deterministic_score(prepared_job.job, self.profile, artifacts)
                self.repository.apply_extraction_updates(upsert_job_id, llm_extraction)
            llm_evaluation = analysis.get("evaluation", {})
            if isinstance(llm_evaluation, dict):
                score = merge_llm_analysis(score, llm_evaluation, self.profile)
            if self.llm_client and analysis_source != "cache":
                self.repository.save_analysis(
                    upsert_job_id,
                    version_id,
                    self.llm_client.model_name,
                    self.llm_client.prompt_version,
                    analysis,
                    cache_key=prepared_job.cache_key if analysis_source == "remote" else None,
                    cache_source=analysis_source,
                )
        self.repository.save_job_payloads(
            upsert_job_id,
            artifacts.normalized_facets,
            artifacts.profile_signals,
            artifacts.extraction_payload,
            score.scoring_explanation,
        )
        self.repository.save_score(upsert_job_id, version_id, score, self.scoring_version)
        cleared_prefilter = not score.hard_rejects
        state = JobState.FILTERED_OUT.value if not cleared_prefilter else JobState.SCORED.value
        triage_status = TriageStatus.REJECTED.value if not cleared_prefilter else TriageStatus.NEW.value
        if score.recommendation == "shortlisted":
            triage_status = TriageStatus.SHORTLISTED.value
        self.repository.set_triage_status(upsert_job_id, triage_status)
        logger.debug(
            "Persisted job_id=%s version_id=%s change_type=%s deterministic=%s final=%s recommendation=%s",
            upsert_job_id,
            version_id,
            prepared_job.change_type,
            score.deterministic_score,
            score.final_score,
            score.recommendation,
        )
        return {
            "job_id": upsert_job_id,
            "version_id": version_id,
            "change_type": prepared_job.change_type,
            "state": state,
            "analysis": analysis,
            "score": score.to_dict(),
        }
