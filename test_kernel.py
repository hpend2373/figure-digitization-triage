"""Regression suite for figure-digitization-triage.

    python test_kernel.py

Every scenario here corresponds to a defect that was found in real use and fixed.
Run this after ANY edit to kernel.py: a validator that stops firing is invisible
otherwise, and several of these checks were silently disabled by later edits
before this file existed.
"""
import importlib.util
import os
import sys
import tempfile

import pandas as pd

KERNEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel.py")


def load():
    spec = importlib.util.spec_from_file_location("fdt", KERNEL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


k = load()
TMP = os.path.join(tempfile.gettempdir(), "fdt_regression_tmp.csv")
FAILURES = []


def run(df, **kw):
    """Validate through a CSV round-trip.

    The round-trip is load-bearing: a blank cell read back from CSV arrives as
    float nan whose str() is "NAN", and an emptiness test written as == ""
    misses it. Two defects survived in-memory testing for exactly this reason.
    """
    pd.DataFrame(df).to_csv(TMP, index=False)
    out = k.fig_validate_extraction(pd.read_csv(TMP), **kw)
    return sorted(set(out["check"])) if len(out) else []


def expect(name, rows, want=None, forbid=None, clean=False, **kw):
    got = run(rows, **kw)
    if clean:
        ok = not got
        detail = "expected no problems, got %s" % got
    else:
        ok = True
        detail = ""
        for w in (want or []):
            if w not in got:
                ok = False
                detail = "missing %s (got %s)" % (w, got)
                break
        for f in (forbid or []):
            if f in got:
                ok = False
                detail = "unexpected %s" % f
                break
        if want is None and forbid is None:
            ok = bool(got)
            detail = "expected some problem, got none"
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if not ok:
        FAILURES.append(name)


CONT_BASE = dict(
    Source_File="x.pdf", Source_Page=4, Source_Image="f.png", Source_Caption_Verbatim="cap",
    Figure_Number="F2", Panel="A", Unit="mmHg", Errorbar_Definition_Source="mean+-SD",
    Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR", WPD_Project_File="p.tar",
    Image_Resolution_Or_Hash="1800x1200",
    Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
    Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=400,
    Axis_Calib_Y1_Value=80, Axis_Calib_Y1_Pixel=500,
    Axis_Calib_Y2_Value=120, Axis_Calib_Y2_Pixel=100,
    Extractor_1="r1", Date="2026-01-01",
    Extraction_Method="DIGITIZED", Bar_Top_Definition="OUTLINE_CENTER",
    Errorbar_Stem_Confirmed="TRUE",
    Observed_Panel_Count=1, Worklist_Panel_Count=1,
    Panel_Reconciliation_Status="MATCHED",
)


def crow(**kw):
    """Build a row from the REAL template columns and nothing else.

    Every key must exist in fig_template_columns(): a fixture that adds a column
    the template does not ship makes a validator check pass here and skip in
    production. That is exactly how the Extraction_Method-gated geometry checks
    went unnoticed.
    """
    cols = k.fig_template_columns()
    d = {c: "" for c in cols}
    d.update(CONT_BASE)
    d.update(kw)
    extra = [c for c in d if c not in cols]
    if extra:
        raise AssertionError("fixture uses non-template columns: %s" % extra)
    return d


def B(**over):
    """A valid B_CHALLENGE_2POINT grid: PRE/POST x SUPINE/HUT."""
    b = dict(Publication_ID="P", Data_Shape="B_CHALLENGE_2POINT",
             Outcome_Variable="Mean arterial pressure", Arm="ALL",
             Mean=96, Dispersion_Value=7, Dispersion_Type="SD", N_Outcome=10,
             Mean_R1=96, Mean_R2=96, Dispersion_R1=7, Dispersion_R2=7,
             Extractor_2="r2", Independent_Verification_Status="AGREED")
    b.update(over)
    return [crow(**dict(b, Posture_Condition=pc, Exposure_Phase=ph))
            for ph, pc in (("PRE", "SUPINE"), ("PRE", "HUT"),
                           ("POST", "SUPINE"), ("POST", "HUT"))]


def G(cells, **over):
    """A G_FACTORIAL_CONDITIONS grid from (posture, timepoint) pairs."""
    b = dict(Publication_ID="G", Data_Shape="G_FACTORIAL_CONDITIONS",
             Outcome_Variable="Heart rate", Arm="ALL", Exposure_Phase="DURING",
             Mean=90, Dispersion_Value=6, Dispersion_Type="SE", N_Outcome=14)
    b.update(over)
    return [crow(**dict(b, Posture_Condition=a, Timepoint_Label=t)) for a, t in cells]


def E(**over):
    d = {c: "" for c in k.fig_association_columns()}
    d.update(dict(
        Publication_ID="E", Source_File="x.pdf", Source_Page=3,
        Source_Caption_Verbatim="cap", Figure_Number="F5",
        Outcome_Variable="CBFV", Predictor_Variable="Plasma volume",
        Association_Type="PEARSON_R", Association_Value=0.62,
        CI_Lower=0.2, CI_Upper=0.85, P_Value=0.03, N_Pairs=12,
        Extraction_Method="DIGITIZED", Source_Image="f.png",
        WPD_Project_File="p.tar", Image_Resolution_Or_Hash="1800x1200",
        Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
        Axis_Calib_X1_Value=0, Axis_Calib_X2_Value=10,
        Axis_Calib_Y1_Value=0, Axis_Calib_Y2_Value=100,
        Association_Value_R1=0.62, Association_Value_R2=0.63,
        Independent_Verification_Status="AGREED",
        Extractor_1="r1", Extractor_2="r2", Date="2026-01-01"))
    d.update(over)
    return [d]


def F(**over):
    d = {c: "" for c in k.fig_binary_event_columns()}
    d.update(dict(
        Publication_ID="F", Source_File="x.pdf", Source_Page=2,
        Source_Caption_Verbatim="cap", Figure_Number="F1",
        Outcome_Variable="Presyncope", Event_Definition="presyncopal symptoms",
        Arm="POST", Exposure_Phase="POST", Timepoint_Label="R+0",
        Events=6, N_at_Risk=10, Arm_Comparator="PRE",
        Events_Comparator=1, N_at_Risk_Comparator=10, Effect_Measure="RR",
        Extraction_Method="DIGITIZED", Source_Image="f.png",
        WPD_Project_File="p.tar", Image_Resolution_Or_Hash="1800x1200",
        Events_R1=6, Events_R2=6, N_at_Risk_R1=10, N_at_Risk_R2=10,
        Events_Comparator_R1=1, Events_Comparator_R2=1,
        N_at_Risk_Comparator_R1=10, N_at_Risk_Comparator_R2=10,
        Independent_Verification_Status="AGREED",
        Extractor_1="r1", Extractor_2="r2", Date="2026-01-01"))
    d.update(over)
    return [d]


print("valid inputs must be silent")
expect("continuous B grid", B(), clean=True)
expect("continuous B grid, dual", B(), clean=True, require_dual=True)
expect("association row", E(), clean=True)
expect("association row, dual", E(), clean=True, require_dual=True)
expect("binary row", F(), clean=True)
expect("binary row, dual", F(), clean=True, require_dual=True)
expect("factorial 2x2", G([("P1", "T1"), ("P1", "T2"), ("P2", "T1"), ("P2", "T2")]), clean=True)
expect("transcribed association needs no WPD",
       E(Extraction_Method="TRANSCRIBED", WPD_Project_File="", Source_Image="",
         Image_Resolution_Or_Hash="", Axis_X_Scale="", Axis_Y_Scale="",
         Axis_Calib_X1_Value="", Axis_Calib_X2_Value="",
         Axis_Calib_Y1_Value="", Axis_Calib_Y2_Value=""), clean=True)
expect("transcribed binary needs no WPD",
       F(Extraction_Method="TRANSCRIBED", WPD_Project_File="", Source_Image="",
         Image_Resolution_Or_Hash=""), clean=True)

print("dispersion and sample size")
expect("zero dispersion", B(Dispersion_Value=0), want=["DISPERSION_NONPOSITIVE"])
expect("negative dispersion", B(Dispersion_Value=-5), want=["DISPERSION_NONPOSITIVE"])
expect("N zero", B(N_Outcome=0), want=["N_INVALID"])
expect("N negative", B(N_Outcome=-3), want=["N_INVALID"])
expect("N fractional", B(N_Outcome=2.5), want=["N_INVALID"])
for dt in ("SD", "SE", "SEM", "CI95", "IQR", "RANGE"):
    over = dict(N_Outcome=1, Dispersion_Type=dt)
    if dt in k.FIG_ASYMMETRIC_TYPES:
        over.update(Dispersion_Value="", Errorbar_Lower=90, Errorbar_Upper=102)
    expect("N=1 with " + dt, B(**over), want=["N_ONE_NO_DISPERSION"])
expect("SE implying an impossible SD", B(Dispersion_Type="SE", Dispersion_Value=80),
       want=["SE_IMPLIES_HUGE_SD"])

print("no error bar is a stated fact")
NEB = dict(Dispersion_Type="NO_ERRORBAR", Dispersion_Value="", Dispersion_R1="",
           Dispersion_R2="", Errorbar_Definition_Source="figure plots points only",
           N_Outcome=1)
expect("NO_ERRORBAR flags nonconvertible by default", B(**NEB),
       want=["NONCONVERTIBLE_NO_VARIANCE"])
expect("NO_ERRORBAR does not demand a second dispersion reading", B(**NEB),
       forbid=["NO_INDEPENDENT_DISPERSION"], require_dual=True)
expect("NO_ERRORBAR is not an N=1 violation", B(**NEB), forbid=["N_ONE_NO_DISPERSION"])

print("error bar bounds and axes")
CI = dict(Dispersion_Type="CI95", Dispersion_Value="")
expect("bounds inverted", B(Errorbar_Lower=110, Errorbar_Upper=90, **CI),
       want=["ERRORBAR_BOUNDS_INVERTED"])
expect("mean outside its bounds", B(Errorbar_Lower=100, Errorbar_Upper=110, **CI),
       want=["MEAN_OUTSIDE_ERRORBAR"])
expect("asymmetric type without bounds", B(**CI), want=["ASYMMETRIC_NEEDS_BOUNDS"])
expect("log axis through zero", B(Axis_Y_Scale="LOG", Axis_Calib_Y1_Value=0),
       want=["LOG_AXIS_NONPOSITIVE"])
expect("log axis negative", B(Axis_Y_Scale="LOG", Axis_Calib_Y1_Value=-10),
       want=["LOG_AXIS_NONPOSITIVE"])
expect("degenerate calibration values",
       B(Axis_Calib_Y1_Value=100, Axis_Calib_Y2_Value=100), want=["Y_CALIB_DEGENERATE"])
expect("degenerate calibration pixels",
       B(Axis_Calib_Y1_Pixel=500, Axis_Calib_Y2_Pixel=500),
       want=["Y_CALIB_PIXEL_DEGENERATE"])
expect("axis scale blank", B(Axis_X_Scale="", Axis_Y_Scale=""), want=["MISSING_REQUIRED"])
expect("axis scale unknown word", B(Axis_Y_Scale="LOGARITHMIC"), want=["BAD_AXIS_SCALE"])

print("mis-typed values must not read as missing")
expect("mean is text", B(Outcome_Variable="Novel index", Mean="abc"),
       want=["NON_NUMERIC_VALUE"])
expect("N is text", B(N_Outcome="ten"), want=["NON_NUMERIC_VALUE"])
expect("calibration is text", B(Axis_Calib_Y1_Value="abc"), want=["NON_NUMERIC_VALUE"])
expect("association value is text", E(Association_Value="abc"), want=["NON_NUMERIC_VALUE"])
expect("N_Pairs is text", E(N_Pairs="ten"), want=["NON_NUMERIC_VALUE"])
expect("association calibration is text", E(Axis_Calib_X1_Value="abc"),
       want=["NON_NUMERIC_VALUE"])
expect("events is text", F(Events="five"), want=["NON_NUMERIC_VALUE"])
expect("denominator is text", F(N_at_Risk="ten"), want=["NON_NUMERIC_VALUE"])

print("dual extraction is checked on the numbers")
expect("means disagree", B(Mean_R2=120), want=["DUAL_READINGS_DISAGREE"])
expect("dispersions disagree", B(Dispersion_R1=2, Dispersion_R2=20),
       want=["DUAL_DISPERSION_DISAGREE"])
expect("consensus mean outside readings", B(Mean_R1=90, Mean_R2=92, Mean=96),
       want=["CONSENSUS_OUTSIDE_READINGS"])
expect("consensus dispersion outside readings",
       B(Dispersion_R1=7, Dispersion_R2=8, Dispersion_Value=50),
       want=["CONSENSUS_DISPERSION_OUTSIDE_READINGS"])
expect("second reader missing", B(Extractor_2=""), want=["NO_SECOND_EXTRACTOR"],
       require_dual=True)
expect("mean read once only", B(Mean_R2=""), want=["NO_INDEPENDENT_READINGS"],
       require_dual=True)
expect("dispersion read once only", B(Dispersion_R2=""),
       want=["NO_INDEPENDENT_DISPERSION"], require_dual=True)
expect("association read once only",
       E(Association_Value_R1="", Association_Value_R2=""),
       want=["NO_INDEPENDENT_READINGS"], require_dual=True)
expect("comparator events read once only",
       F(Events_Comparator_R1="", Events_Comparator_R2=""),
       want=["NO_INDEPENDENT_READINGS"], require_dual=True)
expect("comparator events disagree between readers",
       F(Events_Comparator_R1=1, Events_Comparator_R2=9),
       want=["DUAL_READINGS_DISAGREE"], require_dual=True)
expect("denominator read once only", F(N_at_Risk_R1="", N_at_Risk_R2=""),
       want=["NO_INDEPENDENT_READINGS"], require_dual=True)

print("schema dispatch and completeness")
expect("branch columns only, association", [dict(Association_Value=0.3, N_Pairs=10)],
       want=["SCHEMA_INCOMPLETE"])
expect("branch columns only, binary", [dict(Events=1, N_at_Risk=10)],
       want=["SCHEMA_INCOMPLETE"])
expect("association rows in the mean template",
       B(Data_Shape="E_SCATTER_ASSOCIATION"), want=["WRONG_SCHEMA_FOR_SHAPE"])
expect("binary rows in the mean template",
       B(Data_Shape="F_BINARY_EVENT"), want=["WRONG_SCHEMA_FOR_SHAPE"])
expect("association image missing when digitized", E(Source_Image=""),
       want=["MISSING_PROVENANCE"])
expect("binary image missing when digitized", F(Source_Image=""),
       want=["MISSING_PROVENANCE"])
expect("extraction method unknown", E(Extraction_Method="SCRAPED"),
       want=["BAD_EXTRACTION_METHOD"])

print("association statistics")
expect("r above one", E(Association_Value=1.5, CI_Lower="", CI_Upper="",
                        Association_Value_R1=1.5, Association_Value_R2=1.5),
       want=["ASSOCIATION_VALUE_OUT_OF_RANGE"])
expect("r above one under an alias label",
       E(Association_Type="Pearson correlation", Association_Value=1.5,
         CI_Lower="", CI_Upper="", Association_Value_R1=1.5, Association_Value_R2=1.5),
       want=["ASSOCIATION_VALUE_OUT_OF_RANGE"], forbid=["BAD_ASSOCIATION_TYPE"])
expect("rho above one under a lowercase alias",
       E(Association_Type="spearman", Association_Value=2.0, CI_Lower="", CI_Upper="",
         Association_Value_R1=2.0, Association_Value_R2=2.0),
       want=["ASSOCIATION_VALUE_OUT_OF_RANGE"])
expect("r-squared below zero",
       E(Association_Type="R2", Association_Value=-0.3, CI_Lower="", CI_Upper="",
         Association_Value_R1=-0.3, Association_Value_R2=-0.3),
       want=["ASSOCIATION_VALUE_OUT_OF_RANGE"])
expect("statistic label off-vocabulary",
       E(Association_Type="my own index"), want=["BAD_ASSOCIATION_TYPE"])
expect("two pairs cannot define a correlation", E(N_Pairs=2),
       want=["N_PAIRS_TOO_SMALL"])
expect("interval half filled", E(CI_Upper=""), want=["CI_HALF_FILLED"])
expect("interval inverted", E(CI_Lower=0.9, CI_Upper=0.2), want=["CI_BOUNDS_INVERTED"])
expect("estimate outside its interval", E(Association_Value=0.95,
                                          Association_Value_R1=0.95,
                                          Association_Value_R2=0.95),
       want=["ESTIMATE_OUTSIDE_CI"])
expect("p value above one", E(P_Value=1.4), want=["P_VALUE_OUT_OF_RANGE"])
expect("correlation interval leaves [-1, 1]", E(CI_Lower=-1.2, CI_Upper=1.3),
       want=["ASSOCIATION_CI_OUT_OF_RANGE"])
expect("rank correlation interval leaves [-1, 1]",
       E(Association_Type="SPEARMAN_RHO", CI_Lower=-2, CI_Upper=2),
       want=["ASSOCIATION_CI_OUT_OF_RANGE"])
expect("r-squared interval leaves [0, 1]",
       E(Association_Type="R2", Association_Value=0.5, CI_Lower=-0.3, CI_Upper=1.2,
         Association_Value_R1=0.5, Association_Value_R2=0.5),
       want=["ASSOCIATION_CI_OUT_OF_RANGE"])
expect("slope interval is unbounded",
       E(Association_Type="SLOPE", Association_Value=35, CI_Lower=-50, CI_Upper=120,
         Association_Value_R1=35, Association_Value_R2=35),
       forbid=["ASSOCIATION_CI_OUT_OF_RANGE"])

print("reconciliation preserves both readings")
expect("association readings disagree, unadjudicated",
       E(Association_Value_R1=0.80, Association_Value_R2=0.92),
       want=["DUAL_READINGS_DISAGREE"])
expect("association readings disagree, reconciled with a note",
       E(Association_Value_R1=0.80, Association_Value_R2=0.92, Association_Value=0.86,
         CI_Lower=0.6, CI_Upper=0.95,
         Independent_Verification_Status="RECONCILED",
         Discrepancy_Note="R2 mis-set the y-axis origin; re-read gave 0.86"),
       clean=True)
expect("association reconciled without a note",
       E(Association_Value_R1=0.80, Association_Value_R2=0.92, Association_Value=0.86,
         CI_Lower=0.6, CI_Upper=0.95,
         Independent_Verification_Status="RECONCILED"),
       want=["RECONCILED_WITHOUT_NOTE"])
expect("binary counts disagree, unadjudicated", F(Events_R1=6, Events_R2=7),
       want=["DUAL_READINGS_DISAGREE"])
expect("binary counts disagree, reconciled with a note",
       F(Events_R1=6, Events_R2=7, Events=6,
         Independent_Verification_Status="RECONCILED",
         Discrepancy_Note="R2 counted a partly shaded wedge; source text confirms 6"),
       clean=True)
expect("binary reconciled without a note",
       F(Events_R1=6, Events_R2=7, Events=6,
         Independent_Verification_Status="RECONCILED"),
       want=["RECONCILED_WITHOUT_NOTE"])
expect("verification status off-vocabulary",
       E(Independent_Verification_Status="MAYBE"), want=["BAD_VERIFICATION_STATUS"])

print("event counts")
expect("events exceed denominator", F(Events=15, Events_R1=15, Events_R2=15),
       want=["EVENTS_EXCEED_N"])
expect("denominator zero", F(N_at_Risk=0, N_at_Risk_R1=0, N_at_Risk_R2=0),
       want=["N_AT_RISK_INVALID"])
expect("events negative", F(Events=-2, Events_R1=-2, Events_R2=-2),
       want=["EVENTS_INVALID"])
expect("events fractional", F(Events=6.5, Events_R1=6.5, Events_R2=6.5),
       want=["EVENTS_INVALID"])
expect("effect measure off-vocabulary", F(Effect_Measure="SMD"),
       want=["BAD_EFFECT_MEASURE"])
expect("comparator partly filled", F(N_at_Risk_Comparator=""),
       want=["COMPARATOR_HALF_FILLED"])
expect("ratio without a comparator arm",
       F(Arm_Comparator="", Events_Comparator="", N_at_Risk_Comparator="",
         Events_Comparator_R1="", Events_Comparator_R2="",
         N_at_Risk_Comparator_R1="", N_at_Risk_Comparator_R2=""),
       want=["COMPARATOR_MISSING_FOR_RATIO"])
expect("reported p above one", F(P_Value_Reported=1.4), want=["P_VALUE_OUT_OF_RANGE"])

print("shape-specific grids")
expect("posture grid collapsed to one phase",
       [r for r in B() if r["Exposure_Phase"] == "PRE"], want=["B_PHASE_MISSING"])
expect("posture set asymmetric across phases",
       [r for r in B() if not (r["Exposure_Phase"] == "POST" and r["Posture_Condition"] == "HUT")],
       want=["B_POSTURE_SET_ASYMMETRIC"])
expect("factorial with a pre-exposure row",
       G([("P1", "T1"), ("P1", "T2"), ("P2", "T1"), ("P2", "T2")], Exposure_Phase="PRE"),
       want=["G_PHASE_NOT_DURING"])
expect("factorial with one level on a factor",
       G([("P1", "T1"), ("P1", "T2"), ("P1", "T3")]), want=["G_NOT_A_GRID"])
expect("factorial cell missing",
       G([("P1", "T1"), ("P1", "T2"), ("P2", "T1")]), want=["G_INCOMPLETE_GRID"])
expect("factorial blank factor cannot fill a cell",
       G([("P1", "T1"), ("P1", "T2"), ("P2", "T1"), ("", "T2")]),
       want=["G_FACTOR_MISSING", "G_INCOMPLETE_GRID"])
expect("factorial duplicate cell",
       G([("P1", "T1"), ("P1", "T1"), ("P1", "T2"), ("P2", "T1"), ("P2", "T2")]),
       want=["G_DUPLICATE_CELL"])
expect("units mixed inside one outcome",
       [dict(r, Unit=("mmHg" if i < 2 else "kPa")) for i, r in enumerate(B())],
       want=["MIXED_UNIT_IN_UNIT"])
expect("SD and SE mixed inside one figure",
       [dict(r, Dispersion_Type=("SD" if i < 2 else "SE")) for i, r in enumerate(B())],
       want=["MIXED_DISPERSION_TYPE_IN_UNIT"])

print("caption screening and panels")
CASES = [
    ("Mean heart rate during supine rest and 60-deg tilt before and after bed rest",
     "DIGITIZE"),
    ("Tilt tolerance time before, after 14-day bed rest and after 4 weeks recovery",
     "DIGITIZE"),
    ("Individual and group mean changes in lower body negative pressure (LBNP) tolerance",
     "DIGITIZE"),
    ("Sympathetic index (LF/HF) and spontaneous baroreflex sensitivity during head-up tilt",
     "DIGITIZE"),
    ("Plasma norepinephrine levels in presyncopal and nonpresyncopal men",
     "NO_TARGET_OUTCOME"),
    ("Relationship between plasma volume and stroke index after bed rest",
     "ASSOCIATION_ONLY_NOT_TARGET"),
    ("Incidence of presyncope before and after spaceflight", "BINARY_EVENT_NOT_MEAN"),
    ("Anatomic view of the calf area and echographic view of the gastrocnemius vein",
     "NOT_DATA"),
    ("Schematic of the experimental protocol", "NOT_DATA"),
]
TARGET = [r"heart rate", r"\bHR\b", r"blood pressure", r"\bMAP\b",
          r"(?:orthostatic|tilt|standing|LBNP|lower body negative pressure)[\s\w\-\(\)]{0,26}toleran",
          r"tolerance time", r"sympathetic (?:nerve|activ|outflow|index|nervous system)",
          r"barorefl", r"cerebral", r"stroke index", r"plasma volume"]
for cap, want_route in CASES:
    got = k.fig_screen_caption(cap, target_terms=TARGET)[0]
    ok = got == want_route
    print(("  ok   " if ok else "  FAIL ") + cap[:58]
          + ("" if ok else "  <- got %s want %s" % (got, want_route)))
    if not ok:
        FAILURES.append("screen: " + cap[:40])

TOKENS = [
    ("CI", "After 8 days of HDT, CRAE decreased by 6.40 um (95% confidence interval [CI])", False),
    ("CI", "Cardiac index (CI) and stroke index (SI) during head-up tilt", True),
    ("PV", "Percentage change in flow in the portal vein flow (PV) from supine to tilt", False),
    ("PV", "Percentage changes in plasma volume (PV) versus baseline", True),
    ("CO", "Body weight variations in the control (Co-gr) and exercise (CM-gr) groups", False),
    ("CO", "Cardiac output (CO) and stroke volume before and after bed rest", True),
]
for tok, cap, want_true in TOKENS:
    got = k.fig_token_denotes_outcome(tok, cap)
    ok = got == want_true
    print(("  ok   " if ok else "  FAIL ") + "%s in %s" % (tok, cap[:44])
          + ("" if ok else "  <- got %s" % got))
    if not ok:
        FAILURES.append("token: %s %s" % (tok, cap[:30]))

conf, _ = k.fig_panel_confidence("Mean heart rate before and after bed rest")
ok = conf == "NO_KEY"
print(("  ok   " if ok else "  FAIL ") + "prose without a panel key says nothing about panels"
      + ("" if ok else "  <- got %s" % conf))
if not ok:
    FAILURES.append("panel confidence no key")
conf, _ = k.fig_panel_confidence("Mean HR before and after bed rest")
ok = conf == "SINGLE_KEY_ONLY"
print(("  ok   " if ok else "  FAIL ") + "one panel key is not proof of one panel"
      + ("" if ok else "  <- got %s" % conf))
if not ok:
    FAILURES.append("panel confidence single")
conf, _ = k.fig_panel_confidence("Responses of HR, SBP and DBP to the cold pressor test")
ok = conf == "CAPTION_ENUMERATES"
print(("  ok   " if ok else "  FAIL ") + "several panel keys are enumerated"
      + ("" if ok else "  <- got %s" % conf))
if not ok:
    FAILURES.append("panel confidence enumerated")

print("schema and spec shape")
for name, cols, n in (("continuous", k.fig_template_columns(), None),
                      ("association", k.fig_association_columns(), None),
                      ("binary", k.fig_binary_event_columns(), None)):
    dup = [c for c in set(cols) if list(cols).count(c) > 1]
    ok = not dup
    print(("  ok   " if ok else "  FAIL ") + "%s schema has no duplicate columns" % name
          + ("" if ok else "  <- %s" % dup))
    if not ok:
        FAILURES.append("dup cols " + name)
spec = k.fig_extraction_spec()
ok = set(spec["Data_Shape"]) == set(k.FIG_SHAPES)
print(("  ok   " if ok else "  FAIL ") + "spec covers every shape in FIG_SHAPES"
      + ("" if ok else "  <- %s" % sorted(set(k.FIG_SHAPES) ^ set(spec["Data_Shape"]))))
if not ok:
    FAILURES.append("spec shape coverage")

# --------------------------------------------------------------------------
# Scenarios added for the four screening/normalization defects. Each fix gets a
# failing case AND a valid case: a rule that fires on correct data is as harmful
# as one that misses.
# --------------------------------------------------------------------------

print("outcome name normalization")
# A mean of 999 bpm is impossible however the label is spelled. The range table
# used to be an exact dict lookup, so every spelling but one silently skipped the
# check and produced no flag at all.
for label in ("Heart rate", "Heart Rate", "heart rate", "HR", "Heart rate (bpm)",
              "heart-rate", "Pulse rate"):
    expect("impossible HR under label %r" % label,
           B(Outcome_Variable=label, Mean=999, Unit="bpm"),
           want=["IMPLAUSIBLE_VALUE"])
for label in ("Mean arterial pressure", "MAP", "mean arterial pressure (mmHg)"):
    expect("valid MAP under label %r stays silent" % label,
           B(Outcome_Variable=label, Mean=96),
           forbid=["IMPLAUSIBLE_VALUE", "PLAUSIBILITY_RANGE_NOT_APPLIED"])
expect("outcome with no range is reported, not silently skipped",
       B(Outcome_Variable="Serum osmolality", Mean=290, Unit="mOsm/kg"),
       want=["PLAUSIBILITY_RANGE_NOT_APPLIED"])
expect("a caller-supplied range dict still keys on its own names",
       B(Outcome_Variable="Serum osmolality", Mean=290, Unit="mOsm/kg"),
       forbid=["PLAUSIBILITY_RANGE_NOT_APPLIED", "IMPLAUSIBLE_VALUE"],
       ranges={"Serum osmolality": (250, 320)})
expect("a caller-supplied range still catches an impossible value",
       B(Outcome_Variable="Serum osmolality", Mean=9000, Unit="mOsm/kg"),
       want=["IMPLAUSIBLE_VALUE"],
       ranges={"Serum osmolality": (250, 320)})

print("null token vocabulary")
NULLS = ("", "NONE", "NA", "N/A", "n/a", "N.A.", "-", "\u2014", "\uc5c6\uc74c",
         "\ud574\ub2f9\uc5c6\uc74c", "\ubbf8\uc801\uc6a9", "NOT_APPLICABLE", "nan")
for tok in NULLS:
    df = pd.DataFrame([dict(Timepoints="PRE_POST", Challenge_Test=tok)])
    got = k.fig_classify_shape(df)["Data_Shape_Expected"].iloc[0]
    ok = got == "D_SIMPLE_PREPOST"
    print(("  ok   " if ok else "  FAIL ")
          + "no challenge when Challenge_Test=%r" % tok
          + ("" if ok else "  <- got %s" % got))
    if not ok:
        FAILURES.append("null token %r" % tok)
for tok, want_shape in (("HUT70", "B_CHALLENGE_2POINT"), ("LBNP", "B_CHALLENGE_2POINT")):
    df = pd.DataFrame([dict(Timepoints="PRE_POST", Challenge_Test=tok)])
    got = k.fig_classify_shape(df)["Data_Shape_Expected"].iloc[0]
    ok = got == want_shape
    print(("  ok   " if ok else "  FAIL ") + "a real challenge %r still classifies as B" % tok
          + ("" if ok else "  <- got %s" % got))
    if not ok:
        FAILURES.append("real challenge %r" % tok)
df = pd.DataFrame([dict(Timepoints="SERIAL", Challenge_Test="\uc5c6\uc74c")])
got = k.fig_classify_shape(df)["Data_Shape_Expected"].iloc[0]
ok = got == "C_LONGITUDINAL_SERIAL"
print(("  ok   " if ok else "  FAIL ") + "serial with a Korean null is C, not A"
      + ("" if ok else "  <- got %s" % got))
if not ok:
    FAILURES.append("serial korean null")

print("prediction wording is not an association")
PRED = [
    # A bare r"predict" pattern routed all three of these to E, which turns a
    # group mean into a fabricated correlation.
    ("Predicted heart rate at each tilt angle.", "DIGITIZE"),
    ("Predictors of orthostatic intolerance after 14-day bed rest.", "DIGITIZE"),
    ("Heart rate predicted for each LBNP level.", "DIGITIZE"),
    # Real association evidence must still route to E.
    ("Correlation between plasma volume and stroke index", "ASSOCIATION_ONLY_NOT_TARGET"),
    ("Relationship between plasma volume and heart rate", "ASSOCIATION_ONLY_NOT_TARGET"),
    ("Heart rate against plasma volume, line of best fit shown",
     "ASSOCIATION_ONLY_NOT_TARGET"),
    ("Heart rate predicted from the model versus measured heart rate",
     "ASSOCIATION_ONLY_NOT_TARGET"),
]
PRED_TARGET = TARGET + [r"orthostatic intoleran"]
for cap, want in PRED:
    got = k.fig_screen_caption(cap, target_terms=PRED_TARGET)[0]
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + cap[:58]
          + ("" if ok else "  <- got %s, want %s" % (got, want)))
    if not ok:
        FAILURES.append("predict wording: " + cap[:40])

print("equipment drawings are not data")
DRAW = [
    ("VVIS chair. The drawing shows a model of the centrifuge used to induce OCR "
     "during tilt.", "NOT_DATA"),
    ("Model of the tilt table used to deliver the orthostatic challenge.", "NOT_DATA"),
    ("Line drawing of the lower body negative pressure device.", "NOT_DATA"),
]
for cap, want in DRAW:
    got = k.fig_screen_caption(cap, target_terms=TARGET)[0]
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + cap[:58]
          + ("" if ok else "  <- got %s, want %s" % (got, want)))
    if not ok:
        FAILURES.append("drawing wording: " + cap[:40])

# "model of" alone must NOT exclude mathematical-model output. The assertion is
# only that these survive the NOT_DATA screen - which downstream route they take
# depends on the caller's target_terms and is not what this fix is about.
MATH_MODEL = [
    "Heart rate predicted by a lumped-parameter model of the cardiovascular system, "
    "plotted against measured heart rate.",
    "Mean arterial pressure from the three-element Windkessel model and from "
    "measurement during tilt.",
    "Simulated and measured heart rate from a model of baroreflex control.",
]
for cap in MATH_MODEL:
    got = k.fig_screen_caption(cap, target_terms=TARGET)[0]
    ok = got != "NOT_DATA"
    print(("  ok   " if ok else "  FAIL ") + "mathematical model survives: " + cap[:40]
          + ("" if ok else "  <- got NOT_DATA"))
    if not ok:
        FAILURES.append("math model excluded: " + cap[:40])

print("how the mark was read")
expect("bar top read at the colour fill is a systematic bias",
       B(Bar_Top_Definition="FILL_EDGE"), want=["BAR_TOP_READ_AT_FILL_EDGE"])
expect("bar top definition missing on a digitized row",
       B(Bar_Top_Definition=""), want=["MISSING_BAR_TOP_DEFINITION"])
expect("bar top definition off-vocabulary",
       B(Bar_Top_Definition="TOP_OF_BAR"), want=["BAD_BAR_TOP_DEFINITION"])
expect("a line plot may declare NOT_A_BAR",
       B(Bar_Top_Definition="NOT_A_BAR"),
       forbid=["MISSING_BAR_TOP_DEFINITION", "BAD_BAR_TOP_DEFINITION",
               "BAR_TOP_READ_AT_FILL_EDGE"])
expect("a transcribed row needs no bar geometry",
       B(Extraction_Method="TRANSCRIBED", Bar_Top_Definition="", WPD_Project_File="",
         Errorbar_Stem_Confirmed=""),
       forbid=["MISSING_BAR_TOP_DEFINITION", "ERRORBAR_STEM_UNCONFIRMED"])

print("the whisker must connect to the mark")
expect("dispersion recorded without confirming the stem",
       B(Errorbar_Stem_Confirmed=""), want=["ERRORBAR_STEM_UNCONFIRMED"])
expect("stem explicitly not confirmed",
       B(Errorbar_Stem_Confirmed="FALSE"), want=["ERRORBAR_STEM_UNCONFIRMED"])
expect("stem flag off-vocabulary",
       B(Errorbar_Stem_Confirmed="MAYBE"), want=["BAD_ERRORBAR_STEM_FLAG"])
expect("NO_ERRORBAR needs no stem confirmation",
       B(Dispersion_Type="NO_ERRORBAR", Dispersion_Value="", Dispersion_R1="", Dispersion_R2="",
         Errorbar_Definition_Source="figure plots points without error bars",
         Errorbar_Stem_Confirmed=""),
       forbid=["ERRORBAR_STEM_UNCONFIRMED"])

print("panel reconciliation")
expect("reconciliation not done",
       B(Panel_Reconciliation_Status=""), want=["PANEL_RECONCILIATION_PENDING"])
expect("reconciliation explicitly pending",
       B(Panel_Reconciliation_Status="PENDING"), want=["PANEL_RECONCILIATION_PENDING"])
expect("reconciliation status off-vocabulary",
       B(Panel_Reconciliation_Status="OK"), want=["BAD_PANEL_RECONCILIATION_STATUS"])
expect("counts missing once reconciliation is claimed",
       B(Observed_Panel_Count="", Worklist_Panel_Count=""), want=["MISSING_PANEL_COUNT"])
# The real ID323 Figure 2 defect: six panels on screen, five in the worklist.
expect("more panels on screen than the worklist lists, still called MATCHED",
       B(Observed_Panel_Count=6, Worklist_Panel_Count=5, Unlisted_Panels="PAP",
         Panel_Reconciliation_Status="MATCHED"), want=["PANEL_STATUS_CONTRADICTS_COUNTS"])
expect("unlisted panels found but not named",
       B(Observed_Panel_Count=6, Worklist_Panel_Count=5, Unlisted_Panels="",
         Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND"),
       want=["UNLISTED_PANELS_NOT_RECORDED"])
expect("unlisted panels found and named is clean",
       B(Observed_Panel_Count=6, Worklist_Panel_Count=5, Unlisted_Panels="PAP",
         Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND"),
       forbid=["PANEL_COUNT_MISMATCH", "UNLISTED_PANELS_NOT_RECORDED",
               "PANEL_RECONCILIATION_PENDING"])
expect("fewer panels on screen than listed must say so",
       B(Observed_Panel_Count=4, Worklist_Panel_Count=5,
         Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND"),
       want=["PANEL_STATUS_CONTRADICTS_COUNTS"])
expect("worklist overcount declared is clean",
       B(Observed_Panel_Count=4, Worklist_Panel_Count=5,
         Panel_Reconciliation_Status="WORKLIST_OVERCOUNTS"),
       forbid=["PANEL_STATUS_CONTRADICTS_COUNTS"])
expect("panel count is text",
       B(Observed_Panel_Count="six"), want=["NON_NUMERIC_VALUE"])

# A controlled-vocabulary value that is also a NULL token can never be filled in:
# fig_is_blank would read the answer as an empty cell. NOT_APPLICABLE was exactly
# that mistake in the first draft of Bar_Top_Definition.
print("vocabularies must not collide with the null tokens")
for vname in ("FIG_BAR_TOP_DEFS", "FIG_PANEL_RECON", "FIG_DISPERSION_TYPES", "FIG_PHASES",
              "FIG_SHAPES", "FIG_EXTRACTION_METHODS", "FIG_DUAL_OK", "FIG_BOOL_TRUE",
              "FIG_BOOL_FALSE"):
    bad = [v for v in getattr(k, vname) if k.fig_is_blank(v)]
    ok = not bad
    print(("  ok   " if ok else "  FAIL ") + "%s has no null-token value" % vname
          + ("" if ok else "  <- %s" % bad))
    if not ok:
        FAILURES.append("vocab collision " + vname)

print("the template is the contract")
_cols = k.fig_template_columns()
for _c in ("Extraction_Method", "Bar_Top_Definition", "Errorbar_Stem_Confirmed",
           "Observed_Panel_Count", "Worklist_Panel_Count", "Unlisted_Panels",
           "Panel_Reconciliation_Status"):
    ok = _c in _cols
    print(("  ok   " if ok else "  FAIL ") + "%s ships in fig_template_columns()" % _c)
    if not ok:
        FAILURES.append("template missing " + _c)
# A gate that only fires when an out-of-template column happens to be present is
# not a gate. Build the row from the template alone and require the checks.
expect("geometry checks fire on a row built only from template columns",
       B(Extraction_Method="DIGITIZED", Bar_Top_Definition="", Errorbar_Stem_Confirmed=""),
       want=["MISSING_BAR_TOP_DEFINITION", "ERRORBAR_STEM_UNCONFIRMED"])
expect("Extraction_Method blank is a missing required field",
       B(Extraction_Method=""), want=["MISSING_REQUIRED"])

print("panel counts fully determine the status")
expect("fractional panel count",
       B(Observed_Panel_Count=1.5, Worklist_Panel_Count=1.5), want=["PANEL_COUNT_INVALID"])
expect("zero panel count",
       B(Observed_Panel_Count=0, Worklist_Panel_Count=0), want=["PANEL_COUNT_INVALID"])
expect("negative panel count",
       B(Observed_Panel_Count=-2, Worklist_Panel_Count=-2), want=["PANEL_COUNT_INVALID"])
expect("observed > worklist cannot be WORKLIST_OVERCOUNTS",
       B(Observed_Panel_Count=6, Worklist_Panel_Count=5, Unlisted_Panels="PAP",
         Panel_Reconciliation_Status="WORKLIST_OVERCOUNTS"),
       want=["PANEL_STATUS_CONTRADICTS_COUNTS"])
expect("equal counts cannot be UNLISTED_PANELS_FOUND",
       B(Observed_Panel_Count=5, Worklist_Panel_Count=5,
         Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND"),
       want=["PANEL_STATUS_CONTRADICTS_COUNTS"])
expect("observed < worklist cannot be MATCHED",
       B(Observed_Panel_Count=4, Worklist_Panel_Count=5,
         Panel_Reconciliation_Status="MATCHED"), want=["PANEL_STATUS_CONTRADICTS_COUNTS"])
for _o, _w, _st, _un in ((5, 5, "MATCHED", ""), (6, 5, "UNLISTED_PANELS_FOUND", "PAP"),
                         (4, 5, "WORKLIST_OVERCOUNTS", "")):
    expect("counts %d/%d with %s is clean" % (_o, _w, _st),
           B(Observed_Panel_Count=_o, Worklist_Panel_Count=_w,
             Panel_Reconciliation_Status=_st, Unlisted_Panels=_un),
           forbid=["PANEL_STATUS_CONTRADICTS_COUNTS", "PANEL_COUNT_INVALID",
                   "UNLISTED_PANELS_NOT_RECORDED", "PANEL_COUNT_INCONSISTENT_IN_FIGURE"])
# same figure, two different answers to "how many panels does it have"
_mixed = (B(Observed_Panel_Count=6, Worklist_Panel_Count=5, Unlisted_Panels="PAP",
            Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND")[:2]
          + B(Observed_Panel_Count=5, Worklist_Panel_Count=5,
              Panel_Reconciliation_Status="MATCHED")[2:])
expect("one figure cannot carry two different panel counts", _mixed,
       want=["PANEL_COUNT_INCONSISTENT_IN_FIGURE"])

print("a placeholder is not a dispersion definition")
for _txt in ("HARNESS PLACEHOLDER - unresolved for this figure", "TBD", "unknown",
             "TODO: check the paper", "assumed SE", "???", "not stated in the caption",
             "presumed SEM"):
    expect("placeholder %r is blocked" % _txt[:34],
           B(Errorbar_Definition_Source=_txt), want=["UNRESOLVED_ERRORBAR_DEFINITION"])
for _txt in ("caption: values are mean +- SEM",
             "Methods: data are presented as mean +/- standard deviation",
             "figure legend states bars are SE"):
    expect("real source wording %r passes" % _txt[:30],
           B(Errorbar_Definition_Source=_txt), forbid=["UNRESOLVED_ERRORBAR_DEFINITION"])

print("one figure names one set of missing panels")
_a = B(Observed_Panel_Count=6, Worklist_Panel_Count=5,
       Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND", Unlisted_Panels="PAP")
_b = B(Observed_Panel_Count=6, Worklist_Panel_Count=5,
       Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND", Unlisted_Panels="MAP")
expect("matching counts but different panel names", _a[:2] + _b[2:],
       want=["UNLISTED_PANELS_INCONSISTENT_IN_FIGURE"])
_c = B(Observed_Panel_Count=7, Worklist_Panel_Count=5,
       Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND", Unlisted_Panels="pap , map")
_d = B(Observed_Panel_Count=7, Worklist_Panel_Count=5,
       Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND", Unlisted_Panels="MAP;PAP")
expect("the same set spelled differently is not a disagreement", _c[:2] + _d[2:],
       forbid=["UNLISTED_PANELS_INCONSISTENT_IN_FIGURE"])
expect("one figure naming one set is clean", _a,
       forbid=["UNLISTED_PANELS_INCONSISTENT_IN_FIGURE"])

if os.path.exists(TMP):
    os.remove(TMP)
print()
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
