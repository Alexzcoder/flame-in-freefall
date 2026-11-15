// Flame lab: real-time 2D fluid simulation of a small fire (WebGL2).
// Stable-fluids solver (semi-Lagrangian advection, Jacobi pressure projection, vorticity confinement) plus a
// one-step combustion model: fuel vapour + oxygen -> heat + soot, only where it is hot enough.
// Buoyancy is proportional to gravity, so the flame shape emerges from the physics: tall and flickering in 1 g,
// short and rounder on the Moon, a dim sphere fed only by diffusion in microgravity (which can starve itself of
// oxygen when the fan is off, as BASS-II saw). Pressure: reaction ~ sqrt(p), diffusion ~ 1/sqrt(p). ILLUSTRATIVE: drawn with hand-tuned knobs.
// The NASA-calibrated knobs (simparams.json, flame/calibrate.py) drive the predictions; see dataset/shape_eval.md.

const VS = `#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = p * 0.5 + 0.5; gl_Position = vec4(p, 0., 1.); }`;

const HEAD = `#version 300 es
precision highp float; in vec2 uv; out vec4 o; uniform vec2 tx;`;

const SHADERS = {
  advect: `${HEAD} uniform sampler2D vel, src; uniform float dt; uniform vec4 keep;
    void main(){ vec2 v = texture(vel, uv).xy; o = texture(src, uv - dt * v * tx) * keep; }`,
  // r = temperature, g = fuel vapour, b = oxygen (1 = this cabin's O2 level), a = soot/smoke
  react: `${HEAD} uniform sampler2D s; uniform float dt, k, heat, cool, ign, emit, o2, time, dif, round_, difO, difF, cond, anchor, emit0; uniform vec4 fuelRect;
    void main(){
      vec4 c = texture(s, uv);
      vec4 n = texture(s, uv + vec2(tx.x, 0.)) + texture(s, uv - vec2(tx.x, 0.)) + texture(s, uv + vec2(0., tx.y)) + texture(s, uv - vec2(0., tx.y));
      c.b += (n.b * 0.25 - c.b) * min(0.24, difO * dif);    // oxygen diffusion: the only supply when nothing moves (slower at high pressure)
      c.g += (n.g * 0.25 - c.g) * min(0.24, difF * dif);    // fuel vapour diffuses out too: in still microgravity air the flame sits where fuel meets oxygen
      c.r += (n.r * 0.25 - c.r) * cond;                     // heat conduction
      vec2 ctr = 0.5 * (fuelRect.xy + fuelRect.zw), hs = 0.5 * (fuelRect.zw - fuelRect.xy);
      vec2 d = (uv - ctr) / hs;
      bool onFuel = round_ > 0.5 ? dot(d, d) < 1. : (abs(d.x) < 1. && abs(d.y) < 1.);   // droplet / porous sphere burner are round
      if (onFuel) { c.g += dt * emit * (emit0 + 2.0 * min(c.r, 1.5)); c.r = max(c.r, time < 1.2 ? 1.2 : anchor); }  // surface keeps some heat (anchors the flame); igniter for 1.2 s
      float r = k * c.g * c.b * smoothstep(ign, ign + 0.25, c.r);   // reaction rate
      r = min(r, min(c.g, c.b) / max(dt, 1e-3));
      c.g -= r * dt; c.b -= r * dt * 0.9;
      c.r += r * dt * heat * (0.6 + 0.4 * o2);              // richer air burns hotter
      c.a += r * dt * 0.35;
      c.r -= dt * cool * c.r * c.r;                         // radiative loss (dominant at low flow)
      float edge = min(min(uv.x, 1. - uv.x), min(uv.y, 1. - uv.y));
      if (edge < 0.025) { c.b = mix(c.b, o2, 0.5); c.r *= 0.5; c.a *= 0.8; }  // open boundary: fresh cabin air
      o = max(c, 0.);
    }`,
  forces: `${HEAD} uniform sampler2D vel, s, curl; uniform float dt, buoy, flow, eps;
    void main(){
      vec2 v = texture(vel, uv).xy; vec4 c = texture(s, uv);
      v.y += dt * buoy * (c.r - 0.05 * c.a);                // hot gas rises, soot weighs a little
      v.x += (flow - v.x) * dt * 0.8 * (1. - smoothstep(0.0, 0.12, uv.x)) + (flow - v.x) * dt * 0.05;  // fan inflow from the left
      float L = texture(curl, uv - vec2(tx.x, 0.)).r, R = texture(curl, uv + vec2(tx.x, 0.)).r;
      float B = texture(curl, uv - vec2(0., tx.y)).r, T = texture(curl, uv + vec2(0., tx.y)).r, C = texture(curl, uv).r;
      vec2 g = vec2(abs(T) - abs(B), abs(R) - abs(L)); g /= length(g) + 1e-5;
      v += dt * eps * vec2(g.x, -g.y) * C;                  // vorticity confinement: keeps the flicker
      o = vec4(v, 0., 1.);
    }`,
  curl: `${HEAD} uniform sampler2D vel;
    void main(){ float L = texture(vel, uv - vec2(tx.x, 0.)).y, R = texture(vel, uv + vec2(tx.x, 0.)).y;
      float B = texture(vel, uv - vec2(0., tx.y)).x, T = texture(vel, uv + vec2(0., tx.y)).x; o = vec4(0.5 * (R - L - T + B), 0., 0., 1.); }`,
  div: `${HEAD} uniform sampler2D vel;
    void main(){ float L = texture(vel, uv - vec2(tx.x, 0.)).x, R = texture(vel, uv + vec2(tx.x, 0.)).x;
      float B = texture(vel, uv - vec2(0., tx.y)).y, T = texture(vel, uv + vec2(0., tx.y)).y; o = vec4(0.5 * (R - L + T - B), 0., 0., 1.); }`,
  jacobi: `${HEAD} uniform sampler2D pr, dv;
    void main(){ float L = texture(pr, uv - vec2(tx.x, 0.)).r, R = texture(pr, uv + vec2(tx.x, 0.)).r;
      float B = texture(pr, uv - vec2(0., tx.y)).r, T = texture(pr, uv + vec2(0., tx.y)).r;
      o = vec4((L + R + B + T - texture(dv, uv).r) * 0.25, 0., 0., 1.); }`,
  project: `${HEAD} uniform sampler2D pr, vel;
    void main(){ float L = texture(pr, uv - vec2(tx.x, 0.)).r, R = texture(pr, uv + vec2(tx.x, 0.)).r;
      float B = texture(pr, uv - vec2(0., tx.y)).r, T = texture(pr, uv + vec2(0., tx.y)).r;
      o = vec4(texture(vel, uv).xy - 0.5 * vec2(R - L, T - B), 0., 1.); }`,
  show: `${HEAD} uniform sampler2D s; uniform float blue, k; uniform vec4 win;
    void main(){
      vec4 c = texture(s, win.xy + uv * win.zw); float t = clamp(c.r, 0., 2.);   // win: shown part of the domain
      vec3 fire = vec3(1.6 * t, 1.1 * t * t, 0.55 * t * t * t);                    // red -> orange -> yellow-white
      float zone = clamp(k * c.g * c.b * smoothstep(0.35, 0.6, c.r) * 0.45, 0., 1.); // where it is reacting now
      vec3 col = fire * mix(1.0, 0.45, blue) + vec3(0.18, 0.42, 1.0) * zone * (0.35 + 1.1 * blue);  // soot-free blue in microgravity
      col = mix(col, col * 0.4 + vec3(0.07), clamp(c.a * 0.35, 0., 0.7));          // smoke
      o = vec4(pow(col, vec3(0.85)) + vec3(0.018, 0.022, 0.035), 1.);
    }`,
};

// Physics knobs. Defaults = hand-tuned; flame/calibrate.py fits them to NASA runs and writes simparams.json,
// which replaces them when present (same knobs as flame/sim.py THETA; see dataset/shape_eval.md for how well it fits).
const TH = { k: 16, heat: 1.5, cool: 0.6, ign: 0.35, buoy: 26, dif_o2: 0.22, dif_fuel: 0.20, cond: 0.10, flow_scale: 0.9,
             eps0: 4, eps_g: 10, emit_scale: 1, anchor: 0.5, emit0: 0.7 };
// What you SEE stays on the hand-tuned knobs: the tuned set (fitted at 0 g to whether flames survive) shrinks the flames
// to a thin rim and loses the 1 g plume. Predictions (insights.json, risk.json, the emulator) use the tuned set.
// To draw with tuned knobs for some fuels, list them in TUNED.
const THC = { ...TH }, TUNED = [];
const knobs = fetch(new URL("simparams.json", import.meta.url)).then(r => r.ok ? r.json() : null)
  .then(j => { for (const key in THC) if (j?.theta?.[key] != null) THC[key] = j.theta[key]; }).catch(() => {});
const knobsFor = fuel => TUNED.includes(fuel) ? THC : TH;
export const calibrated = knobs;

export function createFlameLab(canvas, init = {}) {
  const gl = canvas.getContext("webgl2", { antialias: false, premultipliedAlpha: false });
  if (!gl || !gl.getExtension("EXT_color_buffer_float")) { canvas.replaceWith(Object.assign(document.createElement("p"), { textContent: "The flame lab needs WebGL2." })); return null; }
  const W = 96, H = 128;
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const progs = {};
  for (const [name, fs] of Object.entries(SHADERS)) {
    const p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, VS], [gl.FRAGMENT_SHADER, fs]]) {
      const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(name + ": " + gl.getShaderInfoLog(sh));
      gl.attachShader(p, sh);
    }
    gl.bindAttribLocation(p, 0, "p"); gl.linkProgram(p); progs[name] = p;
  }
  const tex = () => {
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, W, H, 0, gl.RGBA, gl.HALF_FLOAT, null);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    return { t, fb };
  };
  const pair = () => { let a = tex(), b = tex(); return { get r() { return a; }, get w() { return b; }, swap() { [a, b] = [b, a]; } }; };
  const vel = pair(), scal = pair(), prs = pair(), dv = tex(), cu = tex();

  function pass(name, target, uniforms) {
    const p = progs[name]; gl.useProgram(p);
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fb : null);
    gl.viewport(0, 0, target ? W : canvas.width, target ? H : canvas.height);
    gl.uniform2f(gl.getUniformLocation(p, "tx"), 1 / W, 1 / H);
    let unit = 0;
    for (const [k, v] of Object.entries(uniforms)) {
      const loc = gl.getUniformLocation(p, k);
      if (v && v.t) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, v.t); gl.uniform1i(loc, unit++); }
      else if (Array.isArray(v)) gl[`uniform${v.length}f`](loc, ...v);
      else gl.uniform1f(loc, v);
    }
    gl.enableVertexAttribArray(0); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  const P = { gravity_g: 1, o2: 0.21, flow_cm_s: 0, fuel: "fabric", pressure_kpa: 101.325, ...init };
  let time = 0, raf = 0, running = true;
  function clear() {
    for (const t of [vel.r, vel.w, prs.r, prs.w, dv, cu]) { gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
    for (const t of [scal.r, scal.w]) { gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb); gl.clearColor(0, 0, P.o2 / 0.21, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
    time = 0;
  }
  // fuel: a burning sample (thin fabric strip, thick acrylic block) or a droplet
  const FUEL = { fabric: { rect: [0.38, 0.14, 0.62, 0.17], emit: 2.2 }, pmma: { rect: [0.40, 0.12, 0.60, 0.20], emit: 0.9 },
                 droplet: { rect: [0.4625, 0.29, 0.5375, 0.3463], emit: 7.0, round: 1 },
                 burner: { rect: [0.4625, 0.40, 0.5375, 0.4563], emit: 9.0, round: 1 } };   // ACME/CFI-G: gas fed through a small porous sphere

  function step(dt) {
    const T = knobsFor(P.fuel);
    const g = Math.max(0, P.gravity_g), o2 = P.o2 / 0.21, f = FUEL[P.fuel] || FUEL.fabric;
    const flow = P.flow_cm_s * T.flow_scale;   // cm/s -> cells/s (one cell ~ 1 mm, playback slowed for visibility)
    time += dt;
    pass("advect", vel.w, { vel: vel.r, src: vel.r, dt, keep: [0.995, 0.995, 1, 1] }); vel.swap();
    pass("advect", scal.w, { vel: vel.r, src: scal.r, dt, keep: [0.995, 0.99, 1, 0.997] }); scal.swap();
    const pr = Math.max(0.2, P.pressure_kpa / 101.325);   // denser gas: faster reaction, slower diffusion
    pass("react", scal.w, { s: scal.r, dt, k: T.k * Math.min(2.2, o2) * Math.sqrt(pr), heat: T.heat, cool: T.cool, ign: T.ign,
      emit: f.emit * T.emit_scale, o2, time, dif: 1 / Math.sqrt(pr), fuelRect: f.rect, round_: f.round || 0,
      difO: T.dif_o2, difF: T.dif_fuel, cond: T.cond, anchor: T.anchor, emit0: T.emit0 }); scal.swap();
    pass("curl", cu, { vel: vel.r });
    pass("forces", vel.w, { vel: vel.r, s: scal.r, curl: cu, dt, buoy: T.buoy * g * Math.sqrt(pr), flow, eps: T.eps0 + T.eps_g * Math.sqrt(g) }); vel.swap();
    pass("div", dv, { vel: vel.r });
    for (let i = 0; i < 24; i++) { pass("jacobi", prs.w, { pr: prs.r, dv }); prs.swap(); }
    pass("project", vel.w, { pr: prs.r, vel: vel.r }); vel.swap();
  }
  // Shown part of the domain: the whole domain fits a 3:4 canvas; a wider canvas shows a band around the fuel
  // (more room above it, where a rising flame goes) instead of stretching.
  function view() {
    const a = canvas.width / canvas.height, d = W / H, f = FUEL[P.fuel] || FUEL.fabric;
    if (a <= d) { const w = a / d; return [(1 - w) / 2, 0, w, 1]; }
    const h = d / a, fy = (f.rect[1] + f.rect[3]) / 2;
    return [0, Math.min(Math.max(fy - 0.3 * h, 0), 1 - h), 1, h];
  }
  function frame() {
    if (!running) return;
    for (let i = 0; i < 2; i++) step(1 / 60);
    pass("show", null, { s: scal.r, blue: Math.max(0, 1 - P.gravity_g * 3), k: knobsFor(P.fuel).k, win: view() });
    raf = requestAnimationFrame(frame);
  }
  clear();
  for (let i = 0; i < (P.warmup || 0); i++) step(1 / 60);   // pre-run (used for screenshots/tests)
  frame();
  return {
    set(p) { Object.assign(P, p); },
    reset(p) { if (p) Object.assign(P, p); clear(); for (let i = 0; i < (P.warmup || 0); i++) step(1 / 60); },
    stop() { running = false; cancelAnimationFrame(raf); },
    get params() { return { ...P }; },
  };
}
