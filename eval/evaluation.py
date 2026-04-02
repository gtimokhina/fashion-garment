"""
Evaluation: load labeled images, run the vision classifier, compare predictions to gold labels.

Compares four fields — ``garment_type``, ``style``, ``occasion``, and ``color`` (gold key
``color`` vs model ``color_palette``). Used by :file:`run_eval.py` and importable for tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Backend on path when imported from run_eval (caller sets cwd + sys.path before import).
from services.ai_classifier import ImageClassification, classify_image

from llm_judge import safe_judge_text, safe_judge_vision

EVAL_FIELDS = ("garment_type", "style", "occasion", "color")

EXPECTED_LABELS_VERSION = 1


def normalize_whitespace(s: str) -> str:
    return " ".join(s.lower().split()).strip()


def prediction_for_label_key(pred: ImageClassification, label_key: str) -> str:
    if label_key == "color":
        return pred.color_palette.value
    attr = getattr(pred, label_key, None)
    if attr is None:
        return ""
    return attr.value if hasattr(attr, "value") else str(attr)


def match_field(
    gold: str,
    pred: str,
    label_key: str,
    *,
    color_mode: str,
    text_match: str,
) -> bool:
    """Return True if gold label matches prediction under the chosen rules."""
    g = normalize_whitespace(gold)
    p = normalize_whitespace(pred)
    if not g:
        return True  # defensive; skipped upstream when gold empty
    if not p:
        return False

    if label_key == "color":
        if color_mode == "strict":
            return g == p
        tokens = [t.strip() for t in gold.split(",") if t.strip()]
        if not tokens:
            return g == p
        pl = p.lower()
        return all(normalize_whitespace(t).lower() in pl for t in tokens)

    if text_match == "token":
        tokens = [t.strip() for t in gold.split(",") if t.strip()]
        if not tokens:
            return g == p
        pl = p.lower()
        return all(normalize_whitespace(t).lower() in pl for t in tokens)

    return g == p


@dataclass
class FieldStats:
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float | None:
        if self.total == 0:
            return None
        return self.correct / self.total


def _empty_failures_dict() -> Dict[str, List[dict[str, Any]]]:
    return {f: [] for f in EVAL_FIELDS}


@dataclass
class EvalState:
    per_field: dict[str, FieldStats] = field(
        default_factory=lambda: {f: FieldStats() for f in EVAL_FIELDS}
    )
    errors: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    labels_version: int | None = None
    # Populated when judge_mode is set: semantic agreement (LLM), parallel to string match.
    judge_per_field: dict[str, FieldStats] | None = None
    judge_mode: Optional[str] = None
    # String-rule mismatches only (gold vs predicted under current rules).
    failures_string: Dict[str, List[dict[str, Any]]] = field(default_factory=_empty_failures_dict)
    # When LLM judge ran: cases where judge said not equivalent to gold.
    failures_judge: Optional[Dict[str, List[dict[str, Any]]]] = None


def load_dataset(dataset_dir: Path) -> tuple[list[dict[str, Any]], Path, int | None]:
    """Return (items, resolved dataset dir, labels version or None)."""
    root = dataset_dir.resolve()
    labels_path = root / "labels.json"
    if not labels_path.is_file():
        raise FileNotFoundError(f"Missing labels.json in {root}")
    raw = json.loads(labels_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("labels.json must be a JSON object")
    ver = raw.get("version")
    if ver is not None and not isinstance(ver, int):
        raise ValueError('labels.json "version" must be an integer if present')
    items = raw.get("items")
    if not isinstance(items, list):
        raise ValueError('labels.json must contain an "items" array')
    return items, root, ver if isinstance(ver, int) else None


def run_eval(
    dataset_dir: Path,
    *,
    color_mode: str,
    text_match: str,
    limit: int | None,
    judge_mode: Optional[str] = None,
) -> EvalState:
    items, root, version = load_dataset(dataset_dir)
    state = EvalState(
        labels_version=version,
        judge_mode=judge_mode,
        judge_per_field=(
            {f: FieldStats() for f in EVAL_FIELDS} if judge_mode else None
        ),
        failures_judge=_empty_failures_dict() if judge_mode else None,
    )

    if version is not None and version != EXPECTED_LABELS_VERSION:
        state.errors.append(
            f'labels.json version is {version}; this evaluator expects version {EXPECTED_LABELS_VERSION}.'
        )

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
            ok = match_field(gold, pr, fk, color_mode=color_mode, text_match=text_match)
            state.per_field[fk].total += 1
            if ok:
                state.per_field[fk].correct += 1
            else:
                state.failures_string[fk].append(
                    {"image": rel, "gold": gold, "predicted": pr}
                )
            fd: dict[str, Any] = {
                "gold": gold,
                "predicted": pr,
                "match": ok,
            }
            if judge_mode and state.judge_per_field is not None:
                if judge_mode == "text":
                    jr, err = safe_judge_text(fk, gold, pr, pred.description)
                else:
                    jr, err = safe_judge_vision(fk, gold, pr, img_path)
                if jr is None:
                    state.errors.append(f"{rel} field={fk}: LLM judge failed: {err}")
                    fd["judge"] = {"error": err}
                else:
                    fd["judge"] = {
                        "equivalent": jr.equivalent,
                        "confidence": jr.confidence,
                        "note": jr.note,
                    }
                    state.judge_per_field[fk].total += 1
                    if jr.equivalent:
                        state.judge_per_field[fk].correct += 1
                    elif state.failures_judge is not None:
                        state.failures_judge[fk].append(
                            {
                                "image": rel,
                                "gold": gold,
                                "predicted": pr,
                                "judge_note": jr.note,
                            }
                        )
            row["fields"][fk] = fd

        state.rows.append(row)

    return state


def micro_accuracy(state: EvalState) -> float | None:
    """Correct / total over all scored field slots (single number)."""
    c = sum(state.per_field[fk].correct for fk in EVAL_FIELDS)
    t = sum(state.per_field[fk].total for fk in EVAL_FIELDS)
    if t == 0:
        return None
    return c / t


def macro_accuracy(state: EvalState) -> float | None:
    """Mean of per-field accuracies (only fields with total > 0)."""
    accs = [state.per_field[fk].accuracy for fk in EVAL_FIELDS if state.per_field[fk].total > 0]
    if not accs:
        return None
    return sum(a for a in accs if a is not None) / len(accs)


def micro_accuracy_judge(state: EvalState) -> float | None:
    if not state.judge_per_field:
        return None
    c = sum(state.judge_per_field[fk].correct for fk in EVAL_FIELDS)
    t = sum(state.judge_per_field[fk].total for fk in EVAL_FIELDS)
    if t == 0:
        return None
    return c / t


def macro_accuracy_judge(state: EvalState) -> float | None:
    if not state.judge_per_field:
        return None
    accs = [
        state.judge_per_field[fk].accuracy
        for fk in EVAL_FIELDS
        if state.judge_per_field[fk].total > 0
    ]
    if not accs:
        return None
    return sum(a for a in accs if a is not None) / len(accs)


def format_results_table_md(state: EvalState) -> str:
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
    micro = micro_accuracy(state)
    macro = macro_accuracy(state)
    lines.append("| **micro** (all slots) | — | — | " + (f"{micro:.1%}" if micro is not None else "n/a") + " |")
    lines.append("| **macro** (mean of fields) | — | — | " + (f"{macro:.1%}" if macro is not None else "n/a") + " |")
    return "\n".join(lines)


def format_judge_table_md(state: EvalState) -> str:
    if not state.judge_per_field:
        return ""
    lines = [
        "",
        "| Field | Judge agrees | Total | Rate |",
        "|-------|--------------|-------|------|",
    ]
    for fk in EVAL_FIELDS:
        st = state.judge_per_field[fk]
        acc = st.accuracy
        acc_s = f"{acc:.1%}" if acc is not None else "n/a"
        lines.append(f"| {fk} | {st.correct} | {st.total} | {acc_s} |")
    mj = micro_accuracy_judge(state)
    ma = macro_accuracy_judge(state)
    lines.append(
        "| **micro** (judge slots) | — | — | "
        + (f"{mj:.1%}" if mj is not None else "n/a")
        + " |"
    )
    lines.append(
        "| **macro** (judge fields) | — | — | "
        + (f"{ma:.1%}" if ma is not None else "n/a")
        + " |"
    )
    return "\n".join(lines)


def format_judge_table_plain(state: EvalState) -> str:
    if not state.judge_per_field:
        return ""
    w = 14
    lines = [
        "",
        f"{'Field (judge)':<{w}} {'Agree':>8} {'Total':>8} {'Rate':>10}",
        "-" * (w + 8 + 8 + 10 + 3),
    ]
    for fk in EVAL_FIELDS:
        st = state.judge_per_field[fk]
        acc = st.accuracy
        acc_s = f"{acc:.1%}" if acc is not None else "n/a"
        lines.append(f"{fk:<{w}} {st.correct:>8} {st.total:>8} {acc_s:>10}")
    mj = micro_accuracy_judge(state)
    ma = macro_accuracy_judge(state)
    lines.append(
        f"{'micro (judge)':<{w}} {'—':>8} {'—':>8} {(f'{mj:.1%}' if mj is not None else 'n/a'):>10}"
    )
    lines.append(
        f"{'macro (judge)':<{w}} {'—':>8} {'—':>8} {(f'{ma:.1%}' if ma is not None else 'n/a'):>10}"
    )
    return "\n".join(lines)


def format_results_table_plain(state: EvalState) -> str:
    w = 14
    lines = [
        "",
        f"{'Field':<{w}} {'Correct':>8} {'Total':>8} {'Accuracy':>10}",
        "-" * (w + 8 + 8 + 10 + 3),
    ]
    for fk in EVAL_FIELDS:
        st = state.per_field[fk]
        acc = st.accuracy
        acc_s = f"{acc:.1%}" if acc is not None else "n/a"
        lines.append(f"{fk:<{w}} {st.correct:>8} {st.total:>8} {acc_s:>10}")
    micro = micro_accuracy(state)
    macro = macro_accuracy(state)
    lines.append(
        f"{'micro (slots)':<{w}} {'—':>8} {'—':>8} {(f'{micro:.1%}' if micro is not None else 'n/a'):>10}"
    )
    lines.append(
        f"{'macro (fields)':<{w}} {'—':>8} {'—':>8} {(f'{macro:.1%}' if macro is not None else 'n/a'):>10}"
    )
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

    micro = micro_accuracy(state)
    macro = macro_accuracy(state)
    if micro is not None:
        lines.append(
            f"**Micro-accuracy** (every labeled field slot): {micro:.1%} — pooled correct / pooled comparisons."
        )
    if macro is not None:
        lines.append(
            f"**Macro-accuracy** (mean of the four field rates): {macro:.1%} — treats each field equally."
        )

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

    spread = (best[1] or 0) - (worst[1] or 0)
    if spread > 0.2:
        lines.append(
            "Large gap between fields — consider tightening gold-label conventions or reviewing prompts for weaker attributes."
        )
    elif spread < 0.05 and best[1] and best[1] > 0.8:
        lines.append("Fields are relatively balanced and overall scores are high on this set.")

    if state.judge_per_field:
        mj = micro_accuracy_judge(state)
        mode = state.judge_mode or "unknown"
        lines.append(
            f"**LLM judge** ({mode}): micro {mj:.1%} — semantic agreement with gold (see judge table); "
            "compare to string-match table above for gap analysis."
        )
        if mj is not None and micro is not None and abs(mj - micro) > 0.1:
            lines.append(
                "String rules and LLM judge differ meaningfully — synonyms or paraphrases likely explain the gap."
            )
    return lines


def format_performance_report_md(state: EvalState) -> str:
    """Short narrative: error counts by attribute, where the model does well vs struggles."""
    lines: list[str] = ["", "## Performance report", ""]
    scored: list[tuple[str, float, int]] = []
    for fk in EVAL_FIELDS:
        st = state.per_field[fk]
        if st.total > 0 and st.accuracy is not None:
            scored.append((fk, st.accuracy, st.total))

    if not scored:
        lines.append("*No scored fields — add non-empty labels in `labels.json`.*")
        return "\n".join(lines)

    lines.append("### Error counts by attribute (string rules)")
    lines.append("")
    lines.append("| Attribute | Wrong | Labeled | Accuracy |")
    lines.append("|-----------|-------|---------|----------|")
    for fk in EVAL_FIELDS:
        st = state.per_field[fk]
        if st.total == 0:
            continue
        n_wrong = len(state.failures_string[fk])
        acc = st.accuracy
        acc_s = f"{acc:.1%}" if acc is not None else "n/a"
        lines.append(f"| {fk} | {n_wrong} | {st.total} | {acc_s} |")
    lines.append("")

    scored.sort(key=lambda x: x[1], reverse=True)
    best_acc, worst_acc = scored[0][1], scored[-1][1]
    spread = best_acc - worst_acc

    strong = [x for x in scored if x[1] >= 0.72]
    weak = [x for x in scored if x[1] < 0.62]

    lines.append("### Where the model performs relatively well")
    lines.append("")
    if strong:
        frag = ", ".join(f"**{fk}** ({acc:.0%} on {n})" for fk, acc, n in strong)
        lines.append(f"- {frag}.")
    else:
        fk, acc, n = scored[0]
        lines.append(
            f"- Strongest field is **{fk}** at **{acc:.0%}** ({n} labeled); none reached 72% under current matching rules."
        )
    lines.append("")

    lines.append("### Where it struggles")
    lines.append("")
    if weak:
        frag = ", ".join(f"**{fk}** ({acc:.0%})" for fk, acc, n in weak)
        lines.append(f"- {frag}.")
    else:
        fk, acc, n = scored[-1]
        if spread <= 0.08:
            lines.append(
                f"- Fields are close in accuracy (spread {spread:.0%}); lowest is **{fk}** at **{acc:.0%}**."
            )
        else:
            lines.append(
                f"- Lowest accuracy: **{fk}** (**{acc:.0%}**, {n} items). Consider gold-label wording vs model vocabulary for this attribute."
            )
    lines.append("")

    if spread > 0.15:
        lines.append(
            f"- **Spread** between best and worst field is **{spread:.0%}** — prioritize error analysis on the weakest attribute."
        )
        lines.append("")

    if state.failures_judge:
        j_total = sum(len(state.failures_judge[fk]) for fk in EVAL_FIELDS)
        s_total = sum(len(state.failures_string[fk]) for fk in EVAL_FIELDS)
        lines.append("### LLM judge vs string rules")
        lines.append("")
        lines.append(
            f"- Judge rejected **{j_total}** field prediction(s) as not equivalent to gold; "
            f"string rules flagged **{s_total}** mismatch(es). "
            "Large gaps often mean synonyms or paraphrases the judge accepts but strict rules do not."
        )
        lines.append("")

    return "\n".join(lines)


def format_failure_examples_md(
    state: EvalState,
    max_per_field: int,
    *,
    include_judge: bool,
) -> str:
    """Grouped failure examples (string rules; optional judge rejections)."""
    lines: list[str] = ["", "## Incorrect predictions — by attribute", ""]

    any_string = any(state.failures_string[fk] for fk in EVAL_FIELDS)
    any_judge = bool(
        include_judge
        and state.failures_judge
        and any(state.failures_judge[fk] for fk in EVAL_FIELDS)
    )

    if not any_string and not any_judge:
        lines.append("*No failures to show for this run.*")
        return "\n".join(lines)

    if max_per_field <= 0:
        lines.append(
            "*Example lines suppressed (`--failure-examples 0`). Error counts are in the performance report and JSON export.*"
        )
        lines.append("")
    else:
        lines.append(
            f"*Up to **{max_per_field}** example(s) per attribute; full lists in `--output-json` under `failures_string` / `failures_judge`.*"
        )
        lines.append("")

    if any_string:
        lines.append("### String rules (prediction did not match gold)")
        lines.append("")
        for fk in EVAL_FIELDS:
            fails = state.failures_string[fk]
            if not fails:
                continue
            lines.append(f"#### `{fk}` — **{len(fails)}** incorrect")
            lines.append("")
            if max_per_field > 0:
                for ex in fails[:max_per_field]:
                    img = str(ex.get("image", "")).replace("|", "\\|")
                    lines.append(f"- `{img}`")
                    lines.append(f"  - **Gold:** {ex.get('gold', '')}")
                    lines.append(f"  - **Predicted:** {ex.get('predicted', '')}")
                if len(fails) > max_per_field:
                    lines.append(
                        f"- *… and {len(fails) - max_per_field} more for this attribute*"
                    )
            lines.append("")

    if any_judge and state.failures_judge:
        lines.append("### LLM judge: not equivalent to gold")
        lines.append("")
        for fk in EVAL_FIELDS:
            fails = state.failures_judge[fk]
            if not fails:
                continue
            lines.append(f"#### `{fk}` — **{len(fails)}** rejection(s)")
            lines.append("")
            if max_per_field > 0:
                for ex in fails[:max_per_field]:
                    img = str(ex.get("image", "")).replace("|", "\\|")
                    lines.append(f"- `{img}`")
                    lines.append(f"  - **Gold:** {ex.get('gold', '')}")
                    lines.append(f"  - **Predicted:** {ex.get('predicted', '')}")
                    note = ex.get("judge_note") or ""
                    if note:
                        lines.append(f"  - *Judge note:* {note}")
                if len(fails) > max_per_field:
                    lines.append(
                        f"- *… and {len(fails) - max_per_field} more for this attribute*"
                    )
            lines.append("")

    return "\n".join(lines)


def json_payload(
    dataset: Path,
    color_mode: str,
    text_match: str,
    state: EvalState,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "dataset": str(dataset.resolve()),
        "color_mode": color_mode,
        "text_match": text_match,
        "labels_version": state.labels_version,
        "judge_mode": state.judge_mode,
        "per_field": {
            fk: {
                "correct": state.per_field[fk].correct,
                "total": state.per_field[fk].total,
                "accuracy": state.per_field[fk].accuracy,
            }
            for fk in EVAL_FIELDS
        },
        "micro_accuracy": micro_accuracy(state),
        "macro_accuracy": macro_accuracy(state),
        "failures_string": {fk: state.failures_string[fk] for fk in EVAL_FIELDS},
        "failure_counts_string": {fk: len(state.failures_string[fk]) for fk in EVAL_FIELDS},
        "rows": state.rows,
        "errors": state.errors,
    }
    if state.judge_per_field:
        out["judge_per_field"] = {
            fk: {
                "correct": state.judge_per_field[fk].correct,
                "total": state.judge_per_field[fk].total,
                "accuracy": state.judge_per_field[fk].accuracy,
            }
            for fk in EVAL_FIELDS
        }
        out["micro_accuracy_judge"] = micro_accuracy_judge(state)
        out["macro_accuracy_judge"] = macro_accuracy_judge(state)
        if state.failures_judge is not None:
            out["failures_judge"] = {fk: state.failures_judge[fk] for fk in EVAL_FIELDS}
            out["failure_counts_judge"] = {
                fk: len(state.failures_judge[fk]) for fk in EVAL_FIELDS
            }
    return out
