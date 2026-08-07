"""Forward test: the monochrome bar reader against a real publisher figure.

    python3 forward_test_397_mono_bar.py [PATH_TO_397_fig3.jpeg]

`test_mono_bar.py` proves the reader on a raster this project drew, where the
truth is known exactly. That proves it is self-consistent. It cannot prove it
survives JPEG softening, a 1-pixel hatch outline that does not reach the
threshold, or two panels of one figure whose axes are four pixels apart - all of
which are true of publication 397 Figure 3 and all of which broke the reader the
first time it met them.

The expected values below were read off the plotted bars independently, by eye,
to the nearest millimetre of mercury. They are a coarse instrument on purpose: a
forward test asks whether the reader is in the right place, not whether it
agrees with itself.
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mark_readers as MR                                          # noqa: E402

DEFAULT = os.path.join(HERE, "397_fig3.jpeg")
path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
if not os.path.exists(path):
    print("SKIP: publisher raster not found: %s" % path)
    raise SystemExit(0)

SPECS = [MR.SeriesSpec("FLUID", bar_fill="SOLID"),
         MR.SeriesSpec("NON_FLUID", bar_fill="HATCHED")]

# Two panels of ONE figure, with axes four pixels apart. Sharing a calibration
# between them - which looks harmless, since both are labelled 50 to 150 - put
# the second panel's baseline five pixels below its bars, and the reader
# returned nothing for all four of its cells. Panel geometry is per panel.
PANELS = (
    dict(name="MEN", box=(118, 480, 90, 470), ticks=[(150, 101), (50, 465)],
         x={"PRE": 187, "POST": 390},
         expected={("FLUID", "PRE"): 97, ("FLUID", "POST"): 123,
                   ("NON_FLUID", "PRE"): 96, ("NON_FLUID", "POST"): 113}),
    dict(name="WOMEN", box=(620, 1010, 88, 466), ticks=[(150, 95), (50, 460)],
         x={"PRE": 720, "POST": 920},
         expected={("FLUID", "PRE"): 88, ("FLUID", "POST"): 110,
                   ("NON_FLUID", "PRE"): 92, ("NON_FLUID", "POST"): 104}),
)

image = Image.open(path).convert("RGB")
total, errors, unconfirmed = 0, [], 0
print("publication 397 Figure 3 - mean arterial pressure, fluid vs non-fluid")
for panel in PANELS:
    cal = MR.AxisCalibration.from_points(panel["ticks"])
    rows = MR.read_monochrome_bar_panel(
        image, panel_box=panel["box"], x_positions=panel["x"],
        y_calibration=cal, series=SPECS, baseline_value=50.0, group_window=75)
    print("  %-6s %d of %d cells" % (panel["name"], len(rows), len(panel["expected"])))
    assert len(rows) == len(panel["expected"]), \
        "%s: read %d of %d cells" % (panel["name"], len(rows), len(panel["expected"]))
    for row in rows:
        key = (row["series"], row["x_label"])
        error = abs(row["mean"] - panel["expected"][key])
        errors.append(error)
        total += 1
        if row["Errorbar_Stem_Confirmed"] != "TRUE":
            unconfirmed += 1
        print("    %-10s %-4s  mean %6.1f (eye %3d, d %.1f)  sd %s  stem %s"
              % (row["series"], row["x_label"], row["mean"],
                 panel["expected"][key], error,
                 "----" if row["dispersion"] is None else "%.1f" % row["dispersion"],
                 row["Errorbar_Stem_Confirmed"]))

assert total == 8, "expected 8 cells across both panels, got %d" % total
assert max(errors) < 2.0, "worst mean is %.2f mmHg from the eye reading" % max(errors)
assert unconfirmed == 0, \
    ("%d of %d error bars were not stem-confirmed. On this figure the stem is a "
     "one-pixel hairline that reads about grey 140, so it disappears under the "
     "same threshold that finds the caps - if this fires again, the stem "
     "threshold has been folded back into the fill threshold." % (unconfirmed, total))

print()
print("  cells read              : %d of 8" % total)
print("  worst mean vs eye       : %.2f mmHg on a 100 mmHg axis" % max(errors))
print("  error bars stem-confirmed: %d of %d" % (total - unconfirmed, total))
print("  verdict: PASS")
