from __future__ import annotations

import html

import streamlit as st

from console.frontend.components.job_display import format_compensation_emphasis, format_job_score
from console.frontend.styles import apply_shared_styles
from console.frontend.utils import execute_action, get_client, render_pager

apply_shared_styles()

client = get_client()

# ── Constants ─────────────────────────────────────────────────────────────
PAGE_KEY = "rejected_page"
FILTER_SIG_KEY = "rejected_filter_sig"
SELECTION_KEY = "rejected_selected_id"

# ── Sidebar filters ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Rejected filters")

    search = st.text_input(
        "Company / title",
        value=st.session_state.get("rejected_filter_search", ""),
        key="rejected_filter_search_input",
        placeholder="Filter by company or title",
    )
    st.session_state["rejected_filter_search"] = search

    page_size = st.select_slider(
        "Page size",
        options=[25, 50, 100],
        value=st.session_state.get("rejected_filter_pgsz", 50),
        key="rejected_filter_pgsz_sl",
    )
    st.session_state["rejected_filter_pgsz"] = page_size

filter_sig = (search.strip().lower(), page_size)
if st.session_state.get(FILTER_SIG_KEY) != filter_sig:
    st.session_state[FILTER_SIG_KEY] = filter_sig
    st.session_state[PAGE_KEY] = 0

current_page = int(st.session_state.get(PAGE_KEY, 0))

# ── Fetch ─────────────────────────────────────────────────────────────────
response = client.list_jobs(
    triage_status="rejected",
    limit=page_size,
    offset=current_page * page_size,
)
all_jobs: list[dict] = response["items"]
total = int(response["total"])
total_pages = max(1, (total + page_size - 1) // page_size)

# Client-side search filter (server doesn't support text search)
search_term = search.strip().lower()
if search_term:
    jobs = [
        j for j in all_jobs
        if search_term in (j.get("company") or "").lower()
        or search_term in (j.get("title_normalized") or j.get("title_raw") or "").lower()
    ]
else:
    jobs = all_jobs

if total and current_page >= total_pages:
    st.session_state[PAGE_KEY] = total_pages - 1
    st.rerun()

# ── Header ────────────────────────────────────────────────────────────────
st.title(f"✕ Rejected ({total})")
st.caption("Restore any role dismissed by mistake — it will reappear in the Inbox.")

if not jobs:
    st.markdown('<div class="console-empty">No rejected jobs to show.</div>', unsafe_allow_html=True)
    st.stop()

render_pager(page_key=PAGE_KEY, total=total, page_size=page_size, current_page=current_page)

# ── Table ─────────────────────────────────────────────────────────────────
COL_WIDTHS = [3.5, 1.5, 1.5, 1.2, 1.2]

header_cols = st.columns(COL_WIDTHS)
for col, label in zip(header_cols, ("Role", "Source / Mode", "Compensation", "Score", "Action")):
    col.markdown(f'<div class="console-table-header-cell">{html.escape(label)}</div>', unsafe_allow_html=True)

for job in jobs:
    title = html.escape(job.get("title_normalized") or job.get("title_raw") or "Untitled")
    company = html.escape(job.get("company") or "Unknown")
    url = html.escape(job.get("url") or "#", quote=True)
    source = html.escape(job.get("source") or "")
    work_mode = html.escape(job.get("work_mode") or "")
    comp = format_compensation_emphasis(job)
    score = format_job_score(job)
    job_id = int(job["id"])

    row_cols = st.columns(COL_WIDTHS, vertical_alignment="center")
    row_cols[0].markdown(
        f'<div class="console-table-cell console-table-role">'
        f'<div class="console-table-role-title"><a href="{url}" target="_blank">{title}</a></div>'
        f'<div class="console-table-role-subtitle">{company}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    row_cols[1].markdown(
        f'<div class="console-table-cell console-table-meta">{source} · {work_mode}</div>',
        unsafe_allow_html=True,
    )
    row_cols[2].markdown(
        f'<div class="console-table-cell console-table-comp">{html.escape(comp)}</div>',
        unsafe_allow_html=True,
    )
    row_cols[3].markdown(
        f'<div class="console-table-cell console-table-score">{html.escape(score)}</div>',
        unsafe_allow_html=True,
    )
    if row_cols[4].button("↩ Restore", key=f"restore-{job_id}", use_container_width=True, help="Move back to Inbox"):
        if execute_action(client, "restore", job_id):
            st.rerun()
