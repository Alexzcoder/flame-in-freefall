"""Data-driven outcome models trained on NASA run tables, with honest grouped cross-validation.

  CFI-G (PSI-159, gas flames, 331 runs): outcome no_ignition / extinction / still burning when stopped;
          time to extinction (10th / 50th / 90th percentile).
  FLEX (PSI-69, fuel droplets, 274 runs): extinction vs. burnout (disruption runs are censored, left out);
          burning rate K (mm^2/s); extinction diameter as a share of the starting diameter.
Folds are whole test days (CFI-G `extra.day`, FLEX `date`), so runs from one session never sit in both train and test.
Every prediction carries `in_range`: is the question inside the conditions NASA actually tested (distance to the
5 nearest training runs vs. what is typical inside the data)?

    python -m flame.predict        # → dataset/predict_eval.md + data/models/outcome_models.pkl
"""
import json, os, pickle

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors

from flame.media import ROOT

MODELS = os.path.join(ROOT, "data", "models", "outcome_models.pkl")
REPORT = os.path.join(ROOT, "dataset", "predict_eval.md")
GAS_FUELS, DROP_FUELS = ["ethane", "propane", "butane"], ["methanol", "heptane"]


def gas_features(c, extra):
    """CFI-G conditions → feature vector. Inverse flames: o2 = burner stream O2, fuel_frac = ambient fuel."""
    inv = c["o2_location"] == "burner_stream"
    flow = (extra.get("o2_flow_mg_s") if inv else c["fuel"]["flow_mg_s"]) or np.nan
    return [c["atmosphere"]["o2_frac"], c["atmosphere"]["pressure_kpa"], float(inv), c["fuel"]["fuel_frac"] or np.nan,
            flow, extra.get("tad_k") or np.nan, extra.get("zst") or np.nan,
            *[float(c["fuel"]["name"] == f) for f in GAS_FUELS]]


GAS_NAMES = ["o2", "pressure_kpa", "inverse", "fuel_frac", "flow_mg_s", "tad_k", "zst", *GAS_FUELS]


def drop_features(c):
    a = c["atmosphere"]
    return [a["o2_frac"], a["pressure_kpa"] or np.nan, a["he_frac"] or 0.0, a["co2_frac"] or 0.0,
            c["fuel"]["diameter_mm"] or np.nan, *[float(c["fuel"]["name"] == f) for f in DROP_FUELS]]


DROP_NAMES = ["o2", "pressure_kpa", "he", "co2", "d0_mm", *DROP_FUELS]


class Range:
    """Is a query inside the tested conditions? kNN distance in standardised features (missing → median)."""

    def __init__(self, X):
        self.med = np.nanmedian(X, 0)
        Xf = np.where(np.isnan(X), self.med, X)
        self.mu, self.sd = Xf.mean(0), Xf.std(0) + 1e-9
        Z = (Xf - self.mu) / self.sd
        self.nn = NearestNeighbors(n_neighbors=6).fit(Z)
        d, _ = self.nn.kneighbors(Z)
        self.limit = float(np.percentile(d[:, 1:].mean(1), 95))

    def __call__(self, X):
        Z = (np.where(np.isnan(X), self.med, X) - self.mu) / self.sd
        d, _ = self.nn.kneighbors(Z, n_neighbors=5)
        dist = d.mean(1)
        return dist <= self.limit, dist / self.limit


def load():
    runs = json.load(open(os.path.join(ROOT, "dataset", "flame_runs.json")))["runs"]
    gas = [r for r in runs if r["investigation"] == "PSI-159" and r["outcome"]["result"] in ("extinction", "terminated", "no_ignition")]
    drop = [r for r in runs if r["investigation"] == "PSI-69"]
    return gas, drop


def cv_classifier(X, y, groups, classes, folds=5):
    """→ out-of-fold predicted labels, balanced accuracy, majority baseline."""
    pred = np.empty(len(y), object)
    for tr, te in GroupKFold(folds).split(X, y, groups):
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0)
        pred[te] = m.fit(X[tr], y[tr]).predict(X[te])
    rec = {c: float(np.mean(pred[y == c] == c)) for c in classes if (y == c).any()}
    return pred, float(np.mean(list(rec.values()))), rec


def cv_quantiles(X, y, groups, folds=5):
    """Log-target quantile regression → out-of-fold q10/q50/q90, median abs error, interval coverage, baseline."""
    q = {a: np.empty(len(y)) for a in (0.1, 0.5, 0.9)}
    base = np.empty(len(y))
    for tr, te in GroupKFold(folds).split(X, y, groups):
        for a in q:
            m = HistGradientBoostingRegressor(loss="quantile", quantile=a, max_iter=300, learning_rate=0.05, random_state=0)
            q[a][te] = m.fit(X[tr], y[tr]).predict(X[te])
        base[te] = np.median(y[tr])
    # conformal widening (CQR): add the 80th percentile of how far real values fell outside the raw interval
    widen = float(np.quantile(np.maximum(q[0.1] - y, y - q[0.9]), 0.8))
    return q, {"mae": float(np.median(np.abs(q[0.5] - y))), "baseline_mae": float(np.median(np.abs(base - y))),
               "coverage_80_raw": float(np.mean((y >= q[0.1]) & (y <= q[0.9]))),
               "coverage_80": float(np.mean((y >= q[0.1] - widen) & (y <= q[0.9] + widen))), "widen": widen}


def fit_quantiles(X, y, widen):
    m = {a: HistGradientBoostingRegressor(loss="quantile", quantile=a, max_iter=300, learning_rate=0.05,
                                          random_state=0).fit(X, y) for a in (0.1, 0.5, 0.9)}
    return {**m, "widen": widen}


def main():
    gas, drop = load()
    report, models = {}, {}
    # ---- CFI-G
    X = np.array([gas_features(r["conditions"], r["extra"]) for r in gas], float)
    y = np.array([r["outcome"]["result"] for r in gas])
    g = np.array([r["extra"].get("day") or "?" for r in gas])
    classes = ["extinction", "no_ignition", "terminated"]
    _, bacc, rec = cv_classifier(X, y, g, classes)
    report["gas_outcome"] = {"runs": len(y), "balanced_accuracy": bacc, "recall": rec, "guessing": 1 / 3,
                             "counts": {c: int((y == c).sum()) for c in classes}}
    ext = y == "extinction"
    t = np.log(np.array([max(r["outcome"]["burn_time_s"] or 0.5, 0.5) for r in gas]))
    _, met = cv_quantiles(X[ext], t[ext], g[ext])
    report["gas_extinction_time"] = {"runs": int(ext.sum()), "median_factor_error": float(np.exp(met["mae"])),
                                     "baseline_factor_error": float(np.exp(met["baseline_mae"])),
                                     "coverage_80": met["coverage_80"]}
    models["gas"] = {"features": GAS_NAMES, "outcome": HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0).fit(X, y),
        "log_extinction_s": fit_quantiles(X[ext], t[ext], met["widen"]), "range": Range(X)}
    # ---- FLEX
    X = np.array([drop_features(r["conditions"]) for r in drop], float)
    y = np.array([r["outcome"]["result"] for r in drop])
    g = np.array([r["date"] or "?" for r in drop])
    keep = y != "disruption"  # droplet broke apart: outcome unknown (censored)
    _, bacc, rec = cv_classifier(X[keep], y[keep], g[keep], ["extinction", "burnout"])
    report["droplet_outcome"] = {"runs": int(keep.sum()), "balanced_accuracy": bacc, "recall": rec, "guessing": 0.5,
                                 "counts": {c: int((y[keep] == c).sum()) for c in ("extinction", "burnout")}}
    models["droplet"] = {"features": DROP_NAMES, "range": Range(X), "outcome": HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0).fit(X[keep], y[keep])}
    K = np.array([r["outcome"]["burning_rate_mm2_s"] or np.nan for r in drop])
    ok = ~np.isnan(K)
    q, met = cv_quantiles(X[ok], K[ok], g[ok])
    report["droplet_burning_rate"] = {"runs": int(ok.sum()), "median_abs_error_mm2_s": met["mae"],
                                      "baseline_mm2_s": met["baseline_mae"], "coverage_80": met["coverage_80"],
                                      "typical_K": float(np.median(K[ok]))}
    models["droplet"]["burning_rate_mm2_s"] = fit_quantiles(X[ok], K[ok], met["widen"])
    d0 = X[:, 4]
    de = np.array([r["outcome"]["extinction_diameter_mm"] if r["outcome"]["extinction_diameter_mm"] is not None else np.nan for r in drop])
    ok = ~np.isnan(de) & ~np.isnan(d0) & (y == "extinction")
    ratio = de[ok] / d0[ok]
    _, met = cv_quantiles(X[ok], ratio, g[ok])
    report["droplet_extinction_size"] = {"runs": int(ok.sum()), "median_abs_error": met["mae"],
                                         "baseline": met["baseline_mae"], "coverage_80": met["coverage_80"]}
    models["droplet"]["extinction_size_ratio"] = fit_quantiles(X[ok], ratio, met["widen"])
    os.makedirs(os.path.dirname(MODELS), exist_ok=True)
    with open(MODELS, "wb") as f:
        pickle.dump(models, f)
    md = markdown(report)
    open(REPORT, "w").write(md)
    json.dump(report, open(REPORT.replace(".md", ".json"), "w"), indent=1)
    print(md)


def markdown(r):
    go, gt = r["gas_outcome"], r["gas_extinction_time"]
    do, dk, dx = r["droplet_outcome"], r["droplet_burning_rate"], r["droplet_extinction_size"]
    pct = lambda d: ", ".join(f"{k} {v:.2f}" for k, v in d.items())
    return "\n".join([
        "# Outcome models: how well can NASA's run tables predict a flame?", "",
        "Generated by `python -m flame.predict`. Gradient-boosted trees, 5-fold cross-validation where each fold is a set "
        "of whole test days (a model never sees a run from the day it is scored on). 80% intervals from quantile models, "
        "widened by conformal calibration on the cross-validation errors (coverage shown is on the same folds, so it is "
        "slightly optimistic).", "",
        "| What is predicted | Runs | Model | Guessing / typical value | Notes |", "|---|---|---|---|---|",
        f"| Gas flame (CFI-G): no ignition / goes out / still burning when stopped | {go['runs']} | balanced accuracy **{go['balanced_accuracy']:.2f}** | {go['guessing']:.2f} | recall: {pct(go['recall'])} |",
        f"| Gas flame: seconds until it goes out | {gt['runs']} | typically off by ×**{gt['median_factor_error']:.2f}** | ×{gt['baseline_factor_error']:.2f} | 80% interval holds {gt['coverage_80']:.0%} |",
        f"| Droplet (FLEX): goes out vs. burns completely | {do['runs']} | balanced accuracy **{do['balanced_accuracy']:.2f}** | {do['guessing']:.2f} | recall: {pct(do['recall'])}; break-ups left out |",
        f"| Droplet burning rate K | {dk['runs']} | median error **{dk['median_abs_error_mm2_s']:.3f}** mm²/s | {dk['baseline_mm2_s']:.3f} | typical K {dk['typical_K']:.2f}; 80% interval holds {dk['coverage_80']:.0%} |",
        f"| Droplet size when the flame goes out (share of start size) | {dx['runs']} | median error **{dx['median_abs_error']:.3f}** | {dx['baseline']:.3f} | 80% interval holds {dx['coverage_80']:.0%} |",
        "", "Use only inside the tested conditions: each prediction says whether it is (`in_range`).", ""])


if __name__ == "__main__":
    main()
