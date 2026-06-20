"""Eval harness: compute precision/recall/F1 against a labeled JSONL dataset.

Usage:
  python eval/score.py eval/validation.jsonl [--threshold 0.08]

Dataset format (one JSON object per line):
  {
    "text": "...",
    "label": 1,           // 1=slop, 0=not-slop
    "category": "FP_trap|FN_trap|general",
    "note": "optional annotation"
  }

Reports:
  - Overall precision, recall, F1 at the given threshold
  - Per-category breakdown
  - Confusion matrix
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import defluff


def evaluate(dataset_path: Path, threshold: float, packs: list[str] | None = None) -> None:
    records = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("No records found.")
        return

    lex = defluff.load_lexicon(packs=packs, no_project_overlay=True)

    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    by_cat: dict[str, dict[str, int]] = {}

    for rec in records:
        text = rec["text"]
        label = int(rec["label"])
        cat = rec.get("category", "general")

        try:
            predicted = 1 if defluff.score(text, lexicon=lex) > threshold else 0
        except ValueError:
            predicted = 0

        if cat not in by_cat:
            by_cat[cat] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}

        if predicted == 1 and label == 1:
            cell = "tp"
        elif predicted == 1 and label == 0:
            cell = "fp"
        elif predicted == 0 and label == 0:
            cell = "tn"
        else:
            cell = "fn"
        by_cat[cat][cell] += 1
        counts[cell] += 1

    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"Threshold: {threshold}")
    print(f"Dataset:   {dataset_path} ({len(records)} records)")
    print("")
    print(f"{'':20s}  {'P':>6}  {'R':>6}  {'F1':>6}")
    print(f"{'Overall':20s}  {precision:6.3f}  {recall:6.3f}  {f1:6.3f}")
    print("")
    print(f"Confusion matrix: TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print("")
    print("Per-category:")
    for cat, counts in sorted(by_cat.items()):
        ctp, cfp, ctn, cfn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
        cp = ctp / (ctp + cfp) if (ctp + cfp) else 0.0
        cr = ctp / (ctp + cfn) if (ctp + cfn) else 0.0
        cf = 2 * cp * cr / (cp + cr) if (cp + cr) else 0.0
        print(f"  {cat:20s}  P={cp:.3f}  R={cr:.3f}  F1={cf:.3f}  "
              f"(n={ctp+cfp+ctn+cfn})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--pack", default=None,
                        help="Comma-separated bundled pack(s) to layer on the base lexicon.")
    args = parser.parse_args()

    packs = [p.strip() for p in args.pack.split(",")] if args.pack else None

    if args.threshold is None:
        lex = defluff.load_lexicon(no_project_overlay=True)
        args.threshold = lex.meta.default_threshold
        if lex.meta.threshold_provisional:
            print(f"Note: using provisional threshold {args.threshold} from lexicon data")
    if packs:
        print(f"Packs layered: {', '.join(packs)}")

    evaluate(args.dataset, args.threshold, packs=packs)


if __name__ == "__main__":
    main()
