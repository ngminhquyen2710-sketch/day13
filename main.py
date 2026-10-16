"""VinBus Blind Spot Guard - canh bao nguoi cat ngang diem mu (camera + IMU dien thoai).

Chay:
  python main.py                         # webcam + Phyphox (theo config.yaml)
  python main.py --imu sim               # webcam + IMU gia lap bang phim
  python main.py --source video.mp4 --imu sim --loop
  python main.py --source video.mp4 --headless   # khong mo cua so, ghi ra logs/.../output.mp4
"""
import argparse
import json
import math
import os
import sys
import threading
import time

import cv2
import numpy as np
import yaml

import ui
from imu import AXES, AXIS_NAMES, SimIMU, make_imu
from latency import LatencyTest
from recorder import Recorder
from risk import NAMES, RiskAssessor, SAFE, DANGER
from tracker import MultiTracker
from vision import PersonDetector, PinholeRanger

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB_FILE = os.path.join(HERE, "calib.json")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_calib(d):
    with open(CALIB_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def open_source(src, w, h):
    if isinstance(src, str) and src.strip().isdigit():
        src = int(src)
    if isinstance(src, int):
        cap = None
        if os.name == "nt":
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = None
        if cap is None:
            cap = cv2.VideoCapture(src)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        is_file = False
    else:
        cap = cv2.VideoCapture(src)
        is_file = True
    if not cap.isOpened():
        sys.exit(f"Khong mo duoc nguon video: {src}")
    return cap, is_file


class Beeper:
    def __init__(self, enabled):
        self.enabled = enabled
        self.last = 0.0

    def __call__(self, level):
        now = time.monotonic()
        if not self.enabled or now - self.last < 0.6:
            return
        self.last = now
        if os.name == "nt":
            import winsound
            freq = 1800 if level >= 3 else 1200
            threading.Thread(target=winsound.Beep, args=(freq, 180), daemon=True).start()
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--source", help="0 = webcam, hoac duong dan video")
    ap.add_argument("--imu", choices=["phyphox", "sim", "none"])
    ap.add_argument("--url", help="URL Phyphox (ghi de config)")
    ap.add_argument("--loop", action="store_true", help="lap lai video")
    ap.add_argument("--headless", action="store_true", help="khong mo cua so, tu ghi video")
    ap.add_argument("--no-comp", action="store_true", help="tat bu IMU luc khoi dong")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if args.url:
        cfg["imu"]["phyphox_url"] = args.url
    calib = load_json(CALIB_FILE)

    src = args.source if args.source is not None else cfg["camera"]["source"]
    cap, is_file = open_source(src, cfg["camera"]["width"], cfg["camera"]["height"])
    ok, frame = cap.read()
    if not ok:
        sys.exit("Khong doc duoc khung hinh dau tien")
    H, W = frame.shape[:2]
    vid_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not (1 < vid_fps < 240):
        vid_fps = 30.0

    focal = calib.get("focal_px", {}).get(f"{W}x{H}") or cfg["camera"]["focal_px"]
    ranger = PinholeRanger(W, H, focal, cfg["person"]["height_m"], cfg["tracking"]["pixel_noise"])
    print("Dang tai model YOLO...")
    detector = PersonDetector(cfg["detector"]["model"], cfg["detector"]["conf"], cfg["detector"]["imgsz"])

    imu = make_imu(cfg, args.imu)
    if not isinstance(imu, SimIMU):
        if "yaw_axis" in calib:
            imu.yaw_axis = AXES[calib["yaw_axis"]]
            imu.yaw_sign = calib.get("yaw_sign", 1)
        if "latency_s" in calib:
            imu.latency = calib["latency_s"]
    imu.start()

    tracker = MultiTracker(cfg["tracking"]["accel_noise"], cfg["tracking"]["gate_m"],
                           cfg["tracking"]["max_missed"], cfg["tracking"]["confirm_hits"])
    risk = RiskAssessor(cfg["risk"], cfg["person"]["height_m"], cfg["person"]["height_min_m"],
                        cfg["imu"]["turn_threshold_dps"])
    rec = Recorder(os.path.join(HERE, "logs"))
    lat = LatencyTest()
    beep = Beeper(cfg["ui"].get("beep", True) and not args.headless)
    print(f"Log: {rec.dir}")

    comp_on = not args.no_comp
    marker = 0
    show_help = True
    toast, toast_until = "Press h to hide help", time.monotonic() + 6
    writer = None
    recording = args.headless
    dist = None
    prev_levels = {}
    fps = 0.0
    t_prev = time.monotonic()
    t_video = 0.0

    def say(msg, sec=4.0):
        nonlocal toast, toast_until
        toast, toast_until = msg, time.monotonic() + sec
        print(msg)

    if not args.headless:
        cv2.namedWindow("VinBus Blind Spot Guard", cv2.WINDOW_NORMAL)

    first = True
    while True:
        if not first:
            ok, frame = cap.read()
            if not ok:
                if is_file and args.loop:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break
        first = False
        now = time.monotonic()
        if is_file:
            dt = 1.0 / vid_fps
            t_video += dt
        else:
            dt = min(max(now - t_prev, 0.005), 0.2)
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - t_prev, 1e-3)) if fps else 1.0 / max(now - t_prev, 1e-3)
        t_prev = now
        tic = time.perf_counter()

        # --- cam bien ---
        vib = imu.vibration()
        noise_scale = 1.0 + 2.0 * min(vib, 3.0)          # xe rung => camera kem tin cay
        dets = detector(frame)
        meas = [ranger.measure(b, c, noise_scale) for b, c in dets]
        L = imu.latency
        dtheta = imu.delta_yaw(now - dt - L, now - L) if comp_on else 0.0
        yaw_rate = imu.yaw_rate(now - L)

        # --- tracking + rui ro ---
        tracker.step(meas, dt, dtheta)
        tracks = tracker.confirmed()
        res, zone, overall = risk.assess(tracks, yaw_rate)
        proc_ms = (time.perf_counter() - tic) * 1000

        # --- log + su kien ---
        yaw_dps = math.degrees(yaw_rate)
        for t in tracks:
            r = res[t.id]
            rec.write("frames", [f"{now:.3f}", t.id, f"{t.pos[0]:.3f}", f"{t.pos[1]:.3f}",
                                 f"{t.vel[0]:.3f}", f"{t.vel[1]:.3f}",
                                 f"{t.meas.X:.3f}" if t.matched else "", f"{t.meas.Z:.3f}" if t.matched else "",
                                 NAMES[r["level"]], "" if r["ttc"] is None else f"{r['ttc']:.2f}",
                                 int(comp_on), f"{yaw_dps:.1f}", f"{vib:.2f}", marker])
            if r["level"] >= DANGER and prev_levels.get(t.id, SAFE) < DANGER:
                rec.write("events", [f"{now:.3f}", t.id, NAMES[r["level"]],
                                     "" if r["ttc"] is None else f"{r['ttc']:.2f}",
                                     int(comp_on), f"{yaw_dps:.1f}", marker])
            prev_levels[t.id] = r["level"]
        if overall >= DANGER:
            beep(overall)

        # --- do khoang cach ---
        if dist is not None:
            cand = [t for t in tracks if t.matched]
            if cand:
                t = max(cand, key=lambda k: k.meas.box[3] - k.meas.box[1])
                dist["raw"].append(t.meas.Z)
                dist["kf"].append(t.pos[1])
                dist["id"] = t.id
            if len(dist["raw"]) >= 30:
                raw, kf = np.array(dist["raw"]), np.array(dist["kf"])
                rec.write("distance", [f"{now:.3f}", dist["id"], len(raw), f"{raw.mean():.3f}",
                                       f"{raw.std():.3f}", f"{kf.mean():.3f}", f"{kf.std():.3f}", ""])
                say(f"Distance: raw {raw.mean():.2f}+-{raw.std():.3f} m | "
                    f"Kalman {kf.mean():.2f}+-{kf.std():.3f} m (saved)", 8)
                dist = None

        # --- do do tre ---
        if lat.active and lat.feed(frame, now):
            out = lat.finish(imu)
            if out:
                imu.latency = max(0.0, out[0])
                calib["latency_s"] = imu.latency
                save_calib(calib)
                rec.write("latency", [f"{now:.3f}", f"{out[0]:.3f}", f"{out[1]:.3f}"])
            say(lat.result, 8)

        # --- ve ---
        ttcs = [r["ttc"] for r in res.values() if r["ttc"] is not None and r["level"] > SAFE]
        hud = dict(overall=overall, min_ttc=min(ttcs) if ttcs else None, fps=fps, proc_ms=proc_ms,
                   focal=ranger.f, hfov=ranger.hfov_deg(), imu_status=imu.status,
                   imu_hz=imu.rate_hz(), latency_ms=imu.latency * 1000, comp_on=comp_on,
                   yaw_dps=yaw_dps, vib=vib, recording=recording, marker=marker)
        msg = toast if now < toast_until else None
        if lat.active:
            msg = f"Latency test: tap the table! {lat.remaining(now):.1f}s"
        if dist is not None:
            msg = f"Distance test: stand still... {len(dist['raw'])}/30"
        canvas = ui.render(frame, tracks, res, zone, overall, ranger, cfg, hud, msg, show_help)

        if recording:
            if writer is None:
                path = os.path.join(rec.dir, "output.mp4")
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"),
                                         vid_fps if is_file else 20.0,
                                         (canvas.shape[1], canvas.shape[0]))
                print("Ghi video:", path)
            writer.write(canvas)

        if args.headless:
            continue
        cv2.imshow("VinBus Blind Spot Guard", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("h"):
            show_help = not show_help
        elif key == ord("i"):
            comp_on = not comp_on
            say("IMU compensation " + ("ON" if comp_on else "OFF"))
        elif key == ord("c"):
            cand = [t for t in tracker.tracks if t.matched]
            if not cand:
                say("Calibrate: no person detected")
            else:
                t = max(cand, key=lambda k: k.meas.box[3] - k.meas.box[1])
                f = ranger.calibrate(t.meas.box, cfg["calibration"]["distance_m"])
                calib.setdefault("focal_px", {})[f"{W}x{H}"] = f
                save_calib(calib)
                tracker.tracks.clear()
                say(f"Focal = {f:.0f} px (HFOV {ranger.hfov_deg():.0f} deg) saved")
        elif key == ord("b"):
            s = imu.calibrate_bias(1.0)
            say("Gyro bias calibrated" if s is not None else "Bias: no IMU data")
        elif key == ord("t"):
            out = imu.detect_axis(1.5)
            if out:
                calib["yaw_axis"], calib["yaw_sign"] = out[0], out[1]
                save_calib(calib)
                say(f"Yaw axis = {out[0]}, sign {out[1]:+d} (turned {out[2]:.0f} deg) saved")
            else:
                say("Axis: no IMU data")
        elif key == ord("l"):
            lat.start(now)
        elif key == ord("d"):
            dist = dict(raw=[], kf=[], id=None)
        elif key == ord("m"):
            marker += 1
            say(f"Trial marker = {marker}")
        elif key == ord("r"):
            recording = not recording
            if not recording and writer is not None:
                writer.release()
                writer = None
            say("Recording " + ("ON" if recording else "OFF (saved)"))
        elif isinstance(imu, SimIMU):
            if key == ord("["):
                imu.turn(-1)
            elif key == ord("]"):
                imu.turn(+1)
            elif key == ord("v"):
                imu.shake()

    if writer is not None:
        writer.release()
    imu.stop()
    rec.close()
    cap.release()
    cv2.destroyAllWindows()
    print("Log da luu tai:", rec.dir)


if __name__ == "__main__":
    main()
