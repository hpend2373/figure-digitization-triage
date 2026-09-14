# -*- coding: utf-8 -*-
"""확인된 패널 자리를 크롭 픽셀에서 600 DPI 그림 래스터로 옮깁니다.

    python3 panel_to_page.py --run DIR --decisions DIR/seg/panel_decisions.csv \\
        --pdfs DIR/seg/_pdf_locations.json --out DIR/seg/regions600

`record_panels.py`가 적은 상자는 **200 DPI 크롭 위의 픽셀**입니다. 축을 읽는
`geometry_proposer`는 600 DPI 래스터를 봅니다. 둘 사이를 잇는 것이 이 파일이고,
잘못 이으면 그 뒤의 기하 확인·읽기·값 검토가 전부 다른 자리를 보게 됩니다.

## 크롭의 자리는 상자 좌표로 알 수 없다

크롭은 `Figure_BBox`를 그대로 잘라 낸 것이 아닙니다. `corpus_intake.crop_figure`는
상자에 8 px를 두르고 나서 바깥 여백을 **잘라 냅니다** - 얼마나 잘랐는지는 어디에도
적혀 있지 않습니다. 실제로 한 그림에서 상자로 계산한 자리와 크롭의 진짜 자리가
9 px 달랐고, 600 DPI에서는 27 px입니다. 그래서 자리는 계산하지 않고 **찾습니다**:
크롭은 페이지 래스터의 정확한 부분 배열이라, 상자 근처에서 픽셀이 한 장 같은
자리가 꼭 하나 있습니다. 같은 자리가 없으면 그 크롭은 이 페이지 래스터에서 나온
것이 아니고, 옮길 수 없습니다.

## 배율은 재는 것이다

페이지 래스터는 "200 DPI"라 부르지만 실제 배율은 **래스터 폭 ÷ 페이지 폭(pt)**
입니다. `crop_figure`가 같은 이유로 그렇게 잽니다 - 픽셀 수를 짝수로 맞춘
렌더러는 모든 크롭을 머리카락만큼 밀어 놓습니다.

## 옮긴 뒤에 되돌려 본다

600 DPI 래스터를 크롭 크기로 줄여 크롭 위에 다시 올려 봅니다. 자리가 맞으면 가장
잘 맞는 어긋남이 0 px입니다. 1 px 넘게 어긋나면 렌더러가 다른 자리를 그린 것이고,
그 래스터 위의 좌표는 답이 아닙니다. 상관값(NCC)도 적지만 문턱은 두지 않습니다 -
잉크가 적은 그림은 상관값이 낮아도 자리는 맞고, 어긋남이 그것을 가립니다.

좌표 규약: `Panel_Page_Pt`는 페이지 왼쪽 위가 원점, y는 아래로 - `Figure_BBox`와
같습니다. `Region_600`은 그 그림의 600 DPI 래스터 안의 픽셀이고,
`geometry_proposer --region`이 받는 것입니다.

이 파일은 아무것도 판정하지 않습니다. 종류·개수·검토자는 `panel_decisions.csv`에서
그대로 옮겨 적습니다.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time

import numpy as np

DPI = 600
PT_PER_INCH = 72.0
PAD = 8          # crop_figure가 두른 여백
SLACK = 4        # 그 위에 더 보는 창
SHIFT_MAX = 1    # 되돌려 본 어긋남의 한계(크롭 픽셀)

COLUMNS = [
    "Draft_ID", "Panel_Index", "Mark_Type", "Mark_Count", "Mark_Type_2",
    "Mark_Count_2", "Overlay", "Source_File", "Source_File_SHA256", "Page",
    "Page_Raster_SHA256", "Crop_SHA256", "Crop_Origin_Px", "Page_Scale_Px_Per_Pt",
    "Panel_Crop_Px", "Panel_Page_Pt", "Raster_600", "Raster_600_SHA256",
    "Raster_600_Origin_Px", "Region_600", "Roundtrip_NCC", "Roundtrip_Shift_Px",
    "Verified_By", "Verified_At",
]


def sha256(path):
    with io.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def gray(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8)


def page_scale(page_shape, page_pt):
    """(sx, sy) 픽셀/pt. 래스터 크기와 페이지 크기에서 잽니다."""
    h, w = page_shape[:2]
    return (w / float(page_pt[0]), h / float(page_pt[1]))


def find_crop(page, crop, bbox_pt, scale, pad=PAD, slack=SLACK):
    """크롭이 페이지 래스터의 어느 자리인가. (ox, oy) 또는 None.

    `bbox_pt` 근처의 창에서 찾고, 찾은 자리의 픽셀이 **한 장 같아야** 합니다.
    가장 비슷한 자리는 언제나 있습니다 - 그것이 같은 자리라는 뜻은 아닙니다.
    """
    import cv2
    ch, cw = crop.shape[:2]
    ph, pw = page.shape[:2]
    x0, y0, x1, y1 = bbox_pt
    sx, sy = scale
    left = max(0, int(x0 * sx) - pad - slack)
    top = max(0, int(y0 * sy) - pad - slack)
    right = min(pw, int(x1 * sx) + pad + slack)
    bottom = min(ph, int(y1 * sy) + pad + slack)
    window = page[top:bottom, left:right]
    # 창이 크롭보다 작으면 cv2가 둘을 바꿔 재고, 아래 등호 검사가 어차피 막습니다 -
    # 크기 검사를 따로 두면 변이가 살아남는 장식이었습니다.
    score = cv2.matchTemplate(window, crop, cv2.TM_SQDIFF)
    _, _, best, _ = cv2.minMaxLoc(score)
    ox, oy = best[0] + left, best[1] + top
    if not np.array_equal(page[oy:oy + ch, ox:ox + cw], crop):
        return None
    return ox, oy


def crop_box_to_pt(box_px, origin, scale):
    """크롭 픽셀 상자 → 페이지 pt. 크롭의 자리(origin)를 더하고 배율로 나눕니다."""
    ox, oy = origin
    sx, sy = scale
    x0, y0, x1, y1 = box_px
    return ((ox + x0) / sx, (oy + y0) / sy, (ox + x1) / sx, (oy + y1) / sy)


def pt_to_px(v, dpi=DPI):
    return v * dpi / PT_PER_INCH


def raster_frame(origin, crop_shape, scale, dpi=DPI):
    """그림 래스터가 페이지 위에서 차지할 자리, dpi 픽셀로. (x, y, w, h)."""
    ox, oy = origin
    ch, cw = crop_shape[:2]
    sx, sy = scale
    x = int(round(pt_to_px(ox / sx, dpi)))
    y = int(round(pt_to_px(oy / sy, dpi)))
    w = int(round(pt_to_px(cw / sx, dpi)))
    h = int(round(pt_to_px(ch / sy, dpi)))
    return x, y, w, h


def region_600(box_pt, frame, dpi=DPI):
    """페이지 pt 상자 → 그 그림 래스터 안의 픽셀 상자."""
    x, y = frame[0], frame[1]
    x0, y0, x1, y1 = box_pt
    return (int(round(pt_to_px(x0, dpi))) - x, int(round(pt_to_px(y0, dpi))) - y,
            int(round(pt_to_px(x1, dpi))) - x, int(round(pt_to_px(y1, dpi))) - y)


def render_command(pdf, page, frame, stem, dpi=DPI):
    """pdftoppm으로 페이지의 그 자리만 그리는 명령. 픽셀은 dpi 기준입니다."""
    x, y, w, h = frame
    return ["pdftoppm", "-r", str(int(dpi)), "-f", str(int(page)), "-l", str(int(page)),
            "-x", str(int(x)), "-y", str(int(y)), "-W", str(int(w)), "-H", str(int(h)),
            "-png", "-singlefile", pdf, stem]


def render_region(pdf, page, frame, out_path, dpi=DPI):
    """그림 자리를 dpi로 그려 out_path에. 못 그리면 상태 문자열."""
    from shutil import which
    if not which("pdftoppm"):
        return "RENDERER_UNAVAILABLE"
    stem = out_path[:-4] if out_path.endswith(".png") else out_path
    try:
        subprocess.run(render_command(pdf, page, frame, stem, dpi),
                       capture_output=True, check=True)
    except Exception:                                   # noqa: BLE001
        return "RENDER_FAILED"
    return "" if os.path.isfile(stem + ".png") else "RENDER_FAILED"


def roundtrip(raster, crop, shift_max=SHIFT_MAX + 3):
    """래스터를 크롭 크기로 줄여 크롭에 다시 올려 본다. (ncc, (dx, dy)).

    dx, dy는 줄인 래스터가 크롭에 가장 잘 맞는 어긋남입니다. 자리가 맞으면 0.
    """
    import cv2
    ch, cw = crop.shape[:2]
    small = cv2.resize(raster, (cw, ch), interpolation=cv2.INTER_AREA)
    m = shift_max
    if ch <= 2 * m + 8 or cw <= 2 * m + 8:
        return None, None
    inner = crop[m:ch - m, m:cw - m]
    score = cv2.matchTemplate(small, inner, cv2.TM_CCOEFF_NORMED)
    _, best, _, loc = cv2.minMaxLoc(score)
    dx, dy = loc[0] - m, loc[1] - m
    a = small.astype(np.float64); a -= a.mean()
    b = crop.astype(np.float64); b -= b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    ncc = float((a * b).sum() / den) if den else 0.0
    return ncc, (int(dx), int(dy))


def readable(rows):
    """그림별로, 옮길 패널 줄. NO_PANELS 그림과 읽을 값 없는 패널은 옮길 것이 없습니다."""
    by = {}
    for r in rows:
        if (r.get("Verdict") or "").strip() != "PANELS":
            continue
        if (r.get("Mark_Type") or "").strip().upper() == "NOT_DATA":
            continue
        by.setdefault(r["Draft_ID"], []).append(r)
    return by


def convert(run, decisions, drafts, pdfs, out_dir, renderer=render_region, dpi=DPI,
            deadline=None):
    """(rows, refusals, left). rows는 COLUMNS 순서의 dict, refusals는 (fid, code, detail),
    left는 `deadline`(time.time() 기준)이 지나 손대지 않은 그림들.

    셸이 두 분에 끊기는 곳에서 265장을 한 번에 그릴 수 없어서, 그림 사이에서 시계를
    보고 멈춥니다. 멈춘 자리는 `--resume`이 이어 갑니다. 그림 하나는 쪼개지 않습니다."""
    rows, refusals, left = [], [], []
    os.makedirs(out_dir, exist_ok=True)
    pages = {}
    for fid, panels in sorted(readable(decisions).items()):
        if deadline is not None and time.time() > deadline:
            left.append(fid); continue
        d = drafts.get(fid)
        if not d:
            refusals.append((fid, "DRAFT_MISSING", "figure_intake_draft.csv에 없는 그림")); continue
        src = d.get("Source_File") or ""
        pdf = pdfs.get(src) or ""
        if not pdf or not os.path.isfile(pdf):
            refusals.append((fid, "PDF_MISSING", src)); continue
        pdf_sha = sha256(pdf)
        if pdf_sha != (d.get("Source_File_SHA256") or ""):
            refusals.append((fid, "PDF_CHANGED", "%s의 지문이 초안과 다릅니다" % src)); continue
        crop_path = os.path.join(run, d.get("Figure_Crop") or "")
        if not (d.get("Figure_Crop") and os.path.isfile(crop_path)):
            refusals.append((fid, "CROP_MISSING", d.get("Figure_Crop") or "(빈칸)")); continue
        crop_sha = sha256(crop_path)
        want = {(p.get("Crop_SHA256") or "").strip() for p in panels}
        if want != {crop_sha}:
            refusals.append((fid, "CROP_CHANGED",
                             "판정이 본 크롭 %s, 지금 크롭 %s" % (",".join(w[:12] for w in want), crop_sha[:12])))
            continue
        page_path = d.get("Page_Raster") or ""
        if page_path and not os.path.isabs(page_path):
            page_path = os.path.join(run, page_path)
        if not page_path or not os.path.isfile(page_path):
            refusals.append((fid, "PAGE_RASTER_MISSING", d.get("Page_Raster") or "(빈칸)")); continue
        if page_path not in pages:
            pages[page_path] = (gray(page_path), sha256(page_path))
        page, page_sha = pages[page_path]
        try:
            page_pt = (float(d["Page_Width_Pt"]), float(d["Page_Height_Pt"]))
            bbox = tuple(float(v) for v in str(d["Figure_BBox"]).split(","))
            assert len(bbox) == 4
        except Exception:                               # noqa: BLE001
            refusals.append((fid, "DRAFT_GEOMETRY_BROKEN", "페이지 크기나 Figure_BBox를 읽을 수 없습니다")); continue
        crop = gray(crop_path)
        scale = page_scale(page.shape, page_pt)
        origin = find_crop(page, crop, bbox, scale)
        if origin is None:
            refusals.append((fid, "CROP_NOT_IN_PAGE", "상자 근처에 크롭과 픽셀이 같은 자리가 없습니다")); continue
        frame = raster_frame(origin, crop.shape, scale, dpi)
        raster = os.path.join(out_dir, "%s_%d.png" % (fid, dpi))
        status = renderer(pdf, int(d["Page"]), frame, raster, dpi)
        if status:
            refusals.append((fid, status, "pdftoppm p%s %s" % (d["Page"], frame))); continue
        big = gray(raster)
        if big.shape[1] != frame[2] or big.shape[0] != frame[3]:
            refusals.append((fid, "RENDER_SIZE_MISMATCH",
                             "부탁한 %dx%d, 나온 %dx%d" % (frame[2], frame[3], big.shape[1], big.shape[0])))
            continue
        ncc, shift = roundtrip(big, crop)
        if shift is None or max(abs(shift[0]), abs(shift[1])) > SHIFT_MAX:
            refusals.append((fid, "ROUNDTRIP_SHIFTED",
                             "줄여서 올려 보니 %s px 어긋납니다" % (shift,))); continue
        raster_sha = sha256(raster)
        for p in panels:
            box_px = tuple(int(round(float(p[k]))) for k in ("X0", "Y0", "X1", "Y1"))
            box_pt = crop_box_to_pt(box_px, origin, scale)
            reg = region_600(box_pt, frame, dpi)
            rows.append({
                "Draft_ID": fid, "Panel_Index": p["Panel_Index"],
                "Mark_Type": p["Mark_Type"], "Mark_Count": p.get("Mark_Count", ""),
                "Mark_Type_2": p.get("Mark_Type_2", ""), "Mark_Count_2": p.get("Mark_Count_2", ""),
                "Overlay": p.get("Overlay", ""),
                "Source_File": src, "Source_File_SHA256": pdf_sha, "Page": d["Page"],
                "Page_Raster_SHA256": page_sha, "Crop_SHA256": crop_sha,
                "Crop_Origin_Px": "%d,%d" % origin,
                "Page_Scale_Px_Per_Pt": "%.6f,%.6f" % scale,
                "Panel_Crop_Px": "%d,%d,%d,%d" % box_px,
                "Panel_Page_Pt": "%.3f,%.3f,%.3f,%.3f" % box_pt,
                "Raster_600": os.path.relpath(raster, run), "Raster_600_SHA256": raster_sha,
                "Raster_600_Origin_Px": "%d,%d" % (frame[0], frame[1]),
                "Region_600": "%d,%d,%d,%d" % reg,
                "Roundtrip_NCC": "%.4f" % ncc, "Roundtrip_Shift_Px": "%d,%d" % shift,
                "Verified_By": p.get("Verified_By", ""), "Verified_At": p.get("Verified_At", ""),
            })
    return rows, refusals, left


def load_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--pdfs", required=True, help="{Source_File: pdf 경로} JSON")
    ap.add_argument("--out", required=True, help="래스터와 CSV가 갈 폴더")
    ap.add_argument("--only", default="", help="쉼표로 나눈 Draft_ID - 이것만")
    ap.add_argument("--resume", action="store_true",
                    help="이미 옮긴 그림은 건너뛰고, 있던 줄에 이어 적는다")
    ap.add_argument("--budget", type=float, default=0,
                    help="이 초가 지나면 그림 사이에서 멈춘다 (0 = 끝까지)")
    a = ap.parse_args(argv)
    drafts = {r["Draft_ID"]: r for r in load_csv(os.path.join(a.run, "figure_intake_draft.csv"))}
    decisions = load_csv(a.decisions)
    if a.only:
        keep = set(a.only.split(","))
        decisions = [r for r in decisions if r["Draft_ID"] in keep]
    kept_rows = []
    out_csv = os.path.join(a.out, "panel_regions_600.csv")
    ref_csv = os.path.join(a.out, "panel_regions_600_refused.csv")
    if a.resume and os.path.isfile(out_csv):
        kept_rows = load_csv(out_csv)
        done = {r["Draft_ID"] for r in kept_rows}
        # 옮긴 그림만 건너뜁니다. 거절됐던 그림은 다시 해 봅니다 - 거절은 답이
        # 아니라 아직 못 옮겼다는 말이고, 거절 목록은 이번 실행이 다시 씁니다.
        decisions = [r for r in decisions if r["Draft_ID"] not in done]
    with io.open(a.pdfs, encoding="utf-8") as fh:
        pdfs = json.load(fh)
    # 상대 경로는 실행 폴더 기준입니다 - 세션마다 마운트 자리가 달라도 그대로 쓰게.
    pdfs = {k: (v if os.path.isabs(v) else os.path.join(a.run, v)) for k, v in pdfs.items()}
    deadline = time.time() + a.budget if a.budget else None
    rows, refusals, left = convert(a.run, decisions, drafts, pdfs, a.out, deadline=deadline)
    rows = kept_rows + rows
    rows.sort(key=lambda r: (r["Draft_ID"], int(r["Panel_Index"])))
    with io.open(out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader(); w.writerows(rows)
    with io.open(ref_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["Draft_ID", "Code", "Detail"]); w.writerows(refusals)
    figs = {r["Draft_ID"] for r in rows}
    print("옮김 그림 %d장 (패널 %d) · 거절 %d · 남음 %d" % (len(figs), len(rows), len(refusals), len(left)))
    for fid, code, detail in refusals:
        print("  거절 %s — %s: %s" % (fid, code, detail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
