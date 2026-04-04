from __future__ import annotations

import streamlit as st

from console.frontend.styles import apply_shared_styles
from console.frontend.utils import get_client

st.set_page_config(page_title="Triage Console", layout="wide", page_icon="⬡")
apply_shared_styles()

client = get_client()

st.title("Triage Console")
st.caption("Job evaluation pipeline · review, decide, package.")

# ── Counts ──────────────────────────────────────────────────────────────
try:
    counts = client.get_counts()
    triage = counts.get("triage", {})
    packages = counts.get("packages", {})
except Exception:
    triage = {}
    packages = {}

inbox_count = triage.get("new", 0)
shortlist_count = triage.get("shortlisted", 0)
rejected_count = triage.get("rejected", 0)
queued_count = triage.get("queued_for_package", 0)

pkg_ready = packages.get("ready_for_review", 0)
pkg_in_progress = sum(
    packages.get(s, 0)
    for s in ("queued", "analyzing", "generating", "validating", "publishing")
)

# ── Metric tiles ─────────────────────────────────────────────────────────
cols = st.columns(5, gap="medium")
cols[0].metric("📥 Inbox", inbox_count, help="Jobs awaiting first review")
cols[1].metric("★ Shortlisted", shortlist_count, help="Jobs held for final decision")
cols[2].metric("✓ Pkg Ready", pkg_ready, help="Application packages ready to review")
cols[3].metric("⧗ Pkg In Progress", pkg_in_progress, help="Packages currently being generated")
cols[4].metric("✕ Rejected", rejected_count, help="Rejected jobs · restorable from the Rejected page")

st.divider()

# ── Quick navigation ──────────────────────────────────────────────────────
nav_cols = st.columns(4, gap="medium")

with nav_cols[0]:
    st.markdown("**📥 Inbox**")
    st.caption(f"{inbox_count} fresh jobs awaiting triage. Review scores, open descriptions, shortlist or reject.")
    st.page_link("pages/1_Inbox.py", label="Go to Inbox →")

with nav_cols[1]:
    st.markdown("**★ Shortlist**")
    st.caption(f"{shortlist_count} jobs held for final decision. Approve sends them to Package.")
    st.page_link("pages/2_Shortlist.py", label="Go to Shortlist →")

with nav_cols[2]:
    st.markdown("**📦 Package**")
    st.caption(f"{queued_count + pkg_in_progress} queued · {pkg_ready} ready. Track application package generation.")
    st.page_link("pages/3_Package.py", label="Go to Package →")

with nav_cols[3]:
    st.markdown("**✕ Rejected**")
    st.caption(f"{rejected_count} rejected jobs. Restore any that were dismissed by mistake.")
    st.page_link("pages/5_Rejected.py", label="Go to Rejected →")

st.divider()

# ── Health ────────────────────────────────────────────────────────────────
try:
    health = client.get("/healthz")
    st.caption(f"API · {health.get('status', 'unknown')}")
except Exception as exc:
    st.caption(f"API · unreachable ({exc})")

