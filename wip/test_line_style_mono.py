"""WORK IN PROGRESS suite for the solid-versus-dashed monochrome line reader.

    python3 wip/test_line_style_mono.py

This does NOT run in the release gate, and it does not currently pass. It is
here to record exactly what works and what does not, so the next attempt starts
from measurements rather than from scratch. See line_style_mono.py for what was
learned.

Many time-course figures carry two black curves and no markers at all. Marker
geometry cannot separate them because there is no marker; the legend says
"solid = Fluid, dashed = No Fluid" and that is the whole discriminant. This
reader measures the ink's duty cycle and matches it to the declared style.

The fixture draws the traps that make it hard: error bars whose stems cross both
curves, whisker caps that look like short horizontal strokes, and a crossing
where the two curves touch.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mark_readers as MR                                        # noqa: E402
import line_style_mono as LSM                                    # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


XS = [110, 160, 210, 260, 310, 360, 410, 460, 510, 560]
LABELS = ["T%d" % i for i in range(len(XS))]
CAL = MR.AxisCalibration.from_points([(70, 420), (120, 60)])
# The last position is a deliberate crossing: both curves land on the same
# value, their strokes merge, and no reader can say which is which. Every other
# position keeps them at least six units apart, which is a normal separation on
# a published time course.
TRUTH = {
    "SOLID":  [92.0, 96.0, 101.0, 107.0, 100.0, 98.0, 99.0, 97.0, 98.0, 99.0],
    "DASHED": [84.0, 87.0, 89.0, 92.0, 91.0, 90.0, 90.0, 91.0, 92.0, 99.0],
}
CROSSING = "T9"
SD = {"SOLID": 5.0, "DASHED": 4.0}
BOX = (90, 590, 50, 430)


def dashed_line(d, points, dash=9, gap=6, width=3):
    """A dashed polyline drawn dash-by-dash along its own arc length."""
    carry, on = 0.0, True
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = float(np.hypot(x1 - x0, y1 - y0))
        t = 0.0
        while t < length:
            step = min((dash if on else gap) - carry, length - t)
            if on:
                a = (x0 + (x1 - x0) * t / length, y0 + (y1 - y0) * t / length)
                b = (x0 + (x1 - x0) * (t + step) / length,
                     y0 + (y1 - y0) * (t + step) / length)
                d.line([a, b], fill="black", width=width)
            t += step
            carry += step
            if carry >= (dash if on else gap):
                carry, on = 0.0, not on


def fixture(path, with_errorbars=True):
    im = Image.new("RGB", (640, 480), "white")
    d = ImageDraw.Draw(im)
    for style, values in TRUTH.items():
        pts = [(x, CAL.value_to_pixel(v)) for x, v in zip(XS, values)]
        if style == "SOLID":
            d.line(pts, fill="black", width=3)
        else:
            dashed_line(d, pts)
        if not with_errorbars:
            continue
        sd_px = abs(CAL.value_to_pixel(SD[style]) - CAL.value_to_pixel(0))
        for x, y in pts:
            d.line((x, y - sd_px, x, y + sd_px), fill="black", width=2)
            d.line((x - 7, y - sd_px, x + 7, y - sd_px), fill="black", width=2)
            d.line((x - 7, y + sd_px, x + 7, y + sd_px), fill="black", width=2)
    im.save(path)
    return im


SPECS = [MR.SeriesSpec("S_FLUID", line_style="SOLID"),
         MR.SeriesSpec("S_NOFLUID", line_style="DASHED")]
STYLE_OF = {"S_FLUID": "SOLID", "S_NOFLUID": "DASHED"}

IMG = os.path.join(HERE, "mono_line_fixture.png")
image = fixture(IMG)


def read(img=None, **kw):
    return LSM.read_monochrome_line_panel(
        img or image, panel_box=BOX,
        x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
        series=SPECS, **kw)


print("two black curves, told apart by their own ink")
rows = read()
_readable = 2 * (len(XS) - 1)
check("both series are found at every separable position",
      len(rows) == _readable, "got %d of %d" % (len(rows), _readable))
check("and neither is claimed where the two curves cross",
      not any(r["x_label"] == CROSSING for r in rows),
      "%r" % sorted({r["x_label"] for r in rows}))
check("the crossing costs only its own cells - nothing shifted",
      {r["x_label"] for r in rows} == set(LABELS) - {CROSSING},
      "%r" % sorted({r["x_label"] for r in rows}))
check("each series carries the style it was declared with",
      all(r["line_style"] == STYLE_OF[r["series"]] for r in rows),
      "%r" % sorted({(r["series"], r["line_style"]) for r in rows}))
_err = max(abs(r["mean"] - TRUTH[STYLE_OF[r["series"]]][LABELS.index(r["x_label"])])
           for r in rows)
check("means recover within 1.5 units on a 50-unit axis", _err < 1.5,
      "max %.3f" % _err)
_duty = {r["line_style"]: r["line_duty"] for r in rows}
check("the solid curve measures near a full duty cycle",
      _duty["SOLID"] > 0.9, "%r" % _duty)
check("the dashed curve measures a clearly lower one",
      _duty["SOLID"] - _duty["DASHED"] > 0.2, "%r" % _duty)
_disp = [r["dispersion"] for r in rows if r["dispersion"] is not None]
check("error bars are recovered on both curves", len(_disp) == len(rows),
      "%d of %d" % (len(_disp), len(rows)))
if _disp:
    _derr = max(abs(r["dispersion"] - SD[STYLE_OF[r["series"]]])
                for r in rows if r["dispersion"] is not None)
    check("dispersions recover within 1.5 units", _derr < 1.5, "max %.3f" % _derr)
check("every recovered error bar has a confirmed stem",
      all(r["Errorbar_Stem_Confirmed"] == "TRUE"
          for r in rows if r["dispersion"] is not None))
check("no cell is claimed twice",
      len({(r["series"], r["x_label"]) for r in rows}) == len(rows))


print("style is measured, not assumed from drawing order")
# The same figure with the two curves' styles swapped must swap the values.
_swapped = Image.new("RGB", (640, 480), "white")
_d = ImageDraw.Draw(_swapped)
for _style, _values in TRUTH.items():
    _pts = [(x, CAL.value_to_pixel(v)) for x, v in zip(XS, _values)]
    if _style == "SOLID":
        dashed_line(_d, _pts)            # the upper curve is now the dashed one
    else:
        _d.line(_pts, fill="black", width=3)
_sw = read(_swapped)
_upper = TRUTH["SOLID"][0]
_got = {r["series"]: r["mean"] for r in _sw if r["x_label"] == "T0"}
check("the swapped figure still yields both series at T0", len(_got) == 2,
      "%r" % _got)
check("swapping the styles swaps which series gets which values",
      abs(_got.get("S_NOFLUID", 0) - _upper) < 1.5,
      "%r against an upper curve at %.1f" % (_got, _upper))


print("an unreadable style produces nothing, not a guess")
for _name, _specs, _frag in (
        ("a line series with no style declared",
         [MR.SeriesSpec("A"), MR.SeriesSpec("B", line_style="SOLID")], "line_style"),
        ("a style outside the vocabulary",
         [MR.SeriesSpec("A", line_style="WAVY"),
          MR.SeriesSpec("B", line_style="SOLID")], "line_style"),
        ("two series sharing one style",
         [MR.SeriesSpec("A", line_style="SOLID"),
          MR.SeriesSpec("B", line_style="SOLID")], "share a line style")):
    try:
        LSM.read_monochrome_line_panel(
            image, panel_box=BOX, x_positions=dict(zip(LABELS, XS)),
            y_calibration=CAL, series=_specs)
        _msg = "accepted"
    except ValueError as exc:
        _msg = str(exc)
    check("%s is refused" % _name, _frag in _msg, _msg)

_absent = LSM.read_monochrome_line_panel(
    image, panel_box=BOX, x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
    series=[MR.SeriesSpec("S_FLUID", line_style="SOLID"),
            MR.SeriesSpec("S_DOTS", line_style="DOTTED")])
check("a declared style the figure does not contain yields no cells for it",
      not any(r["series"] == "S_DOTS" for r in _absent),
      "%r" % sorted({r["series"] for r in _absent}))
check("and the style that IS there still reads",
      sum(r["series"] == "S_FLUID" for r in _absent) >= len(XS) - 1,
      "%d" % sum(r["series"] == "S_FLUID" for r in _absent))


print("the duty-cycle bands leave a gap rather than meeting")
check("nothing classifies between the solid and dashed bands",
      LSM.classify_line_style(0.83) is None
      and LSM.classify_line_style(0.31) is None,
      "%r / %r" % (LSM.classify_line_style(0.83), LSM.classify_line_style(0.31)))
check("a clean solid, dash and dot each land in exactly one band",
      (LSM.classify_line_style(0.99), LSM.classify_line_style(0.60),
       LSM.classify_line_style(0.18)) == ("SOLID", "DASHED", "DOTTED"))

check("this reader is deliberately NOT in the released dispatcher",
      "LINE_STYLE_MONO" not in MR.MARK_TYPES, "%r" % (MR.MARK_TYPES,))
check("and the adapter turns its rows into grid cells",
      len(MR.to_value_records(rows, "CONTINUOUS", "U1", x_factor="TIMEPOINT",
                              series_factor="ARM")) == len(rows))
check("and not in the batch layer's vocabulary either",
      "LINE_STYLE_MONO" not in __import__("batch_manifests").BATCH_MARK_TYPES)

if os.path.exists(IMG):
    os.remove(IMG)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
