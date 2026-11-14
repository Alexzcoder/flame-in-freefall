"""Nearest real experiments to the physics engine's current slider settings.

    python3 -m ranking.nearest --o2 0.30 --pressure 70.3 --flow 10 --phase solid

    from ranking.nearest import nearest_runs
    nearest_runs(ds, o2_frac=0.30, pressure_kpa=70.3, flow_cm_s=10, fuel_phase="solid")

Uses the same similarity as rank.py. Returns the closest runs plus a coverage verdict
("well covered" / "sparse" / "no nearby data") so the UI can warn when the simulator is extrapolating.
"""
import argparse

from flame.schema import Dataset

from .rank import CLOSE, run_similarity
from .scenarios import custom

WELL_COVERED = 10   # >= this many close runs -> "well covered"
PARTIAL = 0.10      # similarity between PARTIAL and CLOSE -> "partial match"; below -> "not near"


def _gaps(run, sc):
    """Plain-language list of which settings differ from this run, biggest first."""
    a, out = run.conditions.atmosphere, []
    d = (sc.o2_frac - a.o2_frac) * 100
    if abs(d) >= 2:
        out.append((abs(d) / (sc.o2_tol * 100), f"oxygen is {abs(d):.0f} points {'higher' if d > 0 else 'lower'} than this run "
                                                 f"({sc.o2_frac * 100:.0f}% vs {a.o2_frac * 100:.0f}%)"))
    if a.pressure_kpa:
        r = sc.pressure_kpa / a.pressure_kpa - 1
        if abs(r) >= 0.10:
            out.append((abs(r) / 0.2, f"pressure is {abs(r) * 100:.0f}% {'higher' if r > 0 else 'lower'} "
                                      f"({sc.pressure_kpa / 6.895:.1f} vs {a.pressure_kpa / 6.895:.1f} psi)"))
    else:
        out.append((1.0, "this run's pressure is unknown"))
    v = run.conditions.flow.velocity_cm_s
    if v is not None and abs(sc.flow_cm_s - v) >= 5:
        dv = sc.flow_cm_s - v
        out.append((abs(dv) / sc.flow_tol, f"airflow is {abs(dv):.0f} cm/s {'faster' if dv > 0 else 'slower'} "
                                           f"({sc.flow_cm_s:g} vs {v:g} cm/s)"))
    return [t for _, t in sorted(out, reverse=True)]


def _match_label(sim, gaps):
    if sim >= CLOSE:
        return "near", None
    if sim >= PARTIAL:
        return "partial", "Partial match: " + "; ".join(gaps[:2]) + "."
    return "far", "Not near your settings: " + "; ".join(gaps[:2]) + ". Use with caution."


def _summary(run, sim, acronyms, sc):
    a, o = run.conditions.atmosphere, run.outcome
    label, warning = _match_label(sim, _gaps(run, sc))
    return {
        "match": label,          # "near" | "partial" | "far"
        "warning": warning,      # None when near
        "differences": _gaps(run, sc),
        "run_id": run.id, "investigation": run.investigation, "acronym": acronyms.get(run.investigation, run.investigation),
        "similarity": round(sim, 3),
        "fuel": run.conditions.fuel.name, "fuel_phase": run.conditions.fuel.phase,
        "o2_pct": round(a.o2_frac * 100, 1) if a.o2_frac is not None else None,
        "pressure_kpa": a.pressure_kpa, "flow_cm_s": run.conditions.flow.velocity_cm_s,
        "assumed": run.assumed,
        "has_outcome": run.has_outcome,
        "outcome": {k: v for k, v in {"ignited": o.ignited, "result": o.result, "burn_time_s": o.burn_time_s,
                                      "censored": o.censored, "spread_rate_mm_s": o.spread_rate_mm_s,
                                      "burning_rate_mm2_s": o.burning_rate_mm2_s}.items() if v is not None},
        "media": run.media[:3],
    }


def nearest_runs(ds, o2_frac, pressure_kpa, flow_cm_s=10.0, gravity_g=0.0, fuel_phase=None, k=5):
    sc = custom(o2_frac, pressure_kpa, gravity_g, flow_cm_s)
    acr = {i.id: i.acronym for i in ds.investigations}
    pool = [r for r in ds.runs if fuel_phase is None or r.conditions.fuel.phase == fuel_phase]
    # full weight here: an exact match is a match; assumed values are flagged per run instead
    scored = sorted(((s, r) for r in pool if (s := run_similarity(r, sc, assumed_weight=1.0)) is not None),
                    key=lambda t: t[0], reverse=True)
    n_close = sum(s >= CLOSE for s, _ in scored)
    n_assumed = sum(s >= CLOSE and bool(r.assumed) for s, r in scored)

    if n_close >= WELL_COVERED:
        verdict, msg = "well_covered", f"{n_close} real experiments were run near these conditions."
    elif n_close > 0:
        verdict, msg = "sparse", f"Only {n_close} real experiment(s) near these conditions; treat predictions with care."
    else:
        verdict, msg = "no_data", ("No real experiments near these conditions. The simulator is extrapolating; "
                                   "the closest runs below are still far away.")
    if n_assumed:
        msg += f" {n_assumed} of them have assumed (not measured) cabin pressure or O2."
    what = f"{fuel_phase} fuels" if fuel_phase else "all fuels"
    return {
        "query": {"o2_pct": round(o2_frac * 100, 1), "pressure_kpa": pressure_kpa, "flow_cm_s": flow_cm_s,
                  "gravity_g": gravity_g, "fuel_phase": fuel_phase},
        "coverage": verdict, "message": f"{msg} (compared against {what})",
        "n_close": n_close,
        "warning": None if n_close else ("No experiment is near these settings. The closest ones are shown, "
                                         "but they were run under different conditions."),
        "matches": [_summary(r, s, acr, sc) for s, r in scored[:k]],
        "caveat": "All PSI data is microgravity." if gravity_g > 0 else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--o2", type=float, required=True, help="O2 mole fraction, e.g. 0.30")
    ap.add_argument("--pressure", type=float, required=True, help="kPa, e.g. 70.3 (= 10.2 psi)")
    ap.add_argument("--flow", type=float, default=10.0)
    ap.add_argument("--gravity", type=float, default=0.0)
    ap.add_argument("--phase", choices=["solid", "liquid", "gas"])
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--data", default="dataset/flame_runs.json")
    a = ap.parse_args()
    out = nearest_runs(Dataset.from_json(a.data), a.o2, a.pressure, a.flow, a.gravity, a.phase, a.k)
    print(f"[{out['coverage']}] {out['message']}")
    if out["warning"]:
        print(f"  WARNING: {out['warning']}")
    for m in out["matches"]:
        print(f"  {m['match']:7} {m['similarity']:.2f}  {m['acronym']:12} {m['run_id']:22} {m['fuel']:10} "
              f"O2 {m['o2_pct']}%  p {m['pressure_kpa']} kPa  flow {m['flow_cm_s']}  -> {m['outcome'] or 'no outcome recorded'}")
        if m["warning"]:
            print(f"          ! {m['warning']}")


if __name__ == "__main__":
    main()
