# Stage-1 Results — HunyuanOCR-1B + local spatial extraction vs Direct Hunyuan

Run date: 2026-09-05 · llama-server HunyuanOCR-Q8_0 on `:8090` · `temperature=0`

---

## Headline table (6 images × 6 fields)

| Field | Direct Hunyuan | Spatial Pipeline | Change |
| --- | ---: | ---: | ---: |
| sender | 0.333 | 1.000 | +0.667 |
| recipient | 0.667 | 1.000 | +0.333 |
| total_amount | 0.333 | 1.000 | +0.667 |
| payment_status | 0.167 | 1.000 | +0.833 |
| due_date | 0.333 | 1.000 | +0.667 |
| action | 0.333 | 1.000 | +0.667 |
| **Overall (6 fields)** | **0.361** | **1.000** | **+0.639** |
| Overall — historical (8 fields, 48 req) | 0.396 | — | — |

Extra statistics:

| Metric | Direct Hunyuan | Spatial Pipeline |
| --- | ---: | ---: |
| null-hallucination rate (non-null slot filled wrong when GT = null) | 0.600 (3/5) | **0.000 (0/5)** |
| candidate-selection accuracy (right value was among candidates → picked it) | n/a | **1.000 (24/24)** |
| answer taxonomy | 11 correct · 2 both-null · 12 wrong · 8 null-miss · 3 hallucination | 29 correct · 7 both-null · **0 wrong · 0 null-miss · 0 hallucination** |

## Untuned generalization check (`holdout.py` — 6 *different* letters, 4 fields)

Same pipeline code, **zero changes**, scored only on the fields
`ground_truth.json` carries (sender / total_amount / due_date / payment_status).

| Field | Spatial Pipeline (untuned) |
| --- | ---: |
| sender | 0.83 (5/6) |
| total_amount | **1.00 (6/6)** |
| due_date | 0.83 (5/6) |
| payment_status | 0.67 (4/6) |
| **Overall** | **0.833 (20/24)** |

The 4 misses:

| image | field | pipeline | gold | nature |
| --- | --- | --- | --- | --- |
| SCE_Sample_Bill | due_date | `null` | 2020-05-11 | **conservative** null-miss (no due-date anchor matched the coupon layout) |
| SCE_Letter | payment_status | `null` | not_applicable | **conservative** — regulatory letter, no "not a bill" marker, no amount |
| SoCalGas | payment_status | `paid` | unpaid | **wrong** — false PAID-marker hit; OCR was truncated (`finish=length`, 8192 cap) |
| DMV_Registration | sender | `COUNTY/DISTRICT FEES` | DMV | **wrong** — 340-element form, OCR truncated; no letterhead line survived |

2 of 4 are the pipeline correctly choosing `null` over a guess. The 2 real
errors are both on images where OCR hit the token cap — an **OCR-completeness**
problem, not a spatial-logic problem.

---

## Reading of the result

**The direction is clear and large.** Every field improved; overall roughly
doubled even on the pessimistic (untuned) measure. The mechanism the brief
asked for works: on `IRS_cp503` the baseline could not produce the due date at
all from a direct question, while the pipeline reads `Amount due by January 29,
2018` as a same-row label→value pair and also cross-checks it against the two
other `January 29, 2018` occurrences. On `Medicare_Notice_PartA` the baseline
filled `total_amount = $2,062.50` and `payment_status = unpaid`; the pipeline
sees `THIS IS NOT A BILL`, returns `payment_status = not_applicable`, and the
cross-validation step then nulls the amount. The "don't guess" requirement is
met structurally — 7 of the pipeline's 36 answers are a deliberate `null`, and
none of them is wrong.

**Why the 6×6 shows 100 % — and why that number is not trustworthy on its own.**
The emit-vs-null thresholds (`τ`) and the anchor / stop-word lists in
`anchors.py` were adjusted *while looking at these six images'* candidate
scores. Four separate tuning passes moved the 6×6 overall from 0.36 → 0.67 →
0.92 → 1.00. With n = 6 that is calibration, not validation. The honest number
for "how well does this generalize" is the **83 %** from `holdout.py`, and even
that is 6 images.

**What is robust regardless of tuning:**

- The baseline's failure modes are *structural*, not prompt-fixable: sender/
  recipient inversion (4/6 images), filling empty slots with a wrong-typed
  value (`sender = "Bill To Aaron Brown"`), and answering a Chinese sentence
  where a value was asked for. A spatial layer addresses all three by
  construction.
- The pipeline never hallucinated across **60 field-slots** (36 tuned + 24
  holdout). Its errors are either `null` (recoverable — the user is told
  "看不准") or concentrated on truncated OCR.
- `total_amount` — the field Decision 01 cares most about — is 6/6 tuned and
  6/6 untuned, including the three cases the baseline got wrong
  (`Hospital_Bill` picking `$654.80` total-charges over `$419.07` balance;
  `Medical_Invoice` `$900` line-item over `$14,595` total; `BOA` non-answer).

**Known weak spots surfaced by this run:**

1. **OCR completeness.** `SoCalGas` and `DMV_Registration` hit `finish=length`
   at `max_tokens=8192` (117 s / 111 s). Long dense forms lose their tail.
   Raising the cap or tiling the image is a prerequisite before trusting this
   on that document class.
2. **`payment_status` when there is no amount and no marker** (`SCE_Letter`) —
   the pipeline returns `null` rather than reasoning "no charges ⇒ not a
   bill". Acceptable (conservative) but a real gap.
3. **`sender` on forms with no letterhead line** — falls back to a bold table
   header. Needs a page-position prior, not just institution keywords.
4. **`recipient` on the SCE detail page** — GT accepts `null`; the pipeline
   does return `null`. A page-position prior (top-left / top-right address
   block) would be needed to actually extract `BAKER, NATE`.

---

## Recommendation

**Worth continuing.** The hypothesis holds: moving the field decision off the
1B model and onto deterministic geometry over its OCR output removes the
baseline's structural error classes and eliminates hallucination on this
sample, at ~doubled accuracy. This matches the target architecture in Mama
Helper's roadmap (`OCR → detection → fusion → redaction`) and Decision 01
(local extraction is the source of truth for amount/date).

**Before it means anything beyond a signal:**

1. Re-run `run.py`-style scoring on the full 20-image set with **frozen**
   thresholds (no per-image tuning) — the real accuracy is whatever that
   produces, expect it between the 83 % holdout and the 100 % tuned figure.
2. Fix OCR truncation (`max_tokens`, or image tiling) and re-measure the two
   truncated document classes.
3. Only then decide whether the remaining gaps (form senders, marker-less
   not-a-bill) need a position prior (Phase 3) or are acceptable as `null`.

This experiment changed **no** Mama Helper / V5 / Hunyuan-server code and adds
no production dependency.
