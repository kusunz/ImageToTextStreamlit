"""Entry point for the image to text Streamlit app."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Image to text",
    page_icon=":material/document_scanner:",
    layout="wide",
)

pages = [
    st.Page("app_pages/extract.py", title="Extract", icon=":material/document_scanner:", default=True),
    st.Page("app_pages/data.py", title="Data", icon=":material/table_view:"),
    st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:"),
]

page = st.navigation(pages, position="top")
page.run()
