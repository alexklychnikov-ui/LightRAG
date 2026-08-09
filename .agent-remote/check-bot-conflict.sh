#!/bin/bash
set -euo pipefail
ENV_FILE=/opt/LightRAG/.env
TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d "\"'")
echo "=== getWebhookInfo ==="
curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
echo
echo "=== getMe ==="
curl -s "https://api.telegram.org/bot${TOKEN}/getMe"
echo
echo "=== containers ==="
docker ps -a --format '{{.Names}} {{.Status}}' | grep -iE 'bot|telegram|rag' || true
echo "=== host python telegram ==="
ps aux | grep -E 'telegram_bot|aiogram' | grep -v grep || true
echo "=== bot logs last 30 ==="
docker logs lightrag-telegram-bot --tail 30 2>&1
