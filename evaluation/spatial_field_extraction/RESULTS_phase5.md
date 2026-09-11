# Phase 5 — Domain-aware Field Interpretation (minimal experiment)

Question: with the domain known, can it help correctly interpret
`total_amount / due_date / payment_status / action`?

Constraints honoured: Phase 3 fully frozen (`frozen_phase3/`), Phase 4
taxonomy frozen at 7 classes (CREDIT_CARD folded into BANKING_FINANCE,
AUTO_INSURANCE → INSURANCE, GOVERNMENT_TAX → GOVERNMENT — the merge the
Phase-4 study recommended). No semantic similarity. No model training.
Only Hunyuan `text + bbox`.

**Design rule:** domain is a *semantic constraint*, never the answer.
`phase5.py` takes the frozen Phase-3 result, then may only **remove /
demote** a money candidate the frozen extractor already scored (using the
label printed on that candidate's row, recovered by geometry), or gate a
field to `null` / `not_applicable`. It never invents a value, never picks
an un-scored candidate, never re-runs OCR. And it overrides the frozen
answer **only when the domain is confidently known** (Phase-4 score gap
≥ 1.5, or the two domains that classified perfectly — BANKING_FINANCE /
UTILITIES_SERVICES). A shaky domain → defer to frozen Phase 3.

Fields touched: `total_amount`, `payment_status`, `action`.
`sender / recipient / due_date` pass through frozen unchanged (domain
carries no reliable signal for them).

## Result — Frozen Phase 3  vs  Domain-aware Phase 5 (50 images)

| field | baseline | Phase 5 | Δ |
|---|---:|---:|---:|
| sender | 0.800 | 0.800 | — |
| recipient | 0.740 | 0.740 | — |
| **total_amount** | 0.780 | **0.900** | **+0.120** |
| **payment_status** | 0.680 | **0.840** | **+0.160** |
| due_date | 0.820 | 0.820 | — |
| action | 0.880 | 0.880 | — (2 cells `pay`→`renew`, both already GT-accepted) |
| **OVERALL** | **0.783** | **0.830** | **+0.047** |

| split | baseline | Phase 5 |
|---|---:|---:|
| dev 20 | 0.892 | **0.900** |
| holdout 30 | 0.711 | **0.783** |

| | baseline | Phase 5 |
|---|---:|---:|
| answer taxonomy | 141 correct · 22 null-miss · **28 wrong · 15 halluc** | 151 correct · 21 null-miss · **21 wrong · 9 halluc** |
| **hallucination events** | 15 | **9** (−6) |
| dev regressions | — | **0** |
| breaks (base ok → Phase 5 wrong) | — | **0** |

25 cells changed: **13 clear fixes**, 12 "even" (all improvements in
kind — a hallucinated amount / unpaid status → the correct `null` /
`not_applicable` that GT already accepts).

## Per named failure cluster

| cluster | baseline | Phase 5 |
|---|---|---|
| **Bank statement → Ending Balance as amount due** | `$14,824.76 / $27,584.38 / $125,883.63 / $6,713.87`, all `unpaid` | **all → `null` + `not_applicable`** (BANKING_FINANCE has no "amount due" anchor → not a bill). 4/4 fixed. |
| **EOB / hospital → Total Charges as patient amount** | CMS_EOB `null` (already ok); **UCLA_Health_Bill `$13,857` (Total Current Charges)** | CMS_EOB still ok; the row-label filter *does* drop the `$13,857` candidate and would pick `$472.00` — **but Phase 4 gives UCLA only gap 1.0** (a spurious BANKING_FINANCE signal off "FINANCIALLY RESPONSIBLE"), so Phase 5's confidence gate declines to override. **1 case not fixed — bounded by Phase 4, not by Phase 5's design.** |
| **Insurance declaration → Premium / Coverage / Deductible as amount** | Penny `$700` (six-month premium), statefarm `$165`, All_State card `unpaid` | Penny/statefarm amount → `null`, payment_status → `not_applicable` (declarations page / card, no "premium due" anchor). Fixed. |
| **Renewal / Notice → action** | DMV_Registration / DMV_late_fee `pay`; statefarm renewal `pay` | → `renew` (INSURANCE/GOVERNMENT + renewal context, no hard-due marker). DMV two already GT-accepted; more accurate either way. |
| **same word, different meaning per domain** | e.g. "comprehensive", "deductible", "balance" | handled by per-domain forbid lists *when the domain is right*. The one wrong-domain case (Eye_care → INSURANCE, gap 1.0) is **caught by the confidence gate** — Phase 5 leaves it to frozen rather than corrupting it. |

## Reading

- **Domain-aware interpretation beats frozen Phase 3, clearly and safely.**
  +4.7 overall, **+7.2 on holdout**, +0.16 payment_status, +0.12
  total_amount, −6 hallucination events, **0 regression on dev, 0 breaks**.
- The gains are exactly where the holdout analysis predicted: bank
  statements and insurance declarations that carry a big number and no
  "amount due" anchor. Domain supplies the missing "is this a bill at
  all?" signal that no amount keyword could.
- **`sender / recipient / due_date` did not move** — confirming domain is
  a constraint on *semantic* fields (what a number means), not on
  *structural* ones (where the name is).
- **Phase 5's ceiling is Phase 4's confidence.** The one cluster case it
  can't fix (UCLA) is a Phase-4 low-gap classification, and the gate
  correctly refuses to act on it rather than risk a wrong-domain
  corruption. This is the intended behaviour: a wrong domain must never
  make a field worse.
- Net: the approach is worth continuing. The next lever is Phase-4
  precision on the low-gap medical/insurance boundary (e.g. the
  "financial" ↔ "financially responsible" collision), not more Phase-5
  rules.

Frozen snapshot: `frozen_phase4_5/` (domain.py / gt_domain.py / phase5.py
+ CHECKSUMS). Results: `results/phase5/summary.json`,
`results/domain/summary.json`.
