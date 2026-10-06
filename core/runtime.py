"""Shared cached runtime resources for the Streamlit app."""

from __future__ import annotations

import streamlit as st
from google import genai

from core import gemini_client
from core.config import Settings, get_settings


@st.cache_resource(show_spinner=False)
def load_settings() -> Settings:
    """Load settings once per server process."""
    return get_settings()


@st.cache_resource(show_spinner=False)
def get_client(api_key: str) -> genai.Client:
    """Create and cache a Gemini client keyed by API key."""
    return gemini_client.build_client(api_key)


@st.cache_data(ttl="10m", max_entries=8, show_spinner=False)
def list_models(api_key: str, page_size: int) -> list[dict[str, object]]:
    """List vision-capable models, cached to keep the UI responsive."""
    client = get_client(api_key)
    models = gemini_client.list_vision_models(client, page_size=page_size)
    return [
        {
            "name": model.name,
            "display_name": model.display_name,
            "supports_image": model.supports_image,
        }
        for model in models
    ]
