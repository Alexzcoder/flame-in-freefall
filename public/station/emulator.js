// Flame emulator in the browser: the neural network trained by flame/emulator.py on thousands of runs of the
// calibrated flame simulation. Conditions in, predicted flame out (image + shape + will it keep burning), instantly.
// It copies the simulation, errors included; members disagreeing = the emulator is unsure.
const FUELS_DEFAULT = ["fabric", "pmma", "droplet", "burner"];
let model = null;

function f16(b64) {   // base64 little-endian float16 → Float32Array
  const bin = atob(b64), n = bin.length / 2, out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const h = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, m = h & 1023;
    out[i] = e === 0 ? s * m * 2 ** -24 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * 2 ** (e - 15);
  }
  return out;
}

export async function loadEmulator(url = "/models/flame_emulator.json", json = null) {
  if (model) return model;
  const j = json || await fetch(url).then(r => r.json());
  model = { ...j, mean: f16(j.img_mean), basis: f16(j.img_basis),
    members: j.members.map(layers => layers.map(l => ({ ...l, w: f16(l.w), b: f16(l.b) }))) };
  return model;
}

const lin = (l, x) => { const y = new Float32Array(l.out); for (let o = 0; o < l.out; o++) { let s = l.b[o]; const r = o * l.in; for (let i = 0; i < l.in; i++) s += l.w[r + i] * x[i]; y[o] = s; } return y; };
const silu = x => x.map(v => v / (1 + Math.exp(-v)));
const sig = v => 1 / (1 + Math.exp(-v));

// c: {gravity_g, o2 (mole fraction), pressure_kpa, flow_cm_s, fuel, emit?}
export function predictFlame(c) {
  if (!model) throw new Error("call loadEmulator() first");
  const fuels = model.fuels || FUELS_DEFAULT, g = Math.max(0, c.gravity_g);
  const x = [g, Math.sqrt(g), c.o2 / 0.21, Math.log(c.pressure_kpa / 101.325), c.flow_cm_s / 20, Math.log(c.emit || 1),
             ...fuels.map(f => +(c.fuel === f))].map((v, i) => (v - model.mu[i]) / model.sd[i]);
  const [H, W] = model.img, n = H * W * 3, img = new Float32Array(n), outs = [];
  for (const L of model.members) {
    let h = Float32Array.from(x);
    for (let k = 0; k < 3; k++) h = silu(lin(L[k], h));
    const coef = lin(L[3], h), sc = lin(L[4], h);
    for (let p = 0; p < n; p++) { let v = model.mean[p]; for (let k = 0; k < coef.length; k++) v += coef[k] * model.basis[k * n + p]; img[p] += Math.min(1, Math.max(0, v)) / model.members.length; }
    outs.push(sc);
  }
  const avg = i => outs.reduce((s, o) => s + o[i], 0) / outs.length;
  const sd = i => Math.sqrt(outs.reduce((s, o) => s + (o[i] - avg(i)) ** 2, 0) / outs.length);
  return {
    image: img, size: [H, W],
    ignited: sig(avg(0)), extinguished: sig(avg(1)), alive: avg(2),
    aspect: Math.exp(avg(3)), fill: avg(4), hollow: avg(5), blue: avg(6), flicker: avg(7),
    unsure: Math.max(sd(0), sd(1)) > 1.0 || sd(3) > 0.35,   // members disagree: treat the answer as a guess
  };
}

// Paint a prediction into a canvas (scaled up, smoothed).
export function drawFlame(canvas, pred) {
  const [H, W] = pred.size, small = document.createElement("canvas"); small.width = W; small.height = H;
  const ctx = small.getContext("2d"), im = ctx.createImageData(W, H);
  for (let p = 0; p < H * W; p++) { for (let k = 0; k < 3; k++) im.data[4 * p + k] = Math.round(255 * Math.min(1, pred.image[3 * p + k] * 1.6)); im.data[4 * p + 3] = 255; }
  ctx.putImageData(im, 0, 0);
  const c = canvas.getContext("2d"); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  c.drawImage(small, 0, 0, canvas.width, canvas.height);
}
