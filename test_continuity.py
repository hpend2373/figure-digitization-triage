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

import numpy as np
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
# A SIGNED BAR CHART. The marks stand on a zero line drawn THROUGH the middle of
# the panel and the y axis runs on past it to the bottom of the scale. Publication
# 475's figure 2 is six of these, and on every one of them the two criteria that
# read "the baseline" were reading a row with no ink in it.
SPINE2, TOP2, BOT2, ZERO = 60, 40, 240, 140


def signed(scale=1, groups=((78, 98, -50), (121, 141, 40), (159, 179, -45)),
           rule_to=None, box_x1=262, extra=(), title=False):
    """`rule_to=None` draws NO zero line, which is the case that broke: the printed
    one on publication 475's figure 2 is lighter than ink, so the only thing on that
    row is the bars themselves."""
    s = scale
    im = Image.new("L", (500 * s, 300 * s), 255)
    d = ImageDraw.Draw(im)
    d.rectangle([SPINE2 * s, TOP2 * s, SPINE2 * s + 1 * s, (BOT2 - 4) * s], fill=0)
    if title:                       # the rotated axis title, left of the label strip
        d.rectangle([22 * s, 90 * s, 40 * s, 190 * s], fill=0)
    if rule_to:
        d.rectangle([SPINE2 * s, ZERO * s, rule_to * s, ZERO * s + 1 * s], fill=0)
    for x0, x1, h in tuple(groups) + tuple(extra):
        top, bot = (ZERO + h, ZERO) if h < 0 else (ZERO, ZERO + h)
        d.rectangle([x0 * s, top * s, x1 * s, bot * s], fill=0)
    _a, dark = A._dark(im)
    panel = (SPINE2 * s - 2, box_x1 * s, TOP2 * s, BOT2 * s)
    return dark, SPINE2 * s, (TOP2 * s, (BOT2 - 4) * s), panel


# BAR GROUPS 59 px APART, which is what makes the fixture a test rather than a
# drawing: the severance below is 40 px, narrower than the panel's own spacing and
# wider than ADOPT_GAP, so only a panel-calibrated reach can tell it is not a
# boundary. 475 figure 2's numbers are 74 and 37.
UP = ((78, 98, -50), (158, 178, -40), (238, 258, -45))

section("7. a signed bar chart: the marks do not stand on the foot of the axis")

for s in (1, 2):
    dark, sx, run, panel = signed(s, rule_to=262)
    by = C.baseline_row(dark, panel, sx, run)
    check("%dx the baseline is the row the bars stand on, not the axis's foot" % s,
          abs(by - ZERO * s) <= 2 and by != run[1] - 1,
          "baseline_row=%d, zero=%d, axis foot=%d" % (by, ZERO * s, run[1] - 1))

dark, sx, run, panel = signed(1, groups=UP, extra=((305, 335, -45),))
orphan = (300, 340, TOP2, BOT2)   # a cut leaf spans the panel's rows
ok, why = C.baseline_continues(dark, panel, orphan, sx, run)
check("and the crossing gap is measured there, not reported as an empty row",
      "간격" in why and "잉크가 없다" not in why, why)
ok2, why2 = C.more_regular(dark, panel, orphan, sx, run)
check("the arbiter counts marks there too, instead of finding none",
      "막대·눈금이 0" not in (why2 or ""), why2)

section("8. a fragment leaves MARKS outside, not a rule")

# A zero line printed 60 px past the plotting area, with nothing drawn in it.
dark, sx, run, panel = signed(1, rule_to=360, groups=UP)
by = C.baseline_row(dark, panel, sx, run)
check("a rule overrunning the box with no mark in it is not a severance",
      A.cut_through_axis(dark, panel, sx, by) == "",
      A.cut_through_axis(dark, panel, sx, by))

# The severance itself: a bar group standing 37 px past the box edge, which is
# where the cut fell. The three-pixel probe that used to ask this lands in white.
dark, sx, run, panel = signed(1, groups=UP, extra=((305, 335, -45),))
by = C.baseline_row(dark, panel, sx, run)
said = A.cut_through_axis(dark, panel, sx, by)
check("a bar group 43 px past the box edge is a severance", "right of x1" in said, said)
check("and the three-pixel probe could not have seen it",
      A.cut_through_axis(dark, panel, sx, by, reach=3) == "",
      A.cut_through_axis(dark, panel, sx, by, reach=3))

# The label strip is not a mark, and a box whose left edge IS its axis has one.
# The axis title is ink, it crosses the baseline row, and it is not a mark. Only
# the box's own left edge can say so: a box that starts AT its spine has the label
# strip and the title outside it by construction.
dark, sx, run, panel = signed(1, groups=UP, title=True)
tight = (int(sx), panel[1], panel[2], panel[3])
check("no left severance is claimed where the box's left edge is its own spine",
      "left of x0" not in A.cut_through_axis(
          dark, tight, sx, C.baseline_row(dark, tight, sx, run)),
      A.cut_through_axis(dark, tight, sx, C.baseline_row(dark, tight, sx, run)))

section("9. how far is \"touching\": the panel says, not a constant")

dark, sx, run, panel = signed(1, groups=UP, extra=((305, 335, -45),))
orphan = (300, 340, TOP2, BOT2)   # a cut leaf spans the panel's rows
gap = orphan[0] - panel[1]
grown = A.adopt_orphans(dark, [panel], [orphan])
check("a piece %d px out - past ADOPT_GAP=%d - is still offered to the six"
      % (gap, A.ADOPT_GAP),
      gap > A.ADOPT_GAP and any(b[1] >= 335 for b in grown),   # the group ends at 335
      "gap %d, boxes now %s" % (gap, grown))

# And the reach is not unlimited: the panel's own widest baseline gap is what it
# is, so a piece beyond that is a neighbour, not a fragment.
dark, sx, run, panel = signed(1, groups=UP, extra=((430, 460, -45),))
far = (425, 465, TOP2, BOT2)
grown = A.adopt_orphans(dark, [panel], [far])
check("a piece %d px out - past the panel's own widest gap - is not"
      % (far[0] - panel[1]),
      all(b[1] < far[0] for b in grown), "boxes now %s" % (grown,))

# --------------------------------------------------------------------------
BAR_FOOT_MARGIN = C.BAR_FOOT

section("10. the threshold the figure states, and what it may decide")

# A LIGHT-GREY AXIS. Publication 475's figure 1 draws its left column's y axes at a
# grey around 155; the shipped threshold of 140 admits two rows of a 238-row line.
def grey_axis(axis=155, page=250, h=270):
    """A figure whose STRUCTURE is printed light and whose marks are solid: the axis,
    its numerals and its gridlines at one grey, the bars in ink. That mixture is what
    makes the shipped threshold wrong here - it is dark enough for the bars and too
    dark for everything holding them."""
    im = Image.new("L", (200, h), page)
    d = ImageDraw.Draw(im)
    d.rectangle([60, 10, 61, h - 20], fill=axis)
    for y in range(30, h - 30, 40):
        d.rectangle([100, y, 120, y + 24], fill=20)        # marks, in solid ink
    for y in range(14, h - 20, 24):
        d.rectangle([40, y, 56, y + 10], fill=axis)        # tick numerals
        d.rectangle([62, y + 5, 190, y + 5], fill=axis)    # gridlines
    return im


im = grey_axis()
grey = np.asarray(im.convert("L"))
t = A.figure_ink(grey)
check("the figure's own threshold sits above the light-grey axis",
      140 < t <= 160, "figure_ink=%d" % t)

_saved = A.INK
A.INK = A.INK_DEFAULT
_a, d140 = A._dark(im)
A.INK = t
_a, dt = A._dark(im)
A.INK = _saved
run140 = A._longest_run(d140[:, 60])
runt = A._longest_run(dt[:, 60])
check("at the shipped threshold the axis is not there", run140 < A.MIN_AXIS_PX,
      "longest run %d px" % run140)
check("at the figure's own threshold the whole axis is", runt >= 200,
      "longest run %d px" % runt)
check("and it is the axis that appears, not the page",
      float(dt.mean()) < 0.35, "ink share %.3f" % float(dt.mean()))
# A blank crop has nothing to separate. Otsu is undefined there, not merely
# uninformative, so it answers with the shipped threshold rather than raising.
check("a clip of one grey falls back to the shipped threshold",
      A.figure_ink(np.asarray(Image.new("L", (40, 40), 200))) == A.INK_DEFAULT)
check("and a two-level clip does not - it answers between them",
      20 < A.figure_ink(np.asarray(grey_axis(axis=60, page=230))) <= 230)

section("11. what \"in this plot's coordinates\" is measured on")

# Bars that hang DOWN from a drawn zero line, in columns that also carry the plate's
# tick labels further down. Publication 475's figure 1 is exactly this.
def hanging(scale=1, labels=True):
    """A piece whose box reaches past the panel's rows, as a cut leaf does: its bars
    hang below a drawn zero line, the plate's x labels sit under it, and the column
    title sits above. All three are ink in the same columns, and only one of them is
    a mark drawn against this panel's axis."""
    s = scale
    im = Image.new("L", (500 * s, 400 * s), 255)
    d = ImageDraw.Draw(im)
    d.rectangle([SPINE2 * s, TOP2 * s, SPINE2 * s + 1 * s, (BOT2 - 4) * s], fill=0)
    d.rectangle([SPINE2 * s, ZERO * s, 380 * s, ZERO * s + 1 * s], fill=0)   # zero rule
    for x0, x1 in ((78, 98), (158, 178), (238, 258)):
        d.rectangle([x0 * s, ZERO * s, x1 * s, (ZERO + 55) * s], fill=0)     # the panel's
    for x0, x1 in ((305, 325), (335, 355)):
        d.rectangle([x0 * s, ZERO * s, x1 * s, (ZERO + 48) * s], fill=0)     # the piece's
    d.rectangle([300 * s, 5 * s, 360 * s, 25 * s], fill=0)                   # column title
    if labels:
        d.rectangle([300 * s, 320 * s, 360 * s, 360 * s], fill=0)            # x labels
    _a, dark = A._dark(im)
    return (dark, SPINE2 * s, (TOP2 * s, (BOT2 - 4) * s),
            (SPINE2 * s - 2, 262 * s, TOP2 * s, BOT2 * s),
            (300 * s, 360 * s, ZERO * s - 2, 365 * s))


dark, sx, run, panel, piece = hanging()
ok, why = C.same_coordinates(dark, panel, piece, run, sx, "right")
check("bars hanging below the zero line are in its coordinates", ok is True, why)
check("and nearly every column of the piece is counted, not one",
      "1.00" in why or "0.9" in why, why)

# Each of the three things that were being measured instead, one at a time.
_by = C.baseline_row(dark, panel, sx, run)
check("the row asked about is the one the marks stand on, not the axis's foot",
      abs(_by - ZERO) <= 2 and _by != run[1] - 1,
      "row %d, axis foot %d" % (_by, run[1] - 1))
col = np.where(dark[piece[2]:piece[3], piece[0] + 8])[0] + piece[2]
check("a hanging bar's LAST ink is its far end - only its FIRST is on the baseline",
      abs(int(col[-1]) - _by) > BAR_FOOT_MARGIN and abs(int(col[0]) - _by) <= BAR_FOOT_MARGIN,
      "first %d last %d baseline %d" % (col[0], col[-1], _by))
full = np.where(dark[:, piece[0] + 8])[0]
check("and over the whole column the title above answers first, the labels last",
      int(full[0]) < TOP2 and int(full[-1]) > _by + 100,
      "column ink runs %d..%d, baseline %d" % (full[0], full[-1], _by))
_ok, _why = C.same_coordinates(dark, panel, piece, run, sx, "right")
# ASKED OF THE NUMBER, NOT OF THE STRING. This read `"1.00" not in why.split(",")[-1]`,
# which stopped meaning what it says the moment the detail gained a second figure.
_legacy, _corrected = C.inside_shares(dark, piece, run)
check("the band term cannot carry this one - the piece reaches past the panel's rows",
      _legacy < C.INSIDE_SHARE, "legacy %.3f, intersection %.3f" % (_legacy, _corrected))

section("12. a plate shredded into more boxes than it has axes")

# The numbers are publication 475 figure 1's: eleven boxes each reading a ladder,
# against the five the re-inked cut produced, for six recorded axes.
shredded = A.mode_score(False, 11, 11, 6)
five = A.mode_score(False, 4, 5, 6)
check("five boxes near the recorded count beat eleven that are not",
      five > shredded, "%s vs %s" % (five, shredded))
check("and with the term off, the eleven win again - the change is observable",
      A.mode_score(False, 11, 11, 6, near=False)
      > A.mode_score(False, 4, 5, 6, near=False))
check("an exact count match still outranks any number of ladders",
      A.mode_score(True, 1, 6, 6) > A.mode_score(False, 40, 40, 6))
check("where no count was recorded, ladders decide as before",
      A.mode_score(False, 11, 11, 0) > A.mode_score(False, 4, 5, 0))
check("overshooting and undershooting by the same amount rank together",
      A.mode_score(False, 3, 8, 6)[1] == A.mode_score(False, 3, 4, 6)[1])


section("13. criterion 4's band term is a ratio of two different regions")

# THE NUMBER THAT IS NOT A SHARE. `band` spans the whole axis run and `whole` spans
# the piece's rows, so the legacy value counts the PANEL's ink over the PIECE's. On a
# panel title above the axis top it reads 2.44 on a term that asks for 0.90. The
# intersection is what the criterion's own docstring describes, and is in [0, 1].
for s in (1, 2):
    im = Image.new("L", (400 * s, 300 * s), 255)
    d = ImageDraw.Draw(im)
    d.rectangle([60 * s, 40 * s, 60 * s, 240 * s], fill=0)
    for x0, x1 in ((78, 98), (120, 140), (162, 182)):
        d.rectangle([x0 * s, 100 * s, x1 * s, 140 * s], fill=0)
        d.rectangle([x0 * s, 141 * s, x1 * s, 170 * s], fill=0)
    d.rectangle([80 * s, 10 * s, 180 * s, 26 * s], fill=0)          # the panel title
    _a, dk = A._dark(im)
    title = (80 * s, 181 * s, 10 * s, 27 * s)
    _run = (40 * s, 241 * s)
    legacy, corrected = C.inside_shares(dk, title, _run)
    check("%dx the legacy share of a title above the axis exceeds 1" % s,
          legacy > 1.0, "legacy %.3f" % legacy)
    check("%dx and the intersection share of the same title is 0" % s,
          corrected == 0.0, "intersection %.3f" % corrected)
    # THE DECISION IS UNCHANGED, DELIBERATELY. Swapping the value swaps which
    # pieces are adopted, and that is an arm of its own.
    ok, why = C.same_coordinates(dk, (58 * s, 200 * s, 40 * s, 140 * s), title,
                                 _run, 60 * s, "above")
    check("%dx and the verdict still follows the legacy number" % s, ok is True, why)

# THE INVARIANT, over every fixture in this file that has a panel and a piece.
_cases = []
for s in (1, 2):
    dark, sx, run = figure(s)
    _cases.append((dark, box(ORPHAN, s), run))
    _cases.append((dark, box(NEIGHBOUR, s), run))
    dark, sx, run, panel = signed(s, rule_to=262)
    _cases.append((dark, (int(300 * s), int(340 * s), int(TOP2 * s), int(BOT2 * s)), run))
    dark, sx, run, panel = signed(s, rule_to=262, title=True)
    _cases.append((dark, (int(22 * s), int(41 * s), int(90 * s), int(190 * s)), run))
    dark, sx, run, piece, panel = hanging(s)
    _cases.append((dark, piece, run))
_out = [C.inside_shares(d, o, r)[1] for d, o, r in _cases]
check("the intersection share is in [0, 1] on all %d fixtures" % len(_out),
      all(0.0 <= v <= 1.0 for v in _out),
      "out of range: %s" % [v for v in _out if not 0.0 <= v <= 1.0])
check("and the legacy share is not, on at least one of them",
      any(C.inside_shares(d, o, r)[0] > 1.0 for d, o, r in _cases),
      "no fixture exposes the defect, so this section proves nothing")

# --------------------------------------------------------------------------
print()
# One line, one format, for the CI guard that checks the documented scenario
# count against the measured one.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
