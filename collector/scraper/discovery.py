from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx

from shared.config import MAX_SEARCH_RESULTS_PER_QUERY, ScraperSettings

from ..profiles import ProfileConfig
from .errors import ScrapeError
from .providers import ATSProvider, canonicalize_url


@dataclass
class DiscoveryQueryStats:
    query: str
    pages_fetched: int = 0
    raw_results: int = 0
    kept_results: int = 0
    duplicate_results: int = 0
    unsupported_results: int = 0
    location_filtered_results: int = 0
    error_message: str = ""


@dataclass
class DiscoveryReport:
    queries: list[DiscoveryQueryStats] = field(default_factory=list)
    auth_succeeded: bool = False
    backend_name: str = ""

    @property
    def total_raw_results(self) -> int:
        return sum(item.raw_results for item in self.queries)

    @property
    def total_kept_results(self) -> int:
        return sum(item.kept_results for item in self.queries)

    @property
    def total_duplicate_results(self) -> int:
        return sum(item.duplicate_results for item in self.queries)

    @property
    def total_unsupported_results(self) -> int:
        return sum(item.unsupported_results for item in self.queries)

    @property
    def total_pages_fetched(self) -> int:
        return sum(item.pages_fetched for item in self.queries)

    @property
    def total_location_filtered_results(self) -> int:
        return sum(item.location_filtered_results for item in self.queries)

    def find_query(self, query: str) -> DiscoveryQueryStats | None:
        for item in self.queries:
            if item.query == query:
                return item
        return None

    def add_location_filtered_result(self, query: str) -> None:
        if stats := self.find_query(query):
            stats.location_filtered_results += 1


class SearchBackend:
    name = "search"

    def search_page(self, query: str, start: int, page_size: int) -> tuple[list[str], bool]:
        raise NotImplementedError


class SerpApiSearchBackend(SearchBackend):
    name = "serpapi"
    endpoint = "https://serpapi.com/search.json"
    default_page_size = 10

    def __init__(self, api_token: str, engine: str = "google", timeout_seconds: int = 20) -> None:
        self.api_token = api_token
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self.cache: dict[tuple[str, int, int], tuple[list[str], bool]] = {}
        self.client = httpx.Client(timeout=self.timeout_seconds, headers={"User-Agent": "Mozilla/5.0 upgraded-fiesta"})

    def search_page(self, query: str, start: int, page_size: int) -> tuple[list[str], bool]:
        cache_key = (query, start, page_size)
        if cache_key in self.cache:
            return self.cache[cache_key]
        try:
            response = self.client.get(
                self.endpoint,
                params={
                    "engine": self.engine,
                    "q": query,
                    "num": page_size,
                    "start": start,
                    "api_key": self.api_token,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ScrapeError(f"SerpAPI HTTP {exc.response.status_code}: {exc.response.text or exc}") from exc
        except httpx.HTTPError as exc:
            raise ScrapeError(f"SerpAPI network error: {exc}") from exc
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ScrapeError("SerpAPI returned invalid JSON") from exc
        if "error" in payload:
            error_message = str(payload["error"])
            if self.is_empty_result_error(error_message):
                result = ([], True)
                self.cache[cache_key] = result
                return result
            raise ScrapeError(f"SerpAPI error: {error_message}")
        urls = [item["link"] for item in payload.get("organic_results", []) if item.get("link")]
        result = (urls[:page_size], True)
        self.cache[cache_key] = result
        return result

    @staticmethod
    def is_empty_result_error(message: str) -> bool:
        normalized = message.lower()
        return "hasn't returned any results" in normalized or "no results" in normalized


class SearchDiscovery:
    def __init__(self, providers: list[ATSProvider], backend: SearchBackend, location_overlays: list[str] | None = None) -> None:
        self.providers = list(providers)
        self.backend = backend
        self.location_overlays = list(location_overlays or [])

    def build_queries(self, terms: list[str]) -> list[str]:
        geo_clause = " OR ".join(f'"{item}"' for item in self.location_overlays) or '"Remote"'
        unique_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in terms:
            cleaned = str(term).strip()
            lowered = cleaned.lower()
            if cleaned and lowered not in seen_terms:
                seen_terms.add(lowered)
                unique_terms.append(cleaned)
        queries: list[str] = []
        seen_queries: set[str] = set()
        for provider in self.providers:
            for host in provider.config.host_patterns:
                for term in unique_terms:
                    query = f'site:{host} "{term}" ({geo_clause})'
                    if query not in seen_queries:
                        seen_queries.add(query)
                        queries.append(query)
        return queries

    def discover(self, terms: list[str], max_results: int, max_candidates: int | None = None) -> tuple[list[tuple[str, str]], DiscoveryReport]:
        capped_results = max(1, min(int(max_results), MAX_SEARCH_RESULTS_PER_QUERY))
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        report = DiscoveryReport(backend_name=self.backend.name)
        for query in self.build_queries(terms):
            stats = DiscoveryQueryStats(query=query)
            report.queries.append(stats)
            start = 0
            page_size = min(getattr(self.backend, "default_page_size", capped_results), capped_results)
            while stats.raw_results < capped_results:
                remaining = capped_results - stats.raw_results
                try:
                    raw_urls, auth_succeeded = self.backend.search_page(query, start=start, page_size=min(page_size, remaining))
                except ScrapeError as exc:
                    stats.error_message = str(exc)
                    break
                report.auth_succeeded = report.auth_succeeded or auth_succeeded
                stats.pages_fetched += 1
                stats.raw_results += len(raw_urls)
                new_in_page = 0
                for url in raw_urls:
                    canonical = canonicalize_url(url)
                    if canonical in seen:
                        stats.duplicate_results += 1
                        continue
                    if not any(provider.matches_url(canonical) for provider in self.providers):
                        stats.unsupported_results += 1
                        continue
                    seen.add(canonical)
                    stats.kept_results += 1
                    new_in_page += 1
                    candidates.append((query, canonical))
                    if max_candidates is not None and len(candidates) >= max_candidates:
                        return candidates, report
                if not raw_urls or len(raw_urls) < min(page_size, remaining) or new_in_page == 0:
                    break
                start += len(raw_urls)
        return candidates, report


def build_location_overlays(profile: ProfileConfig) -> list[str]:
    overlays: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        cleaned = str(item).strip()
        lowered = cleaned.lower()
        if cleaned and lowered not in seen:
            seen.add(lowered)
            overlays.append(cleaned)

    for country in profile.normalization.locations.allowed_countries:
        add(profile.normalization.locations.country_aliases.get(country, country))
    for location in [*profile.normalization.locations.search_locations, *profile.search.locations]:
        add(location)
    for country in profile.normalization.locations.allowed_countries:
        add(f"Remote {profile.normalization.locations.country_aliases.get(country, country)}")
    return overlays


def discover_candidates(run_config, providers: list[ATSProvider], profile: ProfileConfig, backend: SearchBackend | None = None) -> tuple[list[tuple[str, str]], DiscoveryReport]:
    discovered = [(f"seed:{url}", canonicalize_url(url)) for url in run_config.seed_urls]
    report = DiscoveryReport(backend_name=backend.name if backend else "", auth_succeeded=not run_config.query_terms)
    if run_config.query_terms:
        if backend is None:
            raise ScrapeError("Search backend is required when query terms are provided.")
        discovery = SearchDiscovery(providers, backend=backend, location_overlays=build_location_overlays(profile))
        search_results, report = discovery.discover(
            run_config.query_terms,
            max_results=run_config.search_results_per_query,
            max_candidates=run_config.max_pages,
        )
        discovered.extend(search_results)
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source_query, url in discovered:
        canonical = canonicalize_url(url)
        if canonical in seen or not any(provider.matches_url(canonical) for provider in providers):
            continue
        seen.add(canonical)
        deduped.append((source_query, canonical))
    return deduped, report


def get_serpapi_backend(config: ScraperSettings) -> SerpApiSearchBackend:
    api_token = (config.api_key or os.environ.get(config.api_key_env, "")).strip()
    if not api_token:
        raise ScrapeError(f"{config.api_key_env} is required when using --terms.")
    return SerpApiSearchBackend(api_token)
