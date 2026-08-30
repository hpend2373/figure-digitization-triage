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
    # Publication 99, page 4. The caption sits in the RIGHT column at mid
    # height; both stacked power-spectral-density charts are in the LEFT.
    # "The gap above the caption in the caption's column" is white space here.
    ("99", "FIG1", "4"): (0.07, 0.10, 0.56, 0.67),

    # Publication 516, page 6. The caption is printed to the LEFT of the
    # figure and level with its middle. The figure is the two-row panel block
    # - Density above, Kd below - and a box that stops at the caption's top
    # edge keeps only the top row, which is what the audit saw.
    ("516", "FIG5", "6"): (0.42, 0.08, 0.93, 0.33),

    # Publication 437, page 176. Two figures side by side under ONE caption
    # line: "Fig. 2 4D lung model      Fig. 3 Ventilated volumes at apex and
    # basis". The gutter between them is near x = 0.48.
    ("437", "FIG1", "176"): (0.11, 0.07, 0.84, 0.38),
    ("437", "FIG2", "176"): (0.11, 0.46, 0.47, 0.70),
    ("437", "FIG3", "176"): (0.49, 0.46, 0.88, 0.68),

    # Publication 516, page 4. The ordinary two-column case, and the audit
    # judged both of these FIXED - they are here so the harness can be shown
    # to pass what a person passed, not only to fail what a person failed.
    ("516", "FIG1", "4"): (0.09, 0.16, 0.49, 0.87),
    ("516", "FIG2", "4"): (0.52, 0.085, 0.93, 0.63),
}

#: What a person judged of the crop the pipeline produced, at the fifth audit.
#: The harness has to agree with this on every entry, or the harness is what is
#: wrong. Kept beside the regions so the two cannot drift apart.
VISUAL_VERDICT = {
    ("99", "FIG1", "4"): "WRONG",     # the PSD charts below are missing
    ("516", "FIG5", "6"): "WRONG",    # only the top row of bars
    ("437", "FIG2", "176"): "WRONG",  # Fig. 3's graph is in the box too
    ("516", "FIG1", "4"): "OK",
    ("516", "FIG2", "4"): "OK",
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
