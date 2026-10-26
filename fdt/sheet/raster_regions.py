# -*- coding: utf-8 -*-
"""Figure candidates from the page RASTER - ink, not objects.

WHY A THIRD PROPOSER. `figure_bbox` walks text blocks; `figure_regions`
clusters the drawings a PDF declares. Both are blind on a scanned book, where
the PDF declares one image per page and no text worth walking - pid 437 in
run2 is 374 such pages. Ink on the rendered page is the one signal every
document has, so this proposer looks only at pixels.

WHAT IT DOES. The page raster is thresholded to an ink mask. Prose lines -
text lines the PDF's own text layer places, at least PROSE of the page wide -
are painted out, because a paragraph is the one thing that must never become
a candidate. The mask is downsampled by CELL, closed with a small dilation so
the pieces of one drawing touch, and labelled into connected components. A
component wide and tall enough is a candidate; the rest (tick labels left
over from a figure, bullets, stray marks) is not.

COORDINATES. Everything here is in the RASTER's convention - y down from the
top - until the last line of `candidates`, which hands back PDF points with y
up from the bottom, so `figure_regions.assign` can score them against
captions exactly as it scores the object clusters. One conversion, in one
place, named.
"""
import numpy as np


#: Grey level below which a pixel is ink. Same as the intake's `_INK_LEVEL`.
INK = 235
#: Downsampling factor for the component analysis. A 200 dpi page is ~1700 x
#: 2200; at CELL=6 that is ~280 x 370 cells, which pure-Python labelling walks
#: in well under a second and which still resolves a 12pt tick label.
CELL = 6
#: Dilation radius in cells before labelling. Two cells (~12px, ~4pt) joins the
#: pieces of one axis; it does not join two panels a centimetre apart - that
#: is `join_over_blank`'s job, applied to the result.
CLOSE = 2
#: Text lines this fraction of the page wide (or wider) are prose and are
#: painted out before labelling. Same threshold as `figure_regions.PROSE`.
PROSE = 0.20
#: Header and footer bands, as a fraction of page height, painted out. The
#: running head and folio are ink on every page and belong to no figure.
BAND = 0.045
#: Smallest candidate, in points, on either side.
MIN_SIDE_PT = 30.0


def ink_mask(page_grey):
    """Boolean ink mask from a greyscale page (numpy array)."""
    return page_grey < INK


def paint_out_prose(mask, texts_top_origin_px, page_w_px, band=BAND):
    """Remove prose lines and the header/footer bands from the mask, in place."""
    h, w = mask.shape
    for x0, y0, x1, y1 in texts_top_origin_px:
        if (x1 - x0) >= page_w_px * PROSE:
            # WITH ROOM. A text line's box from the PDF hugs the glyph bodies;
            # ascenders and descenders poke out of it, survive the painting,
            # and after dilation come back as "drawings" a paragraph tall.
            # Half a line above and below, and a little to each side, takes
            # the whole line out - and cannot reach a figure, which sits at
            # least a caption's height away.
            m = 0.5 * (y1 - y0)
            mask[max(0, int(y0 - m)):min(h, int(y1 + m) + 1),
                 max(0, int(x0 - 0.01 * w)):min(w, int(x1 + 0.01 * w) + 1)] = False
    b = int(h * band)
    mask[:b, :] = False
    mask[h - b:, :] = False
    return mask


def downsample(mask, cell=CELL):
    h, w = mask.shape
    H, W = (h + cell - 1) // cell, (w + cell - 1) // cell
    padded = np.zeros((H * cell, W * cell), dtype=bool)
    padded[:h, :w] = mask
    return padded.reshape(H, cell, W, cell).any(axis=(1, 3))


def dilate(grid, r=CLOSE):
    out = grid.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.zeros_like(grid)
            ys, ye = max(0, dy), grid.shape[0] + min(0, dy)
            xs, xe = max(0, dx), grid.shape[1] + min(0, dx)
            shifted[ys:ye, xs:xe] = grid[ys - dy:ye - dy, xs - dx:xe - dx]
            out |= shifted
    return out


def components(grid):
    """Bounding boxes (x0, y0, x1, y1) in cells of the grid's 4-connected blobs.

    Two-pass labelling with union-find, in Python, over a grid a few hundred
    cells a side. Written out rather than imported because scipy is not a
    dependency this bundle has, and a few hundred thousand cells is nothing.
    """
    H, W = grid.shape
    labels = np.zeros((H, W), dtype=np.int32)
    parent = [0]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    nxt = 1
    g = grid.tolist()
    lab = labels.tolist()
    for y in range(H):
        row, prev = g[y], (lab[y - 1] if y else None)
        cur = lab[y]
        for x in range(W):
            if not row[x]:
                continue
            left = cur[x - 1] if x else 0
            up = prev[x] if prev is not None else 0
            if left and up:
                cur[x] = left
                union(left, up)
            elif left or up:
                cur[x] = left or up
            else:
                parent.append(nxt)
                cur[x] = nxt
                nxt += 1
    boxes = {}
    for y in range(H):
        cur = lab[y]
        for x in range(W):
            v = cur[x]
            if not v:
                continue
            r = find(v)
            b = boxes.get(r)
            if b is None:
                boxes[r] = [x, y, x + 1, y + 1]
            else:
                if x < b[0]:
                    b[0] = x
                if x + 1 > b[2]:
                    b[2] = x + 1
                if y + 1 > b[3]:
                    b[3] = y + 1
    return [tuple(b) for b in boxes.values()]


def candidates(page_grey, texts_pdf_pts, page_pts, cell=CELL):
    """Candidate boxes in PDF points (y up), from one page's raster.

    `page_grey` is the raster as a 2-D numpy array; `texts_pdf_pts` are the
    PDF's text-line boxes in PDF points (y up), as `figure_regions.page_objects`
    returns them; `page_pts` is (width, height) in points.
    """
    import figure_regions as FR
    h, w = page_grey.shape
    pw, ph = page_pts
    sx, sy = w / pw, h / ph
    # Text lines arrive y-up in points; the mask is y-down in pixels.
    texts_px = [(x0 * sx, (ph - y1) * sy, x1 * sx, (ph - y0) * sy)
                for x0, y0, x1, y1 in texts_pdf_pts]
    mask = paint_out_prose(ink_mask(page_grey), texts_px, w)
    grid = dilate(downsample(mask, cell))
    out = []
    for cx0, cy0, cx1, cy1 in components(grid):
        # Undo the dilation: it widened every component by CLOSE cells on each
        # side so that the pieces would touch, and a candidate should hug the
        # ink, not the halo. Clamped, because a blob at the page edge was not
        # widened past it.
        cx0, cy0 = min(cx0 + CLOSE, cx1 - 1), min(cy0 + CLOSE, cy1 - 1)
        cx1, cy1 = max(cx1 - CLOSE, cx0 + 1), max(cy1 - CLOSE, cy0 + 1)
        px0, py0 = cx0 * cell, cy0 * cell
        px1, py1 = min(w, cx1 * cell), min(h, cy1 * cell)
        # back to points, and back to y-up, in one expression
        box = (px0 / sx, ph - py1 / sy, px1 / sx, ph - py0 / sy)
        if (box[2] - box[0]) >= MIN_SIDE_PT and (box[3] - box[1]) >= MIN_SIDE_PT:
            out.append(box)
    # The same "blank between, no prose" joining the object clusters get, so a
    # two-row figure is one candidate here too - and the same gutter rule.
    return FR.join_over_blank(out, texts_pdf_pts, page_pts)


def regions(page_grey, texts_pdf_pts, page_pts, captions_pdf_pts):
    """[(box|None, code)] for each caption, boxes in PDF points (y up)."""
    import figure_regions as FR
    cands = candidates(page_grey, texts_pdf_pts, page_pts)
    return [(cands[j] if j is not None else None, code)
            for j, code in FR.assign(cands, captions_pdf_pts)]
