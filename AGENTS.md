# AGENTS.md: working with the Flame in Freefall dataset

Read this first if you are an AI agent (Claude Code, Codex, Cursor…) or a teammate working in this repo.

## What this repo is

NASA Space Apps 2026 challenge **"Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data"**.
We harmonise NASA PSI microgravity combustion run tables into one dataset. The physics engine, the ML models and the chatbot all build on it.

```
dataset/flame_runs.json   ← THE dataset (committed). 1,624 runs (633 with outcomes), 24 investigations.
dataset/coverage.md       ← auto-generated: what each investigation can be used for. Read before modelling.
dataset/publications.json ← 299 papers linked to investigations; 141 with abstract (title/venue/year/DOI for all)
dataset/documents.jsonl   ← search corpus: 24 objectives + 299 papers + 1,559 NASA report pages, each with a citation
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
Dataset { schema_version: "0.2", investigations: [Investigation], runs: [Run] }

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
    o2_location  "ambient" | "burner_stream" (inverse flames, see below)
  outcome        observed result, i.e. what a model should predict
    ignited, result (burnout|extinction|disruption|no_ignition|terminated|other),
    censored (True = burn_time_s is a lower bound: operator stopped it or the droplet disrupted),
    burn_time_s, spread_rate_mm_s, burning_rate_mm2_s, extinction_diameter_mm, flame_length_mm, flame_temperature_k
  has_outcome    True if any outcome field is observed → usable as a training label
  assumed        field paths filled by assumption, e.g. ["conditions.atmosphere.pressure_kpa"] (cabin air)
  media          PSI file names (video/zip/images) for this run; download via flame.fetch.Fetcher.presigned_url
  source         {file, row}: the exact row in the original PSI CSV
  extra          everything source-specific (raw text, Tad/Zst, cool-flame flags, comments)
```

## Rules that matter

- **Units are part of the field name.** Gas amounts are mole fractions (0.21 = air), never %. Pressure is kPa (101.325 = 1 atm; a lunar habitat at 10.2 psi ≈ 70.3 kPa).
- **`null` = unknown, NOT zero.** Never fill nulls with 0 in a model without adding a missing-indicator column. `velocity_cm_s = 0.0` with `direction = "quiescent"` is a real zero (still air).
- **Inverse flames** (`conditions.o2_location == "burner_stream"`, 274 runs in PSI-10 and PSI-159): oxygen flows *out of* the burner into a fuel atmosphere. There, `atmosphere.o2_frac` is the O₂ fraction of the burner stream and `fuel.fuel_frac` is the ambient fuel fraction. **Filter them out** (`o2_location == "ambient"`) before plotting or ranking by O₂.
- **Censored burn times:** `outcome.censored == True` (FLEX disruption 61, CFI-G flow-terminated 88) means the flame was still burning when the run ended. Drop these, or use a survival/Tobit-style model, when burn time is the target. Never treat them as extinction times.
- **Assumed values:** SPICE, BASS-II and SAFFIRE tables don't record pressure (and SPICE/SAFFIRE-III not O₂). They ran in ISS-glovebox or Cygnus cabin air, so we fill 101.325 kPa / 0.21 and list the field in `run.assumed`. Exclude or flag them when cabin conditions matter.
- **FLEX `burning_rate_mm2_s`** comes from a column labelled "Burning rate; mm". It is verified as the d²-law constant K in mm²/s: observed burn time / ((d₀² − d_ext²)/K) has a median of 1.01–1.05 across burnout, extinction and disruption runs.
- **BASS-II flow:** `velocity_cm_s = 1.0066 × first 'Air display' value` (NASA fan calibration sheet). The display often steps down during a burn (`extra.air_display`, e.g. "5 down to ext"), so this is the *initial* flow. Outcomes (extinction, blowoff, no ignition) are parsed from the same cell for 19 runs.
- **SPICE `extra.flame_on_s`** is operator-controlled, not a natural burn time, so it is not in `outcome`.
- Don't edit `dataset/` by hand. Fix the matching `Normalizer` in `flame/normalize.py`, then run `python3 -m flame.normalize`.
- Changing the schema = edit `flame/schema.py`, bump `SCHEMA_VERSION`, regenerate, and tell the team (the physics engine depends on it).

## What is in it (coverage)

| Investigation | Family | Runs | Has conditions | Has outcomes |
|---|---|---|---|---|
| PSI-69 FLEX | droplet | 274 | fuel, d₀, O₂/N₂/CO₂/He, pressure | **ignited, result, burn time, burning rate K, extinction d** |
| PSI-39 CFI | droplet | 79 | blend, O₂/N₂/He, pressure | none in table (8 exact duplicate rows dropped) |
| PSI-159 CFI-G | gaseous | 333 | fuel, fuel frac, flow, O₂, pressure | **ignited, result, burn time**; cool flame in `extra` |
| PSI-10 Flame Design | gaseous | 327 | fuel, flows, O₂, pressure; Tad/Zst in `extra` | none in table |
| PSI-107 SPICE | gaseous jet | 469 | fuel, nozzle, fuel flow, co-flow air speed | none (smoke point is in reports) |
| PSI-25 BASS-II | solid | 129 | material, geometry, O₂, CO₂, initial flow | extinction / no ignition for 19 runs |
| PSI-98/99/100 SAFFIRE I–III | solid (large scale, Cygnus) | 13 | material, size, flow, O₂, igniter | burn time, spread (partial) |

**Trainable today: FLEX (274) and CFI-G (333)**, plus 26 solid-fuel runs (BASS-II 19, SAFFIRE 7) with sparse outcomes. Exact numbers are in `dataset/coverage.md`.
Use the outcome-less runs as condition-space coverage (what was tested), never as labels.
The other 15 investigations are in `ds.investigations` with `normalized: false` and a `note` explaining why (test-day rows, ranges, smoke aging, modelling-only…).

Splitting for ML: group by test day (`extra.day` for ACME, `date` for FLEX) so runs from one session don't land in both train and test.

## Search the text (findings, not just numbers)

```python
from flame.search import Index
ix = Index()                                   # loads dataset/documents.jsonl into in-memory SQLite FTS5
for h in ix.search("extinction velocity opposed flow PMMA", k=5, investigation="PSI-25"):
    print(h["cite"], h["text"][:200])          # cite = "PSI-25_Reports_BASS-II Summary Report.pdf, p. 34" or a DOI
```
`kind` filter: `objective` | `abstract` | `title` | `report`. Keyword search (BM25): pass key terms, not full questions.
For an LLM: retrieve with `Index.search`, put `text` + `cite` in the prompt, require answers to quote `cite`.
Report pages are NASA public-domain final reports, the best source for *findings*. 158 papers (mostly Elsevier) have no
retrievable abstract, only a title.

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
python3 -m flame.normalize   # → dataset/flame_runs.json + .csv + coverage.md, then checks: counts, ranges,
                             #   round trip, and ~5,000 numeric values re-read from the raw CSVs
python3 -m flame.schema      # schema self-check on the sample file
python3 -m flame.fetch --reports && python3 -m flame.docs   # 40 NASA report PDFs (~120 MB) → page text
python3 -m flame.papers      # abstracts: OpenAlex → Semantic Scholar → NTRS (cached in data/raw/papers)
python3 -m flame.search      # → dataset/documents.jsonl + search self-check
```

## Dashboard (app/ + public/)

```bash
uvicorn app.main:app --reload     # http://localhost:8000  (pip install fastapi uvicorn)
```
- `app/main.py`: FastAPI JSON API over `flame/` and `ranking/`: `/api/meta`, `/api/coverage`, `/api/rank`,
  `/api/nearest`, `/api/investigations/{id}`, `/api/compare?ids=`, `/api/search?q=`, `POST /api/chat`.
- `app/chat.py`: DeepSeek tool-calling agent (tools = search_documents, find_runs, nearest_runs, rank_investigations,
  get_investigation, compare_investigations). It must cite run ids / report pages. Key: `DEEPSEEK_API_KEY` in `.env`
  (local) or the Vercel project env. Model: `CHAT_MODEL` (default `deepseek-chat`).
- `public/`: static frontend (vanilla JS + Plotly): Overview map, Scenario explorer, Investigations, Ask.
- Deploy: Vercel project `flame-in-freefall` (FastAPI preset), live at https://flame-in-freefall-ivory.vercel.app
  (`vercel deploy --prod --scope alexzcoders-projects` from the repo root).
