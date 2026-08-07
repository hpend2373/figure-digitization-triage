"""Regression suite for the four-grain grid + value engine.

    python test_grid_engine.py       # exit 0 = all scenarios pass

Scenarios describe LAYOUTS and DATA TYPES, never studies. If one ever needs a
publication ID in it, the design has regressed.

Every counter-example that once returned "0 problems" is here as a named case.
"""
import importlib.util
import itertools
import os
import shutil
import sys
import tempfile
import hashlib

import pandas as pd
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grid_engine as G  # noqa: E402

spec = importlib.util.spec_from_file_location("fdt", os.path.join(HERE, "kernel.py"))
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)

FAILURES, PASSED = [], [0]

# The existence check is on by default, so the harness needs real files to point
# at. Creating them here keeps the check exercised instead of switched off.
_TMPDIR = tempfile.mkdtemp(prefix="fdt_grid_")
_IMAGE_PATH = os.path.join(_TMPDIR, "f.png")
Image.new("RGB", (8, 6), "white").save(_IMAGE_PATH)
_IMAGE_SHA = hashlib.sha256(open(_IMAGE_PATH, "rb").read()).hexdigest()
open(os.path.join(_TMPDIR, "p.tar"), "wb").write(b"placeholder")


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


FIG = dict(Figure_ID="F1", Publication_ID=1, Source_File="x.pdf", Source_Page=4,
           Source_Image=os.path.join(_TMPDIR, "f.png"), Source_Caption_Verbatim="cap",
           Figure_Number="FIG1", Image_Resolution_Or_Hash="8x6 sha256:" + _IMAGE_SHA,
           WPD_Project_File=os.path.join(_TMPDIR, "p.tar"),
           Observed_Panel_Count=1, Worklist_Panel_Count=1, Unlisted_Panels="",
           Panel_Reconciliation_Status="MATCHED", Note="")
UNIT = dict(Unit_ID="U1", Figure_ID="F1", Grid_ID="G1", Panel="A",
            Outcome_Variable="Heart rate", Outcome_Domain="CV", Unit="bpm",
            Statistic_Type="CONTINUOUS", Display_Hint="UNSPECIFIED", Grid_Rule="FULL",
            Sparse_Justification="", Dispersion_Type="SEM",
            Errorbar_Definition_Source="caption: mean +/- SEM", N_Outcome=10,
            Value_Scale="RATIO", Extraction_Method="DIGITIZED",
            Bar_Top_Definition="OUTLINE_CENTER", Errorbar_Stem_Confirmed="TRUE",
            Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
            Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
            Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=400,
            Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=500,
            Axis_Calib_Y2_Value=150, Axis_Calib_Y2_Pixel=100,
            Extractor_1="r1", Extractor_2="", Independent_Verification_Status="",
            Discrepancy_Note="", Date="2026-08-06", Note="")


def fr(rows, cols):
    return pd.DataFrame([{c: d.get(c, "") for c in cols} for d in rows], columns=cols)


def run(factors=None, cells=None, fig=None, unit=None, vals=None, grid=None, **kw):
    factors = factors or {"PHASE": ["PRE", "POST"]}
    if grid is None:
        grid = [dict(Grid_ID="G1", Factor_Name=f, Factor_Level=lv, Level_Order=i, Note="")
                for f, lvs in factors.items() for i, lv in enumerate(lvs)]
    if cells is None:
        cells = [dict(zip(factors, c)) for c in itertools.product(*factors.values())]
    if vals is None:
        vals = [dict(Unit_ID="U1", Cell_Key=G.fig_cell_key(c), Mean=60 + i,
                     Dispersion_Value=3) for i, c in enumerate(cells)]
    p = G.fig_validate_bundle(fr([dict(FIG, **(fig or {}))], G.fig_figure_columns()),
                              fr(grid, G.fig_grid_columns()),
                              fr([dict(UNIT, **(unit or {}))], G.fig_unit_columns()),
                              fr(vals, G.fig_values_columns()), kernel=k, **kw)
    return sorted(set(p["check"])) if len(p) else []


SESS = ["B-1", "DI7", "DI14", "DI19", "R1", "R5"]
POST = ["SUPINE", "ORTHOSTASIS"]

print("kernel is not optional")
try:
    G.fig_validate_bundle(fr([FIG], G.fig_figure_columns()),
                          fr([dict(Grid_ID="G1", Factor_Name="PHASE", Factor_Level="PRE",
                                   Level_Order=0, Note="")], G.fig_grid_columns()),
                          fr([UNIT], G.fig_unit_columns()),
                          fr([], G.fig_values_columns()), kernel=None)
    check("calling without a kernel raises", False, "it returned instead")
except ValueError:
    check("calling without a kernel raises", True)

print("one engine, many layouts")
for name, factors, n in (
        ("6 timepoints x 2 postures", {"TIMEPOINT": SESS, "POSTURE": POST}, 12),
        ("bare 6-level time course", {"TIMEPOINT": SESS}, 6),
        ("two-cell pre/post", {"PHASE": ["PRE", "POST"]}, 2),
        ("4 gravity x 3 load", {"GRAVITY": ["0G", "0.5G", "1G", "1.5G"],
                                "LOAD": ["LOW", "MID", "HIGH"]}, 12),
        ("arm x sex x timepoint", {"ARM": ["CON", "EX"], "SEX": ["M", "F"],
                                   "TIMEPOINT": ["PRE", "POST"]}, 8)):
    got = run(factors)
    check("%s (%d cells) validates" % (name, n), got == [], "%s" % got)

print("the grid codes are universal")
full = {"TIMEPOINT": SESS, "POSTURE": POST}
cells = [dict(zip(full, c)) for c in itertools.product(*full.values())]
CASES = [
    ("a missing cell", dict(factors=full, cells=cells[:-1]), "FACTORIAL_CELL_MISSING"),
    ("a repeated combination", dict(factors=full, cells=cells + [cells[0]]),
     "FACTORIAL_CELL_DUPLICATE"),
    ("a level never read", dict(factors=full,
                                cells=[c for c in cells if c["TIMEPOINT"] != "R5"]),
     "FACTOR_LEVEL_MISSING"),
    ("a level outside the declaration",
     dict(factors=full, cells=cells[:-1] + [{"TIMEPOINT": "R9", "POSTURE": "SUPINE"}]),
     "UNDECLARED_FACTOR_LEVEL"),
    ("a cell using different factors",
     dict(factors=full, cells=cells[:-1] + [{"TIMEPOINT": "R5", "ARM": "CON"}]),
     "FACTOR_SET_INCONSISTENT"),
    ("a factor repeated inside one Cell_Key",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=PRE;PHASE=POST", Mean=60,
                     Dispersion_Value=3)]), "BAD_CELL_KEY"),
    ("Level_Order repeated",
     dict(grid=[dict(Grid_ID="G1", Factor_Name="PHASE", Factor_Level=lv, Level_Order=0,
                     Note="") for lv in ("PRE", "POST")]), "BAD_LEVEL_ORDER"),
    ("Level_Order fractional",
     dict(grid=[dict(Grid_ID="G1", Factor_Name="PHASE", Factor_Level=lv, Level_Order=i + 0.5,
                     Note="") for i, lv in enumerate(("PRE", "POST"))]), "BAD_LEVEL_ORDER"),
    ("Level_Order not contiguous",
     dict(grid=[dict(Grid_ID="G1", Factor_Name="PHASE", Factor_Level=lv, Level_Order=i * 5,
                     Note="") for i, lv in enumerate(("PRE", "POST"))]), "BAD_LEVEL_ORDER"),
]
for name, kw, want in CASES:
    check(name + " -> " + want, want in run(**kw), "%s" % run(**kw))

print("the counter-examples that used to pass clean")
COUNTER = [
    ("Extraction_Method=BOGUS", dict(unit={"Extraction_Method": "BOGUS"}),
     "BAD_EXTRACTION_METHOD"),
    ("FILL_EDGE", dict(unit={"Bar_Top_Definition": "FILL_EDGE"}),
     "BAR_TOP_READ_AT_FILL_EDGE"),
    ("stem unconfirmed", dict(unit={"Errorbar_Stem_Confirmed": ""}),
     "ERRORBAR_STEM_UNCONFIRMED"),
    ("panels 6/5 called MATCHED",
     dict(fig={"Observed_Panel_Count": 6, "Worklist_Panel_Count": 5}),
     "PANEL_STATUS_CONTRADICTS_COUNTS"),
    ("caption missing", dict(fig={"Source_Caption_Verbatim": ""}), "MISSING_PROVENANCE"),
    ("axis calibration missing", dict(unit={"Axis_Calib_Y1_Pixel": ""}),
     "MISSING_PROVENANCE"),
    ("N=0", dict(unit={"N_Outcome": 0}), "N_INVALID"),
    ("N fractional", dict(unit={"N_Outcome": 7.5}), "N_INVALID"),
    ("Dispersion_Type=BANANA", dict(unit={"Dispersion_Type": "BANANA"}),
     "BAD_DISPERSION_TYPE"),
    ("Value_Scale blank", dict(unit={"Value_Scale": ""}), "BAD_VALUE_SCALE"),
    ("dispersion blank",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60)
                for lv in ("PRE", "POST")]), "MISSING_DISPERSION"),
    ("dispersion negative",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60, Dispersion_Value=-3)
                for lv in ("PRE", "POST")]), "DISPERSION_NONPOSITIVE"),
    ("Mean blank",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv) for lv in ("PRE", "POST")]),
     "MISSING_REQUIRED"),
    ("Mean is text",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean="sixty",
                     Dispersion_Value=3) for lv in ("PRE", "POST")]), "NON_NUMERIC_VALUE"),
    ("error bar bounds inverted",
     dict(unit={"Dispersion_Type": "CI95"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60, Errorbar_Lower=70,
                     Errorbar_Upper=50) for lv in ("PRE", "POST")]),
     "ERRORBAR_BOUNDS_INVERTED"),
    ("events exceed the denominator",
     dict(unit={"Statistic_Type": "BINARY_EVENT"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Events=15, N_at_Risk=10)
                for lv in ("PRE", "POST")]), "EVENTS_EXCEED_N"),
    ("denominator zero",
     dict(unit={"Statistic_Type": "BINARY_EVENT"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Events=0, N_at_Risk=0)
                for lv in ("PRE", "POST")]), "N_AT_RISK_INVALID"),
]
for label in ("PEARSON_R", "Pearson correlation", "spearman"):
    COUNTER.append(("r=1.5 CI[-2,2] N=1 p=1.4 as %r" % label,
                    dict(unit={"Statistic_Type": "ASSOCIATION"},
                         vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv,
                                    Association_Type=label, Association_Value=1.5,
                                    CI_Lower=-2, CI_Upper=2, N_Pairs=1, P_Value=1.4)
                               for lv in ("PRE", "POST")]),
                    ["ASSOCIATION_VALUE_OUT_OF_RANGE", "ASSOCIATION_CI_OUT_OF_RANGE",
                     "N_PAIRS_TOO_SMALL", "P_VALUE_OUT_OF_RANGE"]))
for name, kw, want in COUNTER:
    wants = [want] if isinstance(want, str) else want
    got = run(**kw)
    check(name, all(w in got for w in wants), "missing %s" % [w for w in wants if w not in got])

print("dual extraction covers every reader column")
DUAL = [
    ("continuous: dispersion read once",
     dict(unit={"Extractor_2": "r2", "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60, Dispersion_Value=3,
                     Mean_R1=60, Mean_R2=60) for lv in ("PRE", "POST")]),
     "NO_INDEPENDENT_READINGS"),
    ("binary: denominator read once",
     dict(unit={"Statistic_Type": "BINARY_EVENT", "Extractor_2": "r2",
                "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Events=3, N_at_Risk=10,
                     Events_R1=3, Events_R2=3) for lv in ("PRE", "POST")]),
     "NO_INDEPENDENT_READINGS"),
    ("binary: counts must match exactly",
     dict(unit={"Statistic_Type": "BINARY_EVENT", "Extractor_2": "r2",
                "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Events=3, N_at_Risk=10,
                     Events_R1=3, Events_R2=4, N_at_Risk_R1=10, N_at_Risk_R2=10)
                for lv in ("PRE", "POST")]), "DUAL_READINGS_DISAGREE"),
    ("association: statistic read once",
     dict(unit={"Statistic_Type": "ASSOCIATION", "Extractor_2": "r2",
                "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Association_Type="PEARSON_R",
                     Association_Value=0.5, N_Pairs=12) for lv in ("PRE", "POST")]),
     "NO_INDEPENDENT_READINGS"),
    ("no second extractor named",
     dict(vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60, Dispersion_Value=3,
                     Mean_R1=60, Mean_R2=60, Dispersion_R1=3, Dispersion_R2=3)
                for lv in ("PRE", "POST")]), "NO_SECOND_EXTRACTOR"),
]
for name, kw, want in DUAL:
    got = run(require_dual=True, **kw)
    check(name, want in got, "%s" % got)
check("a fully dual-read unit passes",
      run(require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60, Dispersion_Value=3,
                     Mean_R1=60, Mean_R2=61, Dispersion_R1=3, Dispersion_R2=3.1)
                for lv in ("PRE", "POST")]) == [],
      "%s" % run(require_dual=True,
                 unit={"Extractor_2": "r2", "Independent_Verification_Status": "AGREED"},
                 vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60,
                            Dispersion_Value=3, Mean_R1=60, Mean_R2=61,
                            Dispersion_R1=3, Dispersion_R2=3.1)
                       for lv in ("PRE", "POST")]))

print("independent means independent, and reconciliation is cell-level")
check("the same named extractor cannot be both readings",
      "SAME_EXTRACTOR" in run(
          require_dual=True,
          unit={"Extractor_1": "reader", "Extractor_2": "reader",
                "Independent_Verification_Status": "AGREED"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv,
                     Mean=60, Dispersion_Value=3, Mean_R1=60, Mean_R2=60,
                     Dispersion_R1=3, Dispersion_R2=3) for lv in ("PRE", "POST")]))
_mixed = [
    dict(Unit_ID="U1", Cell_Key="PHASE=PRE", Mean=70, Dispersion_Value=3,
         Mean_R1=60, Mean_R2=80, Dispersion_R1=3, Dispersion_R2=3,
         Verification_Status="RECONCILED", Reconciliation_Note="R2 used the wrong cap"),
    dict(Unit_ID="U1", Cell_Key="PHASE=POST", Mean=70, Dispersion_Value=3,
         Mean_R1=60, Mean_R2=80, Dispersion_R1=3, Dispersion_R2=3),
]
_mixed_result = run(
    require_dual=True,
    unit={"Extractor_2": "r2", "Independent_Verification_Status": "RECONCILED",
          "Discrepancy_Note": "one or more cells adjudicated"}, vals=_mixed)
check("one reconciled cell cannot waive disagreement in another cell",
      "DUAL_READINGS_DISAGREE" in _mixed_result, "%s" % _mixed_result)
_cell_note_missing = [dict(row) for row in _mixed]
_cell_note_missing[0]["Reconciliation_Note"] = ""
check("a reconciled cell needs its own adjudication note",
      "CELL_RECONCILED_WITHOUT_NOTE" in run(
          require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "RECONCILED",
                "Discrepancy_Note": "unit summary"}, vals=_cell_note_missing))

print("zero means different things on different scales")
near_zero = dict(unit={"Value_Scale": "CHANGE", "Outcome_Variable": "Change of heart rate",
                       "Unit": "%"},
                 vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=0.4,
                            Dispersion_Value=3.2) for lv in ("PRE", "POST")])
check("a change score may carry an SD larger than its mean",
      "SE_IMPLIES_HUGE_SD" not in run(**near_zero), "%s" % run(**near_zero))
ratio_zero = dict(unit={"Value_Scale": "RATIO"},
                  vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=60,
                             Dispersion_Value=40) for lv in ("PRE", "POST")])
check("a ratio-scale outcome still cannot",
      "SE_IMPLIES_HUGE_SD" in run(**ratio_zero), "%s" % run(**ratio_zero))
check("an unknown scale is flagged", "BAD_VALUE_SCALE" in run(unit={"Value_Scale": "ORDINAL"}))

print("sparse grids need a stated reason")
hole = cells[:-1]
check("SPARSE without justification",
      "SPARSE_WITHOUT_JUSTIFICATION" in run(factors=full, cells=hole,
                                            unit={"Grid_Rule": "SPARSE"}))
check("SPARSE with a placeholder",
      "SPARSE_WITHOUT_JUSTIFICATION" in run(
          factors=full, cells=hole,
          unit={"Grid_Rule": "SPARSE", "Sparse_Justification": "TBD"}))
_s = run(factors=full, cells=hole,
         unit={"Grid_Rule": "SPARSE",
               "Sparse_Justification": "the final tilt was cancelled for the last subject"})
check("SPARSE with a real reason passes", _s == [], "%s" % _s)
check("SPARSE cannot hide a level read zero times",
      "FACTOR_LEVEL_MISSING" in run(
          factors=full, cells=[c for c in cells if c["TIMEPOINT"] != "R5"],
          unit={"Grid_Rule": "SPARSE", "Sparse_Justification": "R5 tilt cancelled"}))

print("Display_Hint never changes a verdict")
for hint in ("A_CHALLENGE_TIMECOURSE", "B_CHALLENGE_2POINT", "D_SIMPLE_PREPOST",
             "G_FACTORIAL_CONDITIONS", "UNSPECIFIED"):
    check("hint %s: clean stays clean" % hint,
          run(factors=full, unit={"Display_Hint": hint}) == [])
    check("hint %s: failure stays the same" % hint,
          run(factors=full, cells=cells[:-1], unit={"Display_Hint": hint})
          == ["FACTORIAL_CELL_MISSING"])
check("an unknown hint is flagged, nothing branches on it",
      run(unit={"Display_Hint": "Z_MADE_UP"}) == ["BAD_DISPLAY_HINT"])

print("one grid definition serves many units")
grid = [dict(Grid_ID="G1", Factor_Name=f, Factor_Level=lv, Level_Order=i, Note="")
        for f, lvs in full.items() for i, lv in enumerate(lvs)]
check("a shared grid is declared once, not once per panel",
      len(grid) == len(SESS) + len(POST) and G.fig_expected_cell_count(
          fr(grid, G.fig_grid_columns()), "G1") == 12,
      "%d rows" % len(grid))

print("the shipped templates are the schema")
import csv as _csv
_T = {"figure_manifest_TEMPLATE.csv": G.fig_figure_columns(),
      "grid_definitions_TEMPLATE.csv": G.fig_grid_columns(),
      "unit_manifest_TEMPLATE.csv": G.fig_unit_columns(),
      "figure_values_TEMPLATE.csv": G.fig_values_columns()}
for _f, _cols in _T.items():
    _p = os.path.join(HERE, _f)
    _hdr = next(_csv.reader(open(_p, encoding="utf-8"))) if os.path.exists(_p) else []
    check("%s matches its column function" % _f, _hdr == _cols,
          "missing %s" % [c for c in _cols if c not in _hdr])
_empty = [pd.read_csv(os.path.join(HERE, f)) for f in _T]
_p = G.fig_validate_bundle(*_empty, kernel=k)
check("the four empty templates raise no SCHEMA_INCOMPLETE",
      "SCHEMA_INCOMPLETE" not in set(_p["check"]) if len(_p) else True,
      "%s" % (sorted(set(_p["check"])) if len(_p) else ""))

print("provenance that cannot be followed is not provenance")
for _c, _w in (("WPD_Project_File", "MISSING_PROVENANCE"),):
    check("blank %s on the figure -> %s" % (_c, _w), _w in run(fig={_c: ""}))
for _c in ("Axis_X_Scale", "Axis_Y_Scale"):
    check("blank %s -> MISSING_PROVENANCE" % _c,
          "MISSING_PROVENANCE" in run(unit={_c: ""}))
check("an image path that is not on disk is flagged",
      "SOURCE_FILE_NOT_FOUND" in run(fig={"Source_Image": "no_such_image.png"}))
check("a WPD project that is not on disk is flagged",
      "SOURCE_FILE_NOT_FOUND" in run(fig={"WPD_Project_File": "no_such_project.tar"}))
check("check_files=False makes the absence a stated choice, not silence",
      "SOURCE_FILE_NOT_FOUND" not in run(fig={"Source_Image": "no_such_image.png"},
                                         check_files=False))
check("a wrong recorded image digest is rejected",
      "IMAGE_HASH_MISMATCH" in run(fig={"Image_Resolution_Or_Hash": "8x6 sha256:deadbeef"}))
check("a wrong recorded image dimension is rejected",
      "IMAGE_DIMENSION_MISMATCH" in run(fig={"Image_Resolution_Or_Hash": "9x6 sha256:" + _IMAGE_SHA}))
check("an image identity with neither dimensions nor hash is rejected",
      "IMAGE_HASH_UNPARSEABLE" in run(
          fig={"Image_Resolution_Or_Hash": "high quality scan"}))
check("check_files=False skips disk access, not identity syntax",
      "IMAGE_HASH_UNPARSEABLE" in run(
          fig={"Source_Image": "not_present.png",
               "Image_Resolution_Or_Hash": "high quality scan"},
          check_files=False))
for _n in (1, 2):
    check("a LOG axis calibrated at zero -> LOG_AXIS_NONPOSITIVE_CALIBRATION",
          "LOG_AXIS_NONPOSITIVE_CALIBRATION" in run(
              unit={"Axis_Y_Scale": "LOG", "Axis_Calib_Y%d_Value" % _n: 0}))
check("a LOG axis calibrated at a negative value is flagged",
      "LOG_AXIS_NONPOSITIVE_CALIBRATION" in run(
          unit={"Axis_X_Scale": "LOG", "Axis_Calib_X1_Value": -5}))
check("a LOG axis calibrated positively is fine",
      "LOG_AXIS_NONPOSITIVE_CALIBRATION" not in run(
          unit={"Axis_Y_Scale": "LOG", "Axis_Calib_Y1_Value": 1,
                "Axis_Calib_Y2_Value": 100}))

print("the comparator arm is checked like the index arm")
_bin = {"Statistic_Type": "BINARY_EVENT"}
def _bv(**kw):
    return [dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Events=3, N_at_Risk=10, **kw)
            for lv in ("PRE", "POST")]
check("negative comparator events",
      "EVENTS_INVALID" in run(unit=_bin, vals=_bv(Events_Comparator=-1,
                                                  N_at_Risk_Comparator=10)))
check("comparator denominator zero",
      "N_AT_RISK_INVALID" in run(unit=_bin, vals=_bv(Events_Comparator=1,
                                                     N_at_Risk_Comparator=0)))
check("fractional comparator events",
      "EVENTS_INVALID" in run(unit=_bin, vals=_bv(Events_Comparator=1.5,
                                                  N_at_Risk_Comparator=10)))
check("comparator denominator read only once",
      "NO_INDEPENDENT_READINGS" in run(
          require_dual=True,
          unit=dict(_bin, Extractor_2="r2", Independent_Verification_Status="AGREED"),
          vals=_bv(Events_R1=3, Events_R2=3, N_at_Risk_R1=10, N_at_Risk_R2=10,
                   Events_Comparator=1, Events_Comparator_R1=1, Events_Comparator_R2=1,
                   N_at_Risk_Comparator=10)))
check("a fully dual-read comparator passes",
      run(require_dual=True,
          unit=dict(_bin, Extractor_2="r2", Independent_Verification_Status="AGREED"),
          vals=_bv(Events_R1=3, Events_R2=3, N_at_Risk_R1=10, N_at_Risk_R2=10,
                   Events_Comparator=1, Events_Comparator_R1=1, Events_Comparator_R2=1,
                   N_at_Risk_Comparator=10, N_at_Risk_Comparator_R1=10,
                   N_at_Risk_Comparator_R2=10)) == [],
      "%s" % run(require_dual=True,
                 unit=dict(_bin, Extractor_2="r2",
                           Independent_Verification_Status="AGREED"),
                 vals=_bv(Events_R1=3, Events_R2=3, N_at_Risk_R1=10, N_at_Risk_R2=10,
                          Events_Comparator=1, Events_Comparator_R1=1,
                          Events_Comparator_R2=1, N_at_Risk_Comparator=10,
                          N_at_Risk_Comparator_R1=10, N_at_Risk_Comparator_R2=10)))

print("a documented reconciliation resolves a disagreement")
_far = [dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=70, Dispersion_Value=3,
             Mean_R1=60, Mean_R2=80, Dispersion_R1=3, Dispersion_R2=3)
        for lv in ("PRE", "POST")]
check("AGREED cannot cover a 33% gap",
      "DUAL_READINGS_DISAGREE" in run(
          require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "AGREED"},
          vals=_far))
check("RECONCILED with a note accepts it",
      "DUAL_READINGS_DISAGREE" not in run(
          require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "RECONCILED",
                "Discrepancy_Note": "R2 read the cap, R1 the bar top; adjudicated to R1"},
          vals=[dict(row, Verification_Status="RECONCILED",
                     Reconciliation_Note="R2 read the cap; adjudicated")
                for row in _far]))
check("RECONCILED without a note does not",
      "RECONCILED_WITHOUT_NOTE" in run(
          require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "RECONCILED"},
          vals=_far))
check("reconciliation still cannot move the consensus outside both readings",
      "CONSENSUS_OUTSIDE_READINGS" in run(
          require_dual=True,
          unit={"Extractor_2": "r2", "Independent_Verification_Status": "RECONCILED",
                "Discrepancy_Note": "adjudicated"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=200,
                     Dispersion_Value=3, Mean_R1=60, Mean_R2=80,
                     Dispersion_R1=3, Dispersion_R2=3,
                     Verification_Status="RECONCILED",
                     Reconciliation_Note="adjudicated") for lv in ("PRE", "POST")]))

print("a change score is not on the outcome's native range")
_chg = {"Value_Scale": "CHANGE", "Outcome_Variable": "Heart rate", "Unit": "%"}
check("a -300%% change in heart rate is not IMPLAUSIBLE_VALUE",
      "IMPLAUSIBLE_VALUE" not in run(
          unit=_chg, vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=-300,
                                Dispersion_Value=20) for lv in ("PRE", "POST")]))
check("the same number on the native scale still is",
      "IMPLAUSIBLE_VALUE" in run(
          unit={"Value_Scale": "RATIO"},
          vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, Mean=-300,
                     Dispersion_Value=20) for lv in ("PRE", "POST")]))

print("box and violin summaries preserve quantiles")
_qcols = {"Median_R1", "Median_R2", "Median", "Q1_R1", "Q1_R2", "Q1",
          "Q3_R1", "Q3_R2", "Q3", "Whisker_Lower", "Whisker_Upper"}
_qcols |= {"Whisker_Lower_R1", "Whisker_Lower_R2",
           "Whisker_Upper_R1", "Whisker_Upper_R2"}
check("the value schema carries raw quantiles",
      _qcols.issubset(set(G.fig_values_columns())),
      "missing %s" % sorted(_qcols - set(G.fig_values_columns())))
_qu = {"Statistic_Type": "QUANTILE_SUMMARY", "Dispersion_Type": "IQR",
       "Errorbar_Definition_Source": "box overlay: median, IQR, range"}
_qv = [dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv,
            Median=50 + i, Q1=40 + i, Q3=60 + i,
            Whisker_Lower=20 + i, Whisker_Upper=80 + i)
       for i, lv in enumerate(("PRE", "POST"))]
check("a valid median/IQR/range grid passes", run(unit=_qu, vals=_qv) == [],
      "%s" % run(unit=_qu, vals=_qv))
_badq = [dict(row) for row in _qv]
_badq[0].update(Q1=70, Median=50, Q3=60)
check("quartiles in the wrong order are rejected",
      "QUANTILE_ORDER_INVALID" in run(unit=_qu, vals=_badq))
_dualq = [dict(row, Median_R1=row["Median"], Median_R2=row["Median"],
               Q1_R1=row["Q1"], Q1_R2=row["Q1"],
               Q3_R1=row["Q3"], Q3_R2=row["Q3"],
               Whisker_Lower_R1=row["Whisker_Lower"],
               Whisker_Lower_R2=row["Whisker_Lower"],
               Whisker_Upper_R1=row["Whisker_Upper"],
               Whisker_Upper_R2=row["Whisker_Upper"])
          for row in _qv]
check("quantile dual extraction checks all three summaries",
      run(require_dual=True,
          unit=dict(_qu, Extractor_2="r2", Independent_Verification_Status="AGREED"),
          vals=_dualq) == [])

print("how the p was arrived at is checked, not just stored")
_POINTS = os.path.join(_TMPDIR, "points.json")
open(_POINTS, "w").write("[[1,2],[2,4],[3,5]]")


def _assoc(at="KENDALL_TAU", em="DIGITIZED", npairs=20, **vk):
    """Association row with the field-level provenance filled in by default.

    A computed p is DIGITIZED and needs the point file behind it; Kendall needs
    its tie claim. Scenarios override only what they are about.
    """
    base = dict(Association_Type=at, Association_Value=0.4, N_Pairs=npairs,
                P_Value_Method=("KENDALL_EXACT_PERMUTATION" if at == "KENDALL_TAU"
                                else "FISHER_Z_APPROX"),
                P_Value_Extraction_Method="DIGITIZED", Ties_Present="FALSE",
                Point_Data_Reference=_POINTS)
    base.update(vk)
    return run(unit={"Statistic_Type": "ASSOCIATION", "Extraction_Method": em,
                     "Bar_Top_Definition": "NOT_A_BAR"},
               vals=[dict(Unit_ID="U1", Cell_Key="PHASE=%s" % lv, **base)
                     for lv in ("PRE", "POST")])
for _n, _kw, _w in (
        ("a Kendall p labelled FISHER_Z_APPROX",
         dict(P_Value=0.08, P_Value_Method="FISHER_Z_APPROX"), "P_METHOD_WRONG_FOR_STATISTIC"),
        ("an association row with no method at all",
         dict(P_Value=0.08, P_Value_Method=""), "MISSING_P_VALUE_METHOD"),
        ("a method outside the vocabulary",
         dict(P_Value=0.08, P_Value_Method="EXACT"), "BAD_P_VALUE_METHOD"),
        ("a computed method beside a blank p",
         dict(P_Value_Method="KENDALL_EXACT_PERMUTATION"), "P_METHOD_CLAIMS_UNCOMPUTED_P"),
        ("the large-n variant claimed at n=20",
         dict(P_Value=0.08, P_Value_Method="KENDALL_NORMAL_APPROX_N_GT_200"),
         "P_METHOD_CONTRADICTS_N"),
        ("a copied p labelled as computed from the points",
         dict(P_Value=0.08, P_Value_Method="SOURCE_REPORTED"),
         "P_PROVENANCE_CONTRADICTS_METHOD")):
    check(_n, _w in _assoc(**_kw), "%s" % _assoc(**_kw))
check("a Kendall-only method beside a Pearson r",
      "P_METHOD_WRONG_FOR_STATISTIC" in _assoc(at="PEARSON_R", P_Value=0.08,
                                               P_Value_Method="KENDALL_EXACT_PERMUTATION"))
check("Fisher-z named beside a blank p",
      "P_METHOD_CLAIMS_UNCOMPUTED_P" in _assoc(at="PEARSON_R",
                                               P_Value_Method="FISHER_Z_APPROX"))
# Ties are the reason SOURCE_P_REQUIRED_TIES exists: the exact test does not
# apply, so a blank p is legitimate and a transcribed one is what we want.
for _n, _kw in (
        ("Kendall exact at n=20", dict(P_Value=0.08,
                                       P_Value_Method="KENDALL_EXACT_PERMUTATION")),
        ("Kendall large-n at n=500", dict(npairs=500, P_Value=0.02,
                                          P_Value_Method="KENDALL_NORMAL_APPROX_N_GT_200")),
        ("Kendall with ties and no p",
         dict(P_Value_Method="SOURCE_P_REQUIRED_TIES", Ties_Present="TRUE",
              P_Value_Extraction_Method="")),
        ("Kendall with ties and the source's p",
         dict(P_Value=0.03, P_Value_Method="SOURCE_P_REQUIRED_TIES", Ties_Present="TRUE",
              P_Value_Extraction_Method="TRANSCRIBED"))):
    _g = _assoc(**_kw)
    check("%s passes" % _n, _g == [], "%s" % _g)
_g = _assoc(at="PEARSON_R", P_Value=0.08, P_Value_Method="FISHER_Z_APPROX")
check("Pearson with Fisher-z passes", _g == [], "%s" % _g)
_g = _assoc(at="PEARSON_R", em="TRANSCRIBED", P_Value=0.02,
            P_Value_Method="SOURCE_REPORTED", P_Value_Extraction_Method="TRANSCRIBED",
            Point_Data_Reference="")
check("a transcribed p may say SOURCE_REPORTED", _g == [], "%s" % _g)

print("the effect and the p may come from different places")
check("a p copied from the text on a digitized effect is legitimate",
      _assoc(P_Value=0.08, P_Value_Method="SOURCE_REPORTED",
             P_Value_Extraction_Method="TRANSCRIBED") == [],
      "%s" % _assoc(P_Value=0.08, P_Value_Method="SOURCE_REPORTED",
                    P_Value_Extraction_Method="TRANSCRIBED"))
for _n, _kw, _w in (
        ("a computed p marked TRANSCRIBED",
         dict(P_Value=0.08, P_Value_Extraction_Method="TRANSCRIBED"),
         "P_PROVENANCE_CONTRADICTS_METHOD"),
        ("no field provenance beside a p",
         dict(P_Value=0.08, P_Value_Extraction_Method=""), "MISSING_P_VALUE_PROVENANCE"),
        ("field provenance off-vocabulary",
         dict(P_Value=0.08, P_Value_Extraction_Method="COPIED"),
         "BAD_P_VALUE_PROVENANCE"),
        ("a computed p with no point file behind it",
         dict(P_Value=0.08, Point_Data_Reference=""), "MISSING_POINT_DATA_REFERENCE"),
        ("a point file that is not on disk",
         dict(P_Value=0.08, Point_Data_Reference="/nope/points.json"),
         "SOURCE_FILE_NOT_FOUND")):
    check(_n, _w in _assoc(**_kw), "%s" % _assoc(**_kw))
check("a transcribed unit cannot compute a p from points it never had",
      "P_PROVENANCE_CONTRADICTS_UNIT" in _assoc(em="TRANSCRIBED", P_Value=0.08))

# The point cloud is the record of the EFFECT, not of the p. Gating it on the p
# provenance let two whole classes of digitized association through unaudited:
# one whose p was copied from the text, and one with no p at all. The rule is
# now Statistic_Type=ASSOCIATION and unit Extraction_Method=DIGITIZED, full stop.
for _n, _kw in (
        ("a digitized effect whose p was copied from the text",
         dict(P_Value=0.08, P_Value_Method="SOURCE_REPORTED",
              P_Value_Extraction_Method="TRANSCRIBED", Point_Data_Reference="")),
        ("a digitized Kendall with ties and no p at all",
         dict(P_Value_Method="SOURCE_P_REQUIRED_TIES", Ties_Present="TRUE",
              P_Value_Extraction_Method="", Point_Data_Reference="")),
        ("a digitized Pearson r with no p and no method dispute",
         dict(at="PEARSON_R", P_Value=0.04, P_Value_Method="SOURCE_REPORTED",
              P_Value_Extraction_Method="TRANSCRIBED", Point_Data_Reference=""))):
    _g = _assoc(**_kw)
    check("%s still needs its points" % _n,
          "MISSING_POINT_DATA_REFERENCE" in _g, "%s" % _g)
_g = _assoc(at="PEARSON_R", em="TRANSCRIBED", P_Value=0.02,
            P_Value_Method="SOURCE_REPORTED", P_Value_Extraction_Method="TRANSCRIBED",
            Point_Data_Reference="")
check("a wholly transcribed association needs no point file", _g == [], "%s" % _g)
_g = _assoc(em="", P_Value=0.02, P_Value_Method="SOURCE_REPORTED",
            P_Value_Extraction_Method="TRANSCRIBED", Point_Data_Reference="")
check("the point-file rule keys on DIGITIZED, not on the absence of TRANSCRIBED",
      "MISSING_POINT_DATA_REFERENCE" not in _g, "%s" % _g)

print("the Kendall tie claim is recorded and cross-checked")
for _n, _kw, _w in (
        ("no tie claim at all", dict(P_Value=0.08, Ties_Present=""), "MISSING_TIES_PRESENT"),
        ("tie claim off-vocabulary", dict(P_Value=0.08, Ties_Present="MAYBE"),
         "BAD_TIES_PRESENT"),
        ("the exact test claimed on tied data",
         dict(P_Value=0.08, Ties_Present="TRUE"), "TIES_CONTRADICT_P_METHOD"),
        ("the large-n variant claimed on tied data",
         dict(npairs=500, P_Value=0.02,
              P_Value_Method="KENDALL_NORMAL_APPROX_N_GT_200", Ties_Present="TRUE"),
         "TIES_CONTRADICT_P_METHOD"),
        ("ties-required method on untied data",
         dict(P_Value=0.03, P_Value_Method="SOURCE_P_REQUIRED_TIES",
              P_Value_Extraction_Method="TRANSCRIBED", Ties_Present="FALSE"),
         "TIES_CONTRADICT_P_METHOD")):
    check(_n, _w in _assoc(**_kw), "%s" % _assoc(**_kw))
check("a non-Kendall statistic needs no tie claim",
      _assoc(at="PEARSON_R", P_Value=0.08, P_Value_Method="FISHER_Z_APPROX",
             Ties_Present="") == [],
      "%s" % _assoc(at="PEARSON_R", P_Value=0.08, P_Value_Method="FISHER_Z_APPROX",
                    Ties_Present=""))
# The reader must fill what the validator demands, or the two have drifted.
import mark_readers as _mr  # noqa: E402
_emit = _mr.summarize_association(
    [{"x_value": float(i), "y_value": float((i * 7) % 11)} for i in range(12)],
    "KENDALL_TAU")
for _c in ("P_Value_Method", "P_Value_Extraction_Method", "Ties_Present"):
    check("the reader emits %s" % _c, _c in _emit, "%s" % sorted(_emit))

shutil.rmtree(_TMPDIR, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
