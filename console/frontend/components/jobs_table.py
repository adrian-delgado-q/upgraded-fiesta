from __future__ import annotations

import html
from typing import Any

import streamlit as st

from .job_display import compensation_sort_value, format_compensation_emphasis, format_job_score


SELECTION_KEY = "inbox_selected_job_id"
SHORTLIST_SELECTION_KEY = "shortlist_selected_job_id"
SORT_KEY = "inbox_sort_key"
SORT_DIRECTION_KEY = "inbox_sort_direction"
LOCATION_DISPLAY_MAX_CHARS = 50
ROW_COLUMN_WIDTHS = [3.9, 1.8, 1.9, 1.45, 0.8, 1.35]
SORTABLE_COLUMNS = [
    ("score", "Top score"),
    ("title", "Title"),
    ("company", "Company"),
    ("location", "Location"),
    ("compensation", "Compensation"),
    ("role_family", "Role"),
]
DEFAULT_INBOX_ACTIONS = (
    {"name": "toggle_view", "label": "◉", "help": "Open or close details"},
    {"name": "reject", "label": "✕", "help": "Reject role"},
    {"name": "shortlist", "label": "★", "help": "Move role to shortlist"},
)
DEFAULT_SHORTLIST_ACTIONS = (
    {"name": "toggle_view", "label": "◉", "help": "Open or close details"},
    {"name": "approve", "label": "✓", "help": "Approve role into package"},
    {"name": "reject", "label": "✕", "help": "Reject role"},
)


def _truncate(value: str, max_chars: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1].rstrip()}..."


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


def _table_cell(content: str, *, cell_class: str = "", selected: bool = False) -> str:
    classes = ["console-table-cell"]
    if cell_class:
        classes.append(cell_class)
    if selected:
        classes.append("selected")
    return f'<div class="{" ".join(classes)}">{content}</div>'


def _render_table_header() -> None:
    header_cols = st.columns(ROW_COLUMN_WIDTHS, vertical_alignment="center")
    headers = ("Role", "Location", "Signals", "Comp", "Score", "Actions")
    for col, label in zip(header_cols, headers):
        col.markdown(f'<div class="console-table-header-cell">{html.escape(label)}</div>', unsafe_allow_html=True)


def _render_role_cell(job: dict[str, Any], *, selected: bool) -> None:
    title = html.escape(job["title_normalized"] or job["title_raw"] or "Untitled")
    url = html.escape(job["url"] or "#", quote=True)
    company = html.escape(job["company"] or "Unknown")
    open_flag = '<span class="console-inline-flag">Open</span>' if selected else ""
    st.markdown(
        _table_cell(
            (
                '<div class="console-table-role-title">'
                f'<a href="{url}" target="_blank">{title}</a>{open_flag}'
                "</div>"
                f'<div class="console-table-role-subtitle">{company}</div>'
            ),
            cell_class="console-table-role",
            selected=selected,
        ),
        unsafe_allow_html=True,
    )


def _render_text_cell(text: str, *, cell_class: str = "", selected: bool = False) -> None:
    st.markdown(_table_cell(html.escape(text), cell_class=cell_class, selected=selected), unsafe_allow_html=True)


def render_jobs_table(
    jobs: list[dict[str, Any]],
    *,
    selection_key: str = SELECTION_KEY,
    empty_message: str = "No jobs match the current filters.",
    action_specs: tuple[dict[str, str], ...] = DEFAULT_INBOX_ACTIONS,
    enable_sorting: bool = False,
    toolbar_message: str | None = None,
) -> tuple[int | None, tuple[str, int] | None]:
    if not jobs:
        st.session_state.pop(selection_key, None)
        st.markdown(f'<div class="console-empty">{html.escape(empty_message)}</div>', unsafe_allow_html=True)
        return None, None

    if enable_sorting:
        st.session_state.setdefault(SORT_KEY, "score")
        st.session_state.setdefault(SORT_DIRECTION_KEY, "desc")
        jobs = _sorted_jobs(jobs)

    visible_job_ids = {job["id"] for job in jobs}
    selected_id = st.session_state.get(selection_key)
    if selected_id not in visible_job_ids:
        st.session_state.pop(selection_key, None)
        selected_id = None

    if enable_sorting:
        toolbar_cols = st.columns([1.2, 1.4, 1.2, 3.2])
        toolbar_cols[0].markdown('<div class="console-section-label">Sort</div>', unsafe_allow_html=True)
        sort_options = {label: key for key, label in SORTABLE_COLUMNS}
        selected_label = next(label for key, label in SORTABLE_COLUMNS if key == st.session_state.get(SORT_KEY, "score"))
        sort_label = toolbar_cols[1].selectbox(
            "Sort by",
            list(sort_options),
            index=list(sort_options).index(selected_label),
            label_visibility="collapsed",
            key=f"{selection_key}-sort-select",
        )
        chosen_sort_key = sort_options[sort_label]
        if chosen_sort_key != st.session_state.get(SORT_KEY, "score"):
            st.session_state[SORT_KEY] = chosen_sort_key
            st.rerun()
        direction_label = "Descending" if st.session_state.get(SORT_DIRECTION_KEY, "desc") == "desc" else "Ascending"
        if toolbar_cols[2].button(direction_label, key=f"{selection_key}-sort-direction", use_container_width=True):
            _toggle_sort(st.session_state.get(SORT_KEY, "score"))
            st.rerun()
        if toolbar_message:
            toolbar_cols[3].markdown(
                f'<div class="console-toolbar"><strong>{len(jobs)}</strong> jobs in view. {html.escape(toolbar_message)}</div>',
                unsafe_allow_html=True,
            )
    elif toolbar_message:
        st.markdown(
            f'<div class="console-toolbar"><strong>{len(jobs)}</strong> jobs in view. {html.escape(toolbar_message)}</div>',
            unsafe_allow_html=True,
        )

    _render_table_header()
    for job in jobs:
        location = _truncate(job["location_raw"] or "Unknown", LOCATION_DISPLAY_MAX_CHARS)
        signals = " | ".join(
            (
                _truncate(job["source"] or "Unknown", 18),
                _truncate(job["work_mode"] or "Unknown", 18),
                _truncate(job["role_family"] or "Unknown", 18),
            )
        )
        compensation = format_compensation_emphasis(job)
        score_text = format_job_score(job)
        is_selected = selected_id == job["id"]

        row_cols = st.columns(ROW_COLUMN_WIDTHS, vertical_alignment="center")
        with row_cols[0]:
            _render_role_cell(job, selected=is_selected)
        with row_cols[1]:
            _render_text_cell(location, cell_class="console-table-meta", selected=is_selected)
        with row_cols[2]:
            _render_text_cell(signals, cell_class="console-table-meta", selected=is_selected)
        with row_cols[3]:
            _render_text_cell(compensation, cell_class="console-table-comp", selected=is_selected)
        with row_cols[4]:
            st.markdown(
                _table_cell(score_text, cell_class="console-table-score", selected=is_selected),
                unsafe_allow_html=True,
            )
        with row_cols[5]:
            action_cols = st.columns(len(action_specs), gap="small")
            for action_col, action_spec in zip(action_cols, action_specs):
                if action_col.button(
                    action_spec["label"],
                    key=f"{selection_key}-{action_spec['name']}-{job['id']}",
                    use_container_width=True,
                    help=action_spec["help"],
                ):
                    if action_spec["name"] == "toggle_view":
                        if is_selected:
                            st.session_state.pop(selection_key, None)
                            return None, None
                        st.session_state[selection_key] = job["id"]
                        return job["id"], None
                    return selected_id, (action_spec["name"], job["id"])

    return selected_id, None
