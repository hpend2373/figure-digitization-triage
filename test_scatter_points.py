# -*- coding: utf-8 -*-
"""The routed scatter, from the panel a runner is handed to the file it leaves.

    python3 test_scatter_points.py     # exit 0 = all scenarios pass

`marker_routing` says which mark is which and `axis_grain` says which scale each
was read on. This is the third piece: the durable file those two leave behind,
and the three checks that can be made against it -

    the file against itself      every hash covers what it carries, every value
                                 follows from its pixel under the axis it cites
    the file against the manifest a point cannot sit under a series the manifest
                                 does not put on that axis
    the file against THE RASTER  the panel is routed again and each row's
                                 recorded evidence is compared with the ink

Only the third needs the figure, and only the third cannot be satisfied by
writing: a producer with an editor can make a consistent file, and cannot make
one that agrees with a re-measurement it never made.

Everything here runs in a fresh clone. The panel is `twin_scatter_s3.jpeg`,
which this repository carries, declared the way a batch declares one - a panel
row, four series rows naming their axes, and an axis manifest with three.
"""
import csv
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image                                             # noqa: E402
import axis_grain as AG                                           # noqa: E402
import batch_manifests as BM                                      # noqa: E402
import provenance as PV                                           # noqa: E402
import run_batch as RB                                            # noqa: E402
import finalize_batch as FIN                                      # noqa: E402
import scatter_points as SP                                       # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_scatter_")
DOC = json.load(open(os.path.join(HERE, "twin_scatter_truth.json"),
                     encoding="utf-8"))
R = DOC["renderings"]["s3"]
IMAGE = os.path.join(HERE, R["file"])
PANEL = "P_TWIN"
SHA = RB.file_sha256(IMAGE)


def _ticks(pairs):
    return ";".join("%g:%g" % (v, px) for v, px in pairs)


AXIS_ROWS = [
    dict(Axis_ID="X_BOTTOM", Panel_ID=PANEL, Dimension="X", Side="BOTTOM",
         Unit="cm H2O", Scale="LINEAR", Calibration_Points=_ticks(R["x_ticks"]),
         Note=""),
    dict(Axis_ID="Y_LEFT", Panel_ID=PANEL, Dimension="Y", Side="LEFT",
         Unit="mmHg/L/min", Scale="LINEAR",
         Calibration_Points=_ticks(R["left_y_ticks"]), Note=""),
    dict(Axis_ID="Y_RIGHT", Panel_ID=PANEL, Dimension="Y", Side="RIGHT",
         Unit="index", Scale="LINEAR",
         Calibration_Points=_ticks(R["right_y_ticks"]), Note=""),
]
SERIES_ROWS = [
    dict(Panel_ID=PANEL, Series_ID=sid, Colour_Hex="", Colour_Tolerance="",
         Mask_Key="", Marker_Shape=spec["shape"], Marker_Fill=spec["fill"],
         Line_Style="", Bar_Fill_Pattern="",
         Axis_ID=("Y_LEFT" if spec["axis"] == "LEFT" else "Y_RIGHT"),
         Factor_Name="SERIES", Factor_Level=sid, Note="")
    for sid, spec in sorted(R["series"].items())
]
PANEL_ROW = dict(
    Panel_ID=PANEL, Source_Panel_ID=PANEL, Figure_ID="F_TWIN",
    Identity_Domain_ID="F_TWIN", Unit_ID="U_TWIN", Panel_Label=PANEL,
    Mark_Type="SCATTER", Image_Path=R["file"],
    Panel_X0=R["panel_box"][0], Panel_X1=R["panel_box"][1],
    Panel_Y0=R["panel_box"][2], Panel_Y1=R["panel_box"][3],
    Axis_X_Ticks=_ticks(R["x_ticks"]), Axis_Y_Ticks=_ticks(R["left_y_ticks"]),
    Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
    Association_Type="PEARSON_R", Panel_Mode="AUTO", Config_ID="")
UNIT_ROW = dict(Unit_ID="U_TWIN", Statistic_Type="ASSOCIATION", N_Outcome="")

RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "out")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

print("the axis manifest is what makes the runner take the routed reader")
OUTCOME = RB.run_panel(PANEL_ROW, SERIES_ROWS, [], {}, UNIT_ROW, RAW,
                       file_root=HERE, axis_rows=AXIS_ROWS, output_dir=OUT)
check("a four-series monochrome panel with an axis manifest reads",
      OUTCOME.state == "AUTO_PASS" and len(OUTCOME.values) == 4,
      "%s: %s" % (OUTCOME.state, OUTCOME.detail))
# THE SAME PANEL WITHOUT THE MANIFEST IS THE REFUSAL THAT WAS ALWAYS RIGHT.
# `read_scatter_panel` takes one y calibration and cannot tell four monochrome
# series apart with a shared threshold; nothing here loosened that.
_bare = RB.run_panel(PANEL_ROW, SERIES_ROWS, [], {}, UNIT_ROW, RAW,
                     file_root=HERE, axis_rows=(), output_dir=OUT)
check("  and the same panel without one is refused, as it always was",
      _bare.state != "AUTO_PASS"
      and "marker routing" in (_bare.detail or ""),
      "%s: %s" % (_bare.state, _bare.detail))
check("  every value carries the routed identity method",
      {str(v.get("Identity_Method")) for v in OUTCOME.values}
      == {SP.IDENTITY_METHOD},
      "%r" % ({str(v.get("Identity_Method")) for v in OUTCOME.values},))
# AND THAT METHOD IS REGISTERED, which is what lets a value priced by it be
# finalized at all. An unregistered identity prices at the highest tier.
check("  and that method is in the provenance registry at R0",
      PV.identity_tier(SP.IDENTITY_METHOD) == "R0"
      and SP.IDENTITY_METHOD in PV.IDENTITY_METHODS,
      "%s" % PV.identity_tier(SP.IDENTITY_METHOD))
check("  and the association method is the point cloud's, not the marker's",
      {str(v.get("Value_Method")) for v in OUTCOME.values}
      == {"POINT_CLOUD_ASSOCIATION"},
      "%r" % ({str(v.get("Value_Method")) for v in OUTCOME.values},))

print()
print("each series is calibrated against the axis it names, not the panel's")
# THE CLAIM THE WHOLE GRAIN RESTS ON. The two scales differ by 2.80, so a
# right-hand series read on the left ladder comes back on a scale nothing in the
# figure uses. Here the drawn values are known.
_drawn = {sid: [p[1] for p in spec["pairs"]]
          for sid, spec in sorted(R["series"].items())}
ART = os.path.join(OUT, "scatter_points.csv")
ROWS = list(csv.DictReader(open(ART, encoding="utf-8")))
_by_axis = {}
for row in ROWS:
    _by_axis.setdefault(row["Axis_ID"], []).append(float(row["y_value"]))
check("the left-hand points land on the left scale's range",
      16.0 <= min(_by_axis["Y_LEFT"]) and max(_by_axis["Y_LEFT"]) <= 22.0,
      "%.1f to %.1f" % (min(_by_axis["Y_LEFT"]), max(_by_axis["Y_LEFT"])))
check("  and the right-hand points on the right scale's, which is 2.8x it",
      45.0 <= min(_by_axis["Y_RIGHT"]) and max(_by_axis["Y_RIGHT"]) <= 80.0,
      "%.1f to %.1f" % (min(_by_axis["Y_RIGHT"]), max(_by_axis["Y_RIGHT"])))
check("  every routed point is within 0.3 of a value the figure was drawn with",
      all(min(abs(float(row["y_value"]) - v)
              for v in _drawn[row["Series_ID"]]) < 0.3 for row in ROWS),
      "%r" % (sorted(round(min(abs(float(row["y_value"]) - v)
                               for v in _drawn[row["Series_ID"]]), 3)
                     for row in ROWS)[-3:],))

print()
print("the file it leaves behind, and what can be checked against it")
check("the point file carries every routed point and no refused one",
      len(ROWS) == sum(int(v.get("N_Pairs") or 0) for v in OUTCOME.values)
      and all(r["Point_Record_SHA256"] for r in ROWS),
      "%d rows against %d pairs"
      % (len(ROWS), sum(int(v.get("N_Pairs") or 0) for v in OUTCOME.values)))
check("  and every one of the eighteen routing measurements is a column",
      set(AG.ROUTING_EVIDENCE) <= set(SP.POINT_ARTIFACT_COLUMNS)
      and set(AG.ROUTING_EVIDENCE) <= set(ROWS[0]),
      "%r" % (sorted(set(AG.ROUTING_EVIDENCE) - set(ROWS[0])),))
check("  the file verifies against the manifest it was written under",
      SP.verify_artifact(ROWS, SERIES_ROWS, RB._axis_manifest(AXIS_ROWS),
                         PANEL, SHA) == [],
      "%r" % (SP.verify_artifact(ROWS, SERIES_ROWS,
                                 RB._axis_manifest(AXIS_ROWS), PANEL, SHA)[:2],))
# THE RUNNER READS IT BACK BEFORE ANYBODY IS ASKED TO APPROVE IT. A writer whose
# output nobody reads back is a writer nobody checks, which is the shape
# `mono_bar_geometry.csv` learned first.
check("  and the runner registered it in the ledger under its own type",
      (SP.ARTIFACT_TYPE, ART) in list(OUTCOME.artifacts)
      and SP.ARTIFACT_TYPE in RB.PANEL_ARTIFACT_TYPES,
      "%r" % (list(OUTCOME.artifacts),))
check("  and a stale one cannot survive a re-run",
      "scatter_points.csv" in RB.CANONICAL_OUTPUTS,
      "the point file is not on the cleanup list")

# AND HALF A POINT IS NOT WRITTEN AT ALL. A point `stamp_points` refused has a
# pixel, a refusal and no value; a row for it would be blanks under a Series_ID,
# and the panel's counts are where a refused mark is already reported.
try:
    SP.artifact_rows([dict(Series_ID="S", point_px_x=1.0, point_px_y=2.0)])
    _unstamped = ""
except ValueError as exc:
    _unstamped = "%s" % exc
check("  an unstamped point is refused a row rather than written blank",
      "POINT_NOT_STAMPED" in _unstamped, "%r" % (_unstamped,))
# AND EVERY ROW HAS TO NAME THE SAME X AXIS. The verifier takes it off the file
# rather than from its caller - being told which axis to check against is the
# artifact-checked-against-itself shape - so two rows naming different ones is a
# file whose points were not read on one drawing.
_two_x = [dict(ROWS[0], X_Axis_ID="X_OTHER")] + ROWS[1:]
check("  and a file naming two x axes is refused before any hash is checked",
      any("x axes" in why for why in SP.verify_artifact(
          _two_x, SERIES_ROWS, RB._axis_manifest(AXIS_ROWS), PANEL, SHA)),
      "%r" % (SP.verify_artifact(_two_x, SERIES_ROWS,
                                 RB._axis_manifest(AXIS_ROWS), PANEL, SHA)[:2],))

print()
print("and the raster is asked whether any of it was ever measured")
IM = Image.open(IMAGE).convert("RGB")
check("routed again, the ink agrees with every row",
      SP.current_evidence_failures(ROWS, IM, R["panel_box"], SERIES_ROWS) == [],
      "%r" % (SP.current_evidence_failures(ROWS, IM, R["panel_box"],
                                           SERIES_ROWS)[:2],))
# THE THREE MUTATIONS, AND THEY ARE THREE DIFFERENT FINDINGS.
_edited = [dict(r) for r in ROWS]
_edited[0]["Off_Centre_Ink"] = "0.0100"
_ev = SP.current_evidence_failures(_edited, IM, R["panel_box"], SERIES_ROWS)
check("  an edited measurement is caught by re-measuring, not by a hash",
      [c for _i, c, _d in _ev] == [SP.EVIDENCE_STALE]
      and SP.verify_artifact(_edited, SERIES_ROWS,
                             RB._axis_manifest(AXIS_ROWS), PANEL, SHA),
      "%r" % (_ev[:1],))
_moved = [dict(r) for r in ROWS]
_moved[1]["point_px_x"] = str(float(_moved[1]["point_px_x"]) + 60)
# TWO FINDINGS, NOT ONE, SINCE v9.17. The moved row has no mark under it AND the
# mark it was moved off is still routed with no row carrying it. Before the
# one-to-one matching only the first was said, which is the half of the story a
# producer who moves a point rather than inventing one relies on.
_moved_ev = SP.current_evidence_failures(_moved, IM, R["panel_box"], SERIES_ROWS)
check("  a point moved to where no marker is has no mark to agree with",
      {c for _i, c, _d in _moved_ev} == {SP.NO_MARK_NOW, SP.MARK_MISSING}
      and [i for i, c, _d in _moved_ev if c == SP.NO_MARK_NOW] == [1],
      "%r" % ([(i, c) for i, c, _d in _moved_ev][:3],))
# AND A PANEL THAT NO LONGER SEPARATES IS NOT A ROW THAT IS WRONG. The 3 px
# rendering of the same drawing establishes neither split, so every row's class
# rests on ground that is gone - which is a different sentence from "this
# measurement is false", and gets a different code.
_MICRO = DOC["renderings"]["micro"]
check("  and a rendering that no longer separates says so, not 'wrong'",
      {c for _i, c, _d in SP.current_evidence_failures(
          ROWS, Image.open(os.path.join(HERE, _MICRO["file"])).convert("RGB"),
          _MICRO["panel_box"], SERIES_ROWS)} <= {SP.SPLIT_GONE, SP.NO_MARK_NOW},
      "%r" % ({c for _i, c, _d in SP.current_evidence_failures(
          ROWS, Image.open(os.path.join(HERE, _MICRO["file"])).convert("RGB"),
          _MICRO["panel_box"], SERIES_ROWS)},))

# THE FILE AND THE RASTER HAVE TO BE THE SAME SET, NOT MERELY COMPATIBLE. Until
# v9.17 each row was matched to its own nearest current mark, independently: a
# producer could DROP one mark and DUPLICATE another, re-stamp both rows, rebuild
# the association and the file hash, and every check in this package agreed. Both
# rows sat on a real marker, both hashed, and the association was computed over a
# cloud the figure does not contain.
_ROUTED_NOW = [x for x in
               __import__("marker_routing").route(
                   IM, R["panel_box"],
                   [dict(id=r["Series_ID"], shape=r["Marker_Shape"],
                         fill=r["Marker_Fill"]) for r in SERIES_ROWS])["records"]
               if x.get("Series_ID")]


def _restamp(rows):
    """Re-derive every hash on these rows, the way a forging producer would."""
    axes = RB._axis_manifest(AXIS_ROWS)
    cals = AG.calibrations(axes)
    recs = AG.axis_records(axes)
    out = []
    for row in rows:
        rec = SP.evidence_record(dict(row))
        for key in ("point_px_x", "point_px_y", "x_value", "y_value"):
            rec[key] = float(row[key])
        axis = row["Axis_ID"]
        ev = AG.routing_evidence_sha256(rec)
        rec["Routing_Evidence_SHA256"] = ev
        new = dict(row, Routing_Evidence_SHA256=ev)
        new["Point_Record_SHA256"] = AG.point_record_sha256(
            rec, axis, cals[axis], cals[row["X_Axis_ID"]], PANEL, SHA,
            axis_record=recs[axis], x_axis_record=recs[row["X_Axis_ID"]],
            routing_evidence_hash=ev)
        out.append(new)
    return out


# A,B -> A,A. One mark's row copied over another's, every hash rebuilt.
_dup = _restamp([dict(ROWS[0]), dict(ROWS[0])] + [dict(r) for r in ROWS[2:]])
_dup_ev = SP.current_evidence_failures(_dup, IM, R["panel_box"], SERIES_ROWS)
check("  a row duplicated over another, with every hash rebuilt, is refused",
      SP.DUPLICATE_POINT in {c for _i, c, _d in _dup_ev},
      "%r" % ([(c, d[:60]) for _i, c, d in _dup_ev][:3],))
check("    and the file's own verifier catches the duplicate too",
      any(SP.DUPLICATE_POINT in why for why in SP.verify_artifact(
          _dup, SERIES_ROWS, RB._axis_manifest(AXIS_ROWS), PANEL, SHA)),
      "%r" % (SP.verify_artifact(_dup, SERIES_ROWS,
                                 RB._axis_manifest(AXIS_ROWS), PANEL, SHA)[:2],))
# A,B -> A. One mark simply dropped. Every remaining row is true; the SET is not.
_dropped = _restamp([dict(r) for r in ROWS[1:]])
_drop_ev = SP.current_evidence_failures(_dropped, IM, R["panel_box"], SERIES_ROWS)
# ONE MARK CANNOT ANSWER FOR TWO ROWS, and the MATCHING is what says so. An
# extra row at a real mark's pixel leaves no mark over, so nothing is missing,
# and a verifier that lets every row find its own nearest mark finds one for
# both of them and passes. Under the one-to-one matching the second row has no
# UNCLAIMED mark and is refused - which is the finding that survives when the
# hash the duplicate check reads has been rewritten.
_extra = _restamp([dict(r) for r in ROWS]
                  + [dict(ROWS[0],
                          x_value=str(float(ROWS[0]["x_value"]) + 1e-9))])
_extra_ev = SP.current_evidence_failures(_extra, IM, R["panel_box"], SERIES_ROWS)
check("  an extra row at a mark another row already claims is refused",
      SP.NO_MARK_NOW in {c for _i, c, _d in _extra_ev}
      and SP.MARK_MISSING not in {c for _i, c, _d in _extra_ev},
      "%r" % ([(i, c) for i, c, _d in _extra_ev][:3],))
check("    and it says the mark was already claimed, not that none is there",
      any(c == SP.NO_MARK_NOW and "unclaimed" in d for _i, c, d in _extra_ev),
      "%r" % ([d for _i, c, d in _extra_ev if c == SP.NO_MARK_NOW][:1],))
check("  a routed mark the file leaves out is named, not passed over",
      SP.MARK_MISSING in {c for _i, c, _d in _drop_ev},
      "%r" % ([(c, d[:60]) for _i, c, d in _drop_ev][:3],))
check("    and the finding says which pixel the raster still routes",
      any(c == SP.MARK_MISSING and "(" in d for _i, c, d in _drop_ev),
      "%r" % ([d for _i, c, d in _drop_ev if c == SP.MARK_MISSING][:1],))
# AND THE HONEST FILE STILL PASSES, which is what makes the two findings above
# a check rather than a refusal of everything.
check("    while the file as written is a one-to-one set with the raster",
      SP.current_evidence_failures(ROWS, IM, R["panel_box"], SERIES_ROWS) == [],
      "%r" % (SP.current_evidence_failures(ROWS, IM, R["panel_box"],
                                           SERIES_ROWS)[:2],))

# AND THE SPLIT IT ASKS ABOUT IS THE ONE THAT NAMED THE ROW. Since v9.16 a mark's
# fill comes from its own SHAPE's split; `split_grain_group_only.jpeg` is a panel
# where the panel-wide split does NOT separate and both shape groups do. A
# verifier still asking the panel-wide question rejects all thirty rows of a
# perfectly good file.
_GG = json.load(open(os.path.join(HERE, "split_grain_truth.json"),
                     encoding="utf-8"))["renderings"]["group_only"]
_gg_image = Image.open(os.path.join(HERE, _GG["file"])).convert("RGB")
_gg_series = [dict(Panel_ID="P_GG", Series_ID=d["Series_ID"], Colour_Hex="",
                   Colour_Tolerance="", Mask_Key="",
                   Marker_Shape=d["Marker_Shape"], Marker_Fill=d["Marker_Fill"],
                   Line_Style="", Bar_Fill_Pattern="", Axis_ID=d["Axis_ID"],
                   Factor_Name="SERIES", Factor_Level=d["Series_ID"], Note="")
              for d in _GG["declared"]]
_gg_axes = [dict(Axis_ID="X_BOTTOM", Panel_ID="P_GG", Dimension="X",
                 Side="BOTTOM", Unit="cm H2O", Scale="LINEAR",
                 Calibration_Points=_ticks(_GG["x_ticks"]), Note=""),
            dict(Axis_ID="Y_LEFT", Panel_ID="P_GG", Dimension="Y", Side="LEFT",
                 Unit="mmHg/L/min", Scale="LINEAR",
                 Calibration_Points=_ticks(_GG["left_y_ticks"]), Note=""),
            dict(Axis_ID="Y_RIGHT", Panel_ID="P_GG", Dimension="Y", Side="RIGHT",
                 Unit="index", Scale="LINEAR",
                 Calibration_Points=_ticks(_GG["right_y_ticks"]), Note="")]
_gg_sha = RB.file_sha256(os.path.join(HERE, _GG["file"]))
_gg_points, _gg_meta = SP.read_routed_scatter_panel(
    _gg_image, _GG["panel_box"], _gg_series, RB._axis_manifest(_gg_axes),
    "P_GG", _gg_sha, "X_BOTTOM")
_gg_rows = SP.artifact_rows(_gg_points)
check("a panel whose only splits are per-shape writes a file that verifies",
      len(_gg_rows) == 30
      and not _gg_meta["fill_split"]["separates"]
      and all(_gg_meta["fill_groups"][s]["split"]["separates"]
              for s in ("CIRCLE", "TRIANGLE")),
      "%d rows, panel split %r"
      % (len(_gg_rows), _gg_meta["fill_split"]["separates"]))
check("  and the raster check asks each row's OWN shape group, not the panel",
      SP.current_evidence_failures(_gg_rows, _gg_image, _GG["panel_box"],
                                   _gg_series) == [],
      "%r" % ([(c, d[:70]) for _i, c, d in SP.current_evidence_failures(
          _gg_rows, _gg_image, _GG["panel_box"], _gg_series)][:3],))

print()
print("what the runner refuses, and says why")
_no_axis = [dict(r, Axis_ID="") for r in SERIES_ROWS]
_r1 = RB.run_panel(PANEL_ROW, _no_axis, [], {}, UNIT_ROW, RAW, file_root=HERE,
                   axis_rows=AXIS_ROWS, output_dir=OUT)
check("a series that names no axis on a twin-axis panel is refused",
      _r1.state == "NOT_CONVERTIBLE" and "names no Axis_ID" in (_r1.detail or ""),
      "%s: %s" % (_r1.state, _r1.detail))
_no_x = [r for r in AXIS_ROWS if r["Dimension"] != "X"]
_r2 = RB.run_panel(PANEL_ROW, SERIES_ROWS, [], {}, UNIT_ROW, RAW,
                   file_root=HERE, axis_rows=_no_x, output_dir=OUT)
check("  and a manifest with no x axis is refused rather than defaulted",
      _r2.state == "NOT_CONVERTIBLE" and "x axes" in (_r2.detail or ""),
      "%s: %s" % (_r2.state, _r2.detail))
_wrong = [dict(r, Axis_ID="X_BOTTOM") for r in SERIES_ROWS]
_r3 = RB.run_panel(PANEL_ROW, _wrong, [], {}, UNIT_ROW, RAW, file_root=HERE,
                   axis_rows=AXIS_ROWS, output_dir=OUT)
check("  and a series pointed at the x axis produces no value at all",
      _r3.state == "NOT_CONVERTIBLE"
      and AG.WRONG_DIMENSION in (_r3.detail or ""),
      "%s: %s" % (_r3.state, _r3.detail))

print()
print("and the finalizer holds a routed value against the file that measured it")
# THE SAME SHAPE AS THE GEOMETRY GATE. A value claiming an R0 identity route has
# a file in this run's ledger that recorded the measurements, and the finalizer
# joins the two rather than believing the value row.
import io                                                         # noqa: E402


def _gate(rows, values):
    said = []
    blob = io.StringIO()
    w = csv.DictWriter(blob, fieldnames=list(SP.POINT_ARTIFACT_COLUMNS))
    w.writeheader()
    w.writerows(rows)
    ledger = BM.pd.DataFrame([dict(Artifact_Type=SP.ARTIFACT_TYPE,
                                   Artifact_Path="scatter_points.csv",
                                   SHA256="", Panel_ID=PANEL,
                                   Artifact_Reference="")])
    held = FIN._scatter_route_failures(
        values, ledger, OUT, lambda w_, c, d: said.append((c, d)),
        artifacts={FIN.artifact_key(ledger.iloc[0]):
                   blob.getvalue().encode("utf-8")})
    return held, said


import inspect                                                    # noqa: E402
# AND THE GATE IS IN THE CHAIN. Every scenario below calls it directly, which
# says it works and not that anything calls it - and a gate nothing calls is the
# most expensive kind of decoration, because it reads like protection.
check("the gate is called from the finalizer's method contract",
      "_scatter_route_failures" in inspect.getsource(
          FIN.method_contract_failures),
      "the finalizer does not call it")

_ok_value = dict(Unit_ID="U_TWIN", Cell_Key="SERIES=L_OPEN_CIRCLE",
                 Run_Panel_ID=PANEL, Identity_Method=SP.IDENTITY_METHOD)
_held, _said = _gate(ROWS, [_ok_value])
check("a routed value whose point file agrees is not withheld",
      not _held and not _said, "%r %r" % (_held, _said))
# A VALUE CLAIMING THE ROUTE WITH NO FILE BEHIND IT.
_held, _said = _gate([], [_ok_value])
check("  one claiming the route with no point file is withheld",
      _held == {PANEL} and "wrote no routed point file" in _said[0][1],
      "%r %r" % (_held, _said))
# THE FILE NAMING A DIFFERENT ROUTE.
_other = [dict(r, Identity_Method="DECLARED_SINGLE_SERIES") for r in ROWS]
_held, _said = _gate(_other, [_ok_value])
check("  and one the file names differently is withheld",
      _held == {PANEL} and "DECLARED_SINGLE_SERIES" in _said[0][1],
      "%r %r" % (_held, _said))
# AND THE MERGED BLOB, LAUNDERED INTO THE FILE. Its own recorded off-centre ink
# is over its own recorded threshold, and the gate re-derives that rather than
# reading `Marker_Validity_Status`.
_laundered = [dict(r) for r in ROWS]
_laundered[0]["Off_Centre_Ink"] = "0.5533"
_laundered[0]["Off_Centre_Margin"] = "%.4f" % (0.25 - 0.5533)
_held, _said = _gate(_laundered, [_ok_value])
check("  and a point off a blob that held two markers is withheld",
      _held == {PANEL} and AG.NOT_ONE_MARKER in _said[0][1],
      "%r %r" % (_held, _said[:1]))
# AND THE WORD ALONE DOES NOT SAVE IT EITHER WAY: claiming SINGLE_MARKER over
# the same numbers is still refused, because the numbers are what is read.
_word = [dict(r) for r in _laundered]
_word[0]["Marker_Validity_Status"] = "SINGLE_MARKER"
_held, _said = _gate(_word, [_ok_value])
check("  even when the status column says SINGLE_MARKER",
      _held == {PANEL} and AG.NOT_ONE_MARKER in _said[0][1],
      "%r %r" % (_held, _said[:1]))

print()
print("the manifest layer refuses an axis file that cannot be read on")
_frame = BM.pd.DataFrame([dict(r) for r in AXIS_ROWS])


def _axis_problems(rows):
    df = BM.pd.DataFrame([{c: r.get(c, "") for c in BM.axis_manifest_columns()}
                          for r in rows])
    out = BM.validate_batch_manifests(
        BM.pd.DataFrame([{c: PANEL_ROW.get(c, "")
                          for c in BM.panel_manifest_columns()}]),
        BM.pd.DataFrame([{c: s.get(c, "")
                          for c in BM.series_manifest_columns()}
                         for s in SERIES_ROWS]),
        BM.pd.DataFrame(columns=BM.position_manifest_columns()),
        BM.pd.DataFrame(columns=BM.reader_config_columns()),
        source_documents=BM.pd.DataFrame(
            columns=BM.source_document_manifest_columns()),
        source_figures=BM.pd.DataFrame(
            columns=BM.source_figure_manifest_columns()),
        source_panels=BM.pd.DataFrame(
            columns=BM.source_panel_inventory_columns()),
        reviewers=BM.pd.DataFrame(columns=BM.reviewer_registry_columns()),
        axes=df, check_files=False)
    return sorted({p["check"] for _i, p in out.iterrows()})


check("two y axes declared on the same side are refused",
      "AXIS_PANEL_AMBIGUOUS" in _axis_problems(
          [AXIS_ROWS[0], AXIS_ROWS[1], dict(AXIS_ROWS[2], Side="LEFT")]),
      "%r" % (_axis_problems([AXIS_ROWS[0], AXIS_ROWS[1],
                              dict(AXIS_ROWS[2], Side="LEFT")]),))
check("  a y grain with no x axis in it is refused",
      "AXIS_MANIFEST_INCOMPLETE" in _axis_problems(AXIS_ROWS[1:]),
      "%r" % (_axis_problems(AXIS_ROWS[1:]),))
check("  a calibration that does not parse is refused",
      "BAD_AXIS_CALIBRATION" in _axis_problems(
          [dict(AXIS_ROWS[0], Calibration_Points="2 at 162")] + AXIS_ROWS[1:]),
      "%r" % (_axis_problems(
          [dict(AXIS_ROWS[0], Calibration_Points="2 at 162")] + AXIS_ROWS[1:]),))
check("  and an axis on a panel nobody declared is refused",
      "AXIS_PANEL_UNKNOWN" in _axis_problems(
          AXIS_ROWS + [dict(AXIS_ROWS[1], Axis_ID="Y_OTHER",
                            Panel_ID="P_NOBODY")]),
      "%r" % (_axis_problems(
          AXIS_ROWS + [dict(AXIS_ROWS[1], Axis_ID="Y_OTHER",
                            Panel_ID="P_NOBODY")]),))
# AND AN AXIS MANIFEST THAT IS ABSENT ENTIRELY CHANGES NOTHING. Every batch in
# the corpus has no second scale, so the file is optional and its absence is the
# same run it was before this grain existed.
check("  and the axis manifest is optional, so every other batch is unchanged",
      "axes" in RB.OPTIONAL_MANIFEST_FILES
      and RB.OPTIONAL_MANIFEST_FILES["axes"] == "axis_manifest.csv"
      and "AXIS_MANIFEST_INCOMPLETE" not in _axis_problems([])
      and "BAD_AXIS_ROW" not in _axis_problems([]),
      "%r" % (_axis_problems([]),))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
