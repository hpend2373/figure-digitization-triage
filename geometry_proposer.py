"""Propose a panel's geometry from a raster. Never propose what it means.

    python3 geometry_proposer.py RASTER --out DIR [--region x0,y0,x1,y1]

The plan needs, per panel: a box, an axis region, two tick pairs (value and
pixel) per axis, an x pixel per group, and a fill or marker per series. The
compiler checks every one of those and the runner refuses without them - and
nothing proposes any of them. Publication 127 cost an hour of measuring three
panels by hand; at 189 B-shape figures that is the project's largest single
cost, and it is the same measurement every time.

So this measures the parts that ARE measurement and refuses the parts that are
reading:

    proposed          the plot frame, the axis regions, the tick PIXEL rows,
                      the tick spacing, the group anchor x pixels, and - when
                      the reading holds together as a ladder - what the ticks SAY
    never proposed    what a series MEANS, how many panels the figure has, and
                      whether any of the above is right

**The tick values are read here, and they are still not confirmed here.** A
printed 30 read as 3 rescales every value in the panel by ten - but "a person
types it" was never the only answer to that, and it was the expensive one.
`axis_reader.ladder` is: values must fall monotonically at a CONSTANT value per
pixel, so a single misread digit breaks the sequence and the reading is refused
rather than returned. Measured on this project's own corpus at 600 DPI, six
panels of one figure came back four read - all four correct, one of them only
because the ladder dropped a `9000` that should have been `5000` - and two
refused. None wrong. At 300 DPI the same six gave three, and one of those was
`3.05` for a printed `3.0`: resolution is the lever, and the ladder is the gate.

So the split moved. It is no longer "the machine measures pixels, the person
supplies numbers" but "the machine measures AND reads, the person LOOKS". The
read lands in its own columns (`Y_Tick_Read_*`) and never in the person's, the
overlay draws each value beside the tick it was read from, and a proposal is
CONFIRMED only when somebody who is named says the picture is right.

Everything it does emit is PROPOSED. `proposal_problems` refuses a proposal
that claims to be confirmed without a person behind it, exactly as the intake
draft does, and the overlay is what the person confirms against - the proposal
drawn on the raster it was measured from, so agreeing with it is agreeing with
a picture.

The detection is deterministic and boring on purpose: long dark runs are axis
lines, short marks against an axis are ticks, ink columns inside the frame are
where the marks stand. It reproduces, on the same page, the numbers this
project measured by hand for publication BF02919461 - which is the release
gate, because those numbers then read ten values to within 0.003 of a printed
table.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: What a proposal row carries. Pixels and counts, and the columns that say who
#: has looked at it. There is no column for a tick VALUE, a series name or a
#: panel count: this module has nothing to say about any of them.
PROPOSAL_COLUMNS = (
    "Proposal_ID", "Raster", "Raster_SHA256", "Region",
    "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1",
    "Axis_X_Region", "Axis_Y_Region",
    "Y_Tick_Pixels", "Y_Tick_Count", "Y_Tick_Spacing_Px", "Y_Tick_Regularity",
    "Y_Tick_Coverage",
    "X_Tick_Pixels", "X_Tick_Count",
    "Group_Anchor_Pixels", "Group_Anchor_Count",
    # THE SECOND ANCHOR READING, from the marks' shape rather than from where
    # the ink is. Reported beside the first and not instead of it: which one a
    # panel needs depends on what is drawn in it, and nothing has said that yet
    # when a geometry is proposed. Two readings that agree are evidence; one
    # arbitrated away is a choice nobody measured.
    "Box_Anchor_Pixels", "Box_Anchor_Count", "Box_Anchor_Detail",
    "Confidence", "Confidence_Reason",
    # WHAT THE MACHINE READ, in its own columns. Separate from the two below on
    # purpose: `Y_Tick_Top_Value` still means "a person read this axis", and a
    # PENDING row carrying one is still refused. A reading is not a confirmation,
    # and putting them in one column is how a machine's guess becomes a person's
    # answer without anybody deciding that it should.
    "Y_Tick_Read_Status", "Y_Tick_Read_Values",
    "Y_Tick_Read_First", "Y_Tick_Read_Last",
    "Y_Tick_Read_Residual_Px", "Y_Tick_Read_Detail",
    # WHAT THE TICK GRID SAYS ABOUT THE READING. A ladder is checked against the
    # rows OCR put the numerals on, with the slack those rows need, and a
    # misread that lands inside the slack passes: publication ASEM-P577's
    # `200 150 100 50 0` was read `190 100 20` and stood. The tick marks the
    # same proposal measured have no such slack, and nobody was asking them.
    # A warning, never a verdict: the reading stays, and the page puts the
    # panel in front of the person first.
    "Y_Tick_Read_Warning",
    # WHICH LINE THE AXIS WAS READ FROM, when it was not the frame's left edge.
    # `find_frame` returns the leftmost long rule in the region, and on a boxed
    # panel that is the box, with the plot's spine and its numerals inside it.
    # Reading from the inner rule rescues those panels - but it also means the
    # FRAME IS WRONG, and a person confirming values whose provenance is
    # invisible is confirming arithmetic again. So the line is named here and
    # drawn on the overlay. Empty means the frame's left edge, as always.
    "Y_Axis_Spine_X",
    # A NEIGHBOUR THIS PANEL MAY BE SHARING ITS AXIS WITH. This corpus prints a
    # row of panels with the y axis on the leftmost one and nothing on the
    # rest - Day/Night, left/right column - and those panels have no labels to
    # read and none for a person to type. What a person can say about one is
    # "it uses p7's axis", and that is a verdict of its own (`SHARED`, below),
    # not a pair of numbers. The machine only NAMES the neighbour whose frame
    # stands on the same rows; whether the axis is shared is what the person
    # decides, because a panel with its own unread axis looks the same from
    # here (publication S41467-023-41990-4's ECW panel: same row as ICW,
    # frame within 3 px, and four labels of its own).
    "Y_Axis_Shared_Candidate", "Y_Axis_Shared_Detail",
    "Human_Verification_Status", "Verified_By", "Verified_At",
    # 사람이 적은 두 수. 이름이 `First`/`Last`였고, 그것이 무엇의 처음인지
    # 아무 데도 적혀 있지 않았습니다. 축은 아래에서 시작하니 아래부터 적는
    # 것이 자연스럽고, 계산은 위부터 짝지었습니다 - FIG9 여섯 패널이 전부
    # 뒤집혀 돌아왔고 관문의 문 넷을 다 지났습니다. 뒤집힌 축은 이 코퍼스에
    # 실제로 있어서(`AXIS_INVERTED`) 뒤집힘 자체로는 막을 수 없습니다.
    # 이름이 위치를 말하면 물음에 애매한 데가 없습니다.
    "Y_Tick_Top_Value", "Y_Tick_Bottom_Value",
    # 계산이 실제로 쓰는 것: 값과 그 값이 붙은 픽셀 행의 짝, 둘.
    # 값만 받아 두고 픽셀은 `Y_Tick_Pixels`의 양 끝이라고 짐작하던 것이
    # 두 번째 결함이었습니다 - 리더의 사다리가 눈금 전부를 읽지 못하면
    # (GP001은 6개 중 5개, GP002는 5개 중 3개) 리더가 말한 값은 읽은
    # 눈금의 끝인데 짝은 모든 눈금의 끝과 지어져, 축척이 20~50% 어긋난
    # 채로 잔차 0.1px에 앞뒤가 맞습니다.
    "Confirmed_Tick_Values",
    # 사람의 답 "이 패널은 <Proposal_ID>의 축을 씀". 판정이 SHARED일 때만
    # 채워지고, 짝은 그 패널의 확인된 짝을 관문이 옮겨 적습니다 - 같은
    # 래스터의 같은 픽셀 행이니 옮길 수 있고, 프레임이 어긋나 있으면 옮기지
    # 않습니다. 값 두 개는 비워 둡니다: 이 패널의 값이 아닙니다.
    "Y_Axis_Shared_With", "Note",
)

#: What `read_tick_values` can say. `REFUSED` is a reading that did not hold
#: together; `NOT_ATTEMPTED` is one nobody asked for. Neither is a gap to fill.
READ_OK = "READ"
READ_REFUSED = "REFUSED"
READ_NOT_ATTEMPTED = "NOT_ATTEMPTED"
READ_STATUSES = (READ_OK, READ_REFUSED, READ_NOT_ATTEMPTED)

PROPOSAL_PENDING = "PENDING"
PROPOSAL_SHARED = "SHARED"
PROPOSAL_STATUSES = (PROPOSAL_PENDING, "CONFIRMED", "REJECTED", PROPOSAL_SHARED)

#: How far apart two frames' top and bottom rows may stand, as a fraction of
#: the frame height, for one to be offered as the other's axis. Measured on the
#: 975-panel run: 40 refused panels have a read neighbour within 1%, 9 more
#: within 3%, and past that the frames are different rows of the figure.
SHARED_AXIS_TOLERANCE = 0.02

#: Below this a proposal is still a proposal, but it goes to the top of the
#: sheet. Same threshold and same meaning as the intake draft's.
LOW_CONFIDENCE = 0.6

#: A run of dark pixels this fraction of the region's width (or height) is an
#: axis line rather than a mark. Deliberately high: a bar can be wide and a
#: whisker can be tall, but neither spans the plot.
_AXIS_RUN = 0.55

#: A tick sticks out from its spine by at least this many pixels and at most
#: this many. Expressed against the SPINE, not against the page, so it does not
#: care what DPI the raster was rendered at.
_TICK_MIN_PX = 2
_TICK_MAX_PX = 14

#: Two tick candidates closer than this many pixels are one printed tick that
#: antialiasing split in two.
_TICK_MERGE_PX = 4

#: How long a tick may be, as a fraction of the axis it is drawn against. This
#: is the scale-free half of `_TICK_MAX_PX`, which is only a floor for a very
#: short axis.
_TICK_SPAN_FRACTION = 0.06

#: White this wide between a spine and a tick is antialiasing. Wider is the
#: gutter in front of the axis labels, and the walk must stop before them.
_TICK_GAP_PX = 2


def _s(v):
    return "" if v is None else str(v).strip()


def _gray(image):
    """A 2-D uint8 array from a path, a PIL image or an array."""
    if isinstance(image, np.ndarray):
        if image.ndim == 2:
            return image
        return np.asarray(image).mean(axis=2).astype(np.uint8)
    from PIL import Image
    if isinstance(image, str):
        image = Image.open(image)
    return np.asarray(image.convert("L"))


def _runs(indices, gap=1):
    """Consecutive-ish integers grouped into runs."""
    out, current = [], []
    for value in sorted(indices):
        if current and value - current[-1] > gap:
            out.append(current)
            current = []
        current.append(value)
    if current:
        out.append(current)
    return out


def find_frame(gray, region=None, threshold=160):
    """The plot frame inside a region, as (x0, x1, y0, y1) or None.

    The frame is the pair of longest horizontal runs and the pair of longest
    vertical runs. A panel drawn with only a left spine and a bottom axis - SPSS
    does this - has one of each, and that is still a frame: the other two edges
    are the region's own bounds, which is what a person would draw too.

    ONE LINE IS STILL A FRAME. The paragraph above promised the L-shape and
    the code below refused anything short of it: a panel with a left spine and
    no baseline - the middle rows of a stacked figure that shares one x axis -
    came back as no frame at all. That is 112 of the 145 panels this project's
    600 DPI corpus could not propose a geometry for (75 with only a spine, 37
    with only a baseline). With a spine the ticks are where they always were;
    with only a baseline there is no spine to find ticks on, and the proposal
    says so with a tick count of 0 rather than by not existing - a panel that
    is not on the sheet is a panel nobody decides about. No line at all is no
    frame: nothing printed marks where the plot is.
    """
    dark = _gray(gray) < threshold
    if region:
        rx0, ry0, rx1, ry1 = [int(v) for v in region]
    else:
        ry0, rx0 = 0, 0
        ry1, rx1 = dark.shape
    window = dark[ry0:ry1, rx0:rx1]
    if window.size == 0:
        return None
    height, width = window.shape
    rows = [i + ry0 for i, v in enumerate(window.sum(axis=1))
            if v >= width * _AXIS_RUN]
    cols = [j + rx0 for j, v in enumerate(window.sum(axis=0))
            if v >= height * _AXIS_RUN]
    if not rows and not cols:
        return None
    row_runs = [int(round(sum(r) / len(r))) for r in _runs(rows, gap=2)] if rows else []
    col_runs = [int(round(sum(c) / len(c))) for c in _runs(cols, gap=2)] if cols else []
    # An L-shaped axis is one horizontal line and one vertical one, which is
    # what SPSS prints and what publication BF02919461's right-hand panel is.
    # The missing edges are the region's own bounds - which is where a person
    # would put them too, because there is nothing else printed to put them at.
    # A single horizontal line is the baseline, so the top is the region's; a
    # single vertical line is the spine, so the right edge is the region's;
    # and no line on an axis at all means both of its edges are the region's.
    y0 = min(row_runs) if len(row_runs) > 1 else min(row_runs + [ry0])
    y1 = max(row_runs) if len(row_runs) > 1 else max(row_runs + [ry0 if row_runs else ry1 - 1])
    x0 = min(col_runs) if len(col_runs) > 1 else min(col_runs + [rx1 - 1 if col_runs else rx0])
    x1 = max(col_runs) if len(col_runs) > 1 else max(col_runs + [rx1 - 1])
    if y1 - y0 < 8 or x1 - x0 < 8:
        return None
    return (x0, x1, y0, y1)


def _reach(dark, spine, low, high, axis, sign, limit):
    """How far ink runs away from the spine, row by row (or column by column).

    Measured as a REACH rather than as ink inside a fixed strip, because a
    strip has a width and a width is a number in pixels: at 300 DPI a tick is
    five pixels long and at 600 it is ten, and a detector that asks "is this
    twelve-pixel strip mostly dark" answers no to both. The reach is compared
    against the spine's OWN thickness, which scales with the rendering exactly
    as the tick does.
    """
    out = []
    for k in range(low, high):
        n, blank = 0, 0
        for step in range(1, limit + 1):
            if axis == "Y":
                x = spine + sign * step
                inside = 0 <= x < dark.shape[1] and 0 <= k < dark.shape[0]
                ink = inside and dark[k, x]
            else:
                y = spine + sign * step
                inside = 0 <= y < dark.shape[0] and 0 <= k < dark.shape[1]
                ink = inside and dark[y, k]
            if not inside:
                break
            if ink:
                n += 1
                blank = 0
                continue
            # A pixel or two of white between a spine and its tick is
            # antialiasing, not the end of the tick. More than that is the
            # gutter before the axis LABELS, and the walk has to stop there or
            # every row reaches the text and no row is a tick.
            blank += 1
            if blank > _TICK_GAP_PX:
                break
        out.append(n)
    return np.asarray(out, dtype=int)


def find_ticks(gray, spine, low, high, axis="Y", threshold=160, reach=None):
    """Tick marks against a spine, as pixel positions along it.

    Returned in PIXELS ONLY. What they are worth is the one thing on a figure
    that no measurement can recover and that a mistake in is invisible
    downstream - a printed 30 typed as 3 rescales the panel by ten and leaves
    every check happy - so the values come from a person and this returns none.

    Ticks are looked for on BOTH sides of the spine, because a plot drawn by
    SPSS puts them inside and one drawn by matplotlib puts them outside, and
    neither is a property of the data. The side with more of them wins.
    """
    dark = _gray(gray) < threshold
    axis = axis.upper()
    # A TICK IS SHORT RELATIVE TO ITS AXIS, and that is the only scale-free way
    # to say it. `reach` was a constant fourteen pixels, which is a tick at 300
    # DPI and half a tick at 600 - the same defect the LINE_MONO marker limits
    # still carry, and the reason the same figure reads at one rendering and
    # not at another.
    if reach is None:
        reach = max(_TICK_MAX_PX, int(_TICK_SPAN_FRACTION * (int(high) - int(low))))
    limit = int(reach) + 4
    best = {}
    for sign in (-1, 1):
        profile = _reach(dark, int(spine), int(low), int(high), axis, sign,
                         limit)
        if profile.size == 0:
            continue
        # The spine's own bleed: what the reach is where there is no tick.
        floor = int(np.median(profile))
        hits = [i + int(low) for i, v in enumerate(profile)
                if floor + _TICK_MIN_PX <= v <= floor + int(reach)]
        if not hits:
            continue
        marks = [sum(r) / len(r) for r in _runs(hits, gap=_TICK_MERGE_PX)]
        if len(marks) > len(best.get("marks", [])):
            best = dict(marks=marks,
                        side=("OUTSIDE" if sign < 0 else "INSIDE"))
    return [round(m, 1) for m in best.get("marks", [])], best.get("side", "")


def tick_regularity(marks):
    """How evenly spaced the ticks are, and by how much, in pixels.

    Returned rather than judged. A regular ladder is what lets a person supply
    only the FIRST and LAST value and have the rest follow; an irregular one
    means either the detection is wrong or the axis is broken (a `//` gap), and
    both are things to look at rather than to average away.
    """
    if len(marks) < 3:
        return 0.0, 0.0
    gaps = np.diff(np.asarray(marks, dtype=float))
    spacing = float(np.median(gaps))
    if spacing <= 0:
        return 0.0, 0.0
    worst = float(np.max(np.abs(gaps - spacing)))
    return round(spacing, 2), round(worst / spacing, 3)


#: Two ink clusters separated by less than this fraction of the plot width are
#: one group - the two edges of one outlined bar, or the bars of one cluster.
_GUTTER_FRACTION = 0.035

#: A cluster with nothing in it this tall is not where a mark stands.
_ANCHOR_TALL_FRACTION = 0.06

#: How far inside the frame the plot area starts, as a fraction of the panel.
#: The frame's own stroke is a tall ink column and would be read as a group.
_FRAME_INSET_FRACTION = 0.01


#: A horizontal run shorter than this share of the panel is a tick, a dot's
#: middle row or a letter; longer than this is the frame or a grid rule. Neither
#: end is a mark whose centre means a category.
MARK_MIN_SHARE = 0.02
MARK_MAX_SHARE = 0.40

#: A box draws its width at its TOP and again at its BOTTOM, with the plot's
#: background between them. That separation is the whole discriminator: a
#: scattered point is one band of rows and a box is two or three.
MARK_MIN_BANDS = 2

#: And the width has to occur at this many places across the panel. One is a
#: legend swatch or a p-value underline; a categorical axis has groups.
MARK_MIN_GROUPS = 2


def find_box_anchors(gray, box, threshold=160):
    """(centres, detail) - x pixels of OUTLINED marks: box plots, mostly.

    `find_group_anchors` looks for columns with ink in them, which is what a bar
    chart is. It does not find a box plot: this corpus draws boxes with points
    scattered over them, and the points put ink in every column, so what comes
    back is one anchor or three - never the five that are printed. FIG9 of
    publication S41467 is six panels of exactly that, and none of them reads.

    A BOX IS FOUND BY THE SHAPE OF ITS RULES. It draws a horizontal run of the
    SAME width at its top, at its median and at its bottom, with the plot's
    background between them. A scattered point does not: a circle's run is narrow
    at the top, widest in the middle and narrow again, so the rows that match any
    one width are a SINGLE band. Two separated bands of one width is the test,
    and it is what tells a box from the dots drawn on it.

    Widest first, not commonest. The points outnumber the boxes many times over
    on this corpus, and a mark that carries a value is drawn wider than the dots
    scattered on it. Measured on all six panels of that FIG9: exactly five
    centres in every one, evenly spaced, each under its printed category label.

    A FILLED bar is one band, not two, and is not found here - that is
    `find_group_anchors`'s panel. Neither is a line panel, and neither is a panel
    whose widest outline is drawn once: one mark is not a categorical axis, and a
    category put where the figure has none is a wrong number rather than a
    missing one. In every one of those cases this returns ([], why) rather than
    carry on to a narrower width, because the narrower width is the points.
    """
    gray = _gray(gray)
    x0, x1, y0, y1 = [int(v) for v in box]
    span = x1 - x0
    if span <= 0 or y1 - y0 <= 0:
        return [], "the panel has no area to look in"
    inside = gray[y0 + 1:y1, x0 + 1:x1] < threshold
    tolerance = max(3, int(0.01 * span))
    low, high = MARK_MIN_SHARE * span, MARK_MAX_SHARE * span
    seen = []
    for row in range(inside.shape[0]):
        for start, end in _row_runs(inside[row]):
            if low <= end - start <= high:
                seen.append((end - start, (start + end) / 2.0, row))
    if not seen:
        return [], "no horizontal run of a mark's width inside the panel"
    for width in sorted({int(round(w / 4.0)) * 4 for w, _c, _r in seen}, reverse=True):
        at_width = sorted((c, r) for w, c, r in seen if abs(w - width) <= tolerance)
        kept = [g for g in _cluster(at_width, tolerance)
                if len(_bands([r for _c, r in g])) >= MARK_MIN_BANDS]
        if not kept:
            continue
        # THE WIDEST OUTLINE IS THE ANSWER OR THERE ISN'T ONE. Carrying on to
        # narrower widths is a search, and what it finds is the points: a column
        # of scattered dots is also same-width runs at separated rows, and there
        # are more of them than there are boxes. Measured on all six panels of
        # S41467's FIG9 the widest outline is the box every time, so the next
        # width down is not a second chance - it is a different mark.
        if len(kept) < MARK_MIN_GROUPS:
            return [], ("the widest outlined mark (about %d px) is drawn in %d "
                        "place, and one mark is not a categorical axis"
                        % (width, len(kept)))
        return ([round(sum(c for c, _r in g) / len(g) + x0 + 1, 1) for g in kept],
                "%d outlined marks about %d px wide" % (len(kept), width))
    return [], ("no width is drawn as %d separated rules anywhere in the panel"
                % MARK_MIN_BANDS)


def _cluster(points, tolerance):
    """[(centre, row)] grouped by centre, splitting where the gap exceeds `tolerance`."""
    out, current = [], []
    for centre, row in points:
        if current and centre - current[-1][0] > tolerance:
            out.append(current)
            current = []
        current.append((centre, row))
    if current:
        out.append(current)
    return out


def _bands(rows, gap=2):
    """Row numbers grouped into the separated horizontal rules they came from."""
    return _runs(sorted(set(int(r) for r in rows)), gap=gap)


def _row_runs(mask):
    """[(start, end)] of the True runs in one row. End is exclusive."""
    out, start = [], None
    for i, on in enumerate(mask):
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def find_group_anchors(gray, box, threshold=160, min_fraction=0.004):
    """Where the marks stand, as x pixels inside the plot area.

    A bar's body and an error bar's stem are both tall ink columns, so the same
    measurement finds a bar chart's groups and a point plot's positions. What
    it does NOT do is say how many groups there should be: a group the reader
    misses is a cell the grid gate reports missing, and a group invented here
    would be a cell nobody can account for.
    """
    dark = _gray(gray) < threshold
    x0, x1, y0, y1 = [int(v) for v in box]
    # Inset off the frame by a FRACTION of the panel, not by two pixels. The
    # spine is one pixel thick at 150 DPI and four at 600, and a two-pixel
    # inset leaves the thick one inside the plot area - where it is a very tall
    # ink column, which is exactly what an anchor looks like.
    inset_x = max(2, int((x1 - x0) * _FRAME_INSET_FRACTION))
    inset_y = max(1, int((y1 - y0) * _FRAME_INSET_FRACTION))
    inner = dark[y0 + inset_y:y1 - inset_y, x0 + inset_x:x1 - inset_x]
    if inner.size == 0:
        return []
    counts = inner.sum(axis=0)
    # A GROUP, not a stroke. An outlined bar is two tall columns with a mostly
    # empty middle and a hatched one is dozens; a whisker is one. What they
    # have in common is that a group is ink with white on both sides of it, so
    # the cluster is bounded by columns with essentially nothing in them and
    # the anchor is its ink-weighted centre. For BAR_MONO that IS the group
    # anchor the reader wants, slots and all.
    # ANY ink, not a tall column. An outlined bar is two tall edges with a
    # single-row top between them; requiring height per column splits it into
    # two anchors, one per edge. Requiring only that the column is not empty
    # keeps the bar whole, and the gutter below is what separates one group
    # from the next.
    need = max(1, int(inner.shape[0] * min_fraction))
    hits = [j + x0 + inset_x for j, v in enumerate(counts) if v >= need]
    if not hits:
        return []
    gutter = max(3, int((x1 - x0) * _GUTTER_FRACTION))
    # A cluster is kept only if SOMETHING in it stands up. Joining columns on
    # any ink at all keeps an outlined bar whole, and would also keep the axis
    # caption printed inside the frame; requiring one tall column in the
    # cluster is what tells a mark from a smudge, and it is a fraction of the
    # panel rather than a pixel count.
    tall = max(3, int(inner.shape[0] * _ANCHOR_TALL_FRACTION))
    out = []
    for run in _runs(hits, gap=gutter):
        weight = [int(counts[j - x0 - inset_x]) for j in run]
        # The centre of what STANDS UP in the cluster, not of the cluster. A
        # significance star or an "N = 5" printed next to a bar joins its
        # cluster - they are closer together than the gutter - and averaging it
        # in drags the anchor several pixels off the bar it is supposed to
        # name. A cluster with nothing tall in it is not a mark at all.
        standing = [(j, w) for j, w in zip(run, weight) if w >= tall]
        if not standing:
            continue
        total = sum(w for _j, w in standing)
        out.append(round(sum(j * w for j, w in standing) / total, 1))
    return out


def ladder_coverage(marks, low, high):
    """How much of the axis the tick ladder spans, 0 to 1.

    The hazard this exists for is silent. A person supplies the FIRST and LAST
    tick value, so a ladder that lost its end ticks - which happens the moment
    ticks are drawn INSIDE a boxed frame, because the corner tick and the frame
    line are the same ink - is still perfectly regular, still gets two numbers
    typed against it, and calibrates the panel against the wrong two rows. Even
    spacing cannot catch it. Coverage can.
    """
    if len(marks) < 2 or high <= low:
        return 0.0
    return round((max(marks) - min(marks)) / float(high - low), 3)


def _confidence(frame, y_ticks, regularity, anchors, region, coverage=1.0):
    """How much of a panel this looks like, and why in words."""
    score, reasons = 1.0, []
    if frame is None:
        return 0.0, "no plot frame was found in this region"
    if coverage < 0.9:
        score -= 0.3
        reasons.append("the tick ladder spans only %.0f%% of the axis, so its "
                       "end ticks are probably not the ones a person would "
                       "read the first and last value off" % (coverage * 100))
    if len(y_ticks) < 3:
        score -= 0.4
        reasons.append("only %d y tick(s) were found, so the axis cannot be "
                       "read off a first and last value" % len(y_ticks))
    if regularity > 0.08:
        score -= 0.3
        reasons.append("the y ticks are uneven by %.0f%% of their spacing, "
                       "which is either a broken axis or a misdetection"
                       % (regularity * 100))
    if not anchors:
        score -= 0.3
        reasons.append("no group anchors were found inside the frame")
    elif len(anchors) > 24:
        score -= 0.2
        reasons.append("%d anchor columns were found, which is more groups "
                       "than a panel usually has" % len(anchors))
    if region:
        rx0, ry0, rx1, ry1 = [float(v) for v in region]
        area = max(1.0, (rx1 - rx0) * (ry1 - ry0))
        covered = (frame[1] - frame[0]) * (frame[3] - frame[2]) / area
        if covered < 0.25:
            score -= 0.2
            reasons.append("the frame fills only %.0f%% of the region it was "
                           "looked for in" % (covered * 100))
    return max(0.0, round(score, 2)), "; ".join(reasons)


def propose_panel(image, region=None, proposal_id="GP001", raster_path="",
                  raster_sha256="", threshold=160):
    """One PROPOSED row for one panel-shaped region, or None if there is none.

    `region` is where to look, not what to measure: the frame inside it is what
    becomes the panel box. Intake's `Figure_BBox` is a fine region and so is a
    rectangle somebody dragged.
    """
    gray = _gray(image)
    if region is None:
        region = (0, 0, gray.shape[1], gray.shape[0])
    frame = find_frame(gray, region, threshold=threshold)
    if frame is None:
        return None
    x0, x1, y0, y1 = frame
    y_marks, _y_side = find_ticks(gray, x0, y0 - 2, y1 + 3, axis="Y",
                                  threshold=threshold)
    x_marks, _x_side = find_ticks(gray, y1, x0 - 2, x1 + 3, axis="X",
                                  threshold=threshold)
    spacing, regularity = tick_regularity(y_marks)
    coverage = ladder_coverage(y_marks, y0, y1)
    anchors = find_group_anchors(gray, frame, threshold=threshold)
    boxes, boxes_why = find_box_anchors(gray, frame, threshold=threshold)
    score, why = _confidence(frame, y_marks, regularity, anchors, region,
                             coverage=coverage)
    rx0, ry0, rx1, ry1 = [int(v) for v in region]
    row = {c: "" for c in PROPOSAL_COLUMNS}
    row.update({
        "Proposal_ID": proposal_id,
        "Raster": raster_path, "Raster_SHA256": raster_sha256,
        "Region": "%d,%d,%d,%d" % (rx0, ry0, rx1, ry1),
        "Panel_X0": x0, "Panel_X1": x1, "Panel_Y0": y0, "Panel_Y1": y1,
        # The label strips, as a region for the reviewer's crop. Bounded by the
        # frame and the region, never guessed past them.
        "Axis_Y_Region": "%d,%d,%d,%d" % (rx0, x0, y0, y1),
        "Axis_X_Region": "%d,%d,%d,%d" % (x0, x1, y1, ry1),
        "Y_Tick_Pixels": ";".join("%g" % m for m in y_marks),
        "Y_Tick_Count": len(y_marks),
        "Y_Tick_Spacing_Px": spacing or "",
        "Y_Tick_Regularity": regularity or "",
        "Y_Tick_Coverage": coverage,
        "X_Tick_Pixels": ";".join("%g" % m for m in x_marks),
        "X_Tick_Count": len(x_marks),
        "Group_Anchor_Pixels": ";".join("%g" % a for a in anchors),
        "Group_Anchor_Count": len(anchors),
        "Box_Anchor_Pixels": ";".join("%g" % a for a in boxes),
        "Box_Anchor_Count": len(boxes),
        "Box_Anchor_Detail": boxes_why,
        "Confidence": "%.2f" % score, "Confidence_Reason": why,
        # MEASURED, NOT READ. `read_tick_values` is a separate call because the
        # reading needs tesseract and the measurement does not: a machine with no
        # OCR still proposes a usable geometry, and says so here rather than
        # leaving a blank that reads as "refused".
        "Y_Tick_Read_Status": READ_NOT_ATTEMPTED,
        # The only status this module may write.
        "Human_Verification_Status": PROPOSAL_PENDING,
    })
    return row


def values_from_ladder(pairs, ticks=()):
    """(status, kept, detail) - what a set of read (value, pixel) pairs may become.

    Split out from the reading so the whole guard can be exercised without an
    OCR engine: what is under test here is not whether tesseract saw a `5`, but
    what this module does with what it saw.

    `axis_reader.ladder` is the test. It accepts three or more values falling (or
    rising) monotonically at a CONSTANT value per pixel, so a single misread
    digit breaks the sequence, and when the full set fails it retries on
    contiguous subsets and names what it dropped.

    THE KEPT RUN IS WHAT COMES BACK, not everything that was read. On this
    project's own FIG9 the subset dropped a `9000` printed `5000`; returning all
    the pairs put that 9000 on the overlay in the reader's colour, where a person
    confirming the picture would have confirmed the one value the calibration
    threw away. The run is re-checked here with subsetting OFF, because a run
    that only holds as somebody else's subset is not a ladder.
    """
    import axis_reader as A                                 # noqa: PLC0415
    ok, detail, first, last, residual, _cv = A.ladder(pairs)
    if not ok:
        return READ_REFUSED, [], detail, None
    kept = pairs[pairs.index(first):pairs.index(last) + 1]
    # AND THE TICK GRID HAS THE LAST WORD. The reader's own search skips a
    # ladder the grid contradicts and looks further; if what it hands back is
    # still one - nothing better was found - it is refused HERE, with the
    # grid's reason on the row, rather than proposed as a reading. ASEM-P577's
    # `190 100 20` is a ladder by 6.4% and a misread by 11.8% per tick.
    verdict, why = A.grid_verdict(kept, ticks)
    if verdict == A.GRID_CONTRADICTED:
        return READ_REFUSED, [], "%s; %s" % (why, detail), None
    return READ_OK, kept, detail, residual


def read_tick_values(image, row):
    """Read what this panel's y axis SAYS, or refuse. Never confirm.

    The reader is `axis_reader`: it crops the label strip beside the spine, asks
    tesseract for the numerals, and hands the pairs to `values_from_ladder`.
    Returns the row, updated in place. `Y_Tick_Read_*` only; the person's two
    columns are not touched here and no status is changed.
    """
    import axis_reader as A                                 # noqa: PLC0415

    row.setdefault("Y_Tick_Read_Status", READ_NOT_ATTEMPTED)
    try:
        box = (int(row["Panel_X0"]), int(row["Panel_X1"]),
               int(row["Panel_Y0"]), int(row["Panel_Y1"]))
    except (KeyError, TypeError, ValueError):
        row["Y_Tick_Read_Status"] = READ_REFUSED
        row["Y_Tick_Read_Detail"] = "the proposal carries no panel box to read against"
        return row
    _grey, dark = A._dark(image)
    spine_x, baseline_y = A.spine_and_baseline(dark, box)
    ticks = tick_rows_of(row)
    pairs = A.y_tick_labels(image, dark, box, spine_x, baseline_y, ticks=ticks)
    status, kept, detail, residual = values_from_ladder(pairs, ticks)
    read_box, read_spine, read_base = box, spine_x, baseline_y
    if status != READ_OK:
        # THE FRAME'S LEFT EDGE WAS NOT THE AXIS. Only when the first read
        # refused, so the 660 panels that read from the frame read exactly as
        # before: a second question asked of a panel that came up empty, like
        # the Otsu threshold and the second OCR pass. 27 of this corpus's 282
        # refusals are panels whose numerals sit inside their own frame.
        inner = A.inner_spine(dark, box)
        if inner is not None:                    # `inner_spine`이 프레임 변은 돌려주지 않는다
            inner_base = A.baseline_at(dark, box, inner)
            second = A.y_tick_labels(image, dark, (inner, box[1], box[2], box[3]),
                                     inner, inner_base, ticks=ticks)
            st2, kept2, detail2, resid2 = values_from_ladder(second, ticks)
            if st2 == READ_OK:
                row["Y_Axis_Spine_X"] = "%d" % inner
                inner_box = (inner, box[1], box[2], box[3])
                status, kept, residual = st2, kept2, resid2
                detail = ("%s; READ FROM THE RULE AT x=%d, not the frame's "
                          "left edge at x=%d - the frame is wider than the plot"
                          % (detail2, inner, box[0]))
                read_box, read_spine, read_base = inner_box, inner, inner_base
    if status == READ_OK:
        # AND THEN THE BAND AT THE BASELINE, for the label standing on it.
        deeper = _label_on_the_baseline(image, dark, read_box, read_spine,
                                        read_base, kept, ticks)
        if deeper is not None:
            more, detail3 = deeper
            detail = ("%s; THE LABEL ON THE BASELINE was read from its own band "
                      "and joins the ladder: %d labels, where the strip search "
                      "read %d" % (detail3, len(more), len(kept)))
            kept = more
    apply_reading(row, status, kept, detail, residual)
    code, why = warn_reading(row)
    row["Y_Tick_Read_Warning"] = ("%s: %s" % (code, why)) if code else ""
    return row


def _label_on_the_baseline(image, dark, box, spine_x, baseline_y, kept, ticks=()):
    """(pairs, detail) with the baseline's own label added, or None.

    THE LABEL SITTING ON THE BASELINE IS THE ONE THE CROP CUTS, and on a y axis
    it is usually the 0. Only 63 of this corpus's 685 read panels had a 0 in
    their ladder; 306 more have one printed at the baseline that the strip
    search never saw whole. The 0 is the label worth the most: a bar chart's
    bars all START there, so without it every bar's base is read by
    extrapolation.

    IT IS NOT ACCEPTED FOR BEING WHERE A LABEL WOULD BE. The numeral read down
    there is put beside the labels already read and handed to `ladder` with no
    subsets allowed: it has to fall on the same value-per-pixel line as all of
    them or it is not this axis's label. That is the test the rest of the
    reading passed, applied to one more point - not a comparison against what
    the ladder predicts, which would accept whatever agreed with it.
    """
    import axis_reader as A                                 # noqa: PLC0415

    if len(kept) < 2:
        return None
    # 어느 행이 축의 아래 끝인가. 크롭의 아래 경계와 같은 셈법입니다 - 틀의
    # 밑변과 잰 밑선 중 아래쪽. `spine_and_baseline`은 상자 틀에서 위 변을
    # 돌려주기도 하고, 그때 틀의 밑변이 축의 끝입니다.
    base_row = max(float(box[3]), float(baseline_y) if baseline_y is not None else 0.0)
    rows = sorted(r for _v, r in kept)
    gaps = [b - a for a, b in zip(rows, rows[1:])]
    pitch = sorted(gaps)[len(gaps) // 2]
    if pitch <= 0 or base_row - rows[-1] < 0.5 * pitch:
        # 이미 밑선까지 읽었습니다. 그 아래에는 라벨이 설 자리가 없습니다.
        return None
    for value, at in A.label_near(image, dark, box, spine_x, base_row,
                                  half=int(pitch * 0.55)):
        # 이미 읽은 행의 숫자를 다시 넣어도 `ladder`가 거릅니다 - 같은 행에 둘이
        # 서거나, 2px 떨어진 두 라벨이 값/픽셀을 무너뜨립니다.
        more = sorted(list(kept) + [(value, at)], key=lambda p: p[1])
        ok, detail, _first, _last, _resid, _cv = A.ladder(more, allow_subset=False)
        if ok and A.grid_verdict(more, ticks)[0] != A.GRID_CONTRADICTED:
            return more, detail
    return None


def apply_reading(row, status, kept, detail, residual):
    """Write a reading into its OWN columns. Never into the person's two.

    Split from the reading for the same reason as `values_from_ladder`: this is
    where the line between what a machine read and what a person answered is
    actually drawn, and a line nobody can test is a line that moves. Only
    `Y_Tick_Read_*` is written here - `Y_Tick_Top_Value`, `Y_Tick_Bottom_Value`,
    `Verified_By`, `Verified_At` and `Human_Verification_Status` are not touched,
    whatever the reader saw.
    """
    row["Y_Tick_Read_Status"] = status
    row["Y_Tick_Read_Detail"] = detail
    if status != READ_OK:
        return row
    row["Y_Tick_Read_Values"] = ";".join("%g@%g" % (v, px) for v, px in kept)
    row["Y_Tick_Read_First"] = "%g" % kept[0][0]
    row["Y_Tick_Read_Last"] = "%g" % kept[-1][0]
    row["Y_Tick_Read_Residual_Px"] = ("%.2f" % residual) if residual is not None else ""
    return row


WARN_TICK_STEP = "TICK_STEP_UNEVEN"
WARN_OFF_THE_TICKS = "LABELS_OFF_THE_TICKS"


def tick_rows_of(row):
    """The tick rows a proposal measured, sorted - [] where it measured none."""
    out = []
    for part in _s(row.get("Y_Tick_Pixels")).split(";"):
        try:
            out.append(float(part))
        except ValueError:
            continue
    return sorted(out)


def warn_reading(row):
    """(code, detail) from putting a READ row's labels to its own tick grid,
    or ("", "") - a warning for the person, never a verdict on the reading.

    The grid's verdict is `axis_reader.grid_verdict`, and a reading the grid
    CONTRADICTS never gets this far: the reader skips it and `values_from_ladder`
    refuses what it could not replace. Two things remain to say. A ladder the
    grid contradicts that reached the row anyway - a shared axis copied in, a
    column edited by hand - is named (`TICK_STEP_UNEVEN`). And a ladder of the
    fewest labels accepted whose labels do not even sit on one grid was never
    checked against anything but itself: publication EDGELL-2012's `9 7 1`
    came from a strip beside a frame that was not the axis, one label 34 px
    off the other two (`LABELS_OFF_THE_TICKS`). Longer ladders off the grid
    are drift in the tick pitch over a long axis, and are left alone. Silence
    means "not measured", not "fine" - which is why this is a warning column
    and not a status.
    """
    import axis_reader as A                                 # noqa: PLC0415
    kept = read_values_of(row)
    verdict, why = A.grid_verdict(kept, tick_rows_of(row))
    if verdict == A.GRID_CONTRADICTED:
        return WARN_TICK_STEP, why
    if verdict == A.GRID_OFF and len(kept) <= A.MIN_LABELS:
        return WARN_OFF_THE_TICKS, why
    return "", ""


def read_values_of(row):
    """[(value, pixel)] a reading proposed for this row, or [] - never a gap.

    `REFUSED` and `NOT_ATTEMPTED` both come back empty, and they mean different
    things to a person and the same thing to a calibration: there is no reading
    here.
    """
    if _s(row.get("Y_Tick_Read_Status")).upper() != READ_OK:
        return []
    out = []
    for part in _s(row.get("Y_Tick_Read_Values")).split(";"):
        if not part or "@" not in part:
            continue
        value, pixel = part.split("@", 1)
        try:
            out.append((float(value), float(pixel)))
        except ValueError:
            continue
    return out


def _frame_of(row):
    try:
        return (float(row["Panel_X0"]), float(row["Panel_X1"]),
                float(row["Panel_Y0"]), float(row["Panel_Y1"]))
    except (KeyError, TypeError, ValueError):
        return None


def frames_share_rows(a, b, tolerance=SHARED_AXIS_TOLERANCE):
    """(True, px) when frame `a` stands on the same rows as frame `b`, else
    (False, px). `px` is the larger of the two edge differences."""
    fa, fb = _frame_of(a), _frame_of(b)
    if fa is None or fb is None:
        return False, None
    h = min(fa[3] - fa[2], fb[3] - fb[2])
    px = max(abs(fa[2] - fb[2]), abs(fa[3] - fb[3]))
    return (h > 0 and px <= tolerance * h), px


def shared_axis_candidates(rows):
    """Name, on each unread row, the nearest panel to its left on the same
    raster that stands on the same rows and has ticks of its own. Returns how
    many rows were given a candidate. Rows that read their own axis get none:
    they have one. Written into the machine's two columns only.

    The NEAREST with ticks, not the leftmost: a panel shares the axis printed
    beside it, and a row can hold two axes (two column pairs). A neighbour
    without ticks in between is skipped - it is sharing too."""
    by_raster = {}
    for row in rows:
        by_raster.setdefault(_s(row.get("Raster")), []).append(row)
    named = 0
    for row in rows:
        row.setdefault("Y_Axis_Shared_Candidate", "")
        row.setdefault("Y_Axis_Shared_Detail", "")
        if _s(row.get("Y_Tick_Read_Status")).upper() == READ_OK:
            continue
        me = _frame_of(row)
        if me is None:
            continue
        best = None
        for other in by_raster[_s(row.get("Raster"))]:
            if other is row:
                continue
            them = _frame_of(other)
            if them is None or them[1] > me[0] + 0.1 * (me[1] - me[0]):
                continue                                    # not to the left
            try:
                if int(float(other.get("Y_Tick_Count") or 0)) < 2:
                    continue                                # no axis to share
            except ValueError:
                continue
            same, px = frames_share_rows(row, other)
            if not same:
                continue
            if best is None or them[0] > best[1][0]:
                best = (other, them, px)                    # the nearest
        if best is None:
            continue
        other, _them, px = best
        own = int(float(row.get("Y_Tick_Count") or 0))
        row["Y_Axis_Shared_Candidate"] = _s(other.get("Proposal_ID"))
        row["Y_Axis_Shared_Detail"] = (
            "%s와 같은 행, 프레임 위아래 차 %.0f px%s"
            % (_s(other.get("Proposal_ID")), px,
               "; 이 패널에도 눈금 %d개가 있음" % own if own >= 2 else ""))
        named += 1
    return named


def proposal_problems(rows):
    """[(Proposal_ID, code, detail)] for a proposal that cannot be what it says.

    Checked when a proposal is READ, because the file goes to a person and
    comes back edited. What a person may change is the status, the two tick
    values, the note and their own name. What nobody may do is confirm a
    geometry without saying who they are, or leave a machine's `PENDING` beside
    the two numbers only a person can supply.
    """
    out, seen = [], set()
    by_id = dict((_s(r.get("Proposal_ID")), r) for r in rows)
    for row in rows:
        pid = _s(row.get("Proposal_ID"))
        if not pid:
            out.append(("", "PROPOSAL_ID_MISSING", "a row with no Proposal_ID"))
            continue
        if pid in seen:
            out.append((pid, "PROPOSAL_ID_DUPLICATE", pid))
        seen.add(pid)
        read = _s(row.get("Y_Tick_Read_Status")).upper()
        if read and read not in READ_STATUSES:
            out.append((pid, "PROPOSAL_READ_STATUS_UNKNOWN",
                        "%r is not %s" % (read, "/".join(READ_STATUSES))))
        elif read == READ_OK and not read_values_of(row):
            # A row that says it read the axis and carries nothing is worse than
            # one that refused: the refusal sends a person to the axis and this
            # sends them past it.
            out.append((pid, "PROPOSAL_READ_WITHOUT_VALUES",
                        "%s says the axis was READ and carries no values" % pid))
        status = _s(row.get("Human_Verification_Status")).upper()
        if status not in PROPOSAL_STATUSES:
            out.append((pid, "PROPOSAL_STATUS_UNKNOWN",
                        "%r is not %s" % (status, "/".join(PROPOSAL_STATUSES))))
            continue
        who = _s(row.get("Verified_By"))
        when = _s(row.get("Verified_At"))
        top = _s(row.get("Y_Tick_Top_Value"))
        bottom = _s(row.get("Y_Tick_Bottom_Value"))
        pairs = _s(row.get("Confirmed_Tick_Values"))
        shared = _s(row.get("Y_Axis_Shared_With"))
        if status == PROPOSAL_PENDING:
            if who or when:
                out.append((pid, "PROPOSAL_PENDING_WITH_A_VERIFIER",
                            "%s is still PENDING and names %s"
                            % (pid, who or when)))
            if top or bottom or pairs:
                out.append((pid, "PROPOSAL_PENDING_WITH_A_TICK_VALUE",
                            "%s carries a tick value and nobody has read the "
                            "axis" % pid))
            if shared:
                # The machine's candidate has its own column. This one is a
                # person's answer, and nobody has answered.
                out.append((pid, "PROPOSAL_PENDING_WITH_A_SHARED_AXIS",
                            "%s says it uses %s's axis and nobody has said so"
                            % (pid, shared)))
            continue
        if not who or not when:
            out.append((pid, "PROPOSAL_VERDICT_UNATTRIBUTED",
                        "%s says %s and does not say who or when"
                        % (pid, status)))
        if status == PROPOSAL_SHARED:
            # "This panel uses that one's axis." The target must be a panel,
            # not itself, on the same raster, standing on the same rows - the
            # pairs are pixel rows, and rows only carry across a raster.
            if not shared:
                out.append((pid, "PROPOSAL_SHARED_WITHOUT_A_TARGET",
                            "%s is SHARED and names no panel" % pid))
            elif shared == pid:
                out.append((pid, "PROPOSAL_SHARED_WITH_ITSELF", pid))
            elif shared in by_id:
                target = by_id[shared]
                if _s(target.get("Raster")) != _s(row.get("Raster")):
                    out.append((pid, "PROPOSAL_SHARED_ACROSS_RASTERS",
                                "%s is on %s and %s on %s"
                                % (pid, _s(row.get("Raster")), shared,
                                   _s(target.get("Raster")))))
                else:
                    same, px = frames_share_rows(row, target)
                    if not same:
                        out.append((pid, "PROPOSAL_SHARED_FRAME_MISALIGNED",
                                    "%s's frame is %s px off %s's; its tick "
                                    "rows are not this panel's"
                                    % (pid, "%.0f" % px if px is not None else "?", shared)))
            if top or bottom:
                out.append((pid, "PROPOSAL_SHARED_WITH_A_TICK_VALUE",
                            "%s uses %s's axis and carries a value of its own"
                            % (pid, shared)))
            got = pairs_of(row)
            if got and (len(got) != 2 or got[0][1] == got[1][1]):
                out.append((pid, "PROPOSAL_CALIBRATION_PAIRS_MISSING",
                            "%s carries %d value@pixel pair(s)" % (pid, len(got))))
            continue
        if shared:
            out.append((pid, "PROPOSAL_%s_NAMES_A_SHARED_AXIS" % status,
                        "%s is %s and also says it uses %s's axis; it is one "
                        "or the other" % (pid, status, shared)))
        if status != "CONFIRMED":
            continue
        # The two numbers the whole split exists for.
        for label, value in (("Y_Tick_Top_Value", top),
                             ("Y_Tick_Bottom_Value", bottom)):
            try:
                float(value)
            except ValueError:
                out.append((pid, "PROPOSAL_TICK_VALUE_MISSING",
                            "%s is CONFIRMED with %s=%r; what the axis says is "
                            "the one thing a raster cannot be asked"
                            % (pid, label, value)))
        if top and bottom and top == bottom:
            out.append((pid, "PROPOSAL_TICK_VALUES_EQUAL",
                        "%s says the top and bottom tick are both %s, which is "
                        "not an axis" % (pid, top)))
        # AND THE PAIRS THE CALIBRATION ACTUALLY USES. Two numbers alone leave
        # the pixels to be guessed, and the guess was `Y_Tick_Pixels`'s two ends
        # - which are the right ticks only when whoever answered was answering
        # about those two. The reader usually is not: its ladder covered five of
        # six ticks on this project's own FIG9, and pairing its last value with
        # the last tick made that panel's scale 20% wrong with a 0.1 px residual.
        got = pairs_of(row)
        if len(got) != 2:
            out.append((pid, "PROPOSAL_CALIBRATION_PAIRS_MISSING",
                        "%s is CONFIRMED and carries %d value@pixel pair(s); a "
                        "calibration is two, and which ticks they are cannot be "
                        "guessed from the tick list" % (pid, len(got))))
        elif got[0][1] == got[1][1]:
            out.append((pid, "PROPOSAL_CALIBRATION_PAIRS_ONE_ROW",
                        "%s pins both values to pixel row %g" % (pid, got[0][1])))
        elif got[0][0] == got[1][0]:
            out.append((pid, "PROPOSAL_CALIBRATION_PAIRS_ONE_VALUE",
                        "%s pins the same value %g to two rows" % (pid, got[0][0])))
    return out


def pairs_of(row):
    """[(value, pixel)] a CONFIRMED row's calibration stands on, or []."""
    return _parse_pairs(_s(row.get("Confirmed_Tick_Values")))


def _parse_pairs(text):
    out = []
    for part in str(text or "").split(";"):
        if not part or "@" not in part:
            continue
        value, pixel = part.split("@", 1)
        try:
            out.append((float(value), float(pixel)))
        except ValueError:
            continue
    return out


def calibration_from(row):
    """[[value, pixel], [value, pixel]] for a CONFIRMED or SHARED proposal, or None.
    A SHARED row's pairs are its neighbour's, copied by the record gate after
    the frames were checked; a SHARED row that has not been through the gate
    carries none and calibrates nothing.

    The join between the two halves, and it reads the pixels rather than
    guessing them. It used to take the value columns and pair them with
    `Y_Tick_Pixels`'s two ends - which is right only when the answer was ABOUT
    those two ticks. The reader's answer usually is not: on this project's own
    FIG9 its ladder covered five of six ticks on one panel and three of five on
    another, and pairing its last value with the last tick put those panels 20%
    and 50% off with a ladder residual of 0.1 px and no complaint anywhere.

    So the pairs are carried, not inferred, and a row without them is refused
    rather than calibrated on a guess.
    """
    if _s(row.get("Human_Verification_Status")).upper() not in ("CONFIRMED", PROPOSAL_SHARED):
        return None
    pairs = pairs_of(row)
    if len(pairs) != 2 or pairs[0][1] == pairs[1][1]:
        return None
    return [[pairs[0][0], pairs[0][1]], [pairs[1][0], pairs[1][1]]]


def write_proposals(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(PROPOSAL_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in PROPOSAL_COLUMNS})
    return path


def _font(size):
    """A font that is actually `size` px tall, or the default if none is installed.

    `ImageDraw.text` without a font is 11 px whatever the raster is, and a
    proposal overlay is read at the raster's own scale.
    """
    from PIL import ImageFont
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:                               # pragma: no cover
                continue
    return ImageFont.load_default()


def proposal_overlay(image, row, out_path, shared_ticks=None):
    """The proposal drawn on the raster it was measured from.

    `shared_ticks` are the tick rows of the panel `Y_Axis_Shared_Candidate`
    names, drawn across this panel's spine in a colour of their own, so the
    person deciding "does this panel use that axis" sees whether that axis's
    ticks land on this panel's gridlines and frame.

    This is the artifact a person confirms against. Confirming a geometry from
    four numbers in a CSV is agreeing with arithmetic; confirming it from the
    frame drawn on the figure is looking at the figure - and the axis labels
    stay in the picture, because reading them is the job.
    """
    from PIL import Image, ImageDraw
    base = image if isinstance(image, Image.Image) else Image.open(image)
    canvas = base.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x0, x1 = int(row["Panel_X0"]), int(row["Panel_X1"])
    y0, y1 = int(row["Panel_Y0"]), int(row["Panel_Y1"])
    draw.rectangle((x0, y0, x1, y1), outline=(200, 30, 30), width=2)
    # THE LINE THE VALUES WERE READ FROM, when it was not the frame's left edge.
    # Drawn in the reader's own magenta, because that is what this overlay means
    # by "the machine read this": the values beside it were read from THIS line,
    # and the red frame around them is wider than the plot.
    spine = _s(row.get("Y_Axis_Spine_X"))
    if spine:
        sx = int(float(spine))
        draw.line((sx, y0, sx, y1), fill=(190, 60, 190), width=3)
        x0 = sx
    for y in (shared_ticks or []):
        y = int(float(y))
        for xx in range(x0 - 30, x0 + 31, 6):
            draw.line((xx, y, xx + 3, y), fill=(230, 120, 20), width=2)
    for mark in _s(row.get("Y_Tick_Pixels")).split(";"):
        if not mark:
            continue
        y = int(float(mark))
        draw.line((x0 - 18, y, x0 + 10, y), fill=(30, 90, 200), width=1)
    # WHAT THE READER SAYS EACH TICK IS, beside the tick it was read from. This
    # is what turns confirming into looking: a person who can see `2.6` printed
    # on the axis and `2.6` written next to it has checked the reading, and one
    # who sees `3.05` beside a printed `3.0` has caught it.
    #
    # INSIDE the frame, not outside it. Written past the right edge it lands on
    # the neighbouring panel, which is where this was drawn first and where a
    # reader confirming panel 2 was shown panel 3's numbers.
    region = [int(v) for v in _s(row.get("Region")).split(",")] \
        if _s(row.get("Region")) else None
    reading = read_values_of(row)
    if reading:
        # SIZED TO THE PANEL. A 12 px default on a 4000 px raster is a smudge,
        # and the whole point is that the two numbers can be compared by eye.
        step = abs(reading[1][1] - reading[0][1]) if len(reading) > 1 else (y1 - y0) / 6.0
        # SIZED TO THE STEP, BUT CAPPED TO THE PANEL. Three labels spread over a
        # whole axis give a step of half the panel, and a number drawn at a
        # quarter of THAT covers the data it was drawn to vouch for:
        # publication S0094576511002189's panel read 1, -2, -3 across 2000 px
        # and the overlay wrote them 400 px tall, over the curve.
        size = max(11, min(int(step * 0.28), int((y1 - y0) * 0.05)))
        font = _font(size)
        for value, pixel in reading:
            y = int(float(pixel))
            draw.line((x0 - 22, y, x0 + 14, y), fill=(190, 60, 190), width=3)
            # ABOVE THE TICK LINE, not across it. Written across it, the text's
            # midline - where a minus sign is - lands on the tick line drawn
            # in the same colour, and `-0.9` shows as `0.9`: the one glyph
            # that flips every value in the panel is the one glyph a person
            # cannot see. Publication S0094576505000263's axis, -1 .. -0.3,
            # read correctly and was drawn without a single minus.
            # And inside the picture. The top tick sits at the frame's top
            # edge, and text written above it leaves through the crop: the
            # one value a confirmer most needs to see was the one cut in
            # half. Below the line for that tick, above it for the rest.
            ty = y - size - 3
            if region and ty < region[1]:
                ty = y + 4
            draw.text((x0 + 20, ty), "%g" % value,
                      fill=(190, 60, 190), font=font)
    # TWO READINGS, TWO COLOURS. Drawn the same, a person cannot tell which
    # detector put a line where, and "the anchors look right" stops being a
    # statement about anything.
    for anchor in _s(row.get("Group_Anchor_Pixels")).split(";"):
        if not anchor:
            continue
        x = int(float(anchor))
        draw.line((x, y0, x, y1), fill=(20, 150, 90), width=1)
    # BELOW THE BASELINE, in the reader's own colour. Drawn up inside the plot in
    # a colour of its own it was invisible: this corpus prints its box plots in
    # orange, and an orange anchor line on an orange box is a line nobody can
    # check. Under the axis is empty on every panel of it, and magenta is what
    # this module already means by "the machine read this".
    stub = max(4, (y1 - y0) // 30)
    for anchor in _s(row.get("Box_Anchor_Pixels")).split(";"):
        if not anchor:
            continue
        x = int(float(anchor))
        draw.line((x, y1, x, min(canvas.height - 1, y1 + stub)),
                  fill=(190, 60, 190), width=5)
    if region:
        # ENOUGH ROOM FOR WHAT IS DRAWN OUTSIDE THE FRAME. The anchor stubs hang
        # below the baseline, and a crop that cuts them off is a crop that hides
        # the reading it was made to show.
        pad = overlay_pad(row)
        ox, oy = overlay_origin(row)
        canvas = canvas.crop((ox, oy,
                              min(canvas.width, region[2] + pad),
                              min(canvas.height, region[3] + pad)))
    canvas.save(out_path)
    return out_path


def overlay_pad(row):
    """How far the overlay's crop reaches past the region, in raster pixels."""
    try:
        y0, y1 = int(row["Panel_Y0"]), int(row["Panel_Y1"])
    except (KeyError, TypeError, ValueError):
        return 12
    stub = max(4, (y1 - y0) // 30)
    return max(12, stub + 6)


def overlay_origin(row):
    """(x, y): where the overlay's top-left corner sits on the raster.

    The one place the crop is defined. The confirmation page lets a person
    point at a tick on the overlay, and the row they pointed at is a raster
    row only through this offset; a page that guessed it would put every
    pointed tick a pad's width off, with nothing to say so.
    """
    region = [int(v) for v in _s(row.get("Region")).split(",")] \
        if _s(row.get("Region")) else None
    if not region:
        return 0, 0
    pad = overlay_pad(row)
    return max(0, region[0] - pad), max(0, region[1] - pad)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("raster")
    ap.add_argument("--out", required=True)
    ap.add_argument("--region", action="append", default=[],
                    metavar="X0,Y0,X1,Y1",
                    help="where to look for a panel; repeatable. Without any, "
                         "the whole raster is one region")
    ap.add_argument("--threshold", type=int, default=160)
    ap.add_argument("--no-read", action="store_true",
                    help="measure only; do not read what the axis says")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    from PIL import Image
    image = Image.open(args.raster)
    import hashlib
    digest = hashlib.sha256(open(args.raster, "rb").read()).hexdigest()
    regions = [tuple(int(v) for v in r.split(",")) for r in args.region] or [None]
    rows = []
    for i, region in enumerate(regions, start=1):
        row = propose_panel(image, region, proposal_id="GP%03d" % i,
                            raster_path=os.path.basename(args.raster),
                            raster_sha256=digest, threshold=args.threshold)
        if row is None:
            print("no plot frame in region %s" % (region,))
            continue
        if not args.no_read:
            read_tick_values(image, row)
        rows.append(row)
        picture = proposal_overlay(image, row,
                                   os.path.join(args.out, "%s.png" % row["Proposal_ID"]))
        print("%s  box %s,%s,%s,%s  %s y ticks (spacing %s px, %s%% uneven)  "
              "%s anchors  confidence %s"
              % (row["Proposal_ID"], row["Panel_X0"], row["Panel_X1"],
                 row["Panel_Y0"], row["Panel_Y1"], row["Y_Tick_Count"],
                 row["Y_Tick_Spacing_Px"],
                 round(float(row["Y_Tick_Regularity"] or 0) * 100, 1),
                 row["Group_Anchor_Count"], row["Confidence"]))
        print("    %s" % picture)
        if row["Box_Anchor_Count"]:
            print("    %s" % row["Box_Anchor_Detail"])
        if row["Y_Tick_Read_Status"] == READ_OK:
            print("    axis reads %s .. %s (%s)"
                  % (row["Y_Tick_Read_First"], row["Y_Tick_Read_Last"],
                     row["Y_Tick_Read_Detail"]))
        elif row["Y_Tick_Read_Status"] == READ_REFUSED:
            print("    axis NOT read: %s" % row["Y_Tick_Read_Detail"])
        if row["Confidence_Reason"]:
            print("    %s" % row["Confidence_Reason"])
    path = write_proposals(os.path.join(args.out, "geometry_proposal.csv"), rows)
    print("wrote %s" % path)
    read = sum(1 for r in rows if r["Y_Tick_Read_Status"] == READ_OK)
    print("%d proposal(s), all PENDING; the axis was read on %d and refused on "
          "%d. Open each overlay: the frame, the tick rows, and - where it is "
          "drawn - what the reader says each tick is. Confirming is looking; "
          "type Y_Tick_Top_Value and Y_Tick_Bottom_Value where the reader "
          "refused or where the picture disagrees with it."
          % (len(rows), read, len(rows) - read))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
