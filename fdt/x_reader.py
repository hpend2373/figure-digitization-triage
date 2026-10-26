"""Measure the x axis of a panel: tick marks, numeric tick labels, and bar centres.

Three independent measurements, and the CHECK is that two of them agree.

  TICK MARKS are geometry: short vertical runs of ink in a band just below the
  baseline. They need no OCR and no assumption about what the axis means.

  TICK LABELS are OCR, with column centres instead of rows. On a numeric x axis
  they must form the same kind of ladder the y axis has to form - monotone, with a
  constant value per pixel - and each label must sit over a tick mark. That second
  condition is the cross-check the y axis cannot have: geometry and OCR are
  measured separately here, so they can disagree, and a disagreement is a refusal.

  BAR CENTRES are geometry too: columns above the baseline that hold a tall run of
  ink, grouped into runs. This is the measurement `position_manifest.X_Pixel`
  actually needs for a bar panel, because for a bar chart x is not data - it is a
  label, and the reader is told where to sample.

Everything emitted is PROPOSED. Nothing here writes a confirmation.
"""
import numpy as np
import axis_reader as A

TICK_BAND = (2, 12)      # rows below the baseline that hold the tick marks
TICK_MAX_W = 6           # a tick mark wider than this is not a tick mark
LABEL_BAND = 46          # how far below the baseline the numerals can be
BAR_MIN_W = 6            # a bar narrower than this is a line, an axis or noise
BAR_MIN_H = 0.04         # a bar shorter than this fraction of the panel is noise
TICK_HIT = 0.6           # a label must sit within this fraction of a tick step


def _runs(mask, min_w=1):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_w:
                out.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_w:
        out.append((start, len(mask)))
    return out


def tick_marks(dark, box, spine_x, baseline_y):
    """[centre_column] for every short vertical run of ink under the baseline."""
    x0, x1, _y0, y1 = box
    r0 = int(baseline_y + TICK_BAND[0])
    r1 = int(min(dark.shape[0], baseline_y + TICK_BAND[1]))
    if r1 - r0 < 2:
        return []
    lo, hi = int(max(x0, spine_x - 2)), int(x1)
    band = dark[r0:r1, lo:hi]
    inked = band.any(axis=0) & (band.sum(axis=0) >= (r1 - r0) * 0.6)
    return [lo + (a + b - 1) / 2.0 for a, b in _runs(inked) if b - a <= TICK_MAX_W]


def x_tick_labels(img, dark, box, spine_x, baseline_y):
    """[(value, centre_column)] for numerals in the strip under the baseline."""
    x0, x1, _y0, _y1 = box
    top = int(baseline_y + 2)
    bottom = int(min(img.height, baseline_y + 2 + LABEL_BAND))
    if bottom - top < 20:
        return []
    left = int(max(0, x0 - 12))
    right = int(min(img.width, x1 + 12))
    strip = img.crop((left, top, right, bottom))
    scale = 3
    big = strip.resize((strip.width * scale, strip.height * scale), A.Image.LANCZOS)
    found = {}
    for psm in ("11", "6"):
        cfg = "--psm %s -c tessedit_char_whitelist=0123456789-." % psm
        try:
            d = A.pytesseract.image_to_data(big, config=cfg,
                                           output_type=A.pytesseract.Output.DICT)
        except Exception:
            continue
        for txt, l_, w_, conf in zip(d["text"], d["left"], d["width"], d["conf"]):
            s_ = (txt or "").strip()
            if not A.re.fullmatch(r"-?\d+(?:\.\d+)?", s_):
                continue
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = -1
            if c < 45:
                continue
            col = left + (l_ + w_ / 2.0) / scale
            key = round(col / 6)
            if key not in found or c > found[key][2]:
                found[key] = (float(s_), col, c)
    return sorted(((v, col) for v, col, _c in found.values()), key=lambda p: p[1])


def x_ladder(pairs):
    """(ok, detail, resid_px, cv) - values must RISE as the column rises."""
    if len(pairs) < A.MIN_LABELS:
        return False, "only %d numeric x label(s); %d needed" % (len(pairs), A.MIN_LABELS), None, None
    vals = [v for v, _ in pairs]
    cols = [c for _, c in pairs]
    if len(set(cols)) != len(cols):
        return False, "two labels share a column", None, None
    if not all(b > a for a, b in zip(vals, vals[1:])):
        return False, "x labels are not monotone: %s" % vals, None, None
    steps = [(vals[i + 1] - vals[i]) / (cols[i + 1] - cols[i]) for i in range(len(vals) - 1)]
    m = float(np.mean(steps))
    cv = float(np.std(steps) / abs(m)) if m else 1.0
    if cv > A.SPACING_CV:
        return False, "x value per pixel varies (cv %.3f)" % cv, None, cv
    b = float(np.mean(vals) - m * np.mean(cols))
    resid = float(max(abs((v - b) / m - c) for v, c in pairs))
    return True, "%d x labels, %.4g value/px, residual %.1f px" % (len(pairs), m, resid), resid, cv


def labels_over_ticks(pairs, ticks):
    """(ok, detail) - each numeric label must sit over a tick mark."""
    if not pairs or len(ticks) < 2:
        return False, "no tick marks to check the labels against"
    step = (max(ticks) - min(ticks)) / (len(ticks) - 1)
    miss = []
    for v, col in pairs:
        d = min(abs(col - t) for t in ticks)
        if d > TICK_HIT * step:
            miss.append("%g off by %.0f px" % (v, d))
    if miss:
        return False, "label(s) not over a tick: " + "; ".join(miss[:4])
    return True, "all %d labels sit over one of %d tick marks (step %.1f px)" % (
        len(pairs), len(ticks), step)


def bar_centres(dark, box, spine_x, baseline_y):
    """[(x0, centre, x1, height_px)] for column runs of ink standing on the baseline."""
    x0, x1, y0, _y1 = box
    lo, hi = int(spine_x + 3), int(x1 - 1)
    top = int(y0)
    bot = int(baseline_y - 2)
    if hi - lo < BAR_MIN_W or bot - top < 10:
        return []
    region = dark[top:bot, lo:hi]
    h = region.shape[0]
    # a bar column is inked at the baseline and stays inked upward
    col_h = np.zeros(region.shape[1])
    for j in range(region.shape[1]):
        v = region[:, j]
        run = 0
        for i in range(h - 1, -1, -1):
            if v[i]:
                run += 1
            else:
                break
        col_h[j] = run
    on = col_h >= max(3.0, BAR_MIN_H * h)
    out = []
    for a, b in _runs(on, BAR_MIN_W):
        out.append((lo + a, lo + (a + b - 1) / 2.0, lo + b - 1,
                    float(np.median(col_h[a:b]))))
    return out
