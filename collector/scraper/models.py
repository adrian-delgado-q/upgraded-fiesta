from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.config import MAX_SEARCH_RESULTS_PER_QUERY
from shared.models import NormalizedJob

from ..normalization import (
    canonical_key,
    find_allowed_country_in_text,
    infer_role_family,
    infer_seniority,
    infer_work_mode,
    normalize_location,
    normalize_title,
)
from ..profiles import ProfileConfig


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    host_patterns: tuple[str, ...]
    listing_markers: tuple[str, ...]
    job_markers: tuple[str, ...]


@dataclass
class ScrapeRunConfig:
    query_terms: list[str]
    enabled_providers: list[str]
    locations: list[str] = field(default_factory=list)
    max_pages: int = 150
    max_pages_per_company: int = 40
    max_depth: int = 2
    search_results_per_query: int = 50
    log_level: str = "INFO"
    seed_urls: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not 1 <= self.search_results_per_query <= MAX_SEARCH_RESULTS_PER_QUERY:
            raise ValueError(
                f"search_results_per_query must be between 1 and {MAX_SEARCH_RESULTS_PER_QUERY}."
            )


@dataclass
class ScrapedJobPosting:
    provider: str
    company_slug: str
    company_name: str
    job_url: str
    job_title_raw: str
    location: str
    team: str
    remote_status: str
    posting_id: str
    archive_text: str
    archive_html_snippet: str
    description_html: str
    discovered_from_url: str
    fetched_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_normalized_job(self, profile: ProfileConfig) -> NormalizedJob:
        title_normalized = normalize_title(self.job_title_raw, profile)
        city, region, country = normalize_location(self.location, profile)
        if country is None:
            country = find_allowed_country_in_text(" ".join(part for part in (self.location, self.remote_status) if part), profile)
        work_mode = infer_work_mode(" ".join(part for part in (self.location, self.remote_status) if part), profile)
        job_metadata = {
            "scrape": {
                "provider": self.provider,
                "company_slug": self.company_slug,
                "team": self.team,
                "remote_status": self.remote_status,
                "posting_id": self.posting_id,
                "archive_html_snippet": self.archive_html_snippet,
                "discovered_from_url": self.discovered_from_url,
                "fetched_at": self.fetched_at,
            },
            "raw_posting": self.metadata,
        }
        description = self.archive_text
        role_family = infer_role_family(f"{title_normalized} {description}", profile)
        seniority = infer_seniority(f"{title_normalized} {description}", profile)
        return NormalizedJob(
            source=self.provider,
            source_job_id=self.posting_id or None,
            company=self.company_name.strip() or self.company_slug.replace("-", " ").title(),
            title_raw=self.job_title_raw.strip(),
            title_normalized=title_normalized,
            role_family=role_family,
            seniority=seniority,
            location_raw=self.location or None,
            location_city=city,
            location_region=region,
            location_country=country,
            work_mode=work_mode,
            employment_type=None,
            salary_min_cad=None,
            salary_max_cad=None,
            salary_currency=None,
            salary_period=None,
            url=self.job_url,
            posted_at=None,
            canonical_key=canonical_key(
                self.company_name or self.company_slug,
                title_normalized,
                city or self.location or "",
                self.job_url,
            ),
            description_text=self.archive_text,
            description_html=self.description_html or None,
            metadata=job_metadata,
            discovered_at=self.fetched_at,
            last_seen_at=self.fetched_at,
        )
