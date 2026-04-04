from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # Primitives                                                           #
    # ------------------------------------------------------------------ #

    def get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{self.base_url}{path}"
        if params:
            query = {k: v for k, v in params.items() if v not in (None, "", False)}
            if query:
                url = f"{url}?{urlencode(query)}"
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, payload: dict | None = None) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8")) from exc

    def patch(self, path: str, payload: dict) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8")) from exc

    # ------------------------------------------------------------------ #
    # Domain helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_counts(self) -> dict:
        """Fetch per-triage and per-package-status counts."""
        return self.get("/jobs/counts")  # type: ignore[return-value]

    def get_settings(self) -> dict:
        return self.get("/settings")  # type: ignore[return-value]

    def set_active_profile(self, profile: str) -> dict:
        return self.patch("/settings/profile", {"active_profile": profile})

    def set_thresholds(self, shortlisted: float, review: float, maybe: float, llm_analyze_threshold: float) -> dict:
        return self.patch(
            "/settings/thresholds",
            {
                "shortlisted": shortlisted,
                "review": review,
                "maybe": maybe,
                "llm_analyze_threshold": llm_analyze_threshold,
            },
        )

    def list_jobs(self, **params) -> dict:
        return self.get("/jobs", params)  # type: ignore[return-value]

    def get_job(self, job_id: int) -> dict:
        return self.get(f"/jobs/{job_id}")  # type: ignore[return-value]

    def get_score_breakdown(self, job_id: int) -> dict | None:
        try:
            return self.get(f"/jobs/{job_id}/score-breakdown")  # type: ignore[return-value]
        except Exception:
            return None

    def shortlist_job(self, job_id: int, reason: str | None = None) -> dict:
        return self.post(f"/jobs/{job_id}/shortlist", {"shortlist_reason": reason})

    def reject_job(self, job_id: int) -> dict:
        return self.post(f"/jobs/{job_id}/reject")

    def restore_job(self, job_id: int) -> dict:
        return self.post(f"/jobs/{job_id}/restore")

    def approve_job(self, job_id: int) -> dict:
        return self.post(f"/jobs/{job_id}/approve")

    def list_packages(self, status: str | None = None, limit: int = 100) -> list:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        return self.get("/packages", params)  # type: ignore[return-value]

