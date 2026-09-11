"""
Phase 3 -- Position / Structure layer for sender & recipient.

Everything here is layout geometry over OCR bboxes:
  - address-block detection: a stacked run of [name?] [street?] [city ST zip]
    lines sharing a left edge, with small vertical gaps
  - letterhead detection: text in the top band, grouped into stacked runs,
    scored by glyph size + page position, with a structural demotion for
    document-title banners and field labels

It does NOT expand SENDER_INSTITUTION_HINTS / _NON_NAME_WORDS (those are
imported from anchors.py and used as-is). It adds no semantic similarity.
The street-suffix / address-token sets below are new, and exist only to
recognise the *shape* of a postal address block -- they are not a
sender/name lexicon.
"""

import anchors as A
import spatial as S

PAGE_W = 1000.0
PAGE_H = 1000.0

# address-shape tokens (structural, not an org/name lexicon)
_STREET_SUFFIX = {
    "st", "st.", "street", "ave", "ave.", "avenue", "rd", "rd.", "road",
    "dr", "dr.", "drive", "blvd", "blvd.", "lane", "ln", "ln.", "way",
    "ct", "ct.", "court", "circle", "cir", "cir.", "pkwy", "parkway",
    "plaza", "pl", "pl.", "terrace", "ter", "hwy", "highway", "sq", "trail",
    "cntr", "center", "loop", "path", "run", "pike", "row",
}
_PO_BOX_MARKERS = ("po box", "p.o. box", "p o box", "p.o.box", "post office box",
                   "mail service cntr", "mailstop", "mail stop")


def median_line_height(elements):
    hs = sorted(S.height(e) for e in elements if S.height(e) > 0)
    if not hs:
        return 12.0
    return hs[len(hs) // 2] or 12.0


# --------------------------------------------------- address-shape checks

def _zip_shape(tok):
    t = tok.strip().strip(".,")
    if t.isdigit() and len(t) == 5:
        return True
    if "-" in t:
        a, _, b = t.partition("-")
        return a.isdigit() and len(a) == 5 and b.isdigit() and len(b) == 4
    return False


def looks_like_city_state_zip(text):
    """'HANSON, CT 00000-7253' / 'SPRINGFIELD IL 62704' / 'NEWPORT BEACH, CA
    92663' / 'CITY, ST 12345-6789'. Comma optional. A zip-shaped token with a
    2-3 letter alpha token (state / 'USA') right before it."""
    toks = text.replace(",", " ").split()
    for i in range(1, len(toks)):
        if _zip_shape(toks[i]):
            prev = toks[i - 1].strip(".")
            if prev.isalpha() and 2 <= len(prev) <= 3:
                return True
    # placeholder form with no numeric zip: 'CITY, ST 12345-6789' already
    # caught above; 'CITY, STATE ZIP' (all words) is intentionally NOT a match
    return False


def looks_like_street(text):
    t = text.strip()
    low = t.lower()
    if any(m in low for m in _PO_BOX_MARKERS):
        return True
    toks = t.split()
    if not toks:
        return False
    tailwords = {w.strip(".,").lower() for w in toks[-2:]}
    words = {w.strip(".,").lower() for w in toks}
    has_suffix = bool(tailwords & _STREET_SUFFIX) or bool(words & _STREET_SUFFIX)
    # '<house number> ... <street-suffix word>' -- a real street line, not a
    # '11 CCF' meter reading (needs the suffix word, not just number+word)
    if toks[0].rstrip(".").isdigit() and 1 <= len(toks[0]) <= 6 and has_suffix:
        return True
    if tailwords & _STREET_SUFFIX:
        return True
    # a street-suffix word plus a 4+ digit number -> an address line
    # ('Greater South Avenue 10001 New York U.S.A')
    if has_suffix and any(tk.strip(".,").isdigit() and len(tk.strip(".,")) >= 4
                          for tk in toks):
        return True
    return False


def _has_institution_hint(low):
    """SENDER_INSTITUTION_HINTS membership with word/phrase boundaries, so
    'plan' does not match inside 'exPLANation'. Uses the existing list -- it
    is not expanded here."""
    padded = f" {low} "
    for h in A.SENDER_INSTITUTION_HINTS:
        start = 0
        while True:
            idx = padded.find(h, start)
            if idx == -1:
                break
            before, after = padded[idx - 1], padded[idx + len(h)]
            if not before.isalnum() and not after.isalnum():
                return True
            start = idx + 1
    return False


def _is_numeric_line(text):
    t = text.strip().strip("$.,%#-")
    return bool(t) and all(c.isdigit() or c in " ./,-" for c in t) \
        and any(c.isdigit() for c in t)


def _is_field_label(text):
    t = text.strip()
    if ":" in t and len(t.split()) <= 4:
        return True
    return False


def is_plausible_name_line(text):
    """A line that could be the addressee's name: no digits, no ':', 1-5
    tokens, not a street / city-state-zip, and its word-set is disjoint from
    the existing _NON_NAME_WORDS (used, not expanded)."""
    t = A.name_core(text)
    if not t or ":" in t or any(c.isdigit() for c in t):
        return False
    if looks_like_street(t) or looks_like_city_state_zip(t):
        return False
    # 'and' / '&' are name connectors in a multi-person addressee
    # ('George and Christine E Murphy', 'JAMES & KAREN Q. HINDS')
    toks = [w for w in t.split() if w.lower().strip(".,") not in ("&", "and")]
    if not (2 <= len(toks) <= 5):   # a recipient is 'First Last', not one word
        return False
    words = {w.strip(".,&'").lower() for w in toks}
    if words & A._NON_NAME_WORDS:
        return False
    caps = sum(1 for w in toks if w[:1].isupper() or w.isupper())
    if caps < max(1, len(toks) - 1):
        return False
    return True


def _same_left(a, b, tol=60):
    return abs(S.x1(a) - S.x1(b)) <= tol


# --------------------------------------------------- address blocks

def detect_address_blocks(elements):
    mh = median_line_height(elements)
    # seed from every city/state/zip line, and from street lines not already
    # covered by a c/s/z seed (handles a block whose last line is the street,
    # e.g. 'Aaron Brown' / 'Greater South Avenue 10001 New York')
    csz = [e for e in elements if looks_like_city_state_zip(e["text"])]
    streets = [e for e in elements if looks_like_street(e["text"])
               and not looks_like_city_state_zip(e["text"])
               and ":" not in e["text"]]  # not 'Address: 1234 Main St ...'
    seeds = list(csz)
    for st in streets:
        if not any(_same_left(st, c) and 0 < S.y1(c) - S.y2(st) <= 3.0 * mh
                   for c in csz):
            seeds.append(st)

    def _aligned(a, b):
        return _same_left(a, b, 60) or abs(S.cx(a) - S.cx(b)) <= 90

    blocks = []
    seen_runs = []
    for anchor in seeds:
        col = S.x1(anchor)
        # walk downward too, to pull the c/s/z line under a street seed
        below = sorted([e for e in elements if S.cy(e) > S.cy(anchor) + 1
                        and _aligned(e, anchor)], key=S.cy)
        tail = [anchor]
        prev = anchor
        for e in below:
            if 0 <= S.y1(e) - S.y2(prev) <= 2.2 * mh and \
                    (looks_like_street(e["text"]) or looks_like_city_state_zip(e["text"])):
                tail.append(e)
                prev = e
            else:
                break
        above = sorted([e for e in elements if S.cy(e) < S.cy(anchor) - 1
                        and _aligned(e, anchor)],
                       key=S.cy, reverse=True)
        run = [anchor]
        prev = anchor
        for e in above:
            gap = S.y1(prev) - S.y2(e)
            if -2 <= gap <= 2.8 * mh:
                run.append(e)
                prev = e
            elif S.cy(e) < S.cy(prev) - 3.5 * mh:
                break
        run = list(reversed(run)) + tail[1:]  # top -> bottom
        key = (round(S.y1(run[0]) / 5), round(col / 5))
        if key in seen_runs:
            continue
        seen_runs.append(key)

        # classic mail block order is NAME / TITLE / ORG / STREET / CITY, so
        # the addressee is the TOP-most plausible-name line -- skipping any
        # leading label line ('Bill To:', 'Named Insured(s)', 'Mail To:').
        addr_idx = next((i for i, e in enumerate(run)
                         if looks_like_street(e["text"])
                         or looks_like_city_state_zip(e["text"])), len(run))
        name_line = None
        inst_above_name = False
        for e in run[:addr_idx]:
            tx = e["text"].strip()
            if tx.endswith(("(s)", "(s):", "(s).", ":")):
                continue  # a field label
            if _has_institution_hint(tx.lower()):
                inst_above_name = True
                continue
            if is_plausible_name_line(tx):
                name_line = e
                break
        blocks.append({
            "anchor": anchor,
            "name_line": name_line,
            "name": A.name_core(name_line["text"]) if name_line else None,
            "x_left": col,
            "y_top": S.y1(run[0]),
            "y_bot": S.y2(run[-1]),
            "n_lines": len(run),
            "has_street": any(looks_like_street(x["text"]) for x in run),
            "has_csz": any(looks_like_city_state_zip(x["text"]) for x in run),
            "inst_above_name": inst_above_name,
            "run_texts": [x["text"] for x in run],
        })
    return blocks


# --------------------------------------------------- recipient ladder
# Explicit decision order (no mixed scoring):
#   R1  labeled address block          (Bill To / Patient / Member / To ...)
#   R2  unlabeled complete block by position (name+street+csz, upper zone or
#       the only such block on the page)
#   R3  name repeated in two blocks    (letter body + payment coupon)
#   R4  name forming a partial block   (name directly above a street OR csz)
# Otherwise -> null. A bare name with no address structure is NEVER promoted
# (spec: 单独出现的名字不应轻易认定为 recipient) -- and never a lone
# dictionary word / 'CITY, STATE ZIP' / 'Document Number' / a table header.

_R_TIER_SCORE = {"R1": 0.95, "R2": 0.82, "R3": 0.88, "R4": 0.70}


def _name_addr_positions(b):
    """(name_idx, addr_idx) inside b['run_texts']: where the block's own
    name line sits, and where its first postal-address line sits."""
    rt = b["run_texts"]
    ni = 0
    if b.get("name_line") is not None:
        try:
            ni = rt.index(b["name_line"]["text"])
        except ValueError:
            ni = 0
    ai = next((i for i, t in enumerate(rt)
               if looks_like_street(t) or looks_like_city_state_zip(t)), len(rt))
    return ni, ai


def _addressee_block_ok(b, blocks):
    """Structural guard: is this address block plausibly a real ADDRESSEE
    block (name sitting on top of that person's own postal address), rather
    than a letterhead / remit-to payee / claim-info box / notice paragraph
    that merely contains a Title-Case line shaped like a two-word name?

    Position + block-shape only. No name lexicon, no per-image rule. A block
    carrying an explicit recipient label bypasses every check (handled by
    the caller -- R1).
    """
    rt = b["run_texts"]
    ni, ai = _name_addr_positions(b)
    prose_between = sum(1 for t in rt[ni + 1:ai] if len(t.split()) > 6)
    complete = b["has_street"] and b["has_csz"]
    named_others = [x for x in blocks if x is not b and x["name"]]
    complete_other = any(x["has_street"] and x["has_csz"]
                         for x in blocks if x is not b)

    # G1 -- the "name" is buried several non-address lines above the block's
    # own address, and the gap is filled with running prose: this is a notice
    # paragraph / label column, not an addressee block.
    if ai - ni >= 3 and prose_between >= 2:
        return False

    # G2 -- the line immediately above the name is a bare number line
    # (claim / account / policy id): a data box, not "Name / Street / City".
    if ni >= 1 and _is_numeric_line(rt[ni - 1]):
        return False

    # G3 -- the line right below the name is an institution line: the "name"
    # is line 1 of a stacked company letterhead (ORG / ORG / PO box).
    if ni + 1 < ai and _has_institution_hint(rt[ni + 1].lower()):
        return False

    # G4 -- block sits in the bottom payment-stub band and is either an
    # incomplete address or not the only addressee candidate: a remit-to /
    # tear-off coupon, not the letter's addressee. A lone complete block low
    # on the page (DMV / clinic tear-off with the real registrant) is kept.
    if b["y_top"] > 640 and (not complete or named_others):
        return False

    # G5 -- a city/state/zip line with no street, when a complete address
    # block exists elsewhere: a stray "City ST 12345" grid cell.
    if b["has_csz"] and not b["has_street"] and complete_other:
        return False

    # G6 -- an unlabeled "block" ten-plus lines tall whose name is NOT sitting
    # right on its address (or sits under an institution line): a notice /
    # account-summary column that a run of Title-Case labels was merged into,
    # not a mailing block. A tall block whose name is still directly above the
    # street (a long "billing questions" preamble) is left alone.
    if b["n_lines"] >= 10 and (ai - ni >= 2
                               or (ni >= 1
                                   and _has_institution_hint(rt[ni - 1].lower()))):
        return False

    # G7 -- top-of-page and the name sits below two-plus stacked header
    # lines, the one directly above it being an institution line: this is
    # the issuer's own letterhead / return address, not the addressee.
    if b["y_top"] < 140 and ni >= 2 and _has_institution_hint(rt[ni - 1].lower()):
        return False

    return True


def _recipient_label_above(elements, name_line, y_top, mh):
    for ae in elements:
        low = ae["text"].strip().lower()
        if not any(low.startswith(p.strip()) for p in A.RECIPIENT_ANCHORS):
            continue
        if len(ae["text"].split()) > 4:
            continue
        if _same_left(ae, name_line, tol=90) and \
           0 <= (y_top - S.y2(ae)) <= 3.2 * mh and S.cy(ae) < y_top:
            return ae["text"].strip()
    return None


def classify_recipient(elements):
    """Return tiered recipient candidates: list of {value, tier, evidence}."""
    mh = median_line_height(elements)
    blocks = detect_address_blocks(elements)
    named = [b for b in blocks if b["name"]]
    out = []

    for b in named:
        complete = b["has_street"] and b["has_csz"]
        label = _recipient_label_above(elements, b["name_line"], b["y_top"], mh)
        # structural guard: an unlabeled block that is not addressee-shaped
        # (letterhead / remit-to / claim box / notice paragraph) is dropped.
        if not label and not _addressee_block_ok(b, blocks):
            continue
        repeats = sum(1 for x in named
                      if x["name"].lower() == b["name"].lower()) >= 2
        # demote as a sender return address ONLY when a cleaner recipient
        # block exists elsewhere (a different name with no institution line
        # above it). On an insurance card the insured legitimately sits under
        # the insurer, with no competing person -> not a return address.
        cleaner_elsewhere = any(
            x["name"].lower() != b["name"].lower() and not x["inst_above_name"]
            for x in named)
        looks_return_addr = (b["inst_above_name"] and not label
                             and cleaner_elsewhere)

        if label and not looks_return_addr:
            tier, why = "R1", f"labeled block '{label}'"
        elif repeats:
            tier, why = "R3", "name repeats in a second address block (coupon)"
        elif complete and not looks_return_addr and (
                b["y_top"] < 360 or len([x for x in named if not (
                    x["inst_above_name"] and len(named) > 1)]) == 1):
            tier, why = "R2", "complete unlabeled block, recipient position"
        elif (b["has_street"] or b["has_csz"]) and not looks_return_addr:
            tier, why = "R4", "name above a partial address"
        else:
            continue
        out.append({"value": b["name"], "tier": tier, "y_top": b["y_top"],
                    "complete": complete,
                    "text": " / ".join(b["run_texts"]),
                    "evidence": [(why, _R_TIER_SCORE[tier]),
                                 (f"block: {' / '.join(b['run_texts'][:4])}", 0)]})

    # within a tier, prefer a complete block higher on the page
    out.sort(key=lambda c: (not c["complete"], c["y_top"]))
    return out


# --------------------------------------------------- letterhead / sender

def _sentence_like(text):
    t = text.strip()
    if len(t.split()) > 6:
        return True
    if t.endswith((".", "?", "!", ",")) or "?" in t:
        return True
    return False


def _cluster_top_band(elements, band_y=245, gap_mult=1.7, max_lines=3):
    mh = median_line_height(elements)
    band = sorted([e for e in elements if S.y1(e) < band_y],
                  key=lambda e: (S.y1(e), S.x1(e)))
    groups = []
    used = set()
    for i, e in enumerate(band):
        if id(e) in used:
            continue
        grp = [e]
        used.add(id(e))
        prev = e
        for f in band[i + 1:]:
            if id(f) in used or len(grp) >= max_lines:
                break
            gap = S.y1(f) - S.y2(prev)
            aligned = _same_left(f, prev, 70) or abs(S.cx(f) - S.cx(prev)) <= 90
            if not (0 <= gap <= gap_mult * mh and aligned):
                continue
            # a letterhead is stacked short labels, not running prose
            if _sentence_like(f["text"]) and not _sentence_like(prev["text"]):
                break
            grp.append(f)
            used.add(id(f))
            prev = f
        groups.append(grp)
    return groups, mh


def _is_centered(x1v, x2v, tol=0.14):
    left = x1v
    right = PAGE_W - x2v
    cx = (x1v + x2v) / 2.0
    return abs(cx - PAGE_W / 2) < 0.16 * PAGE_W and \
        abs(left - right) < tol * PAGE_W


def _has_date_content(text):
    if A.parse_date(text):
        return True
    toks = text.split()
    for j in range(len(toks)):
        for w in (1, 2, 3):
            if A.parse_date(" ".join(toks[j:j + w])):
                return True
    return False


def _digit_ratio(text):
    d = sum(c.isdigit() for c in text)
    return d / max(1, len(text))


def _is_banner_heading(grp, mh, has_hint, tagline_below):
    """A document-title banner, not a letterhead.

    - a wide single line spanning most of the column (fires even with a hint
      word inside it, e.g. 'Auto Insurance Declaration Page')
    - an ALL-CAPS short single line with no institution hint and no tagline
      under it ('EXPLANATION OF BENEFITS', 'OFFICIAL NOTICE')
    """
    if len(grp) != 1:
        return False
    e = grp[0]
    w = S.width(e)
    wc = len(e["text"].split())
    if w > 0.55 * PAGE_W and 2 <= wc <= 6:
        return True
    if has_hint:
        return False
    if e["text"].isupper() and 2 <= wc <= 6 and not tagline_below:
        return True
    return False


def detect_letterhead(elements):
    groups, mh = _cluster_top_band(elements)
    band_sorted = sorted([e for e in elements if S.y1(e) < 320], key=S.y1)
    out = []
    for grp in groups:
        # a letterhead may include the agency's own address lines -- keep the
        # group but name it from its non-address lines only
        kept = [g for g in grp if not looks_like_street(g["text"])
                and not looks_like_city_state_zip(g["text"])
                and not _is_numeric_line(g["text"])]
        if not kept:
            continue
        text = " ".join(g["text"].strip() for g in kept).strip()
        if len(text) < 3 or not any(c.isalpha() for c in text):
            continue
        if all(_is_field_label(g["text"]) for g in kept):
            continue  # a stack of 'Field:' labels is not a letterhead
        low = text.lower()
        # a 'Field: value' line does not become a sender just because a hint
        # word appears in it ('Group: ABCDE', 'Payee: ...')
        has_hint = _has_institution_hint(low) and not (
            _is_field_label(text) and len(kept) == 1)

        # reject rows that are really tabular / dated data, not a name
        if not has_hint and (_has_date_content(text) or _digit_ratio(text) > 0.15
                             or any(_is_numeric_line(g["text"]) for g in grp)):
            continue

        x_left = min(S.x1(g) for g in kept)
        x_right = max(S.x2(g) for g in kept)
        h_max = max(S.height(g) for g in kept)
        y_top = min(S.y1(g) for g in kept)

        # candidate gate. A sender is one of:
        #   - a known institution (existing hint list), anywhere it sits
        #   - a prominent single wordmark line in the very top strip
        #   - a centered, stacked multi-line letterhead block (gov notices)
        # A no-hint, left-aligned, multi-line merge is NOT a letterhead
        # (real ones carry a 'Company/Bank/Insurance/...' word) -> reject.
        prominent_wordmark = (len(kept) == 1 and y_top < 125
                              and h_max > 1.3 * mh)
        centered_block = len(kept) >= 2 and _is_centered(x_left, x_right)
        if not (has_hint or prominent_wordmark or centered_block):
            continue

        # is there a tagline directly under a single-line group?
        # (short title-case line, not a 'Field:' label -- 'An EDISON ... Company')
        tagline_below = False
        if len(kept) == 1:
            g0 = kept[0]
            for nb in band_sorted:
                if nb is g0 or S.y1(nb) <= S.y2(g0):
                    continue
                if S.y1(nb) - S.y2(g0) <= 5.0 * mh and _same_left(nb, g0, 100):
                    txt = nb["text"].strip()
                    tagline_below = (not _is_field_label(txt)
                                     and 1 <= len(txt.split()) <= 5
                                     and not txt.isupper())
                    break

        ev = []
        score = 0.30
        ev.append(("top_band_text", 0.30))

        if h_max > 1.15 * mh:
            add = round(min(0.30, (h_max / mh - 1.0) * 0.5), 3)
            score += add
            ev.append((f"large_glyph_height ({h_max:.0f} vs mh {mh:.0f})", add))

        if x_left < 300:
            score += 0.25
            ev.append(("top-left letterhead position (x<300)", 0.25))
        elif len(kept) >= 2 and _is_centered(x_left, x_right):
            score += 0.15
            ev.append(("centered stacked letterhead block", 0.15))

        if len(kept) >= 2:
            score += 0.15
            ev.append((f"multi_line_letterhead_block (x{len(kept)})", 0.15))

        if has_hint:
            score += 0.40
            ev.append(("institution_hint_word (existing list)", 0.40))

        if _is_field_label(text) and len(kept) == 1:
            score -= 0.40
            ev.append(("field_label ('X: value')", -0.40))

        if _is_banner_heading(kept, mh, has_hint, tagline_below):
            pen = -0.55 if (S.width(kept[0]) > 0.55 * PAGE_W) else -0.85
            score += pen
            ev.append(("document-title banner (not a letterhead)", pen))

        # person-name-shaped text at the top is a signatory, not the issuer
        # (skip when a real institution word is present, e.g. 'IRS')
        if not has_hint and (A.looks_like_person_name(text)
                             or A.looks_like_person_name(kept[0]["text"])):
            score -= 0.35
            ev.append(("person_name_shape (signatory, not sender)", -0.35))

        out.append({"value": text, "score": round(score, 3),
                    "has_hint": has_hint, "y_top": y_top,
                    "bbox": [x_left, y_top, x_right,
                             max(S.y2(g) for g in kept)],
                    "evidence": ev})
    out.sort(key=lambda c: c["score"], reverse=True)
    return out


# --------------------------------------------------- sender ladder
# Explicit decision order (no mixed scoring):
#   S1  top letterhead / logo -- prominent text in the top strip, visually
#       separated from the body. If any S1 candidate carries an institution
#       word, S1 is restricted to those ('FARMERS INSURANCE' over a bare
#       'Policygenius' wordmark). Body-text org names never override S1.
#   S2  sender anchor -- 'From / Issued By / Sent By / Customer Service /
#       Remit To / Make checks payable to' + the org beside/after it
#   S3  institution-shaped name by position -- short, upper region, not a
#       title / field label / table header / person name / city-state
# Otherwise -> null.

_S_TIER_SCORE = {"S1": 0.95, "S2": 0.75, "S3": 0.55}
_S1_BAR = 0.55


def classify_sender(elements):
    mh = median_line_height(elements)
    lh = detect_letterhead(elements)

    # S1
    s1 = [c for c in lh if c["score"] >= _S1_BAR]
    if s1:
        if any(c["has_hint"] for c in s1):
            s1 = [c for c in s1 if c["has_hint"]]
        best = max(s1, key=lambda c: c["score"])
        return [{"value": best["value"], "tier": "S1", "evidence": best["evidence"]}]

    # S2 -- an org named on the same row / just after a sender anchor
    anchor_els = [e for e in elements
                  if any(e["text"].strip().lower().startswith(p.strip())
                         for p in A.SENDER_ANCHORS)]
    for ae in anchor_els:
        for e in elements:
            if e is ae:
                continue
            same = S.same_row(ae, e) and S.cx(e) > S.cx(ae)
            below = S.is_below(e, ae) and S.vertical_gap(ae, e) <= 2.0 * mh
            if (same or below) and _has_institution_hint(e["text"].lower()) \
                    and not _is_field_label(e["text"]):
                return [{"value": e["text"].strip(), "tier": "S2",
                         "evidence": [(f"named after sender anchor '{ae['text'].strip()}'",
                                       _S_TIER_SCORE["S2"])]}]

    # S3 -- best institution-shaped short line: prefer the upper region, but
    # a name that repeats (letterhead lost to OCR, issuer only in the coupon)
    # also qualifies. Still excludes titles / labels / names / city-state.
    counts = {}
    for e in elements:
        counts[e["text"].strip().lower()] = counts.get(e["text"].strip().lower(), 0) + 1
    s3 = []
    for e in elements:
        t = e["text"].strip()
        low = t.lower()
        if not _has_institution_hint(low) or len(t.split()) > 5:
            continue
        if _is_field_label(t) or ":" in t or _sentence_like(t) \
                or A.looks_like_person_name(t) or looks_like_city_state_zip(t):
            continue
        near_top = S.y1(e) <= 360
        repeats = counts[low] >= 2
        if not (near_top or repeats):
            continue
        rank = S.y1(e) - S.height(e) * 2 - (200 if repeats else 0)
        s3.append((rank, t))
    if s3:
        s3.sort()
        return [{"value": s3[0][1], "tier": "S3",
                 "evidence": [("institution-shaped line (upper region or repeated)",
                               _S_TIER_SCORE["S3"])]}]
    return []
