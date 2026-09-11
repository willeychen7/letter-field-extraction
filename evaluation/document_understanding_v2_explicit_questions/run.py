"""
Same 9-field JSON output as document_understanding_benchmark/, but the
prompt now spells out 9 explicit numbered questions (one per field) before
asking for the JSON -- still ONE API request per image, not 9 separate
calls. Purpose: check whether decomposing one big schema instruction into
explicit per-field questions (while still batching them in a single
request) improves field understanding, before committing to a full
180-request per-field-call experiment.

No accuracy scoring here -- raw output only, for manual side-by-side review.
Does not touch mama-helper.
"""
import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.txt")).read()

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
BASE_URL = "http://127.0.0.1:8090/v1"

IMAGES = [
    "SCE_Bill_Letter.png", "SCE_Letter.png", "SCE_Sample_Bill.png", "SoCalGas.png",
    "Water_Bill2.jpg", "BOA_Bill_Example.png", "Bank_Bill_Due.png", "AAA_insurance_Bill.png",
    "All_State_Insurance_Card.jpg", "Auto_Insurance_Bill1.jpg", "Great_American_Insurance_Invoice.png",
    "DMV_Registration.png", "DMV_Notice.jpeg", "Hospital_Bill.png", "Medical_Invoice.png",
    "CMS_EOB.png", "hoag-invoice-mychart.png", "IRS_CP504_Notice.png", "IRS_cp503.png",
    "Medicare_Notice_PartA.png",
]


def _uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def call(path, timeout=180):
    payload = {
        "model": "HYVL", "temperature": 0.0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _uri(path)}},
            {"type": "text", "text": PROMPT},
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
    for name in IMAGES:
        stem = os.path.splitext(name)[0]
        path = os.path.join(IMAGES_DIR, name)
        print(f"=== {name} ===")
        t0 = time.perf_counter()
        try:
            resp = call(path)
            elapsed = time.perf_counter() - t0
            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
            content = resp["choices"][0]["message"]["content"]
            with open(os.path.join(raw_dir, f"{stem}.txt"), "w") as f:
                f.write(content)
            print(f"  ok {elapsed:.2f}s finish={resp['choices'][0].get('finish_reason')}")
            print(content)
            print()
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
