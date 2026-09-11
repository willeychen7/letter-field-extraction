"""
Independent HunyuanOCR-1.5 Information Extraction evaluation.

Purpose: test whether Hunyuan's OFFICIAL Information Extraction prompt
pattern can directly return the structured fields Mama Helper actually
needs, on the same 20-image real-US-letter sample used for the Text
Spotting baseline (spotting_eval/). This is a SEPARATE capability axis from
spotting -- "can it read the text" vs "can it understand and structure the
fields" -- and results are kept in a separate directory on purpose so the
two are never conflated into one score.

Official prompt (Tencent-Hunyuan/HunyuanOCR README_v1.0.md, "Application-
oriented Prompts" table, Information Extraction row):
    提取图片中的: ['key1','key2', ...] 的字段内容，并按照JSON格式返回。
We fill in the key list with the 9 fields Mama Helper needs. This is the
officially documented usage of that template (it requires the caller to
supply field names) -- not a custom-designed extraction prompt/schema.

Constraints (per explicit instruction):
  - No PaddleOCR-era regex/rules are ported in here, and the parser/adapter
    below is strictly for reading whatever JSON-ish shape the model
    returns -- it must not "fix" or complete missing fields itself.
  - Does not touch mama-helper. No LangChain. No production code changes.
"""

import argparse
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
    "document_type",
    "sender",
    "recipient_name",
    "address",
    "account_number",
    "amount",
    "due_date",
    "action_required",
    "important_identifier",
]

IE_PROMPT = (
    "提取图片中的: ['" + "', '".join(FIELDS) + "'] 的字段内容，并按照JSON格式返回。"
)

# Same 20-image sample as spotting_eval/run_spotting_eval.py::DEFAULT_IMAGES,
# kept identical on purpose for A/B comparability.
DEFAULT_IMAGES = [
    "SCE_Bill_Letter.png",
    "SCE_Letter.png",
    "SCE_Sample_Bill.png",
    "SoCalGas.png",
    "Water_Bill2.jpg",
    "BOA_Bill_Example.png",
    "Bank_Bill_Due.png",
    "AAA_insurance_Bill.png",
    "All_State_Insurance_Card.jpg",
    "Auto_Insurance_Bill1.jpg",
    "Great_American_Insurance_Invoice.png",
    "DMV_Registration.png",
    "DMV_Notice.jpeg",
    "Hospital_Bill.png",
    "Medical_Invoice.png",
    "CMS_EOB.png",
    "hoag-invoice-mychart.png",
    "IRS_CP504_Notice.png",
    "IRS_cp503.png",
    "Medicare_Notice_PartA.png",
]

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fence(content: str) -> str:
    m = _FENCE_PATTERN.search(content)
    return m.group(1) if m else content


def parse_ie_output(content: str) -> tuple[dict | None, str]:
    """Returns (fields_dict_or_None, parse_status).

    parse_status in {"valid_json_object", "valid_json_wrong_shape",
                      "parse_failed"}.
    Never raises, never invents/fills a missing field.
    """
    unfenced = _strip_code_fence(content)
    try:
        data = json.loads(unfenced)
    except (json.JSONDecodeError, TypeError):
        return None, "parse_failed"

    if isinstance(data, dict):
        return data, "valid_json_object"
    if isinstance(data, list) and data and isinstance(data[0], dict):
        # some responses may wrap the object in a 1-element array
        return data[0], "valid_json_object"
    return None, "valid_json_wrong_shape"


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
                    {"type": "text", "text": IE_PROMPT},
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


def load_ground_truth(gt_path: str) -> dict:
    if not os.path.exists(gt_path):
        return {}
    with open(gt_path) as f:
        return json.load(f)


def gt_key_for_image(stem: str, gt: dict) -> str | None:
    if stem in gt:
        return stem
    for k in gt:
        if k.lower() == stem.lower():
            return k
    return None


def run(images_dir: str, image_names: list, out_dir: str, base_url: str, timeout: int, gt_path: str):
    raw_dir = os.path.join(out_dir, "raw")
    parsed_dir = os.path.join(out_dir, "parsed")
    for d in (raw_dir, parsed_dir):
        os.makedirs(d, exist_ok=True)

    gt = load_ground_truth(gt_path)

    summary_rows = []
    gt_rows = []

    for name in image_names:
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
            "parse_status": None,
            "n_fields_present": 0,
            "n_fields_null_or_missing": 0,
            "error": None,
        }
        for f in FIELDS:
            row[f"field__{f}"] = None

        if not os.path.exists(image_path):
            row.update(status="error", error="file not found")
            summary_rows.append(row)
            print("  ERROR: file not found")
            continue

        t0 = time.perf_counter()
        try:
            resp = _call_server(base_url, image_path, timeout)
            elapsed = time.perf_counter() - t0

            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)

            content = resp["choices"][0]["message"]["content"]
            with open(os.path.join(raw_dir, f"{stem}.txt"), "w") as f:
                f.write(content)

            usage = resp.get("usage", {})
            finish_reason = resp["choices"][0].get("finish_reason")

            fields, parse_status = parse_ie_output(content)
            with open(os.path.join(parsed_dir, f"{stem}.json"), "w") as f:
                json.dump(fields, f, ensure_ascii=False, indent=2)

            n_present = 0
            n_null = 0
            if fields:
                for fkey in FIELDS:
                    val = fields.get(fkey)
                    row[f"field__{fkey}"] = val
                    is_empty = val is None or (isinstance(val, str) and val.strip().lower() in ("", "none", "null", "n/a"))
                    if is_empty:
                        n_null += 1
                    else:
                        n_present += 1

            row.update(
                status="ok",
                inference_time_s=round(elapsed, 3),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                finish_reason=finish_reason,
                parse_status=parse_status,
                n_fields_present=n_present,
                n_fields_null_or_missing=n_null,
            )
            print(f"  ok, {elapsed:.2f}s, parse={parse_status}, present={n_present}/9, finish_reason={finish_reason}")

            gt_key = gt_key_for_image(stem, gt)
            if gt_key and fields:
                truth = gt[gt_key]
                joined_values = " ".join(str(v) for v in fields.values() if v)
                for gtfield, extracted_field in (
                    ("sender", "sender"),
                    ("amount_due", "amount"),
                    ("due_date", "due_date"),
                    ("category", "document_type"),
                ):
                    expected = truth.get(gtfield)
                    if expected is None:
                        continue
                    extracted_val = fields.get(extracted_field)
                    gt_rows.append(
                        {
                            "image": name,
                            "gt_field": gtfield,
                            "expected": expected,
                            "extracted_field": extracted_field,
                            "extracted_value": extracted_val,
                            "expected_substring_in_any_value": str(expected) in joined_values,
                        }
                    )

        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            elapsed = time.perf_counter() - t0
            row.update(status="error", inference_time_s=round(elapsed, 3), error=str(e))
            print(f"  ERROR: {e}")

        summary_rows.append(row)

    def _write(rows, base):
        if not rows:
            return
        with open(os.path.join(out_dir, f"{base}.json"), "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"{base}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    _write(summary_rows, "summary")
    _write(gt_rows, "ground_truth_check")

    ok = sum(1 for r in summary_rows if r["status"] == "ok")
    valid = sum(1 for r in summary_rows if r.get("parse_status") == "valid_json_object")
    print(f"\n[total] {len(summary_rows)} images, {ok} ok, {len(summary_rows)-ok} errors")
    print(f"[parse] valid_json_object={valid} / {len(summary_rows)}")
    print(f"[out] {out_dir}")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images-dir", default="/Users/willeychen/Desktop/mama-helper/demo_image")
    p.add_argument("--out-dir", default="/Users/willeychen/Desktop/hunyuan-service/evaluation/information_extraction_eval/results")
    p.add_argument("--base-url", default="http://127.0.0.1:8090/v1")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument(
        "--gt-path",
        default="/Users/willeychen/Desktop/mama-helper/frontend/src/utils/ground_truth.json",
    )
    p.add_argument("--images", nargs="*", default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.images_dir, args.images or DEFAULT_IMAGES, args.out_dir, args.base_url, args.timeout, args.gt_path)
