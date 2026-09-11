"""
Document Understanding benchmark: fixed prompt (prompt.txt, sibling file),
9 fields, run over the same 20-real-letter sample used throughout this
evaluation history. Produces raw + parsed outputs only -- scoring against
ground truth (ground_truth.json plus manual image review for fields it
doesn't cover) is done separately, not by this script, since several
fields (recipient, payment_status, action, risk) have no machine-readable
ground truth and require a human/Claude to read the source image.
"""
import base64
import csv
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request

FIELDS = [
    "document_type", "sender", "recipient", "amount", "due_date",
    "payment_status", "action_required", "action", "risk",
]

PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.txt")).read()

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
BASE_URL = "http://127.0.0.1:8090/v1"

# Same 20-image sample as the earlier spotting/IE evals, for continuity.
IMAGES = [
    "SCE_Bill_Letter.png", "SCE_Letter.png", "SCE_Sample_Bill.png", "SoCalGas.png",
    "Water_Bill2.jpg", "BOA_Bill_Example.png", "Bank_Bill_Due.png", "AAA_insurance_Bill.png",
    "All_State_Insurance_Card.jpg", "Auto_Insurance_Bill1.jpg", "Great_American_Insurance_Invoice.png",
    "DMV_Registration.png", "DMV_Notice.jpeg", "Hospital_Bill.png", "Medical_Invoice.png",
    "CMS_EOB.png", "hoag-invoice-mychart.png", "IRS_CP504_Notice.png", "IRS_cp503.png",
    "Medicare_Notice_PartA.png",
]

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_NULLISH = {"none", "null", "n/a", "", "unknown"}


def _strip_fence(s):
    m = _FENCE.search(s)
    return m.group(1) if m else s


def parse(content):
    try:
        data = json.loads(_strip_fence(content))
    except (json.JSONDecodeError, TypeError):
        return None, "parse_failed"
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        return None, "valid_json_wrong_shape"
    out = {}
    for f in FIELDS:
        v = data.get(f)
        if isinstance(v, str) and v.strip().lower() in _NULLISH:
            v = None
        out[f] = v
    return out, "valid_json_object"


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
    rows = []
    for name in IMAGES:
        stem = os.path.splitext(name)[0]
        path = os.path.join(IMAGES_DIR, name)
        print(f"=== {name} ===")
        row = {"image": name, "status": None, "inference_time_s": None,
               "completion_tokens": None, "finish_reason": None, "parse_status": None, "error": None}
        for f in FIELDS:
            row[f"field__{f}"] = None
        t0 = time.perf_counter()
        try:
            resp = call(path)
            elapsed = time.perf_counter() - t0
            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
            content = resp["choices"][0]["message"]["content"]
            with open(os.path.join(raw_dir, f"{stem}.txt"), "w") as f:
                f.write(content)
            usage = resp.get("usage", {})
            fields, status = parse(content)
            if fields:
                for f in FIELDS:
                    row[f"field__{f}"] = fields[f]
            row.update(status="ok", inference_time_s=round(elapsed, 3),
                       completion_tokens=usage.get("completion_tokens"),
                       finish_reason=resp["choices"][0].get("finish_reason"),
                       parse_status=status)
            print(f"  ok {elapsed:.2f}s parse={status}")
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            row.update(status="error", error=str(e))
            print(f"  ERROR: {e}")
        rows.append(row)

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[done] {len(rows)} images -> {OUT_DIR}")


if __name__ == "__main__":
    main()
