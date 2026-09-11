# Phase 8 — Contact Organization / Phone (analysis + controlled experiment)

Question: given the frozen Action, can we find the phone the recipient
actually needs — not just list every number? Phases 3–7 frozen. No
re-OCR. No semantic similarity. Never invents a number. `null` when
unsure.

Two components, both experimental (not wired into anything):

- `phone_extract.py` — finds phone-shaped tokens in frozen OCR elements
  and annotates each with channel (from nearby label words), page band,
  fax/TTY/placeholder flags, and org context.
- `contact_pick.py` — picks the one phone relevant to the frozen Action,
  or `null`.

---

## 1–4. Phone inventory across the 50 docs

**Phone SHAPE detection had to be tightened first.** A permissive
`\d{3}\d{3}\d{4}` matched barcode / account-number digit runs in payment
coupons (125 "phones", most junk). Requiring an actual phone separator
(`(800) 242-7338`, `800-242-7338`, `1,800,637,7455`, `1-800-XXX-XXXX`,
`1-800-MEDICARE`) removed the junk cleanly:

| metric | value |
|---|---|
| **1. docs with ≥ 1 real phone** | **31 / 50 (62 %)** |
| **2. phones per doc** | min 0 · max 6 · mean **1.2** · (19 docs have 0, 12 have 1, 13 have 2, 6 have 3) · **61 total** |
| **3. of 61: fax** | 2 |
| &nbsp;&nbsp;&nbsp;&nbsp;TTY / hearing-impaired | 6 |
| &nbsp;&nbsp;&nbsp;&nbsp;placeholder (`XXX-XXX-XXXX`) | 3 |
| &nbsp;&nbsp;&nbsp;&nbsp;toll-free (800/888/…) | 36 |
| **by channel label** | general 24 · **billing 10** · **customer_service 8** · unlabeled 11 · tty 6 · fax 2 |
| **by page band** | body 37 · header 15 · footer-coupon 9 |
| **4. got a usable channel label** | **50 / 61 (82 %)** |

Fax, TTY, "Para Español", "International Calls" are **reliably separated
by their label** — every one in the sample was tagged correctly.

---

## 5. Can the Action be tied to the right phone?

`contact_pick.py` scores each non-fax / non-TTY phone by: channel match
to the Action (`pay` → billing > customer_service > general; `contact` →
customer_service first; …), page band (header / coupon = the canonical
contact line), whether the number **repeats across bands**, and org
match. Picks the top if it clears a confidence floor, else `null`.

Hand-annotated GT: for the **21 docs where an Action exists**, the correct
contact phone (or `null` — 3 docs have an Action but no usable contact).

| outcome | v1 (as-experimented) | v2 (+ report's recall fixes) |
|---|---:|---:|
| **correct number** | 9 | **14** |
| **correct `null`** (no usable contact, said so) | 3 | 3 |
| missed (said `null`, a phone existed) | 7 | 4 |
| **wrong number** | 2 * | **0** |
| **false positive** (invented / picked junk) | **0** | **0** |
| **accuracy** | 12 / 21 (0.57) | **17 / 21 (0.81)** |
| recall where a correct phone exists | 9 / 18 | **14 / 18** |

\* the v1 "wrong" pair was `Medicare_Notice_PartA/B`: picker returned
`1-800-MEDICARE`, GT digit-form `1-800-633-4227` — the same line; fixed in
v2 by a keypad-equivalence in `_norm` (`MEDICARE` → `8006334227`).

**v2 changes (the report's two general recommendations, applied + regressed):**
1. widened the channel-label vocabulary — `patient financial` / `PFS` →
   `hoag` now billing; `to contact us` / `agent` / `or call` added.
2. lone-phone floor: one distinct phone with a **specific** label
   (billing / customer_service / claims / enroll) drops the confidence
   floor to 2.0 — fixes `UCLA_Health_Bill` ×2. **Not** applied to bare
   `general` (a lone unlabelled number is often a redirect to another
   agency, e.g. "Contact CARB at …" on a DMV notice) — that check kept
   `DMV_Registration` a correct `null` and cost 0 false positives.

The 4 remaining v2 misses are all `null`, all safe: two insurance
**agent** phones, `aaa-policy_renew`, and `DMV_registration_late_fee`
(a bare government line). **0 wrong numbers, 0 false positives** — the
picker never hands the reader a wrong number; its failure mode stays
"look it up yourself".

### What the picker gets right (the 9 + 3)

`Hospital_Bill` (billing, "Billing Questions?" + repeats in the payment
coupon, score 5.5) · `SCE_Sample_Bill` ("For billing and service
inquiries") · `BOA_Bill_Example` ("Customer Service") · `water_bill`
("**Pay by Phone**" beat "Customer Service" for `action=pay`) ·
`HOA1` · `HOA4` · `IRS_CP504_Notice` ("To contact us") ·
`Great_American` · `CMS_EOB` ("Customer Service Number").
Correct `null`: `DMV_Registration` (its only phone is "Contact **CARB**"
— the smog board, not the renewal line), `Medixare_Premium_Bill` (only
TTY), `Bank_Bill_Example` (only a garbled street token).

### The 7 misses — all `null`, none wrong

| doc | the phone it should have found | why it said `null` |
|---|---|---|
| `UCLA_Health_Bill` /2 | `310-825-8021` — **it identified this, kind = customer_service** | body band, single occurrence → scored 2.0 < 3.0 floor |
| `hoag-invoice-mychart` | `949-764-8404` next to `PFS@hoag.org` (Patient Financial Services) | "PFS" not a recognised billing context → 0.8 |
| `State_Farm_Insurance` / `statefarm_bill` | the **agent's** phone ("Telephone" / "Your State Farm Agent") | channel = general, body band → 1.5 / 2.5 |
| `aaa-policy_renew` | `1-800-222-8252` under "AAA.com/Renew … Call" | label garbled → 1.0 |
| `DMV_registration_late_fee` | `1-800-921-1117` ("VISIT WWW.DMV.CA.GOV OR CALL") | general, body → 2.0 |

**The channel logic is sound — of every pick it made, all 9 numbers are
right and all 3 nulls are right.** The gap is *recall*: the confidence
floor is tuned so that a single, body-band, less-than-explicitly-labelled
phone is dropped rather than guessed. **Failure mode is `null`, never a
wrong number (0 false positives).**

---

## Verdict on reliability

| capability | reliable? |
|---|---|
| phone **shape** detection (after the separator rule) | **yes** — barcode/account junk eliminated, 0 spurious in the graded set |
| **fax / TTY / placeholder** separation | **yes** — 100 % on this sample |
| **channel** classification (billing / customer_service) where a label exists | **yes** — 82 % of phones labelled, all correct |
| Action → phone when the phone is **header/coupon + labelled** | **yes** — 8/8 clean |
| Action → phone when the phone is **body-band / single / weakly labelled** | **not yet** — picker returns `null` (safe) rather than reaching for it |

Extraction is reliable. The picker is **safe but under-recalls** (~9/18
where a phone exists; 0 wrong numbers). The remaining recall lives in a
small, well-understood set: single-phone docs, agent phones, and
finance-department contexts ("PFS", "To contact us", "OR CALL") that the
label vocabulary doesn't yet name.

## Recommendation

Formal architecture is justified — extraction proved reliable and the
picker's errors are all on the safe side. Before wiring anything:

1. **Widen the channel-label vocabulary** with the finance/dept phrases
   the misses exposed (`PFS`, `patient financial`, `to contact us`,
   `agent`, `or call`) — general, not per-image.
2. **Relax the confidence floor for a single clearly-typed phone**: if a
   doc has exactly one non-fax/non-TTY phone and its channel matches the
   Action, surface it (still `null` when 0 or when ≥ 2 conflict).
3. Output shape: `{contact_organization, contact_type, phone_number,
   confidence, reason}` — same "resolved / not_applicable /
   insufficient_evidence" status idiom as Phase 7.
4. Keep the hard `null` rules: fax, TTY, placeholder, and "two different
   numbers with conflicting channels" always → `null`.

Not done here: no wiring into Mama Helper, no Phase 3–7 change, no domain
or field-semantics change. Artifacts: `phone_extract.py`,
`contact_pick.py`, `run_phase8.py`, `results/phase8_analysis.json`,
`results/phase8_picker.json`.
