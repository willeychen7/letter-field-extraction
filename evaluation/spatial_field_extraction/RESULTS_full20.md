# Full 20-image benchmark — FROZEN Stage-1 pipeline

Run 2026-09-05 · pipeline frozen after 6-image calibration · **no rule / anchor /
threshold change** · `run_full20.py --use-cache` · OCR = `spotting_hunyuan`, temp 0,
max_tokens 8192.

## 1. Overall accuracy (frozen)

| scope | accuracy |
|---|---|
| **All 20 images × 6 fields** | **0.783 (94/120)** |
| Authoritative-GT subset (11 imgs × sender/amount/due/payment) | **0.909 (40/44)** |
| 6-image calibration set (reference) | 1.000 — optimistic, tuned on itself |

## 2. Per-field accuracy

| field | all 20 | authoritative GT | derived GT |
|---|---|---|---|
| sender | 0.75 (15/20) | 0.91 (n=11) | 0.56 (n=9) |
| recipient | **0.55 (11/20)** | 0.64 (n=11) | 0.44 (n=9) |
| total_amount | **0.95 (19/20)** | 1.00 (n=11) | 0.89 (n=9) |
| payment_status | 0.75 (15/20) | 0.82 (n=11) | 0.67 (n=9) |
| due_date | 0.90 (18/20) | 0.91 (n=11) | 0.89 (n=9) |
| action | 0.80 (16/20) | 1.00 (n=11) | 0.56 (n=9) |

Answer taxonomy over 120 slots: 67 correct · 27 both-null-correct · 13 null-miss ·
7 wrong · 6 null-hallucination.

## 3. Hallucination rate

- **6 / 120 = 5.0 %** raw null-hallucination (GT null, pipeline emitted a non-null
  value not in the accept-set).
- Strict (only GT-null slots with no `None` in accept): **1 / 17 = 5.9 %**.
- The 6 events: 3 recipient = placeholder/header text read as a name
  (`CITY, STATE ZIP`, `Document Number: XXXXXXXXX`, `Meter Reading`), 1 sender =
  page title (`EXPLANATION OF BENEFITS`), 1 sender = table label (`Purchases`),
  1 action = `"pay"` triggered by the string *"amount due"* inside
  *"your bill with the amount due will be mailed separately"*.
- **No hallucinated amount and no hallucinated date** anywhere in 20 images.

## 4. `finish=length` (OCR truncation)

3 images hit the 8192-token cap: **SoCalGas · Great_American_Insurance_Invoice ·
DMV_Registration** (also the 3 slowest: 107–126 s; DMV_Registration emitted 340
elements). One more, **SCE_Sample_Bill**, returned `finish=stop` but
under-generated — it skipped the payment stub, so `Amount due by 05/11/20` never
reached the extractor (a 2nd truncation-like failure that the `finish_reason`
flag does not catch).

Impact: 5 of the 26 errors are on the 3 truncated images, and they are the
worst ones — **recipient 0/3 and 2 of the 7 `wrong` (not just null)** come from
truncation. Removing the 3 images barely moves the headline (0.783 → 0.794) but
removes most of the severe misses. total_amount and due_date still scored 3/3
and 3/3 on the truncated images — the tail that gets cut is letterhead /
addressee / payment-stub, not the mid-page amount.

## 5. Authoritative vs Derived GT

| | overall | sender | recipient | amount | payment | due | action |
|---|---|---|---|---|---|---|---|
| Authoritative (11 imgs) | **0.86 (57/66)** | 0.91 | 0.64 | 1.00 | 0.82 | 0.91 | 1.00 |
| Derived (9 imgs) | **0.69 (37/54)** | 0.56 | 0.44 | 0.89 | 0.67 | 0.89 | 0.56 |

The derived set is skewed hard: it contains the 2 student-handout "bills"
(Water_Bill2, Bank_Bill_Due), 2 "THIS IS NOT A BILL" documents (Auto_Insurance,
CMS_EOB), an insurance card (All_State), and 2 of the 3 truncated images. The
authoritative number (0.86, or 0.909 on the 4 core fields) is the more
trustworthy read of real-bill performance.

## 6. Errors by root cause (26 total)

| cause | count | which |
|---|---|---|
| **A. Sender/Recipient position-structure** | **~13** | recipient with a real name present but no anchor and outside the hard-coded upper-left zone (AAA `PAT SMITH`, hoag `JANE DOE`, Auto_Insurance `Jack Smith`); name filter rejects/accepts wrongly (`George and Christine E Murphy` killed by stop-word "and"; `Meter Reading`, `Document Number: XXX`, `CITY, STATE ZIP` accepted as names); sender = page title beats the real issuer (Auto_Insurance `Auto Insurance Declaration Page`, CMS_EOB `EXPLANATION OF BENEFITS`); sender keyword list misfires (DMV_Notice picks `DIRECTOR OF CUSTOMER COMPLIANCE SERVICES` on the "…SERVICES" hint) |
| **B. OCR not read / not complete** | **~6** | 3 × `finish=length` truncation (SoCalGas, Great_American, DMV_Registration → recipient/payment/action/sender); SCE_Sample_Bill payment-stub not generated (`due_date` miss); DMV_Notice `$83.50` only appears glued inside a full sentence, never as its own bbox |
| **C. Anchor not found** | **~4** | AAA_insurance bare `"Due Apr 8 2020"` label + `"no later than <date>"` not in `DUE_DATE_ANCHORS`; AAA_insurance / DMV_Notice `action` — `"has to be paid"`, `"we must RECEIVE"`, payment-coupon layout carry no `"please pay"`-style imperative |
| **D. Anchor false-positive** | 1 | Auto_Insurance `action = "pay"` from *"amount due"* inside a "this is NOT a bill" sentence |
| **E. Other — conservative null on marker-less not-a-bill** | 4 | `payment_status = None` where GT = `not_applicable`, because there is no amount **and** no literal "THIS IS NOT A BILL" string (SCE_Letter, Water_Bill2, All_State card, DMV_Notice-cascade) |
| **D-spatial. Spatial relation computed wrong** | **0** | no confirmed case — every proximity/row/column decision that fired was geometrically correct |

## Reading for the next step

- **`total_amount` (0.95) and `due_date` (0.90) are solid frozen** — the
  anchor→geometry mechanism works for the two fields Decision 01 cares about.
  Their few misses are OCR-completeness (B), not logic.
- **`recipient` (0.55) is the weak field, and the cause is unambiguous:** it is
  category **A / E**, position-structure and name-recognition — *not* anchor
  recall (only AAA's date and the action phrasings are true anchor gaps) and
  *not* spatial-math errors (category D-spatial = 0). Sender's derived-set drop
  is the same disease (title-vs-issuer, keyword misfire).
- Truncation is real but concentrated and detectable — 3 named images, all
  large/dense; worth fixing before any further judgement of those document
  classes.

Per your routing rule: **Sender/Recipient is where the errors are → the
indicated next step is Position/Structure, not Semantic Similarity.** Anchor
recall gaps exist but are small (≈4 slots) and would not be the highest-value
fix. No changes made pending your decision.
