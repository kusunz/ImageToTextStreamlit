"""Data page: fast search, view, export, and review filtering of saved product rows."""

from __future__ import annotations

import json
import time
import pandas as pd
import streamlit as st

from core import db
from core.runtime import load_settings

settings = load_settings()

st.subheader("Saved product data")
st.caption("Fast search, tabular review, and JSON export for product data in the database.")

# Backend switcher: choose PostgreSQL or SQLite
backend_options = ["PostgreSQL", "SQLite"] if settings.postgres_url else ["SQLite"]
default_backend = "PostgreSQL" if settings.postgres_url else "SQLite"
selected_backend = st.segmented_control(
    "Active database",
    options=backend_options,
    default=default_backend,
    help="Switch between PostgreSQL and SQLite to view rows stored in each.",
)
active_db_url = settings.resolve_url(selected_backend or default_backend)

with st.form("filters", border=False):
    col_search, col_supplier, col_status, col_limit = st.columns([2, 1, 1, 1])
    with col_search:
        search = st.text_input("Search", placeholder="Product name, code, or notes")
    with col_supplier:
        supplier = st.text_input("Supplier", placeholder="Exact supplier name")
    with col_status:
        review_filter = st.selectbox("Status", options=["All", "Needs review", "Verified"])
    with col_limit:
        limit = st.number_input("Maximum rows", min_value=50, max_value=5000, value=500, step=50)
    submitted = st.form_submit_button("Search", icon=":material/search:")

db.init_db(active_db_url)

needs_review_val = None
if review_filter == "Needs review":
    needs_review_val = True
elif review_filter == "Verified":
    needs_review_val = False

start_time = time.perf_counter()
total = db.count_rows(active_db_url)
needs_review_total = db.count_rows(active_db_url, needs_review=True)
rows = db.fetch_rows(
    active_db_url,
    search=search,
    supplier=supplier,
    needs_review=needs_review_val,
    limit=int(limit),
)
query_duration_ms = (time.perf_counter() - start_time) * 1000

col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
col_metric1.metric("Database backend", selected_backend or default_backend)
col_metric2.metric("Total records", total)
col_metric3.metric("Needs review", needs_review_total)
col_metric4.metric("Query latency", f"{query_duration_ms:.1f} ms")

if not rows:
    st.info("No rows found matching the current filters.", icon=":material/info:")
    st.stop()

tab_table, tab_json = st.tabs(["Table view", "JSON view"])

rows_dict_list = [row.model_dump(mode="json") for row in rows]

with tab_table:
    frame = pd.DataFrame(rows_dict_list)
    display_columns = [
        "source_file",
        "product_name",
        "product_code",
        "quantity",
        "unit",
        "unit_price",
        "total_price",
        "currency",
        "supplier",
        "invoice_number",
        "needs_review",
        "review_notes",
        "extraction_attempts",
        "confidence",
        "notes",
        "extracted_at",
    ]
    available = [column for column in display_columns if column in frame.columns]
    st.dataframe(
        frame[available],
        hide_index=True,
        column_config={
            "needs_review": st.column_config.CheckboxColumn("Needs review"),
            "extraction_attempts": st.column_config.NumberColumn("Attempts"),
            "confidence": st.column_config.NumberColumn("Confidence", format="%.2f"),
            "unit_price": st.column_config.NumberColumn("Unit price", format="%.2f"),
            "total_price": st.column_config.NumberColumn("Total price", format="%.2f"),
        },
    )

    csv_bytes = frame[available].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name="product_rows.csv",
        mime="text/csv",
        icon=":material/download:",
    )

with tab_json:
    st.caption("JSON representation of the retrieved records.")
    st.json(rows_dict_list)
    json_bytes = json.dumps(rows_dict_list, indent=2, ensure_ascii=False).encode("utf-8")
    st.download_button(
        "Download JSON",
        data=json_bytes,
        file_name="product_rows.json",
        mime="application/json",
        icon=":material/download:",
    )
