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
import subprocess
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
check("and the subject of the approval, hashed",
      len(QUEUE.loc[0, "Review_Subject_SHA256"]) == 64)

FP = QUEUE.loc[0, "Review_Subject_SHA256"]
REVIEW = os.path.join(OUT, "value_review.csv")


def review(rows, path=REVIEW):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.value_review_columns())
        for r in rows:
            w.writerow([r.get(c, "") for c in FIN.value_review_columns()])
    return path


def row(**kw):
    base = dict(Review_ID="R001", Panel_ID="P1", Review_Subject_SHA256=FP,
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
        ("an approval carrying no fingerprint", [row(Review_Subject_SHA256="")],
         "APPROVAL_STALE"),
        ("an approval carrying somebody else's fingerprint",
         [row(Review_Subject_SHA256="0" * 64)], "APPROVAL_STALE"),
        ("a review timestamp that is not a timestamp",
         [row(Reviewed_At="last tuesday")], "BAD_REVIEWED_AT"),
        ("a review dated in the future",
         [row(Reviewed_At="2099-01-01T00:00:00Z")], "BAD_REVIEWED_AT"),
        ("an approval for a panel that never passed machine QC",
         [row(Panel_ID="P_GHOST")], "REVIEW_PANEL_NOT_IN_QUEUE"),
        ("two decisions for one panel, approve first",
         [row(), row(Review_ID="R002", Decision="REJECTED")], "DUPLICATE_REVIEW"),
        ("two decisions for one panel, reject first",
         [row(Decision="REJECTED"), row(Review_ID="R002")], "DUPLICATE_REVIEW"),
        ("one Review_ID used twice",
         [row(), row(Panel_ID="P_OTHER")], "DUPLICATE_REVIEW_ID"),
        # A duplicated Review_ID voided its rows and a MISSING one did not, so
        # the identifier a decision is audited by could just be left out - and
        # every accepted value then carried Review_ID="".
        ("an approval with no Review_ID at all", [row(Review_ID="")],
         "MISSING_REQUIRED"),
        ("an approval whose Review_ID is only whitespace",
         [row(Review_ID="   ")], "MISSING_REQUIRED"),
        # It lands in a CSV column somebody joins on, so it takes the same
        # SAFE_ID rule as every other identifier here.
        ("a Review_ID that would walk out of a directory",
         [row(Review_ID="../../etc/passwd")], "UNSAFE_ID"),
        ("a Review_ID carrying a separator the files use",
         [row(Review_ID="R001;R002")], "UNSAFE_ID")):
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
      _q2.loc[0, "Review_Subject_SHA256"] != FP)

print()
print("an approval is bound to the numbers, not to the panel's name")
# The first subject hash covered the panel id, the unit id, the mark type, the
# image hash, the config hash, the reader version, the pipeline hash and the
# cell count - and claimed in its docstring to expire whenever "the image, the
# config, the reader or the pipeline" changed. It did not cover the Mean the
# person read off the overlay, the Cell_Key it sat in, what CONTROL and TREATED
# mean, the panel box, the ticks, the unit and grid manifests, the OpenCV
# version, or any of the artifacts. So an approval survived swapping two factor
# labels, editing a value, and changing the library that produced it.
_QUEUE_PATH = os.path.join(OUT, "review_queue.csv")


def subject_after(**over):
    """The subject hash the run produces once `over` is applied to the plan."""
    out, _ = fresh_run("run_subject_%d" % (abs(hash(repr(over))) % 10 ** 6), **over)
    q = pd.read_csv(os.path.join(out, "review_queue.csv"), dtype=object).fillna("")
    return out, (q.loc[0, "Review_Subject_SHA256"] if len(q) else "")


_base_out, _base_subject = subject_after()
check("the same inputs give the same subject",
      subject_after()[1] == _base_subject, "%s" % _base_subject[:16])

for _label, _over in (
        ("swapping what CONTROL and TREATED mean",
         dict(series_manifest=[dict(SERIES[0], Factor_Level="TREATED"),
                               dict(SERIES[1], Factor_Level="CONTROL")])),
        ("moving a declared x position by one pixel",
         dict(position_manifest=[dict(POSITIONS[0], X_Pixel=int(POSITIONS[0]["X_Pixel"]) + 1)]
              + POSITIONS[1:])),
        ("nudging the panel box",
         dict(panel_manifest=[dict(PANELS[0], Panel_Y0=41)])),
        ("changing a tick",
         dict(panel_manifest=[dict(PANELS[0], Axis_Y_Ticks="221:40;0:440")])),
        ("renaming a grid level",
         dict(grid_definitions=[dict(g, Factor_Level="EARLY")
                                if g["Factor_Level"] == "T0" else g
                                for g in GRIDS])),
        ("changing the unit's declared dispersion",
         dict(unit_manifest=[dict(UNITS[0], Dispersion_Type="SEM")]))):
    _out, _subject = subject_after(**_over)
    check("%s changes the subject" % _label, _subject != _base_subject,
          "%s vs %s" % (_subject[:16], _base_subject[:16]))

# The three a reviewer cannot see in a manifest diff at all.
check("the environment is part of the subject",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {"Python": "3.11"})
      != RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {"Python": "3.12"}),
      "a different OpenCV gives the same hash")
check("and so are the values themselves",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [{"Cell_Key": "A", "Mean": 1}],
                               {}, {})
      != RB.review_subject_sha256({"Panel_ID": "P1"}, [{"Cell_Key": "A", "Mean": 2}],
                                  {}, {}),
      "a different Mean gives the same hash")
check("and the Cell_Key a value sits in",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [{"Cell_Key": "A", "Mean": 1}],
                               {}, {})
      != RB.review_subject_sha256({"Panel_ID": "P1"}, [{"Cell_Key": "B", "Mean": 1}],
                                  {}, {}))
# Every artifact, by content. The subject used to take two of them off the run
# row by path - `Raw_Data_File` and `WPD_Project_File` - which left the overlay
# out entirely although the docstring listed it, and turned a multi-series
# scatter's ";"-joined point files into a path that does not exist and hashes
# to "".
_base_art = [("OVERLAY", "/x/P1_overlay.png", "a" * 64),
             ("WPD_PROJECT", "/x/P1.tar", "b" * 64),
             ("RAW_MARKS", "/x/P1_marks.json", "c" * 64)]
_with_art = RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {},
                                     artifacts=_base_art)
for _i, _label in enumerate(("the overlay a person looked at",
                             "the WPD project behind the number",
                             "the raw marks the overlay was drawn from")):
    _changed = list(_base_art)
    _changed[_i] = (_changed[_i][0], _changed[_i][1], "d" * 64)
    check("the approval subject covers %s" % _label,
          RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {},
                                   artifacts=_changed) != _with_art,
          "editing it gives the same hash")
check("and an artifact appearing at all changes the subject",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {},
                               artifacts=_base_art[:2]) != _with_art)
# Order must not matter: the ledger is a set of facts about a panel, not a
# sequence, and a reader that sorted differently would expire every approval.
check("but the order the artifacts are listed in does not",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {},
                               artifacts=list(reversed(_base_art))) == _with_art)
# Two point files, which is what a two-series scatter produces. Under the old
# ";"-join both of them were invisible to the subject.
_two = [("POINT_DATA", "/x/P2_S1_points.json", "e" * 64),
        ("POINT_DATA", "/x/P2_S2_points.json", "f" * 64)]
check("a scatter's second point file is in the subject too",
      RB.review_subject_sha256({"Panel_ID": "P2"}, [], {}, {}, artifacts=_two)
      != RB.review_subject_sha256(
          {"Panel_ID": "P2"}, [], {}, {},
          artifacts=[_two[0], (_two[1][0], _two[1][1], "0" * 64)]))
check("and joining their paths with ';' is not a file the run tries to hash",
      RB.file_sha256_or_blank(";".join(p for _, p, _h in _two)) == "")


print()
print("the run the approval refers to has to be the run on disk")
# The finalizer re-read four files to decide whether a value was poolable and
# trusted every one. Approve a correct overlay, then edit a Mean in
# figure_values_machine_qc.csv, and the edited number came out HUMAN_APPROVED.
for _label, _target, _edit in (
        # The one that matters: approve a correct overlay, then change a number.
        ("a Mean in the machine-QC values", "figure_values_machine_qc.csv",
         lambda text: text.replace(text.split("\n")[1].split(",")[
             text.split("\n")[0].split(",").index("Mean")],
             "999.0", 1)),
        ("the review queue", "review_queue.csv", lambda text: text + "\n"),
        ("the raw values", "figure_values_raw.csv", lambda text: text + "\n"),
        ("the run manifest", "run_manifest.csv", lambda text: text + "\n")):
    _tamper_out, _ = fresh_run("run_tamper_%d" % (abs(hash(_label)) % 10 ** 6))
    _q = pd.read_csv(os.path.join(_tamper_out, "review_queue.csv"), dtype=object)
    _rv = os.path.join(_tamper_out, "value_review.csv")
    review([dict(Review_ID="R001", Panel_ID="P1",
                 Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                 Reviewer_ID="RV_H", Decision="APPROVED",
                 Reviewed_At="2026-08-06T10:00:00Z", Note="")], _rv)
    _clean = FIN.finalize(_tamper_out, review_path=_rv, run_date="2026-08-06",
                          today=datetime.date(2026, 8, 6))
    _path = os.path.join(_tamper_out, _target)
    with open(_path, encoding="utf-8") as fh:
        _text = fh.read()
    with open(_path, "w", encoding="utf-8") as fh:
        fh.write(_edit(_text))
    _after = FIN.finalize(_tamper_out, review_path=_rv, run_date="2026-08-06",
                          today=datetime.date(2026, 8, 6))
    check("editing %s after the run is refused" % _label,
          _after["status"] == "RUN_ARTIFACT_MODIFIED" and _after["accepted"] == 0,
          "%s" % _after["status"])
    check("  and no accepted file survives it",
          not os.path.exists(os.path.join(_tamper_out, "figure_values_accepted.csv")),
          "%s" % sorted(os.listdir(_tamper_out)))

print()
print("a run directory can be moved, and finalized from anywhere")
# The ledger recorded absolute paths and the finalizer checked them with
# os.path.exists, so a run produced with a relative output directory and
# finalized from a different working directory reported RUN_ARTIFACT_MODIFIED
# for files sitting right there. Safe, but a false refusal nobody can act on -
# and a scheduler or an agent changes working directory as a matter of course.
_mv_src, _ = fresh_run("run_move")
_q = pd.read_csv(os.path.join(_mv_src, "review_queue.csv"), dtype=object)
review([dict(Review_ID="R001", Panel_ID="P1",
             Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
             Reviewer_ID="RV_H", Decision="APPROVED",
             Reviewed_At="2026-08-06T10:00:00Z", Note="")],
       os.path.join(_mv_src, "value_review.csv"))
_mv_dst = os.path.join(ROOT, "moved_elsewhere")
shutil.move(_mv_src, _mv_dst)
_moved = subprocess.run(
    [sys.executable, os.path.join(HERE, "finalize_batch.py"), _mv_dst,
     "--review", os.path.join(_mv_dst, "value_review.csv"),
     "--manifests", os.path.join(_mv_dst, "manifests"), "--date", "2026-08-06"],
    capture_output=True, text=True, cwd=tempfile.gettempdir())
check("a moved run finalizes from an unrelated working directory",
      _moved.returncode == 0
      and os.path.exists(os.path.join(_mv_dst, "figure_values_accepted.csv")),
      "%s%s" % (_moved.stdout[-400:], _moved.stderr[-200:]))


print()
print("the picture the person approved is also the picture on disk")
# The four CSVs were verified and nothing else. So the numbers could not be
# edited, but the overlay could: replace `review/P1_overlay.png` with a red
# rectangle - or with a different panel's overlay - and the approval bound to
# it still finalized 8 values. An approval says "I looked at this and it is
# right"; nothing established what "this" was.
for _label, _relative, _mutate in (
        ("the overlay a person judged", os.path.join("review", "P1_overlay.png"),
         lambda p: Image.new("RGB", (600, 480), "red").save(p)),
        ("the WPD project behind the number", os.path.join("projects", "P1.tar"),
         lambda p: open(p, "ab").write(b"\0" * 1024)),
        ("the raw marks the overlay was drawn from",
         os.path.join("raw", "P1_marks.json"),
         lambda p: open(p, "a", encoding="utf-8").write(" ")),):
    _a_out, _ = fresh_run("run_artifact_%d" % (abs(hash(_label)) % 10 ** 6))
    _q = pd.read_csv(os.path.join(_a_out, "review_queue.csv"), dtype=object)
    _rv = review([dict(Review_ID="R001", Panel_ID="P1",
                       Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                       Reviewer_ID="RV_H", Decision="APPROVED",
                       Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                 os.path.join(_a_out, "value_review.csv"))
    _before = FIN.finalize(_a_out, review_path=_rv, run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
    check("  %s finalizes untouched" % _label,
          _before["status"] == "FINALIZED" and _before["accepted"] > 0,
          "%s" % _before["status"])
    _target_path = os.path.join(_a_out, _relative)
    check("  and the run wrote it where the ledger says",
          os.path.exists(_target_path), _target_path)
    _mutate(_target_path)
    _after = FIN.finalize(_a_out, review_path=_rv, run_date="2026-08-06",
                          today=datetime.date(2026, 8, 6))
    check("editing %s after the approval is refused" % _label,
          _after["status"] == "RUN_ARTIFACT_MODIFIED" and _after["accepted"] == 0,
          "%s" % _after["status"])
    check("  and no accepted file survives it (%s)" % _label,
          not os.path.exists(os.path.join(_a_out, "figure_values_accepted.csv")))
    # Deleting is not a way round it either.
    os.remove(_target_path)
    _gone = FIN.finalize(_a_out, review_path=_rv, run_date="2026-08-06",
                         today=datetime.date(2026, 8, 6))
    check("  and deleting it is refused too (%s)" % _label,
          _gone["status"] == "RUN_ARTIFACT_MODIFIED", "%s" % _gone["status"])

# The ledger is what makes the per-artifact hashes trustworthy, so it is itself
# one of the verified outputs - otherwise it could simply be rewritten to agree
# with a tampered file.
_led_out, _ = fresh_run("run_ledger")
_q = pd.read_csv(os.path.join(_led_out, "review_queue.csv"), dtype=object)
_rv = review([dict(Review_ID="R001", Panel_ID="P1",
                   Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                   Reviewer_ID="RV_H", Decision="APPROVED",
                   Reviewed_At="2026-08-06T10:00:00Z", Note="")],
             os.path.join(_led_out, "value_review.csv"))
_ledger = pd.read_csv(os.path.join(_led_out, "panel_artifacts.csv"), dtype=object)
check("the run writes an artifact ledger",
      set(_ledger["Artifact_Type"]) == {"OVERLAY", "WPD_PROJECT", "RAW_MARKS"},
      "%s" % sorted(set(_ledger["Artifact_Type"])))
check("with a real hash for every artifact it names",
      all(len(h) == 64 for h in _ledger["SHA256"])
      and all(os.path.exists(RB.resolve_artifact(_led_out, p))
              for p in _ledger["Artifact_Path"]),
      "%s" % _ledger.to_dict("records"))
# Relative to the run directory, so the check survives `mv OUT elsewhere` and a
# finalizer launched from a different working directory.
check("and the paths are relative to the run, not to whoever ran it",
      not any(os.path.isabs(p) for p in _ledger["Artifact_Path"])
      and all(p.startswith(("review/", "projects/", "raw/"))
              for p in _ledger["Artifact_Path"]),
      "%s" % list(_ledger["Artifact_Path"]))
check("a ledger entry pointing outside the run is refused, not read",
      RB.resolve_artifact(_led_out, "../../etc/passwd") is None
      and RB.resolve_artifact(_led_out, "review/P1_overlay.png") is not None)
Image.new("RGB", (600, 480), "red").save(os.path.join(_led_out, "review",
                                                      "P1_overlay.png"))
_ledger.loc[_ledger["Artifact_Type"] == "OVERLAY", "SHA256"] = MR.sha256_of(
    os.path.join(_led_out, "review", "P1_overlay.png"))
_ledger.to_csv(os.path.join(_led_out, "panel_artifacts.csv"), index=False)
_forged = FIN.finalize(_led_out, review_path=_rv, run_date="2026-08-06",
                       today=datetime.date(2026, 8, 6))
check("rewriting the ledger to match a swapped overlay is refused",
      _forged["status"] == "RUN_ARTIFACT_MODIFIED" and _forged["accepted"] == 0,
      "%s" % _forged["status"])

print()
_swap_out, _ = fresh_run("run_registry_swap")
_q = pd.read_csv(os.path.join(_swap_out, "review_queue.csv"), dtype=object)
_rv = review([dict(Review_ID="R001", Panel_ID="P1",
                   Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                   Reviewer_ID="RV_EXTRA", Decision="APPROVED",
                   Reviewed_At="2026-08-06T10:00:00Z", Note="")],
              os.path.join(_swap_out, "value_review.csv"))
_other = write_manifests(os.path.join(ROOT, "m_extra_reviewer"),
                         reviewer_registry=REVIEWERS + [dict(
                             REVIEWERS[0], Reviewer_ID="RV_EXTRA",
                             Reviewer_Name="Added Later")])
_swapped = FIN.finalize(_swap_out, review_path=_rv, manifest_dir=_other,
                        run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("an approver added to a different registry is refused",
      _swapped["status"] == "RUN_ARTIFACT_MODIFIED"
      and any(p["check"] == "REVIEWER_REGISTRY_CHANGED" for p in _swapped["problems"]),
      "%s" % _swapped)


print()
print("a finalization that dies partway leaves nothing poolable")
# The accepted file was written directly and the stamp written after it, so a
# process killed between the two left poolable values with a stale stamp or no
# stamp at all. The same shape run_batch already fixed with staging and a
# commit marker.
for _fault in (0, 1):
    _f_out, _ = fresh_run("run_fault_%d" % _fault)
    _q = pd.read_csv(os.path.join(_f_out, "review_queue.csv"), dtype=object)
    _rv = review([dict(Review_ID="R001", Panel_ID="P1",
                       Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                       Reviewer_ID="RV_H", Decision="APPROVED",
                       Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                 os.path.join(_f_out, "value_review.csv"))
    _r = FIN.finalize(_f_out, review_path=_rv, run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6), fault_after=_fault)
    check("a fault after %d promoted file(s) does not commit" % _fault,
          _r["status"] == "COMMIT_FAILED", "%s" % _r["status"])
    check("  and leaves no accepted file (fault after %d)" % _fault,
          not os.path.exists(os.path.join(_f_out, FIN.FINALIZE_MARKER)),
          "%s" % sorted(os.listdir(_f_out)))
    check("  and no staging directory (fault after %d)" % _fault,
          not os.path.isdir(os.path.join(_f_out, FIN.FINALIZE_STAGING)),
          "%s" % sorted(os.listdir(_f_out)))
    check("  and a stamp that says so (fault after %d)" % _fault,
          json.load(open(os.path.join(_f_out, "finalize_stamp.json")))["Status"]
          == "COMMIT_FAILED")

_clean_out, _ = fresh_run("run_commit_ok")
_q = pd.read_csv(os.path.join(_clean_out, "review_queue.csv"), dtype=object)
_rv = review([dict(Review_ID="R001", Panel_ID="P1",
                   Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                   Reviewer_ID="RV_H", Decision="APPROVED",
                   Reviewed_At="2026-08-06T10:00:00Z", Note="")],
             os.path.join(_clean_out, "value_review.csv"))
_ok2 = FIN.finalize(_clean_out, review_path=_rv, run_date="2026-08-06",
                    today=datetime.date(2026, 8, 6))
_fs = json.load(open(os.path.join(_clean_out, "finalize_stamp.json")))
check("a clean finalization commits and records what it committed",
      _ok2["status"] == "FINALIZED" and len(_fs["Accepted_SHA256"]) == 64
      and len(_fs["Run_Stamp_SHA256"]) == 64, "%s" % _fs)
with open(os.path.join(_clean_out, FIN.FINALIZE_MARKER), encoding="utf-8") as _fh:
    check("and the recorded hash is the file that landed",
          RB.sha256_of_text(_fh.read()) == _fs["Accepted_SHA256"])
# The stamp named the review file by path and said nothing about its contents,
# so "which decisions produced this accepted file" was answerable only by
# trusting that the file had not been edited since.
check("and the decisions themselves are hashed, not merely named",
      _fs.get("Review_File_SHA256") == RB.file_sha256(_rv)
      and len(_fs.get("Review_File_SHA256", "")) == 64,
      "%s" % _fs.get("Review_File_SHA256"))
with open(_rv, "a", encoding="utf-8") as _fh:
    _fh.write("\n")
check("editing the review file changes what the stamp records",
      RB.file_sha256(_rv) != _fs.get("Review_File_SHA256"))


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
