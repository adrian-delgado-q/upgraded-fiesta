from __future__ import annotations

import streamlit as st

from console.frontend.components.detail_panel import render_detail_panel
from console.frontend.components.jobs_table import (
    DEFAULT_SHORTLIST_ACTIONS,
    SHORTLIST_SELECTION_KEY,
    render_jobs_table,
)
from console.frontend.config import get_api_base_url
from console.frontend.services import ApiClient
from console.frontend.styles import apply_shared_styles


client = ApiClient(get_api_base_url())
apply_shared_styles()
PENDING_ACTION_KEY = "shortlist_pending_action"


pending_action = st.session_state.pop(PENDING_ACTION_KEY, None)
if pending_action:
    action_name, action_job_id = pending_action
    if action_name == "approve":
        client.post(f"/jobs/{action_job_id}/approve", {})
    elif action_name == "reject":
        client.post(f"/jobs/{action_job_id}/reject", {})
    st.session_state.pop(SHORTLIST_SELECTION_KEY, None)
    st.rerun()

st.title("Shortlist")
st.markdown(
    '<div class="console-page-note">Approve sends a role into Package. Reject removes it from every visible list.</div>',
    unsafe_allow_html=True,
)
jobs_response = client.get("/jobs", {"triage_status": "shortlisted"})
jobs = jobs_response["items"]
table_container = st.container()
detail_container = None
if st.session_state.get(SHORTLIST_SELECTION_KEY):
    table_container, detail_container = st.columns([1.75, 1.0], vertical_alignment="top")

with table_container:
    selected_id, action = render_jobs_table(
        jobs,
        selection_key=SHORTLIST_SELECTION_KEY,
        empty_message="No shortlisted jobs yet.",
        action_specs=DEFAULT_SHORTLIST_ACTIONS,
        enable_sorting=False,
        toolbar_message="Approve moves roles into Package. Reject removes them from every visible list.",
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
        if col1.button("Close", key=f"shortlist-detail-close-{selected_id}"):
            st.session_state.pop(SHORTLIST_SELECTION_KEY, None)
            st.rerun()
        if col2.button("Reject", key=f"shortlist-detail-reject-{selected_id}"):
            client.post(f"/jobs/{selected_id}/reject", {})
            st.session_state.pop(SHORTLIST_SELECTION_KEY, None)
            st.rerun()
        if col3.button("Approve", key=f"shortlist-detail-approve-{selected_id}"):
            client.post(f"/jobs/{selected_id}/approve", {})
            st.session_state.pop(SHORTLIST_SELECTION_KEY, None)
            st.rerun()
        st.markdown(f"[Open Posting]({job['url']})")
        render_detail_panel(job, breakdown)
