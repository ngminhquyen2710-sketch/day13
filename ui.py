"""Phan A - Giao dien: khung camera + ban do nhin tu tren xuong (BEV) + thanh trang thai."""
import math

import cv2
import numpy as np

from risk import COLORS, NAMES, SAFE

FONT = cv2.FONT_HERSHEY_SIMPLEX
VIEW_H = 540
BEV_W = 440
HUD_H = 70
GRAY = (150, 150, 150)
WHITE = (240, 240, 240)
DARK = (28, 28, 32)


def _text(img, s, org, scale=0.5, color=WHITE, thick=1):
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def _bar(img, x, y, w, h, frac, color, label):
    cv2.rectangle(img, (x, y), (x + w, y + h), (70, 70, 70), -1)
    cv2.rectangle(img, (x, y), (x + int(w * max(0, min(1, frac))), y + h), color, -1)
    _text(img, label, (x, y - 4), 0.42, GRAY)


def draw_camera(frame, tracks, res):
    s = VIEW_H / frame.shape[0]
    cam = cv2.resize(frame, (int(frame.shape[1] * s), VIEW_H))
    for t in tracks:
        if not t.matched:
            continue
        r = res.get(t.id, {})
        lv = r.get("level", SAFE)
        x1, y1, x2, y2 = [int(v * s) for v in t.meas.box]
        cv2.rectangle(cam, (x1, y1), (x2, y2), COLORS[lv], 2)
        lab = f"#{t.id} {t.pos[1]:.1f}m"
        if r.get("ttc") is not None and lv > SAFE:
            lab += f" TTC {r['ttc']:.1f}s"
        if t.meas.truncated:
            lab += " (cut?)"
        _text(cam, lab, (x1, max(16, y1 - 6)), 0.55, COLORS[lv], 2)
    return cam


def draw_bev(tracks, res, zone, overall, ranger, rng_m, min_speed, horizon):
    h, w = VIEW_H, BEV_W
    img = np.full((h, w, 3), DARK, np.uint8)
    ppm = (h - 50) / rng_m
    ox, oy = w // 2, h - 30

    def P(x, z):
        return int(ox + x * ppm), int(oy - z * ppm)

    # luoi 1 m
    for k in range(1, int(rng_m) + 1):
        y = P(0, k)[1]
        cv2.line(img, (0, y), (w, y), (55, 55, 60), 1)
        _text(img, f"{k} m", (4, y - 3), 0.4, GRAY)
    # goc nhin camera (FOV)
    half = math.atan(ranger.cx / ranger.f)
    far = rng_m * 1.2
    for sgn in (-1, 1):
        cv2.line(img, P(0, 0), P(sgn * far * math.tan(half), far), (90, 90, 100), 1, cv2.LINE_AA)
    # hanh lang duong di cua xe
    cv2.rectangle(img, P(zone["px0"], zone["pz1"]), P(zone["px1"], 0), (110, 110, 120), 1,
                  cv2.LINE_AA)
    _text(img, "bus path", (P(zone["px1"], zone["pz1"])[0] + 4, P(0, zone["pz1"])[1] + 12),
          0.4, GRAY)
    # vung nguy hiem
    col = COLORS[overall] if overall > SAFE else (90, 140, 90)
    over = img.copy()
    cv2.rectangle(over, P(zone["x0"], zone["z1"]), P(zone["x1"], zone["z0"]), col, -1)
    img = cv2.addWeighted(over, 0.28, img, 0.72, 0)
    cv2.rectangle(img, P(zone["x0"], zone["z1"]), P(zone["x1"], zone["z0"]), col, 2)
    # xe buyt (camera)
    cv2.rectangle(img, (ox - 34, oy), (ox + 34, h - 4), (200, 160, 60), -1)
    _text(img, "BUS", (ox - 17, h - 10), 0.45, (20, 20, 20))
    if zone["turn"]:
        _text(img, f"TURN {zone['turn']}: zone expanded", (8, 22), 0.55, (0, 210, 255), 2)

    for t in tracks:
        r = res.get(t.id)
        if r is None:
            continue
        c = COLORS[r["level"]]
        # elip bat dinh 2-sigma
        cov = t.P[:2, :2]
        vals, vecs = np.linalg.eigh(cov)
        vals = np.maximum(vals, 1e-6)
        ang = math.degrees(math.atan2(vecs[1, 1], vecs[0, 1]))
        axes = (max(2, int(2 * math.sqrt(vals[1]) * ppm)), max(2, int(2 * math.sqrt(vals[0]) * ppm)))
        cv2.ellipse(img, P(*t.pos), axes, -ang, 0, 360, c, 1, cv2.LINE_AA)
        # do thô (raw) vs Kalman
        if t.matched:
            cv2.drawMarker(img, P(t.meas.X, t.meas.Z), GRAY, cv2.MARKER_TILTED_CROSS, 8, 1)
        cv2.circle(img, P(*t.pos), 6, c, -1, cv2.LINE_AA)
        cv2.circle(img, P(*r["p_c"]), 4, c, 1, cv2.LINE_AA)     # vi tri than trong
        # van toc 1 s + quy dao du bao
        if r["speed"] >= min_speed:
            cv2.arrowedLine(img, P(*t.pos), P(*(t.pos + t.vel)), c, 2, cv2.LINE_AA, tipLength=0.25)
            for tt in np.arange(0.25, horizon + 1e-9, 0.25):
                cv2.circle(img, P(*(r["p_c"] + r["v_c"] * tt)), 1, c, -1)
        _text(img, f"#{t.id}", (P(*t.pos)[0] + 8, P(*t.pos)[1] - 8), 0.45, c)
    return img


def draw_hud(width, hud):
    img = np.full((HUD_H, width, 3), (18, 18, 20), np.uint8)
    lv = hud["overall"]
    banner = NAMES[lv]
    if hud.get("min_ttc") is not None and lv in (1, 2):
        banner += f"  TTC {hud['min_ttc']:.1f}s"
    cv2.rectangle(img, (0, 0), (300, HUD_H), COLORS[lv], -1)
    cv2.putText(img, banner, (14, 46), FONT, 1.0, (15, 15, 15), 3, cv2.LINE_AA)

    x = 316
    _text(img, f"FPS {hud['fps']:.1f}  proc {hud['proc_ms']:.0f} ms  f={hud['focal']:.0f}px "
               f"HFOV {hud['hfov']:.0f}deg", (x, 22), 0.5)
    _text(img, f"IMU: {hud['imu_status']}  {hud['imu_hz']:.0f} Hz  lag {hud['latency_ms']:+.0f} ms",
          (x, 44), 0.5)
    comp = "IMU COMP: ON" if hud["comp_on"] else "IMU COMP: OFF"
    _text(img, comp, (x, 64), 0.55, (90, 230, 90) if hud["comp_on"] else (60, 60, 240), 2)

    bx = width - 330
    yaw = hud["yaw_dps"]
    _bar(img, bx, 18, 140, 10, 0.5 + yaw / 180.0, (0, 210, 255), f"yaw {yaw:+.0f} deg/s")
    _bar(img, bx, 50, 140, 10, 1.0 - min(hud["vib"], 2) / 2, (90, 200, 90) if hud["vib"] < 1 else
         (50, 50, 235), "camera trust")
    tags = []
    if hud.get("recording"):
        tags.append("REC")
    if hud.get("marker"):
        tags.append(f"trial {hud['marker']}")
    _text(img, "  ".join(tags), (width - 170, 26), 0.55, (60, 60, 240), 2)
    return img


HELP = [
    "q quit | h help",
    "c calibrate focal (1 person at calib distance)",
    "i toggle IMU compensation",
    "b gyro bias (hold still) | t detect yaw axis (after turning RIGHT)",
    "l latency test (tap table 5 s)",
    "d distance test (30 frames)",
    "m next trial marker | r record video",
    "[ ] sim turn | v sim shake",
]


def render(frame, tracks, res, zone, overall, ranger, cfg, hud, toast=None, show_help=False,
           help_lines=None):
    lines = help_lines or HELP
    cam = draw_camera(frame, tracks, res)
    bev = draw_bev(tracks, res, zone, overall, ranger, cfg["ui"]["bev_range_m"],
                   cfg["risk"]["min_speed_mps"], cfg["risk"]["horizon_s"])
    body = np.hstack([cam, bev])
    top = draw_hud(body.shape[1], hud)
    canvas = np.vstack([top, body])
    if show_help:
        over = canvas.copy()
        cv2.rectangle(over, (0, HUD_H), (600, HUD_H + 24 * len(lines) + 16), (0, 0, 0), -1)
        canvas = cv2.addWeighted(over, 0.6, canvas, 0.4, 0)
        y = HUD_H + 30
        for line in lines:
            _text(canvas, line, (14, y), 0.55, WHITE)
            y += 24
    if toast:
        _text(canvas, toast, (14, canvas.shape[0] - 16), 0.65, (0, 230, 255), 2)
    return canvas
