"""Forward test: LINE_MONO_STYLE against publication 397 Figure 1, MEN / MAP.

    python3 forward_test_397_line_style.py [PATH_TO_397_fig1.jpeg]

Two black curves, no markers anywhere, and a legend that says "solid = Fluid,
dashed = No Fluid". Marker geometry has nothing to work with; the ink's own
stroke pattern is the entire discriminant. This is the figure type the reader
was written for, and it is the release gate: a fixture the author drew is a
statement about what the author expected, and this is the first thing the
reader met that it did not.

**Four defects, none of which the fixture could show.** Each cost a debugging
round and each is a property of printed figures rather than of this paper:

  GRIDLINES     Figure 1 rules the panel at every 10 mmHg. A gridline measures
                a duty of 1.000 and a gap of 0 - a perfect solid line - so four
                of them plus the real curve made five SOLID candidates at every
                x, the count was never one, and the reader emitted no solid
                cells anywhere while reporting no problem at all. Rules are now
                found by their coverage of the panel and removed.

  STEMS         The error-bar stems are three pixels wide and stand every 33
                columns. They are removed before tracing, which takes the
                curve's own pixels with them, and scoring those columns as
                misses gave the SOLID curve a gap of 3 in every window - one
                over the limit. A column we cannot see through is not a column
                where the curve is absent, so those columns are now skipped in
                both halves of the duty fraction.

  CAPS          The solid curve turns down into 3:00 and its own upper caps sit
                where the descending limb would have continued. Fitted together
                they measured 0.947/gap 1 - a clean SOLID - and the reader
                answered 101.3 mmHg for a curve the eye reads at 98, while the
                real curve went to the other series. A cap is told from a curve
                by the stem under it, not by its length.

  CORNERS       The value used to be read off the fitted quadratic, and a
                quadratic rounds a corner. Reading it off the ink, with the fit
                only saying where to look, took 3:00 from 3.3 mmHg out to 1.6.

**Eight of twenty-four cells are refused, and that is the answer.** At 0:30,
4:30, 5:00 and 6:00 the two curves run within about two mmHg - at 6:00 they
touch. There is no ink at those positions that says which curve is which, so
the reader emits nothing for either series rather than a number for one of
them. The sixteen it does emit are all within 1.65 mmHg of an independent eye
reading, on a 50 mmHg axis.

The expected values below were read off the plotted curves by eye, before the
reader was run against this panel, to the nearest half millimetre of mercury.
They are the only independent truth this project has for this figure.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image                                            # noqa: E402
import mark_readers as MR                                        # noqa: E402
import line_style_mono as LSM                                    # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "397_fig1.jpeg")
if not os.path.exists(path):
    print("SKIP: %s is not on disk" % path, file=sys.stderr)
    raise SystemExit(0)

#: Measured by hand off the rendering: the gridlines at 120 and 70 mmHg lie on
#: rows 76 and 296, the category ticks on columns 83 to 476, and the twelve
#: plotted points sit at the centres of the twelve intervals between them.
CAL = MR.AxisCalibration.from_points([(120.0, 76.0), (70.0, 296.0)])
LABELS = ("0:30", "1:00", "1:30", "2:00", "2:30", "3:00",
          "3:30", "4:00", "4:30", "5:00", "5:30", "6:00")
XS = (99.5, 132.5, 165.0, 197.5, 230.5, 263.5,
      296.5, 329.0, 361.5, 394.5, 427.5, 460.0)
#: The top of the box is row 110, not the frame at 76, because THE LEGEND IS
#: INSIDE THE PLOT AREA - two line samples at about 114 mmHg, above every
#: datum and above the tallest whisker cap at 110.5. Excluding furniture is
#: what a panel box is for; it is ordinary authored geometry, not an exception
#: for this paper.
BOX = (84, 477, 110, 296)

EYE = {
    "FLUID":    (92.5, 99.5, 104.0, 107.0, 105.0, 98.0,
                 98.5, 100.0, 97.0, 98.0, 99.0, 98.0),
    "NO_FLUID": (89.0, 91.0, 92.0, 94.0, 96.0, 96.5,
                 95.0, 95.0, 96.0, 96.0, 96.5, 98.0),
}
#: Where the two curves run too close to be told apart. Named here rather than
#: discovered from the output: a forward test that accepts whatever refusals it
#: is given cannot notice the reader going quiet.
UNRESOLVABLE = ("0:30", "4:30", "5:00", "6:00")
TOLERANCE = 2.0

rows = LSM.read_monochrome_line_panel(
    Image.open(path), panel_box=BOX,
    x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
    series=[MR.SeriesSpec("FLUID", line_style="SOLID"),
            MR.SeriesSpec("NO_FLUID", line_style="DASHED")],
    threshold=150, x_window=10, search_radius=60)

print("publication 397 figure 1, MEN / mean arterial pressure")
errors, failures = [], []
for row in sorted(rows, key=lambda r: (r["series"], r["order"])):
    eye = EYE[row["series"]][LABELS.index(row["x_label"])]
    errors.append(abs(row["mean"] - eye))
    print("    %-9s %-5s  %6.1f (eye %5.1f, d %4.2f)  %s  duty %.3f gap %d"
          % (row["series"], row["x_label"], row["mean"], eye, errors[-1],
             ("sd %5.2f" % row["dispersion"]) if row["dispersion"] is not None
             else "no dispersion", row["line_duty"], row["line_gap"]))

read = {(r["series"], r["x_label"]) for r in rows}
expected = {(s, x) for s in EYE for x in LABELS if x not in UNRESOLVABLE}
if read != expected:
    failures.append("read %d cells, expected %d; missing %r, unexpected %r"
                    % (len(read), len(expected), sorted(expected - read),
                       sorted(read - expected)))
if errors and max(errors) > TOLERANCE:
    failures.append("worst mean is %.2f mmHg from the eye reading, over %.1f"
                    % (max(errors), TOLERANCE))
# Every emitted cell carries the style it was declared with, or the two series
# have been swapped and the means would still look plausible.
wrong = [r for r in rows
         if r["line_style"] != ("SOLID" if r["series"] == "FLUID" else "DASHED")]
if wrong:
    failures.append("%d cells carry the other series' style" % len(wrong))
# The gap is the discriminant, so it has to separate on a real figure and not
# only on a drawn one.
solid = [r["line_gap"] for r in rows if r["series"] == "FLUID"]
dashed = [r["line_gap"] for r in rows if r["series"] == "NO_FLUID"]
if solid and dashed and max(solid) >= min(dashed):
    failures.append("the gap does not separate the styles: solid %r, dashed %r"
                    % (sorted(set(solid)), sorted(set(dashed))))

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - %d of %d cells, %d refused where the curves converge, "
      "worst mean %.2f mmHg against the eye on a 50 mmHg axis."
      % (len(rows), 2 * len(LABELS), 2 * len(UNRESOLVABLE), max(errors)))
