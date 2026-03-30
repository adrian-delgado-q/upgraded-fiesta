from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from shared.enums import Recommendation
from shared.models import NormalizedJob, ScoreBreakdown

from .extraction import ExtractionArtifacts
from .profiles import CategoryConfig, Condition, ProfileConfig, all_conditions_match, get_context_value


def build_feature_context(
    job: NormalizedJob,
    artifacts: ExtractionArtifacts,
    llm_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_dict = asdict(job)
    context: dict[str, Any] = {
        **job_dict,
        "job": job_dict,
        "facets": artifacts.normalized_facets,
        "signals": artifacts.profile_signals,
        "llm": llm_payload or {},
    }
    for key, value in artifacts.normalized_facets.items():
        context.setdefault(key, value)
    return context


def _normalize_scalar(value: Any) -> str:
    return str(value or "").strip().lower()


def _coerce_iterable(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def rule_matches(context: dict[str, Any], condition: Condition) -> bool:
    raw = get_context_value(context, condition.field)
    operator = condition.operator
    if operator == "missing":
        return raw in (None, "", [], {})
    if operator == "exists":
        return raw not in (None, "", [], {})
    if operator == "contains_any":
        values = [_normalize_scalar(item) for item in condition.values or ([condition.value] if condition.value is not None else [])]
        if isinstance(raw, str):
            haystack = raw.lower()
            return any(item and item in haystack for item in values)
        haystack = " ".join(_normalize_scalar(item) for item in _coerce_iterable(raw))
        return any(item and item in haystack for item in values)
    if operator == "intersects":
        raw_values = {_normalize_scalar(item) for item in _coerce_iterable(raw)}
        expected = {_normalize_scalar(item) for item in condition.values}
        return bool(raw_values & expected)
    if operator == "in":
        return _normalize_scalar(raw) in {_normalize_scalar(item) for item in condition.values}
    if operator == "not_in":
        return _normalize_scalar(raw) not in {_normalize_scalar(item) for item in condition.values}
    if operator == "equals":
        return _normalize_scalar(raw) == _normalize_scalar(condition.value)
    if operator == "matches_regex":
        return isinstance(raw, str) and bool(re.search(str(condition.value or ""), raw, flags=re.IGNORECASE))
    if raw in (None, ""):
        return False
    raw_number = float(raw)
    expected = float(condition.value)
    if operator == "lt":
        return raw_number < expected
    if operator == "lte":
        return raw_number <= expected
    if operator == "gt":
        return raw_number > expected
    if operator == "gte":
        return raw_number >= expected
    raise ValueError(f"unsupported operator: {operator}")


def _bounded_score(value: float, config: CategoryConfig) -> float:
    bounded = float(value)
    if config.cap is not None:
        bounded = min(bounded, float(config.cap))
    if config.floor is not None:
        bounded = max(bounded, float(config.floor))
    return bounded


def _score_rule_category(context: dict[str, Any], config: CategoryConfig) -> tuple[float, str | None]:
    for rule in config.rules:
        if all_conditions_match(context, rule.when, rule_matches):
            return _bounded_score(rule.score, config), rule.reason
    return _bounded_score(config.default_score, config), None


def _score_value_map(context: dict[str, Any], config: CategoryConfig) -> tuple[float, str | None]:
    raw = get_context_value(context, config.field or "")
    normalized = _normalize_scalar(raw)
    score = float(config.map.get(normalized, config.default_score))
    return _bounded_score(score, config), None


def _score_signal_group(context: dict[str, Any], config: CategoryConfig) -> tuple[float, str | None]:
    groups = get_context_value(context, "signals.groups") or {}
    group = groups.get(config.signal_group or "")
    if not isinstance(group, dict):
        return _bounded_score(config.default_score, config), None
    score = float(group.get("net", 0.0))
    return _bounded_score(score, config), None


def _recommendation_for(score: float, profile: ProfileConfig) -> str:
    thresholds = profile.scoring.thresholds
    if score >= float(thresholds.shortlisted):
        return Recommendation.SHORTLISTED.value
    if score >= float(thresholds.review):
        return Recommendation.REVIEW.value
    if score >= float(thresholds.maybe):
        return Recommendation.MAYBE.value
    return Recommendation.ARCHIVE.value


def compute_deterministic_score(job: NormalizedJob, profile: ProfileConfig, artifacts: ExtractionArtifacts | None = None) -> ScoreBreakdown:
    artifacts = artifacts or ExtractionArtifacts(normalized_facets={}, profile_signals={}, extraction_payload={})
    context = build_feature_context(job, artifacts)
    category_scores: dict[str, float] = {}
    reasons: list[str] = []
    hard_rejects: list[str] = []

    for reject_rule in profile.scoring.prefilter:
        if all_conditions_match(context, reject_rule.when, rule_matches):
            hard_rejects.append(reject_rule.reason)

    for name, category in profile.scoring.categories.items():
        if category.kind == "value_map":
            score, reason = _score_value_map(context, category)
        elif category.kind == "signal_group":
            score, reason = _score_signal_group(context, category)
        else:
            score, reason = _score_rule_category(context, category)
        category_scores[name] = score
        if reason:
            reasons.append(reason)

    deterministic = sum(category_scores.values())
    if hard_rejects:
        deterministic = min(deterministic, 0.0)
    recommendation = Recommendation.ARCHIVE.value if hard_rejects else _recommendation_for(deterministic, profile)
    explanation = {
        "category_scores": category_scores,
        "hard_rejects": hard_rejects,
        "signal_groups": artifacts.profile_signals.get("groups", {}),
        "vocabularies": artifacts.normalized_facets,
        "stage": "deterministic",
    }
    return ScoreBreakdown(
        category_scores=category_scores,
        deterministic_score=deterministic,
        final_score=deterministic,
        recommendation=recommendation,
        hard_rejects=hard_rejects,
        reasons=reasons,
        warnings=list(hard_rejects),
        scoring_explanation=explanation,
    )


def merge_llm_analysis(breakdown: ScoreBreakdown, analysis: dict[str, Any], profile: ProfileConfig) -> ScoreBreakdown:
    fit_score = float(analysis.get("fit_score") or 0.0)
    risk_penalty = float(analysis.get("risk_penalty") or 0.0)
    policy = profile.scoring.llm
    final_score = (breakdown.deterministic_score * float(policy.deterministic_weight)) + ((fit_score + risk_penalty) * float(policy.llm_weight))
    breakdown.llm_fit_score = fit_score
    breakdown.llm_risk_penalty = risk_penalty
    breakdown.final_score = final_score
    if breakdown.hard_rejects:
        breakdown.recommendation = Recommendation.ARCHIVE.value
    else:
        breakdown.recommendation = str(analysis.get("recommendation") or _recommendation_for(final_score, profile))
    if isinstance(analysis.get("reasons"), list):
        breakdown.reasons.extend(str(item) for item in analysis["reasons"])
    if isinstance(analysis.get("concerns"), list):
        breakdown.warnings.extend(str(item) for item in analysis["concerns"])
    breakdown.scoring_explanation = {
        **breakdown.scoring_explanation,
        "stage": "llm-augmented",
        "llm_evaluation": analysis,
    }
    return breakdown
