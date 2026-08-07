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
check("and the pilot's 48 read values", _summary["values"] == 48, "%s" % _summary)
check("and nothing accepted, because the paper still does not say SD or SEM",
      _summary["accepted"] == 0, "%s" % _summary)
_states = _summary["states"]
check("and the same three terminal states",
      _states == {"QC_FAILED": 12, "NO_READER_AVAILABLE": 4, "MANUAL_POINT_READ": 2},
      "%s" % _states)
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
