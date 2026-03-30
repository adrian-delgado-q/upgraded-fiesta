from __future__ import annotations

import html

import streamlit as st

from console.frontend.components.detail_panel import render_detail_panel
from console.frontend.components.job_display import format_compensation_emphasis, format_job_score
from console.frontend.components.jobs_table import _chip
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
    st.rerun()

st.title("Shortlist")
st.markdown(
    '<div class="console-page-note">Approve sends a role into Package. Reject removes it from every visible list.</div>',
    unsafe_allow_html=True,
)
jobs = client.get("/jobs", {"triage_status": "shortlisted"})
if not jobs:
    st.markdown('<div class="console-empty">No shortlisted jobs yet.</div>', unsafe_allow_html=True)

for job in jobs:
    score = format_job_score(job)
    compensation = format_compensation_emphasis(job)
    toggle_key = f"shortlist-show-jd-{job['id']}"
    st.session_state.setdefault(toggle_key, False)

    row_cols = st.columns([6.2, 2.2], vertical_alignment="center")
    with row_cols[0]:
        title = html.escape(job["title_normalized"] or job["title_raw"] or "Untitled")
        url = html.escape(job["url"] or "#", quote=True)
        company = html.escape(job["company"] or "Unknown")
        location = html.escape(job["location_raw"] or "Unknown")
        source = html.escape(job["source"] or "Unknown")
        work_mode = html.escape(job["work_mode"] or "Mode unknown")
        role_family = html.escape(job["role_family"] or "Unknown")
        seniority = html.escape(job["seniority"] or "Unknown")
        st.markdown(
            (
                '<div class="console-card tight">'
                f'<div class="console-card-title"><a href="{url}" target="_blank">{title}</a></div>'
                f'<div class="console-card-meta">{company} | {location}</div>'
                f'<div class="console-card-submeta">{source} | {work_mode}</div>'
                '<div class="console-chip-row">'
                f'{_chip(compensation, "$", "comp")}'
                f'{_chip(f"Score {score}", "#", "score")}'
                f'{_chip(role_family, "R")}'
                f'{_chip(seniority, "S", "subtle")}'
                '</div>'
                '</div>'
            ),
            unsafe_allow_html=True,
        )

    with row_cols[1]:
        action_cols = st.columns(3)
        if action_cols[0].button(
            "Close" if st.session_state[toggle_key] else "View",
            key=f"shortlist-view-{job['id']}",
            use_container_width=True,
        ):
            st.session_state[toggle_key] = not st.session_state[toggle_key]
            st.rerun()
        if action_cols[1].button("Approve", key=f"approve-{job['id']}", use_container_width=True):
            st.session_state[PENDING_ACTION_KEY] = ("approve", job["id"])
            st.rerun()
        if action_cols[2].button("Reject", key=f"shortlist-reject-{job['id']}", use_container_width=True):
            st.session_state[PENDING_ACTION_KEY] = ("reject", job["id"])
            st.rerun()

    if st.session_state[toggle_key]:
        try:
            breakdown = client.get(f"/jobs/{job['id']}/score-breakdown")
        except Exception:
            breakdown = None
        render_detail_panel(job, breakdown)
