"""Overnight: real NASA flame video → burn-window frames, for shape evaluation and calibration.

For each run with video (dataset/media_index.json): download the main video, find the burn window (flame/clips.py),
keep RGB frames of the burn at up to 2 fps and 320 px wide, delete the raw video. Output per run:
data/frames/<run>.npz (frames uint8 (t, h, w, 3), fps, ignition_s, flame_end_s, video) + data/frames/status.json.
Resumable (finished runs are skipped) and keeps going when one file fails. Disk: only `--workers` raw videos at once.

    python -m flame.harvest                       # BASS-II, CFI, CFI-G (order: smallest downloads first)
    python -m flame.harvest --inv PSI-25 --limit 5
    python -m flame.harvest --inv PSI-10          # Flame Design too (73 GB, no outcomes in the table)
"""
import argparse, concurrent.futures as cf, json, os, shutil, subprocess, tempfile, threading, time, urllib.request

import numpy as np

from flame.clips import burn_window, frames as grey_frames
from flame.fetch import Fetcher
from flame.media import ROOT

INDEX = os.path.join(ROOT, "dataset", "media_index.json")
OUT = os.path.join(ROOT, "data", "frames")
STATUS = os.path.join(OUT, "status.json")
TMP = os.path.join(ROOT, "data", "tmp")
WIDTH, MAX_FRAMES, MAX_FPS = 320, 300, 2.0
_lock = threading.Lock()


def retry(f, tries=6, wait=20):
    for i in range(tries):
        try:
            return f()
        except Exception:  # PSI's API answers 504 when busy; back off and try again
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


def download(acc, name, path):
    url = retry(lambda: Fetcher().presigned_url(acc, name))

    def get():
        with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    retry(get, tries=3)


def burn_frames(raw, ign, end, solid):
    """RGB frames from ignition to flame end (+4 s), at most MAX_FRAMES, WIDTH px wide (BASS overlay rows cut)."""
    dur = max(2, min(end + 4, ign + 900) - ign)
    fps = min(MAX_FPS, MAX_FRAMES / dur)
    crop = "crop=iw:ih*0.82:0:ih*0.18," if solid else ""
    probe = subprocess.run(["ffmpeg", "-v", "quiet", "-ss", str(ign), "-t", str(dur), "-i", raw, "-vf",
                            f"{crop}fps={fps:.4f},scale={WIDTH}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           capture_output=True, check=True).stdout
    h = len(probe)
    # frame height from the scaled size: ask ffprobe once (rawvideo has no header)
    info = subprocess.run(["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", raw], capture_output=True, text=True).stdout.split()[0].split(",")  # .ts: one line per program
    sw, sh = int(info[0]), int(info[1])
    if solid:
        sh = int(sh * 0.82)
    fh = int(round(WIDTH * sh / sw / 2)) * 2
    n = h // (WIDTH * fh * 3)
    return np.frombuffer(probe[:n * WIDTH * fh * 3], np.uint8).reshape(n, fh, WIDTH, 3), fps


def process(run_id, e):
    out = os.path.join(OUT, run_id.replace("/", "_") + ".npz")
    tmp = tempfile.mkdtemp(prefix="harvest_", dir=TMP)
    try:
        raw = os.path.join(tmp, "raw" + os.path.splitext(e["main_video"])[1])
        t = time.time()
        download(e["investigation"], e["main_video"], raw)
        mb = os.path.getsize(raw) / 1e6
        win = burn_window(grey_frames(raw))
        if win is None:
            return run_id, {"status": "no_flame_found", "mb": round(mb)}
        ign, end = win
        fr, fps = burn_frames(raw, ign, end, e["family"] == "solid")
        np.savez_compressed(out + ".part.npz", frames=fr, fps=fps, ignition_s=ign, flame_end_s=end, video=e["main_video"])
        os.replace(out + ".part.npz", out)
        return run_id, {"status": "ok", "ignition_s": int(ign), "flame_end_s": int(end), "frames": len(fr),
                        "fps": round(fps, 3), "mb": round(mb), "s": round(time.time() - t)}
    except Exception as ex:  # one bad file must not stop the night
        return run_id, {"status": "error", "error": f"{type(ex).__name__}: {ex}"[:300]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inv", nargs="*", default=["PSI-25", "PSI-39", "PSI-159"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--only", nargs="*", help="run ids (re)done regardless of status")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    idx = json.load(open(INDEX))["runs"]
    status = json.load(open(STATUS)) if os.path.exists(STATUS) else {}
    size = lambda i: next(f["size_mb"] for f in idx[i]["files"] if f["name"] == idx[i]["main_video"])
    todo = [i for inv in a.inv for i in sorted((i for i in idx if idx[i]["investigation"] == inv), key=size)
            if i not in status or (a.retry_errors and status[i]["status"] == "error")][:a.limit]
    if a.only:
        todo = a.only
    print(f"{len(todo)} runs to harvest, {sum(map(size, todo)) / 1e3:.1f} GB to download", flush=True)
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for k, (run_id, res) in enumerate(ex.map(lambda i: process(i, idx[i]), todo), 1):
            with _lock:
                status[run_id] = res
                with open(STATUS + ".part", "w") as f:
                    json.dump(status, f, indent=1)
                os.replace(STATUS + ".part", STATUS)
            print(f"[{k}/{len(todo)}] {run_id:22} {res['status']:15} {res.get('frames', '')} "
                  f"{res.get('mb', '')} MB {res.get('s', '')} s {res.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
