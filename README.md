# letter-field-extraction

Can a small (1B), locally-run vision-OCR model plus deterministic spatial
rules read a real US letter well enough to extract structured fields —
without a second LLM, without regex-based semantic extraction, and
without semantic similarity?

**Full current status, all results, and the pending/known-issue list:
[`PROJECT_STATUS.md`](PROJECT_STATUS.md).** This file is just the front door.

## Pipeline

```
letter photo / PDF
  → HunyuanOCR-1B (GGUF, llama.cpp)   -- text + bbox, "spotting" prompt
  → Phase 3  Position / Structure     -- sender / recipient via layout geometry
  → Phase 4  Domain classification    -- 7-class taxonomy
  → Phase 7  Field Semantics          -- domain-aware value resolution
  → Phase 8  Contact / Phone          -- which number, for what purpose
  → /v1/analyze (fixed JSON schema)
  → deterministic Chinese explanation (frontend template, no LLM)
  → V0 tester UI (webapp/)
```

The OCR engine is a pluggable front-end, not the point of the project —
`structure.py`/`field_semantics.py`/etc. only consume a plain
`{text, bbox}` contract, so any OCR source that produces that can be
swapped in and benchmarked against the same ground truth (see
`RESULTS_paddleocr_vs_hunyuan_frontend.md` for an example).

## Headline result

| | Overall accuracy (49 real US letters) | Hallucination rate |
|---|---:|---:|
| **This pipeline** (OCR + rules) | **84.1%** | **0.5%** |
| Hunyuan answering fields directly, one prompt | 41.0% | 31.5% |
| Hunyuan answering fields directly, one field per call | 44.5% | 25.0% |

Full write-ups: `RESULTS_native_vs_pipeline.md`, `RESULTS_native_split_question.md`.

## Run it

```bash
pip install -r requirements.txt
LLAMA_SERVER_URL=http://127.0.0.1:8090/v1 \
  python3 -m uvicorn server.api:app --host 127.0.0.1 --port 8091
```

Open `http://localhost:8091/ui/` for the tester UI, or `POST` an image/PDF
to `http://localhost:8091/v1/analyze` directly. Requires a llama-server
already running the HunyuanOCR GGUF weights on `:8090` (not included in
this repo — see `.gitignore` — get them from Hugging Face:
`tencent/HunyuanOCR` / `mradermacher/HunyuanOCR-GGUF`).

## Layout

```
server/api.py                          FastAPI: /v1/ocr, /v1/analyze, /v1/understand-letter (legacy, not used)
webapp/index.html                      V0 tester UI (static, no build)
evaluation/spatial_field_extraction/   Phase 3-8 pipeline + frozen_phase3/ snapshot + benchmark/comparison scripts
experiments/                           GPU feasibility baseline + run01 diagnostics
docs/                                  OCR contract, GPU feasibility write-up
```

See `PROJECT_STATUS.md` for the full phase history, every benchmark
result, and the current pending/blocker list.
