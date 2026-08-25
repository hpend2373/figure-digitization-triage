#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scenarios for the owned label strip and the three boxes.

Drawn fixtures only: no corpus, no OCR, no network.  Every geometric scenario
runs at two scales and must give the SAME verdict at both, because nothing about
ownership is allowed to be a distance in pixels.  The one place a pixel constant
survives is named where it is used: the band walk itself inherits `LABEL_GAP`
and `LABEL_BAND_MAX` from `label_band`, which this module deliberately calls
rather than reimplements.

Each scenario names the clause of the ownership contract it holds.
"""
import sys
import unittest

import ast
import gc
import os

import numpy as np

import axis_reader as A
import panel_geometry as G


def _propose_columns():
    """`propose.py`'s `cols`, read without importing it.

    Read by AST for the same reason `verify_documented_status` reads
    PIPELINE_VERSION that way: importing the driver runs it, and it wants a
    corpus.  A list in a comment must not be able to satisfy a check about what
    the code writes.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "propose.py")
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "cols":
                    return [e.value for e in node.value.elts]
    raise AssertionError("propose.py has no module-level `cols` list")

SCALES = (1, 3)
RUN = 0


def canvas(w, h):
    return np.zeros((h, w), dtype=bool)


def rect(d, x0, x1, y0, y1):
    d[int(y0):int(y1) + 1, int(x0):int(x1) + 1] = True


def left_axis_figure(s, sparse_plot=False, title=True):
    """A left-hand y axis: rotated title, gutter, numerals, spine, baseline, bars.

        x=10s..12s   rotated axis title      (must NOT be owned)
        x=30s..40s   three numerals          (must be owned)
        x=50s        spine
        y=140s       baseline, running right
    """
    d = canvas(300 * s, 200 * s)
    if title:
        rect(d, 10 * s, 12 * s, 40 * s, 140 * s)
    if sparse_plot:
        # Ink-adversarial on purpose: a wide, tall column of numerals beside a
        # nearly empty plot. Total ink says LEFT is the busy side; the baseline
        # still says LEFT is the LABEL side, and that is the discriminator.
        for row in (45, 60, 75, 90, 110, 130):
            rect(d, 28 * s, 44 * s, row * s, row * s + 6 * s)
    else:
        for row in (45, 90, 135):
            rect(d, 30 * s, 40 * s, row * s, row * s + 6 * s)
    rect(d, 50 * s, 50 * s, 40 * s, 140 * s)          # spine
    rect(d, 50 * s, 250 * s, 140 * s, 140 * s)        # baseline, right of the spine
    if sparse_plot:
        rect(d, 120 * s, 122 * s, 60 * s, 140 * s)    # one thin bar
    else:
        for bx in (70, 110, 150, 190):
            rect(d, bx * s, bx * s + 20 * s, 60 * s, 140 * s)
    return d


def wide_axis_figure(s):
    """The same panel, printed wide: the axis title lies 240s px from the spine.

    A reach fixed at 180 px cannot see it at ANY scale here, and a reach taken
    from the panel's own width sees it at every scale.  That is the difference
    between a rule about figures and a rule about pixels.
    """
    d = canvas(500 * s, 200 * s)
    rect(d, 10 * s, 12 * s, 40 * s, 140 * s)          # rotated title, far out
    for row in (45, 90, 135):
        rect(d, 230 * s, 240 * s, row * s, row * s + 6 * s)
    rect(d, 250 * s, 250 * s, 40 * s, 140 * s)        # spine
    rect(d, 250 * s, 450 * s, 140 * s, 140 * s)       # baseline
    for bx in (270, 310, 350, 390):
        rect(d, bx * s, bx * s + 20 * s, 60 * s, 140 * s)
    return d


def right_axis_figure(s):
    """The mirror: spine on the right, data to its left, numerals further right."""
    d = canvas(300 * s, 200 * s)
    rect(d, 250 * s, 250 * s, 40 * s, 140 * s)        # spine
    rect(d, 50 * s, 250 * s, 140 * s, 140 * s)        # baseline, LEFT of the spine
    for row in (45, 90, 135):
        rect(d, 260 * s, 270 * s, row * s, row * s + 6 * s)
    rect(d, 288 * s, 290 * s, 40 * s, 140 * s)        # axis title further right
    for bx in (70, 110, 150, 190):
        rect(d, bx * s, bx * s + 20 * s, 60 * s, 140 * s)
    return d


class Ownership(unittest.TestCase):

    def check(self, fn):
        """Run one scenario at every scale; the verdict must not depend on it."""
        global RUN
        for s in SCALES:
            with self.subTest(scale=s):
                fn(s)
            RUN += 1

    # --- clause: the strip is on the label side of the axis -----------------

    def test_the_baseline_says_which_side_the_labels_are_on(self):
        def go(s):
            d = left_axis_figure(s)
            self.assertEqual(G.label_side(d, (25 * s, 250 * s, 35 * s, 150 * s),
                                          50 * s, 140 * s), G.LEFT)
            d2 = right_axis_figure(s)
            self.assertEqual(G.label_side(d2, (40 * s, 275 * s, 35 * s, 150 * s),
                                          250 * s, 140 * s), G.RIGHT)
        self.check(go)

    def test_a_sparse_plot_does_not_lose_its_side_to_its_own_numerals(self):
        """Ink is the wrong discriminator: one thin bar carries less ink than the
        column of numerals labelling it.  The baseline still runs to the right."""
        def go(s):
            d = left_axis_figure(s, sparse_plot=True)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            left_ink = int(d[:, 25 * s:50 * s].sum())
            right_ink = int(d[:, 51 * s:250 * s].sum())
            self.assertGreater(left_ink, right_ink, "fixture must be ink-adversarial")
            self.assertEqual(G.label_side(d, box, 50 * s, 140 * s), G.LEFT)
        self.check(go)

    # --- clause: it stops at the first blank gutter --------------------------

    def test_the_panel_owns_its_axis_title_as_well_as_its_numerals(self):
        """Neither is data and both are the panel's own, so ownership takes both.
        The first version of this file asked `label_band` - which stops at the
        first gutter because it is feeding OCR - and got an empty strip on every
        real panel it was pointed at."""
        def go(s):
            d = left_axis_figure(s)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            strip = G.label_strip(d, box, 50 * s, 140 * s)
            self.assertIsNotNone(strip)
            lo, hi, _t, _b = strip
            self.assertEqual(hi, 50 * s, "ownership runs up to the axis")
            self.assertLessEqual(lo, 10 * s, "the rotated title is owned too")
        self.check(go)

    def test_the_numeral_band_inside_it_is_the_digits_alone(self):
        """OCR is a different question and keeps the tighter answer."""
        def go(s):
            d = left_axis_figure(s)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            band = G.numeral_band(d, box, 50 * s, 140 * s)
            self.assertIsNotNone(band)
            self.assertEqual(band, (30 * s - 1, 40 * s + 2))
            self.assertGreater(band[0], 12 * s, "the rotated title stays outside")
        self.check(go)

    def test_a_numeral_band_that_cannot_be_isolated_does_not_cost_the_panel_its_strip(self):
        """Publication 475's figure 2: tick marks sit two pixels left of the
        spine, seven blank columns end the band walk there, and the measured
        band is one pixel wide and refused.  Ownership must survive that."""
        def go(s):
            d = left_axis_figure(s)
            d[:, 37 * s:50 * s] = False            # pull the numerals back...
            for row in (45, 90, 135):
                rect(d, 30 * s, 36 * s, row * s, row * s + 6 * s)
                rect(d, 50 * s - 3, 50 * s - 2, row * s, row * s + 2 * s)  # ...ticks here
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            self.assertIsNone(G.numeral_band(d, box, 50 * s, 140 * s),
                              "the band walk must stop on the tick marks")
            self.assertIsNotNone(G.label_strip(d, box, 50 * s, 140 * s))
        self.check(go)

    def test_the_mirror_owns_the_side_its_axis_faces(self):
        def go(s):
            d = right_axis_figure(s)
            box = (40 * s, 275 * s, 35 * s, 150 * s)
            strip = G.label_strip(d, box, 250 * s, 140 * s)
            self.assertIsNotNone(strip)
            lo, hi, _t, _b = strip
            self.assertEqual(lo, 250 * s)
            self.assertGreaterEqual(hi, 270 * s)
            band = G.numeral_band(d, box, 250 * s, 140 * s)
            self.assertEqual(band, (260 * s - 2, 270 * s + 1))
        self.check(go)

    # --- clause: it does not reach past a neighbouring spine -----------------

    def test_a_neighbouring_panel_ends_the_strip_at_its_far_edge(self):
        """Two panels in a row cannot both own one column, and what separates
        them is the neighbour's EDGE.  Bounding at its spine instead would hand
        the neighbour's whole plot to this panel."""
        def go(s):
            d = left_axis_figure(s)
            box = (5 * s, 250 * s, 35 * s, 150 * s)
            nb = (2 * s, 35 * s, 35 * s, 150 * s)     # a panel to the left
            free = G.label_strip(d, box, 50 * s, 140 * s)
            owned = G.label_strip(d, box, 50 * s, 140 * s, neighbours=(nb,))
            self.assertIsNotNone(owned)
            self.assertLess(free[0], owned[0])
            self.assertGreaterEqual(owned[0], 35 * s + G.NEIGHBOUR_MARGIN)
        self.check(go)

    def test_reach_is_the_panel_s_own_width_and_not_a_number_of_pixels(self):
        """A wide panel's title sits further from its axis than any fixed reach
        allows.  Nothing about ownership may be a distance in pixels."""
        def go(s):
            d = wide_axis_figure(s)
            box = (5 * s, 400 * s, 35 * s, 150 * s)
            strip = G.label_strip(d, box, 250 * s, 140 * s)
            self.assertIsNotNone(strip)
            self.assertLessEqual(strip[0], 10 * s,
                                 "the title is 240 scale-units out and is owned")
            near = G.label_strip(d, box, 250 * s, 140 * s, max_reach=30 * s)
            self.assertGreater(near[0], 10 * s, "an explicit reach still bounds it")
        self.check(go)

    def test_a_panel_in_the_row_above_takes_no_columns_away(self):
        """Only a panel BESIDE this one can own part of its label side; one
        stacked above it shares no rows with the strip and bounds nothing."""
        def go(s):
            d = left_axis_figure(s)
            box = (5 * s, 250 * s, 35 * s, 150 * s)
            above = (2 * s, 35 * s, 0 * s, 20 * s)
            free = G.label_strip(d, box, 50 * s, 140 * s)
            with_above = G.label_strip(d, box, 50 * s, 140 * s, neighbours=(above,))
            self.assertEqual(free, with_above)
        self.check(go)

    # --- clause: it does not cross the caption floor -------------------------

    def test_the_caption_floor_ends_the_strip(self):
        def go(s):
            d = left_axis_figure(s)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            full = G.label_strip(d, box, 50 * s, 140 * s)
            cut = G.label_strip(d, box, 50 * s, 140 * s, floor=100 * s)
            self.assertIsNotNone(cut)
            self.assertEqual(cut[3], 100 * s)
            self.assertLess(cut[3], full[3])
        self.check(go)

    # --- clause: it overlaps the axis run ------------------------------------

    def test_a_panel_with_nothing_beside_its_axis_owns_nothing(self):
        def go(s):
            d = left_axis_figure(s, title=False)
            d[:, :45 * s] = False                       # erase the numerals too
            strip = G.label_strip(d, (25 * s, 250 * s, 35 * s, 150 * s), 50 * s, 140 * s)
            self.assertIsNone(strip)
        self.check(go)


class ThreeBoxes(unittest.TestCase):

    def check(self, fn):
        global RUN
        for s in SCALES:
            with self.subTest(scale=s):
                fn(s)
            RUN += 1

    def test_a_strip_inside_the_box_comes_off_the_plot_core(self):
        """The 475 figure-2 shape: the box already contains the numerals, so the
        marks reader has been looking at a column of digits as data."""
        def go(s):
            d = left_axis_figure(s)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            g = G.geometry(d, box, 50 * s, 140 * s)
            self.assertEqual(g["plot_box"][0], 50 * s)
            self.assertGreater(g["plot_box"][0], box[0],
                               "the numerals were inside the plot core")
            self.assertEqual(g["review_box"][1:], box[1:],
                             "only the left edge may move")
        self.check(go)

    def test_a_strip_outside_the_box_comes_back_in_the_review_crop(self):
        """The other direction: the box starts right of the numerals, so the
        person checking the panel would never see the axis their numbers
        came from."""
        def go(s):
            d = left_axis_figure(s)
            box = (48 * s, 250 * s, 35 * s, 150 * s)
            g = G.geometry(d, box, 50 * s, 140 * s)
            self.assertLess(g["review_box"][0], box[0])
            self.assertEqual(g["review_box"][0], 10 * s)
        self.check(go)

    def test_the_plot_core_never_crosses_its_own_spine(self):
        """Numerals printed hard against the axis, with no gutter between them
        and the spine.  The band then runs right up to the spine, and the plot
        core would start one column PAST its own axis - a plot box that does not
        contain the axis it is measured from."""
        def go(s):
            d = left_axis_figure(s)
            box = (25 * s, 250 * s, 35 * s, 150 * s)
            strip = G.label_strip(d, box, 50 * s, 140 * s)
            self.assertEqual(strip[1], 50 * s, "ownership runs up to the axis")
            g = G.geometry(d, box, 50 * s, 140 * s)
            self.assertLessEqual(g["plot_box"][0], 50 * s)
        self.check(go)


class Signature(unittest.TestCase):

    def test_the_ladder_hash_follows_the_values_not_the_pixels(self):
        """Two readings of one axis at two box widths are one axis."""
        global RUN
        self.assertEqual(G.ladder_hash("100:80.0;50:160.0;0:240.0"),
                         G.ladder_hash("100:83.4;50:163.4;0:243.4"))
        self.assertNotEqual(G.ladder_hash("100:80.0;50:160.0;0:240.0"),
                            G.ladder_hash("100:80.0;50:160.0;10:240.0"))
        self.assertEqual(G.ladder_hash(""), "")
        RUN += 3

    def test_identity_does_not_change_when_the_measurement_improves(self):
        """A better reading of one spine reads MORE numerals off it.  If that
        changed the panel's identity, every improvement would report as a
        different panel - the mistake `panel_count` makes one level up."""
        global RUN
        for s in SCALES:
            d = left_axis_figure(s)
            a = G.signature(d, (25 * s, 250 * s, 35 * s, 150 * s), 50 * s, 140 * s,
                            "100:80;0:240")
            b = G.signature(d, (25 * s, 250 * s, 35 * s, 150 * s), 50 * s, 140 * s,
                            "100:80;50:160;0:240")
            self.assertEqual({k: v for k, v in a.items() if k != "ladder"},
                             {k: v for k, v in b.items() if k != "ladder"})
            self.assertNotEqual(a["ladder"], b["ladder"])
            RUN += 1

    def test_two_panels_on_one_spine_share_a_signature(self):
        """Over-segmentation, stated as an identity rather than as a count."""
        global RUN
        for s in SCALES:
            d = left_axis_figure(s)
            upper = G.signature(d, (25 * s, 250 * s, 35 * s, 90 * s), 50 * s, 140 * s)
            lower = G.signature(d, (25 * s, 250 * s, 90 * s, 150 * s), 50 * s, 140 * s)
            self.assertEqual(upper, lower)
            RUN += 1


class MemoisedRuns(unittest.TestCase):
    """`axis_reader.figure_key`: a memo key that cannot outlive its raster."""

    def test_a_rasters_entries_go_when_the_raster_does(self):
        """`id()` is unique only while the object is alive, and CPython hands a
        freed address to the next allocation - so an id-keyed cache can answer a
        question about a live array with a dead one's spine runs. Found by two
        scenarios that passed alone and failed together.
        Guard: figure_key's weakref callback."""
        global RUN
        d = np.zeros((60, 40), dtype=bool)
        d[10:55, 5] = True
        A.spine_run(d, 5, 0, 60)
        A.axis_anchor(d, (0, 40, 0, 60))
        key = id(d)
        self.assertTrue([c for c in A._RUN_CACHE if c[0] == key])
        self.assertTrue([c for c in A._ANCHOR_CACHE if c[0] == key])
        self.assertIn(key, A._LIVE_FIGURES)
        del d
        gc.collect()
        self.assertEqual([c for c in A._RUN_CACHE if c[0] == key], [])
        self.assertEqual([c for c in A._ANCHOR_CACHE if c[0] == key], [])
        self.assertNotIn(key, A._LIVE_FIGURES)
        RUN += 1

    def test_a_live_raster_keeps_its_entries(self):
        """A cache that empties itself is not a cache. The eviction must be tied
        to the referent's death and to nothing else."""
        global RUN
        d = np.zeros((60, 40), dtype=bool)
        d[10:55, 5] = True
        first = A.spine_run(d, 5, 0, 60)
        other = np.zeros((60, 40), dtype=bool)
        other[10:55, 5] = True
        A.spine_run(other, 5, 0, 60)
        del other
        gc.collect()
        key = id(d)
        self.assertTrue([c for c in A._RUN_CACHE if c[0] == key])
        self.assertEqual(A.spine_run(d, 5, 0, 60), first)
        RUN += 1

    def test_an_unweakreferenceable_raster_still_measures(self):
        """The caches are an optimisation and must never be the reason a figure
        fails to measure, so an object weakref cannot hold falls back to the old
        behaviour rather than to a TypeError."""
        global RUN
        probe = _NoWeakref()
        self.assertEqual(A.figure_key(probe), id(probe))
        self.assertNotIn(id(probe), A._LIVE_FIGURES)
        RUN += 1


class _NoWeakref(object):
    __slots__ = ()


_PROBE = _NoWeakref()


class Columns(unittest.TestCase):

    #: The cells the measurement writes. A geometry cell landing on any of these
    #: would not be an added column - it would be a changed measurement wearing
    #: the name of one.
    MEASUREMENT = ("x0", "x1", "y0", "y1", "spine_x", "baseline_y", "status",
                   "ticks", "fragment", "detail", "n_labels", "resid_px",
                   "spacing_cv", "bar_centres", "x_status")

    def test_no_geometry_cell_lands_on_a_measurement_cell(self):
        """The whole point of this step being additive."""
        global RUN
        d = left_axis_figure(1)
        cells = G.as_columns(G.geometry(d, (25, 250, 35, 150), 50, 140))
        self.assertTrue(cells)
        self.assertEqual(sorted(set(cells) & set(self.MEASUREMENT)), [])
        RUN += 1

    def test_the_numeral_band_is_carried_as_its_own_cells(self):
        """Ownership and OCR answer different questions and must be readable
        apart: a panel with a label box and no readable numerals has to be
        distinguishable from one with neither."""
        global RUN
        d = left_axis_figure(1)
        cells = G.as_columns(G.geometry(d, (25, 250, 35, 150), 50, 140))
        self.assertIn("numeral_x0", cells)
        self.assertNotEqual(cells["numeral_x0"], cells["label_x0"])
        self.assertNotEqual(cells["numeral_x1"], cells["label_x1"])
        RUN += 1

    def test_every_geometry_cell_is_actually_written(self):
        """A cell `as_columns` produces and `propose.py` does not list is a cell
        `DictWriter` drops without saying so - the quietest way for this whole
        step to be a no-op that reads as done."""
        global RUN
        existing = _propose_columns()
        self.assertIn("x0", existing, "read the wrong list")
        d = left_axis_figure(1)
        cells = G.as_columns(G.geometry(d, (25, 250, 35, 150), 50, 140))
        self.assertEqual(sorted(set(cells) - set(existing)), [])
        self.assertIn("geom_note", existing,
                      "the failure column has to be written too, or a geometry "
                      "that failed is indistinguishable from one that found nothing")
        RUN += 1


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print("FDT_SCENARIOS_RUN=%d" % RUN)
    sys.exit(0 if result.wasSuccessful() else 1)
