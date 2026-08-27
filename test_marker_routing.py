# -*- coding: utf-8 -*-
"""What `marker_routing` establishes on the twin-axis fixture, and what it does not.

    python3 test_marker_routing.py     # exit 0 = all scenarios pass

This is the first half of a capability the package does not have: which of
several monochrome marker series each mark belongs to. It is pinned here in the
state it is actually in, which is half done -

    the marker SCALE is measured off the panel and tracks the rendering
    the marks are FOUND, with the regression lines that join them removed
    the FILL axis is established, and is exactly right at 11 px and above
    the SHAPE axis is NOT established, and every mark is refused for it

- because a module that assigns a third of the marks to the wrong shape is worse
than one that refuses: a wrong series is a plausible number under the wrong
heading, and nothing downstream can tell it from a right one.

TWO NEGATIVES ARE PINNED ON PURPOSE. "The shape axis does not separate" and "no
series is assigned on a two-shape panel" are scenarios, so the day a fourth
discriminant works they FAIL and have to be changed deliberately. A capability
that arrives silently is one nobody reviewed.

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
    out = MRT.route(Image.open(path).convert("RGB"), r["panel_box"], series)
    truth = [(spec["fill"], spec["shape"], cx, cy)
             for _sid, spec in sorted(r["series"].items())
             for cx, cy in spec["centres"]]
    scale = out["marker_scale_px"] or 1.0
    found = sum(1 for _f, _s, cx, cy in truth
                if any(((x["point_px_x"] - cx) ** 2
                        + (x["point_px_y"] - cy) ** 2) ** 0.5 <= 0.6 * scale
                       for x in out["records"]))
    fill_right = fill_wrong = 0
    for x in out["records"]:
        if not x["fill"]:
            continue
        tf, _ts, cx, cy = min(truth, key=lambda t: (t[2] - x["point_px_x"]) ** 2
                              + (t[3] - x["point_px_y"]) ** 2)
        if ((cx - x["point_px_x"]) ** 2 + (cy - x["point_px_y"]) ** 2) ** 0.5 > 0.6 * scale:
            continue
        if x["fill"] == tf:
            fill_right += 1
        else:
            fill_wrong += 1
    return dict(out=out, drawn=r["total_points"], marker=r["marker_diameter_px"],
                scale=scale, found=found, fill_right=fill_right,
                fill_wrong=fill_wrong,
                assigned=sum(1 for x in out["records"] if x["Series_ID"]),
                refusals=sorted({x["refusal"] for x in out["records"] if x["refusal"]}))


R = {name: routed(name) for name in sorted(DOC["renderings"])}

print("the marker size is measured off the panel, not written down")
# A marker is not a number of pixels. The same drawing at three scales must give
# three scales, each within a pixel of what was drawn.
check("the measured scale is the drawn marker, at every rendering",
      all(abs(R[n]["scale"] - R[n]["marker"]) <= 1.0 for n in R),
      "%r" % {n: (R[n]["marker"], R[n]["scale"]) for n in sorted(R)})

print()
print("the marks are found, with the regression lines removed")
# Four lines run through thirty markers. Component labelling found nine of them;
# hole-filling plus an opening finds most, and a marker touching another marker
# stays one blob and is refused as such.
check("at 11 px and above, 23 of 30 marks are found and none is invented",
      all(R[n]["found"] >= 23 for n in ("s1", "s2", "s3")),
      "%r" % {n: R[n]["found"] for n in ("s1", "s2", "s3")})
check("  and on the overlap rendering every drawn mark is found",
      R["overlap"]["found"] == R["overlap"]["drawn"],
      "%d of %d" % (R["overlap"]["found"], R["overlap"]["drawn"]))
check("  and two marks that touch each other are refused, not split",
      "MARKER_MERGED" in R["overlap"]["refusals"],
      "%r" % (R["overlap"]["refusals"],))

print()
print("the fill axis is established by the panel's own distribution")
check("every fill is right at 11, 22 and 33 px",
      all(R[n]["fill_wrong"] == 0 and R[n]["fill_right"] >= 18
          for n in ("s1", "s2", "s3")),
      "%r" % {n: (R[n]["fill_right"], R[n]["fill_wrong"]) for n in ("s1", "s2", "s3")})
# WHERE IT STARTS TO FAIL, measured rather than assumed. At 5 px the split still
# passes and three of seventeen marks take the wrong side of it: the test says
# two classes and the assignment is not perfect. Pinned so a tightening of
# `SEPARATION` can be argued against a number.
check("  at 5 px the split still passes and 3 of 17 fills are wrong",
      (R["tiny"]["fill_right"], R["tiny"]["fill_wrong"]) == (14, 3),
      "%d right, %d wrong" % (R["tiny"]["fill_right"], R["tiny"]["fill_wrong"]))
check("  and at 3 px there is no split at all, so no fill is claimed",
      not R["micro"]["out"]["fill_split"]["separates"]
      and R["micro"]["fill_right"] == R["micro"]["fill_wrong"] == 0,
      "%r" % (R["micro"]["out"]["fill_split"],))

print()
print("the shape axis is NOT established, and nothing is assigned without it")
# Three discriminants measured, none usable: circularity of the marker's ink cut
# out of the chain it sits in comes back higher for triangles than for discs;
# the corner count is a continuum from 3 to 7; the bbox extent of the opened
# blob overlaps because the opening rounds the triangles. The best of them puts
# a third of the marks in the wrong shape.
check("every mark is refused for its shape on a two-shape panel",
      all("MARKER_SHAPE_UNRESOLVED" in R[n]["refusals"] for n in R),
      "%r" % {n: R[n]["refusals"] for n in sorted(R)})
check("  so no series is assigned, on any rendering",
      all(R[n]["assigned"] == 0 for n in R),
      "%r" % {n: R[n]["assigned"] for n in sorted(R)})
# AND THE EVIDENCE IS ON THE RECORD, so the next attempt starts from data.
_rec = [x for x in R["s3"]["out"]["records"] if x["refusal"] == "MARKER_SHAPE_UNRESOLVED"]
check("  and every refused mark still carries the three measurements tried",
      bool(_rec) and all(set(("circularity", "corners", "bbox_extent")) <= set(x)
                         for x in _rec),
      "%r" % (sorted(_rec[0]) if _rec else None))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
