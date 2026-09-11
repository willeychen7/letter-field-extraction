# Native `/v1/understand-letter` vs OCR+Rules `/v1/analyze` — head-to-head

Read-only benchmark. No Phase 3–8 code touched, no `/v1/analyze` schema
touched, no frozen file touched — this only calls two existing HTTP
endpoints and scores what comes back against the existing ground truth
(`ground_truth_20.py` + `ground_truth_holdout.py`), using the existing
`ground_truth.score_field`.

**Question:** does letting Hunyuan answer "who sent this / how much is due"
directly (one prompt, one JSON reply) do as well as OCR-then-deterministic-
rules? Answer: no, not close.

## What each endpoint does

| | `/v1/understand-letter` ("native") | `/v1/analyze` ("ours") |
|---|---|---|
| Model's job | Read the image, answer 9 fields directly (`schemas/mama_helper_v1.py`'s official Tencent information-extraction prompt) | Read the image, output `text+bbox` only (`spotting_hunyuan` prompt) |
| Who decides sender/recipient/amount/date | the model, freeform | Phase 3 (position/structure) + Phase 7 (domain-aware semantics), deterministic |
| Used in production path | no — exists in code, unused | yes |

## Method

- 50 real letters (the same `GT_DOMAIN` set Phase 9 uses), same
  `ground_truth_20`/`ground_truth_holdout` gold values.
- 4 fields both schemas can answer: `sender`, `recipient` (native:
  `recipient_name`), `total_amount` (native: `amount`), `due_date` (native's
  free-text date normalised to ISO via the frozen `anchors.parse_date`
  before comparing — otherwise "January 29, 2018" vs "2018-01-29" would
  wrongly score as different).
- Same `ground_truth.score_field` for both, so scoring is identical.
- 12 of the 50 images are `.webp`, a format this llama.cpp build's image
  loader rejects (documented in `docs/PHASE9B_GPU_FEASIBILITY.md`) — every
  one of them 502'd on the first pass. Converted to PNG (`sips`) and
  re-run; all 12 then succeeded. Not a native-endpoint quality issue, a
  known image-loader limitation, fixed before scoring. `bench_native_vs_
  pipeline.py` now does this conversion itself.
- Our side (`/v1/analyze`) is scored on 49/50 (one unrelated live-OCR
  failure already logged in `results/phase9/summary.json`); native is
  scored on 50/50. Denominator differs by one image; doesn't move the
  conclusion.

## Result

| Field | Native (`/v1/understand-letter`) | Ours (`/v1/analyze`) |
|---|---:|---:|
| sender | 44.0% (22/50) | **79.6%** (39/49) |
| recipient | 24.0% (12/50) | **81.6%** (40/49) |
| total_amount | 50.0% (25/50) | **89.8%** (44/49) |
| due_date | 46.0% (23/50) | **81.6%** (40/49) |
| **4-field combined** | **41.0%** (82/200) | **83.2%** (163/196) |
| **null-hallucination rate** | **31.5%** (63/200 cells) | **0.5%** (1/196 cells) |

### Example hallucinations (GT says the field doesn't exist; native invented a value anyway)

```
SCE_Letter        total_amount = "715 P Street 20th Floor"   -- an address, not an amount
Water_Bill2       total_amount = "11 CCF"                    -- a usage unit, not an amount
Water_Bill2       sender = "Meter Reading" / recipient = "Units Used"   -- table column headers
BOA_Bill_Example  recipient = "Bank of America"               -- the issuer, not the addressee
```

This matches `schemas/mama_helper_v1.py`'s own docstring, which already
flagged sender/recipient direction as wrong in 6/10 spot-checked cases for
this exact combined-request prompt — the 50-image run reproduces that
finding at scale, and the hallucination-rate number (not tracked before)
makes it worse than the direction-only framing suggested.

## Conclusion

**OCR+rules (`/v1/analyze`) wins on every field, by a wide margin, and
produces roughly 60x fewer hallucinations.** This is not a close call or a
matter of prompt tuning — letting the model answer "who/how much/when"
directly is a fundamentally worse fit for a use case where a wrong dollar
figure or wrong addressee is the failure mode that matters most and the
end user (a non-English-speaking elder) cannot catch it.

`/v1/understand-letter` stays in the code as a reference/comparison
baseline. It must not be used as, or folded into, the production path.

## Artifacts

- `bench_native_vs_pipeline.py` — the benchmark script (resumable, retries
  failed images, handles the webp conversion itself)
- `results/native_benchmark/native_raw.json` — raw `/v1/understand-letter`
  response per image
- `results/native_benchmark/native_scored.json` — per-field, per-image
  scoring rows + the summary table above
