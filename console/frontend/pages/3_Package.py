from __future__ import annotations

import html

import streamlit as st

from console.frontend.components.job_display import format_compensation_emphasis, format_job_score
from console.frontend.components.jobs_table import _chip
from console.frontend.config import get_api_base_url
from console.frontend.services import ApiClient
from console.frontend.styles import apply_shared_styles


client = ApiClient(get_api_base_url())
apply_shared_styles()

st.title("Package")
st.markdown(
    '<div class="console-page-note">Approved shortlist items land here while their package request is queued or being worked.</div>',
    unsafe_allow_html=True,
)

packages = client.get("/packages", {"limit": 100})
if not packages:
    st.markdown('<div class="console-empty">No package requests yet.</div>', unsafe_allow_html=True)

for package in packages:
    title = html.escape(package["title_normalized"] or package["title_raw"] or "Untitled")
    compensation = format_compensation_emphasis(package)
    score = format_job_score(package)
    requested_at = html.escape(str(package.get("created_at") or "").replace("T", " ").replace("+00:00", " UTC"))
    url = html.escape(package["url"] or "#", quote=True)
    company = html.escape(package["company"] or "Unknown")
    location = html.escape(package["location_raw"] or "Unknown")
    package_status = html.escape(package["package_status"] or "unknown")
    role_family = html.escape(package["role_family"] or "Unknown")
    seniority = html.escape(package["seniority"] or "Unknown")
    source = html.escape(package["source"] or "Unknown")
    st.markdown(
        (
            '<div class="console-card tight">'
            f'<div class="console-card-title"><a href="{url}" target="_blank">{title}</a></div>'
            f'<div class="console-card-meta">{company} | {location}</div>'
            f'<div class="console-card-submeta">Status: {package_status} | Requested: {requested_at}</div>'
            '<div class="console-chip-row">'
            f'{_chip(compensation, "$", "comp")}'
            f'{_chip(f"Score {score}", "#", "score")}'
            f'{_chip(role_family, "R")}'
            f'{_chip(seniority, "S", "subtle")}'
            f'{_chip(source, "Src", "subtle")}'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
