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
    img[top_row(40) - 40:top_row(40), a + 25:a + 29] = 0        # off-centre spur
    img[top_row(40) - 46:top_row(40) - 40, a + 20:a + 34] = 0   # ending in a blob
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

    # -------------------------------------------------- 13. the contract
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
