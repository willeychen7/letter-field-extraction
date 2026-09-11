"""
HOLDOUT test of the FROZEN Phase 3 pipeline.

30 fresh US letters that were NOT used to build / tune / threshold Phase 3
(none appear in run_full20.py's IMAGES or ground_truth_20.py). Covers
utility / medical / insurance / DMV / Medicare / bank / HOA / general.
webp/avif originals were converted to PNG (content-preserving) in
holdout_images/.

Pipeline code (structure.py / extract.py / anchors.py / ocr.py) is the
frozen Phase 3 -- no change. This script only runs it and scores.

    python3 run_holdout.py             # fresh OCR
    python3 run_holdout.py --use-cache
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import extract as X                         # noqa: E402  (frozen)
import ground_truth as GTM                  # noqa: E402  (frozen scorer)
from ground_truth_holdout import GT_HOLD, GT_FIELDS, GT_CONF  # noqa: E402
from holdout_set import HOLDOUT             # noqa: E402
from ocr import call_ocr, parse_ocr_elements  # noqa: E402  (frozen)

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "results", "holdout")
RAW = os.path.join(OUT, "raw")


def _src(d, fn):
    return os.path.join(d, fn) if d.startswith("/") else os.path.join(HERE, d, fn)


def get_ocr(key, d, fn, use_cache):
    cache = os.path.join(RAW, f"{key}.ocr.json")
    if use_cache and os.path.exists(cache):
        return json.load(open(cache))
    r = call_ocr(_src(d, fn), timeout=400)
    json.dump(r, open(cache, "w"), ensure_ascii=False, indent=2)
    open(os.path.join(RAW, f"{key}.ocr.txt"), "w").write(r["content"])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)

    preds, ocr_meta, cats = {}, {}, {}
    for key, d, fn, cat in HOLDOUT:
        cats[key] = cat
        r = get_ocr(key, d, fn, args.use_cache)
        els = parse_ocr_elements(r["content"])
        fields = X.extract_fields(els)
        preds[key] = {f: fields[f]["value"] for f in GT_FIELDS}
        ocr_meta[key] = {"finish_reason": r["finish_reason"],
                         "truncated": r["finish_reason"] == "length",
                         "elapsed_s": r["elapsed_s"],
                         "element_count": len(els)}
        json.dump({"key": key, "category": cat, "ocr": ocr_meta[key],
                   "elements": els, "fields": fields, "final": preds[key]},
                  open(os.path.join(RAW, f"{key}.json"), "w"),
                  ensure_ascii=False, indent=2)
        tr = "  <<TRUNC>>" if ocr_meta[key]["truncated"] else ""
        print(f"{key:30s} {cat:10s} {ocr_meta[key]['element_count']:4d} els  "
              f"{r['elapsed_s']:6.1f}s{tr}")

    # score
    per_field = {f: [0, 0] for f in GT_FIELDS}
    per_cat = {}
    kinds = {}
    rows = []
    tot_c = tot = 0
    nh = ns = 0
    for key in preds:
        gt = GT_HOLD[key]
        per_cat.setdefault(cats[key], [0, 0])
        for f in GT_FIELDS:
            entry = gt[f]
            pred = preds[key][f]
            ok, kind = GTM.score_field(f, pred, entry)
            per_field[f][0] += int(ok); per_field[f][1] += 1
            per_cat[cats[key]][0] += int(ok); per_cat[cats[key]][1] += 1
            kinds[kind] = kinds.get(kind, 0) + 1
            tot += 1; tot_c += int(ok)
            if entry["value"] is None and None not in entry.get("accept", []):
                ns += 1
                if kind == "null_hallucination":
                    nh += 1
            rows.append({"key": key, "category": cats[key], "field": f,
                         "pred": pred, "gold": entry["value"],
                         "correct": ok, "kind": kind, "gt_conf": GT_CONF[key]})

    summary = {
        "n_images": len(HOLDOUT),
        "overall_accuracy": round(tot_c / tot, 4),
        "correct": tot_c, "total": tot,
        "dev_benchmark_reference": {"overall": 0.892, "note": "frozen Phase 3 on the 20-image dev set"},
        "per_field": {f: {"accuracy": round(v[0] / v[1], 4), "correct": v[0], "total": v[1]}
                      for f, v in per_field.items()},
        "per_category": {c: {"accuracy": round(v[0] / v[1], 4), "correct": v[0], "total": v[1]}
                         for c, v in per_cat.items()},
        "answer_taxonomy": kinds,
        "null_hallucination": {"count": nh, "null_slots": ns,
                               "rate": round(nh / ns, 4) if ns else 0.0},
        "truncated_images": [k for k, m in ocr_meta.items() if m["truncated"]],
        "gt_confidence_counts": {c: sum(1 for k in GT_CONF if GT_CONF[k] == c)
                                 for c in set(GT_CONF.values())},
        "ocr": ocr_meta,
        "rows": rows,
        "predictions": preds,
    }
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"),
              ensure_ascii=False, indent=2)

    with open(os.path.join(OUT, "comparison.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "holdout_acc", "dev_acc", "delta"])
        DEV = {"sender": 0.95, "recipient": 1.0, "total_amount": 0.95,
               "payment_status": 0.75, "due_date": 0.90, "action": 0.80}
        for f in GT_FIELDS:
            h = summary["per_field"][f]["accuracy"]
            w.writerow([f, f"{h:.3f}", f"{DEV[f]:.3f}", f"{h - DEV[f]:+.3f}"])
        w.writerow(["OVERALL", f"{summary['overall_accuracy']:.3f}", "0.892",
                    f"{summary['overall_accuracy'] - 0.892:+.3f}"])

    print("\n== HOLDOUT (frozen Phase 3) ==")
    for f in GT_FIELDS:
        v = summary["per_field"][f]
        print(f"  {f:15s} {v['accuracy']:.3f}  ({v['correct']}/{v['total']})")
    print(f"  {'OVERALL':15s} {summary['overall_accuracy']:.3f}  ({tot_c}/{tot})"
          f"   [dev benchmark: 0.892]")
    print("\n  per category:")
    for c, v in summary["per_category"].items():
        print(f"    {c:12s} {v['accuracy']:.3f}  ({v['correct']}/{v['total']})")
    print(f"\n  taxonomy: {kinds}")
    print(f"  null-hallucination: {summary['null_hallucination']['rate']:.3f} "
          f"({nh}/{ns})")
    print(f"  OCR truncated: {summary['truncated_images'] or 'none'}")
    print(f"\n[out] {OUT}/summary.json  comparison.csv")


if __name__ == "__main__":
    main()
