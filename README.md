# Fashion Garment Classification & Inspiration Web App

Lightweight AI-powered web app for fashion designers to organize, search, and reuse inspiration imagery from the field.

## Overview

Design teams collect large numbers of inspiration photos; this project explores turning that library into a searchable, annotated resource with AI-assisted garment classification and designer-added metadata.

**Designer annotations** (tags and free-text notes) are stored separately from **AI-generated** descriptions and structured metadata. Search matches both, but the gallery labels them distinctly (amber “Your annotations” vs blue “Description”) so you can tell what came from the model versus human input.

## Stack

| Layer | Technology |
|--------|------------|
| Frontend | Next.js (App Router, TypeScript, Tailwind) in [`app/frontend`](app/frontend) |
| Backend | FastAPI + SQLAlchemy + SQLite in [`app/backend`](app/backend) (`main.py`, `routes/`, `services/`, `models/`) |
| Database | SQLite file under `app/backend/data/` (created on first run) |

## Prerequisites

- **Node.js** 20+ (for Next.js)
- **Python** 3.11+ (for FastAPI)

## Local setup

### 1. Backend (FastAPI)

```bash
cd app/backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

**Images:** `GET /api/images` with optional filters (substring, case-insensitive): `garment_type`, `style`, `occasion`, `color_palette`, `color` (alias for palette text), `q` or `search` (matches **description**, annotation **notes**, and **tags**). **`semantic=true`** with non-empty `q`/`search` (default **`hybrid=true`**): **combined score** = `0.5 × keyword_score + 0.5 × embedding_similarity` (keyword = substring match in desc/notes/tags, 0 or 1; embedding = cosine on stored description vectors). Rows below **`HYBRID_MIN_COMBINED_SCORE`** are dropped; response includes **`keyword_score`**, **`semantic_score`**, **`combined_score`** per item. **`hybrid=false`**: legacy embedding-only ranking (`SEMANTIC_SEARCH_*` thresholds). **`keyword_fallback`**: substring-only SQL results if no rows pass. **Facets:** `GET /api/images/facets`. **Upload:** `POST /api/images/upload` with multipart field **`files`** repeated (one or more images); response `{ "items": [...], "errors": [{ "filename", "detail" }] }` (per-file classification; partial success possible). **Annotations:** `PATCH /api/images/{id}/annotations` with JSON `{ "tags": ["a"], "notes": "..." }` (omit a field to leave it unchanged). Existing rows without embeddings: `python3 scripts/backfill_description_embeddings.py` from `app/backend`.

Optional: copy [`app/backend/.env.example`](app/backend/.env.example) to `app/backend/.env` and set `DATABASE_URL` or comma-separated `CORS_ORIGINS`.

### 2. Frontend (Next.js)

In a **second** terminal:

```bash
cd app/frontend
npm install
cp .env.example .env.local   # optional; defaults to http://127.0.0.1:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use **Upload** and **Gallery** in the nav. The home page includes an **API status** panel that calls `/health` (start the backend first, or you will see “unreachable”).

Dependencies: install with **`pip install -r requirements.txt`** or, if you use Poetry, **`poetry install`** from `app/backend` (see [`pyproject.toml`](app/backend/pyproject.toml)).

### Environment

- **Frontend:** `NEXT_PUBLIC_API_URL` in `.env.local` (see [`app/frontend/.env.example`](app/frontend/.env.example)) points at the FastAPI server.
- **Backend:** CORS allows `localhost:3000` and `127.0.0.1:3000` by default.
- **OpenAI (classification):** set `OPENAI_API_KEY` (and optional `OPENAI_MODEL`) in the environment or in [`app/backend/.env`](app/backend/.env) — loaded automatically on startup via `python-dotenv`. See [`app/backend/.env.example`](app/backend/.env.example).

## Repository layout

| Path | Purpose |
|------|---------|
| `app/frontend/` | Next.js UI. |
| `app/backend/` | FastAPI (`main.py`, `routes/`, `services/`, `models/`), SQLite under `data/`, uploads under `uploads/`. |
| `eval/` | Model evaluation scripts and labeled test set (50–100 images, gold attributes). |
| `tests/` | Unit, integration, and end-to-end tests. |
| `tests/unit/` | Unit tests. |
| `tests/integration/` | Integration tests. |
| `tests/e2e/` | End-to-end tests. |

## Architecture

The browser talks only to **Next.js** for pages and static assets. Client-side `fetch` uses `NEXT_PUBLIC_API_URL` to reach **FastAPI** (JSON, uploads, and future search endpoints). **SQLite** is opened exclusively from the Python process via **SQLAlchemy** (`models/database.py`, `Image` ORM). Upload runs **GPT-4o** classification and persists `description`, `metadata` (structured attributes), and `annotations` (JSON, initially `{}`).

## Evaluation

See `eval/` for scripts and labeled data. **Classifier eval** (gold labels vs model output):

```bash
cd app/backend && source .venv/bin/activate   # optional
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset
```

Dataset format: [`eval/data/example_dataset/README.md`](eval/data/example_dataset/README.md) and [`labels.example.json`](eval/data/example_dataset/labels.example.json). **Export from DB** (images + labels from stored metadata): `python3 eval/scripts/export_dataset_from_db.py` from `app/backend`, or from repo root: `bash eval/run_example_eval.sh` (export + eval in one step).

Requires `OPENAI_*` in `app/backend/.env`. Use `--verbose` for per-image tables and `--output-json path` for machine-readable results.

**Bulk fashion images (Pexels):** use the official API (not the search webpage). Get a free key at [pexels.com/api](https://www.pexels.com/api/), add `PEXELS_API_KEY=...` to `app/backend/.env` (same file as the backend), then:

```bash
python3 eval/scripts/download_pexels_fashion.py   # 50 × "fashion" → eval/data/pexels_fashion/
```

On macOS, `python` is often missing — use `python3` (or activate a venv that provides `python`). You can also `export PEXELS_API_KEY=...` to override. Options: `--count 50`, `--query fashion`, `--out path`.

**Ingest downloads into the app** (same pipeline as the Upload page: save → classify → DB). In a separate terminal, start the backend (`uvicorn` with `OPENAI_*` set — see Backend above), then:

```bash
python3 eval/scripts/ingest_pexels_to_backend.py
python3 eval/scripts/ingest_pexels_to_backend.py --sync-annotations   # same, then tags/notes from description (OpenAI)
```

If you see “connection refused”, the API is not running on the default URL yet.

This POSTs each `pexels_*` file to `/api/images/upload` (AI classification only). **`--sync-annotations`** runs `app/backend/scripts/sync_annotations_from_description.py` afterward (use the same `python3`/venv as the backend so dependencies match). Add **`--tags "a,b"`** and/or **`--notes "..."`** only if you want designer metadata on those rows; omit both to avoid placeholder annotations. Use `--dry-run` to list files only. `BACKEND_URL` or `--base-url` if the API is not on `http://127.0.0.1:8000`.

**Clear all designer annotations in SQLite** (does not touch AI description/metadata):

```bash
cd app/backend && python3 scripts/clear_all_annotations.py
```

**Fill tags and notes from the stored AI description** (plus structured metadata): uses the same OpenAI model to suggest searchable tags—including synonyms grounded in the description—and a short notes line. Replaces existing annotations by default; add `--merge` to union tags and append notes.

```bash
cd app/backend && python3 scripts/sync_annotations_from_description.py --dry-run
python3 scripts/sync_annotations_from_description.py
```

## Testing

Commands will be added once pytest / frontend test runner are wired. Planned coverage:

- Unit: parsing multimodal model output into structured attributes.
- Integration: filter behavior (especially location and time).
- End-to-end: upload, classify, and filter.
