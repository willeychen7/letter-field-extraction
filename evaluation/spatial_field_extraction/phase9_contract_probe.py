"""Minimal Phase-9 contract validation: prove the frozen pipeline needs
ONLY {text, bbox} from OCR, by running the whole stack from a live
container OCR call and comparing to the cached-OCR result."""
import base64, json, sys, urllib.request
sys.path.insert(0, ".")
from ocr import parse_ocr_elements
import field_semantics as FS
from phone_extract import extract_phones
from contact_pick import pick_contact

IMG = "/Users/willeychen/Desktop/mama-helper/demo_image/Hospital_Bill.png"
PROMPT = "检测并识别图片中的文字，将文本坐标格式化输出。"

def live_ocr(base_url):
    b64 = base64.b64encode(open(IMG,"rb").read()).decode()
    payload = {"model":"HYVL","temperature":0.0,"max_tokens":8192,"messages":[
        {"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}},
            {"type":"text","text":PROMPT}]}]}
    req = urllib.request.Request(f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    d = json.loads(urllib.request.urlopen(req, timeout=300).read())
    ch = d["choices"][0]
    return ch["message"]["content"], ch.get("finish_reason"), d.get("usage",{})

# 1. LIVE via the host->container llama (same path hunyuan-service would use internally)
content, finish, usage = live_ocr("http://127.0.0.1:8090/v1")
els_live = parse_ocr_elements(content)

# 2. CACHED (what all prior phases used)
els_cached = parse_ocr_elements(json.load(open("results/full20/raw/Hospital_Bill.ocr.json"))["content"])

def run(els):
    fs = FS.resolve(els)
    ph = extract_phones(els)
    contact = pick_contact(ph, fs["action"]["value"], fs["_domain"], fs["sender"]["value"])
    return {f: fs[f]["value"] for f in ("sender","recipient","total_amount","payment_status","due_date","action")}, fs["_domain"], contact["phone_number"], contact["contact_type"]

print("element counts  live=%d cached=%d  finish=%s ctok=%s" % (len(els_live), len(els_cached), finish, usage.get("completion_tokens")))
print("element shape   :", {k: type(els_live[0][k]).__name__ for k in els_live[0]})
print("sample element  :", els_live[0])
r_live, d_live, p_live, t_live = run(els_live)
r_cache, d_cache, p_cache, t_cache = run(els_cached)
print("\nLIVE   fields:", r_live, "| domain:", d_live, "| contact:", p_live, t_live)
print("CACHED fields:", r_cache, "| domain:", d_cache, "| contact:", p_cache, t_cache)
print("\nfields identical :", r_live == r_cache)
print("domain identical :", d_live == d_cache)
print("contact identical:", (p_live, t_live) == (p_cache, t_cache))
