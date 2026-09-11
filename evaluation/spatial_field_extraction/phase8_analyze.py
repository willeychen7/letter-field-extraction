"""
Phase 8 analysis pass -- statistics only, no picker yet.

  1. how many of the 50 docs contain a phone
  2. phone-count distribution
  3. fax / TTY / placeholder / toll-free / by kind
  4. do bbox band + nearby label give a usable channel signal
  5. does the frozen Phase-7 action line up with any phone's kind
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import field_semantics as FS          # frozen Phase 7 (for the action + domain)
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements
from phone_extract import extract_phones

HERE = os.path.dirname(__file__)


def load(k):
    for b in ("full20", "holdout"):
        p = os.path.join(HERE, "results", b, "raw", k + ".ocr.json")
        if os.path.exists(p):
            return parse_ocr_elements(json.load(open(p))["content"])


ACTION_TO_KINDS = {
    "pay": ["billing", "customer_service", "general"],
    "call": ["customer_service", "billing", "general"],
    "renew": ["customer_service", "enroll", "general"],
    "contact": ["customer_service", "general"],
    "respond": ["customer_service", "general"],
    "review": ["customer_service", "claims", "general"],
}


def main():
    rows = []
    kind_counts = Counter()
    band_counts = Counter()
    n_with_phone = 0
    per_doc_counts = []
    fax = tty = placeholder = toll = 0
    action_alignable = 0
    action_present = 0

    for k in GT_DOMAIN:
        els = load(k)
        if els is None:
            continue
        phones = extract_phones(els)
        fs = FS.resolve(els)
        act = fs["action"]["value"]
        dom = fs["_domain"]

        per_doc_counts.append(len(phones))
        if phones:
            n_with_phone += 1
        for p in phones:
            kind_counts[p["kind"]] += 1
            band_counts[p["band"]] += 1
            fax += p["is_fax"]
            tty += p["is_tty"]
            placeholder += p["is_placeholder"]
            toll += p["is_toll_free"]

        # can the action point at a phone?
        usable = [p for p in phones if not p["is_fax"] and not p["is_tty"]]
        aligned = []
        if act in ACTION_TO_KINDS:
            want = ACTION_TO_KINDS[act]
            aligned = [p for p in usable if p["kind"] in want]
        if act:
            action_present += 1
            if aligned:
                action_alignable += 1

        rows.append({
            "key": k, "domain": dom, "action": act,
            "n_phones": len(phones),
            "n_usable": len(usable),
            "kinds": [p["kind"] for p in phones],
            "aligned_kinds": [p["kind"] for p in aligned],
            "phones": [{kk: p[kk] for kk in ("raw", "norm", "kind", "band",
                                             "is_fax", "is_tty", "is_placeholder",
                                             "label_left", "label_above",
                                             "org_context")} for p in phones],
        })

    n = len(rows)
    print(f"=== Phase 8 phone analysis  ({n} docs) ===\n")
    print(f"1. docs containing >=1 phone : {n_with_phone}/{n} ({n_with_phone/n:.0%})")
    print(f"2. phones per doc            : "
          f"min={min(per_doc_counts)} max={max(per_doc_counts)} "
          f"mean={sum(per_doc_counts)/n:.1f}  distribution={dict(Counter(per_doc_counts))}")
    tot_ph = sum(per_doc_counts)
    print(f"   total phone elements      : {tot_ph}")
    print(f"3. fax={fax}  tty={tty}  placeholder={placeholder}  toll_free={toll}  "
          f"(of {tot_ph})")
    print(f"   by kind   : {dict(kind_counts.most_common())}")
    print(f"   by band   : {dict(band_counts)}")
    print(f"4. label/band channel signal : "
          f"{tot_ph - kind_counts['unlabeled']}/{tot_ph} phones got a channel label "
          f"({(tot_ph-kind_counts['unlabeled'])/tot_ph:.0%})")
    print(f"5. action present & a kind-aligned phone exists : "
          f"{action_alignable}/{action_present}")

    print("\n--- per doc ---")
    for r in sorted(rows, key=lambda x: (-x["n_phones"], x["key"])):
        print(f"\n {r['key']:28s} domain={r['domain']:16s} action={r['action']!r:8s} "
              f"phones={r['n_phones']} usable={r['n_usable']}")
        for p in r["phones"]:
            tags = []
            if p["is_fax"]:
                tags.append("FAX")
            if p["is_tty"]:
                tags.append("TTY")
            if p["is_placeholder"]:
                tags.append("PLACEHOLDER")
            print(f"     {p['norm']:14s} [{p['kind']:16s}] {p['band']:14s} "
                  f"{' '.join(tags):12s} label_left={p['label_left'][:34]!r} "
                  f"above={p['label_above'][:28]!r} org={p['org_context']!r}")

    json.dump(rows, open(os.path.join(HERE, "results", "phase8_analysis.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[out] results/phase8_analysis.json")


if __name__ == "__main__":
    main()
