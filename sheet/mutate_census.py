# -*- coding: utf-8 -*-
"""조사표 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_census.py

`unobserved: none`이 통과 조건입니다. 되돌려도 전부 초록인 가드는 장식이고,
가드가 사라졌는데 그대로 통과하는 시나리오도 장식입니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mutate_guard                                       # noqa: E402
SUITE = ["python3", os.path.join(HERE, "test_sheet_build.py")]

MUT = [
    ("M1 판정 코드 무시", "census.py",
     "    return bool(atoms) and all(a in COUNTABLE_ATOMS for a in atoms)",
     "    return True"),
    ("M2 사람 BLOCKED 무시", "census.py",
     '    if entry["Human_Verdict"] == HUMAN_BLOCKED:',
     "    if False:"),
    ("M3 사람 COUNTABLE 무시", "census.py",
     '    if entry["Human_Verdict"] == HUMAN_COUNTABLE:',
     "    if False:"),
    ("M4 픽셀 변경 재검토 제거", "census.py",
     '        if any(not countable_code(e["Agent_Visual_Code"])',
     "        if False and any(not countable_code(e[\'Agent_Visual_Code\'])"),
    ("M5 사람 칸 검증 제거", "census.py",
     "        if human not in HUMAN_VALUES:", "        if False:"),
    ("M6 코드 어휘 검증 제거", "census.py",
     "            if atom not in ATOMS:", "            if False:"),
    ("M7 digest 길이 검증 제거", "census.py",
     "        if len(sha) != 64:", "        if False:"),
    ("M8 같은 크롭 충돌 검증 제거", "census.py",
     "        if prior and (prior[\"Agent_Visual_Code\"] != code",
     "        if False and (prior[\"Agent_Visual_Code\"] != code"),
    ("M9 조사표 없어도 진행", "build_sheet2.py",
     "elif PATHS.CENSUS_OPTIONAL:", "elif True:"),
    ("M10 빌드 ID에서 조사표 제외", "build_sheet2.py",
     "              PATHS.CENSUS, PATHS.REGIONS]",
     "              PATHS.REGIONS]"),
    ("M11 차단 규칙이 조사표를 안 본다", "block_rules.py",
     "    if census is not None:", "    if False:"),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL ", 1)[1].strip() for l in r.stdout.splitlines()
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
    print("%-9s %-26s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 파일이 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
