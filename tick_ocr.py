# -*- coding: utf-8 -*-
"""One OCR attempt per TICK, instead of one per label strip.

    TICKOCR=1 TRACE=trace.csv python3 propose.py

Publication 177's figure 2 row 4 is labelled 4, 3, 2, 1 - single digits - and the
strip reader returned one of the four. Nothing about that panel is wrong: its box
is right, its spine is the one free anchored candidate, its four tick marks are
found, and fourteen of its fifteen inked label columns are inside the box. The
reader was handed a 226 px strip and asked for every numeral in it, and single
glyphs at that size do not survive the question.

THE TICKS ARE ALREADY MEASURED, so the question can be asked one label at a time:
a crop centred on each tick row, at several magnifications, in the panel's own
greyscale and binarised at the figure's own ink threshold, with tesseract set to
read one line rather than to find text.

WHAT IT MAY NOT DO. It may not invent a digit. A row whose crops produced no
candidate stays empty, and the arithmetic progression is used ONLY to choose
among candidates that were actually read - never to fill a gap, never to correct
a value into the sequence. That distinction is the difference between reading an
axis and drawing one, and it is the guard with the most scenarios behind it.

The progression check is not new either: it is `axis_reader.ladder`, the same
monotone-and-constant-step test every ladder in this package has to pass. This
file chooses which read values to hand it; it does not relax it.

RECORDS ONLY. Nothing here writes into a panel's ticks, status or calibration.
"""
import itertools
import os

import numpy as np
from PIL import Image

import axis_reader as A
import gate_trace as T

ON = os.environ.get("TICKOCR", "0") != "0"

#: Magnifications tried per crop. A single glyph 11 px wide is the case this
#: exists for, and 3x - what the strip reader uses - is where it fails.
SCALES = (4, 6, 8)

#: How tesseract is asked. 7 is "one text line", 8 "one word", 10 "one
#: character": a label may be "100" or it may be "1", and which one it is is not
#: known before it is read.
PSMS = ("7", "8", "10")

#: The most candidates per tick row that are carried into the combination search.
#: A CAP ON WORK, not on the answer - how many were dropped is recorded, and they
#: are dropped lowest-confidence first.
MAX_CANDIDATES = 4

NO_CANDIDATE = "NO_CANDIDATE"
READ = "READ"
REFUSED = "REFUSED"


def crop_box(tick_rows, y, spine_x, side, dark_shape, reach=None):
    """The box one label occupies: centred on its tick, bounded by its neighbours.

    The half-height is HALF THE SMALLEST GAP between neighbouring ticks, measured
    on this axis, so a crop cannot reach the label above or below it. With one
    tick there is nothing to measure and the panel's own `LABEL_BAND_MAX` is the
    only bound left.
    """
    reach = A.LABEL_BAND_MAX if reach is None else int(reach)
    h, w = dark_shape
    gaps = [b - a for a, b in zip(sorted(tick_rows), sorted(tick_rows)[1:])]
    half = (min(gaps) // 2) if gaps else reach
    top, bottom = max(0, int(y) - half), min(h, int(y) + half + 1)
    if side == "LEFT":
        left, right = max(0, int(spine_x) - reach), max(0, int(spine_x))
    else:
        left, right = min(w, int(spine_x) + 1), min(w, int(spine_x) + 1 + reach)
    return (left, right, top, bottom)


def inks_for(ink):
    """The thresholds to binarise at: the pass's own, and the shipped default.

    THE PASS DID NOT CHOOSE ITS INK FOR READING. `REINK` re-cuts a figure that
    came up short of its declared axes at the grey the figure separates from its
    paper, which is a SEGMENTATION decision - and publication 177's figure 2 wins
    on PLAIN at 173, where its single-digit labels erode: at 173 the "2" of row 4
    reads nothing and the "1" reads 4, 7 or 5, and at the shipped 140 all four
    digits read. Both are already-measured numbers; neither is new.
    """
    out = [int(ink)]
    if int(ink) != int(A.INK_DEFAULT):
        out.append(int(A.INK_DEFAULT))
    return out


def renderings(img, box, ink):
    """(name, PIL image) per rendering tried: the greyscale crop, and the crop
    binarised at each threshold `inks_for` names - never at a fixed one."""
    left, right, top, bottom = box
    if right - left < 4 or bottom - top < 4:
        return []
    grey = img.convert("L").crop((left, top, right, bottom))
    arr = np.asarray(grey)
    out = [("grey", grey)]
    for t in inks_for(ink):
        out.append(("ink=%d" % t,
                    Image.fromarray(np.where(arr <= t, 0, 255).astype("uint8"))))
    return out


def read_box(img, box, ink, scales=SCALES, psms=PSMS):
    """[(value, text, conf, scale, rendering, psm)] for one label crop.

    Every attempt that produced a number is kept, not only the best one: two
    renderings disagreeing about a glyph is a fact about the glyph, and a row that
    records only its winner cannot show it.
    """
    try:
        import pytesseract
    except Exception:
        raise RuntimeError("tick-anchored OCR needs pytesseract, which the "
                           "locked environment does not install")
    out = []
    for name, im in renderings(img, box, ink):
        for sc in scales:
            big = im.resize((im.width * sc, im.height * sc), Image.LANCZOS)
            for psm in psms:
                cfg = ("--psm %s -c tessedit_char_whitelist=0123456789-." % psm)
                try:
                    d = pytesseract.image_to_data(
                        big, config=cfg, output_type=pytesseract.Output.DICT)
                except Exception:
                    continue
                for txt, conf in zip(d["text"], d["conf"]):
                    s = (txt or "").strip().replace("--", "-")
                    if not s:
                        continue
                    try:
                        v = float(s)
                    except ValueError:
                        continue
                    try:
                        c = float(conf)
                    except (TypeError, ValueError):
                        c = -1.0
                    out.append((v, s, c, sc, name, psm))
    return out


def best_per_value(cands):
    """One entry per distinct VALUE, keeping its best confidence.

    Twelve attempts agreeing on 3 are one candidate, not twelve, and the count
    that matters downstream is how many DIFFERENT numbers the crop could be.
    """
    best = {}
    for v, s, c, sc, name, psm in cands:
        if v not in best or c > best[v][2]:
            best[v] = (v, s, c, sc, name, psm)
    return sorted(best.values(), key=lambda t: -t[2])


def choose(rows, per_row):
    """(pairs, detail) - the read values that form a ladder, or ([], why not).

    `per_row` maps a tick row to the candidate values READ THERE. Every
    combination takes one candidate from each row that has any, and the winner is
    the one `axis_reader.ladder` accepts. A row with no candidate contributes
    NOTHING: it is not filled from the progression, and if too few rows read then
    the answer is a refusal with the count in it.

    Ties are refused, not broken. Two different combinations that both form a
    ladder mean the axis is not determined by what was read, and picking one
    would be inventing the difference.
    """
    usable = [(r, per_row[r]) for r in rows if per_row.get(r)]
    if len(usable) < A.MIN_LABELS:
        return [], ("only %d of %d tick rows produced a candidate; %d needed"
                    % (len(usable), len(rows), A.MIN_LABELS))
    winners = []
    for combo in itertools.product(*[[(v, r) for v in vals] for r, vals in usable]):
        pairs = sorted(combo, key=lambda p: p[1])
        ok = A.ladder(pairs, allow_subset=False)[0]
        if ok:
            winners.append(pairs)
    if not winners:
        return [], "no combination of the values read forms a ladder"
    distinct = {tuple(p) for p in winners}
    if len(distinct) > 1:
        return [], ("%d different combinations of the values read form a ladder, "
                    "so the axis is not determined by what was read"
                    % len(distinct))
    return winners[0], "one combination of the read values forms a ladder"


def record(img, dark, label, box, spine_x, side, run, ticks, ink=None):
    """One TICK_OCR row per tick, one TICK_OCR_LADDER row for the panel.

    RECORDS ONLY; never handed the proposal list, and the scenario asserts that
    from the signature.
    """
    if not (ON and T.ON):
        return None
    ink = A.INK if ink is None else ink
    per_row, n_dropped = {}, 0
    for y in ticks:
        cb = crop_box(ticks, y, spine_x, side, dark.shape)
        try:
            cands = best_per_value(read_box(img, cb, ink))
        except Exception as exc:
            T.add("TICK_OCR", panel=label, tick_row=y, box=T.box(cb),
                  outcome="FAILED", detail="%s: %s" % (type(exc).__name__, exc))
            continue
        keep = cands[:MAX_CANDIDATES]
        n_dropped += len(cands) - len(keep)
        per_row[y] = [v for v, _s, _c, _sc, _n, _p in keep]
        T.add("TICK_OCR", panel=label, tick_row=y, box=T.box(cb),
              outcome=(READ if keep else NO_CANDIDATE),
              n_candidates=len(cands), n_kept=len(keep),
              candidates=";".join("%g@%.0f/%dx/%s/psm%s" % (v, c, sc, n, p)
                                  for v, _s, c, sc, n, p in keep))
    pairs, detail = choose(list(ticks), per_row)
    T.add("TICK_OCR_LADDER", panel=label, box=T.box(box),
          n_ticks=len(ticks),
          n_rows_read=sum(1 for y in ticks if per_row.get(y)),
          n_candidates_dropped=n_dropped,
          outcome=(READ if pairs else REFUSED),
          ticks=";".join("%g:%g" % (v, r) for v, r in pairs),
          detail=detail)
    return pairs or None
