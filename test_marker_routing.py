# -*- coding: utf-8 -*-
"""What `marker_routing` establishes on the twin-axis fixture, and what it does not.

    python3 test_marker_routing.py     # exit 0 = all scenarios pass

This is the first half of a capability the package does not have: which of
several monochrome marker series each mark belongs to. It is pinned here in the
state it is actually in -

    the marker SCALE is measured off the panel and tracks the rendering
    the marks are FOUND, with the regression lines that join them removed
    a blob holding TWO markers is refused rather than reported at a position
      where nothing was drawn
    the FILL axis is established, on this marker's own ink
    the SHAPE axis is established by the radial third harmonic, which is the
      fourth discriminant tried and the first that a regression line crossing
      the marker cannot move

and it routes 16, 17 and 18 of 30 marks at 11, 22 and 33 px, 19 of 31 on the
rendering where two markers touch, WITH NO MISROUTES ANYWHERE, and refuses
everything at 5 px and 3 px.

## Two numbers in this file moved down, and that is the point

Every count here used to be scored by NEAREST TRUTH CENTRE, which lets one
record answer for two drawn marks. Under that scorer this suite reported 16, 18
and 20 routed with one misroute on the overlap rendering. Under one-to-one
matching the same code was routing 17, 19 and 20 with FOUR misroutes - three of
them invisible, because the record sat between two marks of the same series and
the nearer of the two was scored as its answer. A scorer that cannot see a wrong
answer is not a check, so it was replaced, and the numbers it was hiding are
what `off_centre_ink` now refuses.

Every number below was measured on `twin_scatter_*.jpeg`, which this repository
carries: the whole file runs in a fresh clone with no publisher figure.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image                                             # noqa: E402
import marker_routing as MRT                                      # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


TRUTH = os.path.join(HERE, "twin_scatter_truth.json")
if not os.path.exists(TRUTH):                                     # pragma: no cover
    import make_twin_scatter_fixture as TSF
    TSF.main()
DOC = json.load(open(TRUTH, encoding="utf-8"))


def routed(name):
    r = DOC["renderings"][name]
    path = os.path.join(HERE, r["file"])
    if not os.path.exists(path):                                  # pragma: no cover
        import make_twin_scatter_fixture as TSF
        TSF.main()
    series = [dict(id=sid, shape=spec["shape"], fill=spec["fill"])
              for sid, spec in sorted(r["series"].items())]
    out = MRT.route(Image.open(path).convert("RGB"), r["panel_box"], series,
                    expected_points=r["total_points"])
    truth = [(sid, cx, cy)
             for sid, spec in sorted(r["series"].items())
             for cx, cy in spec["centres"]]
    scale = out["marker_scale_px"] or 1.0
    # NOT_A_MARKER is furniture - numerals, titles, line fragments - and is not
    # a mark this reader claims to have seen. Everything else is.
    marks = [x for x in out["records"] if x["refusal"] != "NOT_A_MARKER"]
    pair = MRT.match_one_to_one(marks, truth, 0.6 * scale)
    right = wrong = refused = invented = 0
    fill_right = fill_wrong = 0
    for i, x in enumerate(marks):
        j = pair.get(i)
        if j is not None and x["fill"]:
            if x["fill"] == DOC["renderings"][name]["series"][truth[j][0]]["fill"]:
                fill_right += 1
            else:
                fill_wrong += 1
        if x["refusal"]:
            refused += 1
        elif j is None:
            invented += 1
        elif truth[j][0] == x["Series_ID"]:
            right += 1
        else:
            wrong += 1
    # THE FIXTURE'S COLUMNS ARE NOT THE READER'S COLUMNS, and they are named
    # apart. These count MARKS ON A DRAWING WHOSE ANSWER IS KNOWN, matched
    # one-to-one; `route` counts CANDIDATE RECORDS and can do no better, because
    # a reader has no truth to match against. Sharing the name `detected`
    # between them put an unresolved glyph and a real marker in one column.
    return dict(out=out, drawn=r["total_points"], marker=r["marker_diameter_px"],
                scale=scale,
                Truth_Matched_Point_Count=len(pair),
                Truth_Missed_Point_Count=r["total_points"] - len(pair),
                Candidate_Mark_Record_Count=len(marks),
                Candidate_Unresolved_Count=refused,
                Candidate_Invented_Count=invented,
                right=right, wrong=wrong,
                fill_right=fill_right, fill_wrong=fill_wrong,
                assigned=sum(1 for x in out["records"] if x["Series_ID"]),
                refusals=sorted({x["refusal"] for x in out["records"] if x["refusal"]}))


R = {name: routed(name) for name in sorted(DOC["renderings"])}
SCALED = ("s1", "s2", "s3")

print("the marker size is measured off the panel, not written down")
# A marker is not a number of pixels. The same drawing at three scales must give
# three scales, each within a pixel of what was drawn.
check("the measured scale is the drawn marker, at every rendering",
      all(abs(R[n]["scale"] - R[n]["marker"]) <= 1.0 for n in R),
      "%r" % {n: (R[n]["marker"], R[n]["scale"]) for n in sorted(R)})

print()
print("every mark is accounted for, in two differently named sets of columns")
# A TABLE THAT SHOWS ONLY WHAT WAS ROUTED CANNOT BE WRONG. The fixture's columns
# count MARKS ON THE DRAWING, matched one-to-one; `route`'s columns count
# CANDIDATE RECORDS, which is all a reader can count. Both have to add up, and
# they add up to different totals - which is why they no longer share a name.
check("the candidate columns add up at every rendering",
      all(R[n]["right"] + R[n]["wrong"] + R[n]["Candidate_Unresolved_Count"]
          + R[n]["Candidate_Invented_Count"]
          == R[n]["Candidate_Mark_Record_Count"] for n in R),
      "%r" % {n: (R[n]["right"], R[n]["wrong"],
                  R[n]["Candidate_Unresolved_Count"],
                  R[n]["Candidate_Invented_Count"],
                  R[n]["Candidate_Mark_Record_Count"]) for n in sorted(R)})
check("  and the truth columns add up to what was drawn",
      all(R[n]["Truth_Matched_Point_Count"] + R[n]["Truth_Missed_Point_Count"]
          == R[n]["drawn"] for n in R),
      "%r" % {n: (R[n]["Truth_Matched_Point_Count"],
                  R[n]["Truth_Missed_Point_Count"], R[n]["drawn"])
              for n in sorted(R)})
# AND THE TWO ARE NOT THE SAME NUMBER, which is the whole reason for the split.
# At 3 px there are 28 candidate records and 11 drawn marks behind them.
check("  the two totals differ where a reader admits what is not a marker",
      R["micro"]["Candidate_Mark_Record_Count"] == 28
      and R["micro"]["Truth_Matched_Point_Count"] == 11,
      "%r" % ((R["micro"]["Candidate_Mark_Record_Count"],
               R["micro"]["Truth_Matched_Point_Count"]),))
check("  19, 20 and 21 of 30 drawn marks are matched at 11, 22 and 33 px",
      [R[n]["Truth_Matched_Point_Count"] for n in SCALED] == [19, 20, 21],
      "%r" % {n: R[n]["Truth_Matched_Point_Count"] for n in SCALED})
# AND THE MARKS IT NEVER SAW ARE COUNTED, which is the column a gallery hides.
check("  and the 11, 10 and 9 it never saw are counted as missed",
      [R[n]["Truth_Missed_Point_Count"] for n in SCALED] == [11, 10, 9],
      "%r" % {n: R[n]["Truth_Missed_Point_Count"] for n in SCALED})
check("  no record is invented at any rendering",
      all(R[n]["Candidate_Invented_Count"] == 0 for n in R),
      "%r" % {n: R[n]["Candidate_Invented_Count"] for n in sorted(R)})
# THE COUNTS TRAVEL WITH THE ROUTE, not just with this suite: a caller that
# never scores against a fixture still gets told how many candidate records the
# panel produced and how many of those could not be routed.
check("  route reports candidate counts, and calls them candidates",
      all(R[n]["out"]["Candidate_Mark_Record_Count"]
          == R[n]["Candidate_Mark_Record_Count"]
          and R[n]["out"]["Routed_Point_Count"] == R[n]["right"] + R[n]["wrong"]
          and R[n]["out"]["Unresolved_Candidate_Count"]
          == R[n]["Candidate_Unresolved_Count"]
          for n in R)
      and "Detected_Point_Count" not in R["s3"]["out"],
      "%r" % {n: (R[n]["out"]["Candidate_Mark_Record_Count"],
                  R[n]["out"]["Routed_Point_Count"]) for n in sorted(R)})
check("  and disagrees with a declared point count when it should",
      all(R[n]["out"]["Candidate_Count_Agreement"] == MRT.COUNT_DISAGREES
          for n in R),
      "%r" % {n: R[n]["out"]["Candidate_Count_Agreement"] for n in sorted(R)})
_r3 = DOC["renderings"]["s3"]


def _route_s3(**kw):
    return MRT.route(Image.open(os.path.join(HERE, _r3["file"])).convert("RGB"),
                     _r3["panel_box"],
                     [dict(id=s, shape=p["shape"], fill=p["fill"])
                      for s, p in sorted(_r3["series"].items())], **kw)


# THE AGREEING VERDICT IS NAMED FOR WHAT IT IS WORTH. Even at s3, where the
# candidate count equals what a person would count, three candidates are
# unresolved - so the count alone does not agree, and the name of the value that
# would say so still refuses to say "complete".
_agree = _route_s3(expected_points=R["s3"]["Candidate_Mark_Record_Count"])
check("  a matching count with unresolved candidates still disagrees",
      _agree["Candidate_Count_Agreement"] == MRT.COUNT_DISAGREES
      and _agree["Unresolved_Candidate_Count"] == 3,
      "%r" % (_agree["Candidate_Count_Agreement"],))
check("  and the agreeing verdict says it is not a completeness proof",
      MRT.COUNT_AGREES == "COUNT_AGREES_NOT_COMPLETENESS"
      and MRT._counts([dict(refusal="", Series_ID="A"),
                       dict(refusal="", Series_ID="B")],
                      2)["Candidate_Count_Agreement"] == MRT.COUNT_AGREES,
      "%r" % (MRT.COUNT_AGREES,))
check("  a route asked for no expected count says so rather than agreeing",
      _route_s3()["Candidate_Count_Agreement"] == "",
      "an absent expected count read as agreement")

print()
print("the scorer is minimum-cost, not merely maximum-cardinality")
# A SCORER THAT JUDGES A READER MUST NOT BE WEAKER THAN THE READER. Greedy over
# increasing distance plus augmenting paths reaches maximum cardinality and
# stops there - and where two matchings pair the same number of marks it takes
# whichever the augmenting order happened to build. Here both matchings pair
# two, and they disagree about WHICH record is which mark, which is exactly the
# right/wrong distinction the fixture exists to measure.
_REC = [dict(point_px_x=0.0, point_px_y=0.0), dict(point_px_x=4.0, point_px_y=0.0)]
_TRU = [("S_P", 3.0, 0.0), ("S_Q", 5.0, 0.0)]


def _greedy_then_augment(records, truth, tol):
    """What the previous scorer did, kept here so the difference is visible."""
    cand = sorted((((t[1] - x["point_px_x"]) ** 2
                    + (t[2] - x["point_px_y"]) ** 2) ** 0.5, i, j)
                  for i, x in enumerate(records) for j, t in enumerate(truth))
    cand = [e for e in cand if e[0] <= tol]
    edges = {}
    for _d, i, j in cand:
        edges.setdefault(i, []).append(j)
    of_rec, of_truth = {}, {}
    for _d, i, j in cand:
        if i not in of_rec and j not in of_truth:
            of_rec[i], of_truth[j] = j, i

    def augment(i, seen):
        for j in edges.get(i, ()):
            if j in seen:
                continue
            seen.add(j)
            if j not in of_truth or augment(of_truth[j], seen):
                of_rec[i], of_truth[j] = j, i
                return True
        return False
    for i in range(len(records)):
        if i not in of_rec:
            augment(i, set())
    return of_rec


def _total(pairing):
    return sum(abs(_TRU[j][1] - _REC[i]["point_px_x"])
               for i, j in pairing.items())


_mincost = MRT.match_one_to_one(_REC, _TRU, 6.0)
_greedy = _greedy_then_augment(_REC, _TRU, 6.0)
check("both scorers pair two marks and they disagree about which",
      len(_mincost) == len(_greedy) == 2 and _mincost != _greedy,
      "%r vs %r" % (_mincost, _greedy))
check("  and the minimum-cost pairing is the closer one, 4.0 against 6.0",
      abs(_total(_mincost) - 4.0) < 1e-9 and abs(_total(_greedy) - 6.0) < 1e-9,
      "%.3f vs %.3f" % (_total(_mincost), _total(_greedy)))
# AND IT IS THE SAME ANSWER EVERY TIME, WHATEVER ORDER THE ROWS ARRIVE IN.
# The index term underneath the distance orders equal-cost EDGES, and that is
# not enough to order equal-cost MATCHINGS: in a symmetric two-by-two both
# pairings sum to the same secondary total, so the answer was decided by the
# caller's row order. A scorer reading a fixture always passes the same order; a
# VERIFIER is handed rows off a CSV somebody may have sorted, and this function
# is now both. So both sides are canonicalised by position first.
# FOUR DISTINCT POINTS AND A REAL TIE. Two records on a line and two marks
# symmetrically above and below it: all four distances are the same, so both
# matchings cost the same and the secondary index term costs the same too. A
# configuration where the two records share a coordinate would NOT show this -
# every pairing gives the same coordinate multiset there, which is a scenario
# that cannot fail.
_SYM = [dict(point_px_x=0.0, point_px_y=0.0), dict(point_px_x=2.0, point_px_y=0.0)]
_SYMT = [("A", 1.0, 1.0), ("B", 1.0, -1.0)]


def _paired(records, truth):
    """The pairing as COORDINATES, which is what has to be order-invariant."""
    got = MRT.match_one_to_one(records, truth, 4.0)
    return sorted((records[i]["point_px_x"], truth[j][2])
                  for i, j in got.items())


check("  a perfectly symmetric tie resolves the same way every time",
      _paired(_SYM, _SYMT) == _paired(_SYM[::-1], _SYMT)
      == _paired(_SYM, _SYMT[::-1]) == _paired(_SYM[::-1], _SYMT[::-1])
      and all(MRT.match_one_to_one(_REC, _TRU, 6.0) == _mincost
              for _ in range(5)),
      "%r vs %r" % (_paired(_SYM, _SYMT), _paired(_SYM[::-1], _SYMT)))
# AND THE SAME OF THE ASYMMETRIC CASE, where the answer is not a tie at all:
# reversing the input must not move which record answers for which mark.
def _paired_x(records, truth):
    got = MRT.match_one_to_one(records, truth, 6.0)
    return sorted((records[i]["point_px_x"], truth[j][1])
                  for i, j in got.items())


check("    and reversing either side changes no pairing anywhere",
      _paired_x(_REC, _TRU) == _paired_x(_REC[::-1], _TRU)
      == _paired_x(_REC, _TRU[::-1]),
      "%r vs %r" % (_paired_x(_REC, _TRU), _paired_x(_REC[::-1], _TRU)))

print()
print("a blob holding two markers is refused, not reported at neither")
# `off_centre_ink` REPLACED A BOUNDING-BOX RATIO. Two markers 0.55 of a marker
# apart give a box 1.5 markers wide - under the old SIZE_HI of 1.75 - and a
# centroid at neither of them.
_singles = [x["off_centre_ink"] for n in SCALED + ("overlap",)
            for x in R[n]["out"]["records"] if not x["refusal"] and x["Series_ID"]]
_merged = [x["off_centre_ink"] for n in SCALED + ("overlap",)
           for x in R[n]["out"]["records"] if x["refusal"] == "MARKER_MERGED"]
# THE CONSTANT IS ASSERTED TO BE INSIDE THE GAP, not asserted to be some round
# number: what matters is that no single mark reaches it and every merged blob
# passes it, at all four renderings that resolve. Measured, the gap is 0.101 to
# 0.345 and `OFF_CENTRE` is 0.25 - 2.5x the worst single, 0.72x the best pair.
check("no single mark reaches OFF_CENTRE and every merged blob passes it",
      max(_singles) < MRT.OFF_CENTRE < min(_merged),
      "singles up to %.3f, merged from %.3f, OFF_CENTRE %.2f"
      % (max(_singles), min(_merged), MRT.OFF_CENTRE))
check("  and the gap between the two is at least threefold",
      min(_merged) / max(_singles) >= 3.0,
      "%.3f / %.3f = %.2f" % (min(_merged), max(_singles),
                              min(_merged) / max(_singles)))
check("  two marks that touch each other are refused, not split",
      all("MARKER_MERGED" in R[n]["refusals"] for n in SCALED + ("overlap",)),
      "%r" % {n: R[n]["refusals"] for n in SCALED + ("overlap",)})
# REVERT: OFF_CENTRE to 1.0, which is the guard switched off. Six marks across
# the family are then routed to the wrong series - one at 11 px, one at 22 px,
# one at 33 px and three on the overlap rendering - which is what this guard is
# for and what the nearest-truth scorer could not see.
#
# IT WAS FOUR UNTIL THE FILL QUESTION WAS ASKED PER SHAPE. A merged blob has the
# ink of two markers in its middle, so its interior ink lands where neither
# marker's does; pooled with every other mark on the panel that reading was
# often outside the split's reach and the blob came back FILL_UNRESOLVED, which
# counted as a refusal rather than a misroute. Asked inside its own shape's
# group the same blob sits inside a tighter distribution and gets an answer -
# a wrong one, because the blob is not one marker. The guard's removal is more
# visible than it was, not less.
_was = MRT.OFF_CENTRE
try:
    MRT.OFF_CENTRE = 1.0
    _off = {n: routed(n) for n in SCALED + ("overlap",)}
finally:
    MRT.OFF_CENTRE = _was
check("  without it six marks across the family are misrouted",
      sum(_off[n]["wrong"] for n in _off) == 6
      and all(R[n]["wrong"] == 0 for n in _off),
      "%r" % {n: (_off[n]["right"], _off[n]["wrong"]) for n in sorted(_off)})

print()
print("the fill axis is established by the panel's own distribution")
check("every fill is right at 22 and 33 px",
      all(R[n]["fill_wrong"] == 0 and R[n]["fill_right"] >= 17
          for n in ("s2", "s3")),
      "%r" % {n: (R[n]["fill_right"], R[n]["fill_wrong"]) for n in ("s2", "s3")})
# AT 11 PX TWO MARKS SIT ON THE BOUNDARY and are refused individually. The panel
# still separates; those two do not, and `MARK_MARGIN` is what tells the two
# questions apart. Before it, one of them was routed to the wrong series.
check("  at 11 px no fill is wrong either",
      R["s1"]["fill_wrong"] == 0,
      "%d wrong, refusals %r" % (R["s1"]["fill_wrong"], R["s1"]["refusals"]))
check("  and at 3 px there is no fill split at all",
      not R["micro"]["out"]["fill_split"]["separates"],
      "%r" % (R["micro"]["out"]["fill_split"],))

print()
print("no mark's fill is measured with another component's ink in it")
# PINNED AS A NEGATIVE, and it is the reason `MARKER_OVERLAP_CONTAMINATED` is
# not a refusal in `marker_routing`. The fill window's farthest corner is 0.40
# of a marker from the centre and `fill_holes` has already made this mark a
# solid footprint 0.50 of a marker in radius, so ink in the window is this
# mark's own by construction. The day a rendering disagrees, this scenario fails
# and the refusal has to be written.
_all = [x for n in R for x in R[n]["out"]["records"] if "Fill_Score_Window" in x]
check("no foreign ink reaches any fill window, at any rendering",
      all(not x["Neighbour_Component_IDs"]
          and x["Foreign_Ink_Pixels_In_Fill_ROI"] == 0 for x in _all),
      "%r" % [(x["Original_Component_ID"], x["Neighbour_Component_IDs"])
              for x in _all if x["Neighbour_Component_IDs"]][:4])
check("  so the window score and this component's own score never differ",
      all(x["Fill_Score_Window"] == x["Fill_Score_Own_Component"]
          and not x["Classification_Changes_When_Foreign_Removed"]
          for x in _all),
      "%r" % [(x["Fill_Score_Window"], x["Fill_Score_Own_Component"])
              for x in _all
              if x["Fill_Score_Window"] != x["Fill_Score_Own_Component"]][:4])
check("  and every mark says which component it came from",
      all(x["Original_Component_ID"] > 0 for x in _all),
      "%r" % [x["Original_Component_ID"] for x in _all[:6]])

print()
print("the shape axis, by the radial third harmonic")
# THE FOURTH DISCRIMINANT. Circularity, corner count and bbox extent all failed
# on the same thing - a regression line crosses the marker - and a radial profile
# is not taken on the outline: a triangle puts its energy at order three while a
# line's exit spikes spread theirs over every harmonic.
check("the shape axis separates at 11 px and above",
      all(R[n]["out"]["shape_split"]["separates"] for n in SCALED),
      "%r" % {n: R[n]["out"]["shape_split"]["separates"] for n in SCALED})
check("  and does not at 5 px or 3 px, where nothing is routed",
      not R["tiny"]["out"]["shape_split"]["separates"]
      and not R["micro"]["out"]["shape_split"]["separates"]
      and R["tiny"]["assigned"] == R["micro"]["assigned"] == 0,
      "%r" % {n: (R[n]["out"]["shape_split"]["separates"], R[n]["assigned"])
              for n in ("tiny", "micro")})
check("  and every routed mark still carries all four measurements",
      all(set(("circularity", "corners", "bbox_extent", "third_harmonic"))
          <= set(x) for x in R["s3"]["out"]["records"]),
      "%r" % (sorted(R["s3"]["out"]["records"][0]),))

print()
print("what it routes, and what it gets wrong")
check("16, 17 and 18 marks routed at 11, 22 and 33 px, and none misrouted",
      [R[n]["right"] for n in SCALED] == [16, 17, 18]
      and all(R[n]["wrong"] == 0 for n in SCALED),
      "%r" % {n: (R[n]["right"], R[n]["wrong"]) for n in SCALED})
# THE MISROUTE THAT USED TO BE PINNED HERE IS GONE, and it was never one: under
# one-to-one scoring the same code had four.
check("  and the overlap rendering routes 19 with none misrouted",
      (R["overlap"]["right"], R["overlap"]["wrong"]) == (19, 0),
      "%d right, %d wrong" % (R["overlap"]["right"], R["overlap"]["wrong"]))

print()
print("a declaration that names one marker twice refuses the whole panel")
# NOT A REFUSAL PER MARK. `declared` is a dict, so the second series silently
# won and every mark of both was routed to whichever name came last.
_dup = [dict(id=s, shape=p["shape"], fill=p["fill"])
        for s, p in sorted(_r3["series"].items())]
_dup = _dup + [dict(id="TYPO", shape=_dup[0]["shape"], fill=_dup[0]["fill"])]
try:
    MRT.route(Image.open(os.path.join(HERE, _r3["file"])).convert("RGB"),
              _r3["panel_box"], _dup)
    _msg = ""
except ValueError as exc:
    _msg = "%s" % exc
check("two series declared with the same marker are refused",
      MRT.DUPLICATE_DECLARATION in _msg and "TYPO" in _msg, "%r" % (_msg,))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
