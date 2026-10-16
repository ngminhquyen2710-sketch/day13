"""Phan A - Vision: phat hien nguoi (YOLO) + uoc luong vi tri bang mo hinh pinhole.

Pinhole:  Z = f * H / h      (h: chieu cao box, pixel; H: chieu cao nguoi, met; f: tieu cu, pixel)
          X = (u - cx) * Z / f
He toa do cua xe (nhin tu tren xuong): X sang phai, Z ve phia truoc camera.
"""
from dataclasses import dataclass
import math

import numpy as np


@dataclass
class Measurement:
    X: float            # met, sang phai
    Z: float            # met, phia truoc
    sx: float           # do lech chuan cua X
    sz: float           # do lech chuan cua Z
    box: tuple          # (x1, y1, x2, y2) pixel
    conf: float
    truncated: bool     # box cham mep tren/duoi -> chieu cao sai -> khoang cach sai


class PersonDetector:
    def __init__(self, model_path="yolo11n.pt", conf=0.4, imgsz=640):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz

    def __call__(self, frame):
        r = self.model.predict(frame, classes=[0], conf=self.conf,
                               imgsz=self.imgsz, verbose=False)[0]
        out = []
        if r.boxes is not None and len(r.boxes):
            xyxy = r.boxes.xyxy.cpu().numpy()
            cf = r.boxes.conf.cpu().numpy()
            for b, c in zip(xyxy, cf):
                out.append((tuple(float(v) for v in b), float(c)))
        return out


class PinholeRanger:
    def __init__(self, width, height, focal_px=None, person_h=1.65, pixel_noise=4.0):
        self.W, self.H = width, height
        self.f = float(focal_px) if focal_px else 0.8 * width
        self.cx = width / 2.0
        self.person_h = person_h
        self.pixel_noise = pixel_noise

    def hfov_deg(self):
        return 2 * math.degrees(math.atan(self.cx / self.f))

    def measure(self, box, conf, noise_scale=1.0):
        x1, y1, x2, y2 = box
        h = max(y2 - y1, 1.0)
        u = (x1 + x2) / 2.0
        truncated = y1 <= 3 or y2 >= self.H - 3
        Z = self.f * self.person_h / h
        X = (u - self.cx) * Z / self.f
        sp = self.pixel_noise * noise_scale
        sz = Z * sp / h                                   # dZ = Z * dh / h
        sx = math.hypot(Z * sp / self.f, X * sp / h)
        if truncated:
            sz *= 3.0
            sx *= 2.0
        return Measurement(X, Z, max(sx, 0.02), max(sz, 0.03), box, conf, truncated)

    def calibrate(self, box, true_distance_m):
        """Nguoi dung cach camera true_distance_m: f = h * D / H."""
        h = max(box[3] - box[1], 1.0)
        self.f = h * true_distance_m / self.person_h
        return self.f
