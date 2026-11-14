"""Habitat fire risk: if a fire starts at one object, how likely is it to reach the others, and how fast?

Two layers, kept apart because they rest on different evidence:
  1. On the burning object (NASA-calibrated simulation, flame/sim.py spread mode at the habitat's air): does a flame
     of this material survive, how fast it spreads (mm/s, with the airflow), and does turning the fans off stop it.
  2. Between objects (standard fire-engineering estimate, NOT NASA microgravity data): the burning area grows at the
     simulated spread speed, its heat release (area x heat release per m^2) radiates as a point source
     (flux = chi * HRR / (4 pi d^2)), objects downwind get extra heat from the hot gas the vent carries, and a
     neighbour ignites when the flux passes its critical heat flux. Material values are typical 1 g laboratory
     ranges (ASSUMPTION, see MATERIALS); every uncertain value is drawn from its range in a Monte Carlo.
Scenes (object positions, fuel loads, vent direction): public/station/scenes/<habitat>.json.

    python -m flame.risk     # → public/station/risk.json
"""
import json, os

import numpy as np

from flame.media import ROOT
from flame.sim import THETA, Sim, load_theta
from flame.spread import mm_per_s, scales

SCENES = os.path.join(ROOT, "public", "station", "scenes")
OUT = os.path.join(ROOT, "public", "station", "risk.json")
WINDOW_S, DRAWS = 300, 2000  # crew response window (assumption: 5 min) and Monte Carlo draws
# ASSUMPTION ranges (1 g laboratory values; microgravity flames are smaller and cooler, so the low ends are favoured
# by the 0.3-1 scaling below): heat release per m^2 burning (kW/m^2), critical heat flux to ignite (kW/m^2),
# time one m^2 burns (s). sim: fuel used in the simulation's spread mode.
MATERIALS = {
    "fabric": {"sim": "fabric", "hrr": (100, 300), "q_crit": (10, 15), "burn_s": (60, 180)},
    "pmma_thick": {"sim": "pmma", "hrr": (300, 800), "q_crit": (10, 16), "burn_s": (600, 1800)},
    "nomex": {"sim": "fabric", "hrr": (50, 150), "q_crit": (20, 28), "burn_s": (60, 180),
              "no_ignition_o2": 0.221},  # SAFFIRE: did not ignite up to 22.1 % O2
    "silicone": {"sim": "pmma", "hrr": (80, 200), "q_crit": (20, 30), "burn_s": (300, 900), "no_ignition_o2": 0.221},
}
CHI = (0.2, 0.4)        # share of heat radiated
UG_SCALE = (0.3, 1.0)   # microgravity flames release less heat per area than 1 g lab tests
DOWNWIND = 1.0          # extra heat for an object straight downwind, at 10 cm/s (scales with vent speed)


def spread_inputs(scene, theta):
    """Simulated spread speed (mm/s) and survival, fans on and off, per simulated fuel at this habitat's air."""
    air = scene["air"]
    tau, fs = scales()
    fuels = sorted({m["sim"] for m in MATERIALS.values()})
    conds, keys = [], []
    for f in fuels:
        for fans in ("on", "off"):
            conds.append(dict(gravity_g=air["gravity_g"], o2=air["o2"], pressure_kpa=air["pressure_kpa"], spread=True,
                              flow_cm_s=air["vent_cm_s"] if fans == "on" else 0.0, fuel=f, ignite="upstream"))
            keys.append((f, fans))
    front, alive, times = Sim(conds, theta).run_spread(40.0, 0.25)
    out = {}
    for k, fr, al in zip(keys, front, alive):
        reach = float(np.nanmax(np.nan_to_num(fr, nan=0.0)))
        survives = bool(al[len(al) // 2:].mean() > 0.5) or reach > 0.95
        out[k] = {"mm_s": mm_per_s(fr, times, tau, fs) if survives else None, "survives": survives}
    return out


def simulate_scene(scene, sp, fans, rng):
    objs = [o for o in scene["objects"] if o["material"]]
    air = scene["air"]
    pos = np.array([[o["pos"][0], o["pos"][2]] for o in objs], float)
    vent = np.array(scene["vent_dir"], float)
    vent /= np.linalg.norm(vent)
    n = len(objs)
    mats = [MATERIALS[o["material"]] for o in objs]
    can_burn = np.array([not (m.get("no_ignition_o2") and air["o2"] <= m["no_ignition_o2"]) for m in mats])
    s = [sp[(m["sim"], fans)] for m in mats]
    results = {}
    for a in range(n):
        if not can_burn[a] or not s[a]["survives"]:
            results[objs[a]["id"]] = {"start_survives": False, "p_reach": {}, "expected_objects": 1.0 if s[a]["survives"] else 0.0,
                                      "median_first_s": None}
            continue
        reached = np.zeros((DRAWS, n), bool)
        first_t = np.full(DRAWS, np.inf)
        for d in range(DRAWS):
            # one uncertain world
            chi, ug = rng.uniform(*CHI), rng.uniform(*UG_SCALE)
            hrr = np.array([rng.uniform(*m["hrr"]) for m in mats]) * ug
            qc = np.array([rng.uniform(*m["q_crit"]) for m in mats])
            burn = np.array([rng.uniform(*m["burn_s"]) for m in mats])
            v = np.array([(x["mm_s"] or 0.0) * rng.uniform(0.7, 1.4) for x in s]) / 1000  # m/s
            t_ign = np.full(n, np.inf)
            t_ign[a] = 0.0
            for _ in range(n):  # cascade: recompute arrival times until nothing changes (n passes is enough)
                for i in np.argsort(t_ign):
                    if not np.isfinite(t_ign[i]) or t_ign[i] > WINDOW_S:
                        continue
                    area_max = objs[i]["load_m2"]
                    t = np.arange(0, WINDOW_S - t_ign[i], 2.0)
                    area = np.minimum(area_max, np.pi * (v[i] * t) ** 2)
                    area = np.where(t > burn[i] * max(area_max, 0.1), 0.0, area)  # burnt out
                    q = chi * hrr[i] * area  # radiated kW
                    for j in range(n):
                        if j == i or not can_burn[j] or t_ign[j] <= t_ign[i]:
                            continue
                        dvec = pos[j] - pos[i]
                        dist = max(np.linalg.norm(dvec), 0.3)
                        down = max(0.0, float(dvec @ vent) / dist) * DOWNWIND * (air["vent_cm_s"] / 10 if fans == "on" else 0)
                        flux = q / (4 * np.pi * dist ** 2) * (1 + down)
                        hit = np.nonzero(flux > qc[j])[0]
                        if len(hit):
                            t_ign[j] = min(t_ign[j], t_ign[i] + t[hit[0]])
            reached[d] = t_ign <= WINDOW_S
            others = [t_ign[j] for j in range(n) if j != a and t_ign[j] <= WINDOW_S]
            first_t[d] = min(others) if others else np.inf
        p = reached.mean(0)
        fin = first_t[np.isfinite(first_t)]
        # safe separation: distance at which the fully burning object's radiation drops below the critical heat flux
        # of fabric (the easiest neighbour to ignite), over the uncertain ranges
        k = rng.uniform(*CHI, DRAWS) * rng.uniform(*UG_SCALE, DRAWS) * rng.uniform(*mats[a]["hrr"], DRAWS)
        d_safe = np.sqrt(k * objs[a]["load_m2"] / (4 * np.pi * rng.uniform(*MATERIALS["fabric"]["q_crit"], DRAWS)))
        others = [np.linalg.norm(pos[j] - pos[a]) for j in range(n) if j != a]
        results[objs[a]["id"]] = {
            "start_survives": True, "spread_mm_s": s[a]["mm_s"],
            "p_reach": {objs[j]["id"]: round(float(p[j]), 3) for j in range(n) if j != a},
            "expected_objects": round(float(reached.sum(1).mean()), 2),
            "p_spreads_at_all": round(float(np.isfinite(first_t).mean()), 3),
            "median_first_s": round(float(np.median(fin))) if len(fin) else None,
            "safe_distance_m": {"median": round(float(np.median(d_safe)), 2), "p90": round(float(np.percentile(d_safe, 90)), 2)},
            "nearest_flammable_m": round(float(min(others)), 2) if others else None}
    return results


def main():
    theta = load_theta()
    rng = np.random.default_rng(0)
    out = {"window_s": WINDOW_S, "draws": DRAWS, "habitats": {},
           "method": __doc__.split("\n\n")[0].strip(), "assumptions": {
               "materials": MATERIALS, "radiated_share": CHI, "microgravity_heat_scale": UG_SCALE,
               "downwind_extra": f"+{DOWNWIND:.0%} heat straight downwind at 10 cm/s (scales with vent speed)",
               "window": "crew response within 5 minutes", "source": "typical 1 g laboratory values, not NASA data",
               "not_modelled": "fire travelling along things that connect objects (cable bundles, clothing, bags "
                               "strapped between racks), which is how real spacecraft fires spread; direct flame "
                               "contact; smoke and toxic gases"}}
    for f in sorted(os.listdir(SCENES)):
        scene = json.load(open(os.path.join(SCENES, f)))
        sp = spread_inputs(scene, theta)
        hab = {"name": scene["name"], "air": scene["air"],
               "spread": {f"{k[0]}_{k[1]}": v for k, v in sp.items()}, "fans": {}}
        for fans in ("on", "off"):
            res = simulate_scene(scene, sp, fans, rng)
            starts = [r for r in res.values()]
            hab["fans"][fans] = {"objects": res,
                                 "habitat_expected_objects": round(float(np.mean([r["expected_objects"] for r in starts])), 2),
                                 "habitat_p_spread": round(float(np.mean([r.get("p_spreads_at_all", 0) for r in starts])), 3)}
        out["habitats"][scene["habitat"]] = hab
        print(scene["name"], {k: (v["habitat_expected_objects"], v["habitat_p_spread"]) for k, v in hab["fans"].items()},
              {k: v for k, v in hab["spread"].items()}, flush=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
