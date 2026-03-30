from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from shared.config import load_runtime_config
from shared.repository import Repository

from .orchestrator import CollectorPipeline
from .profiles import extract_search_terms, load_active_profile
from .scraper.errors import ScrapeError
from .scraper.spider import build_run_config, format_discovery_success_lines, scrape_jobs


logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format="%(levelname)s %(name)s: %(message)s")
    if resolved_level > logging.DEBUG:
        logging.getLogger("scrapy").setLevel(logging.WARNING)
        logging.getLogger("py.warnings").setLevel(logging.ERROR)


def run_scrape_command(args: argparse.Namespace) -> int:
    config = load_runtime_config()
    profile = load_active_profile(args.rules or config.rules_path, profile=args.profile or config.active_profile)
    repository = Repository(config.database_path)
    if not args.terms:
        args.terms = extract_search_terms(profile)
    args.max_pages = args.max_pages or config.scraper_config.max_pages
    args.search_results_per_query = args.search_results_per_query or config.scraper_config.search_results_per_query
    pipeline = CollectorPipeline(repository, profile=profile)
    run_config = build_run_config(args, profile, config.scraper_config)
    logger.info(
        "Starting scrape with %d query term(s), providers=%s, locations=%s",
        len(run_config.query_terms),
        ",".join(run_config.enabled_providers),
        ",".join(run_config.locations) or "<none>",
    )
    scraped_jobs, report = scrape_jobs(run_config, profile, scraper_config=config.scraper_config)
    logger.info(
        "Discovery complete: backend=%s candidates=%d raw=%d",
        report.backend_name or "<none>",
        report.total_kept_results,
        report.total_raw_results,
    )
    for line in format_discovery_success_lines(report):
        logger.info(line)
    logger.info("Crawl complete: scraped %d job(s)", len(scraped_jobs))
    imported = pipeline.import_scraped_jobs(scraped_jobs)
    logger.info("Import complete: saved %d job record(s)", len(imported))
    print(json.dumps(imported, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collector CLI")
    parser.add_argument("command", choices=["init-db", "scrape", "status"])
    parser.add_argument("--rules", default=None)
    parser.add_argument("--terms", nargs="*")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--providers")
    parser.add_argument("--locations", nargs="*")
    parser.add_argument("--seed-url", action="append")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-pages-per-company", type=int)
    parser.add_argument("--max-depth", type=int)
    parser.add_argument("--search-results-per-query", type=int)
    parser.add_argument("--log-level")
    args = parser.parse_args(argv)
    config = load_runtime_config()
    configure_logging(args.log_level or config.log_level)
    repository = Repository(config.database_path)
    if args.command == "init-db":
        repository.init_db()
        print(json.dumps({"database_path": str(config.database_path), "initialized": True}, indent=2))
        return 0
    if args.command == "scrape":
        try:
            return run_scrape_command(args)
        except ScrapeError as exc:
            print(str(exc), file=sys.stderr)
            return 2 if args.terms and "required when using --terms" in str(exc) else 1
    if args.command == "status":
        llm_env_name = config.llm_config.api_key_env
        llm_api_key = config.llm_config.api_key
        scraper_env_name = config.scraper_config.api_key_env
        scraper_api_key = config.scraper_config.api_key
        status = {
            "database_path": str(config.database_path),
            "artifacts_dir": str(config.artifacts_dir),
            "rules_path": str(config.rules_path),
            "active_profile": args.profile or config.active_profile,
            "scraper": {
                "providers": list(config.scraper_config.providers),
                "defaults": {
                    "max_pages": int(config.scraper_config.max_pages),
                    "max_pages_per_company": int(config.scraper_config.max_pages_per_company),
                    "max_depth": int(config.scraper_config.max_depth),
                    "search_results_per_query": int(config.scraper_config.search_results_per_query),
                },
                "search_api_configured": bool(scraper_api_key or os.environ.get(scraper_env_name, "")),
                "search_api_env": scraper_env_name,
            },
            "jobs_total": repository.count_jobs(),
            "jobs_by_source": repository.count_jobs_by_source(),
            "jobs_by_triage_status": repository.count_jobs_by_triage_status(),
            "packages_by_status": repository.count_packages_by_status(),
            "llm": {
                "enabled": bool(config.llm_config.enabled),
                "provider": config.llm_config.provider,
                "model": config.llm_config.model,
                "api_key_configured": bool(llm_api_key or os.environ.get(llm_env_name, "")),
                "api_key_env": llm_env_name,
            },
        }
        print(json.dumps(status, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
