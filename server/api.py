"""
hunyuan-service · Phase 1 fixed API

A thin, stable HTTP boundary in front of the raw llama-server OpenAI-
compatible endpoint (default http://127.0.0.1:8090/v1). This is the
interface Mama Helper's own backend would eventually call in Phase 3 --
it exists so Mama Helper never has to know about llama-server's request
shape, the official prompt template, or Hunyuan's None/null quirks.

Run:
    cd hunyuan-service/server
    uvicorn api:app --reload --port 8091

This process does NOT talk to any third-party cloud API. Its only upstream
dependency is the local llama-server process on LLAMA_SERVER_URL (default
127.0.0.1:8090), which this machine controls.
"""

import base64
import json
import os
import sys
import tempfile
import time

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, "..", "schemas"))
from mama_helper_v1 import PROMPT, parse_model_output  # noqa: E402

# frozen Phase-3 OCR helpers -- reused verbatim, never modified here.
# In the Docker image ocr.py is copied to /app/ocr.py; for a local run it
# lives under evaluation/spatial_field_extraction/.
for _p in (os.path.join(_HERE, ".."),
           os.path.join(_HERE, "..", "evaluation", "spatial_field_extraction")):
    if os.path.exists(os.path.join(_p, "ocr.py")):
        sys.path.insert(0, _p)
        break
from ocr import call_ocr, parse_ocr_elements  # noqa: E402

# frozen Phase 3-8 pipeline -- these modules are IMPORTED AND CALLED ONLY,
# never edited here. They live next to ocr.py (local run) or are copied into
# the image (Docker). If they are not present the /v1/analyze route degrades
# to a 503; /v1/ocr and /v1/understand-letter are unaffected.
try:
    from field_semantics import resolve as _pipeline_resolve  # noqa: E402
    from phone_extract import extract_phones as _pipeline_extract_phones  # noqa: E402
    from contact_pick import pick_contact as _pipeline_pick_contact  # noqa: E402
    _PIPELINE_AVAILABLE = True
except ImportError:  # pragma: no cover - only when pipeline files absent
    _PIPELINE_AVAILABLE = False

try:
    import pypdfium2 as _pdfium  # noqa: E402  (PDF -> image, no system deps)
    _PDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PDF_AVAILABLE = False

LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8090/v1")
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB, matches mama-helper backend's own limit
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # a PDF may be a little larger than a photo

# the six frozen structured fields, in the order the UI shows them
_ANALYZE_FIELDS = ("sender", "recipient", "total_amount",
                   "payment_status", "due_date", "action")

app = FastAPI(title="hunyuan-service", version="0.1.0")


async def _read_request_image(request: Request):
    """Shared image reader for JSON / multipart callers. Returns
    (image_bytes, mime). Mirrors the rules of /v1/ocr exactly; kept as a
    helper so /v1/analyze does not duplicate the parsing (and /v1/ocr
    stays byte-for-byte the Phase 9 contract endpoint)."""
    ctype = request.headers.get("content-type", "")
    image_bytes = b""
    mime = "image/png"
    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        up = form.get("file")
        if up is None:
            raise HTTPException(status_code=400, detail="缺少 file 字段")
        image_bytes = await up.read()
        mime = getattr(up, "content_type", None) or mime
    elif ctype.startswith("application/json"):
        try:
            body = await request.json()
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}") from e
        b64 = body.get("image_base64")
        if not b64:
            raise HTTPException(status_code=400, detail="缺少 image_base64")
        try:
            image_bytes = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"image_base64 解码失败: {e}") from e
        mime = body.get("mime") or mime
    else:
        raise HTTPException(status_code=415,
                            detail="需要 multipart/form-data 或 application/json")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="没有读取到图片内容")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB 限制")
    return image_bytes, mime


def _pdf_first_page_to_png(pdf_bytes):
    """Render page 1 of a PDF to PNG bytes. Used only as pre-processing for
    /v1/analyze -- HunyuanOCR takes an image, so a PDF letter is rasterised
    here before it reaches the (untouched) OCR + Phase 3-8 path."""
    if not _PDF_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="服务器缺少 PDF 支持（pip install pypdfium2）。请改用 JPG / PNG。")
    try:
        doc = _pdfium.PdfDocument(pdf_bytes)
        if len(doc) == 0:
            raise HTTPException(status_code=400, detail="PDF 没有可读页面")
        page = doc[0]
        # scale 2.5 -> ~1500px wide for a US-Letter page: enough for OCR,
        # small enough to stay well under the 10MB image ceiling.
        pil = page.render(scale=2.5).to_pil().convert("RGB")
        import io
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        return buf.getvalue()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"PDF 解析失败: {e}") from e


def _coerce_to_image(image_bytes, mime):
    """(bytes, mime) -> (image_bytes, mime) guaranteed to be a raster image.
    PDF in -> PNG of page 1 out. Everything else passes through."""
    is_pdf = (mime or "").lower() in ("application/pdf", "application/x-pdf") \
        or image_bytes[:5] == b"%PDF-"
    if is_pdf:
        png = _pdf_first_page_to_png(image_bytes)
        if len(png) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413,
                                detail="PDF 渲染后的图片过大，请提供分辨率更低的文件")
        return png, "image/png"
    return image_bytes, mime


def _run_pipeline(elements):
    """OCR elements -> frozen Phase 3-8 -> flat structured result. This is
    the SAME call sequence as evaluation/spatial_field_extraction/
    run_phase9.py::run_pipeline -- no logic added, no rule added, no model
    added. Presentation (English enum -> user text) is the frontend's job.
    """
    fs = _pipeline_resolve(elements)
    phones = _pipeline_extract_phones(elements)
    contact = _pipeline_pick_contact(phones, fs["action"]["value"],
                                     fs["_domain"], fs["sender"]["value"])
    fields = {}
    for f in _ANALYZE_FIELDS:
        fields[f] = {
            "value": fs[f]["value"],
            "status": fs[f].get("_status"),
            "reason": fs[f].get("_reason"),
        }
    return {
        "domain": fs["_domain"],
        "domain_gap": fs.get("_domain_gap"),
        "fields": fields,
        "contact": {
            "phone_number": contact.get("phone_number"),
            "contact_type": contact.get("contact_type"),
            "contact_organization": contact.get("contact_organization"),
        },
        "cross_validation": fs.get("_cross_validation", []),
    }


@app.get("/health")
async def health():
    """Reports both this process's health and whether it can currently
    reach the local llama-server -- callers should treat a degraded
    upstream the same as this service being down.
    """
    upstream_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{LLAMA_SERVER_URL.rstrip('/v1')}/health")
            upstream_ok = r.status_code == 200
    except httpx.HTTPError:
        upstream_ok = False
    return {"status": "ok", "upstream_llama_server": upstream_ok}


@app.post("/v1/understand-letter")
async def understand_letter(file: UploadFile = File(...)):
    """
    Input: a single letter photo (jpg/png/webp -- note: the underlying
    llama-server image loader has been observed to reject .webp; convert
    client-side if needed).

    Output: {status, fields, parse_status, raw_content, timing}
      - fields: the 9-field mama_helper_v1 schema, None-normalized, NOT
        yet validated against fieldExtractor.js's cross-checks (amount
        plausibility, date ordering, sender-looks-like-a-name). Mama
        Helper's caller is responsible for running that validation layer
        before showing any field to a user -- this endpoint only reports
        what Hunyuan said, never whether it should be trusted.
      - raw_content: the model's unmodified text response, always
        included, so a caller can audit what actually came back even when
        parse_status != "valid_json_object".
    """
    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片超过 10MB 限制")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="没有读取到图片内容")

    mime = file.content_type or "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:{mime};base64,{b64}"

    payload = {
        "model": "HYVL",
        "temperature": 0.0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{LLAMA_SERVER_URL}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"无法连接本地 Hunyuan 服务: {e}") from e
    elapsed = time.perf_counter() - t0

    try:
        content = data["choices"][0]["message"]["content"]
        finish_reason = data["choices"][0].get("finish_reason")
        usage = data.get("usage", {})
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"Hunyuan 返回格式异常: {e}") from e

    fields, parse_status = parse_model_output(content)

    return JSONResponse(
        {
            "status": "ok",
            "parse_status": parse_status,
            "fields": fields,
            "raw_content": content,
            "finish_reason": finish_reason,
            "timing": {
                "inference_time_s": round(elapsed, 3),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            },
        }
    )


@app.post("/v1/ocr")
async def ocr(request: Request):
    """
    Minimal OCR / spotting endpoint (Phase 9 contract).

    Input (same rules as /v1/understand-letter):
      - multipart/form-data with a `file` field, OR
      - application/json  {"image_base64": "...", "mime": "image/png"}
      - png / jpg / jpeg only, <= 10MB

    Output: the exact list `ocr.parse_ocr_elements()` produces -- every
    element is strictly {text, bbox}, bbox = [x1,y1,x2,y2] normalised to
    [0,1000], origin top-left. No confidence, no page, no pixel size.
    `truncated` = (finish_reason == "length"). `raw_content` is the
    model's untouched coordinate string, kept for audit / offline replay.
    The frozen Phase 3-8 pipeline consumes `elements` verbatim.
    """
    ctype = request.headers.get("content-type", "")
    image_bytes = b""
    mime = "image/png"

    if ctype.startswith("multipart/form-data"):
        form = await request.form()
        up = form.get("file")
        if up is None:
            raise HTTPException(status_code=400, detail="缺少 file 字段")
        image_bytes = await up.read()
        mime = getattr(up, "content_type", None) or mime
    elif ctype.startswith("application/json"):
        try:
            body = await request.json()
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}") from e
        b64 = body.get("image_base64")
        if not b64:
            raise HTTPException(status_code=400, detail="缺少 image_base64")
        try:
            image_bytes = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"image_base64 解码失败: {e}") from e
        mime = body.get("mime") or mime
    else:
        raise HTTPException(status_code=415,
                            detail="需要 multipart/form-data 或 application/json")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="没有读取到图片内容")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片超过 10MB 限制")

    ext = {"image/png": ".png", "image/jpeg": ".jpg",
           "image/jpg": ".jpg"}.get((mime or "").lower(), ".png")

    tf = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tf.write(image_bytes)
        tf.flush()
        tf.close()
        try:
            # ocr.call_ocr takes a file path -> pass the temp file + our
            # upstream URL; the OCR algorithm itself is untouched.
            resp = await run_in_threadpool(call_ocr, tf.name,
                                           base_url=LLAMA_SERVER_URL)
        except Exception as e:  # noqa: BLE001  (urllib.error / timeout / etc)
            raise HTTPException(status_code=502,
                                detail=f"无法连接本地 Hunyuan 服务: {e}") from e
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass

    content = resp["content"]
    elements = parse_ocr_elements(content)
    usage = resp.get("usage", {})

    return JSONResponse(
        {
            "status": "ok",
            "engine": {
                "model": "HYVL",
                "task": "spotting_hunyuan",
                "coord_space": "normalized_0_1000",
                "origin": "top_left",
            },
            "elements": elements,
            "element_count": len(elements),
            "truncated": resp.get("finish_reason") == "length",
            "raw_content": content,
            "timing": {
                "inference_s": resp.get("elapsed_s"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            },
        }
    )


@app.post("/v1/analyze")
async def analyze(request: Request):
    """
    One call: letter photo -> HunyuanOCR -> frozen Phase 3-8 -> the six
    structured fields + domain + contact. This is the endpoint the V0
    tester UI uses.

    Input:
      - multipart/form-data with a `file` field, OR
      - application/json {"image_base64": "...", "mime": "image/png"}
      - png / jpg / jpeg, OR a PDF (page 1 is rasterised here before OCR)
      - <= 20MB upload; a PDF must rasterise to <= 10MB

    Output:
      {
        "status": "ok",
        "domain": "UTILITIES_SERVICES",
        "domain_gap": 3.1,
        "fields": {
          "sender":         {"value": "...", "status": "resolved", "reason": "..."},
          "recipient":      {"value": null,  "status": "insufficient_evidence", ...},
          "total_amount":   {"value": "126.43", ...},
          "payment_status": {"value": "unpaid", ...},
          "due_date":       {"value": "2026-09-15", ...},
          "action":         {"value": "pay", ...}
        },
        "contact": {"phone_number": "...", "contact_type": "...", "contact_organization": "..."},
        "ocr": {"element_count": 82, "truncated": false},
        "raw_content": "...",              # untouched OCR coordinate string
        "timing": {"inference_s": 4.1, ...}
      }

    `value` is null wherever the frozen pipeline could not decide. Nothing
    in Phase 3-8 is modified -- this route only imports and calls it.
    """
    if not _PIPELINE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=("Phase 3-8 pipeline modules not importable in this "
                    "process (field_semantics / phone_extract / contact_pick). "
                    "Run the API from the repo so evaluation/"
                    "spatial_field_extraction is on sys.path, or rebuild the "
                    "Docker image with those files copied in."))

    image_bytes, mime = await _read_request_image(request)
    image_bytes, mime = await run_in_threadpool(_coerce_to_image, image_bytes, mime)
    ext = {"image/png": ".png", "image/jpeg": ".jpg",
           "image/jpg": ".jpg"}.get((mime or "").lower(), ".png")

    tf = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tf.write(image_bytes)
        tf.flush()
        tf.close()
        try:
            resp = await run_in_threadpool(call_ocr, tf.name,
                                           base_url=LLAMA_SERVER_URL)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502,
                                detail=f"无法连接本地 Hunyuan 服务: {e}") from e
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass

    content = resp["content"]
    elements = parse_ocr_elements(content)
    usage = resp.get("usage", {})

    try:
        result = await run_in_threadpool(_run_pipeline, elements)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500,
                            detail=f"Phase 3-8 pipeline error: {e}") from e

    return JSONResponse(
        {
            "status": "ok",
            "domain": result["domain"],
            "domain_gap": result["domain_gap"],
            "fields": result["fields"],
            "contact": result["contact"],
            "cross_validation": result["cross_validation"],
            "ocr": {
                "element_count": len(elements),
                "truncated": resp.get("finish_reason") == "length",
            },
            "raw_content": content,
            "timing": {
                "inference_s": resp.get("elapsed_s"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            },
        }
    )


# ---- V0 tester UI (static, no build step) ----------------------------------
# Served from the same process so `uvicorn server.api:app` is the only thing
# to start. Open http://localhost:8091/ui/ . This is a standalone page; it
# shares no code with mama-helper's frontend.
_UI_DIR = os.path.join(_HERE, "..", "webapp")
if os.path.isdir(_UI_DIR):
    from fastapi.responses import RedirectResponse  # noqa: E402
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    app.mount("/ui", StaticFiles(directory=_UI_DIR, html=True), name="ui")

    @app.middleware("http")
    async def _no_cache_ui(request: Request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/ui"):
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp

    @app.get("/")
    async def _root_redirect():
        return RedirectResponse(url="/ui/")
