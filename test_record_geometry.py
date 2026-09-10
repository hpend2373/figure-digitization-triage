# -*- coding: utf-8 -*-
"""기하 판정 관문이 무엇을 적고 무엇을 거절하는가.

    python3 test_record_geometry.py     # exit 0 = all scenarios pass

`geometry_page.js`는 브라우저 안에서 무엇이 답이 되는지를 정하고, 이 관문은
그 답이 파일에 적힐 수 있는지를 정합니다. 둘이 같은 말을 하는지도 여기서
봅니다 - 화면이 통과시킨 답을 관문이 이름 없이 거절하면, 사람은 다 해 놓고
나서 아무 설명 없이 되돌아옵니다.
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

import geometry_proposer as GP                                   # noqa: E402
import record_geometry as R                                      # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-record-geom-")
PROP = os.path.join(TMP, "gp")
os.makedirs(PROP)

PROPOSED = {
    "Proposal_ID": "GP001", "Raster": "fig.png",
    "Panel_X0": "10", "Panel_X1": "200", "Panel_Y0": "5", "Panel_Y1": "150",
    "Y_Tick_Pixels": "10;50;90", "Y_Tick_Count": "3",
    "Y_Tick_Read_Status": GP.READ_OK, "Y_Tick_Read_Values": "30@10;20@50;10@90",
    "Y_Tick_Read_First": "30", "Y_Tick_Read_Last": "10",
    "Human_Verification_Status": GP.PROPOSAL_PENDING,
}
GP.write_proposals(os.path.join(PROP, R.PROPOSALS),
                   [PROPOSED, dict(PROPOSED, Proposal_ID="GP002")])


def answer(**over):
    row = {"Proposal_ID": "GP001", "Human_Verification_Status": "CONFIRMED",
           "Y_Tick_First_Value": "30", "Y_Tick_Last_Value": "10",
           "Verified_By": "MC", "Seen_By_Person": "1",
           "Value_Source": "READ", "Note": ""}
    row.update(over)
    return row


def run(answers, **kw):
    out = kw.pop("out_path", os.path.join(TMP, "out.csv"))
    if os.path.exists(out):
        os.remove(out)
    return R.record(PROP, answers, "2026-09-10", out_path=out,
                    log=lambda *a: None, **kw)


def codes(refused):
    return [c for _n, problems in refused for c, _w in problems]


print("사람이 보고 이름을 댄 답은 적힌다")
_w, _r, _p = run([answer()])
check("한 줄이 적힌다", len(_w) == 1 and not _r, "%s %s" % (len(_w), codes(_r)))
check("확인은 확인으로 적힌다",
      _w[0]["Human_Verification_Status"] == "CONFIRMED")
check("본 날짜는 프로그램이 아니라 부른 쪽이 준다",
      _w[0]["Verified_At"] == "2026-09-10")
# REVERT: 제안의 행을 버리고 답만 새로 적는다. 눈금 픽셀이 사라지고,
# `calibration_from`이 확인된 기하에서 아무것도 만들지 못합니다.
check("제안이 잰 것을 그대로 들고 간다", _w[0]["Y_Tick_Pixels"] == "10;50;90",
      _w[0].get("Y_Tick_Pixels"))
check("그래서 그 행에서 바로 계산이 나온다",
      GP.calibration_from(_w[0]) == [[30.0, 10.0], [10.0, 90.0]],
      GP.calibration_from(_w[0]))

print()
print("이 관문이 지키는 것은 값의 모양이 아니라 누가 보았는가다")
# REVERT: 본 표시를 보지 않는다. 화면이 채워 보낼 수는 있지만 채운 것이
# 사람인지는 화면 밖에서 알 수 없고, 이 문이 그 마지막 확인입니다.
check("보았다는 표시가 없으면 거절한다",
      codes(run([answer(Seen_By_Person="")])[1]) == ["NOT_SEEN_BY_PERSON"],
      codes(run([answer(Seen_By_Person="")])[1]))
# REVERT: 이름 없이도 적는다. 되돌아볼 곳이 없는 확인이고,
# `proposal_problems`가 그 파일을 통째로 되돌려 보냅니다.
check("누가 보았는지 없으면 거절한다",
      "UNATTRIBUTED" in codes(run([answer(Verified_By="  ")])[1]))

print()
print("확인은 값을 들고 와야 확인이다")
# REVERT: 값 없는 확인을 적는다. 계산이 되지 않는 기하가 확인된 채로 앉아
# 있고, 다음 사람은 그것이 쓸 수 있는 줄 압니다.
check("값 없는 확인은 거절한다",
      "TICK_VALUE_MISSING" in codes(run([answer(Y_Tick_First_Value="")])[1]))
check("숫자가 아닌 값도 거절한다",
      "TICK_VALUE_MISSING" in codes(run([answer(Y_Tick_First_Value="약 30")])[1]))
check("첫 눈금과 끝 눈금이 같으면 거절한다",
      "TICK_VALUES_EQUAL" in codes(
          run([answer(Y_Tick_First_Value="10", Y_Tick_Last_Value="10")])[1]))
# REVERT: 확인하지 않은 기하에 붙어 온 값을 그냥 적는다. 그 값이 틀린
# 프레임에서 읽은 것인지 고쳐 준 것인지 이 관문은 모릅니다.
check("거절·보류에 붙어 온 값은 거절한다",
      "VALUES_WITHOUT_CONFIRMATION" in codes(
          run([answer(Human_Verification_Status="REJECTED")])[1]))
check("값 없는 거절은 그대로 적힌다",
      len(run([answer(Human_Verification_Status="REJECTED",
                      Y_Tick_First_Value="", Y_Tick_Last_Value="")])[0]) == 1)

print()
print("적을 수 없는 답에는 이름을 붙여 돌려보낸다")
check("모르는 판정은 이름을 대고 거절한다",
      "BAD_VERDICT" in codes(run([answer(Human_Verification_Status="MAYBE")])[1]))
# REVERT: 낸 적 없는 제안의 답도 적는다. 어느 그림의 어느 자리에 대한
# 답인지 이 관문이 알 수 없는 채로 파일에 들어갑니다.
check("낸 적 없는 제안의 답은 거절한다",
      "NOT_PROPOSED" in codes(run([answer(Proposal_ID="GP999")])[1]))
# REVERT: 보류를 확인으로 적는다. "아직 못 정하겠다"가 정해진 것이 됩니다.
check("보류는 적지 않고 이름을 대고 거절한다",
      codes(run([answer(Human_Verification_Status="HOLD",
                        Y_Tick_First_Value="", Y_Tick_Last_Value="")])[1])
      == ["HELD"])

print()
print("두 번 적지 않는다")
_out = os.path.join(TMP, "twice.csv")
R.record(PROP, [answer()], "2026-09-10", out_path=_out, log=lambda *a: None)
_w2, _r2, _ = R.record(PROP, [answer(Y_Tick_First_Value="99")], "2026-09-11",
                       out_path=_out, log=lambda *a: None)
check("이미 적힌 제안은 거절한다",
      not _w2 and "ALREADY_RECORDED" in codes(_r2), codes(_r2))
_w3, _r3, _ = R.record(PROP, [answer(Y_Tick_First_Value="99")], "2026-09-11",
                       out_path=_out, replace=True, log=lambda *a: None)
check("--replace를 주면 바꾼다",
      len(_w3) == 1 and _w3[0]["Y_Tick_First_Value"] == "99")
_rows = list(csv.DictReader(io.open(_out, encoding="utf-8-sig")))
check("바꾼 뒤에도 줄은 하나다", len(_rows) == 1, len(_rows))

print()
print("답 파일과 적는 파일이 같으면 멈춘다")
# REVERT: 같은 파일이어도 그냥 읽고 쓴다. 관문이 자기 출력을 답으로 읽고,
# 전부 이미 적힌 것으로 거절한 뒤 원본을 덮습니다. 처분 관문에서 실제로 한 번
# 그렇게 덮어썼습니다.
_same = os.path.join(TMP, "same.csv")
GP.write_proposals(_same, [dict(PROPOSED)])
try:
    R.record(PROP, [answer()], "2026-09-10", out_path=_same,
             answers_path=_same, log=lambda *a: None)
    check("같은 파일이면 멈춘다", False, "멈추지 않았다")
except SystemExit as exc:
    check("같은 파일이면 멈춘다", "같습니다" in str(exc), str(exc))

print()
print("적으려는 파일 전체를 마지막으로 걸어 본다")
# REVERT: 적기 전에 파일을 걸어 보지 않는다. 이 관문이 적는 파일에는 이번에
# 적는 줄만 있는 것이 아니라 전에 적힌 줄도 그대로 실려 갑니다. 그 줄 하나를
# 누가 손으로 고쳐 두었으면 - 확인하지도 않은 제안에 눈금 값을 적어 넣는 것이
# 가장 쉬운 손질입니다 - 이 관문은 그것을 그대로 다시 적어 축복해 줍니다.
_dirty = os.path.join(TMP, "dirty.csv")
GP.write_proposals(_dirty, [dict(PROPOSED, Proposal_ID="GP002",
                                 Y_Tick_First_Value="30")])
try:
    R.record(PROP, [answer()], "2026-09-10", out_path=_dirty,
             log=lambda *a: None)
    check("실려 가는 줄이 규칙을 어기면 멈춘다", False, "멈추지 않았다")
except SystemExit as exc:
    check("실려 가는 줄이 규칙을 어기면 멈춘다",
          "PROPOSAL_PENDING_WITH_A_TICK_VALUE" in str(exc), str(exc))

print()
print("화면과 논리와 관문이 같은 어휘를 쓴다")
with io.open(os.path.join(HERE, "geometry_page.js"), encoding="utf-8") as fh:
    LOGIC = fh.read()
_js = set(re.findall(r"'([A-Z_]+)'",
                     re.search(r"var VERDICTS = \[(.*?)\]", LOGIC, re.S).group(1)))
# REVERT: 관문의 어휘를 논리와 따로 둔다. 화면이 통과시킨 답을 관문이
# 거절하면 사람은 다 해 놓고 나서 아무 설명 없이 되돌아옵니다.
check("판정의 이름이 셋 다 같다", set(R.VERDICTS) == _js,
      "관문 %s / 논리 %s" % (sorted(R.VERDICTS), sorted(_js)))
_js_needs = set(re.findall(r"'([A-Z_]+)'",
                           re.search(r"var NEEDS_VALUES = \[(.*?)\]",
                                     LOGIC, re.S).group(1)))
check("값을 묻는 판정도 셋 다 같다", set(R.NEEDS_VALUES) == _js_needs,
      "%s / %s" % (sorted(R.NEEDS_VALUES), sorted(_js_needs)))

print()
print("답 CSV가 판정 페이지의 것이 아니면 멈춘다")
try:
    R.record(PROP, [{"Proposal_ID": "GP001"}], "2026-09-10",
             out_path=os.path.join(TMP, "x.csv"), log=lambda *a: None)
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
