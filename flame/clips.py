"""Curated real-footage set: pick runs spread over the condition space, cut a short clip + thumbnail + stills of the burn.

    python -m flame.clips --select            # print the picked runs per family (no downloads)
    python -m flame.clips                     # download → find burn → cut → delete raw; → media_out/ + dataset/media_clips.json
    python -m flame.clips --only PSI-25/B12   # (re)process one run

Needs ffmpeg and dataset/media_index.json (python -m flame.media). Outputs in media_out/ are git-ignored and get
uploaded as a GitHub Release; dataset/media_clips.json (committed) says what each file shows.

Burn window, from mean frame brightness (overlay rows cut off) and "flame area" (share of pixels brighter than 12/255):
lights on during setup → lights off right before ignition → ignition = flame area jumps above the dark baseline
while the lights are still off. Frames with the lights on (flashes) are never taken as flame.
"""
import argparse, concurrent.futures as cf, json, os, shutil, subprocess, tempfile, urllib.request

import numpy as np

from flame.fetch import Fetcher
from flame.media import ROOT

INDEX = os.path.join(ROOT, "dataset", "media_index.json")
OUT_JSON = os.path.join(ROOT, "dataset", "media_clips.json")
OUT_DIR = os.path.join(ROOT, "media_out")

# per family: investigation, how many runs, max main-video size (download is the bottleneck), features to spread over
PLAN = {
    "solid": ("PSI-25", 10, 60, ["conditions.atmosphere.o2_frac", "conditions.flow.velocity_cm_s"], "conditions.fuel.name"),
    "droplet": ("PSI-39", 10, 120, ["conditions.atmosphere.o2_frac", "log_pressure"], None),
    "gas": ("PSI-159", 8, 150, ["conditions.atmosphere.o2_frac", "log_pressure", "conditions.fuel.fuel_frac"],
            "conditions.fuel.name"),
}
CLIP_S, PRE_S = 16, 2  # clip length (ignition + flame settling in), seconds kept before ignition
W, H, TOP = 160, 120, 0.2  # analysis size; top 20% of rows dropped (BASS data overlay)


# ---------- selection ----------
def select():
    """Greedy max-min ("farthest point") sampling on standardised conditions, per family, among small-enough videos."""
    import pandas as pd
    from flame.schema import Dataset
    idx = json.load(open(INDEX))["runs"]
    df = Dataset.from_json(os.path.join(ROOT, "dataset", "flame_runs.json")).to_frame()
    df = df[df["id"].isin(idx)].copy()
    df["mb"] = df["id"].map(lambda i: next(f["size_mb"] for f in idx[i]["files"] if f["name"] == idx[i]["main_video"]))
    df["log_pressure"] = np.log(df["conditions.atmosphere.pressure_kpa"])
    picked = {}
    for fam, (acc, n, cap, feats, cat) in PLAN.items():
        d = df[(df["investigation"] == acc) & (df["mb"] <= cap)].dropna(subset=feats).reset_index(drop=True)
        X = ((d[feats] - d[feats].mean()) / d[feats].std().replace(0, 1)).to_numpy()
        if cat:  # a different fuel counts as far away as 1 std
            X = np.hstack([X, pd.get_dummies(d[cat]).to_numpy(float)])
        chosen = [int(np.argmin(((X - np.median(X, axis=0)) ** 2).sum(1)))]  # start from the most typical run
        dist = ((X - X[chosen[0]]) ** 2).sum(1)
        while len(chosen) < min(n, len(d)) and dist.max() > 0:  # stop when only repeats of picked conditions are left
            chosen.append(int(np.argmax(dist)))
            dist = np.minimum(dist, ((X - X[chosen[-1]]) ** 2).sum(1))
        picked[fam] = d.loc[chosen, ["id", "mb", *feats] + ([cat] if cat else [])]
    return picked


# ---------- burn window ----------
def frames(path):
    """1 frame per second, grey, W×H, overlay rows removed → uint8 array (seconds, rows, cols)."""
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-vf", f"fps=1,scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W)[:, int(H * TOP):]


def burn_window(f):
    """→ (ignition_s, flame_end_s) or None.

    Lights on during setup → lights off → ignition = bright pixels (>12/255, igniter or flame) appear while dark →
    flame lasts while pixels above the camera's own dark noise stay above baseline. The dim threshold adapts per
    video because cameras differ: BASS is pure black when dark, the CFI droplet camera is noisy.
    """
    mean = f.mean(axis=(1, 2))
    lit = np.median(mean[:5])
    dark = mean < 0.5 * lit
    off = next((t for t in range(len(mean) - 3) if dark[t:t + 3].all()), None)
    if lit < 10 or off is None:  # no lights-on setup phase: treat the whole video as dark
        off, dark = 0, np.ones(len(mean), bool)
    base = f[off:off + 3]
    dim_th = np.percentile(base, 99.5) + 2
    hot = (f > max(12, dim_th)).mean(axis=(1, 2)) * 1000
    dim = (f > dim_th).mean(axis=(1, 2)) * 1000
    hot0, dim0 = np.median(hot[off:off + 3]), np.median(dim[off:off + 3])
    ign = next((t for t in range(off, len(f)) if dark[t] and hot[t] > max(5 * hot0, hot0 + 3)), None)
    if ign is None:
        return None
    burning = dark & (dim > dim0 + 2)
    end = next((t for t in range(ign + 5, len(f)) if not burning[t:t + 3].any()), len(f))
    return ign, end


def _check_burn_window():
    # shapes of the Step 0 test videos: BASS B12 (lights off 9 s, igniter 21 s, dim flame to ~88 s)
    # and CFI f173e01 (noisy dark camera, lights flash at 304 s, flame from 328 s)
    def video(*parts):  # parts: (seconds, background level, flame pixels, flame level)
        out = []
        for n, bg, k, lvl in parts:
            fr = np.full((n, 96, W), bg, np.uint8)
            fr[:, 40, :k] = lvl
            out.append(fr)
        return np.concatenate(out)
    f = video((9, 30, 0, 0), (12, 0, 0, 0), (1, 0, 150, 255), (66, 0, 120, 6), (5, 0, 0, 0))
    assert burn_window(f) == (21, 88), burn_window(f)
    rng = np.random.default_rng(0)
    f = video((250, 41, 0, 0), (54, 3, 0, 0), (1, 41, 0, 0), (23, 3, 0, 0), (70, 3, 160, 200))
    f = np.clip(f + rng.integers(0, 8, f.shape), 0, 255).astype(np.uint8)  # sensor noise
    assert burn_window(f)[0] == 328, burn_window(f)


# ---------- one run ----------
def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def process(run_id, entry):
    acc, video = entry["investigation"], entry["main_video"]
    out = os.path.join(OUT_DIR, run_id.replace("/", "_"))
    tmp = tempfile.mkdtemp(prefix="flameclip_")
    try:
        raw = os.path.join(tmp, "raw" + os.path.splitext(video)[1])
        with urllib.request.urlopen(Fetcher().presigned_url(acc, video), timeout=120) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        f = frames(raw)
        win = burn_window(f)
        if win is None:
            return run_id, {"status": "no_flame_found", "source_video": video}
        ign, end = win
        start = max(0, ign - PRE_S)
        # flame phase after the igniter glow: stills, thumbnail and the brightness boost come from here
        flame_ts = np.arange(min(ign + 3, end - 1), end) if end - ign > 4 else np.arange(ign, end)
        stills = [int(t) for t in np.unique(np.linspace(flame_ts[0], flame_ts[-1], 4).round())]
        # levels stretch for dim flames: the 99.9th percentile of flame-phase pixels → white, colours kept
        hi = min(1.0, max(float(np.percentile(f[flame_ts], 99.9)), 32) / 255)  # gain capped at 8x, noise stays dark
        crop = "crop=iw:ih*0.82:0:ih*0.18," if entry["family"] == "solid" else ""  # BASS overlay blows out when boosted
        boost = f"{crop}colorlevels=rimax={hi:.3f}:gimax={hi:.3f}:bimax={hi:.3f},scale=-2:480"
        os.makedirs(out, exist_ok=True)
        enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "veryfast", "-an", "-movflags", "+faststart"]
        ff("-ss", start, "-t", CLIP_S, "-i", raw, "-vf", "scale=-2:480", *enc, f"{out}/clip.mp4")
        ff("-ss", start, "-t", CLIP_S, "-i", raw, "-vf", boost, *enc, f"{out}/clip_enhanced.mp4")
        ff("-ss", stills[len(stills) // 2], "-i", raw, "-frames:v", "1", "-vf", boost, "-q:v", "3", f"{out}/thumb.jpg")
        for i, t in enumerate(stills):
            ff("-ss", t, "-i", raw, "-frames:v", "1", "-vf", boost, "-q:v", "3", f"{out}/still_{i}.jpg")
        rel = os.path.relpath(out, OUT_DIR)
        return run_id, {
            "status": "ok", "source_video": video, "family": entry["family"],
            "ignition_s": ign, "flame_end_s": end, "clip_start_s": start, "clip_length_s": CLIP_S,
            "clip": f"{rel}/clip.mp4", "clip_enhanced": f"{rel}/clip_enhanced.mp4", "thumbnail": f"{rel}/thumb.jpg",
            "stills": [{"file": f"{rel}/still_{i}.jpg", "t_s": t} for i, t in enumerate(stills)],
            "enhancement": f"levels stretched x{1 / hi:.1f} for visibility (clip.mp4 is unmodified)",
            "verified": False,  # set True after a human looked at the clip
        }
    except Exception as e:  # one bad file must not stop the batch; the error is kept in the output
        return run_id, {"status": "error", "source_video": video, "error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true", help="only print the picked runs")
    ap.add_argument("--only", nargs="*", help="run ids to (re)process")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    _check_burn_window()
    picked = select()
    if a.select:
        for fam, d in picked.items():
            print(f"== {fam}: {len(d)} runs, {d['mb'].sum():.0f} MB to download"); print(d.to_string(index=False))
        return
    idx = json.load(open(INDEX))["runs"]
    ids = a.only or [i for d in picked.values() for i in d["id"]]
    done = json.load(open(OUT_JSON))["runs"] if os.path.exists(OUT_JSON) else {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for run_id, res in ex.map(lambda i: process(i, idx[i]), ids):
            done[run_id] = res
            print(f"{run_id:22} {res['status']:15} {res.get('ignition_s', '')} {res.get('error', '')}", flush=True)
            with open(OUT_JSON, "w") as f:  # saved after every run so a crash keeps finished work
                json.dump({"runs": done}, f, indent=1)


if __name__ == "__main__":
    main()
