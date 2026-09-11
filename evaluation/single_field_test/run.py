"""
Single-field smoke test: one field per API request, plain text answer (no
JSON, no schema), no cross-question context. Each of the 8 fields is asked
in its own independent request against each image -- the answer to one
question is never fed into another. temperature=0, same model/server as
every prior test in this history.

Purpose: isolate whether the accuracy problems seen in V1 (one big JSON
schema) and V2 (9 explicit questions still batched into one JSON request)
are caused by asking multiple fields at once, or are inherent to the
model regardless of how narrowly the question is scoped.

Runs a representative SAMPLE of the 20-image set, not the full batch --
per instruction, this is a smoke test to decide whether the full 20x8
run is even worth doing.

Does not touch mama-helper. No prompt tuning after seeing results.
"""
import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

PROMPTS = json.load(open(os.path.join(os.path.dirname(__file__), "prompts.json")))

IMAGES_DIR = "/Users/willeychen/Desktop/mama-helper/demo_image"
OUT_DIR = os.path.join(os.path.dirname(__file__), "results")
BASE_URL = "http://127.0.0.1:8090/v1"

# Representative sample covering the failure modes seen so far:
#  - SCE_Bill_Letter: our most-analyzed baseline (real sender vs a
#    non-person "Group N001" addressee, no real due date)
#  - Hospital_Bill: real named recipient competing with real sender name
#    (the classic sender/recipient swap case), known amount error
#    ($654.80 total charges vs true $419.07 balance)
#  - Medical_Invoice: known severe amount error ($900 line item vs true
#    $14,595 total)
#  - BOA_Bill_Example: has a real, explicit, quantified risk (late fee +
#    APR increase) that both V1 and V2 missed
#  - Medicare_Notice_PartA: explicit "THIS IS NOT A BILL" -- tests whether
#    payment_status/action_required correctly resolve to non-bill values
#  - IRS_cp503: real due date, real sender, real explicit risk, real named
#    recipient -- the "everything is real and present" case
SAMPLE_IMAGES = [
    "SCE_Bill_Letter.png",
    "Hospital_Bill.png",
    "Medical_Invoice.png",
    "BOA_Bill_Example.png",
    "Medicare_Notice_PartA.png",
    "IRS_cp503.png",
]


def _uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


def call(path, question, timeout=120):
    payload = {
        "model": "HYVL", "temperature": 0.0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _uri(path)}},
            {"type": "text", "text": question},
        ]}],
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    for name in SAMPLE_IMAGES:
        path = os.path.join(IMAGES_DIR, name)
        print(f"\n=== {name} ===")
        results[name] = {}
        for field, question in PROMPTS.items():
            t0 = time.perf_counter()
            try:
                resp = call(path, question)
                elapsed = time.perf_counter() - t0
                content = resp["choices"][0]["message"]["content"].strip()
                results[name][field] = content
                print(f"  {field:16s}: {content}   ({elapsed:.1f}s)")
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                results[name][field] = f"ERROR: {e}"
                print(f"  {field:16s}: ERROR: {e}")

    with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[done] -> {OUT_DIR}/results.json")


if __name__ == "__main__":
    main()
