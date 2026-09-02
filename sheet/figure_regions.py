# -*- coding: utf-8 -*-
"""Where the figures on a page actually are, and which caption names each.

WHY A SECOND WAY OF FINDING A FIGURE. `corpus_intake.figure_bbox` walks up
from one caption through TEXT blocks and calls the gap it lands in the figure.
Its own docstring says that is "a LOOK HERE for a contact sheet, not a crop
anybody measures from", and a look at all 461 of run2's countable rows agreed:
171 held no figure at all, 136 held a cut one. The reason is structural. A PDF
says where its drawings and images are, in points, and that walk never asks.

WHAT THIS DOES INSTEAD, in the order the four defect families demand:

    떨어진 패널 → 하나           panels drawn as a dozen separate objects are
                                 one figure, so objects are clustered before
                                 anything is matched to a caption.
    거터 너머는 남               two figures side by side in a two-column
                                 paper are not one wide figure, so a cluster
                                 is never allowed to grow across the gutter
                                 unless a single object already spans it.
    캡션과 후보를 함께 배정      a page's captions and candidates are matched
                                 jointly, one to one. Matching each caption on
                                 its own lets two captions claim one figure
                                 and leaves a real figure unclaimed.
    비슷하면 막는다              when a caption's best and second-best
                                 candidates score within `MARGIN`, nothing is
                                 chosen: an ambiguous assignment is a refusal,
                                 not a coin flip.

WHAT IT DOES NOT DO. It does not decide that a crop is good. It proposes a
region and says how sure it is; `sheet/census.py` still holds what a person
saw, and a region this module is sure about is still only a region.
"""
import os


#: How far apart two pieces of one drawing may sit and still be one figure,
#: in points. A panel's axis, its ticks and its legend arrive as separate
#: objects a few points apart; two figures on one page sit tens of points
#: apart. Measured from run2: raising this past ~20 starts joining a figure to
#: the one below it, and dropping it under ~6 splits axes off their panels.
GAP = 14.0

#: A drawing smaller than this (points squared) is a rule, a box corner or a
#: bullet, not a figure. Kept low so a small inset is still a candidate.
MIN_AREA = 1200.0

#: A candidate thinner than this in either direction is not a figure, whatever
#: its area. The running head's rule plus the strip of drawing around it makes
#: a 500x12 box that clears MIN_AREA comfortably, and in run2 one such strip
#: was picked over the figure below it. Nothing anybody counts panels in is
#: two centimetres by four millimetres.
MIN_SIDE = 24.0

#: A gap wider than GAP still belongs to one figure when nothing is written
#: in it: panels are often set a centimetre apart, and a reader joins them
#: because there is no prose in between. Beyond this the two are treated as
#: separate figures no matter how empty the space is.
REACH_BLANK = 130.0

#: A text line at least this wide (as a fraction of the page) is prose - a
#: caption, a paragraph, a heading. Narrower lines are the figure's own
#: furniture: panel letters, tick labels, axis titles. Prose between two
#: clusters means they are two figures; tick labels between them do not.
PROSE = 0.20

#: How much better the best candidate must score than the next one for the
#: match to be made at all.
MARGIN = 0.15

#: Distance that costs one full point of score, in points. A candidate twice
#: as far from its caption as another is not twice as wrong, but it is worse,
#: and this is the scale on which "worse" is measured.
REACH = 260.0


def _box(objs):
    return (min(o[0] for o in objs), min(o[1] for o in objs),
            max(o[2] for o in objs), max(o[3] for o in objs))


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def overlap(a, b, axis=0):
    """Length of the shared span on one axis: 0 for x, 1 for y."""
    lo, hi = axis, axis + 2
    return max(0.0, min(a[hi], b[hi]) - max(a[lo], b[lo]))


def furniture(graphics, size):
    """Indices of drawings that are page furniture rather than figure parts.

    A journal page carries a rule under its running head, a rule over its
    folio and sometimes a full-height column separator. Each is a drawing, so
    each would otherwise anchor a cluster - and a cluster anchored on a
    full-width rule swallows both columns.
    """
    w, h = size
    out = set()
    for i, g in enumerate(graphics):
        gw, gh = g[2] - g[0], g[3] - g[1]
        spans_page = gw > w * 0.8
        hairline = gh < 3.0 or gw < 3.0
        near_edge = g[3] > h - 60 or g[1] < 60
        if hairline and (spans_page or gh > h * 0.6):
            out.add(i)
        elif near_edge and hairline:
            out.add(i)
        elif area(g) < MIN_AREA:
            out.add(i)
    return out


def gutter(texts, size):
    """(x0, x1) of the empty band between two columns, or None.

    Found from the text, not guessed from the page width: a page laid out in
    one column has no gutter and must not be given one, and a two-column page
    whose columns are uneven must not be split down its middle.
    """
    w, h = size
    body = [t for t in texts if 60 < t[1] and t[3] < h - 40]
    if len(body) < 8:
        return None
    mid = w / 2.0
    left = [t for t in body if t[2] <= mid + w * 0.06]
    right = [t for t in body if t[0] >= mid - w * 0.06]
    if len(left) < 4 or len(right) < 4:
        return None
    edge_l = max(t[2] for t in left)
    edge_r = min(t[0] for t in right)
    if edge_r - edge_l < 8.0:
        return None
    return (edge_l, edge_r)


def cluster(graphics, size, texts=(), gap=GAP):
    """Figure candidates: drawings joined into the shapes a reader would see."""
    skip = furniture(graphics, size)
    items = [g for i, g in enumerate(graphics) if i not in skip]
    if not items:
        return []
    band = gutter(texts, size)

    def joinable(a, b):
        near = (overlap(a, b, 0) > -gap and overlap(a, b, 1) > -gap
                and _gap(a, b, 0) <= gap and _gap(a, b, 1) <= gap)
        if not near or band is None:
            return near
        # NEVER ACROSS THE GUTTER. Two panels in opposite columns pass the
        # distance test whenever the gutter is narrow, and asking whether each
        # box sits entirely outside the band does not work either - a panel
        # normally reaches a few points into it. What separates them is where
        # the EMPTY SPACE between them falls: if that space contains the middle
        # of the gutter, the two are in different columns.
        centre = (band[0] + band[1]) / 2.0
        if a[0] < centre < a[2] or b[0] < centre < b[2]:
            return True                 # one of them crosses on its own
        return not (min(a[2], b[2]) <= centre <= max(a[0], b[0]))

    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    changed = True
    while changed:                      # boxes grow as they merge, so repeat
        changed = False
        groups = {}
        for i in range(len(items)):
            groups.setdefault(find(i), []).append(i)
        keys = sorted(groups)
        boxes = {k: _box([items[i] for i in groups[k]]) for k in keys}
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                a, b = keys[x], keys[y]
                if find(a) == find(b):
                    continue
                if joinable(boxes[a], boxes[b]):
                    parent[find(a)] = find(b)
                    changed = True
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = [_box([items[i] for i in g]) for g in groups.values()]
    out = [b for b in out if area(b) >= MIN_AREA * 3
           and (b[2] - b[0]) >= MIN_SIDE and (b[3] - b[1]) >= MIN_SIDE]
    return join_over_blank(out, texts, size)


def _gap(a, b, axis):
    lo, hi = axis, axis + 2
    return max(0.0, max(a[lo], b[lo]) - min(a[hi], b[hi]))


def _between(a, b, axis):
    """The empty band between two boxes on one axis, as a box."""
    lo, hi = axis, axis + 2
    if a[lo] > b[lo]:
        a, b = b, a
    band = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
    band[lo], band[hi] = a[hi], b[lo]
    return tuple(band)


def join_over_blank(clusters, texts, size, reach=REACH_BLANK, prose=PROSE):
    """Join clusters whose gap holds no prose - one figure, drawn apart.

    THE UNDER-MERGE THIS FIXES. A four-panel figure is often set with a
    centimetre between its rows, which is past `GAP`, so clustering leaves it
    in pieces and the caption takes whichever piece is nearest: run2's
    comparison showed that happening to figures a person had already judged
    complete. What a reader uses to tell "two rows of one figure" from "two
    figures" is not the size of the gap but whether anything is WRITTEN in it.
    A caption between them stops the join, which is the case that matters.
    """
    w, h = size
    prose_lines = [t for t in texts if (t[2] - t[0]) > w * prose]
    band = gutter(texts, size)
    centre = (band[0] + band[1]) / 2.0 if band else None
    out = list(clusters)
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                axis = 1 if _gap(a, b, 1) >= _gap(a, b, 0) else 0
                if _gap(a, b, axis) > reach:
                    continue
                if overlap(a, b, 1 - axis) <= 0:
                    continue            # not lined up: side by side, not rows
                # 거터는 여기서도 벽입니다. 빈칸을 잇는 규칙이 그것을 모르면,
                # 두 단에 나란히 놓인 두 그림 사이에는 글이 없으므로 하나로
                # 붙어 버립니다 - 앞 단계에서 막은 것을 뒤 단계가 되돌립니다.
                if (centre is not None and axis == 0
                        and not (a[0] < centre < a[2] or b[0] < centre < b[2])
                        and min(a[2], b[2]) <= centre <= max(a[0], b[0])):
                    continue
                band = _between(a, b, axis)
                if any(overlap(band, t, 0) > (t[2] - t[0]) * 0.5
                       and overlap(band, t, 1) > (t[3] - t[1]) * 0.5
                       for t in prose_lines):
                    continue            # 사이에 글이 있으면 다른 그림이다
                out[i] = _box([a, b])
                del out[j]
                changed = True
                break
            if changed:
                break
    return sorted(out, key=lambda x: (-x[3], x[0]))


def score(cand, cap):
    """How well a candidate answers to a caption. Higher is better, <=0 is no.

    Two layouts count. A caption UNDER its figure is the common one in this
    literature; a caption BESIDE it happens in books and in landscape plates,
    and the walk this replaces could not see those at all - the region above
    such a caption is the previous paragraph.
    """
    if area(cand) < MIN_AREA * 3:
        return 0.0
    hov = overlap(cand, cap, 0) / max(1.0, min(cand[2] - cand[0],
                                               cap[2] - cap[0]))
    vov = overlap(cand, cap, 1) / max(1.0, min(cand[3] - cand[1],
                                               cap[3] - cap[1]))
    below = cand[1] - cap[3]            # candidate sits above the caption
    above = cap[1] - cand[3]            # candidate sits below the caption
    side = _gap(cand, cap, 0)
    best = 0.0
    if below >= -2.0 and hov > 0.35:
        best = max(best, hov - below / REACH)
    if above >= -2.0 and hov > 0.35:
        # A caption ABOVE its figure is real but rarer, so it starts behind.
        best = max(best, hov - above / REACH - 0.12)
    if vov > 0.35 and side < REACH:
        best = max(best, vov - side / REACH - 0.10)
    return max(0.0, best)


def assign(candidates, captions, margin=MARGIN):
    """Match a page's captions to its candidates, one to one.

    Returns a list the length of `captions`: `(index, code)` where index is
    into `candidates` or None. Codes are the reasons a person can act on:

        OK                 one candidate, clearly the best
        AMBIGUOUS          two candidates score within `margin`
        NO_CANDIDATE       nothing on the page answers to this caption
        TAKEN              its best candidate went to a caption that fit better
    """
    n, m = len(captions), len(candidates)
    table = [[score(candidates[j], captions[i]) for j in range(m)]
             for i in range(n)]
    out = [(None, "NO_CANDIDATE")] * n
    used = set()
    # Highest score first, so the pairing a page makes obvious is made first
    # and the leftovers are the ones that were never clear.
    order = sorted(((table[i][j], i, j) for i in range(n) for j in range(m)),
                   reverse=True)
    for value, i, j in order:
        if value <= 0 or j in used or out[i][0] is not None:
            continue
        if out[i][1] not in ("NO_CANDIDATE",):
            continue
        rivals = sorted((table[i][k] for k in range(m) if k not in used),
                        reverse=True)
        if len(rivals) > 1 and rivals[0] - rivals[1] < margin:
            out[i] = (None, "AMBIGUOUS")
            continue
        out[i] = (j, "OK")
        used.add(j)
    for i in range(n):
        if out[i][0] is None and out[i][1] == "NO_CANDIDATE":
            if any(table[i][j] > 0 for j in range(m)):
                out[i] = (None, "TAKEN")
    return out


# ------------------------------------------------------------------ the PDF

def page_objects(path, pageno, laparams=None):
    """(graphics, texts, (width, height)) for one page, in PDF points."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import (LTImage, LTCurve, LTLine, LTRect, LTFigure,
                                 LTTextLine, LTTextBox, LAParams)
    graphics, texts, size = [], [], (0.0, 0.0)
    for page in extract_pages(path, page_numbers=[pageno - 1],
                              laparams=laparams or LAParams()):
        size = (page.width, page.height)
        stack = list(page)
        while stack:
            el = stack.pop()
            # DESCEND INTO CONTAINERS. Text lines arrive inside text boxes and
            # drawings inside figures; a walk that only looks at the top level
            # of the page finds the drawings and none of the text, which is
            # exactly enough to detect no columns and split nothing.
            if isinstance(el, (LTFigure, LTTextBox)):
                stack.extend(list(el))
                continue
            if isinstance(el, (LTImage, LTCurve, LTLine, LTRect)):
                graphics.append(tuple(el.bbox))
            elif isinstance(el, LTTextLine):
                texts.append(tuple(el.bbox))
        break
    return graphics, texts, size


def regions(path, pageno, captions):
    """Validated regions for one page's captions, straight from the PDF.

    `captions` are caption boxes in PDF points, in the order the caller wants
    the answers back. Returns `[(box|None, code)]`.
    """
    graphics, texts, size = page_objects(path, pageno)
    cands = cluster(graphics, size, texts)
    return [(cands[j] if j is not None else None, code)
            for j, code in assign(cands, captions)]
