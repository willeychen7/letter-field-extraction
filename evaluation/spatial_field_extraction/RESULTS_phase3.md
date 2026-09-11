# Phase 3 — Position / Structure for sender & recipient (explicit decision ladder)

Same 20 images, same OCR cache, same ground truth as the frozen run.
`structure.py` is new; in `extract.py` only `extract_sender` /
`extract_recipient` and the sender↔recipient mutual-exclusion were
rewritten. amount / due_date / payment_status / action logic and every
threshold are **unchanged**. No Semantic Similarity. No new entries in
`SENDER_INSTITUTION_HINTS` / `_NON_NAME_WORDS`. Mama Helper / V5 untouched.

## Headline: frozen → Phase 3 (ladder)

| field | frozen v1 | Phase 3 ladder | Δ |
|---|---:|---:|---:|
| sender | 0.750 | **0.950** | +0.200 |
| recipient | 0.550 | **1.000** | +0.450 |
| total_amount | 0.950 | 0.950 | — (frozen) |
| payment_status | 0.750 | 0.750 | — (frozen) |
| due_date | 0.900 | 0.900 | — (frozen) |
| action | 0.800 | 0.800 | — (frozen) |
| **OVERALL (20×6)** | **0.783** | **0.892** | **+0.109** |
| authoritative-GT subset (11×4) | 0.909 | 0.909 | — |

| quality metric | frozen v1 | Phase 3 ladder |
|---|---|---|
| taxonomy | 67 correct · 27 both-null · **7 wrong · 13 null-miss · 6 halluc** | 74 correct · 33 both-null · **3 wrong · 9 null-miss · 1 halluc** |
| null-hallucination rate (strict) | 5.9 % (1/17) | **0.0 % (0/17)** |
| regressions vs frozen v1 | — | **0** |
| 6-image calibration set | 1.000 | 1.000 (unchanged) |

sender 19/20 (only miss = the truncated DMV_Registration).
recipient 20/20 (12 real names extracted, 8 correct `null`s — 5 documents
have no addressee, 3 are placeholder blocks where `null` is accepted).

## Decision ladders (no mixed scoring)

Sender and recipient candidates are built by **separate** ladders,
evaluated **in priority order**; the first tier that yields a candidate
wins. Then a mutual-exclusion check runs.

### Recipient — `structure.classify_recipient`

1. **R1 — labeled address block.** A detected block (name / [street] /
   city ST zip, vertically adjacent, left- or centre-aligned) with a
   `Bill To / Billed To / Patient / Member / Customer / To / Mail To`
   label that a line directly above it *starts with*.
2. **R3 — coupon repeat.** The same block name appears in a second block
   (letter body + payment stub).
3. **R2 — complete unlabeled block by position.** name + street + city ST
   zip, in the upper zone or the only such block on the page, and not a
   sender return address.
4. **R4 — name + partial address.** A plausible name forming a block with
   just a street *or* just a city ST zip.
5. Otherwise **null.** A bare name with no address structure is never
   promoted; `CITY, STATE ZIP`, `Document Number: XXX`, `Meter Reading`,
   a lone word are never treated as a name.

Block name = the **top-most** plausible-name line (mail order is
NAME / TITLE / ORG / STREET / CITY), skipping a leading `Bill To:` /
`Named Insured(s)` label and institution lines. A name line must be ≥ 2
tokens (`and` / `&` are connectors, so `George and Christine E Murphy`
and `JAMES & KAREN Q. HINDS` count).

### Sender — `structure.classify_sender`

1. **S1 — top letterhead / logo.** Prominent text in the top strip,
   visually separated from the body. **If any S1 candidate carries an
   institution word, S1 is restricted to those** — so `FARMERS INSURANCE`
   (mid-header, has a hint) beats a bare `Policygenius` wordmark at the
   very top. Body-text org names never override S1.
2. **S2 — sender anchor.** `From / Issued By / Sent By / Customer Service
   / Remit To / Make checks payable to` + the org beside/after it.
3. **S3 — institution-shaped line by position.** Short, upper region *or*
   repeated on the page (letterhead lost to OCR, issuer only in the
   coupon — e.g. `AAA Insurance`). Excludes titles, `Field:` labels,
   table headers, person names, city-state lines.
4. Otherwise **null.**

Structural demotions inside S1 (no keyword lists): a wide single-line
banner spanning the column (`Auto Insurance Declaration Page`), an
all-caps title with no tagline under it (`EXPLANATION OF BENEFITS`), a
stack of `Field:` labels, a person-name line (a signatory), tabular /
dated rows. `SENDER_INSTITUTION_HINTS` is matched with **word
boundaries** (so `plan` ≠ `exPLANation`) and ignored on `Field:` lines.

### Mutual exclusion

Sender and recipient are resolved independently, then: if they normalise
to the same string (or one contains the other), keep the one backed by
the stronger **structure** — a real address block (R1/R2/R3) keeps
recipient, a real top letterhead (S1) keeps sender — and null the other.
If neither is clearly stronger, null the lower-scoring one.

## Fixes vs frozen (11 cells, 0 regressions)

recipient: `THANK YOU`→`JOHN B DOE` (SoCalGas), `null`→`PAT SMITH` (AAA),
`null`→`George and Christine E Murphy` (All_State), `null`→`Jack Smith`
(Auto_Insurance), `CARB Non`→`GONZELES C` (DMV_Registration),
`null`→`JANE DOE` (hoag), `null`→`PARKER` (Great_American — `Mail To:`
promotes the block, the `PETER` return address is demoted),
`Meter Reading`→`null` (Water_Bill2), `Document Number: XXX`→`null`
(CMS_EOB), `CITY, STATE ZIP`→`null` (IRS_CP504).
sender: `DIRECTOR OF … SERVICES`→`STATE OF NORTH CAROLINA …` (DMV_Notice,
centered top letterhead group), `Policygenius`→`FARMERS INSURANCE`
(Auto_Insurance, S1 hint-preference), plus `Purchases`→`null`
(Bank_Bill_Due) and `EXPLANATION OF BENEFITS`→`null` (CMS_EOB).

## The 13 remaining errors

| category | count | detail |
|---|---|---|
| **OCR truncation (`finish=length`)** | 3 | DMV_Registration sender, Great_American action, SoCalGas payment_status — the 3 dense/slow images, tail cut at 8192 tokens |
| **out of Phase-3 scope — anchor / marker gaps** (unchanged from frozen) | 9 | `action` null-miss ×2, `due_date` null-miss ×2, `payment_status` null-miss ×4 (no amount **and** no "THIS IS NOT A BILL" string), `total_amount` null-miss ×1 (DMV_Notice `$83.50` only inside a full sentence) |
| **action false-positive** (action logic frozen) | 1 | Auto_Insurance_Bill1 `pay` from "amount due" inside "…will be mailed separately" |

Every sender/recipient structural error is gone except the one on a
truncated image.

## Reading

- The explicit ladder does what the mixed-scoring Phase-3 pass did for
  recipient (1.00) **and** fixes the one case mixed scoring couldn't —
  `Policygenius` vs `Farmers Insurance` — because S1 now *prefers* the
  hint-bearing letterhead candidate rather than the biggest one. Overall
  **+10.9 points (78.3 → 89.2)**, **zero regressions**, hallucination at
  **0**.
- The residual is cleanly separated: **3 OCR-truncation errors** (fix the
  OCR pass) and **9 out-of-scope anchor / marker null-misses**. Neither
  needs Semantic Similarity.
- `total_amount` 0.95 and `due_date` 0.90 are untouched.

## Files

`structure.py` (new: `detect_address_blocks`, `classify_recipient`,
`detect_letterhead`, `classify_sender`) · `extract.py`
(`extract_sender` / `extract_recipient` / mutual-exclusion only) ·
`run_full20.py` · `ground_truth_20.py`. Results kept side by side in
`results/full20/`: `summary_FROZEN_v1.json`, `summary_PHASE3_v2.json`
(mixed scoring), `summary_PHASE3_v3_ladder.json` (this), plus matching
`comparison_*.csv`.
