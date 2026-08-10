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
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compile_plan as CP                                          # noqa: E402
import run_batch as RB                                             # noqa: E402

ROOT = tempfile.mkdtemp(prefix="fdt_plan_")
FAILURES, RAN = [], []


def check(name, ok, detail=""):
    RAN.append(name)
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "  <- %s" % detail))
    if not ok:
        FAILURES.append(name)


PLAN_PATH = os.path.join(HERE, "plan_397.json")
if not os.path.exists(PLAN_PATH):
    print("BLOCKED: plan_397.json is not in the package", file=sys.stderr)
    raise SystemExit(2)
with open(PLAN_PATH, encoding="utf-8") as fh:
    PLAN = json.load(fh)


def compile_to(name, plan=None, file_root=HERE):
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    return out, CP.compile_plan(plan if plan is not None else copy.deepcopy(PLAN),
                                out, file_root=file_root, run_date="2026-08-07")


def codes(problems):
    return sorted({p["check"] for p in problems})


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
_summary = RB.run_batch(MDIR, _ODIR, file_root=HERE, run_date="2026-08-07")
check("the compiled batch runs", _summary["status"] == "RAN", "%s" % _summary)
check("with the pilot's panel count", _summary["panels"] == 18, "%s" % _summary)
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
check("and the 36 values the two-pass reader stands behind",
      _summary["values"] == 36, "%s" % _summary)
check("and nothing accepted, because the paper still does not say SD or SEM",
      _summary["accepted"] == 0, "%s" % _summary)
_states = _summary["states"]
check("and the same three terminal states",
      _states == {"QC_FAILED": 9, "NO_READER_AVAILABLE": 4,
                  "MANUAL_POINT_READ": 5},
      "%s" % _states)
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
         "PLAN_SCHEMA_UNKNOWN")):
    _p = copy.deepcopy(PLAN)
    _mutate(_p)
    _out, (_w, _probs) = compile_to("m_bad", plan=_p)
    check("%s is refused" % _label, _want in codes(_probs), "%s" % codes(_probs))
    check("  and no manifest is written", not _w and not os.path.isdir(_out),
          "%s" % sorted(_w))

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
            CP.validate_plan(_p, file_root=HERE)
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
      not CP.validate_plan(copy.deepcopy(PLAN), file_root=HERE),
      "%s" % codes(CP.validate_plan(copy.deepcopy(PLAN), file_root=HERE)))


_missing = copy.deepcopy(PLAN)
del _missing["units"]
check("a plan missing a whole section is refused",
      "PLAN_SECTION_MISSING" in codes(compile_to("m_nosec", plan=_missing)[1][1]))
check("and so is something that is not a plan at all",
      "PLAN_NOT_AN_OBJECT" in codes(CP.validate_plan(["figures"])))


print()
print("%d scenarios run" % len(RAN))
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
