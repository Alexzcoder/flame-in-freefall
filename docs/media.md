# Media dataset: real experiment footage per run

Goal: link runs to real NASA footage (clip + thumbnail + stills) so the dashboard can show the nearest real experiment
next to the simulated flame, and so the procedural flame can be tuned to look like the real one.

## Step 0 findings (2026-11-14, one file tested per family)

| Family | File tested | Size / length | Access | What the video shows |
|---|---|---|---|---|
| Solid (BASS-II, PSI-25/B12) | `..._SAMPLE_160_TEST_B12.mp4` | 13 MB, 93 s, 720×480 | download whole | sample lit → red igniter glow (~20 s) → dim blue flame |
| Droplet (CFI, PSI-39/f173e01) | `..._F173E01.mp4` | 110 MB, 401 s, 1280×720 | stream frames, 7 frames in 40 s | droplet on needles → dark → spherical flame (~380 s) |
| Gas (CFI-G, PSI-159/21088A1) | `vlc-record-..._21088A1.ts` | 490 MB, 270 s, 640×480 | stream frames, 7 frames in 7 min | lit hardware → ignition (~170 s) → very faint round flame |

- PSI download links are presigned S3 URLs (`Fetcher.presigned_url`). They accept HTTP range requests (`206 Partial Content`),
  so ffmpeg can read only the seconds it needs. A HEAD request returns 403; that is normal (the link is signed for GET).
- mp4 seeks fast (it has an index). `.ts` has no index, so each seek re-reads the stream: download `.ts` once, process, delete.
- Most of each video is setup with lights on. Lights go off right before ignition, so a bright → dark drop in mean
  frame brightness marks the burn window.
- Flames are dim (blue/purple). Clips need a brightness/contrast boost, labelled "enhanced for visibility".
- BASS-II videos have a data overlay (fuel/air/fan values) in the top rows.
- FLEX (PSI-69) has no media on PSI at all; droplet footage comes from CFI (PSI-39).

Download budget: ~30 curated runs ≈ 1–2 GB of raw downloads (processed one at a time, then deleted);
outputs ≈ 50–100 MB, hosted as a GitHub Release, not in git.

## Step 1: run → video index (`python -m flame.media` → `dataset/media_index.json`)

`{"runs": {run_id: {investigation, family, main_video, files: [{name, role, size_mb}]}}}`, roles:
`main` | `second_view` | `still_sequence` | `archive` (zips). Separate from `flame_runs.json`, joined by run id.

| Investigation | Family | Runs | With video |
|---|---|---|---|
| PSI-25 BASS-II | solid | 129 | 121 (was 71: 2-char test ids like B1 were skipped; now matched on TEST id + SAMPLE no., GMT day checked against date) |
| PSI-39 CFI | droplet | 79 | 47 (the other 32 runs have no video on PSI) |
| PSI-159 CFI-G | gas | 333 | 324 |
| PSI-10 Flame Design | gas | 327 | 306 |
| FLEX, SPICE, SAFFIRE | | | 0 (no per-run video files on PSI) |

Not linked: 12 BASS side videos (LOS camera, post-burn pictures), CFI-G files for runs missing from the table.

## Step 2: curated clips (`python -m flame.clips`, then `--publish`)

25 runs picked to spread over conditions (10 solid, 7 droplet, 8 gas) → `media_out/` (git-ignored) +
`dataset/media_clips.json`. `--publish` crops each enhanced clip to the flame, denoises it and writes
`public/media/<run>/clip.mp4` + `thumb.jpg` + `public/media/index.json` (what the frontend loads; Vercel serves `public/`).
23 clips on the website (20 MB); 2 gas runs left out (tiny flame in sensor noise, see `NOT_ON_WEB` in `flame/clips.py`).
Clips are brightened for visibility: label them that way on the site.
