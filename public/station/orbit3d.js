// Orbit view: Earth, the ISS on its orbit, the Moon with a Moon base. Click a habitat to fly to it.
// Not to scale (distances and sizes are compressed so everything fits on screen).
// Reuses the habitat models from station3d.js. Beacon colours come from the confidence logic in app.js.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { buildOrbitalModule, buildMoonBase, makeLabel } from "./station3d.js";

const TEX = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/";
const COLORS = { green: 0x3ecf8e, yellow: 0xf6c945, red: 0xff5c8a, none: 0x8a93a6 };
const DEG = Math.PI / 180;
const EARTH_R = 5, ISS_R = 7.2, MOON_R = 1.4, MOON_ORBIT = 26;

function texture(loader, file, apply) {
  loader.load(TEX + file, t => { t.colorSpace = THREE.SRGBColorSpace; apply(t); }, undefined,
    () => console.warn("texture not loaded, using plain colour:", file));  // offline: keep the plain material
}

function beacon(color) {
  const g = new THREE.Group();
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 12), new THREE.MeshBasicMaterial({ color }));
  const halo = new THREE.Mesh(new THREE.SphereGeometry(0.5, 20, 14),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25, depthWrite: false }));
  g.add(core, halo);
  return { group: g, core, halo };
}

function orbitLine(radius, color, opacity) {
  const pts = [];
  for (let i = 0; i <= 256; i++) { const a = (i / 256) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius)); }
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
}

export function createOrbit3D(container, { onSelect } = {}) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
  catch { container.textContent = "The 3D view needs WebGL, which this browser does not support."; return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.domElement.style.display = "block";
  container.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x03050a);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 600);
  const HOME = { pos: new THREE.Vector3(0, 16, 42), target: new THREE.Vector3(6, 0, 0) };
  camera.position.copy(HOME.pos);

  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(50, 12, 30);
  scene.add(sun);

  // stars
  const sp = [];
  for (let i = 0; i < 2500; i++) {
    const r = 180 + Math.random() * 200, a = Math.random() * Math.PI * 2, b = Math.acos(2 * Math.random() - 1);
    sp.push(r * Math.sin(b) * Math.cos(a), r * Math.sin(b) * Math.sin(a), r * Math.cos(b));
  }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.Float32BufferAttribute(sp, 3));
  scene.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xffffff, size: 0.7, sizeAttenuation: true })));

  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin("anonymous");

  // Earth (tilted 23.4°), clouds and a thin atmosphere glow
  const earthTilt = new THREE.Group(); earthTilt.rotation.z = 23.4 * DEG; scene.add(earthTilt);
  const earth = new THREE.Mesh(new THREE.SphereGeometry(EARTH_R, 96, 64),
    new THREE.MeshPhongMaterial({ color: 0x2a6bd1, specular: 0x222222, shininess: 14 }));
  texture(loader, "earth_atmos_2048.jpg", t => { earth.material.map = t; earth.material.color.set(0xffffff); earth.material.needsUpdate = true; });
  earthTilt.add(earth);
  const clouds = new THREE.Mesh(new THREE.SphereGeometry(EARTH_R * 1.012, 64, 48),
    new THREE.MeshLambertMaterial({ transparent: true, opacity: 0.0, depthWrite: false }));
  texture(loader, "earth_clouds_1024.png", t => { clouds.material.map = t; clouds.material.opacity = 0.75; clouds.material.needsUpdate = true; });
  earthTilt.add(clouds);
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(EARTH_R * 1.07, 64, 48),
    new THREE.MeshBasicMaterial({ color: 0x5aa9ff, transparent: true, opacity: 0.13, side: THREE.BackSide, depthWrite: false })));
  const earthLabel = makeLabel("Earth", 2.2); earthLabel.position.set(0, EARTH_R + 1.6, 0); scene.add(earthLabel);

  // ISS: inclined orbit (51.6°), much closer than real scale
  const issPlane = new THREE.Group(); issPlane.rotation.x = 51.6 * DEG; scene.add(issPlane);
  issPlane.add(orbitLine(ISS_R, 0x9fb8ff, 0.35));
  const issPivot = new THREE.Group(); issPlane.add(issPivot);
  const issHolder = new THREE.Group(); issHolder.position.x = ISS_R; issPivot.add(issHolder);
  const iss = buildOrbitalModule().group; iss.scale.setScalar(0.3); issHolder.add(iss);
  const issBeacon = beacon(COLORS.none); issBeacon.group.position.y = 0.65; issHolder.add(issBeacon.group);
  const issLabel = makeLabel("ISS", 1.9); issLabel.position.y = 1.7; issHolder.add(issLabel);

  // Moon with a Moon base dome on the side facing Earth
  scene.add(orbitLine(MOON_ORBIT, 0xffffff, 0.18));
  const moonPivot = new THREE.Group(); scene.add(moonPivot);
  const moonHolder = new THREE.Group(); moonHolder.position.x = MOON_ORBIT; moonPivot.add(moonHolder);
  const moon = new THREE.Mesh(new THREE.SphereGeometry(MOON_R, 64, 48), new THREE.MeshPhongMaterial({ color: 0x9a9a9a, shininess: 2 }));
  texture(loader, "moon_1024.jpg", t => { moon.material.map = t; moon.material.color.set(0xffffff); moon.material.needsUpdate = true; });
  moonHolder.add(moon);
  const base = buildMoonBase().group; base.scale.setScalar(0.16);
  base.position.set(0, MOON_R + 0.02, 0);
  const baseMount = new THREE.Group(); baseMount.rotation.z = 35 * DEG; baseMount.add(base); moonHolder.add(baseMount);
  const moonBeacon = beacon(COLORS.none); moonBeacon.group.position.y = MOON_R + 0.7; baseMount.add(moonBeacon.group);
  const moonLabel = makeLabel("Moon base", 2.4); moonLabel.position.y = MOON_R + 2.0; moonHolder.add(moonLabel);
  const scaleNote = makeLabel("not to scale", 1.2); scaleNote.position.set(0, -EARTH_R - 1.8, 0);
  scaleNote.material.opacity = 0.5; scene.add(scaleNote);

  // focus = point the camera looks at; center = body it sits on (the camera arrives from outside, above the habitat)
  const targets = {
    iss: { focus: issHolder, center: earth, pick: [iss, issBeacon.group], dist: 2.4, label: issLabel, beacon: issBeacon },
    moon: { focus: base, center: moon, pick: [moon, base, moonBeacon.group], dist: 2.6, label: moonLabel, beacon: moonBeacon },
  };

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 1.5; controls.maxDistance = 120;
  controls.target.copy(HOME.target);

  // ---- picking: click (not drag) on a habitat flies there ----
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const hit = ev => {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    for (const [id, t] of Object.entries(targets)) if (ray.intersectObjects(t.pick, true).length) return id;
    return null;
  };
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const id = hit(e); if (id) { focus(id); onSelect?.(id); }
  });
  renderer.domElement.addEventListener("pointermove", e => { renderer.domElement.style.cursor = hit(e) ? "pointer" : "grab"; });

  // ---- camera flights ----
  let focused = null, flight = null, timeScale = 1;
  const wp = new THREE.Vector3();
  function fly(toPos, toTarget, ms = 1400) {
    flight = { t0: performance.now(), ms, fromPos: camera.position.clone(), fromTarget: controls.target.clone(), toPos, toTarget };
  }
  const cp = new THREE.Vector3();
  function focus(id) {
    const t = targets[id];
    focused = id; timeScale = 0.08;   // slow the orbits so the habitat stays in view
    for (const [k, o] of Object.entries(targets)) {   // close up: hide this habitat's label, shrink its beacon
      o.label.visible = k !== id; o.beacon.group.scale.setScalar(k === id ? 0.2 : 1);
    }
    t.focus.getWorldPosition(wp); t.center.getWorldPosition(cp);
    const out = wp.clone().sub(cp).normalize();                       // "up" from the body's surface
    const side = new THREE.Vector3().crossVectors(out, new THREE.Vector3(0, 1, 0)).normalize();
    if (!isFinite(side.x)) side.set(1, 0, 0);
    const pos = wp.clone().add(out.multiplyScalar(t.dist)).add(side.multiplyScalar(t.dist * 0.6));  // 3/4 view from above
    fly(pos, wp.clone());
  }
  function overview() {
    focused = null; timeScale = 1;
    for (const o of Object.values(targets)) { o.label.visible = true; o.beacon.group.scale.setScalar(1); }
    fly(HOME.pos.clone(), HOME.target.clone());
  }

  const resize = () => {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(container); resize();

  let last = performance.now();
  renderer.setAnimationLoop(() => {
    const now = performance.now();   // same clock as fly(); the rAF timestamp can differ from it
    const dt = Math.min(0.05, (now - last) / 1000) * timeScale; last = now;
    earth.rotation.y += dt * 0.25; clouds.rotation.y += dt * 0.29;
    issPivot.rotation.y += dt * 0.9;          // ~one lap every 7 s at full speed
    moonPivot.rotation.y += dt * 0.06;
    moonHolder.rotation.y = -moonPivot.rotation.y + Math.PI;  // keep the base facing Earth (tidally locked)
    iss.rotation.y += dt * 0.3;
    const pulse = 1 + 0.25 * Math.sin(now / 350);
    issBeacon.halo.scale.setScalar(pulse); moonBeacon.halo.scale.setScalar(pulse);

    if (flight) {
      const k = Math.min(1, (now - flight.t0) / flight.ms), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      if (focused) { targets[focused].focus.getWorldPosition(wp); flight.toPos.add(wp.clone().sub(flight.toTarget)); flight.toTarget.copy(wp); }
      camera.position.lerpVectors(flight.fromPos, flight.toPos, e);
      controls.target.lerpVectors(flight.fromTarget, flight.toTarget, e);
      if (k === 1) flight = null;
    } else if (focused) {                      // follow the moving habitat
      targets[focused].focus.getWorldPosition(wp);
      const delta = wp.clone().sub(controls.target);
      controls.target.add(delta); camera.position.add(delta);
    }
    controls.update();
    renderer.render(scene, camera);
  });

  return {
    focus, overview,
    // level per habitat: "green" | "yellow" | "red"
    update(levels) {
      for (const [id, b] of [["iss", issBeacon], ["moon", moonBeacon]]) {
        const c = COLORS[levels[id]] ?? COLORS.none;
        b.core.material.color.setHex(c); b.halo.material.color.setHex(c);
      }
    },
  };
}
