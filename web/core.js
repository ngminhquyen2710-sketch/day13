/* ===================================================================
   VinBus Blind Spot Guard - LOI MO PHONG (khong phu thuoc do hoa)
   Cung thuat toan voi ban Python: pinhole -> Kalman + bu IMU -> rui ro -> AEB.
   He toa do 2D: x sang phai (dong), z ve phia truoc (bac). Goc xe theta > 0 = da re phai.
   =================================================================== */
'use strict';

const CFG = {
  imgW: 960, imgH: 540, hfovDeg: 90, camH: 1.6,     // camera dau xe (goc rong)
  personH: 1.65, personHmin: 1.5,                    // pinhole: chieu cao gia dinh / than trong
  pixelNoise: 2.0, missProb: 0.03,
  accelNoise: 1.0, confirmHits: 3, maxMissed: 8,     // Kalman
  hw: 1.4, zoneDepth: 3.0, turnExpand: 0.8, turnThrDps: 6,
  horizon: 3.0, dangerS: 1.5, minSpeed: 0.4,         // rui ro
  vibThr: 0.15, syncErr: 0.15,
  aebDecel: 5.0, maxSpeed: 14, wheelBase: 6.0,
  dtPhys: 1 / 60, imuSub: 4,
};
CFG.f = (CFG.imgW / 2) / Math.tan(CFG.hfovDeg * Math.PI / 360);
CFG.cx = CFG.imgW / 2; CFG.cy = CFG.imgH / 2;

const LV = { SAFE: 0, CAUTION: 1, DANGER: 2, STOP: 3 };

function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function gauss(r) { let u = 0; while (!u) u = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r()); }
function rot(th, x, z) { const c = Math.cos(th), s = Math.sin(th); return [c * x - s * z, s * x + c * z]; }
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ---------------- IMU (con quay) ---------------- */
class Gyro {
  constructor() { this.buf = []; this.bias = 0; this.biasReady = false; }
  push(t, g) { this.buf.push([t, g[0], g[1], g[2]]); if (this.buf.length > 2400) this.buf.splice(0, 600); }
  win(t0, t1) { const o = []; for (let i = this.buf.length - 1; i >= 0; i--) { const s = this.buf[i]; if (s[0] < t0) break; if (s[0] <= t1) o.push(s); } return o; }
  yawRate(t, w = 0.1) { const a = this.win(t - w, t); if (!a.length) return 0; let m = 0; for (const s of a) m += s[3]; return m / a.length - this.bias; }
  deltaYaw(t0, t1) {
    const a = this.win(t0, t1);
    if (a.length < 2) return this.yawRate(t1, 0.2) * (t1 - t0);
    let m = 0; for (const s of a) m += s[3]; return (m / a.length - this.bias) * (t1 - t0);
  }
  vibration(t) {
    const a = this.win(t - 0.5, t); if (a.length < 6) return 0;
    const mag = a.map(s => Math.hypot(s[1], s[2], s[3] - this.bias));
    const d = []; for (let i = 1; i < mag.length; i++) d.push(mag[i] - mag[i - 1]);
    const mu = d.reduce((p, q) => p + q, 0) / d.length;
    const sd = Math.sqrt(d.reduce((p, q) => p + (q - mu) ** 2, 0) / d.length);
    return sd / Math.SQRT2 / CFG.vibThr;
  }
  calibrate(t) { const a = this.win(t - 0.45, t); if (a.length > 10) { this.bias = a.reduce((p, s) => p + s[3], 0) / a.length; this.biasReady = true; } }
}

/* ---------------- Kalman: [x, z, vx, vz] ---------------- */
class Track {
  constructor(m, id) {
    this.id = id; this.x = [m.X, m.Z, 0, 0];
    this.P = [[m.sx * m.sx, 0, 0, 0], [0, m.sz * m.sz, 0, 0], [0, 0, 4, 0], [0, 0, 0, 4]];
    this.hits = 1; this.missed = 0; this.meas = m; this.matched = true; this.gt = m.gt;
    this.level = 0; this.ttc = null;
  }
  // nguoi di v*dt, xe tien ds (odometry), roi xe quay dth (IMU)  => p' = R(p + v dt - [0,ds]), v' = R v
  predict(dt, dth, ds, qa) {
    const c = Math.cos(dth), s = Math.sin(dth);
    const [px, pz, vx, vz] = this.x;
    const ax = px + vx * dt, az = pz + vz * dt - ds;
    this.x = [c * ax - s * az, s * ax + c * az, c * vx - s * vz, s * vx + c * vz];
    const F = [[c, -s, c * dt, -s * dt], [s, c, s * dt, c * dt], [0, 0, c, -s], [0, 0, s, c]];
    const FP = mm(F, this.P), P = mm(FP, tr(F));
    const q = qa * qa, d2 = dt * dt, d3 = d2 * dt / 2, d4 = d2 * d2 / 4;
    P[0][0] += q * d4; P[1][1] += q * d4; P[2][2] += q * d2; P[3][3] += q * d2;
    P[0][2] += q * d3; P[2][0] += q * d3; P[1][3] += q * d3; P[3][1] += q * d3;
    this.P = P;
  }
  innov(m) {
    const y = [m.X - this.x[0], m.Z - this.x[1]];
    const S = [[this.P[0][0] + m.sx * m.sx, this.P[0][1]], [this.P[1][0], this.P[1][1] + m.sz * m.sz]];
    return [y, S];
  }
  maha(m) { const [y, S] = this.innov(m); const Si = inv2(S); return Math.sqrt(y[0] * (Si[0][0] * y[0] + Si[0][1] * y[1]) + y[1] * (Si[1][0] * y[0] + Si[1][1] * y[1])); }
  update(m) {
    const [y, S] = this.innov(m); const Si = inv2(S); const P = this.P;
    const K = P.map(r => [r[0] * Si[0][0] + r[1] * Si[1][0], r[0] * Si[0][1] + r[1] * Si[1][1]]);
    for (let i = 0; i < 4; i++) this.x[i] += K[i][0] * y[0] + K[i][1] * y[1];
    const NP = P.map((r, i) => r.map((v, j) => v - K[i][0] * P[0][j] - K[i][1] * P[1][j]));
    for (let i = 0; i < 4; i++) for (let j = 0; j < i; j++) { const a = (NP[i][j] + NP[j][i]) / 2; NP[i][j] = NP[j][i] = a; }
    this.P = NP; this.meas = m; this.hits++; this.missed = 0; this.matched = true; this.gt = m.gt;
  }
}
function mm(A, B) { return A.map(r => B[0].map((_, j) => r.reduce((s, v, k) => s + v * B[k][j], 0))); }
function tr(A) { return A[0].map((_, j) => A.map(r => r[j])); }
function inv2(S) { const d = S[0][0] * S[1][1] - S[0][1] * S[1][0]; return [[S[1][1] / d, -S[0][1] / d], [-S[1][0] / d, S[0][0] / d]]; }

/* ---------------- Danh gia rui ro ---------------- */
function zoneFor(yawRate) {
  const z = { x0: -CFG.hw, x1: CFG.hw, z1: CFG.zoneDepth, turn: 0 };
  const thr = CFG.turnThrDps * Math.PI / 180;
  if (yawRate > thr) { z.x1 += CFG.turnExpand; z.turn = 1; }
  else if (yawRate < -thr) { z.x0 -= CFG.turnExpand; z.turn = -1; }
  return z;
}
const inZone = (x, z, Z) => x >= Z.x0 && x <= Z.x1 && z >= 0 && z <= Z.z1;
const pathLen = s => Math.max(8, 5 + 3 * s);
const inPath = (x, z, s) => Math.abs(x) <= CFG.hw && z >= 0 && z <= pathLen(s);

// p, v: vi tri va van toc RIENG cua nguoi (he xe); s: toc do xe
// sv: do lech chuan cua van toc uoc luong. Chi coi la "dang di chuyen" khi van toc vuot han nhieu.
function assess(px, pz, vx, vz, s, Z, k, sv = 0) {
  px *= k; pz *= k; vx *= k; vz *= k;
  if (Math.hypot(vx, vz) < CFG.minSpeed + 2 * sv) { vx = 0; vz = 0; }
  const rvx = vx, rvz = vz - s;                       // van toc tuong doi so voi xe
  const moving = vx !== 0 || vz !== 0;
  if (inZone(px, pz, Z)) return { level: LV.STOP, ttc: 0, tz: 0, px, pz, rvx, rvz };
  let tz = null, tp = null;
  for (let t = 0.05; t <= CFG.horizon + 1e-9; t += 0.05) {
    const qx = px + rvx * t, qz = pz + rvz * t;
    if (tp === null && inPath(qx, qz, s)) tp = t;
    if (inZone(qx, qz, Z)) { tz = t; break; }
  }
  let level = LV.SAFE;
  if ((tz !== null && tz < CFG.dangerS) || (moving && s > 1 && tp !== null && tp < CFG.dangerS)) level = LV.DANGER;
  else if (tz !== null || tp !== null || inPath(px, pz, s)) level = LV.CAUTION;
  return { level, ttc: tz !== null ? tz : tp, tz, px, pz, rvx, rvz };
}

/* ---------------- Kich ban ---------------- */
// env: mo ta khung canh cho phan ve; obstacles: hop chan (o to do) cho phat hien bi che khuat
const SCENARIOS = {
  stop: {
    title: 'Rời bến', sub: 'Người chạy băng qua đầu xe khi xe vừa rời bến',
    env: 'busstop', duration: 13,
    bus: { x: 5.25, z: 0, th: 0, s: 0 },
    peds: [
      { x: 8.3, z: -1.5, h: 1.62 }, { x: 9.2, z: 0.8, h: 1.74 }, { x: 8.6, z: 2.6, h: 1.58 },
      { x: 7.6, z: 4.5, h: 1.70 },
      { x: -8.6, z: 12, h: 1.72, start: 1.0, speed: 3.0, wps: [[9.0, 12]], kind: 'cross' },
      { x: -9.0, z: 30, h: 1.68, start: 0, speed: 1.2, wps: [[-9.0, -20]], kind: 'walk' },
    ],
    obstacles: [],
    drive(sim) { return { target: sim.t < 1.5 ? 0 : 5.0, yaw: 0 }; },
    captions: [
      [0, 'Xe đang đỗ ở bến. Hành khách đứng chờ trên vỉa hè: đứng yên nên không được gây báo động.'],
      [1.5, 'Xe bắt đầu rời bến.'],
      [1.0, 'Một người chạy băng qua đầu xe để kịp lên xe. Hệ thống phải dự báo quỹ đạo và cảnh báo trước khi người đó vào vùng nguy hiểm.'],
      [7, 'Nếu bật phanh tự động, xe dừng lại; bảng bên dưới đếm số lần cảnh báo kịp thời.'],
    ],
  },
  turn: {
    title: 'Rẽ phải ở ngã tư', sub: 'Xe quay mạnh: chỗ bù IMU tạo khác biệt',
    env: 'intersection', duration: 16,
    bus: { x: 5.25, z: -8, th: 0, s: 7 },
    peds: [
      { x: 9.8, z: 29.0, h: 1.66 }, { x: 10.8, z: 30.2, h: 1.78 }, { x: 8.7, z: 48.8, h: 1.6 },
      { x: -8.8, z: 48.4, h: 1.72 }, { x: -9.2, z: 31.0, h: 1.64 },
      { x: 14.5, z: 49.6, h: 1.70 }, { x: 18.5, z: 50.2, h: 1.62 }, { x: 23.0, z: 49.4, h: 1.76 },
      { x: 20.0, z: 30.6, h: 1.68 },
      { x: 12.0, z: 31.8, h: 1.70, start: 6.4, speed: 1.3, wps: [[12.0, 49]], kind: 'cross' },
      { x: 9.0, z: 5, h: 1.75, start: 0, speed: 1.3, wps: [[9.0, 26]], kind: 'walk' },
    ],
    obstacles: [],
    turnR: 9, turnZc: 25.75,
    drive(sim) {
      const b = sim.bus;
      if (b.phase === undefined) b.phase = 'approach';
      if (b.phase === 'approach' && b.z >= this.turnZc) b.phase = 'turn';
      if (b.phase === 'turn' && b.th >= Math.PI / 2) { b.phase = 'exit'; b.th = Math.PI / 2; }
      const target = b.phase === 'approach' ? (b.z < 12 ? 7 : 4) : (b.phase === 'turn' ? 4 : 6);
      return { target, yaw: b.phase === 'turn' ? b.s / this.turnR : 0 };
    },
    captions: [
      [0, 'Xe tiến vào ngã tư. Người đi bộ đứng chờ ở các góc đường.'],
      [4.2, 'Xe rẽ phải: trong khung hình, người đứng yên trông như đang chạy ngang. Bù IMU giữ họ đứng yên. Bấm I để tắt bù và xem báo động giả.'],
      [6.4, 'Một người đang qua đường ở nhánh xe sắp rẽ vào: đây là nguy hiểm thật.'],
    ],
  },
  child: {
    title: 'Trẻ em lao ra', sub: 'Ca lỗi: bị che khuất và thấp hơn giả định',
    env: 'parked', duration: 9,
    bus: { x: 1.75, z: 0, th: 0, s: 7 },
    peds: [
      { x: 5.6, z: 33.0, h: 1.12, start: 3.2, speed: 2.6, wps: [[-4, 33.0]], kind: 'child' },
      { x: 8.8, z: 20, h: 1.7, start: 0, speed: 1.2, wps: [[8.8, 60]], kind: 'walk' },
      { x: -8.6, z: 26, h: 1.64 },
    ],
    obstacles: [
      { x: 5.25, z: 30.0, w: 1.9, l: 4.5, h: 1.5, color: 0xb8bec6 },
      { x: 5.25, z: 36.1, w: 2.0, l: 5.0, h: 2.1, color: 0x2f4f7a },
      { x: 5.25, z: 22.8, w: 1.9, l: 4.4, h: 1.5, color: 0x8c2f2f },
      { x: 5.25, z: 43.5, w: 1.9, l: 4.5, h: 1.5, color: 0xe3e3e3 },
    ],
    drive() { return { target: 7, yaw: 0 }; },
    captions: [
      [0, 'Xe chạy 25 km/h cạnh dãy ô tô đỗ ven đường.'],
      [3.2, 'Một em nhỏ lao ra từ khe giữa hai xe đỗ.'],
      [4.0, 'Ca lỗi: em bị xe đỗ che nên camera thấy muộn, và vì thấp hơn chiều cao giả định nên bị ước lượng xa hơn thực tế khoảng 40%.'],
    ],
  },
  free: {
    title: 'Lái tự do', sub: 'Bạn tự lái và thả người đi bộ',
    env: 'free', duration: 1e9,
    bus: { x: 1.75, z: 0, th: 0, s: 0 },
    peds: [{ x: 8.6, z: 18, h: 1.7 }, { x: -8.7, z: 26, h: 1.62 }, { x: 8.9, z: 44, h: 1.75 }],
    obstacles: [],
    drive: null,
    captions: [[0, 'Giữ ↑ hoặc Q để tăng tốc, ↓ hoặc E để giảm tốc (giữ lâu sẽ dừng hẳn), ← → để đánh lái. Dùng các nút bên dưới để thả người đi bộ.']],
  },
};

/* ---------------- Mo phong ---------------- */
class Sim {
  constructor(key, opts = {}) {
    this.key = key; this.sc = SCENARIOS[key];
    this.rng = mulberry32(opts.seed || 7);
    this.comp = opts.comp !== false; this.sync = !!opts.sync; this.aebOn = opts.aeb !== false;
    this.t = 0; this.step = 0; this.manual = key === 'free';
    const b = this.sc.bus; this.bus = { x: b.x, z: b.z, th: b.th, s: b.s, yaw: 0, steer: 0, acc: 0 };
    this.gyro = new Gyro(); this.gyroBias = 0.012 + 0.006 * gauss(this.rng);
    this.peds = []; this.pid = 0;
    for (const p of this.sc.peds) this.addPed(p);
    this.obstacles = this.sc.obstacles.map(o => ({ ...o }));
    this.tracks = []; this.tid = 0; this.dets = [];
    this.zone = zoneFor(0); this.overall = 0; this.minTTC = null;
    this.aeb = { active: false, since: -9, clearSince: -9 };
    this.bumpUntil = -1; this.shake = [0, 0];
    this.input = { up: false, down: false, left: false, right: false };
    this.M = { falseAlarms: 0, aebTriggers: 0, needlessBrakes: 0, collisions: 0,
      errA: [0, 0], errC: [0, 0], events: [] };
    this.lastCollision = -9; this.pending = []; this.pendingBrake = [];
  }
  addPed(p) {
    const r = this.rng;
    this.peds.push({ id: ++this.pid, x: p.x, z: p.z, h: p.h || 1.7, vx: 0, vz: 0, kind: p.kind || 'static',
      wps: p.wps ? p.wps.map(w => w.slice()) : [], speed: p.speed || 0, start: p.start || 0,
      look: Math.floor(r() * 1e6), hit: false, gtFirst: null, gtEntry: null, sysFirst: null, gtLevel: 0 });
  }
  // tha nguoi theo toa do he xe (che do lai tu do)
  spawnRel(kind) {
    const b = this.bus, r = this.rng;
    const W = (x, z) => { const [dx, dz] = rot(-b.th, x, z); return [b.x + dx, b.z + dz]; };
    const zAhead = 9 + b.s * 1.6 + r() * 4;
    if (kind === 'right' || kind === 'left') {
      const sd = kind === 'right' ? 1 : -1;
      const [x, z] = W(sd * 7.5, zAhead), [ex, ez] = W(-sd * 9, zAhead);
      this.addPed({ x, z, h: 1.6 + r() * 0.22, start: this.t, speed: 1.3 + r() * 0.5, wps: [[ex, ez]], kind: 'cross' });
    } else if (kind === 'child') {
      const [x, z] = W(4.3, zAhead * 0.8), [ex, ez] = W(-6, zAhead * 0.8);
      this.addPed({ x, z, h: 1.08 + r() * 0.12, start: this.t, speed: 2.4, wps: [[ex, ez]], kind: 'child' });
    } else {
      const sd = r() < 0.5 ? 1 : -1; const [x, z] = W(sd * (3.0 + r() * 1.5), zAhead);
      this.addPed({ x, z, h: 1.58 + r() * 0.24 });
    }
  }
  toBus(x, z) { return rot(this.bus.th, x - this.bus.x, z - this.bus.z); }
  bump() { this.bumpUntil = this.t + 0.8; }

  physics(dt) {
    const b = this.bus, inp = this.input;
    let acc, yaw;
    if (this.manual) {
      acc = inp.up ? 1.6 : inp.down ? -3.2 : -0.15;
      const st = inp.left ? -1 : inp.right ? 1 : 0;
      b.steer = st ? clamp(b.steer + st * 0.7 * dt, -0.55, 0.55) : b.steer * Math.max(0, 1 - 4 * dt);
      yaw = b.s * Math.tan(b.steer) / CFG.wheelBase;
    } else {
      const d = this.sc.drive(this);
      acc = clamp(1.2 * (d.target - b.s), -3, 1.5); yaw = d.yaw;
    }
    if (this.aeb.active) acc = -CFG.aebDecel;
    b.acc = acc; b.s = clamp(b.s + acc * dt, 0, CFG.maxSpeed);
    if (!this.manual) yaw = this.sc.drive(this).yaw;          // phu thuoc toc do moi
    b.yaw = yaw;
    // IMU lay mau 240 Hz
    const n = CFG.imuSub, bumping = this.t < this.bumpUntil;
    for (let i = 1; i <= n; i++) {
      const tau = this.t + i * dt / n, r = this.rng;
      const g = [gauss(r) * 0.01, gauss(r) * 0.01, yaw + this.gyroBias + gauss(r) * 0.012];
      if (bumping) { g[0] += gauss(r) * 0.9; g[1] += gauss(r) * 0.9; g[2] += gauss(r) * 0.9; }
      this.gyro.push(tau + (this.sync ? CFG.syncErr : 0), g);
    }
    b.th += yaw * dt;
    b.x += Math.sin(b.th) * b.s * dt; b.z += Math.cos(b.th) * b.s * dt;
    this.shake = bumping ? [gauss(this.rng) * 6, gauss(this.rng) * 6] : [0, 0];
    for (const p of this.peds) {
      p.vx = 0; p.vz = 0;
      if (p.hit || this.t < p.start || !p.wps.length) continue;
      const [wx, wz] = p.wps[0], dx = wx - p.x, dz = wz - p.z, d = Math.hypot(dx, dz);
      if (d < 0.05) { p.wps.shift(); continue; }
      const st = Math.min(d, p.speed * dt); p.vx = dx / d * p.speed; p.vz = dz / d * p.speed;
      p.x += dx / d * st; p.z += dz / d * st;
    }
    this.t += dt;
  }

  // gia lap detector: hinh chieu that + nhieu + bo sot + bi che khuat
  detect(noiseScale) {
    const out = [], f = CFG.f, cx = CFG.cx, cy = CFG.cy, H = CFG.imgH, W = CFG.imgW, r = this.rng;
    const obs = [];
    for (const o of this.obstacles) {
      const pts = [];
      for (const [ox, oz] of [[-o.w / 2, -o.l / 2], [o.w / 2, -o.l / 2], [-o.w / 2, o.l / 2], [o.w / 2, o.l / 2]]) {
        const [bx, bz] = this.toBus(o.x + ox, o.z + oz); pts.push([bx, bz]);
      }
      const zmin = Math.min(...pts.map(p => p[1]));
      if (zmin < 0.4) continue;
      const us = pts.map(p => cx + f * p[0] / p[1]);
      const vTop = Math.min(...pts.map(p => cy + f * (CFG.camH - o.h) / p[1]));
      obs.push({ zmin, u0: Math.min(...us), u1: Math.max(...us), vTop });
    }
    for (const p of this.peds) {
      const [x, z] = this.toBus(p.x, p.z);
      if (z < 0.8) continue;
      const u = cx + f * x / z, vF = cy + f * CFG.camH / z, hp = f * p.h / z, w = 0.3 * hp;
      let vH = vF - hp, vB = vF;
      if (u < -w / 2 || u > W + w / 2) continue;
      let hidden = false;
      for (const o of obs) {
        if (o.zmin >= z) continue;
        const ov = Math.max(0, Math.min(u + w / 2, o.u1) - Math.max(u - w / 2, o.u0)) / w;
        if (ov > 0.5 && o.vTop < vB) { vB = Math.max(vH, o.vTop); if (vB - vH < 0.35 * hp) hidden = true; }
      }
      if (hidden || r() < CFG.missProb || hp < 22) continue;
      const sp = CFG.pixelNoise * noiseScale;
      let b = [u - w / 2 + gauss(r) * sp, vH + gauss(r) * sp, u + w / 2 + gauss(r) * sp, vB + gauss(r) * sp];
      b = b.map((v, i) => v + this.shake[i % 2]);
      b = [Math.max(0, b[0]), Math.max(0, b[1]), Math.min(W - 1, b[2]), Math.min(H - 1, b[3])];
      const bh = Math.max(b[3] - b[1], 1), uc = (b[0] + b[2]) / 2;
      const trunc = b[1] <= 2 || b[3] >= H - 2;
      const Z = f * CFG.personH / bh, X = (uc - cx) * Z / f;
      let sz = Z * sp / bh, sx = Math.hypot(Z * sp / f, X * sp / bh);
      if (trunc) { sz *= 3; sx *= 2; }
      out.push({ X, Z, sx: Math.max(sx, 0.03), sz: Math.max(sz, 0.05), box: b, trunc, gt: p.id });
    }
    return out;
  }

  perceive(dt) {
    const t = this.t, b = this.bus;
    if (!this.gyro.biasReady && t >= 0.5) this.gyro.calibrate(t);
    const vib = this.gyro.vibration(t); this.vib = vib;
    const ns = 1 + 2 * Math.min(vib, 3);
    const meas = this.detect(ns); this.dets = meas;
    const dth = this.comp ? this.gyro.deltaYaw(t - dt, t) : 0;
    const ds = b.s * dt;                                             // odometry tu dong ho xe
    for (const tk of this.tracks) { tk.predict(dt, dth, ds, CFG.accelNoise); tk.matched = false; }
    const pairs = [];
    this.tracks.forEach((tk, i) => meas.forEach((m, j) => {
      const d = Math.hypot(m.X - tk.x[0], m.Z - tk.x[1]);
      if (d < Math.max(1.5, 0.12 * m.Z) || tk.maha(m) < 3.5) pairs.push([d, i, j]);
    }));
    pairs.sort((a, c) => a[0] - c[0]);
    const ut = new Set(), um = new Set();
    for (const [, i, j] of pairs) { if (ut.has(i) || um.has(j)) continue; this.tracks[i].update(meas[j]); ut.add(i); um.add(j); }
    this.tracks.forEach((tk, i) => { if (!ut.has(i)) tk.missed++; });
    meas.forEach((m, j) => { if (!um.has(j)) this.tracks.push(new Track(m, ++this.tid)); });
    this.tracks = this.tracks.filter(tk => tk.missed <= CFG.maxMissed);

    const yawM = this.gyro.yawRate(t); this.yawMeas = yawM;
    const Z = zoneFor(yawM); this.zone = Z;
    const k = CFG.personHmin / CFG.personH;
    let overall = 0, minTTC = null;
    this.confirmed = this.tracks.filter(tk => tk.hits >= CFG.confirmHits && tk.missed <= 3);
    for (const tk of this.confirmed) {
      const sv = Math.sqrt(Math.max(0, tk.P[2][2] + tk.P[3][3]));
      const a = assess(tk.x[0], tk.x[1], tk.x[2], tk.x[3], b.s, Z, k, sv); tk.sv = sv;
      const prev = tk.level; tk.level = a.level; tk.ttc = a.ttc; tk.risk = a;
      overall = Math.max(overall, a.level);
      if (a.tz !== null) minTTC = minTTC === null ? a.tz : Math.min(minTTC, a.tz);
      const p = this.peds.find(q => q.id === tk.gt);
      if (p) {
        if (a.level >= LV.DANGER && prev < LV.DANGER) {
          this.pending.push({ t, p });
          if (p.sysFirst === null) p.sysFirst = t;
        }
        if (tk.matched && !tk.meas.trunc) {
          const [gx, gz] = this.toBus(p.x, p.z), e = Math.abs(tk.x[1] - gz) / Math.max(gz, 1);
          const E = p.kind === 'child' ? this.M.errC : this.M.errA; E[0] += e; E[1]++;
        }
      }
    }
    this.overall = overall; this.minTTC = minTTC;

    // ground truth: cung ham rui ro, dung vi tri / van toc that, khong than trong
    const Zt = zoneFor(b.yaw); let gtOverall = 0;
    for (const p of this.peds) {
      const [x, z] = this.toBus(p.x, p.z), [vx, vz] = rot(b.th, p.vx, p.vz);
      const a = assess(x, z, vx, vz, b.s, Zt, 1); p.gtLevel = a.level; p.gtRisk = a;
      gtOverall = Math.max(gtOverall, a.level);
      if (a.level >= LV.DANGER && p.gtFirst === null) { p.gtFirst = t; p.gtEntry = t + (a.ttc || 0); }
      if (!p.hit && x > -1.35 && x < 1.35 && z > -11.5 && z < 0.2 && p.h > 0) {
        p.hit = true; this.M.collisions++; this.lastCollision = t; this.log('VA CHẠM', p);
      }
    }
    this.gtOverall = gtOverall;

    // phanh tu dong (AEB)
    const want = this.aebOn && (overall === LV.STOP || (minTTC !== null && minTTC < 1.2));
    if (want && !this.aeb.active) {
      this.aeb.active = true; this.aeb.since = t; this.M.aebTriggers++;
      this.pendingBrake.push({ t });
    }
    if (want) this.aeb.clearSince = t;
    // mot canh bao la "dung" neu ground truth thay nguy hiem trong vong 2,5 s; qua han thi la bao dong gia
    this.pending = this.pending.filter(a => {
      if (a.p.gtLevel >= LV.DANGER || a.p.hit) return false;
      if (t - a.t > 2.5) { this.M.falseAlarms++; this.log('Báo động giả', a.p); return false; }
      return true;
    });
    this.pendingBrake = this.pendingBrake.filter(a => {
      if (gtOverall >= LV.DANGER) return false;
      if (t - a.t > 2.5) { this.M.needlessBrakes++; this.log('Phanh không cần thiết'); return false; }
      return true;
    });
    if (this.aeb.active && !want && t - this.aeb.clearSince > 0.6 && t - this.aeb.since > 0.8) this.aeb.active = false;
  }

  log(msg, p) { this.M.events.unshift({ t: this.t, msg, id: p ? p.id : null }); if (this.M.events.length > 6) this.M.events.pop(); }

  tick() {
    this.physics(CFG.dtPhys); this.step++;
    if (this.step % 2 === 0) this.perceive(2 * CFG.dtPhys);
  }

  summary() {
    const hz = this.peds.filter(p => p.gtFirst !== null);
    const inTime = hz.filter(p => p.sysFirst !== null && p.sysFirst <= p.gtEntry - 0.5);
    const leads = hz.filter(p => p.sysFirst !== null).map(p => p.gtEntry - p.sysFirst);
    return {
      falseAlarms: this.M.falseAlarms, needless: this.M.needlessBrakes, aeb: this.M.aebTriggers,
      hazards: hz.length, inTime: inTime.length, collisions: this.M.collisions,
      lead: leads.length ? leads.reduce((a, c) => a + c, 0) / leads.length : NaN,
      errA: this.M.errA[1] ? 100 * this.M.errA[0] / this.M.errA[1] : NaN,
      errC: this.M.errC[1] ? 100 * this.M.errC[0] / this.M.errC[1] : NaN,
    };
  }
}

if (typeof module !== 'undefined') module.exports = { CFG, LV, Sim, SCENARIOS, assess, zoneFor };
