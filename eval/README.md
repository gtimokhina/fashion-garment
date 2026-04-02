# Evaluation pipeline

Offline evaluation of the **vision classifier** (`app/backend/services/ai_classifier.py`) against a **labeled image set**.

## What it does

1. **Load** a dataset directory containing `labels.json` and image files (paths relative to that directory).
2. **Classify** each image with the same `classify_image()` path as production (OpenAI vision + JSON schema).
3. **Compare** model output to gold labels for four fields:

| Gold key in JSON | Model field | Notes |
|------------------|-------------|--------|
| `garment_type` | `garment_type` | See matching modes below. |
| `style` | `style` | |
| `occasion` | `occasion` | |
| `color` | `color_palette` | Gold uses key `color`; model has no `color` field. |

4. **Report** per-field accuracy, **micro** (pooled correct / pooled labeled slots) and **macro** (mean of the four field accuracies), plus short **insights** (best/worst field, spread).

### Optional: LLM as judge

Deterministic **string rules** can miss synonyms (“navy” vs “dark blue”). With **`--llm-judge`**, a **second** OpenAI call per labeled field scores **semantic** agreement between the gold label and the classifier output:

| Mode | What the judge sees | Cost |
|------|----------------------|------|
| **`text`** | Field name, gold, predicted, plus the classifier’s **description** (no extra image) | 4 × N extra chat calls |
| **`vision`** | Same labels plus the **image** (low detail) | 4 × N extra **vision** calls |

Use **`EVAL_JUDGE_MODEL`** in the repo root `.env` to pick a cheaper judge (e.g. `gpt-4o-mini`); it defaults to **`OPENAI_MODEL`**. Judge results appear in a **second** summary table and in each row under `fields.<name>.judge` (`equivalent`, `confidence`, `note`).

```bash
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset --llm-judge text
```

## Dataset format

See **[`data/example_dataset/README.md`](data/example_dataset/README.md)** and **[`data/example_dataset/labels.example.json`](data/example_dataset/labels.example.json)**.

- **`version`**: use `1` (current format).
- **`items`**: each entry has `image` (relative path) and `labels` (object with any of the four keys; omit or use empty string to skip scoring that field for that image).

## How to run

From `app/backend` (venv recommended so `openai` and `.env` match):

```bash
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset
```

| Flag | Meaning |
|------|---------|
| `--dataset DIR` | Dataset root (default: `eval/data/example_dataset`). |
| `--color-mode strict\|token` | **token** (default): each comma-separated color in gold must appear as a substring in the prediction. **strict**: normalized full-string equality. |
| `--text-match exact\|token` | For garment_type, style, occasion: **exact** (default) normalized match, or **token**: each gold comma-fragment must appear in the prediction (useful for multi-label gold strings). |
| `--limit N` | Only first N items (smoke test). |
| `--verbose` | Per-image ✓/✗ table and JSON lines with gold vs predicted. |
| `--output-json PATH` | Machine-readable full report (includes micro/macro, rows, errors). |
| `--format md\|plain\|both` | Markdown table, ASCII table, or both (default **both**). |
| `--llm-judge none\|text\|vision` | Optional semantic judge (see above). Default **none**. |
| `--failure-examples N` | How many wrong examples to print **per attribute** (string rules + judge). `0` = counts only. Default **8**. |
| `--no-performance-report` | Skip the narrative “performance report” and grouped failure sections. |

After each run, the CLI prints a **performance report** (error counts by attribute, where the model does well vs struggles) and **incorrect predictions grouped by field** (with examples). Full failure lists are always included in **`--output-json`** (`failures_string`, `failure_counts_string`, and `failures_judge` when applicable).

**Environment:** `OPENAI_API_KEY` and optional `OPENAI_MODEL` in the repo root `.env` (loaded when the backend package initializes). Optional **`EVAL_JUDGE_MODEL`** for the judge only.

## Code layout

| File | Role |
|------|------|
| [`run_eval.py`](run_eval.py) | CLI: adjusts `sys.path` / `cwd` to the backend, then imports [`evaluation.py`](evaluation.py). |
| [`evaluation.py`](evaluation.py) | Load labels, run classifier, scoring, tables, insights, JSON export payload. |
| [`llm_judge.py`](llm_judge.py) | OpenAI JSON judge for `--llm-judge text` / `vision`. |

**Export gold data from the app DB** (images + labels from stored metadata):

```bash
cd app/backend && python3 ../../eval/scripts/export_dataset_from_db.py --dataset ../../eval/data/example_dataset
```

**One-shot export + eval:**

```bash
bash eval/run_example_eval.sh
```
