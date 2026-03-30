import sys
import types
import unittest


if "scrapy" not in sys.modules:
    scrapy_stub = types.ModuleType("scrapy")

    class Selector:  # pragma: no cover - test stub only
        def __init__(self, text: str = "") -> None:
            self.text = text

    scrapy_stub.Selector = Selector
    sys.modules["scrapy"] = scrapy_stub


from collector.profiles import load_active_profile
from collector.scraper.discovery import (
    DiscoveryQueryStats,
    DiscoveryReport,
    SearchBackend,
    SearchDiscovery,
    build_location_overlays,
)
from collector.scraper.models import ScrapeRunConfig, ScrapedJobPosting
from collector.scraper.providers import build_providers
from collector.scraper.spider import filter_scraped_jobs, format_discovery_success_lines, scrape_jobs


class FakeBackend(SearchBackend):
    name = "fake"
    default_page_size = 10

    def __init__(self, pages: dict[tuple[str, int], list[str]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, int, int]] = []

    def search_page(self, query: str, start: int, page_size: int) -> tuple[list[str], bool]:
        self.calls.append((query, start, page_size))
        return list(self.pages.get((query, start), []))[:page_size], True


class ScraperRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_active_profile("config/rules.yaml", profile="software_platform")

    def test_build_queries_includes_all_provider_host_patterns(self) -> None:
        providers = build_providers(["greenhouse"])
        discovery = SearchDiscovery(providers, backend=FakeBackend({}), location_overlays=["Canada"])

        queries = discovery.build_queries(["site reliability engineer"])

        self.assertEqual(
            queries,
            [
                'site:boards.greenhouse.io "site reliability engineer" ("Canada")',
                'site:job-boards.greenhouse.io "site reliability engineer" ("Canada")',
            ],
        )

    def test_paginated_discovery_aggregates_results_and_stats(self) -> None:
        providers = build_providers(["ashby"])
        query = 'site:jobs.ashbyhq.com "site reliability engineer" ("Canada")'
        backend = FakeBackend(
            {
                (query, 0): [f"https://jobs.ashbyhq.com/company/{index:08x}-0000-4000-8000-000000000000" for index in range(10)],
                (query, 10): [
                    "https://jobs.ashbyhq.com/company/00000000-0000-4000-8000-000000000000",
                    "https://example.com/not-supported",
                    *[
                        f"https://jobs.ashbyhq.com/company/{index:08x}-0000-4000-8000-000000000000"
                        for index in range(10, 18)
                    ],
                ],
                (query, 20): [
                    f"https://jobs.ashbyhq.com/company/{index:08x}-0000-4000-8000-000000000000"
                    for index in range(18, 23)
                ],
            }
        )
        discovery = SearchDiscovery(providers, backend=backend, location_overlays=["Canada"])

        candidates, report = discovery.discover(["site reliability engineer"], max_results=25)

        self.assertEqual(len(candidates), 23)
        self.assertEqual(report.total_pages_fetched, 3)
        self.assertEqual(report.total_raw_results, 25)
        self.assertEqual(report.total_kept_results, 23)
        self.assertEqual(report.total_duplicate_results, 1)
        self.assertEqual(report.total_unsupported_results, 1)
        self.assertEqual(backend.calls, [(query, 0, 10), (query, 10, 10), (query, 20, 5)])

    def test_filter_scraped_jobs_uses_allowed_country_only(self) -> None:
        run_config = ScrapeRunConfig(query_terms=["site reliability engineer"], enabled_providers=["ashby"], locations=["Toronto"])
        report = DiscoveryReport(queries=[DiscoveryQueryStats(query="query-1")], backend_name="fake")
        jobs = [
            ScrapedJobPosting(
                provider="ashby",
                company_slug="canada-role",
                company_name="Canada Role",
                job_url="https://jobs.ashbyhq.com/company/11111111-1111-4111-8111-111111111111",
                job_title_raw="Site Reliability Engineer",
                location="Calgary, Alberta, Canada",
                team="Infra",
                remote_status="Hybrid",
                posting_id="111",
                archive_text="",
                archive_html_snippet="",
                description_html="",
                discovered_from_url="https://jobs.ashbyhq.com/company/11111111-1111-4111-8111-111111111111",
                fetched_at="2026-03-29T00:00:00+00:00",
                metadata={"source_query": "query-1"},
            ),
            ScrapedJobPosting(
                provider="ashby",
                company_slug="germany-role",
                company_name="Germany Role",
                job_url="https://jobs.ashbyhq.com/company/22222222-2222-4222-8222-222222222222",
                job_title_raw="Site Reliability Engineer",
                location="Berlin, Germany",
                team="Infra",
                remote_status="Remote",
                posting_id="222",
                archive_text="",
                archive_html_snippet="",
                description_html="",
                discovered_from_url="https://jobs.ashbyhq.com/company/22222222-2222-4222-8222-222222222222",
                fetched_at="2026-03-29T00:00:00+00:00",
                metadata={"source_query": "query-1"},
            ),
        ]

        filtered = filter_scraped_jobs(jobs, run_config, self.profile, report=report)

        self.assertEqual([job.company_slug for job in filtered], ["canada-role"])
        self.assertEqual(report.total_location_filtered_results, 1)

    def test_scrape_jobs_reports_location_filtered_counts(self) -> None:
        query = SearchDiscovery(
            build_providers(["ashby"]),
            backend=FakeBackend({}),
            location_overlays=build_location_overlays(self.profile),
        ).build_queries(["site reliability engineer"])[0]
        run_config = ScrapeRunConfig(
            query_terms=["site reliability engineer"],
            enabled_providers=["ashby"],
            locations=["Toronto"],
            search_results_per_query=20,
        )
        backend = FakeBackend(
            {
                (query, 0): [
                    "https://jobs.ashbyhq.com/company/33333333-3333-4333-8333-333333333333",
                    "https://jobs.ashbyhq.com/company/44444444-4444-4444-8444-444444444444",
                ]
            }
        )

        def fake_crawl_runner(config, providers, discovered):
            self.assertEqual(config.search_results_per_query, 20)
            self.assertEqual(len(providers), 1)
            self.assertEqual(discovered[0][0], query)
            return [
                ScrapedJobPosting(
                    provider="ashby",
                    company_slug="remote-canada",
                    company_name="Remote Canada",
                    job_url=discovered[0][1],
                    job_title_raw="Site Reliability Engineer",
                    location="Canada",
                    team="Infra",
                    remote_status="Remote Canada",
                    posting_id="333",
                    archive_text="",
                    archive_html_snippet="",
                    description_html="",
                    discovered_from_url=discovered[0][1],
                    fetched_at="2026-03-29T00:00:00+00:00",
                    metadata={"source_query": discovered[0][0]},
                ),
                ScrapedJobPosting(
                    provider="ashby",
                    company_slug="outside-scope",
                    company_name="Outside Scope",
                    job_url=discovered[1][1],
                    job_title_raw="Site Reliability Engineer",
                    location="Berlin, Germany",
                    team="Infra",
                    remote_status="Remote",
                    posting_id="444",
                    archive_text="",
                    archive_html_snippet="",
                    description_html="",
                    discovered_from_url=discovered[1][1],
                    fetched_at="2026-03-29T00:00:00+00:00",
                    metadata={"source_query": discovered[1][0]},
                ),
            ]

        jobs, report = scrape_jobs(
            run_config,
            self.profile,
            backend=backend,
            crawl_runner=fake_crawl_runner,
        )

        self.assertEqual([job.company_slug for job in jobs], ["remote-canada"])
        self.assertEqual(report.total_kept_results, 2)
        self.assertEqual(report.total_location_filtered_results, 1)
        self.assertIn("location_filtered=1", format_discovery_success_lines(report)[0])


if __name__ == "__main__":
    unittest.main()
