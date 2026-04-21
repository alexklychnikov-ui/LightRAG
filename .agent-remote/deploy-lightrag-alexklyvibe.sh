#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
systemctl start docker || true
if [[ ! -d /opt/LightRAG/.git ]]; then
  rm -rf /opt/LightRAG
  git clone --depth 1 https://github.com/HKUDS/LightRAG.git /opt/LightRAG
fi
cd /opt/LightRAG
cp -n config.ini.example config.ini
mkdir -p data/rag_storage data/inputs
