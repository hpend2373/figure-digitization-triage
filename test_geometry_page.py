# -*- coding: utf-8 -*-
"""기하 확인 페이지가 사람에게 무엇을 내미는가.

    python3 test_geometry_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `geometry_page.js`가 정하고 `test_geometry_page.mjs`가
봅니다. 여기서 붙잡는 것은 화면의 성질입니다: 오버레이가 실려 나가는가, 리더가
읽은 값이 화면의 칸이 아니라 논리로 건너가는가, 화면의 선택지와 논리의 어휘가
같은가, 그리고 내려받는 이름이 관문의 출력과 다른가.
"""
import base64
import csv
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import geometry_page as G                                        # noqa: E402
import geometry_proposer as GP                                   # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-geometry-page-")
PROP = os.path.join(TMP, "gp")
os.makedirs(PROP)

#: 리더가 읽어 낸 제안 하나와 거절한 제안 하나. 이 페이지의 두 가지 줄이고,
#: 사람이 하는 일이 서로 다릅니다.
READ = {
    "Proposal_ID": "GP001", "Raster": "fig.png",
    "Panel_X0": "10", "Panel_X1": "200", "Panel_Y0": "5", "Panel_Y1": "150",
    "Y_Tick_Pixels": "10;50;90", "Y_Tick_Count": "3",
    "Y_Tick_Read_Status": GP.READ_OK,
    "Y_Tick_Read_Values": "30@10;20@50;10@90",
    "Y_Tick_Read_First": "30", "Y_Tick_Read_Last": "10",
    "Y_Tick_Read_Detail": "3 labels, ladder residual 0.1 px",
    "Box_Anchor_Count": "5", "Box_Anchor_Detail": "5 outlined marks about 88 px wide",
    "Confidence": "1.00", "Confidence_Reason": "",
    "Human_Verification_Status": GP.PROPOSAL_PENDING,
}
REFUSED = dict(READ, Proposal_ID="GP002", Y_Tick_Read_Status=GP.READ_REFUSED,
               Y_Tick_Read_Values="", Y_Tick_Read_First="", Y_Tick_Read_Last="",
               Y_Tick_Read_Detail="only 0 label(s); 3 needed to check a ladder")

GP.write_proposals(os.path.join(PROP, GP.PROPOSALS if hasattr(GP, "PROPOSALS")
                                else "geometry_proposal.csv"), [READ, REFUSED])
#: 오버레이 한 장만 둡니다. 없는 그림이 어떻게 나가는지도 이 페이지의 성질입니다.
_png = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg==")
with io.open(os.path.join(PROP, "GP001.png"), "wb") as fh:
    fh.write(_png)

HTML, COUNT = G.build(PROP, log=lambda *a: None)

print("페이지가 제안을 카드로 내민다")
check("제안마다 카드가 하나", COUNT == 2 and HTML.count("class='doc'") == 2,
      "%s / %s" % (COUNT, HTML.count("class='doc'")))
check("오버레이가 있으면 그림으로 실린다", "data:image/png;base64," in HTML)
# REVERT: 오버레이가 없어도 조용히 넘어간다. 확인할 그림이 없는 카드는 확인을
# 청하는 카드가 아니고, 사람은 무엇을 보고 답해야 할지 모릅니다.
check("오버레이가 없으면 없다고 말한다", "오버레이 없음" in HTML)

print()
print("리더가 읽은 것과 못 읽은 것을 다르게 내민다")
check("읽은 축은 읽은 값이 보인다", "리더가 읽은 축" in HTML and "30 · 20 · 10" in HTML,
      HTML.count("리더가 읽은 축"))
# REVERT: 거절을 흠으로만 적고 왜인지는 감춘다. 사람은 자기가 무엇을 고치는지
# 모르는 채로 숫자를 칩니다.
check("거절한 축은 왜 거절했는지까지 보인다",
      "읽지 못했습니다" in HTML and "3 needed to check a ladder" in HTML)
check("상자 x 위치도 몇 개인지 함께 보인다", "상자 x 위치 5개" in HTML)

print()
print("화면과 논리가 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "geometry_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_js = re.search(r"var VERDICTS = \[(.*?)\]", LOGIC, re.S)
_js_words = set(re.findall(r"'([A-Z_]+)'", _js.group(1)))
_screen = set(v for v, _l in G.LABELS)
# REVERT: 화면의 말과 논리의 말을 따로 둔다. 화면에만 있는 답은 고를 수 있지만
# 답이 되지 않고, 논리에만 있는 답은 아무도 고를 수 없습니다.
check("고를 수 있는 답이 곧 답이 되는 답이다", _screen == _js_words,
      "화면 %s / 논리 %s" % (sorted(_screen), sorted(_js_words)))
check("판정 논리가 페이지 안에 들어 있다", "function verdictOf(" in HTML)

print()
print("리더가 읽은 값은 화면의 칸이 아니라 논리로 건너간다")
# REVERT: 읽은 값을 입력 칸에 미리 채워 둔다. 그러면 사람이 고치지 않은 값과
# 사람이 친 값이 구별되지 않고, `Value_Source`가 아무것도 세지 못합니다.
_top = re.search(r"data-top='GP001'[^>]*>", HTML).group(0)
check("맨 위 눈금 칸은 비어서 나간다", "value=" not in _top, _top)
# REVERT: 값만 META로 넘긴다. 리더가 맨 위·맨 아래 눈금을 읽었다는 보장이
# 없어서, 값만 넘기면 그 값이 어느 눈금의 것인지 논리가 짐작해야 합니다.
check("읽은 것은 값이 아니라 값@픽셀 짝으로 건너간다",
      '"readPairs": "30@10;20@50;10@90"' in HTML
      or '"readPairs":"30@10;20@50;10@90"' in HTML)
# REVERT: 값을 붙일 눈금 행을 넘기지 않는다. 사람이 친 값이 어디에 붙는지
# 논리가 알 수 없고, 그러면 짝을 만들 수 없습니다.
check("값을 붙일 눈금 행도 함께 건너간다",
      '"topPixel": "10"' in HTML or '"topPixel":"10"' in HTML)

print()
print("맨 위·맨 아래로 묻는다")
# REVERT: "첫 눈금 / 끝 눈금"이라고 묻는다. 축은 아래에서 시작하니 아래부터
# 적는 것이 자연스럽고, 계산은 위부터 짝지었습니다 - FIG9 여섯 패널이 전부
# 뒤집혀 돌아왔고 관문의 문 넷을 다 지났습니다.
check("어느 끝인지를 위치로 묻는다",
      "맨 <b>위</b> 눈금" in HTML and "맨 <b>아래</b> 눈금" in HTML)
check("어느 눈금 행인지 숫자로도 보여 준다",
      "(픽셀 행 10)" in HTML and "(픽셀 행 90)" in HTML)
check("바꿔 적으면 어떻게 되는지도 칸 옆에 적혀 있다",
      "위·아래를 바꿔 적으면" in HTML.split("<script>")[0])

print()
print("내려받는 이름은 관문의 출력과 다르다")
# REVERT: 관문이 적는 이름으로 내려받는다. 처분 페이지에서 실제로 그렇게
# 만들었고, 관문이 자기 출력을 답으로 읽어 64줄을 전부 거절한 뒤 원본을
# 덮었습니다.
check("답안지는 geometry_answers.csv", "'geometry_answers.csv'" in HTML)
check("관문의 출력 이름으로는 내려받지 않는다",
      "geometry_decisions.csv" not in re.sub(r"//[^\n]*", "", HTML))

print()
print("빈 제안 폴더는 페이지가 아니다")
_empty = os.path.join(TMP, "none")
os.makedirs(_empty)
try:
    G.build(_empty, log=lambda *a: None)
    check("제안이 없으면 멈추고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("제안이 없으면 멈추고 말한다", "제안이 없습니다" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
