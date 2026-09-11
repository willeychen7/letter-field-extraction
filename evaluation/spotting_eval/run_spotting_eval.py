"""
Independent HunyuanOCR-1.5 Text Spotting evaluation pipeline.

Scope (deliberately narrow, per the ongoing HunyuanOCR capability probe):
  - Batch-runs the OFFICIAL spotting_json prompt (verbatim from
    Tencent-Hunyuan/HunyuanOCR inference/utils/tasks.py) against a fixed
    list of real US letter images.
  - Does NOT touch mama-helper: no V5, no PaddleOCR, no regex/PII redaction
    module, no spatial matching, no Claude/OpenAI, no LangChain/LangGraph.
  - Any "PII-likely" classification here is a throwaway evaluation heuristic
    used only to label OCR items for this report. It is not a redaction
    engine and must not be imported by, or copied into, mama-helper.
  - Raw model output is NEVER modified. When it isn't valid JSON (observed
    behavior: the model sometimes emits `text(x1,y1),(x2,y2)text2(...)...`
    instead of a JSON array), a fallback regex parser extracts structured
    {text, bbox_norm} pairs into a SEPARATE field; the raw string is always
    kept untouched alongside it.

Output layout under --out-dir (default: hunyuan-experiment/spotting_eval/results):
  raw/<stem>.json         full server response, untouched
  raw/<stem>.txt          raw content string, untouched
  parsed/<stem>.json      [{text, bbox_norm, bbox_pixel}, ...] (best-effort)
  overlay/<stem>.png      bbox overlay for manual QA
  summary.csv / .json     one row per image: timing, tokens, finish_reason,
                           detection_count, parse_status, error
  pii_eval.csv / .json    one row per detected item classified against a
                           lightweight PII-shape heuristic (A/B/C/D bucket)
  ground_truth_check.csv  cross-check of sender/amount/due_date/category
                           against frontend/src/utils/ground_truth.json
                           (read-only; mama-helper is never written to)
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

from PIL import Image, ImageDraw

SPOTTING_PROMPT = (
    "检测并识别图中所有的文字行，请按从上到下、从左到右的阅读顺序进行识别。 "
    "输出格式为 JSON 数组，每个元素必须包含："
    '"box": [xmin, ymin, xmax, ymax]（坐标需归一化到 [0, 1000] 范围内）；'
    '"text": "识别出的文字内容"。 '
    "注意：请直接输出 JSON 数组，不要包含任何多余的描述性文字。"
)

# Fixed 20-image sample for stage-1 evaluation: covers utility / bank /
# insurance / DMV / medical-EOB / government-notice document types, plus
# at least one explicit "no action required" letter (CMS_EOB, Auto_Insurance
# both carry "THIS IS NOT A BILL"). No .webp/.avif/.pdf — the llama-server
# image loader was already confirmed (stage 2) to reject those formats.
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

# --- lightweight PII-SHAPE heuristics (evaluation-only, not a detector) ----
# Deliberately crude: this exists only to bucket spotting output for manual
# review (A/B/C/D below), not to make redaction decisions.
_RE_DIGITS_RUN = re.compile(r"\d{5,}")
_RE_PHONE = re.compile(r"(\(\d{3}\)\s*\d{3}[-.\s]?\d{4})|(\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
_RE_NAME_LASTFIRST = re.compile(r"^[A-Z][A-Z'\-]+,\s*[A-Z][A-Za-z'\-]+")
_RE_ADDRESS = re.compile(
    r"\d+\s+[A-Z0-9 ]+\b(AVE|AVENUE|ST|STREET|RD|ROAD|DR|DRIVE|BLVD|LN|LANE|WAY|CT|CIR|PKWY)\b",
    re.IGNORECASE,
)
_LABEL_WORDS = (
    "account", "service", "policy", "case", "member", "claim", "id",
    "pod-id", "pod id", "subscriber", "group", "customer", "invoice",
    "reference", "phone", "tel", "vin", "license",
)


def classify_pii_shape(text: str) -> dict:
    """Best-effort, evaluation-only classification of one spotted text line.

    Returns {"kind": "name"|"address"|"id_number"|"phone"|None,
             "merged_with_label": bool}
    `merged_with_label` flags text that looks like "<label>: <value>" or
    "<value> / <other text>" -- i.e. a PII value glued to non-PII text in
    the same spotting line, which is exactly the bbox-granularity problem
    flagged in the prior stage-4 test.
    """
    kind = None
    if _RE_NAME_LASTFIRST.search(text):
        kind = "name"
    elif _RE_ADDRESS.search(text):
        kind = "address"
    elif _RE_PHONE.search(text):
        kind = "phone"
    elif _RE_DIGITS_RUN.search(text):
        kind = "id_number"

    if kind is None:
        return {"kind": None, "merged_with_label": False}

    lower = text.lower()
    has_label_word = any(w in lower for w in _LABEL_WORDS)
    has_colon = ":" in text
    has_slash_trailer = "/" in text and kind == "name"
    merged = has_label_word or has_colon or has_slash_trailer
    return {"kind": kind, "merged_with_label": merged}


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
                    {"type": "text", "text": SPOTTING_PROMPT},
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


# --- raw-output parsing: never mutate the raw string, only extract --------

_LINE_PATTERN = re.compile(r"(.*?)\((\d+),\s*(\d+)\),\((\d+),\s*(\d+)\)", re.DOTALL)
_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fence(content: str) -> str:
    m = _FENCE_PATTERN.search(content)
    return m.group(1) if m else content


def parse_spotting_output(content: str) -> tuple[list, str]:
    """Returns (items, parse_status). items = [{"text","bbox_norm"}].

    parse_status in:
      "valid_json"          -- official JSON array of {box:[4 numbers], text}
      "regex_fallback"      -- observed native "text(x1,y1),(x2,y2)..." dump,
                               no JSON structure at all, but real coordinates
      "json_malformed_no_bbox" -- output IS valid JSON (often inside a
                               ```json fence) but uses the wrong shape: a
                               single {"box": [...text fragments...], "text":
                               "..."} object where "box" holds text strings,
                               not numeric coordinates. Zero bbox recoverable.
      "parse_failed"        -- neither of the above; content unparseable by
                               any known shape.
    Never raises; a failure yields an empty list, not a crashed pipeline.
    """
    unfenced = _strip_code_fence(content)

    # 1) try the officially-requested JSON array shape first.
    try:
        data = json.loads(unfenced)
        if isinstance(data, list):
            items = []
            for el in data:
                box = el.get("box") or el.get("bbox")
                text = el.get("text", "")
                if box and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
                    items.append({"text": text, "bbox_norm": [int(v) for v in box]})
            if items:
                return items, "valid_json"
        if isinstance(data, dict) and "box" in data:
            box = data["box"]
            if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
                return [{"text": data.get("text", ""), "bbox_norm": [int(v) for v in box]}], "valid_json"
            # observed failure mode: "box" holds a list of text fragments,
            # not coordinates -- valid JSON, unusable for bbox extraction.
            return [], "json_malformed_no_bbox"
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    # 2) fallback: observed native format "text(x1,y1),(x2,y2)text2(...)..."
    matches = _LINE_PATTERN.findall(content)
    if matches:
        items = [
            {"text": text, "bbox_norm": [int(x1), int(y1), int(x2), int(y2)]}
            for text, x1, y1, x2, y2 in matches
        ]
        return items, "regex_fallback"

    return [], "parse_failed"


def draw_overlay(image_path: str, items: list, out_path: str) -> None:
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for it in items:
        x1, y1, x2, y2 = it["bbox_norm"]
        px = [x1 * w / 1000, y1 * h / 1000, x2 * w / 1000, y2 * h / 1000]
        draw.rectangle(px, outline="red", width=2)
    img.save(out_path)


def to_pixel_bbox(bbox_norm: list, size: tuple) -> list:
    w, h = size
    x1, y1, x2, y2 = bbox_norm
    return [round(x1 * w / 1000, 1), round(y1 * h / 1000, 1), round(x2 * w / 1000, 1), round(y2 * h / 1000, 1)]


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
    overlay_dir = os.path.join(out_dir, "overlay")
    for d in (raw_dir, parsed_dir, overlay_dir):
        os.makedirs(d, exist_ok=True)

    gt = load_ground_truth(gt_path)

    summary_rows = []
    pii_rows = []
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
            "detection_count": 0,
            "parse_status": None,
            "error": None,
        }

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

            items, parse_status = parse_spotting_output(content)

            img = Image.open(image_path)
            size = img.size
            for it in items:
                it["bbox_pixel"] = to_pixel_bbox(it["bbox_norm"], size)

            with open(os.path.join(parsed_dir, f"{stem}.json"), "w") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)

            draw_overlay(image_path, items, os.path.join(overlay_dir, f"{stem}.png"))

            row.update(
                status="ok",
                inference_time_s=round(elapsed, 3),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                finish_reason=finish_reason,
                detection_count=len(items),
                parse_status=parse_status,
            )
            print(f"  ok, {elapsed:.2f}s, {len(items)} items, parse={parse_status}, finish_reason={finish_reason}")

            # --- PII-shape heuristic pass (evaluation-only) ---
            all_text_joined = " ".join(it["text"] for it in items)
            for it in items:
                shape = classify_pii_shape(it["text"])
                if shape["kind"] is None:
                    continue
                pii_rows.append(
                    {
                        "image": name,
                        "text": it["text"],
                        "kind": shape["kind"],
                        "bbox_norm": it["bbox_norm"],
                        "bbox_pixel": it["bbox_pixel"],
                        "merged_with_label_or_trailer": shape["merged_with_label"],
                        # A/B/C/D bucket per the review protocol:
                        #  - detected + not merged  -> C (bbox likely precise; still needs eyeball check)
                        #  - detected + merged       -> D (PII glued to non-PII text in one bbox)
                        # "A" (missed entirely) and fine-grained "B" (bbox off-target)
                        # cannot be determined automatically without ground-truth
                        # bbox annotations; left for manual review, see report.
                        "auto_bucket": "D_merged_with_nonPII" if shape["merged_with_label"] else "C_standalone_bbox",
                    }
                )

            # --- ground-truth cross-check (read-only against mama-helper) ---
            gt_key = gt_key_for_image(stem, gt)
            if gt_key:
                truth = gt[gt_key]
                for field in ("sender", "amount_due", "due_date", "category"):
                    expected = truth.get(field)
                    if expected is None:
                        continue
                    found = str(expected) in all_text_joined
                    gt_rows.append(
                        {
                            "image": name,
                            "gt_key": gt_key,
                            "field": field,
                            "expected": expected,
                            "found_in_spotted_text": found,
                        }
                    )

        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            elapsed = time.perf_counter() - t0
            row.update(status="error", inference_time_s=round(elapsed, 3), error=str(e))
            print(f"  ERROR: {e}")

        summary_rows.append(row)

    def _write_csv_json(rows, base_name):
        if not rows:
            return
        with open(os.path.join(out_dir, f"{base_name}.json"), "w") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"{base_name}.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    _write_csv_json(summary_rows, "summary")
    _write_csv_json(pii_rows, "pii_eval")
    _write_csv_json(gt_rows, "ground_truth_check")

    ok = sum(1 for r in summary_rows if r["status"] == "ok")
    valid_json = sum(1 for r in summary_rows if r.get("parse_status") == "valid_json")
    regex_fallback = sum(1 for r in summary_rows if r.get("parse_status") == "regex_fallback")
    print(f"\n[total] {len(summary_rows)} images, {ok} ok, {len(summary_rows)-ok} errors")
    print(f"[parse] valid_json={valid_json} regex_fallback={regex_fallback} parse_failed={ok-valid_json-regex_fallback}")
    print(f"[out] {out_dir}")


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--images-dir", default="/Users/willeychen/Desktop/mama-helper/demo_image")
    p.add_argument("--out-dir", default="/Users/willeychen/Desktop/hunyuan-service/evaluation/spotting_eval/results")
    p.add_argument("--base-url", default="http://127.0.0.1:8090/v1")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument(
        "--gt-path",
        default="/Users/willeychen/Desktop/mama-helper/frontend/src/utils/ground_truth.json",
    )
    p.add_argument("--images", nargs="*", default=None, help="override the default 20-image list")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(
        args.images_dir,
        args.images or DEFAULT_IMAGES,
        args.out_dir,
        args.base_url,
        args.timeout,
        args.gt_path,
    )
