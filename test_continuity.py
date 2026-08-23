# -*- coding: utf-8 -*-
"""What may be put back into a panel, and what may not.

    python3 test_continuity.py     # exit 0 = all scenarios pass

The defect these scenarios pin is structural rather than optical. An XY cut
looks for whitespace, and the band between two bar GROUPS is the same
whitespace as the gutter between two PANELS - so a bar chart gets severed, the
piece without the y axis fails the panel filter, and its data leaves the figure
silently. On publication 345 figure 4 that cost the DBP panel its Earth bars.

`continuity.py` answers it with six statements measured separately rather than
one threshold. The scenarios here are mostly about the two ways that judgement
can be wrong in opposite directions:

    a fragment REFUSED    the panel loses data and nothing says so
    a neighbour ADOPTED   two panels become one and the axis assignment shifts

so both fixtures are drawn, and the neighbour is drawn in the SAME ROW BAND as
the panel - the easy version, a neighbour somewhere else on the page, would be
refused by arithmetic that cannot tell the hard case apart.

Nothing here is a distance in pixels: every geometric scenario runs at two
scales and must give the same verdict at both. `baseline_continues` compares
the crossing gap against the widest gap ALREADY INSIDE this panel's baseline,
so the fixture at 2x has a 38 px break that must still read as continuous while
the 1x neighbour's 120 px break does not.

The figures are drawn with PIL, and no scenario here calls OCR: panels, spines,
baselines and continuity are geometry. That is also why `axis_reader` imports
without pytesseract, which the last two scenarios pin.
"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import axis_reader as A                                          # noqa: E402
import continuity as C                                           # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def section(title):
    print("\n" + title)


# --------------------------------------------------------------------------
# The fixture. One panel, drawn as the cut leaves it: a y axis, three bars to
# its right, then a break, then two more bars that the cut called a separate
# block. The gaps are the whole point, so they are named:
#
#   between bar A and bar B   22 px   the widest gap INSIDE the panel
#   between bar B and bar C   17 px
#   between bar C and bar D   19 px   the CROSSING gap - narrower than the
#                                     panel's own widest, so not a boundary
#
# No x axis line is drawn, deliberately. Where a figure draws one, the baseline
# row is inked from end to end and no gap exists to measure; the panels this
# defect happens to are the ones standing on nothing.
# --------------------------------------------------------------------------
SPINE_X, AXIS_TOP, AXIS_BOT = 60, 40, 240
BARS = [(78, 98, 80), (121, 141, 60), (159, 179, 70),        # panel side
        (199, 219, 75), (237, 257, 65)]                      # the severed piece
PANEL = (60, 185, 40, 240)
ORPHAN = (190, 265, 40, 240)
NEIGHBOUR = (300, 400, 40, 240)


def figure(scale=1, bars=BARS, neighbour=False, legend=False, below=None):
    """(dark, sx, run) for the fixture at `scale`, plus whatever else is asked."""
    w, h = 420 * scale, 300 * scale
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    s = scale
    d.rectangle([SPINE_X * s, AXIS_TOP * s, SPINE_X * s + 1 * s, AXIS_BOT * s], fill=0)
    for x0, x1, bh in bars:
        d.rectangle([x0 * s, (AXIS_BOT - bh) * s, x1 * s, AXIS_BOT * s], fill=0)
    if neighbour:                       # a second panel, same rows, own axis
        d.rectangle([300 * s, AXIS_TOP * s, 300 * s + 1 * s, AXIS_BOT * s], fill=0)
        for x0, x1, bh in ((320, 340, 80), (358, 378, 60)):
            d.rectangle([x0 * s, (AXIS_BOT - bh) * s, x1 * s, AXIS_BOT * s], fill=0)
    if legend:                          # a key above the plot, in the piece's columns
        d.rectangle([200 * s, 8 * s, 250 * s, 30 * s], fill=0)
    if below is not None:               # ink under the baseline, in the piece's columns
        d.rectangle([200 * s, below[0] * s, 250 * s, below[1] * s], fill=0)
    _a, dark = A._dark(im)
    return dark, SPINE_X * s, (AXIS_TOP * s, AXIS_BOT * s)


def box(b, s):
    return tuple(int(v * s) for v in b)


# --------------------------------------------------------------------------
section("1. the baseline: a break the panel already contains is not a boundary")

for s in (1, 2):
    dark, sx, run = figure(s)
    ok, why = C.baseline_continues(dark, box(PANEL, s), box(ORPHAN, s), sx, run)
    check("%dx a 19 px crossing gap against a 22 px internal gap continues" % s,
          ok is True, why)

    dark, sx, run = figure(s, neighbour=True)
    ok, why = C.baseline_continues(dark, box(PANEL, s), box(NEIGHBOUR, s), sx, run)
    check("%dx the next panel's 120 px break does not" % s, ok is False, why)

# The constant that is not there. Widen the crossing gap past the panel's own
# widest and the SAME code refuses it - which is what makes the first scenario a
# measurement of this panel rather than a threshold that happened to fit.
far = BARS[:3] + [(210, 230, 75), (248, 268, 65)]
dark, sx, run = figure(1, bars=far)
ok, why = C.baseline_continues(dark, PANEL, (200, 275, 40, 240), sx, run)
check("a 30 px crossing gap against the same 22 px internal gap does not",
      ok is False, why)

dark, sx, run = figure(1)
ok, why = C.baseline_continues(dark, PANEL, (270, 340, 40, 240), sx, run)
check("a piece with no ink on the baseline row is not joined by it", ok is False, why)

# --------------------------------------------------------------------------
section("2. the rows: measured against box and axis together, not the axis alone")

for s in (1, 2):
    dark, sx, run = figure(s)
    ok, why = C.same_rows(box(PANEL, s), box(ORPHAN, s), run)
    check("%dx the piece shares the panel's rows" % s, ok is True, why)

dark, sx, run = figure(1, legend=True)
ok, why = C.same_rows(PANEL, (200, 265, 5, 35), run)
check("a key above the plot does not", ok is False, why)

# THE REFERENCE IS THE UNION OF THE BOX AND THE AXIS, and each half of that is
# a case the other gets wrong. A box may be SHORT - the cut clipped it above its
# own spine - and judging the piece by that box refuses it for rows the panel
# does have:
short = (60, 185, 120, 200)                      # a box that clips its own axis
ok, why = C.same_rows(short, ORPHAN, run)
check("a box shorter than its axis still shares the axis's rows", ok is True, why)

# And a plot legitimately overruns its spine - error-bar caps above the top
# tick, tick labels below the baseline - so the drawn axis is too tight a frame
# too. The first version of this test measured against the axis alone and
# refused the very bar group it was written for.
tall, spilled = (60, 185, 10, 270), (190, 265, 12, 268)
ok, why = C.same_rows(tall, spilled, run)
check("a piece in the rows the plot overruns its axis by shares them", ok is True, why)
ok, why = C.same_rows(PANEL, spilled, run)
check("and where the plot does not overrun, the same piece is outside",
      ok is False, why)

# --------------------------------------------------------------------------
section("3. data without an axis: what makes a piece a piece")

for s in (1, 2):
    dark, sx, run = figure(s, neighbour=True)
    ok, why = C.data_without_axis(dark, box(ORPHAN, s))
    check("%dx the severed bars carry ink and no axis" % s, ok is True, why)
    ok, why = C.data_without_axis(dark, box(NEIGHBOUR, s))
    check("%dx the next panel has its own axis, so it is not an orphan" % s,
          ok is False, why)

dark, sx, run = figure(1)
ok, why = C.data_without_axis(dark, (270, 340, 40, 240))
check("an empty margin has no axis and nothing to recover", ok is False, why)

# --------------------------------------------------------------------------
section("4. the coordinates: marks drawn against THIS axis")

for s in (1, 2):
    dark, sx, run = figure(s)
    ok, why = C.same_coordinates(dark, box(PANEL, s), box(ORPHAN, s), run, sx)
    check("%dx bars standing on the baseline are in its coordinates" % s,
          ok is True, why)

# The window where this criterion is not implied by the rows. A box may reach
# 12% past the panel's rows and still pass `same_rows`; ink that lies IN that
# overhang - a stray label block under the baseline - is drawn against nothing
# in this plot, and only this criterion says so.
dark, sx, run = figure(1, bars=BARS[:3], below=(244, 260))
under = (190, 265, 40, 262)
ok, _ = C.same_rows(PANEL, under, run)
check("a block under the baseline still passes the rows", ok is True)
ok, why = C.same_coordinates(dark, PANEL, under, run, sx)
check("and fails the coordinates - the criterion is observable", ok is False, why)

# --------------------------------------------------------------------------
section("5. the caption: the figure's floor, and unknown is not false")

ok, why = C.same_caption(PANEL, ORPHAN, None)
check("no caption read means unknown, not refused", ok is None, why)
ok, why = C.same_caption(PANEL, ORPHAN, 260)
check("both pieces above the caption belong to the same figure", ok is True, why)
ok, why = C.same_caption(PANEL, (190, 265, 265, 292), 260)
check("a piece below the caption belongs to the page, not the plot",
      ok is False, why)

# --------------------------------------------------------------------------
section("6. regularity: the arbiter, and what it declines to answer")

for s in (1, 2):
    dark, sx, run = figure(s)
    ok, why = C.more_regular(dark, box(PANEL, s), box(ORPHAN, s), sx, run)
    check("%dx the piece extends the bars' rhythm" % s, ok is True, why)

dark, sx, run = figure(1, bars=BARS[:2] + [(199, 219, 75)])
ok, why = C.more_regular(dark, (60, 185, 40, 240), (190, 265, 40, 240), sx, run)
check("two bars are too few to speak of regularity - unknown, not refused",
      ok is None, why)

dark, sx, run = figure(1, bars=BARS[:3])
ok, why = C.more_regular(dark, PANEL, (270, 340, 40, 240), sx, run)
check("a piece that adds no marks is not evidence either way", ok is None, why)

wrecked = BARS[:3] + [(340, 360, 75)]
dark, sx, run = figure(1, bars=wrecked)
ok, why = C.more_regular(dark, PANEL, (330, 400, 40, 240), sx, run)
check("a mark that breaks the spacing is a refusal", ok is False, why)

# --------------------------------------------------------------------------
section("the verdict: what the six add up to")

for s in (1, 2):
    dark, sx, run = figure(s, neighbour=True)
    adopt, t = C.verdict(dark, box(PANEL, s), box(ORPHAN, s), sx, run, 260 * s)
    check("%dx the severed bars are put back" % s, adopt is True, C.describe(t))

    adopt, t = C.verdict(dark, box(PANEL, s), box(NEIGHBOUR, s), sx, run, 260 * s)
    check("%dx the neighbouring panel is not" % s, adopt is False, C.describe(t))
    # AND ON MORE THAN ONE GROUND, which is what stops one criterion's bad day
    # from merging two panels. It shares the panel's rows and stands on the same
    # baseline row, so those two do not save it.
    check("%dx refused for having its own axis" % s,
          t["data_no_axis"][0] is False, C.describe(t))
    check("%dx and independently for the break in the baseline" % s,
          t["baseline"][0] is False, C.describe(t))

dark, sx, run = figure(1, bars=BARS[:3], below=(244, 260))
adopt, t = C.verdict(dark, PANEL, (190, 265, 40, 262), sx, run, 300)
check("a piece in the panel's rows with no join to it is refused - proximity "
      "is never the evidence", adopt is False, C.describe(t))
check("and it is refused for lack of evidence, not for failing the rows",
      t["rows"][0] is True and t["baseline"][0] is False
      and t["coords"][0] is False, C.describe(t))

dark, sx, run = figure(1)
adopt, t = C.verdict(dark, PANEL, ORPHAN, sx, run, None)
check("an unknown caption does not veto", adopt is True and t["caption"][0] is None,
      C.describe(t))

dark, sx, run = figure(1, bars=BARS[:2] + [(159, 179, 70)])
adopt, t = C.verdict(dark, (60, 185, 40, 240), (190, 265, 40, 240), sx, run, 260)
check("nor does an unmeasurable regularity", t["regular"][0] is None, C.describe(t))

# A piece that satisfies everything except the arbiter. `more_regular` never
# adopts on its own and it does veto, so this is the one direction it acts in.
dark, sx, run = figure(1, bars=BARS[:3] + [(199, 219, 75), (330, 350, 65)])
adopt, t = C.verdict(dark, PANEL, (190, 360, 40, 240), sx, run, 260)
check("regularity vetoes a join the other five accept",
      t["baseline"][0] is True and t["rows"][0] is True
      and t["regular"][0] is False and adopt is False, C.describe(t))

# --------------------------------------------------------------------------
section("the reason is carried out, and OCR is optional")

dark, sx, run = figure(1)
_adopt, t = C.verdict(dark, PANEL, ORPHAN, sx, run, 260)
line = C.describe(t)
check("every one of the six names appears in the harness column",
      all(n in line for n in C.NAMES), line)
check("and each carries the number it was decided on",
      all(any(ch.isdigit() for ch in t[n][1]) for n in C.NAMES), line)

check("axis_reader imports with no OCR backend installed",
      "axis_reader" in sys.modules)

# TAKEN AWAY RATHER THAN LOOKED FOR. Gating this on whether tesseract happens to
# be on THIS machine makes the scenario count a property of the machine, and the
# repository has already been through that once with the PDF backends.
_saved, A.pytesseract = A.pytesseract, None
try:
    strip = Image.new("L", (200, 200), 255)
    try:
        A._ocr_numerals(strip, None, 0, 100, 0, 100)
        check("a tick numeral without OCR raises rather than reading none", False,
              "it returned instead of raising")
    except RuntimeError as exc:
        check("a tick numeral without OCR raises rather than reading none",
              "pytesseract" in str(exc), str(exc))
    except Exception as exc:                        # noqa: BLE001
        check("a tick numeral without OCR raises rather than reading none", False,
              "%s: %s" % (type(exc).__name__, exc))
    # And it must raise for a strip big enough to have been read, not fall out of
    # the size floor: a refusal that only fires on inputs nothing would pass is
    # not the refusal under test.
    try:
        A._ocr_numerals(strip, None, 0, 4, 0, 4)
        check("the size floor still answers before OCR is reached", True)
    except RuntimeError:
        check("the size floor still answers before OCR is reached", False,
              "a strip too small to read raised the OCR error instead")
finally:
    A.pytesseract = _saved

# --------------------------------------------------------------------------
print()
# One line, one format, for the CI guard that checks the documented scenario
# count against the measured one.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
