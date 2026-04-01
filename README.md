# Fashion Garment Classification & Inspiration Web App

Lightweight AI-powered web app for fashion designers to organize, search, and reuse inspiration imagery from the field.

## Overview

Design teams collect large numbers of inspiration photos; this project explores turning that library into a searchable, annotated resource with AI-assisted garment classification and designer-added metadata.

## Stack

| Layer | Technology |
|--------|------------|
| Frontend | Next.js (App Router, TypeScript, Tailwind) in [`app/frontend`](app/frontend) |
| Backend | FastAPI + SQLModel + SQLite in [`app/backend`](app/backend) (`main.py`, `routes/`, `services/`, `models/`) |
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

The browser talks only to **Next.js** for pages and static assets. Client-side `fetch` uses `NEXT_PUBLIC_API_URL` to reach **FastAPI** (JSON, uploads, and future search endpoints). **SQLite** is opened exclusively from the Python process; the database file is not shared with Node.

## Evaluation

See `eval/` for scripts, labeled data, and instructions. A short summary of per-attribute accuracy and model strengths/limitations will be added here or linked from `eval/`.

## Testing

Commands will be added once pytest / frontend test runner are wired. Planned coverage:

- Unit: parsing multimodal model output into structured attributes.
- Integration: filter behavior (especially location and time).
- End-to-end: upload, classify, and filter.
