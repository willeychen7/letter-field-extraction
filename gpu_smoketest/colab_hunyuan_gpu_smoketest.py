# =============================================================================
#  HunyuanOCR  ·  free-GPU smoke test  (Google Colab, T4 free tier)
#
#  Verifies: Colab GPU · llama.cpp CUDA build · hunyuan_vl load · mmproj load ·
#  one real letter OCRs · latency · output still matches the {text,bbox} contract.
#
#  DOES NOT touch: Phase 3-8, the OCR prompt, the OCR algorithm, the GGUF models.
#  Uses the EXACT same files and prompt as production.
#
#  How to use: open https://colab.research.google.com , New notebook,
#  Runtime -> Change runtime type -> T4 GPU, then paste each CELL below into
#  its own code cell and run top to bottom.
# =============================================================================


# ==== CELL 1 — confirm a free NVIDIA GPU ======================================
import subprocess
print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout or
      "!!! NO GPU. Runtime -> Change runtime type -> Hardware accelerator: T4 GPU, then rerun.")
# Expect: a table showing 'Tesla T4' (or L4/A100) and ~15360MiB. If it says
# 'No GPU', stop here and tell the owner Colab isn't giving a free GPU right now.


# ==== CELL 2 — build llama.cpp with CUDA (official source, ~4-6 min) =========
# (Colab already has the CUDA toolkit + cmake; this is the same code as the
#  ghcr.io/ggml-org/llama.cpp:server-cuda image, just built here.)
import os, subprocess, textwrap
os.chdir("/content")
if not os.path.isdir("llama.cpp"):
    subprocess.run(["git", "clone", "--depth", "1",
                    "https://github.com/ggml-org/llama.cpp"], check=True)
os.chdir("/content/llama.cpp")
subprocess.run(["cmake", "-B", "build", "-DGGML_CUDA=ON",
                "-DLLAMA_CURL=OFF", "-DCMAKE_BUILD_TYPE=Release"], check=True)
subprocess.run(["cmake", "--build", "build", "--config", "Release",
                "-j", str(os.cpu_count()), "--target", "llama-server"], check=True)
SERVER = "/content/llama.cpp/build/bin/llama-server"
print("built:", SERVER, "exists:", os.path.exists(SERVER))
print(subprocess.run([SERVER, "--version"], capture_output=True, text=True).stderr[:400])


# ==== CELL 3 — get the EXACT two GGUF files ==================================
# Pick ONE of the three ways. The files must be byte-identical to production:
#   HunyuanOCR-Q8_0.gguf         578,  MB   (sha256 optional but recommended)
#   mmproj-HunyuanOCR-Q8_0.gguf  733  MB
MODEL_DIR = "/content/models"
os.makedirs(MODEL_DIR, exist_ok=True)
LM   = f"{MODEL_DIR}/HunyuanOCR-Q8_0.gguf"
MMP  = f"{MODEL_DIR}/mmproj-HunyuanOCR-Q8_0.gguf"

# --- 3A. from a Hugging Face repo (fastest, no upload) ---------------------
#   Fill in the repo id you downloaded these from on Sep 4.
# from huggingface_hub import hf_hub_download
# HF_REPO = "PUT_THE_REPO_ID_HERE"          # e.g. "tencent/HunyuanOCR-GGUF"
# import shutil
# shutil.copy(hf_hub_download(HF_REPO, "HunyuanOCR-Q8_0.gguf"), LM)
# shutil.copy(hf_hub_download(HF_REPO, "mmproj-HunyuanOCR-Q8_0.gguf"), MMP)

# --- 3B. from Google Drive (put the two files in a Drive folder first) -----
# from google.colab import drive; drive.mount("/content/drive")
# import shutil
# SRC = "/content/drive/MyDrive/hunyuan_models"      # <- your Drive folder
# shutil.copy(f"{SRC}/HunyuanOCR-Q8_0.gguf", LM)
# shutil.copy(f"{SRC}/mmproj-HunyuanOCR-Q8_0.gguf", MMP)

# --- 3C. direct upload (1.3 GB, slow/flaky — last resort) -----------------
# from google.colab import files
# up = files.upload()   # choose BOTH .gguf files
# for name, data in up.items():
#     open(f"{MODEL_DIR}/{name}", "wb").write(data)

assert os.path.exists(LM) and os.path.exists(MMP), "models not in place — uncomment one of 3A/3B/3C"
print("LM  :", os.path.getsize(LM), "bytes")
print("MMP :", os.path.getsize(MMP), "bytes")
# Production sizes for reference: LM 577949408 , MMP 732938240
assert os.path.getsize(LM) == 577949408, "LM size mismatch — not the production file!"
assert os.path.getsize(MMP) == 732938240, "mmproj size mismatch — not the production file!"
print("OK: byte-exact production GGUFs")


# ==== CELL 4 — start llama-server (CUDA) with the SAME args as production ====
import subprocess, time, urllib.request, json, threading
# GPU-appropriate context (the ONLY change vs the Mac container: n_ctx 32768->8192,
# to stop the CPU-box OOM; it is a llama.cpp launch flag, not the OCR algorithm).
CMD = [SERVER,
       "-m", LM, "--mmproj", MMP,
       "-ngl", "99", "--ctx-size", "8192", "--parallel", "3",
       "--host", "127.0.0.1", "--port", "8090"]
logf = open("/content/llama.log", "w")
proc = subprocess.Popen(CMD, stdout=logf, stderr=subprocess.STDOUT)

def wait_ready(timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if urllib.request.urlopen("http://127.0.0.1:8090/health", timeout=3).status == 200:
                return True
        except Exception:
            pass
        if proc.poll() is not None:
            return False
        time.sleep(3)
    return False

ok = wait_ready()
print("=== llama.log (load section) ===")
print(open("/content/llama.log").read())
assert ok, "llama-server did not become ready — read the log above (this is where a "\
           "hunyuan_vl / mmproj CUDA incompatibility would show)."
# Expect in the log:
#   load_model: loading model '/content/models/HunyuanOCR-Q8_0.gguf'
#   ... offloading NN repeating layers to GPU ... offloaded NN/NN layers to GPU
#   clip_model_loader: ... (mmproj loads)
#   srv  load_model: loaded multimodal model, '/content/models/mmproj-HunyuanOCR-Q8_0.gguf'
#   main: model loaded / listening on http://127.0.0.1:8090
print("\n>>> CUDA server UP, hunyuan_vl + mmproj loaded")


# ==== CELL 5 — OCR ONE real letter with the EXACT production prompt =========
from google.colab import files
print("Upload ONE real letter image (png/jpg) — e.g. AAA_insurance_Bill.png")
up = files.upload()
img_name = next(iter(up))
img_bytes = up[img_name]

import base64, time, json, urllib.request
SPOTTING_HUNYUAN_PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"  # verbatim, frozen
mime = "image/png" if img_name.lower().endswith(".png") else "image/jpeg"
payload = {
    "model": "HYVL", "temperature": 0.0, "max_tokens": 8192,
    "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url":
            {"url": f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"}},
        {"type": "text", "text": SPOTTING_HUNYUAN_PROMPT},
    ]}],
}
req = urllib.request.Request("http://127.0.0.1:8090/v1/chat/completions",
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    method="POST")
t0 = time.time()
resp = json.loads(urllib.request.urlopen(req, timeout=400).read())
latency = time.time() - t0
ch = resp["choices"][0]
raw_content = ch["message"]["content"]
finish_reason = ch.get("finish_reason")
usage = resp.get("usage", {})
print(f"image           : {img_name}")
print(f"OCR latency     : {latency:.2f} s")
print(f"finish_reason   : {finish_reason}  (truncated = {finish_reason == 'length'})")
print(f"prompt/compl tok: {usage.get('prompt_tokens')} / {usage.get('completion_tokens')}")
print(f"raw_content head: {raw_content[:160]!r}")


# ==== CELL 6 — check the {text,bbox} contract (frozen parser, verbatim copy) =
# This is ocr.py::parse_ocr_elements copied UNCHANGED, only so the check can
# run in Colab where the repo isn't present. Not a modification of Phase 3.
def _read_int(s, i):
    n = len(s)
    while i < n and s[i] == " ": i += 1
    j = i
    while j < n and s[j].isdigit(): j += 1
    if j == i: return None, i
    return int(s[i:j]), j

def _try_coord_group(s, i):
    n = len(s); k = i
    if k >= n or s[k] != "(": return None, i
    k += 1; a, k = _read_int(s, k)
    if a is None or k >= n or s[k] != ",": return None, i
    k += 1; b, k = _read_int(s, k)
    if b is None or k >= n or s[k] != ")": return None, i
    k += 1
    if k >= n or s[k] != ",": return None, i
    k += 1
    if k >= n or s[k] != "(": return None, i
    k += 1; c, k = _read_int(s, k)
    if c is None or k >= n or s[k] != ",": return None, i
    k += 1; d, k = _read_int(s, k)
    if d is None or k >= n or s[k] != ")": return None, i
    k += 1
    return [a, b, c, d], k

def parse_ocr_elements(content):
    s = content.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1: s = s[nl + 1:]
        if s.rstrip().endswith("```"): s = s.rstrip()[:-3]
    elements = []; n = len(s); i = 0; text_start = 0
    while i < n:
        if s[i] == "(":
            bbox, k = _try_coord_group(s, i)
            if bbox is not None:
                raw_text = s[text_start:i].strip().strip(" \n\r\t")
                if raw_text: elements.append({"text": raw_text, "bbox": bbox})
                i = k; text_start = i; continue
        i += 1
    return elements

elements = parse_ocr_elements(raw_content)
print(f"element_count   : {len(elements)}")
print(f"first 3         : {elements[:3]}")
keys = sorted({k for e in elements for k in e})
print(f"keys per element: {keys}   (must be exactly ['bbox', 'text'])")
assert keys == ["bbox", "text"], "CONTRACT BREAK: element has keys other than text/bbox"
assert all(isinstance(e["bbox"], list) and len(e["bbox"]) == 4 for e in elements), "bad bbox"
assert not any("confidence" in e for e in elements), "confidence leaked in"
print("OK: output still matches the {text, bbox} contract, no confidence, no page")


# ==== CELL 7 — smoke-test verdict ============================================
print("=" * 60)
print("HunyuanOCR free-GPU smoke test")
print("=" * 60)
print(f"1. Colab NVIDIA GPU              : (see CELL 1 — expect Tesla T4)")
print(f"2. llama.cpp CUDA build runs     : YES (server came up)")
print(f"3. hunyuan_vl model loads        : YES (see CELL 4 load log)")
print(f"4. mmproj works                  : YES ('loaded multimodal model' + OCR produced coords)")
print(f"5. one real letter OCRs          : YES ({img_name})")
print(f"6. OCR latency                   : {latency:.2f} s   (CPU Docker was: median 61s / max 294s)")
print(f"7. {{text,bbox}} contract holds    : YES ({len(elements)} elements, keys {keys})")
print(f"   truncated flag                : {finish_reason == 'length'}")
print(f"   raw_content captured          : YES ({len(raw_content)} chars)")
print("-> Phase 3-8 need no change: they consume exactly this elements list.")

# tidy up
proc.terminate()
