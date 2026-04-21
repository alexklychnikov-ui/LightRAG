#!/usr/bin/env bash
set -euo pipefail
cd /opt/LightRAG
if grep -q '^TOKEN_SECRET=' .env 2>/dev/null; then
  echo "TOKEN_SECRET: already present"
else
  echo "TOKEN_SECRET=$(openssl rand -hex 32)" >> .env
  chmod 600 .env
  echo "TOKEN_SECRET: added"
fi
docker compose up -d
docker compose restart lightrag
