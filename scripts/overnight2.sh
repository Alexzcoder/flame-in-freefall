#!/usr/bin/env bash
# After scripts/overnight.sh: habitat insights with the calibrated physics.
set -euo pipefail
cd "$(dirname "$0")/.."
while pgrep -f "^bash scripts/overnight.sh" >/dev/null; do sleep 60; done
echo "$(date +%T) insights"
python3 -m flame.insights > data/insights.log 2>&1
node public/station/emulator.test.mjs >> data/insights.log 2>&1 || true
echo "$(date +%T) done"
