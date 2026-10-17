# -*- coding: utf-8 -*-
"""축·계열 확인 페이지의 판정 논리(axis_series_page.js)를 하나씩 되돌려, node 시나리오가 붉어지는지 봅니다.

    python3 mutate_axis_series_page.py      # exit 0 = unobserved 없음

`mutate_bundle_page.py`와 같은 도구입니다(루트 `mutate.py`는 파이썬 묶음만 돌립니다).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import mutate_guard                                              # noqa: E402

SRC = os.path.join(HERE, "axis_series_page.js")
SUITE = "test_axis_series_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 채우기가 고른 답을 덮는다",
     "      PARTS.forEach(function (p) { if (!out[id][p]) out[id][p] = 'ACCEPT'; });",
     "      PARTS.forEach(function (p) { out[id][p] = 'ACCEPT'; });"),
    ("M2 보지 않은 제안대로를 받는다", "    if (!s.seen) {", "    if (false) {"),
    ("M3 이름 없는 답을 받는다", "    if (!name) return { done: false", "    if (false) return { done: false"),
    ("M4 관문 규칙에 걸리는 제안을 받는다", "    if (a === 'ACCEPT' && brk && brk[id + '|' + p]) {", "    if (false) {"),
    ("M5 리더가 읽은 단위를 비우지 않는다",
     "    if (i.ready && i.row && data.proposals[id].idn.unitBlank) i.row.Unit = '';", ""),
    ("M6 고칠 곳에 메모를 요구하지 않는다", "      return { done: true, fix: true, bad: !memo,", "      return { done: true, fix: true, bad: false,"),
    ("M7 다시 대 보기가 페이지에 없는 패널을 보지 않는다",
     "    if (!data.proposals[id] || !p) { out.unknown.push(id); return; }", "    if (!p) return;"),
    ("M8 다시 대 보기가 목격을 보지 않는다",
     "    if (trimmed(r.Seen_By_Person) === '1') s.seen = true;", "    s.seen = true;"),
    ("M9 다시 대 보기가 메모를 버린다", "    if (trimmed(r.Note)) s.note = trimmed(r.Note);", ""),
    ("M10 다시 대 보기가 관문 줄을 대 보지 않는다",
     "    if (got === want) { out.same++; return; }", "    out.same++; return;"),
    ("M11 다시 대 보기가 답하지 않은 패널을 세지 않는다",
     "  data.order.forEach(function (id) { if (!st[id]) out.unanswered.push(id); });", ""),
    ("M12 읽지 못하는 관문 줄을 같은 줄로 센다",
     "      out.differ.push([id, PART_NAME[p], '관문 줄을 읽지 못합니다']); return;", "      out.same++; return;"),
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
    print("%-9s %-40s %s" % ("KILLED" if killed else "SURVIVED", name,
                             ("| " + "; ".join(f.split("  <- ")[0] for f in fails[:2])) if killed
                             else "<-- 이 가드는 시나리오가 없다"))
    if not killed:
        bad += 1

r = subprocess.run(["node", SUITE], capture_output=True, text=True, cwd=HERE)
print("")
print("복원 후: %s" % (r.stdout.strip().splitlines() or ["(없음)"])[-1])
print("unobserved: %s" % ("none" if not bad else bad))
sys.exit(1 if bad else 0)
