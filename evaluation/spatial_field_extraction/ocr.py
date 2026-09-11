"""
OCR stage: HunyuanOCR-1B text + bbox, nothing else.

- Uses the OFFICIAL `spotting_hunyuan` task prompt verbatim
  ("检测并识别图片中的文字，将文本坐标格式化输出。") from
  Tencent-Hunyuan/HunyuanOCR inference/utils/tasks.py.
- max_tokens raised to 8192: the two 4096-truncated images in the earlier
  spotting_eval run (parse_status="length") were the only failures that
  weren't the JSON-shape bug, and this prompt + limit produced clean
  coordinate dumps for all 6 sample images in a probe.
- Output shape observed from this model: a flat run of
  `TEXT(x1,y1),(x2,y2)` groups, coords already in [0,1000].
- The parser below is a hand-written character scan, NOT a regex, per the
  experiment constraint. It only reads the model's own coordinate
  serialisation; it makes no semantic decision about the text.
"""

import base64
import json
import mimetypes
import os
import time
import urllib.request

SPOTTING_HUNYUAN_PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"
DEFAULT_BASE_URL = "http://127.0.0.1:8090/v1"


def _data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def call_ocr(image_path, base_url=DEFAULT_BASE_URL, timeout=300, max_tokens=8192):
    payload = {
        "model": "HYVL",
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_uri(image_path)}},
                    {"type": "text", "text": SPOTTING_HUNYUAN_PROMPT},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    elapsed = time.perf_counter() - t0
    choice = data["choices"][0]
    return {
        "content": choice["message"]["content"],
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage", {}),
        "elapsed_s": round(elapsed, 3),
    }


# --- hand-written coordinate-serialisation parser (no regex) --------------

def _read_int(s, i):
    """Read an unsigned integer starting at s[i] (spaces skipped). Returns
    (value, next_index) or (None, i) if no digit is present."""
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    j = i
    while j < n and s[j].isdigit():
        j += 1
    if j == i:
        return None, i
    return int(s[i:j]), j


def _try_coord_group(s, i):
    """Try to read `(x1,y1),(x2,y2)` starting at s[i]. Returns
    (bbox_list, next_index) or (None, i)."""
    n = len(s)
    k = i
    if k >= n or s[k] != "(":
        return None, i
    k += 1
    a, k = _read_int(s, k)
    if a is None or k >= n or s[k] != ",":
        return None, i
    k += 1
    b, k = _read_int(s, k)
    if b is None or k >= n or s[k] != ")":
        return None, i
    k += 1
    if k >= n or s[k] != ",":
        return None, i
    k += 1
    if k >= n or s[k] != "(":
        return None, i
    k += 1
    c, k = _read_int(s, k)
    if c is None or k >= n or s[k] != ",":
        return None, i
    k += 1
    d, k = _read_int(s, k)
    if d is None or k >= n or s[k] != ")":
        return None, i
    k += 1
    return [a, b, c, d], k


def parse_ocr_elements(content):
    """Scan `content` for `TEXT(x1,y1),(x2,y2)` groups.

    The text of each element is whatever non-coordinate characters precede
    its coordinate group, back to the end of the previous group. Returns a
    list of {"text", "bbox"}; bbox is [x1,y1,x2,y2] in [0,1000].
    """
    s = content.strip()
    # drop a leading/trailing ```json ... ``` fence if the model added one
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    elements = []
    n = len(s)
    i = 0
    text_start = 0
    while i < n:
        if s[i] == "(":
            bbox, k = _try_coord_group(s, i)
            if bbox is not None:
                raw_text = s[text_start:i].strip()
                # trim wrapping punctuation/newlines the model sometimes adds
                raw_text = raw_text.strip(" \n\r\t")
                if raw_text:
                    elements.append({"text": raw_text, "bbox": bbox})
                i = k
                text_start = i
                continue
        i += 1
    return elements
