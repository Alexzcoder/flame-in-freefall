// Walk-in interiors (Moon base, ISS module). Look around like in a room, click a flammable object to start a fire.
// Geometry is illustrative. Flammable surfaces are split into 6 cm cells; firemodel.js decides how fire moves.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MATERIALS } from "./firemodel.js";

const CELL = 0.06;
const MAT_COLOR = { fabric: 0xd9c9a3, pmma_thin: 0xbfe3ff, pmma_thick: 0x8fd0ff, nomex: 0xc7b26a, silicone: 0xe8e8e8, metal: 0x9aa3ad };

function canvasTex(draw, w = 128, h = 128) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const flameTex = canvasTex((g, w, h) => {
  const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
  r.addColorStop(0, "rgba(255,255,230,1)"); r.addColorStop(0.25, "rgba(255,190,80,.95)");
  r.addColorStop(0.6, "rgba(255,90,20,.45)"); r.addColorStop(1, "rgba(255,40,0,0)");
  g.fillStyle = r; g.fillRect(0, 0, w, h);
});
const blueTex = canvasTex((g, w, h) => {   // microgravity flames are dim, round and blue at the base
  const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
  r.addColorStop(0, "rgba(220,240,255,.9)"); r.addColorStop(0.35, "rgba(80,150,255,.6)");
  r.addColorStop(0.7, "rgba(255,120,40,.35)"); r.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = r; g.fillRect(0, 0, w, h);
});
const soft = canvasTex((g, w, h) => {
  const r = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, w, h);
});
const weaveTex = canvasTex((g, w, h) => {   // subtle fabric weave
  g.fillStyle = "#fff"; g.fillRect(0, 0, w, h);
  for (let i = 0; i < w; i += 4) { g.fillStyle = `rgba(0,0,0,${0.05 + 0.04 * ((i / 4) % 2)})`; g.fillRect(i, 0, 2, h); g.fillRect(0, i, w, 2); }
}, 64, 64);
weaveTex.wrapS = weaveTex.wrapT = THREE.RepeatWrapping; weaveTex.repeat.set(6, 6);
const windowTex = (kind) => canvasTex((g, w, h) => {   // the view outside: lunar plain with Earth, or Earth from orbit
  g.fillStyle = "#02030a"; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 90; i++) { g.fillStyle = `rgba(255,255,255,${Math.random() * 0.8})`; g.fillRect(Math.random() * w, Math.random() * h * 0.7, 1.2, 1.2); }
  if (kind === "mars") {
    const sky = g.createLinearGradient(0, 0, 0, h * 0.65); sky.addColorStop(0, "#3a1e14"); sky.addColorStop(1, "#c98a5a");
    g.fillStyle = sky; g.fillRect(0, 0, w, h);
    g.fillStyle = "#fff8e8"; g.beginPath(); g.arc(w * 0.72, h * 0.25, 7, 0, 7); g.fill();   // small, distant Sun
    const gr = g.createLinearGradient(0, h * 0.6, 0, h); gr.addColorStop(0, "#a0522d"); gr.addColorStop(1, "#5e2a14");
    g.fillStyle = gr; g.beginPath(); g.moveTo(0, h * 0.64);
    for (let x = 0; x <= w; x += 12) g.lineTo(x, h * 0.6 + Math.sin(x / 23) * 10 + Math.random() * 5);
    g.lineTo(w, h); g.lineTo(0, h); g.fill();
  } else if (kind === "moon") {
    const e = g.createRadialGradient(w * 0.7, h * 0.28, 2, w * 0.7, h * 0.28, 26);
    e.addColorStop(0, "#9fd0ff"); e.addColorStop(0.6, "#2f6fd1"); e.addColorStop(1, "rgba(47,111,209,0)");
    g.fillStyle = e; g.beginPath(); g.arc(w * 0.7, h * 0.28, 26, 0, 7); g.fill();
    const gr = g.createLinearGradient(0, h * 0.62, 0, h); gr.addColorStop(0, "#9a9a9a"); gr.addColorStop(1, "#5f5f5f");
    g.fillStyle = gr; g.beginPath(); g.moveTo(0, h * 0.66);
    for (let x = 0; x <= w; x += 16) g.lineTo(x, h * 0.62 + Math.sin(x / 37) * 8 + Math.random() * 4);
    g.lineTo(w, h); g.lineTo(0, h); g.fill();
  } else {
    const gr = g.createRadialGradient(w * 0.5, h * 1.6, h * 0.6, w * 0.5, h * 1.6, h * 1.35);
    gr.addColorStop(0, "#1d5fbf"); gr.addColorStop(0.85, "#3b8be0"); gr.addColorStop(0.93, "#9fd3ff"); gr.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  }
}, 256, 256);
const panelTex = canvasTex((g, w, h) => {   // ISS-style rack panel
  g.fillStyle = "#c9ced4"; g.fillRect(0, 0, w, h);
  g.strokeStyle = "#9aa1a9"; g.lineWidth = 3; g.strokeRect(4, 4, w - 8, h - 8);
  g.fillStyle = "#aab1b9"; for (const [x, y] of [[14, 14], [w - 18, 14], [14, h - 18], [w - 18, h - 18]]) g.fillRect(x, y, 5, 5);
}, 128, 128);

// ---------------- scene building blocks ----------------
class Builder {
  constructor(scene) { this.scene = scene; this.surfaces = []; this.cells = []; this.pickables = []; this.props = {}; this.prop = null; }
  track(mesh) { if (this.prop) (this.props[this.prop] ||= []).push(mesh); return mesh; }
  mat(color, opts = {}) { return new THREE.MeshStandardMaterial({ color, roughness: 0.8, metalness: 0.1, side: THREE.DoubleSide, ...opts }); }

  // Rectangle p0 + a*U + b*V. Flammable if mat != metal: split into cells.
  rect(name, mat, p0, U, V, opts = {}) {
    const len = [U.length(), V.length()], Uh = U.clone().normalize(), Vh = V.clone().normalize();
    const N = new THREE.Vector3().crossVectors(Uh, Vh).normalize();
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(len[0], len[1]),
      this.mat(opts.color ?? MAT_COLOR[mat], { ...(mat === "fabric" || mat === "nomex" ? { map: weaveTex } : {}), ...(opts.matOpts || {}) }));
    mesh.matrixAutoUpdate = false;
    mesh.matrix.makeBasis(Uh, Vh, N).setPosition(p0.clone().add(U.clone().multiplyScalar(0.5)).add(V.clone().multiplyScalar(0.5)));
    this.scene.add(mesh); this.track(mesh);
    if (mat === "metal" || MATERIALS[mat]?.inert) return mesh;
    const surf = { name, mat, mesh, first: this.cells.length, count: 0 };
    const na = Math.max(1, Math.round(len[0] / CELL)), nb = Math.max(1, Math.round(len[1] / CELL));
    for (let a = 0; a < na; a++) for (let b = 0; b < nb; b++) {
      const p = p0.clone().add(U.clone().multiplyScalar((a + 0.5) / na)).add(V.clone().multiplyScalar((b + 0.5) / nb));
      this.cells.push({ p: [p.x, p.y, p.z], n: [N.x, N.y, N.z], mat, surf: this.surfaces.length });
    }
    surf.count = this.cells.length - surf.first;
    mesh.userData.surf = this.surfaces.length;
    this.surfaces.push(surf); this.pickables.push(mesh);
    return mesh;
  }

  // Axis-aligned box; flammable boxes get all 6 faces as cell surfaces.
  box(name, mat, center, size, opts = {}) {
    const [cx, cy, cz] = center, [sx, sy, sz] = size, h = [sx / 2, sy / 2, sz / 2];
    if (mat === "metal") {
      const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), this.mat(opts.color ?? MAT_COLOR.metal, { side: THREE.FrontSide, ...(opts.matOpts || {}) }));
      m.position.set(cx, cy, cz); this.scene.add(m); this.track(m); return m;
    }
    const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
    const faces = [
      [V3(cx - h[0], cy - h[1], cz + h[2]), V3(sx, 0, 0), V3(0, sy, 0)], [V3(cx + h[0], cy - h[1], cz - h[2]), V3(-sx, 0, 0), V3(0, sy, 0)],
      [V3(cx - h[0], cy - h[1], cz - h[2]), V3(0, 0, sz), V3(0, sy, 0)], [V3(cx + h[0], cy - h[1], cz + h[2]), V3(0, 0, -sz), V3(0, sy, 0)],
      [V3(cx - h[0], cy + h[1], cz + h[2]), V3(sx, 0, 0), V3(0, 0, -sz)], [V3(cx - h[0], cy - h[1], cz - h[2]), V3(sx, 0, 0), V3(0, 0, sz)],
    ];
    return faces.map(([p0, U, V]) => this.rect(name, mat, p0, U, V, opts));
  }

  neighbours() {   // cells within ~1.5 grid steps are neighbours (also across touching objects)
    const key = (x, y, z) => `${Math.floor(x / 0.1)},${Math.floor(y / 0.1)},${Math.floor(z / 0.1)}`;
    const grid = new Map();
    this.cells.forEach((c, i) => { const k = key(...c.p); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(i); });
    return this.cells.map((c, i) => {
      const out = [], [x, y, z] = c.p;
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        for (const j of grid.get(key(x + dx * 0.1, y + dy * 0.1, z + dz * 0.1)) || []) {
          if (j === i) continue;
          const q = this.cells[j].p, d = Math.hypot(q[0] - x, q[1] - y, q[2] - z);
          if (d <= CELL * 1.5) out.push([j, d]);
        }
      }
      return out;
    });
  }
}

// ---------------- the two interiors ----------------
// Flow is along +x everywhere (supply vent at -x, return at +x). Y is up.
function buildMoonBase(B, kind = "moon") {
  const s = B.scene, R = 4.6, H = 2.7;
  const mars = kind === "mars";   // same layout, Martian dust tracked in, warmer light
  const floor = new THREE.Mesh(new THREE.CircleGeometry(R, 64), B.mat(mars ? 0x6e4232 : 0x55595f)); floor.rotation.x = -Math.PI / 2; s.add(floor);
  const wall = new THREE.Mesh(new THREE.CylinderGeometry(R, R, H, 64, 1, true), B.mat(mars ? 0xe2d2c6 : 0xd8dde3, { side: THREE.BackSide }));
  wall.position.y = H / 2; s.add(wall);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(R, 64, 24, 0, Math.PI * 2, 0, Math.PI / 2), B.mat(0xe6eaef, { side: THREE.BackSide }));
  dome.position.y = H; dome.scale.y = 0.45; s.add(dome);
  for (let i = 0; i < 6; i++) {   // floor panel seams
    const l = new THREE.Mesh(new THREE.BoxGeometry(2 * R, 0.005, 0.02), B.mat(0x3d4147)); l.position.y = 0.003; l.rotation.y = (i * Math.PI) / 6; s.add(l);
  }
  const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
  // crew quarters (-x side): metal cubicle, fabric curtain, sleeping bag, clothes
  B.prop = "crew_quarters";
  B.box("Crew quarters wall", "metal", [-3.2, 1.0, -1.2], [1.2, 2.0, 0.05]);
  B.box("Crew quarters wall", "metal", [-3.2, 1.0, 0.0], [1.2, 2.0, 0.05]);
  B.box("Crew quarters back", "metal", [-3.8, 1.0, -0.6], [0.05, 2.0, 1.2]);
  B.rect("Privacy curtain", "fabric", V3(-2.6, 0.1, -1.15), V3(0, 0, 1.1), V3(0, 1.85, 0));
  B.box("Sleeping bag", "fabric", [-3.15, 0.55, -0.6], [0.9, 0.25, 0.9]);
  B.box("Bunk", "metal", [-3.15, 0.3, -0.6], [1.0, 0.25, 1.0]);
  B.prop = "stowage";
  B.box("Stowage bags", "nomex", [-2.3, 0.3, 0.45], [0.55, 0.55, 0.55]);
  B.box("Stowage bags", "nomex", [-2.3, 0.85, 0.45], [0.5, 0.5, 0.5]);
  B.prop = null;
  // cable tray along the wall at 2.1 m, silicone-jacketed cables
  B.box("Cable tray", "metal", [0, 2.08, -2.2], [5.0, 0.04, 0.25]);
  B.box("Cable bundle (silicone jacket)", "silicone", [0, 2.16, -2.2], [5.0, 0.1, 0.18]);
  // galley table with a cloth
  B.prop = "galley";
  B.box("Table", "metal", [0.3, 0.7, 1.4], [1.4, 0.05, 0.8]);
  B.box("Table leg", "metal", [0.3, 0.35, 1.4], [0.08, 0.7, 0.08]);
  B.rect("Tablecloth", "fabric", V3(-0.4, 0.735, 1.0), V3(1.4, 0, 0), V3(0, 0, 0.8));
  B.rect("Tablecloth (drape)", "fabric", V3(-0.4, 0.43, 1.8), V3(1.4, 0, 0), V3(0, 0.3, 0));
  // lab bench (+x): glovebox with thick acrylic window, thin acrylic labels
  B.prop = "glovebox";
  B.box("Lab bench", "metal", [3.0, 0.45, -0.5], [0.9, 0.9, 1.8]);
  B.box("Glovebox frame", "metal", [3.05, 1.2, -0.5], [0.7, 0.6, 1.0]);
  B.rect("Glovebox window (thick acrylic)", "pmma_thick", V3(2.69, 0.95, -0.95), V3(0, 0, 0.9), V3(0, 0.5, 0));
  B.rect("Acrylic labels & film", "pmma_thin", V3(2.68, 0.55, -1.3), V3(0, 0, 0.6), V3(0, 0.3, 0));
  // window to the lunar surface, ceiling light ring
  const win = new THREE.Mesh(new THREE.CircleGeometry(0.75, 48), new THREE.MeshBasicMaterial({ map: windowTex(kind) }));
  win.position.set(0, 1.5, R - 0.02); win.rotation.y = Math.PI; s.add(win);
  const rim = new THREE.Mesh(new THREE.TorusGeometry(0.77, 0.05, 12, 48), B.mat(0x7c838c)); rim.position.copy(win.position); s.add(rim);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.4, 0.05, 8, 64), new THREE.MeshBasicMaterial({ color: 0xfff6e0 }));
  ring.position.y = H + 0.5; ring.rotation.x = Math.PI / 2; s.add(ring);
  B.prop = null;
  // vents and detector
  const vent = (x, label) => { const m = B.box(label, "metal", [x, 1.6, 2.0], [0.05, 0.4, 0.6], { color: 0x6b7280 }); return m; };
  vent(-4.3, "Supply vent"); vent(4.3, "Return vent");
  return { flowAxis: "x", detector: V3(0.5, H + 0.35, 0), size: { R, H }, views: {
    "Centre": { pos: V3(0.8, 1.6, 0.2), look: V3(-3, 1.1, -0.4) },
    "Crew quarters": { pos: V3(-1.2, 1.5, 0.6), look: V3(-3.2, 1.0, -0.6) },
    "Lab bench": { pos: V3(1.4, 1.5, 0.4), look: V3(3.0, 1.0, -0.5) },
    "Galley": { pos: V3(0.3, 1.6, -1.0), look: V3(0.3, 0.7, 1.4) },
    "Window": { pos: V3(0, 1.6, 2.2), look: V3(0, 1.5, 4.6) },
  }};
}

function buildISS(B) {
  const s = B.scene, L = 9, W = 2.1;
  const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
  panelTex.wrapS = panelTex.wrapT = THREE.RepeatWrapping; panelTex.repeat.set(9, 2);
  // square corridor of rack panels (the ISS lab modules have a square interior)
  for (const [p0, U, V] of [
    [V3(-L / 2, -W / 2, -W / 2), V3(L, 0, 0), V3(0, W, 0)], [V3(-L / 2, -W / 2, W / 2), V3(L, 0, 0), V3(0, W, 0)],
    [V3(-L / 2, -W / 2, -W / 2), V3(L, 0, 0), V3(0, 0, W)], [V3(-L / 2, W / 2, -W / 2), V3(L, 0, 0), V3(0, 0, W)]]) {
    B.rect("Rack panel", "metal", p0, U, V, { color: 0xffffff, matOpts: { map: panelTex } });
  }
  const port = new THREE.Mesh(new THREE.CircleGeometry(0.32, 40), new THREE.MeshBasicMaterial({ map: windowTex("iss") }));
  port.position.set(-0.4, -W / 2 + 0.01, 0); port.rotation.x = -Math.PI / 2; s.add(port);   // nadir window: Earth below
  const prim = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.04, 10, 40), B.mat(0x7c838c)); prim.position.copy(port.position); prim.rotation.x = Math.PI / 2; s.add(prim);
  for (const z of [-0.6, 0.6]) {   // light strips on the ceiling
    const strip = new THREE.Mesh(new THREE.BoxGeometry(L * 0.8, 0.02, 0.12), new THREE.MeshBasicMaterial({ color: 0xf4f8ff })); strip.position.set(0, W / 2 - 0.015, z); s.add(strip);
  }
  for (const x of [-L / 2, L / 2]) B.rect("Bulkhead", "metal", V3(x, -W / 2, x < 0 ? W / 2 : -W / 2), V3(0, 0, x < 0 ? -W : W), V3(0, W, 0), { color: 0xb9bfc6 });
  for (const x of [-L / 2 + 0.01, L / 2 - 0.01]) {   // hatches
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.06, 12, 40), B.mat(0x8b9198)); ring.position.x = x; ring.rotation.y = Math.PI / 2; s.add(ring);
  }
  // crew quarters on the +z wall
  B.prop = "crew_quarters_iss";
  B.rect("Crew quarters curtain", "fabric", V3(-3.2, -0.9, W / 2 - 0.03), V3(1.0, 0, 0), V3(0, 1.8, 0));
  B.box("Sleeping bag", "fabric", [-2.7, 0.0, W / 2 - 0.2], [0.5, 1.6, 0.25]);
  B.rect("Towel", "fabric", V3(-2.15, 0.1, W / 2 - 0.04), V3(0.4, 0, 0), V3(0, 0.6, 0));
  // stowage on the ceiling (Nomex bags)
  B.prop = "stowage";
  B.box("Stowage bags (Nomex)", "nomex", [-1.2, W / 2 - 0.22, 0], [1.0, 0.4, 0.8]);
  B.prop = null;
  // cable bundles in the corners
  B.box("Cable bundle (silicone jacket)", "silicone", [0, W / 2 - 0.08, W / 2 - 0.08], [8.6, 0.12, 0.12]);
  B.box("Cable bundle (silicone jacket)", "silicone", [0, -W / 2 + 0.08, -W / 2 + 0.08], [8.6, 0.12, 0.12]);
  // science glovebox on the -z wall
  B.prop = "glovebox_iss";
  B.box("Glovebox frame", "metal", [1.6, 0.0, -W / 2 + 0.3], [1.0, 0.7, 0.5]);
  B.rect("Glovebox window (thick acrylic)", "pmma_thick", V3(1.15, -0.3, -W / 2 + 0.56), V3(0.9, 0, 0), V3(0, 0.6, 0));
  B.rect("Acrylic labels & film", "pmma_thin", V3(2.3, -0.2, -W / 2 + 0.03), V3(0.6, 0, 0), V3(0, 0.4, 0));
  B.prop = null;
  // laptop with a fabric cover floating (Velcro'd) near the glovebox
  B.rect("Fabric laptop cover", "fabric", V3(0.6, -0.55, -W / 2 + 0.03), V3(0.45, 0, 0), V3(0, 0.35, 0));
  for (const x of [-L / 2 + 0.2, L / 2 - 0.2]) B.box(x < 0 ? "Supply vent" : "Return vent", "metal", [x, 0.6, 0], [0.04, 0.3, 0.5], { color: 0x6b7280 });
  return { flowAxis: "x", detector: V3(3.0, W / 2 - 0.02, 0), size: { L, W }, views: {
    "Centre": { pos: V3(0.2, 0, 0), look: V3(-3, -0.1, 0.9) },
    "Crew quarters": { pos: V3(-1.6, 0.1, -0.3), look: V3(-2.8, 0, 1.05) },
    "Glovebox": { pos: V3(1.2, 0.2, 0.4), look: V3(1.6, -0.1, -1.0) },
    "Down the module": { pos: V3(-4.1, 0.2, 0), look: V3(4, 0, 0) },
  }};
}

// ---------------- generated models (public/models/*.glb) over the simulation geometry ----------------
// Each prop's boxes/rects stay in the scene as the fire model's surfaces (invisible but still clickable/hoverable).
const PROP_MODELS = {   // rotY turns each model's front (+x in the generated file) to face into the room
  crew_quarters: { url: "../models/crew_quarters.glb", rotY: 0 },
  glovebox: { url: "../models/glovebox.glb", rotY: Math.PI },
  glovebox_iss: { url: "../models/glovebox.glb", rotY: -Math.PI / 2 },
  stowage: { url: "../models/stowage.glb", rotY: 0 },
  galley: { url: "../models/galley.glb", rotY: 0 },
};
function fitModels(B, habitatId) {
  const loader = new GLTFLoader();
  for (const [key, meshes] of Object.entries(B.props)) {
    const spec = PROP_MODELS[key]; if (!spec) continue;
    const box = new THREE.Box3(); meshes.forEach(m => { m.updateMatrixWorld(); box.expandByObject(m); });
    const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
    loader.load(spec.url, g => {
      const m = g.scene; m.rotation.y = spec.rotY;
      const mb = new THREE.Box3().setFromObject(m), ms = mb.getSize(new THREE.Vector3());
      m.scale.setScalar(Math.min(size.x / ms.x, size.y / ms.y, size.z / ms.z));   // fit inside the prop's footprint
      const c = new THREE.Box3().setFromObject(m);
      m.position.add(center.clone().sub(c.getCenter(new THREE.Vector3())));
      if (habitatId !== "iss") m.position.y += box.min.y - new THREE.Box3().setFromObject(m).min.y;   // rest on the floor
      B.scene.add(m);
      meshes.forEach(x => {   // still raycast: hover and fire keep working
        const surf = B.surfaces[x.userData.surf];
        if (surf?.mat === "pmma_thick") {   // the generated glovebox is an open frame: keep the acrylic window as glass
          Object.assign(x.material, { transparent: true, opacity: 0.28, color: new THREE.Color(0xbfe6ff), roughness: 0.05, metalness: 0.1, map: null });
          x.material.needsUpdate = true;
        } else x.material.visible = false;
      });
    }, undefined, () => console.warn("prop model not loaded, keeping simple geometry:", spec.url));
  }
}

// ---------------- public API ----------------
export function createInterior(container, habitatId, { onPick, onHover } = {}) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
  catch { container.textContent = "This view needs WebGL, which this browser does not support."; return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.domElement.style.display = "block";
  container.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1118);
  const fog = new THREE.FogExp2(0x2a2c30, 0); scene.fog = fog;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.3));
  const key = new THREE.PointLight(0xfff2dd, 30, 12); key.position.set(0, 2.2, 0); scene.add(key);
  const camera = new THREE.PerspectiveCamera(70, 1, 0.02, 60);

  const B = new Builder(scene);
  const room = habitatId === "iss" ? buildISS(B) : buildMoonBase(B, habitatId);
  fitModels(B, habitatId);
  const nbrs = B.neighbours();
  const cells = B.cells;

  // detector
  const detector = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.04, 24), new THREE.MeshStandardMaterial({ color: 0xf1f1f1, emissive: 0x000000 }));
  detector.position.copy(room.detector); if (habitatId === "iss") detector.rotation.x = 0; scene.add(detector);

  // flames: up to 3 sprites per cell (stacked upward under gravity), char marks, smoke
  const N = cells.length;
  const flamePos = new Float32Array(N * 3 * 3 * 2), charPos = new Float32Array(N * 3 * 2);   // both faces of each patch
  const flameGeo = new THREE.BufferGeometry(); flameGeo.setAttribute("position", new THREE.BufferAttribute(flamePos, 3));
  const charGeo = new THREE.BufferGeometry(); charGeo.setAttribute("position", new THREE.BufferAttribute(charPos, 3));
  const flameMat = new THREE.PointsMaterial({ size: 0.13, map: flameTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
  const flames = new THREE.Points(flameGeo, flameMat); flames.frustumCulled = false; scene.add(flames);
  const chars = new THREE.Points(charGeo, new THREE.PointsMaterial({ size: 0.075, color: 0x111111, map: soft, transparent: true, opacity: 0.9, depthWrite: false }));
  chars.frustumCulled = false; scene.add(chars);
  const glow = new THREE.PointLight(0xff8a3d, 0, 6); scene.add(glow);
  const SMOKE = 2500, smokePos = new Float32Array(SMOKE * 3), smokeVel = new Float32Array(SMOKE * 3), smokeAge = new Float32Array(SMOKE).fill(-1);
  const smokeGeo = new THREE.BufferGeometry(); smokeGeo.setAttribute("position", new THREE.BufferAttribute(smokePos, 3));
  const smoke = new THREE.Points(smokeGeo, new THREE.PointsMaterial({ size: 0.35, map: soft, color: 0x6b6f76, transparent: true, opacity: 0.22, depthWrite: false }));
  smoke.frustumCulled = false; scene.add(smoke);

  // look-around controls: orbit a target a few cm in front of the camera, inverted = "turn your head"
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableZoom = false; controls.enablePan = false; controls.rotateSpeed = -0.35; controls.enableDamping = true;
  const goTo = (name, instant) => {
    const v = room.views[name]; if (!v) return;
    const dir = v.look.clone().sub(v.pos).normalize();
    flight = { t0: performance.now(), ms: instant ? 0 : 900, fromPos: camera.position.clone(), fromT: controls.target.clone(), toPos: v.pos.clone(), toT: v.pos.clone().add(dir.multiplyScalar(0.05)) };
  };
  let flight = null;
  const first = Object.keys(room.views)[0];
  camera.position.copy(room.views[first].pos); goTo(first, true);
  renderer.domElement.addEventListener("wheel", e => {   // zoom = narrow the field of view
    e.preventDefault(); camera.fov = Math.min(85, Math.max(30, camera.fov + e.deltaY * 0.03)); camera.updateProjectionMatrix();
  }, { passive: false });

  // picking
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const solids = [];
  scene.traverse(o => { if (o.isMesh) solids.push(o); });
  const pick = ev => {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const h = ray.intersectObjects(solids, false)[0];
    if (!h || h.object.userData.surf === undefined) return null;
    const surf = B.surfaces[h.object.userData.surf];
    let best = surf.first, bd = Infinity;
    for (let i = surf.first; i < surf.first + surf.count; i++) {
      const p = cells[i].p, d = (p[0] - h.point.x) ** 2 + (p[1] - h.point.y) ** 2 + (p[2] - h.point.z) ** 2;
      if (d < bd) { bd = d; best = i; }
    }
    return { cell: best, surf, point: h.point };
  };
  let hovered = null, down = null;
  const highlight = (surf, on) => { if (surf) for (const m of B.pickables) if (B.surfaces[m.userData.surf] === surf) m.material.emissive?.setHex(on ? 0x3a2410 : 0); };
  renderer.domElement.addEventListener("pointermove", e => {
    const p = pick(e), s = p?.surf ?? null;
    if (s !== hovered) { highlight(hovered, false); highlight(s, true); hovered = s; }
    renderer.domElement.style.cursor = s ? "pointer" : "grab";
    onHover?.(s ? { name: s.name, mat: s.mat } : null, e);
  });
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const p = pick(e); if (p) onPick?.(p);
  });

  const resize = () => { const w = container.clientWidth, h = container.clientHeight; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(container); resize();

  // simulation state rendered at time t (seconds of simulated time)
  let sim = null, simT = 0, lastSmokeT = 0, gravity = 0, flowU = 0.1, flameUp = new THREE.Vector3(0, 1, 0);
  const startMark = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  startMark.visible = false; scene.add(startMark);

  function setSim(result, cond, startCell) {
    sim = result; simT = 0; lastSmokeT = 0; smokeAge.fill(-1);
    gravity = cond.gravity_g; flowU = Math.max(0.01, (result.startVerdict.U ?? cond.vent_cm_s) / 100);
    flameMat.map = gravity > 0.05 ? flameTex : blueTex; flameMat.needsUpdate = true;
    if (startCell != null) { startMark.position.set(...cells[startCell].p); startMark.visible = true; }
  }
  function clear() { sim = null; startMark.visible = false; smokeAge.fill(-1); }

  function draw(now) {
    let nf = 0, nc = 0, gx = 0, gy = 0, gz = 0;
    if (sim) {
      const flick = 0.012;
      for (let i = 0; i < N; i++) {
        const t0 = sim.tIgn[i]; if (!(t0 <= simT)) continue;
        const life = sim.quenchedAt !== null ? sim.quenchedAt : sim.burnFor(i);
        const c = cells[i];
        if (simT < t0 + life) {
          const stack = gravity > 0.05 ? 3 : 1;   // taller flames under gravity, round ones in microgravity
          for (const side of [1, -1]) for (let k = 0; k < stack; k++) {
            const o = 0.02 + k * 0.06 * Math.min(1, gravity * 4 + 0.2);
            flamePos[nf * 3] = c.p[0] + side * c.n[0] * 0.03 + (Math.random() - 0.5) * flick;
            flamePos[nf * 3 + 1] = c.p[1] + side * c.n[1] * 0.03 + (gravity > 0.05 ? o : (Math.random() - 0.5) * flick);
            flamePos[nf * 3 + 2] = c.p[2] + side * c.n[2] * 0.03 + (Math.random() - 0.5) * flick;
            nf++;
          }
          gx += c.p[0]; gy += c.p[1]; gz += c.p[2];
        } else for (const side of [1, -1]) { charPos.set([c.p[0] + side * c.n[0] * 0.006, c.p[1] + side * c.n[1] * 0.006, c.p[2] + side * c.n[2] * 0.006], nc * 3); nc++; }
      }
    }
    const burning = nf / (2 * (gravity > 0.05 ? 3 : 1));
    flameGeo.setDrawRange(0, nf); flameGeo.attributes.position.needsUpdate = true;
    charGeo.setDrawRange(0, nc); charGeo.attributes.position.needsUpdate = true;
    flameMat.size = gravity > 0.05 ? 0.2 : 0.16;
    if (burning) { glow.position.set(gx / burning, gy / burning, gz / burning); glow.intensity = Math.min(25, 1.5 + burning * 0.15) * (0.85 + Math.random() * 0.3); }
    else glow.intensity = 0;
    // smoke: spawn from burning cells, drift with the airflow (+x) and rise under gravity
    const dt = Math.max(0, simT - lastSmokeT); lastSmokeT = simT;
    if (sim && burning && dt > 0) {
      let spawn = Math.min(60, Math.ceil(burning * dt * 0.05));
      for (let s = 0; s < SMOKE && spawn > 0; s++) {
        if (smokeAge[s] >= 0) continue;
        const i = Math.floor(Math.random() * N); if (!(sim.tIgn[i] <= simT)) { continue; }
        smokeAge[s] = 0; spawn--;
        smokePos.set(cells[i].p, s * 3);
        smokeVel.set([flowU * (0.6 + Math.random() * 0.6), (gravity > 0.05 ? 0.05 + 0.15 * Math.sqrt(gravity) : 0) + (Math.random() - 0.5) * 0.02, (Math.random() - 0.5) * 0.02], s * 3);
      }
    }
    let live = 0;
    for (let s = 0; s < SMOKE; s++) {
      if (smokeAge[s] < 0) { smokePos[s * 3 + 1] = -99; continue; }
      smokeAge[s] += dt; live++;
      for (let k = 0; k < 3; k++) smokePos[s * 3 + k] += smokeVel[s * 3 + k] * dt + (Math.random() - 0.5) * 0.004;
      const lim = habitatId === "iss" ? [4.4, 0.98, 0.98] : [4.3, room.size.H + 0.9, 4.3];   // stay inside the room
      for (let k = 0; k < 3; k++) {
        const lo = k === 1 && habitatId !== "iss" ? 0.05 : -lim[k];
        if (smokePos[s * 3 + k] > lim[k] || smokePos[s * 3 + k] < lo) { smokeVel[s * 3 + k] *= -0.2; smokePos[s * 3 + k] = Math.min(lim[k], Math.max(lo, smokePos[s * 3 + k])); }
      }
      if (smokeAge[s] > 900) smokeAge[s] = -1;
    }
    smokeGeo.attributes.position.needsUpdate = true;
    fog.density = Math.min(0.12, live / SMOKE * 0.15);
    const alarm = sim && sim.detectAt !== null && simT >= sim.detectAt;
    detector.material.emissive.setHex(alarm && Math.floor(now / 300) % 2 ? 0xff2020 : 0x000000);
  }

  renderer.setAnimationLoop(() => {
    const now = performance.now();
    if (flight) {
      const k = flight.ms ? Math.min(1, (now - flight.t0) / flight.ms) : 1, e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      camera.position.lerpVectors(flight.fromPos, flight.toPos, e); controls.target.lerpVectors(flight.fromT, flight.toT, e);
      if (k === 1) flight = null;
    }
    controls.update(); draw(now); renderer.render(scene, camera);
  });

  return {
    cells, nbrs, views: Object.keys(room.views), goTo, setSim, clear,
    setTime(t) { if (t < simT) { smokeAge.fill(-1); lastSmokeT = t; } simT = t; },
    surfaceName(cell) { return B.surfaces[cells[cell]?.surf]?.name; },
    detectorDist(cell) { const p = cells[cell].p; return room.detector.distanceTo(new THREE.Vector3(...p)); },
  };
}
