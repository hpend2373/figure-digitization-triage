"""Draw the two bar panels that publication 177 turned out to be made of.

    python3 make_whisker_fixture.py

Both are things a printed figure does and this repository had no fixture for.

    whisker_fixture.png          the whisker is drawn in the BAR'S OWN COLOUR,
                                 and it is long - longer than the 70-pixel
                                 window `read_bar_panel` searches above the top
                                 of the fill for the bar's outline.
    whisker_bracket_fixture.png  the same, plus a SIGNIFICANCE BRACKET floating
                                 above the whisker: a horizontal rule spanning
                                 the bar, with a white gap between it and
                                 everything else.

Why each one is a trap.

A colour reader finds the bar by masking the series colour, and takes the end of
that mask as the end of the bar. When the whisker is another colour that is the
bar's top. When it is the SAME colour - which is how greyscale print draws an
error bar on a black bar - the end of the mask is the tip of the whisker, and
the reader returns the CAP as the mean. On publication 177 that is 314 against a
printed 205, with no refusal and no flag.

The bracket is the reason the obvious repair does not work. Widen the window and
the first wide row above the bar is no longer the bar's outline stroke - it is
the bracket, which belongs to a p value and not to any bar. The rule that
survives both is contiguity: an outline is the ink the fill runs into, and a
bracket has white on both sides of it.

The truth file carries the values the drawing was made from, so a scenario
compares against what was drawn rather than against what the reader last did.
"""
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 620, 520
AXIS_X, BASELINE_Y, TOP_Y = 90, 460, 60
Y_MAX = 100.0                       # value at TOP_Y; 0 at BASELINE_Y
BAR_W = 90
FILL = "#000000"                    # bar and whisker: one colour
#: A cap is a THIRD of the bar, which is what print draws and what publication
#: 177 measures (36 px against a 184 px bar). A cap wider than half the bar
#: would pass the reader's own "is this row wide enough to be the outline" test
#: and the fixture would be testing something no figure does.
STEM_W, CAP_W = 4, 30

#: (Series_ID, x centre, mean, dispersion). The whisker of the second bar is
#: long on purpose: 45 units is 180 px, well past the 70-px window.
#: Far enough apart that the fragment-merge rule cannot join them: it merges
#: two runs of one colour when their gap is under half their combined width,
#: which is how a bar split by its own baseline is put back together.
BARS = [
    ("S_ONE", 200, 40.0, 12.0),
    ("S_TWO", 470, 30.0, 45.0),
]


def y_of(value):
    return BASELINE_Y - (value / Y_MAX) * (BASELINE_Y - TOP_Y)


#: The grey a printed error bar is actually drawn in. Publication 177 measures
#: 128 against a reader whose default ink level is 110, so its whiskers are not
#: ink at all and every cell of the figure came back with no dispersion.
WHISKER_GREY = "#808080"

#: A CAP LIGHTER THAN THE INK LEVEL. Publication 177 prints one at grey 215
#: against a figure whose declared level is 160, so the cap is not ink and only
#: the stem is. The reader used to answer anyway, by calling the stem's own end
#: a cap - a number about half a stroke off, wearing DIRECT_CONNECTED_CAP.
PALE_CAP = "#d7d7d7"

#: A HOLE IN THE STEM, in rows. 177 has a four-row one at 600 dpi, where the
#: JPEG dropped the stroke; the stem is 35 rows long and the hole is in the
#: middle of it. A stem is followed across a gap of two, so this breaks it, the
#: run stops at the hole, and the far end of the stump is not the cap.
STEM_HOLE = 4


def draw(path, bracket=False, whisker=None, cap_ink=None, hole=0):
    im = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(im)
    d.line((AXIS_X, TOP_Y, AXIS_X, BASELINE_Y), fill="black", width=3)
    d.line((AXIS_X, BASELINE_Y, WIDTH - 30, BASELINE_Y), fill="black", width=3)
    for v in (0, 25, 50, 75, 100):                      # tick marks, left of the axis
        y = y_of(v)
        d.line((AXIS_X - 16, y, AXIS_X, y), fill="black", width=3)
    for _sid, xc, mean, disp in BARS:
        top = y_of(mean)
        d.rectangle((xc - BAR_W // 2, top, xc + BAR_W // 2, BASELINE_Y), fill=FILL)
        cap = y_of(mean + disp)
        ink = whisker or FILL
        d.line((xc - STEM_W // 2, cap, xc - STEM_W // 2, top), fill=ink, width=STEM_W)
        d.line((xc - CAP_W // 2, cap, xc + CAP_W // 2, cap),
               fill=cap_ink or ink, width=3)
        if hole:
            # White across the stem, halfway up. Not a gap anybody drew: it is
            # what a JPEG does to a two-pixel stroke, and the figure still shows
            # a whisker to a person looking at it.
            mid = (cap + top) / 2.0
            d.rectangle((xc - STEM_W, mid, xc + STEM_W, mid + hole), fill="white")
    if bracket:
        # A significance bracket over the two bars: the horizontal rule sits
        # above both whiskers with white under it, and the two short verticals
        # come DOWN from it, as a journal draws them.
        y = y_of(90.0)
        d.line((BARS[0][1], y, BARS[1][1], y), fill=FILL, width=3)
        for xc in (BARS[0][1], BARS[1][1]):
            d.line((xc, y, xc, y + 26), fill=FILL, width=3)
        d.text(((BARS[0][1] + BARS[1][1]) // 2 - 6, y - 22), "*", fill=FILL)
    im.save(path)
    return path


def truth():
    return {
        # Inside the axis and above the baseline. Both are drawn in the bars'
        # own colour - a printed figure draws them in black and so does this one
        # - so a box that included either would hand the reader one run of ink
        # spanning the whole panel instead of two bars.
        "panel_box": [AXIS_X + 3, WIDTH - 30, TOP_Y, BASELINE_Y - 2],
        "ticks": [[100.0, y_of(100.0)], [0.0, y_of(0.0)]],
        "colour": FILL,
        "bars": [{"series": sid, "x": xc, "mean": mean, "dispersion": disp}
                 for sid, xc, mean, disp in BARS],
    }


def main():
    plain = draw(os.path.join(HERE, "whisker_fixture.png"))
    bracket = draw(os.path.join(HERE, "whisker_bracket_fixture.png"), bracket=True)
    grey = draw(os.path.join(HERE, "whisker_grey_fixture.png"), whisker=WHISKER_GREY)
    pale = draw(os.path.join(HERE, "whisker_pale_cap_fixture.png"),
                cap_ink=PALE_CAP)
    holed = draw(os.path.join(HERE, "whisker_broken_fixture.png"),
                 hole=STEM_HOLE)
    path = os.path.join(HERE, "whisker_fixture_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(truth(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    for p in (plain, bracket, grey, pale, holed, path):
        print(os.path.basename(p))


if __name__ == "__main__":
    main()
