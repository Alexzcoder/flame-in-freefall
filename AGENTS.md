# AGENTS.md: working with the Flame in Freefall dataset

Read this first if you are an AI agent (Claude Code, Codex, Cursor…) or a teammate working in this repo.

## What this repo is

NASA Space Apps 2026 challenge **"Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data"**.
We harmonise NASA PSI microgravity combustion run tables into one dataset. The physics engine, the ML models and the chatbot all build on it.

```
dataset/flame_runs.json   ← THE dataset (committed). 1,632 runs, 24 investigations.
dataset/flame_runs.csv    ← same runs, flattened (one row per run, dotted column names)
flame/schema.py           ← data contract: dataclasses + load/save. Read it, it is short.
flame/normalize.py        ← raw PSI tables → dataset (one Normalizer class per table)
flame/fetch.py            ← downloads raw PSI metadata + run tables into data/raw/ (git-ignored)
examples/runs.sample.json ← 6 hand-checked runs, good for unit tests
explorer/                 ← internal web viewer, not part of the product
```

## Load the data

```python
from flame.schema import Dataset

ds = Dataset.from_json("dataset/flame_runs.json")   # typed objects, validates schema_version and keys
run = ds.runs[0]
run.conditions.atmosphere.o2_frac, run.conditions.atmosphere.pressure_kpa, run.outcome.burn_time_s

df = ds.to_frame()                                   # pandas, one row per run
df[df["investigation"] == "PSI-69"]["outcome.burn_time_s"]

inv = {i.id: i for i in ds.investigations}           # metadata: title, objective, hardware, publications
```

No pandas? `json.load(open("dataset/flame_runs.json"))` gives plain dicts with the same shape.

## Shape

```
Dataset { schema_version: "0.1", investigations: [Investigation], runs: [Run] }

Run
  id             "PSI-69/20CAL08"  (= <investigation>/<test id from the source table>)
  investigation  "PSI-69"
  date           ISO date or null
  conditions     inputs, i.e. what you would set up
    fuel         name, phase (solid|liquid|gas), geometry, thickness_mm, width_mm, length_mm,
                 diameter_mm, flow_mg_s, fuel_frac
    atmosphere   o2_frac, n2_frac, he_frac, co2_frac, pressure_kpa, temperature_k
    flow         velocity_cm_s, direction (concurrent|opposed|coflow|quiescent)
    ignition     power_w, duration_s
    gravity_g    0.0 for all current data (ISS / Cygnus)
  outcome        observed result, i.e. what a model should predict
    ignited, result (burnout|extinction|disruption|no_ignition|terminated|other),
    burn_time_s, spread_rate_mm_s, burning_rate_mm2_s, extinction_diameter_mm, flame_length_mm, flame_temperature_k
  media          PSI file names (video/zip/images) for this run; download via flame.fetch.Fetcher.presigned_url
  source         {file, row}: the exact row in the original PSI CSV
  extra          everything source-specific (raw text, Tad/Zst, cool-flame flags, comments)
```

## Rules that matter

- **Units are part of the field name.** Gas amounts are mole fractions (0.21 = air), never %. Pressure is kPa (101.325 = 1 atm; a lunar habitat at 10.2 psi ≈ 70.3 kPa).
- **`null` = unknown, NOT zero.** Never fill nulls with 0 in a model without adding a missing-indicator column. `velocity_cm_s = 0.0` with `direction = "quiescent"` is a real zero (still air).
- **Inverse flames** (`extra.flame_type == "inverse"`, in PSI-10 and PSI-159): oxygen flows *out of* the burner into a fuel atmosphere. There, `atmosphere.o2_frac` is the O₂ fraction of the burner stream and `fuel.fuel_frac` is the ambient fuel fraction.
- **FLEX `burning_rate_mm2_s`** comes from a column labelled "Burning rate; mm"; we read it as the d²-law constant K.
- **SPICE `extra.flame_on_s`** is operator-controlled, not a natural burn time, so it is not in `outcome`.
- Don't edit `dataset/` by hand. Fix the matching `Normalizer` in `flame/normalize.py`, then run `python3 -m flame.normalize`.
- Changing the schema = edit `flame/schema.py`, bump `SCHEMA_VERSION`, regenerate, and tell the team (the physics engine depends on it).

## What is in it (coverage)

| Investigation | Family | Runs | Has conditions | Has outcomes |
|---|---|---|---|---|
| PSI-69 FLEX | droplet | 274 | fuel, d₀, O₂/N₂/CO₂/He, pressure | **ignited, result, burn time, burning rate K, extinction d** |
| PSI-39 CFI | droplet | 87 | blend, O₂/N₂/He, pressure | none in table |
| PSI-159 CFI-G | gaseous | 333 | fuel, fuel frac, flow, O₂, pressure | **ignited, result, burn time**; cool flame in `extra` |
| PSI-10 Flame Design | gaseous | 327 | fuel, flows, O₂, pressure; Tad/Zst in `extra` | none in table |
| PSI-107 SPICE | gaseous jet | 469 | fuel, nozzle, fuel flow, co-flow air speed | none (smoke point is in reports) |
| PSI-25 BASS-II | solid | 129 | material, geometry, O₂, CO₂ | none; flow needs fan calibration |
| PSI-98/99/100 SAFFIRE I–III | solid (large scale, Cygnus) | 13 | material, size, flow, O₂, igniter | burn time, spread (partial) |

**Trainable today: FLEX (274) and CFI-G (333).** These are the only tables with outcomes.
The other 15 investigations are in `ds.investigations` with `normalized: false` and a `note` explaining why (test-day rows, ranges, smoke aging, modelling-only…).

Splitting for ML: group by test day (`extra.day` for ACME, `date` for FLEX) so runs from one session don't land in both train and test.

## Physics engine contract

```python
def predict(c: Conditions) -> Outcome: ...
# validate against reality:
for run in ds.runs:
    if run.outcome.burn_time_s is not None:
        err = predict(run.conditions).burn_time_s - run.outcome.burn_time_s
```
Use `examples/runs.sample.json` for fast tests. Swap in `dataset/flame_runs.json` without changing code.

## Regenerate from scratch

```bash
python3 -m flame.fetch       # ~22 MB of metadata + run tables from psi.nasa.gov → data/raw/
python3 -m flame.normalize   # → dataset/flame_runs.json + .csv, then runs sanity checks (counts, ranges, round trip)
python3 -m flame.schema      # schema self-check on the sample file
```
