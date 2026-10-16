"""Ghi log CSV cho phan Bang chung (frames, events, distance)."""
import csv
import os
import time


class Recorder:
    def __init__(self, root="logs"):
        self.dir = os.path.join(root, time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self._f = {}
        self._w = {}
        self._open("frames", ["t", "track_id", "x", "z", "vx", "vz", "meas_x", "meas_z",
                              "level", "ttc", "comp_on", "yaw_rate_dps", "vibration", "marker"])
        self._open("events", ["t", "track_id", "level", "ttc", "comp_on", "yaw_rate_dps", "marker"])
        self._open("distance", ["t", "track_id", "n", "raw_mean", "raw_std", "kf_mean", "kf_std",
                                "true_distance_m"])
        self._open("latency", ["t", "lag_s", "corr"])

    def _open(self, name, header):
        f = open(os.path.join(self.dir, f"{name}.csv"), "w", newline="", encoding="utf-8")
        w = csv.writer(f)
        w.writerow(header)
        self._f[name], self._w[name] = f, w

    def write(self, name, row):
        self._w[name].writerow(row)

    def close(self):
        for f in self._f.values():
            f.close()
