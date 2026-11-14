"""Auto-generated comparison of 2-3 investigations: what is the same, what differs.

    python3 -m ranking.compare PSI-25 PSI-99
    python3 -m ranking.compare PSI-69 PSI-39 --llm      # adds an AI-written summary if ANTHROPIC_API_KEY is set

The structured part is computed from the dataset. The optional AI summary only rewrites those facts in prose.
"""
import argparse
import json

from flame.schema import Dataset

from . import llm
from . import profiles as P

ATM = 101.325


def _fmt_o2(r):
    return f"{r[0] * 100:.0f}-{r[1] * 100:.0f}% O2" if r else "O2 not recorded"


def _fmt_p(r):
    return f"{r[0] / ATM:.2f}-{r[1] / ATM:.2f} atm" if r else "pressure not recorded"


def _fmt_flow(r):
    if not r:
        return "flow not recorded"
    if r[0] == r[1] == 0:
        return "still air (0 cm/s)"
    return f"{r[0]:g} cm/s" if r[0] == r[1] else f"{r[0]:g}-{r[1]:g} cm/s"


def compare(ds, ids, use_llm=False, profiles=None):
    profs = profiles or P.build(ds)
    missing = [i for i in ids if i not in profs]
    if missing:
        raise KeyError(f"unknown investigation id(s): {missing}")
    ps = [profs[i] for i in ids]
    name = {p["id"]: p["acronym"] for p in ps}

    same, diff = [], []

    def compare_attr(label, key, fmt=lambda v: v or "unknown"):
        vals = {p["id"]: p[key] for p in ps}
        if len({json.dumps(v) for v in vals.values()}) == 1:
            same.append(f"Same {label}: {fmt(ps[0][key])}")
        else:
            diff.append(f"{label.capitalize()}: " + "; ".join(f"{name[i]} = {fmt(v)}" for i, v in vals.items()))

    compare_attr("category", "category")
    compare_attr("hardware", "hardware")
    compare_attr("platform", "platform")

    fuels = [set(p["fuels"]) for p in ps]
    common = set.intersection(*fuels) if all(fuels) else set()
    if common:
        same.append("Shared fuels: " + ", ".join(sorted(common)))
    if any(fuels):
        diff.append("Fuels: " + "; ".join(f"{p['acronym']} = {', '.join(p['fuels']) or 'none'}" for p in ps))

    for label, key, fmt in [("oxygen", "o2_frac_range", _fmt_o2), ("pressure", "pressure_kpa_range", _fmt_p),
                            ("airflow", "flow_cm_s_range", _fmt_flow)]:
        ranges = [p[key] for p in ps]
        ov = ranges[0]
        for r in ranges[1:]:
            ov = P.overlap(ov, r)
        if all(ranges) and ov:
            same.append(f"Overlapping {label}: {fmt(ov)}")
        diff.append(f"{label.capitalize()} tested: " + "; ".join(f"{p['acronym']} {fmt(p[key])}" for p in ps))

    outs = [set(p["outcome_fields"]) for p in ps]
    common_out = set.intersection(*outs)
    if common_out:
        same.append("Both measured: " + ", ".join(sorted(common_out)))
    diff.append("Measured outcomes: " + "; ".join(
        f"{p['acronym']} {', '.join(p['outcome_fields']) or 'none in run table'}" for p in ps))
    diff.append("Runs (with outcome): " + "; ".join(f"{p['acronym']} {p['n_runs']} ({p['n_with_outcome']})" for p in ps))

    shared_pillars = set.intersection(*[set(p["pillars"]) for p in ps])
    if shared_pillars:
        same.append("Both inform: " + ", ".join(sorted(shared_pillars)))

    result = {
        "ids": ids,
        "investigations": [P.public(p) for p in ps],
        "similarities": same,
        "differences": diff,
        "summary": _template_summary(ps, same),
        "summary_source": "template",
    }
    if use_llm:
        text = llm.complete(_llm_prompt(result))
        if text:
            result["summary"], result["summary_source"] = text, "llm"
    return result


def _template_summary(ps, same):
    names = " vs ".join(p["acronym"] for p in ps)
    parts = [f"{p['acronym']} ({p['category']}, {p['n_runs']} runs, {_fmt_o2(p['o2_frac_range'])})" for p in ps]
    s = f"{names}: " + "; ".join(parts) + "."
    if same:
        s += " In common: " + "; ".join(x.split(": ", 1)[-1] if x.startswith("Same") else x for x in same[:3]) + "."
    return s


def _llm_prompt(result):
    facts = {k: result[k] for k in ("similarities", "differences")}
    facts["investigations"] = [{k: p[k] for k in ("acronym", "title", "category", "objective", "pillars")}
                               for p in result["investigations"]]
    return ("You are helping aerospace engineers compare NASA microgravity combustion investigations for "
            "spacecraft fire safety. Using ONLY the facts below, write 4-6 plain sentences: how the "
            "investigations are similar, how they differ, and what each contributes to fire safety. "
            "Do not add numbers or claims that are not in the facts.\n\n" + json.dumps(facts, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", help="2-3 investigation ids, e.g. PSI-25 PSI-99")
    ap.add_argument("--data", default="dataset/flame_runs.json")
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    out = compare(Dataset.from_json(a.data), a.ids, use_llm=a.llm)
    print("SIMILAR\n  " + "\n  ".join(out["similarities"] or ["(nothing obvious)"]))
    print("DIFFERENT\n  " + "\n  ".join(out["differences"]))
    print(f"SUMMARY ({out['summary_source']})\n  {out['summary']}")


if __name__ == "__main__":
    main()
