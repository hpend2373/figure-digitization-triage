# -*- coding: utf-8 -*-
"""600 DPI 패널에 기하·정체 제안을 돌리는 실행기의 결정들.

    python3 test_propose_run.py     # exit 0 = all scenarios pass

래스터는 여기서 그립니다: 왼쪽에 막대 다섯 개의 상자 플롯, 오른쪽에 빈 영역 하나.
tesseract가 없어도 돕니다 - 눈금 읽기가 거절되는 것은 이 실행기가 볼 일이 아닙니다.
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

import propose_run as R                                          # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import geometry_proposer as GP                                   # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def chart():
    """왼쪽 0..400: 상자 프레임 + 눈금 11개 + 막대 다섯. 오른쪽 420..800: 비어 있음."""
    im = Image.new("RGB", (800, 320), "white")
    d = ImageDraw.Draw(im)
    x0, x1, y0, y1 = 60, 360, 30, 270
    d.rectangle((x0, y0, x1, y1), outline="black")
    for i in range(11):
        y = y0 + i * (y1 - y0) / 10.0
        d.line((x0 - 5, y, x0 - 1, y), fill="black")
    for g in range(5):
        cx = x0 + 50 * (g + 1)
        d.rectangle((cx - 9, y1 - 60 - 20 * g, cx + 9, y1 - 1), outline="black")
    return im


def write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


TMP = tempfile.mkdtemp(prefix="fdt-prun-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "seg", "r600"))
chart().save(os.path.join(RUN, "seg", "r600", "D1_600.png"))
import hashlib                                                   # noqa: E402
SHA = hashlib.sha256(open(os.path.join(RUN, "seg", "r600", "D1_600.png"), "rb").read()).hexdigest()
REG = os.path.join(RUN, "seg", "r600", "panel_regions_600.csv")
write_csv(REG, [
    {"Draft_ID": "D1", "Panel_Index": "1", "Mark_Type": "BAR", "Mark_Count": "5", "Raster_600": "seg/r600/D1_600.png",
     "Raster_600_SHA256": SHA, "Region_600": "0,0,400,320"},
    {"Draft_ID": "D1", "Panel_Index": "2", "Mark_Type": "LINE", "Mark_Count": "", "Raster_600": "seg/r600/D1_600.png",
     "Raster_600_SHA256": SHA, "Region_600": "420,0,800,320"}])
write_csv(os.path.join(RUN, "figure_intake_draft.csv"), [{"Draft_ID": "D1", "Caption_Text": "Fig. 1 Bars (n = 8)."}])
GDIR, IDIR = os.path.join(RUN, "seg", "g"), os.path.join(RUN, "seg", "i")


def clock_of(*ticks):
    it = iter(ticks)
    last = [0]

    def clock():
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]
    return clock


print("기하")
# REVERT: 시계를 보지 않는다. 몇 분에 끊기는 셸에서 96패널을 시작하면 어디까지 했는지 모릅니다.
n, left = R.geometry_batch(RUN, REG, GDIR, budget=5, clock=clock_of(0, 0, 100))
check("예산이 지나면 패널 사이에서 멈추고 남은 수를 낸다", (n, left) == (1, 1), (n, left))
n, left = R.geometry_batch(RUN, REG, GDIR, budget=5, clock=clock_of(0, 0, 0))
check("다시 부르면 남은 패널만 이어 한다", (n, left) == (1, 0), (n, left))
props = R.load(os.path.join(GDIR, "geometry_proposal.csv"))
refs = R.load(os.path.join(GDIR, GP.REFUSED))
check("프레임을 찾은 패널은 제안, 빈 영역은 거절로", [p["Proposal_ID"] for p in props] == ["D1__p1"]
      and [r["Proposal_ID"] for r in refs] == ["D1__p2"], (props, refs))
# REVERT: 패널이 무엇인지 적지 않는다. 카드가 어느 그림의 무슨 표인지 말하지 못합니다.
check("제안과 거절에 어느 패널의 무엇인지 적힌다", props and props[0]["Note"] == "D1 p1 BAR x5"
      and refs and "D1 p2 LINE" in refs[0].get("Note", ""), (props and props[0]["Note"], refs))
check("두 패널 모두 사람이 볼 그림이 있다", all(os.path.isfile(os.path.join(GDIR, p + ".png")) for p in ("D1__p1", "D1__p2")))
n, left = R.geometry_batch(RUN, REG, GDIR)
check("이미 적힌 패널은 다시 하지 않는다", (n, left) == (0, 0)
      and len(R.load(os.path.join(GDIR, "geometry_proposal.csv"))) == 1, (n, left))

print()
print("정체")
n, left = R.identity_batch(RUN, REG, os.path.join(GDIR, "geometry_proposal.csv"), IDIR, budget=5, clock=clock_of(0, 100))
check("정체도 예산이 지나면 멈춘다", (n, left) == (0, 1), (n, left))
# 프레임 없는 기하 행(사람이 '읽을 플롯이 없다'고 한 것)이 섞인 파일
GMIX = os.path.join(TMP, "geometry_mixed.csv")
rows_mix = R.load(os.path.join(GDIR, "geometry_proposal.csv"))
rows_mix.append(dict(rows_mix[0], Proposal_ID="D1__p2", Panel_X0="", Panel_X1="", Panel_Y0="", Panel_Y1=""))
write_csv(GMIX, rows_mix)
n, left = R.identity_batch(RUN, REG, GMIX, IDIR)
ip = R.load(os.path.join(IDIR, IP.PROPOSALS))
check("프레임 있는 기하 행에만 정체 제안", (n, left) == (1, 0) and [r["Proposal_ID"] for r in ip] == ["D1__p1"], (n, left, ip))
g1 = props[0]
check("정체 카드의 프레임은 기하 제안의 프레임", ip and all(int(float(ip[0][k])) == int(float(g1[k]))
                                             for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")), ip and ip[0])
# REVERT: 패널 종류를 넘기지 않는다. 표 종류 제안이 비어 사람이 다시 고릅니다.
check("패널 종류는 패널 판정에서", ip and ip[0]["Panel_Kind"] == "BAR", ip and ip[0]["Panel_Kind"])
n, left = R.identity_batch(RUN, REG, os.path.join(GDIR, "geometry_proposal.csv"), IDIR)
check("정체도 이미 적힌 패널은 다시 하지 않는다", (n, left) == (0, 0) and len(R.load(os.path.join(IDIR, IP.PROPOSALS))) == 1)

print()
print("다시 그린 프레임 위의 정체")
GCSV = os.path.join(GDIR, "geometry_proposal.csv")
before = io.open(os.path.join(IDIR, IP.PROPOSALS), encoding="utf-8").read()
try:
    R.reframe(RUN, GCSV, IDIR, {"D9__p1": "70,350,40,268"})
    stopped = False
except SystemExit:
    stopped = True
check("기하 제안에 없는 패널은 멈추고 아무것도 쓰지 않는다", stopped and not os.path.exists(os.path.join(IDIR, R.READER_FRAMES))
      and io.open(os.path.join(IDIR, IP.PROPOSALS), encoding="utf-8").read() == before)
GOTHER = os.path.join(TMP, "geometry_other.csv")
write_csv(GOTHER, [dict(R.load(GCSV)[0], Proposal_ID="D7__p1")])
try:
    R.reframe(RUN, GOTHER, IDIR, {"D1__p1": "70,350,40,268"})
    stopped = False
except SystemExit:
    stopped = True
# REVERT: 기하 제안에 있는지 보지 않는다. 정체 제안에만 있는 패널은 기하 행 없이 다시 내다 넘어집니다.
check("정체 제안에만 있고 기하 제안에 없는 패널도 이름을 대고 멈춘다", stopped)
# REVERT: 정수만 받지 않는다. 기하 관문은 반올림, 정체 제안은 버림 - 696.5와 1633.5는 두 카드에서 갈립니다.
try:
    R.reframe(RUN, GCSV, IDIR, {"D1__p1": "70,350,40.5,268"})
    stopped = False
except SystemExit:
    stopped = True
check("정수가 아닌 프레임은 멈춘다", stopped)
done = R.reframe(RUN, GCSV, IDIR, {"D1__p1": "70,350,40,268"})
ip = R.load(os.path.join(IDIR, IP.PROPOSALS))
check("정체 제안의 프레임이 다시 그린 프레임이 된다", done and done[0][2] == "70,350,40,268"
      and (ip[0]["Panel_X0"], ip[0]["Panel_X1"], ip[0]["Panel_Y0"], ip[0]["Panel_Y1"]) == ("70", "350", "40", "268"), (done, ip))
# REVERT: 처음 파일을 남기지 않는다. 리더 프레임 위의 제안이 무엇이었는지 아무도 모릅니다.
keep = R.load(os.path.join(IDIR, R.READER_FRAMES))
check("처음 정체 제안은 reader_frames로 한 번 남는다",
      bool(keep) and int(float(keep[0]["Panel_X0"])) == int(float(g1["Panel_X0"])), keep)
first = io.open(os.path.join(IDIR, IP.PROPOSALS), encoding="utf-8").read()
R.reframe(RUN, GCSV, IDIR, {"D1__p1": "70,350,40,268"})
check("두 번 돌려도 같은 결과", io.open(os.path.join(IDIR, IP.PROPOSALS), encoding="utf-8").read() == first)
R.reframe(RUN, GCSV, IDIR, {"D1__p1": "64,356,34,270"})
keep2 = R.load(os.path.join(IDIR, R.READER_FRAMES))
check("다시 그리기는 늘 리더 프레임의 원본에서 시작한다", keep2 == keep
      and R.load(os.path.join(IDIR, IP.PROPOSALS))[0]["Panel_X0"] == "64", keep2)
# REVERT: 늘 원본에서 시작하지 않는다. 프레임 목록에서 빠진 패널이 지난 다시 그리기를 그대로 듭니다.
R.reframe(RUN, GCSV, IDIR, {})
check("프레임 목록에서 빠진 패널은 리더 프레임으로 돌아간다",
      R.load(os.path.join(IDIR, IP.PROPOSALS))[0]["Panel_X0"] == keep[0]["Panel_X0"])

print()
print("프레임 목록")
FJ = os.path.join(TMP, "props.json")
with io.open(FJ, "w", encoding="utf-8") as fh:
    json.dump({"P": {"A__p1": {"geo": {"frame": "1,2,3,4"}}, "A__p2": {"geo": {"frame": ""}}}, "DRAWN": ["A__p1"]}, fh)
check("확인 페이지의 제안 파일에서는 프레임 있는 패널만", R.frames_from(FJ) == {"A__p1": "1,2,3,4"}, R.frames_from(FJ))
with io.open(FJ, "w", encoding="utf-8") as fh:
    json.dump({"A__p1": "1,2,3,4"}, fh)
check("프레임 목록 그대로도 받는다", R.frames_from(FJ) == {"A__p1": "1,2,3,4"})
check("네 수가 아니면 쓸 수 없다", R.frame_problem("1,2,3") != "")
# REVERT: 뒤집힌 프레임을 받는다.
check("왼쪽≥오른쪽이면 쓸 수 없다", R.frame_problem("5,2,3,4") != "" and R.frame_problem("1,2,3,4") == "")

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("all scenarios passed")
