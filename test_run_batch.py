"""End-to-end gate for the declarative execution layer.

    python3 test_run_batch.py     # exit 0 = all scenarios pass

A synthetic figure with four panels of three different mark types is driven
entirely from CSV manifests through `run_batch` to a gate-clean values file.
Nothing in this module names a publication: the manifests are the only thing
that says what a mark means, which is the whole point of the layer.

Three classes of scenario, in order:

1. **The manifests are checked before a raster is opened.** Every rejection is
   built by mutating a manifest that otherwise runs clean, so a check that has
   quietly stopped firing shows up as a scenario that no longer fails.
2. **The run produces the declared cells and nothing else.** Identity comes from
   the manifest; an unreadable mark leaves a hole and a queue row.
3. **Every failure state is reachable**, and a second run over the same inputs
   is byte-identical.
"""
import csv
import json
import os
import shutil
import sys
import tempfile

import pandas as pd
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_manifests as BM        # noqa: E402
import grid_engine as GE            # noqa: E402
import mark_readers as MR           # noqa: E402
import run_batch as RB              # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_batch_")
IMAGES = os.path.join(ROOT, "images")
os.makedirs(IMAGES, exist_ok=True)

BLUE, RED = (45, 80, 220), (215, 45, 45)
XS = [140, 240, 340, 440]
POSITIONS = ["T0", "T1", "T2", "T3"]
LINE_TRUTH = {"S_BLUE": [55.0, 62.0, 68.0, 74.0], "S_RED": [34.0, 39.0, 45.0, 51.0]}
LINE_SD = 5.0


# --------------------------------------------------------------------------
# rasters
# --------------------------------------------------------------------------

def draw_line_panel(path):
    im = Image.new("RGB", (600, 480), "white")
    d = ImageDraw.Draw(im)
    cal = MR.AxisCalibration.from_points([(0, 420), (100, 60)])
    sd_px = abs(cal.value_to_pixel(LINE_SD) - cal.value_to_pixel(0))
    for name, values in LINE_TRUTH.items():
        colour = BLUE if name == "S_BLUE" else RED
        pts = [(x, cal.value_to_pixel(v)) for x, v in zip(XS, values)]
        d.line(pts, fill=colour, width=3)
        for x, y in pts:
            d.line((x, y - sd_px, x, y + sd_px), fill=colour, width=2)
            d.line((x - 8, y - sd_px, x + 8, y - sd_px), fill=colour, width=2)
            d.line((x - 8, y + sd_px, x + 8, y + sd_px), fill=colour, width=2)
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=colour)
    im.save(path)
    return cal


def draw_flat_line_panel(path):
    """Both series present, neither with a whisker - no weight, not no series."""
    im = Image.new("RGB", (600, 480), "white")
    d = ImageDraw.Draw(im)
    cal = MR.AxisCalibration.from_points([(0, 420), (100, 60)])
    for colour, values in ((BLUE, (50.0, 52.0, 54.0, 56.0)),
                           (RED, (30.0, 32.0, 34.0, 36.0))):
        pts = [(x, cal.value_to_pixel(v)) for x, v in zip(XS, values)]
        d.line(pts, fill=colour, width=3)
        for x, y in pts:
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=colour)
    im.save(path)
    return cal


SCATTER_XY = [(0.8, 3.0), (1.6, 4.2), (2.7, 7.1), (3.3, 6.8), (4.4, 9.6),
              (5.2, 11.8), (6.4, 12.1), (7.5, 15.5), (8.1, 15.1), (9.3, 18.4)]


def draw_scatter_panel(path):
    im = Image.new("RGB", (800, 520), "white")
    d = ImageDraw.Draw(im)
    xcal = MR.AxisCalibration.from_points([(0, 80), (10, 720)])
    ycal = MR.AxisCalibration.from_points([(0, 450), (20, 50)])
    for x, y in SCATTER_XY:
        px, py = xcal.value_to_pixel(x), ycal.value_to_pixel(y)
        d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=BLUE)
    im.save(path)
    return xcal, ycal


def draw_blank_panel(path):
    Image.new("RGB", (600, 480), "white").save(path)


LINE_IMG = os.path.join(IMAGES, "line.png")
FLAT_IMG = os.path.join(IMAGES, "flat.png")
SCAT_IMG = os.path.join(IMAGES, "scatter.png")
BLANK_IMG = os.path.join(IMAGES, "blank.png")
LINE_CAL = draw_line_panel(LINE_IMG)
draw_flat_line_panel(FLAT_IMG)
SX_CAL, SY_CAL = draw_scatter_panel(SCAT_IMG)
draw_blank_panel(BLANK_IMG)


def ticks(cal, values):
    return ";".join("%g:%g" % (v, cal.value_to_pixel(v)) for v in values)


Y_TICKS = ticks(LINE_CAL, (0, 100))
SX_TICKS = ticks(SX_CAL, (0, 10))
SY_TICKS = ticks(SY_CAL, (0, 20))


# --------------------------------------------------------------------------
# manifests
# --------------------------------------------------------------------------

FIGURES = [dict(Figure_ID="F1", Publication_ID=1, Figure_Number="FIG1",
                Source_File="synthetic.pdf", Source_Page=1, Source_Image=LINE_IMG,
                Source_Caption_Verbatim="synthetic four-panel figure",
                Image_Resolution_Or_Hash="600x480 sha256:" + MR.sha256_of(LINE_IMG),
                WPD_Project_File="", Observed_Panel_Count=4,
                Worklist_Panel_Count=4, Unlisted_Panels="",
                Panel_Reconciliation_Status="MATCHED", Note="")]

GRIDS = ([dict(Grid_ID="G_TIME", Factor_Name="ARM", Factor_Level=lv,
               Level_Order=i, Note="") for i, lv in enumerate(("CONTROL", "TREATED"))]
         + [dict(Grid_ID="G_TIME", Factor_Name="TIMEPOINT", Factor_Level=lv,
                 Level_Order=i, Note="") for i, lv in enumerate(POSITIONS)]
         + [dict(Grid_ID="G_ONE", Factor_Name="ARM", Factor_Level="ALL",
                 Level_Order=0, Note="")])


def unit(uid, grid, statistic, **kw):
    base = dict(
        Unit_ID=uid, Figure_ID="F1", Grid_ID=grid, Panel=uid,
        Outcome_Variable="Heart rate", Outcome_Domain="CV", Unit="bpm",
        Statistic_Type=statistic, Display_Hint="UNSPECIFIED", Grid_Rule="FULL",
        Sparse_Justification="", Dispersion_Type="SD",
        Errorbar_Definition_Source="caption: mean +/- SD", N_Outcome=12,
        Value_Scale="RATIO", Extraction_Method="DIGITIZED",
        Bar_Top_Definition="NOT_A_BAR", Errorbar_Stem_Confirmed="TRUE",
        Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
        Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
        Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=500,
        Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=420,
        Axis_Calib_Y2_Value=100, Axis_Calib_Y2_Pixel=60,
        Extractor_1="run_batch", Extractor_2="", Independent_Verification_Status="",
        Discrepancy_Note="", Date="2026-08-06", Note="")
    base.update(kw)
    return base


UNITS = [
    unit("U_LINE", "G_TIME", "CONTINUOUS"),
    unit("U_SCAT", "G_ONE", "ASSOCIATION", Bar_Top_Definition="NOT_A_BAR",
         Errorbar_Stem_Confirmed="NOT_A_BAR", Dispersion_Type="",
         Errorbar_Definition_Source="NO_ERRORBAR"),
    unit("U_FLAT", "G_TIME", "CONTINUOUS"),
    unit("U_MANUAL", "G_TIME", "CONTINUOUS"),
]


def panel(pid, uid, mark, image, box, **kw):
    base = dict(Panel_ID=pid, Figure_ID="F1", Unit_ID=uid, Panel_Label=pid,
                Mark_Type=mark, Image_Path=image,
                Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
                Axis_X_Region="", Axis_Y_Region="",
                Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
                Axis_X_Ticks="", Axis_Y_Ticks=Y_TICKS, Baseline_Value="",
                Association_Type="", Config_ID="C_DEFAULT", Panel_Mode="AUTO",
                Note="")
    base.update(kw)
    return base


PANELS = [
    panel("P_LINE", "U_LINE", "LINE_COLOR", LINE_IMG, (100, 500, 40, 440)),
    panel("P_SCAT", "U_SCAT", "SCATTER", SCAT_IMG, (70, 730, 40, 460),
          Axis_X_Ticks=SX_TICKS, Axis_Y_Ticks=SY_TICKS,
          Association_Type="PEARSON_R", Config_ID="C_SCATTER"),
    panel("P_FLAT", "U_FLAT", "LINE_COLOR", FLAT_IMG, (100, 500, 40, 440)),
    panel("P_MANUAL", "U_MANUAL", "LINE_COLOR", BLANK_IMG, (100, 500, 40, 440),
          Panel_Mode="MANUAL"),
]


def series(pid, sid, level, **kw):
    base = dict(Panel_ID=pid, Series_ID=sid, Colour_Hex="", Colour_Tolerance="",
                Mask_Key="", Marker_Shape="CIRCLE", Marker_Fill="ANY",
                Line_Style="SOLID", Bar_Fill_Pattern="", Factor_Name="ARM",
                Factor_Level=level, Note="")
    base.update(kw)
    return base


SERIES = [
    series("P_LINE", "S_BLUE", "CONTROL", Colour_Hex="#2d50dc"),
    series("P_LINE", "S_RED", "TREATED", Colour_Hex="#d72d2d"),
    series("P_SCAT", "S_BLUE", "ALL", Colour_Hex="#2d50dc"),
    series("P_FLAT", "S_BLUE", "CONTROL", Colour_Hex="#2d50dc"),
    series("P_FLAT", "S_RED", "TREATED", Colour_Hex="#d72d2d"),
    series("P_MANUAL", "S_BLUE", "CONTROL", Colour_Hex="#2d50dc"),
    series("P_MANUAL", "S_RED", "TREATED", Colour_Hex="#d72d2d"),
]

POSITION_ROWS = [
    dict(Panel_ID=pid, Position_ID=q, X_Pixel=x, Slot_Index=i, Display_Order=i,
         Factor_Name="TIMEPOINT", Factor_Level=q, Timepoint_Label=q,
         Timepoint_Days=i * 7, Note="")
    for pid in ("P_LINE", "P_FLAT", "P_MANUAL")
    for i, (q, x) in enumerate(zip(POSITIONS, XS))
]

CONFIGS = [
    dict(Config_ID="C_DEFAULT", Option="x_window", Value="12", Note=""),
    dict(Config_ID="C_DEFAULT", Option="colour_tolerance", Value="70", Note=""),
    dict(Config_ID="C_SCATTER", Option="colour_tolerance", Value="70", Note=""),
    dict(Config_ID="C_SCATTER", Option="min_marker_area", Value="12", Note=""),
]


def write_manifests(directory, panels=PANELS, series_rows=SERIES,
                    positions=POSITION_ROWS, configs=CONFIGS, units=UNITS,
                    figures=FIGURES, grids=GRIDS):
    os.makedirs(directory, exist_ok=True)
    for name, rows, cols in (
            ("figure_manifest", figures, GE.fig_figure_columns()),
            ("grid_definitions", grids, GE.fig_grid_columns()),
            ("unit_manifest", units, GE.fig_unit_columns()),
            ("panel_manifest", panels, BM.panel_manifest_columns()),
            ("series_manifest", series_rows, BM.series_manifest_columns()),
            ("position_manifest", positions, BM.position_manifest_columns()),
            ("reader_config", configs, BM.reader_config_columns())):
        path = os.path.join(directory, "%s.csv" % name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
    return directory


def fr(rows, cols):
    return pd.DataFrame([{c: str(d.get(c, "")) for c in cols} for d in rows],
                        columns=cols)


def validate(panels=PANELS, series_rows=SERIES, positions=POSITION_ROWS,
             configs=CONFIGS, units=UNITS):
    p = BM.validate_batch_manifests(
        fr(panels, BM.panel_manifest_columns()),
        fr(series_rows, BM.series_manifest_columns()),
        fr(positions, BM.position_manifest_columns()),
        fr(configs, BM.reader_config_columns()),
        units=fr(units, GE.fig_unit_columns()), file_root=ROOT)
    return sorted(set(p["check"])) if len(p) else []


def edited(rows, match, **changes):
    """Copy a manifest with one row changed, so a scenario states its own delta."""
    out = []
    for r in rows:
        if all(str(r.get(k, "")) == str(v) for k, v in match.items()):
            r = dict(r, **changes)
        out.append(r)
    return out


# --------------------------------------------------------------------------
print("the manifests are checked before any raster is opened")
check("the reference batch validates clean", validate() == [], "%s" % validate())

for _name, _kw, _want in (
        ("a panel box that does not fit its image",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Panel_X1=9000)),
         "PANEL_BOX_OUTSIDE_IMAGE"),
        ("an inverted panel box",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Panel_X1=50)),
         "BAD_PANEL_BOX"),
        ("an image that is not on disk",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                            Image_Path="/nope/missing.png")),
         "SOURCE_FILE_NOT_FOUND"),
        ("a mark type outside the vocabulary",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="SANKEY")),
         "BAD_MARK_TYPE"),
        ("a Config_ID with no options behind it",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Config_ID="C_GHOST")),
         "CONFIG_NOT_FOUND"),
        ("one tick where two are needed",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Axis_Y_Ticks="0:420")),
         "BAD_AXIS_CALIBRATION"),
        ("no y calibration at all",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Axis_Y_Ticks="")),
         "MISSING_AXIS_CALIBRATION"),
        ("ticks that sit outside the panel they calibrate",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                            Axis_Y_Ticks="0:4000;100:4200")),
         "CALIBRATION_OUTSIDE_PANEL"),
        ("a scatter that does not say which association it yields",
         dict(panels=edited(PANELS, {"Panel_ID": "P_SCAT"}, Association_Type="")),
         "MISSING_ASSOCIATION_TYPE"),
        ("an association type on a line panel",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                            Association_Type="PEARSON_R")),
         "ASSOCIATION_TYPE_NOT_APPLICABLE"),
        ("a bar reader pointed at an association unit",
         dict(panels=edited(PANELS, {"Panel_ID": "P_SCAT"}, Mark_Type="BAR_COLOR")),
         "MARK_TYPE_CONTRADICTS_STATISTIC"),
        ("a panel naming a unit that does not exist",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Unit_ID="U_GHOST")),
         "UNIT_NOT_FOUND"),
        ("a series with no factor level",
         dict(series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                                 Factor_Level="")),
         "MISSING_SERIES_IDENTITY"),
        ("a colour series with no colour",
         dict(series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                                 Colour_Hex="")),
         "MISSING_SERIES_DISCRIMINANT"),
        ("a malformed colour",
         dict(series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                                 Colour_Hex="#zzz")),
         "BAD_SERIES_COLOUR"),
        ("two series told apart by nothing",
         dict(series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                                 Colour_Hex="#2d50dc")),
         "SERIES_NOT_SEPARABLE"),
        ("a marker shape outside the vocabulary",
         dict(series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                                 Marker_Shape="BLOB")),
         "BAD_SERIES_MARKER_SHAPE"),
        ("the same factor on both the series and the position axis",
         dict(positions=edited(POSITION_ROWS, {"Panel_ID": "P_LINE"},
                               Factor_Name="ARM")),
         "FACTOR_ON_BOTH_AXES"),
        ("a position outside the panel box",
         dict(positions=edited(POSITION_ROWS, {"Panel_ID": "P_LINE",
                                               "Position_ID": "T0"}, X_Pixel=5)),
         "POSITION_OUTSIDE_PANEL"),
        ("a position with neither pixel nor slot",
         dict(positions=edited(POSITION_ROWS, {"Panel_ID": "P_LINE",
                                               "Position_ID": "T0"},
                               X_Pixel="", Slot_Index="")),
         "MISSING_POSITION_GEOMETRY"),
        ("declared positions on a scatter",
         dict(positions=POSITION_ROWS + [dict(Panel_ID="P_SCAT", Position_ID="T0",
                                              X_Pixel=200, Slot_Index=0,
                                              Display_Order=0, Factor_Name="TIMEPOINT",
                                              Factor_Level="T0", Timepoint_Label="T0",
                                              Timepoint_Days=0, Note="")]),
         "POSITION_NOT_APPLICABLE"),
        ("a misspelled reader option",
         dict(configs=CONFIGS + [dict(Config_ID="C_DEFAULT", Option="treshold",
                                      Value="150", Note="")]),
         "UNKNOWN_READER_OPTION"),
        ("an option that does not apply to this reader",
         dict(configs=CONFIGS + [dict(Config_ID="C_DEFAULT", Option="stem_required",
                                      Value="FALSE", Note="")]),
         "OPTION_WRONG_FOR_MARK_TYPE"),
        ("an option value of the wrong type",
         dict(configs=edited(CONFIGS, {"Config_ID": "C_DEFAULT",
                                       "Option": "x_window"}, Value="wide")),
         "BAD_READER_OPTION_VALUE"),
        ("the same option set twice in one config",
         dict(configs=CONFIGS + [dict(Config_ID="C_DEFAULT", Option="x_window",
                                      Value="20", Note="")]),
         "DUPLICATE_READER_OPTION"),
):
    _got = validate(**_kw)
    check(_name + " is rejected", _want in _got, "got %s" % _got)

check("a panel with no series declared is rejected",
      "PANEL_HAS_NO_SERIES" in validate(
          series_rows=[r for r in SERIES if r["Panel_ID"] != "P_FLAT"]))
check("a positional panel with no positions is rejected",
      "PANEL_HAS_NO_POSITIONS" in validate(
          positions=[r for r in POSITION_ROWS if r["Panel_ID"] != "P_LINE"]))
check("a duplicate Panel_ID is rejected",
      "DUPLICATE_PANEL_ID" in validate(panels=PANELS + [PANELS[0]]))
check("a series pointing at no panel is rejected",
      "PANEL_NOT_FOUND" in validate(
          series_rows=SERIES + [series("P_GHOST", "S_X", "CONTROL",
                                       Colour_Hex="#2d50dc")]))
check("a manifest missing a column is rejected as a schema error",
      "SCHEMA_INCOMPLETE" in (lambda p: sorted(set(p["check"])) if len(p) else [])(
          BM.validate_batch_manifests(
              fr(PANELS, [c for c in BM.panel_manifest_columns() if c != "Mark_Type"]),
              fr(SERIES, BM.series_manifest_columns()),
              fr(POSITION_ROWS, BM.position_manifest_columns()),
              fr(CONFIGS, BM.reader_config_columns()), file_root=ROOT)))


# --------------------------------------------------------------------------
print("a run turns declared panels into declared cells")
MDIR = write_manifests(os.path.join(ROOT, "manifests"))
ODIR = os.path.join(ROOT, "out")
summary = RB.run_batch(MDIR, ODIR, file_root=ROOT, run_date="2026-08-06")
check("the batch ran", summary["status"] == "RAN", "%s" % summary)

values = pd.read_csv(os.path.join(ODIR, "figure_values.csv"), dtype=object).fillna("")
run = pd.read_csv(os.path.join(ODIR, "run_manifest.csv"), dtype=object).fillna("")
queue = pd.read_csv(os.path.join(ODIR, "manual_queue.csv"), dtype=object).fillna("")
qc = pd.read_csv(os.path.join(ODIR, "qc_problems.csv"), dtype=object).fillna("")
states = dict(zip(run["Panel_ID"], run["Run_State"]))

check("the line panel produced its eight declared cells",
      len(values[values["Unit_ID"] == "U_LINE"]) == 8,
      "%d" % len(values[values["Unit_ID"] == "U_LINE"]))
check("cell keys come from the manifest, not from the reader's labels",
      set(values[values["Unit_ID"] == "U_LINE"]["Cell_Key"]) ==
      {GE.fig_cell_key({"ARM": a, "TIMEPOINT": t})
       for a in ("CONTROL", "TREATED") for t in POSITIONS},
      "%s" % sorted(set(values[values["Unit_ID"] == "U_LINE"]["Cell_Key"]))[:3])
_means = {r["Cell_Key"]: float(r["Mean"])
          for _, r in values[values["Unit_ID"] == "U_LINE"].iterrows()}
_err = max(abs(_means[GE.fig_cell_key({"ARM": arm, "TIMEPOINT": t})] - v)
           for arm, name in (("CONTROL", "S_BLUE"), ("TREATED", "S_RED"))
           for t, v in zip(POSITIONS, LINE_TRUTH[name]))
check("the values are the reader's, recovered within 1 unit", _err < 1.0,
      "max %.3f" % _err)
check("the scatter panel produced one association cell",
      len(values[values["Unit_ID"] == "U_SCAT"]) == 1,
      "%d" % len(values[values["Unit_ID"] == "U_SCAT"]))
_scat = values[values["Unit_ID"] == "U_SCAT"].iloc[0]
check("the association carries its point file and its provenance",
      bool(_scat["Point_Data_Reference"]) and bool(_scat["P_Value_Extraction_Method"])
      and bool(_scat["Ties_Present"]),
      "%r" % dict(_scat))
check("the point file the run wrote is on disk and re-derivable",
      os.path.exists(_scat["Point_Data_Reference"])
      and MR.read_point_data(_scat["Point_Data_Reference"])["Unit_ID"] == "U_SCAT")
check("the point file names the cell it backs",
      MR.read_point_data(_scat["Point_Data_Reference"])["Cell_Key"]
      == _scat["Cell_Key"])
# The two queued panels produced nothing, and the gate says so - that is the
# fail-closed property working, not a defect. What must be true is that the
# complaints are confined to those units and never touch the ones that ran.
_blamed = set()
for _, _p in qc.iterrows():
    _w = str(_p["where"])
    if _w.startswith("unit:"):
        _blamed.add(_w.split(":", 1)[1])
    elif _w.startswith("values:"):
        _blamed.add(values.iloc[int(_w.split(":", 1)[1]) - 2]["Unit_ID"])
check("the units that ran are clean through the gate",
      not (_blamed & {"U_LINE", "U_SCAT"}), "%s" % sorted(_blamed))
check("the gate names the holes the queued panels left",
      _blamed == {"U_FLAT", "U_MANUAL"}, "%s" % sorted(_blamed))
check("and it names them as missing cells, not as bad values",
      set(qc["check"]) <= {"FACTOR_LEVEL_MISSING", "FACTORIAL_CELL_MISSING"},
      "%s" % sorted(set(qc["check"])))

print("every panel lands on exactly one state, and says why")
check("the readable line panel is AUTO_PASS", states.get("P_LINE") == "AUTO_PASS",
      "%s" % states)
check("the scatter panel is AUTO_PASS", states.get("P_SCAT") == "AUTO_PASS",
      "%s" % states)
check("markers with no whiskers are NO_VARIANCE",
      states.get("P_FLAT") == "NO_VARIANCE", "%s" % states)
check("a panel declared MANUAL is never read",
      states.get("P_MANUAL") == "MANUAL_POINT_READ", "%s" % states)
check("every non-passing panel is in the manual queue",
      set(queue["Panel_ID"]) == {"P_FLAT", "P_MANUAL"},
      "%s" % sorted(set(queue["Panel_ID"])))
check("a queue row carries the image and box a human needs to open",
      all(q["Image_Path"] and q["Panel_Box"] for _, q in queue.iterrows()
          if q["Run_State"] != "MANUAL_POINT_READ" or q["Panel_ID"] == "P_FLAT"))
check("no state outside the declared vocabulary",
      set(run["Run_State"]) <= set(BM.RUN_STATES),
      "%s" % (set(run["Run_State"]) - set(BM.RUN_STATES)))
check("a panel that failed produced no values",
      not len(values[values["Unit_ID"].isin(["U_FLAT", "U_MANUAL"])]),
      "%d rows" % len(values[values["Unit_ID"].isin(["U_FLAT", "U_MANUAL"])]))

print("the run records what would have to match for it to be reproducible")
stamp = json.load(open(os.path.join(ODIR, "run_stamp.json")))
check("the stamp carries the reader version and the config hash",
      stamp["Reader_Version"] == MR.READER_VERSION and len(stamp["Config_SHA256"]) == 64)
check("the stamp hashes every input manifest",
      set(stamp["Manifest_SHA256"]) == set(RB.MANIFEST_FILES),
      "%s" % sorted(stamp["Manifest_SHA256"]))
check("each run row carries the image hash it read",
      all(len(h) == 64 for h in run["Image_SHA256"] if h), "%s" % list(run["Image_SHA256"]))

ODIR2 = os.path.join(ROOT, "out2")
RB.run_batch(MDIR, ODIR2, file_root=ROOT, run_date="2026-08-06")
_same = []
for name in ("figure_values.csv", "run_manifest.csv", "manual_queue.csv",
             "qc_problems.csv"):
    # The output directory is embedded in the paths a run writes, so compare the
    # runs with their own root removed. Everything else must match exactly.
    _a = open(os.path.join(ODIR, name)).read().replace(ODIR, "<OUT>")
    _b = open(os.path.join(ODIR2, name)).read().replace(ODIR2, "<OUT>")
    _same.append((name, _a == _b))
check("a second run over the same inputs is identical but for its own path",
      all(ok for _, ok in _same), "%s" % [n for n, ok in _same if not ok])
_p1 = MR.read_point_data(_scat["Point_Data_Reference"])
_p2 = MR.read_point_data(_scat["Point_Data_Reference"].replace(ODIR, ODIR2))
check("and the point clouds it wrote are identical pixel for pixel",
      _p1["points"] == _p2["points"])
_changed = json.load(open(os.path.join(ODIR2, "run_stamp.json")))
check("and its stamp agrees", _changed == stamp)

print("a changed input is visible in the stamp, not silent")
MDIR3 = write_manifests(os.path.join(ROOT, "manifests3"),
                        configs=CONFIGS + [dict(Config_ID="C_DEFAULT",
                                                Option="x_window", Value="14",
                                                Note="")])
ODIR3 = os.path.join(ROOT, "out3")
_s3 = RB.run_batch(MDIR3, ODIR3, file_root=ROOT, run_date="2026-08-06")
check("a duplicated option is caught at validation, before any reading",
      _s3["status"] == "MANIFEST_REJECTED"
      and "DUPLICATE_READER_OPTION" in _s3["detail"], "%s" % _s3)
check("a rejected batch writes its reasons and no values",
      os.path.exists(os.path.join(ODIR3, "manifest_problems.csv"))
      and not os.path.exists(os.path.join(ODIR3, "figure_values.csv")))

MDIR4 = write_manifests(os.path.join(ROOT, "manifests4"),
                        configs=[dict(c, Value=("30" if c["Option"] == "x_window"
                                                else c["Value"])) for c in CONFIGS])
ODIR4 = os.path.join(ROOT, "out4")
RB.run_batch(MDIR4, ODIR4, file_root=ROOT, run_date="2026-08-06")
_st4 = json.load(open(os.path.join(ODIR4, "run_stamp.json")))
check("changing an option changes the config hash",
      _st4["Config_SHA256"] != stamp["Config_SHA256"])

print("the failure states the reader can reach are reachable")
# With check_files off - the deliberate choice for validating a manifest set
# away from its rasters - a missing image survives validation and fails in the
# reader. That is the state the runner must reach rather than crash on.
_bad_geom = write_manifests(
    os.path.join(ROOT, "m_geom"),
    panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                  Image_Path=os.path.join(IMAGES, "vanished.png")))
_o = os.path.join(ROOT, "o_geom")
RB.run_batch(_bad_geom, _o, file_root=ROOT, run_date="2026-08-06",
             check_files=False)
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("a calibration the reader cannot use is PANEL_GEOMETRY_UNRESOLVED",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "PANEL_GEOMETRY_UNRESOLVED",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))

_one_colour = write_manifests(
    os.path.join(ROOT, "m_series"),
    series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                       Colour_Hex="#0a7a10"))
_o = os.path.join(ROOT, "o_series")
RB.run_batch(_one_colour, _o, file_root=ROOT, run_date="2026-08-06")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("a series the reader cannot find is SERIES_IDENTITY_UNRESOLVED, not a hole",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "SERIES_IDENTITY_UNRESOLVED",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))
_v = pd.read_csv(os.path.join(_o, "figure_values.csv"), dtype=object).fillna("")
check("and it contributes no half-panel of values",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))

# Switching a panel to BAR_MONO invalidates a config written for a colour line
# reader, and the validator says so first - so this scenario gives the panel a
# config that actually fits it. That the mismatch was caught is itself the
# behaviour the OPTION_WRONG_FOR_MARK_TYPE scenario above asserts.
_mono_series = [
    dict(r, Colour_Hex="",
         Bar_Fill_Pattern=("SOLID" if r["Series_ID"] == "S_BLUE" else "HATCHED"))
    if r["Panel_ID"] == "P_LINE" else r for r in SERIES]
_mono = write_manifests(
    os.path.join(ROOT, "m_mono"),
    panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="BAR_MONO",
                  Config_ID="C_BARMONO"),
    series_rows=_mono_series,
    configs=CONFIGS + [dict(Config_ID="C_BARMONO", Option="threshold",
                            Value="150", Note="")])
_o = os.path.join(ROOT, "o_mono")
RB.run_batch(_mono, _o, file_root=ROOT, run_date="2026-08-06")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("a bar reader pointed at a line panel finds nothing and queues it",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "MANUAL_POINT_READ",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))
_v = pd.read_csv(os.path.join(_o, "figure_values.csv"), dtype=object).fillna("")
check("and it invents no bars from the line markers",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))

_wrong_grid = write_manifests(
    os.path.join(ROOT, "m_qc"),
    grids=[g for g in GRIDS if not (g["Grid_ID"] == "G_TIME"
                                    and g["Factor_Level"] == "T3")])
_o = os.path.join(ROOT, "o_qc")
_sq = RB.run_batch(_wrong_grid, _o, file_root=ROOT, run_date="2026-08-06")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("values the gate rejects flip the panel to QC_FAILED",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "QC_FAILED",
      "%s / qc=%d" % (dict(zip(_r["Panel_ID"], _r["Run_State"])), _sq["qc_problems"]))
_q = pd.read_csv(os.path.join(_o, "manual_queue.csv"), dtype=object).fillna("")
check("and the run manifest and the queue tell the same story",
      "P_LINE" in set(_q["Panel_ID"]), "%s" % sorted(set(_q["Panel_ID"])))

_sparse_img = os.path.join(IMAGES, "sparse.png")
_si = Image.new("RGB", (800, 520), "white")
_sd = ImageDraw.Draw(_si)
for _x, _y in SCATTER_XY[:2]:
    _px, _py = SX_CAL.value_to_pixel(_x), SY_CAL.value_to_pixel(_y)
    _sd.ellipse((_px - 5, _py - 5, _px + 5, _py + 5), fill=BLUE)
_si.save(_sparse_img)
_sparse = write_manifests(
    os.path.join(ROOT, "m_sparse"),
    panels=edited(PANELS, {"Panel_ID": "P_SCAT"}, Image_Path=_sparse_img))
_o = os.path.join(ROOT, "o_sparse")
RB.run_batch(_sparse, _o, file_root=ROOT, run_date="2026-08-06")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("a cloud too sparse to summarize is NOT_CONVERTIBLE, not a shaky r",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_SCAT"] == "NOT_CONVERTIBLE",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))

print("an automated extraction is re-openable by hand")
_proj = dict(zip(run["Panel_ID"], run["WPD_Project_File"]))
check("every passing panel saved a WPD project",
      all(_proj[p] and os.path.exists(_proj[p]) for p in ("P_LINE", "P_SCAT")),
      "%s" % _proj)
import tarfile  # noqa: E402
with tarfile.open(_proj["P_LINE"]) as _tf:
    _names = _tf.getnames()
    _wpd = json.loads(_tf.extractfile(
        [n for n in _names if n.endswith("wpd.json")][0]).read())
check("the project is a real tar carrying the raster it was read from",
      any(n.endswith(".png") for n in _names), "%s" % _names)
check("it carries one dataset per declared series",
      sorted(d["name"] for d in _wpd["datasetColl"]) == ["S_BLUE", "S_RED"],
      "%s" % [d["name"] for d in _wpd["datasetColl"]])
check("and every mark the reader placed, so a reviewer can see where it looked",
      sum(len(d["data"]) for d in _wpd["datasetColl"]) == 8,
      "%d" % sum(len(d["data"]) for d in _wpd["datasetColl"]))
check("the run filled the figure manifest's WPD_Project_File itself",
      "WPD_Project_File" in pd.read_csv(
          os.path.join(ODIR, "figure_manifest.csv"), dtype=object).fillna("").columns
      and bool(pd.read_csv(os.path.join(ODIR, "figure_manifest.csv"),
                           dtype=object).fillna("").iloc[0]["WPD_Project_File"]))

print("templates are generated from the column functions, never typed")
_tdir = os.path.join(ROOT, "templates")
for _p in RB.emit_templates(_tdir):
    _name = os.path.basename(_p).replace("_TEMPLATE.csv", "")
    _fn = dict(BM.BATCH_TEMPLATES)[_name]
    check("%s template matches its column function" % _name,
          next(csv.reader(open(_p))) == _fn())

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
