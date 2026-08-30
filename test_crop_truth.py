# -*- coding: utf-8 -*-
"""Scenarios for the crop harness - the thing that grades the crop boxes.

    python3 test_crop_truth.py     # exit 0 = all scenarios pass

The harness this replaces scored a box by measuring ink INSIDE THAT SAME BOX.
It passed 19 of 19 while five crops were, by eye, still wrong, and it steered
four rounds of algorithm work. So the harness is now the thing under test, and
these scenarios are about the two properties that made the old one useless:

  the score comes from OUTSIDE the code   `crop_truth.FIGURE_REGIONS` holds
                                          regions read off the rendered pages,
                                          which no change to `figure_bbox` can
                                          move.

  the harness proves itself first         `VISUAL_VERDICT` records what a
                                          person judged of each crop, and the
                                          thresholds have to reproduce it. A
                                          grader that cannot agree with the
                                          judgement it automates grades
                                          nothing.

Reads no files: the pages are publisher PDFs and cannot be published, but the
geometry and the arithmetic can be, and they are what goes wrong.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import crop_truth as T                                            # noqa: E402
import regress_crop as R                                          # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name
          + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


print("the harness that grades a crop")

# ------------------------------------------------------------ the arithmetic
WHOLE = (0.0, 0.0, 1.0, 1.0)
LEFT = (0.0, 0.0, 0.5, 1.0)
RIGHT = (0.5, 0.0, 1.0, 1.0)

check("a box holding all of a figure covers it entirely",
      T.covered(WHOLE, LEFT) == 1.0)
check("a box holding half of it covers half",
      abs(T.covered((0.0, 0.0, 0.25, 1.0), LEFT) - 0.5) < 1e-9,
      "%s" % T.covered((0.0, 0.0, 0.25, 1.0), LEFT))
check("a box beside a figure covers none of it",
      T.covered(RIGHT, LEFT) == 0.0)
check("a box holding a neighbour entirely intrudes completely",
      T.intrusion(WHOLE, [RIGHT]) == 1.0)
check("a box in its own column intrudes on nothing",
      T.intrusion(LEFT, [RIGHT]) == 0.0)
check("intrusion reports the WORST neighbour, not the average",
      T.intrusion((0.4, 0.0, 1.0, 1.0),
                  [(0.9, 0.0, 1.0, 1.0), (0.0, 0.0, 0.45, 1.0)]) == 1.0)
check("a figure with no neighbours has nothing to intrude on",
      T.intrusion(WHOLE, []) == 0.0)
check("a zero-area truth region does not divide by zero",
      T.covered(WHOLE, (0.5, 0.5, 0.5, 0.5)) == 0.0)

# --------------------------------------------- the verdict, and its direction
check("a box that holds the figure and nothing else is OK",
      R.verdict(1.0, 0.0) == "OK")
check("a box that clips the figure is WRONG",
      R.verdict(0.44, 0.0) == "WRONG")
check("a box that swallows a neighbour is WRONG even when it holds its own",
      R.verdict(0.96, 1.00) == "WRONG")
check("the two thresholds sit between the failures and the passes",
      0.44 < R.COVERED_FLOOR <= 0.93 and 0.02 <= R.INTRUSION_CEILING < 1.00,
      "%s / %s" % (R.COVERED_FLOOR, R.INTRUSION_CEILING))

# ------------------------------------------------- the calibration mechanism
_perfect = [(k, 1.0, 0.0, v) for k, v in T.VISUAL_VERDICT.items()]
check("a harness that agrees with the person passes calibration",
      R.calibrate(_perfect) == [], "%s" % R.calibrate(_perfect))
_lying = [(k, 1.0, 0.0, "OK") for k in T.VISUAL_VERDICT]
_wrongs = [k for k, v in T.VISUAL_VERDICT.items() if v == "WRONG"]
check("a harness that calls every crop fine is caught by calibration",
      len(R.calibrate(_lying)) == len(_wrongs), "%s" % R.calibrate(_lying))
check("a harness that scores nothing is caught too",
      len(R.calibrate([])) == len(T.VISUAL_VERDICT))
check("and the report says what the person said and what the harness said",
      all(len(row) == 3 for row in R.calibrate(_lying)))

# ------------------------------------------------------ the fixture itself
check("every recorded verdict has a region to score against",
      all(k in T.FIGURE_REGIONS for k in T.VISUAL_VERDICT),
      "%s" % [k for k in T.VISUAL_VERDICT if k not in T.FIGURE_REGIONS])
check("the fixture holds cases a person passed AND cases they failed",
      set(T.VISUAL_VERDICT.values()) == {"OK", "WRONG"})
check("every region is a box inside the page",
      all(0.0 <= b[0] < b[2] <= 1.0 and 0.0 <= b[1] < b[3] <= 1.0
          for b in T.FIGURE_REGIONS.values()),
      "%s" % [k for k, b in T.FIGURE_REGIONS.items()
              if not (0.0 <= b[0] < b[2] <= 1.0 and 0.0 <= b[1] < b[3] <= 1.0)])
check("no region is a sliver - a figure occupies real area",
      all(T.area(b) > 0.01 for b in T.FIGURE_REGIONS.values()))
check("the pages with two figures record BOTH, or intrusion cannot be seen",
      len(T.regions_on("437", "176")) >= 2
      and len(T.regions_on("516", "4")) == 2,
      "%s" % sorted(T.regions_on("437", "176")))
check("regions_on answers with the labels on that page only",
      set(T.regions_on("516", "4")) == {"FIG1", "FIG2"},
      "%s" % sorted(T.regions_on("516", "4")))
check("and nothing for a page that has none",
      T.regions_on("516", "99") == {})

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
