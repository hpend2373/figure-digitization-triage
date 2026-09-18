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
    "Proposal_ID": "GP001", "Raster": "fig.png", "Region": "40,30,220,180",
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
#: 그리고 리더가 프레임을 못 찾은 패널 하나. 제안이 아니라 거절 목록에 있고,
#: 그림은 같은 그림입니다 - 조각을 나눌 때 그 그림과 함께 가야 합니다.
NOFRAME = GP.refusal_row("GP006", "fig.png", "abc", (300, 30, 480, 180),
                         detail="영역 안에 축선이 하나도 없습니다", note="D1 p6 LINE")
GP.write_refusals(os.path.join(PROP, GP.REFUSED), [NOFRAME])
#: 오버레이 한 장만 둡니다. 없는 그림이 어떻게 나가는지도 이 페이지의 성질입니다.
_png = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg==")
with io.open(os.path.join(PROP, "GP001.png"), "wb") as fh:
    fh.write(_png)

HTML, COUNT = G.build(PROP, log=lambda *a: None)

print("페이지가 제안을 카드로 내민다")
check("제안마다 카드가 하나, 프레임 없는 패널도 하나",
      COUNT == 5 and HTML.count("class='doc'") == 5,
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
check("형제 목록도 논리로 건너간다 - 프레임 없는 패널도 같은 그림의 형제다",
      re.search(r'"siblings": \["GP001", "GP002", "GP006"\]', HTML) is not None
      or '"siblings":["GP001","GP002","GP006"]' in HTML)
check("후보와 그 까닭이 카드에 보인다",
      "축 공유 후보:</b> GP001" in HTML and "프레임 위아래 차 2 px" in HTML)
check("후보의 눈금 색이 무슨 뜻인지 적혀 있다", "축 공유 후보 패널의 눈금 행" in HTML)

print()
print("눈금을 못 잰 패널은 사람이 그림에 찍는다")
# REVERT: 찍을 수 없다. 프레임은 맞는데 눈금이 없거나 안 잡힌 패널은 값을 붙일
# 행이 없어서 막힙니다 - 975장 중 108장.
check("그림에 찍는 단추와 찍은 줄이 카드에 있다",
      "data-arm-top='GP001'" in HTML and "data-arm-bottom='GP001'" in HTML
      and "data-mark-top='GP001'" in HTML and "data-unpick='GP001'" in HTML)
check("눈금 없는 패널은 위·아래 둘 다 그렇다고 말한다",
      re.search(r"data-id='GP003'.*?data-id='GP004'", HTML, re.S).group(0).count("(잰 눈금 없음)") == 2)
# REVERT: 오버레이의 원점을 페이지가 짐작한다. 찍은 줄이 전부 여백만큼 어긋납니다.
_origin = GP.overlay_origin(READ)
check("오버레이의 원점은 제안 모듈이 말한 대로 논리로 건너간다",
      _origin[1] > 0 and (('"originY": %d' % _origin[1]) in HTML or ('"originY":%d' % _origin[1]) in HTML),
      "%s" % (_origin,))
check("프레임의 위·아래 행도 건너간다",
      ('"frameTop": "5"' in HTML or '"frameTop":"5"' in HTML)
      and ('"frameBottom": "150"' in HTML or '"frameBottom":"150"' in HTML))
check("찍은 줄이 프레임 밖이면 어떻게 하라는지 적혀 있다",
      "프레임 밖이면" in HTML.split("<script>")[0])

print()
print("안내는 접을 수 있고, 처음에는 펴져 있다")
# 안내 다섯 문단과 색 설명은 처음 한 번 읽는 것이고, 그 뒤로는 화면의 절반을
# 차지합니다. REVERT: 처음부터 접어 둔다 - 처음 보는 사람이 읽지 않은 채로
# 시작하면 이 페이지의 규칙(목격, 이름, 지어내지 않기)을 모릅니다.
_head = HTML.split("</header>")[0]
_guide = re.search(r"<div id='guide'>(.*?)</div>", _head, re.S)
check("안내와 색 설명이 접히는 자리에 함께 들어 있다",
      _guide is not None and _guide.group(1).count("class='note'") >= 4
      and "class='key'" in _guide.group(1))
check("접는 단추가 있다", "id='guidetoggle'" in _head)
check("처음 열면 펴져 있다", "<div id='guide'>" in _head and "<div id='guide' hidden" not in _head)
# REVERT: 접힘을 답과 같은 자리에 저장한다. 보기의 상태이지 사람이 이 패널들에
# 대해 한 말이 아닙니다.
check("접힘은 답과도 숨김과도 다른 자리에 저장된다",
      "'fdt_geometry_guide'" in HTML)
check("내려받기와 세는 것은 안내를 보지 않는다",
      "guideShut" not in re.search(r"q\('#dl'\)\.addEventListener\(.*?\}\);", HTML, re.S).group(0))

print()
print("본 패널은 치울 수 있고, 치워도 답이다")
# 95장을 한 화면에서 보면 본 것과 안 본 것이 섞입니다. 숨김은 보는 사람의
# 편의이고 답이 아닙니다 - 숨긴 카드도 세어지고 내려받기에 나갑니다.
check("카드마다 숨기기 단추가 있다", HTML.count("data-hide='") == COUNT)
check("답이 된 것을 한꺼번에 숨기고 도로 볼 수 있다",
      "id='hidedone'" in HTML and "id='showall'" in HTML)
# REVERT: 숨긴 카드를 내려받기에서 뺀다. 화면이 판정을 하는 것이고, 본 사람은
# 자기가 뺐다는 것을 모릅니다.
_dl = re.search(r"q\('#dl'\)\.addEventListener\(.*?\}\);", HTML, re.S).group(0)
check("내려받기는 숨김을 보지 않는다", "hiddenIds" not in _dl and "buildCsv(IDS, states)" in _dl)
check("숨김이 답과 다른 자리에 저장된다", "'fdt_geometry_hidden'" in HTML)

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
print("리더가 자기 읽기를 의심하면 그 패널을 맨 앞에 댄다")
# REVERT: 경고를 카드에만 적거나, 어디에도 적지 않는다. 경고는 판정이 아니라
# "먼저 보세요"이고, 카드는 래스터 순서 그대로라 맨 앞의 이름표가 없으면
# 사람은 27장을 찾아 스크롤한다.
check("의심이 없는 페이지에는 그 말이 없다", "먼저 보세요" not in HTML)
_wdir = os.path.join(TMP, "warned")
os.makedirs(_wdir)
WARNED = dict(READ, Proposal_ID="GP005",
              Y_Tick_Read_Values="190@10;100@50;20@90",
              Y_Tick_Read_Warning="TICK_STEP_UNEVEN: value per tick varies 11.8% "
                                  "(90, 80) though the labels sit on evenly spaced ticks")
OFF = dict(READ, Proposal_ID="GP006",
           Y_Tick_Read_Warning="LABELS_OFF_THE_TICKS: the 3 labels read sit on none of "
                               "the 5 ticks measured")
UNKNOWN = dict(READ, Proposal_ID="GP007", Y_Tick_Read_Warning="SOMETHING_NEW: a detail")
GP.write_proposals(os.path.join(_wdir, "geometry_proposal.csv"), [READ, WARNED, OFF, UNKNOWN])
_whtml, _wn = G.build(_wdir, log=lambda *a: None)
_front = _whtml[:_whtml.index("<main>")]
check("맨 앞에 의심하는 패널의 수와 이름이 있다",
      "의심하는 패널 3개" in _front and "GP005" in _front and "GP006" in _front
      and "GP007" in _front and "GP001" not in _front, _front[-400:])
check("이름은 그 카드로 건너뛰는 링크다",
      "href='#p-GP005'" in _front and "id='p-GP005'" in _whtml)
_card5 = _whtml[_whtml.index("id='p-GP005'"):_whtml.index("id='p-GP006'")]
check("카드에는 사람의 말로 적혀 있고 리더의 근거가 딸려 있다",
      "먼저 보세요" in _card5 and "눈금 한 칸당 값이 일정하지 않습니다" in _card5
      and "11.8%" in _card5, _card5[:600])
_card6 = _whtml[_whtml.index("id='p-GP006'"):_whtml.index("id='p-GP007'")]
check("눈금 밖의 라벨은 그렇게 적혀 있다", "어느 눈금과도 맞지 않습니다" in _card6)
_card7 = _whtml[_whtml.index("id='p-GP007'"):]
check("모르는 코드는 숨기지 않고 코드 그대로 보인다", "SOMETHING_NEW" in _card7)
_card1 = _whtml[_whtml.index("id='p-GP001'"):_whtml.index("id='p-GP005'")]
check("의심이 없는 카드에는 아무것도 붙지 않는다", "먼저 보세요" not in _card1)
check("경고가 있어도 읽은 값은 그대로 논리로 건너간다",
      '"readPairs": "190@10;100@50;20@90"' in _whtml)

print()
print("프레임을 못 찾은 패널도 카드로 나가고, 사람이 프레임을 그린다")
# REVERT: 거절 목록은 페이지에 없다. 975장 중 33장이 두 파일 사이에서 조용히
# 빠지고, 페이지를 다 답해도 그 33장은 영영 없습니다.
_c6 = HTML[HTML.index("id='p-GP006'"):]
_c6 = _c6[:_c6.index("</main>")]
check("프레임 없는 카드가 있고 왜 없는지 말한다",
      "프레임 없음" in _c6 and "축선이 하나도 없습니다" in _c6 and "프레임을 찾지 못했습니다" in _c6)
check("그리는 단추가 있다", "data-arm-frame='GP006'" in _c6 and "프레임 그리기" in _c6)
check("제안 카드에도 다시 그리는 단추가 있다", "data-arm-frame='GP001'" in HTML and "프레임 다시 그리기" in HTML)
check("프레임 없는 카드임과 그 영역이 논리로 건너간다",
      ('"noFrame": true' in HTML or '"noFrame":true' in HTML)
      and ('"region": "300,30,480,180"' in HTML or '"region":"300,30,480,180"' in HTML))
check("프레임 없는 카드의 답도 같은 어휘다",
      set(v for v, _l in G.LABELS_NO_FRAME) == set(v for v, _l in G.LABELS)
      and "읽을 플롯이 없다" in _c6)
check("먼저 그려야 하는 패널을 앞에서 이름 댄다", "프레임을 그려야 하는 패널 1개" in HTML)
check("그린 프레임의 뜻이 색 설명에 있다", "사람이 그린 프레임" in HTML)
_ref_rows = [dict(NOFRAME, _no_frame=True)]
_mix = [READ, OTHER, SHARER] + _ref_rows
_by_chunk = [G.chunk_of(_mix, i, 2) for i in (1, 2)]
check("프레임 없는 패널은 자기 그림의 조각에 든다",
      all(len({r["Raster"] for r in c}) <= 1 for c in _by_chunk)
      and any("GP006" in [r["Proposal_ID"] for r in c] and "GP001" in [r["Proposal_ID"] for r in c]
              for c in _by_chunk),
      "%s" % [[r["Proposal_ID"] for r in c] for c in _by_chunk])

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
