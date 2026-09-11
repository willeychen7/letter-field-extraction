"""
Phase 7 controlled experiment.

(1) FAITHFULNESS: the consolidated declarative layer (field_semantics.py)
    must reproduce frozen Phase 5 (phase5.py) cell-for-cell on the 50
    benchmark images for amount / payment_status / action. Any diff is a
    consolidation bug, printed.
(2) SCORING: field_semantics vs frozen Phase 3 baseline, same metrics as
    Phase 5, plus an error-analysis bucketing of every remaining wrong /
    hallucinated / null-miss cell.

Nothing frozen is modified.
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import extract as X
import field_semantics as FS
import ground_truth as GTM
import phase5 as P5
from domain import classify_domain
from ground_truth_20 import GT20
from ground_truth_holdout import GT_HOLD
from gt_domain import GT_DOMAIN
from holdout_set import HOLDOUT
from ocr import parse_ocr_elements
from run_full20 import IMAGES as DEV_IMAGES

HERE = os.path.dirname(__file__)
FIELDS = ["sender", "recipient", "total_amount", "payment_status", "due_date", "action"]
OWNED = ["total_amount", "payment_status", "action"]
OUT = os.path.join(HERE, "results", "phase7")


def load(k):
    for b in ("full20", "holdout"):
        p = os.path.join(HERE, "results", b, "raw", k + ".ocr.json")
        if os.path.exists(p):
            return parse_ocr_elements(json.load(open(p))["content"])


def main():
    os.makedirs(OUT, exist_ok=True)
    gts = {**GT20, **GT_HOLD}
    dev = {os.path.splitext(n)[0] for n in DEV_IMAGES}
    keys = [os.path.splitext(n)[0] for n in DEV_IMAGES] + [k for k, *_ in HOLDOUT]

    base_p, p5_p, fs_p, doms = {}, {}, {}, {}
    for k in keys:
        els = load(k)
        b = X.extract_fields(els)
        p5 = P5.interpret_fields(els)
        fs = FS.resolve(els)
        base_p[k] = {f: b[f]["value"] for f in FIELDS}
        p5_p[k] = {f: p5[f]["value"] for f in FIELDS}
        fs_p[k] = {f: fs[f]["value"] for f in FIELDS}
        doms[k] = (fs["_domain"], fs["_domain_gap"])

    # (1) faithfulness
    diffs = [(k, f, p5_p[k][f], fs_p[k][f]) for k in keys for f in FIELDS
             if p5_p[k][f] != fs_p[k][f]]
    print("=== (1) FAITHFULNESS: field_semantics vs frozen phase5 ===")
    if not diffs:
        print("    IDENTICAL on all 50 x 6 cells. Consolidation is faithful.\n")
    else:
        print(f"    {len(diffs)} differing cell(s):")
        for k, f, a, b in diffs:
            print(f"      {k:28s} {f:14s} phase5={a!r}  field_semantics={b!r}")
        print()

    # (2) scoring
    def score(pred):
        pf = {f: [0, 0] for f in FIELDS}
        kinds = Counter()
        rows = []
        for k in pred:
            gt = gts[k]
            for f in FIELDS:
                ok, kind = GTM.score_field(f, pred[k][f], gt[f])
                pf[f][0] += ok
                pf[f][1] += 1
                kinds[kind] += 1
                rows.append({"key": k, "field": f, "pred": pred[k][f],
                             "gold": gt[f]["value"], "ok": ok, "kind": kind})
        tot_c = sum(v[0] for v in pf.values())
        tot = sum(v[1] for v in pf.values())
        return {"overall": round(tot_c / tot, 4),
                "per_field": {f: round(v[0] / v[1], 4) for f, v in pf.items()},
                "kinds": dict(kinds), "rows": rows}

    base_s, fs_s = score(base_p), score(fs_p)
    sd = lambda pr, d: score({k: pr[k] for k in keys if (k in dev) == d})["overall"]

    print("=== (2) field_semantics  vs  frozen Phase 3 baseline ===\n")
    print(f"{'field':<16}{'baseline':>10}{'phase7':>10}{'delta':>9}")
    for f in FIELDS:
        b, p = base_s["per_field"][f], fs_s["per_field"][f]
        print(f"{f:<16}{b:>10.3f}{p:>10.3f}{p-b:>+9.3f}")
    print(f"{'OVERALL':<16}{base_s['overall']:>10.3f}{fs_s['overall']:>10.3f}"
          f"{fs_s['overall']-base_s['overall']:>+9.3f}")
    print(f"\n  dev:     {sd(base_p, True):.3f} -> {sd(fs_p, True):.3f}")
    print(f"  holdout: {sd(base_p, False):.3f} -> {sd(fs_p, False):.3f}")
    print(f"\n  baseline kinds: {base_s['kinds']}")
    print(f"  phase7 kinds  : {fs_s['kinds']}")

    # (3) error analysis of every non-correct phase7 cell on the owned fields
    print("\n=== (3) ERROR ANALYSIS -- remaining non-correct cells (owned fields) ===")
    buckets = Counter()
    detail = []
    for r in fs_s["rows"]:
        if r["ok"] or r["field"] not in OWNED:
            continue
        k, f = r["key"], r["field"]
        dom, gap = doms[k]
        gold_dom = GT_DOMAIN.get(k, ("?", ""))[0]
        base_ok = GTM.score_field(f, base_p[k][f], gts[k][f])[0]
        if dom != gold_dom:
            bucket = "upstream: Phase-4 domain wrong"
        elif gap < FS.CONF_MIN and dom not in FS.ALWAYS_TRUSTED:
            bucket = "upstream: domain low-confidence -> layer deferred"
        elif base_ok and not r["ok"]:
            bucket = "semantic layer regressed vs frozen"
        elif r["kind"] == "wrong" and base_p[k][f] == fs_p[k][f]:
            bucket = "upstream: Phase-3 candidate wrong, layer had nothing better"
        else:
            bucket = "semantic-layer gap (missing rule) or GT-debatable"
        buckets[bucket] += 1
        detail.append((bucket, k, f, r["pred"], r["gold"], dom, gap))

    for b, c in buckets.most_common():
        print(f"  {c:2d}  {b}")
    print()
    for b, k, f, pr, go, dm, gp in sorted(detail):
        print(f"   [{b[:34]:34s}] {k:26s} {f:13s} pred={pr!r} gold={go!r} "
              f"(domain={dm}/{gp})")

    json.dump({"faithful": not diffs, "diffs": diffs,
               "baseline": {k: base_s[k] for k in ("overall", "per_field", "kinds")},
               "phase7": {k: fs_s[k] for k in ("overall", "per_field", "kinds")},
               "split": {"dev": [sd(base_p, True), sd(fs_p, True)],
                         "holdout": [sd(base_p, False), sd(fs_p, False)]},
               "error_buckets": dict(buckets),
               "error_detail": detail,
               "domains": {k: list(v) for k, v in doms.items()}},
              open(os.path.join(OUT, "summary.json"), "w"), ensure_ascii=False, indent=2)
    print(f"\n[out] {OUT}/summary.json")


if __name__ == "__main__":
    main()
