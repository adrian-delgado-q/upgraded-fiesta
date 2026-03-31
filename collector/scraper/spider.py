from __future__ import annotations

import argparse
import logging
from dataclasses import asdict
from urllib.parse import urlparse
from typing import Any

from shared.config import ScraperSettings

from ..normalization import location_matches_allowed_scope
from ..profiles import ProfileConfig
from .discovery import DiscoveryReport, SearchBackend, discover_candidates, get_serpapi_backend
from .errors import ScrapeError
from .models import ScrapeRunConfig, ScrapedJobPosting
from .providers import ATSProvider, PROVIDER_CONFIGS, build_providers, canonicalize_url


logger = logging.getLogger(__name__)


def build_run_config(args: argparse.Namespace, profile: ProfileConfig, defaults: ScraperSettings | None = None) -> ScrapeRunConfig:
    defaults = defaults or ScraperSettings()
    providers = (
        [item.strip() for item in args.providers.split(",") if item.strip()]
        if getattr(args, "providers", None)
        else list(profile.search.providers or defaults.providers)
    )
    return ScrapeRunConfig(
        query_terms=list(getattr(args, "terms", None) or profile.search.query_terms),
        enabled_providers=providers,
        locations=list(getattr(args, "locations", None) or []),
        max_pages=int(getattr(args, "max_pages", None) or defaults.max_pages),
        max_pages_per_company=int(getattr(args, "max_pages_per_company", None) or defaults.max_pages_per_company),
        max_depth=int(getattr(args, "max_depth", None) or defaults.max_depth),
        search_results_per_query=int(getattr(args, "search_results_per_query", None) or defaults.search_results_per_query),
        log_level=str(getattr(args, "log_level", None) or defaults.log_level),
        seed_urls=list(getattr(args, "seed_url", None) or []),
    )


def validate_run_config(run_config: ScrapeRunConfig) -> None:
    try:
        run_config.validate()
    except ValueError as exc:
        raise ScrapeError(str(exc)) from exc
    if not run_config.enabled_providers:
        raise ScrapeError("At least one provider must be specified. Allowed: ashby, lever, greenhouse.")
    invalid = [provider for provider in run_config.enabled_providers if provider not in PROVIDER_CONFIGS]
    if invalid:
        allowed = ", ".join(sorted(PROVIDER_CONFIGS))
        raise ScrapeError(f"Unsupported provider(s): {', '.join(invalid)}. Allowed: {allowed}.")


def format_discovery_failure(run_config: ScrapeRunConfig, report: DiscoveryReport) -> str:
    lines = [
        "No ATS candidate URLs discovered.",
        f"Providers: {', '.join(run_config.enabled_providers)}",
        f"Search backend: {report.backend_name or 'none'}",
        f"Search API authentication succeeded: {'yes' if report.auth_succeeded else 'no'}",
    ]
    if report.queries:
        lines.append("Queries tried:")
        for stats in report.queries:
            line = (
                f"  {stats.query} -> pages={stats.pages_fetched}, raw={stats.raw_results}, kept={stats.kept_results}, "
                f"duplicates={stats.duplicate_results}, unsupported={stats.unsupported_results}, "
                f"location_filtered={stats.location_filtered_results}"
            )
            if stats.error_message:
                line += f", error={stats.error_message}"
            lines.append(line)
    lines.append(
        f"Totals: pages={report.total_pages_fetched}, raw={report.total_raw_results}, kept={report.total_kept_results}, "
        f"duplicates={report.total_duplicate_results}, unsupported={report.total_unsupported_results}, "
        f"location_filtered={report.total_location_filtered_results}"
    )
    return "\n".join(lines)


def is_location_match(job: ScrapedJobPosting, run_config: ScrapeRunConfig, profile: ProfileConfig) -> bool:
    del run_config
    if not location_matches_allowed_scope(job.location, job.remote_status, profile):
        return False
    return True


def filter_scraped_jobs(
    jobs: list[ScrapedJobPosting],
    run_config: ScrapeRunConfig,
    profile: ProfileConfig,
    report: DiscoveryReport | None = None,
) -> list[ScrapedJobPosting]:
    filtered: list[ScrapedJobPosting] = []
    seen_job_urls: set[str] = set()
    for job in jobs:
        if job.job_url in seen_job_urls:
            continue
        if not is_location_match(job, run_config, profile):
            source_query = str(job.metadata.get("source_query") or "")
            if report and source_query:
                report.add_location_filtered_result(source_query)
            continue
        seen_job_urls.add(job.job_url)
        filtered.append(job)
    return filtered


def format_discovery_success_lines(report: DiscoveryReport) -> list[str]:
    lines = [
        (
            "Discovery diagnostics: "
            f"backend={report.backend_name or '<none>'} pages={report.total_pages_fetched} "
            f"raw={report.total_raw_results} kept={report.total_kept_results} "
            f"duplicates={report.total_duplicate_results} unsupported={report.total_unsupported_results} "
            f"location_filtered={report.total_location_filtered_results}"
        )
    ]
    for stats in report.queries:
        line = (
            f"Query {stats.query} -> pages={stats.pages_fetched} raw={stats.raw_results} "
            f"kept={stats.kept_results} duplicates={stats.duplicate_results} "
            f"unsupported={stats.unsupported_results} location_filtered={stats.location_filtered_results}"
        )
        if stats.error_message:
            line += f" error={stats.error_message}"
        lines.append(line)
    return lines


def get_spider_class() -> type:
    import scrapy

    class ATSJobSpider(scrapy.Spider):
        name = "ats_job_spider"

        def __init__(self, providers: list[ATSProvider], run_config: ScrapeRunConfig, discovered: list[tuple[str, str]], *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.providers = list(providers)
            self.provider_by_host = {host: provider for provider in providers for host in provider.config.host_patterns}
            self.run_config = run_config
            self.discovered = list(discovered)
            self.page_count = 0
            self.page_count_by_company: dict[tuple[str, str], int] = {}

        def start_requests(self):
            for source_query, url in self.discovered:
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    meta={
                        "source_query": source_query,
                        "seed_url": url,
                        "provider_name": self.resolve_provider_name(url),
                        "depth_level": 0,
                    },
                )

        def resolve_provider_name(self, url: str) -> str:
            host = urlparse(url).netloc.lower()
            for pattern, provider in self.provider_by_host.items():
                if host == pattern or host.endswith(f".{pattern}"):
                    return provider.config.name
            return ""

        def resolve_provider(self, url: str, hinted_provider_name: str = "") -> ATSProvider | None:
            if provider_name := self.resolve_provider_name(url):
                return next((p for p in self.providers if p.config.name == provider_name), None)
            if hinted_provider_name:
                return next((p for p in self.providers if p.config.name == hinted_provider_name), None)
            return None

        def parse(self, response):
            url = canonicalize_url(response.url)
            provider = self.resolve_provider(url, response.meta.get("provider_name", ""))
            if provider is None:
                return
            company_key = (provider.config.name, provider.company_slug(url))
            if self.page_count >= self.run_config.max_pages:
                self.crawler.engine.close_spider(self, "max_pages_reached")
                return
            if self.page_count_by_company.get(company_key, 0) >= self.run_config.max_pages_per_company:
                return
            self.page_count += 1
            self.page_count_by_company[company_key] = self.page_count_by_company.get(company_key, 0) + 1
            source = response.text
            job = provider.extract_job(url, source, response.meta.get("seed_url", ""))
            if job:
                item = asdict(job)
                item.setdefault("metadata", {})
                item["metadata"]["source_query"] = response.meta.get("source_query", "")
                yield item
            depth_level = response.meta.get("depth_level", 0)
            if depth_level >= self.run_config.max_depth:
                return
            from scrapy import Selector

            selector = Selector(text=source or "")
            if not provider.is_listing_page(url, selector):
                return
            for link in provider.extract_links(url, selector):
                yield scrapy.Request(
                    url=link,
                    callback=self.parse,
                    meta={
                        "source_query": response.meta.get("source_query", ""),
                        "seed_url": response.meta.get("seed_url", url),
                        "provider_name": provider.config.name,
                        "depth_level": depth_level + 1,
                    },
                )

    return ATSJobSpider


def crawl_jobs(run_config: ScrapeRunConfig, providers: list[ATSProvider], discovered: list[tuple[str, str]]) -> list[ScrapedJobPosting]:
    try:
        from scrapy.crawler import CrawlerProcess
    except ImportError as exc:
        raise ScrapeError("Scrapy is required to run the crawler. Install it with `pip install scrapy`.") from exc
    items: list[dict[str, Any]] = []

    class CollectItemsPipeline:
        def process_item(self, item, spider):
            del spider
            items.append(dict(item))
            return item

    spider_cls = get_spider_class()
    process = CrawlerProcess(
        settings={
            "LOG_LEVEL": "DEBUG" if run_config.log_level.upper() == "DEBUG" else "WARNING",
            "CLOSESPIDER_PAGECOUNT": run_config.max_pages,
            "DOWNLOAD_TIMEOUT": 20,
            "ROBOTSTXT_OBEY": False,
            "ITEM_PIPELINES": {CollectItemsPipeline: 100},
        }
    )
    process.crawl(spider_cls, providers=providers, run_config=run_config, discovered=discovered)
    process.start()
    return [ScrapedJobPosting(**item) for item in items]


def scrape_jobs(
    run_config: ScrapeRunConfig,
    profile: ProfileConfig,
    scraper_config: ScraperSettings | None = None,
    backend: SearchBackend | None = None,
    crawl_runner: Any | None = None,
) -> tuple[list[ScrapedJobPosting], DiscoveryReport]:
    scraper_config = scraper_config or ScraperSettings()
    validate_run_config(run_config)
    providers = build_providers(run_config.enabled_providers)
    if not run_config.query_terms and not run_config.seed_urls:
        raise ScrapeError("Provide --terms for discovery or at least one --seed-url.")
    if run_config.query_terms and backend is None:
        backend = get_serpapi_backend(scraper_config)
    discovered, report = discover_candidates(run_config, providers, profile, backend=backend)
    if not discovered:
        raise ScrapeError(format_discovery_failure(run_config, report))
    crawl_runner = crawl_runner or crawl_jobs
    scraped_jobs = crawl_runner(run_config, providers, discovered)
    return filter_scraped_jobs(scraped_jobs, run_config, profile, report=report), report
