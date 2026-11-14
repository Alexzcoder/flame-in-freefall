// Fire-spread model for the habitat interiors. Pure functions, no DOM: testable with node.
//
// HONESTY RULE: every number is tagged. kind "data" = measured by NASA (with citation). kind "assumption" = our
// simplification, shown as such in the UI. Outside the tested range a material is "untested", never invented.
//
// Model in one paragraph: each surface cell ignites when the flame front reaches it. The front moves at a
// material's spread rate, scaled by oxygen (assumption: rate ∝ O2²), slower against the airflow than with it.
// The airflow a flame feels is the ventilation plus buoyancy (zero in microgravity). Below the quench flow the
// flame puts itself out (measured by BASS-II); above the blowoff flow it is blown out. Smoke reaches the
// detector after the burned area passes a threshold and the air has carried it there.

export const SRC = {
  bass2_spread: { kind: "data", text: "BASS-II: thin PMMA spreads ~2.2 mm/s in microgravity (Summary Report pp. 21, 49)" },
  bass2_thick: { kind: "data", text: "BASS-II: thick PMMA spreads ~0.04 mm/s (Summary Report pp. 50, 135)" },
  bass2_quench: { kind: "data", text: "BASS-II: flame quenches below ~1 cm/s airflow at 21 % O₂, ~2.6 cm/s at 16 % (pp. 21–23); 1–5 cm/s overall (p. 108)" },
  bass2_blowoff: { kind: "data", text: "BASS-II: spread rate roughly independent of opposed flow up to ~40 cm/s, blowoff above (pp. 44, 49)" },
  saffire_sibal: { kind: "data", text: "SAFFIRE-II runs 2-5, 2-6: cotton/fiberglass fabric spread 2.1–2.6 mm/s at ~22 % O₂, 20 cm/s (PSI-99)" },
  saffire_nomex: { kind: "data", text: "SAFFIRE-II run 2-7: Nomex was not ignited at ~22 % O₂ (PSI-99, note 2)" },
  saffire_silicone: { kind: "data", text: "SAFFIRE-II runs 2-1…2-4: silicone flame did not spread in microgravity at ~22 % O₂ (PSI-99)" },
  a_o2: { kind: "assumption", text: "Spread rate scales with O₂² (simplified thermal theory); no solid-fuel data above 22.2 % O₂" },
  a_pressure: { kind: "assumption", text: "Quench flow rises at lower pressure as √(101.3 kPa / p); spread rate itself pressure-independent" },
  a_buoyancy: { kind: "assumption", text: "Buoyant flow next to a small flame ≈ 30 cm/s × √(g); zero in microgravity" },
  a_direction: { kind: "assumption", text: "Against the airflow a flame spreads at half its downstream speed, sideways at 0.7×" },
  a_burn: { kind: "assumption", text: "Burn time per 6 cm patch: thin fabric/film 40 s, thick acrylic 10 min" },
  a_smoke: { kind: "assumption", text: "Detector alarms once ~150 cm² has burned and the air has carried the smoke to it (≥1 cm/s by diffusion)" },
};

// Materials. ref = spread rate (mm/s) at ref_o2; maxTested = highest O2 at which NASA tested it (above: extrapolated).
export const MATERIALS = {
  fabric: { name: "Cotton/fiberglass fabric", proxy: "SIBAL", ref: 2.3, ref_o2: 0.22, maxTested: 0.222, burn_s: 40,
            src: ["saffire_sibal"], quench: "thin" },
  pmma_thin: { name: "Thin acrylic film (PMMA)", ref: 2.2, ref_o2: 0.21, maxTested: 0.222, burn_s: 40, src: ["bass2_spread"], quench: "thin" },
  pmma_thick: { name: "Thick acrylic panel (PMMA)", ref: 0.04, ref_o2: 0.21, maxTested: 0.222, burn_s: 600, src: ["bass2_thick"], quench: "thick" },
  nomex: { name: "Nomex stowage fabric", ref: 0, ref_o2: 0.22, maxTested: 0.221, burn_s: 60, src: ["saffire_nomex"], nonIgnitingUpTo: 0.221 },
  silicone: { name: "Silicone cable jacket", ref: 0, ref_o2: 0.22, maxTested: 0.221, burn_s: 60, src: ["saffire_silicone"], nonIgnitingUpTo: 0.221 },
  metal: { name: "Aluminium", inert: true },
};

const lerp = (a, b, t) => a + (b - a) * t;

// Quench (radiative extinction) flow, cm/s, from the two BASS-II points; floor/ceiling are assumptions.
export function quenchFlow(o2, pressure_kpa, kind = "thin") {
  const t = (0.21 - o2) / (0.21 - 0.16);                         // 0 at 21 %, 1 at 16 %
  let q = Math.min(5, Math.max(0.5, lerp(1.0, 2.6, t)));         // 1.0 @21 %, 2.6 @16 %, kept within 0.5–5 (p. 108)
  if (kind === "thick") q *= 1.5;                                // 400 µm quenched at ~1.5 cm/s vs 1.0 (p. 21)
  return q * Math.sqrt(101.325 / pressure_kpa);
}

export const blowoffFlow = o2 => 40 * (o2 / 0.21);              // cm/s
export const buoyantFlow = g => 30 * Math.sqrt(Math.max(0, g)); // cm/s
export const effectiveFlow = (vent, g) => Math.hypot(vent, buoyantFlow(g));

// Everything the UI needs to know about one material under given conditions.
export function materialVerdict(key, c) {
  const m = MATERIALS[key];
  if (m.inert) return { key, state: "inert", rate: 0, note: "Does not burn." };
  const U = effectiveFlow(c.vent_cm_s, c.gravity_g);
  const extrapolated = c.o2 > m.maxTested + 1e-9;
  if (m.nonIgnitingUpTo !== undefined) {
    if (c.o2 <= m.nonIgnitingUpTo) return { key, state: "no_spread", rate: 0, src: m.src, note: "NASA tests: no ignition / no spread at this O₂." };
    return { key, state: "untested", rate: 0, src: m.src, note: `Never tested above ${(m.maxTested * 100).toFixed(1)} % O₂: unknown.` };
  }
  const q = quenchFlow(c.o2, c.pressure_kpa, m.quench);
  if (U < q) return { key, state: "quench", rate: 0, U, q, src: [...m.src, "bass2_quench"],
    note: `Airflow ${U.toFixed(1)} cm/s is below the quench flow ${q.toFixed(1)} cm/s: the flame puts itself out.` };
  if (U > blowoffFlow(c.o2)) return { key, state: "blowoff", rate: 0, U, src: [...m.src, "bass2_blowoff"], note: "Airflow blows the flame out." };
  const rate = m.ref * (c.o2 / m.ref_o2) ** 2;
  return { key, state: "spreads", rate, U, q, extrapolated, src: [...m.src, "a_o2", "a_direction", "a_burn"],
    note: `Spreads ~${rate.toFixed(rate < 0.1 ? 3 : 1)} mm/s downstream${extrapolated ? " (extrapolated beyond tested O₂)" : ""}.` };
}

// Direction factor: flow is along +x. d = unit vector from burning cell to neighbour.
export function directionFactor(dx) { return dx > 0.5 ? 1 : dx < -0.5 ? 0.5 : 0.7; }

// Ignition times over a cell graph (Dijkstra). cells[i] = {p:[x,y,z], mat}; nbrs[i] = [[j, dist_m], ...].
export function simulate(cells, nbrs, start, c) {
  const verdicts = {};
  for (const k of Object.keys(MATERIALS)) verdicts[k] = materialVerdict(k, c);
  const n = cells.length, tIgn = new Float64Array(n).fill(Infinity);
  const v0 = verdicts[cells[start].mat];
  const result = { tIgn, verdicts, startVerdict: v0, quenchedAt: null };
  if (v0.state === "quench") { tIgn[start] = 0; result.quenchedAt = 6; return finish(result, cells, c); }   // flickers, dies
  if (v0.state !== "spreads") return finish(result, cells, c);                                            // won't ignite / unknown
  tIgn[start] = 0;
  const done = new Uint8Array(n), heap = new MinHeap();
  heap.push(0, start);
  while (heap.size) {
    const [t, i] = heap.pop();
    if (done[i]) continue; done[i] = 1;
    for (const [j, d] of nbrs[i]) {
      const v = verdicts[cells[j].mat];
      if (v.state !== "spreads" || done[j]) continue;
      const dir = (cells[j].p[0] - cells[i].p[0]) / Math.max(d, 1e-6);
      const rate = Math.min(v.rate, verdicts[cells[i].mat].rate || v.rate) * directionFactor(dir); // mm/s
      const tt = t + (d * 1000) / Math.max(rate, 1e-4);
      if (tt < tIgn[j]) { tIgn[j] = tt; heap.push(tt, j); }
    }
  }
  return finish(result, cells, c);
}

class MinHeap {   // binary heap of [time, index]
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  push(t, i) {
    const a = this.a; a.push([t, i]); let k = a.length - 1;
    while (k > 0) { const p = (k - 1) >> 1; if (a[p][0] <= a[k][0]) break; [a[p], a[k]] = [a[k], a[p]]; k = p; }
  }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last; let k = 0;
      for (;;) {
        const l = 2 * k + 1, r = l + 1; let m = k;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === k) break; [a[m], a[k]] = [a[k], a[m]]; k = m;
      }
    }
    return top;
  }
}

const CELL_AREA_CM2 = 36;           // 6 cm grid
function finish(r, cells, c) {
  // smoke detection: time when burned area passes threshold + transport time to detector
  const times = [...r.tIgn].filter(Number.isFinite).sort((a, b) => a - b);
  const need = Math.ceil(150 / CELL_AREA_CM2);
  const U = Math.max(1, effectiveFlow(c.vent_cm_s, c.gravity_g));
  r.detectAt = r.quenchedAt === null && times.length >= need && c.detectorDist_m != null
    ? times[need - 1] + (c.detectorDist_m * 100) / U : null;
  r.areaAt = t => {
    let a = 0;
    for (let i = 0; i < r.tIgn.length; i++) if (r.tIgn[i] <= t) a += CELL_AREA_CM2;
    return a;
  };
  r.burnFor = i => MATERIALS[cells[i].mat].burn_s ?? 60;
  return r;
}
