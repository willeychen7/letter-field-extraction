"""
Phase 7 -- Domain-Aware Field Semantics (stable product layer).

This is Phase 5's validated behaviour, re-expressed as ONE declarative
table instead of scattered experimental code. It is a faithful
consolidation: run_phase7.py asserts it reproduces frozen phase5.py
cell-for-cell on the 50-image benchmark.

Pipeline position:
    OCR text+bbox
      -> Spatial Field Extraction (Phase 3, frozen)   -> candidates + scores
      -> Domain Classification    (Phase 4, frozen)    -> domain + confidence
      -> Domain-Aware Field Semantics (THIS layer)     -> value + status + reason
      -> Amount / Payment Status / Due Date / Action

Contract of this layer:
  * INPUT : frozen Phase-3 field result, the OCR elements, the Phase-4
            domain + its score gap.
  * OUTPUT: per field {value, status, reason}
            status in {"resolved", "not_applicable", "insufficient_evidence"}
  * GUARANTEES:
      - never invents a value; only keeps / drops candidates Phase 3 scored
      - never overrides a frozen answer unless the domain is trusted
        (gap >= CONF_MIN, or a domain whose vocabulary is unambiguous)
      - sender / recipient / due_date are passed through frozen untouched
        (domain carries no reliable signal for them -- Phase 5 finding)
"""

import extract as X            # frozen Phase 3
import spatial as S            # frozen
import structure as ST         # frozen
from domain import classify_domain  # frozen Phase 4

CONF_MIN = 1.5                       # min Phase-4 score gap to trust the domain
ALWAYS_TRUSTED = ("BANKING_FINANCE", "UTILITIES_SERVICES")  # 0 misclassifications

# markers that, on their own, mean "this document is not a bill"
NOT_A_BILL_STRUCT = (
    "this is not a bill", "explanation of benefits", "summary notice",
    "declarations page", "renewal declarations", "proof of insurance",
    "insurance card", "rates & charges", "rates and charges",
    "financial statement", "estimate id", "payment is not required",
    "no payment is required", "do not pay", "retain this for your records",
    "retain for your records", "description of your coverage",
)

# --------------------------------------------------------------------------
# The semantic contract, per domain.
#
#  amount.exclude  : if the LABEL printed on a money candidate's row contains
#                    one of these, that number is not "what the recipient
#                    owes" in this domain -> drop the candidate.
#  amount.require  : unless one of these appears somewhere in the document,
#                    this domain has no "amount due" at all -> value = null.
#  action.renew_if : domains where a renewal context should remap a frozen
#                    "pay" action to "renew".
# --------------------------------------------------------------------------

SEMANTICS = {
    "BANKING_FINANCE": {
        "amount": {
            "exclude": ["ending balance", "beginning balance", "opening balance",
                        "closing balance", "available balance", "balance forward",
                        "previous balance", "balance on ", "total credit",
                        "credit line", "credit available", "available credit",
                        "cash access line", "credit access line"],
            "require": ["amount due", "minimum payment due", "payment due",
                        "current payment due", "new balance total",
                        "total amount due", "please pay this amount",
                        "minimum amount due", "total minimum payment"],
        },
        # a checking / savings statement with no 'amount due' anchor is
        # informational, not an unpaid bill
        "payment_status_null_is": "not_applicable",
        "action_renew": False,
    },
    "HEALTHCARE": {
        "amount": {
            "exclude": ["total charges", "total current charges", "provider charges",
                        "insurance paid", "insurance payment", "insurance adjustment",
                        "insurance pending", "amount approved", "allowed charges",
                        "patient payments", "adjustments", "charges/payments",
                        "total claim cost", "provider can charge"],
            "require": ["amount you owe", "amount due", "patient responsibility",
                        "your responsibility", "balance due", "what you owe",
                        "due from patient", "patient balance",
                        "please pay this amount", "responsibility to pay",
                        "pay this amount"],
        },
        "payment_status_null_is": "not_applicable",
        "action_renew": False,
    },
    "INSURANCE": {
        "amount": {
            "exclude": ["premium", "coverage", "deductible", "limits",
                        "bodily injury", "property damage", "six month premium",
                        "policy premium", "fees", "annual dues", "each person",
                        "each occurrence", "collision", "comprehensive"],
            "require": ["amount due", "premium due", "minimum due",
                        "total amount owed", "please pay this amount",
                        "balance due", "minimum amount due", "amount you owe",
                        "pay this amount", "amount owed"],
        },
        "payment_status_null_is": "not_applicable",
        "action_renew": True,
    },
    "GOVERNMENT": {
        "amount": {
            "exclude": ["registration fee", "license fee", "weight fee",
                        "special plate fee", "smog", "county / district",
                        "owner responsibility fee", "prior balance"],
            "require": ["amount due", "amount due immediately", "amount due by",
                        "total due", "total due on or before", "balance due",
                        "pay this amount", "restoration fee", "amount you owe"],
        },
        # a government notice with a number is not automatically a payment
        # demand -- but we do NOT force not_applicable here (a levy / bill is
        # real). Leave payment_status to the frozen decision.
        "payment_status_null_is": None,
        "action_renew": True,
    },
    "UTILITIES_SERVICES": {
        "amount": {
            "exclude": ["previous balance", "budget", "payments received",
                        "payments and other"],
            "require": ["amount due", "total due", "total amount due",
                        "current charges", "your new charges",
                        "please pay this amount", "amount you owe",
                        "current charge summary", "new balance", "balance due",
                        "payment is due", "your payment is due", "total account",
                        "current invoice", "amount enclosed", "pay this amount"],
        },
        "payment_status_null_is": None,
        "action_renew": False,
    },
    "HOUSING_PROPERTY": {
        # HOA dues bills behave like utilities; keep the frozen amount logic
        "amount": None,
        "payment_status_null_is": None,
        "action_renew": False,
    },
    "OTHER": {
        "amount": None,
        "payment_status_null_is": None,
        "action_renew": False,
    },
}

_RENEW_CONTEXT = ("renewal notice", "renew now", "to renew", "membership renewal",
                  "renewal declarations", "registration renewal")
_HARD_DUE = ("past due", "delinquent", "final notice", "amount due immediately",
             "levy")


# --------------------------------------------------------------------------

def _joined(elements):
    return "  ".join(e["text"].lower() for e in elements)


def _row_label(elements, bbox):
    """Text left of a money token on the same printed row -- the label the
    frozen extractor paired the number with. Pure geometry."""
    cand = {"bbox": bbox}
    parts = [(S.x1(e), e["text"]) for e in elements
             if S.same_row(e, cand) and S.cx(e) < S.cx(cand)
             and 0 <= S.horizontal_gap(e, cand) <= 560]
    parts.sort()
    return " ".join(t for _, t in parts).lower()


def _has_any(text, needles):
    return any(n in text for n in needles)


def resolve(elements):
    """Domain-aware field resolution. Returns the 6-field dict (same shape as
    X.extract_fields) with '_domain', '_domain_gap', and per-field
    '_status'/'_reason' on the three fields this layer owns."""
    base = X.extract_fields(elements)
    joined = _joined(elements)
    lh = ST.classify_sender(elements)
    head = lh[0]["value"] if lh else ""
    dc = classify_domain(joined, head)
    dom, gap = dc["pred"], dc["gap"]
    trust = gap >= CONF_MIN or dom in ALWAYS_TRUSTED
    spec = SEMANTICS.get(dom, SEMANTICS["OTHER"])
    struct_not_bill = _has_any(joined, NOT_A_BILL_STRUCT)

    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    out["_domain"] = dom
    out["_domain_gap"] = gap

    # ---------- total_amount ----------
    amt_val = base["total_amount"]["value"]
    amt_status, amt_reason = "resolved", "frozen extraction (domain carries no constraint)"
    if trust and spec["amount"] is not None:
        excl, req = spec["amount"]["exclude"], spec["amount"]["require"]
        cands = X.extract_amount(elements)
        kept = [c for c in cands
                if not _has_any((c["text"] + " " + _row_label(elements, c["bbox"])).lower(), excl)]
        has_req = _has_any(joined, req)

        if not has_req:
            amt_val, amt_status = None, "not_applicable"
            amt_reason = f"{dom}: no 'amount due' anchor -> not a bill"
        elif struct_not_bill:
            amt_val, amt_status = None, "not_applicable"
            amt_reason = f"{dom}: explicit not-a-bill structure"
        elif kept and kept[0]["score"] >= X.TAU["total_amount"]:
            amt_val, amt_status = kept[0]["value"], "resolved"
            amt_reason = f"{dom}: top admissible candidate after excluding {excl[:1]}..."
        else:
            amt_val, amt_status = None, "insufficient_evidence"
            amt_reason = f"{dom}: no admissible amount candidate above threshold"
    elif struct_not_bill:
        # domain-independent: an EOB / declarations / statement is never a bill
        if amt_val is not None:
            amt_val, amt_status = None, "not_applicable"
            amt_reason = "explicit not-a-bill structure (domain-independent)"

    out["total_amount"] = {"value": amt_val, "score": 0.0, "runner_up": None,
                           "evidence": [(amt_reason, 0)], "_status": amt_status,
                           "_reason": amt_reason}
    amt_num = float(amt_val) if amt_val is not None else None

    # ---------- payment_status ----------
    ps = X.decide_payment_status(elements, amt_num)["value"]
    ps_reason = "frozen marker/anchor decision"
    if ps not in ("paid", "not_applicable"):
        if struct_not_bill and amt_num is None:
            ps, ps_reason = "not_applicable", "explicit not-a-bill structure"
        elif trust and spec.get("payment_status_null_is") == "not_applicable" \
                and amt_num is None and spec["amount"] is not None \
                and not _has_any(joined, spec["amount"]["require"]):
            ps, ps_reason = "not_applicable", f"{dom}: informational document, nothing owed"
    ps_status = "not_applicable" if ps == "not_applicable" else (
        "resolved" if ps else "insufficient_evidence")
    out["payment_status"] = {"value": ps, "score": 0.0, "runner_up": None,
                             "evidence": [(ps_reason, 0)], "_status": ps_status,
                             "_reason": ps_reason}

    # ---------- action ----------
    act = base["action"]["value"]
    act_reason = "frozen action extraction"
    if act == "pay" and spec.get("action_renew") \
            and _has_any(joined, _RENEW_CONTEXT) and not _has_any(joined, _HARD_DUE):
        act, act_reason = "renew", f"{dom}: renewal context, no hard-due marker"
    out["action"] = {"value": act, "score": base["action"]["score"],
                     "runner_up": None, "evidence": [(act_reason, 0)],
                     "_status": "resolved" if act else "insufficient_evidence",
                     "_reason": act_reason}

    # sender / recipient / due_date: frozen pass-through (Phase 5 finding)
    for f in ("sender", "recipient", "due_date"):
        out[f]["_status"] = "resolved" if base[f]["value"] else "insufficient_evidence"
        out[f]["_reason"] = "frozen Phase 3 (domain gives no signal for this field)"

    return out
