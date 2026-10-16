/* ===================================================================
   PHAN VE 3D (three.js): khung canh, xe buyt, nguoi di bo co khop va dang di.
   Quy uoc: diem 2D (x, z) cua mo phong -> three (x, 0, -z). Xe nhin ve -z.
   =================================================================== */
'use strict';

const W3 = (x, z, y = 0) => new THREE.Vector3(x, y, -z);

function canvasTex(w, h, draw, repeat) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); }
  return t;
}

function makeTextures(rand) {
  const asphalt = canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = '#3b3f45'; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 4000; i++) { const v = 45 + rand() * 40; g.fillStyle = `rgb(${v},${v + 2},${v + 6})`; g.fillRect(rand() * w, rand() * h, 1.5, 1.5); }
  }, [1, 1]);
  const tiles = canvasTex(128, 128, (g, w, h) => {
    g.fillStyle = '#a9a39a'; g.fillRect(0, 0, w, h);
    g.strokeStyle = '#8f8981'; g.lineWidth = 2;
    for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 32, 0); g.lineTo(i * 32, h); g.stroke(); g.beginPath(); g.moveTo(0, i * 32); g.lineTo(w, i * 32); g.stroke(); }
    for (let i = 0; i < 600; i++) { g.fillStyle = `rgba(0,0,0,${rand() * 0.08})`; g.fillRect(rand() * w, rand() * h, 2, 2); }
  }, [1, 1]);
  const facade = [0, 1, 2, 3].map(k => canvasTex(128, 256, (g, w, h) => {
    const base = ['#d9cbb4', '#b9c3cc', '#e6e0d6', '#c9b29a'][k];
    g.fillStyle = base; g.fillRect(0, 0, w, h);
    for (let y = 14; y < h - 10; y += 30) for (let x = 10; x < w - 10; x += 28) {
      g.fillStyle = rand() < 0.25 ? '#e9d9a8' : '#3c4e63'; g.fillRect(x, y, 18, 20);
      g.fillStyle = 'rgba(255,255,255,0.25)'; g.fillRect(x, y, 18, 3);
    }
  }, [1, 1]));
  return { asphalt, tiles, facade };
}

/* ---------------- Nguoi 3D ---------------- */
const SKIN = [0xf1c7a5, 0xd9a47e, 0xb67a55, 0x8d5a3b];
const SHIRT = [0x2f6db5, 0xc0392b, 0x2e8b57, 0xe0a526, 0x6c4fa3, 0xf2f2f2, 0x1f2a36, 0xd35400, 0x16a085];
const PANTS = [0x1c2633, 0x3b4a5a, 0x2b2b2b, 0x6b5a45, 0x24456b];
const HAIR = [0x1a1410, 0x3a2a1a, 0x5a3b22, 0x101010];

function mat(c, r = 0.85) { return new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: 0 }); }

function limb(len, rad, m) {
  const g = new THREE.CapsuleGeometry(rad, Math.max(0.01, len - 2 * rad), 4, 10);
  g.translate(0, -len / 2, 0);
  const mesh = new THREE.Mesh(g, m); mesh.castShadow = true; return mesh;
}

function makeHuman(h, seed) {
  const r = mulberry32(seed);
  const pick = a => a[Math.floor(r() * a.length)];
  const child = h < 1.35;
  const skin = mat(pick(SKIN), 0.7), shirt = mat(pick(SHIRT)), pants = mat(pick(PANTS)), hairM = mat(pick(HAIR), 0.95);
  const shoe = mat(r() < 0.5 ? 0x222222 : 0xe8e8e8, 0.6);
  const s = h / 1.75;                                   // ti le theo nguoi 1,75 m
  const root = new THREE.Group();
  const body = new THREE.Group(); root.add(body);
  const hipY = 0.92 * s, legR = 0.065 * s;
  // hong + chan
  const hips = new THREE.Mesh(new THREE.CapsuleGeometry(0.13 * s, 0.12 * s, 4, 10), pants);
  hips.rotation.z = Math.PI / 2; hips.position.y = hipY; hips.castShadow = true; body.add(hips);
  const legs = [];
  for (const sd of [-1, 1]) {
    const hip = new THREE.Group(); hip.position.set(sd * 0.095 * s, hipY, 0); body.add(hip);
    hip.add(limb(0.46 * s, legR * 1.15, pants));
    const knee = new THREE.Group(); knee.position.y = -0.46 * s; hip.add(knee);
    knee.add(limb(0.44 * s, legR, pants));
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.1 * s, 0.07 * s, 0.25 * s), shoe);
    foot.position.set(0, -0.44 * s - 0.01, -0.05 * s); foot.castShadow = true; knee.add(foot);
    legs.push({ hip, knee });
  }
  // than
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.17 * s, 0.34 * s, 6, 14), shirt);
  torso.scale.set(1, 1, 0.62); torso.position.y = hipY + 0.31 * s; torso.castShadow = true; body.add(torso);
  if (!child && r() < 0.35) {          // ba lo
    const bag = new THREE.Mesh(new THREE.BoxGeometry(0.28 * s, 0.36 * s, 0.14 * s), mat(pick([0x34495e, 0x7f8c8d, 0x8e2c2c])));
    bag.position.set(0, hipY + 0.34 * s, 0.17 * s); bag.castShadow = true; body.add(bag);
  }
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * s, 0.055 * s, 0.08 * s, 10), skin);
  neck.position.y = hipY + 0.6 * s; body.add(neck);
  const headR = (child ? 0.125 : 0.108) * s * (child ? 1.12 : 1);
  const head = new THREE.Mesh(new THREE.SphereGeometry(headR, 20, 16), skin);
  head.scale.set(0.9, 1.08, 0.98); head.position.y = hipY + 0.6 * s + 0.04 * s + headR; head.castShadow = true; body.add(head);
  const hair = new THREE.Mesh(new THREE.SphereGeometry(headR * 1.04, 20, 12, 0, Math.PI * 2, 0, Math.PI * (r() < 0.5 ? 0.55 : 0.68)), hairM);
  hair.scale.copy(head.scale); hair.position.copy(head.position); hair.position.z += 0.01 * s; hair.rotation.x = 0.25; body.add(hair);
  // tay
  const arms = [];
  const shY = hipY + 0.52 * s;
  for (const sd of [-1, 1]) {
    const sh = new THREE.Group(); sh.position.set(sd * 0.21 * s, shY, 0); sh.rotation.z = sd * 0.08; body.add(sh);
    sh.add(limb(0.3 * s, 0.052 * s, shirt));
    const el = new THREE.Group(); el.position.y = -0.3 * s; sh.add(el);
    el.add(limb(0.27 * s, 0.043 * s, skin));
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.045 * s, 10, 8), skin); hand.position.y = -0.29 * s; el.add(hand);
    arms.push({ sh, el });
  }
  root.userData = { legs, arms, body, phase: r() * 6.28, s, idle: r() * 6.28 };
  return root;
}

function animateHuman(o, speed, dt, t) {
  const u = o.userData;
  if (speed > 0.05) {
    const stride = 1.35 * u.s;
    u.phase += dt * speed / stride * Math.PI * 2 / 2;
    const run = speed > 2.2, A = run ? 0.75 : 0.45;
    u.legs.forEach((L, i) => {
      const p = u.phase + i * Math.PI;
      L.hip.rotation.x = Math.sin(p) * A;
      L.knee.rotation.x = Math.max(0, -Math.cos(p)) * (run ? 1.3 : 0.75);
    });
    u.arms.forEach((A2, i) => {
      const p = u.phase + i * Math.PI;
      A2.sh.rotation.x = -Math.sin(p) * A * 0.9;
      A2.el.rotation.x = -(run ? 1.2 : 0.35);
    });
    u.body.position.y = Math.abs(Math.sin(u.phase)) * 0.035 * u.s;
    u.body.rotation.x = run ? -0.18 : -0.03;
  } else {
    u.legs.forEach(L => { L.hip.rotation.x *= 0.85; L.knee.rotation.x *= 0.85; });
    u.arms.forEach(A2 => { A2.sh.rotation.x = Math.sin(t * 1.3 + u.idle) * 0.04; A2.el.rotation.x = -0.1; });
    u.body.position.y = 0; u.body.rotation.x = 0;
    u.body.rotation.y = Math.sin(t * 0.5 + u.idle) * 0.06;
  }
}

/* ---------------- Xe ---------------- */
function makeBus() {
  const g = new THREE.Group();
  const L = 11.5, Wd = 2.55, H = 3.1;
  const white = mat(0xf4f6f7, 0.4), teal = mat(0x16a394, 0.45), dark = mat(0x18222c, 0.3);
  const glass = new THREE.MeshStandardMaterial({ color: 0x1d2b38, roughness: 0.15, metalness: 0.3 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(Wd, H - 0.35, L), white);
  body.position.set(0, 0.35 + (H - 0.35) / 2, L / 2); body.castShadow = true; body.receiveShadow = true; g.add(body);
  const skirt = new THREE.Mesh(new THREE.BoxGeometry(Wd + 0.02, 0.5, L + 0.02), teal);
  skirt.position.set(0, 0.6, L / 2); g.add(skirt);
  const band = new THREE.Mesh(new THREE.BoxGeometry(Wd + 0.03, 1.15, L - 1.2), glass);
  band.position.set(0, 2.05, L / 2 + 0.4); g.add(band);
  const ws = new THREE.Mesh(new THREE.BoxGeometry(Wd - 0.15, 1.7, 0.05), glass);
  ws.position.set(0, 1.95, -0.01); g.add(ws);
  const roof = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.3, 3.2), white);
  roof.position.set(0, H + 0.15, 4); roof.castShadow = true; g.add(roof);
  const stripe = new THREE.Mesh(new THREE.BoxGeometry(Wd + 0.035, 0.12, L - 1.2), teal);
  stripe.position.set(0, 1.42, L / 2 + 0.4); g.add(stripe);
  for (const sd of [-1, 1]) {
    const hl = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.16, 0.05), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xfff2c8, emissiveIntensity: 0.8 }));
    hl.position.set(sd * 0.85, 0.75, -0.03); g.add(hl);
    for (const zz of [2.0, 8.9]) {
      const wh = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.32, 20), dark);
      wh.rotation.z = Math.PI / 2; wh.position.set(sd * (Wd / 2 - 0.12), 0.5, zz); wh.castShadow = true; g.add(wh);
    }
  }
  const label = canvasTex(512, 96, (c, w, h) => {
    c.fillStyle = '#f4f6f7'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#16a394'; c.font = 'bold 64px Arial'; c.fillText('VinBus', 20, 72);
    c.fillStyle = '#1d2b38'; c.font = '28px Arial'; c.fillText('E-bus 01', 330, 70);
  });
  for (const sd of [-1, 1]) {
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(4, 0.75), new THREE.MeshStandardMaterial({ map: label, roughness: 0.5 }));
    pl.position.set(sd * (Wd / 2 + 0.02), 0.98, 5); pl.rotation.y = sd * Math.PI / 2; g.add(pl);
  }
  const topLabel = canvasTex(256, 512, (c, w, h) => {
    c.fillStyle = '#f4f6f7'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#16a394'; c.fillRect(0, 0, w, 40);
    c.save(); c.translate(w / 2, h / 2); c.rotate(-Math.PI / 2); c.fillStyle = '#16a394'; c.font = 'bold 90px Arial'; c.textAlign = 'center'; c.fillText('VinBus', 0, 30); c.restore();
  });
  const rp = new THREE.Mesh(new THREE.PlaneGeometry(Wd - 0.05, L - 0.1), new THREE.MeshStandardMaterial({ map: topLabel, roughness: 0.6 }));
  rp.rotation.x = -Math.PI / 2; rp.position.set(0, H + 0.005, L / 2); g.add(rp);
  return g;
}

function makeCar(o) {
  const g = new THREE.Group();
  const paint = new THREE.MeshStandardMaterial({ color: o.color, roughness: 0.35, metalness: 0.4 });
  const glass = new THREE.MeshStandardMaterial({ color: 0x1b2631, roughness: 0.1, metalness: 0.5 });
  const van = o.h > 1.8;
  const low = new THREE.Mesh(new THREE.BoxGeometry(o.w, van ? o.h - 0.25 : 0.75, o.l), paint);
  low.position.y = 0.25 + (van ? (o.h - 0.25) / 2 : 0.375); low.castShadow = true; g.add(low);
  if (!van) {
    const cab = new THREE.Mesh(new THREE.BoxGeometry(o.w - 0.15, 0.5, o.l * 0.55), glass);
    cab.position.set(0, 1.25, 0.1); cab.castShadow = true; g.add(cab);
    const roof = new THREE.Mesh(new THREE.BoxGeometry(o.w - 0.2, 0.05, o.l * 0.5), paint); roof.position.set(0, 1.5, 0.1); g.add(roof);
  } else {
    const ws = new THREE.Mesh(new THREE.BoxGeometry(o.w + 0.01, 0.6, o.l * 0.8), glass); ws.position.set(0, o.h - 0.55, 0.2); g.add(ws);
  }
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const wh = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.22, 16), mat(0x111111));
    wh.rotation.z = Math.PI / 2; wh.position.set(sx * (o.w / 2 - 0.05), 0.33, sz * o.l * 0.32); g.add(wh);
  }
  g.position.copy(W3(o.x, o.z));
  return g;
}

function makeTree(r) {
  const g = new THREE.Group();
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.18, 2.4, 8), mat(0x5b4331));
  trunk.position.y = 1.2; trunk.castShadow = true; g.add(trunk);
  const leafM = mat([0x3f7d3a, 0x4d8c3f, 0x356b33][Math.floor(r() * 3)], 0.9);
  for (let i = 0; i < 3; i++) {
    const s = new THREE.Mesh(new THREE.IcosahedronGeometry(1.1 + r() * 0.5, 1), leafM);
    s.position.set((r() - 0.5) * 0.9, 2.9 + i * 0.5, (r() - 0.5) * 0.9); s.castShadow = true; g.add(s);
  }
  return g;
}

function makeLamp() {
  const g = new THREE.Group(), m = mat(0x4a525b, 0.5);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.09, 6, 8), m); pole.position.y = 3; pole.castShadow = true; g.add(pole);
  const arm = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.08, 0.08), m); arm.position.set(-0.6, 5.95, 0); g.add(arm);
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.12, 0.25), mat(0xe8e2c8)); head.position.set(-1.15, 5.9, 0); g.add(head);
  return g;
}

/* ---------------- Khung canh ---------------- */
function buildWorld(scene, sim) {
  const rand = mulberry32(99);
  const T = makeTextures(rand);
  const env = sim.sc.env;
  const root = new THREE.Group(); scene.add(root);
  const add = (geo, m, x, z, y = 0, rx = -Math.PI / 2) => { const o = new THREE.Mesh(geo, m); o.position.copy(W3(x, z, y)); o.rotation.x = rx; o.receiveShadow = true; root.add(o); return o; };
  const zA = -60, zB = env === 'free' ? 1400 : 200;
  const grass = new THREE.MeshStandardMaterial({ color: 0x7d8f62, roughness: 1 });
  add(new THREE.PlaneGeometry(800, 2000), grass, 0, 600, -0.02);
  const asphaltM = n => { const t = T.asphalt.clone(); t.needsUpdate = true; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(n[0], n[1]); return new THREE.MeshStandardMaterial({ map: t, roughness: 0.95 }); };
  const tileM = n => { const t = T.tiles.clone(); t.needsUpdate = true; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(n[0], n[1]); return new THREE.MeshStandardMaterial({ map: t, roughness: 0.9 }); };
  const white = new THREE.MeshStandardMaterial({ color: 0xf2f2ee, roughness: 0.7 });
  const yellow = new THREE.MeshStandardMaterial({ color: 0xf2c230, roughness: 0.7 });
  const curbM = mat(0xc9c4bb, 0.8);
  const len = zB - zA, mid = (zA + zB) / 2;
  const cross = env === 'intersection';
  // duong chinh
  add(new THREE.PlaneGeometry(14, len), asphaltM([3, len / 4]), 0, mid, 0);
  // via he 2 ben (cat o nga tu)
  const walkSeg = (x0, x1, z0, z1) => {
    const w = x1 - x0, l = z1 - z0; if (l <= 0) return;
    const o = new THREE.Mesh(new THREE.BoxGeometry(w, 0.15, l), tileM([w / 2, l / 2]));
    o.position.copy(W3((x0 + x1) / 2, (z0 + z1) / 2, 0.075)); o.receiveShadow = true; root.add(o);
    const c = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.17, l), curbM);
    c.position.copy(W3(x0 < 0 ? x1 - 0.1 : x0 + 0.1, (z0 + z1) / 2, 0.085)); root.add(c);
  };
  for (const sd of [-1, 1]) {
    const x0 = sd > 0 ? 7 : -12, x1 = sd > 0 ? 12 : -7;
    if (cross) { walkSeg(x0, x1, zA, 33); walkSeg(x0, x1, 47, zB); } else walkSeg(x0, x1, zA, zB);
  }
  if (cross) {
    add(new THREE.PlaneGeometry(400, 14), asphaltM([100, 3]), 0, 40, 0.001);
    for (const sz of [-1, 1]) for (const sx of [-1, 1]) {
      const z0 = sz > 0 ? 47 : 28, z1 = sz > 0 ? 52 : 33;
      const xa = sx > 0 ? 12 : -200, xb = sx > 0 ? 200 : -12;
      const o = new THREE.Mesh(new THREE.BoxGeometry(xb - xa, 0.15, z1 - z0), tileM([(xb - xa) / 2, 2.5]));
      o.position.copy(W3((xa + xb) / 2, (z0 + z1) / 2, 0.075)); o.receiveShadow = true; root.add(o);
    }
    // vach di bo
    const zebra = (cx, cz, along) => { for (let i = -3; i <= 3; i++) { const o = add(new THREE.PlaneGeometry(along === 'x' ? 0.5 : 3, along === 'x' ? 3 : 0.5), white, along === 'x' ? cx + i * 1.0 : cx, along === 'x' ? cz : cz + i * 1.0, 0.012); } };
    zebra(0, 30.6, 'x'); zebra(0, 49.4, 'x'); zebra(9.6, 40, 'z'); zebra(-9.6, 40, 'z');
    zebra(12.2, 40, 'z');
    for (let x = 16; x < 200; x += 6) add(new THREE.PlaneGeometry(3, 0.15), white, x, 40, 0.012);
    for (let x = -16; x > -200; x -= 6) add(new THREE.PlaneGeometry(3, 0.15), white, x, 40, 0.012);
  }
  // vach giua (vang lien) + vach lan (trang dut)
  const skip = z => cross && z > 32 && z < 48;
  for (let z = zA; z < zB; z += 1) if (!skip(z)) add(new THREE.PlaneGeometry(0.15, 1.02), yellow, -0.12, z, 0.012), add(new THREE.PlaneGeometry(0.15, 1.02), yellow, 0.12, z, 0.012);
  for (let z = zA; z < zB; z += 9) for (const x of [-3.5, 3.5]) if (!skip(z)) add(new THREE.PlaneGeometry(0.14, 3), white, x, z, 0.012);
  if (env === 'parked') for (let z = 10; z < 70; z += 6.5) add(new THREE.PlaneGeometry(1.8, 0.12), white, 6.1, z, 0.012);
  // nha, cay, den
  const buildRow = (sd) => {
    for (let z = zA; z < zB; z += 14 + rand() * 6) {
      if (cross && z > 22 && z < 58) continue;
      const w = 9 + rand() * 6, l = 10 + rand() * 4, h = 8 + rand() * 18;
      const fm = new THREE.MeshStandardMaterial({ map: T.facade[Math.floor(rand() * 4)].clone(), roughness: 0.85 });
      fm.map.needsUpdate = true; fm.map.wrapS = fm.map.wrapT = THREE.RepeatWrapping; fm.map.repeat.set(Math.round(l / 4), Math.round(h / 6));
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, l), fm);
      b.position.copy(W3(sd * (13.5 + w / 2), z + l / 2, h / 2)); b.castShadow = true; b.receiveShadow = true; root.add(b);
    }
  };
  buildRow(1); buildRow(-1);
  if (cross) for (const sx of [-1, 1]) for (let x = 20; x < 140; x += 16 + rand() * 6) for (const zz of [55, 25]) {
    const h = 8 + rand() * 16, b = new THREE.Mesh(new THREE.BoxGeometry(12, h, 10), new THREE.MeshStandardMaterial({ map: T.facade[Math.floor(rand() * 4)], roughness: 0.85 }));
    b.position.copy(W3(sx * x, zz + (zz > 40 ? 5 : -5), h / 2)); b.castShadow = true; root.add(b);
  }
  for (let z = zA; z < zB; z += 18) for (const sd of [-1, 1]) {
    if (skip(z) || (cross && z > 26 && z < 54)) continue;
    const lamp = makeLamp(); lamp.position.copy(W3(sd * 7.5, z, 0.15)); lamp.rotation.y = sd > 0 ? 0 : Math.PI; root.add(lamp);
    if (rand() < 0.7) { const tr = makeTree(rand); tr.position.copy(W3(sd * 11, z + 9, 0.15)); root.add(tr); }
  }
  if (env === 'busstop') {
    const shelter = new THREE.Group(), m = mat(0x3d4a56, 0.4);
    const glassM = new THREE.MeshStandardMaterial({ color: 0x9fc3d6, transparent: true, opacity: 0.35, roughness: 0.1 });
    const roofS = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.12, 6), mat(0x16a394, 0.4)); roofS.position.y = 2.6; roofS.castShadow = true; shelter.add(roofS);
    for (const zz of [-2.8, 2.8]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.6, 0.08), m); p.position.set(0.9, 1.3, zz); shelter.add(p); }
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.05, 2.2, 5.6), glassM); back.position.set(1.0, 1.3, 0); shelter.add(back);
    const bench = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.08, 3), mat(0x8a6a4a)); bench.position.set(0.6, 0.5, 0); shelter.add(bench);
    const sign = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.6, 0.9), mat(0x16a394)); sign.position.set(-0.6, 2.3, -3.6); shelter.add(sign);
    const signPole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 2.3), m); signPole.position.set(-0.6, 1.15, -3.6); shelter.add(signPole);
    shelter.position.copy(W3(10, 1, 0.15)); root.add(shelter);
    add(new THREE.PlaneGeometry(0.15, 14), yellow, 6.8, 0, 0.013);
  }
  for (const o of sim.obstacles) root.add(makeCar(o));
  return root;
}

class View3D {
  constructor(driverCanvas, topCanvas) {
    this.rd = new THREE.WebGLRenderer({ canvas: driverCanvas, antialias: true });
    this.rt = new THREE.WebGLRenderer({ canvas: topCanvas, antialias: true });
    for (const r of [this.rd, this.rt]) { r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap; r.outputColorSpace = THREE.SRGBColorSpace; r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.05; }
    this.cam = new THREE.PerspectiveCamera(2 * Math.atan(CFG.cy / CFG.f) * 180 / Math.PI, CFG.imgW / CFG.imgH, 0.1, 400);
    this.top = new THREE.OrthographicCamera(-10, 10, 10, -10, 1, 200);
  }
  load(sim) {
    if (this.scene) this.scene.traverse(o => {      // giai phong bo nho GPU cua canh cu
      if (o.geometry) o.geometry.dispose();
      if (o.material) [].concat(o.material).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); });
    });
    const sc = new THREE.Scene(); this.scene = sc; this.sim = sim;
    sc.background = new THREE.Color(0xbcd3e6); sc.fog = new THREE.Fog(0xbcd3e6, 60, 220);
    sc.add(new THREE.HemisphereLight(0xdfeeff, 0x6d6a5a, 0.9));
    const sun = new THREE.DirectionalLight(0xfff1dc, 2.2); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048); const c = sun.shadow.camera; c.left = -40; c.right = 40; c.top = 40; c.bottom = -40; c.near = 1; c.far = 160;
    sun.shadow.bias = -0.0005; sc.add(sun); sc.add(sun.target); this.sun = sun;
    buildWorld(sc, sim);
    this.bus = makeBus(); sc.add(this.bus);
    this.people = new Map();
  }
  sync(sim, dt) {
    const b = sim.bus;
    this.bus.position.copy(W3(b.x, b.z)); this.bus.rotation.y = -b.th;
    const fwd = W3(Math.sin(b.th), Math.cos(b.th));
    this.cam.position.copy(W3(b.x, b.z, CFG.camH)).addScaledVector(fwd, 0.05);
    this.cam.lookAt(this.cam.position.clone().add(fwd));
    if (sim.shake[0]) { this.cam.position.y += sim.shake[1] * 0.004; this.cam.rotateZ(sim.shake[0] * 0.0012); }
    this.sun.position.copy(W3(b.x + 25, b.z - 15, 45)); this.sun.target.position.copy(W3(b.x, b.z + 10));
    const seen = new Set();
    for (const p of sim.peds) {
      seen.add(p.id);
      let o = this.people.get(p.id);
      if (!o) { o = makeHuman(p.h, p.look + 1); this.scene.add(o); this.people.set(p.id, o); }
      o.position.copy(W3(p.x, p.z));
      const sp = Math.hypot(p.vx, p.vz);
      if (sp > 0.05) o.rotation.y = Math.atan2(-p.vx, p.vz);
      else if (o.userData.face === undefined) { o.rotation.y = p.x > 0 ? Math.PI / 2 : -Math.PI / 2; o.userData.face = 1; }
      if (p.hit) { o.rotation.x = -Math.PI / 2 * Math.min(1, (sim.t - (o.userData.hitT ??= sim.t)) * 3); o.position.y = 0.15; }
      animateHuman(o, p.hit ? 0 : sp, dt, sim.t);
    }
    for (const [id, o] of this.people) if (!seen.has(id)) { this.scene.remove(o); this.people.delete(id); }
  }
  resize(dw, dh, tw, th) {
    this.rd.setPixelRatio(Math.min(2, window.devicePixelRatio)); this.rt.setPixelRatio(Math.min(2, window.devicePixelRatio));
    this.rd.setSize(dw, dh, false); this.rt.setSize(tw, th, false);
    this.tw = tw; this.th = th;
  }
  render(topScale, frontFrac) {
    this.rd.render(this.scene, this.cam);
    const b = this.sim.bus, s = topScale, w = this.tw / s, h = this.th / s;
    const t = this.top; t.left = -w / 2; t.right = w / 2; t.top = h / 2; t.bottom = -h / 2; t.updateProjectionMatrix();
    const ahead = (frontFrac - 0.5) * h;
    const cx = b.x + Math.sin(b.th) * ahead, cz = b.z + Math.cos(b.th) * ahead;
    t.position.copy(W3(cx, cz, 80)); t.up.copy(W3(Math.sin(b.th), Math.cos(b.th))); t.lookAt(W3(cx, cz, 0));
    this.rt.render(this.scene, t);
  }
}
