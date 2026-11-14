"""Curated real-footage set: pick runs spread over the condition space, cut a short clip + thumbnail + stills of the burn.

    python -m flame.clips --select            # print the picked runs per family (no downloads)
    python -m flame.clips                     # download → find burn → cut → delete raw; → media_out/ + dataset/media_clips.json
    python -m flame.clips --only PSI-25/B12   # (re)process one run
    python -m flame.clips --publish           # crop + denoise enhanced clips → public/media/ (served by Vercel)

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
WEB_DIR = os.path.join(ROOT, "public", "media")
# looked at by hand (contact sheet 2026-11-14): kept in media_out/, not shown on the website
NOT_ON_WEB = {
    "PSI-159/21125J1": "tiny flame buried in sensor noise, looks like static",
    "PSI-159/21265H1": "tiny flame buried in sensor noise, looks like static",
}

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


# ---------- website copy: crop away the empty black, denoise ----------
def flame_box(f):
    """Grey frames (t, rows, cols) → (x0, x1, y0, y1) as fractions of the frame, or None (keep the full frame).

    Per pixel, the 90th percentile over time: bright for at least 10% of the clip (flame, lit hardware), so one-frame
    noise and flashes don't count. Box = 1st-99th percentile of those pixels, padded, at least 40% of each side.
    """
    p = np.percentile(f.astype(float), 90, axis=0)
    bg = np.median(p)
    ys, xs = np.nonzero(p > bg + max(15, 8 * np.median(abs(p - bg))))
    if len(xs) < 20:
        return None

    def span(a, b, n):
        pad = 0.15 * (b - a) + 0.03 * n
        a, b = a - pad, b + pad
        if b - a < 0.4 * n:
            c = (a + b) / 2
            a, b = c - 0.2 * n, c + 0.2 * n
        return max(0, a) / n, min(n, b) / n

    rows, cols = p.shape
    return (*span(*np.percentile(xs, [1, 99]) + [0, 1], cols), *span(*np.percentile(ys, [1, 99]) + [0, 1], rows))


def _check_flame_box():
    rng = np.random.default_rng(0)
    f = rng.integers(0, 10, (20, 120, 160)).astype(np.uint8)  # dark noisy camera
    f[:, 50:70, 100:130] = 200  # flame on the right
    x0, x1, y0, y1 = flame_box(f)
    assert x0 < 100 / 160 and x1 > 130 / 160 and y0 < 50 / 120 and y1 > 70 / 120 and x0 > 0.3, (x0, x1, y0, y1)
    assert flame_box(np.zeros((20, 120, 160), np.uint8)) is None


def publish():
    """media_out/<run>/clip_enhanced.mp4 + thumb.jpg → public/media/<run>/clip.mp4 + thumb.jpg, cropped, and a `web`
    entry per run in media_clips.json (null + `web_skip` when not shown)."""
    data = json.load(open(OUT_JSON))
    for run_id, e in data["runs"].items():
        e.pop("web_skip", None)
        e["web"] = None
        if e["status"] != "ok" or run_id in NOT_ON_WEB:
            e["web_skip"] = NOT_ON_WEB.get(run_id, e["status"])
            continue
        src = os.path.join(OUT_DIR, e["clip_enhanced"])
        rel = os.path.dirname(e["clip_enhanced"])
        raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", src, "-vf", f"fps=2,scale={W}:{H}:flags=area,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        f = np.frombuffer(raw, np.uint8).reshape(-1, H, W)
        box = flame_box(f)
        # thumbnail: after the igniter glow (first PRE_S + 3 s), the frame with a typical (median) amount of visible
        # flame; the max picks the blown-out ignition flash, a fixed time can land on a moment the flame is dim
        lit = (f > np.median(f) + 30).sum(axis=(1, 2))[(PRE_S + 3) * 2:]
        ok = np.nonzero(lit)[0]
        thumb_s = PRE_S + 3 + (ok[np.argsort(lit[ok])[len(ok) // 2]] / 2 if len(ok) else 0)
        # crop in source pixels; even sizes for x264. Thumb has the same size as clip_enhanced (same filter chain).
        crop = (f"crop=trunc(iw*{box[1] - box[0]:.3f}/2)*2:trunc(ih*{box[3] - box[2]:.3f}/2)*2"
                f":iw*{box[0]:.3f}:ih*{box[2]:.3f}," if box else "")
        out = os.path.join(WEB_DIR, rel)
        os.makedirs(out, exist_ok=True)
        ff("-i", src, "-vf", crop + "hqdn3d=4:3:8:6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28",
           "-preset", "slow", "-an", "-movflags", "+faststart", f"{out}/clip.mp4")
        if e["family"] == "solid" or run_id == "PSI-39/f233d01":  # f233d01: mid-burn still is a blurry glow (checked by eye)
            ff("-ss", thumb_s, "-i", f"{out}/clip.mp4", "-frames:v", "1", "-q:v", "3", f"{out}/thumb.jpg")
        else:  # faint gas/droplet flames drown in camera noise for the pixel count; the mid-burn still works there
            ff("-i", os.path.join(OUT_DIR, e["thumbnail"]), "-vf", crop + "null", "-q:v", "3", f"{out}/thumb.jpg")
        e["web"] = {"clip": f"media/{rel}/clip.mp4", "thumbnail": f"media/{rel}/thumb.jpg",
                    "crop": [round(v, 3) for v in box] if box else None,
                    "note": "enhanced for visibility, cropped to the flame, denoised"}
        print(f"{run_id:22} {os.path.getsize(f'{out}/clip.mp4') / 1e6:5.1f} MB  crop={e['web']['crop']}", flush=True)
    with open(OUT_JSON, "w") as f:
        json.dump(data, f, indent=1)
    # what the frontend fetches (public/ is the only folder Vercel serves as static files)
    web = {i: {"family": e["family"], **e["web"]} for i, e in data["runs"].items() if e["web"]}
    with open(os.path.join(WEB_DIR, "index.json"), "w") as f:
        json.dump({"runs": web}, f, indent=1)
    print(f"{len(web)} clips on the website")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true", help="only print the picked runs")
    ap.add_argument("--publish", action="store_true", help="crop + copy finished clips to public/media/")
    ap.add_argument("--only", nargs="*", help="run ids to (re)process")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    _check_burn_window()
    _check_flame_box()
    if a.publish:
        return publish()
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
