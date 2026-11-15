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
    """→ per condition: {'burns': visible flame for most of the last quarter (same rule as flame/calibrate.py),
    'aspect', 'blue', 'alive'}."""
    from flame.calibrate import simulate
    alive, frames = simulate([{"cond": c, "frames": True} for c in conds], [theta], SECONDS)
    out = []
    for k, a in enumerate(alive[0]):
        m = clip_measures(frames[(0, k)][4:], skip=0)  # shape, from the first 20 s
        out.append({"burns": bool(a[-len(a) // 4:].mean() > 0.5), "alive": round(float(a.mean()), 2),
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
                notes.append("Turning the fans off is not enough here: the flame keeps burning without airflow."
                             + (" Gravity makes the hot gas rise and pulls in fresh air by itself (physics: NASA has no "
                                "fire tests at lunar gravity)." if h["gravity_g"] > 0 else ""))
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
    # where NASA has the answer: BASS-II flames burned at the initial airflow and went out when the crew turned the
    # fan down; SAFFIRE flames kept burning (the solid fate cases of flame/calibrate.py, used to fit the knobs)
    from flame.calibrate import datasets
    cases = datasets()[2]
    vr = fate([c["cond"] for c in cases], theta)
    ok = [r["burns"] == c["burns"] for c, r in zip(cases, vr)]
    out["validation"] = {
        "cases": len(cases), "matched": int(sum(ok)),
        "runs": {c["id"]: {"o2": c["cond"]["o2"], "flow_cm_s": c["cond"]["flow_cm_s"], "nasa_burns": c["burns"],
                           "sim_burns": r["burns"]} for c, r in zip(cases, vr)},
        "note": "These cases were used to fit the knobs, so this shows the model reproduces them, not that it predicts "
                "new ones. Leave-one-out results: dataset/shape_eval.md."}
    out["model"] = {"calibrated": calibrated, "theta": theta,
                    "method": "flame/sim.py with the knobs fitted by flame/calibrate.py; 2D, small flame, 30 simulated "
                              "seconds; 'burns' = still visible at the end. Evaluation: dataset/shape_eval.md."}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    v = out["validation"]
    print(f"insights written; solid fate check: {v['matched']}/{v['cases']} NASA cases matched")
    for hk, h in out["habitats"].items():
        for item, x in h["items"].items():
            print(hk, item, "on:", x["fans_on"]["burns"], "off:", x["fans_off"]["burns"], "min O2:", x["min_o2_burning_fans_on"])


if __name__ == "__main__":
    main()
