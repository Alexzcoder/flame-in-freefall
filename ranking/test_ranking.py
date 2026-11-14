"""python3 -m ranking.test_ranking   (fast: uses examples/runs.sample.json, then the full dataset if present)"""
import os

from flame.schema import Dataset

from ranking.compare import compare
from ranking.rank import rank, run_similarity
from ranking.scenarios import custom


def check(path):
    ds = Dataset.from_json(path)
    out = rank(ds, "moon_base")
    scores = [r["score"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True), "not sorted"
    assert all(0 <= s <= 100 for s in scores)
    assert len(out["results"]) == len(ds.investigations)
    sc = custom(0.30, 70.3)
    for r in ds.runs:
        s = run_similarity(r, sc)
        if r.conditions.o2_location != "ambient":
            assert s is None, "inverse-flame run used in O2 matching"
        elif s is not None:
            assert 0 <= s <= 1
    ids = [i.id for i in ds.investigations[:2]]
    c = compare(ds, ids)
    assert c["differences"] and c["summary"]
    for f in ("prevention", "detection", "suppression"):
        rank(ds, "iss", focus=f)
    return len(ds.runs)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in ("examples/runs.sample.json", "dataset/flame_runs.json"):
        full = os.path.join(root, p)
        if os.path.exists(full):
            print(f"ok: {p} ({check(full)} runs)")
