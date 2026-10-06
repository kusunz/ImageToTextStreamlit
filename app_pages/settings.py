"""Settings page: inspect configuration and verify the Gemini model list."""

from __future__ import annotations

import streamlit as st

from core.gemini_client import GeminiError
from core.runtime import list_models, load_settings


def _mask_url(url: str) -> str:
    """Hide credentials embedded in a database URL before display."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        credentials, host = rest.split("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


settings = load_settings()

st.subheader("Configuration")
st.caption("Runtime settings resolved from the environment and Streamlit secrets.")

key_state = "configured" if settings.gemini_api_key else "missing"
st.write(f"Gemini API key: {key_state}")
st.write(f"Database target: {_mask_url(settings.database_url)}")
st.write(f"Model page size: {settings.model_page_size}")

if not settings.gemini_api_key:
    st.warning("Add GEMINI_API_KEY to enable extraction.", icon=":material/key_off:")
    st.stop()

if st.button("Reload model list", icon=":material/refresh:"):
    list_models.clear()
    st.rerun()

try:
    models = list_models(settings.gemini_api_key, settings.model_page_size)
except GeminiError as exc:
    st.error(f"Could not load models: {exc}", icon=":material/error:")
    st.stop()

st.divider()
st.subheader(f"Vision-capable models ({len(models)})")
table = [
    {"Model": str(item["name"]), "Display name": str(item["display_name"])}
    for item in models
]
st.dataframe(table, hide_index=True)
