#!/usr/bin/env bash
set -euo pipefail
APIK=$(grep '^LIGHTRAG_API_KEY=' /opt/LightRAG/.env | cut -d= -f2-)
H=(-H "X-API-Key: ${APIK}" -H "Content-Type: application/json")

echo "=== bot-style payload ==="
curl -sS -m 30 -X POST "${H[@]}" \
  -d '{"text":"bot style test","description":"smoke"}' \
  http://127.0.0.1:9621/documents/text
echo

echo "=== with file_source ==="
curl -sS -m 30 -X POST "${H[@]}" \
  -d '{"text":"with source test","file_source":"telegram-smoke-test"}' \
  http://127.0.0.1:9621/documents/text
echo

echo "=== bot container ingest (fixed client) ==="
docker exec lightrag-telegram-bot python3 -c "
import os, requests
u = os.environ['LIGHTRAG_URL'].rstrip('/')
k = os.environ.get('LIGHTRAG_API_KEY', '')
h = {'X-API-Key': k} if k else {}
r = requests.get(f'{u}/health', headers=h, timeout=15)
print('health', r.status_code, r.json().get('status'))
payload = {'text': 'from bot container fixed', 'file_source': 'telegram:smoke', 'description': 'telegram:smoke'}
r2 = requests.post(f'{u}/documents/text', headers={**h, 'Content-Type': 'application/json'}, json=payload, timeout=30)
print('ingest', r2.status_code, r2.text[:200])
"
