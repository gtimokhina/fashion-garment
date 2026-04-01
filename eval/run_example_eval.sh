#!/usr/bin/env bash
# Export images + labels from SQLite into eval/data/example_dataset, then run classifier eval.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/app/backend"
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
"$PY" ../../eval/scripts/export_dataset_from_db.py --dataset ../../eval/data/example_dataset
"$PY" ../../eval/run_eval.py --dataset ../../eval/data/example_dataset --verbose
