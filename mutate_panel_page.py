# -*- coding: utf-8 -*-
"""패널 페이지의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_panel_page.py      # exit 0 = unobserved 없음

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

SRC = os.path.join(HERE, "panel_page.js")
SUITE = "test_panel_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 종류를 안 고른 패널도 넘긴다",
     "      if (!mark) return", "      if (false) return"),
    ("M2 받을 수 없는 종류도 받는다",
     "      if (MARKS.indexOf(mark) < 0) {", "      if (false) {"),
    ("M3 그림 밖의 상자도 받는다",
     "  if (x0 < 0 || y0 < 0 || x1 > w || y1 > h) return", "  if (false) return"),
    ("M4 넓이 없는 상자도 패널로 센다",
     "  if (x1 - x0 < 4 || y1 - y0 < 4) return", "  if (false) return"),
    ("M5 그림 크기를 모르는데도 상자를 놓는다",
     "  if (w === null || h === null) return", "  if (false) return"),
    ("M6 수가 아닌 좌표도 받는다",
     "  if (x0 === null || y0 === null || x1 === null || y1 === null) return",
     "  if (false) return"),
    ("M7 패널이 있다면서 상자 없는 답을 받는다",
     "    if (!boxes.length) {", "    if (false) {"),
    ("M8 직접 보았다는 표시를 묻지 않는다", "  if (!s.seen) return", "  if (false) return"),
    ("M9 누가 보았는지 묻지 않는다", "  if (!who) return", "  if (false) return"),
    ("M10 고르지 않아도 답으로 친다", "  if (!verdict) return", "  if (false) return"),
    ("M11 받을 수 없는 판정도 받는다",
     "  if (VERDICTS.indexOf(verdict) < 0) {", "  if (false) {"),
    ("M12 제안과 그은 것을 같은 것으로 적는다",
     "        Region_Source: b.source === 'PROPOSED' ? 'PROPOSED' : 'DRAWN',",
     "        Region_Source: 'DRAWN',"),
    ("M20 제안된 종류와 고른 종류를 같은 것으로 적는다",
     "        Mark_Source: b.markSource === 'PROPOSED' ? 'PROPOSED' : 'TYPED',",
     "        Mark_Source: 'TYPED',"),
    ("M13 그은 수를 적지 않는다",
     "        Drawn_Count: String(boxes.length),", "        Drawn_Count: '',"),
    ("M14 열쇠를 그대로 Draft_ID로 내보낸다",
     "        Draft_ID: String(s.draft || id),", "        Draft_ID: id,"),
    ("M15 좌표를 반올림하지 않는다",
     "        X0: Math.round(num(b.x0)), Y0: Math.round(num(b.y0)),",
     "        X0: num(b.x0), Y0: Math.round(num(b.y0)),"),
    ("M16 NO_PANELS를 상자 줄로 적는다",
     "      Draft_ID: String(s.draft || id), Panel_Index: 0,",
     "      Draft_ID: String(s.draft || id), Panel_Index: 1,"),
    ("M17 목록 밖의 그림도 줄이 된다",
     "  ids = (ids || []).slice().sort();", "  ids = Object.keys(states || {}).sort();"),
    ("M18 보류를 남은 일로 센다",
     "    if (got.ready && got.rows[0].Verdict === HELD) n++;", "    n++;"),
    ("M21 잰 크기가 아니라 좌표계 크기로 옮긴다",
     "  var x = (num(clientX) - num((rect || {}).left || 0)) * (sw / rw);",
     "  var x = (num(clientX) - num((rect || {}).left || 0)) * (sw / bw);"),
    ("M22 캔버스가 놓인 자리를 빼지 않는다",
     "  var x = (num(clientX) - num((rect || {}).left || 0)) * (sw / rw);",
     "  var x = num(clientX) * (sw / rw);"),
    ("M23 그림 밖의 자리를 그대로 쓴다",
     "  return { x: Math.max(0, Math.min(sw, x)), y: Math.max(0, Math.min(sh, y)) };",
     "  return { x: x, y: y };"),
    ("M24 크기를 몰라도 자리를 낸다",
     "  if (!rw || !rh || !bw || !bh || !sw || !sh) return null;", "  if (false) return null;"),
    ("M25 가장 작은 상자가 아니라 처음 상자를 고른다",
     "    if (a < area) { area = a; best = i; }", "    if (best < 0) { area = a; best = i; }"),
    ("M26 겹치는 상자를 말하지 않는다",
     "      if (f > OVERLAP_MAX) out.push({ a: i + 1, b: j + 1, part: f });", "      if (false) out.push({ a: i + 1, b: j + 1, part: f });"),
    ("M27 겹침을 두 상자 중 큰 쪽으로만 잰다",
     "      var f = Math.max(coverOf(boxes[i], boxes[j]), coverOf(boxes[j], boxes[i]));",
     "      var f = coverOf(boxes[i], boxes[j]);"),
    ("M28 브라우저에 남은 답을 그대로 쓴다",
     "  return was !== now;", "  return false;"),
    ("M29 답을 크롭에 묶지 않는다",
     "        Crop_SHA256: String(s.crop || ''),", "        Crop_SHA256: '',"),
    ("M30 아무 글자나 개수로 받는다",
     "  if (!/^[0-9]+$/.test(t) || Number(t) < 1) return '개수는 1 이상의 정수여야 합니다';",
     "  return '';"),
    ("M31 빈 개수를 막는다", "  if (!t) return '';", "  if (!t) return '개수를 적어 주세요';"),
    ("M32 개수가 잘못돼도 답으로 친다",
     "      if (badCount) return { ready: false, why: (i + 1) + '번 패널: ' + badCount, rows: [] };",
     "      if (false) return { ready: false, why: (i + 1) + '번 패널: ' + badCount, rows: [] };"),
    ("M33 제안된 개수와 사람이 친 개수를 같은 것으로 적는다",
     "          ? (b.countSource === 'PROPOSED' ? 'PROPOSED' : 'TYPED') : '',",
     "          ? 'TYPED' : '',"),
    ("M34 개수 없는 패널도 적은 것으로 센다",
     "      if (!String(bs[j].count === null || bs[j].count === undefined ? '' : bs[j].count).trim()) n++;",
     "      if (false) n++;"),
    ("M35 두 번째 종류를 첫 번째와 같게 받는다",
     "        if (mark2 === mark) return", "        if (false) return"),
    ("M36 읽을 값 없음도 두 번째 종류로 받는다",
     "        if (MARKS.indexOf(mark2) < 0 || mark2 === 'NOT_DATA' || mark === 'NOT_DATA') {",
     "        if (MARKS.indexOf(mark2) < 0) {"),
    ("M37 두 번째 종류의 개수를 보지 않는다",
     "        if (badCount2) return", "        if (false) return"),
    ("M38 두 번째 종류 없이도 개수를 내보낸다",
     "        Mark_Count_2: mark2 ? String(b.count2 === null || b.count2 === undefined ? '' : b.count2).trim() : '',",
     "        Mark_Count_2: String(b.count2 === null || b.count2 === undefined ? '' : b.count2).trim(),"),
    ("M39 겹침을 적지 않는다",
     "        Overlay: b.overlay ? 'INDIVIDUAL' : '',", "        Overlay: '',"),
    ("M40 제안된 겹침과 사람이 표시한 겹침을 같은 것으로 적는다",
     "        Overlay_Source: b.overlay ? (b.overlaySource === 'PROPOSED' ? 'PROPOSED' : 'TYPED') : '',",
     "        Overlay_Source: b.overlay ? 'TYPED' : '',"),
    ("M19 따옴표를 감싸지 않는다",
     "  return '\"' + String(s === null || s === undefined ? '' : s).replace(/\"/g, '\"\"') + '\"';",
     "  return '\"' + String(s === null || s === undefined ? '' : s) + '\"';"),
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
