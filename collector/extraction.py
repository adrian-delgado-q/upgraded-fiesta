from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.models import NormalizedJob

from .profiles import ProfileConfig


@dataclass(slots=True)
class ExtractionArtifacts:
    normalized_facets: dict[str, Any]
    profile_signals: dict[str, Any]
    extraction_payload: dict[str, Any]


def _job_search_text(job: NormalizedJob) -> str:
    parts = [
        job.title_normalized or job.title_raw,
        job.company,
        job.location_raw or "",
        job.work_mode or "",
        job.role_family or "",
        job.seniority or "",
        job.description_text,
    ]
    return "\n".join(part for part in parts if part).lower()


def _add_unique(target: list[str], seen: set[str], value: str) -> None:
    cleaned = str(value).strip()
    lowered = cleaned.lower()
    if cleaned and lowered not in seen:
        seen.add(lowered)
        target.append(cleaned)


def _extract_vocabularies(text: str, profile: ProfileConfig) -> dict[str, list[str]]:
    extracted: dict[str, list[str]] = {}
    for name, vocabulary in profile.extraction.vocabularies.items():
        matches: list[str] = []
        seen: set[str] = set()
        for term in vocabulary.terms:
            if term.lower() in text:
                _add_unique(matches, seen, term)
        for alias, canonical in vocabulary.aliases.items():
            if alias.lower() in text:
                _add_unique(matches, seen, canonical)
        extracted[name] = matches
    return extracted


def _extract_signals(text: str, profile: ProfileConfig) -> dict[str, Any]:
    signals: dict[str, dict[str, Any]] = {"positive": {}, "negative": {}, "neutral": {}}
    groups: dict[str, dict[str, Any]] = {}
    for signal_name, signal in profile.extraction.signals.items():
        terms = signal.terms or [signal_name]
        if not any(term.lower() in text for term in terms):
            continue
        payload = {"weight": float(signal.weight), "group": signal.group, "terms": terms}
        signals[signal.sentiment][signal_name] = payload
        group_state = groups.setdefault(signal.group, {"positive": 0.0, "negative": 0.0, "neutral": 0.0, "net": 0.0, "matched": []})
        signed_weight = float(signal.weight)
        if signal.sentiment == "negative":
            group_state["negative"] += signed_weight
            group_state["net"] -= signed_weight
        elif signal.sentiment == "neutral":
            group_state["neutral"] += signed_weight
        else:
            group_state["positive"] += signed_weight
            group_state["net"] += signed_weight
        group_state["matched"].append(signal_name)
    return {"positive": signals["positive"], "negative": signals["negative"], "neutral": signals["neutral"], "groups": groups}


def extract_profile_data(job: NormalizedJob, profile: ProfileConfig) -> ExtractionArtifacts:
    search_text = _job_search_text(job)
    vocabularies = _extract_vocabularies(search_text, profile)
    profile_signals = _extract_signals(search_text, profile)
    normalized_facets: dict[str, Any] = {
        "role_family": job.role_family,
        "seniority": job.seniority,
        "work_mode": job.work_mode,
        "location_country": job.location_country,
        **vocabularies,
    }
    extraction_payload = {
        "taxonomy": {
            "role_family": job.role_family,
            "seniority": job.seniority,
            "work_mode": job.work_mode,
        },
        "vocabularies": vocabularies,
        "signals": profile_signals,
    }
    return ExtractionArtifacts(
        normalized_facets=normalized_facets,
        profile_signals=profile_signals,
        extraction_payload=extraction_payload,
    )


def merge_llm_extraction(job: NormalizedJob, artifacts: ExtractionArtifacts, llm_payload: dict[str, Any]) -> ExtractionArtifacts:
    facets = dict(artifacts.normalized_facets)
    signals = dict(artifacts.profile_signals)
    extraction_payload = dict(artifacts.extraction_payload)
    extracted_facets = llm_payload.get("facets")
    if isinstance(extracted_facets, dict):
        for key, values in extracted_facets.items():
            if isinstance(values, list):
                existing = list(facets.get(key) or [])
                seen = {str(item).lower() for item in existing}
                for item in values:
                    cleaned = str(item).strip()
                    lowered = cleaned.lower()
                    if cleaned and lowered not in seen:
                        seen.add(lowered)
                        existing.append(cleaned)
                facets[key] = existing
    extraction_payload["llm_extraction"] = llm_payload
    return ExtractionArtifacts(normalized_facets=facets, profile_signals=signals, extraction_payload=extraction_payload)
