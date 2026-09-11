"""
Semantic anchor dictionaries + deterministic value-shape classifiers.

Anchors are NEVER an answer. They are the label text a bill prints next to
the value we actually want ("Balance Due" -> the number to its right).

Value-shape classifiers (looks_like_money / looks_like_date / ...) are
plain character inspection -- .isdigit(), membership in a month-name list,
counting '/' and '-'. No `import re`, per the experiment constraint. The
point is that every decision stays auditable by eye.
"""

# ------------------------------------------------------------------ anchors

AMOUNT_ANCHORS_STRONG = [
    "amount due", "balance due", "amount you owe", "amount you owed",
    "total due", "total amount due", "new balance total", "new balance",
    "amount due by", "pay this amount", "please pay this amount",
    "current payment due", "total minimum payment due", "minimum payment due",
    "your new charges", "total you may be billed", "balance", "pay amount",
    "total", "grand total", "invoice total", "amount enclosed",
]
# labels that sit next to a number we must NOT pick as "what you owe"
AMOUNT_ANCHORS_NEGATIVE = [
    "previous balance", "sub total", "subtotal", "sub-total",
    "total charges", "amount of charges", "payments and other credits",
    "payments/credits", "payment, credits", "credit line", "credit available",
    "credit access line", "available credit", "tax rate", "periodic rate",
    "annual percentage rate", "apr", "late fee", "penalty", "finance charge",
    "amount you paid", "insurance paid", "adjustments", "you saved",
    "amount not covered", "amount approved", "cash advance",
]

DUE_DATE_ANCHORS = [
    "due date", "date due", "pay by", "payment due", "due by", "deadline",
    "amount due by", "payment due date", "due on", "please pay by",
    "pay on or before", "must be received by", "respond by", "pay before",
]
# dates that are explicitly NOT the deadline
DUE_DATE_ANCHORS_NEGATIVE = [
    "statement date", "statement closing date", "closing date", "notice date",
    "date of this notice", "invoice date", "billing date", "issue date",
    "billing period", "opening date", "date of service", "print date",
    "claims processed", "date this period",
]

RECIPIENT_ANCHORS = [
    "bill to", "billed to", "sold to", "ship to", "to:", "attn",
    "patient", "patient name", "member", "member name", "subscriber",
    "customer", "customer name", "account holder", "addressee", "mail to",
    "notice for", "prepared for", "for ",
]

SENDER_ANCHORS = [
    "from", "from:", "issued by", "sent by", "remit to", "make checks payable",
    "customer service", "questions about your bill", "contact us",
]
# strings that identify a party as an institution (a sender), not a person
SENDER_INSTITUTION_HINTS = [
    "edison", "sce", "southern california edison",
    "bank of america", "bankamericard", "chase", "wells fargo", "citibank",
    "internal revenue service", "department of the treasury", "irs",
    "medicare", "medicaid", "centers for medicare", "cms", "social security",
    "socalgas", "the gas company", "dwp", "water district", "utility",
    "allina health", "kaiser", "sutter", "ucla health", "hoag", "cedars",
    "hospital", "health", "healthcare", "medical center", "clinic",
    "insurance", "allstate", "state farm", "geico", "progressive", "aaa",
    "farmers", "mutual", "casualty", "assurance", "dmv",
    "department of motor vehicles", "franchise tax board", "county of",
    "city of", "hoa", "homeowners association", "association",
    "company", "corporation", "inc.", "llc", "l.l.c", "co.", "n.a.",
    "alliance", "authority", "district", "cooperative", "utilities",
    "services", "systems", "solutions", "partners", "network", "group",
    "trust", "fund", "plan", "board", "bureau", "agency", "office of",
]

# action verbs -> normalised action label
ACTION_PHRASES = {
    "pay": [
        "please pay", "pay this amount", "pay the amount", "amount due",
        "make checks payable", "remit payment", "remit to", "send payment",
        "pay by", "payment due", "pay your bill", "pay online", "pay now",
        "to avoid additional interest", "to avoid a late", "past due",
        "due on receipt", "due upon receipt", "payable upon receipt",
        "amount enclosed", "total amount due",
    ],
    "call": [
        "please call", "call us", "call the number", "contact us at",
        "call 1-800", "call our office", "call this number",
    ],
    "contact": [
        "please contact", "contact your agent", "reach out to",
        "get in touch",
    ],
    "renew": [
        "please renew", "renew your", "renewal is due", "to renew",
    ],
    "respond": [
        "please respond", "respond by", "reply by", "response required",
        "required action", "action required", "you must respond",
    ],
    "review": [
        "double-check this notice", "review this notice", "see page 2",
        "verify the information", "check this statement", "this is not a bill",
    ],
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}

NOT_A_BILL_MARKERS = [
    "this is not a bill", "not a bill", "no payment is required",
    "no payment required", "for your information only", "informational only",
    "do not pay", "this is not an invoice",
]
PAID_MARKERS = [
    "paid in full", "payment received", "balance: $0.00", "balance $0.00",
    "no balance due", "no payment due", "amount due: $0.00", "account paid",
    "paid - thank you", "thank you for your payment",
]


# ------------------------------------------------------ value-shape checks

def _clean(tok):
    return tok.strip().strip(",.:;()[]{}").strip()


def looks_like_money(text):
    """A standalone monetary value: optional '$', digits, ',' grouping, and a
    2-digit cents part -- OR a bare integer/'.dd' with a leading '$'.
    Rejects percentages, phone-shaped and date-shaped runs."""
    t = _clean(text)
    if not t:
        return False
    if "%" in t:
        return False
    has_dollar = t.startswith("$") or t.startswith("-$") or t.startswith("$-")
    body = t.lstrip("-$").replace(",", "").strip()
    if not body:
        return False
    if "/" in body or "-" in body:  # date-ish
        return False
    for ch in body:
        if not (ch.isdigit() or ch == "."):
            return False
    if body.count(".") > 1:
        return False
    if "." in body:
        cents = body.split(".")[1]
        if len(cents) != 2:
            return False
        return True
    # no decimal point: only treat as money if it was explicitly $-marked
    return has_dollar and body.isdigit() and 1 <= len(body) <= 9


def money_value(text):
    """Float value of a money-looking token, or None."""
    if not looks_like_money(text):
        return None
    body = _clean(text).lstrip("-$").replace(",", "")
    try:
        return float(body)
    except ValueError:
        return None


def looks_like_date(text):
    return parse_date(text) is not None


def _valid_ymd(y, m, d):
    if not (1990 <= y <= 2035):
        return False
    if not (1 <= m <= 12):
        return False
    if not (1 <= d <= 31):
        return False
    return True


def parse_date(text):
    """Return 'YYYY-MM-DD' for a recognised date, else None.

    Handles:  MM/DD/YYYY  MM/DD/YY  M/D/YY  YYYY-MM-DD
              'January 29, 2018'   '05 Sep 2024'   'Sep 5, 2024'
    Pure string work -- split on spaces / '/' / '-', look words up in MONTHS.
    """
    t = _clean(text).lower().replace(",", " ")
    t = " ".join(t.split())
    if not t:
        return None

    # numeric slash form
    if "/" in t and " " not in t:
        parts = t.split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            mo, da, yr = parts
            y = int(yr)
            if y < 100:
                y += 2000
            m, d = int(mo), int(da)
            if _valid_ymd(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"
        return None

    # ISO form
    if "-" in t and " " not in t:
        parts = t.split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if _valid_ymd(y, m, d):
                return f"{y:04d}-{m:02d}-{d:02d}"
        return None

    # word forms
    toks = t.split()
    month = None
    day = None
    year = None
    for tok in toks:
        tk = tok.strip(".")
        if tk in MONTHS:
            month = MONTHS[tk]
        elif tk.isdigit():
            v = int(tk)
            if v >= 1990 and year is None:
                year = v
            elif 1 <= v <= 31 and day is None:
                day = v
    if month and day and year and _valid_ymd(year, month, day):
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


# words that make a capitalised phrase a form label / bill term, not a name
_NON_NAME_WORDS = {
    "payment", "name", "total", "number", "summary", "information", "date",
    "balance", "amount", "service", "card", "account", "please", "statement",
    "invoice", "bill", "billing", "charges", "charge", "claims", "claim",
    "notice", "address", "addressee", "status", "deductible", "due", "paid",
    "credit", "debit", "check", "cheque", "reference", "period", "page",
    "policy", "member", "subscriber", "customer", "patient", "provider",
    "hospital", "medical", "center", "clinic", "insurance", "bank", "phone",
    "tel", "fax", "email", "www", "http", "signature", "exp", "expiration",
    "description", "quantity", "rate", "tax", "subtotal", "sub", "remit",
    "enclosed", "coupon", "portion", "warning", "example", "questions",
    "inquiries", "detail", "details", "transaction", "activity", "usage",
    "from", "to", "for", "the", "of", "and", "your", "our", "this", "here",
    "pay", "online", "mail", "box", "po", "p.o", "street", "avenue", "ave",
    "road", "rd", "drive", "blvd", "lane", "suite", "apt", "unit", "floor",
    "reminder", "second", "first", "final", "past",
}
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc", "usa",
}


def name_core(text):
    """Strip trailers a spotting line often glues onto an addressee name:
    '/ Page 5 of 5', 'Page 1 of 1', a trailing account stamp. Returns the
    name portion only."""
    t = _clean(text)
    for sep in (" / ", "  "):
        if sep in t:
            t = t.split(sep)[0].strip()
    low = t.lower()
    for marker in (" page ", " pg "):
        if marker in low:
            t = t[:low.index(marker)].strip()
            low = t.lower()
    return t.strip(" /-")


def looks_like_person_name(text):
    """Heuristic: 'LAST, FIRST' or 2-5 capitalised tokens (allowing '&' and
    initials), no digits, no institution hint word, no form-label word, not a
    'CITY, ST' pair. Enough to separate an addressee line from letterhead /
    UI labels -- not a full NER."""
    t = name_core(text)
    if not t or any(c.isdigit() for c in t):
        return False
    low = t.lower()
    words = {w.strip(".,&'") for w in low.split()}
    if words & _NON_NAME_WORDS:
        return False
    if any(h in low for h in SENDER_INSTITUTION_HINTS):
        return False

    if "," in t:
        left, _, right = t.partition(",")
        left, right = left.strip(), right.strip()
        rtoks = right.split()
        if rtoks and rtoks[-1].lower().strip(".") in _US_STATES:
            return False  # 'SIMI VALLEY, CA'
        if left and right and len(left.split()) <= 2 and len(rtoks) <= 3:
            lok = left.replace(" ", "").replace("-", "").isalpha()
            rok = bool(rtoks) and rtoks[0].strip(".").isalpha()
            return lok and rok
        return False

    toks = [tk for tk in t.split() if tk not in ("&",)]
    if not (2 <= len(toks) <= 5):
        return False
    alpha_caps = 0
    for tk in toks:
        tk2 = tk.strip(".&'-")
        if not tk2:
            continue
        if not (tk2[0].isupper() or tk2.isupper()):
            return False
        if tk2.replace("-", "").isalpha():
            alpha_caps += 1
    return alpha_caps >= 2


def contains_any(haystack_lower, needles):
    return any(nd in haystack_lower for nd in needles)
