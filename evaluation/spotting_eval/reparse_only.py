"""Re-run the parser/adapter over already-saved raw outputs, without calling
the server again. Used after fixing a parsing bug in run_spotting_eval.py so
the classification improves without spending more inference time or risking
non-determinism from a second call. Raw files are read-only here.
"""
import csv
import json
import os

from PIL import Image

from run_spotting_eval import (
    DEFAULT_IMAGES,
    classify_pii_shape,
    draw_overlay,
    gt_key_for_image,
    load_ground_truth,
    parse_spotting_output,
    to_pixel_bbox,
)

OUT_DIR = "/Users/willeychen/Desktop/hunyuan-service/evaluation/spotting_eval/results"
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
GT_PATH = "/Users/willeychen/Desktop/mama-helper/frontend/src/utils/ground_truth.json"

raw_dir = os.path.join(OUT_DIR, "raw")
parsed_dir = os.path.join(OUT_DIR, "parsed")
overlay_dir = os.path.join(OUT_DIR, "overlay")
os.makedirs(parsed_dir, exist_ok=True)
os.makedirs(overlay_dir, exist_ok=True)

gt = load_ground_truth(GT_PATH)

summary_rows = []
pii_rows = []
gt_rows = []

for name in DEFAULT_IMAGES:
    stem = os.path.splitext(name)[0]
    resp_path = os.path.join(raw_dir, f"{stem}.json")
    txt_path = os.path.join(raw_dir, f"{stem}.txt")
    if not os.path.exists(resp_path):
        continue
    resp = json.load(open(resp_path))
    content = open(txt_path).read()
    usage = resp.get("usage", {})
    finish_reason = resp["choices"][0].get("finish_reason")

    items, parse_status = parse_spotting_output(content)

    image_path = os.path.join(IMAGES_DIR, name)
    size = Image.open(image_path).size
    for it in items:
        it["bbox_pixel"] = to_pixel_bbox(it["bbox_norm"], size)
    json.dump(items, open(os.path.join(parsed_dir, f"{stem}.json"), "w"), ensure_ascii=False, indent=2)
    draw_overlay(image_path, items, os.path.join(overlay_dir, f"{stem}.png"))

    summary_rows.append(
        {
            "image": name,
            "status": "ok",
            "inference_time_s": None,  # preserved from original run, see summary_v1 timing
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "finish_reason": finish_reason,
            "detection_count": len(items),
            "parse_status": parse_status,
            "error": None,
        }
    )

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
                "auto_bucket": "D_merged_with_nonPII" if shape["merged_with_label"] else "C_standalone_bbox",
            }
        )

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

# merge back original inference_time_s from the first run's summary.json
old_summary_path = os.path.join(OUT_DIR, "summary.json")
if os.path.exists(old_summary_path):
    old = {r["image"]: r for r in json.load(open(old_summary_path))}
    for r in summary_rows:
        if r["image"] in old:
            r["inference_time_s"] = old[r["image"]].get("inference_time_s")


def _write(rows, base):
    if not rows:
        return
    json.dump(rows, open(os.path.join(OUT_DIR, f"{base}.json"), "w"), ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, f"{base}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


_write(summary_rows, "summary")
_write(pii_rows, "pii_eval")
_write(gt_rows, "ground_truth_check")

from collections import Counter

print(Counter(r["parse_status"] for r in summary_rows))
print(f"total detections across all images: {sum(r['detection_count'] for r in summary_rows)}")
