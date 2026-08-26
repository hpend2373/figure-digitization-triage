#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A panel is a plot core, an owned label strip, and the axis both belong to.

Four rounds tried to fix one figure by changing an adoption criterion, and all
four were withdrawn.  The recorded diagnosis is that the distance gate is
load-bearing precisely because criterion 4 is not: publication 475's figure 2
comes out RIGHT because a label strip was wrongly adopted as data and the box it
widened happened to push mode selection the right way.  Reject the strip
honestly and the bar group goes with it.

So the strip stops being something a panel might win by adoption and becomes
something a panel OWNS by construction:

    plot_box      where marks are.  Mark detection, continuity, bar and line
                  reading all belong here
    label_box     everything on the LABEL SIDE of the axis that belongs to this
                  panel: the tick marks, the numerals, and the rotated axis
                  title.  Derived from the axis and bounded by the neighbouring
                  axis - never adopted, never a fragment
    numeral_band  the tighter strip inside it that OCR is pointed at, which is
                  what `label_band` already measures
    review_box    what a person is shown: the union
    signature     the physical axis: spine column, the run it occupies,
                  the baseline, and the ladder it read

OWNERSHIP AND OCR ARE TWO QUESTIONS, and running them together is what made the
first draft of this file report an empty strip on every one of the twelve real
panels it was pointed at.  `label_band` walks left from the axis and stops at
the first blank gutter, because a strip handed to tesseract must be tight.  On
publication 475's figure 2 the first ink left of the spine at x=105 is the tick
marks at 102-103; seven blank columns end the walk there, the measured band is
one pixel wide, and it is refused.  The numerals at 72-94 and the rotated title
at 37-54 are never reached.

    A tight strip is the right answer to "where do I read digits".  It is the
    wrong answer to "what does this panel own".  A panel owns its axis title as
    much as it owns its numerals - neither is data, both are its own - and the
    boundary is the NEIGHBOURING AXIS, not a gutter.

NOTHING HERE CHANGES A MEASUREMENT. This module is pure derivation from a box
that has already been found, and `propose.py` writes its output in NEW columns
beside `x0/x1/y0/y1` rather than instead of them. Replacing the box in the same
change that introduces three of them would make every downstream difference
unattributable, which is the failure the experiment harness exists to prevent.

The consumers, once they move, are named here rather than left implied:

    marks, bars, continuity   -> plot_box
    tick numerals, ladder     -> label_box + spine
    review overlay, crops     -> review_box
    identity, deduplication   -> signature
"""
import hashlib

import axis_reader as A

LEFT, RIGHT = "LEFT", "RIGHT"

#: How far into a neighbouring panel a strip may never reach. Not a tolerance on
#: the strip: a margin on the NEIGHBOUR, so that touching its edge is not the
#: same as owning the column beyond it.
NEIGHBOUR_MARGIN = 1


def _rows_overlap(nb, top, bottom):
    """Does this neighbour occupy any of the rows the strip would?

    A panel in the row ABOVE is not a neighbour of this strip, however close its
    columns are; only a panel beside it can take columns away from it.
    """
    if len(nb) < 4:
        return True
    return not (int(nb[3]) < top or int(nb[2]) > bottom)


def label_side(dark, box, spine_x, baseline_y):
    """Which side of the spine the numerals sit on.

    Decided by where the BASELINE runs, not by where ink is. Ink is a bad
    discriminator here - a sparse line plot can carry less ink than the column of
    numerals labelling it - but the x axis only extends across the data, so the
    side of the spine the baseline runs along is the plot side and the other side
    is the label side. A tie goes to LEFT, which is what a left-hand y axis is.
    """
    x0, x1, _y0, _y1 = box
    sx, by = int(spine_x), int(baseline_y)
    if by < 0 or by >= dark.shape[0]:
        return LEFT
    row = dark[by]
    left = int(row[max(0, int(x0)):sx].sum())
    right = int(row[sx + 1:min(dark.shape[1], int(x1))].sum())
    return LEFT if right >= left else RIGHT


def axis_extent(dark, box, spine_x):
    """(top, bottom) of the ink run in the spine column that this box sits on."""
    run = A.spine_run(dark, spine_x, box[2], box[3])
    return tuple(run) if run else (int(box[2]), int(box[3]))


def _band_right(dark, anchor, top, bottom, max_reach):
    """`label_band` walking the other way, for a right-hand y axis.

    The mirror is written out rather than folded into `label_band` with a step
    argument: that function is quoted verbatim in three places in the record for
    what it measures and why, and a signature change would silently reopen all
    of them.
    """
    a = int(anchor) + 2
    hi_lim = min(dark.shape[1] - 1, a + max_reach)
    t, b = int(max(0, top)), int(min(dark.shape[0], bottom))
    if b - t < 4 or a >= hi_lim:
        return None
    inked = [x for x in range(a, hi_lim + 1) if dark[t:b, x].any()]
    if not inked:
        return None
    left = min(inked)
    right = left
    blank = 0
    x = left + 1
    while x <= hi_lim:
        if dark[t:b, x].any():
            right = x; blank = 0
        else:
            blank += 1
            if blank >= A.LABEL_GAP:
                break
        x += 1
    if right - left < 3:
        return None
    if right - left > A.LABEL_BAND_MAX:
        return None
    return left - 2, right + 1


def label_strip(dark, box, spine_x, baseline_y, side=None, floor=None,
                neighbours=(), max_reach=None):
    """What this panel owns on the label side of its axis, or None.

    Ownership, not adoption, and not OCR.  The four clauses are the contract:

        it is on the label side of the axis
        it spans the axis run vertically - a strip beside nothing is not a strip
          for this panel, and it stops at the caption floor
        it reaches as far as there is ink that overlaps that run, within reach
        it does not cross into a neighbouring panel

    The last clause is what makes this ownership rather than a search: two panels
    in a row cannot both own one column, and what separates them is the other
    panel's own extent rather than a distance.  The bound is the NEIGHBOUR'S FAR
    EDGE, not its spine: a panel to the left ends at its right-hand edge, and
    stopping at its spine instead hands its whole plot to the panel next door -
    which is what the first version did, giving publication 475's figure 2 panel
    D a label box starting at x=427, inside panel C.  Nothing here asks whether the ink is a
    numeral - `numeral_band` asks that, and is allowed to fail without taking the
    ownership answer down with it.
    """
    x0, x1, y0, y1 = (int(v) for v in box)
    side = side or label_side(dark, box, spine_x, baseline_y)
    sx = int(spine_x)
    # REACH IS THE PANEL'S OWN WIDTH, not a number of pixels. `label_band` may
    # keep its 180 - it is looking for digits at a printed size - but a rule
    # about how far a panel's furniture can lie from its axis must give the same
    # answer on the same figure scanned at twice the resolution.
    if max_reach is None:
        max_reach = max(8, x1 - x0)
    top, bottom = axis_extent(dark, box, spine_x)
    top = max(top, y0)
    bottom = min(bottom, y1)
    if floor is not None:
        bottom = min(bottom, int(floor))
    if bottom - top < 4:
        return None

    near = [n for n in neighbours if _rows_overlap(n, top, bottom)]
    if side == LEFT:
        limit = max(0, sx - int(max_reach))
        for n in near:
            if int(n[1]) < sx:
                limit = max(limit, int(n[1]) + NEIGHBOUR_MARGIN)
        cols = [x for x in range(limit, sx) if dark[top:bottom, x].any()]
        if not cols:
            return None
        return (min(cols), sx, top, bottom)

    limit = min(dark.shape[1] - 1, sx + int(max_reach))
    for n in near:
        if int(n[0]) > sx:
            limit = min(limit, int(n[0]) - NEIGHBOUR_MARGIN)
    cols = [x for x in range(sx + 1, limit + 1) if dark[top:bottom, x].any()]
    if not cols:
        return None
    return (sx, max(cols), top, bottom)


def label_ink(dark, box, spine_x, baseline_y, side=None, floor=None):
    """(inked columns, nearest inked column to the spine) where numerals sit.

    NOT "can OCR read it" - "is there anything there to read". A grid figure
    prints its y axis numerals ONCE PER ROW and leaves the other panels a bare
    spine with tick marks: publication 177's figure 2 is five rows of three, and
    ten of its fifteen panels refuse the ladder because there is nothing printed
    beside them. Counting that as a failed reading is counting the figure's own
    layout as a defect, and it is what made the first draft of the provenance
    table read as "invented boxes have worse axes".

    Three bounds, all of them constants this file already has a use for:

        the AXIS RUN, not the box  - the x axis title sits below the run and is
                                     not a y numeral
        LABEL_BAND_MAX from spine  - past that is the neighbouring panel
        RULE_MAX_W beside it       - a tick mark is 1 to 4 columns of the axis
                                     itself, and every panel has them
    """
    x0, x1, y0, y1 = (int(v) for v in box)
    side = side or label_side(dark, box, spine_x, baseline_y)
    top, bottom = axis_extent(dark, box, spine_x)
    top, bottom = max(top, y0), min(bottom, y1)
    if floor is not None:
        bottom = min(bottom, int(floor))
    if bottom - top < 4:
        return 0, None
    sx = int(spine_x)
    if side == LEFT:
        lo = max(0, sx - A.LABEL_BAND_MAX)
        hi = max(lo, sx - A.RULE_MAX_W)
    else:
        lo = min(dark.shape[1], sx + A.RULE_MAX_W + 1)
        hi = min(dark.shape[1], sx + A.LABEL_BAND_MAX + 1)
    cols = [x for x in range(lo, hi) if dark[top:bottom, x].any()]
    if not cols:
        return 0, None
    return len(cols), (max(cols) if side == LEFT else min(cols))


def numeral_band(dark, box, spine_x, baseline_y, side=None, floor=None,
                 max_reach=180):
    """The tight strip OCR is pointed at, inside the owned one, or None.

    This is `label_band` and its mirror, unchanged, including their two pixel
    constants - `LABEL_GAP` and `LABEL_BAND_MAX` - which belong to the question
    "is this a column of digits" and are documented at their definition.  It is
    reported SEPARATELY from ownership so that a panel whose numerals cannot be
    isolated still has a label box, and so that the two failures are told apart
    in the output instead of both showing as a blank cell.
    """
    x0, x1, y0, y1 = (int(v) for v in box)
    side = side or label_side(dark, box, spine_x, baseline_y)
    top, bottom = axis_extent(dark, box, spine_x)
    top, bottom = max(top, y0), min(bottom, y1)
    if floor is not None:
        bottom = min(bottom, int(floor))
    if bottom - top < 4:
        return None
    if side == LEFT:
        return A.label_band(dark, box, spine_x, top, bottom, max_reach)
    return _band_right(dark, spine_x, top, bottom, max_reach)


def signature(dark, box, spine_x, baseline_y, ticks=""):
    """The panel's physical identity.

    `ladder` is RECORDED and is deliberately NOT part of the identity used for
    matching. A better-measured axis reads more numerals off the same spine, and
    an identity that changed when the measurement improved would report every
    improvement as a different panel - which is the mistake `panel_count` makes
    one level up.
    """
    top, bottom = axis_extent(dark, box, spine_x)
    return {
        "spine_x": int(round(spine_x)),
        "axis_top": int(top),
        "axis_bottom": int(bottom),
        "baseline_y": int(round(baseline_y)),
        "ladder": ladder_hash(ticks),
    }


def ladder_hash(ticks):
    """A short hash of the VALUES a ladder read, not of where they sat.

    Pixels move when a box moves; the numbers on the axis do not. Hashing the
    values means two readings of one axis at two box widths carry the same
    ladder hash, and a ladder that read different NUMBERS is visibly a different
    reading of it.
    """
    vals = []
    for t in (ticks or "").split(";"):
        if ":" in t:
            vals.append(t.split(":", 1)[0])
    if not vals:
        return ""
    return hashlib.sha256("|".join(vals).encode()).hexdigest()[:12]


def ladder_points(ticks):
    """[(value, pixel)] in the order the reader produced them."""
    out = []
    for t in (ticks or "").split(";"):
        if ":" not in t:
            continue
        v, px = t.split(":", 1)
        try:
            out.append((float(v), float(px)))
        except ValueError:
            continue
    return out


def fit_line(points):
    """(slope, intercept, max_residual_px) for value = slope * pixel + intercept.

    Least squares by hand: there is no scipy in this package, and two points of a
    ladder are a line without one. `slope` is VALUE PER PIXEL, which is what a
    calibration is; the residual is in PIXELS, because a residual in value units
    cannot be compared between two panels measuring different quantities.
    """
    n = len(points)
    if n < 2:
        return None, None, None
    sx = sum(px for _v, px in points)
    sy = sum(v for v, _px in points)
    sxx = sum(px * px for _v, px in points)
    sxy = sum(v * px for v, px in points)
    den = n * sxx - sx * sx
    if den == 0:
        return None, None, None
    slope = (n * sxy - sx * sy) / den
    inter = (sy - slope * sx) / n
    if slope == 0:
        return slope, inter, None
    resid = max(abs(px - (v - inter) / slope) for v, px in points)
    return slope, inter, resid


def calibration(ticks, ladder_ok=False, axis_break=None):
    """Everything that makes one panel's y mapping what it is.

    `ladder_hash` HASHES THE VALUES ONLY, and that is not a calibration. Two
    panels printing 0, 50, 100 with those values at different rows have the same
    value set and different mappings, and a group that compares them on the value
    hash calls them one scale. The other direction is as bad: one OCR miss changes
    the value set of a panel whose mapping did not move.

    So there are two hashes and they are named for what they cover:

        value_set_sha    the numbers the reader returned, order preserved
        calibration_sha  the ordered (value, pixel) PAIRS, the point count, the
                         scale check and the axis-break state

    `scale_type` is LINEAR_CHECKED only when the ladder passed, because what
    `axis_reader.ladder` checks IS constant value-per-pixel - a log axis fails it.
    A refused ladder says nothing about the scale, and UNKNOWN is the answer.
    """
    pts = ladder_points(ticks)
    slope, inter, resid = fit_line(pts)
    scale = "LINEAR_CHECKED" if (ladder_ok and len(pts) >= 3) else "UNKNOWN"
    brk = "NONE" if axis_break is None else ("BROKEN:%d-%d" % tuple(axis_break))
    body = "|".join("%g@%.1f" % (v, px) for v, px in pts)
    cal = "%s#n=%d#%s#%s" % (body, len(pts), scale, brk)
    return {
        "points": pts,
        "n_points": len(pts),
        "slope": slope,
        "intercept": inter,
        "fit_residual_px": resid,
        "scale_type": scale,
        "axis_break": brk,
        "value_set_sha": ladder_hash(ticks),
        "calibration_sha": hashlib.sha256(cal.encode()).hexdigest()[:12],
    }


def geometry(dark, box, spine_x, baseline_y, floor=None, neighbours=(),
             ticks=""):
    """plot_box, label_box, numeral_band, review_box and the signature.

    `plot_box` is the box with the owned strip taken OFF it, which matters where
    the strip was wrongly inside: the marks reader then stops seeing a column of
    numerals as data.  `review_box` is the union, which matters where the strip
    was wrongly outside: the person checking the panel is shown the axis their
    numbers came from.
    """
    x0, x1, y0, y1 = (int(v) for v in box)
    side = label_side(dark, box, spine_x, baseline_y)
    strip = label_strip(dark, box, spine_x, baseline_y, side, floor,
                        neighbours)
    band = numeral_band(dark, box, spine_x, baseline_y, side, floor)
    sx = int(spine_x)
    plot = [x0, x1, y0, y1]
    if strip:
        lo, hi, _t, _b = strip
        if side == LEFT and hi >= x0:
            plot[0] = min(max(x0, hi + 1), sx)
        if side == RIGHT and lo <= x1:
            plot[1] = max(min(x1, lo - 1), sx)
    review = [x0, x1, y0, y1]
    if strip:
        lo, hi, t, b = strip
        review = [min(x0, lo), max(x1, hi), min(y0, t), max(y1, b)]
    return {
        "label_side": side,
        "plot_box": tuple(plot),
        "label_box": tuple(strip) if strip else None,
        "numeral_band": tuple(band) if band else None,
        "review_box": tuple(review),
        "signature": signature(dark, box, spine_x, baseline_y, ticks),
    }


def as_columns(g):
    """The flat cells `propose.py` writes, beside x0/x1/y0/y1 and never over them."""
    if g is None:
        return {}
    lb, nb = g["label_box"], g["numeral_band"]
    s = g["signature"]
    return {
        "plot_x0": g["plot_box"][0], "plot_x1": g["plot_box"][1],
        "plot_y0": g["plot_box"][2], "plot_y1": g["plot_box"][3],
        "label_x0": lb[0] if lb else "", "label_x1": lb[1] if lb else "",
        "label_y0": lb[2] if lb else "", "label_y1": lb[3] if lb else "",
        "label_side": g["label_side"],
        "numeral_x0": nb[0] if nb else "", "numeral_x1": nb[1] if nb else "",
        "review_x0": g["review_box"][0], "review_x1": g["review_box"][1],
        "review_y0": g["review_box"][2], "review_y1": g["review_box"][3],
        "axis_sig": "%d:%d-%d:%d" % (s["spine_x"], s["axis_top"],
                                     s["axis_bottom"], s["baseline_y"]),
        "ladder_sig": s["ladder"],
    }
