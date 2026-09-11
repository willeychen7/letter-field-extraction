# run00 — GPU baseline (`hunyuan_gpu_benchmark_49.csv`)

Original CSV: `../../hunyuan_gpu_benchmark_49.csv` (repo root) — **untouched**.
Read-only copy + this analysis live here. Nothing is overwritten.

---

## Headline

| | run00 GPU | (for reference: Phase 9 CPU Docker) |
|---|---|---|
| **speed** | median **3.81 s** · mean 4.19 s · p90 6.85 s · **max 12.38 s** · min 0.42 s | median 61 s · max 294 s |
| **container crashes** | **0** / 49 | 2 (+ SoCalGas total loss) |
| HTTP failures | 3 (all `exceed_context_size`, HTTP 400) | 1 (crash) |

**GPU fixed speed and stability, decisively.** But this run's OCR output is
**unusable for the frozen pipeline** — see below.

---

## The run used the WRONG request config

Evidence from the `content` column:

| image | content shape | means |
|---|---|---|
| `hoag`, `DMV_Notice`, `waste_managment` | `<hy-meta><layout>…</layout><poly>(x,y)…</poly></hy-meta>` … | HunyuanOCR **`layout_parse`** task output |
| `DMV_registration_late_fee`, `AAA`, `BOA`, `HOA*` … | `# Title` / `\| VIN \| MAKE \|` markdown / plain text lines | **`doc_parse`** task output (markdown transcription, **no bbox**) |
| `Auto_Insurance`, `SCE_Letter`, `IRS_CP504`, `Medicare_of_Denial` | *"The text in the image is a detailed policy information page…"* | model **summarised** the doc instead of transcribing |
| `All_State` | `<dir>0</dir>` | reading-direction tag, degenerate |
| `food1` | `图片中没有文字。` | correct (it's a food photo) |
| errors | `n_ctx: 2816` / `n_ctx: 4096` in the 400 messages | server started with a **tiny context** (2816–4096) |

**None of the 49 produced the clean `spotting_hunyuan` format
`TEXT(x1,y1),(x2,y2)` that `ocr.py::parse_ocr_elements` needs.** The 3
`<hy-meta>` ones carry *some* inline coords but wrapped in layout blocks.

Two independent config regressions vs the frozen `ocr.py`:

1. **Wrong prompt.** Frozen `ocr.py` sends verbatim
   `检测并识别图片中的文字，将文本坐标格式化输出。` (the official
   `spotting_hunyuan` task). run00's outputs are `doc_parse` /
   `layout_parse` / freeform — a different prompt was used.
2. **Context far too small** (`--ctx-size` ≈ 2816–4096). Frozen `ocr.py`
   needs ≥ 8192; large / high-res images here hit 3027–4090 prompt tokens
   → HTTP 400 before inference.

The CUDA build itself is fine — `hoag` / `DMV_Notice` / `waste_managment`
prove `hunyuan_vl` + this mmproj *can* emit coordinates on GPU.

---

## 1. Which images "failed", and 2. failure type

| bucket | count | images | root cause |
|---|---:|---|---|
| **A · context 超限** (HTTP 400 `exceed_context_size`) | **3** | `Progressive_Insurance_Bill`, `aaa-policy_renew`, `ca-dmv-registration-fee` | `--ctx-size` 2816–4096; these images = 3027 / 3027 / 4089 prompt tokens |
| **B · truncated** (`finish_reason=length`) | **2** | `DMV_registration_late_fee` (2272 ctok), `EastWest_Bank_Form` (1997 ctok) | ran to the token cap |
| **C · repetition** (loop until cap) | **2** | *same 2 as B* — `DMV_registration_late_fee`, `EastWest_Bank_Form` | small model loops on sparse / redacted forms (`$XXX` `XX/XX/XX` rows repeated) |
| **D · semantic — wrong task / degenerate** | **6** | `Auto_Insurance_Bill1`, `IRS_CP504_Notice`, `Medicare_Notice_of_Denial`, `SCE_Letter` (NL summary instead of OCR) · `All_State_Insurance_Card` (`<dir>0</dir>`) · `food1` (`图片中没有文字。` — actually correct) | prompt ambiguity → model describes/analyses instead of transcribing |
| **C₂ · wrong output format** (transcribed, but no `{text,bbox}`) | **~38** | everything not in A/B/D | wrong prompt → `doc_parse` / `layout_parse` markdown/plain-text, no coordinates |
| **OK · clean spotting format** | **0** | — | — |

(B and C are the **same 2 files** — a truncated run here is a repetition
loop that hit the limit.)

### Distinguishing the four the way you asked

- **context 超限**: 3 — `Progressive`, `aaa-policy_renew`, `ca-dmv-registration-fee`.
  Hard 400, never inferred. Fix = raise `--ctx-size` to ≥ 8192.
- **truncated**: 2 — `DMV_registration_late_fee`, `EastWest_Bank_Form`.
  `finish_reason=length`. Fix = raise `--max-tokens` **and** stop the loop.
- **repetition**: 2 — same 2. The truncation *is* a repetition loop.
  Fix = `--repeat-penalty` / `--dry-multiplier`, or the JSON-schema prompt
  (bounded output).
- **语义理解错误**: 6 — model summarised (`Auto_Insurance`, `IRS_CP504`,
  `Medicare_of_Denial`, `SCE_Letter`) or emitted a control tag
  (`All_State`). `food1` is a false positive (no text → correct answer).
  Fix = the exact frozen `spotting_hunyuan` prompt, `temperature 0`.

---

## What this means for the next round

The baseline is **not a like-for-like OCR run** — it used a different task
prompt and a broken context size. So run01 must **re-run all 49** with the
frozen `spotting_hunyuan` prompt + `--ctx-size 8192`, not just the 5
long-doc failures, before any comparison to Phase 9 accuracy is valid.

Then run02 tests the JSON-schema idea as a *separate* config.
