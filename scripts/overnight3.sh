#!/usr/bin/env bash
# After scripts/overnight2.sh: fit the spread knobs (needs the final tau), then the habitat risk model.
set -euo pipefail
cd "$(dirname "$0")/.."
while pgrep -f "^bash scripts/overnight2?.sh" >/dev/null; do sleep 60; done
echo "$(date +%T) spread"
python3 -m flame.spread --gens 20 --pop 32 > data/spread.log 2>&1
echo "$(date +%T) risk"
python3 -m flame.risk > data/risk.log 2>&1
echo "$(date +%T) done"
