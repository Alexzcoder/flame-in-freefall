// DOM rendering for the station: one card per habitat, sliders, and a result row per material.
import { assess } from "./app.js";

const el = (tag, props = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
};

const MATERIAL_NAMES = { pmma: "PMMA (acrylic)", sibal: "Sibal (cotton/fiberglass fabric)" };
const materialName = m => MATERIAL_NAMES[m] ?? m.charAt(0).toUpperCase() + m.slice(1);

const CONFIDENCE_TEXT = { green: "High confidence", yellow: "Medium confidence", red: "Low confidence" };
const RISK_TEXT = { high: "High", medium: "Medium", low: "Low" };

function slider({ label, min, max, step, value, fmt, onInput }) {
  const out = el("output", {}, fmt(value));
  const input = el("input", { type: "range", min, max, step, value });
  input.addEventListener("input", () => {
    const v = Number(input.value);
    out.textContent = fmt(v);
    onInput(v);
  });
  return {
    node: el("label", { class: "slider" }, el("span", {}, label), input, out),
    set(v) { input.value = v; out.textContent = fmt(v); },
  };
}

function outcomeText(run) {
  const o = run.outcome;
  if (o.ignited === false) return "did not ignite";
  const parts = ["ignited"];
  if (o.burn_time_s != null) parts.push(`burned ${o.burn_time_s} s`);
  if (o.result) parts.push(`result: ${o.result}`);
  return parts.join(", ");
}

function detailsTable(near) {
  const rows = near.map(({ run, dist }) => el("tr", {},
    el("td", {}, el("a", {
      href: `https://psi.nasa.gov/physci/repo/data/investigations/${run.investigation}`,
      target: "_blank", rel: "noopener",
    }, run.id)),
    el("td", {}, (run.conditions.atmosphere.o2_frac * 100).toFixed(1)),
    el("td", {}, run.conditions.flow.velocity_cm_s.toFixed(1)),
    el("td", {}, outcomeText(run)),
    el("td", {}, run.extra.air_display ?? ""),
    el("td", {}, dist.toFixed(2)),
  ));
  return el("table", {},
    el("thead", {}, el("tr", {}, ...["Test run", "O₂ %", "Airflow cm/s", "What happened", "Raw airflow note", "Distance"].map(h => el("th", {}, h)))),
    el("tbody", {}, rows));
}

function renderMaterial(a, isOpen, onToggle) {
  const name = materialName(a.material);
  let headline;
  if (a.risk) {
    const filled = { low: 1, medium: 2, high: 3 }[a.risk];
    const meter = el("span", { class: "meter", title: `Risk level: ${RISK_TEXT[a.risk]}` },
      ...[1, 2, 3].map(n => el("i", { class: n <= filled ? "on" : "" })));
    headline = el("span", { class: "risk" }, `Risk: ${RISK_TEXT[a.risk]}`, meter);
  } else {
    headline = el("span", { class: "risk none" }, "No reliable estimate");
  }
  const sub = a.known
    ? `${a.flames} of the ${a.known} nearest tests ignited a flame`
    : "No matching tests";

  const details = el("details", {}, el("summary", {}, a.near.length ? "Why? Show the nearest real tests" : "Why?"));
  if (isOpen) details.open = true;
  details.addEventListener("toggle", () => onToggle(details.open));
  details.append(el("p", { class: "reason" }, a.reason));
  if (a.near.length) details.append(detailsTable(a.near));

  return el("div", { class: "material" },
    el("div", { class: "head" },
      el("span", { class: `dot ${a.confidence}`, title: CONFIDENCE_TEXT[a.confidence] }),
      el("strong", {}, name),
      headline,
      el("span", { class: `conf ${a.confidence}` }, CONFIDENCE_TEXT[a.confidence])),
    el("div", { class: "sub" }, sub),
    details);
}

// Builds one habitat card. `onChange(state)` fires after every recalculation (the chart listens to it).
export function mountHabitat(root, base, labelled, onChange) {
  const state = { ...base };
  const open = new Set();                       // materials whose "Why?" panel is open
  const results = el("div", { class: "results" });

  const render = () => {
    results.replaceChildren(...state.materials.map(m =>
      renderMaterial(assess(state, m, labelled), open.has(m), isOpen => (isOpen ? open.add(m) : open.delete(m)))));
    onChange(state);
  };

  const o2 = slider({ label: "Oxygen", min: 10, max: 45, step: 0.5, value: state.o2_frac * 100,
    fmt: v => `${v.toFixed(1)} %`, onInput: v => { state.o2_frac = v / 100; render(); } });
  const pressure = slider({ label: "Pressure", min: 30, max: 150, step: 0.1, value: state.pressure_kpa,
    fmt: v => `${v.toFixed(1)} kPa (${(v / 6.895).toFixed(1)} psi)`, onInput: v => { state.pressure_kpa = v; render(); } });
  const airflow = slider({ label: "Airflow", min: 0, max: 30, step: 0.5, value: state.airflow_cm_s,
    fmt: v => `${v.toFixed(1)} cm/s`, onInput: v => { state.airflow_cm_s = v; render(); } });
  const gravity = slider({ label: "Gravity", min: 0, max: 1, step: 0.001, value: state.gravity_g,
    fmt: v => `${v.toFixed(3)} g`, onInput: v => { state.gravity_g = v; render(); } });

  const reset = el("button", { type: "button", class: "reset" }, "Reset to habitat values");
  reset.addEventListener("click", () => {
    Object.assign(state, base);
    o2.set(base.o2_frac * 100); pressure.set(base.pressure_kpa);
    airflow.set(base.airflow_cm_s); gravity.set(base.gravity_g);
    render();
  });

  const card = el("section", { class: "card", id: "hab-" + base.id },
    el("h2", {}, base.name),
    base.airflow_verified ? null : el("p", { class: "warn" }, "⚠ Airflow is an unverified placeholder, not a measured value."),
    el("div", { class: "sliders" }, o2.node, pressure.node, airflow.node, gravity.node, reset),
    results);
  root.append(card);
  render();
  return state;
}
