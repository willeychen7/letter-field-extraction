"""
Phase 8 (experiment) -- phone / contact extraction from frozen OCR
elements. No re-OCR. No semantic similarity. Never invents a number.

A phone element is any OCR element whose text contains a US-phone-shaped
token (incl. common OCR manglings: comma separators, glued area code,
1-800-WORD, and 'XXX' placeholders). Each is annotated with:
  - the number, normalised to digits (or the raw placeholder)
  - kind        : the contact channel, from nearby label words
  - is_fax / is_tty / is_placeholder / is_toll_free
  - band        : header / body / footer-coupon (by y position)
  - label       : text on the same row to its left, or the line above
  - org_context : nearest organisation/department words above/left
"""

import re

import spatial as S

# FORMAT detection only. A real phone token must carry phone punctuation
# (parens / dashes / dots / the comma manglings OCR produces) -- a bare
# 10-digit run with no separators is an account number / barcode, not a
# phone, and is rejected here.
_SEP = r"[-.\s,]"
_PHONE_RE = re.compile(
    r"""(?xi)
    (?:1\s?[-.,]\s?)?                       # optional 1- country code
    \(\d{3}\)\s?\d{3}""" + _SEP + r"""\d{4}          # (800) 242-7338
    |
    (?:1\s?[-.,]\s?)?
    \d{3}\s?[-.,]\s?\d{3}\s?[-.,]\s?\d{4}            # 800-242-7338 / 800,242,7338
    |
    (?:1[-.\s]?)?\(?[xX]{3}\)?[-.\s]?[xX]{3}[-.\s]?[xX]{4}   # 1-800-XXX-XXXX
    |
    1[-.\s]?(?:800|888|877|866|855|844|833)[-.\s][A-Z]{4,10}   # 1-800-MEDICARE
    """,
)

_LABELS = {
    "fax": ["fax"],
    "tty": ["tty", "tdd", "hearing impaired", "hearing-impaired", "relay"],
    "billing": ["billing", "billing inquiries", "billing questions",
                "questions about your bill", "bill inquiries", "pay by phone",
                "payment", "make a payment", "phone payment",
                "patient financial", "pfs@", " pfs ", "financial services",
                "to make a payment", "remit"],
    "customer_service": ["customer service", "customer care", "member service",
                         "member services", "service center", "contact us",
                         "to contact us", "questions?", "for questions",
                         "call us", "help", "assistance", "account information",
                         "your agent", "agent:", " agent ", "or call"],
    "claims": ["claim", "claims", "file a claim", "report a claim"],
    "lost_stolen": ["lost or stolen", "lost/stolen", "report lost", "fraud"],
    "provider_clinic": ["appointment", "nurse", "clinic", "office", "scheduling",
                        "provider", "front desk"],
    "roadside": ["roadside", "emergency road", "tow", "towing"],
    "enroll": ["enroll", "sign up", "to enroll", "medicare easy pay"],
    "general": ["call", "phone", "tel", "telephone", "toll free", "toll-free",
                "contact", "1-800", "call 1"],
}

_ORG_HINT = ["bank", "insurance", "hospital", "health", "medical", "dmv",
             "medicare", "medicaid", "irs", "department", "association",
             "district", "company", "gas", "electric", "water", "edison",
             "socalgas", "chase", "allstate", "state farm", "progressive",
             "aaa", "hoa", "services", "administration", "bureau", "agency"]


def _digits(t):
    d = "".join(c for c in t if c.isdigit())
    return d


# well-known toll-free vanity equivalences (letter->keypad), so a picker
# result matches the numeric ground truth
_VANITY_DIGITS = {"MEDICARE": "8006334227", "FLOWERS": "8003569377"}


def _norm(tok):
    up = tok.upper()
    if "X" in up and up.count("X") >= 6:
        return "PLACEHOLDER"
    d = _digits(tok)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) == 10:
        return d
    # 1-800-WORD style
    if re.search(r"[A-Z]{4,}", up):
        word = up.split("-")[-1].strip()
        return _VANITY_DIGITS.get(word, "VANITY:" + word)
    return d or "PLACEHOLDER"


def _band(e, page_h_guess=1000):
    cy = S.cy(e)
    if cy < 160:
        return "header"
    if cy > 820:
        return "footer_coupon"
    return "body"


def _row_left_text(elements, target):
    parts = [(S.x1(e), e["text"]) for e in elements
             if e is not target and S.same_row(e, target)
             and S.cx(e) < S.cx(target) and 0 <= S.horizontal_gap(e, target) <= 620]
    parts.sort()
    return " ".join(t for _, t in parts)


def _line_above_text(elements, target, mh=14):
    cands = [e for e in elements if e is not target
             and 0 <= (S.y1(target) - S.y2(e)) <= 2.4 * mh
             and S.horizontal_overlap_ratio(e, target) >= 0.15]
    cands.sort(key=lambda e: S.y2(e), reverse=True)
    return " ".join(e["text"] for e in cands[:2])


def _classify_kind(context_low):
    for kind, words in _LABELS.items():
        if kind in ("general",):
            continue
        if any(w in context_low for w in words):
            return kind
    if any(w in context_low for w in _LABELS["general"]):
        return "general"
    return "unlabeled"


def _org_context(elements, target, mh=14):
    """nearest words carrying an org/department hint, above or left."""
    best, best_d = None, 1e9
    for e in elements:
        if e is target:
            continue
        low = e["text"].lower()
        if not any(h in low for h in _ORG_HINT):
            continue
        if S.cy(e) > S.cy(target) + 5:      # must be above / same row
            continue
        d = S.center_distance(e, target)
        if d < best_d:
            best, best_d = e["text"].strip(), d
    return best


def extract_phones(elements):
    mh = 14
    hs = sorted(S.height(e) for e in elements if S.height(e) > 0)
    if hs:
        mh = hs[len(hs) // 2] or 14
    out = []
    for e in elements:
        for m in _PHONE_RE.finditer(e["text"]):
            tok = m.group(0)
            up = tok.upper()
            is_vanity = bool(re.search(r"[A-Z]{4,}", up))
            is_ph = "X" in up and up.count("X") >= 6
            nd = len(_digits(tok))
            if not is_vanity and not is_ph and nd not in (10, 11):
                continue
            # must carry at least one phone separator OR be vanity/placeholder
            if not is_vanity and not is_ph and not re.search(_SEP, tok.strip("()")):
                continue
            left = _row_left_text(elements, e)
            above = _line_above_text(elements, e, mh)
            own = e["text"]
            ctx = f"{own}  ||  {left}  ||  {above}".lower()
            norm = _norm(tok)
            kind = _classify_kind(ctx)
            out.append({
                "raw": tok.strip(),
                "in_element": own.strip(),
                "norm": norm,
                "kind": kind,
                "is_fax": "fax" in ctx,
                "is_tty": kind == "tty",
                "is_toll_free": norm[:3] in ("800", "888", "877", "866", "855",
                                             "844", "833") or norm.startswith("VANITY"),
                "is_placeholder": norm == "PLACEHOLDER" or "x" in tok.lower(),
                "band": _band(e),
                "bbox": e["bbox"],
                "label_left": left.strip(),
                "label_above": above.strip(),
                "org_context": _org_context(elements, e, mh),
            })
    # de-dup exact same normalised number + kind + band
    seen, uniq = set(), []
    for p in out:
        key = (p["norm"], p["kind"], p["band"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq
