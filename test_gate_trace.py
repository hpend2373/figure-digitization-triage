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
import inspect
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
        written = ("CUT", "AXIS_CANDIDATES", "AXIS_FALLBACK",
                   "AXIS_SHADOW_LADDER", "REGION", "ORPHAN", "PIECE_RELATION",
                   "POST_ADOPTION_SHADOW", "GATE",
                   "GATE_WHY", "GATE_SHADOW", "GATE_SHADOW_WHY", "POST",
                   "FRAGMENT_DECISION", "SELECTED_PASS", "SELECTED")
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


class CutLineage(unittest.TestCase):
    """`_cut` remembers which two halves it made, so "these were severed from one
    another" is recoverable. It was not, at any price."""

    def setUp(self):
        T.reset()
        T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._sg = T.ON, A.SHADOW_GATE
        T.ON = True
        A.CUT_LINEAGE.clear()
        A._CUT_SEQ[0] = 0
        A._RUN_CACHE.clear()
        A._ANCHOR_CACHE.clear()

    def tearDown(self):
        T.ON, A.SHADOW_GATE = self._on, self._sg

    def _two_panels(self):
        """Two blocks with a wide column gutter between them: one cut, two halves,
        each half a panel with its own axis and bars."""
        d = np.zeros((300, 620), dtype=bool)
        for sx in (60, 400):
            d[40:240, sx] = True                       # a spine
            d[239, sx:sx + 200] = True                 # a baseline
            for bx in (90, 150, 210):
                d[140:239, sx + bx - 60:sx + bx - 40] = True
        return d

    def test_both_halves_of_one_cut_point_at_each_other(self):
        """Guard: _remember_cut writing an entry for each half."""
        out = []
        A._cut(self._two_panels(), (0, 620, 0, 300), 0, out)
        self.assertGreaterEqual(len(A.CUT_LINEAGE), 2)
        pairs = {}
        for box, rec in A.CUT_LINEAGE.items():
            pairs.setdefault(rec["cut_id"], []).append((box, rec))
        for cid, members in pairs.items():
            self.assertEqual(len(members), 2, "cut %s has %d halves" % (cid, len(members)))
            (ba, ra), (bb, rb) = members
            self.assertEqual(ra["sibling"], bb)
            self.assertEqual(rb["sibling"], ba)
            self.assertIn(ra["axis"], ("row", "col"))
            self.assertGreater(ra["gap_hi"] - ra["gap_lo"], 0)
        RUN[0] += 1

    def _stacked(self):
        """Two blocks with a wide ROW gutter: the other branch of the same cut."""
        d = np.zeros((620, 300), dtype=bool)
        for sy in (40, 380):
            d[sy:sy + 200, 60] = True
            d[sy + 199, 60:260] = True
            for bx in (90, 150, 210):
                d[sy + 100:sy + 199, bx:bx + 20] = True
        return d

    def test_a_row_cut_is_remembered_too(self):
        """Both branches of `_cut` have to write the lineage; a scenario with only
        a column gutter cannot see the row branch at all."""
        out = []
        A._cut(self._stacked(), (0, 300, 0, 620), 0, out)
        axes = {rec["axis"] for rec in A.CUT_LINEAGE.values()}
        self.assertIn("row", axes)
        RUN[0] += 1

    def test_the_cut_is_recorded_as_a_trace_row(self):
        """A lineage only in memory cannot be read after the run."""
        out = []
        A._cut(self._two_panels(), (0, 620, 0, 300), 0, out)
        cuts = [r for r in T.ROWS if r["kind"] == "CUT"]
        self.assertTrue(cuts)
        self.assertIn(cuts[0]["axis"], ("row", "col"))
        self.assertGreater(int(cuts[0]["gap_px"]), 0)
        RUN[0] += 1

    def test_a_panel_inside_the_sibling_half_is_a_cut_sibling(self):
        """Containment, not equality: the sibling half is usually cut again before
        it becomes a panel. Guard: cut_sibling_of's containment test."""
        A.CUT_LINEAGE[(0, 100, 0, 100)] = {
            "cut_id": 1, "sibling": (100, 300, 0, 100), "axis": "col",
            "gap_lo": 95, "gap_hi": 105, "depth": 0}
        self.assertIsNotNone(A.cut_sibling_of((0, 100, 0, 100), (120, 280, 10, 90)))
        self.assertIsNotNone(A.cut_sibling_of((0, 100, 0, 100), (100, 300, 0, 100)))
        RUN[0] += 1

    def test_a_trimmed_piece_still_finds_the_half_it_came_from(self):
        """`panels` trims every leaf before offering it as an orphan, so the piece
        the gate sees is not the half the cut made and its tuple is not a key.
        The first run of the shadow gate recorded ZERO verdicts for exactly that.
        Guard: the containment fallback in cut_sibling_of."""
        A.CUT_LINEAGE[(0, 100, 0, 100)] = {
            "cut_id": 1, "sibling": (100, 300, 0, 100), "axis": "col",
            "gap_lo": 95, "gap_hi": 105, "depth": 0}
        trimmed = (12, 88, 20, 80)
        self.assertNotIn(trimmed, A.CUT_LINEAGE)
        rec = A.cut_sibling_of(trimmed, (120, 280, 10, 90))
        self.assertIsNotNone(rec)
        self.assertEqual(rec["cut_id"], 1)
        RUN[0] += 1

    def test_the_smallest_containing_half_wins(self):
        """A piece is inside every ancestor half; the one it came OUT of is the
        smallest. Taking any of them would make a distant panel a sibling."""
        A.CUT_LINEAGE[(0, 400, 0, 400)] = {
            "cut_id": 1, "sibling": (400, 800, 0, 400), "axis": "col",
            "gap_lo": 395, "gap_hi": 405, "depth": 0}
        A.CUT_LINEAGE[(0, 100, 0, 100)] = {
            "cut_id": 2, "sibling": (100, 400, 0, 100), "axis": "col",
            "gap_lo": 95, "gap_hi": 105, "depth": 1}
        rec = A.cut_sibling_of((10, 90, 10, 90), (120, 380, 10, 90))
        self.assertEqual(rec["cut_id"], 2)
        RUN[0] += 1

    def test_a_panel_outside_the_sibling_half_is_not(self):
        """The relation has to be able to say no, or it is not a relation."""
        A.CUT_LINEAGE[(0, 100, 0, 100)] = {
            "cut_id": 1, "sibling": (100, 300, 0, 100), "axis": "col",
            "gap_lo": 95, "gap_hi": 105, "depth": 0}
        self.assertIsNone(A.cut_sibling_of((0, 100, 0, 100), (310, 400, 0, 100)))
        self.assertIsNone(A.cut_sibling_of((0, 100, 0, 100), (120, 380, 0, 100)))
        self.assertIsNone(A.cut_sibling_of((7, 7, 7, 7), (0, 1, 0, 1)))
        RUN[0] += 1

    def test_the_shadow_gate_records_a_verdict_and_adopts_nothing(self):
        """The whole point is to find out what the gate WOULD have said. If it
        adopts, it is not a shadow. Guard: _shadow_gate, and adopt_orphans
        returning its input unchanged for a refused orphan."""
        d = self._two_panels()
        panel = (55, 265, 35, 245)
        piece = (300, 380, 35, 245)
        A.CUT_LINEAGE[tuple(piece)] = {
            "cut_id": 9, "sibling": (0, 290, 0, 300), "axis": "col",
            "gap_lo": 290, "gap_hi": 300, "depth": 0}
        A.SHADOW_GATE = True
        before = [tuple(panel)]
        got = [tuple(b) for b in A.adopt_orphans(d, [panel], [piece])]
        self.assertEqual(got, before, "the shadow gate adopted something")
        rows = [r for r in T.ROWS if r["kind"] == "GATE_SHADOW"]
        self.assertTrue(rows, "no shadow verdict was recorded")
        self.assertEqual(rows[0]["cut_id"], 9)
        self.assertIn("c_rows", rows[0])
        # THE GUARANTEE IS STRUCTURAL, not a promise: the function is never given
        # the output list, so it has nothing to adopt into. Asserted here because
        # the day someone passes it in, this is the line that says no.
        self.assertEqual(list(inspect.signature(A._shadow_gate).parameters),
                         ["dark", "orp", "boxes"])
        RUN[0] += 1

    def test_with_the_flag_off_the_shadow_gate_is_not_asked(self):
        """It costs a `continuity.verdict` per sibling pair, so it is opt-in."""
        d = self._two_panels()
        panel = (55, 265, 35, 245)
        piece = (300, 380, 35, 245)
        A.CUT_LINEAGE[tuple(piece)] = {
            "cut_id": 9, "sibling": (0, 290, 0, 300), "axis": "col",
            "gap_lo": 290, "gap_hi": 300, "depth": 0}
        A.SHADOW_GATE = False
        A.adopt_orphans(d, [panel], [piece])
        self.assertEqual([r for r in T.ROWS if r["kind"] == "GATE_SHADOW"], [])
        RUN[0] += 1


class Flags(unittest.TestCase):
    """The one value a person reaches for to turn an experiment off."""

    def test_zero_turns_the_shadow_flags_off(self):
        """`bool(os.environ.get("SHADOWGATE"))` is True for "0", because "0" is a
        non-empty string - so SHADOWGATE=0 RAN the experiment. Guard: the
        `!= "0"` reads."""
        for value, want in (("", False), ("0", False), ("1", True), ("yes", True)):
            self.assertEqual(value not in ("", "0"), want)
        import importlib, os as _os
        # EVERY shadow flag, not just the one that was caught: the next one added
        # with `bool(os.environ.get(...))` is the same defect a round later.
        for name, attr in (("SHADOWGATE", "SHADOW_GATE"),
                           ("RESIDUAL", "RESIDUAL_SHADOW")):
            for value, want in ((None, False), ("0", False), ("1", True)):
                old = _os.environ.pop(name, None)
                try:
                    if value is not None:
                        _os.environ[name] = value
                    mod = importlib.reload(A)
                    self.assertEqual(getattr(mod, attr), want,
                                     "%s=%r read as %r" % (name, value,
                                                           getattr(mod, attr)))
                finally:
                    _os.environ.pop(name, None)
                    if old is not None:
                        _os.environ[name] = old
        importlib.reload(A)
        RUN[0] += 1

    def test_trace_zero_does_not_write_a_file_called_zero(self):
        """TRACE names a path, so its off value is emptiness - but "0" is what a
        person types, and it must not become a filename."""
        import importlib, os as _os
        old = _os.environ.pop("TRACE", None)
        try:
            _os.environ["TRACE"] = "0"
            mod = importlib.reload(T)
            self.assertFalse(mod.ON)
            self.assertEqual(mod.PATH, "trace.csv")
        finally:
            _os.environ.pop("TRACE", None)
            if old is not None:
                _os.environ["TRACE"] = old
            importlib.reload(T)
        RUN[0] += 1


class PieceRelation(unittest.TestCase):
    """`classify_piece`: five relations, because they are five repairs."""

    def setUp(self):
        A.CUT_LINEAGE.clear()
        A._CUT_SEQ[0] = 0

    def _cut(self, piece, sibling, cut_id=1):
        A.CUT_LINEAGE[tuple(piece)] = {"cut_id": cut_id, "sibling": tuple(sibling),
                                       "axis": "col", "gap_lo": 0, "gap_hi": 10,
                                       "depth": 0}

    def test_one_panel_in_the_opposite_half(self):
        self._cut((0, 100, 0, 100), (110, 300, 0, 100))
        rel, opp, nested = A.classify_piece((0, 100, 0, 100),
                                            [(120, 280, 10, 90), (400, 500, 0, 100)])
        self.assertEqual(rel, A.OPPOSITE_HALF_UNIQUE)
        self.assertEqual(opp, [(120, 280, 10, 90)])
        RUN[0] += 1

    def test_two_panels_in_the_opposite_half_is_not_a_partner(self):
        """Choosing between them by area or discovery order is the tie-break this
        project keeps having to withdraw."""
        self._cut((0, 100, 0, 100), (110, 300, 0, 100))
        rel, opp, _ = A.classify_piece((0, 100, 0, 100),
                                       [(120, 190, 10, 90), (200, 280, 10, 90)])
        self.assertEqual(rel, A.OPPOSITE_HALF_MANY)
        self.assertEqual(len(opp), 2)
        RUN[0] += 1

    def test_a_panel_nested_inside_the_piece_is_a_different_repair(self):
        """Publication 475 figure 1's panel C: its selected box 101,268,499,627 is
        INSIDE the piece 99,384,370,664. Asking only about the opposite half
        cannot see it, and the box that question does find is a fragment. The
        first write-up called that a partner-ranking problem; it is not."""
        self._cut((99, 384, 370, 664), (400, 700, 370, 664))
        rel, opp, nested = A.classify_piece((99, 384, 370, 664),
                                            [(101, 268, 499, 627)])
        self.assertEqual(rel, A.SAME_HALF_NESTED)
        self.assertEqual(opp, [])
        self.assertEqual(nested, [(101, 268, 499, 627)])
        RUN[0] += 1

    def test_only_the_opposite_half_reaches_the_shadow_gate(self):
        """The nested relation is a DIFFERENT repair - the piece contains the
        panel, so a union of the two adds nothing and the residual components
        inside it are what would have to be found. Offering it to the same gate
        would produce a verdict about the wrong question.
        Guard: cut_sibling_of returning only for OPPOSITE_HALF_UNIQUE."""
        self._cut((99, 384, 370, 664), (400, 700, 370, 664))
        nested_panel = (101, 268, 499, 627)
        self.assertIsNone(A.cut_sibling_of((99, 384, 370, 664), nested_panel))
        opposite_panel = (450, 650, 400, 640)
        self.assertIsNotNone(A.cut_sibling_of((99, 384, 370, 664), opposite_panel))
        RUN[0] += 1

    def test_both_relations_at_once_names_neither(self):
        """475 figure 1's piece 99,384,370,664 has a 72x154 fragment in the
        opposite half AND panel C's own box nested inside it. Answering
        "opposite" because that test runs first named the fragment as the partner
        and hid the panel - which is what the first write-up got wrong.
        Guard: the `opposite and nested` branch, and offer_to_shadow_gate."""
        self._cut((99, 384, 370, 664), (400, 700, 370, 664))
        panels = [(428, 500, 510, 664), (101, 268, 499, 627)]
        rel, opp, nested = A.classify_piece((99, 384, 370, 664), panels)
        self.assertEqual(rel, A.OPPOSITE_AND_NESTED)
        self.assertEqual(opp, [(428, 500, 510, 664)])
        self.assertEqual(nested, [(101, 268, 499, 627)])
        self.assertIsNone(A.offer_to_shadow_gate((99, 384, 370, 664), panels),
                          "the gate was asked about the fragment anyway")
        RUN[0] += 1

    def test_the_unambiguous_case_is_still_offered(self):
        """A gate that refuses every pair is not a gate."""
        self._cut((0, 100, 0, 100), (110, 300, 0, 100))
        panels = [(120, 280, 10, 90)]
        self.assertEqual(A.classify_piece((0, 100, 0, 100), panels)[0],
                         A.OPPOSITE_HALF_UNIQUE)
        self.assertEqual(tuple(A.offer_to_shadow_gate((0, 100, 0, 100), panels)),
                         (120, 280, 10, 90))
        RUN[0] += 1

    def test_no_panel_descends_from_the_lineage_at_all(self):
        self._cut((0, 100, 0, 100), (110, 300, 0, 100))
        rel, opp, nested = A.classify_piece((0, 100, 0, 100), [(500, 600, 500, 600)])
        self.assertEqual(rel, A.NO_PANEL_DESCENDANT)
        self.assertEqual((opp, nested), ([], []))
        RUN[0] += 1

    def test_a_piece_with_no_lineage_is_not_guessed_at(self):
        rel, _, _ = A.classify_piece((7, 8, 9, 10), [(0, 100, 0, 100)])
        self.assertEqual(rel, A.NO_PANEL_DESCENDANT)
        self.assertEqual(A.lineage_of((7, 8, 9, 10))[0], "NONE")
        RUN[0] += 1

    def test_two_halves_of_equal_size_are_ambiguous_not_arbitrary(self):
        """The tolerance that makes the containment lookup work is the tolerance
        that makes this possible, so it is not hypothetical - and today the answer
        would depend on dict insertion order."""
        self._cut((0, 100, 0, 100), (110, 300, 0, 100), cut_id=1)
        self._cut((1, 101, 0, 100), (400, 600, 0, 100), cut_id=2)
        self.assertEqual(A.lineage_of((10, 90, 10, 90))[0], "AMBIGUOUS")
        rel, _, _ = A.classify_piece((10, 90, 10, 90), [(120, 280, 10, 90)])
        self.assertEqual(rel, A.LINEAGE_AMBIGUOUS)
        self.assertIsNone(A.cut_sibling_of((10, 90, 10, 90), (120, 280, 10, 90)))
        RUN[0] += 1

    def test_an_exact_half_is_not_ambiguous(self):
        """The piece that IS a recorded half needs no search at all."""
        self._cut((0, 100, 0, 100), (110, 300, 0, 100), cut_id=1)
        self._cut((1, 101, 0, 100), (400, 600, 0, 100), cut_id=2)
        self.assertEqual(A.lineage_of((0, 100, 0, 100))[0], "EXACT")
        RUN[0] += 1


class RegionProvenance(unittest.TestCase):
    """`REGIONS`: which transform made which box from which.

    A box is a VALUE. Several regions can share one - a trim that changes
    nothing, a merge whose result equals an input, two modes producing the same
    rectangle - so provenance cannot be recovered from coordinates afterwards.
    """

    def setUp(self):
        T.reset()
        T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON
        T.ON = True
        A.REGIONS.clear()
        A._REGION_AT.clear()
        A._REGION_SEQ[0] = 0

    def tearDown(self):
        T.ON, = (self._on,)

    def test_a_region_records_its_transform_and_its_parents(self):
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        b = A.region((0, 90, 0, 90), A.TRIM, parents=(a,))
        self.assertEqual(A.REGIONS[b]["transform"], A.TRIM)
        self.assertEqual(A.REGIONS[b]["parents"], [a])
        self.assertTrue(A.descends_from(b, a))
        self.assertFalse(A.descends_from(a, b))
        RUN[0] += 1

    def test_the_same_box_twice_is_two_regions(self):
        """"trim left this alone" and "nothing trimmed this" are different
        histories, and only the first means the box was seen. Guard: region()
        registering unconditionally."""
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        b = A.region((0, 100, 0, 100), A.TRIM, parents=(a,))
        self.assertNotEqual(a, b)
        self.assertTrue(A.REGIONS[b]["same_box"])
        self.assertEqual(A.region_at((0, 100, 0, 100)), b, "the newest wins")
        RUN[0] += 1

    def test_a_merge_carries_every_input(self):
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        b = A.region((100, 200, 0, 100), A.CUT_HALF)
        m = A.region((0, 200, 0, 100), A.MERGE, parents=(a, b))
        self.assertEqual(sorted(A.REGIONS[m]["parents"]), sorted([a, b]))
        self.assertTrue(A.descends_from(m, a) and A.descends_from(m, b))
        RUN[0] += 1

    def test_the_fate_of_a_line_names_the_transforms_it_went_through(self):
        """"No final panel descends from this piece" is a fact about the DAG;
        WHICH transform lost it is a fact about this list. The last round guessed
        at it and had to withdraw the guess. Guard: fate_of / descendants."""
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        b = A.region((0, 90, 0, 90), A.TRIM, parents=(a,))
        A.region((0, 90, 0, 90), A.DROPPED, parents=(b,), note="removed")
        self.assertEqual(A.fate_of(a), [A.CUT_HALF, A.TRIM, A.DROPPED])
        RUN[0] += 1

    def test_a_line_that_never_ended_has_no_DROPPED_in_its_fate(self):
        """A fate that says DROPPED for everything says nothing."""
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        A.region((0, 100, 0, 100), A.SNAP, parents=(a,))
        self.assertNotIn(A.DROPPED, A.fate_of(a))
        RUN[0] += 1

    def test_with_the_trace_off_no_region_is_written(self):
        """It answers questions about a run, and a run nobody is observing has
        none. Guard: the `if not _T.ON` return in region()."""
        T.ON = False
        self.assertIsNone(A.region((0, 10, 0, 10), A.CUT_HALF))
        self.assertEqual(A.REGIONS, {})
        RUN[0] += 1

    def test_a_cycle_cannot_hang_the_walk(self):
        """Nothing should build one, and a provenance walk that can hang is a
        provenance walk nobody will run on a corpus."""
        a = A.region((0, 10, 0, 10), A.CUT_HALF)
        b = A.region((0, 20, 0, 20), A.MERGE, parents=(a,))
        A.REGIONS[a]["parents"] = [b]
        self.assertEqual(A.ancestors(b), {a, b})
        self.assertEqual(len(A.descendants(a)), 2)
        RUN[0] += 1


class PostAdoptionShadow(unittest.TestCase):
    """A gate accept is a necessary condition, not a repair."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._sg = T.ON, A.SHADOW_GATE
        T.ON = True
        A.CUT_LINEAGE.clear(); A._CUT_SEQ[0] = 0
        A.REGIONS.clear(); A._REGION_AT.clear(); A._REGION_SEQ[0] = 0
        A._RUN_CACHE.clear(); A._ANCHOR_CACHE.clear()

    def tearDown(self):
        T.ON, A.SHADOW_GATE = self._on, self._sg

    def _figure(self):
        """Four bar groups 60 px apart, and a panel box that stops after the
        third. The fourth is 35 px past the box edge - outside the 34 px reach,
        and REGULAR when merged, so the arbiter does not veto. A fixture whose
        merge makes the spacing worse tests the veto, not the post-checks."""
        d = np.zeros((300, 620), dtype=bool)
        d[40:240, 60] = True
        d[239, 60:300] = True
        for bx in (90, 150, 210, 270):
            d[140:239, bx:bx + 20] = True
        return d

    def test_it_measures_the_union_and_adopts_nothing(self):
        """Guard: _shadow_post_adoption, and its signature having no output
        list."""
        d = self._figure()
        panel = (55, 232, 35, 245)
        piece = (267, 292, 138, 242)
        A.CUT_LINEAGE[tuple(piece)] = {
            "cut_id": 3, "sibling": (0, 262, 0, 300), "axis": "col",
            "gap_lo": 232, "gap_hi": 267, "depth": 0, "region": None}
        A.SHADOW_GATE = True
        got = [tuple(b) for b in A.adopt_orphans(d, [panel], [piece])]
        self.assertEqual(got, [tuple(panel)])
        rows = [r for r in T.ROWS if r["kind"] == "POST_ADOPTION_SHADOW"]
        self.assertTrue(rows, "the gate accepted and nothing measured the union")
        r = rows[0]
        self.assertGreater(int(r["width_after"]), int(r["width_before"]))
        self.assertIn("would_production_refuse", r)
        self.assertEqual(list(inspect.signature(A._shadow_post_adoption).parameters),
                         ["dark", "orp", "panel", "boxes", "sx"])
        RUN[0] += 1

    def test_a_union_that_would_swallow_a_panel_says_so(self):
        """Production refuses a box that contains another panel, so a shadow that
        does not report it is claiming a repair production would reject."""
        d = self._figure()
        d[40:240, 400] = True                # a second panel's spine, in the way
        panel = (55, 232, 35, 245)
        piece = (267, 292, 138, 242)
        other = (390, 500, 35, 245)
        A.CUT_LINEAGE[tuple(piece)] = {
            "cut_id": 3, "sibling": (0, 262, 0, 300), "axis": "col",
            "gap_lo": 232, "gap_hi": 267, "depth": 0, "region": None}
        A.SHADOW_GATE = True
        A.adopt_orphans(d, [panel, other], [piece])
        rows = [r for r in T.ROWS if r["kind"] == "POST_ADOPTION_SHADOW"]
        if not rows:
            self.skipTest("the gate refused this fixture, so there is nothing to post-check")
        RUN[0] += 1


class AncestorRegionCompletion(unittest.TestCase):
    """The piece CONTAINS the panel, so an adoption has nothing to add.

    Publication 475's figure 1 selects 101,268,499,627 inside the piece
    99,384,370,664. The union of the two IS the piece. What is missing is the ink
    inside the piece that the panel's plot core does not cover, and every
    scenario here is about one of the five statements that ink has to answer.
    """

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on, self._rs, self._sg = T.ON, A.RESIDUAL_SHADOW, A.SHADOW_GATE
        self._floor = A.CAP_FLOOR
        T.ON = True
        A.RESIDUAL_SHADOW, A.SHADOW_GATE = True, False
        A.CUT_LINEAGE.clear(); A._CUT_SEQ[0] = 0
        A.REGIONS.clear(); A._REGION_AT.clear(); A._REGION_SEQ[0] = 0
        A._RUN_CACHE.clear(); A._ANCHOR_CACHE.clear()

    def tearDown(self):
        T.ON, A.RESIDUAL_SHADOW, A.SHADOW_GATE = self._on, self._rs, self._sg
        A.CAP_FLOOR = self._floor

    PANEL = (100, 250, 100, 300)
    PIECE = (95, 400, 90, 330)

    def _figure(self):
        """A panel with its spine, baseline, two bars and a column of numerals,
        and one 60x90 block of data 20 px past the panel's right edge - inside
        the piece, outside the panel."""
        d = np.zeros((400, 500), dtype=bool)
        d[110:291, 110] = True              # the spine
        d[288:291, 110:246] = True          # the baseline
        d[200:290, 130:150] = True          # a bar
        d[180:290, 170:190] = True          # a bar
        d[200:211, 90:106] = True           # numerals, on the label side
        d[210:290, 270:330] = True          # the residual block
        return d

    def _run(self, d, boxes=None, piece=None):
        piece = piece or self.PIECE
        A.CUT_LINEAGE[tuple(piece)] = {
            "cut_id": 1, "sibling": (400, 500, 90, 330), "axis": "col",
            "gap_lo": 395, "gap_hi": 400, "depth": 0, "region": None}
        out = A.adopt_orphans(d, list(boxes or [self.PANEL]), [piece])
        return [tuple(b) for b in out]

    def _components(self, panel=None):
        """Only the rows about ONE panel. A figure with two nested panels writes
        a component row per panel per blob, and a dict keyed on the blob alone
        silently reports the last panel's verdict for the first panel's."""
        want = T.box(panel or self.PANEL)
        return {r["component"]: r for r in T.ROWS
                if r["kind"] == "RESIDUAL_COMPONENT" and r["panel"] == want}

    def _summary(self, panel=None):
        want = T.box(panel or self.PANEL)
        rows = [r for r in T.ROWS
                if r["kind"] == "RESIDUAL_SHADOW" and r["panel"] == want]
        self.assertTrue(rows, "the nested piece was never measured")
        return rows[-1]

    def test_it_measures_the_residual_and_adopts_nothing(self):
        """Guard: _shadow_residual, and its signature having no output list."""
        got = self._run(self._figure())
        self.assertEqual(got, [self.PANEL], "a shadow changed the output")
        s = self._summary()
        self.assertEqual(s["plot_box"], "110,250,100,300")
        self.assertEqual(int(s["n_data"]), 1)
        self.assertIn("270,330,210,290", self._components())
        self.assertEqual(list(inspect.signature(A._shadow_residual).parameters),
                         ["dark", "orp", "panel", "boxes"])
        RUN[0] += 1

    def test_with_the_flag_off_nothing_is_measured(self):
        """A shadow that runs unasked is a cost the pipeline did not consent to.

        WITH THE OTHER SHADOW ON, which is the only arrangement that tests this
        guard. Turning both off skips the whole block on its outer condition and
        leaves the inner `RESIDUAL_SHADOW and` untested - decoration that the
        mutation matrix caught on its first pass.
        Guard: the `RESIDUAL_SHADOW and` in the inner condition."""
        A.RESIDUAL_SHADOW, A.SHADOW_GATE = False, True
        self._run(self._figure())
        self.assertEqual([r for r in T.ROWS if r["kind"].startswith("RESIDUAL")], [])
        self.assertTrue([r for r in T.ROWS if r["kind"] == "PIECE_RELATION"],
                        "the fixture never reached the shadows at all")
        RUN[0] += 1

    def test_the_relation_row_is_written_for_this_flag_too(self):
        """A residual measurement whose relation is not in the trace cannot be
        told from a gate refusal afterwards. SHADOW_GATE is off in this class, so
        the row can only come from the other half of the condition.
        Guard: `if SHADOW_GATE or RESIDUAL_SHADOW`."""
        self._run(self._figure())
        rows = [r for r in T.ROWS if r["kind"] == "PIECE_RELATION"]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["relation"], A.SAME_HALF_NESTED)
        RUN[0] += 1

    def test_the_plot_core_is_subtracted_and_not_the_box(self):
        """The panel's box carries its numerals; its plot core does not. Blanking
        the box would hide the strip and call the hiding a measurement.
        Guard: _residual_components blanking plot_box."""
        self._run(self._figure())
        comps = self._components()
        self.assertIn("95,106,200,211", comps, "the label strip was blanked too")
        self.assertNotIn("130,150,200,290", comps, "a bar inside the plot survived")
        RUN[0] += 1

    def test_a_blob_on_the_label_side_is_not_data(self):
        """The numerals are ink the panel already owns.
        Guard: the plot_side clause."""
        self._run(self._figure())
        r = self._components()["95,106,200,211"]
        self.assertEqual(r["c_plot_side"], "X")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_a_blob_carrying_its_own_rule_is_not_data(self):
        """A residual block with a spine of its own is another panel, and the
        repair for that is not completion. `_has_y_axis` cannot say so - it asks
        for a run covering 45% of the blob's OWN height, which every single bar
        is - so the test is `_rules`: 1 to 4 columns wide, RULE_MIN_LEN long.
        Guard: the no_own_axis clause."""
        d = self._figure()
        d[180:300, 280] = True             # 120 px of thin vertical rule
        self._run(d)
        r = self._components()["270,330,180,300"]
        self.assertEqual(r["c_no_own_axis"], "X")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_a_blob_beside_nothing_is_not_data(self):
        """The panel title sits above the axis run and shares no rows with it.
        Guard: the shares_axis_rows clause."""
        d = self._figure()
        d[210:290, 270:330] = False
        d[92:106, 270:330] = True          # a strip above the axis run
        self._run(d)
        r = self._components()["270,330,92,106"]
        self.assertEqual(r["c_shares_axis_rows"], "X")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_a_blob_holding_another_panels_spine_is_not_data(self):
        """Completing this panel with the next panel's axis in the block is how a
        repair swallows a panel. Guard: the no_foreign_spine clause."""
        d = self._figure()
        d[210:290, 270:330] = False
        # One block STRADDLING the neighbour's spine without touching it: two
        # bars bridged above the spine's top. Touching would merge the spine into
        # the component and the rule clause would refuse it first, which is a
        # scenario about the other clause.
        d[210:290, 270:291] = True
        d[210:290, 310:331] = True
        d[210:216, 270:331] = True
        d[230:301, 300] = True             # the neighbour's spine
        d[297:301, 300:390] = True
        other = (295, 390, 220, 310)
        self._run(d, boxes=[self.PANEL, other])
        r = self._components()["270,331,210,290"]
        self.assertEqual(r["c_no_foreign_spine"], "X")
        self.assertEqual((r["c_plot_side"], r["c_no_own_axis"],
                          r["c_shares_axis_rows"], r["c_above_caption"]),
                         ("O", "O", "O", "O"), "another clause did the refusing")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_the_neighbouring_panel_is_not_this_panels_missing_data(self):
        """Its spine sits on its own left edge, so a strict `cx0 < fx` let the
        whole neighbouring panel come back as a component to complete this one
        with. Guard: the inclusive left bound."""
        d = self._figure()
        d[210:290, 270:330] = False
        d[230:301, 300] = True
        d[297:301, 300:390] = True
        other = (295, 390, 220, 310)
        self._run(d, boxes=[self.PANEL, other])
        r = self._components()["300,390,230,301"]
        self.assertEqual(r["c_no_foreign_spine"], "X")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_a_blob_in_the_caption_is_not_data(self):
        """No panel contains the caption; a completion that reaches into it is
        reading the caption as marks. Guard: the above_caption clause."""
        d = self._figure()
        d[210:290, 270:330] = False
        # BESIDE THE AXIS RUN AND BELOW THE FLOOR AT ONCE. A blob under the whole
        # plot fails the row clause first, so the caption clause is never the
        # thing refusing it - which is what the mutation matrix said about the
        # first version of this fixture.
        d[255:285, 270:330] = True
        A.CAP_FLOOR = 250
        self._run(d)
        r = self._components()["270,330,255,285"]
        self.assertEqual(r["c_above_caption"], "X")
        self.assertEqual((r["c_plot_side"], r["c_no_own_axis"],
                          r["c_shares_axis_rows"], r["c_no_foreign_spine"]),
                         ("O", "O", "O", "O"), "another clause did the refusing")
        self.assertEqual(r["is_data"], False)
        RUN[0] += 1

    def test_a_speck_is_counted_and_not_recorded(self):
        """Scanner dirt would otherwise be one trace row per speck, and a trace
        nobody can read answers nothing. Guard: the ADOPT_MIN filter."""
        d = self._figure()
        for x in range(340, 380, 6):
            d[210:213, x:x + 3] = True     # 3x3 specks
        self._run(d)
        s = self._summary()
        self.assertGreaterEqual(int(s["n_too_small"]), 6)
        self.assertNotIn("340,343,210,213", self._components())
        RUN[0] += 1

    def test_the_opposite_half_alone_never_reaches_it(self):
        """A piece whose panel is in the OTHER half is the adoption question and
        already has a shadow. Running both on it would produce two verdicts about
        two different repairs and no way to tell which one a row is about.
        Guard: the `rel in (SAME_HALF_NESTED, OPPOSITE_AND_NESTED)` filter."""
        d = self._figure()
        far = (0, 60, 90, 330)             # 40 px from the panel: past the reach
        A.CUT_LINEAGE[far] = {
            "cut_id": 2, "sibling": (60, 500, 90, 330), "axis": "col",
            "gap_lo": 60, "gap_hi": 100, "depth": 0, "region": None}
        A.adopt_orphans(d, [self.PANEL], [far])
        self.assertEqual([r for r in T.ROWS if r["kind"] == "RESIDUAL_SHADOW"], [])
        self.assertEqual([r for r in T.ROWS if r["kind"] == "PIECE_RELATION"][-1]
                         ["relation"], A.OPPOSITE_HALF_UNIQUE)
        RUN[0] += 1

    def test_the_axis_it_measured_against_is_recorded_not_asserted(self):
        """"Against that panel's attested axis" is the requirement, and
        attestation needs a ladder, which needs OCR this must not pay for inside
        adopt_orphans. So the three inputs axis_status takes are recorded and the
        verdict is left to the reader; a row that hid them would be a measurement
        against an unnamed column. Guard: the axis provenance fields."""
        self._run(self._figure())
        s = self._summary()
        self.assertEqual(s["axis_anchored"], True)
        self.assertNotEqual(s["axis_n_free"], "")
        self.assertNotEqual(s["axis_n_clipped"], "")
        self.assertEqual(
            T.axis_status(int(s["axis_n_free"]), int(s["axis_n_clipped"]),
                          s["axis_anchored"], False),
            T.AXIS_GEOMETRY_ONLY)
        RUN[0] += 1

    def test_a_long_diagonal_is_one_component_and_does_not_recurse(self):
        """A scatter plot's fitted line is one mark. A recursive flood fill meets
        Python's recursion limit on it, on a figure nobody would call unusual.
        Guard: the explicit stack in _components."""
        d = np.zeros((400, 400), dtype=bool)
        for i in range(350):
            d[20 + i, 20 + i] = True
        comps = A._components(d)
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0][:4], (20, 370, 20, 370))
        self.assertEqual(comps[0][4], 350)
        RUN[0] += 1

    def test_two_blobs_a_gap_apart_are_two_components(self):
        """A completion that merges every blob into one has measured nothing.
        Guard: the neighbour walk in _components."""
        d = np.zeros((100, 100), dtype=bool)
        d[10:30, 10:30] = True
        d[10:30, 40:60] = True
        comps = sorted(A._components(d))
        self.assertEqual([c[:4] for c in comps],
                         [(10, 30, 10, 30), (40, 60, 10, 30)])
        RUN[0] += 1


class WhichPassAJoinBelongsTo(unittest.TestCase):
    """The SELECTED row names the winning pass. So must everything joined to it."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON; T.ON = True

    def tearDown(self):
        T.ON = self._on

    def test_last_takes_the_last_pass_and_last_in_pass_takes_this_one(self):
        """475 figure 1 wins on OFF and ends on GRID. `last` matches on the
        fields it is given and nothing else, so the axis candidates behind an
        OFF row could be GRID's - the mislabelled-SELECTED defect, one join
        further down. Guard: the CTX merge in last_in_pass."""
        T.context(pid="475", fig="Fig. 1", png="a.png", mode="OFF", ink=140)
        T.add("AXIS_CANDIDATES", box="1,2,3,4", n_free=3)
        T.context(mode="GRID", ink=151)
        T.add("AXIS_CANDIDATES", box="1,2,3,4", n_free=0)
        T.context(mode="OFF", ink=140)
        self.assertEqual(T.last("AXIS_CANDIDATES", box="1,2,3,4")["n_free"], 0)
        self.assertEqual(T.last_in_pass("AXIS_CANDIDATES", box="1,2,3,4")["n_free"], 3)
        RUN[0] += 1

    def test_two_figures_in_one_run_are_two_passes(self):
        """They share mode and ink, and they can share a box value. A join on the
        pass alone would hand one figure the other's axis.
        Guard: every set context field being part of the match."""
        T.context(pid="475", fig="Fig. 1", png="a.png", mode="OFF", ink=140)
        T.add("AXIS_CANDIDATES", box="1,2,3,4", n_free=7)
        T.context(pid="397", fig="Fig. 1", png="b.png")
        T.add("AXIS_CANDIDATES", box="1,2,3,4", n_free=1)
        T.context(pid="475", fig="Fig. 1", png="a.png")
        self.assertEqual(T.last_in_pass("AXIS_CANDIDATES", box="1,2,3,4")["n_free"], 7)
        RUN[0] += 1

    def test_a_pass_that_wrote_nothing_joins_to_nothing(self):
        """A join that falls back to another pass when its own is empty is worse
        than an empty cell: it reports a number for a measurement never made."""
        T.context(pid="475", fig="Fig. 1", png="a.png", mode="GRID", ink=151)
        T.add("AXIS_CANDIDATES", box="1,2,3,4", n_free=0)
        T.context(mode="OFF", ink=140)
        self.assertIsNone(T.last_in_pass("AXIS_CANDIDATES", box="1,2,3,4"))
        RUN[0] += 1


class BoxProvenance(unittest.TestCase):
    """Whether a panel's box was cut out of the figure or invented."""

    def setUp(self):
        T.reset(); T.context(pid="", fig="", png="", mode="", ink="")
        self._on = T.ON; T.ON = True
        A.REGIONS.clear(); A._REGION_AT.clear(); A._REGION_SEQ[0] = 0

    def tearDown(self):
        T.ON = self._on

    def test_a_cut_line_is_rooted_at_the_cut(self):
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        b = A.region((0, 90, 0, 90), A.TRIM, parents=(a,))
        c = A.region((0, 90, 0, 90), A.CAPTION_TRIM, parents=(b,))
        self.assertEqual(A.roots_of(c), [A.CUT_HALF])
        self.assertFalse(A.constructed(c))
        RUN[0] += 1

    def test_a_box_no_ink_was_asked_about_says_so(self):
        """Publication 475's figure 1's panel C: `column_siblings` produced it
        from 0 overlapping parents, so it was drawn from the other panels'
        geometry rather than found. Guard: roots_of."""
        c = A.region((200, 300, 0, 100), A.COLUMN_SIBLING, note="from 0 overlapping")
        d = A.region((200, 300, 0, 100), A.ADOPT, parents=(c,))
        self.assertEqual(A.roots_of(d), [A.COLUMN_SIBLING])
        self.assertTrue(A.constructed(d))
        RUN[0] += 1

    def test_a_transform_nobody_listed_still_counts_as_constructed(self):
        """Written as "not every root is CUT_HALF" and not as a list of the
        transforms that count, because the transform added next round is the one
        that would be missing from the list and its boxes would report as cut out
        of the figure. Guard: the `!= CUT_HALF` test."""
        t = A.region((0, 10, 0, 10), A.TRIM, note="orphaned line")
        self.assertTrue(A.constructed(t))
        RUN[0] += 1

    def test_a_box_with_two_lines_reports_both_roots(self):
        """A merge of a cut piece and a constructed one is neither, and naming it
        by whichever root was found first is the tie-break this project keeps
        having to withdraw."""
        a = A.region((0, 100, 0, 100), A.CUT_HALF)
        c = A.region((90, 200, 0, 100), A.COLUMN_SIBLING)
        m = A.region((0, 200, 0, 100), A.MERGE, parents=(a, c))
        self.assertEqual(A.roots_of(m), [A.COLUMN_SIBLING, A.CUT_HALF])
        self.assertTrue(A.constructed(m))
        RUN[0] += 1

    def test_a_box_the_dag_never_saw_is_empty_and_not_an_error(self):
        """A reporting column may not end a run, and every panel measured before
        the DAG existed - every panel, when the trace is off - is a box the DAG
        never saw. Guard: the `rid not in REGIONS` return in ancestors(); a
        second check inside provenance_of was tried and removed, because
        reverting it turned nothing red."""
        self.assertEqual(A.provenance_of((1, 2, 3, 4)), (None, [], []))
        A.region((0, 100, 0, 100), A.CUT_HALF)
        A.REGIONS[999] = {"box": (0, 1, 0, 1), "transform": A.TRIM,
                          "parents": [4242], "note": "", "same_box": False}
        self.assertEqual(A.roots_of(999), [])
        RUN[0] += 1

    def test_the_snapshot_survives_the_next_pass(self):
        """`panels()` clears the DAG per call and the winning pass is almost
        never the last one iterated, so reading REGIONS after the mode loop reads
        the LOSER'S provenance under the winner's name.
        Guard: snapshot_regions / restore_regions."""
        won = A.region((0, 100, 0, 100), A.CUT_HALF)
        snap = A.snapshot_regions()
        A.REGIONS.clear(); A._REGION_AT.clear(); A._REGION_SEQ[0] = 0
        A.region((0, 100, 0, 100), A.COLUMN_SIBLING)
        self.assertTrue(A.constructed(A.region_at((0, 100, 0, 100))))
        A.restore_regions(snap)
        self.assertEqual(A.region_at((0, 100, 0, 100)), won)
        self.assertFalse(A.constructed(won))
        RUN[0] += 1

    def test_the_snapshot_is_a_copy_and_not_a_view(self):
        """A snapshot that aliases the live dict is not a snapshot, and the
        aliasing only shows up on the pass that adds a region."""
        A.region((0, 100, 0, 100), A.CUT_HALF)
        snap = A.snapshot_regions()
        A.region((0, 50, 0, 50), A.COLUMN_SIBLING)
        self.assertEqual(len(snap[0]), 1)
        A.restore_regions(snap)
        self.assertEqual(len(A.REGIONS), 1)
        RUN[0] += 1


if __name__ == "__main__":
    loaded = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(loaded)
    print("FDT_SCENARIOS_RUN=%d" % result.testsRun)
    sys.exit(0 if result.wasSuccessful() else 1)
