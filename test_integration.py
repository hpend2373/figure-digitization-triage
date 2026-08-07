"""End-to-end gate: real template -> reader -> CSV round-trip -> validator.

    python test_integration.py      # exit 0 = all scenarios pass

test_kernel.py checks the validator against hand-built rows and test_bar_reader.py
checks the reader against rasters. Neither notices when the two disagree about
what the template contains - which is exactly how the Extraction_Method-gated
geometry checks came to pass in the suite and skip in production.

This module builds the CSV from fig_template_columns() and nothing else, fills it
from a real figure with bar_reader, round-trips it through disk, and runs the
validator. Nothing here may reference a column the template does not ship.
"""
import csv
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

import pandas as pd
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bar_reader import colour_masks, read_bar_panel, runs  # noqa: E402

spec = importlib.util.spec_from_file_location("fdt", os.path.join(HERE, "kernel.py"))
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)

FAILURES = []
PASSED = [0]
TMP = os.path.join(tempfile.gettempdir(), "fdt_integration.csv")
PHASE = {"B-1": "PRE", "DI7": "DURING", "DI14": "DURING", "DI19": "DURING",
         "R1": "RECOVERY", "R5": "RECOVERY"}
DAYS = {"B-1": -1, "DI7": 7, "DI14": 14, "DI19": 19, "R1": 22, "R5": 26}


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def emit_blank_template(path):
    cols = k.fig_template_columns()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(cols)
    return cols


def build_rows():
    """Read ID 323 Figure 1 and fill the shipped template."""
    cfg = json.load(open(os.path.join(HERE, "fixtures/id323_fig1_panels.json")))
    img = os.path.join(HERE, "fixtures/id323_fig1.jpeg")
    sha = hashlib.sha256(open(img, "rb").read()).hexdigest()
    masks = colour_masks(Image.open(img).convert("RGB"))
    dark = masks["dark"]
    cols = k.fig_template_columns()
    out = []
    for p in cfg["panels"]:
        x0, x1, y0, y1 = p["box"]
        sub = dark[y0:y1, x0:x1]
        ax = min(x0 + i for i, v in enumerate(sub.sum(axis=0)) if v > 0.6 * sub.shape[0])
        sl = dark[y0:y1, max(0, ax - 20):ax - 2]
        tr = [y0 + i for i, v in enumerate(sl) if v.sum() >= 2]
        cen = [round((r[0] + r[-1]) / 2, 1) for r in runs(tr, 4)]
        ticks = list(zip(p["tick_values"], cen))
        for b in read_bar_panel(masks, tuple(p["box"]), ticks, cfg["series"]):
            sess = cfg["sessions"][b["order"]]
            row = {c: "" for c in cols}
            row.update({
                "Publication_ID": cfg["publication_id"],
                "Source_File": cfg["source_file"],
                "Source_Page": cfg["source_page"],
                "Source_Image": os.path.basename(img),
                "Source_Caption_Verbatim": cfg["caption_verbatim"],
                "Figure_Number": "Figure 2", "Panel": p["name"],
                "Data_Shape": "B_CHALLENGE_2POINT",
                "Outcome_Variable": {"SAP": "Systolic blood pressure",
                                     "DAP": "Diastolic blood pressure",
                                     "MAP": "Mean arterial pressure",
                                     "PAP": "Pulse pressure",
                                     "HR": "Heart rate",
                                     "SV": "Stroke volume"}[p["name"]],
                "Outcome_Domain": "CV_HEMO", "Unit": p["unit"], "Arm": "ALL",
                "Posture_Condition": b["series"],
                "Exposure_Phase": PHASE[sess],
                "Timepoint_Label": sess, "Timepoint_Days": DAYS[sess],
                "Mean": round(b["mean"], 3),
                "Dispersion_Value": None if b["dispersion"] is None else round(b["dispersion"], 3),
                "Dispersion_Type": cfg["dispersion_type"],
                "Errorbar_Definition_Source": cfg["errorbar_definition_source"],
                "N_Outcome": cfg["n_outcome"],
                "Extraction_Method": "DIGITIZED",
                "Bar_Top_Definition": b["Bar_Top_Definition"],
                "Errorbar_Stem_Confirmed": b["Errorbar_Stem_Confirmed"],
                "Observed_Panel_Count": cfg["observed_panel_count"],
                "Worklist_Panel_Count": cfg["worklist_panel_count"],
                "Unlisted_Panels": cfg["unlisted_panels"],
                "Panel_Reconciliation_Status": "UNLISTED_PANELS_FOUND",
                "WPD_Project_File": "id323_fig1.tar",
                "Axis_X_Scale": "LINEAR", "Axis_Y_Scale": "LINEAR",
                "Axis_Calib_X1_Value": 0, "Axis_Calib_X1_Pixel": x0,
                "Axis_Calib_X2_Value": 1, "Axis_Calib_X2_Pixel": x1,
                "Axis_Calib_Y1_Value": ticks[-1][0], "Axis_Calib_Y1_Pixel": ticks[-1][1],
                "Axis_Calib_Y2_Value": ticks[0][0], "Axis_Calib_Y2_Pixel": ticks[0][1],
                "Image_Resolution_Or_Hash": "1950x1684 sha256:" + sha[:24],
                "Extractor_1": "bar_reader", "Date": "2026-08-06",
            })
            out.append(row)
    return cols, out


def run(rows, cols, drop=None):
    df = pd.DataFrame(rows, columns=[c for c in cols if c != drop])
    df.to_csv(TMP, index=False)
    p = k.fig_validate_extraction(pd.read_csv(TMP))
    return sorted(set(p["check"])) if len(p) else []


print("the shipped template is what gets filled")
cols = emit_blank_template(os.path.join(HERE, "figure_extraction_template_v7.csv"))
check("template emitted with %d columns" % len(cols), len(cols) == 52, "got %d" % len(cols))
check("Extraction_Method is in the emitted header", "Extraction_Method" in cols)

cols, rows = build_rows()
check("72 rows built from the real figure", len(rows) == 72, "got %d" % len(rows))
check("every filled key exists in the template",
      all(set(r) <= set(cols) for r in rows),
      str(sorted(set().union(*[set(r) - set(cols) for r in rows]))[:5]))

print("CSV round-trip through the validator")
# A genuine B grid is two phases x the same condition set. The published figure
# carries SIX sessions, so the two-phase subset is the part that is really B.
two_phase = [r for r in rows if r["Timepoint_Label"] in ("B-1", "R5")]
got = run(two_phase, cols)
check("a correctly filled 52-column template passes the gate", got == [],
      "problems: %s" % got)
check("the subset is the full condition grid", len(two_phase) == 24,
      "got %d rows" % len(two_phase))

# The worklist calls this figure B. Six sessions collapsing onto three phases put
# three rows in the DURING/SUPINE cell, and the validator says so - the shape
# assignment, not the extraction, is what is wrong.
full = run(rows, cols)
check("all six sessions declared as B raise B_DUPLICATE_CELL",
      "B_DUPLICATE_CELL" in full, "got %s" % full)

print("the new columns are load-bearing, not decorative")
check("dropping Extraction_Method fails the schema check",
      "SCHEMA_INCOMPLETE" in run(two_phase, cols, drop="Extraction_Method"))
for col, want in (("Bar_Top_Definition", "MISSING_BAR_TOP_DEFINITION"),
                  ("Errorbar_Stem_Confirmed", "ERRORBAR_STEM_UNCONFIRMED"),
                  ("Panel_Reconciliation_Status", "PANEL_RECONCILIATION_PENDING")):
    blanked = [dict(r, **{col: ""}) for r in two_phase]
    check("blanking %s raises %s" % (col, want), want in run(blanked, cols))
fill = [dict(r, Bar_Top_Definition="FILL_EDGE") for r in two_phase]
check("declaring FILL_EDGE raises the systematic-bias flag",
      "BAR_TOP_READ_AT_FILL_EDGE" in run(fill, cols))
bad = [dict(r, Panel_Reconciliation_Status="MATCHED") for r in two_phase]
check("6 observed vs 5 listed cannot be MATCHED",
      "PANEL_STATUS_CONTRADICTS_COUNTS" in run(bad, cols))
mixed = [dict(r, Observed_Panel_Count=(5 if i % 2 else 6),
              Worklist_Panel_Count=5,
              Panel_Reconciliation_Status=("MATCHED" if i % 2 else "UNLISTED_PANELS_FOUND"))
         for i, r in enumerate(two_phase)]
check("one figure cannot carry two panel counts",
      "PANEL_COUNT_INCONSISTENT_IN_FIGURE" in run(mixed, cols))

print("a placeholder dispersion definition cannot reach master")
for _txt in ("HARNESS PLACEHOLDER - unresolved", "TBD", "assumed SE"):
    ph = [dict(r, Errorbar_Definition_Source=_txt) for r in two_phase]
    check("placeholder %r is blocked end to end" % _txt[:22],
          "UNRESOLVED_ERRORBAR_DEFINITION" in run(ph, cols))
check("the real caption wording is quoted, not paraphrased",
      "Mean +/- SEM" in rows[0]["Errorbar_Definition_Source"]
      and rows[0]["Dispersion_Type"] == "SEM")
mixed_names = [dict(r, Unlisted_Panels=("PAP" if i % 2 else "MAP"))
               for i, r in enumerate(two_phase)]
check("one figure cannot name two different missing panels",
      "UNLISTED_PANELS_INCONSISTENT_IN_FIGURE" in run(mixed_names, cols))

if os.path.exists(TMP):
    os.remove(TMP)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
