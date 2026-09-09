# -*- coding: utf-8 -*-
"""처분 판정 페이지가 사람에게 무엇을 내미는가.

    python3 test_decision_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `decision_page.js`가 정하고 `test_decision_page.mjs`가
봅니다. 여기서 붙잡는 것은 화면의 성질입니다: 이 페이지가 묻는 일만 카드가
되는가, 고르는 칸이 비어서 나가는가, 화면의 선택지와 논리의 어휘가 같은가.
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

import decision_page as D                                        # noqa: E402

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


TMP = tempfile.mkdtemp(prefix="fdt-decision-")
RUN = os.path.join(TMP, "run")
PLANS = os.path.join(RUN, "plans")
os.makedirs(os.path.join(RUN, "crops"))
os.makedirs(PLANS)

UNC = "셀 수 없다고 하신 그림 — 처분 결정"
MIX = "캡션이 스스로 어긋난 그림 — 어느 패널이 데이터인지 확인"
GEOM = "패널 기하 (읽을 자리·눈금·표 종류)"

write(os.path.join(PLANS, D.FIGURES),
      ["Publication_ID", "Draft_ID", "Figure_Number", "Page", "Image",
       "Disposition", "Observed_Panel_Count", "Dispersion_Type",
       "Errorbar_Definition_Source", "Needs"],
      [{"Publication_ID": "A", "Draft_ID": "d1", "Figure_Number": "FIG1",
        "Page": "3", "Image": os.path.join("crops", "a1.png"),
        "Observed_Panel_Count": "", "Needs": UNC},
       {"Publication_ID": "A", "Draft_ID": "d2", "Figure_Number": "FIG2",
        "Page": "4", "Image": os.path.join("crops", "a1.png"),
        "Observed_Panel_Count": "4", "Dispersion_Type": "IQR",
        "Errorbar_Definition_Source": "Box plots indicate minimum,",
        "Needs": MIX},
       # 이 페이지가 묻지 않는 일. 단추로 답할 수 없습니다.
       {"Publication_ID": "B", "Draft_ID": "d3", "Figure_Number": "FIG1",
        "Page": "2", "Image": os.path.join("crops", "a1.png"),
        "Observed_Panel_Count": "6", "Needs": "%s · 오차 정의" % GEOM}])

write(os.path.join(RUN, D.COUNTS),
      ["Draft_ID", "Entry_Status", "Uncountable_Reason", "Objection_Reason"],
      [{"Draft_ID": "d1", "Entry_Status": "SEEN_UNCOUNTABLE",
        "Uncountable_Reason": "축이 겹쳐 어디까지가 한 패널인지 모르겠습니다"}])

write(os.path.join(RUN, D.CAPTIONS),
      ["Draft_ID", "Caption_Full"],
      [{"Draft_ID": "d2",
        "Caption_Full": "Fig. 2 | b Example of capillaroscopy. Box plots "
                        "indicate minimum, 25th percentile, median."}])

from PIL import Image                                            # noqa: E402
Image.new("RGB", (40, 30), (200, 40, 40)).save(
    os.path.join(RUN, "crops", "a1.png"))

HTML, ITEMS = D.build(RUN, PLANS, log=lambda *_a: None)

# REVERT: 계획서의 할 일을 전부 카드로 만든다. 패널 기하는 읽을 자리와 눈금을
# 쓰는 일이라 단추로 답할 수 없고, 오차 정의는 다른 페이지가 이미 묻습니다.
# 답할 수 없는 칸 앞에 사람을 앉히는 것은 묻지 않는 것보다 나쁩니다.
check("이 페이지가 묻는 일만 카드가 된다",
      ITEMS == 2 and "data-id='UNCOUNTABLE::d1'" in HTML
      and "data-id='MIXED::d2'" in HTML
      # base64 안에 아무 글자나 들어 있으므로 카드의 열쇠로만 봅니다.
      and "::d3'" not in HTML,
      ITEMS)

# REVERT: 화면의 선택지를 논리와 따로 적는다. 화면에만 있는 답은 고를 수는
# 있지만 답이 되지 않고, 논리에만 있는 답은 아무도 고를 수 없습니다.
_js = io.open(os.path.join(HERE, D.LOGIC), encoding="utf-8").read()
_ok = True
for kind, pairs in D.LABELS.items():
    m = re.search(r"%s:\s*\[([^\]]*)\]" % kind, _js)
    want = [v.strip().strip("'") for v in m.group(1).split(",")] if m else []
    if [v for v, _l in pairs] != want:
        _ok = False
check("화면의 선택지와 논리의 어휘가 같다", _ok,
      dict((k, [v for v, _l in p]) for k, p in D.LABELS.items()))

check("물음마다 받는 답이 다르다",
      "value='COUNTABLE'" in HTML and "value='PARTIAL'" in HTML
      and HTML.count("value='COUNTABLE'") == 1)

# REVERT: 고른 채로 낸다. 사람이 하는 일이 판정이 아니라 동의가 됩니다.
_inputs = [l for l in HTML.splitlines() if "<input type=" in l]
check("아무 선택지도 골라 둔 채로 나가지 않는다",
      bool(_inputs) and all("checked" not in l for l in _inputs),
      [l for l in _inputs if "checked" in l][:1])

# REVERT: 계수 시트에 적어 두신 말을 싣지 않는다.
check("사람이 적어 둔 말이 카드에 실린다",
      "축이 겹쳐 어디까지가 한 패널인지" in HTML)

# REVERT: 어긋난 캡션에 캡션을 싣지 않는다. 무엇이 어긋났는지 보지 못한 채
# 어느 패널이 데이터인지 정하게 됩니다.
check("어긋난 캡션 카드에는 캡션 전문이 실린다",
      "Example of capillaroscopy" in HTML and "Box plots indicate" in HTML)

check("META가 물음과 나갈 이름을 들고 있다",
      '"MIXED::d2": {"kind": "MIXED", "draft": "d2"}' in HTML,
      [l for l in HTML.splitlines() if l.startswith("var META")][:1])

check("결정은 페이지 안에 실려 있다",
      "function decisionOf" in HTML and "function buildCsv" in HTML)

_empty = os.path.join(TMP, "empty")
os.makedirs(_empty)
write(os.path.join(_empty, D.FIGURES), ["Draft_ID", "Needs"],
      [{"Draft_ID": "d1", "Needs": GEOM}])
try:
    D.build(RUN, _empty, log=lambda *_a: None)
    _stopped = False
except SystemExit:
    _stopped = True
check("물을 것이 없으면 빈 페이지를 내지 않고 멈춘다", _stopped)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
