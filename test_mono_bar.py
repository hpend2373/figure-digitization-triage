"""Regression suite for the monochrome grouped-bar reader.

    python3 test_mono_bar.py       # exit 0 = all scenarios pass

Black-and-white bar charts name their series by FILL PATTERN. The reader that
handles them is the last one this project was missing, and it repeats every
mistake the colour reader made unless it is stopped from doing so - so the
fixture draws each trap on purpose and the scenarios below measure the cost of
getting it wrong, rather than asserting the current answer is the right one.
"""
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_mono_bar_fixture as FIX      # noqa: E402
import mark_readers as MR                # noqa: E402
import batch_manifests as BM             # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


IMG = os.path.join(HERE, "mono_bar_fixture.png")
TRUTH = os.path.join(HERE, "mono_bar_fixture_truth.json")
COLLIDE = os.path.join(HERE, "mono_bar_fixture_collide.png")
COLLIDE_TRUTH = os.path.join(HERE, "mono_bar_fixture_collide_truth.json")
for _p, _t, _c in ((IMG, TRUTH, None), (COLLIDE, COLLIDE_TRUTH, "T2")):
    if not os.path.exists(_p):
        FIX.draw(_p, _t, collide_group=_c)

SERIES_OF = {"S_SOLID": "SOLID", "S_HATCH": "HATCHED", "S_OPEN": "OPEN"}
SPECS = [MR.SeriesSpec("S_SOLID", bar_fill="SOLID"),
         MR.SeriesSpec("S_HATCH", bar_fill="HATCHED"),
         MR.SeriesSpec("S_OPEN", bar_fill="OPEN")]


def read(path, truth_path, **kw):
    truth = json.load(open(truth_path))
    cal = MR.AxisCalibration.from_points([(v, p) for v, p in truth["y_ticks"]])
    rows = MR.read_monochrome_bar_panel(
        Image.open(path), panel_box=tuple(truth["panel_box"]),
        x_positions=dict(zip(truth["groups"], truth["group_x"])),
        y_calibration=cal, series=SPECS, **kw)
    return rows, truth


print("three printed fills, told apart without any colour")
rows, truth = read(IMG, TRUTH)
check("all twelve bars are read", len(rows) == 12, "got %d" % len(rows))
check("each series is named by its own fill pattern",
      all(r["fill_pattern"] == SERIES_OF[r["series"]] for r in rows),
      "%r" % [(r["series"], r["fill_pattern"]) for r in rows][:3])
check("no cell is claimed twice",
      len({(r["series"], r["x_label"]) for r in rows}) == 12)

want = truth["series"]
_merr = max(abs(r["mean"] - want[SERIES_OF[r["series"]]][r["x_label"]]["mean"])
            for r in rows)
check("means recover within 1 unit on a 100-unit axis", _merr < 1.0,
      "max %.3f" % _merr)
_derr = max(abs(r["dispersion"] - want[SERIES_OF[r["series"]]][r["x_label"]]["dispersion"])
            for r in rows if r["dispersion"] is not None)
check("dispersions recover within 1 unit", _derr < 1.0, "max %.3f" % _derr)
check("every bar reports a stem-confirmed error bar",
      all(r["Errorbar_Stem_Confirmed"] == "TRUE" for r in rows))
check("the bar coordinate is declared as the outline centre",
      all(r["Bar_Top_Definition"] == "OUTLINE_CENTER" for r in rows))
check("every bar is read as growing away from the baseline",
      all(r["Bar_Direction"] == "UP" for r in rows),
      "%r" % sorted({r["Bar_Direction"] for r in rows}))
_bands = {p: (min(r["fill_density"] for r in rows if r["fill_pattern"] == p),
              max(r["fill_density"] for r in rows if r["fill_pattern"] == p))
          for p in ("OPEN", "HATCHED", "SOLID")}
check("the three fills land in bands that do not touch",
      _bands["OPEN"][1] < _bands["HATCHED"][0]
      and _bands["HATCHED"][1] < _bands["SOLID"][0], "%r" % _bands)
check("and the gaps between them are wide, not marginal",
      min(_bands["HATCHED"][0] - _bands["OPEN"][1],
          _bands["SOLID"][0] - _bands["HATCHED"][1]) > 0.2, "%r" % _bands)


print("the significance glyph does not become the error bar")
# T1 and T2 carry a glyph floating above the SOLID bar's cap, in the same black.
# If the reader reached for the topmost dark mark, those two dispersions would
# be visibly larger than the other two of the same series.
_solid = {r["x_label"]: r["dispersion"] for r in rows if r["series"] == "S_SOLID"}
_glyph = [_solid[g] for g in FIX.GLYPH_GROUPS]
_clean = [_solid[g] for g in _solid if g not in FIX.GLYPH_GROUPS]
check("a bar with a glyph reports the same dispersion as one without",
      max(_glyph) - min(_clean) < 0.5, "glyph %r vs clean %r" % (_glyph, _clean))


print("the error-bar cap is not mistaken for the bar itself")
# Measured at the primitive, on the isolated column of one drawn bar, because
# that is where the two rules differ. A cap is drawn about 70% of the bar width,
# which clears a "half the slot" test - so the whisker tip becomes the value.
import cv2  # noqa: E402
import numpy as np  # noqa: E402

_gray = cv2.cvtColor(np.asarray(Image.open(IMG).convert("RGB")).astype(np.uint8),
                     cv2.COLOR_RGB2GRAY)
_dark = _gray < 128
_x0, _x1, _y0, _y1 = truth["panel_box"]
_cal = MR.AxisCalibration.from_points([(v, p) for v, p in truth["y_ticks"]])
_zero_rel = _cal.value_to_pixel(0) - _y0
_span = len(FIX.PATTERNS) * FIX.BAR_W + (len(FIX.PATTERNS) - 1) * FIX.GAP
_walk_err, _naive_err = [], []
for _g, _gx in zip(truth["groups"], truth["group_x"]):
    _left = _gx - _span // 2                       # the SOLID bar of this group
    _col = _dark[_y0:_y1, _left:_left + FIX.BAR_W]
    _true = FIX.to_pixel(want["SOLID"][_g]["mean"]) - _y0
    for _rule, _acc in (("BASELINE_WALK", _walk_err), ("FIRST_WIDE_ROW", _naive_err)):
        _got = MR._mono_bar_extent(_col, _zero_rel, edge_rule=_rule)
        _acc.append(abs(_got[0] - _true) if _got else float("nan"))
_px_per_unit = abs(FIX.to_pixel(1) - FIX.to_pixel(0))
check("the first-wide-row rule really does read the cap",
      min(_naive_err) > 3.0 * _px_per_unit,
      "the trap did not fire: errors %r px - the fixture no longer draws it"
      % [round(e, 1) for e in _naive_err])
_sd_px = abs(FIX.to_pixel(FIX.SD["SOLID"]) - FIX.to_pixel(0))
_naive_by_group = dict(zip(truth["groups"], _naive_err))
_clean_naive = [e for g, e in _naive_by_group.items() if g not in FIX.GLYPH_GROUPS]
_glyph_naive = [e for g, e in _naive_by_group.items() if g in FIX.GLYPH_GROUPS]
check("on a plain bar it lands on the cap, one SD high",
      all(abs(e - _sd_px) < 2.0 for e in _clean_naive),
      "%r px against an SD of %.1f px"
      % ([round(e, 1) for e in _clean_naive], _sd_px))
# The two traps compound: where a significance glyph sits above the cap, the
# naive rule does not stop at the cap either. One wrong rule, two magnitudes of
# error, and nothing in the output says which one happened.
check("on a bar carrying a glyph it goes higher still",
      min(_glyph_naive) > max(_clean_naive) + 5.0,
      "glyph %r vs plain %r px" % ([round(e, 1) for e in _glyph_naive],
                                   [round(e, 1) for e in _clean_naive]))
check("the baseline walk lands on the drawn bar instead",
      max(_walk_err) <= 2.0,
      "walk %r px vs first-wide-row %r px"
      % ([round(e, 1) for e in _walk_err], [round(e, 1) for e in _naive_err]))
check("stated in axis units, the naive rule costs at least a whole SD",
      min(_naive_err) / _px_per_unit > 0.9 * FIX.SD["SOLID"],
      "%.2f-%.2f units against SD %.1f"
      % (min(_naive_err) / _px_per_unit, max(_naive_err) / _px_per_unit,
         FIX.SD["SOLID"]))


print("a group that cannot be told apart produces nothing")
_crows, _ctruth = read(COLLIDE, COLLIDE_TRUTH)
check("the readable groups still read", len(_crows) == 9, "got %d" % len(_crows))
check("the colliding group contributes no cell at all",
      not any(r["x_label"] == "T2" for r in _crows),
      "%r" % sorted({r["x_label"] for r in _crows}))
check("and nothing shifted to fill the hole - the other groups keep their labels",
      {r["x_label"] for r in _crows} == {"T0", "T1", "T3"},
      "%r" % sorted({r["x_label"] for r in _crows}))
_cerr = max(abs(r["mean"] - _ctruth["series"][SERIES_OF[r["series"]]][r["x_label"]]["mean"])
            for r in _crows)
check("the surviving groups are unaffected by the ambiguous one", _cerr < 1.0,
      "max %.3f" % _cerr)


print("a series declaration the reader cannot act on is refused")
for _name, _specs, _frag in (
        ("a bar series with no fill pattern",
         [MR.SeriesSpec("A"), MR.SeriesSpec("B", bar_fill="SOLID")], "bar_fill"),
        ("a fill pattern outside the vocabulary",
         [MR.SeriesSpec("A", bar_fill="STRIPED"),
          MR.SeriesSpec("B", bar_fill="SOLID")], "bar_fill"),
        ("two series sharing one pattern",
         [MR.SeriesSpec("A", bar_fill="SOLID"),
          MR.SeriesSpec("B", bar_fill="SOLID")], "share a fill pattern")):
    _t = json.load(open(TRUTH))
    _cal = MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]])
    try:
        MR.read_monochrome_bar_panel(
            Image.open(IMG), panel_box=tuple(_t["panel_box"]),
            x_positions=dict(zip(_t["groups"], _t["group_x"])),
            y_calibration=_cal, series=_specs)
        _msg = "accepted"
    except ValueError as exc:
        _msg = str(exc)
    check("%s is refused" % _name, _frag in _msg, _msg)

check("BAR_MONO routes through the common dispatcher",
      len(MR.read_panel(
          "BAR_MONO", image=Image.open(IMG),
          panel_box=tuple(truth["panel_box"]),
          x_positions=dict(zip(truth["groups"], truth["group_x"])),
          y_calibration=MR.AxisCalibration.from_points(
              [(v, p) for v, p in truth["y_ticks"]]),
          series=SPECS)) == 12)
check("and the adapter turns its rows into grid cells",
      len(MR.to_value_records(rows, "CONTINUOUS", "U1", x_factor="TIMEPOINT",
                              series_factor="ARM")) == 12)
check("BAR_MONO is in the declared mark vocabulary", "BAR_MONO" in MR.MARK_TYPES)

# A manifest must be able to say what publication 127 prints. If STIPPLED is not
# in the vocabulary, whoever writes that manifest has to declare the nearest
# lie - HATCHED, on a fill reading 0.15 against hatching's 0.26-0.32 - and a lie
# in the manifest is the one error the QC layer cannot catch, because every
# check downstream agrees with it. So the word is declarable, and the reader
# refuses it by name instead of banding it.
#
# REVERT: remove STIPPLED from UNIMPLEMENTED_FILL_PATTERNS. The declaration is
# accepted, classify_bar_fill has no band for it, and the bar is assigned to
# whichever band it lands in - silently, and on 127 that band is HATCHED.
print()
print("a fill the manifest can declare and the reader cannot read")
check("STIPPLED is in the manifest vocabulary",
      "STIPPLED" in BM.BAR_FILL_PATTERNS, repr(BM.BAR_FILL_PATTERNS))
check("and in the reader's, so a spec carrying it parses",
      "STIPPLED" in MR.BAR_FILL_PATTERNS, repr(MR.BAR_FILL_PATTERNS))
check("but the reader has no band for it and says so",
      "STIPPLED" in MR.UNIMPLEMENTED_FILL_PATTERNS,
      repr(MR.UNIMPLEMENTED_FILL_PATTERNS))
_refused = ""
try:
    _truth = json.load(open(TRUTH))
    MR.read_monochrome_bar_panel(
        Image.open(IMG), panel_box=tuple(_truth["panel_box"]),
        x_positions=dict(zip(_truth["groups"], _truth["group_x"])),
        y_calibration=MR.AxisCalibration.from_points(
            [(v, p) for v, p in _truth["y_ticks"]]),
        series=[MR.SeriesSpec("S_STIPPLE", bar_fill="STIPPLED")])
except ValueError as exc:
    _refused = str(exc)
check("reading a STIPPLED series raises rather than guessing",
      "cannot read it" in _refused, repr(_refused[:80]))
check("and the refusal names the panel and the pattern",
      "S_STIPPLE" in _refused and "STIPPLED" in _refused, repr(_refused[:80]))
check("no other declared fill is refused",
      not [p for p in MR.BAR_FILL_PATTERNS
           if p != "STIPPLED" and p in MR.UNIMPLEMENTED_FILL_PATTERNS])

print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
