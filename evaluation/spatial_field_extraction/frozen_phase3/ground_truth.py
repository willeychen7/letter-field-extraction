"""
Ground truth for the 6-image / 6-field stage-1 spatial-extraction eval.

Authority chain (per Mama Helper CLAUDE.md):
  - sender / total_amount / due_date / payment_status derive from
    mama-helper/frontend/src/utils/ground_truth.json (amount_shown,
    due_date, sender, payment_action).
  - recipient / action are not in that file; values below are read
    directly from each document's OCR text and the notes already recorded
    in ground_truth.json. Ambiguous cases carry an `accept` set so the
    scorer is not hostage to one phrasing.

payment_action -> payment_status mapping:
  "pay"  -> "unpaid"      (an amount is owed, nothing marks it paid)
  "none" -> "not_applicable"  (informational; e.g. "THIS IS NOT A BILL")
"""

# value: canonical answer.  accept: extra strings/None that also score correct.
GT = {
    "SCE_Bill_Letter": {
        "sender":        {"value": "SCE", "accept": ["southern california edison", "edison"]},
        # page-5 detail sheet: the addressee is reduced to a bare name + page
        # stamp ("BAKER, NATE / Page 5 of 5") top-right, not a normal address
        # block. null ("can't confidently locate") is an acceptable answer.
        "recipient":     {"value": "BAKER, NATE", "accept": ["nate baker", None]},
        "total_amount":  {"value": "99.36"},
        "payment_status":{"value": "unpaid"},
        "due_date":      {"value": None},
        "action":        {"value": "pay", "accept": [None]},  # detail page, no coupon
    },
    "Hospital_Bill": {
        "sender":        {"value": "Allina Health", "accept": ["allina"]},
        "recipient":     {"value": "JANE DOE"},
        "total_amount":  {"value": "419.07"},
        "payment_status":{"value": "unpaid"},
        "due_date":      {"value": "2013-04-18"},
        "action":        {"value": "pay"},
    },
    "Medical_Invoice": {
        "sender":        {"value": None, "accept": ["zylker heathcare", "zylker healthcare"]},
        "recipient":     {"value": "Aaron Brown"},
        "total_amount":  {"value": "14595.00", "accept": ["14595", "14595.0"]},
        "payment_status":{"value": "unpaid"},
        "due_date":      {"value": "2024-09-05"},
        "action":        {"value": "pay"},
    },
    "BOA_Bill_Example": {
        "sender":        {"value": "Bank of America", "accept": ["bankamericard", "bank of america"]},
        "recipient":     {"value": None},  # customer name not in the cropped image
        "total_amount":  {"value": "4543.36", "accept": ["112.00"]},  # New Balance Total (or min due)
        "payment_status":{"value": "unpaid"},
        "due_date":      {"value": "2018-02-05"},
        "action":        {"value": "pay"},
    },
    "Medicare_Notice_PartA": {
        "sender":        {"value": "Medicare", "accept": ["centers for medicare", "cms", "medicaid"]},
        "recipient":     {"value": "JENNIFER WASHINGTON"},
        "total_amount":  {"value": None},  # $2,062.50 printed but not owed; THIS IS NOT A BILL
        "payment_status":{"value": "not_applicable"},
        "due_date":      {"value": None},
        "action":        {"value": "review", "accept": [None]},
    },
    "IRS_cp503": {
        "sender":        {"value": "IRS", "accept": ["internal revenue service", "department of the treasury"]},
        "recipient":     {"value": "JAMES & KAREN Q. HINDS", "accept": ["james & karen q. hinds"]},
        "total_amount":  {"value": "9533.53"},
        "payment_status":{"value": "unpaid"},
        "due_date":      {"value": "2018-01-29"},
        "action":        {"value": "pay"},
    },
}

FIELDS = ["sender", "recipient", "total_amount", "payment_status", "due_date", "action"]

# sender/recipient alias groups for lenient identity matching
_ALIASES = [
    {"sce", "southern california edison", "edison"},
    {"irs", "internal revenue service", "department of the treasury",
     "department of treasury", "u.s. treasury"},
    {"medicare", "centers for medicare & medicaid services",
     "centers for medicare", "cms", "medicaid"},
    {"bank of america", "bankamericard", "bofa"},
    {"allina health", "allina"},
]


def _norm(s):
    if s is None:
        return None
    t = str(s).strip().lower().replace(",", " ")
    # normalise curly quotes / dashes so "O’Rourke" == "O'Rourke"
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("–", "-"), ("—", "-")):
        t = t.replace(a, b)
    return " ".join(t.split())


def _money_eq(a, b):
    try:
        return abs(float(str(a).replace("$", "").replace(",", "")) -
                   float(str(b).replace("$", "").replace(",", ""))) < 0.01
    except (ValueError, TypeError):
        return False


def _identity_match(pred, gold):
    p, g = _norm(pred), _norm(gold)
    if p is None or g is None:
        return p == g
    if p == g or p in g or g in p:
        return True
    for grp in _ALIASES:
        if any(x in p or p in x for x in grp) and any(x in g or g in x for x in grp):
            return True
    return False


def score_field(field, pred, entry):
    """Return (correct: bool, kind: str). kind in
    correct / wrong / null_hallucination / null_miss / both_null."""
    gold = entry["value"]
    accept = entry.get("accept", [])

    # null bookkeeping
    if gold is None and pred is None:
        return True, "both_null"
    if gold is None and pred is not None:
        # an 'accept' list may still legitimise a non-null answer
        if any(pred is not None and _norm(pred) == _norm(a) for a in accept) or \
           any(a is not None and _identity_match(pred, a) for a in accept if a is not None) or \
           (field == "total_amount" and any(a is not None and _money_eq(pred, a) for a in accept)):
            return True, "correct"
        return False, "null_hallucination"
    if gold is not None and pred is None:
        if None in accept:
            return True, "both_null"
        return False, "null_miss"

    # both non-null: field-specific comparison
    candidates = [gold] + [a for a in accept if a is not None]
    if field in ("sender", "recipient"):
        ok = any(_identity_match(pred, c) for c in candidates)
    elif field == "total_amount":
        ok = any(_money_eq(pred, c) for c in candidates)
    elif field == "due_date":
        ok = any(_norm(pred) == _norm(c) for c in candidates)
    else:  # payment_status, action -- categorical
        ok = any(_norm(pred) == _norm(c) for c in candidates)
    return ok, ("correct" if ok else "wrong")
