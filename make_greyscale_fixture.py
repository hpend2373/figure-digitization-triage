"""Draw the three-grey group panel that a greyscale print actually produces.

    python3 make_greyscale_fixture.py

    greyscale_group_fixture.jpeg  three bars in the three greys a journal uses
                                  for three groups - #000000, #b2b2b2, #666666 -
                                  rendered the way a page is rendered: an
                                  ANTIALIASING RAMP at every edge and then JPEG,
                                  which is what the figure inside a publisher's
                                  PDF is. Plus a significance bracket over the
                                  row, because that is where the ringing is
                                  worst.

WHY THIS IS A TRAP AND THE EARLIER FIXTURES ARE NOT.

`bar_fixture.png` and `whisker_fixture.png` are drawn with hard edges: a pixel is
the bar's colour or it is white, and a colour mask over them is exactly the bars.
No printed figure is like that. A rasteriser lays a ramp of intermediate greys
along every edge, and the JPEG in the PDF smooths it further.

The middle grey of a three-group palette sits ON that ramp. #666666 is 102, and
the ramp from #000000 to white and the ramp from #b2b2b2 to white both pass
through 102 - so a mask for the third group also marks:

    the left and right edges of the other two groups' bars,
    the row where the baseline rule fades into the paper,
    the descenders of the significance bracket.

Every one of those stands at the baseline, so "a bar grows from the baseline"
accepts them, and the fragment-merge rule then joins them into one run three
times the width of a bar. On publication 177 that returned 656 pg/ml against a
printed 380 for one cell and 100 against 24 for another, with no refusal.

THE JPEG IS NOT DECORATION. A hard edge on a white page rings, and the ringing
lands at every intermediate grey - including the middle of the palette, in the
paper ABOVE the bars where nothing is drawn at all. Those specks have no bar
under them and are still marked, and the baseline's own fade marks every column
of the panel, so each speck has something near the axis in its column to make it
look anchored. Written as a PNG this figure has clean edges and none of it
happens; the trap comes from the file format the source is actually in, not from
a constant chosen to produce it. Quality 80 is the comfortable end of what a
publisher embeds, so the trap is there in a GOOD scan.

WHAT SEPARATES THEM, MEASURED ON THIS FIXTURE AND ON 177: a bar is a SOLID BLOCK
OF INK JOINED TO THE BASELINE. The smear is not joined to anything - it is dust
along somebody else's edge - and the baseline's own fade is joined but never
rises above the rule. Neither statement is about a publication or a colour.

The truth file carries the values the drawing was made from.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 620, 520
AXIS_X, BASELINE_Y, TOP_Y = 90, 460, 60
Y_MAX = 100.0
BAR_W = 100
STEM_W, CAP_W = 4, 34
#: The axis and baseline rule, in pixels. A 600 dpi render of a journal page
#: draws them this thick, and the thickness matters: the rule's own fade into
#: the paper is several rows deep, and the middle grey of the palette is one of
#: the greys it fades through. Publication 177 carries that fade in the third
#: group's mask, as runs 8 to 132 pixels wide lying flat on the baseline.
RULE_W = 7
#: The bar outline, as `make_bar_fixture.py` draws it - but in a grey that is
#: none of the three series and 88 apart from the nearest of them, not the black
#: a journal often uses. A black outline would put the FIRST series' exact
#: colour around the other two bars and along every baseline, which is a real
#: figure and a different problem - furniture drawn in a series' own ink - and
#: tangling it in here would leave this fixture testing two things at once.
OUTLINE_W, OUTLINE_HEX = 3, "#333333"

#: (Series_ID, hex, x centre, mean, dispersion). The three greys are the ones
#: publication 177 prints, sampled off its raster.
#: The three bars TOUCH, which is how a grouped panel is drawn and how
#: publication 177 draws it - 5 pixels of paper between bars 180 wide. Bars with
#: room between them would leave each smear on its own, and the fragment-merge
#: rule - which exists to put back together a bar its own zero line split - is
#: the thing that turns adjacent smears into one run three bars wide.
BARS = [
    ("S_BLACK", "#000000", 175, 30.0, 6.0),
    ("S_LIGHT", "#b2b2b2", 277, 55.0, 9.0),
    ("S_MID", "#666666", 379, 42.0, 7.0),
]
MID = "S_MID"

#: Rendered at this multiple and averaged back down, after a blur at the large
#: scale. Box-averaging alone puts a ramp at only a few discrete levels and
#: whether one of them lands within a tolerance of 102 is an accident of the
#: factor; a rasteriser plus a JPEG give a CONTINUOUS ramp, and that is the thing
#: being reproduced. Neither number is a threshold anything is compared against.
SCALE, BLUR = 4, 4.0
#: What a publisher embeds. High rather than low on purpose: the trap has to be
#: there in a clean file, not only in a bad one.
JPEG_QUALITY = 80

#: The legend keys, inside the plot area and clear of every bar.
LEGEND_X, LEGEND_Y, LEGEND_W, LEGEND_H = 500, 90, 34, 20


def y_of(value):
    return BASELINE_Y - (value / Y_MAX) * (BASELINE_Y - TOP_Y)


def draw(path):
    s = SCALE
    im = Image.new("RGB", (WIDTH * s, HEIGHT * s), "white")
    d = ImageDraw.Draw(im)
    d.line((AXIS_X * s, TOP_Y * s, AXIS_X * s, BASELINE_Y * s), fill="black",
           width=RULE_W * s)
    d.line((AXIS_X * s, BASELINE_Y * s, (WIDTH - 30) * s, BASELINE_Y * s),
           fill="black", width=RULE_W * s)
    for v in (0, 25, 50, 75, 100):
        y = y_of(v) * s
        d.line((AXIS_X * s - 16 * s, y, AXIS_X * s, y), fill="black", width=3 * s)
    for _sid, hexv, xc, mean, disp in BARS:
        top = y_of(mean) * s
        # STROKED, like a vector bar in a journal and like `bar_fixture.png`:
        # the data coordinate is the middle of the outline, which is what the
        # reader reports as OUTLINE_CENTER. An unstroked rectangle has no middle
        # to find and every mean comes back a pixel or two low - a property of
        # the drawing, which a fixture must not make the reader wear.
        d.rectangle(((xc - BAR_W // 2) * s, top, (xc + BAR_W // 2) * s,
                     BASELINE_Y * s), fill=hexv, outline=OUTLINE_HEX,
                    width=OUTLINE_W * s)
        # PIL draws the outline INSIDE the rectangle, so the top edge is redrawn
        # centred on the data row - the same correction `make_bar_fixture.py`
        # makes, and the reason OUTLINE_CENTER can be checked against a number.
        d.line(((xc - BAR_W // 2) * s, top, (xc + BAR_W // 2) * s, top),
               fill=OUTLINE_HEX, width=OUTLINE_W * s)
        cap = y_of(mean + disp) * s
        # The error bars are BLACK on all three groups, which is how a journal
        # draws them and what keeps this fixture about one thing: the whisker in
        # the bar's own colour is already `whisker_fixture.png`.
        d.line((xc * s, cap, xc * s, top), fill="#000000", width=STEM_W * s)
        d.line(((xc - CAP_W // 2) * s, cap, (xc + CAP_W // 2) * s, cap),
               fill="#000000", width=3 * s)
    # The significance bracket, drawn as a journal draws it: one rule over the
    # whole row with a descender onto each bar it spans. Its descenders cross
    # the bars' columns, which is how a bracket got read as a bar top.
    y = y_of(88.0) * s
    d.line((BARS[0][2] * s, y, BARS[2][2] * s, y), fill="black", width=3 * s)
    for _sid, _hexv, xc, _m, _dd in BARS:
        d.line((xc * s, y, xc * s, y + 26 * s), fill="black", width=3 * s)
    d.text(((BARS[0][2] + BARS[2][2]) // 2 * s, y - 30 * s), "*", fill="black")
    # THE LEGEND, INSIDE THE AXES, where a journal puts it. Each key is a solid
    # block of a series' EXACT colour standing in white space with no bar under
    # it - the plainest case of "ink of this colour that is not a bar" a figure
    # contains, and not a rasterising artefact at all. It is separated from the
    # baseline by the whole panel, and separated from nothing at all if the only
    # question asked is whether the colour appears somewhere near the axis in
    # this column, which it does: the rule's own fade is in every column.
    for i, (_sid, hexv, _xc, _m, _dd) in enumerate(BARS):
        top = (LEGEND_Y + i * (LEGEND_H + 10)) * s
        d.rectangle((LEGEND_X * s, top, (LEGEND_X + LEGEND_W) * s,
                     top + LEGEND_H * s), fill=hexv)
    im = im.filter(ImageFilter.GaussianBlur(BLUR))
    im = im.resize((WIDTH, HEIGHT), Image.BOX)
    im.save(path, quality=JPEG_QUALITY)
    return path


def truth():
    return {
        # The box's bottom edge IS the baseline row, which is how publication
        # 177's panels are declared: the rule's core is excluded and the rows
        # where it fades into the paper are inside, because that is where a bar
        # ends and there is no way to have one without the other.
        "panel_box": [AXIS_X + 3, WIDTH - 30, TOP_Y, BASELINE_Y],
        "ticks": [[100.0, y_of(100.0)], [0.0, y_of(0.0)]],
        "bars": [{"series": sid, "colour": hexv, "x": xc, "mean": mean,
                  "dispersion": disp}
                 for sid, hexv, xc, mean, disp in BARS],
    }


def main():
    png = draw(os.path.join(HERE, "greyscale_group_fixture.jpeg"))
    path = os.path.join(HERE, "greyscale_group_fixture_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(truth(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    for p in (png, path):
        print(os.path.basename(p))


if __name__ == "__main__":
    main()
