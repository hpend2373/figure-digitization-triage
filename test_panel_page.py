# -*- coding: utf-8 -*-
"""패널 페이지가 사람에게 무엇을 내미는가.

    python3 test_panel_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `panel_page.js`가 정하고 `test_panel_page.mjs`가 봅니다.
여기서 붙잡는 것은 화면의 성질입니다: 크롭이 줄여져 실리되 원본 크기가 함께
건너가는가, 제안이 화면의 칸이 아니라 논리로 건너가는가, 다른 크기 위의 제안은
버려지는가, 묶음이 대기열을 빠짐없이 나누는가, 그리고 내려받는 이름이 관문의
출력과 다른가.
"""
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import panel_page as P                                           # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-panel-page-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "crops"))
from PIL import Image                                            # noqa: E402
#: 화면 너비보다 넓은 크롭 하나. 줄여 실리고 좌표는 원본으로 돌아가야 합니다.
Image.new("RGB", (1800, 900), "white").save(os.path.join(RUN, "crops", "D1.png"))
Image.new("RGB", (600, 300), "white").save(os.path.join(RUN, "crops", "D2.png"))
with io.open(os.path.join(RUN, P.DRAFTS), "w", encoding="utf-8") as fh:
    fh.write("Draft_ID,Figure_Crop,Figure_Number,Caption_Text\n"
             "D1,crops/D1.png,FIG1,Fig. 1 | Heart rate\n"
             "D2,crops/D2.png,FIG2,\n"
             "D3,crops/missing.png,FIG3,\n")
QUEUE = [{"fig": "D1", "axes": "2", "pid": "P"},
         {"fig": "D2", "axes": "1", "pid": "P"},
         {"fig": "D3", "axes": "1", "pid": "P"}]
PROPS = {"D1": {"fig": "D1", "size": [1800, 900], "verdict": "PANELS",
                "crop_sha256": "abc123def456", "proposal_version": "v2",
                "note": "전에 센 수 2 ≠ 제안 1. 상자가 서로 겹칩니다 (1·2 100%)",
                "boxes": [{"x0": 10, "y0": 10, "x1": 800, "y1": 800, "mark": "bar",
                           "count": "5"}]},
         "D2": {"fig": "D2", "size": [999, 300], "boxes": [[10, 10, 100, 100]]},
         "D3": {"fig": "D3", "size": [1, 1], "verdict": "MAYBE", "boxes": []}}

HTML, COUNT = P.build(RUN, QUEUE, PROPS, log=lambda *a: None)

print("그림마다 한 장, 크롭은 줄여서")
check("그림마다 카드가 하나", COUNT == 3 and HTML.count("class='doc'") == 3,
      "%s / %s" % (COUNT, HTML.count("class='doc'")))
check("크롭이 있으면 실린다", "data:image/jpeg;base64," in HTML)
# REVERT: 크롭이 없어도 조용히 넘어간다. 그을 그림이 없는 카드는 답을 청하는
# 카드가 아닙니다.
check("크롭이 없으면 없다고 말한다", "크롭 없음" in HTML)
# REVERT: 원본 크기를 넘기지 않는다. 화면 좌표가 그대로 나가고, 600 DPI로
# 옮길 때 상자가 그림의 절반 자리에 떨어집니다.
_m = re.search(r"var META = (\{.*?\});\n", HTML, re.S)
import json                                                      # noqa: E402
META = json.loads(_m.group(1))
check("원본 크기가 논리로 건너간다", META["D1"]["size"] == {"w": 1800, "h": 900},
      META["D1"]["size"])
check("보이는 크기는 줄인 것이다",
      META["D1"]["shown"] == {"w": P.SHOW_WIDTH, "h": 450}, META["D1"]["shown"])
check("작은 크롭은 줄이지 않는다", META["D2"]["shown"] == {"w": 600, "h": 300})
check("크롭이 없으면 크기도 없다", META["D3"]["size"] is None)
check("캡션이 함께 보인다", "Heart rate" in HTML)
check("전에 센 수가 함께 건너간다", META["D1"]["declared"] == "2")

print()
print("제안은 화면의 칸이 아니라 논리로 건너간다")
check("제안 상자가 종류·개수와 함께 META로 간다",
      META["D1"]["proposed"] == [{"x0": 10, "y0": 10, "x1": 800, "y1": 800,
                                  "mark": "BAR", "count": "5", "source": "PROPOSED",
                                  "markSource": "PROPOSED", "countSource": "PROPOSED"}],
      META["D1"]["proposed"])
check("셀 수 없는 개수는 제안으로 싣지 않는다",
      P.proposed_box({"x0": 1, "y0": 1, "x1": 9, "y1": 9, "mark": "BAR",
                      "count": "몇"})["count"] == "")
# REVERT: 제안된 판정을 넘기지 않는다. 사람이 이미 제안된 것을 다시 고르고,
# 297장을 다 골라야 합니다.
check("제안된 판정이 미리 골라져 나간다", META["D1"]["proposedVerdict"] == "PANELS")
check("이 페이지의 어휘에 없는 판정은 싣지 않는다", META["D3"]["proposedVerdict"] == "")
check("잉크 분할만의 제안(종류 없음)도 받는다",
      P.proposed_box([1, 2, 3, 4])["mark"] == "" and P.proposed_box([1, 2, 3, 4])["markSource"] == "")
check("받을 수 없는 종류는 제안으로 싣지 않는다",
      P.proposed_box({"x0": 1, "y0": 1, "x1": 9, "y1": 9, "mark": "PIE"})["mark"] == "")
# REVERT: 제안이 잰 크기가 크롭과 달라도 싣는다. 그 좌표는 다른 그림의
# 좌표이고, 사람은 엉뚱한 자리의 상자를 "맞다"고 넘깁니다.
check("다른 크기 위의 제안은 싣지 않는다", META["D2"]["proposed"] == [],
      META["D2"]["proposed"])
check("제안이 몇 개인지 카드에 적힌다", "제안 상자 1개" in HTML and "제안 상자 0개" in HTML)

print()
print("답은 제안과 크롭에 묶여 나간다")
# REVERT: 답을 크롭·제안 판본에 묶지 않는다. 브라우저는 같은 file:// 자리에서
# 저장소를 함께 쓰고, 제안을 고쳐 페이지를 다시 만들어도 옛 답이 되살아납니다.
check("크롭 지문과 제안 판본이 META로 간다",
      META["D1"]["crop"] == "abc123def456" and META["D1"]["proposalVersion"] == "v2",
      (META["D1"].get("crop"), META["D1"].get("proposalVersion")))
check("표가 크롭·제안·상자 수를 함께 담는다",
      META["D1"]["stamp"] == "abc123def456/v2/1", META["D1"].get("stamp"))
check("크롭이나 제안이 다르면 표도 다르다",
      META["D1"]["stamp"] != META["D2"]["stamp"])
check("화면이 그 표로 남은 답을 버린다", "staleState(states[id], m)" in HTML)

print()
print("기계가 남긴 말과 어긋난 수를 사람에게 보인다")
# REVERT: 제안한 쪽이 남긴 말을 감춘다. 사람은 기계가 스스로 의심한 자리를
# 모르는 채로 "맞다"를 누릅니다.
check("제안한 쪽의 말이 카드에 실린다", "제안한 쪽의 말" in HTML and "겹칩니다" in HTML)
# REVERT: 겹치는 상자와 전에 센 수의 차이를 말하지 않는다. 계수만 맞으면
# 아무 데도 안 걸리는 오류가 그대로 넘어갑니다.
check("겹침과 계수 차이를 화면이 말한다",
      "overlapPairs(s.boxes)" in HTML and "≠ 그린 수" in HTML)

print()
print("사람이 숫자로 고칠 수 있다")
# REVERT: 자리를 끌기로만 고치게 한다. 한 픽셀을 맞추기 어렵고, 옆 패널에 한 뼘
# 걸친 상자를 고치는 일이 대부분 그런 일입니다.
check("상자마다 좌표 칸이 넷", "n.type = 'number'" in HTML and "['x0', 'y0', 'x1', 'y1']" in HTML)
# REVERT: 개수를 물을 자리가 없다. 리더가 찾아낸 수와 대조할 수는 끌기로는
# 말할 수 없습니다.
check("상자마다 개수 칸이 하나", "cnt.placeholder = '개수'" in HTML)
check("숫자로 고친 상자는 사람이 그은 것으로 바뀐다",
      "if (b.source === 'PROPOSED') { b.source = 'DRAWN'; }" in HTML)
check("끌지 않고도 상자를 더할 수 있다", "data-add=" in HTML and "상자 추가" in HTML)
check("개수를 아직 말하지 않은 패널을 세어 보인다",
      "missingCounts(IDS, states)" in HTML)

print()
print("화면의 기하는 논리가 한다")
# REVERT: 자리를 옮기는 산수를 페이지 안에 다시 적는다. 아무 시나리오도 그것을
# 보지 않고, 창이 좁을 때 상자가 어긋난 자리에 저장됩니다.
check("자리는 imagePoint가 옮긴다",
      "imagePoint(c.getBoundingClientRect()" in HTML and "ev.clientX - r.left" not in HTML)
check("고르기는 boxAt이 한다", "boxAt(s.boxes" in HTML)
check("캔버스가 그림이 차지한 크기를 따라간다",
      ".wrap canvas{" in HTML and "width:100%;height:100%" in HTML)
# REVERT: Delete가 모든 카드를 돈다. 화면 밖 다른 그림의 고른 상자까지 지우고,
# 사람은 지운 줄도 모릅니다.
check("지우기는 마지막에 손댄 카드에만 든다",
      "if (!active) return;" in HTML and "IDS.forEach(function (id) {\n      var s = st(id);" not in HTML)

print()
print("화면과 논리가 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "panel_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_v = set(re.findall(r"'([A-Z_]+)'", re.search(r"var VERDICTS = \[(.*?)\]", LOGIC, re.S).group(1)))
_k = set(re.findall(r"'([A-Z_]+)'", re.search(r"var MARKS = \[(.*?)\]", LOGIC, re.S).group(1)))
check("고를 수 있는 판정이 곧 답이 되는 판정이다",
      set(v for v, _l in P.LABELS) == _v,
      "화면 %s / 논리 %s" % (sorted(v for v, _l in P.LABELS), sorted(_v)))
check("고를 수 있는 종류가 곧 답이 되는 종류다",
      set(v for v, _l in P.MARK_LABELS) == _k,
      "화면 %s / 논리 %s" % (sorted(v for v, _l in P.MARK_LABELS), sorted(_k)))
check("판정 논리가 페이지 안에 들어 있다", "function panelsOf(" in HTML)
check("종류의 말이 페이지 안에 들어 있다", "박스플롯" in HTML)

print()
print("묶음은 대기열을 빠짐없이 나눈다")
_parts = [P.pick_chunk(QUEUE, c, 2) for c in (1, 2)]
check("두 묶음이 셋을 나눈다", [len(p) for p in _parts] == [2, 1], [len(p) for p in _parts])
check("순서는 대기열의 순서다", _parts[0][0]["fig"] == "D1" and _parts[1][0]["fig"] == "D3")
try:
    P.pick_chunk(QUEUE, 3, 2)
    check("묶음 밖의 번호는 멈춘다", False, "멈추지 않았다")
except SystemExit as exc:
    check("묶음 밖의 번호는 멈춘다", "묶음이 아닙니다" in str(exc), str(exc))
check("제목에 묶음 번호가 적힌다",
      "패널 확인 2/2" in P.build(RUN, QUEUE, PROPS, chunk=2, of=2, log=lambda *a: None)[0])

print()
print("내려받는 이름은 관문의 출력과 다르다")
check("답안지는 panel_answers.csv", "'panel_answers.csv'" in HTML)
check("관문의 출력 이름으로는 내려받지 않는다",
      "panel_decisions.csv" not in re.sub(r"//[^\n]*", "", HTML))

print()
print("빈 대기열은 페이지가 아니다")
try:
    P.build(RUN, [], PROPS, log=lambda *a: None)
    check("그림이 없으면 멈추고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("그림이 없으면 멈추고 말한다", "그림이 없습니다" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
