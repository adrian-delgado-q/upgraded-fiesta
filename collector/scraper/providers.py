from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from scrapy import Selector

from .html_extract import (
    extract_json_ld_job_posting,
    extract_label_value,
    extract_links_from_html,
    extract_location_text,
    extract_meta_content,
    extract_remote_scope_text,
    extract_tag_text,
    shorten_html,
    strip_tags,
)
from .models import ProviderConfig, ScrapedJobPosting


TRACKING_QUERY_PREFIXES = ("utm_", "gh_", "lever-", "source", "ref", "refer", "fbclid", "gclid")
IGNORED_QUERY_KEYS = {"fbclid", "gclid", "gh_jid", "gh_src", "lever-source", "source", "ref", "refer"}


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in IGNORED_QUERY_KEYS and not any(key.lower().startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    clean_query.sort()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(clean_query), ""))


PROVIDER_CONFIGS: dict[str, ProviderConfig] = {
    "ashby": ProviderConfig(
        name="ashby",
        host_patterns=("jobs.ashbyhq.com",),
        listing_markers=("/jobs/", "/jobs", "/careers"),
        job_markers=("/job/", "/jobs/", "/jobs"),
    ),
    "lever": ProviderConfig(
        name="lever",
        host_patterns=("jobs.lever.co",),
        listing_markers=("/company", "/jobs", "/careers"),
        job_markers=("/postings/", "/job/", "/jobs/"),
    ),
    "greenhouse": ProviderConfig(
        name="greenhouse",
        host_patterns=("boards.greenhouse.io", "job-boards.greenhouse.io"),
        listing_markers=("/embed/job_board", "/boards", "/jobs"),
        job_markers=("/jobs/", "/embed/job_app"),
    ),
}


class ATSProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def matches_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == pattern or host.endswith(f".{pattern}") for pattern in self.config.host_patterns)

    def company_slug(self, url: str) -> str:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        return parts[0] if parts else parsed.netloc.split(".")[0]

    def company_name(self, url: str, selector: Selector) -> str:
        return extract_meta_content(selector, "property", "og:site_name") or self.company_slug(url).replace("-", " ").title()

    def should_follow(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return any(marker in path for marker in self.config.listing_markers + self.config.job_markers)

    def is_listing_page(self, url: str, selector: Selector) -> bool:
        path = urlparse(url).path.lower()
        if any(marker in path for marker in self.config.listing_markers):
            return True
        provider_links = [link for link in self.extract_links(url, selector) if self.matches_url(link)]
        return len(provider_links) >= 3

    def extract_links(self, url: str, selector: Selector) -> list[str]:
        return [canonicalize_url(link) for link in extract_links_from_html(url, selector) if self.should_follow(link)]

    def extract_structured_title(self, selector: Selector) -> str:
        return (
            extract_meta_content(selector, "property", "og:title")
            or extract_meta_content(selector, "name", "twitter:title")
            or extract_tag_text(selector, "h1")
            or extract_tag_text(selector, "title")
        )

    def is_job_page(self, url: str, selector: Selector, title: str) -> bool:
        path = urlparse(url).path.lower()
        if any(marker in path for marker in self.config.job_markers):
            return True
        if extract_json_ld_job_posting(selector):
            return True
        return title.lower().strip() not in {"careers", "jobs", "open roles", "open positions"}

    def extract_job(self, url: str, source: str, discovered_from_url: str) -> ScrapedJobPosting | None:
        selector = Selector(text=source or "")
        if not (title := self.extract_structured_title(selector)):
            return None
        if not self.is_job_page(url, selector, title):
            return None
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        location = extract_location_text(selector)
        remote_status = extract_remote_scope_text(selector)
        return ScrapedJobPosting(
            provider=self.config.name,
            company_slug=self.company_slug(url),
            company_name=self.company_name(url, selector),
            job_url=canonicalize_url(url),
            job_title_raw=title,
            location=location,
            team=extract_label_value(selector, ("Team", "Department", "Function")),
            remote_status=remote_status,
            posting_id=self.extract_posting_id(url, source),
            archive_text=strip_tags(source),
            archive_html_snippet=shorten_html(source),
            description_html=source,
            discovered_from_url=discovered_from_url,
            fetched_at=fetched_at,
            metadata={
                "provider": self.config.name,
                "source_url": url,
                "raw_location_text": location,
                "raw_remote_status_text": remote_status,
            },
        )

    def extract_posting_id(self, url: str, source: str) -> str:
        del source
        path = urlparse(url).path.rstrip("/")
        return path.split("/")[-1] if path else ""


class AshbyProvider(ATSProvider):
    def __init__(self) -> None:
        super().__init__(PROVIDER_CONFIGS["ashby"])

    def extract_structured_title(self, selector: Selector) -> str:
        for label in ("Job Title", "Role"):
            if title := extract_label_value(selector, (label,)):
                return title
        return super().extract_structured_title(selector)

    def should_follow(self, url: str) -> bool:
        return self._looks_like_ashby_job_path(url) or super().should_follow(url)

    def is_job_page(self, url: str, selector: Selector, title: str) -> bool:
        return self._looks_like_ashby_job_path(url) or super().is_job_page(url, selector, title)

    def _looks_like_ashby_job_path(self, url: str) -> bool:
        parts = [part for part in urlparse(url).path.split("/") if part]
        if len(parts) != 2:
            return False
        return bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", parts[1].lower()))


class LeverProvider(ATSProvider):
    def __init__(self) -> None:
        super().__init__(PROVIDER_CONFIGS["lever"])

    def company_slug(self, url: str) -> str:
        parts = [part for part in urlparse(url).path.split("/") if part]
        return parts[0] if parts else super().company_slug(url)

    def is_job_page(self, url: str, selector: Selector, title: str) -> bool:
        return self._looks_like_lever_job_path(url) or super().is_job_page(url, selector, title)

    def _looks_like_lever_job_path(self, url: str) -> bool:
        parts = [part for part in urlparse(url).path.split("/") if part]
        return len(parts) == 2 and all(parts) and all("/" not in part for part in parts)


class GreenhouseProvider(ATSProvider):
    def __init__(self) -> None:
        super().__init__(PROVIDER_CONFIGS["greenhouse"])

    def company_slug(self, url: str) -> str:
        parts = [part for part in urlparse(url).path.split("/") if part]
        return parts[0] if parts else super().company_slug(url)


def build_providers(enabled: list[str]) -> list[ATSProvider]:
    available = {"ashby": AshbyProvider, "lever": LeverProvider, "greenhouse": GreenhouseProvider}
    invalid = set(enabled) - set(available)
    if invalid:
        raise ValueError(f"Unsupported provider(s): {', '.join(sorted(invalid))}")
    return [available[name]() for name in enabled]
