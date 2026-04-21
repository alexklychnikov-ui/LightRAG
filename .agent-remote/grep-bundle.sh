#!/usr/bin/env bash
curl -sS http://127.0.0.1:9621/webui/assets/index-zoBd8VvX.js -o /tmp/bundle.js
grep -oE "window\.location\.origin[^;]{0,120}" /tmp/bundle.js | head -5
strings /tmp/bundle.js | grep -F "9621" | head -20
strings /tmp/bundle.js | grep -iE "apiprefix|api_url|baseurl|/api/" | head -30
