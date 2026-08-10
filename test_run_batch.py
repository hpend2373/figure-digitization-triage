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
import types
import tarfile
import tempfile

import pandas as pd
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import batch_manifests as BM        # noqa: E402
import kernel as K                 # noqa: E402
import grid_engine as GE            # noqa: E402
import mark_readers as MR           # noqa: E402
import run_batch as RB              # noqa: E402
import bar_reader as BR             # noqa: E402
import datetime                     # noqa: E402
import finalize_batch as FIN        # noqa: E402

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


# Four ticks, not two. A calibration fitted on four is a different, checkable
# object from one fitted on two - and the WPD project used to save only the
# first two, so the artifact that exists for re-deriving a value could not
# reproduce the fit behind it.
Y_TICKS = ticks(LINE_CAL, (0, 25, 50, 100))
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

REVIEWERS = [dict(
    Reviewer_ID="RV_T1", Reviewer_Name="Test Fixture",
    Reviewer_Record_Type="HUMAN", Contact_Type="EMAIL",
    Reviewer_Contact="fixture@example.org", Registered_By="Test Fixture",
    Registration_Date="2026-08-01", Human_Attestation="HUMAN_CONFIRMED",
    Note="synthetic regression reviewer")]

SOURCE_DOCUMENTS = [dict(
    Source_Document_ID="SD1", Publication_ID=1, Document_Role="MAIN_ARTICLE",
    Source_File="synthetic.pdf", Article_Page_Range="1-1",
    Observed_Figure_Count=4, Inventory_Status="VISUALLY_VERIFIED",
    Figure_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="four synthetic source figures")]

# One source figure per raster. The fixture used to put all four panels under a
# single Source_Figure_ID whose Source_Image was only one of the four files -
# a physical figure that is four different files at once. Nothing noticed until
# the hash chain was enforced, which is a fair result for the check: the first
# thing it caught was an inventory that could not describe anything real.
_SOURCE_RASTERS = (("SF1", "P_LINE", LINE_IMG), ("SF2", "P_SCAT", SCAT_IMG),
                   ("SF3", "P_FLAT", FLAT_IMG), ("SF4", "P_MANUAL", BLANK_IMG))
_FIGURE_OF_PANEL = {pid: sfid for sfid, pid, _ in _SOURCE_RASTERS}

SOURCE_FIGURES = [dict(
    Source_Figure_ID=sfid, Source_Document_ID="SD1",
    Publication_ID=1, Figure_Number="FIG%s" % sfid[-1],
    Source_File="synthetic.pdf", Source_Page=1, Source_Image=img,
    Source_Image_SHA256=MR.sha256_of(img),
    Observed_Panel_Count=1, Inventory_Status="VISUALLY_VERIFIED",
    Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="one visible axes region")
    for sfid, _pid, img in _SOURCE_RASTERS]

SOURCE_PANELS = [dict(
    Source_Panel_ID=pid, Source_Figure_ID=_FIGURE_OF_PANEL[pid], Panel_Label=pid,
    Outcome_Label=("Heart rate" if pid != "P_SCAT" else "Heart-rate association"),
    Target_Status="TARGET",
    Panel_Disposition=("MANUAL_DIGITIZE" if pid == "P_MANUAL" else
                       "ASSOCIATION_EXTRACT" if pid == "P_SCAT" else
                       "AUTO_DIGITIZE"),
    Disposition_Reason="synthetic regression fixture", Note="")
    for pid in ("P_LINE", "P_SCAT", "P_FLAT", "P_MANUAL")]

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
    # The declared n is the number of points the figure actually carries. It
    # used to be the shared default of 12 against a ten-point cloud, and the run
    # recorded N_Pairs=10 beside N_Outcome=12 without a word.
    unit("U_SCAT", "G_ONE", "ASSOCIATION", Bar_Top_Definition="NOT_A_BAR",
         Errorbar_Stem_Confirmed="NOT_A_BAR", Dispersion_Type="",
         N_Outcome=len(SCATTER_XY),
         Errorbar_Definition_Source="NO_ERRORBAR"),
    unit("U_FLAT", "G_TIME", "CONTINUOUS"),
    unit("U_MANUAL", "G_TIME", "CONTINUOUS"),
]


def panel(pid, uid, mark, image, box, **kw):
    base = dict(Panel_ID=pid, Source_Panel_ID=pid, Figure_ID="F1", Unit_ID=uid, Panel_Label=pid,
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
                    figures=FIGURES, grids=GRIDS,
                    source_documents=SOURCE_DOCUMENTS,
                    source_figures=SOURCE_FIGURES, source_panels=SOURCE_PANELS,
                    reviewers=REVIEWERS):
    os.makedirs(directory, exist_ok=True)
    for name, rows, cols in (
            ("reviewer_registry", reviewers, BM.reviewer_registry_columns()),
            ("source_document_manifest", source_documents,
             BM.source_document_manifest_columns()),
            ("source_figure_manifest", source_figures, BM.source_figure_manifest_columns()),
            ("source_panel_inventory", source_panels, BM.source_panel_inventory_columns()),
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
             configs=CONFIGS, units=UNITS, source_figures=SOURCE_FIGURES,
             source_panels=SOURCE_PANELS, source_documents=SOURCE_DOCUMENTS,
             reviewers=REVIEWERS):
    p = BM.validate_batch_manifests(
        fr(panels, BM.panel_manifest_columns()),
        fr(series_rows, BM.series_manifest_columns()),
        fr(positions, BM.position_manifest_columns()),
        fr(configs, BM.reader_config_columns()),
        units=fr(units, GE.fig_unit_columns()),
        source_documents=fr(source_documents, BM.source_document_manifest_columns()),
        source_figures=fr(source_figures, BM.source_figure_manifest_columns()),
        source_panels=fr(source_panels, BM.source_panel_inventory_columns()),
        reviewers=fr(reviewers, BM.reviewer_registry_columns()),
        file_root=ROOT)
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

check("an entire physical figure omitted from a document is rejected",
      "SOURCE_FIGURE_COVERAGE_INCOMPLETE" in validate(
          source_documents=[dict(SOURCE_DOCUMENTS[0], Observed_Figure_Count=2)]))

check("a physical figure with only part of its visible panels inventoried is rejected",
      "SOURCE_PANEL_COVERAGE_INCOMPLETE" in validate(
          source_panels=SOURCE_PANELS[:2]))
_virtual14 = [dict(SOURCE_PANELS[i % len(SOURCE_PANELS)],
                   Source_Panel_ID="V%02d" % i, Panel_Label="P%02d" % i,
                   Panel_Disposition="NO_READER_AVAILABLE") for i in range(14)]
check("fourteen virtual declarations cannot satisfy a 36-panel physical figure",
      "SOURCE_PANEL_COVERAGE_INCOMPLETE" in validate(
          source_figures=[dict(SOURCE_FIGURES[0], Observed_Panel_Count=36)],
          source_panels=_virtual14),
      "%s" % validate(
          source_figures=[dict(SOURCE_FIGURES[0], Observed_Panel_Count=36)],
          source_panels=_virtual14))
# The inventory's correctness reduces to one human act: somebody opened the
# figure and counted. No software can check the count, so the attestation is
# the only thing standing behind it - and requiring it to be non-blank let
# Inspector=TBD and Inspection_Date=soon straight through, which is the hedged
# non-answer defect in the field that can least afford it.
for _fld, _val, _want in (
        ("Reviewer_ID", "TBD", "UNRESOLVED_INVENTORY_ATTESTATION"),
        ("Reviewer_ID", "TODO", "UNRESOLVED_INVENTORY_ATTESTATION"),
        ("Reviewer_ID", "?", "REVIEWER_NOT_REGISTERED"),
        ("Reviewer_ID", "x", "REVIEWER_NOT_REGISTERED"),
        ("Inspection_Date", "TBD", "UNRESOLVED_INVENTORY_ATTESTATION"),
        ("Inspection_Date", "soon", "BAD_INSPECTION_DATE"),
        ("Inspection_Date", "later", "BAD_INSPECTION_DATE"),
        ("Inspection_Date", "2026-13-45", "BAD_INSPECTION_DATE"),
        ("Inspection_Date", "07/08/2026", "BAD_INSPECTION_DATE"),
        ("Inspection_Date", "2099-01-01", "BAD_INSPECTION_DATE")):
    check("figure inventory attested with %s=%r is refused" % (_fld, _val),
          _want in validate(source_figures=edited(
              SOURCE_FIGURES, {"Source_Figure_ID": "SF1"}, **{_fld: _val})),
          "%s" % validate(source_figures=edited(
              SOURCE_FIGURES, {"Source_Figure_ID": "SF1"}, **{_fld: _val})))
    check("document inventory attested with %s=%r is refused" % (_fld, _val),
          _want in validate(source_documents=[dict(SOURCE_DOCUMENTS[0],
                                                   **{_fld: _val})]))
for _fld, _val in (("Reviewer_ID", "RV_T1"), ("Inspection_Date", "2026-08-06")):
    check("a real attestation %s=%r passes" % (_fld, _val),
          validate(source_figures=edited(SOURCE_FIGURES,
                                         {"Source_Figure_ID": "SF1"},
                                         **{_fld: _val})) == [],
          "%s" % validate(source_figures=edited(
              SOURCE_FIGURES, {"Source_Figure_ID": "SF1"}, **{_fld: _val})))

# --------------------------------------------------------------------------
# the reviewer registry
# --------------------------------------------------------------------------
# The attestation check used to read a free-text `Inspector` and test it with
# `re.sub(r"[^0-9A-Za-z]", "", who)`, which is a statement that reviewers are
# named in the Latin alphabet. It rejected the name of the person who actually
# did this inventory and accepted the name of the software that cannot do it.


def _reviewer(**changes):
    return edited(REVIEWERS, {"Reviewer_ID": "RV_T1"}, **changes)


for _name in ("김민엽", "李明", "홍길동", "Ólafur Þórsson", "О. Иванов",
              "Nguyễn Thị Hoa", "ＫＩＭ", "JS", "Claude Bernard"):
    check("a reviewer named %s can register" % _name,
          validate(reviewers=_reviewer(Reviewer_Name=_name)) == [],
          "%s" % validate(reviewers=_reviewer(Reviewer_Name=_name)))
for _name in ("AI", "BOT", "LLM", "Codex", "Claude", "GPT-4", "gpt4",
              "auto script", "automated agent"):
    check("a reviewer named %r is refused as non-human" % _name,
          "REVIEWER_NOT_HUMAN" in validate(reviewers=_reviewer(Reviewer_Name=_name)),
          "%s" % validate(reviewers=_reviewer(Reviewer_Name=_name)))
for _name in ("x", "", "12", "-"):
    check("a reviewer named %r is not a name" % _name,
          set(validate(reviewers=_reviewer(Reviewer_Name=_name)))
          & {"UNRESOLVED_REVIEWER_IDENTITY", "MISSING_REQUIRED"},
          "%s" % validate(reviewers=_reviewer(Reviewer_Name=_name)))
check("a reviewer registering under a placeholder is refused",
      "UNRESOLVED_REVIEWER_IDENTITY" in validate(reviewers=_reviewer(Reviewer_Name="TBD")))
check("a registrar named as software is refused",
      "REVIEWER_NOT_HUMAN" in validate(reviewers=_reviewer(Registered_By="Claude")))

# The registry is the only place a person is described, so an attestation that
# points nowhere is the whole defect coming back one level up.
check("an inventory naming an unregistered reviewer is refused",
      "REVIEWER_NOT_REGISTERED" in validate(source_figures=edited(
          SOURCE_FIGURES, {"Source_Figure_ID": "SF1"}, Reviewer_ID="RV_NOBODY")))
check("a document naming an unregistered reviewer is refused",
      "REVIEWER_NOT_REGISTERED" in validate(
          source_documents=[dict(SOURCE_DOCUMENTS[0], Reviewer_ID="RV_NOBODY")]))
check("an empty registry cannot back any inventory",
      "REVIEWER_NOT_REGISTERED" in validate(reviewers=[]))
check("two rows claiming one Reviewer_ID are refused",
      "DUPLICATE_REVIEWER_ID" in validate(
          reviewers=REVIEWERS + [dict(REVIEWERS[0], Reviewer_Name="Someone Else")]))

check("a reviewer declared AUTOMATED_AGENT cannot hold the attestation",
      "REVIEWER_NOT_HUMAN" in validate(
          reviewers=_reviewer(Human_Attestation="AUTOMATED_AGENT")))
check("an invented attestation value is refused",
      "BAD_HUMAN_ATTESTATION" in validate(
          reviewers=_reviewer(Human_Attestation="PROBABLY_HUMAN")))
for _ct, _contact, _want in (
        ("EMAIL", "not-an-address", "BAD_REVIEWER_CONTACT"),
        ("EMAIL", "someone@localhost", "BAD_REVIEWER_CONTACT"),
        ("ORCID", "0000-0002-1825-0097", None),
        ("ORCID", "0000-0002-1694-233X", None),
        ("ORCID", "0000-0002-1825-0098", "BAD_REVIEWER_CONTACT"),
        ("ORCID", "0000-0002-1825", "BAD_REVIEWER_CONTACT"),
        ("POSTCARD", "somewhere", "BAD_CONTACT_TYPE")):
    _got = validate(reviewers=_reviewer(Contact_Type=_ct, Reviewer_Contact=_contact))
    check("%s contact %r %s" % (_ct, _contact, "passes" if _want is None else "is refused"),
          (_got == []) if _want is None else (_want in _got), "%s" % _got)
check("a registration dated in the future is refused",
      "BAD_REGISTRATION_DATE" in validate(reviewers=_reviewer(Registration_Date="2099-01-01")))
check("a free-text registration date is refused",
      "BAD_REGISTRATION_DATE" in validate(reviewers=_reviewer(Registration_Date="last week")))

# A renamed column is the one schema change that can pass in silence: the old
# column is ignored, so a manifest that still records who looked reads as one
# where nobody did.
check("a manifest still carrying the old Inspector column is refused",
      "LEGACY_INSPECTOR_COLUMN" in (
          lambda p: sorted(set(p["check"])) if len(p) else [])(
          BM.validate_batch_manifests(
              fr(PANELS, BM.panel_manifest_columns()),
              fr(SERIES, BM.series_manifest_columns()),
              fr(POSITION_ROWS, BM.position_manifest_columns()),
              fr(CONFIGS, BM.reader_config_columns()),
              units=fr(UNITS, GE.fig_unit_columns()),
              source_documents=fr(
                  [dict(SOURCE_DOCUMENTS[0], Inspector="test fixture")],
                  BM.source_document_manifest_columns() + ["Inspector"]),
              source_figures=fr(SOURCE_FIGURES, BM.source_figure_manifest_columns()),
              source_panels=fr(SOURCE_PANELS, BM.source_panel_inventory_columns()),
              reviewers=fr(REVIEWERS, BM.reviewer_registry_columns()),
              file_root=ROOT)))
check("a registered reviewer who inspected nothing is not an error",
      validate(reviewers=REVIEWERS + [dict(
          Reviewer_ID="RV_T2", Reviewer_Name="Second Extractor",
          Reviewer_Record_Type="HUMAN", Contact_Type="ORCID", Reviewer_Contact="0000-0002-1825-0097",
          Registered_By="Test Fixture", Registration_Date="2026-08-01",
          Human_Attestation="HUMAN_CONFIRMED", Note="")]) == [],
      "%s" % validate(reviewers=REVIEWERS + [dict(
          Reviewer_ID="RV_T2", Reviewer_Name="Second Extractor",
          Reviewer_Record_Type="HUMAN", Contact_Type="ORCID", Reviewer_Contact="0000-0002-1825-0097",
          Registered_By="Test Fixture", Registration_Date="2026-08-01",
          Human_Attestation="HUMAN_CONFIRMED", Note="")]))

# The CLI docstring is the only place a user learns what the runner needs, and
# it silently fell one file behind `MANIFEST_FILES` the moment a manifest was
# added. Documentation that can drift is documentation that will.
_doc = RB.__doc__ or ""
_undocumented = sorted(n for n in RB.MANIFEST_FILES.values() if n not in _doc)
check("every mandatory manifest is named in the runner's usage text",
      _undocumented == [], "undocumented: %s" % _undocumented)
check("the usage text says how many there are",
      "eleven" in _doc and len(RB.MANIFEST_FILES) == 11,
      "%d manifests" % len(RB.MANIFEST_FILES))
# And the optional one, said to be optional. A file the runner reads and the
# usage text does not mention is a file nobody writes; one mentioned without the
# word OPTIONAL is eleven manifests turning into twelve mandatory ones in the
# reader's head.
_opt = sorted(n for n in RB.OPTIONAL_MANIFEST_FILES.values() if n not in _doc)
check("the optional manifest is documented too, and as optional",
      _opt == [] and "OPTIONAL" in _doc, "undocumented: %s" % _opt)

check("an unverified visual inventory blocks the run",
      "SOURCE_INVENTORY_NOT_VERIFIED" in validate(
          source_figures=edited(SOURCE_FIGURES, {"Source_Figure_ID": "SF1"},
                                Inventory_Status="PENDING")))
check("an unresolved source panel blocks the run",
      "SOURCE_PANEL_UNRESOLVED" in validate(
          source_panels=edited(SOURCE_PANELS, {"Source_Panel_ID": "P_FLAT"},
                               Target_Status="UNCERTAIN",
                               Panel_Disposition="UNRESOLVED")))
check("an auto-digitized source panel must link to a run panel",
      "SOURCE_PANEL_RUN_LINK_MISSING" in validate(
          panels=[r for r in PANELS if r["Panel_ID"] != "P_FLAT"]))
check("a run panel absent from the source inventory is rejected",
      "SOURCE_PANEL_NOT_IN_INVENTORY" in validate(
          panels=edited(PANELS, {"Panel_ID": "P_FLAT"},
                        Source_Panel_ID="P_NOT_INVENTORIED")))

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
        # slot_tolerance_px is a BAR_COLOR keyword; the monochrome bar reader
        # has no such parameter, so accepting it here bought a TypeError at run
        # time reported as a figure problem. (`n_slots` used to be the example.
        # It is gone: it existed so BAR_COLOR could rebuild its own x spacing
        # from the bars it happened to detect, which is inference.)
        ("slot_tolerance_px on a monochrome bar panel",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="BAR_MONO",
                            Config_ID="C_MONO"),
              series_rows=[dict(r, Colour_Hex="", Bar_Fill_Pattern=(
                  "SOLID" if r["Series_ID"] == "S_BLUE" else "HATCHED"))
                  if r["Panel_ID"] == "P_LINE" else r for r in SERIES],
              configs=CONFIGS + [dict(Config_ID="C_MONO",
                                      Option="slot_tolerance_px",
                                      Value="4", Note="")]),
         "OPTION_WRONG_FOR_MARK_TYPE"),
        # Ranges, not just types. Each of these parsed cleanly and then selected
        # nothing at all, which reads downstream as an unreadable figure.
        ("a negative grey threshold",
         dict(configs=CONFIGS + [dict(Config_ID="C_SCATTER", Option="threshold",
                                      Value="-1", Note="")]),
         "BAD_READER_OPTION_VALUE"),
        ("a grey threshold above 255",
         dict(configs=CONFIGS + [dict(Config_ID="C_SCATTER", Option="threshold",
                                      Value="300", Note="")]),
         "BAD_READER_OPTION_VALUE"),
        ("a zero-width matching window",
         dict(configs=edited(CONFIGS, {"Config_ID": "C_DEFAULT",
                                       "Option": "x_window"}, Value="0")),
         "BAD_READER_OPTION_VALUE"),
        ("a negative colour tolerance",
         dict(configs=edited(CONFIGS, {"Config_ID": "C_SCATTER",
                                       "Option": "colour_tolerance"}, Value="-5")),
         "BAD_READER_OPTION_VALUE"),
        ("a marker area window that excludes everything",
         dict(configs=edited(edited(CONFIGS, {"Config_ID": "C_SCATTER",
                                              "Option": "min_marker_area"},
                                    Value="500"),
                             {"Config_ID": "C_SCATTER", "Option": "min_marker_area"},
                             Value="500")
              + [dict(Config_ID="C_SCATTER", Option="max_marker_area",
                      Value="10", Note="")]),
         "READER_OPTIONS_CONTRADICT"),
        # The released LINE_MONO reader matches by marker geometry and never
        # looks at Line_Style, so a manifest describing a solid-versus-dashed
        # figure must not validate against it.
        ("a LINE_MONO series told apart only by line style",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="LINE_MONO",
                            Config_ID="C_MONOLINE"),
              series_rows=[dict(r, Colour_Hex="", Marker_Shape="NONE",
                                Line_Style=("SOLID" if r["Series_ID"] == "S_BLUE"
                                            else "DASHED"))
                           if r["Panel_ID"] == "P_LINE" else r for r in SERIES],
              configs=CONFIGS + [dict(Config_ID="C_MONOLINE", Option="threshold",
                                      Value="150", Note="")]),
         "MISSING_SERIES_DISCRIMINANT"),
        ("a LINE_MONO series promising a line style the reader ignores",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="LINE_MONO",
                            Config_ID="C_MONOLINE"),
              series_rows=[dict(r, Colour_Hex="", Marker_Shape="CIRCLE",
                                Marker_Fill=("OPEN" if r["Series_ID"] == "S_BLUE"
                                             else "FILLED"),
                                Line_Style=("SOLID" if r["Series_ID"] == "S_BLUE"
                                            else "DASHED"))
                           if r["Panel_ID"] == "P_LINE" else r for r in SERIES],
              configs=CONFIGS + [dict(Config_ID="C_MONOLINE", Option="threshold",
                                      Value="150", Note="")]),
         "LINE_STYLE_NOT_READ"),
        # An unreleased mark type is not a manifest error, but its series still
        # have to be separable by the discriminant that reader WILL use.
        ("an unreleased mark type whose series share a line style",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                            Mark_Type="LINE_MONO_STYLE", Config_ID=""),
              series_rows=[dict(r, Colour_Hex="", Marker_Shape="NONE",
                                Line_Style="SOLID")
                           if r["Panel_ID"] == "P_LINE" else r for r in SERIES]),
         "SERIES_NOT_SEPARABLE"),
        ("an unreleased mark type whose series declare no line style",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                            Mark_Type="LINE_MONO_STYLE", Config_ID=""),
              series_rows=[dict(r, Colour_Hex="", Marker_Shape="NONE",
                                Line_Style="NONE")
                           if r["Panel_ID"] == "P_LINE" else r for r in SERIES]),
         "MISSING_SERIES_DISCRIMINANT"),
):
    _got = validate(**_kw)
    check(_name + " is rejected", _want in _got, "got %s" % _got)

# `Mask_Key` names one of the reader's three built-in masks and was accepted
# unchecked. The masks are keyed in lower case, so BLUE - the natural way to
# write it - validated, reached `masks["BLUE"]`, raised KeyError inside the
# reader, and became an InternalReaderError, which aborts the whole batch. A
# manifest typo must not be reported as a defect in the reader.
def _bar_series(**kw):
    return dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                              Mark_Type="BAR_COLOR", Config_ID="C_DEFAULT"),
                series_rows=[dict(r, **kw) if r["Panel_ID"] == "P_LINE" else r
                             for r in SERIES],
                positions=POSITION_ROWS)


def _two_masks(first, second, hex_=""):
    return dict(_bar_series(), series_rows=[
        dict(r, Colour_Hex=hex_,
             Mask_Key=(first if r["Series_ID"] == "S_BLUE" else second))
        if r["Panel_ID"] == "P_LINE" else r for r in SERIES])


for _name, _kw, _want in (
        ("Mask_Key naming a mask that does not exist",
         _two_masks("GREEN", "red"), "BAD_MASK_KEY"),
        ("Mask_Key that is not a mask name at all",
         _two_masks("foo", "red"), "BAD_MASK_KEY"),
        # Two discriminants means the manifest says two things and the run
        # believes whichever the code checks first.
        ("a series declaring both a mask and a colour",
         _two_masks("blue", "red", hex_="#2d50dc"),
         "SERIES_DISCRIMINANT_AMBIGUOUS")):
    _got = validate(**_kw)
    check(_name + " is rejected", _want in _got, "got %s" % _got)
for _spelling in ("blue", "BLUE", "Blue", " blue "):
    _got = validate(**_two_masks(_spelling, "red"))
    check("Mask_Key=%r is accepted, whatever the case" % _spelling,
          "BAD_MASK_KEY" not in _got and "SERIES_DISCRIMINANT_AMBIGUOUS" not in _got,
          "got %s" % _got)
check("the validator's mask list is the reader's own",
      tuple(sorted(BM.BAR_COLOR_MASK_KEYS)) == tuple(sorted(BR.BUILTIN_MASK_KEYS)),
      "%s vs %s" % (BM.BAR_COLOR_MASK_KEYS, BR.BUILTIN_MASK_KEYS))

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
              fr(CONFIGS, BM.reader_config_columns()),
              source_documents=fr(SOURCE_DOCUMENTS,
                                  BM.source_document_manifest_columns()),
              source_figures=fr(SOURCE_FIGURES, BM.source_figure_manifest_columns()),
              source_panels=fr(SOURCE_PANELS, BM.source_panel_inventory_columns()),
              reviewers=fr(REVIEWERS, BM.reviewer_registry_columns()),
              file_root=ROOT)))


# --------------------------------------------------------------------------
print("a run turns declared panels into declared cells")
MDIR = write_manifests(os.path.join(ROOT, "manifests"))
ODIR = os.path.join(ROOT, "out")
summary = RB.run_batch(MDIR, ODIR, file_root=ROOT, run_date="2026-08-06")
check("the batch ran", summary["status"] == "RAN", "%s" % summary)

values = pd.read_csv(os.path.join(ODIR, "figure_values_raw.csv"), dtype=object).fillna("")
accepted = pd.read_csv(os.path.join(ODIR, "figure_values_machine_qc.csv"), dtype=object).fillna("")
run = pd.read_csv(os.path.join(ODIR, "run_manifest.csv"), dtype=object).fillna("")
queue = pd.read_csv(os.path.join(ODIR, "manual_queue.csv"), dtype=object).fillna("")
qc = pd.read_csv(os.path.join(ODIR, "qc_problems.csv"), dtype=object).fillna("")
coverage = pd.read_csv(os.path.join(ODIR, "source_panel_coverage.csv"),
                       dtype=object).fillna("")
states = dict(zip(run["Panel_ID"], run["Run_State"]))

check("the source coverage ledger has one row per physical panel",
      len(coverage) == 4 and coverage["Source_Panel_ID"].is_unique,
      "%d rows" % len(coverage))
check("manual panels remain visible in source coverage rather than disappearing",
      dict(zip(coverage["Source_Panel_ID"], coverage["Coverage_Status"]))[
          "P_MANUAL"] == "QUEUED_OR_FAILED")

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
# Recorded relative to the run, so handing the accepted file to another folder
# or another machine does not leave every provenance link pointing at a
# directory that exists only where the run happened.
_scat_points = RB.resolve_artifact(ODIR, _scat["Point_Data_Reference"])
check("the value's point reference is relative to the run, not to this machine",
      not os.path.isabs(_scat["Point_Data_Reference"])
      and _scat["Point_Data_Reference"].startswith("raw/"),
      "%r" % _scat["Point_Data_Reference"])
check("the point file the run wrote is on disk and re-derivable",
      _scat_points and os.path.exists(_scat_points)
      and MR.read_point_data(_scat_points)["Unit_ID"] == "U_SCAT",
      "%r" % _scat_points)
check("the point file names the cell it backs",
      MR.read_point_data(_scat_points)["Cell_Key"] == _scat["Cell_Key"])
check("and so is every other output-facing path the run recorded",
      not any(os.path.isabs(v) for v in
              list(values["WPD_Project_File"]) + list(values["Point_Data_Reference"])
              + list(run["Raw_Data_File"]) + list(run["WPD_Project_File"]) if v),
      "%s" % [v for v in list(values["WPD_Project_File"])
              + list(run["Raw_Data_File"]) if v and os.path.isabs(v)][:3])
# `N_Pairs` is how many blobs survived the area filter. On its own it cannot
# say whether that is the study's sample: it IS the number the association was
# computed from, so it agrees with itself by construction.
check("the association records the count it was measured against",
      int(_scat["Expected_N_From_Source"]) == len(SCATTER_XY)
      and int(_scat["Detected_Unique_Point_Count"]) == len(SCATTER_XY)
      and _scat["Point_Count_Agreement"] == "MATCH",
      "%r" % {k: _scat[k] for k in ("Expected_N_From_Source",
                                    "Detected_Unique_Point_Count",
                                    "Point_Count_Agreement")})
check("and says nothing is hiding behind anything",
      _scat["Overplotting_Possible"] == "FALSE"
      and int(_scat["Series_Mask_Overlap_Count"]) == 0,
      "%r" % dict(_scat))
check("the p is the Pearson t, named for the test that produced it",
      _scat["P_Value_Method"] == "PEARSON_T_TEST", "%r" % _scat["P_Value_Method"])
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

print("nothing unaccepted can reach master by reading one file")
check("there is no file called figure_values.csv at all",
      not os.path.exists(os.path.join(ODIR, "figure_values.csv")),
      "the ambiguous name is back - a downstream reader will pool from it")
check("every raw row carries its own verdict, so no join is needed",
      {"Value_Status", "QC_Codes", "Pooling_Eligible"} <= set(values.columns),
      "%s" % sorted(values.columns)[-4:])
check("every raw status is in the declared vocabulary",
      set(values["Value_Status"]) <= {"MACHINE_QC_PASSED", "QC_FAILED", "PANEL_NOT_PASSED"},
      "%s" % sorted(set(values["Value_Status"])))
# Nothing this module writes is poolable. MACHINE_QC_PASSED means the machine
# found nothing wrong, which is a different claim from a person having looked
# at where the reader put its marks - and it was the same column before, so
# "the gate is happy" and "somebody checked" were indistinguishable downstream.
check("no row the run writes claims to be poolable",
      set(values["Pooling_Eligible"]) == {"FALSE"},
      "%s" % sorted(set(values["Pooling_Eligible"])))
check("the run writes no accepted file at all",
      not os.path.exists(os.path.join(ODIR, "figure_values_accepted.csv")),
      "%s" % sorted(os.listdir(ODIR)))
check("the machine-QC file is the MACHINE_QC_PASSED subset, nothing more",
      len(accepted) == sum(values["Value_Status"] == "MACHINE_QC_PASSED")
      and set(accepted["Cell_Key"]) ==
      set(values[values["Value_Status"] == "MACHINE_QC_PASSED"]["Cell_Key"]),
      "%d vs %d" % (len(accepted),
                    sum(values["Value_Status"] == "MACHINE_QC_PASSED")))
check("every accepted row belongs to an AUTO_PASS panel",
      all(states.get(_p) == "AUTO_PASS"
          for _p, _u in zip(run["Panel_ID"], run["Unit_ID"])
          if _u in set(accepted["Unit_ID"])),
      "%s" % states)

# A unit whose dispersion definition is a placeholder is read fine and rejected
# by the gate. Its numbers are real; they are also unpoolable, and the whole
# point of the split is that a downstream script cannot get at them by accident.
_unresolved = [dict(u, Errorbar_Definition_Source=(
    "UNRESOLVED - the caption does not say whether these are SD or SEM"))
    if u["Unit_ID"] == "U_LINE" else u for u in UNITS]
_mdir = write_manifests(os.path.join(ROOT, "m_unres"), units=_unresolved)
_o = os.path.join(ROOT, "o_unres")
_su = RB.run_batch(_mdir, _o, file_root=ROOT, run_date="2026-08-06")
_raw = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
_acc = pd.read_csv(os.path.join(_o, "figure_values_machine_qc.csv"),
                   dtype=object).fillna("")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("an unresolved SD/SEM unit is still read into the raw file",
      len(_raw[_raw["Unit_ID"] == "U_LINE"]) == 8,
      "%d" % len(_raw[_raw["Unit_ID"] == "U_LINE"]))
check("and every one of its rows is marked QC_FAILED",
      set(_raw[_raw["Unit_ID"] == "U_LINE"]["Value_Status"]) == {"QC_FAILED"},
      "%s" % sorted(set(_raw[_raw["Unit_ID"] == "U_LINE"]["Value_Status"])))
check("and names the gate code that rejected it",
      all("UNRESOLVED_ERRORBAR_DEFINITION" in c
          for c in _raw[_raw["Unit_ID"] == "U_LINE"]["QC_Codes"]),
      "%s" % sorted(set(_raw[_raw["Unit_ID"] == "U_LINE"]["QC_Codes"])))
check("and none of them reaches the accepted file",
      not len(_acc[_acc["Unit_ID"] == "U_LINE"]), "%d rows" % len(_acc))
check("the panel is QC_FAILED in the run manifest too",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "QC_FAILED",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))
check("the clean scatter unit is unaffected and still accepted",
      set(_acc["Unit_ID"]) == {"U_SCAT"}, "%s" % sorted(set(_acc["Unit_ID"])))

# The whole-figure case the review named: publication 397, every panel rejected.
_all_bad = [dict(u, Errorbar_Definition_Source="TBD") for u in UNITS]
_mdir = write_manifests(os.path.join(ROOT, "m_allbad"), units=_all_bad,
                        panels=[p for p in PANELS if p["Panel_ID"] != "P_SCAT"],
                        series_rows=[s for s in SERIES if s["Panel_ID"] != "P_SCAT"],
                        source_panels=edited(
                            SOURCE_PANELS, {"Source_Panel_ID": "P_SCAT"},
                            Panel_Disposition="NO_SUMMARY_STATISTIC",
                            Disposition_Reason="excluded from this all-bad fixture"))
_o = os.path.join(ROOT, "o_allbad")
_sa = RB.run_batch(_mdir, _o, file_root=ROOT, run_date="2026-08-06")
_acc = pd.read_csv(os.path.join(_o, "figure_values_machine_qc.csv"),
                   dtype=object).fillna("")
_raw = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
check("when every panel fails QC the accepted file has zero rows",
      len(_acc) == 0, "%d rows" % len(_acc))
check("while the raw file still holds every reading, for the audit trail",
      len(_raw) == 8, "%d rows" % len(_raw))
check("the summary reports both counts, so a caller cannot read only one",
      _sa["values"] == 8 and _sa["accepted"] == 0, "%s" % _sa)
check("the stamp records read and accepted separately",
      json.load(open(os.path.join(_o, "run_stamp.json")))["Values_Accepted"] == 0)


print("a failed re-run leaves no trace of the run before it")
# The sequence that matters: a good run, then a rejected one into the SAME
# directory. Clearing up at the end of a successful run is not enough - the
# rejected run never gets to the end, and the previous accepted file sits there
# looking like the current answer.
_seq = os.path.join(ROOT, "o_seq")
_good = write_manifests(os.path.join(ROOT, "m_seq_good"))
_first = RB.run_batch(_good, _seq, file_root=ROOT, run_date="2026-08-06")
check("the first run leaves a machine-QC file with rows in it",
      _first["machine_qc"] > 0
      and len(pd.read_csv(os.path.join(_seq, "figure_values_machine_qc.csv"))) > 0,
      "%s" % _first)
_bad_seq = write_manifests(
    os.path.join(ROOT, "m_seq_bad"),
    configs=CONFIGS + [dict(Config_ID="C_DEFAULT", Option="x_window",
                            Value="14", Note="")])
_second = RB.run_batch(_bad_seq, _seq, file_root=ROOT, run_date="2026-08-07")
check("the second run is rejected", _second["status"] == "MANIFEST_REJECTED",
      "%s" % _second)
for _name in ("figure_values_machine_qc.csv", "figure_values_raw.csv",
              "run_manifest.csv", "manual_queue.csv", "qc_problems.csv"):
    check("a rejected re-run leaves no stale %s" % _name,
          not os.path.exists(os.path.join(_seq, _name)),
          "the previous run's file survived and now reads as current")
for _name in ("raw", "projects"):
    check("a rejected re-run leaves no stale %s/ directory" % _name,
          not os.path.isdir(os.path.join(_seq, _name)))
_stamp_path = os.path.join(_seq, "run_stamp.json")
check("a rejected run still writes a stamp", os.path.exists(_stamp_path),
      "no stamp at all - the directory now says nothing about why it is empty")
_stamp = json.load(open(_stamp_path)) if os.path.exists(_stamp_path) else {}
check("the stamp records the rejection rather than the last success",
      _stamp.get("Status") == "MANIFEST_REJECTED", "%r" % _stamp)
check("and reports zero read and zero accepted",
      _stamp.get("Values_Read") == 0 and _stamp.get("Values_Accepted") == 0,
      "%r" % _stamp)
check("and counts the manifest problems that stopped it",
      _stamp.get("Manifest_Problems") == _second["problems"], "%r" % _stamp)
check("the rejection summary reports zero values too, not a missing key",
      _second["values"] == 0 and _second["accepted"] == 0, "%s" % _second)
check("manifest_problems.csv is written and names the cause",
      "DUPLICATE_READER_OPTION" in set(pd.read_csv(
          os.path.join(_seq, "manifest_problems.csv"))["check"]))
check("no staging directory is left behind",
      not os.path.isdir(os.path.join(_seq, RB.STAGING)))
# And the reverse order: a good run into a directory holding a rejection.
_third = RB.run_batch(_good, _seq, file_root=ROOT, run_date="2026-08-08")
check("a good run after a rejection clears the rejection's own outputs",
      _third["status"] == "RAN"
      and not os.path.exists(os.path.join(_seq, "manifest_problems.csv")))
check("and its stamp says RAN",
      json.load(open(os.path.join(_seq, "run_stamp.json")))["Status"] == "RAN")
check("every canonical output name is one the run actually clears",
      {"figure_values_machine_qc.csv", "figure_values_raw.csv", "run_manifest.csv",
       "manual_queue.csv", "qc_problems.csv", "manifest_problems.csv",
       "run_stamp.json"} <= set(RB.CANONICAL_OUTPUTS),
      "%s" % sorted(RB.CANONICAL_OUTPUTS))


print("an input that cannot even be loaded is a failure, not a silence")
# The clearing has to be the FIRST thing a run does. Reading the manifests
# first looked harmless: a missing directory, a malformed CSV or an unreadable
# file raised before anything was cleared, so the previous run's accepted file
# and its Status=RAN stamp both survived a run that never happened.
_load = os.path.join(ROOT, "o_load")
RB.run_batch(_good, _load, file_root=ROOT, run_date="2026-08-06")
check("the setup run leaves an accepted file to go stale",
      len(pd.read_csv(os.path.join(_load, "figure_values_machine_qc.csv"))) > 0)

for _name, _break in (
        ("a manifest directory that does not exist",
         lambda d: "/nope/no/such/manifests"),
        ("a manifest file deleted from the set",
         lambda d: (os.remove(os.path.join(d, "unit_manifest.csv")), d)[1]),
        ("a malformed CSV in the set",
         lambda d: (open(os.path.join(d, "panel_manifest.csv"), "w").write(
             'a,b\n1,2,3,4\n"unclosed\n'), d)[1])):
    _md = os.path.join(ROOT, "m_load_%d" % len(_name))
    shutil.rmtree(_md, ignore_errors=True)
    shutil.copytree(_good, _md)
    _target = _break(_md)
    _raised = None
    try:
        RB.run_batch(_target, _load, file_root=ROOT, run_date="2026-08-07")
    except BaseException as exc:      # BaseException on purpose - see next check
        _raised = exc
    check("%s raises rather than returning a result" % _name,
          _raised is not None, "the run returned normally")
    # SystemExit derives from BaseException, so `except Exception` sails past
    # it. If the loader ever goes back to raising one, this fails here rather
    # than taking the suite down with it.
    check("%s is a catchable Exception, not SystemExit" % _name,
          isinstance(_raised, Exception)
          and not isinstance(_raised, SystemExit), "%r" % type(_raised))
    for _f in ("figure_values_machine_qc.csv", "figure_values_raw.csv",
               "run_manifest.csv", "qc_problems.csv"):
        check("%s leaves no stale %s" % (_name, _f),
              not os.path.exists(os.path.join(_load, _f)),
              "the previous run's file survived an input failure")
    _st = os.path.join(_load, "run_stamp.json")
    check("%s still writes a stamp" % _name, os.path.exists(_st))
    _sj = json.load(open(_st)) if os.path.exists(_st) else {}
    check("%s records INPUT_LOAD_FAILED with zero counts" % _name,
          _sj.get("Status") == "INPUT_LOAD_FAILED"
          and _sj.get("Values_Read") == 0 and _sj.get("Values_Accepted") == 0,
          "%r" % _sj)
    check("%s says what went wrong" % _name, bool(_sj.get("Detail")), "%r" % _sj)
    # restore for the next case
    RB.run_batch(_good, _load, file_root=ROOT, run_date="2026-08-06")

check("every status a stamp can carry is declared",
      {"RAN", "MANIFEST_REJECTED", "INPUT_LOAD_FAILED", "PROMOTE_FAILED",
       "DEMO_OUTPUT_REFUSED", "GEOMETRY_REVIEW_FAILED",
       "INTERNAL_ERROR"} == set(RB.RUN_STATUSES),
      "%s" % sorted(RB.RUN_STATUSES))


print("a panel nobody can read still says how much work it is")
# `Panel_Mode=MANUAL` returned before the series and position maps were built,
# and so did an unopenable raster and an unparseable box - so those panels
# reported Cells_Declared=0 and Missing_Cells="". A manual panel with 24 cells
# came out "MANUAL_POINT_READ 0 / 0": the queue understated the hand-digitizing
# left to do, on exactly the panels that are nothing but hand-digitizing.
_declared_expect = len({r["Series_ID"] for r in SERIES
                        if r["Panel_ID"] == "P_MANUAL"}) * len(
    {r["Position_ID"] for r in POSITION_ROWS if r["Panel_ID"] == "P_MANUAL"})
_rm_now = pd.read_csv(os.path.join(ODIR, "run_manifest.csv"), dtype=object).fillna("")
_manual = _rm_now[_rm_now["Panel_ID"] == "P_MANUAL"].iloc[0]
check("a MANUAL panel declares its cells",
      int(_manual["Cells_Declared"]) == _declared_expect,
      "%s declared, expected %d" % (_manual["Cells_Declared"], _declared_expect))
_q_now = pd.read_csv(os.path.join(ODIR, "manual_queue.csv"), dtype=object).fillna("")
_mq = _q_now[_q_now["Panel_ID"] == "P_MANUAL"]
check("and its queue row counts every cell a person has to read",
      len(_mq) and int(_mq.iloc[0]["Missing_Cell_Count"]) == _declared_expect,
      "%r" % (_mq.iloc[0]["Missing_Cell_Count"] if len(_mq) else None))
# The list itself is rows, not a delimited string: cell keys ARE ";"-joined
# FACTOR=LEVEL pairs, so "ARM=A;T=1;ARM=B;T=1" could not be split back into the
# two cells it came from.
_qc = pd.read_csv(os.path.join(ODIR, "manual_queue_cells.csv"), dtype=object).fillna("")
check("and every one of them is a row of its own",
      len(_qc[_qc["Panel_ID"] == "P_MANUAL"]) == _declared_expect,
      "%d rows" % len(_qc[_qc["Panel_ID"] == "P_MANUAL"]))
check("each parsing as a whole cell key, not half of one",
      all(GE.fig_parse_cell_key(k) is not None for k in _qc["Cell_Key"]),
      "%s" % [k for k in _qc["Cell_Key"] if GE.fig_parse_cell_key(k) is None][:2])
check("Missing_Cells the ambiguous string is gone",
      "Missing_Cells" not in RB.MANUAL_QUEUE_COLUMNS,
      "%s" % RB.MANUAL_QUEUE_COLUMNS)

# Validation normally catches a bad box or a degenerate calibration first, which
# is right. `check_files=False` is how a caller skips the raster checks, and it
# is the path where the runner meets the geometry itself.
_d = os.path.join(ROOT, "o_decl_geometry")
_s2 = RB.run_batch(write_manifests(
    os.path.join(ROOT, "m_decl_geometry"),
    panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                  Image_Path=os.path.join(IMAGES, "vanished_for_geometry.png"))),
    _d, file_root=ROOT, run_date="2026-08-06", check_files=False)
_r2 = pd.read_csv(os.path.join(_d, "run_manifest.csv"), dtype=object).fillna("")
_row = _r2[_r2["Panel_ID"] == "P_LINE"].iloc[0]
check("a raster the runner cannot open is PANEL_GEOMETRY_UNRESOLVED",
      _row["Run_State"] == "PANEL_GEOMETRY_UNRESOLVED", "%s" % _row["Run_State"])
check("and it still declares its cells",
      int(_row["Cells_Declared"]) > 0, "%s" % _row["Cells_Declared"])
_qc2 = pd.read_csv(os.path.join(_d, "manual_queue_cells.csv"), dtype=object).fillna("")
check("and names every one of them for the person who now has to read it",
      len(_qc2[_qc2["Panel_ID"] == "P_LINE"]) == int(_row["Cells_Declared"]),
      "%d rows for %s declared" % (len(_qc2[_qc2["Panel_ID"] == "P_LINE"]),
                                   _row["Cells_Declared"]))

check("every panel in the run declares at least one cell",
      all(int(v) > 0 for v in _rm_now["Cells_Declared"]),
      "%s" % dict(zip(_rm_now["Panel_ID"], _rm_now["Cells_Declared"])))


print("a position without a pixel is not a position")
# The validator accepted X_Pixel OR Slot_Index. `_x_positions` only ever passes
# rows that have an X_Pixel, and no released reader is slot-based - so a
# Slot_Index-only manifest validated, reached the reader as an empty position
# map, and came back as an unreadable figure.
_slot_only = edited(POSITION_ROWS, {"Panel_ID": "P_LINE", "Position_ID": POSITIONS[0]},
                    X_Pixel="")
check("a Slot_Index-only position is refused as a capability, not geometry",
      "UNSUPPORTED_CAPABILITY" in validate(positions=_slot_only),
      "%s" % validate(positions=_slot_only))
check("and a position with neither is still missing geometry",
      "MISSING_POSITION_GEOMETRY" in validate(
          positions=edited(POSITION_ROWS,
                           {"Panel_ID": "P_LINE", "Position_ID": POSITIONS[0]},
                           X_Pixel="", Slot_Index="")),
      "%s" % validate(positions=edited(
          POSITION_ROWS, {"Panel_ID": "P_LINE", "Position_ID": POSITIONS[0]},
          X_Pixel="", Slot_Index="")))
check("Slot_Index remains in the schema, as the ordering hint it is",
      "Slot_Index" in BM.position_manifest_columns())


print("a statistic the runner cannot execute is a sentence, not a discovery")
# `grid_engine` validates four statistic types; the batch layer has raster
# readers for three. BINARY_EVENT has a source-panel disposition and a
# validator and no reader, and `run_batch` sends every AUTO panel to a raster
# reader - so a coherent declaration went to a reader that could not produce it
# and came back as a difficult figure.
check("every statistic the gate validates has a capability entry",
      set(BM.CAPABILITY_MATRIX) == set(GE.FIG_STATISTIC_TYPES),
      "%s" % sorted(set(BM.CAPABILITY_MATRIX) ^ set(GE.FIG_STATISTIC_TYPES)))
check("and every entry says AUTO_SUPPORTED or VALIDATOR_ONLY",
      all(v[0] in ("AUTO_SUPPORTED", "VALIDATOR_ONLY")
          for v in BM.CAPABILITY_MATRIX.values()),
      "%s" % sorted({v[0] for v in BM.CAPABILITY_MATRIX.values()}))
_bin_unit = unit("U_BIN", "G_TIME", "BINARY_EVENT")
_bin_panel = panel("P_BIN", "U_BIN", "LINE_COLOR", LINE_IMG, (100, 500, 40, 440))
_bin_source = dict(Source_Panel_ID="P_BIN", Source_Figure_ID="SF1",
                   Panel_Label="P_BIN", Outcome_Label="Presyncope",
                   Target_Status="TARGET", Panel_Disposition="AUTO_DIGITIZE",
                   Disposition_Reason="binary fixture", Note="")


def _bin(mode):
    return validate(
        panels=PANELS + [dict(_bin_panel, Panel_Mode=mode)],
        units=UNITS + [_bin_unit],
        series_rows=SERIES + [series("P_BIN", "S_A", "CONTROL")],
        positions=POSITION_ROWS + [dict(r, Panel_ID="P_BIN")
                                   for r in POSITION_ROWS
                                   if r["Panel_ID"] == "P_LINE"],
        source_panels=SOURCE_PANELS + [
            dict(_bin_source,
                 Panel_Disposition="MANUAL_DIGITIZE" if mode == "MANUAL"
                 else "AUTO_DIGITIZE")],
        source_figures=[dict(f, Observed_Panel_Count=2)
                        if f["Source_Figure_ID"] == "SF1" else f
                        for f in SOURCE_FIGURES])


check("an AUTO panel declaring a validator-only statistic is refused",
      "UNSUPPORTED_CAPABILITY" in _bin("AUTO"), "%s" % _bin("AUTO"))
check("and the same panel declared MANUAL is allowed through to the queue",
      "UNSUPPORTED_CAPABILITY" not in _bin("MANUAL"), "%s" % _bin("MANUAL"))
check("BINARY_EVENT is the validator-only one",
      BM.VALIDATOR_ONLY_STATISTICS == ("BINARY_EVENT",),
      "%s" % (BM.VALIDATOR_ONLY_STATISTICS,))


print("every allowed declaration is either read exactly, or refused")
# The batch layer requires a series row on every positional panel. The released
# box/violin reader returns positions and no series at all. So a two-series box
# panel validated, ran, and produced half a grid - every cell of the second
# series missing, reported as a difficult figure rather than as a capability
# the package does not have.
_bv_panel = panel("P_BOX", "U_BOX", "BOX_VIOLIN", LINE_IMG, (100, 500, 40, 440))
_bv_unit = unit("U_BOX", "G_TIME", "QUANTILE_SUMMARY")
_bv_source = dict(Source_Panel_ID="P_BOX", Source_Figure_ID="SF1",
                  Panel_Label="P_BOX", Outcome_Label="Heart rate",
                  Target_Status="TARGET", Panel_Disposition="AUTO_DIGITIZE",
                  Disposition_Reason="box fixture", Note="")


def _bv(series_ids):
    return validate(
        panels=PANELS + [_bv_panel], units=UNITS + [_bv_unit],
        series_rows=SERIES + [series("P_BOX", s, lv) for s, lv in series_ids],
        positions=POSITION_ROWS + [dict(r, Panel_ID="P_BOX")
                                   for r in POSITION_ROWS if r["Panel_ID"] == "P_LINE"],
        source_panels=SOURCE_PANELS + [_bv_source],
        source_figures=[dict(f, Observed_Panel_Count=2)
                        if f["Source_Figure_ID"] == "SF1" else f
                        for f in SOURCE_FIGURES])


check("a two-series box panel is refused before the run, not read into holes",
      "UNSUPPORTED_CAPABILITY" in _bv([("S_A", "CONTROL"), ("S_B", "TREATED")]),
      "%s" % _bv([("S_A", "CONTROL"), ("S_B", "TREATED")]))
check("and a one-series box panel is allowed",
      "UNSUPPORTED_CAPABILITY" not in _bv([("S_A", "ALL")]),
      "%s" % _bv([("S_A", "ALL")]))
_bv_problems = BM.validate_batch_manifests(
    fr(PANELS + [_bv_panel], BM.panel_manifest_columns()),
    fr(SERIES + [series("P_BOX", s, lv)
                 for s, lv in (("S_A", "CONTROL"), ("S_B", "TREATED"))],
       BM.series_manifest_columns()),
    fr(POSITION_ROWS + [dict(r, Panel_ID="P_BOX") for r in POSITION_ROWS
                        if r["Panel_ID"] == "P_LINE"],
       BM.position_manifest_columns()),
    fr(CONFIGS, BM.reader_config_columns()),
    units=fr(UNITS + [_bv_unit], GE.fig_unit_columns()),
    source_documents=fr(SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
    source_figures=fr([dict(f, Observed_Panel_Count=2)
                       if f["Source_Figure_ID"] == "SF1" else f
                       for f in SOURCE_FIGURES],
                      BM.source_figure_manifest_columns()),
    source_panels=fr(SOURCE_PANELS + [_bv_source],
                     BM.source_panel_inventory_columns()),
    reviewers=fr(REVIEWERS, BM.reviewer_registry_columns()), file_root=ROOT)
check("UNSUPPORTED_CAPABILITY names the reader limit, not the figure",
      any("grouped box reader" in str(p["detail"])
          for _, p in _bv_problems.iterrows()
          if p["check"] == "UNSUPPORTED_CAPABILITY"),
      "%s" % [p["detail"] for _, p in _bv_problems.iterrows()
              if p["check"] == "UNSUPPORTED_CAPABILITY"])


print("a figure with more than one digitized panel keeps every project")
# `projects_by_figure.setdefault(Figure_ID, outcome.project)` recorded whichever
# panel of a figure finished first, and the gate then looked the project up ON
# THE FIGURE. On publication 397's Figure 3 that meant six panels' values all
# named the MEN panel's tar - somebody else's marks, read off somebody else's
# calibration - and the five WOMEN panels' projects were simply not written
# down anywhere the gate could see.
# Two AUTO panels of the same Figure_ID, on different rasters - which is what a
# publisher figure with MEN and WOMEN sides actually is.
_multi = write_manifests(
    os.path.join(ROOT, "m_multi"),
    units=UNITS + [unit("U_LINE_B", "G_TIME", "CONTINUOUS")],
    panels=PANELS + [panel("P_LINE_B", "U_LINE_B", "LINE_COLOR", LINE_IMG,
                           (100, 500, 40, 440))],
    series_rows=SERIES + [series("P_LINE_B", s, lv, Colour_Hex=hx)
                          for s, lv, hx in (("S_BLUE", "CONTROL", "#2d50dc"),
                                            ("S_RED", "TREATED", "#d72d2d"))],
    positions=POSITION_ROWS + [dict(r, Panel_ID="P_LINE_B")
                               for r in POSITION_ROWS if r["Panel_ID"] == "P_LINE"],
    source_panels=SOURCE_PANELS + [dict(
        Source_Panel_ID="P_LINE_B", Source_Figure_ID="SF1", Panel_Label="P_LINE_B",
        Outcome_Label="Heart rate", Target_Status="TARGET",
        Panel_Disposition="AUTO_DIGITIZE",
        Disposition_Reason="second digitized panel of one figure", Note="")],
    source_figures=[dict(f, Observed_Panel_Count=2)
                    if f["Source_Figure_ID"] == "SF1" else f
                    for f in SOURCE_FIGURES])
_mo = os.path.join(ROOT, "o_multi")
RB.run_batch(_multi, _mo, file_root=ROOT, run_date="2026-08-06")
_raw = pd.read_csv(os.path.join(_mo, "figure_values_raw.csv"), dtype=object).fillna("")
_rm = pd.read_csv(os.path.join(_mo, "run_manifest.csv"), dtype=object).fillna("")
_by_panel = dict(zip(_rm["Panel_ID"], _rm["WPD_Project_File"]))
check("every value names the project that can re-derive it",
      len(_raw) and all(str(v).strip() for v in _raw["WPD_Project_File"]),
      "%d blank of %d" % (sum(1 for v in _raw["WPD_Project_File"]
                              if not str(v).strip()), len(_raw)))
check("and it is its own panel's project, not a sibling's",
      all(r["WPD_Project_File"] == _by_panel.get(r["Run_Panel_ID"], "")
          for _, r in _raw.iterrows() if r["Run_Panel_ID"] in _by_panel),
      "%s" % {r["Run_Panel_ID"]: os.path.basename(r["WPD_Project_File"])
              for _, r in _raw.iterrows()})
_fm = pd.read_csv(os.path.join(_mo, "figure_manifest.csv"), dtype=object).fillna("")
_listed = [p for p in str(_fm.loc[0, "WPD_Project_File"]).split(";") if p]
check("and the figure lists every panel project it produced, not just the first",
      len(_listed) == sum(1 for v in _by_panel.values() if str(v).strip()),
      "%s" % [os.path.basename(p) for p in _listed])
check("and each one is on disk, resolved against the run it belongs to",
      all(RB.resolve_artifact(_mo, p)
          and os.path.exists(RB.resolve_artifact(_mo, p)) for p in _listed),
      "%s" % _listed)

# Two ticks were saved out of however many the calibration was fitted on, so the
# artifact that exists for re-deriving a value could not reproduce the fit.
_proj = RB.resolve_artifact(_mo, _listed[0])
with tarfile.open(_proj) as _tf:
    _info = json.loads(_tf.extractfile("info.json").read().decode("utf-8")) \
        if "info.json" in _tf.getnames() else {}
    _wpd = json.loads(_tf.extractfile(
        next(n for n in _tf.getnames() if n.endswith("wpd.json"))).read().decode("utf-8"))
_declared_ticks = len(BM.parse_ticks(PANELS[0]["Axis_Y_Ticks"]))
_saved = sum(1 for a in _wpd.get("axesColl", [])
             for _c in a.get("calibrationPoints", []) if _c.get("dy") != "")
check("the project saves every declared tick, not the first two",
      _saved >= _declared_ticks, "%d saved of %d declared" % (_saved, _declared_ticks))


print("a defect in a reader is not a difficult figure")
# Every reader call sat inside `except Exception`, and whatever came out was
# reported as PANEL_GEOMETRY_UNRESOLVED. A TypeError from a misspelled keyword
# and a genuinely unreadable axis reached a human as the same queue row: go and
# look at this figure again. Over 116 publications that turns a defect in this
# package into hours of correct manual work nobody knows was unnecessary.
_orig_read_panel = MR.read_panel
_real_calibration = MR.AxisCalibration.from_points


def _raising(exc):
    def _fake(*a, **k):
        raise exc
    return _fake


for _label, _exc, _want_state, _aborts in (
        ("a KeyError from a renamed field", KeyError("Series_ID"), None, True),
        ("a TypeError from a misspelled keyword",
         TypeError("read_panel() got an unexpected keyword 'n_slot'"), None, True),
        ("an IndexError walking off a list", IndexError("list index out of range"),
         None, True),
        ("an axis the reader cannot fit",
         MR.GeometryResolutionError("axis calibration needs two distinct pixels"),
         "PANEL_GEOMETRY_UNRESOLVED", False),
        ("two series the reader cannot tell apart",
         MR.SeriesIdentityError("S_BLUE and S_RED share every mark"),
         "SERIES_IDENTITY_UNRESOLVED", False),
        ("a declaration no released reader honours",
         MR.UnsupportedCapabilityError("stacked bars are not released"),
         "NO_READER_AVAILABLE", False)):
    _out = os.path.join(ROOT, "o_exc_%d" % (abs(hash(_label)) % 10 ** 6))
    MR.read_panel = _raising(_exc)
    try:
        _summary = RB.run_batch(_good, _out, file_root=ROOT, run_date="2026-08-06")
        _raised = None
    except RB.InternalReaderError as exc:
        _summary, _raised = None, exc
    except Exception as exc:                                   # pragma: no cover
        _summary, _raised = None, exc
    finally:
        MR.read_panel = _orig_read_panel
    if _aborts:
        check("%s stops the batch" % _label,
              isinstance(_raised, RB.InternalReaderError), "%r" % _raised)
        _js = json.load(open(os.path.join(_out, "run_stamp.json")))
        check("  and the stamp says INTERNAL_ERROR, not a figure problem",
              _js.get("Status") == "INTERNAL_ERROR", "%r" % _js.get("Status"))
        check("  and names the exception so it can be fixed",
              type(_exc).__name__ in _js.get("Detail", ""), "%r" % _js.get("Detail"))
        check("  and leaves nothing poolable behind",
              not os.path.exists(os.path.join(_out, RB.COMMIT_MARKER))
              and not os.path.exists(os.path.join(_out, "figure_values_accepted.csv")),
              "%s" % sorted(os.listdir(_out)))
    else:
        check("%s is a panel state, not a crash" % _label,
              _raised is None and _summary and _summary["status"] == "RAN",
              "%r %s" % (_raised, _summary))
        _rm = pd.read_csv(os.path.join(_out, "run_manifest.csv"), dtype=object)
        check("  and every auto panel lands on %s" % _want_state,
              _want_state in set(_rm["Run_State"]), "%s" % sorted(set(_rm["Run_State"])))


print("a demonstration identity cannot stand behind a poolable value")
# The worked example needs a reviewer, and a fictional one is the honest choice
# - but the only thing that kept it harmless was that ID397's dispersion
# definition happened to be unresolved, so nothing was accepted. Resolve it and
# the same fictional row signs off real numbers. This batch DOES accept values,
# which is what makes it the right fixture: the gate has to be what stops them.
_demo = os.path.join(ROOT, "o_demo")
_demo_summary = RB.run_batch(_good, _demo, file_root=ROOT,
                             run_date="2026-08-06", run_mode="DEMO_ONLY")
_demo_files = sorted(os.listdir(_demo)) if os.path.isdir(_demo) else []
_demo_stamp = json.load(open(os.path.join(_demo, "run_stamp.json")))
check("a DEMO_ONLY run that accepts values is refused",
      _demo_summary["status"] == "DEMO_OUTPUT_REFUSED", "%s" % _demo_summary)
check("and says how many values it refused to write",
      _demo_summary["would_accept"] > 0 and _demo_summary["accepted"] == 0,
      "%s" % _demo_summary)
check("and writes no accepted file",
      RB.COMMIT_MARKER not in _demo_files, "%s" % _demo_files)
check("and writes no raw values file either",
      "figure_values_raw.csv" not in _demo_files, "%s" % _demo_files)
check("and leaves nothing but the stamp behind",
      _demo_files == ["run_stamp.json"], "%s" % _demo_files)
check("and the review overlays go with it - no picture of a refused run",
      not os.path.isdir(os.path.join(_demo, "review")),
      "%s" % _demo_files)
check("and the stamp records DEMO_ONLY, not a silent ATTESTED",
      _demo_stamp.get("Run_Mode") == "DEMO_ONLY"
      and _demo_stamp.get("Status") == "DEMO_OUTPUT_REFUSED"
      and _demo_stamp.get("Values_Accepted") == 0, "%r" % _demo_stamp)
check("and the stamp says why", "DEMO_ONLY" in _demo_stamp.get("Detail", ""),
      "%r" % _demo_stamp)

# A demo that accepts nothing is the normal case and must still run - otherwise
# the mode is unusable for the thing it exists for.
_demo_ok = os.path.join(ROOT, "o_demo_ok")
_demo_ok_summary = RB.run_batch(
    write_manifests(os.path.join(ROOT, "m_demo_ok"), units=_all_bad,
                    panels=[p for p in PANELS if p["Panel_ID"] != "P_SCAT"],
                    series_rows=[s for s in SERIES if s["Panel_ID"] != "P_SCAT"],
                    source_panels=edited(
                        SOURCE_PANELS, {"Source_Panel_ID": "P_SCAT"},
                        Panel_Disposition="NO_SUMMARY_STATISTIC",
                        Disposition_Reason="excluded from this all-bad fixture")),
    _demo_ok, file_root=ROOT, run_date="2026-08-06", run_mode="DEMO_ONLY")
check("a DEMO_ONLY run that accepts nothing still runs",
      _demo_ok_summary["status"] == "RAN"
      and _demo_ok_summary["accepted"] == 0, "%s" % _demo_ok_summary)
check("and still writes everything that is not a poolable value",
      {"figure_values_raw.csv", "run_manifest.csv", "manual_queue.csv",
       "qc_problems.csv", "source_panel_coverage.csv"}
      <= set(os.listdir(_demo_ok)), "%s" % sorted(os.listdir(_demo_ok)))
check("and its stamp still records DEMO_ONLY",
      json.load(open(os.path.join(_demo_ok, "run_stamp.json"))).get("Run_Mode")
      == "DEMO_ONLY")

_attested = os.path.join(ROOT, "o_attested")
RB.run_batch(_good, _attested, file_root=ROOT, run_date="2026-08-06")
check("the default run mode is ATTESTED",
      json.load(open(os.path.join(_attested, "run_stamp.json"))).get("Run_Mode")
      == "ATTESTED")
_bad_mode = "caught"
try:
    RB.run_batch(_good, os.path.join(ROOT, "o_badmode"), file_root=ROOT,
                 run_mode="PROBABLY_FINE")
except ValueError as exc:
    _bad_mode = str(exc)
except Exception as exc:                                  # pragma: no cover
    _bad_mode = "wrong exception: %r" % exc
check("an invented run mode is a programming error, not a default",
      "run_mode must be" in _bad_mode and "PROBABLY_FINE" in _bad_mode, _bad_mode)


print("what the reader found for a cell outranks what a person typed for the unit")
# The readers produce Errorbar_Stem_Confirmed per MARK. `run_panel` only flagged
# NO_VARIANCE when ALL marks were False, and `to_value_records` then copied
# mean, dispersion and bounds and dropped everything else - so the gate fell
# back to a single human-typed field on the unit manifest. Three confirmed
# whiskers and one unconfirmed passed on the strength of the three.
_prov = pd.read_csv(os.path.join(ODIR, "figure_values_raw.csv"),
                    dtype=object).fillna("")
for _col in ("Errorbar_Stem_Confirmed", "Bar_Top_Definition", "Bar_Direction",
             "Position_Assignment", "Calibration_Max_Residual",
             "Slot_Assignment_Residual_Px"):
    check("the value schema has room for %s" % _col,
          _col in _prov.columns, "%s" % sorted(_prov.columns))
# Room is not the same as carried. The calibration residual is stamped on every
# row by the runner, so it is blank only if the carry is broken - it was
# computed inside `bar_reader` and returned under a name nothing read.
check("every value row carries the residual of the calibration that produced it",
      len(_prov) and all(str(v).strip() for v in _prov["Calibration_Max_Residual"]),
      "%d of %d blank" % (sum(1 for v in _prov["Calibration_Max_Residual"]
                              if not str(v).strip()), len(_prov)))

_mixed = GE.fig_validate_bundle(
    fr(FIGURES, GE.fig_figure_columns()), fr(GRIDS, GE.fig_grid_columns()),
    fr([dict(UNITS[0], Errorbar_Stem_Confirmed="TRUE")], GE.fig_unit_columns()),
    fr([dict(Unit_ID=UNITS[0]["Unit_ID"], Cell_Key="ARM=CONTROL;TIMEPOINT=%s" % q,
             Mean=50 + i, Dispersion_Value=2,
             Errorbar_Stem_Confirmed="TRUE" if i else "FALSE",
             Bar_Top_Definition="NOT_A_BAR", Verification_Status="SINGLE")
        for i, q in enumerate(POSITIONS)], GE.fig_values_columns()),
    K, check_files=False)
_codes = sorted(set(_mixed["check"])) if len(_mixed) else []
check("one unconfirmed whisker in a panel of confirmed ones is caught",
      "CELL_ERRORBAR_STEM_UNCONFIRMED" in _codes, "%s" % _codes)
check("and only that cell is named",
      sum(1 for _, p in _mixed.iterrows()
          if p["check"] == "CELL_ERRORBAR_STEM_UNCONFIRMED") == 1,
      "%s" % _mixed[_mixed["check"] == "CELL_ERRORBAR_STEM_UNCONFIRMED"].to_dict("records"))

_inferred = GE.fig_validate_bundle(
    fr(FIGURES, GE.fig_figure_columns()), fr(GRIDS, GE.fig_grid_columns()),
    fr([UNITS[0]], GE.fig_unit_columns()),
    fr([dict(Unit_ID=UNITS[0]["Unit_ID"], Cell_Key="ARM=CONTROL;TIMEPOINT=%s" % q,
             Mean=50, Dispersion_Value=2, Errorbar_Stem_Confirmed="TRUE",
             Bar_Top_Definition="NOT_A_BAR", Position_Assignment="SEQUENTIAL",
             Verification_Status="SINGLE")
        for q in POSITIONS], GE.fig_values_columns()),
    K, check_files=False)
check("a cell whose x identity was counted off rather than declared is caught",
      "POSITION_INFERRED" in (sorted(set(_inferred["check"])) if len(_inferred) else []),
      "%s" % (sorted(set(_inferred["check"])) if len(_inferred) else []))


print("one raster, one hash, checked end to end")
# The same fact was declared in four places and joined in none: the source
# figure's image, the figure manifest's image, the panel's Image_Path, and the
# hash written beside them. Each file was individually valid, so a panel could
# read raster A while its inventory row, its reconciliation and its provenance
# all described raster B.
check("a source figure must declare the hash of its own raster",
      "MISSING_REQUIRED" in validate(
          source_figures=edited(SOURCE_FIGURES, {"Source_Figure_ID": "SF1"},
                                Source_Image_SHA256="")))
check("a declared hash that is not the file's hash is refused",
      "SOURCE_IMAGE_HASH_MISMATCH" in validate(
          source_figures=edited(SOURCE_FIGURES, {"Source_Figure_ID": "SF1"},
                                Source_Image_SHA256="0" * 64)),
      "%s" % validate(source_figures=edited(
          SOURCE_FIGURES, {"Source_Figure_ID": "SF1"}, Source_Image_SHA256="0" * 64)))
check("a panel reading a raster its source figure does not own is refused",
      "PANEL_IMAGE_NOT_ITS_SOURCE_FIGURE" in validate(
          panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Image_Path=FLAT_IMG)),
      "%s" % validate(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                                    Image_Path=FLAT_IMG)))
check("and swapping the panel's Source_Panel_ID instead does not help",
      "PANEL_IMAGE_NOT_ITS_SOURCE_FIGURE" in validate(
          panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                        Source_Panel_ID="P_FLAT")),
      "%s" % validate(panels=edited(PANELS, {"Panel_ID": "P_LINE"},
                                    Source_Panel_ID="P_FLAT")))
check("moving the raster and its hash together is fine",
      validate(source_figures=edited(
          SOURCE_FIGURES, {"Source_Figure_ID": "SF1"},
          Source_Image=FLAT_IMG, Source_Image_SHA256=MR.sha256_of(FLAT_IMG)),
          panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Image_Path=FLAT_IMG)) == [],
      "%s" % validate(source_figures=edited(
          SOURCE_FIGURES, {"Source_Figure_ID": "SF1"},
          Source_Image=FLAT_IMG, Source_Image_SHA256=MR.sha256_of(FLAT_IMG)),
          panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Image_Path=FLAT_IMG)))


print("an identifier that becomes a filename cannot leave the output directory")
# Panel_ID and Series_ID are interpolated into {Panel_ID}_marks.json,
# {Panel_ID}.tar and {Panel_ID}_{Series_ID}_points.json with nothing checking
# them. Panel_ID="../../escaped" wrote escaped.tar and escaped_marks.json two
# directories above the output root - and the run still reported ACCEPTED.
for _bad in ("../../escaped", "/etc/passwd", "a/b", "..", ".hidden", "",
             "x" * 200):
    if not _bad:
        continue
    check("Panel_ID=%r is refused before anything is written" % _bad,
          "UNSAFE_ID" in validate(
              panels=edited(PANELS, {"Panel_ID": "P_FLAT"}, Panel_ID=_bad)),
          "%s" % validate(panels=edited(PANELS, {"Panel_ID": "P_FLAT"}, Panel_ID=_bad)))
check("Series_ID is checked too, not just Panel_ID",
      "UNSAFE_ID" in validate(
          series_rows=edited(SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"},
                             Series_ID="../x")),
      "%s" % validate(series_rows=edited(
          SERIES, {"Panel_ID": "P_LINE", "Series_ID": "S_RED"}, Series_ID="../x")))
for _ok in ("P_FLAT", "P3_TPR_MEN", "id323.fig2-b", "A1"):
    check("a normal identifier like %r still passes" % _ok,
          not BM.SAFE_ID.match(_ok) is None)

# The image path is the other half: an absolute path anywhere on the machine
# used to resolve, because the resolver tried the string as given first.
_outside = os.path.join(tempfile.gettempdir(), "fdt_outside_root.png")
Image.new("RGB", (40, 40), "white").save(_outside)
check("an image outside file_root is not found, however it is spelled",
      "SOURCE_FILE_NOT_FOUND" in validate(
          panels=edited(PANELS, {"Panel_ID": "P_FLAT"}, Image_Path=_outside)),
      "%s" % validate(panels=edited(PANELS, {"Panel_ID": "P_FLAT"}, Image_Path=_outside)))
check("and neither is one reached by walking out and back in",
      "SOURCE_FILE_NOT_FOUND" in validate(
          panels=edited(PANELS, {"Panel_ID": "P_FLAT"},
                        Image_Path="../%s" % os.path.basename(_outside))))


print("a problem charged to a figure condemns every value read from it")
# The gate reports IMAGE_HASH_MISMATCH at `figures:2` - the raster on disk is
# not the raster the manifest names, so nothing measured from it is evidence of
# anything. `_units_named_by` read only `unit:`, `units:` and `values:`, so the
# figure grain fell on the floor and every value was still ACCEPTED. On the
# dispersion-resolved ID397 copy that was 48 poolable rows from an image the
# batch had been told, nine times, was the wrong one.
for _label, _figs, _want in (
        ("a figure hash that does not match the raster",
         [dict(FIGURES[0], Image_Resolution_Or_Hash="600x480 sha256:" + "0" * 64)],
         "IMAGE_HASH_MISMATCH"),
        ("a figure whose panel count is still unreconciled",
         [dict(FIGURES[0], Panel_Reconciliation_Status="PENDING")],
         None),
        ("a figure whose source image is not on disk",
         [dict(FIGURES[0], Source_Image=os.path.join(ROOT, "no_such_figure.png"))],
         None)):
    _d = os.path.join(ROOT, "o_fig_" + str(abs(hash(_label)) % 10 ** 8))
    _sm = RB.run_batch(write_manifests(os.path.join(ROOT, "m_fig_%d"
                                                    % (abs(hash(_label)) % 10 ** 8)),
                                       figures=_figs),
                       _d, file_root=ROOT, run_date="2026-08-06")
    _qc = pd.read_csv(os.path.join(_d, "qc_problems.csv")) if os.path.exists(
        os.path.join(_d, "qc_problems.csv")) else pd.DataFrame(columns=["where", "check"])
    _acc = pd.read_csv(os.path.join(_d, "figure_values_machine_qc.csv"),
                       dtype=object) if os.path.exists(
        os.path.join(_d, "figure_values_machine_qc.csv")) else pd.DataFrame()
    check("%s is caught at the figure grain" % _label,
          any(str(w).startswith("figures:") for w in _qc.get("where", [])),
          "%s" % _qc.to_dict("records")[:4])
    if _want:
        check("and the code is %s" % _want, _want in set(_qc.get("check", [])),
              "%s" % sorted(set(_qc.get("check", []))))
    check("and not one value from that figure is poolable (%s)" % _label,
          len(_acc) == 0, "%d accepted" % len(_acc))
    _rm = pd.read_csv(os.path.join(_d, "run_manifest.csv"))
    check("and its auto panels are QC_FAILED, not AUTO_PASS (%s)" % _label,
          "AUTO_PASS" not in set(_rm["Run_State"]), "%s" % sorted(set(_rm["Run_State"])))

# A grid problem is the same argument one grain along: every unit that declares
# the grid inherits it.
_gd = os.path.join(ROOT, "o_grid_scope")
_gs = RB.run_batch(
    write_manifests(os.path.join(ROOT, "m_grid_scope"),
                    grids=GRIDS + [dict(Grid_ID="G_TIME", Factor_Name="ARM",
                                        Factor_Level="CONTROL", Level_Order=0,
                                        Note="duplicate level")]),
    _gd, file_root=ROOT, run_date="2026-08-06")
_gq = pd.read_csv(os.path.join(_gd, "qc_problems.csv"))
_g_scoped = any(str(w).startswith(("grid:", "grids:")) for w in _gq["where"])
if _g_scoped:
    _ga = pd.read_csv(os.path.join(_gd, "figure_values_machine_qc.csv"), dtype=object)
    _units_on_g_time = {u["Unit_ID"] for u in UNITS if u["Grid_ID"] == "G_TIME"}
    _units_elsewhere = {u["Unit_ID"] for u in UNITS if u["Grid_ID"] != "G_TIME"}
    check("a grid-grain problem blocks every unit declaring that grid",
          not (set(_ga["Unit_ID"]) & _units_on_g_time),
          "%s still accepted" % sorted(set(_ga["Unit_ID"]) & _units_on_g_time))
    # Inheritance is downward, not sideways. A unit on another grid was not
    # measured any less carefully because this one is broken.
    check("and leaves units on other grids alone",
          bool(set(_ga["Unit_ID"]) & _units_elsewhere) or not _units_elsewhere,
          "accepted=%s other=%s" % (sorted(set(_ga["Unit_ID"])), sorted(_units_elsewhere)))
else:
    check("a grid-grain problem blocks every unit declaring that grid",
          _gs["status"] == "MANIFEST_REJECTED", "%s" % _gs)

# The failure above was silent because an unknown prefix simply did not match.
# The next grain the gate grows must not repeat it.
_fake = pd.DataFrame([dict(where="constellations:2", check="INVENTED_SCOPE",
                           detail="a grain this function has never seen")])
_charged = RB._units_named_by(_fake, pd.DataFrame(), fr(UNITS, GE.fig_unit_columns()))
check("a QC scope nobody taught the runner condemns every unit",
      set(_charged) == {str(u["Unit_ID"]) for u in UNITS} and all(
          any(c.startswith("UNATTRIBUTED_QC_SCOPE") for c in codes)
          for codes in _charged.values()),
      "%s" % _charged)
check("every scope the gate emits is one the runner resolves",
      {"unit", "units", "values", "figures", "grids", "grid"} == set(RB.QC_SCOPES),
      "%s" % sorted(RB.QC_SCOPES))


print("the run mode belongs to the registry, not to the caller")
# The replay: run the demonstration, then hand its own manifests to the plain
# CLI. `run_mode` was an argument, so the promise stayed at the first call site
# and the files walked away without it - Status=RAN, Run_Mode=ATTESTED, same
# fictional reviewer. This fixture DOES accept values, which is the point.
_demo_reg = [dict(REVIEWERS[0], Reviewer_ID="RV_DEMO",
                  Reviewer_Name="Josiah Carberry",
                  Reviewer_Record_Type="DEMO_IDENTITY",
                  Contact_Type="ORCID",
                  Reviewer_Contact="0000-0002-1825-0097",
                  Registered_By="Josiah Carberry",
                  Human_Attestation="DEMO_EXAMPLE")]
_demo_mdir = write_manifests(
    os.path.join(ROOT, "m_demo_identity"), reviewers=_demo_reg,
    source_documents=[dict(SOURCE_DOCUMENTS[0], Reviewer_ID="RV_DEMO")],
    source_figures=[dict(f, Reviewer_ID="RV_DEMO") for f in SOURCE_FIGURES])

_replay = RB.run_batch(_demo_mdir, os.path.join(ROOT, "o_replay"),
                       file_root=ROOT, run_date="2026-08-06")
check("replaying a demo manifest set through the plain runner is still DEMO_ONLY",
      _replay["run_mode"] == "DEMO_ONLY", "%s" % _replay)
check("and its accepted values are refused, not written",
      _replay["status"] == "DEMO_OUTPUT_REFUSED" and _replay["would_accept"] > 0,
      "%s" % _replay)
check("and no accepted file survives the replay",
      RB.COMMIT_MARKER not in os.listdir(os.path.join(ROOT, "o_replay")),
      "%s" % sorted(os.listdir(os.path.join(ROOT, "o_replay"))))
check("and the stamp on the replay says DEMO_ONLY",
      json.load(open(os.path.join(ROOT, "o_replay", "run_stamp.json"))
                )["Run_Mode"] == "DEMO_ONLY")

_promote = RB.run_batch(_demo_mdir, os.path.join(ROOT, "o_promote"),
                        file_root=ROOT, run_date="2026-08-06",
                        run_mode="ATTESTED")
check("the caller cannot promote a demo identity to ATTESTED",
      _promote["status"] == "MANIFEST_REJECTED"
      and "RUN_MODE_REVIEWER_MISMATCH" in _promote["detail"], "%s" % _promote)
check("but the caller may still demote a real registry",
      RB.run_batch(_good, os.path.join(ROOT, "o_demote"), file_root=ROOT,
                   run_date="2026-08-06",
                   run_mode="DEMO_ONLY")["run_mode"] == "DEMO_ONLY")

check("a DEMO_IDENTITY row must not claim HUMAN_CONFIRMED",
      "REVIEWER_RECORD_TYPE_MISMATCH" in validate(
          reviewers=_reviewer(Reviewer_Record_Type="DEMO_IDENTITY",
                              Human_Attestation="HUMAN_CONFIRMED")),
      "%s" % validate(reviewers=_reviewer(Reviewer_Record_Type="DEMO_IDENTITY",
                                          Human_Attestation="HUMAN_CONFIRMED")))
check("a HUMAN row must not hide behind DEMO_EXAMPLE",
      "REVIEWER_RECORD_TYPE_MISMATCH" in validate(
          reviewers=_reviewer(Human_Attestation="DEMO_EXAMPLE")))
check("an invented record type is refused",
      "BAD_REVIEWER_RECORD_TYPE" in validate(
          reviewers=_reviewer(Reviewer_Record_Type="PROBABLY_REAL")))
check("a missing record type is refused",
      "MISSING_REQUIRED" in validate(reviewers=_reviewer(Reviewer_Record_Type="")))
check("a demo row nobody attested with does not demote the run",
      RB.run_batch(write_manifests(os.path.join(ROOT, "m_unused_demo"),
                                   reviewers=REVIEWERS + _demo_reg),
                   os.path.join(ROOT, "o_unused_demo"), file_root=ROOT,
                   run_date="2026-08-06")["run_mode"] == "ATTESTED")


print("a promotion that dies partway leaves nothing poolable")
# promote() moves files one at a time, so it is not atomic. What it can be is
# ORDERED: the accepted file goes last and works as a commit marker, and a
# failure withdraws it. The fault is injected rather than argued about.
_fault = os.path.join(ROOT, "o_fault")
RB.run_batch(_good, _fault, file_root=ROOT, run_date="2026-08-06")
_full = sorted(f for f in os.listdir(_fault) if os.path.isfile(os.path.join(_fault, f)))
check("a clean run commits the marker last and it is present",
      RB.COMMIT_MARKER in _full, "%s" % _full)
for _n in (1, 2, 3):
    _raised = None
    try:
        RB.run_batch(_good, _fault, file_root=ROOT, run_date="2026-08-07",
                     fault_after=_n)
    except Exception as exc:
        _raised = exc
    check("a fault after %d promoted files raises" % _n, _raised is not None)
    check("and leaves no accepted file to pool from (fault after %d)" % _n,
          not os.path.exists(os.path.join(_fault, RB.COMMIT_MARKER)),
          "the commit marker survived a failed promotion")
    check("and no staging directory (fault after %d)" % _n,
          not os.path.isdir(os.path.join(_fault, RB.STAGING)))
    _sp = os.path.join(_fault, "run_stamp.json")
    _sj = json.load(open(_sp)) if os.path.exists(_sp) else {}
    check("and a stamp saying PROMOTE_FAILED (fault after %d)" % _n,
          _sj.get("Status") == "PROMOTE_FAILED"
          and _sj.get("Values_Accepted") == 0,
          "no stamp at all" if not _sj else "%r" % _sj)
check("the marker is the values file a downstream reader would pool",
      RB.COMMIT_MARKER == "figure_values_machine_qc.csv", RB.COMMIT_MARKER)

# Ordering and withdrawal each cover the other, so neither is proven by the
# end-to-end runs above. Exercise them separately, on a directory of stubs.
_stage = os.path.join(ROOT, "promote_unit")
_dest = os.path.join(ROOT, "promote_dest")
for _d in (_stage, _dest):
    shutil.rmtree(_d, ignore_errors=True)
    os.makedirs(_d)
for _f in ("aaa_first.csv", RB.COMMIT_MARKER, "zzz_last.csv", "run_stamp.json"):
    open(os.path.join(_stage, _f), "w").write("stub")
_raised = None
# Two files in, deliberately: sorted() puts `figure_values_machine_qc.csv` SECOND
# among these stubs, so a run that promotes in listing order has already moved
# the marker by here and a run that orders it last has not. Faulting at one
# would pass either way and prove nothing.
try:
    RB.promote(_stage, _dest, fault_after=2)
except Exception as exc:
    _raised = exc
check("promote() raises when a move fails partway", _raised is not None)
check("and the commit marker was never moved, whatever the filenames sort to",
      os.path.exists(os.path.join(_stage, RB.COMMIT_MARKER))
      and not os.path.exists(os.path.join(_dest, RB.COMMIT_MARKER)),
      "the marker is not ordered last - alphabetical order put it first")
check("while the files that explain a result did move first",
      os.path.exists(os.path.join(_dest, "aaa_first.csv")))
open(os.path.join(_dest, RB.COMMIT_MARKER), "w").write("stub")
RB.withdraw_commit(_dest, "2026-08-06", "unit test")
check("withdraw_commit() removes a marker that did land",
      not os.path.exists(os.path.join(_dest, RB.COMMIT_MARKER)))
check("and leaves a PROMOTE_FAILED stamp behind it",
      json.load(open(os.path.join(_dest, "run_stamp.json")))["Status"]
      == "PROMOTE_FAILED")
# A promotion that silently loses a file must not commit either.
shutil.rmtree(_stage, ignore_errors=True)
os.makedirs(_stage)
open(os.path.join(_stage, RB.COMMIT_MARKER), "w").write("stub")
_orig_move = shutil.move


def _lossy_move(src, dst):
    if os.path.basename(src) == RB.COMMIT_MARKER:
        os.remove(src)                       # "moved" but never arrived
        return dst
    return _orig_move(src, dst)


shutil.move = _lossy_move
try:
    RB.promote(_stage, _dest)
    _lost = "committed anyway"
except Exception as exc:
    _lost = str(exc)
finally:
    shutil.move = _orig_move
check("a file that vanishes mid-promotion is caught by the verify pass",
      "missing" in _lost, _lost)
_recovered = RB.run_batch(_good, _fault, file_root=ROOT, run_date="2026-08-08")
check("a clean run after a failed promotion commits normally",
      _recovered["status"] == "RAN"
      and os.path.exists(os.path.join(_fault, RB.COMMIT_MARKER))
      and json.load(open(os.path.join(_fault, "run_stamp.json")))["Status"] == "RAN")


print("a value is judged by the panel that produced it, not by its unit's last")
check("every raw row names both its run panel and physical source panel",
      all(values["Run_Panel_ID"]) and all(values["Source_Panel_ID"]),
      "%s / %s" % (sorted(set(values["Run_Panel_ID"])),
                     sorted(set(values["Source_Panel_ID"]))))
check("and the run panel it names really ran",
      set(values["Run_Panel_ID"]) <= set(run["Panel_ID"]),
      "%s" % sorted(set(values["Run_Panel_ID"]) - set(run["Panel_ID"])))
check("and the physical panel exists in the source inventory",
      set(values["Source_Panel_ID"]) <= {r["Source_Panel_ID"] for r in SOURCE_PANELS})

# Two panels, one unit: the first cannot be read, the second reads cleanly.
# Keying panel state by Unit_ID let the second overwrite the first and the whole
# unit came out ACCEPTED - including the half nobody could read.
_split_panels = [
    panel("P_HALF_A", "U_SPLIT", "LINE_COLOR", BLANK_IMG, (100, 500, 40, 440)),
    panel("P_HALF_B", "U_SPLIT", "LINE_COLOR", LINE_IMG, (100, 500, 40, 440)),
]
_split_series = [series(p, s, lv, Colour_Hex=hx)
                 for p in ("P_HALF_A", "P_HALF_B")
                 for s, lv, hx in (("S_BLUE", "CONTROL", "#2d50dc"),
                                   ("S_RED", "TREATED", "#d72d2d"))]
_split_positions = [
    dict(Panel_ID=p, Position_ID=q, X_Pixel=x, Slot_Index=i, Display_Order=i,
         Factor_Name="TIMEPOINT", Factor_Level=q, Timepoint_Label=q,
         Timepoint_Days=i * 7, Note="")
    for p in ("P_HALF_A", "P_HALF_B") for i, (q, x) in enumerate(zip(POSITIONS, XS))]
_split_units = UNITS + [unit("U_SPLIT", "G_TIME", "CONTINUOUS")]
# P_HALF_A is drawn on BLANK_IMG and P_HALF_B on LINE_IMG, so they belong to
# different physical figures - which is the point of the fixture: one unit fed
# by two panels the reader treats independently.
_split_source_panels = SOURCE_PANELS + [dict(
    Source_Panel_ID=p, Source_Figure_ID=sf, Panel_Label=p,
    Outcome_Label="Heart rate", Target_Status="TARGET",
    Panel_Disposition="AUTO_DIGITIZE",
    Disposition_Reason="two-panel one-unit regression fixture", Note="")
    for p, sf in (("P_HALF_A", "SF4"), ("P_HALF_B", "SF1"))]
_mdir = write_manifests(os.path.join(ROOT, "m_split"),
                        panels=PANELS + _split_panels,
                        series_rows=SERIES + _split_series,
                        positions=POSITION_ROWS + _split_positions,
                        units=_split_units,
                        source_figures=[
                            dict(f, Observed_Panel_Count=2)
                            if f["Source_Figure_ID"] in ("SF1", "SF4") else f
                            for f in SOURCE_FIGURES],
                        source_panels=_split_source_panels)
_o = os.path.join(ROOT, "o_split")
_split_summary = RB.run_batch(_mdir, _o, file_root=ROOT, run_date="2026-08-06")
check("the two-panel-one-unit fixture actually ran",
      _split_summary["status"] == "RAN", "%s" % _split_summary)
_sr = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
_sraw = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
_sacc = pd.read_csv(os.path.join(_o, "figure_values_machine_qc.csv"),
                    dtype=object).fillna("")
_sstates = dict(zip(_sr["Panel_ID"], _sr["Run_State"]))
check("two panels of one unit keep two separate run rows",
      _sstates.get("P_HALF_A") and _sstates.get("P_HALF_B"), "%s" % _sstates)
check("the blank panel of the pair did not pass",
      _sstates.get("P_HALF_A") != "AUTO_PASS", "%s" % _sstates)
check("the readable panel's rows name the readable panel",
      set(_sraw[_sraw["Unit_ID"] == "U_SPLIT"]["Run_Panel_ID"]) == {"P_HALF_B"},
      "%s" % sorted(set(_sraw[_sraw["Unit_ID"] == "U_SPLIT"]["Run_Panel_ID"])))
check("and the unit is not silently accepted on the strength of one panel",
      not len(_sacc[_sacc["Unit_ID"] == "U_SPLIT"]),
      "%d rows accepted for a unit whose other panel could not be read"
      % len(_sacc[_sacc["Unit_ID"] == "U_SPLIT"]))


print("the run records what would have to match for it to be reproducible")
stamp = json.load(open(os.path.join(ODIR, "run_stamp.json")))
check("the stamp carries the reader version and the config hash",
      stamp["Reader_Version"] == MR.READER_VERSION and len(stamp["Config_SHA256"]) == 64)
# Compare against the constant, not a literal. Pinning "7.7" here meant the
# scenario failed on the next version bump for no reason a reader could act on -
# a test that has to be edited every release teaches people to edit tests.
check("the stamp distinguishes pipeline revisions from reader revisions",
      stamp["Pipeline_Version"] == RB.PIPELINE_VERSION
      and stamp["Pipeline_Version"] != stamp["Reader_Version"]
      and len(stamp["Pipeline_Code_SHA256"]) == 64,
      "pipeline %r vs reader %r" % (stamp.get("Pipeline_Version"),
                                    stamp.get("Reader_Version")))
check("the stamp hashes every input manifest",
      set(stamp["Manifest_SHA256"])
      == set(RB.MANIFEST_FILES) | set(RB.OPTIONAL_MANIFEST_FILES),
      "%s" % sorted(stamp["Manifest_SHA256"]))
# The optional one included, and this batch has no identity_resolution.csv at
# all. A file that may be absent still has to be hashed when it is there - a
# resolution that can be edited after the values were approved silently
# re-labels a series between the review and the pool - and the only way to hash
# "it was absent" is to hash the empty frame the loader substitutes. So the
# stamp records a digest for it either way, and an added file changes the
# fingerprint that every approval is bound to.
check("including the one that may be absent, so adding it later is visible",
      "resolutions" in stamp["Manifest_SHA256"]
      and len(stamp["Manifest_SHA256"]["resolutions"]) == 64,
      "%r" % stamp["Manifest_SHA256"].get("resolutions"))

# REVERT: drop "mono_bar_geometry.py" from PIPELINE_CODE_FILES. Every other
# scenario in this file still passes, because the hash is still 64 hex
# characters and still changes whenever run_batch.py does. What breaks is the
# only thing the stamp is for: that module holds the WHOLE monochrome bar
# measurement - stroke, footprint, extent, cap, texture - so the function
# deciding where a bar top is could be rewritten between two batches and the
# stamp would say the two runs were produced by identical code.
#
# The list is derived here rather than typed out again: a hand-written second
# copy of the same names agrees with the first by construction and catches
# nothing. What this walks is what run_batch actually IMPORTS.
_seen, _reachable = set(), []
_stack = ["run_batch"]
while _stack:
    _name = _stack.pop()
    if _name in _seen:
        continue
    _seen.add(_name)
    _mod = sys.modules.get(_name)
    if _mod is None or not getattr(_mod, "__file__", None):
        continue
    if os.path.dirname(os.path.abspath(_mod.__file__)) != HERE:
        continue                       # numpy, pandas, the standard library
    _reachable.append(os.path.basename(_mod.__file__))
    for _obj in vars(_mod).values():
        if isinstance(_obj, types.ModuleType):
            _stack.append(_obj.__name__)
_unhashed = sorted(set(_reachable) - set(RB.PIPELINE_CODE_FILES))
check("every module of this package that run_batch reaches is in the hash",
      not _unhashed, "not hashed: %r" % _unhashed)
check("and mono_bar_geometry - the whole monochrome bar measurement - is one",
      "mono_bar_geometry.py" in RB.PIPELINE_CODE_FILES,
      repr(RB.PIPELINE_CODE_FILES))
# Not "the hash is 64 characters" but "editing this file moves it". One byte,
# in a comment, in the module that was missing.
_geo_path = os.path.join(HERE, "mono_bar_geometry.py")
_before = RB.pipeline_code_sha256()
with open(_geo_path, "rb") as _fh:
    _original = _fh.read()
try:
    with open(_geo_path, "wb") as _fh:
        _fh.write(_original + b"\n# one byte\n")
    _after = RB.pipeline_code_sha256()
finally:
    with open(_geo_path, "wb") as _fh:
        _fh.write(_original)
check("changing one byte of the bar measurement changes the pipeline hash",
      _after != _before, "%s ... %s" % (_before[:16], _after[:16]))
check("and putting it back puts the hash back",
      RB.pipeline_code_sha256() == _before)
check("each run row carries the image hash it read",
      all(len(h) == 64 for h in run["Image_SHA256"] if h), "%s" % list(run["Image_SHA256"]))

ODIR2 = os.path.join(ROOT, "out2")
RB.run_batch(MDIR, ODIR2, file_root=ROOT, run_date="2026-08-06")
_same = []
for name in ("figure_values_raw.csv", "figure_values_machine_qc.csv",
             "run_manifest.csv", "manual_queue.csv", "qc_problems.csv"):
    # The output directory is embedded in the paths a run writes, so compare the
    # runs with their own root removed. Everything else must match exactly.
    _a = open(os.path.join(ODIR, name)).read().replace(ODIR, "<OUT>")
    _b = open(os.path.join(ODIR2, name)).read().replace(ODIR2, "<OUT>")
    _same.append((name, _a == _b))
check("a second run over the same inputs is identical but for its own path",
      all(ok for _, ok in _same), "%s" % [n for n, ok in _same if not ok])
_p1 = MR.read_point_data(RB.resolve_artifact(ODIR, _scat["Point_Data_Reference"]))
_p2 = MR.read_point_data(RB.resolve_artifact(ODIR2, _scat["Point_Data_Reference"]))
check("and the point clouds it wrote are identical pixel for pixel",
      _p1["points"] == _p2["points"])
_changed = json.load(open(os.path.join(ODIR2, "run_stamp.json")))
# Every field but the ones that ARE the output directory. `Output_SHA256` hashes
# files whose rows carry absolute paths, so two runs into two directories
# legitimately differ there - and comparing them anyway would have quietly
# turned this into a test that the paths are equal.
_ignore = {"Output_SHA256"}
check("and its stamp agrees",
      {k: v for k, v in _changed.items() if k not in _ignore}
      == {k: v for k, v in stamp.items() if k not in _ignore},
      "%s" % sorted(k for k in set(_changed) | set(stamp)
                    if k not in _ignore and _changed.get(k) != stamp.get(k)))
check("and the hashes it recorded are of the files it actually wrote",
      all(RB.sha256_of_text(open(os.path.join(ODIR2, n), encoding="utf-8").read())
          == h for n, h in _changed["Output_SHA256"].items()),
      "%s" % sorted(_changed["Output_SHA256"]))

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
      and not os.path.exists(os.path.join(ODIR3, "figure_values_raw.csv"))
      and not os.path.exists(os.path.join(ODIR3, "figure_values_machine_qc.csv")))

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
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
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
# PANEL_GEOMETRY_UNRESOLVED, with the geometry pass's own reason on it. It was
# MANUAL_POINT_READ - "the reader resolved no marks in this panel" - which is
# true and useless: the reasons were on the geometry rows and only findable by
# opening mono_bar_geometry.csv.
_lr = dict(zip(_r["Panel_ID"], _r["Run_State"]))
check("a bar reader pointed at a line panel says what it could not find",
      _lr["P_LINE"] == "PANEL_GEOMETRY_UNRESOLVED", "%s" % _lr)
check("and names it, rather than reporting an empty panel",
      "UNRESOLVED" in dict(zip(_r["Panel_ID"], _r["Detail"]))["P_LINE"],
      "%s" % dict(zip(_r["Panel_ID"], _r["Detail"]))["P_LINE"])
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
check("and it invents no bars from the line markers",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))

print("a fill the manifest declares and the reader can now read")
# STIPPLED is in the manifest vocabulary because publication 127 prints it and
# a manifest that cannot say so forces its author to declare the nearest lie.
# The reader refuses it - and WHICH refusal it raises decides what the audit
# record says. A plain ValueError maps to PANEL_GEOMETRY_UNRESOLVED, which would
# put "this reader has no STIPPLED" on the record as "this panel's geometry
# cannot be trusted": fail-closed with the wrong reason, which is the kind of
# thing a reviewer acts on and a maintainer chases.
#
# REVERT: raise ValueError from the UNIMPLEMENTED_FILL_PATTERNS branch in
# mark_readers. The state below becomes PANEL_GEOMETRY_UNRESOLVED and every
# other assertion in this scenario still passes.
_stipple_series = [
    dict(r, Colour_Hex="",
         Bar_Fill_Pattern=("SOLID" if r["Series_ID"] == "S_BLUE" else "STIPPLED"))
    if r["Panel_ID"] == "P_LINE" else r for r in SERIES]
_stip = write_manifests(
    os.path.join(ROOT, "m_stipple"),
    panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="BAR_MONO",
                  Config_ID="C_BARMONO"),
    series_rows=_stipple_series,
    configs=CONFIGS + [dict(Config_ID="C_BARMONO", Option="threshold",
                            Value="150", Note="")])
_o = os.path.join(ROOT, "o_stipple")
_ss = RB.run_batch(_stip, _o, file_root=ROOT, run_date="2026-08-06")
check("a batch declaring a stipple still runs", _ss["status"] == "RAN",
      "%s" % _ss)
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
_st = dict(zip(_r["Panel_ID"], _r["Run_State"]))
# This scenario used to assert NO_READER_AVAILABLE, and it was right to: the
# old reader classified fills by absolute density and STIPPLED had no band, so
# a stippled bar would have been assigned to whichever band it fell in.
# `read_monochrome_bar_geometry` reads stipples - "some rows of the interior
# are blank" is a structural property, not a density - so the refusal is gone
# and declaring STIPPLED is no longer declaring the unreadable. What is left
# here is a bar reader pointed at a LINE panel, which finds no bars.
#
# REVERT: point BAR_MONO back at `read_monochrome_bar_panel`. The state below
# becomes NO_READER_AVAILABLE again, and publication 127 - three panels of
# OPEN/STIPPLED/SOLID - goes back to being unreadable by this pipeline.
check("a stipple is no longer a fill the pipeline refuses",
      _st.get("P_LINE") == "PANEL_GEOMETRY_UNRESOLVED", "%s" % _st)
check("and the other panels in the batch are unaffected",
      _st.get("P_SCAT") == "AUTO_PASS", "%s" % _st)
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
check("no values are invented for the unreadable fill",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))
check("STIPPLED is declarable in the manifest vocabulary",
      "STIPPLED" in BM.BAR_FILL_PATTERNS, "%s" % (BM.BAR_FILL_PATTERNS,))
# `UNIMPLEMENTED_FILL_PATTERNS` still says STIPPLED, and still should: it is
# `read_monochrome_bar_panel`'s limitation and that reader still has it. What
# changed is which reader BAR_MONO goes to.
check("the old reader still refuses it, and is no longer the one BAR_MONO uses",
      "STIPPLED" in MR.UNIMPLEMENTED_FILL_PATTERNS
      and RB.reader_functions()["BAR_MONO"] is not MR.read_monochrome_bar_panel,
      "%s" % (RB.reader_functions()["BAR_MONO"],))

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
# Swapping the raster under a panel means swapping the physical figure it is a
# panel of - the hash chain will not let the two drift apart, which is what it
# is for.
_sparse = write_manifests(
    os.path.join(ROOT, "m_sparse"),
    panels=edited(PANELS, {"Panel_ID": "P_SCAT"}, Image_Path=_sparse_img),
    source_figures=edited(SOURCE_FIGURES, {"Source_Figure_ID": "SF2"},
                          Source_Image=_sparse_img,
                          Source_Image_SHA256=MR.sha256_of(_sparse_img)))
_o = os.path.join(ROOT, "o_sparse")
RB.run_batch(_sparse, _o, file_root=ROOT, run_date="2026-08-06")
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
check("a cloud too sparse to summarize is NOT_CONVERTIBLE, not a shaky r",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_SCAT"] == "NOT_CONVERTIBLE",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))

print("an automated extraction is re-openable by hand")
_proj = {p: RB.resolve_artifact(ODIR, v) if v else ""
         for p, v in zip(run["Panel_ID"], run["WPD_Project_File"])}
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

print("a mark type with no reader is queued, not treated as a bad manifest")
# One panel nobody can read yet must not stop every panel that can be. On
# publication 397 that was two line figures against twenty-four readable bar
# cells - rejecting the batch would have cost the twenty-four.
_unreleased_series = [
    dict(r, Colour_Hex="", Marker_Shape="NONE",
         Line_Style=("SOLID" if r["Series_ID"] == "S_BLUE" else "DASHED"))
    if r["Panel_ID"] == "P_LINE" else r for r in SERIES]
_ur = write_manifests(
    os.path.join(ROOT, "m_unreleased"),
    panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="LINE_MONO_STYLE",
                  Config_ID=""),
    series_rows=_unreleased_series)
_o = os.path.join(ROOT, "o_unreleased")
_su = RB.run_batch(_ur, _o, file_root=ROOT, run_date="2026-08-06")
check("a batch containing an unreleased mark type still runs",
      _su["status"] == "RAN", "%s" % _su)
_r = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
_st = dict(zip(_r["Panel_ID"], _r["Run_State"]))
check("the unreleased panel is NO_READER_AVAILABLE, not a manifest error",
      _st.get("P_LINE") == "NO_READER_AVAILABLE", "%s" % _st)
check("and the readable panels in the same batch still pass",
      _st.get("P_SCAT") == "AUTO_PASS", "%s" % _st)
_q = pd.read_csv(os.path.join(_o, "manual_queue.csv"), dtype=object).fillna("")
_qrow = _q[_q["Panel_ID"] == "P_LINE"]
check("its queue row names the cells nobody can read yet",
      len(_qrow) and int(_qrow.iloc[0]["Missing_Cell_Count"]) > 0,
      "%s" % (list(_qrow["Missing_Cell_Count"]) if len(_qrow) else "no queue row"))
check("and says why, pointing at where the work stands",
      len(_qrow) and "wip/" in _qrow.iloc[0]["Detail"],
      "%s" % (list(_qrow["Detail"]) if len(_qrow) else ""))
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
check("it contributes no values at all",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))
check("NO_READER_AVAILABLE is in the declared state vocabulary",
      "NO_READER_AVAILABLE" in BM.RUN_STATES)


# ---------------------------------------------------------------------------
# The four artifacts a BAR_MONO geometry review needs, written as one bundle.
#
# An overlay is a review AID: a panel with values and no picture is still
# reviewable through its WPD project, so `draw_panel_overlay` never raises.
# These are the review ITSELF - the numbers, the pictures and the index tying
# them together - and a panel missing one of them cannot be approved at all.
#
# REVERT: log a failure and carry on, the way the overlay does. The run then
# queues a panel whose approval has nothing to be an approval of, and the
# finalizer discovers it after a person has already typed APPROVED.
print()
print("a BAR_MONO geometry review is four artifacts or it is not a review")
_gt = json.load(open(os.path.join(HERE, "mono_bar_fixture_truth.json"),
                     encoding="utf-8"))
_gimg = os.path.join(HERE, "mono_bar_fixture.png")
_grows = MR.read_monochrome_bar_geometry(
    Image.open(_gimg), tuple(_gt["panel_box"]),
    dict(zip(_gt["groups"], _gt["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _gt["y_ticks"]]),
    _gt["patterns"], group_window=60, panel_id="P_GEO", figure_id="F_GEO")
_gdir = os.path.join(ROOT, "geo_review")
os.makedirs(_gdir, exist_ok=True)
try:
    RB.write_geometry_review(_gdir, [(_gimg, r) for r in _grows])
    _exc = None
except Exception as _caught:                 # deliberately broad - see below
    _exc = _caught
check("the bundle refuses rows the figure has not answered",
      _exc is not None and "AUTO_IDENTITY_MISSING" in str(_exc),
      "it wrote a geometry file before the identities existed"
      if _exc is None else str(_exc))
# And refuses it under its OWN exception type. `canonical_artifact_rows` and
# `verify_artifact` raise ValueError, `run_batch` catches GeometryReviewError,
# so a bare ValueError from the writer leaves the runner as an unhandled
# exception - the caller cannot tell "this bundle cannot be written" from a
# defect. Caught as `Exception` above so this reads as a failed scenario rather
# than a traceback that stops the file.
check("and under its own exception type, so the runner can catch it",
      isinstance(_exc, RB.GeometryReviewError), "%r" % (_exc,))
RB.MONO_GEOMETRY.fill_identities_by_figure(_grows)
_gart = RB.write_geometry_review(_gdir, [(_gimg, r) for r in _grows])
check("every panel it covers gets all four artifact types",
      set(_gart) == {"P_GEO"}
      and [t for t, _p in _gart["P_GEO"]][:4]
      == list(RB.GEOMETRY_ARTIFACT_TYPES),
      "%s" % {k: [t for t, _p in v] for k, v in _gart.items()})
# REVERT: register the four and stop. The index links to a picture per ROW and
# the finalizer re-hashes only what the ledger names, so a row crop left out of
# it can be swapped for a picture of a different bar and the approval still
# verifies. There is no count to declare - a panel has as many as it has rows -
# which is why it is a type of its own rather than a fifth fixed entry.
_crops = [p for t, p in _gart["P_GEO"]
          if t == RB.GEOMETRY_ROW_ARTIFACT_TYPE]
check("and one registered picture per geometry row, by name",
      len(_crops) == len(_grows)
      and sorted(os.path.basename(p) for p in _crops)
      == sorted(RB.OVERLAY.row_crop_name(r) for r in _grows),
      "%d crops for %d rows" % (len(_crops), len(_grows)))
check("every row crop the ledger names links from the index",
      all(os.path.basename(p) in open(
          dict(_gart["P_GEO"])["GEOMETRY_REVIEW_INDEX"],
          encoding="utf-8").read() for p in _crops))
check("and every one of them is a file that exists",
      all(os.path.exists(p) for _t, p in _gart["P_GEO"]),
      "%s" % [(t, os.path.exists(p)) for t, p in _gart["P_GEO"]])
_gcsv = dict(_gart["P_GEO"])["MONO_BAR_GEOMETRY"]
with open(_gcsv, encoding="utf-8") as _fh:
    _gback = list(csv.DictReader(_fh))
check("the numbers file is canonical and verifies on the way back in",
      len(_gback) == len(_grows)
      and len(RB.MONO_GEOMETRY.verify_artifact(_gback)["records"]) == len(_grows),
      "%d rows" % len(_gback))
check("the index names the panel picture beside the rows",
      "panel__P_GEO.png" in open(dict(_gart["P_GEO"])["GEOMETRY_REVIEW_INDEX"],
                                 encoding="utf-8").read())
_gmeta = json.load(open(dict(_gart["P_GEO"])["CALIBRATION_PANEL_META"],
                        encoding="utf-8"))
check("and the panel metadata carries the points somebody typed",
      [t["value"] for t in _gmeta["declared_calibration_points"]]
      == [v for v, _p in _gt["y_ticks"]],
      "%s" % _gmeta["declared_calibration_points"])
# REVERT: return the artifacts that could be written. A panel whose picture
# failed then reaches the queue declaring a review nobody can perform.
_real_panel_draw = RB.OVERLAY.draw_panel_geometry
try:
    RB.OVERLAY.draw_panel_geometry = lambda *a, **k: None
    _broke = os.path.join(ROOT, "geo_broken")
    try:
        RB.write_geometry_review(_broke, [(_gimg, r) for r in _grows])
    except RB.GeometryReviewError as _exc:
        check("a panel whose picture could not be drawn is refused, not queued",
              "panel__P_GEO.png" in str(_exc), str(_exc))
    else:
        check("a panel whose picture could not be drawn is refused, not queued",
              False, "it returned a bundle")
finally:
    RB.OVERLAY.draw_panel_geometry = _real_panel_draw
# REVERT: leave the bundle off CANONICAL_OUTPUTS/CANONICAL_DIRS. A second run
# into the same directory then keeps the first run's panel pictures and row
# crops, and the writer's existence check passes on them - so an approval can
# be given against a picture of a different measurement.
check("the geometry bundle is on the cleanup list, both halves",
      "mono_bar_geometry.csv" in RB.CANONICAL_OUTPUTS
      and "geometry-review" in RB.CANONICAL_DIRS,
      "%r %r" % (RB.CANONICAL_OUTPUTS[-2:], RB.CANONICAL_DIRS))
_stale = os.path.join(ROOT, "geo_stale")
os.makedirs(os.path.join(_stale, "geometry-review"), exist_ok=True)
with open(os.path.join(_stale, "geometry-review", "panel__P_GEO.png"), "w") as _fh:
    _fh.write("a picture from a previous run")
with open(os.path.join(_stale, "mono_bar_geometry.csv"), "w") as _fh:
    _fh.write("numbers from a previous run")
RB.clear_outputs(_stale)
check("and a new run removes both before it starts",
      not os.path.exists(os.path.join(_stale, "mono_bar_geometry.csv"))
      and not os.path.isdir(os.path.join(_stale, "geometry-review")),
      "%r" % sorted(os.listdir(_stale)))
# REVERT: `OVERLAY.reset_failures()` inside write_geometry_review. The run's
# overlay log is global, so a helper that clears it erases every panel overlay
# failure that happened before it - and the run reports a clean drawing pass it
# did not have.
RB.OVERLAY.reset_failures()
RB.OVERLAY._FAILURES.append("P_EARLIER: an overlay that could not be drawn")
RB.write_geometry_review(os.path.join(ROOT, "geo_keep"),
                         [(_gimg, r) for r in _grows])
check("writing the bundle does not erase the run's earlier drawing failures",
      any("P_EARLIER" in f for f in RB.OVERLAY.failures()),
      "%r" % RB.OVERLAY.failures())
RB.OVERLAY.reset_failures()
# REVERT: drop review_crop_box from the successor's signature. A caller with
# Axis_X_Region and Axis_Y_Region in hand then has to bypass the shared entry
# point and call geometry_rows directly, which is most of why it exists.
import inspect as _inspect                                          # noqa: E402
check("the reader BAR_MONO now dispatches to can be told where the axis is",
      "review_crop_box" in _inspect.signature(
          RB.reader_functions()["BAR_MONO"]).parameters
      and "review_crop_box" not in BM.READER_OPTIONS,
      repr(sorted(_inspect.signature(
          RB.reader_functions()["BAR_MONO"]).parameters)))
_boxed = MR.read_monochrome_bar_geometry(
    Image.open(_gimg), tuple(_gt["panel_box"]),
    dict(zip(_gt["groups"], _gt["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _gt["y_ticks"]]),
    _gt["patterns"], group_window=60, review_crop_box=[10, 20, 30, 40],
    panel_id="P_GEO", figure_id="F_GEO")
check("and it reaches the record, so the picture can use it",
      all(r.get("review_crop_box") == [10, 20, 30, 40] for r in _boxed),
      repr(_boxed[0].get("review_crop_box")))

check("the artifact types are declared, not spelled at each call site",
      RB.GEOMETRY_ARTIFACT_TYPES
      == ("MONO_BAR_GEOMETRY", "GEOMETRY_REVIEW_INDEX", "CALIBRATION_PANEL",
          "CALIBRATION_PANEL_META"))


# ---------------------------------------------------------------------------
# A BAR_MONO panel that actually reads, driven from manifests.
#
# Every BAR_MONO scenario above this point either calls the reader directly or
# points it at a raster with no bars in it, so the whole runner path - the
# pre-pass, the review bundle, the refusal branches, the cleanup - was only
# ever exercised on a panel that returned nothing. The four checks that follow
# are about what the runner does with a panel that returns TWELVE things, and
# none of them can be written against a panel that returns none.
# ---------------------------------------------------------------------------
print()
print("a monochrome bar panel read end to end from its manifests")
MONO_IMG = os.path.join(IMAGES, "mono.png")
shutil.copyfile(os.path.join(HERE, "mono_bar_fixture.png"), MONO_IMG)
_MONO_BOX = tuple(_gt["panel_box"])
# Where the printed axis lives, in the manifest's own words. The y labels sit
# left of the plot box and the x labels below it; both are outside `_MONO_BOX`,
# which is the point of declaring them.
_MONO_YREG = "30,%d,%d,%d" % (_MONO_BOX[0], _MONO_BOX[2], _MONO_BOX[3])
_MONO_XREG = "%d,%d,%d,470" % (_MONO_BOX[0], _MONO_BOX[1], _MONO_BOX[3])
_MONO_FILLS = ("SOLID", "HATCHED", "OPEN")
_MONO_ARMS = dict(zip(_MONO_FILLS, ("PRE", "EARLY", "LATE")))
_mono_figure = dict(
    Figure_ID="F_MONO", Publication_ID=1, Figure_Number="FIG5",
    Source_File="synthetic.pdf", Source_Page=1, Source_Image=MONO_IMG,
    Source_Caption_Verbatim="synthetic monochrome bar panel",
    Image_Resolution_Or_Hash="sha256:" + MR.sha256_of(MONO_IMG),
    WPD_Project_File="", Observed_Panel_Count=1, Worklist_Panel_Count=1,
    Unlisted_Panels="", Panel_Reconciliation_Status="MATCHED", Note="")
_mono_source_figure = dict(
    Source_Figure_ID="SF_MONO", Source_Document_ID="SD1", Publication_ID=1,
    Figure_Number="FIG5", Source_File="synthetic.pdf", Source_Page=1,
    Source_Image=MONO_IMG, Source_Image_SHA256=MR.sha256_of(MONO_IMG),
    Observed_Panel_Count=1, Inventory_Status="VISUALLY_VERIFIED",
    Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="one monochrome axes region")
_mono_source_panel = dict(
    Source_Panel_ID="P_MONO", Source_Figure_ID="SF_MONO", Panel_Label="P_MONO",
    Outcome_Label="Stroke volume", Target_Status="TARGET",
    Panel_Disposition="AUTO_DIGITIZE",
    Disposition_Reason="synthetic monochrome fixture", Note="")
_mono_grids = GRIDS + (
    [dict(Grid_ID="G_MONO", Factor_Name="ARM", Factor_Level=lv, Level_Order=i,
          Note="") for i, lv in enumerate(("PRE", "EARLY", "LATE"))]
    + [dict(Grid_ID="G_MONO", Factor_Name="TIMEPOINT", Factor_Level=lv,
            Level_Order=i, Note="") for i, lv in enumerate(_gt["groups"])])
# Stroke volume, not the heart rate every other unit in the fixture carries:
# the fixture's shortest bar is 27, and 27 bpm is outside the plausibility
# range for a heart rate - correctly. The gate is not the thing under test here.
_mono_unit = unit("U_MONO", "G_MONO", "CONTINUOUS", Figure_ID="F_MONO",
                  Panel="U_MONO", Bar_Top_Definition="OUTLINE_CENTER",
                  Outcome_Variable="Stroke volume", Unit="ml",
                  Axis_Calib_Y1_Value=_gt["y_ticks"][0][0],
                  Axis_Calib_Y1_Pixel=_gt["y_ticks"][0][1],
                  Axis_Calib_Y2_Value=_gt["y_ticks"][1][0],
                  Axis_Calib_Y2_Pixel=_gt["y_ticks"][1][1])
_mono_panel = panel("P_MONO", "U_MONO", "BAR_MONO", MONO_IMG, _MONO_BOX,
                    Figure_ID="F_MONO", Config_ID="",
                    Axis_X_Region=_MONO_XREG, Axis_Y_Region=_MONO_YREG,
                    Axis_Y_Ticks=";".join("%g:%g" % (v, p)
                                          for v, p in _gt["y_ticks"]))
_mono_series = [series("P_MONO", "S_%s" % f, _MONO_ARMS[f], Bar_Fill_Pattern=f)
                for f in _MONO_FILLS]
_mono_positions = [
    dict(Panel_ID="P_MONO", Position_ID=q, X_Pixel=x, Slot_Index=i,
         Display_Order=i, Factor_Name="TIMEPOINT", Factor_Level=q,
         Timepoint_Label=q, Timepoint_Days=i * 7, Note="")
    for i, (q, x) in enumerate(zip(_gt["groups"], _gt["group_x"]))]


def mono_manifests(directory, **kw):
    """The four-panel fixture batch plus one readable monochrome bar panel."""
    fields = dict(
        panels=PANELS + [_mono_panel], series_rows=SERIES + _mono_series,
        positions=POSITION_ROWS + _mono_positions,
        units=UNITS + [_mono_unit], figures=FIGURES + [_mono_figure],
        grids=_mono_grids, source_figures=SOURCE_FIGURES + [_mono_source_figure],
        source_panels=SOURCE_PANELS + [_mono_source_panel],
        source_documents=[dict(SOURCE_DOCUMENTS[0], Observed_Figure_Count=5)])
    fields.update(kw)
    return write_manifests(directory, **fields)


_mm = mono_manifests(os.path.join(ROOT, "m_monoreal"))
_mo = os.path.join(ROOT, "o_monoreal")
_ms = RB.run_batch(_mm, _mo, file_root=ROOT, run_date="2026-08-06")
check("the batch runs", _ms["status"] == "RAN", "%s" % _ms)
_mr = pd.read_csv(os.path.join(_mo, "run_manifest.csv"), dtype=object).fillna("")
_mrow = _mr[_mr["Panel_ID"] == "P_MONO"]
check("and the monochrome panel passes automatically",
      len(_mrow) and _mrow.iloc[0]["Run_State"] == "AUTO_PASS",
      "%s" % (list(_mrow["Run_State"]) + list(_mrow["Detail"]) if len(_mrow)
              else "no row"))
check("with all twelve declared cells read",
      len(_mrow) and _mrow.iloc[0]["Cells_Declared"] == "12"
      and _mrow.iloc[0]["Cells_Read"] == "12",
      "%s" % (list(zip(_mrow["Cells_Declared"], _mrow["Cells_Read"]))
              if len(_mrow) else "no row"))
_mv = pd.read_csv(os.path.join(_mo, "figure_values_raw.csv"),
                  dtype=object).fillna("")
_mv = _mv[_mv["Unit_ID"] == "U_MONO"]
_worst = 0.0
for _f in _MONO_FILLS:
    for _q in _gt["groups"]:
        _hit = _mv[_mv["Cell_Key"] == "ARM=%s;TIMEPOINT=%s" % (_MONO_ARMS[_f], _q)]
        if not len(_hit):
            _worst = float("inf")
            continue
        _worst = max(_worst, abs(float(_hit.iloc[0]["Mean"])
                                 - _gt["series"][_f][_q]["mean"]))
check("and every value lands on the bar the figure drew, not near it",
      _worst < 0.6, "worst error %s units" % _worst)

# REVERT: pass no `review_crop_box` from `measure_bar_mono_figures`. The crop
# falls back to a fraction of the plot box, `crop_source` reads ESTIMATED, and
# the picture a reviewer approves against no longer contains the printed
# numbers the calibration was read off - which is the one error arithmetic
# cannot catch, because a misread tick VALUE rescales every bar in the panel
# self-consistently.
_mmeta = json.load(open([
    os.path.join(_mo, "geometry-review", f)
    for f in sorted(os.listdir(os.path.join(_mo, "geometry-review")))
    if f.startswith("panel__P_MONO") and f.endswith(".json")][0],
    encoding="utf-8"))
check("the panel picture is cropped to the axis the MANIFEST declared",
      _mmeta["crop_source"] == "DECLARED", "%s" % _mmeta["crop_source"])
# The exact rectangle, because the estimate is not far off - it is a fraction
# of the plot box, and on THIS panel it happens to reach further left than the
# declared y region does. "The crop is wide enough" therefore passes either
# way; what distinguishes them is whose rectangle it is.
_want_crop = [max(0, min(30, _MONO_BOX[0]) - 24),
              max(0, min(_MONO_BOX[2], _MONO_BOX[2]) - 24),
              min(Image.open(MONO_IMG).width, max(_MONO_BOX[1], _MONO_BOX[1]) + 24),
              min(Image.open(MONO_IMG).height, max(470, _MONO_BOX[3]) + 24)]
check("and the rectangle is the declared one, not a fraction of the plot box",
      _mmeta["crop_box"] == _want_crop,
      "%s, from y-region %s and x-region %s, wanted %s"
      % (_mmeta["crop_box"], _MONO_YREG, _MONO_XREG, _want_crop))
check("a panel with no regions declared says the crop was estimated",
      RB._review_crop(dict(Axis_X_Region="", Axis_Y_Region=""),
                      list(_MONO_BOX)) is None)
# A declared region that does not parse refuses the panel. Ignored, the field a
# person filled in is silently not the field the picture used.
_bad_region = mono_manifests(
    os.path.join(ROOT, "m_monobadregion"),
    panels=PANELS + [dict(_mono_panel, Axis_Y_Region="left of the bars")])
_bo = os.path.join(ROOT, "o_monobadregion")
_bs = RB.run_batch(_bad_region, _bo, file_root=ROOT, run_date="2026-08-06")
_br = pd.read_csv(os.path.join(_bo, "run_manifest.csv"), dtype=object).fillna("")
_brow = _br[_br["Panel_ID"] == "P_MONO"]
check("an axis region that does not parse refuses the panel by name",
      len(_brow) and _brow.iloc[0]["Run_State"] == "PANEL_GEOMETRY_UNRESOLVED"
      and "Axis_Y_Region" in _brow.iloc[0]["Detail"],
      "%s" % (list(zip(_brow["Run_State"], _brow["Detail"])) if len(_brow)
              else "no row"))
# REVERT: return the refusal from the panel LOOP instead of inside `run_panel`.
# The outcome then carries Cells_Declared=0 and no missing cells, so twelve
# unread cells are reported as "0 of 0" and nothing is queued for them.
check("and still counts the cells it did not read",
      len(_brow) and _brow.iloc[0]["Cells_Declared"] == "12"
      and _brow.iloc[0]["Cells_Read"] == "0",
      "%s" % (list(zip(_brow["Cells_Declared"], _brow["Cells_Read"]))
              if len(_brow) else "no row"))
_bq = pd.read_csv(os.path.join(_bo, "manual_queue.csv"), dtype=object).fillna("")
_bq = _bq[_bq["Panel_ID"] == "P_MONO"]
check("and queues all twelve of them for a person",
      len(_bq) and _bq.iloc[0]["Missing_Cell_Count"] == "12",
      "%s" % (list(_bq["Missing_Cell_Count"]) if len(_bq) else "no queue row"))

# REVERT: remove three named directories in the DEMO branch instead of calling
# `clear_outputs`. `mono_bar_geometry.csv` and `geometry-review/` are not among
# them, so a run that refused to write a single value leaves twelve means,
# twelve dispersions and their auto identities on disk under a demonstration
# reviewer.
_md = os.path.join(ROOT, "o_monodemo")
_mds = RB.run_batch(_mm, _md, file_root=ROOT, run_date="2026-08-06",
                    run_mode="DEMO_ONLY")
check("a DEMO_ONLY run over a readable bar panel is refused",
      _mds["status"] == "DEMO_OUTPUT_REFUSED" and _mds["would_accept"] > 0,
      "%s" % _mds)
check("and the measurements go with the values it refused to write",
      sorted(os.listdir(_md)) == ["run_stamp.json"], "%s" % sorted(os.listdir(_md)))

# REVERT: drop the GEOMETRY_REVIEW_FAILED branch from `main`. The status is
# real - the run stops before there are any states, qc problems or queue rows -
# and the summary print below it reads all three, so the run reaches a person
# as a KeyError traceback instead of a sentence about the review bundle.
_real_panel_draw2 = RB.OVERLAY.draw_panel_geometry


def _draw_refuses(*a, **kw):
    raise ValueError("the panel picture could not be drawn")


_gf = os.path.join(ROOT, "o_monogeofail")
RB.OVERLAY.draw_panel_geometry = _draw_refuses
try:
    _code, _crash = RB.main([_mm, _gf, "--file-root", ROOT,
                             "--date", "2026-08-06"]), None
except Exception as _caught:     # broad on purpose: a crash IS the failure
    _code, _crash = None, _caught
finally:
    RB.OVERLAY.draw_panel_geometry = _real_panel_draw2
check("a review bundle that cannot be written is a run status, not a traceback",
      _code == 5, "exit %r%s" % (_code, "" if _crash is None
                                 else ", raised %r" % (_crash,)))
_gstamp = json.load(open(os.path.join(_gf, "run_stamp.json"), encoding="utf-8"))
check("and the stamp says GEOMETRY_REVIEW_FAILED",
      _gstamp.get("Status") == "GEOMETRY_REVIEW_FAILED", "%r" % _gstamp)
check("and it is a declared status, so `verify_run` knows it",
      "GEOMETRY_REVIEW_FAILED" in RB.RUN_STATUSES)
check("and nothing partial is left to review or to pool",
      sorted(os.listdir(_gf)) == ["run_stamp.json"], "%s" % sorted(os.listdir(_gf)))
# The ValueError above is not a GeometryReviewError. Passed through, it leaves
# `run_batch` as an unhandled exception - the writer's own validators
# (`canonical_artifact_rows`, `verify_artifact`) raise ValueError too, so this
# is the normal way a bundle fails, not an exotic one.
check("the failure is named as the bundle's own, whatever raised it",
      "ValueError" in _gstamp.get("Detail", ""), "%r" % _gstamp.get("Detail"))


# ---------------------------------------------------------------------------
# A bar whose FILL could not be sampled, named by a person.
#
# Publication 127 prints two bars fifteen pixels tall. They have a mean, they
# have an SE, and once the outline is taken off there is no interior left to
# classify - so the reader has a geometry with no identity, and naming them from
# the pixels would mean "first slot, therefore OPEN": identity by position.
#
# The fixture reproduces exactly that, by drawing one bar of the mono panel at 3
# units instead of 27. The scenario is then the real two-phase workflow: run,
# read the row out of `mono_bar_geometry.csv`, write `identity_resolution.csv`
# against that row's hash, run again.
# ---------------------------------------------------------------------------
print()
print("a bar with no interior to sample, named by a person instead")
import make_mono_bar_fixture as MF                                  # noqa: E402

SHORT_IMG = os.path.join(IMAGES, "mono_short.png")
_short_truth = os.path.join(IMAGES, "mono_short_truth.json")
MF.draw(SHORT_IMG, _short_truth, overrides={("OPEN", "T3"): 3.0})
_st_truth = json.load(open(_short_truth, encoding="utf-8"))
# The legend crop a reviewer read the fill off. It is evidence, so it is a real
# file with a real hash: `check_identity_resolution` re-hashes it, which is what
# stops a resolution from pointing at something that changed afterwards.
LEGEND_IMG = os.path.join(IMAGES, "legend_crop.png")
Image.open(SHORT_IMG).crop((90, 40, 400, 120)).save(LEGEND_IMG)
_short_figure = dict(_mono_figure, Figure_ID="F_SHORT", Figure_Number="FIG6",
                     Source_Image=SHORT_IMG,
                     Image_Resolution_Or_Hash="sha256:" + MR.sha256_of(SHORT_IMG))
_short_source_figure = dict(_mono_source_figure, Source_Figure_ID="SF_SHORT",
                            Figure_Number="FIG6", Source_Image=SHORT_IMG,
                            Source_Image_SHA256=MR.sha256_of(SHORT_IMG))
_short_source_panel = dict(_mono_source_panel, Source_Panel_ID="P_SHORT",
                           Source_Figure_ID="SF_SHORT", Panel_Label="P_SHORT")
# Total peripheral resistance, whose plausible range starts at 0.3: the short
# bar is a real 3-unit reading and a 3-unit STROKE VOLUME is implausible, so
# reusing the previous unit would have made this scenario about the plausibility
# table instead of about the identity.
_short_unit = dict(_mono_unit, Unit_ID="U_SHORT", Figure_ID="F_SHORT",
                   Panel="U_SHORT",
                   Outcome_Variable="Total peripheral resistance",
                   Unit="mmHg/L/min")
_short_panel = dict(_mono_panel, Panel_ID="P_SHORT", Source_Panel_ID="P_SHORT",
                    Figure_ID="F_SHORT", Unit_ID="U_SHORT",
                    Panel_Label="P_SHORT", Image_Path=SHORT_IMG)
_short_series = [dict(r, Panel_ID="P_SHORT") for r in _mono_series]
_short_positions = [dict(r, Panel_ID="P_SHORT") for r in _mono_positions]


def short_manifests(directory, resolutions=None, **kw):
    """Both monochrome panels in one batch, only one of them resolvable.

    P_MONO's fills are all measurable and P_SHORT's are not, so this batch is
    what says the identity channel is per PANEL: one review mode asks three
    questions and the other four, from the same run.
    """
    fields = dict(
        panels=PANELS + [_mono_panel, _short_panel],
        series_rows=SERIES + _mono_series + _short_series,
        positions=POSITION_ROWS + _mono_positions + _short_positions,
        units=UNITS + [_mono_unit, _short_unit],
        figures=FIGURES + [_mono_figure, _short_figure],
        grids=_mono_grids,
        source_figures=SOURCE_FIGURES + [_mono_source_figure,
                                         _short_source_figure],
        source_panels=SOURCE_PANELS + [_mono_source_panel, _short_source_panel],
        source_documents=[dict(SOURCE_DOCUMENTS[0], Observed_Figure_Count=6)])
    fields.update(kw)
    out = write_manifests(directory, **fields)
    if resolutions is not None:
        with open(os.path.join(out, "identity_resolution.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=BM.identity_resolution_columns())
            w.writeheader()
            for row in resolutions:
                w.writerow({c: row.get(c, "")
                            for c in BM.identity_resolution_columns()})
    return out


# REVERT: `identity_resolution.csv` in MANIFEST_FILES rather than
# OPTIONAL_MANIFEST_FILES. Every batch in this file, and every manifest
# directory in the field, then fails to load - and the fix that suggests itself
# is an empty file in each of them, which is how a required manifest becomes one
# nobody reads.
_s1 = short_manifests(os.path.join(ROOT, "m_short1"))
_o1 = os.path.join(ROOT, "o_short1")
_su1 = RB.run_batch(_s1, _o1, file_root=ROOT, run_date="2026-08-06")
check("a batch with no identity_resolution.csv runs",
      _su1["status"] == "RAN", "%s" % _su1)
_r1 = pd.read_csv(os.path.join(_o1, "run_manifest.csv"), dtype=object).fillna("")
_row1 = _r1[_r1["Panel_ID"] == "P_SHORT"].iloc[0]
# REVERT: skip on `record["error"]` in `_geometry_marks` instead of
# `measurement_usable`. BAR_TOO_SMALL_TO_SAMPLE is a complaint about the FILL -
# the mean comes from the top edge and the dispersion from the cap, measured as
# on any other bar - so filing it with the refusals drops a readable value for a
# reason that was never about the value. Eleven of twelve becomes eleven either
# way; what changes is that the twelfth can never be recovered.
check("eleven of the twelve cells read; the short bar has no series",
      (_row1["Cells_Declared"], _row1["Cells_Read"]) == ("12", "11"),
      "%s" % dict(_row1))
_geo1 = pd.read_csv(os.path.join(_o1, "mono_bar_geometry.csv"),
                    dtype=object).fillna("")
_short_row = _geo1[(_geo1["Panel_ID"] == "P_SHORT")
                   & (_geo1["Group_ID"] == "T3")
                   & (_geo1["Geometry_Slot"] == "2")]
check("the geometry file records the bar, its number and why it has no fill",
      len(_short_row) == 1
      and _short_row.iloc[0]["Geometry_Error_Code"] == "BAR_TOO_SMALL_TO_SAMPLE"
      and float(_short_row.iloc[0]["Mean"]) > 0
      and _short_row.iloc[0]["Auto_Fill_Pattern"] == ""
      and _short_row.iloc[0]["Auto_Identity_Status"] == "UNRESOLVED_NO_FILL",
      "%s" % (_short_row.to_dict("records") or "no row"))
_short_hash = _short_row.iloc[0]["Geometry_Row_SHA256"]


def _ghash(group, slot):
    """The hash a person copying a row out of mono_bar_geometry.csv would use."""
    hit = _geo1[(_geo1["Panel_ID"] == "P_SHORT")
                & (_geo1["Group_ID"] == group)
                & (_geo1["Geometry_Slot"] == str(slot))]
    return hit.iloc[0]["Geometry_Row_SHA256"] if len(hit) else ""
_q1 = pd.read_csv(os.path.join(_o1, "manual_queue_cells.csv"),
                  dtype=object).fillna("")
check("and the cell it could not name is queued by name",
      any(r["Panel_ID"] == "P_SHORT" and "LATE" in r["Cell_Key"]
          for _, r in _q1.iterrows()),
      "%s" % [r["Cell_Key"] for _, r in _q1.iterrows()
              if r["Panel_ID"] == "P_SHORT"])


def _resolution(**kw):
    base = dict(Resolution_ID="IR1", Panel_ID="P_SHORT", Group_ID="T3",
                Geometry_Slot="2", Geometry_Row_SHA256=_short_hash,
                Resolved_Series_ID="S_OPEN", Resolved_Fill_Pattern="OPEN",
                Evidence_Type="LEGEND_DECLARED",
                Evidence_Artifact=os.path.relpath(LEGEND_IMG, ROOT),
                Evidence_Artifact_SHA256=MR.sha256_of(LEGEND_IMG),
                Reviewer_ID="RV_T1", Reviewed_At="2026-08-07",
                Note="the legend labels the open bar Late post-flight")
    base.update(kw)
    return base


_s2 = short_manifests(os.path.join(ROOT, "m_short2"), resolutions=[_resolution()])
_o2 = os.path.join(ROOT, "o_short2")
_su2 = RB.run_batch(_s2, _o2, file_root=ROOT, run_date="2026-08-06")
check("with the resolution in place the batch still runs",
      _su2["status"] == "RAN", "%s" % _su2)
_r2 = pd.read_csv(os.path.join(_o2, "run_manifest.csv"), dtype=object).fillna("")
_row2 = _r2[_r2["Panel_ID"] == "P_SHORT"].iloc[0]
check("and all twelve cells are read",
      (_row2["Cells_Declared"], _row2["Cells_Read"]) == ("12", "12"),
      "%s: %s" % (dict(_row2)["Cells_Read"], _row2["Detail"]))
_v2 = pd.read_csv(os.path.join(_o2, "figure_values_raw.csv"),
                  dtype=object).fillna("")
_v2 = _v2[_v2["Unit_ID"] == "U_SHORT"]
_named = _v2[_v2["Cell_Key"] == "ARM=LATE;TIMEPOINT=T3"]
# REVERT: leave IDENTITY_CARRIED out of `to_value_records`, or the six columns
# out of `fig_values_columns`. The value is still produced and still correct;
# what is gone is any way to ask the pooled file which row it was measured from
# and who decided it was this series.
check("the value a person named says so, and points at the row they signed",
      len(_named) == 1
      and _named.iloc[0]["Identity_Source"] == "HUMAN"
      and _named.iloc[0]["Identity_Evidence_Type"] == "LEGEND_DECLARED"
      and _named.iloc[0]["Resolution_ID"] == "IR1"
      and _named.iloc[0]["Resolved_Fill_Pattern"] == "OPEN",
      "%s" % (_named.to_dict("records") or "no row"))
check("and it is bound to the anonymous measurement it came from",
      len(_named) and _named.iloc[0]["Geometry_Row_SHA256"] == _short_hash,
      "%r vs %r" % (_named.iloc[0]["Geometry_Row_SHA256"] if len(_named) else None,
                    _short_hash))
# REVERT: write the person's answer into `Auto_Fill_Pattern` as well - the
# obvious way to make the column "complete". It is the audit trail saying the
# machine measured something a person read off a legend, and the gate then
# cannot tell the two apart.
check("and the reader is not credited with a fill it never measured",
      len(_named) and _named.iloc[0]["Auto_Fill_Pattern"] == "",
      "%r" % (_named.iloc[0]["Auto_Fill_Pattern"] if len(_named) else None))
_auto = _v2[_v2["Cell_Key"] == "ARM=LATE;TIMEPOINT=T0"]
check("a cell the FIGURE named still says AUTO, with the measured fill",
      len(_auto) == 1 and _auto.iloc[0]["Identity_Source"] == "AUTO"
      and _auto.iloc[0]["Identity_Evidence_Type"] == "FILL_MEASURED"
      and _auto.iloc[0]["Auto_Fill_Pattern"] == "OPEN"
      and not _auto.iloc[0]["Resolution_ID"],
      "%s" % (_auto.to_dict("records") or "no row"))
# The geometry artifact is what the FIGURE said and must not learn the answer.
_geo2 = pd.read_csv(os.path.join(_o2, "mono_bar_geometry.csv"),
                    dtype=object).fillna("")
_grow2 = _geo2[(_geo2["Panel_ID"] == "P_SHORT") & (_geo2["Group_ID"] == "T3")
               & (_geo2["Geometry_Slot"] == "2")].iloc[0]
check("the geometry file is unchanged by the resolution, hash and all",
      _grow2["Auto_Fill_Pattern"] == ""
      and _grow2["Auto_Identity_Status"] == "UNRESOLVED_NO_FILL"
      and _grow2["Geometry_Row_SHA256"] == _short_hash,
      "%s" % dict(_grow2))

# REVERT: keep one review mode for every BAR_MONO panel. The panel with a
# human-named cell is then approved without anybody being asked about the one
# claim in it that has no measurement behind it.
_rq2 = pd.read_csv(os.path.join(_o2, "review_queue.csv"), dtype=object).fillna("")
_qrow2 = _rq2[_rq2["Panel_ID"] == "P_SHORT"]
check("the panel is queued under the mode that asks about the naming",
      len(_qrow2) and _qrow2.iloc[0]["Review_Mode"] == "BAR_MONO_GEOMETRY_RESOLVED",
      "%s" % (list(_qrow2["Review_Mode"]) if len(_qrow2) else "not queued"))
check("and that mode requires the resolution rows as an artifact",
      "IDENTITY_RESOLUTION" in RB.REVIEW_MODES["BAR_MONO_GEOMETRY_RESOLVED"]
      and "Identity_Checked"
      in RB.REVIEW_CONFIRMATIONS["BAR_MONO_GEOMETRY_RESOLVED"],
      "%s / %s" % (RB.REVIEW_MODES["BAR_MONO_GEOMETRY_RESOLVED"],
                   RB.REVIEW_CONFIRMATIONS["BAR_MONO_GEOMETRY_RESOLVED"]))
_art2 = pd.read_csv(os.path.join(_o2, "panel_artifacts.csv"),
                    dtype=object).fillna("")
_ident = _art2[(_art2["Panel_ID"] == "P_SHORT")
               & (_art2["Artifact_Type"] == "IDENTITY_RESOLUTION")]
check("which the run wrote, hashed, into the ledger",
      len(_ident) == 1 and len(_ident.iloc[0]["SHA256"]) == 64
      and os.path.exists(os.path.join(_o2, _ident.iloc[0]["Artifact_Path"])),
      "%s" % (_ident.to_dict("records") or "no ledger row"))
check("and the file a reviewer opens is the row that was signed",
      len(_ident) and [r["Resolution_ID"] for r in csv.DictReader(
          open(os.path.join(_o2, _ident.iloc[0]["Artifact_Path"]),
               encoding="utf-8"))] == ["IR1"],
      "%s" % (_ident.iloc[0]["Artifact_Path"] if len(_ident) else ""))
check("a panel with nothing resolved keeps the plain geometry mode",
      set(_rq2[_rq2["Panel_ID"] == "P_MONO"]["Review_Mode"]) <= {"BAR_MONO_GEOMETRY"},
      "%s" % sorted(set(_rq2["Review_Mode"])))

# The three things only the measurement can refuse, each of them the whole panel.
for _label, _kw, _code in (
        ("a row the measurement does not have",
         dict(Group_ID="T9"), "IDENTITY_RESOLUTION_NO_SUCH_ROW"),
        # REVERT: apply a resolution over `resolved_fill_pattern`. This file
        # then becomes an override channel: a person can re-label any bar the
        # reader read, and the geometry file's Auto_Fill_Pattern no longer means
        # anything downstream.
        ("a bar the figure named itself",
         dict(Group_ID="T0", Geometry_Row_SHA256=_ghash("T0", 2)),
         "IDENTITY_RESOLUTION_OVERRIDES_MEASUREMENT"),
        # REVERT: join on (Panel_ID, Group_ID, Geometry_Slot) alone. The triple
        # is a POSITION: re-run after a threshold change or a re-scan and the
        # resolution silently names whatever bar now sits in slot 2, which is
        # identity by position one level up.
        ("a resolution written against a different measurement",
         dict(Geometry_Row_SHA256="0" * 64), "IDENTITY_RESOLUTION_STALE")):
    _bad = short_manifests(
        os.path.join(ROOT, "m_short_%s" % _code.lower()),
        resolutions=[_resolution(**_kw)])
    _bo = os.path.join(ROOT, "o_short_%s" % _code.lower())
    _bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06")
    check("%s refuses the panel, not just the cell" % _label,
          _bs["status"] == "RAN", "%s" % _bs)
    _br = pd.read_csv(os.path.join(_bo, "run_manifest.csv"),
                      dtype=object).fillna("")
    _brow = _br[_br["Panel_ID"] == "P_SHORT"]
    check("  and says %s" % _code,
          len(_brow) and _brow.iloc[0]["Run_State"] == "SERIES_IDENTITY_UNRESOLVED"
          and _code in _brow.iloc[0]["Detail"], "%s" % (
              list(zip(_brow["Run_State"], _brow["Detail"])) if len(_brow)
              else "no row"))
    _bv = pd.read_csv(os.path.join(_bo, "figure_values_raw.csv"),
                      dtype=object).fillna("")
    check("  and contributes no values at all",
          not len(_bv[_bv["Unit_ID"] == "U_SHORT"]),
          "%d rows" % len(_bv[_bv["Unit_ID"] == "U_SHORT"]))

# Everything that can be refused before a raster is opened. Each of these is a
# manifest problem, which means the batch does not run at all: a resolution is
# an INPUT, and an input that cannot be trusted is not a panel to queue.
for _label, _kw, _code in (
        ("FILL_MEASURED typed into the human channel",
         dict(Evidence_Type="FILL_MEASURED"), "IDENTITY_EVIDENCE_NOT_HUMAN"),
        ("an evidence type nobody declared",
         dict(Evidence_Type="I_JUST_KNOW"), "BAD_IDENTITY_EVIDENCE_TYPE"),
        ("a series this panel does not declare",
         dict(Resolved_Series_ID="S_MISSING"),
         "IDENTITY_RESOLUTION_UNKNOWN_SERIES"),
        ("a fill that contradicts the series manifest",
         dict(Resolved_Fill_Pattern="SOLID"),
         "IDENTITY_RESOLUTION_FILL_CONTRADICTS_SERIES"),
        ("evidence that is not on disk",
         dict(Evidence_Artifact="no_such_legend.png"),
         "IDENTITY_EVIDENCE_ARTIFACT_MISSING"),
        ("evidence whose hash moved since it was signed",
         dict(Evidence_Artifact_SHA256="0" * 64),
         "IDENTITY_EVIDENCE_ARTIFACT_HASH_MISMATCH"),
        ("a reviewer's own reading with nothing written down",
         dict(Evidence_Type="REVIEWER_INSPECTION", Note="",
              Evidence_Artifact="", Evidence_Artifact_SHA256=""),
         "IDENTITY_EVIDENCE_UNEXPLAINED"),
        ("a reviewer who is not in the registry",
         dict(Reviewer_ID="RV_NOBODY"), "REVIEWER_NOT_REGISTERED"),
        ("a date that is not a date",
         dict(Reviewed_At="soon"), "BAD_REVIEWED_AT"),
        ("a resolution against a panel that is not BAR_MONO",
         dict(Panel_ID="P_SCAT", Resolved_Series_ID="S_BLUE",
              Resolved_Fill_Pattern=""),
         "IDENTITY_RESOLUTION_WRONG_MARK_TYPE"),
        # A manifest names evidence inside the corpus. An absolute path would
        # let it point at any file on the machine that happens to hash right -
        # the same escape the source rasters are confined against.
        ("evidence outside the corpus",
         dict(Evidence_Artifact=os.path.join(tempfile.gettempdir(),
                                             "outside_the_root.png"),
              Evidence_Artifact_SHA256="0" * 64),
         "IDENTITY_EVIDENCE_ARTIFACT_OUTSIDE_ROOT")):
    _bad = short_manifests(
        os.path.join(ROOT, "m_ir_%s" % _code.lower()),
        resolutions=[_resolution(**_kw)])
    _bo = os.path.join(ROOT, "o_ir_%s" % _code.lower())
    _bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06")
    _codes = set(pd.read_csv(os.path.join(_bo, "manifest_problems.csv"),
                             dtype=object).fillna("")["check"]) \
        if _bs["status"] == "MANIFEST_REJECTED" else set()
    check("%s is a manifest problem, before any raster is opened" % _label,
          _bs["status"] == "MANIFEST_REJECTED" and _code in _codes,
          "%s %s" % (_bs["status"], sorted(_codes)))

# A resolution signed by something that is not a person. `FILL_MEASURED` is what
# a program's answer is called and it lives in the geometry file; a registry row
# that is not Reviewer_Record_Type=HUMAN signing this one is the audit trail
# saying a person did what a program did.
_demo_reg = REVIEWERS + [dict(
    Reviewer_ID="RV_BOT", Reviewer_Name="Digitizer",
    Reviewer_Record_Type="DEMO_IDENTITY", Contact_Type="EMAIL",
    Reviewer_Contact="bot@example.org", Registered_By="Test Fixture",
    Registration_Date="2026-08-01", Human_Attestation="DEMO_EXAMPLE",
    Note="not a person")]
_bad = short_manifests(os.path.join(ROOT, "m_ir_nothuman"),
                       resolutions=[_resolution(Reviewer_ID="RV_BOT")],
                       reviewers=_demo_reg)
_bo = os.path.join(ROOT, "o_ir_nothuman")
_bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06")
_codes = set(pd.read_csv(os.path.join(_bo, "manifest_problems.csv"),
                         dtype=object).fillna("")["check"]) \
    if _bs["status"] == "MANIFEST_REJECTED" else set()
check("a resolution signed by a non-person is refused",
      _bs["status"] == "MANIFEST_REJECTED"
      and "IDENTITY_RESOLUTION_NOT_HUMAN" in _codes,
      "%s %s" % (_bs["status"], sorted(_codes)))

# Two rows for one bar, and two slots of one group named as the same series.
for _label, _rows, _code in (
        ("the same bar resolved twice",
         [_resolution(), _resolution(Resolution_ID="IR2")],
         "IDENTITY_RESOLUTION_DUPLICATE"),
        ("the same Resolution_ID used twice",
         [_resolution(), _resolution(Group_ID="T2",
                                     Geometry_Row_SHA256=_ghash("T2", 2))],
         "DUPLICATE_RESOLUTION_ID"),
        ("one series named twice in one group",
         [_resolution(), _resolution(Resolution_ID="IR2", Geometry_Slot="1",
                                     Geometry_Row_SHA256=_ghash("T3", 1))],
         "IDENTITY_RESOLUTION_SERIES_TWICE_IN_GROUP")):
    _bad = short_manifests(
        os.path.join(ROOT, "m_irdup_%s" % _code.lower()), resolutions=_rows)
    _bo = os.path.join(ROOT, "o_irdup_%s" % _code.lower())
    _bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06")
    _codes = set(pd.read_csv(os.path.join(_bo, "manifest_problems.csv"),
                             dtype=object).fillna("")["check"]) \
        if _bs["status"] == "MANIFEST_REJECTED" else set()
    check("%s is refused" % _label,
          _bs["status"] == "MANIFEST_REJECTED" and _code in _codes,
          "%s %s" % (_bs["status"], sorted(_codes)))

# And an approval of that panel has to say the naming was checked. Driven
# through `approved_panels` with the run's OWN queue and ledger, because the
# requirement is per panel: P_MONO in the same batch is asked three questions
# and P_SHORT four.
#
# REVERT: leave `Identity_Checked` out of REVIEW_CONFIRMATIONS for the resolved
# mode. The approval below goes through with the identity column blank, and the
# one claim in the panel with no measurement behind it is approved by silence.
_fq2 = pd.read_csv(os.path.join(_o2, "review_queue.csv"), dtype=object).fillna("")
_fa2 = pd.read_csv(os.path.join(_o2, "panel_artifacts.csv"),
                   dtype=object).fillna("")
_types2 = {}
for _, _row_ in _fa2.iterrows():
    _types2.setdefault(_row_["Panel_ID"], set()).add(_row_["Artifact_Type"])
_reviewers2 = pd.read_csv(os.path.join(_s2, "reviewer_registry.csv"),
                          dtype=object).fillna("")


def _approve(panel, **extra):
    """One filled review row for `panel`, against this run's own subject hash."""
    hit = _fq2[_fq2["Panel_ID"] == panel]
    base = dict(Review_ID="R_%s" % panel, Panel_ID=panel,
                Review_Subject_SHA256=(hit.iloc[0]["Review_Subject_SHA256"]
                                       if len(hit) else ""),
                Reviewer_ID="RV_T1", Decision="APPROVED",
                Marks_Checked="CONFIRMED", Axis_Labels_Checked="CONFIRMED",
                Calibration_Checked="CONFIRMED", Identity_Checked="",
                Reviewed_At="2026-08-07T10:00:00Z", Note="")
    base.update(extra)
    return pd.DataFrame([base])


for _label, _extra, _want in (
        ("with the naming left blank", {}, False),
        ("with the naming confirmed", dict(Identity_Checked="CONFIRMED"), True)):
    _probs = []
    _got = FIN.approved_panels(
        _approve("P_SHORT", **_extra), _fq2, _reviewers2,
        lambda w, c, d: _probs.append(c),
        today=datetime.date(2026, 8, 8), artifact_types=_types2)
    check("a resolved panel approved %s -> %s"
          % (_label, "accepted" if _want else "refused"),
          bool(_got) == _want
          and (_want or "REVIEW_CONFIRMATION_MISSING" in _probs), "%s" % _probs)
_probs = []
FIN.approved_panels(_approve("P_MONO"), _fq2, _reviewers2,
                    lambda w, c, d: _probs.append(c),
                    today=datetime.date(2026, 8, 8), artifact_types=_types2)
check("and a panel with nothing resolved is not asked about a naming",
      not _probs, "%s" % _probs)
# REVERT: drop IDENTITY_RESOLUTION from the resolved mode's artifact tuple. The
# approval then stands with nothing in the ledger for the rows that were signed,
# so "the naming was checked" points at no file.
_probs = []
_thin = {p: {t for t in ts if t != "IDENTITY_RESOLUTION"}
         for p, ts in _types2.items()}
FIN.approved_panels(_approve("P_SHORT", Identity_Checked="CONFIRMED"), _fq2,
                    _reviewers2, lambda w, c, d: _probs.append(c),
                    today=datetime.date(2026, 8, 8), artifact_types=_thin)
check("and the resolution rows have to be in the ledger to be approved against",
      "REVIEW_ARTIFACT_MISSING" in _probs, "%s" % _probs)
check("every review mode declares the confirmations it asks for",
      set(RB.REVIEW_CONFIRMATIONS) == set(RB.REVIEW_MODES),
      "%s" % sorted(set(RB.REVIEW_CONFIRMATIONS) ^ set(RB.REVIEW_MODES)))
check("and the template ships every column any mode can ask for",
      all(c in FIN.value_review_columns()
          for cols in RB.REVIEW_CONFIRMATIONS.values() for c in cols)
      and "Identity_Checked" in open(
          os.path.join(HERE, "value_review_TEMPLATE.csv"),
          encoding="utf-8").readline(),
      "%s" % FIN.value_review_columns())

# A BAR_MONO value must CARRY its provenance, not merely be consistent about it.
#
# The gate's identity block only fires when one of the columns is filled, which
# is right for a file that cannot know what drew the panel - a line panel's rows
# say nothing about fills - and wrong as the only defence. With the six columns
# gone the mean and the SE are still fine, the gate says nothing, and the value
# is reviewable and poolable with no way to ask which bar it came from.
#
# REVERT: delete the `identity_provenance_problems` call from `run_batch`, or
# the function. Every scenario above still passes, because the runner fills the
# columns today; what is gone is the check that it still does.
print()
print("a monochrome value has to carry where it came from, not just agree with itself")
_MONO_MARKS = {"P_SHORT": "BAR_MONO", "P_LINE": "LINE_COLOR"}


def _prov(**kw):
    base = dict(Run_Panel_ID="P_SHORT", Unit_ID="U_SHORT",
                Cell_Key="ARM=LATE;TIMEPOINT=T3", Mean="3.056",
                Geometry_Row_SHA256="a" * 64, Auto_Fill_Pattern="OPEN",
                Resolved_Fill_Pattern="OPEN", Identity_Source="AUTO",
                Identity_Evidence_Type="FILL_MEASURED", Resolution_ID="")
    base.update(kw)
    return [c for _w, c, _d in RB.identity_provenance_problems([base],
                                                               _MONO_MARKS)]


check("a complete automatic provenance passes", _prov() == [], "%s" % _prov())
_blanked = {c: "" for c in ("Geometry_Row_SHA256", "Auto_Fill_Pattern",
                            "Resolved_Fill_Pattern", "Identity_Source",
                            "Identity_Evidence_Type", "Resolution_ID")}
check("all six columns gone is IDENTITY_PROVENANCE_MISSING",
      _prov(**_blanked) == ["IDENTITY_PROVENANCE_MISSING"], "%s" % _prov(**_blanked))
check("and so is the row hash alone going missing",
      "IDENTITY_PROVENANCE_MISSING" in _prov(Geometry_Row_SHA256=""),
      "%s" % _prov(Geometry_Row_SHA256=""))
check("a row hash that is not a hash is refused too",
      "IDENTITY_PROVENANCE_MISSING" in _prov(Geometry_Row_SHA256="see the csv"),
      "%s" % _prov(Geometry_Row_SHA256="see the csv"))
check("a fill this reader does not distinguish is refused",
      "IDENTITY_PROVENANCE_MISSING" in _prov(Resolved_Fill_Pattern="NONE",
                                             Auto_Fill_Pattern="NONE"),
      "%s" % _prov(Resolved_Fill_Pattern="NONE", Auto_Fill_Pattern="NONE"))
check("an automatic identity whose two fills disagree is refused",
      _prov(Auto_Fill_Pattern="SOLID") == ["IDENTITY_FILL_MISMATCH"],
      "%s" % _prov(Auto_Fill_Pattern="SOLID"))
check("AUTO carrying a resolution, or a human's evidence, is refused",
      _prov(Resolution_ID="IR1") == ["IDENTITY_SOURCE_INCONSISTENT"]
      and _prov(Identity_Evidence_Type="LEGEND_DECLARED")
      == ["IDENTITY_SOURCE_INCONSISTENT"],
      "%s %s" % (_prov(Resolution_ID="IR1"),
                 _prov(Identity_Evidence_Type="LEGEND_DECLARED")))
check("a human identity with no row signed, or a measured fill beside it",
      _prov(Identity_Source="HUMAN", Identity_Evidence_Type="LEGEND_DECLARED",
            Auto_Fill_Pattern="")
      == ["IDENTITY_RESOLUTION_UNIDENTIFIED"]
      and _prov(Identity_Source="HUMAN",
                Identity_Evidence_Type="LEGEND_DECLARED",
                Resolution_ID="IR1") == ["IDENTITY_OVERRODE_MEASUREMENT"],
      "%s" % _prov(Identity_Source="HUMAN",
                   Identity_Evidence_Type="LEGEND_DECLARED", Resolution_ID="IR1"))
check("a source nobody declared is refused",
      "IDENTITY_PROVENANCE_MISSING" in _prov(Identity_Source="MACHINE"),
      "%s" % _prov(Identity_Source="MACHINE"))
# And the same six blanks on a panel nothing drew fills for. This is the reason
# the requirement cannot live in the gate: it is not a property of a values row,
# it is a property of a values row FROM A MONOCHROME BAR PANEL.
check("a colour panel's value says nothing about fills, quite legitimately",
      not RB.identity_provenance_problems(
          [dict(Run_Panel_ID="P_LINE", Unit_ID="U_LINE", Mean="55")],
          _MONO_MARKS),
      "%s" % RB.identity_provenance_problems(
          [dict(Run_Panel_ID="P_LINE", Unit_ID="U_LINE", Mean="55")],
          _MONO_MARKS))
# Wired, not merely present: with the carrier removed the whole panel fails the
# gate rather than passing with blank provenance.
_real_carried = MR.IDENTITY_CARRIED
try:
    MR.IDENTITY_CARRIED = ()
    _po = os.path.join(ROOT, "o_short_noprov")
    _ps = RB.run_batch(_s2, _po, file_root=ROOT, run_date="2026-08-06")
finally:
    MR.IDENTITY_CARRIED = _real_carried
_pqc = set(pd.read_csv(os.path.join(_po, "qc_problems.csv"),
                       dtype=object).fillna("")["check"]) \
    if os.path.exists(os.path.join(_po, "qc_problems.csv")) else set()
_pr = pd.read_csv(os.path.join(_po, "run_manifest.csv"), dtype=object).fillna("")
check("a run whose marks lost their provenance fails the gate",
      "IDENTITY_PROVENANCE_MISSING" in _pqc, "%s" % sorted(_pqc))
check("and both monochrome panels are QC_FAILED, not AUTO_PASS",
      set(_pr[_pr["Panel_ID"].isin(["P_MONO", "P_SHORT"])]["Run_State"])
      == {"QC_FAILED"},
      "%s" % _pr[["Panel_ID", "Run_State"]].to_dict("records"))
check("and the colour panels in the same batch are unaffected",
      _pr[_pr["Panel_ID"] == "P_SCAT"].iloc[0]["Run_State"] == "AUTO_PASS",
      "%s" % _pr[["Panel_ID", "Run_State"]].to_dict("records"))

# The evidence BYTES travel with the run.
#
# `check_identity_resolution` hashes the legend crop at validation time, which
# protects the hash STRING in the manifest and nothing else: edit or delete the
# file afterwards and identity__<Panel_ID>.csv, the ledger and
# Review_Subject_SHA256 are all unchanged, so Identity_Checked=CONFIRMED could
# be given against evidence that no longer exists. And a run directory handed to
# somebody else did not contain the picture its own review mode tells them to
# open.
#
# REVERT: register the resolution rows and not the evidence. The two scenarios
# below are the only place it shows.
print()
print("the evidence a person read the series off travels with the run")
_ev = _art2[(_art2["Panel_ID"] == "P_SHORT")
            & (_art2["Artifact_Type"] == "IDENTITY_EVIDENCE")]
check("the legend crop is copied into the run and hashed into the ledger",
      len(_ev) == 1 and len(_ev.iloc[0]["SHA256"]) == 64
      and os.path.exists(os.path.join(_o2, _ev.iloc[0]["Artifact_Path"])),
      "%s" % (_ev.to_dict("records") or "no ledger row"))
check("byte for byte, and named after the resolution that cites it",
      len(_ev)
      and open(os.path.join(_o2, _ev.iloc[0]["Artifact_Path"]), "rb").read()
      == open(LEGEND_IMG, "rb").read()
      and "IR1" in os.path.basename(_ev.iloc[0]["Artifact_Path"]),
      "%s" % (_ev.iloc[0]["Artifact_Path"] if len(_ev) else ""))
# And the finalizer re-hashes it with everything else in the ledger, so editing
# the copy after the review is RUN_ARTIFACT_MODIFIED rather than an approval of
# something nobody saw.
# Guarded on the ledger row existing, so removing the copy is two failed
# scenarios rather than a traceback that stops the file here.
_ev_path = os.path.join(_o2, _ev.iloc[0]["Artifact_Path"]) if len(_ev) else ""


def _verify_run():
    problems = []
    ok = FIN.verify_run_outputs(
        _o2, json.load(open(os.path.join(_o2, "run_stamp.json"),
                            encoding="utf-8")),
        _s2, lambda w, c, d: problems.append(c))
    return ok, problems


_before, _probs = _verify_run()
check("the run verifies as written", _before and not _probs, "%s" % _probs)
if _ev_path:
    _ev_bytes = open(_ev_path, "rb").read()
    try:
        with open(_ev_path, "wb") as _fh:
            _fh.write(_ev_bytes + b"a different crop")
        _after, _probs = _verify_run()
    finally:
        with open(_ev_path, "wb") as _fh:
            _fh.write(_ev_bytes)
else:
    _after, _probs = True, []
check("and evidence edited after the run is RUN_ARTIFACT_MODIFIED",
      not _after and "RUN_ARTIFACT_MODIFIED" in _probs,
      "%s" % (_probs if _ev_path else "no evidence artifact to tamper with"))

# The copy is verified after it is made, so the two ways it can be wrong are
# refusals of the review bundle rather than a ledger entry nobody can trust.
# Both need --no-file-check, because with file checking on the manifest
# validator catches them first - which is the point: this is the second line.
for _label, _kw, _fix in (
        ("evidence that is not there to copy",
         dict(Evidence_Artifact="gone_before_the_copy.png"), "copied"),
        ("evidence whose bytes do not match the resolution",
         dict(Evidence_Artifact_SHA256="b" * 64), "reproduced")):
    _bad = short_manifests(os.path.join(ROOT, "m_ev_%s" % _fix),
                           resolutions=[_resolution(**_kw)])
    _bo = os.path.join(ROOT, "o_ev_%s" % _fix)
    _bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06",
                       check_files=False)
    check("%s refuses the whole review bundle" % _label,
          _bs["status"] == "GEOMETRY_REVIEW_FAILED"
          and _fix in _bs.get("detail", ""),
          "%s %r" % (_bs["status"], _bs.get("detail")))
    check("  and leaves nothing to review or to pool",
          sorted(os.listdir(_bo)) == ["run_stamp.json"],
          "%s" % sorted(os.listdir(_bo)))
check("only evidence that IS a file is copied; a reviewer's own reading is not",
      BM.FILE_EVIDENCE_TYPES == ("LEGEND_DECLARED", "TEXT_DECLARED")
      and "REVIEWER_INSPECTION" not in BM.FILE_EVIDENCE_TYPES
      and set(BM.FILE_EVIDENCE_TYPES) < set(BM.HUMAN_IDENTITY_EVIDENCE),
      "%s" % (BM.FILE_EVIDENCE_TYPES,))

# Three more ways a resolution can be wrong, each found where it can be found.
for _label, _kw, _code, _rows in (
        # An auto identity and a human one naming the same series in one group.
        # Neither row breaks a rule alone - the human's target really was
        # unnamed - and the pair puts two values in one cell, which used to
        # surface much later as a duplicate factorial cell: fail-closed, but
        # blaming the grid for something the identities did.
        ("a human identity that collides with a measured one",
         dict(Resolved_Series_ID="S_SOLID", Resolved_Fill_Pattern="SOLID"),
         "IDENTITY_RESOLUTION_CONFLICTS_WITH_MEASUREMENT", "run"),
        # The registry and the final approval already refuse a future date. A
        # reading that has not happened is not a reading.
        ("a reading dated in the future",
         dict(Reviewed_At="2099-01-01"), "BAD_REVIEWED_AT", "manifest"),
        # Half a declaration: a path with no hash is an unverifiable file, a
        # hash with no path is a claim about nothing.
        ("evidence declared by half",
         dict(Evidence_Type="REVIEWER_INSPECTION", Evidence_Artifact_SHA256="",
              Note="the legend labels it Late post-flight"),
         "IDENTITY_EVIDENCE_HALF_DECLARED", "manifest")):
    _bad = short_manifests(os.path.join(ROOT, "m_x_%s" % _code.lower()),
                           resolutions=[_resolution(**_kw)])
    _bo = os.path.join(ROOT, "o_x_%s" % _code.lower())
    _bs = RB.run_batch(_bad, _bo, file_root=ROOT, run_date="2026-08-06")
    if _rows == "manifest":
        _codes = set(pd.read_csv(os.path.join(_bo, "manifest_problems.csv"),
                                 dtype=object).fillna("")["check"]) \
            if _bs["status"] == "MANIFEST_REJECTED" else set()
        check("%s is refused before any raster is opened" % _label,
              _bs["status"] == "MANIFEST_REJECTED" and _code in _codes,
              "%s %s" % (_bs["status"], sorted(_codes)))
    else:
        _br = pd.read_csv(os.path.join(_bo, "run_manifest.csv"),
                          dtype=object).fillna("")
        _brow = _br[_br["Panel_ID"] == "P_SHORT"]
        check("%s refuses the panel, naming the collision" % _label,
              len(_brow)
              and _brow.iloc[0]["Run_State"] == "SERIES_IDENTITY_UNRESOLVED"
              and _code in _brow.iloc[0]["Detail"],
              "%s" % (list(zip(_brow["Run_State"], _brow["Detail"]))
                      if len(_brow) else "no row"))

check("the identity vocabulary has one definition, in the layer both can see",
      BM.AUTO_IDENTITY_EVIDENCE is K.FIG_AUTO_IDENTITY_EVIDENCE
      and BM.HUMAN_IDENTITY_EVIDENCE is K.FIG_HUMAN_IDENTITY_EVIDENCE
      and BM.IDENTITY_EVIDENCE_RANK is K.FIG_IDENTITY_EVIDENCE_RANK,
      "%s" % (BM.IDENTITY_EVIDENCE,))
check("and only BAR_MONO's own facts are in the identity half of MARK_CARRIED",
      set(dict(MR.IDENTITY_CARRIED)) == {
          "Geometry_Row_SHA256", "Auto_Fill_Pattern", "Resolved_Fill_Pattern",
          "Identity_Source", "Identity_Evidence_Type", "Resolution_ID"}
      and not set(dict(MR.MARK_CARRIED)) & set(dict(MR.IDENTITY_CARRIED)),
      "%s" % sorted(dict(MR.IDENTITY_CARRIED)))
check("and every one of them has a column in the values file",
      all(c in GE.fig_values_columns()
          for _src, c in MR.MARK_CARRIED + MR.IDENTITY_CARRIED),
      "%s" % [c for _s_, c in MR.MARK_CARRIED + MR.IDENTITY_CARRIED
              if c not in GE.fig_values_columns()])


print("the option table is checked against the readers it configures")
# Declaring that an option "applies to" a mark type is a promise about a
# function signature. `n_slots` was declared for BAR_MONO, whose reader has no
# such parameter: the manifest validated, the run raised TypeError, and the
# runner reported PANEL_GEOMETRY_UNRESOLVED - a message about the figure for a
# defect in a table. Introspection closes the class, not the instance.
import inspect  # noqa: E402

_readers = RB.reader_functions()
check("every batch mark type has a reader function to introspect",
      set(_readers) == set(BM.BATCH_MARK_TYPES),
      "%s" % sorted(set(_readers) ^ set(BM.BATCH_MARK_TYPES)))
_mismatch = []
for _opt, (_parse, _applies, _keyword, _check) in sorted(BM.READER_OPTIONS.items()):
    if _keyword is None:
        continue                    # consumed by the runner, not by a reader
    for _mark in _applies:
        if _keyword not in inspect.signature(_readers[_mark]).parameters:
            _mismatch.append("%s -> %s(%s)" % (_opt, _mark, _keyword))
check("every reader option names a parameter its reader actually accepts",
      not _mismatch, "; ".join(_mismatch))

# The same promise, made to the reader that has not been wired in yet. Checking
# it only at the switchover means finding out then that `threshold`,
# `stem_threshold` and `min_bar_px` are declared for BAR_MONO and not accepted
# by `read_monochrome_bar_geometry` - and the tempting fix at that point is to
# filter the options down to the ones it takes, which turns three settings a
# person wrote in a manifest into three settings nobody applies.
#
# REVERT: delete SUCCESSOR_READERS and this block. Every other scenario passes,
# because the successor is not called by anything yet.
_ahead = []
for _opt, (_parse, _applies, _keyword, _check) in sorted(BM.READER_OPTIONS.items()):
    if _keyword is None:
        continue
    for _mark in _applies:
        _next = RB.SUCCESSOR_READERS.get(_mark)
        if _next is not None and _keyword not in inspect.signature(_next).parameters:
            _ahead.append("%s -> %s(%s)" % (_opt, _mark, _keyword))
check("and so does the reader that is going to replace it",
      not _ahead, "; ".join(_ahead))
# SUCCESSOR_READERS is empty now: the reader it held IS the BAR_MONO reader.
# It stays because the next reader built before it can be wired goes there and
# gets its option contract checked several commits before the switchover
# instead of at it.
check("BAR_MONO dispatches to the geometry reader, and it takes all five options",
      RB.reader_functions()["BAR_MONO"] is MR.read_monochrome_bar_geometry
      and not RB.SUCCESSOR_READERS
      and {"threshold", "stem_threshold", "group_window", "min_bar_px",
           "baseline_value"} <= set(inspect.signature(
               RB.reader_functions()["BAR_MONO"]).parameters),
      repr(sorted(inspect.signature(
          RB.reader_functions()["BAR_MONO"]).parameters)))
# And it does not take them as decoration: the two ink thresholds have to reach
# the measurement, or a manifest could set them and read the same numbers.
with open(os.path.join(HERE, "mono_bar_fixture_truth.json"), encoding="utf-8") as _fh:
    _MONO_TRUTH = json.load(_fh)
_probe_kw = dict(image=Image.open(os.path.join(HERE, "mono_bar_fixture.png")),
                 panel_box=tuple(_MONO_TRUTH["panel_box"]),
                 x_positions=dict(zip(_MONO_TRUTH["groups"],
                                      _MONO_TRUTH["group_x"])),
                 y_calibration=MR.AxisCalibration.from_points(
                     [(v, p) for v, p in _MONO_TRUTH["y_ticks"]]),
                 fills=_MONO_TRUTH["patterns"], group_window=60,
                 panel_id="P", figure_id="F")
_at_128 = MR.read_monochrome_bar_geometry(**_probe_kw)
_at_0 = MR.read_monochrome_bar_geometry(threshold=0, **_probe_kw)
check("threshold reaches the measurement rather than sitting in the signature",
      len(_at_128) == 12
      and [r.get("error") for r in _at_0] == ["STROKE_SCALE_UNRESOLVED"],
      "%r against %d rows" % ([r.get("error") for r in _at_0], len(_at_128)))
# This fixture is pure black on pure white, so any threshold between the two
# reads the same figure - which is why the scenario that shows the threshold
# reaching the CAP classification, and stem_threshold with it, is drawn in grey
# in `test_measure_mono_bars`. Here the point is only that the option is not
# accepted and dropped.
_wide = MR.read_monochrome_bar_geometry(min_bar_px=400, **_probe_kw)
_narrow = [r for r in _wide if r.get("error") == "BAR_TOO_NARROW"]
check("min_bar_px refuses the bars it excludes and names them",
      len(_narrow) == 12 and all(r.get("footprint_width") for r in _narrow),
      repr([(r.get("slot"), r.get("error"), r.get("footprint_width"))
            for r in _wide][:4]))
# REVERT: `continue` on a bar that fails the width gate, which is what the old
# reader did with the group-level form of this option. The panel comes back with
# fewer records than it declared and nothing says why - the failure NO_SEED_
# SUPPORT exists to close, re-entering through a config file.
check("and the panel still reports every bar it declared",
      len([r for r in _wide if r.get("slot") is not None]) == 12,
      "%d rows" % len([r for r in _wide if r.get("slot") is not None]))
check("slot_tolerance_px is offered to BAR_COLOR only",
      BM.READER_OPTIONS["slot_tolerance_px"][1] == ("BAR_COLOR",),
      "%s" % (BM.READER_OPTIONS["slot_tolerance_px"][1],))
check("n_slots is gone - a reader does not reconstruct its own x spacing",
      "n_slots" not in BM.READER_OPTIONS
      and all("n_slots" not in inspect.signature(f).parameters
              for f in _readers.values()),
      "%s" % sorted(BM.READER_OPTIONS))
check("every positional reader takes the declared x pixels",
      all("x_positions" in inspect.signature(_readers[m]).parameters
          for m in BM.POSITIONAL_MARK_TYPES),
      "%s" % [m for m in BM.POSITIONAL_MARK_TYPES
              if "x_positions" not in inspect.signature(_readers[m]).parameters])
check("every option has a range check, not just a parser",
      all(callable(v[3]) for v in BM.READER_OPTIONS.values()))
check("an unreleased mark type is named rather than silently unknown",
      "LINE_MONO_STYLE" in BM.UNRELEASED_MARK_TYPES
      and "LINE_MONO_STYLE" not in BM.BATCH_MARK_TYPES)


print("a scatter whose marks do not add up to the declared sample is not computed")
# An association is a function of a point set. If the reader's point set is not
# the study's point set, the r it produces is not the study's r - and the run
# used to publish it anyway, with `N_Pairs` set to however many contours had
# survived the area filter, which agrees with itself by construction.
for _label, _n, _agreement in (("more subjects than marks", 14, "FEWER_DETECTED"),
                               ("fewer subjects than marks", 7, "MORE_DETECTED")):
    _cdir = os.path.join(ROOT, "count_%d" % _n)
    _cmd = write_manifests(os.path.join(_cdir, "manifests"),
                           units=edited(UNITS, {"Unit_ID": "U_SCAT"}, N_Outcome=_n))
    _csum = RB.run_batch(_cmd, os.path.join(_cdir, "out"), file_root=ROOT,
                         run_date="2026-08-06")
    _crun = pd.read_csv(os.path.join(_cdir, "out", "run_manifest.csv"),
                        dtype=object).fillna("")
    _cvals = pd.read_csv(os.path.join(_cdir, "out", "figure_values_raw.csv"),
                         dtype=object).fillna("")
    _crow = _crun[_crun["Panel_ID"] == "P_SCAT"].iloc[0]
    check("%s sends the panel to a person, not to the values file" % _label,
          _crow["Run_State"] == "MANUAL_POINT_READ"
          and not len(_cvals[_cvals["Unit_ID"] == "U_SCAT"]),
          "%s / %d rows" % (_crow["Run_State"],
                            len(_cvals[_cvals["Unit_ID"] == "U_SCAT"])))
    check("and says which two numbers disagree (%s)" % _label,
          "n=%d" % _n in _crow["Detail"] and "%d distinct" % len(SCATTER_XY)
          in _crow["Detail"], "%s" % _crow["Detail"])
    # The validator must be able to reach the same verdict from the file alone,
    # because a hand-edited values file never went through the runner.
    _forced = dict(Unit_ID="U_SCAT", Cell_Key="ARM=SINGLE",
                   Association_Type="PEARSON_R", Association_Value=0.9,
                   P_Value=0.01, P_Value_Method="PEARSON_T_TEST", N_Pairs=10,
                   P_Value_Extraction_Method="DIGITIZED", Ties_Present="FALSE",
                   Point_Data_Reference="points.json",
                   Expected_N_From_Source=_n, Detected_Unique_Point_Count=10,
                   Point_Count_Agreement=_agreement,
                   Overplotting_Possible="TRUE", Series_Mask_Overlap_Count=0)
    _cp = GE.fig_validate_bundle(
        fr(FIGURES, GE.fig_figure_columns()), fr(GRIDS, GE.fig_grid_columns()),
        fr([u for u in UNITS if u["Unit_ID"] == "U_SCAT"], GE.fig_unit_columns()),
        fr([_forced], GE.fig_values_columns()), kernel=K)
    check("the gate reaches the same verdict from the file alone (%s)" % _label,
          "POINT_COUNT_DISAGREES_WITH_SOURCE" in set(_cp["check"]),
          "%s" % sorted(set(_cp["check"])))


print("a queued panel has something a person can actually open")
# The protocol says: open review/<Panel_ID>_overlay.png for every row of the
# review queue and approve only if each mark sits where a reader would put it.
# `_scatter_outcome` was never passed a review directory, so a scatter reached
# the queue with Overlay_File="" and no OVERLAY artifact - and that instruction
# pointed at nothing. The overlay code has handled point_px_x/point_px_y all
# along; nobody called it.
_rq = pd.read_csv(os.path.join(ODIR, "review_queue.csv"), dtype=object).fillna("")
_art = pd.read_csv(os.path.join(ODIR, "panel_artifacts.csv"), dtype=object).fillna("")
_by_panel = {}
for _, _a in _art.iterrows():
    _by_panel.setdefault(_a["Panel_ID"], set()).add(_a["Artifact_Type"])
check("the scatter panel reached the review queue",
      "P_SCAT" in set(_rq["Panel_ID"]), "%s" % sorted(set(_rq["Panel_ID"])))
check("and it has an overlay, like every other queued panel",
      all(r["Overlay_File"]
          and os.path.exists(RB.resolve_artifact(ODIR, r["Overlay_File"]) or "")
          for _, r in _rq.iterrows()),
      "%s" % [(r["Panel_ID"], r["Overlay_File"]) for _, r in _rq.iterrows()])
check("named relative to the run, so the queue survives being moved",
      not any(os.path.isabs(r["Overlay_File"]) or os.path.isabs(r["WPD_Project_File"])
              for _, r in _rq.iterrows()),
      "%s" % [(r["Overlay_File"], r["WPD_Project_File"]) for _, r in _rq.iterrows()])
check("the overlay is in the ledger too, so tampering with it is caught",
      all("OVERLAY" in _by_panel.get(p, set()) for p in _rq["Panel_ID"]),
      "%s" % {p: sorted(_by_panel.get(p, ())) for p in _rq["Panel_ID"]})
_scat_overlay = os.path.join(ODIR, "review", "P_SCAT_overlay.png")
check("and the scatter's overlay is a real image of its panel",
      os.path.exists(_scat_overlay)
      and Image.open(_scat_overlay).size[0] > 100,
      "%s" % sorted(os.listdir(os.path.join(ODIR, "review"))))
# Every queued panel declares HOW it can be reviewed, and the artifact it names
# must be one the run actually produced.
check("every queued panel declares its review mode",
      set(_rq["Review_Mode"]) <= set(RB.REVIEW_MODES) and len(set(_rq["Review_Mode"])),
      "%s" % sorted(set(_rq["Review_Mode"])))
check("and the mode it declares is backed by a ledger artifact",
      all(set(RB.REVIEW_MODES[r["Review_Mode"]])
          <= _by_panel.get(r["Panel_ID"], set())
          for _, r in _rq.iterrows()),
      "%s" % [(r["Panel_ID"], r["Review_Mode"]) for _, r in _rq.iterrows()])


# `draw_panel_overlay` never raises: a picture that cannot be painted must not
# fail a panel that produced values. That is right, and it means any panel can
# reach the queue with no overlay - so the contract has to be enforced rather
# than assumed. Injected here, because a drawing failure cannot be provoked
# from a manifest.
_no_overlay = lambda *a, **k: None                                  # noqa: E731
_real_overlay = RB.OVERLAY.draw_panel_overlay
_real_project = RB.write_panel_project
try:
    RB.OVERLAY.draw_panel_overlay = _no_overlay
    _wpd_md = write_manifests(os.path.join(ROOT, "wpdonly", "manifests"))
    _wpd_sum = RB.run_batch(_wpd_md, os.path.join(ROOT, "wpdonly", "out"),
                            file_root=ROOT, run_date="2026-08-06")
    _wq = pd.read_csv(os.path.join(ROOT, "wpdonly", "out", "review_queue.csv"),
                      dtype=object).fillna("")
    check("a panel whose picture could not be drawn is still reviewable in WPD",
          len(_wq) and set(_wq["Review_Mode"]) == {"WPD_ONLY"}
          and all(r["WPD_Project_File"] for _, r in _wq.iterrows()),
          "%s" % _wq[["Panel_ID", "Review_Mode", "Overlay_File"]].to_dict("records"))
    # Neither a picture nor a project: nothing a reviewer could open.
    RB.write_panel_project = lambda *a, **k: None
    _none_md = write_manifests(os.path.join(ROOT, "noreview", "manifests"))
    RB.run_batch(_none_md, os.path.join(ROOT, "noreview", "out"),
                 file_root=ROOT, run_date="2026-08-06")
    _nq = pd.read_csv(os.path.join(ROOT, "noreview", "out", "review_queue.csv"),
                      dtype=object).fillna("")
    _nr = pd.read_csv(os.path.join(ROOT, "noreview", "out", "run_manifest.csv"),
                      dtype=object).fillna("")
    _nm = pd.read_csv(os.path.join(ROOT, "noreview", "out", "manual_queue.csv"),
                      dtype=object).fillna("")
    check("a panel with neither is not queued for a review nobody can perform",
          "P_LINE" not in set(_nq["Panel_ID"]),
          "%s" % _nq[["Panel_ID", "Review_Mode"]].to_dict("records"))
    # It is the grid gate that catches this one, not the review contract: a
    # digitized value with no saved project is MISSING_PROVENANCE, so the panel
    # is QC_FAILED before anything asks whether it could be reviewed. Worth
    # writing down, because it is why the runner has no separate demotion for
    # the case - an unreachable branch is decoration - and why the finalizer
    # refuses a blank Review_Mode instead of trusting that ordering to hold.
    check("  it is refused with its reason on the record",
          dict(zip(_nr["Panel_ID"], _nr["Run_State"]))["P_LINE"] != "AUTO_PASS"
          and len(_nm[_nm["Panel_ID"] == "P_LINE"]) == 1
          and _nm[_nm["Panel_ID"] == "P_LINE"]["Detail"].iloc[0],
          "%s" % _nm[_nm["Panel_ID"] == "P_LINE"][["Run_State", "Detail"]].to_dict("records"))
    check("  and its values are not machine-QC-passed either",
          not len(pd.read_csv(
              os.path.join(ROOT, "noreview", "out", "figure_values_machine_qc.csv"),
              dtype=object).fillna("").query("Unit_ID == 'U_LINE'")),
          "some survived")
finally:
    RB.OVERLAY.draw_panel_overlay = _real_overlay
    RB.write_panel_project = _real_project

# The finalizer holds the same contract from its own side, because a review
# queue is a file and a file can come from anywhere.
_fake_queue = pd.DataFrame([dict(Panel_ID="PX", Review_Mode="OVERLAY",
                                 Review_Subject_SHA256="a" * 64)])
_fake_reviews = pd.DataFrame([dict(Review_ID="R001", Panel_ID="PX",
                                   Review_Subject_SHA256="a" * 64,
                                   Reviewer_ID="RV_H", Decision="APPROVED",
                                   Marks_Checked="CONFIRMED",
                                   Reviewed_At="2026-08-06T10:00:00Z", Note="")])
_fake_reviewers = pd.DataFrame([dict(Reviewer_ID="RV_H",
                                     Reviewer_Record_Type="HUMAN")])
for _label, _have, _ok in (("with the overlay the queue promised", {"OVERLAY"}, True),
                           ("with only a project behind it", {"WPD_PROJECT"}, False),
                           ("with nothing behind it", set(), False)):
    pass
# And a queue row that declares no mode at all - which is what a panel with
# neither artifact would produce - is refused rather than approved.
_blank_mode = pd.DataFrame([dict(Panel_ID="PX", Review_Mode="",
                                 Review_Subject_SHA256="a" * 64)])
_bm_probs = []
check("an approval for a panel that declared no review mode is refused",
      not FIN.approved_panels(
          _fake_reviews, _blank_mode, _fake_reviewers,
          lambda w, c, d: _bm_probs.append(c), today=datetime.date(2026, 8, 6),
          artifact_types={"PX": {"OVERLAY"}})
      and "REVIEW_MODE_UNKNOWN" in _bm_probs, "%s" % _bm_probs)
for _label, _have, _ok in (("with the overlay the queue promised", {"OVERLAY"}, True),
                           ("with only a project behind it", {"WPD_PROJECT"}, False),
                           ("with nothing behind it", set(), False)):
    _probs = []
    _got = FIN.approved_panels(
        _fake_reviews, _fake_queue, _fake_reviewers,
        lambda w, c, d: _probs.append(c), today=datetime.date(2026, 8, 6),
        artifact_types={"PX": _have})
    check("an OVERLAY approval %s -> %s" % (_label, "approved" if _ok else "refused"),
          bool(_got) == _ok
          and (_ok or "REVIEW_ARTIFACT_MISSING" in _probs), "%s" % _probs)


print("overplotting with nothing to check the count against is not computed")
# The audit detected a blob too wide to be one marker and set
# Overplotting_Possible=TRUE - and then the runner computed the association
# anyway, because only a COUNT MISMATCH halted it. With no declared n there is
# no count to mismatch, so an r of 0.99 reached MACHINE_QC_PASSED off a cloud
# that may have had points hidden inside other points.
_OVER_IMG = os.path.join(IMAGES, "scatter_overplot.png")
_oim = Image.open(SCAT_IMG).convert("RGB")
_od = ImageDraw.Draw(_oim)
_opx, _opy = SX_CAL.value_to_pixel(4.4), SY_CAL.value_to_pixel(9.6)
_od.ellipse((_opx - 10, _opy - 10, _opx + 10, _opy + 10), fill=BLUE)
_oim.save(_OVER_IMG)
_over_panels = edited(PANELS, {"Panel_ID": "P_SCAT"}, Image_Path=_OVER_IMG)
_over_sfigs = [dict(f, Source_Image=_OVER_IMG,
                    Source_Image_SHA256=MR.sha256_of(_OVER_IMG))
               if f["Source_Figure_ID"] == "SF2" else f for f in SOURCE_FIGURES]
for _label, _n, _want in (("with no declared n", "", "MANUAL_POINT_READ"),
                          ("with a matching declared n", len(SCATTER_XY), "AUTO_PASS")):
    _od_dir = os.path.join(ROOT, "overplot_%s" % (_n or "none"))
    _omd = write_manifests(
        os.path.join(_od_dir, "manifests"), panels=_over_panels,
        source_figures=_over_sfigs,
        units=edited(UNITS, {"Unit_ID": "U_SCAT"}, N_Outcome=_n))
    _osum = RB.run_batch(_omd, os.path.join(_od_dir, "out"), file_root=ROOT,
                         run_date="2026-08-06")
    _orun = pd.read_csv(os.path.join(_od_dir, "out", "run_manifest.csv"),
                        dtype=object).fillna("")
    _ostate = dict(zip(_orun["Panel_ID"], _orun["Run_State"]))
    check("a blob too wide to be one marker %s -> %s" % (_label, _want),
          _ostate["P_SCAT"] == _want,
          "%s | %s" % (_ostate.get("P_SCAT"),
                       dict(zip(_orun["Panel_ID"], _orun["Detail"])).get("P_SCAT")))
    _ovals = pd.read_csv(os.path.join(_od_dir, "out", "figure_values_raw.csv"),
                         dtype=object).fillna("")
    _scat_rows = _ovals[_ovals["Unit_ID"] == "U_SCAT"]
    if _want == "MANUAL_POINT_READ":
        check("  and no association was computed from it",
              not len(_scat_rows), "%d rows" % len(_scat_rows))
        # Nothing may be left on disk that the ledger does not name: the point
        # files used to be written inside the series loop, so a panel a later
        # series sent to manual left JSONs nothing referenced.
        _oart = pd.read_csv(os.path.join(_od_dir, "out", "panel_artifacts.csv"),
                            dtype=object).fillna("")
        _ledgered = {os.path.basename(p) for p in _oart["Artifact_Path"]}
        _on_disk = set(os.listdir(os.path.join(_od_dir, "out", "raw")))
        check("  and the run left no point file the ledger does not name",
              _on_disk <= _ledgered, "%s" % sorted(_on_disk - _ledgered))
    else:
        check("  and a corroborated count still yields its association",
              len(_scat_rows) == 1
              and _scat_rows.iloc[0]["Overplotting_Possible"] == "TRUE",
              "%s" % _scat_rows.to_dict("records"))


print("a run leaves nothing on disk its ledger does not name")
# The point files were written inside the per-series loop, so a two-series
# scatter whose SECOND series could not be reconciled returned
# MANUAL_POINT_READ with the FIRST series' point JSON already on disk - a file
# the run produced, that no ledger names, that no run row references, and that
# a later reader would find sitting in raw/ looking like data.
_TWO_IMG = os.path.join(IMAGES, "scatter_two_series.png")
_tim = Image.new("RGB", (800, 520), "white")
_td = ImageDraw.Draw(_tim)
for _x, _y in SCATTER_XY:
    _px, _py = SX_CAL.value_to_pixel(_x), SY_CAL.value_to_pixel(_y)
    _td.ellipse((_px - 5, _py - 5, _px + 5, _py + 5), fill=BLUE)
_RED_XY = [(0.9, 2.0), (2.0, 3.1), (3.1, 4.0), (4.2, 5.4), (5.3, 6.1),
           (6.4, 7.7), (7.5, 8.2), (8.6, 9.9)]
for _i, (_x, _y) in enumerate(_RED_XY):
    _px, _py = SX_CAL.value_to_pixel(_x), SY_CAL.value_to_pixel(_y)
    # One red marker twice the size: a blob too wide to be a single point.
    _r = 10 if _i == 3 else 5
    _td.ellipse((_px - _r, _py - _r, _px + _r, _py + _r), fill=RED)
_tim.save(_TWO_IMG)
_two_grids = GRIDS + [dict(Grid_ID="G_TWO", Factor_Name="ARM", Factor_Level=lv,
                           Level_Order=i, Note="")
                      for i, lv in enumerate(("BLUE", "RED"))]
_two_units = UNITS + [unit("U_TWO", "G_TWO", "ASSOCIATION",
                           Bar_Top_Definition="NOT_A_BAR",
                           Errorbar_Stem_Confirmed="NOT_A_BAR", Dispersion_Type="",
                           N_Outcome="",
                           Errorbar_Definition_Source="NO_ERRORBAR")]
_two_panels = PANELS + [panel("P_TWO", "U_TWO", "SCATTER", _TWO_IMG,
                              (70, 730, 40, 460), Axis_X_Ticks=SX_TICKS,
                              Axis_Y_Ticks=SY_TICKS, Association_Type="PEARSON_R",
                              Config_ID="C_SCATTER", Source_Panel_ID="P_TWO")]
_two_series = SERIES + [series("P_TWO", "S_B2", "BLUE", Colour_Hex="#2d50dc"),
                        series("P_TWO", "S_R2", "RED", Colour_Hex="#d72d2d")]
_two_sfigs = SOURCE_FIGURES + [dict(
    Source_Figure_ID="SF5", Source_Document_ID="SD1", Publication_ID=1,
    Figure_Number="FIG5", Source_File="synthetic.pdf", Source_Page=1,
    Source_Image=_TWO_IMG, Source_Image_SHA256=MR.sha256_of(_TWO_IMG),
    Observed_Panel_Count=1, Inventory_Status="VISUALLY_VERIFIED",
    Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="one visible axes region")]
_two_spanels = SOURCE_PANELS + [dict(
    Source_Panel_ID="P_TWO", Source_Figure_ID="SF5", Panel_Label="P_TWO",
    Outcome_Label="Heart-rate association", Target_Status="TARGET",
    Panel_Disposition="ASSOCIATION_EXTRACT", Disposition_Reason="configured",
    Note="")]
_two_docs = [dict(d, Observed_Figure_Count=5) for d in SOURCE_DOCUMENTS]
_two_md = write_manifests(os.path.join(ROOT, "twoseries", "manifests"),
                          panels=_two_panels, series_rows=_two_series,
                          units=_two_units, grids=_two_grids,
                          source_figures=_two_sfigs, source_panels=_two_spanels,
                          source_documents=_two_docs)
_two_out = os.path.join(ROOT, "twoseries", "out")
_two_sum = RB.run_batch(_two_md, _two_out, file_root=ROOT, run_date="2026-08-06")
_two_run = pd.read_csv(os.path.join(_two_out, "run_manifest.csv"),
                       dtype=object).fillna("")
_two_state = dict(zip(_two_run["Panel_ID"], _two_run["Run_State"]))
# The same panel, but with the second series too SPARSE rather than
# unreconcilable. This exit ran AFTER the point files were written, so the
# first series' JSON was on disk, named by no ledger and referenced by no run
# row, while `missing` held only the sparse series - so the queue told a hand
# digitizer to read series B and said nothing about series A, whose numbers had
# just been discarded. Cells_Read said 1; figure_values_raw.csv had none.
_SHORT_IMG = os.path.join(IMAGES, "scatter_short.png")
_sim = Image.new("RGB", (800, 520), "white")
_sd = ImageDraw.Draw(_sim)
for _x, _y in SCATTER_XY:
    _px, _py = SX_CAL.value_to_pixel(_x), SY_CAL.value_to_pixel(_y)
    _sd.ellipse((_px - 5, _py - 5, _px + 5, _py + 5), fill=BLUE)
for _x, _y in ((1.0, 2.0), (5.0, 6.0)):     # two red points: below the minimum
    _px, _py = SX_CAL.value_to_pixel(_x), SY_CAL.value_to_pixel(_y)
    _sd.ellipse((_px - 5, _py - 5, _px + 5, _py + 5), fill=RED)
_sim.save(_SHORT_IMG)
_short_md = write_manifests(
    os.path.join(ROOT, "shortseries", "manifests"),
    panels=[dict(p, Image_Path=_SHORT_IMG) if p["Panel_ID"] == "P_TWO" else p
            for p in _two_panels],
    series_rows=_two_series, units=_two_units, grids=_two_grids,
    source_figures=[dict(f, Source_Image=_SHORT_IMG,
                         Source_Image_SHA256=MR.sha256_of(_SHORT_IMG))
                    if f["Source_Figure_ID"] == "SF5" else f for f in _two_sfigs],
    source_panels=_two_spanels, source_documents=_two_docs)
_short_out = os.path.join(ROOT, "shortseries", "out")
RB.run_batch(_short_md, _short_out, file_root=ROOT, run_date="2026-08-06")
_sh_run = pd.read_csv(os.path.join(_short_out, "run_manifest.csv"),
                      dtype=object).fillna("")
_sh = _sh_run[_sh_run["Panel_ID"] == "P_TWO"].iloc[0]
_sh_vals = pd.read_csv(os.path.join(_short_out, "figure_values_raw.csv"),
                       dtype=object).fillna("")
_sh_art = pd.read_csv(os.path.join(_short_out, "panel_artifacts.csv"),
                      dtype=object).fillna("")
_sh_q = pd.read_csv(os.path.join(_short_out, "manual_queue.csv"),
                    dtype=object).fillna("")
_sh_cells = pd.read_csv(os.path.join(_short_out, "manual_queue_cells.csv"),
                        dtype=object).fillna("")
_sh_raw = sorted(f for f in os.listdir(os.path.join(_short_out, "raw"))
                 if f.startswith("P_TWO"))
check("one sparse series sends the whole panel to a person",
      _sh["Run_State"] == "MANUAL_POINT_READ", "%s" % _sh["Run_State"])
check("  and the panel reports nothing read, because nothing was kept",
      _sh["Cells_Read"] == "0" and not len(_sh_vals[_sh_vals["Unit_ID"] == "U_TWO"]),
      "Cells_Read=%s, %d value rows"
      % (_sh["Cells_Read"], len(_sh_vals[_sh_vals["Unit_ID"] == "U_TWO"])))
check("  and no point file was written for the series that could have passed",
      not _sh_raw, "%s" % _sh_raw)
check("  and the ledger names no artifact for the panel",
      not len(_sh_art[_sh_art["Panel_ID"] == "P_TWO"]),
      "%s" % _sh_art[_sh_art["Panel_ID"] == "P_TWO"].to_dict("records"))
check("  and EVERY declared cell is queued for hand reading, not just the sparse one",
      set(_sh_cells[_sh_cells["Panel_ID"] == "P_TWO"]["Cell_Key"])
      == {GE.fig_cell_key({"ARM": lv}) for lv in ("BLUE", "RED")},
      "%s" % sorted(_sh_cells[_sh_cells["Panel_ID"] == "P_TWO"]["Cell_Key"]))
check("  and the count agrees with the cell ledger",
      _sh_q[_sh_q["Panel_ID"] == "P_TWO"]["Missing_Cell_Count"].iloc[0] == "2",
      "%s" % _sh_q[_sh_q["Panel_ID"] == "P_TWO"].to_dict("records"))

check("one unreconcilable series sends the whole panel to a person",
      _two_state.get("P_TWO") == "MANUAL_POINT_READ",
      "%s | %s" % (_two_state.get("P_TWO"),
                   dict(zip(_two_run["Panel_ID"], _two_run["Detail"])).get("P_TWO")))
_two_art = pd.read_csv(os.path.join(_two_out, "panel_artifacts.csv"),
                       dtype=object).fillna("")
_two_ledgered = {os.path.basename(p) for p in _two_art["Artifact_Path"]}
_two_on_disk = set(os.listdir(os.path.join(_two_out, "raw")))
check("and the series that DID reconcile left no unledgered point file",
      not any(f.startswith("P_TWO") for f in _two_on_disk - _two_ledgered),
      "%s on disk, ledger has %s"
      % (sorted(f for f in _two_on_disk if f.startswith("P_TWO")),
         sorted(f for f in _two_ledgered if f.startswith("P_TWO"))))
check("and nothing in raw/ anywhere is missing from the ledger",
      _two_on_disk <= _two_ledgered, "%s" % sorted(_two_on_disk - _two_ledgered))


print("one panel, one terminal state, in every file that names it")
# A panel that read most of its cells returns AUTO_PASS with a missing list, so
# it entered the manual queue as AUTO_PASS. The grid gate then found the same
# missing cells, flipped the run row to QC_FAILED, and APPENDED a second queue
# row - with the removed `Missing_Cells` key, so its count came out blank. One
# panel, two rows, two contradictory states, and `manual_queue_cells.csv`
# filing the missing cells under the state `run_manifest.csv` had withdrawn.
_PART_IMG = os.path.join(IMAGES, "partial_line.png")
_pim = Image.open(LINE_IMG).convert("RGB")
# Erase the last two timepoints, so the panel reads four of its eight cells.
ImageDraw.Draw(_pim).rectangle((XS[-2] - 20, 30, 700, 470), fill="white")
_pim.save(_PART_IMG)
_part_panels = edited(PANELS, {"Panel_ID": "P_LINE"}, Image_Path=_PART_IMG)
_part_sfigs = [dict(f, Source_Image=_PART_IMG,
                    Source_Image_SHA256=MR.sha256_of(_PART_IMG))
               if f["Source_Figure_ID"] == "SF1" else f for f in SOURCE_FIGURES]
_pmd = write_manifests(os.path.join(ROOT, "partial", "manifests"),
                       panels=_part_panels, source_figures=_part_sfigs)
_psum = RB.run_batch(_pmd, os.path.join(ROOT, "partial", "out"), file_root=ROOT,
                     run_date="2026-08-06")
_pq = pd.read_csv(os.path.join(ROOT, "partial", "out", "manual_queue.csv"),
                  dtype=object).fillna("")
_pr = pd.read_csv(os.path.join(ROOT, "partial", "out", "run_manifest.csv"),
                  dtype=object).fillna("")
_pc = pd.read_csv(os.path.join(ROOT, "partial", "out", "manual_queue_cells.csv"),
                  dtype=object).fillna("")
_pstate = dict(zip(_pr["Panel_ID"], _pr["Run_State"]))
check("the fixture really produces a partial read",
      _pstate["P_LINE"] == "QC_FAILED"
      and 0 < len(_pc[_pc["Panel_ID"] == "P_LINE"]) < 8,
      "%s / %d cells" % (_pstate.get("P_LINE"), len(_pc[_pc["Panel_ID"] == "P_LINE"])))
check("the manual queue names each panel exactly once",
      list(_pq[_pq["Panel_ID"] != ""]["Panel_ID"]).count("P_LINE") == 1,
      "%s" % _pq[["Panel_ID", "Run_State", "Missing_Cell_Count"]].to_dict("records"))
check("and the state it gives is the one the run manifest ended on",
      set(_pq[_pq["Panel_ID"] == "P_LINE"]["Run_State"]) == {_pstate["P_LINE"]},
      "%s vs %s" % (set(_pq[_pq["Panel_ID"] == "P_LINE"]["Run_State"]),
                    _pstate["P_LINE"]))
check("the missing cells survive the state change rather than being blanked",
      _pq[_pq["Panel_ID"] == "P_LINE"]["Missing_Cell_Count"].iloc[0]
      == str(len(_pc[_pc["Panel_ID"] == "P_LINE"])),
      "%r vs %d cells"
      % (_pq[_pq["Panel_ID"] == "P_LINE"]["Missing_Cell_Count"].iloc[0],
         len(_pc[_pc["Panel_ID"] == "P_LINE"])))
check("and the cell ledger agrees with the state too",
      set(_pc[_pc["Panel_ID"] == "P_LINE"]["Run_State"]) == {_pstate["P_LINE"]},
      "%s" % set(_pc[_pc["Panel_ID"] == "P_LINE"]["Run_State"]))
check("every queued panel's state matches the run manifest, not just this one",
      all(_pstate[p] == s for p, s in zip(_pq["Panel_ID"], _pq["Run_State"]) if p),
      "%s" % [(p, s, _pstate.get(p)) for p, s in
              zip(_pq["Panel_ID"], _pq["Run_State"]) if p and _pstate.get(p) != s])
check("and the count column stays a whole number of cells",
      all(v == "" or v.isdigit() for v in _pq["Missing_Cell_Count"]),
      "%s" % list(_pq["Missing_Cell_Count"]))


print("a mask name in the wrong case is a manifest problem, not a batch abort")
# `Mask_Key` chose one of the reader's three built-in masks and nothing checked
# it against them. The masks are keyed in lower case, so `Mask_Key=BLUE` - the
# obvious way to write it, and the way every other vocabulary column in these
# manifests is written - validated, reached `masks["BLUE"]` inside the reader,
# raised KeyError, and became an InternalReaderError. That aborts the ENTIRE
# batch: 115 other publications stop because one manifest cell has capitals.
#
# The raster is the frozen bar fixture the reader suite measures against, so
# the numbers below are known independently of this file.
_BARIMG = os.path.join(IMAGES, "bar_fixture.png")
shutil.copy2(os.path.join(HERE, "bar_fixture.png"), _BARIMG)
_BARTRUTH = json.load(open(os.path.join(HERE, "bar_fixture_truth.json")))
_BAR_SESSIONS = sorted({b["session"] for b in _BARTRUTH["bars"]},
                       key=lambda s: min(b["x_pixel"] for b in _BARTRUTH["bars"]
                                         if b["session"] == s))
_BAR_ANCHOR = {s: sum(b["x_pixel"] for b in _BARTRUTH["bars"] if b["session"] == s)
               / sum(1 for b in _BARTRUTH["bars"] if b["session"] == s)
               for s in _BAR_SESSIONS}
_BAR_MEAN = {(b["series"], b["session"]): b["true_mean"] for b in _BARTRUTH["bars"]}

_bar_panels = [panel("P_BAR", "U_BAR", "BAR_COLOR", _BARIMG,
                     tuple(_BARTRUTH["panel_box"]), Figure_ID="F_BAR",
                     Source_Panel_ID="P_BAR", Baseline_Value="0",
                     Axis_Y_Ticks=";".join("%g:%g" % (v, y)
                                           for v, y in _BARTRUTH["ticks"]),
                     Config_ID="C_BAR")]
_bar_units = [unit("U_BAR", "G_BAR", "CONTINUOUS", Figure_ID="F_BAR",
                   Bar_Top_Definition="OUTLINE_CENTER",
                   Errorbar_Stem_Confirmed="TRUE", Dispersion_Type="SD",
                   Errorbar_Definition_Source="caption: mean +/- SD",
                   Axis_Calib_Y1_Value=_BARTRUTH["ticks"][0][0],
                   Axis_Calib_Y1_Pixel=_BARTRUTH["ticks"][0][1],
                   Axis_Calib_Y2_Value=_BARTRUTH["ticks"][-1][0],
                   Axis_Calib_Y2_Pixel=_BARTRUTH["ticks"][-1][1])]
_bar_grids = [dict(Grid_ID="G_BAR", Factor_Name=f, Factor_Level=lv,
                   Level_Order=i, Note="")
              for f, levels in (("ARM", ["SUPINE", "ORTHOSTASIS"]),
                                ("TIMEPOINT", _BAR_SESSIONS))
              for i, lv in enumerate(levels)]
_bar_positions = [
    dict(Panel_ID="P_BAR", Position_ID=s, X_Pixel=_BAR_ANCHOR[s], Slot_Index=i,
         Display_Order=i, Factor_Name="TIMEPOINT", Factor_Level=s,
         Timepoint_Label=s, Timepoint_Days=i * 7, Note="")
    for i, s in enumerate(_BAR_SESSIONS)]
_bar_figures = [dict(Figure_ID="F_BAR", Publication_ID=1,
                     Source_Figure_ID="SF_BAR", Figure_Number="FIGBAR",
                     Source_File="synthetic.pdf", Source_Page=1,
                     Source_Image=_BARIMG,
                     Source_Image_SHA256=MR.sha256_of(_BARIMG),
                     Panel_Count_Declared=1, Panel_Count_Observed=1,
                     Panel_Count_Reconciliation="MATCHED",
                     Unlisted_Panels="", Note="")]
_bar_sfigs = [dict(Source_Figure_ID="SF_BAR", Source_Document_ID="SD1",
                   Publication_ID=1, Figure_Number="FIGBAR",
                   Source_File="synthetic.pdf", Source_Page=1,
                   Source_Image=_BARIMG,
                   Source_Image_SHA256=MR.sha256_of(_BARIMG),
                   Observed_Panel_Count=1, Inventory_Status="VISUALLY_VERIFIED",
                   Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
                   Inspection_Date="2026-08-06", Note="one visible axes region")]
_bar_spanels = [dict(Source_Panel_ID="P_BAR", Source_Figure_ID="SF_BAR",
                     Panel_Label="P_BAR", Outcome_Label="Heart rate",
                     Target_Status="TARGET", Panel_Disposition="AUTO_DIGITIZE",
                     Disposition_Reason="reader configured", Note="")]
_bar_docs = [dict(d, Observed_Figure_Count=1) for d in SOURCE_DOCUMENTS]


def _mask_run(spelling, name):
    rows = [series("P_BAR", "S_SUP", "SUPINE", Mask_Key=spelling),
            series("P_BAR", "S_ORT", "ORTHOSTASIS", Mask_Key="red")]
    md = write_manifests(
        os.path.join(ROOT, name, "manifests"), panels=_bar_panels,
        series_rows=rows, positions=_bar_positions, units=_bar_units,
        grids=_bar_grids, figures=_bar_figures, source_figures=_bar_sfigs,
        source_panels=_bar_spanels, source_documents=_bar_docs,
        configs=[dict(Config_ID="C_BAR", Option="colour_tolerance",
                      Value="70", Note="")])
    try:
        summary = RB.run_batch(md, os.path.join(ROOT, name, "out"),
                               file_root=ROOT, run_date="2026-08-06")
    except Exception as exc:
        # A reader that cannot find a declared mask aborts the whole batch as
        # an InternalReaderError. Catching it here is how this scenario reports
        # "the batch died" rather than taking the suite down with it.
        summary = dict(status="RAISED %s: %s" % (type(exc).__name__, exc))
    return summary, os.path.join(ROOT, name, "out")


_mask_means = {}
for _spelling in ("blue", "BLUE", " Blue "):
    _bs, _bout = _mask_run(_spelling, "maskrun_%d" % (abs(hash(_spelling)) % 10 ** 6))
    check("Mask_Key=%r runs instead of aborting the batch" % _spelling,
          _bs["status"] == "RAN", "%s" % _bs)
    if _bs["status"] != "RAN":
        check("  and reads all twelve bars (%r)" % _spelling, False, "%s" % _bs)
        check("  and recovers the fixture's true means (%r)" % _spelling, False,
              "%s" % _bs)
        continue
    _brun = pd.read_csv(os.path.join(_bout, "run_manifest.csv"),
                        dtype=object).fillna("")
    check("  and reads all twelve bars (%r)" % _spelling,
          int(_brun.loc[0, "Cells_Read"]) == 12, "%s" % _brun.loc[0].to_dict())
    _bv = pd.read_csv(os.path.join(_bout, "figure_values_raw.csv"),
                      dtype=object).fillna("")
    _mask_means[_spelling] = {r["Cell_Key"]: round(float(r["Mean"]), 6)
                              for _, r in _bv.iterrows()}
    _err = max(abs(float(r["Mean"]) - _BAR_MEAN[(
        dict(p.split("=") for p in r["Cell_Key"].split(";"))["ARM"],
        dict(p.split("=") for p in r["Cell_Key"].split(";"))["TIMEPOINT"])])
        for _, r in _bv.iterrows())
    check("  and recovers the fixture's true means (%r)" % _spelling, _err < 1.0,
          "max %.3f" % _err)
check("the spelling of the mask changes nothing about the numbers",
      len({tuple(sorted(v.items())) for v in _mask_means.values()}) == 1,
      "%s" % {k: sorted(v.items())[:1] for k, v in _mask_means.items()})


print("a run with nothing automatic in it is still fully audited")
# The figure manifest's WRITE sat inside `if projects_by_panel and ...`, so a
# batch where every panel was manual or unreadable produced no
# `figure_manifest.csv` at all - while CANONICAL_OUTPUTS and the documentation
# both call it a run output. The runs with nothing automatic in them are
# exactly the ones somebody audits by hand.
_am_md = write_manifests(os.path.join(ROOT, "allmanual", "manifests"),
                         panels=[dict(p, Panel_Mode="MANUAL") for p in PANELS])
_am_out = os.path.join(ROOT, "allmanual", "out")
_am = RB.run_batch(_am_md, _am_out, file_root=ROOT, run_date="2026-08-06")
check("an all-manual batch still runs",
      _am["status"] == "RAN" and set(_am["states"]) == {"MANUAL_POINT_READ"},
      "%s" % _am)
check("  and it produced no WPD project at all, which is the trigger",
      not os.path.exists(os.path.join(_am_out, "projects"))
      or not os.listdir(os.path.join(_am_out, "projects")),
      "%s" % (os.path.exists(os.path.join(_am_out, "projects"))
              and os.listdir(os.path.join(_am_out, "projects"))))
_am_missing = [f for f in RB.CANONICAL_OUTPUTS
               if f not in ("figure_values_accepted.csv", "finalize_stamp.json",
                            "figure_values.csv", "manifest_problems.csv",
                            # Written only when the batch holds a BAR_MONO
                            # panel, and on the cleanup list regardless: a
                            # previous run's geometry file left beside this
                            # run's numbers is the thing that must not survive.
                            "mono_bar_geometry.csv")
               and not os.path.exists(os.path.join(_am_out, f))]
check("  and every canonical output a completed run owns is on disk",
      not _am_missing, "%s" % _am_missing)
_am_fig = pd.read_csv(os.path.join(_am_out, "figure_manifest.csv"),
                      dtype=object).fillna("")
check("  including the figure manifest, with its rows intact",
      set(_am_fig["Figure_ID"]) == {f["Figure_ID"] for f in FIGURES},
      "%s" % sorted(set(_am_fig["Figure_ID"])))


print("a run's overlay failures are its own")
# `_FAILURES` is module state with no reset, and an agent working through 116
# publications in one process is the normal case - so the second run's stamp
# inherited the first run's "3 overlays could not be drawn", naming panels that
# run never saw.
RB.OVERLAY._FAILURES.append("leftover_from_a_previous_publication.png: boom")
check("the fixture really seeds a stale failure",
      any("leftover" in f for f in RB.OVERLAY.failures()))
_clean_md = write_manifests(os.path.join(ROOT, "freshfail", "manifests"))
RB.run_batch(_clean_md, os.path.join(ROOT, "freshfail", "out"), file_root=ROOT,
             run_date="2026-08-06")
_fresh_stamp = json.load(open(os.path.join(ROOT, "freshfail", "out",
                                           "run_stamp.json")))
check("a new run does not inherit the last one's overlay failures",
      "leftover" not in _fresh_stamp.get("Detail", ""),
      "%r" % _fresh_stamp.get("Detail"))
check("and the module state is the run's own by the end of it",
      not any("leftover" in f for f in RB.OVERLAY.failures()),
      "%s" % RB.OVERLAY.failures()[:2])


print("a channel for identities the reader cannot measure")
# Publication 127 prints two bars fifteen pixels tall: a mean, an SE, and no
# interior to sample. A BAR_MONO series is identified by its fill, so naming
# them from the pixels would mean "first slot, therefore OPEN" - identity by
# position. A person names them instead, and the naming is an INPUT with its own
# evidence, not a decision folded into an approval: an approval says "the number
# the reader produced is right" and this says "here is something the reader did
# not produce".
_ir = BM.identity_resolution_columns()
check("the identity channel is a manifest of its own",
      "identity_resolution" in dict(BM.BATCH_TEMPLATES), "%s" % (BM.BATCH_TEMPLATES,))
check("it is keyed by the geometry the reader DID produce",
      all(c in _ir for c in ("Panel_ID", "Group_ID", "Geometry_Slot")), "%s" % _ir)
check("and it names a series rather than a slot order",
      "Resolved_Series_ID" in _ir and not [c for c in _ir if "Order" in c], "%s" % _ir)
check("every resolution says where the identity came from",
      all(c in _ir for c in ("Evidence_Type", "Evidence_Artifact",
                             "Evidence_Artifact_SHA256")), "%s" % _ir)
check("and who said so, and when",
      all(c in _ir for c in ("Reviewer_ID", "Reviewed_At")), "%s" % _ir)
check("a reviewer's own reading is one evidence type among several, not the only one",
      set(BM.HUMAN_IDENTITY_EVIDENCE) == {"LEGEND_DECLARED", "TEXT_DECLARED",
                                          "REVIEWER_INSPECTION"},
      "%s" % (BM.HUMAN_IDENTITY_EVIDENCE,))
# REVERT: one enum holding both halves. A person can then type FILL_MEASURED
# into identity_resolution.csv for a cell where the reader explicitly could NOT
# measure a fill, and the record says an automatic measurement was made.
check("what the reader produces is not what a person may enter",
      "FILL_MEASURED" in BM.AUTO_IDENTITY_EVIDENCE
      and "FILL_MEASURED" not in BM.HUMAN_IDENTITY_EVIDENCE,
      "%s / %s" % (BM.AUTO_IDENTITY_EVIDENCE, BM.HUMAN_IDENTITY_EVIDENCE))
check("and the two halves together are the whole vocabulary",
      set(BM.IDENTITY_EVIDENCE) == set(BM.AUTO_IDENTITY_EVIDENCE)
      | set(BM.HUMAN_IDENTITY_EVIDENCE))
# REVERT: read the trust order off the tuple. Its last entry is the WEAKEST
# evidence there is - a reviewer's own reading, with no legend and no sentence
# behind it - so tuple position says the opposite of the truth.
check("the trust order is written out, not implied by tuple position",
      BM.IDENTITY_EVIDENCE_RANK["REVIEWER_INSPECTION"]
      < BM.IDENTITY_EVIDENCE_RANK["TEXT_DECLARED"]
      < BM.IDENTITY_EVIDENCE_RANK["LEGEND_DECLARED"]
      < BM.IDENTITY_EVIDENCE_RANK["FILL_MEASURED"],
      "%s" % (BM.IDENTITY_EVIDENCE_RANK,))
check("the artifact is hashed, so a resolution cannot change after approval",
      "Evidence_Artifact_SHA256" in _ir)

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
