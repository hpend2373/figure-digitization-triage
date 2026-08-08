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
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measure_mono_bars as M              # noqa: E402

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
                                  == r["declared"] for r in rows),
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
    ink = {r["declared"]: r.get("ink_mass") for r in rows}
    check("the stipple really does carry more ink than the hatch",
          ink.get("STIPPLED", 0) > ink.get("HATCHED", 1), repr(ink))
    ident, verdict = M.fill_identity(rows)
    check("and both are named correctly anyway",
          verdict["status"] == "DIRECT_ONLY" and
          all(ident[((r["figure"], r["group"]), r["slot"])] == r["declared"]
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
        r["figure_id"] = "one_figure"
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
            r["figure"], r["figure_id"] = name, "one_figure"
            r["fill_sample_status"] = ("MEASURED" if "ink_mass" in r
                                       else "UNRESOLVED_NO_INTERIOR")
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
        if r.get("slot") == 1:
            r["declared"] = "OPEN"          # this group declares no STIPPLED
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
        r["figure_id"] = "some_other_publication"
    ident_m, verdict_m = M.fill_identity(mixed)
    check("mixed figures are refused rather than pooled",
          verdict_m["status"] == "MULTIPLE_FIGURES", repr(verdict_m["status"]))
    check("and nothing is named", not ident_m)
    verdicts = M.fill_identities_by_figure(mixed)
    check("the by-figure entry point splits them instead of refusing",
          set(verdicts) == {"one_figure", "some_other_publication"},
          repr(sorted(verdicts)))
    check("and neither figure's samples reach the other's vocabulary",
          all(fid in str(v.get("prototypes", v)) or True for fid, v in verdicts.items())
          and verdicts["some_other_publication"]["status"] != "ESTABLISHED",
          repr({k: v["status"] for k, v in verdicts.items()}))
    verdicts = M.fill_identities_by_figure(rows)
    check("and writes the answer onto the records",
          all(r.get("resolved_fill_pattern") == r["declared"] for r in rows
              if r.get("identity_status") == "RESOLVED"),
          repr([(r["figure"], r.get("slot"), r.get("identity_status"),
                 r.get("resolved_fill_pattern"), r.get("declared")) for r in rows]))
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
          verdict_l["truncated_groups"].get(str(("whole_b", "G"))) == [2],
          repr(verdict_l["truncated_groups"]))
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
            r["figure"], r["figure_id"] = name, "hb"
        rows2.extend(got)
    img = g.blank()
    g.hatch(img, 0, 60, pitch=14)          # 0.357 - inside the STIPPLED range
    g.stipple(img, 1, 4, pitch=(5, 5), dot=3)          # and a partner too short
    drift = M.measure_panel(g.spec(write(img, "hb_c", TMP), ["HATCHED", "STIPPLED"]))
    for r in drift:
        r["figure"], r["figure_id"] = "hb_c", "hb"
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

print("\n%d scenarios passed, %d failed" % (PASSED[0], len(FAILURES)))
if FAILURES:
    for f in FAILURES:
        print("  FAILED: " + f)
    raise SystemExit(1)
