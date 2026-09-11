# Holdout test — frozen Phase 3 on 30 fresh letters

Run 2026-09-05 · pipeline = frozen Phase 3 (`frozen_phase3/`, unchanged) ·
30 US letters that never touched Phase 1–3 tuning · GT built from each
document's text **before** scoring.

Coverage: utility 4 · medical 3 · insurance 7 · DMV 2 · Medicare 3 ·
bank 6 · HOA 4 · general 1. (No fresh IRS — only PDF originals exist; no
fresh electric bill — all SCE/SoCalGas were in the dev set.)
OCR: **0 truncated** (all `finish=stop`).

## Headline

| | dev benchmark (20) | **holdout (30)** |
|---|---:|---:|
| **overall** | **0.892** (107/120) | **0.711 (128/180)** |
| overall, if ~10 debatable GT calls flip | — | ~0.767 (138/180) |

**89.2 % did not hold.** True-holdout accuracy is **71 %**, ~77 % under the
most generous reading of the borderline GT. A 12–18 point drop.

## Per field

| field | dev | holdout | Δ |
|---|---:|---:|---:|
| sender | 0.95 | **0.70** (21/30) | −0.25 |
| recipient | 1.00 | **0.57** (17/30) | −0.43 |
| total_amount | 0.95 | **0.67** (20/30) | −0.28 |
| payment_status | 0.75 | **0.63** (19/30) | −0.12 |
| due_date | 0.90 | **0.77** (23/30) | −0.13 |
| action | 0.80 | **0.93** (28/30) | +0.13 |

**action and due_date (anchor-driven) transferred. sender and recipient
(structure-driven) did not.**

## Per category

| category | acc | | category | acc |
|---|---:|---|---|---:|
| dmv | 0.83 (10/12) | | hoa | 0.75 (18/24) |
| medicare | 0.78 (14/18) | | bank | 0.69 (25/36) |
| insurance | 0.71 (30/42) | | medical | 0.67 (12/18) |
| utility | 0.63 (15/24) | | general | 0.67 (4/6) |

## Why it dropped — the 52 errors, three roughly-equal causes

### 1. Genuine overfit to the 20 dev images (~1/3)

Thresholds and the sender title/header-exclusion patterns were calibrated
by looking at those 20. New phrasings slip through:

- `sender` = a document title/heading, not the issuer:
  `Membership Renewal Notice` (aaa), `Financial Statement`
  (EastWest_Bank_Form), `Real Estate HOA Dues Statement` (HOA2),
  `HOA DUES INVOICE` (HOA3), `GEORGIA INSURANCE POLICY INFORMATION CARD`
  (State_Farm_Card), `QUESTIONS? Please contact us…` (UCLA_Bill2). The
  banner rule only catches ALL-CAPS or column-spanning lines; **Title-Case
  headings leak**.
- `recipient` block picks the wrong line: `FINANCIALLY RESPONSIBLE` (UCLA),
  `LINDA DESPAIN CLU, CHFC` — the agent, not the insured (statefarm_bill),
  `Vehicle Location` (Penny), `Coverage Termination Dates` (Medixare).
- `total_amount` = `TOTAL CURRENT CHARGES $13,857` over the true
  `$472.00` balance due (UCLA_Health_Bill) — the same charges-vs-balance
  trap the dev set's Hospital_Bill passed, failing on a new layout.

### 2. Document categories the dev set never contained (~1/3)

- **Plain bank checking / savings statements** (Chase ×2, First Bank,
  EastWest_Bank_Bill) — 8 errors. A statement has a big balance and no
  literal "THIS IS NOT A BILL", so `decide_payment_status` returns
  **`unpaid`** and `total_amount` grabs the **Ending Balance**
  (`$14,824.76`, `$27,584.38`, `$125,883.63`). The pipeline has **no way
  to tell a statement from a bill**. The dev set's only bank doc was a
  credit-card bill (money genuinely owed).
- **Insurance ID cards with an inline name** — `INSURED JANET SMITH`,
  `Member Name: Jane Doe`. No postal address block → recipient ladder
  (R1–R4 all need a block; R5 was removed) returns `null`. The dev card
  (All_State) happened to have a full address block.
- **Template / placeholder forms** — `[Your Name]`, `Company Name`,
  `Customer Name`, blank `Dear ___`. Mostly handled (→ `null`), a few
  leak a header as a name.

### 3. GT noise on the holdout (~1/3)

Holdout GT is "derived" (annotated fast from OCR); only 3 images have
authoritative GT. Debatable calls scored as errors:

- `payment_status`: autopay bills — I marked `paid` (water_bill,
  statefarm_bill), pipeline said `not_applicable` / `unpaid`. Both
  defensible.
- `aws_invoice` `total_amount` `136.38` vs `135.38` — the invoice prints
  both; `due_date` `2010-09-03` = the "Payment Date" line (I marked
  `null`).
- `Medixare` `due_date` `2021-10-31` (termination date) vs `2021-10-25`
  (pay-by date) — pipeline picked the wrong one, but they're 6 days apart.

Also one OCR artifact, not a pipeline bug: `SHEMARIA, ALFRED I 8 DEANNA`
— OCR read `&` as `8`, so the name line has a digit and the whole
(otherwise perfect) address block loses its name.

## Hallucination

14 `null_hallucination` events / 180 slots = **7.8 %** (dev: 0 %). Almost
all are the bank-statement `total_amount` cluster + a few header-as-name
recipients. The one *amount on a real bill* that was wrong
(`aws 136.38` vs `135.38`) is a rounding/label ambiguity, not an
invention.

## What this means

- **The dev 89.2 % was optimistic on both axes**: real overfit to 20
  images, and the 20 were a narrower slice than "US mail" (no plain bank
  statement, no inline-name card, few template forms).
- **The anchor layer generalizes** (action 0.93, due_date 0.77). **The
  structure layer is brittle** (recipient 0.57) — it works when the
  layout matches the handful it was built against and falls to `null` or
  a wrong line otherwise.
- **New systemic gap, not a tuning issue: "is this a bill at all?"** A
  bank statement, an insurance declarations page, and an EOB all carry a
  large number and no "not a bill" string; the pipeline treats them as
  unpaid bills. This is the highest-value thing the holdout surfaced.

No pipeline changes were made. Results in `results/holdout/`
(`summary.json`, `comparison.csv`, `raw/*.json` with per-image evidence).
