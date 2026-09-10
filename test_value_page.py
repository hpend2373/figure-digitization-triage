# -*- coding: utf-8 -*-
"""값 검토 페이지가 사람에게 무엇을 내미는가.

    python3 test_value_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `value_page.js`가 정하고 `test_value_page.mjs`가 봅니다.
여기서 붙잡는 것은 화면의 성질입니다: 겹쳐 그린 그림이 실려 나가는가, 실행
지문이 화면의 칸이 아니라 논리로 건너가는가, 확인 칸이 이름이 아니라 물음으로
적히는가, 그리고 내려받는 이름이 `finalize_batch`가 읽는 파일과 다른가.
"""
import csv
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import value_page as V                                           # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-value-page-")
VALS = os.path.join(TMP, "values")
os.makedirs(VALS)

COLUMNS = ("Panel", "Outcome", "Group", "Median", "Q1", "Q3",
           "Whisker_Lower", "Whisker_Upper")
ROWS = [
    dict(Panel="P_A", Outcome="Plasma total calcium (mmol/L)", Group="BDC",
         Median="2.354", Q1="2.328", Q3="2.412",
         Whisker_Lower="2.248", Whisker_Upper="2.461"),
    dict(Panel="P_A", Outcome="Plasma total calcium (mmol/L)", Group="D2",
         Median="2.429", Q1="2.373", Q3="2.468",
         Whisker_Lower="2.298", Whisker_Upper="2.511"),
    dict(Panel="P_B", Outcome="Serum CTx (pmol/L)", Group="BDC",
         Median="4389", Q1="3387", Q3="6465",
         Whisker_Lower="1237", Whisker_Upper="12110"),
]
with io.open(os.path.join(VALS, V.VALUES), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
    w.writeheader()
    w.writerows(ROWS)
#: 겹쳐 그린 그림은 한 패널에만 둡니다. 없는 그림이 어떻게 나가는지도 이
#: 페이지의 성질입니다 - 볼 것이 없는 카드는 확인을 청하는 카드가 아닙니다.
with io.open(os.path.join(VALS, "P_A.png"), "wb") as fh:
    fh.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

SUBJECTS = {"P_A": "abc123"}
HTML, COUNT = V.build(VALS, when="2026-09-10", subjects=SUBJECTS,
                      log=lambda *a: None)

print("패널마다 한 장, 값은 표로")
check("패널마다 카드가 하나", COUNT == 2 and HTML.count("class='doc'") == 2,
      "%s / %s" % (COUNT, HTML.count("class='doc'")))
check("그림이 있으면 실린다", "data:image/png;base64," in HTML)
# REVERT: 겹쳐 그린 그림이 없어도 조용히 넘어간다. 볼 것이 없는 카드는 확인을
# 청하는 카드가 아니고, 사람은 무엇을 보고 답해야 할지 모릅니다.
check("그림이 없으면 없다고 말한다", "겹쳐 그린 그림 없음" in HTML)
check("읽힌 값이 표로 함께 보인다",
      "2.354" in HTML and "4389" in HTML and "수염 아래" in HTML)

print()
print("실행 지문은 화면의 칸이 아니라 논리로 건너간다")
# REVERT: 실행 지문을 입력 칸으로 내민다. 사람이 고칠 수 있어서는 안 되는
# 값이고, 고쳐지면 이 승인이 다른 실행의 값에 붙습니다.
check("지문은 META로만 간다",
      ('"subject": "abc123"' in HTML or '"subject":"abc123"' in HTML)
      and "data-subject" not in HTML)
# REVERT: 지문이 없는 패널도 있는 것처럼 내민다. 그 카드의 답은
# `finalize_batch`가 어느 추출에 대한 것인지 알 수 없습니다.
check("지문이 없는 패널은 없다고 적힌다", "실행 지문 없음" in HTML)

print()
print("확인 칸은 이름이 아니라 물음으로 적힌다")
# REVERT: 확인 칸에 열 이름만 적는다. `Axis_Labels_Checked`라고만 쓰여 있으면
# 무엇을 확인하라는 것인지 알 수 없고, 모르면 누르는 것이 확인이 아닙니다.
for _name, _ask in V.ASKS:
    check("  %s → %s" % (_name, _ask[:22]), _ask in HTML, _name)
# REVERT: 무엇을 확인해야 하는지 논리에 넘겨주지 않는다. 그러면 확인 칸이
# 화면에는 있는데 아무것도 요구하지 않고, 하나도 누르지 않은 승인이 그대로
# 답이 됩니다 - 이 페이지가 있는 까닭이 사라집니다.
_need = re.search(r'"required":\s*\[(.*?)\]', HTML, re.S)
check("논리가 무엇을 요구하는지 페이지가 심어 준다",
      _need is not None
      and set(re.findall(r'"([A-Za-z_]+)"', _need.group(1)))
      == set(name for name, _ask in V.ASKS),
      _need.group(1) if _need else "없음")

print()
print("화면과 논리가 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "value_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_js = set(re.findall(r"'([A-Z_]+)'",
                     re.search(r"var DECISIONS = \[(.*?)\]", LOGIC, re.S).group(1)))
check("고를 수 있는 답이 곧 답이 되는 답이다",
      set(v for v, _l in V.LABELS) == _js,
      "화면 %s / 논리 %s" % (sorted(v for v, _l in V.LABELS), sorted(_js)))
check("판정 논리가 페이지 안에 들어 있다", "function reviewOf(" in HTML)

print()
print("내려받는 이름은 finalize_batch가 읽는 파일과 다르다")
# REVERT: `value_review.csv`로 내려받는다. 사람이 그 자리에 두게 되고, 실행이
# 만들어 둔 빈 대기열을 덮어씁니다.
check("답안지는 value_review_answers.csv", "'value_review_answers.csv'" in HTML)
check("본 날짜는 부른 쪽이 준 것이 실린다", '"2026-09-10"' in HTML)

print()
print("읽힌 값이 없는 폴더는 페이지가 아니다")
_empty = os.path.join(TMP, "none")
os.makedirs(_empty)
try:
    V.build(_empty, log=lambda *a: None)
    check("값이 없으면 멈추고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("값이 없으면 멈추고 말한다", "읽힌 값이 없습니다" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
