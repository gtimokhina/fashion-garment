#!/usr/bin/env python3
"""
Evaluate the vision classifier against a labeled image dataset.

Loads images + labels (see eval/data/example_dataset/), runs the same
:classify_image pipeline as production, and reports per-field accuracy for:
garment_type, style, occasion, color (gold ``color`` vs predicted ``color_palette``).

Usage (from repo root, backend venv recommended):

  cd app/backend && source .venv/bin/activate
  python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset

Environment: OPENAI_API_KEY and optional OPENAI_MODEL (see app/backend/.env).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Resolve backend package (loads app/backend/.env via ai_classifier → config)
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from services.ai_classifier import ImageClassification, classify_image  # noqa: E402

EVAL_FIELDS = ("garment_type", "style", "occasion", "color")


def normalize_whitespace(s: str) -> str:
    return " ".join(s.lower().split()).strip()


def prediction_for_label_key(pred: ImageClassification, label_key: str) -> str:
    if label_key == "color":
        return pred.color_palette.value
    attr = getattr(pred, label_key, None)
    if attr is None:
        return ""
    return attr.value if hasattr(attr, "value") else str(attr)


def match_field(gold: str, pred: str, label_key: str, *, color_mode: str) -> bool:
    """Return True if gold label matches prediction under the chosen rules."""
    g = normalize_whitespace(gold)
    p = normalize_whitespace(pred)
    if not g:
        return True  # defensive; skipped upstream when gold empty
    if not p:
        return False

    if label_key != "color":
        return g == p

    if color_mode == "strict":
        return g == p

    # token: each comma-separated token in gold must appear in the prediction (substring).
    tokens = [t.strip() for t in gold.split(",") if t.strip()]
    if not tokens:
        return g == p
    pl = p
    return all(normalize_whitespace(t) in pl for t in tokens)


@dataclass
class FieldStats:
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float | None:
        if self.total == 0:
            return None
        return self.correct / self.total


@dataclass
class EvalState:
    per_field: dict[str, FieldStats] = field(
        default_factory=lambda: {f: FieldStats() for f in EVAL_FIELDS}
    )
    errors: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


def load_dataset(dataset_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    """Return (items, resolved dataset dir)."""
    root = dataset_dir.resolve()
    labels_path = root / "labels.json"
    if not labels_path.is_file():
        raise FileNotFoundError(f"Missing labels.json in {root}")
    raw = json.loads(labels_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("labels.json must be a JSON object")
    items = raw.get("items")
    if not isinstance(items, list):
        raise ValueError('labels.json must contain an "items" array')
    return items, root


def run_eval(
    dataset_dir: Path,
    *,
    color_mode: str,
    limit: int | None,
) -> EvalState:
    items, root = load_dataset(dataset_dir)
    state = EvalState()

    for i, item in enumerate(items):
        if limit is not None and i >= limit:
            break
        if not isinstance(item, dict):
            state.errors.append(f"items[{i}]: expected object, skipping")
            continue
        rel = item.get("image")
        labels = item.get("labels")
        if not isinstance(rel, str) or not rel.strip():
            state.errors.append(f"items[{i}]: missing image path")
            continue
        if not isinstance(labels, dict):
            state.errors.append(f"items[{i}]: missing labels object")
            continue

        img_path = (root / rel).resolve()
        if not img_path.is_file():
            state.errors.append(f"Image not found: {img_path}")
            continue

        try:
            pred = classify_image(img_path).classification
        except Exception as e:
            state.errors.append(f"{rel}: classify_image failed: {e}")
            continue

        row: dict[str, Any] = {
            "image": rel,
            "fields": {},
        }
        for fk in EVAL_FIELDS:
            raw = labels.get(fk)
            gold = str(raw).strip() if raw is not None else ""
            if not gold:
                row["fields"][fk] = {"skipped": True}
                continue
            pr = prediction_for_label_key(pred, fk)
            ok = match_field(gold, pr, fk, color_mode=color_mode)
            state.per_field[fk].total += 1
            if ok:
                state.per_field[fk].correct += 1
            row["fields"][fk] = {
                "gold": gold,
                "predicted": pr,
                "match": ok,
            }

        state.rows.append(row)

    return state


def format_results_table(state: EvalState) -> str:
    lines = [
        "",
        "| Field | Correct | Total | Accuracy |",
        "|-------|---------|-------|----------|",
    ]
    for fk in EVAL_FIELDS:
        st = state.per_field[fk]
        acc = st.accuracy
        acc_s = f"{acc:.1%}" if acc is not None else "n/a"
        lines.append(f"| {fk} | {st.correct} | {st.total} | {acc_s} |")
    return "\n".join(lines)


def format_per_image_table(state: EvalState) -> str:
    if not state.rows:
        return ""
    header = "| Image | " + " | ".join(EVAL_FIELDS) + " |"
    sep = "|" + "|".join(["---"] * (1 + len(EVAL_FIELDS))) + "|"
    lines = ["", "### Per image", "", header, sep]
    for row in state.rows:
        img = row["image"].replace("|", "\\|")
        cells = []
        for fk in EVAL_FIELDS:
            fd = row["fields"].get(fk, {})
            if fd.get("skipped"):
                cells.append("—")
            elif fd.get("match"):
                cells.append("✓")
            else:
                cells.append("✗")
        lines.append("| " + img + " | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def summary_insights(state: EvalState, n_images: int) -> list[str]:
    lines: list[str] = []
    lines.append(f"Images successfully classified: {n_images}.")
    if state.errors:
        lines.append(f"Warnings/errors: {len(state.errors)} (see below).")

    scored = [
        (fk, state.per_field[fk].accuracy, state.per_field[fk].total)
        for fk in EVAL_FIELDS
        if state.per_field[fk].total > 0
    ]
    if not scored:
        lines.append("No labeled fields to score (add non-empty labels in labels.json).")
        return lines

    scored.sort(key=lambda x: x[1] or 0.0)
    worst = scored[0]
    best = scored[-1]
    lines.append(
        f"Lowest accuracy: **{worst[0]}** ({worst[1]:.1%} over {worst[2]} labeled instances)."
    )
    lines.append(
        f"Highest accuracy: **{best[0]}** ({best[1]:.1%} over {best[2]} labeled instances)."
    )

    # Short interpretation
    spread = (best[1] or 0) - (worst[1] or 0)
    if spread > 0.2:
        lines.append(
            "Large gap between fields — consider more consistent gold labels or a tuned prompt for weaker attributes."
        )
    elif spread < 0.05 and best[1] and best[1] > 0.8:
        lines.append("Fields are relatively balanced and overall scores are high on this set.")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Run classifier eval on a labeled dataset.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "eval" / "data" / "example_dataset",
        help="Path to dataset directory (contains labels.json and image files)",
    )
    parser.add_argument(
        "--color-mode",
        choices=("strict", "token"),
        default="token",
        help="How to score color: strict normalized equality, or token (each gold comma-token in pred).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of dataset items to run (for quick tests)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-image match table and gold vs predicted detail in JSON",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Write full results (counts, rows, errors) to this JSON file",
    )
    args = parser.parse_args()

    try:
        state = run_eval(
            args.dataset,
            color_mode=args.color_mode,
            limit=args.limit,
        )
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    n_images = len(state.rows)
    print("# Classifier evaluation")
    print()
    print(f"- Dataset: `{args.dataset.resolve()}`")
    print(f"- Color scoring: **{args.color_mode}**")
    print()
    print("## Summary (accuracy per field)")
    print(format_results_table(state))

    print()
    print("## Insights")
    for line in summary_insights(state, n_images):
        print(f"- {line}")

    if args.verbose:
        print(format_per_image_table(state))
        print()
        print("### Detail (gold vs predicted)")
        print("```json")
        print(json.dumps(state.rows, indent=2))
        print("```")

    if state.errors:
        print()
        print("## Issues")
        for e in state.errors:
            print(f"- {e}")

    if args.output_json:
        out = {
            "dataset": str(args.dataset.resolve()),
            "color_mode": args.color_mode,
            "per_field": {
                fk: {
                    "correct": state.per_field[fk].correct,
                    "total": state.per_field[fk].total,
                    "accuracy": state.per_field[fk].accuracy,
                }
                for fk in EVAL_FIELDS
            },
            "rows": state.rows,
            "errors": state.errors,
        }
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print()
        print(f"Wrote JSON results to `{args.output_json}`")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
