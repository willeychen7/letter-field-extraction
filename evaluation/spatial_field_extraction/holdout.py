"""
Untuned generalization check.

The 6-image headline run in run.py had its thresholds + anchor lists
calibrated while looking at those same 6 images, so its accuracy is
optimistic. This script runs the SAME pipeline code, with NO further
changes, on 6 DIFFERENT real letters and scores the 4 fields for which
mama-helper/frontend/src/utils/ground_truth.json carries a value
(sender, total_amount, due_date, payment_status).

It is a robustness signal for the go/no-go decision, not the deliverable.

    python3 holdout.py            # fresh OCR
    python3 holdout.py --use-cache
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import extract as X          # noqa: E402
import ground_truth as GTM   # noqa: E402
from ocr import call_ocr, parse_ocr_elements  # noqa: E402

HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "results", "raw")
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
GT_PATH = "/Users/willeychen/Desktop/mama-helper/frontend/src/utils/ground_truth.json"

# (image file, ground_truth.json key)
HOLDOUT = [
    ("SCE_Sample_Bill.png", "SCE_Sample_Bill"),
    ("SoCalGas.png", "SoCalGas"),
    ("hoag-invoice-mychart.png", "hoag-invoice-mychart"),
    ("IRS_CP504_Notice.png", "IRS_CP504_Notice"),
    ("DMV_Registration.png", "DMV_Registration"),
    ("SCE_Letter.png", "SCE_Letter"),
]

PAY_MAP = {"pay": "unpaid", "none": "not_applicable", "autopay": "paid",
           "paid": "paid"}
FIELDS = ["sender", "total_amount", "due_date", "payment_status"]


def get_ocr(name, use_cache):
    stem = os.path.splitext(name)[0]
    cache = os.path.join(RAW, f"{stem}.holdout.ocr.json")
    if use_cache and os.path.exists(cache):
        return json.load(open(cache))
    resp = call_ocr(os.path.join(IMAGES_DIR, name))
    json.dump(resp, open(cache, "w"), ensure_ascii=False, indent=2)
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true")
    args = ap.parse_args()

    gt = json.load(open(GT_PATH))
    per_field = {f: [0, 0] for f in FIELDS}
    rows = []
    for name, key in HOLDOUT:
        resp = get_ocr(name, args.use_cache)
        els = parse_ocr_elements(resp["content"])
        fields = X.extract_fields(els)
        truth = gt[key]
        gold = {
            "sender": truth.get("sender"),
            "total_amount": truth.get("amount_shown", truth.get("amount_due")),
            "due_date": truth.get("due_date"),
            "payment_status": PAY_MAP.get(truth.get("payment_action")),
        }
        entrymap = {
            "sender": {"value": gold["sender"], "accept": []},
            "total_amount": {"value": None if gold["total_amount"] is None
                             else f'{float(gold["total_amount"]):.2f}', "accept": []},
            "due_date": {"value": gold["due_date"], "accept": []},
            "payment_status": {"value": gold["payment_status"], "accept": []},
        }
        r = {"image": name}
        for f in FIELDS:
            pred = fields[f]["value"]
            ok, kind = GTM.score_field(f, pred, entrymap[f])
            per_field[f][0] += int(ok)
            per_field[f][1] += 1
            r[f] = f"{'OK ' if ok else 'X  '}{pred!r} / gold {entrymap[f]['value']!r}"
        rows.append(r)
        print(f"=== {name}  ({len(els)} elements, ocr {resp['elapsed_s']}s, "
              f"finish={resp['finish_reason']})")
        for f in FIELDS:
            print(f"    {f:15s} {r[f]}")

    tot_ok = sum(v[0] for v in per_field.values())
    tot = sum(v[1] for v in per_field.values())
    print("\n== HOLDOUT (untuned) ==")
    for f in FIELDS:
        ok, n = per_field[f]
        print(f"  {f:15s} {ok}/{n}  ({ok / n:.2f})")
    print(f"  {'OVERALL':15s} {tot_ok}/{tot}  ({tot_ok / tot:.3f})")

    json.dump({"per_field": {f: {"correct": v[0], "total": v[1]}
                             for f, v in per_field.items()},
               "overall": {"correct": tot_ok, "total": tot,
                           "accuracy": round(tot_ok / tot, 4)},
               "rows": rows},
              open(os.path.join(HERE, "results", "holdout.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[out] {HERE}/results/holdout.json")


if __name__ == "__main__":
    main()
