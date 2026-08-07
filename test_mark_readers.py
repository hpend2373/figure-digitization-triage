"""Image-level regression tests for non-bar figure adapters.

Run through CSV-independent geometry first.  The grid engine remains the only
place that decides whether extracted cells are complete enough for master.
"""
from PIL import Image, ImageDraw
import itertools

from mark_readers import (AxisCalibration, SeriesSpec, read_line_marker_panel,
                          read_monochrome_marker_panel, read_scatter_panel,
                          summarize_association, read_box_violin_panel,
                          read_panel, to_value_records, MARK_CARRIED)


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
# A dispersion is a DIFFERENCE, so a constant pixel offset on both cap rows
# cancels in it and survives every mean-and-dispersion check. The bounds are
# absolute, and they are where the offset shows.
check("the error bar brackets its own mean",
      all(r["errorbar_lower"] <= r["mean"] <= r["errorbar_upper"] for r in rows),
      "%r" % [(r["errorbar_lower"], r["mean"], r["errorbar_upper"])
              for r in rows if not r["errorbar_lower"] <= r["mean"] <= r["errorbar_upper"]][:2])
_berr = max(max(abs(r["errorbar_lower"] - (r["mean"] - 5.0)),
                abs(r["errorbar_upper"] - (r["mean"] + 5.0))) for r in rows)
check("the bounds themselves land within 1 unit, not just their spread",
      _berr < 1.0, "max %.3f" % _berr)


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


print("two colour masks that claim the same marks say so")
import mark_readers as _MR  # noqa: E402
# A scatter's series identity is a colour claim, and two claims can cover the
# same pixel. Every such marker is then read twice, once into each series, and
# both associations are computed from a point set that includes the other's
# points. The reader is the only place this is visible - by the time the rows
# exist they look like ordinary points.
_near = [SeriesSpec("BLUE", rgb=(45, 80, 220), marker="CIRCLE", tolerance=140.0),
         SeriesSpec("NAVY", rgb=(40, 60, 190), marker="CIRCLE", tolerance=140.0)]
_ambiguous = read_scatter_panel(sim, panel_box=(70, 730, 40, 460),
                                x_calibration=sxcal, y_calibration=sycal,
                                series=_near)
check("a marker both masks cover is flagged on the point itself",
      all(p["mask_overlap"] >= 1 for p in _ambiguous) and len(_ambiguous) > 0,
      "%s" % [p.get("mask_overlap") for p in _ambiguous][:6])
check("and the overlap count reaches the audit",
      _MR.point_count_audit(
          [p for p in _ambiguous if p["series"] == "BLUE"],
          expected_n=len(struth))["Series_Mask_Overlap_Count"] == len(struth),
      "%r" % _MR.point_count_audit(
          [p for p in _ambiguous if p["series"] == "BLUE"], expected_n=len(struth)))
check("while two masks that cannot both be right about a pixel report nothing",
      all(p["mask_overlap"] == 0 for p in read_scatter_panel(
          sim, panel_box=(70, 730, 40, 460), x_calibration=sxcal,
          y_calibration=sycal,
          series=[SeriesSpec("BLUE", rgb=(45, 80, 220), marker="CIRCLE"),
                  SeriesSpec("RED", rgb=(215, 45, 45), marker="CIRCLE")])))


print("each statistic gets its own null distribution, not one shared one")
# Published two-sided Student-t critical values. The tail has to be the t's,
# because a normal one is what stood here for every statistic at once.
for _t, _df, _want in ((2.228, 10, 0.05), (3.169, 10, 0.01), (2.776, 4, 0.05),
                       (12.706, 1, 0.05), (1.960, 100000, 0.05)):
    _got = _MR.student_t_two_sided(_t, _df)
    check("t=%.3f on %d df is p=%.2f" % (_t, _df, _want),
          abs(_got - _want) < 5e-4, "got %.6f" % _got)
# The F tail is the same machinery, and for one predictor F = t^2.
check("the F tail agrees with the squared t it must equal",
      abs(_MR.snedecor_f_upper_tail(2.228 ** 2, 1, 10) - 0.05) < 5e-4,
      "%.6f" % _MR.snedecor_f_upper_tail(2.228 ** 2, 1, 10))

_lin = [dict(x_value=x, y_value=y, point_px_x=10.0 * x, point_px_y=10.0 * y,
             marker_area_px=20.0)
        for x, y in ((1, 2), (2, 3), (3, 5), (4, 4), (5, 8), (6, 9))]
_by_kind = {k: summarize_association(_lin, k)
            for k in ("PEARSON_R", "SPEARMAN_RHO", "R_SQUARED", "SLOPE")}
check("every statistic names the test that produced its p",
      [_by_kind[k]["P_Value_Method"] for k in
       ("PEARSON_R", "SPEARMAN_RHO", "R_SQUARED", "SLOPE")]
      == ["PEARSON_T_TEST", "SPEARMAN_T_APPROX", "R_SQUARED_F_TEST",
          "SLOPE_T_TEST"],
      "%s" % {k: v["P_Value_Method"] for k, v in _by_kind.items()})
check("no statistic is labelled with the shared approximation any more",
      "FISHER_Z_APPROX" not in {v["P_Value_Method"] for v in _by_kind.values()})
# The Pearson t and the Fisher z are not the same number on the ten-to-thirty
# points a digitized scatter has. n=6 here: 0.0053 against 0.0026 - a factor of
# two, in the direction that makes a result look stronger than it is.
_fisher = _MR._normal_p_from_r(_by_kind["PEARSON_R"]["Association_Value"], 6)
check("and the t is not the z it replaced",
      _by_kind["PEARSON_R"]["P_Value"] > 1.5 * _fisher,
      "t-test %.6f vs Fisher z %.6f" % (_by_kind["PEARSON_R"]["P_Value"], _fisher))
# The slope's t is computed from the regression's residual variance. For one
# predictor that equals the Pearson t, which is the check: two different
# derivations must land on the same number, or one of them is wrong.
_sx = np.array([p["x_value"] for p in _lin], dtype=float)
_sy = np.array([p["y_value"] for p in _lin], dtype=float)
_b, _a = np.polyfit(_sx, _sy, 1)
_sse = float(np.sum((_sy - (_b * _sx + _a)) ** 2))
_sxx = float(np.sum((_sx - _sx.mean()) ** 2))
_se_b = (_sse / (len(_sx) - 2) / _sxx) ** 0.5
_want_slope_p = _MR.student_t_two_sided(_b / _se_b, len(_sx) - 2)
check("the slope p comes from the regression's own residual variance",
      abs(_by_kind["SLOPE"]["P_Value"] - _want_slope_p) < 1e-12,
      "%r vs %r" % (_by_kind["SLOPE"]["P_Value"], _want_slope_p))
check("which for one predictor must land on the correlation t",
      abs(_by_kind["SLOPE"]["P_Value"] - _by_kind["PEARSON_R"]["P_Value"]) < 1e-12,
      "%r" % [_by_kind["SLOPE"]["P_Value"], _by_kind["PEARSON_R"]["P_Value"]])
check("and the R-squared F lands there too, under its own name",
      abs(_by_kind["R_SQUARED"]["P_Value"] - _by_kind["PEARSON_R"]["P_Value"]) < 1e-12,
      "%r" % [_by_kind["R_SQUARED"]["P_Value"], _by_kind["PEARSON_R"]["P_Value"]])
# A slope on a steeper y is a different slope with the same correlation, so the
# value must move while the p does not.
_steep = [dict(p, y_value=p["y_value"] * 3) for p in _lin]
check("the slope is the fitted slope, not the correlation",
      abs(summarize_association(_steep, "SLOPE")["Association_Value"]
          - 3 * _by_kind["SLOPE"]["Association_Value"]) < 1e-9)
_tied_spearman = summarize_association(
    [dict(x_value=x, y_value=y) for x, y in
     ((1, 2), (2, 2), (3, 5), (4, 5), (5, 8), (6, 9))], "SPEARMAN_RHO")
check("a tied Spearman refuses a p rather than using the untied one",
      _tied_spearman["P_Value"] is None
      and _tied_spearman["P_Value_Method"] == "SOURCE_P_REQUIRED_TIES"
      and _tied_spearman["Ties_Present"] == "TRUE",
      "%r" % _tied_spearman)


print("the point count is measured against the source, not declared by the reader")
_audit = _MR.point_count_audit(_lin, expected_n=6)
check("a clean cloud that matches the declared n says so",
      _audit["Point_Count_Agreement"] == "MATCH"
      and _audit["Detected_Unique_Point_Count"] == 6
      and _audit["Overplotting_Possible"] == "FALSE"
      and _audit["Series_Mask_Overlap_Count"] == 0, "%r" % _audit)
check("a source that declares more subjects than there are marks is FEWER_DETECTED",
      _MR.point_count_audit(_lin, expected_n=9)["Point_Count_Agreement"]
      == "FEWER_DETECTED")
check("and overplotting is the reading it gets",
      _MR.point_count_audit(_lin, expected_n=9)["Overplotting_Possible"] == "TRUE")
check("more marks than subjects is MORE_DETECTED",
      _MR.point_count_audit(_lin, expected_n=4)["Point_Count_Agreement"]
      == "MORE_DETECTED")
check("with no declared n the audit says so rather than agreeing with itself",
      _MR.point_count_audit(_lin)["Point_Count_Agreement"] == "NO_SOURCE_N")
# `int(float("10.5"))` is 10, so a malformed n quietly became a plausible one
# and the comparison then agreed with it. A sample size that has to be
# truncated to be used is not a sample size.
for _bad_n in ("10.5", "-6", "0", "twelve", float("nan")):
    check("a declared n of %r is not truncated into agreement" % _bad_n,
          _MR.point_count_audit(_lin, expected_n=_bad_n)["Point_Count_Agreement"]
          == "NO_SOURCE_N",
          "%r" % _MR.point_count_audit(_lin, expected_n=_bad_n))
check("while a whole number still counts, written either way",
      _MR.point_count_audit(_lin, expected_n="6")["Point_Count_Agreement"] == "MATCH"
      and _MR.point_count_audit(_lin, expected_n=6.0)["Point_Count_Agreement"] == "MATCH")
# Two contours a pixel apart are one printed marker split by a gridline. Counting
# both is how a ten-point figure becomes an eleven-pair correlation.
_split = _lin + [dict(_lin[0], point_px_x=_lin[0]["point_px_x"] + 1.0)]
check("two contours on one marker count once",
      _MR.point_count_audit(_split, expected_n=6)["Detected_Unique_Point_Count"] == 6
      and _MR.point_count_audit(_split, expected_n=6)["Overplotting_Possible"] == "TRUE",
      "%r" % _MR.point_count_audit(_split, expected_n=6))
_fat = [dict(p, marker_area_px=(120.0 if i == 0 else 20.0))
        for i, p in enumerate(_lin)]
check("a blob too big to be one marker is read as overplotting",
      _MR.point_count_audit(_fat, expected_n=6)["Overplotting_Possible"] == "TRUE",
      "%r" % _MR.point_count_audit(_fat, expected_n=6))
_claimed = [dict(p, mask_overlap=(1 if i < 2 else 0)) for i, p in enumerate(_lin)]
check("marks claimed by two series masks are counted",
      _MR.point_count_audit(_claimed, expected_n=6)["Series_Mask_Overlap_Count"] == 2)
_audited_record = to_value_records(
    [dict(summarize_association(_lin, "PEARSON_R"), **_audit)],
    "ASSOCIATION", "UA", cell_levels={"PANEL": "ALL"})[0]
check("and the whole audit reaches the value row",
      all(_audited_record.get(k) == _audit[k] for k in _audit), "%r" % _audited_record)


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
# Real reader output, not hand-written dicts: these carry the raw pixels, which
# is what makes the point file re-derivable rather than merely re-readable.
_scatter_path = _os.path.join(_e2e_dir, "scatter.png")
sim.save(_scatter_path)
_scatter_sha = _mr.sha256_of(_scatter_path)
points = spoints
summary = summarize_association(points, "KENDALL_TAU")
assert summary["Ties_Present"] == "FALSE" and summary["P_Value"] is not None, \
    "this fixture must be untied, or the p provenance is legitimately blank"
path = _mr.write_point_data(points, _os.path.join(_e2e_dir, "UA_points.json"),
                            unit_id="UA", cell_key="PANEL=ALL",
                            source_image=_scatter_path, image_sha256=_scatter_sha,
                            x_calibration=sxcal, y_calibration=sycal,
                            panel_id="P1", reader="SCATTER")
# Merged the way `_scatter_outcome` merges it: an association and the count it
# was computed from travel together, because the gate now refuses a digitized
# association that does not say how many marks it found.
record = to_value_records(
    [dict(summary, **_MR.point_count_audit(points, expected_n=len(points)))],
    "ASSOCIATION", "UA", cell_levels={"PANEL": "ALL"},
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
_tied_points = []
for _i, _v in enumerate((0, 1, 1, 3, 4, 6, 6, 8)):
    _px, _py = sxcal.value_to_pixel(_i), sycal.value_to_pixel(_v)
    _tied_points.append(dict(series="ALL", point_px_x=_px, point_px_y=_py,
                             x_value=sxcal.pixel_to_value(_px),
                             y_value=sycal.pixel_to_value(_py)))
_tied = summarize_association(_tied_points, "KENDALL_TAU")
_tied_path = _mr.write_point_data(_tied_points, _os.path.join(_e2e_dir, "UT_points.json"),
                                  unit_id="UT", cell_key="PANEL=ALL",
                                  source_image=_scatter_path, image_sha256=_scatter_sha,
                                  x_calibration=sxcal, y_calibration=sycal,
                                  panel_id="P1", reader="SCATTER")
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


print("a point file is re-derivable, not merely re-readable")
_pd = _mr.read_point_data(path)
check("the point file names its unit, cell and panel",
      (_pd["Unit_ID"], _pd["Cell_Key"], _pd["Panel_ID"]) == ("UA", "PANEL=ALL", "P1"),
      "%r" % _pd)
check("the point file records the image it was read off",
      _pd["Source_Image"] == _scatter_path and _pd["Image_SHA256"] == _scatter_sha)
check("the point file records the reader and its version",
      _pd["Reader"] == "SCATTER" and _pd["Reader_Version"] == _mr.READER_VERSION,
      "%r" % ((_pd["Reader"], _pd["Reader_Version"]),))
check("both calibrations are stored, not just the answers",
      _pd["X_Calibration"]["slope"] == sxcal.slope
      and _pd["Y_Calibration"]["intercept"] == sycal.intercept,
      "%r" % ((_pd["X_Calibration"], _pd["Y_Calibration"]),))
check("every point keeps its raw pixel and its series",
      all(p.get("point_px_x") is not None and p.get("point_px_y") is not None
          and p.get("series") == "ALL" for p in _pd["points"]),
      "%r" % _pd["points"][:2])
# The whole point of storing the pixel: the value can be recomputed and
# disagreed with. A file that only holds calibrated values agrees with itself
# no matter how wrong the calibration was.
_recomputed = [sycal.pixel_to_value(p["point_px_y"]) for p in _pd["points"]]
check("recomputing y from the stored pixel reproduces the stored value",
      max(abs(a - p["y_value"]) for a, p in zip(_recomputed, _pd["points"])) < 1e-9)
_orig_r = summarize_association(points, "PEARSON_R")["Association_Value"]
_reread = summarize_association(_pd["points"], "PEARSON_R")["Association_Value"]
check("the association recomputes from the file alone",
      abs(_orig_r - _reread) < 1e-12, "%.12f vs %.12f" % (_orig_r, _reread))

for _n, _kw, _frag in (
        ("no Unit_ID", dict(unit_id=""), "unit_id"),
        ("no Cell_Key", dict(cell_key=""), "cell_key"),
        ("no image hash", dict(image_sha256=""), "image_sha256"),
        ("no y calibration", dict(y_calibration=None), "y_calibration")):
    _args = dict(unit_id="UA", cell_key="PANEL=ALL", source_image=_scatter_path,
                 image_sha256=_scatter_sha, x_calibration=sxcal, y_calibration=sycal)
    _args.update(_kw)
    try:
        _mr.write_point_data(points, _os.path.join(_e2e_dir, "reject.json"), **_args)
        _msg = "accepted"
    except ValueError as exc:
        _msg = str(exc)
    check("a point file with %s is refused" % _n, _frag in _msg, _msg)
try:
    _mr.write_point_data([dict(x_value=1.0, y_value=2.0)],
                         _os.path.join(_e2e_dir, "reject.json"), unit_id="UA",
                         cell_key="PANEL=ALL", source_image=_scatter_path,
                         image_sha256=_scatter_sha, x_calibration=sxcal,
                         y_calibration=sycal)
    _msg = "accepted"
except ValueError as exc:
    _msg = str(exc)
check("a point with no raw pixel is refused", "point_px_x" in _msg, _msg)
_lying = [dict(p, y_value=p["y_value"] + 5.0) for p in points]
try:
    _mr.write_point_data(_lying, _os.path.join(_e2e_dir, "reject.json"), unit_id="UA",
                         cell_key="PANEL=ALL", source_image=_scatter_path,
                         image_sha256=_scatter_sha, x_calibration=sxcal,
                         y_calibration=sycal)
    _msg = "accepted"
except ValueError as exc:
    _msg = str(exc)
check("a value that does not follow from its own pixel is refused",
      "does not follow" in _msg, _msg)
import json as _json  # noqa: E402
_tampered = _os.path.join(_e2e_dir, "tampered.json")
_raw = _json.load(open(path))
_raw["points"][0]["y_value"] += 3.0
_json.dump(_raw, open(_tampered, "w"))
try:
    _mr.read_point_data(_tampered)
    _msg = "accepted"
except ValueError as exc:
    _msg = str(exc)
check("reading catches a point file edited after the fact",
      "does not follow" in _msg, _msg)
_old = _os.path.join(_e2e_dir, "old_schema.json")
_json.dump({"n_pairs": 2, "points": [{"x_value": 1, "y_value": 2}]}, open(_old, "w"))
try:
    _mr.read_point_data(_old)
    _msg = "accepted"
except ValueError as exc:
    _msg = str(exc)
check("a values-only point file from the old schema is refused",
      "schema" in _msg, _msg)


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


# ---------------------------------------------------------------------------
# mark-level provenance survives the adapter
# ---------------------------------------------------------------------------
# `to_value_records` copied mean, dispersion and bounds out of a reader row and
# dropped everything else, so `Errorbar_Stem_Confirmed` - which the readers
# produce per MARK - never reached a value. The gate then fell back to a single
# human-typed field on the unit manifest, and a panel with three confirmed
# whiskers and one unconfirmed passed on the strength of the three.
_rows = [dict(series="A", x_label="T0", mean=10.0, dispersion=1.0,
              errorbar_lower=9.0, errorbar_upper=11.0,
              Errorbar_Stem_Confirmed="TRUE", Bar_Top_Definition="OUTLINE_CENTER",
              Bar_Direction="UP", Position_Assignment="DECLARED_ANCHOR",
              calib_max_resid=0.25, slot_residual_px=1.5),
         dict(series="A", x_label="T1", mean=12.0, dispersion=1.2,
              errorbar_lower=10.8, errorbar_upper=13.2,
              Errorbar_Stem_Confirmed="FALSE", Bar_Top_Definition="OUTLINE_CENTER",
              Bar_Direction="UP", Position_Assignment="SEQUENTIAL",
              calib_max_resid=0.25, slot_residual_px=40.0)]
_recs = to_value_records(_rows, "CONTINUOUS", "U1", x_factor="TIMEPOINT",
                         series_factor="ARM")
check("every mark-level field the reader emitted reaches its value row",
      all(all(col in r for _src, col in MARK_CARRIED) for r in _recs),
      "%s" % sorted(_recs[0]))
check("and the two cells keep their own stem findings, not one shared answer",
      [r["Errorbar_Stem_Confirmed"] for r in _recs] == ["TRUE", "FALSE"],
      "%s" % [r.get("Errorbar_Stem_Confirmed") for r in _recs])
check("and their own slot residuals",
      [r["Slot_Assignment_Residual_Px"] for r in _recs] == [1.5, 40.0],
      "%s" % [r.get("Slot_Assignment_Residual_Px") for r in _recs])
check("and the position-assignment marker travels with the cell",
      [r["Position_Assignment"] for r in _recs] == ["DECLARED_ANCHOR", "SEQUENTIAL"],
      "%s" % [r.get("Position_Assignment") for r in _recs])
