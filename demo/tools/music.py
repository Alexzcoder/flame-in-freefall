"""Original background music for the demo video (no licence needed: generated here).
Ambient pad Am-F-C-G with slow swells, a soft bell arpeggio and a sub note; light reverb via ffmpeg.

    python3 demo/tools/music.py   # → demo/public/music.wav (32 s, 44.1 kHz stereo)
"""
import os, subprocess
import numpy as np

SR, DUR = 44100, 32.0
t = np.arange(int(SR * DUR)) / SR
A4 = 440.0
note = lambda n: A4 * 2 ** ((n - 69) / 12)  # MIDI number → Hz
CHORDS = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]]  # Am F C G
BAR = 4.0  # seconds per chord
rng = np.random.default_rng(3)
left, right = np.zeros_like(t), np.zeros_like(t)

def env(start, length, attack, release):
    e = np.zeros_like(t); i0, i1 = int(start * SR), min(len(t), int((start + length) * SR))
    seg = t[i0:i1] - start
    e[i0:i1] = np.minimum(1, seg / attack) * np.minimum(1, (length - seg) / release)
    return np.clip(e, 0, 1)

for k in range(int(DUR / BAR) + 1):
    ch = CHORDS[k % 4]; start = k * BAR
    e = env(start, BAR + 1.2, 1.4, 1.6)  # overlapping swells
    for j, n in enumerate(ch):
        f = note(n)
        for det, pan in ((-0.12, 0.3), (0.12, 0.7)):  # two slightly detuned voices, spread in stereo
            w = np.sin(2 * np.pi * (f + det) * t + j) + 0.25 * np.sin(2 * np.pi * 2 * (f + det) * t)
            left += 0.05 * e * w * (1 - pan); right += 0.05 * e * w * pan
    sub = 0.08 * env(start, BAR, 0.6, 1.0) * np.sin(2 * np.pi * note(ch[0] - 12) * t)
    left += sub; right += sub
    for b in range(8):  # bell arpeggio, eighth notes
        n = ch[b % 4] + 12 * (b % 2 == 1 and b > 3)
        s = start + b * BAR / 8
        i0 = int(s * SR); i1 = min(len(t), i0 + int(1.6 * SR))
        tt = t[i0:i1] - s
        bell = 0.035 * np.exp(-tt * 3.2) * (np.sin(2 * np.pi * note(n + 12) * tt) + 0.3 * np.sin(2 * np.pi * note(n + 24) * tt))
        pan = 0.25 + 0.5 * rng.random()
        left[i0:i1] += bell * (1 - pan); right[i0:i1] += bell * pan

master = np.minimum(1, t / 2.5) * np.minimum(1, (DUR - t) / 3.0)  # fade in / out
mix = np.stack([left, right], 1) * master[:, None]
mix /= np.abs(mix).max() / 0.8
raw = os.path.join(os.path.dirname(__file__), "..", "out", "music_dry.wav")
out = os.path.join(os.path.dirname(__file__), "..", "public", "music.wav")
os.makedirs(os.path.dirname(raw), exist_ok=True)
import wave
with wave.open(raw, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype("<i2").tobytes())
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", "aecho=0.8:0.7:120|260:0.25|0.18,lowpass=f=6000,loudnorm=I=-20", out], check=True)
print("wrote", out)
