"""
Phase 5 -- Domain-aware field INTERPRETATION (minimal experiment).

Rule of the experiment: domain is a SEMANTIC CONSTRAINT, never the answer.
It can only *remove / demote* a candidate the frozen Phase-3 extractor
already produced (with its own text+bbox+structure evidence), or gate a
field to null / not_applicable. It never invents a value, never picks a
candidate the frozen layer didn't score, never re-runs OCR.

Frozen and untouched:
  - Phase 3 pipeline  (extract.py / structure.py / anchors.py / ocr.py)
  - Phase 4 classifier (domain.py)

Domain-aware layer touches only: total_amount, payment_status, action.
sender / recipient / due_date are passed through from frozen Phase 3
unchanged (domain carries no reliable signal for them).
"""

import extract as X            # frozen
import spatial as S            # frozen
import structure as ST         # frozen
from domain import classify_domain  # frozen

# ---- per-domain amount vocabulary ---------------------------------------
# FORBID: a money token whose own line contains one of these is NOT the
#         amount the recipient owes, in this domain.
# REQUIRE: unless one of these appears somewhere in the document, this
#          domain has no "amount due" at all -> total_amount = null.

_AMT_FORBID = {
    "BANKING_FINANCE": [
        "ending balance", "beginning balance", "opening balance",
        "closing balance", "available balance", "balance forward",
        "previous balance", "balance on ", "total credit", "credit line",
        "credit available", "available credit", "cash access line",
        "credit access line",
    ],
    "HEALTHCARE": [
        "total charges", "total current charges", "provider charges",
        "insurance paid", "insurance payment", "insurance adjustment",
        "insurance pending", "amount approved", "allowed charges",
        "patient payments", "adjustments", "charges/payments",
        "total claim cost", "provider can charge",
    ],
    "INSURANCE": [
        "premium", "coverage", "deductible", "limits", "bodily injury",
        "property damage", "six month premium", "policy premium", "fees",
        "annual dues", "each person", "each occurrence", "collision",
        "comprehensive",
    ],
    "GOVERNMENT": [
        "registration fee", "license fee", "weight fee", "special plate fee",
        "smog", "county / district", "owner responsibility fee",
        "prior balance",
    ],
    "UTILITIES_SERVICES": [
        "previous balance", "budget", "payments received", "payments and other",
    ],
}

_AMT_REQUIRE = {
    "BANKING_FINANCE": [
        "amount due", "minimum payment due", "payment due", "current payment due",
        "new balance total", "total amount due", "please pay this amount",
        "minimum amount due", "total minimum payment",
    ],
    "HEALTHCARE": [
        "amount you owe", "amount due", "patient responsibility",
        "your responsibility", "balance due", "what you owe",
        "due from patient", "patient balance", "please pay this amount",
        "responsibility to pay", "pay this amount",
    ],
    "INSURANCE": [
        "amount due", "premium due", "minimum due", "total amount owed",
        "please pay this amount", "balance due", "minimum amount due",
        "amount you owe", "pay this amount", "amount owed",
    ],
    "GOVERNMENT": [
        "amount due", "amount due immediately", "amount due by", "total due",
        "total due on or before", "balance due", "pay this amount",
        "restoration fee", "amount you owe",
    ],
    "UTILITIES_SERVICES": [
        "amount due", "total due", "total amount due", "current charges",
        "your new charges", "please pay this amount", "amount you owe",
        "current charge summary", "new balance", "balance due",
        "payment is due", "your payment is due", "total account",
        "current invoice", "amount enclosed", "pay this amount",
    ],
}

_NOT_A_BILL_STRUCT = (
    "this is not a bill", "explanation of benefits", "summary notice",
    "declarations page", "renewal declarations", "proof of insurance",
    "insurance card", "rates & charges", "rates and charges",
    "financial statement", "estimate id",
    "payment is not required", "no payment is required", "do not pay",
    "retain this for your records", "description of your coverage",
    "retain for your records",
)


def _joined(elements):
    return "  ".join(e["text"].lower() for e in elements)


def _row_label(elements, bbox):
    """Text of the elements on the same printed row, to the LEFT of a money
    token -- i.e. the label the frozen extractor paired the number with
    (its own candidate 'text' is just the digits). Pure geometry."""
    cand = {"bbox": bbox}
    parts = []
    for e in elements:
        if S.same_row(e, cand) and S.cx(e) < S.cx(cand) \
                and 0 <= S.horizontal_gap(e, cand) <= 560:
            parts.append((S.x1(e), e["text"]))
    parts.sort()
    return " ".join(t for _, t in parts).lower()


def _line_forbidden(text_low, domain):
    return any(f in text_low for f in _AMT_FORBID.get(domain, []))


def _doc_has_require(joined_low, domain):
    reqs = _AMT_REQUIRE.get(domain)
    if reqs is None:
        return True
    return any(r in joined_low for r in reqs)


def interpret_fields(elements):
    """Frozen Phase-3 result, then a domain-aware pass over amount /
    payment_status / action. Returns the same dict shape as
    X.extract_fields plus '_domain'."""
    base = X.extract_fields(elements)
    joined = _joined(elements)
    lh = ST.classify_sender(elements)
    head = lh[0]["value"] if lh else ""
    dc = classify_domain(joined, head)
    dom, dom_gap = dc["pred"], dc["gap"]

    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    out["_domain"] = dom
    notes = []

    # The domain constraint may override the frozen answer ONLY when the
    # domain is confidently known (Phase-4 score gap >= 1.5) -- or when it is
    # one of the two domains that classified perfectly and whose vocabulary is
    # unambiguous (BANKING_FINANCE / UTILITIES_SERVICES). Otherwise Phase 5
    # defers to frozen Phase 3 (a wrong domain must not corrupt a field).
    trust_domain = dom_gap >= 1.5 or dom in ("BANKING_FINANCE", "UTILITIES_SERVICES")

    # ---------- total_amount ----------
    if trust_domain and dom in _AMT_REQUIRE:
        cands = X.extract_amount(elements)                       # frozen candidates
        # a candidate is dropped if EITHER its own token OR the label printed
        # on its row is domain-forbidden ('Ending Balance', 'Total Charges',
        # 'Six Month Premium', ...)
        kept = []
        for c in cands:
            ctx = (c["text"] + " " + _row_label(elements, c["bbox"])).lower()
            if not _line_forbidden(ctx, dom):
                kept.append(c)
        has_req = _doc_has_require(joined, dom)
        struct_not_bill = any(m in joined for m in _NOT_A_BILL_STRUCT)

        new_val = None
        if has_req and kept and kept[0]["score"] >= X.TAU["total_amount"]:
            new_val = kept[0]["value"]

        # a statement / declarations / EOB / card / estimate is not a bill:
        # no 'amount due' anchor, or an explicit not-a-bill structure -> null
        if not has_req or struct_not_bill:
            new_val = None

        if new_val != base["total_amount"]["value"]:
            notes.append(f"amount: {base['total_amount']['value']} -> {new_val} "
                         f"(domain={dom}, has_amount_due_anchor={has_req})")
        out["total_amount"] = {"value": new_val,
                               "score": kept[0]["score"] if (new_val and kept) else 0.0,
                               "evidence": [("domain-filtered frozen candidates", 0)],
                               "runner_up": None}

    amt_val = out["total_amount"]["value"]
    amt_num = float(amt_val) if amt_val is not None else None

    # ---------- payment_status ----------
    struct_not_bill_doc = any(m in joined for m in _NOT_A_BILL_STRUCT)
    ps = X.decide_payment_status(elements, amt_num)              # frozen decision
    new_ps = ps["value"]
    if new_ps not in ("paid", "not_applicable"):
        # domain override: an account statement / declarations / card / EOB /
        # estimate with no amount-due anchor is informational, not an unpaid bill
        if struct_not_bill_doc and amt_num is None:
            new_ps = "not_applicable"
        elif trust_domain and dom in ("BANKING_FINANCE", "INSURANCE", "HEALTHCARE") \
                and amt_num is None and not _doc_has_require(joined, dom):
            new_ps = "not_applicable"
    if new_ps != base["payment_status"]["value"]:
        notes.append(f"payment_status: {base['payment_status']['value']} -> {new_ps} (domain={dom})")
    out["payment_status"] = {"value": new_ps, "score": 0.0,
                             "evidence": [("domain-aware", 0)], "runner_up": None}

    # ---------- action ----------
    act = base["action"]["value"]
    if act == "pay" and dom in ("INSURANCE", "GOVERNMENT"):
        renew_ctx = any(k in joined for k in ("renewal notice", "renew now",
                                              "to renew", "membership renewal",
                                              "renewal declarations",
                                              "registration renewal"))
        hard_due = any(k in joined for k in ("past due", "delinquent", "final notice",
                                             "amount due immediately", "levy"))
        if renew_ctx and not hard_due:
            act = "renew"
            notes.append(f"action: pay -> renew (domain={dom}, renewal context)")
    out["action"] = {"value": act, "score": base["action"]["score"],
                     "evidence": base["action"]["evidence"], "runner_up": None}

    out["_phase5_notes"] = notes
    return out
