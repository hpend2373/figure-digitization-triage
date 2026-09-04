# -*- coding: utf-8 -*-
"""2단계 화면 검사의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_display.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SUITE = ["python3", os.path.join(HERE, "test_sheet_build.py")]

MUT = [
    ("M1 빌더가 페이지 상자를 아래 기준으로 그림", "build_sheet2.py",
     "        [x0 * W / pw, y0 * H / ph, x1 * W / pw, y1 * H / ph],",
     "        [x0 * W / pw, (ph - y1) * H / ph, x1 * W / pw, (ph - y0) * H / ph],"),
    ("M2 빌더가 확대 이미지를 축소", "build_sheet2.py",
     "    if ZOOM_MAX_WIDTH and im.width > ZOOM_MAX_WIDTH:",
     "    if im.width > 120:\n        ZOOM_MAX_WIDTH = 120"),
    ("M3 빌더가 썸네일을 정사각형으로", "build_sheet2.py",
     "        im = im.resize((width, max(1, round(im.height * width / im.width))),",
     "        im = im.resize((width, width),"),
    ("M4 검사가 빨강을 아무 색으로", "display_checks.py",
     "RED = lambda r, g, b: r >= 140 and g <= 90 and b <= 90",
     "RED = lambda r, g, b: True"),
    ("M5 변 덮임 문턱 0", "display_checks.py", "EDGE_COVER = 0.55", "EDGE_COVER = 0.0"),
    ("M6 확대 크기 비교 제거", "display_checks.py",
     "    if z.size != want:", "    if False:"),
    ("M7 비율 비교 제거", "display_checks.py",
     "    if abs(a - b) / b > tolerance:", "    if False:"),
    ("M8 검사 묶음에서 page_box 제외", "display_checks.py",
     '                             ("page_box", lambda: page_box_drawn_where_the_row_says(card, row))):',
     "                             ):"),
    ("M9 카드 파서가 그림 있는 카드만 봄", "display_checks.py",
     "        out.append({\"Draft_ID\": m.group(1),",
     "        if img is None:\n            continue\n        out.append({\"Draft_ID\": m.group(1),"),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


mutate_guard.restore_any(HERE)

bad = 0
for name, filename, old, new in MUT:
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    with mutate_guard.mutation(path, base.replace(old, new, 1)):
        code, fails = run()
    killed = code != 0
    print("%-9s %-34s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:56] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
