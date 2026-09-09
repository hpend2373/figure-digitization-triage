# -*- coding: utf-8 -*-
"""처분 판정의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_decision_page.py      # exit 0 = unobserved 없음

`mutate_errorbar_page.py`와 같은 도구입니다 - 루트 `mutate.py`가 파이썬 묶음만
돌리기 때문에 node용 러너가 따로 있고, 지금 셋(`sheet/mutate_sheet.py`,
`mutate_errorbar_page.py`, 이 파일)이 거의 같은 글자입니다. 셋을 `mutate.py`의
`runner` 열쇠 하나로 접는 것이 옳고, 아직 접지 않았습니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import mutate_guard                                              # noqa: E402

SRC = os.path.join(HERE, "decision_page.js")
SUITE = "test_decision_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 그림을 봤다는 표시를 보지 않는다",
     "  if (!s.seen) {", "  if (false) {"),
    ("M2 물음마다 받을 답을 가르지 않는다",
     "  if (allowed.indexOf(choice) < 0) {", "  if (false) {"),
    ("M3 무엇을 묻는지 몰라도 받는다",
     "  if (!allowed) return", "  if (false) return"),
    ("M4 어느 패널인지 묻지 않는다",
     "  if (needsWhich(choice) && !which) {", "  if (false) {"),
    ("M5 패널을 묻지 않는 답에도 패널을 싣는다",
     "    Which_Panels: needsWhich(choice) ? which : '',",
     "    Which_Panels: which,"),
    ("M6 열쇠를 그대로 Draft_ID로 내보낸다",
     "    Draft_ID: String(s.draft || id),", "    Draft_ID: id,"),
    ("M7 고르지 않아도 답으로 친다",
     "  if (!choice) return", "  if (false) return"),
    ("M8 목록 밖의 이름도 줄이 된다",
     "  ids = (ids || []).slice().sort();",
     "  ids = Object.keys(states || {}).sort();"),
    ("M9 보류를 남은 일로 센다",
     "    if (got.ready && got.row.Decision === HELD) n++;", "    n++;"),
    ("M10 따옴표를 감싸지 않는다",
     "    .replace(/\"/g, '\"\"') + '\"';", "    + '\"';"),
]

mutate_guard.restore_any(HERE)

bad = 0
for name, old, new in MUT:
    if base.count(old) != 1:
        print("PATCH_FAILED %s (%d곳)" % (name, base.count(old)))
        bad += 1
        continue
    with mutate_guard.mutation(SRC, base.replace(old, new, 1)):
        r = subprocess.run(["node", SUITE], capture_output=True, text=True,
                           cwd=HERE)
    killed = r.returncode != 0
    fails = [l.split("FAIL  ")[1] for l in r.stdout.splitlines()
             if l.startswith("FAIL  ")]
    print("%-9s %-42s %s"
          % ("KILLED" if killed else "SURVIVED", name,
             ("| " + "; ".join(f.split("  <- ")[0] for f in fails[:2]))
             if killed else "<-- 이 가드는 시나리오가 없다"))
    if not killed:
        bad += 1

r = subprocess.run(["node", SUITE], capture_output=True, text=True, cwd=HERE)
print("")
print("복원 후: %s" % (r.stdout.strip().splitlines() or ["(없음)"])[-1])
print("unobserved: %s" % ("none" if not bad else bad))
sys.exit(1 if bad else 0)
