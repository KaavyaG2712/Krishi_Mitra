# KrishiMitra — Implementation Handoff

**Status:** Architecture and implementation plan approved; code implementation has not yet started.  
**Immediate milestone:** Review 3 on **16 September 2026**.  
**Current delivery target:** a reproducible **local** demonstration on a development laptop. Cloud hosting is explicitly deferred.

---

## 1. Project Goal and Scope

KrishiMitra is an AI-powered agricultural decision-support web application. The full final project will contain four modules:

1. **Crop Health Intelligence** — classify a crop leaf image and present a confidence-aware disease result.
2. **Crop Recommendation** — later recommend crops using district soil/climate inputs.
3. **AI Agronomy Advisor** — answer crop-related questions using only retrieved, authoritative agricultural sources.
4. **Market Intelligence** — later display cached official Mandi prices.

### Review 3 scope: implement only Modules 1 and 3 properly

The review rubric expects working evidence for roughly 50% of the approved scope. Do **not** implement four shallow modules. Review 3 must demonstrate two complete, end-to-end AI modules:

- Module 1: **Crop Health Intelligence**
- Module 3: **AI Agronomy Advisor**

Module 2 and Module 4 must be described in the report/architecture but are scheduled for Phase 3. A basic static dashboard shell is allowed, but not required to count them as implemented.

### Current project decisions

| Decision | Locked value |
| --- | --- |
| UI language | English |
| Team size | 3 members |
| Collaboration | Lead + peer review; every member understands every module |
| Future regions | Karnataka and Maharashtra — **not required for Review 3** |
| Initial crops | Tomato, Maize, Potato, Grape |
| Hosting | No cloud hosting currently; local Docker Compose only in final phase |
| LLM provider | Gemini API Free Tier only; no billing account |

---

## 2. Review 3 MVP Requirements

### Module 1 supported labels

Use this focused 10-class model for the review. Do not train all PlantVillage classes yet.

- Tomato: Healthy, Early Blight, Late Blight
- Potato: Healthy, Early Blight, Late Blight
- Maize: Healthy, Common Rust
- Grape: Healthy, Black Rot

### Module 1 must demonstrate

1. User uploads a leaf image through a minimal React page.
2. FastAPI validates and preprocesses the image.
3. A fine-tuned MobileNetV2 model predicts one of the 10 labels.
4. API stores the scan result in PostgreSQL.
5. UI shows prediction, confidence, model version, and a treatment/advisory reference.
6. Low-confidence predictions return a safe message such as: *“Result uncertain. Please consult a local agricultural officer/KVK.”*

### Module 3 must demonstrate

1. User asks a farming question through a minimal React chat page.
2. FastAPI embeds the query and retrieves relevant chunks from PostgreSQL + pgvector.
3. Gemini generates an answer using only retrieved official material.
4. UI shows answer plus document/page citations.
5. API stores the question, answer, retrieved citations, scores, model versions, and latency.
6. If no adequate evidence is retrieved, the system abstains and gives a safe referral.

### Do not claim

- Do not claim that PlantVillage benchmark accuracy proves accuracy on real farm photos.
- Do not claim “zero hallucination.” Use the phrase **citation-grounded / evidence-grounded advisory**.
- Do not prescribe unsupported pesticide dosages or present the product as a replacement for an agricultural officer.

---

## 3. Locked Architecture and Technology Stack

```text
React + TypeScript + Vite (minimal review UI)
                 |
             HTTP / JSON
                 |
FastAPI + Pydantic + SQLAlchemy + Alembic
      |                              |
Module 1: PyTorch/MobileNetV2   Module 3: pgvector retrieval + Gemini
      |                              |
      +------------ PostgreSQL + pgvector ------------+
```

### Required stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, TanStack Query.
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2, Alembic.
- **Database:** PostgreSQL 16 with the `pgvector` extension.
- **Module 1 ML:** PyTorch, Torchvision, Pillow/OpenCV, scikit-learn metrics.
- **Module 3 RAG:** `google-genai` SDK, `gemini-2.5-flash`, `gemini-embedding-2` with 768 output dimensions, pgvector cosine search.
- **Testing:** pytest for API/model tests; optionally Playwright for browser flow tests.
- **Local operations:** Docker Compose, `.env` configuration, Git/GitHub.

### Deliberate exclusions for Review 3

- No Flutter/mobile application.
- No custom model training from scratch.
- No standalone vector database such as Qdrant/Pinecone.
- No price forecasting, IoT devices, voice assistant, multilingual support, authentication, cloud deployment, or full dashboard polish.
- Do not add LangChain unless it demonstrably speeds implementation. Direct FastAPI + Google Gen AI SDK + pgvector is preferred because it is simpler to explain and debug.

---

## 4. Second-Device Setup

The partner should develop on their own laptop and use GitHub for synchronisation. This is development setup, not cloud deployment.

### Install locally

- Git
- Python 3.12
- Node.js LTS
- Docker Desktop with WSL2 enabled
- VS Code/Cursor/Codex desktop

### Clone repository

```powershell
git clone https://github.com/KaavyaG2712/Krishi_Mitra.git
cd Krishi_Mitra
```

If the repository is private, authenticate with GitHub when prompted.

### Never commit these files

- `.env` or API keys
- `node_modules/`
- Python virtual environments
- raw datasets
- trained model weights/checkpoints unless a deliberately versioned release strategy is chosen
- local PostgreSQL volumes/data
- generated logs containing farmer/private information

Use `.gitignore` to exclude them. Commit source code, schemas/migrations, notebooks without raw data, documentation, data dictionaries, model metadata, and configuration examples only.

---

## 5. Data Collection

### Module 1: PlantVillage training data

Source: [PlantVillage Dataset repository](https://github.com/spMohanty/PlantVillage-Dataset)

Download only folders/classes required by the 10 labels above. Record the exact source URL/commit/date in a `data_sources.md` or CSV register.

PlantVillage is controlled-condition data. Collect 30–50 consented local/field leaf photos if practical. These photos are for **external testing only** and must not be mixed into model training.

For every field photo, record:

- anonymous image ID
- crop
- visible disease/healthy label only if verified
- district/state if voluntarily provided
- capture date
- consent/permission status

### Module 3: document corpus

Collect **10–12 authoritative documents** total:

- Tomato disease/advisory guides: 2–3
- Potato disease/advisory guides: 2
- Maize disease/advisory guides: 2
- Grape disease/advisory guides: 2
- General integrated pest management and safety guidance: 2

Preferred source types:

- Indian Council of Agricultural Research (ICAR): <https://icar.gov.in>
- Krishi Vigyan Kendra network (KVK): <https://kvk.icar.gov.in>
- State Agricultural University extension bulletins
- State Agriculture Department advisories

For each document, store:

- title
- publisher/organisation
- URL
- publication or access date
- licence/terms if stated
- target crop/disease/tags
- local filename/checksum
- relevant PDF page number(s)

Create **30–50 held-out evaluation questions**. Each question needs an expected document and page reference. Do not use these same questions when iteratively adjusting prompts.

### Future data only — do not collect for Review 3 unless time remains

- District soil profile and climate-normal data for Module 2.
- Karnataka/Maharashtra district mappings.
- AGMARKNET Mandi-price data/API key for Module 4.

---

## 6. Module 1 Algorithm: Crop Health Intelligence

### Training workflow

1. Build a stable `class_to_index` label map for the 10 selected labels.
2. Deduplicate/corruption-check images.
3. Create a stratified train/validation/test split **before** any augmentation. Keep field photos in a separate external test folder.
4. Preprocess: RGB conversion, resize/crop to 224×224, ImageNet normalization.
5. Apply augmentation only to training images: horizontal flip, small rotation, brightness/contrast change, and small crop/translation. Do not augment validation/test data.
6. Load ImageNet-pretrained MobileNetV2; replace its final classifier with 10 output classes.
7. Train in two stages: classifier head first with backbone frozen, then selectively fine-tune upper backbone layers.
8. Use cross-entropy loss and AdamW optimisation.
9. Select the final checkpoint using **validation macro-F1**, not training accuracy.
10. Save model artefact, label map, preprocessing configuration, training dataset version, and metrics under a model version.

### Inference workflow

```text
Uploaded image
  → image validation (type/size)
  → RGB + 224×224 preprocessing
  → MobileNetV2 logits
  → softmax probabilities
  → highest-confidence class
  → confidence threshold check
  → persisted result + UI response
```

### Required metrics

- class distribution
- accuracy
- macro precision, recall, and F1
- confusion matrix
- per-class F1
- p50/p95 inference latency on CPU
- separate external field-image result if field images exist

---

## 7. Module 3 Algorithm: Citation-Grounded Agronomy Advisor

### Offline ingestion workflow

1. Catalogue each approved source document in `knowledge_documents`.
2. Extract text page-by-page and preserve page metadata.
3. Remove duplicate headers, footers, navigation text, blank pages, and extraction errors.
4. Split text by headings into chunks of about 350–500 tokens with about 50-token overlap.
5. Attach metadata to every chunk: document ID, title, publisher, page, crop, topic, source URL.
6. Generate embeddings using `gemini-embedding-2` with 768 dimensions.
7. Store chunk text, vector, metadata, and embedding model/version in PostgreSQL + pgvector.
8. Build a pgvector HNSW cosine-similarity index.
9. Run retrieval evaluation using the held-out question set; fix bad chunking/metadata before changing prompts.

### Online question workflow

```text
Farmer question + optional disease scan context
  → in-domain validation
  → query embedding
  → top-k pgvector cosine retrieval
  → metadata filter by crop/disease where available
  → score threshold / evidence sufficiency check
  → Gemini 2.5 Flash with retrieved excerpts only
  → answer + citations or abstention
  → persist message, citations, scores, versions and latency
```

### Generation guardrails

The system prompt must instruct the model to:

- answer only from supplied excerpts;
- cite source title and page(s);
- state uncertainty when the excerpts do not answer the question;
- refuse unrelated questions politely;
- avoid inventing pesticide names/dosages;
- refer farmers to a KVK/agricultural officer for uncertainty, emergency crop loss, or safety-critical advice.

### Required metrics

- number of documents and chunks
- retrieval Precision@3 and/or Recall@5 against held-out questions
- citation correctness/coverage
- abstention correctness for no-evidence questions
- response latency
- unsafe/off-topic test results

---

## 8. Minimum Database Schema

Use UUID primary keys and UTC timestamps. Keep model/data provenance on every derived output.

### Required Review 3 tables

- `model_registry`
  - `id`, `module`, `version`, `dataset_version`, `metrics_json`, `artifact_location`, `created_at`
- `disease_scans`
  - `id`, `image_reference`, `predicted_label`, `confidence`, `model_version`, `created_at`
- `knowledge_documents`
  - `id`, `title`, `publisher`, `source_url`, `licence`, `checksum`, `ingested_at`
- `knowledge_chunks`
  - `id`, `document_id`, `page_number`, `chunk_text`, `embedding vector(768)`, `embedding_model`, `metadata_json`
- `advisor_conversations`
  - `id`, `created_at`
- `advisor_messages`
  - `id`, `conversation_id`, `question`, `answer`, `abstained`, `latency_ms`, `generation_model`, `created_at`
- `advisor_citations`
  - `id`, `message_id`, `chunk_id`, `rank`, `similarity_score`

### Future tables

- `soil_profiles`, `climate_normals`, `crop_recommendation_runs` for Module 2.
- `mandi_prices`, `sync_runs` for Module 4.
- `users`, `farms` only when authentication/farmer profiles become necessary.

---

## 9. API Contracts

All APIs are versioned under `/api/v1`. Validate requests using Pydantic and return a correlation/request ID for debugging.

### Module 1

`POST /api/v1/health/predict`

- Input: multipart leaf image and optional crop hint.
- Output: prediction label, confidence, is-uncertain flag, model version, treatment/advisory reference, scan ID.
- Errors: invalid file type, oversized/corrupt image, unsupported crop hint, unavailable model.

### Module 3

`POST /api/v1/advisor/chat`

- Input: `conversation_id` (optional for new conversation), `question`, `crop` (optional), `disease_scan_id` (optional).
- Output: answer, `abstained`, citations containing title/page/URL, retrieved scores, generation model, latency, message ID.
- Errors: blank/off-topic question, unavailable API key, Gemini quota exhaustion, insufficient evidence, database failure.

### Future APIs

- `POST /api/v1/crop/recommend`
- `GET /api/v1/mandi-prices`

---

## 10. Gemini Free Tier Setup and Security

### Create key

1. Sign into <https://aistudio.google.com/> using a team-owned Google account.
2. Open **Dashboard → API Keys**.
3. Create/import a project named `KrishiMitra-Capstone`.
4. Select **Create API key** and use the new Auth key.
5. Do **not** set up billing, link a payment method, or upgrade tiers.
6. Verify current model quota in **Dashboard → Usage** before demonstrations.

### Local environment values

Create a local backend `.env` file, never committed to Git:

```text
GEMINI_API_KEY=replace-with-local-secret
GEMINI_GENERATION_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
```

The browser/frontend must never receive the key. React calls FastAPI; FastAPI alone calls Gemini.

### Free-tier usage controls

- Embed documents once and persist embeddings; never re-embed at application startup.
- Retrieve no more than 3 relevant chunks in the initial implementation.
- Cap answers around 200–300 words.
- Add a basic request limit during testing.
- Never use Google Search/Maps grounding, image/video generation, Pro models, previews, or paid tiers.
- On HTTP `429 RESOURCE_EXHAUSTED`, show a retry-later message. Do not create extra accounts to evade quota.
- Do not send personal information, phone numbers, precise farmer locations, or unconsented images to Gemini. Free-tier data-use terms may differ from paid-tier terms.

Official references:

- Gemini API key guide: <https://ai.google.dev/gemini-api/docs/api-key>
- Gemini pricing: <https://ai.google.dev/gemini-api/docs/pricing>
- Gemini rate limits: <https://ai.google.dev/gemini-api/docs/rate-limits>
- Gemini embeddings: <https://ai.google.dev/gemini-api/docs/embeddings>

---

## 11. Phase-Wise Plan

### Phase 1 — Foundation and Data Readiness (11–12 September)

- Lock the 10 Module 1 classes.
- Download/version required PlantVillage folders.
- Collect/catalogue 10–12 authoritative RAG documents.
- Create 30–50 held-out RAG evaluation questions.
- Set up repository conventions, `.gitignore`, source register, API key, and local environment.

### Phase 2 — Review 3 Core Implementation (12–16 September)

- Train/evaluate Module 1 baseline and save versioned artefacts.
- Implement Module 3 ingestion, retrieval, grounded generation, and evaluation.
- Set up FastAPI, PostgreSQL + pgvector, migrations, and audit tables.
- Build minimal React image-upload and cited-chat pages.
- Run tests; prepare metrics, screenshots, demo video, report sections, issue/fix log, and viva answers.

### Phase 3 — Remaining Modules and Integration (17 September–12 October)

- Implement Module 2 using Karnataka/Maharashtra district profiles and climate normals.
- Implement Module 4 using a local cached data.gov.in/AGMARKNET sync.
- Build the unified English dashboard and Module 1 → Module 3 disease-context handoff.
- Add end-to-end, stale-data, unsupported-input, and failure-mode tests.

### Phase 4 — Local Final Delivery (13–21 October)

- Finalise Docker Compose for React, FastAPI, PostgreSQL + pgvector, model artefacts, and seed data.
- Verify a clean-laptop local setup from documentation.
- Perform final tests; complete report, viva deck, demo script, and contribution evidence.
- Do not deploy to cloud unless the team explicitly chooses to do so later.

---

## 12. Suggested Responsibility Model

Equal contribution does not require everyone to edit the same files. Use a lead + peer-review model so the panel can see individual contribution.

- **Member A:** leads Module 1 training, evaluation, model artefacts, and inference tests.
- **Member B:** leads Module 3 document corpus, ingestion, retrieval evaluation, and guardrails.
- **Member C:** leads FastAPI integration, database/migrations, React review pages, Docker/local setup.
- **All members:** review code, run integration tests, collect evidence, update report, rehearse demo, and understand all modules.

Record Git commits, issue/task ownership, test reports, and presentation responsibilities.

---

## 13. Review 3 Demonstration Script

1. Start local database/backend/frontend.
2. Show API documentation and database tables.
3. Upload a held-out tomato/potato/maize/grape image.
4. Show disease result, confidence, persisted scan, model version, and low-confidence behaviour.
5. Ask a question tied to one official document.
6. Show retrieved citations and answer; open/identify the relevant source page.
7. Ask an unsupported/off-topic or no-evidence question; show safe abstention.
8. Show metric charts, test log, source register, Git history, and known limitations.

---

## 14. Definition of Done for Review 3

Review 3 is complete only when all statements below are true:

- Module 1 works through browser → FastAPI → model → PostgreSQL → browser.
- Module 3 works through browser → FastAPI → pgvector retrieval → Gemini → citations → PostgreSQL → browser.
- Both modules have saved, reproducible metrics and version metadata.
- The demo can run locally without cloud hosting.
- No secret/API key is committed to GitHub.
- The team can explain datasets, algorithms, validation splits, RAG retrieval, limitations, safety controls, and individual responsibilities.

