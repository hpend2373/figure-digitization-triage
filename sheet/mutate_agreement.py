# -*- coding: utf-8 -*-
"""영역 합의 규칙과 다시 자르기의 가드를 하나씩 되돌리고, 어떤 시나리오가 죽는지 본다.

    python3 mutate_agreement.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = ["python3", os.path.join(HERE, "test_sheet_build.py")]

MUT = [
    ("M1 차단 규칙이 합의를 안 봄", "block_rules.py",
     "    if agreement is not None and agreement != AGREEMENT_COUNTABLE:",
     "    if False:"),
    ("M2 모르는 값을 통과시킴", "block_rules.py",
     '''        return AGREEMENT_UNCOUNTABLE.get(
            agreement, "그림 영역 검증 결과를 해석할 수 없어 막았습니다 (%r)."
            % (agreement,))''',
     '''        if agreement in AGREEMENT_UNCOUNTABLE:
            return AGREEMENT_UNCOUNTABLE[agreement]
        return ""'''),
    ("M3 빌더가 합의를 안 넘김", "build_sheet2.py",
     '''                             agreement=(None if AGREEMENT is None else
                                        AGREEMENT.get(d["Draft_ID"], "PENDING")))''',
     "                             agreement=None)"),
    ("M4 검증표 없어도 진행", "build_sheet2.py",
     "elif PATHS.REGIONS_OPTIONAL:\n    AGREEMENT = None",
     "elif True:\n    AGREEMENT = None"),
    ("M5 빌드 ID에서 검증표 제외", "build_sheet2.py",
     "              PATHS.CENSUS, PATHS.REGIONS]", "              PATHS.CENSUS]"),
    ("M6 다시 자르기가 DISAGREE도 자름", "apply_validated.py",
     '        if reg.get("Agreement") != RECUT_FROM:', "        if False:"),
    ("M7 다시 자르기가 THIN도 자름", "apply_validated.py",
     '        if str(d.get("Crop_Quality_Status") or "").strip() != "ACCEPTABLE":',
     "        if False:"),
    ("M8 크롭 파일을 안 바꿈", "apply_validated.py",
     '        image.save(os.path.join(run, d["Figure_Crop"]))', "        pass"),
    ("M9 옛 상자를 안 남김", "apply_validated.py",
     '        d["Proposal_Figure_BBox"] = d.get("Proposal_Figure_BBox") or old_box',
     "        pass"),
    ("M10 검증표를 AGREE_3으로 안 바꿈", "apply_validated.py",
     '        reg["Agreement"] = "AGREE_3"', "        pass"),
    ("M11 Human_Choice 검증 제거", "apply_validated.py",
     "        if choice not in HUMAN_CHOICES:", "        if False:"),
    ("M12 사람의 BLOCKED 무시", "apply_validated.py",
     '            if choice == "BLOCKED":', "            if False:"),
    ("M13 Agent_Choice를 사람 선택처럼 적용", "apply_validated.py",
     '        choice = str(reg.get("Human_Choice") or "").strip().upper()\n        if choice:',
     '        choice = str(reg.get("Human_Choice") or reg.get("Agent_Choice") or "").strip().upper()\n        if choice:'),
    ("M14 HUMAN_BLOCKED를 통과시킴", "block_rules.py",
     'AGREEMENT_COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED")',
     'AGREEMENT_COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED", "HUMAN_BLOCKED")'),
]


def run():
    r = subprocess.run(SUITE, capture_output=True, text=True, cwd=HERE)
    fails = [l.split("FAIL", 1)[1].strip() for l in r.stdout.splitlines()
             if l.strip().startswith("FAIL")]
    return r.returncode, fails


bad = 0
for name, filename, old, new in MUT:
    path = os.path.join(HERE, filename)
    base = open(path, encoding="utf-8").read()
    if old not in base:
        print("PATCH_FAILED %s" % name)
        bad += 1
        continue
    try:
        open(path, "w", encoding="utf-8").write(base.replace(old, new, 1))
        code, fails = run()
    finally:
        open(path, "w", encoding="utf-8").write(base)
    killed = code != 0
    print("%-9s %-30s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f[:60] for f in fails[:2])) if killed
                             else "<-- 이 가드를 지키는 시나리오가 없다"))
    if not killed:
        bad += 1

code, _ = run()
print("\n복원 후: %s" % ("통과" if code == 0 else "실패 - 복원되지 않았습니다"))
sys.exit(1 if bad or code else 0)
