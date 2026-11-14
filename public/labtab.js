// "Flame lab" tab on the home page: the fluid flame simulation (station/flamelab.js) plus real NASA footage.
// Built the first time the tab opens (each canvas needs its own WebGL context).
import { createFlameLab } from "./station/flamelab.js";
import { realFootage } from "./footage.js";

const PRESETS = {
  "Earth room": { gravity_g: 1, o2: 0.21, flow_cm_s: 0 },
  "Moon base": { gravity_g: 0.166, o2: 0.30, flow_cm_s: 5 },
  "ISS, fan on": { gravity_g: 0, o2: 0.21, flow_cm_s: 10 },
  "ISS, fan off": { gravity_g: 0, o2: 0.21, flow_cm_s: 0 },
};
let built = false;
function build() {
  if (built) return; built = true;
  const $ = id => document.getElementById(id), cur = { ...PRESETS["ISS, fan on"], fuel: "fabric" };
  $("labctl").innerHTML = `<div class="chiprow" id="labpre">${Object.keys(PRESETS).map(n => `<button>${n}</button>`).join("")}</div>
    <label>Gravity<input id="lg" type="range" min="0" max="1" step="0.001"><output id="lgv"></output></label>
    <label>Oxygen<input id="lo" type="range" min="15" max="40" step="0.5"><output id="lov"></output></label>
    <label>Fan airflow<input id="lf" type="range" min="0" max="30" step="0.5"><output id="lfv"></output></label>
    <div class="chiprow" id="labfuel"><button data-f="fabric" class="on">Fabric strip</button><button data-f="pmma">Acrylic block</button><button data-f="droplet">Fuel droplet</button></div>
    <button class="linkbtn" id="labre">↺ relight</button>`;
  const lab = createFlameLab($("labmain"), cur);
  $("labstrip").innerHTML = Object.keys(PRESETS).map((n, i) => `<div><canvas id="ls${i}" width="240" height="320"></canvas><span class="cap">${n}</span></div>`).join("");
  Object.values(PRESETS).forEach((p, i) => createFlameLab($("ls" + i), { ...p, fuel: "fabric" }));
  const S = { lg: ["gravity_g", 1, v => +v === 0 ? "0 g (orbit)" : (+v).toFixed(3) + " g"], lo: ["o2", 100, v => (+v).toFixed(1) + " %"], lf: ["flow_cm_s", 1, v => (+v).toFixed(1) + " cm/s"] };
  const real = () => realFootage($("labreal"), { o2: cur.o2, pressure: 101.325, flow: cur.flow_cm_s, gravity: cur.gravity_g,
    phase: cur.fuel === "droplet" ? "liquid" : "solid" }, "No real NASA footage near these conditions: the simulation is all there is here.");
  const sync = relight => {
    for (const [id, [k, f, fmt]] of Object.entries(S)) { $(id).value = cur[k] * f; $(id + "v").textContent = fmt($(id).value); }
    relight ? lab?.reset(cur) : lab?.set(cur); real();
  };
  for (const [id, [k, f, fmt]] of Object.entries(S)) $(id).oninput = () => { cur[k] = +$(id).value / f; $(id + "v").textContent = fmt($(id).value); lab?.set(cur); clearTimeout(sync.t); sync.t = setTimeout(real, 400); };
  $("labpre").onclick = e => { const p = PRESETS[e.target.textContent]; if (!p) return; Object.assign(cur, p); [...$("labpre").children].forEach(b => b.classList.toggle("on", b === e.target)); sync(true); };
  $("labfuel").onclick = e => { const f = e.target.dataset.f; if (!f) return; cur.fuel = f; [...$("labfuel").children].forEach(b => b.classList.toggle("on", b === e.target)); sync(true); };
  $("labre").onclick = () => lab?.reset(cur);
  sync(false);
}
document.querySelector('[data-tab="lab"]').addEventListener("click", build);
if (location.hash === "#lab") build();
