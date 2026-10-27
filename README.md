# KrishiMitra

KrishiMitra is a three-module agricultural decision-support application for Indian farmers. It combines a React and TypeScript web interface, a FastAPI service, PostgreSQL with pgvector, and local crop-image inference.

## Modules

1. **Crop Health** — analyses a leaf photo with a MobileNetV2 model. The included model supports Tomato, Potato, Maize and Grape across ten trained health/disease labels.
2. **Soil and Crop Planning** — uses a selected location to retrieve mapped soil context and current/forecast weather, then compares up to three crops using published agronomic and economic benchmarks. Farmers do not need to enter soil measurements or provide a Soil Health Card.
3. **Gemini Agronomy Advisor** — retrieves relevant reviewed passages, then asks Gemini to compose an English answer using those passages as supporting context and its broader agronomy knowledge. Translation and multilingual controls are not part of the current app.

The web app also supports importing a soil report, editing recognized values, and saving reports locally. See [`docs/`](docs/) for module methods, data sources, setup notes, limitations and screenshots. The final report and system-design document are in [`documents/`](documents/). See [`docs/local-advisor.md`](docs/local-advisor.md) for advisor behavior and source handling.

## Run on Windows

Install Python 3.12, Node.js LTS and Docker Desktop, then clone this repository and open its folder. Copy `backend/.env.example` to `backend/.env` and add a private `GEMINI_API_KEY`. The key is used only by the backend for answer generation, translation and server-side speech transcription; keep it out of Git and frontend files.

Double-click `Start-KrishiMitra.cmd`. The first run creates the Python environment, installs missing dependencies, starts PostgreSQL + pgvector, applies database migrations and launches the frontend and backend. Later runs reuse installed packages. Use `Stop-KrishiMitra.cmd` to stop the app and database while preserving database data.

- Web app: <http://127.0.0.1:5173>
- API documentation: <http://127.0.0.1:8000/docs> (the launcher may select port 8001 if 8000 is occupied)
- PostgreSQL: `127.0.0.1:5433`
- Logs: `.codex-finalizer/logs/`

Live soil, weather, geocoding and Gemini features need internet access. Module 2 does not require a Soil Health Card API key. Retrieved agriculture passages support Gemini's answer but do not constrain it to verbatim source text. Check [`docs/module-2.md`](docs/module-2.md) for crop-planning datasets and assumptions.

## Development checks

```powershell
cd backend
python -m pytest
cd ..\frontend
npm ci
npm test
npm run typecheck
npm run build
```

## Data and limitations

The trained Module 1 checkpoint is included so predictions work after cloning; training datasets and generated model outputs are excluded. Crop-health labels are limited to the ten listed classes and are not a field-validated diagnosis. Soil maps and crop economics are area-level screening benchmarks, not current field measurements or guaranteed profit predictions. The chat can only answer from its ingested sources and may abstain or miss relevant material. Confirm important decisions with local agricultural experts.
