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

CALS = AG.calibrations(AXES)
POINTS = [dict(Series_ID=sid, series=sid, point_px_x=cx, point_px_y=cy,
               Identity_Method="FIXTURE_DECLARED")
          for sid, spec in sorted(R["series"].items())
          for cx, cy in spec["centres"]]
STAMPED = AG.stamp_points(POINTS, _axis_of, CALS, "X_BOTTOM", PANEL, IMAGE_SHA)

print()
print("what reading a series on the wrong axis costs, measured")
# THE CLAIM THE GRAIN RESTS ON. Every right-hand point read against the
# left-hand calibration comes back on a scale nothing in the figure uses, and
# the two differ by the ratio the fixture was drawn with.
_wrong = AG.stamp_points(
    [p for p in POINTS if _axis_of[p["Series_ID"]] == "Y_RIGHT"],
    {sid: "Y_LEFT" for sid in _axis_of}, CALS, "X_BOTTOM", PANEL, IMAGE_SHA)
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
      AG.verify_points(STAMPED, CALS, "X_BOTTOM", PANEL, IMAGE_SHA) == [],
      "%r" % (AG.verify_points(STAMPED, CALS, "X_BOTTOM", PANEL, IMAGE_SHA)[:3],))
# A POINT WHOSE SERIES NAMES NO AXIS IS NOT CALIBRATED AT ALL. Not calibrated
# against a default: a value on an unknown scale is what this module exists to
# prevent.
_orphan = AG.stamp_points([dict(POINTS[0], Series_ID="S_UNKNOWN")], _axis_of,
                          CALS, "X_BOTTOM", PANEL, IMAGE_SHA)[0]
check("  a point whose series has no axis gets no value and no hash",
      _orphan["y_value"] is None and not _orphan["Point_Record_SHA256"]
      and _orphan["refusal"] == AG.UNKNOWN_AXIS,
      "%r" % ({k: _orphan[k] for k in ("y_value", "refusal")},))

print()
print("a recalibrated axis moves the hashes of ITS points and no others")
# THE PROPERTY A TWIN-AXIS FIGURE NEEDS MOST: half its points are read under
# each scale, so a change to one scale must be visible on exactly half.
_moved = AG.calibrations([AXES[0], AXES[1],
                          dict(AXES[2], Calibration_Points=[[20, 449], [90, 61]])])
_after = AG.stamp_points(POINTS, _axis_of, _moved, "X_BOTTOM", PANEL, IMAGE_SHA)
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
_same_cals = AG.calibrations(_TWIN_SAME)
_one = dict(POINTS[0], Series_ID="S")
_on_a = AG.stamp_points([_one], {"S": "Y_A"}, _same_cals, "X_BOTTOM", PANEL,
                        IMAGE_SHA)[0]
_on_b = AG.stamp_points([_one], {"S": "Y_B"}, _same_cals, "X_BOTTOM", PANEL,
                        IMAGE_SHA)[0]
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
