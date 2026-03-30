from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.profiles import load_active_profile, load_profiles
from shared.config import load_runtime_config


def main() -> int:
    config = load_runtime_config()
    profiles = load_profiles(config.rules_path)
    profile = load_active_profile(config.rules_path, profile=config.active_profile or profiles.active_profile)
    payload = {
        "database_path": str(config.database_path),
        "rules_path": str(config.rules_path),
        "active_profile": profile.profile_name,
        "available_profiles": sorted(profiles.profiles),
        "role_families": [rule.value for rule in profile.normalization.role_taxonomy],
        "scoring_categories": sorted(profile.scoring.categories),
        "scraper_defaults": {
            "providers": list(config.scraper_config.providers),
            "max_pages": int(config.scraper_config.max_pages),
            "max_pages_per_company": int(config.scraper_config.max_pages_per_company),
            "max_depth": int(config.scraper_config.max_depth),
            "search_results_per_query": int(config.scraper_config.search_results_per_query),
        },
        "llm": {
            "enabled": bool(config.llm_config.enabled),
            "provider": config.llm_config.provider,
            "model": config.llm_config.model,
            "api_key_env": config.llm_config.api_key_env,
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
