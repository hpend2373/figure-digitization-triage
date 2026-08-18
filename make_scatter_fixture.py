"""Draw one scatter panel TWICE, at two resolutions, with its statistics on it.

    python3 make_scatter_fixture.py

    scatter_fixture_small.jpeg   the same panel at two scales, three times
    scatter_fixture_large.jpeg   apart, which is the range between a screenshot
                                 and a 600 dpi render of one journal page.
    scatter_fixture_line.jpeg    with a fitted regression line through the cloud
    scatter_fixture_open.jpeg    with the markers drawn as rings
    scatter_fixture_triangle.jpeg  and as open triangles, whose interiors are a
                                 third of the marker rather than three quarters
    scatter_fixture_overlap.jpeg two more pairs, 22 and 10 pixels from their
                                 neighbours against a marker 33 across

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

WHAT THE FOUR VARIANTS ARE FOR is written beside `VARIANTS` below: each is one
thing a printed scatter has that a synthetic one does not, and each defeats the
reading of ink by its OUTLINE. Publication 177 Figure 4 has all of them on one
row of three panels.
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
ANN_X, ANN_Y = 110, 75

#: The two renderings. Not dpi numbers - a factor, which is what changes.
SCALES = {"small": 1, "large": 3}

#: THREE MORE PANELS, each drawn from the same pairs at the larger scale and
#: each holding one thing a printed scatter has that a synthetic one does not.
#:
#:  line     a fitted regression line THROUGH the cloud. It touches every marker
#:           it passes, so the outline of the ink is one contour: publication
#:           177 panel A is a single blob 308 by 279 pixels at 600 dpi and 154
#:           by 141 at 300, which is the same blob and not a resolution to turn
#:           up. Read as contours it is one mark, or none.
#:  open     the markers are RINGS, which is how a journal draws a second or
#:           third group. A ring has no thick middle, so the primitive that
#:           finds a filled circle finds nothing at all on it.
#:  overlap  two markers close enough to touch. Their outlines are one contour
#:           and their centroid is a point at neither of them: 177 panel C
#:           declares 24 and the outline reader found 41, two of those blobs
#:           104 by 195 and 68 by 96 pixels.
#:
#: One pair is added for the overlap panel, 22 pixels from its neighbour at
#: that scale against a marker 33 across - two markers a person plainly sees
#: as two, whose outlines are one contour.
VARIANTS = {"line": dict(fitted_line=True),
            "open": dict(open_markers=True),
            # TWO extra pairs. The first is 22 pixels from its neighbour, which
            # is two markers a person plainly sees as two. The second is TEN,
            # which is the separation publication 177 panel A prints between the
            # two marks a suppression radius of 0.8 of a marker swallowed - and
            # panel C has three more at 5 to 8. Without a pair that close
            # nothing in the suite can tell a radius of 0.45 from one of 0.80,
            # and the fixtures read every drawn pair at either.
            "overlap": dict(extra=[(1.70, 24.6), (1.88, 32.833)]),
            # AN OPEN TRIANGLE, which is what publication 177 panel B is drawn
            # with. It matters separately from the ring because a triangle
            # encloses far less of its own bounding box: 177's measure 12 across
            # against a marker of 32, where a ring's interior is 0.72 of its
            # marker. Held to the MARKER's size window they are all rejected and
            # the panel reads one mark in twelve.
            "triangle": dict(open_markers=True, triangle=True)}
VARIANT_SCALE = 3
SUPERSAMPLE, BLUR, JPEG_QUALITY = 4, 4.0, 80


def x_of(value, s):
    return (AXIS_X + (value / X_MAX) * (RIGHT_X - AXIS_X)) * s


def y_of(value, s):
    return (BASELINE_Y - (value / Y_MAX) * (BASELINE_Y - TOP_Y)) * s


def draw(path, scale, open_markers=False, fitted_line=False, extra=(),
         triangle=False):
    s = scale * SUPERSAMPLE
    pairs = list(PAIRS) + list(extra)
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
    if fitted_line:
        # Least squares through the pairs, drawn from the first x to the last,
        # in the same ink as the markers - which is what makes it one contour
        # with every marker it crosses.
        n = len(pairs)
        mx = sum(p[0] for p in pairs) / n
        my = sum(p[1] for p in pairs) / n
        b = (sum((p[0] - mx) * (p[1] - my) for p in pairs)
             / sum((p[0] - mx) ** 2 for p in pairs))
        xa, xb = min(p[0] for p in pairs), max(p[0] for p in pairs)
        d.line((x_of(xa, s), y_of(my + b * (xa - mx), s),
                x_of(xb, s), y_of(my + b * (xb - mx), s)),
               fill="black", width=RULE_W * s)
    r = MARKER_D * s / 2.0
    for xv, yv in pairs:
        cx, cy = x_of(xv, s), y_of(yv, s)
        if triangle:
            # A BOLD outline, because a printed one is: publication 177 panel B
            # leaves an interior 0.375 of its marker and this stroke leaves
            # 0.38. A hairline triangle encloses two thirds of its own box and
            # would not be the case that matters.
            pts = [(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r), (cx, cy - r)]
            d.line(pts, fill="black", width=max(1, int(round(0.55 * r))),
                   joint="curve")
        elif open_markers:
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="black",
                      width=max(1, int(round(0.28 * r))))
        else:
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
    return [int((ANN_X - pad) * scale), int((ANN_X + 150) * scale),
            int((ANN_Y - pad) * scale),
            int((ANN_Y + 34 * (len(ANNOTATION) - 1) + 34 + pad) * scale)]


def truth():
    out = {"pairs": [[x, y] for x, y in PAIRS], "marker": "CIRCLE",
           "renderings": {}}
    every = dict(SCALES, **{n: VARIANT_SCALE for n in VARIANTS})
    for name, scale in every.items():
        out["renderings"][name] = {
            "file": "scatter_fixture_%s.jpeg" % name,
            "scale": scale,
            "pairs": [[x, y] for x, y in
                      list(PAIRS) + list(VARIANTS.get(name, {}).get("extra", ()))],
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
    paths += [draw(os.path.join(HERE, "scatter_fixture_%s.jpeg" % name),
                   VARIANT_SCALE, **kw) for name, kw in sorted(VARIANTS.items())]
    path = os.path.join(HERE, "scatter_fixture_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(truth(), fh, indent=1, sort_keys=True)
        fh.write("\n")
    for p in paths + [path]:
        print(os.path.basename(p))


if __name__ == "__main__":
    main()
