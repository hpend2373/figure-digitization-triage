"""Worked example: one real publication, read entirely from manifests.

    python3 build_397.py [OUTPUT_DIR]

`build_id323.py` shows the four data grains built by a script that knows the
figure. This shows the other half: nothing here reads a raster or names a
series. It writes seven CSVs and calls `run_batch`, which is the shape a
160-publication batch actually takes.

Publication 397 Figure 3 is a monochrome grouped bar chart - solid "Fluid"
against hatched "Non Fluid", two sessions, two panels split by sex. Everything
the reader needs to know about it lives in `panel_manifest.csv`,
`series_manifest.csv` and `position_manifest.csv`; everything it needs to know
about the STUDY lives in the three data-grain manifests. Neither file mentions
the other's business.

The two panels' axes sit four pixels apart, which is why each carries its own
calibration. Sharing one - which looks safe, since both are labelled 50 to 150 -
put the second panel's baseline below its own bars and the reader returned
nothing for all four of its cells.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import mark_readers as MR                                          # noqa: E402
import run_batch as RB                                             # noqa: E402

IMAGE = os.path.join(HERE, "397_fig3.jpeg")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out_397")
MANIFESTS = os.path.join(OUT, "manifests")

if not os.path.exists(IMAGE):
    print("SKIP: publisher raster not found: %s" % IMAGE)
    raise SystemExit(0)

SHA = MR.sha256_of(IMAGE)
SESSIONS = [("PRE", "Pre HDT Stand", 0), ("POST", "Post HDT Stand", 60)]

FIGURES = [dict(
    Figure_ID="F397_3", Publication_ID=397, Figure_Number="Figure 3",
    Source_File="397.pdf", Source_Page=3, Source_Image=IMAGE,
    Source_Caption_Verbatim=("Mean arterial pressure before and after head-down "
                             "tilt, fluid versus non-fluid, by sex"),
    Image_Resolution_Or_Hash="1021x1462 sha256:" + SHA[:24],
    WPD_Project_File="", Observed_Panel_Count=2, Worklist_Panel_Count=2,
    Unlisted_Panels="", Panel_Reconciliation_Status="MATCHED", Note="")]

GRIDS = ([dict(Grid_ID="G397", Factor_Name="ARM", Factor_Level=lv, Level_Order=i,
               Note="") for i, lv in enumerate(("FLUID", "NON_FLUID"))]
         + [dict(Grid_ID="G397", Factor_Name="SESSION", Factor_Level=lv,
                 Level_Order=i, Note="") for i, (lv, _, _) in enumerate(SESSIONS)])


def unit(uid, panel_label):
    return dict(
        Unit_ID=uid, Figure_ID="F397_3", Grid_ID="G397", Panel=panel_label,
        Outcome_Variable="Mean arterial pressure", Outcome_Domain="CV_HEMO",
        Unit="mmHg", Statistic_Type="CONTINUOUS", Display_Hint="UNSPECIFIED",
        Grid_Rule="FULL", Sparse_Justification="", Dispersion_Type="SD",
        Errorbar_Definition_Source=("UNRESOLVED - the caption does not state "
                                    "whether the whiskers are SD or SEM"),
        N_Outcome=10, Value_Scale="RATIO", Extraction_Method="DIGITIZED",
        Bar_Top_Definition="OUTLINE_CENTER", Errorbar_Stem_Confirmed="TRUE",
        Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
        Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=118,
        Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=480,
        Axis_Calib_Y1_Value=50, Axis_Calib_Y1_Pixel=465,
        Axis_Calib_Y2_Value=150, Axis_Calib_Y2_Pixel=101,
        Extractor_1="run_batch", Extractor_2="", Independent_Verification_Status="",
        Discrepancy_Note="", Date="2026-08-06", Note="")


UNITS = [unit("U397_MEN", "MEN"), unit("U397_WOMEN", "WOMEN")]

PANEL_GEOMETRY = (
    ("P397_MEN", "U397_MEN", "MEN", (118, 480, 90, 470), "150:101;50:465",
     {"PRE": 187, "POST": 390}),
    ("P397_WOMEN", "U397_WOMEN", "WOMEN", (620, 1010, 88, 466), "150:95;50:460",
     {"PRE": 720, "POST": 920}),
)

PANELS, SERIES, POSITIONS = [], [], []
for pid, uid, label, box, ticks, xs in PANEL_GEOMETRY:
    PANELS.append(dict(
        Panel_ID=pid, Figure_ID="F397_3", Unit_ID=uid, Panel_Label=label,
        Mark_Type="BAR_MONO", Image_Path=IMAGE,
        Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
        Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
        Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks=ticks,
        Baseline_Value=50, Association_Type="", Config_ID="C397",
        Panel_Mode="AUTO", Note="baseline is 50 mmHg, not zero"))
    for series_id, pattern in (("FLUID", "SOLID"), ("NON_FLUID", "HATCHED")):
        SERIES.append(dict(
            Panel_ID=pid, Series_ID=series_id, Colour_Hex="", Colour_Tolerance="",
            Mask_Key="", Marker_Shape="NONE", Marker_Fill="", Line_Style="NONE",
            Bar_Fill_Pattern=pattern, Factor_Name="ARM", Factor_Level=series_id,
            Note="legend: %s = %s" % (pattern.lower(), series_id)))
    for order, (level, printed, minutes) in enumerate(SESSIONS):
        POSITIONS.append(dict(
            Panel_ID=pid, Position_ID=level, X_Pixel=xs[level], Slot_Index=order,
            Display_Order=order, Factor_Name="SESSION", Factor_Level=level,
            Timepoint_Label=printed, Timepoint_Days="", Note=""))

CONFIGS = [
    dict(Config_ID="C397", Option="group_window", Value="75",
         Note="two bars per group, about 118 px wide"),
    dict(Config_ID="C397", Option="threshold", Value="128", Note=""),
    dict(Config_ID="C397", Option="stem_threshold", Value="200",
         Note="the whisker stem is a hairline and reads about grey 140"),
]


def write(directory):
    os.makedirs(directory, exist_ok=True)
    for name, rows, cols in (
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
summary = RB.run_batch(MANIFESTS, OUT, file_root=HERE, run_date="2026-08-06")
if summary["status"] == "MANIFEST_REJECTED":
    print("manifests rejected: %s" % summary["detail"])
    raise SystemExit(2)

print("publication 397 Figure 3, read from manifests alone")
print("  panels %d | values read %d | ACCEPTED %d | qc problems %d | queue %d"
      % (summary["panels"], summary["values"], summary["accepted"],
         summary["qc_problems"], summary["manual_queue"]))
for state, n in sorted(summary["states"].items()):
    print("  %-28s %d" % (state, n))

import pandas as pd                                                # noqa: E402
values = pd.read_csv(os.path.join(OUT, "figure_values_raw.csv"))
accepted = pd.read_csv(os.path.join(OUT, "figure_values_accepted.csv"))
for _, r in values.iterrows():
    print("  %-12s %-30s mean %6.1f  sd %-5s %s"
          % (r["Unit_ID"], r["Cell_Key"], r["Mean"],
             "----" if pd.isna(r["Dispersion_Value"])
             else "%.1f" % r["Dispersion_Value"], r["Value_Status"]))
print("  figure_values_accepted.csv: %d rows" % len(accepted))
print()
print("  outputs in %s" % OUT)
print()
print("  Both panels land on QC_FAILED, and that is the demonstration, not a")
print("  defect. The caption does not say whether the whiskers are SD or SEM, so")
print("  Errorbar_Definition_Source records UNRESOLVED - and the gate refuses to")
print("  accept Dispersion_Type=SD sitting beside it, because SD-versus-SEM")
print("  scales the meta-analytic weight by sqrt(n). The eight means are read,")
print("  saved and auditable; the figure cannot enter a pooled variance until")
print("  somebody reads the paper's methods. That is the state of the evidence.")
raise SystemExit(0 if (summary["values"] == 8 and summary["accepted"] == 0)
                 else 1)
