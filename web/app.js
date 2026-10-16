/* ===================================================================
   GIAO DIEN: vong lap, ban phim, lop phu tren camera va ban do, so lieu, so sanh.
   =================================================================== */
'use strict';

const $ = id => document.getElementById(id);
const LCOL = ['#3fc27f', '#f2c230', '#ff8a1f', '#ff4b4b'];
const LNAME = ['AN TOÀN', 'CHÚ Ý', 'NGUY HIỂM', 'DỪNG'];
const TOP_SPAN = 36, FRONT = 0.8;          // ban do: bao nhieu met theo chieu ngang, vi tri dau xe
const opts = { comp: true, sync: false, aeb: true, gt: true };
let sim, view, key = 'turn', paused = false, seed = 11;

function start(k) {
  key = k; seed = (seed * 7919 + 13) % 100000;
  sim = new Sim(k, { seed, comp: opts.comp, sync: opts.sync, aeb: opts.aeb });
  view.load(sim);
  document.querySelectorAll('.tab').forEach(b => b.setAttribute('aria-selected', b.dataset.k === k));
  $('scTitle').textContent = sim.sc.title; $('scSub').textContent = sim.sc.sub;
  $('spawnBox').classList.toggle('dim', false);
  paused = false; syncButtons();
}

/* ---------------- ban phim ---------------- */
const DRIVE = { ArrowUp: 'up', KeyQ: 'up', ArrowDown: 'down', KeyE: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
window.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const c = e.code;
  if (DRIVE[c]) {
    e.preventDefault(); sim.input[DRIVE[c]] = true;
    if (!sim.manual) { sim.manual = true; toast('Bạn đang lái. Bấm R để chạy lại kịch bản tự động.'); }
    return;
  }
  if (e.repeat) return;
  const act = {
    KeyI: () => toggle('comp'), KeyK: () => toggle('sync'), KeyU: () => toggle('aeb'), KeyG: () => toggle('gt'),
    KeyV: () => sim.bump(), KeyR: () => start(key), KeyP: () => pause(), Space: () => pause(),
    Digit1: () => spawn('right'), Digit2: () => spawn('left'), Digit3: () => spawn('static'), Digit4: () => spawn('child'),
    Digit5: () => start('stop'), Digit6: () => start('turn'), Digit7: () => start('child'), Digit8: () => start('free'),
  }[c];
  if (act) { e.preventDefault(); act(); }
});
window.addEventListener('keyup', e => { if (DRIVE[e.code]) sim.input[DRIVE[e.code]] = false; });
window.addEventListener('blur', () => { for (const k in sim.input) sim.input[k] = false; });

function toggle(name) {
  opts[name] = !opts[name];
  if (name === 'comp') sim.comp = opts.comp;
  if (name === 'sync') sim.sync = opts.sync;
  if (name === 'aeb') { sim.aebOn = opts.aeb; if (!opts.aeb) sim.aeb.active = false; }
  syncButtons();
  const msg = { comp: ['Bù IMU: BẬT', 'Bù IMU: TẮT. Khi xe rẽ, người đứng yên sẽ bị tưởng là đang chạy.'],
    sync: ['Lỗi đồng bộ 150 ms: BẬT', 'Lỗi đồng bộ: TẮT'], aeb: ['Phanh tự động: BẬT', 'Phanh tự động: TẮT'],
    gt: ['Hiện vị trí thật: BẬT', 'Hiện vị trí thật: TẮT'] }[name];
  toast(opts[name] ? msg[0] : msg[1]);
}
function pause() { paused = !paused; syncButtons(); }
function spawn(kind) { sim.spawnRel(kind); }
function syncButtons() {
  for (const n of ['comp', 'sync', 'aeb', 'gt']) $('t_' + n).setAttribute('aria-pressed', opts[n]);
  $('pauseBtn').textContent = paused ? 'Tiếp tục (P)' : 'Tạm dừng (P)';
}
let toastT = 0;
function toast(m) { $('toast').textContent = m; $('toast').hidden = false; toastT = performance.now() + 3200; }

/* ---------------- lop phu camera ---------------- */
function drawDriver(ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  const k = w / CFG.imgW, f = CFG.f, cx = CFG.cx, cy = CFG.cy;
  const P = (x, z) => [(cx + f * x / z) * k, (cy + f * CFG.camH / z) * k];
  // duong di cua xe tren mat duong
  const s = sim.bus.s, L = pathLen(s), Z = sim.zone;
  const poly = (x0, x1, z0, z1) => { const a = P(x0, z0), b = P(x1, z0), c = P(x1, z1), d = P(x0, z1); ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.lineTo(...c); ctx.lineTo(...d); ctx.closePath(); };
  poly(-CFG.hw, CFG.hw, 1.2, L); ctx.fillStyle = 'rgba(120,200,255,0.10)'; ctx.fill();
  ctx.setLineDash([10, 8]); ctx.strokeStyle = 'rgba(160,215,255,0.55)'; ctx.lineWidth = 2 * k; ctx.stroke(); ctx.setLineDash([]);
  poly(Z.x0, Z.x1, 1.2, Z.z1); ctx.fillStyle = hexA(LCOL[sim.overall], 0.28); ctx.fill();
  ctx.strokeStyle = hexA(LCOL[sim.overall], 0.9); ctx.lineWidth = 2.5 * k; ctx.stroke();
  // box nguoi
  ctx.font = `600 ${Math.max(11, 15 * k)}px ${getComputedStyle(document.body).getPropertyValue('--body')}`;
  ctx.textBaseline = 'bottom';
  for (const tk of sim.confirmed || []) {
    if (!tk.matched) continue;
    const [x1, y1, x2, y2] = tk.meas.box.map((v, i) => v * k + (i % 2 ? 0 : 0));
    const col = LCOL[tk.level];
    ctx.strokeStyle = col; ctx.lineWidth = Math.max(2, 3 * k); ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    let lab = `#${tk.id}  ${tk.x[1].toFixed(1)} m`;
    if (tk.level >= 1 && tk.ttc !== null && tk.ttc > 0) lab += `  ·  TTC ${tk.ttc.toFixed(1)} s`;
    if (tk.meas.trunc) lab += '  (bị cắt)';
    const tw = ctx.measureText(lab).width + 10, th = 20 * Math.max(0.8, k);
    const ty = Math.max(th, y1 - 2);
    ctx.fillStyle = col; ctx.fillRect(x1 - 1, ty - th, tw, th);
    ctx.fillStyle = '#0b1016'; ctx.fillText(lab, x1 + 4, ty - 3);
  }
}
function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})`; }

/* ---------------- lop phu ban do ---------------- */
function drawTop(ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  const s = w / TOP_SPAN, ox = w / 2, oy = FRONT * h;
  const P = (x, z) => [ox + x * s, oy - z * s];
  const b = sim.bus;
  // goc nhin camera
  const far = 60, half = CFG.hfovDeg * Math.PI / 360;
  ctx.beginPath(); ctx.moveTo(...P(0, 0)); ctx.lineTo(...P(-far * Math.tan(half), far)); ctx.lineTo(...P(far * Math.tan(half), far)); ctx.closePath();
  ctx.fillStyle = 'rgba(160,215,255,0.07)'; ctx.fill();
  ctx.strokeStyle = 'rgba(200,230,255,0.45)'; ctx.lineWidth = 1; ctx.setLineDash([4, 6]);
  ctx.beginPath(); ctx.moveTo(...P(0, 0)); ctx.lineTo(...P(-far * Math.tan(half), far)); ctx.moveTo(...P(0, 0)); ctx.lineTo(...P(far * Math.tan(half), far)); ctx.stroke();
  // hanh lang duong di + vung nguy hiem
  const L = pathLen(b.s), Z = sim.zone;
  ctx.setLineDash([8, 6]); ctx.strokeStyle = 'rgba(170,220,255,0.85)'; ctx.lineWidth = 1.5;
  ctx.strokeRect(P(-CFG.hw, L)[0], P(0, L)[1], 2 * CFG.hw * s, L * s); ctx.setLineDash([]);
  const [zx, zy] = P(Z.x0, Z.z1);
  ctx.fillStyle = hexA(LCOL[sim.overall], 0.3); ctx.fillRect(zx, zy, (Z.x1 - Z.x0) * s, Z.z1 * s);
  ctx.strokeStyle = LCOL[sim.overall]; ctx.lineWidth = 2; ctx.strokeRect(zx, zy, (Z.x1 - Z.x0) * s, Z.z1 * s);
  ctx.font = '600 12px ' + getComputedStyle(document.body).getPropertyValue('--body');
  ctx.fillStyle = 'rgba(225,240,255,0.9)'; ctx.fillText('đường đi của xe', P(CFG.hw, L)[0] + 6, P(0, L)[1] + 14);
  if (Z.turn) { ctx.fillStyle = '#f2c230'; ctx.fillText(Z.turn > 0 ? 'đang rẽ phải: nới vùng' : 'đang rẽ trái: nới vùng', P(Z.turn > 0 ? Z.x1 : Z.x0, Z.z1)[0] + (Z.turn > 0 ? 6 : -130), P(0, Z.z1)[1] - 6); }
  // vi tri that (ground truth): noi voi uoc luong de thay sai so
  if (opts.gt) for (const tk of sim.confirmed || []) {
    const p = sim.peds.find(q => q.id === tk.gt); if (!p) continue;
    const [gx, gz] = sim.toBus(p.x, p.z);
    ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(...P(gx, gz)); ctx.lineTo(...P(tk.x[0], tk.x[1])); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeRect(P(gx, gz)[0] - 5, P(gx, gz)[1] - 5, 10, 10);
  }
  // uoc luong cua he thong
  for (const tk of sim.confirmed || []) {
    const col = LCOL[tk.level], [px, py] = P(tk.x[0], tk.x[1]);
    // elip 2 sigma
    const a = tk.P[0][0], c2 = tk.P[1][1], bxy = tk.P[0][1];
    const tr = (a + c2) / 2, det = Math.sqrt(Math.max(0, ((a - c2) / 2) ** 2 + bxy * bxy));
    const l1 = tr + det, l2 = Math.max(1e-6, tr - det), ang = 0.5 * Math.atan2(2 * bxy, a - c2);
    ctx.beginPath(); ctx.ellipse(px, py, Math.max(3, 2 * Math.sqrt(l1) * s), Math.max(3, 2 * Math.sqrt(l2) * s), -ang, 0, Math.PI * 2);
    ctx.strokeStyle = hexA(col, 0.8); ctx.lineWidth = 1.2; ctx.stroke(); ctx.fillStyle = hexA(col, 0.12); ctx.fill();
    const r = tk.risk;
    if (r && (r.rvx || r.rvz) && tk.level >= 1) {
      ctx.fillStyle = col;
      for (let t = 0.25; t <= CFG.horizon; t += 0.25) { const [qx, qy] = P(r.px + r.rvx * t, r.pz + r.rvz * t); ctx.beginPath(); ctx.arc(qx, qy, 1.8, 0, 7); ctx.fill(); }
    }
    const moving = Math.hypot(tk.x[2], tk.x[3]) >= CFG.minSpeed + 2 * (tk.sv || 0);
    if (moving) {
      const [ex, ey] = P(tk.x[0] + tk.x[2], tk.x[1] + tk.x[3]);
      arrow(ctx, px, py, ex, ey, col);
    }
    ctx.beginPath(); ctx.arc(px, py, 6.5, 0, 7); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = '#0b1016'; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = '#fff'; ctx.strokeStyle = 'rgba(0,0,0,0.75)'; ctx.lineWidth = 3;
    const lab = `#${tk.id} ${tk.x[1].toFixed(1)} m`;
    ctx.strokeText(lab, px + 10, py - 8); ctx.fillText(lab, px + 10, py - 8);
  }
}
function arrow(ctx, x1, y1, x2, y2, col) {
  ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  const a = Math.atan2(y2 - y1, x2 - x1);
  ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - 10 * Math.cos(a - 0.45), y2 - 10 * Math.sin(a - 0.45)); ctx.lineTo(x2 - 10 * Math.cos(a + 0.45), y2 - 10 * Math.sin(a + 0.45)); ctx.closePath(); ctx.fill();
}

/* ---------------- HUD + so lieu ---------------- */
function fmt(v, d = 1) { return Number.isFinite(v) ? v.toFixed(d) : '–'; }
function updateHUD() {
  const lv = sim.overall;
  $('lvl').textContent = LNAME[lv];
  $('lvlBox').style.setProperty('--lv', LCOL[lv]);
  const ttc = sim.confirmed && sim.confirmed.filter(t => t.level >= 1 && t.ttc > 0).map(t => t.ttc);
  $('lvlsub').textContent = lv === 3 ? 'Có người trong vùng sát đầu xe' : ttc && ttc.length ? `Va chạm dự kiến sau ${Math.min(...ttc).toFixed(1)} s` : 'Không có người sắp vào đường đi';
  $('spd').textContent = Math.round(sim.bus.s * 3.6);
  const chips = [];
  chips.push(`<span class="chip ${opts.comp ? 'on' : 'off'}">Bù IMU ${opts.comp ? 'BẬT' : 'TẮT'}</span>`);
  if (opts.sync) chips.push('<span class="chip off">Lệch đồng bộ 150 ms</span>');
  if (sim.aeb.active) chips.push('<span class="chip brake">PHANH TỰ ĐỘNG</span>');
  else if (!opts.aeb) chips.push('<span class="chip dim">Phanh tự động TẮT</span>');
  if (sim.manual && key !== 'free') chips.push('<span class="chip dim">Bạn đang lái</span>');
  if (paused) chips.push('<span class="chip dim">Tạm dừng</span>');
  $('chips').innerHTML = chips.join('');
  const trust = clamp(1 - Math.min(sim.vib || 0, 2) / 2, 0, 1);
  $('trust').style.width = (trust * 100).toFixed(0) + '%';
  $('trust').style.background = trust > 0.5 ? 'var(--safe)' : 'var(--stop)';
  const yaw = (sim.yawMeas || 0) * 180 / Math.PI;
  $('yaw').textContent = `${yaw >= 0 ? '+' : ''}${yaw.toFixed(0)}°/s`;
  $('yawbar').style.left = `${50 + clamp(yaw / 60, -1, 1) * 50}%`;
  $('flash').hidden = !(sim.t - sim.lastCollision < 1.6);

  // phu de kich ban
  let cap = '';
  for (const [t, txt] of sim.sc.captions) if (sim.t >= t) cap = txt;
  if (sim.t > sim.sc.duration) cap = 'Kết thúc kịch bản. Bấm R để chạy lại, hoặc giữ ↑ / Q để tự lái tiếp.';
  if ($('scCap').textContent !== cap) $('scCap').textContent = cap;
  const prog = key === 'free' ? 0 : clamp(sim.t / sim.sc.duration, 0, 1);
  $('scProg').style.width = (prog * 100).toFixed(1) + '%';
  $('scProgWrap').hidden = key === 'free';

  const m = sim.summary();
  $('mFA').textContent = m.falseAlarms; $('mNB').textContent = m.needless;
  $('mWarn').textContent = m.hazards ? `${m.inTime}/${m.hazards}` : '–';
  $('mLead').textContent = Number.isFinite(m.lead) ? `${m.lead.toFixed(1)} s` : '–';
  $('mCol').textContent = m.collisions; $('mCol').closest('.stat').classList.toggle('bad', m.collisions > 0);
  $('mErr').textContent = `${fmt(m.errA, 0)}% / ${fmt(m.errC, 0)}%`;
  $('events').innerHTML = sim.M.events.map(e => `<li><time>${e.t.toFixed(1)} s</time>${e.msg}${e.id ? ` · người ${e.id}` : ''}</li>`).join('') || '<li class="muted">Chưa có sự kiện</li>';
  if (!$('toast').hidden && performance.now() > toastT) $('toast').hidden = true;
}

/* ---------------- so sanh (chay nhanh, khong ve) ---------------- */
async function bench() {
  const modal = $('bench'); modal.hidden = false;
  const modes = [['Bật bù IMU', { comp: true }], ['Tắt bù IMU', { comp: false }], ['Bật bù + lệch đồng bộ 150 ms', { comp: true, sync: true }]];
  const keys = ['stop', 'turn', 'child'], N = 6;
  const rows = []; let done = 0; const total = modes.length * keys.length * N;
  $('benchBody').innerHTML = '';
  for (const k of keys) for (const [name, o] of modes) {
    const a = { fa: 0, nb: 0, hz: 0, it: 0, col: 0, lead: [], ea: [], ec: [] };
    for (let i = 0; i < N; i++) {
      const s = new Sim(k, { ...o, seed: 101 + i * 37 });
      while (s.t < s.sc.duration) s.tick();
      const m = s.summary(); a.fa += m.falseAlarms; a.nb += m.needless; a.hz += m.hazards; a.it += m.inTime; a.col += m.collisions;
      if (Number.isFinite(m.lead)) a.lead.push(m.lead); if (Number.isFinite(m.errA)) a.ea.push(m.errA); if (Number.isFinite(m.errC)) a.ec.push(m.errC);
      done++; $('benchProg').style.width = (100 * done / total).toFixed(0) + '%';
      await new Promise(r => setTimeout(r, 0));
    }
    const avg = v => v.length ? v.reduce((p, q) => p + q, 0) / v.length : NaN;
    rows.push([SCENARIOS[k].title, name, a.fa, a.nb, `${a.it}/${a.hz}`, fmt(avg(a.lead)), a.col, `${fmt(avg(a.ea), 0)}% / ${fmt(avg(a.ec), 0)}%`]);
    $('benchBody').innerHTML = rows.map(r => `<tr>${r.map((c, i) => `<td${i > 1 ? ' class="num"' : ''}>${c}</td>`).join('')}</tr>`).join('');
  }
  $('benchNote').textContent = `Mỗi dòng: ${N} lần chạy với nhiễu ngẫu nhiên khác nhau, phanh tự động bật.`;
}

/* ---------------- khoi dong ---------------- */
function fit() {
  const d = $('drvWrap').getBoundingClientRect(), t = $('topWrap').getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
  view.resize(d.width, d.height, t.width, t.height);
  for (const [id, r] of [['drvOv', d], ['topOv', t]]) { const c = $(id); c.width = r.width * dpr; c.height = r.height * dpr; c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0); }
}
function boot() {
  view = new View3D($('drv3d'), $('top3d'));
  document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => start(b.dataset.k)));
  for (const n of ['comp', 'sync', 'aeb', 'gt']) $('t_' + n).addEventListener('click', () => toggle(n));
  document.querySelectorAll('[data-spawn]').forEach(b => b.addEventListener('click', () => spawn(b.dataset.spawn)));
  $('restartBtn').addEventListener('click', () => start(key));
  $('pauseBtn').addEventListener('click', pause);
  $('bumpBtn').addEventListener('click', () => sim.bump());
  $('benchBtn').addEventListener('click', bench);
  $('benchClose').addEventListener('click', () => { $('bench').hidden = true; });
  start(key);
  new ResizeObserver(fit).observe($('drvWrap')); new ResizeObserver(fit).observe($('topWrap'));
  fit();
  let last = performance.now(), acc = 0;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (!paused) { acc += dt; let n = 0; while (acc >= CFG.dtPhys && n < 8) { sim.tick(); acc -= CFG.dtPhys; n++; } if (n === 8) acc = 0; }
    view.sync(sim, paused ? 0 : dt);
    const t = $('topWrap').getBoundingClientRect();
    view.render(t.width / TOP_SPAN, FRONT);
    const d = $('drvWrap').getBoundingClientRect();
    drawDriver($('drvOv').getContext('2d'), d.width, d.height);
    drawTop($('topOv').getContext('2d'), t.width, t.height);
    updateHUD();
    requestAnimationFrame(frame);
  }
  if (reduce) toast('Đang bật chế độ giảm chuyển động của hệ điều hành; mô phỏng vẫn chạy bình thường.');
  requestAnimationFrame(frame);
}
window.addEventListener('DOMContentLoaded', boot);
