"""Flame shape measures: the same numbers from a NASA video and from the simulation, so the two can be compared.

Cameras differ and have no scale in the frame, so every measure is a ratio, not a size:
  aspect   long axis / short axis of the flame (1 = round, droplet in still air; large = stretched by flow or buoyancy)
  fill     flame area / its convex hull (1 = solid blob; low = ragged, broken or curved, like a crescent)
  hollow   share of the flame's outline with no flame inside (spherical diffusion flames look like rings)
  blue     share of blue in the flame's light (soot-free flames are blue and dim, sooty ones yellow)
  flicker  how much the flame area changes from frame to frame (std / mean), after the igniter phase
  alive    share of frames after ignition with a flame; extinguished = gone at the end after burning
Pixel threshold is set per clip (background + 25% of the way to the brightest flame pixels), so a flame shrinking
before it goes out is still seen as shrinking, and dim blue flames are not compared against bright yellow ones.

    python -m flame.shape     # self-check on drawn shapes
"""
import cv2
import numpy as np

MEASURES = ["aspect", "fill", "hollow", "blue"]
MIN_FRAC = 0.0004  # smallest flame worth measuring: 0.04% of the frame (about 5 px at 96 x 128)


def luminance(img):
    """RGB uint8 (..., h, w, 3) → smoothed luminance: camera speckle (single coloured pixels) averages out."""
    lum = img.astype(np.float32).mean(-1)
    sig = max(0.5, lum.shape[-1] * 0.004)
    one = lambda x: cv2.GaussianBlur(cv2.medianBlur(x, 3), (0, 0), sig)  # median kills isolated speckle pixels
    return one(lum) if lum.ndim == 2 else np.stack([one(x) for x in lum])


def clip_threshold(frames, frac=0.05):
    """frames (t, h, w, 3) uint8 → luminance threshold for "flame" for this whole clip: above the camera's noise
    and `frac` of the way from background to the brightest flame pixels (low enough for dim blue flames)."""
    lum = luminance(frames[::max(1, len(frames) // 30)])
    bg = float(np.median(lum))
    noise = float(np.median(np.abs(lum - bg))) * 1.4826 + 0.5
    peak = float(np.percentile(lum, 99.9))
    return max(bg + 5 * noise, bg + frac * (peak - bg))


def frame_measures(img, th):
    """One RGB frame (h, w, 3) uint8 and a luminance threshold → dict of measures, or None (no flame)."""
    lum = luminance(img)
    h, w = lum.shape
    m = (lum > th).astype(np.uint8)
    k = max(1, round(min(h, w) * 0.05))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))  # drop noise and thin lit hardware (needles, wires)
    k = max(1, round(min(h, w) * 0.01))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3 * k, 3 * k), np.uint8))  # a ring is one object, not many
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n < 2:
        return None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))  # largest bright object = the flame
    blob = (lab == big).astype(np.uint8)
    area = int(blob.sum())
    if area < MIN_FRAC * h * w:
        return None
    ys, xs = np.nonzero(blob)
    cov = np.cov(np.stack([xs, ys]).astype(np.float64)) + np.eye(2) * 1 / 12  # +pixel size so 1-px lines stay finite
    ev, evec = np.linalg.eigh(cov)
    aspect = float(np.sqrt(ev[1] / ev[0]))
    angle = float(np.degrees(np.arctan2(evec[1, 1], evec[0, 1])) % 180)  # long axis, 0 = horizontal
    hull = cv2.convexHull(np.stack([xs, ys], 1).astype(np.int32))
    fill = area / max(cv2.contourArea(hull) + len(hull) / 2, 1)
    # hollow: the flame's outline filled in vs. the flame itself
    cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    solid = cv2.drawContours(np.zeros_like(blob), cnts, -1, 1, thickness=cv2.FILLED)
    hollow = 1 - area / max(int(solid.sum()), 1)
    rgb = img[blob > 0].astype(np.float64).sum(0)
    blue = float(rgb[2] / max(rgb.sum(), 1))
    return {"area": area / (h * w), "aspect": aspect, "angle": angle, "fill": min(fill, 1.0), "hollow": hollow,
            "blue": blue, "cx": float(xs.mean() / w), "cy": float(ys.mean() / h)}


def clip_measures(frames, skip=0.15):
    """Frames from ignition onwards (t, h, w, 3) → per-clip summary (medians over frames + dynamics)."""
    th = clip_threshold(frames)
    per = [frame_measures(f, th) for f in frames]
    t0 = int(len(per) * skip)  # igniter glow at the start
    after = per[t0:]
    lit = [p for p in after if p]
    out = {"frames": len(frames), "alive": len(lit) / max(len(after), 1), "threshold": th}
    # lights on or glare from lit hardware: when the "flame" covers a quarter of the frame, shapes mean nothing
    areas = [p["area"] for p in lit]
    out["lit_scene"] = bool(areas and np.median(areas) > 0.25)
    burned = any(per[:max(t0 + 2, len(per) // 2)])
    out["extinguished"] = bool(burned and len(after) >= 4 and not any(after[-3:]))
    if not lit:
        return {**out, **{k: None for k in MEASURES + ["flicker", "angle"]}}
    for k in MEASURES + ["angle"]:
        out[k] = float(np.median([p[k] for p in lit]))
    a = np.array([p["area"] for p in lit])
    out["flicker"] = float(a.std() / a.mean()) if len(a) > 2 else None
    out["series"] = [{k: round(v, 4) for k, v in p.items()} if p else None for p in per]
    return out


def _check():
    rng = np.random.default_rng(0)

    def canvas():
        return rng.integers(0, 8, (120, 160, 3)).astype(np.uint8)  # dark noisy camera

    ring = canvas()
    cv2.circle(ring, (80, 60), 30, (120, 120, 255), 5)
    ell = canvas()
    cv2.ellipse(ell, (80, 60), (50, 10), 0, 0, 360, (255, 200, 80), -1)
    r = frame_measures(ring, 40)
    e = frame_measures(ell, 40)
    assert 0.9 < r["aspect"] < 1.1 and r["hollow"] > 0.5 and r["blue"] > 0.45, r
    assert 4 < e["aspect"] < 6 and e["hollow"] < 0.2 and e["fill"] > 0.9 and min(e["angle"], 180 - e["angle"]) < 5, e
    drop = canvas()  # dim round droplet flame held by two thin, brighter needles
    cv2.circle(drop, (80, 60), 25, (60, 50, 120), -1)
    cv2.line(drop, (20, 60), (150, 60), (255, 255, 255), 2)
    d = frame_measures(drop, clip_threshold(drop[None]))
    assert d and d["aspect"] < 1.3, ("needles must not stretch the flame", d)
    assert frame_measures(canvas(), 40) is None
    # extinction: flame for 10 frames then nothing
    clip = np.stack([ell] * 10 + [canvas()] * 6)
    c = clip_measures(clip)
    assert c["extinguished"] and 0.4 < c["alive"] < 0.8, c
    c = clip_measures(np.stack([ell] * 16))
    assert not c["extinguished"] and c["alive"] == 1 and c["flicker"] < 0.01, c
    print("shape ok: ring", {k: round(r[k], 2) for k in MEASURES}, "| ellipse", {k: round(e[k], 2) for k in MEASURES})


if __name__ == "__main__":
    _check()
