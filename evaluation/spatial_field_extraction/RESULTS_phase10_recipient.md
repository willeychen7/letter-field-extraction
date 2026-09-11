# Phase 10 — Recipient Error Analysis

Analysis only. No Phase 3–8 code, no frozen snapshot, no Hunyuan prompt,
no new benchmark touched. Source: `results/phase9/summary.json` (live-OCR
E2E, 49 images) + the per-image `results/phase9/raw/*.ocr.json`, replayed
through `structure.detect_address_blocks` for diagnosis.

**Recipient: 34/49 correct = 69.4 %. 15 errors.**

Severity of the 15:

| kind | n | meaning |
|---|---:|---|
| **hallucination** (GT = null, pipeline emitted a name) | **5** | worst — a fake recipient shown to the reader |
| **wrong name** (GT has a name, pipeline emitted a different one) | **4** | also dangerous |
| null-miss (GT has a name, pipeline said null) | 6 | safe — fails as "看不准" |

→ **9 of 15 errors are the pipeline emitting a WRONG name.** All 9 come
from one mechanism.

---

## Every recipient error

| # | image | pred recipient | GT recipient | OCR: was the real name read? | cause class |
|---|---|---|---|---|---|
| 1 | `water_bill` | `VENTURA RIVER` | `null` (placeholder "John Smith") | issuer letterhead + a placeholder `John Smith` block both present | **C3** issuer letterhead as recipient |
| 2 | `att_bill` | `AT&T MOBILITY` | `null` / `tech group…` | payee "AT&T MOBILITY / PO Box…" block; real holder "TECH GROUP…" block has name=`None` | **C3** payee remit-to as recipient |
| 3 | `Chase_Bank_Bill_Example2` | `Ohio/West Virginia Markets` | `null` | inside the bank's own return-address block (`CHASE / JPMorgan… / Ohio/West Virginia Markets / P O Box…`) | **C3** bank return-address region label as name |
| 4 | `Progressive_Insurance_Bill` | `Inspection Site` | `null` / `john smith` | block = `Claim Number / 99-… / Inspection Site / Not Available` | **C1** form-label line taken as the name |
| 5 | `HOA1` | `Automatic Withdrawal` | `null` | block = `Payment Option #1 - / Automatic Withdrawal / …` (coupon) | **C1** coupon phrase taken as the name |
| 6 | `Penny_Insurance_Bill` | `Vehicle Location` | `Penny the Pig` | **YES** `Penny the Pig` @ (87,242). Correct block detected but **name = `None`** (top line `Date Issued: November`); garbage block `Vehicle Location / Los Angeles CA` won | **C1 + C4** correct block name lost → garbage block wins |
| 7 | `Medixare_Premium_Bill` | `Coverage Termination Dates` | `CHARLIE MEDICARE` | **YES** `CHARLIE MEDICARE` @ (558,145). Correct block detected but **name = `None`** (top line = mail barcode `E4955-DEB-0112589-T01997`); garbage block won | **C1 + C4** barcode first line → name lost → garbage wins |
| 8 | `statefarm_bill` | `LINDA DESPAIN CLU, CHFC` | `SMITH, BRENDA` | **YES** `SMITH, BRENDA` @ (73,112). Real block not formed as named; agent-info block got the name | **C1 + C4** agent name taken instead of the insured |
| 9 | `UCLA_Health_Bill2` | `FINANCIALLY RESPONSIBLE` | `John Q. Patient` | **YES** `John Q. Patient` @ (278,289). Block `HOSPITAL SERVICES / QUESTIONS? / Please contact us…` got name `FINANCIALLY RESPONSIBLE` | **C1 + C4** section-heading label taken as the name |
| 10 | `UCLA_Health_Bill` | `null` | `John Q. Patient` | **YES** `John Q. Patient` @ (311,292), inside a form area, no street+city/state/zip below it → no block formed | **C2** name present, no address block |
| 11 | `State_Farm_Insurance_Card` | `null` | `JANET SMITH` | **YES** `JANET SMITH` @ (211,426), inline `INSURED JANET SMITH`, **no postal address on the card** → 0 blocks | **C2** inline name, no address block |
| 12 | `Coverage_Care_Insurance_Card` | `null` | `Jane Doe` | **YES** `Member Name: Jane Doe` @ (70,332), health-plan card, no address → 0 blocks | **C2** inline name, no address block |
| 13 | `First_Bank_Bill` | `null` | `Jack Smith` | **YES** `Mr. Jack Smith` @ (63,161), next to the bank address but no street+zip triple in its column → no block | **C2** name present, no address block |
| 14 | `HOA4` | `null` | `Jane Smith` | **YES** `Billed To: Jane Smith` @ (64,857), in the payment coupon, no address block there | **C2** name present (coupon), no address block |
| 15 | `State_Farm_Insurance` | `null` | `SHEMARIA, ALFRED I & DEANNA` | OCR misread `&` → `8`: `SHEMARIA, ALFRED I 8 DEANNA` @ (126,112). `is_plausible_name_line` rejects it (contains a digit) → block name = `None` | **C5** OCR glyph error breaks the name check |

---

## Counts by cause

| class | what it is | n | % of 15 | emits a wrong name? |
|---|---|---:|---:|---|
| **C1** | **地址块选错行 / 姓名行取到 label** — a form label, coupon phrase, section heading or barcode line becomes the block's `name` | **6** | **40 %** | yes (6/6) |
| **C2** | **没有检测到 recipient** — name IS in the OCR but no address block forms (inline names on ID cards; form-layout bills where the name isn't above a street+city/state/zip) → returns `null` | **5** | 33 % | no — safe null |
| **C3** | **issuer / payee / letterhead as recipient** — the sender's letterhead, a "remit to" payee, or a bank return-address region label is picked | **3** | 20 % | yes (3/3) |
| **C4** | **Position-Structure 判断错误** — not standalone; it is the *second half* of C1's 4 worst cases (Penny, Medixare, statefarm_bill, UCLA2): the correct block IS found, its `name` comes out `None` (label/barcode first line), so a garbage block with a 2-word-cap phrase outranks it | (4, inside C1) | — | yes |
| **C5** | **OCR 本身导致** — `&`→`8` glyph error trips the digit check | **1** | 7 % | no — safe null |
| **C6** | other | **0** | — | — |

**C1 + C3 = 9 / 15 = 60 % of recipient errors, and 100 % of the
dangerous ones** (all 5 hallucinations + all 4 wrong names).

---

## Which pattern hurts the 69 % most

**One mechanism dominates: `structure.py` accepting a non-name line as a
block's `name`.**

It shows up two ways, both in `structure.detect_address_blocks` /
`_name_line` selection:

1. **The correct block is detected but its `name` is `None`** because the
   first line(s) are a label or barcode (`Date Issued:`, `E4955-DEB-…`,
   `Claim Number`) and the name-line skip stops too early → then a
   *competing* block whose middle line looks like a 2-word Title-Case
   name (`Vehicle Location`, `Coverage Termination Dates`, `Inspection
   Site`, `Automatic Withdrawal`, `Ohio/West Virginia Markets`) wins.
   → Penny, Medixare, Progressive, HOA1, Chase2, UCLA2, statefarm_bill.
2. **No positional guard** — a block in a payment-coupon / policy-info /
   letterhead region is treated the same as one in the classic
   upper-left addressee zone. → water_bill (letterhead), att_bill
   (payee), and reinforces #1.

C2 (5 errors) is real but **fails safely** (`null` = "看不准") and is a
recall problem for a different layout family (ID cards, form bills) — a
separate, lower-priority fix.

C5 (1) is a one-off OCR glyph.

---

## Conclusion

**Recipient 69 %  →  largest error source  →  next module to change**

- **Largest error source (60 % of errors, 100 % of the wrong/hallucinated
  outputs): `structure.py` name-line selection + block scoring** picks a
  form label / coupon phrase / section heading / barcode-topped block /
  issuer letterhead / payee address as the recipient name.
- **The single most valuable fix:** in `structure.detect_address_blocks`,
  when a block's `name` resolves to `None` because its leading lines are
  labels/barcodes, keep scanning down to the real name line; and add a
  positional guard so a block sitting in a payment-coupon / policy-info /
  letterhead region cannot be chosen as the recipient over one in the
  addressee zone. This alone addresses 9 of the 15 errors and removes
  every hallucinated recipient.
- C2 (inline names on ID / form-layout docs → `null`) is the next tier,
  but it fails safely and needs a different approach (an inline
  "INSURED / Member Name / Billed To: <name>" reader), so it is priority 2.

Module to change next: **`evaluation/spatial_field_extraction/structure.py`**
— specifically address-block `name` resolution and block selection.
(Not done here — Phase 10 is analysis only.)

---

## Fix result (implemented after this analysis)

One change, in `structure.py::classify_recipient` only: an unlabeled address
block is dropped unless it is *addressee-shaped* (`_addressee_block_ok` —
7 position / block-shape guards: buried name, numeric line above the name,
institution line below the name, bottom payment-stub band, stray
city/state/zip cell, 10+-line notice column, top-of-page letterhead stack).
No change to `detect_address_blocks` name parsing, no vocabulary / regex
expansion, no semantic similarity, Phase 4–8 and the OCR prompt untouched.
Regression-verified with `run_phase9.py --score` (49 live-OCR letters).

| metric | before | after |
|---|---|---|
| **Recipient accuracy** | 69.4 % (15 err) | **81.6 % (9 err)** |
| **Overall E2E** | 82.4 % (300/364) | **84.1 % (306/364)** |
| Recipient hallucinations + wrong names | 5 + 4 | **0 + 0** |

- **C1 → 0.** No form label / coupon phrase / section heading / barcode-topped
  block is emitted as a recipient any more (Progressive, HOA1, Penny,
  Medixare, statefarm_bill, UCLA_Health_Bill2).
- **C3 → 0.** No issuer letterhead / remit-to payee / bank return-address
  region label is emitted (water_bill, att_bill, Chase_Bank_Bill_Example2).
- **Recipient remaining 9 errors are ALL C2 `null_miss`** (name is in the
  OCR but no address block forms — ID cards, form-layout bills): UCLA_Health_Bill,
  UCLA_Health_Bill2, State_Farm_Insurance_Card, Coverage_Care_Insurance_Card,
  State_Farm_Insurance, statefarm_bill, Medixare_Premium_Bill, First_Bank_Bill,
  HOA4. Every recipient output is now either correct or `null` — **no new
  false-positive recipient.**
- **No regression in any other field:** Sender 0.796, Total Amount 0.898,
  Payment Status 0.857, Due Date 0.816, Action 0.878, Domain 0.837 — all
  unchanged from the pre-fix baseline.

Phase 3 re-frozen with this change: `frozen_phase3/structure.py`
(SHA-256 in `frozen_phase3/CHECKSUMS`).
