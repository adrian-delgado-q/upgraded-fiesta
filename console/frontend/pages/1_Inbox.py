from __future__ import annotations

import streamlit as st

from console.frontend.components.detail_panel import render_detail_panel
from console.frontend.components.jobs_table import SELECTION_KEY, render_jobs_table
from console.frontend.styles import apply_shared_styles
from console.frontend.utils import execute_action, get_client, render_pager

apply_shared_styles()

client = get_client()

# ── Constants ─────────────────────────────────────────────────────────────
PAGE_KEY = "inbox_page"
FILTER_SIG_KEY = "inbox_filter_sig"

# ── Sidebar filters ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Inbox filters")

    # Source list — fetched from settings; fallback to defaults
    @st.cache_data(ttl=300)
    def _get_providers() -> list[str]:
        try:
            s = get_client().get_settings()
            return sorted(s.get("scraper_defaults", {}).get("providers", []))
        except Exception:
            return ["ashby", "greenhouse", "lever"]

    providers = _get_providers()
    source = st.selectbox(
        "Source",
        ["All"] + providers,
        index=st.session_state.get("inbox_filter_source_idx", 0),
        key="inbox_filter_source",
    )
    st.session_state["inbox_filter_source_idx"] = ["All", *providers].index(source)

    work_mode = st.selectbox(
        "Work mode",
        ["All", "remote", "hybrid", "onsite"],
        index=st.session_state.get("inbox_filter_wm_idx", 0),
        key="inbox_filter_wm",
    )
    st.session_state["inbox_filter_wm_idx"] = ["All", "remote", "hybrid", "onsite"].index(work_mode)

    role_family = st.text_input(
        "Role family",
        value=st.session_state.get("inbox_filter_role", ""),
        key="inbox_filter_role_input",
        placeholder="e.g. engineering",
    )
    st.session_state["inbox_filter_role"] = role_family

    salary_known = st.checkbox(
        "Salary known only",
        value=st.session_state.get("inbox_filter_salary", False),
        key="inbox_filter_salary_cb",
    )
    st.session_state["inbox_filter_salary"] = salary_known

    page_size = st.select_slider(
        "Page size",
        options=[25, 50, 100, 200],
        value=st.session_state.get("inbox_filter_pgsz", 50),
        key="inbox_filter_pgsz_sl",
    )
    st.session_state["inbox_filter_pgsz"] = page_size

# Detect filter changes → reset pagination
filter_sig = (source, work_mode, role_family.strip(), salary_known, page_size)
if st.session_state.get(FILTER_SIG_KEY) != filter_sig:
    st.session_state[FILTER_SIG_KEY] = filter_sig
    st.session_state[PAGE_KEY] = 0

current_page = int(st.session_state.get(PAGE_KEY, 0))

# ── Fetch ─────────────────────────────────────────────────────────────────
params: dict = {
    "triage_status": "new",
    "salary_known": salary_known,
    "limit": page_size,
    "offset": current_page * page_size,
}
if source != "All":
    params["source"] = source
if work_mode != "All":
    params["work_mode"] = work_mode
if role_family.strip():
    params["role_family"] = role_family.strip()

response = client.list_jobs(**params)
jobs = response["items"]
total = int(response["total"])
total_pages = max(1, (total + page_size - 1) // page_size)

# Guard stale page
if total and current_page >= total_pages:
    st.session_state[PAGE_KEY] = total_pages - 1
    st.rerun()

# ── Header ────────────────────────────────────────────────────────────────
st.title(f"📥 Inbox ({total})")
st.caption("Shortlist keeps promising roles. Reject hides them. Both actions leave Inbox immediately.")

# ── Layout: table + optional detail panel side-by-side ───────────────────
selected_id = st.session_state.get(SELECTION_KEY)
if selected_id:
    table_col, detail_col = st.columns([1.75, 1.0], vertical_alignment="top")
else:
    table_col = st.container()
    detail_col = None

with table_col:
    render_pager(page_key=PAGE_KEY, total=total, page_size=page_size, current_page=current_page)

    new_selected_id, action = render_jobs_table(
        jobs,
        selection_key=SELECTION_KEY,
        empty_message="No jobs match the current filters.",
        enable_sorting=True,
        toolbar_message="Shortlist moves roles out of Inbox. Reject hides them everywhere.",
    )

    if action:
        action_name, action_job_id = action
        if execute_action(client, action_name, action_job_id, selection_key=SELECTION_KEY):
            st.rerun()

# ── Detail panel ──────────────────────────────────────────────────────────
if new_selected_id and detail_col:
    with detail_col:
        job = client.get_job(new_selected_id)
        breakdown = client.get_score_breakdown(new_selected_id)

        close_col, reject_col = st.columns(2)
        if close_col.button("Close", key=f"inbox-close-{new_selected_id}", use_container_width=True):
            st.session_state.pop(SELECTION_KEY, None)
            st.rerun()
        if reject_col.button("✕ Reject", key=f"inbox-reject-{new_selected_id}", use_container_width=True):
            if execute_action(client, "reject", new_selected_id, selection_key=SELECTION_KEY):
                st.rerun()

        shortlist_note = st.text_input(
            "Shortlist note (optional)",
            key=f"inbox-sl-note-{new_selected_id}",
            placeholder="Why does this role stand out?",
        )
        if st.button("★ Shortlist", key=f"inbox-shortlist-{new_selected_id}", use_container_width=True):
            if execute_action(
                client,
                "shortlist",
                new_selected_id,
                reason=shortlist_note.strip() or None,
                selection_key=SELECTION_KEY,
            ):
                st.rerun()

        if job.get("url"):
            st.markdown(f"[Open posting ↗]({job['url']})")

        render_detail_panel(job, breakdown)

