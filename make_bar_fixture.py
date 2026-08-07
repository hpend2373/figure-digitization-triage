"""Synthesize a bar-chart fixture whose true values are known exactly.

The chart deliberately reproduces the two traps found on real figures:
  - bars carry a thick stroke, so the colour fill stops inside the true top
  - significance glyphs and a comparison bracket sit directly above the bars,
    at the same distance an error-bar cap would be, in the same colour
"""
import json
import numpy as np
from PIL import Image, ImageDraw

OUTLINE_W = 4
Y0_PX, YTOP_PX = 520, 80          # pixel rows of value 0 and value YTOP
YTOP = 150.0
X0, X1 = 120, 900

TRUTH = [   # (session, supine_mean, supine_sd, orthostasis_mean, orthostasis_sd)
    ("B-1",  124.0, 3.0, 117.0, 4.5),
    ("DI7",  127.0, 3.0, 112.0, 4.5),
    ("DI14", 118.0, 4.0,  97.0, 5.0),
    ("DI19", 121.0, 3.0, 107.0, 4.0),
    ("R1",   114.0, 3.0, 105.0, 4.5),
    ("R5",   121.0, 3.0, 117.0, 3.5),
]
TICKS = [(0, Y0_PX), (30, None), (60, None), (90, None), (120, None), (150, YTOP_PX)]


def v2y(v):
    return Y0_PX + (YTOP_PX - Y0_PX) * (v / YTOP)


def build(path="bar_fixture.png", meta_path="bar_fixture_truth.json",
          with_glyphs=True):
    W, H = 1000, 620
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    ticks = []
    for v in (0, 30, 60, 90, 120, 150):
        y = int(round(v2y(v)))
        d.line([X0 - 18, y, X0 - 4, y], fill=(0, 0, 0), width=3)   # tick mark
        d.line([X0 - 60, y - 1, X0 - 26, y + 1], fill=(0, 0, 0), width=6)  # label block
        ticks.append((v, y))
    d.line([X0, YTOP_PX - 20, X0, Y0_PX], fill=(0, 0, 0), width=4)
    d.line([X0, Y0_PX, X1, Y0_PX], fill=(0, 0, 0), width=4)

    slot = (X1 - X0 - 40) / len(TRUTH)
    bw = int(slot * 0.34)
    bars = []
    for i, (sess, sm, ssd, om, osd) in enumerate(TRUTH):
        base = X0 + 30 + slot * i
        for j, (name, mean, sd, fill) in enumerate(
                (("SUPINE", sm, ssd, (70, 70, 220)), ("ORTHOSTASIS", om, osd, (220, 40, 40)))):
            xl = int(base + j * (bw + 6))
            xr = xl + bw
            yt = v2y(mean)
            d.rectangle([xl, yt, xr, Y0_PX], fill=fill,
                        outline=(0, 0, 0), width=OUTLINE_W)
            # Real vector figures centre the stroke on the path, so the bar's
            # data coordinate sits in the MIDDLE of the outline. PIL draws the
            # outline inside the rect, so redraw the top edge centred on yt.
            d.line([xl, yt, xr, yt], fill=(0, 0, 0), width=OUTLINE_W)
            xc = (xl + xr) // 2
            ycap = v2y(mean + sd)
            d.line([xc, ycap, xc, yt], fill=(0, 0, 0), width=3)          # stem
            d.line([xc - bw // 3, ycap, xc + bw // 3, ycap],
                   fill=(0, 0, 0), width=3)                              # cap
            if with_glyphs:
                # a significance glyph floating above the cap - no stem to the bar
                d.line([xc - 6, ycap - 26, xc + 6, ycap - 26], fill=(0, 0, 0), width=4)
                d.line([xc - 6, ycap - 32, xc + 6, ycap - 32], fill=(0, 0, 0), width=4)
            bars.append(dict(session=sess, series=name, order=i,
                             true_mean=mean, true_sd=sd))
        if with_glyphs:
            # a comparison bracket spanning the pair, well above both caps
            ytop = min(v2y(sm + ssd), v2y(om + osd)) - 46
            xa = int(base + bw / 2)
            xb = int(base + bw + 6 + bw / 2)
            d.line([xa, ytop, xb, ytop], fill=(0, 0, 0), width=4)
            d.line([xa, ytop, xa, ytop + 12], fill=(0, 0, 0), width=4)
            d.line([xb, ytop, xb, ytop + 12], fill=(0, 0, 0), width=4)

    im.save(path)
    json.dump(dict(ticks=ticks, bars=bars, outline_w=OUTLINE_W,
                   panel_box=[X0 - 10, X1 + 10, YTOP_PX - 60, Y0_PX + 10]),
              open(meta_path, "w"), indent=1)
    return path, meta_path


# Bars on BOTH sides of zero. Every |mean| is kept above the stroke width: a bar
# thinner than its own outline has no colour fill at all, which is a separate
# limit covered by its own scenario.
SIGNED_TRUTH = [
    ("B-1",   -7.5, 2.2,   3.5, 3.2),
    ("DI7",  -12.0, 2.5,  -4.0, 2.7),
    ("DI14", -17.5, 2.4,  -7.0, 3.1),
    ("DI19", -11.5, 2.6,   5.2, 2.4),
    ("R1",    -8.2, 2.3,   2.8, 2.6),
    ("R5",    -2.5, 2.4,   6.0, 2.1),
]
# A bar whose value is a fraction of the stroke width: its fill is entirely
# covered by its own outline, so a colour mask cannot see it.
VANISHING_TRUTH = [("B-1", -7.5, 2.2, 0.2, 2.0)]


def build_signed(path="bar_fixture_signed.png", meta_path="bar_fixture_signed_truth.json",
                 truth=None):
    """Zero line inside the panel; bars hang below it and rise above it.

    The reader must decide direction per BAR, not per panel: DAP-style panels
    carry both. Error bars point away from zero on whichever side the bar is.
    """
    lo, hi = -25.0, 10.0
    ytop, ybot = 80, 520
    def v2y(v):
        return ybot + (ytop - ybot) * ((v - lo) / (hi - lo))
    W, H = 1000, 620
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    ticks = []
    for v in (-25, -20, -15, -10, -5, 0, 5, 10):
        y = int(round(v2y(v)))
        d.line([X0 - 18, y, X0 - 4, y], fill=(0, 0, 0), width=3)
        d.line([X0 - 60, y - 1, X0 - 26, y + 1], fill=(0, 0, 0), width=6)
        ticks.append((v, y))
    d.line([X0, ytop - 20, X0, ybot + 20], fill=(0, 0, 0), width=4)
    zero = v2y(0.0)
    d.line([X0, zero, X1, zero], fill=(0, 0, 0), width=4)

    truth = truth or SIGNED_TRUTH
    slot = (X1 - X0 - 40) / len(truth)
    bw = int(slot * 0.34)
    bars = []
    for i, (sess, am, asd, bm, bsd) in enumerate(truth):
        base = X0 + 30 + slot * i
        for j, (name, mean, sd, fill) in enumerate(
                (("SUPINE", am, asd, (70, 70, 220)), ("ORTHOSTASIS", bm, bsd, (220, 40, 40)))):
            xl = int(base + j * (bw + 6))
            xr = xl + bw
            yv = v2y(mean)
            d.rectangle([xl, min(yv, zero), xr, max(yv, zero)], fill=fill,
                        outline=(0, 0, 0), width=OUTLINE_W)
            d.line([xl, yv, xr, yv], fill=(0, 0, 0), width=OUTLINE_W)
            xc = (xl + xr) // 2
            away = mean - sd if mean < 0 else mean + sd     # error bar points away from zero
            ycap = v2y(away)
            d.line([xc, ycap, xc, yv], fill=(0, 0, 0), width=3)
            d.line([xc - bw // 3, ycap, xc + bw // 3, ycap], fill=(0, 0, 0), width=3)
            # a significance glyph further out, unattached
            off = 26 if mean < 0 else -26
            d.line([xc - 6, ycap + off, xc + 6, ycap + off], fill=(0, 0, 0), width=4)
            bars.append(dict(session=sess, series=name, order=i,
                             true_mean=mean, true_sd=sd,
                             direction="DOWN" if mean < 0 else "UP"))
    im.save(path)
    json.dump(dict(ticks=ticks, bars=bars, outline_w=OUTLINE_W,
                   panel_box=[X0 - 10, X1 + 10, ytop - 60, ybot + 40]),
              open(meta_path, "w"), indent=1)
    return path, meta_path


if __name__ == "__main__":
    print(build())
    print(build("bar_fixture_noglyph.png", "bar_fixture_noglyph_truth.json", with_glyphs=False))
    print(build_signed())
    print(build_signed("bar_fixture_vanishing.png", "bar_fixture_vanishing_truth.json",
                       truth=VANISHING_TRUTH))
