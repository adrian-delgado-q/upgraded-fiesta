from __future__ import annotations

import html
from typing import Any

import streamlit as st

from .job_display import compensation_sort_value, format_compensation_emphasis, format_job_score


SELECTION_KEY = "inbox_selected_job_id"
SORT_KEY = "inbox_sort_key"
SORT_DIRECTION_KEY = "inbox_sort_direction"
LOCATION_DISPLAY_MAX_CHARS = 50
SORTABLE_COLUMNS = [
    ("score", "Top score"),
    ("title", "Title"),
    ("company", "Company"),
    ("location", "Location"),
    ("compensation", "Compensation"),
    ("role_family", "Role"),
]


def _chip(text: str, icon: str, chip_class: str = "") -> str:
    klass = f"console-chip {chip_class}".strip()
    return (
        f'<span class="{klass}">'
        f'<span class="console-chip-icon">{html.escape(icon)}</span>'
        f'{html.escape(text)}'
        '</span>'
    )


def _render_job_summary(job: dict[str, Any], location: str, compensation: str, score_text: str, is_selected: bool) -> None:
    title = html.escape(job["title_normalized"] or job["title_raw"] or "Untitled")
    url = html.escape(job["url"] or "#", quote=True)
    company = html.escape(job["company"] or "Unknown")
    location_html = html.escape(location)
    role_family = html.escape(job["role_family"] or "Unknown")
    seniority = html.escape(job["seniority"] or "Unknown")
    work_mode = html.escape(job["work_mode"] or "Unknown")
    source = html.escape(job["source"] or "Unknown")
    selected_html = '<div class="console-card-submeta">Selected for detail view</div>' if is_selected else ""
    st.markdown(
        (
            '<div class="console-card tight">'
            f'<div class="console-card-title"><a href="{url}" target="_blank">{title}</a></div>'
            f'<div class="console-card-meta">{company} | {location_html}</div>'
            '<div class="console-chip-row">'
            f'{_chip(compensation, "$", "comp")}'
            f'{_chip(f"Score {score_text}", "#", "score")}'
            f'{_chip(role_family, "R")}'
            f'{_chip(seniority, "S", "subtle")}'
            f'{_chip(work_mode, "M", "subtle")}'
            f'{_chip(source, "Src", "subtle")}'
            '</div>'
            f'{selected_html}'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

def _truncate(value: str, max_chars: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1].rstrip()}…"


def _sort_value(job: dict[str, Any], sort_key: str) -> Any:
    if sort_key == "title":
        return (job["title_normalized"] or job["title_raw"] or "").lower()
    if sort_key == "company":
        return (job["company"] or "").lower()
    if sort_key == "location":
        return (job["location_raw"] or "").lower()
    if sort_key == "compensation":
        return compensation_sort_value(job)
    if sort_key == "score":
        return float(format_job_score(job))
    if sort_key == "role_family":
        return (job["role_family"] or "").lower()
    return job["id"]


def _sorted_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sort_key = st.session_state.get(SORT_KEY, "score")
    sort_direction = st.session_state.get(SORT_DIRECTION_KEY, "desc")
    reverse = sort_direction == "desc"
    return sorted(jobs, key=lambda job: (_sort_value(job, sort_key), job["id"]), reverse=reverse)


def _toggle_sort(sort_key: str) -> None:
    current_key = st.session_state.get(SORT_KEY, "score")
    current_direction = st.session_state.get(SORT_DIRECTION_KEY, "desc")
    if current_key == sort_key:
        st.session_state[SORT_DIRECTION_KEY] = "asc" if current_direction == "desc" else "desc"
    else:
        st.session_state[SORT_KEY] = sort_key
        st.session_state[SORT_DIRECTION_KEY] = "desc"

def render_jobs_table(jobs: list[dict[str, Any]]) -> tuple[int | None, tuple[str, int] | None]:
    if not jobs:
        st.session_state.pop(SELECTION_KEY, None)
        st.markdown('<div class="console-empty">No jobs match the current inbox filters.</div>', unsafe_allow_html=True)
        return None, None

    st.session_state.setdefault(SORT_KEY, "score")
    st.session_state.setdefault(SORT_DIRECTION_KEY, "desc")
    jobs = _sorted_jobs(jobs)

    visible_job_ids = {job["id"] for job in jobs}
    selected_id = st.session_state.get(SELECTION_KEY)
    if selected_id not in visible_job_ids:
        st.session_state.pop(SELECTION_KEY, None)
        selected_id = None

    toolbar_cols = st.columns([1.2, 1.4, 1.2, 3.2])
    toolbar_cols[0].markdown('<div class="console-section-label">Sort</div>', unsafe_allow_html=True)
    sort_options = {label: key for key, label in SORTABLE_COLUMNS}
    selected_label = next(label for key, label in SORTABLE_COLUMNS if key == st.session_state.get(SORT_KEY, "score"))
    sort_label = toolbar_cols[1].selectbox(
        "Sort by",
        list(sort_options),
        index=list(sort_options).index(selected_label),
        label_visibility="collapsed",
        key="inbox-sort-select",
    )
    chosen_sort_key = sort_options[sort_label]
    if chosen_sort_key != st.session_state.get(SORT_KEY, "score"):
        st.session_state[SORT_KEY] = chosen_sort_key
        st.rerun()
    direction_label = "Descending" if st.session_state.get(SORT_DIRECTION_KEY, "desc") == "desc" else "Ascending"
    if toolbar_cols[2].button(direction_label, key="sort-direction", use_container_width=True):
        _toggle_sort(st.session_state.get(SORT_KEY, "score"))
        st.rerun()
    toolbar_cols[3].markdown(
        f'<div class="console-toolbar"><strong>{len(jobs)}</strong> jobs in view. '
        'Shortlist moves items out of Inbox. Reject hides them everywhere.</div>',
        unsafe_allow_html=True,
    )

    for job in jobs:
        title = job["title_normalized"] or job["title_raw"]
        location = _truncate(job["location_raw"] or "Unknown", LOCATION_DISPLAY_MAX_CHARS)
        compensation = format_compensation_emphasis(job)
        is_selected = selected_id == job["id"]
        score_text = format_job_score(job)
        row_cols = st.columns([6.2, 2.2], vertical_alignment="center")
        with row_cols[0]:
            _render_job_summary(job, location, compensation, score_text, is_selected)

        view_label = "Close" if is_selected else "View"
        with row_cols[1]:
            action_cols = st.columns(3)
            if action_cols[0].button(view_label, key=f"view-{job['id']}", use_container_width=True):
                if is_selected:
                    st.session_state.pop(SELECTION_KEY, None)
                    return None, None
                st.session_state[SELECTION_KEY] = job["id"]
                return job["id"], None
            if action_cols[1].button("Reject", key=f"reject-{job['id']}", use_container_width=True):
                return selected_id, ("reject", job["id"])
            if action_cols[2].button("Shortlist", key=f"shortlist-{job['id']}", use_container_width=True):
                return selected_id, ("shortlist", job["id"])

    return selected_id, None
