# Flame models: simulation, evaluation against NASA video, outcome models, emulator

Goal: predict how a small fire behaves for any cabin condition (gravity, oxygen, pressure, airflow, fuel), say how
sure we are, and turn that into fire-safety insights for the 3D habitats. Every step is checked against NASA runs.

```
NASA video (PSI) ──harvest.py──▶ data/frames/<run>.npz ──shape.py──▶ real flame measures ─┐
                                                                                          ├─▶ shape_eval.py ─▶ dataset/shape_eval.md
run conditions ──sim.py (GPU)──▶ simulated camera frames ──shape.py──▶ sim flame measures ┘
                         ▲
run outcomes ───calibrate.py (fits sim knobs) ──▶ public/station/simparams.json ──▶ website flame lab (flamelab.js)
                         │
                         └──▶ emulator.py: 20k sims → small neural network ──▶ public/models/flame_emulator.json (emulator.js)
run outcomes ───predict.py (gradient boosting, grouped CV) ──▶ dataset/predict_eval.md
calibrated sim ──insights.py ──▶ public/station/insights.json ──▶ 3D habitat panel (station/inside.html)
```

| File | What it does |
|---|---|
| `flame/sim.py` | PyTorch port of the website simulation (`public/station/flamelab.js`), batched on the GPU. Knobs in `THETA`. |
| `flame/shape.py` | Flame measures from any frames: aspect (stretch), fill, hollow (ring), blue share, flicker, alive/extinguished. Ratios only: NASA cameras have no scale. |
| `flame/harvest.py` | Downloads each run's NASA video, finds the burn, keeps the burn frames (≈4 MB/run), deletes the video. Resumable. |
| `flame/shape_eval.py` | Simulates every harvested run at its conditions and compares measures (Spearman ρ per family) + CFI-G outcomes. |
| `flame/calibrate.py` | Cross-entropy search over 14 knobs: CFI-G time to extinction (331 runs), BASS-II aspect, solid fate (BASS-II went out / SAFFIRE kept burning). Test days held out. |
| `flame/predict.py` | Data-only models: CFI-G outcome + extinction time, FLEX outcome, burning rate, extinction size. 80 % intervals (conformal). |
| `flame/emulator.py` | Neural-network copy of the calibrated simulation (image + shape + fate), ensemble of 3 for uncertainty, exported for the browser. |
| `flame/insights.py` | Per habitat object: fans on/off fate, lowest oxygen that keeps it burning, how visible the flame is. |

## Run it

```bash
python3 -m flame.harvest --workers 6     # NASA video → frames (BASS-II, CFI, CFI-G; ~90 GB streamed, ~2 GB kept)
python3 -m flame.calibrate --gens 40     # ~3 h on an RTX-class GPU → public/station/simparams.json
python3 -m flame.shape_eval --theta public/station/simparams.json   # → dataset/shape_eval.md
python3 -m flame.predict                 # ~30 s CPU → dataset/predict_eval.md
python3 -m flame.emulator --n 20000      # ~30 min → public/models/flame_emulator.json
python3 -m flame.insights                # → public/station/insights.json
node public/station/emulator.test.mjs    # browser emulator == Python
```
`scripts/overnight.sh` chains calibration → evaluation → emulator → insights.

## What to trust

- The simulation is 2D, small and fast. Fit for trends and "does it go out", not for millimetres or seconds.
  `dataset/shape_eval.md` reports how well each measure tracks reality; use only the ones with clear positive ρ.
- The outcome models (`predict.py`) are the most accurate numbers we have for gas flames and droplets, inside the
  tested conditions. Each prediction says `in_range`; outside it is an extrapolation.
- The emulator copies the simulation, errors included. Its ensemble spread flags where it is unsure of *the
  simulation*, not of reality.
- Every NASA run is microgravity: nothing here is checked against Moon or Earth gravity data.
