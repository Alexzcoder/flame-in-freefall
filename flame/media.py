"""Run -> media file index: which real NASA footage belongs to which run.

    python -m flame.media        # needs data/raw/manifests (python -m flame.fetch) → dataset/media_index.json

Starts from run.media (test id found in the file name, see normalize.MediaIndex) and adds BASS-II files, whose
2-character test ids (B1, T5…) the generic matcher skips: there we match TEST_<id> AND SAMPLE_<n> against the run's
extra.sample, and check GMT<day> against the run date. Does not touch flame_runs.json.
"""
import datetime, json, os, re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "dataset", "media_index.json")

FAMILY = {"PSI-25": "solid", "PSI-98": "solid", "PSI-99": "solid", "PSI-100": "solid",
          "PSI-39": "droplet", "PSI-69": "droplet", "PSI-10": "gas", "PSI-159": "gas", "PSI-107": "gas"}
VIDEO = (".mp4", ".ts", ".avi", ".mov")
ROLES = ["main", "second_view", "still_sequence", "archive"]
BASS = re.compile(r"GMT_?(\d+)_SAMPLE_?(\d+)_TEST[_ -]?([A-Z]\d+)(?![0-9])", re.I)


def manifest_files(acc):
    """{file_name: size_bytes} for every file PSI lists for this investigation."""
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if "file_name" in o and "file_size" in o:
                out[o["file_name"]] = int(float(o["file_size"] or 0))
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.load(open(os.path.join(RAW, "manifests", f"{acc}.json"))))
    return out


def role(name):
    n = name.lower()
    if not n.endswith(VIDEO):
        return "archive"  # zips of raw images/data: huge, not used for clips
    if "still_sequence" in n:
        return "still_sequence"
    if "2nd_view" in n:
        return "second_view"
    return "main"


def sample_no(s):
    """'185M' / '185' → 185. The table adds letter suffixes (m, M, L) that file names drop."""
    m = re.match(r"\d+", str(s or ""))
    return int(m[0]) if m else None


def bass_files(run, files):
    test_id = run["id"].split("/", 1)[1]
    doy = datetime.date.fromisoformat(run["date"]).timetuple().tm_yday if run["date"] else None
    out = []
    for name in files:
        m = BASS.search(name)
        if not m or m[3].upper() != test_id.upper() or int(m[2]) != sample_no(run["extra"].get("sample")):
            continue
        assert doy is None or abs(int(m[1]) - doy) <= 1, f"{run['id']}: GMT{m[1]} vs date {run['date']}"
        out.append(name)
    return out


def build(runs):
    sizes, index = {}, {}
    for run in runs:
        acc = run["investigation"]
        if acc not in FAMILY:
            continue
        if acc not in sizes:
            sizes[acc] = manifest_files(acc)
        names = set(run["media"])
        if acc == "PSI-25":
            names |= set(bass_files(run, sizes[acc]))
        # PSI lists most files twice: "X.zip" (legacy) and "PSI-25_Raw Data_X.zip"; keep the prefixed one
        prefixed = {m[1] for n in names if (m := re.match(rf"{acc}_[^_]+_(.*)$", n))}
        names = {n for n in names if n.startswith(acc + "_") or n not in prefixed}
        if not any(n.lower().endswith(VIDEO) for n in names):
            continue
        files = sorted(({"name": n, "role": role(n), "size_mb": round(sizes[acc].get(n, 0) / 1e6, 1)} for n in names),
                       key=lambda f: (ROLES.index(f["role"]), not f["name"].lower().endswith(".mp4"), f["name"]))
        # mp4 before .ts of the same recording: mp4 seeks fast; 2nd camera view if there is no main one (3 BASS runs)
        index[run["id"]] = {"investigation": acc, "family": FAMILY[acc], "files": files,
                            "main_video": files[0]["name"] if files[0]["role"] in ("main", "second_view") else None}
    return index


def check(index, runs):
    b1 = index["PSI-25/B1"]
    assert b1["main_video"] == "PSI-25_Raw Data_BASS_GMT50_SAMPLE_147_TEST_B1.mp4", b1
    assert all(f["name"].lower().endswith(VIDEO) or f["role"] == "archive" for e in index.values() for f in e["files"])
    shared = [v for v, n in Counter(e["main_video"] for e in index.values() if e["main_video"]).items() if n > 1]
    assert not shared, f"main video linked to several runs: {shared[:5]}"
    by_id = {r["id"]: r for r in runs}
    for rid, e in index.items():  # every BASS link must agree on sample number
        if e["investigation"] == "PSI-25":
            for f in e["files"]:
                m = BASS.search(f["name"])
                assert not m or int(m[2]) == sample_no(by_id[rid]["extra"]["sample"]), (rid, f["name"])


if __name__ == "__main__":
    runs = json.load(open(os.path.join(ROOT, "dataset", "flame_runs.json")))["runs"]
    index = build(runs)
    check(index, runs)
    with open(OUT, "w") as f:
        json.dump({"runs": index}, f, indent=1)
    total = Counter(r["investigation"] for r in runs if r["investigation"] in FAMILY)
    linked = Counter(e["investigation"] for e in index.values())
    with_main = Counter(e["investigation"] for e in index.values() if e["main_video"])
    for acc in total:
        print(f"{acc:8} {FAMILY[acc]:8} runs {total[acc]:4}  with video {linked[acc]:4}  with main view {with_main[acc]:4}")
    print(f"wrote {OUT}: {len(index)} runs")
