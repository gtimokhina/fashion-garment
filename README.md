# Fashion Garment Classification & Inspiration Web App

Lightweight AI-powered web app for fashion designers to organize, search, and reuse inspiration imagery from the field.

## Overview

Design teams collect large numbers of inspiration photos; this project explores turning that library into a searchable, annotated resource with AI-assisted garment classification and designer-added metadata.

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

**Images:** `GET /api/images` with optional filters (substring, case-insensitive): `garment_type`, `style`, `occasion`, `color_palette`, `color` (alias for palette text), `q` or `search` (matches **description**, annotation **notes**, and **tags**). **Facets:** `GET /api/images/facets`. **Upload:** `POST /api/images/upload` with multipart field **`files`** repeated (one or more images); response `{ "items": [...], "errors": [{ "filename", "detail" }] }` (per-file classification; partial success possible). **Annotations:** `PATCH /api/images/{id}/annotations` with JSON `{ "tags": ["a"], "notes": "..." }` (omit a field to leave it unchanged).

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

See `eval/` for scripts, labeled data, and instructions. A short summary of per-attribute accuracy and model strengths/limitations will be added here or linked from `eval/`.

**Bulk fashion images (Pexels):** use the official API (not the search webpage). Get a free key at [pexels.com/api](https://www.pexels.com/api/), then:

```bash
export PEXELS_API_KEY=your_key
python eval/scripts/download_pexels_fashion.py   # 50 × "fashion" → eval/data/pexels_fashion/
```

Options: `--count 50`, `--query fashion`, `--out path`.

## Testing

Commands will be added once pytest / frontend test runner are wired. Planned coverage:

- Unit: parsing multimodal model output into structured attributes.
- Integration: filter behavior (especially location and time).
- End-to-end: upload, classify, and filter.
