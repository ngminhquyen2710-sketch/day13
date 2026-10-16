"""Mo phong VinBus Blind Spot Guard - demo khong can webcam, khong can dien thoai.

The gioi ao: xe buyt (camera dau xe + IMU) tren mot con duong, co nguoi di bo.
Moi thu sau buoc "camera" chay DUNG code that cua he thong:
    box pinhole (vision.py) -> Kalman + bu IMU (tracker.py) -> canh bao (risk.py) -> giao dien (ui.py)
Vi biet vi tri THAT cua moi nguoi, mo phong tu tinh so lieu Bang chung:
    bao dong gia, canh bao kip thoi, sai so khoang cach.

Chay:
    python simulate.py                 # tuong tac, tu chay kich ban demo (phim p de dung/chay)
    python simulate.py --manual        # tu dieu khien hoan toan bang phim
    python simulate.py --compare       # chay nhanh nhieu lan, in bang so sanh co/khong bu IMU
"""
import argparse
import math
import os
import time

import cv2
import numpy as np
import yaml

import ui
from imu import IMUBase
from risk import DANGER, RiskAssessor, SAFE
from tracker import MultiTracker
from vision import PinholeRanger

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 960, 540
CAM_H = 1.2                 # chieu cao camera so voi mat duong (m)
DT = 1.0 / 30
TURN_RATE = math.radians(45)
SYNC_ERR = 0.15             # loi dong bo thoi gian IMU khi bat phim k (s)

SIM_HELP = [
    "p auto scenario on/off | q quit | h help",
    "1 cross from right | 2 cross from left | 3 static person",
    "4 child crossing | 5 walker on sidewalk | x clear",
    "a / d  turn left / right (1 s)   w / s  speed +/-",
    "v road bump | k IMU sync error 150 ms",
    "i IMU compensation | g ground truth | z reset stats | r record",
]


def rot(theta):
    """Ma tran doi tu the gioi sang he xe khi xe da quay phai mot goc theta."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]])


class WorldIMU(IMUBase):
    """IMU nhan du lieu tu the gioi ao; dung dong ho mo phong thay cho dong ho may."""
    name = "sim-world"

    def __init__(self, vib_threshold):
        super().__init__(yaw_axis="z", yaw_sign=1, latency_s=0.0, vib_threshold=vib_threshold)
        self.clock = 0.0
        self.bias_ready = True
        self.status = "simulated gyro"
        self.connected = True

    def vibration(self, win=0.5):
        arr = self.window(self.clock - win, self.clock)
        if len(arr) < 6:
            return 0.0
        mag = np.linalg.norm(arr[:, 1:4] - self.bias, axis=1)
        return float(np.std(np.diff(mag)) / math.sqrt(2) / self.vib_threshold)

    def calibrate_bias(self, win=1.0):
        arr = self.window(self.clock - win, self.clock)
        if len(arr) < 10:
            return None
        self.bias = arr[:, 1:4].mean(axis=0)
        return 0.0

    def rate_hz(self):
        return float(len(self.window(self.clock - 1.0, self.clock)))


class Ped:
    _n = 0

    def __init__(self, pos_w, vel_w, height, kind, color):
        Ped._n += 1
        self.id = Ped._n
        self.p = np.array(pos_w, float)
        self.v = np.array(vel_w, float)
        self.h = height
        self.kind = kind            # static | cross | child | walk
        self.color = color
        self.phase = np.random.uniform(0, 6.28)
        self.first_warn = None
        self.entry = None


class World:
    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.rng = rng
        self.t = 0.0
        self.b = np.zeros(2)            # vi tri xe (the gioi)
        self.theta = 0.0                # goc xe da quay phai (rad)
        self.yaw_rate = 0.0
        self.turn_target = 0.0
        self.turn_until = 0.0
        self.speed = 0.0
        self.bump_until = 0.0
        self.peds = []
        self.gyro_bias = np.array([0.004, -0.006, 0.02])

    # ---- doi he toa do ----
    def to_bus(self, p_w):
        return rot(self.theta) @ (np.asarray(p_w) - self.b)

    def to_world(self, p_b):
        return self.b + rot(-self.theta) @ np.asarray(p_b)

    def vec_to_world(self, v_b):
        return rot(-self.theta) @ np.asarray(v_b)

    # ---- tao nguoi (toa do theo he xe luc tao) ----
    def spawn(self, kind, side=None, z=None, speed=None):
        r = self.rng
        side = side if side is not None else (1 if r.random() < 0.5 else -1)
        colors = [(60, 60, 200), (200, 120, 40), (40, 160, 60), (160, 60, 160), (30, 140, 220)]
        col = colors[r.integers(len(colors))]
        if kind == "static":
            pb = (side * r.uniform(1.3, 1.9), z or r.uniform(2.6, 4.2))
            vb, h = (0, 0), r.uniform(1.55, 1.8)
        elif kind == "walk":
            pb, vb, h = (side * 1.9, z or 6.0), (0, -(speed or 1.0)), r.uniform(1.55, 1.8)
        elif kind == "child":
            pb, vb, h = (side * 2.8, z or 2.6), (-side * (speed or 1.1), 0), r.uniform(1.05, 1.2)
        else:
            pb, vb, h = (side * 3.0, z or r.uniform(2.6, 3.6)), (-side * (speed or 1.2), 0), \
                r.uniform(1.55, 1.85)
        self.peds.append(Ped(self.to_world(pb), self.vec_to_world(vb), h, kind, col))

    def turn(self, direction, duration=1.0):
        self.turn_target = direction * TURN_RATE
        self.turn_until = self.t + duration

    def bump(self):
        self.bump_until = self.t + 0.8

    # ---- buoc mo phong ----
    def step(self, imu, sync_err):
        if self.t >= self.turn_until:
            self.turn_target = 0.0
        n = 8
        for k in range(n):
            self.yaw_rate += 0.25 * (self.turn_target - self.yaw_rate)
            tau = self.t + (k + 1) * DT / n
            g = self.rng.normal(0, 0.01, 3) + self.gyro_bias
            g[2] += self.yaw_rate
            if tau < self.bump_until:
                g += self.rng.normal(0, 1.0, 3)
            imu.push(tau + sync_err, *g)
            self.theta += self.yaw_rate * DT / n
        heading = np.array([math.sin(self.theta), math.cos(self.theta)])
        self.b = self.b + heading * self.speed * DT
        for p in self.peds:
            p.p = p.p + p.v * DT
        self.t += DT
        imu.clock = self.t
        # bo nguoi da di xa
        self.peds = [p for p in self.peds if np.linalg.norm(self.to_bus(p.p)) < 14]

    def shake(self):
        if self.t < self.bump_until:
            return self.rng.normal(0, 5, 2)
        return np.zeros(2)


# ===================== ve khung hinh camera =====================
class Renderer:
    def __init__(self, f):
        self.f = f
        self.cx, self.cy = W / 2, H / 2
        bg = np.zeros((H, W, 3), np.uint8)
        for y in range(H):
            if y < self.cy:
                a = y / self.cy
                bg[y] = (235 - 40 * a, 205 - 15 * a, 170 + 30 * a)
            else:
                a = (y - self.cy) / (H - self.cy)
                bg[y] = (95 - 25 * a, 98 - 25 * a, 100 - 25 * a)
        self.bg = bg

    def proj(self, pb, y=0.0):
        """Chieu diem (x, z) cao y met so voi mat duong len anh."""
        x, z = pb
        if z < 0.35:
            return None
        return (self.cx + self.f * x / z, self.cy + self.f * (CAM_H - y) / z)

    def person_box(self, pb, h):
        x, z = pb
        if z < 0.5:
            return None
        u = self.cx + self.f * x / z
        vf = self.cy + self.f * CAM_H / z
        hp = self.f * h / z
        w = 0.38 * hp
        return (u - w / 2, vf - hp, u + w / 2, vf)

    def polyline(self, img, world, pts_w, color, thick):
        prev = None
        for pw in pts_w:
            q = self.proj(world.to_bus(pw))
            if q is not None and prev is not None and abs(q[0]) < 5 * W:
                cv2.line(img, (int(prev[0]), int(prev[1])), (int(q[0]), int(q[1])), color, thick,
                         cv2.LINE_AA)
            prev = q

    def draw(self, world):
        img = self.bg.copy()
        bz = world.b[1]
        zs = np.arange(math.floor(bz) - 6, bz + 50, 0.5)
        bx = world.b[0]
        # le duong va vach giua (co dinh trong the gioi => thay ro khi xe quay)
        for xr in (-3.2, 3.2):
            self.polyline(img, world, [(bx * 0 + xr, z) for z in zs], (200, 200, 200), 2)
        for z0 in np.arange(math.floor(bz / 4) * 4 - 8, bz + 50, 4):
            self.polyline(img, world, [(0, z0), (0, z0 + 1.6)], (60, 220, 240), 2)
        # vat the: cot den + nguoi, ve xa truoc gan sau
        items = []
        for z0 in np.arange(math.floor(bz / 5) * 5 - 10, bz + 50, 5):
            for xr in (-4.0, 4.0):
                pb = world.to_bus((xr, z0))
                if pb[1] > 0.5:
                    items.append((pb[1], "pole", pb, None))
        for p in world.peds:
            pb = world.to_bus(p.p)
            if pb[1] > 0.5:
                items.append((pb[1], "ped", pb, p))
        items.sort(key=lambda k: -k[0])
        for z, kind, pb, p in items:
            if kind == "pole":
                a, b = self.proj(pb, 0), self.proj(pb, 4.5)
                if a and b and -50 < a[0] < W + 50:
                    th = max(1, int(self.f * 0.12 / z))
                    cv2.line(img, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (70, 70, 80), th)
                    cv2.circle(img, (int(b[0]), int(b[1])), max(2, th), (120, 230, 250), -1)
            else:
                self.draw_person(img, pb, p, world.t)
        dx, dy = world.shake()
        if dx or dy:
            img = cv2.warpAffine(img, np.float32([[1, 0, dx], [0, 1, dy]]), (W, H),
                                 borderMode=cv2.BORDER_REPLICATE)
        return img, (dx, dy)

    def draw_person(self, img, pb, p, t):
        box = self.person_box(pb, p.h)
        if box is None:
            return
        x1, y1, x2, y2 = box
        hp = y2 - y1
        u = (x1 + x2) / 2
        moving = np.linalg.norm(p.v) > 0.1
        sw = 0.12 * hp * math.sin(t * 7 + p.phase) if moving else 0.0
        hip = y1 + 0.52 * hp
        lw = max(1, int(hp * 0.06))
        for s in (-1, 1):
            cv2.line(img, (int(u), int(hip)), (int(u + s * sw), int(y2)), (40, 40, 50), lw, cv2.LINE_AA)
        tw = 0.30 * hp
        cv2.rectangle(img, (int(u - tw / 2), int(y1 + 0.17 * hp)), (int(u + tw / 2), int(hip)),
                      p.color, -1)
        for s in (-1, 1):
            cv2.line(img, (int(u + s * tw / 2), int(y1 + 0.2 * hp)),
                     (int(u + s * tw / 2 - s * sw * 0.6), int(y1 + 0.5 * hp)), p.color, lw,
                     cv2.LINE_AA)
        cv2.circle(img, (int(u), int(y1 + 0.085 * hp)), max(2, int(0.085 * hp)), (150, 180, 220), -1,
                   cv2.LINE_AA)


# ===================== kich ban demo =====================
SCRIPT = [
    (0.0, "clear"),
    (0.2, "static", dict(side=1, z=3.0)), (0.2, "static", dict(side=-1, z=3.5)),
    (0.2, "static", dict(side=1, z=4.3)),
    (2.5, "turn", 1), (4.5, "turn", -1), (6.5, "turn", -1), (8.5, "turn", 1),
    (10.5, "cross", dict(side=1, z=3.0)),
    (14.0, "child", dict(side=-1, z=2.6)),
    (17.0, "bump", None),
    (18.0, "cross", dict(side=-1, z=3.4)), (18.6, "turn", 1), (20.6, "turn", -1),
]
SCRIPT_LEN = 24.0
CAPTIONS = [
    (0.0, "Scene 1: 3 people standing still beside the road"),
    (2.5, "Scene 2: bus turns - standing people must NOT trigger alarms (try i)"),
    (10.5, "Scene 3: adult crossing in front of the bus"),
    (14.0, "Scene 4: child crossing (failure case: short => looks far away)"),
    (17.0, "Scene 5: road bump - camera trust drops"),
    (18.0, "Scene 6: person crossing while bus turns right"),
]


class Scenario:
    def __init__(self):
        self.t0 = 0.0
        self.i = 0

    def restart(self, t):
        self.t0, self.i = t, 0

    def caption(self, world):
        rel = world.t - self.t0
        cur = ""
        for t, txt in CAPTIONS:
            if t <= rel:
                cur = txt
        return cur

    def update(self, world):
        rel = world.t - self.t0
        while self.i < len(SCRIPT) and SCRIPT[self.i][0] <= rel:
            ev = SCRIPT[self.i]
            if ev[1] == "clear":
                world.peds.clear()
            elif ev[1] == "turn":
                world.turn(ev[2])
            elif ev[1] == "bump":
                world.bump()
            else:
                world.spawn(ev[1], **ev[2])
            self.i += 1
        if rel >= SCRIPT_LEN:
            self.restart(world.t)
            return True
        return False


# ===================== so lieu (ground truth) =====================
class Metrics:
    def __init__(self, risk):
        self.risk = risk
        self.reset()

    def reset(self):
        self.false_alarms = 0
        self.leads = []          # thoi gian canh bao truoc khi nguoi cat vao duong di (s)
        self.err = {"adult": [], "child": []}
        self.prev = {}

    def update(self, world, tracks, res):
        peds = {p.id: p for p in world.peds}
        for t in tracks:
            gid = getattr(t, "gt_id", None)
            p = peds.get(gid)
            lv = res[t.id]["level"]
            if p is not None:
                pb = world.to_bus(p.p)
                if t.matched:
                    self.err["child" if p.kind == "child" else "adult"].append(
                        abs(t.pos[1] - pb[1]) / max(pb[1], 0.5))
                if lv >= DANGER and self.prev.get(t.id, SAFE) < DANGER:
                    if p.kind == "static":
                        self.false_alarms += 1
                    elif p.kind in ("cross", "child") and p.first_warn is None and p.entry is None:
                        p.first_warn = world.t
            self.prev[t.id] = lv
        zone = dict(px0=-self.risk.hw, px1=self.risk.hw, pz1=self.risk.path_len)
        for p in world.peds:
            if p.kind in ("cross", "child") and p.entry is None:
                pb = world.to_bus(p.p)
                if RiskAssessor.in_path(pb, zone):
                    p.entry = world.t
                    self.leads.append(None if p.first_warn is None else p.entry - p.first_warn)

    def summary(self):
        ok = [l for l in self.leads if l is not None and l >= 0.5]
        got = [l for l in self.leads if l is not None]
        ea = np.mean(self.err["adult"]) * 100 if self.err["adult"] else float("nan")
        ec = np.mean(self.err["child"]) * 100 if self.err["child"] else float("nan")
        return dict(false_alarms=self.false_alarms, crossers=len(self.leads), in_time=len(ok),
                    mean_lead=float(np.mean(got)) if got else float("nan"),
                    err_adult=ea, err_child=ec)

    def text(self):
        s = self.summary()
        def fmt(v, spec):
            return "-" if v != v else format(v, spec)       # NaN -> "-"
        return (f"GROUND TRUTH | false alarms (static people): {s['false_alarms']} | "
                f"crossers warned >=0.5s early: {s['in_time']}/{s['crossers']} "
                f"(avg lead {fmt(s['mean_lead'], '.1f')}s) | dist err adult "
                f"{fmt(s['err_adult'], '.0f')}% child {fmt(s['err_child'], '.0f')}%")


# ===================== vong chay =====================
def build(cfg, seed):
    rng = np.random.default_rng(seed)
    world = World(cfg, rng)
    f = 0.55 * W                      # camera goc rong (~82 do), nhu camera diem mu that
    ranger = PinholeRanger(W, H, f, cfg["person"]["height_m"], cfg["tracking"]["pixel_noise"])
    imu = WorldIMU(cfg["imu"]["vibration_threshold"])
    tracker = MultiTracker(cfg["tracking"]["accel_noise"], cfg["tracking"]["gate_m"],
                           cfg["tracking"]["max_missed"], cfg["tracking"]["confirm_hits"])
    risk = RiskAssessor(cfg["risk"], cfg["person"]["height_m"], cfg["person"]["height_min_m"],
                        cfg["imu"]["turn_threshold_dps"])
    return world, Renderer(f), ranger, imu, tracker, risk, Metrics(risk)


def perceive(world, rend, ranger, shake, noise_scale):
    """Gia lap detector: box tu hinh chieu that + nhieu pixel + thinh thoang bo sot."""
    meas = []
    for p in world.peds:
        pb = world.to_bus(p.p)
        box = rend.person_box(pb, p.h)
        if box is None or world.rng.random() < 0.04:
            continue
        sp = 2.0 * noise_scale
        b = np.array(box) + world.rng.normal(0, sp, 4) + [shake[0], shake[1], shake[0], shake[1]]
        uc = (b[0] + b[2]) / 2
        if uc < 0 or uc > W or b[3] < 0:
            continue
        b = (max(b[0], 0), max(b[1], 0), min(b[2], W - 1), min(b[3], H - 1))
        if b[3] - b[1] < 12:
            continue
        m = ranger.measure(b, 0.85, noise_scale)
        m.gt_id = p.id
        meas.append(m)
    return meas


def sim_step(world, rend, ranger, imu, tracker, risk, metrics, comp_on, sync_err, render=True):
    world.step(imu, sync_err)
    if not getattr(imu, "calibrated", False) and world.t >= 1.0:
        imu.calibrate_bias(0.9)          # xe dung yen giay dau tien => uoc luong bias con quay
        imu.calibrated = True
    frame, shake = rend.draw(world) if render else (None, world.shake())
    vib = imu.vibration()
    noise_scale = 1.0 + 2.0 * min(vib, 3.0)
    meas = perceive(world, rend, ranger, shake, noise_scale)
    dtheta = imu.delta_yaw(world.t - DT, world.t) if comp_on else 0.0
    tracker.step(meas, DT, dtheta)
    for t in tracker.tracks:
        if t.matched:
            t.gt_id = getattr(t.meas, "gt_id", None)
    tracks = tracker.confirmed()
    yaw_rate = imu.yaw_rate(world.t)
    res, zone, overall = risk.assess(tracks, yaw_rate)
    metrics.update(world, tracks, res)
    return frame, tracks, res, zone, overall, yaw_rate, vib


def draw_ground_truth(canvas, world, cfg, cam_w):
    rng_m = cfg["ui"]["bev_range_m"]
    ppm = (ui.VIEW_H - 50) / rng_m
    ox, oy = cam_w + ui.BEV_W // 2, ui.HUD_H + ui.VIEW_H - 30
    for p in world.peds:
        x, z = world.to_bus(p.p)
        if 0 < z < rng_m + 0.5:
            c = (int(ox + x * ppm), int(oy - z * ppm))
            if cam_w < c[0] < canvas.shape[1]:
                cv2.rectangle(canvas, (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), (255, 255, 255), 1)


def interactive(cfg, args):
    world, rend, ranger, imu, tracker, risk, metrics = build(cfg, args.seed)
    scen = Scenario()
    auto = not args.manual
    comp_on, show_gt, show_help, sync_on = True, True, True, False
    recording, writer = False, None
    toast, toast_until = "Auto scenario running - press p to take control", 5.0
    fps, t_prev = 0.0, time.perf_counter()
    win = "VinBus Blind Spot Guard - SIMULATION"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)

    def say(msg):
        nonlocal toast, toast_until
        toast, toast_until = msg, world.t + 3.0

    while True:
        tic = time.perf_counter()
        if auto and scen.update(world):
            say("Scenario restarted")
        frame, tracks, res, zone, overall, yaw_rate, vib = sim_step(
            world, rend, ranger, imu, tracker, risk, metrics, comp_on,
            SYNC_ERR if sync_on else 0.0)
        proc_ms = (time.perf_counter() - tic) * 1000
        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3) if fps else 1 / max(now - t_prev, 1e-3)
        t_prev = now
        ttcs = [r["ttc"] for r in res.values() if r["ttc"] is not None and r["level"] > SAFE]
        status = "SIM gyro" + (" | SYNC ERROR 150ms" if sync_on else "")
        status += f" | speed {world.speed:.1f} m/s" + (" | AUTO" if auto else " | MANUAL")
        hud = dict(overall=overall, min_ttc=min(ttcs) if ttcs else None, fps=fps, proc_ms=proc_ms,
                   focal=ranger.f, hfov=ranger.hfov_deg(), imu_status=status,
                   imu_hz=imu.rate_hz(), latency_ms=0.0, comp_on=comp_on,
                   yaw_dps=math.degrees(yaw_rate), vib=vib, recording=recording, marker=0)
        msg = toast if world.t < toast_until else (scen.caption(world) if auto else None)
        canvas = ui.render(frame, tracks, res, zone, overall, ranger, cfg, hud, msg, show_help,
                           SIM_HELP)
        if show_gt:
            draw_ground_truth(canvas, world, cfg, canvas.shape[1] - ui.BEV_W)
        strip = np.full((30, canvas.shape[1], 3), (18, 18, 20), np.uint8)
        ui._text(strip, metrics.text(), (10, 20), 0.5, (230, 230, 230))
        canvas = np.vstack([canvas, strip])
        if recording:
            if writer is None:
                path = os.path.join(HERE, "logs", time.strftime("sim_%Y%m%d_%H%M%S.mp4"))
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30,
                                         (canvas.shape[1], canvas.shape[0]))
                print("Ghi video:", path)
            writer.write(canvas)
        cv2.imshow(win, canvas)

        wait = max(1, int((DT - (time.perf_counter() - tic)) * 1000))
        key = cv2.waitKey(wait) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("h"):
            show_help = not show_help
        elif key == ord("p"):
            auto = not auto
            if auto:
                scen.restart(world.t)
            say("Auto scenario " + ("ON" if auto else "OFF - manual control"))
        elif key == ord("i"):
            comp_on = not comp_on
            say("IMU compensation " + ("ON" if comp_on else "OFF"))
        elif key == ord("k"):
            sync_on = not sync_on
            say("IMU sync error " + ("ON (150 ms)" if sync_on else "OFF"))
        elif key == ord("g"):
            show_gt = not show_gt
        elif key == ord("z"):
            metrics.reset()
            say("Stats reset")
        elif key == ord("x"):
            world.peds.clear()
        elif key == ord("1"):
            world.spawn("cross", side=1)
        elif key == ord("2"):
            world.spawn("cross", side=-1)
        elif key == ord("3"):
            world.spawn("static")
        elif key == ord("4"):
            world.spawn("child")
        elif key == ord("5"):
            world.spawn("walk")
        elif key == ord("a"):
            world.turn(-1)
        elif key == ord("d"):
            world.turn(1)
        elif key == ord("w"):
            world.speed = min(3.0, world.speed + 0.5)
        elif key == ord("s"):
            world.speed = max(0.0, world.speed - 0.5)
        elif key == ord("v"):
            world.bump()
        elif key == ord("r"):
            recording = not recording
            if not recording and writer is not None:
                writer.release()
                writer = None
            say("Recording " + ("ON" if recording else "OFF (saved in logs/)"))

    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()
    print(metrics.text())


def compare(cfg, args):
    """Chay kich ban demo nhieu lan (nhanh, khong ve) cho tung che do, in bang so sanh."""
    modes = [("Bu IMU: TAT", False, 0.0), ("Bu IMU: BAT", True, 0.0),
             ("Bu IMU: BAT + lech dong bo 150 ms", True, SYNC_ERR)]
    rows = []
    for name, comp, serr in modes:
        tot = dict(false_alarms=0, crossers=0, in_time=0, leads=[], ea=[], ec=[])
        for run in range(args.runs):
            world, rend, ranger, imu, tracker, risk, metrics = build(cfg, args.seed + run)
            scen = Scenario()
            while world.t < SCRIPT_LEN - 0.1:
                scen.update(world)
                sim_step(world, rend, ranger, imu, tracker, risk, metrics, comp, serr, render=False)
            s = metrics.summary()
            tot["false_alarms"] += s["false_alarms"]
            tot["crossers"] += s["crossers"]
            tot["in_time"] += s["in_time"]
            tot["leads"] += [l for l in metrics.leads if l is not None]
            tot["ea"] += metrics.err["adult"]
            tot["ec"] += metrics.err["child"]
        rows.append((name, tot))
    n_static = 3 * args.runs
    print(f"\nKich ban demo x {args.runs} lan (moi lan: 3 nguoi dung yen + xe re 6 lan, "
          f"3 nguoi cat ngang, 1 lan xoc)\n")
    print(f"{'Che do':<36}{'Bao dong gia':>14}{'Canh bao kip thoi':>20}{'Lead TB':>10}"
          f"{'Sai so KC nguoi lon':>22}{'tre em':>9}")
    for name, t in rows:
        lead = np.mean(t["leads"]) if t["leads"] else float("nan")
        print(f"{name:<36}{t['false_alarms']:>14}{t['in_time']:>14}/{t['crossers']:<5}"
              f"{lead:>9.2f}s{np.mean(t['ea'])*100:>21.1f}%{np.mean(t['ec'])*100:>8.0f}%")
    print(f"\n(Bao dong gia = so lan DANGER/STOP tren {n_static} luot nguoi dung yen; "
          "canh bao kip thoi = DANGER truoc khi nguoi buoc vao duong di it nhat 0,5 s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--manual", action="store_true", help="khong chay kich ban tu dong")
    ap.add_argument("--compare", action="store_true", help="in bang so sanh, khong mo cua so")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if args.compare:
        compare(cfg, args)
    else:
        interactive(cfg, args)


if __name__ == "__main__":
    main()
