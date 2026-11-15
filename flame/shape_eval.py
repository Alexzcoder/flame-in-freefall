"""Score the flame simulation against real NASA runs.

For every harvested run (data/frames/*.npz, flame/harvest.py): set the simulation to that run's conditions, measure
the flame the same way in both (flame/shape.py), and compare.
  * Shape trends, per family: Spearman rank correlation sim vs real across runs, per measure. "Does the simulated
    flame get longer / rounder / bluer where the real one does?" The simulation is a 2D sketch with no length scale,
    so trends are the fair test; absolute differences are reported too.
  * Outcome, CFI-G (gas): does the simulated flame go out (extinction) or keep burning until the run is stopped,
    as recorded in the run table? Balanced accuracy vs. always guessing the most common outcome.

    python -m flame.shape_eval                  # default (website) physics → dataset/shape_eval.md + .json
    python -m flame.shape_eval --theta public/station/simparams.json
"""
import argparse, json, os

import numpy as np

from flame.media import ROOT
from flame.shape import MEASURES, clip_measures
from flame.sim import THETA, Sim, load_theta

FRAMES = os.path.join(ROOT, "data", "frames")
REAL_CACHE = os.path.join(FRAMES, "measures.json")
SIM_SECONDS, SIM_EVERY, SIM_SKIP = 30.0, 0.5, 2.0
FAMILY = {"PSI-25": "solid", "PSI-39": "droplet", "PSI-159": "gas"}
COMPARE = MEASURES + ["flicker"]


def runs_by_id():
    return {r["id"]: r for r in json.load(open(os.path.join(ROOT, "dataset", "flame_runs.json")))["runs"]}


def sim_conditions(run):
    """Run record → simulation inputs, or None when the simulation can't represent it (reason in the 2nd value)."""
    c, inv = run["conditions"], run["investigation"]
    atm, fuel = c["atmosphere"], c["fuel"]
    base = dict(gravity_g=c["gravity_g"] or 0.0, o2=atm["o2_frac"], pressure_kpa=atm["pressure_kpa"] or 101.325,
                flow_cm_s=c["flow"]["velocity_cm_s"])
    if base["o2"] is None:
        return None, "oxygen not recorded"
    if inv == "PSI-25":
        if base["flow_cm_s"] is None:
            return None, "airflow not recorded"
        thick = fuel["name"] == "pmma" and (fuel["geometry"] == "rod" or (fuel["thickness_mm"] or 0) >= 1)
        return {**base, "fuel": "pmma" if thick else "fabric"}, None  # thin films and fabrics burn like a thin strip
    if inv == "PSI-39":
        return {**base, "flow_cm_s": 0.0, "fuel": "droplet"}, None  # helium dilution is not modelled
    if inv == "PSI-159":
        x = run["extra"]
        base["tad_k"] = x.get("tad_k")  # adiabatic flame temperature: sets heat release when calibrated (tad_exp)
        if c["o2_location"] == "burner_stream":
            if not x.get("o2_flow_mg_s"):
                return None, "burner oxygen flow not recorded"
            return {**base, "flow_cm_s": 0.0, "fuel": "burner", "inverse": True, "ambient_fuel": fuel["fuel_frac"],
                    "emit": x["o2_flow_mg_s"] / 5.0}, None
        if not fuel["flow_mg_s"]:
            return None, "fuel flow not recorded"
        return {**base, "flow_cm_s": 0.0, "fuel": "burner", "emit": fuel["flow_mg_s"]}, None
    return None, "investigation not simulated"


def real_measures(refresh=False):
    """Measures of every harvested video (cached; recomputed for new or changed files)."""
    import hashlib
    import flame.shape
    code = hashlib.sha1(open(flame.shape.__file__, "rb").read()).hexdigest()[:12]  # new measuring code → recompute
    cache = {} if refresh or not os.path.exists(REAL_CACHE) else json.load(open(REAL_CACHE))
    if cache.get("_code") != code:
        cache = {}
    cache["_code"] = code
    for f in sorted(os.listdir(FRAMES)):
        if not f.endswith(".npz") or ".part" in f:
            continue
        rid = f[:-4].replace("_", "/", 1)
        mtime = os.path.getmtime(os.path.join(FRAMES, f))
        if (cache.get(rid) or {}).get("mtime") == mtime:
            continue
        d = np.load(os.path.join(FRAMES, f))
        m = clip_measures(d["frames"])
        m.pop("series", None)
        cache[rid] = {**m, "mtime": mtime, "fps": float(d["fps"]), "seconds": int(d["flame_end_s"]) - int(d["ignition_s"])}
    with open(REAL_CACHE, "w") as f:
        json.dump(cache, f)
    return {k: v for k, v in cache.items() if k != "_code"}


def sim_measures(conds, theta=None, batch=512, seconds=SIM_SECONDS):
    """Simulate every condition dict; → list of clip measures (frames after SIM_SKIP sim-seconds)."""
    out = []
    for i in range(0, len(conds), batch):
        frames = Sim(conds[i:i + batch], theta).run(seconds, SIM_EVERY).numpy()
        k = int(SIM_SKIP / SIM_EVERY)
        for f in frames:
            m = clip_measures(f[k:], skip=0)
            m["lit_at_start"] = m.pop("series", [None])[0] is not None if m.get("series") else False
            m["ever_lit"] = bool(m["alive"] > 0)
            out.append(m)
    return out


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 4 or a.std() == 0 or b.std() == 0:
        return None
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def evaluate(theta=None, ids=None):
    """→ (report dict, per-run rows). ids: restrict to these runs (calibration folds)."""
    runs, real = runs_by_id(), real_measures()
    rows, skipped = [], {}
    # shape: harvested videos with a usable flame
    for rid, m in real.items():
        if ids is not None and rid not in ids:
            continue
        c, why = sim_conditions(runs[rid])
        if c is None:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        rows.append({"id": rid, "family": FAMILY[runs[rid]["investigation"]], "cond": c, "real": m})
    # outcome: every CFI-G run with a recorded result (video or not)
    out_rows = []
    for rid, r in runs.items():
        if r["investigation"] != "PSI-159" or r["outcome"]["result"] not in ("extinction", "terminated", "no_ignition"):
            continue
        if ids is not None and rid not in ids:
            continue
        c, why = sim_conditions(r)
        if c is not None:
            out_rows.append({"id": rid, "cond": c, "result": r["outcome"]["result"]})
    sims = sim_measures([x["cond"] for x in rows] + [x["cond"] for x in out_rows], theta)
    for x, s in zip(rows, sims):
        x["sim"] = s
    for x, s in zip(out_rows, sims[len(rows):]):
        x["sim"] = s
        x["pred"] = "no_ignition" if not s["ever_lit"] else "extinction" if s["extinguished"] else "terminated"
    rep = {"theta": {**THETA, **(theta or {})}, "skipped": skipped, "shape": {}, "outcome": {}}
    for fam in ("solid", "droplet", "gas"):
        fr = [x for x in rows if x["family"] == fam]
        glare = [x for x in fr if x["real"].get("lit_scene")]
        both = [x for x in fr if x["real"]["alive"] > 0 and x["sim"]["alive"] > 0 and not x["real"].get("lit_scene")]
        res = {"runs": len(fr), "lit_scene_excluded": len(glare), "both_have_flame": len(both), "measures": {}}
        for k in COMPARE:
            pairs = [(x["sim"][k], x["real"][k]) for x in both if x["sim"].get(k) is not None and x["real"].get(k) is not None]
            if pairs:
                s, r = map(np.array, zip(*pairs))
                res["measures"][k] = {"n": len(pairs), "spearman": spearman(s, r), "median_sim": float(np.median(s)),
                                      "median_real": float(np.median(r)), "mae": float(np.abs(s - r).mean())}
        rep["shape"][fam] = res
    if out_rows:
        labels = sorted({x["result"] for x in out_rows})
        recall = {l: float(np.mean([x["pred"] == l for x in out_rows if x["result"] == l])) for l in labels}
        counts = {l: sum(x["result"] == l for x in out_rows) for l in labels}
        conf = {l: {p: sum(x["result"] == l and x["pred"] == p for x in out_rows) for p in labels} for l in labels}
        rep["outcome"] = {"runs": len(out_rows), "counts": counts, "recall": recall,
                          "balanced_accuracy": float(np.mean(list(recall.values()))),
                          "majority_baseline": 1 / len(labels), "confusion": conf}
    return rep, rows + out_rows


def score(rep):
    """One number to maximise in calibration: outcome balanced accuracy + mean shape trend correlation."""
    rhos = [m["spearman"] for f in rep["shape"].values() for m in f["measures"].values() if m["spearman"] is not None]
    return rep.get("outcome", {}).get("balanced_accuracy", 0) + (np.mean(rhos) if rhos else 0)


def markdown(rep):
    L = ["# Flame simulation vs. real NASA runs", "",
         "Generated by `python -m flame.shape_eval`. Measures are defined in `flame/shape.py`; real frames come from "
         "`flame/harvest.py`. Spearman ρ: +1 = the simulation ranks runs exactly like reality, 0 = no relation.", ""]
    o = rep.get("outcome")
    if o:
        L += ["## Outcome: does the gas flame go out? (CFI-G, all runs with a recorded result)", "",
              f"{o['runs']} runs. Balanced accuracy **{o['balanced_accuracy']:.2f}** (guessing: {o['majority_baseline']:.2f}).", "",
              "| real \\ simulated | " + " | ".join(o["counts"]) + " | recall |", "|---" * (len(o["counts"]) + 2) + "|"]
        for l, row in o["confusion"].items():
            L.append(f"| {l} ({o['counts'][l]}) | " + " | ".join(str(v) for v in row.values()) + f" | {o['recall'][l]:.2f} |")
        L.append("")
    L += ["## Shape trends", ""]
    for fam, f in rep["shape"].items():
        L += [f"### {fam}: {f['runs']} runs with video, {f['both_have_flame']} with a flame in both "
              f"({f.get('lit_scene_excluded', 0)} left out: lights on or glare from lit hardware)", "",
              "| measure | n | Spearman ρ | median sim | median real | mean abs diff |", "|---|---|---|---|---|---|"]
        for k, m in f["measures"].items():
            rho = "–" if m["spearman"] is None else f"{m['spearman']:+.2f}"
            L.append(f"| {k} | {m['n']} | {rho} | {m['median_sim']:.2f} | {m['median_real']:.2f} | {m['mae']:.2f} |")
        L.append("")
    if rep["skipped"]:
        L += ["Not simulated: " + ", ".join(f"{v} ({k})" for k, v in rep["skipped"].items()), ""]
    L += [f"Score (balanced accuracy + mean ρ): **{score(rep):.3f}**", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theta", help="simparams.json to evaluate (default: website defaults)")
    ap.add_argument("--out", default=os.path.join(ROOT, "dataset", "shape_eval"))
    a = ap.parse_args()
    theta = {**THETA, **json.load(open(a.theta))["theta"]} if a.theta else None
    rep, rows = evaluate(theta)
    with open(a.out + ".json", "w") as f:
        json.dump(rep, f, indent=1)
    md = markdown(rep)
    open(a.out + ".md", "w").write(md)
    print(md)


if __name__ == "__main__":
    main()
