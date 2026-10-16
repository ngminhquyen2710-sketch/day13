"""Tong hop so lieu cho phan Bang chung.

  python analyze.py              # phien log moi nhat
  python analyze.py logs/2026...  # phien cu the

In ra:
  - So canh bao (DANGER/STOP) theo tung luot thu (marker) va che do bu IMU
  - Ket qua do khoang cach (dien cot true_distance_m trong distance.csv de tinh sai so)
  - Do tre camera/IMU
"""
import csv
import glob
import os
import sys
from collections import defaultdict


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    if len(sys.argv) > 1:
        d = sys.argv[1]
    else:
        runs = sorted(glob.glob(os.path.join(root, "*")))
        if not runs:
            sys.exit("Chua co log nao")
        d = runs[-1]
    print("Phien:", d)

    frames = read(os.path.join(d, "frames.csv"))
    events = read(os.path.join(d, "events.csv"))

    # thoi luong + che do cua tung marker
    dur = defaultdict(lambda: [1e18, -1e18, set()])
    for r in frames:
        k = r["marker"]
        t = float(r["t"])
        dur[k][0] = min(dur[k][0], t)
        dur[k][1] = max(dur[k][1], t)
        dur[k][2].add(r["comp_on"])

    cnt = defaultdict(int)
    for e in events:
        cnt[(e["marker"], e["comp_on"])] += 1

    print("\n== Canh bao DANGER/STOP theo luot thu ==")
    print(f"{'trial':>6} {'comp':>5} {'events':>7} {'duration_s':>11}")
    keys = sorted(set(list(dur.keys()) + [k[0] for k in cnt]), key=lambda s: int(s or 0))
    for k in keys:
        modes = sorted(dur[k][2]) if k in dur else ["?"]
        for m in modes:
            span = dur[k][1] - dur[k][0] if k in dur else 0
            print(f"{k:>6} {('ON' if m == '1' else 'OFF'):>5} {cnt[(k, m)]:>7} {span:>11.1f}")

    dist = read(os.path.join(d, "distance.csv"))
    if dist:
        print("\n== Do khoang cach ==")
        for r in dist:
            line = (f"raw {float(r['raw_mean']):.2f} +- {float(r['raw_std']):.3f} m | "
                    f"Kalman {float(r['kf_mean']):.2f} +- {float(r['kf_std']):.3f} m")
            if r.get("true_distance_m"):
                tr = float(r["true_distance_m"])
                err = float(r["kf_mean"]) - tr
                line += f" | that {tr:.2f} m, sai so {err:+.2f} m ({100*err/tr:+.0f}%)"
            print(line)

    lat = read(os.path.join(d, "latency.csv"))
    for r in lat:
        print(f"\nDo tre camera so voi IMU: {float(r['lag_s'])*1000:+.0f} ms (corr {float(r['corr']):.2f})")


if __name__ == "__main__":
    main()
