from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

from .profiles import ProfileConfig, TaxonomyRule


def normalize_title(title: str, profile: ProfileConfig) -> str:
    normalized_title = (title or "").lower().strip()
    for key, replacement in profile.normalization.title_replacements.items():
        normalized_title = re.sub(rf"\b{re.escape(key)}\b", replacement, normalized_title)
    return " ".join(normalized_title.split()).title()


def _find_taxonomy_value(text: str, rules: list[TaxonomyRule], default: str) -> str:
    text_lower = text.lower()
    for rule in rules:
        if any(variant.lower() in text_lower for variant in rule.variants):
            return rule.value
    for rule in rules:
        if any(keyword.lower() in text_lower for keyword in rule.keywords):
            return rule.value
    return default


def infer_role_family(text: str, profile: ProfileConfig) -> str:
    return _find_taxonomy_value(text, profile.normalization.role_taxonomy, profile.defaults.role_family)


def infer_seniority(text: str, profile: ProfileConfig) -> str:
    return _find_taxonomy_value(text, profile.normalization.seniority_taxonomy, profile.defaults.seniority)


def infer_work_mode(text: str, profile: ProfileConfig) -> str:
    return _find_taxonomy_value(text, profile.normalization.work_mode_taxonomy, profile.defaults.work_mode)


def _normalize_country_token(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def get_country_aliases(profile: ProfileConfig) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for alias, canonical in profile.normalization.locations.country_aliases.items():
        alias_key = _normalize_country_token(alias)
        canonical_text = canonical.strip()
        if alias_key and canonical_text:
            resolved[alias_key] = canonical_text
    for country in profile.normalization.locations.allowed_countries:
        country_text = country.strip()
        country_key = _normalize_country_token(country_text)
        if country_key and country_text:
            resolved.setdefault(country_key, country_text.title())
    return resolved


def normalize_country_name(country_raw: str | None, profile: ProfileConfig) -> str | None:
    token = _normalize_country_token(country_raw or "")
    if not token:
        return None
    return get_country_aliases(profile).get(token)


def get_allowed_countries(profile: ProfileConfig) -> set[str]:
    return {
        _normalize_country_token(normalize_country_name(item, profile) or item)
        for item in profile.normalization.locations.allowed_countries
        if item.strip()
    }


def find_allowed_country_in_text(text: str | None, profile: ProfileConfig) -> str | None:
    haystack = _normalize_country_token(text or "")
    if not haystack:
        return None
    aliases = get_country_aliases(profile)
    allowed = get_allowed_countries(profile)
    for alias in sorted(aliases, key=len, reverse=True):
        canonical = aliases[alias]
        if _normalize_country_token(canonical) not in allowed:
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", haystack):
            return canonical
    return None


def location_matches_allowed_scope(location: str | None, remote_status: str | None, profile: ProfileConfig) -> bool:
    combined_text = " ".join(part for part in (location, remote_status) if part)
    allowed = get_allowed_countries(profile)
    if not allowed:
        return True
    country = find_allowed_country_in_text(combined_text, profile)
    return country is not None


def normalize_location(location_raw: str | None, profile: ProfileConfig) -> tuple[str | None, str | None, str | None]:
    if not location_raw:
        return None, None, None
    cleaned_location = re.sub(r"\s+", " ", location_raw).strip()
    parts = [part.strip() for part in re.split(r"\s*(?:,|;|\|)\s*", cleaned_location) if part.strip()]
    city = parts[0] if parts else None
    region = parts[1] if len(parts) >= 2 else None
    country = find_allowed_country_in_text(cleaned_location, profile)
    if country is None:
        country = normalize_country_name(parts[-1] if parts else "", profile)
    if country is None and profile.defaults.location_country:
        country = profile.defaults.location_country
    return city, region, country


def canonical_key(company: str, title: str, location: str, url: str) -> str:
    raw_str = f"{company}:{title}:{location}:{url}".lower()
    return sha256(raw_str.encode("utf-8")).hexdigest()


def content_hash(job: Any) -> str:
    title = getattr(job, "title_normalized", None) or getattr(job, "title_raw", "")
    location = getattr(job, "location_raw", None) or ""
    description = getattr(job, "description_text", "")
    raw_str = f"{title}\n{location}\n{description}"
    return sha256(raw_str.encode("utf-8")).hexdigest()
