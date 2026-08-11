"""The proposer, against the geometry this project measured by hand.

    python3 forward_test_beckers_geometry.py [PAGE_RASTER]

Publication BF02919461 page 3 is the only figure in this package whose values
are PRINTED in the same paper - Table 1 gives ApEn as mean and SEM for supine
and standing at five sessions, and Figures 1 and 2 plot the same means with 95%
confidence intervals. Measuring those two panels by hand produced a plan that
read all ten cells to a mean absolute error of 0.0028 against that table.

That makes this the one place where a proposed geometry can be checked against
something better than an opinion. The numbers below are the hand measurement,
committed here as the expected answer:

    Fig 1 (supine)    box 302,1179,2020,2746   ticks 2019.5 .. 2746.0
                      anchors 459.5 601.0 741.5 881.5 1024.0
    Fig 2 (standing)  box 1446,2257,2049.5,2720  ticks 2049.5 .. 2720.0
                      anchors 1591.0 1721.5 1851.5 1981.5 2113.0

The raster is a 300 DPI render of a publisher page and is not redistributable,
so this SKIPs when it is not on disk - loudly, and with the command that makes
it, because a forward test nobody can run is a forward test nobody runs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CANDIDATES = (os.path.join(HERE, "bf_p3_300dpi.png"),
              "/home/claude/gt/bf_p3_300dpi.png")
path = sys.argv[1] if len(sys.argv) > 1 else next(
    (p for p in CANDIDATES if os.path.exists(p)), CANDIDATES[0])
if not os.path.exists(path):
    print("SKIP: %s is not on disk. Make it with\n"
          "  pdftoppm -r 300 -f 3 -l 3 -png BF02919461.pdf bf300\n"
          "and pass the page 3 PNG as the first argument." % path,
          file=sys.stderr)
    raise SystemExit(0)

import geometry_proposer as GP                                   # noqa: E402

#: What a person measured, by eye and by profile, before any of this existed.
HAND = {
    "SUPINE": dict(region=(260, 1980, 1220, 2800),
                   box=(302, 1179, 2020, 2746),
                   first_tick=2019.5, last_tick=2746.0, ticks=12,
                   anchors=(459.5, 601.0, 741.5, 881.5, 1024.0)),
    "STANDING": dict(region=(1400, 1980, 2320, 2800),
                     box=(1446, 2257, 2049, 2720),
                     first_tick=2049.5, last_tick=2720.0, ticks=12,
                     anchors=(1591.0, 1721.5, 1851.5, 1981.5, 2113.0)),
}

#: A panel box two pixels out changes a crop. Two pixels on a TICK is 0.003
#: units on this axis, which is inside the printed table's own rounding, and
#: the run in `PILOT_BECKERS.md` shows what that costs: nothing measurable.
BOX_TOL_PX = 2.0
TICK_TOL_PX = 1.5
ANCHOR_TOL_PX = 2.0

failures = []
print("proposed geometry vs the hand measurement, publication BF02919461")
for name, hand in HAND.items():
    row = GP.propose_panel(path, hand["region"], proposal_id="GP_%s" % name)
    if row is None:
        failures.append("%s: no proposal at all" % name)
        continue
    box = (int(row["Panel_X0"]), int(row["Panel_X1"]),
           int(row["Panel_Y0"]), int(row["Panel_Y1"]))
    marks = [float(m) for m in row["Y_Tick_Pixels"].split(";") if m]
    anchors = [float(a) for a in row["Group_Anchor_Pixels"].split(";") if a]
    dbox = max(abs(a - b) for a, b in zip(box, hand["box"]))
    print("  %-9s box %s  delta %.1f px" % (name, box, dbox))
    if dbox > BOX_TOL_PX:
        failures.append("%s: box is %.1f px from the hand measurement %s"
                        % (name, dbox, hand["box"]))
    print("    %d y ticks (hand %d), first %.1f (hand %.1f), last %.1f "
          "(hand %.1f), coverage %s"
          % (len(marks), hand["ticks"], marks[0] if marks else -1,
             hand["first_tick"], marks[-1] if marks else -1, hand["last_tick"],
             row["Y_Tick_Coverage"]))
    if len(marks) != hand["ticks"]:
        failures.append("%s: %d ticks, hand found %d"
                        % (name, len(marks), hand["ticks"]))
    elif max(abs(marks[0] - hand["first_tick"]),
             abs(marks[-1] - hand["last_tick"])) > TICK_TOL_PX:
        failures.append("%s: the ladder's ends are %.1f/%.1f, hand %.1f/%.1f"
                        % (name, marks[0], marks[-1], hand["first_tick"],
                           hand["last_tick"]))
    # The ends are the two rows a person types a value against, so a ladder
    # that does not reach the axis is the one failure that stays invisible
    # downstream.
    if float(row["Y_Tick_Coverage"] or 0) < 0.95:
        failures.append("%s: the ladder spans only %s of the axis"
                        % (name, row["Y_Tick_Coverage"]))
    print("    %d anchors (hand %d), worst delta %.1f px"
          % (len(anchors), len(hand["anchors"]),
             max((abs(a - b) for a, b in zip(anchors, hand["anchors"])),
                 default=-1)))
    if len(anchors) != len(hand["anchors"]):
        failures.append("%s: %d anchors, hand found %d"
                        % (name, len(anchors), len(hand["anchors"])))
    elif max(abs(a - b) for a, b in zip(anchors, hand["anchors"])) > ANCHOR_TOL_PX:
        failures.append("%s: an anchor is off by more than %.1f px"
                        % (name, ANCHOR_TOL_PX))
    # And nothing that only a person can answer.
    if row["Y_Tick_First_Value"] or row["Y_Tick_Last_Value"]:
        failures.append("%s: the proposal invented a tick VALUE" % name)
    if row["Human_Verification_Status"] != "PENDING":
        failures.append("%s: the proposal is not PENDING" % name)

print()
if failures:
    for line in failures:
        print("FAIL %s" % line)
    raise SystemExit(1)
print("verdict: PASS - the proposal reproduces the hand measurement that read "
      "ten printed values to 0.0028, and still asks a person for the two "
      "numbers a raster cannot be asked")
