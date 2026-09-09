# -*- coding: utf-8 -*-
"""판정 페이지의 결정들을 하나씩 되돌려, 시나리오가 붉어지는지 봅니다.

    python3 mutate_errorbar_page.py      # exit 0 = unobserved 없음

`sheet/mutate_sheet.py`와 같은 도구입니다. 루트 `mutate.py`는 파이썬 묶음만
돌리고, 이 파일의 결정들은 node가 돌립니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import mutate_guard                                              # noqa: E402

SRC = os.path.join(HERE, "errorbar_page.js")
SUITE = "test_errorbar_page.mjs"
base = open(SRC, encoding="utf-8").read()

MUT = [
    ("M1 확인을 보지 않는다",
     "  if (!s.verified) {", "  if (false) {"),
    ("M2 인용문 없이도 답이 된다",
     "  if (needsQuote(code) && !quote) {", "  if (false) {"),
    ("M3 모르는 종류를 받는다",
     "  if (TYPES.indexOf(code) < 0 && DISPOSITIONS.indexOf(code) < 0) {",
     "  if (false) {"),
    ("M4 인용문을 요구하지 않는 답에도 인용문을 싣는다",
     "    Errorbar_Definition_Source: needsQuote(code) ? quote : '',",
     "    Errorbar_Definition_Source: quote,"),
    ("M5 인용문 없는 답도 쪽을 싣는다",
     "    Found_On_Page: needsQuote(code) ? page : '',",
     "    Found_On_Page: page,"),
    ("M6 처분에도 인용문을 요구한다",
     "var QUOTE_FREE = ['NO_ERRORBAR'].concat(DISPOSITIONS);",
     "var QUOTE_FREE = [];"),
    ("M7 목록 밖의 이름도 줄이 된다",
     "  docs = (docs || []).slice().sort();",
     "  docs = Object.keys(states || {}).sort();"),
    ("M8 남은 일을 세지 않는다",
     "    if (!answerOf(docs[i], (states || {})[docs[i]]).ready) left++;",
     "    left++;"),
    ("M10 열쇠를 그대로 문서 이름으로 내보낸다",
     "    Source_Document_ID: String(s.doc || doc),",
     "    Source_Document_ID: doc,"),
    ("M11 어느 그림 것인지 싣지 않는다",
     "    Figure_Number: String(s.figure || ''),",
     "    Figure_Number: '',"),
    ("M9 따옴표를 감싸지 않는다",
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
