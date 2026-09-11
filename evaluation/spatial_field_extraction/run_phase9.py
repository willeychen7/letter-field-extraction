"""
Phase 9 -- End-to-End evaluation (plan B).

  image -> POST hunyuan-service /v1/ocr  (LIVE, no cached OCR as input)
        -> elements
        -> frozen Phase 3 -> Phase 4 -> Phase 7   (field_semantics.resolve)
        -> frozen Phase 8   (phone_extract + contact_pick)
        -> final structured result
        -> scored vs ground_truth_20 / ground_truth_holdout / Phase-8 GT

Also (Step 5 regression): cached-OCR -> frozen pipeline  vs
                          live-OCR   -> frozen pipeline, final-output diff.

Nothing in Phase 3-8 is imported-and-modified; only consumed.

    python3 run_phase9.py --ocr      # live /v1/ocr for all 50 (resumable)
    python3 run_phase9.py --score    # score + attribute + regression
    python3 run_phase9.py            # both
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

import contact_pick as CP
import field_semantics as FS
import ground_truth as GTM
import phone_extract as PE
from ground_truth_20 import GT20
from ground_truth_holdout import GT_HOLD
from gt_domain import GT_DOMAIN
from ocr import parse_ocr_elements
from run_phase8 import GT_CONTACT

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "results", "phase9")
RAW = os.path.join(OUT, "raw")
OCR_URL = os.environ.get("HUNYUAN_SERVICE_URL", "http://localhost:8091/v1/ocr")
IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
CONV_DIR = os.path.join(HERE, "holdout_images")

FIELDS = ["sender", "recipient", "total_amount", "payment_status", "due_date", "action"]


def _img_path(key):
    for d in (IMAGES_DIR, CONV_DIR):
        for ext in (".png", ".jpg", ".jpeg"):
            p = os.path.join(d, key + ext)
            if os.path.exists(p):
                return p
    return None


def live_ocr(key, retries=2):
    """POST to /v1/ocr. The Docker CPU-only llama container crashes under
    sustained load (~every 12-15 heavy multimodal reqs) and auto-restarts
    via its `--restart` policy -> retry 502 with backoff so a batch can
    still complete. This is client-side resilience only; the OCR algorithm
    and the endpoint are untouched."""
    p = _img_path(key)
    if p is None:
        return None
    mime = "image/jpeg" if p.endswith((".jpg", ".jpeg")) else "image/png"
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    body = json.dumps({"image_base64": b64, "mime": mime}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(OCR_URL, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        t0 = time.perf_counter()
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=400).read())
            d["_client_roundtrip_s"] = round(time.perf_counter() - t0, 3)
            d["_attempts"] = attempt + 1
            return d
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (502, 503, 504) and attempt < retries - 1:
                wait = 20
                print(f"      {key}: HTTP {e.code}, waiting {wait}s for llama to recover "
                      f"(attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
    raise last


def do_ocr():
    os.makedirs(RAW, exist_ok=True)
    keys = list(GT_DOMAIN)
    for i, k in enumerate(keys, 1):
        f = os.path.join(RAW, k + ".ocr.json")
        if os.path.exists(f):
            print(f"[{i}/{len(keys)}] skip {k}")
            continue
        try:
            r = live_ocr(k)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(keys)}] ERROR {k}: {e}")
            json.dump({"error": str(e)}, open(f, "w"))
            continue
        if r is None:
            print(f"[{i}/{len(keys)}] MISSING IMAGE {k}")
            continue
        json.dump(r, open(f, "w"), ensure_ascii=False, indent=2)
        print(f"[{i}/{len(keys)}] {k:30s} els={r['element_count']:4d} "
              f"trunc={r['truncated']} ocr_s={r['timing']['inference_s']} "
              f"rt_s={r['_client_roundtrip_s']} attempts={r.get('_attempts', 1)}",
              flush=True)
        time.sleep(6)  # let the CPU-only container drain KV cache between images


# ---------------------------------------------------------------- pipeline

def run_pipeline(elements):
    fs = FS.resolve(elements)
    fields = {f: fs[f]["value"] for f in FIELDS}
    phones = PE.extract_phones(elements)
    contact = CP.pick_contact(phones, fs["action"]["value"], fs["_domain"],
                              fs["sender"]["value"])
    return {
        "fields": fields,
        "domain": fs["_domain"],
        "domain_gap": fs["_domain_gap"],
        "statuses": {f: fs[f].get("_status") for f in FIELDS},
        "reasons": {f: fs[f].get("_reason") for f in FIELDS},
        "contact": contact,
    }


# ---------------------------------------------------------------- scoring

_ALIASES_DOMAIN = {  # our-GT-vs-classifier debatable pairs (Phase 4 study)
    ("HEALTHCARE", "GOVERNMENT"), ("GOVERNMENT", "HEALTHCARE"),
    ("HOUSING_PROPERTY", "INSURANCE"), ("INSURANCE", "HOUSING_PROPERTY"),
    ("OTHER", "UTILITIES_SERVICES"), ("UTILITIES_SERVICES", "OTHER"),
}


def score_all(pred_by_key, elems_by_key, trunc_by_key):
    gts = {**GT20, **GT_HOLD}
    per_field = {f: [0, 0] for f in FIELDS}
    dom_ok = dom_tot = 0
    contact_org_ok = contact_type_ok = phone_ok = c_graded = 0
    kinds = Counter()
    halluc = 0
    attribution = Counter()
    rows = []

    for k, pr in pred_by_key.items():
        gt = gts[k]
        gdom = GT_DOMAIN[k][0]
        els = elems_by_key[k]
        joined = " ".join(e["text"].lower() for e in els)
        trunc = trunc_by_key[k]

        # domain
        dom_tot += 1
        d_ok = pr["domain"] == gdom
        dom_ok += d_ok
        if not d_ok:
            attribution["D. Phase 4 domain"] += 1
        rows.append({"key": k, "field": "domain", "pred": pr["domain"],
                     "gold": gdom, "ok": d_ok})

        # the 6 core fields
        for f in FIELDS:
            entry = gt[f]
            pv = pr["fields"][f]
            ok, kind = GTM.score_field(f, pv, entry)
            per_field[f][0] += ok
            per_field[f][1] += 1
            kinds[kind] += 1
            if kind == "null_hallucination":
                halluc += 1
            rows.append({"key": k, "field": f, "pred": pv, "gold": entry["value"],
                         "ok": ok, "kind": kind})
            if ok:
                continue
            # ---- attribution for this wrong cell ----
            gold_txt = str(entry["value"] or "")
            gold_in_ocr = gold_txt and any(
                gold_txt.replace("$", "").replace(",", "")[:6].lower() in joined
                or gold_txt.lower() in joined for _ in [0])
            if trunc:
                attribution["B. OCR truncated"] += 1
            elif entry["value"] is not None and gold_txt and not gold_in_ocr \
                    and f in ("sender", "recipient", "total_amount", "due_date"):
                attribution["A. OCR did not read it"] += 1
            elif None in entry.get("accept", []) or kind == "both_null":
                attribution["G. GT / boundary"] += 1
            elif not d_ok or (pr["domain_gap"] < FS.CONF_MIN
                              and pr["domain"] not in FS.ALWAYS_TRUSTED
                              and f in ("total_amount", "payment_status")):
                attribution["D. Phase 4 domain"] += 1
            elif f in ("total_amount", "payment_status"):
                attribution["E. Phase 7 semantic field"] += 1
            elif f == "action":
                attribution["E. Phase 7 semantic field"] += 1
            else:  # sender / recipient / due_date, OCR had it, domain right
                attribution["C. Phase 3 spatial extraction"] += 1

        # contact / phone
        gc = GT_CONTACT.get(k)
        if gc is not None:
            c_graded += 1
            gnum, gtype = gc
            c = pr["contact"]
            pnum = c["phone_number"]
            p_ok = (pnum == gnum) if gnum is not None else (pnum is None)
            phone_ok += p_ok
            t_ok = (c["contact_type"] == gtype) if gtype is not None \
                else (c["contact_type"] is None)
            contact_type_ok += t_ok
            # contact_organization: no explicit GT -> lenient: correct when a
            # phone was (correctly) picked and org is non-empty or == sender,
            # or when correctly null
            if gnum is None:
                o_ok = pnum is None
            else:
                o_ok = p_ok and bool(c["contact_organization"])
            contact_org_ok += o_ok
            rows.append({"key": k, "field": "phone", "pred": pnum, "gold": gnum,
                         "ok": p_ok})
            if not p_ok:
                if trunc:
                    attribution["B. OCR truncated"] += 1
                elif gnum and gnum not in "".join(
                        e["text"] for e in els).replace("-", "").replace(" ", ""):
                    attribution["A. OCR did not read it"] += 1
                else:
                    attribution["F. Phase 8 contact/phone"] += 1

    total_cells = dom_tot + sum(v[1] for v in per_field.values()) + c_graded
    total_ok = dom_ok + sum(v[0] for v in per_field.values()) + phone_ok
    return {
        "domain": {"acc": round(dom_ok / dom_tot, 4), "err": dom_tot - dom_ok},
        "per_field": {f: {"acc": round(v[0] / v[1], 4), "err": v[1] - v[0]}
                      for f, v in per_field.items()},
        "contact_organization": {"acc": round(contact_org_ok / c_graded, 4),
                                 "err": c_graded - contact_org_ok},
        "contact_type": {"acc": round(contact_type_ok / c_graded, 4),
                         "err": c_graded - contact_type_ok},
        "phone": {"acc": round(phone_ok / c_graded, 4), "err": c_graded - phone_ok},
        "overall": {"acc": round(total_ok / total_cells, 4),
                    "ok": total_ok, "cells": total_cells},
        "hallucination": halluc,
        "answer_kinds": dict(kinds),
        "attribution": dict(attribution),
        "rows": rows,
    }


def do_score():
    keys = list(GT_DOMAIN)
    live_raw, live_elems, trunc, ocr_lat, e2e_lat = {}, {}, {}, [], []
    live_pred, cached_pred = {}, {}
    ocr_fail = []

    for k in keys:
        f = os.path.join(RAW, k + ".ocr.json")
        if not os.path.exists(f):
            ocr_fail.append((k, "no file"))
            continue
        r = json.load(open(f))
        if r.get("error"):
            ocr_fail.append((k, r["error"]))
            continue
        live_raw[k] = r
        els = parse_ocr_elements(r["raw_content"])
        # contract check: endpoint elements must equal reparse of raw_content
        assert els == r["elements"], f"{k}: elements != parse(raw_content)"
        live_elems[k] = els
        trunc[k] = r["truncated"]
        ocr_lat.append(r["timing"]["inference_s"] or 0)

        t0 = time.perf_counter()
        live_pred[k] = run_pipeline(els)
        e2e_lat.append((r["timing"]["inference_s"] or 0)
                       + round(time.perf_counter() - t0, 3))

        # cached OCR for the same image (regression)
        for cdir in ("full20", "holdout"):
            cf = os.path.join(HERE, "results", cdir, "raw", k + ".ocr.json")
            if os.path.exists(cf):
                cels = parse_ocr_elements(json.load(open(cf))["content"])
                cached_pred[k] = run_pipeline(cels)
                break

    S = score_all(live_pred, live_elems, trunc)

    # Step-5 regression: live vs cached final output
    reg_diffs = []
    for k in cached_pred:
        lv, cv = live_pred[k], cached_pred[k]
        d = {}
        for f in FIELDS:
            if lv["fields"][f] != cv["fields"][f]:
                d[f] = (cv["fields"][f], lv["fields"][f])
        if lv["domain"] != cv["domain"]:
            d["domain"] = (cv["domain"], lv["domain"])
        if lv["contact"]["phone_number"] != cv["contact"]["phone_number"]:
            d["phone"] = (cv["contact"]["phone_number"], lv["contact"]["phone_number"])
        if d:
            reg_diffs.append({"key": k, "diffs": d})

    n = len(live_elems)
    latency = {
        "ocr_inference_s": {"mean": round(sum(ocr_lat) / n, 1),
                            "min": round(min(ocr_lat), 1), "max": round(max(ocr_lat), 1)},
        "e2e_s": {"mean": round(sum(e2e_lat) / n, 1),
                  "min": round(min(e2e_lat), 1), "max": round(max(e2e_lat), 1)},
    }
    summary = {
        "dataset": "50 real US letters (20 dev + 30 holdout), LIVE /v1/ocr",
        "images": len(GT_DOMAIN),
        "live_ocr_success": n,
        "live_ocr_failed": ocr_fail,
        "ocr_truncated": [k for k in trunc if trunc[k]],
        "latency": latency,
        "metrics": {kk: S[kk] for kk in ("domain", "per_field", "contact_organization",
                                         "contact_type", "phone", "overall",
                                         "hallucination", "answer_kinds", "attribution")},
        "regression_live_vs_cached": {
            "compared": len(cached_pred),
            "identical": len(cached_pred) - len(reg_diffs),
            "diffs": reg_diffs,
        },
        "rows": S["rows"],
    }
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"),
              ensure_ascii=False, indent=2)

    m = S
    print("=== Phase 9 E2E ===")
    print(f"images={len(GT_DOMAIN)}  live OCR ok={n}  failed={len(ocr_fail)}  "
          f"truncated={len(summary['ocr_truncated'])} {summary['ocr_truncated']}")
    print(f"OCR inference s: mean {latency['ocr_inference_s']['mean']} "
          f"(max {latency['ocr_inference_s']['max']})")
    print(f"E2E s         : mean {latency['e2e_s']['mean']} "
          f"(max {latency['e2e_s']['max']})")
    print(f"\nOVERALL {m['overall']['acc']:.3f}  ({m['overall']['ok']}/{m['overall']['cells']})"
          f"   hallucination={m['hallucination']}")
    print(f"\n{'field':<22}{'acc':>8}{'err':>6}")
    print(f"{'Domain':<22}{m['domain']['acc']:>8.3f}{m['domain']['err']:>6}")
    for f in FIELDS:
        print(f"{f:<22}{m['per_field'][f]['acc']:>8.3f}{m['per_field'][f]['err']:>6}")
    for f in ("contact_organization", "contact_type", "phone"):
        print(f"{f:<22}{m[f]['acc']:>8.3f}{m[f]['err']:>6}")
    print(f"\nanswer kinds : {m['answer_kinds']}")
    print(f"attribution  : {m['attribution']}")
    print(f"\nregression live-vs-cached: {summary['regression_live_vs_cached']['identical']}"
          f"/{summary['regression_live_vs_cached']['compared']} identical")
    for d in reg_diffs:
        print(f"   DIFF {d['key']}: {d['diffs']}")
    print(f"\n[out] {OUT}/summary.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.ocr or not (a.ocr or a.score):
        do_ocr()
    if a.score or not (a.ocr or a.score):
        do_score()


if __name__ == "__main__":
    main()
