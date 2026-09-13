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

If `docker pull` reports a missing `docker-credential-desktop` helper, remove only the broken `"credsStore": "desktop"` line from `C:\Users\<your-user>\.docker\config.json` after making a backup. This is only appropriate when Docker Desktop has no credential-helper executable and the config has no saved registry credentials.

## Start the backend

In a second PowerShell window:

```powershell
cd C:\Users\Ajay\OneDrive\Documents\ChatGPT\proj1\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ml]"
Copy-Item .env.example .env
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` and run the `GET /api/v1/health` endpoint. After training has produced the local model artefact, use `POST /api/v1/health/predict` to upload a leaf image. Every accepted prediction stores a scan ID, model version, confidence, label, and SHA-256 image reference in PostgreSQL; the uploaded image itself is not stored.

Do not put a real Gemini key in Git. Later, place it only in `backend/.env`.

## Prepare and train the crop-health model

After the PlantVillage subset has been prepared, create a deterministic split manifest from the repository root:

```powershell
py -3.12 data\create_splits.py `
  --dataset-root data\processed\plantvillage_10class `
  --output data\splits\plantvillage_10class.csv
```

Install the backend's ML dependencies and run the baseline training:

```powershell
cd C:\Users\Ajay\OneDrive\Documents\ChatGPT\proj1\backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,ml]"
python scripts\train_crop_health.py `
  --dataset-root ..\data\processed\plantvillage_10class `
  --manifest ..\data\splits\plantvillage_10class.csv `
  --output-dir ..\models\checkpoints\mobilenetv2-10class-v1 `
  --cpu
```

The first training run downloads ImageNet-pretrained MobileNetV2 weights. It selects the checkpoint using validation macro-F1, then records independent test metrics and CPU latency locally.

## Project status

Module 1 now supports the full local flow: browser → FastAPI → MobileNetV2 model → PostgreSQL → browser. Its controlled PlantVillage test macro-F1 is 0.9863; that result must not be treated as a claim about real field photographs.

The initial Review 3 database migration also creates the provenance tables needed for Module 3. The next increment is ingesting reviewed official documents and implementing retrieval with citations.
