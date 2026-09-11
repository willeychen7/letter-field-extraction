# HunyuanOCR + Spatial Field Extraction — Project Status

Last updated: 2026-09-11

An independent experiment, separate from the `mama-helper` production app:
can a small (1B) local vision-OCR model + deterministic spatial rules read a
real US letter well enough to extract structured fields — without a second
LLM, without regex-based semantic extraction, and without semantic
similarity.

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

Hard constraints held throughout: no second LLM/Ollama/Qwen/external API, no
regex for semantic field extraction, no semantic similarity, amounts/dates
always local-extracted (never LLM-authored), null when uncertain (never
guessed).

## Phase status

| Phase | What | Status |
|---|---|---|
| 1 | Stage-1 baseline (anchors + spatial rules, 20 images) | frozen |
| 3 | Position/Structure: sender/recipient via bbox geometry | frozen (Phase 10 re-froze it) |
| 4 | Domain classification, 7-class taxonomy | frozen |
| 5 | Domain-aware field interpretation | merged into 7 |
| 7 | Field Semantics (declarative `SEMANTICS` table) | frozen |
| 8 | Action → Contact Org → Phone | frozen, 0 wrong numbers |
| 9 | End-to-end eval, 49 real letters, live OCR | complete |
| 9B | GPU feasibility (free-tier GPU smoke test) | closed / baseline established |
| 10 | Recipient error analysis + one targeted fix | complete |
| — | Architecture Validation (image/PDF → OCR → Phase 3-8 → API → UI) | complete |
| — | Native direct-answer vs rules (combined / split / null-fallback) | complete, settled |

## Current accuracy (Phase 9, 49 real US letters, live OCR)

| Field | Accuracy |
|---|---|
| Overall E2E | **84.1%** (306/364 graded cells) |
| total_amount | 89.8% |
| action | 87.8% |
| payment_status | 85.7% |
| domain | 83.7% |
| recipient | 81.6% |
| due_date | 81.6% |
| phone | 81.0% |
| sender | 79.6% |
| Hallucinations | 4 (none in recipient) |

### Phase 10 fix (structure.py, recipient block selection only)

Added 7 position/block-shape guards to `classify_recipient` — no vocabulary
expansion, no name-parsing changes, no touch to Phase 4-8. Result:
recipient 69.4% → 81.6%, overall 82.4% → 84.1%, the 9 dangerous
wrong-name/hallucination outputs → 0. Re-frozen in `frozen_phase3/`.

## Should Hunyuan answer fields directly instead of / in addition to rules? Settled: no.

Three variants benchmarked against the rules pipeline, same 50 real
letters, same ground truth, same scoring:

| approach | overall (4 comparable fields) | hallucination rate |
|---|---:|---:|
| **rules** (`/v1/analyze`) | **83.2%** | **0.5%** |
| Hunyuan direct-answer, combined prompt (9 fields at once) | 41.0% | 31.5% |
| Hunyuan direct-answer, split (1 field per call) | 44.5% | 25.0% |
| Hunyuan as fallback only when rules say null | net **negative** — recovers 22% of null cells, breaks 78% of them (fresh hallucinations or confidently-wrong answers) | — |

Splitting the question into one field per call helps identity fields
(sender/recipient, since there's no competing field to confuse it) but
hurts value fields (amount/due_date — the model hedges with a list of
candidates instead of committing to one). Net still ~39 points behind
rules. The null-fallback idea (only ask the model when rules are silent)
is a net loser: for every cell it recovers it damages about three others,
because Hunyuan doesn't reliably know when it doesn't know.

**Conclusion: no configuration of "ask Hunyuan directly" is competitive
with the rules pipeline for this task.** `/v1/understand-letter` and the
split-question path stay as reference baselines only, never in the
production path.

Write-ups: `RESULTS_native_vs_pipeline.md` (combined prompt),
`RESULTS_native_split_question.md` (split), `RESULTS_fallback_on_null.md`
(null-fallback).

## PaddleOCR vs HunyuanOCR as the OCR front-end

Same Phase 3-8 rules, only the OCR source swapped: HunyuanOCR 87.6% vs
PaddleOCR 70.5% (15 images with both cached). Root cause is NOT proven to
be recognition accuracy — mama-helper's own cached PaddleOCR output merges
words within a line without spaces (`SOUTHERNCALIFORNIA`), which breaks
Phase 3's word-boundary-dependent rules. mama-helper has its own fix for
this (`utils/secondPassOcr.js`, decision 12) that the cached fixture never
went through. **Re-test pending** against post-second-pass PaddleOCR output
before this comparison can fairly say which OCR reads better.
Write-up: `RESULTS_paddleocr_vs_hunyuan_frontend.md`.

## V0 tester UI

`server/api.py::POST /v1/analyze` — OCR → frozen Phase 3-8 → fixed JSON
(imports and calls the frozen modules only, adds no logic). Accepts image or
PDF (PDF page 1 rasterised via `pypdfium2` before OCR).

`webapp/index.html` — single-file, no build step, visually modeled on
mama-helper V5 ("安心小助手"): live camera (`getUserMedia`, falls back to
the native file picker if unavailable/denied), scan-line loading animation,
Chinese field cards (mm/dd/yyyy dates, xxx-xxx-xxxx phones, 金额+付款状态+
截止日期 merged into one card), deterministic "这封信说什么 / 你需要做什么"
narrative with a rule-based "要留意" flag (checks `payment_status` before
warning, so a `not_applicable`/`paid` letter never gets a false "you owe
money" flag), and local-voice text-to-speech. Pure presentation layer — the
only network call it makes is `POST /v1/analyze`.

Run: `LLAMA_SERVER_URL=http://127.0.0.1:8090/v1 python3 -m uvicorn
server.api:app --host 127.0.0.1 --port 8091`, open `http://localhost:8091/ui/`.

### Architecture Validation (completed)

Verified end-to-end with real images and a real PDF, browser `fetch`
interception, and SHA-256 checks:
- `/v1/analyze` schema stable (unchanged by any UI work)
- image and PDF both run the full chain successfully
- JSON → Chinese narrative → UI rendering correct, including null handling
  and mm/dd/yyyy / xxx-xxx-xxxx formatting
- UI makes exactly one network call (`/v1/analyze`); Phase 3-8 checksums
  unchanged since the Step 1 freeze
- no external LLM/cloud call anywhere in the path; the only upstream is the
  local/LAN llama-server. No de-identification layer exists yet — needed
  before any future LLM is added downstream of OCR.

Not yet validated: real phone-camera photos (skew/shadow/low light/HEIC),
the Dockerized deployment path (Dockerfile is updated but not rebuilt/run),
concurrent/multi-user load.

## Known bottlenecks

1. **Latency** — the OCR model runs on CPU (no GPU on this Mac); a real
   letter takes 7-30s, large images/PDFs up to several minutes. GPU speed
   is settled and doesn't need re-checking: ~3-5s median across multiple
   Kaggle T4 runs (run00 and run01), consistently ~10x+ faster than CPU.

   **Hard blocker for any future GPU deployment (not just "nice to have"
   to check) — GPU output format is still wrong.** run01 (frozen
   `spotting_hunyuan` prompt, correct `--ctx-size`, clean single-process
   server, verified byte-identical prompt) still returns 0/49 images in
   the `TEXT(x,y),(x,y)` format Phase 3-8 requires — instead getting
   `doc_parse` markdown / plain-text transcription / `layout_parse`
   region-boxes. Confirmed NOT caused by: wrong prompt, stale/duplicate
   server processes, insufficient context, or the model failing to read
   the image (content is legible and accurate, just not in spotting
   shape). Leading suspect: llama.cpp build/version mismatch — this Mac's
   working server reports `0.3.0, commit c1d0e7a00` (not resolvable in
   the `ggml-org/llama.cpp` history, likely a HunyuanOCR-specific
   fork/branch), Kaggle's freshly-built server reports `0.4.0-dev, commit
   8172e65` — unconfirmed which change is responsible. **Until this is
   fixed, GPU cannot run the pipeline at all** (Phase 3-8 gets no usable
   `{text,bbox}` elements, every field comes back null) — this blocks
   deployment, it does not just lower accuracy. Not being actively
   investigated further right now (parked, not abandoned); must be
   resolved before any GPU deployment work starts.
2. **sender accuracy (79.6%)** — largest field-level gap. Same failure
   shape Phase 10 fixed for recipient: a document-title banner
   (`"HOA DUES INVOICE"`, `"Financial Statement"`) outranking the real
   institution name. Not yet analyzed (queued: Sender Error Analysis, same
   method as Phase 10).

## Pending / bring up when needed (diagnosed, not yet fixed)

Two concrete `structure.py`/`anchors.py` gaps found while spot-checking
individual images (not yet actioned — queued for a Phase-10-style pass:
analyze → narrow fix → full 49-image regression):

- **`aws_invoice.png` recipient not found**: OCR merged the label and name
  onto one line (`"Attn: Jeff Barr"`). `is_plausible_name_line` rejects any
  line containing `:`, so the whole line is discarded instead of just the
  label prefix — a new failure shape (label+name glued in a single OCR
  element), not covered by the existing "label on its own line" logic.
- **`AAA_insurance_Bill.png` due_date not found**: the bill says `"Due Apr
  8 2020"` — a bare "Due" with no space-separated phrase. `DUE_DATE_ANCHORS`
  only has multi-word phrases (`"due date"`, `"payment due"`, `"due by"`,
  ...); a standalone "Due" matches none of them, so the correctly-parsed
  date never gets an anchor-proximity score and stays below the acceptance
  threshold. Confirmed via the native-vs-pipeline diff: this exact anchor
  gap accounts for most of the 7 due_date cells where the direct-answer
  model beat the rules pipeline.

## Explicitly deferred (not started without further sign-off)

GPU run02 (structured JSON extraction), Phase 10's C2 gap (inline name
reader for ID-card-style layouts), production deployment.

## Index of `evaluation/spatial_field_extraction/RESULTS_*.md`

Chronological. Each is a frozen record of one experiment — don't edit old
ones, add a new file for a new finding.

| File | What it settled |
|---|---|
| `RESULTS.md` / `RESULTS_full20.md` / `RESULTS_holdout.md` | Stage-1 baseline, 20-image / full-20 / holdout runs |
| `RESULTS_phase3.md` | Position/Structure (sender/recipient) design + first results |
| `RESULTS_phase4_domain.md` | 7-class domain taxonomy |
| `RESULTS_phase5.md` / `RESULTS_phase6.md` | Domain-aware interpretation (merged into Phase 7) |
| `RESULTS_phase7.md` | Field Semantics declarative table |
| `RESULTS_phase8.md` | Contact org / phone selection |
| `RESULTS_phase9.md` | First end-to-end live-OCR eval |
| `RESULTS_phase10_recipient.md` | Recipient error analysis + the block-selection fix (69.4% → 81.6%) |
| `RESULTS_native_vs_pipeline.md` | Hunyuan direct-answer (combined prompt) vs rules — 41.0% vs 83.2% |
| `RESULTS_native_split_question.md` | Direct-answer, one field per call — 44.5% vs 83.2% |
| `RESULTS_fallback_on_null.md` | "Ask Hunyuan only when rules say null" — net negative, not adopted |
| `RESULTS_paddleocr_vs_hunyuan_frontend.md` | PaddleOCR vs HunyuanOCR as OCR front-end — 70.5% vs 87.6%, re-test pending |
| `FROZEN.md` | What "frozen" means for this codebase + the checksum process |

`docs/PHASE9_OCR_CONTRACT.md` and `docs/PHASE9B_GPU_FEASIBILITY.md` are
design docs, not results.

## Repo layout

```
server/api.py                          FastAPI: /v1/ocr, /v1/analyze, /v1/understand-letter (legacy, not used)
webapp/index.html                      V0 tester UI (static, no build)
evaluation/spatial_field_extraction/   Phase 3-8 pipeline + frozen_phase3/ snapshot + benchmark/comparison scripts
experiments/                           GPU feasibility baseline (run00, read-only) + bench_harness.py (for run01)
docs/                                  OCR contract, GPU feasibility write-up
models/                                HunyuanOCR GGUF weights (not tracked in git — see .gitignore)
```
