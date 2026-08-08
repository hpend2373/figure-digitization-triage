"""What a monochrome bar chart actually looks like, measured rather than assumed.

    python3 measure_mono_bars.py                  # print the table
    python3 measure_mono_bars.py --json OUT.json  # and write it

`_FILL_BANDS` and `_INSIDE_MIN_DENSITY` in `mark_readers.py` carry a comment
saying they were "measured on a real monochrome figure". They were - on ONE.
Publication 127 is the second, and it disagrees with every one of them: its
solid fill reads 0.70 against a band that starts at 0.72, its stipple rows read
0.10 against a floor of 0.15, and its open bar's right stroke does not fall in
the last two columns of the slot the reader gave it.

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


def stroke_scale(gray, box, threshold=128, span_fraction=0.5):
    """Line weight in pixels, from the longest horizontal rule in the panel."""
    x0, x1, y0, y1 = map(int, box)
    strip = gray[y0:y1, x0:x1] < threshold
    if not strip.size:
        return StrokeScale(reason="the panel box selects no pixels")
    wide = np.where(strip.sum(axis=1) > span_fraction * strip.shape[1])[0]
    if not len(wide):
        return StrokeScale(
            reason="no horizontal rule spans %.0f%% of the panel width"
                   % (100 * span_fraction))
    thickest = max(len(g) for g in _runs(list(wide)))
    return StrokeScale(value_px=int(thickest), status="MEASURED")


def seed_support(gray, box, zero_row, stroke, window, threshold=128,
                 direction="UP"):
    """Columns of `window` whose ink reaches the baseline, as x-runs.

    Ink that does not touch the baseline is an error bar, a significance glyph
    or the neighbouring bar, and none of them is part of this bar. The band
    starts one stroke clear of the baseline rule, because the rule itself is
    dark across every column and would make an open bar's footprint the whole
    slot.
    """
    x0, x1, y0, y1 = map(int, box)
    xa, xb = window
    dark = gray[y0:y1, xa:xb] < threshold
    depth = SEED_DEPTH_STROKES * stroke
    if direction == "UP":
        top, bottom = max(0, zero_row - stroke - depth), max(1, zero_row - stroke)
    else:
        top, bottom = min(dark.shape[0] - 1, zero_row + stroke), \
            min(dark.shape[0], zero_row + stroke + depth)
    band = dark[top:bottom]
    if band.shape[0] < 2:
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

    Returns (edge_row, method, contradiction) where `contradiction` is the
    distance beyond the edge at which supported ink still exists - the check
    that stops a walk which stopped too early from being reported as a short
    bar.
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


#: What an inked structure beyond the bar end turns out to be. The distinction
#: matters because only the first of these means the walk was wrong.
REMOTE_KINDS = ("BODY_CONTINUATION", "ERRORBAR_CAP", "ANNOTATION_OR_GLYPH",
                "UNRESOLVED_REMOTE_SUPPORT")


def remote_support(gray, box, window, footprint, edge_row, zero_row, stroke,
                   direction="UP", threshold=128):
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
                              several strokes. The walk stopped too early and
                              this bar has no value.
      ERRORBAR_CAP            a thin horizontal rule that misses the side
                              tracks and hangs off a central stem. Expected,
                              and where the dispersion comes from.
      ANNOTATION_OR_GLYPH     touches neither the tracks nor a stem: an
                              asterisk, a bracket, a significance marker.
      UNRESOLVED_REMOTE_SUPPORT   none of the above cleanly. Fail closed.
    """
    x0, x1, y0, y1 = map(int, box)
    xa = window[0]
    fx0, fx1 = footprint
    bar_w = fx1 - fx0 + 1
    dark = gray[y0:y1, xa + fx0:xa + fx1 + 1] < threshold
    height = dark.shape[0]
    track = max(1, min(stroke, int(round(0.06 * bar_w))))
    step = -1 if direction == "UP" else 1
    centre = slice(max(0, bar_w // 2 - max(1, bar_w // 10)),
                   min(bar_w, bar_w // 2 + max(1, bar_w // 10) + 1))

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
    edge = int(round(edge_row))
    limit = 0 if step < 0 else height - 1
    scan = range(edge + step * max(1, stroke), limit + step, step)
    scan = [r for r in scan if 0 <= r < height]
    if not scan:
        return []
    stem_rows = []
    for r in scan:
        if not dark[r, centre].any():
            break
        stem_rows.append(r)
    cap_rows, cap_span = [], 0.0
    if stem_rows:
        tip = stem_rows[-1]
        for r in [x for x in range(tip - 2 * stroke, tip + 2 * stroke + 1)
                  if 0 <= x < height and abs(x - edge) > stroke]:
            occupied = np.where(dark[r])[0]
            if not len(occupied):
                continue
            span = (occupied[-1] - occupied[0] + 1) / float(bar_w)
            if span >= 0.30 and not (dark[r, :track].any() and dark[r, -track:].any()):
                cap_rows.append(r)
                cap_span = max(cap_span, span)
    masked = dark.copy()
    for r in stem_rows:
        masked[r, centre] = False
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
                        central_stem_fraction=1.0,
                        centre_row=int(round(float(np.mean(cap_rows))))))
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
        # is to run down to the bar end through ink of your own.
        gap = [r for r in range(edge, comp[0], step) if 0 <= r < height]
        joined = (float(np.mean([bool(masked[r].any()) for r in gap]))
                  if gap else 1.0)
        thick = extent >= 2 * stroke
        if (both_tracks >= 0.5 or (span >= 0.55 and bins >= 3 and thick)) and joined >= 0.5:
            kind = "BODY_CONTINUATION"
        elif joined < 0.5:
            kind = "ANNOTATION_OR_GLYPH"
        else:
            kind = "UNRESOLVED_REMOTE_SUPPORT"
        out.append(dict(kind=kind, distance_px=int(abs(comp[0] - edge)),
                        extent_px=int(extent), side_track_fraction=round(both_tracks, 3),
                        span_fraction=round(float(span), 3), occupied_bins=int(bins),
                        central_stem_fraction=round(joined, 3),
                        centre_row=int(round(float(np.mean(comp))))))
    return out


def texture(gray, box, window, footprint, edge_row, zero_row, stroke,
            direction="UP"):
    """Everything about the ink inside one bar, at four thresholds and none.

    The interior is the middle of the bar in both axes, as a FRACTION of the
    bar: the old reader sampled a fixed 40 px starting 6 px in, which is most of
    a 55 px bar and a quarter of a 188 px one.
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
    if height < 4 or cb - ca < 3:
        return None
    keep_top = top + max(2 * stroke, int(round(0.12 * height)))
    keep_bottom = bottom - max(2 * stroke, int(round(0.10 * height)))
    if keep_bottom - keep_top < 3:
        keep_top, keep_bottom = top, bottom
    roi = gray[keep_top:keep_bottom, ca:cb]
    if roi.size == 0:
        return None
    out = dict(bar_width=int(bar_w), bar_height=int(height),
               roi_shape=[int(roi.shape[0]), int(roi.shape[1])],
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
    """One record per declared bar of one panel."""
    gray = _gray(spec["path"])
    box = spec["box"]
    scale = stroke_scale(gray, box)
    cal = MR.AxisCalibration.from_points([tuple(t) for t in spec["ticks"]])
    x0, x1, y0, y1 = map(int, box)
    zero = int(round(cal.value_to_pixel(spec.get("baseline", 0.0)))) - y0
    fills = spec["fills"]
    records = []
    if not scale.ok:
        return [dict(figure=spec["tag"], group=None, stroke=scale.as_dict(),
                     error="STROKE_SCALE_UNRESOLVED")]
    stroke = scale.value_px
    for label, gx in spec["anchors"].items():
        gw = spec["group_window"]
        window = (max(x0, int(gx) - gw), min(x1, int(gx) + gw + 1))
        # Direction is measured, not declared: whichever side of the baseline
        # carries seed support is the side the bars are on.
        support = {}
        for candidate in ("UP", "DOWN"):
            segs, _pers = seed_support(gray, box, zero, stroke, window,
                                       direction=candidate)
            support[candidate] = (sum(len(g) for g in segs), segs)
        (up_total, up_segs), (down_total, down_segs) = support["UP"], support["DOWN"]
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
        prints, bounds = footprints_from_seed(segments, len(fills))
        for k, fp in enumerate(prints):
            rec = dict(figure=spec["tag"], group=label, slot=k,
                       declared=fills[k], stroke_px=stroke, direction=direction)
            if fp is None:
                rec["error"] = "NO_SEED_SUPPORT"
                records.append(rec)
                continue
            # The bar end, measured crudely and only so the interior can be
            # sampled: this script does not implement the reader's walk.
            edge, method = trace_extent(
                gray, box, window, fp, zero, stroke, direction=direction)
            remote = remote_support(gray, box, window, fp, edge, zero, stroke,
                                    direction=direction)
            body = [r for r in remote if r["kind"] == "BODY_CONTINUATION"]
            caps = [r for r in remote if r["kind"] == "ERRORBAR_CAP"]
            rec.update(slot_bounds=(list(bounds[k]) if bounds[k] else None),
                       edge_row=round(edge, 1), support=method,
                       remote=remote,
                       # Only a body continuation says the walk was wrong.
                       contradiction_px=(min(r["distance_px"] for r in body)
                                         if body else 0),
                       cap_px=(caps[0]["centre_row"] if caps else None),
                       value=round(cal.pixel_to_value(y0 + edge), 3),
                       footprint=[int(fp[0]), int(fp[1])],
                       footprint_width=int(fp[1] - fp[0] + 1),
                       seed_segments=len([s for s in segments
                                          if fp[0] <= s[0] <= fp[1]]))
            tex = texture(gray, box, window, fp, edge, zero, stroke,
                          direction=direction)
            if tex is None:
                rec["error"] = "BAR_TOO_SMALL_TO_SAMPLE"
            else:
                rec.update(tex)
            records.append(rec)
    return records


def builtin_specs():
    """Every real or synthetic monochrome bar panel the package ships."""
    specs = [
        dict(tag="397_fig3_P3_MEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=[118, 480, 90, 470], ticks=[[150.0, 101.0], [50.0, 465.0]],
             anchors={"PRE": 187, "POST": 390}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0),
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
                print("%-20s %-8s %-4s %-9s  %s"
                      % (r["figure"], r.get("group"), r.get("slot"),
                         r.get("declared"), r["error"]))
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
