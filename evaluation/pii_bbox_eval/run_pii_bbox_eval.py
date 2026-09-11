"""
Independent test: can HunyuanOCR-1.5 itself do joint PII identification +
bbox localization in one pass, well enough to be Mama Helper's local
privacy/PII detection+localization layer (the step that must run BEFORE
anything is sent to Claude/GPT)?

This is a THIRD, separate capability axis from the prior two evals:
  - spotting_eval/      -> can it find text + coordinates at all (40% yes)
  - information_extraction_eval/ -> can it fill structured fields (100% JSON,
    but sender/recipient direction wrong in 60% of checkable cases, and
    forced-filling of wrong-typed values into empty slots)
  - pii_bbox_eval/ (this dir) -> can it do PII typing + bbox jointly, and
    does it correctly return null for a PII type that isn't present instead
    of substituting a different type of number into the slot

The prompt (prompt.txt, sibling file) is a purpose-built PII+bbox schema --
there is no official Tencent-Hunyuan task type that combines typed PII
extraction with bounding boxes, so unlike the doc_parse/spotting_json/IE
tests this one is NOT reusing an official template verbatim. It is the
minimum schema needed to answer the question this experiment stage was
asked to answer.

Hard constraints (do not violate):
  - The parser/adapter below only reads whatever JSON the model returns.
    It NEVER guesses at PII with regex, never fills a missing field, and
    never "fixes" a wrong-typed value the model already returned. If the
    model fails, the failure is recorded as-is.
  - Does not touch mama-helper. No LangChain. No production code.
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

PII_SLOTS = [
    "recipient_name",
    "address",
    "account_number",
    "policy_member_claim_number",
    "phone",
    "email",
    "ssn",
    "medicare_medical_id",
    "other_identifier",
]

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


def parse_pii_output(content: str) -> tuple[dict | None, str]:
    """Returns (dict_or_None, parse_status).

    Never raises. Never invents a slot value. Just structural JSON reading:
    parse_status in {"valid_json_object", "valid_json_wrong_shape", "parse_failed"}.
    """
    unfenced = _strip_code_fence(content)
    try:
        data = json.loads(unfenced)
    except (json.JSONDecodeError, TypeError):
        return None, "parse_failed"
    if isinstance(data, dict):
        return data, "valid_json_object"
    return None, "valid_json_wrong_shape"


def slot_is_well_formed(value) -> bool:
    """True iff value is null, OR {"text": str, "bbox": [4 numbers]}.
    This is a structural check only -- it says nothing about whether the
    text/bbox content is CORRECT, only whether the model followed the
    requested shape for a non-null slot.
    """
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if "text" not in value or "bbox" not in value:
        return False
    bbox = value["bbox"]
    return isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)


def _image_data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _call_server(base_url: str, image_path: str, prompt: str, timeout: int) -> dict:
    payload = {
        "model": "HYVL",
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_uri(image_path)}},
                    {"type": "text", "text": prompt},
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


def run(images_dir: str, image_names: list, out_dir: str, base_url: str, timeout: int, prompt_path: str):
    raw_dir = os.path.join(out_dir, "raw")
    parsed_dir = os.path.join(out_dir, "parsed")
    for d in (raw_dir, parsed_dir):
        os.makedirs(d, exist_ok=True)

    prompt = open(prompt_path).read()

    summary_rows = []
    slot_rows = []

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
            "n_slots_non_null": 0,
            "n_slots_well_formed": 0,
            "n_slots_malformed": 0,
            "error": None,
        }

        if not os.path.exists(image_path):
            row.update(status="error", error="file not found")
            summary_rows.append(row)
            print("  ERROR: file not found")
            continue

        t0 = time.perf_counter()
        try:
            resp = _call_server(base_url, image_path, prompt, timeout)
            elapsed = time.perf_counter() - t0

            with open(os.path.join(raw_dir, f"{stem}.json"), "w") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
            content = resp["choices"][0]["message"]["content"]
            with open(os.path.join(raw_dir, f"{stem}.txt"), "w") as f:
                f.write(content)

            usage = resp.get("usage", {})
            finish_reason = resp["choices"][0].get("finish_reason")

            data, parse_status = parse_pii_output(content)
            with open(os.path.join(parsed_dir, f"{stem}.json"), "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            n_non_null = 0
            n_well = 0
            n_bad = 0
            if data:
                for slot in PII_SLOTS:
                    val = data.get(slot)  # missing key treated same as null
                    well_formed = slot_is_well_formed(val)
                    if val is not None:
                        n_non_null += 1
                    if well_formed:
                        n_well += 1
                    else:
                        n_bad += 1
                    slot_rows.append(
                        {
                            "image": name,
                            "slot": slot,
                            "raw_value": json.dumps(val, ensure_ascii=False),
                            "is_null": val is None,
                            "well_formed": well_formed,
                            "text": val.get("text") if isinstance(val, dict) else (val if isinstance(val, str) else None),
                            "bbox": val.get("bbox") if isinstance(val, dict) else None,
                        }
                    )

            row.update(
                status="ok",
                inference_time_s=round(elapsed, 3),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                finish_reason=finish_reason,
                parse_status=parse_status,
                n_slots_non_null=n_non_null,
                n_slots_well_formed=n_well,
                n_slots_malformed=n_bad,
            )
            print(f"  ok, {elapsed:.2f}s, parse={parse_status}, non_null={n_non_null}/9, malformed={n_bad}, finish_reason={finish_reason}")

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
    _write(slot_rows, "pii_slots")

    ok = sum(1 for r in summary_rows if r["status"] == "ok")
    valid = sum(1 for r in summary_rows if r.get("parse_status") == "valid_json_object")
    print(f"\n[total] {len(summary_rows)} images, {ok} ok, {len(summary_rows)-ok} errors")
    print(f"[parse] valid_json_object={valid} / {len(summary_rows)}")
    print(f"[out] {out_dir}")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images-dir", default="/Users/willeychen/Desktop/mama-helper/demo_image")
    p.add_argument("--out-dir", default="/Users/willeychen/Desktop/hunyuan-service/evaluation/pii_bbox_eval/results")
    p.add_argument("--base-url", default="http://127.0.0.1:8090/v1")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--prompt-path", default="/Users/willeychen/Desktop/hunyuan-service/evaluation/pii_bbox_eval/prompt.txt")
    p.add_argument("--images", nargs="*", default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.images_dir, args.images or DEFAULT_IMAGES, args.out_dir, args.base_url, args.timeout, args.prompt_path)
