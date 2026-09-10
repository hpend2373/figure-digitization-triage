# -*- coding: utf-8 -*-
"""값 검토의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_value_page.py      # exit 0 = unobserved 없음

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

SRC = os.path.join(HERE, "value_page.js")
SUITE = "test_value_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 확인 칸을 보지 않고 승인으로 친다",
     "  var missing = decision === APPROVED ? missingChecks(s) : [];",
     "  var missing = [];"),
    ("M2 거절과 보류에도 확인 칸을 요구한다",
     "  var missing = decision === APPROVED ? missingChecks(s) : [];",
     "  var missing = missingChecks(s);"),
    ("M3 누가 보았는지 묻지 않는다", "  if (!who) {", "  if (false) {"),
    ("M4 실행 지문이 없어도 답으로 친다", "  if (!subject) {", "  if (false) {"),
    ("M5 고르지 않아도 답으로 친다", "  if (!decision) return", "  if (false) return"),
    ("M6 받을 수 없는 답도 받는다",
     "  if (DECISIONS.indexOf(decision) < 0) {", "  if (false) {"),
    ("M7 확인하지 않은 것을 확인했다고 적는다",
     "    checks[need[i]] = (s.checks || {})[need[i]] ? 'TRUE' : 'FALSE';",
     "    checks[need[i]] = 'TRUE';"),
    ("M8 묻지 않은 확인도 채워 내보낸다",
     "    Identity_Checked: checks.Identity_Checked || '',",
     "    Identity_Checked: 'TRUE',"),
    ("M9 본 날짜를 브라우저 시계에서 가져온다",
     "    got.row.Reviewed_At = String(when || '');",
     "    got.row.Reviewed_At = new Date().toISOString().slice(0, 10);"),
    ("M10 열쇠를 그대로 Panel_ID로 내보낸다",
     "    Panel_ID: String(s.panel || id),", "    Panel_ID: id,"),
    ("M11 목록 밖의 이름도 줄이 된다",
     "  ids = (ids || []).slice().sort();",
     "  ids = Object.keys(states || {}).sort();"),
    ("M12 보류를 남은 일로 센다",
     "    if (got.ready && got.row.Decision === HELD) n++;", "    n++;"),
    ("M13 따옴표를 감싸지 않는다",
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
