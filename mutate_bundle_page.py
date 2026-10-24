# -*- coding: utf-8 -*-
"""남은 결정 묶음 페이지의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_bundle_page.py      # exit 0 = unobserved 없음

`mutate_decision_page.py`와 같은 도구입니다(루트 `mutate.py`는 파이썬 묶음만 돌립니다).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import mutate_guard                                              # noqa: E402

SRC = os.path.join(HERE, "bundle_page.js")
SUITE = "test_bundle_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 제안과 다른 답도 보지 않고 받는다",
     "    if (choice === EDIT || choice !== clean(item.proposal).toUpperCase()) {", "    if (false) {"),
    ("M2 제안을 낸 것 없이도 승인한다",
     "    if (!observed) return", "    if (false) return"),
    ("M3 본 것과 승인한 사람이 같아도 받는다",
     "    if (observed.toLowerCase() === who.toLowerCase()) {", "    if (false) {"),
    ("M4 고친 이름도 승인으로 받는다",
     "    if (choice === EDIT || choice !== clean(item.proposal).toUpperCase()) {",
     "    if (choice !== clean(item.proposal).toUpperCase()) {"),
    ("M5 채우기가 고른 답을 덮는다",
     "    if (clean(s.choice)) continue;", ""),
    ("M6 CSV에서 그림 지문을 뺀다",
     "Image_SHA256: clean(item.img_sha)", "Image_SHA256: ''"),
    ("M7 항목에 없는 답도 받는다",
     "  if (optionValues(item).indexOf(choice) < 0) {", "  if (false) {"),
    ("M8 이름 없이도 받는다",
     "  if (!who) return", "  if (false) return"),
    ("M9 보류에 본 답 표시를 붙인다",
     "    sp = '';\n  } else if (seen) {", "    sp = '1';\n  } else if (seen) {"),
    ("M10 고친 이름이 비어도 받는다",
     "    if (!text) return", "    if (false) return"),
    ("M11 제안과 같은 고친 이름도 받는다",
     "    if (!edited(item, s)) return", "    if (false) return"),
    ("M12 제안한 이름을 싣지 않는다",
     "    text = clean(item.text.value); unit = clean(item.text.unit);", ""),
    ("M13 묶음 채우기가 묶음을 가리지 않는다",
     "    if (pred && !pred(it)) continue;", ""),
    ("M14 효과 목록 안의 이름 쓰기를 보지 않는다",
     "      for (var k = 0; k < e.length; k++) if (e[k] && e[k].uses_text) return true;", ""),
]

mutate_guard.restore_any(HERE)

bad = 0
for name, old, new in mutate_guard.slice_of(MUT):
    if base.count(old) != 1:
        print("PATCH_FAILED %s (%d곳)" % (name, base.count(old)))
        bad += 1
        continue
    with mutate_guard.mutation(SRC, base.replace(old, new, 1)):
        r = subprocess.run(["node", SUITE], capture_output=True, text=True, cwd=HERE)
    killed = r.returncode != 0
    fails = [l.split("FAIL  ")[1] for l in r.stdout.splitlines() if l.startswith("FAIL  ")]
    print("%-9s %-36s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f.split("  <- ")[0] for f in fails[:2])) if killed
                             else "<-- 이 가드는 시나리오가 없다"))
    if not killed:
        bad += 1

r = subprocess.run(["node", SUITE], capture_output=True, text=True, cwd=HERE)
print("")
print("복원 후: %s" % (r.stdout.strip().splitlines() or ["(없음)"])[-1])
print("unobserved: %s" % ("none" if not bad else bad))
sys.exit(1 if bad else 0)
