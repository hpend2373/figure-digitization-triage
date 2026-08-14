"""Regression suite for the monochrome grouped-bar reader.

    python3 test_mono_bar.py       # exit 0 = all scenarios pass

Black-and-white bar charts name their series by FILL PATTERN. The reader that
handles them is the last one this project was missing, and it repeats every
mistake the colour reader made unless it is stopped from doing so - so the
fixture draws each trap on purpose and the scenarios below measure the cost of
getting it wrong, rather than asserting the current answer is the right one.
"""
import inspect
import json
import os
import sys

import numpy as np
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

# v7.70: IT DOES NOT, AND IT SAYS SO. This scenario used to assert that
# `read_panel("BAR_MONO", ...)` returns twelve rows - which it did, from the
# single-panel absolute-band reader, while the pipeline read the same panel in two
# passes through `mono_bar_geometry` and got a different fill vocabulary and an
# identity route. A common dispatcher that answers differently from the pipeline
# is worse than one that refuses: the caller cannot tell.
try:
    MR.read_panel(
        "BAR_MONO", image=Image.open(IMG),
        panel_box=tuple(truth["panel_box"]),
        x_positions=dict(zip(truth["groups"], truth["group_x"])),
        y_calibration=MR.AxisCalibration.from_points(
            [(v, p) for v, p in truth["y_ticks"]]),
        series=SPECS)
    _dispatch = "it returned rows"
except MR.UnsupportedCapabilityError as exc:
    _dispatch = str(exc)
check("BAR_MONO refuses the common dispatcher rather than answering differently",
      "two passes" in _dispatch and "fill_identities_by_figure" in _dispatch,
      _dispatch)
check("  and the single-panel reader still reads this panel, under its own name",
      len(MR.read_monochrome_bar_panel(
          Image.open(IMG), panel_box=tuple(truth["panel_box"]),
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
_refused, _kind = "", None
try:
    _truth = json.load(open(TRUTH))
    MR.read_monochrome_bar_panel(
        Image.open(IMG), panel_box=tuple(_truth["panel_box"]),
        x_positions=dict(zip(_truth["groups"], _truth["group_x"])),
        y_calibration=MR.AxisCalibration.from_points(
            [(v, p) for v, p in _truth["y_ticks"]]),
        series=[MR.SeriesSpec("S_STIPPLE", bar_fill="STIPPLED")])
except Exception as exc:                                        # noqa: BLE001
    _refused, _kind = str(exc), type(exc)
check("reading a STIPPLED series raises rather than guessing",
      "cannot read it" in _refused, repr(_refused[:80]))
# The TYPE decides the run state: run_batch maps UnsupportedCapabilityError to
# NO_READER_AVAILABLE and ValueError to PANEL_GEOMETRY_UNRESOLVED, so a plain
# ValueError here would file "no STIPPLED reader" as "this panel's geometry
# cannot be trusted". test_run_batch.py asserts the state end to end.
check("and raises the capability error, not a geometry one",
      _kind is MR.UnsupportedCapabilityError, repr(_kind))
check("and the refusal names the panel and the pattern",
      "S_STIPPLE" in _refused and "STIPPLED" in _refused, repr(_refused[:80]))
check("no other declared fill is refused",
      not [p for p in MR.BAR_FILL_PATTERNS
           if p != "STIPPLED" and p in MR.UNIMPLEMENTED_FILL_PATTERNS])

# The two-pass entry point: the production module measuring a panel WITHOUT
# naming its series. The existing reader has to decide identity inside one
# panel, and the only evidence a panel holds is an absolute density against
# _FILL_BANDS - measured on one figure and wrong on the second. This one leaves
# the identity open for fill_identities_by_figure, which needs every panel of
# the figure before it can say anything.
#
# REVERT: have it return `series` per row like the old reader. The rows look
# richer and every one of them is a series named by where the bar sat.
print()
print("the production module can measure a panel without naming its series")
_t = json.load(open(TRUTH))
_geo = MR.read_monochrome_bar_geometry(
    Image.open(IMG), tuple(_t["panel_box"]),
    dict(zip(_t["groups"], _t["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]]),
    _t["patterns"], group_window=60, panel_id="P_MONO", identity_domain_id="F_MONO")
_cells = [r for r in _geo if r.get("slot") is not None]
check("it reads every bar the fixture draws", len(_cells) == 12,
      "%d" % len(_cells))
check("and gets their means", all("value" in r for r in _cells),
      "%s" % [r.get("error") for r in _cells if "value" not in r])
check("no row carries a series name",
      not [r for r in _cells if r.get("series") or r.get("resolved_fill_pattern")],
      "%s" % [(r.get("slot"), r.get("resolved_fill_pattern")) for r in _cells][:3])
check("every row says its identity is not calibrated yet",
      all(r.get("identity_status") == "NOT_CALIBRATED" for r in _cells),
      "%s" % {r.get("identity_status") for r in _cells})
check("the panel and figure it belongs to travel with each row",
      all(r.get("figure") == "P_MONO" and r.get("identity_domain_id") == "F_MONO"
          for r in _cells))
_v = MR.MONO_GEOMETRY.fill_identities_by_figure(_geo)
check("and the figure names them once every panel has been measured",
      _v["F_MONO"]["status"] == "ESTABLISHED"
      and all(r["resolved_fill_pattern"] == _t["patterns"][r["slot"]]
              for r in _cells),
      "%s" % _v["F_MONO"]["status"])
check("the reader measures with the shared geometry, not a copy of it",
      MR.read_monochrome_bar_geometry.__globals__["MONO_GEOMETRY"].geometry_rows
      is MR.MONO_GEOMETRY.geometry_rows)

# The grain the whole design turns on, exercised through the PRODUCTION wrapper
# rather than the prototype driver: geometry is per PANEL and identity is per
# FIGURE. One panel of one group can name its own bars from the relations inside
# them and nothing more, because every prototype range it produces has zero
# width. Two panels of the same figure have a spread, and only then are the
# ranges reusable.
#
# REVERT: pool by panel instead of by identity_domain_id (drop the identity_domain_id bucketing in
# fill_identities_by_figure). Each panel then answers alone, all three come back
# DIRECT_ONLY, and publication 127's two unnameable bars stay unnameable - the
# figure never gets the chance to be more than the sum of its panels. REVERT the
# other way - pool everything handed in - and the third panel below, which is a
# different publication, calibrates the same vocabulary.
print()
print("geometry is per panel, identity is per figure, and the two do not mix")
_cal_f = MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]])


def _one_group(group, panel_id, identity_domain_id):
    return MR.read_monochrome_bar_geometry(
        Image.open(IMG), tuple(_t["panel_box"]),
        {group: dict(zip(_t["groups"], _t["group_x"]))[group]},
        _cal_f, _t["patterns"], group_window=60,
        panel_id=panel_id, identity_domain_id=identity_domain_id)


_pA = _one_group("T0", "P_A", "FIG_ONE")
_pB = _one_group("T1", "P_B", "FIG_ONE")
_pC = _one_group("T2", "P_C", "FIG_TWO")     # a different publication entirely
_alone = MR.MONO_GEOMETRY.fill_identities_by_figure([dict(r) for r in _pA])
check("one panel of one group names its own bars and claims nothing more",
      _alone["FIG_ONE"]["status"] == "DIRECT_ONLY"
      and not _alone["FIG_ONE"]["prototype_ready"],
      repr(_alone["FIG_ONE"]["status"]))
_pair = [dict(r) for r in _pA] + [dict(r) for r in _pB]
_both = MR.MONO_GEOMETRY.fill_identities_by_figure(_pair)
check("two panels of the same figure make the vocabulary reusable",
      _both["FIG_ONE"]["status"] == "ESTABLISHED"
      and _both["FIG_ONE"]["complete_groups"] == 2,
      "%r over %r groups" % (_both["FIG_ONE"]["status"],
                             _both["FIG_ONE"]["complete_groups"]))
check("and all six of their bars are named",
      sum(r.get("identity_status") == "RESOLVED" for r in _pair) == 6,
      repr([r.get("identity_status") for r in _pair]))
_mixed = ([dict(r) for r in _pA] + [dict(r) for r in _pB]
          + [dict(r) for r in _pC])
_split = MR.MONO_GEOMETRY.fill_identities_by_figure(_mixed)
check("a panel of another figure is answered separately",
      set(_split) == {"FIG_ONE", "FIG_TWO"}, repr(sorted(_split)))
check("and it never joins the first figure's vocabulary",
      _split["FIG_ONE"]["complete_groups"] == 2
      and _split["FIG_TWO"]["complete_groups"] == 1
      and _split["FIG_TWO"]["status"] == "DIRECT_ONLY",
      repr({k: (v["status"], v["complete_groups"]) for k, v in _split.items()}))
check("nor does mixing them change what the first figure says",
      _split["FIG_ONE"]["prototypes"] == _both["FIG_ONE"]["prototypes"],
      "%r against %r" % (_split["FIG_ONE"]["prototypes"],
                         _both["FIG_ONE"]["prototypes"]))

# REVERT: give panel_id and identity_domain_id a default of "". The suite still passes -
# every scenario above supplies them - and a caller that forgets gets one
# figure bucket named "" holding every panel it has measured. Those panels then
# calibrate a SHARED fill vocabulary, so two publications pool into one. That is
# not a crash; it is a plausible answer computed from the wrong figure, and the
# only place it would ever be noticed is a value in a meta-analysis.
print()
print("the panel and the figure have to be named, and named for real")
_kw = dict(image=Image.open(IMG), panel_box=tuple(_t["panel_box"]),
           x_positions=dict(zip(_t["groups"], _t["group_x"])),
           y_calibration=MR.AxisCalibration.from_points(
               [(v, p) for v, p in _t["y_ticks"]]),
           fills=_t["patterns"], group_window=60)
_sig = inspect.signature(MR.read_monochrome_bar_geometry)
check("both are keyword-only and neither has a default",
      all(_sig.parameters[n].kind is inspect.Parameter.KEYWORD_ONLY
          and _sig.parameters[n].default is inspect.Parameter.empty
          for n in ("panel_id", "identity_domain_id")),
      repr([(n, str(_sig.parameters[n])) for n in ("panel_id", "identity_domain_id")]))
for _missing in ("panel_id", "identity_domain_id"):
    _args = dict(_kw, panel_id="P", identity_domain_id="F")
    _args.pop(_missing)
    try:
        MR.read_monochrome_bar_geometry(**_args)
    except TypeError as exc:
        check("omitting %s is a TypeError, not a nameless figure" % _missing,
              _missing in str(exc), str(exc))
    else:
        check("omitting %s is a TypeError, not a nameless figure" % _missing,
              False, "it returned rows")
for _blank in ("", "   "):
    for _which in ("panel_id", "identity_domain_id"):
        _args = dict(_kw, panel_id="P", identity_domain_id="F")
        _args[_which] = _blank
        try:
            MR.read_monochrome_bar_geometry(**_args)
        except ValueError as exc:
            check("a blank %s is refused as loudly as a missing one" % _which,
                  _which in str(exc), str(exc))
        else:
            check("a blank %s is refused as loudly as a missing one" % _which,
                  False, "it returned rows")

# REVERT: call image.convert("RGB") unconditionally. A caller holding the array
# this package works in internally - which is what every function in
# mono_bar_geometry takes - has to wrap it back into a PIL Image to hand it over.
print()
print("the reader takes the array it hands out, as well as an Image")
_rgb = np.asarray(Image.open(IMG).convert("RGB")).astype(np.uint8)
# A FRESH read from the Image, because `_geo` above was handed to
# fill_identities_by_figure and carries the names it wrote.
_from_image = MR.read_monochrome_bar_geometry(
    Image.open(IMG), tuple(_t["panel_box"]),
    dict(zip(_t["groups"], _t["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]]),
    _t["patterns"], group_window=60, panel_id="P_MONO", identity_domain_id="F_MONO")
_from_array = MR.read_monochrome_bar_geometry(
    _rgb, tuple(_t["panel_box"]), dict(zip(_t["groups"], _t["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]]),
    _t["patterns"], group_window=60, panel_id="P_MONO", identity_domain_id="F_MONO")
check("an RGB ndarray reads exactly what the Image reads",
      _from_array == _from_image,
      "%d rows against %d" % (len(_from_array), len(_from_image)))
_from_gray = MR.read_monochrome_bar_geometry(
    MR.MONO_GEOMETRY._gray_from_rgb(_rgb), tuple(_t["panel_box"]),
    dict(zip(_t["groups"], _t["group_x"])),
    MR.AxisCalibration.from_points([(v, p) for v, p in _t["y_ticks"]]),
    _t["patterns"], group_window=60, panel_id="P_MONO", identity_domain_id="F_MONO")
check("and a 2-D greyscale array is taken as greyscale, not re-converted",
      _from_gray == _from_image,
      "%d rows against %d" % (len(_from_gray), len(_from_image)))

print()
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
