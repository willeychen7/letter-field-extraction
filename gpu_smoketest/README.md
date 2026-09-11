# GPU Smoke Test — status

## I cannot run this myself. Stopping here as instructed.

The free-GPU smoke test needs a Google Colab session, and I can't operate one:

| blocker | detail |
|---|---|
| **No local GPU** | this Mac is Apple M4 (Metal only); `nvidia-smi` absent; Docker here has no NVIDIA runtime → no CUDA path locally |
| **No paid GPU** | per your instruction — not renting one |
| **Colab needs your Google login** | I must not enter credentials or drive an authenticated Google session |
| **The 1.3 GB of GGUF files are local** | `HunyuanOCR-Q8_0.gguf` (578 MB) + `mmproj-HunyuanOCR-Q8_0.gguf` (733 MB) live on this Mac; a Colab runtime can't read the local filesystem, and I can't reliably drive a 1.3 GB browser upload |

## What I've prepared for you

`colab_hunyuan_gpu_smoketest.py` — a 7-cell Colab notebook that does the whole
test with **zero changes** to Phase 3–8 / the OCR prompt / the OCR algorithm /
the GGUF files. Same `HunyuanOCR-Q8_0.gguf` + `mmproj-HunyuanOCR-Q8_0.gguf` +
the exact `spotting_hunyuan` prompt (`检测并识别图片中的文字，将文本坐标格式化输出。`).

### To run it (≈15 min, free T4)

1. Open <https://colab.research.google.com> → **New notebook**
2. **Runtime → Change runtime type → T4 GPU**
3. Paste each `# ==== CELL N ====` block from `colab_hunyuan_gpu_smoketest.py`
   into its own cell, run top to bottom.
4. **CELL 3** — get the two GGUF files onto Colab. Pick one:
   - **3A (best)**: if you know the Hugging Face repo you downloaded them from
     on Sep 4, fill `HF_REPO` and uncomment 3A — no upload, pulls from HF CDN.
   - **3B**: put both `.gguf` files in a Google Drive folder, set `SRC`,
     uncomment 3B.
   - **3C**: direct `files.upload()` of both files (1.3 GB, slow, last resort).
   The cell asserts the file sizes match production byte-for-byte
   (`577949408` / `732938240`) — if they don't, it stops.
5. **CELL 5** — upload ONE real letter (e.g. `AAA_insurance_Bill.png`).

### What it prints (the 7 things you asked to verify)

1. Colab NVIDIA GPU — `nvidia-smi` table (expect `Tesla T4`, ~15 GB)
2. llama.cpp CUDA build runs — server comes up
3. `hunyuan_vl` loads — load log with `offloaded NN/NN layers to GPU`
4. mmproj works — `loaded multimodal model` + real coordinates in the output
5. one real letter OCRs — success + element count
6. OCR latency — one number, next to "CPU Docker was median 61s / max 294s"
7. `{text, bbox}` contract — asserts every element is exactly `{bbox, text}`,
   bbox length 4, no `confidence`, no `page`; plus `truncated` flag and
   `raw_content` captured

### If it fails

- **CELL 1 says no GPU** → Colab isn't giving a free GPU right now; tell me, we
  pick another free option.
- **CELL 4 llama-server won't start** → paste me the load log. That's where a
  `hunyuan_vl` / mmproj CUDA-build incompatibility would show — do NOT change
  the model or pipeline; send me the exact error.
- **CELL 6 assertion fails** → the CUDA build changed the output format; send me
  `raw_content[:400]` and the element dump.

Then paste the CELL 7 verdict back to me and I'll write the CPU-vs-GPU
comparison + answer whether GPU actually fixes the bottleneck.
