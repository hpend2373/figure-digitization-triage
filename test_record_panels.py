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
SHA = R.crop_facts(RUN, {"D1": {"Figure_Crop": "crops/D1.png"}}, "D1")[1]


def panel(i, **over):
    row = {"Draft_ID": "D1", "Panel_Index": str(i), "X0": "10", "Y0": "10",
           "X1": "400", "Y1": "300", "Mark_Type": "BOX", "Region_Source": "DRAWN",
           "Mark_Source": "TYPED", "Crop_SHA256": SHA, "Proposal_Version": "v2",
           "Mark_Count": "3", "Count_Source": "TYPED",
           "Mark_Type_2": "", "Mark_Count_2": "", "Mark2_Source": "",
           "Overlay": "", "Overlay_Source": "",
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
      "NOT_SEEN_BY_PERSON" in codes(run([panel(1),
                                         panel(2, X0="500", X1="900",
                                               Seen_By_Person="")])[1]))
check("누가 보았는지 없으면 거절한다",
      "UNATTRIBUTED" in codes(run([panel(1, Verified_By=" ")])[1]))
# REVERT: 한 그림에 이름이 둘이어도 적는다. 어느 사람이 본 것인지 줄마다
# 다르면 그 그림을 본 사람이 누구인지 말할 수 없습니다.
check("한 그림에 이름이 둘이면 거절한다",
      "UNATTRIBUTED" in codes(run([panel(1),
                                   panel(2, X0="500", X1="900",
                                         Verified_By="XX")])[1]))

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
print("좌표는 이 크롭 위의 좌표여야 한다")
# REVERT: 크기만 보고 지문은 보지 않는다. 같은 이름으로 다시 만들어진 크롭은
# 같은 크기의 다른 그림이고, 그때 상자는 아무 데도 아닌 자리를 가리킵니다.
check("다른 크롭에서 온 답은 거절한다",
      "CROP_CHANGED" in codes(run([panel(1, Crop_SHA256="0" * 64)])[1]))
check("지문이 없는 낡은 답도 거절한다",
      "CROP_CHANGED" in codes(run([panel(1, Crop_SHA256="")])[1]))
check("적힌 줄에는 지금 크롭의 지문이 들어간다",
      run([panel(1, Crop_SHA256=SHA.upper())])[0][0]["Crop_SHA256"] == SHA)
# REVERT: 실수 좌표를 그대로 적는다. 다음 단계는 이 값을 픽셀 자리로 쓰고,
# `10.4`는 픽셀이 아닙니다.
check("좌표는 정수로 적힌다", run([panel(1, X0="10.4")])[0][0]["X0"] == "10")
# REVERT: 전에 센 수를 답에서 받아 적는다. 그러면 그 수는 아무것과도 대조되지
# 않고, 화면이 들고 온 것이 그대로 증거가 됩니다.
check("전에 센 수는 답이 아니라 대기열에서 온다",
      run([panel(1, Declared_Count="99")])[0][0]["Declared_Count"] == "2")

print()
print("개수는 대조할 수여야 한다")
check("개수가 그대로 들고 간다", run([panel(1)])[0][0]["Mark_Count"] == "3")
# REVERT: 아무 글자나 개수로 받는다. 리더가 찾아낸 수와 대조할 수가 아니고,
# 격자 관문은 그 패널의 구멍을 영영 못 잡습니다.
check("셀 수 없는 개수는 거절한다",
      "BAD_COUNT" in codes(run([panel(1, Mark_Count="세 개")])[1]))
check("0은 개수가 아니다", "BAD_COUNT" in codes(run([panel(1, Mark_Count="0")])[1]))
# REVERT: 빈 개수를 막는다. 이 관문이 묻는 것은 자리와 종류이고, 개수를
# 1019칸 채우게 붙잡아 두면 아무도 끝내지 못합니다.
check("아직 말하지 않은 개수는 막지 않는다",
      not run([panel(1, Mark_Count="", Count_Source="")])[1])

print()
print("한 자리에 종류가 둘일 수 있다")
_two = run([panel(1, Mark_Type_2="LINE", Mark_Count_2="2", Mark2_Source="PROPOSED")])
check("두 번째 종류가 그대로 적힌다",
      not _two[1] and _two[0][0]["Mark_Type_2"] == "LINE" and _two[0][0]["Mark_Count_2"] == "2")
# REVERT: 두 번째 종류를 첫 번째와 같게, 또는 읽을 값 없음으로 받는다.
check("첫 번째와 같은 둘째 종류는 거절한다",
      "BAD_MARK_2" in codes(run([panel(1, Mark_Type_2="BOX")])[1]))
check("읽을 값 없음은 둘째 종류가 아니다",
      "BAD_MARK_2" in codes(run([panel(1, Mark_Type_2="NOT_DATA")])[1]))
check("둘째 종류 없이 온 개수는 거절한다",
      "BAD_MARK_2" in codes(run([panel(1, Mark_Count_2="2")])[1]))
check("둘째 종류의 개수도 셀 수여야 한다",
      "BAD_COUNT" in codes(run([panel(1, Mark_Type_2="LINE", Mark_Count_2="x")])[1]))
check("개별 점·선 겹침은 그대로 적힌다",
      run([panel(1, Overlay="INDIVIDUAL", Overlay_Source="TYPED")])[0][0]["Overlay"] == "INDIVIDUAL")
# REVERT: 겹침 칸에 아무 말이나 받는다. 리더는 정해진 말만 알아듣습니다.
check("모르는 겹침 말은 거절한다",
      "BAD_OVERLAY" in codes(run([panel(1, Overlay="DOTS")])[1]))

print()
print("같은 패널을 두 번 적지 않는다")
# REVERT: 거의 같은 상자 둘을 그대로 적는다. 한 패널을 두 번 읽어 같은 값이
# 두 번 풀에 들어갑니다 - 자동 분할이 실제로 그런 상자를 냈습니다.
check("거의 같은 상자 둘은 거절한다",
      "PANEL_DUPLICATE" in codes(run([panel(1), panel(2, X0="12", Y0="12")])[1]))
check("포개지지만 다른 상자는 적는다",
      not run([panel(1), panel(2, X0="100", X1="900", Y1="700")])[1])

print()
print("한 그림의 답은 한 덩어리다")
# REVERT: 번호가 이어지지 않아도 적는다. 2번만 온 그림이 패널 하나짜리로 적힙니다.
check("번호가 1부터 이어지지 않으면 거절한다",
      "PANEL_INDEX_BROKEN" in codes(run([panel(2)])[1]))
check("번호가 겹쳐도 거절한다",
      "PANEL_INDEX_BROKEN" in codes(run([panel(1), panel(1, X0="500", X1="900")])[1]))
check("패널이 없다는 답은 0번 한 줄로 적힌다",
      len(run([none_row()])[0]) == 1 and not run([none_row()])[1])
# REVERT: 패널이 없다는 답에 상자 줄이 붙어도 적는다. 그 상자가 무엇을
# 뜻하는지 이 관문은 모릅니다.
check("패널이 없다면서 상자가 붙어 오면 거절한다",
      "ROWS_WITHOUT_PANELS" in codes(run([panel(1, Verdict="NO_PANELS")])[1]))
check("한 그림에 판정이 둘이면 거절한다",
      "BAD_VERDICT" in codes(run([panel(1),
                                  panel(2, X0="500", X1="900", Verdict="NO_PANELS")])[1]))
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
R.record(RUN, QUEUE, [panel(1), panel(2, X0="500", X1="900")], "2026-09-10", _out,
         log=lambda *a: None)
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
print("대기열은 페이지가 실은 그 묶음이다")
# REVERT: 묶음이 아니라 대기열 전체를 본다. 그러면 "이 대기열의 그림이 아니다"가
# 아무것도 막지 못하고, 다른 묶음에서 브라우저에 남아 있던 답이 그대로 적힙니다.
_q = os.path.join(TMP, "queue.csv")
with io.open(_q, "w", encoding="utf-8") as fh:
    fh.write("pid,fig,axes\nP,D1,2\nP,D2,1\n")
_a = os.path.join(TMP, "answers.csv")
with io.open(_a, "w", encoding="utf-8", newline="") as fh:
    _wr = csv.DictWriter(fh, fieldnames=list(panel(1).keys()))
    _wr.writeheader()
    _wr.writerow(panel(1))
_o = os.path.join(TMP, "chunked.csv")
check("다른 묶음의 답은 CLI에서도 거절된다",
      R.main(["--run", RUN, "--queue", _q, "--answers", _a, "--when", "2026-09-10",
              "--out", _o, "--chunk", "2", "--of", "2"]) == 1)
check("제 묶음의 답은 CLI에서 적힌다",
      R.main(["--run", RUN, "--queue", _q, "--answers", _a, "--when", "2026-09-10",
              "--out", _o, "--chunk", "1", "--of", "2"]) == 0)

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
