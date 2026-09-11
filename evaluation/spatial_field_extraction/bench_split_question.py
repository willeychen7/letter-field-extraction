"""
Third variant: ask Hunyuan ONE field at a time (4 separate calls per image),
instead of the combined 9-field prompt /v1/understand-letter uses. This is
the untested hypothesis flagged in schemas/mama_helper_v1.py's own docstring
("the split-request variant... has NOT been validated on the full ground-
truth batch"). Same 49-50 images, same ground truth, same scoring as the
combined-prompt benchmark, so the three numbers are directly comparable:
  - rules (/v1/analyze)              -- already measured
  - combined prompt (understand-letter) -- already measured
  - split, one-field-at-a-time (this script) -- new

Read-only against Phase 3-8 (doesn't touch it). Talks to llama-server on
:8090 directly with hand-built per-field prompts, same style/temperature/
model as /v1/understand-letter, so the ONLY variable that changes is
"how many fields asked per call".
"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ground_truth as GTM
import anchors as A
from ground_truth_20 import GT20
from ground_truth_holdout import GT_HOLD
from gt_domain import GT_DOMAIN

GT = {**GT20, **GT_HOLD}
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
CONV_DIR = os.path.join(HERE, "holdout_images")
LLAMA_URL = "http://127.0.0.1:8090/v1/chat/completions"
OUT_DIR = os.path.join(HERE, "results", "native_split")
OUT = os.path.join(OUT_DIR, "split_raw.json")

# same GT field name -> native schema key used throughout this project
FIELD_KEY = {"sender": "sender", "recipient": "recipient_name",
            "total_amount": "amount", "due_date": "due_date"}

# exact same template/wording as schemas/mama_helper_v1.py::PROMPT, just one
# key in the list instead of all 9 -- isolates "split vs combined" as the
# only variable, no extra prompt engineering added.
def field_prompt(key):
    return (f"提取图片中的: ['{key}'] 的字段内容，"
            "并按照JSON格式返回。如果某个字段在图片中确实不存在，必须返回 null，"
            "不要猜测，也不要用其他字段的内容代替。")


_NULL_STRINGS = {"none", "null", "n/a", "", "unknown", "未知"}


def _strip_fence(content):
    c = content.strip()
    if c.startswith("```"):
        nl = c.find("\n")
        if nl != -1:
            c = c[nl + 1:]
        if c.rstrip().endswith("```"):
            c = c.rstrip()[:-3]
    return c


_WEBP_CACHE = os.path.join(OUT_DIR, "_webp_as_png")


def img_path(key):
    """Same webp->PNG workaround as bench_native_vs_pipeline.py -- this
    llama.cpp build's image loader rejects .webp."""
    for d in (IMAGES_DIR, CONV_DIR):
        for ext in (".png", ".jpg", ".jpeg"):
            p = os.path.join(d, key + ext)
            if os.path.exists(p):
                return p
        webp = os.path.join(d, key + ".webp")
        if os.path.exists(webp):
            os.makedirs(_WEBP_CACHE, exist_ok=True)
            cached = os.path.join(_WEBP_CACHE, key + ".png")
            if not os.path.exists(cached):
                os.system(f'sips -s format png "{webp}" --out "{cached}" >/dev/null 2>&1')
            if os.path.exists(cached):
                return cached
    return None


def ask_field(image_path, field_key, timeout=120):
    mime = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    b64 = base64.b64encode(open(image_path, "rb").read()).decode()
    payload = {
        "model": "HYVL", "temperature": 0.0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": field_prompt(field_key)},
        ]}],
    }
    req = urllib.request.Request(LLAMA_URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    elapsed = round(time.perf_counter() - t0, 2)
    content = data["choices"][0]["message"]["content"]
    try:
        obj = json.loads(_strip_fence(content))
        val = obj.get(field_key) if isinstance(obj, dict) else None
        if isinstance(val, str) and val.strip().lower() in _NULL_STRINGS:
            val = None
        parse_ok = True
    except (json.JSONDecodeError, AttributeError):
        val, parse_ok = None, False
    return {"value": val, "parse_ok": parse_ok, "raw": content, "elapsed": elapsed}


def norm_date(v):
    if v is None:
        return None
    iso = A.parse_date(str(v))
    return iso if iso else str(v)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    raw = json.load(open(OUT)) if os.path.exists(OUT) else {}
    keys = list(GT_DOMAIN)

    for i, k in enumerate(keys, 1):
        raw.setdefault(k, {})
        p = img_path(k)
        if p is None:
            print(f"[{i}/{len(keys)}] {k}: NO IMAGE")
            continue
        for gt_field, native_key in FIELD_KEY.items():
            if gt_field in raw[k] and "error" not in raw[k][gt_field]:
                continue
            try:
                res = ask_field(p, native_key)
                raw[k][gt_field] = res
                print(f"[{i}/{len(keys)}] {k:28s} {gt_field:14s} -> {str(res['value'])[:30]!r:32s} "
                      f"({res['elapsed']}s, parse_ok={res['parse_ok']})")
            except Exception as e:  # noqa: BLE001
                raw[k][gt_field] = {"error": str(e)}
                print(f"[{i}/{len(keys)}] {k:28s} {gt_field:14s} ERROR: {e}")
            json.dump(raw, open(OUT, "w"), ensure_ascii=False, indent=2)

    # ---------------- score ----------------
    FIELDS = list(FIELD_KEY)
    per_field = {f: [0, 0] for f in FIELDS}
    halluc = 0
    rows = []
    for k in keys:
        if k not in GT:
            continue
        for f in FIELDS:
            entry = raw.get(k, {}).get(f)
            if not entry or "error" in entry:
                continue
            pv = entry["value"]
            if f == "due_date":
                pv = norm_date(pv)
            ok, kind = GTM.score_field(f, pv, GT[k][f])
            per_field[f][0] += ok
            per_field[f][1] += 1
            if kind == "null_hallucination":
                halluc += 1
            rows.append({"key": k, "field": f, "pred": pv, "gold": GT[k][f]["value"],
                        "ok": ok, "kind": kind})

    total_ok = sum(v[0] for v in per_field.values())
    total_n = sum(v[1] for v in per_field.values())
    print(f"\n=== SPLIT (one field per call) -- scored {total_n} cells ===")
    for f in FIELDS:
        ok, tot = per_field[f]
        print(f"  {f:15s} {ok:2d}/{tot:2d} = {ok/tot*100:5.1f}%" if tot else f"  {f:15s} no data")
    print(f"  {'OVERALL':15s} {total_ok:2d}/{total_n:2d} = {total_ok/total_n*100:5.1f}%   hallucinations={halluc}")

    json.dump({"per_field": per_field, "hallucination": halluc, "rows": rows},
             open(os.path.join(OUT_DIR, "split_scored.json"), "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
