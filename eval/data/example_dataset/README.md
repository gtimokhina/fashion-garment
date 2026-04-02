# Example evaluation dataset

Place **images** under `images/` and list them with gold labels in **`labels.json`**.

## Populate from the app database

To copy every library image from `app/backend/uploads/` and build `labels.json` from stored **metadata** (same fields the classifier saved: `garment_type`, `style`, `occasion`, `color_palette` → label `color`):

```bash
cd app/backend && source .venv/bin/activate
python3 ../../eval/scripts/export_dataset_from_db.py
```

Then run the evaluation pipeline (re-classifies each file and compares to the labels above):

```bash
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset --verbose
```

Gold labels come from the DB snapshot; `run_eval.py` runs **fresh** vision calls, so scores reflect agreement between a new classification and the stored metadata (useful for regression / consistency checks).

## `labels.json` schema

Top level:

| Field       | Type   | Description |
|------------|--------|-------------|
| `version`  | number | Format version (currently `1`). |
| `items`    | array  | One object per image. |

Each **item**:

| Field     | Type   | Description |
|----------|--------|-------------|
| `image`  | string | Path to the file **relative to this dataset directory** (e.g. `images/coat_01.jpg`). |
| `labels` | object | Ground-truth strings for evaluation (see below). |

Each **label** value is a string. Use empty string or omit a key if you do not want that field scored for that image.

### Label keys (compared to classifier output)

| Key in JSON    | Compared to model field | Notes |
|----------------|---------------------------|--------|
| `garment_type` | `garment_type`            | Normalized exact match. |
| `style`        | `style`                   | Normalized exact match. |
| `occasion`     | `occasion`                | Normalized exact match. |
| `color`        | `color_palette`           | See `--color-mode`: **strict** (normalized equality) or **token** (default): each comma-separated token in gold appears as a substring in the prediction. |

The classifier does not emit a field named `color`; gold `color` is compared to **`color_palette`**.

For **garment_type**, **style**, and **occasion**, `run_eval.py` supports **`--text-match exact`** (default: full normalized string match) or **`--text-match token`** (each comma-separated fragment in gold must appear in the prediction — helpful when gold lists multiple styles or occasions).

## Example

See [`labels.example.json`](labels.example.json). Copy it to `labels.json`, add real images under `images/`, and run:

```bash
cd app/backend && source .venv/bin/activate   # optional
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset
```

Requires `OPENAI_API_KEY` (e.g. in the repo root `.env`).
