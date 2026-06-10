#!/usr/bin/env bash
set -euo pipefail
ENV=/opt/LightRAG/.env
APIK=$(grep '^LIGHTRAG_API_KEY=' "$ENV" | cut -d= -f2-)

echo "=== ingest text ==="
ingest=$(curl -sS -m 60 -X POST \
  -H "X-API-Key: ${APIK}" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Smoke test LightRAG migration $(date -u +%s). LightRAG хранит знания в PostgreSQL.\",\"description\":\"smoke-test\"}" \
  http://127.0.0.1:9621/documents/text)
echo "$ingest" | head -c 300
echo

echo "=== query mix (indexed doc) ==="
sleep 10
query=$(curl -sS -m 120 -X POST \
  -H "X-API-Key: ${APIK}" \
  -H "Content-Type: application/json" \
  -d '{"query":"from bot container fixed","mode":"mix"}' \
  http://127.0.0.1:9621/query)
echo "$query" | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("response") or d.get("answer") or str(d)[:200]; print("answer_len", len(r)); print(r[:400])'

echo "=== bot container env ==="
docker exec lightrag-telegram-bot printenv BOT_ENABLE_WEB_SEARCH BOT_ENABLE_DEEP_QA LIGHTRAG_URL | sort
TAVILY_LEN=$(docker exec lightrag-telegram-bot printenv TAVILY_API_KEY 2>/dev/null | wc -c)
echo "TAVILY_API_KEY container_len=$((TAVILY_LEN-1))"

echo "=== MCP venv ==="
/opt/lightrag-mcp-venv/bin/python -c 'import mcp, requests; print("mcp_ok")'
