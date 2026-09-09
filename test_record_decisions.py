# -*- coding: utf-8 -*-
"""처분을 적는 관문.

    python3 test_record_decisions.py     # exit 0 = all scenarios pass

`record_errorbar`와 같은 자리에 있고 같은 것을 지킵니다: 사람이 보았다고 말한
답만 적힙니다. 여기서 하나 더 있는 것은 **짝 맞추기**입니다 - 계획서가 그
그림에 대해 그 물음을 물었는지. 묻지 않은 물음에 온 답은 어디서 왔든 적히지
않습니다.
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

import decision_page as DP                                       # noqa: E402
import record_decisions as RD                                    # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def write(path, columns, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(dict((c, r.get(c, "")) for c in columns))


TMP = tempfile.mkdtemp(prefix="fdt-recdec-")
RUN = os.path.join(TMP, "run")
PLANS = os.path.join(RUN, "plans")
os.makedirs(PLANS)

UNC = "셀 수 없다고 하신 그림 — 처분 결정"
MIX = "캡션이 스스로 어긋난 그림 — 어느 패널이 데이터인지 확인"

write(os.path.join(PLANS, DP.FIGURES),
      ["Publication_ID", "Draft_ID", "Figure_Number", "Page", "Needs"],
      [{"Publication_ID": "A", "Draft_ID": "d1", "Figure_Number": "FIG1",
        "Page": "3", "Needs": UNC},
       {"Publication_ID": "A", "Draft_ID": "d2", "Figure_Number": "FIG2",
        "Page": "4", "Needs": MIX}])
write(os.path.join(RUN, RD.DRAFT),
      ["Draft_ID", "Source_Document_ID"],
      [{"Draft_ID": "d1", "Source_Document_ID": "A"},
       {"Draft_ID": "d2", "Source_Document_ID": "A"}])

ASKED = RD.load_asked(RUN, PLANS)


def codes(answer):
    return [c for c, _w in RD.check_answer(answer, ASKED)]


def ans(**over):
    a = {"Draft_ID": "d1", "Question": "UNCOUNTABLE", "Decision": "NOT_DATA",
         "Which_Panels": "", "Seen_By_Person": "1", "Note": ""}
    a.update(over)
    return a


check("다 갖춘 답은 문제가 없다", codes(ans()) == [], codes(ans()))

# REVERT: 사람이 보았다는 표시를 보지 않는다. 화면이 그 칸을 채워 보낼 수는
# 있지만, 채운 것이 사람인지 프로그램인지는 화면 밖에서 알 수 없습니다.
check("그림을 봤다고 하지 않은 답은 적지 않는다",
      codes(ans(Seen_By_Person="")) == ["NOT_SEEN_BY_PERSON"],
      codes(ans(Seen_By_Person="")))

# REVERT: 계획서가 물었는지 보지 않는다. 그러면 계획서를 다시 낸 뒤의 답이나
# 다른 run의 답이 이 run에 적힙니다 - 어느 물음에 대한 답인지 모르는 채로.
check("계획서가 묻지 않은 것에 온 답은 적지 않는다",
      "NOT_ASKED" in codes(ans(Draft_ID="d9")),
      codes(ans(Draft_ID="d9")))
check("같은 그림이라도 묻지 않은 물음이면 적지 않는다",
      "NOT_ASKED" in codes(ans(Draft_ID="d1", Question="MIXED",
                               Decision="DATA")))

check("모르는 물음은 이름을 대며 거절한다",
      codes(ans(Question="WHATEVER")) == ["BAD_QUESTION"])
check("물음에 없는 답은 이름을 대며 거절한다",
      codes(ans(Decision="DATA")) == ["BAD_DECISION"])

# REVERT: 어느 패널인지 묻지 않는다. 어느 패널인지 모르는 "일부"는 다음
# 사람에게 아무 말도 하지 않습니다.
check("일부 패널만이라면서 패널을 안 적으면 거절한다",
      codes(ans(Draft_ID="d2", Question="MIXED", Decision="PARTIAL"))
      == ["PARTIAL_WITHOUT_PANELS"])
# REVERT: 패널을 받지 않는 답에 붙은 이름을 그냥 적는다. 그 이름이 무엇을
# 뜻하는지 아무도 모르는 채 기록에 남습니다.
check("패널을 받지 않는 답에 패널이 붙으면 거절한다",
      codes(ans(Draft_ID="d2", Question="MIXED", Decision="DATA",
                Which_Panels="a")) == ["PANELS_WITHOUT_PARTIAL"])
check("패널을 적은 PARTIAL은 통과한다",
      codes(ans(Draft_ID="d2", Question="MIXED", Decision="PARTIAL",
                Which_Panels="a")) == [])

# REVERT: HOLD를 처분으로 적는다. "아직 못 정하겠다"가 정해진 것이 됩니다.
check("아직 못 정하겠다는 적지 않고 이름을 댄다",
      codes(ans(Decision="HOLD")) == ["HELD"])

# 세 곳의 어휘가 같아야 합니다. 한 곳에만 있는 답은 고를 수는 있지만 적히지
# 않거나, 적힐 수는 있지만 아무도 고를 수 없습니다.
_js = io.open(os.path.join(HERE, DP.LOGIC), encoding="utf-8").read()
_same = True
for kind, allowed in RD.CHOICES.items():
    m = re.search(r"%s:\s*\[([^\]]*)\]" % kind, _js)
    js = tuple(v.strip().strip("'") for v in m.group(1).split(",")) if m else ()
    screen = tuple(v for v, _l in DP.LABELS.get(kind, []))
    if js != allowed or screen != allowed:
        _same = False
check("관문·화면·논리의 어휘가 셋 다 같다", _same,
      dict((k, (v, tuple(x for x, _l in DP.LABELS.get(k, []))))
           for k, v in RD.CHOICES.items()))

# ------------------------------------------------------------- 적는 일

OUT = os.path.join(RUN, RD.DECISIONS)
_w, _r, _p = RD.record(RUN, PLANS, [ans(), ans(Draft_ID="d2", Question="MIXED",
                                          Decision="PARTIAL", Which_Panels="a")],
                       "2026-09-09", log=lambda *_a: None)
_rows = {r["Draft_ID"]: r for r in
         csv.DictReader(io.open(OUT, encoding="utf-8-sig"))}
check("적힌 행은 두 줄", len(_rows) == 2 and not _r, (len(_rows), _r))

# REVERT: 사람이 본 날을 오늘로 채운다. 언제 보았는지는 이 프로그램이 아는
# 것이 아닙니다.
check("사람이 본 날이 그대로 적힌다",
      _rows["d1"]["Recorded_At"] == "2026-09-09")
check("초안과 계획서에서 이름을 채워 적는다",
      _rows["d1"]["Source_Document_ID"] == "A"
      and _rows["d1"]["Figure_Number"] == "FIG1"
      and _rows["d1"]["Page"] == "3", _rows["d1"])

# REVERT: 이미 적힌 것을 말없이 덮어쓴다. 판정이 언제 어떻게 바뀌었는지가
# 사라집니다.
_w2, _r2, _ = RD.record(RUN, PLANS, [ans(Decision="RECROP")], "2026-09-10",
                        log=lambda *_a: None)
check("이미 적힌 물음은 --replace 없이 다시 적히지 않는다",
      not _w2 and [c for c, _x in _r2[0][1]] == ["ALREADY_DECIDED"], _r2)
_w3, _r3, _ = RD.record(RUN, PLANS, [ans(Decision="RECROP")], "2026-09-10",
                        replace=True, log=lambda *_a: None)
_rows = {r["Draft_ID"]: r for r in
         csv.DictReader(io.open(OUT, encoding="utf-8-sig"))}
check("--replace면 덮어쓰고 다른 줄은 그대로 둔다",
      len(_rows) == 2 and _rows["d1"]["Decision"] == "RECROP"
      and _rows["d2"]["Decision"] == "PARTIAL", _rows)

# REVERT: 답 파일이 곧 적는 파일이어도 그냥 돌린다. 관문이 자기가 적어 둔
# 것을 답으로 읽고, 전부 ALREADY_DECIDED로 거절한 뒤 원본을 덮어씁니다.
# 실제로 한 번 덮어썼습니다.
try:
    RD.record(RUN, PLANS, [ans()], "2026-09-09", answers_path=OUT,
              log=lambda *_a: None)
    _stopped = False
except SystemExit:
    _stopped = True
check("답 파일과 적는 파일이 같으면 멈춘다", _stopped)

# REVERT: 판정 페이지가 관문의 출력과 같은 이름으로 내려받는다.
_page = io.open(os.path.join(HERE, "decision_page.py"), encoding="utf-8").read()
check("판정 페이지는 관문의 출력과 다른 이름으로 내려받는다",
      "'figure_decision_answers.csv'" in _page
      and "a.download = 'figure_decisions.csv'" not in _page)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
