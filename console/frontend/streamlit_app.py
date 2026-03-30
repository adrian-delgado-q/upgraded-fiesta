from __future__ import annotations

import streamlit as st

from console.frontend.config import get_api_base_url
from console.frontend.services import ApiClient
from console.frontend.styles import apply_shared_styles


st.set_page_config(page_title="Job Console", layout="wide")
apply_shared_styles()
st.title("Triage Console")
st.write("Inbox surfaces fresh roles only. Shortlist is the decision lane. Approved roles move into Package.")
client = ApiClient(get_api_base_url())
health = client.get("/healthz")
st.success(f"API status: {health['status']}")
