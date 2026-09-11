# Earlier experiments (pre-`spatial_field_extraction/`)

These directories predate the OCR-then-rules architecture and this status
doc. They're the capability probe that led to it: a systematic attempt to
find *some* way to get HunyuanOCR to answer structured fields directly,
before the project settled on "OCR only for text+bbox, a separate
deterministic rules layer does the judgment" (see the main
`PROJECT_STATUS.md` and `RESULTS_native_vs_pipeline.md` for why that
settled question was re-confirmed later at full scale).

Read-only summary — reconstructed from each script's own docstring and its
`results/summary.json`, nothing re-run or re-scored for this note.

| Directory | What it tested | What came back |
|---|---|---|
| `spotting_eval/` | Official `spotting_json` prompt (verbatim from Tencent's own task list) for text+bbox, 20 images | **0/20 clean JSON.** 10/20 malformed with no bbox, 8/20 needed a regex fallback to salvage anything, 2/20 total parse failure. This is almost certainly why the project later moved to the plain-string `spotting_hunyuan` prompt (`"检测并识别图片中的文字，将文本坐标格式化输出。"`) that `ocr.py` uses now — the "official" JSON-schema spotting mode was unreliable. |
| `information_extraction_eval/` | Official IE prompt pattern, 9 fields in one JSON call, 20 images | 20/20 valid JSON, fields filled 8.2/9 on average (rarely null) — but per the script's own docstring, sender/recipient direction was wrong in ~60% of checkable cases. High fill-rate, not high correctness — the model fills confidently rather than saying "don't know". Directly foreshadows the 41.0%/31.5%-hallucination result `RESULTS_native_vs_pipeline.md` measured later at full scale. |
| `pii_bbox_eval/` | Custom (not an official Tencent template) schema: joint PII-type + bbox in one pass, 20 images | 20/20 valid JSON, slots filled 6.8/9 on average, but only 2.2/9 were *well-formed* (6.8/9 malformed). Concluded not viable as a local PII-detection layer. |
| `document_understanding_benchmark/` | Official 9-field IE-style prompt, 20 images, output only (no scoring in-script — several fields have no machine-checkable ground truth) | 20/20 valid JSON. No aggregate accuracy computed here; would need manual/image review per the script's own docstring. |
| `document_understanding_v2_explicit_questions/` | Same 9 fields, but the prompt spells out 9 numbered questions before asking for JSON (still one API call) | Ran across the 20-image set (40 output files). No scoring script — raw output only, for manual side-by-side comparison against v1. |
| `full_text_dump_eval/` | Official `structured_parse` prompt (`"提取图中的文字。"`, no formatting requirement) — pure text recognition, formatting-compliance removed as a variable | 37/37 successful responses. Text-recognition-only check, not a field-extraction test. |
| `free_form_understanding/` | No schema at all — "read this letter and explain it in plain language" | Only 4 output files — a small spot-check, not a full batch. Purpose was to separate "does it understand the letter" from "can it follow a strict schema". |
| `single_field_test/` | One field per API call, plain-text answer, no JSON, no cross-question context — 8 fields x a 6-image representative sample | Only 1 output file present — appears to have stopped at an early smoke-test stage rather than completing the planned sample. Its `prompts.json` (8 fields) was later reused verbatim by `qwen3vl_ab_test/`. |
| `qwen3vl_ab_test/` | A/B: Qwen3-VL 8B (local via Ollama) vs HunyuanOCR-1B, reusing `single_field_test`'s exact 6 images + 8 prompts | Only 2 of the 6 images have output (`SCE_Bill_Letter`, `Hospital_Bill`) — matches the project's own instruction early in this history to pause the Qwen3-VL comparison; never completed. |
| `batch_doc_parse.py` (top-level, no results dir) | "Stage 2 — batch `doc_parse` over all of `demo_image/`" | Explicitly marked `NOT YET EXECUTED` in its own docstring. Never run. |

## What this means for anything currently cited from these directories

- Don't cite an accuracy number from these as if it were a validated,
  full-scale result — several never finished their planned sample size,
  and several intentionally have no scoring step (raw output only, by
  design, per their own docstrings).
- The one number worth trusting as-is: **`spotting_eval/`'s 0/20 clean
  JSON rate for the official `spotting_json` prompt** — that's a complete
  20-image run with an unambiguous parse-status field, and it lines up
  with the later architectural choice (a different, plain-string spotting
  prompt) well enough that it's very likely the reason for it.
- If any of these ever need to inform a real decision again, re-run them
  fresh against the current model/server rather than trusting an old
  partial batch.
