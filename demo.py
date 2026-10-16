"""Menu demo: bam MOT phim so de chon, khong can Enter.

    python demo.py
Dong cua so dang chay (phim q hoac Esc) se quay lai menu.
"""
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def getkey():
    """Doc mot phim, khong can Enter."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):          # phim dac biet (mui ten...) -> bo qua
            msvcrt.getwch()
            return ""
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def run(args):
    print("\n>>", " ".join(args), "\n")
    subprocess.run([PY] + args, cwd=HERE)


def phyphox_url():
    try:
        import yaml
        with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as f:
            return yaml.safe_load(f)["imu"]["phyphox_url"]
    except Exception:
        return "http://192.168.43.1:8080"


MENU = """
==============================================
   VinBus Blind Spot Guard - DEMO
==============================================
 1. Mo phong 3D tren trinh duyet (sim.html)
 2. Camera that + IMU dien thoai (Phyphox)
 3. Camera that + IMU gia lap bang phim
 4. Chay tren file video + IMU gia lap
 5. Tong hop log cua lan chay camera gan nhat
 0. Thoat
----------------------------------------------
Bam mot phim so: """


def main():
    while True:
        print(MENU, end="", flush=True)
        c = getkey()
        print(c)
        if c == "1":
            webbrowser.open(Path(HERE, "sim.html").resolve().as_uri())
            print("Da mo sim.html tren trinh duyet.")
        elif c == "2":
            run(["main.py", "--url", phyphox_url()])
        elif c == "3":
            run(["main.py", "--imu", "sim"])
        elif c == "4":
            v = input("Duong dan video (keo tha file vao day roi Enter): ").strip().strip('"')
            if v:
                run(["main.py", "--source", v, "--imu", "sim", "--loop"])
        elif c == "5":
            run(["analyze.py"])
            print("Bam phim bat ky de quay lai menu...")
            getkey()
        elif c in ("0", "q", "\x1b", "\x03"):
            break


if __name__ == "__main__":
    main()
