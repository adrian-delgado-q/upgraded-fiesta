from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import yaml


MAX_SEARCH_RESULTS_PER_QUERY = 100


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class WorkerConfig(ConfigModel):
    poll_seconds: int = 10
    log_idle_cycles: int = 6


class ScraperSettings(ConfigModel):
    api_key: str = ""
    api_key_env: str = "SERP_API_TOKEN"
    providers: list[str] = Field(default_factory=lambda: ["ashby", "lever", "greenhouse"])
    max_pages: int = 150
    max_pages_per_company: int = 40
    max_depth: int = 2
    search_results_per_query: int = Field(default=50, ge=1, le=MAX_SEARCH_RESULTS_PER_QUERY)
    log_level: str = "INFO"


class LLMSettings(ConfigModel):
    provider: str = "deepseek"
    api_key: str = ""
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-reasoner"
    prompt_version: str = "framework-v1"
    enabled: bool = True
    timeout_seconds: int = 45
    max_concurrent_requests: int = 5


class RuntimeOptions(ConfigModel):
    database_path: str = "storage/job_system.db"
    artifacts_dir: str = "storage/artifacts"
    rules_path: str = "config/rules.yaml"
    active_profile: str = ""
    pandoc_binary: str = "pandoc"
    log_level: str = "INFO"
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)


@dataclass(slots=True)
class RuntimeConfig:
    root_dir: Path
    database_path: Path
    artifacts_dir: Path
    rules_path: Path
    active_profile: str | None
    pandoc_binary: str
    log_level: str
    worker_poll_seconds: int
    worker_log_idle_cycles: int
    scraper_config: ScraperSettings = field(default_factory=ScraperSettings)
    llm_config: LLMSettings = field(default_factory=LLMSettings)
    runtime_options: RuntimeOptions = field(default_factory=RuntimeOptions)


def load_runtime_config(root_dir: str | Path | None = None) -> RuntimeConfig:
    repo_root = Path(root_dir or Path(__file__).resolve().parent.parent)
    config_dir = repo_root / "config"
    runtime_options = RuntimeOptions.model_validate(_load_yaml(config_dir / "runtime.yaml"))
    return RuntimeConfig(
        root_dir=repo_root,
        database_path=(repo_root / runtime_options.database_path).resolve(),
        artifacts_dir=(repo_root / runtime_options.artifacts_dir).resolve(),
        rules_path=(repo_root / runtime_options.rules_path).resolve(),
        active_profile=runtime_options.active_profile.strip() or None,
        pandoc_binary=os.environ.get("PANDOC_BINARY", runtime_options.pandoc_binary),
        log_level=os.environ.get("JOB_HUNTER_LOG_LEVEL", runtime_options.log_level).upper(),
        worker_poll_seconds=int(os.environ.get("JOB_HUNTER_WORKER_POLL_SECONDS", runtime_options.worker.poll_seconds)),
        worker_log_idle_cycles=int(os.environ.get("JOB_HUNTER_WORKER_LOG_IDLE_CYCLES", runtime_options.worker.log_idle_cycles)),
        scraper_config=runtime_options.scraper,
        llm_config=runtime_options.llm,
        runtime_options=runtime_options,
    )
