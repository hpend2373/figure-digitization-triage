# -*- coding: utf-8 -*-
"""패널 판정 관문이 무엇을 적고 무엇을 거절하는가.

    python3 test_record_panels.py     # exit 0 = all scenarios pass

`panel_page.js`는 브라우저 안에서 무엇이 답이 되는지를 정하고, 이 관문은 그
답이 파일에 적힐 수 있는지를 정합니다. 여기서만 할 수 있는 것이 하나 있습니다:
크롭을 다시 열어 상자가 정말 그 그림 안에 드는지 보는 일입니다.
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

import record_panels as R                                        # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-record-panels-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "crops"))
from PIL import Image                                            # noqa: E402
Image.new("RGB", (1000, 800), "white").save(os.path.join(RUN, "crops", "D1.png"))
with io.open(os.path.join(RUN, "figure_intake_draft.csv"), "w", encoding="utf-8") as fh:
    fh.write("Draft_ID,Figure_Crop\nD1,crops/D1.png\nD2,crops/gone.png\n")
QUEUE = [{"fig": "D1", "axes": "2"}, {"fig": "D2", "axes": "1"}]


def panel(i, **over):
    row = {"Draft_ID": "D1", "Panel_Index": str(i), "X0": "10", "Y0": "10",
           "X1": "400", "Y1": "300", "Mark_Type": "BOX", "Region_Source": "DRAWN",
           "Mark_Source": "TYPED",
           "Declared_Count": "2", "Drawn_Count": "2", "Verdict": "PANELS",
           "Seen_By_Person": "1", "Verified_By": "MC", "Note": ""}
    row.update(over)
    return row


def none_row(**over):
    base = dict(X0="", Y0="", X1="", Y1="", Mark_Type="", Region_Source="",
                Drawn_Count="0", Verdict="NO_PANELS")
    base.update(over)
    return panel(0, **base)


def run(answers, **kw):
    out = kw.pop("out_path", os.path.join(TMP, "out.csv"))
    if os.path.exists(out):
        os.remove(out)
    return R.record(RUN, QUEUE, answers, "2026-09-10", out, log=lambda *a: None, **kw)


def codes(refused):
    return [c for _n, problems in refused for c, _w in problems]


print("사람이 보고 이름을 댄 답은 적힌다")
_w, _r, _p = run([panel(1), panel(2, X0="500", X1="900", Mark_Type="bar")])
check("패널마다 한 줄이 적힌다", len(_w) == 2 and not _r, "%s %s" % (len(_w), codes(_r)))
check("본 날짜는 프로그램이 아니라 부른 쪽이 준다", _w[0]["Verified_At"] == "2026-09-10")
check("종류는 대문자로 적힌다", _w[1]["Mark_Type"] == "BAR")
check("자리와 출처가 그대로 들고 간다",
      _w[1]["X1"] == "900" and _w[1]["Region_Source"] == "DRAWN"
      and _w[1]["Mark_Source"] == "TYPED", _w[1])
_rows = list(csv.DictReader(io.open(_p, encoding="utf-8-sig")))
check("파일의 열은 정해진 순서다", list(_rows[0].keys()) == list(R.COLUMNS),
      list(_rows[0].keys()))

print()
print("이 관문이 지키는 것은 누가 보았는가다")
check("보았다는 표시가 없으면 거절한다",
      "NOT_SEEN_BY_PERSON" in codes(run([panel(1, Seen_By_Person="")])[1]))
check("한 줄만 표시가 없어도 그 그림을 거절한다",
      "NOT_SEEN_BY_PERSON" in codes(run([panel(1), panel(2, Seen_By_Person="")])[1]))
check("누가 보았는지 없으면 거절한다",
      "UNATTRIBUTED" in codes(run([panel(1, Verified_By=" ")])[1]))
# REVERT: 한 그림에 이름이 둘이어도 적는다. 어느 사람이 본 것인지 줄마다
# 다르면 그 그림을 본 사람이 누구인지 말할 수 없습니다.
check("한 그림에 이름이 둘이면 거절한다",
      "UNATTRIBUTED" in codes(run([panel(1), panel(2, Verified_By="XX")])[1]))

print()
print("상자는 실제 크롭 안에 들어야 한다")
# REVERT: 크롭을 열지 않고 좌표를 받는다. 브라우저에 남아 있던 다른 묶음의
# 상자가 이 그림의 것으로 적히고, 600 DPI로 옮길 때 흰 종이를 읽습니다.
check("크롭 밖의 상자는 거절한다",
      "BOX_OUTSIDE_CROP" in codes(run([panel(1, X1="1200")])[1]))
check("넓이 없는 상자는 거절한다",
      "BOX_EMPTY" in codes(run([panel(1, X1="12")])[1]))
check("수가 아닌 좌표는 거절한다",
      "BOX_NOT_NUMERIC" in codes(run([panel(1, X0="a")])[1]))
check("크롭을 열 수 없으면 거절한다",
      "CROP_UNREADABLE" in codes(run([panel(1, Draft_ID="D2")])[1]))
check("받을 수 없는 종류는 거절한다",
      "BAD_MARK" in codes(run([panel(1, Mark_Type="PIE")])[1]))
check("종류가 비어도 거절한다",
      "BAD_MARK" in codes(run([panel(1, Mark_Type="")])[1]))

print()
print("한 그림의 답은 한 덩어리다")
# REVERT: 번호가 이어지지 않아도 적는다. 2번만 온 그림이 패널 하나짜리로 적힙니다.
check("번호가 1부터 이어지지 않으면 거절한다",
      "PANEL_INDEX_BROKEN" in codes(run([panel(2)])[1]))
check("번호가 겹쳐도 거절한다",
      "PANEL_INDEX_BROKEN" in codes(run([panel(1), panel(1)])[1]))
check("패널이 없다는 답은 0번 한 줄로 적힌다",
      len(run([none_row()])[0]) == 1 and not run([none_row()])[1])
# REVERT: 패널이 없다는 답에 상자 줄이 붙어도 적는다. 그 상자가 무엇을
# 뜻하는지 이 관문은 모릅니다.
check("패널이 없다면서 상자가 붙어 오면 거절한다",
      "ROWS_WITHOUT_PANELS" in codes(run([panel(1, Verdict="NO_PANELS")])[1]))
check("한 그림에 판정이 둘이면 거절한다",
      "BAD_VERDICT" in codes(run([panel(1), panel(2, Verdict="NO_PANELS")])[1]))
check("모르는 판정은 이름을 대고 거절한다",
      "BAD_VERDICT" in codes(run([panel(1, Verdict="MAYBE")])[1]))
check("보류는 적지 않고 이름을 대고 거절한다",
      codes(run([none_row(Verdict="HOLD")])[1]) == ["HELD"],
      codes(run([none_row(Verdict="HOLD")])[1]))
# REVERT: 대기열에 없는 그림의 답도 적는다. 어느 묶음의 답인지 이 관문이 알 수
# 없는 채로 파일에 들어갑니다.
check("대기열에 없는 그림의 답은 거절한다",
      "NOT_QUEUED" in codes(run([none_row(Draft_ID="D9")])[1]))

print()
print("두 번 적지 않는다")
_out = os.path.join(TMP, "twice.csv")
R.record(RUN, QUEUE, [panel(1), panel(2)], "2026-09-10", _out, log=lambda *a: None)
_w2, _r2, _ = R.record(RUN, QUEUE, [none_row()], "2026-09-11", _out, log=lambda *a: None)
check("이미 적힌 그림은 거절한다", not _w2 and "ALREADY_RECORDED" in codes(_r2), codes(_r2))
_w3, _r3, _ = R.record(RUN, QUEUE, [none_row()], "2026-09-11", _out, replace=True,
                       log=lambda *a: None)
_rows = list(csv.DictReader(io.open(_out, encoding="utf-8-sig")))
# REVERT: 바꿀 때 지난 줄을 남긴다. 패널 둘짜리 그림이 NO_PANELS 한 줄과
# 함께 셋 줄로 앉습니다.
check("--replace는 그 그림의 지난 줄을 전부 걷어낸다",
      len(_w3) == 1 and len(_rows) == 1 and _rows[0]["Verdict"] == "NO_PANELS",
      (len(_w3), len(_rows)))

print()
print("답 파일과 적는 파일이 같으면 멈춘다")
_same = os.path.join(TMP, "same.csv")
with io.open(_same, "w", encoding="utf-8") as fh:
    fh.write("x\n")
try:
    R.record(RUN, QUEUE, [panel(1)], "2026-09-10", _same, answers_path=_same,
             log=lambda *a: None)
    check("같은 파일이면 멈춘다", False, "멈추지 않았다")
except SystemExit as exc:
    check("같은 파일이면 멈춘다", "같습니다" in str(exc), str(exc))

print()
print("화면과 논리와 관문이 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "panel_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_v = set(re.findall(r"'([A-Z_]+)'", re.search(r"var VERDICTS = \[(.*?)\]", LOGIC, re.S).group(1)))
_k = set(re.findall(r"'([A-Z_]+)'", re.search(r"var MARKS = \[(.*?)\]", LOGIC, re.S).group(1)))
check("판정의 이름이 셋 다 같다", set(R.VERDICTS) == _v, "%s / %s" % (sorted(R.VERDICTS), sorted(_v)))
check("종류의 이름이 셋 다 같다", set(R.MARKS) == _k, "%s / %s" % (sorted(R.MARKS), sorted(_k)))

print()
print("답 CSV가 패널 페이지의 것이 아니면 멈춘다")
try:
    R.record(RUN, QUEUE, [{"Draft_ID": "D1"}], "2026-09-10", os.path.join(TMP, "x.csv"),
             log=lambda *a: None)
    check("빠진 열을 이름 대고 말한다", False, "멈추지 않았다")
except SystemExit as exc:
    check("빠진 열을 이름 대고 말한다", "Seen_By_Person" in str(exc), str(exc))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
