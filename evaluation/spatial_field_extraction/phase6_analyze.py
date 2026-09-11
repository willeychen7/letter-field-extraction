"""
Phase 6 -- ANALYSIS ONLY. Why does Phase-4 domain classification go wrong
at low confidence? No pipeline change. Nothing frozen is modified.

For every image: full per-domain score, and for each domain scoring > 0
which exact phrases fired in issuer / subject / layout. Then group by
boundary type and look for the competition mechanism.
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))

import domain as D
import structure as ST
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements

HERE = os.path.dirname(__file__)


def load(key):
    for b in ("full20", "holdout"):
        p = os.path.join(HERE, "results", b, "raw", key + ".ocr.json")
        if os.path.exists(p):
            els = parse_ocr_elements(json.load(open(p))["content"])
            return els, ("dev" if b == "full20" else "hold")
    return None, None


def fired(text_low, families):
    out = []
    for gi, group in enumerate(families):
        hits = [p for p in group if p in text_low]
        if hits:
            out.append((gi, hits))
    return out


def full_evidence(els):
    low = "  " + " ".join(e["text"] for e in els).lower() + "  "
    lh = ST.classify_sender(els)
    head = ("  " + (lh[0]["value"] if lh else "") + "  ").lower()
    rows = {}
    for dom in D.DOMAINS:
        if dom == "OTHER":
            continue
        iss = fired(head, D.ISSUER.get(dom, [])) or fired(low, D.ISSUER.get(dom, []))
        sub = fired(low, D.SUBJECT.get(dom, []))
        lay = fired(low, D.LAYOUT.get(dom, []))
        rows[dom] = {"issuer": iss, "subject": sub, "layout": lay}
    dc = D.classify_domain(" ".join(e["text"] for e in els),
                           lh[0]["value"] if lh else "")
    return rows, dc, (lh[0]["value"] if lh else "")


def main():
    boundaries = {
        "HEALTHCARE<->INSURANCE": {"HEALTHCARE", "INSURANCE"},
        "HEALTHCARE<->GOVERNMENT": {"HEALTHCARE", "GOVERNMENT"},
        "BANKING_FINANCE<->OTHER": {"BANKING_FINANCE", "OTHER"},
        "INSURANCE<->HOUSING_PROPERTY": {"INSURANCE", "HOUSING_PROPERTY"},
    }
    per_boundary = defaultdict(list)
    sparse = []
    all_rows = []

    for key, (gold, note) in GT_DOMAIN.items():
        els, split = load(key)
        if els is None:
            continue
        ev, dc, head = full_evidence(els)
        pred, gap = dc["pred"], dc["gap"]
        scores = dc["scores"]
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top2 = {ranked[0][0], ranked[1][0]}
        n_el = len(els)
        rec = {"key": key, "split": split, "gold": gold, "pred": pred,
               "gap": gap, "n_el": n_el, "scores": scores, "head": head,
               "ev": ev, "correct": pred == gold, "top2": list(top2)}
        all_rows.append(rec)

        if n_el < 25 and (pred == "OTHER" or not rec["correct"]):
            sparse.append(rec)
        for bname, bset in boundaries.items():
            # the two competitors are within this boundary and it's close
            if {ranked[0][0], ranked[1][0]} == bset and gap < 2.0:
                per_boundary[bname].append(rec)
            elif not rec["correct"] and {gold, pred} == bset:
                per_boundary[bname].append(rec)

    def show(rec):
        print(f"\n  [{rec['split']}] {rec['key']}  gold={rec['gold']} pred={rec['pred']} "
              f"gap={rec['gap']} n_el={rec['n_el']}  head={rec['head']!r}")
        for dom, sc in sorted(rec["scores"].items(), key=lambda kv: -kv[1]):
            if sc <= 0:
                continue
            e = rec["ev"][dom]
            bits = []
            if e["issuer"]:
                bits.append("ISS=" + ",".join(h for _, hs in e["issuer"] for h in hs[:2]))
            if e["subject"]:
                bits.append(f"SUB[{len(e['subject'])}g]=" +
                            ",".join(h for _, hs in e["subject"] for h in hs[:2]))
            if e["layout"]:
                bits.append("LAY=" + ",".join(h for _, hs in e["layout"] for h in hs[:2]))
            print(f"     {dom:20s} {sc:>5.2f}  " + "  ".join(bits))

    print("=" * 70)
    print("BOUNDARY CASES (competitors within the named boundary, gap < 2)")
    print("=" * 70)
    for bname, recs in per_boundary.items():
        print(f"\n### {bname}   ({len(recs)} cases)")
        for r in recs:
            show(r)

    print("\n" + "=" * 70)
    print(f"SPARSE-OCR -> OTHER  ({len(sparse)} cases, n_el < 25)")
    print("=" * 70)
    for r in sparse:
        show(r)

    # high-confidence baseline: what clean evidence looks like
    conf = [r for r in all_rows if r["gap"] >= 3 and r["correct"]]
    print("\n" + "=" * 70)
    print(f"HIGH-CONFIDENCE CORRECT ({len(conf)}) -- evidence-group profile")
    print("=" * 70)
    prof = Counter()
    for r in conf:
        e = r["ev"][r["pred"]]
        prof[(bool(e["issuer"]), len(e["subject"]), bool(e["layout"]))] += 1
    for k, c in prof.most_common():
        print(f"  issuer={k[0]}  subject_groups={k[1]}  layout={k[2]}   x{c}")

    json.dump({"all_rows": all_rows}, open(os.path.join(HERE, "results", "domain",
              "phase6_evidence.json"), "w"), ensure_ascii=False, indent=2)
    print(f"\n[out] results/domain/phase6_evidence.json")


if __name__ == "__main__":
    main()
