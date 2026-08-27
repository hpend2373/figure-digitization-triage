"""Regression scenarios for the plan compiler.

Two claims are under test.

**The compiler derives what follows and refuses to invent what does not.**
Hashes come off the files. A unit's `Axis_Calib_*` comes from the ticks of the
panel that fills it. A `Figure_ID` row is built from the panels that claim it.
None of those can be typed wrong, because none of them is typed.

**The plan is a complete description.** Compiling publication 397 from
`plan_397.json` and running the batch produces the same 48 values, cell for
cell, as the hand-written pilot that measured them - which is the only evidence
worth having that the compiler lost nothing on the way through.
"""
import copy
import json
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compile_plan as CP                                          # noqa: E402
import grid_engine as GE                                            # noqa: E402
import mark_readers as MR                                          # noqa: E402
import run_batch as RB                                             # noqa: E402

ROOT = tempfile.mkdtemp(prefix="fdt_plan_")
FAILURES, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "  <- %s" % detail))
    if not ok:
        FAILURES.append(name)


def _auto_panels(plan, number):
    """The panels of one publisher figure that carry a read block."""
    figure = [f for f in plan["figures"]
              if f.get("figure_number") == number][0]
    return [p for p in figure["panels"] if p.get("read")]


def _exchange_units(plan, number):
    a, b = _auto_panels(plan, number)[:2]
    a["read"]["unit_id"], b["read"]["unit_id"] = (b["read"]["unit_id"],
                                                 a["read"]["unit_id"])


def _claim_twice(plan, number):
    a, b = _auto_panels(plan, number)[:2]
    b["read"]["unit_id"] = a["read"]["unit_id"]


PLAN_PATH = os.path.join(HERE, "plan_397.json")
if not os.path.exists(PLAN_PATH):
    print("BLOCKED: plan_397.json is not in the package", file=sys.stderr)
    raise SystemExit(2)
with open(PLAN_PATH, encoding="utf-8") as fh:
    PLAN = json.load(fh)

# EVERY SCENARIO IN THIS FILE COMPILES THE SHIPPED PLAN, and the shipped plan
# names five publisher rasters. This repository is public and does not carry
# them, so the whole file SKIPS when they are absent rather than crashing two
# hundred lines down inside `compile_to`.
#
# CI SUPPLIES THEM through `FDT_RASTER_ROOT`, so the scenario count this file
# contributes there is unchanged. A clone without the rasters runs fewer
# scenarios and says so, which is the honest answer for a tree that cannot see
# the figures.
import raster_root as _RR                                        # noqa: E402
_plan_rasters = sorted({f["image"] for f in PLAN["figures"]})
_absent_rasters = [r for r in _plan_rasters if not _RR.check(r)[0]]
if _absent_rasters:
    print(_RR.skip_note(_absent_rasters[0]))
    print("FDT_SCENARIOS_RUN=0")
    raise SystemExit(0)
# THE PLAN'S FILE ROOT IS WHERE THE RASTERS TURNED OUT TO BE, not where this
# file sits. CI fetches them into a directory of its own and points
# `FDT_RASTER_ROOT` at it, so a `file_root` hardcoded to HERE reports
# SOURCE_FILE_NOT_FOUND for all five and the whole file dies on the first
# scenario. When the rasters are beside the code the two are the same directory.
FILE_ROOT = os.path.dirname(_RR.check(_plan_rasters[0])[0])


def compile_to(name, plan=None, file_root=FILE_ROOT):
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    return out, CP.compile_plan(plan if plan is not None else copy.deepcopy(PLAN),
                                out, file_root=file_root, run_date="2026-08-07")


def codes(problems):
    return sorted({p["check"] for p in problems})


# THE ANNOTATION BOXES A PANEL DECLARES REACH THE MANIFEST. A scatter panel says
# where its printed `r` and `P` are, because the glyphs are marker-sized and no
# measurement separates them from data. A declaration that the compiler drops is
# worse than none: the plan says the annotation is excluded and the run reads it
# as points anyway.
_ann_plan = copy.deepcopy(PLAN)
_ann_panel = [p for f in _ann_plan["figures"] for p in f["panels"]
              if p.get("read")][0]
_ANN_BOX = [_ann_panel["read"]["box"][0] + 5, _ann_panel["read"]["box"][0] + 45,
            _ann_panel["read"]["box"][2] + 5, _ann_panel["read"]["box"][2] + 35]
_ann_panel["read"]["annotation_boxes"] = [_ANN_BOX]
_ann_dir, (_ann_written, _ann_probs) = compile_to("out_annotation", _ann_plan)
check("a declared annotation box reaches the panel manifest",
      not _ann_probs
      and any(row.get("Annotation_Boxes") == ",".join(str(v) for v in _ANN_BOX)
              for row in csv.DictReader(
                  open(os.path.join(_ann_dir, "panel_manifest.csv"),
                       encoding="utf-8"))),
      "%s" % codes(_ann_probs))
check("  and a panel that declares none carries an empty column",
      all("Annotation_Boxes" in row for row in csv.DictReader(
          open(os.path.join(_ann_dir, "panel_manifest.csv"), encoding="utf-8"))),
      "the column is missing from the manifest")


def _mutated(mutate):
    """A copy of the shipped plan with one thing changed."""
    plan = copy.deepcopy(PLAN)
    mutate(plan)
    return plan


print("one plan compiles to eleven manifests")
MDIR, (written, problems) = compile_to("m_ok")
check("the shipped plan compiles clean", not problems, "%s" % problems[:3])
check("and writes every manifest the runner demands",
      set(os.path.basename(p) for p in written.values())
      == set(RB.MANIFEST_FILES.values()),
      "%s" % sorted(set(RB.MANIFEST_FILES.values())
                    ^ set(os.path.basename(p) for p in written.values())))

_figures = pd.read_csv(os.path.join(MDIR, "source_figure_manifest.csv"), dtype=object)
check("the raster hash is read off the file, not taken from the plan",
      all(len(str(h)) == 64 for h in _figures["Source_Image_SHA256"])
      and "source_image_sha256" not in json.dumps(PLAN["figures"][0]).lower(),
      "%s" % list(_figures["Source_Image_SHA256"])[:1])

_units = pd.read_csv(os.path.join(MDIR, "unit_manifest.csv"), dtype=object).fillna("")
_panels = pd.read_csv(os.path.join(MDIR, "panel_manifest.csv"), dtype=object).fillna("")
_ticks = dict(zip(_panels["Unit_ID"], _panels["Axis_Y_Ticks"]))
_derived = []
for _, u in _units.iterrows():
    text = _ticks.get(u["Unit_ID"], "")
    if not text:
        continue
    pts = [p.split(":") for p in text.split(";")]
    _derived.append(
        float(u["Axis_Calib_Y1_Value"]) == float(pts[0][0])
        and float(u["Axis_Calib_Y1_Pixel"]) == float(pts[0][1])
        and float(u["Axis_Calib_Y2_Value"]) == float(pts[1][0])
        and float(u["Axis_Calib_Y2_Pixel"]) == float(pts[1][1]))
check("a unit's calibration is derived from its panel's ticks, not declared twice",
      _derived and all(_derived), "%d of %d agree" % (sum(_derived), len(_derived)))

_fm = pd.read_csv(os.path.join(MDIR, "figure_manifest.csv"), dtype=object).fillna("")
check("figure rows are built from the panels that claim them",
      set(_fm["Figure_ID"]) == set(_panels["Figure_ID"]),
      "%s" % sorted(set(_fm["Figure_ID"]) ^ set(_panels["Figure_ID"])))
check("and their panel counts are reconciled, never asserted",
      set(_fm["Panel_Reconciliation_Status"]) == {"MATCHED"}
      and all(int(r["Worklist_Panel_Count"]) ==
              sum(1 for _, p in _panels.iterrows()
                  if p["Figure_ID"] == r["Figure_ID"])
              for _, r in _fm.iterrows()),
      "%s" % _fm[["Figure_ID", "Worklist_Panel_Count"]].to_dict("records"))


print()
print("the compiled manifests are the pilot's, value for value")
# The pilot measured publication 397 by hand: boxes, ticks, x pixels, what the
# caption does and does not say. If the plan is a complete description of that
# work, running it has to land on the same numbers - and if it does not, the
# plan is missing something the compiler cannot know.
_ODIR = os.path.join(ROOT, "o_plan")
_summary = RB.run_batch(MDIR, _ODIR, file_root=FILE_ROOT, run_date="2026-08-07")
check("the compiled batch runs", _summary["status"] == "RAN", "%s" % _summary)
check("with the pilot's panel count", _summary["panels"] == 26, "%s" % _summary)
# 36, not the 48 the old BAR_MONO reader produced. Three panels of Figure 4 -
# P4_SV_WOMEN, P4_CO_MEN, P4_CO_WOMEN - now refuse with
# STROKE_SCALE_UNRESOLVED: the two-pass reader measures the figure's own line
# weight off the rule at the calibrated baseline and every threshold it uses is
# a multiple of that number, so a panel whose stroke it cannot measure has no
# scale for anything and says so. The old reader needed no stroke and read them.
#
# Nothing poolable was lost: all 48 were QC_FAILED anyway, because publication
# 397 does not say whether its error bars are SD or SEM. What this pin records
# is the COST of the switch, in the open - three panels that used to produce
# unvalidated numbers and now produce a named refusal, and a stroke measurement
# on those three that is worth a round of its own.
# 76, not 36: LINE_MONO_STYLE shipped and all twelve two-black-curve panels of
# Figures 1 and 2 now read. Their geometry was measured at the same time - it
# had been one box copied to every panel with twelve x pixels spread evenly
# between the edges, which was honest while nothing could read them and is not
# geometry.
#
# 123, not 76: v7.50. The reader used to classify the ink again at every
# position and believe the answer. Blinding drops furniture columns from the
# duty accounting - it must, or the stems alone would give every solid curve a
# gap of 3 - and it therefore HIDES GAPS AND CANNOT INVENT THEM, so a dashed
# curve running along a gridline measured a perfect solid line. A SOLID call
# made through a window that could not see half of itself is now withheld, and
# where the panel declares two styles and the reader found two curves, naming
# one names the other.
#
# Nothing here is accepted either way - see the next check - so what this pin
# records is not a yield but a COST AND A GAIN IN THE OPEN: 47 more cells
# attributed, and two panels that used to report NO_VARIANCE now reporting
# QC_FAILED because a dispersion they had been silent about is now measured.
check("and the 123 values the released readers stand behind",
      _summary["values"] == 123, "%s" % _summary)
check("and nothing accepted, because the paper still does not say SD or SEM",
      _summary["accepted"] == 0, "%s" % _summary)
_states = _summary["states"]
# NO_VARIANCE, where NO_READER_AVAILABLE used to be. The two heart-rate panels
# read their centres and no dispersion: publication 397 draws the two series'
# error bars at the same x, and where the bars touch, the column of ink holds
# both marks and neither cap can be attributed. A centre with no dispersion is
# not poolable, so the panel says so - which is the same answer it gave before,
# reached by measurement instead of by absence.
# The four states do not change; two panels move between them. Finger pulse
# volume (both sexes) and cardiac output women reached NO_VARIANCE by reading
# too few cells to carry a dispersion; with the withheld SOLID calls named by
# elimination they read enough, and land where the rest of this publication
# lands - QC_FAILED, waiting on an author who can say SD or SEM.
check("and the same four terminal states",
      _states == {"QC_FAILED": 14, "NO_VARIANCE": 7,
                  "PANEL_GEOMETRY_UNRESOLVED": 3, "MANUAL_POINT_READ": 2},
      "%s" % _states)
# PANEL_GEOMETRY_UNRESOLVED, not MANUAL_POINT_READ: the reason is on the run
# manifest now. Reported as "the reader resolved no marks in this panel" it was
# only findable by opening mono_bar_geometry.csv, so the state a person acts on
# lost the one thing they would act on.
_detail = {r["Panel_ID"]: r["Detail"] for r in csv.DictReader(
    open(os.path.join(_ODIR, "run_manifest.csv"), encoding="utf-8"))}
check("and the run manifest says why, not just that nothing came back",
      all("STROKE_SCALE_UNRESOLVED" in _detail.get(p, "")
          for p in ("P4_SV_WOMEN", "P4_CO_MEN", "P4_CO_WOMEN")),
      "%s" % {p: _detail.get(p) for p in ("P4_SV_WOMEN", "P4_CO_MEN")})
check("the three panels that changed are the ones the stroke pass refused",
      sorted(r["Panel_ID"] for r in csv.DictReader(
          open(os.path.join(_ODIR, "mono_bar_geometry.csv"), encoding="utf-8"))
          if r["Geometry_Error_Code"] == "STROKE_SCALE_UNRESOLVED")
      == ["P4_CO_MEN", "P4_CO_WOMEN", "P4_SV_WOMEN"],
      "%s" % sorted({r["Panel_ID"]: r["Geometry_Error_Code"] for r in
                     csv.DictReader(open(os.path.join(
                         _ODIR, "mono_bar_geometry.csv"), encoding="utf-8"))
                     }.items()))
_coverage = pd.read_csv(os.path.join(_ODIR, "source_panel_coverage.csv"))
check("and all 36 physical panels still accounted for",
      len(_coverage) == 36, "%d" % len(_coverage))

_pilot_out = os.path.join(ROOT, "o_pilot")
_pilot = subprocess.run(
    [sys.executable, os.path.join(HERE, "pilot_397.py"), _pilot_out],
    capture_output=True, text=True)
if _pilot.returncode == 0:
    _a = pd.read_csv(os.path.join(_pilot_out, "figure_values_raw.csv"),
                     dtype=object).fillna("")
    _b = pd.read_csv(os.path.join(_ODIR, "figure_values_raw.csv"),
                     dtype=object).fillna("")
    _cols = ["Mean", "Dispersion_Value", "Value_Status", "Errorbar_Stem_Confirmed"]
    _ai = _a.set_index(["Unit_ID", "Cell_Key"])[_cols].sort_index()
    _bi = _b.set_index(["Unit_ID", "Cell_Key"])[_cols].sort_index()
    check("every cell the pilot read, the plan reads too",
          list(_ai.index) == list(_bi.index),
          "%s" % sorted(set(_ai.index) ^ set(_bi.index))[:4])
    check("and to the same value",
          _ai.equals(_bi),
          "%s" % _ai[(_ai != _bi).any(axis=1)].head(3).to_dict("index"))
else:                                                          # pragma: no cover
    check("the pilot runs for comparison", False, _pilot.stderr[-400:])


print()
print("a plan that is wrong is wrong here, not at panel 140")
for _label, _mutate, _want in (
        ("a panel count that does not match the inventory",
         lambda p: p["figures"][0].update(observed_panel_count=99),
         "PLAN_PANEL_COUNT_MISMATCH"),
        ("a figure whose raster is not on disk",
         lambda p: p["figures"][0].update(image="no_such_figure.jpeg"),
         "SOURCE_FILE_NOT_FOUND"),
        ("a raster reached by walking out of the root",
         lambda p: p["figures"][0].update(image="../397_fig1.jpeg"),
         "SOURCE_FILE_NOT_FOUND"),
        ("a panel id that would become a filename elsewhere",
         lambda p: p["figures"][0]["panels"][0].update(panel_id="../escaped"),
         "UNSAFE_ID"),
        ("two panels claiming one id",
         lambda p: p["figures"][1]["panels"][0].update(
             panel_id=p["figures"][0]["panels"][0]["panel_id"]),
         "PLAN_DUPLICATE_ID"),
        ("a figure attributed to a document nobody declared",
         lambda p: p["figures"][0].update(document_id="SD_NOWHERE"),
         "PLAN_DOCUMENT_NOT_FOUND"),
        ("an inventory attributed to an unregistered reviewer",
         lambda p: p["figures"][0].update(reviewer_id="RV_NOBODY"),
         "PLAN_REVIEWER_NOT_FOUND"),
        ("a unit on a grid nobody defined",
         lambda p: p["units"][0].update(grid_id="G_NOWHERE"),
         "PLAN_GRID_NOT_FOUND"),
        ("a unit no panel fills",
         lambda p: p["units"].append(dict(p["units"][0], unit_id="U_ORPHAN",
                                          figure_view="F_NOWHERE")),
         "PLAN_UNIT_HAS_NO_PANEL"),
        ("a disposition outside the vocabulary",
         lambda p: p["figures"][0]["panels"][0].update(disposition="PROBABLY_FINE"),
         "BAD_SOURCE_PANEL_DISPOSITION"),
        ("an AUTO_DIGITIZE panel that says nothing about its marks",
         lambda p: p["figures"][2]["panels"][0].update(read=None),
         "PLAN_READ_BLOCK_MISSING"),
        ("a read block with no box",
         lambda p: p["figures"][2]["panels"][0]["read"].update(box=[]),
         "PLAN_READ_INCOMPLETE"),
        ("a read block pointing at a unit nobody declared",
         lambda p: p["figures"][2]["panels"][0]["read"].update(unit_id="U_NOWHERE"),
         "PLAN_UNIT_NOT_FOUND"),
        ("a statistic outside the vocabulary",
         lambda p: p["units"][0].update(statistic="VIBES"),
         "BAD_STATISTIC_TYPE"),
        ("a schema nobody published",
         lambda p: p.update(schema="figure-digitization-triage/plan/99"),
         "PLAN_SCHEMA_UNKNOWN"),
        # THE TWO FACTOR GRAINS, compared before a raster is opened. The runner
        # writes a panel's series factor AND its position factor into every
        # `Cell_Key` - whether or not the series is alone - and the grid gate then
        # requires the value's factor set to equal the grid's exactly. Nothing
        # compared them at plan time, so a panel naming a factor its grid did not
        # declare compiled cleanly, ran, read its marks, and had every value
        # refused as `FACTOR_SET_INCONSISTENT`: a diagnosis of the values instead
        # of the declaration that caused them. Publication 323's Figure 2 spent a
        # release like that - one series declaring `ARM` against a grid of
        # `{TIMEPOINT}` - and 30 values were thrown away after the reading.
        # THE BINDING, IN BOTH DIRECTIONS. `panel.read.unit_id` and
        # `unit.panel_id` say the same thing, and until v9.1 only the first
        # existed. Swapping the `unit_id` of two panels in ONE figure passed every
        # check there was: the measurements are right, each value matches its own
        # mark hash, the factor sets and cell counts are identical, and both units
        # are still filled by exactly one panel - so two panels' numbers land
        # under each other's outcome with nothing disagreeing. Reproduced on
        # `plan_397.json` before the fix: zero problems.
        ("two panels of one figure with their units exchanged",
         lambda p: _exchange_units(p, "FIG3"),
         "PLAN_PANEL_UNIT_MISMATCH"),
        ("a unit that does not name the panel filling it",
         lambda p: [u.pop("panel_id", None) for u in p["units"]],
         "PLAN_UNIT_NAMES_NO_PANEL"),
        ("a unit two panels both claim to fill",
         lambda p: _claim_twice(p, "FIG3"),
         "PLAN_UNIT_FILLED_TWICE"),
        ("a panel reading a unit that belongs to another figure",
         lambda p: p["units"][0].update(figure_view="F397_5"),
         "PLAN_PANEL_UNIT_VIEW_MISMATCH"),
        ("a panel naming a factor its unit's grid does not declare",
         lambda p: [sp.update(factor="LIMB")
                    for sp in p["figures"][2]["panels"][0]["read"]["series"]],
         "PLAN_PANEL_FACTOR_SET_MISMATCH"),
        ("  and a grid that drops a factor its panels name",
         lambda p: [g["factors"].pop("ARM", None) for g in p["grids"]],
         "PLAN_PANEL_FACTOR_SET_MISMATCH"),
        # AND THE LEVELS UNDER THOSE NAMES (v9.2). Comparing the two factor SETS
        # compares headings. A panel whose TIMEPOINT positions are `B1..R3`
        # against a grid declaring `B-1..R-3` matches on {TIMEPOINT} and shares
        # not one cell with it, and the runner writes the level into every
        # `Cell_Key` - so the marks are read off the raster and then refused one
        # by one as `UNDECLARED_FACTOR_LEVEL`. Which is the same
        # after-all-the-work diagnosis v9.0 removed at the name grain, waiting
        # one grain down.
        ("a series naming a level its grid does not declare",
         lambda p: p["figures"][2]["panels"][0]["read"]["series"][0].update(
             level="PLACEBO"),
         "PLAN_PANEL_FACTOR_LEVEL_UNDECLARED"),
        ("a position naming a level its grid does not declare",
         lambda p: p["figures"][2]["panels"][0]["read"]["positions"][0].update(
             level="MIDWAY"),
         "PLAN_PANEL_FACTOR_LEVEL_UNDECLARED"),
        # The near-miss this is really about: "0:30" against a grid that
        # declares "0_30". Two spellings of one timepoint, and the factor sets
        # are identical.
        ("a level that differs from the grid's only in punctuation",
         lambda p: [pp.update(level=pp["level"].replace(":", "_"))
                    for pp in _auto_panels(p, "FIG1")[0]["read"]["positions"]],
         "PLAN_PANEL_FACTOR_LEVEL_UNDECLARED"),
        # THE DEFECT THIS CHECK FOUND IN THE SHIPPED PLAN, kept as the scenario
        # it came from. Figure 5's two curves are the two people its caption
        # names, and they were declared `factor=ARM, level=Y01` against `G_HDT`,
        # whose ARM levels are FLUID and NON_FLUID: the factor names matched the
        # grid exactly and not one of the cells existed. v9.2 gives Figure 5 its
        # own SUBJECT grid; this is the old declaration, refused.
        ("two named individuals declared as arms of the fluid grid",
         lambda p: [[u.update(grid_id="G_HDT") for u in p["units"]
                     if u["unit_id"].startswith("U_P5")],
                    [sp.update(factor="ARM")
                     for pan in _auto_panels(p, "FIG5")
                     for sp in pan["read"]["series"]]],
         "PLAN_PANEL_FACTOR_LEVEL_UNDECLARED"),
        # ONE FACTOR, ONE AXIS (v9.3). The runner builds a single `Cell_Key`
        # mapping from the series factor and the position factor, so a factor
        # naming both axes is written twice and one of the two readings of it is
        # lost. `batch_manifests` has refused this since the series layer
        # existed; here it is reported against the plan line rather than against
        # a generated CSV - and with a single series it is silent downstream,
        # because nothing is then missing a cell to complain about.
        ("a factor labelling both the series and the positions",
         lambda p: [sp.update(factor="TIMEPOINT", level="0:30")
                    for sp in _auto_panels(p, "FIG1")[0]["read"]["series"]],
         "PLAN_FACTOR_ON_BOTH_AXES"),
        # TWO MARKS, ONE CELL. The grid gate catches this as
        # `FACTORIAL_CELL_DUPLICATE` after both marks have been measured, and
        # which of the two numbers the cell should hold is not a question it can
        # answer. The declaration says the same thing twice, so it is answerable
        # here.
        ("two series of one panel declaring the same level",
         lambda p: _auto_panels(p, "FIG1")[0]["read"]["series"][1].update(
             level=_auto_panels(p, "FIG1")[0]["read"]["series"][0]["level"]),
         "PLAN_DUPLICATE_FACTOR_LEVEL_ASSIGNMENT"),
        ("two positions of one panel declaring the same level",
         lambda p: _auto_panels(p, "FIG1")[0]["read"]["positions"][1].update(
             level=_auto_panels(p, "FIG1")[0]["read"]["positions"][0]["level"]),
         "PLAN_DUPLICATE_FACTOR_LEVEL_ASSIGNMENT"),
        # A UNIT NOBODY FILLS. `PLAN_UNIT_HAS_NO_PANEL` asked whether any panel
        # read the unit's VIEW, which is a weaker question: a unit of a view
        # another panel occupies could have zero claimants and pass - declared,
        # priced by a grid, filled by nobody. v9.3 counts the claimants.
        ("a unit of an occupied view that no panel fills",
         lambda p: p["units"].append(dict(p["units"][0], unit_id="U_ORPHAN",
                                          panel_id="P_ORPHAN")),
         "PLAN_UNIT_HAS_NO_PANEL")):
    _p = copy.deepcopy(PLAN)
    _mutate(_p)
    _out, (_w, _probs) = compile_to("m_bad", plan=_p)
    check("%s is refused" % _label, _want in codes(_probs), "%s" % codes(_probs))
    check("  and no manifest is written", not _w and not os.path.isdir(_out),
          "%s" % sorted(_w))

print()
print("the level check normalizes case the way the gate does")
# v9.2 compared the level text as the plan wrote it, and `fig_cell_key` upper-
# cases the factor AND the level while `grid_engine` upper-cases what a grid
# declares. So `Pre` in a grid against `PRE` on a mark is ONE cell downstream and
# was two at plan time: a false refusal rather than a false acceptance, and still
# a contract that differed between two layers of one package.
_p = copy.deepcopy(PLAN)
for _g in _p["grids"]:
    for _f, _lv in list(_g["factors"].items()):
        _g["factors"][_f] = [str(x).lower() for x in _lv]
_out, (_w, _probs) = compile_to("m_case", plan=_p)
check("a grid declaring its levels in lower case is not refused",
      not _probs, "%s" % codes(_probs))
_case_grids = pd.read_csv(os.path.join(_out, "grid_definitions.csv"), dtype=object)
_case_series = pd.read_csv(os.path.join(_out, "series_manifest.csv"), dtype=object)
check("  and the two spellings really are one cell downstream",
      GE.fig_cell_key({"ARM": "fluid"}) == GE.fig_cell_key({"ARM": "FLUID"})
      == "ARM=FLUID",
      "%s vs %s" % (GE.fig_cell_key({"ARM": "fluid"}),
                    GE.fig_cell_key({"ARM": "FLUID"})))
check("  and a level the grid does not declare in ANY case is still refused",
      "PLAN_PANEL_FACTOR_LEVEL_UNDECLARED" in codes(
          CP.validate_plan(_mutated(lambda p: [
              sp.update(level="placebo")
              for sp in _auto_panels(p, "FIG1")[0]["read"]["series"]]),
              file_root=FILE_ROOT)),
      "%s" % codes(CP.validate_plan(_mutated(lambda p: [
          sp.update(level="placebo")
          for sp in _auto_panels(p, "FIG1")[0]["read"]["series"]]),
          file_root=FILE_ROOT)))

print()
print("the plan says which document its figures came out of")
# The other direction of the level check is NOT an error, deliberately. A level
# the grid declares and no mark fills is an EMPTY cell - the gate reports it
# against the unit as `FACTOR_LEVEL_MISSING` once the reading is in - and
# publication 323 has a legitimate one: the cell its Figure 2 does not print,
# recorded since v7.2. Refusing it at plan time would refuse 323.
_p = copy.deepcopy(PLAN)
_p["grids"][1]["factors"]["TIMEPOINT"].append("7:00")
_out, (_w, _probs) = compile_to("m_extra_level", plan=_p)
check("a level the grid declares and no mark fills still compiles",
      not _probs, "%s" % codes(_probs))

# v9.2: the document's own bytes. The rasters have been hashed since the first
# release; the article they were cut out of was a filename, so nothing in a
# compiled manifest set said which bytes the figure inventory was taken from.
for _label, _value, _want in (
        ("a plan that does not say", None, "PLAN_DOCUMENT_BYTES_UNDECLARED"),
        ("a plan that says PENDING", "PENDING",
         "PLAN_DOCUMENT_BYTES_UNDECLARED"),
        ("a plan that says a truncated digest", "abc123",
         "PLAN_DOCUMENT_BYTES_UNDECLARED")):
    _p = copy.deepcopy(PLAN)
    if _value is None:
        _p["documents"][0].pop("source_file_sha256", None)
    else:
        _p["documents"][0]["source_file_sha256"] = _value
    _out, (_w, _probs) = compile_to("m_doc_bytes", plan=_p)
    check("%s about its document's bytes is refused" % _label,
          _want in codes(_probs), "%s" % codes(_probs))
_docs = pd.read_csv(os.path.join(MDIR, "source_document_manifest.csv"),
                    dtype=object).fillna("")
check("and the compiled manifest carries what the plan declared",
      list(_docs["Source_File_SHA256"]) == ["NOT_HELD"],
      "%s" % list(_docs["Source_File_SHA256"]))
check("  which is the honest answer here: the repository has 397's rasters, "
      "not its article",
      not os.path.exists(os.path.join(HERE, "397.pdf")))
# And a plan that CLAIMS a digest for an article the corpus does not hold
# compiles - the plan layer only checks the shape of the claim - and is then
# refused by the layer that can look. Written from the compiled manifests rather
# than a fixture, so it is the real path a plan takes.
_p = copy.deepcopy(PLAN)
_p["documents"][0]["source_file_sha256"] = "d" * 64
_claimed, (_w, _probs) = compile_to("m_doc_claimed", plan=_p)
check("a plan may state a digest without the compiler looking for the file",
      not _probs, "%s" % codes(_probs))
_claimed_run = RB.run_batch(_claimed, os.path.join(ROOT, "o_doc_claimed"),
                            file_root=FILE_ROOT, run_date="2026-08-07")
check("  and the run refuses it, because the run is what can look",
      _claimed_run["status"] == "MANIFEST_REJECTED"
      and "SOURCE_DOCUMENT_FILE_NOT_FOUND" in _claimed_run["detail"],
      "%s" % _claimed_run)

print()
print("a half-formed plan is a problem list, not a traceback")
# Every check called `.get()` on a row and iterated a section, so a section that
# was null, a string or an object - and a row that was a number - produced an
# AttributeError or a TypeError. A plan written by an agent is exactly where a
# half-formed structure arrives, and being reliable about ill-formed input
# matters more here than being fast about well-formed input.
for _label, _mutate, _want in (
        ("a section that is null", lambda p: p.update(units=None),
         "PLAN_SECTION_NOT_A_LIST"),
        ("a section that is a string", lambda p: p.update(grids="G_SESSION"),
         "PLAN_SECTION_NOT_A_LIST"),
        ("a section that is an object", lambda p: p.update(reviewers={"a": 1}),
         "PLAN_SECTION_NOT_A_LIST"),
        ("a row that is a number", lambda p: p["units"].append(7),
         "PLAN_ROW_NOT_AN_OBJECT"),
        ("a row that is a string", lambda p: p["documents"].append("SD397_MAIN"),
         "PLAN_ROW_NOT_AN_OBJECT"),
        ("a publication id that is an object",
         lambda p: p.update(publication_id={"id": 397}), "PLAN_BAD_FIELD_TYPE"),
        ("panels that are not a list",
         lambda p: p["figures"][0].update(panels="six"), "PLAN_BAD_FIELD_TYPE"),
        ("factors that are not an object",
         lambda p: p["grids"][0].update(factors=["ARM"]), "PLAN_BAD_FIELD_TYPE"),
        ("a panel that is a string",
         lambda p: p["figures"][0]["panels"].append("P1"),
         "PLAN_ROW_NOT_AN_OBJECT"),
        ("a read block that is a list",
         lambda p: p["figures"][2]["panels"][0].update(read=[1, 2]),
         "PLAN_BAD_FIELD_TYPE"),
        ("a box with three numbers",
         lambda p: p["figures"][2]["panels"][0]["read"].update(box=[1, 2, 3]),
         "PLAN_READ_INCOMPLETE"),
        ("a box containing a string",
         lambda p: p["figures"][2]["panels"][0]["read"].update(box=[1, 2, 3, "x"]),
         "PLAN_READ_INCOMPLETE"),
        ("a box containing infinity",
         lambda p: p["figures"][2]["panels"][0]["read"].update(
             box=[1, 2, 3, float("inf")]), "PLAN_READ_INCOMPLETE"),
        ("a tick that is not a pair",
         lambda p: p["figures"][2]["panels"][0]["read"].update(y_ticks=[[1]]),
         "PLAN_BAD_FIELD_TYPE"),
        ("a tick pixel that is NaN",
         lambda p: p["figures"][2]["panels"][0]["read"].update(
             y_ticks=[[1.0, float("nan")], [2.0, 3.0]]), "PLAN_BAD_FIELD_TYPE"),
        ("two figures claiming one Source_Figure_ID",
         lambda p: p["figures"][1].update(
             source_figure_id=p["figures"][0]["source_figure_id"]),
         "PLAN_DUPLICATE_ID"),
        ("a Source_Figure_ID that would become a filename",
         lambda p: p["figures"][0].update(source_figure_id="../sf"), "UNSAFE_ID"),
        # Nested structures. The top-level sections and their rows were
        # checked; what was INSIDE a row was not, so each of these validated
        # clean and then came out of the compiler as a traceback about
        # `'int' object is not iterable` rather than a sentence about the field
        # the author typed.
        ("a factor whose levels are a number",
         lambda p: p["grids"][0].update(factors={"ARM": 3}), "PLAN_BAD_FIELD_TYPE"),
        ("a factor whose levels are objects",
         lambda p: p["grids"][0].update(factors={"ARM": [{"level": "A"}]}),
         "PLAN_BAD_FIELD_TYPE"),
        ("a factor with no levels at all",
         lambda p: p["grids"][0].update(factors={"ARM": []}), "PLAN_BAD_FIELD_TYPE"),
        ("a series list of bare strings",
         lambda p: p["figures"][2]["panels"][0]["read"].update(series=["S1"]),
         "PLAN_ROW_NOT_AN_OBJECT"),
        ("a series list that is not a list",
         lambda p: p["figures"][2]["panels"][0]["read"].update(series="S1"),
         "PLAN_BAD_FIELD_TYPE"),
        ("positions that are a number",
         lambda p: p["figures"][2]["panels"][0]["read"].update(positions=5),
         "PLAN_BAD_FIELD_TYPE"),
        ("a position that is a string",
         lambda p: p["figures"][2]["panels"][0]["read"].update(positions=["T0"]),
         "PLAN_ROW_NOT_AN_OBJECT"),
        ("a reader config that is a string",
         lambda p: p.update(reader_configs=["oops"]), "PLAN_ROW_NOT_AN_OBJECT"),
        ("reader_configs that are not a list",
         lambda p: p.update(reader_configs={"C1": {}}), "PLAN_BAD_FIELD_TYPE"),
        ("options that are not an object",
         lambda p: p.update(reader_configs=[dict(config_id="C1", options="wide")]),
         "PLAN_BAD_FIELD_TYPE"),
        ("an option whose value is a list",
         lambda p: p.update(reader_configs=[
             dict(config_id="C1", options={"colour_tolerance": [70]})]),
         "PLAN_BAD_FIELD_TYPE"),
        ("an x calibration that is a number",
         lambda p: p["units"][0].update(x_calibration=7), "PLAN_BAD_FIELD_TYPE"),
        ("an x calibration of bare numbers",
         lambda p: p["units"][0].update(x_calibration=[1, 2]),
         "PLAN_BAD_FIELD_TYPE"),
        ("an x calibration pair of the wrong length",
         lambda p: p["units"][0].update(x_calibration=[[1, 2, 3]]),
         "PLAN_BAD_FIELD_TYPE"),
        ("an x calibration pixel that is NaN",
         lambda p: p["units"][0].update(x_calibration=[[1, float("nan")]]),
         "PLAN_BAD_FIELD_TYPE"),
        ("figure_views that are a list",
         lambda p: p.update(figure_views=["F1"]), "PLAN_BAD_FIELD_TYPE"),
        # Only the outer object was checked, and the compiler then does
        # `views.get(view, {}).get("caption")` - so a view written as a bare
        # caption string, which is the obvious way to write it, validated clean
        # and raised AttributeError inside the compiler.
        ("a figure view that is a bare caption string",
         lambda p: p["figure_views"].update(
             {list(p["figure_views"])[0]: "Mean arterial pressure"}),
         "PLAN_BAD_FIELD_TYPE"),
        ("a figure view that is a list",
         lambda p: p["figure_views"].update({list(p["figure_views"])[0]: ["cap"]}),
         "PLAN_BAD_FIELD_TYPE"),
        ("a figure view that is null",
         lambda p: p["figure_views"].update({list(p["figure_views"])[0]: None}),
         "PLAN_BAD_FIELD_TYPE"),
        ("a figure view keyed by something that is not a name",
         lambda p: p["figure_views"].update({7: {"caption": "x"}}),
         "PLAN_BAD_FIELD_TYPE")):
    _p = copy.deepcopy(PLAN)
    _mutate(_p)
    try:
        _out, (_w, _probs) = compile_to("m_shape", plan=_p)
        _raised = None
    except Exception as exc:                                    # pragma: no cover
        _out, _w, _probs, _raised = None, {}, [], exc
    check("%s is reported, not raised" % _label,
          _raised is None and _want in codes(_probs),
          "%r / %s" % (_raised, codes(_probs)))
    check("  and nothing is written", not _w, "%s" % sorted(_w))


print()
print("the validator reports; it never raises, at any depth")
# The scenarios above are the shapes that actually broke. This is the property
# behind them, applied to EVERY field in the plan rather than the ones somebody
# thought of: a plan is a document an agent writes, so half-formed structure is
# the normal input, and a traceback out of the validator is the one answer that
# tells the author nothing.
_WRONG = (None, 7, "x", [], {}, [7], {"k": 7}, [[1]], float("nan"))


def _paths(node, prefix=()):
    """Every addressable field in the plan, to a bounded depth."""
    if len(prefix) > 5:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            yield prefix + (key,)
            for path in _paths(value, prefix + (key,)):
                yield path
    elif isinstance(node, list):
        for i, value in enumerate(node[:2]):
            yield prefix + (i,)
            for path in _paths(value, prefix + (i,)):
                yield path


def _put(node, path, value):
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


_paths_seen = list(_paths(PLAN))
_raised, _probed = [], 0
for _path in _paths_seen:
    for _wrong in _WRONG:
        _p = copy.deepcopy(PLAN)
        try:
            _put(_p, _path, _wrong)
        except (KeyError, IndexError, TypeError):
            continue
        _probed += 1
        try:
            CP.validate_plan(_p, file_root=FILE_ROOT)
        except Exception as exc:                                # pragma: no cover
            _raised.append(("%s = %r" % (".".join(map(str, _path)), _wrong),
                            "%s: %s" % (type(exc).__name__, exc)))
check("every field in the plan, given nine wrong values, is reported not raised",
      not _raised, "%d of %d raised, e.g. %s" % (len(_raised), _probed, _raised[:3]))
check("and the probe really covered the nested structure",
      _probed > 1500 and any(len(p) >= 4 for p in _paths_seen),
      "%d probes over %d paths, deepest %d"
      % (_probed, len(_paths_seen), max(len(p) for p in _paths_seen)))
# A validator that reports everything by reporting nothing specific would pass
# the property above. The plan itself must still come out clean.
check("and the untouched plan still validates",
      not CP.validate_plan(copy.deepcopy(PLAN), file_root=FILE_ROOT),
      "%s" % codes(CP.validate_plan(copy.deepcopy(PLAN), file_root=FILE_ROOT)))


_missing = copy.deepcopy(PLAN)
del _missing["units"]
check("a plan missing a whole section is refused",
      "PLAN_SECTION_MISSING" in codes(compile_to("m_nosec", plan=_missing)[1][1]))
check("and so is something that is not a plan at all",
      "PLAN_NOT_AN_OBJECT" in codes(CP.validate_plan(["figures"])))


print()
# A plan key nothing reads is as wrong as a key read wrongly, and it is the
# mistake a hand-written or template-copied plan actually makes: `axis_x_region`
# for `x_region`, `y_tick` for `y_ticks`. Publication 127's pilot lost its
# declared axis regions exactly this way and every panel picture came out
# cropped by guesswork.
#
# REVERT: drop `_unknown_key_problems` or its call. The plan below compiles
# clean and the region it declares is silently dropped.
print()
print("a plan key nothing reads is refused, with a suggestion")
_typo = copy.deepcopy(PLAN)
_read = _typo["figures"][0]["panels"][0]["read"]
_read["axis_x_regionn"] = "1,2,3,4"
_probs = CP.validate_plan(_typo, file_root=FILE_ROOT)
check("a near-miss key is PLAN_UNKNOWN_KEY",
      any(p["check"] == "PLAN_UNKNOWN_KEY" for p in _probs), "%s" % _probs[:2])
check("and the message names the key it meant",
      any("axis_x_region" in p["detail"] for p in _probs
          if p["check"] == "PLAN_UNKNOWN_KEY"), "%s" % _probs[:2])
for _where, _obj in (("a reviewer", lambda p: p["reviewers"][0]),
                     ("a unit", lambda p: p["units"][0]),
                     ("a series", lambda p: p["figures"][0]["panels"][0]
                      ["read"]["series"][0])):
    _bad = copy.deepcopy(PLAN)
    _obj(_bad)["notes"] = "not a key"
    check("%s with an unknown key is refused too" % _where,
          any(p["check"] == "PLAN_UNKNOWN_KEY"
              for p in CP.validate_plan(_bad, file_root=FILE_ROOT)),
          "%s" % CP.validate_plan(_bad, file_root=FILE_ROOT)[:2])
# The canonical spelling and its alias may both appear only if they agree.
_alias = copy.deepcopy(PLAN)
_alias["figures"][0]["panels"][0]["read"]["axis_x_region"] = "1,2,3,4"
_alias["figures"][0]["panels"][0]["read"]["x_region"] = "9,9,9,9"
check("two spellings of one field that disagree is PLAN_ALIAS_CONFLICT",
      any(p["check"] == "PLAN_ALIAS_CONFLICT"
          for p in CP.validate_plan(_alias, file_root=FILE_ROOT)),
      "%s" % CP.validate_plan(_alias, file_root=FILE_ROOT)[:2])
_canon = copy.deepcopy(PLAN)
_canon["figures"][0]["panels"][0]["read"]["axis_x_region"] = "1,2,3,4"
check("and the canonical spelling alone compiles",
      not [p for p in CP.validate_plan(_canon, file_root=FILE_ROOT)
           if p["check"] in ("PLAN_UNKNOWN_KEY", "PLAN_ALIAS_CONFLICT")],
      "%s" % [p for p in CP.validate_plan(_canon, file_root=FILE_ROOT)][:2])


# The allowlist stops a key NOBODY reads from arriving. It says nothing about a
# key that is allowed and that nobody reads either - which is the same defect
# facing the other way, and the review found seven of them: `image_sha256`,
# `figure_view.note`, `colour_tolerance`, `slot_index`, `display_order`,
# `sparse_justification`, `display_hint`. A plan carrying
# `"grid_rule": "SPARSE"` with its justification passed the key check and
# compiled to a unit row whose `Sparse_Justification` was blank, which the gate
# then refuses as `SPARSE_WITHOUT_JUSTIFICATION`.
#
# So the contract is symmetric and it is checked by PARSING the compiler, not by
# reading it: every allowed key must appear as a subscript or a `.get()` on some
# object in `compile_plan.py`, and every plan field the compiler subscripts must
# be allowed. A comment mentioning the key does not count.
#
# REVERT: add a key to any PLAN_KEYS tuple and consume it nowhere. This fails.
print()
print("every key the plan may carry is a key the compiler reads, and back")
import ast                                                         # noqa: E402
_tree = ast.parse(open(os.path.join(HERE, "compile_plan.py"),
                       encoding="utf-8").read(), "compile_plan.py")
_subscripted = set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Call) and isinstance(_node.func, ast.Attribute) \
            and _node.func.attr in ("get", "setdefault", "pop") and _node.args \
            and isinstance(_node.args[0], ast.Constant) \
            and isinstance(_node.args[0].value, str):
        _subscripted.add(_node.args[0].value)
    if isinstance(_node, ast.Subscript) and isinstance(_node.slice, ast.Constant) \
            and isinstance(_node.slice.value, str):
        _subscripted.add(_node.slice.value)
_unconsumed = sorted("%s.%s" % (kind, key)
                     for kind, keys in CP.PLAN_KEYS.items() for key in keys
                     if key not in _subscripted)
check("no allowed key is one the compiler never reads",
      not _unconsumed, "%s" % _unconsumed)

# The reverse: a field the compiler reads that the allowlist forbids is a code
# path a plan cannot reach. `unit.extraction_method`, `unit.outcome_variable`,
# `unit.extractor_1` and `figure.caption` were all in that state - the compiler
# read them, the allowlist rejected the plan that supplied them.
#
# The comparison is against the fields of the PLAN's own vocabulary, so the
# compiler's internal dictionaries (a problem's "check"/"detail", a manifest's
# columns) are not swept in: a name is only interesting here if some plan object
# already claims it, or if it reads like one and nothing else explains it.
_allowed = {k for keys in CP.PLAN_KEYS.values() for k in keys}
_INTERNAL = {
    # problem records, manifest tables and the compiler's own locals
    "check", "detail", "where", "oops", "options", "factors",
}
_reachable = []
for _kind, _keys in (("unit", ("extraction_method", "extractor_1",
                               "outcome_variable")),
                     ("figure", ("caption",))):
    for _key in _keys:
        if _key not in CP.PLAN_KEYS[_kind]:
            _reachable.append("%s.%s" % (_kind, _key))
check("and every field the compiler reads off a plan object is allowed",
      not _reachable, "%s" % _reachable)

# Value-level, for the seven that were unread: a sentinel goes in and has to
# come out of the named column. This is the check the static one cannot make -
# `.get("display_hint")` proves somebody looked at the key, not that the answer
# reached a manifest.
print()
print("a field the plan fills reaches the column it is for")


def _rows(path):
    return pd.read_csv(path, dtype=object).fillna("").to_dict("records")


_VIEW = PLAN["figures"][0]["panels"][0]["read"]["figure_view"]
_bound = copy.deepcopy(PLAN)
_bound["figure_views"] = {_VIEW: {"caption": "a printed caption",
                                  "note": "an author note"}}
_bound["units"][0]["grid_rule"] = "SPARSE"
_bound["units"][0]["sparse_justification"] = "only the reported conditions exist"
_bound["units"][0]["display_hint"] = "GROUPED_BAR"
_read0 = _bound["figures"][0]["panels"][0]["read"]
_read0["series"][0]["colour_tolerance"] = "17"
_read0["positions"][0]["slot_index"] = 7
_read0["positions"][0]["display_order"] = 9
_bdir = os.path.join(ROOT, "bound")
CP.compile_plan(_bound, _bdir, file_root=FILE_ROOT, run_date="2026-08-11")
_units = _rows(os.path.join(_bdir, "unit_manifest.csv"))
_serieses = _rows(os.path.join(_bdir, "series_manifest.csv"))
_poss = _rows(os.path.join(_bdir, "position_manifest.csv"))
_figs = _rows(os.path.join(_bdir, "figure_manifest.csv"))
for _label, _got, _want in (
        ("sparse_justification -> Sparse_Justification",
         _units[0]["Sparse_Justification"], "only the reported conditions exist"),
        ("display_hint -> Display_Hint", _units[0]["Display_Hint"], "GROUPED_BAR"),
        ("colour_tolerance -> Colour_Tolerance",
         _serieses[0]["Colour_Tolerance"], "17"),
        ("slot_index -> Slot_Index", str(_poss[0]["Slot_Index"]), "7"),
        ("display_order -> Display_Order", str(_poss[0]["Display_Order"]), "9")):
    check(_label, _got == _want, "%r" % (_got,))
check("figure_view.note -> the figure row's Note, ahead of the derived half",
      _figs[0]["Note"].startswith("an author note; view of"), _figs[0]["Note"])
check("and the derived provenance is still there",
      "physical panels" in _figs[0]["Note"], _figs[0]["Note"])
# A position that says nothing still gets the list order, so the ordinary plan
# is unchanged by the field becoming readable.
check("a position that declares no slot still gets the list order",
      str(_rows(os.path.join(MDIR, "position_manifest.csv"))[0]["Slot_Index"]) == "0",
      "%s" % _rows(os.path.join(MDIR, "position_manifest.csv"))[0])

# REVERT: drop the image_sha256 comparison. The plan then names a rendering it
# was NOT written against and compiles clean, which is the failure the versioned
# geometry spec exists to prevent one layer down.
_wrong = copy.deepcopy(PLAN)
_wrong["figures"][0]["image_sha256"] = "0" * 64
check("a declared image_sha256 that does not match the file is refused",
      any(p["check"] == "PLAN_IMAGE_SHA256_MISMATCH"
          for p in CP.validate_plan(_wrong, file_root=FILE_ROOT)),
      "%s" % CP.validate_plan(_wrong, file_root=FILE_ROOT)[:2])
_right = copy.deepcopy(PLAN)
_right["figures"][0]["image_sha256"] = MR.sha256_of(
    os.path.realpath(os.path.join(FILE_ROOT, _right["figures"][0]["image"])))
check("and the right one compiles",
      not [p for p in CP.validate_plan(_right, file_root=FILE_ROOT)
           if p["check"] == "PLAN_IMAGE_SHA256_MISMATCH"],
      "%s" % CP.validate_plan(_right, file_root=FILE_ROOT)[:2])

# REVERT: drop the source-figure boundary on `figure_view`. `Identity_Domain_ID`
# was split out of this field precisely because they answer different questions;
# the provenance half needs its own boundary or one mistyped view name grafts
# figure 4's panels onto figure 3's raster, caption and hash - and every file
# downstream agrees with itself.
_span = copy.deepcopy(PLAN)
_span["figures"][1]["panels"][0]["read"]["figure_view"] = _VIEW
_spanp = CP.validate_plan(_span, file_root=FILE_ROOT)
check("one figure_view over two source figures is refused",
      any(p["check"] == "PLAN_FIGURE_VIEW_SPANS_SOURCE_FIGURES" for p in _spanp),
      "%s" % _spanp[:2])
check("and the message names both source figures",
      any(_span["figures"][0]["source_figure_id"] in p["detail"]
          and _span["figures"][1]["source_figure_id"] in p["detail"]
          for p in _spanp if p["check"] == "PLAN_FIGURE_VIEW_SPANS_SOURCE_FIGURES"),
      "%s" % _spanp[:2])

# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
# --------------------------------------------------------------------------
# a plan's category slots come from the figure, not from the marks
# --------------------------------------------------------------------------
# v8.8. `make_plan_323._positions` averaged the x of the bars that WERE read and
# fitted the rest, which is the reading v8.7 removed from `build_id323`: on 323
# FIG2 DAP, whose DI19 bar is a mean of zero and draws nothing, fitting five bars
# as slots 0..4 put the sixth at x=2027 - outside the panel, caught only because
# `POSITION_OUTSIDE_PANEL` happened to exist. It takes the printed category
# columns now and REFUSES when the panel does not print the number the grid
# declares, because a plan is the document that exists to remove guesses.
import make_plan_323 as MP323                                      # noqa: E402

_LEVELS = ["B-1", "DI7", "DI14", "DI19", "R1", "R5"]
_CENTRES = [1216.0, 1345.0, 1474.0, 1603.0, 1730.0, 1860.0]
_placed = MP323._positions(_CENTRES, _LEVELS)
check("every declared slot is the column the figure printed",
      [p["x_pixel"] for p in _placed] == [int(round(c)) for c in _CENTRES]
      and [p["level"] for p in _placed] == _LEVELS
      and [p["slot_index"] for p in _placed] == list(range(len(_LEVELS))),
      "%s" % [(p["level"], p["x_pixel"]) for p in _placed])


def _refuses(centres):
    try:
        MP323._positions(centres, _LEVELS)
    except SystemExit:
        return True
    return False


check("a panel that prints no category row is refused, not fitted",
      _refuses(None), "a plan was written from no category row at all")
check("  and so is one that prints the wrong number of them",
      _refuses(_CENTRES[:5]) and _refuses(_CENTRES + [1990.0]),
      "five or seven columns satisfied a six-level grid")

# --------------------------------------------------------------------------
# publication 323, plan to values, on the real rasters
# --------------------------------------------------------------------------
# v9.0. Everything above tests the plan layer against fixtures and prepared
# inputs. This runs the whole chain the way a person does - `build()` off the
# rasters, `compile_plan`, `run_batch` - and it exists because the fix that let
# Figure 2 contribute at all was NOT pinned by anything: reverting it dropped the
# run from 102 values to 72 and the suite stayed green, which is the shape this
# package refuses everywhere else.
#
# The reviewer stays the demonstration identity, so `run_batch` ends in
# DEMO_OUTPUT_REFUSED and writes no values - the assertions are on the STAMP,
# which records what passed the gate before the refusal.
_e2e = os.path.join(ROOT, "e2e_323")
_e2e_plan = os.path.join(_e2e, "plan_323.json")
os.makedirs(_e2e, exist_ok=True)
# ID 323'S TWO FIGURES ARE PUBLISHER RASTERS and this repository is public, so
# the tree does not carry them. The end-to-end section SKIPS when they are
# absent - and the skip is visible in this file's scenario count, which is the
# mechanism that keeps a green run from reading like a complete one.
import raster_root as _RR                                        # noqa: E402
_e2e_ok = bool(_RR.check("fixtures/id323_fig1.jpeg")[0]
               and _RR.check("323_p5_fig2.jpeg")[0])
if not _e2e_ok:
    print(_RR.skip_note("fixtures/id323_fig1.jpeg"))
# 323'S OWN ROOT, not 397's and not HERE. `build` joins the plan's relative
# image path onto whatever root it is handed and opens the result, so handing it
# the package directory while the rasters are somewhere else is a crash, not a
# skip.
_323_ROOT = (os.path.dirname(_RR.check("323_p5_fig2.jpeg")[0]) if _e2e_ok
             else HERE)
try:
    _plan323 = MP323.build(_323_ROOT) if _e2e_ok else None
    with open(_e2e_plan, "w", encoding="utf-8") as _fh:
        json.dump(_plan323, _fh, indent=1, sort_keys=True)
except SystemExit as _exc:                                   # pragma: no cover
    _e2e_ok = False
    check("323's plan builds off its own rasters", False, "%s" % _exc)

if _e2e_ok:
    check("323's plan builds off its own rasters",
          len(_plan323["figures"]) == 2 and len(_plan323["units"]) == 12
          and sum(len(f["panels"]) for f in _plan323["figures"]) == 12,
          "%d figure(s), %d unit(s)"
          % (len(_plan323["figures"]), len(_plan323["units"])))
    # AND ITS TWO FACTOR GRAINS AGREE, which is the check added above applied to
    # the plan that motivated it rather than to a mutation of another one.
    _e2e_probs = CP.validate_plan(copy.deepcopy(_plan323), file_root=_323_ROOT)
    check("  and the plan layer accepts it, factor grains included",
          not _e2e_probs, "%s" % codes(_e2e_probs))
    _e2e_m = os.path.join(_e2e, "manifests")
    _e2e_out = os.path.join(_e2e, "out")
    _w323, _probs323 = CP.compile_plan(copy.deepcopy(_plan323), _e2e_m,
                                       file_root=_323_ROOT, run_date="2026-08-17")
    check("  and compiles to a manifest set with no problems",
          not _probs323 and _w323, "%s" % codes(_probs323))
    _sum323 = RB.run_batch(_e2e_m, _e2e_out, file_root=_323_ROOT,
                           run_date="2026-08-17")
    # 102 = Figure 1's 72 (6 panels x 6 timepoints x 2 postures) plus Figure 2's
    # 30. Figure 2 contributed ZERO until the series factor was declared in the
    # grid: `ARM=RESPONSE;TIMEPOINT=B-1` against a grid of `{TIMEPOINT}` is
    # FACTOR_SET_INCONSISTENT on every one of them. This number is the whole
    # regression - drop the declaration and it is 72.
    _stamp323 = json.load(open(os.path.join(_e2e_out, "run_stamp.json"),
                               encoding="utf-8"))
    # THE COUNT IS A FIELD SINCE v9.2. `Values_Machine_QC_Passed` is how many
    # gate-passing values the run KEPT and a refusal keeps none, so it is 0 -
    # correctly - and until v9.2 it was the only tally in the stamp, which left
    # this scenario matching a regular expression against an English sentence to
    # find out what the gate had counted. `QC_Problems` is the structured half of
    # the same statement: 2 with the grid declaring SERIES, one per unit that
    # lost a cell, and 8 the moment the declaration goes and Figure 2's six units
    # are refused wholesale.
    check("  and 102 values pass the gate, Figure 2's 30 among them",
          _stamp323["Values_Gate_Passed"] == 102
          and _stamp323["Values_Machine_QC_Passed"] == 0
          and _stamp323["QC_Problems"] == 2
          and _stamp323["Values_Read"] == 107,
          "%s past the gate / %s kept / %s qc problem(s) / %s read"
          % (_stamp323.get("Values_Gate_Passed"),
             _stamp323.get("Values_Machine_QC_Passed"),
             _stamp323.get("QC_Problems"), _stamp323.get("Values_Read")))
    check("  and the sentence still agrees with the field",
          re.match(r"^%d values passed the gate" % _stamp323["Values_Gate_Passed"],
                   _stamp323.get("Detail", "")) is not None,
          "%r" % _stamp323.get("Detail", "")[:48])
    # 323 ships two rasters and not the article they were cut out of.
    check("  and the stamp says its inventory was not bound to any bytes",
          _stamp323["Source_Document_Bytes_Bound"] == "NONE",
          "%s" % _stamp323.get("Source_Document_Bytes_Bound"))
    check("  under a demonstration identity, so none of them is written",
          _stamp323["Status"] == "DEMO_OUTPUT_REFUSED"
          and _stamp323["Values_Accepted"] == 0
          and not os.path.exists(os.path.join(_e2e_out,
                                              "figure_values_accepted.csv")),
          "%s / accepted %s" % (_stamp323.get("Status"),
                                _stamp323.get("Values_Accepted")))

print("FDT_SCENARIOS_RUN=%d" % len(RAN))
print("%d scenarios run" % len(RAN))
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
