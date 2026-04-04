"""Shared frontend utilities for the triage console."""

from __future__ import annotations

import streamlit as st

from .services import ApiClient


@st.cache_resource
def _build_client() -> ApiClient:
    from .config import get_api_base_url

    return ApiClient(get_api_base_url())


def get_client() -> ApiClient:
    """Return the cached ApiClient singleton (one instance per Streamlit server process)."""
    return _build_client()


def execute_action(
    client: ApiClient,
    action: str,
    job_id: int,
    *,
    reason: str | None = None,
    selection_key: str | None = None,
) -> bool:
    """
    Dispatch a triage action and clear the current selection.

    Returns True if the action was handled (so callers can st.rerun()).
    """
    try:
        if action == "reject":
            client.reject_job(job_id)
        elif action == "shortlist":
            client.shortlist_job(job_id, reason)
        elif action == "approve":
            client.approve_job(job_id)
        elif action == "restore":
            client.restore_job(job_id)
        else:
            return False
    except RuntimeError as exc:
        st.error(f"Action failed: {exc}")
        return False

    if selection_key:
        st.session_state.pop(selection_key, None)
    return True


def render_pager(
    *,
    page_key: str,
    total: int,
    page_size: int,
    current_page: int,
) -> None:
    """Render Previous / page-info / Next controls."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages <= 1 and total == 0:
        return

    page_start = current_page * page_size + 1 if total else 0
    page_end = min((current_page + 1) * page_size, total)

    cols = st.columns([1, 2, 1, 3])
    if cols[0].button("← Prev", use_container_width=True, disabled=current_page <= 0):
        st.session_state[page_key] = max(0, current_page - 1)
        st.rerun()
    cols[1].markdown(
        f"<div class='console-toolbar' style='text-align:center'>"
        f"<strong>{current_page + 1}</strong> / {total_pages}</div>",
        unsafe_allow_html=True,
    )
    if cols[2].button("Next →", use_container_width=True, disabled=current_page >= total_pages - 1):
        st.session_state[page_key] = min(total_pages - 1, current_page + 1)
        st.rerun()
    cols[3].markdown(
        f"<div class='console-toolbar'>{page_start}–{page_end} of <strong>{total}</strong></div>",
        unsafe_allow_html=True,
    )
