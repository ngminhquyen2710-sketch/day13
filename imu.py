"""Phan B - IMU: doc con quay (gyroscope) cua dien thoai qua Phyphox, hoac gia lap bang phim.

Cung cap cho he thong:
  - yaw_rate(t)       : toc do quay cua xe (rad/s, duong = re phai), da tru bias
  - delta_yaw(t0, t1) : goc xe da quay trong khoang [t0, t1]  -> dung de bu chuyen dong trong Kalman
  - vibration()       : muc rung (1.0 = bang nguong)          -> camera kem tin cay

Dong bo thoi gian: moc thoi gian cua Phyphox (tinh tu luc bat dau do) duoc doi sang
dong ho laptop bang offset = min(t_nhan - t_phyphox)  (goi tin it tre nhat).

Chay rieng de kiem tra:  python imu.py --probe http://<ip>:8080
"""
import collections
import math
import threading
import time

import numpy as np

AXES = {"x": 0, "y": 1, "z": 2}
AXIS_NAMES = "xyz"


class IMUBase:
    name = "none"

    def __init__(self, yaw_axis="y", yaw_sign=1, latency_s=0.0, vib_threshold=0.15):
        self.buf = collections.deque(maxlen=8000)       # (t_laptop, gx, gy, gz) rad/s
        self.lock = threading.Lock()
        self.bias = np.zeros(3)
        self.bias_ready = False
        self.yaw_axis = AXES.get(str(yaw_axis), 1)
        self.yaw_sign = 1 if yaw_sign >= 0 else -1
        self.latency = float(latency_s)
        self.vib_threshold = vib_threshold
        self.status = "no IMU"
        self.connected = False
        self._t_first = None

    # ---- vong doi ----
    def start(self):
        pass

    def stop(self):
        pass

    # ---- du lieu ----
    def push(self, t, gx, gy, gz):
        with self.lock:
            self.buf.append((t, gx, gy, gz))
        if not self.bias_ready:
            if self._t_first is None:
                self._t_first = t
            elif t - self._t_first > 1.5:
                self.calibrate_bias(1.2)          # tu hieu chuan bias luc moi ket noi (giu yen)

    def window(self, t0, t1):
        with self.lock:
            rows = [s for s in self.buf if t0 <= s[0] <= t1]
        return np.array(rows, dtype=float).reshape(-1, 4)

    def last_sample_age(self):
        with self.lock:
            if not self.buf:
                return math.inf
            return time.monotonic() - self.buf[-1][0]

    def rate_hz(self):
        now = time.monotonic()
        return float(len(self.window(now - 1.0, now)))

    def _yaw(self, arr):
        return self.yaw_sign * (arr[:, 1 + self.yaw_axis] - self.bias[self.yaw_axis])

    def yaw_rate(self, t, win=0.1):
        arr = self.window(t - win, t)
        if len(arr) == 0:
            with self.lock:
                if not self.buf or t - self.buf[-1][0] > 0.3:
                    return 0.0
                arr = np.array([self.buf[-1]], dtype=float)
        return float(np.mean(self._yaw(arr)))

    def delta_yaw(self, t0, t1):
        if t1 <= t0:
            return 0.0
        arr = self.window(t0, t1)
        if len(arr) >= 2:
            return float(np.mean(self._yaw(arr)) * (t1 - t0))
        return self.yaw_rate(t1, 0.2) * (t1 - t0)

    def vibration(self, win=0.5):
        """Do rung = do lech chuan cua bien thien |omega| giua cac mau (loc thong cao)."""
        now = time.monotonic()
        arr = self.window(now - win, now)
        if len(arr) < 6:
            return 0.0
        mag = np.linalg.norm(arr[:, 1:4] - self.bias, axis=1)
        jitter = np.std(np.diff(mag)) / math.sqrt(2)
        return float(jitter / self.vib_threshold)

    # ---- hieu chuan ----
    def calibrate_bias(self, win=1.0):
        now = time.monotonic()
        arr = self.window(now - win, now)
        if len(arr) < 10:
            return None
        self.bias = arr[:, 1:4].mean(axis=0)
        self.bias_ready = True
        return float(np.linalg.norm(arr[:, 1:4].std(axis=0)))

    def detect_axis(self, win=1.5):
        """Goi ngay sau khi xoay laptop sang PHAI mot lan: chon truc co goc quay lon nhat."""
        now = time.monotonic()
        arr = self.window(now - win, now)
        if len(arr) < 10:
            return None
        g = arr[:, 1:4] - self.bias
        dt = np.diff(arr[:, 0], prepend=arr[0, 0])
        ang = (g * dt[:, None]).sum(axis=0)
        k = int(np.argmax(np.abs(ang)))
        self.yaw_axis = k
        self.yaw_sign = 1 if ang[k] > 0 else -1
        return AXIS_NAMES[k], self.yaw_sign, math.degrees(abs(ang[k]))


class NullIMU(IMUBase):
    name = "none"


class SimIMU(IMUBase):
    """IMU gia lap: giu phim '[' = re trai, ']' = re phai, 'v' = rung."""
    name = "sim"

    def __init__(self, turn_rate_dps=60.0, **kw):
        kw.update(yaw_axis="z", yaw_sign=1)
        super().__init__(**kw)
        self.bias_ready = True
        self.turn_rate = math.radians(turn_rate_dps)
        self._target = 0.0
        self._rate = 0.0
        self._last_key = 0.0
        self._vib_until = 0.0
        self._running = False
        self.status = "SIM ([ ] turn, v shake)"
        self.connected = True

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def turn(self, direction):
        self._target = direction * self.turn_rate
        self._last_key = time.monotonic()

    def shake(self):
        self._vib_until = time.monotonic() + 0.6

    def _loop(self):
        rng = np.random.default_rng()
        while self._running:
            now = time.monotonic()
            if now - self._last_key > 0.25:
                self._target = 0.0
            self._rate += 0.15 * (self._target - self._rate)     # tang/giam muot
            g = rng.normal(0, 0.01, 3)
            g[2] += self._rate
            if now < self._vib_until:
                g += rng.normal(0, 1.2, 3)
            self.push(now, *g)
            time.sleep(0.01)


class PhyphoxIMU(IMUBase):
    name = "phyphox"

    def __init__(self, url, buffers, **kw):
        super().__init__(**kw)
        self.url = url.rstrip("/")
        self.b = buffers
        self.offset = None
        self.last_ph = -1.0
        self._running = False
        self.status = "connecting..."

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        import requests
        s = requests.Session()
        started = False
        tb = self.b["time"]
        names = [self.b["x"], self.b["y"], self.b["z"]]
        while self._running:
            try:
                if not started:
                    s.get(f"{self.url}/control?cmd=start", timeout=1.5)
                    started = True
                th = f"{self.last_ph:.6f}"
                q = f"{tb}={th}&" + "&".join(f"{n}={th}|{tb}" for n in names)
                r = s.get(f"{self.url}/get?{q}", timeout=1.0)
                recv = time.monotonic()
                d = r.json()
                buf = d["buffer"]
                ts = buf[tb]["buffer"]
                cols = [buf[n]["buffer"] for n in names]
                n = min([len(ts)] + [len(c) for c in cols])
                if n:
                    if ts[n - 1] is None:
                        n -= 1
                if n:
                    if self.offset is not None and ts[n - 1] < self.last_ph - 1.0:
                        self.offset = None                 # thi nghiem bi khoi dong lai
                    off = recv - ts[n - 1]
                    self.offset = off if self.offset is None else min(self.offset, off)
                    for i in range(n):
                        if None in (ts[i], cols[0][i], cols[1][i], cols[2][i]):
                            continue
                        self.push(ts[i] + self.offset, cols[0][i], cols[1][i], cols[2][i])
                    self.last_ph = ts[n - 1]
                if not d.get("status", {}).get("measuring", True):
                    started = False                        # app dang dung -> bat lai
                self.connected = True
                self.status = "phyphox OK" if self.bias_ready else "phyphox OK - hold still (bias)"
                time.sleep(0.02)
            except KeyError as e:
                self.connected = False
                self.status = f"phyphox: buffer {e} not found (check config)"
                time.sleep(1.0)
            except Exception as e:  # mat mang, sai IP...
                self.connected = False
                self.status = f"phyphox error: {type(e).__name__}"
                started = False
                time.sleep(1.0)


def make_imu(cfg, source=None):
    c = cfg["imu"]
    source = source or c.get("source", "none")
    kw = dict(yaw_axis=c.get("yaw_axis", "y"), yaw_sign=c.get("yaw_sign", 1),
              latency_s=c.get("latency_s", 0.0),
              vib_threshold=c.get("vibration_threshold", 0.15))
    if source == "phyphox":
        return PhyphoxIMU(c["phyphox_url"], c["buffers"], **kw)
    if source == "sim":
        kw["latency_s"] = 0.0
        return SimIMU(**kw)
    return NullIMU(**kw)


if __name__ == "__main__":
    import argparse
    import json

    import requests

    ap = argparse.ArgumentParser(description="Kiem tra ket noi Phyphox")
    ap.add_argument("--probe", required=True, help="URL Phyphox, vd http://192.168.43.1:8080")
    a = ap.parse_args()
    url = a.probe.rstrip("/")
    try:
        cfg = requests.get(f"{url}/config", timeout=3).json()
        print("Thi nghiem:", cfg.get("title"))
        print("Cac buffer:", [b.get("name") for b in cfg.get("buffers", [])])
    except Exception as e:
        print("Khong doc duoc /config:", e)
    try:
        r = requests.get(f"{url}/get?gyrX&gyrY&gyrZ&gyr_time", timeout=3).json()
        print(json.dumps(r, indent=1)[:800])
    except Exception as e:
        print("Khong doc duoc /get:", e)
