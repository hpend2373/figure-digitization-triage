# -*- coding: utf-8 -*-
"""기하 확인의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_geometry_page.py      # exit 0 = unobserved 없음

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

SRC = os.path.join(HERE, "geometry_page.js")
SUITE = "test_geometry_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 오버레이를 봤다는 표시를 보지 않는다",
     "  if (!s.seen) {", "  if (false) {"),
    ("M2 누가 보았는지 묻지 않는다",
     "  if (!who) {", "  if (false) {"),
    ("M3 확인에 눈금 값을 묻지 않는다",
     "      if (!isNumber(typedTop) || !isNumber(typedBottom)) {", "      if (false) {"),
    ("M4 맨 위와 맨 아래가 같아도 받는다",
     "    if (Number(top) === Number(bottom)) {", "    if (false) {"),
    ("M5 거절과 보류에도 눈금 값을 묻는다",
     "  if (needsValues(verdict)) {", "  if (true) {"),
    ("M6 리더의 값을 맨 위·맨 아래 픽셀과 짝지운다",
     "      pairs = [read[0], read[read.length - 1]];",
     "      pairs = [[read[0][0], Number(s.topPixel)],\n               [read[read.length - 1][0], Number(s.bottomPixel)]];"),
    ("M7 사람이 친 값을 짝 없이 내보낸다",
     "    Confirmed_Tick_Values: pairs.map(function (p) {\n      return p[0] + '@' + p[1];\n    }).join(';'),",
     "    Confirmed_Tick_Values: '',"),
    ("M8 값을 붙일 눈금 행이 없어도 받는다",
     "      if (!isNumber(s.topPixel) || !isNumber(s.bottomPixel)\n          || Number(s.topPixel) === Number(s.bottomPixel)) {",
     "      if (false) {"),
    ("M9 리더와 방향이 어긋나도 받는다",
     "    if (mine && theirs && mine !== theirs) {", "    if (false) {"),
    ("M10 방향이 같기만 하면 어긋난 것으로 친다",
     "    if (mine && theirs && mine !== theirs) {", "    if (mine && theirs) {"),
    ("M11 사람이 친 값보다 읽은 값을 앞에 둔다",
     "    if (!typed && read.length >= 2) {", "    if (read.length >= 2) {"),
    ("M12 고르지 않아도 답으로 친다",
     "  if (!verdict) return", "  if (false) return"),
    ("M13 받을 수 없는 답도 받는다",
     "  if (VERDICTS.indexOf(verdict) < 0) {", "  if (false) {"),
    ("M14 값의 출처를 늘 읽은 값이라고 적는다",
     "      source = 'TYPED';", "      source = 'READ';"),
    ("M15 열쇠를 그대로 Proposal_ID로 내보낸다",
     "    Proposal_ID: String(s.proposal || id),", "    Proposal_ID: id,"),
    ("M16 목록 밖의 이름도 줄이 된다",
     "  ids = (ids || []).slice().sort();",
     "  ids = Object.keys(states || {}).sort();"),
    ("M17 보류를 남은 일로 센다",
     "    if (got.ready && got.row.Human_Verification_Status === HELD) n++;", "    n++;"),
    ("M18 만들어진 축의 방향을 되읽어 주지 않는다",
     "  return sign < 0 ? '위로 갈수록 커지는 축' : '아래로 갈수록 커지는 축';",
     "  return '';"),
    ("M19 따옴표를 감싸지 않는다",
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
