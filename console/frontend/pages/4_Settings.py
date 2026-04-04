from __future__ import annotations

import streamlit as st

from console.frontend.styles import apply_shared_styles
from console.frontend.utils import get_client

apply_shared_styles()

client = get_client()

st.title("⚙ Settings")
st.caption("Adjust the active profile and scoring thresholds. Changes are written to config files immediately.")

try:
    settings = client.get_settings()
except Exception as exc:
    st.error(f"Could not load settings: {exc}")
    st.stop()

active_profile: str = settings.get("active_profile", "")
available_profiles: list[str] = settings.get("available_profiles", [active_profile])
thresholds: dict = settings.get("scoring_thresholds", {})

# ── Active profile ────────────────────────────────────────────────────────
st.subheader("Active profile")
st.caption("The scoring profile controls which rules and weights apply during evaluation.")

profile_idx = available_profiles.index(active_profile) if active_profile in available_profiles else 0
chosen_profile = st.selectbox(
    "Profile",
    available_profiles,
    index=profile_idx,
    key="settings_profile_select",
)

if chosen_profile != active_profile:
    if st.button("Save profile", key="settings_profile_save"):
        try:
            client.set_active_profile(chosen_profile)
            st.success(f"Active profile set to **{chosen_profile}**. Restart the API for changes to take full effect.")
            st.rerun()
        except RuntimeError as exc:
            st.error(f"Failed: {exc}")

st.divider()

# ── Scoring thresholds ────────────────────────────────────────────────────
st.subheader("Scoring thresholds")
st.caption(
    "Jobs scoring above **Shortlisted** are auto-recommended for shortlisting. "
    "LLM analyse threshold sets the minimum score to trigger deep analysis."
)

with st.form("thresholds_form"):
    t_shortlisted = st.slider(
        "Shortlisted threshold",
        min_value=0.0,
        max_value=1.0,
        value=float(thresholds.get("shortlisted", 0.7)),
        step=0.01,
        format="%.2f",
    )
    t_review = st.slider(
        "Review threshold",
        min_value=0.0,
        max_value=1.0,
        value=float(thresholds.get("review", 0.5)),
        step=0.01,
        format="%.2f",
    )
    t_maybe = st.slider(
        "Maybe threshold",
        min_value=0.0,
        max_value=1.0,
        value=float(thresholds.get("maybe", 0.3)),
        step=0.01,
        format="%.2f",
    )
    t_llm = st.slider(
        "LLM analyse threshold",
        min_value=0.0,
        max_value=1.0,
        value=float(thresholds.get("llm_analyze_threshold", 0.4)),
        step=0.01,
        format="%.2f",
    )
    submitted = st.form_submit_button("Save thresholds")

if submitted:
    try:
        client.set_thresholds(
            shortlisted=t_shortlisted,
            review=t_review,
            maybe=t_maybe,
            llm_analyze_threshold=t_llm,
        )
        st.success("Thresholds saved. New scores computed on next pipeline run.")
    except RuntimeError as exc:
        st.error(f"Failed: {exc}")

st.divider()

# ── Read-only info ────────────────────────────────────────────────────────
st.subheader("Runtime info")
info_cols = st.columns(3)
info_cols[0].metric("LLM provider", settings.get("llm", {}).get("provider", "—"))
info_cols[1].metric("LLM model", settings.get("llm", {}).get("model", "—"))
info_cols[2].metric(
    "LLM enabled",
    "Yes" if settings.get("llm", {}).get("enabled") else "No",
)

providers = settings.get("scraper_defaults", {}).get("providers", [])
if providers:
    st.caption(f"Scraper providers: {', '.join(providers)}")

