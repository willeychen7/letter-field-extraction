FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx python-multipart \
    pypdfium2 pillow

COPY server/api.py /app/server/api.py
COPY schemas/mama_helper_v1.py /app/schemas/mama_helper_v1.py
# frozen Phase 3-8 modules, imported and CALLED verbatim by /v1/ocr and
# /v1/analyze -- never modified in this image.
COPY evaluation/spatial_field_extraction/ocr.py /app/ocr.py
COPY evaluation/spatial_field_extraction/spatial.py /app/spatial.py
COPY evaluation/spatial_field_extraction/anchors.py /app/anchors.py
COPY evaluation/spatial_field_extraction/structure.py /app/structure.py
COPY evaluation/spatial_field_extraction/extract.py /app/extract.py
COPY evaluation/spatial_field_extraction/domain.py /app/domain.py
COPY evaluation/spatial_field_extraction/field_semantics.py /app/field_semantics.py
COPY evaluation/spatial_field_extraction/phone_extract.py /app/phone_extract.py
COPY evaluation/spatial_field_extraction/contact_pick.py /app/contact_pick.py
# V0 tester UI (static, served at /ui/)
COPY webapp/ /app/webapp/

EXPOSE 8091

# Upstream llama.cpp server. Docker-to-Docker default: the HunyuanOCR
# container, reachable by network alias on a shared user-defined network.
# Override with -e LLAMA_SERVER_URL=... (e.g. http://host.docker.internal:8090/v1
# to reach a llama-server running on the host instead).
ENV LLAMA_SERVER_URL=http://hunyuan-llama:8090/v1

CMD ["python", "-m", "uvicorn", "server.api:app", "--host", "0.0.0.0", "--port", "8091"]
