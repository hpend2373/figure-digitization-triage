"""WORK IN PROGRESS - not part of the released reader set, and not dispatched.

Solid-versus-dashed monochrome lines. Publication 397 Figures 1, 2 and 5 are
exactly this: two black curves, no markers at all, and a legend that says which
is which. Marker geometry cannot help, so the discriminant has to be the ink's
own duty cycle.

## Where it actually stands

On a synthetic fixture with two curves at a normal separation it reads 16 of 18
separable cells, assigns both styles correctly, and recovers means within 1.5
units on a 50-unit axis. That is close to working and not the same as working:

* at a deliberate CROSSING, where the two curves land on the same value, it
  still emits both cells instead of dropping them. The whole design of this
  system is that an unresolvable mark produces no row, and this one produces two
* two of eighteen separable cells are silently missing, and the reason has not
  been characterised
* it has not been run against publication 397 at all

Shipping it in that state would put numbers in a values file that nobody can
defend, which is the failure this package exists to prevent - and it is exactly
the reason BAR_MONO was held back from the previous release. It is held here
until it has a fixture it passes completely and a forward test on a real figure,
the same bar `read_monochrome_bar_panel` had to clear.

## What was learned, so the next attempt does not restart

A whole-panel sequential tracer does not work. It has to survive every dash gap
on every slope in one pass, and a dash TIP - one row of a three-pixel stroke -
biases the run centre enough to lose a steep curve. One miss fragments the
series and the figure reads as containing a single curve.

A short windowed fit does work, with three details that each cost a debugging
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
"""
import numpy as np
import cv2
from PIL import Image

from mark_readers import (AxisCalibration, SeriesSpec, _runs,  # noqa: F401
                          _errorbar_around_marker)


LINE_STYLES = ("SOLID", "DASHED", "DOTTED")

#: Fraction of columns along a traced curve that carry real ink. A solid stroke
#: is near 1.0; a dash pattern of about 8 on, 6 off lands near 0.6; a dotted
#: rule lands lower still. The bands leave a gap on either side - a curve in the
#: gap is ambiguous and its cells are dropped.
_STYLE_BANDS = {"SOLID": (0.88, 1.01), "DASHED": (0.35, 0.78), "DOTTED": (-0.01, 0.28)}


def classify_line_style(duty):
    """SOLID / DASHED / DOTTED for a traced curve's duty cycle, or None."""
    hits = [k for k, (lo, hi) in _STYLE_BANDS.items() if lo <= duty < hi]
    return hits[0] if len(hits) == 1 else None


def _strip_vertical_strokes(mask, min_run=11):
    """Remove error-bar stems, keeping the near-horizontal curves.

    A stem is a tall thin vertical run; a curve crossing one is two or three
    pixels of the same column. Opening with a tall thin kernel finds the stems
    exactly, and the two or three curve pixels inside a stem go with it - which
    is why the tracer below has to bridge gaps rather than demand ink in every
    column. It bridges at most a dash's width, so it cannot bridge across the
    end of a line.
    """
    tall = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_run)))
    return mask & ~(tall > 0)


def _column_runs(mask, x, max_thickness=7):
    """Vertical runs of ink in one column, narrow enough to be a curve."""
    idx = np.where(mask[:, x])[0]
    return [g for g in _runs(idx.tolist(), gap=1) if len(g) <= max_thickness]


def _line_fit_window(mask, x, y, half=22, band=5, tol=2.5):
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

    Returns (duty, y_at_x, slope) or (None, None, None).
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
        return None, None, None
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
        return None, None, None
    hits = 0
    for xi in range(lo_x, hi_x):
        predicted = float(curve(xi))
        lo_y, hi_y = max(0, int(predicted - tol)), min(height, int(predicted + tol) + 1)
        if hi_y > lo_y and mask[lo_y:hi_y, xi].any():
            hits += 1
    total = hi_x - lo_x
    slope = float(curve.deriv()(x)) if order == 2 else float(fit[0])
    return hits / float(max(1, total)), float(curve(x)), slope


def _curve_candidates(mask, x, y0, y1, probe=8, half=22, band=5):
    """Every distinct curve passing near column x, with its style duty cycle.

    Seeds come from columns either side of x rather than from x itself: at x the
    error-bar stem has been stripped away and the curve's own pixels went with
    it. Each seed is fitted twice - once from where it was found, once recentred
    on the fitted position - so a seed taken eight columns off a steep curve
    still converges onto it.
    """
    seeds = []
    for offset in (-probe, probe, 0):
        xi = int(round(x)) + offset
        if not (0 <= xi < mask.shape[1]):
            continue
        for run in _column_runs(mask, xi):
            centre = float(np.mean(run))
            if y0 <= centre <= y1:
                seeds.append(centre)
    found = []
    for seed in seeds:
        duty, y_at_x, slope = _line_fit_window(mask, int(round(x)), seed,
                                               half=half, band=band)
        if y_at_x is None:
            continue
        duty, y_at_x, slope = _line_fit_window(mask, int(round(x)), y_at_x,
                                               half=half, band=band)
        if y_at_x is None or not (y0 <= y_at_x <= y1):
            continue
        if any(abs(y_at_x - f["y"]) <= 3.0 for f in found):
            continue
        found.append(dict(y=y_at_x, duty=duty, slope=slope))
    return found


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
    curve_mask = _strip_vertical_strokes(mask)
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
    out = []
    for order, (label, x) in enumerate(x_positions.items()):
        xi = int(round(x))
        candidates = _curve_candidates(curve_mask, xi, y0, y1, probe=probe,
                                       half=fit_half, band=fit_band)
        styled = []
        for candidate in candidates:
            style = classify_line_style(candidate["duty"])
            if style is not None:
                styled.append(dict(candidate, style=style))
        counts = {}
        for candidate in styled:
            counts[candidate["style"]] = counts.get(candidate["style"], 0) + 1
        for spec in series:
            style = str(spec.line_style).strip().upper()
            if counts.get(style, 0) != 1:
                continue          # absent here, or two curves of the same style
            candidate = next(c for c in styled if c["style"] == style)
            cy = candidate["y"]
            whisker = _errorbar_around_marker(mask, xi, cy, y0, y1,
                                              half_window=x_window,
                                              marker_half_height=4,
                                              search_radius=search_radius)
            lower = upper = dispersion = None
            stem = False
            if whisker is not None:
                top, bottom, stem = whisker
                upper = max(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                lower = min(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                dispersion = (upper - lower) / 2.0
            if not stem:
                lower = upper = dispersion = None
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(xi),
                marker_center_px=cy, mean=y_calibration.pixel_to_value(cy),
                dispersion=dispersion, errorbar_lower=lower, errorbar_upper=upper,
                line_style=style, line_duty=round(candidate["duty"], 3),
                Marker_Definition="LINE_CENTER",
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


