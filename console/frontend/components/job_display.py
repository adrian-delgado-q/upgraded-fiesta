from __future__ import annotations

from typing import Any


def _format_amount(value: Any, currency: str) -> str:
    if value in (None, ""):
        return ""
    amount = float(value)
    if amount >= 1000:
        if amount.is_integer():
            return f"{currency} {int(amount):,}"
        return f"{currency} {amount:,.0f}"
    if amount.is_integer():
        return f"{currency} {int(amount)}"
    return f"{currency} {amount:,.2f}"


def format_compensation(job: dict[str, Any]) -> str:
    minimum = job.get("salary_min_cad")
    maximum = job.get("salary_max_cad")
    currency = str(job.get("salary_currency") or "CAD").upper()
    period = str(job.get("salary_period") or "").strip().lower()
    minimum_text = _format_amount(minimum, currency)
    maximum_text = _format_amount(maximum, currency)
    if minimum_text and maximum_text:
        base = f"{minimum_text} - {maximum_text}"
    elif minimum_text:
        base = f"From {minimum_text}"
    elif maximum_text:
        base = f"Up to {maximum_text}"
    else:
        return "Unknown"

    if period:
        return f"{base}/{period}"
    return base


def format_compensation_badge(job: dict[str, Any]) -> str:
    compensation = format_compensation(job)
    if compensation == "Unknown":
        return "Compensation unknown"
    return compensation


def format_compensation_emphasis(job: dict[str, Any]) -> str:
    compensation = format_compensation(job)
    if compensation == "Unknown":
        return "Salary not listed"
    return compensation


def format_job_score(job: dict[str, Any]) -> str:
    score = round(job.get("final_score") or job.get("deterministic_score") or 0, 1)
    return f"{score:.1f}"


def compensation_sort_value(job: dict[str, Any]) -> tuple[int, float]:
    minimum = job.get("salary_min_cad")
    maximum = job.get("salary_max_cad")
    if minimum not in (None, ""):
        return (1, float(minimum))
    if maximum not in (None, ""):
        return (1, float(maximum))
    return (0, 0.0)
