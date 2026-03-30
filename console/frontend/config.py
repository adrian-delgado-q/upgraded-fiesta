from __future__ import annotations

import os

import streamlit as st


DEFAULT_API_BASE_URL = "http://localhost:8000"


def get_api_base_url() -> str:
    env_value = os.getenv("JOB_CONSOLE_API_BASE_URL")
    if env_value:
        return env_value.rstrip("/")
    try:
        configured_value = st.secrets["api_base_url"]
    except Exception:
        return DEFAULT_API_BASE_URL
    return str(configured_value).rstrip("/") or DEFAULT_API_BASE_URL
