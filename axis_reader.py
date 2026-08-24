"""Measure a figure's panels and each panel's y axis, and refuse what it cannot check.

Two things this does that the shipped proposer does not:

  PANEL SEGMENTATION by recursive XY-cut. A multi-panel figure is separated by
  whitespace gutters, so cutting on the widest empty band and recursing finds the
  blocks; a block is kept only if it holds BOTH a long vertical run and a long
  horizontal run, which is what an axis pair looks like. The proposer has no
  segmentation at all and returns one frame across four panels.

  TICK VALUES BY OCR, WITH A CONSISTENCY TEST. tesseract reads the numerals and
  reports a box per numeral, so the value and its pixel row arrive together. A
  misread 30-as-3 then breaks either monotonicity or the constant spacing of the
  ladder, and that is the check the design said no arithmetic could do: it is not
  arithmetic on the VALUE, it is arithmetic on the SEQUENCE. Three or more labels
  are needed for it to mean anything, so two-label axes are refused.

Everything emitted is PROPOSED. Nothing here writes a confirmation.
"""
import re
import collections
import numpy as np
from PIL import Image
try:                       # OCR IS AN OPTIONAL BACKEND, the way the PDF readers are.
    import pytesseract     # Panels, spines, baselines and continuity are geometry and
except ImportError:        # call none of it, so requiring tesseract to IMPORT this module
    pytesseract = None     # would put the whole harness behind a system package.

INK = 140                 # a grey below this is ink
GUTTER_INK = 0.004        # a row/column with less inked fraction than this is empty
MIN_GUTTER = 8            # a gutter narrower than this is letter spacing
MIN_BLOCK = 90            # the cut stops recursing below this
MIN_AXIS_PX = 40          # an axis line shorter than this cannot carry a calibration
AXIS_TIE = 0.95           # two rules this close in length are the same rule, twice
FRAME_SPAN = 0.95         # a run longer than this share of the block is the page, not an axis
#: How the cut decides whether a whitespace band is interior to a panel.
#:   OFF   - cut the widest gutter, as an XY-cut does
#:   PLAIN - never cut through a rule that runs across the gutter
#:   CAP   - PLAIN, but ignore rules that span almost the whole block (page borders)
#: None of the three is right on all 187 figures, which is why the caller tries
#: all three and keeps the one whose panel count matches the axes I counted by eye.
SEVER_MODE = "PLAIN"
import os as _os
SNAP = _os.environ.get("SNAP", "1") != "0"    # harness: offer the box the spine implies
CAP = _os.environ.get("CAP", "1") != "0"      # harness: the caption is the figure floor
BROAD = _os.environ.get("BROAD", "1") != "0"  # harness: when the cut cannot place a row, take the slab
WIDE = _os.environ.get("WIDE", "1") != "0"    # harness: put back the fragment the cut sliced off
CAP_FLOOR = None         # set per figure by the caller; the caption starts at this row
FIG_TARGET = 0           # how many panels this figure is known to have, 0 if unknown
AXIS_RUN = 0.45           # a run this fraction of the block is an axis line
MAX_DEPTH = 4
SPACING_CV = 0.08         # tick ladder regularity
MIN_LABELS = 3


def _dark(path_or_img):
    im = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    a = np.asarray(im.convert("L"))
    return a, a < INK


def _longest_run(v):
    best = run = 0
    for x in v:
        run = run + 1 if x else 0
        if run > best:
            best = run
    return best


def _run_at(v, i):
    """Length of the contiguous inked run that CONTAINS index i (0 if i is blank).

    Not the longest run in the line - the run through the cut. Two panels side by
    side both have a long baseline, and asking only "is there a long run in this
    row" says yes for the row that crosses both, which refuses the very cut that
    separates them. Asking whether the run passes THROUGH the gutter is the
    question that distinguishes an interior gap from a panel boundary.
    """
    n = len(v)
    if i < 0 or i >= n or not v[i]:
        return 0
    a = i
    while a > 0 and v[a - 1]:
        a -= 1
    b = i
    while b + 1 < n and v[b + 1]:
        b += 1
    return b - a + 1


def _gutters(profile, limit):
    """[(start, end)] runs of near-empty lines wider than MIN_GUTTER."""
    empty = profile < GUTTER_INK
    out, start = [], None
    for i, e in enumerate(empty):
        if e and start is None:
            start = i
        elif not e and start is not None:
            if i - start >= MIN_GUTTER:
                out.append((start, i))
            start = None
    if start is not None and limit - start >= MIN_GUTTER:
        out.append((start, limit))
    return out


def _trim(dark, box):
    """Shrink a box to the rows and columns that actually hold ink.

    An XY-cut leaf is bounded by the gutters that made it, not by its content, so
    a block that carries a caption line and 40 px of white margin is measured as
    taller than its own axis. The 45% run test then refuses a real panel for a
    reason that is about the margin, not about the plot. Trimming first makes the
    test ask what it means to ask: is this line long compared to the DRAWING.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    if sub.size == 0:
        return box
    rows = np.where(sub.mean(axis=1) >= GUTTER_INK)[0]
    cols = np.where(sub.mean(axis=0) >= GUTTER_INK)[0]
    if rows.size == 0 or cols.size == 0:
        return box
    return (x0 + int(cols[0]), x0 + int(cols[-1]) + 1,
            y0 + int(rows[0]), y0 + int(rows[-1]) + 1)


def _is_plot(dark, box):
    """Does this block hold an axis pair?

    Measured two ways, because either alone is wrong. A FRACTION, so that a block
    whose long line spans a tenth of it is text and not an axis. And an ABSOLUTE
    length, so that a 20 px scrap with a 20 px line in it is not a panel. What is
    NOT tested is a square minimum on the block: a column of four bars is 85 px
    wide and 250 px tall, and refusing it for its width refused 8 real panels of
    publication 36 alone while its axes measured 0.81 and 1.00.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    if sub.shape[0] < MIN_AXIS_PX or sub.shape[1] < MIN_AXIS_PX:
        return False
    v = max(_longest_run(sub[:, x]) for x in range(sub.shape[1]))
    h = max(_longest_run(sub[y, :]) for y in range(sub.shape[0]))
    return (v >= AXIS_RUN * sub.shape[0] and h >= AXIS_RUN * sub.shape[1]
            and v >= MIN_AXIS_PX and h >= MIN_AXIS_PX)


def _has_y_axis(dark, box):
    """A weaker signature: a long VERTICAL run, and no demand for a bottom line.

    Plenty of published panels draw no x axis at all - a floating y axis with tick
    marks and nothing along the bottom. Refusing those for a missing horizontal
    run threw away 40 figures. So they are admitted as CANDIDATES, and the tick
    ladder is left to do the refusing: a candidate that cannot produce three
    numerals falling at a constant value per pixel never reaches the output.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    if sub.shape[0] < MIN_AXIS_PX or sub.shape[1] < MIN_AXIS_PX:
        return False
    v = max(_longest_run(sub[:, x]) for x in range(sub.shape[1]))
    return v >= AXIS_RUN * sub.shape[0] and v >= MIN_AXIS_PX


def _severs_axis(sub, mid, vertical):
    """Would a cut at `mid` cut THROUGH an axis line?

    The gutter between two bar groups and the gutter between two panels look the
    same to a whitespace profile. They are not the same: the panel's baseline runs
    THROUGH the first one and stops at the second. So before cutting a column, ask
    whether any row that holds a rule long enough to be an axis is inked at that
    column - if it is, the cut would sever the rule, and the whitespace is interior
    to one panel. This is what kept publication 402's single bar chart from being
    reported as three panels with a box a third of the figure wide.
    """
    if SEVER_MODE == "OFF":
        return False
    h, w = sub.shape
    # A run this long is not an axis, it is the page. Publication 323's figure 1
    # carries the journal's header rule down the whole raster - 1179 px of 1190 -
    # and one such line was enough to refuse every cut and report six panels as
    # one. An axis or a gridline spans the PLOT, which is always shorter than the
    # block that holds it, its labels and its margins.
    span = FRAME_SPAN if SEVER_MODE == "CAP" else 1e9
    if vertical:
        need, cap = max(MIN_AXIS_PX, AXIS_RUN * w), span * w
        return any(need <= _run_at(sub[y, :], mid) <= cap
                   for y in range(h) if sub[y, mid])
    need, cap = max(MIN_AXIS_PX, AXIS_RUN * h), span * h
    return any(need <= _run_at(sub[:, x], mid) <= cap
               for x in range(w) if sub[mid, x])


def _cut(dark, box, depth, out):
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    if sub.size == 0:
        return
    if depth >= MAX_DEPTH or sub.shape[0] < 2 * MIN_BLOCK and sub.shape[1] < 2 * MIN_BLOCK:
        out.append(box)
        return
    rows = sub.mean(axis=1)
    cols = sub.mean(axis=0)
    # the widest interior gutter on either axis, whichever is wider
    rg = [g for g in _gutters(rows, sub.shape[0]) if g[0] > 4 and g[1] < sub.shape[0] - 4]
    cg = [g for g in _gutters(cols, sub.shape[1]) if g[0] > 4 and g[1] < sub.shape[1] - 4]
    rbest = max(rg, key=lambda g: g[1] - g[0], default=None)
    cbest = max(cg, key=lambda g: g[1] - g[0], default=None)
    rw = (rbest[1] - rbest[0]) if rbest else 0
    cw = (cbest[1] - cbest[0]) if cbest else 0
    # widest first, but a cut that severs an axis is not taken at all
    cands = sorted([(rw, "row", rbest), (cw, "col", cbest)], reverse=True,
                   key=lambda t: t[0])
    for width, kind, g in cands:
        if width < MIN_GUTTER or g is None:
            continue
        mid = (g[0] + g[1]) // 2
        if kind == "row":
            if _severs_axis(sub, mid, vertical=False):
                continue
            _cut(dark, (x0, x1, y0, y0 + mid), depth + 1, out)
            _cut(dark, (x0, x1, y0 + mid, y1), depth + 1, out)
            return
        else:
            if _severs_axis(sub, mid, vertical=True):
                continue
            _cut(dark, (x0, x0 + mid, y0, y1), depth + 1, out)
            _cut(dark, (x0 + mid, x1, y0, y1), depth + 1, out)
            return
    out.append(box)


RULE_MIN_LEN = 90         # a structural rule is at least this long at 200 dpi
RULE_MAX_W = 4            # and no wider than this - a bar is wider
RULE_KEEP = 0.5           # rules shorter than this share of the longest are not structural
RULE_MERGE = 22           # rules closer than this are the same column or row


def _rules(dark, box, vertical):
    """[(start, end, length)] thin, long ink rules - the spines and baselines.

    Measured with an ABSOLUTE length floor rather than a fraction of the block,
    because the block is exactly what is not yet known: a leaf holding two rows of
    panels gives each panel's spine only 40% of its height, so a fractional test
    cannot see the grid it is supposed to find. Thin, because a bar is 6 px or more
    and a rule is 1 to 4.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    if vertical:
        runs = [_longest_run(sub[:, i]) for i in range(sub.shape[1])]
        off = x0
    else:
        runs = [_longest_run(sub[i, :]) for i in range(sub.shape[0])]
        off = y0
    hits = [i for i, r in enumerate(runs) if r >= RULE_MIN_LEN]
    groups = []
    for i in hits:
        if groups and i - groups[-1][-1] <= 3:
            groups[-1].append(i)
        else:
            groups.append([i])
    out = [(off + g[0], off + g[-1], max(runs[g[0]:g[-1] + 1]))
           for g in groups if g[-1] - g[0] + 1 <= RULE_MAX_W]
    if not out:
        return []
    longest = max(r[2] for r in out)
    out = [r for r in out if r[2] >= RULE_KEEP * longest]
    merged = []
    for r in out:
        if merged and r[0] - merged[-1][1] <= RULE_MERGE:
            merged[-1] = (merged[-1][0], r[1], max(merged[-1][2], r[2]))
        else:
            merged.append(r)
    return merged


def panels_from_rules(dark, shape=None):
    """Panels found from the axis rules themselves, as a grid.

    The whitespace XY-cut fails on a tight grid: publication 177's figure 2 is five
    rows by three columns and came back as seven blocks, because the bands between
    panels are narrower than a gutter. But the five baselines and three spines ARE
    there, 90 px long and 2 px thick. Reading the rules gives the grid directly, and
    the row band between two baselines is where the column cut belongs - so the
    whitespace search is used, just told where to look.
    """
    h, w = dark.shape
    box = (0, w, 0, h)
    vs = _rules(dark, box, True)
    hs = _rules(dark, box, False)
    if len(vs) * len(hs) < 2 or not vs or not hs:
        return []
    out = []
    for j, hr in enumerate(hs):
        top = (hs[j - 1][1] + 4) if j else 0
        bottom = min(h, hr[1] + 6)
        if bottom - top < MIN_AXIS_PX:
            continue
        for i, vr in enumerate(vs):
            left = vr[0] - 2
            if i + 1 < len(vs):
                band = dark[top:bottom, vr[1]:vs[i + 1][0]]
                if band.size == 0:
                    continue
                prof = band.mean(axis=0)
                gaps = _gutters(prof, len(prof))
                right = (vr[1] + (gaps[-1][0] + gaps[-1][1]) // 2) if gaps else vs[i + 1][0] - 4
            else:
                right = w
            if right - left < MIN_AXIS_PX:
                continue
            cell = _trim(dark, (max(0, left), min(w, right), top, bottom))
            # NO AXIS-PAIR TEST HERE. The cell was cut FROM a spine and a baseline,
            # so asking it to prove it holds an axis pair asks the same question
            # twice and answers it worse - on publication 92's figure 3 it threw
            # away four of the six cells the rules had just found. Size is the only
            # guard; the ladder is still the gate on what gets emitted.
            if (cell[1] - cell[0]) >= MIN_AXIS_PX and (cell[3] - cell[2]) >= MIN_AXIS_PX:
                out.append(cell)
    out.sort(key=lambda b: (b[1] - b[0]) * (b[3] - b[2]), reverse=True)
    return out


PLOT_INK_MIN = 0.002      # ink share right of the spine below this is not a plot
SOLID_INK_MAX = 0.90      # a box this inked all over is a filled legend, not a plot


def holds_data(dark, box):
    """Is there anything to the RIGHT of this box's spine?

    A label column is not a panel. The XY-cut keeps splitting until the numerals of
    a y axis sit alone in their own block, and that block passes every test a panel
    passes - it has a long vertical rule beside it and a checkable tick ladder, so
    it was being counted as a panel and pushing the panel count past the number of
    axes in the figure. Publication 349's figure 5 came back as eight panels for
    five axes; three of them were label columns with EXACTLY zero ink right of the
    spine. A plot has marks. This asks for them.
    """
    x0, x1, y0, y1 = box
    sx, _by = spine_and_baseline(dark, box)
    right = dark[y0:y1, min(x1, sx + 3):x1]
    if right.size == 0 or float(right.mean()) < PLOT_INK_MIN:
        return False
    whole = dark[y0:y1, x0:x1]
    if whole.size and float(whole.mean()) > SOLID_INK_MAX:
        return False
    return True


#: Boxes the harness changed on the last call, so a run can report where it
#: intervened instead of silently improving. {box: "why"}.
HARNESS_TAG = {}
FIGURE_BOXES = []        # boxes refused as being the whole figure, kept for the audit

MERGE_GAP = 28            # px between two pieces of one plot
MERGE_BASE_TOL = 4        # their baselines must agree to this many rows
REPEAT_MIN_GUTTER = 6     # row gap that separates two panels of one column


def _baseline_continuous(dark, by, x_from, x_to, need=0.85):
    """Is the baseline row inked all the way across the gap between two boxes?"""
    if x_to <= x_from:
        return True
    band = dark[max(0, by - 1):by + 2, x_from:x_to]
    if band.size == 0:
        return False
    return float(band.any(axis=0).mean()) >= need


def merge_split_panels(dark, boxes):
    """Join boxes that are two pieces of ONE plot.

    The cut sometimes slices a panel down a whitespace column inside the plot -
    publication 391's figure 4 came back with a 274 px box and a 43 px sliver two
    pixels to its right, sharing one baseline, and the sliver then counted as a
    panel and shifted every name after it. The test is not "are they close": it is
    whether THE BASELINE RUNS UNBROKEN from one into the other. A real gutter
    between two panels has no axis crossing it.
    """
    out = [tuple(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(len(out)):
                if i == j:
                    continue
                a, b = out[i], out[j]
                if not (0 <= b[0] - a[1] <= MERGE_GAP):
                    continue
                lo, hi = max(a[2], b[2]), min(a[3], b[3])
                if hi - lo < 0.6 * min(a[3] - a[2], b[3] - b[2]):
                    continue
                try:
                    _sa, bya = spine_and_baseline(dark, a)
                    _sb, byb = spine_and_baseline(dark, b)
                except Exception:
                    continue
                if abs(bya - byb) > MERGE_BASE_TOL:
                    continue
                if not _baseline_continuous(dark, bya, a[1], b[0]):
                    continue
                merged = (min(a[0], b[0]), max(a[1], b[1]),
                          min(a[2], b[2]), max(a[3], b[3]))
                new = _trim(dark, merged)
                HARNESS_TAG[new] = ("MERGED_SPLIT_PLOT: two boxes %d px apart shared "
                                    "baseline row %d with unbroken ink across the gap"
                                    % (b[0] - a[1], bya))
                out = [x for k, x in enumerate(out) if k not in (i, j)] + [new]
                changed = True
                break
            if changed:
                break
    return out


SNAP_MIN = 12             # a box that misses its own spine by less than this is not severed
ANCHOR_HALF = 0.60        # the y axis is in the left part of its own panel
ANCHOR_OVER = 0.30        # and it runs down most of the panel's rows
FIG_SHARE = 0.75          # a box covering this much of the plate is the plate
BROAD_GUTTER = 6          # blank columns that separate one column of panels from the next
BROAD_MERGE = 0.5         # verticals sharing this much of their rows are in one panel
BROAD_BORDER = 0.90       # a vertical this tall is a page border, not a panel's axis
BROAD_CAP = 3             # never offer more than this many slabs per missing panel
ADOPT_GAP = 34            # px between a panel and the piece the cut sliced off it
ADOPT_MIN = 8             # a sliver smaller than this is not a piece of a plot
ADOPT_SHARE = 0.50        # how much of the shorter side the two must share

_RUN_CACHE = {}
_ANCHOR_CACHE = {}


def _spine_segs(dark, spine_x, min_len=MIN_AXIS_PX):
    """(top, bottom) of every long ink run in this column."""
    col = dark[:, int(spine_x)]
    segs, start = [], None
    for i, v in enumerate(col):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append((start, i)); start = None
    if start is not None:
        segs.append((start, len(col)))
    return [t for t in segs if t[1] - t[0] >= min_len]


def spine_run(dark, spine_x, y0, y1, min_len=MIN_AXIS_PX):
    """The ink run in column `spine_x` that this box is sitting on. Memoised."""
    key = (id(dark), int(spine_x), min_len)
    segs = _RUN_CACHE.get(key)
    if segs is None:
        segs = _spine_segs(dark, spine_x, min_len)
        if len(_RUN_CACHE) > 20000:
            _RUN_CACHE.clear()
        _RUN_CACHE[key] = segs
    if not segs:
        return None
    best = max(segs, key=lambda t: min(t[1], y1) - max(t[0], y0))
    return best if min(best[1], y1) - max(best[0], y0) > 0 else None


def axis_anchor(dark, box, min_len=MIN_AXIS_PX):
    """Memoised wrapper around `_axis_anchor`."""
    key = (id(dark), tuple(box), min_len)
    if key not in _ANCHOR_CACHE:
        if len(_ANCHOR_CACHE) > 20000:
            _ANCHOR_CACHE.clear()
        _ANCHOR_CACHE[key] = _axis_anchor(dark, box, min_len)
    return _ANCHOR_CACHE[key]


def _axis_anchor(dark, box, min_len=MIN_AXIS_PX):
    """The column this box's y axis is really in, or None to keep the plain search.

    `spine_and_baseline` takes the longest vertical in the block, and that is the
    right answer only when the block IS a panel. When the cut has left a box 86 px
    tall on a 160 px panel, the panel's own axis is CLIPPED by the box edge and
    something else - a grid line, an error bar - is now the longest thing in it.
    Publication 397's figure 2 loses six of its eight panels exactly this way.

    A run that touches the top or bottom EDGE of the box is not evidence of an axis -
    it is evidence that the box has cut something. Among the runs that end inside the
    box, the leftmost one in the box's left part is the y axis.
    """
    x0, x1, y0, y1 = box
    h, w = dark.shape
    reach = int(x0 + ANCHOR_HALF * (x1 - x0))
    need = ANCHOR_OVER * max(1, y1 - y0)
    free, clipped = [], []
    for x in range(max(0, x0), min(w, max(x0 + 1, reach))):
        col = dark[:, x]
        if not col.any():
            continue
        s = None
        for y in range(h):
            if col[y] and s is None:
                s = y
            elif not col[y] and s is not None:
                if y - s >= min_len and min(y, y1) - max(s, y0) > need:
                    (clipped if (s <= y0 or y >= y1) else free).append((x, s, y))
                s = None
        if s is not None and h - s >= min_len and min(h, y1) - max(s, y0) > need:
            clipped.append((x, s, h))
    pick = free or clipped
    return min(pick, key=lambda t: t[0]) if pick else None


def caption_floor_trim(dark, boxes, floor):
    """No panel contains the caption. The caption belongs to the FIGURE."""
    if floor is None:
        return list(boxes)
    out = []
    for b in boxes:
        b = tuple(b)
        x0, x1, y0, y1 = b
        if y1 <= floor or y0 >= floor:
            out.append(b); continue
        new = _trim(dark, (x0, x1, y0, max(y0 + 1, floor - 2)))
        if new[3] - new[2] < MIN_AXIS_PX:
            continue
        HARNESS_TAG[new] = ("CAPTION_IS_NOT_A_PANEL: the box ran to row %d, past the "
                            "caption that starts at row %d, so it held figure text "
                            "rather than plot" % (y1, floor))
        out.append(new)
    return out


def figure_is_not_a_panel(dark, boxes, floor, target):
    """Drop the box that is the whole figure. Only when others remain to replace it."""
    if not target or target < 2 or len(boxes) < 3:
        return list(boxes)
    h, w = dark.shape
    top = min((b[2] for b in boxes), default=0)
    bottom = floor if floor else max((b[3] for b in boxes), default=h)
    plate = max(1, bottom - top)
    out = []
    for b in boxes:
        b = tuple(b)
        x0, x1, y0, y1 = b
        if ((min(y1, bottom) - y0) / plate >= FIG_SHARE
                and (x1 - x0) / w >= FIG_SHARE and len(boxes) - 1 >= 2):
            FIGURE_BOXES.append((b, "FIGURE_IS_NOT_A_PANEL: this box covers the whole "
                                    "plate above the caption, and the figure has %d "
                                    "panels" % target))
            continue
        out.append(b)
    return out if len(out) >= 2 else list(boxes)


def _axis_rows(dark, x0, x1, bottom, min_len=MIN_AXIS_PX):
    """Row bands in this column that hold a long vertical - one band per panel row."""
    runs = []
    for x in range(max(0, x0), min(dark.shape[1], x1)):
        col = dark[:bottom, x]
        if not col.any():
            continue
        s = None
        for y in range(bottom):
            if col[y] and s is None:
                s = y
            elif not col[y] and s is not None:
                if y - s >= min_len and (y - s) < BROAD_BORDER * bottom:
                    runs.append((s, y))
                s = None
        if s is not None and bottom - s >= min_len and (bottom - s) < BROAD_BORDER * bottom:
            runs.append((s, bottom))
    runs.sort()
    bands = []
    for a, b in runs:
        if bands and min(bands[-1][1], b) - max(bands[-1][0], a) > \
           BROAD_MERGE * min(b - a, bands[-1][1] - bands[-1][0]):
            bands[-1] = (min(bands[-1][0], a), max(bands[-1][1], b))
        else:
            bands.append((a, b))
    return [b for b in bands if b[1] - b[0] >= min_len]


def _iou(a, b):
    """Intersection over union - are these the SAME region?"""
    ix = min(a[1], b[1]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[2], b[2])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    ua = (a[1] - a[0]) * (a[3] - a[2]) + (b[1] - b[0]) * (b[3] - b[2]) - inter
    return inter / ua if ua > 0 else 0.0


def broad_slabs(dark, boxes, floor, target):
    """When the cut cannot decide where a row ends, take the whole slab between axes.

    A four by two plate of line charts defeats the whitespace cut, because the gap
    between two rows of panels is no wider than the gap inside a panel between its
    title, its plot and its rotated x labels. There is no threshold that separates
    those two kinds of gap - which is the point: DON'T CHOOSE. The axes say which
    rows hold a panel, so the row break goes in the middle of the empty space between
    two of them and the slab takes everything in between.

    Broad is safe because nothing is decided by it. Each slab is a CANDIDATE.
    """
    if not target or sum(1 for b in boxes if _is_plot(dark, b)) >= target:
        return []
    h, w = dark.shape
    bottom = floor if floor else h
    if bottom < MIN_AXIS_PX:
        return []
    prof = dark[:bottom].mean(axis=0)
    cols, prev = [], 0
    for a, b in _gutters(prof, w):
        if b - a >= BROAD_GUTTER and a > prev:
            cols.append((prev, a)); prev = b
    cols.append((prev, w))
    cols = [c for c in cols if c[1] - c[0] >= MIN_AXIS_PX]
    out = []
    have = sum(1 for b in boxes if _is_plot(dark, b))
    budget = BROAD_CAP * max(1, target - have)
    for cx0, cx1 in cols:
        bands = _axis_rows(dark, cx0, cx1, bottom)
        if len(bands) < 2:
            continue
        for i, (a, b) in enumerate(bands):
            top = 0 if i == 0 else (bands[i - 1][1] + a) // 2
            bot = bottom if i == len(bands) - 1 else (b + bands[i + 1][0]) // 2
            cell = _trim(dark, (cx0, cx1, max(0, top), min(bottom, bot)))
            if (cell[1] - cell[0]) < MIN_AXIS_PX or (cell[3] - cell[2]) < MIN_AXIS_PX:
                continue
            # REDUNDANT MEANS THE SAME BOX, NOT A BOX INSIDE ONE.
            if any(_iou(cell, o) >= 0.85 for o in boxes):
                continue
            if cell in out or not _has_y_axis(dark, cell):
                continue
            HARNESS_TAG[cell] = ("BROAD_SLAB: the row cut could not place this panel, so the "
                                 "slab between the axis at rows %d-%d and its neighbours was "
                                 "taken whole" % (a, b))
            out.append(cell)
            if len(out) >= budget:
                return out
    return out


def adopt_orphans(dark, boxes, orphans):
    """A block with no axis of its own, touching exactly one panel, is that panel's.

        하나의 패널
          → 막대 그룹 사이·곡선 아래·캡션 위의 빈 공간을 패널 경계로 오인
          → 왼쪽 조각 + 오른쪽 조각으로 분할
          → 한쪽만 y축을 보유
          → 축 없는 조각은 패널 필터에서 탈락
          → 데이터가 사라지거나 뒤 패널의 이름·축 배정까지 밀림

    Publication 345's figure 4 draws four bar groups per panel and the cut fell in
    the gap before the last one. The left piece kept the y axis and was offered as a
    panel; the right piece, 38 px of bars with no axis in it, failed every test a
    panel has to pass and was DISCARDED. The panel was then reported complete with a
    quarter of its data outside the box - a correct reading of an incomplete plot,
    which is the worst kind of wrong.

    The judgement is `continuity.verdict`: six independent statements, each measured
    and each recorded. Direction only chooses which pair of edges to measure, and only
    LEFT and RIGHT are looked at - see `continuity.same_coordinates` for why.

    THE GUARD IS AMBIGUITY. A block between two stacked panels could belong to either
    and ink cannot say which, so a block touching more than one panel is left alone.
    """
    out = list(boxes)
    taken = collections.Counter()

    # HOW FAR IS "TOUCHING"? A CONSTANT WAS ANSWERING THAT. `ADOPT_GAP` is 34 px and
    # publication 475's figure 2 slices panel E 37 px from its own third bar group,
    # so the piece was refused before any of the six statements were asked - by the
    # very kind of fixed distance criterion 1 exists to do without. The panel already
    # says how wide its own bar-group gaps are: 74 px here. That is the reach, with
    # the old constant kept as the FLOOR for panels whose baseline shows no gaps at
    # all, so this widens nothing - it stops the gate from overruling the test.
    budget = {}
    for b in boxes:
        span = ADOPT_GAP
        if SELF_GAP:
            try:
                an = axis_anchor(dark, b)
                bsx = an[0] if an is not None else spine_and_baseline(dark, b)[0]
                brun = spine_run(dark, bsx, b[2], b[3])
                import continuity as _C
                bby = _C.baseline_row(dark, b, bsx, brun)
                row = dark[max(0, bby - 1):bby + 2].any(axis=0)
                gaps = _row_gaps(row, int(bsx), b[1])
                span = max(ADOPT_GAP, max(gaps) if gaps else 0)
            except Exception:
                span = ADOPT_GAP
        budget[tuple(b)] = span

    for orp in orphans:
        ox0, ox1, oy0, oy1 = orp
        if (ox1 - ox0) < ADOPT_MIN or (oy1 - oy0) < ADOPT_MIN:
            continue
        cands = []
        for b in boxes:
            x0, x1, y0, y1 = b
            vov = max(0, min(y1, oy1) - max(y0, oy0))
            vsh = vov / max(1, min(y1 - y0, oy1 - oy0))
            # SIDEWAYS ONLY. Adopting the blocks ABOVE and BELOW was tried on the
            # corpus and cost ten ladders to gain nine x readings: what sits there is
            # the panel title and the axis title, pulling them in moves the top edge
            # the y label strip is measured from, and there is no way to test them.
            reach = budget.get(tuple(b), ADOPT_GAP)
            if ox0 >= x1 and ox0 - x1 <= reach and vsh >= ADOPT_SHARE:
                cands.append((ox0 - x1, "right", b))
            elif ox1 <= x0 and x0 - ox1 <= reach and vsh >= ADOPT_SHARE:
                cands.append((x0 - ox1, "left", b))
        if len(cands) != 1:
            continue                      # nobody, or nobody we can be sure about
        gap, side, b = cands[0]
        x0, x1, y0, y1 = b
        if taken[(tuple(b), side)]:
            continue                      # one adoption per side per panel
        try:
            an = axis_anchor(dark, b)
            sx = an[0] if an is not None else spine_and_baseline(dark, b)[0]
            run = spine_run(dark, sx, y0, y1)
        except Exception:
            continue
        if run is None:
            continue
        import continuity as C
        ok, tests = C.verdict(dark, b, orp, sx, run, CAP_FLOOR, side)
        if not ok:
            continue
        new = _trim(dark, (min(x0, ox0), max(x1, ox1), min(y0, oy0), max(y1, oy1)))
        if new in out:
            continue
        # A PANEL DOES NOT CONTAIN ANOTHER PANEL.
        if any(o is not b and (min(new[1], o[1]) - max(new[0], o[0])) *
               (min(new[3], o[3]) - max(new[2], o[2]))
               > 0.10 * (o[1] - o[0]) * (o[3] - o[2])
               and min(new[1], o[1]) > max(new[0], o[0])
               and min(new[3], o[3]) > max(new[2], o[2]) for o in boxes):
            continue
        taken[(tuple(b), side)] += 1
        HARNESS_TAG[new] = ("ADOPTED_ORPHAN: the block at %d-%d x %d-%d touches only this "
                            "panel (%s, %d px away) | %s"
                            % (ox0, ox1, oy0, oy1, side, gap, C.describe(tests)))
        out.append(new)
    return out


def snap_to_spine(dark, boxes):
    """Add, for a box that stops before its own axis line does, the box the axis says.

    ADDITIVE ON PURPOSE: growing a box is not always right, so both are offered and
    the LADDER picks.
    """
    out = [tuple(b) for b in boxes]
    for b in list(out):
        x0, x1, y0, y1 = b
        try:
            sx, _by = spine_and_baseline(dark, b)
        except Exception:
            continue
        run = spine_run(dark, sx, y0, y1)
        if run is None:
            continue
        ny0, ny1 = min(y0, run[0] - 2), max(y1, run[1] + 2)
        if (y0 - ny0) + (ny1 - y1) < SNAP_MIN:
            continue
        new = (x0, x1, max(0, ny0), min(dark.shape[0], ny1))
        if new in out:
            continue
        HARNESS_TAG[new] = ("EXTENDED_TO_SPINE: the box held rows %d-%d but its own axis "
                            "line runs %d-%d, so the cut severed the panel"
                            % (y0, y1, run[0], run[1]))
        out.append(new)
    return out


def column_siblings(dark, boxes):
    """Panels the cut missed, found by re-cutting the COLUMN a known panel sits in.

    A figure is a grid, so a column that holds one panel usually holds more. When
    the whitespace cut finds only one of them - publication 416's figure 4 returned
    the third M90 box plot and neither of the two above it - restricting the search
    to that panel's x range and cutting only on rows finds the siblings, because
    the horizontal structure that hid them is no longer in the way. Candidates
    only: each must still hold an axis pair and pass the ladder to be used.
    """
    h, w = dark.shape
    found = []
    for x0, x1, y0, y1 in boxes:
        if x1 - x0 < MIN_AXIS_PX:
            continue
        strip = dark[:, x0:x1]
        prof = strip.mean(axis=1)
        empty = prof < GUTTER_INK
        bands, start = [], None
        for i, e in enumerate(empty):
            if not e and start is None:
                start = i
            elif e and start is not None:
                if i - start >= MIN_AXIS_PX:
                    bands.append((start, i))
                start = None
        if start is not None and h - start >= MIN_AXIS_PX:
            bands.append((start, h))
        for a, b in bands:
            if min(b, y1) - max(a, y0) > 0.5 * (b - a):
                continue                        # this is the panel we came from
            cell = _trim(dark, (x0, x1, a, b))
            if (cell[1] - cell[0]) < MIN_AXIS_PX or (cell[3] - cell[2]) < MIN_AXIS_PX:
                continue
            if any(min(cell[1], o[1]) - max(cell[0], o[0]) > 0
                   and min(cell[3], o[3]) - max(cell[2], o[2]) > 0.5 * (cell[3] - cell[2])
                   for o in boxes):
                continue                        # already covered
            if _has_y_axis(dark, cell) and holds_data(dark, cell):
                HARNESS_TAG[cell] = ("FOUND_BY_COLUMN_RESCAN: the cut missed this panel; "
                                     "it was found by re-cutting the column x %d-%d"
                                     % (x0, x1))
                found.append(cell)
    return found


def panels(path, loose=False):
    """Candidate plot blocks, largest first. Boxes are (x0, x1, y0, y1).

    With loose=True the blocks that hold only a y axis are appended after the
    confident ones, so a caller can tell the two apart.
    """
    HARNESS_TAG.clear()
    del FIGURE_BOXES[:]
    a, dark = _dark(path)
    leaves = []
    _cut(dark, (0, a.shape[1], 0, a.shape[0]), 0, leaves)
    leaves = [_trim(dark, b) for b in leaves]
    keep = [b for b in leaves if _is_plot(dark, b) and holds_data(dark, b)]
    keep.sort(key=lambda b: (b[1] - b[0]) * (b[3] - b[2]), reverse=True)
    if SEVER_MODE == "GRID":
        keep = [b for b in panels_from_rules(dark) if holds_data(dark, b)]
        keep = merge_split_panels(dark, keep)
    if not loose:
        return keep, dark
    extra = ([] if SEVER_MODE == "GRID"
             else [b for b in leaves
                   if b not in keep and _has_y_axis(dark, b) and holds_data(dark, b)])
    # THE HARNESS RUNS ON THE WHOLE CANDIDATE SET, confident and loose together,
    # because a plot cut in two usually leaves one confident piece and one sliver -
    # merging only within the confident list never sees the pair.
    # AN ORPHAN IS DEFINED BY WHAT IT IS, NOT BY WHAT SURVIVED THE FILTER. Taking the
    # set difference against `keep` was wrong in GRID mode, where `keep` comes from
    # the rules rather than from the leaves - a real neighbouring panel was then in
    # the orphan list and got adopted whole.
    orphans = [b for b in leaves if not (_has_y_axis(dark, b) and holds_data(dark, b))]
    allb = merge_split_panels(dark, keep + extra)
    allb = allb + [c for c in column_siblings(dark, allb) if c not in allb]
    # ADOPTION RUNS AFTER THE COLUMN RESCAN. The rescan is not additive - it refuses a
    # cell overlapping a box already in the list - so widening a box first changes
    # which siblings it finds.
    if WIDE:
        allb = adopt_orphans(dark, allb, orphans)
    if CAP:
        allb = caption_floor_trim(dark, allb, CAP_FLOOR)
    if BROAD:
        slabs = [c for c in broad_slabs(dark, allb, CAP_FLOOR, FIG_TARGET)
                 if c not in allb]
        allb = allb + slabs
        # A SLAB NEVER GOT AN ADOPTION PASS. Adoption runs at step 8 and the slab is
        # built at step 6, so every box the row cut could not place was offered the
        # discarded pieces exactly zero times. That is how publication 475's figure 2
        # kept losing panel E's third bar group: the box that ended up being panel E
        # did not exist yet when the orphans were handed out. The second pass is
        # OFFERED THE SLABS ONLY, so nothing that already had its turn gets another.
        if WIDE and WIDE2 and slabs:
            grown = adopt_orphans(dark, slabs, orphans)
            allb = allb + [c for c in grown if c not in allb]
    if SNAP:
        allb = snap_to_spine(dark, allb)
    if CAP:
        # LAST, because it is the only step that REMOVES a candidate.
        allb = figure_is_not_a_panel(dark, allb, CAP_FLOOR, FIG_TARGET)
    keep = [b for b in allb if _is_plot(dark, b)]
    extra = [b for b in allb if b not in keep and _has_y_axis(dark, b)]
    keep.sort(key=lambda b: (b[1] - b[0]) * (b[3] - b[2]), reverse=True)
    extra.sort(key=lambda b: (b[1] - b[0]) * (b[3] - b[2]), reverse=True)
    return keep, dark, extra


def spine_and_baseline(dark, box):
    """(spine x, baseline y) - the LEFTMOST long vertical and LOWEST long horizontal.

    Not the plain argmax. A boxed panel draws a frame, so its top and bottom rules
    have the SAME length, and argmax returns whichever comes first - the top. Every
    measurement hanging off the baseline then looks in the wrong place: the x tick
    marks are searched for inside the plot, and the y label strip is cut off ten
    pixels below the frame's top edge. The baseline of a y axis is the bottom one,
    and the spine is the left one, so ties are broken that way on purpose.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    vruns = [_longest_run(sub[:, x]) for x in range(sub.shape[1])]
    vmax = max(vruns) if vruns else 0
    sx = next((x for x, v in enumerate(vruns) if v >= AXIS_TIE * vmax), 0)
    return x0 + sx, baseline_at(dark, box, x0 + sx)


def baseline_at(dark, box, spine_x):
    """The baseline a given spine stands on - the second half of spine_and_baseline.

    Split out because the spine can be WRONG and correctable (see `axis_anchor`),
    and a corrected spine needs its own baseline.
    """
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    sx = max(0, min(sub.shape[1] - 1, int(spine_x) - x0))
    hruns = [_longest_run(sub[y, sx:]) for y in range(sub.shape[0])]
    # THE LOWEST RULE, not the longest one. A significance bracket drawn across the
    # top of a panel is longer than the x axis, and a chart whose bars all point
    # down puts its zero line at the TOP - in both cases the longest horizontal run
    # is above the data, and everything measured from "the baseline" then looks in
    # the wrong place. Any row spanning AXIS_RUN of the block is a rule; the axis is
    # the last of them.
    need = max(MIN_AXIS_PX, AXIS_RUN * (sub.shape[1] - sx))
    cands = [y for y, h in enumerate(hruns) if h >= need]
    if cands:
        by = cands[-1]
    else:
        hmax = max(hruns) if hruns else 0
        by = max((y for y, h in enumerate(hruns) if h >= AXIS_TIE * hmax), default=0)
    return y0 + by


MARK_FRAG = _os.environ.get("MARKFRAG", "1") != "0"   # harness: a fragment leaves MARKS outside
SELF_GAP = _os.environ.get("SELFGAP", "1") != "0"     # harness: the panel says how far "touching" is
WIDE2 = _os.environ.get("WIDE2", "1") != "0"          # harness: the slab gets an adoption pass too


def _row_gaps(row, x_from, x_to):
    """Widths of the empty stretches between inked runs on one row."""
    xs = [x for x in range(int(x_from), min(len(row), int(x_to))) if row[x]]
    out, prev = [], None
    for x in xs:
        if prev is not None and x - prev > 1:
            out.append(x - prev - 1)
        prev = x
    return out


def _marks_outside(dark, box, by, frm, to):
    """Is there MARK ink outside the box on this side, or only the rule?"""
    y0, y1 = box[2], box[3]
    lo, hi = max(0, min(frm, to)), min(dark.shape[1], max(frm, to))
    if hi - lo < 2:
        return False
    band = dark[max(0, y0):min(dark.shape[0], y1), lo:hi]
    rule = dark[max(0, by - 2):by + 3, lo:hi]
    return int(band.sum()) - int(rule.sum()) >= PLOT_INK_MIN * band.size


def cut_through_axis(dark, box, spine_x, baseline_y, reach=None):
    """Did the segmentation cut THROUGH this panel's own axis lines?

    A box is only a panel if its axes end inside it. When the cut lands in the gap
    between two bar groups, the baseline runs in from the left and out to the
    right, so the pixels just OUTSIDE the box on the baseline row are still inked -
    a local, checkable signature that the box is a fragment of a wider panel and
    not a panel. Publication 402's single bar chart came out as three such
    fragments, each with a correct tick ladder read off the shared label column and
    a box a third of the plot wide, which is the worst kind of wrong: right numbers
    on the wrong geometry.

    TWO THINGS WERE WRONG WITH ASKING IT AT THREE PIXELS, and publication 475's
    figure 2 shows both at once.

    IT MISSED. Panel E's box stops at x=299 and its third bar group stands at
    337-367 - 37 px away, across a gap the cut mistook for a boundary. A three-pixel
    probe lands in white and reports a clean panel, which is the exact severance
    this check exists to catch, going unreported. The reach is now the panel's own
    widest baseline gap: the piece that was sliced off sits one bar-group gap away,
    and the panel says how wide that is.

    IT CRIED WOLF. That figure prints its zero line 51 px PAST the plotting area
    into the gutter, with no bar anywhere in the overrun. Panels A, C and F were
    called fragments for it and demoted out of AUTO_DIGITIZE. A rule leaving the box
    is not data leaving the box: what makes a box a fragment is MARKS outside it, so
    the ink in the overrun now has to be more than the rule itself.
    """
    x0, x1, y0, y1 = box
    h, w = dark.shape
    why = []
    by = int(baseline_y)
    if reach is None:
        reach = 3
        if MARK_FRAG:
            row = dark[max(0, by - 1):by + 2].any(axis=0)
            gaps = _row_gaps(row, int(spine_x), x1)
            reach = max(3, max(gaps) if gaps else 0)
    if 0 <= by < h:
        # A PANEL'S MARKS LIVE RIGHT OF ITS SPINE. Where the box's left edge IS the
        # axis, everything to its left is the y label strip and the axis title -
        # ink, but never marks - so there is nothing to ask on that side. Asking
        # anyway called 475 figure 2's panel E a fragment on the left because its
        # rotated axis title crosses the zero line.
        at_the_wall = MARK_FRAG and x0 >= int(spine_x) - 4
        left = dark[max(0, by - 1):by + 2, max(0, x0 - reach):x0].any()
        if x0 > 0 and left and not at_the_wall and (
                not MARK_FRAG or _marks_outside(dark, box, by, x0 - reach, x0)):
            why.append("baseline continues left of x0")
        right = dark[max(0, by - 1):by + 2, x1:min(w, x1 + reach)].any()
        if x1 < w and right and (not MARK_FRAG
                                 or _marks_outside(dark, box, by, x1, x1 + reach)):
            why.append("baseline continues right of x1")
    # THE SPINE KEEPS ITS THREE PIXELS. A y axis is one line, so ink just above or
    # below the box IS the axis running on; there is no bar-group gap to reach across
    # and nothing to mistake for a rule overrun.
    sx, pad = int(spine_x), 3
    if 0 <= sx < w:
        if y0 - pad >= 0 and dark[max(0, y0 - pad):y0, sx].any():
            why.append("spine continues above y0")
        if y1 + pad <= h and dark[y1:min(h, y1 + pad), sx].any():
            why.append("spine continues below y1")
    return "; ".join(why)


def _ocr_numerals(img, dark, left, right, top, bottom, scale=3):
    """[(value, row)] for every numeral tesseract finds in a strip, sign included.

    The sign comes from tesseract itself: '-' is in the whitelist, so "-20" is
    read as -20. A geometric minus detector was written on the assumption that
    tesseract drops the sign; reverting it changed neither the pass count nor a
    single tick string on 392 panels, so it was decoration and is gone.
    """
    if right - left < 8 or bottom - top < 20:
        return []
    if pytesseract is None:
        # NOT `return []`. "no numerals here" and "nothing looked" are different
        # answers, and only one of them is a fact about the figure - a ladder
        # silently built from zero numerals is the fail-open shape this package
        # refuses everywhere else.
        raise RuntimeError("reading a tick numeral needs pytesseract, which the "
                           "locked environment does not install; the geometry "
                           "path does not call this")
    strip = img.crop((int(left), int(top), int(right), int(bottom)))
    big = strip.resize((strip.width * scale, strip.height * scale), Image.LANCZOS)
    found = {}
    for psm in ("11", "6"):
        cfg = "--psm %s -c tessedit_char_whitelist=0123456789-." % psm
        try:
            d = pytesseract.image_to_data(big, config=cfg,
                                          output_type=pytesseract.Output.DICT)
        except Exception:
            continue
        for txt, l_, t_, w_, h_, conf in zip(d["text"], d["left"], d["top"],
                                             d["width"], d["height"], d["conf"]):
            s_ = (txt or "").strip().replace("--", "-")
            if not re.fullmatch(r"-?\d+(?:\.\d+)?", s_):
                continue
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = -1
            if c < 45:
                continue
            row = top + (t_ + h_ / 2.0) / scale
            key = round(row / 4)
            if key not in found or c > found[key][2]:
                found[key] = (float(s_), row, c)
    return sorted(((v, r) for v, r, _c in found.values()), key=lambda p: p[1])


#: Strips to try, as (how far left of the anchor to start, how wide). A label
#: column is not at a fixed distance: "-0.5" and "1200" are three times the width
#: of "50", and a shared y axis puts the numerals outside the panel's own block,
#: so the anchor is tried at the spine AND at the block's left edge.
#: NARROWEST FIRST. A wide strip reaches the rotated axis title, and "HR
#: (beats/min)" read sideways gave publication 475's figure 3 a label "2" between
#: 80 and 60 that broke the ladder. The wide strips are still tried, just later.
_STRIPS = ((2, 44), (6, 60), (6, 110), (6, 170))


LABEL_GAP = 7             # blank columns this wide end the label column
LABEL_BAND_MAX = 60       # a measured label column wider than this is not one
SCALES = (3, 4)           # magnifications the FALLBACK pass unions over


def label_band(dark, box, anchor, top, bottom, max_reach=180):
    """(left, right) of the FIRST block of ink to the left of `anchor`, measured.

    A fixed-width strip is a guess about where the numerals are, and on a narrow
    panel the guess reaches past them into the rotated axis title. Publication 95's
    figure 5 puts "BP(MCA)-LF Power (mm Hg)2/Hz" sideways at x 90-112, a blank
    gutter at 113-128, the digits at 129-137 and the spine at 147: every fixed
    strip wide enough to include the digits also included the title, and tesseract
    read one numeral out of seven. Walking left from the axis and stopping at the
    first gutter measures the label column instead of guessing it.
    """
    a = int(anchor) - 2
    lo_lim = max(0, a - max_reach)
    t, b = int(max(0, top)), int(min(dark.shape[0], bottom))
    if b - t < 4 or a <= lo_lim:
        return None
    inked = [x for x in range(lo_lim, a + 1) if dark[t:b, x].any()]
    if not inked:
        return None
    right = max(inked)
    left = right
    blank = 0
    x = right - 1
    while x >= lo_lim:
        if dark[t:b, x].any():
            left = x; blank = 0
        else:
            blank += 1
            if blank >= LABEL_GAP:
                break
        x -= 1
    if right - left < 3:
        return None
    # A MEASURED BAND WIDER THAN THIS HAS MERGED WITH SOMETHING ELSE. Where the
    # gutter between the numerals and the rotated title is under LABEL_GAP px, the
    # walk keeps going and swallows the title - publication 323's figure 1 came back
    # with a 129 px band and a self-consistent but wrong ladder, which is worse than
    # no band at all. A column of axis numerals is narrow; if the measurement says
    # otherwise, the measurement is not of a column of axis numerals.
    if right - left > LABEL_BAND_MAX:
        return None
    return left - 1, right + 2


def y_tick_labels(img, dark, box, spine_x, baseline_y=None, pad=6, width=58, scale=3):
    """The first strip geometry whose numerals form a checkable ladder.

    A search, not a guess: `ladder` has to accept the result, and it only accepts
    three or more labels that fall monotonically at a constant value per pixel.
    A strip that catches a caption, an axis title or the neighbouring panel's
    numbers fails that test, which is why trying several is safe.
    """
    x0, x1, y0, y1 = box
    # The strip runs to the BOTTOM OF THE BOX. Clipping it at the baseline was a
    # guard against a caption leaking a numeral in, but the box is now trimmed to
    # ink so the caption is usually outside it - and the guard cost every panel
    # whose lowest rule is not its x axis.
    bottom = max(y1 + 6, (baseline_y + 10) if baseline_y is not None else 0)
    # A BROKEN AXIS ENDS THE LADDER. Labels under the break are on another scale,
    # so the strip stops at the break rather than reading through it.
    brk = axis_break(dark, box, spine_x)
    if brk is not None and brk[0] > y0 + MIN_AXIS_PX:
        bottom = min(bottom, brk[0])
    top = max(0, y0 - 10)
    best = []
    for use_union in (False, True):
        for anchor in (spine_x, x0):
            band = label_band(dark, box, anchor, top, min(img.height, bottom))
            geoms = ([(anchor - band[1], band[1] - band[0])] if band else []) + list(_STRIPS)
            for gap, w in geoms:
                left, right = max(0, anchor - gap - w), max(1, anchor - gap)
                if not use_union:
                    pairs = _ocr_numerals(img, dark, left, right, top,
                                          min(img.height, bottom), scale)
                else:
                    # SECOND PASS ONLY. One strip read at two magnifications and
                    # unioned by row, because tesseract drops a different numeral at
                    # each: publication 122's heart-rate axis gives 70 at x3 and
                    # 80/50 at x4, so no single pass reaches the three labels the
                    # ladder needs while the axis is perfectly legible. Run FIRST it
                    # was harmful - it cost 23 panels to gain 14, because a union is
                    # also a union of noise - so it is a fallback, reached only when
                    # no single-scale strip produced a ladder. That makes it strictly
                    # additive. Rows where the two scales disagree are dropped, not
                    # arbitrated.
                    merged = {}
                    for sc in SCALES:
                        for v, row in _ocr_numerals(img, dark, left, right, top,
                                                    min(img.height, bottom), sc):
                            k = round(row / 4)
                            if k in merged and merged[k] and abs(merged[k][0] - v) > 1e-9:
                                merged[k] = None
                            elif k not in merged:
                                merged[k] = (v, row)
                    pairs = sorted((p for p in merged.values() if p), key=lambda p: p[1])
                if ladder(pairs)[0]:
                    return pairs
                if len(pairs) > len(best):
                    best = pairs
    return best


def axis_break(dark, box, spine_x, min_seg=20, gap_lo=4, gap_hi=60):
    """(gap_top, gap_bottom) where the y axis is CUT, or None.

    A broken axis is drawn as two slashes across the spine, and the spine itself
    stops and restarts. That gap is measurable without OCR: the column of the
    spine splits into two long runs. It matters because the labels below the break
    are NOT on the same scale as the labels above it - figure 3 of publication 475
    puts 0 below a break under 60, and a straight-line fit through both would
    misprice every bar in the panel.
    """
    x0, x1, y0, y1 = box
    col = dark[y0:y1, int(spine_x)]
    segs, start = [], None
    for i, v in enumerate(col):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append((start + y0, i + y0)); start = None
    if start is not None:
        segs.append((start + y0, y1))
    segs = [s for s in segs if s[1] - s[0] >= min_seg]
    for a, b in zip(segs, segs[1:]):
        gap = b[0] - a[1]
        if gap_lo <= gap <= gap_hi:
            return a[1], b[0]
    return None


def _runs_of(pairs, lo):
    """Contiguous slices of `pairs`, longest first, down to length `lo`."""
    n = len(pairs)
    for size in range(n, lo - 1, -1):
        for start in range(0, n - size + 1):
            yield pairs[start:start + size]


def ladder(pairs, allow_subset=True):
    """(ok, detail, first, last, residual_px, spacing_cv) for a tick ladder.

    The sequence is the check. Values must fall monotonically as the pixel row
    grows (a y axis increases upward), and the step between neighbouring labels
    must be constant: a misread digit breaks one or the other.

    When the whole set fails, the SAME test is applied to contiguous subsets, and
    the longest one that passes is returned with the dropped labels named. This is
    not a weaker test - every accepted subset satisfies exactly the conditions the
    full set had to satisfy, and the subset must be contiguous in pixel order so
    labels cannot be cherry-picked from opposite ends. It exists because two real
    things put a label into the strip that does not belong on the ladder: a broken
    axis, whose bottom label is on another scale, and a rotated axis title, whose
    letters OCR as a numeral. Both refused publication 475's figure 3 panels A and
    B, whose printed axes are perfectly regular.
    """
    if len(pairs) < MIN_LABELS:
        return False, "only %d label(s); %d needed to check a ladder" % (len(pairs), MIN_LABELS), None, None, None, None
    full = _check_ladder(pairs)
    if full[0] or not allow_subset or len(pairs) <= MIN_LABELS:
        return full
    winners = [sub for sub in _runs_of(pairs, MIN_LABELS) if _check_ladder(sub)[0]]
    if not winners:
        return full
    best = winners[0]
    if sum(1 for w in winners if len(w) == len(best)) > 1:
        return (False, "%s; more than one subset of %d labels forms a ladder, so which one is right is not determined"
                % (full[1], len(best)), None, None, None, None)
    ok, detail, first, last, resid, cv = _check_ladder(best)
    dropped = [p for p in pairs if p not in best]
    return (ok, "%s; SUBSET: dropped %s (%s)"
            % (detail, ", ".join("%g@%.0f" % (v, r) for v, r in dropped), full[1]),
            first, last, resid, cv)


def _check_ladder(pairs):
    if len(pairs) < MIN_LABELS:
        return False, "only %d label(s); %d needed to check a ladder" % (len(pairs), MIN_LABELS), None, None, None, None
    vals = [v for v, _ in pairs]
    rows = [r for _, r in pairs]
    falling = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
    # AN INVERTED AXIS IS STILL AN AXIS. A y axis normally rises upward, so values
    # fall as the pixel row grows - but published panels do invert it: a "% decrease"
    # plotted downward, publication 411's CrCP scale ("note the inverted scale" in
    # its own caption), publication 92's 3-D bars. Monotone in EITHER direction is
    # the constraint; the constant-spacing test is unchanged and the direction is
    # reported, because a calibration that has the sign backwards is not a detail.
    rising = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
    if not (falling or rising):
        return False, "values are not monotone with pixel row: %s" % vals, None, None, None, None
    steps = [vals[i] - vals[i + 1] for i in range(len(vals) - 1)]
    gaps = [rows[i + 1] - rows[i] for i in range(len(rows) - 1)]
    if min(gaps) <= 0:
        return False, "two labels share a row", None, None, None, None
    per = [s / g for s, g in zip(steps, gaps)]
    cv = float(np.std(per) / abs(np.mean(per))) if np.mean(per) else 9.9
    if cv > SPACING_CV:
        return False, "value-per-pixel varies %.1f%% across the ladder" % (100 * cv), None, None, None, None
    # least squares on the whole ladder, reported as the residual of the fit
    A = np.vstack([rows, np.ones(len(rows))]).T
    coef, *_ = np.linalg.lstsq(A, np.array(vals), rcond=None)
    pred = A @ coef
    resid = float(np.max(np.abs(pred - np.array(vals)) / abs(coef[0]))) if coef[0] else 9e9
    return True, "%d labels, %.3f value/px, ladder residual %.1f px%s" % (
        len(pairs), coef[0], resid,
        "" if falling else "  [AXIS_INVERTED: values rise as the pixel row rises]"), \
        pairs[0], pairs[-1], resid, cv
