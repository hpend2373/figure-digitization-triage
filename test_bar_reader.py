"""Image-level regression suite for bar_reader.

    python test_bar_reader.py        # exit 0 = all scenarios pass

Every scenario corresponds to a defect found while digitizing real figures.
Unlike test_kernel.py, which checks a filled CSV, these run the reader against
actual rasters: a synthetic chart whose true values are known exactly, and a
frozen real figure (ID 323 Figure 1, six panels, 72 bars).

Scenario count is printed at the end; do not hard-code it in prose.
"""
import json
import os
import sys
import hashlib
import statistics as S

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bar_reader import colour_masks, read_bar_panel, runs  # noqa: E402

FAILURES = []
PX_PER_UNIT = 440.0 / 150.0          # synthetic fixture: axis span / value span


_PASSED = [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        _PASSED[0] += 1
    else:
        FAILURES.append(name)


def read_fixture(img, meta, stem_required=True):
    m = colour_masks(Image.open(os.path.join(HERE, img)).convert("RGB"))
    cfg = json.load(open(os.path.join(HERE, meta)))
    bars = read_bar_panel(m, tuple(cfg["panel_box"]), cfg["ticks"],
                          {"SUPINE": "blue", "ORTHOSTASIS": "red"},
                          stem_required=stem_required)
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
# The whisker points AWAY from zero, so a down bar's dispersion is negative in
# axis units; its magnitude is what matters.
sdisp = [abs(b["dispersion"] or 0) - struth[(b["series"], b["order"])]["true_sd"]
         for b in sbars]
check("signed dispersions recovered within 0.5 unit", max(map(abs, sdisp)) < 0.5,
      "max|err| %.3f" % max(map(abs, sdisp)))
check("a down bar's whisker is signed away from zero",
      all((b["dispersion"] or 0) < 0 for b in sbars if b["Bar_Direction"] == "DOWN")
      and all((b["dispersion"] or 0) > 0 for b in sbars if b["Bar_Direction"] == "UP"))

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
print("%d scenarios run" % (len(FAILURES) + _PASSED[0]))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("all scenarios passed")
