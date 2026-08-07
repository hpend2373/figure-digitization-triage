"""Regression scenarios for the human-approval gate.

The claim under test is narrow and load-bearing: `figure_values_accepted.csv`
exists only where a registered person looked at a specific extraction and said
so. Every scenario here is a way of getting a value into that file without that
having happened.

The fixture is deliberately one that produces values. A gate tested only on a
batch that accepts nothing tests nothing.
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
import finalize_batch as FIN                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import mark_readers as MR                                          # noqa: E402
import run_batch as RB                                             # noqa: E402

ROOT = tempfile.mkdtemp(prefix="fdt_finalize_")
FAILURES = []
RAN = []


def check(name, ok, detail=""):
    RAN.append(name)
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "  <- %s" % detail))
    if not ok:
        FAILURES.append(name)


# --------------------------------------------------------------------------
# a batch that really does produce values
# --------------------------------------------------------------------------
IMG = os.path.join(ROOT, "panel.png")
BLUE, RED = (45, 80, 220), (215, 45, 45)
XS = [140, 240, 340, 440]
LABELS = ["T0", "T1", "T2", "T3"]


def draw():
    im = Image.new("RGB", (600, 480), "white")
    d = ImageDraw.Draw(im)
    d.line((100, 40, 100, 440), fill=(0, 0, 0))
    d.line((100, 440, 500, 440), fill=(0, 0, 0))
    for i, x in enumerate(XS):
        for colour, off in ((BLUE, 0), (RED, 18)):
            y = 380 - i * 40 - (0 if colour == BLUE else 25)
            d.ellipse((x + off - 6, y - 6, x + off + 6, y + 6), fill=colour)
            d.line((x + off, y - 22, x + off, y + 22), fill=colour, width=2)
            d.line((x + off - 6, y - 22, x + off + 6, y - 22), fill=colour, width=2)
            d.line((x + off - 6, y + 22, x + off + 6, y + 22), fill=colour, width=2)
    im.save(IMG)


draw()
SHA = MR.sha256_of(IMG)
TICKS = "220:40;0:440"

REVIEWERS = [dict(Reviewer_ID="RV_H", Reviewer_Name="Test Reviewer",
                  Reviewer_Record_Type="HUMAN", Contact_Type="EMAIL",
                  Reviewer_Contact="reviewer@example.org",
                  Registered_By="Test Reviewer", Registration_Date="2026-08-01",
                  Human_Attestation="HUMAN_CONFIRMED", Note=""),
             dict(Reviewer_ID="RV_D", Reviewer_Name="Josiah Carberry",
                  Reviewer_Record_Type="DEMO_IDENTITY", Contact_Type="ORCID",
                  Reviewer_Contact="0000-0002-1825-0097",
                  Registered_By="Test Reviewer", Registration_Date="2026-08-01",
                  Human_Attestation="DEMO_EXAMPLE", Note="")]

SOURCE_DOCUMENTS = [dict(
    Source_Document_ID="SD1", Publication_ID=9, Document_Role="MAIN_ARTICLE",
    Source_File="synthetic.pdf", Article_Page_Range="1-1", Observed_Figure_Count=1,
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
    Unit_ID="U1", Figure_ID="F1", Grid_ID="G", Panel="P1", Outcome_Name="Heart rate",
    Outcome_Variable="Heart rate", Outcome_Domain="CV_HEMO", Unit="bpm",
    Units="bpm", Statistic_Type="CONTINUOUS", Grid_Rule="FULL",
    Value_Scale="RATIO",
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
    Baseline_Value="", Association_Type="", Config_ID="", Panel_Mode="AUTO",
    Note="")]
SERIES = [dict(Panel_ID="P1", Series_ID=sid, Colour_Hex=hx, Colour_Tolerance="",
               Mask_Key="", Marker_Shape="CIRCLE", Marker_Fill="ANY",
               Line_Style="SOLID", Bar_Fill_Pattern="", Factor_Name="ARM",
               Factor_Level=lv, Note="")
          for sid, lv, hx in (("S_B", "CONTROL", "#2d50dc"),
                              ("S_R", "TREATED", "#d72d2d"))]
POSITIONS = [dict(Panel_ID="P1", Position_ID=q, X_Pixel=x + 9, Slot_Index=i,
                  Display_Order=i, Factor_Name="TIMEPOINT", Factor_Level=q,
                  Timepoint_Label=q, Timepoint_Days=i * 7, Note="")
             for i, (q, x) in enumerate(zip(LABELS, XS))]


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
    }
    for name, rows in over.items():
        tables[name] = (rows, tables[name][1])
    for name, (rows, cols) in tables.items():
        with open(os.path.join(directory, "%s.csv" % name), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
    return directory


def fresh_run(name, **over):
    """A completed ATTESTED run, with its manifests beside it as finalize expects."""
    out = os.path.join(ROOT, name)
    shutil.rmtree(out, ignore_errors=True)
    mdir = write_manifests(os.path.join(out, "manifests"), **over)
    summary = RB.run_batch(mdir, out, file_root=ROOT, run_date="2026-08-06")
    return out, summary


OUT, SUMMARY = fresh_run("run1")
print("the batch reaches machine QC and stops there")
check("the run completed", SUMMARY["status"] == "RAN", "%s" % SUMMARY)
check("and produced values", SUMMARY["machine_qc"] > 0, "%s" % SUMMARY)
check("and reports zero accepted, because nobody has looked yet",
      SUMMARY["accepted"] == 0, "%s" % SUMMARY)
check("and wrote no accepted file",
      not os.path.exists(os.path.join(OUT, "figure_values_accepted.csv")),
      "%s" % sorted(os.listdir(OUT)))

QUEUE = pd.read_csv(os.path.join(OUT, "review_queue.csv"), dtype=object).fillna("")
check("every passing panel is in the review queue",
      set(QUEUE["Panel_ID"]) == {"P1"}, "%s" % sorted(set(QUEUE["Panel_ID"])))
check("with a picture a person can judge",
      bool(QUEUE.loc[0, "Overlay_File"])
      and os.path.exists(QUEUE.loc[0, "Overlay_File"]),
      "%r" % QUEUE.loc[0, "Overlay_File"])
check("and the WPD project for re-deriving the number",
      bool(QUEUE.loc[0, "WPD_Project_File"]))
check("and a fingerprint of the extraction being approved",
      len(QUEUE.loc[0, "Panel_Fingerprint"]) == 64)

FP = QUEUE.loc[0, "Panel_Fingerprint"]
REVIEW = os.path.join(OUT, "value_review.csv")


def review(rows, path=REVIEW):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.value_review_columns())
        for r in rows:
            w.writerow([r.get(c, "") for c in FIN.value_review_columns()])
    return path


def row(**kw):
    base = dict(Review_ID="R001", Panel_ID="P1", Panel_Fingerprint=FP,
                Reviewer_ID="RV_H", Decision="APPROVED",
                Reviewed_At="2026-08-06T10:00:00Z", Note="")
    base.update(kw)
    return base


print()
print("an approval is a person, looking at this extraction, saying so")
_ok = FIN.finalize(OUT, review_path=review([row()]), run_date="2026-08-06",
                   today=datetime.date(2026, 8, 6))
check("a clean approval finalizes", _ok["status"] == "FINALIZED", "%s" % _ok)
_acc = pd.read_csv(os.path.join(OUT, "figure_values_accepted.csv"), dtype=object)
check("and the accepted file carries the values", len(_acc) == _ok["accepted"] > 0,
      "%d" % len(_acc))
check("and every row says who approved it and when",
      set(_acc["Reviewer_ID"]) == {"RV_H"} and set(_acc["Review_ID"]) == {"R001"}
      and set(_acc["Value_Status"]) == {"HUMAN_APPROVED"}
      and set(_acc["Pooling_Eligible"]) == {"TRUE"},
      "%s" % _acc.head(1).to_dict("records"))

for _label, _rows, _want in (
        ("no review file at all", None, "REVIEW_FILE_MISSING"),
        ("an empty review file", [], None),
        ("a decision left blank", [row(Decision="")], None),
        ("a rejection", [row(Decision="REJECTED")], None),
        ("an invented decision", [row(Decision="LOOKS_FINE")], "BAD_REVIEW_DECISION"),
        ("a reviewer nobody registered", [row(Reviewer_ID="RV_NOBODY")],
         "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED"),
        ("a DEMO_IDENTITY approver", [row(Reviewer_ID="RV_D")],
         "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED"),
        ("a blank reviewer", [row(Reviewer_ID="")],
         "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED"),
        ("an approval carrying no fingerprint", [row(Panel_Fingerprint="")],
         "APPROVAL_STALE"),
        ("an approval carrying somebody else's fingerprint",
         [row(Panel_Fingerprint="0" * 64)], "APPROVAL_STALE"),
        ("a review timestamp that is not a timestamp",
         [row(Reviewed_At="last tuesday")], "BAD_REVIEWED_AT"),
        ("a review dated in the future",
         [row(Reviewed_At="2099-01-01T00:00:00Z")], "BAD_REVIEWED_AT"),
        ("an approval for a panel that never passed machine QC",
         [row(Panel_ID="P_GHOST")], "REVIEW_PANEL_NOT_IN_QUEUE"),
        ("two decisions for one panel",
         [row(), row(Review_ID="R002", Decision="REJECTED")], "DUPLICATE_REVIEW")):
    _path = os.path.join(OUT, "review_case.csv")
    if _rows is None:
        if os.path.exists(_path):
            os.remove(_path)
    else:
        review(_rows, _path)
    _r = FIN.finalize(OUT, review_path=_path, run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6))
    _codes = {p["check"] for p in _r["problems"]}
    _accepted_exists = os.path.exists(os.path.join(OUT, "figure_values_accepted.csv"))
    if _label == "two decisions for one panel":
        # The first decision stands and the duplicate is reported; what must not
        # happen is a second, contradictory decision silently overwriting it.
        check("%s is reported" % _label, "DUPLICATE_REVIEW" in _codes, "%s" % _codes)
        continue
    check("%s accepts nothing" % _label,
          _r["accepted"] == 0 and not _accepted_exists,
          "%s | file=%s" % (_r, _accepted_exists))
    if _want:
        check("  and says %s" % _want, _want in _codes, "%s" % _codes)

print()
print("an approval does not survive the thing it approved changing")
# Re-run with one manifest field changed and the same decision file. The
# fingerprint covers the image, the config, the reader and the pipeline, so an
# approval given for the old extraction is not an approval of the new one.
_moved = os.path.join(ROOT, "moved.png")
Image.open(IMG).rotate(0).convert("RGB").save(_moved)
ImageDraw.Draw(Image.open(_moved)).point((1, 1))
_im = Image.open(_moved)
_im.putpixel((0, 0), (254, 254, 254))
_im.save(_moved)
OUT2, SUM2 = fresh_run(
    "run2",
    source_figure_manifest=[dict(SOURCE_FIGURES[0], Source_Image=_moved,
                                 Source_Image_SHA256=MR.sha256_of(_moved))],
    figure_manifest=[dict(FIGURES[0], Source_Image=_moved,
                          Image_Resolution_Or_Hash="600x480 sha256:"
                                                   + MR.sha256_of(_moved))],
    panel_manifest=[dict(PANELS[0], Image_Path=_moved)])
check("the re-run still produces values", SUM2["machine_qc"] > 0, "%s" % SUM2)
_stale = FIN.finalize(OUT2, review_path=review([row()],
                                               os.path.join(OUT2, "old_review.csv")),
                      run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("an approval from the previous run is stale, not inherited",
      "APPROVAL_STALE" in {p["check"] for p in _stale["problems"]}
      and _stale["accepted"] == 0, "%s" % _stale)
_q2 = pd.read_csv(os.path.join(OUT2, "review_queue.csv"), dtype=object).fillna("")
check("and the new run asks for a new decision",
      _q2.loc[0, "Panel_Fingerprint"] != FP)

print()
print("a finalization does not outlive the run that justified it")
_again = FIN.finalize(OUT, review_path=review([row()]), run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6))
check("re-finalizing after approval works", _again["status"] == "FINALIZED")
RB.run_batch(os.path.join(OUT, "manifests"), OUT, file_root=ROOT,
             run_date="2026-08-06")
check("but a fresh run clears the accepted file it produced",
      not os.path.exists(os.path.join(OUT, "figure_values_accepted.csv")),
      "%s" % sorted(os.listdir(OUT)))
check("and clears the finalize stamp with it",
      not os.path.exists(os.path.join(OUT, "finalize_stamp.json")),
      "%s" % sorted(os.listdir(OUT)))

print()
print("a demonstration cannot be approved into existence")
OUT3, SUM3 = fresh_run("run3", reviewer_registry=[
    dict(REVIEWERS[0], Reviewer_Record_Type="DEMO_IDENTITY",
         Human_Attestation="DEMO_EXAMPLE")])
check("a demo registry refuses its own output",
      SUM3["status"] == "DEMO_OUTPUT_REFUSED", "%s" % SUM3)
_demo_fin = FIN.finalize(OUT3, review_path=review(
    [row()], os.path.join(OUT3, "value_review.csv")), run_date="2026-08-06",
    today=datetime.date(2026, 8, 6))
check("and no approval finalizes it",
      _demo_fin["status"] == "RUN_NOT_FINALIZABLE" and _demo_fin["accepted"] == 0,
      "%s" % _demo_fin)
check("and the reason names the run mode, not the reviewer",
      "DEMO" in _demo_fin["detail"], "%s" % _demo_fin["detail"])

_stampless = os.path.join(ROOT, "no_run")
os.makedirs(_stampless, exist_ok=True)
check("a directory that is not a run cannot be finalized",
      FIN.finalize(_stampless, run_date="2026-08-06")["status"]
      == "RUN_NOT_FINALIZABLE")

print()
print("%d scenarios run" % len(RAN))
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
