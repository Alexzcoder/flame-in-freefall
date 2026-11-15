#!/usr/bin/env bash
# Overnight chain (detached): calibration → evaluation with calibrated physics → emulator data + training.
# Each step logs to data/; a failed step stops the chain (set -e). Re-run safe: harvest and real measures resume.
set -euo pipefail
cd "$(dirname "$0")/.."
while pgrep -f "python3 -m flame.calibrate" >/dev/null; do sleep 60; done
while pgrep -f "python3 -m flame.harvest" >/dev/null; do sleep 60; done
echo "$(date +%T) evaluation (calibrated)"
python3 -m flame.shape_eval --theta public/station/simparams.json > data/eval_calibrated.log 2>&1
echo "$(date +%T) emulator"
python3 -m flame.emulator --n 20000 > data/emulator.log 2>&1
echo "$(date +%T) done"
