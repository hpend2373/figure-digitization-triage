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
                      the tick spacing, the group anchor x pixels
    never proposed    what a tick is WORTH, what a series MEANS, how many
                      panels the figure has

**The tick values are the whole reason for the split.** A printed 30 read as 3
rescales every value in the panel by ten, leaves the calibration residual at
zero, and makes every number in the file self-consistent and wrong. No
arithmetic can catch it and no classifier should be trusted with it, so this
module reports "eleven ticks, evenly spaced, at these pixel rows" and a person
types what the first and last one say. That is one number per axis per panel
instead of a measurement session.

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
    "Confidence", "Confidence_Reason",
    "Human_Verification_Status", "Verified_By", "Verified_At",
    "Y_Tick_First_Value", "Y_Tick_Last_Value", "Note",
)

PROPOSAL_PENDING = "PENDING"
PROPOSAL_STATUSES = (PROPOSAL_PENDING, "CONFIRMED", "REJECTED")

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
    if not rows or not cols:
        return None
    row_runs = [int(round(sum(r) / len(r))) for r in _runs(rows, gap=2)]
    col_runs = [int(round(sum(c) / len(c))) for c in _runs(cols, gap=2)]
    # An L-shaped axis is one horizontal line and one vertical one, which is
    # what SPSS prints and what publication BF02919461's right-hand panel is.
    # The missing edges are the region's own bounds - which is where a person
    # would put them too, because there is nothing else printed to put them at.
    y0 = min(row_runs) if len(row_runs) > 1 else min(row_runs + [ry0])
    y1 = max(row_runs) if len(row_runs) > 1 else max(row_runs + [ry0])
    x0 = min(col_runs) if len(col_runs) > 1 else min(col_runs + [rx1 - 1])
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
        "Confidence": "%.2f" % score, "Confidence_Reason": why,
        # The only status this module may write.
        "Human_Verification_Status": PROPOSAL_PENDING,
    })
    return row


def proposal_problems(rows):
    """[(Proposal_ID, code, detail)] for a proposal that cannot be what it says.

    Checked when a proposal is READ, because the file goes to a person and
    comes back edited. What a person may change is the status, the two tick
    values, the note and their own name. What nobody may do is confirm a
    geometry without saying who they are, or leave a machine's `PENDING` beside
    the two numbers only a person can supply.
    """
    out, seen = [], set()
    for row in rows:
        pid = _s(row.get("Proposal_ID"))
        if not pid:
            out.append(("", "PROPOSAL_ID_MISSING", "a row with no Proposal_ID"))
            continue
        if pid in seen:
            out.append((pid, "PROPOSAL_ID_DUPLICATE", pid))
        seen.add(pid)
        status = _s(row.get("Human_Verification_Status")).upper()
        if status not in PROPOSAL_STATUSES:
            out.append((pid, "PROPOSAL_STATUS_UNKNOWN",
                        "%r is not %s" % (status, "/".join(PROPOSAL_STATUSES))))
            continue
        who = _s(row.get("Verified_By"))
        when = _s(row.get("Verified_At"))
        first = _s(row.get("Y_Tick_First_Value"))
        last = _s(row.get("Y_Tick_Last_Value"))
        if status == PROPOSAL_PENDING:
            if who or when:
                out.append((pid, "PROPOSAL_PENDING_WITH_A_VERIFIER",
                            "%s is still PENDING and names %s"
                            % (pid, who or when)))
            if first or last:
                out.append((pid, "PROPOSAL_PENDING_WITH_A_TICK_VALUE",
                            "%s carries a tick value and nobody has read the "
                            "axis" % pid))
            continue
        if not who or not when:
            out.append((pid, "PROPOSAL_VERDICT_UNATTRIBUTED",
                        "%s says %s and does not say who or when"
                        % (pid, status)))
        if status != "CONFIRMED":
            continue
        # The two numbers the whole split exists for.
        for label, value in (("Y_Tick_First_Value", first),
                             ("Y_Tick_Last_Value", last)):
            try:
                float(value)
            except ValueError:
                out.append((pid, "PROPOSAL_TICK_VALUE_MISSING",
                            "%s is CONFIRMED with %s=%r; what the axis says is "
                            "the one thing a raster cannot be asked"
                            % (pid, label, value)))
        if first and last and first == last:
            out.append((pid, "PROPOSAL_TICK_VALUES_EQUAL",
                        "%s says the first and last tick are both %s, which is "
                        "not an axis" % (pid, first)))
    return out


def calibration_from(row):
    """[[value, pixel], [value, pixel]] for a CONFIRMED proposal, or None.

    The join between the two halves: the pixels this module measured and the
    values a person read, put together only once both exist. Returns the FIRST
    and LAST tick, which on a regular ladder pins every one between them.
    """
    if _s(row.get("Human_Verification_Status")).upper() != "CONFIRMED":
        return None
    marks = [float(m) for m in _s(row.get("Y_Tick_Pixels")).split(";") if m]
    try:
        first = float(_s(row.get("Y_Tick_First_Value")))
        last = float(_s(row.get("Y_Tick_Last_Value")))
    except ValueError:
        return None
    if len(marks) < 2:
        return None
    return [[first, marks[0]], [last, marks[-1]]]


def write_proposals(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(PROPOSAL_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in PROPOSAL_COLUMNS})
    return path


def proposal_overlay(image, row, out_path):
    """The proposal drawn on the raster it was measured from.

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
    for mark in _s(row.get("Y_Tick_Pixels")).split(";"):
        if not mark:
            continue
        y = int(float(mark))
        draw.line((x0 - 18, y, x0 + 10, y), fill=(30, 90, 200), width=1)
    for anchor in _s(row.get("Group_Anchor_Pixels")).split(";"):
        if not anchor:
            continue
        x = int(float(anchor))
        draw.line((x, y0, x, y1), fill=(20, 150, 90), width=1)
    region = [int(v) for v in _s(row.get("Region")).split(",")] \
        if _s(row.get("Region")) else None
    if region:
        pad = 12
        canvas = canvas.crop((max(0, region[0] - pad), max(0, region[1] - pad),
                              min(canvas.width, region[2] + pad),
                              min(canvas.height, region[3] + pad)))
    canvas.save(out_path)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("raster")
    ap.add_argument("--out", required=True)
    ap.add_argument("--region", action="append", default=[],
                    metavar="X0,Y0,X1,Y1",
                    help="where to look for a panel; repeatable. Without any, "
                         "the whole raster is one region")
    ap.add_argument("--threshold", type=int, default=160)
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
        if row["Confidence_Reason"]:
            print("    %s" % row["Confidence_Reason"])
    path = write_proposals(os.path.join(args.out, "geometry_proposal.csv"), rows)
    print("wrote %s" % path)
    print("%d proposal(s), all PENDING. Open each overlay, check the frame and "
          "the tick ladder, then type Y_Tick_First_Value and Y_Tick_Last_Value "
          "- what the axis SAYS is the one thing this cannot measure."
          % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
