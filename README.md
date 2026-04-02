# Fashion Garment — Inspiration Library & Vision Classifier

A small full-stack app for **fashion and retail teams** to collect inspiration images, run **GPT‑4o (vision)** classification into structured attributes, add **designer annotations**, and **search** with lexical filters, optional **semantic / hybrid** ranking, and **faceted** counts.

---

## Project overview

- **Problem:** Reference photos pile up in folders or chat threads; designers need quick recall by garment, palette, occasion, and their own tags—not only filenames.
- **Approach:** Upload images through a web UI or API; each image gets a model-written **description**, JSON **metadata** (garment type, style, colors, occasion, etc., each with a **confidence**), and separate **annotations** (tags, notes, optional designer string). The gallery exposes filters, search, and optional embedding-backed ranking.
- **Scope:** Single-user / small-team prototype: one SQLite database, local file storage, OpenAI for vision and embeddings. Not a multi-tenant production CDN.
- **First-run gallery:** If the image table is **empty** when the API starts, it inserts **one bundled demo photo** and metadata so a fresh clone is not blank. Disable with **`FASHION_GARMENT_SKIP_SEED=1`** (tests set this automatically). If you wipe the DB/uploads and restart with an empty table, the seed runs again.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser                                                                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP (pages, JS)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Next.js (App Router) — app/frontend                                     │
│  · Gallery, upload UI · NEXT_PUBLIC_API_URL → FastAPI                    │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ JSON, multipart upload
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI — app/backend                                                   │
│  · /api/images*, /health  · StaticFiles: /uploads/                       │
│  · Routes → services (classifier, filters, embeddings, CRUD)             │
└───────┬─────────────────────┬─────────────────────┬─────────────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌────────────────┐    ┌──────────────────┐
│ SQLite        │    │ Local disk      │    │ OpenAI API        │
│ (metadata +   │    │ uploads/        │    │ vision classify + │
│  embeddings)  │    │                 │    │ text embeddings   │
└───────────────┘    └────────────────┘    └──────────────────┘
```

**Data flow (upload):** multipart file → save under `uploads/` → `classify_image` (vision JSON) → normalize → optional description embedding → persist `Image` row.

**Data flow (search):** query params → SQL JSON substring filters and/or hybrid `0.5×keyword + 0.5×cosine(description_embedding)` when `semantic=true` with text query.

---

## Setup

**Prerequisites:** an [OpenAI](https://platform.openai.com/) API key for classification. For **local dev without Docker:** Node.js 20+ and Python 3.9+ (3.11+ recommended). To run everything in containers, you only need [Docker](#docker).

### Environment (one file)

Copy the repo root template and fill in secrets once:

```bash
cp .env.example .env   # at project root; OPENAI_API_KEY, optional OPENAI_MODEL, etc.
```

The backend reads **`.env` at the project root**. [Docker Compose](#docker) uses the same root `.env`.

### Backend

```bash
cd app/backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Frontend

```bash
cd app/frontend
npm install
cp .env.example .env.local   # optional; defaults to http://127.0.0.1:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Tests

```bash
pip install -r app/backend/requirements.txt -r app/backend/requirements-dev.txt
pytest
```

### Docker

Use this path if you want to run the full stack **without installing Node or Python** on your machine. You only need [Docker](https://docs.docker.com/get-docker/) (Docker Desktop on macOS/Windows, or Docker Engine + Compose on Linux) with **Compose v2** (`docker compose`, not the legacy `docker-compose` binary).

#### Quick start

1. Clone the repo and open the project root:

   ```bash
   git clone <repository-url> fashion-garment
   cd fashion-garment
   ```

2. Create your environment file from the template (see [Environment (one file)](#environment-one-file)):

   ```bash
   cp .env.example .env
   ```

3. Edit **`.env`** in the repo root and set at least **`OPENAI_API_KEY`**. Uploads and classification will fail without it.

4. Build images and start containers:

   ```bash
   docker compose up --build
   ```

   Add **`-d`** to run in the background (`docker compose up --build -d`).

5. Open the app:

   - **Web UI:** [http://localhost:3000](http://localhost:3000) (gallery on `/`, upload on `/upload`)
   - **API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health:** [http://localhost:8000/health](http://localhost:8000/health)

On first API start, **one example image** is seeded when the library is empty (see overview). Add your own via **Upload**. New Docker volumes contain no data until containers run; the seed runs on the backend’s first startup after that.

#### Environment variables (Docker)

Compose reads **`.env`** from the **repo root** for variable substitution and passes the relevant values into containers. Common entries:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes (for real uploads) | Vision classification and embeddings. |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o` in Compose. |
| `NEXT_PUBLIC_API_URL` | No | **URL the browser uses** to call the API. Use `http://localhost:8000` when you open the UI at `http://localhost:3000` on the same machine. If you publish the API on another host or port, set this to match **before** building the frontend image. |
| `BACKEND_PORT` | No | Host port for the API (default `8000`). |
| `FRONTEND_PORT` | No | Host port for Next.js (default `3000`). |
| `CORS_ORIGINS` | No | Comma-separated origins allowed by the API; include the exact UI origin (e.g. `http://localhost:3000`). |

**Important:** `NEXT_PUBLIC_*` is **baked in at image build time** for the frontend. After changing `NEXT_PUBLIC_API_URL` (or switching host/port), rebuild the frontend:

```bash
docker compose build frontend --no-cache
docker compose up
```

Backend-only env changes (e.g. `OPENAI_API_KEY`) take effect on **container restart**; `docker compose up --build` is enough if you did not change build args.

#### Images and compose file

- **`app/backend/Dockerfile`** — Python 3.11, FastAPI, dependencies from `requirements.txt`; SQLite at `/data/app.db`, uploads under `/app/uploads`.
- **`app/frontend/Dockerfile`** — multi-stage Node 20 build, Next.js **`output: "standalone"`**, production server on port 3000.
- **`docker-compose.yml`** — defines `backend` and `frontend`, plus named volumes **`backend_data`** (database) and **`backend_uploads`** (image files). Data survives `docker compose stop`; removing volumes deletes the library.

#### Useful commands

```bash
# Stop containers (keeps volumes)
docker compose down

# View logs (foreground run logs to the terminal; with -d use:)
docker compose logs -f backend
docker compose logs -f frontend

# Run the pytest suite in a one-off container
docker compose --profile test run --rm test
```

#### Resetting data

To wipe the SQLite DB and all uploaded files from Docker volumes:

```bash
docker compose down -v
```

The next `docker compose up --build` creates fresh volumes; the first API startup seeds the demo image when the table is empty.

#### Troubleshooting (Docker)

- **UI shows “API unreachable” or uploads fail:** Confirm `OPENAI_API_KEY` in root `.env`, restart with `docker compose up`, and check `docker compose logs backend`.
- **Gallery loads but images are broken:** Ensure `NEXT_PUBLIC_API_URL` points to where **your browser** can reach the API (usually `http://localhost:8000` if ports are mapped as defaults), then rebuild the frontend as above.
- **CORS errors in the browser:** Add your exact UI URL (including port) to `CORS_ORIGINS` in `.env` and restart the backend container.

---


## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness JSON `{"status":"ok"}`. |
| `GET` | `/api/images` | List images. **Metadata filters** (case-insensitive substring on structured fields): `garment_type`, `style`, `material`, `color` / `color_palette`, `pattern`, `season`, `occasion`, `consumer_profile`, `trend_notes`, `location_context`. **`q` / `search`:** description + annotation notes + tags. **`semantic=true`** + non-empty query: embedding ranking; default **`hybrid=true`** combines keyword (0/1) and embedding cosine; response may include `semantic_score`, `keyword_score`, `combined_score`, `keyword_fallback`. |
| `GET` | `/api/images/facets` | Facet value counts (same filter dimensions; standard faceted behavior). |
| `POST` | `/api/images/upload` | Multipart **`files`** (repeat field); per-file classify and persist; returns `items` + `errors`. |
| `GET` | `/api/images/{id}` | Single image payload. |
| `PATCH` | `/api/images/{id}` | Update `description`, `metadata`, and/or `annotations` (JSON body). |
| `PATCH` | `/api/images/{id}/annotations` | Merge **tags**, **notes**, **designer**; omitted keys unchanged. |
| `DELETE` | `/api/images/{id}` | Remove row and delete file under `uploads/`. |

Static assets: **`GET /uploads/...`** served from `app/backend/uploads/`.

---

## Design decisions

1. **Split AI output vs designer input:** `metadata` holds model attributes (+ confidences); `annotations` holds human tags/notes/designer so UX and search can distinguish “model vs you” without schema collisions.
2. **SQLite + JSON columns:** Fast to ship, easy backup, sufficient for a local library; metadata stored as JSON matching the vision schema (`value` + `confidence` per field).
3. **Substring filters first:** Predictable for small corpora; **semantic/hybrid** layered on for “vibe” queries without abandoning SQL filters.
4. **OpenAI JSON mode + Pydantic:** Typed parsing with a repair pass on failure reduces brittle regex on raw model text.
5. **Eval outside the request path:** `eval/run_eval.py` re-runs classification against labeled sets; optional **LLM judge** separates *string-match* accuracy from *semantic* agreement.

---

## Trade-offs

| Choice | Upside | Downside |
|--------|--------|----------|
| SQLite | Zero ops, portable | Concurrent writes weak; not ideal for high fan-out APIs |
| File-backed uploads | Simple, works with StaticFiles | No S3 lifecycle, CDN, or virus pipeline |
| Single multimodal call per upload | Low latency vs multi-step pipelines | One prompt carries all fields; harder field-level tuning |
| Hybrid search | Blends exact-ish keywords with semantic recall | Tuning thresholds (`HYBRID_*`, `SEMANTIC_*`) is environment-specific |
| Storing raw model JSON (`ai_raw_response`) | Debuggability | Larger rows; privacy/storage discipline needed |

---

## Limitations

- **No auth:** Anyone with network access to the API can read/write (add reverse proxy + auth for shared hosts).
- **English-centric prompts** and Western-biased training data in base models may skew labels for global street style.
- **Gold labels in eval** are only as good as export/annotation quality; DB-exported labels can match an *earlier* model run (consistency check), not absolute truth.
- **Embeddings** require OpenAI; offline/air-gapped use needs a different embedder and code path.
- **Classifier cost & rate limits** scale linearly with uploads; bulk ingest (e.g. Pexels scripts) should be run deliberately.

---

## Evaluation results summary

**Pinned snapshot (2026-03-31):** `gpt-4o` on **`eval/data/example_dataset`** (**N = 53** images, gold labels from stored metadata). Matching: `--color-mode token`, `--text-match exact`, no LLM judge. *Your* run may differ slightly if `OPENAI_MODEL` or prompts differ.

| Field | Accuracy |
|-------|----------|
| `garment_type` | 26.4% |
| `style` | 45.3% |
| `occasion` | 77.4% |
| `color` (vs `color_palette`) | 37.7% |
| **Micro** (all 212 field slots) | **46.7%** |
| **Macro** (mean of four fields) | **46.7%** |

**Takeaway:** strongest on **occasion**, weakest on **garment_type** under strict string rules—often partly **vocabulary** (e.g. gold “joggers” vs “streetwear ensemble”) rather than pure vision error; see optional `--llm-judge` in [`eval/README.md`](eval/README.md).

**Artifacts:** aggregates in [`eval/results/snapshot_manifest.json`](eval/results/snapshot_manifest.json); full per-image rows in [`eval/results/eval_snapshot_gpt4o.json`](eval/results/eval_snapshot_gpt4o.json); see [`eval/results/README.md`](eval/results/README.md).

**How to run / refresh:** [`eval/README.md`](eval/README.md), [`eval/data/example_dataset/README.md`](eval/data/example_dataset/README.md).

```bash
cd app/backend && source .venv/bin/activate
pip install -r requirements.txt
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset --output-json ../../eval/results/eval_snapshot_gpt4o.json
```

**Bulk imagery:** official Pexels API (`PEXELS_API_KEY`): `eval/scripts/download_pexels_fashion.py`, then `eval/scripts/ingest_pexels_to_backend.py` (optional `--sync-annotations`) — [`eval/README.md`](eval/README.md).

---

## Repository layout

| Path | Role |
|------|------|
| [`app/frontend/`](app/frontend/) | Next.js UI (gallery, upload). |
| [`app/backend/`](app/backend/) | FastAPI app, SQLAlchemy models, classifier, search, scripts. |
| [`app/backend/seed_assets/`](app/backend/seed_assets/) | Bundled demo image for first-run gallery seed. |
| [`eval/`](eval/README.md) | Offline classifier evaluation, optional LLM judge, Pexels helpers. |
| [`eval/results/`](eval/results/README.md) | Pinned eval JSON + manifest for README baselines. |
| [`tests/`](tests/) | Pytest: unit (JSON parse), integration (filters), e2e (mocked classify + upload). |
| [`docker-compose.yml`](docker-compose.yml) | Orchestrates `backend` + `frontend`; [`Dockerfile.test`](Dockerfile.test) for CI-style pytest. |

---

## Additional scripts (backend)

| Script | Use |
|--------|-----|
| `scripts/backfill_description_embeddings.py` | Fill missing vectors for semantic search. |
| `scripts/sync_annotations_from_description.py` | Suggest tags/notes from description + metadata (preserves **`designer`** unless `--merge` semantics apply). |
| `scripts/clear_all_annotations.py` | Clear designer annotations only. |

---

## License / contributing

Treat API keys and local SQLite/uploads as secrets and artifacts; do not commit `.env` or production databases. Extend eval and thresholds in code when you change prompts or models so regressions stay visible.
