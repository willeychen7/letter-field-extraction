"""
Stage 2 (NOT YET EXECUTED) — batch HunyuanOCR-1.5 doc_parse over demo_image/.

Scope, deliberately narrow:
  - One independent request per image, official doc_parse prompt only
    (verbatim from Tencent-Hunyuan/HunyuanOCR inference/utils/tasks.py).
  - No V5, no PaddleOCR, no regex, no PII redaction, no spatial matching,
    no second-pass OCR, no Claude/OpenAI, no output post-processing of any
    kind (no correction, no summarization, no translation).
  - Does not touch anything under mama-helper/ — only reads images from
    demo_image/ and writes results under this experiment directory.

Usage (when explicitly asked to run stage 2):
    python3 batch_doc_parse.py \
        --images-dir /Users/willeychen/Desktop/mama-helper/demo_image \
        --out-dir /Users/willeychen/Desktop/hunyuan-service/results/doc_parse_batch_20 \
        --base-url http://127.0.0.1:8090/v1

Per-image output: <out-dir>/raw/<image_stem>.json (full server response,
untouched) and <out-dir>/raw/<image_stem>.md (raw content field only).
Summary: <out-dir>/summary.csv and <out-dir>/summary.json.
"""

import argparse
import base64
import csv
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

DOC_PARSE_PROMPT = (
    "提取文档图片中正文的所有信息用markdown格式表示，"
    "其中页眉、页脚部分忽略，表格用html格式表达，"
    "文档中公式用latex格式表示，按照阅读顺序组织进行解析。"
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _image_data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _call_server(base_url: str, image_path: str, timeout: int) -> dict:
    payload = {
        "model": "HYVL",
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_uri(image_path)}},
                    {"type": "text", "text": DOC_PARSE_PROMPT},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _list_images(images_dir: str) -> list:
    names = sorted(os.listdir(images_dir))
    return [n for n in names if os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS]


def run(images_dir: str, out_dir: str, base_url: str, timeout: int, max_images: int | None):
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    images = _list_images(images_dir)
    if max_images is not None:
        images = images[:max_images]

    rows = []
    for name in images:
        stem = os.path.splitext(name)[0]
        image_path = os.path.join(images_dir, name)
        print(f"=== {name} ===")

        row = {
            "image": name,
            "status": None,
            "inference_time_s": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "finish_reason": None,
            "error": None,
        }

        t0 = time.perf_counter()
        try:
            resp = _call_server(base_url, image_path, timeout)
            elapsed = time.perf_counter() - t0

            content = resp["choices"][0]["message"]["content"]
            usage = resp.get("usage", {})

            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
            with open(os.path.join(raw_dir, f"{stem}.md"), "w") as f:
                f.write(content)

            row.update(
                status="ok",
                inference_time_s=round(elapsed, 3),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                finish_reason=resp["choices"][0].get("finish_reason"),
            )
            print(f"  ok, {elapsed:.2f}s, finish_reason={row['finish_reason']}")
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            elapsed = time.perf_counter() - t0
            row.update(status="error", inference_time_s=round(elapsed, 3), error=str(e))
            print(f"  ERROR: {e}")

        rows.append(row)

    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "summary.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n[total] {len(rows)} images, {ok} ok, {len(rows) - ok} errors")
    print(f"[summary] {os.path.join(out_dir, 'summary.csv')}")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images-dir", default="/Users/willeychen/Desktop/mama-helper/demo_image")
    p.add_argument("--out-dir", default="/Users/willeychen/Desktop/hunyuan-service/results/doc_parse_batch_20")
    p.add_argument("--base-url", default="http://127.0.0.1:8090/v1")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--max-images", type=int, default=None, help="cap for a quick trial run")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.images_dir, args.out_dir, args.base_url, args.timeout, args.max_images)
