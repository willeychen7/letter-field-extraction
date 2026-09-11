"""
Phase 5 comparison: Frozen Phase 3 (baseline)  vs  Domain-aware Phase 5.

Runs both over the SAME 50 images (20 dev + 30 holdout) from cached OCR.
Nothing in the frozen pipeline or the Phase-4 classifier changes.
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import extract as X                       # frozen
import ground_truth as GTM                # frozen scorer
import phase5 as P5                       # domain-aware layer
from ground_truth_20 import GT20
from ground_truth_holdout import GT_HOLD
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements
from run_full20 import IMAGES as DEV_IMAGES
from holdout_set import HOLDOUT

HERE = os.path.dirname(__file__)
FIELDS = ["sender", "recipient", "total_amount", "payment_status", "due_date", "action"]
OUT = os.path.join(HERE, "results", "phase5")


def _load(key):
    for base in ("full20", "holdout"):
        p = os.path.join(HERE, "results", base, "raw", key + ".ocr.json")
        if os.path.exists(p):
            return parse_ocr_elements(json.load(open(p))["content"])
    return None


def _score(preds, gts):
    per_field = {f: [0, 0] for f in FIELDS}
    kinds = Counter()
    nh = ns = tot_c = tot = 0
    rows = []
    for key, gt in gts.items():
        for f in FIELDS:
            entry = gt[f]
            pred = preds[key][f]
            ok, kind = GTM.score_field(f, pred, entry)
            per_field[f][0] += int(ok); per_field[f][1] += 1
            kinds[kind] += 1
            tot += 1; tot_c += int(ok)
            if entry["value"] is None and None not in entry.get("accept", []):
                ns += 1
                if kind == "null_hallucination":
                    nh += 1
            rows.append({"key": key, "field": f, "pred": pred, "gold": entry["value"],
                         "correct": ok, "kind": kind})
    return {
        "overall": round(tot_c / tot, 4), "correct": tot_c, "total": tot,
        "per_field": {f: round(v[0] / v[1], 4) for f, v in per_field.items()},
        "per_field_raw": {f: v for f, v in per_field.items()},
        "kinds": dict(kinds),
        "hallucination_rate": round(nh / ns, 4) if ns else 0.0,
        "hallucination_events": sum(1 for r in rows if r["kind"] == "null_hallucination"),
        "rows": rows,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    keys = [os.path.splitext(n)[0] for n in DEV_IMAGES] + [k for k, *_ in HOLDOUT]
    gts = {**GT20, **GT_HOLD}

    base_preds, p5_preds, domains = {}, {}, {}
    for key in keys:
        els = _load(key)
        if els is None:
            print("MISS", key); continue
        b = X.extract_fields(els)
        p = P5.interpret_fields(els)
        base_preds[key] = {f: b[f]["value"] for f in FIELDS}
        p5_preds[key] = {f: p[f]["value"] for f in FIELDS}
        domains[key] = p["_domain"]

    base = _score(base_preds, gts)
    p5 = _score(p5_preds, gts)

    # split views
    dev_keys = set(os.path.splitext(n)[0] for n in DEV_IMAGES)
    def split_overall(preds, want_dev):
        sub = {k: v for k, v in gts.items() if (k in dev_keys) == want_dev}
        return _score({k: preds[k] for k in sub}, sub)["overall"]

    summary = {
        "n_images": len(keys),
        "baseline_overall": base["overall"],
        "phase5_overall": p5["overall"],
        "delta_overall": round(p5["overall"] - base["overall"], 4),
        "baseline": {k: base[k] for k in ("overall", "per_field", "kinds",
                                          "hallucination_rate", "hallucination_events")},
        "phase5": {k: p5[k] for k in ("overall", "per_field", "kinds",
                                      "hallucination_rate", "hallucination_events")},
        "split": {
            "dev": {"baseline": split_overall(base_preds, True),
                    "phase5": split_overall(p5_preds, True)},
            "holdout": {"baseline": split_overall(base_preds, False),
                        "phase5": split_overall(p5_preds, False)},
        },
        "changed_cells": [],
        "domains": domains,
    }
    b_by = {(r["key"], r["field"]): r for r in base["rows"]}
    p_by = {(r["key"], r["field"]): r for r in p5["rows"]}
    for k in b_by:
        if b_by[k]["pred"] != p_by[k]["pred"]:
            summary["changed_cells"].append({
                "key": k[0], "field": k[1], "domain": domains[k[0]],
                "base": b_by[k]["pred"], "base_ok": b_by[k]["correct"],
                "phase5": p_by[k]["pred"], "phase5_ok": p_by[k]["correct"],
            })
    json.dump({**summary, "baseline_rows": base["rows"], "phase5_rows": p5["rows"]},
              open(os.path.join(OUT, "summary.json"), "w"), ensure_ascii=False, indent=2)

    print(f"=== Frozen Phase 3  vs  Domain-aware Phase 5  ({len(keys)} images) ===\n")
    print(f"{'field':<16}{'baseline':>10}{'phase5':>10}{'delta':>9}")
    for f in FIELDS:
        b, p = base["per_field"][f], p5["per_field"][f]
        print(f"{f:<16}{b:>10.3f}{p:>10.3f}{p-b:>+9.3f}")
    print(f"{'OVERALL':<16}{base['overall']:>10.3f}{p5['overall']:>10.3f}"
          f"{p5['overall']-base['overall']:>+9.3f}")
    print(f"\n  dev:     {summary['split']['dev']['baseline']:.3f} -> {summary['split']['dev']['phase5']:.3f}")
    print(f"  holdout: {summary['split']['holdout']['baseline']:.3f} -> {summary['split']['holdout']['phase5']:.3f}")
    print(f"\n  hallucination events: {base['hallucination_events']} -> {p5['hallucination_events']}"
          f"   (rate {base['hallucination_rate']:.3f} -> {p5['hallucination_rate']:.3f})")
    print(f"  taxonomy base : {base['kinds']}")
    print(f"  taxonomy p5   : {p5['kinds']}")

    print(f"\n  changed cells ({len(summary['changed_cells'])}):")
    for c in summary["changed_cells"]:
        d = ("FIX " if (not c["base_ok"] and c["phase5_ok"]) else
             "BREAK" if (c["base_ok"] and not c["phase5_ok"]) else "even ")
        print(f"    {d} [{c['domain']:18s}] {c['key']:28s} {c['field']:14s} "
              f"{c['base']!r} -> {c['phase5']!r}")
    print(f"\n[out] {OUT}/summary.json")


if __name__ == "__main__":
    main()
