"""
Stage-1 experiment runner:  HunyuanOCR-1B + local deterministic spatial
field extraction  vs  the earlier "Image -> Hunyuan -> answer" baseline.

  6 images x 6 fields.  No regex / no 2nd LLM / no Ollama / no external API.
  OCR = official spotting_hunyuan prompt only.

Outputs (evaluation/spatial_field_extraction/results/):
  raw/<stem>.ocr.txt      raw OCR string, untouched
  raw/<stem>.ocr.json     full server response
  raw/<stem>.json         parsed elements + per-field candidates/scores/
                          evidence + cross-validation + final fields
  summary.json            per-image + aggregate metrics for both systems
  comparison.csv          the headline field-by-field table

Re-run with  --use-cache  to skip OCR and reuse raw/<stem>.ocr.json.
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import anchors as A          # noqa: E402
import extract as X          # noqa: E402
import ground_truth as GTM   # noqa: E402
from ocr import call_ocr, parse_ocr_elements  # noqa: E402

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "results")
RAW = os.path.join(RESULTS, "raw")
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
BASELINE_PATH = os.path.join(
    HERE, "..", "single_field_test", "results", "results.json"
)

IMAGES = [
    "SCE_Bill_Letter.png",
    "Hospital_Bill.png",
    "Medical_Invoice.png",
    "BOA_Bill_Example.png",
    "Medicare_Notice_PartA.png",
    "IRS_cp503.png",
]


# ---------------------------------------------------------------- OCR

def get_ocr(name, use_cache):
    stem = os.path.splitext(name)[0]
    cache = os.path.join(RAW, f"{stem}.ocr.json")
    if use_cache and os.path.exists(cache):
        with open(cache) as f:
            resp = json.load(f)
        print(f"  [cache] {stem}")
        return resp
    path = os.path.join(IMAGES_DIR, name)
    resp = call_ocr(path)
    with open(cache, "w") as f:
        json.dump(resp, f, ensure_ascii=False, indent=2)
    with open(os.path.join(RAW, f"{stem}.ocr.txt"), "w") as f:
        f.write(resp["content"])
    print(f"  [ocr]   {stem}  {resp['elapsed_s']}s  finish={resp['finish_reason']}"
          f"  ptok={resp['usage'].get('prompt_tokens')}"
          f"  ctok={resp['usage'].get('completion_tokens')}")
    return resp


# ---------------------------------------------------- baseline normalisation

def norm_baseline(field, raw):
    if raw is None:
        return None
    s = str(raw).strip()
    low = s.lower()
    if low in ("null", "none", "", "n/a", "无", "未知", "无法确定"):
        return None
    if s.startswith("ERROR:"):
        return None
    # baseline sometimes answers with a whole Chinese sentence -> not a value
    if field in ("total_amount", "due_date", "sender", "recipient") and len(s) > 60:
        return "__SENTENCE__" + s[:40]
    if field == "total_amount":
        keep = "".join(c for c in s if c.isdigit() or c == ".")
        return keep or s
    if field == "payment_status":
        for v in ("not_applicable", "unpaid", "paid"):
            if v in low:
                return v
        return None
    if field == "action":
        # map baseline free text to the same small label set the pipeline uses
        for label, phrases in A.ACTION_PHRASES.items():
            if any(p in low for p in phrases):
                return label
        if "pay" in low or "remit" in low:
            return "pay"
        if "call" in low:
            return "call"
        return s
    return s


# ---------------------------------------------------------------- scoring

def score_system(preds_by_image):
    """preds_by_image: {stem: {field: value}}  ->  metrics dict."""
    per_field = {f: {"correct": 0, "total": 0} for f in GTM.FIELDS}
    kinds = {}
    rows = []
    total_correct = total = 0
    null_hall = null_slots = 0
    for stem, preds in preds_by_image.items():
        gt = GTM.GT[stem]
        for f in GTM.FIELDS:
            entry = gt[f]
            pred = preds.get(f)
            ok, kind = GTM.score_field(f, pred, entry)
            per_field[f]["total"] += 1
            per_field[f]["correct"] += int(ok)
            kinds[kind] = kinds.get(kind, 0) + 1
            total += 1
            total_correct += int(ok)
            if entry["value"] is None and None not in entry.get("accept", []):
                null_slots += 1
                if kind == "null_hallucination":
                    null_hall += 1
            rows.append({"image": stem, "field": f, "pred": pred,
                         "gold": entry["value"], "correct": ok, "kind": kind})
    return {
        "overall_accuracy": round(total_correct / total, 4),
        "correct": total_correct, "total": total,
        "per_field": {f: {"accuracy": round(v["correct"] / v["total"], 4),
                          **v} for f, v in per_field.items()},
        "kind_counts": kinds,
        "null_slots": null_slots,
        "null_hallucinations": null_hall,
        "null_hallucination_rate": round(null_hall / null_slots, 4) if null_slots else 0.0,
        "rows": rows,
    }


def candidate_selection_accuracy(detail_by_image):
    """Of the non-null-GT fields where the correct value WAS among the
    scored spatial candidates, how often did the pipeline's final pick
    equal GT?  (Isolates scoring/selection quality from candidate recall.)"""
    hit = avail = 0
    misses = []
    for stem, det in detail_by_image.items():
        gt = GTM.GT[stem]
        for f in ("total_amount", "due_date", "sender", "recipient", "action"):
            entry = gt[f]
            if entry["value"] is None:
                continue
            cands = det["candidates"].get(f, [])
            present = any(GTM.score_field(f, c["value"], entry)[0] for c in cands)
            if not present:
                continue
            avail += 1
            final = det["fields"][f]["value"]
            if GTM.score_field(f, final, entry)[0]:
                hit += 1
            else:
                misses.append({"image": stem, "field": f, "final": final,
                               "gold": entry["value"],
                               "candidates": [(c["value"], c["score"]) for c in cands[:5]]})
    return {"candidate_present_slots": avail, "selected_correct": hit,
            "candidate_selection_accuracy": round(hit / avail, 4) if avail else None,
            "misses": misses}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)

    pipeline_preds = {}
    pipeline_detail = {}

    print("== OCR + spatial extraction ==")
    for name in IMAGES:
        stem = os.path.splitext(name)[0]
        resp = get_ocr(name, args.use_cache)
        elements = parse_ocr_elements(resp["content"])

        cands = {
            "total_amount": X.extract_amount(elements),
            "due_date": X.extract_due_date(elements),
            "sender": X.extract_sender(elements),
            "recipient": X.extract_recipient(elements),
            "action": X.extract_action(elements),
        }
        fields = X.extract_fields(elements)

        pipeline_preds[stem] = {f: fields[f]["value"] for f in GTM.FIELDS}
        pipeline_detail[stem] = {"candidates": cands, "fields": fields}

        with open(os.path.join(RAW, f"{stem}.json"), "w") as f:
            json.dump({
                "image": name,
                "ocr": {"finish_reason": resp["finish_reason"],
                        "elapsed_s": resp["elapsed_s"],
                        "usage": resp["usage"],
                        "element_count": len(elements)},
                "elements": elements,
                "candidates": cands,
                "fields": fields,
                "final": pipeline_preds[stem],
            }, f, ensure_ascii=False, indent=2)
        print(f"    -> {pipeline_preds[stem]}")

    # baseline
    with open(BASELINE_PATH) as f:
        base_raw = json.load(f)
    baseline_preds = {}
    for name in IMAGES:
        stem = os.path.splitext(name)[0]
        rec = base_raw.get(name, {})
        baseline_preds[stem] = {f: norm_baseline(f, rec.get(f)) for f in GTM.FIELDS}

    pipe_metrics = score_system(pipeline_preds)
    base_metrics = score_system(baseline_preds)
    csa = candidate_selection_accuracy(pipeline_detail)

    summary = {
        "images": IMAGES,
        "fields": GTM.FIELDS,
        "baseline_source": "single_field_test/results/results.json "
                           "(Image -> Hunyuan -> answer, 1 field / request, temp=0)",
        "baseline_historical_8field_accuracy": 0.396,
        "baseline": {k: v for k, v in base_metrics.items() if k != "rows"},
        "pipeline": {k: v for k, v in pipe_metrics.items() if k != "rows"},
        "candidate_selection": csa,
        "baseline_rows": base_metrics["rows"],
        "pipeline_rows": pipe_metrics["rows"],
        "pipeline_predictions": pipeline_preds,
        "baseline_predictions": baseline_preds,
    }
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # comparison.csv
    with open(os.path.join(RESULTS, "comparison.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field", "direct_hunyuan", "spatial_pipeline", "change"])
        for fld in GTM.FIELDS:
            b = base_metrics["per_field"][fld]["accuracy"]
            p = pipe_metrics["per_field"][fld]["accuracy"]
            w.writerow([fld, f"{b:.3f}", f"{p:.3f}", f"{p - b:+.3f}"])
        w.writerow(["OVERALL (6 fields)",
                    f"{base_metrics['overall_accuracy']:.3f}",
                    f"{pipe_metrics['overall_accuracy']:.3f}",
                    f"{pipe_metrics['overall_accuracy'] - base_metrics['overall_accuracy']:+.3f}"])
        w.writerow(["baseline historical (8 fields, 48 req)", "0.396", "", ""])

    # console table
    print("\n== RESULTS ==")
    print(f"{'field':<22}{'DirectHunyuan':>15}{'Spatial':>12}{'change':>10}")
    for fld in GTM.FIELDS:
        b = base_metrics["per_field"][fld]["accuracy"]
        p = pipe_metrics["per_field"][fld]["accuracy"]
        print(f"{fld:<22}{b:>15.3f}{p:>12.3f}{p - b:>+10.3f}")
    print(f"{'OVERALL (6f)':<22}{base_metrics['overall_accuracy']:>15.3f}"
          f"{pipe_metrics['overall_accuracy']:>12.3f}"
          f"{pipe_metrics['overall_accuracy'] - base_metrics['overall_accuracy']:>+10.3f}")
    print(f"\nnull-hallucination rate:  baseline={base_metrics['null_hallucination_rate']:.3f}"
          f"   pipeline={pipe_metrics['null_hallucination_rate']:.3f}")
    print(f"candidate-selection accuracy (pipeline): "
          f"{csa['candidate_selection_accuracy']}  "
          f"({csa['selected_correct']}/{csa['candidate_present_slots']})")
    print(f"\n[out] {RESULTS}/summary.json  comparison.csv  raw/*.json")


if __name__ == "__main__":
    main()
