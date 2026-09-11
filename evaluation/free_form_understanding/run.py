"""
No-schema, no-format comprehension check: ask Hunyuan to read a letter and
explain it in plain language, with zero JSON/markdown/field requirements.
Purpose: isolate "does it understand the letter" from "can it follow a
strict output schema" -- the two have been getting conflated in every
prior schema-based test.

Does not touch mama-helper. Raw output only, no post-processing.
"""
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.txt")
PROMPT = open(PROMPT_PATH).read().strip()

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
BASE_URL = "http://127.0.0.1:8090/v1"


def _image_data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def call_server(image_path, timeout=180):
    payload = {
        "model": "HYVL",
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_uri(image_path)}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(images):
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in images:
        stem = os.path.splitext(name)[0]
        path = os.path.join(IMAGES_DIR, name)
        print(f"=== {name} ===")
        t0 = time.perf_counter()
        try:
            resp = call_server(path)
            elapsed = time.perf_counter() - t0
            content = resp["choices"][0]["message"]["content"]
            usage = resp.get("usage", {})
            with open(os.path.join(OUT_DIR, f"{stem}.txt"), "w") as f:
                f.write(content)
            print(f"  ok {elapsed:.2f}s tokens={usage.get('completion_tokens')} finish={resp['choices'][0].get('finish_reason')}")
            print(content)
            print()
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    imgs = sys.argv[1:] or [
        "SCE_Bill_Letter.png",
        "SCE_Sample_Bill.png",
        "hoag-invoice-mychart.png",
        "IRS_cp503.png",
    ]
    main(imgs)
