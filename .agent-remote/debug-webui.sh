#!/usr/bin/env bash
set -euo pipefail
JS=$(curl -sS http://127.0.0.1:9621/webui/index.html | sed -n 's/.*src="\([^"]*\.js\)".*/\1/p' | head -1)
echo "js_path=$JS"
curl -sS -o /dev/null -w "js_http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:9621${JS}"
# sample strings from bundle
curl -sS "http://127.0.0.1:9621${JS}" | tr '"' '\n' | grep -E '^https?://' | sort -u | head -30
