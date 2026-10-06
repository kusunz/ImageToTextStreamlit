"""Extract page: upload images, run Gemini vision, cross-check review, and save to the database."""

from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from core import db, gemini_client
from core.extract import ImageInput, extract_batch, image_hash
from core.gemini_client import GeminiError, guess_mime_type
from core.runtime import get_client, list_models, load_settings
from core.schema import ExtractedRow

REVIEW_COLUMNS = [
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
    "confidence",
    "needs_review",
    "review_notes",
    "extraction_attempts",
    "notes",
]

CURRENCY_OPTIONS = ["VND", "USD", "EUR", "JPY", "KRW", "CNY", "THB", "UNKNOWN"]


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _hash_for_file(source_file: str, review_rows: list[dict[str, object]]) -> str:
    for row in review_rows:
        if str(row.get("source_file", "")) == source_file:
            return str(row.get("image_hash", ""))
    return image_hash(source_file.encode("utf-8"))


settings = load_settings()

st.subheader("Extract product data from images")
st.caption(
    "Primary extraction via Gemini 3.5 Flash Lite, cross-checked with Gemma 4 26B. "
    "Incomplete data triggers an automatic second-pass re-read; unresolved items are marked for manual review."
)

if not settings.gemini_api_key:
    st.warning(
        "No Gemini API key configured. Add GEMINI_API_KEY to .env or .streamlit/secrets.toml, then reload.",
        icon=":material/key_off:",
    )
    st.stop()

# Database selection (supports both SQLite and Postgres)
backend_options = ["PostgreSQL", "SQLite"] if settings.postgres_url else ["SQLite"]
default_backend = "PostgreSQL" if settings.postgres_url else "SQLite"
selected_backend = st.segmented_control(
    "Target database",
    options=backend_options,
    default=default_backend,
    help="Choose which database to save results into (both SQLite and PostgreSQL supported).",
)
active_db_url = settings.resolve_url(selected_backend or default_backend)

uploaded = st.file_uploader(
    "Image files",
    type=["png", "jpg", "jpeg", "webp", "heic", "heif"],
    accept_multiple_files=True,
    help="Select one file or many files. Multiple selection works like a folder upload.",
)

# Model configuration
col_primary, col_review = st.columns(2)

try:
    model_options = list_models(settings.gemini_api_key, settings.model_page_size)
except GeminiError as exc:
    st.error(f"Could not load the model list: {exc}", icon=":material/error:")
    st.stop()

model_names = [str(item["name"]) for item in model_options]
labels = {str(item["name"]): str(item["display_name"]) for item in model_options}

# Default index for primary model: gemini-3.5-flash-lite
default_primary_idx = 0
if gemini_client.PRIMARY_MODEL_NAME in model_names:
    default_primary_idx = model_names.index(gemini_client.PRIMARY_MODEL_NAME)

with col_primary:
    selected_primary_model = st.selectbox(
        "Primary vision model",
        options=model_names,
        index=default_primary_idx,
        format_func=lambda name: labels.get(name, name),
        help="Primary model for image OCR and extraction (Gemini 3.5 Flash Lite).",
    )

with col_review:
    selected_review_model = st.text_input(
        "Text review model",
        value=gemini_client.REVIEW_MODEL_NAME,
        help="Text-to-text cross-check audit model (Gemma 4 26B).",
    )

temperature = st.slider(
    "Creativity",
    min_value=0.0,
    max_value=1.0,
    value=0.0,
    step=0.1,
    help="Keep at 0 for strict literal reading.",
)

run = st.button(
    "Extract and verify",
    type="primary",
    icon=":material/document_scanner:",
    disabled=not uploaded,
)

if run and uploaded:
    images: list[ImageInput] = []
    for item in uploaded:
        try:
            mime = guess_mime_type(item.name, getattr(item, "type", None))
        except GeminiError as exc:
            st.warning(str(exc))
            continue
        images.append(ImageInput(filename=item.name, data=item.getvalue(), mime_type=mime))

    if not images:
        st.error("No supported images to process.", icon=":material/error:")
        st.stop()

    client = get_client(settings.gemini_api_key)
    progress = st.progress(0.0, text="Starting extraction and cross-check")
    collected: list[ExtractedRow] = []
    raw_json_list: list[dict[str, object]] = []
    errors: list[str] = []
    total = len(images)
    total_rereads = 0
    total_needs_review = 0

    for index, image in enumerate(images, start=1):
        progress.progress(
            (index - 1) / total,
            text=f"Processing {image.filename} ({index}/{total})",
        )
        outcome = extract_batch(
            client=client,
            model_name=selected_primary_model,
            images=[image],
            review_model=selected_review_model,
            temperature=temperature,
        )
        collected.extend(outcome.rows)
        raw_json_list.extend(outcome.raw_extractions)
        errors.extend(outcome.errors)
        total_rereads += outcome.reread_count
        total_needs_review += outcome.needs_review_count

    progress.progress(1.0, text="Extraction and verification complete")

    st.session_state["review_rows"] = [row.model_dump() for row in collected]
    st.session_state["review_json"] = raw_json_list
    st.session_state["review_errors"] = errors
    st.session_state["review_model"] = selected_primary_model
    st.session_state["cross_check_model"] = selected_review_model
    st.session_state["total_rereads"] = total_rereads
    st.session_state["total_needs_review"] = total_needs_review

errors = st.session_state.get("review_errors", [])
for message in errors:
    st.warning(message)

review_rows: list[dict[str, object]] = st.session_state.get("review_rows", [])
review_json: list[dict[str, object]] = st.session_state.get("review_json", [])

if review_rows:
    st.divider()

    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Extracted items", len(review_rows))
    m_col2.metric("Re-reads triggered", st.session_state.get("total_rereads", 0))
    m_col3.metric("Needs review", st.session_state.get("total_needs_review", 0))

    tab_table, tab_json = st.tabs(["Table review", "Structured JSON"])

    with tab_table:
        st.caption("Review extracted products. Incomplete items are flagged under 'Needs review'.")
        frame = pd.DataFrame(review_rows)
        for column in REVIEW_COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        frame = frame[REVIEW_COLUMNS]

        edited = st.data_editor(
            frame,
            key="review_editor",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "source_file": st.column_config.TextColumn("File", disabled=True),
                "product_name": st.column_config.TextColumn("Product name"),
                "product_code": st.column_config.TextColumn("Code"),
                "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, format="%.2f"),
                "unit": st.column_config.TextColumn("Unit"),
                "unit_price": st.column_config.NumberColumn("Unit price", format="%.2f"),
                "total_price": st.column_config.NumberColumn("Total price", format="%.2f"),
                "currency": st.column_config.SelectboxColumn("Currency", options=CURRENCY_OPTIONS),
                "supplier": st.column_config.TextColumn("Supplier"),
                "invoice_number": st.column_config.TextColumn("Invoice"),
                "confidence": st.column_config.NumberColumn(
                    "Confidence", min_value=0.0, max_value=1.0, format="%.2f"
                ),
                "needs_review": st.column_config.CheckboxColumn("Needs review"),
                "review_notes": st.column_config.TextColumn("Review notes"),
                "extraction_attempts": st.column_config.NumberColumn("Attempts", disabled=True),
                "notes": st.column_config.TextColumn("Notes"),
            },
        )

        st.caption(f"{int(edited.shape[0])} product lines ready to save into {selected_backend or default_backend}.")

        if st.button("Save to database", type="primary", icon=":material/save:"):
            model_name = str(st.session_state.get("review_model", selected_primary_model))
            review_mdl = str(st.session_state.get("cross_check_model", selected_review_model))
            records: list[ExtractedRow] = []
            for position, raw in edited.iterrows():
                source_file = str(raw.get("source_file", "") or "")
                content_hash = _hash_for_file(source_file, review_rows)
                try:
                    records.append(
                        ExtractedRow(
                            source_file=source_file,
                            image_hash=content_hash,
                            model_name=model_name,
                            supplier=str(raw.get("supplier", "") or ""),
                            invoice_number=str(raw.get("invoice_number", "") or ""),
                            product_name=str(raw.get("product_name", "") or ""),
                            product_code=str(raw.get("product_code", "") or ""),
                            quantity=float(raw.get("quantity", 0) or 0),
                            unit=str(raw.get("unit", "") or ""),
                            unit_price=_optional_float(raw.get("unit_price")),
                            total_price=_optional_float(raw.get("total_price")),
                            currency=str(raw.get("currency", "UNKNOWN") or "UNKNOWN"),
                            notes=str(raw.get("notes", "") or ""),
                            confidence=float(raw.get("confidence", 0) or 0),
                            needs_review=bool(raw.get("needs_review", False)),
                            review_notes=str(raw.get("review_notes", "") or ""),
                            extraction_attempts=int(raw.get("extraction_attempts", 1) or 1),
                            cross_check_model=review_mdl,
                        )
                    )
                except (TypeError, ValueError):
                    st.warning(f"Skipped an invalid row at position {position}.")
            db.init_db(active_db_url)
            inserted, updated = db.upsert_rows(active_db_url, records)
            st.success(f"Saved {inserted} new rows and updated {updated} existing rows into {selected_backend or default_backend}.")
            st.session_state["review_rows"] = []
            st.session_state["review_json"] = []
            st.session_state["review_errors"] = []

    with tab_json:
        st.caption("Raw structured JSON returned by Google Gemini and cross-checked by Gemma.")
        if review_json:
            st.json(review_json)
            json_str = json.dumps(review_json, indent=2, ensure_ascii=False)
            st.download_button(
                "Download JSON",
                data=json_str.encode("utf-8"),
                file_name="extracted_products.json",
                mime="application/json",
                icon=":material/download:",
            )
        else:
            st.info("No raw JSON data available for this batch.")
