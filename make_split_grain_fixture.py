# -*- coding: utf-8 -*-
"""Seven monochrome scatters drawn to ask ONE question: is fill a panel-wide axis?

    python3 make_split_grain_fixture.py

    split_grain_imbalanced.jpeg     four classes at 12/8/6/4, all four real
    split_grain_confounded.jpeg     the global interior-ink gap falls between two
                                    SHAPES, not between two FILLS
    split_grain_outlier.jpeg        one fill class and three contaminated marks
    split_grain_one_fill.jpeg       one shape declared with a single fill
    split_grain_shape_blind.jpeg    the fill separates and the shape does not
    split_grain_tiny.jpeg           a 5 px marker
    split_grain_micro.jpeg          a 3 px marker
    split_grain_overlap.jpeg        markers of different series touching
    split_grain_truth.json

WHY A SECOND FIXTURE FAMILY. `twin_scatter_*.jpeg` draws four classes at 10/8/6/6
whose FILL marginal is 16 open and 14 filled - two halves of one panel, near
enough equal that no rule about a minimum class size is ever consulted. It
therefore cannot say anything about the case the corpus actually contains:
publication 464 Figure 2 resolves 31 marks whose fill marginal is 25 and 6, and
`marker_routing._split` declines the 25|6 cut because six of thirty-one is under
a quarter. Nothing in the repository exercised that rule, so nothing in the
repository could say whether the rule is right.

## What the measurement found, and what it did not

Interior ink is read in a window at the mark's centroid, and A HOLLOW TRIANGLE'S
WINDOW IS NOT A HOLLOW CIRCLE'S. A ring encloses white; a triangle inscribed in
the same box puts two of its own edges through the window. Measured on
`twin_scatter_s3.jpeg`, matched one-to-one against what was drawn:

    CIRCLE   OPEN     0.048 - 0.295
    TRIANGLE OPEN     0.333 - 0.510
    TRIANGLE FILLED   0.857 - 0.932
    CIRCLE   FILLED   1.000

FOUR BANDS, NOT TWO. The panel-wide fill split pools all four, so the "open"
cluster it computes a spread for is two clusters, and the separation index it
scores is depressed by a difference that has nothing to do with fill. That is a
measurement, and it is the whole reason this family exists.

It does NOT follow that the global cut is in the wrong place. On every rendering
of `twin_scatter` and on five renderings of 464 Figure 2 off its publisher PDF,
the largest gap is still the one between OPEN and FILLED, because the two open
bands are closer to each other than the open band is to the filled one. A grain
that is wrong in principle and right in every observed case is a grain whose
replacement has to be argued from a case where it is wrong - so
`split_grain_confounded.jpeg` is that case, drawn rather than hoped for.

## What each rendering is for

  imbalanced    12/8/6/4. The four classes are real and unequal, and the answer
                is that all of them route. A minimum-class rule that fires here
                is refusing a class the figure drew.
  confounded    open triangles printed with a heavy outline, so their interior
                ink rises to meet the filled marks, and fifteen open circles
                sitting near zero. The largest gap in the pooled distribution is
                then between the two OPEN classes. A panel-wide split takes it
                and calls every open triangle FILLED.
  outlier       ONE fill class was drawn. Three marks sit where a regression
                line crosses their middle, so their interior ink is high. A
                floor low enough to admit them invents a second class, and every
                one of those three is then a wrong value under a series name.
  one_fill      circles declared open AND filled, triangles declared filled
                only. The triangles' fill is a DECLARATION, not a measurement,
                and an identity method whose name says the ink decided may not
                be stamped on them.
  shape_blind   the fill separates cleanly and the shape does not. No mark may
                be routed: a fill without a shape names no class.
  tiny / micro  5 px and 3 px, where the evidence runs out. Fail-closed.
  overlap       markers of different series touching, so a blob holds two. The
                pair is refused and must not reach any split.

NOTHING HERE READS ANYTHING. This module draws and declares what it drew.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 780, 520
LEFT_X, RIGHT_X = 110, 660
TOP_Y, BASELINE_Y = 60, 450
X_LO, X_HI = 0.0, 12.0
LEFT_LO, LEFT_HI = 10.0, 35.0
RIGHT_LO, RIGHT_HI = 20.0, 90.0
X_TICKS = (0, 2, 4, 6, 8, 10, 12)
LEFT_TICKS = (10, 15, 20, 25, 30, 35)
RIGHT_TICKS = (20, 30, 40, 50, 60, 70, 80, 90)
RULE_W = 2
MARKER_D = 15
SUPERSAMPLE, JPEG_QUALITY = 4, 80
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

LEFT_TITLE = "Total Peripheral Resistance"
RIGHT_TITLE = "Splanchnic Vascular Resistance Index"
X_TITLE = "Central Venous Pressure (cm H2O)"

#: A marker's outline width, as a fraction of its diameter. The default is what
#: `make_twin_scatter_fixture` draws; `confounded` prints its open triangles at
#: a third of the marker, which is a line weight journals do use and which puts
#: the triangle's own edges through the fill window at its centroid.
STROKE = 1.0 / 8.0
HEAVY = 1.0 / 5.0


def x_of(value, s):
    return (LEFT_X + (value - X_LO) / (X_HI - X_LO) * (RIGHT_X - LEFT_X)) * s


def y_of(value, axis, s):
    lo, hi = (LEFT_LO, LEFT_HI) if axis == "LEFT" else (RIGHT_LO, RIGHT_HI)
    return (BASELINE_Y - (value - lo) / (hi - lo) * (BASELINE_Y - TOP_Y)) * s


def font(px):
    try:
        return ImageFont.truetype(MONO, px)
    except OSError as exc:                                        # pragma: no cover
        raise SystemExit(
            "%s is not on this machine and these fixtures print axis numerals "
            "and titles, which are the furniture a reader has to not read as "
            "data. Install DejaVu (Debian/Ubuntu: `apt-get install "
            "fonts-dejavu-core`). (%s)" % (MONO, exc))


def _wobble(i, phase):
    """A deterministic residual in [-1, 1]: no seed, no `random`, same every run."""
    return math.sin(2.399963 * i + phase) * math.cos(1.170107 * i + 0.5 * phase)


def _cloud(x_lo, x_hi, y_lo, y_hi, n, spread=0.0, phase=0.0):
    """`n` (x, y) pairs scattered about a line, so a regression through them is real.

    THE RESIDUALS ARE THE POINT, not decoration. A cloud drawn exactly on its own
    regression line is one connected component with that line: every marker
    touches it, `marker_scale` finds no near-square component to measure itself
    on, and the panel returns a scale of zero. Real data does not sit on its fit,
    and a fixture that does is testing a figure nobody printed. `spread` is in
    the axis' own units, and the x wobble is what keeps two neighbours from
    sharing a column.
    """
    if n == 1:
        return [(round(x_lo, 3), round(y_lo, 3))]
    out = []
    for i in range(n):
        t = i / float(n - 1)
        x = x_lo + (x_hi - x_lo) * t + 0.28 * (x_hi - x_lo) / n * _wobble(i, phase + 2.0)
        y = y_lo + (y_hi - y_lo) * t + spread * _wobble(i, phase)
        out.append((round(x, 3), round(y, 3)))
    return out


#: FOUR CLASSES, FOUR MARKS EACH, SPREAD ACROSS THE PANEL. The size cases are
#: drawn on this rather than on `imbalanced`, because thirty marks at a 5 px
#: marker touch each other and every refusal is then `MARKER_MERGED` - which is
#: fail-closed for the wrong reason. Sparse, the only thing that changes between
#: the three sizes is the size.
SPARSE_SERIES = [
    dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
         pairs=[(0.9, 31.5), (3.4, 28.0), (6.0, 30.2), (8.6, 26.5)]),
    dict(id="L_FILLED_CIRCLE", axis="LEFT", shape="CIRCLE", fill="FILLED",
         pairs=[(1.6, 21.0), (4.2, 18.5), (6.8, 20.4), (9.4, 16.2)]),
    dict(id="R_OPEN_TRIANGLE", axis="RIGHT", shape="TRIANGLE", fill="OPEN",
         pairs=[(2.4, 86.0), (5.0, 80.5), (7.6, 84.0), (10.2, 76.0)]),
    dict(id="R_FILLED_TRIANGLE", axis="RIGHT", shape="TRIANGLE", fill="FILLED",
         pairs=[(1.2, 64.0), (3.8, 58.5), (8.4, 62.0), (11.0, 54.0)]),
]

#: EVERY CASE, as a declaration and a drawing. `stroke` is a fraction of the
#: marker; `truth_fill` is what was DRAWN, which is what the suite scores
#: against, and `declared_fills` is what the panel's manifest says exists - the
#: two differ in `one_fill`, which is the whole point of that case.
CASES = {
    "imbalanced": dict(
        marker_d=MARKER_D, scale=2,
        what="four real classes at 12/8/6/4; every one of them routes",
        series=[
            dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
                 pairs=_cloud(0.8, 6.4, 31.0, 24.0, 12, 1.5, 0.0)),
            dict(id="L_FILLED_CIRCLE", axis="LEFT", shape="CIRCLE",
                 fill="FILLED", pairs=_cloud(7.0, 11.4, 21.0, 15.0, 8, 1.4, 1.3)),
            dict(id="R_OPEN_TRIANGLE", axis="RIGHT", shape="TRIANGLE",
                 fill="OPEN", pairs=_cloud(0.8, 5.4, 84.0, 72.0, 6, 4.5, 2.6)),
            dict(id="R_FILLED_TRIANGLE", axis="RIGHT", shape="TRIANGLE",
                 fill="FILLED", pairs=_cloud(7.2, 11.4, 62.0, 50.0, 4, 4.5, 3.9))]),
    "confounded": dict(
        marker_d=MARKER_D, scale=2,
        what="the largest gap in the pooled interior ink is between the two "
             "OPEN classes, so a panel-wide split calls the open triangles "
             "FILLED",
        series=[
            dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
                 pairs=_cloud(0.8, 11.4, 33.0, 23.0, 12, 1.6, 0.0)),
            dict(id="L_FILLED_CIRCLE", axis="LEFT", shape="CIRCLE",
                 fill="FILLED", pairs=_cloud(1.2, 5.6, 16.0, 11.5, 4, 1.3, 1.3)),
            dict(id="R_OPEN_TRIANGLE", axis="RIGHT", shape="TRIANGLE",
                 fill="OPEN", stroke=HEAVY,
                 pairs=_cloud(7.2, 11.4, 86.0, 74.0, 5, 4.5, 2.6)),
            dict(id="R_FILLED_TRIANGLE", axis="RIGHT", shape="TRIANGLE",
                 fill="FILLED", pairs=_cloud(0.8, 4.8, 68.0, 56.0, 4, 4.5, 3.9))]),
    "outlier": dict(
        marker_d=MARKER_D, scale=2, blot=2,
        what="ONE shape and one fill class were drawn; two marks are crossed by "
             "a rule and read high. A second class here is invented",
        series=[
            dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
                 pairs=_cloud(0.8, 11.4, 32.0, 15.0, 13, 2.2, 0.0))],
        # DECLARED AND NOT DRAWN. A manifest written from a caption that names
        # solid and open symbols, on a panel whose solid ones are in another
        # figure. The reader may not invent the class the caption promised.
        declared_extra=[
            dict(id="L_FILLED_CIRCLE", shape="CIRCLE", fill="FILLED",
                 axis="LEFT")]),
    "one_fill": dict(
        marker_d=MARKER_D, scale=2,
        what="circles are declared open and filled and both are drawn; "
             "triangles are declared FILLED only",
        series=[
            dict(id="L_OPEN_CIRCLE", axis="LEFT", shape="CIRCLE", fill="OPEN",
                 pairs=_cloud(0.8, 5.6, 32.0, 25.0, 8, 1.5, 0.0)),
            dict(id="L_FILLED_CIRCLE", axis="LEFT", shape="CIRCLE",
                 fill="FILLED", pairs=_cloud(6.6, 11.4, 22.0, 15.0, 8, 1.4, 1.3)),
            dict(id="R_FILLED_TRIANGLE", axis="RIGHT", shape="TRIANGLE",
                 fill="FILLED", pairs=_cloud(1.0, 11.0, 86.0, 60.0, 8, 4.5, 2.6))]),
    "shape_blind": dict(
        marker_d=7, scale=1, like="one_fill", no_lines=True,
        what="an 8 px marker: the FILL separates and the SHAPE does not, so "
             "every mark is refused even though half its class is established"),
    "tiny": dict(
        marker_d=5, scale=1, series=SPARSE_SERIES, no_lines=True,
        what="the sparse drawing at a 5 px marker"),
    "micro": dict(
        marker_d=4, scale=1, series=SPARSE_SERIES, no_lines=True,
        what="the sparse drawing at a 4 px marker"),
    "overlap": dict(
        marker_d=MARKER_D, scale=2, like="imbalanced", extra_overlap=True,
        what="the imbalanced drawing with a filled circle touching an open one"),
}


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
    return (sxy / sxx if sxx else 0.0), my - (sxy / sxx if sxx else 0.0) * mx


def pearson(pairs):
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def _spec(name):
    """A case, with `like` resolved to the series it borrows."""
    case = dict(CASES[name])
    if case.get("like"):
        case["series"] = CASES[case["like"]]["series"]
        case.setdefault("declared_extra", CASES[case["like"]].get("declared_extra", []))
    return case


def draw(path, name):
    case = _spec(name)
    scale, marker_d = case["scale"], case["marker_d"]
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
        d.text((LEFT_X * s - 12 * s, y), "%g" % v, font=nf, fill="black", anchor="rm")
    for v in RIGHT_TICKS:
        y = y_of(v, "RIGHT", s)
        d.line((RIGHT_X * s, y, RIGHT_X * s + 8 * s, y), fill="black", width=w)
        d.text((RIGHT_X * s + 12 * s, y), "%g" % v, font=nf, fill="black", anchor="lm")
    d.text(((LEFT_X + RIGHT_X) / 2.0 * s, (BASELINE_Y + 40) * s), X_TITLE,
           font=font(int(17 * s)), fill="black", anchor="ma")
    for title, x, rot in ((LEFT_TITLE, 26, 90), (RIGHT_TITLE, WIDTH - 26, 270)):
        tf = font(int(17 * s))
        tw = int(tf.getlength(title))
        strip = Image.new("RGB", (tw + 8 * s, int(24 * s)), "white")
        ImageDraw.Draw(strip).text((0, 0), title, font=tf, fill="black")
        strip = strip.rotate(rot, expand=True)
        im.paste(strip, (int(x * s - strip.width / 2.0),
                         int((TOP_Y + BASELINE_Y) / 2.0 * s - strip.height / 2.0)))
    drawn = []
    for spec in case["series"]:
        pairs = list(spec["pairs"])
        if case.get("extra_overlap") and spec["id"] == "L_FILLED_CIRCLE":
            first = case["series"][0]["pairs"][0]
            pairs = pairs + [(first[0] + (marker_d * 0.55) * (X_HI - X_LO)
                              / (RIGHT_X - LEFT_X), first[1])]
        if not case.get("no_lines"):
            # NO FIT LINE ON THE SIZE CASES. At a 5 px marker the line's stubs
            # put ink far enough from a blob's centroid that `off_centre_ink`
            # refuses it as a merged pair - which is fail-closed for the wrong
            # reason. These three renderings differ from each other in ONE
            # thing, the marker's size, or they are not a size experiment.
            slope, intercept = _fit(pairs)
            xs = [p[0] for p in pairs]
            d.line((x_of(min(xs), s), y_of(slope * min(xs) + intercept, spec["axis"], s),
                    x_of(max(xs), s), y_of(slope * max(xs) + intercept, spec["axis"], s)),
                   fill="black", width=max(1, int(1.5 * s)))
        stroke = max(1, int(round(marker_d * s * spec.get("stroke", STROKE))))
        for x, y in pairs:
            cx, cy = x_of(x, s), y_of(y, spec["axis"], s)
            _marker(d, cx, cy, spec["shape"], spec["fill"], marker_d * s, stroke)
            drawn.append(dict(series=spec["id"], axis=spec["axis"],
                              shape=spec["shape"], fill=spec["fill"],
                              x_value=x, y_value=y,
                              point_px_x=cx / float(SUPERSAMPLE),
                              point_px_y=cy / float(SUPERSAMPLE)))
    # THE CONTAMINATED MARKS OF THE `outlier` CASE. A short heavy rule through a
    # mark's middle, which is what a regression line does to a ring it crosses.
    # Drawn LAST so it lies over the marker, and recorded, so the suite scores
    # these three as the open marks they are rather than as a class.
    blotted = []
    if case.get("blot"):
        for point in drawn[:case["blot"]]:
            cx = point["point_px_x"] * SUPERSAMPLE
            cy = point["point_px_y"] * SUPERSAMPLE
            half = marker_d * s * 0.75
            d.line((cx - half, cy, cx + half, cy), fill="black",
                   width=max(2, int(round(marker_d * s * 0.32))))
            blotted.append([round(point["point_px_x"], 2),
                            round(point["point_px_y"], 2)])
    im = im.resize((WIDTH * scale, HEIGHT * scale), Image.LANCZOS)
    im.save(path, quality=JPEG_QUALITY)
    return drawn, blotted


def rendering(name):
    case = _spec(name)
    path = os.path.join(HERE, "split_grain_%s.jpeg" % name)
    drawn, blotted = draw(path, name)
    scale, marker_d = case["scale"], case["marker_d"]
    by_series = {}
    for spec in case["series"]:
        pts = [p for p in drawn if p["series"] == spec["id"]]
        by_series[spec["id"]] = dict(
            axis=spec["axis"], shape=spec["shape"], fill=spec["fill"],
            drawn=len(pts),
            pairs=[[p["x_value"], p["y_value"]] for p in pts],
            centres=[[round(p["point_px_x"], 2), round(p["point_px_y"], 2)]
                     for p in pts],
            pearson_r=round(pearson([(p["x_value"], p["y_value"])
                                     for p in pts]), 6))
    # THE DECLARATION IS NOT THE DRAWING. `outlier` declares two fills per shape
    # and draws one, which is what a manifest written from a caption looks like
    # when the figure's second class is not there.
    declared = [dict(Series_ID=s["id"], Marker_Shape=s["shape"],
                     Marker_Fill=s["fill"], Axis_ID=("Y_LEFT" if s["axis"] == "LEFT"
                                                    else "Y_RIGHT"))
                for s in case["series"]]
    for extra in case.get("declared_extra", ()):
        declared.append(dict(Series_ID=extra["id"], Marker_Shape=extra["shape"],
                             Marker_Fill=extra["fill"],
                             Axis_ID=("Y_LEFT" if extra["axis"] == "LEFT"
                                      else "Y_RIGHT")))
    return dict(
        file=os.path.basename(path), case=name, what=case["what"], scale=scale,
        marker_diameter_px=marker_d * scale,
        panel_box=[int((LEFT_X + 2) * scale), int(RIGHT_X * scale),
                   int(TOP_Y * scale), int((BASELINE_Y - 1) * scale)],
        x_ticks=[[v, round(x_of(v, scale), 2)] for v in (X_TICKS[0], X_TICKS[-1])],
        left_y_ticks=[[v, round(y_of(v, "LEFT", scale), 2)]
                      for v in (LEFT_TICKS[0], LEFT_TICKS[-1])],
        right_y_ticks=[[v, round(y_of(v, "RIGHT", scale), 2)]
                       for v in (RIGHT_TICKS[0], RIGHT_TICKS[-1])],
        declared=declared, series=by_series, contaminated=blotted,
        total_points=len(drawn))


def truth():
    return {
        "what_this_is":
            "Eight monochrome scatters drawn to test the GRAIN of the fill "
            "split rather than its threshold. Every marker's series, axis, "
            "shape, fill and centre is declared, and each case names the answer "
            "a correct reader reaches.",
        "why":
            "Interior ink is measured in a window at the mark's centroid, and a "
            "hollow triangle puts its own edges through that window while a "
            "ring encloses white. The panel-wide fill split therefore pools "
            "four bands and scores the spread of two of them as one cluster's. "
            "`confounded` is the case where that costs a wrong answer rather "
            "than a weaker index.",
        "renderings": {name: rendering(name) for name in sorted(CASES)},
    }


def main():
    doc = truth()
    path = os.path.join(HERE, "split_grain_truth.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    for name in sorted(doc["renderings"]):
        print(doc["renderings"][name]["file"])
    print(os.path.basename(path))


if __name__ == "__main__":
    main()
