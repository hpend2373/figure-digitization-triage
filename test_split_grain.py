# -*- coding: utf-8 -*-
"""Which distribution the fill question is asked of, and what each answer costs.

    python3 test_split_grain.py     # exit 0 = all scenarios pass

`marker_routing` told two monochrome series apart by measuring a marker's shape
and its fill, and it asked BOTH questions of the whole panel at once. The shape
question is right that way - a third harmonic is a third harmonic whatever else
is on the page. The fill question is not, and this file is the measurement that
says so and the fixtures that hold the answer.

## The four bands

Interior ink is read in a window at the mark's centroid. A ring encloses white;
a triangle inscribed in the same box puts two of its own edges through that
window. So a panel drawing rings, discs, hollow triangles and solid triangles
has FOUR bands in one distribution, not two - measured on `twin_scatter_s3.jpeg`
and matched one-to-one against what was drawn:

    CIRCLE   OPEN     0.048 - 0.295
    TRIANGLE OPEN     0.333 - 0.510
    TRIANGLE FILLED   0.857 - 0.932
    CIRCLE   FILLED   1.000

A panel-wide split pools those into two clusters, so the spread it scores as one
cluster's is two clusters'. On every rendering this repository carried before
this round the largest gap was STILL between OPEN and FILLED, because the two
open bands sit closer to each other than to the filled ones - which is why the
grain was wrong in principle and right in every observed case.

## The case where it is wrong in fact

`split_grain_confounded.jpeg` prints its open triangles with the heavier outline
journals use, so their interior ink rises to 0.52-0.62 while fifteen open
circles sit near 0.05. The largest gap in the pooled set is then between the two
OPEN classes. The panel-wide rule takes it, calls all five open triangles
FILLED, and routes them to the filled-triangle series: five values published
under another series' name, each with a plausible number and a coordinate on the
right axis. Asked inside each measured shape the same panel is right about all
twenty-five of its marks.

## What is NOT claimed

That relaxing the minimum class size would have helped. `split_grain_outlier`
draws ONE fill class and two marks a rule crosses; drop the floor to two and the
reader invents a second class and names both of them. Both fixtures are in the
comparison below, and the candidate that wins wins on both.

Publication 464 Figure 2 is not in this file. Its clip is a publisher figure
this repository does not carry, and the numbers this round could measure about
it came from a rendering that is NOT that clip - so they inform the reasoning
and pin nothing. `forward_test_464_scatter.py` still holds what the clip says.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image                                             # noqa: E402

import axis_grain as AG                                           # noqa: E402
import compare_split_grain as CSG                                 # noqa: E402
import diagnose_marker_split as D                                 # noqa: E402
import marker_routing as MRT                                      # noqa: E402
import provenance as PROV                                         # noqa: E402
import scatter_points as SP                                       # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


TRUTH = os.path.join(HERE, "split_grain_truth.json")
if not os.path.exists(TRUTH):                                     # pragma: no cover
    import make_split_grain_fixture as MSG
    MSG.main()
DOC = json.load(open(TRUTH, encoding="utf-8"))


def declared(rendering):
    return [dict(id=d["Series_ID"], shape=d["Marker_Shape"],
                 fill=d["Marker_Fill"]) for d in rendering["declared"]]


def routed(name):
    r = DOC["renderings"][name]
    path = os.path.join(HERE, r["file"])
    if not os.path.exists(path):                                  # pragma: no cover
        import make_split_grain_fixture as MSG
        MSG.main()
    series = declared(r)
    out = MRT.route(Image.open(path).convert("RGB"), r["panel_box"], series,
                    expected_points=r["total_points"])
    truth = [(sid, cx, cy) for sid, s in sorted(r["series"].items())
             for cx, cy in s["centres"]]
    scale = out["marker_scale_px"] or 1.0
    marks = [x for x in out["records"] if x["refusal"] != "NOT_A_MARKER"]
    pair = MRT.match_one_to_one(marks, truth, 0.6 * scale)
    right = wrong = refused = invented = 0
    bands = collections.defaultdict(list)
    for i, x in enumerate(marks):
        j = pair.get(i)
        if j is not None and x["Marker_Validity_Status"] == "SINGLE_MARKER":
            spec = r["series"][truth[j][0]]
            bands[(spec["shape"], spec["fill"])].append(x["interior_ink"])
        if x["refusal"]:
            refused += 1
        elif j is None:
            invented += 1
        elif truth[j][0] == x["Series_ID"]:
            right += 1
        else:
            wrong += 1
    return dict(out=out, series=series, truth=truth, rendering=r, scale=scale,
                marks=marks, right=right, wrong=wrong, refused=refused,
                invented=invented, bands=dict(bands),
                refusals=sorted({x["refusal"] for x in out["records"]
                                 if x["refusal"]}),
                matched=len(pair), drawn=r["total_points"])


R = {name: routed(name) for name in sorted(DOC["renderings"])}

print("interior ink is four bands, and the shape is what separates two of them")
# THE MEASUREMENT THE WHOLE ROUND RESTS ON, taken on the fixture that was here
# BEFORE it - so it is a statement about the reader rather than about a drawing
# made to prove a point.
_twin = json.load(open(os.path.join(HERE, "twin_scatter_truth.json"),
                       encoding="utf-8"))["renderings"]["s3"]
_series = [dict(id=sid, shape=s["shape"], fill=s["fill"])
           for sid, s in sorted(_twin["series"].items())]
_out = MRT.route(Image.open(os.path.join(HERE, _twin["file"])).convert("RGB"),
                 _twin["panel_box"], _series)
_marks = [x for x in _out["records"] if x["refusal"] != "NOT_A_MARKER"]
_truth = [(sid, cx, cy) for sid, s in sorted(_twin["series"].items())
          for cx, cy in s["centres"]]
_pair = MRT.match_one_to_one(_marks, _truth, 0.6 * _out["marker_scale_px"])
_band = collections.defaultdict(list)
for _i, _x in enumerate(_marks):
    _j = _pair.get(_i)
    if _j is None or _x["Marker_Validity_Status"] != "SINGLE_MARKER":
        continue
    _spec = _twin["series"][_truth[_j][0]]
    _band[(_spec["shape"], _spec["fill"])].append(_x["interior_ink"])
check("on twin_scatter_s3 the two OPEN classes do not overlap each other",
      max(_band[("CIRCLE", "OPEN")]) < min(_band[("TRIANGLE", "OPEN")]),
      "circles to %.3f, triangles from %.3f"
      % (max(_band[("CIRCLE", "OPEN")]), min(_band[("TRIANGLE", "OPEN")])))
# AND THE SHAPE GAP INSIDE `OPEN` IS THE SAME SIZE AS THE GAP BETWEEN THE TWO
# FILLS. A difference that large is not noise on the fill axis; it is a second
# variable in it.
_open_span = (max(_band[("TRIANGLE", "OPEN")])
              - min(_band[("CIRCLE", "OPEN")]))
_fill_gap = (min(_band[("TRIANGLE", "FILLED")])
             - max(_band[("TRIANGLE", "OPEN")]))
check("  and the shape's span inside OPEN is comparable with the fill gap",
      _open_span > 0.4 and _fill_gap > 0.3,
      "OPEN spans %.3f, the gap to FILLED is %.3f" % (_open_span, _fill_gap))
check("  so the panel-wide split's within-spread is two clusters', not one's",
      MRT.separation_index(MRT.Split(**_out["fill_split"]))
      < min(MRT.separation_index(MRT.Split(**_out["fill_groups"][s]["split"]))
            for s in ("CIRCLE", "TRIANGLE")),
      "panel %.2f, groups %r"
      % (MRT.separation_index(MRT.Split(**_out["fill_split"])),
         {s: _out["fill_groups"][s]["index"] for s in ("CIRCLE", "TRIANGLE")}))

print()
print("a panel where the pooled gap falls between two SHAPES, not two fills")
_c = R["confounded"]
check("the confounded panel routes all 25 of its marks, none of them wrong",
      (_c["right"], _c["wrong"], _c["refused"]) == (25, 0, 0),
      "%d right, %d wrong, %d refused" % (_c["right"], _c["wrong"],
                                          _c["refused"]))
# REVERT: ask the fill question of the whole panel, which is what this module
# did until v9.16. Five open triangles are then routed to the filled-triangle
# series. This is the scenario the change exists for, and it is measured by
# re-running the same records under the old rule rather than by describing it.
_was, _splits, _unstable = CSG.assign(_c["out"]["records"], _c["series"],
                                      "CURRENT_GLOBAL")
_old_wrong = 0
for _i, _rec in enumerate(_c["out"]["records"]):
    _name = _was.get(_i, ("", "", ""))[1]
    if not _name:
        continue
    _k = _c["marks"].index(_rec) if _rec in _c["marks"] else None
    _j = _pair_j = None
    if _k is not None:
        _j = MRT.match_one_to_one(_c["marks"], _c["truth"],
                                  0.6 * _c["scale"]).get(_k)
    if _j is None or _c["truth"][_j][0] != _name:
        _old_wrong += 1
check("  and the panel-wide rule puts five of them under another series' name",
      _old_wrong == 5, "%d misrouted under the panel-wide split" % _old_wrong)
check("  the panel-wide split is still recorded, and it is the wrong line",
      _c["out"]["fill_split"]["separates"]
      and 0.2 < float(_c["out"]["fill_split"]["threshold"]) < 0.5,
      "%r" % (_c["out"]["fill_split"],))
check("  each shape's own split separates, and by a wider index",
      all(_c["out"]["fill_groups"][s]["split"]["separates"]
          for s in ("CIRCLE", "TRIANGLE"))
      and all(float(_c["out"]["fill_groups"][s]["index"])
              > MRT.separation_index(MRT.Split(**_c["out"]["fill_split"]))
              for s in ("CIRCLE", "TRIANGLE")),
      "%r" % ({s: _c["out"]["fill_groups"][s]["index"]
               for s in ("CIRCLE", "TRIANGLE")},))

print()
print("the four classes are unequal and all four are real")
_i = R["imbalanced"]
check("12/8/6/4 routes every mark, and the quarter refuses no class",
      (_i["right"], _i["wrong"], _i["refused"]) == (30, 0, 0),
      "%d right, %d wrong, %d refused" % (_i["right"], _i["wrong"],
                                          _i["refused"]))
check("  and the smallest class is under a quarter of its own shape's marks",
      _i["out"]["fill_groups"]["TRIANGLE"]["low_n"] == 6
      and _i["out"]["fill_groups"]["TRIANGLE"]["high_n"] == 4,
      "%r" % (_i["out"]["fill_groups"]["TRIANGLE"],))

print()
print("an outlier is not a class, at either grain")
_o = R["outlier"]
check("one fill class and two crossed marks establishes no split",
      (_o["right"], _o["wrong"]) == (0, 0)
      and not _o["out"]["fill_groups"]["CIRCLE"]["split"]["separates"],
      "%r" % (_o["out"]["fill_groups"]["CIRCLE"],))
# REVERT: the minimum class size to two, which is what "the floor is too high"
# would do. The two contaminated marks become a class and are named.
_rel, _rsplits, _runstable = CSG.assign(_o["out"]["records"], _o["series"],
                                        "RELAXED_GLOBAL")
check("  and dropping the floor to two invents one and names two marks with it",
      _rsplits[""].separates
      and sum(1 for v in _rel.values() if v[1] == "L_FILLED_CIRCLE") == 2
      and not any(s["fill"] == "FILLED"
                  for s in _o["rendering"]["series"].values()),
      "%r" % (collections.Counter(v[1] for v in _rel.values() if v[1]),))

print()
print("the identity method names the axis the ink actually decided")
# v9.16 STAMPED `MEASURED_MARKER_SHAPE_FILL` ON EVERY ROUTED MARK, and refused a
# shape declared with one fill outright. Both were wider than the evidence: on a
# panel of ONE declared shape the shape came off the manifest, and a shape with
# one declared fill is named by the shape alone - which was measured. v9.17 uses
# the registry's own narrower names, and the refusal is gone because it was the
# right answer to the wrong question.
_f = R["one_fill"]
_tri = [x for x in _f["out"]["records"] if x.get("shape") == "TRIANGLE"
        and x["Marker_Validity_Status"] == "SINGLE_MARKER"]
check("a shape declared with one fill is named by its shape, and says so",
      bool(_tri) and all(x["Identity_Method"] == "MEASURED_MARKER_SHAPE"
                         and x["Series_ID"] == "R_FILLED_TRIANGLE"
                         and not x["fill"] for x in _tri),
      "%r" % (sorted({(x["Identity_Method"], x["fill"], x["Series_ID"])
                      for x in _tri}),))
check("  and it carries no fill group, because none was asked",
      all(x["Fill_Group_Threshold"] is None
          and x["Fill_Conditioning_Shape"] == "" for x in _tri),
      "%r" % (sorted({(x["Fill_Conditioning_Shape"], x["Fill_Group_Threshold"])
                      for x in _tri}),))
check("  the circles on the same panel measured both, and say that instead",
      _f["right"] == 24 and _f["wrong"] == 0
      and {x["Identity_Method"] for x in _f["out"]["records"]
           if x.get("shape") == "CIRCLE" and x["Series_ID"]}
      == {"MEASURED_MARKER_SHAPE_FILL"},
      "%d right, %d wrong" % (_f["right"], _f["wrong"]))
# AND A PANEL OF ONE DECLARED SHAPE MEASURED ONLY THE FILL. `outlier` declares
# circles open and filled and nothing else, so its shape axis is a manifest
# column - which is what the method has to say.
check("  a panel of one declared shape claims the fill and not the shape",
      MRT.identity_method(False, True) == "MEASURED_MARKER_FILL"
      and MRT.identity_method(True, False) == "MEASURED_MARKER_SHAPE"
      and MRT.identity_method(True, True) == "MEASURED_MARKER_SHAPE_FILL"
      and MRT.identity_method(False, False) == "DECLARED_SINGLE_SERIES",
      "%r" % (MRT.IDENTITY_BY_EVIDENCE,))
check("    and every one of the four is a pair SCATTER may produce",
      all(not PROV.contract_failure("SCATTER", m, "POINT_CLOUD_ASSOCIATION")
          for m in MRT.IDENTITY_BY_EVIDENCE.values()),
      "%r" % ([m for m in MRT.IDENTITY_BY_EVIDENCE.values()
               if PROV.contract_failure("SCATTER", m,
                                        "POINT_CLOUD_ASSOCIATION")],))
# REVERT: `fill_verdict` returning the single declared fill, which is the branch
# that was removed in v9.16. Every triangle would then carry a FILL nothing
# measured, and - with v9.17's method table - the wider method beside it.
check("  the removed branch would have put a measured fill on all eight",
      sum(1 for x in _tri
          if CSG.verdict_before(x["Fill_Score_Window"],
                                MRT.Split(None, 0.0, 0.0, False),
                                {"FILLED"}) == "FILLED") == 8,
      "%d of %d" % (sum(1 for x in _tri
                        if CSG.verdict_before(x["Fill_Score_Window"],
                                              MRT.Split(None, 0.0, 0.0, False),
                                              {"FILLED"})), len(_tri)))

print()
print("the panel whose only splits are per-shape")
_go = R["group_only"]
check("the panel-wide split does not separate and both shape groups do",
      not _go["out"]["fill_split"]["separates"]
      and all(_go["out"]["fill_groups"][s]["split"]["separates"]
              for s in ("CIRCLE", "TRIANGLE")),
      "panel %r, groups %r"
      % (_go["out"]["fill_split"]["separates"],
         {s: _go["out"]["fill_groups"][s]["split"]["separates"]
          for s in ("CIRCLE", "TRIANGLE")}))
check("  and all thirty of its marks route, none of them wrong",
      (_go["right"], _go["wrong"]) == (30, 0),
      "%d right, %d wrong" % (_go["right"], _go["wrong"]))
# REVERT: the panel-wide grain. Nothing routes at all - which is the cost of the
# old grain stated as a number rather than as an argument.
_gw, _gs, _gu = CSG.assign(_go["out"]["records"], _go["series"],
                           "CURRENT_GLOBAL")
check("  under the panel-wide rule the same figure routes nothing",
      sum(1 for v in _gw.values() if v[1]) == 0 and not _gs[""].separates,
      "%d routed under the panel-wide split"
      % sum(1 for v in _gw.values() if v[1]))

print()
print("a fill without a shape names no class")
_b = R["shape_blind"]
check("the fill separates, the shape does not, and nothing is routed",
      _b["out"]["fill_split"]["separates"]
      and not _b["out"]["shape_split"]["separates"]
      and _b["right"] == _b["wrong"] == 0
      and _b["refusals"] == ["MARKER_SHAPE_UNRESOLVED"],
      "%r" % (_b["refusals"],))
check("  and a mark with no shape is in no group and carries no group evidence",
      all(x["Fill_Conditioning_Shape"] == ""
          and x["Fill_Group_Threshold"] is None
          for x in _b["out"]["records"]
          if x["Marker_Validity_Status"] == "SINGLE_MARKER"),
      "%r" % (sorted({str(x["Fill_Conditioning_Shape"])
                      for x in _b["out"]["records"]}),))

print()
print("small markers stay fail-closed at both grains")
for _name in ("tiny", "micro"):
    check("%s routes nothing" % _name,
          R[_name]["right"] == R[_name]["wrong"] == 0
          and all(not x["Series_ID"] for x in R[_name]["out"]["records"]),
          "%d right, %d wrong, %r" % (R[_name]["right"], R[_name]["wrong"],
                                      R[_name]["refusals"]))
# REVERT: `_split`'s zero-spread branch, which returned an INFINITE index for a
# set whose values are all the same number. `split_grain_tiny` has four circles
# at a 5 px marker that all read exactly 1.0; before this round that group came
# back separated with `between = 0.0`, `_clear` waved every mark through because
# there was no `between` to measure a margin against, and all four were named
# FILLED. One class read as two.
check("  a set of identical values is one class, not two",
      not MRT._split([1.0, 1.0, 1.0, 1.0]).separates
      and not MRT._split([0.5] * 9).separates,
      "%r" % (MRT._split([1.0, 1.0, 1.0, 1.0]),))
check("    and two tight classes with no spread at all still separate",
      MRT._split([1.0, 1.0, 2.0, 2.0]).separates
      and MRT.separation_index(MRT._split([1.0, 1.0, 2.0, 2.0])) == float("inf"),
      "%r" % (MRT._split([1.0, 1.0, 2.0, 2.0]),))

print()
print("a merged blob reaches no group")
_v = R["overlap"]
check("the touching pair is refused and is not in either shape's split",
      "MARKER_MERGED" in _v["refusals"] and _v["wrong"] == 0
      and sum(g["n"] for s, g in _v["out"]["fill_groups"].items())
      == sum(1 for x in _v["out"]["records"]
             if x["Marker_Validity_Status"] == "SINGLE_MARKER"
             and x.get("shape")),
      "%r" % ({s: g["n"] for s, g in _v["out"]["fill_groups"].items()},))

print()
print("the evidence a reviewer re-derives the verdict from")
_routed_marks = [x for x in R["confounded"]["out"]["records"] if x["Series_ID"]]
check("every routed mark carries all eleven group columns",
      bool(_routed_marks)
      and all(all(c in x for c in MRT.GROUP_EVIDENCE) for x in _routed_marks),
      "%r" % (sorted(set(MRT.GROUP_EVIDENCE) - set(_routed_marks[0])),))
check("  and every one of them is inside the routing evidence hash",
      set(MRT.GROUP_EVIDENCE) <= set(AG.ROUTING_EVIDENCE)
      and set(MRT.GROUP_EVIDENCE) <= set(SP.POINT_ARTIFACT_COLUMNS),
      "%r" % (sorted(set(MRT.GROUP_EVIDENCE) - set(AG.ROUTING_EVIDENCE)),))
check("  the recorded margin is the distance from the group's own threshold",
      all(abs(float(x["Fill_Group_Margin"])
              - abs(float(x["interior_ink"])
                    - float(x["Fill_Group_Threshold"]))) < 1e-6
          for x in _routed_marks),
      "%r" % ([(x["Fill_Group_Margin"], x["interior_ink"],
                x["Fill_Group_Threshold"]) for x in _routed_marks[:3]],))
check("  and the group that decided a mark is the shape that mark was measured as",
      all(x["Fill_Conditioning_Shape"] == x["shape"] for x in _routed_marks),
      "%r" % (sorted({(x["Fill_Conditioning_Shape"], x["shape"])
                      for x in _routed_marks}),))
# THE VERIFIER, AND WHAT IT CATCHES. Each of these is a producer with an editor:
# the numbers are self-consistent as a document and contradict the class.
_good = dict(_routed_marks[0])
check("a clean routed mark passes the group verifier",
      AG.fill_group_validity(_good) == "", AG.fill_group_validity(_good))
_flip = dict(_good, fill=("OPEN" if _good["fill"] == "FILLED" else "FILLED"))
check("  a flipped fill is caught by its own recorded threshold",
      AG.NOT_A_GROUP in AG.fill_group_validity(_flip),
      "%r" % (AG.fill_group_validity(_flip),))
_other = "TRIANGLE" if _good["shape"] == "CIRCLE" else "CIRCLE"
_swap = dict(_good,
             Fill_Group_Threshold=R["confounded"]["out"]["fill_groups"][_other]
             ["split"]["threshold"])
check("  the other shape's threshold pasted in is caught by the margin",
      AG.NOT_A_GROUP in AG.fill_group_validity(_swap),
      "%r" % (AG.fill_group_validity(_swap),))
_stamp = dict(_good, Fill_Conditioning_Shape=_other)
check("  a re-stamped conditioning shape is caught by the mark's own shape",
      AG.NOT_A_GROUP in AG.fill_group_validity(_stamp),
      "%r" % (AG.fill_group_validity(_stamp),))
_open = dict(_good, Fill_Group_Separates="FALSE")
check("  and a group that did not separate cannot carry a class",
      AG.NOT_A_GROUP in AG.fill_group_validity(_open),
      "%r" % (AG.fill_group_validity(_open),))
check("  while a record that measured nothing says nothing here",
      AG.fill_group_validity(dict(Series_ID="S", Marker_Fill="OPEN")) == "",
      "%r" % (AG.fill_group_validity(dict(Series_ID="S")),))
# AND THE FINALIZER REACHES IT THROUGH `marker_validity`, which is the function
# `_scatter_route_failures` calls. A group check nothing in the gate path
# consults is a check that never runs on a real batch.
check("  and the gate's own entry point carries the group check",
      AG.marker_validity(_good) == "" and AG.NOT_A_GROUP in AG.marker_validity(_flip),
      "%r" % (AG.marker_validity(_flip),))

print()
print("the group evidence survives a round trip through the artifact CSV")
# THE FAIL-OPEN THIS SUITE EXISTS TO NOT REPEAT. A column the CSV writes and
# `evidence_record` cannot map back comes home as None on every row, the
# evidence hash is then taken over blanks, and every check downstream agrees
# with a file that says nothing.
_row = {}
for _column in SP.POINT_ARTIFACT_COLUMNS:
    _ev = AG.routing_evidence(_good)
    _row[_column] = ("" if _ev.get(_column) is None else _ev[_column]) \
        if _column in _ev else ""
_back = SP.evidence_record({k: ("" if v is None else str(v))
                            for k, v in _row.items()})
check("every group column maps back to the name the reader wrote",
      all(AG._EVIDENCE_FROM.get(c) for c in MRT.GROUP_EVIDENCE),
      "%r" % ([c for c in MRT.GROUP_EVIDENCE if not AG._EVIDENCE_FROM.get(c)],))
check("  and the evidence hash is the same before and after the trip",
      AG.routing_evidence_sha256(_back) == AG.routing_evidence_sha256(_good),
      "%s vs %s" % (AG.routing_evidence_sha256(_back)[:12],
                    AG.routing_evidence_sha256(_good)[:12]))
check("    including the fields a CSV would turn into strings",
      AG.routing_evidence(_back)["Fill_Group_Separates"] == "TRUE"
      and isinstance(AG.routing_evidence(_back)["Fill_Group_N"], int),
      "%r" % ({k: AG.routing_evidence(_back)[k]
               for k in ("Fill_Group_Separates", "Fill_Group_N")},))

print()
print("four rules, one harness, and what each of them costs")
_rows = CSG.table()
_by = {}
for _r in _rows:
    _by.setdefault(_r["candidate"], []).append(_r)
_tot = {k: dict(wrong=sum(x["wrong"] for x in v),
                right=sum(x["right"] for x in v),
                false_split=sum(x["false_split"] for x in v),
                twin=sum(x["right"] for x in v if x["fixture"].startswith("twin/")))
        for k, v in _by.items()}
for _name in CSG.CANDIDATES:
    print("    %-20s right %3d  wrong %2d  false_split %d  twin routed %d"
          % (_name, _tot[_name]["right"], _tot[_name]["wrong"],
             _tot[_name]["false_split"], _tot[_name]["twin"]))
check("only the two conditioned rules reach wrong = 0",
      _tot["CURRENT_GLOBAL"]["wrong"] == 5
      and _tot["RELAXED_GLOBAL"]["wrong"] == 19
      and _tot["SHAPE_CONDITIONED"]["wrong"] == 0
      and _tot["DECLARATION_AWARE"]["wrong"] == 0,
      "%r" % ({k: v["wrong"] for k, v in sorted(_tot.items())},))
# AND THE ADOPTED RULE IS NOT PAYING FOR IT IN REFUSALS EITHER. It routes more
# marks than the rule it replaced, on the same fourteen renderings - which is
# not why it was adopted and is worth having said, because "wrong 0" is cheap
# for a reader that refuses everything.
check("  and it routes MORE than the rule it replaced, not fewer",
      _tot["SHAPE_CONDITIONED"]["right"] > _tot["CURRENT_GLOBAL"]["right"]
      and _tot["SHAPE_CONDITIONED"]["right"]
      > _tot["DECLARATION_AWARE"]["right"],
      "%r" % ({k: v["right"] for k, v in sorted(_tot.items())},))
check("  relaxing the floor is the only rule that invents a class",
      _tot["RELAXED_GLOBAL"]["false_split"] == 1
      and all(_tot[k]["false_split"] == 0 for k in CSG.CANDIDATES
              if k != "RELAXED_GLOBAL"),
      "%r" % ({k: v["false_split"] for k, v in sorted(_tot.items())},))
# AND THE ONE THAT WAS REJECTED, AND WHY. DECLARATION_AWARE reaches wrong = 0
# too, and it does it by refusing marks the reader was right about: at 11 and 22
# px the circle group holds seven marks and five of them are open, so an
# absolute support of three refuses a class the drawing has eight of. The same
# drawing at three scales then gives three different answers, which is the
# property the twin fixture exists to hold the reader to.
check("  and the stricter rule refuses marks the existing fixture routes",
      _tot["DECLARATION_AWARE"]["twin"] < _tot["SHAPE_CONDITIONED"]["twin"]
      == _tot["CURRENT_GLOBAL"]["twin"],
      "%r" % ({k: v["twin"] for k, v in sorted(_tot.items())},))
_da = {x["fixture"]: x["right"] for x in _by["DECLARATION_AWARE"]}
check("    so it is not scale-invariant on one drawing at three sizes",
      len({_da["twin/s1"], _da["twin/s2"], _da["twin/s3"]}) == 3,
      "%r" % ({k: _da[k] for k in ("twin/s1", "twin/s2", "twin/s3")},))

print()
print("the existing fixture answers exactly as it did")
# THE PROPERTY A CHANGE OF GRAIN HAD TO NOT COST. Same numbers, mark for mark,
# on the family that was here first.
_sc = {x["fixture"]: x for x in _by["SHAPE_CONDITIONED"]}
_cg = {x["fixture"]: x for x in _by["CURRENT_GLOBAL"]}
check("twin_scatter routes 16, 17, 18 and 19 with none misrouted, as before",
      [_sc["twin/%s" % n]["right"] for n in ("s1", "s2", "s3", "overlap")]
      == [16, 17, 18, 19]
      and all(_sc["twin/%s" % n]["wrong"] == 0
              for n in ("s1", "s2", "s3", "overlap")),
      "%r" % ({n: (_sc["twin/%s" % n]["right"], _sc["twin/%s" % n]["wrong"])
               for n in ("s1", "s2", "s3", "overlap")},))
check("  and every twin rendering is unchanged, right and wrong alike",
      all((_sc[k]["right"], _sc[k]["wrong"])
          == (_cg[k]["right"], _cg[k]["wrong"])
          for k in _sc if k.startswith("twin/")),
      "%r" % ({k: (_cg[k]["right"], _sc[k]["right"])
               for k in sorted(_sc) if k.startswith("twin/")
               and _cg[k]["right"] != _sc[k]["right"]},))

print()
print("the diagnostics are the measurement, not a description of it")
_diag = D.diagnose(Image.open(os.path.join(HERE,
                                           DOC["renderings"]["confounded"]["file"])
                              ).convert("RGB"),
                   DOC["renderings"]["confounded"]["panel_box"],
                   R["confounded"]["series"], panel="grain", rendering="confounded")
check("every cut of the pooled distribution is tabulated, not just the winner",
      len(_diag["global_cuts"]) > 1
      and all({"low_n", "high_n", "threshold", "between", "within", "index"}
              <= set(c) for c in _diag["global_cuts"]),
      "%d cuts" % len(_diag["global_cuts"]))
check("  and the plainest pooled cut is the one that splits the two OPEN classes",
      D.best(_diag["global_cuts"])["low_n"] == 12
      and D.best(_diag["global_cuts"])["high_n"] == 13,
      "%r" % (D.best(_diag["global_cuts"]),))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
