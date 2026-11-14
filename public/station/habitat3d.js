// Habitat explorer: a furnished Moon base and ISS module seen as a "dollhouse" (near walls are see-through).
// Every object carries an info marker. Hover = quick card, click = full details. Layouts are illustrative.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const CAT = { burn: { color: "#ff7a2f", icon: "🔥" }, safety: { color: "#3ecf8e", icon: "🧯" }, system: { color: "#5aa9ff", icon: "⚙" } };

// ---------- the furniture: one entry per object, info written for a curious non-expert ----------
// mat: key into firemodel.MATERIALS for things that burn (the page adds NASA's verdict live)
const ITEMS = {
  crew_quarters: { name: "Crew quarters", cat: "burn", mat: "fabric", model: "crew_quarters", h: 2.0,
    text: "A private sleeping booth with a fabric curtain and a sleeping bag: the biggest pile of fabric in the habitat, and where people are least alert." },
  galley: { name: "Galley table", cat: "burn", mat: "fabric", model: "galley", h: 0.85,
    text: "Meals, a fabric tablecloth and food packaging. Heaters and drink-bag warmers sit right next to things that burn." },
  glovebox: { name: "Science glovebox", cat: "burn", mat: "pmma_thick", model: "glovebox", h: 1.3,
    text: "A sealed work box with a thick acrylic window. NASA's BASS-II experiment burned acrylic samples inside a glovebox like this on the ISS." },
  stowage: { name: "Cargo bags", cat: "burn", mat: "nomex", model: "stowage", h: 0.95,
    text: "Soft cargo bags made of Nomex, a flame-resistant fabric chosen precisely because it is hard to ignite." },
  cables: { name: "Cable bundle", cat: "burn", mat: "silicone", h: 0,
    text: "Power and data cables with silicone jackets. Wiring faults and overheated connectors are classic ignition sources." },
  extinguisher: { name: "Fire extinguisher", cat: "safety", model: "extinguisher", h: 0.75,
    text: "Portable extinguisher. In a sealed cabin the extinguishing agent and the smoke stay in the air, so the crew puts on breathing masks first." },
  mask: { name: "Emergency breathing mask", cat: "safety", model: "mask", h: 0.45,
    text: "The first thing the crew grabs when the fire alarm sounds: smoke cannot be vented out of a sealed habitat quickly." },
  detector: { name: "Smoke detector", cat: "safety", h: 0,
    text: "In microgravity smoke doesn't rise; it drifts with the ventilation, so detectors sit in the airflow path. NASA's SAME experiments measured microgravity smoke to design better detectors." },
  fireport: { name: "Fire port", cat: "safety", h: 0,
    text: "A small port in an equipment rack where the extinguisher nozzle goes, so a fire inside the rack can be fought without opening it." },
  eclss: { name: "Life-support rack", cat: "system", model: "eclss", h: 2.0,
    text: "Makes oxygen and removes CO₂. In a fire response the fans are switched off so they stop feeding the flame and spreading smoke. NASA's BASS-II showed flames can go out by themselves when the airflow stops in orbit." },
  battery: { name: "Battery bank", cat: "system", model: "battery", h: 1.2,
    text: "Lithium-ion batteries store the habitat's power. A failing cell can overheat on its own (thermal runaway), a fire source not covered by the combustion data here." },
  suit: { name: "Spacesuit", cat: "system", model: "suit", h: 1.9,
    text: "Spacesuits run on pure oxygen at about 4.3 psi. In pure oxygen most materials burn far more easily; try the Spacesuit preset in the Habitat check." },
  plants: { name: "Plant growth chamber", cat: "system", model: "plants", h: 1.6,
    text: "Grow lights, pumps and wiring run around the clock next to dry plant material, a small but constant electrical risk." },
  treadmill: { name: "Treadmill", cat: "system", model: "treadmill", h: 1.0,
    text: "Daily exercise: an electric motor and belt friction are heat sources, in use every day." },
  laptop: { name: "Laptop station", cat: "system", model: "laptop", h: 0.95,
    text: "Laptops mean lithium-ion batteries and plastics. Overheating electronics are one of the most likely ways a spacecraft fire starts." },
};

// placements: [item id, x, y, z, rotY or "center"(face the room centre)]
const LAYOUTS = {
  moon: { cam: [7.5, 6.8, 8.5], target: [0, 0.8, 0], items: [
    ["crew_quarters", -3.9, 0, -0.9, "center"], ["stowage", -3.4, 0, 1.0, "center"], ["extinguisher", -2.3, 0, 3.1, "center"],
    ["mask", -1.6, 0.7, 3.55, "center"], ["eclss", -0.4, 0, 3.95, "center"], ["battery", 1.4, 0, 3.6, "center"],
    ["plants", 3.0, 0, 2.6, "center"], ["glovebox", 3.8, 0, 0.2, "center"], ["laptop", 3.2, 0, -2.0, "center"],
    ["treadmill", 1.2, 0, -3.5, "center"], ["suit", -1.4, 0, -3.7, "center"], ["galley", -0.3, 0, -0.2, 0.4]] },
  iss: { cam: [2.5, 3.4, 7.8], target: [0, -0.1, 0], items: [
    ["eclss", -2.6, -1.0, -0.78, 0], ["glovebox", 1.6, -1.0, -0.62, Math.PI / 2], ["crew_quarters", -0.7, -1.0, 0.75, -Math.PI / 2],
    ["laptop", 3.0, -0.4, 0.7, -Math.PI / 2], ["stowage", 0.3, 0.62, -0.1, 0], ["treadmill", -4.0, -1.0, 0.0, 0],
    ["extinguisher", 4.3, -0.6, 0.85, -Math.PI / 2], ["mask", 4.3, 0.15, 0.95, -Math.PI / 2], ["plants", 3.8, -1.0, -0.7, Math.PI / 2],
    ["battery", -1.0, -1.0, -0.75, Math.PI / 2]] },
};

function loadTex(url, repeat) {
  const t = new THREE.TextureLoader().load(url); t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); t.anisotropy = 8; return t;
}
function marker(cat) {
  const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
  g.fillStyle = CAT[cat].color; g.globalAlpha = 0.25; g.beginPath(); g.arc(64, 64, 62, 0, 7); g.fill();
  g.globalAlpha = 1; g.beginPath(); g.arc(64, 64, 40, 0, 7); g.fill();
  g.fillStyle = "#fff"; g.font = "bold 46px Georgia, serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("i", 64, 68);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.setScalar(0.34); s.renderOrder = 10; return s;
}

export function createHabitat(container, hab, { onHover, onSelect } = {}) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
  catch { container.textContent = "This view needs WebGL, which this browser does not support."; return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.style.display = "block"; container.prepend(renderer.domElement);

  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x07090e);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;   // soft studio reflections for PBR materials
  scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 0.6));
  const sun = new THREE.DirectionalLight(0xfff4e6, 2.2); sun.position.set(4, 9, 3); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -7, right: 7, top: 7, bottom: -7, near: 1, far: 25 }); sun.shadow.bias = -0.0005;
  scene.add(sun);
  const L = LAYOUTS[hab];
  const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 400); camera.position.set(...L.cam);
  const sp = []; for (let i = 0; i < 2500; i++) { const r = 150 + Math.random() * 100, a = Math.random() * 6.283, b = Math.acos(2 * Math.random() - 1);
    sp.push(r * Math.sin(b) * Math.cos(a), Math.abs(r * Math.cos(b)) * (hab === "moon" ? 1 : Math.sign(Math.random() - 0.3)), r * Math.sin(b) * Math.sin(a)); }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.Float32BufferAttribute(sp, 3));
  scene.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xffffff, size: 0.6, sizeAttenuation: true })));

  // ---------- room shell ----------
  const std = (o) => new THREE.MeshStandardMaterial({ roughness: 0.75, metalness: 0.05, ...o });
  const markers = [], pickables = [];
  const addMarker = (id, pos) => {
    const m = marker(ITEMS[id].cat); m.position.copy(pos); m.userData.item = id; scene.add(m); markers.push(m); return m;
  };
  if (hab === "moon") {
    const R = 5, H = 2.9;
    const floor = new THREE.Mesh(new THREE.CircleGeometry(R, 72), std({ map: loadTex("../img/tex/floor.jpg", [3, 3]), metalness: 0.4, roughness: 0.6 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    const wall = new THREE.Mesh(new THREE.CylinderGeometry(R, R, H, 96, 1, true), std({ map: loadTex("../img/tex/moon_wall.jpg", [7, 1.4]), side: THREE.BackSide }));
    wall.position.y = H / 2; wall.receiveShadow = true; scene.add(wall);   // BackSide: the near wall disappears (dollhouse)
    const rim = new THREE.Mesh(new THREE.TorusGeometry(R, 0.06, 10, 120), std({ color: 0x9aa3ad, metalness: 0.7, roughness: 0.3 }));
    rim.rotation.x = Math.PI / 2; rim.position.y = H; scene.add(rim);
    const lamp = new THREE.PointLight(0xfff3dd, 18, 12); lamp.position.set(0, H - 0.2, 0); scene.add(lamp);
    // smoke detector on top of the life-support rack (in the airflow path), cable run on the floor along the wall
    const det = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 24), std({ color: 0xf2f2f2 })); det.position.set(-0.4, 2.05, 3.95); scene.add(det);
    addMarker("detector", new THREE.Vector3(-0.4, 2.7, 3.7)); pickables.push([det, "detector"]);
    const cab = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.2, 12), std({ color: 0xdedede, roughness: 0.5 }));
    cab.rotation.z = Math.PI / 2; cab.rotation.y = -0.35; cab.position.set(0.55, 0.07, 4.1); scene.add(cab);
    addMarker("cables", new THREE.Vector3(0.55, 0.45, 4.1)); pickables.push([cab, "cables"]);
    // outside: lunar ground, stars, Earth in the black sky
    const tl = new THREE.TextureLoader();
    const ground = new THREE.Mesh(new THREE.CircleGeometry(60, 64), std({ color: 0x8a8a8a, roughness: 1 }));
    tl.load("https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/moon_1024.jpg", t => {
      t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(10, 10); ground.material.map = t; ground.material.needsUpdate = true; });
    ground.rotation.x = -Math.PI / 2; ground.position.y = -0.02; ground.receiveShadow = true; scene.add(ground);
    const earth = new THREE.Mesh(new THREE.SphereGeometry(3, 48, 32), new THREE.MeshBasicMaterial({ color: 0x2f6fd1 }));
    tl.load("https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/earth_atmos_2048.jpg", t => { t.colorSpace = THREE.SRGBColorSpace; earth.material.map = t; earth.material.color.set(0xffffff); earth.material.needsUpdate = true; });
    earth.position.set(-30, 22, -45); scene.add(earth);
  } else {
    const Lx = 10, W = 2.2;
    const wallTex = loadTex("../img/tex/iss_wall.jpg", [4, 1]);
    const panel = (pos, rot, map) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(Lx, W), std({ map, metalness: 0.2 }));
      m.position.set(...pos); m.rotation.set(...rot); m.receiveShadow = true; scene.add(m); return m; };
    // FrontSide planes facing inward: the walls nearest the camera are culled, so you look inside
    panel([0, 0, -W / 2], [0, 0, 0], wallTex); panel([0, 0, W / 2], [0, Math.PI, 0], wallTex);
    panel([0, -W / 2, 0], [-Math.PI / 2, 0, 0], loadTex("../img/tex/floor.jpg", [4, 1])); panel([0, W / 2, 0], [Math.PI / 2, 0, 0], wallTex);
    for (const x of [-Lx / 2, Lx / 2]) {
      const end = new THREE.Mesh(new THREE.PlaneGeometry(W, W), std({ color: 0xc4c9cf, metalness: 0.3 }));
      end.position.x = x; end.rotation.y = x < 0 ? Math.PI / 2 : -Math.PI / 2; scene.add(end);
      const hatch = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.06, 12, 40), std({ color: 0x8b9198, metalness: 0.6 }));
      hatch.position.x = x + (x < 0 ? 0.02 : -0.02); hatch.rotation.y = Math.PI / 2; scene.add(hatch);
    }
    for (const z of [-0.6, 0.6]) { const s = new THREE.Mesh(new THREE.BoxGeometry(Lx * 0.85, 0.02, 0.14), new THREE.MeshBasicMaterial({ color: 0xf4f8ff }));
      s.position.set(0, W / 2 - 0.02, z); scene.add(s); }
    const lamp = new THREE.PointLight(0xf4f8ff, 14, 10); lamp.position.set(0, 0.8, 0); scene.add(lamp);
    sun.position.set(2, 8, 6);
    const earthBelow = new THREE.Mesh(new THREE.SphereGeometry(60, 96, 64), new THREE.MeshStandardMaterial({ color: 0x2f6fd1, roughness: 0.9 }));
    new THREE.TextureLoader().load("https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/earth_atmos_2048.jpg", t => {
      t.colorSpace = THREE.SRGBColorSpace; earthBelow.material.map = t; earthBelow.material.color.set(0xffffff); earthBelow.material.needsUpdate = true; });
    earthBelow.position.set(0, -75, -20); earthBelow.rotation.z = 0.4; scene.add(earthBelow);   // Earth ~400 km below (not to scale)
    const det = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.04, 20), std({ color: 0xf2f2f2 })); det.position.set(-1.8, W / 2 - 0.03, 0.3); scene.add(det);
    addMarker("detector", new THREE.Vector3(-1.8, W / 2 + 0.2, 0.3)); pickables.push([det, "detector"]);
    const fp = new THREE.Mesh(new THREE.CircleGeometry(0.06, 20), std({ color: 0xd23b2b })); fp.position.set(-2.0, 0.15, -W / 2 + 0.02); scene.add(fp);
    addMarker("fireport", new THREE.Vector3(-2.0, 0.45, -W / 2 + 0.3)); pickables.push([fp, "fireport"]);
    for (const [y, z] of [[W / 2 - 0.08, W / 2 - 0.08], [-W / 2 + 0.08, -W / 2 + 0.08]]) {
      const cab = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, Lx * 0.9, 12), std({ color: 0xdedede })); cab.rotation.z = Math.PI / 2; cab.position.set(0, y, z); scene.add(cab);
      if (y > 0) { addMarker("cables", new THREE.Vector3(2.4, y + 0.18, z)); pickables.push([cab, "cables"]); }
    }
  }

  // ---------- furniture (generated GLB models) ----------
  const gltf = new GLTFLoader();
  for (const [id, x, y, z, rot] of L.items) {
    const it = ITEMS[id];
    gltf.load(`../models/${it.model}.glb`, g => {
      const m = g.scene;
      m.traverse(o => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } });
      const s0 = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
      m.scale.setScalar(it.h / s0.y);
      m.rotation.y = rot === "center" ? Math.atan2(-x, -z) - Math.PI / 2 : rot;   // models face +x: turn them towards the room
      const b = new THREE.Box3().setFromObject(m), c = b.getCenter(new THREE.Vector3());
      m.position.set(x - c.x, y - b.min.y, z - c.z);
      scene.add(m); pickables.push([m, id]);
      const top = new THREE.Box3().setFromObject(m);
      addMarker(id, new THREE.Vector3(x, top.max.y + 0.28, z));
    }, undefined, () => console.warn("model missing:", it.model));
  }

  // ---------- controls, hover, click ----------
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(...L.target); controls.enableDamping = true;
  controls.minDistance = 2.5; controls.maxDistance = hab === "moon" ? 16 : 13; controls.maxPolarAngle = hab === "moon" ? 1.35 : Math.PI;
  controls.autoRotate = true; controls.autoRotateSpeed = 0.35;
  renderer.domElement.addEventListener("pointerdown", () => { controls.autoRotate = false; });

  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const hit = e => {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const mh = ray.intersectObjects(markers, false)[0]; if (mh) return mh.object.userData.item;
    for (const h of ray.intersectObjects(pickables.map(p => p[0]), true)) {
      let o = h.object; while (o && !pickables.some(p => p[0] === o)) o = o.parent;
      const p = pickables.find(q => q[0] === o); if (p) return p[1];
    }
    return null;
  };
  let hovered = null, down = null;
  renderer.domElement.addEventListener("pointermove", e => {
    const id = hit(e); renderer.domElement.style.cursor = id ? "pointer" : "grab";
    if (id !== hovered) { markers.forEach(m => m.scale.setScalar(m.userData.item === id ? 0.46 : 0.34)); hovered = id; }
    onHover?.(id ? { id, ...ITEMS[id] } : null, e);
  });
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const id = hit(e); if (id) { focus(id); onSelect?.({ id, ...ITEMS[id] }); }
  });

  let fly = null;
  function focus(id) {
    const mk = markers.find(m => m.userData.item === id); if (!mk) return;
    const to = mk.position.clone().setY(Math.max(0.4, mk.position.y - 0.6));
    const dir = camera.position.clone().sub(controls.target).normalize();
    fly = { t0: performance.now(), fT: controls.target.clone(), tT: to, fP: camera.position.clone(), tP: to.clone().add(dir.multiplyScalar(hab === "moon" ? 4.2 : 3.2)) };
    controls.autoRotate = false;
  }
  const resize = () => { const w = container.clientWidth, h = container.clientHeight; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); };
  new ResizeObserver(resize).observe(container); resize();
  renderer.setAnimationLoop(() => {
    if (fly) {
      const k = Math.min(1, (performance.now() - fly.t0) / 900), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      controls.target.lerpVectors(fly.fT, fly.tT, e); camera.position.lerpVectors(fly.fP, fly.tP, e); if (k === 1) fly = null;
    }
    controls.update(); renderer.render(scene, camera);
  });
  return { focus, items: ITEMS, reset() { fly = { t0: performance.now(), fT: controls.target.clone(), tT: new THREE.Vector3(...L.target), fP: camera.position.clone(), tP: new THREE.Vector3(...L.cam) }; } };
}
