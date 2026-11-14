"""Quick local explorer for the downloaded PSI combustion data.

Usage: python3 view.py  ->  http://localhost:8000   (python3 view.py build  -> public/index.html only)
Reads data/raw/{manifests/*.json, run_tables/*.csv}; stdlib only.
api/dl.py redirects file links to fresh PSI presigned S3 URLs (also the Vercel function).
"""
import csv, glob, http.server, io, json, os, re, sys, urllib.parse
from api.dl import handler as DlHandler
from collections import defaultdict

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")

# What one row of each run table is. Keyed by table name (filename minus "PSI-xx_Experimental table_").
TABLE_NOTES = {
    "FLEX": "One row = one free-floating fuel droplet burned in the Combustion Integrated Rack (CIR). Varies fuel, pressure and O2/N2/CO2/He mix; measures initial droplet diameter, diameter at flame extinction, burning rate and burn time. Best table for 'will it extinguish in this atmosphere?'.",
    "Flex2": "Not individual runs: one row per fuel with the RANGES of conditions tested (droplet size, O2 fraction, pressure, flow). Use as a coverage map, not as data points.",
    "CFI": "One row = one droplet cool-flame test (follow-on to FLEX in the same hardware). Pressure, O2/N2/He mole fractions, whether the droplet was fiber-supported, and fuel (e.g. C12H26 = dodecane).",
    "Flame Design_Normal Flame": "One row = one spherical gaseous diffusion flame (ACME). 'Normal' = fuel issues from a porous sphere into an oxidizer. Columns are fuel/N2 mass flows, O2 mole fraction, pressure, stoichiometric mixture fraction (Zst) and adiabatic flame temperature (Tad). Studies soot-free flame design.",
    "Flame Design_Inverse Flame": "Same as Normal Flame but 'Inverse' = oxygen flows out of the sphere into a fuel atmosphere. Same columns (XO2, flows, pressure, Zst, Tad).",
    "CFI-G_Normal Flames": "One row = one gaseous spherical flame test probing cool flames (low-temperature chemistry). Fuel, O2 fraction, pressure, hydrocarbon mass flow, Tad, Zst, and whether hot ignition / cool flame occurred.",
    "CFI-G_Inverse Flames": "Inverse-flame version of CFI-G (oxidizer issues into fuel). Same kind of columns plus outcome flags.",
    "Spice": "One row = one co-flow laminar jet flame (SPICE, Microgravity Science Glovebox). Fuel, nozzle diameter, fuel flow (sccm and mg/s), co-flow air velocity, ignition/flame-off times. Used to find the smoke point (when soot escapes).",
    "BASS-II": "One row = one solid-fuel burn (thin PMMA films, rods, etc.) in the MSG flow duct. Material and geometry are free text; flow set by fan/air display values; O2, CO2, CO measured before and after. Core data for solid flame spread vs. airflow and O2.",
    "BASS": "One row = one BASS-I solid-fuel burn. Only date, test and sample number plus material (e.g. SIBAL cotton/fiberglass fabric, PMMA). Conditions live in the PDFs/videos, not here.",
    "SAFFIRE-1": "One row = one large sample burned inside an uncrewed Cygnus cargo vehicle after it left the ISS. Material, size, airflow, O2, igniter power and time, burn time, flow direction (concurrent/opposed), cameras.",
    "SAFFIRE-2": "Like SAFFIRE-1, nine smaller samples, adds microgravity vs. 1-g burn/spread length comparison columns. Many values have units inside the cell.",
    "SAFFIRE-3": "Two rows: the SAFFIRE-III large fabric sample. Same layout as SAFFIRE-1.",
    "SAME": "One row = one material heated to produce smoke (Smoke Aerosol Measurement Experiment). Material, airflow, mass-loss rate, aging time. Feeds smoke-detector design.",
    "SAME-R": "One row = one SAME reflight test. Material, inlet velocity, Rt/R0 (smoke-detector ratio), duration and aging/mixing times.",
    "Slice": "Test log only: date and gaseous fuel mix used for SLICE lifted-flame tests.",
    "ACME BRE": "One row = one test DAY (not one flame) of the Burning Rate Emulator: a gaseous burner that mimics a burning solid. Burner size, fuel bottle, list of O2 levels, number of flames ignited.",
    "CLD Flame": "One row = one test day of Coflow Laminar Diffusion flames. Fuel/N2 flow controllers, fuel bottle, concentration range, flames ignited.",
    "ACME E-FIELD Flames": "One row = one test day of flames in an electric field. Mesh polarity, fuel, flames ignited.",
    "ACME s-Flame": "One row = one test day of spherical s-Flames (structure and response). Atmosphere, fuel bottle, flames ignited.",
    "DAFT": "Two sessions of dust/aerosol sampling (Arizona Road Dust) for smoke-detector calibration. Not a combustion run table.",
    "Data Summary Table": "Index of datasets published in papers (cool flame limits etc.) with links to the figure in the reference publication. Not runs.",
}

GLOSSARY = [
    ("XO2 / Oxygen / Percent O2", "Oxygen amount. 0.21 (fraction) = 21 % (percent) = normal air."),
    ("Xf / Xfuel / XC2H4", "Mole fraction of fuel in the gas fed to the burner."),
    ("Zst", "Stoichiometric mixture fraction: where fuel and oxidizer meet in exactly the right ratio. Low Zst → flame sits on the oxidizer side and is sootier."),
    ("Tad (K)", "Adiabatic flame temperature: theoretical max flame temperature for that mixture."),
    ("TFP", "Total fuel/flow parameter from the ACME logs (see investigation PDFs)."),
    ("mfuel / mHC / mN2 (mg/s)", "Mass flow rates of fuel / hydrocarbon / nitrogen."),
    ("sccm", "Standard cubic centimetres per minute, a volumetric gas flow rate."),
    ("p / Pressure (atm, bar, mmHg)", "Chamber pressure. 1 atm = 1.013 bar = 760 mmHg = 101.3 kPa. Lunar habitat target ≈ 0.69 atm."),
    ("Air Flow / Air Rate / Inlet velocity (cm/s)", "Speed of air past the sample. Buoyant flow on Earth ≈ 30–50 cm/s; ISS ventilation ≈ 5–20 cm/s."),
    ("Concurrent / Opposed", "Flame spreading with vs. against the airflow."),
    ("Droplet / extinction diameter", "FLEX droplets start at about 1–5 mm; flame goes out at the extinction diameter."),
    ("GMT / Test Day (e.g. 19304)", "Day-of-year. '19304' = year 2019, day 304."),
    ("SIBAL", "Cotton/fiberglass fabric used as a standard spacecraft material sample."),
    ("PMMA", "Acrylic (plexiglass), the standard solid fuel for flame-spread studies."),
    ("Rt/R0", "SAME smoke-detector signal ratio (test vs. baseline)."),
]

KINDS = {  # extension -> (category, explanation)
    "video": ({".mp4", ".ts", ".avi", ".mov", ".m4v"}, "Downlinked video of burns. .ts files are raw ISS UDP video streams recorded with VLC; .mp4 are the same, converted. The test ID is usually at the end of the file name (e.g. 21242A1, TEST_B1)."),
    "image": ({".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".nef"}, "Still photos, screenshots, high-res camera frames (.tif, .nef = Nikon raw)."),
    "archive": ({".zip", ".7z", ".tar", ".gz"}, "Zipped bundles. In 'Raw Data' these are mostly camera frame sequences (per test/camera) and sensor dumps; in 'metadata' an ISA-Tab description of the study. The PSI API does not list zip contents, you must download one to see inside."),
    "sensor": ({".txt", ".csv", ".dat", ".asc", ".log", ".meta", ".metadata", ".mdipsug", ".xml", ".pxp"}, "Instrument time-series and logs: thermocouples, radiometers, flow controllers, gas analyzers, ACME diagnostics (.mdipsug), Igor Pro files (.pxp)."),
    "doc": ({".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}, "Reports, papers, test matrices, engineering requirements, calibration sheets."),
}


def kind_of(name):
    e = os.path.splitext(name)[1].lower()
    for k, (exts, _) in KINDS.items():
        if e in exts:
            return k
    return "other"


def files_of(o, out):
    if isinstance(o, dict):
        if "file_name" in o and "file_size" in o:
            out[o.get("remote_path", o["file_name"])] = o
            return
        for v in o.values():
            files_of(v, out)
    elif isinstance(o, list):
        for v in o:
            files_of(v, out)


def load():
    invs = []
    for path in sorted(glob.glob(os.path.join(RAW, "manifests", "*.json"))):
        d = json.load(open(path))
        acc = d["accession"]
        files = {}
        files_of(d, files)
        flist = []
        for p, f in files.items():
            parts = p.split("/")
            flist.append([parts[4] if len(parts) > 5 else "(root)", f["file_name"], float(f.get("file_size") or 0), kind_of(f["file_name"])])
        flist.sort(key=lambda x: (x[0], x[1]))
        tables = []
        for t in sorted(glob.glob(os.path.join(RAW, "run_tables", acc + "_*.csv"))):
            rows = [r for r in csv.reader(io.StringIO(open(t, encoding="utf-8-sig", errors="replace").read()))
                    if any(c.strip() for c in r)]
            if rows:
                name = re.sub(r"^PSI-\d+_Experimental table_", "", os.path.basename(t)[:-4])
                tables.append({"name": name, "note": TABLE_NOTES.get(name, ""),
                               "columns": [c.strip() for c in rows[0]], "rows": rows[1:]})
        invs.append({
            "acc": acc, "acronym": d.get("investigationAcronym") or "", "title": d.get("title", ""),
            "sub": d.get("subResearchArea") or "", "objective": d.get("objective") or "",
            "hypothesis": d.get("hypothesis") or "", "impacts": d.get("researchImpacts") or "", "doi": d.get("doi") or "",
            "pubs": [{"title": p.get("title", ""), "doi": p.get("doi", "")} for p in d.get("publications") or []],
            "files": flist, "size": sum(f[2] for f in flist), "tables": tables,
        })
    return invs


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flame in Freefall · PSI Combustion Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{--bg:#0b0d12;--panel:#12151c;--panel2:#181c25;--line:#232834;--fg:#e4e7ee;--mute:#8a93a6;--dim:#5d6577;
--acc:#ff7a2f;--acc-soft:rgba(255,122,47,.12);--blue:#5aa9ff;--ok:#3ecf8e;--r:10px}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font:14px/1.5 Inter,system-ui,sans-serif;color:var(--fg);background:var(--bg);display:grid;grid-template-rows:56px 1fr;grid-template-columns:320px 1fr;grid-template-areas:"top top" "side main"}
a{color:var(--blue);text-decoration:none} a:hover{text-decoration:underline}
header{grid-area:top;display:flex;align-items:center;gap:14px;padding:0 20px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#1a110b,var(--bg) 40%)}
header .logo{width:26px;height:26px;border-radius:50%;background:radial-gradient(circle at 50% 55%,#ffd27a 0 18%,#ff7a2f 40%,#ff3d2f 65%,transparent 72%);box-shadow:0 0 18px #ff7a2f88}
header b{font-size:15px;letter-spacing:.2px} header span{color:var(--mute);font-size:13px}
header .sp{flex:1}
#side{grid-area:side;overflow:auto;border-right:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column}
#q{margin:12px;padding:9px 12px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg);font:inherit;outline:none}
#q:focus{border-color:var(--acc)}
.grp{padding:10px 14px 4px;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.it{padding:9px 14px;cursor:pointer;border-left:3px solid transparent}
.it:hover{background:var(--panel2)} .it.on{background:var(--acc-soft);border-left-color:var(--acc)}
.it .t{display:flex;justify-content:space-between;gap:8px;font-weight:600}
.it .t em{font-style:normal;font-weight:500;color:var(--mute);font-size:12px}
.it small{display:block;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.it .bar{height:3px;background:var(--line);border-radius:2px;margin-top:6px}.it .bar i{display:block;height:100%;background:var(--acc);border-radius:2px}
#main{grid-area:main;overflow:auto;padding:24px 32px 60px}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.3px} h3{margin:0 0 10px;font-size:15px}
.mute{color:var(--mute)} .mono{font-family:"JetBrains Mono",monospace;font-size:12px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.tile .v{font-size:22px;font-weight:700} .tile .l{color:var(--mute);font-size:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;margin:14px 0}
.layers{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.layer{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.layer .n{display:inline-block;width:22px;height:22px;border-radius:50%;background:var(--acc-soft);color:var(--acc);text-align:center;font-weight:700;font-size:12px;line-height:22px;margin-right:8px}
.layer.key{border-color:#ff7a2f66}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.ic{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px;cursor:pointer;transition:.15s}
.ic:hover{border-color:var(--acc);transform:translateY(-1px)}
.ic .a{font-weight:700} .ic .s{color:var(--mute);font-size:12px;margin:4px 0 8px;min-height:36px}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;background:var(--panel2);border:1px solid var(--line);color:var(--mute);margin:2px 4px 2px 0}
.badge.k{background:var(--acc-soft);border-color:#ff7a2f55;color:#ffb08a} .badge.ok{color:var(--ok);border-color:#3ecf8e44}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:18px 0 4px;position:sticky;top:-24px;background:var(--bg);z-index:5;padding-top:8px}
.tabs button{background:none;border:0;color:var(--mute);font:inherit;font-weight:500;padding:9px 14px;cursor:pointer;border-bottom:2px solid transparent}
.tabs button.on{color:var(--fg);border-bottom-color:var(--acc)}
.note{border-left:3px solid var(--acc);padding:10px 14px;background:var(--acc-soft);border-radius:0 8px 8px 0;margin:8px 0 12px}
p{white-space:pre-wrap;max-width:980px;margin:.2em 0 1em;color:#cfd3dc}
table{border-collapse:collapse;font-size:12px;width:max-content}
td,th{border-bottom:1px solid var(--line);padding:5px 10px;white-space:nowrap;max-width:300px;overflow:hidden;text-overflow:ellipsis;text-align:left}
th{background:var(--panel2);position:sticky;top:0;cursor:pointer;font-weight:600;color:#fff}
tr:hover td{background:#171b24}
.tw{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:8px;margin-top:10px}
.ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:8px 0}
.ctl label{color:var(--mute);font-size:12px}
select{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:inherit;font-size:12px;max-width:240px}
.imgs{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 12px}.imgs img{height:200px;border-radius:8px;border:1px solid var(--line)}
details{border:1px solid var(--line);border-radius:8px;margin:8px 0;background:var(--panel2)}
details summary{cursor:pointer;padding:10px 14px;font-weight:500}
details summary span{color:var(--mute);font-weight:400}
details .tw{margin:0 10px 10px}
ul.pubs{padding-left:18px} ul.pubs li{margin:6px 0}
.gloss td:first-child{font-weight:600;color:#ffb08a}.gloss td{white-space:normal;max-width:none;vertical-align:top}
.pl-ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0}
.pl-ctl button{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:7px 14px;font:inherit;cursor:pointer}
.pl-ctl button:hover{border-color:var(--acc)} .pl-ctl button.pri{background:var(--acc);border-color:var(--acc);color:#1a0d05;font-weight:600}
.dots{display:flex;gap:6px;flex-wrap:wrap}.dots span{font-size:12px;padding:4px 10px;border-radius:20px;border:1px solid var(--line);color:var(--mute);cursor:pointer}
.dots span.on{border-color:var(--acc);color:#ffb08a;background:var(--acc-soft)}
#stage{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);display:block}
#stage text{font-family:Inter,system-ui,sans-serif;fill:#d7dae0}
#stage .mono{font-family:"JetBrains Mono",monospace}
#cap{margin-top:14px}#cap h3{color:var(--acc);font-size:17px}
.cap-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:14px}
.eli5,.tech,.words{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 18px}
.eli5{background:linear-gradient(135deg,rgba(62,207,142,.10),rgba(90,169,255,.06));border-color:#3ecf8e55}
.eli5 p{font-size:15.5px;line-height:1.65;color:#e9fbf2;margin:0}
.eli5.intro{margin:14px 0 4px}.eli5.intro p{font-size:14.5px}
.tag{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}
.tech p{margin:0 0 12px}.tech code{display:block;font-family:"JetBrains Mono",monospace;font-size:12px;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px 12px;color:#ffb08a;white-space:pre-wrap}
.words{margin-top:14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px 18px}.words .tag{grid-column:1/-1}
.words div b{display:block;color:#ffb08a;font-size:13px}.words div span{color:var(--mute);font-size:13px}
@media(max-width:1100px){.cap-grid{grid-template-columns:1fr}}
.prog{height:3px;background:var(--line);border-radius:2px;overflow:hidden;margin-top:-1px}.prog i{display:block;height:100%;width:0;background:var(--acc)}
@media(max-width:820px){body{grid-template-columns:1fr;grid-template-areas:"top" "main"}#side{display:none}#main{padding:16px}}
</style></head><body>
<header><div class="logo"></div><b>Flame in Freefall</b><span>NASA PSI microgravity combustion data explorer</span><div class="sp"></div>
<a href="https://psi.nasa.gov/physci/repo/search?q=combustion" target=_blank>PSI repository ↗</a><a href="#pipeline" style="margin-left:16px">Pipeline ▶</a></header>
<nav id="side"><input id="q" placeholder="Filter investigations…"><div id="list"></div></nav>
<main id="main"></main>
<script>
const D = __DATA__, KINDS = __KINDS__, GLOSS = __GLOSS__;
const gb = b => b>=1e12 ? (b/1e12).toFixed(2)+' TB' : b>=1e9 ? (b/1e9).toFixed(1)+' GB' : b>=1e6 ? (b/1e6).toFixed(1)+' MB' : (b/1e3).toFixed(0)+' KB';
const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = v => { const m = String(v).replace(/,/g,'').match(/-?\d*\.?\d+(e-?\d+)?/i); return m ? +m[0] : null; };
const dl = (acc,f) => `/api/dl?acc=${encodeURIComponent(acc)}&file=${encodeURIComponent(f)}`;
const runs = d => d.tables.reduce((s,t)=>s+t.rows.length,0);
const name = d => d.acronym || d.acc;
const PAL = ['#ff7a2f','#5aa9ff','#3ecf8e','#c084fc','#f6c945','#ff5c8a','#2dd4bf','#a3a3a3'];
const lay = o => ({paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:'#c9cdd6',family:'Inter'},colorway:PAL,
  legend:{orientation:'h',y:-0.25},...o,xaxis:{gridcolor:'#232834',zeroline:false,...(o.xaxis||{})},yaxis:{gridcolor:'#232834',zeroline:false,...(o.yaxis||{})}});
const CFG = {displaylogo:false,responsive:true};
const maxSize = Math.max(...D.map(d=>d.size));
D.sort((a,b) => runs(b)-runs(a) || b.size-a.size);
const main = document.getElementById('main'), list = document.getElementById('list'), q = document.getElementById('q');

function drawList(){
  const f = q.value.toLowerCase();
  const m = D.filter(d => !f || (d.acc+' '+d.acronym+' '+d.title+' '+d.sub).toLowerCase().includes(f));
  const item = d => `<div class="it" data-acc="${d.acc}"><div class="t">${esc(name(d))}<em>${runs(d)?runs(d)+' runs':'docs'}</em></div>
    <small>${esc(d.title)}</small><small class="mono">${d.acc} · ${gb(d.size)}</small><div class="bar"><i style="width:${Math.max(1,Math.log10(d.size+1)/Math.log10(maxSize)*100)}%"></i></div></div>`;
  const a = m.filter(d=>runs(d)), b = m.filter(d=>!runs(d));
  list.innerHTML = `<div class="it" data-acc=""><div class="t">Overview</div><small>What is here and how to read it</small></div><div class="it" data-acc="pipeline"><div class="t">Pipeline ▶</div><small>Animated: raw PSI files → training-ready data</small></div>`
    + (a.length?`<div class="grp">With run tables · ${a.length}</div>`+a.map(item).join(''):'')
    + (b.length?`<div class="grp">Documents / models only · ${b.length}</div>`+b.map(item).join(''):'');
  mark();
}
function mark(){ const h = location.hash.slice(1); list.querySelectorAll('.it').forEach(x => x.classList.toggle('on', x.dataset.acc===h.split('/')[0])); }
q.oninput = drawList;
list.onclick = e => { const el = e.target.closest('.it'); if (el) location.hash = el.dataset.acc; };
main.onclick = e => { const el = e.target.closest('[data-go]'); if (el) location.hash = el.dataset.go; };
window.onhashchange = route;
function route(){ mark(); main.scrollTop = 0; stopPipeline(); if (location.hash.startsWith('#pipeline')) return pipeline(); const d = D.find(x => x.acc === location.hash.slice(1)); d ? show(d) : overview(); }

function kindTotals(files){ const t={}; files.forEach(f=>{(t[f[3]] ||= [0,0]); t[f[3]][0]++; t[f[3]][1]+=f[2];}); return t; }
const tile = (v,l) => `<div class="tile"><div class="v">${v}</div><div class="l">${l}</div></div>`;

function overview(){
  const all = D.flatMap(d=>d.files), kt = kindTotals(all), tot = all.reduce((s,f)=>s+f[2],0);
  const small = all.filter(f=>f[3]!=='video'&&f[3]!=='archive').reduce((s,f)=>s+f[2],0);
  main.innerHTML = `<h1>Microgravity combustion data, at a glance</h1>
  <div class="mute">All ${D.length} combustion investigations in NASA's Physical Sciences Informatics (PSI) repository: ISS flame, droplet, smoke and solid-fuel fire experiments.</div>
  <div class="tiles">${tile(D.length,'investigations')}${tile(D.reduce((s,d)=>s+runs(d),0).toLocaleString(),'run-table rows')}${tile(all.length.toLocaleString(),'files')}${tile(gb(tot),'total archive')}${tile(gb(small),'excluding video &amp; zips')}${tile(D.reduce((s,d)=>s+d.pubs.length,0),'publications')}</div>
  <h3>How the data is organised</h3>
  <div class="layers">
   <div class="layer"><span class="n">1</span><b>Metadata</b><p class="mute">Objective, hypothesis, research impacts, hardware, DOI and the publication list for each investigation. Clean JSON from the PSI API.</p></div>
   <div class="layer key"><span class="n">2</span><b>Run table</b> <span class="badge k">key layer</span><p class="mute">A small CSV, usually one row per test: fuel, O₂, pressure, airflow and sometimes results. This is what experiments get compared on. Formats differ between investigations (see the note on each table).</p></div>
   <div class="layer"><span class="n">3</span><b>Files</b><p class="mute">Videos, images, zipped camera frames, sensor logs and reports on S3. About 99% of the bytes. Listed here; click a file to download it from NASA.</p></div>
  </div>
  <div class="card"><h3>Investigations</h3><div class="grid">${D.map(d=>`<div class="ic" data-go="${d.acc}"><div class="a">${esc(name(d))} <span class="mute mono">${d.acc}</span></div>
    <div class="s">${esc(d.title)}</div>${runs(d)?`<span class="badge k">${runs(d)} runs</span>`:'<span class="badge">no run table</span>'}<span class="badge">${gb(d.size)}</span>${d.sub?`<span class="badge">${esc(d.sub)}</span>`:''}</div>`).join('')}</div></div>
  <div class="card"><h3>Where the bytes are</h3><div class="mute">GB per investigation by file type (log scale). Four gaseous-flame investigations hold most of it.</div><div id="o1"></div></div>
  <div class="card"><h3>File types</h3><div class="tw" style="max-height:none"><table><tr><th>Type</th><th>Files</th><th>Size</th><th>What it is</th></tr>
  ${Object.entries(kt).sort((a,b)=>b[1][1]-a[1][1]).map(([k,v])=>`<tr><td><b>${k}</b></td><td>${v[0].toLocaleString()}</td><td>${gb(v[1])}</td><td style="white-space:normal;max-width:720px">${esc(KINDS[k]||'')}</td></tr>`).join('')}</table></div></div>
  <div class="card"><h3>Column glossary</h3><div class="mute">Terms used in the run-table headers.</div><div class="tw" style="max-height:none"><table class="gloss">${GLOSS.map(g=>`<tr><td>${esc(g[0])}</td><td>${esc(g[1])}</td></tr>`).join('')}</table></div></div>`;
  const kinds = Object.keys(kt), lab = D.map(name);
  Plotly.newPlot('o1', kinds.map(k=>({type:'bar',name:k,x:lab,y:D.map(d=>(kindTotals(d.files)[k]||[0,0])[1]/1e9)})),
    lay({barmode:'stack',yaxis:{type:'log',title:'GB'},height:380,margin:{t:10,b:110,l:50,r:10}}), CFG);
}

function show(d){
  const kt = kindTotals(d.files);
  main.innerHTML = `<div class="mono mute">${d.acc} · ${esc(d.sub)}</div><h1>${esc(name(d))}: ${esc(d.title)}</h1>
  <div>DOI <a target=_blank href="https://doi.org/${esc(d.doi)}">${esc(d.doi)}</a></div>
  <div class="tiles">${tile(runs(d),'run-table rows')}${tile(d.tables.length,'run tables')}${tile(d.files.length.toLocaleString(),'files')}${tile(gb(d.size),'archive size')}${tile((kt.video||[0])[0],'videos')}${tile(d.pubs.length,'publications')}</div>
  <div class="tabs">${['About','Run tables','Files','Publications'].map((t,i)=>`<button data-t="${i}" class="${i===(d.tables.length?1:0)?'on':''}">${t}</button>`).join('')}</div>
  <div id="tab"></div>`;
  const tabs = main.querySelector('.tabs');
  tabs.onclick = e => { const b = e.target.closest('button'); if (!b) return; tabs.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b)); renderTab(d,+b.dataset.t); };
  renderTab(d, d.tables.length?1:0);
}

function renderTab(d, t){
  const el = document.getElementById('tab');
  if (t===0) el.innerHTML = `<div class="card"><h3>Objective</h3><p>${esc(d.objective)||'<span class=mute>-</span>'}</p>${d.hypothesis?`<h3>Hypothesis</h3><p>${esc(d.hypothesis)}</p>`:''}${d.impacts?`<h3>Research impacts</h3><p>${esc(d.impacts)}</p>`:''}</div>`;
  if (t===1) tablesTab(d, el);
  if (t===2) filesTab(d, el);
  if (t===3) el.innerHTML = `<div class="card"><ul class="pubs">${d.pubs.map(p=>`<li>${esc(p.title)} ${p.doi?`<a target=_blank href="https://doi.org/${esc(p.doi)}">doi ↗</a>`:''}</li>`).join('') || '<li class=mute>none listed</li>'}</ul></div>`;
}

function filesTab(d, el){
  const kt = kindTotals(d.files);
  const imgs = d.files.filter(f=>f[3]==='image' && /Representative/i.test(f[0]));
  const byFolder = {}; d.files.forEach(f=>{(byFolder[f[0]] ||= [0,0]); byFolder[f[0]][0]++; byFolder[f[0]][1]+=f[2];});
  el.innerHTML = `${imgs.length?`<div class="card"><h3>Representative images</h3><div class="imgs">${imgs.map(f=>`<a href="${dl(d.acc,f[1])}" target=_blank><img loading=lazy src="${dl(d.acc,f[1])}" title="${esc(f[1])}" alt="${esc(f[1])}"></a>`).join('')}</div></div>`:''}
  <div class="card"><h3>Folders</h3><div class="tw" style="max-height:none"><table><tr><th>Folder</th><th>Files</th><th>Size</th></tr>${Object.entries(byFolder).sort((a,b)=>b[1][1]-a[1][1]).map(([k,v])=>`<tr><td>${esc(k)}</td><td>${v[0]}</td><td>${gb(v[1])}</td></tr>`).join('')}</table></div></div>
  <div class="card"><h3>By file type</h3><div class="mute">Clicking a file gets a temporary download link from NASA. Zip and .ts files can be several GB each.</div>
  ${Object.keys(kt).sort((a,b)=>kt[b][1]-kt[a][1]).map(k=>{ const fs=d.files.filter(f=>f[3]===k);
    return `<details><summary>${k} · ${fs.length} files · ${gb(kt[k][1])} <span>- ${esc(KINDS[k]||'')}</span></summary><div class="tw"><table><tr><th>Folder</th><th>File</th><th>Size</th></tr>
    ${fs.slice(0,500).map(f=>`<tr><td class="mute">${esc(f[0])}</td><td><a href="${dl(d.acc,f[1])}" target=_blank>${esc(f[1])}</a></td><td>${gb(f[2])}</td></tr>`).join('')}
    ${fs.length>500?`<tr><td colspan=3 class=mute>… ${fs.length-500} more</td></tr>`:''}</table></div></details>`; }).join('')}</div>`;
}

function tablesTab(d, el){
  if (!d.tables.length) { el.innerHTML = '<div class="card"><div class="note">No Experimental table. This is a modelling/analysis study or only has documents. See Files and Publications.</div></div>'; return; }
  el.innerHTML = d.tables.map((t,k)=>`<div class="card"><h3>${esc(t.name)} <span class="badge">${t.rows.length} rows × ${t.columns.length} cols</span></h3>
    <div class="note">${esc(t.note||'No description yet.')}</div>
    <div class="ctl"><label>X</label><select id="x${k}"></select><label>Y</label><select id="y${k}"></select><label>Colour</label><select id="c${k}"><option value="-1">none</option></select>
    <span class="mute" style="font-size:12px">"(text)" columns plot as categories</span></div>
    <div id="p${k}"></div><div class="tw"><table id="t${k}"></table></div><div class="mute" style="font-size:12px;margin-top:6px">Click a header to sort · hover a cell for its full text</div></div>`).join('');
  d.tables.forEach((t,k) => {
    const numeric = t.columns.map((_,c) => t.rows.filter(r => num(r[c])!==null).length > t.rows.length*0.6);
    const opts = t.columns.map((c,j) => `<option value="${j}">${esc(c)}${numeric[j]?'':' (text)'}</option>`).join('');
    const nc = numeric.map((v,j)=>v?j:-1).filter(j=>j>=0);
    const X = document.getElementById('x'+k), Y = document.getElementById('y'+k), C = document.getElementById('c'+k);
    X.innerHTML = opts; Y.innerHTML = opts; C.innerHTML += opts;
    X.value = nc[0] ?? 0; Y.value = nc[1] ?? nc[0] ?? 1;
    const plot = () => {
      const x = +X.value, y = +Y.value, c = +C.value, groups = {};
      t.rows.forEach(r => { const g = c<0 ? 'runs' : (r[c]||'').trim()||'(blank)';
        (groups[g] ||= {x:[],y:[],text:[]}); groups[g].x.push(numeric[x]?num(r[x]):r[x]); groups[g].y.push(numeric[y]?num(r[y]):r[y]); groups[g].text.push(r.slice(0,4).join(' · ')); });
      Plotly.react('p'+k, Object.entries(groups).slice(0,30).map(([g,v]) => ({type:'scatter',mode:'markers',name:g,marker:{size:8,opacity:.85,line:{width:0}},...v})),
        lay({height:360,margin:{t:10,l:60,r:10},showlegend:c>=0,xaxis:{title:t.columns[x]},yaxis:{title:t.columns[y]}}), CFG);
    };
    [X,Y,C].forEach(s => s.onchange = plot); plot();
    let rows = t.rows, sortc = -1, dir = 1;
    const tbl = document.getElementById('t'+k);
    const render = () => tbl.innerHTML = '<tr>'+t.columns.map((c,j)=>`<th data-j="${j}">${esc(c)}${sortc==j?(dir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr>' +
      rows.map(r => '<tr>'+t.columns.map((_,j)=>`<td title="${esc(r[j])}">${esc(r[j])}</td>`).join('')+'</tr>').join('');
    tbl.onclick = e => { const j = e.target.closest('th')?.dataset.j; if (j===undefined) return; dir = sortc==j ? -dir : 1; sortc = j;
      rows = [...t.rows].sort((a,b) => { const p=num(a[j]), q=num(b[j]); return dir*((p!==null&&q!==null)? p-q : String(a[j]).localeCompare(String(b[j]))); }); render(); };
    render();
  });
}
__PIPELINE_JS__
drawList(); route();
</script></body></html>"""


def render():
    return (PAGE.replace("__DATA__", json.dumps(load()).replace("</", "<\\/"))
            .replace("__KINDS__", json.dumps({k: v[1] for k, v in KINDS.items()}))
            .replace("__GLOSS__", json.dumps(GLOSSARY))
            .replace("__PIPELINE_JS__", open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.js")).read()))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(render())
    print("wrote", out)
    if sys.argv[1:] == ["build"]:
        sys.exit()

    class H(DlHandler):
        def do_GET(self):
            if self.path.startswith("/api/dl"):
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(open(out, "rb").read())

    print("http://localhost:8000")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
