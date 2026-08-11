"""Scenario suite for the solid-versus-dashed monochrome line reader.

    python3 test_line_style_mono.py

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
#
# The DASHED curve sits about thirteen units below the solid one, which with
# these dispersions leaves clear white between the two error bars - except at
# T5, where it is drawn deliberately close so the two bars touch and merge into
# one column of ink. That is the second trap: nothing local to that column says
# which cap belongs to which mark, and the reader has to say so rather than
# take the nearest stroke. It used to take the nearest stroke, and reported a
# dispersion 1.99 units short.
TRUTH = {
    "SOLID":  [92.0, 96.0, 101.0, 107.0, 100.0, 98.0, 99.0, 97.0, 98.0, 99.0],
    "DASHED": [78.0, 81.0, 84.0, 87.0, 86.0, 91.0, 85.0, 84.0, 85.0, 99.0],
}
CROSSING = "T9"
MERGED_BARS = "T5"
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
# REVERT NOTE. This used to assert `_duty["SOLID"] - _duty["DASHED"] > 0.2`,
# and it was asserting the wrong quantity. The duty a dash pattern measures
# depends on where in its phase the fitting window opens and on how much of the
# window is off the end of the data: on this very fixture the dashed curve
# measures anywhere from 0.605 to 0.81, straight through the bottom of the
# SOLID band, so the separation is not reliably 0.2 and the reader does not use
# it. What separates them is the GAP - a solid stroke never skips three columns
# in a row, a dash pattern skips one every period however the window falls.
_gap = {r["line_style"]: [x["line_gap"] for x in rows
                          if x["line_style"] == r["line_style"]]
        for r in rows}
check("no solid reading ever skips more than two columns in a row",
      max(_gap["SOLID"]) <= LSM._SOLID_MAX_GAP, "%r" % sorted(set(_gap["SOLID"])))
check("every dashed reading skips more than that",
      min(_gap["DASHED"]) > LSM._SOLID_MAX_GAP,
      "%r" % sorted(set(_gap["DASHED"])))
_disp = {(r["series"], r["x_label"]): r["dispersion"] for r in rows}
_separate = [k for k in _disp if k[1] != MERGED_BARS]
check("error bars are recovered wherever the two bars are separate ink",
      all(_disp[k] is not None for k in _separate),
      "%r" % sorted(k for k in _separate if _disp[k] is None))
_derr = max(abs(_disp[k] - SD[STYLE_OF[k[0]]])
            for k in _separate if _disp[k] is not None)
check("and recover within 1.5 units", _derr < 1.5, "max %.3f" % _derr)
# The load-bearing half. Taking the nearest wide stroke gave a number here too,
# and it was wrong by more than the tolerance above - which is worse than
# silence, because it is defensible-looking.
_merged = [k for k in _disp if k[1] == MERGED_BARS]
check("where the two bars merge into one column of ink, no dispersion at all",
      len(_merged) == 2 and all(_disp[k] is None for k in _merged),
      "%r" % {k: _disp[k] for k in _merged})
check("but the means at that position are still read",
      all(r["mean"] is not None for r in rows if r["x_label"] == MERGED_BARS),
      "%d rows" % sum(1 for r in rows if r["x_label"] == MERGED_BARS))
check("a dispersion is reported only with the stem that carries it",
      all((r["Errorbar_Stem_Confirmed"] == "TRUE")
          == (r["dispersion"] is not None) for r in rows))
check("no cell is claimed twice",
      len({(r["series"], r["x_label"]) for r in rows}) == len(rows))


print("an error bar is the connected column of ink through the mark")
# At the merged position the two bars are within the default search radius of
# each other AND of a much larger one, so what refuses there is the rule and
# not the reach: widen the search until the radius cannot be the reason, and
# the answer has to be the same.
_wide = read(search_radius=140)
_wd = {(r["series"], r["x_label"]): r["dispersion"] for r in _wide}
check("a reach long enough to walk into the neighbour's bar changes nothing",
      all(_wd.get(k) is None for k in _wd if k[1] == MERGED_BARS),
      "%r" % {k: v for k, v in _wd.items() if k[1] == MERGED_BARS})
check("and the separate positions still recover with that reach",
      all(_wd[k] is not None for k in _wd if k[1] != MERGED_BARS),
      "%r" % sorted(k for k in _wd if k[1] != MERGED_BARS and _wd[k] is None))

# A curve with no error bar at all. The run through the mark is the stroke
# itself, and on a gently sloping curve the stroke's own top row is a short
# horizontal run that ends inside the window - so "it has caps" is not enough
# to refuse it, and the reader also requires the run to reach further from the
# mark than the stroke is thick.
_bare = fixture(os.path.join(HERE, "mono_line_bare.png"), with_errorbars=False)
_br = read(_bare)
check("a figure with no error bars yields means",
      len(_br) >= 2 * (len(XS) - 2), "%d rows" % len(_br))
check("and not one dispersion",
      all(r["dispersion"] is None for r in _br),
      "%r" % [(r["series"], r["x_label"], r["dispersion"]) for r in _br
              if r["dispersion"] is not None])

# Two faults a published figure really has: an error bar drawn as a bare stem
# with no caps, and a vertical time marker standing the full height of the
# panel through one position.
_faults = Image.new("RGB", (640, 480), "white")
_fd = ImageDraw.Draw(_faults)
_NO_CAPS, _RULE = "T2", "T3"
for _style, _values in TRUTH.items():
    _pts = [(x, CAL.value_to_pixel(v)) for x, v in zip(XS, _values)]
    if _style == "SOLID":
        _fd.line(_pts, fill="black", width=3)
    else:
        dashed_line(_fd, _pts)
    _sd_px = abs(CAL.value_to_pixel(SD[_style]) - CAL.value_to_pixel(0))
    for _label, (_x, _y) in zip(LABELS, _pts):
        _fd.line((_x, _y - _sd_px, _x, _y + _sd_px), fill="black", width=2)
        if _label == _NO_CAPS:
            continue                     # a bare stem: no caps drawn
        for _end in (-_sd_px, _sd_px):
            _fd.line((_x - 7, _y + _end, _x + 7, _y + _end), fill="black", width=2)
_fd.line((XS[LABELS.index(_RULE)], BOX[2], XS[LABELS.index(_RULE)], BOX[3]),
         fill="black", width=2)
_fr = {(r["series"], r["x_label"]): r["dispersion"] for r in read(_faults)}
check("a bar with no caps is not a dispersion",
      all(_fr.get((s, _NO_CAPS), "missing") in (None, "missing")
          for s in STYLE_OF),
      "%r" % {k: v for k, v in _fr.items() if k[1] == _NO_CAPS})
check("and neither is a column of ink that never ends",
      all(_fr.get((s, _RULE), "missing") in (None, "missing") for s in STYLE_OF),
      "%r" % {k: v for k, v in _fr.items() if k[1] == _RULE})
check("while the untouched positions still recover theirs",
      any(v is not None for k, v in _fr.items()
          if k[1] not in (_NO_CAPS, _RULE)),
      "%r" % _fr)
# `search_radius` is the author saying how big the figure they measured is, the
# way `whisker_search_px` does for LINE_MONO - not a wall the reader hides
# behind. One curve, so nothing else can be what refuses: a bar drawn four
# times the declared reach is not read at the declared reach, and IS read when
# the declaration matches the figure.
_tall = Image.new("RGB", (640, 480), "white")
_ld = ImageDraw.Draw(_tall)
_LONG_BAR = "T6"
_pts = [(x, CAL.value_to_pixel(v)) for x, v in zip(XS, TRUTH["SOLID"])]
_ld.line(_pts, fill="black", width=3)
for _label, (_x, _y) in zip(LABELS, _pts):
    _px = abs(CAL.value_to_pixel(20.0 if _label == _LONG_BAR else 5.0)
              - CAL.value_to_pixel(0))
    _ld.line((_x, _y - _px, _x, _y + _px), fill="black", width=2)
    for _end in (-_px, _px):
        _ld.line((_x - 7, _y + _end, _x + 7, _y + _end), fill="black", width=2)
_ONE = [MR.SeriesSpec("S_ONLY", line_style="SOLID")]
_near = {r["x_label"]: r["dispersion"] for r in LSM.read_monochrome_line_panel(
    _tall, panel_box=BOX, x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
    series=_ONE, search_radius=60)}
_far = {r["x_label"]: r["dispersion"] for r in LSM.read_monochrome_line_panel(
    _tall, panel_box=BOX, x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
    series=_ONE, search_radius=200)}
check("a bar longer than the declared reach is not read",
      _near.get(_LONG_BAR) is None, "%r" % _near.get(_LONG_BAR))
check("and the ordinary bars beside it are",
      all(v is not None for k, v in _near.items() if k != _LONG_BAR),
      "%r" % _near)
check("declare the reach the figure needs and the same bar reads",
      _far.get(_LONG_BAR) is not None
      and abs(_far[_LONG_BAR] - 20.0) < 1.5, "%r" % _far.get(_LONG_BAR))

for _tmp in (os.path.join(HERE, "mono_line_bare.png"),):
    if os.path.exists(_tmp):
        os.remove(_tmp)


print("two curves of one style at one x are two curves nobody can name")
# A third solid curve. The panel declares SOLID and DASHED, so the solid style
# is found twice at every position and names neither - and the dashed series,
# which is still unambiguous, must not pay for it.
_third = Image.new("RGB", (640, 480), "white")
_td = ImageDraw.Draw(_third)
for _style, _values in TRUTH.items():
    _pts = [(x, CAL.value_to_pixel(v)) for x, v in zip(XS, _values)]
    if _style == "SOLID":
        _td.line(_pts, fill="black", width=3)
    else:
        dashed_line(_td, _pts)
_td.line([(x, CAL.value_to_pixel(v - 8.0)) for x, v in zip(XS, TRUTH["DASHED"])],
         fill="black", width=3)
_tr = read(_third)
check("neither solid curve is named",
      not any(r["series"] == "S_FLUID" for r in _tr),
      "%r" % sorted({(r["series"], r["x_label"]) for r in _tr
                     if r["series"] == "S_FLUID"}))
check("and the dashed series is read anyway",
      sum(r["series"] == "S_NOFLUID" for r in _tr) >= len(XS) - 3,
      "%d" % sum(r["series"] == "S_NOFLUID" for r in _tr))


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


print("a window with nothing observable in it has no duty cycle")
# Not a hypothetical: publication 397's WOMEN mean-arterial-pressure panel has
# a window where every column carries a gridline, a stem or a cap. The reader
# divided by zero, `run_batch` reported an InternalReaderError, and the whole
# eighteen-panel batch aborted on one panel's blind spot.
_all_ink = np.ones((60, 80), dtype=bool)
check("a fit whose every column is furniture returns nothing",
      LSM._line_fit_window(_all_ink, 40, 30, blind=_all_ink)
      == (None, None, None, None),
      "%r" % (LSM._line_fit_window(_all_ink, 40, 30, blind=_all_ink),))
check("and the same window with nothing blinding it does report one",
      LSM._line_fit_window(_all_ink, 40, 30)[0] == 1.0,
      "%r" % (LSM._line_fit_window(_all_ink, 40, 30),))


print("the duty-cycle bands leave a gap rather than meeting")
check("nothing classifies between the solid and dashed bands",
      LSM.classify_line_style(0.83) is None
      and LSM.classify_line_style(0.31) is None,
      "%r / %r" % (LSM.classify_line_style(0.83), LSM.classify_line_style(0.31)))
check("a clean solid, dash and dot each land in exactly one band",
      (LSM.classify_line_style(0.99), LSM.classify_line_style(0.60),
       LSM.classify_line_style(0.18)) == ("SOLID", "DASHED", "DOTTED"))
# With a gap the answer comes from the gap, EXCEPT for dotted: a dot pattern
# has a gap like a dash pattern and is told from it by how little ink there is.
check("a traced curve with a gap and almost no ink is dotted, not dashed",
      LSM.classify_line_style(0.18, longest_gap=6) == "DOTTED",
      "%r" % LSM.classify_line_style(0.18, longest_gap=6))
check("and one with a gap and plenty of ink is dashed",
      LSM.classify_line_style(0.60, longest_gap=6) == "DASHED")

print("the reader is reachable the same way every other reader is")
_BM = __import__("batch_manifests")
check("the dispatcher routes LINE_MONO_STYLE to it",
      MR.read_panel("LINE_MONO_STYLE", image=image, panel_box=BOX,
                    x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
                    series=SPECS) == rows)
check("it is in the reader vocabulary", "LINE_MONO_STYLE" in MR.MARK_TYPES)
check("and in the batch layer's", "LINE_MONO_STYLE" in _BM.BATCH_MARK_TYPES)
check("and no longer listed as unreleased",
      "LINE_MONO_STYLE" not in _BM.UNRELEASED_MARK_TYPES,
      "%r" % sorted(_BM.UNRELEASED_MARK_TYPES))
check("it locates marks at declared x, so it needs a position manifest",
      "LINE_MONO_STYLE" in _BM.POSITIONAL_MARK_TYPES)
check("and it separates series by drawn form, not by colour",
      "LINE_MONO_STYLE" in _BM.MONO_MARK_TYPES
      and "LINE_MONO_STYLE" not in _BM.COLOUR_MARK_TYPES)
check("the adapter turns its rows into grid cells",
      len(MR.to_value_records(rows, "CONTINUOUS", "U1", x_factor="TIMEPOINT",
                              series_factor="ARM")) == len(rows))

if os.path.exists(IMG):
    os.remove(IMG)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
