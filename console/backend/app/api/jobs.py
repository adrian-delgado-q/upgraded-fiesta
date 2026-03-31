from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from shared.models import PackageRequestRecord

from ..dependencies import get_repository

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize(value: object) -> object:
    return jsonable_encoder(value)


class ImportPayload(BaseModel):
    jobs: list[dict]


class TriagePayload(BaseModel):
    triage_status: str
    shortlist_reason: str | None = None


@router.post("/import")
def import_jobs(payload: ImportPayload) -> list[dict]:
    from ..dependencies import get_collector
    from collector.scraper.models import ScrapedJobPosting

    jobs = [ScrapedJobPosting(**job) for job in payload.jobs]
    return get_collector().import_scraped_jobs(jobs)


@router.get("")
def list_jobs(
    triage_status: str | None = None,
    source: str | None = None,
    role_family: str | None = None,
    salary_known: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, gt=0, le=500),
) -> dict[str, object]:
    filters = {
        "triage_status": triage_status,
        "source": source,
        "role_family": role_family,
        "salary_known": salary_known,
    }
    repository = get_repository()
    jobs = repository.list_jobs(
        filters,
        limit=limit,
        offset=offset,
    )
    total = repository.count_jobs_for_filters(filters)
    return _serialize(
        {
            "items": jobs,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": limit is not None and offset + len(jobs) < total,
        }
    )


@router.get("/{job_id}")
def get_job(job_id: int) -> dict:
    job = get_repository().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize(job)


@router.get("/{job_id}/score-breakdown")
def get_job_score_breakdown(job_id: int) -> dict:
    breakdown = get_repository().get_job_score_breakdown(job_id)
    if not breakdown:
        raise HTTPException(status_code=404, detail="Score breakdown not found")
    return _serialize(breakdown)


@router.patch("/{job_id}/triage-status")
def patch_triage_status(job_id: int, payload: TriagePayload) -> dict:
    if not get_repository().get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    get_repository().set_triage_status(job_id, payload.triage_status, payload.shortlist_reason)
    return {"status": "ok"}


@router.post("/{job_id}/shortlist")
def shortlist_job(job_id: int, payload: TriagePayload) -> dict:
    get_repository().set_triage_status(job_id, "shortlisted", payload.shortlist_reason)
    return {"status": "shortlisted"}


@router.post("/{job_id}/reject")
def reject_job(job_id: int) -> dict:
    get_repository().set_triage_status(job_id, "rejected")
    return {"status": "rejected"}


@router.post("/{job_id}/approve")
def approve_job(job_id: int) -> dict:
    repository = get_repository()
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.latest_version_id:
        raise HTTPException(status_code=400, detail="Job has no version to package")
    package_id = repository.queue_package_request(
        PackageRequestRecord(
            job_id=job_id,
            job_version_id=int(job.latest_version_id),
            package_type="application_package",
            requested_by="console",
            generation_profile=job.role_family or "default",
        )
    )
    if package_id is None:
        raise HTTPException(status_code=500, detail="Failed to queue package")
    return {"status": "queued_for_package", "package_id": package_id}
