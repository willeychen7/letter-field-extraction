"""
Model A/B test: Qwen3-VL 8B vs HunyuanOCR-1B baseline.

Reuses, unchanged:
  - the exact 6-image sample from single_field_test/
  - the exact 8 field prompts from single_field_test/prompts.json
  - single-field-per-request methodology (no JSON, no batching, no
    cross-question context, temperature=0)

Only variable changed: the model. Qwen3-VL 8B runs locally via Ollama
(http://127.0.0.1:11434/v1/chat/completions, OpenAI-compatible), same
machine, no cloud call, no mama-helper/V5/Hunyuan-service code touched.

This is a benchmark script only -- no product integration.
"""
import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

SINGLE_FIELD_DIR = "/Users/willeychen/Desktop/hunyuan-service/evaluation/single_field_test"
PROMPTS = json.load(open(os.path.join(SINGLE_FIELD_DIR, "prompts.json")))

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
BASE_URL = "http://127.0.0.1:11434/v1"
MODEL = "qwen3-vl:8b"

# Identical to single_field_test/run.py::SAMPLE_IMAGES
SAMPLE_IMAGES = [
    "SCE_Bill_Letter.png",
    "Hospital_Bill.png",
    "Medical_Invoice.png",
    "BOA_Bill_Example.png",
    "Medicare_Notice_PartA.png",
    "IRS_cp503.png",
]


def _uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def call(path, question, timeout=180):
    payload = {
        "model": MODEL, "temperature": 0.0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _uri(path)}},
            {"type": "text", "text": question},
        ]}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    raw_dir = os.path.join(OUT_DIR, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    results = {}
    for name in SAMPLE_IMAGES:
        path = os.path.join(IMAGES_DIR, name)
        stem = os.path.splitext(name)[0]
        print(f"\n=== {name} ===")
        results[name] = {}
        raw_responses = {}
        for field, question in PROMPTS.items():
            t0 = time.perf_counter()
            try:
                resp = call(path, question)
                elapsed = time.perf_counter() - t0
                content = resp["choices"][0]["message"]["content"].strip()
                results[name][field] = content
                raw_responses[field] = resp
                print(f"  {field:16s}: {content[:200]!r}   ({elapsed:.1f}s)")
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                results[name][field] = f"ERROR: {e}"
                print(f"  {field:16s}: ERROR: {e}")
        with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
            json.dump(raw_responses, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[done] -> {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
