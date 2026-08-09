#!/usr/bin/env bash
set -euo pipefail
cd /opt/LightRAG

ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${1:-$(openssl rand -base64 18 | tr -d '=+/' | cut -c1-16)}"
HASH_LINE="$(docker exec rag lightrag-hash-password --username "$ADMIN_USER" "$ADMIN_PASS")"

if grep -q '^AUTH_ACCOUNTS=' .env; then
  sed -i "s|^AUTH_ACCOUNTS=.*|AUTH_ACCOUNTS='${HASH_LINE}'|" .env
else
  printf "AUTH_ACCOUNTS='%s'\n" "$HASH_LINE" >> .env
fi

if ! grep -q '^TOKEN_EXPIRE_HOURS=' .env; then
  echo 'TOKEN_EXPIRE_HOURS=48' >> .env
fi

chmod 600 .env

if docker compose -f docker-compose.yml config --services 2>/dev/null | grep -qx lightrag; then
  SVC=lightrag
else
  SVC=rag
fi

docker compose -f docker-compose.yml up -d --force-recreate "$SVC"
sleep 5

AUTH_JSON="$(curl -fsS http://127.0.0.1:9621/auth-status)"
python3 - <<PY
import json, os
d = json.loads("""$AUTH_JSON""")
print("auth_mode=", d.get("auth_mode"))
print("auth_configured=", d.get("auth_configured"))
PY

echo "ADMIN_USER=$ADMIN_USER"
echo "ADMIN_PASS=$ADMIN_PASS"
