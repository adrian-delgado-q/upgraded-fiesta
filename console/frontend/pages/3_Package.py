from __future__ import annotations

import html

import streamlit as st

from console.frontend.components.job_display import format_compensation_emphasis, format_job_score
from console.frontend.components.jobs_table import _chip
from console.frontend.styles import apply_shared_styles
from console.frontend.utils import get_client

apply_shared_styles()

client = get_client()

# ── Status colour map ─────────────────────────────────────────────────────
_STATUS_BADGE = {
    "ready_for_review": ("✓ Ready", "comp"),
    "approved": ("✓ Approved", "comp"),
    "queued": ("⧗ Queued", "subtle"),
    "analyzing": ("⧖ Analysing", "subtle"),
    "generating": ("⧖ Generating", "subtle"),
    "validating": ("⧖ Validating", "subtle"),
    "publishing": ("⧖ Publishing", "subtle"),
    "failed": ("✕ Failed", "score"),
}

# ── Sidebar filter ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Package filters")
    status_options = ["All", "ready_for_review", "queued", "analyzing", "generating", "failed"]
    status_filter = st.selectbox(
        "Status",
        status_options,
        index=st.session_state.get("pkg_filter_status_idx", 0),
        key="pkg_filter_status",
    )
    st.session_state["pkg_filter_status_idx"] = status_options.index(status_filter)

# ── Fetch ─────────────────────────────────────────────────────────────────
packages = client.list_packages(
    status=None if status_filter == "All" else status_filter,
    limit=200,
)

# ── Header ────────────────────────────────────────────────────────────────
st.title(f"📦 Package ({len(packages)})")
st.caption("Approved roles land here while their application package is being generated.")

if not packages:
    st.markdown('<div class="console-empty">No package requests match the current filter.</div>', unsafe_allow_html=True)
    st.stop()

# ── Cards ─────────────────────────────────────────────────────────────────
for pkg in packages:
    title = html.escape(pkg.get("title_normalized") or pkg.get("title_raw") or "Untitled")
    company = html.escape(pkg.get("company") or "Unknown")
    location = html.escape(pkg.get("location_raw") or "Unknown")
    url = html.escape(pkg.get("url") or "#", quote=True)
    source = html.escape(pkg.get("source") or "")
    role_family = html.escape(pkg.get("role_family") or "")
    seniority = html.escape(pkg.get("seniority") or "")
    work_mode = html.escape(pkg.get("work_mode") or "")
    compensation = format_compensation_emphasis(pkg)
    score = format_job_score(pkg)
    raw_status = pkg.get("package_status") or "unknown"
    badge_label, badge_cls = _STATUS_BADGE.get(raw_status, (raw_status.replace("_", " ").title(), "subtle"))
    requested_at = str(pkg.get("created_at") or "").replace("T", " ")[:16]

    chips = "".join(
        [
            _chip(badge_label, css_class=badge_cls),
            _chip(compensation, "$", "comp") if compensation != "Salary not listed" else "",
            _chip(f"Score {score}", "#", "score"),
            _chip(role_family, "R") if role_family else "",
            _chip(seniority, "S", "subtle") if seniority else "",
            _chip(work_mode, css_class="subtle") if work_mode else "",
            _chip(source, css_class="subtle") if source else "",
        ]
    )

    st.markdown(
        (
            '<div class="console-card tight">'
            f'<div class="console-card-title"><a href="{url}" target="_blank">{title}</a></div>'
            f'<div class="console-card-meta">{company} · {location}</div>'
            f'<div class="console-card-submeta">Requested {requested_at}</div>'
            f'<div class="console-chip-row">{chips}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

