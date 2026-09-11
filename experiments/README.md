# hunyuan-service · experiments

Benchmark runs of HunyuanOCR (GGUF + llama.cpp) on a **fixed 49-image set**.
The image list is frozen in `benchmark_49_files.txt` so every run is
directly comparable.

**Rules**
- The baseline (`../hunyuan_gpu_benchmark_49.csv`, repo root) is **never
  modified or overwritten**. A read-only copy is in `run00_baseline/`.
- Every new run gets its own `<run_id>/` dir and a `results.csv` carrying
  `experiment · run_id · prompt_mode · ctx_size · max_tokens` columns.
- No changes to Phase 3–8, the `ocr.py` OCR prompt, the GGUF models, or
  mama-helper. `bench_harness.py --prompt spotting` uses the **verbatim**
  frozen `SPOTTING_HUNYUAN_PROMPT`.

---

## Runs

| run_id | prompt | ctx | max_tok | env | status | notes |
|---|---|---|---|---|---|---|
| **run00_baseline** | *doc_parse / layout / freeform (NOT spotting)* | ~2816–4096 | ? | GPU (Colab/Kaggle) | ✅ done | speed great (median 3.8 s, 0 crashes); **output unusable** — 0/49 clean spotting format, 3 context-overflow, 2 truncated+repetition. See `run00_baseline/ANALYSIS.md` |
| **run01_spotting_ctx8192** | `spotting` (frozen, verbatim) | 8192 | 8192 | GPU | ⏳ to run | **re-run all 49** with the correct prompt + fixed context. This is the real like-for-like vs Phase 9. |
| **run02_json_schema** | `json_schema` (experimental) | 8192 | 2048 | GPU | ⏳ to run | direct structured extraction, bypasses Phase 3–8, for comparison |

---

## How to run the next rounds (on the GPU box / Colab, llama-server on :8090)

Start llama-server with the **matching context**:

```
llama-server -m HunyuanOCR-Q8_0.gguf --mmproj mmproj-HunyuanOCR-Q8_0.gguf \
  -ngl 99 --ctx-size 8192 --parallel 2 --host 127.0.0.1 --port 8090
```

### run01 — spotting prompt, ctx 8192 (all 49)

```
python3 bench_harness.py --run-id run01_spotting_ctx8192 \
  --prompt spotting --ctx-size 8192 --max-tokens 8192 \
  --server http://127.0.0.1:8090/v1 \
  --images-dir <demo_image dir> --images-dir <holdout_images dir>
```

Also acceptable if only re-checking the long-doc failures first:

```
python3 bench_harness.py --run-id run01_spotting_ctx8192 --prompt spotting \
  --ctx-size 8192 --max-tokens 8192 --server http://127.0.0.1:8090/v1 \
  --only Progressive_Insurance_Bill.jpg aaa-policy_renew.jpg \
         ca-dmv-registration-fee.webp DMV_registration_late_fee.webp \
         EastWest_Bank_Form.png
```

### run02 — fixed JSON schema

```
python3 bench_harness.py --run-id run02_json_schema \
  --prompt json_schema --ctx-size 8192 --max-tokens 2048 \
  --server http://127.0.0.1:8090/v1 \
  --images-dir <demo_image dir> --images-dir <holdout_images dir>
```

Results land in `experiments/run01_spotting_ctx8192/results.csv` and
`experiments/run02_json_schema/results.csv` — the baseline stays put.

---

## Comparing a new run to baseline

`compare_runs.py <run00_baseline/…csv> <runNN/results.csv>` (added when the
first new run exists) — per-image diff of `content_shape`, `truncated`,
`repetition`, `latency`, and (for spotting runs) whether
`parse_ocr_elements` now yields clean `{text,bbox}`.
