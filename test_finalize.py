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


def _verified(run_dir, manifest_dir=None):
    """The bundle `finalize` hands its contract checks: manifests plus outputs.

    `verify_run_outputs` keeps the rows of each output it hashed under
    `outputs`, so the checks that re-derive a declaration read the bytes that
    were verified rather than opening the path again. A caller that reaches
    `method_contract_failures` directly has to build the same bundle.
    """
    frames = RB.load_manifests(manifest_dir
                               or os.path.join(run_dir, "manifests"))
    path = os.path.join(run_dir, "run_manifest.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            frames["outputs"] = {"run_manifest.csv": list(csv.DictReader(fh))}
    return frames


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


# A PANEL DECLARED AS THE READER THAT RECONSTRUCTS VALUES.
#
# Every tier scenario below needs a value method only `LINE_MONO_STYLE` produces
# - a fit fallback, a bracketed interpolation, a style named by elimination - and
# from v7.68 the finalizer refuses a pair its panel's reader could not have
# reached. The first version of these scenarios declared the panel `LINE_COLOR`
# and had it claim `MEASURED_LINE_STYLE`, which is exactly the lie that gate
# exists to catch, so the fixture now says what it is doing: the raster is the
# colour fixture, the panel is declared for the style reader, and the wrapper
# below stands in for that reader by reading the marks off the colours.
STYLE_PANELS = [dict(PANELS[0], Mark_Type="LINE_MONO_STYLE")]
STYLE_SERIES = [dict(s, Line_Style=style, Colour_Hex="", Marker_Shape="",
                     Marker_Fill="")
                for s, style in zip(SERIES, ("SOLID", "DASHED"))]
_COLOUR_SPECS = [MR.SeriesSpec("S_B", rgb=(45, 80, 220), marker="CIRCLE"),
                 MR.SeriesSpec("S_R", rgb=(215, 45, 45), marker="CIRCLE")]


def style_reader(assign):
    """A stand-in for `LINE_MONO_STYLE`, reading this fixture's coloured marks.

    `assign(index, row)` writes the two provenance fields. The marks themselves
    are real - found in the raster, calibrated, carried through
    `to_value_records` and the grid gate like any other reader's - so the methods
    arrive by the path a taught reader's would rather than by editing a CSV,
    which `RUN_ARTIFACT_MODIFIED` refuses anyway.
    """
    def wrapped(mark_type, **kw):
        rows = MR.read_line_marker_panel(
            image=kw["image"], panel_box=kw["panel_box"],
            x_positions=kw["x_positions"], y_calibration=kw["y_calibration"],
            series=_COLOUR_SPECS)
        for i, row in enumerate(rows):
            row.pop("Identity_Method", None)
            row.pop("Value_Method", None)
            assign(i, row)
            _style_evidence(row)
        return rows
    return wrapped


def _style_evidence(row):
    """Give the stand-in's mark the measurements its method claims to rest on.

    v7.72 re-derives a LINE_MONO_STYLE row's methods from its own evidence, so a
    fixture that names a method and records no supports is a reader claiming an
    interpolation it cannot show - which is what the new check exists to refuse.
    Setting the evidence here keeps every scenario below saying one thing rather
    than two, and keeps the honesty in one place.
    """
    method = row.get("Value_Method")
    row["line_style_source"] = (
        "MEASURED" if row.get("Identity_Method") == "MEASURED_LINE_STYLE"
        else row.get("Identity_Method"))
    x = float(row["x"])
    for key in ("Value_Support_Left_Px", "Value_Support_Right_Px",
                "Value_Span_Px", "Occlusion_Cause", "Occlusion_Width_Px",
                "Local_Stroke_Px", "Expected_Dash_Gap_Px"):
        row.pop(key, None)
    # WRITTEN THE WAY `_ink_at` WRITES IT, which is the only thing that makes
    # these scenarios evidence about the real reader. It reports the single
    # supporting column in BOTH fields with the span measuring how far the value
    # was carried, and it always records a span and a cause - `value_span or 0`,
    # `occlusion_cause or NONE`. A fixture that omitted them was a foreign
    # producer, and from v7.76 it is refused as one.
    row["Errorbar_Stem_Confirmed"] = row.get("Errorbar_Stem_Confirmed", "TRUE")
    if method == "FIT_FALLBACK":
        return                                   # no ink either side, and it says so
    if method == "EXTRAPOLATED_CURVE_INK":
        row["Value_Support_Left_Px"] = row["Value_Support_Right_Px"] = x - 3
        row["Value_Span_Px"] = 3
        row["Occlusion_Cause"] = "NONE"
        return
    if method == "DIRECT_CURVE_INK":
        row["Value_Support_Left_Px"] = row["Value_Support_Right_Px"] = x
        row["Value_Span_Px"] = 0
        row["Occlusion_Cause"] = "NONE"
        return
    row.update(Value_Support_Left_Px=x - 2, Value_Support_Right_Px=x + 2,
               Value_Span_Px=4, Occlusion_Width_Px=3, Local_Stroke_Px=6,
               Expected_Dash_Gap_Px=0,
               Occlusion_Cause={"LOCAL_BRACKETED_INTERPOLATION": "MIXED",
                                "RESTORED_MASKED_FURNITURE": "ERRORBAR_STEM",
                                "RESTORED_LINE_PATTERN_GAP": "NONE"}
               .get(method, "MIXED"))
    if method == "NONLOCAL_INTERPOLATION":
        # THE SUPPORTS MOVE WITH THE SPAN. From v7.79 the verifier checks that
        # the two columns bracket the value and that the span is the gap between
        # them, so a fixture that widened the span alone described a mark no
        # reader can produce.
        row.update(Value_Support_Left_Px=x - 20, Value_Support_Right_Px=x + 20,
                   Value_Span_Px=40, Local_Stroke_Px=2)


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
def _with_methods(i, r):
    r["Identity_Method"] = "MEASURED_LINE_STYLE"
    r["Value_Method"] = "FIT_FALLBACK" if i == 0 else "DIRECT_CURVE_INK"


_real_read_panel = MR.read_panel
_STYLE = dict(panel_manifest=STYLE_PANELS, series_manifest=STYLE_SERIES)
try:
    MR.read_panel = style_reader(_with_methods)
    _R4_DIR, _ = fresh_run("run_tier", **_STYLE)
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
def _all_extrapolated(_i, r):
    r["Identity_Method"] = "MEASURED_LINE_STYLE"
    r["Value_Method"] = "EXTRAPOLATED_CURVE_INK"


try:
    MR.read_panel = style_reader(_all_extrapolated)
    _ALL_DIR, _ = fresh_run("run_tier_all", **_STYLE)
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
print("the weight is evidence too, and the gate prices it")
# v7.70. A cell whose mean came straight off the ink and whose error bar was read
# from a cap no stem connects to it was R0 on both of the axes that existed. The
# third axis is the one that decides the weight in a continuous meta-analysis.
# The panel is LINE_COLOR here, not the style reader: an unstemmed cap is
# something a marker reader can actually meet, and the dispersion contract in
# v7.68's shape refuses a claim its reader could not have reached.
def _unstemmed(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r["Dispersion_Method"] = "UNSTEMMED_CAP"
    return rows


try:
    MR.read_panel = _unstemmed
    _DISP_DIR, _ = fresh_run("run_dispersion")
finally:
    MR.read_panel = _real_read_panel
_qd = pd.read_csv(os.path.join(_DISP_DIR, "figure_values_machine_qc.csv"),
                  dtype=object).fillna("")
check("a row measured on both mean axes can still be R3 on the third",
      len(_qd) > 0
      and {PROV.review_tier(r["Identity_Method"], r["Value_Method"])
           for _, r in _qd.iterrows()} == {"R0"}
      and {PROV.row_tier(r) for _, r in _qd.iterrows()} == {"R3"},
      "%s" % sorted({PROV.row_tier(r) for _, r in _qd.iterrows()}))
_fpd = pd.read_csv(os.path.join(_DISP_DIR, "review_queue.csv"),
                   dtype=object).fillna("")
check("  so its panel is asked about the inference, off the same derivation",
      int(_fpd.loc[0, "Inference_Cells"]) == len(_qd),
      "%r" % _fpd.loc[0, "Inference_Cells"])
_rd = FIN.finalize(_DISP_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fpd.loc[0, "Review_Subject_SHA256"],
         Inference_Checked="CONFIRMED")],
    path=os.path.join(_DISP_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("  and the cell-level contract asks about each one by name",
      _rd["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "INFERENCE_CONFIRMATION_MISSING"
              for p in _rd["problems"]), "%s" % _rd)
# A SPREAD A MODEL PRODUCED is R4 and unfinalizable - and no reader may claim it
# yet, which is the honest state rather than an end-to-end scenario over a
# producer this package does not have. The registry prices what a future reader
# will be able to say; the contract is what stops today's readers saying it.
check("a weight a model produced is priced R4 and no reader may claim it",
      PROV.dispersion_tier("FITTED_DISPERSION") == "R4"
      and all(PROV.dispersion_contract_failure(mark, "FITTED_DISPERSION")
              for mark in PROV.DISPERSION_CONTRACT),
      "%s" % [m for m in PROV.DISPERSION_CONTRACT
              if not PROV.dispersion_contract_failure(m, "FITTED_DISPERSION")])
# AND A SPREAD WITH NO ACCOUNT OF ITSELF IS REFUSED AT THE GATE, which is the
# reachable R4 on this axis: a reader that answers the two questions about the
# mean and says nothing about the error bar it also emitted. Priced on the mean
# alone this row is R0 and pools.
def _mute_dispersion(*a, **kw):
    rows = _real_read_panel(*a, **kw)
    for r in rows:
        r.pop("Dispersion_Method", None)
    return rows


try:
    MR.read_panel = _mute_dispersion
    _MUTE_DIR, _ = fresh_run("run_mute_dispersion")
finally:
    MR.read_panel = _real_read_panel
_qm = pd.read_csv(os.path.join(_MUTE_DIR, "figure_values_machine_qc.csv"),
                  dtype=object).fillna("")
_rm = FIN.finalize(_MUTE_DIR, review_path=review(
    [row(Review_Subject_SHA256=pd.read_csv(
        os.path.join(_MUTE_DIR, "review_queue.csv"),
        dtype=object).fillna("").loc[0, "Review_Subject_SHA256"])],
    path=os.path.join(_MUTE_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("a row that says nothing about the spread it emitted is refused",
      _rm["status"] == "NOTHING_FINALIZABLE" and _rm["accepted"] == 0
      and all(str(r["Dispersion_Value"]).strip() for _, r in _qm.iterrows()),
      "%s" % _rm)
_blocked_mute = pd.read_csv(os.path.join(_MUTE_DIR, "method_blocked_cells.csv"),
                            dtype=object).fillna("")
check("  and the work list says WHICH axis refused it, not just that one did",
      "Dispersion_Method" in _blocked_mute.columns
      and len(_blocked_mute) == len(_qm)
      and all("SPREAD" in r["Detail"] for _, r in _blocked_mute.iterrows()),
      "%s" % _blocked_mute.head(1).to_dict("records"))
check("  which the two axes about the mean would have called R0 and pooled",
      {PROV.review_tier(r["Identity_Method"], r["Value_Method"])
       for _, r in _qm.iterrows()} == {"R0"}
      and {PROV.row_tier(r) for _, r in _qm.iterrows()} == {"R4"},
      "%s" % sorted({PROV.row_tier(r) for _, r in _qm.iterrows()}))
check("  and were one to arrive, the row would be refused and put on the list",
      PROV.row_tier(dict(Identity_Method="MEASURED_LINE_STYLE",
                         Value_Method="DIRECT_CURVE_INK",
                         Dispersion_Value="1.0",
                         Dispersion_Method="FITTED_DISPERSION"))
      not in PROV.FINALIZABLE_TIERS)

def _blank_route_refused():
    """The geometry writer refuses a row that names a fill and no route."""
    import mono_bar_geometry as MONO
    record = dict(figure="P1", group="G", slot=0, value=1.0,
                  panel_box=(0, 10, 0, 10), resolved_fill_pattern="OPEN",
                  identity_status="RESOLVED", identity_source="AUTO",
                  domain_identity_sha256="d" * 64)
    record["geometry_row_sha256"] = MONO.geometry_row_sha256(record)
    record["auto_identity_sha256"] = MONO.auto_identity_sha256(record)
    try:
        MONO.artifact_row(record)
    except ValueError as exc:
        return "AUTO_IDENTITY_ROUTE_MISSING" in str(exc)
    return False


print()
print("a method is a claim about evidence, and the evidence has a vote")
# v7.68. Blank and unregistered methods are refused, so the remaining way to buy
# a cheap tier is to write down a REGISTERED method that is not the one the
# evidence supports - and every file hash in the run is then correct, because
# whoever produced the values wrote them that way from the start.
_liar = style_reader(lambda i, r: r.update(
    Identity_Method="MEASURED_COLOUR", Value_Method="MARKER_CENTER"))
try:
    MR.read_panel = _liar
    _LIE_DIR, _ = fresh_run("run_wrong_reader", **_STYLE)
finally:
    MR.read_panel = _real_read_panel
_fpl = pd.read_csv(os.path.join(_LIE_DIR, "review_queue.csv"),
                   dtype=object).fillna("").loc[0, "Review_Subject_SHA256"]
_rl = FIN.finalize(_LIE_DIR, review_path=review(
    [row(Review_Subject_SHA256=_fpl)],
    path=os.path.join(_LIE_DIR, "value_review.csv")),
    run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("a pair the panel's reader could not have produced is refused",
      _rl["status"] == "NOTHING_APPROVED"
      and any(p["check"] == "METHOD_NOT_POSSIBLE_FOR_READER"
              for p in _rl["problems"]), "%s" % _rl)
check("  and the refusal names what that reader does produce",
      any("LINE_MONO_STYLE" in p["detail"] and "MEASURED_COLOUR" in p["detail"]
          for p in _rl["problems"]
          if p["check"] == "METHOD_NOT_POSSIBLE_FOR_READER"),
      "%s" % [p["detail"] for p in _rl["problems"]][:1])
# The matrix is over PAIRS, not over two independent lists: a value method one
# reader produces beside an identity method another one does is still impossible.
check("the contract answers per mark type, and says nothing about readers it "
      "has not heard of",
      not PROV.contract_failure("LINE_MONO_STYLE", "MEASURED_LINE_STYLE",
                                "FIT_FALLBACK")
      and PROV.contract_failure("BOX_VIOLIN", "MEASURED_LINE_STYLE",
                                "DIRECT_CURVE_INK")
      and PROV.contract_failure("LINE_COLOR", "HUMAN_RESOLUTION",
                                "MARKER_CENTER")
      and not PROV.contract_failure("A_READER_FROM_2027", "ANYTHING", "AT_ALL"),
      PROV.contract_failure("BOX_VIOLIN", "MEASURED_LINE_STYLE",
                            "DIRECT_CURVE_INK"))
# HUMAN_RESOLUTION IS R0 BECAUSE A PERSON SIGNED FOR IT. A row claiming it
# without an `Identity_Source=HUMAN` and a `Resolution_ID` is claiming the
# strongest evidence the ladder has and citing none of it.
_pl = []
_held_h = FIN.method_contract_failures(
    pd.DataFrame([dict(Run_Panel_ID="P1", Unit_ID="U1", Cell_Key="c",
                       Identity_Method="HUMAN_RESOLUTION",
                       Value_Method="BAR_OUTLINE_CENTER",
                       Identity_Source="AUTO", Resolution_ID="")]),
    pd.DataFrame([dict(Panel_ID="P1", Mark_Type="BAR_MONO")]),
    pd.DataFrame(columns=["Panel_ID", "Artifact_Type", "Artifact_Path"]),
    OUT, lambda w, c, d: _pl.append(c), frames=_verified(OUT))
# BLANK EVIDENCE IS NOT CONSENT. v7.71. Both cross-checks compared non-blank
# answers only, so an artifact that said NOTHING about how its series was named
# bought whatever the value row claimed - the fail-open these functions exist to
# close, arrived at from the other side.
_pt_dir = os.path.join(ROOT, "point_blank")
os.makedirs(_pt_dir, exist_ok=True)


def _cloud(path, record_method, point_methods):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": MR.POINT_DATA_SCHEMA,
                   "Identity_Method": record_method,
                   "points": [{"Identity_Method": m} for m in point_methods]},
                  fh)
    return path


def _point_check(record_method, point_methods, claimed="MEASURED_COLOUR"):
    path = _cloud(os.path.join(_pt_dir, "cloud.json"), record_method,
                  point_methods)
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame([dict(Run_Panel_ID="P1", Unit_ID="U1", Cell_Key="c",
                           Identity_Method=claimed,
                           Value_Method="POINT_CLOUD_ASSOCIATION",
                           Point_Data_Reference=path)]),
        pd.DataFrame([dict(Panel_ID="P1", Mark_Type="SCATTER")]),
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="POINT_DATA",
                           Artifact_Path=path)]),
        _pt_dir, lambda w, c, d: seen.append(c),
        frames=_verified(OUT))
    return held, seen


_held_p, _seen_p = _point_check("", ["MEASURED_COLOUR",
                                     "DECLARED_SINGLE_SERIES"])
check("a point cloud that cannot agree with itself supports no claim at all",
      _held_p == {"P1"} and "METHOD_EVIDENCE_UNRESOLVED" in _seen_p, "%s" % _seen_p)
_held_p, _seen_p = _point_check("", ["MEASURED_COLOUR", "MEASURED_COLOUR"])
check("  and a record-level blank over points that DO agree is a contradiction",
      _held_p == {"P1"} and "METHOD_CONTRADICTS_POINTS" in _seen_p, "%s" % _seen_p)
_held_p, _seen_p = _point_check("MEASURED_COLOUR",
                                ["MEASURED_COLOUR", "DECLARED_SINGLE_SERIES"])
check("  and one point disagreeing is enough, whatever the record says",
      _held_p == {"P1"} and "METHOD_EVIDENCE_UNRESOLVED" in _seen_p, "%s" % _seen_p)
_held_p, _seen_p = _point_check("MEASURED_COLOUR", ["MEASURED_COLOUR"] * 3)
check("  while a cloud that agrees with itself and with the row is accepted",
      not _held_p and not _seen_p, "%s" % _seen_p)
# THE SAME FROM THE GEOMETRY SIDE.
_geo_seen = []
_held_g = FIN._geometry_route_failures(
    pd.DataFrame([dict(Run_Panel_ID="P1", Unit_ID="U1", Cell_Key="c",
                       Identity_Method="MEASURED_FILL_RELATION",
                       Geometry_Row_SHA256="a" * 64)]),
    pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="MONO_BAR_GEOMETRY",
                       Artifact_Path=_cloud.__name__)]),
    _pt_dir, lambda w, c, d: _geo_seen.append(c))
check("a geometry file that cannot be read refuses the route it cannot confirm",
      "METHOD_NOT_POSSIBLE_FOR_READER" in _geo_seen or not _held_g,
      "%s" % _geo_seen)
# A FOREIGN GEOMETRY FILE THAT NAMES A PATTERN AND NO ROUTE. The writer refuses to
# produce one from v7.71, so this is the shape a run made by something else
# arrives in - and it is exactly where reading a blank as consent would let a
# value claim R0 for a bar whose route nothing recorded.
_geo_csv = os.path.join(_pt_dir, "mono_bar_geometry.csv")
with open(_geo_csv, "w", newline="", encoding="utf-8") as _fh:
    _w = csv.writer(_fh)
    _w.writerow(["Geometry_Row_SHA256", "Auto_Fill_Pattern",
                 "Auto_Identity_Method"])
    _w.writerow(["b" * 64, "OPEN", ""])


def _geometry_claim(claimed, said=""):
    with open(_geo_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Geometry_Row_SHA256", "Auto_Fill_Pattern",
                    "Auto_Identity_Method"])
        w.writerow(["b" * 64, "OPEN", said])
    seen = []
    held = FIN._geometry_route_failures(
        pd.DataFrame([dict(Run_Panel_ID="P1", Unit_ID="U1", Cell_Key="c",
                           Identity_Method=claimed,
                           Geometry_Row_SHA256="b" * 64)]),
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="MONO_BAR_GEOMETRY",
                           Artifact_Path=_geo_csv)]),
        _pt_dir, lambda w_, c, d: seen.append(c))
    return held, seen


_held_g, _geo_seen = _geometry_claim("MEASURED_FILL_RELATION", said="")
check("a geometry row that names a pattern and no route supports no claim",
      _held_g == {"P1"} and "METHOD_CONTRADICTS_GEOMETRY" in _geo_seen,
      "%s" % _geo_seen)
_held_g, _geo_seen = _geometry_claim("MEASURED_FILL_RELATION",
                                     said="FIGURE_PROTOTYPE_MATCH")
check("  and one that names a different route is the same refusal",
      _held_g == {"P1"} and "METHOD_CONTRADICTS_GEOMETRY" in _geo_seen,
      "%s" % _geo_seen)
_held_g, _geo_seen = _geometry_claim("MEASURED_FILL_RELATION",
                                     said="MEASURED_FILL_RELATION")
check("  while agreement is agreement",
      not _held_g and not _geo_seen, "%s" % _geo_seen)
check("and a named bar with no route is refused where the file is written",
      _blank_route_refused(), "the writer accepted a resolved row with no route")

check("a human resolution that cites no resolution is not a human resolution",
      _held_h == {"P1"} and "METHOD_NOT_POSSIBLE_FOR_READER" in _pl, "%s" % _pl)
_pl = []
_ok_h = FIN.method_contract_failures(
    pd.DataFrame([dict(Run_Panel_ID="P1", Unit_ID="U1", Cell_Key="c",
                       Identity_Method="HUMAN_RESOLUTION",
                       Value_Method="BAR_OUTLINE_CENTER",
                       Identity_Source="HUMAN", Resolution_ID="IR1")]),
    pd.DataFrame([dict(Panel_ID="P1", Mark_Type="BAR_MONO")]),
    pd.DataFrame(columns=["Panel_ID", "Artifact_Type", "Artifact_Path"]),
    OUT, lambda w, c, d: _pl.append(c), frames=_verified(OUT))
check("  while one that does is left to the resolution contract to check",
      not _ok_h and not _pl, "%s" % _pl)

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
def _inferred_identity(_i, r):
    r["Identity_Method"] = "COMPLEMENT_OF_DECLARED_STYLES"
    r["Value_Method"] = "DIRECT_CURVE_INK"


try:
    MR.read_panel = style_reader(_inferred_identity)
    _R2_DIR, _ = fresh_run("run_inferred", **_STYLE)
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
def _reconstructed(i, r):
    r["Identity_Method"] = "MEASURED_LINE_STYLE"
    r["Value_Method"] = ("LOCAL_BRACKETED_INTERPOLATION" if i < 2
                         else "DIRECT_CURVE_INK")
    # A READER THAT RECONSTRUCTS A NUMBER SAYS BETWEEN WHICH COLUMNS, and from
    # v7.72 the finalizer re-derives the method from those columns - so the
    # evidence is written by `_style_evidence` for every method this stand-in
    # names, in one place, rather than by each scenario for its own.
    r["Trace_Agreement"] = "AGREED"


try:
    MR.read_panel = style_reader(_reconstructed)
    _R3_DIR, _r3_summary = fresh_run("run_cells", **_STYLE)
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
# AND THE SPREAD IS IN THE RECIPE TOO. v7.71. `row_tier` has priced the
# dispersion since v7.70 and this identifier did not, so a cell asked about at
# this grain because of its ERROR BAR kept the same id when the answer to that
# question changed - the stale-confirmation problem the support columns were added
# to close, on the axis added after them.
check("  including the spread, since a cell can be asked about for that alone",
      "Dispersion_Method" in RB.INFERENCE_IDENTITY_FIELDS
      and RB.inference_id(dict(_evidence, Dispersion_Method="UNSTEMMED_CAP"),
                          panel_id="P1")
      != RB.inference_id(dict(_evidence,
                              Dispersion_Method="RESTORED_MASKED_CAP"),
                         panel_id="P1")
      and RB.inference_id(dict(_evidence, Errorbar_Upper="9"), panel_id="P1")
      != RB.inference_id(dict(_evidence, Errorbar_Upper="9.5"),
                         panel_id="P1"),
      "%s" % [c for c in ("Dispersion_Method", "Errorbar_Lower",
                          "Errorbar_Upper", "Errorbar_Stem_Confirmed")
              if c not in RB.INFERENCE_IDENTITY_FIELDS])
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
# A CELL NOBODY CAN SEE IS A CELL NOBODY CAN CONFIRM. The picture can go missing
# for a reason that is nobody's fault - a crop that could not be painted, which
# `draw_inference_context` reports rather than raising, exactly as every other
# picture in this package does. (A reader that claims a bracketed interpolation
# and records no supports is refused earlier and harder, by the evidence check
# below: it is not a missing picture, it is a missing measurement.)
def _no_supports(i, r):
    r["Identity_Method"] = "MEASURED_LINE_STYLE"
    r["Value_Method"] = ("LOCAL_BRACKETED_INTERPOLATION" if i < 1
                         else "DIRECT_CURVE_INK")


_real_context = RB.OVERLAY.draw_inference_context
try:
    MR.read_panel = style_reader(_no_supports)
    RB.OVERLAY.draw_inference_context = lambda *a, **kw: None
    _NOCTX_DIR, _ = fresh_run("run_nocontext", **_STYLE)
finally:
    MR.read_panel = _real_read_panel
    RB.OVERLAY.draw_inference_context = _real_context
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
check("a reconstruction whose picture could not be painted has none registered",
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
print("a number JSON cannot express never reaches an artifact")
# v7.84. Python writes a bare `NaN`, which is not JSON, and every
# `abs(a - b) > EPSILON` comparison downstream is False against it - so a
# geometry that cannot be checked reads as one that agrees. The writer refuses,
# and the panel is refused with a reason rather than finalized from an artifact
# nothing can check.
def _nan_mean(i, r):
    r["Identity_Method"] = "MEASURED_LINE_STYLE"
    r["Value_Method"] = "DIRECT_CURVE_INK"
    if i == 0:
        r["mean"] = float("nan")


_NAN_DIR = os.path.join(ROOT, "run_nan")
_nan_raised = None
try:
    MR.read_panel = style_reader(_nan_mean)
    fresh_run("run_nan", **_STYLE)
except Exception as exc:
    _nan_raised = exc
finally:
    MR.read_panel = _real_read_panel
check("a reader that computes a NaN stops the batch, naming the panel",
      isinstance(_nan_raised, RB.InternalReaderError)
      and "P1" in "%s" % _nan_raised, "%r" % _nan_raised)
check("  and no artifact nothing can check is left behind",
      not os.path.exists(os.path.join(_NAN_DIR, "raw", "P1_marks.json")),
      "%s" % (sorted(os.listdir(os.path.join(_NAN_DIR, "raw")))
              if os.path.isdir(os.path.join(_NAN_DIR, "raw")) else "no raw"))
check("  and the stamp says INTERNAL_ERROR, not a figure problem",
      json.load(open(os.path.join(_NAN_DIR, "run_stamp.json"),
                     encoding="utf-8")).get("Status") == "INTERNAL_ERROR",
      "%s" % json.load(open(os.path.join(_NAN_DIR, "run_stamp.json"),
                            encoding="utf-8")).get("Status"))



# A REAL BAR_COLOR RUN, end to end. Everything above reads the line fixture; the
# BAR_COLOR verifier is asked for by `Mark_Type`, so without a bar panel in a
# real run the finalizer's side of it - the join, the envelope, the calibration
# it hands the verifier - is exercised by nothing.
_BAR_TRUTH = json.load(open(os.path.join(HERE, "bar_fixture_truth.json"),
                            encoding="utf-8"))
# Copied into the run root, because a panel's `Image_Path` is resolved against
# `file_root` and the manifest validator refuses one that is not on disk.
_BAR_IMG = os.path.join(ROOT, "bar_fixture.png")
shutil.copy(os.path.join(HERE, "bar_fixture.png"), _BAR_IMG)
_BAR_SHA = RB.file_sha256(_BAR_IMG)
_BAR_TICKS = ";".join("%s:%s" % (v, px) for v, px in _BAR_TRUTH["ticks"])
_BAR_SESSIONS = sorted({b["session"] for b in _BAR_TRUTH["bars"]},
                       key=lambda s: min(b["x_pixel"] for b in _BAR_TRUTH["bars"]
                                         if b["session"] == s))
_BAR_ANCHORS = {s: sum(b["x_pixel"] for b in _BAR_TRUTH["bars"]
                       if b["session"] == s)
                / len([b for b in _BAR_TRUTH["bars"] if b["session"] == s])
                for s in _BAR_SESSIONS}


def bar_manifests():
    """The bar fixture declared as a panel: box, ticks, colours and anchors."""
    x0, x1, y0, y1 = _BAR_TRUTH["panel_box"]
    return dict(
        source_figure_manifest=[dict(SOURCE_FIGURES[0], Source_Image=_BAR_IMG,
                                     Source_Image_SHA256=_BAR_SHA)],
        figure_manifest=[dict(FIGURES[0], Source_Image=_BAR_IMG,
                              Image_Resolution_Or_Hash="sha256:" + _BAR_SHA)],
        grid_definitions=([dict(Grid_ID="G", Factor_Name="ARM", Factor_Level=lv,
                     Level_Order=i, Note="")
                for i, lv in enumerate(("SUPINE", "ORTHOSTASIS"))]
               + [dict(Grid_ID="G", Factor_Name="TIMEPOINT", Factor_Level=s,
                       Level_Order=i, Note="")
                  for i, s in enumerate(_BAR_SESSIONS)]),
        unit_manifest=[dict(UNITS[0], Bar_Top_Definition="OUTLINE_CENTER")],
        panel_manifest=[dict(PANELS[0], Mark_Type="BAR_COLOR", Image_Path=_BAR_IMG,
                     Panel_X0=x0, Panel_X1=x1, Panel_Y0=y0, Panel_Y1=y1,
                     Axis_Y_Ticks=_BAR_TICKS, Baseline_Value="0")],
        series_manifest=[dict(Panel_ID="P1", Series_ID=sid, Colour_Hex="",
                              Colour_Tolerance="", Mask_Key=key,
                              Marker_Shape="", Marker_Fill="", Line_Style="",
                              Bar_Fill_Pattern="", Factor_Name="ARM",
                              Factor_Level=sid, Note="")
                         for sid, key in (("SUPINE", "blue"),
                                          ("ORTHOSTASIS", "red"))],
        position_manifest=[dict(Panel_ID="P1", Position_ID=s,
                                X_Pixel=_BAR_ANCHORS[s], Slot_Index=i,
                                Display_Order=i, Factor_Name="TIMEPOINT",
                                Factor_Level=s, Timepoint_Label=s,
                                Timepoint_Days=i, Note="")
                           for i, s in enumerate(_BAR_SESSIONS)])


_BAR_DIR, _bar_summary = fresh_run("run_bars", **bar_manifests())
_bar_qc = pd.read_csv(os.path.join(_BAR_DIR, "figure_values_machine_qc.csv"),
                      dtype=object).fillna("")
_bar_led = pd.read_csv(os.path.join(_BAR_DIR, "panel_artifacts.csv"),
                       dtype=object).fillna("")
_bar_queue = pd.read_csv(os.path.join(_BAR_DIR, "review_queue.csv"),
                         dtype=object).fillna("")
check("the bar fixture runs as a BAR_COLOR panel and produces values",
      _bar_summary["status"] == "RAN" and len(_bar_qc) == 12
      and set(_bar_qc["Identity_Method"]) == {"MEASURED_COLOUR"}
      and set(_bar_qc["Value_Method"]) == {"BAR_OUTLINE_CENTER"},
      "%s / %d values" % (_bar_summary, len(_bar_qc)))


def _bar_join(rows=None, flag_all=False):
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame(rows if rows is not None else _bar_qc.to_dict("records")),
        _bar_queue.rename(columns={"Panel_ID": "Panel_ID"}), _bar_led, _BAR_DIR,
        lambda w, c, d: seen.append(c), frames=_verified(_BAR_DIR))
    return held, seen


check("and every one of them passes the join, verifier included",
      _bar_join() == (set(), []), "%s" % (_bar_join(),))
# THE VERIFIER IS ASKED, AND IT IS ASKED WITH THE RUN'S OWN CALIBRATION. Both
# halves matter: a verifier nobody calls is decoration, and one handed no axis
# cannot re-compute what a pixel row should have read.
_bar_rows = _bar_qc.to_dict("records")
check("a bar value whose mark disagrees with it about the spread is refused",
      "METHOD_CONTRADICTS_MARK" in _bar_join(
          [dict(_bar_rows[0], Dispersion_Method="NO_DISPERSION")])[1],
      "%s" % (_bar_join([dict(_bar_rows[0],
                              Dispersion_Method="NO_DISPERSION")])[1],))
_bar_env_path = RB.resolve_artifact(
    _BAR_DIR, _bar_led[_bar_led["Artifact_Type"] == "RAW_MARKS"]
    .iloc[0]["Artifact_Path"])
_bar_env = json.load(open(_bar_env_path, encoding="utf-8"))
check("  and the mark it was checked against carries the pixel rows the numbers "
      "came from",
      all(FIN._s(m.get("top_px")) and FIN._s(m.get("fill_top_px"))
          and FIN._s(m.get("cap_px")) for m in _bar_env["marks"]),
      "%s" % _bar_env["marks"][0])
# THE ARITHMETIC, THROUGH THE FINALIZER. A mark whose pixel row no longer
# produces its number is refused - which is only possible because the finalizer
# hands the verifier the calibration it re-derived from the verified manifests.
_bar_edit = os.path.join(ROOT, "bar_marks_edited")


def _bar_edited(mutate):
    shutil.rmtree(_bar_edit, ignore_errors=True)
    os.makedirs(_bar_edit)
    shutil.copy(os.path.join(_BAR_DIR, "run_manifest.csv"), _bar_edit)
    body = json.loads(json.dumps(_bar_env))
    was = FIN._s(body["marks"][0]["Mark_Record_SHA256"])
    mutate(body["marks"][0])
    header = {k: v for k, v in body.items() if k != "marks"}
    body["marks"] = RB.stamp_marks(
        [{k: v for k, v in m.items()
          if k not in ("Mark_Record_SHA256", "Method_Attestation_SHA256")}
         for m in body["marks"]], header)
    path = os.path.join(_bar_edit, "P1_marks.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=1, sort_keys=True)
    now = body["marks"][0]
    rows = [dict(r, Mark_Record_SHA256=now["Mark_Record_SHA256"],
                 Method_Attestation_SHA256=now["Method_Attestation_SHA256"])
            if FIN._s(r.get("Mark_Record_SHA256")) == was else dict(r)
            for r in _bar_rows]
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame(rows), _bar_queue,
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="RAW_MARKS",
                           Artifact_Path=path)]),
        _bar_edit, lambda w, c, d: seen.append(c),
        frames=_verified(_bar_edit, os.path.join(_BAR_DIR, "manifests")))
    return held, seen


_held_b, _seen_b = _bar_edited(lambda m: m.update(top_px=float(m["top_px"]) + 6))
check("a bar whose top row no longer produces its mean is refused by the "
      "calibration this run declared",
      _held_b == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_b,
      "%s" % _seen_b)
_held_b, _seen_b = _bar_edited(lambda m: m.update(cap_px=float(m["cap_px"]) - 9))
check("  and so is one whose cap is not the distance its dispersion claims",
      _held_b == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_b,
      "%s" % _seen_b)
# AND WHEN THE MARK AND THE VALUE AGREE ON A METHOD THE INK DOES NOT SUPPORT,
# the verifier is the only thing left that can say so - the join compares them to
# each other and finds nothing. A stem this reader did not confirm beside a cap
# it measured anyway is the shape `bar_reader` cannot produce, and the artifact
# says both.
# TWO BARS EXCHANGING THEIR LABELS. v7.86. `DECLARED_ANCHOR` said the reader
# used declared anchors, not that THIS mark is at the one it names - so a
# producer could swap two marks' x_labels, recompute their cells and every hash,
# and pass: the numbers still match their marks, the cells still match the
# labels, and nothing compared a mark's own x column to the anchors.
def _bar_swapped_labels():
    shutil.rmtree(_bar_edit, ignore_errors=True)
    os.makedirs(_bar_edit)
    shutil.copy(os.path.join(_BAR_DIR, "run_manifest.csv"), _bar_edit)
    body = json.loads(json.dumps(_bar_env))
    first = body["marks"][0]
    partner = next(m for m in body["marks"][1:]
                   if m["series"] == first["series"]
                   and m["x_label"] != first["x_label"])
    was = {m["Mark_Record_SHA256"]: m["x_label"] for m in (first, partner)}
    first["x_label"], partner["x_label"] = partner["x_label"], first["x_label"]
    header = {k: v for k, v in body.items() if k != "marks"}
    body["marks"] = RB.stamp_marks(
        [{k: v for k, v in m.items()
          if k not in ("Mark_Record_SHA256", "Method_Attestation_SHA256")}
         for m in body["marks"]], header)
    path = os.path.join(_bar_edit, "P1_marks.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=1, sort_keys=True)
    # And the values follow them: new hashes, and the cell key the manifests
    # give the label each mark now claims.
    levels = {FIN._s(r.get("Position_ID")): FIN._s(r.get("Factor_Level"))
              for _, r in _verified(_BAR_DIR)["positions"].iterrows()}
    rows, marks = [], {m["Mark_Record_SHA256"]: m for m in body["marks"]}
    for old_hash, old_label in was.items():
        value = next(r for r in _bar_rows
                     if FIN._s(r.get("Mark_Record_SHA256")) == old_hash)
        mark = next(m for m in body["marks"]
                    if abs(float(m["x"]) - float(
                        next(mm for mm in _bar_env["marks"]
                             if mm["Mark_Record_SHA256"] == old_hash)["x"]))
                    < 1e-9)
        rows.append(dict(
            value, Mark_Record_SHA256=mark["Mark_Record_SHA256"],
            Method_Attestation_SHA256=mark["Method_Attestation_SHA256"],
            Cell_Key=GE.fig_cell_key({"ARM": mark["series"],
                                      "TIMEPOINT": levels[mark["x_label"]]})))
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame(rows), _bar_queue,
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="RAW_MARKS",
                           Artifact_Path=path)]),
        _bar_edit, lambda w, c, d: seen.append(c),
        frames=_verified(_bar_edit, os.path.join(_BAR_DIR, "manifests")))
    return held, seen, marks


_held_b, _seen_b, _ = _bar_swapped_labels()
check("two bars that exchange their x labels are refused, cells and hashes "
      "recomputed though they are",
      _held_b == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_b,
      "%s" % _seen_b)
_held_b, _seen_b = _bar_edited(
    lambda m: m.update(Errorbar_Stem_Confirmed="FALSE"))
check("a mark and a value agreeing on a spread the mark's own stem denies is "
      "refused by the verifier",
      _held_b == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_b,
      "%s" % _seen_b)

print()
print("a value is joined to the mark it was made from, and checked against it")
# v7.72. The matrix says which methods a reader CAN produce; this says which one
# THIS row's own evidence came to. Five of the seven readers had no durable
# artifact for that question at all - the raw marks and the values were joinable
# only by panel, so a value could carry any mark's number and any method the
# matrix allowed.
_marks_led = pd.read_csv(os.path.join(_R3_DIR, "panel_artifacts.csv"),
                         dtype=object).fillna("")
_marks_path = RB.resolve_artifact(
    _R3_DIR, _marks_led[_marks_led["Artifact_Type"] == "RAW_MARKS"]
    .iloc[0]["Artifact_Path"])
_envelope = json.load(open(_marks_path, encoding="utf-8"))
check("every mark carries a measurement hash and an attestation over its methods",
      _envelope["schema"].endswith("/3")
      and all(len(m["Mark_Record_SHA256"]) == 64
              and len(m["Method_Attestation_SHA256"]) == 64
              for m in _envelope["marks"]),
      "%s" % _envelope["schema"])
check("  and the value rows cite them, so the join is by content",
      set(_qc3["Mark_Record_SHA256"])
      == {m["Mark_Record_SHA256"] for m in _envelope["marks"]},
      "%d values, %d marks" % (len(_qc3), len(_envelope["marks"])))
# THE TWO HASHES ARE TWO CLAIMS. A method resolved or corrected later must not
# move the hash that answers "is this the same measurement" - the same separation
# `Geometry_Row_SHA256` and `Auto_Identity_SHA256` have had since v7.29.
_m0 = dict(_envelope["marks"][0])
_env0 = {k: v for k, v in _envelope.items() if k != "marks"}
check("the measurement hash ignores the methods, and the attestation does not",
      RB.mark_record_sha256(dict(_m0, Value_Method="FIT_FALLBACK"), _env0)
      == RB.mark_record_sha256(_m0, _env0)
      and RB.method_attestation_sha256(dict(_m0, Value_Method="FIT_FALLBACK"),
                                       _m0["Mark_Record_SHA256"])
      != RB.method_attestation_sha256(_m0, _m0["Mark_Record_SHA256"]),
      "%s" % _m0["Mark_Record_SHA256"][:16])
check("  and a mark measured differently is a different mark",
      RB.mark_record_sha256(dict(_m0, mean=float(_m0["mean"]) + 1.0), _env0)
      != RB.mark_record_sha256(_m0, _env0))
# AND A MARK READ UNDER A DIFFERENT INSTRUCTION IS A DIFFERENT MARK. v7.82. The
# digest sits INSIDE the record hash, not beside it: two artifacts of the same
# figure read under two declarations - a different baseline, a different
# threshold, a different series colour - would otherwise hash their marks
# identically, and a value could be joined to a mark from the other one.
check("  and so is one read under a different measurement declaration",
      RB.mark_record_sha256(
          _m0, dict(_env0, Measurement_Declaration_SHA256="e" * 64))
      != RB.mark_record_sha256(_m0, _env0)
      and len(_env0["Measurement_Declaration_SHA256"]) == 64,
      "%s" % _env0.get("Measurement_Declaration_SHA256"))


def _joined(rows):
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame(rows),
        pd.DataFrame([dict(Panel_ID="P1", Mark_Type="LINE_MONO_STYLE")]),
        _marks_led, _R3_DIR, lambda w, c, d: seen.append(c),
        frames=_verified(_R3_DIR))
    return held, seen


def _mark_detail(rows, code):
    """The detail the join reports for one code, so a message can be read back."""
    said = []
    FIN.method_contract_failures(
        pd.DataFrame(rows),
        pd.DataFrame([dict(Panel_ID="P1", Mark_Type="LINE_MONO_STYLE")]),
        _marks_led, _R3_DIR,
        lambda w, c, d: said.append(d) if c == code else None,
        frames=_verified(_R3_DIR))
    return " | ".join(said)


_rows3 = _qc3.to_dict("records")
_held_j, _seen_j = _joined(_rows3)
check("the run's own values pass the join they were stamped by",
      not _held_j and not _seen_j, "%s" % _seen_j)
_held_j, _seen_j = _joined([dict(_rows3[0], Mark_Record_SHA256="f" * 64)])
check("a value citing a mark no artifact carries has no evidence at all",
      _held_j == {"P1"} and "MARK_EVIDENCE_MISSING" in _seen_j, "%s" % _seen_j)
_held_j, _seen_j = _joined([dict(_rows3[0]),
                            dict(_rows3[1],
                                 Mark_Record_SHA256=_rows3[0]
                                 ["Mark_Record_SHA256"])])
check("and one printed mark cannot be the evidence for two values",
      _held_j == {"P1"} and "MARK_EVIDENCE_SHARED" in _seen_j, "%s" % _seen_j)
_held_j, _seen_j = _joined([dict(_rows3[0], Value_Method="DIRECT_CURVE_INK")])
check("a method swapped on the value disagrees with the mark it cites",
      _held_j == {"P1"} and "METHOD_CONTRADICTS_MARK" in _seen_j, "%s" % _seen_j)
_held_j, _seen_j = _joined([dict(_rows3[0],
                                 Method_Attestation_SHA256="0" * 64)])
check("  and an attestation that does not recompute is refused as well",
      _held_j == {"P1"} and "METHOD_ATTESTATION_STALE" in _seen_j, "%s" % _seen_j)
# AND THE METHODS ARE RE-DERIVED FROM THE MEASUREMENTS. The join above catches a
# value that lies about its mark; this catches a MARK that lies about itself, and
# it is the difference between "possible" and "true".
check("a mark whose own supports do not support its method is refused",
      "METHOD_CONTRADICTS_EVIDENCE" == PROV.evidence_failure(
          "LINE_MONO_STYLE",
          dict(line_style_source="MEASURED", Value_Support_Left_Px="",
               Value_Support_Right_Px="", Errorbar_Stem_Confirmed="TRUE"),
          dict(Identity_Method="MEASURED_LINE_STYLE",
               Value_Method="DIRECT_CURVE_INK",
               Dispersion_Method="DIRECT_CONNECTED_CAP"))[0],
      "no ink either side and DIRECT_CURVE_INK was accepted")
# ONE COLUMN, TWO MEANINGS, AND THE SPAN SAYS WHICH. `_ink_at` reports the single
# supporting column in BOTH fields when the ink is on one side only. Read as
# DIRECT, that turns an R4 carried sideways into an R0 - and it did, on 9 of
# publication 397's 87 line marks, until the derivation was run against the real
# figure rather than against fixtures that happened to agree with it.
_one_sided = dict(line_style_source="MEASURED", x="734",
                  Value_Support_Left_Px="727", Value_Support_Right_Px="727",
                  Value_Span_Px="7", Errorbar_Stem_Confirmed="TRUE")
check("one supporting column at a distance is a carry, not an observation",
      PROV.expected_line_style_methods(_one_sided).expected["Value_Method"]
      == "EXTRAPOLATED_CURVE_INK"
      and PROV.expected_line_style_methods(
          dict(_one_sided, x="727", Value_Span_Px="0")).expected["Value_Method"]
      == "DIRECT_CURVE_INK",
      "%s" % (PROV.expected_line_style_methods(_one_sided),))
check("  and the two are R4 and R0, which is why the difference matters",
      PROV.value_tier("EXTRAPOLATED_CURVE_INK") == "R4"
      and PROV.value_tier("DIRECT_CURVE_INK") == "R0")
check("  and a reader the registry cannot re-derive is left to the matrix",
      PROV.evidence_failure("BOX_VIOLIN", dict(anything=1),
                            dict(Value_Method="BOX_GEOMETRY")) == ("", ""))

print()
print("the join is to a cell and a number, not only to a method")
# v7.74. Everything above binds a value's METHODS to its mark. Two values read
# the SAME WAY in one panel could still exchange their marks and pass every one
# of those checks: both hashes existed, neither was shared, and the methods
# matched because they were identical. Nothing compared the numbers, and a
# `Cell_Key` swap has no arithmetic signature at all - which is the failure
# v7.29-v7.31 runs were withheld for on the BAR_MONO side and that the five join
# readers were still open to.
_same = [r for r in _rows3
         if FIN._s(r.get("Value_Method")) == "DIRECT_CURVE_INK"]
check("the fixture holds two values read the same way, which is what makes the "
      "swap invisible to the method checks",
      len(_same) >= 2
      and {(FIN._s(r["Identity_Method"]), FIN._s(r["Value_Method"]),
            FIN._s(r["Dispersion_Method"])) for r in _same[:2]} == {
          (FIN._s(_same[0]["Identity_Method"]),
           FIN._s(_same[0]["Value_Method"]),
           FIN._s(_same[0]["Dispersion_Method"]))},
      "%s" % [(r["Cell_Key"], r["Value_Method"]) for r in _rows3])
_a, _b = dict(_same[0]), dict(_same[1])
_swapped = [dict(_a, Mark_Record_SHA256=_b["Mark_Record_SHA256"],
                 Method_Attestation_SHA256=_b["Method_Attestation_SHA256"]),
            dict(_b, Mark_Record_SHA256=_a["Mark_Record_SHA256"],
                 Method_Attestation_SHA256=_a["Method_Attestation_SHA256"])]
_held_j, _seen_j = _joined(_swapped)
check("two values that exchange their marks are refused, method for method "
      "identical though they are",
      _held_j == {"P1"} and "VALUE_CONTRADICTS_MARK" in _seen_j,
      "%s" % _seen_j)
# ONE NUMBER AT A TIME, because a swap of the whole row is the easy case: a value
# that keeps its own cell and its own mark and takes ANOTHER mark's mean is the
# shape a rounding, a re-fit or a copied cell produces.
_held_j, _seen_j = _joined([dict(_a, Mean=_b["Mean"])])
check("  a mean taken from another mark is refused on its own",
      _held_j == {"P1"} and "VALUE_CONTRADICTS_MARK" in _seen_j
      and _a["Mean"] != _b["Mean"], "%s" % _seen_j)
check("  and the refusal names the column and both numbers",
      _mark_detail([dict(_a, Mean=_b["Mean"])], "VALUE_CONTRADICTS_MARK")
      .count("Mean") == 1
      and FIN._s(_b["Mean"])[:6] in _mark_detail(
          [dict(_a, Mean=_b["Mean"])], "VALUE_CONTRADICTS_MARK"),
      "%s" % _mark_detail([dict(_a, Mean=_b["Mean"])],
                          "VALUE_CONTRADICTS_MARK"))
_disp = [r for r in _rows3 if not BM.blank(r.get("Dispersion_Value"))]
_held_j, _seen_j = _joined([dict(_disp[0],
                                 Dispersion_Value=str(
                                     float(_disp[0]["Dispersion_Value"]) + 1.0))])
check("  and a number the mark does not carry AT ALL is refused, not skipped",
      _joined([dict(_a, Median="5.0")])[0] == {"P1"}
      and "VALUE_CONTRADICTS_MARK" in _joined([dict(_a, Median="5.0")])[1]
      and BM.blank(_a.get("Median")),
      "%s" % _joined([dict(_a, Median="5.0")])[1])
check("  and so is a dispersion the mark it cites does not carry",
      _held_j == {"P1"} and "VALUE_CONTRADICTS_MARK" in _seen_j
      and len(_disp) > 0, "%s" % _seen_j)
# THE CELL KEY IS THE ONE WITH NO ARITHMETIC SIGNATURE. Every number stays the
# mark's own; only the heading moves, so the panel's totals, means and hashes are
# all unchanged and the figure now says the treated group did what the control
# group did.
_held_j, _seen_j = _joined([dict(_a, Cell_Key=_b["Cell_Key"])])
check("a value filed under another cell's heading is refused, every number "
      "correct though it is",
      _held_j == {"P1"} and "CELL_CONTRADICTS_MARK" in _seen_j
      and _a["Cell_Key"] != _b["Cell_Key"], "%s" % _seen_j)
check("  and the cell it is refused against is derived from the manifests, not "
      "from the value",
      _b["Cell_Key"] in _mark_detail([dict(_a, Cell_Key=_b["Cell_Key"])],
                                     "CELL_CONTRADICTS_MARK"),
      "%s" % _mark_detail([dict(_a, Cell_Key=_b["Cell_Key"])],
                          "CELL_CONTRADICTS_MARK"))
# AND THE MARK IS CHECKED AGAINST ITSELF. Until v7.74 both of a mark's hashes
# were read off the artifact and only the VALUE's copy was recomputed, so editing
# a measurement and its hash together produced a self-consistent artifact that
# every check above accepted.
_edit_dir = os.path.join(ROOT, "marks_edited")


def _mark_detail_at(where, code):
    """The detail one code carries, for the marks last written by `_edited_marks`."""
    said = []
    body = json.load(open(os.path.join(where, "P1_marks.json"), encoding="utf-8"))
    rows = [dict(r, Mark_Record_SHA256=m["Mark_Record_SHA256"],
                 Method_Attestation_SHA256=m["Method_Attestation_SHA256"])
            for r, m in zip(_rows3, body["marks"])]
    FIN.method_contract_failures(
        pd.DataFrame(rows),
        pd.DataFrame([dict(Panel_ID="P1", Mark_Type="LINE_MONO_STYLE")]),
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="RAW_MARKS",
                           Artifact_Path=os.path.join(where, "P1_marks.json"))]),
        where, lambda w, c, d: said.append(d) if c == code else None,
        frames=_verified(_R3_DIR))
    return " | ".join(said)


def _edited_marks(mutate, rows=None, restamp=False, rebind=False,
                  envelope=None):
    """The run's own marks with one of them changed on disk, and the join re-run.

    `rebind` moves the VALUE that cited the changed mark onto its new hashes, so
    the artifact and the values agree with each other. That is the shape a run
    made by something else arrives in, and it is where a check that only compared
    the two of them to each other would find nothing to say.
    """
    shutil.rmtree(_edit_dir, ignore_errors=True)
    os.makedirs(_edit_dir)
    # The run's own manifest travels with the marks: from v7.80 the finalizer
    # re-derives the conditions a panel was measured under from the panel
    # manifest and this file, so a scratch directory without it is a run that
    # never read the panel at all.
    shutil.copy(os.path.join(_R3_DIR, "run_manifest.csv"), _edit_dir)
    body = json.loads(json.dumps(_envelope))
    was = FIN._s(body["marks"][0]["Mark_Record_SHA256"])
    mutate(body["marks"][0])
    if envelope:
        envelope(body)
    # AFTER the mutations, so a re-stamp is a re-stamp under the CHANGED
    # conditions - the artifact a foreign producer hands over, internally
    # perfect and externally undeclared - rather than under the old ones.
    header = {k: v for k, v in body.items() if k != "marks"}
    if restamp:
        body["marks"] = RB.stamp_marks(
            [{k: v for k, v in m.items()
              if k not in ("Mark_Record_SHA256", "Method_Attestation_SHA256")}
             for m in body["marks"]], header)
    path = os.path.join(_edit_dir, "P1_marks.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=1, sort_keys=True)
    if rebind:
        now = body["marks"][0]
        rows = [dict(r, Mark_Record_SHA256=now["Mark_Record_SHA256"],
                     Method_Attestation_SHA256=now["Method_Attestation_SHA256"])
                if FIN._s(r.get("Mark_Record_SHA256")) == was else dict(r)
                for r in (rows if rows is not None else _rows3)]
    seen = []
    held = FIN.method_contract_failures(
        pd.DataFrame(rows if rows is not None else _rows3),
        pd.DataFrame([dict(Panel_ID="P1", Mark_Type="LINE_MONO_STYLE")]),
        pd.DataFrame([dict(Panel_ID="P1", Artifact_Type="RAW_MARKS",
                           Artifact_Path=path)]),
        _edit_dir, lambda w, c, d: seen.append(c),
        frames=_verified(_R3_DIR))
    return held, seen


_held_e, _seen_e = _edited_marks(lambda m: m.update(mean=float(m["mean"]) + 5.0))
check("a measurement edited inside the artifact no longer hashes to its own "
      "record",
      _held_e == {"P1"} and "MARK_RECORD_HASH_MISMATCH" in _seen_e, "%s" % _seen_e)
_held_e, _seen_e = _edited_marks(
    lambda m: m.update(mean=float(m["mean"]) + 5.0), restamp=True)
check("  and re-hashing it does not help: the value cites a mark that is gone",
      _held_e == {"P1"} and "MARK_EVIDENCE_MISSING" in _seen_e, "%s" % _seen_e)
# THE SERIES ON THE MARK IS INSIDE THE MEASUREMENT HASH, so moving a mark to
# another series is the same refusal - which is what closes the last door on the
# cell-key check: an attacker who cannot change the value's key changes the
# mark's series instead.
_held_e, _seen_e = _edited_marks(lambda m: m.update(series="S_R"))
check("  and a mark moved to another series is refused the same way",
      _held_e == {"P1"} and "MARK_RECORD_HASH_MISMATCH" in _seen_e, "%s" % _seen_e)
_held_e, _seen_e = _edited_marks(lambda m: m.update(series="S_R"), restamp=True)
check("  re-hashed, the value that cites it no longer finds its evidence",
      _held_e == {"P1"} and "MARK_EVIDENCE_MISSING" in _seen_e, "%s" % _seen_e)
# AND REBOUND - the shape a foreign producer arrives in rather than an edit: the
# marks and the values agree with each other, and they agree about a series the
# figure's own manifests do not declare.
_held_e, _seen_e = _edited_marks(lambda m: m.update(series="S_R"), restamp=True,
                                 rebind=True)
check("  rebound to it, the mark and the value agree about the wrong cell, and "
      "the manifests refuse both",
      _held_e == {"P1"} and "CELL_CONTRADICTS_MARK" in _seen_e, "%s" % _seen_e)
_held_e, _seen_e = _edited_marks(
    lambda m: m.update(Value_Method="DIRECT_CURVE_INK",
                       Mark_Record_SHA256=m["Mark_Record_SHA256"]))
check("and a method rewritten inside the artifact leaves the mark's own "
      "attestation stale",
      _held_e == {"P1"} and "METHOD_ATTESTATION_STALE" in _seen_e, "%s" % _seen_e)
# A SERIES NO MANIFEST DECLARES CANNOT NAME A CELL, and a mark that names one is
# not evidence for whatever heading the value happens to carry. Fail-closed: the
# expected key is derived or the value is refused, never guessed.
_held_e, _seen_e = _edited_marks(lambda m: m.update(series="S_NOWHERE"),
                                 restamp=True, rebind=True)
check("a mark read as a series the verified manifests do not declare supports "
      "no cell at all",
      _held_e == {"P1"} and "MARK_CELL_UNDECLARED" in _seen_e, "%s" % _seen_e)
# AND A MARK THAT CANNOT ANSWER IS NOT A MARK THAT AGREES. v7.76. The
# re-derivation was partial: an axis it could not derive was absent from its
# answer, and an absent expectation compared equal to whatever the value claimed.
# Here the run's own mark loses the one field that separates a value read off the
# ink from one carried sideways to it.
_held_e, _seen_e = _edited_marks(lambda m: m.update(Value_Span_Px=None),
                                 restamp=True, rebind=True)
check("a mark missing the evidence for an axis refuses the value on it",
      _held_e == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_e,
      "%s" % _seen_e)
check("  and the refusal says which measurement is missing",
      "Value_Span_Px" in _mark_detail_at(_edit_dir, "METHOD_EVIDENCE_INCOMPLETE"),
      "%s" % _mark_detail_at(_edit_dir, "METHOD_EVIDENCE_INCOMPLETE"))
# AND THE GEOMETRY OF THE EVIDENCE IS CHECKED, not only its presence. v7.79. A
# mark whose support columns, span and x cannot all be true re-derived a method
# from fields that contradict each other - the general form of the nine carries
# v7.73 found, and reachable from a foreign producer with every hash correct.
_held_e, _seen_e = _edited_marks(
    lambda m: m.update(Value_Support_Left_Px=float(m["x"]) - 10,
                       Value_Support_Right_Px=float(m["x"]) - 10,
                       Value_Span_Px=0),
    restamp=True, rebind=True)
check("a mark ten pixels away claiming a span of zero is refused, not read as a "
      "direct observation",
      _held_e == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_e,
      "%s" % _seen_e)
# AND A CURVE MARK'S OWN ARITHMETIC, THROUGH THE FINALIZER. v7.87. The line
# reader's numbers are pixel rows put through the panel's axis, exactly as a
# bar's are, and until now only the method was re-derived from them.
_held_e, _seen_e = _edited_marks(
    lambda m: m.update(marker_center_px=float(m["marker_center_px"]) + 7),
    restamp=True, rebind=True)
check("a curve mark read at a row that does not produce its mean is refused",
      _held_e == {"P1"} and "METHOD_EVIDENCE_INCOMPLETE" in _seen_e,
      "%s" % _seen_e)
check("  and the refusal names the row and what it actually reads",
      "under this run's y calibration" in _mark_detail_at(
          _edit_dir, "METHOD_EVIDENCE_INCOMPLETE"),
      "%s" % _mark_detail_at(_edit_dir, "METHOD_EVIDENCE_INCOMPLETE"))
# A SCHEMA THIS MODULE CANNOT JOIN IS NOT A SCHEMA IT MAY FINALIZE. v7.75. Every
# check above was conditional on the producer's own choice of schema: a run
# written to `mark-data/1` skipped the join, the numbers and the cell silently
# and finalized on the method matrix alone, which is the fail-open that reads as
# a pass.
_held_e, _seen_e = _edited_marks(
    lambda m: None,
    envelope=lambda b: b.update(schema="figure-digitization-triage/mark-data/1"))
check("raw marks this module cannot join are refused, not skipped",
      _held_e == {"P1"} and "MARK_EVIDENCE_SCHEMA_UNSUPPORTED" in _seen_e,
      "%s" % _seen_e)
# AND A BLANK HASH IS NOT AN EXEMPTION EITHER. The five readers with no other
# durable route must cite a mark; so must any value whose panel HAS joinable
# marks, whatever its type - the run itself says the evidence was there.
_held_j, _seen_j = _joined([dict(_a, Mark_Record_SHA256="",
                                 Method_Attestation_SHA256="")])
check("a value of a join reader that cites no mark at all is refused",
      _held_j == {"P1"} and "MARK_EVIDENCE_MISSING" in _seen_j, "%s" % _seen_j)
check("  and the five readers named are the ones with no other durable route",
      PROV.MARK_JOIN_REQUIRED == {"LINE_COLOR", "LINE_MONO", "LINE_MONO_STYLE",
                                  "BAR_COLOR", "BOX_VIOLIN"}
      and not (PROV.MARK_JOIN_REQUIRED & {"BAR_MONO", "SCATTER"}),
      "%s" % sorted(PROV.MARK_JOIN_REQUIRED))
# AND THE CONDITIONS THE MARKS WERE MEASURED UNDER ARE THE RUN'S, NOT THE
# ARTIFACT'S OWN. v7.80. `Mark_Record_SHA256` covers the panel box, both
# calibrations and the raster hash - correctly, a pixel is only a measurement
# relative to them - and the finalizer re-hashed the artifact's own copy of them.
# A producer could declare one tick mapping, read the figure under another, hash
# the marks under the second, and hand over a run where the marks, the values and
# every hash agree with each other. The only thing that disagreed was the
# manifest the run was validated against, and nothing compared them.
def _under(change):
    return _edited_marks(lambda m: None, envelope=change, restamp=True,
                         rebind=True)


_held_e, _seen_e = _under(
    lambda b: b.__setitem__("Y_Calibration",
                            dict(b["Y_Calibration"],
                                 slope=b["Y_Calibration"]["slope"] * 1.1)))
check("marks measured under a calibration the manifests do not declare are "
      "refused, however well they agree with their own hashes",
      _held_e == {"P1"} and "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e,
      "%s" % _seen_e)
check("  and the refusal names the field that disagrees",
      "Y_Calibration" in _mark_detail_at(_edit_dir,
                                         "MARK_ENVELOPE_CONTRADICTS_RUN"),
      "%s" % _mark_detail_at(_edit_dir, "MARK_ENVELOPE_CONTRADICTS_RUN"))
_held_e, _seen_e = _under(
    lambda b: b.__setitem__("Panel_Box", [b["Panel_Box"][0] + 5]
                            + list(b["Panel_Box"][1:])))
check("  and so is a panel box nobody declared",
      _held_e == {"P1"} and "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e,
      "%s" % _seen_e)
_held_e, _seen_e = _under(lambda b: b.__setitem__("Image_SHA256", "c" * 64))
check("  and marks read from a raster this run did not read",
      _held_e == {"P1"} and "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e,
      "%s" % _seen_e)
_held_e, _seen_e = _under(lambda b: b.__setitem__("Panel_ID", "P_ELSEWHERE"))
check("  and marks filed under a panel the manifests do not declare at all",
      "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e, "%s" % _seen_e)
# AND A NUMBER SPELLED DIFFERENTLY IS THE SAME NUMBER. A producer whose JSON
# writes the box as floats has not measured under a different box, and refusing
# it would be this module inventing a disagreement out of an encoder's habits.
_held_e, _seen_e = _under(
    lambda b: b.__setitem__("Panel_Box", [float(v) for v in b["Panel_Box"]]))
check("  while a box spelled as floats is the same box",
      "MARK_ENVELOPE_CONTRADICTS_RUN" not in _seen_e, "%s" % _seen_e)
# AND THE DECLARATION DIGEST IS CHECKED LIKE THE REST OF THE ENVELOPE. Marks
# hashed under a declaration this run's manifests do not produce are refused
# however well they agree with themselves - which is what closes the baseline,
# the reader options, the series discriminants and the position columns, none of
# which have a named field in the envelope.
_held_e, _seen_e = _under(
    lambda b: b.__setitem__("Measurement_Declaration_SHA256", "d" * 64))
check("marks hashed under a measurement declaration this run did not make are "
      "refused",
      _held_e == {"P1"} and "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e,
      "%s" % _seen_e)
check("  and the refusal names the declaration, not just the calibration",
      "Measurement_Declaration_SHA256" in _mark_detail_at(
          _edit_dir, "MARK_ENVELOPE_CONTRADICTS_RUN"),
      "%s" % _mark_detail_at(_edit_dir, "MARK_ENVELOPE_CONTRADICTS_RUN"))
# A TOKEN IS NOT A NUMBER, THOUGH. The axis scale is a declaration, and the mark
# hashes cover it: marks hashed under `linear` were hashed under a string this
# run's manifests do not produce, and the fix for float spelling must not quietly
# become case-insensitivity for everything.
_held_e, _seen_e = _under(
    lambda b: b["Y_Calibration"].__setitem__(
        "scale", str(b["Y_Calibration"]["scale"]).lower()))
check("  while an axis scale spelled differently is a different declaration",
      _held_e == {"P1"} and "MARK_ENVELOPE_CONTRADICTS_RUN" in _seen_e,
      "%s" % _seen_e)
# THE HEADER IS BUILT BY ONE FUNCTION, so the writer and the checker cannot
# drift: the run's own envelope re-derives exactly from the verified manifests.
_run_row = next(r for r in csv.DictReader(
    open(os.path.join(_R3_DIR, "run_manifest.csv"), encoding="utf-8"))
    if r["Panel_ID"] == "P1")
_panel_row = next(p for _, p in RB.load_manifests(
    os.path.join(_R3_DIR, "manifests"))["panels"].iterrows()
    if FIN._s(p.get("Panel_ID")) == "P1")
_r3_frames = RB.load_manifests(os.path.join(_R3_DIR, "manifests"))
check("the run's own marks were measured under the conditions it declared",
      {k: _envelope.get(k) for k in RB.MARK_ENVELOPE_FIELDS}
      == json.loads(json.dumps(RB.mark_envelope_header(
          _panel_row, _run_row["Image_SHA256"], _run_row["Reader_Version"],
          series_rows=[r for _, r in _r3_frames["series"].iterrows()
                       if FIN._s(r.get("Panel_ID")) == "P1"],
          position_rows=[r for _, r in _r3_frames["positions"].iterrows()
                         if FIN._s(r.get("Panel_ID")) == "P1"],
          config_rows=[r for _, r in _r3_frames["configs"].iterrows()
                       if FIN._s(r.get("Config_ID"))
                       == FIN._s(_panel_row.get("Config_ID"))]))),
      "%s" % {k: _envelope.get(k) for k in RB.MARK_ENVELOPE_FIELDS})
# AND THE DECLARATION DIGEST IS OVER MORE THAN THE NAMED FIELDS. v7.82. A
# baseline, a reader threshold, a series colour or a position's own column are
# all instructions this panel was read under, and none of them were bound to the
# marks: a producer could declare one set, read the figure under another, and
# hash the marks under the second with every check passing.
_decl = RB.measurement_declaration_sha256(
    _panel_row, [r for _, r in _r3_frames["series"].iterrows()
                 if FIN._s(r.get("Panel_ID")) == "P1"],
    [r for _, r in _r3_frames["positions"].iterrows()
     if FIN._s(r.get("Panel_ID")) == "P1"], [],
    _run_row["Image_SHA256"], _run_row["Reader_Version"])
check("the measurement declaration is the panel, its series, its positions and "
      "its reader options",
      _decl == _envelope["Measurement_Declaration_SHA256"]
      and all(_decl != RB.measurement_declaration_sha256(
          changed, series, positions, configs, _run_row["Image_SHA256"],
          _run_row["Reader_Version"])
          for changed, series, positions, configs in (
              (dict(_panel_row, Baseline_Value="7"),
               [r for _, r in _r3_frames["series"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"],
               [r for _, r in _r3_frames["positions"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"], []),
              (_panel_row,
               [dict(r, Colour_Hex="#000000")
                for _, r in _r3_frames["series"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"],
               [r for _, r in _r3_frames["positions"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"], []),
              (_panel_row,
               [r for _, r in _r3_frames["series"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"],
               [dict(r, X_Pixel=str(int(float(r["X_Pixel"])) + 3))
                for _, r in _r3_frames["positions"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"], []),
              (_panel_row,
               [r for _, r in _r3_frames["series"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"],
               [r for _, r in _r3_frames["positions"].iterrows()
                if FIN._s(r.get("Panel_ID")) == "P1"],
               [dict(Config_ID="C1", Option="threshold", Value="150")]))),
      "%s" % _decl[:16])
# AND THE COLUMNS THIS BINDS ARE THE COLUMNS THE ADAPTER WRITES. A reader that
# starts carrying a tenth number would otherwise be bound to its mark in nine,
# and the tenth would be free - the same drift `INTERPOLATION_CARRIED` was
# written for.
_probe = dict(mean=1.0, dispersion=2.0, errorbar_lower=3.0, errorbar_upper=4.0,
              median=5.0, q1=6.0, q3=7.0, whisker_lower=8.0, whisker_upper=9.0,
              series="S_B", x_label="D0")
_from_marks = set()
for _kind in ("CONTINUOUS", "QUANTILE_SUMMARY"):
    _rec = MR.to_value_records([dict(_probe)], _kind, "U1",
                               x_factor="TIMEPOINT", series_factor="GROUP")[0]
    _from_marks |= {c for c, v in _rec.items()
                    if isinstance(v, float) and v in set(_probe.values())}
check("every number the adapter copies from a mark is a number the join checks",
      _from_marks == {c for c, _f in FIN.MARK_VALUE_FIELDS},
      "adapter %s / bound %s"
      % (sorted(_from_marks), sorted(c for c, _f in FIN.MARK_VALUE_FIELDS)))

print()
print("everything about a review that can be checked without looking at ink")
# v7.73. A human review of an R2 or R3 panel is a person looking at ink and
# saying what they see, and nothing here does that. What a program can do is
# everything around it - which cells will be asked about and why, whether the
# bundle is complete, whether the answers are, and where two independent
# reviewers disagree - and doing that badly is how a review becomes a formality.
import review_preflight as PF                                      # noqa: E402
_asked = PF.questions(_R3_DIR)
check("the preflight names the cells that will be asked about, before anybody "
      "starts",
      len(_asked) == 2
      and {q["Tier"] for q in _asked} == {"R3"}
      and all(q["Inference_ID"] for q in _asked), "%s" % _asked)
check("  and says WHY each one, in the words of the question",
      all("NUMBER was reconstructed" in q["Asked_Because"] for q in _asked),
      "%s" % [q["Asked_Because"] for q in _asked])
check("  derived the same way the finalizer derives it, or the two disagree",
      {q["Inference_ID"] for q in _asked} == set(_ids3),
      "%s" % sorted(q["Inference_ID"] for q in _asked))
check("a complete bundle has no problems to report",
      PF.bundle_problems(_R3_DIR) == [], "%s" % PF.bundle_problems(_R3_DIR))
_answers([_answer(_ids3[0])])
check("and an unanswered question is reported before a finalizer is asked",
      any("has no answer" in why for _w, why in PF.answer_problems(
          _R3_DIR, _r3_review, _r3_cells)),
      "%s" % PF.answer_problems(_R3_DIR, _r3_review, _r3_cells))
_answers([_answer(i) for i in _ids3])
_panel3()
check("  while a complete set of answers reports nothing",
      PF.answer_problems(_R3_DIR, _r3_review, _r3_cells) == [],
      "%s" % PF.answer_problems(_R3_DIR, _r3_review, _r3_cells))
# TWO REVIEWERS, COMPARED CELL BY CELL. The identifiers are content-derived, so
# two people working from two copies of the bundle produce comparable rows
# without having agreed on anything first.
_second = os.path.join(_R3_DIR, "second_reviewer.csv")
with open(_second, "w", newline="", encoding="utf-8") as _fh:
    _w2 = csv.writer(_fh)
    _w2.writerow(FIN.inference_review_columns())
    for _i, _iid in enumerate(_ids3):
        _row2 = _answer(_iid, "REJECTED" if _i == 0 else "CONFIRMED")
        _w2.writerow([_row2.get(c, "") for c in FIN.inference_review_columns()])
check("two reviewers who disagree about one cell are reported on that cell",
      PF.disagreements(_r3_cells, _second)
      == [(_ids3[0], "CONFIRMED", "REJECTED")],
      "%s" % PF.disagreements(_r3_cells, _second))
# AND WHAT THE FINALIZER WOULD SAY, THROUGH THE FINALIZER'S OWN FUNCTION. v7.77.
# The preflight answered overlapping questions in its own code, so it could report
# a clean bundle that `finalize` then refused - the worst failure a preflight has,
# because the reviewer trusts it and signs. `validate_finalization` decides and
# `finalize` writes; the preflight calls the decider.
#
# PARITY IS CHECKED PER MUTATION, not once on the happy path, because two code
# paths agree on the happy path by construction.
_answers([_answer(i) for i in _ids3])
_panel3()


def _parity(name, mutate):
    """Break one thing; the preflight and the finalizer must say the same."""
    keep_review = open(_r3_review, encoding="utf-8").read()
    keep_cells = open(_r3_cells, encoding="utf-8").read()
    try:
        mutate()
        said, refusals = PF.would_refuse(_R3_DIR, _r3_review, _r3_cells,
                                         today=datetime.date(2026, 8, 6))
        done = FIN.finalize(_R3_DIR, review_path=_r3_review,
                            inference_review_path=_r3_cells,
                            run_date="2026-08-06",
                            today=datetime.date(2026, 8, 6))
    finally:
        open(_r3_review, "w", encoding="utf-8").write(keep_review)
        open(_r3_cells, "w", encoding="utf-8").write(keep_cells)
    check("  the preflight and the finalizer agree: %s" % name,
          said == done["status"]
          and {c for _w, c, _d in refusals}
          == {FIN._s(p["check"]) for p in done["problems"]},
          "preflight %s %s / finalizer %s %s"
          % (said, sorted({c for _w, c, _d in refusals}), done["status"],
             sorted({FIN._s(p["check"]) for p in done["problems"]})))


_parity("a complete bundle", lambda: None)
_parity("one cell unanswered", lambda: _answers([_answer(_ids3[0])]))
_parity("a cell answered twice",
        lambda: _answers([_answer(_ids3[0]), _answer(_ids3[0]),
                          _answer(_ids3[1])]))
_parity("a rejected reconstruction",
        lambda: _answers([_answer(_ids3[0]), _answer(_ids3[1], "REJECTED")]))
_parity("an unregistered approver",
        lambda: review([row(Review_Subject_SHA256=_fp3,
                            Inference_Checked="CONFIRMED",
                            Reviewer_ID="RV_NOBODY")], path=_r3_review))
_parity("an approval of a different run",
        lambda: review([row(Review_Subject_SHA256="e" * 64,
                            Inference_Checked="CONFIRMED")], path=_r3_review))
_parity("no panel decision at all", lambda: review([], path=_r3_review))
_parity("the inference confirmation withheld",
        lambda: review([row(Review_Subject_SHA256=_fp3,
                            Inference_Checked="")], path=_r3_review))
_answers([_answer(i) for i in _ids3])
_panel3()
# TWO REVIEWERS WHO EACH CONTRADICT THEMSELVES ARE NOT TWO REVIEWERS WHO AGREE.
# `disagreements` built each side with a dict comprehension, so a file answering
# one cell twice kept the last row silently - and the duplicate is exactly what
# the answer check refuses, reported by one function and hidden by the other.
_twice = os.path.join(_R3_DIR, "answered_twice.csv")
with open(_twice, "w", newline="", encoding="utf-8") as _fh:
    _w3 = csv.writer(_fh)
    _w3.writerow(FIN.inference_review_columns())
    for _v in ("CONFIRMED", "REJECTED"):
        _r = _answer(_ids3[0], _v)
        _w3.writerow([_r.get(c, "") for c in FIN.inference_review_columns()])
check("a reviewer who answered one cell twice is reported, not silently merged",
      any("answered 2 times" in b
          for _iid, _a, b in PF.disagreements(_r3_cells, _twice)),
      "%s" % PF.disagreements(_r3_cells, _twice))
# AND THE COUNT IS THE COUNT. It deduplicated the duplicates and then counted
# occurrences in that list, so three answers to one cell reported as two - wrong
# in the direction of looking smaller.
_thrice = os.path.join(_R3_DIR, "answered_thrice.csv")
with open(_thrice, "w", newline="", encoding="utf-8") as _fh:
    _w4 = csv.writer(_fh)
    _w4.writerow(FIN.inference_review_columns())
    for _v in ("CONFIRMED", "REJECTED", "CONFIRMED"):
        _r = _answer(_ids3[0], _v)
        _w4.writerow([_r.get(c, "") for c in FIN.inference_review_columns()])
check("  and three answers are reported as three",
      any("answered 3 times" in b
          for _iid, _a, b in PF.disagreements(_r3_cells, _thrice)),
      "%s" % PF.disagreements(_r3_cells, _thrice))
# AND IT SIGNS NOTHING. A preflight that finalizes is not a preflight, and a
# program that fills in a confirmation is the one failure this package exists to
# prevent - so the claim is checked the only way it can be: nothing in the run
# directory changes.
def _fingerprint(directory):
    """Every file under the run, by content. Names alone miss a rewrite."""
    out = {}
    for where, _dirs, files in os.walk(directory):
        for name in files:
            path = os.path.join(where, name)
            out[os.path.relpath(path, directory)] = RB.file_sha256(path)
    return out


_before = _fingerprint(_R3_DIR)
PF.main([_R3_DIR, "--review", _r3_review, "--inference", _r3_cells,
         "--second", _second])
check("and the preflight signs nothing: the run directory is untouched",
      _fingerprint(_R3_DIR) == _before,
      "the preflight changed %s"
      % sorted(set(_fingerprint(_R3_DIR).items())
               ^ set(_before.items())))
# AND THE EXIT CODE IS THE FINALIZER'S ANSWER. v7.78. It was "any problem at
# all", so a reconstruction a person correctly REJECTED - the run finalizes
# without that cell, which is the partial-rejection path the first pilot is
# designed around - came back from the preflight as a failure. A pilot whose own
# designed-in rejection reads as a broken bundle teaches the reviewer to ignore
# the tool.
_answers([_answer(_ids3[0]), _answer(_ids3[1], "REJECTED")])
_panel3()
_rej_status, _rej_problems = PF.would_refuse(_R3_DIR, _r3_review, _r3_cells,
                                             today=datetime.date(2026, 8, 6))
check("a rejected reconstruction still finalizes, and the preflight passes",
      _rej_status == "FINALIZED"
      and any(c == "INFERENCE_REJECTED" for _w, c, _d in _rej_problems)
      and PF.main([_R3_DIR, "--review", _r3_review,
                   "--inference", _r3_cells]) == 0,
      "%s / %s" % (_rej_status, [c for _w, c, _d in _rej_problems]))
check("  and it is reported as an exclusion, not as a refusal",
      all(c in FIN.NONFATAL_CHECKS for _w, c, _d in _rej_problems),
      "%s" % [c for _w, c, _d in _rej_problems])
check("  while a batch that must be whole says so with --require-all-values",
      PF.main([_R3_DIR, "--review", _r3_review, "--inference", _r3_cells,
               "--require-all-values"]) == 2)
# AND "WHOLE" MEANS THE PANELS TOO. Checking only the exclusions let a run pass
# strict mode with one panel refused beside the one that finalized: values lost,
# and the flag that exists to notice that said nothing. Built by approving a
# panel this run does not have, which is a refusal on a run that still
# finalizes.
_answers([_answer(i) for i in _ids3])
review([row(Review_Subject_SHA256=_fp3, Inference_Checked="CONFIRMED"),
        dict(row(Review_Subject_SHA256=_fp3, Inference_Checked="CONFIRMED"),
             Review_ID="R002", Panel_ID="P_NOT_IN_THIS_RUN")],
       path=_r3_review)
_side_status, _side_problems = PF.would_refuse(
    _R3_DIR, _r3_review, _r3_cells, today=datetime.date(2026, 8, 6))
check("a run that finalizes with something refused beside it passes by default "
      "and fails strict",
      _side_status == "FINALIZED"
      and any(c not in FIN.NONFATAL_CHECKS for _w, c, _d in _side_problems)
      and PF.main([_R3_DIR, "--review", _r3_review,
                   "--inference", _r3_cells]) == 0
      and PF.main([_R3_DIR, "--review", _r3_review, "--inference", _r3_cells,
                   "--require-all-values"]) == 2,
      "%s / %s" % (_side_status, [c for _w, c, _d in _side_problems]))
_panel3()
_answers([_answer(_ids3[0])])
check("and an unanswered question still fails the preflight",
      PF.main([_R3_DIR, "--review", _r3_review, "--inference", _r3_cells]) == 2)
_answers([_answer(i) for i in _ids3])
check("  while a complete review passes it",
      PF.main([_R3_DIR, "--review", _r3_review, "--inference", _r3_cells]) == 0)
# AND THE TWO SHARE THEIR INPUTS, not only their decider. `--manifests` exists on
# the finalizer for a run that has been moved; without it on the preflight, the
# same run could fail one and pass the other with the same decision function
# between them.
_moved_dir = os.path.join(ROOT, "moved_run")
shutil.rmtree(_moved_dir, ignore_errors=True)
shutil.copytree(_R3_DIR, _moved_dir)
_moved_manifests = os.path.join(ROOT, "moved_manifests")
shutil.rmtree(_moved_manifests, ignore_errors=True)
shutil.move(os.path.join(_moved_dir, "manifests"), _moved_manifests)
# WHAT A RUN HANDED TO SOMEBODY ELSE LOOKS LIKE: the stamp records the absolute
# path of a directory on the machine that produced it, and that directory is not
# on this one. The `manifests/` copy inside the run is the fallback that travels;
# a run whose manifests live elsewhere has neither, and needs to be told.
_moved_stamp = os.path.join(_moved_dir, "run_stamp.json")
_ms = json.load(open(_moved_stamp, encoding="utf-8"))
_ms["Manifest_Dir"] = os.path.join(ROOT, "a_directory_on_another_machine")
json.dump(_ms, open(_moved_stamp, "w", encoding="utf-8"), indent=1,
          sort_keys=True)
_moved_review = os.path.join(_moved_dir, "value_review.csv")
_moved_cells = os.path.join(_moved_dir, "inference_review.csv")
check("a run whose manifests were moved out is refused by both",
      PF.would_refuse(_moved_dir, _moved_review, _moved_cells,
                      today=datetime.date(2026, 8, 6))[0]
      == FIN.finalize(_moved_dir, review_path=_moved_review,
                      inference_review_path=_moved_cells,
                      run_date="2026-08-06",
                      today=datetime.date(2026, 8, 6))["status"]
      != "FINALIZED",
      "%s" % (PF.would_refuse(_moved_dir, _moved_review, _moved_cells,
                              today=datetime.date(2026, 8, 6))[0],))
check("  and pointed at them, both finalize",
      PF.would_refuse(_moved_dir, _moved_review, _moved_cells,
                      today=datetime.date(2026, 8, 6),
                      manifest_dir=_moved_manifests)[0] == "FINALIZED"
      and PF.main([_moved_dir, "--review", _moved_review,
                   "--inference", _moved_cells,
                   "--manifests", _moved_manifests]) == 0,
      "%s" % (PF.would_refuse(_moved_dir, _moved_review, _moved_cells,
                              today=datetime.date(2026, 8, 6),
                              manifest_dir=_moved_manifests),))
# A DECISION FILE THAT WILL NOT PARSE IS A FINDING, NOT A TRACEBACK. The preflight
# read the same CSVs the finalizer does, unguarded, so a reviewer with a broken
# file got a stack trace where the finalizer gives a code and a filename.
_broken = os.path.join(ROOT, "broken_review.csv")
with open(_broken, "w", encoding="utf-8") as _fh:
    _fh.write('Review_ID,Panel_ID\n"unclosed,quote\n')
_pf_broken = PF.would_refuse(_R3_DIR, _broken, _r3_cells,
                             today=datetime.date(2026, 8, 6))
_fin_broken = FIN.finalize(_R3_DIR, review_path=_broken,
                           inference_review_path=_r3_cells,
                           run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
check("a malformed review file gives both of them the same finding",
      _pf_broken[0] == _fin_broken["status"]
      and {c for _w, c, _d in _pf_broken[1]}
      == {FIN._s(p["check"]) for p in _fin_broken["problems"]}
      and "REVIEW_FILE_UNREADABLE" in {c for _w, c, _d in _pf_broken[1]},
      "%s / %s" % (_pf_broken, _fin_broken["status"]))
check("  and the preflight reports it instead of raising",
      PF.main([_R3_DIR, "--review", _broken, "--inference", _r3_cells]) == 2)
_broken_cells = os.path.join(ROOT, "broken_inference.csv")
with open(_broken_cells, "w", encoding="utf-8") as _fh:
    _fh.write('Inference_ID,Panel_ID\n"unclosed,quote\n')
_pf_bc = PF.would_refuse(_R3_DIR, _r3_review, _broken_cells,
                         today=datetime.date(2026, 8, 6))
_fin_bc = FIN.finalize(_R3_DIR, review_path=_r3_review,
                       inference_review_path=_broken_cells,
                       run_date="2026-08-06", today=datetime.date(2026, 8, 6))
check("and so does a malformed per-cell answer file",
      _pf_bc[0] == _fin_bc["status"]
      and {c for _w, c, _d in _pf_bc[1]}
      == {FIN._s(p["check"]) for p in _fin_bc["problems"]}
      and PF.main([_R3_DIR, "--review", _r3_review,
                   "--inference", _broken_cells]) == 2,
      "%s / %s" % (_pf_bc, _fin_bc["status"]))
_answers([_answer(i) for i in _ids3])
_panel3()
# INCLUDING THE FUNCTION IT SHARES WITH THE FINALIZER. `finalize` removes the
# previous accepted file and stamp before it decides anything, so the decider had
# to be lifted out of that; a decider that still deleted would take a bundle
# apart every time a reviewer asked what would happen.
_before = _fingerprint(_R3_DIR)
FIN.validate_finalization(_R3_DIR, review_path=_r3_review,
                          inference_review_path=_r3_cells,
                          today=datetime.date(2026, 8, 6))
check("  and neither does the decision function inside the finalizer",
      _fingerprint(_R3_DIR) == _before,
      "validate_finalization changed %s"
      % sorted(set(_fingerprint(_R3_DIR).items()) ^ set(_before.items())))

print()
print("the hash on the stamp is the hash of the decisions that were read")
# v7.79. `validate_finalization` read the review files and `finalize` hashed the
# PATHS afterwards, so a spreadsheet autosave landing between the decision and
# the stamp produced an accepted file decided from one set of decisions and a
# `Review_File_SHA256` naming another - the exact question the hash exists to
# answer, answered wrong, with nothing in the run saying so.
#
# Observed by making the race happen: the loader writes into the file the moment
# it has been read, which is what a save landing in that window does.
_race_dir, _ = fresh_run("run_race")
_race_review = os.path.join(_race_dir, "value_review.csv")
_race_q = pd.read_csv(os.path.join(_race_dir, "review_queue.csv"),
                      dtype=object).fillna("")
review([row(Review_Subject_SHA256=_race_q.loc[0, "Review_Subject_SHA256"])],
       path=_race_review)
_read_bytes = RB.file_sha256(_race_review)
_real_read_decisions = FIN.read_decisions


def _read_then_save(path, *a, **kw):
    out = _real_read_decisions(path, *a, **kw)
    if path == _race_review:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n")            # an autosave, landing in the window
    return out


try:
    FIN.read_decisions = _read_then_save
    _raced = FIN.finalize(_race_dir, review_path=_race_review,
                          run_date="2026-08-06",
                          today=datetime.date(2026, 8, 6))
finally:
    FIN.read_decisions = _real_read_decisions
_race_stamp = json.load(open(os.path.join(_race_dir, "finalize_stamp.json"),
                             encoding="utf-8"))
check("a save landing between the decision and the stamp does not change what "
      "the stamp says was read",
      _raced["status"] == "FINALIZED"
      and _race_stamp["Review_File_SHA256"] == _read_bytes
      and RB.file_sha256(_race_review) != _read_bytes,
      "stamp %s / read %s / on disk %s"
      % (_race_stamp["Review_File_SHA256"][:12], _read_bytes[:12],
         RB.file_sha256(_race_review)[:12]))
# AND THE WINDOW IS CLOSED AT BOTH ENDS. Above, the save lands after the read;
# here it lands between the HASH and the PARSE, which is the window that exists
# only inside the loader. Hashing the bytes and then re-opening the path would
# decide from a file nobody hashed - the same defect the other way round.
_race2_dir, _ = fresh_run("run_race2")
_race2_review = os.path.join(_race2_dir, "value_review.csv")
_race2_q = pd.read_csv(os.path.join(_race2_dir, "review_queue.csv"),
                       dtype=object).fillna("")
review([row(Review_Subject_SHA256=_race2_q.loc[0, "Review_Subject_SHA256"])],
       path=_race2_review)
_race2_bytes = RB.file_sha256(_race2_review)


class _SaveOnHash:
    """`hashlib`, with an autosave landing the instant the bytes are hashed."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def sha256(self, data=b""):
        if data and _race2_review in getattr(self, "_armed", [_race2_review]):
            review([row(Review_Subject_SHA256=_race2_q.loc[
                0, "Review_Subject_SHA256"], Reviewer_ID="RV_NOBODY")],
                path=_race2_review)
        return self._real.sha256(data)


_real_hashlib = FIN.hashlib
try:
    FIN.hashlib = _SaveOnHash(_real_hashlib)
    _raced2 = FIN.finalize(_race2_dir, review_path=_race2_review,
                           run_date="2026-08-06",
                           today=datetime.date(2026, 8, 6))
finally:
    FIN.hashlib = _real_hashlib
check("and the decisions are parsed from the bytes that were hashed, not from "
      "the path again",
      _raced2["status"] == "FINALIZED"
      and json.load(open(os.path.join(_race2_dir, "finalize_stamp.json"),
                         encoding="utf-8"))["Review_File_SHA256"]
      == _race2_bytes,
      "%s / stamp %s / hashed %s"
      % (_raced2["status"],
         json.load(open(os.path.join(_race2_dir, "finalize_stamp.json"),
                        encoding="utf-8"))["Review_File_SHA256"][:12],
         _race2_bytes[:12]))
# AND A REFUSAL RECORDS THE BYTES THAT CAUSED IT. The parse branch hashed the
# path again, so a malformed file saved over immediately afterwards left the
# stamp naming bytes that would have parsed. Smaller than the other window - it
# is the audit rather than the accepted values - and the same shape.
_bad_dir, _ = fresh_run("run_badbytes")
_bad_review = os.path.join(_bad_dir, "value_review.csv")
with open(_bad_review, "w", encoding="utf-8") as _fh:
    _fh.write('Review_ID,Panel_ID\n"unclosed,quote\n')
_bad_bytes = RB.file_sha256(_bad_review)
_real_or_blank = RB.file_sha256_or_blank


def _repair_then_hash(path):
    """A save landing the moment somebody re-opens the file to hash it.

    Only reachable if the refusal DOES re-open it: the loader that hashes before
    it parses already has the digest and never calls this for the review file.
    """
    if path == _bad_review:
        review([row()], path=_bad_review)
    return _real_or_blank(path)


try:
    RB.file_sha256_or_blank = _repair_then_hash
    FIN.finalize(_bad_dir, review_path=_bad_review, run_date="2026-08-06",
                 today=datetime.date(2026, 8, 6))
finally:
    RB.file_sha256_or_blank = _real_or_blank
check("a refusal names the bytes that caused it, not the ones saved after",
      json.load(open(os.path.join(_bad_dir, "finalize_stamp.json"),
                     encoding="utf-8"))["Review_File_SHA256"] == _bad_bytes,
      "stamp %s / broken %s / on disk %s"
      % (json.load(open(os.path.join(_bad_dir, "finalize_stamp.json"),
                        encoding="utf-8"))["Review_File_SHA256"][:12],
         _bad_bytes[:12], RB.file_sha256(_bad_review)[:12]))
check("  and the per-cell answers are hashed the same way, when there are any",
      FIN.validate_finalization(
          _R3_DIR, review_path=_r3_review, inference_review_path=_r3_cells,
          today=datetime.date(2026, 8, 6)).inference_sha
      == RB.file_sha256(_r3_cells),
      "%s" % FIN.validate_finalization(
          _R3_DIR, review_path=_r3_review, inference_review_path=_r3_cells,
          today=datetime.date(2026, 8, 6)).inference_sha)

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
