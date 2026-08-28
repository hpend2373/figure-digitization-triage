# -*- coding: utf-8 -*-
"""The durable file a routed scatter leaves behind, and what can be checked against the ink.

    points, meta = read_routed_scatter_panel(image, panel_box, series, axes,
                                             panel_id, image_sha256, x_axis_id)
    rows = artifact_rows(points, meta)
    verify_artifact(rows, series, axes, panel_id, image_sha256)
    current_evidence_failures(rows, image, panel_box, series)

WHY A SECOND POINT FILE. `mark_readers.write_point_data` already persists a
cloud and re-derives every value from its own pixel at write time, and that is
the right file for a scatter whose series were told apart by COLOUR: the
identity is a hex value somebody declared and the cloud is the whole evidence.
A MONOCHROME four-series panel is not that. Its identity was measured - a shape
and a fill, each against a threshold the panel's own distribution produced - and
none of those measurements fit in a file whose per-point columns are

    series, point_px_x, point_px_y, x_value, y_value, Identity_Method

So a value read this way could be published with its identity route named and
nothing on disk able to disagree. This file is the disagreement: every point
carries the twenty-nine measurements `marker_routing` decided on - the marker's
own geometry, the shape split, and the fill group of its own shape - the axis it
was read against, and three hashes binding them together.

## THREE DIFFERENT CHECKS, AND ONLY THE THIRD LOOKS AT THE FIGURE

    verify_artifact            the file against ITSELF - every hash covers what
                               it carries, every value follows from its pixel
                               under the axis it cites, no two rows are one
                               point, and no point sits under a series the
                               manifest does not put on that axis.
    axis_grain.verify_points   the same, at the record level, plus the marker
                               validity the routing rested on AND whether this
                               marker's evidence names this series at all -
                               `expected_route`, which is what makes a swapped
                               `Series_ID` a finding rather than a re-stamp.
    current_evidence_failures  the file against THE RASTER. The panel is routed
                               again, now, and each row's recorded evidence is
                               compared with what the ink says today.

The first two cannot catch a producer that measured nothing and wrote a
consistent file; the third can, and it is the only one that needs the image. It
is also the only one that can go stale for an innocent reason - a different
OpenCV, a re-rendered page - so it reports differences rather than raising, and
the caller decides what a difference is worth.
"""
import hashlib
import json

import axis_grain as AG
import marker_routing as MRT

#: One row per point, and the evidence is not in a JSON blob. A reviewer opening
#: this file has to be able to sort by `Off_Centre_Ink` without parsing anything.
POINT_ARTIFACT_COLUMNS = (
    "Panel_ID", "Series_ID", "Axis_ID", "X_Axis_ID",
    "point_px_x", "point_px_y", "x_value", "y_value",
    "Identity_Method", "Value_Method",
) + AG.ROUTING_EVIDENCE + (
    "Image_SHA256", "Axis_Record_SHA256", "X_Axis_Record_SHA256",
    # THE TWO GRAINS UNDER THIS ONE, cited by hash. A point file holds only
    # ROUTED points, so a fill group's N and distribution can never be rebuilt
    # from it: the marks that were refused AT the fill boundary - the ones that
    # made the group what it is - are exactly the ones it does not carry. Until
    # v9.19 the only thing that could re-derive a group was re-opening the
    # raster, and a finalizer handed an artifact bundle and no figure had to
    # take the group's own word for it.
    "Candidate_Record_SHA256", "Fill_Group_Record_SHA256",
    "Routing_Evidence_SHA256", "Point_Record_SHA256",
)

#: WHAT A CANDIDATE MARK MEASURED ABOUT ITSELF - the routing evidence minus the
#: group's numbers and minus the panel-wide diagnostics. The group is taken OVER
#: these marks, so a candidate hash that covered the group's answer would make
#: the two grains cite each other in a circle.
CANDIDATE_EVIDENCE = tuple(c for c in AG.ROUTING_EVIDENCE
                           if c not in MRT.GROUP_EVIDENCE
                           and c not in ("Fill_Split", "Fill_Margin"))

#: One row per CANDIDATE mark, routed or refused. `NOT_A_MARKER` records are
#: furniture and are not candidates - the same population `route` counts as
#: `Candidate_Mark_Record_Count`.
CANDIDATE_COLUMNS = (
    ("Panel_ID", "Candidate_Index", "point_px_x", "point_px_y", "Refusal")
    + CANDIDATE_EVIDENCE + ("Image_SHA256", "Candidate_Record_SHA256"))

#: One row per SHAPE GROUP the fill question was asked of, citing every
#: candidate it was taken over. This is what makes the split re-derivable from
#: the files alone: the cited candidates carry their own interior ink, so the
#: threshold, the spread and the verdict can be recomputed and compared.
GROUP_COLUMNS = (
    "Panel_ID", "Fill_Conditioning_Shape", "Declared_Fills", "Fill_Group_N",
    "Fill_Group_Low_N", "Fill_Group_High_N", "Fill_Group_Threshold",
    "Fill_Group_Between", "Fill_Group_Within", "Fill_Group_Separation_Index",
    "Fill_Group_Minimum_Allowed", "Fill_Group_Separates",
    "Candidate_Record_SHA256_List", "Image_SHA256", "Fill_Group_Record_SHA256")

#: The two artifact types the grains are registered under.
CANDIDATE_ARTIFACT_TYPE = "SCATTER_MARKER_CANDIDATES"
GROUP_ARTIFACT_TYPE = "SCATTER_FILL_GROUPS"

#: The artifact type this file is registered under in a run's ledger.
ARTIFACT_TYPE = "SCATTER_POINTS"
#: WHAT A ROUTED POINT'S IDENTITY MAY BE CALLED, and it is not one name. Which
#: method a mark carries depends on which axis the panel's DECLARATION made
#: measurable: both, the fill alone (one declared shape), or the shape alone (a
#: shape declared with one fill). See `marker_routing.identity_method`.
#:
#: These three REQUIRE this file. `DECLARED_SINGLE_SERIES` - a panel of one
#: series, where nothing was measured to name anything - does not, and is
#: produced by the unrouted reader as well.
IDENTITY_METHODS = ("MEASURED_MARKER_SHAPE_FILL", "MEASURED_MARKER_FILL",
                    "MEASURED_MARKER_SHAPE")
#: The method a four-class twin-axis panel produces, kept as a name because it
#: is the one the worked examples and the gallery talk about.
IDENTITY_METHOD = "MEASURED_MARKER_SHAPE_FILL"

#: A row's recorded evidence disagrees with the panel routed again now.
EVIDENCE_STALE = "ROUTING_EVIDENCE_DOES_NOT_MATCH_THE_INK"
#: There is no mark at this row's pixel any more.
NO_MARK_NOW = "NO_MARK_AT_THIS_PIXEL_NOW"
#: The panel no longer establishes the split this row's class rests on.
SPLIT_GONE = "THE_PANEL_NO_LONGER_SEPARATES"
#: THE RASTER ROUTES A MARK THIS FILE DOES NOT CARRY. Not the same finding as a
#: row with no mark under it: every row can be true and the SET still be wrong.
MARK_MISSING = "ROUTED_MARK_MISSING_FROM_ARTIFACT"
#: Two rows are the same point. A file holding a mark twice is a cloud with a
#: member the figure drew once, and an association over it is not the figure's.
DUPLICATE_POINT = "DUPLICATE_POINT_RECORD"
#: A group's numbers do not follow from the candidates it says it was taken over.
GROUP_NOT_DERIVED = "FILL_GROUP_DOES_NOT_FOLLOW_FROM_ITS_CANDIDATES"
#: A point cites a group or a candidate that is not in the bundle, or one whose
#: numbers are not the ones on the point.
GROUP_NOT_CITED = "POINT_CITES_A_GROUP_THIS_RUN_DID_NOT_WRITE"
CANDIDATE_NOT_CITED = "POINT_CITES_A_CANDIDATE_THIS_RUN_DID_NOT_WRITE"

#: WHAT THE EVIDENCE CONCLUDES, as opposed to what it measures. Neither is in
#: `ROUTING_EVIDENCE` - they are the answer, not the working - so the column loop
#: below would never have compared them with the raster. A `Series_ID` swapped
#: between two points on the SAME axis kept every measurement true and moved the
#: numbers under each other's headings.
ROUTE_COLUMNS = ("Series_ID", "Identity_Method")

#: PANEL-WIDE NUMBERS NO ROW'S ROUTE RESTS ON, since v9.16. They stay on the row
#: and inside its hash - a reviewer needs to see the line the old grain drew, and
#: an unhashed column is one a producer may edit quietly - and they are compared
#: with the raster under THEIR OWN CODE. A rendering that moves the PANEL's
#: threshold without moving this mark's own group has not made this row's ROUTE
#: stale, and calling that `ROUTING_EVIDENCE_DOES_NOT_MATCH_THE_INK` puts a
#: number nothing read in the same sentence as the numbers everything read.
PANEL_DIAGNOSTICS = ("Fill_Split", "Fill_Margin")
#: A panel-wide diagnostic has moved and the row's own route has not. Reported,
#: because dropping the comparison would leave a hashed column no re-measurement
#: ever looks at; named apart, because it is not a reason to doubt the value.
DIAGNOSTIC_STALE = "PANEL_DIAGNOSTIC_DOES_NOT_MATCH_THE_INK"

#: How far a re-routed centroid may sit from a recorded one and still be the
#: same mark, as a fraction of the panel's own marker. Not a pixel count: the
#: whole module measures in markers.
SAME_MARK = 0.25


def _s(value):
    return "" if value is None else str(value).strip()


def read_routed_scatter_panel(image, panel_box, series, axes, panel_id,
                              image_sha256, x_axis_id, threshold=150,
                              exclude_boxes=(), expected_points=None):
    """Route the marks, calibrate each against ITS OWN axis, stamp every point.

    `series` is the series manifest - `Series_ID`, `Marker_Shape`,
    `Marker_Fill`, `Axis_ID` - and every one of those four is load-bearing. The
    shape and fill are the declaration `marker_routing` routes against; the
    Axis_ID is what `axis_grain` calibrates against, and a series that names no
    axis, or names one that is not a Y axis of this panel, produces points with
    no value rather than points on a guessed scale.

    Returns `(points, meta)`. `points` is every ROUTED mark, stamped; `meta` is
    what the panel established - the two splits, the marker scale, and the
    candidate counts, refusals included. A caller that reports only `points` is
    reporting only the successes, which is why the counts are not optional.
    """
    declared = [dict(id=_s(r.get("Series_ID")),
                     shape=_s(r.get("Marker_Shape")).upper(),
                     fill=_s(r.get("Marker_Fill")).upper())
                for r in series]
    out = MRT.route(image, panel_box, declared, threshold=threshold,
                    exclude_boxes=exclude_boxes,
                    expected_points=expected_points)
    routed = [r for r in out["records"] if r.get("Series_ID")]
    # EACH POINT CITES THE CANDIDATE IT CAME FROM AND THE GROUP THAT NAMED IT,
    # by hash and before the stamp, so both are inside `Point_Record_SHA256`.
    cands = candidate_rows(out["records"], panel_id, image_sha256)
    groups = group_rows(out, cands, panel_id, image_sha256)
    by_pixel = {(round(float(c["point_px_x"]), 4),
                 round(float(c["point_px_y"]), 4)): c for c in cands}
    by_shape = {_s(g["Fill_Conditioning_Shape"]): g for g in groups}
    for r in routed:
        cand = by_pixel.get((round(float(r["point_px_x"]), 4),
                             round(float(r["point_px_y"]), 4)))
        r["Candidate_Record_SHA256"] = (_s(cand["Candidate_Record_SHA256"])
                                        if cand else "")
        shape = _s(r.get("Fill_Conditioning_Shape"))
        group = by_shape.get(shape) if shape else None
        r["Fill_Group_Record_SHA256"] = (_s(group["Fill_Group_Record_SHA256"])
                                         if group else "")
    stamped = AG.stamp_points(routed, series, axes, x_axis_id, panel_id,
                              image_sha256)
    # WHICH PANEL AND WHICH IMAGE, ON THE ROW. Both are inside
    # `Point_Record_SHA256` already, and a hash is not something a person can
    # sort a spreadsheet by: without these two columns a file holding two
    # panels' points could not be split back into them, and the finalizer's
    # join - value row's Run_Panel_ID against the file - had nothing to join on.
    for p in stamped:
        p["Panel_ID"] = panel_id
        p["Image_SHA256"] = image_sha256
    meta = {k: v for k, v in out.items() if k != "records"}
    meta["Refusals"] = sorted({r["refusal"] for r in out["records"]
                               if r["refusal"]})
    meta["records"] = out["records"]
    meta["candidate_rows"] = cands
    meta["group_rows"] = groups
    return stamped, meta


def artifact_rows(points):
    """The rows a batch writes, refusing a point that was not calibrated.

    A REFUSED POINT IS NOT IN THIS FILE. It has no value and no hash, so a row
    for it would be a row of blanks under a Series_ID - and the counts that say
    how many marks were refused live on the panel's own record, where a reader
    can see them beside how many were routed. Half a point in a point file is
    the shape this package refuses everywhere else.
    """
    rows = []
    for p in points:
        if not _s(p.get("Point_Record_SHA256")):
            raise ValueError(
                "scatter_points: POINT_NOT_STAMPED - %r carries no "
                "Point_Record_SHA256; a point that was refused belongs in the "
                "panel's counts, not in its point file"
                % (_s(p.get("Series_ID")) or "a point",))
        evidence = AG.routing_evidence(p)
        row = {}
        for column in POINT_ARTIFACT_COLUMNS:
            if column in evidence:
                value = evidence[column]
            else:
                value = p.get(column)
            row[column] = "" if value is None else value
        rows.append(row)
    return rows


def evidence_record(row):
    """An artifact ROW as a routing record, so the evidence can be re-derived.

    THE COLUMN NAMES AND THE RECORD NAMES ARE NOT THE SAME, on purpose: a file a
    person opens says `Off_Centre_Ink` and the reader that measured it says
    `off_centre_ink`. Everything that re-derives a verdict from a row has to
    come through here - `axis_grain.routing_evidence` reads the reader's names,
    so handing it a row straight from the CSV returns eighteen Nones and
    `marker_validity` then says "nothing measured this", which is the fail-open
    version of the check it was written to be.
    """
    rec = dict(row)
    for column in AG.ROUTING_EVIDENCE:
        source = AG._EVIDENCE_FROM.get(column)
        if source is None:
            continue
        # A WORD'S BLANK IS "" AND A NUMBER'S IS None, and a CSV spells both the
        # same way. Running a word through `_number` turned "" into None, so a
        # mark named by its shape alone - whose `Marker_Fill` is "" because
        # nothing measured it - hashed differently on the way back in.
        rec[source] = (_s(row.get(column)) if column in AG.TEXT_EVIDENCE
                       else _number(row.get(column)))
    return rec


def verify_artifact(rows, series, axes, panel_id, image_sha256):
    """What is wrong with this file, read back as a CSV reader hands it over.

    EVERY CELL A STRING, because that is what a person's copy of the file is
    after a spreadsheet has been near it. The hashes are recomputed over the
    numbers the file carries rather than the numbers a producer had in memory,
    so a value edited in a cell breaks the row that holds it.
    """
    problems = []
    # THE X AXIS COMES OFF THE FILE, and every row has to name the same one. A
    # caller passing it in would be telling the verifier which axis to check
    # against, which is the artifact-checked-against-itself shape this whole
    # file exists to avoid; and two rows naming different x axes is a panel
    # whose points are not on one drawing.
    xs = sorted({_s(r.get("X_Axis_ID")) for r in rows})
    if not rows:
        return []
    if len(xs) != 1 or not xs[0]:
        return ["these %d rows name %d x axes (%s); one panel has one"
                % (len(rows), len(xs), ", ".join(x or "nothing" for x in xs))]
    x_axis_id = xs[0]
    # TWO ROWS THAT ARE THE SAME POINT. Checked HERE as well as against the
    # raster, because it needs no figure: a file carrying one mark twice is
    # wrong about itself, and `current_evidence_failures` is the check a caller
    # can skip when it does not have the image.
    counted = {}
    for i, row in enumerate(rows):
        key = _s(row.get("Point_Record_SHA256"))
        if not key:
            continue
        if key in counted:
            problems.append("row %d: %s - this row is row %d again, and a "
                            "cloud cannot hold one mark twice"
                            % (i, DUPLICATE_POINT, counted[key]))
        else:
            counted[key] = i
    if problems:
        return problems
    records = []
    for i, row in enumerate(rows):
        rec = dict(row)
        for key in ("point_px_x", "point_px_y", "x_value", "y_value"):
            if _s(rec.get(key)) == "":
                problems.append("row %d: no %s" % (i, key))
                rec[key] = None
            else:
                try:
                    rec[key] = float(rec[key])
                except (TypeError, ValueError):
                    problems.append("row %d: %s=%r is not a number"
                                    % (i, key, rec[key]))
                    rec[key] = None
        # THE EVIDENCE COMES BACK OFF THE COLUMNS, and the record has to carry
        # it under the names `axis_grain` reads, or the evidence hash would be
        # recomputed over eighteen Nones and agree with nothing.
        rec = dict(evidence_record(rec), **{k: rec[k] for k in
                                            ("point_px_x", "point_px_y",
                                             "x_value", "y_value")})
        records.append(rec)
    if problems:
        return problems
    return ["row %d: %s" % (i, why) for i, why in
            AG.verify_points(records, series, axes, x_axis_id, panel_id,
                             image_sha256)]


def _number(value):
    """The cell as a number where it is one, as a string where it is not."""
    text = _s(value)
    if text == "":
        return None
    try:
        return float(text) if ("." in text or "e" in text.lower()) else int(text)
    except ValueError:
        return text


def candidate_evidence(record):
    """The mark's own measurements, under the names the FILE spells them."""
    ev = AG.routing_evidence(record)
    return {c: ev.get(c) for c in CANDIDATE_EVIDENCE}


def candidate_record_sha256(record, panel_id, image_sha256):
    """Over one mark's pixel, its refusal and what it measured about itself."""
    ev = candidate_evidence(record)
    return hashlib.sha256(json.dumps(
        {"Panel_ID": _s(panel_id), "Image_SHA256": _s(image_sha256),
         "point_px_x": round(float(record["point_px_x"]), 4),
         "point_px_y": round(float(record["point_px_y"]), 4),
         "Refusal": _s(record.get("refusal")),
         "evidence": {k: (None if ev[k] is None else
                          (float(ev[k]) if isinstance(ev[k], (int, float))
                           and not isinstance(ev[k], bool) else _s(ev[k])))
                      for k in sorted(ev)}},
        sort_keys=True, default=float).encode("utf-8")).hexdigest()


def candidate_rows(records, panel_id, image_sha256):
    """One row per candidate mark, routed or refused, in the order routed found them."""
    out = []
    for i, r in enumerate(x for x in records
                          if _s(x.get("refusal")) != "NOT_A_MARKER"):
        ev = candidate_evidence(r)
        row = dict(Panel_ID=panel_id, Candidate_Index=i,
                   point_px_x=round(float(r["point_px_x"]), 4),
                   point_px_y=round(float(r["point_px_y"]), 4),
                   Refusal=_s(r.get("refusal")), Image_SHA256=image_sha256,
                   Candidate_Record_SHA256=candidate_record_sha256(
                       r, panel_id, image_sha256))
        for column in CANDIDATE_EVIDENCE:
            row[column] = "" if ev.get(column) is None else ev[column]
        out.append(row)
    return out


def group_members(candidates, shape):
    """The candidate rows a shape's fill question was asked over.

    RE-DERIVED FROM THE FILE, not remembered. `route` takes the group over the
    marks that were ONE MARKER and whose shape came out as this one - a mark
    whose shape is unresolved carries no shape and is in no group - and both of
    those are columns on the candidate row.
    """
    return [c for c in candidates
            if _s(c.get("Marker_Validity_Status")) == AG.SINGLE_MARKER
            and _s(c.get("Marker_Shape")) == _s(shape)]


def fill_group_record_sha256(row):
    """Over the group's numbers AND the candidates it was taken over."""
    return hashlib.sha256(json.dumps(
        {k: _s(row.get(k)) for k in GROUP_COLUMNS
         if k != "Fill_Group_Record_SHA256"},
        sort_keys=True).encode("utf-8")).hexdigest()


def group_rows(meta, candidates, panel_id, image_sha256):
    """One row per shape group, citing the candidate hashes it rests on."""
    out = []
    for shape, g in sorted((meta.get("fill_groups") or {}).items()):
        members = group_members(candidates, shape)
        row = dict(
            Panel_ID=panel_id, Fill_Conditioning_Shape=shape,
            Declared_Fills="/".join(g.get("declared_fills") or ()),
            Fill_Group_N=int(g["n"]), Fill_Group_Low_N=int(g["low_n"]),
            Fill_Group_High_N=int(g["high_n"]),
            Fill_Group_Threshold=("" if g["split"]["threshold"] is None
                                  else g["split"]["threshold"]),
            Fill_Group_Between=float(g["split"]["between"]),
            Fill_Group_Within=float(g["split"]["within"]),
            Fill_Group_Separation_Index=g["index"],
            Fill_Group_Minimum_Allowed=int(g["minimum"]),
            Fill_Group_Separates=("TRUE" if g["split"]["separates"] else "FALSE"),
            Candidate_Record_SHA256_List=";".join(
                sorted(_s(c["Candidate_Record_SHA256"]) for c in members)),
            Image_SHA256=image_sha256)
        row["Fill_Group_Record_SHA256"] = fill_group_record_sha256(row)
        out.append(row)
    return out


def verify_candidates(rows):
    """What is wrong with the candidate file, read back as strings."""
    problems = []
    seen = {}
    for i, row in enumerate(rows):
        rec = evidence_record(dict(row))
        rec["point_px_x"] = _number(row.get("point_px_x"))
        rec["point_px_y"] = _number(row.get("point_px_y"))
        rec["refusal"] = _s(row.get("Refusal"))
        if rec["point_px_x"] is None or rec["point_px_y"] is None:
            problems.append("candidate %d: no pixel" % i)
            continue
        want = candidate_record_sha256(rec, _s(row.get("Panel_ID")),
                                       _s(row.get("Image_SHA256")))
        if want != _s(row.get("Candidate_Record_SHA256")):
            problems.append("candidate %d: hash does not cover this mark" % i)
            continue
        key = _s(row.get("Candidate_Record_SHA256"))
        if key in seen:
            problems.append("candidate %d: %s - this mark is candidate %d again"
                            % (i, DUPLICATE_POINT, seen[key]))
        else:
            seen[key] = i
    return problems


def verify_groups(groups, candidates):
    """Every group's numbers, RE-DERIVED from the candidates it cites.

    THIS IS WHAT THE POINT FILE COULD NOT DO. A fill group is a statistic over
    the marks of one shape, INCLUDING the ones the split then refused, and a file
    of routed points does not carry those. Handed both grains, a finalizer with
    no figure can recompute the threshold, the spread and the verdict and say
    whether the group it is being asked to trust is the one those marks make.
    """
    problems = []
    by_hash = {_s(c.get("Candidate_Record_SHA256")): c for c in candidates}
    for i, row in enumerate(groups):
        cited = [h for h in _s(row.get("Candidate_Record_SHA256_List")).split(";")
                 if h]
        missing = [h for h in cited if h not in by_hash]
        if missing:
            problems.append("group %d: %s - it cites %d candidate(s) this file "
                            "does not carry" % (i, GROUP_NOT_DERIVED,
                                                len(missing)))
            continue
        shape = _s(row.get("Fill_Conditioning_Shape"))
        members = group_members(list(by_hash.values()), shape)
        if sorted(cited) != sorted(_s(c["Candidate_Record_SHA256"])
                                   for c in members):
            problems.append(
                "group %d: %s - the %s marks in the candidate file are %d and "
                "this group cites %d"
                % (i, GROUP_NOT_DERIVED, shape or "(no shape)", len(members),
                   len(cited)))
            continue
        values = [_number(by_hash[h].get("Interior_Ink")) for h in cited]
        if any(v is None for v in values):
            problems.append("group %d: %s - a cited candidate carries no "
                            "interior ink" % (i, GROUP_NOT_DERIVED))
            continue
        got = MRT.fill_group(values)
        if len(_s(row.get("Declared_Fills")).split("/")) < 2 \
                and _s(row.get("Declared_Fills")):
            got["split"] = MRT.Split(None, 0.0, 0.0, False)
            got["low_n"] = got["high_n"] = 0
            got["index"] = 0.0
        want = dict(
            Fill_Group_N=int(got["n"]), Fill_Group_Low_N=int(got["low_n"]),
            Fill_Group_High_N=int(got["high_n"]),
            Fill_Group_Threshold=("" if got["split"].threshold is None
                                  else got["split"].threshold),
            Fill_Group_Between=float(got["split"].between),
            Fill_Group_Within=float(got["split"].within),
            Fill_Group_Separation_Index=got["index"],
            Fill_Group_Minimum_Allowed=int(got["minimum"]),
            Fill_Group_Separates=("TRUE" if got["split"].separates else "FALSE"))
        for key, value in sorted(want.items()):
            said, mine = _number(row.get(key)), value
            if isinstance(said, (int, float)) and isinstance(mine, (int, float)):
                if abs(float(said) - float(mine)) > 1e-4:
                    problems.append("group %d: %s - %s says %s and these %d "
                                    "marks give %s"
                                    % (i, GROUP_NOT_DERIVED, key, said,
                                       len(values), mine))
            elif _s(said) != _s(mine):
                problems.append("group %d: %s - %s says %r and these %d marks "
                                "give %r" % (i, GROUP_NOT_DERIVED, key,
                                             _s(said), len(values), _s(mine)))
        if fill_group_record_sha256(row) != _s(row.get("Fill_Group_Record_SHA256")):
            problems.append("group %d: hash does not cover this group" % i)
    return problems


def verify_citations(rows, candidates, groups):
    """Every point's two citations: the candidate it came from, the group that named it."""
    problems = []
    by_c = {_s(c.get("Candidate_Record_SHA256")): c for c in candidates}
    by_g = {_s(g.get("Fill_Group_Record_SHA256")): g for g in groups}
    for i, row in enumerate(rows):
        chash = _s(row.get("Candidate_Record_SHA256"))
        cand = by_c.get(chash)
        if cand is None:
            problems.append("row %d: %s (%s)" % (i, CANDIDATE_NOT_CITED,
                                                 chash[:12] or "nothing"))
        else:
            for column in CANDIDATE_EVIDENCE + ("point_px_x", "point_px_y"):
                said, mine = _number(row.get(column)), _number(cand.get(column))
                if isinstance(said, (int, float)) and isinstance(mine, (int, float)):
                    if abs(float(said) - float(mine)) > 1e-4:
                        problems.append("row %d: %s - %s is %s on the point and "
                                        "%s on the candidate it cites"
                                        % (i, CANDIDATE_NOT_CITED, column,
                                           said, mine))
                elif _s(said) != _s(mine):
                    problems.append("row %d: %s - %s is %r on the point and %r "
                                    "on the candidate it cites"
                                    % (i, CANDIDATE_NOT_CITED, column,
                                       _s(said), _s(mine)))
        ghash = _s(row.get("Fill_Group_Record_SHA256"))
        if not ghash:
            # A MARK NAMED BY ITS SHAPE ALONE CITES NO GROUP, because none was
            # asked. Its `Fill_Conditioning_Shape` is blank for the same reason.
            if _s(row.get("Fill_Conditioning_Shape")):
                problems.append("row %d: %s - it names a conditioning shape and "
                                "cites no group" % (i, GROUP_NOT_CITED))
            continue
        group = by_g.get(ghash)
        if group is None:
            problems.append("row %d: %s (%s)" % (i, GROUP_NOT_CITED,
                                                 ghash[:12]))
            continue
        if _s(group.get("Fill_Conditioning_Shape")) \
                != _s(row.get("Fill_Conditioning_Shape")):
            problems.append("row %d: %s - the group it cites is the %s group and "
                            "this mark is a %s"
                            % (i, GROUP_NOT_CITED,
                               _s(group.get("Fill_Conditioning_Shape")),
                               _s(row.get("Fill_Conditioning_Shape"))))
            continue
        for column in MRT.GROUP_EVIDENCE:
            if column in ("Fill_Conditioning_Shape", "Fill_Group_Margin"):
                continue
            said, mine = _number(row.get(column)), _number(group.get(column))
            if isinstance(said, (int, float)) and isinstance(mine, (int, float)):
                if abs(float(said) - float(mine)) > 1e-4:
                    problems.append("row %d: %s - %s is %s on the point and %s "
                                    "in the group it cites"
                                    % (i, GROUP_NOT_CITED, column, said, mine))
            elif _s(said) != _s(mine):
                problems.append("row %d: %s - %s is %r on the point and %r in "
                                "the group it cites"
                                % (i, GROUP_NOT_CITED, column, _s(said),
                                   _s(mine)))
    return problems


def point_file_sha256(rows):
    """Over the whole file, so a row removed is a different file.

    The point SET hash in an association covers the points it was computed
    from; this covers the FILE, including points no association used. A row
    deleted from a file nothing has summarised yet leaves every remaining hash
    valid, and this is what disagrees.
    """
    return hashlib.sha256(json.dumps(
        [[_s(r.get(c)) for c in POINT_ARTIFACT_COLUMNS] for r in rows],
        sort_keys=False).encode("utf-8")).hexdigest()


def current_evidence_failures(rows, image, panel_box, series, threshold=150,
                              exclude_boxes=()):
    """Every row whose recorded evidence the raster does not support NOW.

    THE ONLY CHECK HERE THAT OPENS THE FIGURE. The hashes prove a file is
    internally consistent and say nothing about whether anything was ever
    measured: a producer with an editor can write eighteen plausible numbers,
    stamp them, and pass every other verifier in this package. Routing the panel
    again and comparing is the check that cannot be satisfied by writing.

    Five kinds of finding, and they are different acts:

        DUPLICATE_POINT_RECORD         two rows are the same point. Found before
                                       the raster is consulted at all: a file
                                       holding one mark twice is wrong about
                                       itself.
        NO_MARK_AT_THIS_PIXEL_NOW      a row's pixel has no candidate mark within
                                       a quarter of a marker. The point was
                                       invented, or the image is not the one it
                                       was read on.
        ROUTED_MARK_MISSING_FROM_...   the raster routes a mark this file does
                                       not carry.
        THE_PANEL_NO_LONGER_SEPARATES  the split a row's class rests on does not
                                       hold on this raster. Nothing about the
                                       row is provably wrong; the ground it
                                       stood on is gone.
        ROUTING_EVIDENCE_DOES_NOT_...  the mark is there and its measurements
                                       are not the ones recorded.

    ## A SET, NOT A BAG OF INDEPENDENT ROWS. v9.17.

    Until v9.17 each row found its own nearest current mark, on its own. Nothing
    asked whether ONE mark had answered for TWO rows, and nothing asked whether a
    mark the raster routes had a row at all - so a producer could drop mark B,
    write mark A's row twice, re-derive both hashes, recompute the association
    over the file it had just made and the file hash over that, and every check
    in this package agreed with it. Both rows sat on a real marker. The cloud was
    not the figure's.

    So the rows and the currently routed marks are matched ONE-TO-ONE, by the
    same minimum-cost maximum matching the fixture scorer is judged with -
    `marker_routing.match_one_to_one` - and both sides' leftovers are findings.

    ## THE SPLIT IT ASKS ABOUT IS THE ONE THAT NAMED THE ROW. v9.17.

    Since v9.16 a mark's fill comes from the split taken inside ITS OWN measured
    shape, and this function was still asking whether the PANEL-WIDE fill split
    holds - the v9.15 grain, left behind. `split_grain_group_only.jpeg` is the
    panel that shows what that costs: its panel-wide split does not separate and
    both of its shape groups do, so a perfectly good thirty-row file came back
    thirty times `THE_PANEL_NO_LONGER_SEPARATES`. The question is now asked of
    the group named on the row.

    Matching is done against every SINGLE_MARKER candidate rather than against
    the routed ones only, for the same reason: when a group stops separating its
    marks stop being routed, and a row would then be told "there is no mark here"
    when the mark is there and it is the GROUND that went.

    Returns a list of `(row index, code, detail)`; a finding about the panel
    rather than about one row carries `None` for the index. It does NOT raise: a
    run on a different OpenCV can move a third harmonic in the fourth decimal,
    and the caller is the one that knows whether that matters.
    """
    declared = [dict(id=_s(r.get("Series_ID")),
                     shape=_s(r.get("Marker_Shape")).upper(),
                     fill=_s(r.get("Marker_Fill")).upper())
                for r in series]
    out = MRT.route(image, panel_box, declared, threshold=threshold,
                    exclude_boxes=exclude_boxes)
    scale = out["marker_scale_px"] or 1.0
    # EVERY MARK THE PANEL STILL SAYS IS ONE MARKER, not only the routed ones.
    candidates = [r for r in out["records"]
                  if _s(r.get("Marker_Validity_Status")) == AG.SINGLE_MARKER]
    routed_now = [r for r in candidates if r.get("Series_ID")]
    found = []
    seen = {}
    for i, row in enumerate(rows):
        key = _s(row.get("Point_Record_SHA256"))
        if key and key in seen:
            found.append((i, DUPLICATE_POINT,
                          "this row is row %d again: one mark cannot be two "
                          "points of a cloud" % seen[key]))
        elif key:
            seen[key] = i
    placed = []
    for i, row in enumerate(rows):
        try:
            placed.append(dict(point_px_x=float(row["point_px_x"]),
                               point_px_y=float(row["point_px_y"]), _row=i))
        except (KeyError, TypeError, ValueError):
            found.append((i, NO_MARK_NOW, "the row carries no pixel"))
    # ONE MARK, ONE ROW. `match_one_to_one` is the scorer this package holds its
    # own reader to; a verifier weaker than that scorer is a verifier a producer
    # can sit between.
    truth = [(j, r["point_px_x"], r["point_px_y"])
             for j, r in enumerate(candidates)]
    pairs = MRT.match_one_to_one(placed, truth, SAME_MARK * scale)
    of_row = {placed[k]["_row"]: candidates[truth[j][0]]
              for k, j in pairs.items()}
    for k, entry in enumerate(placed):
        if k in pairs:
            continue
        found.append((entry["_row"], NO_MARK_NOW,
                      "no unclaimed mark within %.1f px of (%.1f, %.1f)"
                      % (SAME_MARK * scale, entry["point_px_x"],
                         entry["point_px_y"])))
    matched = {id(candidates[truth[j][0]]) for j in pairs.values()}
    for r in routed_now:
        if id(r) not in matched:
            found.append((None, MARK_MISSING,
                          "the raster routes %s at (%.1f, %.1f) and no row of "
                          "this file carries it"
                          % (_s(r.get("Series_ID")) or "a mark",
                             r["point_px_x"], r["point_px_y"])))
    for i, row in enumerate(rows):
        mark = of_row.get(i)
        if mark is None:
            continue
        # THE GROUP THAT NAMED THIS ROW, asked of the panel as it stands now -
        # and ONLY the gate this mark's own method rests on. A mark named by its
        # SHAPE alone did not consult a fill split, and a shape drawn with one
        # fill usually has no fill split to consult: requiring one of every row
        # refused the shape-only routes v9.17 had just made honest.
        shape = _s(mark.get("shape")) or _s(row.get("Fill_Conditioning_Shape"))
        group = (out.get("fill_groups") or {}).get(shape)
        group_ok = bool(group and group["split"]["separates"])
        method = _s(mark.get("Identity_Method"))
        needs_shape = method in ("MEASURED_MARKER_SHAPE_FILL",
                                 "MEASURED_MARKER_SHAPE")
        needs_fill = method in ("MEASURED_MARKER_SHAPE_FILL",
                                "MEASURED_MARKER_FILL")
        if (needs_shape and not out["shape_split"]["separates"]) \
                or (needs_fill and not group_ok):
            found.append((i, SPLIT_GONE,
                          "this row was named by %s; the panel now separates "
                          "shape=%s and the %s fill group %s"
                          % (method or "an unnamed method",
                             out["shape_split"]["separates"], shape or "?",
                             "separates" if group_ok else "does not")))
            continue
        # AND WHOSE MARK IS IT NOW. `Series_ID` and `Identity_Method` are not
        # routing evidence - they are what the evidence CONCLUDES - so the
        # comparison below would never have reached them, and a same-axis swap
        # sat behind exactly that gap.
        wrong = []
        for column in ROUTE_COLUMNS:
            if _s(row.get(column)) != _s(mark.get(column)):
                wrong.append("%s recorded %r, the ink routes this mark to %r"
                             % (column, _s(row.get(column)),
                                _s(mark.get(column))))
        want = AG.routing_evidence(mark)
        drifted = []
        for column in AG.ROUTING_EVIDENCE:
            if column in PANEL_DIAGNOSTICS:
                # A PANEL-WIDE NUMBER THIS ROW'S ROUTE DOES NOT REST ON.
                # Compared, and reported under its own code below.
                said = _number(row.get(column))
                got = want.get(column)
                if isinstance(said, (int, float)) and isinstance(got, (int, float)):
                    if abs(float(said) - float(got)) > 1e-4:
                        drifted.append("%s recorded %s, the ink says %.4f"
                                       % (column, said, float(got)))
                elif _s(said) != _s(got):
                    drifted.append("%s recorded %r, the ink says %r"
                                   % (column, _s(said), _s(got)))
                continue
            said = _number(row.get(column))
            got = want.get(column)
            if isinstance(said, (int, float)) and isinstance(got, (int, float)):
                if abs(float(said) - float(got)) > 1e-4:
                    wrong.append("%s recorded %s, the ink says %.4f"
                                 % (column, said, float(got)))
            elif _s(said) != _s(got):
                wrong.append("%s recorded %r, the ink says %r"
                             % (column, _s(said), _s(got)))
        if wrong:
            found.append((i, EVIDENCE_STALE, "; ".join(wrong)))
        elif drifted:
            found.append((i, DIAGNOSTIC_STALE, "; ".join(drifted)))
    return found
