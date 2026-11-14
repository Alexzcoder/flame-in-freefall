# Space Apps 2026 submission: Flame in Freefall

**Deadline: Sunday 15 November 2026, 11:59 PM, team owner's local time.** Submitted on the Project tab of the team
page at spaceappschallenge.org. Aim to submit by the afternoon, not at 23:59.
Rules from the [Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/)
and [Judging & Awards Guide](https://www.spaceappschallenge.org/resources/judging-awards-guide) (re-check the 2026
versions on the site before submitting). Judging: Impact, Creativity, Validity, Relevance, Presentation (presentation
weighs as much as the others).

## Checklist

- [ ] Team registered, challenge "Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data" selected (team owner submits)
- [ ] PR with the overnight model work reviewed and merged, production deployed, live site checked
- [ ] Demo video ≤ 30 s, English subtitles burned in, uploaded unlisted (YouTube), link opens without login
- [ ] Final project link: live site https://flame-in-freefall-ivory.vercel.app (public)
- [ ] **OPEN DECISION (waiting on Alex): make the GitHub repo public or link the site only.** Git history checked
      2026-11-14: no API keys committed (only the `sk-...` placeholder in an example).
- [ ] Title, summary, details, NASA data, references, AI disclosure pasted from below
- [ ] After the event: rotate the DeepSeek API key (it was pasted in a chat)

## Title

Flame in Freefall: what NASA's microgravity fire data says about your habitat

## Summary (short)

Moon bases are planned at 30 %+ oxygen and 10.2 psi, conditions where materials burn more easily, yet no solid
material in NASA's public data has been burned in microgravity above 22 % oxygen. Flame in Freefall turns 1,624 NASA
microgravity combustion runs from 24 investigations into one checked dataset and a website where anyone can set a
cabin atmosphere and see what NASA has really tested, what it hasn't, and what a NASA-calibrated flame model predicts:
does a small fire keep burning, how does it spread, does switching the fans off stop it. Ember, an AI assistant,
answers questions citing NASA runs and report pages.

## Project details (long)

**What it does.** For any cabin atmosphere (oxygen, pressure, airflow, gravity, fuel type):
1. *What NASA tested*: the closest real experiments and how well the data covers these conditions (gap map).
2. *What a flame does there*: a live fluid simulation of a small fire, next to real NASA footage of the closest run.
3. *What it means for a habitat*: a 3D ISS module and Moon base where each object shows NASA's verdict for its
   material, a simulated fire with fans on vs. off, and how far other flammables should be kept away.
4. *Ask Ember*: a cited AI answer from NASA run tables and final reports.

**How it works.**
- Data: PSI run tables normalised into one schema (1,624 runs, 633 with measured outcomes), every value traceable to
  its source row; 5,123 numbers re-checked against the raw NASA files; assumptions flagged per run.
- Search: 1,882 report pages and paper abstracts, keyword index, cited answers.
- Physics: a 2D flame simulation (fluid flow + one-step combustion + fuel spread) running in the browser (WebGL) and on
  a GPU (PyTorch). Its knobs are fitted to NASA runs: CFI-G gas-flame extinction times (331 runs), BASS-II flame
  shapes measured from 384 NASA videos, BASS-II/SAFFIRE burn-or-extinguish outcomes, and BASS-II/SAFFIRE spread rates.
  Whole test days are held out to score it. Results: solid fires burn or go out as NASA saw in 30 of 31 cases
  predicted with each case left out; spread fitted to 6 of 7 NASA targets (fabric 2.38 vs. 2.1-2.6 mm/s). Gas-flame
  outcomes from the simulation do not beat guessing on held-out days, so gas and droplet numbers come from the data
  models. Full scores: https://flame-in-freefall-ivory.vercel.app/checked.html
- Data-only models: gradient-boosted trees with test-day cross-validation and calibrated 80 % ranges, e.g. gas-flame
  extinction time within ×1.42 (vs ×2.67 guessing), droplet burning rate 0.040 mm²/s error (vs 0.095).
- A neural-network emulator of the calibrated simulation predicts a flame instantly in the browser.

**Finding worth knowing.** In the ISS, switching the fans off starves a small fabric fire (as NASA's BASS-II saw). In a
Moon base it does not in our model: lunar gravity makes hot gas rise and draws in fresh air by itself. (Physics, not
data: no lunar-gravity fire tests exist.)

**Benefits / impact.** Habitat designers and safety engineers see at a glance where the evidence ends (e.g. solids
above 22 % O₂), instead of extrapolating silently. Every prediction says whether it is inside the tested conditions.

**Tools.** Python (stdlib, PyTorch, scikit-learn, OpenCV), FastAPI on Vercel, vanilla JS, WebGL2, Three.js, Plotly.

## NASA data and resources

- NASA Physical Sciences Informatics (PSI), https://psi.nasa.gov: run tables, file manifests and videos of PSI-69
  FLEX, PSI-39 CFI, PSI-159 ACME CFI-G, PSI-10 ACME Flame Design, PSI-107 SPICE, PSI-25 BASS-II, PSI-98/99/100
  SAFFIRE I-III, plus metadata of 15 further combustion investigations.
- NASA final reports in PSI (40 PDFs), notably the BASS-II Summary Report NASA/TM-20210011385.
- NASA Technical Reports Server (abstracts), NASA Exploration Atmospheres Working Group recommendation (8.2 psi, 34 % O₂).

## References

299 papers linked to the investigations (`dataset/publications.json`: title, venue, year, DOI). Abstracts from
OpenAlex, Semantic Scholar and NTRS.

## Use of AI (disclose)

- Claude Code (Anthropic) helped write code, data processing and documentation; the team reviewed and directed it.
- Ember chat uses DeepSeek through its API; answers are grounded in retrieved NASA documents and must cite them.
- Higgsfield generated the Ember character GIFs and the 3D object models of the habitats (labelled as illustrations).
- The flame emulator is a neural network we trained ourselves on our own simulation output.

## Demo video (≤ 30 s, subtitles burned in)

| s | Shot | Subtitle |
|---|---|---|
| 0-3 | Home hero, Ember falling | Moon bases will run at 30 % oxygen. How does fire behave there? |
| 3-8 | Gap map, solids cluster below 22 % | NASA has never burned a solid in microgravity above 22 % O₂. |
| 8-14 | Scenario explorer: Moon base preset, flame sim + coverage note | Set any cabin air: see the closest NASA tests and a NASA-calibrated flame. |
| 14-19 | Simulation vs. reality: sim next to real NASA video | Our physics is fitted to 384 real NASA flame videos and 600+ outcomes. |
| 19-25 | 3D Moon base, click crew quarters: fans on/off, safe distance | Per object: does a fire keep burning? Does cutting the fans stop it? |
| 25-30 | Ask Ember with cited answer, logo | Every answer cites NASA. Flame in Freefall. |

Capture: headless Chrome screenshots/screen capture of the live site after the merge, stitched with ffmpeg,
subtitles burned in (drawtext), 1080p, ≤ 30.0 s. Optional voice-over.
