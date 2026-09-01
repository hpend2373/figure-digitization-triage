# -*- coding: utf-8 -*-
"""Where the figures actually are, on the pages the crop harness scores.

WHY THIS FILE EXISTS. `regress_crop.py` used to score a box by measuring ink
INSIDE THAT SAME BOX - target ink over the caption's own span, foreign ink over
another caption's. That is circular: a box that misses its figure entirely
still scores, because whatever it does hold is what gets measured. It passed
19 of 19 while five crops were, by eye, still wrong, and four rounds of
algorithm work were steered by it.

A harness needs something the code cannot move. These are regions read off the
rendered pages against a printed grid, one figure at a time. They are
MEASUREMENTS, not the publisher's content, so unlike the rasters they can live
here - which is what makes the harness reproducible from this repository plus
the reader's own copy of the PDFs.

Coordinates are fractions of the page, (x0, y0, x1, y1) from the top left, so
they hold at any render resolution. They are deliberately generous at the
edges: the question a crop has to answer is "is the whole figure here, and
nothing else's figure", not "is this box correct to the pixel".

Every entry was established by looking. None was derived from the box the
pipeline produced - that is the entire point.
"""

#: (pid, FIGURE LABEL, page) -> (x0, y0, x1, y1) as fractions of the page.
FIGURE_REGIONS = {
    # --- publication 36, page 4. Two figures, one per column, the ordinary
    # case. Both judged FIXED, and here so the harness can be shown to pass
    # what a person passed rather than only to fail what they failed.
    ("36", "FIG1", "4"): (0.06, 0.065, 0.47, 0.325),
    ("36", "FIG2", "4"): (0.50, 0.065, 0.93, 0.375),

    # --- publication 99. Page 6 is the ordinary case, three figures in two
    # columns, all judged FIXED.
    ("99", "FIG2", "6"): (0.06, 0.085, 0.48, 0.61),
    ("99", "FIG3", "6"): (0.50, 0.085, 0.94, 0.49),
    ("99", "FIG4", "6"): (0.50, 0.635, 0.94, 0.83),
    # Page 4 is not: the caption sits in the RIGHT column at mid height and
    # both stacked power-spectral-density charts are in the LEFT, so "the gap
    # above the caption, in the caption's column" is white space.
    ("99", "FIG1", "4"): (0.07, 0.10, 0.56, 0.67),

    # --- publication 516. Pages 4 and 5 are ordinary; page 6 is not.
    ("516", "FIG1", "4"): (0.09, 0.16, 0.49, 0.87),
    ("516", "FIG2", "4"): (0.52, 0.085, 0.93, 0.63),
    ("516", "FIG3", "5"): (0.09, 0.175, 0.49, 0.87),
    ("516", "FIG4", "5"): (0.53, 0.085, 0.93, 0.30),
    # The caption is printed to the LEFT of the figure and level with its
    # middle. The figure is a two-row panel block - Density above, Kd below -
    # and a box that stops at the caption's top keeps only the top row.
    ("516", "FIG5", "6"): (0.42, 0.08, 0.93, 0.33),

    # --- publication 533, page 3. Ordinary two-column, both FIXED.
    ("533", "FIG2", "3"): (0.07, 0.075, 0.48, 0.605),
    ("533", "FIG3", "3"): (0.53, 0.085, 0.93, 0.29),

    # --- publication 437, page 176. Two figures side by side under ONE
    # caption line: "Fig. 2 4D lung model      Fig. 3 Ventilated volumes at
    # apex and basis". The gutter between them is near x = 0.48.
    ("437", "FIG1", "176"): (0.11, 0.07, 0.84, 0.38),
    ("437", "FIG2", "176"): (0.11, 0.46, 0.47, 0.70),
    ("437", "FIG3", "176"): (0.49, 0.46, 0.88, 0.68),

    # --- publication 397, page 4. ONE figure spanning both columns: eight
    # panels, MEN on the left and WOMEN on the right, under a caption that
    # starts in the left column.
    ("397", "FIG1", "4"): (0.06, 0.075, 0.68, 0.70),

    # --- publication 554, page 5. The caption-beside-the-figure layout again:
    # both captions are in the RIGHT column, both bar charts in the LEFT.
    ("554", "FIG3", "5"): (0.11, 0.075, 0.45, 0.30),
    ("554", "FIG4", "5"): (0.11, 0.365, 0.45, 0.60),

    # --- publication 700, page 3. One flow chart across the full width -
    # Session A on the left, Session B on the right, one figure.
    ("700", "FIG1", "3"): (0.09, 0.075, 0.90, 0.375),

    # --- publication 518, page 3. Caption in the right column, a four-panel
    # block in the left and middle.
    ("518", "FIG1", "3"): (0.07, 0.085, 0.63, 0.50),

    # --- publication 159, page 5. Three stacked panels A/B/C in the centre
    # right, caption to their left.
    ("159", "FIG3", "5"): (0.40, 0.615, 0.88, 0.90),
}

#: What a person judged of the crop the pipeline produced, at the fifth audit.
#: The harness has to agree with this on every entry, or the harness is what is
#: wrong. Kept beside the regions so the two cannot drift apart.
#: Figures a person judged, that the harness can no longer put a number on.
#:
#: A REFUSAL IS NOT AN AGREEMENT AND IT IS NOT A FAILURE EITHER. `covered` and
#: `intrusion` are shares of a page, so they need the page's size; when the
#: geometry is not one of the trusted methods, or the draft offers two boxes
#: and nothing says which, the honest answer is that this crop cannot be
#: scored. Both of these were scored by an earlier run, on page geometry that
#: run had no business trusting - so the refusal is the improvement, not the
#: regression.
#:
#: Recorded here, one line each, because a refusal nobody wrote down is
#: indistinguishable from the harness quietly losing its grip on a case. A new
#: one that is not in this map is a failure until a person puts it here.
NOT_SCORABLE = {
    ("437", "FIG2", "176"): "374쪽 단행본 - 쪽 크기가 균일하지 않아 기하가 "
                            "신뢰 범위 밖입니다. 사람은 WRONG으로 봤고, "
                            "계수는 어느 쪽이든 막힙니다.",
    ("518", "FIG1", "3"): "초안이 상자 두 개를 내놓고 어느 쪽인지 말하지 "
                          "않습니다. 사람은 WRONG으로 봤고, 계수는 어느 "
                          "쪽이든 막힙니다.",
}

VISUAL_VERDICT = {
    # the ten the fifth audit judged FIXED
    ("36", "FIG1", "4"): "OK",
    ("36", "FIG2", "4"): "OK",
    ("99", "FIG2", "6"): "OK",
    ("99", "FIG3", "6"): "OK",
    ("516", "FIG1", "4"): "OK",
    ("516", "FIG2", "4"): "OK",
    ("516", "FIG3", "5"): "OK",
    ("516", "FIG4", "5"): "OK",
    ("533", "FIG2", "3"): "OK",
    ("533", "FIG3", "3"): "OK",
    # and the eight it judged still wrong
    ("99", "FIG1", "4"): "WRONG",     # the PSD charts below are missing
    ("516", "FIG5", "6"): "WRONG",    # only the top row of bars
    ("437", "FIG2", "176"): "WRONG",  # Fig. 3's graph is in the box too
    ("554", "FIG4", "5"): "WRONG",    # mostly blank; the bar chart is elsewhere
    ("700", "FIG1", "3"): "WRONG",    # Session B is missing
    ("397", "FIG1", "4"): "WRONG",    # the WOMEN half is clipped
    ("518", "FIG1", "3"): "WRONG",    # four graphs, a sliver of one shown
    ("159", "FIG3", "5"): "WRONG",    # A/B/C, only the start of A and B
}


def regions_on(pid, page):
    """{label: box} for one page of one publication."""
    return {label: box for (p, label, pg), box in FIGURE_REGIONS.items()
            if p == str(pid) and pg == str(page)}


def overlap(a, b):
    """Area of the intersection of two fractional boxes."""
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def covered(box, truth):
    """Share of the TRUE figure the box holds. 1.0 = the whole figure."""
    return overlap(box, truth) / area(truth) if area(truth) else 0.0


def intrusion(box, others):
    """Largest share of ANOTHER figure the box holds. 0.0 = none of them."""
    return max([overlap(box, o) / area(o) for o in others if area(o)] or [0.0])
