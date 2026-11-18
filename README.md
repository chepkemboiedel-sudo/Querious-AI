# Querious-AI
A transparent self correcting natural language interface for data analysis 
Querious AI lets anyone ask questions about their data in plain English and shows how each answer was found. 

## Run it locally

Querious runs on one machine: a FastAPI backend and a React frontend, with local data files only (no hosted database, no accounts).

### Requirements

- Python 3.12 (on Windows use `py -3.12`; another default `python` version will not work)
- Node.js 22 LTS (22.12 or later) and npm

### Backend (`backend/`)

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest                              # tests use the mock LLM provider only; no network
uvicorn app.main:app --reload       # http://127.0.0.1:8000/health -> {"status": "ok"}
```

### Frontend (`frontend/`)

```powershell
cd frontend
npm ci
npm run dev                         # http://localhost:5173
npm test
npm run build                       # output in frontend/dist/
```

### Import and dependency scan

From the repository root. It fails on a hosted-database driver or account library (H12), a model SDK imported outside `backend/app/llm/` (H13), or an import of `eval/` from `backend/app` (H14). It uses the standard library only.

```powershell
py -3.12 backend/scripts/import_scan.py
```

CI (`.github/workflows/ci.yml`) runs the scan, the backend tests and the frontend tests and build on every pull request into `dev`. It uses no secrets and a read-only token.

## Supported browsers

Current desktop versions of Chrome, Firefox and Edge. Mobile layouts are not supported in the MVP.
