from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yaml

from collector.profiles import load_active_profile, load_profiles
from shared.config import load_runtime_config

router = APIRouter(prefix="/settings", tags=["settings"])


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@router.get("")
def get_settings() -> dict:
    config = load_runtime_config()
    profiles = load_profiles(config.rules_path)
    profile = load_active_profile(config.rules_path, profile=config.active_profile or profiles.active_profile)
    return {
        "active_profile": profile.profile_name,
        "available_profiles": sorted(profiles.profiles),
        "role_families": [rule.value for rule in profile.normalization.role_taxonomy],
        "scoring_thresholds": {
            "shortlisted": float(profile.scoring.thresholds.shortlisted),
            "review": float(profile.scoring.thresholds.review),
            "maybe": float(profile.scoring.thresholds.maybe),
            "llm_analyze_threshold": float(profile.scoring.llm.analyze_threshold),
        },
        "scraper_defaults": {
            "providers": list(config.scraper_config.providers),
        },
        "llm": {
            "enabled": bool(config.llm_config.enabled),
            "provider": config.llm_config.provider,
            "model": config.llm_config.model,
        },
    }


class ProfilePayload(BaseModel):
    active_profile: str


class ThresholdsPayload(BaseModel):
    shortlisted: float
    review: float
    maybe: float
    llm_analyze_threshold: float


@router.patch("/profile")
def set_active_profile(payload: ProfilePayload) -> dict:
    config = load_runtime_config()
    profiles = load_profiles(config.rules_path)
    if payload.active_profile not in profiles.profiles:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown profile '{payload.active_profile}'. Available: {sorted(profiles.profiles)}",
        )
    runtime_path = config.root_dir / "config" / "runtime.yaml"
    data = _load_yaml(runtime_path)
    data["active_profile"] = payload.active_profile
    _save_yaml(runtime_path, data)
    return {"active_profile": payload.active_profile}


@router.patch("/thresholds")
def set_thresholds(payload: ThresholdsPayload) -> dict:
    config = load_runtime_config()
    profiles = load_profiles(config.rules_path)
    active = config.active_profile or profiles.active_profile
    rules_data = _load_yaml(config.rules_path)
    profile_data = rules_data.get("profiles", {}).get(active)
    if profile_data is None:
        raise HTTPException(status_code=404, detail=f"Profile '{active}' not found in rules file")
    profile_data.setdefault("scoring", {}).setdefault("thresholds", {})
    profile_data["scoring"]["thresholds"]["shortlisted"] = round(float(payload.shortlisted), 3)
    profile_data["scoring"]["thresholds"]["review"] = round(float(payload.review), 3)
    profile_data["scoring"]["thresholds"]["maybe"] = round(float(payload.maybe), 3)
    profile_data.setdefault("scoring", {}).setdefault("llm", {})
    profile_data["scoring"]["llm"]["analyze_threshold"] = round(float(payload.llm_analyze_threshold), 3)
    _save_yaml(config.rules_path, rules_data)
    return {
        "shortlisted": payload.shortlisted,
        "review": payload.review,
        "maybe": payload.maybe,
        "llm_analyze_threshold": payload.llm_analyze_threshold,
    }
