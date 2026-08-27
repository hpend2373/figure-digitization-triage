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


def panel(label, box, run, baseline, ladder=False, sha="", ticks=(), spine=None,
          geometry="ANCHOR_FREE", completeness="COMPLETE", brk="NONE", points=None,
          value_sha=None):
    """One panel as `record` needs it, eligible by default so a scenario about
    something else does not have to say so."""
    return {"label": label, "box": tuple(box), "run": tuple(run) if run else None,
            "baseline": baseline, "ladder_ok": ladder,
            "calibration_sha": sha, "value_set_sha": value_sha or sha,
            "points": points or [], "ticks": list(ticks), "side": "LEFT",
            "axis_geometry": geometry, "completeness": completeness,
            "axis_break": brk,
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
        self.assertEqual(g[0]["status"], Y.ONE_PROVIDER)
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
        self.assertEqual(self.groups()[0]["status"], Y.MANY_PROVIDERS)
        self.assertEqual(int(self.groups()[0]["n_distinct_calibrations"]), 2)
        RUN[0] += 1

    def test_two_readers_are_a_count_and_a_distance_not_a_verdict(self):
        """`Y_SCALE_GROUP_AMBIGUOUS` was a verdict reached by comparing VALUE-SET
        hashes, and it was wrong in both directions: two panels printing the same
        numbers at different rows hashed the same, and one OCR miss made a panel
        that had not moved hash differently. So the band reports how many
        eligible providers it has and how far their LINES are apart, and decides
        nothing. Guard: MANY_PROVIDERS, n_eligible_providers, and
        cross_provider_max_resid_px."""
        same = [(100.0, 100.0), (50.0, 200.0), (0.0, 300.0)]
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  points=same),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "bbb",
                  points=same)])
        g = self.groups()[0]
        self.assertEqual(g["status"], Y.MANY_PROVIDERS)
        self.assertEqual(int(g["n_eligible_providers"]), 2)
        self.assertAlmostEqual(float(g["cross_provider_max_resid_px"]), 0.0,
                               places=6)
        RUN[0] += 1

    def test_the_same_numbers_at_different_rows_are_two_calibrations(self):
        """The defect the value-set hash could not see: both panels print
        0, 50, 100 and they are not the same scale.
        Guard: calibration_sha covering the (value, pixel) PAIRS."""
        import panel_geometry as G
        a = G.calibration("100:100;50:200;0:300", ladder_ok=True)
        b = G.calibration("100:100;50:250;0:400", ladder_ok=True)
        self.assertEqual(a["value_set_sha"], b["value_set_sha"])
        self.assertNotEqual(a["calibration_sha"], b["calibration_sha"])
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True,
                  a["calibration_sha"], points=a["points"],
                  value_sha=a["value_set_sha"]),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True,
                  b["calibration_sha"], points=b["points"],
                  value_sha=b["value_set_sha"])])
        g = self.groups()[0]
        self.assertEqual(int(g["n_distinct_calibrations"]), 2)
        self.assertGreater(float(g["cross_provider_max_resid_px"]), 20)
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
        self.assertEqual(self.groups()[0]["status"], Y.ONE_PROVIDER)
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
            self.assertEqual([r for r in T.ROWS
                              if r["kind"] == "Y_SCALE_GROUP"][0]["status"],
                             Y.ONE_PROVIDER)
            self.assertGreater(int(m["symmetric_max"]), 0)
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
            self.assertEqual(m["symmetric_max"], "")
            self.assertEqual(int(m["provider_unmatched"]), 2,
                             "the provider's ticks vanished from the count")
            self.assertEqual(int(m["n_ticks"]), 0)
        finally:
            T.ON = self._on
        RUN[0] += 1

    def test_the_mirror_reads_the_side_its_axis_faces(self):
        d, sx = self._panel(0, (56, 91))
        d2 = np.zeros((240, 900), dtype=bool)
        d2[30:190, 500:502] = True
        for y in (56, 91):
            d2[y:y + 3, 502:509] = True
        d2[188:191, 300:500] = True
        self.assertEqual(Y.tick_rows(d2, (300, 520, 20, 200), 500, (30, 190),
                                     "RIGHT"), [57, 92])
        RUN[0] += 1


class WhatTheBandMayClaim(unittest.TestCase):
    """The names were stronger than the evidence, and a picture drawn from them
    read as though a shared scale had been verified."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._y = T.ON, Y.ON
        T.ON, Y.ON = True, True

    def tearDown(self):
        T.ON, Y.ON = self._on, self._y

    def group(self):
        return [r for r in T.ROWS if r["kind"] == "Y_SCALE_GROUP"][0]

    def test_every_band_says_the_transfer_is_unvalidated(self):
        """Nothing here has been checked against a masked-label corpus, so no row
        may read as though it had. Guard: the transfer cell."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115)])
        self.assertEqual(self.group()["transfer"], Y.TRANSFER_UNVALIDATED)
        self.assertEqual(self.group()["status"], Y.ONE_PROVIDER)
        RUN[0] += 1

    def test_a_chained_band_is_labelled_chained(self):
        """min_pair_overlap was recorded and the status stayed the same, so a
        chained band and a real row read alike at a glance.
        Guard: the linkage cell."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 0, 100), (0, 100), 100, True, "aaa"),
            panel("P02", (210, 400, 0, 100), (50, 150), 150),
            panel("P03", (410, 600, 0, 100), (100, 200), 200)])
        self.assertEqual(self.group()["linkage"], Y.LINKAGE_CHAINED)
        RUN[0] += 1

    def test_a_real_row_is_not_labelled_chained(self):
        """A flag that fires on everything says nothing."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115)])
        self.assertEqual(self.group()["linkage"], Y.LINKAGE_COMPLETE)
        RUN[0] += 1


class ProviderEligibility(unittest.TestCase):
    """A ladder proves numerals were read beside SOME column."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._y = T.ON, Y.ON
        T.ON, Y.ON = True, True

    def tearDown(self):
        T.ON, Y.ON = self._on, self._y

    def test_a_ladder_off_a_fallback_column_may_not_lend_itself(self):
        """Publication 475's figure 1's panel C reads a ladder off a column no
        candidate search ever found. Lending that to the rest of its row would
        spread one unverified axis across three panels.
        Guard: the axis_geometry clause of eligibility()."""
        p = panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  geometry="FALLBACK_LONGEST")
        self.assertEqual(Y.eligibility(p)[0], Y.INELIGIBLE)
        Y.record(np.zeros((10, 10), dtype=bool), [
            p, panel("P02", (210, 400, 20, 120), (25, 115), 115)])
        g = [r for r in T.ROWS if r["kind"] == "Y_SCALE_GROUP"][0]
        self.assertEqual(g["status"], Y.NO_ELIGIBLE)
        self.assertEqual(g["provider_panel"], "")
        self.assertEqual(int(g["n_readers"]), 1)
        RUN[0] += 1

    def test_a_ladder_on_a_fragment_may_not_lend_itself(self):
        """Guard: the completeness clause."""
        p = panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  completeness="FRAGMENT")
        self.assertEqual(Y.eligibility(p)[0], Y.INELIGIBLE)
        self.assertIn("box FRAGMENT", "; ".join(Y.eligibility(p)[1]))
        RUN[0] += 1

    def test_a_broken_axis_may_not_lend_itself(self):
        """The labels below a break are not on the scale of the labels above it.
        Guard: the axis_break clause."""
        p = panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  brk="BROKEN:60-80")
        self.assertEqual(Y.eligibility(p)[0], Y.INELIGIBLE)
        RUN[0] += 1

    def test_an_answer_nobody_supplied_is_UNKNOWN_and_not_ELIGIBLE(self):
        """A default of ELIGIBLE would make every caller that forgets to pass the
        cells a caller that lends every ladder. Guard: the `not supplied` return."""
        p = panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa")
        del p["completeness"]
        self.assertEqual(Y.eligibility(p)[0], Y.ELIGIBILITY_UNKNOWN)
        RUN[0] += 1

    def test_a_clean_reader_is_eligible(self):
        """A gate that refuses everything is not a gate."""
        p = panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa")
        self.assertEqual(Y.eligibility(p), (Y.ELIGIBLE, []))
        RUN[0] += 1


class TicksMustTouchTheSpine(unittest.TestCase):
    """Ink NEAR the spine is not a tick mark."""

    def _fig(self):
        """A spine, four real ticks, and three things that are not ticks: a
        numeral stroke in the label column, a significance bracket, and a
        gridline reaching in from the plot side."""
        d = np.zeros((300, 400), dtype=bool)
        d[40:260, 100:102] = True                  # spine, 2 columns
        for y in (60, 110, 160, 210):
            d[y:y + 3, 94:100] = True              # ticks, touching
        d[70:90, 70:74] = True                     # a numeral stroke, detached
        d[120:124, 60:80] = True                   # a bracket, detached
        d[240:243, 102:200] = True                 # plot-side ink at another row
        return d

    def test_only_the_attached_marks_are_ticks(self):
        """The first version asked whether ANY ink lay in a four-column window
        and let a numeral stroke, a bracket and the baseline ink in: publication
        177 figure 2's panel P01 came back with six ticks where the axis has
        four. Guard: the contiguity walk in tick_runs."""
        d = self._fig()
        self.assertEqual(Y.tick_rows(d, (60, 300, 40, 260), 100, (40, 260), "LEFT"),
                         [61, 111, 161, 211])
        RUN[0] += 1

    def test_the_length_of_each_mark_is_recorded_and_not_capped(self):
        """Capping the length needs a constant nobody has measured. The lengths
        are reported so the distribution can be looked at.
        Guard: tick_runs returning the length."""
        d = self._fig()
        runs = Y.tick_runs(d, (60, 300, 40, 260), 100, (40, 260), "LEFT")
        self.assertEqual([ln for _a, _b, ln in runs], [6, 6, 6, 6])
        RUN[0] += 1

    def test_a_one_way_residual_cannot_see_a_missing_tick(self):
        """P02's three ticks matched P01's six at 1 px, and the three P01 ticks
        P02 does not have were invisible. Guard: match_ticks reporting both
        directions and the unmatched counts."""
        m = Y.match_ticks([37, 112, 188], [36, 111, 187, 248, 253, 261])
        self.assertEqual(m["target_to_provider_max"], 1)
        self.assertEqual(m["provider_to_target_max"], 73)
        self.assertEqual(m["symmetric_max"], 73)
        self.assertEqual(m["tick_match_count"], 3)
        self.assertEqual(m["provider_unmatched"], 3)
        self.assertEqual(m["target_unmatched"], 0)
        RUN[0] += 1

    def test_the_pairing_is_one_to_one(self):
        """Two target ticks may not both claim the same provider tick and be
        counted as two matches."""
        m = Y.match_ticks([100, 101], [100])
        self.assertEqual(m["tick_match_count"], 1)
        self.assertEqual(m["target_unmatched"], 1)
        RUN[0] += 1

    def test_the_line_residual_is_the_only_tolerance_free_comparison(self):
        """Where the target's values would land on the provider's line, against
        where the target read them. Guard: line_residual."""
        prov = {"points": [(100.0, 100.0), (50.0, 200.0), (0.0, 300.0)]}
        same = {"points": [(75.0, 150.0)]}
        off = {"points": [(75.0, 180.0)]}
        self.assertAlmostEqual(Y.line_residual(same, prov), 0.0, places=6)
        self.assertAlmostEqual(Y.line_residual(off, prov), 30.0, places=6)
        self.assertIsNone(Y.line_residual(same, {"points": [(1.0, 1.0)]}))
        RUN[0] += 1


class TheMetamorphicPair(unittest.TestCase):
    """The transfer test needs no masking: the corpus already holds bands where
    both panels read their own ladder, and those pairs carry ground truth."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._y = T.ON, Y.ON
        T.ON, Y.ON = True, True

    def tearDown(self):
        T.ON, Y.ON = self._on, self._y

    def checks(self):
        return [r for r in T.ROWS if r["kind"] == "TRANSFER_CHECK"]

    def test_two_panels_on_one_scale_transfer_with_no_error(self):
        """The case the whole idea rests on. Guard: transfer_error."""
        pts = [(100.0, 100.0), (50.0, 200.0), (0.0, 300.0)]
        got = Y.transfer_error({"points": pts}, {"points": pts})
        self.assertAlmostEqual(got["transfer_max_abs"], 0.0, places=6)
        self.assertAlmostEqual(got["transfer_max_rel"], 0.0, places=6)
        self.assertAlmostEqual(got["slope_rel_err"], 0.0, places=6)
        RUN[0] += 1

    def test_two_scales_in_one_band_are_measured_and_not_refused(self):
        """A band is a geometric relation. Whether it implies one y scale is the
        question the distribution is being built to answer, so the disagreement
        is a NUMBER here, not a verdict."""
        target = {"points": [(4.0, 100.0), (3.0, 200.0), (2.0, 300.0)]}
        source = {"points": [(100.0, 100.0), (50.0, 200.0), (0.0, 300.0)]}
        got = Y.transfer_error(target, source)
        self.assertGreater(got["transfer_max_rel"], 10)
        self.assertNotIn("verdict", got)
        RUN[0] += 1

    def test_the_error_is_normalised_by_the_targets_own_range(self):
        """A panel in mmHg and one in l/min/m2 cannot be put in one distribution
        on absolute error. Guard: the division by the target's span."""
        small = {"points": [(4.0, 100.0), (2.0, 300.0)]}
        big = {"points": [(400.0, 100.0), (200.0, 300.0)]}
        off_small = {"points": [(4.2, 100.0), (2.2, 300.0)]}
        off_big = {"points": [(420.0, 100.0), (220.0, 300.0)]}
        a = Y.transfer_error(small, off_small)
        b = Y.transfer_error(big, off_big)
        self.assertAlmostEqual(a["transfer_max_rel"], b["transfer_max_rel"],
                               places=6)
        self.assertNotAlmostEqual(a["transfer_max_abs"], b["transfer_max_abs"])
        RUN[0] += 1

    def test_a_panel_with_one_point_has_no_line_and_no_error(self):
        """Zero error against nothing is the strongest possible agreement
        reported for no evidence."""
        self.assertIsNone(Y.transfer_error({"points": [(1.0, 1.0)]},
                                           {"points": [(1.0, 1.0), (2.0, 2.0)]}))
        RUN[0] += 1

    def test_both_directions_are_recorded(self):
        """A -> B and B -> A are different measurements: the normalisation is by
        the TARGET's range, so the pair is not symmetric."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  points=[(100.0, 100.0), (0.0, 300.0)]),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "bbb",
                  points=[(4.0, 100.0), (2.0, 300.0)])])
        pairs = {(r["target"], r["source"]) for r in self.checks()}
        self.assertEqual(pairs, {("P01", "P02"), ("P02", "P01")})
        RUN[0] += 1

    def test_the_pair_carries_the_evidence_a_ladderless_target_would_have(self):
        """`same_calibration` cannot license a transfer: a pair whose
        calibrations agree is a pair that both READ, and needs no transfer. What
        a target with no ladder still has is its tick signature and its geometry,
        so those travel on the same row and the corpus can be asked whether they
        predict the error. Guard: the match_ticks and geometry fields."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  points=[(100.0, 100.0), (0.0, 300.0)], ticks=[30, 60, 90]),
            panel("P02", (210, 400, 20, 120), (26, 116), 116, True, "bbb",
                  points=[(4.0, 100.0), (2.0, 300.0)], ticks=[31, 61])])
        r = [x for x in self.checks() if x["target"] == "P02"][0]
        self.assertEqual(int(r["tick_match_count"]), 2)
        self.assertEqual(int(r["provider_unmatched"]), 1)
        self.assertEqual(int(r["symmetric_max"]), 29)
        self.assertEqual(int(r["d_baseline"]), 1)
        self.assertEqual(int(r["d_axis_top"]), 1)
        RUN[0] += 1

    def test_a_band_where_only_one_panel_reads_has_no_pair(self):
        """No ground truth, no metamorphic test. The pair is what makes it one."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  points=[(100.0, 100.0), (0.0, 300.0)]),
            panel("P02", (210, 400, 20, 120), (25, 115), 115)])
        self.assertEqual(self.checks(), [])
        RUN[0] += 1

    def test_the_pair_is_not_restricted_to_the_eligible_provider(self):
        """The question is what the BAND RELATION implies. Eligibility is a
        separate question about lending, and filtering on it here would measure
        the gate instead of the relation."""
        Y.record(np.zeros((10, 10), dtype=bool), [
            panel("P01", (10, 200, 20, 120), (25, 115), 115, True, "aaa",
                  points=[(100.0, 100.0), (0.0, 300.0)],
                  geometry="FALLBACK_LONGEST"),
            panel("P02", (210, 400, 20, 120), (25, 115), 115, True, "bbb",
                  points=[(4.0, 100.0), (2.0, 300.0)])])
        rows = self.checks()
        self.assertEqual(len(rows), 2)
        self.assertIn("INELIGIBLE", {r["source_eligibility"] for r in rows})
        RUN[0] += 1


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN[0])
    sys.exit(0 if result.wasSuccessful() else 1)
