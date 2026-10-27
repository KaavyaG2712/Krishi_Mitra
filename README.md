# KrishiMitra

KrishiMitra is an agricultural decision-support web application with crop-health analysis, soil and crop planning, and a multilingual agronomy advisor.

## Production deployment

### Frontend — Cloudflare Pages

Connect this GitHub repository to Cloudflare Pages and use:

- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`
- Build environment variable: `VITE_API_BASE_URL=https://<render-service>.onrender.com/api/v1`

### API — Render

Create a Render Web Service from this repository and a Render PostgreSQL database in the same region. Use:

- Root directory: `backend`
- Python version: `3.12.11`
- Build command: `pip install ".[ml,corpus,crop-benchmark]"`
- Pre-deploy command: `alembic upgrade head`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/v1/health`

Set these backend environment variables in Render:

- `ENVIRONMENT=production`
- `PYTHON_VERSION=3.12.11`
- `DATABASE_URL` to the database's internal URL, changing its prefix from `postgresql://` to `postgresql+psycopg://`
- `FRONTEND_ORIGINS` to the exact Cloudflare Pages origin, such as `https://<project>.pages.dev`
- `SIGNING_SECRET` to a private random value of at least 32 characters
- `GEMINI_API_KEY` only if Gemini translation or speech features are enabled

Never put secrets in Git or in a `VITE_*` variable. The crop-health model and the crop-yield benchmark dataset are included because the running app needs them. Database migrations create the schema and enable pgvector.

## Project structure

- `frontend/` — React and Vite web app
- `backend/` — FastAPI API, database migrations, and application modules
- `models/checkpoints/mobilenetv2-10class-v1/` — released crop-health model
- `data/raw/crop-yield-benchmark/` — runtime yield benchmark and provenance

The API stores advisor and scan records in PostgreSQL. User-uploaded leaf images are analyzed in memory and are not stored.
