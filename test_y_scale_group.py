#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenarios for the y scale group shadow.

    python3 test_y_scale_group.py

The pipeline assumed every panel carries its own ladder. Publication 177's
figure 2 refuses eleven of fifteen because it prints its y numerals once per
row, so the owner of a y scale is a ROW GROUP. These scenarios pin what the
shadow may claim - a group, a provider, and the raw residuals - and, just as
hard, what it may NOT: no tolerance, no transfer, no cell written into a panel.

Every scenario names the guard it holds. Reverting the guard must turn it red.
"""
import inspect
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import axis_reader as A                                          # noqa: E402
import gate_trace as T                                          # noqa: E402
import y_scale_group as Y                                        # noqa: E402

RUN = [0]


def panel(label, box, run, baseline, ladder=False, sha="", ticks=(), spine=None):
    return {"label": label, "box": tuple(box), "run": tuple(run) if run else None,
            "baseline": baseline, "ladder_ok": ladder, "sha": sha,
            "ticks": list(ticks), "side": "LEFT",
            "spine": box[0] + 10 if spine is None else spine}


class Grouping(unittest.TestCase):

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._y = T.ON, Y.ON
        T.ON, Y.ON = True, True

    def tearDown(self):
        T.ON, Y.ON = self._on, self._y

    def groups(self):
        return [r for r in T.ROWS if r["kind"] == "Y_SCALE_GROUP"]

    def members(self, gid=None):
        return [r for r in T.ROWS if r["kind"] == "Y_SCALE_MEMBER"
                and (gid is None or r["group_id"] == gid)]

    def test_three_panels_in_a_row_are_one_group(self):
        """The 177 shape: one provider, two dependants.
        Guard: bands(), and the single-calibration branch."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115),
            panel("P03", (410, 600, 20, 120), (25, 115), 115)])
        g = self.groups()
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["status"], Y.SHARED_ROW_CANDIDATE)
        self.assertEqual(g[0]["provider_panel"], "P01")
        self.assertEqual(g[0]["member_panels"], "P01;P02;P03")
        RUN[0] += 1

    def test_the_grouping_is_on_the_axis_runs_and_not_the_boxes(self):
        """An invented box can be far taller than the axis inside it, and
        grouping on boxes lets one such box pull in the row above - which would
        hand a panel the wrong row's calibration.
        Guard: bands() reading p["run"]."""
        tall = panel("P09", (410, 600, 0, 400), (300, 390), 390)
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            tall])
        g = self.groups()
        self.assertEqual(len(g), 2, "the tall box joined a row its axis is not in")
        RUN[0] += 1

    def test_a_chained_band_reports_its_weakest_pair(self):
        """Single linkage can walk from one row to the next through overlapping
        middles. It is not forbidden here - forbidding it needs a tolerance - it
        is REPORTED, so a chained band is visible instead of asserted away.
        Guard: min_pair_overlap."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 0, 100), (0, 100), 100, True, "aaa"),
            panel("P02", (210, 400, 0, 100), (50, 150), 150),
            panel("P03", (410, 600, 0, 100), (100, 200), 200)])
        g = self.groups()
        self.assertEqual(len(g), 1)
        self.assertLess(float(g[0]["min_pair_overlap"]), A.ADOPT_SHARE)
        RUN[0] += 1

    def test_a_row_with_no_reader_says_so_and_compares_nothing(self):
        """Publication 177's figure 2 row 4: P10 is the leftmost panel and refuses
        its own ladder, so nothing in that row can lend one. Reporting it as a
        shared-axis row with two dependants is what the last round's prose did.
        Guard: the `if not readers` branch."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P10", (10, 200, 20, 120), (25, 115), 115),
            panel("P11", (210, 400, 20, 120), (25, 115), 115),
            panel("P12", (410, 600, 20, 120), (25, 115), 115)])
        g = self.groups()
        self.assertEqual(g[0]["status"], Y.NO_PROVIDER)
        self.assertEqual(g[0]["provider_panel"], "")
        for m in self.members():
            self.assertNotIn("d_baseline", m,
                             "a residual was measured against a provider that "
                             "does not exist")
        RUN[0] += 1

    def test_two_different_calibrations_in_one_row_is_ambiguous(self):
        """Choosing between them by position or discovery order is the tie-break
        this project keeps having to withdraw.
        Guard: the `len(shas) > 1` branch."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "bbb")])
        self.assertEqual(self.groups()[0]["status"], Y.AMBIGUOUS)
        self.assertEqual(int(self.groups()[0]["n_distinct_calibrations"]), 2)
        RUN[0] += 1

    def test_two_readers_of_the_SAME_ladder_are_not_ambiguous(self):
        """A figure that repeats its numerals on every panel has as many readers
        as panels, and calling that ambiguous would refuse the easy case.
        Guard: the distinctness being over the SHA, not the reader count."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "aaa")])
        g = self.groups()[0]
        self.assertEqual(g["status"], Y.SHARED_ROW_CANDIDATE)
        self.assertEqual(int(g["n_readers"]), 2)
        self.assertEqual(int(g["n_distinct_calibrations"]), 1)
        RUN[0] += 1

    def test_a_member_that_read_a_different_ladder_is_a_conflict(self):
        """Not a tolerance question: the two read different NUMBERS off one row.
        Guard: the DISAGREES branch."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "bbb")])
        m = [r for r in self.members() if r["panel"] == "P02"][0]
        self.assertEqual(m["conflict"], Y.DISAGREES)
        RUN[0] += 1

    def test_no_tolerance_is_applied_to_any_residual(self):
        """A member 40 rows off in baseline and 60 in axis top is still recorded
        as a candidate WITH THOSE NUMBERS. Refusing it would need a tolerance
        nobody has measured, and inventing one here is what the whole round is
        against. Guard: the absence of any comparison in `record`."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 200), (30, 190), 190, True, "aaa"),
            panel("P02", (210, 400, 20, 200), (90, 195), 150)])
        self.assertEqual(self.groups()[0]["status"], Y.SHARED_ROW_CANDIDATE)
        m = [r for r in self.members() if r["panel"] == "P02"][0]
        self.assertEqual(int(m["d_baseline"]), -40)
        self.assertEqual(int(m["d_axis_top"]), 60)
        RUN[0] += 1

    def test_it_records_and_is_never_handed_the_proposal_list(self):
        """Like every other shadow in this package. Guard: the signature."""
        self.assertEqual(list(inspect.signature(Y.record).parameters),
                         ["dark", "panels"])
        RUN[0] += 1

    def test_with_the_flag_off_nothing_is_recorded(self):
        """Guard: the `if not (ON and T.ON)` return."""
        Y.ON = False
        self.assertEqual(Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa")]), [])
        self.assertEqual(self.groups(), [])
        RUN[0] += 1

    def test_zero_turns_the_flag_off(self):
        """`bool(os.environ.get("YGROUP"))` is True for "0". Guard: the `!= "0"`."""
        import importlib, os as _os
        for value, want in ((None, False), ("0", False), ("1", True)):
            old = _os.environ.pop("YGROUP", None)
            try:
                if value is not None:
                    _os.environ["YGROUP"] = value
                self.assertEqual(importlib.reload(Y).ON, want,
                                 "YGROUP=%r read as %r" % (value, Y.ON))
            finally:
                _os.environ.pop("YGROUP", None)
                if old is not None:
                    _os.environ["YGROUP"] = old
        importlib.reload(Y)
        RUN[0] += 1


class TickRowSignature(unittest.TestCase):
    """The one piece of evidence a panel with no numerals can still offer."""

    def _panel(self, ox, tick_rows, spine_w=2, run=(30, 190)):
        """A spine `spine_w` columns wide with short marks on its label side."""
        d = np.zeros((240, 900), dtype=bool)
        sx = ox + 40
        d[run[0]:run[1], sx:sx + spine_w] = True
        for y in tick_rows:
            d[y:y + 3, sx - 6:sx] = True
        d[run[1] - 2:run[1] + 1, sx:ox + 220] = True       # baseline
        return d, sx

    def test_the_window_starts_outside_the_spines_own_rule(self):
        """A 2 px spine and a window fixed 4 px wide means every row of the axis
        reads as a tick and the signature becomes the whole run. The window is
        measured from the END of the rule instead.
        Guard: spine_cols(), and tick_rows() using it."""
        # `spine_and_baseline` returns ONE column of the rule and it need not be
        # the first: here the reported spine is the rule's last column, so a
        # window taken from it backwards sits INSIDE the rule.
        d, sx = self._panel(0, (56, 91, 126, 161), spine_w=3)
        got = Y.tick_rows(d, (0, 220, 20, 200), sx + 2, (30, 190), "LEFT")
        self.assertEqual(got, [57, 92, 127, 162])
        self.assertEqual(Y.spine_cols(d, (0, 220, 20, 200), sx + 2), (sx, sx + 2))
        RUN[0] += 1

    def test_two_panels_labelled_on_the_same_rows_match(self):
        """What a shared y scale looks like when neither panel has numerals."""
        d1, s1 = self._panel(0, (56, 91, 126, 161))
        d2, s2 = self._panel(300, (56, 91, 126, 161))
        a = Y.tick_rows(d1, (0, 220, 20, 200), s1, (30, 190), "LEFT")
        b = Y.tick_rows(d2, (300, 520, 20, 200), s2, (30, 190), "LEFT")
        self.assertEqual(a, b)
        RUN[0] += 1

    def test_a_different_scale_shows_up_as_a_tick_residual(self):
        """A log axis, or an axis break on one side only, puts the ticks
        somewhere else. The shadow does NOT refuse the group for it - refusing
        needs a tolerance - it records the residual, which is what the corpus
        distribution has to be built from before anything is promoted."""
        prov = panel("P01", (0, 220, 20, 200), (30, 190), 188, True, "aaa",
                     ticks=[57, 92, 127, 162])
        log = panel("P02", (300, 520, 20, 200), (30, 190), 188,
                    ticks=[40, 70, 120, 175])
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, Y.ON, T.ON = T.ON, True, True
        try:
            Y.record(np.zeros((10, 10), dtype=bool), [prov, log])
            m = [r for r in T.ROWS if r["kind"] == "Y_SCALE_MEMBER"
                 and r["panel"] == "P02"][0]
            self.assertEqual(r"SHARED_ROW_CANDIDATE",
                             [r for r in T.ROWS
                              if r["kind"] == "Y_SCALE_GROUP"][0]["status"])
            self.assertGreater(int(m["tick_residual_max"]), 0)
            self.assertEqual(int(m["n_ticks"]), 4)
        finally:
            T.ON = self._on
        RUN[0] += 1

    def test_a_panel_with_no_ticks_has_no_residual_rather_than_a_zero(self):
        """A zero residual against nothing is the strongest possible agreement
        reported for the weakest possible evidence."""
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, Y.ON, T.ON = T.ON, True, True
        try:
            Y.record(np.zeros((10, 10), dtype=bool), [
                panel("P01", (0, 220, 20, 200), (30, 190), 188, True, "aaa",
                      ticks=[57, 92]),
                panel("P02", (300, 520, 20, 200), (30, 190), 188)])
            m = [r for r in T.ROWS if r["kind"] == "Y_SCALE_MEMBER"
                 and r["panel"] == "P02"][0]
            self.assertEqual(m["tick_residual_max"], "")
            self.assertEqual(int(m["n_ticks"]), 0)
        finally:
            T.ON = self._on
        RUN[0] += 1

    def test_the_mirror_reads_the_side_its_axis_faces(self):
        d, sx = self._panel(0, (56, 91))
        d2 = np.zeros((240, 900), dtype=bool)
        d2[30:190, 500:502] = True
        for y in (56, 91):
            d2[y:y + 3, 503:509] = True
        d2[188:191, 300:500] = True
        self.assertEqual(Y.tick_rows(d2, (300, 520, 20, 200), 500, (30, 190),
                                     "RIGHT"), [57, 92])
        RUN[0] += 1


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN[0])
    sys.exit(0 if result.wasSuccessful() else 1)
