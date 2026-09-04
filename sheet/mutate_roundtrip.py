# -*- coding: utf-8 -*-
"""왕복 검사의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_roundtrip.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SUITE = ["python3", os.path.join(HERE, "test_sheet_build.py")]

MUT = [
    ("M1 y를 아래 기준으로", "roundtrip.py",
     "    top = max(0, int(y0 * sy) - PAD)",
     "    top = max(0, int((ph - y1) * sy) - PAD)"),
    ("M2 pad 제거", "roundtrip.py", "PAD = 8", "PAD = 0"),
    ("M3 여백 자르기 제거", "roundtrip.py", "    if ink.any():", "    if False:"),
    ("M4 내용 차이 무시", "roundtrip.py", "    if diff > 0.5:", "    if False:"),
    ("M5 크기 차이 무시", "roundtrip.py", "    if disk.size != image.size:",
     "    if False:"),
    ("M6 selfcheck가 MISMATCH를 통과시킴", "roundtrip.py",
     '        if status != "MATCH":', "        if False:"),
    ("M7 차단 규칙이 왕복 결과를 안 봄", "block_rules.py",
     "    if roundtrip in ROUNDTRIP_UNVERIFIABLE:", "    if False:"),
    ("M8 빌더가 왕복 결과를 안 넘김", "build_sheet2.py",
     '                             roundtrip=ROUNDTRIP.get(d["Draft_ID"]),',
     "                             roundtrip=None,"),
    ("M9 검사기가 왕복 단계를 뺌", "verify_intake_images.py",
     "    mismatched = roundtrip_mismatches(root)", "    mismatched = []"),
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
    print("%-9s %-30s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:60] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
