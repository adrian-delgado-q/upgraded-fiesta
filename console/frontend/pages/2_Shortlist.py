from __future__ import annotations

import streamlit as st

from console.frontend.components.detail_panel import render_detail_panel
from console.frontend.components.jobs_table import (
    DEFAULT_SHORTLIST_ACTIONS,
    SHORTLIST_SELECTION_KEY,
    render_jobs_table,
)
from console.frontend.styles import apply_shared_styles
from console.frontend.utils import execute_action, get_client, render_pager

apply_shared_styles()

client = get_client()

# ── Constants ─────────────────────────────────────────────────────────────
PAGE_KEY = "shortlist_page"
FILTER_SIG_KEY = "shortlist_filter_sig"

# ── Sidebar filters ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Shortlist filters")

    role_family = st.text_input(
        "Role family",
        value=st.session_state.get("shortlist_filter_role", ""),
        key="shortlist_filter_role_input",
        placeholder="e.g. engineering",
    )
    st.session_state["shortlist_filter_role"] = role_family

    salary_known = st.checkbox(
        "Salary known only",
        value=st.session_state.get("shortlist_filter_salary", False),
        key="shortlist_filter_salary_cb",
    )
    st.session_state["shortlist_filter_salary"] = salary_known

    page_size = st.select_slider(
        "Page size",
        options=[25, 50, 100, 200],
        value=st.session_state.get("shortlist_filter_pgsz", 50),
        key="shortlist_filter_pgsz_sl",
    )
    st.session_state["shortlist_filter_pgsz"] = page_size

# Detect filter changes → reset pagination
filter_sig = (role_family.strip(), salary_known, page_size)
if st.session_state.get(FILTER_SIG_KEY) != filter_sig:
    st.session_state[FILTER_SIG_KEY] = filter_sig
    st.session_state[PAGE_KEY] = 0

current_page = int(st.session_state.get(PAGE_KEY, 0))

# ── Fetch ─────────────────────────────────────────────────────────────────
params: dict = {
    "triage_status": "shortlisted",
    "salary_known": salary_known,
    "limit": page_size,
    "offset": current_page * page_size,
}
if role_family.strip():
    params["role_family"] = role_family.strip()

response = client.list_jobs(**params)
jobs = response["items"]
total = int(response["total"])
total_pages = max(1, (total + page_size - 1) // page_size)

if total and current_page >= total_pages:
    st.session_state[PAGE_KEY] = total_pages - 1
    st.rerun()

# ── Header ────────────────────────────────────────────────────────────────
st.title(f"★ Shortlist ({total})")
st.caption("Approve sends a role into Package. Reject removes it from every visible list.")

# ── Layout ────────────────────────────────────────────────────────────────
selected_id = st.session_state.get(SHORTLIST_SELECTION_KEY)
if selected_id:
    table_col, detail_col = st.columns([1.75, 1.0], vertical_alignment="top")
else:
    table_col = st.container()
    detail_col = None

with table_col:
    render_pager(page_key=PAGE_KEY, total=total, page_size=page_size, current_page=current_page)

    new_selected_id, action = render_jobs_table(
        jobs,
        selection_key=SHORTLIST_SELECTION_KEY,
        empty_message="No shortlisted jobs yet.",
        action_specs=DEFAULT_SHORTLIST_ACTIONS,
        enable_sorting=True,
        toolbar_message="Approve moves roles into Package. Reject removes them permanently.",
    )

    if action:
        action_name, action_job_id = action
        if execute_action(client, action_name, action_job_id, selection_key=SHORTLIST_SELECTION_KEY):
            st.rerun()

# ── Detail panel ──────────────────────────────────────────────────────────
if new_selected_id and detail_col:
    with detail_col:
        job = client.get_job(new_selected_id)
        breakdown = client.get_score_breakdown(new_selected_id)

        close_col, reject_col, approve_col = st.columns(3)
        if close_col.button("Close", key=f"sl-close-{new_selected_id}", use_container_width=True):
            st.session_state.pop(SHORTLIST_SELECTION_KEY, None)
            st.rerun()
        if reject_col.button("✕ Reject", key=f"sl-reject-{new_selected_id}", use_container_width=True):
            if execute_action(client, "reject", new_selected_id, selection_key=SHORTLIST_SELECTION_KEY):
                st.rerun()
        if approve_col.button("✓ Approve", key=f"sl-approve-{new_selected_id}", use_container_width=True):
            if execute_action(client, "approve", new_selected_id, selection_key=SHORTLIST_SELECTION_KEY):
                st.success("Queued for packaging.")
                st.rerun()

        if job.get("url"):
            st.markdown(f"[Open posting ↗]({job['url']})")
        if job.get("shortlist_reason"):
            st.info(f"Shortlist note: {job['shortlist_reason']}")

        render_detail_panel(job, breakdown)

