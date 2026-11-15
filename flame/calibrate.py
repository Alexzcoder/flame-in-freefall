"""Fit the flame simulation's physics knobs (flame/sim.py THETA) to real NASA runs.

Targets (training days only; test days are held out and reported separately):
  * CFI-G gas flames (table outcomes, every run with a result): no ignition / extinction after t seconds / still
    burning when the crew stopped the run at t seconds. The simulation's time is converted to seconds with one
    fitted factor tau. Per-run loss 0..1: wrong ignition = 1, extinction time off by a factor of 4 or more = 1,
    flame dies before the crew stopped a still-burning run = up to 1.
  * BASS-II solids (video): rank agreement of flame aspect ratio (how stretched by the airflow), weight 0.25.
  * Solid fate, weight 0.5. BASS-II: flames burned at the initial airflow and went out when the crew turned the fan
    down (`extra.air_display`, e.g. "5 down to ext"): keep burning at the initial flow, go out at the last fan setting
    (0 when not logged). SAFFIRE: burned steadily (~21.5 % O2, 20 cm/s). Burning and going out weigh half each.
Search: cross-entropy method over a box, 16 candidates per generation, all candidates x runs in one GPU batch.

    python -m flame.calibrate --gens 30          # → public/station/simparams.json + data/calib/log.jsonl
"""
import argparse, json, multiprocessing as mp, os, re, time

import numpy as np
import torch

from flame.media import ROOT
from flame.shape import clip_measures
from flame.shape_eval import real_measures, runs_by_id, sim_conditions, spearman
from flame.sim import DT, PARAMS_JSON, THETA, Sim

LOG = os.path.join(ROOT, "data", "calib", "log.jsonl")
SECONDS, EVERY, BATCH = 30.0, 0.5, 1024
TEST_DAYS_GAS = {"3", "7", "11"}  # CFI-G test days held out (~20% of runs)
# knob: (low, high, log scale)
BOX = {"k": (4, 64, 1), "heat": (0.5, 4, 1), "cool": (0.1, 3, 1), "ign": (0.15, 0.7, 0), "dif_o2": (0.05, 0.24, 0),
       "dif_fuel": (0.05, 0.24, 0), "cond": (0.02, 0.2, 0), "emit_scale": (0.2, 5, 1), "inv_fuel": (0.2, 5, 1),
       "inv_o2": (0.2, 5, 1), "tad_exp": (0, 6, 0), "flow_scale": (0.3, 3, 1), "anchor": (0.0, 0.8, 0),
       "emit0": (0.0, 1.5, 0)}
NAMES = list(BOX)


def to_theta(z):
    """z in [0, 1]^d → knob dict."""
    th = {}
    for (k, (lo, hi, lg)), v in zip(BOX.items(), np.clip(z, 0, 1)):
        th[k] = float(np.exp(np.log(lo) + v * (np.log(hi) - np.log(lo))) if lg else lo + v * (hi - lo))
    return th


def from_theta(th):
    return np.array([(np.log(th[k]) - np.log(lo)) / (np.log(hi) - np.log(lo)) if lg else (th[k] - lo) / (hi - lo)
                     for k, (lo, hi, lg) in BOX.items()]).clip(0, 1)


def datasets():
    """→ gas rows (CFI-G with outcome), solid rows (BASS-II video, not glare), each with split = train/test."""
    runs, real = runs_by_id(), real_measures()
    gas, solid = [], []
    for rid, r in runs.items():
        if r["investigation"] != "PSI-159" or r["outcome"]["result"] not in ("extinction", "terminated", "no_ignition"):
            continue
        c, _ = sim_conditions(r)
        if c is None:
            continue
        c["tad_k"] = r["extra"].get("tad_k")
        gas.append({"id": rid, "cond": c, "result": r["outcome"]["result"], "t": r["outcome"]["burn_time_s"],
                    "split": "test" if r["extra"].get("day") in TEST_DAYS_GAS else "train"})
    dates = sorted({runs[i]["date"] or "" for i in real if i.startswith("PSI-25/")})
    test_dates = set(dates[::5])  # every 5th test day held out
    for rid, m in real.items():
        if not rid.startswith("PSI-25/") or m.get("lit_scene") or not m.get("aspect"):
            continue
        c, _ = sim_conditions(runs[rid])
        if c is not None:
            solid.append({"id": rid, "cond": c, "aspect": m["aspect"],
                          "split": "test" if (runs[rid]["date"] or "") in test_dates else "train"})
    fate = []
    for rid, r in runs.items():
        c = r["conditions"]
        if r["investigation"] in ("PSI-98", "PSI-99") and r["outcome"]["burn_time_s"] and \
                c["fuel"]["name"] in ("sibal", "pmma", "pmma+nomex"):  # SAFFIRE: burned steadily
            fate.append({"id": rid, "burns": True, "cond": dict(
                gravity_g=0.0, o2=c["atmosphere"]["o2_frac"], pressure_kpa=101.325,
                flow_cm_s=c["flow"]["velocity_cm_s"], fuel="fabric" if c["fuel"]["name"] == "sibal" else "pmma")})
        elif r["investigation"] == "PSI-25" and r["outcome"]["result"] == "extinction":
            # BASS-II: the flame burned at the initial airflow; the crew then turned the fan DOWN until it went out
            # ("5 down to ext", "5 3 2 ext"). Blowoff and unclear entries are left out.
            txt = str(r["extra"].get("air_display") or "")
            if "blowoff" in txt or "pots" in txt or not any(w in txt for w in ("down", "decr", "ext")):
                continue
            cond = sim_conditions(r)[0]
            if not cond:
                continue
            nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt)]
            last = 1.0066 * nums[-1] if len(nums) > 1 else 0.0  # fan display → cm/s (NASA calibration sheet)
            fate.append({"id": rid, "burns": True, "cond": cond})
            fate.append({"id": rid + "@low", "burns": False, "cond": {**cond, "flow_cm_s": last}})
    return gas, solid, fate


def simulate(rows, thetas, seconds=SECONDS):
    """rows × thetas → per (theta, row): alive series (n,), and camera frames for rows marked 'frames'."""
    jobs = [(ti, ri) for ti in range(len(thetas)) for ri in range(len(rows))]
    alive = np.zeros((len(thetas), len(rows), int(round(seconds / EVERY))), bool)
    frames = {}
    for b in range(0, len(jobs), BATCH):
        chunk = jobs[b:b + BATCH]
        pad = BATCH - len(chunk)  # fixed batch size: the compiled step is reused, not recompiled
        conds = [rows[ri]["cond"] for _, ri in chunk] + [rows[chunk[-1][1]]["cond"]] * pad
        ths = [thetas[ti] for ti, _ in chunk] + [thetas[chunk[-1][0]]] * pad
        sim = Sim(conds, ths)
        want = torch.tensor([bool(rows[ri].get("frames")) for _, ri in chunk] + [False] * pad)
        idx = torch.nonzero(want).flatten()
        fr, k, nxt = [], 0, EVERY
        for _ in range(int(round(seconds / DT))):
            sim.step()
            if sim.time + 1e-9 >= nxt:
                img = sim.render("camera")
                a = ((img.mean(-1) > 0.12).sum((1, 2)) >= 4).cpu().numpy()
                for j, (ti, ri) in enumerate(chunk):
                    alive[ti, ri, k] = a[j]
                if len(idx) and nxt <= 20.0:
                    fr.append((img[idx.to(img.device)] * 255).to(torch.uint8).cpu())
                k, nxt = k + 1, nxt + EVERY
        if len(idx):
            fr = torch.stack(fr, 1).numpy()
            for j, i in enumerate(idx.tolist()):
                frames[chunk[i]] = fr[j]
    return alive, frames


def _aspect(f):
    m = clip_measures(f[4:], skip=0)  # skip the first 2 s (igniter)
    return m["aspect"]


def gas_loss(alive, rows, tau):
    """alive (n_rows, n_t) for one theta; tau = real seconds per sim second → mean loss, details."""
    t_sim = (np.arange(alive.shape[1]) + 1) * EVERY
    late = t_sim > 1.5  # after the igniter
    L, pred = [], []
    for a, r in zip(alive, rows):
        lit = a[late]
        ever = lit.any()
        dies = ever and not lit[-1]
        t_die = tau * t_sim[late][np.nonzero(lit)[0].max()] if dies else None
        if r["result"] == "no_ignition":
            L.append(0.0 if not ever else 1.0)
        elif not ever:
            L.append(1.0)
        elif r["result"] == "extinction":
            te = max(r["t"] or 1.0, 0.5)
            L.append(min(1.0, abs(np.log(t_die / te)) / np.log(4)) if dies else 1.0)
        else:  # terminated: still burning at t, so the simulated flame must last at least that long
            tc = max(r["t"] or 1.0, 0.5)
            L.append(min(1.0, max(0.0, np.log(tc / t_die)) / np.log(4)) if dies else 0.0)
        pred.append("no_ignition" if not ever else "extinction" if dies else "terminated")
    return float(np.mean(L)), pred


def best_tau(alive, rows):
    taus = np.exp(np.linspace(np.log(0.3), np.log(60), 40))
    losses = [gas_loss(alive, rows, t)[0] for t in taus]
    i = int(np.argmin(losses))
    return float(taus[i]), losses[i]


def fate_loss(alive, rows):
    """Solid fate: half the weight on runs that went out, half on runs that kept burning. Smooth: share of the last
    quarter of the simulated time with a visible flame (pass/fail gives the search nothing to climb)."""
    burning_at_end = alive[:, -alive.shape[1] // 4:].mean(1)
    miss_out = [b for b, r in zip(burning_at_end, rows) if not r["burns"]]
    miss_burn = [1 - b for b, r in zip(burning_at_end, rows) if r["burns"]]
    return 0.5 * float(np.mean(miss_out) if miss_out else 0) + 0.5 * float(np.mean(miss_burn) if miss_burn else 0)


def objective(thetas, gas, solid, pool, fate=()):
    rows = gas + [{**s, "frames": True} for s in solid] + list(fate)
    alive, frames = simulate(rows, thetas)
    out = []
    keys = [(ti, len(gas) + si) for ti in range(len(thetas)) for si in range(len(solid))]
    aspects = pool.map(_aspect, [frames[k] for k in keys]) if solid else []
    for ti in range(len(thetas)):
        tau, gl = best_tau(alive[ti, :len(gas)], gas)
        asp = aspects[ti * len(solid):(ti + 1) * len(solid)]
        ok = [(a, s["aspect"]) for a, s in zip(asp, solid) if a is not None]
        rho = spearman(*zip(*ok)) if len(ok) > 4 else None
        fl = fate_loss(alive[ti, len(gas) + len(solid):], fate) if fate else 0.0
        out.append({"loss": gl + 0.25 * (1 - (rho or 0)) + 0.5 * fl, "gas_loss": gl, "tau": tau, "aspect_rho": rho,
                    "fate_loss": fl})
    return out


def report(theta, tau, gas, solid, pool, fate=()):
    """Metrics per split for one theta (+ solid fate on all fate runs: too few to split)."""
    res = {}
    if fate:
        alive, _ = simulate(list(fate), [theta])
        end = alive[0][:, -2:].all(1)
        res["solid_fate"] = {"went_out_runs": sum(not r["burns"] for r in fate),
                             "sim_goes_out": int(sum(not e for e, r in zip(end, fate) if not r["burns"])),
                             "burned_runs": sum(r["burns"] for r in fate),
                             "sim_keeps_burning": int(sum(e for e, r in zip(end, fate) if r["burns"]))}
    for split in ("train", "test"):
        g = [r for r in gas if r["split"] == split]
        s = [r for r in solid if r["split"] == split]
        rows = g + [{**x, "frames": True} for x in s]
        alive, frames = simulate(rows, [theta])
        gl, pred = gas_loss(alive[0, :len(g)], g, tau)
        labels = ("extinction", "no_ignition", "terminated")
        recall = {l: float(np.mean([p == l for p, r in zip(pred, g) if r["result"] == l])) for l in labels}
        conf = {l: {p: sum(r["result"] == l and q == p for q, r in zip(pred, g)) for p in labels} for l in labels}
        asp = pool.map(_aspect, [frames[(0, len(g) + i)] for i in range(len(s))]) if s else []
        ok = [(a, x["aspect"]) for a, x in zip(asp, s) if a is not None]
        # extinction time error for runs both real and simulated flames went out
        t_sim = (np.arange(alive.shape[2]) + 1) * EVERY
        errs = []
        for a, r in zip(alive[0, :len(g)], g):
            lit = a[t_sim > 1.5]
            if r["result"] == "extinction" and lit.any() and not lit[-1]:
                errs.append(abs(np.log(tau * t_sim[t_sim > 1.5][np.nonzero(lit)[0].max()] / max(r["t"] or 1, 0.5))))
        res[split] = {"gas_runs": len(g), "gas_loss": gl, "balanced_accuracy": float(np.mean(list(recall.values()))),
                      "recall": recall, "confusion": conf,
                      "extinction_time_factor_median": float(np.exp(np.median(errs))) if errs else None,
                      "solid_runs": len(s), "aspect_rho": spearman(*zip(*ok)) if len(ok) > 4 else None}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=30)
    ap.add_argument("--pop", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--start", default='{"anchor": 0.4, "ign": 0.5, "cool": 0.6, "dif_o2": 0.1}',
                    help="knobs to start the search from (JSON; rest = website defaults). Default: a corner found by a "
                         "grid where all 31 solid fate targets are right")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    gas, solid, fate = datasets()
    tr_g, tr_s = [r for r in gas if r["split"] == "train"], [r for r in solid if r["split"] == "train"]
    print(f"gas {len(tr_g)} train / {len(gas) - len(tr_g)} test, solid {len(tr_s)} train / {len(solid) - len(tr_s)} test, "
          f"solid fate {len(fate)} (all used: too few to split)", flush=True)
    rng = np.random.default_rng(a.seed)
    base = {**{k: THETA[k] for k in NAMES}, **json.loads(a.start)}
    mean, std = from_theta(base), np.full(len(NAMES), 0.3)
    best = None
    with mp.Pool(min(24, os.cpu_count())) as pool:
        for gen in range(a.gens):
            t0 = time.time()
            Z = np.clip(mean + std * rng.standard_normal((a.pop, len(NAMES))), 0, 1)
            if gen == 0:
                Z[0] = mean  # the starting point is candidate 0
            if best is not None:
                Z[-1] = best["z"]  # keep the best so far (re-evaluated: it is deterministic, so this is a check)
            thetas = [{**THETA, **to_theta(z)} for z in Z]
            res = objective(thetas, tr_g, tr_s, pool, fate)
            order = np.argsort([r["loss"] for r in res])
            elite = Z[order[:max(2, a.pop // 4)]]
            mean = 0.7 * elite.mean(0) + 0.3 * mean
            std = np.maximum(0.7 * elite.std(0) + 0.3 * std, 0.02)
            top = res[order[0]]
            if best is None or top["loss"] < best["loss"]:
                best = {**top, "z": Z[order[0]], "theta": thetas[order[0]]}
            rec = {"gen": gen, "best_loss": best["loss"], "gen_best": top, "s": round(time.time() - t0),
                   "theta": {k: round(v, 4) for k, v in thetas[order[0]].items()}}
            with open(LOG, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"gen {gen:2d} loss {top['loss']:.3f} (gas {top['gas_loss']:.3f}, tau {top['tau']:.2f}, "
                  f"aspect rho {top['aspect_rho']}, fate {top['fate_loss']:.2f}) best {best['loss']:.3f}  {rec['s']} s", flush=True)
        base_rep = report({**THETA}, best_tau(simulate(tr_g, [dict(THETA)])[0][0], tr_g)[0], gas, solid, pool, fate)
        rep = report(best["theta"], best["tau"], gas, solid, pool, fate)
    out = {"theta": {k: round(v, 5) for k, v in best["theta"].items()}, "tau_real_s_per_sim_s": best["tau"],
           "fit": rep, "website_defaults_fit": base_rep, "generations": a.gens, "population": a.pop,
           "note": "Fitted by flame/calibrate.py to CFI-G outcomes (gas) and BASS-II flame aspect (solid). "
                   "Test days held out; see dataset/shape_eval.md."}
    with open(PARAMS_JSON, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({"calibrated": rep, "website_defaults": base_rep}, indent=1))


if __name__ == "__main__":
    main()
