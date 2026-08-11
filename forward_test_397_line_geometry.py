"""Forward test: the AUTHORED geometry of 397's twelve line panels.

    python3 forward_test_397_line_geometry.py

`forward_test_397_line_style.py` checks what the reader gets out of ONE panel,
against an eye reading. This checks the input to all twelve: that every number
`pilot_397.py` declares about these panels is a fact about the raster.

It exists because the geometry for these panels was authored in bulk. Before
LINE_MONO_STYLE shipped they carried one box copied to every panel and twelve x
pixels spread evenly between its edges, which nobody noticed for as long as no
reader looked at them. Measuring twelve panels by hand replaces one silent
error with twelve chances at a transcription one - a digit dropped from a tick
column moves a whole series and produces perfectly plausible numbers.

Three properties, each checked against the pixels:

  THE Y TICKS ARE GRIDLINES. A declared tick row has to be inked nearly all the
  way across the panel. A row one pixel off a gridline is a calibration that is
  wrong by one pixel everywhere, which on the finger-pulse-volume panel is 14
  units of a 2400-unit axis.

  THE X PIXELS SIT BETWEEN TICK MARKS. These are Excel category charts, so a
  plotted point is at the CENTRE of its category interval, not on the tick.
  Each declared x has to be the midpoint of two adjacent printed ticks.

  THE LADDER IS REGULAR. Twelve equal intervals; a panel whose declared x
  pixels are not evenly spaced has had one of them mistyped.

This is not independent of the measurement in the sense a second pair of eyes
would be - it reads the same rasters. It is independent of the DECLARATION,
which is where the errors this guards against live.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image                                            # noqa: E402

SOURCE = open(os.path.join(HERE, "pilot_397.py"), encoding="utf-8").read()
NS = {"__file__": os.path.join(HERE, "pilot_397.py"), "__name__": "geom_source"}
exec(compile(SOURCE[:SOURCE.index("write(MANIFESTS)")], "pilot_397.py", "exec"), NS)
LINE_FIGURES = NS["LINE_FIGURES"]
RASTERS = NS["RASTERS"]

#: A gridline is inked across at least this much of the panel. Same rule the
#: reader removes them with, and the same reason: a curve would have to be flat
#: to the pixel across the whole panel to match it.
RULE_COVERAGE = 0.9
#: A declared x may sit this far from the midpoint of its two ticks. One pixel
#: covers the rounding in "the centre of a 33 px interval"; two would let a
#: whole tick's worth of drift through unnoticed.
X_TOLERANCE = 1.0

failures = []
print("publication 397, figures 1 and 2 - the geometry as declared")
for _fid, image, rows in LINE_FIGURES:
    path = os.path.join(RASTERS, image)
    if not os.path.exists(path):
        print("SKIP: %s is not on disk" % path, file=sys.stderr)
        raise SystemExit(0)
    grey = np.asarray(Image.open(path).convert("L"))
    for pid, _sex, outcome, _unit, box, tick_text, x_pixels in rows:
        x0, x1, y0, y1 = box
        ink = grey[:, x0:x1] < 150
        width = x1 - x0
        rules = {int(r) for r, v in enumerate(ink.sum(axis=1))
                 if v >= RULE_COVERAGE * width}
        problems = []
        # 1. every declared calibration tick is a printed gridline, inside the box
        for pair in tick_text.split(";"):
            value, row = pair.split(":")
            row = int(float(row))
            if not (y0 <= row <= y1):
                problems.append("tick %s at row %d is outside the box %d-%d"
                                % (value, row, y0, y1))
            elif row not in rules:
                near = sorted(rules, key=lambda r: abs(r - row))[:1]
                problems.append("tick %s at row %d is not a gridline (nearest "
                                "%s)" % (value, row, near or "none"))
        # 2. the printed tick marks below the panel, and the declared x pixels
        #    as their interval centres
        marks = []
        for probe in range(y1 + 1, y1 + 9):
            if probe >= grey.shape[0]:
                break
            columns = (np.where(grey[probe, x0 - 4:x1 + 20] < 150)[0]
                       + x0 - 4).tolist()
            runs, run = [], []
            for c in columns:
                if run and c - run[-1] > 1:
                    runs.append(run)
                    run = []
                run.append(c)
            if run:
                runs.append(run)
            centres = [float(np.mean(r)) for r in runs if len(r) <= 4]
            if len(centres) == len(x_pixels) + 1:
                spacing = np.diff(centres)
                if float(max(spacing) - min(spacing)) <= 4.0:
                    marks = centres
                    break
        if not marks:
            problems.append("no row below the panel carries %d evenly spaced "
                            "tick marks" % (len(x_pixels) + 1))
        else:
            for i, declared in enumerate(x_pixels):
                middle = (marks[i] + marks[i + 1]) / 2.0
                if abs(declared - middle) > X_TOLERANCE:
                    problems.append("x[%d]=%g is %.1f px off the centre of "
                                    "ticks %g..%g" % (i, declared,
                                                      declared - middle,
                                                      marks[i], marks[i + 1]))
        # 3. the declared ladder is regular
        gaps = np.diff(np.asarray(x_pixels, dtype=float))
        if float(max(gaps) - min(gaps)) > 2.0:
            problems.append("the declared x pixels are not evenly spaced: "
                            "gaps %.1f to %.1f" % (min(gaps), max(gaps)))
        print("  %-14s %-28s %s"
              % (pid, outcome,
                 "ok" if not problems else "FAIL " + problems[0]))
        failures.extend("%s: %s" % (pid, p) for p in problems)

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - %d panels, every declared tick row on a printed "
      "gridline and every declared x within %.1f px of its interval centre."
      % (sum(len(rows) for _f, _i, rows in LINE_FIGURES), X_TOLERANCE))
