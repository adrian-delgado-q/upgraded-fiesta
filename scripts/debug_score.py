from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.extraction import extract_profile_data
from collector.llm import LLMClient
from collector.normalization import canonical_key, infer_role_family, infer_seniority, infer_work_mode, normalize_location, normalize_title
from collector.profiles import load_active_profile
from collector.scoring import compute_deterministic_score
from shared.config import load_runtime_config
from shared.models import NormalizedJob


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug normalization, extraction, scoring, and local LLM analysis for a sample job.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--title", required=True)
    parser.add_argument("--company", default="Debug Company")
    parser.add_argument("--location", default="")
    parser.add_argument("--remote", default="")
    parser.add_argument("--url", default="https://example.com/jobs/debug")
    parser.add_argument("--description", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_runtime_config()
    profile = load_active_profile(config.rules_path, profile=args.profile or config.active_profile)
    title_normalized = normalize_title(args.title, profile)
    city, region, country = normalize_location(args.location, profile)
    work_mode_text = " ".join(part for part in (args.location, args.remote) if part)
    description_for_inference = f"{title_normalized} {args.description}"
    job = NormalizedJob(
        source="debug",
        company=args.company,
        title_raw=args.title,
        title_normalized=title_normalized,
        role_family=infer_role_family(description_for_inference, profile),
        seniority=infer_seniority(description_for_inference, profile),
        location_raw=args.location or None,
        location_city=city,
        location_region=region,
        location_country=country,
        work_mode=infer_work_mode(work_mode_text, profile),
        url=args.url,
        canonical_key=canonical_key(args.company, title_normalized, args.location, args.url),
        description_text=args.description,
    )
    artifacts = extract_profile_data(job, profile)
    score = compute_deterministic_score(job, profile, artifacts)
    llm = LLMClient(config.llm_config, profile)
    analysis = llm.analyze(job, artifacts, score.deterministic_score)
    payload = {
        "job": {
            "title_raw": job.title_raw,
            "title_normalized": job.title_normalized,
            "role_family": job.role_family,
            "seniority": job.seniority,
            "location_city": job.location_city,
            "location_region": job.location_region,
            "location_country": job.location_country,
            "work_mode": job.work_mode,
        },
        "normalized_facets": artifacts.normalized_facets,
        "profile_signals": artifacts.profile_signals,
        "score": score.to_dict(),
        "llm_analysis": analysis,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
