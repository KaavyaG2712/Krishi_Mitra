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

## One-click local start (Windows)

After the initial Python and Node.js setup, double-click [Start-KrishiMitra.cmd](Start-KrishiMitra.cmd) in File Explorer. It will start the PostgreSQL + pgvector database, wait for it to become ready, apply Alembic migrations, and open separate PowerShell windows for the FastAPI backend and React frontend.

You can also run it from the repository root in PowerShell:

```powershell
.\Start-KrishiMitra.cmd
```

On a newly cloned repository, use the setup variant once. It creates `backend/.venv`, installs the backend packages, and runs `npm ci` from the checked-in lockfile if those dependencies are missing:

```powershell
.\scripts\Start-KrishiMitra.ps1 -InstallMissing
```

Add `-OpenBrowser` to open the website automatically after launch. The normal launcher deliberately reuses an existing virtual environment and `node_modules` rather than reinstalling packages every time. It never overwrites an existing `backend/.env`; if that file is absent, it creates it from `backend/.env.example`.

The launcher leaves an already-listening server on port `8000` or `5173` alone, so it is safe to run again. Open `http://localhost:5173` for the web app and `http://127.0.0.1:8000/docs` for the API documentation. Close the Backend or Frontend PowerShell window to stop that server; run `docker compose down` from the repository root to stop the database without deleting its data.

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

### Crop Health limitations and safe use

`Crop Hint` means **Expected crop**. It is a cross-check: the model predicts the crop from the image, then compares it with the crop selected by the user. A mismatch is marked uncertain and must not be used as a diagnosis. It is deliberately not used to force the output into the selected crop, because doing so could turn a potato image into a misleading tomato result.

Version `mobilenetv2-10class-v1` can only distinguish these conditions: Tomato (Healthy, Early Blight, Late Blight), Potato (Healthy, Early Blight, Late Blight), Maize (Healthy, Common Rust), and Grape (Healthy, Black Rot). It has **no Northern Leaf Blight class**, so a northern-leaf-blight photo may be forced into the closest known maize class with a high softmax score. That score is relative to the limited known labels, not proof that the disease is Common Rust. The app rejects grayscale images because its model was trained with colour images only.

To recognise Northern Leaf Blight reliably, add a labeled Northern Leaf Blight class (and representative field photos/negative examples), retrain, calibrate on held-out field data, and evaluate an explicit unknown/out-of-distribution rejection rule before publishing a new model version.

The initial Review 3 database migration also creates the provenance tables needed for Module 3. The next increment is ingesting reviewed official documents and implementing retrieval with citations.
