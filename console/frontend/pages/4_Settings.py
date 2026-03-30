from __future__ import annotations

import streamlit as st

from console.frontend.config import get_api_base_url
from console.frontend.services import ApiClient
from console.frontend.styles import apply_shared_styles


client = ApiClient(get_api_base_url())
apply_shared_styles()
st.title("Settings")
current = client.get("/settings")
st.caption("Collector runtime and rules metadata")
st.json(current)
