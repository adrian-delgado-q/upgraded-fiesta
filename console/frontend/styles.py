from __future__ import annotations

import streamlit as st


SHARED_CSS = """
<style>
    :root {
        --bg: #f4f1ea;
        --panel: #fbf8f2;
        --panel-strong: #ffffff;
        --line: #d8cfbf;
        --text: #1f2b3d;
        --muted: #6f7c8f;
        --accent: #b65c2f;
        --accent-soft: #f2e2d7;
        --success: #355f4a;
        --danger: #8d3b2f;
    }

    .stApp {
        background:
            radial-gradient(circle at top right, rgba(182, 92, 47, 0.08), transparent 28%),
            linear-gradient(180deg, #f8f5ee 0%, #f2eee5 100%);
        color: var(--text);
    }

    .main .block-container {
        max-width: 1420px;
        padding-top: 1.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    .stApp h1, .stApp h2, .stApp h3 {
        color: var(--text);
        letter-spacing: -0.02em;
    }

    .stApp h1 {
        font-size: 3rem;
        margin-bottom: 0.35rem;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ede8dd 0%, #e7e1d5 100%);
        border-right: 1px solid rgba(31, 43, 61, 0.08);
    }

    [data-testid="stSidebar"] .block-container {
        padding-top: 1.1rem;
    }

    [data-testid="stSidebar"] .stSelectbox,
    [data-testid="stSidebar"] .stTextInput,
    [data-testid="stSidebar"] .stCheckbox,
    [data-testid="stSidebar"] .stNumberInput {
        margin-bottom: 0.55rem;
    }

    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stNumberInput input {
        min-height: 2.45rem;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.86);
    }

    [data-testid="stButton"] button {
        min-height: 1.85rem;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.88);
        box-shadow: none;
        font-weight: 600;
        font-size: 0.92rem;
        padding: 0.15rem 0.75rem;
    }

    [data-testid="stButton"] button:hover {
        border-color: #c39b84;
        color: var(--accent);
    }

    [data-testid="stHorizontalBlock"] {
        gap: 0.7rem;
    }

    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid rgba(31, 43, 61, 0.08);
        border-radius: 16px;
        padding: 0.85rem 1rem;
    }

    .console-toolbar {
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(31, 43, 61, 0.08);
        border-radius: 18px;
        padding: 0.45rem 0.85rem;
        margin-bottom: 1rem;
    }

    .console-card {
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(250, 247, 241, 0.98) 100%);
        border: 1px solid rgba(31, 43, 61, 0.1);
        border-radius: 22px;
        padding: 1.05rem 1.2rem;
        box-shadow: 0 8px 28px rgba(31, 43, 61, 0.05);
        margin-bottom: 0.95rem;
    }

    .console-card.tight {
        padding: 0.82rem 0.95rem;
        margin-bottom: 0.55rem;
    }

    .console-card-title {
        font-size: 1.08rem;
        font-weight: 700;
        line-height: 1.35;
        margin-bottom: 0.2rem;
    }

    .console-card-meta {
        color: var(--muted);
        font-size: 0.9rem;
        line-height: 1.35;
    }

    .console-card-submeta {
        color: var(--muted);
        font-size: 0.84rem;
        line-height: 1.35;
        margin-top: 0.3rem;
    }

    .console-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.32rem;
        margin-top: 0.55rem;
    }

    .console-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.28rem;
        border-radius: 999px;
        padding: 0.22rem 0.52rem 0.22rem 0.34rem;
        border: 1px solid rgba(31, 43, 61, 0.08);
        background: rgba(255, 255, 255, 0.82);
        color: var(--text);
        font-size: 0.8rem;
        font-weight: 600;
        white-space: nowrap;
    }

    .console-chip-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.05rem;
        height: 1.05rem;
        border-radius: 999px;
        background: rgba(31, 43, 61, 0.08);
        color: var(--muted);
        font-size: 0.63rem;
        font-weight: 800;
        line-height: 1;
        flex: 0 0 auto;
    }

    .console-chip.comp {
        color: var(--success);
        background: rgba(53, 95, 74, 0.08);
        border-color: rgba(53, 95, 74, 0.18);
    }

    .console-chip.comp .console-chip-icon {
        background: rgba(53, 95, 74, 0.16);
        color: var(--success);
    }

    .console-chip.score {
        color: var(--accent);
        background: rgba(182, 92, 47, 0.09);
        border-color: rgba(182, 92, 47, 0.18);
    }

    .console-chip.score .console-chip-icon {
        background: rgba(182, 92, 47, 0.16);
        color: var(--accent);
    }

    .console-chip.subtle {
        color: var(--muted);
    }

    .console-section-label {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        font-size: 0.74rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }

    .console-empty {
        background: rgba(255, 255, 255, 0.7);
        border: 1px dashed rgba(31, 43, 61, 0.18);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        color: var(--muted);
    }

    .console-page-note {
        color: var(--muted);
        margin-bottom: 0.9rem;
    }
</style>
"""


def apply_shared_styles() -> None:
    st.markdown(SHARED_CSS, unsafe_allow_html=True)
