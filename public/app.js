const PSI_KPA = 6.89476;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const api = async (path, opts) => { const r = await fetch(path, opts); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json(); };
const CAT_C = {solid: '#ff7a2f', droplet: '#5aa9ff', gaseous: '#c084fc', smoke: '#3ecf8e', other: '#8a93a6'};
const lay = o => ({paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: {color: '#c9cdd6', family: 'Inter'},
  legend: {orientation: 'h', y: -0.18}, margin: {t: 20, r: 20, l: 60, b: 60}, ...o,
  xaxis: {gridcolor: '#232834', zeroline: false, ...(o.xaxis || {})}, yaxis: {gridcolor: '#232834', zeroline: false, ...(o.yaxis || {})}});
let META;
// Plain-language explanations for every technical term (hover, focus or tap). Used via data-term="key" or tip().
const TIPS = {
  o2: 'Share of the air that is oxygen. Normal air is 21 %. More oxygen: materials ignite more easily and burn faster.',
  pressure: 'How hard the air pushes. Sea level is 14.7 psi (101 kPa). Habitats at lower pressure add extra oxygen so people can breathe, which raises fire risk.',
  airflow: 'Speed of the air moving past the burning item, from ventilation fans (cm/s). In space there is no natural draft, so the fans decide how much fresh oxygen a fire gets.',
  gravity: 'All NASA data here is from microgravity (about 0 g, on the ISS or a cargo ship). Moon, Mars and Earth gravity make hot gas rise, which changes how flames behave. Treat results as bounds.',
  fuel: 'What burns. Solid materials (fabrics, plastics) are closest to a real cabin fire; droplets and gas flames teach the underlying physics.',
  near: 'Close match: this experiment ran in very similar conditions to your settings.',
  partial: 'Partly similar: one or two settings differ noticeably.',
  far: 'Not similar: shown only because it is the closest available. Conditions were different.',
  assumed: 'Not measured in the experiment. We filled in normal ISS cabin air (14.7 psi, 21 % oxygen).',
  censored: 'The run was stopped while the flame was still burning, so the real burn time was longer than shown.',
  score: 'Relevance 0–100: 50 % how close its experiments are to this atmosphere, 20 % whether they recorded results, 20 % how close the fuel is to a cabin fire (solids highest), 10 % how directly it targets fire safety.',
  coverage: 'How many real experiments ran near these settings: well covered (10 or more), sparse (1–9), no nearby data (0).',
  similarity: 'Similarity from 0 to 1 between the experiment and your settings (1 = same oxygen, pressure and airflow).',
  pillars: 'Prevention: stop fires starting and spreading. Detection: notice them early (smoke). Suppression: put them out.',
  outcome: 'What happened in the experiment: did it ignite, how it ended (burned out, went out, stopped), how long it burned.',
};
const tip = (k, label, cls = '') => `<span class="term ${cls}" tabindex="0" data-tip="${esc(TIPS[k])}">${label}</span>`;
function decorateTerms(root = document) {
  root.querySelectorAll('[data-term]').forEach(el => { el.classList.add('term'); el.tabIndex = 0; el.dataset.tip = TIPS[el.dataset.term]; el.removeAttribute('data-term'); });
}
document.addEventListener('click', e => {  // "start here" buttons: switch tab or scroll to an element
  const go = e.target.closest('[data-go]')?.dataset.go; if (!go) return;
  if (go.startsWith('#')) document.querySelector(go)?.scrollIntoView({behavior: 'smooth', block: 'start'}); else { show(go); window.scrollTo(0, 0); }
});

// ---------- tabs ----------
$('tabs').onclick = e => { const b = e.target.closest('button'); if (b) show(b.dataset.tab); };
function show(t) {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  document.querySelectorAll('.tab').forEach(s => s.classList.toggle('on', s.id === 'sec-' + t));
  history.replaceState(null, '', '#' + t);
  document.body.dataset.tab = t;  // lets CSS hide the Ember button on the Ask tab
  if (t === 'overview') Plotly.Plots.resize('map');
}

// ---------- overview ----------
async function overview() {
  const pts = await api('/api/coverage');
  const tile = (v, l) => `<div class="tile"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  $('tiles').innerHTML = tile(META.n_runs.toLocaleString(), 'experiment runs') + tile(META.n_with_outcome, 'with measured outcomes')
    + tile(META.n_investigations, 'NASA investigations') + tile(META.n_documents.toLocaleString(), 'report pages & papers searchable');
  const traces = [];
  for (const cat of Object.keys(CAT_C)) for (const asm of [false, true]) {
    const p = pts.filter(x => x.category === cat && x.assumed === asm);
    if (!p.length) continue;
    traces.push({type: 'scatter', mode: 'markers', name: `${cat}${asm ? ' (assumed p/O₂)' : ''}`,
      x: p.map(d => d.pressure_kpa / PSI_KPA), y: p.map(d => d.o2_pct),
      text: p.map(d => `${d.id}<br>${d.fuel}${d.has_outcome ? '' : ' · no outcome'}${asm ? ' · assumed' : ''}`), hoverinfo: 'text',
      marker: {size: 8, color: asm ? 'rgba(0,0,0,0)' : CAT_C[cat], line: {color: CAT_C[cat], width: asm ? 1.5 : 0}, opacity: 0.85}});
  }
  traces.unshift({type: 'scatter', mode: 'lines', name: 'Planned habitat zone', showlegend: false, fill: 'toself',
    fillcolor: 'rgba(0,0,0,0)', line: {width: 0}, x: [8, 12, 12, 8, 8], y: [25, 25, 40, 40, 25], hoveron: 'fills',
    text: 'Planned habitat zone: 25–40 % O₂ at 8–12 psi.<br>Covers the Moon base (30 %, 10.2 psi), NASA exploration atmosphere<br>(34 %, 8.2 psi) and Shuttle pre-spacewalk cabin (26.5 %, 10.2 psi).<br>Only FLEX fuel droplets were tested here; no solid materials.', hoverinfo: 'text'});
  traces.unshift({type: 'scatter', mode: 'markers+text', name: 'habitats', x: [14.7, 10.2], y: [21, 30], text: ['ISS', 'Moon Base'],
    textposition: 'top center', marker: {symbol: 'star', size: 18, color: '#ffd27a', line: {color: '#000', width: 1}}, hoverinfo: 'text'});
  Plotly.newPlot('map', traces, lay({xaxis: {title: 'Pressure (psi, log scale)', range: [Math.log10(4), Math.log10(75)], type: 'log', tickvals: [4, 5, 6, 8, 10, 12, 14.7, 20, 30, 40, 60], ticktext: ['4', '5', '6', '8', '10', '12', '14.7 (sea level)', '20', '30', '40', '60']}, yaxis: {title: 'Oxygen (%)', range: [10, 45]},
    shapes: [{type: 'rect', x0: 8, x1: 12, y0: 25, y1: 40, fillcolor: 'rgba(255,210,122,.10)', line: {color: '#ffd27a', dash: 'dot', width: 1.5}, layer: 'below'}],
    annotations: [{x: Math.log10(8.15), y: 39.3, xanchor: 'left', yanchor: 'top', showarrow: false, align: 'left',
      text: '<b>Planned habitat zone</b><br>25–40 % O₂ · 8–12 psi', font: {size: 11, color: '#ffd27a'}}]}),
    {displaylogo: false, responsive: true});
  const box = pts.filter(d => d.o2_pct >= 25 && d.o2_pct <= 40 && d.pressure_kpa >= 8 * PSI_KPA && d.pressure_kpa <= 12 * PSI_KPA && !d.assumed);
  const byInv = {}; box.forEach(d => byInv[d.inv] = (byInv[d.inv] || 0) + 1);
  const solidMax = Math.max(...pts.filter(d => d.category === 'solid').map(d => d.o2_pct));
  const FAM = {droplet: ['💧 Fuel droplets', 'A fuel drop burns as a perfect sphere. Measures burning rate and the size at which the flame goes out. Used to test suppressants (CO₂, helium).'],
    gaseous: ['🔵 Gas flames', 'Gas fed through a porous sphere or a jet. Studies soot, cool flames and extinction limits: the basic chemistry of flames.'],
    solid: ['🟧 Solid materials', 'Acrylic, fabrics, silicone burned in airflow, up to SAFFIRE\'s metre-scale fires in an empty cargo ship. Closest to a real cabin fire.'],
    smoke: ['🌫️ Smoke & dust', 'Smoke from overheated materials, to design detectors that work in microgravity. Mostly in reports, not run tables.']};
  $('families').innerHTML = Object.entries(FAM).map(([k, [t, d]]) => {
    const inv = META.investigations.filter(x => x.category === k);
    const runs = inv.reduce((s, x) => s + x.n_runs, 0), lab = inv.reduce((s, x) => s + x.n_with_outcome, 0);
    return `<div class="card ex"><h3>${t}</h3><p>${d}</p><div class="chips"><span>${inv.length} investigations</span><span>${runs} runs</span><span>${lab} with outcome</span></div>
      <div class="mute" style="font-size:12px;margin-top:6px">${inv.map(x => esc(x.acronym)).join(' · ')}</div></div>`;
  }).join('');
  $('finding').innerHTML = `<h3>Key finding</h3><p>Only <b>${box.length} runs</b> were tested near planned habitat atmospheres
    (${Object.entries(byInv).map(([k, v]) => `${esc(k)}: ${v}`).join(', ') || 'none'}). No solid cabin material in NASA's public PSI data
    was burned in microgravity above <b>${solidMax.toFixed(1)} % O₂</b>. Moon Base cabins are planned at 30 %+. How fabrics and plastics burn there
    is an open question the data can bound but not answer.</p>`;
}

// ---------- scenario ----------
// Published atmospheres. Many are far outside the tested data on purpose: the explorer then shows "no nearby data".
const PRESETS = [
  {g: 'Space', name: 'ISS cabin', o2: 21, psi: 14.7, flow: 10, grav: 0, note: 'ISS and most spacecraft: sea-level air, microgravity, ventilation 5–20 cm/s.'},
  {g: 'Space', name: 'Moon base', o2: 30, psi: 10.2, flow: 10, grav: 0.166, note: 'Challenge brief: lunar habitats planned at 30 %+ O₂ and ~10.2 psi, which makes materials more flammable.'},
  {g: 'Space', name: 'Pressurized rover', o2: 30, psi: 10.2, flow: 20, grav: 0.166, note: 'Same atmosphere as the Moon base in a small cabin with stronger local airflow (team assumption).'},
  {g: 'Space', name: 'Mars base', o2: 30, psi: 10.2, flow: 10, grav: 0.38, note: 'No official figure; assumed equal to the Moon base.'},
  {g: 'Space', name: 'NASA exploration atm.', o2: 34, psi: 8.2, flow: 10, grav: 0.166, note: 'NASA Exploration Atmospheres Working Group (2006) recommendation for lunar missions: 8.2 psi, 34 % O₂.'},
  {g: 'Space', name: 'Shuttle pre-spacewalk', o2: 26.5, psi: 10.2, flow: 10, grav: 0, note: 'Space Shuttle cabin was lowered to 10.2 psi / 26.5 % O₂ before spacewalks to shorten pre-breathing.'},
  {g: 'Space', name: 'Spacesuit', o2: 100, psi: 4.3, flow: 10, grav: 0, note: 'US spacesuit (EMU): pure oxygen at 4.3 psi.'},
  {g: 'Space', name: 'Apollo 1 (1967)', o2: 100, psi: 16.7, flow: 0, grav: 1, note: 'Pure O₂ at ~16.7 psi during the ground test where a cabin fire killed three astronauts.'},
  {g: 'Earth', name: 'Room air', o2: 21, psi: 14.7, flow: 0, grav: 1, note: 'Normal air at sea level, still air. The microgravity data has no buoyancy, so compare with care.'},
  {g: 'Earth', name: 'Airliner cabin', o2: 21, psi: 10.9, flow: 10, grav: 1, note: 'Airliner cabins are pressurised to an ~8,000 ft altitude: ~10.9 psi.'},
  {g: 'Earth', name: 'Hyperbaric chamber', o2: 100, psi: 35.3, flow: 0, grav: 1, note: 'Monoplace hyperbaric oxygen therapy: pure O₂ at ~2.4 atm. Clothing and bedding are tightly restricted because of fire risk.'},
];
function scenarioUI() {
  const grp = g => `<span class="mute" style="font-size:12px;align-self:center;margin-right:2px">${g}</span>` +
    PRESETS.map((p, i) => p.g === g ? `<button data-i="${i}">${esc(p.name)}</button>` : '').join('');
  $('presets').innerHTML = grp('Space') + '<span style="flex-basis:100%"></span>' + grp('Earth');
  $('presets').onclick = e => {
    const p = PRESETS[e.target.dataset.i]; if (!p) return;
    $('o2').value = p.o2; $('p').value = p.psi; $('flow').value = p.flow; $('g').value = String(p.grav);
    $('presetnote').textContent = p.note;
    $('presets').querySelectorAll('button').forEach(b => b.classList.toggle('on', b === e.target));
    updateScenario();
  };
  ['o2', 'p', 'flow', 'g', 'phase'].forEach(id => $(id).addEventListener('input', () => {
    $('presetnote').textContent = ''; $('presets').querySelectorAll('button').forEach(b => b.classList.remove('on'));
  }));
  ['o2', 'p', 'flow', 'g', 'phase'].forEach(id => $(id).addEventListener('input', debounce(updateScenario, 250)));
  updateScenario();
}
function debounce(f, ms) { let t; return () => { clearTimeout(t); t = setTimeout(f, ms); }; }
async function updateScenario() {
  const o2 = +$('o2').value / 100, psi = +$('p').value, flow = +$('flow').value, g = +$('g').value, phase = $('phase').value;
  $('o2v').textContent = `${$('o2').value} %`; $('pv').textContent = `${psi.toFixed(1)} psi · ${(psi * PSI_KPA).toFixed(0)} kPa`;
  $('fv').textContent = `${flow} cm/s`;
  const q = `o2=${o2}&pressure=${(psi * PSI_KPA).toFixed(2)}&flow=${flow}&gravity=${g}`;
  const [near, rk] = await Promise.all([api(`/api/nearest?${q}&phase=${phase}&k=8`), api(`/api/rank?scenario=custom&${q}`)]);
  const label = {well_covered: 'Well covered', sparse: 'Sparse data', no_data: 'No nearby data'}[near.coverage];
  $('verdict').innerHTML = `${tip('coverage', `<span class="badge b-${near.coverage}">${label}</span>`)}<div class="verdict-big">${near.n_close} close experiment${near.n_close === 1 ? '' : 's'}</div>
    <div class="plain"><b>What this means:</b> ${plainSummary(near, phase)}</div>
    <p>${esc(near.message)}</p>${near.warning ? `<p class="warn">⚠ ${esc(near.warning)}</p>` : ''}${near.caveat ? `<p class="mute">${esc(near.caveat)}</p>` : ''}`;
  $('nearest').innerHTML = `<div class="scroll"><table><tr><th>${tip('similarity', 'Match')}</th><th>Run</th><th>${tip('fuel', 'Fuel')}</th><th>${tip('o2', 'O₂')}</th><th>${tip('pressure', 'Pressure')}</th><th class="hide-sm">${tip('airflow', 'Flow')}</th><th>${tip('outcome', 'Outcome')}</th></tr>${near.matches.map(m => `<tr>
    <td>${tip(m.match, `<span class="badge b-${m.match}">${m.match}</span>`)} <small>${m.similarity.toFixed(2)}</small></td>
    <td class="mono">${esc(m.run_id)}<small>${esc(m.acronym)}</small></td><td>${esc(m.fuel)}<small>${esc(m.fuel_phase)}</small></td>
    <td>${m.o2_pct ?? '–'} %</td><td>${m.pressure_kpa ? (m.pressure_kpa / PSI_KPA).toFixed(1) + ' psi' : '–'}${m.assumed?.length ? `<small>${tip('assumed', 'assumed')}</small>` : ''}</td>
    <td class="hide-sm">${m.flow_cm_s ?? '–'} cm/s</td><td>${outcomeText(m.outcome)}${m.match !== 'near' && m.differences.length ? `<small class="warn">${esc(m.differences.slice(0, 2).join('; '))}</small>` : ''}</td></tr>`).join('')}</table></div>`;
  $('scenrank').innerHTML = rankHTML(rk.results.slice(0, 8), false);
}
function plainSummary(near, phase) {
  const what = {solid: 'solid materials', liquid: 'fuel droplets', gas: 'gas flames'}[phase] || 'any fuel';
  if (near.coverage === 'well_covered') return `NASA ran ${near.n_close} experiments with ${what} close to these conditions, so there is real evidence to compare against.`;
  if (near.coverage === 'sparse') return `Only ${near.n_close} NASA experiment${near.n_close === 1 ? '' : 's'} with ${what} came close to these conditions. Use ${near.n_close === 1 ? 'it' : 'them'} as a hint, not as proof.`;
  const top = near.matches[0];
  if (!top) return `NASA has no experiments with ${what} at all.`;
  return `NASA has never tested ${what} in conditions like these. The closest test (${esc(top.acronym)}, ${top.o2_pct} % oxygen at ${(top.pressure_kpa / PSI_KPA).toFixed(1)} psi) is the nearest evidence, but compared with it ${esc(top.differences.slice(0, 2).join(' and '))}. Anything predicted here is an educated guess beyond the data.`;
}
function outcomeText(o) {
  if (!o || !Object.keys(o).length) return '<span class="mute">not recorded</span>';
  const parts = [];
  if (o.result) parts.push(o.result.replace('_', ' ')); else if (o.ignited != null) parts.push(o.ignited ? 'ignited' : 'no ignition');
  if (o.burn_time_s != null) parts.push(`${o.burn_time_s} s${o.censored ? '+' : ''}`);
  if (o.burning_rate_mm2_s != null) parts.push(`K ${o.burning_rate_mm2_s} mm²/s`);
  if (o.spread_rate_mm_s != null) parts.push(`spread ${o.spread_rate_mm_s} mm/s`);
  return esc(parts.join(' · ')) + (o.censored ? `<small>${tip('censored', 'censored')}: still burning when stopped</small>` : '');
}
function rankHTML(rows, clickable) {
  return rows.map(r => `<div class="rk" data-id="${r.id}"><div class="n">${r.rank}</div><div class="body">
    <div class="t">${esc(r.acronym)} <span class="mute mono">${r.id}</span> <span class="badge">${esc(r.category)}</span> <b style="float:right">${tip('score', r.score, 'r')}</b></div>
    <div class="s">${esc(r.title)}</div><div class="bar"><i style="width:${r.score}%"></i></div>
    ${clickable ? '' : `<ul class="tight">${r.reasons.map(x => `<li>${esc(x)}</li>`).join('')}${r.caveats.map(x => `<li class="warn">${esc(x)}</li>`).join('')}</ul>`}
  </div></div>`).join('');
}

// ---------- investigations ----------
async function investigationsUI() {
  $('rscen').innerHTML = Object.entries(META.scenarios).map(([k, s]) => `<option value="${k}" ${k === 'moon_base' ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  $('rscen').onchange = $('rfocus').onchange = loadRanking;
  $('ranklist').onclick = e => { const el = e.target.closest('.rk'); if (el) detail(el.dataset.id); };
  await loadRanking();
}
async function loadRanking() {
  const rk = await api(`/api/rank?scenario=${$('rscen').value}&focus=${$('rfocus').value}`);
  $('ranklist').innerHTML = rankHTML(rk.results, true);
  const first = $('ranklist').querySelector('.rk'); if (first) detail(first.dataset.id, rk);
}
async function detail(id, rk) {
  document.querySelectorAll('#ranklist .rk').forEach(x => x.classList.toggle('on', x.dataset.id === id));
  const p = await api(`/api/investigations/${id}`);
  const rng = (r, f, u) => r ? `${f(r[0])}–${f(r[1])} ${u}` : '<span class="mute">not recorded</span>';
  const others = META.investigations.filter(x => x.id !== id);
  $('detail').innerHTML = `<div class="mono mute">${p.id} · ${esc(p.platform || '')}</div><h3 style="font-size:19px;margin:4px 0 8px">${esc(p.acronym)}: ${esc(p.title)}</h3>
    <div class="chips">${p.pillars.map(x => `<span>${x}</span>`).join('')}<span>${esc(p.category)}</span></div>
    <div class="kv"><div>Hardware</div><div>${esc(p.hardware || '–')}</div>
      <div>Runs</div><div>${p.n_runs} (${p.n_with_outcome} with outcome)${p.normalized ? '' : ` <span class="warn">${esc(p.note)}</span>`}</div>
      <div>Fuels</div><div>${esc(p.fuels.join(', ') || '–')}</div>
      <div>${tip('o2', 'Oxygen tested')}</div><div>${rng(p.o2_frac_range, v => (v * 100).toFixed(1), '%')}</div>
      <div>${tip('pressure', 'Pressure tested')}</div><div>${rng(p.pressure_kpa_range, v => (v / PSI_KPA).toFixed(1), 'psi')}</div>
      <div>${tip('airflow', 'Airflow tested')}</div><div>${p.flow_cm_s_range && p.flow_cm_s_range[1] === 0 ? 'still air (0 cm/s)' : rng(p.flow_cm_s_range, v => v, 'cm/s')}</div>
      <div>${tip('outcome', 'Measured outcomes')}</div><div>${esc(p.outcome_fields.join(', ') || 'none in run table')}</div>
      <div>DOI</div><div>${p.doi ? `<a target="_blank" href="https://doi.org/${esc(p.doi)}">${esc(p.doi)}</a>` : '–'}</div></div>
    <details open><summary><b>Objective</b></summary><p>${esc(p.objective || '–')}</p></details>
    <details><summary><b>Publications (${p.publications.length})</b></summary>${p.publications.map(x => `<details><summary>${esc(x.title)} <span class="mute">${x.year || ''}</span></summary>
      <p>${x.abstract ? esc(x.abstract) : '<span class="mute">No abstract available.</span>'}</p>${x.doi ? `<a target="_blank" href="https://doi.org/${esc(x.doi)}">doi:${esc(x.doi)}</a>` : ''}
      ${x.oa_pdf ? ` · <a target="_blank" href="${esc(x.oa_pdf)}">free PDF</a>` : ''}</details>`).join('')}</details>
    <h3 style="margin-top:16px">Compare with</h3><div class="row"><select id="cmpsel"><option value="">Choose an investigation…</option>${others.map(x => `<option value="${x.id}">${esc(x.acronym)} (${x.id})</option>`).join('')}</select></div><div id="cmpout"></div>`;
  $('cmpsel').onchange = async e => {
    if (!e.target.value) return;
    const c = await api(`/api/compare?ids=${id},${e.target.value}`);
    $('cmpout').innerHTML = `<p><b>Similar</b></p><ul class="tight">${c.similarities.map(x => `<li>${esc(x)}</li>`).join('') || '<li class="mute">nothing obvious</li>'}</ul>
      <p><b>Different</b></p><ul class="tight">${c.differences.map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="mute">${esc(c.summary)}</p>`;
  };
}

// ---------- ask ----------
const history_ = [];
const SUGGEST = ['Which experiments are closest to a Moon base cabin atmosphere?', 'Why do flames in microgravity extinguish at low airflow?',
  'What did BASS-II find about extinction of PMMA?', 'Compare FLEX and CFI', 'How does helium affect droplet extinction?'];
function askUI() {
  $('suggest').innerHTML = SUGGEST.map(s => `<button>${esc(s)}</button>`).join('');
  $('suggest').onclick = e => { if (e.target.tagName === 'BUTTON') { $('q').value = e.target.textContent; send(); } };
  $('chatform').onsubmit = e => { e.preventDefault(); send(); };
}
function md(text) {
  const inline = t => t.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]{3,160})\]/g, '<span class="cite">$1</span>');
  const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => inline(c.trim()));
  return esc(text).split(/\n{2,}/).map(block => {
    const lines = block.split('\n').filter(l => l.trim());
    if (lines.length >= 2 && lines.every(l => l.trim().startsWith('|'))) {          // markdown table
      const rows = lines.filter(l => !/^\s*\|?\s*:?-{2,}/.test(l));
      return `<table class="mdt"><tr>${cells(rows[0]).map(c => `<th>${c}</th>`).join('')}</tr>${rows.slice(1)
        .map(r => `<tr>${cells(r).map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`;
    }
    return lines.map(l => {
      const m = l.match(/^(#{1,4})\s+(.*)/);
      if (m) return `<h4>${inline(m[2])}</h4>`;
      if (/^\s*[-*•] /.test(l)) return `<li>${inline(l.replace(/^\s*[-*•] /, ''))}</li>`;
      return `<p>${inline(l)}</p>`;
    }).join('').replace(/(<li>.*?<\/li>)+/g, x => `<ul class="tight">${x}</ul>`);
  }).join('');
}
async function send() {
  const q = $('q').value.trim(); if (!q) return;
  $('q').value = ''; history_.push({role: 'user', content: q});
  $('msgs').insertAdjacentHTML('beforeend', `<div class="msg user">${esc(q)}</div><div class="msg bot typing" id="pending">Searching the data…</div>`);
  $('msgs').scrollTop = 1e9;
  try {
    const r = await api('/api/chat', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({messages: history_})});
    history_.push({role: 'assistant', content: r.answer});
    let html = md(r.answer);
    for (const u of r.unverified || [])  // citations the server couldn't match to any retrieved source
      html = html.split(`<span class="cite">${esc(u)}`).join(`<span class="cite bad" title="not found in the retrieved sources">${esc(u)}`);
    $('pending').outerHTML = `<div class="msg bot">${html}
      ${(r.unverified || []).length ? `<div class="trace warn">⚠ ${r.unverified.length} citation(s) could not be matched to a retrieved source: ${r.unverified.map(esc).join('; ')}</div>` : ''}
      ${r.trace.length ? `<div class="trace">Looked up: ${r.trace.map(t => `${esc(t.tool)}(${esc(Object.values(t.args).join(', ').slice(0, 60))})`).join(' → ')}</div>` : ''}
      ${r.sources.length ? `<details class="trace"><summary>${r.sources.length} sources</summary><ul class="tight">${r.sources.map(s => `<li><span class="cite">${esc(s.cite)}</span> ${esc(s.investigations.join(', '))}</li>`).join('')}</ul></details>` : ''}</div>`;
  } catch (e) {
    $('pending').outerHTML = `<div class="msg bot warn">Error: ${esc(e.message)}</div>`;
  }
  $('msgs').scrollTop = 1e9;
}

// ---------- boot ----------
(async () => {
  META = await api('/api/meta');
  decorateTerms();
  askUI();
  await Promise.all([overview(), investigationsUI()]);
  scenarioUI();
  const t = location.hash.slice(1); if (t && $('sec-' + t)) show(t);
})();
