"""
Run HunyuanOCR-1.5's plain 'structured_parse' task (official prompt: just
"提取图中的文字。" -- no markdown/table/reading-order formatting requirement)
over every readable (png/jpg/jpeg) image in demo_image/, to check pure text
recognition accuracy with the formatting-compliance failure mode removed.

Does not touch mama-helper. No LangChain. Parser only reads raw text, does
not correct or reformat it.
"""
import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

PROMPT = "提取图中的文字。"  # official structured_parse task prompt, verbatim

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = "/Users/willeychen/Desktop/hunyuan-service/evaluation/full_text_dump_eval/results"
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


def main():
    raw_dir = os.path.join(OUT_DIR, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    images = sorted(
        f for f in os.listdir(IMAGES_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )
    rows = []
    for name in images:
        stem = os.path.splitext(name)[0]
        path = os.path.join(IMAGES_DIR, name)
        print(f"=== {name} ===")
        row = {"image": name, "status": None, "inference_time_s": None,
               "prompt_tokens": None, "completion_tokens": None, "finish_reason": None, "error": None}
        t0 = time.perf_counter()
        try:
            resp = call_server(path)
            elapsed = time.perf_counter() - t0
            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
            content = resp["choices"][0]["message"]["content"]
            with open(os.path.join(raw_dir, f"{stem}.txt"), "w") as f:
                f.write(content)
            usage = resp.get("usage", {})
            row.update(status="ok", inference_time_s=round(elapsed, 3),
                       prompt_tokens=usage.get("prompt_tokens"),
                       completion_tokens=usage.get("completion_tokens"),
                       finish_reason=resp["choices"][0].get("finish_reason"))
            print(f"  ok {elapsed:.2f}s tokens={usage.get('completion_tokens')} finish={row['finish_reason']}")
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            elapsed = time.perf_counter() - t0
            row.update(status="error", inference_time_s=round(elapsed, 3), error=str(e))
            print(f"  ERROR: {e}")
        rows.append(row)

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    import csv
    with open(os.path.join(OUT_DIR, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n[total] {len(rows)}, ok={ok}, errors={len(rows)-ok}")


if __name__ == "__main__":
    main()
