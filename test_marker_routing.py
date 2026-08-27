# -*- coding: utf-8 -*-
"""What `marker_routing` establishes on the twin-axis fixture, and what it does not.

    python3 test_marker_routing.py     # exit 0 = all scenarios pass

This is the first half of a capability the package does not have: which of
several monochrome marker series each mark belongs to. It is pinned here in the
state it is actually in, which is half done -

    the marker SCALE is measured off the panel and tracks the rendering
    the marks are FOUND, with the regression lines that join them removed
    the FILL axis is established, on this marker's own ink
    the SHAPE axis is established by the radial third harmonic, which is the
      fourth discriminant tried and the first that a regression line crossing
      the marker cannot move

and it routes 16, 18 and 20 of 30 marks at 11, 22 and 33 px with NO misroutes,
refuses everything at 5 px and 3 px, and gets exactly one mark wrong on the
rendering where two markers touch. That one is pinned as wrong rather than fixed:
the fix refuses five to thirteen legitimate marks per rendering.

THE TWO NEGATIVES THIS FILE USED TO PIN - "the shape axis does not separate" and
"no series is assigned" - are gone, which is what they were for. They failed the
moment the fourth discriminant worked and were changed on purpose. A capability
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
    right = wrong = 0
    for x in out["records"]:
        if not x["Series_ID"]:
            continue
        tf, ts, cx, cy = min(truth, key=lambda t: (t[2] - x["point_px_x"]) ** 2
                             + (t[3] - x["point_px_y"]) ** 2)
        near = ((cx - x["point_px_x"]) ** 2 + (cy - x["point_px_y"]) ** 2) ** 0.5
        want = next((sid for sid, spec in sorted(DOC["renderings"][name]["series"].items())
                     if [cx, cy] in [list(c) for c in spec["centres"]]), "")
        if near <= 0.6 * scale and want == x["Series_ID"]:
            right += 1
        else:
            wrong += 1
    return dict(out=out, drawn=r["total_points"], marker=r["marker_diameter_px"],
                scale=scale, found=found, fill_right=fill_right,
                fill_wrong=fill_wrong, right=right, wrong=wrong,
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
check("every fill is right at 22 and 33 px",
      all(R[n]["fill_wrong"] == 0 and R[n]["fill_right"] >= 18
          for n in ("s2", "s3")),
      "%r" % {n: (R[n]["fill_right"], R[n]["fill_wrong"]) for n in ("s2", "s3")})
# AT 11 PX TWO MARKS SIT ON THE BOUNDARY and are refused individually. The panel
# still separates; those two do not, and `MARK_MARGIN` is what tells the two
# questions apart. Before it, one of them was routed to the wrong series.
check("  at 11 px two marks sit on the fill boundary and are refused alone",
      R["s1"]["fill_wrong"] == 0
      and "MARKER_FILL_UNRESOLVED" in R["s1"]["refusals"],
      "%d wrong, refusals %r" % (R["s1"]["fill_wrong"], R["s1"]["refusals"]))
check("  and at 3 px there is no fill split at all",
      not R["micro"]["out"]["fill_split"]["separates"],
      "%r" % (R["micro"]["out"]["fill_split"],))

print()
print("the shape axis, by the radial third harmonic")
# THE FOURTH DISCRIMINANT. Circularity, corner count and bbox extent all failed
# on the same thing - a regression line crosses the marker - and a radial profile
# is not taken on the outline: a triangle puts its energy at order three while a
# line's exit spikes spread theirs over every harmonic.
check("the shape axis separates at 11 px and above",
      all(R[n]["out"]["shape_split"]["separates"] for n in ("s1", "s2", "s3")),
      "%r" % {n: R[n]["out"]["shape_split"]["separates"]
              for n in ("s1", "s2", "s3")})
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
check("16, 18 and 20 marks routed at 11, 22 and 33 px, and none misrouted",
      (R["s1"]["right"], R["s2"]["right"], R["s3"]["right"]) == (16, 18, 20)
      and R["s1"]["wrong"] == R["s2"]["wrong"] == R["s3"]["wrong"] == 0,
      "%r" % {n: (R[n]["right"], R[n]["wrong"]) for n in ("s1", "s2", "s3")})
# ONE KNOWN MISROUTE, PINNED AS ONE. On the overlap rendering a marker of the
# touching pair keeps its own blob, and part of its partner sits inside the
# window its fill is measured in: an open circle reads 0.83 against a 0.63
# boundary and is routed as filled. Refusing marks whose BOXES nearly touch
# fixes it and costs five to thirteen legitimate marks per rendering, which is
# the wrong trade - so it stays wrong, and it stays counted.
check("  and the overlap rendering routes 22 with exactly one misroute",
      (R["overlap"]["right"], R["overlap"]["wrong"]) == (22, 1),
      "%d right, %d wrong" % (R["overlap"]["right"], R["overlap"]["wrong"]))
check("  two marks that touch each other are refused, not split",
      "MARKER_MERGED" in R["overlap"]["refusals"],
      "%r" % (R["overlap"]["refusals"],))

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %r" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
