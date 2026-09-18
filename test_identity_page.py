# -*- coding: utf-8 -*-
"""정체 확인 페이지가 사람에게 무엇을 내미는가.

    python3 test_identity_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `identity_page.js`가 정하고 `test_identity_page.mjs`가
봅니다. 여기서 붙잡는 것은 화면의 성질입니다: 읽은 것이 화면의 칸이 아니라
논리로 건너가는가, 거절이 왜인지까지 보이는가, 화면의 선택지와 논리의 어휘가
같은가, 내려받는 이름이 관문의 출력과 다른가.
"""
import base64
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import identity_page as G                                        # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import record_identity as R                                      # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-identity-page-")
PROP = os.path.join(TMP, "ip")
os.makedirs(PROP)

READ = {c: "" for c in IP.IDENTITY_COLUMNS}
READ.update({
    "Proposal_ID": "GP001", "Raster": "fig.png", "Region": "20,20,760,540",
    "Panel_X0": "100", "Panel_X1": "700", "Panel_Y0": "60", "Panel_Y1": "460", "Spine_X": "100",
    "Panel_Kind": "BAR", "X_Anchor_Pixels": "175;325;475;625", "X_Anchor_Count": "4",
    "X_Label_Read_Status": IP.READ_OK, "X_Labels_Read": "Pre@175;D1@325;D3@475;R0@625",
    "X_Label_Detail": "4 labels; frame anchors agree",
    "Series_Colours": "220,40,40;40,80,220", "Series_Colour_Count": "2",
    "Series_Read_Status": IP.READ_OK, "Series_Read": "Fluid@220,40,40;Control@40,80,220",
    "Series_Detail": "2 legend entries, one per plot colour", "Mark_Type_Proposed": "BAR_COLOR",
    "Y_Title_Read_Status": IP.READ_OK, "Y_Title_Read": "Heart rate (bpm)", "Outcome_Read": "Heart rate",
    "Unit_Read": "bpm", "Y_Title_Detail": "bottom-up, conf 88",
    "N_Read_Status": IP.READ_OK, "N_Read": "8", "N_Detail": "n = 8 in the caption",
    "Human_Verification_Status": IP.PENDING,
})
REFUSED = dict(READ, Proposal_ID="GP002", X_Label_Read_Status=IP.READ_REFUSED, X_Labels_Read="",
               X_Label_Detail="labels are not at one pitch (gap cv 0.34: 99, 210)",
               Series_Read_Status=IP.READ_REFUSED, Series_Read="",
               Series_Detail="no chromatic ink in the plot; series are not told apart by colour",
               Mark_Type_Proposed="BAR_MONO", Y_Title_Read_Status=IP.READ_REFUSED, Y_Title_Read="",
               Outcome_Read="", Unit_Read="", Y_Title_Detail="tesseract read no word in the title strip",
               N_Read_Status=IP.READ_REFUSED, N_Read="", N_Detail="the caption prints no n =")
WARNED = dict(READ, Proposal_ID="GP003", Panel_Kind="LINE", Mark_Type_Proposed="LINE_COLOR",
              X_Label_Detail="4 labels; frame anchors disagree")
OTHER = dict(READ, Proposal_ID="GP004", Raster="other.png")
IP.write_proposals(os.path.join(PROP, IP.PROPOSALS), [READ, REFUSED, WARNED, OTHER])
_png = base64.b64decode(b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
with io.open(os.path.join(PROP, "GP001.png"), "wb") as fh:
    fh.write(_png)

HTML, COUNT = G.build(PROP, log=lambda *a: None)

print("페이지가 제안을 카드로 내민다")
check("제안마다 카드가 하나", COUNT == 4 and HTML.count("class='doc'") == 4, "%s / %s" % (COUNT, HTML.count("class='doc'")))
check("오버레이가 있으면 그림으로 실린다", "data:image/png;base64," in HTML)
# REVERT: 오버레이가 없어도 조용히 넘어간다. 확인할 그림이 없는 카드는 확인을 청하는 카드가 아닙니다.
check("오버레이가 없으면 없다고 말한다", "오버레이 없음" in HTML)

print()
print("리더가 읽은 것과 못 읽은 것을 다르게 내민다")
_c1 = HTML[HTML.index("id='p-GP001'"):HTML.index("id='p-GP002'")]
_c2 = HTML[HTML.index("id='p-GP002'"):HTML.index("id='p-GP003'")]
_c3 = HTML[HTML.index("id='p-GP003'"):HTML.index("id='p-GP004'")]
check("읽은 x 라벨이 보인다", "리더가 읽은 x 라벨" in _c1 and "Pre · D1 · D3 · R0" in _c1)
check("읽은 계열이 보인다", "Fluid · Control" in _c1)
check("읽은 y축 제목과 n이 보인다", "Heart rate (bpm)" in _c1 and "캡션의 n:</b> 8" in _c1, _c1[_c1.find("캡션의 n"):][:60])
# REVERT: 거절을 흠으로만 적고 왜인지는 감춘다. 사람은 자기가 무엇을 고치는지 모르는 채로 적습니다.
check("거절한 것은 왜 거절했는지까지 보인다",
      "리더가 읽지 못했습니다" in _c2 and "gap cv 0.34" in _c2 and "no chromatic ink" in _c2
      and "no word in the title strip" in _c2 and "prints no n" in _c2)
check("거절한 카드에는 무엇을 적어야 하는지 적혀 있다", "x 위치를 찍고 라벨을 적어 주세요" in _c2 and "범례를 보고 계열을 적어 주세요" in _c2)
# REVERT: 앵커와 어긋난 읽기를 여느 읽기처럼 낸다. 앵커는 라벨의 수와 자리를 다시 볼 이유입니다.
check("앵커와 어긋난 읽기는 먼저 보라고 말한다", "먼저 보세요" in _c3 and "먼저 보세요" not in _c1)

print()
print("읽은 것은 화면의 칸이 아니라 논리로 건너간다")
_out = re.search(r"data-outcome='GP001'[^>]*>", HTML).group(0)
# REVERT: 읽은 값을 입력 칸에 미리 채운다. 사람이 고치지 않은 값과 친 값이 구별되지 않습니다.
check("결과변수 칸은 비어서 나가고 읽은 것은 자리 표시로만 보인다", "value=" not in _out and "placeholder='Heart rate'" in _out, _out)
check("읽은 라벨·계열·제목·n이 META로 건너간다",
      '"readLabels": "Pre@175;D1@325;D3@475;R0@625"' in HTML and '"readSeries": "Fluid@220,40,40;Control@40,80,220"' in HTML
      and '"readOutcome": "Heart rate"' in HTML and '"readN": "8"' in HTML)
check("리더가 제안한 표 종류와 고를 수 있는 종류가 건너간다",
      '"markProposed": "BAR_COLOR"' in HTML and '"markChoices": ["BAR_COLOR", "BAR_MONO"]' in HTML
      and '"markChoices": ["LINE_COLOR", "LINE_MONO", "LINE_MONO_STYLE"]' in HTML)
check("프레임과 원점이 건너간다 - 찍은 x 위치를 래스터 열로 옮기는 데 필요하다",
      '"frameX0": "100"' in HTML and '"originX": 8' in HTML)
check("찾은 색이 건너간다 - 사람이 계열에 색을 붙일 수 있게", '"colours": [[220, 40, 40], [40, 80, 220]]' in HTML)

print()
print("화면과 논리와 관문이 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "identity_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_js = set(re.findall(r"'([A-Z_]+)'", re.search(r"var VERDICTS = \[(.*?)\]", LOGIC, re.S).group(1)))
check("고를 수 있는 답이 곧 답이 되는 답이다", set(v for v, _l in G.LABELS) == _js == set(R.VERDICTS),
      "화면 %s / 논리 %s / 관문 %s" % (sorted(set(v for v, _l in G.LABELS)), sorted(_js), R.VERDICTS))
_marks = set(re.findall(r"'([A-Z_]+)'", re.search(r"var MARK_TYPES = \[(.*?)\]", LOGIC, re.S).group(1)))
import batch_manifests as BM                                     # noqa: E402
check("논리의 표 종류는 배치층의 것과 같다", _marks == set(BM.BATCH_MARK_TYPES), "%s" % sorted(_marks))
check("판정 논리가 페이지 안에 들어 있다", "function verdictOf(" in HTML)
check("내려받는 이름은 관문이 적는 이름과 다르다", "identity_answers.csv" in HTML and R.DECISIONS not in HTML)
_cols = re.search(r"var CSV_COLUMNS = \[(.*?)\]", LOGIC, re.S).group(1)
check("관문이 요구하는 열이 전부 나간다", all(("'%s'" % c) in _cols for c in R.ANSWER_REQUIRED))

print()
print("사람만 적는 것이 물어져 있다")
check("x 요인과 계열 요인을 묻는다", "data-xfactor='GP001'" in _c1 and "data-sfactor='GP001'" in _c1)
check("막대의 값을 어디서 읽는지와 오차막대 줄기를 묻는다", "data-bartop='GP001'" in _c1 and "data-stem='GP001'" in _c1)
check("x 위치를 찍고 계열을 더할 수 있다", "data-arm-x='GP001'" in _c1 and "data-s-add='GP001'" in _c1)
check("목격과 이름을 묻는다", "data-seen='GP001'" in _c1 and "data-who='GP001'" in _c1)

print()
print("조각")
_html2, _n2 = G.build(PROP, log=lambda *a: None, chunk=2, of=2)
check("조각은 그림 단위로 나뉜다", _n2 == 1 and "GP004" in _html2 and "id='p-GP001'" not in _html2, "%s" % _n2)

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
