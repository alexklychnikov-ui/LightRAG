#!/usr/bin/env bash
set -euo pipefail

REMOTE_DIR="/opt/LightRAG"
BACKUP_ROOT="/opt/_backup-lightrag-before-restore"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${STAMP}"

echo "[restore] backup dir: ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

OPENAI_KEY=""
LR_KEY=""
DOMAIN="alexklyvibe.ru"
if [[ -f "${REMOTE_DIR}/.env.secrets.json" ]]; then
  OPENAI_KEY="$(jq -r '.LLM_BINDING_API_KEY // empty' "${REMOTE_DIR}/.env.secrets.json")"
fi
if [[ -f "${REMOTE_DIR}/.env" ]]; then
  LR_KEY="$(grep '^LIGHTRAG_API_KEY=' "${REMOTE_DIR}/.env" | head -n1 | cut -d= -f2- | tr -d '"')"
  DOMAIN="$(grep '^PUBLISH_DOMAIN=' "${REMOTE_DIR}/.env" | head -n1 | cut -d= -f2- | tr -d '"' || true)"
fi
[[ -n "${DOMAIN}" ]] || DOMAIN="alexklyvibe.ru"
[[ -n "${LR_KEY}" ]] || LR_KEY="$(openssl rand -hex 24)"
[[ -n "${OPENAI_KEY}" ]] || echo "[restore] WARN: OPENAI_API_KEY not found in backup secrets"

echo "[restore] stopping old stack"
if [[ -f "${REMOTE_DIR}/docker-compose.yaml" ]]; then
  (cd "${REMOTE_DIR}" && docker compose -f docker-compose.yaml down) || true
elif [[ -f "${REMOTE_DIR}/docker-compose.yml" ]]; then
  (cd "${REMOTE_DIR}" && docker compose down) || true
fi

echo "[restore] moving ${REMOTE_DIR} -> ${BACKUP_DIR}"
mv "${REMOTE_DIR}" "${BACKUP_DIR}/LightRAG-oleks"

echo "[restore] cloning HKUDS/LightRAG"
git clone --depth 1 https://github.com/HKUDS/LightRAG.git "${REMOTE_DIR}"
cd "${REMOTE_DIR}"

cp -n config.ini.example config.ini
mkdir -p data/rag_storage data/inputs data/postgres/init data/postgres/data
echo 'CREATE EXTENSION IF NOT EXISTS vector;' > data/postgres/init/01-init.sql

cp /tmp/lightrag-restore/docker-compose.restore-vps.yml docker-compose.yml
cp /tmp/lightrag-restore/docker-compose.telegram-bot.yml docker-compose.telegram-bot.yml
cp -r /tmp/lightrag-restore/telegram_bot ./
cp /tmp/lightrag-restore/lightrag_mcp_server.py ./

POSTGRES_PASSWORD="$(openssl rand -hex 16)"
TOKEN_SECRET="$(openssl rand -hex 32)"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_BOT_CHATID=""
BOT_ALLOWED_USER_IDS=""
if [[ -f "${BACKUP_DIR}/LightRAG-oleks/.env.telegram.bak" ]]; then
  # optional manual backup placed by operator
  source "${BACKUP_DIR}/LightRAG-oleks/.env.telegram.bak"
fi

cat > .env <<EOF
HOST=0.0.0.0
PORT=9621
WEBUI_TITLE=LightRAG
WEBUI_DESCRIPTION=Graph RAG
CORS_ORIGINS=https://lightrag.${DOMAIN}

OPENAI_API_KEY=${OPENAI_KEY}
LLM_BINDING=openai
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

LIGHTRAG_API_KEY=${LR_KEY}
TOKEN_SECRET=${TOKEN_SECRET}

SUMMARY_LANGUAGE=Russian
CHUNK_SIZE=1200
CHUNK_OVERLAP_SIZE=120
TOP_K=50
COSINE_THRESHOLD=0.25
ENABLE_LLM_CACHE=true
ENABLE_LLM_CACHE_FOR_EXTRACT=true
MAX_ASYNC=4
MAX_PARALLEL_INSERT=2
EMBEDDING_FUNC_MAX_ASYNC=8
EMBEDDING_BATCH_NUM=10
MAX_GRAPH_NODES=1500
RELATED_CHUNK_NUMBER=8
KG_CHUNK_PICK_METHOD=VECTOR

LIGHTRAG_KV_STORAGE=PGKVStorage
LIGHTRAG_DOC_STATUS_STORAGE=PGDocStatusStorage
LIGHTRAG_VECTOR_STORAGE=PGVectorStorage
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=lightrag
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DATABASE=lightrag
POSTGRES_MAX_CONNECTIONS=25
POSTGRES_VECTOR_INDEX_TYPE=HNSW
POSTGRES_HNSW_M=16
POSTGRES_HNSW_EF=200

TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_BOT_CHATID=${TELEGRAM_BOT_CHATID}
BOT_ALLOWED_USER_IDS=${BOT_ALLOWED_USER_IDS}
BOT_ACCESS_CONTROL_REQUIRED=true
BOT_DENY_GROUP_CHATS=true
LIGHTRAG_URL=http://lightrag:9621

BOT_ENABLE_DEEP_QA=true
BOT_ENABLE_WEB_SEARCH=true
BOT_ENABLE_OPENAI_FALLBACK=true
BOT_TRANSLATE_TO_RU=true
BOT_QUERY_MODE=mix
BOT_OPENAI_MODEL=o4-mini
BOT_ENABLE_ANSWER_COMPLETENESS_JUDGE=true
TAVILY_API_KEY=

EOF
chmod 600 .env

docker network inspect lightrag_frontend >/dev/null 2>&1 || docker network create lightrag_frontend

echo "[restore] starting LightRAG + Postgres"
docker compose pull
docker compose up -d

for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:9621/health >/dev/null 2>&1; then
    echo "[restore] health OK"
    break
  fi
  sleep 3
done
curl -fsS http://127.0.0.1:9621/health || { echo "[restore] health FAILED"; exit 1; }

if [[ -n "${TELEGRAM_BOT_TOKEN}" ]]; then
  echo "[restore] starting telegram-bot"
  docker compose -f docker-compose.yml -f docker-compose.telegram-bot.yml up -d --build --force-recreate telegram-bot
else
  echo "[restore] SKIP telegram-bot: TELEGRAM_BOT_TOKEN empty — add to .env and redeploy"
fi

if [[ ! -d /opt/lightrag-mcp-venv ]]; then
  apt-get update -qq
  apt-get install -y -qq python3.12-venv
  python3.12 -m venv /opt/lightrag-mcp-venv
  /opt/lightrag-mcp-venv/bin/pip install -q mcp requests
fi

echo "[restore] done. backup: ${BACKUP_DIR}"
echo "[restore] LIGHTRAG_API_KEY saved in ${REMOTE_DIR}/.env"
