// Secret: click the falling Ember logo → "Freefall", an endless dodge game.
// Ember falls forever; station debris rises past; steer with ←/→ (A/D), the mouse, or by dragging. Ember leans
// against its motion (air pushing back). Oxygen bubbles score; speed grows. Esc or × closes it.
const logo = document.querySelector(".logo-gif");
if (logo) {
  logo.style.cursor = "pointer";
  logo.title = "";
  logo.addEventListener("click", open);
}

function open() {
  if (document.getElementById("egg")) return;
  const root = document.createElement("div");
  root.id = "egg";
  root.innerHTML = `<style>
    #egg{position:fixed;inset:0;z-index:1000;background:radial-gradient(ellipse at 50% 30%,#141a2b,#05060b);overflow:hidden;
      font:600 14px Inter,system-ui,sans-serif;color:#e4e7ee;touch-action:none;user-select:none}
    #egg canvas{position:absolute;inset:0;width:100%;height:100%}
    #egg img{position:absolute;width:76px;height:76px;margin:-38px 0 0 -38px;pointer-events:none;will-change:transform}
    #egg .hud{position:absolute;left:16px;top:14px;display:flex;gap:14px;align-items:center}
    #egg .hud b{font-size:22px}#egg .x{position:absolute;right:14px;top:10px;background:none;border:0;color:#8a93a6;font-size:28px;cursor:pointer}
    #egg .msg{position:absolute;left:50%;top:42%;transform:translate(-50%,-50%);text-align:center;background:#12151ecc;
      border:1px solid #2a303c;border-radius:14px;padding:18px 24px;max-width:min(360px,86vw)}
    #egg .msg h2{margin:0 0 6px;font-size:22px}#egg .msg p{margin:4px 0;color:#c9cdd6;font-weight:500}
    #egg .msg button{margin-top:10px;font:inherit;background:#ff7a2f;color:#1a0d05;border:0;border-radius:9px;padding:8px 16px;cursor:pointer}
  </style><canvas></canvas><img src="${logo.src}" alt=""><div class="hud"><span>Depth <b id="eggS">0</b></span><span style="color:#8a93a6">Best <span id="eggB">0</span></span></div>
  <button class="x" aria-label="Close">×</button><div class="msg" id="eggM"></div>`;
  document.body.appendChild(root);
  const cv = root.querySelector("canvas"), ctx = cv.getContext("2d"), ember = root.querySelector("img");
  const $ = id => root.querySelector("#" + id);
  let best = 0;
  try { best = +localStorage.getItem("eggBest") || 0; } catch {}
  $("eggB").textContent = best;
  let W, H, dpr, raf, last, state;
  const keys = {};
  const resize = () => { dpr = devicePixelRatio || 1; W = innerWidth; H = innerHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
  resize();
  const R = 26;  // Ember hit radius

  function reset() {
    state = { x: W / 2, vx: 0, y: H * 0.3, speed: 180, depth: 0, obs: [], bubbles: [], specks: [], spawn: 0.6, tilt: 0, alive: true, target: null, glow: 0 };
    for (let i = 0; i < 60; i++) state.specks.push({ x: Math.random() * W, y: Math.random() * H, l: 6 + Math.random() * 16 });
  }
  function spawnRow() {
    const gap = Math.max(130, 230 - state.depth / 60), gx = 30 + Math.random() * (W - gap - 60), y = H + 30;
    state.obs.push({ y, h: 18, l: 0, r: gx }, { y, h: 18, l: gx + gap, r: W });
    if (Math.random() < 0.7) state.bubbles.push({ x: gx + gap / 2 + (Math.random() - 0.5) * gap * 0.4, y: y + 90 + Math.random() * 60, r: 11, t: Math.random() * 6 });
  }
  function msg(html) { const m = $("eggM"); m.style.display = html ? "block" : "none"; m.innerHTML = html; m.querySelector("button")?.addEventListener("click", start); }
  function start() { reset(); msg(""); last = performance.now(); cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); }
  function over() {
    state.alive = false;
    const d = Math.floor(state.depth);
    if (d > best) { best = d; try { localStorage.setItem("eggBest", best); } catch {} $("eggB").textContent = best; }
    msg(`<h2>Ember bumped into the station</h2><p>Depth ${d}${d >= best ? " · new best!" : ""}</p><button>Fall again</button>`);
  }

  function tick(now) {
    const dt = Math.min(0.033, (now - last) / 1000); last = now;
    const s = state;
    // steering: keys accelerate; mouse/touch pulls toward the pointer
    const ax = ((keys.ArrowRight || keys.d ? 1 : 0) - (keys.ArrowLeft || keys.a ? 1 : 0)) * 2600;
    s.vx += ax * dt;
    if (s.target != null && !ax) s.vx += (s.target - s.x) * 9 * dt * 60 * dt * 10;
    s.vx *= Math.pow(0.04, dt);  // air drag
    s.x = Math.min(W - R, Math.max(R, s.x + s.vx * dt));
    // lean against the motion: moving right tilts left, and the other way round
    s.tilt += ((-s.vx / 900) * 35 - s.tilt) * Math.min(1, dt * 10);
    s.speed += dt * 7; s.depth += s.speed * dt / 10;
    s.spawn -= dt * s.speed / 180;
    if (s.spawn <= 0) { spawnRow(); s.spawn = 1.15; }
    for (const o of s.obs) o.y -= s.speed * dt;
    for (const b of s.bubbles) { b.y -= s.speed * dt; b.t += dt; }
    for (const p of s.specks) { p.y -= s.speed * dt * (1.4 + p.l / 12); if (p.y < -20) { p.y = H + 20; p.x = Math.random() * W; } }
    s.obs = s.obs.filter(o => o.y > -40); s.bubbles = s.bubbles.filter(b => b.y > -30 && !b.got);
    for (const o of s.obs) {
      const cx = Math.max(o.l, Math.min(s.x, o.r)), cy = Math.max(o.y, Math.min(s.y, o.y + o.h));
      if ((cx - s.x) ** 2 + (cy - s.y) ** 2 < (R * 0.8) ** 2) { over(); break; }
    }
    for (const b of s.bubbles) if ((b.x - s.x) ** 2 + (b.y - s.y) ** 2 < (R + b.r) ** 2) { b.got = true; s.depth += 25; s.glow = 1; }
    s.glow = Math.max(0, s.glow - dt * 2);
    draw();
    $("eggS").textContent = Math.floor(s.depth);
    if (s.alive) raf = requestAnimationFrame(tick);
  }

  function draw() {
    const s = state;
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = "#ffffff22"; ctx.lineWidth = 1.5;  // air rushing past
    for (const p of s.specks) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x, p.y + p.l); ctx.stroke(); }
    for (const o of s.obs) {  // station beams: panels with rivets and a warning stripe
      if (o.r - o.l < 2) continue;
      const g = ctx.createLinearGradient(0, o.y, 0, o.y + o.h); g.addColorStop(0, "#5b6476"); g.addColorStop(1, "#2c3240");
      ctx.fillStyle = g; ctx.beginPath(); ctx.roundRect(o.l, o.y, o.r - o.l, o.h, 4); ctx.fill();
      ctx.fillStyle = "#f6c94588"; ctx.fillRect(o.l === 0 ? o.r - 10 : o.l, o.y, 10, o.h);
      ctx.fillStyle = "#9aa3b5"; for (let x = o.l + 14; x < o.r - 10; x += 40) { ctx.beginPath(); ctx.arc(x, o.y + o.h / 2, 2, 0, 7); ctx.fill(); }
    }
    for (const b of s.bubbles) {  // oxygen bubbles
      const r = b.r + Math.sin(b.t * 4) * 1.5;
      ctx.strokeStyle = "#5aa9ff"; ctx.fillStyle = "#5aa9ff22"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(b.x, b.y, r, 0, 7); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#cfe4ff"; ctx.font = "700 10px Inter,sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("O₂", b.x, b.y + 0.5);
    }
    if (s.glow) { ctx.fillStyle = `rgba(255,140,60,${0.35 * s.glow})`; ctx.beginPath(); ctx.arc(s.x, s.y, 50, 0, 7); ctx.fill(); }
    ember.style.transform = `translate(${s.x}px,${s.y}px) rotate(${s.tilt}deg) scale(${1 + s.glow * 0.15})`;
  }

  const onKey = e => {
    if (e.key === "Escape") return close();
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (["ArrowLeft", "ArrowRight", "a", "d"].includes(k)) { keys[k] = e.type === "keydown"; e.preventDefault(); }
  };
  const onPointer = e => { if (e.type === "pointerleave") state.target = null; else state.target = e.clientX; };
  function close() {
    cancelAnimationFrame(raf);
    removeEventListener("keydown", onKey); removeEventListener("keyup", onKey); removeEventListener("resize", resize);
    root.remove();
  }
  addEventListener("keydown", onKey); addEventListener("keyup", onKey); addEventListener("resize", resize);
  root.addEventListener("pointermove", onPointer); root.addEventListener("pointerdown", onPointer); root.addEventListener("pointerleave", onPointer);
  root.querySelector(".x").addEventListener("click", close);
  reset(); draw();
  msg(`<h2>Freefall</h2><p>Ember is falling through the station. Dodge the beams, grab the O₂.</p><p style="color:#8a93a6;font-size:12.5px">← → or A/D, or move the mouse · Esc to leave</p><button>Start falling</button>`);
}
