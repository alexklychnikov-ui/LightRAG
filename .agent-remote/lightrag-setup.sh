#!/usr/bin/env bash
set -euo pipefail
cd /opt/LightRAG
cp -n config.ini.example config.ini
mkdir -p data/rag_storage data/inputs
LRK="$(openssl rand -hex 24)"
if [ ! -f .env ]; then
  cat > .env <<EOF
HOST=0.0.0.0
PORT=9621
WEBUI_TITLE='LightRAG'
WEBUI_DESCRIPTION='Graph RAG'

# Положи сюда ключ OpenAI или совместимого провайдера (Polza/OpenRouter и т.д.)
OPENAI_API_KEY=

LLM_BINDING=openai
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

# Ключ для вызовов API LightRAG (curl / MCP): заголовок X-API-Key
LIGHTRAG_API_KEY=${LRK}
EOF
  chmod 600 .env
else
  echo ".env already exists, skip writing"
fi
docker compose pull
docker compose up -d
docker compose ps
echo "LIGHTRAG_API_KEY (save this):" "$(grep '^LIGHTRAG_API_KEY=' .env | cut -d= -f2-)"
