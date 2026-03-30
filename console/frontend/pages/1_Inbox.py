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
    st.caption("Max items")
    max_items = st.number_input("Max items", min_value=1, max_value=500, value=100, step=25, label_visibility="collapsed")
    salary_known = st.checkbox("Salary known")

jobs = client.get(
    "/jobs",
    {
        "triage_status": triage_status,
        "source": source,
        "role_family": role_family,
        "salary_known": salary_known,
        "limit": int(max_items),
    },
)
st.caption(f"Showing up to {int(max_items)} matching jobs")
selected_id, action = render_jobs_table(jobs)
if action:
    st.session_state[PENDING_ACTION_KEY] = action
    st.rerun()

if selected_id:
    job = client.get(f"/jobs/{selected_id}")
    breakdown = None
    try:
        breakdown = client.get(f"/jobs/{selected_id}/score-breakdown")
    except Exception:
        breakdown = None
    col1, col2, col3 = st.columns(3)
    if col1.button("Reject", key=f"detail-reject-{selected_id}"):
        client.post(f"/jobs/{selected_id}/reject", {})
        st.session_state.pop(SELECTION_KEY, None)
        st.rerun()
    if col2.button("Shortlist", key=f"detail-shortlist-{selected_id}"):
        client.post(f"/jobs/{selected_id}/shortlist", {"triage_status": "shortlisted", "shortlist_reason": "Manual shortlist"})
        st.session_state.pop(SELECTION_KEY, None)
        st.rerun()
    col3.markdown(f"[Open Posting]({job['url']})")
    render_detail_panel(job, breakdown)
