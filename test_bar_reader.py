"""Image-level regression suite for bar_reader.

    python test_bar_reader.py        # exit 0 = all scenarios pass

Every scenario corresponds to a defect found while digitizing real figures.
Unlike test_kernel.py, which checks a filled CSV, these run the reader against
actual rasters: a synthetic chart whose true values are known exactly, and a
frozen real figure (ID 323 Figure 1, six panels, 72 bars).

Scenario count is printed at the end; do not hard-code it in prose.
"""
import json
import math
import os
import sys
import hashlib
import statistics as S

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bar_reader import colour_masks, read_bar_panel, runs  # noqa: E402
from mark_readers import AxisCalibration                     # noqa: E402

FAILURES = []
PX_PER_UNIT = 440.0 / 150.0          # synthetic fixture: axis span / value span


_PASSED = [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        _PASSED[0] += 1
    else:
        FAILURES.append(name)


def anchors_of(cfg):
    """Declared x pixel per session: the centre of the group, as a manifest
    would record it. Not derived from what the reader found - that is the whole
    point of the change these tests cover."""
    by_session = {}
    for b in cfg["bars"]:
        by_session.setdefault(b["session"], []).append(b["x_pixel"])
    return {s: sum(v) / len(v) for s, v in by_session.items()}


def read_fixture(img, meta, stem_required=True, image=None, x_positions=None,
                 declared=True):
    cfg = json.load(open(os.path.join(HERE, meta)))
    im = image or Image.open(os.path.join(HERE, img)).convert("RGB")
    m = colour_masks(im)
    bars = read_bar_panel(m, tuple(cfg["panel_box"]), cfg["ticks"],
                          {"SUPINE": "blue", "ORTHOSTASIS": "red"},
                          stem_required=stem_required,
                          x_positions=(x_positions if x_positions is not None
                                       else (anchors_of(cfg) if declared else None)))
    order_of = {s: i for i, s in enumerate(sorted(
        anchors_of(cfg), key=lambda k: anchors_of(cfg)[k]))}
    for b in bars:
        if b.get("x_label") is not None:
            b["order"] = order_of[b["x_label"]]
    truth = {(b["series"], b["order"]): b for b in cfg["bars"]}
    return bars, truth


# ---------------------------------------------------------------- synthetic
print("synthetic chart with a stroked outline and significance glyphs")
bars, truth = read_fixture("bar_fixture.png", "bar_fixture_truth.json")
check("every bar is found", len(bars) == 12, "got %d" % len(bars))

err_outline = [b["mean"] - truth[(b["series"], b["order"])]["true_mean"] for b in bars]
err_fill = [b["mean_if_read_at_fill_edge"] - truth[(b["series"], b["order"])]["true_mean"]
            for b in bars]
check("OUTLINE_CENTER recovers every true mean within 2 px",
      max(map(abs, err_outline)) < 2.0 / PX_PER_UNIT,
      "max|err| %.3f" % max(map(abs, err_outline)))
check("reading the colour fill is biased in ONE direction (systematic, not noise)",
      all(e < 0 for e in err_fill), "signs %s" % sorted(set(int(e > 0) for e in err_fill)))
check("the fill-edge bias is at least 3x the outline-centre error",
      abs(S.mean(err_fill)) > 3 * abs(S.mean(err_outline)),
      "fill %.3f vs outline %.3f" % (S.mean(err_fill), S.mean(err_outline)))

err_disp = [(b["dispersion"] or 0) - truth[(b["series"], b["order"])]["true_sd"] for b in bars]
check("dispersion recovered within 1 unit", max(map(abs, err_disp)) < 1.0,
      "max|err| %.3f" % max(map(abs, err_disp)))
check("every whisker is stem-confirmed",
      all(b["Errorbar_Stem_Confirmed"] == "TRUE" for b in bars))
check("Bar_Top_Definition is reported for every bar",
      all(b["Bar_Top_Definition"] == "OUTLINE_CENTER" for b in bars))

print("significance glyphs must not be read as error-bar caps")
clean, ctruth = read_fixture("bar_fixture_noglyph.png", "bar_fixture_noglyph_truth.json")
gm = {(b["series"], b["order"]): b for b in bars}
cm = {(b["series"], b["order"]): b for b in clean}
dmean = max(abs(gm[k]["mean"] - cm[k]["mean"]) for k in gm)
ddisp = max(abs((gm[k]["dispersion"] or 0) - (cm[k]["dispersion"] or 0)) for k in gm)
check("glyphs change no mean", dmean < 1e-9, "max delta %.4f" % dmean)
check("glyphs change no dispersion", ddisp < 1e-9, "max delta %.4f" % ddisp)

# Prove the trap is real rather than asserting the fixed reader happens to work.
naive, _ = read_fixture("bar_fixture.png", "bar_fixture_truth.json", stem_required=False)
nerr = [(b["dispersion"] or 0) - truth[(b["series"], b["order"])]["true_sd"] for b in naive]
_mean_true_sd = S.mean([t["true_sd"] for t in truth.values()])
check("without the stem rule the glyph inflates dispersion by >3x the true SD",
      S.mean(nerr) > 3 * _mean_true_sd,
      "naive bias %+.2f vs 3x mean true SD %.2f (fixed bias %+.2f)"
      % (S.mean(nerr), 3 * _mean_true_sd, S.mean(err_disp)))
naive_clean, _ = read_fixture("bar_fixture_noglyph.png", "bar_fixture_noglyph_truth.json",
                              stem_required=False)
nce = [(b["dispersion"] or 0) - ctruth[(b["series"], b["order"])]["true_sd"] for b in naive_clean]
check("on a glyph-free chart the stem rule changes nothing (no false positives)",
      abs(S.mean(nce) - S.mean(err_disp)) < 0.05,
      "naive %.3f vs fixed %.3f" % (S.mean(nce), S.mean(err_disp)))


print("bars are read from the end away from the baseline")
sm = json.load(open(os.path.join(HERE, "bar_fixture_signed_truth.json")))
sbars, struth = read_fixture("bar_fixture_signed.png", "bar_fixture_signed_truth.json")
check("every signed bar is found", len(sbars) == 12, "got %d" % len(sbars))
check("the panel really carries both directions",
      {b["Bar_Direction"] for b in sbars} == {"UP", "DOWN"},
      str({b["Bar_Direction"] for b in sbars}))
check("direction is right on every bar",
      all(b["Bar_Direction"] == struth[(b["series"], b["order"])]["direction"] for b in sbars),
      str([(b["series"], b["order"], b["Bar_Direction"]) for b in sbars
           if b["Bar_Direction"] != struth[(b["series"], b["order"])]["direction"]]))
serr = [b["mean"] - struth[(b["series"], b["order"])]["true_mean"] for b in sbars]
check("signed means recovered within 0.5 unit", max(map(abs, serr)) < 0.5,
      "max|err| %.3f" % max(map(abs, serr)))
# The whisker points AWAY from zero, so the raw difference is negative on a down
# bar. `dispersion` is the MAGNITUDE, because that is what the grid gate
# accepts and what a meta-analysis weights by; the direction lives in
# `Bar_Direction` and the raw difference in `dispersion_signed`. Emitting the
# signed value as `dispersion` meant a correctly-read down bar was rejected
# downstream by DISPERSION_NONPOSITIVE - two components, each with a passing
# test, asserting opposite contracts.
sdisp = [(b["dispersion"] or 0) - struth[(b["series"], b["order"])]["true_sd"]
         for b in sbars]
check("dispersions recovered within 0.5 unit", max(map(abs, sdisp)) < 0.5,
      "max|err| %.3f" % max(map(abs, sdisp)))
check("dispersion is a magnitude, whichever way the bar points",
      all((b["dispersion"] or 0) > 0 for b in sbars),
      "%s" % [(b["Bar_Direction"], b["dispersion"]) for b in sbars
              if (b["dispersion"] or 0) <= 0])
check("and the sign the reader saw is kept, in the field whose job that is",
      all((b["dispersion_signed"] or 0) < 0
          for b in sbars if b["Bar_Direction"] == "DOWN")
      and all((b["dispersion_signed"] or 0) > 0
              for b in sbars if b["Bar_Direction"] == "UP"),
      "%s" % [(b["Bar_Direction"], b["dispersion_signed"]) for b in sbars])

# A bar thinner than its own stroke has no colour fill. The reader cannot see it,
# which is a known limit - and the grid engine is what catches the hole.
vbars, vtruth = read_fixture("bar_fixture_vanishing.png", "bar_fixture_vanishing_truth.json")
check("a bar thinner than its outline is dropped, not guessed",
      len(vbars) == 1 and len(vtruth) == 2, "read %d of %d" % (len(vbars), len(vtruth)))


# ------------------------------------------------------------ real fixture
print("frozen real figure - ID 323 Figure 1, six panels")
cfg = json.load(open(os.path.join(HERE, "fixtures/id323_fig1_panels.json")))
exp = json.load(open(os.path.join(HERE, "fixtures/id323_fig1_expected.json")))
img = os.path.join(HERE, "fixtures/id323_fig1.jpeg")
sha = hashlib.sha256(open(img, "rb").read()).hexdigest()
check("fixture image is the one the expected values were read from",
      sha == exp["image_sha256"], sha[:16])

masks = colour_masks(Image.open(img).convert("RGB"))
dark = masks["dark"]


def find_ticks(box, n):
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    h = sub.shape[0]
    ax = min(x0 + i for i, v in enumerate(sub.sum(axis=0)) if v > 0.6 * h)
    sl = dark[y0:y1, max(0, ax - 20):ax - 2]
    tr = [y0 + i for i, v in enumerate(sl) if v.sum() >= 2]
    return [round((r[0] + r[-1]) / 2, 1) for r in runs(tr, 4)]


got = {}
for p in cfg["panels"]:
    cen = find_ticks(p["box"], len(p["tick_values"]))
    check("%s: all %d y ticks detected" % (p["name"], len(p["tick_values"])),
          len(cen) == len(p["tick_values"]), "got %d" % len(cen))
    if len(cen) != len(p["tick_values"]):
        continue
    bars = read_bar_panel(masks, tuple(p["box"]), list(zip(p["tick_values"], cen)),
                          cfg["series"])
    check("%s: 12 bars (6 sessions x 2 conditions)" % p["name"], len(bars) == 12,
          "got %d" % len(bars))
    check("%s: calibration residual under 0.2 units" % p["name"],
          bars and bars[0]["calib_max_resid"] < 0.2,
          "%.3f" % (bars[0]["calib_max_resid"] if bars else -1))
    for b in bars:
        got[(p["name"], b["series"], cfg["sessions"][b["order"]])] = b

dm = dd = 0.0
for row in exp["values"]:
    b = got.get((row["panel"], row["series"], row["session"]))
    if b is None:
        check("missing bar %s/%s/%s" % (row["panel"], row["series"], row["session"]), False)
        continue
    dm = max(dm, abs(b["mean"] - row["mean"]))
    if row["dispersion"] is not None and b["dispersion"] is not None:
        dd = max(dd, abs(b["dispersion"] - row["dispersion"]))
# The frozen values are stored to 3 dp, so half of the last digit is the exact
# tolerance: anything larger is a real change in the reader, not rounding.
TOL = 5e-4
check("all 72 means reproduce the frozen values", dm <= TOL, "max delta %.6f" % dm)
check("all 72 dispersions reproduce the frozen values", dd <= TOL, "max delta %.6f" % dd)
check("every bar of the real figure is stem-confirmed",
      all(b["Errorbar_Stem_Confirmed"] == "TRUE" for b in got.values()))
check("PAP is present on screen although the worklist omitted it",
      any(k[0] == "PAP" for k in got) and cfg["unlisted_panels"] == "PAP")
check("observed panel count exceeds the worklist count",
      cfg["observed_panel_count"] > cfg["worklist_panel_count"])

print()

# ---------------------------------------------------- declared anchors, not pitch
print("a bar goes to the position the manifest declared, or to none")
# The slot code used to rebuild its own spacing: global min/max of the detected
# bars for the pitch, each series' own leftmost bar for the origin. Two silent
# failures followed. A series whose FIRST bar was invisible had every later bar
# shifted one label left. And when a whole slot went undetected the derived
# pitch collapsed - 123 px to 108 px on this fixture - so a real slot-4 bar came
# out labelled slot 5. Both produce small residuals, so a residual gate could
# not have caught either.
_cfg = json.load(open(os.path.join(HERE, "bar_fixture_signed_truth.json")))
_ANCHORS = anchors_of(_cfg)
_BY_X = sorted(_ANCHORS, key=lambda k: _ANCHORS[k])


def erase(bar_filter):
    """The signed fixture with some bars painted out, as printing can do."""
    im = Image.open(os.path.join(HERE, "bar_fixture_signed.png")).convert("RGB")
    d = ImageDraw.Draw(im)
    for b in _cfg["bars"]:
        if bar_filter(b):
            d.rectangle((b["x_pixel"] - 30, _cfg["panel_box"][2],
                         b["x_pixel"] + 30, _cfg["panel_box"][3]), fill="white")
    return im


_first_gone = erase(lambda b: b["series"] == "SUPINE" and b["order"] == 0)
_bars, _ = read_fixture("bar_fixture_signed.png", "bar_fixture_signed_truth.json",
                        image=_first_gone)
_labels = {(b["series"], b["x_label"]) for b in _bars}
check("a series whose first bar is invisible keeps every other label",
      all(("SUPINE", _BY_X[i]) in _labels for i in range(1, len(_BY_X))),
      "%s" % sorted(l for s, l in _labels if s == "SUPINE"))
check("and the hole is at the position that really is empty",
      ("SUPINE", _BY_X[0]) not in _labels,
      "%s" % sorted(l for s, l in _labels if s == "SUPINE"))
check("and the other series is untouched",
      len([b for b in _bars if b["series"] == "ORTHOSTASIS"]) == len(_BY_X),
      "%d" % len([b for b in _bars if b["series"] == "ORTHOSTASIS"]))

_slot_gone = erase(lambda b: b["order"] == len(_BY_X) - 1)
_bars2, _ = read_fixture("bar_fixture_signed.png", "bar_fixture_signed_truth.json",
                         image=_slot_gone)
_l2 = {(b["series"], b["x_label"]) for b in _bars2}
check("a whole slot going missing does not renumber the ones before it",
      all((s, _BY_X[i]) in _l2 for s in ("SUPINE", "ORTHOSTASIS")
          for i in range(len(_BY_X) - 1)),
      "%s" % sorted(_l2))
check("and the missing slot is simply absent",
      not any(l == _BY_X[-1] for _, l in _l2), "%s" % sorted(_l2))

_mid_gone = erase(lambda b: b["order"] == 2)
_bars3, _ = read_fixture("bar_fixture_signed.png", "bar_fixture_signed_truth.json",
                         image=_mid_gone)
_l3 = {(b["series"], b["x_label"]) for b in _bars3}
check("a middle slot going missing leaves a hole, not a shift",
      all((s, _BY_X[i]) in _l3 for s in ("SUPINE", "ORTHOSTASIS")
          for i in (0, 1, 3, 4, 5))
      and not any(l == _BY_X[2] for _, l in _l3), "%s" % sorted(_l3))

_far = read_bar_panel(
    colour_masks(Image.open(os.path.join(HERE, "bar_fixture_signed.png")).convert("RGB")),
    tuple(_cfg["panel_box"]), _cfg["ticks"],
    {"SUPINE": "blue", "ORTHOSTASIS": "red"},
    x_positions={"ELSEWHERE": _cfg["panel_box"][0] + 5}, slot_tolerance_px=8)
check("a bar near no declared anchor is dropped, not snapped to the nearest",
      _far == [], "%s" % [(b["series"], b["x_label"]) for b in _far])

_seq = read_bar_panel(
    colour_masks(Image.open(os.path.join(HERE, "bar_fixture_signed.png")).convert("RGB")),
    tuple(_cfg["panel_box"]), _cfg["ticks"],
    {"SUPINE": "blue", "ORTHOSTASIS": "red"})
check("counting bars off left to right is still possible but says so",
      _seq and all(b["Position_Assignment"] == "SEQUENTIAL" for b in _seq),
      "%s" % sorted({b.get("Position_Assignment") for b in _seq}))
check("while a declared reading is labelled as declared",
      all(b["Position_Assignment"] == "DECLARED_ANCHOR" for b in _bars),
      "%s" % sorted({b.get("Position_Assignment") for b in _bars}))


# ---------------------------------------------------------------- a log y axis
print("a colour bar on a log axis reads as a log axis")
# The manifest has allowed Axis_Y_Scale=LOG since v7.1. BAR_COLOR was the one
# reader that did not take the shared AxisCalibration: it re-fitted the ticks
# with np.polyfit, which is linear, and produced values off by an order of
# magnitude - with a saved WPD project that recorded scale LOG beside them.
LOG_IMG = os.path.join(HERE, "fixtures", "log_bars.png")
os.makedirs(os.path.dirname(LOG_IMG), exist_ok=True)
_LOG_TRUE = [("T0", 3.0, 12.0), ("T1", 30.0, 120.0), ("T2", 300.0, 700.0)]
_ltop, _lbot, _lx0, _lx1 = 60, 560, 120, 720


def _log_y(value):
    lo, hi = math.log(1.0), math.log(1000.0)
    return _lbot + (_ltop - _lbot) * ((math.log(value) - lo) / (hi - lo))


_li = Image.new("RGB", (800, 640), "white")
_ld = ImageDraw.Draw(_li)
_lticks = []
for _v in (1, 10, 100, 1000):
    _y = int(round(_log_y(_v)))
    _ld.line([_lx0 - 16, _y, _lx0 - 4, _y], fill=(0, 0, 0), width=3)
    _lticks.append((_v, _y))
_ld.line([_lx0, _ltop - 10, _lx0, _lbot + 10], fill=(0, 0, 0), width=4)
_ld.line([_lx0, _lbot, _lx1, _lbot], fill=(0, 0, 0), width=4)
_LOG_ANCHORS = {}
for _i, (_lab, _a, _b) in enumerate(_LOG_TRUE):
    _base = _lx0 + 60 + 200 * _i
    for _j, (_val, _fill) in enumerate(((_a, (45, 80, 220)), (_b, (215, 45, 45)))):
        _xl = _base + _j * 60
        _xr = _xl + 46
        _yt = int(round(_log_y(_val)))
        _ld.rectangle([_xl, _yt, _xr, _lbot], fill=_fill, outline=(0, 0, 0), width=3)
    _LOG_ANCHORS[_lab] = _base + 53
_li.save(LOG_IMG)

_lcal = AxisCalibration.from_points(_lticks, scale="LOG")
_lbars = read_bar_panel(colour_masks(_li), (_lx0, _lx1, _ltop, _lbot),
                        series={"A": "blue", "B": "red"},
                        y_calibration=_lcal, x_positions=_LOG_ANCHORS,
                        baseline_value=1.0, stem_required=False)
_got = {(b["series"], b["x_label"]): b["mean"] for b in _lbars}
_want = {}
for _lab, _a, _b in _LOG_TRUE:
    _want[("A", _lab)] = _a
    _want[("B", _lab)] = _b
check("every log bar is found", set(_got) == set(_want),
      "%s" % sorted(set(_want) ^ set(_got)))
_rel = [abs(_got[k] - v) / v for k, v in _want.items() if k in _got]
check("and read within 5%% of its true value on the log scale",
      _rel and max(_rel) < 0.05, "max rel err %.3f" % (max(_rel) if _rel else 9))
_linear = read_bar_panel(colour_masks(_li), (_lx0, _lx1, _ltop, _lbot),
                         series={"A": "blue", "B": "red"},
                         y_calibration=AxisCalibration.from_points(_lticks),
                         x_positions=_LOG_ANCHORS, baseline_value=0.0,
                         stem_required=False)
_lin = {(b["series"], b["x_label"]): b["mean"] for b in _linear}
check("reading the same panel linearly is wrong by an order of magnitude",
      max(abs(_lin[k] - v) / v for k, v in _want.items() if k in _lin) > 5,
      "%s" % {k: round(v, 1) for k, v in list(_lin.items())[:3]})
try:
    read_bar_panel(colour_masks(_li), (_lx0, _lx1, _ltop, _lbot),
                   series={"A": "blue"}, y_calibration=_lcal,
                   x_positions=_LOG_ANCHORS, baseline_value=0.0)
    _refused = ""
except ValueError as exc:
    _refused = str(exc)
check("a baseline of zero on a log axis is refused, not invented",
      "LOG" in _refused, _refused or "no error raised")

# The residual is in the axis's own units - log units on a LOG axis - so the
# same ticks give a near-zero residual read correctly and a huge one read
# linearly. It was computed before and returned under a name nothing read.
_log_resid = _lcal.max_residual
_lin_resid = AxisCalibration.from_points(_lticks).max_residual
check("the calibration carries the residual somebody can gate on",
      _log_resid < 0.01 and _lin_resid > 100,
      "log %.4g linear %.4g" % (_log_resid, _lin_resid))
check("and the bars carry it too, per mark",
      all(abs(b["calib_max_resid"] - _log_resid) < 1e-12 for b in _lbars),
      "%s" % sorted({round(b["calib_max_resid"], 6) for b in _lbars}))


# --------------------------------------------------- colours the manifest names
print("a bar panel drawn in any two colours reads by what the manifest declares")
# `colour_masks` returned exactly three masks - blue, red and dark - tuned on
# one publication, and `Mask_Key` chose between them. `Colour_Hex` was required
# on every colour series, validated, and then ignored; `colour_tolerance` was
# offered as a BAR_COLOR option whose reader keyword was None. So a figure drawn
# in green and purple validated and had no way through.
ANY_IMG = os.path.join(HERE, "fixtures", "any_colour_bars.png")
os.makedirs(os.path.dirname(ANY_IMG), exist_ok=True)
_GREEN, _PURPLE = (26, 148, 74), (126, 74, 168)
_ATRUE = [("T0", 30.0, 45.0), ("T1", 55.0, 70.0), ("T2", 80.0, 62.0)]
_ax0, _ax1, _ay0, _ay1 = 110, 700, 50, 520


def _av2y(value):
    return _ay1 + (_ay0 - _ay1) * (value / 100.0)


_ai = Image.new("RGB", (760, 600), "white")
_ad = ImageDraw.Draw(_ai)
_aticks = [(v, int(round(_av2y(v)))) for v in (0, 25, 50, 75, 100)]
for _v, _y in _aticks:
    _ad.line([_ax0 - 14, _y, _ax0 - 4, _y], fill=(0, 0, 0), width=3)
_ad.line([_ax0, _ay0 - 10, _ax0, _ay1 + 10], fill=(0, 0, 0), width=4)
_ad.line([_ax0, _ay1, _ax1, _ay1], fill=(0, 0, 0), width=4)
_AANCHORS = {}
for _i, (_lab, _g, _p) in enumerate(_ATRUE):
    _base = _ax0 + 70 + 190 * _i
    for _j, (_val, _fill) in enumerate(((_g, _GREEN), (_p, _PURPLE))):
        _xl = _base + _j * 62
        _ad.rectangle([_xl, int(round(_av2y(_val))), _xl + 48, _ay1],
                      fill=_fill, outline=(0, 0, 0), width=3)
    _AANCHORS[_lab] = _base + 55
_ai.save(ANY_IMG)

_amasks = colour_masks(_ai, declared={"GREEN": ("#1a944a", 60),
                                      "PURPLE": ("#7e4aa8", 60)})
check("a declared colour produces a mask of its own",
      {"GREEN", "PURPLE"} <= set(_amasks) and _amasks["GREEN"].any()
      and _amasks["PURPLE"].any(),
      "%s" % sorted(_amasks))
check("and the built-in three are still there for the worked examples",
      {"blue", "red", "dark"} <= set(_amasks))
check("and the two declared masks do not overlap",
      not (_amasks["GREEN"] & _amasks["PURPLE"]).any(),
      "%d pixels claimed twice" % int((_amasks["GREEN"] & _amasks["PURPLE"]).sum()))

_abars = read_bar_panel(
    _amasks, (_ax0, _ax1, _ay0, _ay1),
    series={"GREEN": "GREEN", "PURPLE": "PURPLE"},
    y_calibration=AxisCalibration.from_points(_aticks),
    x_positions=_AANCHORS, baseline_value=0.0, stem_required=False)
_agot = {(b["series"], b["x_label"]): b["mean"] for b in _abars}
_awant = {}
for _lab, _g, _p in _ATRUE:
    _awant[("GREEN", _lab)] = _g
    _awant[("PURPLE", _lab)] = _p
check("every bar of a green-and-purple panel is found",
      set(_agot) == set(_awant), "%s" % sorted(set(_awant) ^ set(_agot)))
check("and read within one unit of its true value",
      _agot and max(abs(_agot[k] - v) for k, v in _awant.items() if k in _agot) < 1.0,
      "%s" % {k: round(v, 2) for k, v in sorted(_agot.items())})

# The old three masks cannot see this panel at all, which is the point.
_legacy = read_bar_panel(
    colour_masks(_ai), (_ax0, _ax1, _ay0, _ay1),
    series={"GREEN": "blue", "PURPLE": "red"},
    y_calibration=AxisCalibration.from_points(_aticks),
    x_positions=_AANCHORS, baseline_value=0.0, stem_required=False)
check("while the built-in blue/red masks find nothing in it",
      len(_legacy) < len(_awant),
      "%d bars found with the hard-coded masks" % len(_legacy))

# The real case: the printed colour is never exactly the swatch in the legend.
# "#20a050" is about 15 RGB units from the ink actually on this fixture.
_near, _far = "#20a050", "#20a050"
_wide = colour_masks(_ai, declared={"GREEN": (_near, 40)})["GREEN"]
_tight = colour_masks(_ai, declared={"GREEN": (_far, 4)})["GREEN"]
check("tolerance is honoured, not decorative",
      int(_tight.sum()) == 0 < int(_wide.sum()),
      "tight %d, wide %d" % (int(_tight.sum()), int(_wide.sum())))
check("and a slightly-off declared colour still reads at a sane tolerance",
      abs(int(_wide.sum()) - int(_amasks["GREEN"].sum())) * 1.0
      / max(1, int(_amasks["GREEN"].sum())) < 0.05,
      "%d vs %d" % (int(_wide.sum()), int(_amasks["GREEN"].sum())))

print("Mask_Key names a mask the reader has, or the manifest is refused")
# `Mask_Key` picked one of three hard-coded masks and was never checked against
# them. The masks are lower case, so `Mask_Key=BLUE` - the natural way to write
# it - validated, reached `masks[key]`, raised KeyError, and became an
# InternalReaderError, which aborts the entire batch. A manifest typo is not a
# reader defect and must not be reported as one.
import batch_manifests as _BM  # noqa: E402
import bar_reader as BR  # noqa: E402
import numpy as np  # noqa: E402
check("the reader's built-in masks and the validator's list are one list",
      tuple(sorted(BR.BUILTIN_MASK_KEYS)) == tuple(sorted(_BM.BAR_COLOR_MASK_KEYS)),
      "%s vs %s" % (BR.BUILTIN_MASK_KEYS, _BM.BAR_COLOR_MASK_KEYS))
check("and they are the keys colour_masks actually returns",
      set(BR.BUILTIN_MASK_KEYS)
      <= set(BR.colour_masks(np.zeros((4, 4, 3), dtype=np.uint8))),
      "%s" % sorted(BR.colour_masks(np.zeros((4, 4, 3), dtype=np.uint8))))
for _key in ("BLUE", "GREEN", "foo", "Dark "):
    _built = BR.colour_masks(np.zeros((4, 4, 3), dtype=np.uint8))
    check("Mask_Key=%r is not a mask the reader has" % _key,
          _key not in _built,
          "it is, so the validator would be wrong to refuse it")
check("but case-folding turns the ones that name a real mask into it",
      all(_k.strip().casefold() in BR.BUILTIN_MASK_KEYS
          for _k in ("BLUE", "Dark ", "Red")))

print("%d scenarios run" % (len(FAILURES) + _PASSED[0]))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
