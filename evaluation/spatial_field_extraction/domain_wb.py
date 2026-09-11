"""
Phase 4 (research only) -- Document Domain classifier.

7 classes (frozen): INSURANCE HEALTHCARE BANKING_FINANCE GOVERNMENT
UTILITIES_SERVICES HOUSING_PROPERTY OTHER  (CREDIT_CARD folded into
BANKING_FINANCE; AUTO_INSURANCE broadened to INSURANCE)

Design: no single keyword decides a class. Each class accumulates a score
from THREE independent evidence groups:
  1. issuer  -- what kind of organisation the letterhead / top block is
  2. subject -- what the document is structurally about (multi-term families)
  3. layout  -- form-specific structural tells (a coverage table + VIN, a
                checking summary, an EOB claim grid, an HOA dues line ...)
A class needs corroboration across >= 2 groups (or a strong issuer + 1) to
win. Ties / low max -> OTHER.

This does NOT import or modify the frozen Phase-3 pipeline. It only reads
OCR text. It is an experiment to test whether the taxonomy is natural.
"""

DOMAINS = ["INSURANCE", "HEALTHCARE", "BANKING_FINANCE", "GOVERNMENT",
           "UTILITIES_SERVICES", "HOUSING_PROPERTY", "OTHER"]

# ---- evidence term families. Each inner list = one "group hit" if ANY of its
#      phrases appear. Multiple groups hitting = corroboration.

ISSUER = {
    "INSURANCE": [
        ["insurance company", "mutual automobile", "casualty insurance",
         "fire and casualty", "auto club", "farmers insurance", "allstate",
         "state farm", "geico", "progressive", "aaa insurance", "mercury insurance",
         "nationwide", "liberty mutual", "the general", "esurance"],
    ],
    "HEALTHCARE": [
        ["health", "hospital", "medical center", "medical group", "clinic",
         "orthopedic", "healthcare", "physicians", "medicaid services",
         "centers for medicare", "health plan", "vision", "dental", "wellness",
         "kaiser", "sutter", "cedars", "ucla health", "hoag"],
    ],
    "BANKING_FINANCE": [
        ["bank", "n.a.", " na ", "credit union", "financial", "savings",
         "trust company", "jpmorgan", "wells fargo", "citibank", "chase",
         "capital one", "morgan stanley", "fidelity", "charles schwab",
         "east west bank", "first bank"],
    ],
    "GOVERNMENT": [
        ["internal revenue service", "department of the treasury", "irs",
         "department of motor vehicles", "dmv", "social security administration",
         "franchise tax board", "department of transportation",
         "state of ", "county of ", "city of ", "comptroller", "tax collector",
         "public service agency", "health & human services", "health and human services"],
    ],
    "UTILITIES_SERVICES": [
        ["edison", "gas company", "socalgas", "pg&e", "pacific gas",
         "water district", "water authority", "municipal water", "power company",
         "electric", "sanitation", "waste management", " wm ", "at&t", "verizon",
         "comcast", "xfinity", "spectrum", "cox communications", "t-mobile",
         "ventura river", "trabuco canyon"],
    ],
    "HOUSING_PROPERTY": [
        ["homeowners association", "home owners association", "hoa",
         "community association", "condominium association", "property management",
         "hoa management", "realty", "property tax", "assessor"],
    ],
}

SUBJECT = {
    "INSURANCE": [
        ["policy number", "policy #", "policy no"],
        ["vehicle", "vin", "year/make/model", "make model", "odometer",
         "vehicle id number", "license plate"],
        ["bodily injury", "property damage", "collision", "comprehensive",
         "uninsured motorist", "liability coverage", "deductible", "coverage",
         "premium", "named insured", "declarations", "policy period",
         "roadside", "membership renewal", "annual dues"],
    ],
    "HEALTHCARE": [
        ["explanation of benefits", "summary notice", "claim number",
         "claims processed", "medical claim"],
        ["provider", "patient", "guarantor", "date of service", "diagnosis",
         "procedure", "copay", "co-pay", "deductible for", "coinsurance",
         "amount you owe", "your responsibility", "financially responsible"],
        ["medicare", "medicaid", "part a", "part b", "part d", "prescription drug",
         "hospital insurance", "medical insurance", "benefit period", "enrollee"],
    ],
    "BANKING_FINANCE": [
        ["checking", "savings account", "account statement", "checking summary",
         "statement period", "statement of account"],
        ["beginning balance", "ending balance", "opening balance", "closing balance",
         "deposits and additions", "withdrawals", "electronic withdrawals",
         "night deposit", "wire transfer", "overdraft", "available balance"],
        ["loan", "mortgage", "principal balance", "escrow", "interest ytd",
         "investment", "portfolio", "brokerage", "money market"],
        ["credit card", "cardmember", "card member", "bankamericard",
         "cash rewards", "visa signature", "rewards card", "minimum payment due",
         "new balance total", "available credit", "credit line", "credit limit",
         "cash advance", "annual percentage rate", "penalty apr",
         "late payment warning", "purchases and adjustments"],
    ],
    "GOVERNMENT": [
        ["tax year", "notice date", "taxpayer identification", "social security number",
         "notice cp", "form 1040"],
        ["notice of intent to levy", "levy", "federal tax lien", "unpaid taxes",
         "amount due immediately", "installment agreement", "penalty and interest",
         "failure-to-pay penalty"],
        ["registration renewal", "driving privilege", "suspension", "restoration fee",
         "vehicle registration", "license fee", "weight fee", "smog",
         "renewal identification"],
    ],
    "UTILITIES_SERVICES": [
        ["service address", "service account", "billing period", "meter reading",
         "meter size", "account summary"],
        ["kwh", "kilowatt", "therms", "hcf", "ccf", "hundred cubic feet",
         "gallons", "usage summary", "tier 1", "rate schedule", "generation charges",
         "water service", "sewer"],
        ["wireless", "data summary", "minutes", "text messages", "bill-at-a-glance",
         "pickup schedule", "trash", "recycling", "cloudfront", "data transfer",
         "web services"],
    ],
    "HOUSING_PROPERTY": [
        ["hoa dues", "homeowner's dues", "homeowners dues", "association dues",
         "quarterly assessment", "special assessment", "monthly hoa"],
        ["property address", "lot #", "lot number", "clubhouse", "common area",
         "architectural", "covenant", "resident information", "unit "],
        ["property tax", "assessed value", "parcel", "millage"],
    ],
}

LAYOUT = {
    "INSURANCE": [
        ["coverage information", "vehicle information", "household drivers",
         "policy premium + fees", "limits and/or deductibles", "each person/each",
         "premium invoice", "renewal declarations", "balance due notice"],
    ],
    "HEALTHCARE": [
        ["this is not a bill", "provider charges", "allowed charges",
         "what you owe", "claim detail", "your claims & costs", "your deductible status",
         "notice of denial", "hospital services", "date(s) of service"],
    ],
    "BANKING_FINANCE": [
        ["transaction detail", "financial statement", "monthly income",
         "monthly expenses", "assets and liabilities", "details of your account",
         "instances", "service fee was waived"],
        ["total minimum payment", "finance charge summary",
         "minimum payment warning"],
    ],
    "GOVERNMENT": [
        ["billing summary", "what you need to do immediately", "official notice",
         "generated fees", "amount due by", "your caller id", "page 1 of"],
    ],
    "UTILITIES_SERVICES": [
        ["current charge summary", "rates & charges", "rates and charges",
         "your new charges", "usage/unit", "previous balance", "amount due"],
    ],
    "HOUSING_PROPERTY": [
        ["dues statement", "hoa invoice", "hoa dues invoice", "assessment",
         "detach here and return", "please register your e-mail"],
    ],
}


import re as _re
_WB_CACHE = {}
def _wb(term, text_low):
    rx = _WB_CACHE.get(term)
    if rx is None:
        # word boundary that tolerates a trailing plural 's', keeps phrases
        rx = _re.compile(r"(?<![a-z0-9])" + _re.escape(term.strip()) + r"(?:s)?(?![a-z])")
        _WB_CACHE[term] = rx
    return rx.search(text_low) is not None

def _hits(text_low, families):
    """number of distinct groups that fire, plus the phrases that fired.
    WORD-BOUNDARY variant (Phase 6 experiment): 'vision' no longer matches
    inside 'division', 'vin' no longer matches inside arbitrary words."""
    n, ev = 0, []
    for group in families:
        g = [p for p in group if _wb(p, text_low)]
        if g:
            n += 1
            ev.append(g[0])
    return n, ev


def classify_domain(ocr_text, letterhead_text=""):
    low = ("  " + ocr_text + "  ").lower()
    head = ("  " + (letterhead_text or "") + "  ").lower()

    scores, evidence = {}, {}
    for dom in DOMAINS:
        if dom == "OTHER":
            continue
        iss_n, iss_ev = _hits(head or low, ISSUER.get(dom, []))
        if not iss_ev:  # issuer words also count if they appear anywhere up top
            iss_n, iss_ev = _hits(low, ISSUER.get(dom, []))
            iss_n = min(iss_n, 1)
        sub_n, sub_ev = _hits(low, SUBJECT.get(dom, []))
        lay_n, lay_ev = _hits(low, LAYOUT.get(dom, []))

        groups_present = (1 if iss_ev else 0) + (1 if sub_n else 0) + (1 if lay_n else 0)
        raw = (2.0 if iss_ev else 0) + min(sub_n, 3) * 1.0 + min(lay_n, 2) * 1.0
        # require corroboration: a lone issuer word, or a single subject group,
        # is not enough on its own
        score = raw if groups_present >= 2 else raw * 0.35
        scores[dom] = round(score, 2)
        evidence[dom] = {"issuer": iss_ev, "subject": sub_ev, "layout": lay_ev,
                         "groups": groups_present}

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_s = ranked[0]
    second, second_s = ranked[1]
    gap = round(top_s - second_s, 2)

    if top_s < 2.5:
        pred = "OTHER"
    elif gap < 1.0 and evidence[top]["groups"] < 2:
        pred = "OTHER"
    else:
        pred = top

    return {
        "pred": pred, "top": top, "top_score": top_s,
        "second": second, "second_score": second_s, "gap": gap,
        "scores": scores, "evidence": {top: evidence[top], second: evidence[second]},
    }
