"""
Phase 8 experiment -- pick the ONE contact phone relevant to the frozen
Action, from the phones phone_extract.py found. Deterministic. Never
invents a number. Returns null when no phone scores clearly.

Signal used: the frozen action + domain, the phone's channel label
(billing / customer_service / ...), its page band, whether it repeats
across bands (header + payment coupon = the canonical contact line),
and its org context. No semantic similarity.
"""

# action -> preferred channel kinds, with weights
_ACTION_PREF = {
    "pay":     {"billing": 3, "customer_service": 2, "general": 1, "enroll": 1},
    "call":    {"customer_service": 3, "billing": 2, "general": 1},
    "contact": {"customer_service": 3, "billing": 2, "general": 1},
    "respond": {"customer_service": 3, "general": 1},
    "renew":   {"customer_service": 2, "enroll": 2, "general": 2, "billing": 1},
    "review":  {"customer_service": 2, "general": 1, "claims": 1},
}
# no action -> a contact is optional; only surface a clearly-labelled one
_NOACTION_PREF = {"customer_service": 2, "billing": 1}

_MIN_SCORE = 3.0


def pick_contact(phones, action, domain, sender):
    usable = [p for p in phones
              if not p["is_fax"] and not p["is_tty"] and not p["is_placeholder"]
              and not str(p["norm"]).startswith("VANITY:1")  # street-number junk
              ]
    if not usable:
        return {"phone_number": None, "contact_type": None,
                "contact_organization": None, "score": 0.0,
                "reason": "no usable phone element"}

    pref = _ACTION_PREF.get(action) if action else _NOACTION_PREF
    if pref is None:
        pref = _NOACTION_PREF

    # count how many distinct bands each normalised number appears in
    band_span = {}
    for p in usable:
        band_span.setdefault(p["norm"], set()).add(p["band"])

    scored = []
    for p in usable:
        s = 0.0
        why = []
        k = p["kind"]
        if k in pref:
            s += pref[k]
            why.append(f"kind={k}(+{pref[k]})")
        elif k == "unlabeled":
            s += 0.3
        # a Medicare/IRS-style national help line
        if str(p["norm"]).startswith("VANITY:") or p["norm"] in (
                "8006334227", "8008291040"):
            s += 0.5
        if p["band"] == "header":
            s += 1.0
            why.append("header(+1)")
        if p["band"] == "footer_coupon":
            s += 1.0
            why.append("coupon(+1)")
        if len(band_span.get(p["norm"], ())) >= 2:
            s += 1.0
            why.append("repeats across bands(+1)")
        lbl = (p["label_left"] + " " + p["label_above"]).lower()
        if action == "pay" and ("pay by phone" in lbl or "phone payment" in lbl):
            s += 1.5
            why.append("'pay by phone'(+1.5)")
        oc = (p["org_context"] or "").lower()
        if sender and sender.split()[0].lower() in oc:
            s += 0.5
            why.append("org matches sender(+0.5)")
        scored.append((s, p, why))

    # collapse to the best score per distinct number before ranking
    best_by_num = {}
    for s, p, why in scored:
        if p["norm"] not in best_by_num or s > best_by_num[p["norm"]][0]:
            best_by_num[p["norm"]] = (s, p, why)
    ranked = sorted(best_by_num.values(), key=lambda x: x[0], reverse=True)
    top_s, top_p, top_why = ranked[0]

    # lone-phone rule: exactly ONE distinct usable number that carries a
    # SPECIFIC channel label (billing / customer_service / claims / enroll)
    # -> a lower floor, because there is nothing to be ambiguous with.
    # Deliberately NOT applied to bare 'general' (weak "call/phone" context
    # only): a lone unlabelled number is often a redirect to another agency
    # (e.g. "Contact CARB at ..." on a DMV notice) -> stay null.
    floor = _MIN_SCORE
    if len(ranked) == 1 and top_p["kind"] in (
            "billing", "customer_service", "claims", "enroll"):
        floor = 2.0
        top_why.append("lone specifically-labelled phone (floor 2.0)")

    if top_s < floor:
        return {"phone_number": None, "contact_type": None,
                "contact_organization": None, "score": round(top_s, 2),
                "reason": f"best phone scored {top_s:.1f} < {floor}"}
    # genuine ambiguity: two DIFFERENT numbers, close scores, different channels
    if len(ranked) > 1 and abs(ranked[0][0] - ranked[1][0]) < 0.5 \
            and ranked[0][1]["kind"] != ranked[1][1]["kind"]:
        return {"phone_number": None, "contact_type": None,
                "contact_organization": None, "score": round(top_s, 2),
                "reason": "top two phones tie with different channels"}

    return {
        "phone_number": top_p["norm"],
        "contact_type": top_p["kind"],
        "contact_organization": top_p["org_context"] or sender,
        "score": round(top_s, 2),
        "reason": "; ".join(top_why),
    }
