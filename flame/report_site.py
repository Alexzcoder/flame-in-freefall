"""Build public/checked.html ("How we checked") from the report files, so the page shows only measured numbers.

Reads: dataset/predict_eval.json, public/station/simparams.json, dataset/loo_eval.md, dataset/spread_eval.md,
public/models/flame_emulator.json, public/station/insights.json, public/station/risk.json.

    python -m flame.report_site
"""
import json, os, re

from flame.media import ROOT

OUT = os.path.join(ROOT, "public", "checked.html")


def load(rel):
    try:
        p = os.path.join(ROOT, rel)
        return json.load(open(p)) if rel.endswith(".json") else open(p).read()
    except FileNotFoundError:
        return None


def main():
    pe, sp, em = load("dataset/predict_eval.json"), load("public/station/simparams.json"), load("public/models/flame_emulator.json")
    loo, spread = load("dataset/loo_eval.md") or "", load("dataset/spread_eval.md") or ""
    m = re.search(r"Solid fate: (\d+) of (\d+)", loo)
    fate_loo = f"{m.group(1)} of {m.group(2)}" if m else "pending"
    m = re.search(r"Spread: (\d+) of (\d+)", loo)
    spread_loo = f"{m.group(1)} of {m.group(2)}" if m else "pending"
    m = re.search(r"\*\*(\d+) of (\d+)\*\* NASA targets matched", spread)
    spread_fit = f"{m.group(1)} of {m.group(2)}" if m else "pending"
    rows_data = ""
    if pe:
        go, gt, do, dk, dx = (pe[k] for k in ("gas_outcome", "gas_extinction_time", "droplet_outcome", "droplet_burning_rate", "droplet_extinction_size"))
        rows_data = f"""
<tr><td>Gas flame (CFI-G): no ignition / goes out / still burning</td><td>{go['runs']}</td><td><b>{go['balanced_accuracy']:.2f}</b> balanced accuracy</td><td>{go['guessing']:.2f}</td></tr>
<tr><td>Gas flame: seconds until it goes out</td><td>{gt['runs']}</td><td>typically off by <b>×{gt['median_factor_error']:.2f}</b></td><td>×{gt['baseline_factor_error']:.2f}</td></tr>
<tr><td>Droplet (FLEX): goes out vs. burns completely</td><td>{do['runs']}</td><td><b>{do['balanced_accuracy']:.2f}</b> balanced accuracy</td><td>{do['guessing']:.2f}</td></tr>
<tr><td>Droplet burning rate K</td><td>{dk['runs']}</td><td><b>{dk['median_abs_error_mm2_s']:.3f}</b> mm²/s median error</td><td>{dk['baseline_mm2_s']:.3f}</td></tr>
<tr><td>Droplet size when the flame goes out (share of start)</td><td>{dx['runs']}</td><td><b>{dx['median_abs_error']:.3f}</b> median error</td><td>{dx['baseline']:.3f}</td></tr>"""
    rows_sim = ""
    if sp:
        for name, key in (("Original (hand-tuned)", "website_defaults_fit"), ("Tuned on NASA runs", "fit")):
            t = sp[key]["test"]
            tf = t["extinction_time_factor_median"]
            rows_sim += (f"<tr><td>{name}</td><td>{t['balanced_accuracy']:.2f}</td><td>{'×%.2f' % tf if tf else '–'}</td>"
                         f"<td>{sp[key]['solid_fate']['sim_goes_out'] + sp[key]['solid_fate']['sim_keeps_burning']} of "
                         f"{sp[key]['solid_fate']['went_out_runs'] + sp[key]['solid_fate']['burned_runs']}</td></tr>")
    emu = ""
    if em:
        r = em["test"]
        emu = (f"Tested on {r['test']:,} held-out simulations: it predicts whether a flame lights in "
               f"{r['accuracy']['ignited']:.1%} and whether it goes out in {r['accuracy']['extinguished']:.1%} of cases.")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>How we checked · Flame in Freefall</title><link rel="icon" href="img/ember-icon.png">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0b0d12;--panel:#12151e;--line:#2a303c;--fg:#e4e7ee;--mute:#8a93a6;--acc:#ff7a2f;--ok:#3ecf8e;--warn:#f6c945}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 Inter,system-ui,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:28px 16px 60px}}a{{color:#5aa9ff}}h1{{font-size:30px;margin:10px 0 6px}}
h2{{font-size:20px;margin:34px 0 8px}}.lead{{color:#c9cdd6}}.mute{{color:var(--mute);font-size:13px}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}}th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--mute);font-weight:600}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:12px 0}}
.k{{display:inline-block;font-size:11px;font-weight:700;border-radius:4px;padding:1px 6px;margin-right:6px}}
.cv{{background:#3ecf8e22;color:#7ee8b8}}.ho{{background:#5aa9ff22;color:#9ccaff}}.fit{{background:#f6c94522;color:#f6dc8a}}
header{{display:flex;align-items:center;gap:10px}}header img{{width:40px;height:40px}}
.scroll{{overflow-x:auto}}
</style></head><body><main>
<header><a href="/"><img src="img/ember-logo.gif" alt="Flame in Freefall"></a><a href="/" style="color:var(--fg);text-decoration:none;font-weight:700">Flame in Freefall</a></header>
<h1>How we checked our numbers</h1>
<p class="lead">Every claim on this site comes with how it was tested. Labels:
<span class="k cv">CROSS-VALIDATED</span>scored on whole NASA test days the model never saw ·
<span class="k ho">HELD OUT</span>one set of test days kept aside ·
<span class="k fit">FIT</span>reproduces cases it was tuned on (not a prediction).</p>

<h2>1. The data</h2>
<div class="card">1,624 NASA microgravity combustion runs from 24 investigations in NASA's Physical Sciences Informatics archive,
one schema, every value traced to its source file and row. 5,123 numbers re-read from NASA's raw files and matched.
Assumed values (e.g. cabin pressure when not recorded) and censored burn times are flagged on every run.</div>

<h2>2. Data models: the numbers we predict <span class="k cv">CROSS-VALIDATED</span></h2>
<p class="mute">Gradient-boosted trees, 5-fold cross-validation by NASA test day; 80 % ranges calibrated on the same folds.</p>
<div class="scroll"><table><tr><th>What is predicted</th><th>Runs</th><th>Model</th><th>Guessing</th></tr>{rows_data}</table></div>

<h2>3. The flame simulation <span class="k ho">HELD OUT</span></h2>
<p class="mute">A 2D fluid + combustion simulation, tuned on NASA gas-flame outcomes (331 runs), BASS-II flame shapes measured
from 384 NASA videos, and solid burn-or-out cases. Scored on test days the tuning never saw.</p>
<div class="scroll"><table><tr><th>Physics</th><th>Gas flame outcome, balanced accuracy (test days)</th><th>Gas flame-out time error (test days)</th><th>Solid burns or goes out (all cases)</th></tr>{rows_sim}</table></div>
<div class="card"><b>What tuning bought:</b> solid fires now survive or go out the way NASA saw (burning at the initial
airflow, out when the fan is turned down). Predicted without seeing the case (leave-one-out): <b>{fate_loo}</b>
<span class="k cv">LEAVE-ONE-OUT</span><br><b>What it did not:</b> gas-flame outcomes are no better than guessing on test
days, so gas-flame and droplet numbers on this site come from the data models above. Flame shapes did not hold up on
held-out runs, so the flames you see in the simulator are illustrative.</div>

<h2>4. Flame spread <span class="k fit">FIT</span> <span class="k cv">LEAVE-ONE-OUT</span></h2>
<div class="card">Seven NASA targets (BASS-II Summary Report NASA/TM-20210011385; SAFFIRE-II): spread speeds and the
airflow below which a flame goes out. Fit: <b>{spread_fit}</b> matched. Predicted with each target left out: <b>{spread_loo}</b>.</div>

<h2>5. The instant predictor (neural network)</h2>
<div class="card">A small neural network trained on 20,000 runs of the tuned simulation, so the site can answer instantly.
{emu} It copies the simulation, errors included.</div>

<h2>6. What we do not claim</h2>
<ul><li>Every NASA run here was in microgravity. Moon and Earth gravity effects come from physics, not data.</li>
<li>Spread between objects (safe separation distances) uses standard fire-engineering heat-radiation estimates with
typical laboratory values, not NASA microgravity data, and ignores fire travelling along cables or bags.</li>
<li>Above 22 % oxygen no solid material has been burned in microgravity in NASA's public data: anything there is an extrapolation.</li></ul>
<p class="mute">Full reports in the repository: dataset/predict_eval.md, dataset/shape_eval.md, dataset/spread_eval.md,
dataset/loo_eval.md, docs/models.md.</p>
</main></body></html>"""
    open(OUT, "w").write(html)
    print("wrote", OUT, "| fate LOO", fate_loo, "| spread fit", spread_fit, "| spread LOO", spread_loo)


if __name__ == "__main__":
    main()
