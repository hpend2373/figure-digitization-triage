"""Synthetic monochrome grouped-bar rasters with recorded truth.

    python3 make_mono_bar_fixture.py        # writes the fixtures next to this file

A black-and-white bar chart names its series by FILL PATTERN, and every trap the
colour reader hit is present here too, drawn deliberately:

* a significance glyph floating above the whisker, the same black, exactly where
  a cap sits - so a reader that takes the topmost dark pixel inflates the SD
* a stroked outline whose interior fill stops inside it - so a reader that takes
  the fill edge biases every mean in one direction
* one group whose two bars carry the same pattern, which no reader can separate
  and which must therefore produce nothing

The truth file records the values that were DRAWN, so a scenario compares the
reader against the figure's intent rather than against its own last output.
"""
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

WIDTH, HEIGHT = 760, 520
PANEL = (90, 720, 40, 430)
Y_TICKS = [(0, 420), (100, 60)]
GROUPS = ["T0", "T1", "T2", "T3"]
GROUP_X = [190, 330, 470, 610]
PATTERNS = ["SOLID", "HATCHED", "OPEN"]
BAR_W, GAP = 26, 6
STROKE = 3

TRUTH = {
    "SOLID":   [62.0, 68.0, 74.0, 58.0],
    "HATCHED": [48.0, 53.0, 57.0, 44.0],
    "OPEN":    [30.0, 34.0, 39.0, 27.0],
}
SD = {"SOLID": 6.0, "HATCHED": 5.0, "OPEN": 4.0}
#: Groups that carry a significance glyph above the whisker cap.
GLYPH_GROUPS = {"T1", "T2"}


def to_pixel(value):
    (v0, p0), (v1, p1) = Y_TICKS
    return p0 + (value - v0) * (p1 - p0) / (v1 - v0)


def _hatch(im, box):
    """Diagonal hatching, clipped to the bar interior.

    Drawn into a tile and pasted rather than stroked across the canvas: an
    unclipped diagonal ran the width of the figure, and every column of the
    panel then read as part of a bar. The fixture's own bug, but the reader
    could not have been right about a figure like that either.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = max(0, x1 - x0), max(0, y1 - y0)
    if w <= 0 or h <= 0:
        return
    tile = Image.new("RGB", (w, h), "white")
    td = ImageDraw.Draw(tile)
    # Spacing chosen so the interior density lands near the 0.26 measured on a
    # real hatched figure, not so dense that hatched is indistinguishable from
    # solid - a fixture that only tests the easy separation tests nothing.
    for offset in range(-h, w, 9):
        td.line((offset, h, offset + h, 0), fill="black", width=2)
    im.paste(tile, (x0, y0))


def draw(path, truth_path, collide_group=None, overrides=None):
    """collide_group: draw that group's bars with one shared pattern.

    overrides: {(pattern, group): value}, drawn and recorded in place of the
    table above. It exists for one case: a bar SHORT enough that there is no
    interior left to sample, which is publication 127's two fifteen-pixel bars.
    Such a bar has a mean and a dispersion and no measurable fill - the whole
    reason `identity_resolution.csv` exists - and no group of the table above
    produces one, so a scenario about a human-named series had nothing to name.
    """
    overrides = dict(overrides or {})
    im = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(im)
    zero = int(round(to_pixel(0)))
    d.line((PANEL[0], zero, PANEL[1], zero), fill="black", width=2)
    d.line((PANEL[0], PANEL[2], PANEL[0], PANEL[3]), fill="black", width=2)
    span = len(PATTERNS) * BAR_W + (len(PATTERNS) - 1) * GAP
    recorded = {}
    for group, gx in zip(GROUPS, GROUP_X):
        left = gx - span // 2
        for k, pattern in enumerate(PATTERNS):
            drawn = pattern if group != collide_group else PATTERNS[0]
            value = overrides.get((pattern, group),
                                  TRUTH[pattern][GROUPS.index(group)])
            top = int(round(to_pixel(value)))
            x0 = left + k * (BAR_W + GAP)
            box = (x0, top, x0 + BAR_W, zero)
            if drawn == "SOLID":
                d.rectangle(box, fill="black")
            elif drawn == "HATCHED":
                d.rectangle(box, fill="white", outline="black", width=STROKE)
                _hatch(im, (x0 + STROKE, top + STROKE,
                            x0 + BAR_W - STROKE, int(zero) - STROKE))
                d.rectangle(box, outline="black", width=STROKE)
            else:
                d.rectangle(box, fill="white", outline="black", width=STROKE)
            # whisker: stem from the bar top to the cap, then the cap stroke
            sd_px = abs(to_pixel(SD[pattern]) - zero)
            xc = x0 + BAR_W // 2
            cap = int(round(top - sd_px))
            d.line((xc, top, xc, cap), fill="black", width=2)
            d.line((xc - 9, cap, xc + 9, cap), fill="black", width=2)
            # the trap: a significance glyph, same black, floating above the cap
            if group in GLYPH_GROUPS and pattern == "SOLID":
                d.line((xc - 7, cap - 16, xc + 7, cap - 16), fill="black", width=2)
                d.line((xc, cap - 23, xc, cap - 9), fill="black", width=2)
            if group != collide_group:
                recorded.setdefault(pattern, {})[group] = dict(
                    mean=value, dispersion=SD[pattern], x=xc)
    im.save(path)
    with open(truth_path, "w", encoding="utf-8") as fh:
        json.dump({"panel_box": list(PANEL), "y_ticks": Y_TICKS,
                   "groups": GROUPS, "group_x": GROUP_X, "patterns": PATTERNS,
                   "collide_group": collide_group,
                   "overrides": sorted("%s/%s=%s" % (p, g, v)
                                       for (p, g), v in overrides.items()),
                   "series": recorded},
                  fh, indent=1, sort_keys=True)
    return path


if __name__ == "__main__":
    print(draw(os.path.join(HERE, "mono_bar_fixture.png"),
               os.path.join(HERE, "mono_bar_fixture_truth.json")))
    print(draw(os.path.join(HERE, "mono_bar_fixture_collide.png"),
               os.path.join(HERE, "mono_bar_fixture_collide_truth.json"),
               collide_group="T2"))
