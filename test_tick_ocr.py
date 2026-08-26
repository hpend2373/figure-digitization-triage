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


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN[0])
    sys.exit(0 if result.wasSuccessful() else 1)
