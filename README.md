# Image to text (Streamlit + Gemini 3.5 Flash Lite + Gemma 4 26B)

Local Streamlit app that reads product information and quantity from images
using Google Gemini 3.5 Flash Lite, cross-checks results with Gemma 4 26B,
and persists verified data into PostgreSQL or SQLite.

## Features

- Primary extraction with Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite`).
- Text-to-text quality cross-check with Gemma 4 26B (`gemma-4-26b`).
- Automatic second-pass re-read when product name, quantity, or unit is missing.
- Flags persistent incomplete items as Needs Review for manual inspection.
- Auto-fetches live vision-capable model list from Google Gemini API.
- Strict English prompts for high OCR accuracy and schema conformance.
- Fast tabular review and JSON inspection with download buttons.
- Supports both PostgreSQL (with connection pooling) and SQLite (WAL mode).
- Deduplicates rows by image hash, product code, and product name.

## Project layout

```
streamlit_app.py          Entry point with st.navigation
app_pages/                Extract, Data, and Settings pages
core/                     Config, Gemini client, schema, database, services
tests/                    Offline tests for parsing, review, and DB behavior
Dockerfile                Container image for the app
docker-compose.yml        App plus Postgres services
```

## Configuration

Copy `.env.example` to `.env` and set values, or use
`.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`).

| Variable | Purpose |
| --- | --- |
| GEMINI_API_KEY | Gemini API key from AI Studio. Required. |
| DATABASE_URL | SQLAlchemy URL. Empty uses the SQLite file at data/app.db. |
| GEMINI_MODEL_PAGE_SIZE | Maximum number of models to request. Default 200. |

For Postgres use `postgresql+psycopg://user:pass@host:5432/dbname`
(psycopg v3 driver).

## Run locally on the host

```
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Run on the VM with Docker

All execution and testing must run on the VM:

```
docker compose up --build -d
docker compose logs -f app
```

The app is served on port 8502. Compose starts Postgres and points the app at
it automatically. Set GEMINI_API_KEY in `.env` before starting.

To stop:

```
docker compose down
```

## Tests

Offline tests do not call the Gemini API:

```
python -m pytest
```
