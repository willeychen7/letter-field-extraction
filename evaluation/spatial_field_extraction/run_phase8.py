"""
Phase 8 controlled experiment: does contact_pick.py select the phone the
action actually needs?

GT below = hand-annotated from each doc's OCR text: the correct phone
(digits) for the frozen action, or None when the doc has no usable
contact for that action. Phases 3-7 frozen.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import field_semantics as FS
from contact_pick import pick_contact
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements
from phone_extract import extract_phones

HERE = os.path.dirname(__file__)

# correct contact phone for the current action (digits) | None
# "n/a" = no action / informational, not scored for contact recall
GT_CONTACT = {
    "Hospital_Bill":            ("6122629000", "billing"),
    "SCE_Sample_Bill":          ("8009907788", "billing"),
    "BOA_Bill_Example":         ("8006377455", "customer_service"),
    "water_bill":               ("8555940615", "billing"),        # 'Pay by Phone'
    "HOA1":                     ("2256781505", "billing"),
    "HOA4":                     ("8667295327", "billing"),
    "IRS_CP504_Notice":         ("8008291040", "customer_service"),
    "Great_American_Insurance_Invoice": ("8008474357", "billing"),
    "hoag-invoice-mychart":     ("9497648404", "billing"),        # PFS line
    "State_Farm_Insurance":     ("8504787748", "general"),        # agent
    "statefarm_bill":           ("4695864244", "general"),        # agent
    "DMV_registration_late_fee":("8009211117", "general"),
    "UCLA_Health_Bill":         ("3108258021", "customer_service"),
    "UCLA_Health_Bill2":        ("3108258021", "customer_service"),
    "aaa-policy_renew":         ("8002228252", "general"),
    "CMS_EOB":                  ("8001234567", "customer_service"),
    "Medicare_Notice_PartA":    ("8006334227", "general"),
    "Medicare_Notice_PartB":    ("8006334227", "general"),
    # action present, but NO usable contact phone in the OCR -> correct = null
    "DMV_Registration":         (None, None),   # 'Contact CARB' = smog board, not renewal
    "Medixare_Premium_Bill":    (None, None),   # only TTY + Social Security
    "Bank_Bill_Example":        (None, None),   # only a garbled street token
}
# everything else: no action / statement / card -> contact not required (n/a)


def load(k):
    for b in ("full20", "holdout"):
        p = os.path.join(HERE, "results", b, "raw", k + ".ocr.json")
        if os.path.exists(p):
            return parse_ocr_elements(json.load(open(p))["content"])


def main():
    rows = []
    scored = Counter()
    for k in GT_DOMAIN:
        els = load(k)
        if els is None:
            continue
        fs = FS.resolve(els)
        act, dom, sender = fs["action"]["value"], fs["_domain"], fs["sender"]["value"]
        phones = extract_phones(els)
        got = pick_contact(phones, act, dom, sender)

        gt = GT_CONTACT.get(k)
        verdict = "n/a"
        if gt is not None:
            gnum, gkind = gt
            pnum = got["phone_number"]
            if gnum is None:
                verdict = "correct_null" if pnum is None else "false_positive"
            elif pnum is None:
                verdict = "missed"
            elif pnum == gnum:
                verdict = "correct"
            else:
                verdict = "wrong_number"
            scored[verdict] += 1
        rows.append({"key": k, "domain": dom, "action": act,
                     "n_phones": len(phones), "gt": gt,
                     "pick": got, "verdict": verdict})

    graded = [r for r in rows if r["verdict"] != "n/a"]
    correct = scored["correct"] + scored["correct_null"]
    print(f"=== Phase 8 contact-phone picker  ({len(graded)} graded docs) ===\n")
    print(f"  correct (right number) : {scored['correct']}")
    print(f"  correct (right null)   : {scored['correct_null']}")
    print(f"  missed (said null)     : {scored['missed']}")
    print(f"  wrong number           : {scored['wrong_number']}")
    print(f"  false positive         : {scored['false_positive']}")
    print(f"  --> accuracy           : {correct}/{len(graded)} = {correct/len(graded):.2f}")
    non_null_gt = [r for r in graded if r["gt"][0] is not None]
    hit = sum(1 for r in non_null_gt if r["verdict"] == "correct")
    print(f"  recall on docs that HAVE a correct phone: {hit}/{len(non_null_gt)}")

    print("\n--- graded docs ---")
    for r in sorted(graded, key=lambda x: x["verdict"]):
        g = r["gt"]
        print(f"  [{r['verdict']:14s}] {r['key']:28s} act={r['action']!r:8s} "
              f"gt={g[0]!r:12s} pick={r['pick']['phone_number']!r:12s} "
              f"type={r['pick']['contact_type']!r:18s} score={r['pick']['score']}")
        if r["verdict"] not in ("correct", "correct_null"):
            print(f"                   reason: {r['pick']['reason']}")

    json.dump(rows, open(os.path.join(HERE, "results", "phase8_picker.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[out] results/phase8_picker.json")


if __name__ == "__main__":
    main()
