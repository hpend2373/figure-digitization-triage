"""Draw one scatter panel TWICE, at two resolutions, with its statistics on it.

    python3 make_scatter_fixture.py

    scatter_fixture_small.jpeg   the same panel at two scales, 2.5x apart, which
    scatter_fixture_large.jpeg   is the range between a 150 dpi screenshot and a
                                 600 dpi render of the same journal page.

WHY TWO SIZES. `read_scatter_panel` decided what a marker is with four absolute
numbers - area between 12 and 500 square pixels, bounding box under 35 across
and over 3 - and a marker is not a number of pixels. It is a mark a plotting
program drew at one setting, and how many pixels that is depends entirely on how
the page was rendered. On publication 177 Figure 4 at 600 dpi the markers are 28
to 36 pixels across and 600 square, so the area ceiling rejected EVERY data point
in the panel; what came back instead was the printed annotation. The same figure
at 300 dpi has markers half that size and the same reader behaves differently on
it. A fixture at one size cannot show that, and one at two sizes cannot hide it.

WHY THE ANNOTATION IS ON THE PANEL. A journal prints `r` and `P` inside the
axes, and at any resolution the glyphs are marker-sized: on 177 Figure 4 they
are 28x44 and 32x48 against markers of 28x28. There is no measurement that tells
a letter from a marker - `0` IS a small circle - so this is not something a
reader can be made cleverer about. It is something the panel has to declare, the
way it already declares where its axes are.

    Panel A of 177 Figure 4 reads r = -0.47 against a printed 0.91, and all four
    of the "data points" it found are letters of "r = 0.91" and "P < 0.001".

The truth file carries the pairs the drawing was made from, and the annotation
rectangle at both scales, so a scenario compares against what was drawn.

No fitted line is drawn here. A regression line through the cloud welds every
marker into one contour, which is a different rule needing a different fixture.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 620, 520
AXIS_X, BASELINE_Y, TOP_Y, RIGHT_X = 90, 460, 60, 590
X_MAX, Y_MAX = 3.0, 80.0
RULE_W = 3
MARKER_D = 11                       # marker diameter at scale 1

#: (x, y) in data units. Twelve pairs with a real correlation, spread over the
#: panel so no two markers touch at either scale - overlapping markers are a
#: separate rule with a separate fixture.
PAIRS = [
    (0.42, 9.0), (0.61, 14.5), (0.83, 12.0), (1.05, 21.0),
    (1.24, 18.5), (1.47, 27.0), (1.66, 24.0), (1.88, 33.5),
    (2.10, 31.0), (2.31, 40.0), (2.55, 44.5), (2.76, 52.0),
]

#: The annotation a journal puts inside the axes, and where it puts it.
ANNOTATION = ("r = 0.98", "P < 0.001")
ANN_X, ANN_Y = 330, 120

#: The two renderings. Not dpi numbers - a factor, which is what changes.
SCALES = {"small": 1, "large": 3}
SUPERSAMPLE, BLUR, JPEG_QUALITY = 4, 4.0, 80


def x_of(value, s):
    return (AXIS_X + (value / X_MAX) * (RIGHT_X - AXIS_X)) * s


def y_of(value, s):
    return (BASELINE_Y - (value / Y_MAX) * (BASELINE_Y - TOP_Y)) * s


def draw(path, scale):
    s = scale * SUPERSAMPLE
    im = Image.new("RGB", (WIDTH * scale * SUPERSAMPLE,
                           HEIGHT * scale * SUPERSAMPLE), "white")
    d = ImageDraw.Draw(im)
    d.line((AXIS_X * s, TOP_Y * s, AXIS_X * s, BASELINE_Y * s), fill="black",
           width=RULE_W * s)
    d.line((AXIS_X * s, BASELINE_Y * s, RIGHT_X * s, BASELINE_Y * s),
           fill="black", width=RULE_W * s)
    for v in (0, 1, 2, 3):
        d.line((x_of(v, s), BASELINE_Y * s, x_of(v, s), BASELINE_Y * s + 14 * s),
               fill="black", width=RULE_W * s)
    for v in (0, 20, 40, 60, 80):
        d.line((AXIS_X * s - 14 * s, y_of(v, s), AXIS_X * s, y_of(v, s)),
               fill="black", width=RULE_W * s)
    r = MARKER_D * s / 2.0
    for xv, yv in PAIRS:
        cx, cy = x_of(xv, s), y_of(yv, s)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="black")
    # The statistics, inside the axes, in a type size a journal uses.
    try:
        from PIL import ImageFont
        font = ImageFont.load_default(size=26 * s)
    except Exception:                                   # pragma: no cover
        font = None
    for i, text in enumerate(ANNOTATION):
        d.text((ANN_X * s, (ANN_Y + i * 34) * s), text, fill="black", font=font)
    im = im.filter(ImageFilter.GaussianBlur(BLUR))
    im = im.resize((WIDTH * scale, HEIGHT * scale), Image.BOX)
    im.save(path, quality=JPEG_QUALITY)
    return path


def annotation_box(scale):
    """The rectangle the panel declares as annotation, in raster pixels.

    Generous by a marker's width on every side, which is how a person drawing it
    on the figure would draw it, and still clear of every pair above.
    """
    pad = MARKER_D
    return [int((ANN_X - pad) * scale), int((RIGHT_X - 2) * scale),
            int((ANN_Y - pad) * scale),
            int((ANN_Y + 34 * (len(ANNOTATION) - 1) + 34 + pad) * scale)]


def truth():
    out = {"pairs": [[x, y] for x, y in PAIRS], "marker": "CIRCLE",
           "renderings": {}}
    for name, scale in SCALES.items():
        out["renderings"][name] = {
            "file": "scatter_fixture_%s.jpeg" % name,
            "scale": scale,
            # Inside the axes and clear of the rules, the way a panel box is
            # declared everywhere else in this package.
            "panel_box": [int((AXIS_X + 3) * scale), int(RIGHT_X * scale),
                          int(TOP_Y * scale), int((BASELINE_Y - 2) * scale)],
            "x_ticks": [[v, x_of(v, scale)] for v in (0, 3)],
            "y_ticks": [[v, y_of(v, scale)] for v in (0, 80)],
            "annotation_box": annotation_box(scale),
        }
    return out


def main():
    paths = [draw(os.path.join(HERE, "scatter_fixture_%s.jpeg" % name), scale)
             for name, scale in sorted(SCALES.items())]
    path = os.path.join(HERE, "scatter_fixture_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(truth(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    for p in paths + [path]:
        print(os.path.basename(p))


if __name__ == "__main__":
    main()
