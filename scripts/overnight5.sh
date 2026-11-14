#!/usr/bin/env bash
# 2026-11-14 23:30: longer spread fit (wider ranges) → risk → insights (corrected check) → leave-one-out checks.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "$(date +%T) spread"; python3 -m flame.spread --gens 50 --pop 48 > data/spread.log 2>&1
echo "$(date +%T) risk"; python3 -m flame.risk > data/risk.log 2>&1
echo "$(date +%T) insights"; python3 -m flame.insights > data/insights.log 2>&1
echo "$(date +%T) loo"; python3 -m flame.loo > data/loo.log 2>&1
echo "$(date +%T) done"
