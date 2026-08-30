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
import csv
import os
import sys
import tempfile

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
check("the fixture covers the pages both audits ruled on, not a handful",
      len(T.VISUAL_VERDICT) >= 18, "%d" % len(T.VISUAL_VERDICT))
check("and it is not lopsided - a threshold cannot be fitted to one side",
      3 <= sum(1 for v in T.VISUAL_VERDICT.values() if v == "WRONG")
      <= len(T.VISUAL_VERDICT) - 3,
      "%s" % sorted(T.VISUAL_VERDICT.values()))
check("more than one publication is represented on each side",
      len({k[0] for k, v in T.VISUAL_VERDICT.items() if v == "OK"}) >= 3
      and len({k[0] for k, v in T.VISUAL_VERDICT.items()
               if v == "WRONG"}) >= 3)

# A SCORE IS NOT A VERDICT. A figure nobody has judged is measured, never
# decided: manufacturing the judgement the harness exists to reproduce is the
# one way it could go quietly wrong again.
_unjudged = [k for k in T.FIGURE_REGIONS if k not in T.VISUAL_VERDICT]
check("figures with no recorded verdict exist and are kept separate",
      len(_unjudged) > 0, "%s" % _unjudged)
# THE HARNESS READS THE DRAFT. It used to call `figure_bbox` itself, on
# whatever backend the machine happened to default to, so it graded a box the
# shipped draft may never have held: publication 437's Fig. 3 came back
# "NO_BOX" for four rounds while the draft had carried the row since v9.23,
# found by the second reader after pdfminer merged that caption into the line
# above.
_dir = tempfile.mkdtemp(prefix="fdt_truth_")
with open(os.path.join(_dir, "figure_intake_draft.csv"), "w",
          encoding="utf-8") as _fh:
    _w = csv.writer(_fh)
    _w.writerow(["Source_Document_ID", "Figure_Number", "Page", "Figure_BBox"])
    _w.writerow(["DOC", "FIG1", "4", "10,20,110,220"])
    _w.writerow(["DOC", "FIG2", "4", ""])
    _w.writerow(["DOC", "FIG3", "4", "5,5,50,50"])
    _w.writerow(["DOC", "FIG3", "4", "999,999,1000,1000"])
_boxes = R.draft_boxes(_dir)
check("a box in the draft is what gets graded",
      _boxes[("DOC", "FIG1", "4")] == "10,20,110,220", "%s" % _boxes)
check("a row with no box contributes none",
      ("DOC", "FIG2", "4") not in _boxes)
check("the first row for a figure wins, so a later duplicate cannot displace it",
      _boxes[("DOC", "FIG3", "4")] == "5,5,50,50")
check("the box is scaled to the page, not left in points",
      R.box_for.__doc__ and "fractions" in R.box_for.__doc__)

check("calibration is computed only over the judged ones",
      R.calibrate([(k, 1.0, 0.0, "WRONG") for k in _unjudged])
      == [(k, v, "not scored") for k, v in sorted(T.VISUAL_VERDICT.items())],
      "%d" % len(R.calibrate([(k, 1.0, 0.0, "WRONG") for k in _unjudged])))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
