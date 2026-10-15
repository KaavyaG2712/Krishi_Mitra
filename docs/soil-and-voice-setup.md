# Soil health and multilingual voice: setup

This extends the existing KrishiMitra React/FastAPI application. It does not replace the leaf-image classifier or create a second app. Python 3.12 and Node.js 22 LTS are recommended for the verified setup.

## Install and run

From the repository root, in PowerShell:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
cd backend
.venv/Scripts/python.exe -m pip install -e ".[dev,soil-ml]"
if (!(Test-Path .env)) { Copy-Item .env.example .env }
cd ../frontend
npm.cmd ci
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Use `.[dev,ml]` instead to include Torch/torchvision for the existing leaf model. The smaller `soil-ml` extra installs scikit-learn for offline experiments without downloading Torch. Soil entry and the chatbot can start without ML packages; missing leaf-model dependencies return a controlled unavailable response.

The existing PostgreSQL + pgvector schema is unchanged. Start the database and apply the existing migrations before using stored chat or leaf scans:

```powershell
# From the repository root
docker compose up -d db
cd backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm.cmd run dev
```

Open http://localhost:5173. The existing Windows launcher still works. When upgrading an existing checkout, reinstall dependencies explicitly; the launcher intentionally does not update an already-present environment. Soil normalization itself does not need PostgreSQL. Chat—including soil explanation in the advisor—uses the existing database and requires configured Gemini access.

## Backend environment

Keep these values only in `backend/.env` or the deployment secret manager. The example files contain no real keys.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL/psycopg URL; use separate production credentials |
| `FRONTEND_ORIGINS` | Comma-separated exact frontend origins; wildcard origins are rejected |
| `GEMINI_API_KEY` | Existing Gemini backend secret; also used by translation |
| `GEMINI_GENERATION_MODEL` | Existing configurable generation model; confirm availability in your project |
| `GEMINI_SPEECH_MODEL` | Optional audio-capable model override; blank reuses the generation model |
| `SIGNING_SECRET` | Random secret of at least 32 characters, mandatory outside development |
| `ENVIRONMENT` | `development` locally; `production` for deployment |
| `SOIL_HEALTH_API_URL` | `https://soilhealth4.dac.gov.in/` from official v1.35 documentation |
| `SOIL_HEALTH_API_TOKEN` | Issued SHC access token |
| `SOIL_HEALTH_REFRESH_TOKEN` | Issued refresh token; optional if access-token rotation is managed externally |
| `SOIL_HEALTH_TIMEOUT_SECONDS` | Per-upstream-request timeout; default 12, allowed 1–30 seconds |
| `SOIL_HEALTH_CACHE_SECONDS` | In-process cache lifetime; default 900, maximum 86400 seconds |
| `SOIL_HEALTH_AREA_ACCESS` | Default false. Enable only when authorized to disclose non-personal area samples |
| `SOIL_HEALTH_UNITS_JSON` | Official result-key → issuer-confirmed unit mapping; default `{}` |
| `SOIL_HEALTH_DEMO` | Default false; enables a separate synthetic fixture endpoint in development only |

Generate a signing secret locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it stable across workers and restarts. Development without a secret uses a random process key; restarting invalidates existing conversation/profile tokens. Capabilities expire after 24 hours. They are signed, not encrypted: treat them as private session data. Never put them in URLs or logs.

## Government API access and contract

The implementation follows the [official SHC API Integration Guidelines v1.35, revised 20 March 2024](https://soilhealth.dac.gov.in/files/SHC_API_Integration_Guidelines.pdf), inspected on 26 September 2026. Register the application through the authority’s process before using issued tokens. Documentation lists `soilhealthcard.support@krishitantra.com` for consumer registration; verify current contact instructions through the [official portal](https://soilhealth.dac.gov.in/). No registration request was sent during this implementation.

Implemented read-only operations:

| Operation | Use |
| --- | --- |
| `generateAccessToken(refreshToken: ...)` | Renew access once after authentication failure; retain rotated token in process memory |
| `getState` | State directory |
| `getdistrictAndSubdistrictBystate` | Districts or subdistricts for a state |
| `getVillageBydistrict` | Villages constrained by district and subdistrict |
| `getTestForAuthUser(state: ..., district: ...)` | Retrieve authorized records, then filter by exact village ID |

The adapter sends documented token/bearer headers over HTTPS and will not follow redirects or accept an arbitrary upstream host. It requests only `village`, `sampleDate`, and `results` from card records. No farmer names, phone numbers, addresses, land survey numbers, HTML reports, or exact sample coordinates are requested or exposed. Selecting a village returns the latest available dated matching sample, **not** a village average, field-specific test, or assertion that the sample is recent.

Before enabling real access, validate the issued schema against the adapter:

1. Directory JSON must be lists with `id` (or `_id`) and `name`. Subdistrict entries need a `district` (or `district_id`) relationship. The guideline does not fully specify these JSON structures. Unknown shapes fail closed; adapt only this service if the approved payload differs.
2. `getTestForAuthUser` must return a list. `village` must identify the selected village; `results` must be an object. No unbounded farmer-directory queries are performed.
3. The documentation shows bare numeric soil results but does not define their units. Obtain written unit/test-method definitions. For bare values, populate `SOIL_HEALTH_UNITS_JSON` using those definitions. **Do not copy guessed kg/ha or ppm mappings.** Explicit `{value, unit, method?}` measurements are also accepted. Source-supplied units are retained without conversion.
4. Unknown/missing units, invalid values, malformed JSON/GraphQL errors and oversized responses return an actionable error. They never produce synthetic “government” data.
5. Confirm the terms allow non-personal area-level display before enabling `SOIL_HEALTH_AREA_ACCESS=true`. A credential alone is not proof that redistribution is authorized.

No live credentialed SHC call was possible in this checkout. The authentication, directory and result contracts were exercised with HTTP mocks; integration acceptance with an issued account remains required.

### GPS limitation

The guideline does not document coordinate-based card lookup or reverse geocoding. The UI requests location once only after a click; the API explicitly returns `gps_lookup_unavailable` and offers the manual path. It does not call an invented endpoint, send GPS to a third-party geocoder, log it, or persist it. A separately authorized geographic service/data source is needed to enable actual GPS lookup later. Manual state → district → block → village selection uses the official directory when access is available.

### Normalization

| SHC result key | Internal parameter |
| --- | --- |
| `n`, `p`, `k` | `nitrogen`, `phosphorus`, `potassium` |
| `S`, `Zn`, `Fe`, `Cu`, `Mn`, `B` | `sulphur`, `zinc`, `iron`, `copper`, `manganese`, `boron` |
| `pH`, `EC`, `OC` | `ph`, `electricalConductivity`, `organicCarbon` |

Each measurement carries its value and unit, with an optional method. The profile also carries location labels/IDs, source, source classification, sample date, UTC retrieval time, coverage, nullable confidence and an explicit demo flag. Coordinates are deliberately omitted. Only the backend assigns source classification. Profiles sent to the advisor require an untampered signature.

Manual units are selected explicitly. Zero is kept as zero; omitted values stay absent. Validation rejects negative/non-finite values, booleans, numeric strings, unsupported manual units, future dates, pH outside 0–14 and concentration values exceeding their physical mass-fraction maximum. These are validation limits, not fertility thresholds. No nutrient Low/Medium/High bands, pH fertility category or automatic unit conversions are applied. Values in kg/ha depend on sample depth/density and cannot be assigned a universal upper agronomic limit here.

### Cache and mock data

The service caches successful lookups, including empty results, for 15 minutes by default. It also caches directories, bounds entries to 256, and serializes concurrent upstream calls to avoid duplicate requests. Cached results retain their original retrieval time and a UI cache marker. Failures are not cached. This is one-worker memory caching; use a shared cache and distributed quotas when scaling.

`GET /api/v1/soil/demo` is a separate opt-in development fixture. It returns `is_demo=true`, a synthetic source label and `USER_ENTERED`, never `GOVERNMENT_VERIFIED`. No real lookup can fall back to it. Provider tests use synthetic fixtures independently of that endpoint.

## Voice and translation

| Layer | Implementation |
| --- | --- |
| STT | Microphone recording → bounded WAV → `/speech/transcribe` → Gemini; browser SpeechRecognition is an explicit fallback |
| Translation | Backend `TranslationProvider` with existing Gemini SDK |
| Canonical answer | Existing Gemini advisor for general questions; deterministic structured soil explanation for a signed soil profile |
| TTS | Browser speech synthesis with a matching installed voice |
| Locales | English `en-IN`, Hindi `hi-IN`, Tamil `ta-IN`, Telugu `te-IN` |

The user controls recording, editing and submission. STT displays the original script; successful chat responses retain both original and English transcripts. Input translation failure stops generation and keeps the draft. Output translation failure keeps the English answer, marks its language correctly for playback, and allows translation-only retry. Numbers with units and recognized crop/technical terms are protected with placeholders; missing/changed placeholders or newly introduced digits cause translation rejection. This verifies preservation, **not** linguistic correctness. Native-speaker assessment is still needed.

There is no autoplay. Listen, Pause, Resume and Stop are exposed; actual pause/resume behavior depends on the device. Missing voices, unsupported recognition, denied permission, no speech, network failure, recognition timeout and playback failure retain the text interface. A recording watchdog stops the listening state. Switching language or leaving the advisor cancels recognition/playback.

The default recording route sends up to 30 seconds of audio to this backend and Google Gemini, reusing `GEMINI_API_KEY`. Audio is processed in memory, not retained by this app. The selected model must support audio; configure `GEMINI_SPEECH_MODEL` if needed. `/speech/status` reports whether a key is configured, not whether an upstream request has succeeded. Farmers do not supply their own key. Microphone capture needs localhost or HTTPS and browser permission. Browser recognition remains an explicit fallback; it can fail with `network` even when ordinary web browsing works, because it uses a separate browser-provider service. See [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition) and [Gemini audio documentation](https://ai.google.dev/gemini-api/docs/audio). This is not offline STT. TTS still uses installed device voices; see [MDN getVoices](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices).

## Import a soil report without government access

The primary route is now **Scan or import your soil report**: choose a photo/PDF or paste results text, review detected values and units, and optionally save a named report on the device. No government or Gemini key is needed for this route. `npm ci` prepares same-origin Tesseract workers, WASM and English OCR data; `npm run dev` and `npm run build` also prepare them. Deploy the full `dist` directory, including `ocr/`. PDF.js reads text PDFs and renders scans for local OCR. See the [follow-up guide](speech-and-report-import.md) for formats, bounds, privacy and accuracy limitations.

Core soil actions, parameter labels, form guidance, language navigation and voice controls are localized. Some secondary copy, backend error text and the existing crop-health screen remain English. A full native-language editorial pass is required before claiming complete UI localization.

## Offline soil-model experiment

No tabular soil/crop-suitability dataset or deployed soil model exists in this repository. `scripts/train_soil.py` provides an offline **classification** comparison of Random Forest and scikit-learn Histogram Gradient Boosting. It does not estimate nutrients or predict fertilizer quantities, and no inference route is exposed.

After obtaining licensed, agronomist-reviewed data with documented units and labels:

```powershell
cd backend
.venv/Scripts/python.exe -m pip install -e ".[soil-ml]"
.venv/Scripts/python.exe scripts/train_soil.py --dataset ../data/processed/reviewed.csv --source "Publisher, release, licence, URL" --features nitrogen,phosphorus,potassium,ph --target suitable_crop --group geographic_region --version soil-crop-v1 --output ../models/checkpoints/soil-crop-v1
```

Those feature/target names are examples of your **own reviewed CSV schema**, not a bundled dataset. Include units in a data dictionary; do not mix units or methods in one column. The script rejects target/group leakage, duplicate feature rows, missing targets/groups, non-finite values and rows above 25% missingness. It requires at least six geographic groups and class coverage in folds/holdout. Group creation must keep repeated/nearby sites together; coarse district labels alone do not prove geographic independence.

A seeded group holdout is reserved for the final test. GroupKFold on development groups compares accuracy, macro precision/recall/F1; model selection uses mean validation macro-F1. Median imputation is fitted within each fold. Only the selected pipeline sees the final test. Saved files include the fitted preprocessing/model pipeline, ordered feature list, dataset checksum/source, split counts, seed, model/runtime versions, candidate validation metrics, final classification report/confusion matrix and limitations. Existing output directories are not overwritten.

Only a synthetic software smoke test was run. There are no agricultural evaluation metrics or winner claims. Before serving an artifact, add a reviewed model registry entry, calibrated validity domain, feature/unit/missingness validation, geographic/temporal external validation and an inference adapter. Never load untrusted joblib files. XGBoost/LightGBM/CatBoost were not added: the two baseline candidates use the existing scikit-learn dependency and there is no dataset justifying extra libraries.

## Verification and production build

```powershell
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q app scripts
cd ../frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
npm.cmd audit
```

Optional audit tool (not required at runtime): `python -m pip install pip-audit`, then `python -m pip_audit`. Update pip before auditing a newly created environment. No standalone linter was configured in the existing repository; type checking, Python compilation, regression/component tests and build are used here.

Serve `frontend/dist` from an HTTPS static host and run FastAPI behind an HTTPS reverse proxy. `VITE_API_BASE_URL` is a public build-time URL; on an Android phone, `127.0.0.1` refers to the phone, so use the actual HTTPS API origin. Vite preview/dev servers are not production hosting. Exact CORS origins, a stable signing secret, private database networking, global request/body limits, a data retention policy and validated SHC access are deployment requirements. The included 30-request/minute IP limit is process-local and must be paired with trusted-proxy/global quota configuration in a multi-worker deployment.

There is no service worker/PWA offline cache in this change. The existing app has no offline shell; local manual drafts are opt-in and survive reload, but submission, chat, translation and government lookup need a connection. Clear saved drafts on shared phones. Soil profiles are kept in page memory, not added to a persistent farm-history database. Existing chat storage retains canonical questions/answers; original/English transcripts are held in the browser response state rather than a new database schema.
