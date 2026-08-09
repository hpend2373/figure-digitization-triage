"""What a monochrome bar chart actually looks like, measured rather than assumed.

    python3 measure_mono_bars.py                  # print the table
    python3 measure_mono_bars.py --json OUT.json  # and write it

`_FILL_BANDS` and `_INSIDE_MIN_DENSITY` in `mark_readers.py` carry a comment
saying they were "measured on a real monochrome figure". They were - on ONE.
Publication 127 is the second, and it does not fit them: under the production
reader's binary density rule its solid bars read about 0.70, which is neither
SOLID (0.72 and up) nor HATCHED (up to 0.60) but the dead zone between the two,
and its stipple rows read 0.10 against a floor of 0.15. Its open bar's right
stroke does not fall in the last two columns of the slot the reader gave it.

What this script records is `ink_mass`, which is threshold-free - one minus the
mean grey of the interior - and is NOT the same feature as the production
reader's binary density. The two must not be compared as though they were; the
bands here are drawn from ink_mass measurements and the bands there from density
ones, and a fill can sit in a clean band under one and in a dead zone under the
other. That is an argument for replacing the feature, not for retuning it.

This script is the evidence a replacement has to be justified by. It reads
figures and decides nothing; nothing in the package imports it.

Three rules govern what it measures, because the point is to find quantities
that survive a different journal, a different DPI and a different scan:

**Every length is a multiple of the figure's own stroke.** The thickness of the
baseline rule is measurable in the panel, and it is what a pixel count was
standing in for. Where the stroke cannot be measured this says so rather than
returning 1, which would disguise a detection failure as a thin line.

**Every intensity feature is reported at four thresholds, and once without
one.** A feature that separates two fills at 128 and not at 160 is a property of
the threshold. `ink_mass` uses the grey values directly and has no threshold at
all.

**The footprint comes from the baseline, not from the column heights.** Ink that
does not touch the baseline is an error bar, a significance glyph or a
neighbour, and taking the full-height dark span lets all three widen a bar.
Slot boundaries are then the midpoints BETWEEN detected footprints, so a slot is
a place to look and never a bar edge.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mark_readers as MR                                          # noqa: E402

try:
    import cv2
except ImportError:                                                # pragma: no cover
    cv2 = None

#: Reported at each of these, so a feature that only separates at one of them
#: can be recognised as an artefact of the threshold rather than a property of
#: the ink.
THRESHOLDS = (96, 128, 160, 192)

#: Fraction of the seed band a column must be inked in to count as support.
#: Dimensionless, and the same number for every figure.
SEED_SUPPORT = 0.25

#: How deep the seed band goes, as a multiple of the measured stroke. Deep
#: enough to be inside a short bar, shallow enough not to leave a short one.
SEED_DEPTH_STROKES = 3


class StrokeScale(object):
    """The figure's own line weight, or an explicit refusal to guess it.

    Returning 1 px when no rule can be found makes a detection failure
    indistinguishable from a hairline figure, and every threshold downstream is
    a multiple of this number. A reader that inherits this must raise
    `GeometryResolutionError` on UNRESOLVED rather than carry on with 1.
    """

    def __init__(self, value_px=None, status="UNRESOLVED", reason=""):
        self.value_px = value_px
        self.status = status
        self.reason = reason

    @property
    def ok(self):
        return self.status == "MEASURED"

    def __repr__(self):
        return ("StrokeScale(%r px)" % self.value_px if self.ok
                else "StrokeScale(UNRESOLVED: %s)" % self.reason)

    def as_dict(self):
        return dict(value_px=self.value_px, status=self.status, reason=self.reason)


def _gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    if cv2 is not None:
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return rgb.mean(axis=2).astype(np.uint8)   # pragma: no cover


def _runs(indices, gap=1):
    out, cur = [], []
    for i in indices:
        if cur and i - cur[-1] > gap:
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _longest_dark_run(strip):
    """Length of the longest CONTIGUOUS dark run in each row."""
    pad = np.zeros((strip.shape[0], 1), dtype=np.int8)
    edges = np.diff(np.concatenate(
        [pad, strip.astype(np.int8), pad], axis=1), axis=1)
    out = np.zeros(strip.shape[0], dtype=int)
    for i in range(strip.shape[0]):
        starts = np.where(edges[i] == 1)[0]
        if not len(starts):
            continue
        out[i] = int((np.where(edges[i] == -1)[0] - starts).max())
    return out


def stroke_scale(gray, box, threshold=128, baseline_row=None, min_aspect=20,
                 tolerance=0.6, search_fraction=0.02):
    """Line weight in pixels: how thick THE BASELINE RULE is.

    Not the longest rule in the panel - the one the bars stand on. A panel
    frame, a gridline and a box border are all as long as the axis and can be
    drawn heavier, and `argmax` returns the FIRST of the tied maxima, which is
    whichever of them is nearest the top of the panel. The scenario in this
    package that draws an 8 px frame above a 4 px baseline measured the stroke
    at 8, and since seed depth, direction margin, remote reach, minimum interior
    height, component thickness and gap tolerance are all multiples of it, the
    whole geometry doubled. It passed anyway - which is the point: a stroke that
    is wrong by a factor of two does not fail, it drifts.

    `baseline_row` is the calibrated zero, so `measure_panel` computes the axis
    calibration BEFORE the stroke rather than after. The search is a fraction of
    the panel height around it - the rule sits within a pixel of the calibrated
    zero on all five panels measured here, and a candidate further away than
    that is a different line. If nothing rule-shaped is there, this refuses;
    falling back to the longest run anywhere is how the 8 px frame won.

    Called without a `baseline_row` it still takes the panel's longest run, for
    ad-hoc inspection. Nothing in the measurement path does that.

    Two things were wrong with measuring this as "the thickest band of rows
    whose dark pixel COUNT exceeds half the panel width".

    A rule is CONTIGUOUS. A row that crosses several bars is not a rule even
    when the bars add up to half the panel, and the band it belongs to is as
    thick as the bars are tall: three 100 px bars in a 400 px panel measured the
    stroke at 124 px. Every threshold here is a multiple of the stroke, so the
    panel then read one bar out of three. Bars are separated by paper; rules are
    not.

    And half the panel width is a number this script had no business choosing.
    Publication 397's panel box holds no rule longer than a third of its width,
    so demanding half refuses the figure, and lowering the fraction until 397
    passes is how `_INSIDE_MIN_DENSITY` came to exist. The panel's own longest
    horizontal run is the reference instead: whatever the longest run is, the
    rows that carry one within `tolerance` of it are the same rule - a tick mark
    or an antialiased end can shorten it on individual rows - and how thick that
    band is, is the stroke, and no fraction was tuned to make it so.

    Measured off the panel's longest line, 397 read 2 px; measured off its own
    baseline it reads 1 px in the MEN panel and 2 px in the WOMEN panel, because
    that is where the axis lands on the pixel grid in each. The two numbers are
    not a disagreement - they answer different questions, and the baseline is
    the one the bars stand on. Publication 127 reads 3, 3 and 4 across its three
    sub-panels for the same reason.

    The band is the rows CONTIGUOUS with the longest one, not every row in the
    panel that clears the bar - the rule is one object, and a stray row
    elsewhere in the panel is a different object with a different thickness.
    Measured that way the three sub-panels of publication 127's Figure 4, which
    are the same figure at the same DPI and must therefore agree, all read 3 px;
    taking the thickest band anywhere in the panel read 1, 3 and 4.

    Two numbers are asserted rather than measured, and both are statements about
    shape rather than about any figure. `min_aspect`: something only twenty
    times longer than it is thick is a block, and a panel whose longest
    horizontal structure is a block has no rule in it to measure. `tolerance`:
    the antialiased outer row of a rule loses a few pixels at each end, never
    half its length, while the longest run in a row of BARS is one bar - so
    anything between "widest bar" and "nearly the whole rule" separates them,
    and 0.6 is the middle of that window. It is at its narrowest on 397, whose
    panel box crops the axis to 118 px against a 62 px bar.
    """
    x0, x1, y0, y1 = map(int, box)
    strip = gray[y0:y1, x0:x1] < threshold
    if not strip.size:
        return StrokeScale(reason="the panel box selects no pixels")
    runs = _longest_dark_run(strip)
    if not runs.size or int(runs.max()) < 1:
        return StrokeScale(reason="the panel box holds no dark pixels")
    def band_of(seed):
        """The rule the row at `seed` belongs to: (lo, hi, its longest run)."""
        length = int(runs[seed])
        lo = hi = seed
        while lo - 1 >= 0 and runs[lo - 1] >= tolerance * length:
            lo -= 1
        while hi + 1 < len(runs) and runs[hi + 1] >= tolerance * length:
            hi += 1
        return lo, hi, length

    if baseline_row is None:
        lo, hi, longest = band_of(int(np.argmax(runs)))
    else:
        reach = max(4, int(round(search_fraction * strip.shape[0])))
        a = max(0, int(baseline_row) - reach)
        b = min(len(runs), int(baseline_row) + reach + 1)
        if b <= a:
            return StrokeScale(reason="the calibrated baseline is outside the panel")
        # A rule-shaped band that CONTAINS the calibrated zero beats one that
        # does not, and only then does length decide. A gridline a few pixels
        # above the baseline drawn to the same length ties on length, and
        # `argmax` breaks a tie by taking whichever comes first, which going
        # down the page is the gridline.
        #
        # Containment, not distance. Ranking candidates by distance looks more
        # general and is worse: the same physical rule yields NESTED bands
        # depending on which of its rows seeded them, the loosest of those
        # reaches nearest the zero row, and preferring it moved publication
        # 127's stroke from 3 px to 4, 4 and 7 across three panels that must
        # agree. Containment cannot choose between nested bands of one rule and
        # does not have to - when no band contains the zero, which is the case
        # on three of the five panels measured here, the longest run in the
        # window is the answer and it is the right one.
        # Only rows that are themselves near the longest run in the window may
        # seed a candidate. A short run seeds a LOOSE band - its tolerance is a
        # fraction of its own small length - and a loose band swallows rows the
        # rule does not own: on publication 127 an 182 px row two below the axis
        # grew a band of seven rows that reached the zero row and won on
        # containment, against the three the rule actually occupies.
        strongest = int(runs[a:b].max())
        seen, holding, longest_seed = set(), None, None
        for seed in range(a, b):
            if runs[seed] < max(1, tolerance * strongest):
                continue
            lo, hi, length = band_of(seed)
            if (lo, hi) in seen:
                continue
            seen.add((lo, hi))
            if longest_seed is None or length > longest_seed[2]:
                longest_seed = (lo, hi, length)
            if lo <= baseline_row <= hi and length >= min_aspect * (hi - lo + 1):
                if holding is None or length > holding[2]:
                    holding = (lo, hi, length)
        if holding is None and longest_seed is None:
            return StrokeScale(
                reason="no ink within %d px of the calibrated baseline at row %s"
                       % (reach, baseline_row))
        lo, hi, longest = holding or longest_seed
    thickest = hi - lo + 1
    if longest < min_aspect * thickest:
        return StrokeScale(
            reason="the longest horizontal run near row %s is %d px across and "
                   "%d px thick, which is a block and not a rule"
                   % (baseline_row, longest, thickest))
    return StrokeScale(value_px=int(thickest), status="MEASURED")


def rule_edge(dark, zero_row, stroke, direction, min_span=0.6, min_ink=0.4):
    """The last row of the baseline rule, on the side the bars are on.

    The measured stroke is the rule's SOLID CORE - three rows on publication 127
    at 600 DPI - and the rule's inked extent at threshold 128 is wider than its
    core, because the edges are antialiased. Standing one core-stroke clear of
    the baseline leaves the seed band sitting on the rule's fade, every column in
    the window reads as seeded including the paper at its edges, and the clipping
    guard then fires on every group in the figure. So the clearance is measured
    rather than derived from the stroke.

    Finding the rule is easy: it is the row near the baseline whose ink is a
    SINGLE unbroken run across most of the window, which a row of bars is not,
    however much of the window the bars add up to. Finding where it ENDS is the
    part that needs care, because its fading rows are no longer unbroken - on
    publication 127 the rule reads 0.93, 0.98, 1.00, 0.75, 0.49 of the window
    and only the middle three are unbroken. Two rules, either sufficient:

      still unbroken across the window   - unambiguously the rule;
      still inked, and LESS inked than the row before it - a fade. A bar row is
        as inked as the bar row before it, so a fade terminates on the first row
        that stops fading, which is the first row that belongs to something else.
    """
    step = -1 if direction == "UP" else 1
    height, width = dark.shape
    near = [r for r in range(max(0, zero_row - 2 * stroke - 1),
                             min(height, zero_row + 2 * stroke + 2))]
    if not near:
        return int(zero_row)
    spans = {r: int(_longest_dark_run(dark[r:r + 1])[0]) for r in near}
    seed = max(near, key=lambda r: spans[r])
    if spans[seed] < min_span * width:
        return int(zero_row)
    row, ink = seed, float(dark[seed].mean())
    while 0 <= row + step < height:
        nxt = row + step
        ink_next = float(dark[nxt].mean())
        unbroken = _longest_dark_run(dark[nxt:nxt + 1])[0] >= min_span * width
        if not (unbroken or (ink_next >= min_ink and ink_next < ink)):
            break
        row, ink = nxt, ink_next
    return int(row)


def seed_support(gray, box, zero_row, stroke, window, threshold=128,
                 direction="UP"):
    """Columns of `window` whose ink reaches the baseline, as x-runs.

    Ink that does not touch the baseline is an error bar, a significance glyph
    or the neighbouring bar, and none of them is part of this bar. The band
    starts one row clear of the baseline rule's own inked thickness, because the
    rule is dark across every column and would make an open bar's footprint the
    whole slot.
    """
    x0, x1, y0, y1 = map(int, box)
    xa, xb = window
    dark = gray[y0:y1, xa:xb] < threshold
    depth = SEED_DEPTH_STROKES * stroke
    edge = rule_edge(dark, zero_row, stroke, direction)
    if direction == "UP":
        top, bottom = max(0, edge - 1 - depth), max(1, edge - 1)
    else:
        top, bottom = min(dark.shape[0] - 1, edge + 1), \
            min(dark.shape[0], edge + 1 + depth)
    band = dark[top:bottom]
    if band.shape[0] < depth:
        # A short band is not a weak measurement, it is a different one:
        # SEED_SUPPORT is a fraction of the band, and a quarter of two rows is
        # one row. Below publication 127's baseline the panel has three rows
        # left, the last of them the rule's own fade at 0.39 of the window, and
        # a quarter of three rows made that fade look like 251 px of downward
        # bar against 246 px of real upward bar - so the direction test called
        # the group ambiguous and refused a figure it could read.
        return [], np.zeros(xb - xa)
    persistence = band.mean(axis=0)
    keep = [i for i, v in enumerate(persistence) if v >= SEED_SUPPORT]
    segments = [g for g in _runs(keep, gap=max(2, stroke))
                if len(g) >= max(2, stroke // 2)]
    return segments, persistence


def footprints_from_seed(segments, n_bars):
    """Group seed segments into `n_bars` footprints, by even pitch.

    Bars in a printed group are equal width and evenly spaced, so which segment
    belongs to which bar follows from where it sits between the first and the
    last. An OPEN bar contributes two narrow segments and a SOLID one
    contributes one wide one; both land in the same bar.

    Returns (footprints, slot_bounds). The footprints are the bars. The bounds
    are the midpoints BETWEEN them - a place to search, never a bar edge, and
    the thing the old reader mistook for one.
    """
    if not segments or n_bars < 1:
        return [], []
    lo, hi = segments[0][0], segments[-1][-1]
    pitch = (hi - lo + 1) / float(n_bars)
    buckets = [[] for _ in range(n_bars)]
    for seg in segments:
        centre = (seg[0] + seg[-1]) / 2.0
        k = min(n_bars - 1, max(0, int((centre - lo) / pitch)))
        buckets[k].append(seg)
    prints = [(bucket[0][0], bucket[-1][-1]) if bucket else None
              for bucket in buckets]
    # The boundaries the docstring promises, computed rather than implied.
    # Even pitch is how a segment is ASSIGNED to a bar; the boundary between
    # two bars is the midpoint of the gap between the footprints that came out,
    # which is not the same number and is the one a caller should search in.
    bounds = []
    for i, fp in enumerate(prints):
        if fp is None:
            bounds.append(None)
            continue
        prev = next((p for p in reversed(prints[:i]) if p), None)
        nxt = next((p for p in prints[i + 1:] if p), None)
        left = fp[0] if prev is None else int(round((prev[1] + fp[0]) / 2.0))
        right = fp[1] if nxt is None else int(round((fp[1] + nxt[0]) / 2.0))
        bounds.append((left, right))
    return prints, bounds


def trace_extent(gray, box, window, footprint, zero_row, stroke,
                 direction="UP", threshold=128):
    """Walk from the baseline to the bar end on horizontal SUPPORT, not density.

    Two independent reasons a row is still inside the bar, either sufficient:

    **Both edge tracks are inked.** Definitive for an OPEN bar, which is nothing
    but its outline. The tracks are found from the bar's own footprint, not from
    the first and last two columns of a slot - publication 127's open bar has a
    stray column 8 px past its right stroke, so `body[:, -2:]` was white at
    every row and the walk stopped on the baseline, returning 0.15 for a bar of
    height 14.7.

    **The ink is spread across the bar.** A stipple inks 10% of a row, which is
    below any floor that also excludes an error-bar stem - but it inks that 10%
    in bins all across the bar, and a 2 px stem inks one bin. Distribution
    separates them where density cannot, so there is no `_INSIDE_MIN_DENSITY`.

    Sampled over a short vertical window rather than a single row, because a
    stipple has blank rows between its dots, and with hysteresis, because it has
    blank windows too. Both are multiples of the measured stroke.

    Returns (edge_row, method). It used to return a third value, a
    `contradiction` distance measured by rerunning `supported()` above the edge;
    that reused the walk's support test without the three gap rules the walk
    uses to exclude an error-bar cap, so it re-found the cap the walk had just
    refused and reported it as proof the walk was wrong. Asking what the ink
    above the bar IS belongs to `remote_support`, which masks the stem and the
    cap before it looks.
    """
    x0, x1, y0, y1 = map(int, box)
    xa = window[0]
    fx0, fx1 = footprint
    bar_w = fx1 - fx0 + 1
    dark = gray[y0:y1, xa + fx0:xa + fx1 + 1] < threshold
    height = dark.shape[0]
    track = max(1, min(stroke, int(round(0.06 * bar_w))))
    win = max(2, stroke)
    step = -1 if direction == "UP" else 1
    start = zero_row + step * (stroke + 1)
    bins = 5
    need_bins = 3

    def supported(row):
        a, b = sorted((row, row + step * win))
        a, b = max(0, a), min(height, b + 1)
        if b - a < 1:
            return False, ""
        chunk = dark[a:b]
        left = chunk[:, :track].any()
        right = chunk[:, -track:].any()
        if left and right:
            return True, "SIDE_TRACK"
        columns = chunk.any(axis=0)
        if not columns.any():
            return False, ""
        occupied = np.where(columns)[0]
        span = (occupied[-1] - occupied[0] + 1) / float(bar_w)
        filled = sum(1 for part in np.array_split(columns, bins) if part.any())
        if span >= 0.55 and filled >= need_bins:
            return True, "DISTRIBUTED_BODY"
        return False, ""

    # Two rules about gaps, and both exist because of the error-bar cap.
    #
    # A cap is drawn about 70% of the bar's width, so it satisfies
    # DISTRIBUTED_BODY on its own - it is wide, it spans, it fills the bins.
    # What it is NOT is continuous with the bar: between a bar top and its cap
    # lie the whisker rows, inked only by a two-pixel stem. So:
    #
    #   a gap may be crossed only while SIDE_TRACK is carrying the walk, because
    #     a side stroke runs unbroken from baseline to bar end by construction
    #     and a blank window in it is a raster artefact, not a boundary;
    #   distributed ink must be gapless, because the thing on the far side of a
    #     gap in distributed ink is a cap.
    #
    # And support regained after ANY miss must persist. A cap is one stroke
    # thick: it supports one window and then there is nothing above it. Bar
    # body supports the next window too. This is what stops a full-width cap on
    # a small-SD bar, where the gap is short enough to be crossed.
    row, misses, last, method = start, 0, start, ""
    while 0 <= row < height:
        ok, how = supported(row)
        if ok:
            if misses:
                # How THICK is the thing we just found, in ROWS? A cap is one
                # stroke of ink and then paper; bar body keeps going. Rows, not
                # windows: consecutive windows overlap, so two of them both
                # catch a 2 px cap and it measures 8 px thick - which is how it
                # survived the first version of this check.
                thickness, probe = 0, row
                while 0 <= probe < height and dark[probe].any():
                    occupied = np.where(dark[probe])[0]
                    if (occupied[-1] - occupied[0] + 1) < 0.55 * bar_w:
                        break
                    thickness += 1
                    probe += step
                if thickness < 2 * stroke or method != "SIDE_TRACK":
                    break
            last, misses, method = row, 0, how or method
        else:
            misses += 1
            if method != "SIDE_TRACK" or misses > 2:
                break
        row += step * win
    # The window walk lands within `win` px of the end; refine row by row so the
    # answer is the bar top and not the last window boundary before it. This is
    # also what removed the last unit of error against the synthetic fixture's
    # known means - a 4 px window is 1.1 units on that axis.
    #
    # It cannot run on to the cap: between the bar end and the cap lie rows
    # inked only by the stem, and the first of them fails both tests.
    probe = last
    while 0 <= probe + step < height:
        nxt = probe + step
        occupied = np.where(dark[nxt])[0]
        if not len(occupied):
            break
        span = (occupied[-1] - occupied[0] + 1) / float(bar_w)
        tracks = dark[nxt, :track].any() and dark[nxt, -track:].any()
        if not (tracks or span >= 0.55):
            break
        probe = nxt
    return float(probe), method or "NONE"


def trim_to_own_bar(gray, box, window, footprint, edge_row, zero_row, stroke,
                    direction="UP", threshold=128, min_share=0.5):
    """Drop footprint columns whose ink belongs to the bar next door.

    Two bars that TOUCH defeat everything upstream. On publication 397's WOMEN
    panel the solid bar occupies columns 16-73 and the hatched one starts at 78,
    and the hatched bar's leading diagonals reach back to column 74 on some
    rows. Those columns are seeded, so the footprint comes out 16-77 - four
    columns into the neighbour - and above the solid bar's top they carry the
    neighbour's body. Taking the midpoint of the gap BETWEEN footprints is no
    help: there is no gap, the bleed is inside the seed run.

    The measurement is VERTICAL OCCUPANCY IN THE BODY BAND - the rows between
    the provisional bar top and the baseline, which is the part of the slot that
    is bar and nothing else. A column of this bar is inked through that band; a
    neighbour's diagonal crossing into the slot is inked in a fraction of it.

    The band matters more than the statistic. The first attempt at this compared
    each column's TOPMOST ink instead, on the theory that a bar's top is level -
    and the topmost ink in a column is the error bar, not the bar. The synthetic
    fixture's caps span 70% of the bar, so the median column top was the cap row
    and every column outside the cap was trimmed; the fixture lost three bars
    per group and the corpus went from 37 dispersions to 23. Requiring the ink
    to be contiguous with the baseline does not rescue it either, because a
    stipple's columns are dotted.

    The comparison is LOCAL: a column is trimmed when it carries much less ink
    than the most inked column just inside it. Neither a global median nor a
    global maximum works. An open bar's interior is paper, so its median
    occupancy is near zero and a median-relative test trims its own side
    strokes. And publication 397's hatched bars have a top rule but NO side
    strokes, so every column of them is inked about a third of the time and a
    single column that happens to catch two diagonals becomes a global maximum
    that the rest of the bar cannot clear - which trimmed all four hatched cells
    to nothing. "The bleed is at the edge and the bar is beside it" is a
    statement about neighbours, so it is tested against neighbours.

    The band's one-stroke inset from the provisional top is defensive rather
    than load-bearing: adding the error bar's rows would raise the occupancy of
    a few central columns, which cannot change an EDGE decision unless the cap
    is wider than its bar. No scenario pins it, and this comment is the record
    of that rather than a claim it is covered.
    """
    x0, x1, y0, y1 = map(int, box)
    xa = window[0]
    fx0, fx1 = footprint
    dark = gray[y0:y1, xa + fx0:xa + fx1 + 1] < threshold
    top = int(round(min(edge_row, zero_row))) + stroke
    bottom = int(round(max(edge_row, zero_row))) - stroke
    if bottom - top < max(3, 2 * stroke):
        return footprint, [], ""
    band = dark[top:bottom]
    occupancy = band.mean(axis=0)
    if occupancy.max() <= 0:
        return footprint, [], ""
    # How far inward the comparison looks. Two strokes is enough when the bleed
    # is four columns, as on publication 397, and not when it is forty: the
    # window then sits inside the bleed, sees only more of it, and stops at
    # once. A quarter of the footprint is the bound, because a footprint whose
    # outer quarter is somebody else's bar is not one that trimming can repair -
    # and the convergence guard refuses that case rather than trimming into it.
    reach = max(3, 2 * stroke, len(occupancy) // 4)

    def inward(index, step):
        window = occupancy[index + step:index + step * (reach + 1):step]
        return float(window.max()) if window.size else 0.0

    # How far inward the comparison LOOKS and how much it is allowed to REMOVE
    # are two different numbers, and one `reach` was doing both jobs badly. A
    # footprint whose outer quarter is somebody else's bar is not one that
    # trimming can repair, so that is the budget - and it is a refusal, not a
    # smaller footprint, because the alternative is a bar measured from
    # whatever survived. NOT PINNED BY A SCENARIO: a synthetic bleed wide enough
    # to spend the budget did not seed into the footprint at all, so nothing
    # exercises this branch and this comment is the record of that rather than a
    # claim of coverage.
    budget = max(1, len(occupancy) // 4)
    lo, hi, dropped = 0, len(occupancy) - 1, []
    while lo < hi and occupancy[lo] < min_share * inward(lo, 1):
        dropped.append(fx0 + lo)
        lo += 1
    left = lo
    while hi > lo and occupancy[hi] < min_share * inward(hi, -1):
        dropped.append(fx0 + hi)
        hi -= 1
    right = len(occupancy) - 1 - hi
    if left > budget or right > budget:
        return footprint, sorted(dropped), "EXCESSIVE_TRIM"
    if not dropped:
        return footprint, [], ""
    return (fx0 + lo, fx0 + hi), sorted(dropped), ""


def refine_footprint(footprint, trace, trim):
    """One trim, one re-trace, one CONFIRMING trim - as a state machine.

    Separated from `measure_panel` so the two refusals it can reach are testable
    without a raster that produces them. Neither is reachable end to end: a bleed
    wide enough to spend the trim budget is too faint to seed into the footprint
    in the first place, and a second pass that moves the footprint again needs a
    figure nobody has found. Injecting `trace` and `trim` pins the CONTRACT -
    which refusal, under which name, carrying which record - and the primitives
    they stand in for are pinned separately.

    Returns (footprint, edge, method, dropped, error, detail).
    """
    edge, method = trace(footprint)
    first, dropped, why = trim(footprint, edge)
    if why:
        return (footprint, edge, method, dropped, why,
                dict(convergence_stage="FIRST_PASS"))
    if not dropped:
        return footprint, edge, method, [], "", {}
    retraced, retraced_method = trace(first)
    again, more, why_again = trim(first, retraced)
    if why_again or tuple(again) != tuple(first):
        # Two different findings, and they used to share one name. An
        # over-budget trim hands back the footprint it was given, so calling it
        # a convergence failure produced records whose two footprints AGREE
        # while the error says they did not.
        return (first, retraced, retraced_method, sorted(set(dropped) | set(more)),
                why_again or "FOOTPRINT_DID_NOT_CONVERGE",
                dict(convergence_stage="SECOND_PASS",
                     first_trimmed_footprint=[int(first[0]), int(first[1])],
                     second_trimmed_footprint=[int(again[0]), int(again[1])],
                     provisional_edge_row_panel=round(float(edge), 1),
                     retraced_edge_row_panel=round(float(retraced), 1)))
    return first, retraced, retraced_method, dropped, "", {}


#: What an inked structure beyond the bar end turns out to be. The distinction
#: matters because only the first of these means the walk was wrong.
REMOTE_KINDS = ("BODY_CONTINUATION", "ERRORBAR_CAP", "BAR_EDGE_REMNANT",
                "NEIGHBOUR_STRUCTURE", "ANNOTATION_OR_GLYPH",
                "UNRESOLVED_REMOTE_SUPPORT")


def stem_band(stem_dark, scan, bar_w, stroke, max_strokes=4):
    """Where the whisker actually is, as a column slice, or None.

    Assuming the stem runs up the middle of the bar costs three of publication
    397's four WOMEN cells their dispersion: its whiskers are drawn at 39% to
    46% of the bar width, and a centre slice of the bar's middle fifth misses
    them by two pixels. Nothing says an error bar is centred on its bar - it is
    centred on the series, and the bar's footprint is measured from ink that can
    be a few pixels wider than the bar on either side.

    So it is found instead: among the narrow runs of ink in the first rows above
    the bar, the one nearest the bar's centre. Narrow because a stem is a
    hairline - a run wider than a few strokes is the bar's own antialiased top,
    which is what the first row above a solid bar holds at the stem threshold.
    Nearest the centre because a bar's outline reaches the edges and a stem does
    not.
    """
    centre = (bar_w - 1) / 2.0
    for row in scan[:max(3, 2 * stroke)]:
        best = None
        columns = np.where(stem_dark[row])[0]
        if not len(columns):
            continue
        for run in _runs(list(columns), gap=max(1, stroke // 2)):
            if run[-1] - run[0] + 1 > max_strokes * stroke:
                continue
            offset = abs((run[0] + run[-1]) / 2.0 - centre)
            if best is None or offset < best[0]:
                best = (offset, run[0], run[-1])
        if best is not None:
            pad = max(1, stroke)
            return slice(max(0, best[1] - pad), min(bar_w, best[2] + 1 + pad))
    return None


def remote_support(gray, box, window, footprint, edge_row, zero_row, stroke,
                   direction="UP", threshold=128, stem_threshold=200):
    """Everything inked beyond the bar end, classified rather than counted.

    The first version of this returned one integer: the distance at which
    `supported()` was still true. That reused the walk's support test WITHOUT
    the three rules the walk uses to exclude an error-bar cap - so the cap the
    walk had just refused was scanned again and reported as evidence that the
    walk had stopped too early. `!60` on publication 127's normal-paced panel
    is 0.93 axis units above the bar at a scale of 9 units per 581 px, which is
    the size of an SE bar on that figure, not the size of a missing bar body.

    Sampling every fourth window made it worse: at 20 px per probe the reported
    distance is quantised to the probe grid, a thin cap that happens to land on
    one is counted, and a body that lies between two is missed.

    So: walk the rows above the end, group inked rows into components, and ask
    what each component IS.

      BODY_CONTINUATION       side tracks, or distributed ink, sustained over
                              several strokes, CONTINUOUS with the bar. The
                              walk stopped too early and this bar has no value.
      ERRORBAR_CAP            a thin horizontal rule that misses the side
                              tracks and hangs off a central stem. Expected,
                              and where the dispersion comes from.
      NEIGHBOUR_STRUCTURE     ink that CONTINUES PAST this bar's footprint. A
                              bar is not wider than its own footprint, so
                              whatever this is, it is not this bar's body: the
                              neighbouring bar, a rule spanning the group, a
                              significance bracket. On publication 397's WOMEN
                              panel the hatched bar's top rule runs from column
                              72 to 129 while the solid bar occupies 16 to 74 -
                              three columns of overhang, above the solid bar's
                              top, in columns that below it are solid bar. No
                              trim can take them; they are this bar's columns.
                              Only what happens OUTSIDE the footprint says whose
                              the structure is.
      ANNOTATION_OR_GLYPH     provably not this bar: separated from it by white
                              paper and too far away for that gap to be a
                              raster artefact. An asterisk, a bracket, a panel
                              rule, a title, the neighbouring group.
      UNRESOLVED_REMOTE_SUPPORT   none of the above cleanly. Fail closed.

    Two thresholds, because a bar edge and a whisker stem are not printed with
    the same weight. Body geometry - the side tracks, the span, the bins - is
    measured at `threshold`; the central stem that a cap hangs off is traced at
    `stem_threshold`, the same 200 the production error-bar reader uses, because
    a two-pixel antialiased stem on a 600 DPI rescan sits in the 130-190 grey
    range and is invisible at 128. Where the stem is invisible, the cap above it
    is not connected to anything and is classified as a free-floating glyph.

    `distance_px` is what separates the last two kinds. A body continuation
    separated from the bar by white paper is only physically possible when the
    gap is a raster artefact - a stipple's blank row, a broken outline - which
    is a small multiple of the stroke. Ink 150 px above the bar with nothing in
    between is the panel's furniture, and a rule at the top of a panel is wide,
    spanning and thick, so shape alone cannot tell it from a bar.
    """
    x0, x1, y0, y1 = map(int, box)
    xa = window[0]
    fx0, fx1 = footprint
    bar_w = fx1 - fx0 + 1
    strip = gray[y0:y1, xa + fx0:xa + fx1 + 1]
    dark = strip < threshold
    stem_dark = strip < stem_threshold
    # The columns just OUTSIDE the footprint, on both sides, clipped to the
    # group window. A component that reaches into them is wider than this bar.
    margin = max(2, stroke)
    limit = window[1] - window[0] - 1
    left_margin = gray[y0:y1, xa + max(0, fx0 - margin):xa + fx0] < threshold
    right_margin = (gray[y0:y1, xa + fx1 + 1:xa + min(limit, fx1 + margin) + 1]
                    < threshold)
    height = dark.shape[0]
    track = max(1, min(stroke, int(round(0.06 * bar_w))))
    step = -1 if direction == "UP" else 1
    centre = slice(max(0, bar_w // 2 - max(1, bar_w // 10)),
                   min(bar_w, bar_w // 2 + max(1, bar_w // 10) + 1))
    #: How far a gap between the bar and a body-like component may be and still
    #: be a printing artefact rather than a boundary. Four strokes, so it scales
    #: with the figure and not with the DPI it was scanned at.
    reach = max(2, 4 * stroke)

    # The order matters, and the first attempt at this did it wrong. Grouping
    # "rows with any ink" merges the cap, the whisker stem and everything above
    # into one component, because the stem inks every row between them - so a
    # 2 px cap measured 17 px thick and was called a body continuation.
    #
    #   trace the stem up from the bar end
    #   find the cap at the end of the stem
    #   mask both
    #   whatever ink is LEFT beyond the bar end is the question
    #
    # After the mask, a component cannot be stem-connected by construction, so
    # the classification is about the component's own shape.
    def spread(r, mat=None):
        occupied = np.where((stem_dark if mat is None else mat)[r])[0]
        return int(occupied[-1] - occupied[0] + 1) if len(occupied) else 0

    edge = int(round(edge_row))
    limit = 0 if step < 0 else height - 1
    # Where the bar ends and the error bar begins, measured rather than assumed
    # to be one stroke. Skipping a fixed `stroke` rows is right when the bar's
    # top rule is one stroke thick and wrong when the whole error bar is short:
    # on publication 127's SUPINE bars the stem is a SINGLE row between the top
    # rule and the cap, the fixed skip stepped straight over it, and the cap
    # then had nothing to hang from. So walk off the bar instead - past rows
    # still as wide as the bar - and start at the first row that is not the bar.
    start = edge
    while 0 <= start + step < height:
        w = spread(start + step, dark)
        if not w or w < 0.5 * bar_w:
            break
        start += step
    scan = [r for r in range(start + step, limit + step, step) if 0 <= r < height]
    if not scan:
        return []
    # The measured stem AND the bar's middle, together. Replacing the middle
    # with the measured run found publication 397's off-centre whiskers and lost
    # five of publication 127's cells, whose stems are central and whose masks
    # then left a residue the classifier could not name. Widening never costs a
    # trace and never leaves more behind, so the band is the union.
    band = np.zeros(bar_w, dtype=bool)
    band[centre] = True
    found = stem_band(stem_dark, scan, bar_w, stroke)
    if found is not None:
        band[found] = True
    stem_rows = []
    for r in scan:
        if not stem_dark[r, band].any():
            break
        stem_rows.append(r)
    # An error bar is a NARROW stem carrying a WIDE cap, and that is the whole
    # of the distinction: the stem is the narrowest row of the structure and the
    # cap is several times wider than it. The rule this replaces asked whether a
    # row spanned 30% of the BAR, which is a fraction of the wrong thing - it
    # was fitted to the synthetic fixture in this package, whose caps are 70% of
    # the bar. Publication 397 draws its caps at 0.18 of the bar and publication
    # 127 at 0.17-0.19, so the test found none of the 18 error bars in 127 and
    # the figure had no dispersion at all. Measured against the stem instead,
    # every cap in all three figures reads between 5 and 11 times its own stem
    # and every non-cap row reads 1.0-1.2.
    cap_rows, cap_span, stem_px = [], 0.0, 0
    if stem_rows:
        tip = stem_rows[-1]
        stem_px = min(spread(r) for r in stem_rows)
        floor = max(3 * stem_px, 3 * stroke)
        # Beyond the bar, which is where `start` ends - not "more than a stroke
        # from the edge". That older form was consistent with a fixed one-stroke
        # skip and stopped being so when the skip was measured: on a bar whose
        # whole error bar is four rows, it excluded the cap itself.
        for r in [x for x in range(tip - 2 * stroke, tip + 2 * stroke + 1)
                  if 0 <= x < height and (x - start) * step > 0]:
            width = spread(r)
            if not width or width < floor:
                continue
            if not (dark[r, :track].any() and dark[r, -track:].any()):
                cap_rows.append(r)
                cap_span = max(cap_span, width / float(bar_w))
    masked = dark.copy()
    for r in stem_rows:
        masked[r, band] = False
    for r in cap_rows:
        masked[r, :] = False

    inked = [r for r in scan if masked[r].any()]
    out = []
    if cap_rows:
        out.append(dict(kind="ERRORBAR_CAP",
                        distance_px=int(abs(cap_rows[0] - edge)),
                        extent_px=int(len(cap_rows)),
                        side_track_fraction=0.0,
                        span_fraction=round(float(cap_span), 3),
                        occupied_bins=0,
                        connection_fraction=1.0,
                        stem_width_px=int(stem_px),
                        cap_width_px=int(round(cap_span * bar_w)),
                        centre_row_panel=int(round(float(np.mean(cap_rows))))))
    if not inked:
        return out
    components, current = [], [inked[0]]
    for r in inked[1:]:
        if abs(r - current[-1]) <= max(1, stroke // 2):
            current.append(r)
        else:
            components.append(current)
            current = [r]
    components.append(current)

    for comp in components:
        band = masked[min(comp):max(comp) + 1]
        extent = len(comp)
        both_tracks = float(np.mean([bool(masked[r, :track].any() and
                                          masked[r, -track:].any()) for r in comp]))
        columns = band.any(axis=0)
        occupied = np.where(columns)[0]
        span = ((occupied[-1] - occupied[0] + 1) / float(bar_w)) if len(occupied) else 0.0
        bins = sum(1 for part in np.array_split(columns, 5) if part.any())
        # Continuous with the bar? After masking, the only way to be connected
        # is to run down to the bar end through ink of your own. This is not a
        # "central stem fraction", which is what it used to be called - the stem
        # has been masked out by this point and cannot contribute to it.
        gap = [r for r in range(edge, comp[0], step) if 0 <= r < height]
        joined = (float(np.mean([bool(masked[r].any()) for r in gap]))
                  if gap else 1.0)
        distance = int(abs(comp[0] - edge))
        thick = extent >= 2 * stroke
        body_like = both_tracks >= 0.5 or (span >= 0.55 and bins >= 3 and thick)
        # Does it carry on past the footprint? Only counted when the component
        # actually reaches the footprint's edge, so a cap in the middle of the
        # bar cannot inherit a neighbour's ink on the same rows.
        # ADJACENT, row by row: the component's own edge pixel and the margin
        # pixel beside it, inked on the same row. "The component reaches the
        # edge and there is ink somewhere in the margin at these rows" is a
        # weaker claim that the same evidence satisfies - and NEIGHBOUR_STRUCTURE
        # is the one classification that LIFTS a refusal, so a false positive
        # here returns a number instead of withholding one. Two shapes it would
        # have got wrong: a narrow unidentified thing at the edge with unrelated
        # annotation beside it, and a footprint that UNDER-covers its own bar,
        # whose side stroke then continues into the margin because it is the
        # bar's.
        #
        # NOT PINNED BY A SCENARIO. A synthetic sliver at the footprint edge is
        # picked up as a stem candidate and masked before it can become a
        # component, so no fixture reaches this branch; what is known is that
        # tightening the test from "ink somewhere in the margin" to "adjacent,
        # row by row" took the corpus from four NEIGHBOUR_STRUCTURE components
        # to two without changing a single value, which is two false positives
        # removed.
        beyond = bool(
            (right_margin.size
             and any(masked[r, -1] and right_margin[r, 0] for r in comp))
            or (left_margin.size
                and any(masked[r, 0] and left_margin[r, -1] for r in comp)))
        # Only for a component that does NOT look like a bar body. A footprint
        # can also UNDER-cover its bar, and then the margin holds this bar's own
        # ink - which is what the full-width hatch above a printing gap looked
        # like, and it was being handed to the neighbour. A sliver at one edge is
        # the case this test is for; a body-shaped component is judged as a body.
        if beyond and not body_like:
            kind = "NEIGHBOUR_STRUCTURE"
        elif extent < stroke and distance <= stroke:
            # Nothing is printed thinner than one stroke, so a sub-stroke
            # component lying against the bar end is the bar's own antialiased
            # edge or the ringing around it - the row the walk stopped just
            # below. Both conditions are needed: a one-pixel mark a hundred
            # pixels away is a glyph and is classified as one. Without this,
            # three of publication 127's cells refused themselves over a single
            # row of grey left behind when the scan start was measured instead
            # of assumed.
            kind = "BAR_EDGE_REMNANT"
        elif body_like and joined >= 0.5:
            kind = "BODY_CONTINUATION"
        elif body_like and distance <= reach:
            # Body-shaped, close enough for the gap to be a printing artefact,
            # and not continuous. This is the case that used to be dismissed as
            # an annotation: a stipple whose top row happens to be blank, or an
            # outline broken by the rescan, is exactly this shape, and calling
            # it a glyph let the bar keep a value measured below its own top.
            kind = "UNRESOLVED_REMOTE_SUPPORT"
        elif joined < 0.5:
            kind = "ANNOTATION_OR_GLYPH"
        else:
            kind = "UNRESOLVED_REMOTE_SUPPORT"
        out.append(dict(kind=kind, distance_px=distance,
                        extent_px=int(extent), side_track_fraction=round(both_tracks, 3),
                        span_fraction=round(float(span), 3), occupied_bins=int(bins),
                        connection_fraction=round(joined, 3),
                        body_like=bool(body_like), reach_px=int(reach),
                        centre_row_panel=int(round(float(np.mean(comp))))))
    return out


def texture(gray, box, window, footprint, edge_row, zero_row, stroke,
            direction="UP"):
    """Everything about the ink inside one bar, at four thresholds and none.

    The interior is the middle of the bar in both axes, as a FRACTION of the
    bar: the old reader sampled a fixed 40 px starting 6 px in, which is most of
    a 55 px bar and a quarter of a 188 px one.

    `edge_row` and `zero_row` are BOX-relative, like everything else here, and
    the columns are absolute. The first version of this sliced `gray` with the
    box-relative rows and the absolute columns in the same expression, so on
    publication 127 - panel top at page row 1580 - every texture number came
    from a band 1159 px above the panel. It read white paper and reported
    `ink_mass 0.000` for a solid black bar, and that number is what the fill
    vocabulary was about to be built on.

    A bar too short to have an interior gets nothing. The bar's own top rule and
    the baseline rule are each a stroke thick, so on publication 127's middle
    panel - SUPINE bars 15 px tall at a stroke of 5 - the two rules ARE the bar,
    and the previous version, whose inset collapsed back to the full bar when
    the inset left nothing, reported an OPEN bar at `ink_mass 0.517` and a SOLID
    one at 0.876. Sampling the strokes and calling it fill would have taught the
    fill vocabulary that OPEN is half black.
    """
    x0, x1, y0, y1 = map(int, box)
    xa, _xb = window
    fx0, fx1 = footprint
    bar_w = fx1 - fx0 + 1
    inset = max(stroke, int(round(0.12 * bar_w)))
    ca, cb = xa + fx0 + inset, xa + fx1 + 1 - inset
    top, bottom = (edge_row, zero_row) if direction == "UP" else (zero_row, edge_row)
    top, bottom = int(round(min(top, bottom))), int(round(max(top, bottom)))
    height = bottom - top
    #: The thinnest strip of interior worth a number: two strokes, so it cannot
    #: be one rule and its antialiasing.
    floor = max(3, 2 * stroke)
    if height < 4 or cb - ca < floor:
        return None
    keep_top = top + max(2 * stroke, int(round(0.12 * height)))
    keep_bottom = bottom - max(2 * stroke, int(round(0.10 * height)))
    if keep_bottom - keep_top < floor:
        return None
    roi = gray[y0 + keep_top:y0 + keep_bottom, ca:cb]
    if roi.size == 0:
        return None
    # How much `ink_mass` moves across the bar's own interior. This is the
    # measurement's uncertainty, taken from the bar rather than asserted: a
    # stipple's tiles disagree by a few hundredths and a solid bar's by nothing,
    # so a figure with one group - where no pattern has a spread across groups -
    # still has a floor to hold "least ink" and "most ink" to.
    _tiles = np.array_split(roi, min(6, max(2, roi.shape[0] // 4)))
    _mass = [float((1.0 - t / 255.0).mean()) for t in _tiles if t.size]
    out = dict(bar_width=int(bar_w), bar_height=int(height),
               roi_shape=[int(roi.shape[0]), int(roi.shape[1])],
               ink_mass_tile_spread=round(max(_mass) - min(_mass), 4)
               if _mass else 0.0,
               # No threshold at all: how much ink is on the paper, 0 for white
               # and 1 for black. A feature that needs no cut point cannot be
               # wrong about where the cut point should be.
               ink_mass=round(float((1.0 - roi / 255.0).mean()), 4))
    for t in THRESHOLDS:
        d = roi < t
        rows = d.mean(axis=1)
        # Median over vertical tiles, not one mean: a stipple's dot phase makes
        # individual rows swing between 0 and 0.3.
        tiles = np.array_split(d, min(6, max(2, d.shape[0] // 4)))
        tile_cov = [float(t_.mean()) for t_ in tiles if t_.size]
        cols = [i for i, v in enumerate(d.mean(axis=0)) if v >= SEED_SUPPORT]
        segs = _runs(cols, gap=max(2, stroke))
        out["t%d" % t] = dict(
            coverage=round(float(d.mean()), 4),
            coverage_median_tile=round(float(np.median(tile_cov)) if tile_cov else 0.0, 4),
            row_coverage_min=round(float(rows.min()), 4),
            column_segments=len(segs),
            # Normalised, because a raw count grows with bar width, stipple
            # pitch and DPI. Segments per stroke-width of bar.
            segment_density=round(len(segs) * stroke / float(bar_w), 4))
    return out


def measure_panel(spec):
    """One record per declared bar of one panel.

    Row coordinates come in two frames and both are named in every field that
    carries one. `*_row_panel` counts from the top of the panel BOX, which is
    what every array in this file is sliced to; `*_px_image` counts from the top
    of the page, which is what an axis calibration takes. Publication 127's
    panels start at page rows 620, 1580 and 2510, so a panel row handed to a
    calibration is out by that much: the error bar drawn 25 px above a bar top
    reported a dispersion of 142 units instead of 8.3.
    """
    gray = _gray(spec["path"])
    box = spec["box"]
    x0, x1, y0, y1 = map(int, box)
    # Calibration first, because the stroke is the thickness of the rule at the
    # BASELINE and the baseline is where the calibration says the zero is.
    cal = MR.AxisCalibration.from_points([tuple(t) for t in spec["ticks"]])
    zero = int(round(cal.value_to_pixel(spec.get("baseline", 0.0)))) - y0
    scale = stroke_scale(gray, box, baseline_row=zero)
    fills = spec["fills"]
    records = []
    if not scale.ok:
        return [dict(figure=spec["tag"], group=None, stroke=scale.as_dict(),
                     error="STROKE_SCALE_UNRESOLVED")]
    stroke = scale.value_px
    figure_id = spec.get("figure_id", spec["tag"])
    for label, gx in spec["anchors"].items():
        gw = spec["group_window"]
        window = (max(x0, int(gx) - gw), min(x1, int(gx) + gw + 1))
        # Direction is measured, not declared: whichever side of the baseline
        # carries seed support is the side the bars are on.
        support = {}
        for candidate in ("UP", "DOWN"):
            segs, pers = seed_support(gray, box, zero, stroke, window,
                                      direction=candidate)
            support[candidate] = (sum(len(g) for g in segs), segs, pers)
        (up_total, up_segs, up_pers) = support["UP"]
        (down_total, down_segs, down_pers) = support["DOWN"]
        # Nothing on either side of the baseline. Falling through to the tie
        # test does not catch this - `min(0, 0) > 0` is false - so the group
        # went on to footprint an empty segment list, got no footprints back,
        # and DISAPPEARED: no record, no error, and a panel that quietly
        # reported fewer bars than it declared.
        if max(up_total, down_total) == 0:
            records.append(dict(figure=spec["tag"], group=label,
                                error="NO_SEED_SUPPORT",
                                up_support=0, down_support=0,
                                window=[int(window[0]), int(window[1])]))
            continue
        # A tie is not UP. Checking UP first and only replacing on a strictly
        # greater total meant an equal split - possible on a very short bar, or
        # on baseline noise - silently declared the bars upward.
        margin = max(2 * stroke, int(round(0.10 * max(up_total, down_total))))
        if abs(up_total - down_total) <= margin and min(up_total, down_total) > 0:
            records.append(dict(figure=spec["tag"], group=label,
                                error="BAR_DIRECTION_UNRESOLVED",
                                up_support=up_total, down_support=down_total,
                                margin=margin))
            continue
        direction = "UP" if up_total >= down_total else "DOWN"
        segments = up_segs if direction == "UP" else down_segs
        persistence = up_pers if direction == "UP" else down_pers
        # Does the group run off the end of the window it was given? If the
        # outermost column of the window is itself seeded, the bar there has no
        # measured right (or left) edge - and `footprints_from_seed` divides the
        # span it CAN see by the declared bar count, so a window 22 px short on
        # publication 127 moved every boundary and put the neighbouring bar's
        # right stroke inside the last bar's footprint. The last bar then traced
        # its neighbour's outline and read 3.37 where the bar was 1.5.
        #
        # An anchor that is off-centre is a geometry error and this is where it
        # becomes visible, so it must refuse rather than widen the window
        # itself: widening would move the boundary again with nothing to check
        # it against.
        clipped = [side for side, v in (("LEFT", persistence[0]),
                                        ("RIGHT", persistence[-1]))
                   if v >= SEED_SUPPORT]
        if clipped:
            records.append(dict(figure=spec["tag"], group=label,
                                error="GROUP_WINDOW_CLIPPED", clipped_at=clipped,
                                direction=direction,
                                window=[int(window[0]), int(window[1])],
                                seed_extent=[int(segments[0][0]),
                                             int(segments[-1][-1])] if segments else None))
            continue
        prints, bounds = footprints_from_seed(segments, len(fills))
        for k, fp in enumerate(prints):
            rec = dict(figure=spec["tag"], figure_id=figure_id, group=label,
                       slot=k, declared=fills[k], stroke_px=stroke,
                       direction=direction,
                       # What the group is SUPPOSED to hold, on every record.
                       # Without it a group is only knowable from the records
                       # that came back, so a record lost to a defect takes its
                       # declaration with it and the remainder looks complete.
                       declared_group_size=len(fills),
                       declared_group_patterns=sorted(fills))
            if fp is None:
                rec["error"] = "NO_SEED_SUPPORT"
                records.append(rec)
                continue
            # The bar end and the footprint, refined against each other.
            fp0 = fp
            fp, edge, method, dropped, refusal, detail = refine_footprint(
                fp0,
                lambda f: trace_extent(gray, box, window, f, zero, stroke,
                                       direction=direction),
                lambda f, e: trim_to_own_bar(gray, box, window, f, e, zero,
                                             stroke, direction=direction))
            if dropped:
                rec["trimmed_columns"] = dropped
                rec["provisional_footprint"] = [int(fp0[0]), int(fp0[1])]
            if refusal:
                rec["error"] = refusal
                rec.update(detail)
                records.append(rec)
                continue
            remote = remote_support(gray, box, window, fp, edge, zero, stroke,
                                    direction=direction)
            body = [r for r in remote if r["kind"] == "BODY_CONTINUATION"]
            unresolved = [r for r in remote
                          if r["kind"] == "UNRESOLVED_REMOTE_SUPPORT"]
            caps = [r for r in remote if r["kind"] == "ERRORBAR_CAP"]
            cap_row = caps[0]["centre_row_panel"] if caps else None
            rec.update(slot_bounds=(list(bounds[k]) if bounds[k] else None),
                       # Both frames, both named. The bare `cap_px` this
                       # replaced held a PANEL row under a name the production
                       # reader uses for a PAGE row, and the production reader
                       # feeds it straight to a calibration.
                       edge_row_panel=round(edge, 1),
                       edge_px_image=round(y0 + edge, 1),
                       cap_row_panel=cap_row,
                       cap_px_image=(None if cap_row is None else y0 + cap_row),
                       support=method, remote=remote,
                       # Only a body continuation says the walk was wrong.
                       contradiction_px=(min(r["distance_px"] for r in body)
                                         if body else 0),
                       footprint=[int(fp[0]), int(fp[1])],
                       footprint_width=int(fp[1] - fp[0] + 1),
                       seed_segments=len([s for s in segments
                                          if fp[0] <= s[0] <= fp[1]]))
            # Fail closed, and closed means the number does not exist. The
            # previous version put the classification in the record and then
            # carried on to write `value` and a full texture block anyway, so a
            # bar whose top was in doubt entered the fill-identity step as a
            # clean prototype sample - which is the one place where a wrong
            # number does the most damage, because it becomes the definition
            # every other bar is matched against.
            #
            # BODY_CONTINUATION means the top is known to be wrong.
            # UNRESOLVED_REMOTE_SUPPORT means it is not known to be right, which
            # for a prototype is the same thing.
            reason = ("BAR_EXTENT_UNRESOLVED" if body else
                      "REMOTE_SUPPORT_UNRESOLVED" if unresolved else "")
            if reason:
                rec["error"] = reason
                rec["provisional_value"] = round(cal.pixel_to_value(y0 + edge), 3)
                records.append(rec)
                continue
            rec["value"] = round(cal.pixel_to_value(y0 + edge), 3)
            # The dispersion the cap implies, computed HERE rather than left to
            # a caller, because computing it is what proves the two rows are in
            # the same frame. A cap row in panel coordinates against a mean in
            # page coordinates produces a number - it just is not a dispersion.
            if cap_row is not None:
                rec["dispersion"] = round(
                    abs(cal.pixel_to_value(y0 + cap_row) - rec["value"]), 3)
            tex = texture(gray, box, window, fp, edge, zero, stroke,
                          direction=direction)
            if tex is None:
                rec["error"] = "BAR_TOO_SMALL_TO_SAMPLE"
            else:
                rec.update(tex)
            # Whether a fill was SAMPLED, which is not whether the series was
            # IDENTIFIED. This function measures one panel and identity is
            # figure-local, so nothing here can name a series; the two were one
            # field called `identity_status` and the forward tests were counting
            # samples while saying "identities". `fill_identities_by_figure`
            # sets `identity_status` and `resolved_fill_pattern`.
            #
            # `declared` is the spec's DECLARATION, to be checked against what
            # the fill measures - never an identification. Calling a bar OPEN
            # because it is the first slot is identifying a series by position.
            rec["fill_sample_status"] = ("MEASURED" if tex is not None
                                         else "UNRESOLVED_NO_INTERIOR")
            rec["identity_status"] = "NOT_CALIBRATED"
            records.append(rec)
    return records


def builtin_specs():
    """Every real or synthetic monochrome bar panel the package ships."""
    specs = [
        dict(tag="397_fig3_P3_MEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=[118, 480, 90, 470], ticks=[[150.0, 101.0], [50.0, 465.0]],
             anchors={"PRE": 187, "POST": 390}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0, figure_id="397_fig3"),
        # The second panel of the SAME figure, four pixels of axis apart from
        # the first. Sharing one calibration between them put this one's
        # baseline below its own bars and returned nothing for all four of its
        # cells, which is why the production reader takes geometry per panel -
        # and why measuring only the first panel here would have left the
        # prototype's version of that mistake undetected.
        dict(tag="397_fig3_P3_WOMEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=[620, 1010, 88, 466], ticks=[[150.0, 95.0], [50.0, 460.0]],
             anchors={"PRE": 720, "POST": 920}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0, figure_id="397_fig3"),
    ]
    truth = os.path.join(HERE, "mono_bar_fixture_truth.json")
    if os.path.exists(truth):
        with open(truth, encoding="utf-8") as fh:
            cfg = json.load(fh)
        specs.append(dict(
            tag="mono_fixture", path=os.path.join(HERE, "mono_bar_fixture.png"),
            box=cfg["panel_box"], ticks=cfg["y_ticks"],
            anchors={g: x for g, x in zip(cfg["groups"], cfg["group_x"])},
            fills=cfg["patterns"], group_window=60, baseline=0.0))
    return [s for s in specs if os.path.exists(s["path"])]


def load_specs(paths, raster_root=""):
    """Extra geometries, each checked against the raster it was measured on."""
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for spec in json.load(fh):
                # Resolved against --raster-root, then the spec's own
                # directory. The spec is versioned and the raster is not, so
                # the spec must not name a directory on the machine it was
                # written on.
                raster = spec["path"]
                if not os.path.isabs(raster):
                    for root in [r for r in (raster_root, os.path.dirname(path)) if r]:
                        candidate = os.path.join(root, raster)
                        if os.path.exists(candidate):
                            raster = candidate
                            break
                spec["path"] = raster
                if not os.path.exists(raster):
                    print("SKIP %s: %s is not on this machine" % (spec["tag"], raster))
                    continue
                want = str(spec.get("raster_sha256", "")).strip().lower()
                if want:
                    with open(raster, "rb") as fh2:
                        got = hashlib.sha256(fh2.read()).hexdigest()
                    if got != want:
                        print("SKIP %s: raster hashes %s..., the spec says %s..."
                              % (spec["tag"], got[:16], want[:16]))
                        continue
                out.append(spec)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", default="")
    ap.add_argument("--extra", action="append", default=[],
                    help="JSON of further panel geometries (repeatable)")
    ap.add_argument("--raster-root", default=os.environ.get("FDT_RASTER_ROOT", ""),
                    help="where the private rasters the geometry specs name live")
    ap.add_argument("--specs-dir", default=os.path.join(HERE, "geometry"),
                    help="directory of versioned *.geometry.json specs")
    args = ap.parse_args(argv)

    specs = builtin_specs()
    if os.path.isdir(args.specs_dir):
        specs += load_specs(sorted(
            os.path.join(args.specs_dir, f) for f in os.listdir(args.specs_dir)
            if f.endswith(".geometry.json")), raster_root=args.raster_root)
    specs += load_specs(args.extra, raster_root=args.raster_root)

    everything = []
    print("%-20s %-8s %-4s %-9s %-4s %-7s %-7s %-16s %s"
          % ("figure", "group", "slot", "declared", "dir", "value", "inkmass",
             "support", "coverage/segments t=96,128,160,192"))
    for spec in specs:
        for r in measure_panel(spec):
            everything.append(r)
            if r.get("error"):
                # The provisional number is printed so the refusal can be
                # audited, and printed in brackets so it cannot be mistaken for
                # a reading. Nothing downstream may read it.
                prov = ("  (value %.2f, no fill)" % r["value"]
                        if "value" in r else
                        "  (provisional %.2f)" % r["provisional_value"]
                        if "provisional_value" in r else "")
                print("%-20s %-8s %-4s %-9s  %s%s"
                      % (r["figure"], r.get("group"), r.get("slot"),
                         r.get("declared"), r["error"], prov))
                continue
            cells = " ".join("%.2f/%d" % (r["t%d" % t]["coverage_median_tile"],
                                          r["t%d" % t]["column_segments"])
                             for t in THRESHOLDS)
            print("%-20s %-8s %-4d %-9s %-4s %-7.2f %-7.3f %-16s %s"
                  % (r["figure"], r["group"], r["slot"], r["declared"],
                     r["direction"], r.get("value", float("nan")), r["ink_mass"],
                     "%s%s" % (r["support"],
                               "" if not r["contradiction_px"]
                               else " !%d" % r["contradiction_px"]), cells))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(everything, fh, indent=1)
        print("\nwrote %s (%d records)" % (args.json, len(everything)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#: What each printed word MEANS about the interior, as a relation rather than a
#: number. Nothing here is a measurement, and nothing here is figure-specific:
#: these are the properties that make the words the words.
#:
#:   OPEN      the interior is paper - it has the LEAST ink of the group
#:   SOLID     the interior is ink - it has the MOST
#:   HATCHED   continuous strokes, so every row of the interior is crossed
#:   STIPPLED  isolated islands, so some rows of the interior are blank
#:
#: The first two are relations WITHIN a group and say nothing about absolute
#: density; the last two are structural and say nothing about which is darker.
#: That matters: a dense stipple can carry more ink than a sparse hatch, so
#: ordering all four by ink would be a claim about typesetting, not about the
#: words. The measured corpus happens to run OPEN 0.000, STIPPLED 0.14-0.16,
#: HATCHED 0.26-0.32, SOLID 0.73-1.00, and the identity does not rely on it.
FILL_VOCABULARY = ("OPEN", "STIPPLED", "HATCHED", "SOLID")


def _sample(rec):
    """The three numbers the identity is decided on, or None."""
    if "ink_mass" not in rec or "t128" not in rec:
        return None
    return dict(ink=float(rec["ink_mass"]),
                noise=float(rec.get("ink_mass_tile_spread", 0.0)),
                rows_all_inked=float(rec["t128"]["row_coverage_min"]) > 0.0,
                segments=float(rec["t128"]["segment_density"]))


def _structurally_possible(pattern, sample):
    """Whether the word can describe this interior at all, ink aside."""
    if pattern == "HATCHED":
        return sample["rows_all_inked"]
    if pattern == "STIPPLED":
        return not sample["rows_all_inked"]
    return True


def _assign_group(samples, declared):
    """One slot to one pattern, from the group's own ink and structure.

    `samples` is {slot: sample} and `declared` the multiset of patterns the
    group is supposed to contain. Returns {slot: pattern} or None - and None is
    the answer whenever the assignment is not FORCED, because the alternative is
    naming a series by where it sits.
    """
    if len(samples) != len(declared) or len(set(declared)) != len(declared):
        return None                # a repeated fill cannot identify anything
    left, want = dict(samples), list(declared)
    by_ink = sorted(left, key=lambda s: left[s]["ink"])
    out = {}
    if "OPEN" in want:
        out[by_ink[0]] = "OPEN"
        want.remove("OPEN")
    if "SOLID" in want:
        out[by_ink[-1]] = "SOLID"
        want.remove("SOLID")
    if len(set(out.values())) != len(out):
        return None
    rest = [s for s in by_ink if s not in out]
    if sorted(want) == ["HATCHED", "STIPPLED"]:
        hatched = [s for s in rest if left[s]["rows_all_inked"]]
        stippled = [s for s in rest if not left[s]["rows_all_inked"]]
        if len(hatched) != 1 or len(stippled) != 1:
            return None
        out[hatched[0]], out[stippled[0]] = "HATCHED", "STIPPLED"
    elif len(want) == 1 and len(rest) == 1:
        out[rest[0]] = want[0]
    elif want or rest:
        return None
    return out if len(out) == len(samples) else None


def fill_identity(records):
    """Name the series of one FIGURE by fill, from that figure's own samples.

    A figure, not a panel. Publication 127's Figure 4 is three sub-panels, and
    its middle panel alone offers one sample of each pattern - one sample has no
    spread, a figure with no spread has no estimate of its own measurement
    noise, and nothing can be matched against a prototype of zero width. Pooled
    across the figure the same patterns have a spread of 0.00-0.02 against gaps
    of 0.58, and the three cells that panel could not calibrate on its own are
    matched immediately. `figure_id` is what says which panels are one figure;
    it defaults to the panel tag, which makes a lone panel its own figure.

    Two stages, because a bar too short to sample a fill would otherwise take
    the identity of whichever slot it sits in.

    **Calibrate.** Only groups where EVERY slot yielded a fill can be assigned
    from the relations above, because "least ink in the group" is not a
    statement about a group with a hole in it. Those groups give the figure its
    own prototype range for each pattern.

    **Match.** Every remaining sample is matched against those ranges, and only
    when it falls inside exactly one of them.

    The separation test needs no threshold. Each pattern's samples across the
    figure have a SPREAD, and each pair of patterns has a GAP; the vocabulary is
    established only when every gap is larger than the spreads it separates. On
    publication 127 the spreads are 0.00-0.02 and the smallest gap is 0.58. A
    pattern seen once has no spread of its own and inherits the widest spread in
    the figure, so it is held to the same standard rather than to none.

    Returns (identities, verdict). `identities` maps (panel, group, slot) to a
    pattern for every cell that has one, and `verdict["status"]` is one of:

      ESTABLISHED   every complete group assigned, and the figure has shown how
                    much a pattern varies - at least two complete groups and a
                    non-zero spread - so the prototype ranges are reusable and
                    incomplete groups are matched against them.
      DIRECT_ONLY   every complete group assigned, but from a single group, so
                    every prototype range has zero width. Those groups keep
                    their identities; nothing is matched against them.
      AMBIGUOUS     a group could not be assigned, or two patterns are closer
                    than one of them varies. Nothing is named.
      NOT_ENOUGH_COMPLETE_GROUPS   no group had a fill in every slot.

    All records must belong to ONE figure; pass mixed figures and this refuses
    with MULTIPLE_FIGURES rather than pooling two publications into one
    vocabulary. `fill_identities_by_figure` does the splitting.
    """
    figure_ids = {r.get("figure_id", r.get("figure")) for r in records}
    if len(figure_ids) > 1:
        return {}, dict(status="MULTIPLE_FIGURES",
                        figure_ids=sorted(str(f) for f in figure_ids))
    groups, declared, expected = {}, {}, {}
    for rec in records:
        if rec.get("group") is None or rec.get("slot") is None:
            continue
        # Panel AND group. The three sub-panels of publication 127's Figure 4
        # each have a SUPINE and a STANDING group, and pooling them by name
        # alone would make one group out of three.
        key = (rec["figure"], rec["group"])
        groups.setdefault(key, {})[rec["slot"]] = _sample(rec)
        declared.setdefault(key, {})[rec["slot"]] = rec.get("declared")
        if rec.get("declared_group_size") is not None:
            expected[key] = (int(rec["declared_group_size"]),
                             sorted(rec.get("declared_group_patterns") or []))

    complete, partial, truncated = {}, {}, {}
    for key, slots in groups.items():
        size, patterns = expected.get(key, (len(slots), sorted(
            v for v in declared[key].values() if v)))
        arrived = sorted(v for v in declared[key].values() if v)
        if len(slots) != size or arrived != patterns:
            # A slot the panel declared did not come back at all. The records
            # that DID come back may every one of them carry a fill, and the
            # group is still not complete - and it cannot be told apart from a
            # smaller group unless the declaration travels on the records.
            truncated[key] = sorted(set(range(size)) - set(slots))
            partial[key] = slots
        elif all(v is not None for v in slots.values()):
            complete[key] = slots
        else:
            partial[key] = slots

    assigned, unassignable = {}, []
    for key, slots in complete.items():
        want = [declared[key][s] for s in sorted(slots)]
        got = _assign_group(slots, want)
        if got is None:
            unassignable.append(key)
            continue
        for slot, pattern in got.items():
            assigned[(key, slot)] = pattern

    if not assigned:
        # "No complete group" and "complete groups nobody could assign" are
        # different findings and were reported as the same one, which also sent
        # every measured bar to NOT_CALIBRATED when the truth was AMBIGUOUS.
        return {}, dict(status="AMBIGUOUS" if unassignable
                        else "NOT_ENOUGH_COMPLETE_GROUPS",
                        prototype_ready=False,
                        complete_groups=len(complete),
                        truncated_groups={str(k): v for k, v in truncated.items()},
                        unassignable_groups=sorted(str(k) for k in unassignable))

    pooled = {}
    for (key, slot), pattern in assigned.items():
        pooled.setdefault(pattern, []).append(groups[key][slot]["ink"])
    spread = {p: max(v) - min(v) for p, v in pooled.items()}
    noise = max([groups[k][s]["noise"] for k, s in assigned] or [0.0])
    floor = max(max(spread.values()), noise)
    # A prototype RANGE is only reusable when the figure has shown how much a
    # pattern varies. One complete group gives one sample per pattern, every
    # spread is zero, and a zero-width range with a zero tolerance would match
    # nothing honestly and everything by luck - so that case assigns the groups
    # it can read directly and refuses to match anything else against them.
    # This is what the docstring always claimed and the code did not do: it
    # reported ESTABLISHED off a single group because any non-zero gap beats a
    # zero floor.
    prototype_ready = len(complete) >= 2

    order = sorted(pooled, key=lambda p: min(pooled[p]))
    gaps, failures = [], []
    for a, b in zip(order, order[1:]):
        gap = min(pooled[b]) - max(pooled[a])
        need = max(spread[a], spread[b], floor)
        # HATCHED and STIPPLED are told apart by whether any interior row is
        # blank, not by how much ink there is, so requiring an ink gap between
        # them is the ordering this file refuses, smuggled back in as a
        # validity test: a sparse hatch and a dense stipple are correctly named
        # by structure and have no gap to show. Every other pair IS decided on
        # ink and has to earn it.
        structural = {a, b} == {"HATCHED", "STIPPLED"}
        gaps.append(dict(between=[a, b], gap=round(gap, 4),
                         needed=(None if structural else round(need, 4)),
                         separated_by="STRUCTURE" if structural else "INK"))
        if not structural and gap <= need:
            failures.append("%s/%s gap %.4f against spread %.4f" % (a, b, gap, need))

    clean = not (failures or unassignable)
    verdict = dict(status=("ESTABLISHED" if clean and prototype_ready
                           else "DIRECT_ONLY" if clean else "AMBIGUOUS"),
                   prototype_ready=bool(prototype_ready),
                   complete_groups=len(complete),
                   truncated_groups={str(k): v for k, v in truncated.items()},
                   unassignable_groups=sorted(str(k) for k in unassignable),
                   prototypes={p: [round(min(v), 4), round(max(v), 4)]
                               for p, v in sorted(pooled.items())},
                   separation=gaps, failures=failures)
    if verdict["status"] == "AMBIGUOUS":
        return {}, verdict
    if verdict["status"] == "DIRECT_ONLY":
        # The complete groups were assigned from relations inside themselves,
        # which stands on its own. Nothing else may lean on it.
        verdict["matched_against_prototypes"] = 0
        verdict["cells_identified"] = len(assigned)
        return assigned, verdict

    matched = 0
    for key, slots in partial.items():
        # Only the patterns THIS group declares. Matching against every
        # prototype in the figure can return a pattern the group does not
        # contain: a partial group declaring OPEN and STIPPLED could come back
        # SOLID because its one sample happened to reach the SOLID range.
        allowed = set(declared[key].values())
        for slot, sample in slots.items():
            if sample is None:
                continue
            # Structure decides HATCHED against STIPPLED here as well. Matching
            # on ink alone throws away the only evidence that separates them and
            # re-introduces the ordering this file refuses to make: a hatched
            # bar whose density drifts into the stipple range would be renamed,
            # silently, against a row structure that says it cannot be one.
            hits = [p for p, v in pooled.items()
                    if p in allowed and _structurally_possible(p, sample)
                    and min(v) - floor <= sample["ink"] <= max(v) + floor]
            if len(hits) == 1:
                assigned[(key, slot)] = hits[0]
                matched += 1
    verdict["matched_against_prototypes"] = matched
    verdict["cells_identified"] = len(assigned)
    return assigned, verdict


#: What `identity_status` on a record can say once the figure has been resolved.
IDENTITY_STATES = ("RESOLVED", "AMBIGUOUS", "NOT_CALIBRATED",
                   "UNRESOLVED_NO_FILL")


def fill_identities_by_figure(records):
    """Resolve every figure in `records` and write the answer onto the records.

    The public entry point, because `fill_identity` takes one figure and a
    caller holding a batch has several. Each record gains:

      fill_sample_status    MEASURED / UNRESOLVED_NO_INTERIOR (set at measure
                            time; whether there was an interior to sample)
      identity_status       RESOLVED / AMBIGUOUS / NOT_CALIBRATED /
                            UNRESOLVED_NO_FILL
      resolved_fill_pattern the pattern, or "" - and this, not `declared`, is
                            what names the series

    Returns {figure_id: verdict}.
    """
    by_figure = {}
    for rec in records:
        by_figure.setdefault(rec.get("figure_id", rec.get("figure")), []).append(rec)
    verdicts = {}
    for figure_id, rows in by_figure.items():
        identities, verdict = fill_identity(rows)
        verdicts[figure_id] = verdict
        for rec in rows:
            if rec.get("group") is None or rec.get("slot") is None:
                continue
            key = ((rec["figure"], rec["group"]), rec["slot"])
            pattern = identities.get(key)
            if pattern:
                rec["identity_status"] = "RESOLVED"
                rec["resolved_fill_pattern"] = pattern
            else:
                rec["resolved_fill_pattern"] = ""
                rec["identity_status"] = (
                    "UNRESOLVED_NO_FILL"
                    if rec.get("fill_sample_status") != "MEASURED"
                    else "AMBIGUOUS" if verdict["status"] in
                    ("AMBIGUOUS", "MULTIPLE_FIGURES") else "NOT_CALIBRATED")
    return verdicts
