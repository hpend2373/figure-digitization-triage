# -*- coding: utf-8 -*-
"""정체 판정 관문이 무엇을 적고 무엇을 거절하는가.

    python3 test_record_identity.py     # exit 0 = all scenarios pass
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import identity_proposer as IP                                   # noqa: E402
import record_identity as R                                      # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-record-identity-")
PROP = os.path.join(TMP, "ip")
os.makedirs(PROP)

PROPOSED = {c: "" for c in IP.IDENTITY_COLUMNS}
PROPOSED.update({"Proposal_ID": "GP001", "Raster": "fig.png", "Region": "20,20,760,540",
                 "Panel_X0": "100", "Panel_X1": "700", "Panel_Y0": "60", "Panel_Y1": "460",
                 "Panel_Kind": "BAR", "X_Label_Read_Status": IP.READ_OK,
                 "X_Labels_Read": "Pre@175;D1@325", "Series_Read_Status": IP.READ_OK,
                 "Series_Read": "Fluid@220,40,40;Control@40,80,220", "Mark_Type_Proposed": "BAR_COLOR",
                 "Outcome_Read": "Heart rate", "Unit_Read": "bpm", "Human_Verification_Status": IP.PENDING})
IP.write_proposals(os.path.join(PROP, R.PROPOSALS),
                   [PROPOSED, dict(PROPOSED, Proposal_ID="GP002", Panel_Kind="LINE", Mark_Type_Proposed="LINE_COLOR"),
                    dict(PROPOSED, Proposal_ID="GP003", Panel_Kind="BOX", Mark_Type_Proposed="BOX_VIOLIN")])

LABELS = json.dumps([{"label": "Pre", "px": 175}, {"label": "D1", "px": 325}])
SERIES = json.dumps([{"name": "Fluid", "colour": "#DC2828", "line_style": "", "marker": "", "marker_fill": "", "bar_fill": ""},
                     {"name": "Control", "colour": "#2850DC", "line_style": "", "marker": "", "marker_fill": "", "bar_fill": ""}])


def answer(**over):
    row = {"Proposal_ID": "GP001", "Human_Verification_Status": "CONFIRMED", "X_Factor": "TIMEPOINT",
           "X_Labels": LABELS, "Series_Factor": "ARM", "Series": SERIES, "Mark_Type": "BAR_COLOR",
           "Outcome_Name": "Heart rate", "Unit": "bpm", "N_Outcome": "8",
           "Bar_Top_Definition": "OUTLINE_CENTER", "Errorbar_Stem_Confirmed": "TRUE",
           "Verified_By": "MC", "Seen_By_Person": "1", "Value_Sources": "x:READ", "Note": ""}
    row.update(over)
    return row


def series(*entries):
    return json.dumps([dict({"name": "", "colour": "", "line_style": "", "marker": "", "marker_fill": "", "bar_fill": ""}, **e)
                       for e in entries])


def run(answers, **kw):
    out = kw.pop("out_path", os.path.join(TMP, "out.csv"))
    if os.path.exists(out):
        os.remove(out)
    return R.record(PROP, answers, "2026-09-18", out_path=out, log=lambda *a: None, **kw)


def codes(refused):
    return [c for _n, problems in refused for c, _w in problems]


print("사람이 보고 이름을 댄 답은 적힌다")
_w, _r, _p = run([answer()])
check("한 줄이 적힌다", len(_w) == 1 and not _r, "%s %s" % (len(_w), codes(_r)))
check("제안의 열 위에 사람의 것이 얹힌다",
      _w and _w[0]["X_Factor"] == "TIMEPOINT" and _w[0]["X_Labels"] == LABELS and _w[0]["Mark_Type"] == "BAR_COLOR"
      and _w[0]["Outcome_Name"] == "Heart rate" and _w[0]["N_Outcome"] == "8" and _w[0]["Verified_At"] == "2026-09-18"
      and _w[0]["X_Labels_Read"] == "Pre@175;D1@325", "%s" % ({k: _w[0].get(k) for k in ("X_Factor", "Mark_Type")} if _w else None,))
with io.open(_p, encoding="utf-8") as fh:
    _back = list(csv.DictReader(fh))
check("적힌 파일은 제안의 모양 그대로다", list(_back[0].keys()) == list(IP.IDENTITY_COLUMNS) and _back[0]["Human_Verification_Status"] == "CONFIRMED")
check("거절도 적힌다, 값 없이",
      (lambda w: len(w) == 1 and w[0]["X_Factor"] == "" and w[0]["Human_Verification_Status"] == "REJECTED")(
          run([answer(Human_Verification_Status="REJECTED", X_Factor="", X_Labels="", Series="", Outcome_Name="")])[0]))
check("보류는 적히지 않는다", "HELD" in codes(run([answer(Human_Verification_Status="HOLD")])[1]))

print()
print("이 관문이 지키는 것은 누가 보았는가다")
check("보지 않은 답은 거절한다", "NOT_SEEN_BY_PERSON" in codes(run([answer(Seen_By_Person="")])[1]))
check("이름 없는 답은 거절한다", "UNATTRIBUTED" in codes(run([answer(Verified_By="")])[1]))
check("모르는 답은 거절한다", "BAD_VERDICT" in codes(run([answer(Human_Verification_Status="MAYBE")])[1]))
check("낸 적 없는 제안은 거절한다", "NOT_PROPOSED" in codes(run([answer(Proposal_ID="GP999")])[1]))

print()
print("확인은 계획서가 설 수 있는 정체를 들고 와야 한다")
# REVERT: x 요인 없이 적는다. 격자가 설 이름이 없고, 계획서는 그 자리를 짐작할 수 없습니다.
check("x 요인이 없으면 거절한다", "X_FACTOR_MISSING" in codes(run([answer(X_Factor="")])[1]))
check("요인 이름은 대문자·숫자·밑줄이어야 한다", "FACTOR_NAME_BAD" in codes(run([answer(X_Factor="time point")])[1]))
check("한 요인이 두 축에 있으면 거절한다", "FACTOR_ON_BOTH_AXES" in codes(run([answer(Series_Factor="TIMEPOINT")])[1]))
check("계열 요인이 없으면 거절한다", "SERIES_FACTOR_MISSING" in codes(run([answer(Series_Factor="")])[1]))
# REVERT: 하나뿐인 계열은 요인·이름 없이 받는다. 수준 없는 계열은 Cell_Key가 되지 못합니다.
check("계열이 하나여도 요인은 있어야 한다",
      "SERIES_FACTOR_MISSING" in codes(run([answer(Series_Factor="", Series=series({"name": "ALL", "colour": "#DC2828"}))])[1]))
check("계열이 하나여도 이름(수준)은 있어야 한다",
      "SERIES_NAME_MISSING" in codes(run([answer(Series_Factor="GROUP", Series=series({"name": "", "colour": "#DC2828"}))])[1]))
check("요인과 이름이 있는 계열 하나는 된다",
      not run([answer(Series_Factor="GROUP", Series=series({"name": "ALL", "colour": "#DC2828"}))])[1],
      "%s" % codes(run([answer(Series_Factor="GROUP", Series=series({"name": "ALL", "colour": "#DC2828"}))])[1]))
check("x 위치가 없으면 거절한다", "X_POSITIONS_MISSING" in codes(run([answer(X_Labels="[]")])[1]))
check("JSON이 아닌 위치는 거절한다", "X_Labels_NOT_JSON" in codes(run([answer(X_Labels="Pre@175")])[1]))
check("빈 라벨은 거절한다", "X_LABEL_MISSING" in codes(run([answer(X_Labels=json.dumps([{"label": "", "px": 175}]))])[1]))
# REVERT: 같은 라벨 둘을 받는다. 두 자리가 한 셀에 적힙니다.
check("같은 라벨 둘은 거절한다",
      "X_LABEL_DUPLICATE" in codes(run([answer(X_Labels=json.dumps([{"label": "Pre", "px": 175}, {"label": "pre", "px": 325}]))])[1]))
check("픽셀이 수가 아니면 거절한다", "X_PIXEL_MISSING" in codes(run([answer(X_Labels=json.dumps([{"label": "Pre", "px": "x"}]))])[1]))
check("프레임 밖의 위치는 거절한다",
      "X_PIXEL_OUTSIDE_FRAME" in codes(run([answer(X_Labels=json.dumps([{"label": "Pre", "px": 175}, {"label": "Far", "px": 900}]))])[1]))
check("프레임 가장자리를 조금 넘는 위치는 받는다",
      not run([answer(X_Labels=json.dumps([{"label": "Pre", "px": 95}, {"label": "D1", "px": 325}]))])[1])
check("계열이 없으면 거절한다", "SERIES_MISSING" in codes(run([answer(Series="[]")])[1]))
check("표 종류가 어휘 밖이면 거절한다", "MARK_TYPE_BAD" in codes(run([answer(Mark_Type="BAR_RAINBOW")])[1]))
# REVERT: 세어진 종류와 다른 표 종류를 받는다. BAR로 센 패널이 SCATTER로 읽히면 x가 데이터가 됩니다.
check("세어진 종류에 맞지 않는 표 종류는 거절한다",
      "MARK_TYPE_NOT_FOR_KIND" in codes(run([answer(Mark_Type="SCATTER", Bar_Top_Definition="")])[1]))
check("LINE 패널은 LINE_MONO_STYLE도 된다",
      not run([answer(Proposal_ID="GP002", Mark_Type="LINE_MONO_STYLE", Bar_Top_Definition="",
                      Series=series({"name": "A", "line_style": "SOLID"}, {"name": "B", "line_style": "DASHED"}))])[1],
      "%s" % codes(run([answer(Proposal_ID="GP002", Mark_Type="LINE_MONO_STYLE", Bar_Top_Definition="",
                               Series=series({"name": "A", "line_style": "SOLID"}, {"name": "B", "line_style": "DASHED"}))])[1]))
check("색으로 가르는 표에 색 없는 계열은 거절한다",
      "SERIES_COLOUR_MISSING" in codes(run([answer(Series=series({"name": "A", "colour": "#DC2828"}, {"name": "B"}))])[1]))
check("색은 #RRGGBB여야 한다", "SERIES_COLOUR_BAD" in codes(run([answer(Series=series({"name": "A", "colour": "red"}, {"name": "B", "colour": "#2850DC"}))])[1]))
check("선 모양으로 가르는 표에 선 모양 없는 계열은 거절한다",
      "SERIES_DISCRIMINANT_MISSING" in codes(run([answer(Proposal_ID="GP002", Mark_Type="LINE_MONO_STYLE", Bar_Top_Definition="",
                                                         Series=series({"name": "A", "line_style": "SOLID"}, {"name": "B"}))])[1]))
check("모르는 모양은 거절한다",
      "SERIES_STYLE_UNKNOWN" in codes(run([answer(Proposal_ID="GP002", Mark_Type="LINE_MONO_STYLE", Bar_Top_Definition="",
                                                  Series=series({"name": "A", "line_style": "WAVY"}, {"name": "B", "line_style": "DASHED"}))])[1]))
check("두 계열을 가를 것이 없으면 거절한다",
      "SERIES_NOT_SEPARABLE" in codes(run([answer(Series=series({"name": "A", "colour": "#DC2828"}, {"name": "B", "colour": "#dc2828"}))])[1]))
check("같은 계열 이름 둘은 거절한다",
      "SERIES_NAME_DUPLICATE" in codes(run([answer(Series=series({"name": "A", "colour": "#DC2828"}, {"name": "a", "colour": "#2850DC"}))])[1]))
check("이름 없는 계열은 거절한다",
      "SERIES_NAME_MISSING" in codes(run([answer(Series=series({"name": "", "colour": "#DC2828"}, {"name": "B", "colour": "#2850DC"}))])[1]))
# REVERT: 결과변수 없이 적는다. 값이 무엇의 값인지 없는 단위입니다.
check("결과변수가 없으면 거절한다", "OUTCOME_MISSING" in codes(run([answer(Outcome_Name="")])[1]))
check("n은 비워도 된다", not run([answer(N_Outcome="")])[1])
check("n이 양의 정수가 아니면 거절한다", "N_BAD" in codes(run([answer(N_Outcome="8.5")])[1]) and "N_BAD" in codes(run([answer(N_Outcome="0")])[1]))
check("막대 표에 값 정의가 없으면 거절한다", "BAR_TOP_MISSING" in codes(run([answer(Bar_Top_Definition="")])[1]))
check("상자 표에는 값 정의를 묻지 않는다",
      not run([answer(Proposal_ID="GP003", Mark_Type="BOX_VIOLIN", Bar_Top_Definition="", Errorbar_Stem_Confirmed="",
                      Series_Factor="GROUP", Series=series({"name": "ALL", "colour": "#DC2828"}))])[1],
      "%s" % codes(run([answer(Proposal_ID="GP003", Mark_Type="BOX_VIOLIN", Bar_Top_Definition="", Errorbar_Stem_Confirmed="",
                               Series_Factor="GROUP", Series=series({"name": "ALL", "colour": "#DC2828"}))])[1]))
check("줄기 확인은 TRUE/FALSE여야 한다", "STEM_BAD" in codes(run([answer(Errorbar_Stem_Confirmed="maybe")])[1]))

print()
print("두 번 적지 않는다, 그리고 자기 출력을 답으로 읽지 않는다")
_out = os.path.join(TMP, "twice.csv")
R.record(PROP, [answer()], "2026-09-18", out_path=_out, log=lambda *a: None)
_w2, _r2, _ = R.record(PROP, [answer(X_Factor="SESSION")], "2026-09-19", out_path=_out, log=lambda *a: None)
check("이미 적힌 제안은 --replace 없이 거절한다", not _w2 and "ALREADY_RECORDED" in codes(_r2))
_w3, _r3, _ = R.record(PROP, [answer(X_Factor="SESSION")], "2026-09-19", out_path=_out, replace=True, log=lambda *a: None)
check("--replace면 바뀐다", len(_w3) == 1 and _w3[0]["X_Factor"] == "SESSION")
try:
    R.record(PROP, [answer()], "2026-09-18", out_path=_out, answers_path=_out, log=lambda *a: None)
    check("답 파일과 적는 파일이 같으면 멈춘다", False, "멈추지 않았다")
except SystemExit as exc:
    check("답 파일과 적는 파일이 같으면 멈춘다", "같습니다" in str(exc), str(exc))
try:
    R.record(PROP, [{"Proposal_ID": "GP001"}], "2026-09-18", out_path=_out, log=lambda *a: None)
    check("빠진 열을 이름 대고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("빠진 열을 이름 대고 말한다", "Human_Verification_Status" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
