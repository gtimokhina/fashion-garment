# Fashion Garment — Inspiration Library & Vision Classifier

A small full-stack app for **fashion and retail teams** to collect inspiration images, run **GPT‑4o (vision)** classification into structured attributes, add **designer annotations**, and **search** with lexical filters, optional **semantic / hybrid** ranking, and **faceted** counts.

---

## Project overview

- **Problem:** Reference photos pile up in folders or chat threads; designers need quick recall by garment, palette, occasion, and their own tags—not only filenames.
- **Approach:** Upload images through a web UI or API; each image gets a model-written **description**, JSON **metadata** (garment type, style, colors, occasion, etc., each with a **confidence**), and separate **annotations** (tags, notes, optional designer string). The gallery exposes filters, search, and optional embedding-backed ranking.
- **Scope:** Single-user / small-team prototype: one SQLite database, local file storage, OpenAI for vision and embeddings. Not a multi-tenant production CDN.

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

**Prerequisites:** Node.js 20+, Python 3.9+ (3.11+ recommended), an [OpenAI](https://platform.openai.com/) API key.

### Backend

```bash
cd app/backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # set OPENAI_API_KEY, optional OPENAI_MODEL, DATABASE_URL, CORS_ORIGINS
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
| [`eval/`](eval/README.md) | Offline classifier evaluation, optional LLM judge, Pexels helpers. |
| [`eval/results/`](eval/results/README.md) | Pinned eval JSON + manifest for README baselines. |
| [`tests/`](tests/) | Pytest: unit (JSON parse), integration (filters), e2e (mocked classify + upload). |

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
