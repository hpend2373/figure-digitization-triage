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
import provenance as PROV                                          # noqa: E402
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
# Recorded relative to the run, so the queue still points at the right picture
# after the directory is moved or copied to another machine.
check("with a picture a person can judge",
      bool(QUEUE.loc[0, "Overlay_File"])
      and not os.path.isabs(QUEUE.loc[0, "Overlay_File"])
      and os.path.exists(RB.resolve_artifact(OUT, QUEUE.loc[0, "Overlay_File"])),
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
                Marks_Checked="CONFIRMED",
                Reviewed_At="2026-08-06T10:00:00Z", Note="")
    base.update(kw)
    return base


print()
print("an approval cannot buy a number a model made")
# R4 IS THE TIER FOR A VALUE THAT WAS NOT READ OFF THE INK - the fitted curve
# produced it, or the nearest observation was carried sideways with nothing
# bracketing it. A reviewer looking at an overlay cannot tell a fitted y from a
# read one; that is exactly what the picture cannot show, so an APPROVED decision
# over such a value is a signature on something nobody could have checked.
#
# THE METHODS HAVE TO ARRIVE LEGITIMATELY. Written onto
# `figure_values_machine_qc.csv` after the run, they are caught by
# RUN_ARTIFACT_MODIFIED - the ledger hashes that file, and the first version of
# this scenario tripped it. So the READER answers them, the way a reader that has
# been taught to will: this fixture's panel is LINE_COLOR, which does not, so it
# is wrapped for the length of one run.
def _with_methods(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for i, r in enumerate(rows):
        r["Identity_Method"] = "MEASURED_LINE_STYLE"
        r["Value_Method"] = "FIT_FALLBACK" if i == 0 else "DIRECT_CURVE_INK"
    return rows


_real_read_panel = MR.read_panel
try:
    MR.read_panel = _with_methods
    _R4_DIR, _ = fresh_run("run_tier")
finally:
    MR.read_panel = _real_read_panel
_qc = pd.read_csv(os.path.join(_R4_DIR, "figure_values_machine_qc.csv"),
                  dtype=object).fillna("")
check("the run itself carried the methods into its values",
      set(_qc["Value_Method"]) == {"FIT_FALLBACK", "DIRECT_CURVE_INK"},
      "%r" % sorted(set(_qc["Value_Method"])))
_fp4 = pd.read_csv(os.path.join(_R4_DIR, "review_queue.csv"),
                   dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_r4 = FIN.finalize(_R4_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fp4)],
    path=os.path.join(_R4_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("the panel still finalizes - this refuses values, not approvals",
      _r4["status"] == "FINALIZED", "%s" % _r4)
_acc4 = pd.read_csv(os.path.join(_R4_DIR, "figure_values_accepted.csv"),
                    dtype=object).fillna("")
check("and the value the fit produced is not in the accepted file",
      "FIT_FALLBACK" not in set(_acc4["Value_Method"]),
      "%r" % sorted(set(_acc4["Value_Method"])))
check("while the ones read off the ink are",
      len(_acc4) == len(_qc) - 1 and set(_acc4["Value_Method"]) == {"DIRECT_CURVE_INK"},
      "%d of %d, %r" % (len(_acc4), len(_qc), sorted(set(_acc4["Value_Method"]))))
_stamp4 = json.load(open(os.path.join(_R4_DIR, "finalize_stamp.json"),
                         encoding="utf-8"))
# AND THE REFUSAL IS SOMEBODY'S WORK, at run time rather than after an approval.
# v7.67. The value is dropped and counted, and until now that was the end of it:
# a reviewer met "one of eight refused" after signing for the panel, with no list
# of which one or what to do about it.
_blocked_list = pd.read_csv(os.path.join(_R4_DIR, "method_blocked_cells.csv"),
                            dtype=object).fillna("")
check("the run writes the refused cell down as work, before anybody reviews it",
      len(_blocked_list) == 1
      and _blocked_list.iloc[0]["Value_Method"] == "FIT_FALLBACK"
      and _blocked_list.iloc[0]["Cell_State"] == "MODEL_ESTIMATE_ONLY"
      and _blocked_list.iloc[0]["Next_Action"] == "MANUAL_REDIGITIZATION",
      "%s" % _blocked_list.to_dict("records"))
check("  with the raster to re-read it from, and the cell to re-read",
      bool(_blocked_list.iloc[0]["Image_Path"])
      and bool(_blocked_list.iloc[0]["Cell_Key"])
      and bool(_blocked_list.iloc[0]["Unit_ID"]),
      "%s" % _blocked_list.to_dict("records"))
check("  and the panel is still queued for review, because its other cells stand",
      list(pd.read_csv(os.path.join(_R4_DIR, "review_queue.csv"),
                       dtype=object).fillna("")["Panel_ID"]) == ["P1"])
# The cells that CAN be finalized are not on the list. A work list that names
# every cell is a work list nobody reads.
check("  and a value a signature can finalize is not somebody's work",
      len(_blocked_list) < len(_qc), "%d of %d" % (len(_blocked_list), len(_qc)))
# ON THE RUN STAMP, so it is known before an afternoon is spent reviewing rather
# than after. The finalize stamp says the same number from the other end.
_run_stamp4 = json.load(open(os.path.join(_R4_DIR, "run_stamp.json"),
                             encoding="utf-8"))
check("  and the run says how many before anybody opens the queue",
      _run_stamp4["Values_Method_Blocked"] == len(_blocked_list) == 1,
      "%s" % _run_stamp4.get("Values_Method_Blocked"))
check("the stamp counts what it refused, so the yield is not a mystery",
      _stamp4["Values_Method_Blocked"] == 1
      and _stamp4["Values_Accepted"] == len(_qc) - 1, "%s" % _stamp4)
check("and names the cell and the reason",
      any(p["check"] == "VALUE_METHOD_NOT_FINALIZABLE"
          and "FIT_FALLBACK" in p["detail"] for p in _stamp4["Problems"]),
      "%s" % [p["check"] for p in _stamp4["Problems"]])

# ALL of them, and there is nothing to finalize. Distinct from NOTHING_APPROVED,
# which is about the decisions; this is about the evidence, and whoever reads the
# stamp needs different answers to the two.
def _all_extrapolated(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r["Identity_Method"] = "MEASURED_LINE_STYLE"
        r["Value_Method"] = "EXTRAPOLATED_CURVE_INK"
    return rows


try:
    MR.read_panel = _all_extrapolated
    _ALL_DIR, _ = fresh_run("run_tier_all")
finally:
    MR.read_panel = _real_read_panel
_fpall = pd.read_csv(os.path.join(_ALL_DIR, "review_queue.csv"),
                     dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_rall = FIN.finalize(_ALL_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fpall)],
    path=os.path.join(_ALL_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("a panel of nothing but model estimates finalizes nothing",
      _rall["status"] == "NOTHING_FINALIZABLE", "%s" % _rall)
check("and it is not reported as nobody having looked",
      _rall["status"] != "NOTHING_APPROVED" and not os.path.exists(
          os.path.join(_ALL_DIR, "figure_values_accepted.csv")))

# A BLANK PAIR IS NOT AN ABSENCE THIS GATE MAY WAIVE - v7.66, and this scenario
# is the reverse of what it asserted for five releases.
#
# v7.61 blocked only a pair that was STATED and priced at an unfinalizable tier.
# That exception was correct then and only then: five of the six readers answered
# neither question, and treating blank as R4 refused every value in the package.
# v7.64 and v7.65 taught all six, so the exception now protects nothing this
# package produces - and what it does protect is a run made by SOMETHING ELSE.
# `review_tier("", "")` has always been R4; the point of pricing an unregistered
# method at the top is that a gate acts on it.
#
# THE BLANKNESS IS PRODUCED, not inherited: this fixture's panel is LINE_COLOR,
# which answers both questions, so an untaught producer is simulated by a wrapper
# that returns rows without the two keys.
def _no_methods(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r.pop("Identity_Method", None)
        r.pop("Value_Method", None)
    return rows


try:
    MR.read_panel = _no_methods
    _BLANK_DIR, _ = fresh_run("run_blank")
finally:
    MR.read_panel = _real_read_panel
_fpb = pd.read_csv(os.path.join(_BLANK_DIR, "review_queue.csv"),
                   dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_rb = FIN.finalize(_BLANK_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fpb)],
    path=os.path.join(_BLANK_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
_stamp_plain = json.load(open(os.path.join(_BLANK_DIR, "finalize_stamp.json"),
                              encoding="utf-8"))
check("a value that does not say how it was got is refused, not counted",
      _rb["status"] == "NOTHING_FINALIZABLE"
      and _stamp_plain["Values_Accepted"] == 0
      and not os.path.exists(os.path.join(_BLANK_DIR,
                                          "figure_values_accepted.csv")),
      "%s" % _rb)
check("and the refusal is counted in the stamp, not only in the problem list",
      _stamp_plain["Values_Method_Unstated"] > 0
      and _stamp_plain["Values_Method_Blocked"]
      == _stamp_plain["Values_Method_Unstated"], "%s" % _stamp_plain)
check("and every refused cell is named, with the reason and the tier",
      sum(1 for p in _stamp_plain["Problems"]
          if p["check"] == "VALUE_METHOD_UNSTATED" and "/" in p["where"])
      == _stamp_plain["Values_Method_Unstated"]
      and all("R4" in p["detail"] for p in _stamp_plain["Problems"]
              if p["check"] == "VALUE_METHOD_UNSTATED" and "/" in p["where"]),
      "%s" % [p["where"] for p in _stamp_plain["Problems"]])
# HALF-BLANK IS BLANK. A row naming how the number was got and not how the series
# was named is a number with no series behind it, and the pair is what is priced.
def _half_stated(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r.pop("Identity_Method", None)
        r["Value_Method"] = "MARKER_CENTER"
    return rows


try:
    MR.read_panel = _half_stated
    _HALF_DIR, _ = fresh_run("run_half")
finally:
    MR.read_panel = _real_read_panel
_fph = pd.read_csv(os.path.join(_HALF_DIR, "review_queue.csv"),
                   dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_rh = FIN.finalize(_HALF_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fph)],
    path=os.path.join(_HALF_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
_stamp_half = json.load(open(os.path.join(_HALF_DIR, "finalize_stamp.json"),
                             encoding="utf-8"))
check("a row that answers one of the two questions is refused as well",
      _rh["status"] == "NOTHING_FINALIZABLE" and _rh["accepted"] == 0,
      "%s" % _rh)
check("  and is counted as UNSTATED, not as a method that failed on its merits",
      _stamp_half["Values_Method_Unstated"] == _stamp_half["Values_Method_Blocked"]
      > 0
      and all(p["check"] == "VALUE_METHOD_UNSTATED"
              for p in _stamp_half["Problems"]),
      "%s" % {p["check"] for p in _stamp_half["Problems"]})
check("  because the PAIR is what is priced, not the better half",
      PROV.review_tier("", "MARKER_CENTER") == "R4"
      and PROV.review_tier("MEASURED_COLOUR", "MARKER_CENTER") == "R0",
      PROV.review_tier("", "MARKER_CENTER"))
# AND A READER THAT DOES ANSWER CLOSES THE GAP. Same fixture, same panel, the real
# reader: v7.64 taught LINE_COLOR, so this run's values say how the series was
# named and how the number was got, the flag does not fire, and the count is zero.
# This is what the two columns were added for - a run whose evidence a gate can
# actually price.
_taught = fresh_run("run_taught")[0]
_fpt = pd.read_csv(os.path.join(_taught, "review_queue.csv"),
                   dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_rt = FIN.finalize(_taught, review_path=review(
    [row(Review_Subject_SHA256=_fpt)],
    path=os.path.join(_taught, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
_stamp_taught = json.load(open(os.path.join(_taught, "finalize_stamp.json"),
                               encoding="utf-8"))
check("while a reader that answers leaves no gap to count",
      _rt["status"] == "FINALIZED" and _rt["accepted"] > 0
      and _stamp_taught["Values_Method_Unstated"] == 0
      and _stamp_taught["Values_Method_Blocked"] == 0
      and not any(p["check"] == "VALUE_METHOD_UNSTATED"
                  for p in _stamp_taught["Problems"]), "%s" % _stamp_taught)
_acct = pd.read_csv(os.path.join(_taught, "figure_values_accepted.csv"),
                    dtype=object).fillna("")
check("and every accepted value is priced, in the registry's own vocabulary",
      len(_acct) > 0
      and {PROV.review_tier(r["Identity_Method"], r["Value_Method"])
           for _, r in _acct.iterrows()} == {"R0"},
      "%s" % sorted({(r["Identity_Method"], r["Value_Method"])
                     for _, r in _acct.iterrows()}))

print()
print("a cell whose series was reasoned to asks the reviewer one more question")
# R2 IS THE TIER WHERE THE NUMBER IS MEASURED AND THE ROW HEADING IS NOT - named
# by elimination, or matched against a fill prototype formed in another group.
# `Marks_Checked` says the marks are in the right places, which is a different
# sentence: the row heading decides WHICH COLUMN OF THE ANALYSIS this number
# lands in, and it came from reasoning rather than from ink.
#
# The question is priced from the values, not declared anywhere, so a panel
# cannot opt out of it by leaving a column blank.
def _inferred_identity(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r["Identity_Method"] = "COMPLEMENT_OF_DECLARED_STYLES"
        r["Value_Method"] = "DIRECT_CURVE_INK"
    return rows


try:
    MR.read_panel = _inferred_identity
    _R2_DIR, _ = fresh_run("run_inferred")
finally:
    MR.read_panel = _real_read_panel
_q2 = pd.read_csv(os.path.join(_R2_DIR, "review_queue.csv"),
                  dtype=object).fillna("")
_qc2 = pd.read_csv(os.path.join(_R2_DIR, "figure_values_machine_qc.csv"),
                   dtype=object).fillna("")
# v7.65: THE QUESTION IS NOT A MODE. It was two - `OVERLAY_INFERRED` and
# `OVERLAY_INFERRED_CELLS` - and both opened the same overlay as `OVERLAY`, so
# what they carried was a question rather than an artifact. Folded back into the
# values, it reaches every mode: teaching BAR_MONO produced R2 cells on panels
# queued `BAR_MONO_GEOMETRY`, which no overlay-shaped mode name could ask about.
check("the panel is queued in the ordinary mode, with the question beside it",
      list(_q2["Review_Mode"]) == ["OVERLAY"]
      and [int(v or -1) for v in _q2.get("Inference_Cells", [])] == [len(_qc2)],
      "%r / %r" % (list(_q2["Review_Mode"]), list(_q2["Inference_Cells"])))
check("and the question is asked of the values, whatever the mode",
      RB.inference_confirmations(_qc2.to_dict("records"))
      == (RB.INFERENCE_CONFIRMATION,)
      and RB.inference_confirmations([]) == (),
      "%r" % (RB.inference_confirmations(_qc2.to_dict("records")),))
_fp2 = _q2.loc[0, "Review_Subject_SHA256"]
_r2_path = os.path.join(_R2_DIR, "value_review.csv")
_no_inf = FIN.finalize(_R2_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fp2)], path=_r2_path),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("an approval that does not mention the inference is not an approval",
      _no_inf["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "REVIEW_CONFIRMATION_MISSING"
              for p in _no_inf["problems"]),
      "%s" % _no_inf)
check("and no accepted file was written",
      not os.path.exists(os.path.join(_R2_DIR, "figure_values_accepted.csv")))
_with_inf = FIN.finalize(_R2_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fp2, Inference_Checked="CONFIRMED")],
    path=_r2_path), run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("with it, the same panel finalizes",
      _with_inf["status"] == "FINALIZED" and _with_inf["accepted"] > 0,
      "%s" % _with_inf)
# AND IT IS NOT ASKED OF EVERY PANEL. A confirmation column every panel carries
# is a column everybody types CONFIRMED into - which is why this is a MODE and
# not a fifth question on OVERLAY. The plain run above is queued as OVERLAY and
# finalizes without it.
_plain_q = pd.read_csv(os.path.join(OUT, "review_queue.csv"),
                       dtype=object).fillna("")
check("a panel with nothing inferred is not asked about inference",
      list(_plain_q["Review_Mode"]) == ["OVERLAY"]
      and "Inference_Checked" not in RB.REVIEW_CONFIRMATIONS["OVERLAY"],
      "%r / %r" % (list(_plain_q["Review_Mode"]),
                   RB.REVIEW_CONFIRMATIONS["OVERLAY"]))
# A blank pair asks nothing either: the readers that do not answer yet cannot be
# gated, and pricing their silence as an inference would put the question on
# every panel in the package.
check("nor is a panel whose reader does not answer the question at all",
      list(pd.read_csv(os.path.join(_BLANK_DIR, "review_queue.csv"),
                       dtype=object).fillna("")["Review_Mode"]) == ["OVERLAY"])

print()
print("a cell whose number was reconstructed is answered for by itself")
# R3 IS THE TIER WHERE THE NUMBER CAME FROM NEIGHBOURING INK rather than from ink
# at the cell - a bracketed interpolation across a masked stretch, or the edge of
# a run too thick to be one stroke. A panel-level "I looked at the inferences"
# cannot carry it: one wrong cell in twenty does not show up in a single answer,
# and the overlay draws a mark either way. So the questions are enumerated and the
# answers have to match them exactly.
def _reconstructed(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for i, r in enumerate(rows):
        r["Identity_Method"] = "MEASURED_LINE_STYLE"
        r["Value_Method"] = ("LOCAL_BRACKETED_INTERPOLATION" if i < 2
                             else "DIRECT_CURVE_INK")
        if i >= 2:
            continue
        # A READER THAT RECONSTRUCTS A NUMBER SAYS BETWEEN WHICH COLUMNS. The
        # first version of this wrapper set the method and nothing else, which is
        # a reader claiming a bracketed interpolation with no brackets - and from
        # v7.67 that panel is refused, because no picture of the cell can be
        # drawn from a row that does not say where the ink was.
        r["Value_Support_Left_Px"] = float(r["x"]) - 2
        r["Value_Support_Right_Px"] = float(r["x"]) + 2
        r["Value_Span_Px"] = 4
        r["Occlusion_Cause"] = "ERRORBAR_STEM"
        r["Occlusion_Width_Px"] = 3
        r["Local_Stroke_Px"] = 2
        r["Expected_Dash_Gap_Px"] = 0
        r["Trace_Agreement"] = "AGREED"
    return rows


try:
    MR.read_panel = _reconstructed
    _R3_DIR, _r3_summary = fresh_run("run_cells")
finally:
    MR.read_panel = _real_read_panel
_q3 = pd.read_csv(os.path.join(_R3_DIR, "review_queue.csv"),
                  dtype=object).fillna("")
check("the panel is queued in the ordinary mode, and counts its reasoned cells",
      list(_q3["Review_Mode"]) == ["OVERLAY"]
      and [int(v or -1) for v in _q3.get("Inference_Cells", [])] == [2],
      "%r / %r" % (list(_q3["Review_Mode"]), list(_q3["Inference_Cells"])))
# THE ARTIFACT REQUIREMENT IS DERIVED TOO, and always was: no review mode names
# `INFERENCE_MANIFEST`. `inference_contract_failures` requires it of a panel whose
# VALUES hold a reconstructed number, which is why v7.65 could drop the two modes
# without touching this half of the contract - and why a run made by a producer
# that never wrote the file is refused rather than believed.
check("and no mode requires the list of cells - the values do",
      not any("INFERENCE_MANIFEST" in types
              for types in RB.REVIEW_MODES.values()),
      "%r" % {m: t for m, t in RB.REVIEW_MODES.items()
              if "INFERENCE_MANIFEST" in t})
_led3 = pd.read_csv(os.path.join(_R3_DIR, "panel_artifacts.csv"),
                    dtype=object).fillna("")
_man3 = _led3[_led3["Artifact_Type"] == "INFERENCE_MANIFEST"]
check("the run wrote that list and registered it, so it is hashed",
      len(_man3) == 1
      and os.path.exists(RB.resolve_artifact(_R3_DIR,
                                             _man3.iloc[0]["Artifact_Path"]))
      and len(_man3.iloc[0]["SHA256"]) == 64,
      "%s" % _man3.to_dict("records"))
_qc3 = pd.read_csv(os.path.join(_R3_DIR, "figure_values_machine_qc.csv"),
                   dtype=object).fillna("")
_cells3 = FIN.collect_inference_manifests(_R3_DIR)
# THE EVIDENCE IS ON THE ROW, not only in the reader's memory. v7.66 bound
# `Inference_ID` to these eight columns and every one of them hashed as the empty
# string, because the value row the finalizer re-derives from did not carry them:
# the recipe named columns that existed on the mark and nowhere else.
_manifest_evidence = [r for r in _cells3
                      if all(FIN._s(r.get(c)) for c in
                             ("Value_Span_Px", "Value_Support_Left_Px",
                              "Value_Support_Right_Px", "Occlusion_Cause",
                              "Local_Stroke_Px", "Trace_Agreement"))]
check("the list a reviewer reads carries the evidence, not just the answer",
      len(_manifest_evidence) == len(_cells3) == 2,
      "%s" % [{k: v for k, v in r.items() if "Px" in k or "Occlusion" in k}
              for r in _cells3])
check("  and the same columns are on the value row the finalizer re-derives from",
      all(c in _qc3.columns for c in RB.INFERENCE_IDENTITY_FIELDS
          if c not in ("Panel_ID",)),
      "%s" % [c for c in RB.INFERENCE_IDENTITY_FIELDS
              if c not in ("Panel_ID",) and c not in _qc3.columns])

check("and it lists the reconstructed cells and nothing else",
      len(_cells3) == 2
      and {r["Value_Method"] for r in _cells3} == {"LOCAL_BRACKETED_INTERPOLATION"}
      and len(_qc3) > 2, "%d of %d" % (len(_cells3), len(_qc3)))
# Content-derived, and the number is part of the content: a re-run that
# reconstructs the same cell to a different value has not been confirmed.
_probe = dict(Unit_ID="U1", Cell_Key="ARM=CONTROL;TIMEPOINT=T0",
              Identity_Method="MEASURED_LINE_STYLE",
              Value_Method="LOCAL_BRACKETED_INTERPOLATION",
              Mean="12.5", Dispersion_Value="1.0")
check("the identifier is derived from the cell, the method and the number",
      RB.inference_id(_probe, panel_id="P1")
      == RB.inference_id(dict(_probe, Note="anything"), panel_id="P1")
      and RB.inference_id(_probe, panel_id="P1")
      != RB.inference_id(dict(_probe, Mean="12.6"), panel_id="P1")
      and RB.inference_id(_probe, panel_id="P1")
      != RB.inference_id(_probe, panel_id="P2"),
      RB.inference_id(_probe, panel_id="P1"))
# AND FROM THE EVIDENCE, NOT ONLY THE ANSWER - v7.66. Hashing the cell, the
# methods and the number binds the OUTPUT, and output and evidence move
# independently: a re-run whose supports shift and whose occlusion changes from
# one cause to MIXED can land on the same mean, and a curve is smooth enough over
# a few pixels that it does not have to be much of a coincidence. The identifier
# was then unchanged and a confirmation given against the first reconstruction
# attached itself to the second. The panel's subject hash does go stale in that
# case - but the two files are filled in by different people at different times,
# and nothing made the cell answer expire with the panel one.
_evidence = dict(_probe, Source_Panel_ID="P1", Value_Span_Px="3",
                 Value_Support_Left_Px="101", Value_Support_Right_Px="104",
                 Occlusion_Cause="ERRORBAR_STEM", Occlusion_Width_Px="2",
                 Local_Stroke_Px="3", Expected_Dash_Gap_Px="0",
                 Trace_Agreement="AGREED")
_base_id = RB.inference_id(_evidence, panel_id="P1")
for _field, _moved in (("Value_Support_Left_Px", "96"),
                       ("Value_Support_Right_Px", "109"),
                       ("Value_Span_Px", "13"),
                       ("Occlusion_Cause", "MIXED"),
                       ("Occlusion_Width_Px", "6"),
                       ("Local_Stroke_Px", "4"),
                       ("Expected_Dash_Gap_Px", "5"),
                       ("Trace_Agreement",
                        "CONSERVATIVE_OF_CONFLICTING_TRACES")):
    check("  %s moving refuses the old confirmation, at the same mean" % _field,
          RB.inference_id(dict(_evidence, **{_field: _moved}), panel_id="P1")
          != _base_id, _field)
check("  while a re-run that reproduces the evidence keeps the same id",
      RB.inference_id(dict(_evidence), panel_id="P1") == _base_id
      # And a number that has been through a CSV hashes as the number it is:
      # the run derives these in memory and `finalize` derives them again from
      # the file, so `12.5` and `"12.50"` cannot be two different questions.
      and RB.inference_id(dict(_evidence, Mean=12.50), panel_id="P1") == _base_id
      and RB.inference_id(dict(_evidence, Value_Span_Px="3.0"),
                          panel_id="P1") == _base_id, _base_id)
check("  and every field of the row a reviewer reads is in the recipe",
      set(RB.INFERENCE_IDENTITY_FIELDS)
      == set(RB.INFERENCE_MANIFEST_COLUMNS) - {"Inference_ID"},
      "%s" % sorted(set(RB.INFERENCE_MANIFEST_COLUMNS)
                    - {"Inference_ID"} - set(RB.INFERENCE_IDENTITY_FIELDS)))
check("and the ids in the file are the ones the finalizer re-derives",
      {r["Inference_ID"] for r in _cells3}
      == {RB.inference_id(v, panel_id=FIN._s(v.get("Run_Panel_ID")))
          for v in _qc3.to_dict("records")
          if FIN._s(v.get("Value_Method")) == "LOCAL_BRACKETED_INTERPOLATION"},
      "%s" % sorted(r["Inference_ID"] for r in _cells3))

# AND THE LIST IS PART OF WHAT THE PANEL'S APPROVAL IS OF. Registered in the
# ledger, so a run that reconstructs one more cell than the run somebody signed
# for is APPROVAL_STALE rather than an extra question nobody was asked.
_arts3 = [(r["Artifact_Type"], r["Artifact_Path"], r["SHA256"],
           r["Artifact_Reference"])
          for _, r in _led3.iterrows() if r["Panel_ID"] == "P1"]
check("dropping the list of cells changes what the approval is of",
      RB.review_subject_sha256({"Panel_ID": "P1"}, [], {}, {},
                               artifacts=_arts3)
      != RB.review_subject_sha256(
          {"Panel_ID": "P1"}, [], {}, {},
          artifacts=[a for a in _arts3 if a[0] != "INFERENCE_MANIFEST"]),
      "%s" % [a[0] for a in _arts3])

_ids3_pre = sorted(r["Inference_ID"] for r in _cells3)
# AND A PICTURE OF EACH ONE. The manifest gives a reviewer the supports, the span
# and the cause as pixel NUMBERS; holding a coordinate in your head against a
# printed figure is arithmetic performed by somebody who cannot check it.
_ctx3 = _led3[_led3["Artifact_Type"] == "INFERENCE_CONTEXT"]
check("every cell asked about by name has a picture of itself",
      len(_ctx3) == 2
      and set(_ctx3["Artifact_Reference"]) == set(_ids3_pre)
      and all(os.path.exists(RB.resolve_artifact(_R3_DIR, p_))
              for p_ in _ctx3["Artifact_Path"]),
      "%s" % _ctx3[["Artifact_Path", "Artifact_Reference"]].to_dict("records"))
check("  registered against the Inference_ID it belongs to, not by filename",
      all(_s_ref.startswith("INF_") for _s_ref in _ctx3["Artifact_Reference"]),
      "%s" % list(_ctx3["Artifact_Reference"]))
# A READER THAT RECONSTRUCTS A NUMBER WITHOUT SAYING BETWEEN WHICH COLUMNS gets
# no picture, and a cell nobody can see is a cell nobody can confirm. Refused,
# rather than confirmed against a caption.
def _no_supports(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for i, r in enumerate(rows):
        r["Identity_Method"] = "MEASURED_LINE_STYLE"
        r["Value_Method"] = ("LOCAL_BRACKETED_INTERPOLATION" if i < 1
                             else "DIRECT_CURVE_INK")
    return rows


try:
    MR.read_panel = _no_supports
    _NOCTX_DIR, _ = fresh_run("run_nocontext")
finally:
    MR.read_panel = _real_read_panel
_led_noctx = pd.read_csv(os.path.join(_NOCTX_DIR, "panel_artifacts.csv"),
                         dtype=object).fillna("")
_q_noctx = pd.read_csv(os.path.join(_NOCTX_DIR, "review_queue.csv"),
                       dtype=object).fillna("")
_cells_noctx = FIN.collect_inference_manifests(_NOCTX_DIR)
_r_noctx = FIN.finalize(_NOCTX_DIR, review_path=review(
    [row(Review_Subject_SHA256=_q_noctx.loc[0, "Review_Subject_SHA256"],
         Inference_Checked="CONFIRMED")],
    path=os.path.join(_NOCTX_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("a reconstruction with no supports on the row can be pictured by nobody",
      len(_cells_noctx) == 1
      and not any(_led_noctx["Artifact_Type"] == "INFERENCE_CONTEXT"),
      "%s" % sorted(set(_led_noctx["Artifact_Type"])))
check("  so the panel is held, whatever the decision file says",
      _r_noctx["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "INFERENCE_CONTEXT_MISSING"
              for p in _r_noctx["problems"]), "%s" % _r_noctx)

_fp3 = _q3.loc[0, "Review_Subject_SHA256"]
_r3_review = os.path.join(_R3_DIR, "value_review.csv")
_r3_cells = os.path.join(_R3_DIR, "inference_review.csv")
_ids3 = sorted(r["Inference_ID"] for r in _cells3)


def _panel3():
    return review([row(Review_Subject_SHA256=_fp3,
                       Inference_Checked="CONFIRMED")], path=_r3_review)


def _answers(rows):
    with open(_r3_cells, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.inference_review_columns())
        for r in rows:
            w.writerow([r.get(c, "") for c in FIN.inference_review_columns()])
    return _r3_cells


def _answer(iid, verdict="CONFIRMED", **kw):
    base = dict(Inference_ID=iid, Panel_ID="P1", Reviewer_ID="RV_H",
                Inference_Confirmed=verdict, Reviewed_At="2026-08-06T10:00:00Z")
    base.update(kw)
    return base


def _finalize3():
    return FIN.finalize(_R3_DIR, review_path=_panel3(), run_date="2026-08-06",
                        today=datetime.date(2026, 8, 6))


if os.path.exists(_r3_cells):
    os.remove(_r3_cells)
_none = _finalize3()
check("an approval with no per-cell answers finalizes nothing",
      _none["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "INFERENCE_CONFIRMATION_MISSING"
              for p in _none["problems"]), "%s" % _none)
check("and the refusal names the cell and how its number was got",
      any("LOCAL_BRACKETED_INTERPOLATION" in p["detail"]
          for p in _none["problems"]
          if p["check"] == "INFERENCE_CONFIRMATION_MISSING"),
      "%s" % [p["detail"] for p in _none["problems"]])
_answers([_answer(_ids3[0])])
_half = _finalize3()
check("answering one of two is not answering", _half["status"] == "NOTHING_APPROVED"
      and sum(1 for p in _half["problems"]
              if p["check"] == "INFERENCE_CONFIRMATION_MISSING") == 1,
      "%s" % _half)
_answers([_answer(i) for i in _ids3])
_all3 = _finalize3()
check("a confirmed answer for every one of them finalizes",
      _all3["status"] == "FINALIZED" and _all3["accepted"] == len(_qc3),
      "%s of %d" % (_all3, len(_qc3)))
_stamp3 = json.load(open(os.path.join(_R3_DIR, "finalize_stamp.json"),
                         encoding="utf-8"))
check("and the stamp records those decisions by content, not by path",
      _stamp3["Inference_Review_File_SHA256"] == RB.file_sha256(_r3_cells)
      and _stamp3["Values_Inference_Rejected"] == 0, "%s" % _stamp3)
# REJECTED IS AN ANSWER, AND IT COSTS THE CELL. A reviewer who can see that one
# reconstruction is wrong should not have to throw away the values beside it -
# which is what a contract with only CONFIRMED and silence would make them do.
_answers([_answer(_ids3[0]), _answer(_ids3[1], "REJECTED")])
_rej = _finalize3()
_acc3 = pd.read_csv(os.path.join(_R3_DIR, "figure_values_accepted.csv"),
                    dtype=object).fillna("")
_stamp_rej = json.load(open(os.path.join(_R3_DIR, "finalize_stamp.json"),
                            encoding="utf-8"))
check("a refused reconstruction costs its cell and not its panel",
      _rej["status"] == "FINALIZED" and len(_acc3) == len(_qc3) - 1
      and _stamp_rej["Values_Inference_Rejected"] == 1, "%s" % _rej)
check("and the refused cell is the one that is gone",
      sum(1 for _, r in _acc3.iterrows()
          if RB.inference_id(r.to_dict(),
                             panel_id=FIN._s(r.get("Run_Panel_ID"))) == _ids3[1]) == 0
      and any(p["check"] == "INFERENCE_REJECTED" for p in _rej["problems"]),
      "%s" % [p["check"] for p in _rej["problems"]])
_answers([_answer(i, "REJECTED") for i in _ids3]
         + [_answer(RB.inference_id(v, panel_id=FIN._s(v.get("Run_Panel_ID"))),
                    "REJECTED")
            for v in _qc3.to_dict("records")
            if FIN._s(v.get("Value_Method")) != "LOCAL_BRACKETED_INTERPOLATION"])
_all_rej = _finalize3()
check("answers for cells this run did not ask about are refused, not ignored",
      _all_rej["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "INFERENCE_CONFIRMATION_UNKNOWN"
              for p in _all_rej["problems"]), "%s" % _all_rej)
_answers([_answer(_ids3[0]), _answer(_ids3[0]), _answer(_ids3[1])])
_dup = _finalize3()
check("two answers for one cell cannot be told apart, so neither applies",
      _dup["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "INFERENCE_CONFIRMATION_DUPLICATE"
              for p in _dup["problems"]), "%s" % _dup)
_answers([_answer(_ids3[0]), _answer(_ids3[1], "")])
_blank3 = _finalize3()
check("a blank verdict is not one of the two answers",
      _blank3["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "BAD_INFERENCE_DECISION"
              for p in _blank3["problems"]), "%s" % _blank3)
_answers([_answer(_ids3[0]), _answer(_ids3[1], Reviewer_ID="RV_D")])
_demo3 = _finalize3()
check("and a demonstration identity cannot confirm a reconstruction either",
      _demo3["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED"
              for p in _demo3["problems"]), "%s" % _demo3)
_answers([_answer(_ids3[0], Reviewed_At="2027-01-01T00:00:00Z"),
          _answer(_ids3[1])])
_future3 = _finalize3()
check("nor can a confirmation dated after the day it is read",
      _future3["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "BAD_REVIEWED_AT" for p in _future3["problems"]),
      "%s" % _future3)
# THE TEMPLATE IS WHY A REVIEWER NEVER TYPES ONE OF THESE IDS. Copied by hand,
# one transposed character is an answer to a question nobody asked - which the
# contract above reports rather than accepts, but the reviewer's afternoon is
# gone either way.
_tmpl3 = os.path.join(_R3_DIR, "template_inference.csv")
FIN.write_inference_template(_tmpl3, _cells3)
_tmpl_rows = pd.read_csv(_tmpl3, dtype=object).fillna("")
check("the template pre-fills every id, panel, unit and cell",
      list(_tmpl_rows.columns) == FIN.inference_review_columns()
      and sorted(_tmpl_rows["Inference_ID"]) == _ids3
      and set(_tmpl_rows["Inference_Confirmed"]) == {""},
      "%s" % _tmpl_rows.to_dict("records"))
# AND A PANEL WITH NOTHING RECONSTRUCTED IS NOT ASKED FOR THE FILE AT ALL. The
# ordinary run has no `inference_review.csv` anywhere near it, and finalizes.
check("a panel with no reconstructed value needs no per-cell file",
      list(pd.read_csv(os.path.join(OUT, "review_queue.csv"),
                       dtype=object).fillna("")["Review_Mode"]) == ["OVERLAY"]
      and not os.path.exists(os.path.join(OUT, "inference_review.csv")))
# THE CONTRACT IS RE-DERIVED FROM THE VALUES, NOT READ OFF THE LEDGER. Nothing
# pins a minimum pipeline version, so a run made by an older producer arrives with
# a complete-looking ledger and no manifest at all. Called directly, because a
# ledger edited on disk is RUN_ARTIFACT_MODIFIED long before this check runs.
_p3 = []
_held, _rejected = FIN.inference_contract_failures(
    _R3_DIR, _led3[_led3["Artifact_Type"] != "INFERENCE_MANIFEST"], _qc3,
    pd.DataFrame([_answer(i) for i in _ids3]), pd.DataFrame(REVIEWERS),
    lambda w, c, d: _p3.append(c), today=datetime.date(2026, 8, 6),
    panels={"P1"})
check("a run whose producer wrote no list of cells is withheld",
      _held == {"P1"} and "INFERENCE_MANIFEST_MISSING" in _p3, "%s" % _p3)
# And a run whose values have MOVED since the list was written: same cells, one
# different number, so the ids the finalizer re-derives are not the ids a person
# was handed. Nudged in the frame rather than on disk, for the same reason.
_p3 = []
_moved = _qc3.copy()
_moved.loc[_moved["Value_Method"] == "LOCAL_BRACKETED_INTERPOLATION",
           "Mean"] = "999.9"
_held, _ = FIN.inference_contract_failures(
    _R3_DIR, _led3, _moved,
    pd.DataFrame([_answer(i) for i in _ids3]), pd.DataFrame(REVIEWERS),
    lambda w, c, d: _p3.append(c), today=datetime.date(2026, 8, 6),
    panels={"P1"})
check("and so is one whose list is not the questions its values ask",
      _held == {"P1"} and "INFERENCE_MANIFEST_MISMATCH" in _p3, "%s" % _p3)

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
                 Marks_Checked="CONFIRMED",
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
print("a run stamp that cannot be read is a refusal, not a traceback")
# Every other file this module reads is guarded; `run_stamp.json` was not, and
# the accepted file and the previous stamp are deleted before it is opened - so
# a truncated one raised out of the finalizer leaving the run with no result
# AND no stamp explaining the absence.
for _label, _write in (
        ("truncated JSON", lambda p: open(p, "a", encoding="utf-8").write("{{")),
        ("a JSON list", lambda p: open(p, "w", encoding="utf-8").write("[1, 2]")),
        ("a bare scalar", lambda p: open(p, "w", encoding="utf-8").write("42")),
        ("bytes that are not UTF-8", lambda p: open(p, "wb").write(b"\xff\xfe{}")),
        ("nothing at all", lambda p: open(p, "w", encoding="utf-8").write(""))):
    _s_out, _ = fresh_run("run_stamp_%d" % (abs(hash(_label)) % 10 ** 6))
    _sq = pd.read_csv(os.path.join(_s_out, "review_queue.csv"), dtype=object)
    _srv = review([dict(Review_ID="R001", Panel_ID="P1",
                        Review_Subject_SHA256=_sq.loc[0, "Review_Subject_SHA256"],
                        Reviewer_ID="RV_H", Decision="APPROVED",
                        Marks_Checked="CONFIRMED",
                        Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                  os.path.join(_s_out, "value_review.csv"))
    _write(os.path.join(_s_out, "run_stamp.json"))
    try:
        _sr = FIN.finalize(_s_out, review_path=_srv, run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
    except Exception as _exc:
        _sr = dict(status="RAISED %s" % type(_exc).__name__, accepted=0)
    check("a run stamp that is %s is refused, not raised" % _label,
          _sr["status"] == "RUN_NOT_FINALIZABLE" and _sr["accepted"] == 0,
          "%s" % _sr["status"])
    check("  and the refusal is itself on the record (%s)" % _label,
          os.path.exists(os.path.join(_s_out, "finalize_stamp.json")),
          "%s" % sorted(os.listdir(_s_out)))
    check("  and nothing poolable survives it (%s)" % _label,
          not os.path.exists(os.path.join(_s_out, "figure_values_accepted.csv")))


print()
print("a stamp can be a well-formed object with a malformed field inside it")
# The top-level guard checks that `run_stamp.json` is an object. It was, in each
# of these: `Output_SHA256: ["x"]` is valid JSON. `recorded.get(name)` on a list
# then raised AttributeError - after the accepted file and the previous stamp
# were deleted - so the exact failure the top-level guard exists to prevent came
# back one level down. A guard on the outside of a structure is not a guard on
# what is inside it.
for _label, _value in (("a list", ["x"]), ("a string", "abcdef"),
                       ("a boolean", True), ("a number", 7),
                       ("an object whose hashes are not strings",
                        {"run_manifest.csv": 5})):
    _n_out, _ = fresh_run("run_nested_%d" % (abs(hash(_label)) % 10 ** 6))
    _nq = pd.read_csv(os.path.join(_n_out, "review_queue.csv"), dtype=object)
    _nrv = review([dict(Review_ID="R001", Panel_ID="P1",
                        Review_Subject_SHA256=_nq.loc[0, "Review_Subject_SHA256"],
                        Reviewer_ID="RV_H", Decision="APPROVED",
                        Marks_Checked="CONFIRMED",
                        Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                  os.path.join(_n_out, "value_review.csv"))
    _np = os.path.join(_n_out, "run_stamp.json")
    _nd = json.load(open(_np))
    _nd["Output_SHA256"] = _value
    json.dump(_nd, open(_np, "w"))
    check("  the fixture is still valid JSON with an object at the root (%s)"
          % _label,
          isinstance(json.load(open(_np)), dict))
    try:
        _nr = FIN.finalize(_n_out, review_path=_nrv, run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
    except Exception as _exc:
        _nr = dict(status="RAISED %s" % type(_exc).__name__, accepted=0)
    check("Output_SHA256 as %s is refused, not raised" % _label,
          _nr["status"] in ("RUN_ARTIFACT_MODIFIED", "RUN_NOT_FINALIZABLE")
          and _nr["accepted"] == 0, "%s" % _nr["status"])
    check("  and the refusal names the schema, not a hash mismatch (%s)" % _label,
          any(p["check"] == "RUN_STAMP_SCHEMA_INVALID" for p in _nr["problems"]),
          "%s" % sorted({p["check"] for p in _nr["problems"]}))
    check("  and it is on the record with nothing poolable (%s)" % _label,
          os.path.exists(os.path.join(_n_out, "finalize_stamp.json"))
          and not os.path.exists(os.path.join(_n_out,
                                              "figure_values_accepted.csv")))


print()
print("every failure ends in a stamp, including one it cannot parse")
# Hashing is bytes; parsing is interpretation. Doing them the other way round
# meant a machine-QC CSV with a broken quote raised out of pd.read_csv before
# verification ran - and by then the previous accepted file and stamp had
# already been deleted, so the run was left with neither a result nor a stamp
# saying why.
for _target, _corrupt in (("figure_values_machine_qc.csv", True),
                          ("review_queue.csv", True),
                          ("panel_artifacts.csv", True)):
    _p_out, _ = fresh_run("run_parse_%s" % _target.split(".")[0][:12])
    _pq = pd.read_csv(os.path.join(_p_out, "review_queue.csv"), dtype=object)
    _prv = review([dict(Review_ID="R001", Panel_ID="P1",
                        Review_Subject_SHA256=_pq.loc[0, "Review_Subject_SHA256"],
                        Reviewer_ID="RV_H", Decision="APPROVED",
                        Marks_Checked="CONFIRMED",
                        Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                  os.path.join(_p_out, "value_review.csv"))
    with open(os.path.join(_p_out, _target), "a", encoding="utf-8") as _fh:
        _fh.write('"unterminated,,,\n')
    try:
        _pr = FIN.finalize(_p_out, review_path=_prv, run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
    except Exception as _exc:
        # Which is the defect: the accepted file and the stamp are deleted
        # first, so an exception here leaves the run with neither a result nor
        # an explanation.
        _pr = dict(status="RAISED %s: %s" % (type(_exc).__name__, _exc),
                   accepted=0)
    check("a malformed %s is refused, not raised" % _target,
          _pr["status"] in ("RUN_ARTIFACT_MODIFIED", "RUN_NOT_FINALIZABLE")
          and _pr["accepted"] == 0, "%s" % _pr["status"])
    check("  and leaves a stamp saying so (%s)" % _target,
          os.path.exists(os.path.join(_p_out, "finalize_stamp.json"))
          and json.load(open(os.path.join(_p_out, "finalize_stamp.json")))["Status"]
          == _pr["status"],
          "%s" % sorted(os.listdir(_p_out)))
    check("  and no accepted file (%s)" % _target,
          not os.path.exists(os.path.join(_p_out, "figure_values_accepted.csv")))


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
             Marks_Checked="CONFIRMED",
             Reviewed_At="2026-08-06T10:00:00Z", Note="")],
       os.path.join(_mv_src, "value_review.csv"))
_mv_dst = os.path.join(ROOT, "moved_elsewhere")
shutil.move(_mv_src, _mv_dst)
# No --manifests. The stamp records the absolute directory the run used, which
# is a path on the machine the run happened on; a `manifests/` directory sitting
# inside the run travels with it, and is now looked for first. Without that, a
# run folder handed to somebody else needed the sender to also explain where
# their manifests had been.
_moved = subprocess.run(
    [sys.executable, os.path.join(HERE, "finalize_batch.py"), _mv_dst,
     "--review", os.path.join(_mv_dst, "value_review.csv"), "--date", "2026-08-06"],
    capture_output=True, text=True, cwd=tempfile.gettempdir())
check("a moved run finalizes from an unrelated working directory",
      _moved.returncode == 0
      and os.path.exists(os.path.join(_mv_dst, "figure_values_accepted.csv")),
      "%s%s" % (_moved.stdout[-400:], _moved.stderr[-200:]))
# Finalizing is not the whole of portability. The queue tells a person which
# picture to open and the accepted file tells a re-analyst where the points
# are; both used to record the path the run happened to have, so handing the
# finished data to another folder or another machine broke every one of those
# links while the file still looked complete.
_mv_q = pd.read_csv(os.path.join(_mv_dst, "review_queue.csv"), dtype=object).fillna("")
check("and the moved queue still points at pictures that exist",
      all(RB.resolve_artifact(_mv_dst, r["Overlay_File"])
          and os.path.exists(RB.resolve_artifact(_mv_dst, r["Overlay_File"]))
          for _, r in _mv_q.iterrows()),
      "%s" % list(_mv_q["Overlay_File"]))
_mv_acc = pd.read_csv(os.path.join(_mv_dst, "figure_values_accepted.csv"),
                      dtype=object).fillna("")
_mv_refs = [v for c in ("Point_Data_Reference", "WPD_Project_File")
            for v in _mv_acc.get(c, []) if v]
check("and every provenance reference in the accepted file still resolves",
      _mv_refs and all(
          RB.resolve_artifact(_mv_dst, v)
          and os.path.exists(RB.resolve_artifact(_mv_dst, v)) for v in _mv_refs),
      "%s" % sorted(set(_mv_refs))[:4])
check("and none of them names the directory the run happened in",
      not any(os.path.isabs(v) for v in _mv_refs)
      and not any(os.path.isabs(v) for v in _mv_q["Overlay_File"] if v),
      "%s" % [v for v in _mv_refs if os.path.isabs(v)][:3])


# Bytes, not decoded text. Text hashing goes through an encoding and a newline
# convention, so a file that does not decode cannot be hashed at all - and the
# thing being protected is the file on disk, not a string derived from it.
_bh_out, _ = fresh_run("run_bytehash")
_bh_stamp = json.load(open(os.path.join(_bh_out, "run_stamp.json")))
check("the run hashes its outputs as bytes",
      all(_bh_stamp["Output_SHA256"][n] == RB.file_sha256(os.path.join(_bh_out, n))
          for n in _bh_stamp["Output_SHA256"]),
      "%s" % sorted(_bh_stamp["Output_SHA256"]))
check("and the finalizer checks them the same way",
      all(n in _bh_stamp["Output_SHA256"] for n in FIN.VERIFIED_OUTPUTS),
      "%s" % sorted(set(FIN.VERIFIED_OUTPUTS) - set(_bh_stamp["Output_SHA256"])))
# The difference is reachable. Text hashing opens the file as UTF-8, so an
# output corrupted with bytes that are not valid UTF-8 raised out of the
# verifier instead of failing it - after the accepted file and stamp were
# already gone.
_bh_rv = review([dict(Review_ID="R001", Panel_ID="P1",
                      Review_Subject_SHA256=pd.read_csv(
                          os.path.join(_bh_out, "review_queue.csv"),
                          dtype=object).loc[0, "Review_Subject_SHA256"],
                      Reviewer_ID="RV_H", Decision="APPROVED",
                      Marks_Checked="CONFIRMED",
                      Reviewed_At="2026-08-06T10:00:00Z", Note="")],
                os.path.join(_bh_out, "value_review.csv"))
with open(os.path.join(_bh_out, "run_manifest.csv"), "ab") as _fh:
    _fh.write(b"\xff\xfe not utf-8\n")
try:
    _bh_r = FIN.finalize(_bh_out, review_path=_bh_rv, run_date="2026-08-06",
                         today=datetime.date(2026, 8, 6))
except Exception as _exc:
    _bh_r = dict(status="RAISED %s" % type(_exc).__name__, accepted=0)
check("an output corrupted with non-UTF-8 bytes is refused, not raised",
      _bh_r["status"] == "RUN_ARTIFACT_MODIFIED" and _bh_r["accepted"] == 0,
      "%s" % _bh_r["status"])
check("  and it leaves a stamp saying so",
      os.path.exists(os.path.join(_bh_out, "finalize_stamp.json"))
      and not os.path.exists(os.path.join(_bh_out, "figure_values_accepted.csv")))


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
                       Marks_Checked="CONFIRMED",
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
                   Marks_Checked="CONFIRMED",
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
                   Marks_Checked="CONFIRMED",
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
                       Marks_Checked="CONFIRMED",
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

# An approval says a person agreed. It does not say what they LOOKED at, and
# the two are different claims: the whole reason a panel is queued with an
# artifact is that somebody opens it, and `Decision=APPROVED` down a column is
# indistinguishable from a review.
#
# REVERT: drop REVIEW_CONFIRMATIONS from the finalizer. Every scenario above
# still passes - they all fill the field now - and a run where nobody opened a
# single overlay finalizes exactly like one where somebody opened all of them.
print()
print("an approval has to say what was checked, not only that it was approved")
for _label, _value, _want in (("blank", "", False), ("no", "NO", False),
                              ("confirmed", "CONFIRMED", True),
                              ("lower case", "confirmed", True)):
    _r = FIN.finalize(OUT, review_path=review([row(Marks_Checked=_value)]),
                      run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6))
    check("Marks_Checked=%s -> %s" % (_label or "blank",
                                      "finalized" if _want else "refused"),
          (_r["status"] == "FINALIZED") is _want
          and (_want or any(p["check"] == "REVIEW_CONFIRMATION_MISSING"
                            for p in _r["problems"])),
          "%s %r" % (_r["status"], _r.get("problems")))
check("the confirmation the mode asks for is the one it can answer",
      RB.REVIEW_CONFIRMATIONS["OVERLAY"] == ("Marks_Checked",)
      and set(RB.REVIEW_CONFIRMATIONS) == set(RB.REVIEW_MODES),
      repr(RB.REVIEW_CONFIRMATIONS))
check("and the template ships the column, so a reviewer has somewhere to say it",
      "Marks_Checked" in FIN.value_review_columns()
      and "Marks_Checked" in open(
          os.path.join(HERE, "value_review_TEMPLATE.csv"),
          encoding="utf-8").readline())

# REVERT: `REVIEW_MODES[mode] not in artifact_types`. One artifact per mode is
# a limit of the table, not of review: a mode that needs the numbers, the
# pictures and the index tying them together can then declare one of the three
# and be approved without the other two.
print()
print("a mode may require more than one artifact, and all of them must be there")
_multi_out, _ = fresh_run("run_two_artifacts")
_mq = pd.read_csv(os.path.join(_multi_out, "review_queue.csv"), dtype=object)
_multi_rv = review(
    [dict(Review_ID="R%03d" % (i + 1), Panel_ID=r["Panel_ID"],
          Review_Subject_SHA256=r["Review_Subject_SHA256"],
          Reviewer_ID="RV_H", Decision="APPROVED", Marks_Checked="CONFIRMED",
          Reviewed_At="2026-08-06T10:00:00Z", Note="")
     for i, (_, r) in enumerate(_mq.iterrows())],
    os.path.join(_multi_out, "value_review.csv"))
_multi = dict(RB.REVIEW_MODES)
try:
    # A type this run does not produce - the panels here carry both an
    # overlay and a project, so requiring the project proves nothing.
    RB.REVIEW_MODES["OVERLAY"] = ("OVERLAY", "CALIBRATION_PANEL")
    _r = FIN.finalize(_multi_out, review_path=_multi_rv,
                      run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6))
    check("a second required artifact that is absent refuses the approval",
          _r["status"] != "FINALIZED"
          and any(p["check"] == "REVIEW_ARTIFACT_MISSING"
                  for p in _r["problems"]),
          "%s %r" % (_r["status"], _r.get("problems")))
    check("and the refusal names the one that is missing",
          any("CALIBRATION_PANEL" in p["detail"] for p in _r["problems"]
              if p["check"] == "REVIEW_ARTIFACT_MISSING"),
          repr(_r["problems"]))
finally:
    RB.REVIEW_MODES.clear()
    RB.REVIEW_MODES.update(_multi)

_clean_out, _ = fresh_run("run_commit_ok")
_q = pd.read_csv(os.path.join(_clean_out, "review_queue.csv"), dtype=object)
_rv = review([dict(Review_ID="R001", Panel_ID="P1",
                   Review_Subject_SHA256=_q.loc[0, "Review_Subject_SHA256"],
                   Reviewer_ID="RV_H", Decision="APPROVED",
                   Marks_Checked="CONFIRMED",
                   Reviewed_At="2026-08-06T10:00:00Z", Note="")],
             os.path.join(_clean_out, "value_review.csv"))
_ok2 = FIN.finalize(_clean_out, review_path=_rv, run_date="2026-08-06",
                    today=datetime.date(2026, 8, 6))
_fs = json.load(open(os.path.join(_clean_out, "finalize_stamp.json")))
check("a clean finalization commits and records what it committed",
      _ok2["status"] == "FINALIZED" and len(_fs["Accepted_SHA256"]) == 64
      and len(_fs["Run_Stamp_SHA256"]) == 64, "%s" % _fs)
check("and the recorded hash is the file that landed",
      RB.file_sha256(os.path.join(_clean_out, FIN.FINALIZE_MARKER))
      == _fs["Accepted_SHA256"])
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
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % len(RAN))
print("%d scenarios run" % len(RAN))
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
