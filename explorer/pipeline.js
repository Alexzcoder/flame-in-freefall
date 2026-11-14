// "Pipeline" tab: animated walk-through from raw PSI files to a training-ready matrix.
// Injected into the page by view.py (uses D, gb, esc, kindTotals, runs, name, main from there).
const NS = 'http://www.w3.org/2000/svg';
let PL = {stage: 0, token: 0, timer: null, playing: false};
const INV_C = {FLEX: '#5aa9ff', 'BASS-II': '#ff7a2f', 'SAFFIRE-I': '#3ecf8e', 'SAFFIRE-II': '#2dd4bf', 'CFI-G': '#c084fc'};
const KIND_C = {archive: '#7c5cff', video: '#ff5c8a', sensor: '#5aa9ff', doc: '#8a93a6', image: '#3ecf8e', other: '#5d6577'};

function S(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function T(parent, x, y, str, attrs) { const t = S('text', {x, y, ...(attrs || {})}, parent); t.textContent = str; return t; }
function later(ms, fn) { const tok = PL.token; setTimeout(() => { if (tok === PL.token) fn(); }, ms); }
// fade/slide an element in after `delay` seconds; `from` is the starting CSS transform
function A(node, delay, from) {
  node.style.opacity = 0; node.style.transform = from || 'translate(0px,14px)';
  node.style.transition = `opacity .6s ease ${delay}s, transform .9s cubic-bezier(.2,.7,.2,1) ${delay}s`;
  requestAnimationFrame(() => requestAnimationFrame(() => { node.style.opacity = 1; node.style.transform = 'translate(0px,0px)'; }));
  return node;
}
function box(p, x, y, w, h, fill, stroke, rx) { return S('rect', {x, y, width: w, height: h, rx: rx ?? 6, fill, stroke: stroke || 'none'}, p); }
function arrow(p, x1, y1, x2, y2, delay) {
  const l = S('line', {x1, y1, x2, y2, stroke: '#ff7a2f', 'stroke-width': 2, 'marker-end': 'url(#ah)'}, p);
  const len = Math.hypot(x2 - x1, y2 - y1); l.style.strokeDasharray = len; l.style.strokeDashoffset = len;
  l.style.transition = `stroke-dashoffset .7s ease ${delay}s`; requestAnimationFrame(() => requestAnimationFrame(() => l.style.strokeDashoffset = 0));
  return l;
}

const STAGES = [
  {name: '1 · Raw archive', title: 'Start: 24 investigations, 7.8 TB on NASA S3', text: 'Each crate is one PSI combustion investigation; the bands show what its bytes are. About 99 % is zipped camera frames and video (purple/pink). That media stays on S3 and is referenced by file name. We download only metadata and the run tables (orange chips): about 22 MB. That small slice is what we train on.', eli5: "Treat PSI as a data lake with a strongly skewed size distribution. Bytes are concentrated in unstructured media (frames, video), while information relevant to modelling sits in small structured tables. We pull the full file manifest (≈36k files with sizes), but only materialise the structured layer: run tables plus metadata. Media is kept as a key (file name ↔ test ID) so it can be joined lazily, which is the usual reference-not-copy pattern for large panel datasets.", code: "fetch.py \u2192 GET /geode-py/ws/repo/investigations/PSI-xx (file list)  +  download '*Experimental table*.csv'", words: [["Manifest", "Index of every file with path and size; lets us plan downloads without fetching anything."], ["Run table", "Investigation-level CSV; one observation per test (where it is well formed)."], ["Lazy join", "Store the key now, fetch the large object only on demand."]], draw: s1},
  {name: '2 · Messy run tables', title: 'The run tables are useful but messy', text: 'Every investigation logged its tests differently. Pressure is in mmHg in one table and bar in another, O₂ is a percentage, a fraction or a range, material and size share one text cell, and one cell can hold several values. Highlighted cells cannot go into a model as they are.', eli5: "This is a heterogeneous, multi-source panel with no shared data dictionary. Columns that mean the same thing use different units (mmHg, bar, atm) and representations (fraction, %, interval, free text), and some cells are compound or interval-censored (\"21.5 - 21.7\", \"0.9 1.3 2.75\"). Observation units also differ: per run, per test day, or per range of conditions. Before any estimation, the variables need to be made commensurable, and the unit of observation must be made consistent.", code: "pd.read_csv(...) works, but the columns mean different things in every file", words: [["Commensurable", "Same quantity, same unit, same scale, so values can be compared or pooled."], ["Interval data", "A range instead of a point value; we store the midpoint and keep the bounds in extra."], ["Unit of observation", "What one row represents. Mixing runs with test days would bias any pooled estimate."]], draw: s2},
  {name: '3 · Normalize', title: 'One Normalizer class per investigation → shared Run schema', text: 'Each normalizer parses its own table into the same Run object (flame/schema.py). Units become part of the field name (kPa, cm/s, mm), O₂ is always a fraction, and outcomes come from a fixed set of values. Anything we cannot derive honestly becomes null, never a guess.', eli5: "Each investigation gets a deterministic mapping f_i: raw row → Run, implemented as one Normalizer subclass. The target space is a fixed typed schema: SI-style units encoded in the field name, gas composition as mole fractions, outcomes from a closed set of categories. Anything not identifiable from the source is null, never imputed at this stage. Imputation is a modelling decision and belongs downstream, where it can be documented and tested.", code: "class FlexNormalizer(Normalizer): def to_run(self, row) -> Run   # one class per investigation", words: [["Schema", "The typed codomain every f_i maps into (flame/schema.py)."], ["Closed vocabulary", "A categorical variable with a fixed set of allowed levels; it rejects typos and synonyms."], ["Provenance", "source {file, row} on every Run, so every value can be traced back for audit."]], draw: s3},
  {name: '4 · Join', title: 'Concatenate all runs → one tidy table', text: 'Because every normalizer outputs the same schema, joining is just concatenation: pd.json_normalize(runs) gives about 1,800 rows × 30 columns. Hatched cells are missing values. Missing is NOT zero: an unmeasured airflow is not still air.', eli5: "Because all f_i share a codomain, the join is a row-wise union (an unbalanced, long-format panel), not a key-based merge. The result is about 1,800 × 30 with block-structured missingness: whether a value is missing depends on the investigation, i.e. on the instrument that ran it. That is missing-not-at-random by design, so missing values must not be zero-filled or mean-imputed across the whole sample.", code: "df = pd.json_normalize(json.load(open('data/runs.json'))['runs'])   # ~1,800 rows \u00d7 30 columns", words: [["Long format", "One row per observation, one column per variable; ideal for pandas/sklearn."], ["Block missingness", "Missing patterns aligned with source groups, not random cells."], ["MNAR", "Missing not at random: missingness depends on the process that generated the data, so naive imputation biases estimates."]], draw: s4},
  {name: '5 · Encode', title: 'Encode → feature matrix X and target y', text: 'Categories become one-hot columns (phase: solid/liquid/gas). Numbers are scaled to 0–1 (pressure and flow on a log scale). Every column that can be missing gets a mask column (1 = missing) and its value is filled with 0, so the network can tell "zero" from "unknown". Rows without the target are left out of that target, not filled.', eli5: "Build the design matrix X = [D | Z | M] and the target y. D holds dummy variables for categoricals (one-hot; drop one level for linear models to avoid the dummy-variable trap). Z holds continuous regressors after a monotone transform and scaling: log for pressure and flow, which span orders of magnitude, then min–max or z-scoring. M holds missingness indicators, so the model can learn a separate intercept for \"unknown\" (the classic missing-indicator method). y is the log of the outcome. Rows where y is missing are excluded for that target, not imputed. For high-cardinality fuels, replace dummies with physical covariates (heat of combustion, boiling point, molar mass), so the model can generalise to fuels it hasn't seen.", code: "OneHotEncoder(phase) | MinMaxScaler(log p, log flow, O\u2082) | df[col].isna() \u2192 mask | y = log(burn_time_s)", words: [["Design matrix", "n × p matrix of regressors."], ["Dummy-variable trap", "Perfect collinearity when all k levels plus an intercept are included."], ["Missing-indicator method", "Fill with a constant and add a 0/1 flag; the flag absorbs the level shift."], ["Log transform", "Turns multiplicative, heavy-tailed scales into roughly additive ones."]], draw: s5},
  {name: '6 · Split & train', title: 'Train per family, split by campaign, compare with physics', text: 'Outcomes are only comparable within a family: droplets report burning rate and extinction diameter, solids report spread rate. So we train one small model per family. Splits are by test day / campaign, not by random row, so runs from one session never appear in both train and test (that would leak). Model predictions and physics-engine predictions are both scored against real NASA runs.', eli5: "Outcomes are only comparable within a family (droplet burning rate K, solid spread rate, gas-flame extinction), so we fit one model per family instead of a pooled model with an incoherent y. Runs from the same test day share latent conditions such as calibration and hardware state, so they are intra-cluster correlated. A random row split would leak cluster effects into the test set and overstate out-of-sample performance (the same failure as look-ahead bias in backtesting). We therefore use GroupKFold over test days. The benchmark is a three-way comparison on the held-out set: the ML model, the physics engine (a structural model) and the observed outcome. That is reduced-form versus structural, scored on MAE or log-loss.", code: "GroupShuffleSplit(groups=test_day) \u2192 fit(X_train, y_train) \u2192 score(model, physics_engine) on X_test vs y_test", words: [["Clustered data", "Observations within a group are correlated; treat the group as the unit of sampling."], ["GroupKFold", "Cross-validation where whole groups go to one fold; no cluster spans train and test."], ["Leakage", "Information from the test distribution entering training; scores become optimistic."], ["Structural vs reduced-form", "Physics-based model with interpretable parameters vs. a flexible predictive fit."]], draw: s6},
];

function pipeline() {
  main.innerHTML = `<h1>From raw NASA files to a training set</h1>
  <div class="mute">An animated walk-through of the data pipeline using real values from the PSI run tables. Use ← → or the buttons.</div>
  <div class="eli5 intro"><div class="tag">💡 The problem</div><p>Without buoyancy there is no natural convection, so microgravity flames are diffusion-limited: spherical, cooler and slower, and they can persist at O₂ levels and flows where they would extinguish in 1 g. Spacecraft fire risk therefore cannot be extrapolated from ground data. PSI holds about 2,000 instrumented ISS combustion runs across 24 investigations, recorded in incompatible formats. The goal: harmonise them into one panel, estimate E[outcome | fuel, O₂, pressure, flow, g] within each experiment family, and benchmark that against a physics-based model. The six steps below are the ETL and estimation design.</p></div>
  <div class="pl-ctl"><button id="pl-prev">← Prev</button><button id="pl-play" class="pri">▶ Play all</button><button id="pl-next">Next →</button><button id="pl-re">↻ Replay step</button><div class="dots" id="pl-dots"></div></div>
  <svg id="stage" viewBox="0 0 1000 540"></svg><div class="prog"><i id="pl-bar"></i></div><div id="cap"></div>`;
  document.getElementById('pl-dots').innerHTML = STAGES.map((s, i) => `<span data-s="${i}">${s.name}</span>`).join('');
  document.getElementById('pl-dots').onclick = e => { const s = e.target.dataset.s; if (s !== undefined) { pause(); go(+s); } };
  document.getElementById('pl-prev').onclick = () => { pause(); go(Math.max(0, PL.stage - 1)); };
  document.getElementById('pl-next').onclick = () => { pause(); go(Math.min(STAGES.length - 1, PL.stage + 1)); };
  document.getElementById('pl-re').onclick = () => go(PL.stage);
  document.getElementById('pl-play').onclick = () => PL.playing ? pause() : play();
  const m = location.hash.match(/^#pipeline\/(\d)/); if (m) PL.stage = Math.min(STAGES.length, Math.max(1, +m[1])) - 1;
  go(PL.stage);
}
function stopPipeline() { pause(); PL.token++; }
function pause() { PL.playing = false; clearInterval(PL.timer); const b = document.getElementById('pl-play'); if (b) b.textContent = '▶ Play all'; }
function play() {
  PL.playing = true; document.getElementById('pl-play').textContent = '❚❚ Pause';
  if (PL.stage === STAGES.length - 1) go(0);
  clearInterval(PL.timer);
  PL.timer = setInterval(() => { if (PL.stage < STAGES.length - 1) go(PL.stage + 1); else pause(); }, 9000);
}
document.addEventListener('keydown', e => {
  if (!location.hash.startsWith('#pipeline') || e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowRight') { pause(); go(Math.min(STAGES.length - 1, PL.stage + 1)); }
  if (e.key === 'ArrowLeft') { pause(); go(Math.max(0, PL.stage - 1)); }
});
function go(i) {
  PL.stage = i; PL.token++;
  const svg = document.getElementById('stage'); if (!svg) return;
  svg.innerHTML = `<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#ff7a2f"/></marker>
    <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#1a1e27"/><line x1="0" y1="0" x2="0" y2="6" stroke="#3a4050" stroke-width="2"/></pattern></defs>`;
  document.querySelectorAll('#pl-dots span').forEach((d, k) => d.classList.toggle('on', k === i));
  const st = STAGES[i];
  document.getElementById('cap').innerHTML = `<h3>Step ${i + 1}: ${st.title}</h3>
    <div class="cap-grid"><div class="eli5"><div class="tag">💡 Intuition</div><p>${esc(st.eli5)}</p></div>
    <div class="tech"><div class="tag">🔧 What actually happens</div><p>${esc(st.text)}</p><div class="tag">💻 In code</div><code>${esc(st.code)}</code></div></div>
    <div class="words"><div class="tag">📖 Words used in this step</div>${st.words.map(w => `<div><b>${esc(w[0])}</b><span>${esc(w[1])}</span></div>`).join('')}</div>`;
  const bar = document.getElementById('pl-bar'); bar.style.transition = 'none'; bar.style.width = (i / STAGES.length * 100) + '%';
  requestAnimationFrame(() => { bar.style.transition = 'width 8.5s linear'; bar.style.width = ((i + 1) / STAGES.length * 100) + '%'; });
  st.draw(svg);
}

// ---- stage 1: crates of investigations, media fades, run tables fly out ----
function s1(svg) {
  const inv = [...D].sort((a, b) => b.size - a.size), cols = 6, cw = 104, ch = 118;
  const tgt = {x: 700, y: 120, w: 280, h: 300};
  const tb = A(S('g', {}, svg), 2.6);
  box(tb, tgt.x, tgt.y, tgt.w, tgt.h, '#1d1510', '#ff7a2f', 10);
  T(tb, tgt.x + 16, tgt.y + 28, 'data/raw  (we download)', {'font-weight': 600, fill: '#ffb08a'});
  T(tb, tgt.x + 16, tgt.y + 50, 'metadata + run tables ≈ 22 MB', {'font-size': 12, fill: '#8a93a6'});
  const allBytes = D.reduce((s, d) => s + d.size, 0);
  T(svg, 20, 24, `PSI combustion archive: ${gb(allBytes)}`, {'font-weight': 600});
  const media = [];
  inv.forEach((d, i) => {
    const x = 20 + (i % cols) * cw, y = 40 + Math.floor(i / cols) * ch;
    const g = A(S('g', {}, svg), i * 0.05);
    box(g, x, y, cw - 10, ch - 12, '#181c25', '#2a2f3a', 8);
    T(g, x + 8, y + 16, name(d).slice(0, 13), {'font-size': 11, 'font-weight': 600});
    const kt = kindTotals(d.files), tot = d.size || 1; let yy = y + 24; const H = 62;
    ['archive', 'video', 'sensor', 'doc', 'image', 'other'].forEach(k => {
      const h = kt[k] ? Math.max(1.5, kt[k][1] / tot * H) : 0; if (!h) return;
      const r = box(g, x + 8, yy, cw - 26, Math.min(h, y + 24 + H - yy), KIND_C[k], 'none', 2); yy += h;
      if (k === 'archive' || k === 'video') media.push(r);
    });
    T(g, x + 8, y + ch - 20, gb(d.size), {'font-size': 10, fill: '#8a93a6', class: 'mono'});
    // chip = metadata (+ run table) that we keep
    const fx = tgt.x + 18 + (i % 6) * 42, fy = tgt.y + 76 + Math.floor(i / 6) * 50;
    const sx = x + cw - 34, sy = y + ch - 30;
    const chip = S('g', {}, svg);
    box(chip, fx, fy, 34, 22, runs(d) ? '#ff7a2f' : '#5d6577', 'none', 4);
    T(chip, fx + 17, fy + 15, runs(d) ? 'CSV' : 'meta', {'font-size': 9, 'text-anchor': 'middle', fill: '#1a0d05', 'font-weight': 700});
    T(chip, fx + 17, fy + 36, name(d).slice(0, 7), {'font-size': 8, 'text-anchor': 'middle', fill: '#8a93a6'});
    A(chip, 2.8 + i * 0.06, `translate(${sx - fx}px,${sy - fy}px)`);
  });
  later(1700, () => media.forEach(r => { r.style.transition = 'opacity 1s'; r.style.opacity = 0.18; }));
  const lg = A(S('g', {}, svg), 1.9);
  Object.entries({archive: 'zipped frames', video: 'video', sensor: 'sensor logs', doc: 'docs', image: 'images'}).forEach(([k, l], j) => {
    box(lg, 20 + j * 120, 520, 12, 12, KIND_C[k], 'none', 2); T(lg, 38 + j * 120, 530, l, {'font-size': 11, fill: '#8a93a6'});
  });
  T(A(S('g', {}, svg), 2.2), 700, 470, 'media stays on S3, linked by file name', {'font-size': 12, fill: '#8a93a6'});
}

// ---- stage 2: four messy table cards (real snippets) ----
const MESSY = [
  {t: 'FLEX (PSI-69)', c: '#5aa9ff', h: ['Fuel', 'Ambient pressure; mmHg', 'O initial; mole frac', 'Droplet d; mm', 'Test end'],
    r: [['Methanol', '*757.7', '0.21', '1.69', 'Disruption'], ['Methanol', '*773.7', '0.18', '3.43', 'Extinction']]},
  {t: 'BASS-II (PSI-25)', c: '#ff7a2f', h: ['Test #', 'Fuel Sample Material', 'Fan display', 'O2 % by vol'],
    r: [['B1', '*100 micron PMMA film 2 cm wide', '*62', '*22.2'], ['B6', '*2 cm 0.1 mm PMMA film', '*0.9 1.3 2.75', '21']]},
  {t: 'SAFFIRE-I / II', c: '#3ecf8e', h: ['Sample', 'Material', 'Thickness', 'Air Flow', 'Percent O2', 'Burn Time'],
    r: [['S1', 'SIBAL Fabric', '0.37', '20', '*21.5 - 21.7', '420'], ['2-1', 'Silicone', '*0.27 mm', '*20 cm/s', '*~ 21.5', '*Insignificant']]},
  {t: 'CFI-G (PSI-159)', c: '#c084fc', h: ['Fuel', 'Test', 'XO2 before', 'approx p (bar)', 'burn time', 'Self-ext?'],
    r: [['ethane', '21088A1', '0.3939', '*0.944', '50', '*SE']]},
];
function s2(svg) {
  MESSY.forEach((m, i) => {
    const x = 20 + (i % 2) * 490, y = 20 + Math.floor(i / 2) * 260, w = 470;
    const g = A(S('g', {}, svg), i * 0.35);
    box(g, x, y, w, 240, '#181c25', '#2a2f3a', 10); box(g, x, y, 5, 240, m.c, 'none', 2);
    T(g, x + 18, y + 26, m.t, {'font-weight': 700, fill: m.c});
    const cw = (w - 30) / m.h.length;
    m.h.forEach((h, j) => { box(g, x + 15 + j * cw, y + 42, cw - 3, 40, '#232834', 'none', 3);
      wrap(g, x + 19 + j * cw, y + 57, h, cw - 8, 10, '#ffffff'); });
    m.r.forEach((row, k) => row.forEach((v, j) => {
      const bad = v.startsWith('*'), vv = bad ? v.slice(1) : v, cy = y + 90 + k * 62;
      const cell = box(g, x + 15 + j * cw, cy, cw - 3, 54, bad ? 'rgba(255,122,47,.16)' : '#12151c', bad ? '#ff7a2f' : '#232834', 3);
      wrap(g, x + 19 + j * cw, cy + 16, vv, cw - 8, 11, bad ? '#ffb08a' : '#d7dae0', 'mono');
      if (bad) { cell.style.opacity = 0; cell.style.transition = 'opacity .5s'; later(1600 + i * 250 + j * 60, () => cell.style.opacity = 1); }
    }));
  });
}
function wrap(p, x, y, str, w, fs, fill, cls) {
  const maxc = Math.max(4, Math.floor(w / (fs * 0.6))), words = String(str).split(/\s+/), lines = [''];
  words.forEach(wd => { if ((lines[lines.length - 1] + ' ' + wd).trim().length > maxc) lines.push(wd); else lines[lines.length - 1] = (lines[lines.length - 1] + ' ' + wd).trim(); });
  lines.slice(0, 3).forEach((l, i) => T(p, x, y + i * (fs + 3), l.length > maxc ? l.slice(0, maxc - 1) + '…' : l, {'font-size': fs, fill, class: cls || ''}));
}

// ---- stage 3: raw value -> schema field ----
const NORM = [
  ['FLEX', 'Ambient pressure; mmHg = 757.7', 'atmosphere.pressure_kpa = 101.02', '× 0.13332'],
  ['CFI-G', 'approx p (bar) = 0.944', 'atmosphere.pressure_kpa = 94.44', '× 100'],
  ['SAFFIRE-I', 'Percent O2 = "21.5 - 21.7"', 'atmosphere.o2_frac = 0.216', 'range → midpoint ÷ 100'],
  ['BASS-II', '"100 micron PMMA film 2 cm wide"', 'fuel = {name: pmma, geometry: film, thickness_mm: 0.1, width_mm: 20}', 'parse text'],
  ['FLEX', 'Test end = "Disruption"', 'outcome.result = "disruption"', 'fixed set of values'],
  ['CFI-G', 'Self-ext or flow term = "SE"', 'outcome.result = "extinction"', 'code → label'],
  ['BASS-II', 'Fan display = 62', 'flow.velocity_cm_s = null   (+ extra.fan_display = 62)', 'needs calibration → null'],
];
function s3(svg) {
  T(A(S('g', {}, svg), 0), 20, 26, 'raw cell (as logged)', {'font-size': 12, fill: '#8a93a6', 'font-weight': 600});
  T(A(S('g', {}, svg), 0), 560, 26, 'Run schema field (flame/schema.py)', {'font-size': 12, fill: '#8a93a6', 'font-weight': 600});
  NORM.forEach(([inv, raw, out, how], i) => {
    const y = 40 + i * 70, d = 0.3 + i * 0.9;
    const g = A(S('g', {}, svg), d, 'translate(-20px,0px)');
    box(g, 20, y, 400, 52, '#181c25', '#2a2f3a', 8); box(g, 20, y, 5, 52, INV_C[inv] || '#888', 'none', 2);
    T(g, 36, y + 20, inv, {'font-size': 11, fill: INV_C[inv] || '#888', 'font-weight': 700});
    T(g, 36, y + 40, raw, {'font-size': 12, class: 'mono', fill: '#ffb08a'});
    arrow(svg, 428, y + 26, 550, y + 26, d + 0.35);
    T(A(S('g', {}, svg), d + 0.4), 489, y + 18, how, {'font-size': 10, 'text-anchor': 'middle', fill: '#8a93a6'});
    const o = A(S('g', {}, svg), d + 0.7, 'translate(20px,0px)');
    const isNull = out.includes('null');
    box(o, 560, y, 420, 52, isNull ? 'url(#hatch)' : 'rgba(62,207,142,.10)', isNull ? '#5d6577' : '#3ecf8e', 8);
    wrap(o, 574, y + 22, out, 400, 12, isNull ? '#c9cdd6' : '#b9f5d8', 'mono');
  });
}

// ---- stage 4: the joined table ----
const JOIN_COLS = ['run', 'fuel', 'phase', 'O₂', 'p kPa', 'flow cm/s', 'burn s', 'ext. d mm', 'spread mm/s'];
const JOIN_ROWS = [
  ['FLEX', 'PSI-69/20CAL08', 'methanol', 'liquid', 0.21, 101.0, 0, 4.3, 0.89, null],
  ['FLEX', 'PSI-69/204F001', 'methanol', 'liquid', 0.18, 103.2, 0, 23.2, null, null],
  ['BASS-II', 'PSI-25/B1', 'pmma', 'solid', 0.222, null, null, null, null, null],
  ['SAFFIRE-I', 'PSI-98/S1', 'sibal', 'solid', 0.216, null, 20, 420, null, null],
  ['SAFFIRE-II', 'PSI-99/2-1', 'silicone', 'solid', 0.215, null, 20, null, null, null],
  ['CFI-G', 'PSI-159/21088A1', 'ethane', 'gas', 0.394, 94.4, 0, 50, null, null],
];
function s4(svg) {
  const x0 = 20, y0 = 40, cw = [150, 90, 70, 70, 80, 90, 80, 100, 110], rh = 50;
  let x = x0; const hg = A(S('g', {}, svg), 0);
  JOIN_COLS.forEach((c, j) => { box(hg, x, y0, cw[j] - 4, 34, '#232834', 'none', 4); T(hg, x + 8, y0 + 22, c, {'font-size': 12, 'font-weight': 600, fill: '#fff'}); x += cw[j]; });
  JOIN_ROWS.forEach(([inv, ...vals], i) => {
    const y = y0 + 44 + i * rh, g = A(S('g', {}, svg), 0.5 + i * 0.45, 'translate(-60px,0px)');
    box(g, x0 - 10, y, 5, rh - 6, INV_C[inv], 'none', 2);
    let xx = x0;
    vals.forEach((v, j) => {
      const nul = v === null;
      box(g, xx, y, cw[j] - 4, rh - 6, nul ? 'url(#hatch)' : '#181c25', '#232834', 4);
      T(g, xx + 8, y + 27, nul ? 'null' : String(v), {'font-size': 12, class: 'mono', fill: nul ? '#6b7385' : j === 0 ? INV_C[inv] : '#d7dae0'});
      xx += cw[j];
    });
  });
  const f = A(S('g', {}, svg), 3.6);
  T(f, x0, y0 + 44 + JOIN_ROWS.length * rh + 26, '⋮  ≈ 1,800 rows from ~12 investigations', {'font-size': 13, fill: '#8a93a6'});
  box(f, 620, 440, 360, 76, '#1d1510', '#ff7a2f', 8);
  T(f, 636, 466, 'pd.json_normalize(dataset["runs"])', {'font-size': 13, class: 'mono', fill: '#ffb08a'});
  T(f, 636, 492, 'hatched = missing ≠ 0', {'font-size': 12, fill: '#c9cdd6'});
}

// ---- stage 5: encode into X / mask / y ----
function s5(svg) {
  const rows = JOIN_ROWS.map(([inv, id, fuel, phase, o2, p, flow, burn]) => ({inv, id, phase, o2, p, flow, burn}));
  const sc = (v, a, b) => Math.max(0, Math.min(1, (v - a) / (b - a)));
  const cols = [
    {g: 'one-hot phase', n: 'solid', f: r => +(r.phase === 'solid')},
    {g: 'one-hot phase', n: 'liquid', f: r => +(r.phase === 'liquid')},
    {g: 'one-hot phase', n: 'gas', f: r => +(r.phase === 'gas')},
    {g: 'scaled numbers', n: 'O₂', f: r => sc(r.o2, 0.15, 0.40)},
    {g: 'scaled numbers', n: 'log p', f: r => r.p == null ? 0 : sc(Math.log(r.p), Math.log(50), Math.log(110))},
    {g: 'scaled numbers', n: 'log flow', f: r => r.flow == null ? 0 : sc(Math.log1p(r.flow), 0, Math.log1p(30))},
    {g: 'missing masks', n: 'p?', f: r => +(r.p == null), m: 1},
    {g: 'missing masks', n: 'flow?', f: r => +(r.flow == null), m: 1},
  ];
  const x0 = 150, y0 = 90, cs = 62, rh = 52;
  rows.forEach((r, i) => T(A(S('g', {}, svg), 0.1 * i), 20, y0 + i * rh + 32, r.id, {'font-size': 11, class: 'mono', fill: INV_C[r.inv]}));
  let lastG = '';
  cols.forEach((c, j) => {
    const d = 0.6 + j * 0.35, x = x0 + j * cs + (c.g === 'scaled numbers' ? 14 : c.g === 'missing masks' ? 28 : 0);
    if (c.g !== lastG) { T(A(S('g', {}, svg), d), x, 40, c.g, {'font-size': 11, fill: '#ff7a2f', 'font-weight': 600}); lastG = c.g; }
    T(A(S('g', {}, svg), d), x + cs / 2 - 3, 70, c.n, {'font-size': 11, 'text-anchor': 'middle', fill: '#fff'});
    rows.forEach((r, i) => {
      const v = c.f(r), g = A(S('g', {}, svg), d + i * 0.05, 'translate(0px,-10px)');
      const col = c.m ? (v ? '#ff5c8a' : '#232834') : `rgba(90,169,255,${0.12 + 0.88 * v})`;
      box(g, x, y0 + i * rh, cs - 6, rh - 8, col, '#2a2f3a', 4);
      T(g, x + (cs - 6) / 2, y0 + i * rh + 27, v.toFixed(c.m || c.g === 'one-hot phase' ? 0 : 2), {'font-size': 11, 'text-anchor': 'middle', class: 'mono', fill: '#fff'});
    });
  });
  // target y
  const yx = x0 + cols.length * cs + 70, d = 0.6 + cols.length * 0.35 + 0.3;
  T(A(S('g', {}, svg), d), yx, 40, 'target y', {'font-size': 11, fill: '#3ecf8e', 'font-weight': 600});
  T(A(S('g', {}, svg), d), yx + 40, 70, 'log burn s', {'font-size': 11, 'text-anchor': 'middle', fill: '#fff'});
  rows.forEach((r, i) => {
    const g = A(S('g', {}, svg), d + i * 0.08), has = r.burn != null;
    box(g, yx, y0 + i * rh, 80, rh - 8, has ? 'rgba(62,207,142,.25)' : 'url(#hatch)', has ? '#3ecf8e' : '#3a4050', 4);
    T(g, yx + 40, y0 + i * rh + 27, has ? Math.log(r.burn).toFixed(2) : 'drop', {'font-size': 11, 'text-anchor': 'middle', class: 'mono', fill: has ? '#b9f5d8' : '#6b7385'});
  });
  const f = A(S('g', {}, svg), d + 0.8);
  T(f, 20, 420, 'X = [one-hot | scaled | masks]   →   shape (n_runs, n_features)', {'font-size': 13, class: 'mono', fill: '#c9cdd6'});
  T(f, 20, 446, 'y = observed outcome; rows without it are dropped for that target, never filled', {'font-size': 13, class: 'mono', fill: '#c9cdd6'});
  T(f, 20, 472, 'many fuels? use fuel properties (heat of combustion, boiling point) instead of one-hot per name', {'font-size': 12, fill: '#8a93a6'});
}

// ---- stage 6: families, grouped split, model vs physics vs real ----
function s6(svg) {
  const cnt = names => D.reduce((s, d) => s + d.tables.filter(t => names.includes(t.name)).reduce((a, t) => a + t.rows.length, 0), 0);
  const fam = [
    {n: 'Droplets', s: 'FLEX + CFI', c: '#5aa9ff', k: cnt(['FLEX', 'CFI']), y: 'burning rate, extinction d'},
    {n: 'Gaseous flames', s: 'CFI-G + Flame Design', c: '#c084fc', k: cnt(['CFI-G_Normal Flames', 'CFI-G_Inverse Flames', 'Flame Design_Normal Flame', 'Flame Design_Inverse Flame']), y: 'self-extinction, cool flame'},
    {n: 'Solids', s: 'BASS-II + SAFFIRE', c: '#ff7a2f', k: cnt(['BASS-II', 'SAFFIRE-1', 'SAFFIRE-2', 'SAFFIRE-3']), y: 'ignition, spread rate'},
  ];
  const max = Math.max(...fam.map(f => f.k)), W = 380;
  T(A(S('g', {}, svg), 0), 20, 28, 'one model per family · split by test day / campaign', {'font-size': 12, fill: '#8a93a6', 'font-weight': 600});
  fam.forEach((f, i) => {
    const y = 50 + i * 120, g = A(S('g', {}, svg), 0.3 + i * 0.4), w = Math.max(60, f.k / max * W);
    T(g, 20, y + 14, `${f.n}  ·  ${f.k} runs`, {'font-weight': 700, fill: f.c});
    T(g, 20, y + 32, f.s + '  →  y: ' + f.y, {'font-size': 11, fill: '#8a93a6'});
    [[0, .7, 'train'], [.7, .15, 'val'], [.85, .15, 'test']].forEach(([o, p, l], k) => {
      const seg = box(g, 20 + o * w, y + 44, p * w - 2, 30, f.c, 'none', 4); seg.setAttribute('opacity', [0.9, 0.55, 0.3][k]);
      if (w * p > 34) T(g, 20 + o * w + 6, y + 64, l, {'font-size': 11, fill: '#0b0d12', 'font-weight': 600});
    });
  });
  // model diagram
  const g = A(S('g', {}, svg), 1.8);
  box(g, 470, 150, 90, 60, '#181c25', '#5aa9ff', 8); T(g, 515, 185, 'X', {'text-anchor': 'middle', 'font-weight': 700, 'font-size': 18});
  const layers = [5, 7, 7, 1], nx = [600, 660, 720, 780], nodes = [];
  layers.forEach((n, L) => { nodes[L] = []; for (let k = 0; k < n; k++) nodes[L].push([nx[L], 180 + (k - (n - 1) / 2) * 22]); });
  const net = A(S('g', {}, svg), 2.2);
  for (let L = 0; L < layers.length - 1; L++) nodes[L].forEach(a => nodes[L + 1].forEach(b => S('line', {x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: '#2f3644', 'stroke-width': 1}, net)));
  nodes.flat().forEach(([x, y]) => S('circle', {cx: x, cy: y, r: 6, fill: '#5aa9ff'}, net));
  T(net, 690, 270, 'small MLP / gradient boosting', {'text-anchor': 'middle', 'font-size': 11, fill: '#8a93a6'});
  arrow(svg, 562, 180, 590, 180, 2.4);
  const p = A(S('g', {}, svg), 3.0);
  box(p, 470, 330, 330, 60, '#181c25', '#c084fc', 8);
  T(p, 635, 356, 'physics engine (teammate)', {'text-anchor': 'middle', 'font-weight': 600});
  T(p, 635, 376, 'predict(run.conditions) → Outcome', {'text-anchor': 'middle', 'font-size': 11, class: 'mono', fill: '#c9cdd6'});
  const r = A(S('g', {}, svg), 3.6);
  box(r, 860, 230, 120, 110, 'rgba(62,207,142,.12)', '#3ecf8e', 10);
  T(r, 920, 262, 'real NASA', {'text-anchor': 'middle', 'font-weight': 700, fill: '#b9f5d8'});
  T(r, 920, 280, 'run outcome', {'text-anchor': 'middle', 'font-weight': 700, fill: '#b9f5d8'});
  T(r, 920, 306, 'score both:', {'text-anchor': 'middle', 'font-size': 11, fill: '#c9cdd6'});
  T(r, 920, 324, 'MAE · accuracy', {'text-anchor': 'middle', 'font-size': 11, class: 'mono', fill: '#c9cdd6'});
  arrow(svg, 790, 180, 865, 245, 3.8); arrow(svg, 802, 360, 865, 320, 4.0);
  T(A(S('g', {}, svg), 4.4), 470, 450, 'Why grouped splits: runs from one test day share hardware state and calibration.', {'font-size': 12, fill: '#8a93a6'});
  T(A(S('g', {}, svg), 4.6), 470, 470, 'Random row splits would leak that into the test score.', {'font-size': 12, fill: '#8a93a6'});
}
