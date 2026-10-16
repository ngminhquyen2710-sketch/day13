"""Phan C - Tracking: Kalman filter van toc khong doi + bu chuyen dong quay cua xe (tu IMU).

Trang thai moi nguoi (he toa do xe): s = [x, z, vx, vz]
  - (x, z): vi tri, met
  - (vx, vz): van toc CUA CHINH NGUOI DO (so voi mat dat)

Khi xe quay sang phai mot goc dtheta, moi diem dung yen trong the gioi
bi quay nguoc lai trong he toa do xe:  p' = R(dtheta) p.
=> Buoc du bao:  p' = R (p + v dt),  v' = R v
Neu KHONG bu (dtheta = 0), Kalman se hieu nham "khung hinh truot" thanh "nguoi dang chay".
"""
import itertools
import math

import numpy as np

H_MAT = np.array([[1.0, 0, 0, 0], [0, 1.0, 0, 0]])


class Track:
    _ids = itertools.count(1)

    def __init__(self, m):
        self.id = next(Track._ids)
        self.x = np.array([m.X, m.Z, 0.0, 0.0])
        self.P = np.diag([m.sx ** 2, m.sz ** 2, 1.0, 1.0])
        self.hits = 1
        self.missed = 0
        self.meas = m            # detection gan nhat (de ve box)
        self.matched = True

    def predict(self, dt, dtheta, accel_noise):
        c, s = math.cos(dtheta), math.sin(dtheta)
        R = np.array([[c, -s], [s, c]])
        F = np.zeros((4, 4))
        F[:2, :2] = R
        F[:2, 2:] = R * dt
        F[2:, 2:] = R
        G = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
        Q = G @ G.T * accel_noise ** 2
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def innovation(self, m):
        y = np.array([m.X, m.Z]) - H_MAT @ self.x
        S = H_MAT @ self.P @ H_MAT.T + np.diag([m.sx ** 2, m.sz ** 2])
        return y, S

    def mahalanobis(self, m):
        y, S = self.innovation(m)
        return float(math.sqrt(y @ np.linalg.solve(S, y)))

    def update(self, m):
        y, S = self.innovation(m)
        K = self.P @ H_MAT.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        I_KH = np.eye(4) - K @ H_MAT
        Rm = np.diag([m.sx ** 2, m.sz ** 2])
        self.P = I_KH @ self.P @ I_KH.T + K @ Rm @ K.T     # dang Joseph, on dinh so hoc
        self.meas = m
        self.hits += 1
        self.missed = 0
        self.matched = True

    @property
    def pos(self):
        return self.x[:2]

    @property
    def vel(self):
        return self.x[2:]


class MultiTracker:
    def __init__(self, accel_noise=1.5, gate_m=1.0, max_missed=10, confirm_hits=3):
        self.tracks = []
        self.accel_noise = accel_noise
        self.gate_m = gate_m
        self.max_missed = max_missed
        self.confirm_hits = confirm_hits

    def step(self, measurements, dt, dtheta=0.0):
        for t in self.tracks:
            t.predict(dt, dtheta, self.accel_noise)
            t.matched = False

        # ghep tham lam theo khoang cach (cap gan nhat truoc)
        pairs = []
        for i, t in enumerate(self.tracks):
            for j, m in enumerate(measurements):
                d = float(np.hypot(m.X - t.pos[0], m.Z - t.pos[1]))
                if d < self.gate_m or t.mahalanobis(m) < 3.5:
                    pairs.append((d, i, j))
        pairs.sort()
        used_t, used_m = set(), set()
        for _, i, j in pairs:
            if i in used_t or j in used_m:
                continue
            self.tracks[i].update(measurements[j])
            used_t.add(i)
            used_m.add(j)

        for i, t in enumerate(self.tracks):
            if i not in used_t:
                t.missed += 1
        for j, m in enumerate(measurements):
            if j not in used_m:
                self.tracks.append(Track(m))
        self.tracks = [t for t in self.tracks if t.missed <= self.max_missed]

    def confirmed(self, max_missed=3):
        return [t for t in self.tracks if t.hits >= self.confirm_hits and t.missed <= max_missed]
