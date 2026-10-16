"""Menu demo: chon chay camera that hoac mo phong.

    python demo.py
Dong cua so dang chay (phim q) se quay lai menu.
"""
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(args):
    print("\n>>", " ".join(args), "\n")
    subprocess.run([PY] + args, cwd=HERE)


def main():
    with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
        url = yaml.safe_load(f)["imu"]["phyphox_url"]
    while True:
        print("""
==============================================
   VinBus Blind Spot Guard - DEMO
==============================================
 1. Camera that + IMU dien thoai (Phyphox)
 2. Camera that + IMU gia lap bang phim
 3. Mo phong - kich ban tu dong
 4. Mo phong - tu dieu khien
 5. Mo phong - bang so lieu so sanh (khong mo cua so)
 6. Chay tren file video + IMU gia lap
 7. Tong hop log cua lan chay camera gan nhat
 0. Thoat
----------------------------------------------""")
        c = input("Chon: ").strip()
        if c == "1":
            u = input(f"URL Phyphox [{url}]: ").strip() or url
            run(["main.py", "--url", u])
        elif c == "2":
            run(["main.py", "--imu", "sim"])
        elif c == "3":
            run(["simulate.py"])
        elif c == "4":
            run(["simulate.py", "--manual"])
        elif c == "5":
            run(["simulate.py", "--compare"])
            input("\nEnter de quay lai menu...")
        elif c == "6":
            v = input("Duong dan video (keo tha file vao day): ").strip().strip('"')
            if v:
                run(["main.py", "--source", v, "--imu", "sim", "--loop"])
        elif c == "7":
            run(["analyze.py"])
            input("\nEnter de quay lai menu...")
        elif c == "0":
            break


if __name__ == "__main__":
    main()
