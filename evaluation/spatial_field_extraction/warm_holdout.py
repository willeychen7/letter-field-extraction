import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from ocr import call_ocr
from holdout_set import HOLDOUT
HERE = os.path.dirname(__file__)
RAW = os.path.join(HERE, "results", "holdout", "raw")
os.makedirs(RAW, exist_ok=True)
for key, d, fn, cat in HOLDOUT:
    src = fn if d.startswith("/") else os.path.join(HERE, d, fn)
    src = os.path.join(d, fn) if d.startswith("/") else os.path.join(HERE, d, fn)
    cache = os.path.join(RAW, f"{key}.ocr.json")
    if os.path.exists(cache):
        print("skip", key, flush=True); continue
    if not os.path.exists(src):
        print("MISSING", key, src, flush=True); continue
    try:
        r = call_ocr(src, timeout=400)
        json.dump(r, open(cache, "w"), ensure_ascii=False, indent=2)
        open(os.path.join(RAW, f"{key}.ocr.txt"), "w").write(r["content"])
        print(f"{key:32s} {r['elapsed_s']:6.1f}s finish={r['finish_reason']} ctok={r['usage'].get('completion_tokens')}", flush=True)
    except Exception as e:
        print("ERR", key, repr(e), flush=True)
print("== warm_holdout done ==", flush=True)
