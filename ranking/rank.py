"""Relevance ranking: which investigations matter most for a given habitat?

    python3 -m ranking.rank moon_base
    python3 -m ranking.rank moon_base --focus prevention

Score (0-100) = 50% condition match + 20% labelled data + 20% cabin relevance + 10% fire-safety focus.
Everything is computed from the dataset, so every number in `reasons` can be checked.
"""
import argparse
import math

from flame.schema import Dataset

from . import profiles as P
from .scenarios import SCENARIOS, Scenario

WEIGHTS = {"condition_match": 0.50, "labelled_data": 0.20, "cabin_relevance": 0.20, "safety_focus": 0.10}
TOP_K = 5          # condition match = mean similarity of the K closest runs
CLOSE = 0.5        # similarity at which a run counts as "close"
ASSUMED_WEIGHT = 0.5


def run_similarity(run, sc: Scenario, assumed_weight=ASSUMED_WEIGHT):
    """0..1, how close one run's conditions are to the scenario. None if not comparable."""
    a = run.conditions.atmosphere
    if run.conditions.o2_location != "ambient" or a.o2_frac is None:
        return None
    z = ((a.o2_frac - sc.o2_frac) / sc.o2_tol) ** 2
    z += (math.log(a.pressure_kpa / sc.pressure_kpa) / sc.p_tol_log) ** 2 if a.pressure_kpa else 1.0  # unknown = 1 sigma
    v = run.conditions.flow.velocity_cm_s
    z += ((v - sc.flow_cm_s) / sc.flow_tol) ** 2 if v is not None else 1.0
    sim = math.exp(-0.5 * z)
    if any(f in run.assumed for f in ("conditions.atmosphere.o2_frac", "conditions.atmosphere.pressure_kpa")):
        sim *= assumed_weight
    return sim


def _pct(x):
    return f"{x * 100:.0f}%"


def score_investigation(prof, sc: Scenario, focus=None):
    sims = sorted(((s, r) for r in prof["_runs"] if (s := run_similarity(r, sc)) is not None),
                  key=lambda t: t[0], reverse=True)
    top = [s for s, _ in sims[:TOP_K]] + [0.0] * max(0, TOP_K - len(sims))
    match = sum(top) / TOP_K if sims else 0.0
    close = [(s, r) for s, r in sims if s >= CLOSE]
    nearish = [r for s, r in sims if s >= 0.3]
    labelled = (sum(r.has_outcome for r in nearish) / len(nearish)) if nearish else 0.0

    prior = P.CATEGORY_PRIOR.get(prof["category"], 0.4)
    comps = {"condition_match": match, "labelled_data": labelled, "cabin_relevance": prior,
             "safety_focus": prof["safety_focus"]}
    total = sum(WEIGHTS[k] * v for k, v in comps.items())

    reasons, caveats = [], []
    if not prof["normalized"]:
        caveats.append(f"No run-level data in the dataset ({prof['note']}); ranked on its description only.")
    elif not sims:
        caveats.append("No runs with ambient O2 to compare against this habitat.")
    else:
        reasons.append(f"{len(close)} of {len(sims)} runs are close to {sc.name} conditions"
                       if close else f"closest run is still far from {sc.name} conditions "
                       f"(similarity {math.floor(sims[0][0] * 100) / 100:.2f}, close = {CLOSE:.2f}+)")
        if nearish:
            reasons.append(f"{_pct(labelled)} of the nearby runs have a measured outcome")
    reasons.append(P.CATEGORY_WHY.get(prof["category"], ""))
    if focus:
        reasons.append(f"{'covers' if focus in prof['pillars'] else 'does not cover'} {focus}")
    if prof["share_assumed"]:
        caveats.append(f"{_pct(prof['share_assumed'])} of its runs have assumed (not measured) cabin pressure or O2; "
                       "those runs count half.")
    if sc.gravity_g > 0:
        caveats.append("All data is microgravity; partial-gravity behaviour is bounded, not measured.")

    best = [{"run_id": r.id, "similarity": round(s, 3),
             "o2_pct": round(r.conditions.atmosphere.o2_frac * 100, 1),
             "pressure_kpa": r.conditions.atmosphere.pressure_kpa,
             "flow_cm_s": r.conditions.flow.velocity_cm_s,
             "fuel": r.conditions.fuel.name, "has_outcome": r.has_outcome} for s, r in sims[:3]]

    return {
        "id": prof["id"], "acronym": prof["acronym"], "title": prof["title"], "category": prof["category"],
        "pillars": prof["pillars"], "score": round(total * 100, 1),
        "components": {k: round(v, 3) for k, v in comps.items()},
        "n_runs": prof["n_runs"], "n_close_runs": len(close), "closest_runs": best,
        "reasons": [x for x in reasons if x], "caveats": caveats,
    }


def rank(ds, scenario, focus=None, profiles=None):
    """Rank every investigation for a scenario. Returns a JSON-serialisable dict."""
    sc = SCENARIOS[scenario] if isinstance(scenario, str) else scenario
    profs = profiles or P.build(ds)
    # with a focus, investigations covering it come first, then the rest, each by score
    results = sorted((score_investigation(p, sc, focus) for p in profs.values()),
                     key=lambda r: (focus is None or focus in r["pillars"], r["score"]), reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    near = sum(r["n_close_runs"] for r in results)
    return {"scenario": sc.to_dict(), "focus": focus, "weights": WEIGHTS, "total_close_runs": near,
            "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=list(SCENARIOS))
    ap.add_argument("--focus", choices=["prevention", "detection", "suppression"])
    ap.add_argument("--data", default="dataset/flame_runs.json")
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    out = rank(Dataset.from_json(a.data), a.scenario, a.focus)
    print(f"{out['scenario']['name']}: {out['scenario']['o2_pct']}% O2, {out['scenario']['pressure_psi']} psi"
          f"{' | focus: ' + a.focus if a.focus else ''}\n")
    for r in out["results"][: a.top]:
        print(f"{r['rank']:2}. {r['acronym']:22} {r['score']:5.1f}  close runs: {r['n_close_runs']}")
        for x in r["reasons"]:
            print(f"      + {x}")
        for x in r["caveats"]:
            print(f"      ! {x}")


if __name__ == "__main__":
    main()
