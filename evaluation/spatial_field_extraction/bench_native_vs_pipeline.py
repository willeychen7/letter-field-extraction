"""
Head-to-head benchmark: Hunyuan's native direct-answer endpoint
(/v1/understand-letter) vs our OCR+rules endpoint (/v1/analyze), on the
SAME 49 real letters + SAME ground truth + SAME scoring function.

Read-only against the pipeline: does not touch Phase 3-8, does not modify
any frozen file, does not change /v1/analyze. Just calls both HTTP
endpoints and scores what comes back.
"""
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
BASE = os.environ.get("HUNYUAN_SERVICE_URL", "http://localhost:8091")
OUT_DIR = os.path.join(HERE, "results", "native_benchmark")
OUT = os.path.join(OUT_DIR, "native_raw.json")

FIELDS = ["sender", "recipient", "total_amount", "due_date"]  # the 4 fields both schemas can answer


_WEBP_CACHE = os.path.join(OUT_DIR, "_webp_as_png")


def img_path(key):
    """Return a path llama-server's image loader can read. .webp is a known
    rejected format for this llama.cpp build (see docs/PHASE9B_GPU_
    FEASIBILITY.md) -- converted to PNG once via `sips`, cached under
    results/native_benchmark/_webp_as_png/, and reused on reruns."""
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


def call_understand(path, timeout=120):
    mime = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    boundary = "----bench"
    with open(path, "rb") as f:
        data = f.read()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x{os.path.splitext(path)[1]}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/v1/understand-letter", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    d["_elapsed"] = round(time.perf_counter() - t0, 2)
    return d


def norm_date(v):
    if v is None:
        return None
    iso = A.parse_date(str(v))
    return iso if iso else str(v)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    raw = {}
    if os.path.exists(OUT):
        raw = json.load(open(OUT))

    keys = list(GT_DOMAIN)
    for i, k in enumerate(keys, 1):
        if k in raw and not raw[k].get("_error"):
            print(f"[{i}/{len(keys)}] skip {k}")
            continue
        p = img_path(k)
        if p is None:
            raw[k] = {"_error": "no image"}
            print(f"[{i}/{len(keys)}] {k}: NO IMAGE")
            continue
        try:
            d = call_understand(p)
            raw[k] = d
            print(f"[{i}/{len(keys)}] {k}: {d.get('parse_status')} ({d.get('_elapsed')}s)")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            raw[k] = {"_error": str(e)}
            print(f"[{i}/{len(keys)}] {k}: ERROR {e}")
        json.dump(raw, open(OUT, "w"), ensure_ascii=False, indent=2)

    # ---------------- score ----------------
    per_field = {f: [0, 0] for f in FIELDS}
    halluc = 0
    rows = []
    scored_keys = 0
    for k in keys:
        d = raw.get(k, {})
        if d.get("_error") or d.get("parse_status") != "valid_json_object":
            continue
        f = d.get("fields") or {}
        scored_keys += 1
        pred_map = {
            "sender": f.get("sender"),
            "recipient": f.get("recipient_name"),
            "total_amount": f.get("amount"),
            "due_date": norm_date(f.get("due_date")),
        }
        gt = GT[k]
        for field in FIELDS:
            ok, kind = GTM.score_field(field, pred_map[field], gt[field])
            per_field[field][0] += ok
            per_field[field][1] += 1
            if kind == "null_hallucination":
                halluc += 1
            rows.append({"key": k, "field": field, "pred": pred_map[field],
                        "gold": gt[field]["value"], "ok": ok, "kind": kind})

    print("\n=== NATIVE /v1/understand-letter -- scored on", scored_keys, "images (of", len(keys), ") ===")
    for f in FIELDS:
        ok, tot = per_field[f]
        print(f"  {f:15s} {ok:2d}/{tot:2d} = {ok/tot*100:5.1f}%")
    print(f"  hallucinations: {halluc}")

    json.dump({"per_field": per_field, "hallucination": halluc, "scored": scored_keys,
              "total": len(keys), "rows": rows},
             open(OUT.replace("native_raw", "native_scored"), "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
