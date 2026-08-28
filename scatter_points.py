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
carries the eighteen measurements `marker_routing` decided on, the axis it was
read against, and three hashes binding them together.

## THREE DIFFERENT CHECKS, AND ONLY THE THIRD LOOKS AT THE FIGURE

    verify_artifact            the file against ITSELF - every hash covers what
                               it carries, every value follows from its pixel
                               under the axis it cites, and no point sits under
                               a series the manifest does not put on that axis.
    axis_grain.verify_points   the same, at the record level, plus the marker
                               validity the routing rested on.
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
    "Routing_Evidence_SHA256", "Point_Record_SHA256",
)

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
        if source is not None:
            rec[source] = _number(row.get(column))
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
        # THE GROUP THAT NAMED THIS ROW, asked of the panel as it stands now.
        # The shape axis is still a panel-wide question and the fill axis is
        # not, which is the whole of v9.16 said once more here.
        shape = _s(mark.get("shape")) or _s(row.get("Fill_Conditioning_Shape"))
        group = (out.get("fill_groups") or {}).get(shape)
        group_ok = bool(group and group["split"]["separates"])
        if not out["shape_split"]["separates"] or not group_ok:
            found.append((i, SPLIT_GONE,
                          "this panel now separates shape=%s, and the %s fill "
                          "group %s"
                          % (out["shape_split"]["separates"], shape or "?",
                             "separates" if group_ok else "does not")))
            continue
        wrong = []
        want = AG.routing_evidence(mark)
        for column in AG.ROUTING_EVIDENCE:
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
    return found
