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

REVIEWERS = [dict(
    Reviewer_ID="RV_T1", Reviewer_Name="Test Fixture", Contact_Type="EMAIL",
    Reviewer_Contact="fixture@example.org", Registered_By="Test Fixture",
    Registration_Date="2026-08-01", Human_Attestation="HUMAN_CONFIRMED",
    Note="synthetic regression reviewer")]

SOURCE_DOCUMENTS = [dict(
    Source_Document_ID="SD1", Publication_ID=1, Document_Role="MAIN_ARTICLE",
    Source_File="synthetic.pdf", Article_Page_Range="1-1",
    Observed_Figure_Count=1, Inventory_Status="VISUALLY_VERIFIED",
    Figure_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="one synthetic source figure")]

SOURCE_FIGURES = [dict(
    Source_Figure_ID="SF1", Source_Document_ID="SD1",
    Publication_ID=1, Figure_Number="FIG1",
    Source_File="synthetic.pdf", Source_Page=1, Source_Image=LINE_IMG,
    Observed_Panel_Count=4, Inventory_Status="VISUALLY_VERIFIED",
    Panel_Count_Method="HUMAN_VISUAL", Reviewer_ID="RV_T1",
    Inspection_Date="2026-08-06", Note="four visible axes regions")]

SOURCE_PANELS = [dict(
    Source_Panel_ID=pid, Source_Figure_ID="SF1", Panel_Label=pid,
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
    unit("U_SCAT", "G_ONE", "ASSOCIATION", Bar_Top_Definition="NOT_A_BAR",
         Errorbar_Stem_Confirmed="NOT_A_BAR", Dispersion_Type="",
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
          Contact_Type="ORCID", Reviewer_Contact="0000-0002-1825-0097",
          Registered_By="Test Fixture", Registration_Date="2026-08-01",
          Human_Attestation="HUMAN_CONFIRMED", Note="")]) == [],
      "%s" % validate(reviewers=REVIEWERS + [dict(
          Reviewer_ID="RV_T2", Reviewer_Name="Second Extractor",
          Contact_Type="ORCID", Reviewer_Contact="0000-0002-1825-0097",
          Registered_By="Test Fixture", Registration_Date="2026-08-01",
          Human_Attestation="HUMAN_CONFIRMED", Note="")]))

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
        # n_slots is a BAR_COLOR keyword. read_monochrome_bar_panel derives its
        # slot count from the declared series and has no such parameter, so
        # accepting it here bought a TypeError at run time reported as a figure
        # problem.
        ("n_slots on a monochrome bar panel",
         dict(panels=edited(PANELS, {"Panel_ID": "P_LINE"}, Mark_Type="BAR_MONO",
                            Config_ID="C_MONO"),
              series_rows=[dict(r, Colour_Hex="", Bar_Fill_Pattern=(
                  "SOLID" if r["Series_ID"] == "S_BLUE" else "HATCHED"))
                  if r["Panel_ID"] == "P_LINE" else r for r in SERIES],
              configs=CONFIGS + [dict(Config_ID="C_MONO", Option="n_slots",
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
accepted = pd.read_csv(os.path.join(ODIR, "figure_values_accepted.csv"), dtype=object).fillna("")
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

print("nothing unaccepted can reach master by reading one file")
check("there is no file called figure_values.csv at all",
      not os.path.exists(os.path.join(ODIR, "figure_values.csv")),
      "the ambiguous name is back - a downstream reader will pool from it")
check("every raw row carries its own verdict, so no join is needed",
      {"Value_Status", "QC_Codes", "Pooling_Eligible"} <= set(values.columns),
      "%s" % sorted(values.columns)[-4:])
check("every raw status is in the declared vocabulary",
      set(values["Value_Status"]) <= {"ACCEPTED", "QC_FAILED", "PANEL_NOT_PASSED"},
      "%s" % sorted(set(values["Value_Status"])))
check("Pooling_Eligible is TRUE exactly when the status is ACCEPTED",
      all((r["Pooling_Eligible"] == "TRUE") == (r["Value_Status"] == "ACCEPTED")
          for _, r in values.iterrows()))
check("the accepted file is the eligible subset, nothing more",
      len(accepted) == sum(values["Pooling_Eligible"] == "TRUE")
      and set(accepted["Cell_Key"]) ==
      set(values[values["Pooling_Eligible"] == "TRUE"]["Cell_Key"]),
      "%d vs %d" % (len(accepted), sum(values["Pooling_Eligible"] == "TRUE")))
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
_acc = pd.read_csv(os.path.join(_o, "figure_values_accepted.csv"),
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
_acc = pd.read_csv(os.path.join(_o, "figure_values_accepted.csv"),
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
check("the first run leaves an accepted file with rows in it",
      _first["accepted"] > 0
      and len(pd.read_csv(os.path.join(_seq, "figure_values_accepted.csv"))) > 0,
      "%s" % _first)
_bad_seq = write_manifests(
    os.path.join(ROOT, "m_seq_bad"),
    configs=CONFIGS + [dict(Config_ID="C_DEFAULT", Option="x_window",
                            Value="14", Note="")])
_second = RB.run_batch(_bad_seq, _seq, file_root=ROOT, run_date="2026-08-07")
check("the second run is rejected", _second["status"] == "MANIFEST_REJECTED",
      "%s" % _second)
for _name in ("figure_values_accepted.csv", "figure_values_raw.csv",
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
      {"figure_values_accepted.csv", "figure_values_raw.csv", "run_manifest.csv",
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
      len(pd.read_csv(os.path.join(_load, "figure_values_accepted.csv"))) > 0)

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
    for _f in ("figure_values_accepted.csv", "figure_values_raw.csv",
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
      {"RAN", "MANIFEST_REJECTED", "INPUT_LOAD_FAILED", "PROMOTE_FAILED"}
      == set(RB.RUN_STATUSES), "%s" % sorted(RB.RUN_STATUSES))


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
      RB.COMMIT_MARKER == "figure_values_accepted.csv", RB.COMMIT_MARKER)

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
# Two files in, deliberately: sorted() puts `figure_values_accepted.csv` SECOND
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
_split_source_panels = SOURCE_PANELS + [dict(
    Source_Panel_ID=p, Source_Figure_ID="SF1", Panel_Label=p,
    Outcome_Label="Heart rate", Target_Status="TARGET",
    Panel_Disposition="AUTO_DIGITIZE",
    Disposition_Reason="two-panel one-unit regression fixture", Note="")
    for p in ("P_HALF_A", "P_HALF_B")]
_mdir = write_manifests(os.path.join(ROOT, "m_split"),
                        panels=PANELS + _split_panels,
                        series_rows=SERIES + _split_series,
                        positions=POSITION_ROWS + _split_positions,
                        units=_split_units,
                        source_figures=[dict(SOURCE_FIGURES[0], Observed_Panel_Count=6)],
                        source_panels=_split_source_panels)
_o = os.path.join(ROOT, "o_split")
RB.run_batch(_mdir, _o, file_root=ROOT, run_date="2026-08-06")
_sr = pd.read_csv(os.path.join(_o, "run_manifest.csv"), dtype=object).fillna("")
_sraw = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
_sacc = pd.read_csv(os.path.join(_o, "figure_values_accepted.csv"),
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
      set(stamp["Manifest_SHA256"]) == set(RB.MANIFEST_FILES),
      "%s" % sorted(stamp["Manifest_SHA256"]))
check("each run row carries the image hash it read",
      all(len(h) == 64 for h in run["Image_SHA256"] if h), "%s" % list(run["Image_SHA256"]))

ODIR2 = os.path.join(ROOT, "out2")
RB.run_batch(MDIR, ODIR2, file_root=ROOT, run_date="2026-08-06")
_same = []
for name in ("figure_values_raw.csv", "figure_values_accepted.csv",
             "run_manifest.csv", "manual_queue.csv", "qc_problems.csv"):
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
      and not os.path.exists(os.path.join(ODIR3, "figure_values_raw.csv"))
      and not os.path.exists(os.path.join(ODIR3, "figure_values_accepted.csv")))

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
check("a bar reader pointed at a line panel finds nothing and queues it",
      dict(zip(_r["Panel_ID"], _r["Run_State"]))["P_LINE"] == "MANUAL_POINT_READ",
      "%s" % dict(zip(_r["Panel_ID"], _r["Run_State"])))
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
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
      len(_qrow) and bool(_qrow.iloc[0]["Missing_Cells"]),
      "%s" % (list(_qrow["Missing_Cells"]) if len(_qrow) else "no queue row"))
check("and says why, pointing at where the work stands",
      len(_qrow) and "wip/" in _qrow.iloc[0]["Detail"],
      "%s" % (list(_qrow["Detail"]) if len(_qrow) else ""))
_v = pd.read_csv(os.path.join(_o, "figure_values_raw.csv"), dtype=object).fillna("")
check("it contributes no values at all",
      not len(_v[_v["Unit_ID"] == "U_LINE"]), "%d rows" % len(_v))
check("NO_READER_AVAILABLE is in the declared state vocabulary",
      "NO_READER_AVAILABLE" in BM.RUN_STATES)


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
check("n_slots is offered to BAR_COLOR only",
      BM.READER_OPTIONS["n_slots"][1] == ("BAR_COLOR",),
      "%s" % (BM.READER_OPTIONS["n_slots"][1],))
check("and BAR_MONO derives its slot count from the declared series instead",
      "n_slots" not in inspect.signature(_readers["BAR_MONO"]).parameters)
check("every option has a range check, not just a parser",
      all(callable(v[3]) for v in BM.READER_OPTIONS.values()))
check("an unreleased mark type is named rather than silently unknown",
      "LINE_MONO_STYLE" in BM.UNRELEASED_MARK_TYPES
      and "LINE_MONO_STYLE" not in BM.BATCH_MARK_TYPES)


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
