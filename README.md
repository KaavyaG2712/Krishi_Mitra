# KrishiMitra

KrishiMitra is a local agricultural decision-support web application. Review 3 implements two evidence-focused modules:

- Crop Health Intelligence — classifies an uploaded leaf image across 10 approved labels.
- Citation-Grounded Agronomy Advisor — answers in-domain questions only from retrieved official agricultural material.

## Development approach

During development, run PostgreSQL + pgvector in Docker and run FastAPI and the React/Vite frontend directly in separate terminals. This keeps code changes fast to inspect. A complete Docker Compose stack will be added for the final reproducible demonstration.

## Prerequisites

- Git
- Python 3.12
- Node.js LTS (already detected locally)
- Docker Desktop with the WSL 2 backend enabled

## Start the database

From the repository root in PowerShell:

```powershell
docker compose up -d db
docker compose ps
```

The local database is available at `localhost:5432`. Its development-only credentials are in `compose.yaml`; they are not for deployment.

## Start the backend

In a second PowerShell window:

```powershell
cd C:\Users\Ajay\OneDrive\Documents\ChatGPT\proj1\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` and run the `GET /api/v1/health` endpoint. Run backend tests with `pytest`.

Do not put a real Gemini key in Git. Later, place it only in `backend/.env`.

## Project status

Phase 1 has established the repository safeguards and backend starting point. The next implementation increment is the database schema and Alembic migration for model, scan, document, chunk, conversation, message, and citation provenance.
