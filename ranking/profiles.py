"""Per-investigation summaries built from the dataset (read-only). Shared by rank.py and compare.py."""
import math

PILLAR_WORDS = {
    "suppression": ("extinguish", "suppress", "suppression", "extinction"),
    "detection": ("smoke", "detect", "aerosol", "dust"),
    "prevention": ("flammab", "flame spread", "spread", "material", "ignition", "fire safety", "burning"),
}
SAFETY_WORDS = ("fire safety", "spacecraft fire", "flammab", "extinguish", "suppress", "smoke", "detect",
                "flame spread", "spread", "material", "crew", "habitat")

# How directly each family of experiment maps onto a fire in a crew cabin
CATEGORY_PRIOR = {"solid": 1.0, "smoke": 0.9, "droplet": 0.6, "gaseous": 0.5, "other": 0.4}
CATEGORY_WHY = {
    "solid": "burns solid materials (fabrics, plastics), the closest match to a cabin fire",
    "smoke": "studies smoke, which feeds directly into fire detection",
    "droplet": "burns liquid fuel droplets: useful for suppression and burning-rate physics",
    "gaseous": "burns gaseous fuels: fundamental flame physics, less direct for cabin materials",
    "other": "modelling or supporting study",
}

OUTCOME_FIELDS = ["ignited", "result", "burn_time_s", "spread_rate_mm_s", "burning_rate_mm2_s",
                  "extinction_diameter_mm", "flame_length_mm", "flame_temperature_k"]


def text_of(inv):
    return f"{inv.title} {inv.objective or ''}".lower()


def pillars(inv):
    t = text_of(inv)
    found = [p for p, words in PILLAR_WORDS.items() if p != "detection" and any(w in t for w in words)]
    if inv.category == "smoke":  # detection only from smoke studies; keywords give false positives
        found.append("detection")
    if inv.category == "solid" and "prevention" not in found:
        found.append("prevention")
    return found or ["prevention"]


def keyword_score(inv):
    t = text_of(inv)
    hits = sum(w in t for w in SAFETY_WORDS)
    return min(1.0, hits / 4)


def measured(run, field):
    """True if a condition value exists and was not filled in by assumption."""
    return f"conditions.atmosphere.{field}" not in run.assumed


def _range(vals):
    vals = [v for v in vals if v is not None]
    return [round(min(vals), 4), round(max(vals), 4)] if vals else None


def build(ds):
    """investigation id -> profile dict."""
    by_inv = {}
    for r in ds.runs:
        by_inv.setdefault(r.investigation, []).append(r)
    out = {}
    for inv in ds.investigations:
        runs = by_inv.get(inv.id, [])
        amb = [r for r in runs if r.conditions.o2_location == "ambient"]
        out[inv.id] = {
            "id": inv.id, "acronym": inv.acronym, "title": inv.title, "category": inv.category,
            "hardware": inv.hardware, "platform": inv.platform, "doi": inv.doi,
            "objective": inv.objective, "normalized": inv.normalized, "note": inv.note,
            "n_publications": len(inv.publications),
            "pillars": pillars(inv),
            "safety_focus": keyword_score(inv),
            "n_runs": len(runs),
            "n_inverse_flame_runs": len(runs) - len(amb),
            "n_with_outcome": sum(r.has_outcome for r in runs),
            "fuels": sorted({r.conditions.fuel.name for r in runs} - {"unknown"}),
            "fuel_phases": sorted({r.conditions.fuel.phase for r in runs}),
            # measured values only (assumed cabin values are excluded from ranges)
            "o2_frac_range": _range([r.conditions.atmosphere.o2_frac for r in amb if measured(r, "o2_frac")]),
            "pressure_kpa_range": _range([r.conditions.atmosphere.pressure_kpa for r in amb if measured(r, "pressure_kpa")]),
            "flow_cm_s_range": _range([r.conditions.flow.velocity_cm_s for r in runs]),
            "outcome_fields": [f for f in OUTCOME_FIELDS if any(getattr(r.outcome, f) is not None for r in runs)],
            "share_assumed": round(sum(bool(r.assumed) for r in runs) / len(runs), 2) if runs else None,
            "_runs": amb,  # internal, stripped before export
        }
    return out


def public(profile):
    return {k: v for k, v in profile.items() if not k.startswith("_")}


def overlap(a, b):
    """Overlap of two [lo, hi] ranges, or None."""
    if not a or not b:
        return None
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return [lo, hi] if lo <= hi else None


def log_ratio(a, b):
    return abs(math.log(a / b))
