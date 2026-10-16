"""Ghep web/*.js + page.html thanh sim.html.

  python web/build.py                 # sim.html chay offline (three.js nhung san trong file)
  python web/build.py --cdn out.html  # ban nap three.js tu CDN (nhe hon)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THREE_LOCAL = os.path.join(HERE, "three.min.js")
THREE_CDN = '<script src="https://cdn.jsdelivr.net/npm/three@0.157.0/build/three.min.js"></script>'


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def build(cdn, out):
    page = read("page.html")
    page = page.replace("/*CORE*/", read("core.js").replace("if (typeof module !== 'undefined') module.exports", "if (false) module.exports"))
    page = page.replace("/*RENDER*/", read("render.js")).replace("/*APP*/", read("app.js"))
    if cdn:
        page = page.replace("<!--THREE-->", THREE_CDN)
        body = page
    else:
        with open(THREE_LOCAL, encoding="utf-8") as f:
            three = f.read()
        page = page.replace("<!--THREE-->", "<script>" + three + "</script>")
        body = ('<!doctype html>\n<html lang="vi">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print("Da ghi", out, f"({len(body) // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--cdn":
        build(True, sys.argv[2])
    else:
        build(False, os.path.join(ROOT, "sim.html"))
