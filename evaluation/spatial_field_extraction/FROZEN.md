# Phase 3 — FROZEN

As of this point the Phase 3 pipeline is frozen. No further changes to
rules, thresholds, anchor lists, or the decision ladders until the holdout
result is in.

## Frozen state

- **Dev benchmark:** 20 images, **89.2 % overall (107/120)**
  - sender 0.95 · recipient 1.00 · total_amount 0.95 · payment_status 0.75
    · due_date 0.90 · action 0.80
  - 0 regressions vs the pre-Phase-3 frozen baseline (78.3 %)
  - null-hallucination rate 0.0 %
- **6-image calibration set:** 1.00 (unchanged)

## Frozen files (snapshot in `frozen_phase3/`)

```
anchors.py    fddb08f0…   semantic anchor dicts + value-shape classifiers
spatial.py    931a55f0…   bbox geometry primitives
structure.py  fddb08f0…   address blocks + letterhead + decision ladders
extract.py    c795fa25…   field extractors + cross-validation
ocr.py        75184bab…   HunyuanOCR call + coordinate parser
ground_truth.py 9cd437cb… lenient scorer (aliases, money-eq, quote-norm)
```
(see `frozen_phase3/CHECKSUMS.txt` for full md5s)

## Not frozen (evaluation scaffolding, may change)

`run_full20.py`, `run_holdout.py`, `holdout_set.py`, `ground_truth_20.py`,
`ground_truth_holdout.py` — these are the benchmark harness and GT, not the
pipeline.

## What the holdout must answer

Does 89.2 % hold on 30 fresh letters that never touched tuning?
