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

So every point gets `Point_Record_SHA256` over its pixel, its axis and the
calibration it was read under, and an association carries `Point_Set_SHA256`
over the ordered list of them. Then a moved pixel breaks its own point's hash, a
dropped point breaks the set hash, and a recalibrated axis breaks every point on
THAT axis and none on the other - which is the property a twin-axis figure needs
most, because half its points are read under each.
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
            if len(set(values)) < 2 or len(set(pixels)) < 2:
                out.append("%s: its calibration points do not span anything"
                           % where)
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
    """{Axis_ID: AxisCalibration}, refusing a manifest that does not validate."""
    import mark_readers as MR
    problems = validate_axes(rows)
    if problems:
        raise ValueError("the axis manifest does not validate: %s"
                         % "; ".join(problems))
    out = {}
    for row in rows:
        pts = [(float(v), float(px)) for v, px in row["Calibration_Points"]]
        out[_s(row["Axis_ID"])] = MR.AxisCalibration.from_points(pts)
    return out


def series_axis(series_rows, axes):
    """{Series_ID: Axis_ID}, or a refusal per series that cannot name one."""
    known = {_s(r.get("Axis_ID")) for r in axes}
    out, refused = {}, {}
    for row in series_rows:
        sid = _s(row.get("Series_ID")) or _s(row.get("id"))
        axis = _s(row.get(SERIES_AXIS_COLUMN))
        if not axis:
            refused[sid] = UNKNOWN_AXIS
        elif axis not in known:
            refused[sid] = FOREIGN_AXIS
        else:
            out[sid] = axis
    return out, refused


def _calibration_record(cal):
    import mark_readers as MR
    return MR._calibration_record(cal)


def point_record_sha256(point, axis_id, y_calibration, x_calibration,
                        panel_id, image_sha256):
    """WHAT WAS MEASURED, under which axis, on which image.

    The pixel and the calibration together, because a pixel is only a
    measurement relative to one - and the AXIS ID inside the hash, so the same
    pixel read on the left scale and on the right scale are two different
    records rather than one with two values.
    """
    return hashlib.sha256(json.dumps(
        {"point_px_x": round(float(point["point_px_x"]), 4),
         "point_px_y": round(float(point["point_px_y"]), 4),
         "Axis_ID": _s(axis_id),
         "Panel_ID": _s(panel_id),
         "Image_SHA256": _s(image_sha256),
         "X_Calibration": _calibration_record(x_calibration),
         "Y_Calibration": _calibration_record(y_calibration)},
        sort_keys=True, default=float).encode("utf-8")).hexdigest()


def stamp_points(points, axis_of, cals, x_axis_id, panel_id, image_sha256):
    """Every point calibrated against ITS OWN axis, with its own hash.

    `axis_of` maps Series_ID to Axis_ID; `cals` is `calibrations`' output. A
    point whose series names no axis is not calibrated at all - it comes back
    with its pixel, its refusal, and no value, because a value on an unknown
    scale is the thing this module exists to prevent.
    """
    xcal = cals[x_axis_id]
    out = []
    for p in points:
        sid = _s(p.get("Series_ID")) or _s(p.get("series"))
        axis = axis_of.get(sid)
        rec = dict(p)
        rec["Series_ID"] = sid
        if not axis:
            rec.update(Axis_ID="", x_value=None, y_value=None,
                       Point_Record_SHA256="", refusal=UNKNOWN_AXIS)
            out.append(rec)
            continue
        ycal = cals[axis]
        rec.update(
            Axis_ID=axis,
            x_value=xcal.pixel_to_value(float(p["point_px_x"])),
            y_value=ycal.pixel_to_value(float(p["point_px_y"])),
            Value_Method="MARKER_CENTER",
            refusal="")
        rec["Point_Record_SHA256"] = point_record_sha256(
            rec, axis, ycal, xcal, panel_id, image_sha256)
        out.append(rec)
    return out


def point_set_sha256(records):
    """Over the ORDERED point hashes, so a dropped point is a different set."""
    return hashlib.sha256(json.dumps(
        [_s(r.get("Point_Record_SHA256")) for r in records],
        sort_keys=False).encode("utf-8")).hexdigest()


def association_over_points(records, association_type="PEARSON_R"):
    """An association and the point set it was computed from, by hash.

    Refuses a set holding a point that was not calibrated: an r over a cloud
    where one member has no value is an r over a different cloud.
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
    summary = MR.summarize_association(
        [dict(x_value=r["x_value"], y_value=r["y_value"]) for r in records],
        association_type)
    summary["Axis_ID"] = sorted(axes)[0]
    summary["Point_Set_SHA256"] = point_set_sha256(records)
    summary["Point_Record_SHA256_List"] = [_s(r.get("Point_Record_SHA256"))
                                           for r in records]
    return summary


def verify_points(records, cals, x_axis_id, panel_id, image_sha256):
    """Which points no longer hash to what they carry, and which lost a value."""
    xcal = cals[x_axis_id]
    out = []
    for i, r in enumerate(records):
        axis = _s(r.get("Axis_ID"))
        if not axis:
            out.append((i, "no axis"))
            continue
        if axis not in cals:
            out.append((i, "axis %s is not in this manifest" % axis))
            continue
        want = point_record_sha256(r, axis, cals[axis], xcal, panel_id,
                                   image_sha256)
        if want != _s(r.get("Point_Record_SHA256")):
            out.append((i, "hash does not cover this point"))
            continue
        ycal = cals[axis]
        for key, cal, pixel in (("x_value", xcal, "point_px_x"),
                                ("y_value", ycal, "point_px_y")):
            if r.get(key) is None:
                out.append((i, "no %s" % key))
            elif abs(cal.pixel_to_value(float(r[pixel])) - float(r[key])) > 1e-6:
                out.append((i, "%s does not follow from %s" % (key, pixel)))
    return out
