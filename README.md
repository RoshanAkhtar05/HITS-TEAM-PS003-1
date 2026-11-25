# TATHYA-DF
**Digital Evidence Correlation & Crime Reconstruction Engine**

TATHYA-DF is an investigator-assistance prototype for organising supported digital evidence, extracting entities and relationships, exploring a case-scoped knowledge graph, reviewing event timelines, and generating a case investigation PDF. Automated outputs are investigative leads and require human verification.

## Quick start (Windows or macOS)

### Requirements
- Python **3.12**
- Node.js **22 LTS** (includes npm)
- Internet connection for first-time dependency installation

### Windows
1. Extract the ZIP to a normal folder (do not run it from inside the ZIP).
2. Double-click `START_WINDOWS.bat`.
3. Allow the first run to install Python and Node dependencies. This can take several minutes.
4. Your browser opens at **http://localhost:5173**.

### macOS
1. Extract the ZIP to a normal folder.
2. Open Terminal in the extracted folder and run once:
   ```bash
   chmod +x START_MAC.command
   ```
3. Double-click `START_MAC.command`.
4. Allow the first run to install dependencies. This can take several minutes.
5. Your browser opens at **http://localhost:5173**.

The launchers create a local Python virtual environment, install the listed dependencies, install the spaCy English model if missing, create `backend/.env` from the safe example file, and open separate backend/frontend terminal windows. Keep both server windows open while using the app.

## Deploy online

For a hosted demonstration, follow [`DEPLOY_ONLINE.md`](DEPLOY_ONLINE.md). The deployment setup uses Render for the API and persistent runtime data, and Vercel for the frontend.

## Manual start (if the launcher is blocked)

### Backend
From the project folder:

**Windows**
```bat
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .env.example .env
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

**macOS**
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend (second terminal)
```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Backend API docs: **http://localhost:8000/docs**.

## Included demo data
- `raw_data/` contains the synthetic multi-source sample files used for demonstration.
- `jumbled_test_input/` contains deliberately messy sample inputs for parser testing.
Use only synthetic or authorised evidence.

## Tests
From the project folder:
```bash
cd backend
python -m unittest discover -s tests -v
```

Frontend production build:
```bash
cd frontend
npm ci
npm run build
```

## What is implemented
- Case creation and evidence upload with SHA-256 digest calculation at upload time.
- Case-scoped staging and source-specific parsers for supported file types.
- Entity extraction, entity resolution, and graph integration.
- Interactive graph inspection with available source references.
- Timeline reconstruction, including unplaced events where timestamps are insufficient.
- Configured rule-based review indicators.
- Case-specific PDF investigation report generation.

## Important prototype limitations
- File parsing depends on supported extensions, filename conventions, and source-specific parser formats; an upload is not guaranteed to be processable.
- SHA-256 records the uploaded bytes; it does not prove pre-upload authenticity or chain of custody.
- Graph links, rule scores, and alerts are investigative leads, not proof of identity, presence, intent, or guilt.
- Timestamp comparisons require timezone and clock-context review.
- The PDF is an investigator-review prototype report, not a certified forensic report.
- Optional Neo4j, PostgreSQL/Supabase, Redis, Ollama, and Gemini integrations are disabled unless configured in `backend/.env`.

## Configuration and data
`backend/.env.example` lists optional integration settings. For hosted frontend deployments, set `VITE_API_BASE_URL` to the deployed backend URL; local development defaults to `http://localhost:8000`. The launcher copies it to `backend/.env` on first run. Do not place real API keys or passwords in the ZIP or publish them to GitHub.

Runtime uploads, case workspaces, and the local SQLite database are generated locally and are not included in this source package.

## Project layout
```text
TATHYA-DF/
├── START_WINDOWS.bat
├── START_MAC.command
├── README.md
├── LICENSE
├── raw_data/
├── jumbled_test_input/
├── backend/
│   ├── api/
│   ├── analysis/
│   ├── db/
│   ├── preprocessor/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    ├── package.json
    └── package-lock.json
```
