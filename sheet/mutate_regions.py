# -*- coding: utf-8 -*-
"""그림 영역 규칙의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_regions.py

`unobserved: none`이 통과 조건입니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "figure_regions.py")
SUITE = ["python3", os.path.join(HERE, "test_figure_regions.py")]

MUT = [
    ("M1 페이지 장식 제거", "    skip = furniture(graphics, size)", "    skip = set()"),
    ("M2 최소 넓이 무시", "    out = [b for b in out if area(b) >= MIN_AREA * 3",
     "    out = [b for b in out if area(b) >= 0"),
    ("M3 납작한 띠 허용", "           and (b[2] - b[0]) >= MIN_SIDE and (b[3] - b[1]) >= MIN_SIDE]",
     "           and (b[2] - b[0]) >= 0 and (b[3] - b[1]) >= 0]"),
    ("M4 거터를 못 찾게", "    if edge_r - edge_l < 8.0:", "    if True:"),
    ("M5 뭉치기가 거터를 무시", "        centre = (band[0] + band[1]) / 2.0",
     "        return near\n        centre = (band[0] + band[1]) / 2.0"),
    ("M6 빈칸 잇기가 거터를 무시", "                if (centre is not None and axis == 0",
     "                if (False and axis == 0"),
    ("M7 사이의 글을 무시", "                if any(overlap(band, t, 0) > (t[2] - t[0]) * 0.5",
     "                if False and any(overlap(band, t, 0) > (t[2] - t[0]) * 0.5"),
    ("M8 아무리 멀어도 잇기", "                if _gap(a, b, axis) > reach:",
     "                if False:"),
    ("M9 비슷해도 고르기", "        if len(rivals) > 1 and rivals[0] - rivals[1] < margin:",
     "        if False:"),
    ("M10 한 그림을 여럿에게", "        if value <= 0 or j in used or out[i][0] is not None:",
     "        if value <= 0 or out[i][0] is not None:"),
    ("M11 옆 캡션을 못 보게", "    if vov > 0.35 and side < REACH:", "    if False:"),
    ("M12 위 캡션을 못 보게", "        best = max(best, hov - above / REACH - 0.12)",
     "        best = max(best, 0.0)"),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL ", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


base = open(SRC, encoding="utf-8").read()
bad = 0
for name, old, new in MUT:
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    try:
        open(SRC, "w", encoding="utf-8").write(base.replace(old, new, 1))
        code, fails = run()
    finally:
        open(SRC, "w", encoding="utf-8").write(base)
    killed = code != 0
    print("%-9s %-24s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
