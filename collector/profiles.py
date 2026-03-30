from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("must be a list of non-empty strings")
    cleaned = [str(item).strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("must be a list of non-empty strings")
    return cleaned


def _clean_string_mapping(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("must be a mapping of strings")
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


class TaxonomyRule(ProfileModel):
    value: str
    variants: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must be non-empty")
        return cleaned

    @field_validator("variants", "keywords", mode="before")
    @classmethod
    def validate_lists(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class LocationConfig(ProfileModel):
    allowed_countries: list[str] = Field(default_factory=list)
    country_aliases: dict[str, str] = Field(default_factory=dict)
    search_locations: list[str] = Field(default_factory=list)

    @field_validator("allowed_countries", "search_locations", mode="before")
    @classmethod
    def validate_lists(cls, value: Any) -> list[str]:
        return _clean_string_list(value)

    @field_validator("country_aliases", mode="before")
    @classmethod
    def validate_mapping(cls, value: Any) -> dict[str, str]:
        return _clean_string_mapping(value)


class NormalizationConfig(ProfileModel):
    title_replacements: dict[str, str] = Field(default_factory=dict)
    role_taxonomy: list[TaxonomyRule] = Field(default_factory=list)
    seniority_taxonomy: list[TaxonomyRule] = Field(default_factory=list)
    work_mode_taxonomy: list[TaxonomyRule] = Field(default_factory=list)
    locations: LocationConfig = Field(default_factory=LocationConfig)

    @field_validator("title_replacements", mode="before")
    @classmethod
    def validate_mapping(cls, value: Any) -> dict[str, str]:
        return _clean_string_mapping(value)


class VocabularyConfig(ProfileModel):
    terms: list[str] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)

    @field_validator("terms", mode="before")
    @classmethod
    def validate_terms(cls, value: Any) -> list[str]:
        return _clean_string_list(value)

    @field_validator("aliases", mode="before")
    @classmethod
    def validate_aliases(cls, value: Any) -> dict[str, str]:
        return _clean_string_mapping(value)


class SignalDefinition(ProfileModel):
    weight: float = 0.0
    group: str = "general"
    sentiment: Literal["positive", "negative", "neutral"] = "positive"
    terms: list[str] = Field(default_factory=list)

    @field_validator("terms", mode="before")
    @classmethod
    def validate_terms(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class ExtractionConfig(ProfileModel):
    vocabularies: dict[str, VocabularyConfig] = Field(default_factory=dict)
    signals: dict[str, SignalDefinition] = Field(default_factory=dict)


class Condition(ProfileModel):
    field: str
    operator: Literal["equals", "in", "not_in", "contains_any", "matches_regex", "exists", "missing", "lt", "lte", "gt", "gte", "intersects"]
    value: str | float | int | bool | None = None
    values: list[str | float | int | bool] = Field(default_factory=list)

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must be non-empty")
        return cleaned

    @field_validator("values", mode="before")
    @classmethod
    def validate_values(cls, value: Any) -> list[str | float | int | bool]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("values must be a list")
        return [item for item in value if item not in (None, "")]


class ScoreRule(ProfileModel):
    score: float
    when: list[Condition] = Field(default_factory=list)
    reason: str | None = None


class RejectRule(ProfileModel):
    when: list[Condition]
    reason: str


class CategoryConfig(ProfileModel):
    kind: Literal["rules", "value_map", "signal_group"] = "rules"
    field: str | None = None
    rules: list[ScoreRule] = Field(default_factory=list)
    map: dict[str, float] = Field(default_factory=dict)
    signal_group: str | None = None
    default_score: float = 0.0
    cap: float | None = None
    floor: float | None = None

    @field_validator("map", mode="before")
    @classmethod
    def validate_map(cls, value: Any) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("map must be a mapping")
        return {str(key).strip(): float(score) for key, score in value.items() if str(key).strip()}


class ThresholdConfig(ProfileModel):
    shortlisted: float = 80.0
    review: float = 65.0
    maybe: float = 50.0


class LLMScoringConfig(ProfileModel):
    analyze_threshold: float = 35.0
    deterministic_weight: float = 0.6
    llm_weight: float = 0.4


class ScoringConfig(ProfileModel):
    prefilter: list[RejectRule] = Field(default_factory=list)
    categories: dict[str, CategoryConfig] = Field(default_factory=dict)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    llm: LLMScoringConfig = Field(default_factory=LLMScoringConfig)


class LLMProfileConfig(ProfileModel):
    extraction_enabled: bool = True
    evaluation_enabled: bool = True
    extraction_guidance: str = ""
    evaluation_guidance: str = ""


class SearchConfig(ProfileModel):
    query_terms: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)

    @field_validator("query_terms", "providers", "locations", mode="before")
    @classmethod
    def validate_lists(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class DefaultsConfig(ProfileModel):
    role_family: str = "general"
    seniority: str = "mid"
    work_mode: str = ""
    location_country: str = ""


class ProfileConfig(ProfileModel):
    profile_name: str = "default"
    extends: list[str] = Field(default_factory=list)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    llm: LLMProfileConfig = Field(default_factory=LLMProfileConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    @field_validator("extends", mode="before")
    @classmethod
    def validate_extends(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class ProfilesFile(ProfileModel):
    active_profile: str
    profiles: dict[str, ProfileConfig]

    @field_validator("profiles", mode="before")
    @classmethod
    def validate_profiles(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError("profiles must be a non-empty mapping")
        return {str(key).strip(): item for key, item in value.items() if str(key).strip()}

    @model_validator(mode="after")
    def validate_active_profile(self) -> "ProfilesFile":
        if self.active_profile not in self.profiles:
            raise ValueError(f"active_profile must reference an existing profile: {self.active_profile}")
        return self


def _attach_profile_name(name: str, profile: ProfileConfig) -> ProfileConfig:
    return profile.model_copy(update={"profile_name": name})


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if key not in merged:
            merged[key] = deepcopy(value)
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _resolve_profile(name: str, raw_profiles: dict[str, dict[str, Any]], stack: list[str] | None = None) -> dict[str, Any]:
    stack = list(stack or [])
    if name in stack:
        raise ValueError(f"Cyclic profile inheritance detected: {' -> '.join(stack + [name])}")
    if name not in raw_profiles:
        raise ValueError(f"Unknown profile referenced in extends: {name}")
    raw = deepcopy(raw_profiles[name])
    parents = [str(item).strip() for item in raw.get("extends", []) if str(item).strip()]
    stack.append(name)
    resolved: dict[str, Any] = {}
    for parent in parents:
        resolved = _deep_merge(resolved, _resolve_profile(parent, raw_profiles, stack))
    raw.pop("extends", None)
    return _deep_merge(resolved, raw)


def load_profiles(path: str | Path) -> ProfilesFile:
    profiles_path = Path(path)
    if not profiles_path.exists():
        raise FileNotFoundError(f"Profiles file not found: {profiles_path}")
    with profiles_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Profiles file must contain a top-level mapping: {profiles_path}")
    raw_profiles = raw.get("profiles")
    if not isinstance(raw_profiles, dict):
        raise ValueError("profiles must be a mapping")
    resolved_profiles: dict[str, ProfileConfig] = {}
    for name in raw_profiles:
        merged = _resolve_profile(name, raw_profiles)
        try:
            resolved_profiles[name] = _attach_profile_name(name, ProfileConfig.model_validate({"profile_name": name, **merged}))
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
    try:
        config = ProfilesFile.model_validate({"active_profile": raw.get("active_profile"), "profiles": resolved_profiles})
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    return config


def load_active_profile(path: str | Path, profile: str | None = None) -> ProfileConfig:
    profiles = load_profiles(path)
    selected = profile or profiles.active_profile
    if selected not in profiles.profiles:
        raise ValueError(f"Unknown profile: {selected}")
    return _attach_profile_name(selected, profiles.profiles[selected])


def extract_search_terms(profile: ProfileConfig) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        cleaned = str(item).strip()
        if not cleaned:
            return
        lowered = cleaned.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        terms.append(cleaned)

    for item in profile.search.query_terms:
        add(item)
    for rule in profile.normalization.role_taxonomy:
        add(rule.value)
        for item in [*rule.variants, *rule.keywords]:
            add(item)
    for vocabulary in profile.extraction.vocabularies.values():
        for item in vocabulary.terms:
            add(item)
    for signal_name, signal in profile.extraction.signals.items():
        add(signal_name)
        for term in signal.terms:
            add(term)
    return terms


def get_context_value(context: dict[str, Any], path: str) -> Any:
    if path in context:
        return context[path]
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return None
    return current


def all_conditions_match(context: dict[str, Any], conditions: list[Condition], evaluator) -> bool:
    return all(evaluator(context, condition) for condition in conditions)
