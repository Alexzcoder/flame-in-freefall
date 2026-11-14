// 3D view of the habitats (Three.js). Purely visual: colours come from the confidence logic in app.js.
// Each habitat is a module; each material in it is a small cube coloured green / yellow / red.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const COLORS = { green: 0x2ea043, yellow: 0xd29922, red: 0xe5534b };
const MATERIAL_NAMES = { pmma: "PMMA", sibal: "Sibal", cotton: "Cotton" };
const niceName = m => MATERIAL_NAMES[m] ?? m.charAt(0).toUpperCase() + m.slice(1);
const SPACING = 8;

function makeLabel(text, scale = 1) {
  const canvas = document.createElement("canvas");
  canvas.width = 512; canvas.height = 128;
  const ctx = canvas.getContext("2d");
  ctx.font = "bold 56px system-ui, sans-serif";
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(text, 256, 64);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false }));
  sprite.scale.set(4 * scale, 1 * scale, 1);
  return sprite;
}

function metal(color) {
  return new THREE.MeshStandardMaterial({ color, metalness: 0.6, roughness: 0.4 });
}

// ISS-style module: hull, long truss and two solar panels, floating in space.
function buildOrbitalModule() {
  const g = new THREE.Group();
  const hull = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, 3.2, 32), metal(0xcfd4da));
  hull.rotation.z = Math.PI / 2;
  g.add(hull);
  for (const s of [-1, 1]) {
    const cap = new THREE.Mesh(new THREE.SphereGeometry(0.7, 24, 16), metal(0xb8bec6));
    cap.position.x = s * 1.6;
    g.add(cap);
  }
  const truss = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 6.4), metal(0x9aa1a9));
  g.add(truss);
  for (const s of [-1, 1]) {
    const panel = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 0.04, 1.5),
      new THREE.MeshStandardMaterial({ color: 0x1e3a8a, emissive: 0x0b1b4a, metalness: 0.3, roughness: 0.5 }));
    panel.position.z = s * 2.6;
    g.add(panel);
  }
  return { group: g, beadY: 1.25, beadSpan: 2.4, labelY: 2.6 };
}

// Moon base: translucent dome on a grey lunar patch.
function buildMoonBase() {
  const g = new THREE.Group();
  const ground = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 3.4, 0.2, 48),
    new THREE.MeshStandardMaterial({ color: 0x8a8d93, roughness: 1 }));
  ground.position.y = -0.7;
  g.add(ground);
  for (const [x, z, r] of [[-2, 1.4, 0.5], [2.2, -1.1, 0.35], [1.1, 2.2, 0.25]]) {
    const crater = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.02, 24), new THREE.MeshStandardMaterial({ color: 0x6b6e74, roughness: 1 }));
    crater.position.set(x, -0.59, z);
    g.add(crater);
  }
  const dome = new THREE.Mesh(new THREE.SphereGeometry(1.9, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: 0xdfe6ee, transparent: true, opacity: 0.35, side: THREE.DoubleSide, metalness: 0.2, roughness: 0.2 }));
  dome.position.y = -0.6;
  g.add(dome);
  return { group: g, beadY: -0.2, beadSpan: 1.8, labelY: 2.2 };
}

function buildGeneric() {
  const g = new THREE.Group();
  const capsule = new THREE.Mesh(new THREE.CapsuleGeometry(0.7, 2, 8, 24), metal(0xcfd4da));
  capsule.rotation.z = Math.PI / 2;
  g.add(capsule);
  return { group: g, beadY: 1.25, beadSpan: 2.2, labelY: 2.4 };
}

export function createStation3D(container, habitats) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch (e) {
    container.textContent = "The 3D view needs WebGL, which this browser does not support.";
    return null;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.append(renderer.domElement);
  renderer.domElement.style.display = "block";

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05070d);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 400);
  camera.position.set(0, 5, 15);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(6, 9, 7);
  scene.add(sun);

  // stars
  const starPos = [];
  for (let i = 0; i < 900; i++) {
    const r = 60 + Math.random() * 60, a = Math.random() * Math.PI * 2, b = Math.acos(2 * Math.random() - 1);
    starPos.push(r * Math.sin(b) * Math.cos(a), r * Math.sin(b) * Math.sin(a), r * Math.cos(b));
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.Float32BufferAttribute(starPos, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.35, sizeAttenuation: true })));

  // habitats
  const beads = [];   // beads[i][j] = cube for material j of habitat i
  habitats.forEach((h, i) => {
    const built = h.id === "iss" ? buildOrbitalModule() : h.id === "moon" ? buildMoonBase() : buildGeneric();
    built.group.position.x = (i - (habitats.length - 1) / 2) * SPACING;
    const title = makeLabel(h.name, 1.4);
    title.position.set(0, built.labelY, 0);
    built.group.add(title);

    beads[i] = h.materials.map((m, j) => {
      const n = h.materials.length;
      const x = n === 1 ? 0 : (j / (n - 1) - 0.5) * built.beadSpan;
      const cube = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.42, 0.42),
        new THREE.MeshStandardMaterial({ color: 0x555555, emissive: 0x333333, emissiveIntensity: 0.8 }));
      cube.position.set(x, built.beadY, 0);
      built.group.add(cube);
      const label = makeLabel(niceName(m), 0.55);
      label.position.set(x, built.beadY + 0.55, 0);
      built.group.add(label);
      return cube;
    });
    scene.add(built.group);
  });

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;
  controls.minDistance = 6;
  controls.maxDistance = 40;
  controls.target.set(0, 0.5, 0);

  const resize = () => {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(container);
  resize();

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
  });

  return {
    // levels[i][j] = "green" | "yellow" | "red" for material j of habitat i
    update(levels) {
      levels.forEach((row, i) => row.forEach((level, j) => {
        const cube = beads[i]?.[j];
        if (!cube) return;
        cube.material.color.setHex(COLORS[level]);
        cube.material.emissive.setHex(COLORS[level]);
        cube.material.emissiveIntensity = 0.6;
      }));
    },
  };
}
