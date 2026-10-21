"""Scenarios for a MANUAL panel read from `supplied_readings.csv`.

The claim under test (decided 2026-10-18, "1로 가자"): an AI agent may place the
points of a panel no reader can read, the run turns them into values with the
panel's own calibration, and NOTHING about the route into the pool changes - a
registered person still approves the panel's overlay, and because every placed
point is R2 they also confirm, in so many words, that they checked the placed
points (`Inference_Checked`).

So every scenario below is one of three kinds: a reading that must not become a
value (refused before the run), a value that must say who made it and how
(methods, numbers, overlay), and a value that must not reach the pool without the
person (finalize).

And since 2026-10-20 ("이거 내가 추가적으로 찍을 수 있게 해줘"), the same file takes
a point the registered reviewer placed themselves (`Reader_Kind=PERSON`): their
own digitization, `MANUAL_DIGITIZED` and R0, refused unless `Read_By` is a HUMAN
in the registry, and marked `P` on the overlay rather than `@`.
"""
import csv
import datetime
import json
import os
import shutil
import sys
import tempfile

import pandas as pd
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import compile_plan as CP                                          # noqa: E402
import finalize_batch as FIN                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import mark_readers as MR                                          # noqa: E402
import provenance as PROV                                          # noqa: E402
import review_overlay as OVERLAY                                   # noqa: E402
import run_batch as RB                                             # noqa: E402

ROOT = tempfile.mkdtemp(prefix="fdt_supplied_")
FAILURES = []
RAN = []


def check(name, ok, detail=""):
    RAN.append(name)
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "  <- %s" % detail))
    if not ok:
        FAILURES.append(name)


# --------------------------------------------------------------------------
# one figure: two coloured series, four timepoints, error bars both ways
# --------------------------------------------------------------------------
IMG = os.path.join(ROOT, "panel.png")
BLUE, RED = (45, 80, 220), (215, 45, 45)
XS = [140, 240, 340, 440]
LABELS = ["T0", "T1", "T2", "T3"]


def centre(series, i):
    """Where the fixture draws each marker: (x, y)."""
    x = XS[i] + (0 if series == "S_B" else 18)
    return x, 380 - i * 40 - (0 if series == "S_B" else 25)


def draw():
    im = Image.new("RGB", (600, 480), "white")
    d = ImageDraw.Draw(im)
    d.line((100, 40, 100, 440), fill=(0, 0, 0))
    d.line((100, 440, 500, 440), fill=(0, 0, 0))
    for i in range(len(XS)):
        for sid, colour in (("S_B", BLUE), ("S_R", RED)):
            x, y = centre(sid, i)
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=colour)
            d.line((x, y - 22, x, y + 22), fill=colour, width=2)
            d.line((x - 6, y - 22, x + 6, y - 22), fill=colour, width=2)
            d.line((x - 6, y + 22, x + 6, y + 22), fill=colour, width=2)
    im.save(IMG)


draw()
SHA = MR.sha256_of(IMG)
TICKS = "220:40;0:440"


def value_at(px):
    """The fixture's calibration, written out: 0 at row 440, 220 at row 40."""
    return (440.0 - px) * 220.0 / 400.0


SOURCE_PDF = os.path.join(ROOT, "synthetic.pdf")
with open(SOURCE_PDF, "wb") as _fh:
    _fh.write(b"%PDF-1.4\n% synthetic supplied-readings document\n%%EOF\n")
SOURCE_PDF_SHA = MR.sha256_of(SOURCE_PDF)

REVIEWERS = [dict(Reviewer_ID="RV_H", Reviewer_Name="Test Reviewer",
                  Reviewer_Record_Type="HUMAN", Contact_Type="ORCID",
                  Reviewer_Contact="0000-0002-1694-233X",
                  Registered_By="Test Reviewer", Registration_Date="2026-08-01",
                  Human_Attestation="HUMAN_CONFIRMED", Note="")]
SOURCE_DOCUMENTS = [dict(
    Source_Document_ID="SD1", Publication_ID=9, Document_Role="MAIN_ARTICLE",
    Source_File="synthetic.pdf", Source_File_SHA256=SOURCE_PDF_SHA,
    Article_Page_Range="1-1", Observed_Figure_Count=1,
    Inventory_Status="VISUALLY_VERIFIED", Figure_Count_Method="HUMAN_VISUAL",
    Reviewer_ID="RV_H", Inspection_Date="2026-08-06", Note="")]
SOURCE_FIGURES = [dict(
    Source_Figure_ID="SF1", Source_Document_ID="SD1", Publication_ID=9,
    Figure_Number="FIG1", Source_File="synthetic.pdf", Source_Page=1,
    Source_Image=IMG, Source_Image_SHA256=SHA, Observed_Panel_Count=1,
    Inventory_Status="VISUALLY_VERIFIED", Panel_Count_Method="HUMAN_VISUAL",
    Reviewer_ID="RV_H", Inspection_Date="2026-08-06", Note="")]
SOURCE_PANELS = [dict(
    Source_Panel_ID="P1", Source_Figure_ID="SF1", Panel_Label="P1",
    Outcome_Label="Heart rate", Target_Status="TARGET",
    Panel_Disposition="AUTO_DIGITIZE", Disposition_Reason="fixture", Note="")]
FIGURES = [dict(
    Figure_ID="F1", Publication_ID=9, Figure_Number="FIG1",
    Source_File="synthetic.pdf", Source_Page=1, Source_Image=IMG,
    Source_Caption_Verbatim="synthetic panel, mean +/- SD",
    Image_Resolution_Or_Hash="600x480 sha256:" + SHA, WPD_Project_File="",
    Observed_Panel_Count=1, Worklist_Panel_Count=1, Unlisted_Panels="",
    Panel_Reconciliation_Status="MATCHED", Note="")]
GRIDS = ([dict(Grid_ID="G", Factor_Name="ARM", Factor_Level=lv, Level_Order=i,
               Note="") for i, lv in enumerate(("CONTROL", "TREATED"))]
         + [dict(Grid_ID="G", Factor_Name="TIMEPOINT", Factor_Level=lv,
                 Level_Order=i, Note="") for i, lv in enumerate(LABELS)])
UNITS = [dict(
    Unit_ID="U1", Figure_ID="F1", Grid_ID="G",
    Panel_ID="P1", Source_Panel_ID="P1", Panel="P1", Outcome_Name="Heart rate",
    Outcome_Variable="Heart rate", Outcome_Domain="CV_HEMO", Unit="bpm",
    Units="bpm", Statistic_Type="CONTINUOUS", Grid_Rule="FULL",
    Value_Scale="RATIO", Analysis_Transformation="UNTRANSFORMED",
    Distribution_Shape="SYMMETRIC", Transformation_Source="",
    Dispersion_Type="SD", Errorbar_Definition_Source="caption: mean +/- SD",
    N_Outcome=10, N_Source="caption", Extraction_Method="DIGITIZED",
    Bar_Top_Definition="NOT_A_BAR", Errorbar_Stem_Confirmed="TRUE",
    Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
    Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
    Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=500,
    Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=440,
    Axis_Calib_Y2_Value=220, Axis_Calib_Y2_Pixel=40,
    Extractor_1="run_batch", Extractor_2="", Independent_Verification_Status="",
    Discrepancy_Note="", Date="2026-08-06", Note="")]
PANELS = [dict(
    Panel_ID="P1", Source_Panel_ID="P1", Figure_ID="F1", Unit_ID="U1",
    Panel_Label="P1", Mark_Type="LINE_COLOR", Image_Path=IMG,
    Panel_X0=100, Panel_X1=500, Panel_Y0=40, Panel_Y1=440,
    Axis_X_Region="", Axis_Y_Region="", Axis_X_Scale="LINEAR",
    Axis_Y_Scale="LINEAR", Axis_X_Ticks="", Axis_Y_Ticks=TICKS,
    Baseline_Value="", Association_Type="", Config_ID="", Panel_Mode="MANUAL",
    Note="values read by a person (Read_Route=MANUAL)")]
SERIES = [dict(Panel_ID="P1", Series_ID=sid, Colour_Hex="", Colour_Tolerance="",
               Mask_Key="", Marker_Shape="", Marker_Fill="",
               Line_Style="", Bar_Fill_Pattern="", Factor_Name="ARM",
               Factor_Level=lv, Note="legend: %s" % lv)
          for sid, lv in (("S_B", "CONTROL"), ("S_R", "TREATED"))]
POSITIONS = [dict(Panel_ID="P1", Position_ID=q, X_Pixel=x + 9, Slot_Index=i,
                  Display_Order=i, Factor_Name="TIMEPOINT", Factor_Level=q,
                  Timepoint_Label=q, Timepoint_Days=i * 7, Note="")
             for i, (q, x) in enumerate(zip(LABELS, XS))]


def reading(sid, i, **over):
    x, y = centre(sid, i)
    row = dict(Reading_ID="P1__%s__%s" % (sid, LABELS[i]), Panel_ID="P1",
               Series_ID=sid, Position_ID=LABELS[i], Mark_X_Px=x, Mark_Y_Px=y,
               Upper_Y_Px=y - 22, Lower_Y_Px=y + 22, Reader_Kind="AI_AGENT",
               Read_By="claude-opus-5-5", Read_At="2026-10-18",
               Raster_SHA256=SHA, Note="")
    row.update(over)
    return row


READINGS = [reading(sid, i) for sid in ("S_B", "S_R") for i in range(4)]


def write_manifests(directory, **over):
    os.makedirs(directory, exist_ok=True)
    tables = {
        "reviewer_registry": (REVIEWERS, BM.reviewer_registry_columns()),
        "source_document_manifest": (SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
        "source_figure_manifest": (SOURCE_FIGURES, BM.source_figure_manifest_columns()),
        "source_panel_inventory": (SOURCE_PANELS, BM.source_panel_inventory_columns()),
        "figure_manifest": (FIGURES, GE.fig_figure_columns()),
        "grid_definitions": (GRIDS, GE.fig_grid_columns()),
        "unit_manifest": (UNITS, GE.fig_unit_columns()),
        "panel_manifest": (PANELS, BM.panel_manifest_columns()),
        "series_manifest": (SERIES, BM.series_manifest_columns()),
        "position_manifest": (POSITIONS, BM.position_manifest_columns()),
        "reader_config": ([], BM.reader_config_columns()),
        "supplied_readings": (READINGS, BM.supplied_readings_columns()),
    }
    for name, rows in over.items():
        tables[name] = (rows, tables[name][1])
    for name, (rows, cols) in tables.items():
        if rows is None:
            continue                    # the optional file, absent
        with open(os.path.join(directory, "%s.csv" % name), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
    return directory


def fresh_run(name, **over):
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    mdir = write_manifests(os.path.join(out, "manifests"), **over)
    summary = RB.run_batch(mdir, out, file_root=ROOT, run_date="2026-10-18")
    return out, summary


def frame(rows, cols):
    return pd.DataFrame([{c: ("" if r.get(c) is None else str(r.get(c)))
                          for c in cols} for r in rows], columns=cols)


def validate(readings=READINGS, panels=PANELS, units=UNITS, series=SERIES,
             reviewers=None):
    problems = BM.validate_batch_manifests(
        frame(panels, BM.panel_manifest_columns()),
        frame(series, BM.series_manifest_columns()),
        frame(POSITIONS, BM.position_manifest_columns()),
        frame([], BM.reader_config_columns()),
        units=frame(units, GE.fig_unit_columns()),
        source_documents=frame(SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
        source_figures=frame(SOURCE_FIGURES, BM.source_figure_manifest_columns()),
        source_panels=frame(SOURCE_PANELS, BM.source_panel_inventory_columns()),
        reviewers=frame(REVIEWERS if reviewers is None else reviewers,
                        BM.reviewer_registry_columns()),
        readings=frame(readings, BM.supplied_readings_columns()),
        file_root=ROOT, doc_root=ROOT)
    return set(problems["check"]) if len(problems) else set()


def read(out, name):
    return pd.read_csv(os.path.join(out, name), dtype=object).fillna("")


def review(out, **kw):
    row = dict(Review_ID="R001", Panel_ID="P1",
               Review_Subject_SHA256=read(out, "review_queue.csv").loc[
                   0, "Review_Subject_SHA256"],
               Reviewer_ID="RV_H", Decision="APPROVED",
               Marks_Checked="CONFIRMED", Inference_Checked="CONFIRMED",
               Reviewed_At="2026-10-18T10:00:00Z", Note="")
    row.update(kw)
    path = os.path.join(out, "value_review.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.value_review_columns())
        w.writerow([row.get(c, "") for c in FIN.value_review_columns()])
    return path


def finalize(out, **kw):
    return FIN.finalize(out, review_path=review(out, **kw), run_date="2026-10-18",
                        today=datetime.date(2026, 10, 18))


# ==========================================================================
print("a reading that cannot be a value of this panel is refused before the run")
check("the fixture's own readings validate", validate() == set(),
      "%s" % sorted(validate()))
_auto = [dict(PANELS[0], Panel_Mode="AUTO", Mark_Type="LINE_COLOR")]
_auto_series = [dict(s, Colour_Hex=hx, Marker_Shape="CIRCLE", Marker_Fill="ANY",
                     Line_Style="SOLID")
                for s, hx in zip(SERIES, ("#2d50dc", "#d72d2d"))]
check("a reader's panel takes no supplied readings",
      "SUPPLIED_READING_ON_READER_PANEL" in validate(panels=_auto,
                                                     series=_auto_series))
check("a reading of a panel nobody declared is refused",
      "SUPPLIED_READING_PANEL_UNKNOWN"
      in validate([reading("S_B", 0, Panel_ID="P9")]))
check("a series the panel does not declare is refused",
      "SUPPLIED_READING_SERIES_UNKNOWN"
      in validate([reading("S_B", 0, Series_ID="S_X")]))
check("a position the panel does not declare is refused",
      "SUPPLIED_READING_POSITION_UNKNOWN"
      in validate([reading("S_B", 0, Position_ID="T9")]))
check("one cell read twice is refused",
      "SUPPLIED_READING_CELL_TWICE"
      in validate([reading("S_B", 0), reading("S_B", 0, Reading_ID="again")]))
check("one Reading_ID used twice is refused",
      "SUPPLIED_READING_DUPLICATE"
      in validate([reading("S_B", 0), reading("S_R", 0, Reading_ID="P1__S_B__T0")]))
check("a Reading_ID that is not a safe identifier is refused",
      "SUPPLIED_READING_ID_BAD"
      in validate([reading("S_B", 0, Reading_ID="../x")]))
check("a pixel outside the plot area is refused",
      "SUPPLIED_READING_OUTSIDE_PANEL"
      in validate([reading("S_B", 0, Upper_Y_Px=20)]))
check("an upper end below the mark is refused",
      "SUPPLIED_READING_ENDS_INVERTED"
      in validate([reading("S_B", 0, Upper_Y_Px=centre("S_B", 0)[1] + 5)]))
check("a lower end above the mark is refused",
      "SUPPLIED_READING_ENDS_INVERTED"
      in validate([reading("S_B", 0, Lower_Y_Px=centre("S_B", 0)[1] - 5)]))
check("a point filed under a position it is not nearest is refused",
      "SUPPLIED_READING_NOT_AT_ITS_POSITION"
      in validate([reading("S_B", 0, Position_ID="T1")]))
check("a reading made on another raster is refused",
      "SUPPLIED_READING_RASTER_MISMATCH"
      in validate([reading("S_B", 0, Raster_SHA256="0" * 64)]))
check("a reader kind with no registered method is refused",
      "SUPPLIED_READER_KIND_UNKNOWN"
      in validate([reading("S_B", 0, Reader_Kind="HUMAN")]))
check("who placed the points is required",
      "MISSING_REQUIRED" in validate([reading("S_B", 0, Read_By="")]))
check("the date the reading was made is a date",
      "SUPPLIED_READING_DATE_BAD"
      in validate([reading("S_B", 0, Read_At="yesterday")]))
check("a pixel that is not a number is refused",
      "SUPPLIED_READING_PIXEL_BAD"
      in validate([reading("S_B", 0, Mark_Y_Px="nan")]))
check("the mark's own pixels are required",
      "MISSING_REQUIRED" in validate([reading("S_B", 0, Mark_X_Px="")]))
check("only a continuous or a box unit takes a supplied reading",
      "SUPPLIED_READING_STATISTIC_UNSUPPORTED"
      in validate(units=[dict(UNITS[0], Statistic_Type="ASSOCIATION")]))
check("  and a box unit's reading without its box edges is refused",
      "SUPPLIED_READING_BOX_EDGES_MISSING"
      in validate(units=[dict(UNITS[0], Statistic_Type="QUANTILE_SUMMARY")]))
check("an error bar end may be left blank",
      validate([reading("S_B", 0, Lower_Y_Px="")]) == set(),
      "%s" % sorted(validate([reading("S_B", 0, Lower_Y_Px="")])))

# ==========================================================================
print()
print("a manual panel nobody has read is queued exactly as before")
_none, _sn = fresh_run("no_readings", supplied_readings=None)
_rm = read(_none, "run_manifest.csv")
check("a batch with no supplied_readings.csv runs", _sn["status"] == "RAN",
      "%s" % _sn)
check("  and its manual panel is MANUAL_POINT_READ, every cell missing",
      _rm.loc[0, "Run_State"] == "MANUAL_POINT_READ"
      and int(_rm.loc[0, "Cells_Declared"]) == 8, "%s" % _rm.to_dict("records"))
_stamp = json.load(open(os.path.join(_none, "run_stamp.json"), encoding="utf-8"))
check("  and the absent file is still hashed, so adding one later is a change",
      "readings" in _stamp["Manifest_SHA256"], "%s" % sorted(_stamp["Manifest_SHA256"]))

# ==========================================================================
print()
print("a manual panel with readings is read from them, and says who read it")
OUT, SUMMARY = fresh_run("run1")
RM = read(OUT, "run_manifest.csv")
QC = read(OUT, "figure_values_machine_qc.csv")
check("the run completed", SUMMARY["status"] == "RAN", "%s" % SUMMARY)
check("  and the panel passed the gate with every cell",
      RM.loc[0, "Run_State"] == "AUTO_PASS" and int(RM.loc[0, "Cells_Read"]) == 8
      and len(QC) == 8, "%s / %d values" % (RM.to_dict("records"), len(QC)))
check("  and the run manifest says the values came from supplied readings, by whom",
      "supplied reading" in RM.loc[0, "Detail"]
      and "claude-opus-5-5" in RM.loc[0, "Detail"], RM.loc[0, "Detail"])
_by_cell = {r["Cell_Key"]: r for r in QC.to_dict("records")}


def _cell(sid, i):
    level = dict(S_B="CONTROL", S_R="TREATED")[sid]
    for key, r in _by_cell.items():
        if "ARM=%s" % level in key and "TIMEPOINT=%s" % LABELS[i] in key:
            return r
    return None


_ok_numbers = []
for sid in ("S_B", "S_R"):
    for i in range(4):
        r = _cell(sid, i)
        y = centre(sid, i)[1]
        _ok_numbers.append(
            r is not None
            and abs(float(r["Mean"]) - value_at(y)) < 1e-9
            and abs(float(r["Dispersion_Value"]) - 22 * 220.0 / 400.0) < 1e-9
            and abs(float(r["Errorbar_Upper"]) - value_at(y - 22)) < 1e-9
            and abs(float(r["Errorbar_Lower"]) - value_at(y + 22)) < 1e-9)
check("every number is the panel's calibration at the placed pixel",
      all(_ok_numbers), "%s" % _ok_numbers)
check("the methods say an agent placed the points, and filed two series",
      set(QC["Identity_Method"]) == {"AI_ASSIGNED_SERIES"}
      and set(QC["Value_Method"]) == {"AI_PLACED_POINT"}
      and set(QC["Dispersion_Method"]) == {"AI_PLACED_CAP"},
      "%s" % QC[["Identity_Method", "Value_Method", "Dispersion_Method"]]
      .drop_duplicates().to_dict("records"))
check("  which is R2: finalizable, and asking a confirmation of the panel",
      {PROV.row_tier(r) for r in QC.to_dict("records")} == {"R2"})
QUEUE = read(OUT, "review_queue.csv")
check("the panel is queued for an overlay review, counting every placed point",
      QUEUE.loc[0, "Review_Mode"] == "OVERLAY"
      and int(QUEUE.loc[0, "Inference_Cells"]) == 8,
      "%s" % QUEUE.to_dict("records"))
check("  and the overlay exists",
      os.path.exists(RB.resolve_artifact(OUT, QUEUE.loc[0, "Overlay_File"])))
_marks = json.load(open(RB.resolve_artifact(OUT, QUEUE.loc[0, "Raw_Data_File"]),
                        encoding="utf-8"))["marks"]
check("the marks carry the reading whole, inside their own hash",
      all(m.get("Reading_ID") and m.get("Read_By") == "claude-opus-5-5"
          and m.get("Read_At") == "2026-10-18" and m.get("Raster_SHA256") == SHA
          and m.get("Reader_Kind") == "AI_AGENT" for m in _marks)
      and all(RB.mark_record_sha256(
          m, json.load(open(RB.resolve_artifact(OUT, QUEUE.loc[0, "Raw_Data_File"]),
                            encoding="utf-8"))) == m["Mark_Record_SHA256"]
          for m in _marks), "%s" % _marks[:1])
check("the WPD project holds every placed point",
      bool(QUEUE.loc[0, "WPD_Project_File"])
      and sum(len(v) for v in RB.project_points(_marks).values()) == 8)
check("the overlay marks a placed point as placed, and keys it",
      all(OVERLAY.mark_label(m).endswith(OVERLAY.PLACED_MARK_SUFFIX)
          for m in _marks)
      and "PLACED by an AI agent" in OVERLAY.inferred_note(_marks)
      and "SERIES reasoned to" not in OVERLAY.inferred_note(_marks),
      OVERLAY.inferred_note(_marks))

# Both placed ends are drawn: a reviewer asked whether the end BELOW a point
# sits on the printed one has to be shown it.
_lone = dict(_marks[0], cap_px=None, cap_low_px=_marks[0]["Errorbar_Bottom_Px"])
_with = OVERLAY.draw_panel_overlay(os.path.join(ROOT, "with_low.png"), IMG,
                                   (100, 500, 40, 440), [_lone])
_without = OVERLAY.draw_panel_overlay(os.path.join(ROOT, "without_low.png"), IMG,
                                      (100, 500, 40, 440),
                                      [dict(_lone, cap_low_px=None)])
check("the overlay draws the end placed below the point",
      _with and _without
      and open(_with, "rb").read() != open(_without, "rb").read())

# ==========================================================================
print()
print("the readings decide the methods, not the mark type")
_one, _ = fresh_run(
    "one_series", series_manifest=[SERIES[0]],
    grid_definitions=([dict(Grid_ID="G", Factor_Name="ARM", Factor_Level="CONTROL",
                            Level_Order=0, Note="")]
                      + [g for g in GRIDS if g["Factor_Name"] == "TIMEPOINT"]),
    supplied_readings=[r for r in READINGS if r["Series_ID"] == "S_B"])
_q1 = read(_one, "figure_values_machine_qc.csv")
check("one declared series is a declared identity, R2 for the point alone",
      set(_q1["Identity_Method"]) == {"DECLARED_SINGLE_SERIES"} and len(_q1) == 4
      and {PROV.row_tier(r) for r in _q1.to_dict("records")} == {"R2"},
      "%s" % _q1[["Identity_Method", "Value_Method"]].to_dict("records"))
_f1 = finalize(_one)
check("  and it finalizes on the same approval: the declared pair is the route's too",
      _f1["status"] == "FINALIZED" and _f1["accepted"] == 4, "%s" % _f1)
_bar, _ = fresh_run(
    "bar_mono", panel_manifest=[dict(PANELS[0], Mark_Type="BAR_MONO",
                                     Baseline_Value="0",
                                     Identity_Domain_ID="F1")],
    unit_manifest=[dict(UNITS[0], Bar_Top_Definition="OUTLINE_CENTER")])
_qb = read(_bar, "figure_values_machine_qc.csv")
_rb = read(_bar, "run_manifest.csv")
check("a BAR_MONO panel read from readings is not held to the fill-identity rules",
      _rb.loc[0, "Run_State"] == "AUTO_PASS" and len(_qb) == 8
      and set(_qb["Value_Method"]) == {"AI_PLACED_POINT"},
      "%s" % _rb.loc[0, "Detail"])
check("  and is queued for the overlay, not the geometry review it never had",
      read(_bar, "review_queue.csv").loc[0, "Review_Mode"] == "OVERLAY")

# ==========================================================================
print()
print("what was not placed is missing, and says so")
_half, _ = fresh_run("half",
                     supplied_readings=[r for r in READINGS if r["Series_ID"] == "S_B"])
_rh = read(_half, "run_manifest.csv")
_mq = read(_half, "manual_queue_cells.csv")
check("a series nobody placed is four missing cells, not an unresolved identity",
      _rh.loc[0, "Run_State"] != "SERIES_IDENTITY_UNRESOLVED"
      and int(_rh.loc[0, "Cells_Read"]) == 4
      and len(_mq[_mq["Panel_ID"] == "P1"]) == 4,
      "%s / %d queued" % (_rh.to_dict("records"), len(_mq)))
_up, _ = fresh_run("upper_only",
                   supplied_readings=[dict(r, Lower_Y_Px="") for r in READINGS])
_qu = read(_up, "figure_values_machine_qc.csv")
_r0 = [r for r in _qu.to_dict("records") if "CONTROL" in r["Cell_Key"]
       and "T0" in r["Cell_Key"]]
check("one end placed: the spread is that end's distance from the mean",
      len(_qu) == 8 and _r0
      and abs(float(_r0[0]["Dispersion_Value"]) - 22 * 0.55) < 1e-9
      and _r0[0]["Errorbar_Lower"] == ""
      and abs(float(_r0[0]["Errorbar_Upper"]) - value_at(358)) < 1e-9,
      "%s" % _r0)
_bare, _ = fresh_run("no_ends",
                     supplied_readings=[dict(r, Upper_Y_Px="", Lower_Y_Px="")
                                        for r in READINGS])
check("no end placed at all: the panel has no weight, as for any reader",
      read(_bare, "run_manifest.csv").loc[0, "Run_State"] == "NO_VARIANCE",
      "%s" % read(_bare, "run_manifest.csv").to_dict("records"))

# ==========================================================================
print()
print("the person is still the door into the pool")
_fin = finalize(OUT, Inference_Checked="")
check("an approval that does not confirm the placed points finalizes nothing",
      _fin["status"] != "FINALIZED" or _fin.get("accepted", 0) == 0,
      "%s" % _fin)
check("  and no accepted file is written",
      not os.path.exists(os.path.join(OUT, "figure_values_accepted.csv"))
      or len(read(OUT, "figure_values_accepted.csv")) == 0)
_fin = finalize(OUT, Decision="REJECTED")
check("a rejection finalizes nothing",
      not os.path.exists(os.path.join(OUT, "figure_values_accepted.csv"))
      or len(read(OUT, "figure_values_accepted.csv")) == 0, "%s" % _fin)
_fin = finalize(OUT)
check("a registered person who checked the overlay and the placed points "
      "finalizes the panel",
      _fin["status"] == "FINALIZED"
      and len(read(OUT, "figure_values_accepted.csv")) == 8, "%s" % _fin)
_acc = read(OUT, "figure_values_accepted.csv")
check("  and the accepted values still say an agent placed them",
      set(_acc["Value_Method"]) == {"AI_PLACED_POINT"})
_stale = finalize(OUT, Review_Subject_SHA256="0" * 64)
check("an approval of a different extraction finalizes nothing",
      _stale["status"] != "FINALIZED" or _stale.get("accepted", 0) == 0,
      "%s" % _stale)

# A reading changed after the run is a manifest the run did not validate.
_ed, _ = fresh_run("edited_after")
_path = os.path.join(_ed, "manifests", "supplied_readings.csv")
_rows = list(csv.DictReader(open(_path, encoding="utf-8")))
_rows[0]["Mark_Y_Px"] = str(float(_rows[0]["Mark_Y_Px"]) - 10)
with open(_path, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=BM.supplied_readings_columns())
    w.writeheader()
    w.writerows(_rows)
_fe = finalize(_ed)
check("a reading edited after the run refuses the run",
      _fe["status"] != "FINALIZED"
      and "RUN_MANIFEST_MODIFIED" in {p["check"] for p in _fe["problems"]},
      "%s" % _fe)

# ==========================================================================
print()
print("the route's contract, both ways")
check("a reader's panel cannot claim a placed point",
      bool(PROV.contract_failure("LINE_COLOR", "AI_ASSIGNED_SERIES",
                                 "AI_PLACED_POINT"))
      and bool(PROV.contract_failure("BAR_MONO", "DECLARED_SINGLE_SERIES",
                                     "AI_PLACED_POINT")))
check("a supplied panel cannot claim a reader's measurement",
      bool(PROV.contract_failure("SUPPLIED", "MEASURED_COLOUR", "MARKER_CENTER"))
      and bool(PROV.dispersion_contract_failure("SUPPLIED",
                                                "DIRECT_CONNECTED_CAP")))
check("the route is the panel's mode, and the mark type otherwise",
      PROV.route_of("BAR_MONO", "MANUAL") == "SUPPLIED"
      and PROV.route_of("bar_mono", "") == "BAR_MONO"
      and PROV.route_of("LINE_COLOR", "AUTO") == "LINE_COLOR")
check("a placed point is not a person's manual digitizing",
      PROV.value_tier("AI_PLACED_POINT") == "R2"
      and PROV.identity_tier("AI_ASSIGNED_SERIES") == "R2"
      and PROV.dispersion_tier("AI_PLACED_CAP") == "R2"
      and PROV.value_tier("MANUAL_DIGITIZED") == "R0")

# A reader panel whose reader claimed the agent's methods: the queue says
# LINE_COLOR, the manifest says AUTO, and the contract is the reader's.
_real_read_panel = MR.read_panel


def _claims_placed(mark_type, **kw):
    rows = _real_read_panel(mark_type, **kw)
    for r in rows:
        r["Identity_Method"] = "AI_ASSIGNED_SERIES"
        r["Value_Method"] = "AI_PLACED_POINT"
        r["Dispersion_Method"] = "AI_PLACED_CAP"
    return rows


try:
    MR.read_panel = _claims_placed
    _lie, _ = fresh_run("reader_claims_placed", panel_manifest=_auto,
                        series_manifest=_auto_series, supplied_readings=None)
finally:
    MR.read_panel = _real_read_panel
_fl = finalize(_lie)
check("a reader's values claiming placed points are withheld at finalization",
      "METHOD_NOT_POSSIBLE_FOR_READER" in {p["check"] for p in _fl["problems"]}
      and _fl["accepted"] == 0,
      "%s" % sorted({p["check"] for p in _fl["problems"]}))

# ==========================================================================
print()
print("the verifier re-makes each value from its declared reading")
_ctx = FIN.panel_expectations(dict(
    RB.load_manifests(os.path.join(OUT, "manifests")),
    outputs={"run_manifest.csv": RM.to_dict("records")}))["P1"]
_m0 = dict(_marks[0])
_claimed = {f: _m0.get(f) for f in PROV.METHOD_FIELDS}
check("the run's own mark passes",
      PROV.evidence_failure("SUPPLIED", _m0, _claimed, _ctx["context"]) == ("", ""),
      "%s" % (PROV.evidence_failure("SUPPLIED", _m0, _claimed, _ctx["context"]),))
check("  and the route recorded for the panel is the supplied one",
      _ctx["route"] == "SUPPLIED")
for name, edit, code in (
        ("a mark moved off its reading's pixel",
         dict(marker_center_px=_m0["marker_center_px"] + 3,
              mean=value_at(_m0["marker_center_px"] + 3)),
         "METHOD_EVIDENCE_INCOMPLETE"),
        ("a number that is not the calibration at the pixel",
         dict(mean=_m0["mean"] + 1), "METHOD_EVIDENCE_INCOMPLETE"),
        ("a spread that is not the ends' distance",
         dict(dispersion=_m0["dispersion"] * 2), "METHOD_EVIDENCE_INCOMPLETE"),
        ("a mark citing a reading nobody declared",
         dict(Reading_ID="P1__nobody"), "METHOD_EVIDENCE_INCOMPLETE"),
        ("a mark refiled under another series",
         dict(series="S_R"), "METHOD_EVIDENCE_INCOMPLETE"),
        ("a mark that says another agent placed it",
         dict(Read_By="someone-else"), "METHOD_EVIDENCE_INCOMPLETE"),
        ("a mark of a kind its reading does not say",
         dict(Reader_Kind="HUMAN"), "METHOD_EVIDENCE_INCOMPLETE"),
):
    got = PROV.evidence_failure("SUPPLIED", dict(_m0, **edit), _claimed,
                                _ctx["context"])
    check("  %s is refused" % name, got[0] == code, "%s" % (got,))
got = PROV.evidence_failure(
    "SUPPLIED", _m0, dict(_claimed, Identity_Method="DECLARED_SINGLE_SERIES"),
    _ctx["context"])
check("  a two-series panel's point claiming a declared identity contradicts it",
      got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (got,))
got = PROV.evidence_failure(
    "SUPPLIED", dict(_m0, Errorbar_Top_Px=None, Errorbar_Bottom_Px=None,
                     dispersion=None, errorbar_lower=None, errorbar_upper=None),
    _claimed, _ctx["context"])
check("  a point whose ends were dropped while the value kept a capped spread "
      "contradicts it", got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (got,))
got = PROV.evidence_failure("SUPPLIED", _m0, _claimed,
                            dict(_ctx["context"], Y_Calibration=None))
check("  and a verifier with no calibration refuses rather than assumes one",
      got[0] == "METHOD_EVIDENCE_INCOMPLETE", "%s" % (got,))

# ==========================================================================
print()
print("the plan carries the readings to the manifest")
_plan_read = {"readings": [{"series_id": "S_B", "position_id": "T0",
                            "x_px": 140, "y_px": 380, "upper_px": 358,
                            "lower_px": 402, "reader_kind": "AI_AGENT",
                            "read_by": "claude-opus-5-5", "read_at": "2026-10-18",
                            "raster_sha256": SHA, "note": ""}]}
check("a reading is a key the plan's read block may carry",
      "readings" in CP.PLAN_KEYS["read"] and "reading" in CP.PLAN_KEYS)
check("the compiler makes one reading row per placed cell, none when nothing was",
      CP.reading_rows("P1", _plan_read)[0]["Reading_ID"] == "P1__S_B__T0"
      and CP.reading_rows("P1", _plan_read)[0]["Mark_Y_Px"] == 380
      and CP.reading_rows("P1", {}) == [],
      "%s" % CP.reading_rows("P1", _plan_read))

# AND THE WHOLE WAY: a plan whose manual panel carries readings compiles to a
# manifest set the runner reads them from. The plan is the document an agent
# writes; nothing below it is typed.
PLAN = {
    "schema": CP.PLAN_SCHEMA, "publication_id": 9,
    "reviewers": [{"reviewer_id": "RV_H", "name": "Test Reviewer",
                   "record_type": "HUMAN", "contact_type": "ORCID",
                   "contact": "0000-0002-1694-233X",
                   "registered_by": "Test Reviewer",
                   "registration_date": "2026-08-01",
                   "human_attestation": "HUMAN_CONFIRMED", "note": ""}],
    "documents": [{"document_id": "SD1", "role": "MAIN_ARTICLE",
                   "source_file": "synthetic.pdf",
                   "source_file_sha256": SOURCE_PDF_SHA, "page_range": "1-1",
                   "observed_figure_count": 1,
                   "inventory_status": "VISUALLY_VERIFIED",
                   "figure_count_method": "HUMAN_VISUAL", "reviewer_id": "RV_H",
                   "inspection_date": "2026-08-06", "note": ""}],
    "grids": [{"grid_id": "G", "factors": {"ARM": ["CONTROL", "TREATED"],
                                           "TIMEPOINT": LABELS}}],
    "reader_configs": [], "figure_views": {"F1": {"caption": "mean +/- SD"}},
    "figures": [{
        "source_figure_id": "SF1", "document_id": "SD1", "figure_number": "FIG1",
        "source_file": "synthetic.pdf", "source_page": 1, "image": "panel.png",
        "observed_panel_count": 1, "inventory_status": "VISUALLY_VERIFIED",
        "panel_count_method": "HUMAN_VISUAL", "reviewer_id": "RV_H",
        "inspection_date": "2026-08-06", "note": "",
        "panels": [{
            "panel_id": "P1", "label": "P1", "outcome_label": "Heart rate",
            "target_status": "TARGET", "disposition": "AUTO_DIGITIZE",
            "reason": "fixture",
            "read": {
                "mark_type": "LINE_COLOR", "unit_id": "U1", "figure_view": "F1",
                "box": [100, 500, 40, 440], "y_ticks": [[220, 40], [0, 440]],
                "y_scale": "LINEAR", "x_scale": "LINEAR", "panel_mode": "MANUAL",
                "series": [{"series_id": sid, "factor": "ARM", "level": lv}
                           for sid, lv in (("S_B", "CONTROL"), ("S_R", "TREATED"))],
                "positions": [{"position_id": q, "factor": "TIMEPOINT", "level": q,
                               "x_pixel": x + 9} for q, x in zip(LABELS, XS)],
                "readings": [{"series_id": r["Series_ID"],
                              "position_id": r["Position_ID"],
                              "x_px": r["Mark_X_Px"], "y_px": r["Mark_Y_Px"],
                              "upper_px": r["Upper_Y_Px"],
                              "lower_px": r["Lower_Y_Px"],
                              "reader_kind": "AI_AGENT",
                              "read_by": "claude-opus-5-5",
                              "read_at": "2026-10-18", "raster_sha256": SHA}
                             for r in READINGS]}}]}],
    "units": [{"unit_id": "U1", "panel_id": "P1", "figure_view": "F1",
               "grid_id": "G", "panel": "P1", "outcome_name": "Heart rate",
               "domain": "CV_HEMO", "unit": "bpm", "statistic": "CONTINUOUS",
               "dispersion_type": "SD", "n_outcome": 10, "n_source": "caption",
               "bar_top_definition": "NOT_A_BAR",
               "errorbar_stem_confirmed": "TRUE",
               "errorbar_source": "caption: mean +/- SD",
               "distribution_shape": "SYMMETRIC",
               "x_calibration": [[0, 149], [3, 449]]}],
}
_pdir = os.path.join(ROOT, "from_plan")
shutil.rmtree(_pdir, ignore_errors=True)
_written, _pp = CP.compile_plan(PLAN, os.path.join(_pdir, "manifests"),
                                file_root=ROOT, run_date="2026-10-18")
_compiled = (pd.read_csv(_written["supplied_readings"], dtype=object).fillna("")
             if not _pp and "supplied_readings" in _written else pd.DataFrame())
check("the compiler writes the plan's readings as supplied_readings.csv",
      not _pp and len(_compiled) == 8
      and set(_compiled["Reading_ID"]) == {r["Reading_ID"] for r in READINGS},
      "%s / %d rows" % (_pp[:3], len(_compiled)))
if not _pp:
    _ps = RB.run_batch(os.path.join(_pdir, "manifests"), _pdir, file_root=ROOT,
                       run_date="2026-10-18")
    _prm = read(_pdir, "run_manifest.csv") if _ps["status"] == "RAN" else None
    check("  and the batch compiled from it reads the manual panel from them",
          _prm is not None and _prm.loc[0, "Run_State"] == "AUTO_PASS"
          and int(_prm.loc[0, "Cells_Read"]) == 8, "%s" % _ps)
else:
    check("  and the batch compiled from it reads the manual panel from them",
          False, "the plan did not compile")

# ==========================================================================
print()
print("a point the registered person placed is that person's own reading")


def person(sid, i, **over):
    return reading(sid, i, **dict(dict(Reader_Kind="PERSON", Read_By="RV_H",
                                       Read_At="2026-10-18"), **over))


_DEMO = dict(REVIEWERS[0], Reviewer_ID="RV_DEMO", Reviewer_Name="Demo Example",
             Reviewer_Record_Type="DEMO_IDENTITY", Human_Attestation="DEMO_EXAMPLE")
check("a person's reading by a registered person validates",
      validate([person("S_B", 0)]) == set(), "%s" % sorted(validate([person("S_B", 0)])))
check("  and one by somebody the registry does not know is refused",
      "SUPPLIED_READER_NOT_REGISTERED" in validate([person("S_B", 0, Read_By="RV_X")]))
check("  and one by a registry entry that is not a person is refused",
      "SUPPLIED_READER_NOT_HUMAN"
      in validate([person("S_B", 0, Read_By="RV_DEMO")], reviewers=REVIEWERS + [_DEMO]))
check("  and one dated after today is refused",
      "SUPPLIED_READING_DATE_FUTURE"
      in validate([person("S_B", 0, Read_At=str(datetime.date.today()
                                                 + datetime.timedelta(days=1)))]))
check("  and an agent's reading is not asked to be a registered person",
      validate([reading("S_B", 0)]) == set())
check("the two kinds, and what each places",
      PROV.SUPPLIED_READER_KINDS == ("AI_AGENT", "PERSON")
      and PROV.supplied_methods("PERSON", 2, True)
      == ("PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED", "MANUAL_PLACED_CAP")
      and PROV.supplied_methods("person", 1, False)
      == ("DECLARED_SINGLE_SERIES", "MANUAL_DIGITIZED", "NO_DISPERSION")
      and PROV.supplied_methods("AI_AGENT", 2, True)
      == ("AI_ASSIGNED_SERIES", "AI_PLACED_POINT", "AI_PLACED_CAP"))
check("  and a person's point, series and end are R0",
      PROV.identity_tier("PERSON_ASSIGNED_SERIES") == "R0"
      and PROV.value_tier("MANUAL_DIGITIZED") == "R0"
      and PROV.dispersion_tier("MANUAL_PLACED_CAP") == "R0")
check("the route's contract takes a person's pair and not a crossed one",
      not PROV.contract_failure("SUPPLIED", "PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED")
      and not PROV.contract_failure("SUPPLIED", "DECLARED_SINGLE_SERIES",
                                    "MANUAL_DIGITIZED")
      and bool(PROV.contract_failure("SUPPLIED", "AI_ASSIGNED_SERIES", "MANUAL_DIGITIZED"))
      and bool(PROV.contract_failure("SUPPLIED", "PERSON_ASSIGNED_SERIES",
                                     "AI_PLACED_POINT"))
      and not PROV.dispersion_contract_failure("SUPPLIED", "MANUAL_PLACED_CAP")
      and bool(PROV.contract_failure("LINE_COLOR", "PERSON_ASSIGNED_SERIES",
                                     "MANUAL_DIGITIZED")))

# A panel the agent read but for one symbol it could not, which the person placed.
_MIX = [r for r in READINGS if r["Reading_ID"] != "P1__S_R__T2"] + [person("S_R", 2)]
_mx, _smx = fresh_run("mixed", supplied_readings=_MIX)
_qm = read(_mx, "figure_values_machine_qc.csv")
_pm = [r for r in _qm.to_dict("records") if "TREATED" in r["Cell_Key"]
       and "TIMEPOINT=T2" in r["Cell_Key"]]
check("the person's point is a value with the person's methods",
      _smx["status"] == "RAN" and len(_qm) == 8 and len(_pm) == 1
      and (_pm[0]["Identity_Method"], _pm[0]["Value_Method"],
           _pm[0]["Dispersion_Method"])
      == ("PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED", "MANUAL_PLACED_CAP")
      and PROV.row_tier(_pm[0]) == "R0"
      and abs(float(_pm[0]["Mean"]) - value_at(centre("S_R", 2)[1])) < 1e-9,
      "%s" % _pm)
_qq = read(_mx, "review_queue.csv")
check("  and the agent's seven still ask the panel's confirmation, the person's does not",
      int(_qq.loc[0, "Inference_Cells"]) == 7, "%s" % _qq.to_dict("records"))
_mm = json.load(open(RB.resolve_artifact(_mx, _qq.loc[0, "Raw_Data_File"]),
                     encoding="utf-8"))["marks"]
_mine = [m for m in _mm if m.get("Reader_Kind") == "PERSON"]
check("  and the overlay marks it P, keyed, and the agent's @",
      len(_mine) == 1
      and OVERLAY.mark_label(_mine[0]).endswith(OVERLAY.PERSON_MARK_SUFFIX)
      and not OVERLAY.mark_label(_mine[0]).endswith(OVERLAY.PLACED_MARK_SUFFIX)
      and sum(1 for m in _mm if OVERLAY.mark_label(m).endswith(
          OVERLAY.PLACED_MARK_SUFFIX)) == 7
      and "placed by a person" in OVERLAY.inferred_note(_mm),
      OVERLAY.inferred_note(_mm))
import value_page as VP                                            # noqa: E402
_card = VP.run_card(_mx, _qq.to_dict("records")[0],
                    [dict(r, Run_Panel_ID="P1") for r in _qm.to_dict("records")], [])
check("  and the value page says the person placed one, and marks its row P",
      "사람이 직접 찍은 점 1개" in _card and _card.count(" P</td>") == 1
      and _card.count(" @</td>") == 7, _card[:300])
_fmx = finalize(_mx)
check("  and the panel finalizes on the same approval, keeping whose each point is",
      _fmx["status"] == "FINALIZED" and _fmx["accepted"] == 8
      and sorted(read(_mx, "figure_values_accepted.csv")["Value_Method"])
      == ["AI_PLACED_POINT"] * 7 + ["MANUAL_DIGITIZED"], "%s" % _fmx)

_all, _ = fresh_run("all_person", supplied_readings=[
    person(r["Series_ID"], LABELS.index(r["Position_ID"])) for r in READINGS])
_qa = read(_all, "review_queue.csv")
check("a panel the person placed whole asks no inference confirmation",
      int(_qa.loc[0, "Inference_Cells"]) == 0
      and {PROV.row_tier(r) for r in read(_all, "figure_values_machine_qc.csv")
           .to_dict("records")} == {"R0"}, "%s" % _qa.to_dict("records"))
_fa = finalize(_all, Inference_Checked="")
check("  and finalizes on the overlay approval alone",
      _fa["status"] == "FINALIZED" and _fa["accepted"] == 8, "%s" % _fa)

_cx = FIN.panel_expectations(dict(
    RB.load_manifests(os.path.join(_mx, "manifests")),
    outputs={"run_manifest.csv": read(_mx, "run_manifest.csv").to_dict("records")}))["P1"]
_p0 = dict(_mine[0])
_pc = {f: _p0.get(f) for f in PROV.METHOD_FIELDS}
check("the verifier passes the person's own mark",
      PROV.evidence_failure("SUPPLIED", _p0, _pc, _cx["context"]) == ("", ""),
      "%s" % (PROV.evidence_failure("SUPPLIED", _p0, _pc, _cx["context"]),))
got = PROV.evidence_failure(
    "SUPPLIED", _p0, dict(_pc, Identity_Method="AI_ASSIGNED_SERIES",
                          Value_Method="AI_PLACED_POINT",
                          Dispersion_Method="AI_PLACED_CAP"), _cx["context"])
check("  and refuses it claiming an agent placed it",
      got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (got,))
got = PROV.evidence_failure("SUPPLIED", dict(_p0, Reader_Kind="AI_AGENT"), _pc,
                            _cx["context"])
check("  and refuses a mark whose kind is not its reading's",
      got[0] == "METHOD_EVIDENCE_INCOMPLETE", "%s" % (got,))
got = PROV.evidence_failure(
    "SUPPLIED", dict(_p0, Reader_Kind="AI_AGENT"),
    dict(_pc, Identity_Method="AI_ASSIGNED_SERIES", Value_Method="AI_PLACED_POINT",
         Dispersion_Method="AI_PLACED_CAP"), _cx["context"])
check("  and refuses a mark and value relabelled an agent's together: the reading says",
      got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (got,))
_a0 = [m for m in _mm if m.get("Reader_Kind") == "AI_AGENT"][0]
got = PROV.evidence_failure(
    "SUPPLIED", _a0, dict({f: _a0.get(f) for f in PROV.METHOD_FIELDS},
                          Identity_Method="PERSON_ASSIGNED_SERIES",
                          Value_Method="MANUAL_DIGITIZED",
                          Dispersion_Method="MANUAL_PLACED_CAP"), _cx["context"])
check("  and refuses an agent's point claiming to be the person's",
      got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (got,))

# ==========================================================================
print()
print("a box plot's five lines, placed, are a five-number summary")
BOX_IMG = os.path.join(ROOT, "boxes.png")


def box_rows_of(sid, i):
    """(whisker top, box top, median, box bottom, whisker bottom) the fixture draws."""
    base = 330 - i * 30 - (0 if sid == "S_B" else 20)
    return base - 60, base - 25, base, base + 20, base + 55


def box_x(sid, i):
    return XS[i] + 9 + (-18 if sid == "S_B" else 18)


_bi = Image.new("RGB", (600, 480), "white")
_bd = ImageDraw.Draw(_bi)
_bd.line((100, 40, 100, 440), fill=(0, 0, 0))
_bd.line((100, 440, 500, 440), fill=(0, 0, 0))
for _i in range(len(XS)):
    for _sid, _col in (("S_B", BLUE), ("S_R", RED)):
        _x = box_x(_sid, _i)
        _wt, _bt, _md, _bb, _wb = box_rows_of(_sid, _i)
        _bd.rectangle((_x - 10, _bt, _x + 10, _bb), outline=_col, width=2)
        _bd.line((_x - 10, _md, _x + 10, _md), fill=_col, width=2)
        _bd.line((_x, _wt, _x, _bt), fill=_col, width=1)
        _bd.line((_x, _bb, _x, _wb), fill=_col, width=1)
        _bd.line((_x - 6, _wt, _x + 6, _wt), fill=_col, width=2)
        _bd.line((_x - 6, _wb, _x + 6, _wb), fill=_col, width=2)
_bi.save(BOX_IMG)
BOX_SHA = MR.sha256_of(BOX_IMG)


def box_reading(sid, i, **over):
    wt, bt, md, bb, wb = box_rows_of(sid, i)
    row = dict(Reading_ID="P1__%s__%s" % (sid, LABELS[i]), Panel_ID="P1", Series_ID=sid,
               Position_ID=LABELS[i], Mark_X_Px=box_x(sid, i), Mark_Y_Px=md,
               Upper_Y_Px=wt, Lower_Y_Px=wb, Box_Upper_Y_Px=bt, Box_Lower_Y_Px=bb,
               Reader_Kind="AI_AGENT", Read_By="claude-opus-5-5", Read_At="2026-10-20",
               Raster_SHA256=BOX_SHA, Note="")
    row.update(over)
    return row


BOX_READINGS = [box_reading(sid, i) for sid in ("S_B", "S_R") for i in range(4)]
BOX_COLS = BM.supplied_readings_columns() + list(BM.SUPPLIED_OPTIONAL_COLUMNS)
BOX_UNITS = [dict(UNITS[0], Statistic_Type="QUANTILE_SUMMARY", Dispersion_Type="IQR",
                  Errorbar_Definition_Source="box plot: median, IQR, whiskers min-max")]
BOX_PANELS = [dict(PANELS[0], Mark_Type="BOX_VIOLIN", Image_Path=BOX_IMG)]
BOX_FIGS = [dict(SOURCE_FIGURES[0], Source_Image=BOX_IMG, Source_Image_SHA256=BOX_SHA)]
BOX_FIGURES = [dict(FIGURES[0], Source_Image=BOX_IMG,
                    Image_Resolution_Or_Hash="600x480 sha256:" + BOX_SHA)]


def box_validate(readings=BOX_READINGS, units=BOX_UNITS):
    problems = BM.validate_batch_manifests(
        frame(BOX_PANELS, BM.panel_manifest_columns()),
        frame(SERIES, BM.series_manifest_columns()),
        frame(POSITIONS, BM.position_manifest_columns()),
        frame([], BM.reader_config_columns()),
        units=frame(units, GE.fig_unit_columns()),
        source_documents=frame(SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
        source_figures=frame(BOX_FIGS, BM.source_figure_manifest_columns()),
        source_panels=frame(SOURCE_PANELS, BM.source_panel_inventory_columns()),
        reviewers=frame(REVIEWERS, BM.reviewer_registry_columns()),
        readings=frame(readings, BOX_COLS), file_root=ROOT, doc_root=ROOT)
    return set(problems["check"]) if len(problems) else set()


def box_run(name, readings=BOX_READINGS):
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    mdir = write_manifests(os.path.join(out, "manifests"), panel_manifest=BOX_PANELS,
                           unit_manifest=BOX_UNITS, source_figure_manifest=BOX_FIGS,
                           figure_manifest=BOX_FIGURES, supplied_readings=None)
    with open(os.path.join(mdir, "supplied_readings.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(BOX_COLS)
        for r in readings:
            w.writerow([r.get(c, "") for c in BOX_COLS])
    return out, RB.run_batch(mdir, out, file_root=ROOT, run_date="2026-10-20")


check("a box unit's readings with their box edges validate",
      box_validate() == set(), "%s" % sorted(box_validate()))
check("  and box edges on a mean's reading are refused",
      "SUPPLIED_READING_BOX_ON_MEAN" in box_validate(units=[UNITS[0]]))
_wt0, _bt0, _md0, _bb0, _wb0 = box_rows_of("S_B", 0)
check("  and a box whose edges are upside down is refused",
      "SUPPLIED_READING_BOX_INVERTED"
      in box_validate([box_reading("S_B", 0, Box_Upper_Y_Px=_bb0, Box_Lower_Y_Px=_bt0)]))
check("  and a median outside its box is refused",
      "SUPPLIED_READING_BOX_INVERTED"
      in box_validate([box_reading("S_B", 0, Mark_Y_Px=_bt0 - 5, Upper_Y_Px=_wt0)]))
check("  and a whisker end inside the box is refused",
      "SUPPLIED_READING_BOX_INVERTED"
      in box_validate([box_reading("S_B", 0, Upper_Y_Px=_bt0 + 5)]))
check("  and a box whose median is its lower quartile and its lowest value validates",
      box_validate([box_reading("S_B", 0, Mark_Y_Px=_bb0, Lower_Y_Px=_bb0)]) == set(),
      "%s" % sorted(box_validate([box_reading("S_B", 0, Mark_Y_Px=_bb0, Lower_Y_Px=_bb0)])))
check("  and so does one whose highest value is its upper quartile",
      box_validate([box_reading("S_B", 0, Upper_Y_Px=_bt0)]) == set())
check("  while a mean whose lower end is on its mark is still refused",
      "SUPPLIED_READING_ENDS_INVERTED"
      in box_validate([dict(box_reading("S_B", 0, Lower_Y_Px=_md0), Box_Upper_Y_Px="",
                            Box_Lower_Y_Px="")], units=[UNITS[0]]))
check("  and a box edge outside the plot area is refused",
      "SUPPLIED_READING_OUTSIDE_PANEL"
      in box_validate([box_reading("S_B", 0, Box_Lower_Y_Px=460, Lower_Y_Px="")]))

_bx, _sbx = box_run("boxes")
_qb = read(_bx, "figure_values_machine_qc.csv")
_rbx = read(_bx, "run_manifest.csv")
check("a box panel read from its readings passes with every cell",
      _sbx["status"] == "RAN" and _rbx.loc[0, "Run_State"] == "AUTO_PASS" and len(_qb) == 8,
      "%s / %s" % (_rbx.to_dict("records"), len(_qb)))
_ok_box = []
for _sid in ("S_B", "S_R"):
    for _i in range(4):
        _lvl = dict(S_B="CONTROL", S_R="TREATED")[_sid]
        _r = [r for r in _qb.to_dict("records") if "ARM=%s" % _lvl in r["Cell_Key"]
              and "TIMEPOINT=%s" % LABELS[_i] in r["Cell_Key"]]
        _wt, _bt, _md, _bb, _wb = box_rows_of(_sid, _i)
        _ok_box.append(len(_r) == 1 and all(
            abs(float(_r[0][k]) - value_at(px)) < 1e-9 for k, px in (
                ("Median", _md), ("Q1", _bb), ("Q3", _bt), ("Whisker_Lower", _wb),
                ("Whisker_Upper", _wt))))
check("  and every five-number summary is the calibration at its five rows",
      all(_ok_box), "%s" % _ok_box)
check("  and the methods say an agent placed them, R2, and the panel asks the confirmation",
      set(_qb["Value_Method"]) == {"AI_PLACED_POINT"}
      and set(_qb["Dispersion_Method"]) == {"AI_PLACED_CAP"}
      and {PROV.row_tier(r) for r in _qb.to_dict("records")} == {"R2"}
      and int(read(_bx, "review_queue.csv").loc[0, "Inference_Cells"]) == 8)
_bq = read(_bx, "review_queue.csv")
_bm = json.load(open(RB.resolve_artifact(_bx, _bq.loc[0, "Raw_Data_File"]), encoding="utf-8"))["marks"]
check("  and the overlay draws each box's five lines and marks it placed",
      all(len(OVERLAY.box_rows(m)) == 5 for m in _bm)
      and all(OVERLAY.mark_label(m).endswith(OVERLAY.PLACED_MARK_SUFFIX) for m in _bm))
_flat = [box_reading("S_B", 0, Mark_Y_Px=_bb0, Lower_Y_Px=_bb0)] + BOX_READINGS[1:]
_fx, _sfx = box_run("boxes_flat", _flat)
_qf = read(_fx, "figure_values_machine_qc.csv")
_f0 = [r for r in _qf.to_dict("records") if "ARM=CONTROL" in r["Cell_Key"]
       and "TIMEPOINT=%s" % LABELS[0] in r["Cell_Key"]]
check("a box whose median, lower quartile and lowest value share a row runs and passes",
      _sfx["status"] == "RAN" and read(_fx, "run_manifest.csv").loc[0, "Run_State"] == "AUTO_PASS"
      and len(_qf) == 8 and len(_f0) == 1
      and float(_f0[0]["Median"]) == float(_f0[0]["Q1"]) == float(_f0[0]["Whisker_Lower"]),
      "%s / %s" % (read(_fx, "run_manifest.csv").to_dict("records"), _f0))
check("a mean's mark carries no box key, so its record is what it was",
      not any("box_upper_px" in m or "box_lower_px" in m for m in _marks))
_fb = finalize(_bx)
check("  and the box panel finalizes on the same approval",
      _fb["status"] == "FINALIZED" and _fb["accepted"] == 8, "%s" % _fb)
_bctx = FIN.panel_expectations(dict(
    RB.load_manifests(os.path.join(_bx, "manifests")),
    outputs={"run_manifest.csv": _rbx.to_dict("records")}))["P1"]
_b0 = dict(_bm[0])
_bcl = {f: _b0.get(f) for f in PROV.METHOD_FIELDS}
check("the verifier re-makes a box's five numbers and passes the run's own mark",
      PROV.evidence_failure("SUPPLIED", _b0, _bcl, _bctx["context"]) == ("", ""),
      "%s" % (PROV.evidence_failure("SUPPLIED", _b0, _bcl, _bctx["context"]),))
for _name, _edit in (("a quartile that is not the calibration at its edge", dict(q1=_b0["q1"] + 1)),
                     ("a box edge moved off its reading", dict(box_upper_px=_b0["box_upper_px"] - 4)),
                     ("a median that is not the calibration at its line", dict(median=_b0["median"] + 1)),
                     ("a whisker that is not its end's value",
                      dict(whisker_upper=_b0["whisker_upper"] + 1))):
    _got = PROV.evidence_failure("SUPPLIED", dict(_b0, **_edit), _bcl, _bctx["context"])
    check("  and refuses %s" % _name, _got[0] == "METHOD_EVIDENCE_INCOMPLETE", "%s" % (_got,))

_pbox = {"readings": [{"series_id": "S_B", "position_id": "T0", "x_px": 140, "y_px": 330,
                       "upper_px": 270, "lower_px": 385, "box_upper_px": 305,
                       "box_lower_px": 350, "reader_kind": "AI_AGENT",
                       "read_by": "claude-opus-5-5", "read_at": "2026-10-20",
                       "raster_sha256": SHA, "note": ""}]}
check("the plan carries a box's edges to the manifest row",
      CP.reading_rows("P1", _pbox)[0]["Box_Upper_Y_Px"] == 305
      and CP.reading_rows("P1", _pbox)[0]["Box_Lower_Y_Px"] == 350
      and "box_upper_px" in CP.PLAN_KEYS["reading"])
_mdir2 = os.path.join(ROOT, "from_plan", "manifests")
check("  and a batch with no box reading writes no box columns",
      not _pp and open(os.path.join(_mdir2, "supplied_readings.csv"), encoding="utf-8")
      .readline().strip().split(",") == BM.supplied_readings_columns())

# ==========================================================================
print()
print("an end set at the edge of what hides the bar is a bound, and says so")
# Built 2026-10-21 (the person: "끝이 없는 칸도 넣어줘야해"). A cell whose error bar
# cannot be seen - inside its marker, under other marks, or on a bar two series
# share - goes in with its ends at the edge of what hides them: an UPPER BOUND on
# the spread. The number is made the same way as a cap's; what changes is what
# the value says it is (`BOUND_HIDDEN_END`, R3, asked about per cell).
BOUND_COLS = BM.supplied_readings_columns() + list(BM.SUPPLIED_OPTIONAL_COLUMNS)


def bound_validate(readings, units=UNITS):
    problems = BM.validate_batch_manifests(
        frame(PANELS, BM.panel_manifest_columns()),
        frame(SERIES, BM.series_manifest_columns()),
        frame(POSITIONS, BM.position_manifest_columns()),
        frame([], BM.reader_config_columns()),
        units=frame(units, GE.fig_unit_columns()),
        source_documents=frame(SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
        source_figures=frame(SOURCE_FIGURES, BM.source_figure_manifest_columns()),
        source_panels=frame(SOURCE_PANELS, BM.source_panel_inventory_columns()),
        reviewers=frame(REVIEWERS, BM.reviewer_registry_columns()),
        readings=frame(readings, BOUND_COLS), file_root=ROOT, doc_root=ROOT)
    return set(problems["check"]) if len(problems) else set()


check("End_Basis is an optional column beside the box edges",
      BM.SUPPLIED_END_BASIS_COLUMN == "End_Basis"
      and "End_Basis" in BM.SUPPLIED_OPTIONAL_COLUMNS
      and "End_Basis" not in BM.SUPPLIED_BOX_COLUMNS
      and "End_Basis" not in BM.supplied_readings_columns()
      and PROV.SUPPLIED_END_BASES == ("CAP", "BOUND", "NONE"))
check("a reading whose ends are a bound validates",
      bound_validate([reading("S_B", 0, End_Basis="BOUND")]) == set(),
      "%s" % sorted(bound_validate([reading("S_B", 0, End_Basis="BOUND")])))
check("  and so does one that says CAP, or says it in small letters",
      bound_validate([reading("S_B", 0, End_Basis="CAP"),
                      reading("S_R", 0, End_Basis="bound")]) == set())
check("  and an End_Basis this file does not define is refused",
      "SUPPLIED_END_BASIS_UNKNOWN"
      in bound_validate([reading("S_B", 0, End_Basis="GUESS")]))
check("  and a bound with no end placed is refused",
      "SUPPLIED_END_BOUND_WITHOUT_END"
      in bound_validate([reading("S_B", 0, End_Basis="BOUND", Upper_Y_Px="",
                                 Lower_Y_Px="")]))
check("  while a bound with one end is fine",
      bound_validate([reading("S_B", 0, End_Basis="BOUND", Lower_Y_Px="")]) == set())
check("  and a bound on a box's whiskers is refused",
      "SUPPLIED_END_BOUND_ON_BOX"
      in box_validate([box_reading("S_B", 0, End_Basis="BOUND")]))
check("the method names the number, whoever placed it",
      PROV.supplied_methods("AI_AGENT", 2, True, "BOUND")
      == ("AI_ASSIGNED_SERIES", "AI_PLACED_POINT", "BOUND_HIDDEN_END")
      and PROV.supplied_methods("PERSON", 2, True, "bound")
      == ("PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED", "BOUND_HIDDEN_END")
      and PROV.supplied_methods("AI_AGENT", 2, True, "CAP")
      == ("AI_ASSIGNED_SERIES", "AI_PLACED_POINT", "AI_PLACED_CAP")
      and PROV.supplied_methods("PERSON", 1, False, "BOUND")
      == ("DECLARED_SINGLE_SERIES", "MANUAL_DIGITIZED", "NO_DISPERSION")
      and PROV.supplied_methods("AI_AGENT", 2, True)
      == ("AI_ASSIGNED_SERIES", "AI_PLACED_POINT", "AI_PLACED_CAP"))
check("  and a bound is R3, asked per cell, and only a supplied reading can claim one",
      PROV.dispersion_tier("BOUND_HIDDEN_END") == "R3"
      and "R3" in PROV.CELL_CONFIRMATION_TIERS
      and not PROV.dispersion_contract_failure("SUPPLIED", "BOUND_HIDDEN_END")
      and bool(PROV.dispersion_contract_failure("LINE_COLOR", "BOUND_HIDDEN_END"))
      and bool(PROV.dispersion_contract_failure("BAR_COLOR", "BOUND_HIDDEN_END")))

_BOUND = [dict(r, End_Basis="BOUND") if r["Reading_ID"] == "P1__S_B__T1" else r
          for r in READINGS if r["Reading_ID"] != "P1__S_R__T2"] \
    + [person("S_R", 2, End_Basis="BOUND", Upper_Y_Px="")]


def bound_run(name, readings):
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    mdir = write_manifests(os.path.join(out, "manifests"), supplied_readings=None)
    with open(os.path.join(mdir, "supplied_readings.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(BOUND_COLS)
        for r in readings:
            w.writerow([r.get(c, "") for c in BOUND_COLS])
    return out, RB.run_batch(mdir, out, file_root=ROOT, run_date="2026-10-21")


_bo, _sbo = bound_run("bounds", _BOUND)
_qbo = read(_bo, "figure_values_machine_qc.csv")
_rbo = read(_bo, "run_manifest.csv")
_bcells = [r for r in _qbo.to_dict("records")
           if r["Dispersion_Method"] == "BOUND_HIDDEN_END"]
check("a panel with two bounded cells runs and passes with every cell",
      _sbo["status"] == "RAN" and _rbo.loc[0, "Run_State"] == "AUTO_PASS"
      and len(_qbo) == 8, "%s / %d" % (_rbo.to_dict("records"), len(_qbo)))
check("  and exactly those two say BOUND_HIDDEN_END, an agent's and a person's, R3",
      len(_bcells) == 2
      and sorted(r["Value_Method"] for r in _bcells)
      == ["AI_PLACED_POINT", "MANUAL_DIGITIZED"]
      and {PROV.row_tier(r) for r in _bcells} == {"R3"}
      and sorted(set(_qbo["Dispersion_Method"]))
      == ["AI_PLACED_CAP", "BOUND_HIDDEN_END"], "%s" % _bcells)
_b_ai = [r for r in _bcells if "CONTROL" in r["Cell_Key"]]
check("  and the bound's number is made as a cap's would be, from the placed ends",
      len(_b_ai) == 1
      and abs(float(_b_ai[0]["Dispersion_Value"]) - 22 * 220.0 / 400.0) < 1e-9
      and abs(float(_b_ai[0]["Mean"]) - value_at(centre("S_B", 1)[1])) < 1e-9,
      "%s" % _b_ai)
_bq = read(_bo, "review_queue.csv")
_bmk = json.load(open(RB.resolve_artifact(_bo, _bq.loc[0, "Raw_Data_File"]),
                      encoding="utf-8"))["marks"]
check("  and the two marks carry End_Basis, and the six caps carry no such key",
      sorted(m.get("End_Basis") for m in _bmk if "End_Basis" in m) == ["BOUND", "BOUND"]
      and sum(1 for m in _bmk if "End_Basis" not in m) == 6, "%s" % _bmk[:2])
_asked = FIN.collect_inference_manifests(_bo)
check("the run asks about the two bounds per cell, and about no cap",
      len(_asked) == 2
      and sorted(r["Cell_Key"] for r in _asked) == sorted(r["Cell_Key"] for r in _bcells),
      "%s" % _asked)
_bcells_path = os.path.join(_bo, "inference_review.csv")


def _bound_answers(rows):
    with open(_bcells_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.inference_review_columns())
        for r in rows:
            w.writerow([dict(Inference_ID=r["Inference_ID"], Panel_ID="P1",
                             Unit_ID=r.get("Unit_ID", ""), Cell_Key=r["Cell_Key"],
                             Reviewer_ID="RV_H", Inference_Confirmed="CONFIRMED",
                             Reviewed_At="2026-10-21T10:00:00Z", Note="").get(c, "")
                        for c in FIN.inference_review_columns()])
    return _bcells_path


def _bound_finalize():
    return FIN.finalize(_bo, review_path=review(_bo), run_date="2026-10-21",
                        today=datetime.date(2026, 10, 21),
                        inference_review_path=_bcells_path)


check("  and a blank end names the same question in memory (NaN) and in the file (blank)",
      RB.inference_id(dict(_bcells[0], Errorbar_Upper=float("nan")), "P1")
      == RB.inference_id(dict(_bcells[0], Errorbar_Upper=""), "P1")
      and RB.inference_id(dict(_bcells[0], Errorbar_Upper=1.5), "P1")
      != RB.inference_id(dict(_bcells[0], Errorbar_Upper=""), "P1"))
_bound_answers([])
_bnone = _bound_finalize()
check("  so the panel approval alone finalizes nothing",
      _bnone["status"] == "NOTHING_APPROVED"
      and sum(1 for p in _bnone["problems"]
              if p["check"] == "INFERENCE_CONFIRMATION_MISSING") == 2, "%s" % _bnone)
_bound_answers(_asked)
_ball = _bound_finalize()
check("  and with each bound confirmed the panel finalizes, the bounds still saying so",
      _ball["status"] == "FINALIZED" and _ball["accepted"] == 8
      and sorted(read(_bo, "figure_values_accepted.csv")["Dispersion_Method"])
      == ["AI_PLACED_CAP"] * 6 + ["BOUND_HIDDEN_END"] * 2, "%s" % _ball)
_bcx = FIN.panel_expectations(dict(
    RB.load_manifests(os.path.join(_bo, "manifests")),
    outputs={"run_manifest.csv": _rbo.to_dict("records")}))["P1"]
_bm0 = [m for m in _bmk if m.get("End_Basis") == "BOUND"
        and m.get("Reader_Kind") == "AI_AGENT"][0]
_bcl = {f: _bm0.get(f) for f in PROV.METHOD_FIELDS}
check("the verifier passes a bound's own mark",
      _bcl["Dispersion_Method"] == "BOUND_HIDDEN_END"
      and PROV.evidence_failure("SUPPLIED", _bm0, _bcl, _bcx["context"]) == ("", ""),
      "%s" % (PROV.evidence_failure("SUPPLIED", _bm0, _bcl, _bcx["context"]),))
_got = PROV.evidence_failure("SUPPLIED", _bm0, dict(_bcl, Dispersion_Method="AI_PLACED_CAP"),
                             _bcx["context"])
check("  and refuses the bound's value claiming to be a cap",
      _got[0] == "METHOD_CONTRADICTS_EVIDENCE", "%s" % (_got,))
_got = PROV.evidence_failure(
    "SUPPLIED", {k: v for k, v in _bm0.items() if k != "End_Basis"},
    dict(_bcl, Dispersion_Method="AI_PLACED_CAP"), _bcx["context"])
check("  and refuses a mark and value relabelled a cap together: the reading says",
      _got[0] in ("METHOD_EVIDENCE_INCOMPLETE", "METHOD_CONTRADICTS_EVIDENCE"), "%s" % (_got,))

_pbound = {"readings": [dict(PLAN["figures"][0]["panels"][0]["read"]["readings"][0],
                             end_basis="bound")]}
check("the plan carries what the ends are to the manifest row",
      "end_basis" in CP.PLAN_KEYS["reading"]
      and CP.reading_rows("P1", _pbound)[0]["End_Basis"] == "BOUND"
      and CP.reading_rows("P1", PLAN["figures"][0]["panels"][0]["read"])[0]["End_Basis"] == "")
_bplan = json.loads(json.dumps(PLAN))
_bplan["figures"][0]["panels"][0]["read"]["readings"][1]["end_basis"] = "BOUND"
_bpdir = os.path.join(ROOT, "from_plan_bound")
shutil.rmtree(_bpdir, ignore_errors=True)
_bwritten, _bpp = CP.compile_plan(_bplan, os.path.join(_bpdir, "manifests"),
                                  file_root=ROOT, run_date="2026-10-21")
check("  and a batch with a bound writes End_Basis and no box columns",
      not _bpp and open(_bwritten["supplied_readings"], encoding="utf-8").readline()
      .strip().split(",") == BM.supplied_readings_columns() + ["End_Basis"],
      "%s" % (_bpp[:3],))

# ==========================================================================
print()
print("a mean kept without its error bar, by decision, says so and is not a miss")
# Built 2026-10-21 (the person, of cells whose ends they had placed inside the
# marker and then dropped: "평균만이라도 넣어줘", then "평균만"). `End_Basis=NONE`
# keeps the mean and records that no end is placed on purpose: the value is
# `MEAN_ONLY_DECLARED`, R0, and the grid gate does not take it for a forgotten
# spread. A blank-ended reading WITHOUT the word is still a missing spread.
# REVERT: let NONE carry an end, or sit on a box; return NO_DISPERSION for it;
# price it above R0; or let the gate ask it for a spread.
check("a mean-only reading with no end validates",
      bound_validate([reading("S_B", 0, End_Basis="NONE", Upper_Y_Px="",
                              Lower_Y_Px="")]) == set(),
      "%s" % sorted(bound_validate([reading("S_B", 0, End_Basis="NONE", Upper_Y_Px="",
                                            Lower_Y_Px="")])))
check("  and one that places an end anyway is refused",
      "SUPPLIED_END_NONE_WITH_END"
      in bound_validate([reading("S_B", 0, End_Basis="NONE", Upper_Y_Px="")]))
check("  and a mean only on a box is refused",
      "SUPPLIED_END_NONE_ON_BOX"
      in box_validate([box_reading("S_B", 0, End_Basis="NONE")]))
check("the method says mean only, whoever placed it, and only where no end is placed",
      PROV.supplied_methods("PERSON", 2, False, "NONE")
      == ("PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED", "MEAN_ONLY_DECLARED")
      and PROV.supplied_methods("AI_AGENT", 1, False, "none")
      == ("DECLARED_SINGLE_SERIES", "AI_PLACED_POINT", "MEAN_ONLY_DECLARED")
      and PROV.supplied_methods("PERSON", 2, False, "")
      == ("PERSON_ASSIGNED_SERIES", "MANUAL_DIGITIZED", "NO_DISPERSION")
      and PROV.supplied_methods("PERSON", 2, True, "NONE")[2] == "MANUAL_PLACED_CAP")
check("  and it is R0, and only a supplied reading can claim it",
      PROV.dispersion_tier("MEAN_ONLY_DECLARED") == "R0"
      and not PROV.dispersion_contract_failure("SUPPLIED", "MEAN_ONLY_DECLARED")
      and bool(PROV.dispersion_contract_failure("LINE_COLOR", "MEAN_ONLY_DECLARED")))
_MO = [dict(r, End_Basis="NONE", Upper_Y_Px="", Lower_Y_Px="")
       if r["Reading_ID"] == "P1__S_B__T1" else r for r in READINGS]
_mo, _smo = bound_run("mean_only", _MO)
_qmo = read(_mo, "figure_values_machine_qc.csv")
_rmo = read(_mo, "run_manifest.csv")
_mcell = [r for r in _qmo.to_dict("records") if r["Dispersion_Method"] == "MEAN_ONLY_DECLARED"]
check("a panel with a mean-only cell runs and passes with every cell",
      _smo["status"] == "RAN" and _rmo.loc[0, "Run_State"] == "AUTO_PASS"
      and len(_qmo) == 8, "%s / %d" % (_rmo.to_dict("records"), len(_qmo)))
check("  and that cell is a mean with no spread, saying MEAN_ONLY_DECLARED, R2 for its point",
      len(_mcell) == 1
      and str(_mcell[0]["Dispersion_Value"]) in ("", "nan")
      and abs(float(_mcell[0]["Mean"]) - value_at(centre("S_B", 1)[1])) < 1e-9
      and PROV.row_tier(_mcell[0]) == "R2", "%s" % _mcell)
_NE = [dict(r, Upper_Y_Px="", Lower_Y_Px="") if r["Reading_ID"] == "P1__S_B__T1" else r
       for r in READINGS]
_ne, _sne = bound_run("no_ends_unsaid", _NE)
check("  while the same blank ends without the word are a missing spread",
      read(_ne, "run_manifest.csv").loc[0, "Run_State"] == "QC_FAILED"
      and "MISSING_DISPERSION" in set(read(_ne, "qc_problems.csv")["check"]),
      "%s" % read(_ne, "run_manifest.csv").to_dict("records"))
_mfin = FIN.finalize(_mo, review_path=review(_mo), run_date="2026-10-21",
                     today=datetime.date(2026, 10, 21))
check("  and the panel finalizes with the mean-only cell in it, still saying so",
      _mfin["status"] == "FINALIZED" and _mfin["accepted"] == 8
      and sorted(read(_mo, "figure_values_accepted.csv")["Dispersion_Method"])
      == ["AI_PLACED_CAP"] * 7 + ["MEAN_ONLY_DECLARED"], "%s" % _mfin)
_mmk = json.load(open(RB.resolve_artifact(_mo, read(_mo, "review_queue.csv").loc[0, "Raw_Data_File"]),
                      encoding="utf-8"))["marks"]
_mm = [m for m in _mmk if m.get("End_Basis") == "NONE"]
check("  and its mark is labelled and footed as a mean only on the overlay",
      len(_mm) == 1 and " =" in RB.OVERLAY.mark_label(_mm[0])
      and "1 mark(s): MEAN ONLY" in RB.OVERLAY.inferred_note(_mmk)
      and "MEAN ONLY" not in RB.OVERLAY.inferred_note([m for m in _mmk if m not in _mm]),
      "%r" % RB.OVERLAY.inferred_note(_mmk))

print()
print("FDT_SCENARIOS_RUN=%d" % len(RAN))
print("%d scenarios run" % len(RAN))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all passed")
shutil.rmtree(ROOT, ignore_errors=True)
