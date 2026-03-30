"""Collector orchestration for normalization, extraction, scoring, and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from shared.config import load_runtime_config
from shared.enums import JobState, TriageStatus
from shared.models import NormalizedJob
from shared.repository import Repository

from .extraction import ExtractionArtifacts, extract_profile_data, merge_llm_extraction
from .llm import LLMClient
from .normalization import content_hash as build_content_hash
from .profiles import ProfileConfig
from .scoring import compute_deterministic_score, merge_llm_analysis
from .scraper.models import ScrapedJobPosting


logger = logging.getLogger(__name__)


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
        return [self._process_job(job.to_normalized_job(self.profile)) for job in jobs]

    def import_normalized_jobs(self, jobs: list[NormalizedJob]) -> list[dict[str, object]]:
        return [self._process_job(job) for job in jobs]

    def _process_job(self, job: NormalizedJob) -> dict[str, object]:
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
        analysis: dict[str, Any] | None = None
        if self.llm_client and self.llm_client.should_analyze(score.deterministic_score):
            analysis = self.llm_client.analyze(job, artifacts, score.deterministic_score)
            llm_extraction = analysis.get("extraction", {})
            if isinstance(llm_extraction, dict):
                artifacts = merge_llm_extraction(job, artifacts, llm_extraction)
                self.repository.apply_extraction_updates(upsert.job_id, llm_extraction)
            llm_evaluation = analysis.get("evaluation", {})
            if isinstance(llm_evaluation, dict):
                score = merge_llm_analysis(score, llm_evaluation, self.profile)
            self.repository.save_analysis(
                upsert.job_id,
                upsert.version_id,
                self.llm_client.model_name,
                self.llm_client.prompt_version,
                analysis,
            )
        self.repository.save_job_payloads(
            upsert.job_id,
            artifacts.normalized_facets,
            artifacts.profile_signals,
            artifacts.extraction_payload,
            score.scoring_explanation,
        )
        self.repository.save_score(upsert.job_id, upsert.version_id, score, self.scoring_version)
        cleared_prefilter = not score.hard_rejects
        state = JobState.FILTERED_OUT.value if not cleared_prefilter else JobState.SCORED.value
        triage_status = TriageStatus.REJECTED.value if not cleared_prefilter else TriageStatus.NEW.value
        if score.recommendation == "shortlisted":
            triage_status = TriageStatus.SHORTLISTED.value
        self.repository.set_triage_status(upsert.job_id, triage_status)
        logger.debug(
            "Persisted job_id=%s version_id=%s change_type=%s deterministic=%s final=%s recommendation=%s",
            upsert.job_id,
            upsert.version_id,
            upsert.change_type,
            score.deterministic_score,
            score.final_score,
            score.recommendation,
        )
        return {
            "job_id": upsert.job_id,
            "version_id": upsert.version_id,
            "change_type": upsert.change_type,
            "state": state,
            "analysis": analysis,
            "score": score.to_dict(),
        }
