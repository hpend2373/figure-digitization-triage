"""Scenarios for the monochrome bar geometry prototype.

    python3 test_measure_mono_bars.py      # exit 0 = all scenarios pass

`measure_mono_bars.py` is the evidence a replacement for `_FILL_BANDS` has to be
justified by, and evidence nobody checks is decoration. Every scenario here
draws the trap it is about, so the assertion is about the cost of getting it
wrong rather than about the number that happens to come out today.

Each one was written by reverting the fix it guards and confirming the scenario
fails; the revert is named in the comment above it, so the next person can do
the same in ten seconds. Two rules the whole file is built on:

**A refusal is a result.** Most of these assert that NO value came back. A
prototype that returns a number it cannot defend is worse than one that returns
nothing, because the fill vocabulary is trained on these numbers and a wrong
prototype becomes the definition every other bar is matched against.

**The panel does not start at row 0.** Every fixture here puts its panel far
down the page and paints the band above it solid black, because a coordinate
mistake that only shows up on a real 600 DPI page render is a mistake a
synthetic fixture with `y0 = 0` will never catch.
"""
import csv
import json
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mark_readers as MRX                 # noqa: E402
import review_overlay as OVERLAY           # noqa: E402
import measure_mono_bars as M              # noqa: E402
import mono_bar_geometry as G              # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


# ---------------------------------------------------------------- the canvas
#
# One geometry for every scenario, so a difference in a result is a difference
# in what was drawn. The panel sits at page row 400 and the 300 rows above it
# are painted black: nothing that slices the panel correctly can see them, and
# anything that mixes box-relative rows with absolute ones reads solid ink.
STROKE = 4
X0, X1, Y0, Y1 = 40, 440, 400, 800
BASE = 720                      # page row of the value-0 rule
PX_PER_UNIT = 3.0               # 100 units over 300 px
SLOTS = [(60, 159), (180, 279), (300, 399)]
ANCHOR = (SLOTS[0][0] + SLOTS[-1][1]) // 2
TICKS = [[0, BASE], [100, BASE - 100 * PX_PER_UNIT]]


def blank():
    img = np.full((860, 480), 255, np.uint8)
    img[100:350, :] = 0         # the trap for box-relative row arithmetic
    img[BASE:BASE + STROKE, X0 + 5:X1 - 5] = 0       # the baseline rule
    return img


def top_row(units):
    return int(round(BASE - units * PX_PER_UNIT))


def solid(img, slot, units):
    a, b = SLOTS[slot]
    img[top_row(units):BASE, a:b + 1] = 0


def outline(img, slot, units):
    a, b = SLOTS[slot]
    t = top_row(units)
    img[t:BASE, a:a + STROKE] = 0
    img[t:BASE, b + 1 - STROKE:b + 1] = 0
    img[t:t + STROKE, a:b + 1] = 0


def hatched(img, slot, units, skip=()):
    """Diagonals, which is what makes the walk use DISTRIBUTED_BODY rather than
    the side tracks - the case where a gap in the ink is not crossable."""
    a, b = SLOTS[slot]
    t = top_row(units)
    for c in range(a - (BASE - t), b + 1, 9):
        for k in range(BASE - t):
            x, y = c + k, BASE - 1 - k
            if a <= x <= b and t <= y < BASE and not any(lo <= y <= hi for lo, hi in skip):
                img[y, max(a, x - 1):min(b, x + 1) + 1] = 0


def errorbar(img, slot, units, length, cap_units=0.7, stem_grey=0):
    a, b = SLOTS[slot]
    t = top_row(units)
    mid = (a + b) // 2
    img[t - length:t, mid - 1:mid + 2] = stem_grey
    half = int(cap_units * (b - a + 1) / 2)
    img[t - length - 2:t - length, mid - half:mid + half + 1] = 0


def write(img, name, tmp):
    path = os.path.join(tmp, name + ".png")
    Image.fromarray(img).save(path)
    return path


def dither(img, y, fraction, a=SLOTS[0][0], b=SLOTS[-1][1]):
    """A partly inked row, which is what the edge of a printed rule looks like
    once it has been rendered, rescanned and JPEG'd: dark in most columns, an
    unbroken run in none of them."""
    for x in range(a, b + 1):
        if (x * 7919) % 1000 < fraction * 1000:
            img[y, x] = 0


def spec(path, fills, anchor=ANCHOR, window=190, tag="t", box=None):
    return dict(tag=tag, path=path, box=box or [X0, X1, Y0, Y1], ticks=TICKS,
                anchors={"G": anchor}, fills=fills, group_window=window,
                baseline=0.0)


class Geometry(object):
    """The same figure at any scale, so "every length is a multiple of the
    stroke" can be checked rather than asserted.

    Everything in CI is drawn at about a 2 px stroke - 397 is 1, the fixture 2 -
    and publication 127 at 600 DPI is 3, which CI never sees because its raster
    is not redistributable. A rule that holds at one stroke width and not at
    another is a rule about this fixture.
    """

    def __init__(self, s):
        r = lambda v: int(round(v * s))                            # noqa: E731
        self.s, self.r = s, r
        self.stroke = max(1, r(STROKE))
        self.x0, self.x1, self.y0, self.y1 = r(X0), r(X1), r(Y0), r(Y1)
        self.base, self.ppu = r(BASE), PX_PER_UNIT * s
        self.slots = [(r(a), r(b)) for a, b in SLOTS]
        self.shape = (r(860), r(480))
        # A stipple is a lattice, so its pitch is part of the figure and scales
        # with it. Coverage stays near 0.09 at every scale, which is the band
        # publication 127's stipple actually reads in.
        self.dot = max(1, r(2))
        self.pitch = (max(self.dot + 1, r(7)), max(self.dot + 1, r(6)))

    def blank(self):
        img = np.full(self.shape, 255, np.uint8)
        img[self.r(100):self.r(350), :] = 0
        img[self.base:self.base + self.stroke, self.x0 + 5:self.x1 - 5] = 0
        return img

    def top(self, units):
        return int(round(self.base - units * self.ppu))

    def outline(self, img, k, units):
        a, b = self.slots[k]
        t, w = self.top(units), self.stroke
        img[t:self.base, a:a + w] = 0
        img[t:self.base, b + 1 - w:b + 1] = 0
        img[t:t + w, a:b + 1] = 0

    def solid(self, img, k, units):
        a, b = self.slots[k]
        img[self.top(units):self.base, a:b + 1] = 0

    def hatch(self, img, k, units, pitch=9):
        """Diagonals inside an outline. A 45 degree stroke crosses EVERY row of
        the interior however far apart the strokes are, which is what makes
        "no blank rows" a property of the word rather than of the density."""
        self.outline(img, k, units)
        a, b = self.slots[k]
        t, w = self.top(units), self.stroke
        for c in range(a - (self.base - t), b + 1, self.r(pitch)):
            for j in range(self.base - t):
                x, y = c + j, self.base - 1 - j
                if a + w <= x <= b - w and t + w <= y < self.base:
                    img[y, max(a, x - w // 2):min(b, x + w // 2) + 1] = 0

    def stipple(self, img, k, units, pitch=None, dot=None):
        """An outlined bar with a dot lattice inside it, which is what
        publication 127 prints: most rows of the interior are blank paper, and
        the side strokes are what carries the walk past them."""
        self.outline(img, k, units)
        a, b = self.slots[k]
        t = self.top(units)
        px, py = pitch or self.pitch, (pitch or self.pitch)
        px, py = (px if isinstance(px, tuple) else (px, px))[0], \
                 (py if isinstance(py, tuple) else (py, py))[1]
        d = dot or self.dot
        for y in range(t + 2 * self.stroke, self.base - self.stroke, py):
            for x in range(a + 2 * self.stroke, b + 1 - 2 * self.stroke, px):
                img[y:y + d, x:x + d] = 0

    def spec(self, path, fills, anchors=None):
        anchor = (self.slots[0][0] + self.slots[-1][1]) // 2
        return dict(tag="scale%g" % self.s, path=path,
                    box=[self.x0, self.x1, self.y0, self.y1],
                    ticks=[[0, self.base], [100, self.base - 100 * self.ppu]],
                    anchors=anchors or {"G": anchor}, fills=fills,
                    group_window=self.r(190), baseline=0.0)


#: The grey the SYNTHETIC fixture prints its axis numbers in. Nothing else uses
#: it, so "are the printed tick labels still in the picture, and not painted
#: over" is a pixel count rather than an opinion.
LABEL_INK = 77


def print_axis_labels(img, geom, values):
    """Draw `0`, `10`, `20` ... beside the axis, where a journal prints them.

    The fixtures in this file draw bars and no numbers, which is fine for
    measuring and useless for the one check the panel picture exists for: the
    value the calibration claims, beside the value the FIGURE prints. Without
    printed numbers a test can only confirm the orange line is in the right
    place, and a line in the right place is exactly what a factor-of-ten error
    still produces.
    """
    from PIL import ImageDraw as _Draw
    canvas = Image.fromarray(img)
    draw = _Draw.Draw(canvas)
    for value in values:
        y = int(round(geom.base - value * geom.ppu))
        draw.text((max(0, geom.x0 - 32), max(0, y - 5)), "%g" % value,
                  fill=LABEL_INK)
    return np.array(canvas)


def _text(value):
    return "" if value == "" or value is None else str(value)


def _raises_value(call):
    try:
        call()
    except ValueError:
        return True
    return False


def _raises_type(call):
    try:
        call()
    except TypeError:
        return True
    return False


def _raises(call, marker):
    """Whether `call` refuses, by the name the refusal goes by."""
    try:
        call()
    except ValueError as exc:
        return marker in str(exc)
    return False


def only(records, slot=0):
    hit = [r for r in records if r.get("slot") == slot]
    return hit[0] if hit else (records[0] if records else {})


def kinds(rec):
    return [m["kind"] for m in rec.get("remote", [])]


TMP = tempfile.mkdtemp(prefix="mmb_")
try:
    # -------------------------------------------------- 1. the ordinary case
    print("an error bar is expected furniture, not a contradiction")
    img = blank()
    solid(img, 0, 60)
    errorbar(img, 0, 60, length=24)
    rec = only(M.measure_panel(spec(write(img, "cap", TMP), ["SOLID"])))
    check("the bar reads its own top, not the cap",
          abs(rec.get("value", -99) - 60.0) <= 0.5, repr(rec.get("value")))
    check("the cap is classified as a cap",
          kinds(rec) == ["ERRORBAR_CAP"], repr(kinds(rec)))
    check("no contradiction is raised", rec.get("contradiction_px") == 0,
          repr(rec.get("contradiction_px")))
    check("the fill is sampled", rec.get("ink_mass", 0) > 0.9,
          repr(rec.get("ink_mass")))
    # REVERT: store the cap's panel row under `cap_px` and hand it to the
    # calibration, as the production reader does with its own `cap_px`. On this
    # panel - page row 400 - the 8.5 unit error bar reports 141.8.
    cap_page = top_row(60) - 25.5              # two cap rows, drawn 24 px up
    check("the cap row is reported in page coordinates",
          abs(rec.get("cap_px_image", -999) - cap_page) <= 1.0,
          "%r against %r" % (rec.get("cap_px_image"), cap_page))
    check("the panel-frame row is kept separately and differs by y0",
          rec.get("cap_px_image", 0) - rec.get("cap_row_panel", 0) == Y0,
          "%r %r" % (rec.get("cap_px_image"), rec.get("cap_row_panel")))
    check("the dispersion the cap implies is the one it was drawn at",
          abs(rec.get("dispersion", -99) - 25.5 / PX_PER_UNIT) <= 0.5,
          repr(rec.get("dispersion")))

    # -------------------------------------------------- 2. a glyph above it
    print("\na significance glyph above the cap changes nothing")
    img = blank()
    solid(img, 0, 60)
    errorbar(img, 0, 60, length=24)
    img[top_row(60) - 60:top_row(60) - 52, 100:112] = 0        # the asterisk
    rec = only(M.measure_panel(spec(write(img, "glyph", TMP), ["SOLID"])))
    check("the value is the same as without the glyph",
          abs(rec.get("value", -99) - 60.0) <= 0.5, repr(rec.get("value")))
    check("cap and glyph are told apart",
          sorted(kinds(rec)) == ["ANNOTATION_OR_GLYPH", "ERRORBAR_CAP"],
          repr(kinds(rec)))

    # -------------------------------------------------- 3. a gap in the body
    #
    # REVERT: delete the `elif body_like and distance <= reach` branch in
    # remote_support(). The component above the gap becomes ANNOTATION_OR_GLYPH,
    # the bar keeps a value measured 20 units below its own top, and that value
    # becomes a HATCHED prototype.
    print("\na body-shaped thing just above the bar is not an annotation")
    img = blank()
    gap = (top_row(40) - 12, top_row(40) - 1)
    hatched(img, 0, 60, skip=[gap])
    rec = only(M.measure_panel(spec(write(img, "gap", TMP), ["HATCHED"])))
    check("the walk is refused, not trusted",
          rec.get("error") == "REMOTE_SUPPORT_UNRESOLVED",
          repr(rec.get("error")) + " " + repr(kinds(rec)))
    check("no value survives the refusal", "value" not in rec,
          repr(rec.get("value")))
    check("no fill survives the refusal", "ink_mass" not in rec)
    check("the number that was refused is still auditable",
          "provisional_value" in rec)

    # -------------------------------------------------- 4. a narrow residual
    #
    # REVERT: change the final `else` in remote_support() to
    # ANNOTATION_OR_GLYPH. A shape that matches nothing then reads as a shape
    # that was positively identified as harmless.
    print("\nink continuous with the bar that is not shaped like the bar")
    img = blank()
    solid(img, 0, 40)
    a, _b = SLOTS[0]
    # A patch: too wide to be a stem, too narrow to be the bar, off to one side
    # so it is not the bar's own top, and sitting on the bar so it is not a
    # separate glyph. The fixture used to be a narrow spur ending in a wider
    # blob, which is what an error bar IS - and once the stem was measured
    # rather than assumed central, the reader correctly read it as one.
    img[top_row(40) - 10:top_row(40), a + 5:a + 35] = 0
    rec = only(M.measure_panel(spec(write(img, "spur", TMP), ["SOLID"])))
    check("an unidentifiable neighbour refuses the bar",
          rec.get("error") == "REMOTE_SUPPORT_UNRESOLVED",
          repr(rec.get("error")) + " " + repr(kinds(rec)))
    check("and it is recorded as unresolved, not as a glyph",
          "UNRESOLVED_REMOTE_SUPPORT" in kinds(rec), repr(kinds(rec)))

    # -------------------------------------------------- 5. nothing at all
    #
    # REVERT: delete the `max(up_total, down_total) == 0` guard in
    # measure_panel(). The group returns NO records - not an error, nothing -
    # and a panel silently reports fewer bars than it declared.
    print("\na group with no bars says so")
    img = blank()
    solid(img, 0, 60)
    records = M.measure_panel(spec(write(img, "empty", TMP), ["SOLID"],
                                   anchor=X1 - 20, window=15))
    check("the empty group still produces a record", len(records) == 1,
          "got %d records" % len(records))
    check("and the record says why",
          records and records[0].get("error") == "NO_SEED_SUPPORT",
          repr(records[0].get("error")) if records else "no record")

    # -------------------------------------------------- 6. a clipped window
    #
    # REVERT: delete the `clipped` guard in measure_panel(). Publication 127's
    # middle panel then reads 3.37 for a bar that is 2.47, because the visible
    # span divided by three puts the neighbour's stroke in the last footprint.
    print("\na group that runs off the end of its own window is refused")
    img = blank()
    for k in range(3):
        solid(img, k, 40 + 10 * k)
    path = write(img, "clip", TMP)
    tight = M.measure_panel(spec(path, ["SOLID"] * 3, window=150))
    check("the clip is detected",
          tight and tight[0].get("error") == "GROUP_WINDOW_CLIPPED",
          repr(tight[0].get("error")) if tight else "no record")
    check("and it names the side it happened on",
          tight and "LEFT" in tight[0].get("clipped_at", []),
          repr(tight[0].get("clipped_at")) if tight else "")
    wide = M.measure_panel(spec(path, ["SOLID"] * 3, window=190))
    check("the same figure in a window that fits reads all three bars",
          [round(r.get("value", -99)) for r in wide] == [40, 50, 60],
          repr([r.get("value") for r in wide]))

    # -------------------------------------------------- 7. where texture looks
    #
    # REVERT: change the roi slice in texture() back to
    # `gray[keep_top:keep_bottom, ca:cb]`. The open bar reads ink_mass 1.000
    # off the black band 300 px above the panel, and OPEN enters the fill
    # vocabulary as the blackest thing in the figure.
    print("\ntexture is sampled inside the panel and nowhere else")
    img = blank()
    outline(img, 0, 60)
    solid(img, 1, 60)
    both = M.measure_panel(spec(write(img, "rows", TMP), ["OPEN", "SOLID"]))
    op, so = only(both, 0), only(both, 1)
    check("an open bar is empty", op.get("ink_mass", 1.0) < 0.05,
          repr(op.get("ink_mass")))
    check("a solid bar is full", so.get("ink_mass", 0.0) > 0.9,
          repr(so.get("ink_mass")))
    check("the two are not the same measurement",
          abs(op.get("ink_mass", 0) - so.get("ink_mass", 0)) > 0.8)

    # -------------------------------------------------- 8. a bar with no inside
    #
    # REVERT: restore `keep_top, keep_bottom = top, bottom` as the fallback in
    # texture(). A 13 px bar at a stroke of 4 is its own two rules, so an OPEN
    # bar reports half its area as fill.
    print("\na bar too short to have an interior gets no fill")
    img = blank()
    outline(img, 0, 4)
    rec = only(M.measure_panel(spec(write(img, "short", TMP), ["OPEN"])))
    check("the fill is refused", rec.get("error") == "BAR_TOO_SMALL_TO_SAMPLE",
          repr(rec.get("error")))
    check("no fill number is reported at all", "ink_mass" not in rec,
          repr(rec.get("ink_mass")))
    check("the bar top itself is still measured and kept",
          abs(rec.get("value", -99) - 4.0) <= 0.6, repr(rec.get("value")))

    # -------------------------------------------------- 9. a grey stem
    #
    # REVERT: pass threshold instead of stem_threshold to the stem trace and cap
    # search in remote_support(). The stem is invisible at 128, the cap hangs
    # off nothing, and it is filed as an annotation - which is harmless here and
    # is not harmless on a figure where the cap is what the dispersion is read
    # from.
    print("\na stem printed lighter than the bar is still a stem")
    img = blank()
    solid(img, 0, 60)
    errorbar(img, 0, 60, length=24, stem_grey=170)
    rec = only(M.measure_panel(spec(write(img, "greystem", TMP), ["SOLID"])))
    check("the cap is found through a grey stem",
          "ERRORBAR_CAP" in kinds(rec), repr(kinds(rec)))
    check("and the bar still reads its own top",
          abs(rec.get("value", -99) - 60.0) <= 0.5, repr(rec.get("value")))

    # -------------------------------------------------- 10. panel furniture
    #
    # REVERT: drop `and distance <= reach` so any body-like component is
    # unresolved. Publication 397's four bars all lose their values to the rule
    # at the top of the panel, which is wide, spanning and thick - shape alone
    # cannot tell it from a bar body, only distance can.
    print("\na rule at the top of the panel is not the top of the bar")
    img = blank()
    solid(img, 0, 40)
    img[Y0 + 20:Y0 + 28, X0 + 5:X1 - 5] = 0            # the panel's own frame
    rec = only(M.measure_panel(spec(write(img, "frame", TMP), ["SOLID"])))
    # The frame is drawn to the same length as the baseline and twice its
    # weight, so it ties on run length and wins on argmax, which returns the
    # FIRST maximum and the frame is nearer the top of the panel.
    #
    # REVERT: call stroke_scale() without baseline_row. Every threshold in the
    # file doubles and the scenario still passes on its other assertions, which
    # is the point - a stroke wrong by a factor of two does not fail, it drifts.
    check("a thicker distant frame does not replace the baseline stroke",
          rec.get("stroke_px") == STROKE, repr(rec.get("stroke_px")))
    check("the distant rule does not refuse the bar",
          rec.get("error") is None, repr(rec.get("error")))
    check("it is filed as not-this-bar",
          "ANNOTATION_OR_GLYPH" in kinds(rec), repr(kinds(rec)))
    check("the bar keeps its value",
          abs(rec.get("value", -99) - 40.0) <= 0.5, repr(rec.get("value")))

    # -------------------------------------------------- 11. a fading rule
    #
    # REVERT: in rule_edge(), drop the fade clause and keep only `if not
    # unbroken`. The seed band then starts on the rule's own ringing, the paper
    # BETWEEN the bars is inked in a quarter of the band, every column in the
    # window seeds, and the group is refused for running off a window it fits
    # inside comfortably.
    print("\nthe ringing around a printed rule is part of the rule")
    img = blank()
    for k in range(3):
        solid(img, k, 40 + 10 * k)
    for k, frac in enumerate((0.85, 0.70, 0.55, 0.42)):
        dither(img, BASE - 1 - k, frac, X0 + 5, X1 - 5)
    got = M.measure_panel(spec(write(img, "ring", TMP), ["SOLID"] * 3))
    check("the group is not refused",
          [r.get("error") for r in got] == [None] * 3,
          repr([r.get("error") for r in got]))
    check("and all three bars read their own heights",
          [round(r.get("value", -99)) for r in got] == [40, 50, 60],
          repr([r.get("value") for r in got]))

    # -------------------------------------------------- 12. a cropped panel
    #
    # REVERT: `if band.shape[0] < 2` in seed_support(). SEED_SUPPORT is a
    # FRACTION of the band, so a band truncated by the panel edge changes what
    # the constant means - a quarter of two rows is one row. Publication 127's
    # panel box ends three rows below its baseline, and the rule's own fade in
    # those rows outvoted 246 px of real upward bar.
    print("\na panel that ends at its baseline has no downward bars")
    img = blank()
    for k in range(3):
        solid(img, k, 40 + 10 * k)
    for y in range(BASE + STROKE, BASE + STROKE + 3):
        dither(img, y, 0.95)
    cropped = [X0, X1, Y0, BASE + STROKE + 3]
    got = M.measure_panel(spec(write(img, "crop", TMP), ["SOLID"] * 3, box=cropped))
    check("the bars are still read upward",
          [r.get("direction") for r in got] == ["UP"] * 3,
          repr([(r.get("direction"), r.get("error")) for r in got]))
    check("with the heights they were drawn at",
          [round(r.get("value", -99)) for r in got] == [40, 50, 60],
          repr([r.get("value") for r in got]))

    # -------------------------------------------------- 13. a real stipple
    #
    # The fill publication 127 broke on, and the one no synthetic fixture in
    # this package had: interior coverage under a tenth, four blank rows in
    # every six, and the ink in small components spread across the whole bar.
    # `hatched()` is not a substitute - a diagonal inks every row.
    print("\na stipple is mostly blank paper and still a filled bar")
    g = Geometry(1.0)
    img = g.blank()
    g.outline(img, 0, 60)
    g.stipple(img, 1, 60)
    g.solid(img, 2, 60)
    got = M.measure_panel(g.spec(write(img, "stipple", TMP),
                                 ["OPEN", "STIPPLED", "SOLID"]))
    check("all three bars are read", len(got) == 3 and
          all("value" in r for r in got), repr([r.get("error") for r in got]))
    check("and all three are the height they were drawn at",
          all(abs(r.get("value", -99) - 60.0) <= 0.6 for r in got),
          repr([r.get("value") for r in got]))
    ink = [r.get("ink_mass") for r in got]
    check("the stipple's interior is under a tenth inked",
          0.05 <= ink[1] <= 0.13, repr(ink))
    check("the bar is over 180 px tall, so this is not a rounding artefact",
          got[1].get("bar_height", 0) >= 180, repr(got[1].get("bar_height")))
    check("most of its rows are empty",
          got[1]["t128"]["row_coverage_min"] == 0.0,
          repr(got[1]["t128"]["row_coverage_min"]))
    check("its ink is in many separate columns, unlike a stem",
          got[1]["t128"]["column_segments"] >= 5,
          repr(got[1]["t128"]["column_segments"]))
    check("open, stipple and solid do not overlap",
          ink[0] < 0.05 < ink[1] < 0.4 < ink[2], repr(ink))

    # -------------------------------------------------- 14. scale invariance
    #
    # Every length in the file is a multiple of the measured stroke, which is
    # the claim that makes one geometry serve 397 at 1 px, the fixture at 2 and
    # publication 127 at 3. Nothing checked it: the private raster is the only
    # thing in the corpus with a stroke above 2, and CI cannot see it.
    print("\nthe same figure at half, one and double size reads the same")
    seen = {}
    for s in (0.5, 1.0, 2.0):
        g = Geometry(s)
        img = g.blank()
        g.outline(img, 0, 30)
        g.stipple(img, 1, 45)
        g.solid(img, 2, 60)
        rows = M.measure_panel(g.spec(write(img, "scale%g" % s, TMP),
                                      ["OPEN", "STIPPLED", "SOLID"]))
        seen[s] = rows
        check("stroke %.0f px measured at scale %g" % (g.stroke, s),
              rows and rows[0].get("stroke_px") == g.stroke,
              repr(rows[0].get("stroke_px")) if rows else "no records")
        check("three bars read at scale %g" % s,
              len(rows) == 3 and all("value" in r for r in rows),
              repr([r.get("error") for r in rows]))
    want = [30.0, 45.0, 60.0]
    for s, rows in sorted(seen.items()):
        got = [r.get("value", -99) for r in rows]
        check("the means survive scale %g" % s,
              all(abs(a - b) <= 1.0 for a, b in zip(got, want)), repr(got))
    fills = {s: [r.get("ink_mass") for r in rows] for s, rows in seen.items()}
    check("and so does the fill ordering, at every scale",
          all(f[0] < 0.05 < f[1] < 0.4 < f[2] for f in fills.values()),
          repr(fills))

    # -------------------------------------------------- 15. a real cap ratio
    #
    # REVERT: `if width < floor` back to `span < 0.30` with span as a fraction
    # of the BAR. Every error bar in both real figures disappears - 397 draws
    # its caps at 0.18 of the bar and publication 127 at 0.17-0.19 - and the
    # figures report no dispersion at all. The 0.30 was fitted to the fixture in
    # this file, whose caps are 0.70 of the bar, which is why nothing noticed.
    print("\na cap is wide next to its stem, not next to the bar")
    img = blank()
    solid(img, 0, 60)
    errorbar(img, 0, 60, length=24, cap_units=0.20)
    rec = only(M.measure_panel(spec(write(img, "narrowcap", TMP), ["SOLID"])))
    caps = [m for m in rec.get("remote", []) if m["kind"] == "ERRORBAR_CAP"]
    check("a cap a fifth of the bar wide is still a cap", len(caps) == 1,
          repr(kinds(rec)))
    check("and it is several times wider than the stem it hangs from",
          caps and caps[0]["cap_width_px"] >= 3 * caps[0]["stem_width_px"],
          repr(caps))
    check("the dispersion is the one it was drawn at",
          abs(rec.get("dispersion", -99) - 25.5 / PX_PER_UNIT) <= 0.5,
          repr(rec.get("dispersion")))

    # -------------------------------------------------- 16. a one-row stem
    #
    # REVERT: `scan = range(edge + step * max(1, stroke), ...)`. On a short bar
    # the whole error bar is a single row of stem between the top rule and the
    # cap, a fixed one-stroke skip steps over it, and the cap has nothing to
    # hang from. Four of publication 127's cells are drawn this way.
    print("\nan error bar shorter than the bar's own top rule")
    img = blank()
    solid(img, 0, 12)
    errorbar(img, 0, 12, length=1, cap_units=0.20)
    rec = only(M.measure_panel(spec(write(img, "shortbar", TMP), ["SOLID"])))
    check("the cap is found through a single row of stem",
          "ERRORBAR_CAP" in kinds(rec), repr(kinds(rec)))
    check("the bar still reads its own top",
          abs(rec.get("value", -99) - 12.0) <= 0.7, repr(rec.get("value")))

    # -------------------------------------------------- 17. the bar's own edge
    #
    # REVERT: delete the `extent < stroke and distance <= stroke` branch. The
    # antialiased row the walk stopped just below becomes an unidentifiable
    # structure and the bar refuses itself. Three of publication 127's cells did
    # this the moment the scan start was measured instead of assumed.
    print("\nthe bar's own antialiased edge is not a separate structure")
    img = blank()
    solid(img, 0, 40)
    img[top_row(40) - 1, 70:110] = 90     # one row of ringing: dark, sub-stroke
    rec = only(M.measure_panel(spec(write(img, "ring1", TMP), ["SOLID"])))
    check("the remnant does not refuse the bar", rec.get("error") is None,
          "%r %r" % (rec.get("error"), kinds(rec)))
    check("and it is named for what it is",
          "UNRESOLVED_REMOTE_SUPPORT" not in kinds(rec), repr(kinds(rec)))

    # -------------------------------------------------- 18. an impostor rule
    #
    # REVERT: `seed = a + argmax(runs[a:b])` picks the LONGEST run in the search
    # window, and a gridline just above the baseline that is exactly as long
    # ties - argmax then takes whichever comes first, which going down the page
    # is the gridline. Distance to the calibrated zero has to win before length
    # does.
    print("\na heavier gridline just above the baseline is not the baseline")
    img = blank()
    solid(img, 0, 40)
    img[BASE - 15:BASE - 7, X0 + 5:X1 - 5] = 0           # 8 px thick, same span
    gray = np.asarray(Image.open(write(img, "impostor", TMP)).convert("L"))
    zero = BASE - Y0
    check("the rule containing the calibrated zero wins over the longer-or-equal one",
          M.stroke_scale(gray, [X0, X1, Y0, Y1], baseline_row=zero).value_px == STROKE,
          repr(M.stroke_scale(gray, [X0, X1, Y0, Y1], baseline_row=zero)))
    check("and without the baseline it is the gridline that is measured",
          M.stroke_scale(gray, [X0, X1, Y0, Y1]).value_px == 8,
          repr(M.stroke_scale(gray, [X0, X1, Y0, Y1])))

    # -------------------------------------------------- 19. identity
    print("\na bar with no measurable fill has a geometry and no identity")
    img = blank()
    solid(img, 0, 60)
    outline(img, 1, 4)
    got = M.measure_panel(spec(write(img, "identity", TMP), ["SOLID", "OPEN"]))
    tall, short = only(got, 0), only(got, 1)
    check("the tall bar yielded a fill sample",
          tall.get("fill_sample_status") == "MEASURED",
          repr(tall.get("fill_sample_status")))
    check("the short bar did not, though its slot declares one",
          short.get("fill_sample_status") == "UNRESOLVED_NO_INTERIOR",
          repr(short.get("fill_sample_status")))
    check("neither is named until a figure resolves it",
          all(r.get("identity_status") == "NOT_CALIBRATED" for r in got),
          repr([r.get("identity_status") for r in got]))
    check("and the short bar still has its geometry", "value" in short)

    # -------------------------------------------------- 20. a ragged rule
    #
    # REVERT: `if runs[seed] < max(1, tolerance * strongest)` back to
    # `< 1`. A printed rule's rows do not all carry the same run - publication
    # 127's axis reads 182, 456, 654, 1207, 844, 1072 down its six rows - and a
    # SHORT row seeds a LOOSE band, because the tolerance is a fraction of its
    # own small length. The loose band swallows rows the rule does not own,
    # reaches the calibrated zero, and wins on containment: 3 px became 7.
    print("\na short row of a rule may not speak for the whole rule")
    img = blank()
    img[BASE:BASE + STROKE, :] = 255                    # replace the plain rule
    for offset, run in ((-3, 40), (-2, 150), (-1, 390), (0, 280), (1, 350), (2, 120)):
        img[BASE + offset, X0 + 5:X0 + 5 + run] = 0
    gray = np.asarray(Image.open(write(img, "ragged", TMP)).convert("L"))
    got = M.stroke_scale(gray, [X0, X1, Y0, Y1], baseline_row=BASE + 2 - Y0)
    check("the rule is measured from its strong rows, not its weakest",
          got.value_px == 3, repr(got))

    # -------------------------------------------------- 21. fill identity
    print("\nthe series are named by their fill, from the figure's own samples")
    g = Geometry(1.0)
    img = g.blank()
    for k, units in enumerate((30, 45, 60)):
        (g.outline, g.stipple, g.solid)[k](img, k, units)
    spec1 = g.spec(write(img, "ident3", TMP), ["OPEN", "STIPPLED", "SOLID"])
    spec1["anchors"] = {"G1": spec1["anchors"]["G"]}
    rows = M.measure_panel(spec1)
    ident, verdict = M.fill_identity(rows)
    # One complete group: assignable from relations inside itself, and not a
    # reusable prototype - every range has zero width.
    check("one group names its own bars and claims nothing more",
          verdict["status"] == "DIRECT_ONLY" and not verdict["prototype_ready"],
          repr(verdict["status"]))
    check("every bar is named, and named correctly",
          len(ident) == 3 and all(ident[(r["figure"], r["group"]), r["slot"]]
                                  == r["spec_fill"] for r in rows),
          repr(ident))
    check("each ink-separated gap is wider than the spread it separates",
          all(s["gap"] > s["needed"] for s in verdict["separation"]
              if s["separated_by"] == "INK"), repr(verdict["separation"]))

    # -------------------------------------------------- 22. not by position
    #
    # REVERT: return the declared list in slot order from _assign_group(). The
    # scenario passes for every figure whose bars happen to be drawn in the
    # order they are declared - which is all of them - and this is the one that
    # says the identity came from the ink.
    print("\nnaming follows the ink even when it contradicts the slot order")
    img = g.blank()
    g.solid(img, 0, 60)                      # drawn solid-first ...
    g.outline(img, 1, 30)
    rows = M.measure_panel(g.spec(write(img, "flipped", TMP),
                                  ["OPEN", "SOLID"]))     # ... declared open-first
    ident, verdict = M.fill_identity(rows)
    check("the group is still assigned",
          verdict["status"] == "DIRECT_ONLY", repr(verdict["status"]))
    got = {r["slot"]: ident.get(((r["figure"], r["group"]), r["slot"])) for r in rows}
    check("slot 0 is named SOLID though the spec declares OPEN there",
          got.get(0) == "SOLID", repr(got))
    check("and slot 1 SOLID's opposite", got.get(1) == "OPEN", repr(got))

    # -------------------------------------------------- 23. structure, not ink
    #
    # REVERT: order STIPPLED and HATCHED by ink instead of by whether any row of
    # the interior is blank. A dense stipple carries more ink than a sparse
    # hatch, so the two swap names and every value in the figure goes to the
    # wrong series - silently, because both are still "identified".
    print("\na dense stipple is darker than a sparse hatch and still a stipple")
    img = g.blank()
    g.hatch(img, 0, 60, pitch=16)                        # sparse: less ink
    g.stipple(img, 1, 60, pitch=5, dot=3)                # dense: more ink
    rows = M.measure_panel(g.spec(write(img, "swap", TMP), ["HATCHED", "STIPPLED"]))
    ink = {r["spec_fill"]: r.get("ink_mass") for r in rows}
    check("the stipple really does carry more ink than the hatch",
          ink.get("STIPPLED", 0) > ink.get("HATCHED", 1), repr(ink))
    ident, verdict = M.fill_identity(rows)
    check("and both are named correctly anyway",
          verdict["status"] == "DIRECT_ONLY" and
          all(ident[((r["figure"], r["group"]), r["slot"])] == r["spec_fill"]
              for r in rows), "%r %r" % (verdict["status"], ident))

    # -------------------------------------------------- 24. refusal
    print("\ntwo fills the figure cannot separate name nothing at all")
    img = g.blank()
    g.hatch(img, 0, 60, pitch=9)
    g.hatch(img, 1, 45, pitch=9)
    rows = M.measure_panel(g.spec(write(img, "same", TMP), ["HATCHED", "STIPPLED"]))
    ident, verdict = M.fill_identity(rows)
    check("nothing is named", not ident, repr(ident))
    # REVERT: return NOT_ENOUGH_COMPLETE_GROUPS whenever nothing was assigned.
    # This group IS complete - every slot has a fill - and the finding is that
    # its two patterns cannot be told apart. Reporting a shortage of groups
    # sends the bars to NOT_CALIBRATED, so the audit record says "the figure
    # never got the chance" where the truth is "the figure tried and could not".
    check("the figure had a complete group and could not assign it",
          verdict["status"] == "AMBIGUOUS", repr(verdict["status"]))
    check("and it names the group it could not assign",
          len(verdict["unassignable_groups"]) == 1,
          repr(verdict["unassignable_groups"]))
    M.fill_identities_by_figure(rows)
    check("its measured bars say AMBIGUOUS, not NOT_CALIBRATED",
          all(r.get("identity_status") == "AMBIGUOUS" for r in rows),
          repr([r.get("identity_status") for r in rows]))

    # -------------------------------------------------- 25. separation
    #
    # REVERT: drop the `gap <= need` test in fill_identity(). Every group here
    # assigns cleanly on its own - OPEN is the emptier of the two bars in both -
    # and the assignment is still worthless, because what separates the two
    # patterns across the FIGURE is smaller than how much one of them varies.
    # Without the test the figure reports ESTABLISHED and names four bars.
    print("\nseparation smaller than spread names nothing")
    g = Geometry(1.0)
    img = g.blank()
    g.outline(img, 0, 60)                              # OPEN, both groups
    g.stipple(img, 1, 60, pitch=(200, 6), dot=1)       # almost no ink at all
    tag = write(img, "sep_a", TMP)
    rows_a = M.measure_panel(g.spec(tag, ["OPEN", "STIPPLED"]))
    img = g.blank()
    g.outline(img, 0, 45)
    g.stipple(img, 1, 45, pitch=5, dot=3)              # the same pattern, dense
    rows_b = M.measure_panel(g.spec(write(img, "sep_b", TMP), ["OPEN", "STIPPLED"]))
    for r in rows_b:
        r["figure"] = "second_group"
    both = rows_a + rows_b
    for r in both:
        r["identity_domain_id"] = "one_figure"
    ink = sorted(round(r.get("ink_mass", -1), 4) for r in both)
    ident, verdict = M.fill_identity(both)
    check("the two patterns are closer than one of them varies",
          verdict["status"] == "AMBIGUOUS", "%r  ink %r" % (verdict["status"], ink))
    check("so nothing is named", not ident, repr(ident))
    # REVERT: set identity_status from whether a fill was sampled. Every bar
    # here HAS an interior and a texture; not one of them has an identity, and
    # a field that answers the first question while being read as the answer to
    # the second reports four named series on a figure that named none.
    M.fill_identities_by_figure(both)
    check("every bar here did yield a fill sample",
          all(r.get("fill_sample_status") == "MEASURED" for r in both),
          repr([r.get("fill_sample_status") for r in both]))
    check("and not one of them is RESOLVED, because sampling is not naming",
          not [r for r in both if r.get("identity_status") == "RESOLVED"],
          repr([r.get("identity_status") for r in both]))
    check("their status says the figure could not separate them",
          all(r.get("identity_status") == "AMBIGUOUS" for r in both),
          repr([r.get("identity_status") for r in both]))

    # -------------------------------------------------- 26. incomplete groups
    #
    # REVERT: calibrate on every group, complete or not. A group with a bar too
    # short to sample has fewer samples than declared fills, no assignment is
    # forced, and the whole FIGURE goes AMBIGUOUS - so one 15 px bar costs every
    # other bar in the figure its name. Publication 127 has two of them.
    print("\none unsampleable bar does not cost the figure its vocabulary")
    rows = []
    for name, units in (("whole_a", (30, 45, 60)), ("whole_b", (33, 48, 63)),
                        ("holey", (30, 40, 4))):
        img = g.blank()
        g.outline(img, 0, units[0])
        g.stipple(img, 1, units[1])
        g.solid(img, 2, units[2])
        got = M.measure_panel(g.spec(write(img, name, TMP),
                                     ["OPEN", "STIPPLED", "SOLID"]))
        for r in got:
            r["figure"], r["identity_domain_id"] = name, "one_figure"
        rows.extend(got)
    ident, verdict = M.fill_identity(rows)
    check("two complete groups make the prototypes reusable",
          verdict["status"] == "ESTABLISHED" and verdict["prototype_ready"],
          repr(verdict.get("failures") or verdict["status"]))
    check("and the six bars they hold are named",
        sum(1 for k in ident if k[0][0] != "holey") == 6, repr(len(ident)))
    check("the incomplete group's two sampled bars are matched to them",
          sum(1 for k in ident if k[0][0] == "holey") == 2, repr(ident))
    check("the short bar is not named",
          not any(k[0][0] == "holey" and k[1] == 2 for k in ident), repr(ident))

    # -------------------------------------------------- 26b. DIRECT_ONLY
    #
    # REVERT: drop `prototype_ready` and report ESTABLISHED whenever the
    # assignment is clean. A single complete group gives one sample per pattern,
    # every prototype range has zero width, and matching an incomplete group
    # against a range of zero width with a tolerance of zero succeeds only by
    # luck - which is exactly how a wrong identity gets in.
    one = [r for r in rows if r["figure"] in ("whole_a", "holey")]
    ident_one, verdict_one = M.fill_identity(one)
    check("with only one complete group the prototypes are not reusable",
          verdict_one["status"] == "DIRECT_ONLY", repr(verdict_one["status"]))
    check("so nothing in the incomplete group is matched",
          not any(k[0][0] == "holey" for k in ident_one), repr(ident_one))
    check("while the complete group keeps its three names",
          sum(1 for k in ident_one if k[0][0] == "whole_a") == 3, repr(ident_one))

    # -------------------------------------------------- 26c. declared set
    #
    # REVERT: drop `p in allowed` from the partial match. A group is then
    # matched against every prototype in the FIGURE rather than against the
    # patterns it declares, so a bar can come back as a fill its own group does
    # not contain.
    holey = [dict(r) for r in rows if r["figure"] == "holey"]
    for r in holey:
        # The DECLARATION is a property of the group, so re-declaring it means
        # re-declaring it on every record of the group. This group now says it
        # holds two opens and a solid, and no stipple at all.
        r["declared_group_patterns"] = ["OPEN", "OPEN", "SOLID"]
    ident_d, _v = M.fill_identity(
        [r for r in rows if r["figure"] != "holey"] + holey)
    check("a bar is never named a pattern its own group does not declare",
          all(v in ("OPEN", "SOLID") for k, v in ident_d.items()
              if k[0][0] == "holey"),
          repr({k: v for k, v in ident_d.items() if k[0][0] == "holey"}))

    # -------------------------------------------------- 26d. one figure
    print("\ntwo publications are not one figure-local vocabulary")
    mixed = [dict(r) for r in rows]
    for r in mixed[:3]:
        r["identity_domain_id"] = "some_other_publication"
    ident_m, verdict_m = M.fill_identity(mixed)
    check("mixed figures are refused rather than pooled",
          verdict_m["status"] == "MULTIPLE_FIGURES", repr(verdict_m["status"]))
    check("and nothing is named", not ident_m)
    verdicts = M.fill_identities_by_figure(mixed)
    check("the by-figure entry point splits them instead of refusing",
          set(verdicts) == {"one_figure", "some_other_publication"},
          repr(sorted(verdicts)))
    # `all(... or True ...)` stood here and said nothing. What it was reaching
    # for is this: the figure's answer must be the answer it would have given
    # alone, so nothing of the other publication's reached it.
    alone = M.fill_identities_by_figure(
        [dict(r) for r in mixed if r.get("identity_domain_id") == "one_figure"])
    check("and neither figure's samples reach the other's vocabulary",
          verdicts["one_figure"]["prototypes"]
          == alone["one_figure"]["prototypes"]
          and verdicts["one_figure"]["complete_groups"]
          == alone["one_figure"]["complete_groups"]
          and verdicts["some_other_publication"]["status"] != "ESTABLISHED",
          "%r against %r" % (verdicts["one_figure"]["prototypes"],
                             alone["one_figure"]["prototypes"]))
    verdicts = M.fill_identities_by_figure(rows)
    check("and writes the answer onto the records",
          all(r.get("resolved_fill_pattern") == r["spec_fill"] for r in rows
              if r.get("identity_status") == "RESOLVED"),
          repr([(r["figure"], r.get("slot"), r.get("identity_status"),
                 r.get("resolved_fill_pattern"), r.get("spec_fill")) for r in rows]))
    check("a sampled bar that could not be named says NOT_CALIBRATED or AMBIGUOUS,"
          " and an unsampled one says so differently",
          all(r["identity_status"] == "UNRESOLVED_NO_FILL" for r in rows
              if r.get("fill_sample_status") == "UNRESOLVED_NO_INTERIOR"),
          repr([(r["figure"], r.get("slot"), r.get("fill_sample_status"),
                 r.get("identity_status")) for r in rows
                if r.get("fill_sample_status") != "MEASURED"]))

    # -------------------------------------------------- 26e. a lost record
    #
    # REVERT: decide completeness from the records that arrived. A group of
    # three whose third record never came back looks like a complete group of
    # two - every record present has a fill - and it calibrates the figure's
    # prototypes off a group that is missing a bar.
    print("\na group missing a record is not a smaller group")
    lost = [r for r in rows if not (r["figure"] == "whole_b" and r.get("slot") == 2)]
    ident_l, verdict_l = M.fill_identity(lost)
    check("the truncated group is not used to calibrate",
          verdict_l["complete_groups"] == 1, repr(verdict_l["complete_groups"]))
    check("and it is named, with the slot that went missing",
          verdict_l["truncated_groups"].get(str(("whole_b", "G")), {})
          .get("missing_slots") == [2], repr(verdict_l["truncated_groups"]))

    # REVERT: `len(slots) != size` instead of the exact set. Slots {0,1,3}
    # against a declared three has the right count and the right patterns while
    # missing slot 2 and carrying a slot the panel never declared.
    shifted = [dict(r) for r in rows if r["figure"] == "whole_b"]
    for r in shifted:
        if r.get("slot") == 2:
            r["slot"] = 3
    _i, verdict_x = M.fill_identity(
        [r for r in rows if r["figure"] != "whole_b"] + shifted)
    entry = verdict_x["truncated_groups"].get(str(("whole_b", "G")), {})
    check("a slot set with a hole and a stranger is not complete",
          entry.get("missing_slots") == [2] and entry.get("unexpected_slots") == [3],
          repr(verdict_x["truncated_groups"]))

    # REVERT: build the slot dictionary without keeping the arrival list. The
    # second record for a slot overwrites the first, so the group looks one
    # record short and reports no missing slot at all.
    doubled = [dict(r) for r in rows if r["figure"] == "whole_b"]
    doubled.append(dict(doubled[0]))
    _i, verdict_d = M.fill_identity(
        [r for r in rows if r["figure"] != "whole_b"] + doubled)
    entry = verdict_d["truncated_groups"].get(str(("whole_b", "G")), {})
    check("a slot that arrives twice is not a complete group either",
          entry.get("duplicate_slots") == [0], repr(verdict_d["truncated_groups"]))
    check("so one complete group is left and nothing is matched against it",
          verdict_l["status"] == "DIRECT_ONLY", repr(verdict_l["status"]))

    # -------------------------------------------------- 26f. structure again
    #
    # REVERT: drop `_structurally_possible` from the partial match. A hatched
    # bar whose density drifts into the stipple range is renamed STIPPLED, on
    # ink alone, against a row structure that says it cannot be one - which is
    # the ordering this file exists to refuse.
    print("\na drifting hatch is not renamed a stipple by ink alone")
    rows2 = []
    for name, height in (("hb_a", 60), ("hb_b", 57)):
        img = g.blank()
        g.hatch(img, 0, height, pitch=24)               # sparse: about 0.21
        g.stipple(img, 1, height, pitch=(5, 5), dot=3)  # dense: about 0.36
        got = M.measure_panel(g.spec(write(img, name, TMP), ["HATCHED", "STIPPLED"]))
        for r in got:
            r["figure"], r["identity_domain_id"] = name, "hb"
        rows2.extend(got)
    img = g.blank()
    g.hatch(img, 0, 60, pitch=14)          # 0.357 - inside the STIPPLED range
    g.stipple(img, 1, 4, pitch=(5, 5), dot=3)          # and a partner too short
    drift = M.measure_panel(g.spec(write(img, "hb_c", TMP), ["HATCHED", "STIPPLED"]))
    for r in drift:
        r["figure"], r["identity_domain_id"] = "hb_c", "hb"
    ident2, verdict2 = M.fill_identity(rows2 + drift)
    hatch_ink = next(r["ink_mass"] for r in drift if r.get("slot") == 0)
    protos = verdict2["prototypes"]
    check("the drifting hatch really does land inside the stipple range",
          protos["STIPPLED"][0] - 0.06 <= hatch_ink <= protos["STIPPLED"][1] + 0.06
          and hatch_ink > protos["HATCHED"][1] + 0.06,
          "%.4f against %r" % (hatch_ink, protos))
    named = [v for k, v in ident2.items() if k[0][0] == "hb_c" and k[1] == 0]
    check("and it is not renamed STIPPLED on that evidence",
          named != ["STIPPLED"], repr(named))
    check("its rows are all inked, which a stipple's are not",
          next(r["t128"]["row_coverage_min"] for r in drift if r.get("slot") == 0) > 0)

    # -------------------------------------------------- 26g. the noise floor
    #
    # REVERT: floor = max(spread.values()). With one complete group every spread
    # is zero, so ANY difference in ink - including one smaller than how much a
    # single bar's own interior varies - is enough to force "least" and "most".
    print("\na gap smaller than one bar's own variation is not a separation")
    img = g.blank()
    g.outline(img, 0, 60)
    a, b = g.slots[1]
    g.outline(img, 1, 60)
    top = g.top(60)
    for y in range(top + 3 * g.stroke, top + (g.base - top) // 3, 5):
        for x in range(a + 2 * g.stroke, b - 2 * g.stroke, 5):
            img[y:y + 3, x:x + 3] = 0        # ink in the top third only
    rows3 = M.measure_panel(g.spec(write(img, "lumpy", TMP), ["OPEN", "STIPPLED"]))
    lumpy = next(r for r in rows3 if r.get("slot") == 1)
    check("the inked bar varies across its own interior by more than its mean",
          lumpy["ink_mass_tile_spread"] > lumpy["ink_mass"],
          "%r vs %r" % (lumpy["ink_mass_tile_spread"], lumpy["ink_mass"]))
    ident3, verdict3 = M.fill_identity(rows3)
    check("so the figure refuses to call one of them the emptier",
          verdict3["status"] == "AMBIGUOUS", repr(verdict3["status"]))
    check("and names neither", not ident3, repr(ident3))

    # -------------------------------------------------- 26h. an off-centre stem
    #
    # REVERT: drop the stem_band() call and keep only the bar's middle fifth.
    # Publication 397's WOMEN panel draws its whiskers at 39% of the bar width,
    # outside that slice, and three of its four cells lost their dispersion to
    # it - silently, because a bar with no cap is a bar with no dispersion and
    # nothing says which of the two it was.
    print("\nan error bar is centred on its series, not on its bar")
    img = blank()
    solid(img, 0, 60)
    a, b = SLOTS[0]
    off = a + int(0.28 * (b - a))        # outside the bar's middle fifth
    img[top_row(60) - 24:top_row(60), off:off + 2] = 0
    img[top_row(60) - 26:top_row(60) - 24, off - 9:off + 11] = 0
    rec = only(M.measure_panel(spec(write(img, "offstem", TMP), ["SOLID"])))
    check("the cap on an off-centre stem is found",
          "ERRORBAR_CAP" in kinds(rec), repr(kinds(rec)))
    check("and the dispersion it implies is the one it was drawn at",
          abs(rec.get("dispersion", -99) - 25.0 / PX_PER_UNIT) <= 0.5,
          repr(rec.get("dispersion")))
    check("the bar is not refused over it", rec.get("error") is None,
          repr(rec.get("error")))

    # -------------------------------------------------- 26i. touching bars
    #
    # REVERT: drop the trim_to_own_bar() call. The left bar's footprint keeps
    # four columns of its neighbour, and above its own top those columns carry
    # the neighbour's body - a structure inside the footprint that is not this
    # bar, so the cell refuses itself. This is publication 397's WOMEN panel,
    # where the solid bar ends at column 73 and the hatched one starts at 78
    # with diagonals reaching back to 74.
    print("\ntwo bars that touch do not share a footprint")
    g2 = Geometry(1.0)
    img = g2.blank()
    a0, b0 = g2.slots[0]
    a1, b1 = g2.slots[1]
    img[g2.top(40):g2.base, a0:b0 + 1] = 0                 # the left bar, solid
    # ...carrying an error bar, because the band the occupancy is measured in
    # has to exclude it. Measuring over the whole slot instead makes the cap's
    # columns the most inked ones and the bar's own edges the least.
    mid = (a0 + b0) // 2
    img[g2.top(40) - 20:g2.top(40), mid - 1:mid + 2] = 0
    img[g2.top(40) - 22:g2.top(40) - 20, mid - 35:mid + 36] = 0
    tall, edge = g2.top(70), b0 + 1          # adjacent, with NO gap at all
    img[tall:tall + g2.stroke, edge:b1 + 1] = 0             # a taller neighbour
    for c in range(edge - (g2.base - tall), b1 + 1, 9):     # whose hatch bleeds
        for j in range(g2.base - tall):
            x, y = c + j, g2.base - 1 - j
            if edge <= x <= b1 and tall <= y < g2.base:
                img[y, x:x + 2] = 0
    spec2 = g2.spec(write(img, "touch", TMP), ["SOLID", "HATCHED"])
    got = M.measure_panel(spec2)
    left = only(got, 0)
    check("the left bar's footprint is trimmed back to its own columns",
          left.get("trimmed_columns"), repr(left.get("trimmed_columns")))
    check("and it reads its own height rather than refusing itself",
          abs(left.get("value", -99) - 40.0) <= 1.0,
          "%r %r" % (left.get("value"), left.get("error")))
    # The fixture's geometry is known exactly, so the footprint is pinned
    # exactly. "Something was trimmed and the mean survived" passes just as well
    # when the trim ate a third of the bar, because a solid bar's top does not
    # move when you narrow it.
    off = max(g2.x0, (g2.slots[0][0] + g2.slots[-1][1]) // 2 - g2.r(190))
    check("the final footprint is exactly the left bar",
          left.get("footprint") == [a0 - off, b0 - off],
          "%r against %r" % (left.get("footprint"), [a0 - off, b0 - off]))
    check("only the neighbour's columns were removed",
          all(c > b0 - off for c in left["trimmed_columns"]),
          repr(left["trimmed_columns"]))
    check("and the provisional footprint is kept, so the move is auditable",
          left.get("provisional_footprint", [0, 0])[1] > b0 - off,
          repr(left.get("provisional_footprint")))
    right = only(got, 1)
    check("the neighbour it was trimmed away from is still readable",
          "value" in right and right.get("error") is None,
          "%r %r" % (right.get("value"), right.get("error")))

    # -------------------------------------------------- 26j. the neighbour
    #
    # REVERT: drop the `beyond` branch in remote_support(). The overhang becomes
    # a 2 px sliver inside this bar's footprint that is neither bar, cap nor
    # glyph, and the cell refuses itself - which is what publication 397's WOMEN
    # PRE/SOLID did until this existed. A bar is never wider than its own
    # footprint, so nothing outside it can be this bar, and a real body
    # continuation can never trip this.
    print("\nthe bar next door reaching over this one is not this one's problem")
    g3 = Geometry(1.0)
    img = g3.blank()
    a0, b0 = g3.slots[0]
    a1, b1 = g3.slots[1]
    img[g3.top(40):g3.base, a0:b0 + 1] = 0                 # this bar
    tall = g3.top(70)
    img[tall:tall + g3.stroke, b0 - 2:b1 + 1] = 0          # the neighbour's top
    img[tall:g3.base, a1:a1 + g3.stroke] = 0               # rule, overhanging by
    img[tall:g3.base, b1 + 1 - g3.stroke:b1 + 1] = 0       # three columns
    got = M.measure_panel(g3.spec(write(img, "overhang", TMP), ["SOLID", "OPEN"]))
    mine = only(got, 0)
    check("the overhang is named as the neighbour's",
          "NEIGHBOUR_STRUCTURE" in kinds(mine), repr(kinds(mine)))
    check("and this bar is not refused over it", mine.get("error") is None,
          "%r %r" % (mine.get("error"), kinds(mine)))
    check("it reads its own height",
          abs(mine.get("value", -99) - 40.0) <= 1.0, repr(mine.get("value")))

    # -------------------------------------------------- 26k. the trim budget
    #
    # `trim_to_own_bar` takes a footprint, so the budget branch can be pinned by
    # calling it directly. Building an end-to-end figure for it does not work: a
    # bleed wide enough to spend the budget is too faint to seed into the
    # footprint in the first place, so the whole pipeline never offers the
    # primitive the input that reaches this branch.
    #
    # REVERT: return the trimmed footprint instead of EXCESSIVE_TRIM. A bar whose
    # footprint is a quarter somebody else's gets measured from whatever columns
    # survived, with nothing on the record to say so.
    print("\na footprint a quarter made of the bar next door is refused")
    stroke_px, e_row, z_row = 2, 10, 110
    canvas = np.full((120, 60), 255, np.uint8)
    canvas[e_row + stroke_px:z_row - stroke_px, 0:29] = 0        # this bar
    depth = (z_row - stroke_px) - (e_row + stroke_px)
    for col, share in enumerate([0.40, 0.16, 0.06, 0.025, 0.01, 0.004,
                                 0.002, 0.001, 0.001, 0.001, 0.001], start=29):
        canvas[e_row + stroke_px:e_row + stroke_px + max(1, int(depth * share)),
               col] = 0                                          # fading bleed
    kept, gone, reason = M.trim_to_own_bar(
        canvas, (0, 60, 0, 120), (0, 60), (0, 39), e_row, z_row, stroke_px)
    check("more than a quarter of the footprint would have to go",
          len(gone) > 40 // 4, "%d columns" % len(gone))
    check("so the trim is refused by name", reason == "EXCESSIVE_TRIM",
          repr(reason))
    check("and the footprint is handed back untouched", tuple(kept) == (0, 39),
          repr(kept))
    kept2, gone2, reason2 = M.trim_to_own_bar(
        canvas, (0, 60, 0, 120), (0, 60), (0, 33), e_row, z_row, stroke_px)
    check("the same figure inside budget trims and is not refused",
          not reason2 and tuple(kept2) != (0, 33) and gone2,
          "%r %r %r" % (kept2, len(gone2), reason2))

    # -------------------------------------------------- 26l. the two refusals
    #
    # `refine_footprint` is a state machine over trace and trim, so the two
    # refusals it can reach are pinned with fakes. Neither is reachable from a
    # raster: a bleed wide enough to spend the trim budget is too faint to seed
    # into the footprint at all, and a second pass that moves the footprint again
    # needs a figure nobody has found. What is tested here is the CONTRACT -
    # which refusal, under which name, carrying which record - and the primitives
    # it stands in for are pinned separately just above.
    print("\nthe footprint and the extent have to agree before either is used")
    trace_calls = []

    def fake_trace(fp):
        trace_calls.append(tuple(fp))
        return (100.0 + len(trace_calls), "SIDE_TRACK")

    def settles(fp, edge):
        return ((0, 18), [19, 20], "") if tuple(fp) == (0, 20) else (tuple(fp), [], "")

    got = M.refine_footprint((0, 20), fake_trace, settles)
    check("a footprint that settles is used, with both passes run",
          got[0] == (0, 18) and not got[4] and len(trace_calls) == 2,
          "%r %r" % (got, trace_calls))

    def keeps_moving(fp, edge):
        return ((fp[0], fp[1] - 2), [fp[1] - 1, fp[1]], "")

    got = M.refine_footprint((0, 20), fake_trace, keeps_moving)
    check("a footprint that keeps moving is refused",
          got[4] == "FOOTPRINT_DID_NOT_CONVERGE", repr(got[4]))
    check("and the record carries both footprints and both edge rows",
          got[5].get("convergence_stage") == "SECOND_PASS" and
          got[5]["first_trimmed_footprint"] != got[5]["second_trimmed_footprint"] and
          got[5]["provisional_edge_row_panel"] != got[5]["retraced_edge_row_panel"],
          repr(got[5]))

    # REVERT: `rec["error"] = "FOOTPRINT_DID_NOT_CONVERGE"` unconditionally in
    # the second pass. An over-budget trim hands back the footprint it was
    # given, so the record then says the two passes disagree while showing two
    # footprints that are identical.
    def over_budget_second(fp, edge):
        return (((0, 18), [19, 20], "") if tuple(fp) == (0, 20)
                else (tuple(fp), list(range(10, 19)), "EXCESSIVE_TRIM"))

    got = M.refine_footprint((0, 20), fake_trace, over_budget_second)
    check("a second pass over budget keeps its own name",
          got[4] == "EXCESSIVE_TRIM", repr(got[4]))
    check("and says which pass it happened on",
          got[5].get("convergence_stage") == "SECOND_PASS", repr(got[5]))

    def over_budget_first(fp, edge):
        return (tuple(fp), [19, 20], "EXCESSIVE_TRIM")

    got = M.refine_footprint((0, 20), fake_trace, over_budget_first)
    check("a first pass over budget is named on the first pass",
          got[4] == "EXCESSIVE_TRIM"
          and got[5].get("convergence_stage") == "FIRST_PASS", repr(got))

    # -------------------------------------------------- 26m. one measurement
    #
    # The geometry lives in `mono_bar_geometry` so the production reader and
    # this driver run the SAME code. Two implementations of one measurement
    # drift, and this project has already paid for that: the prototype read
    # publication 397's WOMEN panel for weeks while the production reader was
    # never pointed at it, and the two disagreed about that panel's stroke, its
    # caps and its footprints with nothing to notice.
    #
    # REVERT: copy a function back into the driver instead of importing it. The
    # names still resolve, every other scenario still passes, and the two copies
    # start diverging on the next fix to either.
    print("\nthe driver and the shared module are the same measurement")
    shared = ["stroke_scale", "seed_support", "footprints_from_seed",
              "trace_extent", "trim_to_own_bar", "refine_footprint",
              "remote_support", "stem_band", "texture", "fill_identity",
              "fill_identities_by_figure", "rule_edge"]
    same = [n for n in shared if getattr(M, n, None) is getattr(G, n, object())]
    check("every geometry function the driver uses IS the shared one",
          len(same) == len(shared),
          repr([n for n in shared if n not in same]))
    check("and the vocabularies are one object, not two equal tuples",
          M.FILL_VOCABULARY is G.FILL_VOCABULARY
          and M.REMOTE_KINDS is G.REMOTE_KINDS
          and M.THRESHOLDS is G.THRESHOLDS)
    check("the shared module does not import the diagnostic corpus",
          not hasattr(G, "builtin_specs") and not hasattr(G, "load_specs"),
          "%r" % [n for n in ("builtin_specs", "load_specs") if hasattr(G, n)])
    # The panel loop is in the shared module too, taking an array and a
    # calibration rather than a spec - so the production reader can call it
    # without adopting this file's spec format, and cannot end up with its own
    # copy of the loop.
    check("the panel loop is shared, and the driver only supplies the spec",
          callable(getattr(G, "geometry_rows", None)), repr(dir(G)[:0]))
    check("and it names no series while it measures a panel",
          all(r.get("resolved_fill_pattern", "") == "" and
              r.get("identity_status") == "NOT_CALIBRATED"
              for r in M.measure_panel(spec1) if r.get("slot") is not None),
          repr([(r.get("slot"), r.get("identity_status")) for r
                in M.measure_panel(spec1)]))
    # An import of mark_readers here would close a cycle the moment the
    # production reader imports this module, which is why geometry_rows takes a
    # calibration object rather than tick points.
    check("the shared module imports no axis module, so no cycle can form",
          not [l for l in open(os.path.join(HERE, "mono_bar_geometry.py"))
               if l.startswith(("import ", "from ")) and "mark_readers" in l])

    # ------------------------------------------- 26o2. the two ink thresholds
    #
    # `threshold` and `stem_threshold` are manifest options for BAR_MONO. Every
    # helper in the geometry used to default them separately, so `geometry_rows`
    # could be handed one and read the figure at another - and a panel read at
    # one threshold and classified at a second is not one measurement.
    #
    # REVERT: drop the two arguments from geometry_rows and let each helper
    # default. Nothing on the corpus moves, because every figure this package
    # can reach is dark ink on white paper and 128 separates them all; a manifest
    # that sets either option changes nothing, silently.
    #
    # Drawn in GREY on purpose. Every other fixture here is pure black on pure
    # white, where any threshold between 1 and 254 reads the same figure - so
    # none of them can tell a threaded option from an ignored one.
    print("\nboth ink thresholds reach the measurement, not just the signature")
    g4 = Geometry(1.0)
    INK = 170
    grey = np.full(g4.shape, 255, np.uint8)
    grey[g4.r(100):g4.r(350), :] = 0                     # the usual trap band
    grey[g4.base:g4.base + g4.stroke, g4.x0 + 5:g4.x1 - 5] = INK
    a4, b4 = g4.slots[0]
    top4 = g4.top(40)
    grey[top4:g4.base, a4:b4 + 1] = INK
    mid = (a4 + b4) // 2
    grey[top4 - 26:top4, mid - 1:mid + 2] = INK          # a faint stem ...
    grey[top4 - 30:top4 - 26, mid - 24:mid + 25] = INK   # ... and its cap
    grey_path = write(grey, "greybar", TMP)
    grey_gray = M._gray(grey_path)
    grey_cal = MRX.AxisCalibration.from_points(
        [(0, g4.base), (100, g4.base - 100 * g4.ppu)])

    def grey_rows(**kw):
        return G.geometry_rows(
            grey_gray, [g4.x0, g4.x1, g4.y0, g4.y1], grey_cal,
            {"G": (g4.slots[0][0] + g4.slots[-1][1]) // 2}, ["SOLID"],
            g4.r(190), baseline=0.0, panel_id="P", identity_domain_id="F", **kw)

    check("at the default threshold this figure is not ink at all",
          [r.get("error") for r in grey_rows()] == ["STROKE_SCALE_UNRESOLVED"],
          repr([r.get("error") for r in grey_rows()]))
    faint = only(grey_rows(threshold=190))
    check("raising it reads the bar",
          abs(faint.get("value", -99) - 40.0) <= 1.0,
          repr((faint.get("value"), faint.get("error"))))
    check("and the error bar with it",
          "dispersion" in faint and abs(faint["dispersion"] - 10.0) < 2.0,
          repr(faint.get("dispersion")))
    # The second threshold is a second knob, not the same one: the stem is
    # traced at `stem_threshold`, so dropping it below the stem's own grey loses
    # the cap while the body is still read.
    no_stem = only(grey_rows(threshold=190, stem_threshold=120))
    check("stem_threshold is a different knob from threshold",
          no_stem.get("error") == "REMOTE_SUPPORT_UNRESOLVED"
          and kinds(no_stem) == ["UNRESOLVED_REMOTE_SUPPORT"],
          repr((no_stem.get("error"), kinds(no_stem))))
    check("and lowering it fails closed rather than dropping the error bar",
          "value" not in no_stem and "dispersion" not in no_stem,
          repr((no_stem.get("value"), no_stem.get("dispersion"))))

    # ------------------------------------------- 26o3. a bar too narrow to be one
    #
    # REVERT: `continue` past a bar that fails the width gate, which is what
    # `read_monochrome_bar_panel` does with the group-level form of this option.
    # The panel returns fewer records than it declared, with nothing saying why -
    # the failure NO_SEED_SUPPORT was added to close, re-entering through a
    # config file. See MIN_BAR_PX for what else changed about the option.
    print("\na bar narrower than the gate is refused, not dropped")
    g5 = Geometry(1.0)
    three = g5.blank()
    g5.outline(three, 0, 30)
    g5.stipple(three, 1, 45)
    g5.solid(three, 2, 60)
    three_path = write(three, "gated", TMP)
    three_gray = M._gray(three_path)
    three_cal = MRX.AxisCalibration.from_points(
        [(0, g5.base), (100, g5.base - 100 * g5.ppu)])

    def three_rows(**kw):
        return G.geometry_rows(
            three_gray, [g5.x0, g5.x1, g5.y0, g5.y1], three_cal,
            {"G": (g5.slots[0][0] + g5.slots[-1][1]) // 2},
            ["OPEN", "STIPPLED", "SOLID"], g5.r(190), baseline=0.0,
            panel_id="P", identity_domain_id="F", **kw)

    check("nothing in the fixture is near the default gate",
          all(r.get("error") != "BAR_TOO_NARROW" for r in three_rows()),
          repr([r.get("error") for r in three_rows()]))
    narrow = three_rows(min_bar_px=400)
    check("a gate above every bar refuses every bar",
          [r.get("error") for r in narrow] == ["BAR_TOO_NARROW"] * 3,
          repr([r.get("error") for r in narrow]))
    check("and the panel still returns one record per declared bar",
          len(narrow) == 3, "%d records" % len(narrow))
    check("each refusal carries the width it was measured at and the gate",
          all(r.get("footprint_width") and r.get("min_bar_px") == 400
              for r in narrow),
          repr([(r.get("footprint_width"), r.get("min_bar_px"))
                for r in narrow]))
    check("a refused bar keeps the identity fields every row carries",
          all(r["identity_status"] == "NOT_CALIBRATED"
              and r["fill_sample_status"] == "NOT_SAMPLED" for r in narrow),
          repr([(r["identity_status"], r["fill_sample_status"])
                for r in narrow]))
    check("the refusal is fail-closed: no value, no texture",
          not any("value" in r or "ink_mass" in r for r in narrow),
          repr([sorted(k for k in r if k in ("value", "ink_mass"))
                for r in narrow]))

    # ------------------------------------------- 26p. whose structure is it
    #
    # NEIGHBOUR_STRUCTURE is the one classification here that LIFTS a refusal,
    # so what it is bound to matters more than what any other kind is bound to.
    # It used to be bound to two things it should not have been.
    #
    # REVERT: `beyond = any(masked[r, -1] and margin[r, 0] for r in comp)`, the
    # row-by-row adjacency test this replaces. Scenario 26j still passes - the
    # overhang there really is the neighbour's - and all three cases below come
    # back NEIGHBOUR_STRUCTURE, which is the same answer for a structure that
    # ends in empty paper two pixels past the footprint and for a band that is
    # half something this bar has not accounted for.
    #
    # Driven at `remote_support` rather than through a figure, like 26k: the
    # discriminating cases need a component sitting ON the bar end with a
    # measured footprint and a declared neighbour, and every end-to-end way of
    # drawing that either feeds the structure to the stem tracer or moves the
    # scan start above it.
    print("\nink leaving this bar has to arrive somewhere for it to be excused")
    WX0, WX1, WY0, WY1 = 40, 440, 400, 800
    WBASE, WSTROKE = 720, 4
    OWN, NEXT_DOOR = (20, 219), (240, 339)       # window-relative footprints

    def neighbour_canvas(right_end, residual=False):
        img = np.full((860, 480), 255, np.uint8)
        img[100:350, :] = 0
        img[WBASE:WBASE + WSTROKE, WX0 + 5:WX1 - 5] = 0
        img[600:WBASE, 60:260] = 0                       # this bar, 200 px wide
        img[180:WBASE, 280:380] = 0                      # the bar next door
        img[595:600, WX0 + 180:WX0 + right_end + 1] = 0  # the structure
        if residual:
            # Same rows, not the same object: a sliver this bar has not
            # accounted for, sitting where the row band cannot tell it from the
            # structure beside it.
            img[595:600, WX0 + 150:WX0 + 170] = 0
        return img

    def remote_kinds(right_end, residual=False, neighbours=(NEXT_DOOR,)):
        return [r["kind"] for r in G.remote_support(
            neighbour_canvas(right_end, residual), [WX0, WX1, WY0, WY1],
            (WX0, WX1), OWN, 200, 320, WSTROKE, direction="UP",
            neighbours=neighbours)]

    check("a structure running from this bar into the next one is the next"
          " one's", remote_kinds(339) == ["NEIGHBOUR_STRUCTURE"],
          repr(remote_kinds(339)))
    check("the same structure stopping in the paper beside it is not",
          remote_kinds(225) == ["UNRESOLVED_REMOTE_SUPPORT"],
          repr(remote_kinds(225)))
    check("and a band that is half something else is not either",
          remote_kinds(339, residual=True) == ["UNRESOLVED_REMOTE_SUPPORT"],
          repr(remote_kinds(339, residual=True)))
    # A caller that has not said what is next door gets the refusal, not the
    # benefit of the doubt.
    check("with no neighbour declared there is nothing to be the neighbour's",
          remote_kinds(339, neighbours=()) == ["UNRESOLVED_REMOTE_SUPPORT"],
          repr(remote_kinds(339, neighbours=())))
    # And the caller that supplies them is `geometry_rows`, not the driver:
    # 26j reads a real figure and gets NEIGHBOUR_STRUCTURE, which it can only do
    # if the panel loop passes the other slots' footprints down.
    check("the panel loop is what tells it, so a real figure still resolves",
          "NEIGHBOUR_STRUCTURE" in kinds(mine), repr(kinds(mine)))

    # REVERT: use cv2.connectedComponents when cv2 is importable. It agrees
    # here, and on a machine without cv2 the same figure would be classified by
    # a different rule - which is not a classification.
    import cv2 as _cv2_probe                                       # noqa: E402
    _rng = np.zeros((40, 60), bool)
    for _y, _x in ((3, 4), (3, 5), (4, 5), (10, 10), (11, 11), (12, 12),
                   (20, 0), (20, 59), (30, 30), (31, 29), (31, 31), (39, 0)):
        _rng[_y, _x] = True
    _mine = G._components_2d(_rng)
    _n, _theirs = _cv2_probe.connectedComponents(_rng.astype(np.uint8),
                                                 connectivity=8)
    _pairs = {(int(a), int(b)) for a, b in zip(_mine[_rng], _theirs[_rng])}
    check("the hand-written labelling is the same labelling cv2 computes",
          len(_pairs) == len({a for a, _b in _pairs})
          and len(_pairs) == len({b for _a, b in _pairs}) == _n - 1,
          "%d objects against %d, mapping %r" % (len({a for a, _b in _pairs}),
                                                 _n - 1, sorted(_pairs)))

    # ------------------------------------------- 26n. the anonymous grain
    #
    # `fills` is the group's DECLARATION - a MULTISET of the patterns the panel
    # is supposed to hold - and the order it is written in is a human's
    # left-to-right reading of the printed figure. A per-slot copy of it inside
    # the record is a series named by where the bar sits, which is the one
    # inference this package refuses, and it made the whole record stream depend
    # on that order.
    #
    # REVERT: put `declared=fills[k]` back on the record in `geometry_rows`, and
    # read it back in `fill_identity`. Every other scenario in this file still
    # passes - the identity was already decided by ink and structure, so no NAME
    # moves - and these three stop being the same records.
    print("\nthe records do not depend on the order the fills are listed")
    g = Geometry(1.0)
    img = g.blank()
    g.outline(img, 0, 30)
    g.stipple(img, 1, 45)
    g.solid(img, 2, 60)
    perm_path = write(img, "perm", TMP)
    perm_cal = MRX.AxisCalibration.from_points(
        [(0, g.base), (100, g.base - 100 * g.ppu)])
    perm_gray = M._gray(perm_path)

    def perm_rows(order):
        return G.geometry_rows(perm_gray, [g.x0, g.x1, g.y0, g.y1], perm_cal,
                               {"G": (g.slots[0][0] + g.slots[-1][1]) // 2},
                               list(order), g.r(190), baseline=0.0,
                               panel_id="P", identity_domain_id="F")

    orders = (["OPEN", "STIPPLED", "SOLID"], ["SOLID", "OPEN", "STIPPLED"],
              ["STIPPLED", "SOLID", "OPEN"])
    streams = [perm_rows(o) for o in orders]
    check("the panel measures three bars whichever way the spec lists them",
          all(len(s) == 3 and all("value" in r for r in s) for s in streams),
          repr([[r.get("error") for r in s] for s in streams]))
    differs = [k for k in set().union(*[set(r) for s in streams for r in s])
               if any(a.get(k) != b.get(k)
                      for a, b in zip(streams[0], streams[1])
                      ) or any(a.get(k) != b.get(k)
                               for a, b in zip(streams[0], streams[2]))]
    check("and the records are IDENTICAL, field for field, not merely equivalent",
          not differs, "fields that moved: %r" % sorted(differs))
    check("what every record carries is the group's sorted multiset",
          all(r["declared_group_patterns"] == ["OPEN", "SOLID", "STIPPLED"]
              and r["declared_group_size"] == 3
              for s in streams for r in s),
          repr([r.get("declared_group_patterns") for r in streams[1]]))
    for stream, order in zip(streams, orders):
        M.fill_identities_by_figure(stream)
    named = [{(r["slot"]): r["resolved_fill_pattern"] for r in s} for s in streams]
    check("the three bars are named from their ink, the same way each time",
          named[0] == named[1] == named[2] == {0: "OPEN", 1: "STIPPLED",
                                               2: "SOLID"},
          repr(named))

    # REVERT: have `fill_identity` read a per-slot declared field again. This is
    # the behavioural half of the same fix: `spec_fill` is fixture truth that
    # the driver staples on AFTER the measurement, and if the identity can see
    # it then the spec is deciding what the figure says. Scrambling it here must
    # change nothing at all.
    scrambled = M.measure_panel(g.spec(perm_path,
                                       ["OPEN", "STIPPLED", "SOLID"]))
    M.fill_identities_by_figure(scrambled)
    honest = {(r["group"], r["slot"]): r["resolved_fill_pattern"]
              for r in scrambled}
    lying = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))
    for r in lying:
        r["spec_fill"] = "SOLID"                 # every slot, deliberately wrong
    M.fill_identities_by_figure(lying)
    check("a wrong `spec_fill` on every record changes no identity",
          {(r["group"], r["slot"]): r["resolved_fill_pattern"]
           for r in lying} == honest and honest[("G", 0)] == "OPEN",
          repr(honest))

    # REVERT: fall back to per-slot declarations when the group-level ones are
    # missing. The declaration is then assembled from whatever arrived, so two
    # records disagreeing about what their own group holds is not a finding -
    # it is just a longer list.
    print("\na group whose records disagree about their own declaration")
    split = [dict(r) for r in M.measure_panel(
        g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))]
    split[1]["declared_group_patterns"] = ["OPEN", "OPEN", "SOLID"]
    _i, verdict_s = M.fill_identity(split)
    entry = verdict_s["truncated_groups"].get(str(("scale1", "G")), {})
    check("two declarations for one group calibrate nothing",
          verdict_s["complete_groups"] == 0
          and entry.get("declaration") == "INCONSISTENT",
          repr(verdict_s["truncated_groups"]))
    bare = [dict(r) for r in split]
    for r in bare:
        r.pop("declared_group_size", None)
        r.pop("declared_group_patterns", None)
    _i, verdict_b = M.fill_identity(bare)
    check("and no declaration at all is a refusal, not an empty one",
          verdict_b["status"] == "NOT_ENOUGH_COMPLETE_GROUPS"
          and verdict_b["truncated_groups"].get(
              str(("scale1", "G")), {}).get("declaration") == "MISSING",
          repr(verdict_b["truncated_groups"]))

    # ------------------------------------------- 26o. one row shape
    #
    # REVERT: build each refusal with its own `dict(...)` again. Every scenario
    # that reads a refusal still passes, because each reads the one field it
    # cares about. What breaks is the consumer: `fill_identities_by_figure`
    # buckets on `identity_domain_id`, and a refusal that carried none fell back to the
    # PANEL id - so one two-panel figure with one bad panel produced TWO
    # verdicts, the second computed from the panel that had already refused.
    print("\nevery row has the same shape, refusal or reading")
    naked = np.full((860, 480), 255, np.uint8)
    naked[100:350, :] = 0                            # no baseline rule at all
    no_rule = M.measure_panel(spec(write(naked, "norule", TMP), ["SOLID"]))
    img = blank()
    solid(img, 0, 40)
    a, b = SLOTS[0]
    img[BASE + STROKE:BASE + STROKE + 40 * 3, a:b + 1] = 0    # and one below it
    both_ways = M.measure_panel(spec(write(img, "twoways", TMP), ["SOLID"]))
    img = blank()
    solid(img, 0, 60)
    empty = M.measure_panel(spec(write(img, "empty2", TMP), ["SOLID"],
                                 anchor=X1 - 20, window=15))
    img = blank()
    for k in range(3):
        solid(img, k, 40 + 10 * k)
    clip = M.measure_panel(spec(write(img, "clip2", TMP), ["SOLID"] * 3,
                                window=150))
    shapes = dict(STROKE_SCALE_UNRESOLVED=no_rule,
                  BAR_DIRECTION_UNRESOLVED=both_ways,
                  NO_SEED_SUPPORT=empty, GROUP_WINDOW_CLIPPED=clip)
    BASE_FIELDS = ("figure", "identity_domain_id", "group", "slot",
                   "declared_group_size", "declared_group_patterns",
                   "fill_sample_status", "identity_status",
                   "resolved_fill_pattern")
    for want, rows_ in sorted(shapes.items()):
        check("%s is reachable and is the error it says it is" % want,
              rows_ and rows_[0].get("error") == want,
              repr([r.get("error") for r in rows_]))
        missing = [f for f in BASE_FIELDS if f not in (rows_[0] if rows_ else {})]
        check("%s carries every field a reading carries" % want,
              not missing, "missing %r" % missing)
        check("%s belongs to a named figure, so it buckets with its siblings"
              % want,
              bool(rows_) and rows_[0].get("identity_domain_id") == rows_[0].get("figure"),
              repr((rows_[0].get("figure"), rows_[0].get("identity_domain_id"))
                   if rows_ else None))
    good = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))
    check("and a reading carries nothing a refusal does not",
          not [f for f in BASE_FIELDS if f not in good[0]],
          repr(sorted(good[0])))
    # The defect itself, end to end: ONE figure of two panels measured through
    # the shared entry point with the figure named, one panel refusing outright.
    # Nothing here re-labels a record afterwards, because re-labelling is what
    # hid the defect - the caller supplies `identity_domain_id` and the refusal has to
    # keep it on its own.
    two = G.geometry_rows(M._gray(write(naked, "norule2", TMP)),
                          [X0, X1, Y0, Y1],
                          MRX.AxisCalibration.from_points(
                              [tuple(t) for t in TICKS]),
                          {"G": ANCHOR}, ["SOLID"], 190, baseline=0.0,
                          panel_id="panel_bad", identity_domain_id="one_figure")
    ok_rows = G.geometry_rows(perm_gray, [g.x0, g.x1, g.y0, g.y1], perm_cal,
                              {"G": (g.slots[0][0] + g.slots[-1][1]) // 2},
                              ["OPEN", "STIPPLED", "SOLID"], g.r(190),
                              baseline=0.0, panel_id="panel_ok",
                              identity_domain_id="one_figure")
    verdicts_two = M.fill_identities_by_figure(two + ok_rows)
    check("a panel that refused does not become a figure of its own",
          set(verdicts_two) == {"one_figure"}, repr(sorted(verdicts_two)))
    check("and its refusal row is not mistaken for an unnamed bar",
          two[0].get("identity_status") == "NOT_CALIBRATED"
          and two[0].get("fill_sample_status") == "NOT_SAMPLED",
          repr((two[0].get("identity_status"),
                two[0].get("fill_sample_status"))))

    # ------------------------------------------- 26s. read at one threshold
    #
    # The threshold reached the GEOMETRY and stopped there. `texture` reports
    # four fixed blocks - t96, t128, t160, t192 - and `_sample` took the
    # structural half of the identity from `t128` whatever the caller asked
    # for. So a figure read at 190 was CLASSIFIED at 128, which is the thing
    # threading the option through was supposed to stop.
    #
    # A grey hatch has ink at 190 and none at 128, so it comes back
    # `rows_all_inked = False` and HATCHED becomes structurally impossible for
    # it. Inside a complete group that is a refusal - the whole group goes
    # unassignable. Against prototypes another group already established it is
    # worse: the bar is matched on ink alone against whichever pattern remains
    # structurally possible, which is a RENAMING.
    #
    # REVERT: `rows_all_inked = float(rec["t128"]["row_coverage_min"]) > 0.0`
    # in `_sample`. Nothing on the corpus moves - every figure this package can
    # reach is black on white, where the identity block IS t128 - and both
    # scenarios below break.
    print("\nthe identity is decided at the threshold the panel was read at")
    g7 = Geometry(1.0)
    GREY = 170

    def grey_panel(name, units=(30, 45, 60), level=GREY, short=None, pitch=9):
        img = g7.blank()
        g7.outline(img, 0, units[0])
        g7.hatch(img, 1, units[1], pitch=pitch)
        g7.stipple(img, 2, units[2] if short is None else short)
        if level != 0:
            # Everything the panel drew, in grey. The baseline rule included,
            # so nothing here is a two-tone figure that only half exists at 128.
            img[img == 0] = level
            img[g7.r(100):g7.r(350), :] = 0        # except the trap band
        return write(img, name, TMP)

    grey_spec = g7.spec(grey_panel("greyfig"), ["OPEN", "HATCHED", "STIPPLED"])

    def grey_identity(threshold):
        rows_ = G.geometry_rows(
            M._gray(grey_spec["path"]), grey_spec["box"],
            MRX.AxisCalibration.from_points(
                [tuple(t) for t in grey_spec["ticks"]]),
            grey_spec["anchors"], grey_spec["fills"], grey_spec["group_window"],
            baseline=0.0, threshold=threshold, panel_id="grey", identity_domain_id="grey")
        verdicts = M.fill_identities_by_figure(rows_)
        return rows_, verdicts["grey"]

    at_190, v190 = grey_identity(190)
    check("the grey panel is measured at 190",
          all("value" in r for r in at_190),
          repr([r.get("error") for r in at_190]))
    check("t128 sees no interior in it at all, which is the trap",
          all(r["t128"]["row_coverage_min"] == 0.0 for r in at_190),
          repr([r["t128"]["row_coverage_min"] for r in at_190]))
    check("the identity block does see one, because it is read at 190",
          [r["identity_threshold"] for r in at_190] == [190] * 3
          and [r["identity_rows_all_inked"] for r in at_190] == [False, True,
                                                                 False],
          repr([(r["identity_threshold"], r["identity_rows_all_inked"])
                for r in at_190]))
    check("so the group assigns, and the hatch is named HATCHED",
          v190["status"] == "DIRECT_ONLY"
          and [r["resolved_fill_pattern"] for r in at_190]
          == ["OPEN", "HATCHED", "STIPPLED"],
          "%r %r" % (v190["status"],
                     [r["resolved_fill_pattern"] for r in at_190]))

    # And the renaming, which is the case that returns an answer rather than
    # withholding one. Two black groups establish the vocabulary; a partial grey
    # group is then matched against it.
    print("\na grey hatch is not renamed against another group's prototypes")
    proto = []
    for name, units in (("blk_a", (30, 45, 60)), ("blk_b", (33, 48, 63))):
        img = g7.blank()
        g7.outline(img, 0, units[0])
        g7.hatch(img, 1, units[1])
        g7.stipple(img, 2, units[2])
        got = G.geometry_rows(
            M._gray(write(img, name, TMP)),
            [g7.x0, g7.x1, g7.y0, g7.y1],
            MRX.AxisCalibration.from_points([(0, g7.base),
                                             (100, g7.base - 100 * g7.ppu)]),
            {"G": (g7.slots[0][0] + g7.slots[-1][1]) // 2},
            ["OPEN", "HATCHED", "STIPPLED"], g7.r(190), baseline=0.0,
            threshold=190, panel_id=name, identity_domain_id="mixed")
        proto.extend(got)
    partial = G.geometry_rows(
        # pitch 18 at grey 170 puts this hatch's INK inside the black
        # STIPPLE's prototype range - which is the whole point. Its structure
        # is the only thing that says it is not one, and the structure is the
        # thing the fixed t128 could not see.
        M._gray(grey_panel("greypart", short=4, pitch=18)),
        [g7.x0, g7.x1, g7.y0, g7.y1],
        MRX.AxisCalibration.from_points([(0, g7.base),
                                         (100, g7.base - 100 * g7.ppu)]),
        {"G": (g7.slots[0][0] + g7.slots[-1][1]) // 2},
        ["OPEN", "HATCHED", "STIPPLED"], g7.r(190), baseline=0.0,
        threshold=190, panel_id="grey_partial", identity_domain_id="mixed")
    mixed_rows = proto + partial
    v_mixed = M.fill_identities_by_figure(mixed_rows)["mixed"]
    check("the two black groups establish a reusable vocabulary",
          v_mixed["status"] == "ESTABLISHED" and v_mixed["complete_groups"] == 2,
          "%r over %d" % (v_mixed["status"], v_mixed["complete_groups"]))
    grey_hatch = next(r for r in partial if r.get("slot") == 1)
    check("the grey bar in slot 1 really is a hatch - no interior row is blank",
          grey_hatch["identity_rows_all_inked"]
          and grey_hatch["t128"]["row_coverage_min"] == 0.0,
          repr((grey_hatch["identity_rows_all_inked"],
                grey_hatch["t128"]["row_coverage_min"])))
    check("its ink lands squarely inside the STIPPLE prototype range",
          v_mixed["prototypes"]["STIPPLED"][0] - 0.01
          <= grey_hatch["ink_mass"]
          <= v_mixed["prototypes"]["STIPPLED"][1] + 0.01,
          "%r against %r" % (grey_hatch["ink_mass"],
                             v_mixed["prototypes"]["STIPPLED"]))
    check("and it is still never called STIPPLED",
          grey_hatch["resolved_fill_pattern"] in ("", "HATCHED"),
          repr(grey_hatch["resolved_fill_pattern"]))

    # ------------------------------------------- 26r. two groups is not enough
    #
    # `prototype_ready` said "at least two complete groups AND a non-zero
    # spread" in the docstring and `len(complete) >= 2` in the code. The
    # difference is a figure whose two groups reproduce each other EXACTLY -
    # every sample equal, every tile spread zero - which has a floor of zero,
    # and matching an incomplete group against a range of zero width with a
    # tolerance of zero is the same luck the group count was added to prevent,
    # reached from the other side.
    #
    # REVERT: `prototype_ready = len(complete) >= 2`. The figure below reports
    # ESTABLISHED and offers reusable prototypes that cannot tolerate a single
    # unit of drift, and nothing else in the suite notices, because every other
    # fixture draws its groups at different heights.
    print("\ntwo groups that agree perfectly have not shown how much they vary")
    g6 = Geometry(1.0)
    flat_rows = []
    for name in ("flat_a", "flat_b"):
        img = g6.blank()
        g6.outline(img, 0, 40)
        g6.solid(img, 1, 40)                 # identical in both groups
        got = M.measure_panel(g6.spec(write(img, name, TMP), ["OPEN", "SOLID"]))
        for r in got:
            r["figure"], r["identity_domain_id"] = name, "flat_figure"
        flat_rows.extend(got)
    _i6, verdict6 = M.fill_identity(flat_rows)
    check("the two groups really are identical to the last decimal",
          len({(r["ink_mass"], r["ink_mass_tile_spread"]) for r in flat_rows}) == 2,
          repr(sorted((r["ink_mass"], r["ink_mass_tile_spread"])
                      for r in flat_rows)))
    check("two complete groups, and still not a reusable vocabulary",
          verdict6["complete_groups"] == 2
          and not verdict6["prototype_ready"]
          and verdict6["status"] == "DIRECT_ONLY",
          "%r over %d groups" % (verdict6["status"],
                                 verdict6["complete_groups"]))
    check("the four bars they hold are still named from their own relations",
          len(_i6) == 4, repr(_i6))

    # ------------------------------------------- 26q. the written-down row
    #
    # `mono_bar_geometry.csv` is what a batch writes between measuring a panel
    # and naming its series, and it has to survive being read back by something
    # that is not this process.
    #
    # REVERT: hand a record straight to a CSV writer. Every scenario above still
    # passes, because none of them writes a file; the artifact then holds
    # Python `repr` of nested dicts, which has no parser, depends on dict
    # ordering and float repr, and moves a hash taken over it when the same
    # numbers are written by a different interpreter.
    print("\nthe row a batch writes down is one text for one measurement")
    written = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))
    art = G.artifact_rows(written)
    check("the artifact has exactly the declared columns, in order",
          all(list(rowx) == list(G.GEOMETRY_ARTIFACT_COLUMNS) for rowx in art),
          repr(list(art[0])))
    flat = [c for c in G.GEOMETRY_ARTIFACT_COLUMNS
            if any(not isinstance(rowx[c], (str, int, float)) for rowx in art)]
    check("no cell holds a list or a dict - a CSV cannot carry one",
          not flat, "not flat: %r" % flat)
    back = [json.loads(rowx["Diagnostics_JSON"]) for rowx in art]
    check("and the nested half round-trips as JSON",
          all(isinstance(d, dict) and "remote" in d for d in back),
          repr(sorted(back[0])[:6]))
    check("nothing measured is dropped between the record and the row",
          all(not (set(rec) - set(d) - {"footprint"} -
                   {f for f, _c in G.ARTIFACT_FIELD_COLUMNS} -
                   set(G.UNHASHED_FIELDS))
              for rec, d in zip(written, back)),
          repr([sorted(set(rec) - set(d) - {"footprint"}
                       - {f for f, _c in G.ARTIFACT_FIELD_COLUMNS}
                       - set(G.UNHASHED_FIELDS))
                for rec, d in zip(written, back)]))
    # REVERT: json.dumps(diagnostics) without sort_keys and separators. The two
    # dicts below hold the same measurement and produce different text, so the
    # same numbers written twice hash differently.
    check("canonical JSON does not depend on the order the keys were built in",
          G.canonical_json({"b": 1, "a": [2, 3]})
          == G.canonical_json({"a": [2, 3], "b": 1})
          == '{"a":[2,3],"b":1}',
          repr(G.canonical_json({"b": 1, "a": [2, 3]})))
    # REVERT: json.dumps(..., default=str). A numpy number then serialises as a
    # QUOTED STRING, so a record built with numpy scalars and the same record
    # built with Python floats hash differently while printing the same numbers.
    check("a numpy number is written as the number it is",
          G.canonical_json({"v": np.float64(1.5), "n": np.int64(3),
                            "a": np.array([1, 2])}) == '{"a":[1,2],"n":3,"v":1.5}',
          repr(G.canonical_json({"v": np.float64(1.5), "n": np.int64(3),
                                 "a": np.array([1, 2])})))

    # REVERT: hash the whole record. `fill_identities_by_figure` writes identity
    # onto the record IN PLACE, so the hash then changes the moment a series is
    # named - and the question it exists to answer, "is this the same
    # measurement the reviewer approved", stops having one.
    print("\nthe row hash is of the measurement, and naming is not measuring")
    before = [rec["geometry_row_sha256"] for rec in written]
    check("every row is stamped at measurement time",
          all(len(h) == 64 for h in before), repr(before[:1]))
    M.fill_identities_by_figure(written)
    check("naming the series does not change any of them",
          [rec["geometry_row_sha256"] for rec in written] == before
          and all(rec["identity_status"] == "RESOLVED" for rec in written),
          repr([(rec["identity_status"], rec["geometry_row_sha256"][:8])
                for rec in written]))
    check("and recomputing after naming still agrees",
          [G.geometry_row_sha256(rec) for rec in written] == before)
    again = M.measure_panel(g.spec(perm_path, ["SOLID", "OPEN", "STIPPLED"]))
    check("the same panel measured again hashes the same, in any fill order",
          [rec["geometry_row_sha256"] for rec in again] == before,
          repr([rec["geometry_row_sha256"][:8] for rec in again]))
    moved = dict(written[0])
    moved["value"] = moved["value"] + 0.001
    check("a measurement that moved hashes differently",
          G.geometry_row_sha256(moved) != before[0])
    # A human resolving a fill in identity_resolution.csv must not disturb it
    # either, which is the same property from the other side.
    human = dict(written[0], identity_status="RESOLVED",
                 resolved_fill_pattern="HATCHED")
    check("nor does a human overriding what the figure said",
          G.geometry_row_sha256(human) == before[0])

    # REVERT: `out["Geometry_Row_SHA256"] = record.get("geometry_row_sha256")
    # or geometry_row_sha256(record)`. The hash is then copied out of the record
    # while the columns are filled from the record as it now stands, so a row
    # edited after it was stamped is written with a changed Mean and an
    # unchanged hash - a file attesting to a measurement it does not contain,
    # which is worse than carrying no hash at all. The scenario above does not
    # catch it: it calls the hash function directly and never writes a row.
    print("\nthe artifact refuses to write a row that moved after it was stamped")
    for field, value in (("value", written[0]["value"] + 0.001),
                         ("footprint", [0, 1]),
                         ("ink_mass", 0.5)):
        edited = dict(written[0])
        edited[field] = value
        try:
            G.artifact_row(edited)
        except ValueError as exc:
            check("editing %s after the stamp is refused" % field,
                  "MODIFIED_AFTER_STAMP" in str(exc), str(exc))
        else:
            check("editing %s after the stamp is refused" % field, False,
                  "it wrote the row")
    check("naming a series is not editing it, so the row still writes",
          G.artifact_row(written[0])["Geometry_Row_SHA256"] == before[0]
          and written[0]["identity_status"] == "RESOLVED",
          repr(written[0]["identity_status"]))
    check("and the driver's fixture truth is not part of the measurement",
          G.artifact_row(dict(written[0], spec_fill="NONSENSE"))[
              "Geometry_Row_SHA256"] == before[0])

    # REVERT: `if stamped and stamped != actual` with no `not stamped` branch -
    # an unstamped row is then hashed as it now stands. `geometry_rows` stamps
    # every row it returns, so an unstamped row is a row that LOST its stamp,
    # and hashing whatever it now says launders an edit into a canonical
    # artifact by deleting one field.
    print("\nand refuses a row whose stamp has gone missing")
    # Measured and not yet named, because a row whose measurement moved also
    # breaks the identity attestation below - and this scenario is about the
    # stamp, not about that.
    unnamed = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))
    laundered = {k: v for k, v in unnamed[0].items()
                 if k != "geometry_row_sha256"}
    laundered["value"] = laundered["value"] + 1.0
    try:
        G.artifact_row(laundered)
    except ValueError as exc:
        check("deleting the stamp does not launder an edit",
              "UNSTAMPED" in str(exc), str(exc))
    else:
        check("deleting the stamp does not launder an edit", False,
              "it wrote the row")
    check("a migration utility can still read an older row, by saying so",
          G.artifact_row(laundered, allow_unstamped=True)["Mean"]
          == laundered["value"])
    check("and a batch run does not, because that is the default",
          G.artifact_rows.__defaults__ == (False, False)
          and "allow_unstamped" in G.artifact_rows.__code__.co_varnames,
          repr(G.artifact_rows.__defaults__))

    # REVERT: leave the two flags to whoever writes the file. `run_batch` then
    # has to remember `require_auto_identity=True`, and the run that forgets
    # writes a perfectly valid geometry file in which every Auto_Identity_Status
    # says NOT_CALIBRATED - for a batch that resolved the identities in memory a
    # moment later and wrote them nowhere. The stages are naturally listed in
    # the order that produces exactly that.
    print("\nthe batch writer has no flag to forget")
    unresolved = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED",
                                                    "SOLID"]))
    check("writing the geometry file before the figure is answered is refused",
          _raises(lambda: G.canonical_artifact_rows(unresolved),
                  "AUTO_IDENTITY_MISSING"),
          repr([r.get("identity_status") for r in unresolved]))
    check("a diagnostic dump of the same rows is still allowed",
          [r["Auto_Identity_Status"] for r in G.artifact_rows(unresolved)]
          == ["NOT_CALIBRATED"] * 3)
    M.fill_identities_by_figure(unresolved)
    resolved_rows = G.canonical_artifact_rows(unresolved)
    check("and after the figure has answered, every row carries both hashes",
          all(len(r["Domain_Identity_SHA256"]) == 64
              and len(r["Auto_Identity_SHA256"]) == 64
              for r in resolved_rows),
          repr([(r["Domain_Identity_SHA256"][:8],
                 r["Auto_Identity_SHA256"][:8]) for r in resolved_rows]))
    check("including the rows the figure could not name",
          all(r["Auto_Identity_SHA256"] for r in G.canonical_artifact_rows(
              [dict(x, identity_status="UNRESOLVED_NO_FILL",
                    resolved_fill_pattern="",
                    auto_identity_sha256=G.auto_identity_sha256(
                        dict(x, identity_status="UNRESOLVED_NO_FILL",
                             resolved_fill_pattern="")))
               for x in unresolved])))

    # REVERT: treat a row with no `auto_identity_sha256` as pre-identity. A
    # caller that clears the answer and leaves its provenance behind - or takes
    # the answer off the figure's verdict without attesting the row - then
    # writes a file that cannot say whether auto resolution reached this row.
    print("\nhalf an auto identity is not an auto identity")
    half = dict(unresolved[0])
    del half["auto_identity_sha256"]
    half["identity_status"], half["resolved_fill_pattern"] = "NOT_CALIBRATED", ""
    check("an answer deleted with its provenance left behind is refused",
          _raises(lambda: G.artifact_row(half), "AUTO_IDENTITY_PARTIAL"),
          "it wrote the row")
    check("and the row that has genuinely never been resolved still writes",
          G.artifact_row(M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED",
                                                            "SOLID"]))[0]
                         )["Auto_Identity_Status"] == "NOT_CALIBRATED")

    # REVERT: let an unstamped row keep its attestation through migration. The
    # attestation names a Geometry_Row_SHA256 the row no longer has, while the
    # column is filled with the hash recomputed at write time - so the file
    # passes the writer and fails a reader recomputing from the columns.
    carried = {k: v for k, v in unresolved[0].items()
               if k != "geometry_row_sha256"}
    check("a migrated row may not carry an attestation of a hash it lost",
          _raises(lambda: G.artifact_row(carried, allow_unstamped=True),
                  "AUTO_IDENTITY_ON_UNSTAMPED_ROW"),
          "it wrote the row")

    # REVERT: drop the identity_source guard from artifact_row. A caller that
    # applies identity_resolution.csv by overwriting resolved_fill_pattern and
    # re-emitting the geometry file then records a HUMAN decision in a column
    # called Auto_Fill_Pattern - an audit trail saying the machine decided
    # something a person did, in the one file that is supposed to hold what the
    # FIGURE said.
    print("\nthe geometry file holds what the figure said, not what a person did")
    check("the rows the figure named say so",
          all(r.get("identity_source") == "AUTO" for r in written),
          repr({r.get("identity_source") for r in written}))
    reviewed = dict(written[0], identity_source="HUMAN",
                    resolved_fill_pattern="HATCHED")
    try:
        G.artifact_row(reviewed)
    except ValueError as exc:
        check("a human resolution is refused by the geometry artifact",
              "identity_resolution.csv" in str(exc), str(exc))
    else:
        check("a human resolution is refused by the geometry artifact", False,
              "it wrote the row")
    check("and HUMAN is a declared source, not an ad-hoc string",
          G.IDENTITY_SOURCES == ("AUTO", "HUMAN"), repr(G.IDENTITY_SOURCES))

    # REVERT: check `identity_source` and nothing else. That stops a caller
    # that is TELLING THE TRUTH, which is not the caller that goes wrong. The
    # join that overwrites the pattern and forgets to move the source is the
    # one that files a person's decision under Auto_Fill_Pattern, and a source
    # field it never touched cannot detect it.
    print("\nand an auto identity that no longer matches what the figure said")
    for field, value in (("resolved_fill_pattern", "HATCHED"),
                         ("identity_status", "AMBIGUOUS")):
        forged = dict(written[0])
        forged[field] = value                # source left at AUTO, as the bug
        try:                                 # leaves it
            G.artifact_row(forged)
        except ValueError as exc:
            check("overwriting %s behind the resolver's back is caught" % field,
                  "AUTO_IDENTITY_MODIFIED" in str(exc), str(exc))
        else:
            check("overwriting %s behind the resolver's back is caught" % field,
                  False, "it wrote the row")
    invented = dict(written[0])
    del invented["auto_identity_sha256"]
    check("an identity nobody attested to is refused as well",
          _raises(lambda: G.artifact_row(invented), "AUTO_IDENTITY_UNATTESTED"),
          "an unattested identity was written")
    fresh = M.measure_panel(g.spec(perm_path, ["OPEN", "STIPPLED", "SOLID"]))
    check("a row measured and not yet named needs no attestation",
          G.artifact_row(fresh[0])["Auto_Identity_Status"] == "NOT_CALIBRATED",
          repr(fresh[0].get("auto_identity_sha256")))
    # The attestation binds the answer to the ROW and to the FIGURE, so an
    # identity cannot be carried across from a bar that earned it.
    swapped = dict(written[1], auto_identity_sha256=written[0][
        "auto_identity_sha256"])
    check("nor can one bar's name be moved onto another",
          _raises(lambda: G.artifact_row(swapped), "AUTO_IDENTITY_MODIFIED"),
          "a transplanted identity was written")
    other_figure = dict(written[0], domain_identity_sha256="0" * 64)
    check("nor can it be carried over from another figure's verdict",
          _raises(lambda: G.artifact_row(other_figure),
                  "AUTO_IDENTITY_MODIFIED"),
          "a transplanted verdict was written")
    check("and both hashes are columns, so a reader can recompute them",
          {"Domain_Identity_SHA256", "Auto_Identity_SHA256"}
          <= set(G.GEOMETRY_ARTIFACT_COLUMNS), repr(G.GEOMETRY_ARTIFACT_COLUMNS))

    # REVERT: json.dumps without allow_nan=False, and `return str(obj)` at the
    # end of _plain. Python writes `NaN` into what it calls JSON and no other
    # language's parser reads it back; and a set or a Path is folded into the
    # hash as text that looks like data, where the first disagreement between
    # two runs would be a memory address.
    print("\nwhat cannot be written down canonically is not written down")
    for bad in (float("nan"), float("inf")):
        try:
            G.canonical_json({"v": bad})
        except ValueError:
            check("%r is refused rather than written as JSON" % bad, True)
        else:
            check("%r is refused rather than written as JSON" % bad, False,
                  G.canonical_json({"v": bad}))
    check("a non-string dictionary key is refused too",
          _raises_type(lambda: G.canonical_json({1: "numeric", "1": "string"})),
          "1 and \"1\" were folded into one key")
    for bad in ({1, 2}, object()):
        try:
            G.canonical_json({"v": bad})
        except TypeError as exc:
            check("a %s is refused rather than stringified"
                  % type(bad).__name__, "cannot write" in str(exc), str(exc))
        else:
            check("a %s is refused rather than stringified"
                  % type(bad).__name__, False, G.canonical_json({"v": bad}))

    # ------------------------------------------- 26t. read it back
    #
    # A writer nobody can read back is a writer nobody can check. The eighteen
    # denormalized columns cannot carry the record on their own: a CSV holds
    # text, so `cap_px_image` is written `1189` whether the record held the
    # integer 1189 or the float 1189.0, and the canonical JSON of those two is
    # not the same string. Measured on publication 127 that is what happened,
    # on the first row of the file - the reader recomputed a different hash for
    # a file it had just been handed.
    #
    # REVERT: drop `Anonymous_Record_JSON` and rebuild the record from the
    # eighteen columns. Every writer scenario above still passes, because none
    # of them reads a file back.
    print("\nthe file can be read back, and the hash recomputed from it")
    g8 = Geometry(1.0)

    def zoo_rows(panel_id, draw, fills, **kw):
        img = g8.blank()
        draw(img)
        return G.geometry_rows(
            M._gray(write(img, panel_id, TMP)),
            [g8.x0, g8.x1, g8.y0, g8.y1],
            MRX.AxisCalibration.from_points(
                [(0, g8.base), (100, g8.base - 100 * g8.ppu)]),
            kw.pop("anchors", {"G": (g8.slots[0][0] + g8.slots[-1][1]) // 2}),
            fills, kw.pop("window", g8.r(190)), baseline=0.0,
            panel_id=panel_id, identity_domain_id="zoo", **kw)

    def three(img):
        g8.outline(img, 0, 30)
        g8.stipple(img, 1, 45)
        g8.solid(img, 2, 60)

    def with_cap(img):
        g8.solid(img, 0, 60)
        errorbar(img, 0, 60, length=g8.r(30))

    def one_short(img):
        g8.outline(img, 0, 30)
        g8.stipple(img, 1, 45)
        g8.solid(img, 2, 4)                     # too small to sample a fill

    zoo = []
    zoo += zoo_rows("zoo_plain", three, ["OPEN", "STIPPLED", "SOLID"])
    zoo += zoo_rows("zoo_cap", with_cap, ["SOLID"])
    zoo += zoo_rows("zoo_short", one_short, ["OPEN", "STIPPLED", "SOLID"])
    zoo += zoo_rows("zoo_narrow", three, ["OPEN", "STIPPLED", "SOLID"],
                    min_bar_px=400)
    zoo += zoo_rows("zoo_empty", lambda img: g8.solid(img, 0, 60),
                    ["SOLID"], anchors={"G": g8.x1 - 20}, window=15)
    bare = np.full(g8.shape, 255, np.uint8)
    bare[g8.r(100):g8.r(350), :] = 0
    zoo += G.geometry_rows(
        M._gray(write(bare, "zoo_norule", TMP)), [g8.x0, g8.x1, g8.y0, g8.y1],
        MRX.AxisCalibration.from_points([(0, g8.base),
                                         (100, g8.base - 100 * g8.ppu)]),
        {"G": (g8.slots[0][0] + g8.slots[-1][1]) // 2}, ["SOLID"], g8.r(190),
        baseline=0.0, panel_id="zoo_norule", identity_domain_id="zoo")
    kinds_present = {r.get("error") or "READING" for r in zoo}
    check("the fixture covers every row type a real file holds",
          {"READING", "BAR_TOO_SMALL_TO_SAMPLE", "BAR_TOO_NARROW",
           "NO_SEED_SUPPORT", "STROKE_SCALE_UNRESOLVED"} <= kinds_present,
          repr(sorted(kinds_present)))
    check("including one bar with a cap and one without",
          any("dispersion" in r for r in zoo)
          and any("value" in r and "dispersion" not in r for r in zoo))
    M.fill_identities_by_figure(zoo)
    written_rows = G.canonical_artifact_rows(zoo)

    def to_csv_and_back(rowdicts):
        path = os.path.join(TMP, "artifact.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(G.GEOMETRY_ARTIFACT_COLUMNS))
            w.writeheader()
            w.writerows(rowdicts)
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    on_disk = to_csv_and_back(written_rows)
    result = G.verify_artifact(on_disk)
    check("every row comes back and every row hash recomputes",
          len(result["records"]) == len(zoo), "%d of %d"
          % (len(result["records"]), len(zoo)))
    check("and the restored records are the records that were written",
          [{k: v for k, v in r.items() if k not in G.UNHASHED_FIELDS}
           for r in zoo] == result["records"])
    # The exact defect, named: an integer survives as an integer.
    caps = [r for r in zoo if r.get("cap_px_image") is not None]
    check("an integer cell does not come back a float",
          caps and all(isinstance(rec.get("cap_px_image"), int)
                       for rec in result["records"]
                       if rec.get("cap_px_image") is not None),
          repr([type(rec.get("cap_px_image")).__name__
                for rec in result["records"]
                if rec.get("cap_px_image") is not None]))
    check("the figure's verdict is recomputed from the file, not trusted",
          result["figures"]["zoo"]["status"] in G.IDENTITY_STATES
          or result["figures"]["zoo"]["status"] in
          ("ESTABLISHED", "DIRECT_ONLY", "AMBIGUOUS",
           "NOT_ENOUGH_COMPLETE_GROUPS"),
          repr(result["figures"]["zoo"]["status"]))
    check("the readable half is a subset of the authoritative half, exactly",
          all(json.loads(r["Diagnostics_JSON"]).items()
              <= json.loads(r["Anonymous_Record_JSON"]).items()
              for r in on_disk))

    # REVERT: return the record and skip the column comparison. `Mean` is a
    # convenience for a person and for SQL, and a file whose convenience column
    # disagrees with the record its hash covers says two things.
    print("\nand refuses a file that says two things")
    for column, value in (("Mean", "99.9"), ("Footprint_X0", "0"),
                          ("Geometry_Error_Code", "NOTHING_WRONG"),
                          ("Auto_Fill_Pattern", "SOLID")):
        bad = [dict(r) for r in on_disk]
        row0 = next(i for i, r in enumerate(bad) if r[column] != "")
        bad[row0][column] = value
        check("editing %s in the file is caught" % column,
              _raises(lambda: G.verify_artifact(bad),
                      "COLUMN_DISAGREES_WITH_RECORD")
              or _raises(lambda: G.verify_artifact(bad),
                         "AUTO_IDENTITY_MODIFIED"),
              "it verified")
    tampered = [dict(r) for r in on_disk]
    rec0 = json.loads(tampered[0]["Anonymous_Record_JSON"])
    rec0["value"] = 99.9
    tampered[0]["Anonymous_Record_JSON"] = G.canonical_json(rec0)
    check("editing the record itself is caught by its own hash",
          _raises(lambda: G.verify_artifact(tampered),
                  "GEOMETRY_ROW_HASH_MISMATCH"), "it verified")
    broken = [dict(r) for r in on_disk]
    broken[0]["Anonymous_Record_JSON"] = "{not json"
    check("an unparseable record is a refusal, not a skipped row",
          _raises(lambda: G.verify_artifact(broken),
                  "ANONYMOUS_RECORD_UNPARSEABLE"), "it verified")
    short = [{k: v for k, v in r.items() if k != "Diagnostics_JSON"}
             for r in on_disk]
    check("a file missing a column is refused before anything is parsed",
          _raises(lambda: G.verify_artifact(short),
                  "ARTIFACT_COLUMNS_UNEXPECTED"), "it verified")

    # REVERT: verify each row and stop. The things only the WHOLE file says -
    # one slot claimed twice, one figure answered two ways, a verdict hash
    # nothing in the file produces - are invisible row by row.
    print("\nand the things only the whole file says")
    doubled = [dict(r) for r in on_disk]
    doubled.append(dict(doubled[0]))
    check("the same slot claimed twice is refused",
          _raises(lambda: G.verify_artifact(doubled),
                  "DUPLICATE_GEOMETRY_SLOT"), "it verified")
    # Two rows that are each internally consistent and were attested under
    # DIFFERENT verdicts - which is what merging two runs of the same figure
    # into one file produces. Editing the hash in place does not reach this
    # check, because the row-level attestation catches that first.
    subset = [dict(r) for r in zoo[:4]]
    M.fill_identities_by_figure(subset)
    replacement = G.artifact_row(subset[0])
    split_fig = [replacement if (r["Panel_ID"], r["Group_ID"],
                                 r["Geometry_Slot"])
                 == (replacement["Panel_ID"], _text(replacement["Group_ID"]),
                     _text(replacement["Geometry_Slot"])) else dict(r)
                 for r in on_disk]
    check("the two verdicts really are different",
          replacement["Domain_Identity_SHA256"]
          != on_disk[0]["Domain_Identity_SHA256"],
          "the subset answered the figure the same way")
    check("one domain answered two ways is refused",
          _raises(lambda: G.verify_artifact(split_fig),
                  "DOMAIN_IDENTITY_INCONSISTENT"), "it verified")
    # REVERT: drop the per-panel (Figure_ID, Identity_Domain_ID) check. One
    # panel belongs to ONE view and ONE domain; a file that gives it two is two
    # producers written over each other, and every row of it hashes correctly
    # because each half was measured honestly.
    _tv = (zoo_rows("zoo_twoview", three, ["OPEN", "STIPPLED", "SOLID"],
                    figure_id="VIEW_A")
           + zoo_rows("zoo_twoview", with_cap, ["SOLID"], figure_id="VIEW_B",
                      anchors={"H": (g8.slots[0][0] + g8.slots[-1][1]) // 2 + 1}))
    M.fill_identities_by_figure(_tv)
    _two_views = G.canonical_artifact_rows(_tv)
    check("the two halves really are one panel with two views",
          {(r["Panel_ID"], r["Figure_ID"]) for r in _two_views}
          == {("zoo_twoview", "VIEW_A"), ("zoo_twoview", "VIEW_B")},
          "%s" % sorted({(r["Panel_ID"], r["Figure_ID"]) for r in _two_views}))
    check("one panel claiming two view/domain pairs is refused",
          _raises(lambda: G.verify_artifact(to_csv_and_back(_two_views)),
                  "PANEL_IDENTITY_INCONSISTENT"), "it verified")
    _ov = zoo_rows("zoo_oneview", three, ["OPEN", "STIPPLED", "SOLID"],
                   figure_id="VIEW_A")
    M.fill_identities_by_figure(_ov)
    check("and one panel with one pair verifies",
          len(G.verify_artifact(to_csv_and_back(
              G.canonical_artifact_rows(_ov)))["records"]) == 3)

    # REVERT: accept Domain_Identity_SHA256 because it is 64 hex characters.
    # A hash that exists is not a verdict that is true: until it is recomputed
    # from the rows in the file, it only says the writer wrote something down.
    forged_fig = [dict(r) for r in on_disk]
    for r in forged_fig:
        r["Domain_Identity_SHA256"] = "2" * 64
    check("a verdict hash the file's own rows do not produce is refused",
          _raises(lambda: G.verify_artifact(forged_fig),
                  "DOMAIN_VERDICT_NOT_REPRODUCED")
          or _raises(lambda: G.verify_artifact(forged_fig),
                     "AUTO_IDENTITY_MODIFIED"), "it verified")
    check("and a file that has not been tampered with still verifies",
          len(G.verify_artifact(to_csv_and_back(written_rows))["records"])
          == len(zoo))

    # ------------------------------------------- 26u. a picture per row
    #
    # The panel overlay answers "did it put the marks in the right places" for
    # a PANEL. The geometry artifact is finer than that - one row per bar - and
    # a reviewer checking eighteen rows against a 600 DPI page render is doing
    # arithmetic on page coordinates by hand.
    #
    # REVERT: have `draw_row_crop` take the spec - the panel box and the group
    # window - beside the record. The pictures look identical and a crop can
    # then be drawn from a DIFFERENT panel's geometry and look perfectly
    # reasonable. The record locating itself is what makes the picture evidence
    # about the row rather than a picture that happens to be next to it.
    print("\neach geometry row can be looked at, from the record alone")
    check("every row says where on the page it was measured",
          all(r.get("panel_box") and r.get("zero_px_image") is not None
              for r in zoo),
          repr([sorted(k for k in ("panel_box", "zero_px_image")
                       if r.get(k) is None) for r in zoo][:3]))
    check("and every row with a footprint says it in page columns too",
          all(r.get("footprint_px_image") for r in zoo if r.get("footprint")),
          repr([(r.get("figure"), r.get("footprint"),
                 r.get("footprint_px_image")) for r in zoo
                if r.get("footprint") and not r.get("footprint_px_image")]))
    crop_dir = os.path.join(TMP, "rows")
    OVERLAY.reset_failures()
    made = []
    for r in zoo:
        made.append(OVERLAY.draw_row_crop(
            os.path.join(crop_dir, OVERLAY.row_crop_name(r)),
            os.path.join(TMP, "%s.png" % r["figure"]), r))
    check("every row gets a picture, refusals included",
          all(made) and len(made) == len(zoo),
          "%d of %d, failures %r" % (len([m for m in made if m]), len(zoo),
                                     OVERLAY.failures()))
    # REVERT: name the file after the panel, group and slot only. Two runs that
    # measured the same bar DIFFERENTLY then write to one filename, and the
    # second silently replaces the first - so a reviewer comparing a picture
    # with a row can be looking at a picture of a different measurement.
    moved = dict(zoo[0])
    moved["value"] = moved["value"] + 1.0
    moved["geometry_row_sha256"] = G.geometry_row_sha256(moved)
    check("the filename carries the measurement, not just the slot",
          OVERLAY.row_crop_name(moved) != OVERLAY.row_crop_name(zoo[0])
          and OVERLAY.row_crop_name(zoo[0]).startswith("zoo_plain__G__slot0__"),
          "%r and %r" % (OVERLAY.row_crop_name(zoo[0]),
                         OVERLAY.row_crop_name(moved)))
    check("and an unstamped record says so rather than looking measured",
          OVERLAY.row_crop_name(
              {k: v for k, v in zoo[0].items()
               if k != "geometry_row_sha256"}).endswith("unstamped.png"))
    # The picture has to be OF the bar. A crop that is the right size and the
    # wrong place passes every check above.
    solid_row = next(r for r in zoo
                     if r["figure"] == "zoo_plain" and r.get("slot") == 2)
    shot = Image.open(os.path.join(
        crop_dir, OVERLAY.row_crop_name(solid_row))).convert("L")
    body = np.asarray(shot)[:shot.height - 58]
    middle = body[body.shape[0] // 2, :]
    width = solid_row["footprint_px_image"][1] - solid_row["footprint_px_image"][0] + 1
    # The pad, then the bar, exactly. A crop of the right size in the wrong
    # place passes every check above this one.
    check("the crop really is this bar, at the offset the pad implies",
          bool((middle[24:24 + width] < 128).all()),
          "%d of the %d footprint columns are ink"
          % (int((middle[24:24 + width] < 128).sum()), width))
    check("and there is paper beside it, so it is not the neighbour",
          middle[18] >= 128 and middle[24 + width + 4] >= 128,
          "%r" % [int(middle[18]), int(middle[24 + width + 4])])
    blank_row = next(r for r in zoo if r.get("error") == "STROKE_SCALE_UNRESOLVED")
    tall = Image.open(os.path.join(crop_dir, OVERLAY.row_crop_name(blank_row)))
    check("a row that never found a bar is shown its whole panel",
          tall.height > shot.height, "%d against %d" % (tall.height, shot.height))
    # REVERT: let a drawing failure raise. A picture that cannot be painted must
    # not fail a row that produced a value - and it must not vanish silently
    # either, which is what `failures()` is for.
    OVERLAY.reset_failures()
    check("a missing raster is a recorded failure, not an exception",
          OVERLAY.draw_row_crop(os.path.join(crop_dir, "x.png"),
                                os.path.join(TMP, "not_here.png"), zoo[0])
          is None and len(OVERLAY.failures()) == 1, repr(OVERLAY.failures()))
    OVERLAY.reset_failures()
    folder = os.path.join(TMP, "rows2")
    # REVERT: take one image path and a list of records. A figure is several
    # panels, so a caller with three of them calls this three times - and each
    # call rewrites index.html, leaving eighteen pictures beside a sheet
    # listing the last six. A sheet that under-reports the folder it sits in is
    # worse than no sheet, because it is the thing a reviewer counts against.
    paths = OVERLAY.write_row_crops(
        folder, [(os.path.join(TMP, "%s.png" % r["figure"]), r) for r in zoo
                 if r["figure"] in ("zoo_plain", "zoo_cap")])
    sheet = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
    check("the folder carries a contact sheet naming every picture in it",
          len(paths) == 6
          and all(os.path.basename(p) in sheet for p in paths),
          repr(sorted(os.listdir(folder))))
    check("across every panel of the figure, not just the last one",
          "zoo_plain" in sheet and "zoo_cap" in sheet,
          "panels named in the sheet: %r"
          % sorted({n for n in ("zoo_plain", "zoo_cap") if n in sheet}))
    check("and the sheet says how many rows, pictures and panels there were",
          "4 rows, 4 pictures, 2 panels" in sheet,
          sheet[sheet.find("<h1>"):sheet.find("</h1>") + 5])

    # ------------------------------------------- 26v. the axis, in frame
    #
    # A crop of one bar shows the reader found the bar. It cannot show the
    # reader knows what the bar is WORTH, because that is the axis and the axis
    # is printed OUTSIDE the panel box. A panel read at the wrong scale has
    # every bar wrong together and every bar still looks like a bar.
    #
    # REVERT: draw the panel picture cropped to `panel_box`. The bars are all
    # there, the picture looks complete, and the tick labels the whole check
    # depends on are outside the crop.
    print("\nthe panel picture puts the axis in frame and the calibration on it")
    check("every row carries the axis mapping that produced its value",
          all(r.get("calibration", {}).get("slope") for r in zoo),
          repr([r.get("calibration") for r in zoo[:1]]))
    panel_png = os.path.join(folder, "panel__zoo_plain.png")
    check("the panel gets its own picture, beside the rows",
          os.path.exists(panel_png)
          and "panel__zoo_plain.png" in sheet, repr(sorted(os.listdir(folder))))
    panel_img = Image.open(panel_png).convert("RGB")
    row_img = Image.open(os.path.join(
        crop_dir, OVERLAY.row_crop_name(solid_row)))
    # Not "bigger than a bar" - bigger than the PANEL BOX, on the two sides the
    # axis is printed on. A picture cropped to the box holds every bar and none
    # of the numbers they are measured against.
    # The left margin is as much as the PAGE allows, up to a fifth of the
    # panel - this fixture's panel starts 40 px from the page edge, so it gets
    # 40. What must not happen is no margin at all.
    check("and it reaches outside the box, where the ticks are printed",
          panel_img.width >= (g8.x1 - g8.x0) + min(g8.x0,
                                                   0.2 * (g8.x1 - g8.x0))
          and (panel_img.height - 58) >= (g8.y1 - g8.y0) * 1.1
          and panel_img.width > row_img.width,
          "%dx%d against the panel box's %dx%d"
          % (panel_img.width, panel_img.height - 58,
             g8.x1 - g8.x0, g8.y1 - g8.y0))
    # The check the picture exists FOR: the line the calibration calls 50 has
    # to land on the row the fixture drew 50 at. The fixture's own geometry
    # says where that is, so this is an independent statement about the
    # drawing rather than a restatement of the calibration.
    # The DECLARED point, drawn solid. The fixture calibrates at 0 and 100, so
    # 100 is a number a person typed and the line for it must land on the row
    # the fixture drew 100 at.
    arr = np.asarray(panel_img)
    want_row = int(round(g8.base - 100 * g8.ppu))
    y = want_row - max(0, g8.y0 - 24)
    band = arr[max(0, y - 2):y + 3]
    solid = ((band[:, :, 0] == 200) & (band[:, :, 1] == 120)
             & (band[:, :, 2] == 0))
    check("the line for a declared point lands on the row it was declared at",
          bool(solid.any()) and float(solid.sum()) > 0.5 * panel_img.width,
          "%d solid-orange pixels within two rows of %d"
          % (int(solid.sum()), want_row))
    # REVERT: check the caption by searching the PNG's bytes for the text.
    # Text drawn into an image is PIXELS - the string is not in the file - so
    # that check finds nothing on a correct picture and can only be made to
    # pass by weakening it, which is what happened: it was written
    # `... in open(png,"rb").read().decode(...) or True` and passed
    # unconditionally. What the picture DREW has to come back as data.
    meta = json.load(open(os.path.splitext(panel_png)[0] + ".json",
                          encoding="utf-8"))
    # REVERT: draw round values only, and report them as `axis_ticks`. On a
    # panel calibrated at 2.5 and 7.5 the picture then shows 3, 4, 5, 6, 7 -
    # and neither number anybody entered. The declared points ARE the
    # calibration; a guide line at a round value is a reading aid.
    check("the picture reports what it drew, as data rather than as pixels",
          meta["declared_calibration_points"]
          and all(set(t) == {"value", "pixel"}
                  for t in meta["declared_calibration_points"]
                  + meta["generated_reference_ticks"]),
          repr(meta.get("declared_calibration_points")))
    check("and the points it reports are the points somebody typed",
          [(t["value"], t["pixel"]) for t in
           meta["declared_calibration_points"]]
          == [(0.0, float(g8.base)), (100.0, float(g8.base - 100 * g8.ppu))],
          repr(meta["declared_calibration_points"]))
    check("with the guide lines kept separate, and never duplicating one",
          not ({t["value"] for t in meta["generated_reference_ticks"]}
               & {t["value"] for t in meta["declared_calibration_points"]}),
          repr([t["value"] for t in meta["generated_reference_ticks"]]))
    check("and each reported line is where the calibration puts that value",
          all(abs(t["pixel"] - (g8.base - t["value"] * g8.ppu)) < 0.51
              for t in meta["declared_calibration_points"]
              + meta["generated_reference_ticks"]),
          repr([(t["value"], t["pixel"], g8.base - t["value"] * g8.ppu)
                for t in meta["generated_reference_ticks"]]))
    check("the contact sheet names the typed points, not only the guides",
          "Calibration points somebody typed" in sheet
          and all("%g" % t["value"] in sheet
                  for t in meta["declared_calibration_points"]),
          sheet[sheet.find("Calibration points"):][:110])
    # REVERT: draw the panel picture without the calibration lines. Everything
    # above still passes - the bars are marked, the baseline is marked - and
    # the one thing a per-bar crop cannot show is still not shown.
    plain_dir = os.path.join(TMP, "noaxis")
    OVERLAY.reset_failures()
    stripped = [dict(r) for r in zoo if r["figure"] == "zoo_plain"]
    for r in stripped:
        r.pop("calibration", None)
    OVERLAY.draw_panel_geometry(
        os.path.join(plain_dir, "p.png"),
        os.path.join(TMP, "zoo_plain.png"), stripped)
    bare_arr = np.asarray(Image.open(
        os.path.join(plain_dir, "p.png")).convert("RGB"))
    bare_orange = ((bare_arr[:, :, 0] == 200) & (bare_arr[:, :, 1] == 120)
                   & (bare_arr[:, :, 2] == 0))
    check("a panel whose rows carry no calibration draws no axis lines",
          not bare_orange.any(), "%d orange pixels" % int(bare_orange.sum()))

    # ------------------------------------------- 26v2. the axis says it fits
    #
    # `check_calibration` uses `slope` and `intercept` and nothing else, so a
    # record could carry points nobody fitted, an `n_points` counting something
    # else and a `max_residual` invented from nothing, and every value in the
    # file would still follow from the mapping. Those three are the PROVENANCE
    # of the mapping - what a person typed, how many ticks they read, how badly
    # the line missed them - and provenance nobody checks is decoration.
    #
    # REVERT: drop `validate_calibration`. Every value check still passes, the
    # artifact still verifies, and the points can say anything at all.
    print("\nthe calibration has to fit the points it says it came from")
    honest = dict(zoo[0]["calibration"])
    G.validate_calibration(honest)                       # the real one is fine
    for field, value in (("n_points", 4),
                         ("max_residual", 0.001),
                         ("slope", honest["slope"] * 1.001),
                         ("intercept", honest["intercept"] + 1.0),
                         ("scale", "LOOG"),
                         ("points", [[0.0, 1.0], [1.0, 2.0]])):
        broken = dict(honest)
        broken[field] = value
        check("a calibration whose %s is not true of its points is refused"
              % field, _raises_value(lambda: G.validate_calibration(broken)),
              "it validated")
    check("and a row without one cannot enter a canonical geometry file",
          _raises(lambda: G.canonical_artifact_rows(
              [dict(r, calibration=None) for r in zoo[:1]]),
              "CALIBRATION_MISSING"), "it wrote the row")
    # End to end, not by reading the source: a row that is internally perfect
    # in every other way - the hash covers the lie, the attestation covers the
    # hash, `Mean` follows from the slope - and whose `n_points` is not true of
    # its points.
    lying = dict(zoo[0])
    lying["calibration"] = dict(honest, n_points=4)
    lying["geometry_row_sha256"] = G.geometry_row_sha256(lying)
    lying["auto_identity_sha256"] = G.auto_identity_sha256(lying)
    lying_row = {k: _text(v) for k, v in G.artifact_row(lying).items()}
    check("the durable reader catches it on the way back in",
          _raises(lambda: G.verify_artifact([lying_row],
                                            recompute_identity=False),
                  "CALIBRATION_POINT_COUNT"),
          "the file verified")
    # REVERT: leave `review_crop_box` out of the panel consistency tuple. The
    # picture is drawn from the FIRST row's crop, so rows that disagree get a
    # panel drawn against a review region that is not theirs.
    mixed_crop = [dict(r) for r in zoo if r["figure"] == "zoo_plain"]
    mixed_crop[1]["review_crop_box"] = [0, 10, 0, 10]
    OVERLAY.reset_failures()
    check("a panel whose rows disagree about the review crop is not drawn",
          OVERLAY.draw_panel_geometry(
              os.path.join(TMP, "disagree.png"),
              os.path.join(TMP, "zoo_plain.png"), mixed_crop) is None
          and any("review_crop_box" in f for f in OVERLAY.failures()),
          repr(OVERLAY.failures()))
    OVERLAY.reset_failures()

    # ------------------------------------------- 26w. the factor of ten
    #
    # The severe calibration failure is not a tick pixel a few rows out - that
    # is 1.7% on publication 127 at ten pixels, below the digitization noise.
    # It is a tick VALUE misread: a printed 30 typed as 3 makes every bar in
    # the panel exactly ten times too small, all together, and every bar still
    # looks like a bar. No arithmetic catches it - the mapping is perfectly
    # self-consistent, and a third tick scales with the other two so the
    # residual stays zero. The only thing that catches it is the number the
    # calibration claims sitting beside the number the FIGURE prints.
    #
    # Which means the fixture has to print numbers. Everything else in this
    # file draws bars and no axis, so until now a scenario could only confirm
    # the orange line was in the right PLACE - and a line in the right place is
    # exactly what a factor-of-ten error still produces.
    #
    # REVERT: draw the panel picture without the value labels, or draw them on
    # the left over the printed ones. Both leave a picture that looks complete
    # and cannot be compared with anything.
    print("\na printed axis, and the number the calibration puts beside it")
    g9 = Geometry(1.0)
    printed = print_axis_labels(g9.blank(), g9, (0, 50, 100))
    g9.solid(printed, 0, 60)
    lab_path = write(printed, "labelled", TMP)
    lab_gray = M._gray(lab_path)
    lab_anchor = {"G": (g9.slots[0][0] + g9.slots[-1][1]) // 2}

    def labelled_rows(top_value):
        """The panel read with the top tick declared as `top_value`."""
        return G.geometry_rows(
            lab_gray, [g9.x0, g9.x1, g9.y0, g9.y1],
            MRX.AxisCalibration.from_points(
                [(0, g9.base), (top_value, g9.base - 100 * g9.ppu)]),
            lab_anchor, ["SOLID"], g9.r(190), baseline=0.0,
            panel_id="labelled", identity_domain_id="labelled")

    right = labelled_rows(100)                 # the axis really is 0..100
    wrong = labelled_rows(10)                  # the 100 was read as 10
    _src = np.asarray(Image.open(lab_path).convert("L"))[:, :g9.x0]
    check("the fixture prints 0, 50 and 100 beside its axis",
          int(((_src > 0) & (_src < 255)).sum()) > 40,
          "%d printed pixels left of the plot area"
          % int(((_src > 0) & (_src < 255)).sum()))
    check("and the misread calibration is exactly ten times too small",
          abs(right[0]["value"] / wrong[0]["value"] - 10.0) < 1e-6,
          "%r against %r" % (right[0]["value"], wrong[0]["value"]))
    check("with nothing in the row's own arithmetic to disagree with it",
          G.check_calibration(wrong[0]) is None
          and wrong[0]["calibration"]["max_residual"] < 1e-9,
          repr(wrong[0]["calibration"]["max_residual"]))
    ten_dir = os.path.join(TMP, "tenx")
    OVERLAY.reset_failures()
    good_meta = OVERLAY.draw_panel_geometry(
        os.path.join(ten_dir, "right.png"), lab_path, right)
    bad_meta = OVERLAY.draw_panel_geometry(
        os.path.join(ten_dir, "wrong.png"), lab_path, wrong)
    check("the correct panel shows the number the person typed: 100",
          [t["value"] for t in good_meta["declared_calibration_points"]]
          == [0.0, 100.0],
          repr(good_meta["declared_calibration_points"]))
    check("and the misread one shows 10, on the row the page prints 100",
          [t["value"] for t in bad_meta["declared_calibration_points"]]
          == [0.0, 10.0]
          and (bad_meta["declared_calibration_points"][1]["pixel"]
               == good_meta["declared_calibration_points"][1]["pixel"]),
          repr(bad_meta["declared_calibration_points"]))
    check("which is the whole comparison: same row, different number",
          100.0 not in {t["value"] for t in
                        bad_meta["declared_calibration_points"]
                        + bad_meta["generated_reference_ticks"]},
          repr([t["value"] for t in bad_meta["generated_reference_ticks"]]))
    # Which is only useful if the printed numbers are still THERE to compare
    # with - in frame, and not painted over by the orange ones.
    # The comparison is only possible if the printed numbers are still THERE:
    # inside the crop, and not painted over by the drawn ones. Everything left
    # of the plot area is the printed axis, and the picture must reproduce that
    # strip untouched, pixel for pixel.
    source = np.asarray(Image.open(lab_path).convert("L"))
    for name, meta in (("right", good_meta), ("wrong", bad_meta)):
        shown = np.asarray(Image.open(meta["path"]).convert("L"))
        x0c, y0c, x1c, y1c = meta["crop_box"]
        edge = meta["plot_left_in_crop"]
        theirs = shown[:y1c - y0c, :edge]
        ours = source[y0c:y1c, x0c:x0c + edge]
        printed = int(((ours > 0) & (ours < 255)).sum())
        check("the %s picture reproduces the printed axis strip untouched"
              % name,
              printed > 40 and theirs.shape == ours.shape
              and bool((theirs == ours).all()),
              "%d printed pixels, %d differ"
              % (printed, int((theirs != ours).sum())
                 if theirs.shape == ours.shape else -1))
    check("and the strip is wide enough to hold the numbers the page prints",
          good_meta["plot_left_in_crop"] >= 32,
          "%d px of margin" % good_meta["plot_left_in_crop"])
    # REVERT: draw the lines and not the numbers. The metadata still reports
    # the values, every check above still passes, and the picture a reviewer
    # opens has four orange lines and nothing to compare the printed numbers
    # WITH - which is the whole comparison.
    for name, meta in (("right", good_meta), ("wrong", bad_meta)):
        rgb = np.asarray(Image.open(meta["path"]).convert("RGB")).astype(int)
        orange = ((rgb[:, :, 0] > 140) & (rgb[:, :, 1] > 60)
                  & (rgb[:, :, 1] < 200) & (rgb[:, :, 2] < 120))
        x0c, y0c = meta["crop_box"][0], meta["crop_box"][1]
        drawn = []
        for tick in meta["declared_calibration_points"]:
            y = int(round(tick["pixel"])) - y0c
            band = orange[max(0, y - 12):max(0, y - 1)]
            drawn.append(int(band.sum()))
        check("the %s picture writes the value beside each line, not just the"
              " line" % name,
              len(drawn) >= 2 and all(n >= 4 for n in drawn),
              "orange pixels above each line: %r" % drawn)

    # -------------------------------------------------- 27. the contract
    print("\nthe fail-closed contract holds for every refusal in this file")
    for name, rec_ in (("gap", only(M.measure_panel(spec(
            os.path.join(TMP, "gap.png"), ["HATCHED"])))),
            ("spur", only(M.measure_panel(spec(
                os.path.join(TMP, "spur.png"), ["SOLID"]))))):
        check("%s: refused records carry no value" % name, "value" not in rec_)
        check("%s: refused records carry no texture" % name,
              not any(k.startswith("t") and k[1:].isdigit() for k in rec_))
finally:
    shutil.rmtree(TMP, ignore_errors=True)

# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("\n%d scenarios passed, %d failed" % (PASSED[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    raise SystemExit(1)
