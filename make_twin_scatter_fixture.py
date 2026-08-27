# -*- coding: utf-8 -*-
"""Draw a TWIN-AXIS four-series monochrome scatter, the way a journal prints one.

    python3 make_twin_scatter_fixture.py

    twin_scatter_s1.jpeg      one drawing at three scales, so nothing in a
    twin_scatter_s2.jpeg      reader may depend on how the page was rendered
    twin_scatter_s3.jpeg
    twin_scatter_overlap.jpeg two markers of DIFFERENT series touching
    twin_scatter_tiny.jpeg    a marker 5 px across, where a ring's interior
                              still separates from a disc's - by a margin
    twin_scatter_micro.jpeg   3 px, where it does not: no threshold divides
                              open from filled, and the fill must be refused
    twin_scatter_truth.json

WHY THIS FIXTURE EXISTS. Publication 464 Figure 2 is a real one of these:
total peripheral resistance against central venous pressure as open and filled
CIRCLES on a left axis at 10-35, a splanchnic index as open and filled TRIANGLES
on a right axis at 20-90, one shared x, a dashed regression line through each
cloud. `read_scatter_panel` refuses it - more than one monochrome series needs
explicit marker routing - and that refusal is right: asked instead for ONE
monochrome series the same panel returns 247 marks, made of tick numerals, the
rotated right-hand axis title and the regression lines broken into fragments,
and reports r = 0.008 P = 0.90 where both clouds fall steeply.

The refusal is a `png/verify.py` scenario already. What has no fixture is the
CAPABILITY: four monochrome series told apart by marker shape and fill, and two
y calibrations over one panel. This is that fixture, and it is drawn rather than
borrowed so the answer is known:

    every marker's centre, series, axis, shape and fill
    the two y calibrations, which are DIFFERENT
    where the furniture is - numerals, titles, regression lines
    the association per series, computed from the pairs the drawing was made of

WHAT EACH RENDERING IS FOR

  s1 / s2 / s3   the same drawing three times over. A reader whose marker test
                 is a number of pixels passes one of these and fails the others,
                 which is the defect the single-axis scatter fixture was built
                 for and this one inherits.
  overlap        two markers of DIFFERENT SERIES touching. Their outlines are
                 one contour, and a reader that splits it by centroid puts a
                 point at neither of them and gives it to whichever series wins.
                 The right answer is to refuse that pair and keep the rest.
  tiny / micro   two steps down in marker size. At 5 px a ring's interior
                 still separates from a disc's; at 3 px the open triangles
                 reach a HIGHER interior ink ratio than the filled ones, so no
                 threshold divides them and the only correct answer for the
                 fill is to refuse it. This module declares only what it DREW -
                 the suite measures the ink itself, so the separation is an
                 independent statement about the drawing rather than a number
                 the generator wrote down about its own output.

NOTHING HERE READS ANYTHING. This module draws and declares; the reader that
will be held to it does not exist yet, and the scenarios that use it today
assert what the CURRENT one refuses.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 780, 520
LEFT_X, RIGHT_X = 110, 660
TOP_Y, BASELINE_Y = 60, 450
X_LO, X_HI = 2.0, 12.0
LEFT_LO, LEFT_HI = 10.0, 35.0
RIGHT_LO, RIGHT_HI = 20.0, 90.0
X_TICKS = (2, 4, 6, 8, 10, 12)
LEFT_TICKS = (10, 15, 20, 25, 30, 35)
RIGHT_TICKS = (20, 30, 40, 50, 60, 70, 80, 90)
RULE_W = 2
MARKER_D = 11
SUPERSAMPLE, BLUR, JPEG_QUALITY = 4, 4.0, 80
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

#: FOUR SERIES, and which axis each is plotted against. Shape and fill are the
#: only things that separate them - there is no colour - which is exactly the
#: case `read_scatter_panel` refuses today.
SERIES = (
    dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
         pairs=[(4.2, 21.8), (4.8, 20.5), (5.2, 19.4), (5.8, 18.6),
                (6.4, 18.2), (7.1, 17.6), (8.0, 17.2), (8.6, 16.9),
                (9.5, 16.4), (9.9, 16.2)]),
    dict(id="L_FILLED_CIRCLE", axis="LEFT", shape="CIRCLE", fill="FILLED",
         pairs=[(5.9, 19.2), (6.3, 18.3), (6.6, 18.5), (7.2, 16.5),
                (7.9, 17.4), (8.3, 17.1), (9.4, 16.1), (9.7, 16.6)]),
    dict(id="R_OPEN_TRIANGLE", axis="RIGHT", shape="TRIANGLE", fill="OPEN",
         pairs=[(3.2, 65.0), (3.8, 64.8), (4.6, 65.2), (5.9, 58.0),
                (6.1, 57.5), (8.1, 50.0)]),
    dict(id="R_FILLED_TRIANGLE", axis="RIGHT", shape="TRIANGLE", fill="FILLED",
         pairs=[(4.3, 79.5), (4.9, 74.8), (5.8, 71.0), (7.0, 63.5),
                (7.6, 61.0), (9.2, 46.0)]),
)

#: The right-hand axis title, printed up the side. On 464 this is where eight of
#: the shortcut's 247 "data points" came from.
LEFT_TITLE = "Total Peripheral Resistance"
RIGHT_TITLE = "Splanchnic Vascular Resistance Index"
X_TITLE = "Central Venous Pressure (cm H2O)"

SCALES = {"s1": 1, "s2": 2, "s3": 3}
VARIANT_SCALE = 3


def x_of(value, s):
    return (LEFT_X + (value - X_LO) / (X_HI - X_LO) * (RIGHT_X - LEFT_X)) * s


def y_of(value, axis, s):
    lo, hi = (LEFT_LO, LEFT_HI) if axis == "LEFT" else (RIGHT_LO, RIGHT_HI)
    return (BASELINE_Y - (value - lo) / (hi - lo) * (BASELINE_Y - TOP_Y)) * s


def font(px):
    try:
        return ImageFont.truetype(MONO, px)
    except OSError as exc:                                  # pragma: no cover
        raise SystemExit(
            "%s is not on this machine and this fixture prints axis numerals "
            "and titles, which are the furniture a reader has to not read as "
            "data. Install DejaVu (Debian/Ubuntu: `apt-get install "
            "fonts-dejavu-core`). (%s)" % (MONO, exc))


def _marker(d, cx, cy, shape, fill, diameter, stroke):
    r = diameter / 2.0
    if shape == "CIRCLE":
        box = [cx - r, cy - r, cx + r, cy + r]
        if fill == "FILLED":
            d.ellipse(box, fill="black")
        else:
            d.ellipse(box, outline="black", width=stroke)
    else:
        pts = [(cx, cy - r), (cx - r, cy + r * 0.8), (cx + r, cy + r * 0.8)]
        if fill == "FILLED":
            d.polygon(pts, fill="black")
        else:
            d.line(pts + [pts[0]], fill="black", width=stroke, joint="curve")


def _fit(pairs):
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    slope = sxy / sxx
    return slope, my - slope * mx


def pearson(pairs):
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    return sxy / math.sqrt(sxx * syy)


def draw(path, scale, marker_d=MARKER_D, extra_overlap=False):
    s = scale * SUPERSAMPLE
    im = Image.new("RGB", (WIDTH * scale * SUPERSAMPLE,
                           HEIGHT * scale * SUPERSAMPLE), "white")
    d = ImageDraw.Draw(im)
    w = max(1, RULE_W * s)
    d.line((LEFT_X * s, TOP_Y * s, LEFT_X * s, BASELINE_Y * s), fill="black", width=w)
    d.line((RIGHT_X * s, TOP_Y * s, RIGHT_X * s, BASELINE_Y * s), fill="black", width=w)
    d.line((LEFT_X * s, BASELINE_Y * s, RIGHT_X * s, BASELINE_Y * s),
           fill="black", width=w)
    nf = font(int(15 * s))
    for v in X_TICKS:
        d.line((x_of(v, s), BASELINE_Y * s, x_of(v, s), (BASELINE_Y + 8) * s),
               fill="black", width=w)
        d.text((x_of(v, s), (BASELINE_Y + 12) * s), "%g" % v, font=nf,
               fill="black", anchor="ma")
    for v in LEFT_TICKS:
        y = y_of(v, "LEFT", s)
        d.line((LEFT_X * s - 8 * s, y, LEFT_X * s, y), fill="black", width=w)
        d.text((LEFT_X * s - 12 * s, y), "%g" % v, font=nf, fill="black",
               anchor="rm")
    for v in RIGHT_TICKS:
        y = y_of(v, "RIGHT", s)
        d.line((RIGHT_X * s, y, RIGHT_X * s + 8 * s, y), fill="black", width=w)
        d.text((RIGHT_X * s + 12 * s, y), "%g" % v, font=nf, fill="black",
               anchor="lm")
    d.text(((LEFT_X + RIGHT_X) / 2.0 * s, (BASELINE_Y + 40) * s), X_TITLE,
           font=font(int(17 * s)), fill="black", anchor="ma")
    # THE TWO SIDE TITLES, PRINTED UP THE SIDE. Rotated text is furniture whose
    # letters are marker-sized at any scale.
    for title, x, rot in ((LEFT_TITLE, 26, 90), (RIGHT_TITLE, WIDTH - 26, 270)):
        tf = font(int(17 * s))
        tw = int(tf.getlength(title))
        strip = Image.new("RGB", (tw + 8 * s, int(24 * s)), "white")
        ImageDraw.Draw(strip).text((0, 0), title, font=tf, fill="black")
        strip = strip.rotate(rot, expand=True)
        im.paste(strip, (int(x * s - strip.width / 2.0),
                         int((TOP_Y + BASELINE_Y) / 2.0 * s - strip.height / 2.0)))
    stroke = max(1, int(round(marker_d * s / 8.0)))
    drawn = []
    for spec in SERIES:
        pairs = list(spec["pairs"])
        if extra_overlap and spec["id"] == "L_FILLED_CIRCLE":
            # TOUCHING A MARKER OF ANOTHER SERIES. Placed a marker's width from
            # L_OPEN_CIRCLE's first point, in data units at this scale.
            pairs = pairs + [(4.2 + (marker_d * 0.55) * (X_HI - X_LO)
                              / (RIGHT_X - LEFT_X), 21.8)]
        slope, intercept = _fit(pairs)
        xs = [p[0] for p in pairs]
        d.line((x_of(min(xs), s), y_of(slope * min(xs) + intercept, spec["axis"], s),
                x_of(max(xs), s), y_of(slope * max(xs) + intercept, spec["axis"], s)),
               fill="black", width=max(1, int(1.5 * s)))
        for x, y in pairs:
            cx, cy = x_of(x, s), y_of(y, spec["axis"], s)
            _marker(d, cx, cy, spec["shape"], spec["fill"], marker_d * s, stroke)
            drawn.append(dict(series=spec["id"], axis=spec["axis"],
                              shape=spec["shape"], fill=spec["fill"],
                              x_value=x, y_value=y,
                              point_px_x=cx / float(SUPERSAMPLE),
                              point_px_y=cy / float(SUPERSAMPLE)))
    im = im.filter(ImageFilter.GaussianBlur(BLUR)) if False else im
    im = im.resize((WIDTH * scale, HEIGHT * scale), Image.LANCZOS)
    im.save(path, quality=JPEG_QUALITY)
    return path, drawn


def rendering(name, scale, marker_d=MARKER_D, extra_overlap=False):
    path, drawn = draw(os.path.join(HERE, "twin_scatter_%s.jpeg" % name), scale,
                       marker_d=marker_d, extra_overlap=extra_overlap)
    by_series = {}
    for spec in SERIES:
        pts = [p for p in drawn if p["series"] == spec["id"]]
        by_series[spec["id"]] = dict(
            axis=spec["axis"], shape=spec["shape"], fill=spec["fill"],
            pairs=[[p["x_value"], p["y_value"]] for p in pts],
            centres=[[round(p["point_px_x"], 2), round(p["point_px_y"], 2)]
                     for p in pts],
            pearson_r=round(pearson([(p["x_value"], p["y_value"]) for p in pts]), 6))
    return dict(
        file=os.path.basename(path), scale=scale, marker_diameter_px=marker_d * scale,
        panel_box=[int((LEFT_X + 2) * scale), int(RIGHT_X * scale),
                   int(TOP_Y * scale), int((BASELINE_Y - 1) * scale)],
        x_ticks=[[v, round(x_of(v, scale), 2)] for v in (X_TICKS[0], X_TICKS[-1])],
        left_y_ticks=[[v, round(y_of(v, "LEFT", scale), 2)]
                      for v in (LEFT_TICKS[0], LEFT_TICKS[-1])],
        right_y_ticks=[[v, round(y_of(v, "RIGHT", scale), 2)]
                       for v in (RIGHT_TICKS[0], RIGHT_TICKS[-1])],
        series=by_series,
        total_points=len(drawn))


def truth():
    out = {
        "what_this_is":
            "A twin-axis four-series monochrome scatter, drawn so the answer is "
            "known. Publication 464 Figure 2 is a real one; this is the same "
            "shape with every marker's series, axis, shape, fill and centre "
            "declared, and the two y calibrations deliberately different.",
        "what_no_reader_does_yet":
            "Nothing in this package reads it. `read_scatter_panel` refuses "
            "more than one monochrome series, and there is no vocabulary for a "
            "second y axis. The scenarios that use this fixture today assert "
            "that refusal and measure the evidence a future reader would have "
            "to gate on; promoting 464 Figure 2 to a positive forward test "
            "comes after these renderings pass, not before.",
        "series_by_axis": {"LEFT": ["L_OPEN_CIRCLE", "L_FILLED_CIRCLE"],
                           "RIGHT": ["R_OPEN_TRIANGLE", "R_FILLED_TRIANGLE"]},
        "renderings": {},
    }
    for name, scale in sorted(SCALES.items()):
        out["renderings"][name] = rendering(name, scale)
    out["renderings"]["overlap"] = rendering("overlap", VARIANT_SCALE,
                                             extra_overlap=True)
    # WHERE THE EVIDENCE RUNS OUT, in two steps rather than one. At a marker 5
    # px across a ring's interior still separates from a disc's - by a margin,
    # which a reader may take. At 3 px it does not: the open triangles reach a
    # higher interior ink ratio than the filled ones, so no threshold divides
    # them and the only correct answer for the FILL is to refuse it. Both are
    # here because "small" is not the property; "the two classes overlap" is,
    # and only a measurement says which rendering has crossed it.
    out["renderings"]["tiny"] = rendering("tiny", 1, marker_d=5)
    out["renderings"]["micro"] = rendering("micro", 1, marker_d=3)
    return out


def main():
    doc = truth()
    path = os.path.join(HERE, "twin_scatter_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    for name in sorted(doc["renderings"]):
        print(doc["renderings"][name]["file"])
    print(os.path.basename(path))


if __name__ == "__main__":
    main()
