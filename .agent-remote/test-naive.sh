#!/usr/bin/env bash
set -euo pipefail
cd /opt/naive-proxy
NAIVE_USER=naiveuser
NAIVE_PASS="${NAIVE_PASS:?set NAIVE_PASS env}"

echo "=== local HTTPS sites ==="
curl -sS -m 10 -o /dev/null -w 'alexklyvibe.ru %{http_code}\n' https://alexklyvibe.ru/
curl -sS -m 10 -o /dev/null -w 'lightrag health %{http_code}\n' https://lightrag.alexklyvibe.ru/health

echo "=== forward proxy CONNECT (naiveuser) ==="
code=$(curl -sS -m 25 -o /tmp/naive_proxy.out -w '%{http_code}' \
  -x "https://${NAIVE_USER}:${NAIVE_PASS}@127.0.0.1:443" \
  --resolve alexklyvibe.ru:443:127.0.0.1 \
  https://example.com/ || echo 000)
echo "proxy_example_http=${code}"
head -c 120 /tmp/naive_proxy.out 2>/dev/null || true
echo

echo "=== forward proxy without auth (expect 407) ==="
code2=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' \
  -x https://127.0.0.1:443 \
  --resolve alexklyvibe.ru:443:127.0.0.1 \
  https://example.com/ || echo 000)
echo "proxy_noauth_http=${code2}"

echo "=== proxy ip check ==="
code3=$(curl -sS -m 25 -o /tmp/naive_ip.out -w '%{http_code}' \
  -x "https://${NAIVE_USER}:${NAIVE_PASS}@127.0.0.1:443" \
  --resolve alexklyvibe.ru:443:127.0.0.1 \
  https://api.ipify.org?format=json || echo 000)
echo "ipify_http=${code3}"
cat /tmp/naive_ip.out 2>/dev/null || true
echo

echo "=== caddy certs in data ==="
ls -la /opt/naive-proxy/data/caddy/certificates 2>/dev/null | head -5 || ls -la /opt/naive-proxy/data/ | head -10

echo "=== old naiveproxy path ==="
ls -la /opt/naiveproxy 2>/dev/null || echo "no /opt/naiveproxy"
