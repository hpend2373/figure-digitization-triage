# -*- coding: utf-8 -*-
"""축·계열 확인 페이지를 짓는 쪽의 결정들.

    python3 test_axis_series_page.py     # exit 0 = all scenarios pass

무엇이 답이 되는지는 `axis_series_page.js`(와 그 밑의 geometry_page.js·identity_page.js)가
정하고 `test_axis_series_page.mjs`가 봅니다. 여기서 보는 것은 제안 파일을 두 페이지의 상태
칸으로 옮기는 일, 짓기 전에 멈추는 자리, 그리고 페이지에 실리는 것입니다.
"""
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


def _blind_ocr():
    """tesseract가 있든 없든 같은 결과가 나오게: 아무 글자도 읽지 않는 pytesseract.

    이 실행기들이 볼 일은 제안을 어디에 어떻게 적는가이지 글자를 읽는가가 아닙니다. 진짜
    tesseract가 있는 작업과 없는 작업에서 시나리오가 갈리면, 같은 수가 두 뜻이 됩니다."""
    import types
    fake = types.ModuleType("pytesseract")

    class Output(object):
        DICT = "dict"
    fake.Output = Output
    fake.image_to_data = lambda *a, **k: {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
    sys.modules["pytesseract"] = fake


_blind_ocr()

from PIL import Image, ImageDraw                                 # noqa: E402

import axis_series_page as A                                     # noqa: E402
import propose_run as R                                          # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def chart():
    im = Image.new("RGB", (800, 320), "white")
    d = ImageDraw.Draw(im)
    for left in (0, 400):
        x0, x1, y0, y1 = left + 60, left + 360, 30, 270
        d.rectangle((x0, y0, x1, y1), outline="black")
        for k in range(11):
            y = y0 + k * (y1 - y0) / 10.0
            d.line((x0 - 5, y, x0 - 1, y), fill="black")
        for g in range(5):
            cx = x0 + 50 * (g + 1)
            d.rectangle((cx - 9, y1 - 60 - 20 * g, cx + 9, y1 - 1), outline="black")
    return im


TMP = tempfile.mkdtemp(prefix="fdt-axpage-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "seg", "r600"))
chart().save(os.path.join(RUN, "seg", "r600", "D1_600.png"))
REG = os.path.join(RUN, "seg", "r600", "panel_regions_600.csv")
write_csv(REG, [{"Draft_ID": "D1", "Panel_Index": str(k), "Mark_Type": "BAR", "Mark_Count": "5",
                 "Raster_600": "seg/r600/D1_600.png", "Raster_600_SHA256": "x", "Region_600": reg}
                for k, reg in ((1, "0,0,400,320"), (2, "400,0,800,320"))])
write_csv(os.path.join(RUN, "figure_intake_draft.csv"),
          [{"Draft_ID": "D1", "Caption_Text": "Fig. 1 Bars.", "Source_File": "doc.pdf", "Figure_Crop": ""}])
GDIR, IDIR = os.path.join(RUN, "seg", "g"), os.path.join(RUN, "seg", "i")
R.geometry_batch(RUN, REG, GDIR)
R.identity_batch(RUN, REG, os.path.join(GDIR, "geometry_proposal.csv"), IDIR)
G = {r["Proposal_ID"]: r for r in R.load(os.path.join(GDIR, "geometry_proposal.csv"))}
I = {r["Proposal_ID"]: r for r in R.load(os.path.join(IDIR, "identity_proposal.csv"))}


def idn(**over):
    d = {"verdict": "CONFIRMED", "xFactor": "TIMEPOINT", "seriesFactor": "GROUP", "markType": "BAR_MONO",
         "series": [{"name": "ALL", "colour": None, "line_style": "", "marker": "", "marker_fill": "",
                     "bar_fill": "OPEN", "cue": ""}],
         "route": "AUTO", "outcome": "Heart rate", "unit": "bpm", "n": "", "barTop": "OUTLINE_CENTER", "stem": True,
         "positions": [{"label": "A%d" % k, "px": 110 + 50 * k} for k in range(5)], "say": "근거"}
    d.update(over)
    return d


def geo(**over):
    d = {"verdict": "CONFIRMED", "top": "", "bottom": "", "rows": [], "frame": "", "shared": "", "say": "근거"}
    d.update(over)
    return d


PROPS = {"BY": "Claude", "P": {"D1__p1": {"geo": geo(top="100", bottom="0"), "idn": idn(), "look": "먼저 볼 것"},
                               "D1__p2": {"geo": geo(), "idn": {"verdict": "REJECTED", "say": "연속 x"}, "look": ""}}}
PJ = os.path.join(TMP, "proposals.json")


def save(props):
    with io.open(PJ, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False)
    return PJ


print("제안을 두 페이지의 상태 칸으로")
gm, im = A.metas(G, I, ["D1__p1", "D1__p2"])
check("기하 META의 값이 붙는 자리는 리더가 잰 눈금의 양 끝",
      gm["D1__p1"]["topPixel"] == G["D1__p1"]["Y_Tick_Pixels"].split(";")[0]
      and gm["D1__p1"]["bottomPixel"] == G["D1__p1"]["Y_Tick_Pixels"].split(";")[-1], gm["D1__p1"])
check("같은 래스터의 다른 패널이 축을 빌려 올 후보", gm["D1__p1"]["siblings"] == ["D1__p2"], gm["D1__p1"]["siblings"])
gs, ist, pg, pi = A.states(PROPS["P"]["D1__p1"], dict(im["D1__p1"], readOutcome="Heart rate", readUnit=""), "Claude")
# REVERT: 리더와 같은 이름도 제안의 것으로 넣는다. Value_Sources가 리더가 맞힌 것을 셀 수 없습니다.
check("리더가 읽은 결과 이름과 같으면 비워 두어 리더의 것으로 나간다", ist["outcome"] == "" and "결과 이름 리더" in pi, (ist, pi))
check("리더와 다른 단위는 제안의 것으로", ist["unit"] == "bpm" and "단위 Claude" in pi, (ist, pi))
check("눈금 값만 적은 기하는 리더가 잰 행에 붙는다(행을 넣지 않는다)",
      gs == {"verdict": "CONFIRMED", "top": "100", "bottom": "0"} and "행은 리더가 잰 것" in pg, (gs, pg))
gs, ist, pg, pi = A.states({"geo": geo(top="9", bottom="1", rows=[40, 260], frame="60,360,40,260"), "idn": idn(unit="")},
                           dict(im["D1__p1"], readUnit="A%"), "Claude")
# REVERT: 다시 그린 프레임을 넘기지 않는다. 관문이 리더의 프레임에 사람의 값을 붙입니다.
check("다시 그린 프레임과 찍은 행이 상태로 간다", gs.get("frame") == "60,360,40,260"
      and (gs.get("pickedTopPixel"), gs.get("pickedBottomPixel")) == (40, 260) and "다시 그림" in pg, gs)
# REVERT: 단위를 비우는 제안을 알리지 않는다. 리더가 잘못 읽은 'A%'가 단위로 나갑니다.
check("리더가 읽은 단위를 비우는 제안은 unitBlank", ist.get("unitBlank") is True and ist["unit"] == "", ist)
gs, ist, pg, pi = A.states({"geo": geo(rows=[50, 250], top="9", bottom="1"), "idn": {"verdict": "REJECTED"}},
                           im["D1__p2"], "Claude")
check("프레임 없이 찍은 행만 있으면 리더 프레임 위의 찍은 행", "frame" not in gs and gs["pickedTopPixel"] == 50
      and pg.startswith("프레임 리더"), (gs, pg))
check("읽지 않는다 제안은 판정만 간다", ist == {"verdict": "REJECTED"} and "읽지 않는다" in pi, (ist, pi))

print()
print("짓기 전에 멈추는 자리")
check("제안 파일과 리더 제안이 맞으면 멈출 것이 없다", A.check_inputs(G, I, PROPS["P"]) == [])
# REVERT: 얹을 제안이 없는 패널을 그냥 둔다. 그 패널은 카드 없이 두 파일 사이에서 빠집니다.
stops = A.check_inputs(G, I, {"D1__p1": PROPS["P"]["D1__p1"]})
check("리더 제안은 있는데 얹을 제안이 없으면 멈춘다", [s[1] for s in stops] == ["NO_PROPOSAL"], stops)
# REVERT: --subset이어도 리더 제안 전부를 맞춰 본다. 고칠 곳 몇 개만 다시 물을 길이 없습니다.
check("--subset이면 제안 파일의 패널만 본다", A.check_inputs(G, I, {"D1__p1": PROPS["P"]["D1__p1"]}, subset=True) == [])
moved = {"D1__p1": dict(PROPS["P"]["D1__p1"], geo=geo(top="9", bottom="1", rows=[40, 260], frame="62,358,40,262")),
         "D1__p2": PROPS["P"]["D1__p2"]}
# REVERT: 두 카드의 프레임을 맞춰 보지 않는다. make_plan이 확인된 정체를 '다른 프레임 위'라며 다시 묻습니다.
stops = A.check_inputs(G, I, moved)
check("다시 그린 프레임이 정체 카드의 프레임과 다르면 멈춘다", [s[1] for s in stops] == ["FRAMES_DISAGREE"], stops)
R.reframe(RUN, os.path.join(GDIR, "geometry_proposal.csv"), IDIR, {"D1__p1": "62,358,40,262"})
I2 = {r["Proposal_ID"]: r for r in R.load(os.path.join(IDIR, "identity_proposal.csv"))}
check("reframe 뒤에는 멈출 것이 없다", A.check_inputs(G, I2, moved) == [], A.check_inputs(G, I2, moved))
try:
    A.build(RUN, GDIR, IDIR, save({"BY": "Claude", "P": {"D1__p1": PROPS["P"]["D1__p1"]}}), "2026-10-16", log=lambda *_: None)
    stopped = False
except SystemExit:
    stopped = True
check("멈출 것이 있으면 페이지를 짓지 않는다", stopped)

print()
print("페이지에 실리는 것")
html, info = A.build(RUN, GDIR, IDIR, save({"BY": "Claude", "P": moved}), "2026-10-16", log=lambda *_: None)
check("패널마다 카드 하나", len(re.findall(r"<div class='doc' id='c-", html)) == 2 and info["panels"] == 2, info)
# REVERT: '제안대로'를 미리 고르지 않는다. 96패널이면 192번 고릅니다.
check("두 부분 모두 '제안대로'가 미리 골라져 있다", len(re.findall(r"value='ACCEPT' checked", html)) == 4)
# REVERT: 목격을 미리 누른다. 그림을 안 연 카드가 본 카드가 됩니다.
check("'두 그림을 직접 봤다'는 미리 눌러져 있지 않다", re.search(r"data-seen='[^']*' checked", html) is None
      and "type='checkbox' data-seen" in html)
check("판정 논리는 두 페이지의 것이 실린다", html.count("function verdictOf(") == 2 and "function makeCheck(" in html)
check("다시 그린 프레임은 파란 점선으로 그림 위에", "class='ov ovf'" in html)
check("제안한 쪽의 이름이 카드와 Note 출처에", "Claude가 다시 그린 프레임" in html and "프레임 Claude(다시 그림)" in html)
check("'먼저 보세요'는 맨 위에 모은다", "먼저 보세요 (1)" in html)
check("읽지 않는다 제안의 카드", "이 패널은 읽지 않는다(수작업 판독)" in html)
html2, _ = A.build(RUN, GDIR, IDIR, save({"P": moved}), "2026-10-16", log=lambda *_: None)
check("제안한 쪽이 적혀 있지 않으면 '제안'으로 부른다", "프레임 제안(다시 그림)" in html2)
html3, info3 = A.build(RUN, GDIR, IDIR, save({"BY": "Claude", "P": {"D1__p2": moved["D1__p2"]}}), "2026-10-17",
                       log=lambda *_: None, subset=True)
check("--subset 페이지는 그 패널의 카드만", info3["panels"] == 1 and "id='c-D1__p2'" in html3 and "id='c-D1__p1'" not in html3, info3)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("all scenarios passed")
