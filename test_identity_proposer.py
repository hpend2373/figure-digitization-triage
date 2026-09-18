# -*- coding: utf-8 -*-
"""What the identity reader proposes, and what it refuses.

    python3 test_identity_proposer.py     # exit 0 = all scenarios pass

The words are faked in most scenarios - `_words` is replaced by a function
that returns the planted words inside the box it is asked about - so what is
under test is the rule, not tesseract: labels are joined by gap, positions
must stand at one pitch, a legend must name the plot's colours one each, a
title ends at its unit. Two scenarios at the end read real glyphs and skip
where tesseract is not installed.
"""
import csv
import os
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402

N = [0]
FAIL = []
SKIPPED = [0]


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def has_ocr():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ROOT = tempfile.mkdtemp(prefix="fdt_identity_")

RED, BLUE, GREEN = (220, 40, 40), (40, 80, 220), (40, 180, 60)
FRAME = (100, 700, 60, 460)          # x0, x1, y0, y1 - the proposal order
REGION = "20,20,760,540"


def fixture(colours=(RED, BLUE), legend=True, bars=4):
    """A bar panel: `bars` groups, one bar per colour in each, a legend of
    swatches inside the frame. No text is drawn - the words are planted."""
    im = Image.new("RGB", (800, 560), "white")
    d = ImageDraw.Draw(im)
    x0, x1, y0, y1 = FRAME
    d.rectangle((x0, y0, x1, y1), outline="black", width=2)
    pitch = (x1 - x0) / float(bars)
    for g in range(bars):
        cx = x0 + pitch * (g + 0.5)
        for k, c in enumerate(colours):
            bx = cx - 12 * len(colours) + 24 * k
            d.rectangle((bx, y1 - 80 - 40 * k - 20 * g, bx + 20, y1 - 2), fill=c)
    if legend:
        for k, c in enumerate(colours):
            d.rectangle((520, 80 + 26 * k, 540, 96 + 26 * k), fill=c)
    return im


def planted(words):
    """A `_words` that returns the planted (text, x, y, conf, h, w) inside the box."""
    def fake(img, box, scale=3, psm="11", whitelist=None):
        left, top, right, bottom = [int(v) for v in box]
        return [w for w in words if left <= w[1] <= right and top <= w[2] <= bottom]
    return fake


def word(text, x, y, h=18, conf=90):
    return (text, float(x), float(y), float(conf), float(h), 9.0 * len(text))


def geometry_row(**over):
    row = {c: "" for c in GP.PROPOSAL_COLUMNS}
    row.update({"Proposal_ID": "GP001", "Raster": "fix.png", "Raster_SHA256": "abc",
                "Region": REGION, "Panel_X0": FRAME[0], "Panel_X1": FRAME[1],
                "Panel_Y0": FRAME[2], "Panel_Y1": FRAME[3],
                "Group_Anchor_Pixels": ";".join("%g" % (FRAME[0] + 150 * (g + 0.5)) for g in range(4)),
                "Group_Anchor_Count": 4, "Human_Verification_Status": "CONFIRMED"})
    row.update(over)
    return row


_real_words = IP._words
_real_ocr = IP.A.pytesseract


class FakeOCR(object):
    """A pytesseract that reads the planted title."""
    class Output(object):
        DICT = "dict"

    def __init__(self, tokens, conf=90):
        self.tokens, self.conf = tokens, conf

    def image_to_data(self, big, config="", output_type=None):
        return {"text": list(self.tokens), "conf": [self.conf] * len(self.tokens),
                "left": [0] * len(self.tokens), "top": [0] * len(self.tokens),
                "width": [10] * len(self.tokens), "height": [10] * len(self.tokens)}


def with_fakes(words, title_tokens):
    IP._words = planted(words)
    IP.A.pytesseract = FakeOCR(title_tokens)


def restore():
    IP._words = _real_words
    IP.A.pytesseract = _real_ocr


X_LABELS = [word("Pre", 175, 480), word("D1", 325, 480), word("D3", 475, 480), word("R0", 625, 480)]
LEGEND = [word("Fluid", 570, 88), word("Control", 578, 114)]

print("the x labels are read as words, joined by gap, and must stand at one pitch")
im = fixture()
with_fakes(X_LABELS + LEGEND, ["Heart", "rate", "(bpm)"])
row = IP.propose_identity(im, geometry_row(), kind="BAR", caption="Values are mean, n = 8.")
restore()
check("four labels are read at their positions",
      row["X_Label_Read_Status"] == IP.READ_OK
      and IP.labels_of(row["X_Labels_Read"]) == [("Pre", 175.0), ("D1", 325.0), ("D3", 475.0), ("R0", 625.0)],
      "%s %s" % (row["X_Label_Read_Status"], row["X_Labels_Read"]))
check("the frame's anchors agree, and it says so", "anchors agree" in row["X_Label_Detail"], row["X_Label_Detail"])
check("a categorical axis is not numeric", row["X_Numeric"] == "")

with_fakes([word("D1", 165, 480), word("evening", 200, 480), word("D3", 325, 480),
            word("D5", 475, 480), word("R0", 625, 480)], ["Heart", "rate", "(bpm)"])
# REVERT: every word is its own label. "D1 evening" is one label on this
# corpus's figure 2, and as two it stands at no pitch.
joined = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
check("two words that nearly touch are one label", joined[0] == IP.READ_OK and joined[1][0][0] == "D1 evening",
      "%s %s" % (joined[0], joined[1]))

with_fakes([word("Pre", 175, 480), word("D1", 260, 480), word("D3", 475, 480), word("R0", 625, 480)], [])
uneven = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
# REVERT: labels anywhere are accepted. A joined or split label lands off the
# pitch, and the pitch is the one thing the reader did not produce.
check("labels off one pitch are refused, with the gaps",
      uneven[0] == IP.READ_REFUSED and "one pitch" in uneven[2], "%s %s" % (uneven[0], uneven[2]))
with_fakes([word("Pre", 175, 480), word("D1", 325, 480), word("D1", 475, 480), word("R0", 625, 480)], [])
dup = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
check("the same label twice is refused", dup[0] == IP.READ_REFUSED and "twice" in dup[2], dup[2])
with_fakes([word("0", 175, 480), word("10", 325, 480), word("20", 475, 480), word("40", 625, 480)], [])
ladder = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
check("numeric labels that are not a ladder are refused",
      ladder[0] == IP.READ_REFUSED and "ladder" in ladder[2] and ladder[3] is True, "%s %s" % (ladder[0], ladder[2]))
with_fakes([word("0", 175, 480), word("10", 325, 480), word("20", 475, 480), word("30", 625, 480)], [])
ladder = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
check("numeric labels that are a ladder are read, and marked numeric", ladder[0] == IP.READ_OK and ladder[3] is True)
with_fakes([word("—", 175, 480), word("|", 325, 480)], [])
punct = IP.read_x_labels(im, IP._dark(im.convert("L")), FRAME, [], [int(v) for v in REGION.split(",")])
restore()
check("punctuation tesseract makes of tick marks is not a word", punct[0] == IP.READ_REFUSED and "no word" in punct[2], punct[2])
check("anchors that disagree are reported, not obeyed",
      IP.anchor_agreement([("a", 100.0), ("b", 200.0), ("c", 300.0)], [100.0, 205.0]) == "DISAGREE"
      and IP.anchor_agreement([("a", 100.0), ("b", 200.0)], [100.0, 200.0, 300.0]) == "DISAGREE"
      and IP.anchor_agreement([("a", 100.0), ("b", 200.0)], [102.0, 198.0]) == "AGREE"
      and IP.anchor_agreement([("a", 100.0)], []) == "NO_ANCHORS")
check("the strip may reach a little past the region, not far",
      IP.label_strip(im, FRAME, [20, 20, 760, 470])[1] == min(560, 470 + int(0.12 * 400), 460 + 88))

print()
print("the legend must name the plot's colours, one each")
colours = IP.plot_colours(im.convert("RGB"), FRAME)
check("two chromatic colours are found in the plot, grey ink is not one",
      len(colours) == 2 and {tuple(c[2]) for c in colours} == {RED, BLUE} or
      len(colours) == 2 and all(min(abs(c[2][i] - t[i]) for t in (RED, BLUE)) < 12 for c in colours for i in range(3)),
      "%s" % (colours,))
check("the series are read with the legend's names and the plot's colours",
      row["Series_Read_Status"] == IP.READ_OK
      and [n for n, _c in IP.series_of(row["Series_Read"])] == ["Fluid", "Control"],
      "%s %s %s" % (row["Series_Read_Status"], row["Series_Read"], row["Series_Detail"]))
check("a colour bar panel is proposed as BAR_COLOR", row["Mark_Type_Proposed"] == "BAR_COLOR")
with_fakes(X_LABELS + [word("Fluid", 570, 88)], [])
one = IP.read_legend(im, im.convert("RGB"), FRAME, [int(v) for v in REGION.split(",")], colours)
restore()
# REVERT: a plot colour no legend entry names is filled in. That is a series
# nobody declared, and the grid gate would file its values under nothing.
check("a plot colour the legend does not name refuses the set",
      one[0] == IP.READ_REFUSED and "named by no legend entry" in one[2], "%s %s" % (one[0], one[2]))
im3 = fixture(colours=(RED, BLUE), legend=False)
d = ImageDraw.Draw(im3)
d.rectangle((520, 80, 540, 96), fill=GREEN)
with_fakes([word("Sham", 570, 88)], [])
alien = IP.read_legend(im3, im3.convert("RGB"), FRAME, [int(v) for v in REGION.split(",")], colours)
restore()
check("a legend colour the plot does not contain refuses the set",
      alien[0] == IP.READ_REFUSED and "does not contain" in alien[2], "%s %s" % (alien[0], alien[2]))
im1 = fixture(colours=(RED,), legend=False)
with_fakes(X_LABELS, [])
single = IP.read_legend(im1, im1.convert("RGB"), FRAME, [int(v) for v in REGION.split(",")],
                        IP.plot_colours(im1.convert("RGB"), FRAME))
restore()
check("one colour and no legend is one unnamed series", single[0] == IP.READ_OK and single[1][0][0] == ""
      and single[1][0][1] is not None, "%s" % (single,))
# NEARLY grey, as printed ink is: a saturation of 0.09, well under the line.
imm = fixture(colours=((70, 64, 64),), legend=False)
mono = IP.read_legend(imm, imm.convert("RGB"), FRAME, [int(v) for v in REGION.split(",")],
                      IP.plot_colours(imm.convert("RGB"), FRAME))
check("grey ink is no colour, and a mono panel's series are refused to the person",
      mono[0] == IP.READ_REFUSED and "no chromatic ink" in mono[2], "%s" % (mono,))
with_fakes(X_LABELS, ["Heart", "rate", "(bpm)"])
rowm = IP.propose_identity(imm, geometry_row(), kind="BAR")
restore()
check("a mono bar panel is proposed as BAR_MONO", rowm["Mark_Type_Proposed"] == "BAR_MONO", rowm["Mark_Type_Proposed"])
check("a box panel is BOX_VIOLIN whatever its colour", IP.MARK_TYPES_FOR["BOX"] == ("BOX_VIOLIN",))

print()
print("the y title is the strip left of the numerals, and it ends at its unit")
check("the title is split into outcome and unit",
      row["Y_Title_Read_Status"] == IP.READ_OK and row["Outcome_Read"] == "Heart rate" and row["Unit_Read"] == "bpm",
      "%s %r %r" % (row["Y_Title_Read_Status"], row["Outcome_Read"], row["Unit_Read"]))
check("a title without a unit keeps the text and an empty unit", IP.split_title("Renin") == ("Renin", ""))
check("square brackets are a unit too", IP.split_title("Distance [m]") == ("Distance", "m"))
IP.A.pytesseract = FakeOCR(["CTx", "(pmol.L)", "NO", "O1"])
tail = IP.read_y_title(im, IP._dark(im.convert("L")), FRAME, FRAME[0], [int(v) for v in REGION.split(",")])
restore()
# REVERT: stray capitals after the unit stay in the title. Tick marks and the
# panel's letter read as "NO O1" on this corpus's figure 5b.
check("stray capitals after the unit are dropped", tail[0] == IP.READ_OK and tail[1] == "CTx (pmol.L)", "%r" % (tail,))
# A panel with no numerals of its own: the first ink left of the spine IS
# the title, and the strip left of it is nothing. Then the whole strip is
# read. REVERT: refuse it, and every shared-axis panel loses its title.
imt = fixture()
ImageDraw.Draw(imt).rectangle((24, 160, 54, 400), fill="black")
IP.A.pytesseract = FakeOCR(["Heart", "rate", "(bpm)"])
own = IP.read_y_title(imt, IP._dark(imt.convert("L")), FRAME, FRAME[0], [int(v) for v in REGION.split(",")])
restore()
check("a title that is the only ink left of the spine is still read",
      own[0] == IP.READ_OK and own[2] == "Heart rate", "%r" % (own,))
IP.A.pytesseract = FakeOCR(["Lo", "LG"])
junk = IP.read_y_title(im, IP._dark(im.convert("L")), FRAME, FRAME[0], [int(v) for v in REGION.split(",")])
restore()
check("two stray letters are not a title", junk[0] == IP.READ_REFUSED and "not a title" in junk[4], "%r" % (junk,))
IP.A.pytesseract = FakeOCR(["©", "|"])
none = IP.read_y_title(im, IP._dark(im.convert("L")), FRAME, FRAME[0], [int(v) for v in REGION.split(",")])
restore()
check("punctuation alone is no title", none[0] == IP.READ_REFUSED, "%r" % (none,))

print()
print("n comes from the caption, and only when the caption prints one n")
check("n = 8 is read", IP.read_n("Values are mean, n = 8.") == (IP.READ_OK, "8", "n = 8 in the caption")
      and row["N_Read"] == "8")
check("N=12 is read too", IP.read_n("N=12 subjects")[1] == "12")
# REVERT: the first n wins. A caption naming n = 8 and n = 6 is two groups, and
# which one this panel is, the caption does not say.
check("several different n refuse", IP.read_n("n = 8 men and n = 6 women")[0] == IP.READ_REFUSED)
check("the same n twice is one n", IP.read_n("n = 8; n = 8")[1] == "8")
check("no n is refused, not invented", IP.read_n("no sample size here") == (IP.READ_REFUSED, "", "the caption prints no n ="))

print()
print("the proposal row carries the frame it was read on and nothing a person owns")
check("the row has every column and is PENDING",
      set(row) == set(IP.IDENTITY_COLUMNS) and row["Human_Verification_Status"] == IP.PENDING
      and row["X_Factor"] == "" and row["Series_Factor"] == "" and row["Outcome_Name"] == "")
check("the frame and raster are the geometry's", (row["Panel_X0"], row["Panel_X1"]) == (100, 700)
      and row["Raster"] == "fix.png" and row["Raster_SHA256"] == "abc")
drawn = geometry_row(Group_Anchor_Pixels="", Group_Anchor_Count=0, Frame_Source="DRAWN")
with_fakes(X_LABELS + LEGEND, [])
rowd = IP.propose_identity(im, drawn, kind="BAR")
restore()
# REVERT: a drawn frame's anchors stay empty. The page then cannot say
# whether the labels agree with anything, on exactly the frames a person
# had to draw by hand.
check("a drawn frame carries no anchors, so they are measured afresh",
      rowd["X_Anchor_Source"] in ("BOX", "GROUP") and int(rowd["X_Anchor_Count"]) > 0
      and rowd["X_Label_Read_Status"] == IP.READ_OK,
      "%s %s %s" % (rowd["X_Anchor_Source"], rowd["X_Anchor_Count"], rowd["X_Label_Read_Status"]))
path = IP.write_proposals(os.path.join(ROOT, "identity_proposal.csv"), [row])
with open(path, encoding="utf-8") as fh:
    back = list(csv.DictReader(fh))
check("the file round-trips", back[0]["X_Labels_Read"] == row["X_Labels_Read"] and back[0]["Series_Read"] == row["Series_Read"])
pic = IP.overlay(im, row, os.path.join(ROOT, "GP001.png"))
check("the overlay is cut at the stated origin",
      Image.open(pic).size[0] == min(800, 760 + 12 + 160) - IP.overlay_origin(row)[0]
      and IP.overlay_origin(row) == (8, 8), "%s %s" % (Image.open(pic).size, IP.overlay_origin(row)))
check("labels_of and series_of parse what the row carries",
      IP.labels_of("D1 evening@100;D3@200") == [("D1 evening", 100.0), ("D3", 200.0)]
      and IP.series_of("Fluid@220,40,40;Control@40,80,220;Plain") == [("Fluid", (220, 40, 40)), ("Control", (40, 80, 220)), ("Plain", None)])

print()
print("and with real glyphs")
if has_ocr() and os.path.exists(FONT):
    from PIL import ImageFont
    imr = fixture()
    d = ImageDraw.Draw(imr)
    font = ImageFont.truetype(FONT, 22)
    for text, x in (("Pre", 175), ("D1", 325), ("D3", 475), ("R0", 625)):
        d.text((x - 14, 470), text, fill="black", font=font)
    for text, y in (("Fluid", 78), ("Control", 104)):
        d.text((548, y), text, fill="black", font=font)
    for text, y in (("100", 60), ("50", 260), ("0", 460)):
        d.text((66, y - 12), text, fill="black", font=font)
    title = Image.new("L", (240, 30), 255)
    ImageDraw.Draw(title).text((4, 2), "Heart rate (bpm)", fill=0, font=font)
    imr.paste(title.transpose(Image.ROTATE_90).convert("RGB"), (24, 160))
    rowr = IP.propose_identity(imr, geometry_row(), kind="BAR", caption="n = 8")
    # tesseract reads "R0" as "RO" about as often as not; the person corrects
    # it, and what is measured here is that four labels come back at one pitch.
    check("real x labels are read at one pitch",
          rowr["X_Label_Read_Status"] == IP.READ_OK and [t for t, _p in IP.labels_of(rowr["X_Labels_Read"])][:3] == ["Pre", "D1", "D3"]
          and len(IP.labels_of(rowr["X_Labels_Read"])) == 4,
          "%s %s %s" % (rowr["X_Label_Read_Status"], rowr["X_Labels_Read"], rowr["X_Label_Detail"]))
    check("a real legend names the plot's colours",
          rowr["Series_Read_Status"] == IP.READ_OK and [n for n, _c in IP.series_of(rowr["Series_Read"])] == ["Fluid", "Control"],
          "%s %s %s" % (rowr["Series_Read_Status"], rowr["Series_Read"], rowr["Series_Detail"]))
    check("a real rotated title is read and split",
          rowr["Y_Title_Read_Status"] == IP.READ_OK and rowr["Outcome_Read"] == "Heart rate" and rowr["Unit_Read"] == "bpm",
          "%s %r" % (rowr["Y_Title_Read_Status"], rowr["Y_Title_Read"]))
else:
    SKIPPED[0] = 3
    print("  skip: no tesseract or no DejaVu font - 3 glyph-reading scenarios")

import shutil                                                    # noqa: E402
shutil.rmtree(ROOT, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
