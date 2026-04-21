#!/usr/bin/env bash
set -euo pipefail
ENV=/opt/LightRAG/.env
if [[ ! -f "$ENV" ]]; then echo "FAIL: no $ENV"; exit 1; fi
set -a
# shellcheck disable=SC1090
source "$ENV"
set +a

fail=0

# --- OpenAI ---
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY: EMPTY"
  fail=1
else
  http=$(curl -sS -o /tmp/oa.json -w '%{http_code}' \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    https://api.openai.com/v1/models \
    --connect-timeout 15 --max-time 45) || true
  if [[ "$http" == "200" ]]; then
    echo "OPENAI_API_KEY: OK (GET /v1/models -> 200)"
  elif [[ "$http" == "401" ]]; then
    echo "OPENAI_API_KEY: BAD (HTTP 401)"
    fail=1
  elif [[ "$http" == "403" ]]; then
    echo "OPENAI_API_KEY: FORBIDDEN (HTTP 403)"
    fail=1
  else
    echo "OPENAI_API_KEY: HTTP $http"
    fail=1
  fi
fi

# --- LightRAG X-API-Key ---
if [[ -z "${LIGHTRAG_API_KEY:-}" ]]; then
  echo "LIGHTRAG_API_KEY: EMPTY"
  fail=1
else
  hs=$(curl -sS -o /tmp/scan.json -w '%{http_code}' -X POST \
    -H "X-API-Key: ${LIGHTRAG_API_KEY}" \
    http://127.0.0.1:9621/documents/scan \
    --connect-timeout 15 --max-time 45) || true
  if [[ "$hs" == "200" ]] || [[ "$hs" == "409" ]]; then
    echo "LIGHTRAG_API_KEY: OK (POST /documents/scan -> HTTP $hs)"
  elif [[ "$hs" == "401" ]] || [[ "$hs" == "403" ]]; then
    echo "LIGHTRAG_API_KEY: REJECTED (HTTP $hs)"
    fail=1
  else
    echo "LIGHTRAG_API_KEY: unexpected HTTP $hs"
    fail=1
  fi
fi

# --- Real LLM + embedding (only if OpenAI models HTTP 200) ---
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  exit "$fail"
fi
http_models=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  https://api.openai.com/v1/models \
  --connect-timeout 15 --max-time 45) || true
if [[ "$http_models" != "200" ]]; then
  exit "$fail"
fi

body='{"model":"gpt-4o-mini","messages":[{"role":"user","content":"ping"}],"max_tokens":4}'
hc=$(curl -sS -o /tmp/chat.json -w '%{http_code}' \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$body" \
  https://api.openai.com/v1/chat/completions \
  --connect-timeout 25 --max-time 90) || true
if [[ "$hc" == "200" ]]; then
  echo "OpenAI chat gpt-4o-mini: OK"
else
  echo "OpenAI chat gpt-4o-mini: FAIL HTTP $hc"
  fail=1
fi

emb='{"model":"text-embedding-3-small","input":"ok"}'
he=$(curl -sS -o /tmp/emb.json -w '%{http_code}' \
  -H "Authorization: Bearer ${OPENAI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$emb" \
  https://api.openai.com/v1/embeddings \
  --connect-timeout 25 --max-time 90) || true
if [[ "$he" == "200" ]]; then
  echo "OpenAI embedding text-embedding-3-small: OK"
else
  echo "OpenAI embedding: FAIL HTTP $he"
  fail=1
fi

exit "$fail"
