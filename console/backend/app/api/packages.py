from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from ..dependencies import get_repository

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("")
def list_packages(
    status: str | None = Query(default=None),
    limit: int | None = Query(default=None, gt=0, le=500),
) -> list[dict]:
    statuses = [status] if status else None
    return jsonable_encoder(get_repository().list_packages(statuses=statuses, limit=limit))
