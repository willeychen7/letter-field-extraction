"""
FROZEN Stage-1 pipeline on the full 20-image benchmark.

Freeze point: spatial.py / anchors.py / extract.py / ocr.py / ground_truth.py
are used exactly as committed after the 6-image calibration. This script adds
NO rules, NO keywords, NO threshold changes. It only:
  - runs the frozen OCR + extract over 20 images
  - records finish_reason / token usage / element count / truncation
  - scores against ground_truth_20.py
  - reports per-field accuracy, hallucination, null breakdown

No mama-helper / V5 write. No Qwen / Ollama / other model.

    python3 run_full20.py             # fresh OCR
    python3 run_full20.py --use-cache # reuse results/full20/raw/*.ocr.json
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import extract as X            # frozen  # noqa: E402
import ground_truth as GTM     # frozen scorer  # noqa: E402
from ground_truth_20 import GT20, GT_FIELDS, GT_CONFIDENCE  # noqa: E402
from ocr import call_ocr, parse_ocr_elements  # frozen  # noqa: E402

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "results", "full20")
RAW = os.path.join(OUT, "raw")
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"

# canonical 20-image benchmark (== spotting_eval DEFAULT_IMAGES)
IMAGES = [
    "SCE_Bill_Letter.png", "SCE_Letter.png", "SCE_Sample_Bill.png",
    "SoCalGas.png", "Water_Bill2.jpg", "BOA_Bill_Example.png",
    "Bank_Bill_Due.png", "AAA_insurance_Bill.png",
    "All_State_Insurance_Card.jpg", "Auto_Insurance_Bill1.jpg",
    "Great_American_Insurance_Invoice.png", "DMV_Registration.png",
    "DMV_Notice.jpeg", "Hospital_Bill.png", "Medical_Invoice.png",
    "CMS_EOB.png", "hoag-invoice-mychart.png", "IRS_CP504_Notice.png",
    "IRS_cp503.png", "Medicare_Notice_PartA.png",
]


def get_ocr(name, use_cache):
    stem = os.path.splitext(name)[0]
    cache = os.path.join(RAW, f"{stem}.ocr.json")
    if use_cache and os.path.exists(cache):
        return json.load(open(cache))
    resp = call_ocr(os.path.join(IMAGES_DIR, name))
    json.dump(resp, open(cache, "w"), ensure_ascii=False, indent=2)
    open(os.path.join(RAW, f"{stem}.ocr.txt"), "w").write(resp["content"])
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)

    preds, detail, ocr_meta = {}, {}, {}
    for name in IMAGES:
        stem = os.path.splitext(name)[0]
        resp = get_ocr(name, args.use_cache)
        els = parse_ocr_elements(resp["content"])
        fields = X.extract_fields(els)
        preds[stem] = {f: fields[f]["value"] for f in GT_FIELDS}
        detail[stem] = fields
        ocr_meta[stem] = {
            "finish_reason": resp["finish_reason"],
            "truncated": resp["finish_reason"] == "length",
            "elapsed_s": resp["elapsed_s"],
            "prompt_tokens": resp["usage"].get("prompt_tokens"),
            "completion_tokens": resp["usage"].get("completion_tokens"),
            "element_count": len(els),
        }
        json.dump({"image": name, "ocr": ocr_meta[stem], "elements": els,
                   "fields": fields, "final": preds[stem]},
                  open(os.path.join(RAW, f"{stem}.json"), "w"),
                  ensure_ascii=False, indent=2)
        tr = "  <<TRUNCATED>>" if ocr_meta[stem]["truncated"] else ""
        print(f"{stem:34s} {ocr_meta[stem]['element_count']:4d} els  "
              f"{resp['elapsed_s']:6.1f}s  finish={resp['finish_reason']}{tr}")

    # ---- scoring ----
    per_field = {f: {"correct": 0, "total": 0, "by_conf": {}} for f in GT_FIELDS}
    kinds = {}
    rows = []
    null_hall = null_slots = 0
    total_c = total = 0
    for stem in preds:
        gt = GT20[stem]
        conf = GT_CONFIDENCE[stem]
        for f in GT_FIELDS:
            entry = gt[f]
            pred = preds[stem][f]
            ok, kind = GTM.score_field(f, pred, entry)
            pf = per_field[f]
            pf["total"] += 1
            pf["correct"] += int(ok)
            pf["by_conf"].setdefault(conf, [0, 0])
            pf["by_conf"][conf][0] += int(ok)
            pf["by_conf"][conf][1] += 1
            kinds[kind] = kinds.get(kind, 0) + 1
            total += 1
            total_c += int(ok)
            if entry["value"] is None and None not in entry.get("accept", []):
                null_slots += 1
                if kind == "null_hallucination":
                    null_hall += 1
            rows.append({"image": stem, "field": f, "pred": pred,
                         "gold": entry["value"], "accept": entry.get("accept", []),
                         "correct": ok, "kind": kind, "gt_confidence": conf})

    # subset: images whose GT is authoritative (mama-helper ground_truth.json)
    auth = [s for s in preds if GT_CONFIDENCE[s] == "authoritative"]
    auth_fields = ["sender", "total_amount", "due_date", "payment_status"]
    auth_c = auth_t = 0
    for r in rows:
        if r["image"] in auth and r["field"] in auth_fields:
            auth_t += 1
            auth_c += int(r["correct"])

    summary = {
        "n_images": len(IMAGES),
        "frozen": True,
        "overall_accuracy_all": round(total_c / total, 4),
        "overall_correct": total_c, "overall_total": total,
        "authoritative_subset": {
            "images": auth, "fields": auth_fields,
            "accuracy": round(auth_c / auth_t, 4), "correct": auth_c, "total": auth_t,
        },
        "per_field": {
            f: {
                "accuracy": round(v["correct"] / v["total"], 4),
                "correct": v["correct"], "total": v["total"],
                "by_gt_confidence": {c: {"acc": round(a / n, 3), "n": n}
                                     for c, (a, n) in v["by_conf"].items()},
            } for f, v in per_field.items()
        },
        "answer_taxonomy": kinds,
        "null_hallucination": {"count": null_hall, "null_slots": null_slots,
                               "rate": round(null_hall / null_slots, 4) if null_slots else 0.0},
        "ocr": ocr_meta,
        "truncated_images": [s for s, m in ocr_meta.items() if m["truncated"]],
        "rows": rows,
        "predictions": preds,
    }
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"),
              ensure_ascii=False, indent=2)

    with open(os.path.join(OUT, "comparison.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "accuracy_all20", "correct", "total"])
        for f in GT_FIELDS:
            v = summary["per_field"][f]
            w.writerow([f, f"{v['accuracy']:.3f}", v["correct"], v["total"]])
        w.writerow(["OVERALL_all20", f"{summary['overall_accuracy_all']:.3f}",
                    total_c, total])
        a = summary["authoritative_subset"]
        w.writerow([f"OVERALL_authoritative_subset ({len(auth)} imgs x 4 fields)",
                    f"{a['accuracy']:.3f}", a["correct"], a["total"]])

    # console
    print("\n== PER-FIELD (all 20) ==")
    for f in GT_FIELDS:
        v = summary["per_field"][f]
        bc = "  ".join(f"{c}:{d['acc']:.2f}(n={d['n']})"
                       for c, d in v["by_gt_confidence"].items())
        print(f"  {f:15s} {v['accuracy']:.3f}  ({v['correct']}/{v['total']})   {bc}")
    print(f"  {'OVERALL':15s} {summary['overall_accuracy_all']:.3f}  "
          f"({total_c}/{total})")
    a = summary["authoritative_subset"]
    print(f"\n  authoritative-GT subset: {a['accuracy']:.3f} ({a['correct']}/{a['total']})"
          f"  [{len(auth)} imgs x sender/amount/due/payment]")
    print(f"\n  answer taxonomy: {kinds}")
    print(f"  null-hallucination rate: {summary['null_hallucination']['rate']:.3f} "
          f"({null_hall}/{null_slots} GT-null slots)")
    print(f"  OCR truncated (finish=length): {summary['truncated_images'] or 'none'}")
    print(f"\n[out] {OUT}/summary.json  comparison.csv  raw/*.json")


if __name__ == "__main__":
    main()
