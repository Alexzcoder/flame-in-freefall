# ranking/: relevance ranking + auto-generated comparison

Owner: Kai. **Only edit files in this folder.** It reads `dataset/flame_runs.json` and never changes
`flame/` or `dataset/`. Other teammates use it through the JSON files or the two functions below.

## Use it

```bash
python3 -m ranking.rank moon_base                    # ranked list in the terminal
python3 -m ranking.rank iss --focus detection        # prevention | detection | suppression
python3 -m ranking.compare PSI-25 PSI-99             # what's the same / different
python3 -m ranking.compare PSI-25 PSI-99 --llm       # + AI summary (needs an API key, see below)
python3 -m ranking.export                            # writes ranking/out/*.json for the frontend
python3 -m ranking.test_ranking                      # quick checks
```

Run from the repo root. Scenarios: `iss`, `moon_base`, `pressurized_rover`, `mars_base`
(edit `scenarios.py` to add more; `custom(o2_frac, pressure_kpa, ...)` builds one from sliders).

## AI summaries (DeepSeek or Claude)

Optional. Without a key everything still works and uses template summaries.

```bash
cp ranking/.env.example .env      # in the repo root; .env is git-ignored
# edit .env: put your key after DEEPSEEK_API_KEY= (or ANTHROPIC_API_KEY=)
python3 -m ranking.llm            # self-test: prints provider + model, makes one tiny call
python3 -m ranking.export --llm   # regenerate comparisons with AI summaries
```
- `RANKING_LLM_PROVIDER=auto` (default) uses DeepSeek if its key is set, otherwise Claude.
- Default models: `deepseek-flash`, `claude-sonnet-5-5`. Override with `RANKING_LLM_MODEL`.
- The AI only rewrites the computed facts into prose; it is told not to add numbers or claims.
- **Never commit a key.** Keys go in `.env` (ignored by git) or your shell, never in code.

## For the frontend (no Python needed)

`ranking/out/rankings.json`
```
rankings[scenario_id][focus]          focus = "all" | "prevention" | "detection" | "suppression"
  .scenario   {name, o2_pct, pressure_psi, gravity_g, note, ...}
  .results[]  {rank, id, acronym, title, category, pillars, score (0-100),
               components {condition_match, labelled_data, cabin_relevance, safety_focus} (0-1),
               n_runs, n_close_runs, closest_runs[{run_id, similarity, o2_pct, pressure_kpa, fuel, has_outcome}],
               reasons[], caveats[]}
```

`ranking/out/comparisons.json`
```
investigations[id]   profile: fuels, o2_frac_range, pressure_kpa_range, flow_cm_s_range, outcome_fields, pillars, ...
pairs["PSI-25|PSI-99"] {similarities[], differences[], summary, summary_source ("template" | "llm")}
```
Pair keys are sorted by PSI number (lower number first).

## Nearest experiments to the simulator's sliders

```bash
python3 -m ranking.nearest --o2 0.30 --pressure 70.3 --flow 10 --phase solid
```
`nearest_runs(ds, o2_frac, pressure_kpa, flow_cm_s, gravity_g, fuel_phase, k)` returns:
```
coverage   "well_covered" (10+ near runs) | "sparse" (1-9) | "no_data" (0)
message    one-line explanation for the UI
warning    shown when nothing is near (null otherwise)
matches[]  closest runs, ALWAYS returned, each with:
  match        "near" (similarity >= 0.5) | "partial" (0.1-0.5) | "far" (< 0.1)
  warning      e.g. "Not near your settings: oxygen is 8 points higher than this run (30% vs 22%); ..."
  differences  every setting that differs, biggest first
  similarity, acronym, run_id, fuel, o2_pct, pressure_kpa, flow_cm_s, outcome{}, assumed[], media[]
```
UI suggestion: green badge for near, amber for partial, grey/red with the warning text for far.

## For Python teammates (chatbot, physics engine)

```python
from flame.schema import Dataset
from ranking.rank import rank
from ranking.compare import compare
from ranking.scenarios import custom
ds = Dataset.from_json("dataset/flame_runs.json")
rank(ds, custom(0.30, 70.3, gravity_g=0.166))   # e.g. ranking for the simulator's current slider values
compare(ds, ["PSI-69", "PSI-39"])
```

## How the score works

`score = 50% condition match + 20% labelled data + 20% cabin relevance + 10% fire-safety focus`

- **Condition match**: each run gets a similarity (0-1) from its distance to the scenario
  (O2 +-4 points, pressure +-20 %, flow +-15 cm/s at 1 sigma). Average of the 5 closest runs.
  Only `o2_location == "ambient"` runs count; runs with assumed O2/pressure count half.
- **Labelled data**: share of nearby runs with `has_outcome == True`.
- **Cabin relevance**: solid materials 1.0, smoke 0.9, droplets 0.6, gas flames 0.5, other 0.4.
- **Fire-safety focus**: fire-safety keywords in the title and objective.
- Investigations without run data are still listed, ranked on their description, with a caveat.
- With `--focus`, investigations covering that pillar are listed first.

Every number in `reasons` comes from the dataset, so it can be shown to judges as is.
The AI summary (optional) only rewrites the computed facts; it is told not to add new claims.
