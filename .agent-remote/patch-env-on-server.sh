#!/usr/bin/env bash
set -euo pipefail
ENV=/opt/LightRAG/.env
PATCH=/tmp/env-secrets.patch

if [[ ! -f "$PATCH" ]]; then
  echo "missing $PATCH"
  exit 1
fi

# shellcheck disable=SC1090
source "$PATCH"

python3 <<'PY'
from pathlib import Path

env_path = Path("/opt/LightRAG/.env")
lines = env_path.read_text().splitlines()
patch = {}
for raw in Path("/tmp/env-secrets.patch").read_text().splitlines():
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    k, v = raw.split("=", 1)
    patch[k.strip()] = v.strip()

out = []
seen = set()
for line in lines:
    if "=" not in line or line.strip().startswith("#"):
        out.append(line)
        continue
    key = line.split("=", 1)[0]
    if key in patch and patch[key]:
        out.append(f"{key}={patch[key]}")
        seen.add(key)
    else:
        if key == "WEBUI_DESCRIPTION":
            out.append('WEBUI_DESCRIPTION="Graph RAG"')
        else:
            out.append(line)
        seen.add(key)

for key, val in patch.items():
    if key not in seen and val:
        out.append(f"{key}={val}")

env_path.write_text("\n".join(out) + "\n")
PY

chmod 600 "$ENV"
cd /opt/LightRAG
docker compose up -d --force-recreate lightrag

APIK=$(grep '^LIGHTRAG_API_KEY=' "$ENV" | cut -d= -f2-)
OA=$(grep '^OPENAI_API_KEY=' "$ENV" | cut -d= -f2-)
echo "openai_len=${#OA}"
echo "lr_key_len=${#APIK}"

hs=$(curl -sS -o /tmp/scan.out -w '%{http_code}' -X POST -H "X-API-Key: ${APIK}" http://127.0.0.1:9621/documents/scan || true)
echo "scan_http=${hs}"

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  docker compose -f docker-compose.yml -f docker-compose.telegram-bot.yml up -d --build --force-recreate telegram-bot
  echo "telegram-bot started"
else
  echo "telegram-bot skipped: no token"
fi
