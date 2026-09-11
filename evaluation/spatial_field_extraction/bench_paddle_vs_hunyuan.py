"""
Same-image, same-pipeline, different-OCR-front-end comparison:
PaddleOCR {text,bbox} -> frozen field_semantics.resolve()  vs
HunyuanOCR {text,bbox} -> frozen field_semantics.resolve()

No regex added anywhere. Phase 3-8 code is not modified, not called
differently -- only the OCR *elements* fed into it change. Read-only,
uses only OCR results already cached on disk (no new model calls).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import field_semantics as FS          # frozen
import ground_truth as GTM
from ground_truth_20 import GT20
from ground_truth_holdout import GT_HOLD
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements    # frozen

GT = {**GT20, **GT_HOLD}
PP_PATH = "/Users/willeychen/Desktop/mama-helper/frontend/src/utils/demo_ocr_pp.json"
FIELDS = ["sender", "recipient", "total_amount", "payment_status", "due_date", "action"]


def paddle_elements(entry):
    """PaddleOCR {lines:[{text,left,top,right,bottom}], width, height}
    -> the exact {text, bbox:[x1,y1,x2,y2]} contract Phase 3-8 expects,
    normalised to 0-1000 like HunyuanOCR's coordinate space (structure.py's
    PAGE_W/PAGE_H = 1000 and every threshold in it assumes this space)."""
    w, h = entry["width"], entry["height"]
    out = []
    for ln in entry["lines"]:
        out.append({
            "text": ln["text"],
            "bbox": [ln["left"] / w * 1000, ln["top"] / h * 1000,
                    ln["right"] / w * 1000, ln["bottom"] / h * 1000],
        })
    return out


def hunyuan_elements(key):
    r = json.load(open(os.path.join(HERE, "results", "phase9", "raw", key + ".ocr.json")))
    if "raw_content" not in r:
        return None  # this image's live OCR call errored (e.g. SoCalGas, 502) -- excluded
    return parse_ocr_elements(r["raw_content"])


def score_source(name, elements_by_key, keys):
    per_field = {f: [0, 0] for f in FIELDS}
    dom_ok = dom_tot = 0
    halluc = 0
    rows = []
    for k in keys:
        els = elements_by_key[k]
        fs = FS.resolve(els)
        gdom = GT_DOMAIN[k][0]
        dom_tot += 1
        d_ok = fs["_domain"] == gdom
        dom_ok += d_ok
        for f in FIELDS:
            pv = fs[f]["value"]
            ok, kind = GTM.score_field(f, pv, GT[k][f])
            per_field[f][0] += ok
            per_field[f][1] += 1
            if kind == "null_hallucination":
                halluc += 1
            rows.append({"source": name, "key": k, "field": f, "pred": pv,
                        "gold": GT[k][f]["value"], "ok": ok, "kind": kind})
    print(f"\n=== {name}  (same frozen field_semantics.resolve, {len(keys)} images) ===")
    print(f"  {'domain':15s} {dom_ok:2d}/{dom_tot:2d} = {dom_ok/dom_tot*100:5.1f}%")
    tot_ok = dom_ok
    tot_n = dom_tot
    for f in FIELDS:
        ok, tot = per_field[f]
        tot_ok += ok
        tot_n += tot
        print(f"  {f:15s} {ok:2d}/{tot:2d} = {ok/tot*100:5.1f}%")
    print(f"  {'OVERALL':15s} {tot_ok:2d}/{tot_n:2d} = {tot_ok/tot_n*100:5.1f}%   hallucinations={halluc}")
    return rows


def main():
    pp = json.load(open(PP_PATH))
    keys = sorted(k for k in pp if k in GT and
                 os.path.exists(os.path.join(HERE, "results", "phase9", "raw", k + ".ocr.json")))
    print("images used (have PaddleOCR cache + Hunyuan cache + our ground truth):", len(keys))
    print(keys)

    hunyuan_els = {k: hunyuan_elements(k) for k in keys}
    keys = [k for k in keys if hunyuan_els[k] is not None]
    print("images after dropping OCR-call failures:", len(keys))

    paddle_els = {k: paddle_elements(pp[k]) for k in keys}

    # sanity: show raw text shape difference on one example
    print("\n--- raw text shape, same line, SCE_Bill_Letter ---")
    print("PaddleOCR :", repr(paddle_els["SCE_Bill_Letter"][2]["text"]))
    print("HunyuanOCR:", repr(next(e["text"] for e in hunyuan_els["SCE_Bill_Letter"]
                                   if "SOUTHERN" in e["text"].upper())))

    rows_pp = score_source("PaddleOCR  -> Phase 3-8 (unmodified)", paddle_els, keys)
    rows_hy = score_source("HunyuanOCR -> Phase 3-8 (unmodified)", hunyuan_els, keys)

    out_dir = os.path.join(HERE, "results", "paddle_vs_hunyuan")
    os.makedirs(out_dir, exist_ok=True)
    json.dump({"rows": rows_pp + rows_hy}, open(os.path.join(out_dir, "scored.json"), "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
