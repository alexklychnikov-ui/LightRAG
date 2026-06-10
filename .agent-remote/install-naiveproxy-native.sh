#!/bin/bash
# Thin wrapper: expects vps bundle in /tmp/vps-bundle (same layout as Empty_ProxyNaive/vps/)
set -euo pipefail
NAIVE_PASS="${1:?usage: install-naiveproxy-native.sh PLAINTEXT_PASSWORD}"
BUNDLE="${2:-/tmp/vps-bundle}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$BUNDLE/deploy.sh" ]; then
  bash "$BUNDLE/deploy.sh" "$NAIVE_PASS" "$BUNDLE"
  exit 0
fi

if [ -f "$SCRIPT_DIR/../Empty_ProxyNaive/vps/deploy.sh" ]; then
  bash "$SCRIPT_DIR/../Empty_ProxyNaive/vps/deploy.sh" "$NAIVE_PASS" "$SCRIPT_DIR/../Empty_ProxyNaive/vps"
  exit 0
fi

echo "ERROR: vps bundle not found. Push Empty_ProxyNaive/vps/ to /tmp/vps-bundle or clone both repos side by side."
exit 1
