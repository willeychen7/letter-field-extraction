# PaddleOCR vs HunyuanOCR as the front-end for Phase 3–8

Read-only comparison. No regex added, no Phase 3–8 code touched or called
differently — the ONLY thing that changes between the two runs is which
OCR engine's `{text, bbox}` elements are fed into the same frozen
`field_semantics.resolve()`. Uses only already-cached OCR output (mama-
helper's `frontend/src/utils/demo_ocr_pp.json` for PaddleOCR,
`results/phase9/raw/*.ocr.json` for HunyuanOCR) — no new model calls.

**Question:** with zero regex and the exact same downstream rules, which
OCR engine's output makes Phase 3–8 more accurate?

## Method

- 16 images have all three of: cached PaddleOCR output, cached HunyuanOCR
  output, and our ground truth (`ground_truth_20`/`ground_truth_holdout`).
  1 (`SoCalGas`) is excluded — its cached HunyuanOCR call had errored
  (502), so neither side has usable data for it. **15 images scored.**
- PaddleOCR's `{text, left, top, right, bottom}` (pixel space) is
  normalised to the same 0–1000 coordinate space HunyuanOCR uses
  (`structure.py`'s `PAGE_W`/`PAGE_H = 1000`) — otherwise every
  position-based rule in Phase 3 would silently misfire.
- Both element sets are run through the identical, unmodified
  `field_semantics.resolve()` and scored with `ground_truth.score_field`
  across all 6 fields + domain.

## Result

| | domain | sender | recipient | total_amount | payment_status | due_date | action | **overall** | hallucinations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **PaddleOCR → Phase 3–8** | 80.0% | 73.3% | 60.0% | 66.7% | 66.7% | 73.3% | 73.3% | **70.5%** (74/105) | 2 |
| **HunyuanOCR → Phase 3–8** | 80.0% | 80.0% | 93.3% | 93.3% | 86.7% | 86.7% | 93.3% | **87.6%** (92/105) | 1 |

HunyuanOCR's output gets **17.1 points higher** overall through the exact
same rules.

## Root cause: not recognition accuracy — a text-shape mismatch

```
PaddleOCR : 'SOUTHERNCALIFORNIA'          (no space between words)
HunyuanOCR: 'SOUTHERN CALIFORNIA'
```

The PaddleOCR output currently cached in mama-helper **merges words within
a line without inserting spaces**. Nearly every Phase 3 heuristic depends
on `.split()` word boundaries — counting tokens (2–5 for a plausible name),
checking each word against `_NON_NAME_WORDS`, detecting "CITY, ST ZIP"
(needs a space before the state abbreviation), etc. Gluing words together
breaks these checks wholesale, regardless of whether PaddleOCR read the
characters correctly.

Concrete failures (mostly safe `null_miss`, a few real `wrong`):

```
DMV_Registration   all 5 fields -> None   (address block never formed: glued text)
IRS_cp503          total_amount = 9444.07 (gold 9533.53 -- misread a run of glued digits)
aaa-policy_renew   sender = "Membership Renewal Notice"  (banner-as-sender, worse with glued text)
Medical_Invoice    sender = "ZylkerHeathcare 14B,Northern Street,"  (hallucination from a glued address run)
```

## Conclusion

**Under "zero regex + identical Phase 3–8", HunyuanOCR is clearly better
— but the gap is a text-shape/interface mismatch, not a proven gap in raw
character recognition.** PaddleOCR's line-merging (as currently cached in
mama-helper) does not preserve the word-spacing Phase 3–8 was designed
around. If that merging were changed to preserve spaces, the gap would
likely shrink — that has not been tested here, and would require touching
mama-helper's own OCR post-processing, out of scope for this comparison.

## Artifacts

- `bench_paddle_vs_hunyuan.py` — the comparison script (reads only
  already-cached OCR output, makes no model calls)
- `results/paddle_vs_hunyuan/scored.json` — per-field, per-image rows for
  both sources
