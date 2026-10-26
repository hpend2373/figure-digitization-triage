# -*- coding: utf-8 -*-
"""값 검토 페이지가 사람에게 무엇을 내미는가.

    python3 tests/test_value_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `value_page.js`가 정하고 `test_value_page.mjs`가 봅니다.
여기서 붙잡는 것은 화면의 성질입니다: 겹쳐 그린 그림이 실려 나가는가, 실행
지문이 화면의 칸이 아니라 논리로 건너가는가, 확인 칸이 이름이 아니라 물음으로
적히는가, 그리고 내려받는 이름이 `finalize_batch`가 읽는 파일과 다른가.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import csv
import io
import json
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
with io.open(os.path.join(_paths.CODE, "value_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()

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
print("확인 칸에 적히는 말이 관문이 보는 말과 같다")
# REVERT: 확인 칸에 이 페이지가 고른 낱말을 적는다. `TRUE`라고 적었고 관문은
# `CONFIRMED`를 봅니다 - 사람이 여섯 패널을 다 보고 다 눌렀는데
# `finalize_batch`가 여섯 줄을 전부 되돌려 보냈고, 그 왕복을 사람이 두 번
# 했습니다. 관문의 낱말은 `run_batch`가 정합니다.
import run_batch as RB                                           # noqa: E402
_conf = re.search(r"var CONFIRMED = '([A-Z_]+)'", LOGIC).group(1)
check("확인의 낱말은 run_batch가 정한 것과 같다", _conf == RB.REVIEW_CONFIRMED,
      "페이지 %s / 관문 %s" % (_conf, RB.REVIEW_CONFIRMED))
_asked = set(name for name, _a in V.ASKS)
check("페이지가 묻는 확인은 이 실행 모드가 요구하는 것과 같다",
      _asked == set(RB.REVIEW_CONFIRMATIONS["BAR_MONO_GEOMETRY"]),
      "페이지 %s / 모드 %s"
      % (sorted(_asked), sorted(RB.REVIEW_CONFIRMATIONS["BAR_MONO_GEOMETRY"])))

print()
print("화면과 논리가 같은 어휘를 쓴다")
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

print()
print("실행의 대기열 그대로 (--run): 패널이 요구하는 확인을 run_batch에게 묻는다")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "review"))
for _pid in ("P_AI", "P_R"):
    with io.open(os.path.join(RUN, "review", "%s_overlay.png" % _pid), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + b"\x01" * 8)
_qcols = ("Panel_ID", "Unit_ID", "Mark_Type", "Cells_Read", "Cells_Declared",
          "Review_Mode", "Inference_Cells", "Overlay_File", "Review_Subject_SHA256")
with io.open(os.path.join(RUN, V.QUEUE), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_qcols))
    w.writeheader()
    w.writerow(dict(Panel_ID="P_AI", Unit_ID="U_AI", Mark_Type="BAR_MONO",
                    Cells_Read="2", Cells_Declared="2", Review_Mode="OVERLAY",
                    Inference_Cells="2", Overlay_File="review/P_AI_overlay.png",
                    Review_Subject_SHA256="fp_ai"))
    w.writerow(dict(Panel_ID="P_R", Unit_ID="U_R", Mark_Type="LINE_COLOR",
                    Cells_Read="1", Cells_Declared="1", Review_Mode="OVERLAY",
                    Inference_Cells="0", Overlay_File="review/P_R_overlay.png",
                    Review_Subject_SHA256="fp_r"))
_vcols = ("Run_Panel_ID", "Cell_Key", "Mean", "Dispersion_Value", "Errorbar_Lower",
          "Errorbar_Upper", "Identity_Method", "Value_Method", "Dispersion_Method")
with io.open(os.path.join(RUN, V.MACHINE_QC), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_vcols))
    w.writeheader()
    for _k in ("ARM=A", "ARM=B"):
        w.writerow(dict(Run_Panel_ID="P_AI", Cell_Key=_k, Mean="31.5",
                        Dispersion_Value="2.25", Errorbar_Upper="33.75",
                        Identity_Method="AI_ASSIGNED_SERIES",
                        Value_Method="AI_PLACED_POINT",
                        Dispersion_Method="AI_PLACED_CAP"))
    w.writerow(dict(Run_Panel_ID="P_R", Cell_Key="ARM=A", Mean="12",
                    Dispersion_Value="1", Identity_Method="MEASURED_COLOUR",
                    Value_Method="MARKER_CENTER",
                    Dispersion_Method="DIRECT_CONNECTED_CAP"))
RHTML, RCOUNT = V.build_run(RUN, when="2026-10-18", log=lambda *a: None)
_meta = json.loads(re.search(r"var META = (\{.*?\});", RHTML, re.S).group(1))
check("대기열의 패널마다 카드가 하나, 겹친 그림이 실린다",
      RCOUNT == 2 and RHTML.count("class='doc'") == 2
      and RHTML.count("data:image/png;base64,") == 2, RCOUNT)
# REVERT: 확인 칸을 이 페이지가 고정해서 묻는다. AI가 놓은 점의 패널은
# `Inference_Checked`가 없으면 `finalize_batch`가 하나도 받지 않고, 사람은 다
# 보고 다 누른 뒤에야 그것을 압니다.
check("AI가 놓은 점의 패널은 점을 보았다는 확인을 요구한다",
      _meta["P_AI"]["required"] == ["Marks_Checked", "Inference_Checked"],
      _meta["P_AI"]["required"])
check("판독기가 읽은 패널은 모드가 요구하는 것만",
      _meta["P_R"]["required"] == ["Marks_Checked"], _meta["P_R"]["required"])
check("실행 지문은 대기열의 것이 META로 간다",
      _meta["P_AI"]["subject"] == "fp_ai" and _meta["P_R"]["subject"] == "fp_r"
      and "data-subject" not in RHTML)
check("AI가 놓은 점이라고 카드가 말하고, 물음도 그렇게 적힌다",
      "AI가 놓은 점 2개" in RHTML and V.RUN_ASKS["Inference_Checked"] in RHTML
      and RHTML.count("AI가 놓은 점 ") == 1, "")
check("값이 표로 함께 보인다", "31.5" in RHTML and "33.75" in RHTML)
check("실행 페이지도 본 날짜를 심는다",
      re.search(r"var WHEN = \"2026-10-18\";", RHTML) is not None,
      re.findall(r"var WHEN = [^;]*;", RHTML))
_nofig = V.run_card(RUN, dict(Panel_ID="P_X", Unit_ID="U_X", Mark_Type="LINE_COLOR",
                              Cells_Read="1", Cells_Declared="1", Overlay_File=""),
                    [], ["Marks_Checked"])
check("겹쳐 그린 그림이 없는 실행 카드는 그렇다고 말한다",
      "겹쳐 그린 그림 없음" in _nofig and "<img" not in _nofig, _nofig[:200])
try:
    V.main(["--values", VALS, "--run", RUN, "--out", os.path.join(TMP, "x.html")])
    check("--values와 --run은 함께 받지 않는다", False, "받았다")
except SystemExit as exc:
    check("--values와 --run은 함께 받지 않는다", exc.code == 2, exc.code)
_empty_run = os.path.join(TMP, "empty_run")
os.makedirs(_empty_run)
try:
    V.build_run(_empty_run, log=lambda *a: None)
    check("대기열이 없으면 멈추고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("대기열이 없으면 멈추고 말한다", "검토할 패널이 없습니다" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
