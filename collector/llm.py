from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import logging
import os
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from shared.config import LLMSettings
from shared.models import NormalizedJob

from .extraction import ExtractionArtifacts
from .profiles import ProfileConfig


logger = logging.getLogger(__name__)


class LLMExtractionResponse(BaseModel):
    normalized_title: str | None = None
    role_family: str | None = None
    seniority: str | None = None
    work_mode: str | None = None
    location_interpretation: dict[str, str | None] = Field(default_factory=dict)
    compensation: dict[str, Any] = Field(default_factory=dict)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


class LLMEvaluationResponse(BaseModel):
    fit_score: float = 0.0
    risk_penalty: float = 0.0
    recommendation: str = "review"
    reasons: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    category_adjustments: dict[str, float] = Field(default_factory=dict)


class LLMAnalysisResponse(BaseModel):
    extraction: LLMExtractionResponse = Field(default_factory=LLMExtractionResponse)
    evaluation: LLMEvaluationResponse = Field(default_factory=LLMEvaluationResponse)


class LLMClient:
    PROMPT_SHAPING_VERSION = "compact-v1"

    def __init__(self, config: LLMSettings, profile: ProfileConfig) -> None:
        self.config = config
        self.profile = profile
        self.api_key = (config.api_key or os.environ.get(config.api_key_env, "")).strip()
        self.timeout = httpx.Timeout(config.timeout_seconds)
        self.client = httpx.Client(timeout=self.timeout, headers={"User-Agent": "upgraded-fiesta/0.1"})

    @property
    def model_name(self) -> str:
        return self.config.model

    @property
    def prompt_version(self) -> str:
        return self.config.prompt_version

    @property
    def uses_remote_api(self) -> bool:
        return self.config.enabled and bool(self.api_key)

    def should_analyze(self, deterministic_score: float) -> bool:
        return self.config.enabled and deterministic_score >= float(self.profile.scoring.llm.analyze_threshold)

    def build_cache_key(self, content_hash: str) -> str:
        raw_str = "|".join(
            [
                content_hash,
                self.profile.profile_name,
                self.config.model,
                self.config.prompt_version,
                self.PROMPT_SHAPING_VERSION,
            ]
        )
        return sha256(raw_str.encode("utf-8")).hexdigest()

    def analyze(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> dict[str, dict[str, Any]]:
        return self.analyze_with_source(job, artifacts, deterministic_score)[0]

    def analyze_with_source(
        self,
        job: NormalizedJob,
        artifacts: ExtractionArtifacts,
        deterministic_score: float,
    ) -> tuple[dict[str, dict[str, Any]], str]:
        if self.uses_remote_api:
            try:
                return self._analyze_remote(job, artifacts, deterministic_score), "remote"
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
                return self._analyze_local(job, artifacts, deterministic_score), "local"
        return self._analyze_local(job, artifacts, deterministic_score), "local"

    async def analyze_async(
        self,
        job: NormalizedJob,
        artifacts: ExtractionArtifacts,
        deterministic_score: float,
    ) -> dict[str, dict[str, Any]]:
        return (await self.analyze_with_source_async(job, artifacts, deterministic_score))[0]

    async def analyze_with_source_async(
        self,
        job: NormalizedJob,
        artifacts: ExtractionArtifacts,
        deterministic_score: float,
    ) -> tuple[dict[str, dict[str, Any]], str]:
        if self.uses_remote_api:
            try:
                return await self._analyze_remote_async(job, artifacts, deterministic_score), "remote"
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
                logger.warning(
                    "Falling back to local LLM analysis company=%s title=%s",
                    job.company,
                    job.title_normalized or job.title_raw,
                )
                return self._analyze_local(job, artifacts, deterministic_score), "local"
        return self._analyze_local(job, artifacts, deterministic_score), "local"

    def _chat_json(self, prompt: str) -> dict[str, Any]:
        response = self.client.post(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON that matches the requested schema."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)

    async def _chat_json_async(self, client: httpx.AsyncClient, prompt: str) -> dict[str, Any]:
        response = await client.post(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": "Return only valid JSON that matches the requested schema."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)

    def _analyze_remote(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> dict[str, dict[str, Any]]:
        analysis_prompt = self._build_analysis_prompt(job, artifacts, deterministic_score)
        analysis = LLMAnalysisResponse.model_validate(self._chat_json(analysis_prompt))
        return analysis.model_dump()

    async def _analyze_remote_async(
        self,
        job: NormalizedJob,
        artifacts: ExtractionArtifacts,
        deterministic_score: float,
    ) -> dict[str, dict[str, Any]]:
        analysis_prompt = self._build_analysis_prompt(job, artifacts, deterministic_score)
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "upgraded-fiesta/0.1"}) as client:
            analysis_payload = await self._chat_json_with_retry(client, prompt=analysis_prompt, job=job, stage="analysis")
        analysis = LLMAnalysisResponse.model_validate(analysis_payload)
        return analysis.model_dump()

    async def _chat_json_with_retry(
        self,
        client: httpx.AsyncClient,
        *,
        prompt: str,
        job: NormalizedJob,
        stage: str,
    ) -> dict[str, Any]:
        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                return await self._chat_json_async(client, prompt)
            except httpx.ReadTimeout:
                logger.warning(
                    "LLM read timeout company=%s title=%s stage=%s attempt=%s/%s",
                    job.company,
                    job.title_normalized or job.title_raw,
                    stage,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    logger.warning(
                        "LLM fallback to local analysis after timeout company=%s title=%s stage=%s",
                        job.company,
                        job.title_normalized or job.title_raw,
                        stage,
                    )
                    raise
                await asyncio.sleep(0)
        raise RuntimeError("unreachable")

    def _analyze_local(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> dict[str, dict[str, Any]]:
        vocabularies = artifacts.normalized_facets
        groups = artifacts.profile_signals.get("groups", {})
        total_positive = sum(float(group.get("positive", 0.0)) for group in groups.values())
        total_negative = sum(float(group.get("negative", 0.0)) for group in groups.values())
        extraction = LLMExtractionResponse(
            normalized_title=job.title_normalized or job.title_raw,
            role_family=job.role_family,
            seniority=job.seniority,
            work_mode=job.work_mode,
            location_interpretation={
                "city": job.location_city,
                "region": job.location_region,
                "country": job.location_country,
            },
            compensation={
                "salary_min": job.salary_min_cad,
                "salary_max": job.salary_max_cad,
                "salary_currency": job.salary_currency,
                "salary_period": job.salary_period,
                "salary_is_explicit": bool(job.salary_min_cad or job.salary_max_cad),
            },
            facets={key: value for key, value in vocabularies.items() if isinstance(value, list)},
            evidence=[f"Matched signal group: {name}" for name in groups] or ["Local heuristic extraction only"],
        )
        fit_score = min(100.0, deterministic_score + total_positive + sum(len(value) for value in vocabularies.values() if isinstance(value, list)))
        risk_penalty = -min(30.0, total_negative)
        recommendation = "review"
        if fit_score + risk_penalty >= float(self.profile.scoring.thresholds.shortlisted):
            recommendation = "shortlisted"
        elif fit_score + risk_penalty < float(self.profile.scoring.thresholds.maybe):
            recommendation = "archive"
        evaluation = LLMEvaluationResponse(
            fit_score=fit_score,
            risk_penalty=risk_penalty,
            recommendation=recommendation,
            reasons=[f"Local fit estimate for profile {self.profile.profile_name}"],
            concerns=["Local fallback evaluation used"],
            category_adjustments={name: float(group.get("net", 0.0)) for name, group in groups.items()},
        )
        return {"extraction": extraction.model_dump(), "evaluation": evaluation.model_dump()}

    def _build_analysis_prompt(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> str:
        vocabulary_names = ", ".join(sorted(self.profile.extraction.vocabularies)) or "skills, tools, certifications"
        compact_payload = {
            "profile": self.profile.profile_name,
            "title": job.title_normalized or job.title_raw,
            "company": job.company,
            "location": job.location_raw or "",
            "work_mode": job.work_mode or "",
            "role_family": job.role_family or "",
            "seniority": job.seniority or "",
            "deterministic_score": deterministic_score,
            "deterministic_facets": artifacts.normalized_facets,
            "signal_groups": artifacts.profile_signals.get("groups", {}),
            "description_excerpt": self._sanitize_description(job.description_text),
        }
        return (
            "Analyze this job for the active profile and return one JSON object with keys "
            "extraction and evaluation.\n"
            "extraction must contain: normalized_title, role_family, seniority, work_mode, "
            "location_interpretation, compensation, facets, evidence.\n"
            "evaluation must contain: fit_score, risk_penalty, recommendation, reasons, concerns, "
            "category_adjustments.\n"
            "Compensation must include salary_min, salary_max, salary_currency, salary_period, salary_is_explicit.\n"
            f"Profile: {self.profile.profile_name}\n"
            f"Vocabulary buckets: {vocabulary_names}\n"
            f"Extraction guidance: {self._compact_text(self.profile.llm.extraction_guidance)}\n"
            f"Evaluation guidance: {self._compact_text(self.profile.llm.evaluation_guidance)}\n"
            f"Context: {json.dumps(compact_payload, ensure_ascii=True, separators=(',', ':'))}"
        )

    def _compact_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    def _sanitize_description(self, description: str) -> str:
        compact = self._compact_text(description)
        max_chars = max(1, int(self.config.max_description_chars))
        if len(compact) <= max_chars:
            return compact
        truncated = compact[: max_chars - 1].rsplit(" ", 1)[0].strip()
        return f"{truncated}..."
