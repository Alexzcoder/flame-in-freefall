"""Flame spread over a fuel strip: fit the spread knobs to NASA spread rates and extinction limits, and report.

Spread mode in flame/sim.py: a strip of fuel cells that heat up (slowly when thick), release fuel vapour above a
pyrolysis temperature and burn out, so the flame front moves by itself. Speeds in mm/s come from the scales the main
calibration already fixed: tau (real seconds per sim second, from CFI-G extinction times) and flow_scale (cells per
sim second per cm/s). One grid cell = 1 / (flow_scale * tau) cm. Nothing here is free to rescale speeds.

Targets (thin = 100 um PMMA film or fabric):
  BASS-II Summary Report (NASA/TM-20210011385):
    thin PMMA, opposed flow, 20.7 % O2: steady spread 2.2 mm/s (pp. 31, 49)
    thin PMMA, 21 % O2: goes out within 2 s when the flow is cut (p. 31); extinction flow ~1 cm/s (p. 31)
    thin PMMA, 16 % O2: extinction flow ~2.6 cm/s (p. 23)
  SAFFIRE-II (PSI-99 runs 2-5, 2-6): cotton/fibreglass fabric, concurrent 20 cm/s, 22.1 % O2: 2.1-2.6 mm/s
Reported only (not fitted): thick PMMA ~0.044 mm/s is a 1 g downward value (p. 50), not microgravity.

    python -m flame.spread --gens 12     # adds the spread knobs to public/station/simparams.json, writes dataset/spread_eval.md
"""
import argparse, json, os

import numpy as np

from flame.media import ROOT
from flame.sim import PARAMS_JSON, THETA, W, Sim, load_theta

REPORT = os.path.join(ROOT, "dataset", "spread_eval.md")
KNOBS = {"pyro": (0.2, 0.9, 0), "c_thin": (0.03, 3, 1), "c_thick": (1, 60, 1), "burn_thin": (0.02, 2, 1),
         "burn_thick": (0.001, 0.2, 1), "k_strip": (0.5, 30, 1)}
BASE = dict(gravity_g=0.0, pressure_kpa=101.325, spread=True)
# name, conditions, target: ("speed", mm/s, tolerance factor) or ("burns", True/False), source
TARGETS = [
    ("thin PMMA opposed 5 cm/s, 20.7% O2", dict(o2=0.207, flow_cm_s=5, fuel="fabric", ignite="downstream"),
     ("speed", 2.2, 1.3), "BASS-II Summary Report pp. 31, 49"),
    ("thin PMMA opposed 3 cm/s, 21% O2", dict(o2=0.21, flow_cm_s=3, fuel="fabric", ignite="downstream"),
     ("burns", True), "BASS-II Summary Report p. 31 (burns above ~1 cm/s)"),
    ("thin PMMA, flow cut, 21% O2", dict(o2=0.21, flow_cm_s=0, fuel="fabric", ignite="downstream"),
     ("burns", False), "BASS-II Summary Report p. 31 (out within 2 s)"),
    ("thin PMMA opposed 0.5 cm/s, 21% O2", dict(o2=0.21, flow_cm_s=0.5, fuel="fabric", ignite="downstream"),
     ("burns", False), "BASS-II Summary Report p. 31 (extinction ~1 cm/s)"),
    ("thin PMMA opposed 4 cm/s, 16% O2", dict(o2=0.16, flow_cm_s=4, fuel="fabric", ignite="downstream"),
     ("burns", True), "BASS-II Summary Report p. 23 (extinction ~2.6 cm/s at 16%)"),
    ("thin PMMA opposed 1.5 cm/s, 16% O2", dict(o2=0.16, flow_cm_s=1.5, fuel="fabric", ignite="downstream"),
     ("burns", False), "BASS-II Summary Report p. 23"),
    ("SIBAL fabric concurrent 20 cm/s, 22.1% O2", dict(o2=0.221, flow_cm_s=20, fuel="fabric", ignite="upstream"),
     ("speed", 2.35, 1.3), "SAFFIRE-II PSI-99 runs 2-5, 2-6 (2.1-2.6 mm/s)"),
]
REPORT_ONLY = [("thick PMMA opposed 5 cm/s, 21% O2", dict(o2=0.21, flow_cm_s=5, fuel="pmma", ignite="downstream"),
                "~0.044 mm/s in 1 g downward spread (p. 50); no microgravity value in the report text")]
SECONDS, EVERY = 40.0, 0.25


def scales():
    """tau and flow_scale from the main calibration (simparams.json), else the defaults."""
    try:
        j = json.load(open(PARAMS_JSON))
        return float(j["tau_real_s_per_sim_s"]), float(j["theta"].get("flow_scale", THETA["flow_scale"]))
    except (FileNotFoundError, KeyError):
        return 4.0, THETA["flow_scale"]


def mm_per_s(front, times, tau, fs):
    """Front (fraction of strip) over sim time → steady spread speed in real mm/s (slope over 15-85 % of the strip)."""
    f, t = np.asarray(front, float), np.asarray(times)
    ok = ~np.isnan(f) & (f > 0.15) & (f < 0.85)
    if ok.sum() < 4:
        return None
    slope = np.polyfit(t[ok], f[ok], 1)[0]  # strip fractions per sim-second
    if slope <= 0:
        return None
    cells = slope * 0.84 * W
    return float(cells * 10 / (fs * tau) / tau)  # cells/sim-s → cm/sim-s → mm/real-s


def run(thetas, cases, tau, fs):
    conds = [{**BASE, **c} for _, c, *_ in cases]
    rows = [(ti, ci) for ti in range(len(thetas)) for ci in range(len(cases))]
    front, alive, times = Sim([conds[ci] for _, ci in rows], [thetas[ti] for ti, _ in rows]).run_spread(SECONDS, EVERY)
    out = [[None] * len(cases) for _ in thetas]
    for k, (ti, ci) in enumerate(rows):
        burning_late = bool(alive[k][int(len(times) * 0.5):].mean() > 0.5) or bool(np.nanmax(np.nan_to_num(front[k])) > 0.95)
        out[ti][ci] = {"mm_s": mm_per_s(front[k], times, tau, fs), "burns": burning_late,
                       "reach": float(np.nanmax(np.nan_to_num(front[k], nan=0.0)))}
    return out


def loss(res):
    L = []
    for (_, _, tgt, _), r in zip(TARGETS, res):
        if tgt[0] == "speed":
            L.append(1.0 if r["mm_s"] is None else min(1.0, abs(np.log(r["mm_s"] / tgt[1])) / np.log(3)))
        else:
            L.append(0.0 if r["burns"] == tgt[1] else 1.0)
    return float(np.mean(L))


def to_theta(z, base):
    th = dict(base)
    for (k, (lo, hi, lg)), v in zip(KNOBS.items(), np.clip(z, 0, 1)):
        th[k] = float(np.exp(np.log(lo) + v * (np.log(hi) - np.log(lo))) if lg else lo + v * (hi - lo))
    return th


def from_theta(th):
    return np.array([(np.log(th[k]) - np.log(lo)) / (np.log(hi) - np.log(lo)) if lg else (th[k] - lo) / (hi - lo)
                     for k, (lo, hi, lg) in KNOBS.items()]).clip(0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=12)
    ap.add_argument("--pop", type=int, default=32)
    a = ap.parse_args()
    base = load_theta()
    tau, fs = scales()
    rng = np.random.default_rng(0)
    mean, std = from_theta(base), np.full(len(KNOBS), 0.3)
    best = (loss(run([base], TARGETS, tau, fs)[0]), base)
    print(f"tau {tau:.2f} s/sim-s, 1 cell = {10 / (fs * tau):.2f} mm; start loss {best[0]:.3f}", flush=True)
    for gen in range(a.gens):
        Z = np.clip(mean + std * rng.standard_normal((a.pop, len(KNOBS))), 0, 1)
        ths = [to_theta(z, base) for z in Z]
        Ls = [loss(r) for r in run(ths, TARGETS, tau, fs)]
        order = np.argsort(Ls)
        if Ls[order[0]] < best[0]:
            best = (Ls[order[0]], ths[order[0]])
        el = Z[order[:max(2, a.pop // 4)]]
        mean, std = 0.7 * el.mean(0) + 0.3 * mean, np.maximum(0.7 * el.std(0) + 0.3 * std, 0.02)
        print(f"gen {gen:2d} loss {Ls[order[0]]:.3f} best {best[0]:.3f}", flush=True)
    th = best[1]
    res = run([th], TARGETS + [(n, c, None, s) for n, c, s in REPORT_ONLY], tau, fs)[0]
    lines = ["# Flame spread: simulation vs. NASA", "",
             "Generated by `python -m flame.spread`. Spread speeds are converted with the time and length scales fitted "
             f"by the main calibration (tau = {tau:.2f} real s per sim s, 1 cell = {10 / (fs * tau):.2f} mm), so they "
             "are predictions, not rescaled. Thin = 100 µm film or fabric, modelled as a thin strip.", "",
             "| Case | NASA | Simulation | Match | Source |", "|---|---|---|---|---|"]
    hits = 0
    for (name, _, tgt, src), r in zip(TARGETS + [(n, c, None, s) for n, c, s in REPORT_ONLY], res):
        sim = ("burns" if r["burns"] else "goes out") + (f", {r['mm_s']:.2f} mm/s" if r["mm_s"] else "")
        if tgt is None:
            nasa, ok = src, "(not fitted)"
            src = "BASS-II Summary Report p. 50"
        elif tgt[0] == "speed":
            nasa = f"{tgt[1]} mm/s"
            good = r["mm_s"] is not None and abs(np.log(r["mm_s"] / tgt[1])) <= np.log(tgt[2])
            ok, hits = ("yes" if good else "no"), hits + good
        else:
            nasa = "burns" if tgt[1] else "goes out"
            good = r["burns"] == tgt[1]
            ok, hits = ("yes" if good else "no"), hits + good
        lines.append(f"| {name} | {nasa} | {sim} | {ok} | {src} |")
    lines += ["", f"**{hits} of {len(TARGETS)}** NASA targets matched (speeds within ×1.3). These targets were used to fit "
              "the five spread knobs, so this shows the model *can* reproduce them, not that it predicts new cases.", ""]
    open(REPORT, "w").write("\n".join(lines))
    print("\n".join(lines))
    j = json.load(open(PARAMS_JSON)) if os.path.exists(PARAMS_JSON) else {"theta": dict(THETA)}
    j["theta"].update({k: round(th[k], 5) for k in KNOBS})
    j["spread"] = {"targets_matched": hits, "targets": len(TARGETS), "loss": best[0], "mm_per_cell": 10 / (fs * tau)}
    with open(PARAMS_JSON, "w") as f:
        json.dump(j, f, indent=1)


if __name__ == "__main__":
    main()
