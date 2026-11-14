// node public/station/emulator.test.mjs: the browser emulator must reproduce the reference prediction that
// flame/emulator.py wrote into the export (same weights, same maths).
import { readFileSync } from "fs";
globalThis.atob ??= s => Buffer.from(s, "base64").toString("binary");
const { loadEmulator, predictFlame } = await import("./emulator.js");
const j = JSON.parse(readFileSync(new URL("../models/flame_emulator.json", import.meta.url)));
await loadEmulator(null, j);
const p = predictFlame(j.reference.cond), sig = v => 1 / (1 + Math.exp(-v));
// ignited/extinguished compared as probabilities (a log-odds of 90 is just "certain": 1.0 in float64)
const got = [p.ignited, p.extinguished, p.alive, Math.log(p.aspect), p.fill, p.hollow, p.blue, p.flicker];
const want = j.reference.scalars.map((v, i) => i < 2 ? sig(v) : v);
const sum = p.image.reduce((a, b) => a + b, 0);
got.forEach((v, i) => { if (Math.abs(v - want[i]) > 0.02) throw new Error(`scalar ${i}: ${v} vs ${want[i]}`); });
if (Math.abs(sum - j.reference.img_sum) > 0.5) throw new Error(`image sum ${sum} vs ${j.reference.img_sum}`);
console.log("emulator.js matches the Python reference:", got.map(v => v.toFixed(3)).join(" "));
