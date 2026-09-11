"""
Local deterministic spatial field extraction.

Input : list of OCR elements {"text","bbox":[x1,y1,x2,y2]}  (bbox in 0..1000)
Output: {field: {"value", "score", "evidence"[]}}  for the 6 stage-1 fields
        sender, recipient, total_amount, payment_status, due_date, action

Design rules (from the experiment brief):
  - No regex, no second LLM, no external API. Only anchors + geometry.
  - Transparent additive score with a written reason for every term.
  - Never invent a value. Below threshold -> null is the correct answer.
"""

import anchors as A
import spatial as S
import structure as ST

# score threshold below which we emit null rather than guess
# emit-vs-null thresholds. Round values picked after inspecting the candidate
# score distributions on the 6 sample images -- this is calibration on n=6,
# not held-out validation; a real go/no-go needs the full 20-image set.
TAU = {
    "total_amount": 0.55,
    "due_date": 0.50,
    "sender": 0.45,
    "recipient": 0.50,
    "action": 0.40,
    "payment_status": 0.0,  # categorical, decided by markers not a score
}


def _low(e):
    return e["text"].lower()


def _find_anchor_elements(elements, phrases):
    """Elements whose text contains one of `phrases` (substring, lower-case).
    Returns [(element, matched_phrase)]."""
    out = []
    for e in elements:
        low = _low(e)
        for p in phrases:
            if p in low:
                out.append((e, p))
                break
    return out


def _proximity_score(anchor, cand):
    """0..1 by how a bill would visually pair a label with its value.

    Same-row alignment IS the signal on a bill: the value column can be far
    to the right of its label, so a same-row hit gets a solid floor (0.55)
    plus a gentle gap-based bonus, rather than decaying to ~0 across the
    page width. Directly-below with x-overlap (boxed forms, e.g. 'DATE DUE'
    over the date) is the next strongest."""
    if S.same_row(anchor, cand) and S.cx(cand) >= S.cx(anchor):
        gap = max(0.0, S.horizontal_gap(anchor, cand))
        return min(1.0, 0.55 + 0.45 * max(0.0, 1.0 - gap / 700.0))
    if S.is_below(cand, anchor):
        gap = max(0.0, S.vertical_gap(anchor, cand))
        if gap <= 45 and S.horizontal_overlap_ratio(anchor, cand) >= 0.20:
            return max(0.0, 0.80 - gap / 150.0)
    d = S.center_distance(anchor, cand)
    return max(0.0, 0.32 - d / 900.0)


# --------------------------------------------------------------- amount

def extract_amount(elements):
    cands = []
    money_els = [e for e in elements if A.looks_like_money(e["text"])]
    values = [A.money_value(e["text"]) for e in money_els]
    strong = _find_anchor_elements(elements, A.AMOUNT_ANCHORS_STRONG)
    negative = _find_anchor_elements(elements, A.AMOUNT_ANCHORS_NEGATIVE)

    for e, v in zip(money_els, values):
        if v is None or v <= 0:
            continue
        ev = []
        score = 0.25
        ev.append(("base_money_token", 0.25))

        best_anchor = None
        best_prox = 0.0
        best_phrase = None
        for a, phrase in strong:
            prox = _proximity_score(a, e)
            if prox > best_prox:
                best_prox, best_anchor, best_phrase = prox, a, phrase
        if best_anchor is not None and best_prox > 0.05:
            add = round(0.55 * best_prox, 3)
            score += add
            rel = "same_row" if S.same_row(best_anchor, e) else "below"
            ev.append((f"strong_anchor '{best_phrase}' ({rel}, prox={best_prox:.2f})", add))

        neg_hit = None
        for a, phrase in negative:
            if S.same_row(a, e) and abs(S.cx(a) - S.cx(e)) < 520:
                neg_hit = phrase
                break
        if neg_hit:
            score -= 0.45
            ev.append((f"negative_anchor '{neg_hit}' same_row", -0.45))

        if e["text"].strip().startswith("$"):
            score += 0.12
            ev.append(("has_dollar_sign", 0.12))

        occ = sum(1 for x in values if x is not None and abs(x - v) < 0.005)
        if occ >= 2:
            score += 0.12
            ev.append((f"value_repeats_x{occ}", 0.12))

        # bottom-of-page remittance coupon often repeats the true amount
        if S.cy(e) > 780:
            score += 0.05
            ev.append(("in_payment_coupon_band", 0.05))

        cands.append({
            "value": f"{v:.2f}",
            "num": v,
            "score": round(score, 3),
            "text": e["text"],
            "bbox": e["bbox"],
            "evidence": ev,
        })

    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands


# --------------------------------------------------------------- due date

def extract_due_date(elements):
    cands = []
    date_els = [(e, A.parse_date(e["text"])) for e in elements]
    date_els = [(e, d) for e, d in date_els if d]
    pos = _find_anchor_elements(elements, A.DUE_DATE_ANCHORS)
    neg = _find_anchor_elements(elements, A.DUE_DATE_ANCHORS_NEGATIVE)

    for e, iso in date_els:
        ev = []
        score = 0.15
        ev.append(("base_date_token", 0.15))

        best_prox, best_phrase, best_a = 0.0, None, None
        for a, phrase in pos:
            prox = _proximity_score(a, e)
            if prox > best_prox:
                best_prox, best_phrase, best_a = prox, phrase, a
        if best_a is not None and best_prox > 0.05:
            add = round(0.6 * best_prox, 3)
            score += add
            rel = "same_row" if S.same_row(best_a, e) else "below"
            ev.append((f"due_anchor '{best_phrase}' ({rel}, prox={best_prox:.2f})", add))

        neg_hit = None
        for a, phrase in neg:
            if _proximity_score(a, e) > 0.30:
                neg_hit = phrase
                break
        if neg_hit:
            score -= 0.5
            ev.append((f"non_deadline_anchor '{neg_hit}'", -0.5))

        # a date embedded in a sentence that also says "by" / "pay"
        low = _low(e)
        if "by " in low and ("pay" in low or "amount due" in low):
            score += 0.2
            ev.append(("inline 'pay ... by <date>'", 0.2))

        cands.append({
            "value": iso, "score": round(score, 3), "text": e["text"],
            "bbox": e["bbox"], "evidence": ev,
        })

    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands


# --------------------------------------------------------------- sender
# Phase 3: explicit decision ladder S1 -> S2 -> S3 (structure.classify_sender).
# No mixed scoring. SENDER_INSTITUTION_HINTS is used, not expanded.

def extract_sender(elements):
    ladder = ST.classify_sender(elements)   # 0 or 1 entry, tagged with tier
    out = []
    for c in ladder:
        out.append({"value": c["value"], "score": ST._S_TIER_SCORE[c["tier"]],
                    "tier": c["tier"], "text": c["value"], "evidence": c["evidence"]})
    return out


# --------------------------------------------------------------- recipient
# Phase 3: explicit decision ladder R1 -> R5 (structure.classify_recipient).
# R1 labeled address block > R3 coupon-repeat > R2 complete block by
# position > R4 name+partial address > R5 bare name next to a label.

_R_ORDER = ["R1", "R3", "R2", "R4", "R5"]


def extract_recipient(elements):
    cands = ST.classify_recipient(elements)
    if not cands:
        return []
    # pick the first tier (in priority order) that produced a candidate
    by_tier = {}
    for c in cands:
        by_tier.setdefault(c["tier"], []).append(c)
    for tier in _R_ORDER:
        if tier in by_tier:
            picked = by_tier[tier]
            return [{"value": c["value"], "score": ST._R_TIER_SCORE[tier],
                     "tier": tier, "text": c.get("text", c["value"]),
                     "evidence": c["evidence"]} for c in picked]
    return []


# --------------------------------------------------------------- action

def extract_action(elements):
    cands = []
    for e in elements:
        low = _low(e)
        for label, phrases in A.ACTION_PHRASES.items():
            hit = next((p for p in phrases if p in low), None)
            if not hit:
                continue
            score = 0.4
            ev = [(f"action_phrase '{hit}' -> {label}", 0.4)]
            if low.strip().startswith(("please ", "you must ", "to avoid")):
                score += 0.2
                ev.append(("imperative_sentence_start", 0.2))
            if S.cy(e) < 500:
                score += 0.05
                ev.append(("upper_half_of_page", 0.05))
            cands.append({
                "value": label, "score": round(score, 3), "text": e["text"],
                "bbox": e["bbox"], "evidence": ev,
            })
            break
    # prefer the strongest, but 'pay' outranks 'review' when both present
    order = {"pay": 3, "respond": 2, "renew": 2, "call": 1, "contact": 1, "review": 0}
    cands.sort(key=lambda c: (c["score"], order.get(c["value"], 0)), reverse=True)
    return cands


# --------------------------------------------------------------- payment_status

def decide_payment_status(elements, amount_value):
    joined = "  ".join(e["text"].lower() for e in elements)
    ev = []
    if A.contains_any(joined, A.NOT_A_BILL_MARKERS):
        ev.append("explicit 'this is not a bill' marker")
        return {"value": "not_applicable", "score": 1.0, "evidence": ev}
    if A.contains_any(joined, A.PAID_MARKERS):
        ev.append("explicit paid / zero-balance marker")
        return {"value": "paid", "score": 1.0, "evidence": ev}
    has_due_anchor = any(p in joined for p in A.AMOUNT_ANCHORS_STRONG) or \
        any(p in joined for p in A.DUE_DATE_ANCHORS)
    if amount_value is not None and amount_value > 0 and has_due_anchor:
        ev.append(f"positive amount ({amount_value:.2f}) + due/balance anchor, no paid marker")
        return {"value": "unpaid", "score": 0.8, "evidence": ev}
    if amount_value is not None and amount_value > 0:
        ev.append("positive amount present but no explicit due anchor")
        return {"value": "unpaid", "score": 0.55, "evidence": ev}
    ev.append("no amount owed and no paid/not-a-bill marker -> undetermined")
    return {"value": None, "score": 0.0, "evidence": ev}


# --------------------------------------------------------------- orchestrate

def _top(cands):
    return cands[0] if cands else None


def extract_fields(elements):
    amount_c = extract_amount(elements)
    due_c = extract_due_date(elements)
    sender_c = extract_sender(elements)
    recip_c = extract_recipient(elements)
    action_c = extract_action(elements)

    result = {}

    def finalize(field, cands):
        top = _top(cands)
        if top and top["score"] >= TAU[field]:
            result[field] = {
                "value": top["value"], "score": top["score"],
                "evidence": top["evidence"],
                "runner_up": (cands[1]["value"], cands[1]["score"]) if len(cands) > 1 else None,
            }
        else:
            result[field] = {
                "value": None,
                "score": top["score"] if top else 0.0,
                "evidence": (top["evidence"] if top else []) + [("below_threshold_or_no_candidate", 0)],
                "runner_up": (top["value"], top["score"]) if top else None,
            }

    finalize("total_amount", amount_c)
    finalize("due_date", due_c)
    finalize("sender", sender_c)
    finalize("recipient", recip_c)
    finalize("action", action_c)

    amt_val = result["total_amount"]["value"]
    amt_num = float(amt_val) if amt_val is not None else None
    ps = decide_payment_status(elements, amt_num)
    result["payment_status"] = {"value": ps["value"], "score": ps["score"],
                                "evidence": [(x, 0) for x in ps["evidence"]],
                                "runner_up": None}

    # ---------------- cross-validation ----------------
    xval = []

    # 1. mutual exclusion: sender and recipient are built independently by
    # their own ladders; if they collide, trust the stronger STRUCTURE.
    #   recipient tiers R1/R2/R3 = a real address block  -> beats sender
    #   sender tier S1 = a real top letterhead           -> beats recipient
    #   otherwise the lower-tier candidate is nulled
    s_v = (result["sender"]["value"] or "").lower()
    r_v = (result["recipient"]["value"] or "").lower()
    if s_v and r_v and (s_v in r_v or r_v in s_v):
        s_tier = (_top(sender_c) or {}).get("tier", "S3")
        r_tier = (_top(recip_c) or {}).get("tier", "R5")
        r_strong = r_tier in ("R1", "R2", "R3")
        s_strong = s_tier == "S1"
        if r_strong and not s_strong:
            result["sender"]["value"] = None
            xval.append(f"sender==recipient -> kept recipient ({r_tier}), nulled sender")
        elif s_strong and not r_strong:
            result["recipient"]["value"] = None
            xval.append(f"sender==recipient -> kept sender ({s_tier}), nulled recipient")
        elif result["sender"]["score"] >= result["recipient"]["score"]:
            result["recipient"]["value"] = None
            xval.append("sender==recipient -> nulled recipient (weaker)")
        else:
            result["sender"]["value"] = None
            xval.append("sender==recipient -> nulled sender (weaker)")

    # 2. due_date must not precede a detected statement/notice date
    stmt_iso = None
    for e in elements:
        low = e["text"].lower()
        if any(k in low for k in ("statement date", "notice date", "invoice date",
                                  "date of this notice", "statement closing date")):
            d = A.parse_date(e["text"])
            if d:
                stmt_iso = d if (stmt_iso is None or d < stmt_iso) else stmt_iso
    dd = result["due_date"]["value"]
    if dd and stmt_iso and dd < stmt_iso:
        result["due_date"]["value"] = None
        xval.append(f"due_date {dd} precedes statement date {stmt_iso} -> nulled")

    # 3. amount sanity: chosen amount vs sum of line-item money tokens
    money_nums = sorted(
        [A.money_value(e["text"]) for e in elements if A.looks_like_money(e["text"])],
        reverse=True,
    )
    money_nums = [m for m in money_nums if m is not None]
    if amt_num is not None and money_nums:
        if amt_num == max(money_nums):
            xval.append(f"amount {amt_num:.2f} is the largest money token (consistent)")
        else:
            bigger = [m for m in money_nums if m > amt_num + 0.005]
            xval.append(f"note: {len(bigger)} money token(s) larger than chosen amount {amt_num:.2f}")

    # 4. not_applicable payment_status but a strong amount was chosen
    if result["payment_status"]["value"] == "not_applicable" and amt_num:
        # trust the explicit marker; drop the amount to avoid implying a bill
        result["total_amount"]["value"] = None
        xval.append("payment_status=not_applicable -> nulled total_amount (not a bill)")

    result["_cross_validation"] = xval
    return result
