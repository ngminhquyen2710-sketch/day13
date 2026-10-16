"""Phan C - Danh gia rui ro: vung nguy hiem + hanh lang duong di + thoi gian den va cham (TTC).

Hai vung trong he toa do xe:
  - Vung nguy hiem (sat dau xe, sau zone_depth_m): co nguoi o day => STOP
  - Hanh lang duong di (cung be ngang, dai path_length_m): duong xe sap di qua

Muc canh bao:
  STOP    : nguoi da o trong vung nguy hiem
  DANGER  : nguoi dang di chuyen, du bao cat vao hanh lang trong < danger_s giay
  CAUTION : du bao cat vao hanh lang trong horizon_s giay, hoac dang dung trong hanh lang
  SAFE    : con lai (ke ca nguoi dung yen ngoai hanh lang)
Khi xe re (theo IMU), vung nguy hiem duoc noi rong ve phia re.
Che do than trong: dung chieu cao nguoi nho nhat => vi tri gan hon => canh bao som hon.

Vi sao can bu IMU: khi xe quay, nguoi dung yen ben le TRONG NHU dang chay ngang qua
truoc xe. Neu khong bu, Kalman uoc luong van toc sai va du bao nguoi do cat vao
hanh lang => bao dong gia.
"""
import math

import numpy as np

SAFE, CAUTION, DANGER, STOP = 0, 1, 2, 3
NAMES = ["SAFE", "CAUTION", "DANGER", "STOP"]
COLORS = [(90, 200, 90), (0, 210, 255), (0, 130, 255), (50, 50, 235)]   # BGR


class RiskAssessor:
    def __init__(self, cfg, person_h, person_h_min, turn_threshold_dps):
        self.hw = cfg["zone_half_width_m"]
        self.depth = cfg["zone_depth_m"]
        self.path_len = cfg.get("path_length_m", 4.5)
        self.expand = cfg["turn_expand_m"]
        self.horizon = cfg["horizon_s"]
        self.danger_s = cfg["danger_s"]
        self.min_speed = cfg["min_speed_mps"]
        self.k = person_h_min / person_h if cfg.get("conservative", True) else 1.0
        self.turn_thr = math.radians(turn_threshold_dps)

    def zone(self, yaw_rate):
        x0, x1, turn = -self.hw, self.hw, None
        if yaw_rate > self.turn_thr:
            x1 += self.expand
            turn = "RIGHT"
        elif yaw_rate < -self.turn_thr:
            x0 -= self.expand
            turn = "LEFT"
        return dict(x0=x0, x1=x1, z0=0.0, z1=self.depth, turn=turn,
                    px0=-self.hw, px1=self.hw, pz1=self.path_len)

    @staticmethod
    def inside(p, z):
        return z["x0"] <= p[0] <= z["x1"] and z["z0"] <= p[1] <= z["z1"]

    @staticmethod
    def in_path(p, z):
        return z["px0"] <= p[0] <= z["px1"] and 0.0 <= p[1] <= z["pz1"]

    def assess(self, tracks, yaw_rate):
        z = self.zone(yaw_rate)
        res = {}
        for t in tracks:
            p = t.pos * self.k
            v = t.vel * self.k
            speed = float(np.linalg.norm(v))
            ttc = None
            if self.inside(p, z):
                level, ttc = STOP, 0.0
            elif self.in_path(p, z):
                level = CAUTION        # dang dung trong duong di cua xe
            elif speed < self.min_speed:
                level = SAFE
            else:
                for tt in np.arange(0.05, self.horizon + 1e-9, 0.05):
                    q = p + v * tt
                    if self.inside(q, z) or self.in_path(q, z):
                        ttc = float(tt)
                        break
                if ttc is None:
                    level = SAFE
                elif ttc < self.danger_s:
                    level = DANGER
                else:
                    level = CAUTION
            res[t.id] = dict(level=level, ttc=ttc, p_c=p, v_c=v, speed=speed)
        overall = max([r["level"] for r in res.values()], default=SAFE)
        return res, z, overall
