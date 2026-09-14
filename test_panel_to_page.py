# -*- coding: utf-8 -*-
"""크롭 픽셀을 600 DPI 래스터로 옮기는 결정들.

    python3 test_panel_to_page.py     # exit 0 = all scenarios pass

그림은 전부 여기서 만듭니다: 페이지 하나, 그 안의 정확한 부분 배열인 크롭 하나,
그리고 렌더러 대신 크롭을 세 배로 키워 돌려주는 가짜. pdftoppm은 필요 없습니다 -
렌더러가 무엇을 그리는지는 명령을 보고, 그린 것을 어떻게 다루는지는 가짜로 봅니다.
"""
import io
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import panel_to_page as P                                        # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


# 페이지: 300x400 px가 100x(400/3) pt를 그린 것 - 배율 3.0 px/pt, 200 DPI가 아닙니다.
rng = np.random.RandomState(7)
PAGE = np.full((400, 300), 255, dtype=np.uint8)
PAGE[40:340, 30:270] = rng.randint(0, 256, size=(300, 240)).astype(np.uint8)   # 잉크
PAGE_PT = (100.0, 400.0 / 3.0)
SCALE = P.page_scale(PAGE.shape, PAGE_PT)
# 크롭: 자리 (57, 61)에서 잘라 낸 정확한 부분 배열. 상자는 (50/3, 55/3, ...) pt -
# crop_figure가 하듯 8 px를 두르고 여백을 잘라 낸 셈입니다.
OX, OY, CW, CH = 57, 61, 180, 240
CROP = PAGE[OY:OY + CH, OX:OX + CW].copy()
BBOX = ((OX - 3) / 3.0, (OY - 2) / 3.0, (OX + CW + 5) / 3.0, (OY + CH + 4) / 3.0)

print("배율은 재는 것이다")
check("배율은 래스터 크기 ÷ 페이지 pt", SCALE == (3.0, 3.0), SCALE)

print()
print("크롭의 자리는 찾는 것이다")
check("정확한 부분 배열이면 그 자리를 낸다", P.find_crop(PAGE, CROP, BBOX, SCALE) == (OX, OY),
      P.find_crop(PAGE, CROP, BBOX, SCALE))
# REVERT: 가장 비슷한 자리를 같은 자리로 친다. 다른 렌더에서 나온 크롭도 어딘가에
# 가장 비슷한 자리는 있고, 거기에 상자를 옮기면 아무도 모르는 채로 어긋납니다.
other = CROP.copy(); other[100, 100] ^= 0x40
check("픽셀 하나라도 다르면 자리가 아니다", P.find_crop(PAGE, other, BBOX, SCALE) is None)
check("창이 크롭보다 작으면 같은 자리가 없다",
      P.find_crop(PAGE, CROP, (0.0, 0.0, 10.0, 10.0), SCALE) is None)

print()
print("옮기는 셈")
# REVERT: 크롭의 자리를 더하지 않는다. 크롭 픽셀이 페이지 픽셀인 줄 알고 나눕니다.
pt = P.crop_box_to_pt((30, 60, 90, 120), (OX, OY), SCALE)
check("크롭 상자 → 페이지 pt는 자리를 더하고 배율로 나눈다",
      pt == ((OX + 30) / 3.0, (OY + 60) / 3.0, (OX + 90) / 3.0, (OY + 120) / 3.0), pt)
frame = P.raster_frame((OX, OY), CROP.shape, SCALE, dpi=600)
check("래스터 틀은 크롭 자리와 크기를 600 DPI 픽셀로",
      frame == (int(round(OX / 3.0 * 600 / 72)), int(round(OY / 3.0 * 600 / 72)),
                int(round(CW / 3.0 * 600 / 72)), int(round(CH / 3.0 * 600 / 72))), frame)
reg = P.region_600(pt, frame, dpi=600)
check("Region_600은 래스터 원점을 뺀 픽셀",
      reg == tuple(int(round(v * 600 / 72)) - o for v, o in zip(pt, (frame[0], frame[1], frame[0], frame[1]))),
      reg)
cmd = P.render_command("a.pdf", 5, (10, 20, 300, 400), "out/x", dpi=600)
check("렌더 명령은 그 페이지의 그 자리만, 600 DPI로",
      cmd[:3] == ["pdftoppm", "-r", "600"] and cmd[cmd.index("-f") + 1] == "5"
      and cmd[cmd.index("-l") + 1] == "5" and cmd[cmd.index("-x") + 1:cmd.index("-x") + 8]
      == ["10", "-y", "20", "-W", "300", "-H", "400"] and "-singlefile" in cmd, cmd)

print()
print("옮긴 뒤에 되돌려 본다")
import cv2                                                       # noqa: E402
BIG = cv2.resize(CROP, (CW * 3, CH * 3), interpolation=cv2.INTER_NEAREST)
ncc, shift = P.roundtrip(BIG, CROP)
check("제자리면 어긋남 0", shift == (0, 0) and ncc > 0.95, (ncc, shift))
moved = np.roll(BIG, 6, axis=1)                                   # 600 DPI에서 6 px = 크롭 2 px
ncc2, shift2 = P.roundtrip(moved, CROP)
check("민 래스터는 어긋남이 보인다", shift2 is not None and abs(shift2[0]) == 2, (ncc2, shift2))

print()
print("변환기가 무엇을 옮기고 무엇을 거절하는가")
TMP = tempfile.mkdtemp(prefix="fdt-p2p-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "crops")); os.makedirs(os.path.join(RUN, "pages"))
from PIL import Image                                            # noqa: E402
Image.fromarray(PAGE).save(os.path.join(RUN, "pages", "p1.png"))
Image.fromarray(CROP).save(os.path.join(RUN, "crops", "D1.png"))
Image.fromarray(other).save(os.path.join(RUN, "crops", "D2.png"))
with io.open(os.path.join(RUN, "doc.pdf"), "wb") as fh:
    fh.write(b"%PDF-1.4 not really\n")
PDF_SHA = P.sha256(os.path.join(RUN, "doc.pdf"))
CROP_SHA = P.sha256(os.path.join(RUN, "crops", "D1.png"))
PDFS = {"doc.pdf": os.path.join(RUN, "doc.pdf")}


def draft(fid, crop="crops/D1.png", pdf_sha=PDF_SHA):
    return {"Draft_ID": fid, "Source_File": "doc.pdf", "Source_File_SHA256": pdf_sha,
            "Page": "1", "Page_Raster": "pages/p1.png", "Figure_Crop": crop,
            "Page_Width_Pt": "%r" % PAGE_PT[0], "Page_Height_Pt": "%r" % PAGE_PT[1],
            "Figure_BBox": "%.4f,%.4f,%.4f,%.4f" % BBOX}


def panel(fid, i, mark="LINE", count="2", verdict="PANELS", crop_sha=CROP_SHA):
    return {"Draft_ID": fid, "Panel_Index": str(i), "X0": "30", "Y0": "60", "X1": "90", "Y1": "120",
            "Mark_Type": mark, "Mark_Count": count, "Mark_Type_2": "", "Mark_Count_2": "",
            "Overlay": "", "Crop_SHA256": crop_sha, "Verdict": verdict,
            "Verified_By": "RV", "Verified_At": "2026-09-13"}


def fake_renderer(pdf, page, frame, out_path, dpi):
    """크롭을 정확히 frame 크기로 키운 것을 '렌더'로 돌려준다."""
    big = cv2.resize(CROP, (frame[2], frame[3]), interpolation=cv2.INTER_LINEAR)
    Image.fromarray(big).save(out_path)
    return ""


def run(decisions, drafts=None, renderer=fake_renderer, pdfs=PDFS):
    out = os.path.join(TMP, "out%d" % N[0])
    return P.convert(RUN, decisions, drafts or {"D1": draft("D1"), "D2": draft("D2", "crops/D2.png")},
                     pdfs, out, renderer=renderer)


rows, ref, _ = run([panel("D1", 1), panel("D1", 2, "BAR", "4")])
check("패널마다 한 줄, 종류·개수·검토자는 그대로",
      not ref and len(rows) == 2 and rows[1]["Mark_Type"] == "BAR" and rows[1]["Mark_Count"] == "4"
      and rows[0]["Verified_By"] == "RV" and rows[0]["Crop_Origin_Px"] == "%d,%d" % (OX, OY)
      and rows[0]["Roundtrip_Shift_Px"] == "0,0", (ref, rows and rows[0]))
check("Region_600은 geometry_proposer가 받을 픽셀 상자",
      rows and rows[0]["Region_600"] == "%d,%d,%d,%d" % P.region_600(
          P.crop_box_to_pt((30, 60, 90, 120), (OX, OY), SCALE),
          P.raster_frame((OX, OY), CROP.shape, SCALE)), rows and rows[0]["Region_600"])
# REVERT: 읽을 값 없는 패널과 패널 없는 그림도 옮긴다. 축을 읽을 자리가 아닌데
# 기하 제안이 거기서 눈금을 찾습니다.
rows, ref, _ = run([panel("D1", 1, "NOT_DATA", ""), panel("D1", 2)])
check("읽을 값 없는 패널은 옮기지 않는다", not ref and [r["Panel_Index"] for r in rows] == ["2"])
rows, ref, _ = run([panel("D1", 0, "", "", verdict="NO_PANELS")])
check("패널 없는 그림은 옮길 것도 거절할 것도 없다", not rows and not ref, (rows, ref))
# REVERT: 크롭 지문을 보지 않는다. 판정이 본 크롭과 다른 크롭 위의 좌표를 옮깁니다.
rows, ref, _ = run([panel("D1", 1, crop_sha="0" * 64)])
check("판정이 본 크롭이 아니면 거절", [c for _, c, _ in ref] == ["CROP_CHANGED"] and not rows, ref)
# REVERT: PDF 지문을 보지 않는다. 다른 PDF를 그려 놓고 같은 이름이라 믿습니다.
rows, ref, _ = run([panel("D1", 1)], drafts={"D1": draft("D1", pdf_sha="1" * 64)})
check("초안의 PDF가 아니면 거절", [c for _, c, _ in ref] == ["PDF_CHANGED"] and not rows, ref)
rows, ref, _ = run([panel("D1", 1)], pdfs={})
check("PDF가 없으면 거절", [c for _, c, _ in ref] == ["PDF_MISSING"], ref)
rows, ref, _ = run([panel("D2", 1, crop_sha=P.sha256(os.path.join(RUN, "crops", "D2.png")))])
check("페이지에 없는 크롭은 거절", [c for _, c, _ in ref] == ["CROP_NOT_IN_PAGE"] and not rows, ref)


def wrong_size(pdf, page, frame, out_path, dpi):
    Image.fromarray(cv2.resize(CROP, (frame[2] + 3, frame[3]))).save(out_path); return ""


def shifted(pdf, page, frame, out_path, dpi):
    big = cv2.resize(CROP, (frame[2], frame[3]), interpolation=cv2.INTER_LINEAR)
    Image.fromarray(np.roll(big, 6, axis=1)).save(out_path); return ""


def broken(pdf, page, frame, out_path, dpi):
    return "RENDER_FAILED"


# REVERT: 렌더러가 낸 크기를 믿는다. 부탁한 틀과 다른 크기의 래스터 위에서 같은
# 좌표를 쓰면 상자가 안쪽으로 밀립니다.
rows, ref, _ = run([panel("D1", 1)], renderer=wrong_size)
check("부탁한 크기와 다른 래스터는 거절", [c for _, c, _ in ref] == ["RENDER_SIZE_MISMATCH"], ref)
# REVERT: 되돌려 본 어긋남을 보지 않는다. 렌더러가 옆 자리를 그려도 좌표는 그대로 나갑니다.
rows, ref, _ = run([panel("D1", 1)], renderer=shifted)
check("되돌려 보니 어긋난 래스터는 거절", [c for _, c, _ in ref] == ["ROUNDTRIP_SHIFTED"], ref)
rows, ref, _ = run([panel("D1", 1)], renderer=broken)
check("렌더러의 거절은 그대로 이름을 대고 나간다", [c for _, c, _ in ref] == ["RENDER_FAILED"], ref)
# REVERT: 시계를 보지 않는다. 두 분에 끊기는 셸에서 265장을 시작하면 셋째 장에서
# 죽고, 어디까지 했는지 아무도 모릅니다.
rows, ref, left = P.convert(RUN, [panel("D1", 1)], {"D1": draft("D1")}, PDFS,
                            os.path.join(TMP, "late"), renderer=fake_renderer, deadline=0)
check("시계가 지나면 손대지 않은 그림을 이름으로 낸다", not rows and not ref and left == ["D1"], (rows, ref, left))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("all scenarios passed")
