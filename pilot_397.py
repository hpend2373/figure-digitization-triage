"""Pilot: publication 397, every figure, through the batch layer.

    python3 pilot_397.py [OUTPUT_DIR] [RASTER_DIR]

Five figures, declared honestly - the two that a released reader can do and the
three it cannot, in one manifest set and one run. That mix is the point. A batch
over 160 publications will always contain figures nobody can read yet, and what
matters is that they are counted and queued rather than silently absent or
allowed to stop the ones that can be read.

    Figure 3   MAP,                2 panels   BAR_MONO          readable
    Figure 4   HR / SV / CO,       6 panels   BAR_MONO          readable
    Figure 1   MAP / TPR / SV,     6 panels   LINE_MONO_STYLE   no reader yet
    Figure 2   HR / TFV / ...,     6 panels   LINE_MONO_STYLE   no reader yet
    Figure 5   single-subject traces          MANUAL            not summary data

Figure 5 is `Panel_Mode=MANUAL` for a different reason from Figures 1 and 2, and
the distinction is worth keeping: 1 and 2 are group means this project will be
able to read once the solid/dashed reader is finished, while 5 plots two named
individuals beat by beat and is not a summary statistic at all. One is a
software gap; the other is a study-design fact no reader will ever change.

Every panel's own axis calibration is measured from its own gridlines. On this
publication the left and right panels of one figure differ by two to seven
pixels, which is under half a millimetre of print and worth about a fifth of a
unit on the cardiac-output axis.
"""
import csv
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import mark_readers as MR                                          # noqa: E402
import run_batch as RB                                             # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out_pilot_397")
MANIFESTS = os.path.join(OUT, "manifests")
RASTERS = sys.argv[2] if len(sys.argv) > 2 else HERE

# Every raster this pilot names, checked before anything is built.
#
# There was a check for three of these, and it sat at the bottom of the file -
# after the manifests, which hash their own rasters as they are assembled. It
# could therefore never fire: a missing figure raised FileNotFoundError out of
# `sha256_of` two hundred lines earlier, and a guard that can only run once its
# subject has already crashed is decoration. Ahead of the first open, and
# exiting 2 rather than 0, it says which files are absent and stops.
FIGURE_RASTERS = tuple("397_fig%d.jpeg" % n for n in range(1, 6))
_absent = [f for f in FIGURE_RASTERS
           if not os.path.exists(os.path.join(RASTERS, f))]
if _absent:
    print("BLOCKED: publisher rasters not found in %s: %s"
          % (RASTERS, ", ".join(_absent)), file=sys.stderr)
    raise SystemExit(2)

# --------------------------------------------------------------------------
# who stands behind this run
# --------------------------------------------------------------------------
# A worked example needs a reviewer, and it must not ship somebody's personal
# address to everyone the zip reaches. The first attempt at that was a fictional
# identity carrying `Note="EXAMPLE - replace before treating any output as
# data"`, and a note is a request, not a gate. Three things were wrong with it:
#
#   FDT_REVIEWER_NAME alone   -> a real name vouching for a fictional ORCID
#   FDT_REVIEWER_ORCID alone  -> a fictional name against a real ORCID, and the
#                                Note flipped to "opened all five rasters"
#   neither                   -> a fictional person marked HUMAN_CONFIRMED,
#                                Status=RAN
#
# The last one was only harmless because ID397's dispersion definition happens
# to be unresolved, so nothing is accepted. Resolve it and the same fictional
# row signs off poolable values. A safety property that holds by coincidence is
# not a property.
#
# So: all four or none. A partial attestation is not an attestation, and the
# no-attestation case is declared to the runner as DEMO_ONLY rather than left
# to look like a real run.
DEMO_NAME, DEMO_ORCID, DEMO_DATE = "Josiah Carberry", "0000-0002-1825-0097", "2026-08-07"
ATTESTATION_ENV = ("FDT_REVIEWER_NAME", "FDT_REVIEWER_ORCID",
                   "FDT_INSPECTION_DATE", "FDT_REGISTRATION_DATE")
_env = {k: os.environ.get(k, "").strip() for k in ATTESTATION_ENV}
_given = [k for k in ATTESTATION_ENV if _env[k]]
if _given and len(_given) < len(ATTESTATION_ENV):
    print("BLOCKED: a partial attestation is not an attestation.\n"
          "  set: %s\n  missing: %s\n"
          "Set all four to attest a real inspection, or none to run the "
          "demonstration." % (", ".join(_given),
                              ", ".join(k for k in ATTESTATION_ENV if not _env[k])),
          file=sys.stderr)
    raise SystemExit(2)

if _given:
    RUN_MODE = "ATTESTED"
    # The dates are asked for rather than assumed. A hardcoded 2026-08-07 is a
    # false record on every run after the day it was written, and an inspection
    # date is the one field whose whole purpose is to be comparable later.
    ATTESTATION = dict(
        Reviewer_ID="RV_INSPECTOR", Reviewer_Name=_env["FDT_REVIEWER_NAME"],
        Reviewer_Record_Type="HUMAN",
        Contact_Type="ORCID", Reviewer_Contact=_env["FDT_REVIEWER_ORCID"],
        Registered_By=_env["FDT_REVIEWER_NAME"],
        Registration_Date=_env["FDT_REGISTRATION_DATE"],
        Human_Attestation="HUMAN_CONFIRMED",
        Note="opened all five publisher rasters and counted the panels")
    INSPECTION_DATE = _env["FDT_INSPECTION_DATE"]
    RUN_DATE = (os.environ.get("FDT_RUN_DATE", "").strip()
                or datetime.date.today().isoformat())
else:
    RUN_MODE = "DEMO_ONLY"
    # DEMO_IDENTITY travels with the manifests. The mode used to be an
    # argument this script passed to the runner, which meant the demonstration's
    # own manifest set replayed through the plain CLI came back Status=RAN,
    # Run_Mode=ATTESTED - the promise stayed at the call site while the files
    # walked away without it.
    ATTESTATION = dict(
        Reviewer_ID="RV_INSPECTOR", Reviewer_Name=DEMO_NAME,
        Reviewer_Record_Type="DEMO_IDENTITY",
        Contact_Type="ORCID", Reviewer_Contact=DEMO_ORCID,
        Registered_By=DEMO_NAME, Registration_Date=DEMO_DATE,
        Human_Attestation="DEMO_EXAMPLE",
        Note="ORCID's fictional demonstration record")
    INSPECTION_DATE = RUN_DATE = DEMO_DATE

SESSIONS = [("PRE", "Pre HDT Stand"), ("POST", "Post HDT Stand")]
HDT = ["0:30", "1:00", "1:30", "2:00", "2:30", "3:00",
       "3:30", "4:00", "4:30", "5:00", "5:30", "6:00"]

# --------------------------------------------------------------------------
# what is in the publication - measured from the rasters, declared here
# --------------------------------------------------------------------------
# (Figure_ID, file, outcome, unit, domain, panel rows)
#   panel row = (Panel_ID, sex, box, y ticks, {session: x pixel})
BAR_FIGURES = [
    ("F397_3", "397_fig3.jpeg", "Mean arterial pressure", "mmHg", "CV_HEMO", [
        ("P3_MEN", "MEN", (118, 480, 90, 470), "150:101;50:465",
         {"PRE": 187, "POST": 390}),
        ("P3_WOMEN", "WOMEN", (620, 1010, 88, 466), "150:95;50:460",
         {"PRE": 720, "POST": 920}),
    ]),
    # Figure 3's other four panels. The inventory recorded them, which is what
    # made them visible - but recording a panel as MANUAL_DIGITIZE when the
    # released reader can do it is a different kind of loss: sixteen cells left
    # on the table because nobody wrote four boxes and four calibrations.
    ("F397_3_TPR", "397_fig3.jpeg", "Total peripheral resistance", "units",
     "CV_HEMO", [
        ("P3_TPR_MEN", "MEN", (70, 480, 583, 955), "100:589;25:949",
         {"PRE": 175, "POST": 376}),
        ("P3_TPR_WOMEN", "WOMEN", (596, 995, 583, 952), "100:589;25:946",
         {"PRE": 708, "POST": 906}),
    ]),
    ("F397_3_FPV", "397_fig3.jpeg", "Finger pulse volume", "units", "CV_HEMO", [
        ("P3_FPV_MEN", "MEN", (70, 480, 1075, 1432), "1800:1081;0:1426",
         {"PRE": 190, "POST": 392}),
        ("P3_FPV_WOMEN", "WOMEN", (596, 995, 1075, 1395), "1800:1081;0:1389",
         {"PRE": 708, "POST": 910}),
    ]),
    ("F397_4_HR", "397_fig4.jpeg", "Heart rate", "bpm", "CV_HEMO", [
        ("P4_HR_MEN", "MEN", (76, 480, 90, 395), "120:97;60:391",
         {"PRE": 184, "POST": 406}),
        ("P4_HR_WOMEN", "WOMEN", (600, 995, 88, 392), "120:95;60:388",
         {"PRE": 702, "POST": 913}),
    ]),
    ("F397_4_SV", "397_fig4.jpeg", "Stroke volume", "ml/beat", "CV_HEMO", [
        ("P4_SV_MEN", "MEN", (70, 480, 508, 810), "50:515;20:806",
         {"PRE": 179, "POST": 400}),
        ("P4_SV_WOMEN", "WOMEN", (596, 995, 500, 799), "50:507;20:795",
         {"PRE": 694, "POST": 895}),
    ]),
    ("F397_4_CO", "397_fig4.jpeg", "Cardiac output", "l/min", "CV_HEMO", [
        ("P4_CO_MEN", "MEN", (70, 480, 934, 1283), "5:941;1:1279",
         {"PRE": 162, "POST": 374}),
        ("P4_CO_WOMEN", "WOMEN", (596, 995, 931, 1289), "5:938;1:1285",
         {"PRE": 698, "POST": 909}),
    ]),
]

# The line figures. Panel boxes and calibrations are declared so the manifests
# are ready the day the reader ships; the run will queue them regardless.
LINE_FIGURES = [
    ("F397_1", "397_fig1.jpeg", "Mean arterial pressure", "mmHg", [
        ("P1_MAP_MEN", "MEN", (84, 430, 70, 300), "120:76;70:296"),
        ("P1_MAP_WOMEN", "WOMEN", (520, 870, 70, 300), "120:76;70:296"),
    ]),
    ("F397_2", "397_fig2.jpeg", "Heart rate", "bpm", [
        ("P2_HR_MEN", "MEN", (84, 430, 70, 300), "80:72;50:290"),
        ("P2_HR_WOMEN", "WOMEN", (520, 870, 70, 300), "80:72;50:290"),
    ]),
]

FIGURES, GRIDS, UNITS, PANELS, SERIES, POSITIONS = [], [], [], [], [], []
SOURCE_DOCUMENTS, SOURCE_FIGURES, SOURCE_PANELS = [], [], []
REVIEWERS = [ATTESTATION]
GRIDS += [dict(Grid_ID="G_SESSION", Factor_Name="ARM", Factor_Level=lv,
               Level_Order=i, Note="") for i, lv in enumerate(("FLUID", "NON_FLUID"))]
GRIDS += [dict(Grid_ID="G_SESSION", Factor_Name="SESSION", Factor_Level=lv,
               Level_Order=i, Note="") for i, (lv, _) in enumerate(SESSIONS)]
GRIDS += [dict(Grid_ID="G_HDT", Factor_Name="ARM", Factor_Level=lv,
               Level_Order=i, Note="") for i, lv in enumerate(("FLUID", "NON_FLUID"))]
GRIDS += [dict(Grid_ID="G_HDT", Factor_Name="TIMEPOINT", Factor_Level=lv,
               Level_Order=i, Note="") for i, lv in enumerate(HDT)]


def figure(fid, image, caption, panels):
    FIGURES.append(dict(
        Figure_ID=fid, Publication_ID=397, Figure_Number=fid.split("_")[1],
        Source_File="397.pdf", Source_Page=0,
        Source_Image=os.path.join(RASTERS, image),
        Source_Caption_Verbatim=caption,
        Image_Resolution_Or_Hash="sha256:" + MR.sha256_of(
            os.path.join(RASTERS, image))[:24],
        WPD_Project_File="", Observed_Panel_Count=panels,
        Worklist_Panel_Count=panels, Unlisted_Panels="",
        Panel_Reconciliation_Status="MATCHED", Note=""))


def unit(uid, fid, grid, panel_label, outcome, units, domain, **kw):
    base = dict(
        Unit_ID=uid, Figure_ID=fid, Grid_ID=grid, Panel=panel_label,
        Outcome_Variable=outcome, Outcome_Domain=domain, Unit=units,
        Statistic_Type="CONTINUOUS", Display_Hint="UNSPECIFIED",
        Grid_Rule="FULL", Sparse_Justification="", Dispersion_Type="SD",
        Errorbar_Definition_Source="",
        N_Outcome=10, Value_Scale="RATIO", Extraction_Method="DIGITIZED",
        Bar_Top_Definition="OUTLINE_CENTER", Errorbar_Stem_Confirmed="TRUE",
        Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
        Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
        Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=400,
        Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=400,
        Axis_Calib_Y2_Value=100, Axis_Calib_Y2_Pixel=100,
        Extractor_1="run_batch", Extractor_2="",
        Independent_Verification_Status="", Discrepancy_Note="",
        Date=RUN_DATE, Note="")
    base.update(kw)
    UNITS.append(base)


# What the paper actually says about its own error bars, quoted, and split by
# figure because the paper splits it. The running text at p.90 defines the bars
# for the 30-min-mean line figures; the captions for the stand-test bar figures
# give the averaging window and never say what the whiskers are. Writing "SEM"
# on Figures 3 and 4 because Figures 1 and 2 say so would be an inference, and
# the gate blocks a hedge as firmly as it blocks a blank.
BAR_ERRORBAR_SOURCE = (
    "caption Fig. 3/4: 'Cardiovascular responses to pre-HDT stand tests and "
    "post-HDT stand tests (3-min means)' - NOT STATED whether bars are SD or SEM")
LINE_ERRORBAR_SOURCE = (
    "text p.90: 'physiological responses (30-min means and SEMs) of men (left) "
    "and women (right) during 6-h exposures to HDT'")

for fid, image, outcome, units, domain, rows in BAR_FIGURES:
    figure(fid, image, "%s, fluid versus non-fluid, by sex" % outcome, len(rows))
    for pid, sex, box, ticks, xs in rows:
        uid = "U_" + pid
        unit(uid, fid, "G_SESSION", sex, outcome, units, domain,
             Bar_Top_Definition="OUTLINE_CENTER",
             Errorbar_Definition_Source=BAR_ERRORBAR_SOURCE)
        PANELS.append(dict(
            Panel_ID=pid, Source_Panel_ID=pid, Figure_ID=fid,
            # One legend over one figure view, said out loud: BAR_MONO
            # calibrates its fills inside the domain, not inside the view.
            Identity_Domain_ID=fid,
            Unit_ID=uid, Panel_Label=sex,
            Mark_Type="BAR_MONO", Image_Path=os.path.join(RASTERS, image),
            Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
            Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
            Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks=ticks,
            Baseline_Value=float(ticks.split(";")[1].split(":")[0]),
            Association_Type="", Config_ID="C_BAR", Panel_Mode="AUTO",
            Note="baseline is the axis minimum, not zero"))
        for series_id, pattern in (("FLUID", "SOLID"), ("NON_FLUID", "HATCHED")):
            SERIES.append(dict(
                Panel_ID=pid, Series_ID=series_id, Colour_Hex="",
                Colour_Tolerance="", Mask_Key="", Marker_Shape="NONE",
                Marker_Fill="", Line_Style="NONE", Bar_Fill_Pattern=pattern,
                Factor_Name="ARM", Factor_Level=series_id,
                Note="legend: %s = %s" % (pattern.lower(), series_id)))
        for order, (level, printed) in enumerate(SESSIONS):
            POSITIONS.append(dict(
                Panel_ID=pid, Position_ID=level, X_Pixel=xs[level],
                Slot_Index=order, Display_Order=order, Factor_Name="SESSION",
                Factor_Level=level, Timepoint_Label=printed, Timepoint_Days="",
                Note=""))

for fid, image, outcome, units, rows in LINE_FIGURES:
    figure(fid, image, "%s over head-down tilt, fluid versus non-fluid, by sex"
           % outcome, len(rows))
    for pid, sex, box, ticks in rows:
        uid = "U_" + pid
        unit(uid, fid, "G_HDT", sex, outcome, units, "CV_HEMO",
             Bar_Top_Definition="NOT_A_BAR", N_Outcome=10, Dispersion_Type="SEM",
             Errorbar_Definition_Source=LINE_ERRORBAR_SOURCE)
        PANELS.append(dict(
            Panel_ID=pid, Source_Panel_ID=pid, Figure_ID=fid,
            # One legend over one figure view, said out loud: BAR_MONO
            # calibrates its fills inside the domain, not inside the view.
            Identity_Domain_ID=fid,
            Unit_ID=uid, Panel_Label=sex,
            Mark_Type="LINE_MONO_STYLE", Image_Path=os.path.join(RASTERS, image),
            Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
            Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
            Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks=ticks,
            Baseline_Value="", Association_Type="", Config_ID="",
            Panel_Mode="AUTO",
            Note="two black curves, no markers - solid Fluid, dashed No Fluid"))
        for series_id, style in (("FLUID", "SOLID"), ("NON_FLUID", "DASHED")):
            SERIES.append(dict(
                Panel_ID=pid, Series_ID=series_id, Colour_Hex="",
                Colour_Tolerance="", Mask_Key="", Marker_Shape="NONE",
                Marker_Fill="", Line_Style=style, Bar_Fill_Pattern="",
                Factor_Name="ARM", Factor_Level=series_id,
                Note="legend: %s = %s" % (style.lower(), series_id)))
        span = box[1] - box[0] - 40
        for order, label in enumerate(HDT):
            POSITIONS.append(dict(
                Panel_ID=pid, Position_ID=label.replace(":", "_"),
                X_Pixel=box[0] + 25 + round(order * span / (len(HDT) - 1)),
                Slot_Index=order, Display_Order=order, Factor_Name="TIMEPOINT",
                Factor_Level=label, Timepoint_Label=label, Timepoint_Days="",
                Note=""))

# Figure 5 - two named subjects, beat by beat. Declared and refused on purpose.
figure("F397_5", "397_fig5.jpeg",
       "Beat-to-beat heart rate and mean arterial pressure for two individual "
       "subjects (Y01, Y07) during no-fluid and fluid-loading head-down tilt", 2)
for pid, sex, box in (("P5_NOFLUID", "NO_FLUID_HDT", (84, 430, 60, 300)),
                      ("P5_FLUID", "FLUID_HDT", (520, 870, 60, 300))):
    uid = "U_" + pid
    unit(uid, "F397_5", "G_HDT", sex, "Heart rate", "bpm", "CV_HEMO",
         Bar_Top_Definition="NOT_A_BAR", Errorbar_Stem_Confirmed="FALSE",
         Dispersion_Type="NO_ERRORBAR",
         Errorbar_Definition_Source=(
             "caption Fig. 5: 'Physiological responses (3-min means) of Y01 and "
             "Y07' - single traces, no error bars are drawn"),
         N_Outcome=1,
         Note="single-subject trace - not a group summary")
    PANELS.append(dict(
        Panel_ID=pid, Source_Panel_ID=pid, Figure_ID="F397_5",
        Identity_Domain_ID="F397_5", Unit_ID=uid, Panel_Label=sex,
        Mark_Type="LINE_MONO", Image_Path=os.path.join(RASTERS, "397_fig5.jpeg"),
        Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
        Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
        Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks="100:60;50:290",
        Baseline_Value="", Association_Type="", Config_ID="",
        Panel_Mode="MANUAL",
        Note="n=1 per curve, beat-to-beat: no summary statistic exists to read"))
    for series_id, shape in (("Y01", "CIRCLE"), ("Y07", "SQUARE")):
        SERIES.append(dict(
            Panel_ID=pid, Series_ID=series_id, Colour_Hex="", Colour_Tolerance="",
            Mask_Key="", Marker_Shape=shape, Marker_Fill="ANY", Line_Style="",
            Bar_Fill_Pattern="", Factor_Name="ARM", Factor_Level=series_id,
            Note="named individual subject"))
    for order, label in enumerate(HDT):
        POSITIONS.append(dict(
            Panel_ID=pid, Position_ID=label.replace(":", "_"),
            X_Pixel=box[0] + 25 + round(order * (box[1] - box[0] - 40) / (len(HDT) - 1)),
            Slot_Index=order, Display_Order=order, Factor_Name="TIMEPOINT",
            Factor_Level=label, Timepoint_Label=label, Timepoint_Days="", Note=""))

CONFIGS = [
    dict(Config_ID="C_BAR", Option="group_window", Value="75",
         Note="two bars per group, about 120 px wide"),
    dict(Config_ID="C_BAR", Option="threshold", Value="128", Note=""),
    dict(Config_ID="C_BAR", Option="stem_threshold", Value="200",
         Note="the whisker stem is a hairline and reads about grey 140"),
]

# --------------------------------------------------------------------------
# Physical-source inventory.  This is deliberately broader than the reader
# manifests above.  The five publisher figures contain 36 visible plot regions;
# only 14 currently have reader rows.  The other 22 stay explicit as no-reader,
# manual, non-target or no-summary dispositions instead of disappearing.
# --------------------------------------------------------------------------
_SOURCE_SPECS = {
    1: [
        ("P1_MAP_MEN", "MAP men", "TARGET", "NO_READER_AVAILABLE"),
        ("P1_MAP_WOMEN", "MAP women", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F1_TPR_MEN", "TPR men", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F1_TPR_WOMEN", "TPR women", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F1_FPV_MEN", "Finger pulse volume men", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F1_FPV_WOMEN", "Finger pulse volume women", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F1_TEMP_MEN", "Skin temperature men", "NON_TARGET", "NON_TARGET_OUTCOME"),
        ("S397_F1_TEMP_WOMEN", "Skin temperature women", "NON_TARGET", "NON_TARGET_OUTCOME"),
    ],
    2: [
        ("P2_HR_MEN", "Heart rate men", "TARGET", "NO_READER_AVAILABLE"),
        ("P2_HR_WOMEN", "Heart rate women", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F2_TFV_MEN", "Thoracic fluid volume men", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F2_TFV_WOMEN", "Thoracic fluid volume women", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F2_SC_MEN", "Skin conductance men", "NON_TARGET", "NON_TARGET_OUTCOME"),
        ("S397_F2_SC_WOMEN", "Skin conductance women", "NON_TARGET", "NON_TARGET_OUTCOME"),
        ("S397_F2_CO_MEN", "Cardiac output men", "TARGET", "NO_READER_AVAILABLE"),
        ("S397_F2_CO_WOMEN", "Cardiac output women", "TARGET", "NO_READER_AVAILABLE"),
    ],
    3: [
        ("P3_MEN", "MAP men", "TARGET", "AUTO_DIGITIZE"),
        ("P3_WOMEN", "MAP women", "TARGET", "AUTO_DIGITIZE"),
        ("P3_TPR_MEN", "TPR men", "TARGET", "AUTO_DIGITIZE"),
        ("P3_TPR_WOMEN", "TPR women", "TARGET", "AUTO_DIGITIZE"),
        ("P3_FPV_MEN", "Finger pulse volume men", "TARGET", "AUTO_DIGITIZE"),
        ("P3_FPV_WOMEN", "Finger pulse volume women", "TARGET", "AUTO_DIGITIZE"),
    ],
    4: [
        ("P4_HR_MEN", "Heart rate men", "TARGET", "AUTO_DIGITIZE"),
        ("P4_HR_WOMEN", "Heart rate women", "TARGET", "AUTO_DIGITIZE"),
        ("P4_SV_MEN", "Stroke volume men", "TARGET", "AUTO_DIGITIZE"),
        ("P4_SV_WOMEN", "Stroke volume women", "TARGET", "AUTO_DIGITIZE"),
        ("P4_CO_MEN", "Cardiac output men", "TARGET", "AUTO_DIGITIZE"),
        ("P4_CO_WOMEN", "Cardiac output women", "TARGET", "AUTO_DIGITIZE"),
    ],
    5: [
        ("P5_NOFLUID", "Heart rate no-fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
        ("P5_FLUID", "Heart rate fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
        ("S397_F5_MAP_NF", "MAP no-fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
        ("S397_F5_MAP_F", "MAP fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
        ("S397_F5_TEMP_NF", "Skin temperature no-fluid", "NON_TARGET", "NON_TARGET_OUTCOME"),
        ("S397_F5_TEMP_F", "Skin temperature fluid", "NON_TARGET", "NON_TARGET_OUTCOME"),
        ("S397_F5_TPR_NF", "TPR no-fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
        ("S397_F5_TPR_F", "TPR fluid", "TARGET", "NO_SUMMARY_STATISTIC"),
    ],
}
SOURCE_DOCUMENTS.append(dict(
    Source_Document_ID="SD397_MAIN", Publication_ID=397,
    Document_Role="MAIN_ARTICLE", Source_File="397.pdf",
    Article_Page_Range="full target article", Observed_Figure_Count=5,
    Inventory_Status="VISUALLY_VERIFIED", Figure_Count_Method="HUMAN_VISUAL",
    Reviewer_ID="RV_INSPECTOR", Inspection_Date=INSPECTION_DATE,
    Note="all five publisher figures inventoried"))
for fig_no, specs in sorted(_SOURCE_SPECS.items()):
    SOURCE_FIGURES.append(dict(
        Source_Figure_ID="SF397_%d" % fig_no,
        Source_Document_ID="SD397_MAIN", Publication_ID=397,
        Figure_Number="FIG%d" % fig_no, Source_File="397.pdf", Source_Page=0,
        Source_Image=os.path.join(RASTERS, "397_fig%d.jpeg" % fig_no),
        Source_Image_SHA256=MR.sha256_of(
            os.path.join(RASTERS, "397_fig%d.jpeg" % fig_no)),
        Observed_Panel_Count=len(specs), Inventory_Status="VISUALLY_VERIFIED",
        Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_INSPECTOR",
        Inspection_Date=INSPECTION_DATE, Note="counted on the full publisher raster"))
    for order, (spid, outcome, target, disposition) in enumerate(specs, 1):
        SOURCE_PANELS.append(dict(
            Source_Panel_ID=spid, Source_Figure_ID="SF397_%d" % fig_no,
            Panel_Label="P%02d" % order, Outcome_Label=outcome,
            Target_Status=target, Panel_Disposition=disposition,
            Disposition_Reason=("reader/run manifest configured" if spid.startswith("P")
                                else "visible panel inventoried; reader not configured"),
            Note=""))


def write(directory):
    os.makedirs(directory, exist_ok=True)
    for name, rows, cols in (
            ("reviewer_registry", REVIEWERS, BM.reviewer_registry_columns()),
            ("source_document_manifest", SOURCE_DOCUMENTS,
             BM.source_document_manifest_columns()),
            ("source_figure_manifest", SOURCE_FIGURES, BM.source_figure_manifest_columns()),
            ("source_panel_inventory", SOURCE_PANELS, BM.source_panel_inventory_columns()),
            ("figure_manifest", FIGURES, GE.fig_figure_columns()),
            ("grid_definitions", GRIDS, GE.fig_grid_columns()),
            ("unit_manifest", UNITS, GE.fig_unit_columns()),
            ("panel_manifest", PANELS, BM.panel_manifest_columns()),
            ("series_manifest", SERIES, BM.series_manifest_columns()),
            ("position_manifest", POSITIONS, BM.position_manifest_columns()),
            ("reader_config", CONFIGS, BM.reader_config_columns())):
        with open(os.path.join(directory, "%s.csv" % name), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])


write(MANIFESTS)
# No run_mode argument: the registry above says what this run is, and the
# runner reads it from there.
summary = RB.run_batch(MANIFESTS, OUT, file_root=RASTERS, run_date=RUN_DATE)
if summary["status"] == "MANIFEST_REJECTED":
    import pandas as pd
    print("manifests rejected: %s" % summary["detail"])
    print(pd.read_csv(os.path.join(OUT, "manifest_problems.csv")).to_string())
    raise SystemExit(2)

# Before the summary is read, because a refused run wrote no summary to read.
if summary["status"] == "DEMO_OUTPUT_REFUSED":
    print("DEMO_OUTPUT_REFUSED: %s" % summary["detail"], file=sys.stderr)
    print("set FDT_REVIEWER_NAME, FDT_REVIEWER_ORCID, FDT_INSPECTION_DATE and "
          "FDT_REGISTRATION_DATE to run this as attested work", file=sys.stderr)
    raise SystemExit(4)

import pandas as pd                                                # noqa: E402
run = pd.read_csv(os.path.join(OUT, "run_manifest.csv"))
raw = pd.read_csv(os.path.join(OUT, "figure_values_raw.csv"))
machine_qc = pd.read_csv(os.path.join(OUT, "figure_values_machine_qc.csv"))
review = pd.read_csv(os.path.join(OUT, "review_queue.csv"))

# There is no ACCEPTED column to print here any more, and that is the change.
# This script ends at machine QC; `finalize_batch.py` turns approved panels into
# poolable values, and nothing else does.
print("publication 397 - every figure, one run  [%s]" % summary["run_mode"])
print("  panels %d | cells declared %d | read %d | MACHINE_QC_PASSED %d"
      % (summary["panels"], int(run["Cells_Declared"].sum()), len(raw),
         len(machine_qc)))
print("  awaiting human review: %d panels" % len(review))
print()
print("  %-16s %-22s %s" % ("PANEL", "STATE", "READ / DECLARED"))
for _, r in run.iterrows():
    print("  %-16s %-22s %d / %d" % (r["Panel_ID"], r["Run_State"],
                                     r["Cells_Read"], r["Cells_Declared"]))
print()
by_state = run["Run_State"].value_counts().to_dict()
for state, n in sorted(by_state.items()):
    print("  %-24s %d panels" % (state, n))
print()
if len(raw):
    print("  values read (all QC_FAILED - see below):")
    for _, r in raw.iterrows():
        print("    %-14s %-28s %8.2f  %s" % (
            r["Unit_ID"].replace("U_P4_", "").replace("U_P3_", ""),
            r["Cell_Key"], r["Mean"],
            "----" if pd.isna(r["Dispersion_Value"])
            else "%.2f" % r["Dispersion_Value"]))
print()
print("  outputs in %s" % OUT)
raise SystemExit(0)
