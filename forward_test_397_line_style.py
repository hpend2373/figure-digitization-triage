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

**Six of twenty-four cells are refused, and that is the answer.** At 4:30, 5:00
and 6:00 the two curves are ONE RUN OF INK - nine to ten pixels where a stroke
is three - and at 6:00 they touch outright. Nothing at those positions says
which curve is which, so the reader emits nothing for either series rather than
a number for one of them. The eighteen it does emit are all within 1.65 mmHg of
an independent eye reading, on a 50 mmHg axis.

**0:30 used to be refused with them, and that was a defect, not a merge.** The
two curves are four mmHg apart there and both plainly traceable. Two more
things had to be true before the reader could say so, and both are about the
reader over-claiming rather than about this paper:

  DATA SPAN     The panel box says where the panel is; the declared positions
                say where the data is. At the first plotted point half the fit
                window hangs over the axis, and a SINGLE STRAY PIXEL of the
                y-axis - sixteen columns from the nearest curve - was collected
                as a sample of it. It stretched the fitted span from column 95
                back to 84, dragged the quadratic six pixels, and the dashed
                curve came back at 90.7 where the eye reads 89.0: inside this
                test's tolerance, and wrong. Clipped to the declared span it
                reads 89.4.

  BLIND WINDOWS Blinding hides gaps and cannot invent them, so a window that
                could not see most of itself has no business calling a curve
                SOLID. The dashed curve runs along the 90 mmHg gridline through
                0:30; 68% of that window is blinded, every dash gap with it,
                and it measured duty 1.000 gap 0. Two SOLID candidates at one x
                meant neither was unique and BOTH cells were dropped - a
                correctly traced curve thrown away because the reader believed
                a classification it could not support.

With the SOLID call withheld, naming the other curve names this one: two
declared styles, two curves found, one of them measured. Four of the eighteen
cells are named that way and say so in `line_style_source`.

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
# A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC. Absent is a SKIP; present
# and not the render these coordinates were measured on is a failure.
import raster_root as RR                                          # noqa: E402
path, _note = RR.check("397_fig1.jpeg")
if not path:
    print(RR.skip_note("397_fig1.jpeg"))
    raise SystemExit(0)
print(_note)

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
#: Where the two curves are one run of ink. Named here rather than discovered
#: from the output: a forward test that accepts whatever refusals it is given
#: cannot notice the reader going quiet. 0:30 was on this list and did not
#: belong on it - see the module docstring.
UNRESOLVABLE = ("4:30", "5:00", "6:00")

#: Named by elimination rather than measured, because more than half of the
#: window was furniture. Pinned, both ways: a cell that quietly starts being
#: inferred is a cell whose evidence changed without anybody saying so, and a
#: cell that stops being inferred means the blindness guard has stopped firing.
INFERRED = {("FLUID", "3:00"), ("FLUID", "3:30"), ("FLUID", "4:00"),
            ("NO_FLUID", "0:30")}
TOLERANCE = 2.0

rows = LSM.read_monochrome_line_panel(
    Image.open(path), panel_box=BOX,
    x_positions=dict(zip(LABELS, XS)), y_calibration=CAL,
    series=[MR.SeriesSpec("FLUID", line_style="SOLID"),
            MR.SeriesSpec("NO_FLUID", line_style="DASHED")],
    threshold=150, x_window=10, search_radius=60)

# WHY EACH ERROR BAR WAS READ OR REFUSED, on the real figure. v7.92 made the
# reason part of the reader's answer; this is the measurement that reason exists
# for, and it is the evidence behind `RESTORED_MASKED_CAP` staying reserved: not
# one of these marks has a cap partly covered by furniture. Three read a bar,
# twelve share a column of ink with the other curve - which no reader and no
# person can attribute from that column - and three have a cap one pixel
# narrower than the rule accepts. Pinned rather than printed: a distribution that
# drifts is the reader changing its mind about a figure nobody re-drew.
import collections as _collections                                # noqa: E402
_why = _collections.Counter(r["Dispersion_Refusal"] for r in rows)
_WHY_EXPECTED = {"CAP_READ": 3, "MARKS_SHARE_A_COLUMN": 12, "NO_BOUNDED_CAP": 3}
print()
print("why each error bar was read or refused")
for _reason, _n in sorted(_why.items()):
    print("    %-24s %2d" % (_reason, _n))
if dict(_why) != _WHY_EXPECTED:
    print("MISMATCH: expected %s" % _WHY_EXPECTED)
    raise SystemExit(1)
print("    (no cap on this figure is partly covered by furniture, which is what "
      "RESTORED_MASKED_CAP is reserved for)")

print("publication 397 figure 1, MEN / mean arterial pressure")
errors, failures = [], []
for row in sorted(rows, key=lambda r: (r["series"], r["order"])):
    eye = EYE[row["series"]][LABELS.index(row["x_label"])]
    errors.append(abs(row["mean"] - eye))
    print("    %-9s %-5s  %6.1f (eye %5.1f, d %4.2f)  %s  duty %.3f gap %d "
          "blind %.2f%s"
          % (row["series"], row["x_label"], row["mean"], eye, errors[-1],
             ("sd %5.2f" % row["dispersion"]) if row["dispersion"] is not None
             else "no dispersion", row["line_duty"], row["line_gap"],
             row["line_window_blindness"],
             "  named by elimination" if row["line_style_source"] != "MEASURED"
             else ""))

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
# What the reader INFERRED has to be what it says it inferred. An inference
# that reports itself as a measurement is worse than no inference: the cell
# reads as ink-backed to everyone downstream.
inferred = {(r["series"], r["x_label"]) for r in rows
            if r["line_style_source"] != "MEASURED"}
if inferred != INFERRED:
    failures.append("named by elimination: %r, expected %r"
                    % (sorted(inferred), sorted(INFERRED)))
# And an inference is only allowed where the window could not answer. Two
# halves of one contract, both observable: nothing is inferred from a window
# that could see itself, and no SOLID call survives one that could not.
unjustified = [(r["series"], r["x_label"], r["line_window_blindness"])
               for r in rows if r["line_style_source"] != "MEASURED"
               and r["line_window_blindness"] <= 0.5]
if unjustified:
    failures.append("named by elimination with the window in view: %r"
                    % (unjustified,))
overclaimed = [(r["series"], r["x_label"], r["line_window_blindness"])
               for r in rows if r["line_style_source"] == "MEASURED"
               and r["line_style"] == "SOLID"
               and r["line_window_blindness"] > 0.5]
if overclaimed:
    failures.append("SOLID measured through a mostly blinded window: %r"
                    % (overclaimed,))
# The gap is the discriminant, so it has to separate on a real figure and not
# only on a drawn one - WHERE IT WAS MEASURED. Where the window was blinded the
# gap is exactly what could not be seen, and holding an inferred cell to it
# would be testing the thing the inference exists to work around.
measured = [r for r in rows if r["line_style_source"] == "MEASURED"]
solid = [r["line_gap"] for r in measured if r["series"] == "FLUID"]
dashed = [r["line_gap"] for r in measured if r["series"] == "NO_FLUID"]
if solid and dashed and max(solid) >= min(dashed):
    failures.append("the gap does not separate the styles: solid %r, dashed %r"
                    % (sorted(set(solid)), sorted(set(dashed))))

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - %d of %d cells, %d refused where the two curves are one "
      "run of ink, %d named by elimination, worst mean %.2f mmHg against the "
      "eye on a 50 mmHg axis."
      % (len(rows), 2 * len(LABELS), 2 * len(UNRESOLVABLE), len(INFERRED),
         max(errors)))
