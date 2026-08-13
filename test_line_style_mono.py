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
import provenance as PROV                                        # noqa: E402

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
      == (None,) * 11,
      "%r" % (LSM._line_fit_window(_all_ink, 40, 30, blind=_all_ink),))
check("and the same window with nothing blinding it does report one",
      LSM._line_fit_window(_all_ink, 40, 30)[0] == 1.0,
      "%r" % (LSM._line_fit_window(_all_ink, 40, 30),))
# The window also has to say HOW MUCH of itself it could not see, because a
# duty measured through furniture is not the same claim as one measured
# through air, and nothing downstream can tell them apart without this.
check("and it reports how blinded it was, both ways",
      LSM._line_fit_window(_all_ink, 40, 30)[4] == 0.0,
      "%r" % (LSM._line_fit_window(_all_ink, 40, 30)[4],))


print("the panel box says where the panel is; the positions say where the data is")
# A REAL DEFECT, FOUND ON 397 FIGURE 1 AND REPRODUCED HERE. At the first
# plotted point half the fit window hangs over the axis, and a single stray
# pixel of axis furniture inside the panel box was collected as a sample of the
# curve: it stretched the fitted span sixteen columns to the left, dragged the
# quadratic, and the dashed curve came back 1.7 units off - inside the forward
# test's tolerance and wrong. Four pixels of ink, and BOTH cells at that
# position were lost.
_speck_y = CAL.value_to_pixel(TRUTH["SOLID"][0])


def with_speck(x):
    marked = image.copy()
    ImageDraw.Draw(marked).rectangle([x, _speck_y + 5, x + 3, _speck_y + 7],
                                     fill="black")
    return marked


_clean = {(r["series"], r["x_label"]): r["mean"] for r in read()}
_outside = {(r["series"], r["x_label"]): r["mean"]
            for r in read(with_speck(XS[0] - 18))}
check("a speck between the axis and the first plotted point changes nothing",
      _outside == _clean,
      "%d cells against %d" % (len(_outside), len(_clean)))
# The other half of the same statement, and the reason this is a span rather
# than a blanket: ink one window inside the first position is DATA. The reader
# does not get to decide that a stroke near the end of the curve is furniture.
_inside = {(r["series"], r["x_label"]): r["mean"]
           for r in read(with_speck(XS[0] - 8))}
check("and ink inside that span is still the panel's ink",
      ("S_FLUID", "T0") not in _inside,
      "%r" % sorted(k for k in _inside if k[1] == "T0"))


print("a window that could not see itself does not get to call a curve solid")
# BLINDING HIDES GAPS AND CANNOT INVENT THEM. Every column carrying furniture
# is dropped from the duty accounting - it has to be, or the stems alone would
# give every solid curve on 397 a gap of 3 - so a dashed curve whose gaps all
# fall on a gridline measures duty 1.000, gap 0. That is what happens at 0:30
# on 397 Figure 1, where the dashed curve runs along the 90 mmHg rule: 68% of
# the window blinded, a perfect SOLID reading, two SOLID candidates at one x,
# and both cells thrown away.
_solid_reading = dict(duty=1.0, gap=0)
check("a solid reading taken through a mostly blinded window is withheld",
      LSM._local_style(dict(_solid_reading, blindness=0.68)) is None,
      "%r" % LSM._local_style(dict(_solid_reading, blindness=0.68)))
check("the same reading through a window in view is solid",
      LSM._local_style(dict(_solid_reading, blindness=0.31)) == "SOLID",
      "%r" % LSM._local_style(dict(_solid_reading, blindness=0.31)))
# One-way, on purpose. Furniture can hide a gap; it cannot draw one.
check("a dashed reading is not withheld however blinded the window was",
      LSM._local_style(dict(duty=0.6, gap=5, blindness=0.95)) == "DASHED",
      "%r" % LSM._local_style(dict(duty=0.6, gap=5, blindness=0.95)))
check("and a window with no blindness recorded is read as unblinded",
      LSM._local_style(dict(_solid_reading, blindness=None)) == "SOLID")


print("two curves and two styles: naming one names the other")
# What the withheld reading is replaced by. This is the weakest inference in
# the reader and it needs the least: not continuity, only that the panel holds
# what it was declared to hold and that the reader found that many curves here.
# On 397 Figure 1 it recovers four of the eighteen cells, 0:30 among them.
_DECLARED = ["SOLID", "DASHED"]


def _fill(styles):
    found = {"x": [dict(y=float(i), style=s) for i, s in enumerate(styles)]}
    LSM._complement_fill(found, _DECLARED)
    return [(c["style"], c.get("style_source", "")) for c in found["x"]]


check("the one blank among as many curves as series takes the missing style",
      _fill(["SOLID", None]) == [("SOLID", ""),
                                 ("DASHED", "COMPLEMENT_OF_DECLARED_STYLES")],
      "%r" % (_fill(["SOLID", None]),))
check("and says so, because an inference that reports itself as a measurement "
      "is worse than no inference",
      _fill([None, "DASHED"])[0][1] == "COMPLEMENT_OF_DECLARED_STYLES")
check("two blanks leave two blanks - there is nothing to eliminate",
      _fill([None, None]) == [(None, ""), (None, "")],
      "%r" % (_fill([None, None]),))
check("a count that is not the declared count fills nothing",
      _fill(["SOLID", None, None]) == [("SOLID", ""), (None, ""), (None, "")],
      "%r" % (_fill(["SOLID", None, None]),))
# THE FAILURE MODE OF THE VERSION THAT WAS THROWN AWAY. A continuity-voting
# fill assigned a style a candidate at that x already carried, which made the
# count two - the reader's own signal that it cannot tell two curves apart -
# and DESTROYED six cells on 397's WOMEN finger-pulse-volume panel that were
# about to be emitted. Elimination cannot do it: it only ever assigns the style
# nobody has.
check("it never hands out a style another curve at that x already carries",
      _fill(["SOLID", "SOLID", None]) == [("SOLID", ""), ("SOLID", ""),
                                          (None, "")],
      "%r" % (_fill(["SOLID", "SOLID", None]),))

# AND IT IS WIRED IN, which the scenarios above cannot see: they call the
# function. A gridline laid along the dashed curve at T7 reproduces 397's 0:30
# on a figure this file drew - the rule is removed as furniture, the removal
# blinds 87% of that window, every dash gap goes with it, and the curve reads
# as a clean solid line. Without the guard there are two SOLID candidates at
# T7 and both cells go; with the guard and without this fill the dashed cell
# has no style and both cells go anyway. Only both together read it.
# One figure, drawn once and used by two sections: the gridline laid along the
# dashed curve at T7 blinds 87% of that window (here) and explains a 35-column
# gap in the ink (the occlusion-cause scenarios further down).
_ruled = image.copy()
ImageDraw.Draw(_ruled).line(
    [(BOX[0] + 1, CAL.value_to_pixel(84.0)), (BOX[1] - 1, CAL.value_to_pixel(84.0))],
    fill="black", width=1)
_ruled_rows = read(_ruled)
_named = [(r["series"], r["x_label"]) for r in _ruled_rows
          if r["line_style_source"] != "MEASURED"]
check("a rule laid along a dashed curve costs that position nothing",
      len(_ruled_rows) == _readable, "got %d of %d" % (len(_ruled_rows), _readable))
check("the curve it blinded is named by elimination, and only that one",
      _named == [("S_NOFLUID", "T7")], "%r" % (_named,))
_t7 = next(r for r in _ruled_rows
           if (r["series"], r["x_label"]) == ("S_NOFLUID", "T7"))
check("named, and still measured: the value is the ink's, not the inference's",
      abs(_t7["mean"] - TRUTH["DASHED"][LABELS.index("T7")]) < 1.5,
      "%.3f against %.1f" % (_t7["mean"], TRUTH["DASHED"][LABELS.index("T7")]))
check("and it carries the blindness that justifies naming it that way",
      _t7["line_window_blindness"] > 0.5, "%r" % _t7["line_window_blindness"])


print("why a gap carried no ink, which is not the same question as how wide it is")
# THE MEASUREMENT THAT MADE THIS NECESSARY. On 397, 160 of 180 cells interpolate
# and 122 of those span three pixels or fewer - the width of the error-bar stem
# standing at every datum. A boolean union of stem, rule and cap cannot say
# whether such a gap is a stroke THIS READER ERASED or a three-pixel dash gap
# the figure drew, and neither can the span: they are the same width. Separated
# by cause, 120 of the 122 are the stem and TWO ARE NOT - which is exactly the
# two that a width rule would have called restored furniture.
_flat = np.poly1d([0.0, 20.0])                      # a curve at row 20
_empty = np.zeros((40, 60), dtype=bool)
_stem = _empty.copy(); _stem[15:25, 31:34] = True   # three columns, fully covered
_rule = _empty.copy(); _rule[19:21, :] = True
check("a gap every column of which is one mask is that mask's doing",
      LSM._occlusion_cause({"ERRORBAR_STEM": _stem}, _flat, 2.5, 30, 34, 40)
      == ("ERRORBAR_STEM", 3),
      "%r" % (LSM._occlusion_cause({"ERRORBAR_STEM": _stem}, _flat, 2.5, 30, 34, 40),))
# PARTLY explained is not explained. A gap covered for two of its three columns
# would be called restored furniture by any rule that asks "is there furniture
# in here", and the claim being made is about the WHOLE gap.
_part = _empty.copy(); _part[15:25, 31:33] = True
check("a gap only partly covered is MIXED, not the mask's doing",
      LSM._occlusion_cause({"ERRORBAR_STEM": _part}, _flat, 2.5, 30, 34, 40)
      == (LSM.MIXED_OCCLUSION, 3),
      "%r" % (LSM._occlusion_cause({"ERRORBAR_STEM": _part}, _flat, 2.5, 30, 34, 40),))
check("a gap no mask covers is the figure's own, not the reader's",
      LSM._occlusion_cause({"ERRORBAR_STEM": _empty}, _flat, 2.5, 30, 34, 40)
      == (LSM.NO_OCCLUSION, 3),
      "%r" % (LSM._occlusion_cause({"ERRORBAR_STEM": _empty}, _flat, 2.5, 30, 34, 40),))
check("two kinds of furniture over one gap is MIXED - one cause or none",
      LSM._occlusion_cause({"ERRORBAR_STEM": _stem, "HORIZONTAL_RULE": _rule},
                           _flat, 2.5, 30, 34, 40)[0] == LSM.MIXED_OCCLUSION,
      "%r" % (LSM._occlusion_cause({"ERRORBAR_STEM": _stem,
                                    "HORIZONTAL_RULE": _rule},
                                   _flat, 2.5, 30, 34, 40),))
check("adjacent supports have no gap to explain",
      LSM._occlusion_cause({"ERRORBAR_STEM": _stem}, _flat, 2.5, 30, 31, 40)
      == (LSM.NO_OCCLUSION, 0))
check("and the causes are the three kinds of furniture this reader removes",
      LSM.BLIND_CAUSES == ("ERRORBAR_STEM", "HORIZONTAL_RULE", "WHISKER_CAP"),
      "%r" % (LSM.BLIND_CAUSES,))

print("the same span, two different answers, on figures this file draws")
# THE SOLID CURVE HAS NO GAPS OF ITS OWN, so with error bars every gap in it is
# the stem, and every one is found to be.
_int = [r for r in read() if r["Value_Method"] == "INTERPOLATED_CURVE_INK"]
_solid_int = [r for r in _int if r["line_style"] == "SOLID"]
check("an unbroken curve's only gaps are the stems, and it says so",
      _solid_int and all(r["Occlusion_Cause"] == "ERRORBAR_STEM"
                         for r in _solid_int),
      "%r" % sorted({(r["Occlusion_Cause"], r["Value_Span_Px"])
                     for r in _solid_int}))
# The dashed curve's gaps at the same positions are its OWN dash gaps widened by
# the stem, so neither explains the whole gap: MIXED, refused as furniture.
_dashed_wide = [r for r in _int
                if r["line_style"] == "DASHED" and r["Value_Span_Px"] > 3]
check("a dash gap widened by a stem is explained by neither, so MIXED",
      _dashed_wide and all(r["Occlusion_Cause"] == LSM.MIXED_OCCLUSION
                           for r in _dashed_wide),
      "%r" % sorted({(r["Occlusion_Cause"], r["Value_Span_Px"])
                     for r in _dashed_wide}))
# THE SAME FIGURE WITHOUT ERROR BARS. The solid curve now needs no interpolation
# at all, and the dashed curve's gaps are the FIGURE's - at widths the with-bars
# run also produced. Nothing in the span separates the two sets.
_bare_int = [r for r in read(_bare) if r["Value_Method"] == "INTERPOLATED_CURVE_INK"]
check("take the bars away and the unbroken curve needs no interpolation",
      not [r for r in _bare_int if r["line_style"] == "SOLID"],
      "%r" % [(r["x_label"], r["Value_Span_Px"])
              for r in _bare_int if r["line_style"] == "SOLID"])
check("while the dashed curve's own gaps are the figure's, not the reader's",
      _bare_int and all(r["Occlusion_Cause"] == LSM.NO_OCCLUSION
                        for r in _bare_int),
      "%r" % sorted({(r["Occlusion_Cause"], r["Value_Span_Px"])
                     for r in _bare_int}))
_shared = ({r["Value_Span_Px"] for r in _dashed_wide}
           & {r["Value_Span_Px"] for r in _bare_int})
check("and the two sets share widths, so the width cannot be the test",
      bool(_shared), "with bars %r / without %r"
      % (sorted({r["Value_Span_Px"] for r in _dashed_wide}),
         sorted({r["Value_Span_Px"] for r in _bare_int})))
# AND THE CAUSES HAVE TO BE DISTINCT, not three names for one union. The first
# version of this passed with `ERRORBAR_STEM` aliased to stem|rule|cap, because
# on a figure whose only furniture at the data IS the stem, a union and a part
# answer alike. The rule laid along the dashed curve at T7 is where they differ:
# a 35-column gap the GRIDLINE explains, which a reader that cannot tell its
# furniture apart would file under the stem - and "a stroke the error bar hid"
# and "a stroke a gridline hid" are different claims about different widths.
_ruled_int = [r for r in read(_ruled)
              if r["Value_Method"] == "INTERPOLATED_CURVE_INK"]
_by_rule = [r for r in _ruled_int if r["Occlusion_Cause"] == "HORIZONTAL_RULE"]
check("a gap a gridline explains is the gridline's, not the stem's",
      len(_by_rule) == 1 and _by_rule[0]["x_label"] == "T7",
      "%r" % sorted({(r["series"], r["x_label"], r["Occlusion_Cause"],
                      r["Value_Span_Px"]) for r in _ruled_int}))
check("and it is far wider than any stem gap on the same figure",
      _by_rule[0]["Value_Span_Px"]
      > max(r["Value_Span_Px"] for r in _ruled_int
            if r["Occlusion_Cause"] == "ERRORBAR_STEM"),
      "%d against %d" % (_by_rule[0]["Value_Span_Px"],
                         max(r["Value_Span_Px"] for r in _ruled_int
                             if r["Occlusion_Cause"] == "ERRORBAR_STEM")))
check("every cell says which two columns its number was measured between",
      all(r["Value_Support_Left_Px"] is not None
          and r["Value_Support_Right_Px"] is not None
          for r in read() if r["Value_Method"] != "FIT_FALLBACK"))


print("a number read off the ink and a number the fit made are not the same claim")
# `_ink_at` HAS FOUR PATHS AND USED TO RETURN ONE THING. Measured on 397's
# twelve line panels the day this was written: 180 cells, of which SIX were
# direct observations. 160 were interpolated - 122 of those across a span of
# three pixels or less, which is the error-bar stem the reader blinds at every
# datum, so most "interpolation" here is the reader stepping over ink IT
# removed - and 14 had ink on one side only. All 180 left by the same door.
_DIRECT = LSM._ink_at({40: 10.0}, 40, np.poly1d([0.0, 99.0]))
check("ink in the column at x is a direct reading",
      _DIRECT == (10.0, "DIRECT_CURVE_INK", 0, 40, 40), "%r" % (_DIRECT,))
_BOTH = LSM._ink_at({38: 10.0, 42: 14.0}, 40, np.poly1d([0.0, 99.0]))
check("ink on both sides is interpolated, and reports the span it crossed",
      _BOTH == (12.0, "INTERPOLATED_CURVE_INK", 4, 38, 42), "%r" % (_BOTH,))
# Not interpolation: nothing brackets the answer. Called INTERPOLATED it would
# have been reviewable as a restored stroke, which is what it is not.
_ONE = LSM._ink_at({30: 10.0}, 40, np.poly1d([0.0, 99.0]))
check("ink on one side only is extrapolation, not interpolation",
      _ONE == (10.0, "EXTRAPOLATED_CURVE_INK", 10, 30, 30), "%r" % (_ONE,))
_NONE = LSM._ink_at({}, 40, np.poly1d([0.0, 99.0]))
check("and no ink at all is the fit's answer, which is a model estimate",
      _NONE == (99.0, "FIT_FALLBACK", 0, None, None), "%r" % (_NONE,))

print("every cell says how it was named and how its number was got")
_prov = read()
check("both questions are answered on every row",
      all(r["Identity_Method"] and r["Value_Method"] for r in _prov))
check("and in the shared vocabulary, not this reader's private one",
      {r["Identity_Method"] for r in _prov} <= set(PROV.IDENTITY_METHODS)
      and {r["Value_Method"] for r in _prov} <= set(PROV.VALUE_METHODS),
      "%r / %r" % (sorted({r["Identity_Method"] for r in _prov}),
                   sorted({r["Value_Method"] for r in _prov})))
# DERIVED, never declared. A tier a reader writes is a tier a reader can lower.
check("the tier on every row is the one the registry derives",
      all(r["Review_Tier"] == PROV.review_tier(r["Identity_Method"],
                                               r["Value_Method"])
          for r in _prov))
check("a measured style is MEASURED_LINE_STYLE, an eliminated one is not",
      {r["Identity_Method"] for r in _prov if r["line_style_source"] == "MEASURED"}
      == {"MEASURED_LINE_STYLE"},
      "%r" % sorted({(r["line_style_source"], r["Identity_Method"])
                     for r in _prov}))


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
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
