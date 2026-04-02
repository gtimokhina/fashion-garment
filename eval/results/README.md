# Evaluation snapshots

Pinned outputs from `eval/run_eval.py` for documentation and regression baselines.

| File | Description |
|------|-------------|
| [`eval_snapshot_gpt4o.json`](eval_snapshot_gpt4o.json) | Full run output (`--output-json`): per-row gold vs predicted, failure lists, `per_field` counts. |
| [`snapshot_manifest.json`](snapshot_manifest.json) | Aggregates only (small diff-friendly summary). |

Reproduce (from `app/backend` with `OPENAI_*` set):

```bash
python3 ../../eval/run_eval.py --dataset ../../eval/data/example_dataset \
  --color-mode token --text-match exact --llm-judge none \
  --failure-examples 0 --no-performance-report \
  --output-json ../../eval/results/eval_snapshot_gpt4o.json
```
