# -*- coding: utf-8 -*-
"""Which of several monochrome marker series each mark belongs to, or a refusal.

`mark_readers.read_scatter_panel` refuses more than one monochrome series: a
shared threshold cannot say which mark is which, and guessing would put a
plausible number under the wrong heading. That refusal is right and stays. This
module is the evidence that would let it be lifted - and it produces a REFUSAL
PER MARK wherever the evidence is not there, rather than a verdict for the panel.

    route(image, panel_box, series) -> [record, ...]

WHAT IT DOES NOT DO. It does not calibrate, does not name a series' meaning, and
does not decide anything about the y axis. A twin-axis figure needs a second
calibration and an axis grain to hang it on; this answers the other half - which
mark is which - on ONE axis, and says so.

## Two thresholds, and neither is a number in this file

A marker is not a number of pixels: it is a mark a plotting program drew at one
setting, and how many pixels that is depends on how the page was rendered. So
the size window is measured off the panel - the median side of its own
near-square components - exactly as the line readers measure their stroke.

Shape and fill are decided the same way, by the PANEL'S OWN distribution:

    circularity   a disc and a triangle sit at different values, and a panel
                  drawing both has a bimodal set
    interior ink  a ring's middle is white and a disc's is black, and a panel
                  drawing both has a bimodal set

`_split` finds the largest gap in a sorted set and compares it with the largest
gap WITHIN either side of it. A real bimodal split has a between-gap wider than
any within-gap; a single blurred cluster does not. That test is scale-free, needs
no constant, and is the whole reason this module can refuse instead of guessing:
on `twin_scatter_micro.jpeg` - markers 3 px across - the open triangles reach a
HIGHER interior ink ratio than the filled ones, no split exists, and every mark
comes back with its shape and `MARKER_FILL_UNRESOLVED`.

## The shape axis does not separate yet, and this file says so

Three discriminants have been measured on this fixture family and none of them
splits CIRCLE from TRIANGLE:

    circularity     of the marker's ink cut out of the chain it sits in. Comes
                    back HIGHER for triangles (0.56-0.62) than for discs
                    (0.38-0.44), because the dilation that recovers a marker's
                    corners also recovers the stubs of the line that crossed it
                    and a perimeter is the measurement that ruins first.
    corner count    a continuum from 3 to 7 with no gap - triangles at 3-4,
                    circles at 4-7, overlapping at 4, for the same reason.
    bbox extent     measured on the OPENED blob, which has no line in it. The
                    opening that removed the line rounded the triangles:
                    circles 0.65-0.78 against triangles 0.55-0.78.

So `route` refuses the shape of every mark on these renderings, and NOTHING is
misrouted - the scored comparison against the fixture's own centres is 0 wrong
at every rendering. That is the state `test_marker_routing.py` pins. The day a
fourth discriminant works, the scenario that says "the shape axis does not
separate" fails and has to be changed on purpose, which is the point of pinning
a negative.

The FILL axis does separate, and by the panel's own gap: interior ink 0.05-0.46
for rings against 0.85-0.93 for discs at s3, and no split at all at 3 px.

## What a refusal is worth

`twin_scatter_s3.jpeg` asked for one monochrome series returns 26 marks for 30
drawn and r = -0.686 where the four series were drawn at -0.85 to -0.99; at
another scale of the SAME drawing it returns 82. A number that moves with the
page size is not a reading. Refusing the marks whose class is not established
costs those marks and keeps the rest.
"""
import collections
import math

import cv2
import numpy as np
from PIL import Image

#: How far from the panel's own marker size a component may be and still be one.
#: A ratio, not a pixel count.
SIZE_LO, SIZE_HI = 0.55, 1.75
#: Beyond this, one component holds more than one marker.
MERGED_AREA = 2.0
#: The middle of a marker, as a fraction of its side. Small enough that a ring's
#: stroke does not reach it at the sizes a journal prints.
INTERIOR = 0.28
#: A component this much longer than it is tall is a rule or a curve, not a mark.
ASPECT = 1.8

SHAPES = ("CIRCLE", "TRIANGLE")
FILLS = ("OPEN", "FILLED")

#: Every answer this module gives that is not a series.
REFUSALS = ("NOT_A_MARKER", "MARKER_MERGED", "MARKER_SHAPE_UNRESOLVED",
            "MARKER_FILL_UNRESOLVED", "MARKER_CLASS_NOT_DECLARED")

# A PROXIMITY RULE WAS HERE AND WAS REMOVED. It refused any mark with another
# blob within 0.75 of a marker, to stop a touching neighbour's ink being
# measured as this marker's fill. Setting its threshold to zero broke no
# scenario: once `MARK_MARGIN` refuses marks sitting on the boundary, the marks
# the proximity rule caught were already being refused for the right reason. An
# unobservable guard is decoration, so it is gone and this comment is what
# remains of it.

Split = collections.namedtuple("Split", "threshold between within separates")

#: How far apart two clusters' means must be, in units of their pooled spread,
#: before this module will call them two classes. Two is the smallest value at
#: which a rendering that plainly draws rings and discs separates while one whose
#: markers are three pixels across does not - which is the only calibration
#: available for it, and it is written here rather than inside `_split` so it can
#: be argued about.
SEPARATION = 2.0

#: How far from the boundary a single mark must sit, as a fraction of the
#: distance between the two clusters' means, before its class is called
#: established. The panel's split can hold while ONE mark sits on the line:
#: at an 11 px marker one circle's third harmonic (0.0956) is above the lowest
#: triangle's (0.0911), and without this it was routed to the wrong series - a
#: plausible number under the wrong heading, which is the one outcome worse than
#: a missing one. The split is the panel's question; this is each mark's.
MARK_MARGIN = 0.15

#: The opening kernel `marker_blobs` last used, so `_at_blob` can dilate a blob
#: back by exactly it. A module-level cell rather than a parameter threaded
#: through two call sites for one integer.
KOPEN = [3]


def _split(values):
    """Two clusters or one, by 1-D two-means and a separation index.

    THE LARGEST GAP WAS THE WRONG STATISTIC and the fixture said so twice. Take
    `between > within` and eleven marks at a 3 px marker produce a spurious gap
    that beats every gap inside both clusters - this module then reported a fill
    split on the rendering the gallery had just measured as having none. Take
    `between > 2 * within` and the interior-ink distribution of a panel that
    plainly draws rings and discs stops separating too, because ONE gap inside a
    cluster is a bad estimate of that cluster's spread.

    So: two-means on the sorted values, and the index is the distance between
    the two means over their pooled spread - the same shape as any two-sample
    statistic, and scale-free, so it says the same thing at every rendering. A
    cluster of fewer than a quarter of the marks is an outlier and not a class.
    """
    xs = np.array(sorted(float(v) for v in values), dtype=float)
    if len(xs) < 4:
        return Split(None, 0.0, 0.0, False)
    best = None
    for cut in range(1, len(xs)):
        lo, hi = xs[:cut], xs[cut:]
        if min(len(lo), len(hi)) < max(2, len(xs) // 4):
            continue
        spread = lo.std() + hi.std()
        index = (hi.mean() - lo.mean()) / spread if spread > 1e-9 else float("inf")
        if best is None or index > best[0]:
            best = (index, (lo[-1] + hi[0]) / 2.0, hi.mean() - lo.mean(), spread)
    if best is None:
        return Split(None, 0.0, 0.0, False)
    index, threshold, between, within = best
    return Split(round(float(threshold), 4), round(float(between), 4),
                 round(float(within), 4), bool(index >= SEPARATION))


def _clear(value, split):
    """Is this mark far enough from the boundary to be called?"""
    if split.threshold is None or not split.between:
        return True
    return abs(float(value) - split.threshold) >= MARK_MARGIN * abs(split.between)


def _components(mask):
    n, labels, stats, cents = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        out.append(dict(label=i, x=int(x), y=int(y), w=int(w), h=int(h),
                        area=int(area), cx=float(cents[i][0]),
                        cy=float(cents[i][1])))
    return out, labels


def marker_scale(components):
    """The panel's own marker size: the median side of its near-square parts.

    Measured, because a marker at 600 dpi is three times the marker at 200 and
    neither is a property of the figure.
    """
    sides = [max(c["w"], c["h"]) for c in components
             if c["w"] and c["h"]
             and 1.0 / ASPECT <= float(c["w"]) / c["h"] <= ASPECT]
    if not sides:
        return 0.0
    return float(np.median(sides))


def fill_holes(mask):
    """`mask` with every enclosed white region filled in.

    A CLOSING WAS THE WRONG TOOL and the fixture said so. A ring's stroke is as
    thin as the regression line, so a closing wide enough to fill the ring is
    also wide enough to merge two markers - and one narrow enough to keep them
    apart leaves the ring hollow. At a 33 px marker with a 4 px stroke the
    interior is 25 px across and a 13 px kernel filled none of it: ten of thirty
    markers vanished in the opening that followed.

    Filling HOLES has no width at all. Flood the complement from the border;
    what the flood cannot reach is enclosed, whatever its size, and nothing that
    was not already touching becomes touching. A ring the regression line cuts
    across is still enclosed - by the ring and the line together - so it fills
    too.
    """
    m = mask.astype(np.uint8)
    h, w = m.shape
    flood = np.zeros((h + 2, w + 2), np.uint8)
    flood[1:-1, 1:-1] = m
    cv2.floodFill(flood, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 2,
                  flags=cv2.FLOODFILL_FIXED_RANGE)
    outside = flood[1:-1, 1:-1] == 2
    return np.logical_or(m > 0, ~outside & (m == 0)).astype(np.uint8)


def marker_blobs(mask, scale):
    """The markers, with the lines that join them taken away.

    THREE STEPS AND ONE UNIT, all of them fractions of the panel's own marker.

      close   with a kernel wider than a ring's stroke, so an OPEN marker
              becomes a disc. Without it a ring is exactly as thin as the
              regression line and no thickness test can tell them apart.
      open    with a kernel between the line's stroke and the marker's width.
              This is what removes the lines: `twin_scatter_s3.jpeg` draws four
              regression lines through thirty markers, and without an opening
              every marker it touches is one component with it. Routing by
              component found nine marks in thirty; treating a marker's window
              as clipped found none at all, because the line always leaves the
              window.
      label   what is left is one component per marker - except where two
              markers touch each other, which stays one component and is
              refused as such rather than split by a centroid at neither.

    Returns the opened components and the CLOSED mask, because the shape
    evidence has to come from the closed one: an ellipse-kernel opening rounds a
    triangle's corners, which is the one thing the shape test needs.
    """
    closed = fill_holes(mask)
    k = max(3, int(round(scale * 0.22)) * 2 + 1)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    KOPEN[0] = k
    n, labels, stats, cents = cv2.connectedComponentsWithStats(opened, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        out.append(dict(label=i, x=int(x), y=int(y), w=int(w), h=int(h),
                        area=int(area), cx=float(cents[i][0]),
                        cy=float(cents[i][1])))
    return out, closed, opened, labels


def radial_third_harmonic(filled, cx, cy, scale, rays=72):
    """How three-cornered this mark's outline is, ignoring what crosses it.

    THE FOURTH DISCRIMINANT, and the first that works. The three before it all
    failed on the same thing: a regression line crosses the marker, and every
    measurement taken on the marker's OUTLINE (circularity, vertex count) or on
    a line-free approximation of it (the opened blob's bbox extent) is either
    ruined by the line's stubs or by the opening that removed them.

    A radial profile is not taken on the outline. Walk out from the centre along
    `rays` directions and record where the ink stops; a disc gives a constant
    radius, a triangle gives one with three lobes. The line contributes at the
    TWO angles where it leaves, and a spike at two angles spreads its energy
    evenly over every harmonic - while a triangle puts its energy specifically
    at order three. So the magnitude of the third harmonic over the mean
    separates them and the line does not get a say:

        s3   circles up to 0.087, triangles from 0.091
        s2   circles up to 0.080, triangles from 0.091
        s1   circles up to 0.096, triangles from 0.091   <- one circle crosses

    The overlap at 11 px is real and is why this is still fed through the
    panel's own two-means split rather than compared with a number: one mark on
    the wrong side of a threshold is what a split with a separation index
    survives and a constant does not.
    """
    radii = []
    for k in range(rays):
        theta = 2.0 * math.pi * k / rays
        dx, dy = math.cos(theta), math.sin(theta)
        last = 0.0
        step = 0.5
        while step < 0.85 * scale:
            x, y = int(round(cx + step * dx)), int(round(cy + step * dy))
            if 0 <= y < filled.shape[0] and 0 <= x < filled.shape[1] \
                    and filled[y, x]:
                last = step
                step += 0.5
            else:
                break
        radii.append(last)
    arr = np.array(radii, dtype=float)
    middle = float(np.median(arr[arr > 0])) if (arr > 0).any() else 0.0
    if middle <= 0:
        return None
    spectrum = np.fft.rfft(arr / middle)
    if len(spectrum) <= 3 or abs(spectrum[0]) < 1e-9:
        return None
    return float(abs(spectrum[3]) / abs(spectrum[0]))


def _at_blob(blob, closed, grey, scale, own=None, kopen=3, raw=None):
    """The evidence one opened component carries about its class."""
    pad = max(2, int(round(scale * 0.25)))
    y0 = max(0, blob["y"] - pad)
    y1 = min(closed.shape[0], blob["y"] + blob["h"] + pad)
    x0 = max(0, blob["x"] - pad)
    x1 = min(closed.shape[1], blob["x"] + blob["w"] + pad)
    cx = int(round(blob["cx"]))
    cy = int(round(blob["cy"]))
    # THE SHAPE COMES FROM THE CLOSED MASK, cut to this marker's own box. The
    # opening that removed the lines also rounds a triangle, and the corner
    # count is the evidence that separates the two shapes.
    # THIS MARKER'S OWN INK, and not the run of ink it sits in. The filled mask
    # still holds every regression line, so the component at this centre is the
    # whole chain: measuring a triangle's corners on that returned the corners
    # of the chain, and nothing separated. The opened blob says where this
    # marker is; dilating it back by the opening's own kernel recovers the ink
    # the opening shaved off, corners included, and nothing else.
    grown = cv2.dilate((own == blob["label"]).astype(np.uint8)[y0:y1, x0:x1],
                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kopen, kopen)))
    piece = np.logical_and(closed[y0:y1, x0:x1] > 0, grown > 0).astype(np.uint8)
    if not piece.any():
        return None
    contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    filled = cv2.contourArea(contour)
    inner = max(1, int(round(scale * INTERIOR)))
    # MEASURED ON THIS MARKER'S OWN INK, not on the page. Read off the greyscale
    # it included whatever a TOUCHING neighbour had put inside this marker's
    # middle: on the overlap rendering an open circle came back at 0.825 against
    # a 0.606 boundary and was routed as filled. `piece` is this blob's ink and
    # nothing else's, so a neighbour cannot fill a ring any more.
    # ON THE RAW MASK. Cutting it to THIS blob's ink was tried - a touching
    # neighbour puts its own disc inside a ring's middle, and one mark on the
    # overlap rendering was routed as filled because of it - and then reverted:
    # once `MARK_MARGIN` refused marks sitting on the boundary, removing the
    # neighbour's ink changed nothing that any scenario could see. A guard whose
    # removal breaks no test is decoration, and this file would rather carry the
    # measurement than the code. (NOT the hole-filled mask: there every ring's
    # middle is already black and the fill axis collapses to 1.0 for everything.)
    patch = raw[cy - inner:cy + inner + 1, cx - inner:cx + inner + 1]
    side = float(max(blob["w"], blob["h"]))
    short = float(max(1, min(blob["w"], blob["h"])))
    return dict(point_px_x=float(blob["cx"]), point_px_y=float(blob["cy"]),
                box=[int(blob["x"]), int(blob["x"] + blob["w"]),
                     int(blob["y"]), int(blob["y"] + blob["h"])],
                side_px=side, area_px=int(blob["area"]),
                enclosed_px=float(filled),
                circularity=round((4.0 * math.pi * filled / perimeter ** 2)
                                  if perimeter else 0.0, 4),
                corners=int(len(cv2.approxPolyDP(contour, 0.045 * perimeter, True))),
                interior_ink=round(float(patch.mean()) if patch.size else 0.0, 4),
                aspect=round(side / short, 3),
                size_ratio=round(side / scale, 3) if scale else 0.0,
                # THE THIRD DISCRIMINANT TRIED, and the third that does not
                # separate. Measured on the OPENED blob, which has no line in
                # it - and the opening that removed the line also rounded the
                # triangles: circles 0.65-0.78 against triangles 0.55-0.78 on
                # `twin_scatter_s3.jpeg`. Recorded, not used.
                bbox_extent=round(blob["area"] / float(max(1, blob["w"] * blob["h"])), 4),
                third_harmonic=radial_third_harmonic(closed, cx, cy, scale),
                ink_px=int(piece.sum()))


def _geometry(mask, comp, labels, grey, scale):
    """The evidence one component carries about being a marker of some class."""
    sub = (labels[comp["y"]:comp["y"] + comp["h"],
                  comp["x"]:comp["x"] + comp["w"]] == comp["label"])
    contours, _ = cv2.findContours(sub.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    filled = cv2.contourArea(contour)
    circularity = (4.0 * math.pi * filled / (perimeter ** 2)) if perimeter else 0.0
    corners = len(cv2.approxPolyDP(contour, 0.045 * perimeter, True))
    side = max(comp["w"], comp["h"])
    inner = max(1, int(round(side * INTERIOR)))
    cx, cy = int(round(comp["x"] + comp["w"] / 2.0)), int(round(comp["y"] + comp["h"] / 2.0))
    patch = grey[cy - inner:cy + inner + 1, cx - inner:cx + inner + 1]
    interior = float((patch < 128).mean()) if patch.size else 0.0
    return dict(point_px_x=cx + 0.0, point_px_y=cy + 0.0, side_px=side,
                area_px=comp["area"], enclosed_px=float(filled),
                circularity=round(circularity, 4), corners=int(corners),
                interior_ink=round(interior, 4),
                aspect=round(float(max(comp["w"], comp["h"]))
                             / max(1, min(comp["w"], comp["h"])), 3),
                size_ratio=round(side / scale, 3) if scale else 0.0)


def route(image, panel_box, series, threshold=150, exclude_boxes=()):
    """One record per component: a Series_ID, or the reason there is none.

    `series` is the panel's DECLARATION - the (shape, fill) pairs it says it
    contains, as `mark_readers.SeriesSpec`s or as dicts. A class the panel did
    not declare is refused rather than invented.
    """
    declared = {}
    for spec in series:
        shape = getattr(spec, "marker", None) or spec.get("shape")
        fill = getattr(spec, "fill", None) or spec.get("fill")
        name = getattr(spec, "name", None) or spec.get("id")
        declared[(str(shape).upper(), str(fill).upper())] = name
    x0, x1, y0, y1 = (int(v) for v in panel_box)
    grey = np.asarray((image.convert("L") if isinstance(image, Image.Image)
                       else Image.fromarray(image).convert("L"))).astype(int)
    mask = np.zeros(grey.shape, dtype=bool)
    mask[y0:y1, x0:x1] = grey[y0:y1, x0:x1] < int(threshold)
    for bx0, bx1, by0, by1 in exclude_boxes or ():
        mask[int(by0):int(by1), int(bx0):int(bx1)] = False

    comps, _labels = _components(mask)
    scale = marker_scale(comps)
    if not scale:
        # NO SCALE, NO ROUTING. Every window below is a fraction of the panel's
        # own marker, and a panel that shows none has nothing to measure it on.
        return dict(marker_scale_px=0.0, shape_split=Split(None, 0, 0, False)._asdict(),
                    fill_split=Split(None, 0, 0, False)._asdict(), records=[])
    blobs, closed, _opened, own = marker_blobs(mask, scale)
    seen = []
    for blob in blobs:
        geo = _at_blob(blob, closed, grey, scale, own=own, kopen=KOPEN[0],
                       raw=mask)
        if geo is None:
            continue
        geo["refusal"] = ""
        side = geo["side_px"]
        if side < SIZE_LO * scale or geo["aspect"] > ASPECT:
            geo["refusal"] = "NOT_A_MARKER"
        elif side > SIZE_HI * scale:
            # TWO MARKERS THE OPENING COULD NOT SEPARATE, because they touch
            # each other rather than a line. Their centroid is at neither, so
            # the pair is refused and the panel keeps every other mark.
            geo["refusal"] = "MARKER_MERGED"
        seen.append(geo)

    # AND NO MARK IS MEASURED WITH ANOTHER INSIDE ITS WINDOW. Pairwise, before
    # either split is asked for: a polluted interior would otherwise join the
    # distribution the fill threshold is derived from.
    kept = [g for g in seen if not g["refusal"]]
    # THE PANEL'S OWN TWO SPLITS. Asked for only where the declaration needs
    # them: a panel of one shape has nothing to separate.
    want_shapes = {s for s, _f in declared}
    want_fills = {f for _s, f in declared}
    # ON THE THIRD HARMONIC of the radial profile, which is the one measurement
    # of these four that a line crossing the marker cannot move. The other three
    # stay on every record: they are what the next attempt would have had to
    # re-measure otherwise.
    shape_split = (_split([g["third_harmonic"] for g in kept
                           if g["third_harmonic"] is not None])
                   if len(want_shapes) > 1 else Split(None, 0.0, 0.0, True))
    fill_split = (_split([g["interior_ink"] for g in kept])
                  if len(want_fills) > 1 else Split(None, 0.0, 0.0, True))

    for geo in kept:
        # CIRCLE is the rounder side of the panel's own circularity split, and
        # a triangle's corner count is checked against it rather than believed
        # on its own: a blurred disc approximates to four or five vertices at
        # small sizes and a triangle to three at every size that resolves.
        if len(want_shapes) == 1:
            shape = sorted(want_shapes)[0]
        elif geo["third_harmonic"] is None or not shape_split.separates:
            shape = ""
            geo["refusal"] = "MARKER_SHAPE_UNRESOLVED"
        elif not _clear(geo["third_harmonic"], shape_split):
            # THE PANEL SEPARATES AND THIS MARK DOES NOT. Refused on its own,
            # which is the difference between a reader that answers about a
            # figure and one that answers about every mark on it.
            shape = ""
            geo["refusal"] = "MARKER_SHAPE_UNRESOLVED"
        else:
            # A TRIANGLE PUTS ITS ENERGY AT ORDER THREE and a disc does not, so
            # the high side of the panel's own split is the triangles.
            shape = ("TRIANGLE" if geo["third_harmonic"] >= shape_split.threshold
                     else "CIRCLE")
        if len(want_fills) == 1:
            fill = sorted(want_fills)[0]
        elif not fill_split.separates or not _clear(geo["interior_ink"],
                                                    fill_split):
            fill = ""
            geo["refusal"] = geo["refusal"] or "MARKER_FILL_UNRESOLVED"
        else:
            fill = ("FILLED" if geo["interior_ink"] >= fill_split.threshold
                    else "OPEN")
        geo["shape"] = shape
        geo["fill"] = fill
        geo["shape_threshold"] = shape_split.threshold
        geo["fill_threshold"] = fill_split.threshold
        if geo["refusal"]:
            geo["Series_ID"] = ""
            geo["Identity_Method"] = ""
            continue
        name = declared.get((shape, fill))
        if name is None:
            geo["refusal"] = "MARKER_CLASS_NOT_DECLARED"
            geo["Series_ID"] = ""
            geo["Identity_Method"] = ""
            continue
        geo["Series_ID"] = name
        geo["Identity_Method"] = "MEASURED_MARKER_SHAPE_FILL"
    for geo in seen:
        geo.setdefault("shape", "")
        geo.setdefault("fill", "")
        geo.setdefault("Series_ID", "")
        geo.setdefault("Identity_Method", "")
    return dict(marker_scale_px=scale, shape_split=shape_split._asdict(),
                fill_split=fill_split._asdict(), records=seen)
