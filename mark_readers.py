"""Reusable raster readers for non-bar scientific figures.

Readers return geometry and values only.  They do not infer study arms or
timepoints; callers supply those labels and the four-grain grid validator checks
that every declared cell is represented.
"""
from dataclasses import dataclass
import math

import numpy as np
import cv2
from PIL import Image

# The geometry both this module and the diagnostic driver measure with. Imported
# rather than reimplemented: two implementations of one measurement drift, and
# this project has already paid for that on publication 397's WOMEN panel.
# `mono_bar_geometry` deliberately imports nothing from here - it takes a
# calibration object, not tick points - so this direction is the only one.
import mono_bar_geometry as MONO_GEOMETRY


def _runs(indices, gap=1):
    out, cur = [], []
    for value in sorted(int(v) for v in indices):
        if cur and value - cur[-1] <= gap:
            cur.append(value)
        else:
            if cur:
                out.append(cur)
            cur = [value]
    if cur:
        out.append(cur)
    return out


class ReaderError(Exception):
    """A condition the reader was built to meet, met.

    The runner used to wrap every reader call in a bare `except Exception` and
    report whatever came out as PANEL_GEOMETRY_UNRESOLVED. A TypeError from a
    misspelled keyword, a KeyError from a renamed field and a genuinely
    unreadable axis all arrived at a human as the same queue row: "go and look
    at this figure again". Two of those three are bugs in this package, and
    sending them to a person to re-read is how a defect hides inside 116
    publications of honest manual work.

    Readers raise these for things that are ACTUALLY about the figure. Anything
    else that escapes a reader is a defect, and `run_batch` stops the batch.
    """


class GeometryResolutionError(ReaderError, ValueError):
    """The box, the calibration or the raster cannot be trusted.

    Also a ValueError, so callers that predate the taxonomy still catch it.
    """


class SeriesIdentityError(ReaderError):
    """Marks were found but which series they belong to is ambiguous."""


class UnsupportedCapabilityError(ReaderError):
    """The declaration is coherent and no released reader can honour it."""


@dataclass(frozen=True)
class AxisCalibration:
    slope: float
    intercept: float
    scale: str = "LINEAR"
    #: Largest absolute residual of the fit, in axis units (log units on a LOG
    #: axis). Emitted so a bad calibration is a number somebody can gate on
    #: rather than a shape nobody looked at. `bar_reader` computed exactly this
    #: and returned it under a different name, where nothing read it.
    max_residual: float = 0.0
    #: The points the fit came from, `((value, pixel), ...)`. Kept because the
    #: fit alone cannot say what a person typed: a slope and an intercept
    #: reproduce the mapping and not the two numbers somebody read off the
    #: printed axis, so nothing downstream could compare a DECLARED tick pixel
    #: with a tick mark found on the page, or say which of four points was the
    #: one that did not fit.
    points: tuple = ()

    @classmethod
    def from_points(cls, points, scale="LINEAR"):
        """Fit pixel -> value from ``[(value, pixel), ...]``."""
        scale = str(scale).upper()
        values = np.asarray([p[0] for p in points], dtype=float)
        pixels = np.asarray([p[1] for p in points], dtype=float)
        if len(points) < 2 or len(set(pixels)) < 2:
            raise GeometryResolutionError(
                "axis calibration needs two distinct pixels")
        if scale == "LOG":
            if np.any(values <= 0):
                raise GeometryResolutionError(
                    "LOG calibration values must be positive")
            values = np.log(values)
        elif scale != "LINEAR":
            raise GeometryResolutionError("scale must be LINEAR or LOG")
        slope, intercept = np.polyfit(pixels, values, 1)
        resid = float(np.abs(values - (slope * pixels + intercept)).max())
        return cls(float(slope), float(intercept), scale, resid,
                   tuple((float(p[0]), float(p[1])) for p in points))

    def pixel_to_value(self, pixel):
        raw = self.slope * float(pixel) + self.intercept
        return float(np.exp(raw) if self.scale == "LOG" else raw)

    def value_to_pixel(self, value):
        raw = np.log(float(value)) if self.scale == "LOG" else float(value)
        return float((raw - self.intercept) / self.slope)


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    rgb: tuple | None = None
    marker: str = "CIRCLE"
    fill: str = "ANY"
    tolerance: float = 70.0
    #: How a monochrome BAR series is told apart - SOLID / HATCHED / OPEN.
    #: Deliberately separate from `fill`, which is the OPEN/FILLED state of a
    #: MARKER. Overloading one field for both meant an open circle and an
    #: unfilled bar were the same declaration, and a panel carrying both could
    #: not be described at all.
    bar_fill: str = ""
    #: How a monochrome LINE series is told apart when the markers match.
    line_style: str = ""


def _rgb_mask(rgb, target, tolerance):
    arr = np.asarray(rgb, dtype=float)
    target = np.asarray(target, dtype=float)
    return np.linalg.norm(arr - target, axis=2) <= float(tolerance)


def _marker_and_errorbar(mask, x, y0, y1, half_window=12):
    """Return marker centre and connected whisker extent at an expected x."""
    h, w = mask.shape
    xa, xb = max(0, int(round(x)) - half_window), min(w, int(round(x)) + half_window + 1)
    patch = mask[max(0, y0):min(h, y1), xa:xb]
    counts = patch.sum(axis=1)
    groups = _runs(np.where(counts >= 5)[0], gap=1)
    if not groups:
        return None
    # Caps are wide but only 1-3 rows.  A marker is thick in both dimensions.
    marker = max(groups, key=lambda g: (len(g), float(counts[g].sum())))
    if len(marker) < 4:
        return None
    cy = max(0, y0) + float(np.mean(marker))
    xc = int(round(x))
    col = mask[:, max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    supports = _runs(np.where(col)[0], gap=2)
    connected = [g for g in supports if g[0] - 2 <= cy <= g[-1] + 2]
    whisker = max(connected, key=len) if connected else marker
    # Horizontal cap strokes form short, wide row groups on either side of the
    # much taller marker group.  Use their stroke centres rather than the outer
    # pixels, otherwise every SD is inflated by half a cap stroke at both ends.
    above = [g for g in groups if g[-1] < marker[0]]
    below = [g for g in groups if g[0] > marker[-1]]
    # `groups` index into the CROPPED patch; `whisker` indexes the full column.
    # Returning one of each put the cap rows y0 pixels high whenever the panel
    # did not start at row 0, which on a 400 px panel with y0=40 shifted both
    # bounds by 11 units - while leaving their DIFFERENCE, and therefore the
    # dispersion, exactly right. A suite that checks means and dispersions sees
    # nothing; the first thing to notice was the gate saying the mean sat
    # outside its own error bar.
    off = max(0, y0)
    top = (off + float(np.mean(max(above, key=lambda g: g[-1])))) if above \
        else float(whisker[0])
    bottom = (off + float(np.mean(min(below, key=lambda g: g[0])))) if below \
        else float(whisker[-1])
    return cy, top, bottom, bool(above and below)


def _errorbar_around_marker(mask, x, cy, y0, y1, half_window=8,
                            marker_half_height=8, search_radius=28):
    """Find cap centres attached to a known monochrome marker.

    Marker discovery and whisker discovery are deliberately separate.  In a
    black multi-series plot a vertical whisker is physically joined to the
    marker, so contour geometry alone turns a circle into a tall irregular
    object.  Once the marker centre is known, however, cap rows are simply the
    nearest wide dark strokes above and below it whose stem crosses the marker.
    """
    h, w = mask.shape
    xc = int(round(x))
    ya = max(int(y0), int(round(cy - search_radius)))
    yb = min(int(y1), int(round(cy + search_radius + 1)))
    xa, xb = max(0, xc - half_window), min(w, xc + half_window + 1)
    patch = mask[ya:yb, xa:xb]
    if patch.size == 0:
        return None
    counts = patch.sum(axis=1)
    groups = _runs(np.where(counts >= 5)[0], gap=1)
    above = [g for g in groups if ya + g[-1] < cy - marker_half_height]
    below = [g for g in groups if ya + g[0] > cy + marker_half_height]
    if not above or not below:
        return None
    top_group = max(above, key=lambda g: g[-1])
    bottom_group = min(below, key=lambda g: g[0])
    top = ya + float(np.mean(top_group))
    bottom = ya + float(np.mean(bottom_group))
    # A true error-bar stem reaches from each cap to the marker at x.  Allow a
    # one-pixel antialiasing gap, but do not accept significance brackets.
    upper_stem = mask[max(0, int(top)):min(h, int(cy - marker_half_height) + 1),
                      max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    lower_stem = mask[max(0, int(cy + marker_half_height)):min(h, int(bottom) + 1),
                      max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    stem_confirmed = bool(len(upper_stem) and len(lower_stem)
                          and upper_stem.mean() >= 0.70
                          and lower_stem.mean() >= 0.70)
    return top, bottom, stem_confirmed


def read_line_marker_panel(image, panel_box, x_positions, y_calibration, series,
                           x_window=12):
    """Read coloured line/marker series at caller-declared x positions.

    The expected x grid is supplied explicitly.  Missing markers remain missing
    so the grid engine, rather than a left-to-right counter, identifies the cell.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    # EVERY MASK BEFORE ANY MARK, so each mark can be asked whether another
    # series' colour also claims it. Two declared colours closer than the sum of
    # their tolerances produce two masks over one printed marker, and reading
    # them independently gives a complete grid in which two series hold the same
    # mark - no cell missing, no count wrong, and one of the two numbers
    # attributed to a series that was never there. `read_scatter_panel` has
    # measured this since it shipped; the two colour readers did not.
    masks = {}
    for spec in series:
        if spec.rgb is None:
            raise ValueError("coloured line reader requires SeriesSpec.rgb")
        mask = _rgb_mask(rgb, spec.rgb, spec.tolerance)
        region = np.zeros_like(mask)
        region[max(0, y0):min(mask.shape[0], y1), max(0, x0):min(mask.shape[1], x1)] = True
        masks[spec.name] = mask & region
    for spec in series:
        mask = masks[spec.name]
        others = [m for name, m in masks.items() if name != spec.name]
        for order, (label, x) in enumerate(x_positions.items()):
            found = _marker_and_errorbar(mask, x, y0, y1, half_window=x_window)
            if found is None:
                continue
            cy, top, bottom, stem = found
            upper = max(y_calibration.pixel_to_value(top), y_calibration.pixel_to_value(bottom))
            lower = min(y_calibration.pixel_to_value(top), y_calibration.pixel_to_value(bottom))
            mean = y_calibration.pixel_to_value(cy)
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(x),
                marker_center_px=cy, mean=mean,
                errorbar_lower=lower, errorbar_upper=upper,
                dispersion=(upper - lower) / 2.0,
                Marker_Definition="MARKER_CENTER",
                # HOW THIS SERIES WAS NAMED AND HOW THE NUMBER WAS GOT. The mask
                # this marker was found in was built from the colour the manifest
                # declares for this series, and the pixels at the mark matched it
                # - so the identity rests on measured colour, not on a
                # declaration alone. `MISSING_SERIES_DISCRIMINANT` is what makes
                # that true of every LINE_COLOR series: the manifest cannot
                # decline to say what colour a series is.
                #
                # What this does NOT claim is that two declared colours are far
                # enough apart to be told apart at their tolerances. That is a
                # separate question, and one no tier can answer - which is why
                # it stays on the open list rather than being priced here.
                Identity_Method="MEASURED_COLOUR",
                Value_Method="MARKER_CENTER",
                # AND HOW THE ERROR BAR WAS GOT, which is a third question and
                # often the one that decides the weight. `_marker_and_errorbar`
                # follows a stem from this mark to the cap; ink at the right
                # distance with nothing joining it is a cap or a significance
                # glyph, and telling those apart is a person's job.
                Dispersion_Method=("DIRECT_CONNECTED_CAP" if stem
                                   else "UNSTEMMED_CAP"),
                # HOW MANY OTHER DECLARED COLOURS ALSO COVER THIS MARK. Measured
                # here and acted on by the batch layer, which is the division
                # every other reader field follows: naming a series the ink does
                # not separate is not this function's decision to make quietly.
                mask_overlap=int(_pixel_claimed_by(others, x, cy)),
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


#: How far a candidate may be from the panel's own marker size, as a ratio of
#: the side length. Wide enough for an open square beside a filled circle -
#: they differ by a third - and narrow enough that a tick label or a whole bar
#: is not a marker.
_MARKER_SIDE_LO, _MARKER_SIDE_HI = 0.45, 2.2

#: And the loose net the scale is measured through, expressed against the
#: PANEL, because there is nothing else to express it against before a scale
#: exists. A marker is a small thing in a plot.
_MARKER_SEED_MIN_PX = 3
_MARKER_SEED_MAX_FRACTION = 0.12


def measure_marker_scale(dark, panel_box, x_positions, x_window):
    """The typical marker side length in this panel, in pixels.

    Two passes, and this is the first: collect every enclosed white region and
    every thick ink core near a declared x, through a net whose only limits are
    "bigger than three pixels" and "smaller than a tenth of the panel", and
    take the MEDIAN side. A panel has one marker size by construction - it is
    drawn by one plotting program at one setting - so the median is that size
    however the page was rendered.

    Returns 0.0 when there is nothing to measure, and the caller then falls
    back to the loose net rather than to a number from another rendering.
    """
    x0, x1, y0, y1 = map(int, panel_box)
    ceiling = max(8, int((x1 - x0) * _MARKER_SEED_MAX_FRACTION))
    per_cell = []
    for x in x_positions.values():
        xa = max(x0, int(round(x)) - x_window)
        xb = min(x1, int(round(x)) + x_window + 1)
        crop = dark[max(0, y0):min(dark.shape[0], y1), xa:xb]
        if crop.size == 0:
            continue
        sides = []
        white = (crop == 0).astype(np.uint8)
        count, labels, stats_, _ = cv2.connectedComponentsWithStats(white, 8)
        for lab in range(1, count):
            bx, by, bw, bh, _area = stats_[lab]
            if bx == 0 or by == 0 or bx + bw == crop.shape[1] \
                    or by + bh == crop.shape[0]:
                continue
            if min(bw, bh) < _MARKER_SEED_MIN_PX or max(bw, bh) > ceiling:
                continue
            sides.append(float(max(bw, bh)))
        distance = cv2.distanceTransform((crop > 0).astype(np.uint8),
                                         cv2.DIST_L2, 5)
        cores = (distance >= 2.2).astype(np.uint8) * 255
        contours, _ = cv2.findContours(cores, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            _bx, _by, bw, bh = cv2.boundingRect(contour)
            if min(bw, bh) < _MARKER_SEED_MIN_PX or max(bw, bh) > ceiling:
                continue
            sides.append(float(max(bw, bh)))
        # THE BIGGEST marker-shaped thing at this x, not all of them. A median
        # over every seed is dragged down by antialiasing specks and by the
        # dots inside a stippled fill, and HOW MANY of those there are depends
        # on the rendering - which is the whole thing being removed here. A
        # declared x holds one marker per series, so the largest seed at it is
        # a marker, and the median across cells survives one odd cell.
        if sides:
            per_cell.append(max(sides))
    if not per_cell:
        return 0.0
    return float(np.median(per_cell))


def _marker_sized(area, bw, bh, scale, filled=False):
    """Is this blob the size of the markers in this panel?

    With a measured `scale` the test is a ratio, so it says the same thing at
    every rendering. Without one - a panel where nothing could be measured -
    it falls back to the loose net rather than to the old absolute numbers,
    because those numbers were a marker at exactly one DPI.
    """
    side = max(bw, bh)
    if side <= 0 or min(bw, bh) < _MARKER_SEED_MIN_PX:
        return False
    floor = 20 if filled else 12
    if not scale:
        return area >= floor * 0.25
    # The side against the panel's own marker, and nothing else. An area floor
    # was here too and could not be made to fail: every blob it would have
    # rejected is already outside the side window or under the seed minimum,
    # and a guard nothing can observe is decoration.
    return _MARKER_SIDE_LO * scale <= side <= _MARKER_SIDE_HI * scale


def _shape_wanted(shape, expected):
    """Is this classified shape one some declared series is looking for?

    `ANY` matches whatever came back, including a shape the classifier could
    not name. That is the point of declaring it: a twelve-pixel open square
    with rounded corners classifies as CIRCLE about as often as SQUARE, and on
    a one-series panel the answer changes nothing about which series it is.
    """
    wanted = {s.marker.upper() for s in expected}
    return "ANY" in wanted or shape in wanted


def _contour_marker_shape(contour):
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return "UNKNOWN"
    approx = cv2.approxPolyDP(contour, 0.06 * perimeter, True)
    vertices = len(approx)
    area = cv2.contourArea(contour)
    circularity = 4.0 * np.pi * area / (perimeter * perimeter)
    # Rasterisation and a one-pixel connecting line can simplify a circle to
    # four or five polygon vertices.  Circularity is more stable than vertex
    # count for that case and remains well above a diamond's value.
    if circularity >= 0.84:
        return "CIRCLE"
    if vertices == 3:
        return "TRIANGLE"
    if vertices == 4:
        pts = approx[:, 0, :]
        # A diamond has a single extreme point at its top; an axis-aligned
        # square has a horizontal top edge.  Both remain valid marker classes.
        top_count = int((pts[:, 1] == pts[:, 1].min()).sum())
        return "DIAMOND" if top_count == 1 else "SQUARE"
    return "CIRCLE" if vertices >= 5 and circularity >= 0.55 else "UNKNOWN"


#: The smallest white region that can be half of a marker's interior. Below
#: this it is antialiasing, and joining it to something is inventing a shape.
_MIN_INTERIOR_PART_PX = 6


def _one_interior_per_marker(white, stem_px, ink):
    """The white a marker outline encloses, as ONE region per marker.

    An error-bar stem is drawn THROUGH its own marker, so the enclosed white of
    an open square arrives as two slivers either side of the stem. Each sliver
    on its own is not a square, and two of them in one x cell is "two
    candidates, keep neither" - so publication BF02919461's five open squares
    read as two. The stem does not make two interiors.

    Closed horizontally, but only over the interior: closing the raw white
    would dilate the PAGE across the two-pixel outline and swallow the hole
    into the background, which is what happens if you try it. Components
    touching the crop border are the page and are removed first, exactly as the
    caller already removes them; `stem_px` is how wide a stem may be, so a
    genuine gap between two separate markers is not bridged.
    """
    if stem_px < 1:
        return white
    count, labels, stats_, _ = cv2.connectedComponentsWithStats(white, 8)
    interior = np.zeros_like(white)
    for lab in range(1, count):
        bx, by, bw, bh, area = stats_[lab]
        if bx == 0 or by == 0 or bx + bw == white.shape[1] \
                or by + bh == white.shape[0]:
            continue
        # A stem splits an interior into two REAL halves. A speck of
        # antialiasing beside an overlapping blob is not a half, and letting it
        # take part turned publication 386's ambiguous C2 cell - which the
        # reader is supposed to leave missing - into a triangle 2.4 units from
        # its own series and 0.6 from somebody else's.
        if area < _MIN_INTERIOR_PART_PX:
            continue
        interior[labels == lab] = 1
    closed = cv2.morphologyEx(
        interior, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (2 * int(stem_px) + 1, 1)))
    # ONLY across ink. Closing on its own bridges whatever lies between two
    # interiors, and on publication 386's dense four-series panel that is the
    # white page between two neighbouring open triangles - which invents a
    # marker halfway between them. What makes two halves one interior is that
    # the thing separating them is a drawn stem, so the pixels the close adds
    # have to be pixels somebody drew.
    candidate = np.maximum(interior,
                           np.where((closed > 0) & (ink > 0), 1, 0)
                           .astype(np.uint8))
    # And only where the bridge ACTUALLY joined two parts. This is the guard
    # that matters, and it covers both ways of getting it wrong. Ink pixels
    # beside a part that reach nobody are still ink, and adding them would grow
    # the interior by the thickness of its own outline; and closing a SINGLE
    # interior is not a merge at all but a reshaping - it fills the region's
    # concavities wherever ink lies behind them, which turned publication 386's
    # ambiguous overlapping blob from UNKNOWN, the correct answer, into a
    # TRIANGLE 2.4 units from its own series and 0.6 from somebody else's.
    n, merged_labels, _st, _c = cv2.connectedComponentsWithStats(candidate, 8)
    joined = np.zeros_like(white)
    for merged in range(1, n):
        region = merged_labels == merged
        if len(np.unique(labels[region & (interior > 0)])) >= 2:
            joined[region] = 1
        else:
            joined[region & (interior > 0)] = 1
    if not joined.any():
        return white
    # Put the page back exactly as it was, so a component that touched the
    # border still touches it and is still skipped by the caller.
    return np.maximum(white - interior, joined).astype(np.uint8)


def read_monochrome_marker_panel(image, panel_box, x_positions, y_calibration,
                                 series, x_window=18, threshold=150,
                                 stem_px=4, marker_half_height=8,
                                 whisker_search_px=28, marker_scale=0.0):
    """Separate black multi-series plots by marker geometry.

    Thin connecting lines are removed with a small morphological opening.  The
    adapter intentionally emits no value for a marker whose shape is ambiguous;
    the grid gate then routes that cell to manual WPD instead of guessing a
    series identity.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    dark = (gray < int(threshold)).astype(np.uint8) * 255
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    expected = list(series)
    # THE PANEL'S OWN MARKER SIZE, measured before anything is classified.
    # The limits used to be absolute - area 12..300 px, no side over 24 - which
    # is a marker at 300 DPI and half of one at 600: publication BF02919461
    # reads ten cells at 300 and NONE at 500, off the same page. BAR_MONO has
    # measured its stroke scale from the panel since it shipped; this is the
    # same idea for a marker.
    scale = marker_scale if marker_scale else measure_marker_scale(
        dark, panel_box, x_positions, x_window)
    for order, (label, x) in enumerate(x_positions.items()):
        xa, xb = max(x0, int(round(x)) - x_window), min(x1, int(round(x)) + x_window + 1)
        crop = dark[max(0, y0):min(dark.shape[0], y1), xa:xb]
        candidates = []
        # Open markers are defined by an enclosed white hole.  Detect that hole
        # before morphology: a thin outline may otherwise be erased, while its
        # enclosed region remains an unambiguous OPEN-vs-FILLED signal.
        white = (crop == 0).astype(np.uint8)
        white = _one_interior_per_marker(white, stem_px, crop)
        nlab, labels, stats_, cents = cv2.connectedComponentsWithStats(white, 8)
        for lab in range(1, nlab):
            bx, by, bw, bh, area = stats_[lab]
            if bx == 0 or by == 0 or bx + bw == crop.shape[1] or by + bh == crop.shape[0]:
                continue
            if not _marker_sized(area, bw, bh, scale):
                continue
            component = (labels == lab).astype(np.uint8) * 255
            holes, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not holes:
                continue
            contour = max(holes, key=cv2.contourArea)
            shape = _contour_marker_shape(contour)
            if not _shape_wanted(shape, expected):
                continue
            cx, cy = cents[lab]
            candidates.append((shape, "OPEN", xa + cx, y0 + cy,
                               float(cv2.contourArea(contour)), 0.0))
        # Filled markers may be connected to a whisker and a line.  A distance
        # transform keeps the thick marker core while eliminating one-pixel
        # lines and caps, so its geometry remains classifiable.
        distance = cv2.distanceTransform((crop > 0).astype(np.uint8), cv2.DIST_L2, 5)
        cores = (distance >= 2.2).astype(np.uint8) * 255
        contours, _ = cv2.findContours(cores, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            bx, by, bw, bh = cv2.boundingRect(contour)
            if not _marker_sized(area, bw, bh, scale, filled=True):
                continue
            shape = _contour_marker_shape(contour)
            if not _shape_wanted(shape, expected):
                continue
            moment = cv2.moments(contour)
            if moment["m00"] == 0:
                continue
            cx = xa + moment["m10"] / moment["m00"]
            cy = y0 + moment["m01"] / moment["m00"]
            inside = np.zeros_like(cores)
            cv2.drawContours(inside, [contour], -1, 255, thickness=-1)
            denom = max(1, int((inside > 0).sum()))
            fill_ratio = float(((cores > 0) & (inside > 0)).sum()) / denom
            if fill_ratio >= 0.58:
                candidates.append((shape, "FILLED", cx, cy, area, fill_ratio))
        # At most one mark of a given series may occupy a declared x cell.  If
        # two candidates survive, keep neither: series identity is unresolved.
        for spec in expected:
            shape = spec.marker.upper()
            if shape == "ANY":
                # Declared as "one series, nothing to tell apart". Every
                # candidate of the wanted fill belongs to it; two of them is
                # still two, and still refused below.
                matches = [c for c in candidates
                           if spec.fill.upper() in ("ANY", c[1])]
                if len(matches) != 1:
                    continue
                found_shape, fill_state, cx, cy, area, fill_ratio = matches[0]
                whisker = _errorbar_around_marker(
                    dark > 0, x, cy, y0, y1,
                    marker_half_height=marker_half_height,
                    search_radius=whisker_search_px)
                lower = upper = dispersion = None
                stem = False
                if whisker is not None:
                    top, bottom, stem = whisker
                    upper = max(y_calibration.pixel_to_value(top),
                                y_calibration.pixel_to_value(bottom))
                    lower = min(y_calibration.pixel_to_value(top),
                                y_calibration.pixel_to_value(bottom))
                    dispersion = (upper - lower) / 2.0
                out.append(dict(
                    series=spec.name, order=order, x_label=label, x=float(cx),
                    marker_center_px=float(cy),
                    mean=y_calibration.pixel_to_value(cy),
                    dispersion=dispersion, errorbar_lower=lower,
                    errorbar_upper=upper,
                    # What it actually LOOKED like, never "ANY": the artifact
                    # records the measurement, and the declaration is in the
                    # manifest where the author put it.
                    Marker_Definition=found_shape,
                    Marker_Fill=fill_state, marker_fill_ratio=fill_ratio,
                    # SHAPE=ANY MEANS THE SHAPE WAS NOT A DISCRIMINANT. What
                    # remains depends on the FILL: declared OPEN or FILLED, the
                    # candidates were filtered on a fill this reader measured, so
                    # the identity is measured. Declared ANY as well, nothing
                    # about the mark was compared with anything - the identity is
                    # "one series was declared, so this is it", which is R1 and
                    # not R0. The number is measured either way.
                    Identity_Method=("DECLARED_SINGLE_SERIES"
                                     if spec.fill.upper() == "ANY"
                                     else "MEASURED_MARKER_FILL"),
                    Value_Method="MARKER_CENTER",
                    Dispersion_Method=("NO_DISPERSION" if whisker is None
                                       else "DIRECT_CONNECTED_CAP" if stem
                                       else "UNSTEMMED_CAP"),
                    Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
                    marker_area_px=float(area)))
                continue
            wanted_fill = spec.fill.upper()
            if wanted_fill not in ("ANY", "OPEN", "FILLED"):
                raise ValueError("SeriesSpec.fill must be ANY, OPEN or FILLED")
            matches = [c for c in candidates if c[0] == shape and
                       (wanted_fill == "ANY" or c[1] == wanted_fill)]
            if len(matches) != 1:
                continue
            _, fill_state, cx, cy, area, fill_ratio = matches[0]
            whisker = _errorbar_around_marker(
                dark > 0, x, cy, y0, y1,
                marker_half_height=marker_half_height,
                search_radius=whisker_search_px)
            lower = upper = dispersion = None
            stem = False
            if whisker is not None:
                top, bottom, stem = whisker
                upper = max(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                lower = min(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                dispersion = (upper - lower) / 2.0
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(cx),
                marker_center_px=float(cy), mean=y_calibration.pixel_to_value(cy),
                dispersion=dispersion, errorbar_lower=lower, errorbar_upper=upper,
                Marker_Definition=shape,
                Marker_Fill=fill_state, marker_fill_ratio=fill_ratio,
                # The shape WAS the discriminant here: every candidate whose
                # measured shape is not this series' was dropped above. Named
                # after the shape rather than the fill even when both were
                # filtered on, because the shape is what `MISSING_SERIES_
                # DISCRIMINANT` requires of a LINE_MONO series and the fill is
                # optional beside it.
                Identity_Method="MEASURED_MARKER_SHAPE",
                Value_Method="MARKER_CENTER",
                Dispersion_Method=("NO_DISPERSION" if whisker is None
                                   else "DIRECT_CONNECTED_CAP" if stem
                                   else "UNSTEMMED_CAP"),
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
                marker_area_px=float(area),
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


def _pixel_claimed_by(masks, px, py, radius=1):
    """How many OTHER series masks also cover this marker's centre."""
    hits = 0
    for mask in masks:
        r0, r1 = max(0, int(round(py)) - radius), int(round(py)) + radius + 1
        c0, c1 = max(0, int(round(px)) - radius), int(round(px)) + radius + 1
        if mask[r0:r1, c0:c1].any():
            hits += 1
    return hits


#: Two centroids closer than this many pixels are one printed marker as far as a
#: reader is concerned - contour finding can split a marker crossed by a grid
#: line into two blobs, and counting both would inflate N.
_COINCIDENT_POINT_PX = 3.0

#: A blob this many times the series' median marker area is more than one
#: overlapping marker, not one large one.
_MERGED_MARKER_AREA_RATIO = 1.6


def point_count_audit(points, expected_n=None):
    """Does the number of detected marks match the sample the paper claims?

    `N_Pairs` used to be however many contours survived the area filter, and
    that number went into the values file as though it were the study's n. It is
    not: two subjects plotted at the same coordinates are one contour, a marker
    crossed by a gridline can be two, and a point claimed by two colour masks is
    counted twice. None of that is visible downstream unless the counts are
    written down beside the association and compared with what the source says.
    """
    detected = []
    for point in points:
        px, py = float(point.get("point_px_x", 0.0)), float(point.get("point_px_y", 0.0))
        if any(math.hypot(px - qx, py - qy) < _COINCIDENT_POINT_PX
               for qx, qy in detected):
            continue
        detected.append((px, py))
    unique = len(detected)
    areas = sorted(float(p.get("marker_area_px") or 0.0) for p in points)
    merged = False
    if areas and areas[len(areas) // 2] > 0:
        median = areas[len(areas) // 2]
        merged = any(a > _MERGED_MARKER_AREA_RATIO * median for a in areas)
    overlap = sum(int(p.get("mask_overlap") or 0) for p in points)
    expected = None
    if expected_n not in (None, ""):
        # No truncation. `int(float("10.5"))` is 10, so a malformed n silently
        # became a plausible one and the comparison below then agreed with it.
        # A declared n that is not a whole number of subjects is not a number
        # this can be measured against; the validator refuses it upstream and
        # here it simply is not used.
        try:
            value = float(expected_n)
        except (TypeError, ValueError):
            value = None
        if value is not None and value > 0 and value == int(value):
            expected = int(value)
    if expected is None:
        agreement = "NO_SOURCE_N"
    elif expected == unique:
        agreement = "MATCH"
    elif unique < expected:
        agreement = "FEWER_DETECTED"
    else:
        agreement = "MORE_DETECTED"
    # Fewer marks than subjects is the classic overplot; so is a blob too big to
    # be one marker, or a duplicate centroid dropped just above.
    possible = (agreement == "FEWER_DETECTED" or merged
                or unique < len(points))
    return dict(
        Expected_N_From_Source=("" if expected is None else expected),
        Detected_Unique_Point_Count=unique,
        Point_Count_Agreement=agreement,
        Overplotting_Possible="TRUE" if possible else "FALSE",
        Series_Mask_Overlap_Count=overlap,
    )


def read_scatter_panel(image, panel_box, x_calibration, y_calibration, series,
                       min_area=12, max_area=500):
    """Read coloured or a single monochrome scatter series.

    Multiple monochrome series require marker-identity routing rather than a
    shared threshold and therefore fail closed here.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    # Build every series mask before reading any of them. Two colours that are
    # close enough to claim the same pixel produce two points from one marker,
    # and the count that becomes N_Pairs cannot show it unless the masks are
    # compared with each other.
    masks = {}
    for spec in series:
        if spec.rgb is None:
            if len(series) != 1:
                raise ValueError("multiple monochrome scatter series need explicit marker routing")
            gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            masks[spec.name] = (gray < 150).astype(np.uint8) * 255
        else:
            masks[spec.name] = _rgb_mask(rgb, spec.rgb, spec.tolerance).astype(np.uint8) * 255
    for spec in series:
        mask = masks[spec.name]
        others = [m for name, m in masks.items() if name != spec.name]
        crop = mask[max(0, y0):min(mask.shape[0], y1), max(0, x0):min(mask.shape[1], x1)]
        opened = cv2.morphologyEx(
            crop, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not (min_area <= area <= max_area):
                continue
            _, _, bw, bh = cv2.boundingRect(contour)
            if max(bw, bh) > 35 or min(bw, bh) < 3:
                continue
            moment = cv2.moments(contour)
            if moment["m00"] == 0:
                continue
            px = x0 + moment["m10"] / moment["m00"]
            py = y0 + moment["m01"] / moment["m00"]
            points.append(dict(
                series=spec.name, point_px_x=float(px), point_px_y=float(py),
                x_value=x_calibration.pixel_to_value(px),
                y_value=y_calibration.pixel_to_value(py),
                Marker_Definition=spec.marker.upper(), marker_area_px=float(area),
                mask_overlap=int(_pixel_claimed_by(others, px, py)),
                # A COLOURED SERIES IS FOUND IN ITS OWN COLOUR'S MASK; a single
                # monochrome series is found in a grey threshold that says
                # nothing about which series a mark belongs to - there is only
                # one, by declaration, which is the branch above that refuses
                # more. The distinction survives into the value row because
                # `_scatter_outcome` reads it off the points it summarized.
                Identity_Method=("MEASURED_COLOUR" if spec.rgb is not None
                                 else "DECLARED_SINGLE_SERIES"),
                # AND NO `Value_Method` HERE. A point is not a value row: the
                # cell this panel produces is an association over the whole set,
                # and its method is `POINT_CLOUD_ASSOCIATION`, set where the
                # summary is built. A per-point "MARKER_CENTER" would be true,
                # carried nowhere and consumed by nothing - a field that looks
                # like provenance and is decoration.
            ))
        points.sort(key=lambda row: (row["x_value"], row["y_value"]))
        for order, row in enumerate(points):
            row["order"] = order
            out.append(row)
    return out


def _average_ranks(values):
    """Average ranks for ties, equivalent to rankdata(method='average')."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def _pearson(x, y):
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        raise ValueError("association needs variation on both axes")
    return float(np.corrcoef(x, y)[0, 1])


def _betacf(a, b, x):
    """Continued fraction for the incomplete beta, Lentz's method."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m_ in range(1, 300):
        m2 = 2 * m_
        aa = m_ * (b - m_) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m_) * (qab + m_) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def regularized_incomplete_beta(a, b, x):
    """I_x(a, b), hand-rolled because this package does not import scipy.

    The one function every exact p below needs. Written out rather than
    approximated, so a Student-t tail is a Student-t tail rather than a normal
    one wearing its name.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided(t, df):
    """P(|T_df| >= |t|). Exact, not a normal approximation."""
    if df <= 0:
        return None
    t = abs(float(t))
    if not math.isfinite(t):
        return 0.0
    return float(regularized_incomplete_beta(df / 2.0, 0.5,
                                             df / (df + t * t)))


def _t_p_from_r(r, n):
    """Two-sided p for a correlation, from the t statistic it implies.

    t = r*sqrt((n-2)/(1-r^2)) on n-2 degrees of freedom. This is the standard
    test for a Pearson r, and it is NOT the Fisher-z normal approximation that
    stood here for every statistic at once. On the small n a digitized scatter
    gives - a dozen points is typical - the two disagree by enough to move a
    result across 0.05.
    """
    if n <= 2:
        return None
    if abs(r) >= 1:
        return 0.0
    t = r * math.sqrt((n - 2) / (1.0 - r * r))
    return student_t_two_sided(t, n - 2)


def snedecor_f_upper_tail(f, df1, df2):
    """P(F_{df1,df2} >= f), from the same incomplete beta as the t tail."""
    if df1 <= 0 or df2 <= 0:
        return None
    f = float(f)
    if not math.isfinite(f):
        return 0.0
    if f <= 0:
        return 1.0
    return float(regularized_incomplete_beta(df2 / 2.0, df1 / 2.0,
                                             df2 / (df2 + df1 * f)))


def _slope_t_p(x, y):
    """(slope, two-sided p) from the regression's OWN residual variance.

    t = b / SE(b), SE(b) = sqrt(SSE/(n-2) / Sxx), on n-2 degrees of freedom.
    For a one-predictor fit this is algebraically the Pearson t, but it is
    computed from the residuals rather than borrowed from a correlation, and it
    is labelled SLOPE_T_TEST so the values file records which test was run
    rather than which one happened to be lying around.
    """
    n = len(x)
    slope, intercept = (float(v) for v in np.polyfit(x, y, 1))
    if n <= 2:
        return slope, None
    sxx = float(np.sum((x - float(np.mean(x))) ** 2))
    if sxx == 0:
        raise ValueError("association needs variation on both axes")
    sse = float(np.sum((y - (slope * x + intercept)) ** 2))
    if sse <= 0:
        # A perfectly collinear cloud. The residual variance is zero, so the
        # t statistic is infinite and the tail is zero - not undefined.
        return slope, 0.0
    se = math.sqrt(sse / (n - 2) / sxx)
    if se == 0:
        return slope, 0.0
    return slope, student_t_two_sided(slope / se, n - 2)


def _normal_p_from_r(r, n):
    """Two-sided Fisher-z normal approximation; None when n is too small.

    Kept because `_kendall_tau_b` uses it for its own asymptotic branch, where a
    normal approximation IS the standard test. It is no longer applied to
    Pearson, Spearman, R-squared and slope alike.
    """
    if n <= 3:
        return None
    if abs(r) >= 1:
        return 0.0
    z = math.atanh(r) * math.sqrt(n - 3)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def _kendall_exact_two_sided(n, observed_s):
    """Exact two-sided no-tie Kendall p from the inversion-count distribution."""
    # counts[k] is the number of permutations of m items with k inversions.
    counts = [1]
    for m in range(2, n + 1):
        max_inv = m * (m - 1) // 2
        prefix = [0]
        for count in counts:
            prefix.append(prefix[-1] + count)
        new = []
        for k in range(max_inv + 1):
            left = max(0, k - (m - 1))
            right = min(k, len(counts) - 1)
            new.append(prefix[right + 1] - prefix[left])
        counts = new
    total_pairs = n * (n - 1) // 2
    extreme = sum(count for inversions, count in enumerate(counts)
                  if abs(total_pairs - 2 * inversions) >= abs(observed_s))
    return float(extreme / math.factorial(n))


def _kendall_tau_b(x, y):
    concordant = discordant = tie_x = tie_y = 0
    for i in range(len(x) - 1):
        for j in range(i + 1, len(x)):
            dx, dy = x[j] - x[i], y[j] - y[i]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tie_x += 1
            elif dy == 0:
                tie_y += 1
            elif dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    den = math.sqrt((concordant + discordant + tie_x)
                    * (concordant + discordant + tie_y))
    if den == 0:
        raise ValueError("Kendall tau needs comparable pairs")
    tau = (concordant - discordant) / den
    n = len(x)
    has_ties = len(set(x)) < n or len(set(y)) < n
    if has_ties:
        # An exact conditional permutation test with ties requires a different
        # null distribution.  Do not silently substitute the no-tie normal
        # approximation; retain the tau and require the source's reported p.
        return float(tau), None, "SOURCE_P_REQUIRED_TIES"
    observed_s = concordant - discordant
    if n <= 200:
        return (float(tau), _kendall_exact_two_sided(n, observed_s),
                "KENDALL_EXACT_PERMUTATION")
    # Very large scatterplots would make the exact big-integer distribution
    # unnecessarily costly; the asymptotic no-tie variance is accurate there.
    z = tau * math.sqrt(9 * n * (n - 1) / (2 * (2 * n + 5)))
    return (float(tau), float(math.erfc(abs(z) / math.sqrt(2.0))),
            "KENDALL_NORMAL_APPROX_N_GT_200")


def summarize_association(points, association_type="PEARSON_R"):
    """Calculate a reported association from preserved digitized coordinates."""
    kind = str(association_type).strip().upper()
    x = np.asarray([p["x_value"] for p in points], dtype=float)
    y = np.asarray([p["y_value"] for p in points], dtype=float)
    if len(x) < 3:
        raise ValueError("at least three pairs are required")
    ties = bool(len(set(x)) < len(x) or len(set(y)) < len(y))
    # One test per statistic. Every branch below used to end in the same
    # Fisher-z normal approximation, labelled FISHER_Z_APPROX on all five - so a
    # slope, an R-squared and a rank correlation were reported as though the
    # same null distribution described them, on the ten-to-thirty points a
    # digitized scatter actually has.
    if kind == "PEARSON_R":
        value = _pearson(x, y)
        p, p_method = _t_p_from_r(value, len(x)), "PEARSON_T_TEST"
    elif kind == "SPEARMAN_RHO":
        value = _pearson(_average_ranks(x), _average_ranks(y))
        if ties:
            # Average ranks change the permutation null, and the untied
            # t-approximation is anticonservative under them. Same rule as
            # Kendall: keep the coefficient, refuse the p.
            p, p_method = None, "SOURCE_P_REQUIRED_TIES"
        else:
            # With no ties the rank pairs are a permutation of 1..n and the
            # t on n-2 df is the standard asymptotic test.
            p, p_method = _t_p_from_r(value, len(x)), "SPEARMAN_T_APPROX"
    elif kind == "KENDALL_TAU":
        value, p, p_method = _kendall_tau_b(x, y)
    elif kind == "R_SQUARED":
        r = _pearson(x, y)
        value = r * r
        # The model's own F: MSR/MSE with 1 and n-2 degrees of freedom. For a
        # one-predictor fit F = t^2 and the tail equals the Pearson t's, which
        # is the point - it is named for the test that was run.
        n = len(x)
        if value >= 1.0:
            p = 0.0
        else:
            p = snedecor_f_upper_tail((value / (1.0 - value)) * (n - 2), 1, n - 2)
        p_method = "R_SQUARED_F_TEST"
    elif kind == "SLOPE":
        value, p = _slope_t_p(x, y)
        p_method = "SLOPE_T_TEST"
    else:
        raise ValueError("unsupported association type: %s" % association_type)
    method = p_method
    return dict(Association_Type=kind, Association_Value=float(value),
                P_Value=None if p is None else float(p), N_Pairs=int(len(x)),
                P_Value_Method=method,
                # Every p this function returns was computed from the digitized
                # cloud, so it says so. A p copied out of the running text is
                # marked TRANSCRIBED by whoever copies it - the validator will
                # not let a computed method carry that label.
                P_Value_Extraction_Method=("" if p is None else "DIGITIZED"),
                # The tie state is the evidence behind the Kendall method choice.
                # Emitting it means the validator can contradict the reader
                # instead of trusting it.
                Ties_Present="TRUE" if ties else "FALSE")


def read_box_violin_panel(image, panel_box, x_positions, y_calibration,
                          half_window=18, threshold=100):
    """Read five-number summaries from boxes or box-overlaid violins.

    A density silhouette alone does not identify quartiles.  In that case this
    function returns no value and leaves the grid cell for manual review.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    dark = gray < int(threshold)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    for order, (label, x) in enumerate(x_positions.items()):
        xa, xb = max(x0, int(round(x)) - half_window), min(x1, int(round(x)) + half_window + 1)
        counts = dark[max(0, y0):min(dark.shape[0], y1), xa:xb].sum(axis=1)
        line_groups = _runs(np.where(counts >= 10)[0], gap=1)
        lines = []
        for group in line_groups:
            centre = y0 + float(np.mean(group))
            width = int(max(counts[group]))
            lines.append((centre, width))
        # Whisker caps + Q3 + median + Q1 must all be visible.  A pure violin,
        # or a violin with only a median dot, is not convertible to an IQR.
        if len(lines) != 5:
            continue
        box_lines = [row for row in lines if row[1] >= 20]
        if len(box_lines) != 3:
            continue
        values = sorted(y_calibration.pixel_to_value(row[0]) for row in lines)
        qvalues = sorted(y_calibration.pixel_to_value(row[0]) for row in box_lines)
        out.append(dict(
            order=order, x_label=label, x=float(x),
            whisker_lower=values[0], q1=qvalues[0], median=qvalues[1],
            q3=qvalues[2], whisker_upper=values[-1],
            Summary_Type="MEDIAN_IQR_RANGE", Marker_Definition="BOX_OVERLAY",
            # NOTHING ABOUT THE BOX SAYS WHICH SERIES IT IS. This reader takes no
            # series at all: it reads one five-number summary per declared x
            # position, and whichever series the cell belongs to was declared by
            # the manifest for the whole panel. That is R1 - a declaration, with
            # no competing identity to get wrong - and not R0, however carefully
            # the quartiles were measured.
            Identity_Method="DECLARED_SINGLE_SERIES",
            # The spread IS the box: three wide lines and two caps, all five
            # required present before a row is emitted at all.
            Dispersion_Method="DIRECT_BOX_GEOMETRY",
            # The five numbers are the box's own lines: three wide ones for the
            # quartiles and two caps, each required to be present before a row is
            # emitted at all.
            Value_Method="BOX_GEOMETRY",
        ))
    return out


BAR_FILL_PATTERNS = ("SOLID", "HATCHED", "STIPPLED", "OPEN")

#: Declarable, and not yet readable. `measure_mono_bars.py` separates STIPPLED
#: from the other three on publication 127 - 0.144-0.157 ink mass against
#: hatching's 0.262-0.318, and blank interior rows where hatching has none - but
#: that identity is figure-local and this reader is still absolute-banded. A
#: series declared STIPPLED therefore comes back UNREADABLE_FILL_PATTERN rather
#: than being squeezed into the HATCHED band, which is where it would land and
#: where it would be wrong without ever being flagged.
UNIMPLEMENTED_FILL_PATTERNS = ("STIPPLED",)

#: Interior dark density separates the three printed fills. Measured on a real
#: monochrome figure: solid 0.93, diagonal hatch 0.26, outline-only ~0.02. The
#: bands leave a wide dead zone on purpose - a bar landing in it is ambiguous
#: and is dropped rather than assigned to whichever series is listed first.
_FILL_BANDS = {"SOLID": (0.72, 1.01), "HATCHED": (0.12, 0.60), "OPEN": (-0.01, 0.06)}

#: A slot column counts as part of the bar when this fraction of the rows just
#: above the baseline are dark. Low enough for a hatched fill, high enough to
#: exclude the gap between two bars.
_FOOT_MIN_FRACTION = 0.15

#: Absolute floor for "this row is still inside the bar". An error-bar stem is
#: two pixels wide, so on a 55 px bar it reads about 0.04 - the floor has to sit
#: above that, or the walk climbs the whisker on an open bar.
_INSIDE_MIN_DENSITY = 0.15


def classify_bar_fill(interior):
    """SOLID / HATCHED / OPEN for a bar interior, or None when ambiguous."""
    if interior.size == 0:
        return None, 0.0
    density = float(interior.mean())
    hits = [k for k, (lo, hi) in _FILL_BANDS.items() if lo <= density < hi]
    return (hits[0] if len(hits) == 1 else None), density


def _mono_bar_errorbar(gray, dark, xc, edge, down, y0, y1, half_width=2,
                       max_whisker_px=90, min_cap_px=5, stem_threshold=200,
                       skip_px=2, min_stem_px=1):
    """Cap centre above a monochrome bar, only if a stem reaches the bar.

    The same trap as the colour reader: a significance glyph sits exactly where
    a cap sits and is exactly as black. The rule is physical - a cap counts only
    when a continuous vertical stroke joins it to the bar end.

    The stem gets its OWN, far more permissive threshold, and that is not a
    fudge. Grey level in a raster is ink coverage: a filled bar covers its
    pixels completely and reads near 0, while a one-pixel hairline at 60%
    coverage reads about 140 on the same figure. Thresholding both at 128 found
    every cap and no stem, so on publication 397 the reader confirmed nothing
    and returned no dispersion at all - a fail-closed answer produced by a
    measurement error rather than by the figure.

    Returns (cap_row, stem_confirmed) or (None, False).
    """
    step = 1 if down else -1
    edge = int(round(edge))
    start = edge + step * skip_px            # clear of the bar's own top stroke
    limit = (min(int(y1), start + max_whisker_px) if down
             else max(int(y0), start - max_whisker_px))
    rows = (range(start + 1, limit) if down else range(limit, start))
    faint = gray < stem_threshold
    # One pixel is enough, and has to be: a hairline stem IS one pixel wide.
    # Demanding two meant the reader confirmed no stem anywhere on publication
    # 397 and reported no dispersion at all. The protection against noise is not
    # the per-row count - it is that the run must be contiguous and must reach
    # the bar, which a stray speck never does.
    stem = [y for y in rows
            if faint[y, max(0, xc - half_width):xc + half_width + 1].sum()
            >= min_stem_px]
    if not stem:
        return None, False
    groups = _runs(stem, gap=2)
    attached = [g for g in groups
                if ((g[0] <= start + 4) if down else (g[-1] >= start - 4))]
    if not attached:
        return None, False
    segment = attached[0] if down else attached[-1]
    if len(segment) < 3:
        return None, False        # a speck touching the bar is not a whisker
    far = segment[-1] if down else segment[0]
    caps = []
    for n in range(8):
        y = far - step * n
        if not (0 <= y < dark.shape[0]):
            break
        if dark[y, max(0, xc - 12):xc + 13].sum() >= min_cap_px:
            caps.append(y)
        elif caps:
            break
    return ((caps[0] + caps[-1]) / 2.0 if caps else float(far)), True


def _mono_bar_extent(column, zero_rel, foot_px=10, stroke_px=8,
                     edge_rule="BASELINE_WALK"):
    """Bar end, column range and direction for one slot, walked from the baseline.

    Finding the end by "the first row spanning half the slot" looks right and is
    not. An error-bar cap is drawn about 70% of the bar's width, so on a narrow
    bar the cap clears that bar and the reader takes the whisker tip as the
    value - reading every mean high by one SD, silently, in one direction.

    Walking UP FROM THE BASELINE instead removes the cap from the question
    entirely: a bar has two side strokes continuous from the baseline to its
    end, and a floating cap has none. The walk stops before it ever reaches the
    cap. It also works identically for solid, hatched and open bars, which the
    density-based approach does not - an open bar has nothing but its outline.

    Returns (edge_row, bar_x0, bar_x1, is_downward) or None.
    """
    height, width = column.shape
    zero = int(round(zero_rel))
    if width < 4 or not (0 <= zero < height):
        return None
    # Measure the true bar width where the bar certainly is: against the
    # baseline. The slot includes the gap to the next bar; the bar does not.
    foot = column[max(0, zero - foot_px):max(1, zero - 1)]
    if not foot.size:
        return None
    present = np.where(foot.sum(axis=0) >= _FOOT_MIN_FRACTION * foot.shape[0])[0]
    if not len(present):
        # An empty slot, or a bar so short it never rises above the baseline.
        return None
    bx0, bx1 = int(present[0]), int(present[-1])
    body = column[:, bx0:bx1 + 1]
    if body.shape[1] < 4:
        return None
    if edge_rule == "FIRST_WIDE_ROW":
        # The defective rule, kept callable so the suite can SHOW the cap being
        # taken as the bar end rather than merely assert it is not. Never used
        # by the reader itself.
        wide = np.where(column.sum(axis=1) >= 0.5 * column.shape[1])[0]
        if not len(wide):
            return None
        down = abs(int(wide.max()) - zero) > abs(int(wide.min()) - zero)
        return float(wide.max() if down else wide.min()), bx0, bx1, down
    if edge_rule != "BASELINE_WALK":
        raise ValueError("edge_rule must be BASELINE_WALK or FIRST_WIDE_ROW")
    # Two independent signs that a row is still inside the bar, because no one
    # of them survives all three fills on a real raster:
    #
    #   side strokes - definitive for an OPEN bar, which is nothing but its
    #     outline, and reliable for a crisp vector figure
    #   row density  - the only thing left on a JPEG-softened HATCHED bar, whose
    #     1 px outline does not survive the threshold at all. Measured against
    #     the bar's OWN density at the baseline, so a 25%-dark hatch is compared
    #     with a 25%-dark hatch and not with a solid fill.
    #
    # The floor matters as much as the ratio: an open bar's foot density is
    # about 0.04, and half of that is below the density of the error-bar STEM,
    # so a purely relative rule walks straight up the whisker.
    left, right = body[:, :2].any(axis=1), body[:, -2:].any(axis=1)
    bar_w = bx1 - bx0 + 1
    foot_density = float(foot[:, bx0:bx1 + 1].mean()) if foot.size else 0.0
    floor = max(0.5 * foot_density, _INSIDE_MIN_DENSITY)
    density = body.sum(axis=1) / float(bar_w)

    def inside(row):
        return bool((left[row] and right[row]) or density[row] >= floor)

    def walk(start, step):
        row = start
        while 0 <= row + step < height and inside(row + step):
            row += step
        return row

    up_end, down_end = walk(zero - 2, -1), walk(zero + 2, 1) if zero + 2 < height else zero
    down = abs(down_end - zero) > abs(up_end - zero)
    edge = down_end if down else up_end
    # A stroked outline's data coordinate is the centre of the stroke. A solid
    # fill has no separate outline, so its edge IS the coordinate - extend only
    # across a stroke-thick run, never across the body of a filled bar.
    step = 1 if down else -1
    far = edge
    while (0 <= far + (-step) < height and abs(far - edge) < stroke_px
           and body[far + (-step)].sum() >= 0.8 * bar_w):
        far += -step
    return (((edge + far) / 2.0 if abs(far - edge) < stroke_px else float(edge)),
            bx0, bx1, down)


def read_monochrome_bar_panel(image, panel_box, x_positions, y_calibration, series,
                              group_window=70, threshold=128, baseline_value=0.0,
                              min_bar_px=12, edge_rule="BASELINE_WALK",
                              stem_threshold=200):
    """Read grouped monochrome bars separated by FILL PATTERN, not by colour.

    Solid-versus-hatched is how a black-and-white bar chart names its series,
    and no colour mask can see the difference. Within one x group the bars are
    adjacent, so the group is split into len(series) slots and each slot is
    classified by the dark density of its interior.

    Two geometric rules carry over from the colour reader because they are facts
    about printed figures, not about one publication:

    * the data coordinate is the OUTLINE, found as the first row spanning half
      the slot width - not the topmost dark pixel, which is the error-bar cap.
      Sampling the interior below that pixel lands in the whisker's white space
      and reads every fill as OPEN.
    * a cap counts only when a stem physically joins it to the bar.

    Fail-closed: if two slots classify the same way, or any slot is ambiguous,
    the whole group is dropped. A group that cannot be told apart produces no
    rows and the grid gate reports the missing cells.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    dark = gray < int(threshold)
    x0, x1, y0, y1 = map(int, panel_box)
    zero_row = y_calibration.value_to_pixel(baseline_value)
    want = []
    for spec in series:
        pattern = str(spec.bar_fill or "").strip().upper()
        if pattern in UNIMPLEMENTED_FILL_PATTERNS:
            # UnsupportedCapabilityError, not ValueError. `run_batch` maps
            # ValueError to PANEL_GEOMETRY_UNRESOLVED, so raising one here would
            # file "this reader has no STIPPLED" under "this panel's geometry
            # cannot be trusted" - fail-closed with the wrong reason on the
            # record, which is the kind of thing a reviewer acts on and a
            # maintainer chases. UnsupportedCapabilityError maps to
            # NO_READER_AVAILABLE, which is what this is.
            raise UnsupportedCapabilityError(
                "SeriesSpec %r declares bar_fill=%r. The manifest vocabulary "
                "accepts it and this reader cannot read it: its fill classifier "
                "is absolute-banded and %s has no band, so the bar would be "
                "assigned to whichever band it happened to fall in. Read the "
                "panel with measure_mono_bars.py, or queue it for manual "
                "extraction." % (spec.name, spec.bar_fill, pattern))
        if pattern not in BAR_FILL_PATTERNS:
            raise ValueError(
                "SeriesSpec.bar_fill must be one of %s for a monochrome bar "
                "series; %r declares %r" % ("/".join(BAR_FILL_PATTERNS),
                                            spec.name, spec.bar_fill))
        want.append(pattern)
    if len(set(want)) != len(want):
        raise ValueError("two monochrome bar series share a fill pattern, so no "
                         "reader can separate them: %s" % want)
    out = []
    for order, (label, gx) in enumerate(x_positions.items()):
        xa, xb = max(x0, int(gx) - group_window), min(x1, int(gx) + group_window + 1)
        band = dark[y0:y1, xa:xb]
        columns = band.sum(axis=0)
        idx = [i for i, v in enumerate(columns) if v > 0.06 * band.shape[0]]
        if not idx:
            continue
        lo, hi = idx[0], idx[-1]
        if hi - lo + 1 < min_bar_px * len(series):
            continue
        width = (hi - lo + 1) / float(len(series))
        slots = []
        for k in range(len(series)):
            sa = int(round(lo + k * width)) + 2
            sb = int(round(lo + (k + 1) * width)) - 2
            if sb - sa < 4:
                slots = []
                break
            found = _mono_bar_extent(band[:, sa:sb], zero_row - y0,
                                     edge_rule=edge_rule)
            if found is None:
                slots = []
                break
            edge, bx0, bx1, down = found
            # Sample the interior INSIDE the outline. Including the two side
            # strokes lifted an open bar's density from ~0.02 to 0.16 and put it
            # in the hatched band - the reader then named the wrong series with
            # complete confidence, which is worse than reading nothing.
            inset = max(3, int(round(0.16 * (bx1 - bx0 + 1))))
            body = band[:, sa + bx0 + inset:sa + bx1 + 1 - inset]
            if body.shape[1] < 3:
                slots = []
                break
            inner = int(round(edge))
            interior = (body[max(0, inner - 40):max(0, inner - 6)] if down
                        else body[inner + 6:inner + 46])
            fill, density = classify_bar_fill(interior)
            slots.append(dict(fill=fill, density=density, edge=y0 + edge, down=down,
                              xc=xa + sa + (bx0 + bx1) // 2))
        if not slots or any(s["fill"] is None for s in slots):
            continue
        if sorted(s["fill"] for s in slots) != sorted(want):
            continue          # cannot name the series - leave the cells missing
        group = []
        for spec in series:
            match = [s for s in slots
                     if s["fill"] == str(spec.bar_fill).strip().upper()]
            if len(match) != 1:
                group = []
                break
            s = match[0]
            cap, stem = _mono_bar_errorbar(gray, dark, s["xc"], s["edge"],
                                           s["down"], y0, y1,
                                           stem_threshold=stem_threshold)
            mean = y_calibration.pixel_to_value(s["edge"])
            dispersion = (None if cap is None
                          else abs(y_calibration.pixel_to_value(cap) - mean))
            group.append(dict(
                series=spec.name, order=order, x_label=label, x=float(s["xc"]),
                top_px=float(s["edge"]), cap_px=(None if cap is None else float(cap)),
                mean=mean, dispersion=dispersion,
                fill_pattern=s["fill"], fill_density=round(s["density"], 3),
                Bar_Direction="DOWN" if s["down"] else "UP",
                Bar_Top_Definition="OUTLINE_CENTER",
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
            ))
        out.extend(group)
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


def read_monochrome_bar_geometry(image, panel_box, x_positions, y_calibration,
                                 fills, group_window=70, baseline_value=0.0,
                                 threshold=128, stem_threshold=200,
                                 min_bar_px=MONO_GEOMETRY.MIN_BAR_PX,
                                 review_crop_box=None, *, panel_id,
                                 identity_domain_id, figure_id=""):
    """The bars of one panel, measured and NOT named.

    The production entry point to `mono_bar_geometry`. It exists beside
    `read_monochrome_bar_panel` rather than replacing it because the two answer
    different questions and only one of them can be answered by a panel.

    `read_monochrome_bar_panel` returns rows carrying a `series`. To do that it
    has to decide, inside one panel, which bar is which - and the only evidence a
    panel holds is an absolute fill density compared against `_FILL_BANDS`, which
    were measured on a single figure and do not fit the second one. This returns
    the geometry with the identity left open: every record says
    `identity_status: NOT_CALIBRATED` and carries an empty
    `resolved_fill_pattern`.

    Naming happens afterwards, across the whole figure, in
    `mono_bar_geometry.fill_identities_by_figure` - which needs samples from
    every panel of the figure before it can say what the figure's fills look
    like, and refuses when they do not separate. That is why this cannot simply
    be folded into the existing reader: the caller has to collect panels first.

    `fills` is the group's DECLARATION - the multiset of patterns the panel is
    supposed to contain, checked against what the fills measure. It is not a
    per-slot identification and the order it is written in does not reach the
    records: pass the same patterns in any order and the rows are identical.

    **`panel_id` and `identity_domain_id` are required, and keyword-only.** They were
    keyword arguments defaulting to `""`, which is the shape that made the
    defect they exist to prevent invisible. `fill_identities_by_figure` buckets
    on `identity_domain_id`, so a caller that forgot it got one bucket named `""` holding
    every panel of every figure it had measured - and those panels calibrate a
    shared fill vocabulary. Two publications pooled into one vocabulary is not a
    crash; it is a plausible answer, computed from the wrong figure. Blank is
    refused for the same reason a missing argument is.

    Every option `batch_manifests.READER_OPTIONS` declares for BAR_MONO is a
    parameter here, under the keyword the option maps to, because a declared
    option that a reader does not take is either a TypeError mid-run or - worse
    - a setting written in a manifest, validated, and silently ignored.
    `min_bar_px` changed grain when it moved here; `MONO_GEOMETRY.MIN_BAR_PX`
    says how, and a manifest carrying the old number keeps working.

    `review_crop_box` is NOT one of them, and is deliberately not a
    `READER_OPTIONS` entry: it is caller-derived context - the plot area unioned
    with the manifest's `Axis_X_Region` and `Axis_Y_Region` - rather than a
    setting somebody tunes. It has to come through here all the same, or a
    caller wanting a declared review crop has to bypass the shared entry point
    and call `geometry_rows` directly, which is most of the reason the shared
    entry point exists.

    `image` may be a PIL Image or an ndarray. An ndarray is taken as it is
    given: HxWx3 is treated as RGB and converted, HxW as greyscale already. The
    wrapper used to call `.convert("RGB")` unconditionally, so a caller holding
    the array this package works in internally had to wrap it in an Image to
    hand it back.
    """
    for name, value in (("panel_id", panel_id), ("identity_domain_id", identity_domain_id)):
        if not str(value or "").strip():
            raise ValueError(
                "read_monochrome_bar_geometry: %s must name the %s these rows "
                "belong to; blank pools unrelated figures into one fill "
                "vocabulary" % (name, "panel" if name == "panel_id" else "figure"))
    if isinstance(image, np.ndarray):
        arr = np.asarray(image)
        gray = (arr.astype(np.uint8) if arr.ndim == 2 else
                MONO_GEOMETRY._gray_from_rgb(arr[:, :, :3].astype(np.uint8)))
    else:
        gray = MONO_GEOMETRY._gray_from_rgb(
            np.asarray(image.convert("RGB")).astype(np.uint8))
    return MONO_GEOMETRY.geometry_rows(
        gray, panel_box, y_calibration, x_positions, list(fills), group_window,
        baseline=baseline_value, threshold=threshold,
        stem_threshold=stem_threshold, min_bar_px=min_bar_px,
        review_crop_box=review_crop_box, panel_id=panel_id,
        identity_domain_id=identity_domain_id, figure_id=figure_id)


MARK_TYPES = ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO",
              "LINE_MONO_STYLE", "SCATTER", "BOX_VIOLIN")

#: Bumped whenever a reader's numerical output can change. A batch run records
#: it beside the image hash and the config hash, so "the numbers moved" can be
#: attributed instead of argued about.
READER_VERSION = "7.3"


def read_panel(mark_type, **kwargs):
    """Dispatch a declared graphical mark to its reader adapter.

    Routing is explicit and fails closed.  Caption words or study identities
    never silently select a numerical reader.
    """
    kind = str(mark_type).strip().upper()
    if kind == "LINE_COLOR":
        return read_line_marker_panel(**kwargs)
    if kind == "LINE_MONO":
        return read_monochrome_marker_panel(**kwargs)
    if kind == "LINE_MONO_STYLE":
        # Imported here rather than at module scope: `line_style_mono` imports
        # from this module, and a top-level import would be a cycle.
        from line_style_mono import read_monochrome_line_panel
        return read_monochrome_line_panel(**kwargs)
    if kind == "BAR_MONO":
        # NOT `read_monochrome_bar_panel`, which is what this line used to call.
        #
        # That reader classifies a fill against ABSOLUTE density bands measured on
        # one publication, panel by panel. The pipeline stopped using it: a
        # monochrome fill is figure-local, so `run_batch` measures every BAR_MONO
        # panel of a figure with no series named, pools the samples, and lets the
        # FIGURE say what its fills mean - which is the whole of
        # `mono_bar_geometry.fill_identity`, and the only path that produces
        # `Auto_Identity_Method`, STIPPLED support and a durable geometry row.
        #
        # So the generic entry point was quietly the OTHER reader. An agent
        # reaching for `read_panel("BAR_MONO", ...)` - the obvious thing to reach
        # for - got a different answer from the pipeline, with no identity
        # provenance and a different fill vocabulary, and nothing said so.
        raise UnsupportedCapabilityError(
            "BAR_MONO is read in two passes and cannot be dispatched per panel: "
            "a monochrome fill means what the FIGURE's other groups say it "
            "means, so the panels of one figure are measured together and named "
            "afterwards. Use `mono_bar_geometry.geometry_rows` for one panel's "
            "measurements and `fill_identities_by_figure` to name them, or "
            "`run_batch` for the whole thing. "
            "`read_monochrome_bar_panel` is the single-panel absolute-band "
            "reader this call used to reach: it is kept for diagnostics, it "
            "produces no identity provenance, and it is not what the pipeline "
            "runs.")
    if kind == "SCATTER":
        return read_scatter_panel(**kwargs)
    if kind == "BOX_VIOLIN":
        return read_box_violin_panel(**kwargs)
    if kind == "BAR_COLOR":
        from bar_reader import colour_masks, read_bar_panel
        image = kwargs.pop("image")
        # `declared_colours` is {Series_ID: (hex, tolerance)}. When it is given,
        # each series gets a mask built from what the manifest says its colour
        # is, instead of choosing between three hard-coded ones tuned on a
        # single publication.
        declared = kwargs.pop("declared_colours", None)
        masks = colour_masks(
            image.convert("RGB") if isinstance(image, Image.Image) else image,
            declared=declared)
        return read_bar_panel(masks=masks, **kwargs)
    raise ValueError("unknown mark type %r; expected %s" % (mark_type, "/".join(MARK_TYPES)))


#: Every column an ASSOCIATION cell must carry from the reader into the values
#: file. The validator gates on all seven; the adapter used to copy five, so two
#: reader-supplied provenance fields died between the reader and the gate. Keep
#: this list and `fig_values_columns()` in step - `test_mark_readers.py` asserts
#: the containment, so adding a field to one and not the other fails the suite.
#: Mark-level facts every value row carries out of the reader, whatever the
#: statistic. These used to stop at `to_value_records`, which copied mean,
#: dispersion and bounds and dropped the rest - so nothing downstream could tell
#: a whisker the reader had confirmed from one it had not.
MARK_CARRIED = (
    ("Errorbar_Stem_Confirmed", "Errorbar_Stem_Confirmed"),
    # HOW the series was named and HOW the number was got. Universal on purpose:
    # every reader answers both questions whether or not it has been taught to
    # say so, and a field only the readers that answer it carry is a field the
    # gate cannot require. Blank until each reader is taught, and blank is
    # priced at the HIGHEST review tier by `provenance.review_tier` - the fields
    # can only make a value harder to pool, never easier.
    ("Identity_Method", "Identity_Method"),
    ("Value_Method", "Value_Method"),
    # And the third: how the DISPERSION was got. Universal for the same reason
    # the first two are - every reader that emits an error bar answers it, and a
    # blank beside a dispersion NUMBER prices at the highest tier rather than the
    # lowest.
    ("Dispersion_Method", "Dispersion_Method"),
    ("Bar_Top_Definition", "Bar_Top_Definition"),
    ("Bar_Direction", "Bar_Direction"),
    ("Position_Assignment", "Position_Assignment"),
    ("calib_max_resid", "Calibration_Max_Residual"),
    ("slot_residual_px", "Slot_Assignment_Residual_Px"),
)

#: Carried exactly like `MARK_CARRIED` and listed apart from it, because these
#: are not universal: only a monochrome bar HAS them. Every reader emits a bar
#: top definition and a calibration residual; only BAR_MONO has a series whose
#: identity is a separate claim from its number, so a line panel's value rows
#: carry none of the six and must not be required to.
#:
#: What they carry is WHERE THE VALUE CAME FROM AND WHO NAMED ITS SERIES. A
#: BAR_MONO value is a measurement of one anonymous row plus an identity
#: established somewhere else, and until these six columns existed the join
#: stopped at the raw marks: `figure_values_accepted.csv` held a mean under a
#: series heading with nothing binding it to the row it was measured from, and
#: no way to ask whether a person or the figure decided which series it was.
IDENTITY_CARRIED = (
    # `Geometry_Row_SHA256` is the anonymous measurement's own hash, taken
    # before any identity touched the record - so it still answers "is this the
    # same bar the reviewer approved" after a resolution is applied.
    ("Geometry_Row_SHA256", "Geometry_Row_SHA256"),
    # `Auto_Fill_Pattern` is what the READER measured and stays blank when it
    # measured nothing; `Resolved_Fill_Pattern` is what the series was finally
    # taken to be. Two columns, because collapsing them loses the distinction
    # the geometry artifact is built around.
    ("Auto_Fill_Pattern", "Auto_Fill_Pattern"),
    ("Resolved_Fill_Pattern", "Resolved_Fill_Pattern"),
    ("Identity_Source", "Identity_Source"),
    ("Identity_Evidence_Type", "Identity_Evidence_Type"),
    ("Resolution_ID", "Resolution_ID"),
)



#: WHAT A RECONSTRUCTED NUMBER WAS RECONSTRUCTED FROM. Carried like
#: `IDENTITY_CARRIED` and listed apart from `MARK_CARRIED` for the same reason:
#: only a reader that interpolates HAS these, and a line panel's three-pixel span
#: is not a question a bar reader can answer.
#:
#: They existed on the reader row from v7.58 and stopped there. `Inference_ID`
#: was then bound to them in v7.66 - the recipe named all eight - and every one
#: of them hashed as the empty string, because the value row the finalizer
#: re-derives from did not carry them. The comment beside the recipe said "every
#: field must be one the VALUE ROW carries"; nothing checked that it was true,
#: which is the same defect as v7.51's field whitelist and was found the same
#: way, by looking at what an artifact actually contained.
INTERPOLATION_CARRIED = (
    ("Value_Span_Px", "Value_Span_Px"),
    ("Value_Support_Left_Px", "Value_Support_Left_Px"),
    ("Value_Support_Right_Px", "Value_Support_Right_Px"),
    ("Occlusion_Cause", "Occlusion_Cause"),
    ("Occlusion_Width_Px", "Occlusion_Width_Px"),
    ("Local_Stroke_Px", "Local_Stroke_Px"),
    ("Expected_Dash_Gap_Px", "Expected_Dash_Gap_Px"),
    ("Trace_Agreement", "Trace_Agreement"),
)


ASSOCIATION_CARRIED = (
    "Association_Type", "Association_Value", "P_Value", "P_Value_Method",
    "N_Pairs", "P_Value_Extraction_Method", "Ties_Present",
    "Point_Data_Reference",
    # What the reader counted, against what the paper says it should have
    # counted. `N_Pairs` alone cannot distinguish "twelve subjects" from "twelve
    # blobs that survived an area filter".
    "Expected_N_From_Source", "Detected_Unique_Point_Count",
    "Point_Count_Agreement", "Overplotting_Possible",
    "Series_Mask_Overlap_Count",
)


#: Bumped to /3 in v7.70: every point now records how its series was named, and
#: the record carries the one method they all agree on. A reader of a /2 file
#: cannot distinguish "no method" from "the field did not exist yet".
POINT_DATA_SCHEMA = "figure-digitization-triage/point-data/3"


def _calibration_record(cal):
    if cal is None:
        return None
    return dict(slope=float(cal.slope), intercept=float(cal.intercept),
                scale=str(cal.scale),
                max_residual=float(getattr(cal, "max_residual", 0.0)))


def write_point_data(points, path, unit_id, cell_key, source_image,
                     image_sha256, x_calibration, y_calibration,
                     panel_id=None, reader=None, tolerance=1e-6):
    """Persist the digitized point cloud an association was computed from.

    A digitized r or tau is a claim about a set of coordinates nobody else can
    see. Writing them next to the value is what makes the claim checkable, and
    the validator requires the path on every digitized association row.

    Calibrated x/y alone are NOT enough to reproduce anything. They are already
    the reader's answer: if the calibration was wrong, the saved values are
    wrong in exactly the same way and nothing in the file disagrees with
    anything else. What makes the record checkable is the pair - the raw pixel
    the reader actually measured, and the calibration it applied - plus enough
    identity to say which image, which cell and which series each point belongs
    to. All of it is required; a point file that cannot be traced back to a row
    is not provenance.

    Every point is re-derived from its own pixel and calibration before the file
    is written, and a mismatch beyond `tolerance` raises. A file whose values do
    not follow from its own pixels is internally inconsistent, and the moment to
    find that out is at write time.

    Returns `path`, so it composes into a `to_value_records` call.
    """
    import json
    import os
    for name, value in (("unit_id", unit_id), ("cell_key", cell_key),
                        ("source_image", source_image),
                        ("image_sha256", image_sha256),
                        ("y_calibration", y_calibration)):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(
                "write_point_data needs %s: a point cloud that cannot be traced "
                "back to an image and a cell is not provenance" % name)
    rows = []
    for i, p in enumerate(points):
        for key in ("x_value", "y_value", "point_px_x", "point_px_y"):
            if p.get(key) is None:
                raise ValueError(
                    "point %d has no %s - a digitized point without its raw "
                    "pixel cannot be re-derived, only re-trusted" % (i, key))
        px, py = float(p["point_px_x"]), float(p["point_px_y"])
        xv, yv = float(p["x_value"]), float(p["y_value"])
        if x_calibration is not None:
            back = x_calibration.pixel_to_value(px)
            if abs(back - xv) > tolerance * max(1.0, abs(xv)):
                raise ValueError(
                    "point %d: x_value=%r does not follow from pixel %r under "
                    "the given calibration (would be %r)" % (i, xv, px, back))
        back = y_calibration.pixel_to_value(py)
        if abs(back - yv) > tolerance * max(1.0, abs(yv)):
            raise ValueError(
                "point %d: y_value=%r does not follow from pixel %r under the "
                "given calibration (would be %r)" % (i, yv, py, back))
        rows.append(dict(series=(None if p.get("series") is None else str(p["series"])),
                         point_px_x=px, point_px_y=py, x_value=xv, y_value=yv,
                         # HOW THIS POINT'S SERIES WAS NAMED, in the durable
                         # file. The association row copies it off the points and
                         # nothing could check that copy: a summary claiming
                         # MEASURED_COLOUR over a cloud read from a grey
                         # threshold was un-refutable from the artifact.
                         Identity_Method=str(p.get("Identity_Method") or "")))
    # ONE ANSWER, OR THE FILE SAYS SO. Every point of one series is named the
    # same way by every reader in this package, and a future one that mixes them
    # would make the association row's single `Identity_Method` a lie - so the
    # record carries the agreed method, or the empty string where they disagree,
    # and the finalizer can compare the row against the cloud it came from.
    methods = {str(r.get("Identity_Method") or "") for r in rows}
    record = {
        "schema": POINT_DATA_SCHEMA,
        "Identity_Method": (methods.pop() if len(methods) == 1 else ""),
        "Unit_ID": str(unit_id), "Cell_Key": str(cell_key),
        "Panel_ID": None if panel_id is None else str(panel_id),
        "Source_Image": str(source_image), "Image_SHA256": str(image_sha256),
        "Reader": None if reader is None else str(reader),
        "Reader_Version": READER_VERSION,
        "X_Calibration": _calibration_record(x_calibration),
        "Y_Calibration": _calibration_record(y_calibration),
        "n_pairs": len(rows), "points": rows,
    }
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    return path


def read_point_data(path):
    """Load a point file and re-derive every value from its own pixels.

    Raises if the file was written by an older schema, if a value no longer
    follows from its pixel under the recorded calibration, or if the recorded
    pair count disagrees with the points actually present.
    """
    import json
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    if record.get("schema") != POINT_DATA_SCHEMA:
        raise ValueError("%s is schema %r, expected %r - an older point file "
                         "has no pixels to re-derive from"
                         % (path, record.get("schema"), POINT_DATA_SCHEMA))
    points = record.get("points") or []
    if record.get("n_pairs") != len(points):
        raise ValueError("%s says n_pairs=%r but carries %d points"
                         % (path, record.get("n_pairs"), len(points)))
    for axis, key in (("Y_Calibration", "y_value"), ("X_Calibration", "x_value")):
        cal = record.get(axis)
        if cal is None:
            continue
        fitted = AxisCalibration(float(cal["slope"]), float(cal["intercept"]),
                                 str(cal["scale"]))
        pixel_key = "point_px_y" if axis.startswith("Y") else "point_px_x"
        for i, p in enumerate(points):
            back = fitted.pixel_to_value(float(p[pixel_key]))
            if abs(back - float(p[key])) > 1e-6 * max(1.0, abs(float(p[key]))):
                raise ValueError("%s point %d: %s does not follow from %s"
                                 % (path, i, key, pixel_key))
    return record


def sha256_of(path):
    """SHA-256 of a file, for the image identity a point file records."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cell_key(levels):
    return ";".join("%s=%s" % (str(k).strip().upper(), str(v).strip().upper())
                    for k, v in sorted(levels.items(), key=lambda item: str(item[0]).upper()))


def to_value_records(rows, statistic_type, unit_id, x_factor=None,
                     series_factor=None, cell_levels=None,
                     point_data_reference=None):
    """Convert adapter rows into the common Unit_ID x Cell_Key grain.

    `point_data_reference` fills that column on ASSOCIATION rows that do not
    already carry one. `summarize_association` cannot know where the caller
    chose to write the points, so the path enters here; pass the return value
    of `write_point_data`.
    """
    kind = str(statistic_type).strip().upper()
    out = []
    for row in rows:
        levels = dict(cell_levels or {})
        if x_factor:
            if "x_label" not in row:
                raise ValueError("%s needs x_label for factor %s" % (kind, x_factor))
            levels[x_factor] = row["x_label"]
        if series_factor:
            if "series" not in row:
                raise ValueError("%s needs series for factor %s" % (kind, series_factor))
            levels[series_factor] = row["series"]
        if not levels:
            raise ValueError("at least one Cell_Key factor must be supplied")
        record = dict(Unit_ID=unit_id, Cell_Key=_cell_key(levels))
        for source, column in (MARK_CARRIED + IDENTITY_CARRIED
                               + INTERPOLATION_CARRIED):
            if row.get(source) is not None:
                record[column] = row.get(source)
        if kind == "CONTINUOUS":
            record.update(Mean=row.get("mean"), Dispersion_Value=row.get("dispersion"),
                          Errorbar_Lower=row.get("errorbar_lower"),
                          Errorbar_Upper=row.get("errorbar_upper"))
        elif kind == "QUANTILE_SUMMARY":
            record.update(Median=row.get("median"), Q1=row.get("q1"), Q3=row.get("q3"),
                          Whisker_Lower=row.get("whisker_lower"),
                          Whisker_Upper=row.get("whisker_upper"))
        elif kind == "ASSOCIATION":
            # Every field the validator gates on must survive the adapter. The
            # three provenance columns were dropped here, so a reader that
            # emitted them correctly still produced rows the gate then failed -
            # or worse, rows that passed because the gate saw blanks it read as
            # "not applicable". ASSOCIATION_CARRIED is asserted by the tests.
            for key in ASSOCIATION_CARRIED:
                record[key] = row.get(key, "")
            if not record.get("Point_Data_Reference") and point_data_reference:
                record["Point_Data_Reference"] = point_data_reference
        else:
            raise ValueError("unsupported statistic type %r" % statistic_type)
        out.append(record)
    return out
