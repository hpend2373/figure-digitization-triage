"""What a raster may be asked, and what only a person can answer.

    python3 test_geometry_proposer.py     # exit 0 = all scenarios pass

Panel geometry is the project's largest hand cost - a box, two tick pairs, an x
pixel per group, per panel, for 189 B-shape figures - and it is the same
measurement every time. So it is proposed here.

The scenarios are mostly about the boundary, again. A frame found two pixels
out costs a slightly wider crop. A tick VALUE guessed wrong rescales every
number in the panel by ten, leaves the calibration residual at zero, and makes
the whole file self-consistent and wrong - so the contract under test is that
this module never produces one, and refuses a proposal that claims to be
confirmed without a person having typed it.

The fixtures are drawn here with PIL at two scales, because the second thing
under test is that nothing in the detection is a distance in pixels: the same
figure rendered twice as large must give the same tick COUNT and the same
proportional positions. The reader's own marker limits failed exactly that way
on publication BF02919461.
"""
import csv
import os
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geometry_proposer as GP                                  # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_geom_")


def panel_fixture(scale=1, ticks=11, groups=5, frame="BOX", tick_side="OUTSIDE"):
    """A plot that looks like the ones this corpus prints.

    `scale` multiplies every dimension, so a scenario can assert that the
    detection says the same thing about the same figure at two renderings.
    """
    W, H = 400 * scale, 320 * scale
    x0, x1 = 60 * scale, 360 * scale
    y0, y1 = 30 * scale, 270 * scale
    image = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(image)
    width = max(1, scale)
    d.line((x0, y0, x0, y1), fill="black", width=width)
    d.line((x0, y1, x1, y1), fill="black", width=width)
    if frame == "BOX":
        d.line((x0, y0, x1, y0), fill="black", width=width)
        d.line((x1, y0, x1, y1), fill="black", width=width)
    step = (y1 - y0) / float(ticks - 1)
    reach = 5 * scale
    for i in range(ticks):
        y = y0 + i * step
        if tick_side == "OUTSIDE":
            d.line((x0 - reach, y, x0 - width, y), fill="black", width=width)
        else:
            d.line((x0 + width, y, x0 + reach, y), fill="black", width=width)
            # A few short strokes OUTSIDE too, standing in for the printed
            # tick labels. A detector that takes the first side it looks at
            # rather than the side with more marks reads these as the ladder.
            if i % 4 == 0:
                d.line((x0 - reach, y, x0 - width, y), fill="black",
                       width=width)
    # One bar per group, tall enough to be ink and short enough to be a bar.
    span = (x1 - x0) / float(groups + 1)
    anchors = []
    for g in range(groups):
        cx = x0 + span * (g + 1)
        anchors.append(cx)
        top = y1 - (60 + 20 * g) * scale
        d.rectangle((cx - 9 * scale, top, cx + 9 * scale, y1 - width),
                    outline="black", width=width)
    return image, (x0, x1, y0, y1), anchors, [y0 + i * step for i in range(ticks)]


print("the frame, the ticks and the anchors are measurements")
_im, _frame, _anchors, _tickrows = panel_fixture()
_got = GP.find_frame(_im)
check("the plot frame is found", _got is not None and
      max(abs(a - b) for a, b in zip(_got, _frame)) <= 2,
      "%s vs %s" % (_got, _frame))
_marks, _side = GP.find_ticks(_im, _frame[0], _frame[2] - 4, _frame[3] + 5)
check("every printed tick is found, and no others",
      len(_marks) == len(_tickrows), "%d vs %d" % (len(_marks), len(_tickrows)))
check("and each one is where it was drawn",
      len(_marks) == len(_tickrows)
      and max(abs(a - b) for a, b in zip(_marks, _tickrows)) <= 1.5,
      "%s" % _marks[:4])
check("the side the ticks are on is reported, not assumed",
      _side == "OUTSIDE", _side)
_iim, _iframe = panel_fixture(tick_side="INSIDE")[:2]
_inside, _iside = GP.find_ticks(_iim, _iframe[0], _iframe[2] - 4, _iframe[3] + 5)
# REVERT: take the first side looked at instead of the side with more marks.
# The fixture prints three label-shaped strokes outside the spine, so a
# detector that does not compare reads a three-rung ladder off the labels.
check("ticks drawn inside the axis are found, on the right side",
      len(_inside) >= len(_tickrows) - 2 and _iside == "INSIDE",
      "%d %s" % (len(_inside), _iside))
# REVERT: drop `ladder_coverage`. Ticks drawn INSIDE a boxed frame put the
# corner tick and the frame line in the same ink, so the ladder loses its ends
# - and it is still perfectly evenly spaced. A person then types the first and
# last value against the wrong two rows and the panel is calibrated wrongly
# with every check passing. Even spacing cannot see this; coverage can.
check("a ladder that lost its end ticks is still perfectly regular",
      GP.tick_regularity(_inside)[1] < 0.05,
      "%s" % (GP.tick_regularity(_inside),))
check("but it does not span the axis, and that is reported",
      GP.ladder_coverage(_inside, _iframe[2], _iframe[3]) < 0.9,
      "%s" % GP.ladder_coverage(_inside, _iframe[2], _iframe[3]))
check("and the full ladder does span it",
      GP.ladder_coverage(_marks, _frame[2], _frame[3]) > 0.98,
      "%s" % GP.ladder_coverage(_marks, _frame[2], _frame[3]))
_ip = GP.propose_panel(_iim, proposal_id="GP009")
check("so the proposal scores down and says why",
      float(_ip["Confidence"]) < 1.0 and "ladder spans" in _ip["Confidence_Reason"],
      "%s %s" % (_ip["Confidence"], _ip["Confidence_Reason"]))
_found = GP.find_group_anchors(_im, _frame)
check("one anchor per group", len(_found) == len(_anchors),
      "%d vs %d" % (len(_found), len(_anchors)))
check("and each at the centre of its bar",
      len(_found) == len(_anchors)
      and max(abs(a - b) for a, b in zip(_found, _anchors)) <= 2.0,
      "%s" % [round(a - b, 1) for a, b in zip(_found, _anchors)])

# REVERT: keep every ink cluster. A significance star, a legend, an "N = 5"
# row - anything printed inside the plot area is then a group, and the panel
# comes back with more x positions than it has groups.
_smudge = panel_fixture()[0]
_sd = ImageDraw.Draw(_smudge)
# A short mark between two bars, the height of a printed character.
_sd.rectangle((133, 90, 141, 98), fill="black")
_sd.text((200, 95), "N = 5", fill="black")
_smudged = GP.find_group_anchors(_smudge, _frame)
check("a printed mark inside the plot is not a group",
      len(_smudged) == len(_anchors), "%s" % _smudged)
check("and does not drag the anchor of the bar it sits beside",
      len(_smudged) == len(_anchors)
      and max(abs(a - b) for a, b in zip(_smudged, _anchors)) <= 2.0,
      "%s" % [round(a - b, 1) for a, b in zip(_smudged, _anchors)])

# REVERT: look for ticks inside a fixed-width strip again. A tick is five
# pixels long at 300 DPI and ten at 600, and a strip is a distance in pixels -
# so a detector built on one answers nothing on the other. This is the defect
# the LINE_MONO marker limits still have.
print()
print("nothing in the detection is a distance in pixels")
_small, _sframe, _sanchors, _sticks = panel_fixture(scale=1)
_big, _bframe, _banchors, _bticks = panel_fixture(scale=4)
_sm, _ = GP.find_ticks(_small, _sframe[0], _sframe[2] - 4, _sframe[3] + 5)
_bm, _ = GP.find_ticks(_big, _bframe[0], _bframe[2] - 16, _bframe[3] + 17)
check("the same figure rendered 4x larger gives the same tick count",
      len(_sm) == len(_bm) == len(_sticks), "%d vs %d" % (len(_sm), len(_bm)))
check("and the same ticks, to within a pixel of the scaling",
      len(_sm) == len(_bm)
      and max(abs(b - a * 4) for a, b in zip(_sm, _bm)) <= 4.0,
      "%s" % [round(b - a * 4, 1) for a, b in zip(_sm, _bm)][:4])
check("and the same anchors",
      len(GP.find_group_anchors(_big, _bframe)) == len(_sanchors))

print()
print("a panel drawn with two spines is still a panel")
_L, _Lframe, _Lanchors, _Lticks = panel_fixture(frame="L")
_lgot = GP.find_frame(_L)
check("an L-shaped axis yields a frame",
      _lgot is not None and abs(_lgot[0] - _Lframe[0]) <= 2
      and abs(_lgot[3] - _Lframe[3]) <= 2, "%s" % (_lgot,))

print()
print("the spacing is reported; the values are not")
_spacing, _regular = GP.tick_regularity(_marks)
check("a regular ladder reports its spacing", _spacing > 0, "%s" % _spacing)
check("and reports itself regular", _regular < 0.05, "%s" % _regular)
_broken = list(_marks)
_broken[5] += 25
check("a ladder with a gap in it does not",
      GP.tick_regularity(_broken)[1] > 0.2, "%s" % (GP.tick_regularity(_broken),))

_row = GP.propose_panel(_im, proposal_id="GP001", raster_path="fix.png")
check("a proposal is produced", _row is not None)
# REVERT: let `propose_panel` write a tick value, or a status. The one number a
# raster cannot be asked is what the axis SAYS, and a wrong answer to it
# rescales the panel with every check still passing.
check("it carries no tick value at all",
      _row["Y_Tick_First_Value"] == "" and _row["Y_Tick_Last_Value"] == "")
check("and no verifier, and PENDING",
      _row["Human_Verification_Status"] == "PENDING"
      and not _row["Verified_By"] and not _row["Verified_At"])
check("it carries every proposal column",
      set(_row) == set(GP.PROPOSAL_COLUMNS),
      "%s" % (set(_row) ^ set(GP.PROPOSAL_COLUMNS)))
check("a proposal the machine just made has no problems",
      not GP.proposal_problems([_row]), "%s" % GP.proposal_problems([_row]))
_written = GP.write_proposals(os.path.join(ROOT, "p.csv"), [_row])
_back = list(csv.DictReader(open(_written, encoding="utf-8")))
check("and it round-trips through the CSV unchanged",
      not GP.proposal_problems(_back)
      and _back[0]["Y_Tick_Pixels"] == _row["Y_Tick_Pixels"])

print()
print("a proposal becomes a calibration only when a person reads the axis")
# REVERT: drop `proposal_problems` from the join, or let `calibration_from`
# work on a PENDING row. The geometry then reaches a plan with the two numbers
# nobody supplied - and blank tick values are how a panel gets calibrated
# against zero.
_conf = dict(_back[0])
check("a PENDING proposal yields no calibration",
      GP.calibration_from(_conf) is None)
# REVERT: drop the status guard from `calibration_from`. A row somebody typed
# values into and did not sign is refused by `proposal_problems` - and this is
# the other side of that door, so the geometry cannot reach a plan by being
# read directly.
_unsigned = dict(_conf, Y_Tick_First_Value="1.3", Y_Tick_Last_Value="0.2")
check("and neither does one with the values typed in but nobody's name on it",
      GP.calibration_from(_unsigned) is None,
      "%s" % (GP.calibration_from(_unsigned),))
_conf.update(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
             Verified_At="2026-08-11", Y_Tick_First_Value="1.3",
             Y_Tick_Last_Value="0.2")
_cal = GP.calibration_from(_conf)
check("a confirmed one yields two points, value and pixel",
      _cal is not None and len(_cal) == 2 and _cal[0][0] == 1.3
      and _cal[1][0] == 0.2, "%s" % (_cal,))
check("and the pixels are the FIRST and LAST tick that was measured",
      _cal[0][1] == float(_row["Y_Tick_Pixels"].split(";")[0])
      and _cal[1][1] == float(_row["Y_Tick_Pixels"].split(";")[-1]),
      "%s" % (_cal,))
for _label, _edit, _code in (
        ("a confirmation with nobody behind it",
         dict(Human_Verification_Status="CONFIRMED", Y_Tick_First_Value="1.3",
              Y_Tick_Last_Value="0.2"), "PROPOSAL_VERDICT_UNATTRIBUTED"),
        ("a confirmation with no tick value",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11"), "PROPOSAL_TICK_VALUE_MISSING"),
        ("a confirmation whose two ticks are the same number",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11", Y_Tick_First_Value="1",
              Y_Tick_Last_Value="1"), "PROPOSAL_TICK_VALUES_EQUAL"),
        ("a PENDING row that names a verifier anyway",
         dict(Verified_By="RV_1"), "PROPOSAL_PENDING_WITH_A_VERIFIER"),
        ("a PENDING row carrying a tick value",
         dict(Y_Tick_First_Value="1.3"), "PROPOSAL_PENDING_WITH_A_TICK_VALUE"),
        ("a status nobody declared",
         dict(Human_Verification_Status="LOOKS_FINE"),
         "PROPOSAL_STATUS_UNKNOWN"),
        ("a row with no identifier", dict(Proposal_ID=""),
         "PROPOSAL_ID_MISSING")):
    _bad = dict(_back[0]); _bad.update(_edit)
    check("%s is refused" % _label,
          any(c == _code for _p, c, _d in GP.proposal_problems([_bad])),
          "%s" % GP.proposal_problems([_bad]))
check("and two proposals with one identifier are refused",
      any(c == "PROPOSAL_ID_DUPLICATE"
          for _p, c, _d in GP.proposal_problems([_back[0], dict(_back[0])])))

print()
print("the confidence says what is doubtful, and the overlay shows it")
# REVERT: delete any penalty. Nothing refuses a proposal for scoring badly, so
# the only cost is silent - the panel a person most needed to look at stops
# sorting to the top and stops carrying the sentence saying why.
_few = GP.propose_panel(panel_fixture(ticks=2)[0], proposal_id="GP002")
# REVERT: drop the irregularity penalty. A ladder the detector got wrong, or an
# axis printed with a break in it, then scores 1.00 and nobody looks - and the
# two values a person types are typed against a ladder that is not one.
_even = GP._confidence((0, 100, 0, 100), _marks, 0.01, [10, 50, 90], None)
_uneven = GP._confidence((0, 100, 0, 100), _marks, 0.25, [10, 50, 90], None)
check("an uneven ladder scores below an even one",
      _uneven[0] < _even[0], "%s vs %s" % (_uneven[0], _even[0]))
check("and the reason says by how much it is uneven",
      "uneven" in _uneven[1], _uneven[1])
check("a panel with two ticks scores down",
      _few is not None and float(_few["Confidence"]) <= 0.6, "%s" % _few)
check("and says the axis cannot be read from a first and last value",
      "tick" in _few["Confidence_Reason"], _few["Confidence_Reason"])
_blank = Image.new("RGB", (200, 200), "white")
check("a region with no frame in it yields no proposal",
      GP.propose_panel(_blank) is None)
_over = GP.proposal_overlay(_im, _row, os.path.join(ROOT, "o.png"))
check("the overlay is written", os.path.exists(_over))
_ov = Image.open(_over).convert("RGB")
_px = _ov.load()
check("and it is drawn on the raster, not on a blank",
      _ov.size[0] > 100 and any(_px[x, y] != (255, 255, 255)
                                for x in range(0, _ov.size[0], 7)
                                for y in range(0, _ov.size[1], 7)))

print()
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
import shutil                                                    # noqa: E402
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
