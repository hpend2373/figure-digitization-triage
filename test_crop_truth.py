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
      R.calibrate(_perfect)[0] == [], "%s" % (R.calibrate(_perfect)[0],))
_lying = [(k, 1.0, 0.0, "OK") for k in T.VISUAL_VERDICT]
_wrongs = [k for k, v in T.VISUAL_VERDICT.items() if v == "WRONG"]
check("a harness that calls every crop fine is caught by calibration",
      len(R.calibrate(_lying)[0]) == len(_wrongs), "%s" % (R.calibrate(_lying)[0],))
check("a harness that scores nothing is caught too",
      len(R.calibrate([])[0]) == len(T.VISUAL_VERDICT))
check("and the report says what the person said and what the harness said",
      all(len(row) == 3 for row in R.calibrate(_lying)[0]))

# ------------------------------- a refusal is not a disagreement, if recorded
# Equality was the whole rule, so a crop the harness stopped being able to
# score read the same as one it got wrong - and those are opposite things.
_refusable = sorted(T.NOT_SCORABLE)
check("픽스처가 점수 불가로 기록한 항목이 있다", bool(_refusable))
_refused = [(k, 1.0, 0.0, R.UNTRUSTED if k in T.NOT_SCORABLE else v)
            for k, v in T.VISUAL_VERDICT.items()]
_bad, _tol = R.calibrate(_refused)
check("기록된 항목의 점수 불가는 실패가 아니라 별도로 보고된다",
      _bad == [] and sorted(k for k, _w, _h in _tol) == _refusable,
      "%s / %s" % (_bad, _tol))
_new_refusal = [(k, 1.0, 0.0,
                 R.AMBIGUOUS if k == _wrongs[0] and k not in T.NOT_SCORABLE
                 else v)
                for k, v in T.VISUAL_VERDICT.items()]
check("기록에 없는 새 점수 불가는 실패다",
      [k for k, _w, _h in R.calibrate(_new_refusal)[0]] == [_wrongs[0]],
      "%s" % (R.calibrate(_new_refusal)[0],))
_permissive = [(k, 1.0, 0.0, "OK" if k in T.NOT_SCORABLE else v)
               for k, v in T.VISUAL_VERDICT.items()]
check("점수 불가로 기록된 항목이라도 OK라고 하면 실패다 - 사람은 WRONG이라 했다",
      sorted(k for k, _w, _h in R.calibrate(_permissive)[0]) == _refusable,
      "%s" % (R.calibrate(_permissive)[0],))
check("점수 불가 기록에는 사람이 쓴 사유가 붙어 있다",
      all(isinstance(v, str) and len(v.strip()) > 10
          for v in T.NOT_SCORABLE.values()))

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
COLS = ["Source_Document_ID", "Figure_Number", "Page", "Figure_BBox",
        "Page_Width_Pt", "Page_Height_Pt", "Page_Geometry_Method"]


def _draft(rows):
    d = tempfile.mkdtemp(prefix="fdt_truth_")
    with open(os.path.join(d, "figure_intake_draft.csv"), "w",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for r in rows:
            w.writerow(r)
    return R.draft_rows(d)


_e = _draft([["DOC", "FIG1", "4", "61.2,79.2,306.0,396.0", "612", "792", "PYPDF_MEDIABOX"],
             ["DOC", "FIG2", "4", "", "612", "792", "PYPDF_MEDIABOX"]])
check("a box in the draft is what gets graded",
      _e[("DOC", "FIG1", "4")]["box"] == "61.2,79.2,306.0,396.0", "%s" % _e)
check("a row with no box contributes none", ("DOC", "FIG2", "4") not in _e)

# THE DENOMINATOR IS THE PAGE THE DRAFT RECORDED. The harness used to work the
# page size out from the text on it, and text stops short of the paper: this
# box is exactly a tenth-to-half of a 612 x 792 page, and against a text extent
# of, say, 306 x 396 it would read as half-to-whole.
_box, _st = R.box_for(_e[("DOC", "FIG1", "4")])
check("the box is scaled by the page the draft wrote down", _st == "OK", _st)
check("and the fractions are the page's, not the printing's",
      _box and abs(_box[0] - 0.1) < 1e-6 and abs(_box[2] - 0.5) < 1e-6,
      "%s" % (_box,))

_missing = _draft([["DOC", "FIG1", "4", "10,20,110,220", "", "", "UNKNOWN"]])
check("a row whose page size was never read is not scored",
      R.box_for(_missing[("DOC", "FIG1", "4")])[1] == R.NO_PAGE_SIZE)
_zero = _draft([["DOC", "FIG1", "4", "10,20,110,220", "0", "792", "UNKNOWN"]])
check("and neither is one whose page has no width",
      R.box_for(_zero[("DOC", "FIG1", "4")])[1] == R.NO_PAGE_SIZE)

# A KEY CLAIMED TWICE IS NOT A TIE TO BREAK.
_same = _draft([["DOC", "FIG3", "4", "5,5,50,50", "612", "792", "PYPDF_MEDIABOX"],
                ["DOC", "FIG3", "4", "5,5,50,50", "612", "792", "PYPDF_MEDIABOX"]])
check("the same box proposed twice is one box",
      R.box_for(_same[("DOC", "FIG3", "4")])[1] == "OK")
_diff = _draft([["DOC", "FIG3", "4", "5,5,50,50", "612", "792", "PYPDF_MEDIABOX"],
                ["DOC", "FIG3", "4", "9,9,99,99", "612", "792", "PYPDF_MEDIABOX"]])
check("two different boxes for one figure are AMBIGUOUS, not first-wins",
      R.box_for(_diff[("DOC", "FIG3", "4")])[1] == R.AMBIGUOUS)
check("and both candidates are kept for a person to look at",
      sorted(_diff[("DOC", "FIG3", "4")]["candidates"])
      == ["5,5,50,50", "9,9,99,99"],
      "%s" % _diff[("DOC", "FIG3", "4")]["candidates"])
check("the ambiguous row is measured as nothing, not scored",
      R.box_for(_diff[("DOC", "FIG3", "4")])[0] is None)

# TWO DOCUMENTS MAY SHARE A FILENAME. The harness used to find the PDF by
# basename, so `a/fulltext.pdf` and `b/fulltext.pdf` collapsed to whichever the
# staged list named last, and one publication's box was scored against the
# other's page. Nothing here opens a PDF at all now; the document id is the
# join, and it is in the draft.
_two = _draft([["DOC_A", "FIG1", "4", "61.2,0,122.4,79.2", "612", "792", "PYPDF_MEDIABOX"],
               ["DOC_B", "FIG1", "4", "297.5,0,595.0,84.2", "595", "842", "PYPDF_MEDIABOX"]])
check("two documents keep their own boxes even under one filename",
      len(_two) == 2)
check("and each is scaled by its OWN page size",
      abs(R.box_for(_two[("DOC_A", "FIG1", "4")])[0][0] - 0.1) < 1e-6
      and abs(R.box_for(_two[("DOC_B", "FIG1", "4")])[0][0] - 0.5) < 1e-6,
      "%s / %s" % (R.box_for(_two[("DOC_A", "FIG1", "4")])[0],
                   R.box_for(_two[("DOC_B", "FIG1", "4")])[0]))
# THE HARNESS OPENS NO PDF. Not "finds the right one" - opens none at all, so
# there is no file to resolve and no basename to collide.
_SRC = open(os.path.join(HERE, "sheet", "regress_crop.py"),
            encoding="utf-8").read()
check("the harness imports no PDF reader",
      "import corpus_intake" not in _SRC and "pdfminer" not in _SRC
      and "pypdf" not in _SRC)
check("and reads no staged source list",
      "STAGED" not in _SRC)

# THE SAME POINTS OVER A DIFFERENT DENOMINATOR ARE A DIFFERENT FRACTION. Two
# rows can carry an identical Figure_BBox and disagree about the page - one
# read from a MediaBox, one from `pdfinfo` on a document whose pages are not
# all the same size - and comparing the boxes alone let file order choose which
# denominator won.
_geo_conflict = _draft([
    ["DOC", "FIG1", "4", "61.2,0,306.0,396.0", "612", "792", "PYPDF_MEDIABOX"],
    ["DOC", "FIG1", "4", "61.2,0,306.0,396.0", "595", "842", "PDFINFO_UNIFORM"]])
check("one box and two page sizes is ambiguous, not first-wins",
      R.box_for(_geo_conflict[("DOC", "FIG1", "4")])[1] == R.AMBIGUOUS)

# A PAGE HAS ONE SIZE. Even where each figure's own rows agree, two figures on
# one page that disagree about how big it is cannot both be right.
_page_split = _draft([
    ["DOC", "FIG1", "4", "10,10,100,100", "612", "792", "PYPDF_MEDIABOX"],
    ["DOC", "FIG2", "4", "10,10,100,100", "595", "842", "PYPDF_MEDIABOX"]])
check("two figures disagreeing about their shared page are both held",
      R.box_for(_page_split[("DOC", "FIG1", "4")])[1] == R.UNTRUSTED
      and R.box_for(_page_split[("DOC", "FIG2", "4")])[1] == R.UNTRUSTED)
check("and a page whose rows agree is untouched by that rule",
      R.box_for(_draft([
          ["DOC", "FIG1", "4", "10,10,100,100", "612", "792", "PYPDF_MEDIABOX"],
          ["DOC", "FIG2", "4", "20,20,200,200", "612", "792", "PYPDF_MEDIABOX"]
      ])[("DOC", "FIG1", "4")])[1] == "OK")

# A SIZE NOTHING MEASURED IS NOT A SIZE. UNKNOWN is what `page_geometry`
# returns when all three ways failed; writing plausible numbers beside it would
# make the harness score against a guess.
check("a page size no backend actually read is not scored against",
      R.box_for(_draft([["DOC", "FIG1", "4", "10,10,100,100",
                         "612", "792", "UNKNOWN"]])[("DOC", "FIG1", "4")])[1]
      == R.UNTRUSTED)
check("and only the three real methods are trusted",
      set(R.TRUSTED_METHODS)
      == {"PYPDF_MEDIABOX", "PDFMINER_LAYOUT", "PDFINFO_UNIFORM"})

# A BOX OUTSIDE ITS OWN PAGE IS A COORDINATE SYSTEM MISMATCH, not a crop.
# Normalising it yields a fraction above 1.0, which reads like an answer.
for _label, _bbox in (("wider than the paper", "10,10,900,100"),
                      ("taller than the paper", "10,10,100,900"),
                      ("starting left of the paper", "-5,10,100,100"),
                      ("inverted in x", "300,10,100,100"),
                      ("inverted in y", "10,300,100,100")):
    check("a box %s is not scored" % _label,
          R.box_for(_draft([["DOC", "FIG1", "4", _bbox, "612", "792",
                             "PYPDF_MEDIABOX"]])[("DOC", "FIG1", "4")])[1]
          == R.UNTRUSTED, _bbox)
check("a box that exactly fills the page is still scored",
      R.box_for(_draft([["DOC", "FIG1", "4", "0,0,612,792", "612", "792",
                         "PYPDF_MEDIABOX"]])[("DOC", "FIG1", "4")])[1] == "OK")
check("a page size that is not a number is missing, not untrusted",
      R.box_for(_draft([["DOC", "FIG1", "4", "10,10,100,100", "", "",
                         "PYPDF_MEDIABOX"]])[("DOC", "FIG1", "4")])[1]
      == R.NO_PAGE_SIZE)
check("and a non-finite page size is refused too",
      R.box_for(_draft([["DOC", "FIG1", "4", "10,10,100,100", "nan", "792",
                         "PYPDF_MEDIABOX"]])[("DOC", "FIG1", "4")])[1]
      == R.NO_PAGE_SIZE)


check("calibration is computed only over the judged ones",
      R.calibrate([(k, 1.0, 0.0, "WRONG") for k in _unjudged])[0]
      == [(k, v, "not scored") for k, v in sorted(T.VISUAL_VERDICT.items())],
      "%d" % len(R.calibrate([(k, 1.0, 0.0, "WRONG") for k in _unjudged])[0]))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
