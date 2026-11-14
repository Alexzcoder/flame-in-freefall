import assert from "node:assert/strict";
import { simulate, materialVerdict, quenchFlow, effectiveFlow } from "./firemodel.js";
// 1 m strip of fabric along x, 6 cm cells, fire lit at x=0.5 m
const cells = [], nbrs = [];
for (let i = 0; i <= 16; i++) cells.push({ p: [i * 0.06, 0, 0], mat: "fabric" });
cells.forEach((_, i) => nbrs.push([[i - 1, 0.06], [i + 1, 0.06]].filter(([j]) => j >= 0 && j < cells.length)));
const iss = { o2: 0.21, pressure_kpa: 101.325, gravity_g: 0, vent_cm_s: 10, detectorDist_m: 2 };
let r = simulate(cells, nbrs, 8, iss);
const down = r.tIgn[16], up = r.tIgn[0];
console.log("ISS fabric: downstream end", down.toFixed(0), "s, upstream end", up.toFixed(0), "s, detect", r.detectAt?.toFixed(0), "s");
assert.ok(down < up, "downstream (with the flow) must burn sooner");
assert.ok(Math.abs(down - 480 / (2.3 * (0.21 / 0.22) ** 2)) < 1, "downstream time = distance / rate");
// microgravity, fans off -> quench (BASS-II)
r = simulate(cells, nbrs, 8, { ...iss, vent_cm_s: 0 });
assert.equal(r.startVerdict.state, "quench"); assert.equal(r.tIgn.filter(Number.isFinite).length, 1);
console.log("ISS fans off:", r.startVerdict.note);
// Moon, fans off -> buoyancy keeps it alive, faster at 30 % O2, flagged extrapolated
const moon = { o2: 0.30, pressure_kpa: 70.3, gravity_g: 0.166, vent_cm_s: 0, detectorDist_m: 2 };
r = simulate(cells, nbrs, 8, moon);
assert.equal(r.startVerdict.state, "spreads"); assert.ok(r.startVerdict.extrapolated);
console.log("Moon fans off:", r.startVerdict.note, "| buoyant flow", effectiveFlow(0, 0.166).toFixed(1), "cm/s");
// untested / no-spread materials
assert.equal(materialVerdict("nomex", moon).state, "untested");
assert.equal(materialVerdict("nomex", iss).state, "no_spread");
assert.equal(materialVerdict("metal", iss).state, "inert");
// quench flow matches BASS-II points
assert.ok(Math.abs(quenchFlow(0.21, 101.325) - 1.0) < 1e-9 && Math.abs(quenchFlow(0.16, 101.325) - 2.6) < 1e-9);
console.log("all model checks passed");
