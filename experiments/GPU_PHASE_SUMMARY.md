# GPU Phase — Summary

Summary only. No code, no benchmark data, and no experiments were changed
or created for this document.

Scope: whether the **runtime** (HunyuanOCR GGUF + llama.cpp on a GPU) is
fast and stable enough to keep experimenting on. It is NOT a judgement of
OCR output quality on GPU — run00's output is not usable as-is (wrong
prompt), so a like-for-like accuracy run (run01) is still pending.

---

## 1. GPU / Runtime

| item | value |
|---|---|
| model | **HunyuanOCR-1B**, arch `hunyuan_vl` (24 layers, hidden 1024, train ctx 32768) |
| GGUF (text) | `HunyuanOCR-Q8_0.gguf` — **561 MB**, Q8_0 |
| mmproj (vision) | `mmproj-HunyuanOCR-Q8_0.gguf` — **699 MB**, arch `clip`, image_size 2048 |
| weights total | ≈ **1.26 GB** |
| llama.cpp | CUDA server build (inferred — the run loaded `hunyuan_vl` + `mmproj`, did multimodal inference, emitted `TEXT(x,y),(x,y)` coords on 3 images; the CSV does not record the exact build/tag) |
| Metal / GPU working? | **GPU: yes.** Multimodal inference ran on all 49 images at 0.4–12 s each with **0 container crashes**. (Metal = the retired Mac-native path, not part of this phase.) |
| runtime env | **user-run on a free NVIDIA GPU** (Colab / Kaggle T4-class, per the agreed plan). Exact instance / driver / build not recorded in `hunyuan_gpu_benchmark_49.csv`. |
| server context in this run | `--ctx-size` ≈ **2816–4096** (from the HTTP-400 messages) — too small; frozen `ocr.py` expects ≥ 8192 |

---

## 2. Benchmark (`hunyuan_gpu_benchmark_49.csv`, run00)

| metric | value |
|---|---|
| images tested | **49** (the fixed Phase-9 set, minus SoCalGas which CPU had lost — list frozen in `benchmark_49_files.txt`) |
| success / fail (HTTP) | **46 / 3** |
| failures | `Progressive_Insurance_Bill.jpg`, `aaa-policy_renew.jpg`, `ca-dmv-registration-fee.webp` — all HTTP 400 `exceed_context_size` |
| latency (all 49) | mean **4.19 s** · median **3.81 s** · min 0.42 s · p90 6.85 s · **max 12.38 s** |
| latency (46 success) | mean 4.42 s · median 4.00 s · max 12.38 s |
| prompt tokens | mean **1109** · min 292 · max 2437 |
| completion tokens | mean **499** · min 5 · max 2272 |
| truncated (`finish=length`) | **2** — `DMV_registration_late_fee.webp`, `EastWest_Bank_Form.png` |
| repetition | **2** — *same 2 files* (the truncation is a repeat-loop hitting the cap) |
| main failure causes | (a) **context too small** → 3× HTTP 400 on large / high-res images; (b) **wrong prompt** → 0/49 in clean spotting format; (c) **repetition loop** → 2× truncated on sparse/redacted forms |

vs the CPU Docker run (Phase 9): median 61 s, max 294 s, 2 crashes, 1 total
loss. **GPU ≈ 16× faster, 0 crashes.**

---

## 3. Verified capabilities

| capability | status | evidence |
|---|---|---|
| HunyuanOCR runs stably on a local GPU | **YES** | 46/49 HTTP 200, 0 crashes, ~4 s median, model + mmproj loaded |
| document parsing (`doc_parse` markdown) | **YES, works** | 21/49 returned clean markdown transcription (`# Title`, `\| … \|` tables) |
| spotting / bbox (`TEXT(x,y),(x,y)`) | **PARTIAL / unproven** | only 3/49 emitted coordinates, and wrapped in `<hy-meta><poly>` layout blocks. Run00 did not use the frozen spotting prompt, so GPU spotting output is **not yet validated** for the pipeline contract |
| batch processing | **YES** | 49 sequential requests completed in one run, no restart needed |

---

## 4. Known problems found

| problem | detail |
|---|---|
| `.webp` / `.avif` input | run00 sent `.webp` files directly and they were accepted by this GPU build (no failures attributable to format). Still, `bench_harness.py` converts webp/avif → PNG defensively; the safe assumption remains **convert client-side**. |
| long document / context | `--ctx-size` 2816–4096 is too small: large/high-res images produce 3000–4090 prompt tokens → hard HTTP 400 before inference. Must run llama-server with **`--ctx-size ≥ 8192`**. |
| repetition | small model loops on **sparse / redacted forms** (`$XXX`, `XX/XX/XX` rows) until it hits `max_tokens`. 2/49. Needs a repeat penalty or a bounded-output prompt. |
| prompt → result | **the dominant finding.** Same model, same images: the prompt used in run00 (not the frozen `spotting_hunyuan` one) produced `doc_parse` markdown (21), `layout_parse` `<hy-meta>` (3), plain text (16), NL summaries (4), a `<dir>0</dir>` tag (1), `图片中没有文字。` (1, correct for a food photo), empty (3). **0 in the format `parse_ocr_elements` needs.** |
| CSV provenance | `hunyuan_gpu_benchmark_49.csv` does not record the GPU model, llama.cpp build/tag, ctx-size, or the exact prompt used. Future runs (via `bench_harness.py`) capture `prompt_mode / ctx_size / max_tokens` columns. |

---

## 5. GPU Phase conclusion

- **Is the GPU / runtime good enough to keep experimenting on?**
  **YES.** ~4 s median, 12 s worst, 0 crashes over 49 images, model +
  mmproj load fine, batch runs complete. The 10–20 s "usable" bar is met
  with margin.
- **Is further GPU / runtime optimisation needed?**
  **NO.** Every issue in run00 (context 400s, truncation, repetition,
  wrong output shape) is a **request-config** problem — `--ctx-size`,
  `max_tokens`, repeat penalty, and the prompt — not a GPU or llama.cpp
  problem. Those are dialled in the *next* experiment (run01), not by
  touching the runtime.

> **`GPU Phase: CLOSED / BASELINE ESTABLISHED`**
>
> Runtime speed + stability are proven. GPU OCR **output correctness** is
> not yet proven (run00 used the wrong prompt) — that is run01's job, not
> a GPU-phase item.

---

## 6. Baseline artifacts to keep

| file | what it is | keep? |
|---|---|---|
| `hunyuan_gpu_benchmark_49.csv` (repo root) | **the original run00 CSV** — 49 rows, GPU, as produced by the user | **KEEP, never modify.** This is the baseline of record. |
| `experiments/run00_baseline/hunyuan_gpu_benchmark_49.csv` | read-only (chmod 444) copy of the above, md5 `0e916094cca0ebaa53cbd97dac90d081` | KEEP — integrity copy |
| `experiments/run00_baseline/ANALYSIS.md` | per-image failure breakdown + root causes for run00 | KEEP |
| `experiments/run00_baseline/failure_breakdown.json` | machine-readable bucket list (A context / B truncated / C format / D semantic) | KEEP |
| `experiments/benchmark_49_files.txt` | the frozen 49-filename list — every future run uses exactly these | KEEP |
| `experiments/bench_harness.py` | parametrised runner for run01+ (`--prompt spotting\|json_schema`, `--ctx-size`, `--max-tokens`); writes to `experiments/<run_id>/results.csv`, refuses to overwrite the baseline | KEEP (not run yet) |
| `experiments/README.md` | experiment log / run table / how-to-run | KEEP |
| `gpu_smoketest/colab_hunyuan_gpu_smoketest.py` + `README.md` | the single-image Colab smoke-test notebook (superseded by run00, kept for reference) | KEEP |
| `docs/PHASE9B_GPU_FEASIBILITY.md` | the pre-run GPU feasibility assessment | KEEP |
| `docs/PHASE9_OCR_CONTRACT.md` | the `{text,bbox}` OCR-endpoint contract | KEEP |

**Not overwritten, not deleted.** No new benchmark data was produced by
this summary.

---

## GPU Phase Status

- **Status:** `CLOSED / BASELINE ESTABLISHED`
- **What was proven:** HunyuanOCR-1B GGUF (Q8_0) + mmproj runs on a free
  NVIDIA GPU via llama.cpp — median ~4 s, max ~12 s, **0 crashes** over 49
  images (CPU Docker was median 61 s / max 294 s / 2 crashes). Batch
  processing and `doc_parse` markdown output both work.
- **Known limitations:** run00 used the wrong prompt + a too-small
  context, so **spotting / `{text,bbox}` output on GPU is not yet
  validated**; 3 context-overflow 400s (ctx 2816–4096); 2
  truncation/repetition loops on sparse forms; CSV lacks provenance
  (prompt / build / ctx).
- **Baseline files:** `hunyuan_gpu_benchmark_49.csv` (root, original) ·
  `experiments/run00_baseline/` (analysis + read-only copy) ·
  `experiments/benchmark_49_files.txt` (frozen 49-image list).
- **Next phase:** run01 — re-run all 49 with the **frozen
  `spotting_hunyuan` prompt** + `--ctx-size 8192` + `max_tokens 8192`;
  then run02 — fixed JSON-schema extraction. Both via
  `experiments/bench_harness.py`, results as `experiments/<run_id>/results.csv`.
  (Not started.)
