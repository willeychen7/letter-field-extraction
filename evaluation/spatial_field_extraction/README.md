# Spatial Field Extraction — Stage-1 Experiment

**Question.** Is *HunyuanOCR-1B → OCR text+bbox → local deterministic spatial
extraction* more reliable than the earlier *Image → Hunyuan → answer* baseline?

**Baseline.** `single_field_test/results/results.json` — one field per request,
plain-text answer, `temperature=0`. Historical overall = **39.6 %** (6 images ×
8 fields = 48 requests). Re-scored on the 6 fields below it is **36.1 %**.

**Constraints honoured.** No regex, no 2nd LLM, no Ollama / Qwen, no external
API. OCR uses the official `spotting_hunyuan` task prompt only. The one piece
of pattern code is a hand-written character scanner that reads HunyuanOCR's own
`TEXT(x1,y1),(x2,y2)` coordinate serialisation — it makes no semantic decision.
Value-shape checks (`looks_like_money`, `parse_date`, `looks_like_person_name`)
are plain string inspection (`.isdigit()`, month-name lookup, token counting) —
no `import re` anywhere in the tree.

## Pipeline

```
image
  → HunyuanOCR (spotting_hunyuan prompt, temp=0, max_tokens=8192)
  → parse_ocr_elements()            [{text, bbox:[x1,y1,x2,y2]}], bbox in 0..1000
  → spatial primitives              above/below/left/right, same_row/col,
                                    h/v overlap, center distance, gaps
  → semantic anchors                label dictionaries per field (anchors.py)
  → candidate matching              money/date/name-shaped elements near anchors
  → candidate scoring               transparent additive score + written reasons
  → cross-validation                sender≠recipient, due_date≥statement_date,
                                    amount vs largest money token, not-a-bill ⇒
                                    null amount
  → final fields                    top candidate if score ≥ τ, else null
```

## Files

| file | role |
|---|---|
| `ocr.py` | HunyuanOCR call + hand-written coordinate parser (no regex) |
| `spatial.py` | 2-D geometry primitives over bboxes |
| `anchors.py` | anchor dictionaries + string-only value-shape classifiers |
| `extract.py` | candidate matching, scoring, cross-validation, thresholds |
| `ground_truth.py` | 6×6 ground truth + lenient scorer (aliases, money eq) |
| `run.py` | headline 6-image / 6-field run + baseline re-score |
| `holdout.py` | same pipeline, **no changes**, on 6 other letters (4 fields) |
| `results/raw/<stem>.json` | elements + every candidate + score + evidence |
| `results/summary.json` | all metrics, both systems |
| `results/comparison.csv` | the headline table |
| `results/holdout.json` | untuned generalization check |

## How to reproduce

```
cd evaluation/spatial_field_extraction
python3 run.py                 # fresh OCR   (llama-server on :8090)
python3 run.py --use-cache     # reuse results/raw/*.ocr.json
python3 holdout.py             # untuned check on 6 different letters
```

## Result — see `RESULTS.md` for the full write-up and the honesty caveats.
