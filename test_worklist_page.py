# -*- coding: utf-8 -*-
"""남은 일 목록이 무엇을 보여 주는가.

    python3 test_worklist_page.py     # exit 0 = all scenarios pass

이 페이지는 답을 받지 않으므로 지킬 것이 하나뿐입니다: **계획서가 적어 둔 일과
화면에 보이는 일이 같아야 한다.** 하나라도 빠지면 그 일은 아무도 모르게 남고,
없는 일이 늘면 사람이 없는 일을 합니다.
"""
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import worklist_page as W                                        # noqa: E402

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


TMP = tempfile.mkdtemp(prefix="fdt-worklist-")
RUN = os.path.join(TMP, "run")
PLANS = os.path.join(RUN, "plans")
os.makedirs(os.path.join(RUN, "crops"))
os.makedirs(PLANS)

GEOM = "패널 기하 (읽을 자리·눈금·표 종류)"
DISP = "셀 수 없다고 하신 그림 — 처분 결정"

write(os.path.join(PLANS, W.FIGURES),
      ["Publication_ID", "Draft_ID", "Figure_Number", "Page", "Image", "Route",
       "Disposition", "Observed_Panel_Count", "Statistic_Type",
       "Dispersion_Type", "Errorbar_Definition_Source", "Errorbar_Source_Kind",
       "Needs"],
      [{"Publication_ID": "A", "Draft_ID": "d1", "Figure_Number": "FIG1",
        "Page": "3", "Image": os.path.join("crops", "a1.png"),
        "Disposition": "GEOMETRY_NOT_AUTHORED", "Observed_Panel_Count": "6",
        "Statistic_Type": "CONTINUOUS", "Dispersion_Type": "SD",
        "Errorbar_Source_Kind": "CAPTION", "Needs": GEOM},
       # 한 그림에 일이 둘. 두 묶음 모두에 나와야 합니다.
       {"Publication_ID": "A", "Draft_ID": "d2", "Figure_Number": "FIG2",
        "Page": "4", "Image": os.path.join("crops", "gone.png"),
        "Disposition": "GEOMETRY_NOT_AUTHORED", "Observed_Panel_Count": "2",
        "Needs": "%s · 오차 정의" % GEOM},
       {"Publication_ID": "B", "Draft_ID": "d3", "Figure_Number": "FIG1",
        "Page": "2", "Image": os.path.join("crops", "b1.png"),
        "Disposition": "UNRESOLVED", "Observed_Panel_Count": "",
        "Needs": DISP},
       # 할 일이 없는 그림. 목록에 없어야 합니다.
       {"Publication_ID": "C", "Draft_ID": "d4", "Figure_Number": "FIG1",
        "Page": "9", "Image": os.path.join("crops", "b1.png"),
        "Disposition": "NOT_DATA", "Needs": ""}])

write(os.path.join(RUN, W.COUNTS),
      ["Draft_ID", "Observed_Panel_Count", "Entry_Status",
       "Uncountable_Reason", "Objection_Reason"],
      [{"Draft_ID": "d3", "Entry_Status": "SEEN_UNCOUNTABLE",
        "Uncountable_Reason": "축이 겹쳐 어디까지가 한 패널인지 모르겠습니다"}])

from PIL import Image                                            # noqa: E402
Image.new("RGB", (40, 30), (200, 40, 40)).save(
    os.path.join(RUN, "crops", "a1.png"))
Image.new("RGB", (40, 30), (40, 40, 200)).save(
    os.path.join(RUN, "crops", "b1.png"))

HTML, FIGS, WORK = W.build(RUN, PLANS, log=lambda *_a: None)

check("일이 있는 그림만 실린다", (FIGS, WORK) == (3, 4), (FIGS, WORK))
check("일이 없는 그림은 실리지 않는다", "data-doc='C'" not in HTML and "C</div>" not in HTML)

# REVERT: 일이 여럿인 그림을 한 번만 싣는다. 그러면 그 그림의 나머지 일은
# 어느 묶음에도 없고, 계획서에는 있는 일이 화면에서 사라집니다.
check("일이 둘인 그림은 두 묶음에 다 나온다",
      HTML.count("FIG2 · p.4") == 2, HTML.count("FIG2 · p.4"))

check("탭은 일마다 하나씩, 개수와 함께",
      "data-need=''>전체 4<" in HTML
      and HTML.count("class='tab'") == 3,
      HTML.count("class='tab'"))

# REVERT: 계수 시트에 적어 두신 말을 싣지 않는다. 왜 이 그림이 여기 있는지를
# 알려면 시트를 다시 열어야 합니다.
check("사람이 적어 둔 말이 카드에 실린다",
      "축이 겹쳐 어디까지가 한 패널인지" in HTML)

check("크롭이 없으면 없다고 적는다",
      "크롭 없음" in HTML and HTML.count("data:image/jpeg;base64,") == 2,
      HTML.count("data:image/jpeg;base64,"))

# REVERT: `[hidden]`을 !important 없이 둔다. `.grid{display:grid}`와 명시도가
# 같아서 뒤에 오는 쪽이 이기고, 탭을 눌러도 아무것도 숨겨지지 않습니다.
# 브라우저로 돌려 보고서야 알았습니다.
check("숨김 규칙이 격자 규칙을 이긴다",
      "[hidden]{display:none!important}" in HTML)

_empty = os.path.join(TMP, "empty")
os.makedirs(_empty)
write(os.path.join(_empty, W.FIGURES), ["Draft_ID", "Needs"],
      [{"Draft_ID": "d1", "Needs": ""}])
try:
    W.build(RUN, _empty, log=lambda *_a: None)
    _stopped = False
except SystemExit:
    _stopped = True
check("남은 일이 없으면 빈 페이지를 내지 않고 멈춘다", _stopped)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
