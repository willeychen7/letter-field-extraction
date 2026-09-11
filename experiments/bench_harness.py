"""
Parametrised HunyuanOCR benchmark harness (experiment runner).

Runs the SAME fixed 49 images as run00 baseline, against a llama.cpp
server, and writes a CSV that ALIGNS with the baseline (same base columns)
plus experiment-identifier columns. Never touches:
  - hunyuan_gpu_benchmark_49.csv           (repo root, the baseline)
  - experiments/run00_baseline/*
  - Phase 3-8 code, the OCR prompt in ocr.py, the GGUF models, mama-helper

Two prompt modes:
  --prompt spotting     -> the VERBATIM frozen ocr.py::SPOTTING_HUNYUAN_PROMPT
  --prompt json_schema  -> a fixed JSON-schema structured-extraction prompt
                           (experimental; bypasses Phase 3-8, for comparison)

Usage (run on the GPU box / Colab, next to a llama-server on :8090):
    python3 bench_harness.py --run-id run01_spotting_ctx8192 \
        --prompt spotting --ctx-size 8192 --max-tokens 8192 \
        --server http://127.0.0.1:8090/v1 \
        --images-dir /path/to/demo_image --images-dir2 /path/to/holdout_images

Output: experiments/<run-id>/results.csv  (+ raw/<file>.txt per image)
"""
import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [ln.strip() for ln in open(os.path.join(HERE, "benchmark_49_files.txt"))
         if ln.strip()]

# --- frozen prompt, copied verbatim from evaluation/.../ocr.py (do not edit) --
SPOTTING_HUNYUAN_PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"

# --- experimental fixed JSON schema (NOT frozen; the point of experiment 2) ---
JSON_SCHEMA_PROMPT = (
    "阅读这张信件图片，只输出下面这个 JSON（不要输出 JSON 以外的任何内容）。"
    "字段在图片中找不到就填 null，不要猜测。金额保留原始写法（含符号）。"
    "日期用 YYYY-MM-DD。\n"
    '{"sender":null,"recipient":null,"document_type":null,'
    '"total_amount_due":null,"due_date":null,"statement_date":null,'
    '"payment_status":null,"action_required":null,'
    '"contact_organization":null,"contact_phone":null}'
)
PROMPTS = {"spotting": SPOTTING_HUNYUAN_PROMPT, "json_schema": JSON_SCHEMA_PROMPT}


def _resolve(fname, dirs):
    stem, ext = os.path.splitext(fname)
    for d in dirs:
        for e in (ext, ".png", ".jpg", ".jpeg", ".webp", ".avif"):
            p = os.path.join(d, stem + e)
            if os.path.exists(p):
                return p
    return None


def _data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".webp", ".avif"):
        # content-preserving convert so the loader accepts it
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.open(path).convert("RGB").save(buf, format="PNG")
        raw, mime = buf.getvalue(), "image/png"
    else:
        raw = open(path, "rb").read()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


_COORD = re.compile(r"\(\d+,\s*\d+\),\(\d+,\s*\d+\)")


def _flags(content, finish_reason):
    c = content or ""
    truncated = finish_reason == "length"
    # crude repetition check: a >=25-char line repeated >=4x
    lines = [ln.strip() for ln in c.splitlines() if len(ln.strip()) >= 25]
    rep = False
    if lines:
        from collections import Counter
        rep = max(Counter(lines).values()) >= 4
    coord_groups = len(_COORD.findall(c))
    has_meta = "<hy-meta>" in c or "<poly>" in c
    if not c.strip():
        shape = "EMPTY"
    elif coord_groups >= 3 and not has_meta:
        shape = "SPOTTING_COORD"
    elif has_meta:
        shape = "LAYOUT_PARSE"
    elif c.strip().startswith("{") or c.strip().startswith("```json"):
        shape = "JSON"
    elif re.match(r"(the (text|image|document)|this (image|document))", c.strip().lower()):
        shape = "NL_DESCRIPTION"
    elif c.lstrip().startswith("#") or "| " in c:
        shape = "DOC_PARSE_MD"
    else:
        shape = "PLAIN_TEXT"
    return truncated, rep, coord_groups, shape


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--prompt", choices=list(PROMPTS), required=True)
    ap.add_argument("--server", default="http://127.0.0.1:8090/v1")
    ap.add_argument("--ctx-size", type=int, default=8192,
                    help="informational only -- start llama-server with this")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--images-dir", action="append", default=[])
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to these filenames (e.g. re-run the failures)")
    args = ap.parse_args()

    dirs = args.images_dir or [
        "/Users/willeychen/Desktop/mama-helper/demo_image",
        os.path.join(HERE, "..", "evaluation", "spatial_field_extraction", "holdout_images"),
    ]
    out_dir = os.path.join(HERE, args.run_id)
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "results.csv")
    assert os.path.abspath(csv_path) != os.path.join(HERE, "..", "hunyuan_gpu_benchmark_49.csv"), \
        "refusing to overwrite the baseline"

    prompt_text = PROMPTS[args.prompt]
    targets = FILES if not args.only else [f for f in FILES if f in set(args.only)]

    cols = ["experiment", "run_id", "prompt_mode", "ctx_size", "max_tokens",
            "index", "filename", "latency_sec", "http_status", "success",
            "prompt_tokens", "completion_tokens", "finish_reason",
            "truncated", "repetition", "coord_groups", "content_shape",
            "content", "error"]
    w = csv.DictWriter(open(csv_path, "w", newline=""), fieldnames=cols)
    w.writeheader()

    for i, fname in enumerate(targets, 1):
        path = _resolve(fname, dirs)
        row = {"experiment": "phase9b_gpu", "run_id": args.run_id,
               "prompt_mode": args.prompt, "ctx_size": args.ctx_size,
               "max_tokens": args.max_tokens, "index": i, "filename": fname,
               "latency_sec": "", "http_status": "", "success": False,
               "prompt_tokens": "", "completion_tokens": "", "finish_reason": "",
               "truncated": False, "repetition": False, "coord_groups": 0,
               "content_shape": "", "content": "", "error": ""}
        if path is None:
            row["error"] = "image not found"
            w.writerow(row); print(f"[{i}/{len(targets)}] {fname}: NOT FOUND"); continue

        payload = {"model": "HYVL", "temperature": args.temperature,
                   "max_tokens": args.max_tokens,
                   "messages": [{"role": "user", "content": [
                       {"type": "image_url", "image_url": {"url": _data_uri(path)}},
                       {"type": "text", "text": prompt_text}]}]}
        req = urllib.request.Request(f"{args.server}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.perf_counter()
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
            row["latency_sec"] = round(time.perf_counter() - t0, 3)
            row["http_status"] = 200
            ch = resp["choices"][0]
            content = ch["message"]["content"]
            fr = ch.get("finish_reason", "")
            usage = resp.get("usage", {})
            row["prompt_tokens"] = usage.get("prompt_tokens", "")
            row["completion_tokens"] = usage.get("completion_tokens", "")
            row["finish_reason"] = fr
            row["success"] = True
            row["content"] = content
            tr, rep, cg, sh = _flags(content, fr)
            row["truncated"], row["repetition"] = tr, rep
            row["coord_groups"], row["content_shape"] = cg, sh
            open(os.path.join(raw_dir, fname + ".txt"), "w").write(content)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            row["latency_sec"] = round(time.perf_counter() - t0, 3)
            row["http_status"] = e.code
            row["error"] = body[:500]
        except Exception as e:  # noqa: BLE001
            row["latency_sec"] = round(time.perf_counter() - t0, 3)
            row["error"] = f"{type(e).__name__}: {e}"
        w.writerow(row)
        print(f"[{i}/{len(targets)}] {fname:34s} {row['latency_sec']:>7}s "
              f"http={row['http_status']} shape={row['content_shape']} "
              f"trunc={row['truncated']} rep={row['repetition']} "
              f"coords={row['coord_groups']}", flush=True)

    print(f"\n[out] {csv_path}")


if __name__ == "__main__":
    main()
