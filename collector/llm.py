from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

from shared.config import LLMSettings
from shared.models import NormalizedJob

from .extraction import ExtractionArtifacts
from .profiles import ProfileConfig


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


class LLMClient:
    def __init__(self, config: LLMSettings, profile: ProfileConfig) -> None:
        self.config = config
        self.profile = profile
        self.api_key = (config.api_key or os.environ.get(config.api_key_env, "")).strip()
        self.client = httpx.Client(timeout=config.timeout_seconds, headers={"User-Agent": "upgraded-fiesta/0.1"})

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

    def analyze(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> dict[str, dict[str, Any]]:
        if self.uses_remote_api:
            try:
                return self._analyze_remote(job, artifacts, deterministic_score)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError):
                return self._analyze_local(job, artifacts, deterministic_score)
        return self._analyze_local(job, artifacts, deterministic_score)

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

    def _analyze_remote(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> dict[str, dict[str, Any]]:
        extraction_prompt = self._build_extraction_prompt(job, artifacts)
        evaluation_prompt = self._build_evaluation_prompt(job, artifacts, deterministic_score)
        extraction = LLMExtractionResponse.model_validate(self._chat_json(extraction_prompt))
        evaluation = LLMEvaluationResponse.model_validate(self._chat_json(evaluation_prompt))
        return {"extraction": extraction.model_dump(), "evaluation": evaluation.model_dump()}

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

    def _build_extraction_prompt(self, job: NormalizedJob, artifacts: ExtractionArtifacts) -> str:
        vocabulary_names = ", ".join(sorted(self.profile.extraction.vocabularies)) or "skills, tools, certifications"
        return (
            "Extract structured facts from this job posting. "
            "Return JSON with keys: normalized_title, role_family, seniority, work_mode, "
            "location_interpretation, compensation, facets, evidence.\n"
            "Compensation must include salary_min, salary_max, salary_currency, salary_period, salary_is_explicit.\n"
            f"Profile: {self.profile.profile_name}\n"
            f"Vocabulary buckets: {vocabulary_names}\n"
            f"Profile guidance: {self.profile.llm.extraction_guidance}\n\n"
            f"Title: {job.title_normalized or job.title_raw}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location_raw or ''}\n"
            f"Work mode: {job.work_mode or ''}\n"
            f"Role family: {job.role_family or ''}\n"
            f"Seniority: {job.seniority or ''}\n"
            f"Deterministic facets: {json.dumps(artifacts.normalized_facets, ensure_ascii=True)}\n"
            f"Description:\n{job.description_text}"
        )

    def _build_evaluation_prompt(self, job: NormalizedJob, artifacts: ExtractionArtifacts, deterministic_score: float) -> str:
        return (
            "Evaluate candidate fit for the active profile. "
            "Return JSON with keys: fit_score, risk_penalty, recommendation, reasons, concerns, category_adjustments.\n"
            f"Profile: {self.profile.profile_name}\n"
            f"Profile guidance: {self.profile.llm.evaluation_guidance}\n"
            f"Deterministic score: {deterministic_score}\n"
            f"Signal groups: {json.dumps(artifacts.profile_signals.get('groups', {}), ensure_ascii=True)}\n"
            f"Facets: {json.dumps(artifacts.normalized_facets, ensure_ascii=True)}\n"
            f"Title: {job.title_normalized or job.title_raw}\n"
            f"Description:\n{job.description_text}"
        )
