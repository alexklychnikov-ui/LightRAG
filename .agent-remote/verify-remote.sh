#!/usr/bin/env bash
set -euo pipefail
ENV=/opt/LightRAG/.env
APIK=$(grep '^LIGHTRAG_API_KEY=' "$ENV" | cut -d= -f2-)
OA=$(grep '^OPENAI_API_KEY=' "$ENV" | cut -d= -f2-)

echo "openai_len=${#OA}"
echo "lr_key_len=${#APIK}"
curl -fsS -m 10 http://127.0.0.1:9621/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print("health", d["status"], "auth", d.get("auth_mode"))'

hs=$(curl -sS -m 15 -o /tmp/scan.out -w '%{http_code}' -X POST -H "X-API-Key: ${APIK}" http://127.0.0.1:9621/documents/scan || echo 000)
echo "scan_http=${hs}"
head -c 120 /tmp/scan.out 2>/dev/null || true
echo

oh=$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${OA}" https://api.openai.com/v1/models || echo 000)
echo "openai_http=${oh}"
