# Flame in Freefall

**NASA Space Apps Challenge:** *Flame in Freefall: AI-Powered Fire Safety Insights from Microgravity Combustion Data*

Fire behaves differently without gravity: there is no buoyant convection, so flames are spherical, cooler, slower, and can burn
in conditions (low O₂, low flow) where they would go out on Earth. This project mines microgravity combustion experiment
data to pull out fire-safety insights for spacecraft and habitats.

## Data sources

- NASA Physical Sciences Informatics (PSI): https://psi.nasa.gov — ISS combustion experiments (FLEX, FLEX-2, BASS, ACME, SoFIE, CFI)
- NASA Open Data Portal: https://data.nasa.gov

Raw data goes in `data/` (git-ignored).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab
```

## Team

-
