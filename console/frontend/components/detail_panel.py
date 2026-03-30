from __future__ import annotations

from typing import Any

import streamlit as st

from .job_display import format_compensation, format_compensation_badge


def render_detail_panel(job: dict[str, Any], breakdown: dict[str, Any] | None) -> None:
    score_value = round(job.get("final_score") or job.get("deterministic_score") or 0, 1)
    recommendation = (job.get("recommendation") or "unknown").replace("_", " ")
    st.markdown(f"### {job['title_normalized'] or job['title_raw']}")
    st.caption(f"{job['company']} | {job['location_raw'] or 'Unknown'} | {job['source']}")
    summary_cols = st.columns(4)
    summary_cols[0].metric("Compensation", format_compensation_badge(job))
    summary_cols[1].metric("Score", f"{score_value:.1f}")
    summary_cols[2].metric("Role", job["role_family"] or "Unknown")
    summary_cols[3].metric("Seniority", job["seniority"] or "Unknown")
    meta_cols = st.columns(3)
    meta_cols[0].metric("Work Mode", job["work_mode"] or "Unknown")
    meta_cols[1].metric("Status", job["triage_status"])
    meta_cols[2].metric("Recommendation", recommendation.title())

    description_text = (job.get("description_text") or "").strip()
    if description_text:
        with st.expander("Job Description", expanded=False):
            st.text(description_text)
    if breakdown:
        explanation = breakdown.get("explanation_json") or {}
        if isinstance(explanation, str):
            explanation = {}
        st.markdown("#### Decision Summary")
        decision_cols = st.columns(2)
        with decision_cols[0]:
            st.markdown("**Category Scores**")
            st.json(explanation.get("category_scores", {}))
        with decision_cols[1]:
            st.markdown("**Hard Rejects**")
            hard_rejects = explanation.get("hard_rejects", [])
            if hard_rejects:
                st.write("\n".join(f"- {item}" for item in hard_rejects))
            else:
                st.caption("None")
        with st.expander("Signal Groups", expanded=False):
            st.json(explanation.get("signal_groups", {}))
    with st.expander("Structured Payloads", expanded=False):
        st.json(
            {
                "normalized_facets": job.get("normalized_facets_json", {}),
                "profile_signals": job.get("profile_signals_json", {}),
                "extraction": job.get("extraction_json", {}),
                "score_breakdown": breakdown or {},
            }
        )
