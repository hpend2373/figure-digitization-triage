# -*- coding: utf-8 -*-
"""Two y axes on one panel, and a point that says which it was read on.

    python3 test_axis_grain.py     # exit 0 = all scenarios pass

`Panel_ID` was doing two jobs. Publication 464 Figure 2 prints two y scales over
one panel, the proposer reads one ladder on it, and until `axis_grain` there was
no way to say the second scale exists: either the figure becomes two pretend
panels or one axis is lost, and both are a wrong number rather than a missing
one.

Everything here runs in a fresh clone. The geometry comes from
`twin_scatter_truth.json` - drawn by `make_twin_scatter_fixture.py`, whose two
calibrations differ by 2.80 on purpose - and the series membership comes from
that file's own declaration rather than from a reader: `marker_routing` refuses
the shape axis on a two-shape panel, so nothing here pretends the routing is
solved. The points are labelled `FIXTURE_DECLARED`, which is not in
`provenance.IDENTITY_METHODS` and therefore prices at the highest tier - no
value derived here could be finalized, which is correct for a fixture.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import axis_grain as AG                                           # noqa: E402
import mark_readers as MR                                         # noqa: E402
import provenance as PV                                           # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


DOC = json.load(open(os.path.join(HERE, "twin_scatter_truth.json"),
                     encoding="utf-8"))
R = DOC["renderings"]["s3"]
PANEL = "TWIN_S3"
IMAGE_SHA = "f" * 64                       # the fixture's identity, not a claim

AXES = [
    dict(Axis_ID="X_BOTTOM", Panel_ID=PANEL, Dimension="X", Side="BOTTOM",
         Unit="cm H2O", Scale="LINEAR", Calibration_Points=R["x_ticks"]),
    dict(Axis_ID="Y_LEFT", Panel_ID=PANEL, Dimension="Y", Side="LEFT",
         Unit="mmHg/L/min", Scale="LINEAR", Calibration_Points=R["left_y_ticks"]),
    dict(Axis_ID="Y_RIGHT", Panel_ID=PANEL, Dimension="Y", Side="RIGHT",
         Unit="index", Scale="LINEAR", Calibration_Points=R["right_y_ticks"]),
]
SERIES = [dict(Series_ID=sid,
               Axis_ID=("Y_LEFT" if spec["axis"] == "LEFT" else "Y_RIGHT"))
          for sid, spec in sorted(R["series"].items())]

print("an axis manifest says which side each scale is printed on")
check("the fixture's three axes validate",
      AG.validate_axes(AXES) == [], "%r" % (AG.validate_axes(AXES),))
# THE RULE THAT MATTERS. Two y scales on one panel, both declared LEFT: the
# manifest then holds two calibrations nothing can tell apart, and a reader
# picks - which is how a splanchnic index gets published on a peripheral
# resistance scale.
_same_side = [dict(AXES[1]), dict(AXES[2], Side="LEFT")]
check("  two y axes on one panel and one side are refused",
      any("cannot be told apart" in p for p in AG.validate_axes(_same_side)),
      "%r" % (AG.validate_axes(_same_side),))
check("  an axis with one calibration point is refused",
      any("needs two" in p for p in
          AG.validate_axes([dict(AXES[1], Calibration_Points=[[10, 450]])])),
      "%r" % (AG.validate_axes([dict(AXES[1], Calibration_Points=[[10, 450]])]),))
check("  and a Y axis declared on the BOTTOM is refused",
      any("is on LEFT or RIGHT" in p for p in
          AG.validate_axes([dict(AXES[1], Side="BOTTOM")])),
      "%r" % (AG.validate_axes([dict(AXES[1], Side="BOTTOM")]),))

print()
print("a LOG10 axis is fitted as a log, and was not")
# THREE DECADES AT EQUAL PIXEL SPACING. On a log axis the middle tick is 10; on
# the straight line that `calibrations` used to fit through the same points it
# is 50.5, and nothing complained, because two points fit any straight line
# exactly and the residual of a three-point fit was never looked at either.
_DECADE = [AXES[0],
           dict(Axis_ID="Y_LOG", Panel_ID=PANEL, Dimension="Y", Side="LEFT",
                Unit="pg/mL", Scale="LOG10",
                Calibration_Points=[[1, 400], [10, 300], [100, 200]])]
_log = AG.calibrations(_DECADE)["Y_LOG"]
check("the middle of 1-10-100 at equal spacing reads 10, not 50.5",
      abs(_log.pixel_to_value(300) - 10.0) < 1e-6,
      "%.4f" % _log.pixel_to_value(300))
check("  and the fit is a log fit, with no residual over three decades",
      _log.scale == "LOG" and _log.max_residual < 1e-9,
      "%r %.3g" % (_log.scale, _log.max_residual))
# REVERT: declare the same axis LINEAR, which is what `calibrations` did to
# every axis whatever its manifest said. The middle decade then reads 37.0 from
# three ticks and 50.5 from the two end ticks - both published without a murmur,
# the second with a residual of exactly zero.
_lin = AG.calibrations([AXES[0], dict(_DECADE[1], Scale="LINEAR")])["Y_LOG"]
_lin2 = AG.calibrations([AXES[0], dict(_DECADE[1], Scale="LINEAR",
                                       Calibration_Points=[[1, 400], [100, 200]])
                         ])["Y_LOG"]
check("  declared LINEAR the same ticks read 37.0 there, and 50.5 from two",
      abs(_lin.pixel_to_value(300) - 37.0) < 1e-6
      and abs(_lin2.pixel_to_value(300) - 50.5) < 1e-6
      and _lin2.max_residual < 1e-9,
      "%.4f / %.4f" % (_lin.pixel_to_value(300), _lin2.pixel_to_value(300)))
check("  a LOG10 axis calibrated at zero is refused before the fit",
      any("not a number" in p for p in AG.validate_axes(
          [dict(_DECADE[1], Calibration_Points=[[0, 400], [100, 200]])])),
      "%r" % (AG.validate_axes(
          [dict(_DECADE[1], Calibration_Points=[[0, 400], [100, 200]])]),))
check("  and a calibration point that is not finite is refused",
      any("finite" in p for p in AG.validate_axes(
          [dict(AXES[1], Calibration_Points=[[10, 450], [float("nan"), 60]])])),
      "%r" % (AG.validate_axes(
          [dict(AXES[1], Calibration_Points=[[10, 450], [float("nan"), 60]])]),))

_axis_of, _refused = AG.series_axis(SERIES, AXES)
check("every series names an axis the manifest declares",
      _axis_of and not _refused, "%r %r" % (_axis_of, _refused))
check("  a series naming no axis is refused, not defaulted",
      AG.series_axis([dict(Series_ID="S")], AXES)[1] == {"S": AG.UNKNOWN_AXIS},
      "%r" % (AG.series_axis([dict(Series_ID="S")], AXES)[1],))
check("  and one naming an axis nobody declared is refused too",
      AG.series_axis([dict(Series_ID="S", Axis_ID="Y_MIDDLE")], AXES)[1]
      == {"S": AG.FOREIGN_AXIS},
      "%r" % (AG.series_axis([dict(Series_ID="S", Axis_ID="Y_MIDDLE")], AXES)[1],))
# EXISTING IS NOT BEING THE RIGHT AXIS. The manifest holds the x axis too, and a
# series pointed at X_BOTTOM used to validate cleanly while every y value came
# off the horizontal scale - the exact failure the module was written to stop,
# reached through the front door.
check("  a series pointed at the X axis is refused by role",
      AG.series_axis([dict(Series_ID="S", Axis_ID="X_BOTTOM")], AXES)[1]
      == {"S": AG.WRONG_DIMENSION},
      "%r" % (AG.series_axis([dict(Series_ID="S", Axis_ID="X_BOTTOM")], AXES)[1],))
_other = AXES + [dict(Axis_ID="Y_LEFT_P2", Panel_ID="OTHER", Dimension="Y",
                      Side="LEFT", Unit="mmHg", Scale="LINEAR",
                      Calibration_Points=R["left_y_ticks"])]
check("  and one pointed at another panel's axis is refused too",
      AG.series_axis([dict(Series_ID="S", Axis_ID="Y_LEFT_P2")], _other,
                     panel_id=PANEL)[1] == {"S": AG.WRONG_PANEL},
      "%r" % (AG.series_axis([dict(Series_ID="S", Axis_ID="Y_LEFT_P2")], _other,
                             panel_id=PANEL)[1],))
# AND THE X AXIS ITSELF IS CHECKED, not taken on trust from its name.
_A_POINT = dict(Series_ID=sorted(_axis_of)[0], point_px_x=400.0, point_px_y=300.0,
                Identity_Method="FIXTURE_DECLARED")
try:
    AG.stamp_points([_A_POINT], SERIES, AXES, "Y_LEFT", PANEL, IMAGE_SHA)
    _xrole = ""
except ValueError as exc:
    _xrole = "%s" % exc
check("  and stamping against a Y axis as if it were X is refused",
      AG.X_WRONG_DIMENSION in _xrole, "%r" % (_xrole,))
try:
    AG.stamp_points([_A_POINT], SERIES, _other + [
        dict(AXES[0], Axis_ID="X_P2", Panel_ID="OTHER")], "X_P2", PANEL, IMAGE_SHA)
    _xpanel = ""
except ValueError as exc:
    _xpanel = "%s" % exc
check("  as is one belonging to another panel",
      AG.X_WRONG_PANEL in _xpanel, "%r" % (_xpanel,))

CALS = AG.calibrations(AXES)
RECS = AG.axis_records(AXES)
POINTS = [dict(Series_ID=sid, series=sid, point_px_x=cx, point_px_y=cy,
               Identity_Method="FIXTURE_DECLARED")
          for sid, spec in sorted(R["series"].items())
          for cx, cy in spec["centres"]]
STAMPED = AG.stamp_points(POINTS, SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)

print()
print("what reading a series on the wrong axis costs, measured")
# THE CLAIM THE GRAIN RESTS ON. Every right-hand point read against the
# left-hand calibration comes back on a scale nothing in the figure uses, and
# the two differ by the ratio the fixture was drawn with.
_wrong = AG.stamp_points(
    [p for p in POINTS if _axis_of[p["Series_ID"]] == "Y_RIGHT"],
    [dict(Series_ID=sid, Axis_ID="Y_LEFT") for sid in _axis_of], AXES,
    "X_BOTTOM", PANEL, IMAGE_SHA)
_right = [r for r in STAMPED if r["Axis_ID"] == "Y_RIGHT"]
_ratio = [w["y_value"] / r["y_value"] for w, r in zip(_wrong, _right)]
check("the right-hand series on the left calibration is wrong by 0.3 to 0.4x",
      all(0.25 < v < 0.45 for v in _ratio),
      "%r" % [round(v, 3) for v in _ratio[:4]])
check("  and the two declared calibrations differ by 2.80",
      abs(CALS["Y_RIGHT"].slope / CALS["Y_LEFT"].slope - 2.80) < 0.05,
      "%.3f" % (CALS["Y_RIGHT"].slope / CALS["Y_LEFT"].slope))

print()
print("every point carries its axis and its own hash")
check("all %d points are calibrated and hashed" % len(POINTS),
      all(r["Axis_ID"] and r["Point_Record_SHA256"] and r["y_value"] is not None
          for r in STAMPED), "%d of %d" % (
          sum(1 for r in STAMPED if r["Point_Record_SHA256"]), len(STAMPED)))
check("  and every one of them re-derives from its own pixel",
      AG.verify_points(STAMPED, SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA) == [],
      "%r" % (AG.verify_points(STAMPED, SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)[:3],))
# A POINT WHOSE SERIES NAMES NO AXIS IS NOT CALIBRATED AT ALL. Not calibrated
# against a default: a value on an unknown scale is what this module exists to
# prevent.
_orphan = AG.stamp_points([dict(POINTS[0], Series_ID="S_UNKNOWN")], SERIES,
                          AXES, "X_BOTTOM", PANEL, IMAGE_SHA)[0]
check("  a point whose series has no axis gets no value and no hash",
      _orphan["y_value"] is None and not _orphan["Point_Record_SHA256"]
      and _orphan["refusal"] == AG.UNKNOWN_AXIS,
      "%r" % ({k: _orphan[k] for k in ("y_value", "refusal")},))

print()
print("a recalibrated axis moves the hashes of ITS points and no others")
# THE PROPERTY A TWIN-AXIS FIGURE NEEDS MOST: half its points are read under
# each scale, so a change to one scale must be visible on exactly half.
_moved = [AXES[0], AXES[1],
          dict(AXES[2], Calibration_Points=[[20, 449], [90, 61]])]
_after = AG.stamp_points(POINTS, SERIES, _moved, "X_BOTTOM", PANEL, IMAGE_SHA)
_left_same = all(a["Point_Record_SHA256"] == b["Point_Record_SHA256"]
                 for a, b in zip(STAMPED, _after) if a["Axis_ID"] == "Y_LEFT")
_right_moved = all(a["Point_Record_SHA256"] != b["Point_Record_SHA256"]
                   for a, b in zip(STAMPED, _after) if a["Axis_ID"] == "Y_RIGHT")
check("recalibrating the right axis changes every right point's hash",
      _right_moved, "some right-hand hashes did not move")
check("  and leaves every left point's hash alone", _left_same,
      "a left-hand hash moved")

# AND THE AXIS ID IS IN THE HASH, which only matters when two axes carry the
# SAME numbers - a figure printing 0-100 up both sides for two different
# quantities. Then one pixel means two things, the calibration records are
# identical, and the Axis_ID is the only thing that separates the records.
# Without this scenario, dropping Axis_ID from the hash broke nothing: the
# fixture's two scales differ, so their calibration records already differed.
_TWIN_SAME = [AXES[0],
              dict(AXES[1], Axis_ID="Y_A", Unit="mmHg",
                   Calibration_Points=R["left_y_ticks"]),
              dict(AXES[2], Axis_ID="Y_B", Unit="beats/min",
                   Calibration_Points=R["left_y_ticks"])]
_one = dict(POINTS[0], Series_ID="S")
_on_a = AG.stamp_points([_one], [dict(Series_ID="S", Axis_ID="Y_A")], _TWIN_SAME,
                        "X_BOTTOM", PANEL, IMAGE_SHA)[0]
_on_b = AG.stamp_points([_one], [dict(Series_ID="S", Axis_ID="Y_B")], _TWIN_SAME,
                        "X_BOTTOM", PANEL, IMAGE_SHA)[0]
check("two axes with the same numbers still hash their points apart",
      _on_a["Point_Record_SHA256"] != _on_b["Point_Record_SHA256"]
      and abs(_on_a["y_value"] - _on_b["y_value"]) < 1e-9,
      "same hash %s, same value %s"
      % (_on_a["Point_Record_SHA256"] == _on_b["Point_Record_SHA256"],
         _on_a["y_value"] == _on_b["y_value"]))

print()
print("an association cites the points it was computed from, by hash")
_by_series = {}
for r in STAMPED:
    _by_series.setdefault(r["Series_ID"], []).append(r)
_assoc = {sid: AG.association_over_points(rows)
          for sid, rows in sorted(_by_series.items())}
check("each series' r is the r its own points give",
      all(abs(_assoc[sid]["Association_Value"]
              - R["series"][sid]["pearson_r"]) < 0.02 for sid in _assoc),
      "%r" % {sid: round(_assoc[sid]["Association_Value"], 4) for sid in _assoc})
check("  and each cites exactly its own point hashes, in order",
      all(_assoc[sid]["Point_Record_SHA256_List"]
          == [r["Point_Record_SHA256"] for r in _by_series[sid]]
          for sid in _assoc),
      "a cited list is not the cloud's own")
# DROP ONE POINT and the set hash moves, even though every surviving point still
# hashes correctly. That is the gap an association citing a FILE could not see.
_short = dict(_by_series)
_sid = sorted(_by_series)[0]
_short_assoc = AG.association_over_points(_by_series[_sid][:-1])
check("  dropping one point changes the set hash",
      _short_assoc["Point_Set_SHA256"] != _assoc[_sid]["Point_Set_SHA256"]
      and _short_assoc["N_Pairs"] == _assoc[_sid]["N_Pairs"] - 1,
      "%s vs %s" % (_short_assoc["Point_Set_SHA256"][:12],
                    _assoc[_sid]["Point_Set_SHA256"][:12]))
# AND MIXING TWO AXES INTO ONE CLOUD IS REFUSED. Not because r cannot be
# computed - it can, and that is the danger - but because the y values are not
# measurements of one quantity.
try:
    AG.association_over_points(STAMPED)
    _mixed = ""
except ValueError as exc:
    _mixed = "%s" % exc
check("  and an association over two axes at once is refused",
      "needs one" in _mixed, "%r" % (_mixed,))
try:
    AG.association_over_points([_orphan])
    _nov = ""
except ValueError as exc:
    _nov = "%s" % exc
check("  as is one over a point that carries no value",
      "different cloud" in _nov, "%r" % (_nov,))

print()
print("and so is an association over two series that share one axis")
# THE AXIS RULE IS ARITHMETIC; THIS ONE IS NOT. The open circles and the filled
# circles are both read on Y_LEFT, so an r over the two together computes
# perfectly and answers about neither group. It was computed, and nothing said
# so: `Series_ID` simply held two values in a column nobody joined on.
_left = [r for r in STAMPED if r["Axis_ID"] == "Y_LEFT"]
_left_series = sorted({r["Series_ID"] for r in _left})
try:
    AG.association_over_points(_left)
    _two = ""
except ValueError as exc:
    _two = "%s" % exc
check("two series on one axis are refused, and the codes name both",
      AG.MULTIPLE_SERIES in _two and len(_left_series) == 2
      and all(sid in _two for sid in _left_series),
      "%r" % (_two,))
_decl = {"Aggregation_Method": "POOLED_ACROSS_SERIES",
         "Aggregation_Series_IDs": ", ".join(_left_series),
         "Aggregation_Justification":
             "both series are the same subjects before and after tilt"}
_pooled = AG.association_over_points(_left, aggregation=_decl)
check("  a caller that declares the pooling gets it, with the reason attached",
      all(_pooled[c] == _decl[c] for c in AG.AGGREGATION_COLUMNS)
      and _pooled["N_Pairs"] == len(_left) and _pooled["Series_ID"] == "",
      "%r" % ({c: _pooled[c] for c in AG.AGGREGATION_COLUMNS},))
# A DECLARATION THAT DOES NOT MATCH THE CLOUD IS NOT A DECLARATION. Naming one
# series and handing over two is how a pooling gets waved through by a form.
try:
    AG.association_over_points(_left, aggregation=dict(
        _decl, Aggregation_Series_IDs=_left_series[0]))
    _mis = ""
except ValueError as exc:
    _mis = "%s" % exc
check("  and one naming the wrong series is refused",
      AG.MULTIPLE_SERIES in _mis and "the points are" in _mis, "%r" % (_mis,))
check("  a single-series association still names its series",
      _assoc[_sid]["Series_ID"] == _sid
      and all(_assoc[_sid][c] == "" for c in AG.AGGREGATION_COLUMNS),
      "%r" % (_assoc[_sid]["Series_ID"],))

print()
print("the point hash covers whose the point is, not only where it is")
# THE MUTATION. Swap `Series_ID` between two points read on the SAME axis and
# change nothing else: the pixels, the values, the calibration and the axis are
# all untouched, so the first version of this hash still verified both and two
# clouds had quietly exchanged a member each.
_swap = [dict(r) for r in STAMPED]
_a = next(i for i, r in enumerate(_swap) if r["Series_ID"] == _left_series[0])
_b = next(i for i, r in enumerate(_swap) if r["Series_ID"] == _left_series[1])
_swap[_a]["Series_ID"], _swap[_b]["Series_ID"] = (_swap[_b]["Series_ID"],
                                                  _swap[_a]["Series_ID"])
_bad = dict(AG.verify_points(_swap, SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA))
check("swapping two same-axis points' series refuses both of them",
      _a in _bad and _b in _bad
      and all("hash does not cover" in _bad[i] for i in (_a, _b))
      and len(_bad) == 2,
      "%r" % (sorted(_bad.items())[:4],))
# AND THE ROUTING EVIDENCE IS RE-MEASURED FROM THE RECORD, so a producer that
# rewrites a mark's shape and re-stamps the point does not get a clean bill.
_ROUTED = dict(Series_ID=_left_series[0], point_px_x=400.0, point_px_y=300.0,
               Identity_Method="MEASURED_MARKER_SHAPE_FILL", shape="CIRCLE",
               fill="OPEN", third_harmonic=0.041, interior_ink=0.07,
               shape_threshold=0.061, fill_threshold=0.684,
               Original_Component_ID=7, Foreign_Ink_Fraction=0.0,
               marker_scale_px=34.0, side_px=37.0, aspect=1.028,
               size_ratio=1.088, off_centre_ink=0.041,
               off_centre_threshold=0.25, off_centre_margin=0.209,
               Marker_Validity_Status="SINGLE_MARKER")
_stamped_one = AG.stamp_points([_ROUTED], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA)[0]
check("  a routed point's evidence hash covers all ten measurements",
      sorted(AG.routing_evidence(_ROUTED)) == sorted(AG.ROUTING_EVIDENCE)
      and AG.routing_evidence(_ROUTED)["Shape_Margin"] is not None
      and AG.verify_points([_stamped_one], SERIES, AXES, "X_BOTTOM", PANEL,
                           IMAGE_SHA) == [],
      "%r" % (AG.routing_evidence(_ROUTED),))
_lied = dict(_stamped_one, fill="FILLED")
check("  and rewriting the fill after the stamp is caught",
      [m for _i, m in AG.verify_points([_lied], SERIES, AXES, "X_BOTTOM", PANEL,
                                       IMAGE_SHA)] == [
          "routing evidence does not hash to what it carries"],
      "%r" % (AG.verify_points([_lied], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA),))
# A POINT NOTHING ROUTED still has an evidence hash, and it is the hash of ten
# Nones - which is a different hash from any measured mark's, and that is the
# distinction it exists to make.
check("  a declared point hashes as having no evidence, not as having none needed",
      AG.routing_evidence_sha256(dict(Series_ID="S", point_px_x=1, point_px_y=1))
      != AG.routing_evidence_sha256(_ROUTED),
      "a fixture declaration and a measured mark hash the same evidence")

print()
print("a merged blob cannot be laundered into a point")
# THE MUTATION THE REVIEW ASKED FOR, on a REAL record: take the blob
# `marker_routing` refused as MARKER_MERGED on twin_scatter_s3, clear the
# refusal, give it a series and an identity method, and stamp it honestly - both
# hashes recomputed, nothing left inconsistent. Before the marker-validity
# fields were in the evidence, that record verified clean: the numbers that made
# the blob invalid were not covered by anything.
from PIL import Image                                             # noqa: E402
import marker_routing as MRT                                      # noqa: E402
_S3 = DOC["renderings"]["s3"]
_ROUTE = MRT.route(
    Image.open(os.path.join(HERE, _S3["file"])).convert("RGB"), _S3["panel_box"],
    [dict(id=sid, shape=spec["shape"], fill=spec["fill"])
     for sid, spec in sorted(_S3["series"].items())])
_MERGED = [r for r in _ROUTE["records"] if r["refusal"] == "MARKER_MERGED"][0]


def _laundered(**edits):
    p = dict(_MERGED)
    p.update(Series_ID=_left_series[0],
             Identity_Method="MEASURED_MARKER_SHAPE_FILL", refusal="")
    p.update(edits)
    rec = AG.stamp_points([p], SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)[0]
    return AG.verify_points([rec], SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)


check("the blob route refused as merged still verifies as not one marker",
      [m for _i, m in _laundered()]
      and AG.NOT_ONE_MARKER in _laundered()[0][1]
      and "%.4f" % _MERGED["off_centre_ink"] in _laundered()[0][1],
      "%r" % (_laundered(),))
# AND EDITING THE WORD IS NOT ENOUGH. `Marker_Validity_Status` is re-derived
# from the two numbers beside it rather than read.
check("  claiming SINGLE_MARKER over the same numbers is still refused",
      AG.NOT_ONE_MARKER
      in _laundered(Marker_Validity_Status="SINGLE_MARKER")[0][1],
      "%r" % (_laundered(Marker_Validity_Status="SINGLE_MARKER"),))
# AND EDITING ONE NUMBER LEAVES THE OTHER TWO DISAGREEING.
check("  and shrinking the off-centre ink alone leaves the margin wrong",
      "is not" in _laundered(Marker_Validity_Status="SINGLE_MARKER",
                             off_centre_ink=0.04)[0][1],
      "%r" % (_laundered(Marker_Validity_Status="SINGLE_MARKER",
                         off_centre_ink=0.04),))
check("  the evidence covers all eight marker-validity fields",
      set(("Marker_Scale_Px", "Side_Px", "Aspect", "Size_Ratio",
           "Off_Centre_Ink", "Off_Centre_Threshold", "Off_Centre_Margin",
           "Marker_Validity_Status")) <= set(AG.ROUTING_EVIDENCE)
      and AG.routing_evidence(_MERGED)["Off_Centre_Ink"] is not None,
      "%r" % (sorted(AG.ROUTING_EVIDENCE),))
# A ROUTED MARK THAT REALLY WAS ONE MARKER PASSES, so the check is not simply
# refusing everything that carries evidence.
_good = [r for r in _ROUTE["records"] if r["Series_ID"]][0]
_good_rec = AG.stamp_points(
    [dict(_good, Series_ID=_left_series[0])], SERIES, AXES, "X_BOTTOM", PANEL,
    IMAGE_SHA)[0]
check("  and a mark that was one marker verifies clean",
      AG.verify_points([_good_rec], SERIES, AXES, "X_BOTTOM", PANEL,
                       IMAGE_SHA) == [],
      "%r" % (AG.verify_points([_good_rec], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA),))

print()
print("and the axis a point cites is checked where the stamp is made")
# `series_axis` REFUSED A SERIES POINTED AT THE X AXIS AND NOTHING MADE ANYONE
# CALL IT. `stamp_points` took an `axis_of` mapping and believed it, so
# `{"S1": "X_BOTTOM"}` stamped every point with the x calibration used as the y
# scale - hashed, and verified clean. The mapping is now derived here from the
# series manifest, which is the only thing that closes the path.
import inspect                                                    # noqa: E402
check("stamp_points takes the series manifest, not an axis mapping",
      list(inspect.signature(AG.stamp_points).parameters)[:2]
      == ["points", "series_rows"],
      "%r" % (list(inspect.signature(AG.stamp_points).parameters),))
_x_declared = [dict(Series_ID=sid, Axis_ID="X_BOTTOM") for sid in _axis_of]
_on_x = AG.stamp_points(POINTS[:1], _x_declared, AXES, "X_BOTTOM", PANEL,
                        IMAGE_SHA)[0]
check("  a series declared on the x axis gets no value and no hash",
      _on_x["y_value"] is None and not _on_x["Point_Record_SHA256"]
      and _on_x["refusal"] == AG.WRONG_DIMENSION,
      "%r" % ({k: _on_x[k] for k in ("y_value", "refusal")},))
# AND THE RECORD IS CHECKED TOO, because a record can be written past
# `stamp_points` altogether. Here the point is re-hashed AS IF the x axis were
# its y axis - every hash self-consistent - and the verifier still refuses.
_XCAL = AG.calibrations(AXES)["X_BOTTOM"]
_XREC = AG.axis_records(AXES)["X_BOTTOM"]
_forged = dict(STAMPED[0], Axis_ID="X_BOTTOM", Axis_Record_SHA256=_XREC,
               y_value=_XCAL.pixel_to_value(float(STAMPED[0]["point_px_y"])))
_forged["Point_Record_SHA256"] = AG.point_record_sha256(
    _forged, "X_BOTTOM", _XCAL, _XCAL, PANEL, IMAGE_SHA, axis_record=_XREC,
    x_axis_record=_XREC,
    routing_evidence_hash=_forged["Routing_Evidence_SHA256"])
check("  a record re-hashed onto the x axis is refused by role, not by hash",
      [m for _i, m in AG.verify_points([_forged], SERIES, AXES, "X_BOTTOM",
                                       PANEL, IMAGE_SHA)]
      and AG.WRONG_DIMENSION in AG.verify_points(
          [_forged], SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)[0][1],
      "%r" % (AG.verify_points([_forged], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA),))
# AND MOVING A POINT TO THE OTHER Y AXIS - a real Y axis on this panel, so the
# role check passes - disagrees with what its series is declared on.
_YR = AG.calibrations(AXES)["Y_RIGHT"]
_YRREC = AG.axis_records(AXES)["Y_RIGHT"]
_left_point = [r for r in STAMPED if r["Axis_ID"] == "Y_LEFT"][0]
_moved_axis = dict(_left_point, Axis_ID="Y_RIGHT", Axis_Record_SHA256=_YRREC,
                   y_value=_YR.pixel_to_value(float(_left_point["point_px_y"])))
_moved_axis["Point_Record_SHA256"] = AG.point_record_sha256(
    _moved_axis, "Y_RIGHT", _YR, AG.calibrations(AXES)["X_BOTTOM"], PANEL,
    IMAGE_SHA, axis_record=_YRREC,
    x_axis_record=AG.axis_records(AXES)["X_BOTTOM"],
    routing_evidence_hash=_moved_axis["Routing_Evidence_SHA256"])
check("  and one moved to the panel's OTHER y axis disagrees with its series",
      "declared on Y_LEFT" in AG.verify_points(
          [_moved_axis], SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)[0][1],
      "%r" % (AG.verify_points([_moved_axis], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA),))
# AND THE VALUE METHOD IS IN THE HASH AND RE-CHECKED. A scatter point is its
# marker's centre; a record saying otherwise is describing a different reading.
_vm = dict(STAMPED[0], Value_Method="BAR_TOP")
_vm["Point_Record_SHA256"] = AG.point_record_sha256(
    _vm, _vm["Axis_ID"], CALS[_vm["Axis_ID"]], CALS["X_BOTTOM"], PANEL,
    IMAGE_SHA, axis_record=RECS[_vm["Axis_ID"]],
    x_axis_record=RECS["X_BOTTOM"],
    routing_evidence_hash=_vm["Routing_Evidence_SHA256"])
# TWO DIFFERENT FAILURES, and the message says which. Edited WITHOUT re-stamping
# it is the hash that catches it, which is what putting Value_Method inside the
# hash buys; edited WITH a fresh stamp it is the policy - a routed scatter point
# is its marker's centre - that catches it.
_vm_unstamped = dict(STAMPED[0], Value_Method="BAR_TOP")
check("an edited Value_Method breaks the point hash",
      [m for _i, m in AG.verify_points([_vm_unstamped], SERIES, AXES,
                                       "X_BOTTOM", PANEL, IMAGE_SHA)]
      == ["hash does not cover this point"],
      "%r" % (AG.verify_points([_vm_unstamped], SERIES, AXES, "X_BOTTOM",
                               PANEL, IMAGE_SHA),))
check("  and a re-hashed Value_Method is still refused",
      any("Value_Method" in m for _i, m in AG.verify_points(
          [_vm], SERIES, AXES, "X_BOTTOM", PANEL, IMAGE_SHA)),
      "%r" % (AG.verify_points([_vm], SERIES, AXES, "X_BOTTOM", PANEL,
                               IMAGE_SHA),))

print()
print("the set hash is a set")
# IT WAS OVER THE ORDERED LIST WITH `Set` IN ITS NAME. Component labelling is
# what decides the order, so the same reader on the same figure could produce
# two set hashes and disagree with itself about a cloud it had read correctly.
_rev = AG.association_over_points(list(reversed(_by_series[_sid])))
check("reversing the cloud leaves the set hash alone",
      _rev["Point_Set_SHA256"] == _assoc[_sid]["Point_Set_SHA256"],
      "%s vs %s" % (_rev["Point_Set_SHA256"][:12],
                    _assoc[_sid]["Point_Set_SHA256"][:12]))
check("  and the ordered citation still records the order it was given",
      _rev["Point_Record_SHA256_List"]
      == list(reversed(_assoc[_sid]["Point_Record_SHA256_List"])),
      "the ordered list did not follow the order")

print()
print("and the counts reach the row somebody reads")
# AN r OVER NINETEEN POINTS IS SILENT ABOUT THE ELEVEN MARKS THE READER NEVER
# SAW. `marker_routing.route` counts them; without this step the count stops at
# the reader and the association row reads like a complete cloud.
_counts = dict(Expected_Point_Count=30, Candidate_Mark_Record_Count=19,
               Routed_Point_Count=16, Unresolved_Candidate_Count=3,
               Candidate_Count_Agreement="CANDIDATE_COUNT_DISAGREES")
_with = AG.with_completeness(_assoc[_sid], _counts)
check("an association can carry the reader's completeness counts",
      all(_with[k] == v for k, v in _counts.items())
      and _with["Association_Value"] == _assoc[_sid]["Association_Value"],
      "%r" % ({k: _with[k] for k in _counts},))
check("  and says nothing rather than AGREES when nobody counted the page",
      _assoc[_sid]["Candidate_Count_Agreement"] == ""
      and _assoc[_sid]["Expected_Point_Count"] is None,
      "%r" % (_assoc[_sid]["Candidate_Count_Agreement"],))

print()
print("and none of it could be finalized, which is right for a fixture")
# FIXTURE_DECLARED is not in the registry, and an unregistered identity method
# prices at the highest tier by design. A demo cloud that could be pooled would
# be the agent laundering its own declaration into a measurement.
check("FIXTURE_DECLARED prices at the highest tier",
      PV.identity_tier("FIXTURE_DECLARED") == PV.UNKNOWN_TIER
      and PV.UNKNOWN_TIER not in PV.FINALIZABLE_TIERS,
      "%s" % PV.identity_tier("FIXTURE_DECLARED"))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
