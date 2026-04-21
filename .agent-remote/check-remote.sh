#!/bin/bash
set -euo pipefail
LINE=$(grep '^OPENAI_API_KEY=' /opt/LightRAG/.env || true)
VAL=${LINE#OPENAI_API_KEY=}
VAL=${VAL//\"/}
VAL=${VAL//\'/}
echo "openai_key_length=${#VAL}"
APIK=$(grep '^LIGHTRAG_API_KEY=' /opt/LightRAG/.env | cut -d= -f2-)
CODE=$(curl -sS -o /tmp/hr -w '%{http_code}' -H "X-API-Key: ${APIK}" http://127.0.0.1:9621/documents/paginated?page=1 || echo fail)
echo "documents_endpoint_http=${CODE}"
