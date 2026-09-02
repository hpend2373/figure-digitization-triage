# -*- coding: utf-8 -*-
"""Scenarios for finding a figure from what the PDF draws.

    python3 test_figure_regions.py      # exit 0 = all scenarios pass

Every scenario here is one of the four defect families the run2 census found,
written as geometry so it can be checked without a publisher's PDF, plus an
end-to-end pass over a PDF this file builds itself.
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figure_regions as FR                                      # noqa: E402

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % detail))
    if not ok:
        FAIL.append(name)


PAGE = (612.0, 792.0)


def body_text(rows=12, left=True, right=True):
    """Enough body lines that the column detector has something to read."""
    out = []
    for i in range(rows):
        y = 700 - i * 14
        if left:
            out.append((56.0, y, 290.0, y + 10))
        if right:
            out.append((322.0, y, 556.0, y + 10))
    return out


print("한 페이지에서 그림이 어디인지")

# ------------------------------------------------ 떨어진 패널은 하나의 그림이다
_panels = [(50, 600, 200, 700), (210, 600, 360, 700), (50, 480, 360, 590)]
_one = FR.cluster(_panels, PAGE, [])
check("떨어져 그려진 패널 셋이 후보 하나가 된다", len(_one) == 1, _one)
check("그 후보는 세 패널을 모두 덮는다",
      _one and _one[0] == (50, 480, 360, 700), _one)
_far = FR.cluster([(50, 600, 200, 700), (50, 100, 200, 200)], PAGE, [])
check("멀리 떨어진 둘은 합쳐지지 않는다", len(_far) == 2, _far)

# ------------------------------------------------------------- 페이지 장식 제거
_rule = [(40, 60, 572, 63)] + _panels
check("아래를 가로지르는 괘선은 후보가 아니다",
      FR.cluster(_rule, PAGE, []) == _one, FR.cluster(_rule, PAGE, []))
check("괘선 하나뿐이면 후보가 없다", FR.cluster([(40, 60, 572, 63)], PAGE, []) == [])
check("점 하나 크기의 조각도 후보가 아니다",
      FR.cluster([(300, 300, 306, 306)], PAGE, []) == [])
# 괘선이 그림에서 멀면 최소 크기 검사만으로도 걸러집니다. 장식 제거가 실제로
# 하는 일은 그림에 '붙어 있는' 괘선을 미리 빼는 것입니다 - 빼지 않으면 그
# 괘선이 뭉치기에 끌려 들어가 후보를 페이지 폭으로 늘려 놓습니다.
_rule_touching = [(56, 500, 288, 640), (40, 493, 572, 494.5)]
_kept = FR.cluster(_rule_touching, PAGE, _txt if False else [])
check("그림에 붙은 괘선이 후보를 페이지 폭으로 늘리지 않는다",
      len(_kept) == 1 and _kept[0][2] - _kept[0][0] < 300, _kept)

# 최소 크기는 통과하지만 넓이가 그림이라기엔 작은 표식 - 로고나 기호입니다.
check("작은 표식은 후보가 아니다",
      FR.cluster([(300, 300, 332, 340)], PAGE, []) == [],
      FR.cluster([(300, 300, 332, 340)], PAGE, []))

# 넓이만 보면 통과하는 납작한 띠 - 러닝헤드 주변이 이 모양이고, run2에서
# 실제로 그 띠가 아래 그림 대신 뽑혔습니다.
check("납작한 띠는 넓이가 충분해도 후보가 아니다",
      FR.cluster([(56, 740, 556, 752)], PAGE, []) == [],
      FR.cluster([(56, 740, 556, 752)], PAGE, []))

# ------------------------------------------------------------ 거터 너머는 남이다
# 거터 폭보다 가깝게 마주 본 둘. 거리만으로는 갈라지지 않으므로, 갈라진다면
# 그것은 거터를 봤기 때문입니다 - 멀찍이 떨어뜨려 놓고 통과하는 시나리오는
# 거터 규칙을 지우고도 통과합니다.
_two_col = [(56, 500, 298, 640), (306, 500, 556, 640)]
_txt = body_text()
_band = FR.gutter(_txt, PAGE)
check("본문에서 거터를 찾는다", _band is not None and _band[0] < _band[1], _band)
check("거터 양쪽 그림 둘은 후보 둘로 남는다",
      len(FR.cluster(_two_col, PAGE, _txt)) == 2,
      FR.cluster(_two_col, PAGE, _txt))
check("거터가 없는(한 단) 페이지에서는 나누지 않는다",
      len(FR.cluster(_two_col, PAGE, body_text(rows=12, right=False))) == 1,
      FR.cluster(_two_col, PAGE, body_text(rows=12, right=False)))
_wide = [(56, 500, 556, 640), (56, 470, 288, 495)]
check("거터를 스스로 가로지르는 그림은 하나로 남는다",
      len(FR.cluster(_wide, PAGE, _txt)) == 1, FR.cluster(_wide, PAGE, _txt))

# --------------------------------------- 빈칸은 잇고, 글이 있으면 끊는다
# 한 그림의 두 줄은 GAP보다 훨씬 벌어져 있는 일이 흔합니다. 사람이 그것을
# 한 그림으로 보는 근거는 간격의 크기가 아니라 그 사이에 아무것도 씌어 있지
# 않다는 것이고, 캡션이 끼어 있으면 두 그림입니다.
_rows = [(56, 560, 288, 660), (56, 420, 288, 520)]        # 40pt 벌어진 두 줄
check("사이에 글이 없으면 벌어진 두 줄은 한 그림이다",
      len(FR.cluster(_rows, PAGE, [])) == 1, FR.cluster(_rows, PAGE, []))
_caption_between = [(56, 530, 288, 545)]                   # 그 사이의 캡션 한 줄
check("사이에 캡션이 있으면 두 그림으로 남는다",
      len(FR.cluster(_rows, PAGE, _caption_between)) == 2,
      FR.cluster(_rows, PAGE, _caption_between))
_tick_between = [(56, 530, 96, 540)]                       # 눈금 숫자 정도의 조각
check("눈금 숫자만 한 글자는 두 줄을 끊지 못한다",
      len(FR.cluster(_rows, PAGE, _tick_between)) == 1,
      FR.cluster(_rows, PAGE, _tick_between))
_far_rows = [(56, 600, 288, 700), (56, 200, 288, 300)]     # 300pt 벌어짐
check("아주 멀면 빈칸이어도 잇지 않는다",
      len(FR.cluster(_far_rows, PAGE, [])) == 2, FR.cluster(_far_rows, PAGE, []))
_across = [(56, 500, 240, 640), (360, 500, 556, 640)]      # 거터를 사이에 둔 둘
check("빈칸 잇기도 거터는 넘지 않는다",
      len(FR.cluster(_across, PAGE, _txt)) == 2,
      FR.cluster(_across, PAGE, _txt))

# ------------------------------------------------------------------ 캡션 배정
_cap_below = (50, 440, 360, 455)
check("아래 캡션이 위 그림에 배정된다",
      FR.assign(_one, [_cap_below]) == [(0, "OK")])
_cap_above = (50, 710, 360, 725)
check("위에 있는 캡션도 배정된다 (책·가로 판형)",
      FR.assign(_one, [_cap_above])[0][1] == "OK")
_side_fig = FR.cluster([(300, 500, 540, 640)], PAGE, [])
check("옆에 붙은 캡션도 배정된다",
      FR.assign(_side_fig, [(60, 540, 280, 560)])[0][1] == "OK",
      FR.assign(_side_fig, [(60, 540, 280, 560)]))
check("아무 데도 닿지 않는 캡션은 NO_CANDIDATE",
      FR.assign(_one, [(50, 80, 360, 95)]) == [(None, "NO_CANDIDATE")])

# ---------------------------------------------------- 비슷하면 고르지 않는다
_twin = [(56, 500, 288, 640), (322, 500, 556, 640)]
#: 두 그림에 폭이 걸친 캡션 하나 - 어느 쪽 그림의 캡션인지 페이지가 말해 주지
#: 않는 배치입니다.
_mid_cap = (56, 460, 556, 475)
_amb = FR.assign(FR.cluster(_twin, PAGE, _txt), [_mid_cap])
check("두 후보가 비슷하게 그럴듯하면 고르지 않는다", _amb[0][1] == "AMBIGUOUS",
      _amb)
check("차이가 분명하면 고른다",
      FR.assign(FR.cluster(_twin, PAGE, _txt), [(56, 460, 288, 475)])
      == [(0, "OK")])

# ------------------------------------------------- 페이지의 캡션을 함께 배정한다
_pair = FR.cluster(_twin, PAGE, _txt)
_both = FR.assign(_pair, [(56, 460, 288, 475), (322, 460, 556, 475)])
check("캡션 둘이 각각 자기 그림을 가져간다",
      sorted(j for j, _ in _both) == [0, 1], _both)
check("한 그림을 두 캡션이 가져가지 않는다",
      len({j for j, c in _both if j is not None}) == 2)
_greedy = FR.assign(_pair[:1], [(56, 460, 288, 475), (60, 455, 285, 470)])
check("후보가 하나뿐이면 더 잘 맞는 캡션이 가져가고 나머지는 TAKEN",
      sorted(c for _, c in _greedy) == ["OK", "TAKEN"], _greedy)

# ------------------------------------------------------------ 실제 PDF 한 장
TMP = tempfile.mkdtemp(prefix="fdt-regions-")
PDF = os.path.join(TMP, "fixture.pdf")
try:
    from reportlab.pdfgen import canvas as _canvas
    c = _canvas.Canvas(PDF, pagesize=PAGE)
    for x0, y0, x1, y1 in _panels:      # 패널 셋을 선으로 그린다
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)
        c.line(x0 + 4, y0 + 4, x1 - 4, y1 - 4)
    c.setFont("Helvetica", 9)
    c.drawString(50, 445, "Fig. 1  three panels drawn as separate objects")
    for i in range(14):                 # 본문 두 단
        c.drawString(56, 400 - i * 12, "body text on the left column " * 2)
        c.drawString(322, 400 - i * 12, "body text on the right column " * 2)
    c.showPage()
    c.save()
    _g, _t, _size = FR.page_objects(PDF, 1)
    check("PDF에서 그림 객체를 읽는다", len(_g) >= len(_panels), len(_g))
    check("페이지 크기를 그대로 읽는다",
          abs(_size[0] - PAGE[0]) < 1 and abs(_size[1] - PAGE[1]) < 1, _size)
    _cap = [t for t in _t if t[1] < 460 and t[3] > 440]
    check("캡션 줄을 텍스트에서 찾는다", len(_cap) == 1, _cap)
    _r = FR.regions(PDF, 1, _cap)
    check("PDF 한 장에서 캡션이 세 패널 전체에 배정된다",
          _r and _r[0][1] == "OK", _r)
    _box = _r[0][0]
    check("그 영역이 세 패널을 모두 담는다",
          _box and _box[0] <= 51 and _box[1] <= 481
          and _box[2] >= 359 and _box[3] >= 699, _box)
except ImportError:
    print("  SKIP reportlab이 없어 PDF 한 장 시나리오는 건너뜁니다")
finally:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
