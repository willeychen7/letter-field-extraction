#!/usr/bin/env bash
# Docker-to-Docker runbook for hunyuan-service.
#
#   image  → hunyuan-service (:8091, published)  → hunyuan-llama (:8090, internal)
#
# The HunyuanOCR llama.cpp container is started separately (it has a
# models/ volume mount and must not be recreated). This script only:
#   1. ensures the shared user-defined network exists
#   2. attaches the running llama container to it as `hunyuan-llama`
#   3. (re)builds and runs hunyuan-service on that network
#
# Usage:  ./docker-run.sh [LLAMA_CONTAINER_NAME]   (default: romantic_meninsky)
set -euo pipefail
export PATH="$HOME/.docker/bin:$PATH"

LLAMA_CTR="${1:-romantic_meninsky}"
NET="hunyuan-net"
cd "$(dirname "$0")"

docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET"

# idempotent attach with a stable alias
if ! docker inspect "$LLAMA_CTR" --format '{{json .NetworkSettings.Networks}}' | grep -q "\"$NET\""; then
  docker network connect --alias hunyuan-llama "$NET" "$LLAMA_CTR"
fi

docker build -t hunyuan-service:local .
docker rm -f hunyuan-service 2>/dev/null || true
docker run -d --name hunyuan-service \
  --network "$NET" \
  -p 8091:8091 \
  -e LLAMA_SERVER_URL=http://hunyuan-llama:8090/v1 \
  --restart unless-stopped \
  hunyuan-service:local

sleep 3
echo "--- health ---"
curl -s -m 10 http://localhost:8091/health; echo
echo "--- connection test (AAA_insurance_Bill.png) ---"
curl -s -m 180 -X POST http://localhost:8091/v1/understand-letter \
  -F "file=@/Users/willeychen/Desktop/mama-helper/demo_image/AAA_insurance_Bill.png;type=image/png" \
  -w "\nHTTP %{http_code}\n" | python3 -m json.tool
