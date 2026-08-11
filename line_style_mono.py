"""LINE_MONO_STYLE: monochrome curves told apart by SOLID versus DASHED.

Publication 397 Figures 1, 2 and 5 are exactly this, and so are 121 of the 353
figures on the worklist: two black curves, no markers at all, and a legend that
says which is which. `read_monochrome_marker_panel` separates series by marker
shape and fill and has nothing to work with here, because there is no marker.
The discriminant has to be the ink's own stroke pattern.

## What the discriminant actually is

NOT the duty cycle, which was the obvious answer and the wrong one. The
fraction of columns a dash pattern inks depends on where in its phase the
window happens to open and on how much of the window is off the end of the
data; on the fixture the same dashed stroke measures anywhere from 0.605 to
0.81, straight through the bottom of the band a solid line occupies. THE
LONGEST RUN OF SKIPPED COLUMNS does not move: a solid stroke never has one, a
dash pattern has one every period however the window falls. Duty is kept for
what it can do, which is separate DOTTED from DASHED.

## What is not ink, and is removed before anything is traced

Three kinds of furniture measure as clean solid lines. Each was found on a real
figure and none was visible on the drawn fixture, which is why the fixture is
not the release gate:

* GRIDLINES. A rule spans the panel at a constant row: duty 1.000, gap 0. Four
  of them made five SOLID candidates at every x on 397, the count was never
  one, and the reader emitted no solid cells at all while reporting no problem.
* ERROR-BAR STEMS. Tall thin vertical runs, removed so they cannot be traced -
  which takes the curve's own two or three pixels with them at every stem.
* WHISKER CAPS. A cap is a short horizontal stroke and so is a steep curve, so
  length cannot tell them apart. A cap has a STEM UNDER IT and it ends.

Everything removed also BLINDS the accounting: a column we cannot see through
is not a column where the curve is absent. Scored as misses, the stems alone
gave every solid curve on 397 a gap of 3, one over the limit.

## The fit, and what it is and is not for

A whole-panel sequential tracer does not work. It has to survive every dash gap
on every slope in one pass, and a dash TIP - one row of a three-pixel stroke -
biases the run centre enough to lose a steep curve. One miss fragments the
series and the figure reads as containing a single curve.

A short windowed fit does work, with four details that each cost a debugging
round:

* fit a QUADRATIC. A straight fit through a local maximum leaves most of the
  window outside tolerance, and the solid curve at its own peak measured a duty
  of 0.47 and classified as dashed.
* count only the span the ink covers. At the first and last plotted point half
  the window is off the end of the data, and scoring those empty columns as
  misses halves the duty of a perfectly solid line.
* let the collection band FOLLOW the first fit. A flat band cannot hold a curve
  rising a pixel per column, and a band wide enough to hold one of two curves
  fourteen pixels apart swallows the other.
* READ THE VALUE OFF THE INK, not off the fit. The fit is a smoothing device
  and a quadratic rounds a corner; on 397 that put the solid curve 3.3 mmHg
  above where the eye reads it at the one position where it turns.

## Where it refuses

Two curves within a stroke's width of each other are one stroke, and nothing
local to that column says which is which. A style found somewhere on the panel
is expected everywhere on it, and a position where an expected style is missing
while another was found is a position where they merged: no cell for either
series. Likewise a dispersion is the connected column of ink through the mark -
where two error bars touch, the run holds both marks, and the cell keeps its
mean and reports no dispersion rather than the neighbour's cap.
"""
import numpy as np
import cv2
from PIL import Image

from mark_readers import (AxisCalibration, SeriesSpec, _runs,  # noqa: F401
                          _errorbar_around_marker)


LINE_STYLES = ("SOLID", "DASHED", "DOTTED")

#: Fraction of columns along a traced curve that carry real ink. Kept, because
#: it is what separates DOTTED from DASHED, and dropped as the SOLID/DASHED
#: discriminant - see below.
_STYLE_BANDS = {"SOLID": (0.88, 1.01), "DASHED": (0.35, 0.78), "DOTTED": (-0.01, 0.28)}

#: THE LONGEST RUN OF COLUMNS WITH NO INK, which is what actually tells a solid
#: line from a dashed one. Duty does not: the fraction a dash pattern measures
#: depends on where in its phase the window happens to open and on how much of
#: the window is off the end of the data, and on the fixture's own dashed curve
#: it ranges from 0.605 to 0.81 for the same stroke - straight through the
#: bottom of the SOLID band. The GAP does not move: a solid stroke has none, and
#: a dash pattern has one every period however the window is placed.
#:
#: In columns, and compared against the dash period rather than against a
#: number of pixels, so it says the same thing at any rendering.
_SOLID_MAX_GAP = 2

#: Two fitted centres closer than this are the same curve seen twice.
_SAME_CURVE_PX = 8.0
_DOTTED_MAX_DUTY = 0.30


def classify_line_style(duty, longest_gap=None):
    """SOLID / DASHED / DOTTED for a traced curve, or None.

    `longest_gap` is the run of columns the curve skipped. Without it the
    answer falls back to the duty bands, which is what the bare-duty callers
    (and the band scenarios) still ask for.
    """
    if longest_gap is None:
        hits = [k for k, (lo, hi) in _STYLE_BANDS.items() if lo <= duty < hi]
        return hits[0] if len(hits) == 1 else None
    if duty < _DOTTED_MAX_DUTY:
        return "DOTTED"
    if longest_gap <= _SOLID_MAX_GAP:
        return "SOLID" if duty >= _STYLE_BANDS["SOLID"][0] else None
    # A gap wider than half the window is not a dash pattern, it is two curves
    # or the end of one.
    return "DASHED" if duty >= _STYLE_BANDS["DASHED"][0] else None


def _vertical_strokes(mask, min_run=11):
    """The error-bar stems: tall thin vertical runs.

    A stem is a tall thin vertical run; a curve crossing one is two or three
    pixels of the same column. Opening with a tall thin kernel finds the stems
    exactly, and the two or three curve pixels inside a stem go with it.
    """
    tall = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_run)))
    return tall > 0


def _strip_vertical_strokes(mask, min_run=11):
    """The near-horizontal ink, with the stems taken out."""
    return mask & ~_vertical_strokes(mask, min_run=min_run)


#: A row has to be inked across this fraction of the panel to be a rule rather
#: than a datum. A gridline runs edge to edge in one row by definition; a curve
#: would have to be flat to the pixel across the whole panel to match it, and a
#: curve that flat carries no information the ladder does not already give.
_RULE_COVERAGE = 0.9


def _horizontal_rules(mask, x0, x1, coverage=_RULE_COVERAGE):
    """The gridlines and the frame, as a row mask.

    PUBLICATION 397'S GRIDLINES ARE PERFECT SOLID LINES. Every window over one
    measures a duty of 1.000 and a gap of 0, so each of the four gridlines
    inside the panel was a SOLID candidate at every x - four of them plus the
    real curve made five, the count for SOLID was never one, and the reader
    emitted no solid cells anywhere on the figure while looking entirely
    healthy. This is the first real figure it met and the defect was invisible
    on a synthetic fixture, which had no gridlines.

    Removed from the ink like the stems, and blinding like the stems: where a
    curve crosses a rule its own pixels go with the rule, and columns we cannot
    see through are not columns where the curve is absent.
    """
    width = max(1, int(x1) - int(x0))
    inked = mask[:, int(x0):int(x1)].sum(axis=1)
    rows = inked >= coverage * width
    out = np.zeros(mask.shape, dtype=bool)
    out[rows, :] = True
    return out & mask


def _cap_ink(mask, stems, half_window):
    """The error-bar caps: bounded horizontal runs at the ends of a stem.

    A CAP IS A SHORT HORIZONTAL STROKE AND SO IS A CURVE, seen through a small
    enough window, which is why this cannot be decided on the ink alone: a
    steeply falling curve occupies four columns of each row and would be erased
    by any length rule wide enough to catch a cap. What a cap has and a curve
    has not is a STEM UNDER IT - it sits at the extremity of a tall vertical
    run, and it ends.

    On publication 397 the solid curve turns down into 3:00 and its own upper
    caps stand right where the descending limb would have continued. Fitted
    together they measured a duty of 0.92 and a gap of 2 - a clean SOLID - and
    the reader answered 101.3 for a curve the eye reads at 98, while the real
    curve, merged with the dashed one six pixels below, went to the other
    series. Two confident numbers, both wrong, from one piece of furniture.
    """
    height, width = mask.shape
    out = np.zeros(mask.shape, dtype=bool)
    count, _labels, stats, _c = cv2.connectedComponentsWithStats(
        stems.astype(np.uint8), connectivity=8)
    reach = max(6, int(half_window) * 4)
    for i in range(1, count):
        c0 = int(stats[i, cv2.CC_STAT_LEFT])
        r0 = int(stats[i, cv2.CC_STAT_TOP])
        xc = c0 + int(stats[i, cv2.CC_STAT_WIDTH]) // 2
        r1 = r0 + int(stats[i, cv2.CC_STAT_HEIGHT]) - 1
        for end in (r0, r1):
            for row in range(end - 2, end + 3):
                if not (0 <= row < height) or not mask[row, xc]:
                    continue
                left = right = xc
                while left - 1 >= max(0, xc - reach) and mask[row, left - 1]:
                    left -= 1
                while right + 1 < min(width, xc + reach + 1) and mask[row, right + 1]:
                    right += 1
                if left <= xc - reach or right >= xc + reach:
                    continue      # it does not end inside the window: a curve
                out[row, left:right + 1] = True
    return out


def _column_runs(mask, x, max_thickness=7):
    """Vertical runs of ink in one column, narrow enough to be a curve."""
    idx = np.where(mask[:, x])[0]
    return [g for g in _runs(idx.tolist(), gap=1) if len(g) <= max_thickness]


def _line_fit_window(mask, x, y, half=22, band=5, tol=2.5, blind=None):
    """Duty cycle and refined y for the curve passing near (x, y).

    A whole-panel sequential tracer was the obvious way to do this and the wrong
    one. It has to survive every dash gap on every slope in one pass, and a dash
    TIP - where one row of a three-pixel stroke is inked - biases the run centre
    enough to lose the curve on a steep segment. One miss splits the series into
    fragments, none of which spans enough of the panel to be recognised, and the
    figure reads as containing one curve.

    Fitting a short window instead is both simpler and steadier. Every inked
    column within +/-`half` of x and +/-`band` rows of the seed contributes to
    one least-squares line, so tip bias averages out instead of accumulating;
    then duty is the fraction of columns carrying ink within `tol` of that line.
    Solid comes back near 1.0, a dash pattern near 0.6, and a whisker cap - which
    is 14 px of horizontal stroke in a 45 px window - near 0.3, so caps fall out
    on their own rather than needing to be recognised.

    Returns (duty, y_at_x, slope, longest_gap) or four Nones.
    """
    height, width = mask.shape
    lo_x, hi_x = max(0, x - half), min(width, x + half + 1)

    def collect(centre_at):
        """Ink centres per column, within `band` rows of a moving centre line."""
        out_x, out_y = [], []
        for xi in range(lo_x, hi_x):
            c = centre_at(xi)
            lo_y, hi_y = max(0, int(c) - band), min(height, int(c) + band + 1)
            idx = np.where(mask[lo_y:hi_y, xi])[0]
            if len(idx):
                out_x.append(xi)
                out_y.append(lo_y + float(np.mean(idx)))
        return out_x, out_y

    # First pass: a flat band around the seed, which is enough to establish the
    # slope. Second pass: the band FOLLOWS that first fit. A flat band cannot
    # hold a curve rising a pixel per column - it leaves through the top of the
    # window - and on a figure where two curves run fourteen pixels apart a band
    # wide enough to hold one of them swallows the other, so the reader sees one
    # merged curve and drops both cells.
    xs, ys = collect(lambda _: y)
    if len(xs) >= 5 and len(set(xs)) >= 2:
        first = np.poly1d(np.polyfit(np.asarray(xs, dtype=float),
                                     np.asarray(ys, dtype=float), 1))
        xs, ys = collect(lambda xi: float(first(xi)))
    if len(xs) < 5 or len(set(xs)) < 2:
        return None, None, None, None
    # Quadratic, not linear. A time course turns over, and a straight fit
    # through a peak leaves most of the window outside `tol` - the solid curve
    # at its own maximum measured a duty of 0.47 and was classified as dashed.
    # Two degrees of freedom follow the turn without chasing dash tips.
    order = 2 if len(set(xs)) >= 8 else 1
    fit = np.polyfit(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), order)
    curve = np.poly1d(fit)
    # Count only the span the ink actually covers. At the first and last plotted
    # points half the window is off the end of the data, and scoring those empty
    # columns as misses halved the duty of a perfectly solid line.
    lo_x, hi_x = min(xs), max(xs) + 1
    if hi_x - lo_x < 12:
        return None, None, None, None
    # A COLUMN WHERE THE CURVE IS COVERED IS NOT A COLUMN WHERE THE CURVE IS
    # ABSENT. The stems have been taken out of `mask` so that a tall glyph
    # cannot be traced as a curve, and that removal takes the curve's own two or
    # three pixels with it. Scored as misses those columns are our own doing:
    # on publication 397 the error-bar stems are three pixels wide and stand
    # every 33 columns, so every window over the SOLID curve showed a gap of 3
    # and the reader found no solid line anywhere on the figure. Skipped in both
    # the numerator and the denominator, the gap measures the line style.
    hits, observed, gap, longest = 0, 0, 0, 0
    seen = {}
    for xi in range(lo_x, hi_x):
        predicted = float(curve(xi))
        lo_y, hi_y = max(0, int(predicted - tol)), min(height, int(predicted + tol) + 1)
        if blind is not None and hi_y > lo_y and blind[lo_y:hi_y, xi].any():
            continue
        observed += 1
        idx = np.where(mask[lo_y:hi_y, xi])[0] if hi_y > lo_y else []
        if len(idx):
            hits += 1
            gap = 0
            seen[xi] = lo_y + float(np.mean(idx))
        else:
            gap += 1
            longest = max(longest, gap)
    if not observed:
        # Every column of the window is furniture. Publication 397's WOMEN MAP
        # panel has such a window and the reader divided by zero there, which
        # `run_batch` reports as an InternalReaderError and which aborts the
        # whole batch - one panel's blind spot taking seventeen readable panels
        # with it.
        return None, None, None, None
    slope = float(curve.deriv()(x)) if order == 2 else float(fit[0])
    return (hits / float(observed), _ink_at(seen, x, curve), slope, longest)


def _ink_at(seen, x, curve):
    """The curve's height at x, taken from the INK rather than from the fit.

    The fit is a smoothing device: it has to be, because duty has to be scored
    against something steadier than the pixels. Reading the VALUE off it pays
    for that smoothing at every corner. Publication 397's solid curve drops
    seven mmHg into 3:00 and runs flat out of it, and a quadratic through that
    corner rounds it off - the reader answered 101.2 where the eye reads 98.

    So the fit says where to look and the ink says how high. Where the column
    at x is inked, that is the answer; where it is not - a dash gap, or a stem
    standing over it - the nearest inked column each side is interpolated, and
    only a curve with no ink on one side at all falls back to the fit.
    """
    if not seen:
        return float(curve(x))
    left = max((xi for xi in seen if xi <= x), default=None)
    right = min((xi for xi in seen if xi >= x), default=None)
    if left is None or right is None:
        return float(seen[left if left is not None else right])
    if left == right:
        return float(seen[left])
    weight = (float(x) - left) / float(right - left)
    return float(seen[left] * (1.0 - weight) + seen[right] * weight)


def _curve_candidates(mask, x, y0, y1, probe=8, half=22, band=5,
                      extra_seeds=(), blind=None):
    """Every distinct curve passing near column x, with its style duty cycle.

    Seeds come from columns either side of x rather than from x itself: at x the
    error-bar stem has been stripped away and the curve's own pixels went with
    it. Each seed is fitted twice - once from where it was found, once recentred
    on the fitted position - so a seed taken eight columns off a steep curve
    still converges onto it.
    """
    # SEEDED FROM SEVERAL COLUMNS, spanning more than a dash period. A dashed
    # curve is ABSENT from some columns by construction, so three probes can
    # all land in its gaps - the fixture's dashed curve went unseeded at one of
    # ten positions that way, and under the consistency rule below that costs
    # both series their cell there.
    # Three probes, not a sweep. Widening the net seeds the ERROR-BAR CAPS -
    # a cap is a 14 px horizontal stroke and a 45 px window over a row of them
    # measures a duty of 0.87 with a gap of 2, which sits one hundredth below
    # the SOLID band. Candidates that are one bad pixel from being a curve are
    # not what a fail-closed reader wants floating about, so the extra reach
    # comes from `extra_seeds` - the fitted centres of the position next door,
    # which are curve positions by construction.
    seeds = list(extra_seeds)
    for offset in (-probe, probe, 0):
        xi = int(round(x)) + offset
        if not (0 <= xi < mask.shape[1]):
            continue
        for run in _column_runs(mask, xi):
            centre = float(np.mean(run))
            if y0 <= centre <= y1:
                seeds.append(centre)
    # Seeds that converge on one curve are returned as several entries and
    # collapsed by the caller, which has to dedupe across the two sweeps
    # anyway. Doing it twice was two names for one rule.
    found = []
    for seed in seeds:
        duty, y_at_x, slope, gap = _line_fit_window(mask, int(round(x)), seed,
                                                    half=half, band=band,
                                                    blind=blind)
        if y_at_x is None:
            continue
        duty, y_at_x, slope, gap = _line_fit_window(mask, int(round(x)), y_at_x,
                                                    half=half, band=band,
                                                    blind=blind)
        if y_at_x is None or not (y0 <= y_at_x <= y1):
            continue
        found.append(dict(y=y_at_x, duty=duty, slope=slope, gap=gap))
    return found


def _bar_extent(mask, x, cy, other_centres, half_window, marker_half_height,
                search_radius):
    """The error bar around the curve at cy, as (top, bottom), or None.

    THE ERROR BAR IS THE CONNECTED COLUMN OF INK THROUGH THE MARK. Not the
    nearest wide stroke either side, which is what `_errorbar_around_marker`
    takes and what this reader took until it was measured: on a two-curve time
    course the OTHER series' cap is a wide horizontal stroke a few pixels away,
    and taking the nearest one read the neighbour's cap as this curve's. On the
    fixture that came back as a dispersion 1.99 units short of the truth -
    a plausible number that is simply wrong, which is the one output this
    package exists to refuse.

    Walking the connected run instead makes the answer structural. Where the
    two bars are separate ink there is white between them, the walk stops at
    this bar's own cap, and the reading is right. Where they touch or overlap
    the walk swallows both and the run contains the OTHER curve's centre - and
    then no rule local to this column can say which cap belongs to which mark,
    so the cell keeps its mean and reports no dispersion. A human reading that
    figure cannot attribute those caps either.

    Both ends must be a CAP: a horizontal stroke that ends. A cap is a stroke
    of its own length, a curve reaches both edges of any window you look
    through, so the run through the end row has to be bounded inside a window
    several times the cap's width.
    """
    height, width = mask.shape
    xc = int(round(x))
    column = mask[:, max(0, xc - 1):min(width, xc + 2)].any(axis=1)
    row0 = int(round(cy))
    if not (0 <= row0 < height) or not column[row0]:
        return None
    reach = max(6, half_window * 3)
    lo_x, hi_x = max(0, xc - reach), min(width, xc + reach + 1)

    def bounded_run(row):
        if not (0 <= row < height) or not mask[row, xc]:
            return False
        left = xc
        while left - 1 >= lo_x and mask[row, left - 1]:
            left -= 1
        right = xc
        while right + 1 < hi_x and mask[row, right + 1]:
            right += 1
        if left <= lo_x or right >= hi_x - 1:
            return False          # it leaves the window: a curve, not a cap
        return (right - left + 1) >= max(4, half_window)

    limit = int(search_radius)
    top, bottom = row0, row0
    while top - 1 >= 0 and column[top - 1]:
        top -= 1
        if row0 - top > limit:
            return None           # the ink does not end: an axis, not a bar
    while bottom + 1 < height and column[bottom + 1]:
        bottom += 1
        if bottom - row0 > limit:
            return None
    if row0 - top <= marker_half_height or bottom - row0 <= marker_half_height:
        return None               # the stroke itself, with no bar around it
    if any(top <= centre <= bottom for centre in other_centres):
        return None               # two marks in one column of ink: unattributable
    if not bounded_run(top) or not bounded_run(bottom):
        return None
    return float(top), float(bottom)


def read_monochrome_line_panel(image, panel_box, x_positions, y_calibration,
                               series, threshold=150, x_window=10,
                               fit_half=22, fit_band=5, probe=8,
                               search_radius=60):
    """Read black line series told apart by LINE STYLE - solid vs dashed.

    The other monochrome reader separates series by marker shape and fill. A
    great many figures have no markers at all: two black curves, one solid and
    one dashed, and the legend is the only thing that says which is which. No
    amount of marker geometry helps, because there are no markers.

    The discriminant here is the curve's own duty cycle, measured in a short
    window at each declared x. That is a property of the ink, not of drawing
    order, so it can be declared in a manifest and checked against the figure -
    the same contract every other reader in this module keeps.

    Fail-closed in four places: a curve whose duty cycle lands between the bands
    is dropped, two curves at one x that classify the same way are both dropped,
    a declared style with no matching curve at that x yields no cell, and a
    whisker with no confirmed stem yields a centre with no dispersion rather
    than a dispersion measured off a significance glyph.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    x0, x1, y0, y1 = map(int, panel_box)
    mask = np.zeros(gray.shape, dtype=bool)
    mask[y0:y1, x0:x1] = gray[y0:y1, x0:x1] < int(threshold)
    # Both are ink that is not a datum, and both hide the curve where it
    # crosses them, so both are taken out of the traceable ink AND used to
    # blind the duty accounting.
    stems = _vertical_strokes(mask)
    blind = (stems | _horizontal_rules(mask, x0, x1)
             | _cap_ink(mask, stems, x_window))
    curve_mask = mask & ~blind
    want = []
    for spec in series:
        style = str(spec.line_style or "").strip().upper()
        if style not in LINE_STYLES:
            raise ValueError(
                "SeriesSpec.line_style must be one of %s for a monochrome line "
                "series; %r declares %r" % ("/".join(LINE_STYLES), spec.name,
                                            spec.line_style))
        want.append(style)
    if len(set(want)) != len(want):
        raise ValueError("two monochrome line series share a line style, so no "
                         "reader can separate them: %s" % want)
    # FIRST PASS: what is separable at each x, before anything is emitted.
    #
    # A CURVE IS CONTINUOUS AND IT HAS A SLOPE, so the neighbouring position's
    # fit says where to look here. A dashed curve is absent from whole columns
    # by construction and the three fixed probes can all land in its gaps - the
    # fixture lost it that way, and under the consistency rule below that costs
    # BOTH series their cell. Carrying the neighbour's fitted CENTRE alone is
    # not enough on a moving curve: between two positions the fixture's dashed
    # curve descends 22 px, four times the collection band, so the carried seed
    # lands on nothing. Carried with its slope it lands within a pixel.
    #
    # Swept BOTH WAYS, because a curve missed at the first position has no
    # earlier neighbour to be carried from, and one missed anywhere breaks the
    # chain for every position after it.
    ordered = list(x_positions.items())

    def sweep(sequence):
        seen, carried = {}, []
        for label, x in sequence:
            xi = int(round(x))
            found = _curve_candidates(curve_mask, xi, y0, y1, probe=probe,
                                      half=fit_half, band=fit_band,
                                      blind=blind,
                                      extra_seeds=[y + slope * (xi - x_at)
                                                   for y, slope, x_at in carried])
            seen[label] = found
            carried = [(c["y"], c["slope"], xi) for c in found
                       if classify_line_style(c["duty"], c["gap"]) is not None]
        return seen

    forward, backward = sweep(ordered), sweep(list(reversed(ordered)))
    per_x = {}
    for label, _x in ordered:
        styled = []
        for candidate in forward[label] + backward[label]:
            style = classify_line_style(candidate["duty"], candidate["gap"])
            if style is None:
                continue
            if any(abs(candidate["y"] - s["y"]) <= _SAME_CURVE_PX for s in styled):
                continue      # the same curve, reached from either direction
            styled.append(dict(candidate, style=style))
        counts = {}
        for candidate in styled:
            counts[candidate["style"]] = counts.get(candidate["style"], 0) + 1
        per_x[label] = (styled, counts)
    # A CURVE DOES NOT VANISH FOR ONE POSITION AND COME BACK. Where two curves
    # cross they are one stroke, and there is nothing at that x to see: the
    # merged ink measures a full duty and no gap, so it reads as a clean solid
    # line and the reader emits ONE cell - a number for one series and silence
    # for the other, which is worse than silence for both. Locally there is no
    # signal at all; across the panel there is. A style found somewhere is
    # expected everywhere, and an x where an expected style is missing while
    # another was found is an x where they merged.
    #
    # A style found NOWHERE is not expected anywhere - that is a declared
    # series the figure does not contain, which is a different thing and still
    # costs the other series nothing.
    present = {style for styled, _c in per_x.values() for style in
               {s["style"] for s in styled}}
    declared = {str(spec.line_style).strip().upper() for spec in series}
    expected = present & declared
    unresolved = set()
    for label, (styled, counts) in per_x.items():
        here = {s["style"] for s in styled} & declared
        if here and here != expected:
            unresolved.add(label)
    out = []
    for order, (label, x) in enumerate(x_positions.items()):
        xi = int(round(x))
        if label in unresolved:
            continue
        styled, counts = per_x[label]
        for spec in series:
            style = str(spec.line_style).strip().upper()
            if counts.get(style, 0) != 1:
                continue          # absent here, or two curves of the same style
            candidate = next(c for c in styled if c["style"] == style)
            cy = candidate["y"]
            whisker = _bar_extent(mask, xi, cy,
                                  [c["y"] for c in styled if c is not candidate],
                                  half_window=x_window,
                                  marker_half_height=4,
                                  search_radius=search_radius)
            lower = upper = dispersion = None
            stem = whisker is not None
            if whisker is not None:
                top, bottom = whisker
                upper = max(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                lower = min(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                dispersion = (upper - lower) / 2.0
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(xi),
                marker_center_px=cy, mean=y_calibration.pixel_to_value(cy),
                dispersion=dispersion, errorbar_lower=lower, errorbar_upper=upper,
                line_style=style, line_duty=round(candidate["duty"], 3),
                # The gap, not the duty, is what said SOLID or DASHED. Recorded
                # beside the duty so a reviewer can check the call that was
                # actually made rather than the one the number suggests.
                line_gap=candidate["gap"],
                Marker_Definition="LINE_CENTER",
                # Connected by construction: the bar IS the run of ink through
                # the mark, so a recovered dispersion has a confirmed stem and
                # an unrecovered one has no dispersion to confirm.
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


