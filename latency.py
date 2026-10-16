"""Phan B - Do do tre camera so voi IMU.

Cach lam: bam 'l', trong 5 giay go manh vai lan vao ban (hoac lac laptop).
Camera thay khung hinh rung, IMU thay dinh quay. Tim do lech thoi gian L
lam hai tin hieu khop nhau nhat (tuong quan cheo):  motion(t) ~ imu(t - L).
L > 0 nghia la anh tu camera den tre hon du lieu IMU L giay.
"""
import cv2
import numpy as np


class LatencyTest:
    def __init__(self, duration=5.0):
        self.duration = duration
        self.active = False
        self.result = None

    def start(self, now):
        self.active = True
        self.t0 = now
        self.motion = []
        self.prev = None
        self.result = None

    def remaining(self, now):
        return max(0.0, self.duration - (now - self.t0))

    def feed(self, frame, t):
        g = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if self.prev is not None:
            self.motion.append((t, float(np.mean(np.abs(g - self.prev)))))
        self.prev = g
        return t - self.t0 >= self.duration

    def finish(self, imu):
        self.active = False
        m = np.array(self.motion)
        arr = imu.window(self.t0 - 1.0, self.t0 + self.duration + 1.0)
        if len(m) < 20 or len(arr) < 50:
            self.result = "Latency test: not enough data (IMU connected?)"
            return None
        mag = np.linalg.norm(arr[:, 1:4] - imu.bias, axis=1)
        fs = 200.0
        tg = np.arange(m[0, 0] + 0.5, m[-1, 0] - 0.5, 1 / fs)
        mo = np.interp(tg, m[:, 0], m[:, 1])
        mo = (mo - mo.mean()) / (mo.std() + 1e-9)
        best, best_c = 0.0, -9.0
        for lag in np.arange(-0.5, 0.5, 0.005):
            a = np.interp(tg - lag, arr[:, 0], mag)
            a = (a - a.mean()) / (a.std() + 1e-9)
            c = float(np.mean(mo * a))
            if c > best_c:
                best, best_c = float(lag), c
        self.result = f"Camera lag vs IMU = {best*1000:+.0f} ms (corr {best_c:.2f})"
        return best, best_c
