# -*- coding: utf-8 -*-
"""The caption belongs to the FIGURE. No panel contains it."""
import re
import numpy as np

RULE_LEN, CAP_SPAN, CAP_DENS, CAP_WORDS = 40, 0.60, 0.55, 8
CAP_HEAD = re.compile(r'^\W{0,3}(fig|figure|fjg|abb|table|tab)\b', re.I)


def _longest_run(v):
    best = cur = 0
    for x in v:
        cur = cur + 1 if x else 0
        if cur > best:
            best = cur
    return best


def structure_floor(dark, rule_len=RULE_LEN):
    """The last row that belongs to a drawn structure rather than to text.

    Both directions matter. Taking only the horizontal rules puts the floor at the
    lowest x axis, but a summary panel whose spine runs 200 px BELOW its own zero
    line would then have everything under that line look like caption.
    """
    h, w = dark.shape
    rows = np.zeros(h, dtype=bool)
    for y in range(h):
        if _longest_run(dark[y]) >= rule_len:
            rows[y] = True
    for x in range(w):
        col = dark[:, x]
        if not col.any():
            continue
        s = None
        for y in range(h):
            if col[y] and s is None:
                s = y
            elif not col[y] and s is not None:
                if y - s >= rule_len:
                    rows[s:y] = True
                s = None
        if s is not None and h - s >= rule_len:
            rows[s:h] = True
    idx = np.where(rows)[0]
    return int(idx[-1]) if len(idx) else -1


def text_bands(dark, rule_len=RULE_LEN):
    h = dark.shape[0]
    ink = dark.any(axis=1)
    isrule = np.array([_longest_run(dark[y]) >= rule_len for y in range(h)])
    out, s = [], None
    for y in range(h):
        ok = ink[y] and not isrule[y]
        if ok and s is None:
            s = y
        elif not ok and s is not None:
            out.append((s, y)); s = None
    if s is not None:
        out.append((s, h))
    return out


def band_shape(dark, a, b):
    cols = dark[a:b].any(axis=0)
    idx = np.where(cols)[0]
    if len(idx) == 0:
        return 0.0, 0.0, (0, 0)
    span = (idx[-1] - idx[0] + 1) / dark.shape[1]
    dens = float(cols[idx[0]:idx[-1] + 1].mean())
    return span, dens, (int(idx[0]), int(idx[-1]))


def read(img, a, b, x0, x1, scale=3):
    import pytesseract
    from PIL import Image
    crop = img.crop((max(0, x0 - 4), max(0, a - 3), min(img.width, x1 + 5),
                     min(img.height, b + 3))).convert("L")
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    try:
        return " ".join(pytesseract.image_to_string(crop, config="--psm 7").split())
    except Exception:
        return ""


def caption_band(img, dark):
    """(top_row, text) of the caption inside this clip, or None.

    The structural test proposes and the READING disposes: trimming a panel is
    destructive, so the evidence has to be positive, not merely consistent.
    """
    floor = structure_floor(dark)
    best = None
    for a, b in text_bands(dark):
        if a <= floor or b - a < 6:
            continue
        span, dens, (x0, x1) = band_shape(dark, a, b)
        if span < CAP_SPAN or dens < CAP_DENS:
            continue
        txt = read(img, a, b, x0, x1)
        if CAP_HEAD.match(txt) or len(txt.split()) >= CAP_WORDS:
            if best is None or a < best[0]:
                best = (a, txt)
    return best


PANEL_TOKENS = re.compile(r'\(([A-Ha-h])\)|(?:^|[\s;,])([A-H])[\)\.:]\s')
RANGE = re.compile(r'\(?([A-Ha-h])\)?\s*[-–—]\s*\(?([A-Ha-h])\)?')


def caption_panels(text):
    """The panel names the caption itself enumerates, in the order it names them."""
    if not text:
        return []
    seen, out = set(), []
    for m in RANGE.finditer(text):
        a, b = m.group(1), m.group(2)
        if a.isalpha() and b.isalpha() and a.islower() == b.islower() and ord(b) - ord(a) in range(1, 8):
            for c in range(ord(a), ord(b) + 1):
                if chr(c) not in seen:
                    seen.add(chr(c)); out.append(chr(c))
    for m in PANEL_TOKENS.finditer(text):
        ch = m.group(1) or m.group(2)
        if ch and ch not in seen:
            seen.add(ch); out.append(ch)
    return out
