"""Pilot: publication 397, EVERY panel of every figure, in one run.

    python3 pilot_397.py [OUTPUT_DIR]

Thirty-six panels across five figures. Twenty-four are target cardiovascular
outcomes; twelve are not, and every one of those twelve still gets a row.

    Figure 1   8 panels   MAP, TPR, finger pulse volume, skin temperature
    Figure 2   8 panels   HR, thoracic fluid volume, skin conductance, cardiac output
    Figure 3   6 panels   MAP, TPR, finger pulse volume          (stand tests)
    Figure 4   6 panels   HR, stroke volume, cardiac output      (stand tests)
    Figure 5   8 panels   two named subjects, beat by beat

The first version of this pilot declared fourteen. It split each source figure
into per-outcome virtual figures, gave each `Observed_Panel_Count=2`, and every
one of them reported MATCHED - so twenty-two real panels, sixteen of them target
outcomes, were invisible to the reconciliation that exists to catch exactly
that. Four of the sixteen were bar panels the released reader could already do.

Two rules came out of it, and both are now enforced by the validator rather than
by whoever writes the manifest:

* **one Figure_ID per printed figure**, carrying the real panel count
* **every panel gets a row**, with `Panel_Disposition` saying why it is or is
  not extracted. A panel with no row is invisible; a panel marked NON_TARGET is
  a decision somebody can disagree with.

Skin temperature and skin conductance are `NON_TARGET` here - real measurements,
outside a cardiovascular review's outcome set. Figure 5 is
`NO_SUMMARY_STATISTIC`: two named individuals plotted beat by beat, which is not
a summary statistic and never will be.
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

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out_pilot_397")
MANIFESTS = os.path.join(OUT, "manifests")
SESSIONS = [("PRE", "Pre HDT Stand"), ("POST", "Post HDT Stand")]
HDT = ["0:30", "1:00", "1:30", "2:00", "2:30", "3:00",
       "3:30", "4:00", "4:30", "5:00", "5:30", "6:00"]

# What the paper says about its own error bars, quoted, and split by figure
# because the paper splits it. The running text defines the bars for the
# 30-min-mean line figures; the stand-test captions give the averaging window
# and never say what the whiskers are.
LINE_SRC = ("text p.90: 'physiological responses (30-min means and SEMs) of men "
            "(left) and women (right) during 6-h exposures to HDT'")
BAR_SRC = ("caption Fig. 3/4: 'Cardiovascular responses to pre-HDT stand tests "
           "and post-HDT stand tests (3-min means)' - NOT STATED whether the "
           "bars are SD or SEM")
TRACE_SRC = ("caption Fig. 5: 'Physiological responses (3-min means) of Y01 and "
             "Y07' - single subjects, no error bars are drawn")

# --------------------------------------------------------------------------
# every panel of every figure, measured off the rasters
# --------------------------------------------------------------------------
BAR_PANELS = {
    "F397_3": ("397_fig3.jpeg", 6, [
        ("P3_MAP_MEN", "Mean arterial pressure", "mmHg", "MEN",
         (118, 480, 90, 470), "150:101;50:465", {"PRE": 187, "POST": 390}),
        ("P3_MAP_WOMEN", "Mean arterial pressure", "mmHg", "WOMEN",
         (620, 1010, 88, 466), "150:95;50:460", {"PRE": 720, "POST": 920}),
        ("P3_TPR_MEN", "Total peripheral resistance", "units", "MEN",
         (70, 480, 583, 955), "100:589;25:949", {"PRE": 175, "POST": 376}),
        ("P3_TPR_WOMEN", "Total peripheral resistance", "units", "WOMEN",
         (596, 995, 583, 952), "100:589;25:946", {"PRE": 708, "POST": 906}),
        ("P3_FPV_MEN", "Finger pulse volume", "units", "MEN",
         (70, 480, 1075, 1432), "1800:1081;0:1426", {"PRE": 190, "POST": 392}),
        ("P3_FPV_WOMEN", "Finger pulse volume", "units", "WOMEN",
         (596, 995, 1075, 1395), "1800:1081;0:1389", {"PRE": 708, "POST": 910}),
    ]),
    "F397_4": ("397_fig4.jpeg", 6, [
        ("P4_HR_MEN", "Heart rate", "bpm", "MEN",
         (76, 480, 90, 395), "120:97;60:391", {"PRE": 184, "POST": 406}),
        ("P4_HR_WOMEN", "Heart rate", "bpm", "WOMEN",
         (600, 995, 88, 392), "120:95;60:388", {"PRE": 702, "POST": 913}),
        ("P4_SV_MEN", "Stroke volume", "ml/beat", "MEN",
         (70, 480, 508, 810), "50:515;20:806", {"PRE": 179, "POST": 400}),
        ("P4_SV_WOMEN", "Stroke volume", "ml/beat", "WOMEN",
         (596, 995, 500, 799), "50:507;20:795", {"PRE": 694, "POST": 895}),
        ("P4_CO_MEN", "Cardiac output", "l/min", "MEN",
         (70, 480, 934, 1283), "5:941;1:1279", {"PRE": 162, "POST": 374}),
        ("P4_CO_WOMEN", "Cardiac output", "l/min", "WOMEN",
         (596, 995, 931, 1289), "5:938;1:1285", {"PRE": 698, "POST": 909}),
    ]),
}

LINE_PANELS = {
    "F397_1": ("397_fig1.jpeg", 8, [
        ("P1_MAP_MEN", "Mean arterial pressure", "mmHg", "MEN",
         (84, 440, 68, 305), "120:75;70:295", "EXTRACT", ""),
        ("P1_MAP_WOMEN", "Mean arterial pressure", "mmHg", "WOMEN",
         (520, 880, 70, 305), "120:79;70:294", "EXTRACT", ""),
        ("P1_TPR_MEN", "Total peripheral resistance", "units", "MEN",
         (84, 440, 440, 652), "60:448;20:642", "EXTRACT", ""),
        ("P1_TPR_WOMEN", "Total peripheral resistance", "units", "WOMEN",
         (520, 880, 438, 655), "60:445;20:645", "EXTRACT", ""),
        ("P1_FPV_MEN", "Finger pulse volume", "units", "MEN",
         (84, 440, 790, 980), "2600:797;200:970", "EXTRACT", ""),
        ("P1_FPV_WOMEN", "Finger pulse volume", "units", "WOMEN",
         (520, 880, 792, 982), "2600:800;200:972", "EXTRACT", ""),
        ("P1_SKT_MEN", "Skin temperature", "degrees C", "MEN",
         (84, 440, 1094, 1313), "38:1100;26:1303", "NON_TARGET",
         "thermoregulatory, not a cardiovascular outcome of this review"),
        ("P1_SKT_WOMEN", "Skin temperature", "degrees C", "WOMEN",
         (520, 880, 1098, 1316), "38:1104;26:1306", "NON_TARGET",
         "thermoregulatory, not a cardiovascular outcome of this review"),
    ]),
    "F397_2": ("397_fig2.jpeg", 8, [
        ("P2_HR_MEN", "Heart rate", "bpm", "MEN",
         (84, 440, 76, 300), "80:83;50:289", "EXTRACT", ""),
        ("P2_HR_WOMEN", "Heart rate", "bpm", "WOMEN",
         (520, 880, 79, 302), "80:86;50:292", "EXTRACT", ""),
        ("P2_TFV_MEN", "Thoracic fluid volume", "ml", "MEN",
         (84, 440, 438, 650), "8000:446;5000:639", "EXTRACT", ""),
        ("P2_TFV_WOMEN", "Thoracic fluid volume", "ml", "WOMEN",
         (520, 880, 438, 656), "7000:445;4000:646", "EXTRACT", ""),
        ("P2_SCL_MEN", "Skin conductance level", "microsiemens", "MEN",
         (84, 440, 760, 1013), "22:767;2:1003", "NON_TARGET",
         "sudomotor/autonomic, not a cardiovascular outcome of this review"),
        ("P2_SCL_WOMEN", "Skin conductance level", "microsiemens", "WOMEN",
         (520, 880, 766, 1023), "22:774;2:1013", "NON_TARGET",
         "sudomotor/autonomic, not a cardiovascular outcome of this review"),
        ("P2_CO_MEN", "Cardiac output", "l/min", "MEN",
         (84, 440, 1142, 1396), "4.5:1149;2:1386", "EXTRACT", ""),
        ("P2_CO_WOMEN", "Cardiac output", "l/min", "WOMEN",
         (520, 880, 1141, 1395), "4.5:1148;2:1385", "EXTRACT", ""),
    ]),
}

TRACE_PANELS = ("397_fig5.jpeg", 8, [
    ("P5_%s_%s" % (code, cond), name, unit, cond)
    for code, name, unit in (("HR", "Heart rate", "bpm"),
                             ("MAP", "Mean arterial pressure", "mmHg"),
                             ("SKT", "Skin temperature", "degrees C"),
                             ("TPR", "Total peripheral resistance", "units"))
    for cond in ("NOFLUID", "FLUID")
])

FIGURES, GRIDS, UNITS, PANELS, SERIES, POSITIONS = [], [], [], [], [], []
for gid, factors in (("G_SESSION", [("ARM", ("FLUID", "NON_FLUID")),
                                    ("SESSION", tuple(l for l, _ in SESSIONS))]),
                     ("G_HDT", [("ARM", ("FLUID", "NON_FLUID")),
                                ("TIMEPOINT", tuple(HDT))])):
    for factor, levels in factors:
        GRIDS += [dict(Grid_ID=gid, Factor_Name=factor, Factor_Level=lv,
                       Level_Order=i, Note="") for i, lv in enumerate(levels)]


def figure(fid, image, caption, panel_count):
    FIGURES.append(dict(
        Figure_ID=fid, Publication_ID=397, Figure_Number=fid.split("_")[1],
        Source_File="397.pdf", Source_Page=0,
        Source_Image=os.path.join(HERE, image),
        Source_Caption_Verbatim=caption,
        Image_Resolution_Or_Hash="sha256:" + MR.sha256_of(
            os.path.join(HERE, image))[:24],
        WPD_Project_File="", Observed_Panel_Count=panel_count,
        Worklist_Panel_Count=panel_count, Unlisted_Panels="",
        Panel_Reconciliation_Status="MATCHED",
        Note="every panel of the printed figure has a row in panel_manifest"))


def unit(uid, fid, grid, panel_label, outcome, units, **kw):
    base = dict(
        Unit_ID=uid, Figure_ID=fid, Grid_ID=grid, Panel=panel_label,
        Outcome_Variable=outcome, Outcome_Domain="CV_HEMO", Unit=units,
        Statistic_Type="CONTINUOUS", Display_Hint="UNSPECIFIED",
        Grid_Rule="FULL", Sparse_Justification="", Dispersion_Type="SD",
        Errorbar_Definition_Source=BAR_SRC, N_Outcome=10, Value_Scale="RATIO",
        Extraction_Method="DIGITIZED", Bar_Top_Definition="OUTLINE_CENTER",
        Errorbar_Stem_Confirmed="TRUE", Axis_X_Scale="LINEAR",
        Axis_Y_Scale="LINEAR",
        Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
        Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=400,
        Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=400,
        Axis_Calib_Y2_Value=100, Axis_Calib_Y2_Pixel=100,
        Extractor_1="run_batch", Extractor_2="",
        Independent_Verification_Status="", Discrepancy_Note="",
        Date="2026-08-07", Note="")
    base.update(kw)
    UNITS.append(base)


def panel(pid, fid, image, mark, box, ticks, uid="", baseline="", config="",
          disposition="EXTRACT", mode="AUTO", label="", note=""):
    PANELS.append(dict(
        Panel_ID=pid, Figure_ID=fid, Unit_ID=uid, Panel_Label=label,
        Mark_Type=mark, Image_Path=os.path.join(HERE, image),
        Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
        Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
        Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks=ticks,
        Baseline_Value=baseline, Panel_Disposition=disposition,
        Association_Type="", Config_ID=config, Panel_Mode=mode, Note=note))


# ---- the bar figures: every panel is a target, and readable ---------------
for fid, (image, count, rows) in BAR_PANELS.items():
    figure(fid, image, "Cardiovascular responses to pre-HDT and post-HDT stand "
           "tests (3-min means), men (left) and women (right)", count)
    for pid, outcome, units, sex, box, ticks, xs in rows:
        uid = "U_" + pid
        unit(uid, fid, "G_SESSION", sex, outcome, units)
        panel(pid, fid, image, "BAR_MONO", box, ticks, uid=uid,
              baseline=float(ticks.split(";")[1].split(":")[0]),
              config="C_BAR", label=sex,
              note="baseline is the axis minimum, not zero")
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

# ---- the line figures: targets await a reader, two panels are not targets --
for fid, (image, count, rows) in LINE_PANELS.items():
    figure(fid, image, "Physiological data in 30-min means during 6 h of HDT, "
           "men (left) and women (right)", count)
    for pid, outcome, units, sex, box, ticks, disposition, note in rows:
        if disposition != "EXTRACT":
            panel(pid, fid, image, "", box, ticks, disposition=disposition,
                  label=sex, note=note)
            continue
        uid = "U_" + pid
        unit(uid, fid, "G_HDT", sex, outcome, units, Dispersion_Type="SEM",
             Errorbar_Definition_Source=LINE_SRC, Bar_Top_Definition="NOT_A_BAR")
        panel(pid, fid, image, "LINE_MONO_STYLE", box, ticks, uid=uid, label=sex,
              note="two black curves, no markers - solid Fluid, dashed No Fluid")
        for series_id, style in (("FLUID", "SOLID"), ("NON_FLUID", "DASHED")):
            SERIES.append(dict(
                Panel_ID=pid, Series_ID=series_id, Colour_Hex="",
                Colour_Tolerance="", Mask_Key="", Marker_Shape="NONE",
                Marker_Fill="", Line_Style=style, Bar_Fill_Pattern="",
                Factor_Name="ARM", Factor_Level=series_id,
                Note="legend: %s = %s" % (style.lower(), series_id)))
        span = box[1] - box[0] - 45
        for order, label in enumerate(HDT):
            POSITIONS.append(dict(
                Panel_ID=pid, Position_ID=label.replace(":", "_"),
                X_Pixel=box[0] + 28 + round(order * span / (len(HDT) - 1)),
                Slot_Index=order, Display_Order=order, Factor_Name="TIMEPOINT",
                Factor_Level=label, Timepoint_Label=label, Timepoint_Days="",
                Note=""))

# ---- the individual-trace figure: eight rows, none of them extractable ----
_image, _count, _rows = TRACE_PANELS
figure("F397_5", _image,
       "Physiological responses (3-min means) of Y01 - syncope after no fluid "
       "HDT - and Y07, who had no symptoms after either test", _count)
for pid, outcome, units, cond in _rows:
    panel(pid, "F397_5", _image, "", (84, 440, 60, 320), "100:60;50:290",
          disposition="NO_SUMMARY_STATISTIC", label=cond,
          note="%s plotted for two named subjects (Y01, Y07) beat by beat: n=1 "
               "per curve, no summary statistic exists to read. %s"
               % (outcome, TRACE_SRC))

CONFIGS = [
    dict(Config_ID="C_BAR", Option="group_window", Value="75",
         Note="two bars per group, about 120 px wide"),
    dict(Config_ID="C_BAR", Option="threshold", Value="128", Note=""),
    dict(Config_ID="C_BAR", Option="stem_threshold", Value="200",
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


if not all(os.path.exists(os.path.join(HERE, "397_fig%d.jpeg" % i))
           for i in range(1, 6)):
    print("SKIP: publisher rasters not found")
    raise SystemExit(0)

write(MANIFESTS)
summary = RB.run_batch(MANIFESTS, OUT, file_root=HERE, run_date="2026-08-07")
if summary["status"] == "MANIFEST_REJECTED":
    import pandas as pd
    print("manifests rejected: %s" % summary["detail"])
    print(pd.read_csv(os.path.join(OUT, "manifest_problems.csv")).to_string()[:4000])
    raise SystemExit(2)

import pandas as pd                                                # noqa: E402
run = pd.read_csv(os.path.join(OUT, "run_manifest.csv"))
raw = pd.read_csv(os.path.join(OUT, "figure_values_raw.csv"))
accepted = pd.read_csv(os.path.join(OUT, "figure_values_accepted.csv"))
by_unit = {u["Unit_ID"]: u for u in UNITS}

print("publication 397 - all %d panels of all 5 figures, one run" % len(PANELS))
print("  panels %d | cells declared %d | read %d | ACCEPTED %d"
      % (summary["panels"], int(run["Cells_Declared"].sum()), len(raw),
         len(accepted)))
print()
for state, n in sorted(run["Run_State"].value_counts().to_dict().items()):
    print("  %-24s %2d panels" % (state, n))
print()
print("  %-16s %-22s %s" % ("PANEL", "STATE", "READ/DECL"))
for _, r in run.iterrows():
    print("  %-16s %-22s %d/%d" % (r["Panel_ID"], r["Run_State"],
                                   r["Cells_Read"], r["Cells_Declared"]))
print()
if len(raw):
    print("  %d values read, all %s" % (len(raw),
                                        "/".join(sorted(set(raw["Value_Status"])))))
    for _, r in raw.iterrows():
        arm, sess = [p.split("=")[1] for p in sorted(r["Cell_Key"].split(";"))]
        u = by_unit[r["Unit_ID"]]
        print("    %-28s %-6s %-10s %-5s %9.2f  %7.2f"
              % (u["Outcome_Variable"], u["Panel"], arm, sess, r["Mean"],
                 r["Dispersion_Value"]))
print()
print("  outputs in %s" % OUT)
raise SystemExit(0)
