"""Scenarios for a group's own n (`series_n.csv`, per-cell `N_Cell`).

The claim under test (decided 2026-10-19, "1은 만들어주고"): a unit's one
`N_Outcome` cannot say the n of a panel whose series are groups of different
size - women and men, finishers and non-finishers - and every value such a panel
produced failed machine QC on a missing n however well it was read. Each group
now carries its own n, from the identity card (one per series, all or none, never
beside the card's n) through the plan and an optional manifest to the value row
(`N_Cell`), and the grid gate takes it in place of the unit's.

Four kinds of scenario: what the card gate refuses, what the batch layer refuses,
what the run writes on each value, and what the gate (and the re-gate at
finalization) does with it.
"""
import csv
import datetime
import io
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
import identity_proposer as IP                                     # noqa: E402
import mark_readers as MR                                          # noqa: E402
import record_identity as RI                                       # noqa: E402
import run_batch as RB                                             # noqa: E402

ROOT = tempfile.mkdtemp(prefix="fdt_series_n_")
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
        "series_n": (None, BM.series_n_columns()),
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


def validate(series_n=(), readings=READINGS, panels=PANELS, units=UNITS,
             series=SERIES):
    problems = BM.validate_batch_manifests(
        frame(panels, BM.panel_manifest_columns()),
        frame(series, BM.series_manifest_columns()),
        frame(POSITIONS, BM.position_manifest_columns()),
        frame([], BM.reader_config_columns()),
        units=frame(units, GE.fig_unit_columns()),
        source_documents=frame(SOURCE_DOCUMENTS, BM.source_document_manifest_columns()),
        source_figures=frame(SOURCE_FIGURES, BM.source_figure_manifest_columns()),
        source_panels=frame(SOURCE_PANELS, BM.source_panel_inventory_columns()),
        reviewers=frame(REVIEWERS, BM.reviewer_registry_columns()),
        readings=frame(readings, BM.supplied_readings_columns()),
        series_n=frame(list(series_n), BM.series_n_columns()),
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



# The fixture's two series are groups of different size: CONTROL 11, TREATED 9.
SERIES_N = [dict(Panel_ID="P1", Series_ID="S_B", N_Outcome="11",
                 N_Source="identity card (per series)", Note=""),
            dict(Panel_ID="P1", Series_ID="S_R", N_Outcome="9",
                 N_Source="identity card (per series)", Note="")]
NO_UNIT_N = [dict(UNITS[0], N_Outcome="", N_Source="")]


# ==========================================================================
print("the card gate: one n for the card, or one per series - never both, never some")
check("a positive whole number, as a number or as digits, is a group's n",
      all(RI.series_n_ok(v) for v in (1, 11, "9", " 12 ", None, "")))
check("zero, a negative, a fraction, a word and a boolean are not",
      not any(RI.series_n_ok(v) for v in (0, -3, "0", 1.5, "1.5", "eleven", True)))

_TMP = os.path.join(ROOT, "card")
_PROP = os.path.join(_TMP, "ip")
os.makedirs(_PROP)
_PROPOSED = {c: "" for c in IP.IDENTITY_COLUMNS}
_PROPOSED.update({"Proposal_ID": "GP001", "Raster": "fig.png", "Region": "20,20,760,540",
                  "Panel_X0": "100", "Panel_X1": "700", "Panel_Y0": "60", "Panel_Y1": "460",
                  "Panel_Kind": "BAR", "X_Label_Read_Status": IP.READ_OK,
                  "X_Labels_Read": "Pre@175;D1@325", "Series_Read_Status": IP.READ_OK,
                  "Series_Read": "Women@220,40,40;Men@40,80,220", "Mark_Type_Proposed": "BAR_COLOR",
                  "Outcome_Read": "Heart rate", "Unit_Read": "bpm",
                  "Human_Verification_Status": IP.PENDING})
IP.write_proposals(os.path.join(_PROP, RI.PROPOSALS), [_PROPOSED])


def _series(*ns):
    out = []
    for (name, colour), n in zip((("Women", "#DC2828"), ("Men", "#2850DC")), ns):
        e = {"name": name, "colour": colour, "line_style": "", "marker": "",
             "marker_fill": "", "bar_fill": ""}
        if n is not None:
            e["n"] = n
        out.append(e)
    return json.dumps(out)


def _answer(**over):
    row = {"Proposal_ID": "GP001", "Human_Verification_Status": "CONFIRMED",
           "X_Factor": "TIMEPOINT",
           "X_Labels": json.dumps([{"label": "Pre", "px": 175}, {"label": "D1", "px": 325}]),
           "Series_Factor": "SEX", "Series": _series(11, 10), "Mark_Type": "BAR_COLOR",
           "Outcome_Name": "Heart rate", "Unit": "bpm", "N_Outcome": "",
           "Bar_Top_Definition": "OUTLINE_CENTER", "Errorbar_Stem_Confirmed": "TRUE",
           "Verified_By": "MC", "Seen_By_Person": "1", "Note": ""}
    row.update(over)
    return row


def _record(answer):
    out = os.path.join(_TMP, "out.csv")
    if os.path.exists(out):
        os.remove(out)
    written, refused, _p = RI.record(_PROP, [answer], "2026-10-19", out_path=out,
                                     log=lambda *a: None)
    return written, [c for _n, ps in refused for c, _w in ps]


_w, _codes = _record(_answer())
check("a card with every group's n and no card n is written",
      len(_w) == 1 and not _codes, "%s" % _codes)
check("  and the decision keeps each group's n on its series",
      _w and [e.get("n") for e in json.loads(_w[0]["Series"])] == [11, 10]
      and _w[0]["N_Outcome"] == "", "%s" % (_w[0]["Series"] if _w else None))
check("an n on some series and not others is refused",
      "SERIES_N_PARTIAL" in _record(_answer(Series=_series(11, None)))[1])
check("a group's n beside the card's n is refused",
      "N_TWICE" in _record(_answer(N_Outcome="21"))[1])
check("a group's n that is not a positive whole number is refused",
      "SERIES_N_BAD" in _record(_answer(Series=_series(11, 0)))[1]
      and "SERIES_N_BAD" in _record(_answer(Series=_series("ten", 10)))[1])
check("a card with one n and no group's n is written as before",
      not _record(_answer(Series=_series(None, None), N_Outcome="21"))[1])
check("the routed answer's n as digits is a group's n",
      not _record(_answer(Series=_series("11", "10")))[1])

# ==========================================================================
print()
print("the batch layer: a group's n names a declared series, once, all or none")
check("the fixture's groups validate with the unit's n left blank",
      validate(SERIES_N, units=NO_UNIT_N) == set(),
      "%s" % sorted(validate(SERIES_N, units=NO_UNIT_N)))
check("a batch without the file validates as before",
      validate() == set(), "%s" % sorted(validate()))
check("a panel nobody declared is refused",
      "SERIES_N_PANEL_UNKNOWN" in validate([dict(SERIES_N[0], Panel_ID="P9")],
                                           units=NO_UNIT_N))
check("a series the panel does not declare is refused",
      "SERIES_N_SERIES_UNKNOWN" in validate(SERIES_N + [dict(SERIES_N[0], Series_ID="S_X")],
                                            units=NO_UNIT_N))
check("one series given two n's is refused",
      "SERIES_N_DUPLICATE" in validate(SERIES_N + [dict(SERIES_N[0], N_Outcome="12")],
                                       units=NO_UNIT_N))
check("an n that is not a positive whole number is refused",
      "SERIES_N_BAD" in validate([dict(SERIES_N[0], N_Outcome="0"), SERIES_N[1]],
                                 units=NO_UNIT_N)
      and "SERIES_N_BAD" in validate([dict(SERIES_N[0], N_Outcome="10.5"), SERIES_N[1]],
                                     units=NO_UNIT_N))
check("where the n was read is required",
      "MISSING_REQUIRED" in validate([dict(SERIES_N[0], N_Source=""), SERIES_N[1]],
                                     units=NO_UNIT_N))
check("some of a panel's series and not all is refused",
      "SERIES_N_PARTIAL" in validate(SERIES_N[:1], units=NO_UNIT_N))
check("a group's n beside the unit's own n is refused",
      "SERIES_N_WITH_UNIT_N" in validate(SERIES_N))
check("a unit that is not continuous or a quantile summary takes no group's n",
      "SERIES_N_STATISTIC_UNSUPPORTED" in validate(
          SERIES_N, units=[dict(NO_UNIT_N[0], Statistic_Type="ASSOCIATION")]))

# ==========================================================================
print()
print("the run stamps each value with its group's n")
_levels = RB.series_n_by_cell(frame(SERIES_N, BM.series_n_columns()),
                              frame(SERIES, BM.series_manifest_columns()))
check("a group's n is found by the level its series puts in the Cell_Key",
      RB.cell_n(_levels.get("P1"), "ARM=CONTROL;TIMEPOINT=T0") == "11"
      and RB.cell_n(_levels.get("P1"), "ARM=TREATED;TIMEPOINT=T3") == "9",
      "%s" % _levels)
check("  and a cell no group names, or a panel without groups' n, gets none",
      RB.cell_n(_levels.get("P1"), "ARM=OTHER;TIMEPOINT=T0") == ""
      and RB.cell_n(None, "ARM=CONTROL;TIMEPOINT=T0") == "")

OUT, SUMMARY = fresh_run("by_group", series_n=SERIES_N, unit_manifest=NO_UNIT_N)
QC = read(OUT, "figure_values_machine_qc.csv")
RAW = read(OUT, "figure_values_raw.csv")
check("a panel whose groups carry their n passes the gate with every cell",
      SUMMARY["status"] == "RAN" and len(QC) == 8, "%s / %d" % (SUMMARY, len(QC)))
check("  and each value carries its own group's n",
      all(r["N_Cell"] == ("11" if "ARM=CONTROL" in r["Cell_Key"] else "9")
          for r in QC.to_dict("records")), "%s" % QC[["Cell_Key", "N_Cell"]].to_dict("records"))
check("  and no value is refused for the unit's blank n",
      not any("MISSING_REQUIRED" in (c or "") for c in RAW["QC_Codes"]),
      "%s" % set(RAW["QC_Codes"]))
_stamp = json.load(open(os.path.join(OUT, "run_stamp.json"), encoding="utf-8"))
check("  and the file is hashed into the run's stamp",
      "series_n" in _stamp["Manifest_SHA256"], "%s" % sorted(_stamp["Manifest_SHA256"]))

_none, _sn = fresh_run("no_n", unit_manifest=NO_UNIT_N)
_raw = read(_none, "figure_values_raw.csv")
check("without a group's n or the unit's, every value still fails on the missing n",
      _sn["status"] == "RAN" and len(_raw) == 8
      and all("MISSING_REQUIRED" in c for c in _raw["QC_Codes"])
      and len(read(_none, "figure_values_machine_qc.csv")) == 0,
      "%s" % set(_raw["QC_Codes"]))
_one, _so = fresh_run("unit_n")
_qc1 = read(_one, "figure_values_machine_qc.csv")
check("a unit with its one n runs as before, with no cell n",
      len(_qc1) == 8 and set(_qc1["N_Cell"]) == {""}, "%d" % len(_qc1))
_bad, _sb = fresh_run("bad_n", series_n=SERIES_N[:1], unit_manifest=NO_UNIT_N)
check("a batch with a partial set of groups' n is refused before the run",
      _sb["status"] == "MANIFEST_REJECTED", "%s" % _sb)

# ==========================================================================
print()
print("the gate takes the cell's n in place of the unit's")
_fig = frame(FIGURES, GE.fig_figure_columns())
_grid = frame(GRIDS, GE.fig_grid_columns())


def _gate(values, units=NO_UNIT_N):
    qc = GE.fig_validate_bundle(_fig, _grid, frame(units, GE.fig_unit_columns()),
                                frame(values, GE.fig_values_columns(cell_n=True)),
                                kernel=RB.K, check_files=False)
    return qc


_base = [dict(r) for r in QC.to_dict("records")]
_q = _gate(_base)
check("every cell with its group's n: no n is missing",
      not any((p["check"] == "MISSING_REQUIRED" and "N_" in p["detail"])
              for p in _q.to_dict("records")), "%s" % _q.to_dict("records")[:3])
_hole = [dict(r) for r in _base]
_hole[0]["N_Cell"] = ""
_q = _gate(_hole)
check("one cell without its group's n, beside others with theirs, is missing its n",
      any(p["check"] == "MISSING_REQUIRED" and p["where"] == "values:2"
          for p in _q.to_dict("records")), "%s" % _q.to_dict("records")[:3])
_badv = [dict(r) for r in _base]
_badv[0]["N_Cell"] = "0"
check("a cell n that is not a positive whole number is refused",
      "N_INVALID" in set(_gate(_badv)["check"]))
check("a cell n beside the unit's own n is refused",
      "N_CELL_AND_UNIT_N" in set(_gate(_base, units=UNITS)["check"]))
check("a values file without the column is gated as before",
      "MISSING_REQUIRED" in set(GE.fig_validate_bundle(
          _fig, _grid, frame(NO_UNIT_N, GE.fig_unit_columns()),
          frame(_base, GE.fig_values_columns()), kernel=RB.K, check_files=False)["check"])
      and "SCHEMA_INCOMPLETE" not in set(GE.fig_validate_bundle(
          _fig, _grid, frame(UNITS, GE.fig_unit_columns()),
          frame(_base, GE.fig_values_columns()), kernel=RB.K, check_files=False)["check"]))
# The SE check reads the cell's n: an SE of 2 on a mean of 10 is an SD of 20 at
# n=100 (impossible on a symmetric ratio scale) and of 4 at n=4.
_se_units = [dict(NO_UNIT_N[0], Dispersion_Type="SE", Distribution_Shape="SYMMETRIC")]
_se = [dict(_base[0], Mean="10", Dispersion_Value="2", Errorbar_Lower="", Errorbar_Upper="",
            N_Cell=n_) for n_ in ("100", "4")]
_flags = [set(p["check"] for p in _gate([v], units=_se_units).to_dict("records")
              if p["where"] == "values:2") for v in _se]
check("the SE-implies-SD check uses the cell's own n",
      "SE_IMPLIES_HUGE_SD" in _flags[0] and "SE_IMPLIES_HUGE_SD" not in _flags[1],
      "%s" % _flags)

# ==========================================================================
print()
print("finalization re-gates with the cell's n, and the person is still the door")


def _review(out, **kw):
    row = dict(Review_ID="R001", Panel_ID="P1",
               Review_Subject_SHA256=read(out, "review_queue.csv").loc[0, "Review_Subject_SHA256"],
               Reviewer_ID="RV_H", Decision="APPROVED",
               Marks_Checked="CONFIRMED", Inference_Checked="CONFIRMED",
               Reviewed_At="2026-10-19T10:00:00Z", Note="")
    row.update(kw)
    path = os.path.join(out, "value_review.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FIN.value_review_columns())
        w.writerow([row.get(c, "") for c in FIN.value_review_columns()])
    return path


_fin = FIN.finalize(OUT, review_path=_review(OUT), run_date="2026-10-19",
                    today=datetime.date(2026, 10, 19))
_acc = (read(OUT, "figure_values_accepted.csv")
        if os.path.exists(os.path.join(OUT, "figure_values_accepted.csv")) else pd.DataFrame())
check("an approved panel whose groups carry their n is finalized whole",
      _fin["status"] == "FINALIZED" and len(_acc) == 8, "%s" % _fin)
check("  and the accepted values keep each group's n",
      len(_acc) == 8 and set(_acc["N_Cell"]) == {"11", "9"},
      "%s" % (set(_acc["N_Cell"]) if len(_acc) else None))
_ed, _ = fresh_run("edited_n", series_n=SERIES_N, unit_manifest=NO_UNIT_N)
_path = os.path.join(_ed, "manifests", "series_n.csv")
_rows = list(csv.DictReader(open(_path, encoding="utf-8")))
_rows[0]["N_Outcome"] = "30"
with open(_path, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=BM.series_n_columns())
    w.writeheader()
    w.writerows(_rows)
_fe = FIN.finalize(_ed, review_path=_review(_ed), run_date="2026-10-19",
                   today=datetime.date(2026, 10, 19))
check("a group's n edited after the run refuses the run",
      _fe["status"] != "FINALIZED"
      and "RUN_MANIFEST_MODIFIED" in {p["check"] for p in _fe["problems"]}, "%s" % _fe)
# A CANDIDATE WHOSE n IS NOT THE RAW FILE'S, with the run's stamp re-made so the
# artifact hash cannot be what catches it: the raw comparison must cover N_Cell.
_tq, _ = fresh_run("tampered_n", series_n=SERIES_N, unit_manifest=NO_UNIT_N)
_tq_path = os.path.join(_tq, "figure_values_machine_qc.csv")
_tq_frame = pd.read_csv(_tq_path, dtype=object).fillna("")
_tq_frame.loc[0, "N_Cell"] = "30"
_tq_frame.to_csv(_tq_path, index=False)
_tq_stamp_path = os.path.join(_tq, "run_stamp.json")
_tq_stamp = json.load(open(_tq_stamp_path, encoding="utf-8"))
_tq_stamp["Output_SHA256"]["figure_values_machine_qc.csv"] = RB.file_sha256(_tq_path)
with open(_tq_stamp_path, "w", encoding="utf-8") as fh:
    json.dump(_tq_stamp, fh, indent=1, sort_keys=True)
_tf = FIN.finalize(_tq, review_path=_review(_tq), run_date="2026-10-19",
                   today=datetime.date(2026, 10, 19))
check("a candidate whose group's n is not the raw file's is refused",
      _tf["status"] != "FINALIZED"
      and "MACHINE_QC_NOT_DERIVED_FROM_RAW" in {p["check"] for p in _tf["problems"]},
      "%s / %s" % (_tf["status"], sorted({p["check"] for p in _tf["problems"]})))

# ==========================================================================
print()
print("the plan carries each group's n to the manifest")
check("a group's n is a key a plan's series may carry",
      "n_outcome" in CP.PLAN_KEYS["series"] and "n_source" in CP.PLAN_KEYS["series"])
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
                "series": [{"series_id": sid, "factor": "ARM", "level": lv,
                            "n_outcome": n_, "n_source": "identity card (per series)"}
                           for sid, lv, n_ in (("S_B", "CONTROL", 11), ("S_R", "TREATED", 9))],
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
               "dispersion_type": "SD",
               "bar_top_definition": "NOT_A_BAR",
               "errorbar_stem_confirmed": "TRUE",
               "errorbar_source": "caption: mean +/- SD",
               "distribution_shape": "SYMMETRIC",
               "x_calibration": [[0, 149], [3, 449]]}],
}
_pdir = os.path.join(ROOT, "from_plan")
shutil.rmtree(_pdir, ignore_errors=True)
_written, _pp = CP.compile_plan(PLAN, os.path.join(_pdir, "manifests"),
                                file_root=ROOT, run_date="2026-10-19")
_sn_rows = (pd.read_csv(_written["series_n"], dtype=object).fillna("")
            if not _pp and "series_n" in _written else pd.DataFrame())
check("the compiler writes each group's n as series_n.csv",
      not _pp and len(_sn_rows) == 2
      and dict(zip(_sn_rows["Series_ID"], _sn_rows["N_Outcome"])) == {"S_B": "11", "S_R": "9"}
      and set(_sn_rows["N_Source"]) == {"identity card (per series)"},
      "%s / %s" % (_pp[:3], _sn_rows.to_dict("records") if len(_sn_rows) else None))
if not _pp:
    _ps = RB.run_batch(os.path.join(_pdir, "manifests"), _pdir, file_root=ROOT,
                       run_date="2026-10-19")
    _pq = (read(_pdir, "figure_values_machine_qc.csv") if _ps["status"] == "RAN"
           else pd.DataFrame())
    check("  and the batch compiled from it passes with each group's n on its cells",
          len(_pq) == 8 and set(_pq["N_Cell"]) == {"11", "9"}, "%s" % _ps)
else:
    check("  and the batch compiled from it passes with each group's n on its cells",
          False, "the plan did not compile")
_plain = json.loads(json.dumps(PLAN))
for _sp in _plain["figures"][0]["panels"][0]["read"]["series"]:
    _sp.pop("n_outcome")
    _sp.pop("n_source")
_plain["units"][0]["n_outcome"] = 10
_w2, _pp2 = CP.compile_plan(_plain, os.path.join(_pdir, "plain"), file_root=ROOT,
                            run_date="2026-10-19")
check("a plan with one n per unit writes the file with its header and no rows",
      not _pp2 and list(pd.read_csv(_w2["series_n"], dtype=object).columns)
      == BM.series_n_columns() and len(pd.read_csv(_w2["series_n"], dtype=object)) == 0,
      "%s" % _pp2[:3])

print()
print("FDT_SCENARIOS_RUN=%d" % len(RAN))
print("%d scenarios run" % len(RAN))
if FAILURES:
    print("FAILED: %s" % FAILURES)
    sys.exit(1)
print("all passed")
