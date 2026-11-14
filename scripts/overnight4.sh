#!/usr/bin/env bash
# Restarted chain (2026-11-14 23:05): emulator (tuned physics for solids only) → insights → spread fit → risk.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "$(date +%T) emulator"; python3 -m flame.emulator --n 20000 > data/emulator.log 2>&1
echo "$(date +%T) insights"; python3 -m flame.insights > data/insights.log 2>&1
node public/station/emulator.test.mjs >> data/insights.log 2>&1 || true
echo "$(date +%T) spread"; python3 -m flame.spread --gens 20 --pop 32 > data/spread.log 2>&1
echo "$(date +%T) risk"; python3 -m flame.risk > data/risk.log 2>&1
echo "$(date +%T) done"
