"""Image-level regression tests for non-bar figure adapters.

Run through CSV-independent geometry first.  The grid engine remains the only
place that decides whether extracted cells are complete enough for master.
"""
from PIL import Image, ImageDraw
import itertools

from mark_readers import (AxisCalibration, SeriesSpec, read_line_marker_panel,
                          read_monochrome_marker_panel, read_scatter_panel,
                          summarize_association, read_box_violin_panel,
                          read_panel, to_value_records)


FAILURES = []
PASSED = 0


def check(name, ok, detail=""):
    global PASSED
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else " <- " + detail))
    if ok:
        PASSED += 1
    else:
        FAILURES.append(name)


def line_fixture():
    im = Image.new("RGB", (760, 480), "white")
    d = ImageDraw.Draw(im)
    xs = [140, 240, 340, 440, 540, 640]
    ycal = AxisCalibration.from_points([(0, 420), (100, 60)])
    truth = {
        "BLUE": [55, 62, 68, 64, 70, 76],
        # Keep the synthetic whiskers visually separable.  Occluded whiskers
        # are a manual-review condition, not something a reader can recover.
        "RED": [34, 39, 42, 46, 50, 55],
    }
    colors = {"BLUE": (45, 80, 220), "RED": (215, 45, 45)}
    for name, vals in truth.items():
        pts = [(x, ycal.value_to_pixel(v)) for x, v in zip(xs, vals)]
        d.line(pts, fill=colors[name], width=3)
        for x, y in pts:
            sd_px = abs(ycal.value_to_pixel(5) - ycal.value_to_pixel(0))
            d.line((x, y - sd_px, x, y + sd_px), fill=colors[name], width=2)
            d.line((x - 8, y - sd_px, x + 8, y - sd_px), fill=colors[name], width=2)
            d.line((x - 8, y + sd_px, x + 8, y + sd_px), fill=colors[name], width=2)
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=colors[name])
    return im, xs, ycal, truth


print("coloured line/marker time course")
im, xs, ycal, truth = line_fixture()
rows = read_line_marker_panel(
    im,
    panel_box=(100, 700, 40, 430),
    x_positions={f"T{i}": x for i, x in enumerate(xs)},
    y_calibration=ycal,
    series=[
        SeriesSpec("BLUE", rgb=(45, 80, 220), marker="CIRCLE"),
        SeriesSpec("RED", rgb=(215, 45, 45), marker="CIRCLE"),
    ],
)
check("all 12 marker values are found", len(rows) == 12, "got %d" % len(rows))
got = {(r["series"], r["x_label"]): r for r in rows}
err = [abs(got[(s, f"T{i}")]["mean"] - value)
       for s, values in truth.items() for i, value in enumerate(values)]
check("line means recover within 1 unit", max(err) < 1.0, "max %.3f" % max(err))
derr = [abs(abs(r["dispersion"]) - 5.0) for r in rows]
check("line error bars recover within 1 unit", max(derr) < 1.0,
      "max %.3f" % max(derr))
check("every line error bar has a connected stem",
      all(r["Errorbar_Stem_Confirmed"] == "TRUE" for r in rows))


def monochrome_fixture():
    im = Image.new("RGB", (760, 480), "white")
    d = ImageDraw.Draw(im)
    xs = [140, 240, 340, 440, 540, 640]
    ycal = AxisCalibration.from_points([(0, 420), (100, 60)])
    truth = {"CIRCLE": [68, 72, 66, 75, 71, 78],
             "TRIANGLE": [32, 38, 41, 45, 49, 53]}
    for name, vals in truth.items():
        pts = [(x, ycal.value_to_pixel(v)) for x, v in zip(xs, vals)]
        d.line(pts, fill="black", width=2)
        for x, y in pts:
            if name == "CIRCLE":
                d.ellipse((x - 6, y - 6, x + 6, y + 6), fill="black")
            else:
                d.polygon([(x, y - 7), (x - 7, y + 6), (x + 7, y + 6)], fill="black")
    return im, xs, ycal, truth


print("monochrome multi-series markers")
mim, mxs, mycal, mtruth = monochrome_fixture()
mrows = read_monochrome_marker_panel(
    mim,
    panel_box=(100, 700, 40, 430),
    x_positions={f"T{i}": x for i, x in enumerate(mxs)},
    y_calibration=mycal,
    series=[SeriesSpec("CIRCLE", marker="CIRCLE"),
            SeriesSpec("TRIANGLE", marker="TRIANGLE")],
)
check("all 12 monochrome markers are separated", len(mrows) == 12,
      "got %d" % len(mrows))
mgot = {(r["series"], r["x_label"]): r for r in mrows}
merr = [abs(mgot[(s, f"T{i}")]["mean"] - value)
        for s, values in mtruth.items() for i, value in enumerate(values)]
check("marker shape assigns the right black series", max(merr) < 1.2,
      "max %.3f" % max(merr))


def monochrome_open_filled_fixture():
    im = Image.new("RGB", (760, 520), "white")
    d = ImageDraw.Draw(im)
    xs = [140, 240, 340, 440, 540, 640]
    ycal = AxisCalibration.from_points([(0, 470), (100, 50)])
    truth = {
        "OPEN_CIRCLE": [84, 82, 80, 78, 76, 74],
        "FILLED_CIRCLE": [64, 62, 60, 58, 56, 54],
        "OPEN_TRIANGLE": [44, 42, 40, 38, 36, 34],
        "FILLED_TRIANGLE": [24, 22, 20, 18, 16, 14],
    }
    for name, vals in truth.items():
        pts = [(x, ycal.value_to_pixel(v)) for x, v in zip(xs, vals)]
        d.line(pts, fill="black", width=2)
        for x, y in pts:
            sd_px = abs(ycal.value_to_pixel(3) - ycal.value_to_pixel(0))
            d.line((x, y - sd_px, x, y + sd_px), fill="black", width=1)
            d.line((x - 5, y - sd_px, x + 5, y - sd_px), fill="black", width=1)
            d.line((x - 5, y + sd_px, x + 5, y + sd_px), fill="black", width=1)
            filled = name.startswith("FILLED")
            fill = "black" if filled else "white"
            if name.endswith("CIRCLE"):
                d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=fill,
                          outline="black", width=2)
            else:
                d.polygon([(x, y + 7), (x - 8, y - 6), (x + 8, y - 6)],
                          fill=fill, outline="black")
                if not filled:
                    d.line([(x, y + 7), (x - 8, y - 6), (x + 8, y - 6), (x, y + 7)],
                           fill="black", width=2)
    return im, xs, ycal, truth


print("open/filled monochrome marker identities")
ofim, ofxs, ofycal, oftruth = monochrome_open_filled_fixture()
ofrows = read_monochrome_marker_panel(
    ofim, panel_box=(100, 700, 40, 480),
    x_positions={f"T{i}": x for i, x in enumerate(ofxs)},
    y_calibration=ofycal,
    series=[SeriesSpec("OPEN_CIRCLE", marker="CIRCLE", fill="OPEN"),
            SeriesSpec("FILLED_CIRCLE", marker="CIRCLE", fill="FILLED"),
            SeriesSpec("OPEN_TRIANGLE", marker="TRIANGLE", fill="OPEN"),
            SeriesSpec("FILLED_TRIANGLE", marker="TRIANGLE", fill="FILLED")],
)
check("four monochrome series remain distinct", len(ofrows) == 24,
      "got %d" % len(ofrows))
ofgot = {(r["series"], r["x_label"]): r for r in ofrows}
oferr = [abs(ofgot[(s, f"T{i}")]["mean"] - value)
         for s, values in oftruth.items() for i, value in enumerate(values)]
check("open/filled markers map to the correct series", max(oferr) < 1.5,
      "max %.3f" % max(oferr))
check("monochrome error bars are recovered without using series colour",
      all(r["dispersion"] is not None and abs(r["dispersion"] - 3.0) < 1.0
          and r["Errorbar_Stem_Confirmed"] == "TRUE" for r in ofrows),
      "missing/wrong error bar on %d rows" % sum(
          r["dispersion"] is None or r["Errorbar_Stem_Confirmed"] != "TRUE"
          for r in ofrows))


def scatter_fixture():
    im = Image.new("RGB", (800, 520), "white")
    d = ImageDraw.Draw(im)
    xcal = AxisCalibration.from_points([(0, 80), (10, 720)])
    ycal = AxisCalibration.from_points([(0, 450), (20, 50)])
    xy = [(0.8, 3.0), (1.6, 4.2), (2.7, 7.1), (3.3, 6.8), (4.4, 9.6),
          (5.2, 11.8), (6.4, 12.1), (7.5, 15.5), (8.1, 15.1), (9.3, 18.4)]
    for x, y in xy:
        px, py = xcal.value_to_pixel(x), ycal.value_to_pixel(y)
        d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(45, 80, 220))
    return im, xcal, ycal, xy


print("scatter/association")
sim, sxcal, sycal, struth = scatter_fixture()
spoints = read_scatter_panel(
    sim, panel_box=(70, 730, 40, 460),
    x_calibration=sxcal, y_calibration=sycal,
    series=[SeriesSpec("ALL", rgb=(45, 80, 220), marker="CIRCLE")],
)
check("all scatter points are found", len(spoints) == len(struth),
      "got %d" % len(spoints))
spoints = sorted(spoints, key=lambda r: r["x_value"])
serr = max(max(abs(row["x_value"] - want[0]), abs(row["y_value"] - want[1]))
           for row, want in zip(spoints, struth))
check("scatter coordinates recover within 0.05 axis units", serr < 0.05,
      "max %.4f" % serr)
assoc = summarize_association(spoints, "PEARSON_R")
import numpy as np
truth_r = float(np.corrcoef([x for x, _ in struth], [y for _, y in struth])[0, 1])
check("Pearson r is calculated from the digitized points",
      abs(assoc["Association_Value"] - truth_r) < 2e-4,
      "%.6f vs %.6f" % (assoc["Association_Value"], truth_r))
check("association retains its pair count", assoc["N_Pairs"] == len(struth))
assoc_record = to_value_records(
    [assoc], "ASSOCIATION", "UA", cell_levels={"PANEL": "ALL"})[0]
check("association p-value method survives the common value adapter",
      assoc_record.get("P_Value_Method") == assoc.get("P_Value_Method"),
      "%r" % assoc_record)


def brute_kendall_two_sided_p(y):
    """Exact no-tie permutation p for a small regression fixture."""
    n = len(y)
    total_pairs = n * (n - 1) // 2
    inversions = lambda seq: sum(seq[i] > seq[j] for i in range(n) for j in range(i + 1, n))
    observed_s = total_pairs - 2 * inversions(y)
    null_s = [total_pairs - 2 * inversions(p) for p in itertools.permutations(range(n))]
    return sum(abs(s) >= abs(observed_s) for s in null_s) / len(null_s)


print("Kendall small-sample p values")
ky = (0, 2, 1, 4, 3)
kpoints = [dict(x_value=i, y_value=y) for i, y in enumerate(ky)]
kexact = summarize_association(kpoints, "KENDALL_TAU")
kexpected = brute_kendall_two_sided_p(ky)
check("no-tie Kendall uses the exact permutation distribution",
      kexact.get("P_Value_Method") == "KENDALL_EXACT_PERMUTATION"
      and abs(kexact["P_Value"] - kexpected) < 1e-12,
      "%r vs p=%g" % (kexact, kexpected))
small_exact_ok = True
for n in range(3, 8):
    probes = list(itertools.islice(itertools.permutations(range(n)), 0, 12))
    for perm in probes:
        result = summarize_association(
            [dict(x_value=i, y_value=y) for i, y in enumerate(perm)],
            "KENDALL_TAU")
        if abs(result["P_Value"] - brute_kendall_two_sided_p(perm)) > 1e-12:
            small_exact_ok = False
            break
check("exact Kendall agrees with brute permutations for n=3..7",
      small_exact_ok)
ktie = summarize_association(
    [dict(x_value=i, y_value=y) for i, y in enumerate((0, 1, 1, 3, 4))],
    "KENDALL_TAU")
check("tied Kendall does not invent an approximate p value",
      ktie["P_Value"] is None
      and ktie.get("P_Value_Method") == "SOURCE_P_REQUIRED_TIES",
      "%r" % ktie)


print("the association adapter carries every field the gate demands")
# The reader emitted the provenance fields and the validator required them, and
# to_value_records - the only thing between them - dropped three of the seven.
# Each half passed its own suite. This block is the join, so the drop cannot
# come back: reader -> adapter -> CSV columns -> validator, in one chain.
import os as _os  # noqa: E402
import tempfile as _tempfile  # noqa: E402
import mark_readers as _mr  # noqa: E402
import grid_engine as _ge  # noqa: E402
import kernel as _k  # noqa: E402

_e2e_dir = _tempfile.mkdtemp(prefix="fdt_e2e_")
points = [dict(x_value=float(i), y_value=float((i * 7) % 13)) for i in range(13)]
summary = summarize_association(points, "KENDALL_TAU")
assert summary["Ties_Present"] == "FALSE" and summary["P_Value"] is not None, \
    "this fixture must be untied, or the p provenance is legitimately blank"
path = _mr.write_point_data(points, _os.path.join(_e2e_dir, "UA_points.json"))
record = to_value_records([summary], "ASSOCIATION", "UA",
                          cell_levels={"PANEL": "ALL"},
                          point_data_reference=path)[0]
# The three asserts the review asked for, stated as asserts.
assert record["P_Value_Extraction_Method"], "adapter dropped P_Value_Extraction_Method"
assert record["Ties_Present"], "adapter dropped Ties_Present"
assert record["Point_Data_Reference"], "adapter dropped Point_Data_Reference"
check("the adapter carries P_Value_Extraction_Method", bool(record["P_Value_Extraction_Method"]))
check("the adapter carries Ties_Present", bool(record["Ties_Present"]))
check("the adapter carries Point_Data_Reference", bool(record["Point_Data_Reference"]))
check("the carried values are the reader's own, not defaults",
      record["P_Value_Extraction_Method"] == summary["P_Value_Extraction_Method"]
      and record["Ties_Present"] == summary["Ties_Present"], "%r" % record)
check("the point file the adapter names is really on disk",
      _os.path.exists(record["Point_Data_Reference"]))
_carried = set(_mr.ASSOCIATION_CARRIED)
check("every carried column exists in the values schema",
      _carried <= set(_ge.fig_values_columns()),
      "%s" % sorted(_carried - set(_ge.fig_values_columns())))
check("the adapter carries the whole declared set",
      _carried <= set(record), "%s" % sorted(_carried - set(record)))

# Straight into the validator, on a digitized unit, with nothing hand-filled.
import pandas as _pd  # noqa: E402


def _fr(rows, cols):
    return _pd.DataFrame([{c: d.get(c, "") for c in cols} for d in rows], columns=cols)


_e2e_img = _os.path.join(_e2e_dir, "f.png")
Image.new("RGB", (8, 6), "white").save(_e2e_img)
import hashlib as _hashlib  # noqa: E402
_e2e_sha = _hashlib.sha256(open(_e2e_img, "rb").read()).hexdigest()
_e2e_wpd = _os.path.join(_e2e_dir, "p.tar")
open(_e2e_wpd, "wb").write(b"placeholder")
_e2e_fig = [dict(Figure_ID="F1", Publication_ID=1, Figure_Number="FIG1",
                 Source_File="x.pdf", Source_Page=1, Source_Image=_e2e_img,
                 Source_Caption_Verbatim="cap",
                 Image_Resolution_Or_Hash="8x6 sha256:" + _e2e_sha,
                 WPD_Project_File=_e2e_wpd,
                 Observed_Panel_Count=1, Worklist_Panel_Count=1,
                 Panel_Reconciliation_Status="MATCHED", Unlisted_Panels="", Note="")]
_e2e_grid = [dict(Grid_ID="G1", Factor_Name="PANEL", Factor_Level="ALL",
                  Level_Order=0, Note="")]
_e2e_unit = [dict(Unit_ID="UA", Figure_ID="F1", Grid_ID="G1", Panel="A",
                  Outcome_Variable="Heart rate", Outcome_Domain="CV", Unit="bpm",
                  Statistic_Type="ASSOCIATION", Display_Hint="UNSPECIFIED",
                  Grid_Rule="FULL", Sparse_Justification="", N_Outcome=13,
                  Value_Scale="RATIO", Extraction_Method="DIGITIZED",
                  Bar_Top_Definition="NOT_A_BAR", Errorbar_Stem_Confirmed="NOT_A_BAR",
                  Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
                  Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=100,
                  Axis_Calib_X2_Value=1, Axis_Calib_X2_Pixel=400,
                  Axis_Calib_Y1_Value=0, Axis_Calib_Y1_Pixel=500,
                  Axis_Calib_Y2_Value=150, Axis_Calib_Y2_Pixel=100,
                  Extractor_1="r1", Extractor_2="", Independent_Verification_Status="",
                  Discrepancy_Note="", Date="2026-08-06", Note="")]


def _gate(value_row):
    p = _ge.fig_validate_bundle(_fr(_e2e_fig, _ge.fig_figure_columns()),
                                _fr(_e2e_grid, _ge.fig_grid_columns()),
                                _fr(_e2e_unit, _ge.fig_unit_columns()),
                                _fr([value_row], _ge.fig_values_columns()),
                                kernel=_k, file_root=_e2e_dir)
    return sorted(set(p["check"])) if len(p) else []


_e2e_codes = _gate(record)
check("a reader-built association row clears the gate untouched",
      _e2e_codes == [], "%s" % _e2e_codes)
_bad = _gate(dict(record, Point_Data_Reference=""))
check("and the same row without its points does not",
      "MISSING_POINT_DATA_REFERENCE" in _bad, "%s" % _bad)
for _drop, _want in (("P_Value_Extraction_Method", "MISSING_P_VALUE_PROVENANCE"),
                     ("Ties_Present", "MISSING_TIES_PRESENT")):
    _g = _gate(dict(record, **{_drop: ""}))
    check("dropping %s in transit raises %s" % (_drop, _want), _want in _g, "%s" % _g)

# A tied Kendall has no computed p, so P_Value_Extraction_Method is legitimately
# blank - but the tie claim and the points are exactly what make that legitimate,
# so those two must still arrive.
_tied_points = [dict(x_value=float(i), y_value=float(v))
                for i, v in enumerate((0, 1, 1, 3, 4, 6, 6, 8))]
_tied = summarize_association(_tied_points, "KENDALL_TAU")
_tied_path = _mr.write_point_data(_tied_points, _os.path.join(_e2e_dir, "UT_points.json"))
_tied_rec = to_value_records([_tied], "ASSOCIATION", "UT",
                             cell_levels={"PANEL": "ALL"},
                             point_data_reference=_tied_path)[0]
check("a tied Kendall still carries its tie claim and its points",
      _tied_rec["Ties_Present"] == "TRUE" and _tied_rec["Point_Data_Reference"] == _tied_path
      and _tied_rec["P_Value_Method"] == "SOURCE_P_REQUIRED_TIES", "%r" % _tied_rec)
check("a blank p carries a blank provenance, not a fabricated one",
      _tied_rec["P_Value"] is None and _tied_rec["P_Value_Extraction_Method"] == "",
      "%r" % _tied_rec)
_row_path = to_value_records([dict(_tied, Point_Data_Reference="/from/the/row.json")],
                             "ASSOCIATION", "UT", cell_levels={"PANEL": "ALL"},
                             point_data_reference=_tied_path)[0]
check("a path already on the reader row wins over the adapter default",
      _row_path["Point_Data_Reference"] == "/from/the/row.json",
      "%r" % _row_path["Point_Data_Reference"])


print("single-colour scatter and association families")
black = Image.new("RGB", (800, 520), "white")
bd = ImageDraw.Draw(black)
for x, y in struth:
    px, py = sxcal.value_to_pixel(x), sycal.value_to_pixel(y)
    bd.ellipse((px - 5, py - 5, px + 5, py + 5), fill="black")
bpoints = read_scatter_panel(
    black, panel_box=(70, 730, 40, 460),
    x_calibration=sxcal, y_calibration=sycal,
    series=[SeriesSpec("ALL", rgb=None, marker="CIRCLE")],
)
check("a single black scatter series is extractable", len(bpoints) == len(struth),
      "got %d" % len(bpoints))
for association_type in ("SPEARMAN_RHO", "KENDALL_TAU", "R_SQUARED", "SLOPE"):
    try:
        summary = summarize_association(spoints, association_type)
        association_ok = (summary["Association_Type"] == association_type
                          and summary["N_Pairs"] == len(struth)
                          and np.isfinite(summary["Association_Value"]))
    except (ValueError, KeyError):
        association_ok = False
    check("%s is calculated from preserved points" % association_type,
          association_ok)


def box_violin_fixture(with_summary=True):
    im = Image.new("RGB", (800, 520), "white")
    d = ImageDraw.Draw(im)
    ycal = AxisCalibration.from_points([(0, 450), (100, 50)])
    xs = [200, 400, 600]
    truth = [(15, 30, 44, 61, 82), (10, 24, 38, 55, 76), (20, 36, 52, 68, 90)]
    for x, (lo, q1, med, q3, hi) in zip(xs, truth):
        ys = [ycal.value_to_pixel(v) for v in (lo, q1, med, q3, hi)]
        # Pale violin silhouette; the black internal box carries the extractable
        # numerical summary.
        poly = [(x, ys[4]), (x - 28, (ys[4] + ys[3]) / 2),
                (x - 40, (ys[3] + ys[1]) / 2), (x - 22, (ys[1] + ys[0]) / 2),
                (x, ys[0]), (x + 22, (ys[1] + ys[0]) / 2),
                (x + 40, (ys[3] + ys[1]) / 2), (x + 28, (ys[4] + ys[3]) / 2)]
        d.polygon(poly, fill=(215, 215, 230), outline=(170, 170, 185))
        if with_summary:
            ylo, yq1, ymed, yq3, yhi = ys
            d.line((x, yhi, x, ylo), fill="black", width=2)
            d.line((x - 7, yhi, x + 7, yhi), fill="black", width=2)
            d.line((x - 7, ylo, x + 7, ylo), fill="black", width=2)
            d.rectangle((x - 13, yq3, x + 13, yq1), outline="black", width=2)
            d.line((x - 13, ymed, x + 13, ymed), fill="black", width=2)
    return im, xs, ycal, truth


print("box/violin quantile summaries")
bim, bxs, bycal, btruth = box_violin_fixture(True)
brows = read_box_violin_panel(
    bim, panel_box=(120, 680, 40, 460),
    x_positions={f"G{i}": x for i, x in enumerate(bxs)},
    y_calibration=bycal,
)
check("three box summaries are found", len(brows) == 3, "got %d" % len(brows))
berr = []
for row, want in zip(brows, btruth):
    got5 = [row[k] for k in ("whisker_lower", "q1", "median", "q3", "whisker_upper")]
    berr.extend(abs(a - b) for a, b in zip(got5, want))
check("median, quartiles and whiskers recover within 1 unit", max(berr) < 1.0,
      "max %.3f" % max(berr))
vim, vxs, vycal, _ = box_violin_fixture(False)
vrows = read_box_violin_panel(
    vim, panel_box=(120, 680, 40, 460),
    x_positions={f"G{i}": x for i, x in enumerate(vxs)},
    y_calibration=vycal,
)
check("a pure violin does not invent quartiles", vrows == [])


print("one adapter contract feeds the four-grain value table")
routed = read_panel(
    "LINE_COLOR", image=im, panel_box=(100, 700, 40, 430),
    x_positions={f"T{i}": x for i, x in enumerate(xs)},
    y_calibration=ycal,
    series=[SeriesSpec("BLUE", rgb=(45, 80, 220), marker="CIRCLE"),
            SeriesSpec("RED", rgb=(215, 45, 45), marker="CIRCLE")],
)
records = to_value_records(routed, "CONTINUOUS", "U1",
                           x_factor="TIMEPOINT", series_factor="ARM")
check("line adapter emits twelve unique grid records",
      len(records) == 12 and len({r["Cell_Key"] for r in records}) == 12)
check("line records carry mean and dispersion",
      all(r["Mean"] is not None and r["Dispersion_Value"] is not None for r in records))
qrecords = to_value_records(brows, "QUANTILE_SUMMARY", "UQ",
                            x_factor="ARM", series_factor=None)
check("box adapter preserves median and quartiles in the common value schema",
      len(qrecords) == 3 and all(r["Q1"] < r["Median"] < r["Q3"] for r in qrecords))
try:
    read_panel("MAGIC_UNKNOWN_MARK", image=im)
    bad_mark_rejected = False
except ValueError:
    bad_mark_rejected = True
check("unknown mark types fail closed", bad_mark_rejected)


print()
print("%d scenarios run" % (PASSED + len(FAILURES)))
if FAILURES:
    raise SystemExit("%d FAILED: %s" % (len(FAILURES), FAILURES))
print("all scenarios passed")
