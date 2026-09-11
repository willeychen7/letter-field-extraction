"""
Phase 4 research run: classify all 50 benchmark images (20 dev + 30
holdout) into the 8 domains, compare to gt_domain.py, and dump the
confusion structure. No rule tuning to any set. Phase 3 stays frozen.
"""

import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))

import structure as ST                       # frozen, read-only
from domain import classify_domain, DOMAINS  # noqa: E402
from gt_domain import GT_DOMAIN               # noqa: E402
from ocr import parse_ocr_elements            # frozen, read-only

HERE = os.path.dirname(__file__)
DEV_RAW = os.path.join(HERE, "results", "full20", "raw")
HOLD_RAW = os.path.join(HERE, "results", "holdout", "raw")
OUT = os.path.join(HERE, "results", "domain")


def _load_text(key):
    for base, suff in ((DEV_RAW, ".ocr.json"), (HOLD_RAW, ".ocr.json")):
        p = os.path.join(base, key + suff)
        if os.path.exists(p):
            content = json.load(open(p))["content"]
            els = parse_ocr_elements(content)
            text = " ".join(e["text"] for e in els)
            lh = ST.classify_sender(els)
            head = lh[0]["value"] if lh else ""
            return text, head, ("dev" if base == DEV_RAW else "holdout")
    return None, None, None


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    confusion = defaultdict(Counter)
    for key, (gold, note) in GT_DOMAIN.items():
        text, head, split = _load_text(key)
        if text is None:
            print("MISSING OCR:", key)
            continue
        r = classify_domain(text, head)
        ok = r["pred"] == gold
        confusion[gold][r["pred"]] += 1
        rows.append({
            "key": key, "split": split, "gold": gold, "pred": r["pred"],
            "correct": ok, "top": r["top"], "top_score": r["top_score"],
            "second": r["second"], "second_score": r["second_score"],
            "gap": r["gap"], "letterhead": head, "note": note,
            "evidence": r["evidence"],
        })

    n = len(rows)
    correct = sum(1 for x in rows if x["correct"])
    other_pred = sum(1 for x in rows if x["pred"] == "OTHER")
    other_gold = sum(1 for x in rows if x["gold"] == "OTHER")

    json.dump({"n": n, "accuracy": round(correct / n, 4), "correct": correct,
               "other_predicted": other_pred, "other_gold": other_gold,
               "confusion": {g: dict(c) for g, c in confusion.items()},
               "rows": rows},
              open(os.path.join(OUT, "summary.json"), "w"),
              ensure_ascii=False, indent=2)

    print(f"=== DOMAIN classification: {correct}/{n} = {correct/n:.3f} "
          f"(agreement with hand labels) ===\n")

    print("per row:")
    for x in sorted(rows, key=lambda r: (r["split"], r["gold"], r["key"])):
        mark = "  " if x["correct"] else "XX"
        flag = "  <<" + x["note"][:60] if x["note"] else ""
        print(f" {mark} [{x['split'][:4]}] {x['key']:32s} gold={x['gold']:18s} "
              f"pred={x['pred']:18s} (top={x['top_score']} gap={x['gap']}){flag}")

    print("\nconfusion (gold -> predicted counts):")
    for g in DOMAINS:
        if g in confusion:
            line = "  ".join(f"{p}:{c}" for p, c in confusion[g].most_common())
            print(f"  {g:20s} -> {line}")

    print("\ngold distribution :", dict(Counter(x['gold'] for x in rows)))
    print("pred distribution :", dict(Counter(x['pred'] for x in rows)))
    print(f"\nOTHER: gold={other_gold}/{n} ({other_gold/n:.0%})  "
          f"predicted={other_pred}/{n} ({other_pred/n:.0%})")
    print(f"\n[out] {OUT}/summary.json")


if __name__ == "__main__":
    main()
