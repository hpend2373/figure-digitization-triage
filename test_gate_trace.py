# -*- coding: utf-8 -*-
"""What the trace records, and what it costs when it is off.

    python3 test_gate_trace.py

The overlay draws one red box for three different failures and the footer counts
two of them, so a picture of publication 475's figure 1 says the harness failed
and not WHERE. These scenarios pin the rows that answer "where": every axis
candidate the anchor search saw, which one it took and why, and - for each piece
the cut discarded - whether it reached the six statements or was refused before
them, with the refusal in numbers that can be acted on.

Every scenario is paired with one guard, named in its docstring. Reverting the
guard must turn the scenario red; that check is run each round and its output is
in `INSTALL.md`.
"""
import csv
import io
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import axis_reader as A                                          # noqa: E402
import gate_trace as T                                           # noqa: E402

RUN = [0]


class Recording(unittest.TestCase):

    def setUp(self):
        T.reset()
        T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON

    def tearDown(self):
        T.ON = self._on

    def test_with_the_flag_off_nothing_is_recorded(self):
        """The trace may not cost the pipeline anything it is not asked for. With
        `TRACE` unset every call is a branch not taken, which is what lets
        `harness_compare` show the output is byte-identical.
        Guard: the `if not ON: return` in add()."""
        T.ON = False
        for i in range(50):
            T.add("ORPHAN", orphan="1,2,3,4", outcome="TOO_SMALL")
        self.assertEqual(T.ROWS, [])
        self.assertIsNone(T.dump("/tmp/should_not_exist_%d.csv" % os.getpid()))
        RUN[0] += 1

    def test_every_row_carries_the_pass_it_belongs_to(self):
        """A trace that does not say which mode and ink a row came from cannot be
        filtered to the pass that won, and the first trace of 475 figure 1
        labelled its selected rows with the last combination tried.
        Guard: context() merged into every row by add()."""
        T.ON = True
        T.context(pid="475", fig="Fig. 1", png="x.png", mode="OFF", ink="151")
        T.add("SELECTED", panel="P01")
        T.context(mode="GRID", ink="140")
        T.add("SELECTED", panel="P02")
        self.assertEqual([(r["mode"], r["ink"], r["panel"]) for r in T.ROWS],
                         [("OFF", "151", "P01"), ("GRID", "140", "P02")])
        RUN[0] += 1

    def test_the_dump_is_one_table_with_a_stable_prefix(self):
        """Kinds carry different fields, and a reader still has to be able to sort
        and filter. Guard: dump()'s fixed `order` then discovered columns."""
        T.ON = True
        # BUILT WITHOUT add(), on purpose. add() seeds every row from the context
        # and so happens to put the prefix first; the `order` list is what
        # guarantees it when a row does not come from there.
        T.ROWS.append({"outcome": "NO_PANEL_IN_REACH", "orphan": "1,2,3,4",
                       "kind": "ORPHAN", "mode": "OFF", "ink": "140",
                       "pid": "1", "fig": "F", "png": "p"})
        T.ROWS.append({"c_rows": "O", "accepted": False, "kind": "GATE",
                       "orphan": "1,2,3,4", "pid": "1", "fig": "F", "png": "p",
                       "mode": "OFF", "ink": "140"})
        path = "/tmp/gt_%d.csv" % os.getpid()
        T.dump(path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0])[:6],
                         ["pid", "fig", "png", "mode", "ink", "kind"])
        self.assertEqual([r["kind"] for r in rows], ["ORPHAN", "GATE"])
        self.assertEqual(rows[1]["outcome"], "")       # absent, not missing
        os.remove(path)
        RUN[0] += 1

    def test_the_summary_separates_refused_from_offered(self):
        """The whole point: a refusal BEFORE the gate and a refusal BY the gate are
        different repairs. Guard: summary()'s per-outcome counter."""
        T.ON = True
        for i in range(3):
            T.add("ORPHAN", outcome="NO_PANEL_IN_REACH")
        T.add("ORPHAN", outcome="OFFERED")
        s = T.summary()
        self.assertIn("NO_PANEL_IN_REACH 3", s)
        self.assertIn("OFFERED 1", s)
        RUN[0] += 1


class WhyNoPanelWasInReach(unittest.TestCase):
    """`axis_reader._nearest_note`: a refusal in numbers that can be acted on."""

    def test_the_note_reports_the_best_candidate_on_each_side(self):
        """The first version reported the NEAREST box, which is always an
        overlapping one at 0 px, so it said nothing. What decides the prefilter is
        the gap AND the shared rows, per side.
        Guard: `if side not in best or vsh > best[side][1]`."""
        # THE SIDE IS THE PIECE'S, NOT THE PANEL'S - `adopt_orphans` names the side
        # of the PANEL the piece lies on, and the note keeps that vocabulary. A
        # panel 30 px to the piece's right is therefore reported as "left".
        # BOTH BOXES ON THE SAME SIDE, which is the only case a tie-break decides:
        # the closer one shares no rows, the farther one shares all of them. The
        # near miss is the second, and reporting the first says nothing.
        orp = (200, 300, 100, 200)
        boxes = [(305, 400, 900, 1000),     # 5 px away, no shared rows
                 (330, 430, 100, 200)]      # 30 px away, shares every row
        note = A._nearest_note(orp, boxes, {})
        self.assertIn("left 30px share 1.00", note)
        self.assertNotIn("left 5px", note)
        RUN[0] += 1

    def test_the_note_names_which_of_the_two_conditions_failed(self):
        """"Nobody in reach" cannot be acted on; "[gap]" and "[share]" can, and on
        475 figure 1 the answer is that a piece with a perfect row overlap missed
        on distance by 10 px. Guard: the [gap]/[share] suffixes."""
        orp = (200, 300, 100, 200)
        far = A._nearest_note(orp, [(500, 600, 100, 200)], {})
        self.assertIn("[gap]", far)
        self.assertNotIn("[share]", far)
        near_but_unshared = A._nearest_note(orp, [(305, 400, 900, 1000)], {})
        self.assertIn("[share]", near_but_unshared)
        RUN[0] += 1

    def test_a_candidate_that_passes_both_is_not_marked(self):
        """A note that flags everything flags nothing."""
        orp = (200, 300, 100, 200)
        ok = A._nearest_note(orp, [(305, 400, 100, 200)], {})
        self.assertNotIn("[gap]", ok)
        self.assertNotIn("[share]", ok)
        RUN[0] += 1


class AxisCandidates(unittest.TestCase):
    """`axis_reader._axis_anchor`: every vertical it saw, and why it took one."""

    def setUp(self):
        T.reset()
        T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON
        T.ON = True
        A._RUN_CACHE.clear()
        A._ANCHOR_CACHE.clear()

    def tearDown(self):
        T.ON = self._on

    def _raster(self):
        """A box holding two long verticals: one ending inside it, one cut by its
        bottom edge. This is publication 475 figure 1's panel D in miniature."""
        d = np.zeros((400, 400), dtype=bool)
        d[100:260, 120] = True              # runs free inside the box
        d[200:400, 60] = True               # touches the bottom edge: clipped
        return d

    def test_it_records_the_candidates_it_did_not_take(self):
        """"The blue line is on an error bar" is only actionable if the row names
        the column that was available instead. Guard: the AXIS_CANDIDATES row."""
        d = self._raster()
        got = A._axis_anchor(d, (40, 300, 90, 300))
        row = [r for r in T.ROWS if r["kind"] == "AXIS_CANDIDATES"][0]
        self.assertIn("120:100-260:free", row["candidates"])
        self.assertIn("60:200-400:clipped", row["candidates"])
        self.assertEqual(row["selected_x"], 120)
        self.assertEqual(got[0], 120)
        RUN[0] += 1

    def test_it_records_free_beating_clipped_as_the_reason(self):
        """That preference is the mechanism: on 475 figure 1's panel D the panel's
        own axis is clipped by the box edge, so a shorter run standing on a bar
        wins. The reason has to say so. Guard: the `reason` field."""
        d = self._raster()
        A._axis_anchor(d, (40, 300, 90, 300))
        row = [r for r in T.ROWS if r["kind"] == "AXIS_CANDIDATES"][0]
        self.assertIn("free", row["reason"])
        self.assertEqual(row["n_free"], 1)
        self.assertEqual(row["n_clipped"], 1)
        RUN[0] += 1

    def test_a_box_with_only_clipped_runs_says_so(self):
        """A box whose every candidate is cut by its own edges is the weakest case
        there is, and the function STILL RETURNS ONE - `pick = free or clipped`.
        That is what publication 475's figure 1's P07 is.

        THIS SCENARIO PINS WHAT THE CODE DOES, NOT WHAT IT SHOULD DO. An earlier
        version of this docstring said such a box "contains no axis", which is a
        contract the runtime does not have: the prose asserted one thing and the
        function did another, which is the decoration problem one level up. What
        the box should return instead is a change to the pipeline's output and
        belongs to its own arm; `gate_trace.AXIS_UNRESOLVED` is the name it is
        counted under until then.
        Guard: the clipped fallback branch of `reason`."""
        d = np.zeros((400, 400), dtype=bool)
        d[90:300, 60] = True                # spans the whole box: cut both ends
        got = A._axis_anchor(d, (40, 300, 90, 300))
        row = [r for r in T.ROWS if r["kind"] == "AXIS_CANDIDATES"][0]
        self.assertEqual(row["n_free"], 0)
        self.assertIn("no free run", row["reason"])
        self.assertEqual(got[0], 60, "the runtime returns the clipped candidate")
        self.assertEqual(T.axis_status(0, 2, anchored=True, ladder_ok=True),
                         T.AXIS_UNRESOLVED)
        RUN[0] += 1

    def test_a_box_with_no_long_run_says_that_instead(self):
        """Panel C's box: nothing passed, so the spine came from the fallback and
        the trace has to distinguish that from a bad choice."""
        A._axis_anchor(np.zeros((400, 400), dtype=bool), (40, 300, 90, 300))
        row = [r for r in T.ROWS if r["kind"] == "AXIS_CANDIDATES"][0]
        self.assertEqual(row["selected_x"], "")
        self.assertIn("no run long enough", row["reason"])
        RUN[0] += 1


class AxisStatus(unittest.TestCase):
    """`gate_trace.axis_status`: the four states the overlay drew as one line."""

    def test_no_candidate_at_all_is_not_the_same_as_a_bad_one(self):
        """Panel C's box: nothing passed the anchor test, so the spine came from
        the plain longest-vertical fallback. Its LADDER_OK means a ladder could be
        read off that column, not that the column is the panel's axis.
        Guard: the `if not anchored` branch."""
        self.assertEqual(T.axis_status(0, 0, anchored=False, ladder_ok=True),
                         T.AXIS_FALLBACK_ONLY)
        self.assertEqual(T.axis_status(3, 1, anchored=False, ladder_ok=True),
                         T.AXIS_FALLBACK_ONLY)
        RUN[0] += 1

    def test_clipped_only_outranks_the_ladder(self):
        """P07 reads no ladder, but a clipped-only box that DID read one is still
        the weakest case: the ladder says a column of numerals was found beside
        that vertical, not that the vertical is an axis.
        Guard: the clipped-only branch coming before the ladder branch."""
        self.assertEqual(T.axis_status(0, 2, anchored=True, ladder_ok=True),
                         T.AXIS_UNRESOLVED)
        self.assertEqual(T.axis_status(0, 2, anchored=True, ladder_ok=False),
                         T.AXIS_UNRESOLVED)
        RUN[0] += 1

    def test_a_free_candidate_is_attested_only_by_its_ladder(self):
        """The difference between P06 (true axis, ladder reads) and P03 (a run on
        a bar, ladder refused) is the ladder and nothing else."""
        self.assertEqual(T.axis_status(2, 2, anchored=True, ladder_ok=True),
                         T.AXIS_ATTESTED)
        self.assertEqual(T.axis_status(2, 2, anchored=True, ladder_ok=False),
                         T.AXIS_GEOMETRY_ONLY)
        RUN[0] += 1

    def test_every_kind_the_recorder_writes_is_in_KINDS(self):
        """`summary()` counts by KINDS, so a kind missing from it is a kind the
        terminal never mentions - GATE_WHY and SELECTED_PASS were both missing.
        Guard: the KINDS tuple."""
        written = ("AXIS_CANDIDATES", "AXIS_FALLBACK", "AXIS_SHADOW_LADDER",
                   "ORPHAN", "GATE", "GATE_WHY", "POST", "FRAGMENT_DECISION",
                   "SELECTED_PASS", "SELECTED")
        self.assertEqual(set(written) - set(T.KINDS), set())
        T.ON = True
        T.reset()
        for k in written:
            T.add(k)
        s = T.summary()
        for k in written:
            self.assertIn(k, s, "%s is recorded but never summarised" % k)
        RUN[0] += 1


class FallbackAxisIsTraced(unittest.TestCase):
    """`spine_and_baseline` records why it picked a column, because on 475
    figure 1's panel C that column is the only thing behind a LADDER_OK."""

    def setUp(self):
        T.reset()
        T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON
        T.ON = True
        A._RUN_CACHE.clear()
        A._ANCHOR_CACHE.clear()

    def tearDown(self):
        T.ON = self._on

    def test_the_fallback_records_its_candidates_and_its_rule(self):
        """A scenario asserting only "the fallback was used" cannot see whether
        the trace says WHICH columns were available or why one won.
        Guard: the AXIS_FALLBACK row in spine_and_baseline."""
        d = np.zeros((400, 400), dtype=bool)
        d[100:300, 150] = True              # 200 px - the longest
        d[120:280, 90] = True               # 160 px, further left
        A.spine_and_baseline(d, (60, 300, 90, 320))
        rows = [r for r in T.ROWS if r["kind"] == "AXIS_FALLBACK"]
        self.assertTrue(rows, "the fallback wrote no row")
        row = rows[0]
        self.assertIn("150:", row["candidates"])
        self.assertIn("90:", row["candidates"])
        self.assertIn("leftmost column whose run is", row["reason"])
        self.assertEqual(row["longest"], 200)
        RUN[0] += 1

    def test_the_row_names_the_column_that_was_chosen(self):
        """The tie rule takes the LEFTMOST column within AXIS_TIE of the longest,
        which is not the longest - and the overlay drew both the same."""
        d = np.zeros((400, 400), dtype=bool)
        d[100:300, 150] = True
        d[100:299, 90] = True               # 1 px shorter, well inside the tie
        A.spine_and_baseline(d, (60, 300, 90, 320))
        row = [r for r in T.ROWS if r["kind"] == "AXIS_FALLBACK"][0]
        self.assertEqual(row["selected_x"], 90)
        self.assertEqual(row["longest"], 200)
        RUN[0] += 1


if __name__ == "__main__":
    loaded = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(loaded)
    print("FDT_SCENARIOS_RUN=%d" % result.testsRun)
    sys.exit(0 if result.wasSuccessful() else 1)
