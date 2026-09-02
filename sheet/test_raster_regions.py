# -*- coding: utf-8 -*-
"""Scenarios for the raster proposer - figures from ink alone.

    python3 test_raster_regions.py
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import raster_regions as RR                                      # noqa: E402

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


PAGE_PT = (612.0, 792.0)
PX = (850, 1100)                       # 100 dpi-ish, 1.389 px/pt
SX, SY = PX[0] / PAGE_PT[0], PX[1] / PAGE_PT[1]


def page_with(panels, text_rows=(), thick_text=False):
    """A page raster (grey array) and the PDF-style text boxes (y up) for it."""
    im = Image.new("L", PX, 255)
    d = ImageDraw.Draw(im)
    for x0, y0, x1, y1 in panels:                  # points, y DOWN (raster)
        d.rectangle([x0 * SX, y0 * SY, x1 * SX, y1 * SY], outline=0, width=3)
        d.line([x0 * SX + 6, y1 * SY - 6, x1 * SX - 6, y0 * SY + 6], fill=0, width=2)
    texts = []
    for x0, y, x1 in text_rows:                    # a prose line: x0..x1 at y (pt, y down)
        # glyph bodies plus ascenders/descenders that poke out of the box
        d.rectangle([x0 * SX, y * SY, x1 * SX, (y + 8) * SY], fill=60)
        if thick_text:
            d.rectangle([x0 * SX, (y - 3) * SY, x1 * SX, (y + 11) * SY], fill=90)
        texts.append((x0, PAGE_PT[1] - (y + 8), x1, PAGE_PT[1] - y))   # y up
    return np.asarray(im), texts


def to_down(box):
    x0, y0, x1, y1 = box
    return (x0, PAGE_PT[1] - y1, x1, PAGE_PT[1] - y0)


print("잉크만 보고 그림이 어디인지")

# ------------------------------------------------------------ 한 그림, 세 패널
_panels = [(60, 100, 200, 220), (210, 100, 350, 220), (60, 230, 350, 330)]
_pg, _tx = page_with(_panels)
_c = RR.candidates(_pg, _tx, PAGE_PT)
check("떨어져 그려진 패널 셋이 후보 하나가 된다", len(_c) == 1, _c)
_b = to_down(_c[0]) if _c else None
check("그 후보가 세 패널을 모두 담는다",
      _b and _b[0] <= 61 and _b[1] <= 101 and _b[2] >= 349 and _b[3] >= 329, _b)
check("후보는 PDF 규약(y 위로)으로 돌려준다 - 위 기준 값과 다르다",
      _c and abs(_c[0][1] - (PAGE_PT[1] - 330)) < 12, _c)

# ------------------------------------------------- 본문은 지워지고 그림만 남는다
_rows = [(60, 400 + i * 14, 500) for i in range(12)]
_pg2, _tx2 = page_with(_panels, _rows, thick_text=True)
_c2 = RR.candidates(_pg2, _tx2, PAGE_PT)
check("본문 열두 줄이 있어도 후보는 그림 하나뿐이다", len(_c2) == 1, _c2)
check("글줄 상자 밖으로 삐져나온 잉크(어센더·디센더)도 남지 않는다",
      len(_c2) == 1 and to_down(_c2[0])[3] < 340, _c2 and to_down(_c2[0]))
_mask = RR.ink_mask(_pg2.copy())
_before = int(_mask.sum())
RR.paint_out_prose(_mask, [(x0 * SX, (PAGE_PT[1] - y1) * SY, x1 * SX,
                            (PAGE_PT[1] - y0) * SY) for x0, y0, x1, y1 in _tx2],
                   PX[0])
check("지운 뒤 잉크가 실제로 줄어든다", int(_mask.sum()) < _before * 0.6,
      (_before, int(_mask.sum())))

# ------------------------------------------------ 짧은 글자는 지우지 않는다
_short = [(60, 400, 120)]                          # 60pt: 눈금 숫자 정도
_pg3, _tx3 = page_with([], _short)
check("짧은 글자는 prose가 아니므로 지우지 않는다 - 지우면 그림 안 눈금도 사라진다",
      RR.paint_out_prose(RR.ink_mask(_pg3.copy()),
                         [(x0 * SX, (PAGE_PT[1] - y1) * SY, x1 * SX,
                           (PAGE_PT[1] - y0) * SY) for x0, y0, x1, y1 in _tx3],
                         PX[0]).sum() > 0)
check("하지만 그것만으로는 후보가 되지 못한다 (너무 작다)",
      RR.candidates(_pg3, _tx3, PAGE_PT) == [])

# ------------------------------------------------------- 러닝헤드와 폴리오
_pg4, _tx4 = page_with([(60, 8, 500, 20)])           # 맨 위 띠
check("페이지 위아래 띠의 잉크는 후보가 아니다", RR.candidates(_pg4, _tx4, PAGE_PT) == [])

# ----------------------------------------------------------- 두 그림, 캡션 사이
_two = [(60, 100, 350, 220), (60, 330, 350, 450)]
_cap = [(60, 235, 350)]
_pg5, _tx5 = page_with(_two, _cap)
check("사이에 캡션이 있으면 두 그림으로 남는다",
      len(RR.candidates(_pg5, _tx5, PAGE_PT)) == 2, RR.candidates(_pg5, _tx5, PAGE_PT))
_pg6, _tx6 = page_with(_two)
check("사이에 글이 없으면 한 그림으로 잇는다",
      len(RR.candidates(_pg6, _tx6, PAGE_PT)) == 1, RR.candidates(_pg6, _tx6, PAGE_PT))

# --------------------------------------------------------------- 부품들
_g = np.zeros((10, 10), dtype=bool)
_g[1:3, 1:3] = True
_g[6:9, 5:9] = True
check("연결 성분이 둘이면 상자 둘", sorted(RR.components(_g)) == [(1, 1, 3, 3), (5, 6, 9, 9)],
      RR.components(_g))
_g2 = np.zeros((6, 6), dtype=bool)
_g2[0, :] = True
_g2[:, 5] = True                                     # ㄱ 모양: 하나로 이어져야 한다
check("모서리에서 만나는 두 획은 한 성분이다", len(RR.components(_g2)) == 1)
_d = RR.dilate(np.pad(np.ones((1, 1), dtype=bool), 3), r=1)
check("팽창은 반지름만큼 넓힌다", int(_d.sum()) == 9)
_ds = RR.downsample(np.ones((13, 7), dtype=bool), cell=6)
check("내림 표본은 가장자리 셀을 버리지 않는다", _ds.shape == (3, 2) and _ds.all())

# ------------------------------------------------------------- 캡션 배정
_r = RR.regions(_pg2, _tx2, PAGE_PT, [(60, PAGE_PT[1] - 350, 350, PAGE_PT[1] - 340)])
check("아래 캡션이 그림에 배정된다", _r and _r[0][1] == "OK", _r)

print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
