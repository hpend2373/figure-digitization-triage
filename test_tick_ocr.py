#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenarios for tick-anchored OCR.

    python3 test_tick_ocr.py

Publication 177's figure 2 row 4 is labelled 4, 3, 2, 1 and the strip reader
returned one of the four. Asking one crop per TICK recovers all four. The
scenarios that matter most here are the ones about what this may NOT do: the
arithmetic progression chooses among values that were READ, and never fills a
gap or corrects a value into line. A reader that can do either is drawing an
axis, not reading one.
"""
import inspect
import os
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import axis_reader as A                                          # noqa: E402
import gate_trace as T                                          # noqa: E402
import tick_ocr as O                                            # noqa: E402
import y_scale_group as Y                                        # noqa: E402

RUN = [0]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def has_ocr():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


class ChoosingAmongWhatWasRead(unittest.TestCase):
    """The progression is a tie-break, not a generator."""

    def test_one_ladder_among_the_read_values_is_the_answer(self):
        """177 figure 2's P10: four rows, one of which reads two candidates, and
        exactly one combination is monotone with a constant step."""
        pairs, detail = O.choose([843, 917, 992, 1068],
                                 {843: [4.0], 917: [2.0, 3.0],
                                  992: [2.0], 1068: [1.0]})
        self.assertEqual(pairs, [(4.0, 843), (3.0, 917), (2.0, 992), (1.0, 1068)])
        self.assertIn("one combination", detail)
        RUN[0] += 1

    def test_a_row_that_read_nothing_is_not_filled_from_the_sequence(self):
        """The whole point. Three rows read 4, 2, 1 and the fourth read nothing;
        3 is exactly what the progression would supply, and supplying it would be
        inventing a measurement. Guard: `usable` skipping empty rows, and the
        combination never adding a row."""
        pairs, _d = O.choose([843, 917, 992, 1068],
                             {843: [4.0], 917: [], 992: [2.0], 1068: [1.0]})
        self.assertEqual([r for _v, r in pairs], [843, 992, 1068])
        self.assertNotIn(917, [r for _v, r in pairs])
        self.assertNotIn(3.0, [v for v, _r in pairs])
        RUN[0] += 1

    def test_a_value_off_the_line_is_refused_and_not_snapped_onto_it(self):
        """A misread 9 where 3 belongs must break the ladder, not be corrected
        into it. Guard: `A.ladder` deciding, with no repair step."""
        pairs, detail = O.choose([100, 200, 300],
                                 {100: [4.0], 200: [9.0], 300: [2.0]})
        self.assertEqual(pairs, [])
        self.assertIn("no combination", detail)
        RUN[0] += 1

    def test_a_misread_row_is_not_dropped_as_a_subset(self):
        """`ladder` accepts a contiguous SUBSET when the full set fails, which is
        right for a strip - a rotated title OCRs as a numeral and does not belong
        on the axis. It is wrong here: every candidate is anchored to a tick that
        was MEASURED, so a value that does not fit is a misread and dropping it
        silently leaves that tick carrying a wrong number nobody sees.
        Guard: allow_subset=False."""
        # THE MISREAD IS AT AN END, which is the case a contiguous subset can
        # quietly drop: 4, 3, 2 is a ladder and the fourth tick keeps its 9.
        pairs, detail = O.choose([100, 200, 300, 400],
                                 {100: [4.0], 200: [3.0], 300: [2.0],
                                  400: [9.0]})
        self.assertEqual(pairs, [], "the misread row was dropped as a subset")
        self.assertIn("no combination", detail)
        # and a combination that DOES fit is still found when one exists
        ok, _d = O.choose([100, 200, 300, 400],
                          {100: [4.0], 200: [3.0], 300: [2.0],
                           400: [9.0, 1.0]})
        self.assertEqual([v for v, _r in ok], [4.0, 3.0, 2.0, 1.0])
        RUN[0] += 1

    def test_too_few_rows_read_is_a_refusal_with_the_count_in_it(self):
        """`MIN_LABELS` is the same floor every ladder in this package has.
        Guard: the `len(usable) < A.MIN_LABELS` return."""
        pairs, detail = O.choose([100, 200, 300], {100: [4.0], 200: [3.0]})
        self.assertEqual(pairs, [])
        self.assertIn("2 of 3", detail)
        self.assertIn(str(A.MIN_LABELS), detail)
        RUN[0] += 1

    def test_two_combinations_that_both_work_are_refused(self):
        """Picking one would be inventing the difference between them.
        Guard: the distinct-winner check."""
        pairs, detail = O.choose([100, 200, 300],
                                 {100: [4.0], 200: [3.0], 300: [2.0, 2.0000001]})
        # the two candidates differ, so two ladders exist and neither is chosen
        self.assertEqual(pairs, [])
        self.assertIn("different combinations", detail)
        RUN[0] += 1

    def test_the_check_is_the_packages_own_ladder(self):
        """A monotone-only test would accept 4, 3, 1 - which is not an axis.
        Guard: ladder() being the test rather than a local one."""
        pairs, _d = O.choose([100, 200, 300],
                             {100: [4.0], 200: [3.0], 300: [1.0]})
        self.assertEqual(pairs, [])
        RUN[0] += 1


class OneCropPerTick(unittest.TestCase):

    def test_the_crop_is_bounded_by_the_neighbouring_ticks(self):
        """A crop tall enough to reach the label above it reads that label, and
        the row then has a candidate that belongs to another tick.
        Guard: half the SMALLEST measured gap."""
        box = O.crop_box([100, 140, 180], 140, 50, "LEFT", (400, 400))
        self.assertEqual(box[2:], (120, 161))
        wide = O.crop_box([100, 300], 100, 50, "LEFT", (400, 400))
        self.assertEqual(wide[3] - wide[2], 201)
        RUN[0] += 1

    def test_a_single_tick_falls_back_to_the_panels_own_bound(self):
        """With one tick there is no gap to measure, and LABEL_BAND_MAX is the
        only bound left rather than an invented one."""
        box = O.crop_box([200], 200, 50, "LEFT", (400, 400))
        self.assertEqual(box[3] - box[2], 2 * A.LABEL_BAND_MAX + 1)
        RUN[0] += 1

    def test_the_crop_is_on_the_label_side(self):
        left = O.crop_box([100, 140], 100, 50, "LEFT", (400, 400))
        right = O.crop_box([100, 140], 100, 50, "RIGHT", (400, 400))
        self.assertEqual((left[0], left[1]), (max(0, 50 - A.LABEL_BAND_MAX), 50))
        self.assertEqual((right[0], right[1]), (51, 51 + A.LABEL_BAND_MAX))
        RUN[0] += 1

    def test_agreeing_attempts_are_one_candidate_and_not_twelve(self):
        """Twelve renderings reading 3 are one candidate. What matters downstream
        is how many DIFFERENT numbers the crop could be.
        Guard: best_per_value."""
        raw = [(3.0, "3", 40, 4, "grey", "7"), (3.0, "3", 81, 8, "ink", "8"),
               (8.0, "8", 30, 6, "grey", "10")]
        got = O.best_per_value(raw)
        self.assertEqual([v for v, *_ in got], [3.0, 8.0])
        self.assertEqual(got[0][2], 81, "the best confidence was not kept")
        RUN[0] += 1

    def test_every_declared_magnification_is_actually_tried(self):
        """The 177 row-4 reads came from 6x and 8x and none from 3x, which is
        where the strip reader looks - so the sweep is the difference between
        reading that panel and not. What a drawn fixture CAN hold is that every
        declared scale is attempted; that the sweep changes the answer is a
        corpus fact and is recorded in INSTALL.md rather than asserted here.
        Guard: the loop over SCALES."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img = Image.new("L", (60, 40), 255)
        ImageDraw.Draw(img).text((6, 6), "4",
                                 font=ImageFont.truetype(FONT, 12), fill=0)
        seen = {sc for _v, _s, _c, sc, _n, _p in O.read_box(img, (0, 60, 0, 40), 140)}
        self.assertEqual(seen, set(O.SCALES))
        self.assertGreater(len(O.SCALES), 1, "a sweep of one is not a sweep")
        RUN[0] += 1

    def test_the_binarisation_uses_the_figures_own_ink_threshold(self):
        """A fixed threshold is the constant this package spent four rounds
        removing from everything else. Guard: renderings() taking `ink`."""
        img = Image.new("L", (40, 40), 255)
        img.putpixel((10, 10), 150)
        at140 = O.renderings(img, (0, 40, 0, 40), 140)
        at200 = O.renderings(img, (0, 40, 0, 40), 200)
        self.assertEqual(np.asarray(at140[1][1]).min(), 255)
        self.assertEqual(np.asarray(at200[1][1]).min(), 0)
        self.assertIn("ink=200", at200[1][0])
        RUN[0] += 1

    def test_the_shipped_ink_is_tried_as_well_as_the_passs_own(self):
        """The pass chose its ink for SEGMENTATION. Publication 177's figure 2
        wins on PLAIN at 173 because it came up short of its declared axes, and
        at 173 its single digits erode: the "2" of row 4 reads nothing and the
        "1" reads 4, 7 or 5. At the shipped 140 all four read. Guard: inks_for."""
        self.assertEqual(O.inks_for(173), [173, A.INK_DEFAULT])
        self.assertEqual(O.inks_for(A.INK_DEFAULT), [A.INK_DEFAULT],
                         "the same threshold was rendered twice")
        names = [n for n, _im in O.renderings(Image.new("L", (40, 40), 255),
                                              (0, 40, 0, 40), 173)]
        self.assertEqual(names, ["grey", "ink=173", "ink=%d" % A.INK_DEFAULT])
        RUN[0] += 1


class RecordsAndChangesNothing(unittest.TestCase):

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._o = T.ON, O.ON
        T.ON, O.ON = True, True

    def tearDown(self):
        T.ON, O.ON = self._on, self._o

    def test_it_is_never_handed_the_proposal_list(self):
        """Like every other shadow here. Guard: the signature."""
        self.assertEqual(list(inspect.signature(O.record).parameters),
                         ["img", "dark", "label", "box", "spine_x", "side",
                          "run", "ticks", "ink"])
        RUN[0] += 1

    def test_with_the_flag_off_nothing_is_recorded(self):
        O.ON = False
        img = Image.new("L", (40, 40), 255)
        self.assertIsNone(O.record(img, np.zeros((40, 40), dtype=bool), "P01",
                                   (0, 40, 0, 40), 20, "LEFT", (0, 40), [10, 20]))
        self.assertEqual(T.ROWS, [])
        RUN[0] += 1

    def test_zero_turns_the_flag_off(self):
        """`bool(os.environ.get("TICKOCR"))` is True for "0"."""
        import importlib, os as _os
        for value, want in ((None, False), ("0", False), ("1", True)):
            old = _os.environ.pop("TICKOCR", None)
            try:
                if value is not None:
                    _os.environ["TICKOCR"] = value
                self.assertEqual(importlib.reload(O).ON, want,
                                 "TICKOCR=%r read as %r" % (value, O.ON))
            finally:
                _os.environ.pop("TICKOCR", None)
                if old is not None:
                    _os.environ["TICKOCR"] = old
        importlib.reload(O)
        RUN[0] += 1

    def test_a_row_that_read_nothing_is_recorded_as_such(self):
        """An empty row that is silently skipped is indistinguishable from a row
        nobody looked at. Guard: the NO_CANDIDATE outcome."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        img = Image.new("L", (200, 200), 255)
        d = ImageDraw.Draw(img)
        d.rectangle([120, 20, 121, 180], fill=0)          # a spine, no numerals
        for y in (60, 110, 160):
            d.rectangle([114, y, 119, y + 2], fill=0)
        dark = np.asarray(img) <= 140
        O.record(img, dark, "P01", (60, 200, 20, 190), 120, "LEFT", (20, 180),
                 [61, 111, 161])
        rows = [r for r in T.ROWS if r["kind"] == "TICK_OCR"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["outcome"] for r in rows}, {O.NO_CANDIDATE})
        lad = [r for r in T.ROWS if r["kind"] == "TICK_OCR_LADDER"][0]
        self.assertEqual(lad["outcome"], O.REFUSED)
        RUN[0] += 1

    def test_single_digit_labels_are_read_one_crop_at_a_time(self):
        """The 177 row-4 shape, drawn: a spine, four ticks, and the single digits
        4 3 2 1 beside them. The strip reader is what fails on this; this is the
        route that does not."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img = Image.new("L", (280, 340), 255)
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(FONT, 34)
        sx = 170
        d.rectangle([sx, 40, sx + 1, 300], fill=0)
        d.rectangle([sx, 298, 260, 300], fill=0)
        for y, txt in zip((60, 130, 200, 270), ("4", "3", "2", "1")):
            d.rectangle([sx - 7, y, sx - 1, y + 2], fill=0)
            d.text((sx - 40, y - 17), txt, font=f, fill=0)
        dark = np.asarray(img) <= 140
        ticks = [(a + b) // 2 for a, b, _ln in
                 Y.tick_runs(dark, (60, 270, 40, 310), sx, (40, 300), "LEFT")]
        self.assertEqual(len(ticks), 4, "the fixture's own ticks were not found")
        got = O.record(img, dark, "P01", (60, 270, 40, 310), sx, "LEFT",
                       (40, 300), ticks)
        lad = [r for r in T.ROWS if r["kind"] == "TICK_OCR_LADDER"][0]
        self.assertEqual(lad["outcome"], O.READ, lad["detail"])
        self.assertEqual([v for v, _r in got], [4.0, 3.0, 2.0, 1.0])
        RUN[0] += 1


_TUNED_H = A._TUNED_PANEL_PX


def panel_with_labels(scale, labels=("3000", "2000", "1000"), tick=6, gap=95):
    """A panel drawn at `scale`: a spine, three ticks and three WIDE numerals.

    Everything in it is `scale` times the tuned render - which is what a 600 DPI
    page is next to the 300 DPI one `_STRIPS` was measured on. `tick` is the
    tick length and `gap` the label's distance from the spine, both at scale 1.
    """
    # The panel is the TUNED height at scale 1, so scale 2 is exactly the step
    # from the 300 DPI render `_STRIPS` was measured on to a 600 DPI one.
    w, h = int(300 * scale), int(460 * scale)
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, int(20 * scale))
    sx, top = int(150 * scale), int(20 * scale)
    bot = top + int(_TUNED_H * scale)
    d.rectangle([sx, top, sx + int(scale), bot], fill=0)                   # spine
    d.rectangle([sx, bot, w - int(20 * scale), bot + int(scale)], fill=0)  # baseline
    ys = [int((top + off) * scale) for off in (60, 190, 320)]
    for y, txt in zip(ys, labels):
        d.rectangle([sx - int(tick * scale), y, sx - 1, y + max(1, int(2 * scale))], fill=0)
        d.text((sx - int(gap * scale), y - int(11 * scale)), txt, font=f, fill=0)
    box = (sx, w - int(20 * scale), top, bot)
    return img, np.asarray(img) <= 140, box, sx, bot


class LabelStripsScaleWithTheRender(unittest.TestCase):
    """`_STRIPS` is pixels, and pixels are a resolution."""

    def test_at_the_tuned_height_the_strips_are_unchanged(self):
        self.assertEqual(A.strips_for(A._TUNED_PANEL_PX), list(A._STRIPS))
        self.assertEqual(A.strips_for(A._TUNED_PANEL_PX * 1.1), list(A._STRIPS))
        RUN[0] += 1

    def test_a_taller_panel_adds_wider_strips_after_the_tuned_ones(self):
        got = A.strips_for(A._TUNED_PANEL_PX * 2)
        self.assertEqual(got[:len(A._STRIPS)], list(A._STRIPS),
                         "the tuned strips must still be tried first")
        wider = got[len(A._STRIPS):]
        self.assertEqual(wider, [(4, 88), (12, 120), (12, 220), (12, 340)], wider)
        self.assertFalse(set(wider) & set(A._STRIPS), "a width was tried twice")
        RUN[0] += 1

    def test_a_height_that_is_not_a_number_is_not_a_scale(self):
        self.assertEqual(A.strips_for(None), list(A._STRIPS))
        self.assertEqual(A.strips_for(0), list(A._STRIPS))
        RUN[0] += 1

    def test_wide_labels_are_read_at_the_bigger_render(self):
        """The defect, drawn. `3000` is wider than every tuned strip once the
        page is rendered at twice the DPI, so the numerals are cut in half and
        tesseract reads nothing - on 379 of this project's 600 DPI panels."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0)
        pairs = A.y_tick_labels(img, dark, box, sx, base)
        self.assertTrue(A.ladder(pairs)[0], "the wide labels were not read: %s" % (pairs,))
        self.assertEqual([v for v, _r in pairs], [3000.0, 2000.0, 1000.0], pairs)
        RUN[0] += 1

    def test_every_tuned_strip_at_both_anchors_comes_before_any_wider_one(self):
        """REVERT: append the wider strips inside the anchor loop. Then the
        spine's wide strips are tried before the block edge's narrow ones, and a
        fallback that can change an answer an earlier pass already had is not a
        fallback: two of thirty panels that read correctly came back with a
        different, worse ladder. Observed on the STRIPS THE SEARCH ASKS FOR, so
        it does not need tesseract and does not depend on a fixture happening to
        exhibit it."""
        asked = []

        def spy(img, dark, left, right, top, bottom, scale=3, **kw):
            asked.append(int(right) - int(left))
            return []

        img, dark, box, sx, base = panel_with_labels(2.0)
        real = A._ocr_numerals
        A._ocr_numerals = spy
        try:
            A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        widest_tuned = max(w for _g, w in A._STRIPS)
        wide = [i for i, w in enumerate(asked) if w > widest_tuned]
        self.assertTrue(wide, "no wider strip was ever tried: %s" % (asked,))
        tuned_widths = {w for _g, w in A._STRIPS}
        before = [w for w in asked[:wide[0]] if w in tuned_widths]
        self.assertGreaterEqual(
            len(before), 2 * len(A._STRIPS),
            "a wider strip was tried before both anchors had had every tuned "
            "strip: %s" % (asked[:wide[0] + 1],))
        RUN[0] += 1


class OneStripOneRead(unittest.TestCase):

    def test_no_strip_is_read_twice_at_the_same_magnification(self):
        """REVERT: call tesseract again for a strip it has already read. The
        union pass re-reads every single-pass strip at x3, and the wider pass
        repeats the pattern: a third of the calls on a refused panel, for
        answers already in hand. tesseract is deterministic on the same pixels,
        so the memo changes nothing but the clock."""
        asked = []

        def spy(img, dark, left, right, top, bottom, scale=3, **kw):
            asked.append((int(left), int(right), int(top), int(bottom), int(scale)))
            return []

        img, dark, box, sx, base = panel_with_labels(2.0)
        real = A._ocr_numerals
        A._ocr_numerals = spy
        try:
            A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        self.assertGreater(len(asked), 8, "the search hardly searched: %s" % (asked,))
        self.assertEqual(len(asked), len(set(asked)),
                         "%d of %d strip reads were repeats" % (len(asked) - len(set(asked)), len(asked)))
        RUN[0] += 1


class WhatAWordSays(unittest.TestCase):
    """`numeral`: the string a tesseract word amounts to, or None."""

    def test_the_regex_alone_is_what_it_was(self):
        self.assertEqual(A.numeral("200"), "200")
        self.assertEqual(A.numeral("-20"), "-20")
        self.assertEqual(A.numeral("0.5"), "0.5")
        self.assertIsNone(A.numeral("200-"))
        self.assertIsNone(A.numeral("150,000"))
        self.assertIsNone(A.numeral("0,90"))
        RUN[0] += 1

    def test_commas_are_thousands_or_decimals_and_nothing_else(self):
        """REVERT: drop the comma handling. "150,000" and "0,90" then split
        into two numerals each, and the whitelist never sees a comma."""
        self.assertEqual(A.numeral("150,000", comma=True), "150000")
        self.assertEqual(A.numeral("1,000,000", comma=True), "1000000")
        self.assertEqual(A.numeral("0,90", comma=True), "0.90")
        self.assertEqual(A.numeral("-2,5", comma=True), "-2.5")
        self.assertIsNone(A.numeral("1,0000", comma=True))
        self.assertIsNone(A.numeral("12,34,5", comma=True))
        RUN[0] += 1


class TheSecondPass(unittest.TestCase):
    """Everything learnt at 600 DPI lives in a pass that runs only after the
    tuned search refused - because put into the first pass, each of these
    changed a reading that was right."""

    def test_tick_reach_is_the_ticks_and_not_the_spine_or_the_gridlines(self):
        """REVERT: take a percentile over every row. The spine is a rule
        several pixels wide and `spine_x` a column inside it, so most rows
        carry a 3 px run - publication 283's figure 2 had 647 of them against
        25 tick rows - and the reach came out 3 where the ticks were 31."""
        dark = np.zeros((400, 300), dtype=bool)
        dark[:, 197:201] = True                               # a spine 4 px wide
        for y in (50, 150, 250, 350):
            dark[y:y + 3, 170:200] = True                     # 30 px ticks
        dark[296:306, 0:200] = True                           # a gridline to the spine, 10 rows
        self.assertEqual(A.tick_reach(dark, 200, 0, 400, cap=60), 30)
        self.assertEqual(A.tick_reach(dark, 200, 0, 40, cap=60), 3,
                         "no tick: the spine's own thickness is the reach")
        RUN[0] += 1

    def test_the_magnification_keeps_the_glyph_size_tesseract_was_tuned_on(self):
        """REVERT: magnify x3 whatever the render. At 600 DPI that is where
        `5` reads as `9`: publication 360's 3.5 read 3.9 at x3, 3.5 at x1.5."""
        self.assertEqual(A.scale_for(A._TUNED_PANEL_PX), 3.0)
        self.assertEqual(A.scale_for(A._TUNED_PANEL_PX * 2), 1.5)
        self.assertEqual(A.scale_for(A._TUNED_PANEL_PX * 10), 1.0, "never below none")
        self.assertEqual(A.scale_for(A._TUNED_PANEL_PX / 2), 3.0, "never above the tuned")
        self.assertEqual(A.scale_for(None), 3)
        RUN[0] += 1

    def test_the_second_pass_starts_only_after_the_first_refused(self):
        """REVERT: run the second pass first, or fold its settings into the
        first. A comma in the first pass's whitelist read one panel's 3.5 as
        3.9; an anchor moved 2 px flipped a marginal read. Observed on the
        calls the search makes, so it needs no tesseract."""
        asked = []

        def spy(img, dark, left, right, top, bottom, scale=3, **kw):
            asked.append((bool(kw.get("comma")), int(right), float(scale)))
            return []

        img, dark, box, sx, base = panel_with_labels(2.0, tick=22, gap=72)
        real = A._ocr_numerals
        A._ocr_numerals = spy
        try:
            A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        flags = [c for c, _r, _s in asked]
        self.assertIn(True, flags, "the second pass never ran")
        self.assertIn(False, flags, "the first pass never ran")
        first_second = flags.index(True)
        self.assertNotIn(True, flags[:first_second])
        self.assertNotIn(False, flags[first_second:],
                         "a first-pass call after the second pass began")
        # and the second pass is the one with the 600 DPI settings
        second = [(r, s) for c, r, s in asked if c]
        reach = A.tick_reach(dark, sx, box[2], box[3], cap=max(10, (box[3] - box[2]) // 8))
        self.assertGreater(reach, 20, "the fixture's ticks were not measured")
        self.assertTrue(all(r <= sx - reach for r, _s in second),
                        "a second-pass strip reaches into the ticks: %s" % (second[:4],))
        self.assertTrue(all(s in (1.5, 2.0) for _r, s in second),
                        "the second pass did not magnify for the render: %s" % (sorted({s for _r, s in second}),))
        RUN[0] += 1

    def test_a_cut_strip_is_dropped_whole(self):
        """REVERT: drop only the words the guard flagged. A cut at the strip's
        edge crosses every right-aligned label of that width whether the guard
        can see it on each or not - a cut just after a decimal point leaves
        nothing on the middle rows. Publication RS-5362092's `0.74 0.72 0.70
        0.68` came back `74 72 70` unflagged beside a flagged `38`, and the
        three were a ladder: every value in the panel a hundred times too
        big. ("250 225 200" read as "50 25 0" is the same shape with every
        word flagged.) The strips are faked so the rule is observed by
        itself."""
        calls = []

        def fake(img, dark, left, right, top, bottom, scale=3, **kw):
            calls.append((int(left), int(right)))
            if right - left < 100:                              # narrow: cut after the point
                return [(74.0, 100.0, A.CLIP_NONE), (72.0, 200.0, A.CLIP_NONE),
                        (70.0, 300.0, A.CLIP_NONE), (38.0, 400.0, A.CLIP_STRIP)]
            return [(0.74, 100.0, A.CLIP_NONE), (0.72, 200.0, A.CLIP_NONE),
                    (0.70, 300.0, A.CLIP_NONE)]

        img, dark, box, sx, base = panel_with_labels(2.0)
        real = A._ocr_numerals
        A._ocr_numerals = fake
        try:
            got = A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        self.assertEqual([v for v, _r in got], [0.74, 0.72, 0.70], got)
        self.assertTrue(any(r - l < 100 for l, r in calls), "no narrow strip was tried first")
        RUN[0] += 1

    def test_a_dropped_glyph_costs_only_its_word(self):
        """REVERT: a clipped numeral disqualifies its whole strip. Publication
        S41467-023-41990-4's ECW axis, `5 0 -5 -10`: tesseract dropped the
        minus of -5 in a strip that held all four labels whole, the guard
        flagged the 5, the strip went out with 5, 0 and -10 in it, no other
        strip read three, and the axis was refused. A glyph dropped INSIDE the
        strip says nothing about the other words. Faked: the narrow strip is
        that strip, the wide one reads nothing."""

        def fake(img, dark, left, right, top, bottom, scale=3, **kw):
            if right - left < 100:
                return [(5.0, 100.0, A.CLIP_NONE), (0.0, 200.0, A.CLIP_NONE),
                        (5.0, 300.0, A.CLIP_WORD), (-10.0, 400.0, A.CLIP_NONE)]
            return []

        img, dark, box, sx, base = panel_with_labels(2.0)
        real = A._ocr_numerals
        A._ocr_numerals = fake
        try:
            got = A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        self.assertEqual(got, [(5.0, 100.0), (0.0, 200.0), (-10.0, 400.0)])
        RUN[0] += 1

    def test_a_cut_seen_at_either_magnification_condemns_the_union(self):
        """The union pass reads one strip at two magnifications and merges by
        row. The 0.74 strip above at x3 flags its `38` as a dropped glyph and
        at x4 as a cut; merged by "first flag wins" the cut is lost and the
        union is `74 72 70`, a ladder. The graver verdict has to win the
        merge. Faked so no single magnification ladders on its own."""

        def fake(img, dark, left, right, top, bottom, scale=3, **kw):
            if right - left >= 100:
                return []
            if abs(float(scale) - 3.0) < 1e-6:
                return [(74.0, 100.0, A.CLIP_NONE), (70.0, 300.0, A.CLIP_NONE),
                        (38.0, 400.0, A.CLIP_WORD)]
            return [(72.0, 200.0, A.CLIP_NONE), (38.0, 400.0, A.CLIP_STRIP)]

        img, dark, box, sx, base = panel_with_labels(2.0)
        real = A._ocr_numerals
        A._ocr_numerals = fake
        try:
            got = A.y_tick_labels(img, dark, box, sx, base)
        finally:
            A._ocr_numerals = real
        self.assertFalse(A.ladder(got)[0], "the cut strip's union was accepted: %s" % (got,))
        RUN[0] += 1

    def test_the_guard_tells_a_cut_from_a_dropped_glyph(self):
        """The classification itself, on real ink with tesseract faked: `-5`
        is drawn, and the reader is told only the `5` was read. With the strip
        holding the minus the word is `CLIP_WORD`; with the strip's edge
        between the minus and the 5 it is `CLIP_STRIP`. Same ink, same word,
        one question: does the word start at the strip's edge?"""
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        if A.pytesseract is None:
            self.skipTest("axis_reader has no pytesseract to fake")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("-5", "-15", "-25"), gap=100)
        x0, x1, y0, y1 = box
        rows = np.where(dark[y0:y1, :sx - 40].any(axis=1))[0] + y0
        yt, yb = int(rows.min()), int(rows.min() + 40)             # the first label's rows
        cols = np.where(dark[yt:yb, :sx - 40].any(axis=0))[0]
        runs = [[cols[0]]]
        for c in cols[1:]:
            (runs[-1].append(c) if c - runs[-1][-1] <= 3 else runs.append([c]))
        minus, digit = runs[0], runs[-1]                             # ink columns of - and 5
        gl, gr = int(digit[0]), int(digit[-1]) + 1
        top, bottom = max(0, y0 - 10), min(img.height, y1 + 6)

        def faked(left, scale):
            def image_to_data(big, config="", output_type=None):
                return {"text": ["5"], "conf": ["90"],
                        "left": [int((gl - left) * scale)], "top": [int((yt - top) * scale)],
                        "width": [int((gr - gl) * scale)], "height": [int((yb - yt) * scale)]}
            real = A.pytesseract.image_to_data
            A.pytesseract.image_to_data = image_to_data
            try:
                return A._ocr_numerals(img, dark, left, sx - 40, top, bottom, scale, with_clip=True)
            finally:
                A.pytesseract.image_to_data = real

        inside = faked(int(minus[0]) - 120, 1.5)
        at_edge = faked(int(minus[-1]) + 2, 1.5)
        self.assertEqual([(v, cl) for v, _r, cl in inside], [(5.0, A.CLIP_WORD)], inside)
        self.assertEqual([(v, cl) for v, _r, cl in at_edge], [(5.0, A.CLIP_STRIP)], at_edge)
        RUN[0] += 1

    def test_a_cut_digit_is_seen_as_clipped(self):
        """The clip test itself, on real ink: a strip whose left edge falls
        inside the `1` of 1400 reads 400 and flags it; one that holds the
        whole label reads 1400 and does not. (An edge that lands exactly in
        the gap between two digits is not seen - that is the guard's limit,
        and the overlay is where those are caught.)"""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("1400", "1200", "1000"), gap=100)
        x0, x1, y0, y1 = box
        cols = np.where(dark[y0:y1, :sx - 40].any(axis=0))[0]
        ink_left = int(cols.min())
        top, bottom = max(0, y0 - 10), min(img.height, y1 + 6)
        whole = A._ocr_numerals(img, dark, ink_left - 20, sx - 40, top, bottom, 1.5, with_clip=True)
        cut = A._ocr_numerals(img, dark, ink_left + 20, sx - 40, top, bottom, 1.5, with_clip=True)
        self.assertEqual([(v, cl) for v, _r, cl in whole], [(1400.0, False), (1200.0, False), (1000.0, False)])
        self.assertEqual([(v, cl) for v, _r, cl in cut],
                         [(400.0, A.CLIP_STRIP), (200.0, A.CLIP_STRIP), (0.0, A.CLIP_STRIP)])
        RUN[0] += 1

    def test_a_sign_left_of_the_strip_makes_the_word_untrusted(self):
        """REVERT: look only two pixels past the edge. Publication
        S0362119712070249 prints -10 -20 -30 -40 with the minus a third of an
        em to the left; a strip starting between the two read 10 20 30 40 - a
        ladder in good standing with the wrong sign, and every value in the
        panel flipped. The same look catches `0.8` read as `8`."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("-10", "-20", "-30"), gap=100)
        x0, x1, y0, y1 = box
        ink_left = int(np.where(dark[y0:y1, :sx - 40].any(axis=0))[0].min())
        top, bottom = max(0, y0 - 10), min(img.height, y1 + 6)
        signed = A._ocr_numerals(img, dark, ink_left - 20, sx - 40, top, bottom, 1.5, with_clip=True)
        unsigned = A._ocr_numerals(img, dark, ink_left + 18, sx - 40, top, bottom, 1.5, with_clip=True)
        self.assertEqual([(v, cl) for v, _r, cl in signed], [(-10.0, False), (-20.0, False), (-30.0, False)])
        self.assertEqual([(v, cl) for v, _r, cl in unsigned],
                         [(10.0, A.CLIP_STRIP), (20.0, A.CLIP_STRIP), (30.0, A.CLIP_STRIP)])
        RUN[0] += 1

    def test_ticks_inside_the_strip_are_read_past_in_the_second_pass(self):
        """The 283 shape, drawn: 200 150 100 with 44 px ticks. The tuned strips
        end 2 to 6 px from the spine and so hold the ticks; tesseract returns
        "200-" at confidence 0 and the first pass refuses. The second pass
        starts past the ticks and reads the axis."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("200", "150", "100"), tick=22, gap=72)
        pairs = A.y_tick_labels(img, dark, box, sx, base)
        self.assertEqual([v for v, _r in pairs], [200.0, 150.0, 100.0], pairs)
        RUN[0] += 1

    def test_a_negative_axis_is_read_with_its_sign(self):
        """The whole read, not the one strip: -10 -20 -30 come back negative,
        and an axis through zero (10, 0, -10) comes back as a ladder with a
        negative step. The single-strip test above shows the guard; this one
        shows the pass that runs in production keeps the sign it found."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("-10", "-20", "-30"), gap=100)
        pairs = A.y_tick_labels(img, dark, box, sx, base)
        self.assertEqual([v for v, _r in pairs], [-10.0, -20.0, -30.0], pairs)
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("10", "0", "-10"), gap=100)
        pairs = A.y_tick_labels(img, dark, box, sx, base)
        self.assertEqual([v for v, _r in pairs], [10.0, 0.0, -10.0], pairs)
        RUN[0] += 1

    def test_european_decimals_are_read_in_the_second_pass(self):
        """PIIS1566070202001327's axes: 1,00 0,90 ... 0,00. Without the comma
        they read as 1 00 0 90, and once as the ladder 9 .. 1 - ten times
        the printed value, accepted."""
        if not has_ocr():
            self.skipTest("no tesseract in this environment")
        if not os.path.exists(FONT):
            self.skipTest("no DejaVu font to draw numerals with")
        img, dark, box, sx, base = panel_with_labels(2.0, labels=("1,00", "0,90", "0,80"))
        pairs = A.y_tick_labels(img, dark, box, sx, base)
        self.assertEqual([v for v, _r in pairs], [1.0, 0.9, 0.8], pairs)
        RUN[0] += 1


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN[0])
    sys.exit(0 if result.wasSuccessful() else 1)
