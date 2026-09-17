"""What a raster may be asked, and what only a person can answer.

    python3 test_geometry_proposer.py     # exit 0 = all scenarios pass

Panel geometry is the project's largest hand cost - a box, two tick pairs, an x
pixel per group, per panel, for 189 B-shape figures - and it is the same
measurement every time. So it is proposed here.

The scenarios are mostly about the boundary, again. A frame found two pixels
out costs a slightly wider crop. A tick VALUE guessed wrong rescales every
number in the panel by ten - so the contract under test is that a reading which
does not hold together as a ladder is REFUSED rather than returned, that only
the run the ladder kept is proposed, that a reading lands in its own columns and
never in the person's, and that a proposal claiming to be CONFIRMED without a
person is refused whatever the machine read.

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


def box_fixture(scale=1, groups=5, dots=9):
    """A box plot with points scattered over it, which is what this corpus prints.

    The points are the whole difficulty. They put ink in every column of the
    panel, so a detector that looks for inked columns finds one group or three
    where five are drawn - and there are many more points than boxes, so a
    detector that takes the COMMONEST repeated width finds the points.
    """
    W, H = 400 * scale, 320 * scale
    x0, x1 = 60 * scale, 360 * scale
    y0, y1 = 30 * scale, 270 * scale
    image = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(image)
    width = max(1, scale)
    d.line((x0, y0, x0, y1), fill="black", width=width)
    d.line((x0, y1, x1, y1), fill="black", width=width)
    span = (x1 - x0) / float(groups + 1)
    half, centres = 14 * scale, []
    for g in range(groups):
        cx = x0 + span * (g + 1)
        centres.append(cx)
        top, bottom = y1 - (150 - 8 * g) * scale, y1 - (70 - 8 * g) * scale
        # top, median and bottom: three rules of ONE width, which is the box
        d.rectangle((cx - half, top, cx + half, bottom), outline="black",
                    width=width)
        d.line((cx - half, (top + bottom) / 2, cx + half, (top + bottom) / 2),
               fill="black", width=width)
        # the whisker, and the points scattered across the group's width
        d.line((cx, top - 20 * scale, cx, bottom + 20 * scale), fill="black",
               width=width)
        for i in range(dots):
            dx = cx + ((i % 3) - 1) * 8 * scale
            dy = top + (i * (bottom - top)) / float(dots)
            d.ellipse((dx - 4 * scale, dy - 4 * scale, dx + 4 * scale,
                       dy + 4 * scale), fill="black")
    return image, (x0, x1, y0, y1), centres


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

# REVERT: require a line on both axes. The docstring promised the L-shape and
# the code refused anything short of it - 112 of the 145 panels this corpus
# could not propose a geometry for had a spine or a baseline, not both.
print()
print("one printed line is still a frame")


def one_line_fixture(which):
    """A panel with ONLY a spine or ONLY a baseline, and ticks on the spine."""
    W, H = 400, 320
    x0, x1, y0, y1 = 60, 360, 30, 270
    image = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(image)
    if which == "SPINE":
        d.line((x0, y0, x0, y1), fill="black", width=1)
        for i in range(6):
            y = y0 + i * (y1 - y0) / 5.0
            d.line((x0 - 5, y, x0 - 1, y), fill="black", width=1)
    else:
        d.line((x0, y1, x1, y1), fill="black", width=1)
    for g in range(4):
        cx = x0 + (x1 - x0) * (g + 1) / 5.0
        d.rectangle((cx - 9, y1 - 60 - 20 * g, cx + 9, y1 - 2), outline="black")
    return image, (x0, x1, y0, y1)


_S, _Sframe = one_line_fixture("SPINE")
_sgot = GP.find_frame(_S, region=(0, 0, 400, 320))
check("a spine with no baseline yields a frame on the region's rows",
      _sgot is not None and abs(_sgot[0] - _Sframe[0]) <= 2
      and _sgot[2] == 0 and _sgot[3] == 319, "%s" % (_sgot,))
check("and its ticks are found on that spine",
      _sgot is not None and len(GP.find_ticks(_S, _sgot[0], _sgot[2] - 2, _sgot[3] + 3)[0]) == 6,
      "%s" % (_sgot and GP.find_ticks(_S, _sgot[0], _sgot[2] - 2, _sgot[3] + 3)[0],))
_B, _Bframe = one_line_fixture("BASELINE")
_bgot = GP.find_frame(_B, region=(0, 0, 400, 320))
check("a baseline with no spine yields a frame on the region's columns",
      _bgot is not None and abs(_bgot[3] - _Bframe[3]) <= 2
      and _bgot[0] == 0 and _bgot[1] == 399, "%s" % (_bgot,))
check("and it has no ticks to offer, which the proposal says rather than hides",
      _bgot is not None and GP.propose_panel(_B, (0, 0, 400, 320))["Y_Tick_Count"] == 0)
_N = Image.new("RGB", (400, 320), "white")
ImageDraw.Draw(_N).rectangle((100, 100, 130, 200), outline="black")
check("no printed line at all is no frame", GP.find_frame(_N, region=(0, 0, 400, 320)) is None)

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
      _row["Y_Tick_Top_Value"] == "" and _row["Y_Tick_Bottom_Value"] == "")
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
_unsigned = dict(_conf, Y_Tick_Top_Value="1.3", Y_Tick_Bottom_Value="0.2",
                 Confirmed_Tick_Values="1.3@10;0.2@90")
check("and neither does one with the values typed in but nobody's name on it",
      GP.calibration_from(_unsigned) is None,
      "%s" % (GP.calibration_from(_unsigned),))
_conf.update(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
             Verified_At="2026-08-11", Y_Tick_Top_Value="1.3",
             Y_Tick_Bottom_Value="0.2",
             Confirmed_Tick_Values="1.3@10;0.2@90")
_cal = GP.calibration_from(_conf)
check("a confirmed one yields two points, value and pixel",
      _cal is not None and len(_cal) == 2 and _cal[0][0] == 1.3
      and _cal[1][0] == 0.2, "%s" % (_cal,))
# THIS SCENARIO USED TO ASSERT THE DEFECT. It required the pixels to be the
# first and last of `Y_Tick_Pixels`, which is right only when the answer was
# about those two ticks - and the reader's answer usually is not. What the row
# carries is what the calibration stands on.
check("and the pixels are the ones the row carries, not the tick list's ends",
      _cal[0][1] == 10.0 and _cal[1][1] == 90.0
      and float(_row["Y_Tick_Pixels"].split(";")[-1]) != 90.0,
      "%s vs %s" % (_cal, _row["Y_Tick_Pixels"]))
for _label, _edit, _code in (
        ("a confirmation with nobody behind it",
         dict(Human_Verification_Status="CONFIRMED", Y_Tick_Top_Value="1.3",
              Y_Tick_Bottom_Value="0.2",
              Confirmed_Tick_Values="1.3@10;0.2@90"),
         "PROPOSAL_VERDICT_UNATTRIBUTED"),
        ("a confirmation with no tick value",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11"), "PROPOSAL_TICK_VALUE_MISSING"),
        ("a confirmation whose two ticks are the same number",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11", Y_Tick_Top_Value="1",
              Y_Tick_Bottom_Value="1",
              Confirmed_Tick_Values="1@10;1@90"),
         "PROPOSAL_TICK_VALUES_EQUAL"),
        ("a PENDING row that names a verifier anyway",
         dict(Verified_By="RV_1"), "PROPOSAL_PENDING_WITH_A_VERIFIER"),
        ("a PENDING row carrying a tick value",
         dict(Y_Tick_Top_Value="1.3"), "PROPOSAL_PENDING_WITH_A_TICK_VALUE"),
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
print("where the marks stand, when the marks are boxes")

_bim, _bframe, _bcentres = box_fixture()
_marks, _why = GP.find_box_anchors(_bim, _bframe)
# REVERT: take the commonest repeated width instead of the widest. There are
# nine points per group and one box, so the points win and a five-group panel
# comes back with twenty anchors.
check("every box is found, and only the boxes",
      len(_marks) == len(_bcentres), "%d vs %d: %s" % (len(_marks), len(_bcentres), _marks))
check("and each one is where it was drawn",
      len(_marks) == len(_bcentres)
      and max(abs(a - b) for a, b in zip(_marks, _bcentres)) <= 2,
      "%s vs %s" % (_marks, _bcentres))
check("the width it decided on is said out loud",
      "wide" in _why, _why)

# REVERT: make the run limits pixel distances. The same figure rendered larger
# is the same figure, and this whole module is measured at more than one scale.
# Two is not enough to catch a constant chosen from the small one: the fixture's
# box is 28 px wide at scale 1 and 56 at scale 2, and any range wide enough for
# a real figure holds both.
for _scale in (2, 4):
    _bs, _fs, _cs = box_fixture(scale=_scale)
    _ms, _whys = GP.find_box_anchors(_bs, _fs)
    check("the same figure drawn %dx as large gives the same reading" % _scale,
          len(_ms) == len(_marks)
          and max(abs(a * _scale - b) for a, b in zip(_marks, _ms)) <= 2 * _scale,
          "%s" % _ms)

# REVERT: find filled bars here too. A filled bar is ONE band of rows, not two,
# and its panel is `find_group_anchors`'s - a detector that answers for both is a
# detector nobody can disagree with.
_bar = Image.new("RGB", (400, 320), "white")
_bd = ImageDraw.Draw(_bar)
_bd.line((60, 30, 60, 270), fill="black")
_bd.line((60, 270, 360, 270), fill="black")
for _g in range(5):
    _cx = 60 + 50 * (_g + 1)
    _bd.rectangle((_cx - 14, 270 - (60 + 20 * _g), _cx + 14, 269), fill="black")
check("filled bars are not outlined marks",
      GP.find_box_anchors(_bar, (60, 360, 30, 270))[0] == [],
      "%s" % (GP.find_box_anchors(_bar, (60, 360, 30, 270)),))

# REVERT: return a guess when nothing repeats. A line panel has no mark of one
# width, and putting a category where the figure has none is a wrong number.
_lim = Image.new("RGB", (400, 320), "white")
_ld = ImageDraw.Draw(_lim)
_ld.line((60, 30, 60, 270), fill="black")
_ld.line((60, 270, 360, 270), fill="black")
_ld.line([(70 + 8 * i, 200 - 4 * (i % 7)) for i in range(30)], fill="black")
_lmarks, _lwhy = GP.find_box_anchors(_lim, (60, 360, 30, 270))
check("a panel with no repeated mark gets no anchors, and a reason",
      _lmarks == [] and _lwhy, "%s %s" % (_lmarks, _lwhy))
_one, _oframe, _ocent = box_fixture(groups=1)
check("one mark is not a categorical axis",
      GP.find_box_anchors(_one, _oframe)[0] == [])

# REVERT: replace the ink-column reading with this one. Which reading a panel
# needs depends on what is drawn in it, and nothing has said that yet when a
# geometry is proposed.
_brow = GP.propose_panel(_bim)
check("both readings are proposed, in their own columns",
      _brow["Box_Anchor_Count"] == len(_bcentres)
      and "Group_Anchor_Pixels" in _brow and "Box_Anchor_Pixels" in _brow,
      "%s / %s" % (_brow["Box_Anchor_Count"], _brow["Group_Anchor_Count"]))
check("and the ink-column reading is still its own answer",
      _brow["Group_Anchor_Pixels"] == ";".join(
          "%g" % a for a in GP.find_group_anchors(GP._gray(_bim), _bframe)),
      "%s" % _brow["Group_Anchor_Pixels"])
_bpic = GP.proposal_overlay(_bim, _brow, os.path.join(ROOT, "marks.png"))
_bpx = Image.open(_bpic).convert("RGB").load()
_bsize = Image.open(_bpic).size
check("and the mark reading is drawn in its own colour",
      any(_bpx[x, y] == (190, 60, 190)
          for x in range(_bsize[0]) for y in range(_bsize[1])))

print()
print("a calibration stands on pairs, not on two numbers and a guess")

# REVERT: pair the confirmed values with `Y_Tick_Pixels`'s two ends. That is the
# right pair only when the answer was ABOUT those two ticks, and the reader's
# usually is not: its ladder covered five of six ticks on this project's own
# FIG9 and three of five on another panel. Pairing its last value with the last
# tick put those two panels 20% and 50% off, with a ladder residual of 0.1 px
# and no complaint anywhere.
_conf = dict(_row, Human_Verification_Status="CONFIRMED", Verified_By="MC",
             Verified_At="2026-09-10", Y_Tick_Top_Value="40",
             Y_Tick_Bottom_Value="20",
             Y_Tick_Pixels="100;200;300;400",
             Confirmed_Tick_Values="40@100;20@300")
check("the calibration uses the pixels it was given",
      GP.calibration_from(_conf) == [[40.0, 100.0], [20.0, 300.0]],
      GP.calibration_from(_conf))
check("and refuses a row that carries none",
      GP.calibration_from(dict(_conf, Confirmed_Tick_Values="")) is None)
check("a CONFIRMED row with no pairs is refused",
      any(c == "PROPOSAL_CALIBRATION_PAIRS_MISSING"
          for _p, c, _d in GP.proposal_problems(
              [dict(_conf, Confirmed_Tick_Values="40@100")])))
check("and one that pins both values to one row",
      any(c == "PROPOSAL_CALIBRATION_PAIRS_ONE_ROW"
          for _p, c, _d in GP.proposal_problems(
              [dict(_conf, Confirmed_Tick_Values="40@100;20@100")])))

print()
print("what the reader may say about an axis")

# REVERT: hand back everything the OCR returned. `ladder` accepts a contiguous
# SUBSET when the full set fails; on FIG9 of this project's own corpus that
# dropped a `9000` printed `5000`, and drawing all the pairs put that 9000 back
# on the overlay in the reader's own colour - where a person confirming the
# picture confirms the one value the calibration threw away.
_LADDER = [(30.0, 100.0), (20.0, 200.0), (10.0, 300.0)]
_status, _kept, _detail, _resid = GP.values_from_ladder(_LADDER)
check("a reading that holds together is proposed",
      _status == GP.READ_OK and _kept == _LADDER, "%s %s" % (_status, _kept))
_WITH_BAD = _LADDER + [(9000.0, 400.0)]
_status, _kept, _detail, _resid = GP.values_from_ladder(_WITH_BAD)
check("and only the run the ladder kept",
      _status == GP.READ_OK and _kept == _LADDER, "%s %s" % (_status, _kept))
check("the dropped value is named, not silently gone",
      "9000" in _detail, _detail)

# REVERT: return the reading even when the ladder refuses it. A misread digit
# breaks either the direction or the step, and both are the whole guard.
_status, _kept, _detail, _resid = GP.values_from_ladder(
    [(30.0, 100.0), (6.0, 200.0), (10.0, 300.0)])
check("a reading that is not monotone is refused, not returned",
      _status == GP.READ_REFUSED and _kept == [], "%s %s" % (_status, _kept))
_status, _kept, _detail, _resid = GP.values_from_ladder([(30.0, 100.0), (20.0, 200.0)])
check("two labels are not a ladder",
      _status == GP.READ_REFUSED and "3 needed" in _detail, _detail)

# REVERT: put the reading in the person's column. `Y_Tick_Top_Value` means a
# person read this axis; a machine writing there is a machine answering for one.
_read = GP.apply_reading(dict(_row), *GP.values_from_ladder(_WITH_BAD))
check("what the reader read lands in the reader's columns",
      (_read["Y_Tick_Read_First"], _read["Y_Tick_Read_Last"],
       _read["Y_Tick_Read_Values"]) == ("30", "10", "30@100;20@200;10@300"),
      "%s" % [_read[c] for c in ("Y_Tick_Read_First", "Y_Tick_Read_Last",
                                 "Y_Tick_Read_Values")])
check("and in nobody else's",
      not GP._s(_read.get("Y_Tick_Top_Value"))
      and not GP._s(_read.get("Y_Tick_Bottom_Value"))
      and not GP._s(_read.get("Verified_By")),
      "%s" % [_read.get(c) for c in ("Y_Tick_Top_Value", "Y_Tick_Bottom_Value",
                                     "Verified_By")])
check("a refused reading writes no value at all",
      not GP._s(GP.apply_reading(dict(_row), *GP.values_from_ladder(
          [(30.0, 100.0), (6.0, 200.0), (10.0, 300.0)])).get("Y_Tick_Read_First")))
check("a reading is not a confirmation",
      _read["Human_Verification_Status"] == GP.PROPOSAL_PENDING
      and not GP._s(_read.get("Y_Tick_Top_Value"))
      and not GP._s(_read.get("Verified_By")))
check("and a PENDING row that carries one is still refused",
      any(c == "PROPOSAL_PENDING_WITH_A_TICK_VALUE"
          for _p, c, _d in GP.proposal_problems(
              [dict(_read, Y_Tick_Top_Value="30")])))
check("a proposal that says it read the axis and carries nothing is refused",
      any(c == "PROPOSAL_READ_WITHOUT_VALUES"
          for _p, c, _d in GP.proposal_problems(
              [dict(_read, Y_Tick_Read_Values="")])))
check("a reading status this module cannot write is refused",
      any(c == "PROPOSAL_READ_STATUS_UNKNOWN"
          for _p, c, _d in GP.proposal_problems(
              [dict(_read, Y_Tick_Read_Status="PROBABLY")])))
check("values are read back only from a row that says it read them",
      GP.read_values_of(_read) == [(30.0, 100.0), (20.0, 200.0), (10.0, 300.0)]
      and GP.read_values_of(dict(_read, Y_Tick_Read_Status=GP.READ_REFUSED)) == [])
check("measuring alone does not claim to have read",
      GP.propose_panel(_im)["Y_Tick_Read_Status"] == GP.READ_NOT_ATTEMPTED)

# REVERT: write the read value past the frame's right edge. On a figure whose
# panels sit side by side that is the NEXT panel, and a person confirming this
# one is shown numbers drawn on that one.
_pic = GP.proposal_overlay(_im, _read, os.path.join(ROOT, "read.png"))
_rov = Image.open(_pic).convert("RGB")
_rpx = _rov.load()
_ink = [(x, y) for x in range(_rov.size[0]) for y in range(_rov.size[1])
        if _rpx[x, y] == (190, 60, 190)]
_offset = int(GP._s(_read.get("Region")).split(",")[0] or 0) - 12
check("the reading is drawn on the picture the person confirms", bool(_ink))
check("and inside the frame it belongs to",
      _ink and max(x for x, _y in _ink) + max(0, _offset) <= int(_read["Panel_X1"]),
      "%s vs %s" % (max(x for x, _y in _ink) if _ink else None, _read["Panel_X1"]))

# REVERT: draw the reading across the tick line. The text's midline - where a
# minus sign is - lands on the line drawn in the same colour, and -0.9 shows as
# 0.9: the one glyph that flips every value in the panel is the one a person
# cannot see. Publication S0094576505000263's axis (-1 .. -0.3) read correctly
# and was drawn without a single minus.
print()
print("a negative axis is read, kept and shown with its sign")
_NEG = [(-10.0, 100.0), (-20.0, 200.0), (-30.0, 300.0)]
_ZERO = [(10.0, 100.0), (0.0, 200.0), (-10.0, 300.0)]
_nst, _nk, _nd, _ = GP.values_from_ladder(_NEG)
_zst, _zk, _zd, _ = GP.values_from_ladder(_ZERO)
check("an all-negative ladder is a ladder", _nst == GP.READ_OK and [v for v, _p in _nk] == [-10.0, -20.0, -30.0], _nd)
check("a ladder through zero is a ladder", _zst == GP.READ_OK and [v for v, _p in _zk] == [10.0, 0.0, -10.0], _zd)
_nread = GP.apply_reading(dict(_row), *GP.values_from_ladder(_NEG))
check("the sign reaches the reader's columns",
      (_nread["Y_Tick_Read_First"], _nread["Y_Tick_Read_Last"], _nread["Y_Tick_Read_Values"])
      == ("-10", "-30", "-10@100;-20@200;-30@300"),
      "%s" % [_nread[c] for c in ("Y_Tick_Read_First", "Y_Tick_Read_Last", "Y_Tick_Read_Values")])
_pos = GP.apply_reading(dict(_row), *GP.values_from_ladder([(10.0, 100.0), (20.0, 200.0), (30.0, 300.0)]))
_npic = Image.open(GP.proposal_overlay(_im, _nread, os.path.join(ROOT, "neg.png"))).convert("RGB")
_ppic = Image.open(GP.proposal_overlay(_im, _pos, os.path.join(ROOT, "pos.png"))).convert("RGB")
_npx, _ppx = _npic.load(), _ppic.load()
_W, _H = _npic.size
# the magenta tick bars are the rows with an unbroken 30 px run of that
# colour; the value text and the anchor stubs are magenta too, but in runs
# of a few pixels
def _run(y):
    best = cur = 0
    for x in range(_W):
        cur = cur + 1 if _npx[x, y] == (190, 60, 190) else 0
        best = max(best, cur)
    return best
_bars = [y for y in range(_H) if _run(y) >= 30]
_near = set(b + d for b in _bars for d in range(-2, 3))
_onband = sum(1 for x in range(_W) for y in _near if 0 <= y < _H and _npx[x, y] != _ppx[x, y])
_offband = sum(1 for x in range(_W) for y in range(_H)
               if y not in _near and _npx[x, y] != _ppx[x, y])
check("and the value is written clear of the tick line, where a minus can be seen",
      len(_bars) >= 3 and _offband > 0 and _onband == 0,
      "bars %d, differs on the tick line %d px, off it %d px" % (len(_bars), _onband, _offband))
# REVERT: size the value only to the tick step. Three labels spread over a whole
# axis give a step of half the panel, and a number at a quarter of that covers
# the data it was drawn to vouch for (S0094576511002189: 1, -2, -3 over 2000 px,
# written 400 px tall, across the curve).
_h = int(_row["Panel_Y1"]) - int(_row["Panel_Y0"])
_far = GP.apply_reading(dict(_row), *GP.values_from_ladder(
    [(3.0, float(_row["Panel_Y0"]) + 5), (1.0, float(_row["Panel_Y0"]) + _h * 0.45),
     (-1.0, float(_row["Panel_Y0"]) + _h * 0.9)]))
_fpic = Image.open(GP.proposal_overlay(_im, _far, os.path.join(ROOT, "far.png"))).convert("RGB")
_fpx = _fpic.load()
_rows_with = [y for y in range(_fpic.size[1])
              if any(_fpx[x, y] == (190, 60, 190) for x in range(_fpic.size[0]))]
_runs, _cur = [], None
for y in _rows_with:
    if _cur is not None and y == _cur[-1] + 1:
        _cur.append(y)
    else:
        _cur = [y]; _runs.append(_cur)
check("a value whose neighbours are far away is still drawn small enough to see past",
      max(len(r) for r in _runs) <= _h * 0.06,
      "가장 높은 자홍 덩어리 %d px / 프레임 %d px" % (max(len(r) for r in _runs), _h))

# REVERT: write every value above its tick. The top tick sits at the frame's
# top edge, and the text above it leaves through the crop: the one value a
# confirmer most needs to see was the one cut in half (GISOLF 2005, 120).
_ty0 = int(_row["Panel_Y0"])
_top = GP.apply_reading(dict(_row, Region="%s,%d,%s,%s" % (_row["Panel_X0"], _ty0, _row["Panel_X1"], _row["Panel_Y1"])),
                        *GP.values_from_ladder([(30.0, float(_ty0)), (20.0, _ty0 + 100.0), (10.0, _ty0 + 200.0)]))
_tpic = Image.open(GP.proposal_overlay(_im, _top, os.path.join(ROOT, "top.png"))).convert("RGB")
_tpx = _tpic.load()
_above = sum(1 for x in range(_tpic.size[0]) for y in range(min(10, _tpic.size[1]))
             if _tpx[x, y] == (190, 60, 190))
_anywhere = sum(1 for x in range(_tpic.size[0]) for y in range(_tpic.size[1])
                if _tpx[x, y] == (190, 60, 190))
check("a value at the frame's top edge is written inside the picture, not out through the crop",
      _anywhere > 0 and _above == 0, "%d magenta px in the top rows" % _above)

# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.

# THE FRAME'S LEFT EDGE IS NOT ALWAYS THE AXIS. `find_frame` returns the
# leftmost long rule in the region, and on a boxed panel that is the box, with
# the plot's spine and every numeral INSIDE it. Publication PONE-0032854 puts
# the border at x 2 and the spine at x 499; 104 of this corpus's 282 refusals
# have such a rule inside their frame, and reading from it rescues 27.
print()
print("when the frame's left edge reads nothing, the rule inside it is tried")
_SPINE = int(_row["Panel_X0"]) + 100
# 이 틀 안에, 밑선 위로 한 칸이 남게. 밑선에 설 라벨의 자리가 있어야 합니다.
_LADDER = [(30.0, float(_row["Panel_Y0"]) + 40), (20.0, float(_row["Panel_Y0"]) + 90),
           (10.0, float(_row["Panel_Y0"]) + 140)]
_LSTR = ";".join("%g@%g" % p for p in _LADDER)


def _reading_spy(good_at):
    """A y_tick_labels that only reads at `good_at`, and says where it was asked."""
    asked = []

    def spy(img, dark, box, spine_x, baseline_y=None, **kw):
        asked.append(int(spine_x))
        return list(_LADDER) if int(spine_x) == good_at else []
    return spy, asked


_spy, _asked = _reading_spy(_SPINE)
import axis_reader as A                                           # noqa: E402
_real_labels, _real_inner, _real_near = A.y_tick_labels, A.inner_spine, A.label_near
A.y_tick_labels = _spy
A.inner_spine = lambda dark, box, **kw: _SPINE
A.label_near = lambda *a, **k: []          # 밑선 띠는 아래에서 따로 봅니다
try:
    _inner_row = GP.read_tick_values(_im, dict(_row))
finally:
    A.y_tick_labels, A.label_near = _real_labels, _real_near
check("a panel that reads nothing at its frame's edge is asked again at the rule inside",
      _asked == [int(_row["Panel_X0"]), _SPINE], "%s" % _asked)
check("and what the rule read is the reading",
      _inner_row["Y_Tick_Read_Status"] == GP.READ_OK
      and _inner_row["Y_Tick_Read_Values"] == _LSTR,
      "%s" % _inner_row["Y_Tick_Read_Values"])
check("the line it was read from is named, not left to be guessed",
      _inner_row["Y_Axis_Spine_X"] == str(_SPINE), _inner_row["Y_Axis_Spine_X"])
check("and the detail says the frame is wider than the plot",
      ("x=%d" % _SPINE) in _inner_row["Y_Tick_Read_Detail"]
      and ("x=%s" % _row["Panel_X0"]) in _inner_row["Y_Tick_Read_Detail"],
      _inner_row["Y_Tick_Read_Detail"][-90:])

# REVERT: try the inner rule always. The 660 panels that read from their frame
# must read exactly as before - this is a second question asked of a panel that
# came up empty, like the Otsu threshold and the second OCR pass.
_spy2, _asked2 = _reading_spy(int(_row["Panel_X0"]))
_inner_called = []
A.y_tick_labels = _spy2
A.label_near = lambda *a, **k: []
A.inner_spine = lambda dark, box, **kw: (_inner_called.append(1) or _SPINE)
try:
    _first_row = GP.read_tick_values(_im, dict(_row))
finally:
    A.y_tick_labels, A.inner_spine, A.label_near = _real_labels, _real_inner, _real_near
check("a panel that read at its frame's edge is not asked twice",
      _asked2 == [int(_row["Panel_X0"])] and not _inner_called,
      "%s %s" % (_asked2, _inner_called))
check("and carries no other line", _first_row["Y_Axis_Spine_X"] == "",
      _first_row["Y_Axis_Spine_X"])

# REVERT: take the inner rule's answer whatever it says. Both reads refusing is
# the ordinary case (255 of this corpus's panels), and a refusal that names a
# line it "read from" sends the next person to the wrong line.
_spy3, _asked3 = _reading_spy(-1)                     # nothing reads anywhere
A.y_tick_labels = _spy3
A.label_near = lambda *a, **k: []
A.inner_spine = lambda dark, box, **kw: _SPINE
try:
    _none_row = GP.read_tick_values(_im, dict(_row))
finally:
    A.y_tick_labels, A.inner_spine, A.label_near = _real_labels, _real_inner, _real_near
check("when the rule inside reads nothing either, the panel is refused",
      _none_row["Y_Tick_Read_Status"] == GP.READ_REFUSED
      and _none_row["Y_Tick_Read_Values"] == "", _none_row["Y_Tick_Read_Status"])
check("and it names no line it did not read from",
      _none_row["Y_Axis_Spine_X"] == "" and "x=%d" % _SPINE not in _none_row["Y_Tick_Read_Detail"],
      "%s / %s" % (_none_row["Y_Axis_Spine_X"], _none_row["Y_Tick_Read_Detail"][:60]))

# REVERT: read from the inner rule and draw the frame as if nothing happened.
# The frame IS wrong on these panels, and a person confirming values whose
# provenance is invisible is confirming arithmetic again.
_ipic = Image.open(GP.proposal_overlay(_im, _inner_row, os.path.join(ROOT, "inner.png"))).convert("RGB")
_ipx = _ipic.load()
_ox, _oy = GP.overlay_origin(_inner_row)
# 굵기 3의 세로선은 가운데 열에 다 찍히지 않습니다 - 그 자리 ±2열 중 가장 긴 것.
_col = _SPINE - _ox
_down = max(sum(1 for y in range(_ipic.size[1]) if _ipx[c, y] == (190, 60, 190))
            for c in range(max(0, _col - 2), min(_ipic.size[0], _col + 3)))
check("the line the values came from is drawn on the picture",
      _down > 0.5 * (int(_row["Panel_Y1"]) - int(_row["Panel_Y0"])), "%d px" % _down)

# THE LABEL SITTING ON THE BASELINE IS THE ONE THE CROP CUTS, and on a y axis
# it is usually the 0. Only 63 of this corpus's 685 read panels had a 0 in
# their ladder; 306 more have one printed at the baseline, cut in half by a
# crop that stops ten pixels past it. The 0 is the label worth the most: a bar
# chart's bars all start there.
print()
print("the label standing on the baseline is read from its own band")
_PITCH = _LADDER[1][1] - _LADDER[0][1]
_BASE_ROW = _LADDER[-1][1] + _PITCH


def _with_band(found):
    """Run a reading whose strip search gives `_LADDER` and whose baseline band
    gives `found`, and hand back the row and what the band was asked."""
    asked = []

    def band(img, dark, box, spine_x, row, half, scale=3):
        asked.append((int(row), int(half)))
        return list(found)
    spy, _a = _reading_spy(int(_row["Panel_X0"]))
    A.y_tick_labels, A.label_near = spy, band
    try:
        return GP.read_tick_values(_im, dict(_row)), asked
    finally:
        A.y_tick_labels, A.label_near = _real_labels, _real_near


_deep_row, _dasked = _with_band([(0.0, _BASE_ROW)])
check("the band beside the baseline is read once the strip search has a ladder",
      len(_dasked) == 1 and _dasked[0][0] == int(_row["Panel_Y1"]), "%s" % _dasked)
check("and it is half a label's pitch tall, not a fixed number of pixels",
      abs(_dasked[0][1] - 0.55 * _PITCH) <= 1, "%s vs pitch %s" % (_dasked[0][1], _PITCH))
check("a numeral that falls on the same line as the labels already read joins them",
      _deep_row["Y_Tick_Read_Values"] == _LSTR + ";0@%g" % _BASE_ROW
      and _deep_row["Y_Tick_Read_Last"] == "0", _deep_row["Y_Tick_Read_Values"])
check("and the detail says where it came from",
      "LABEL ON THE BASELINE" in _deep_row["Y_Tick_Read_Detail"],
      _deep_row["Y_Tick_Read_Detail"][-80:])

# REVERT: accept the numeral for being where a label would be. The band holds
# whatever is printed down there - the x axis's own leftmost numeral, a
# footnote marker, half of a caption - and a value that does not fall on the
# ladder's line is not this axis's label.
for _name, _found in (("a numeral off the ladder's line", [(7.0, _BASE_ROW)]),
                      ("nothing at all", []),
                      ("a numeral on a row already read", [(0.0, _LADDER[-1][1] + 2)])):
    _kept_row, _ = _with_band(_found)
    check("the reading is unchanged when the band gives %s" % _name,
          _kept_row["Y_Tick_Read_Values"] == _LSTR
          and "LABEL ON THE BASELINE" not in _kept_row["Y_Tick_Read_Detail"],
          _kept_row["Y_Tick_Read_Values"])

# REVERT: read the band even when the lowest label already stands on the
# baseline. There is no room for a label below it, and the band would hold the
# label that was already read.
_low = [(30.0, float(_row["Panel_Y1"]) - 100), (20.0, float(_row["Panel_Y1"]) - 50),
        (10.0, float(_row["Panel_Y1"]))]
_asked_low = []


def _band_low(img, dark, box, spine_x, row, half, scale=3):
    _asked_low.append(row)
    return [(0.0, row + 50)]


_spy_low, _ = _reading_spy(int(_row["Panel_X0"]))
A.y_tick_labels = lambda *a, **k: list(_low)
A.label_near = _band_low
try:
    _low_row = GP.read_tick_values(_im, dict(_row))
finally:
    A.y_tick_labels, A.label_near = _real_labels, _real_near
check("a ladder that already reaches the baseline is not asked for one more",
      not _asked_low, "%s" % _asked_low)

# A ROW OF PANELS WITH ONE AXIS. This corpus prints Day/Night, left/right
# column, with the y axis on the leftmost panel and nothing on the rest. Those
# panels have no labels to read and none for a person to type; what a person
# can say is "it uses p1's axis". The machine names the neighbour, and only
# names it - whether the axis is shared is the person's call, because a panel
# with its own unread axis looks the same from here.
print()
print("a panel with no axis of its own is offered its neighbour's")
def _p(pid, x0, x1, y0, y1, ticks, read, raster="a.png"):
    return {"Proposal_ID": pid, "Raster": raster, "Panel_X0": x0, "Panel_X1": x1,
            "Panel_Y0": y0, "Panel_Y1": y1, "Y_Tick_Count": ticks,
            "Y_Tick_Read_Status": read, "Y_Tick_Pixels": "60;200;340",
            "Y_Tick_Read_Values": "40@60;30@200;20@340" if read == GP.READ_OK else "",
            "Human_Verification_Status": GP.PROPOSAL_PENDING}
_fig = [_p("p1", 100, 400, 50, 450, 4, GP.READ_OK),          # row 1: the axis
        _p("p2", 500, 800, 53, 449, 0, GP.READ_REFUSED),      #   same row, no ticks
        _p("p3", 900, 1200, 52, 451, 4, GP.READ_REFUSED),     #   same row, own ticks, unread
        _p("p7", 1300, 1600, 50, 450, 4, GP.READ_OK),         #   same row, read its own
        _p("p4", 100, 400, 500, 900, 0, GP.READ_REFUSED),     # row 2: leftmost, no ticks
        _p("p5", 500, 800, 500, 930, 0, GP.READ_REFUSED),     #   frame 7% off the row
        _p("p9", 900, 1200, 500, 900, 4, GP.READ_OK),         #   an axis, to the RIGHT of p4
        _p("p10", 100, 400, 950, 1350, 4, GP.READ_OK),        # row 3: two axes
        _p("p11", 500, 800, 950, 1350, 4, GP.READ_OK),
        _p("p12", 900, 1200, 950, 1350, 0, GP.READ_REFUSED),  #   beside the second
        _p("p6", 100, 400, 50, 450, 0, GP.READ_REFUSED, raster="b.png")]  # another raster
_named = GP.shared_axis_candidates(_fig)
_cand = dict((r["Proposal_ID"], r["Y_Axis_Shared_Candidate"]) for r in _fig)
_by = dict((r["Proposal_ID"], r) for r in _fig)
check("the panel to the right with no ticks is offered the axis on its rows",
      _cand["p2"] == "p1", "%s" % _cand)
check("and so is one with unread ticks of its own, with a warning",
      _cand["p3"] == "p1" and "눈금 4개" in _by["p3"]["Y_Axis_Shared_Detail"],
      _by["p3"]["Y_Axis_Shared_Detail"])
check("a neighbour without ticks in between is skipped, not offered",
      _cand["p3"] == "p1" and _by["p2"]["Y_Tick_Count"] == 0)
check("the nearest axis to the left is offered, not the leftmost",
      _cand["p12"] == "p11", "%s" % _cand["p12"])
check("the panel that read its own axis is offered nothing", _cand["p1"] == "" and _cand["p7"] == "")
check("nor one with an axis only to its right", _cand["p4"] == "", "%s" % _cand["p4"])
check("nor one whose frame stands on other rows", _cand["p5"] == "")
check("nor one on another raster", _cand["p6"] == "")
check("and the count is the rows named", _named == 3, "%s" % _named)

# What a SHARED verdict may say.
_ok = dict(_fig[1], Human_Verification_Status="SHARED", Verified_By="MC",
           Verified_At="2026-09-10", Y_Axis_Shared_With="p1")
_owner = dict(_fig[0], Human_Verification_Status="CONFIRMED", Verified_By="MC",
              Verified_At="2026-09-10", Y_Tick_Top_Value="40", Y_Tick_Bottom_Value="20",
              Confirmed_Tick_Values="40@60;20@340")
def _codes(rows):
    return [c for _p, c, _d in GP.proposal_problems(rows)]
check("a SHARED row naming a neighbour on its own rows is in order",
      _codes([_owner, _ok]) == [], "%s" % _codes([_owner, _ok]))
check("one naming no panel is refused",
      "PROPOSAL_SHARED_WITHOUT_A_TARGET" in _codes([_owner, dict(_ok, Y_Axis_Shared_With="")]))
check("one naming itself is refused",
      "PROPOSAL_SHARED_WITH_ITSELF" in _codes([_owner, dict(_ok, Y_Axis_Shared_With="p2")]))
check("one naming a panel on another raster is refused",
      "PROPOSAL_SHARED_ACROSS_RASTERS" in _codes([_owner, dict(_ok, Raster="b.png")]))
check("one naming a panel on other rows is refused",
      "PROPOSAL_SHARED_FRAME_MISALIGNED" in _codes([_owner, dict(_ok, Panel_Y1=520)]))
check("one carrying a tick value of its own is refused",
      "PROPOSAL_SHARED_WITH_A_TICK_VALUE" in _codes([_owner, dict(_ok, Y_Tick_Bottom_Value="0")]))
check("a PENDING row that already names a shared axis is refused",
      "PROPOSAL_PENDING_WITH_A_SHARED_AXIS" in _codes([dict(_fig[1], Y_Axis_Shared_With="p1")]))
check("and a CONFIRMED row that also names one is one or the other",
      "PROPOSAL_CONFIRMED_NAMES_A_SHARED_AXIS" in _codes([dict(_owner, Y_Axis_Shared_With="p3")]))
check("the machine's candidate on a PENDING row is not an answer",
      _codes([_fig[1]]) == [], "%s" % _codes([_fig[1]]))
check("a SHARED row carrying the copied pairs calibrates on them",
      GP.calibration_from(dict(_ok, Confirmed_Tick_Values="40@60;20@340")) == [[40.0, 60.0], [20.0, 340.0]])
check("and one that has not been through the gate calibrates nothing",
      GP.calibration_from(_ok) is None)

# The neighbour's ticks, drawn on this panel so the person can see whether
# they land on its gridlines and frame.
_spic = Image.open(GP.proposal_overlay(_im, _row, os.path.join(ROOT, "shared.png"),
                                       shared_ticks=[int(_row["Panel_Y0"]) + 40])).convert("RGB")
_spx = _spic.load()
_orange = sum(1 for x in range(_spic.size[0]) for y in range(_spic.size[1])
              if _spx[x, y] == (230, 120, 20))
_plain = Image.open(GP.proposal_overlay(_im, _row, os.path.join(ROOT, "plain.png"))).convert("RGB")
_ppx2 = _plain.load()
_orange0 = sum(1 for x in range(_plain.size[0]) for y in range(_plain.size[1])
               if _ppx2[x, y] == (230, 120, 20))
check("the neighbour's tick rows are drawn on this panel in their own colour",
      _orange > 0 and _orange0 == 0, "%d / %d" % (_orange, _orange0))

# WHERE THE OVERLAY SITS ON THE RASTER. The page lets a person point at a
# tick on the overlay; the row they pointed at is a raster row only through
# this offset. REVERT: let the page guess the pad - every pointed tick lands
# a pad's width off, with nothing to say so.
print()
print("the overlay's origin is stated, and it is where the crop was cut")
_reg = dict(_row, Region="%d,%d,%d,%d" % (int(_row["Panel_X0"]) - 30, int(_row["Panel_Y0"]) - 25,
                                           int(_row["Panel_X1"]) + 30, int(_row["Panel_Y1"]) + 25))
_opic = Image.open(GP.proposal_overlay(_im, _reg, os.path.join(ROOT, "origin.png"))).convert("RGB")
_ox, _oy = GP.overlay_origin(_reg)
_edge = _opic.getpixel((int(_reg["Panel_X1"]) - _ox, int(_reg["Panel_Y0"]) + 50 - _oy))
check("the frame's right edge is at Panel_X1 minus the origin", _edge == (200, 30, 30), "%s" % (_edge,))
check("and a row without a region starts at the raster's corner", GP.overlay_origin(dict(_reg, Region="")) == (0, 0))

# THE LADDER HAS SLACK AND THE TICK GRID HAS NONE. `axis_reader.ladder` lets
# value-per-pixel vary 8% because OCR rows wobble, and a misread that lands
# inside the 8% passes: publication ASEM-P577's `200 150 100 50 0` read
# `190 100 20` (6.4%) and stood. Snapped to the ticks the same proposal
# measured, 377 of this corpus's 378 checkable panels are exactly constant.
print()
print("a reading is put to the tick grid its own proposal measured")
_GRID = {"Y_Tick_Read_Status": GP.READ_OK, "Y_Tick_Pixels": "1870.5;2039.5;2208;2377.5;2546"}
_asem = GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="190@2039.5;100@2208;20@2378"))
check("labels on the ticks whose value per tick is not constant are warned about",
      _asem[0] == GP.WARN_TICK_STEP and "11.8%" in _asem[1], "%s" % (_asem,))
check("the printed axis on the same ticks is not",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="150@2039.5;100@2208;50@2378")) == ("", ""))
# REVERT: demand exact equality. Labels printed to three digits - 33.3 66.7
# 100 - differ by 0.3% per tick and are an axis, not a misread.
check("labels rounded on the page are not a misread",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="100@2039.5;66.7@2208;33.3@2378")) == ("", ""),
      "%s" % (GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="100@2039.5;66.7@2208;33.3@2378")),))
# The step is per TICK, so labels two ticks apart carry two steps.
check("labels two ticks apart carry two steps",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="40@1870.5;20@2208;10@2377.5")) == ("", ""),
      "%s" % (GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="40@1870.5;20@2208;10@2377.5")),))
# REVERT: read the tick list as a grid whatever is in it. Stray marks - data
# points, gridlines - get into the tick list (S41526's D006 has 1720 1866 2014
# 2083 2142 2159), and against such a list an honest axis looks uneven.
_STRAY = dict(_GRID, Y_Tick_Pixels="0;100;140;200;300;400",
              Y_Tick_Read_Values="40@0;26@140;0@400")
check("a tick list with stray marks in it says nothing",
      GP.warn_reading(_STRAY) == ("", ""), "%s" % (GP.warn_reading(_STRAY),))
_OFF = dict(_GRID, Y_Tick_Read_Values="9@1900;7@2100;1@2300")
_off = GP.warn_reading(_OFF)
check("three labels that sit on no tick at all are warned about",
      _off[0] == GP.WARN_OFF_THE_TICKS and "none of the 5 ticks" in _off[1], "%s" % (_off,))
# REVERT: warn whenever the labels are off the grid. 99 of this corpus's read
# panels are, and most of them are long ladders that checked themselves; the
# shortest ladder accepted is the one that never was.
check("four such labels are a ladder that checked itself",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="9@1900;7@2100;5@2300;3@2500")) == ("", ""))
check("some labels on the grid and some off is not measured either way",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="190@2039.5;100@2208;20@2383")) == ("", ""),
      "%s" % (GP.warn_reading(dict(_GRID, Y_Tick_Read_Values="190@2039.5;100@2208;20@2383")),))
check("a proposal with too few ticks measured says nothing",
      GP.warn_reading(dict(_GRID, Y_Tick_Pixels="2039.5;2208",
                           Y_Tick_Read_Values="190@2039.5;100@2208;20@2378")) == ("", ""))
check("and a refused reading has nothing to put to the grid",
      GP.warn_reading(dict(_GRID, Y_Tick_Read_Status=GP.READ_REFUSED,
                           Y_Tick_Read_Values="190@2039.5;100@2208;20@2378")) == ("", ""))

print()
print("the warning rides in the proposal, beside the reading and not instead of it")
_trows = [float(t) for t in _row["Y_Tick_Pixels"].split(";")][:3]
_UNEVEN = [(190.0, _trows[0]), (100.0, _trows[1]), (20.0, _trows[2])]
_EVEN = [(150.0, _trows[0]), (100.0, _trows[1]), (50.0, _trows[2])]


def _read_with(ladder):
    real = A.y_tick_labels, A.inner_spine, A.label_near
    A.y_tick_labels = lambda img, dark, box, spine_x, baseline_y=None, **kw: list(ladder)
    A.inner_spine = lambda dark, box, **kw: None
    A.label_near = lambda *a, **k: []
    try:
        return GP.read_tick_values(_im, dict(_row))
    finally:
        A.y_tick_labels, A.inner_spine, A.label_near = real


_wrow = _read_with(_UNEVEN)
check("an uneven reading is still READ, with its values",
      _wrow["Y_Tick_Read_Status"] == GP.READ_OK and GP.read_values_of(_wrow) == _UNEVEN,
      "%s %s" % (_wrow["Y_Tick_Read_Status"], _wrow["Y_Tick_Read_Values"]))
check("and carries the warning in its own column",
      _wrow["Y_Tick_Read_Warning"].startswith(GP.WARN_TICK_STEP + ": "),
      "%r" % (_wrow["Y_Tick_Read_Warning"],))
_erow = _read_with(_EVEN)
check("an even one carries none", _erow["Y_Tick_Read_Warning"] == "",
      "%r" % (_erow["Y_Tick_Read_Warning"],))
check("the column is a proposal column, so it reaches the CSV and the page",
      "Y_Tick_Read_Warning" in GP.PROPOSAL_COLUMNS)

print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
import shutil                                                    # noqa: E402
shutil.rmtree(ROOT, ignore_errors=True)
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
