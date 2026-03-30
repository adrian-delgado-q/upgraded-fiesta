from __future__ import annotations

from functools import lru_cache

from collector.orchestrator import CollectorPipeline
from collector.profiles import load_active_profile
from shared.config import load_runtime_config
from shared.repository import Repository


@lru_cache(maxsize=1)
def get_repository() -> Repository:
    config = load_runtime_config()
    return Repository(config.database_path)


@lru_cache(maxsize=1)
def get_collector() -> CollectorPipeline:
    config = load_runtime_config()
    return CollectorPipeline(
        get_repository(),
        profile=load_active_profile(config.rules_path, profile=config.active_profile),
    )
