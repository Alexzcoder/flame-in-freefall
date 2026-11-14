// Logic for the station simulator. No DOM code here, so it can be reused by the team dashboard.
//
// Model: "nearest real tests". For a habitat + material we find the closest PSI solid-fuel runs
// (by O2 and airflow), summarise what happened in them, and say how far we are from real data.

// ---------- thresholds (judgement calls, listed in the page footnotes) ----------
export const SOLID_PRESSURE_KPA = 101.325; // solid-fuel tables have no pressure: cabin air was assumed
export const PRESSURE_TOLERANCE_KPA = 5;
export const O2_UNIT = 0.05;               // 5 points of O2 = 1 distance unit
export const MAX_DIST = 3;                 // nearest test further than this -> red
export const GREEN_NEAREST = 0.5;          // green needs the nearest test this close...
export const GREEN_RADIUS = 1.5;           // ...and at least GREEN_MIN tests within this radius
export const GREEN_MIN = 3;

// ---------- loading (the ONLY place that reads data) ----------
export async function loadData() {
  // Deployed: the API serves the dataset. Local `python3 -m http.server` from the repo root: read the file directly.
  let res = await fetch("/api/dataset").catch(() => null);
  if (!res || !res.ok) res = await fetch("../../dataset/flame_runs.json");
  if (!res.ok) throw new Error("could not load dataset: " + res.status);
  const d = await res.json();
  if (d.schema_version !== "0.2") throw new Error("schema changed: " + d.schema_version);
  // Inverse flames carry the burner-stream O2, not the room atmosphere: leave them out.
  const tested = d.runs.filter(r => r.conditions.o2_location === "ambient");
  return {
    tested,                                        // everything that was run (for the coverage chart)
    labelled: tested.filter(r => r.has_outcome),   // runs with an observed outcome (for the risk model)
    investigations: Object.fromEntries(d.investigations.map(i => [i.id, i])),
  };
}

// ---------- Step 3: candidates ----------
// Same fuel, solid only, and with the numbers we need.
export function candidatesFor(runs, material) {
  return runs.filter(r =>
    r.conditions.fuel.name === material &&
    r.conditions.fuel.phase === "solid" &&
    r.conditions.atmosphere.o2_frac != null &&
    r.conditions.flow.velocity_cm_s != null
  );
}

// ---------- Step 4: distance and nearest ----------
// O2: 5 points = 1 unit. Airflow: doubling = 1 unit (log scale).
// Pressure is ignored on purpose: solid-fuel runs only have an assumed pressure.
export function distance(habitat, run) {
  const dO2 = (habitat.o2_frac - run.conditions.atmosphere.o2_frac) / O2_UNIT;
  const dFlow = Math.log2((habitat.airflow_cm_s + 1) / (run.conditions.flow.velocity_cm_s + 1));
  return Math.hypot(dO2, dFlow);
}

export function nearest(habitat, candidates, k = 5) {
  return candidates
    .map(run => ({ run, dist: distance(habitat, run) }))
    .sort((a, b) => a.dist - b.dist)
    .slice(0, k);
}

// ---------- Step 5: risk ----------
// IMPORTANT: BASS-II runs were started with an ignited flame at the listed (initial) flow, and the flow
// was then stepped down until the flame went out ("extinction"). So `result: extinction` does NOT mean
// the flame died at the listed flow. What a run tells us at that flow is: did a flame ignite?
export function classify(run) {
  if (run.outcome.ignited === true) return "flame";
  if (run.outcome.ignited === false) return "no_flame";
  return "unknown";
}

export function riskLevel(share) {
  if (share == null) return null;
  return share >= 0.75 ? "high" : share >= 0.4 ? "medium" : "low";
}

// ---------- Step 6: confidence ----------
const red = reason => ({ level: "red", reason });

export function confidence(habitat, near, nCandidates) {
  const g = habitat.gravity_g;
  if (g > 0 && g < 1) return red("No partial-gravity combustion data exists: every run in the dataset is at 0 g.");
  if (g >= 1) return red("The dataset only has microgravity (0 g) runs, none at 1 g.");
  if (nCandidates === 0) return red("No test runs exist for this material.");
  if (near[0].dist > MAX_DIST) return red(`The nearest test is too far away (distance ${near[0].dist.toFixed(1)}).`);
  if (Math.abs(habitat.pressure_kpa - SOLID_PRESSURE_KPA) > PRESSURE_TOLERANCE_KPA) {
    return red("Solid-fuel tests have no measured pressure (cabin air, 101.3 kPa, was assumed), so this pressure is untested.");
  }
  const close = near.filter(n => n.dist <= GREEN_RADIUS).length;
  if (near[0].dist <= GREEN_NEAREST && close >= GREEN_MIN) {
    return { level: "green", reason: `Real tests close by: nearest at distance ${near[0].dist.toFixed(2)}, ${close} within ${GREEN_RADIUS}.` };
  }
  return {
    level: "yellow",
    reason: `Interpolating: nearest test at distance ${near[0].dist.toFixed(2)}, only ${close} within ${GREEN_RADIUS}.`,
  };
}

// ---------- everything for one habitat + material ----------
export function assess(habitat, material, labelled, k = 5) {
  const cands = candidatesFor(labelled, material);
  const near = nearest(habitat, cands, k);
  if (near.length === 0) {
    return { material, candidates: 0, near, flames: 0, known: 0, share: null, risk: null,
             confidence: "red", reason: confidence(habitat, near, 0).reason };
  }
  const conf = confidence(habitat, near, cands.length);
  const known = near.filter(n => classify(n.run) !== "unknown");
  const flames = known.filter(n => classify(n.run) === "flame").length;
  const share = known.length ? flames / known.length : null;
  return {
    material,
    candidates: cands.length,
    near,
    flames,
    known: known.length,
    share,
    // a red verdict means "no reliable estimate": we do not show a risk level for it
    risk: conf.level === "red" ? null : riskLevel(share),
    confidence: conf.level,
    reason: conf.reason,
  };
}
