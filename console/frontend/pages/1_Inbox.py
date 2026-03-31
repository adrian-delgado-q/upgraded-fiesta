from __future__ import annotations

import streamlit as st

from console.frontend.config import get_api_base_url
from console.frontend.components.detail_panel import render_detail_panel
from console.frontend.components.jobs_table import SELECTION_KEY, render_jobs_table
from console.frontend.services import ApiClient
from console.frontend.styles import apply_shared_styles


client = ApiClient(get_api_base_url())
apply_shared_styles()
PENDING_ACTION_KEY = "inbox_pending_action"
PAGE_KEY = "inbox_page"
FILTER_SIGNATURE_KEY = "inbox_filter_signature"


pending_action = st.session_state.pop(PENDING_ACTION_KEY, None)
if pending_action:
    action_name, action_job_id = pending_action
    if action_name == "reject":
        client.post(f"/jobs/{action_job_id}/reject", {})
    elif action_name == "shortlist":
        client.post(
            f"/jobs/{action_job_id}/shortlist",
            {"triage_status": "shortlisted", "shortlist_reason": "Manual shortlist"},
        )
    st.session_state.pop(SELECTION_KEY, None)
    st.rerun()

st.title("Inbox")
st.caption("Review fresh jobs. Shortlisting moves them out of Inbox. Rejected jobs are hidden everywhere.")
with st.sidebar:
    st.caption("Status")
    triage_status = st.selectbox(
        "Status",
        ["", "new"],
        label_visibility="collapsed",
    )
    st.caption("Source")
    source = st.selectbox("Source", ["", "ashby", "lever", "greenhouse"], label_visibility="collapsed")
    st.caption("Role family")
    role_family = st.text_input("Role family", label_visibility="collapsed")
    st.caption("Page size")
    page_size = st.number_input("Page size", min_value=25, max_value=500, value=100, step=25, label_visibility="collapsed")
    salary_known = st.checkbox("Salary known")

filter_signature = (triage_status, source, role_family.strip(), salary_known, int(page_size))
if st.session_state.get(FILTER_SIGNATURE_KEY) != filter_signature:
    st.session_state[FILTER_SIGNATURE_KEY] = filter_signature
    st.session_state[PAGE_KEY] = 0

current_page = int(st.session_state.get(PAGE_KEY, 0))
response = client.get(
    "/jobs",
    {
        "triage_status": triage_status,
        "source": source,
        "role_family": role_family,
        "salary_known": salary_known,
        "limit": int(page_size),
        "offset": current_page * int(page_size),
    },
)
jobs = response["items"]
total_jobs = int(response["total"])
page_size_value = int(page_size)
total_pages = max(1, (total_jobs + page_size_value - 1) // page_size_value)
if total_jobs and current_page >= total_pages:
    st.session_state[PAGE_KEY] = total_pages - 1
    st.rerun()

page_start = (current_page * page_size_value) + 1 if total_jobs else 0
page_end = min((current_page + 1) * page_size_value, total_jobs)
st.caption(f"Showing {page_start}-{page_end} of {total_jobs} matching unprocessed jobs")

pager_cols = st.columns([1, 1.5, 1, 3])
prev_disabled = current_page <= 0
next_disabled = current_page >= (total_pages - 1) or total_jobs == 0
if pager_cols[0].button("Previous", use_container_width=True, disabled=prev_disabled):
    st.session_state[PAGE_KEY] = max(0, current_page - 1)
    st.rerun()
pager_cols[1].markdown(
    f"<div class='console-toolbar'><strong>Page {current_page + 1}</strong> of {total_pages}</div>",
    unsafe_allow_html=True,
)
if pager_cols[2].button("Next", use_container_width=True, disabled=next_disabled):
    st.session_state[PAGE_KEY] = min(total_pages - 1, current_page + 1)
    st.rerun()
pager_cols[3].markdown(
    f"<div class='console-toolbar'><strong>{len(jobs)}</strong> jobs on this page</div>",
    unsafe_allow_html=True,
)

table_container = st.container()
detail_container = None
if st.session_state.get(SELECTION_KEY):
    table_container, detail_container = st.columns([1.75, 1.0], vertical_alignment="top")

with table_container:
    selected_id, action = render_jobs_table(
        jobs,
        selection_key=SELECTION_KEY,
        empty_message="No jobs match the current inbox filters.",
        enable_sorting=True,
        toolbar_message="Shortlist moves items out of Inbox. Reject hides them everywhere.",
    )
if action:
    st.session_state[PENDING_ACTION_KEY] = action
    st.rerun()

if selected_id:
    with detail_container or st.container():
        st.markdown("### Open Role")
        job = client.get(f"/jobs/{selected_id}")
        breakdown = None
        try:
            breakdown = client.get(f"/jobs/{selected_id}/score-breakdown")
        except Exception:
            breakdown = None
        col1, col2, col3 = st.columns(3)
        if col1.button("Close", key=f"detail-close-{selected_id}"):
            st.session_state.pop(SELECTION_KEY, None)
            st.rerun()
        if col2.button("Reject", key=f"detail-reject-{selected_id}"):
            client.post(f"/jobs/{selected_id}/reject", {})
            st.session_state.pop(SELECTION_KEY, None)
            st.rerun()
        if col3.button("Shortlist", key=f"detail-shortlist-{selected_id}"):
            client.post(f"/jobs/{selected_id}/shortlist", {"triage_status": "shortlisted", "shortlist_reason": "Manual shortlist"})
            st.session_state.pop(SELECTION_KEY, None)
            st.rerun()
        st.markdown(f"[Open Posting]({job['url']})")
        render_detail_panel(job, breakdown)
