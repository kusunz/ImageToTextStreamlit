# Local Deployment Guide

Step-by-step instructions to run the application on a local development machine.

## Prerequisites

- Git
- Docker and Docker Compose (recommended), or Python 3.11+
- Google Gemini API key from https://aistudio.google.com/apikey

## Step 1: Clone Repository

```bash
git clone https://github.com/kusunz/ImageToTextStreamlit.git
cd ImageToTextStreamlit
```

## Step 2: Configure Environment

Copy the environment template:

Linux or macOS:
```bash
cp .env.example .env
```

Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

Edit `.env` and set your API key:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
APP_PORT=8502
```

## Step 3: Deployment Options

### Option A: Docker Compose (Recommended)

Runs the Streamlit web app and PostgreSQL 17 in isolated containers.

1. Build and start services:
```bash
docker compose up --build -d
```

2. Check container status:
```bash
docker compose ps
```

3. Open in browser:
```
http://localhost:8502
```

4. Stop services:
```bash
docker compose down
```

### Option B: Bare-Metal Python (SQLite Mode)

Runs directly using local Python and the built-in SQLite database.

1. Create and activate a virtual environment:

Linux or macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
streamlit run streamlit_app.py --server.port 8502
```

4. Open in browser:
```
http://localhost:8502
```

## Step 4: Verification Workflow

1. Open the Extract page in your browser.
2. Select target database (PostgreSQL or SQLite).
3. Primary model is set to Gemini 3.5 Flash Lite (`gemini-3.5-flash-lite`).
4. Cross-check model is set to Gemma 4 26B (`gemma-4-26b`).
5. Upload an image or multiple images.
6. Click Extract and verify.
7. Review table or inspect raw JSON.
8. Click Save to database.
9. Verify stored records in the Data page, filter by review status, or export to CSV and JSON.

## Step 5: Offline Tests

Run test suite without calling external APIs:

```bash
pytest
```
