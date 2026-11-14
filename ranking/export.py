"""Write ranking + comparison results as JSON for the frontend (no Python needed on their side).

    python3 -m ranking.export          # -> ranking/out/rankings.json, ranking/out/comparisons.json
    python3 -m ranking.export --llm    # also AI summaries (DeepSeek or Claude key in .env, see README)
"""
import argparse
import itertools
import json
import os

from flame.schema import Dataset

from . import profiles as P
from .compare import compare
from .rank import rank
from .scenarios import SCENARIOS

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
FOCUSES = [None, "prevention", "detection", "suppression"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset/flame_runs.json")
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    ds = Dataset.from_json(a.data)
    profs = P.build(ds)
    os.makedirs(OUT, exist_ok=True)

    rankings = {sid: {f or "all": rank(ds, sid, f, profs) for f in FOCUSES} for sid in SCENARIOS}
    with open(os.path.join(OUT, "rankings.json"), "w") as f:
        json.dump({"schema_version": ds.schema_version, "rankings": rankings}, f, indent=1)

    ids = sorted(profs, key=lambda i: int(i.split("-")[1]))
    pairs = {f"{x}|{y}": compare(ds, [x, y], use_llm=a.llm, profiles=profs) for x, y in itertools.combinations(ids, 2)}
    with open(os.path.join(OUT, "comparisons.json"), "w") as f:
        json.dump({"schema_version": ds.schema_version, "investigations": {i: P.public(profs[i]) for i in ids},
                   "pairs": pairs}, f, indent=1)

    print(f"wrote {OUT}/rankings.json ({len(SCENARIOS)} scenarios x {len(FOCUSES)} focuses)")
    print(f"wrote {OUT}/comparisons.json ({len(pairs)} pairs)")


if __name__ == "__main__":
    main()
