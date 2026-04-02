#!/usr/bin/env python3
"""
CLI for classifier evaluation. Core logic lives in :mod:`evaluation`.

  cd app/backend && source .venv/bin/activate
  python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset

See :file:`README.md` in this directory and :file:`data/example_dataset/README.md`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from evaluation import (  # noqa: E402  # import after path/cwd
    format_failure_examples_md,
    format_judge_table_md,
    format_judge_table_plain,
    format_performance_report_md,
    format_per_image_table,
    format_results_table_md,
    format_results_table_plain,
    json_payload,
    run_eval,
    summary_insights,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the vision classifier on a labeled image dataset (see eval/data/example_dataset).",
    )
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
        help="Color: strict normalized equality, or token (each gold comma-token substring in prediction).",
    )
    parser.add_argument(
        "--text-match",
        choices=("exact", "token"),
        default="exact",
        help="garment_type, style, occasion: exact string match after normalization, or token "
        "(each comma-separated gold fragment must appear in prediction).",
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
    parser.add_argument(
        "--format",
        choices=("md", "plain", "both"),
        default="both",
        help="Result table: Markdown, plain ASCII, or both (default: both)",
    )
    parser.add_argument(
        "--llm-judge",
        choices=("none", "text", "vision"),
        default="none",
        help="Optional second LLM pass: semantic agreement with gold. "
        "'text' uses classifier description + labels (cheap). "
        "'vision' re-sends the image (expensive). Default: none.",
    )
    parser.add_argument(
        "--failure-examples",
        type=int,
        default=8,
        metavar="N",
        help="Max incorrect examples printed per attribute (string rules + judge); 0 = counts only. Default: 8.",
    )
    parser.add_argument(
        "--no-performance-report",
        action="store_true",
        help="Skip the performance narrative and grouped failure sections.",
    )
    args = parser.parse_args()

    judge_mode = None if args.llm_judge == "none" else args.llm_judge

    try:
        state = run_eval(
            args.dataset,
            color_mode=args.color_mode,
            text_match=args.text_match,
            limit=args.limit,
            judge_mode=judge_mode,
        )
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    n_images = len(state.rows)
    print("# Classifier evaluation")
    print()
    print(f"- Dataset: `{args.dataset.resolve()}`")
    print(f"- Color scoring: **{args.color_mode}**")
    print(f"- Text fields (garment_type, style, occasion): **{args.text_match}**")
    if judge_mode:
        print(f"- LLM judge: **{judge_mode}** (semantic agreement; see second table)")
    print()
    print("## Summary (string rules — accuracy per field)")
    if args.format in ("md", "both"):
        print(format_results_table_md(state))
    if args.format == "both":
        print()
        print("### Plain table")
        print(format_results_table_plain(state))
    elif args.format == "plain":
        print(format_results_table_plain(state))

    if judge_mode and state.judge_per_field:
        print()
        print("## LLM judge (semantic agreement with gold)")
        if args.format in ("md", "both"):
            print(format_judge_table_md(state))
        if args.format == "both":
            print()
            print("### Plain (judge)")
            print(format_judge_table_plain(state))
        elif args.format == "plain":
            print(format_judge_table_plain(state))

    if not args.no_performance_report:
        print(format_performance_report_md(state))
        print(
            format_failure_examples_md(
                state,
                max_per_field=max(0, args.failure_examples),
                include_judge=bool(judge_mode),
            )
        )

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
        out = json_payload(
            args.dataset.resolve(),
            args.color_mode,
            args.text_match,
            state,
        )
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print()
        print(f"Wrote JSON results to `{args.output_json}`")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
