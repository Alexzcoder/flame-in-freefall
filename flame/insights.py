"""Fire-safety insights for the 3D habitats, from the calibrated flame simulation (+ how sure we can be).

For each habitat (ISS module, Moon base) and each object that burns, simulate a small fire of its material:
  * fans on (the habitat's ventilation speed) and fans off: does the flame keep going or go out by itself?
  * the lowest oxygen level at which it still keeps burning (fans on), vs. the habitat's oxygen
  * how it looks: stretched downstream by the airflow, blue and dim (soot-free) or yellow
Also checks the simulation where NASA has the answer: BASS-II solid runs that went out on their own.

    python -m flame.insights    # → public/station/insights.json (read by station/inside.html)
"""
import json, os

import numpy as np

from flame.media import ROOT
from flame.shape import clip_measures
from flame.shape_eval import runs_by_id, sim_conditions
from flame.sim import PARAMS_JSON, Sim, load_theta

OUT = os.path.join(ROOT, "public", "station", "insights.json")
HABITATS = {  # same as station/inside.html COND
    "iss": {"name": "ISS module", "o2": 0.21, "pressure_kpa": 101.325, "gravity_g": 0.0, "vent_cm_s": 10},
    "moon": {"name": "Moon base", "o2": 0.30, "pressure_kpa": 70.3, "gravity_g": 0.166, "vent_cm_s": 5},
}
MATERIALS = {  # firemodel.js key → simulated fuel, and what NASA data says about ignition
    "fabric": ("fabric", None), "pmma_thin": ("fabric", None), "pmma_thick": ("pmma", None),
    "nomex": ("fabric", "NASA's SAFFIRE tests could not ignite it up to 22.1 % oxygen; this is what happens if it does."),
    "silicone": ("pmma", "NASA's SAFFIRE tests could not ignite it up to 22.1 % oxygen; this is what happens if it does."),
}
ITEMS = {"crew_quarters": "fabric", "galley": "fabric", "glovebox": "pmma_thick", "stowage": "nomex", "cables": "silicone"}
O2_SCAN = np.round(np.arange(0.12, 0.505, 0.02), 3)
SECONDS = 30.0


def fate(conds, theta):
    """→ per condition: {'burns': still burning at the end, 'aspect', 'blue', 'alive'}."""
    fr = Sim(conds, theta).run(SECONDS, 0.5).numpy()
    out = []
    for f in fr:
        m = clip_measures(f[4:], skip=0)
        out.append({"burns": bool(m["alive"] > 0 and not m["extinguished"]), "alive": round(m["alive"], 2),
                    "aspect": None if m.get("aspect") is None else round(m["aspect"], 2),
                    "blue": None if m.get("blue") is None else round(m["blue"], 2)})
    return out


def main():
    theta = load_theta()
    calibrated = os.path.exists(PARAMS_JSON)
    jobs = []
    for hk, h in HABITATS.items():
        for fuel in sorted({v[0] for v in MATERIALS.values()}):
            base = dict(gravity_g=h["gravity_g"], pressure_kpa=h["pressure_kpa"], fuel=fuel)
            jobs.append((hk, fuel, "on", None, {**base, "o2": h["o2"], "flow_cm_s": h["vent_cm_s"]}))
            jobs.append((hk, fuel, "off", None, {**base, "o2": h["o2"], "flow_cm_s": 0.0}))
            jobs += [(hk, fuel, "scan", o, {**base, "o2": float(o), "flow_cm_s": h["vent_cm_s"]}) for o in O2_SCAN]
    res = fate([j[4] for j in jobs], theta)
    by = {}
    for (hk, fuel, kind, o2, _), r in zip(jobs, res):
        by.setdefault((hk, fuel), {"scan": []})
        if kind == "scan":
            by[(hk, fuel)]["scan"].append((o2, r["burns"]))
        else:
            by[(hk, fuel)][kind] = r
    out = {"habitats": {}}
    for hk, h in HABITATS.items():
        items = {}
        for item, mat in ITEMS.items():
            fuel, caveat = MATERIALS[mat]
            d = by[(hk, fuel)]
            burning = [o for o, b in d["scan"] if b]
            min_o2 = min(burning) if burning else None
            on, off = d["on"], d["off"]
            notes = []
            if on["burns"] and not off["burns"]:
                notes.append("Turning the fans off starves this flame of oxygen: it goes out by itself in the simulation.")
            elif on["burns"] and off["burns"]:
                notes.append("Turning the fans off is not enough here: the flame keeps burning without airflow.")
            elif not on["burns"]:
                notes.append("At this habitat's air a small flame of this material dies out in the simulation.")
            if min_o2 is not None:
                margin = h["o2"] - min_o2
                notes.append(f"Keeps burning down to about {min_o2 * 100:.0f} % oxygen with the fans on "
                             f"({'%.0f points below' % (margin * 100) if margin > 0 else 'above'} this habitat's {h['o2'] * 100:.0f} %).")
            if on.get("blue") is not None and on["blue"] > 0.4:
                notes.append("Mostly blue, soot-free light: dim and easy to miss, and little smoke for detectors.")
            if on.get("aspect") and on["aspect"] > 2.5:
                notes.append("The airflow stretches it downstream, so it spreads toward where the air goes.")
            items[item] = {"material": mat, "sim_fuel": fuel, "fans_on": on, "fans_off": off,
                           "min_o2_burning_fans_on": min_o2, "notes": notes, "caveat": caveat}
        out["habitats"][hk] = {**h, "items": items}
    # where NASA has the answer: BASS-II solids that went out on their own
    runs = runs_by_id()
    bass = [(rid, r) for rid, r in runs.items() if r["investigation"] == "PSI-25" and r["outcome"]["result"] == "extinction"]
    conds = [(rid, sim_conditions(r)[0]) for rid, r in bass]
    conds = [(rid, c) for rid, c in conds if c]
    vr = fate([c for _, c in conds], theta) if conds else []
    out["validation"] = {
        "bass2_went_out": len(conds), "sim_also_goes_out": sum(not r["burns"] for r in vr),
        "runs": {rid: {"o2": c["o2"], "flow_cm_s": c["flow_cm_s"], "sim_burns": r["burns"]} for (rid, c), r in zip(conds, vr)},
        "note": "All 17 BASS-II runs with a recorded outcome went out by themselves (none burned to the end), so this "
                "checks one side only."}
    out["model"] = {"calibrated": calibrated, "theta": theta,
                    "method": "flame/sim.py with the knobs fitted by flame/calibrate.py; 2D, small flame, 30 simulated "
                              "seconds; 'burns' = still visible at the end. Evaluation: dataset/shape_eval.md."}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    v = out["validation"]
    print(f"insights written; BASS-II check: sim goes out in {v['sim_also_goes_out']}/{v['bass2_went_out']} runs that really went out")
    for hk, h in out["habitats"].items():
        for item, x in h["items"].items():
            print(hk, item, "on:", x["fans_on"]["burns"], "off:", x["fans_off"]["burns"], "min O2:", x["min_o2_burning_fans_on"])


if __name__ == "__main__":
    main()
