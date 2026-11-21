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

`pytest` skips the slow, local-only timing test (a generated 50 MB CSV must load within 10 seconds, US-01). Run it on request with `pytest -m slow`. CI does not run it.

### Your dataset

One dataset is active at a time. It is stored in the local `data/` folder (not committed; set `QUERIOUS_DATA_DIR` to use another folder) and is still there after a restart. Loading another dataset replaces it.

- `POST /datasets/upload` (form field `file`): one `.csv` file, UTF-8, with a header row and at least one data row, up to 50 MB. Other files are rejected with a message that says why.
- `POST /datasets/sample`: the built-in fictional sample, `customers` and `orders` (`backend/app/pipeline/sample_data/`).
- `GET /datasets/active`: the active dataset's stored profile, or `null`: its name, `fingerprint` (SHA-256 of the loaded file bytes), each table's `row_count` and `columns` (name and inferred DuckDB type), and `examples` (up to five values per text column, for local display on the Data overview only; never sent to the LLM). The upload and sample endpoints return the same shape.

Column names are assumed to be in English (ASSUMPTION-01). This is not enforced.

### Business terms (`semantic_layer.yaml`)

A data steward defines business terms, metrics and allowed joins offline in `semantic_layer.yaml` at the repository root, one section per dataset: `sample` for the built-in sample, or an upload's file name (case is ignored). The format is documented in `backend/app/semantic/schema.py`. Set `QUERIOUS_SEMANTIC_LAYER` to read another file.

- The active dataset's section is checked against its schema every time it becomes active. A definition that refers to a missing table or column, or that the format cannot express, is rejected with a message that names it, and the load fails (the previous dataset stays active).
- A dataset with no section has no terms, metrics or joins. That is not an error.
- `GET /semantic/terms`: every term of the active dataset with its description, plus the semantic-layer `version` recorded for audit, or `null` with no active dataset. No endpoint can edit terms.

### Frontend (`frontend/`)

```powershell
cd frontend
npm ci
npm run dev                         # http://localhost:5173 (start the backend first; /datasets, /semantic
                                    # and /health are proxied to http://127.0.0.1:8000)
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
