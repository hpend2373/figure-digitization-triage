# -*- coding: utf-8 -*-
"""One panel, more than one y axis - and every point saying which it was read on.

    axes = [{"Axis_ID": "Y_LEFT", "Panel_ID": "P01", "Dimension": "Y",
             "Side": "LEFT", "Unit": "mmHg/L/min", "Scale": "LINEAR",
             "Calibration_Points": [[10, 450], [35, 60]]}, ...]
    problems = validate_axes(axes)
    cals = calibrations(axes)

WHY THIS EXISTS. `Panel_ID` was doing two jobs. Publication 464 Figure 2 draws
total peripheral resistance up the left at 10-35 and a splanchnic index up the
right at 20-90 over ONE panel and ONE x axis, and the proposer reads one ladder
on it: the panel count said 1, the declared axis count said 1, and the axes read
as accounted for. Nothing in this package could express the second scale, so
either the figure becomes two pretend panels or one axis is lost - and both of
those are a wrong number rather than a missing one.

    A series names its own axis. That is the whole change.

WHAT A WRONG AXIS COSTS, measured on `twin_scatter_s3.jpeg`, whose two
calibrations differ by 2.80: read the right-hand series against the left-hand
calibration and every value comes back on a scale nothing in the figure uses.
`test_axis_grain.py` pins that number, because "the axes are different" is the
claim the grain rests on and it should be a measurement.

## And the points carry their own hash

`mark_readers.write_point_data` already persists the cloud an association was
computed from, and re-derives every value from its own pixel at write time. What
it does not do is let a single point be pinned: an association row cites a FILE,
so a point silently moved inside that file leaves the row's own r unchanged and
nothing disagrees with anything.

So every point gets `Point_Record_SHA256` over its pixel, its axis, the
calibration it was read under, WHOSE it is and how that was decided, and an
association carries `Point_Set_SHA256` over the sorted list of them. Then a
moved pixel breaks its own point's hash, a dropped point breaks the set hash,
and a recalibrated axis breaks every point on THAT axis and none on the other -
which is the property a twin-axis figure needs most, because half its points are
read under each.

    Point_Record_SHA256      pixel + Series_ID + Identity_Method + Axis_ID +
                             Panel_ID + Image_SHA256 + both axis records +
                             both calibrations + Routing_Evidence_SHA256
    Axis_Record_SHA256       the manifest row: side, unit, scale, panel, ticks
    Routing_Evidence_SHA256  the ten measurements a shape-and-fill routing
                             decided on, margins included

WHAT THE FIRST VERSION MISSED. It covered the pixel and the calibration, and
nothing else - so `Series_ID` could be swapped between two points read on the
same axis and both hashes still verified. Two clouds exchange a member each,
every value still re-derives from its own pixel, and no check anywhere
disagrees. `test_axis_grain.py` performs that swap.

## One axis AND one series

`association_over_points` refused two axes from the start, because two scales in
one cloud are not measurements of one quantity. It did NOT refuse two series,
and that is the more common mistake: an r over the open circles and the filled
circles together is computable, reads plausibly, and is about neither group. It
is now refused unless the caller declares the pooling in
`Aggregation_Method` / `Aggregation_Series_IDs` / `Aggregation_Justification`.
"""
import hashlib
import json

AXIS_COLUMNS = ("Axis_ID", "Panel_ID", "Dimension", "Side", "Unit", "Scale",
                "Calibration_Points")
DIMENSIONS = ("X", "Y")
SIDES = {"X": ("BOTTOM", "TOP"), "Y": ("LEFT", "RIGHT")}
SCALES = ("LINEAR", "LOG10")

#: What a series row must say, and the refusal when it does not.
SERIES_AXIS_COLUMN = "Axis_ID"
UNKNOWN_AXIS = "SERIES_AXIS_NOT_DECLARED"
FOREIGN_AXIS = "SERIES_AXIS_NOT_IN_MANIFEST"
#: AND WHAT IT MUST BE. A series naming an axis that exists is not enough: the
#: manifest holds the x axis too, and a series pointed at it validated cleanly
#: while every y value came off the horizontal scale. The same for a panel - one
#: figure's Y_LEFT is another figure's Y_LEFT.
WRONG_DIMENSION = "SERIES_AXIS_WRONG_DIMENSION"
WRONG_PANEL = "SERIES_AXIS_WRONG_PANEL"
X_WRONG_DIMENSION = "X_AXIS_WRONG_DIMENSION"
X_WRONG_PANEL = "X_AXIS_WRONG_PANEL"

#: An association over more than one series. Refused unless the caller declares
#: it meant to, in these three columns.
MULTIPLE_SERIES = "ASSOCIATION_SPANS_MULTIPLE_SERIES"
AGGREGATION_COLUMNS = ("Aggregation_Method", "Aggregation_Series_IDs",
                       "Aggregation_Justification")


def _s(value):
    return "" if value is None else str(value).strip()


def validate_axes(rows):
    """Everything wrong with an axis manifest, as sentences.

    The rule that matters is the LAST one: two axes of the same dimension on one
    panel must be on different sides. A figure prints the left scale on the left
    and the right scale on the right, and a manifest that does not distinguish
    them has recorded two calibrations nobody can tell apart - which is a worse
    state than one calibration, because the reader will pick.
    """
    out = []
    seen = {}
    for i, row in enumerate(rows):
        where = "axes[%d]" % i
        missing = [c for c in AXIS_COLUMNS if not _s(row.get(c))
                   and c != "Calibration_Points"]
        if missing:
            out.append("%s: no %s" % (where, ", ".join(missing)))
        dim = _s(row.get("Dimension")).upper()
        if dim and dim not in DIMENSIONS:
            out.append("%s: Dimension=%r is not one of %s"
                       % (where, dim, "/".join(DIMENSIONS)))
        side = _s(row.get("Side")).upper()
        if dim in SIDES and side and side not in SIDES[dim]:
            out.append("%s: a %s axis is on %s, not %r"
                       % (where, dim, " or ".join(SIDES[dim]), side))
        scale = _s(row.get("Scale")).upper()
        if scale and scale not in SCALES:
            out.append("%s: Scale=%r is not one of %s"
                       % (where, scale, "/".join(SCALES)))
        points = row.get("Calibration_Points") or []
        if len(points) < 2:
            out.append("%s: %d calibration point(s); a scale needs two"
                       % (where, len(points)))
        else:
            values = [float(p[0]) for p in points]
            pixels = [float(p[1]) for p in points]
            if any(v != v or v in (float("inf"), float("-inf")) for v in values) \
                    or any(x != x or x in (float("inf"), float("-inf"))
                           for x in pixels):
                out.append("%s: a calibration point is not a finite number"
                           % where)
            elif len(set(values)) < 2 or len(set(pixels)) < 2:
                out.append("%s: its calibration points do not span anything"
                           % where)
            elif scale == "LOG10" and any(v <= 0 for v in values):
                # A LOG AXIS CANNOT BE CALIBRATED THROUGH ZERO. Caught here
                # rather than inside the fit, because a manifest is what a
                # person types and this is the sentence they need to read.
                out.append("%s: a LOG10 axis is calibrated at %s; the log of a "
                           "non-positive value is not a number"
                           % (where, min(values)))
        key = (_s(row.get("Panel_ID")), dim, side)
        if key in seen:
            # THE ONE THAT MATTERS. Two y axes on one panel, both called LEFT:
            # the manifest holds two scales and nothing says which series is on
            # which, so a reader picks - and picking is how a splanchnic index
            # gets published on a peripheral-resistance scale.
            out.append("%s: %s already declares a %s axis on the %s (%s); two "
                       "scales on one side cannot be told apart"
                       % (where, key[0], dim, side, seen[key]))
        seen[key] = _s(row.get("Axis_ID"))
        if _s(row.get("Axis_ID")) in [_s(r.get("Axis_ID")) for r in rows[:i]]:
            out.append("%s: Axis_ID=%s is used twice"
                       % (where, _s(row.get("Axis_ID"))))
    return out


def calibrations(rows):
    """{Axis_ID: AxisCalibration}, refusing a manifest that does not validate.

    THE SCALE IS PASSED THROUGH, and for one release it was not: every axis was
    fitted LINEAR whatever its manifest said, so a decade axis declared LOG10
    read a straight line through log-spaced ticks and every value between the
    calibration points came back wrong - quietly, with a small residual, because
    two points fit any straight line exactly. `mark_readers.AxisCalibration`
    spells the log scale `LOG`; this module spells it `LOG10` because that is
    what a person writes on a manifest, and the translation lives here.
    """
    import mark_readers as MR
    problems = validate_axes(rows)
    if problems:
        raise ValueError("the axis manifest does not validate: %s"
                         % "; ".join(problems))
    out = {}
    for row in rows:
        pts = [(float(v), float(px)) for v, px in row["Calibration_Points"]]
        scale = "LOG" if _s(row.get("Scale")).upper() == "LOG10" else "LINEAR"
        out[_s(row["Axis_ID"])] = MR.AxisCalibration.from_points(pts, scale=scale)
    return out


def axis_record_sha256(row):
    """The manifest row itself, so a point can cite the axis it was read on.

    The calibration record covers the FIT; this covers what the axis was
    DECLARED to be - its side, its unit, its scale, its panel. Two axes can fit
    the same line and mean different things, and a point that cites only the fit
    cannot tell them apart.
    """
    return hashlib.sha256(json.dumps(
        {"Axis_ID": _s(row.get("Axis_ID")),
         "Panel_ID": _s(row.get("Panel_ID")),
         "Dimension": _s(row.get("Dimension")).upper(),
         "Side": _s(row.get("Side")).upper(),
         "Unit": _s(row.get("Unit")),
         "Scale": _s(row.get("Scale")).upper(),
         "Calibration_Points": [[float(v), float(px)]
                                for v, px in (row.get("Calibration_Points") or ())]},
        sort_keys=True).encode("utf-8")).hexdigest()


def axis_records(rows):
    """{Axis_ID: axis_record_sha256}."""
    return {_s(r.get("Axis_ID")): axis_record_sha256(r) for r in rows}


def series_axis(series_rows, axes, panel_id=None):
    """{Series_ID: Axis_ID}, or a refusal per series that cannot name one.

    EXISTING IS NOT THE SAME AS BEING THE RIGHT AXIS. The manifest holds the x
    axis as well, and a series pointed at it passed every check this function
    used to make while its y values came off the horizontal scale. `panel_id`,
    when given, is the panel these series are on: an axis belonging to another
    panel is a foreign scale with a familiar name.
    """
    by_id = {_s(r.get("Axis_ID")): r for r in axes}
    out, refused = {}, {}
    for row in series_rows:
        sid = _s(row.get("Series_ID")) or _s(row.get("id"))
        axis = _s(row.get(SERIES_AXIS_COLUMN))
        if not axis:
            refused[sid] = UNKNOWN_AXIS
        elif axis not in by_id:
            refused[sid] = FOREIGN_AXIS
        elif _s(by_id[axis].get("Dimension")).upper() != "Y":
            refused[sid] = WRONG_DIMENSION
        elif panel_id is not None \
                and _s(by_id[axis].get("Panel_ID")) != _s(panel_id):
            refused[sid] = WRONG_PANEL
        else:
            out[sid] = axis
    return out, refused


def _x_axis(axes, x_axis_id, panel_id=None):
    """The x axis by ID, refusing one that is not an x axis or not this panel's."""
    by_id = {_s(r.get("Axis_ID")): r for r in axes}
    row = by_id.get(_s(x_axis_id))
    if row is None:
        raise ValueError("%s: %r is not in this manifest"
                         % (FOREIGN_AXIS, x_axis_id))
    if _s(row.get("Dimension")).upper() != "X":
        raise ValueError("%s: %s is a %s axis; the points' x values cannot be "
                         "read on it" % (X_WRONG_DIMENSION, x_axis_id,
                                         _s(row.get("Dimension")).upper()))
    if panel_id is not None and _s(row.get("Panel_ID")) != _s(panel_id):
        raise ValueError("%s: %s belongs to panel %s, not %s"
                         % (X_WRONG_PANEL, x_axis_id, _s(row.get("Panel_ID")),
                            _s(panel_id)))
    return row


def _calibration_record(cal):
    import mark_readers as MR
    return MR._calibration_record(cal)


#: What `marker_routing` decided about a mark, and how close the decision was.
#: A point whose value re-derives from its pixel is not thereby a point of the
#: series it is filed under: the series came from a shape and a fill measured
#: against two thresholds, and none of that was in the hash.
#:
#: AND THE FIRST EIGHT ARE ABOUT WHETHER THIS BLOB WAS ONE MARKER AT ALL. They
#: were missing, and their absence left the most important verdict of the whole
#: reader outside the hash: `off_centre_ink > OFF_CENTRE` is what refuses a blob
#: holding two markers, and a producer could clear the refusal, write a
#: Series_ID, re-stamp every hash, and nothing downstream measured the number
#: that made the blob invalid. `verify_points` now re-derives the verdict from
#: these rather than believing `Marker_Validity_Status`.
#: AND THE LAST ELEVEN ARE THE GROUP THE FILL WAS DECIDED IN. `Fill_Split` is
#: the PANEL'S threshold and it is no longer what named this mark: since v9.16
#: the fill question is asked inside the mark's own measured shape, because the
#: interior-ink window of a hollow triangle is not a hollow circle's and a
#: panel-wide split pools two distributions into one. A row carrying only the
#: panel's threshold could not be checked against the verdict it was given -
#: the margin would be measured from the wrong line - so the group's own
#: threshold, spread, counts, floor and this mark's margin from it all travel,
#: and `Fill_Conditioning_Shape` says which group asked.
ROUTING_EVIDENCE = ("Marker_Scale_Px", "Side_Px", "Aspect", "Size_Ratio",
                    "Off_Centre_Ink", "Off_Centre_Threshold",
                    "Off_Centre_Margin", "Marker_Validity_Status",
                    "Marker_Shape", "Marker_Fill", "Third_Harmonic",
                    "Interior_Ink", "Shape_Split", "Fill_Split", "Shape_Margin",
                    "Fill_Margin", "Component_ID", "Foreign_Ink_Fraction",
                    "Fill_Conditioning_Shape", "Fill_Group_N",
                    "Fill_Group_Low_N", "Fill_Group_High_N",
                    "Fill_Group_Threshold", "Fill_Group_Between",
                    "Fill_Group_Within", "Fill_Group_Separation_Index",
                    "Fill_Group_Minimum_Allowed", "Fill_Group_Separates",
                    "Fill_Group_Margin")

#: Where each of those lives on a `marker_routing.route` record.
_EVIDENCE_FROM = {"Marker_Scale_Px": "marker_scale_px", "Side_Px": "side_px",
                  "Aspect": "aspect", "Size_Ratio": "size_ratio",
                  "Off_Centre_Ink": "off_centre_ink",
                  "Off_Centre_Threshold": "off_centre_threshold",
                  "Off_Centre_Margin": "off_centre_margin",
                  "Marker_Validity_Status": "Marker_Validity_Status",
                  "Marker_Shape": "shape", "Marker_Fill": "fill",
                  "Third_Harmonic": "third_harmonic",
                  "Interior_Ink": "interior_ink",
                  "Shape_Split": "shape_threshold",
                  "Fill_Split": "fill_threshold",
                  "Component_ID": "Original_Component_ID",
                  "Foreign_Ink_Fraction": "Foreign_Ink_Fraction"}
#: THE GROUP FIELDS CARRY THEIR OWN NAMES on the record, so the mapping is the
#: identity - written out rather than special-cased, because `evidence_record`
#: reads `_EVIDENCE_FROM` to put a CSV row back under the reader's names and a
#: column missing from this dict comes back as None on every row. That was the
#: fail-open `scatter_points.evidence_record` exists to have fixed once.
for _column in ("Fill_Conditioning_Shape", "Fill_Group_N", "Fill_Group_Low_N",
                "Fill_Group_High_N", "Fill_Group_Threshold",
                "Fill_Group_Between", "Fill_Group_Within",
                "Fill_Group_Separation_Index", "Fill_Group_Minimum_Allowed",
                "Fill_Group_Separates", "Fill_Group_Margin"):
    _EVIDENCE_FROM[_column] = _column
del _column

#: A point's SERIES does not follow from the marker evidence beside it.
#:
#: THE HOLE THIS CLOSES. Every other check on a routed point asks whether the
#: point is consistent WITH ITSELF: the pixel gives the value under the axis it
#: cites, the hashes cover what they carry, the marker evidence hashes to its own
#: digest, the fill agrees with its own group's threshold. None of them asked the
#: one question the whole reader exists to answer - does this MARKER mean this
#: SERIES? So two points on the SAME axis could have their `Series_ID` swapped,
#: every hash re-derived, the association recomputed over the file just made, and
#: nothing disagreed: both rows had a real marker's evidence, both re-derived
#: their value, and the numbers were published under each other's headings. On a
#: twin-axis panel that is the cheapest wrong answer there is, because the two
#: series share a calibration and the values stay in range.
ROUTE_NOT_DERIVED = "SERIES_DOES_NOT_FOLLOW_FROM_MARKER_EVIDENCE"


def declared_markers(series_rows, panel_id=None):
    """({(SHAPE, FILL): Series_ID}, {SHAPE: fills}) for one panel, or (None, None).

    `(None, None)` when NO row of the manifest declares a marker shape: such a
    panel was never read by the routed reader, so there is nothing to hold a
    point's route to and saying so is not the same as passing it.
    """
    rows = [r for r in series_rows
            if panel_id is None or _s(r.get("Panel_ID")) in ("", _s(panel_id))]
    declared, fills_of = {}, {}
    for r in rows:
        shape = _s(r.get("Marker_Shape")).upper()
        fill = _s(r.get("Marker_Fill")).upper()
        # `ANY` IS THE MANIFEST'S WAY OF SAYING "NOT THIS". A colour panel
        # declares `Marker_Shape=CIRCLE, Marker_Fill=ANY` because its series are
        # told apart by a hex value and the marker is furniture; reading that as
        # a marker declaration would hold a colour-routed point to a marker route
        # nobody claimed.
        if not shape or not fill or "ANY" in (shape, fill):
            continue
        declared[(shape, fill)] = _s(r.get("Series_ID"))
        fills_of.setdefault(shape, set()).add(fill)
    if not declared:
        return None, None
    return declared, fills_of


def expected_route(record, series_rows, panel_id=None):
    """(Series_ID, Identity_Method) this record's OWN evidence supports, or (None, None).

    Derived from the marker evidence on the record and the panel's DECLARATION,
    and from nothing the record says about itself: `Series_ID` and
    `Identity_Method` are exactly the two fields a producer would edit, so they
    are the two this may not read.

        MEASURED_MARKER_SHAPE_FILL   the (shape, fill) pair names one series
        MEASURED_MARKER_SHAPE        the shape names one series, and the fill was
                                     never in question for it
        MEASURED_MARKER_FILL         one shape on the panel, so the fill names it
        DECLARED_SINGLE_SERIES       one series, and nothing measured names it

    `(None, None)` means THERE IS NOTHING TO DERIVE FROM - the record measured no
    marker, or the manifest declares none. Both are ordinary: a fixture's
    declaration and a person's click carry no marker evidence, and a colour panel
    declares no shape. `route_failure` is what turns a derivable route that
    DISAGREES into a finding.
    """
    import marker_routing as MRT
    ev = routing_evidence(record)
    shape = _s(ev["Marker_Shape"]).upper()
    fill = _s(ev["Marker_Fill"]).upper()
    declared, fills_of = declared_markers(series_rows, panel_id)
    if declared is None or (not shape and not fill):
        return None, None
    if shape not in fills_of:
        return "", MRT.identity_method(len(fills_of) > 1, False)
    fills = fills_of[shape]
    method = MRT.identity_method(len(fills_of) > 1, len(fills) > 1)
    if len(fills) > 1:
        return (declared.get((shape, fill), "") if fill else ""), method
    # THE FILL IS NOT WHAT NAMES IT. `route` leaves such a mark's fill blank
    # because nothing measured it, so a record carrying one is claiming a
    # measurement its own method says was not made - and the empty expected
    # series below is what says so.
    if fill:
        return "", method
    return declared.get((shape, sorted(fills)[0]), ""), method


def route_failure(record, series_rows, panel_id=None):
    """Why this record's Series_ID or Identity_Method is not what its evidence says.

    RE-DERIVED, NOT READ, like `marker_validity` and `fill_group_validity`. The
    difference is what it re-derives: those two ask whether the measurements on
    the record are consistent with each other, and this asks the question the
    reader exists to answer - does this MARKER mean this SERIES on this panel?
    Without it two points on the same axis could have their `Series_ID` swapped,
    every hash re-derived, and nothing in this package disagreed.
    """
    want_series, want_method = expected_route(record, series_rows, panel_id)
    if want_series is None:
        return ""
    ev = routing_evidence(record)
    shape = _s(ev["Marker_Shape"]) or "(no shape)"
    fill = _s(ev["Marker_Fill"]) or "(no measured fill)"
    got_series = _s(record.get("Series_ID"))
    if not want_series:
        return ("%s: no series of this panel is a %s %s, and the record says %s"
                % (ROUTE_NOT_DERIVED, fill, shape, got_series or "nothing"))
    if got_series != want_series:
        return ("%s: a %s %s on this panel is %s, and the record says %s"
                % (ROUTE_NOT_DERIVED, fill, shape, want_series,
                   got_series or "nothing"))
    got_method = _s(record.get("Identity_Method"))
    if got_method != want_method:
        return ("%s: this panel's declaration makes the route %s and the record "
                "claims %s" % (ROUTE_NOT_DERIVED, want_method,
                               got_method or "nothing"))
    return ""


#: THE EVIDENCE COLUMNS THAT ARE WORDS, not numbers. Their blank is the empty
#: string and it has to survive a round trip through a CSV: `_number("")` is
#: None, and a record whose `Marker_Fill` was "" - which is what a mark named by
#: its SHAPE alone carries, because nothing measured its fill - came back None
#: and hashed to a different digest than the file it was read from. One blank per
#: column, and for these it is "".
TEXT_EVIDENCE = ("Marker_Validity_Status", "Marker_Shape", "Marker_Fill",
                 "Fill_Conditioning_Shape", "Fill_Group_Separates")

#: The one status under which a point may carry a measured series.
SINGLE_MARKER = "SINGLE_MARKER"
#: What `verify_points` says when the evidence on a routed point says the blob
#: it came from was not one marker.
NOT_ONE_MARKER = "MARKER_NOT_ONE_MARKER"


def routing_evidence(point):
    """The ten fields, read off a routed point, with margins computed.

    A point that did not come from `marker_routing` - a fixture's declaration, a
    person's click - has None in every field, and that is a value the hash
    covers like any other: it says "nothing measured this", which is exactly
    what distinguishes it from a mark whose class was established.
    """
    out = {}
    for key in ROUTING_EVIDENCE:
        src = _EVIDENCE_FROM.get(key)
        out[key] = point.get(src) if src else None
    for margin, value, split in (("Shape_Margin", "Third_Harmonic", "Shape_Split"),
                                 ("Fill_Margin", "Interior_Ink", "Fill_Split")):
        # `Off_Centre_Margin` is NOT computed here - it comes off the record, so
        # that a producer who edits it disagrees with `Off_Centre_Threshold`
        # minus `Off_Centre_Ink` and `verify_points` can say so.
        if out[value] is None or out[split] is None:
            out[margin] = None
        else:
            out[margin] = round(abs(float(out[value]) - float(out[split])), 6)
    return out


def routing_evidence_sha256(point):
    return hashlib.sha256(json.dumps(routing_evidence(point), sort_keys=True,
                                     default=float).encode("utf-8")).hexdigest()


def point_record_sha256(point, axis_id, y_calibration, x_calibration, panel_id,
                        image_sha256, axis_record="", x_axis_record="",
                        routing_evidence_hash=""):
    """WHAT WAS MEASURED, WHOSE IT IS, under which axis, on which image.

    THE FIRST VERSION COVERED THE PIXEL AND THE CALIBRATION ONLY, and a point's
    SERIES was outside it: swap `Series_ID` between two points read on the same
    axis and both hashes still verified, because everything the hash covered was
    unchanged. Two clouds then exchange a member each and every downstream check
    agrees with itself. So the identity travels inside the hash too - the series,
    how that series was decided, the axis row it was read on rather than only the
    fit, and the routing evidence the decision rested on.
    """
    return hashlib.sha256(json.dumps(
        {"point_px_x": round(float(point["point_px_x"]), 4),
         "point_px_y": round(float(point["point_px_y"]), 4),
         "Series_ID": _s(point.get("Series_ID")),
         "Identity_Method": _s(point.get("Identity_Method")),
         "Value_Method": _s(point.get("Value_Method")),
         "Axis_ID": _s(axis_id),
         "Panel_ID": _s(panel_id),
         "Image_SHA256": _s(image_sha256),
         "Axis_Record_SHA256": _s(axis_record),
         "X_Axis_Record_SHA256": _s(x_axis_record),
         # THE TWO GRAINS UNDER THIS POINT. Inside the hash, or a producer could
         # re-point a row at another candidate or another group and leave every
         # other digest standing.
         "Candidate_Record_SHA256": _s(point.get("Candidate_Record_SHA256")),
         "Fill_Group_Record_SHA256": _s(point.get("Fill_Group_Record_SHA256")),
         "Routing_Evidence_SHA256": _s(routing_evidence_hash),
         "X_Calibration": _calibration_record(x_calibration),
         "Y_Calibration": _calibration_record(y_calibration)},
        sort_keys=True, default=float).encode("utf-8")).hexdigest()


def stamp_points(points, series_rows, axes, x_axis_id, panel_id, image_sha256):
    """Every point calibrated against ITS OWN axis, with its own hash.

    IT TOOK AN `axis_of` MAPPING AND TRUSTED IT. `series_axis` checked that a
    series named a Y axis on this panel, and then nothing made a caller go
    through `series_axis`: hand this function `{"S1": "X_BOTTOM"}` directly and
    every point was stamped with the x calibration used as the y scale, hashed,
    and verified clean. The check has to live where the stamp is made, so the
    mapping is DERIVED here from the series manifest rather than accepted.

    `series_rows` is that manifest - `[{"Series_ID": ..., "Axis_ID": ...}, ...]`.
    `axes` is the axis manifest, from which both the calibrations and the axis
    records are derived here as well: a caller holding a `cals` dict that no
    longer matches the manifest it came from is another way for a point to cite
    an axis row it was not read under.

    A point whose series names no axis, or names one that is not a Y axis on
    this panel, is not calibrated at all - it comes back with its pixel, its
    refusal, and no value, because a value on an unknown scale is the thing this
    module exists to prevent.
    """
    cals = calibrations(axes)
    records = axis_records(axes)
    xrow = _x_axis(axes, x_axis_id, panel_id)
    xcal = cals[_s(xrow["Axis_ID"])]
    xrec = records[_s(xrow["Axis_ID"])]
    axis_of, refused = series_axis(series_rows, axes, panel_id=panel_id)
    out = []
    for p in points:
        sid = _s(p.get("Series_ID")) or _s(p.get("series"))
        axis = axis_of.get(sid)
        rec = dict(p)
        rec["Series_ID"] = sid
        if not axis:
            rec.update(Axis_ID="", x_value=None, y_value=None,
                       Point_Record_SHA256="",
                       refusal=refused.get(sid, UNKNOWN_AXIS))
            out.append(rec)
            continue
        ycal = cals[axis]
        rec.update(
            Axis_ID=axis,
            Axis_Record_SHA256=records[axis],
            X_Axis_ID=_s(xrow["Axis_ID"]),
            X_Axis_Record_SHA256=xrec,
            x_value=xcal.pixel_to_value(float(p["point_px_x"])),
            y_value=ycal.pixel_to_value(float(p["point_px_y"])),
            Value_Method="MARKER_CENTER",
            refusal="")
        rec["Routing_Evidence_SHA256"] = routing_evidence_sha256(rec)
        rec["Point_Record_SHA256"] = point_record_sha256(
            rec, axis, ycal, xcal, panel_id, image_sha256,
            axis_record=records[axis], x_axis_record=xrec,
            routing_evidence_hash=rec["Routing_Evidence_SHA256"])
        out.append(rec)
    return out


def point_set_sha256(records):
    """Over the point hashes SORTED, because a scatter cloud is a set.

    IT WAS OVER THE ORDERED LIST and the name said `Set`. Reading the same panel
    with the components enumerated in a different order - which is a property of
    the labelling, not of the figure - then produced a different set hash for
    the same cloud, and two runs of the same reader disagreed about a figure
    neither had misread. A dropped point still moves this; a reordering does
    not, and the ORDER is preserved separately in `Point_Record_SHA256_List`.
    """
    return hashlib.sha256(json.dumps(
        sorted(_s(r.get("Point_Record_SHA256")) for r in records)
    ).encode("utf-8")).hexdigest()


def association_over_points(records, association_type="PEARSON_R",
                            aggregation=None):
    """An association and the point set it was computed from, by hash.

    ONE AXIS AND ONE SERIES. The axis rule is arithmetic - two scales in one
    cloud are not measurements of one quantity. The SERIES rule is not: Pearson's
    r over an open-circle cloud and a filled-circle cloud together is perfectly
    computable, and it answers a question nobody asked. Two series on one axis
    are two experimental groups, and pooling them silently turns "resistance
    falls with pressure in the supine group" into a number about neither group.

    A caller that means to pool says so in `aggregation`, giving all three of
    `AGGREGATION_COLUMNS`; the declaration travels on the summary, so a reviewer
    reads the justification next to the r rather than having to notice that the
    Series_ID column holds two values.
    """
    import mark_readers as MR
    bad = [r for r in records if r.get("refusal") or r.get("y_value") is None]
    if bad:
        raise ValueError(
            "%d of %d points carry no value (%s); an association over them "
            "would be an association over a different cloud"
            % (len(bad), len(records),
               ", ".join(sorted({_s(r.get("refusal")) or "no value" for r in bad}))))
    axes = {_s(r.get("Axis_ID")) for r in records}
    if len(axes) != 1:
        # TWO SCALES IN ONE CLOUD. Pearson's r is invariant to a positive affine
        # change of y WITHIN a series, so mixing two series that share an axis is
        # a different question from mixing two AXES - and this one has no answer:
        # the cloud's y values are not measurements of one quantity.
        raise ValueError("these points are read on %d axes (%s); an association "
                         "needs one" % (len(axes), ", ".join(sorted(axes))))
    series = sorted({_s(r.get("Series_ID")) for r in records})
    declared = dict(aggregation or {})
    if len(series) != 1:
        missing = [c for c in AGGREGATION_COLUMNS if not _s(declared.get(c))]
        if missing:
            raise ValueError(
                "%s: these points belong to %d series (%s) and the pooling is "
                "not declared - %s. An r over two groups is a number about "
                "neither."
                % (MULTIPLE_SERIES, len(series), ", ".join(series),
                   ", ".join("no " + c for c in missing)))
        said = [x.strip() for x in _s(declared["Aggregation_Series_IDs"]).split(",")]
        if sorted(x for x in said if x) != series:
            raise ValueError(
                "%s: the declaration pools %s and the points are %s"
                % (MULTIPLE_SERIES, ", ".join(sorted(x for x in said if x)),
                   ", ".join(series)))
    summary = MR.summarize_association(
        [dict(x_value=r["x_value"], y_value=r["y_value"]) for r in records],
        association_type)
    summary["Axis_ID"] = sorted(axes)[0]
    summary["Series_ID"] = series[0] if len(series) == 1 else ""
    for column in AGGREGATION_COLUMNS:
        summary[column] = _s(declared.get(column))
    summary["Point_Set_SHA256"] = point_set_sha256(records)
    summary["Point_Record_SHA256_List"] = [_s(r.get("Point_Record_SHA256"))
                                           for r in records]
    summary["Expected_Point_Count"] = None
    summary["Candidate_Mark_Record_Count"] = len(records)
    summary["Routed_Point_Count"] = sum(1 for r in records
                                        if _s(r.get("Series_ID")))
    summary["Unresolved_Candidate_Count"] = sum(1 for r in records
                                                if not _s(r.get("Series_ID")))
    summary["Candidate_Count_Agreement"] = ""
    return summary


def with_completeness(summary, counts):
    """Carry `marker_routing.route`'s counts onto an association.

    THE COUNTS HAVE TO REACH THE ROW SOMEBODY READS. An association over
    nineteen points is silent about the eleven marks the reader never saw, and
    an r over two thirds of a cloud is not an r over the cloud. `route` counts
    them; this is how the count travels the last step.
    """
    out = dict(summary)
    for key in ("Expected_Point_Count", "Candidate_Mark_Record_Count",
                "Routed_Point_Count", "Unresolved_Candidate_Count",
                "Candidate_Count_Agreement"):
        if key in counts:
            out[key] = counts[key]
    return out


def verify_points(records, series_rows, axes, x_axis_id, panel_id, image_sha256):
    """Everything about these points that does not follow from what they carry.

    THE HASH IS NOT THE ONLY CHECK, because a producer who edits a record can
    re-stamp every hash on it. Three things are re-derived rather than believed:
    the axis a point cites has to BE a Y axis on this panel and the one its
    series is declared on, the value has to follow from the pixel under that
    axis' calibration, and the routing evidence has to be consistent with the
    series the point carries - a blob whose own recorded off-centre ink is over
    its own recorded threshold was not one marker, whatever the refusal field
    was later set to.
    """
    cals = calibrations(axes)
    recs = axis_records(axes)
    by_id = {_s(r.get("Axis_ID")): r for r in axes}
    xrow = _x_axis(axes, x_axis_id, panel_id)
    xcal = cals[_s(xrow["Axis_ID"])]
    xrec = recs[_s(xrow["Axis_ID"])]
    declared, _refused = series_axis(series_rows, axes, panel_id=panel_id)
    out = []
    for i, r in enumerate(records):
        axis = _s(r.get("Axis_ID"))
        if not axis:
            out.append((i, "no axis"))
            continue
        if axis not in cals:
            out.append((i, "axis %s is not in this manifest" % axis))
            continue
        # THE AXIS' ROLE, RE-DERIVED HERE. `series_axis` refuses a series that
        # names the x axis, and a record can be written past `series_axis`: this
        # is the same question asked of the record itself.
        row = by_id[axis]
        if _s(row.get("Dimension")).upper() != "Y":
            out.append((i, "%s: %s is a %s axis"
                        % (WRONG_DIMENSION, axis,
                           _s(row.get("Dimension")).upper() or "dimensionless")))
            continue
        if _s(row.get("Panel_ID")) != _s(panel_id):
            out.append((i, "%s: %s belongs to panel %s"
                        % (WRONG_PANEL, axis, _s(row.get("Panel_ID")))))
            continue
        said = declared.get(_s(r.get("Series_ID")))
        if said is None:
            out.append((i, "%s: %s is not a series of this panel"
                        % (UNKNOWN_AXIS, _s(r.get("Series_ID")))))
            continue
        if said != axis:
            out.append((i, "this point is read on %s and its series is declared "
                           "on %s" % (axis, said)))
            continue
        want = point_record_sha256(r, axis, cals[axis], xcal, panel_id,
                                   image_sha256, axis_record=recs[axis],
                                   x_axis_record=xrec,
                                   routing_evidence_hash=_s(
                                       r.get("Routing_Evidence_SHA256")))
        if want != _s(r.get("Point_Record_SHA256")):
            out.append((i, "hash does not cover this point"))
            continue
        if routing_evidence_sha256(r) != _s(r.get("Routing_Evidence_SHA256")):
            # THE HASH IS SELF-CONSISTENT AND THE EVIDENCE IS NOT. A producer
            # that rewrote a mark's shape and re-stamped the point would pass
            # the line above; this re-measures the evidence hash from the
            # evidence still on the record.
            out.append((i, "routing evidence does not hash to what it carries"))
            continue
        bad = marker_validity(r)
        if bad:
            out.append((i, bad))
            continue
        # AND DOES THIS MARKER MEAN THIS SERIES. Re-derived from the evidence and
        # the declaration; the two fields a producer would edit are the two this
        # does not read. Without it a same-axis `Series_ID` swap passed every
        # check in this package.
        bad = route_failure(r, series_rows, panel_id)
        if bad:
            out.append((i, bad))
            continue
        ycal = cals[axis]
        for key, cal, pixel in (("x_value", xcal, "point_px_x"),
                                ("y_value", ycal, "point_px_y")):
            if r.get(key) is None:
                out.append((i, "no %s" % key))
            elif abs(cal.pixel_to_value(float(r[pixel])) - float(r[key])) > 1e-6:
                out.append((i, "%s does not follow from %s" % (key, pixel)))
        if _s(r.get("Value_Method")) != "MARKER_CENTER":
            out.append((i, "Value_Method=%r; a routed scatter point is its "
                           "marker's centre" % _s(r.get("Value_Method"))))
    return out


def marker_validity(record):
    """Why this record's own evidence says its blob was not one marker, or "".

    RE-DERIVED, NOT READ. `Marker_Validity_Status` is a word and the two numbers
    beside it are the measurement: a producer that clears a refusal, writes a
    Series_ID and re-stamps every hash has to also make `Off_Centre_Ink` smaller
    than `Off_Centre_Threshold` and keep `Off_Centre_Margin` equal to their
    difference - at which point it is no longer editing a field, it is claiming
    a measurement that a raster can be held against.
    """
    ev = routing_evidence(record)
    ink, cut = ev["Off_Centre_Ink"], ev["Off_Centre_Threshold"]
    if ink is None or cut is None:
        # NOTHING MEASURED THIS. A fixture's declaration or a person's click
        # carries no marker evidence at all, and that is not a contradiction -
        # it is what `Identity_Method` is for.
        return ""
    if float(ink) > float(cut):
        return ("%s: off-centre ink %.4f is over this panel's own %.4f, so the "
                "component this point came from held more than one marker"
                % (NOT_ONE_MARKER, float(ink), float(cut)))
    if ev["Off_Centre_Margin"] is not None \
            and abs(float(ev["Off_Centre_Margin"])
                    - (float(cut) - float(ink))) > 1e-6:
        return ("%s: the recorded margin %.4f is not %.4f minus %.4f"
                % (NOT_ONE_MARKER, float(ev["Off_Centre_Margin"]),
                   float(cut), float(ink)))
    if _s(ev["Marker_Validity_Status"]) != SINGLE_MARKER:
        return ("%s: Marker_Validity_Status=%r"
                % (NOT_ONE_MARKER, _s(ev["Marker_Validity_Status"])))
    return fill_group_validity(record)


#: What `verify_points` says when a routed point's own fill evidence does not
#: support the class it carries.
NOT_A_GROUP = "MARKER_FILL_GROUP_DOES_NOT_SUPPORT_THIS_CLASS"


def fill_group_validity(record):
    """Why this record's own group evidence does not name its fill, or "".

    RE-DERIVED, NOT READ, for the same reason `marker_validity` re-derives the
    merged-blob verdict. Since v9.16 a mark's fill comes from a split taken over
    ITS OWN SHAPE'S marks, so three things have to hold on the row: the group
    said it separates, the recorded margin is the distance from the recorded
    threshold to the recorded ink, and the side of the threshold the ink falls
    on is the fill the row carries. A producer that writes FILLED on a mark
    whose ink is under its own group's threshold is claiming a measurement the
    row itself contradicts.

    A row with no group evidence at all - a fixture's declaration, a person's
    click - says nothing here, exactly as `marker_validity` says nothing about
    a record that measured no off-centre ink.
    """
    ev = routing_evidence(record)
    threshold = ev["Fill_Group_Threshold"]
    ink = ev["Interior_Ink"]
    if threshold is None or ink is None:
        return ""
    if _s(ev["Fill_Group_Separates"]).upper() != "TRUE":
        return ("%s: Fill_Group_Separates=%r, so this panel established no fill "
                "split inside %s" % (NOT_A_GROUP,
                                     _s(ev["Fill_Group_Separates"]),
                                     _s(ev["Fill_Conditioning_Shape"]) or "?"))
    margin = ev["Fill_Group_Margin"]
    if margin is None or abs(float(margin)
                             - abs(float(ink) - float(threshold))) > 1e-6:
        return ("%s: the recorded group margin %r is not the distance from "
                "%.6f to %.6f" % (NOT_A_GROUP, margin, float(ink),
                                  float(threshold)))
    want = "FILLED" if float(ink) >= float(threshold) else "OPEN"
    if _s(ev["Marker_Fill"]) and _s(ev["Marker_Fill"]) != want:
        return ("%s: interior ink %.6f is %s its own group's threshold %.6f, "
                "which is %s, and the row says %s"
                % (NOT_A_GROUP, float(ink),
                   "at or over" if want == "FILLED" else "under",
                   float(threshold), want, _s(ev["Marker_Fill"])))
    # THE SHAPE THE GROUP WAS TAKEN OVER HAS TO BE THIS MARK'S SHAPE. Without
    # this a row could carry the circles' threshold under a triangle's shape and
    # every arithmetic check above would still pass.
    if _s(ev["Fill_Conditioning_Shape"]) != _s(ev["Marker_Shape"]):
        return ("%s: the fill was decided in the %r group and this mark's "
                "shape is %r" % (NOT_A_GROUP,
                                 _s(ev["Fill_Conditioning_Shape"]),
                                 _s(ev["Marker_Shape"])))
    return ""
