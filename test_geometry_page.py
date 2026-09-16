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

#: 축을 나눠 쓸 수 있는 세 번째 패널: 같은 그림, 눈금 없음, 리더가 GP001을
#: 후보로 댄 것. 그리고 다른 그림의 패널 하나 - 그 패널은 후보가 될 수 없습니다.
SHARER = dict(REFUSED, Proposal_ID="GP003", Y_Tick_Pixels="", Y_Tick_Count="0",
              Y_Axis_Shared_Candidate="GP001",
              Y_Axis_Shared_Detail="GP001와 같은 행, 프레임 위아래 차 2 px")
OTHER = dict(READ, Proposal_ID="GP004", Raster="other.png")

GP.write_proposals(os.path.join(PROP, GP.PROPOSALS if hasattr(GP, "PROPOSALS")
                                else "geometry_proposal.csv"), [READ, REFUSED, SHARER, OTHER])
#: 오버레이 한 장만 둡니다. 없는 그림이 어떻게 나가는지도 이 페이지의 성질입니다.
_png = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg==")
with io.open(os.path.join(PROP, "GP001.png"), "wb") as fh:
    fh.write(_png)

HTML, COUNT = G.build(PROP, log=lambda *a: None)

print("페이지가 제안을 카드로 내민다")
check("제안마다 카드가 하나", COUNT == 4 and HTML.count("class='doc'") == 4,
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
print("축을 나눠 쓰는 패널을 고를 수 있다")
# REVERT: 답에 "다른 패널 축을 쓴다"가 없다. 이 코퍼스의 Day/Night, 왼쪽/오른쪽
# 열 패널은 눈금도 숫자도 없어서, 그 답이 없으면 사람은 값을 지어내거나
# 보류로 남깁니다.
check("다른 패널 축을 쓴다는 답을 고를 수 있다",
      any(v == "SHARED" for v, _l in G.LABELS) and "value='SHARED'" in HTML)
_sel3 = re.search(r"<select data-shared='GP003'>(.*?)</select>", HTML, re.S).group(1)
check("같은 그림의 다른 패널만 고를 수 있다",
      "value='GP001'" in _sel3 and "value='GP002'" in _sel3
      and "value='GP003'" not in _sel3 and "value='GP004'" not in _sel3, _sel3)
check("리더가 댄 후보는 논리로 건너간다",
      '"sharedCandidate": "GP001"' in HTML or '"sharedCandidate":"GP001"' in HTML)
check("형제 목록도 논리로 건너간다",
      re.search(r'"siblings": \["GP001", "GP002"\]', HTML) is not None
      or '"siblings":["GP001","GP002"]' in HTML)
check("후보와 그 까닭이 카드에 보인다",
      "축 공유 후보:</b> GP001" in HTML and "프레임 위아래 차 2 px" in HTML)
check("후보의 눈금 색이 무슨 뜻인지 적혀 있다", "축 공유 후보 패널의 눈금 행" in HTML)

print()
print("조각은 그림을 자르지 않는다")
# REVERT: 행 수로만 끊는다. 축을 빌리는 패널과 빌려주는 패널이 두 조각에
# 갈리면 답이 두 파일에 갈리고, 관문은 어느 한쪽을 먼저 적을 수 없습니다.
_rows = [dict(Raster="a.png", Proposal_ID="a%d" % i) for i in range(6)] \
      + [dict(Raster="b.png", Proposal_ID="b%d" % i) for i in range(2)] \
      + [dict(Raster="c.png", Proposal_ID="c%d" % i) for i in range(4)]
_chunks = [G.chunk_of(_rows, i, 3) for i in (1, 2, 3)]
check("모든 행이 한 번씩 나간다",
      sorted(r["Proposal_ID"] for c in _chunks for r in c) == sorted(r["Proposal_ID"] for r in _rows))
check("한 그림은 한 조각에 있다",
      all(sum(1 for c in _chunks if any(r["Raster"] == ras for r in c)) == 1
          for ras in ("a.png", "b.png", "c.png")),
      "%s" % [[r["Proposal_ID"] for r in c] for c in _chunks])
check("조각은 순서를 지킨다",
      [r["Proposal_ID"] for c in _chunks for r in c] == [r["Proposal_ID"] for r in _rows])
check("조각 하나면 전부 그대로다", G.chunk_of(_rows, 1, 1) == _rows)
# REVERT: 넘으면 끊는다. 조각마다 조금씩 모자라고, 모자란 만큼이 마지막 조각에
# 쌓입니다 - 975장을 열로 나눴더니 마지막이 183장이었습니다.
_sizes = [20, 20, 20, 45, 20, 20, 45, 20, 20, 45]
_big = [dict(Raster="r%d.png" % g, Proposal_ID="r%d_%d" % (g, i))
        for g, n in enumerate(_sizes) for i in range(n)]
_lens = [len(G.chunk_of(_big, i, 3)) for i in (1, 2, 3)]
check("조각의 크기가 고르다", max(_lens) <= 1.5 * min(_lens), "%s" % _lens)
try:
    G.chunk_of(_rows, 4, 3)
    check("없는 조각을 달라면 멈춘다", False)
except SystemExit as exc:
    check("없는 조각을 달라면 멈춘다", "--chunk" in str(exc), str(exc))
_html2, _n2 = G.build(PROP, log=lambda *a: None, chunk=2, of=2)
check("페이지도 조각으로 나온다", _n2 < COUNT and "2/2" in _html2, "%d" % _n2)

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
