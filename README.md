# Flame in Freefall

**NASA Space Apps Challenge:** *Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data*

Fire behaves differently without gravity: there is no buoyant convection, so flames are spherical, cooler, slower, and can burn
in conditions (low O₂, low flow) where they would go out on Earth. This project mines microgravity combustion experiment
data to pull out fire-safety insights for spacecraft and habitats.

## Dataset

`dataset/flame_runs.json` has 1,632 microgravity combustion runs from 9 NASA PSI investigations (FLEX, CFI, CFI-G, Flame Design, SPICE, BASS-II, SAFFIRE I–III), harmonised into one schema, plus metadata for all 24 combustion investigations.
**See [AGENTS.md](AGENTS.md) for how to load and use it.**

```bash
python3 -m flame.fetch       # raw PSI metadata + run tables → data/raw/ (git-ignored)
python3 -m flame.normalize   # → dataset/flame_runs.json + .csv
```

## Data sources

- NASA Physical Sciences Informatics (PSI): https://psi.nasa.gov/physci/repo/search?q=combustion
- NASA Technical Reports Server: https://ntrs.nasa.gov

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Team

-
