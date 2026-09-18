# -*- coding: utf-8 -*-
"""What a confirmed frame still does not say: WHICH marks, WHERE on x, and WHAT.

    python3 identity_proposer.py RASTER --geometry geometry_decisions.csv \
        --out DIR [--caption "..."]

A geometry a person confirmed gives the reader a frame and a y calibration.
Reading a value off a mark also needs three things nobody has written yet:

    the x POSITIONS and what each one is called   (positions)
    the SERIES - which ink is which group           (series)
    the OUTCOME and its UNIT - the y axis title     (unit)

and, for the unit, the sample size the caption prints. Every one of these was
typed by hand for the three pilot publications. At 942 panels that is not a
plan, it is the transcription error the plan exists to prevent, so this module
READS each of them off the raster and proposes it - under the same rule as the
y-axis reader: read, check the reading against something it did not produce,
and refuse rather than guess.

    x labels     each label must sit over an anchor the frame measured (a bar
                 centre or a group column); an anchor with no label, or a label
                 with no anchor, refuses the set
    series       the legend's swatch colours must be the colours found in the
                 plot, one each; a legend the plot does not contain, or ink
                 the legend does not name, refuses the set
    y title      the strip left of the numerals, rotated; refused when
                 tesseract reads nothing or the words are not words
    n            the caption's "n = 8"; refused when the caption prints
                 several different n

Everything here is PROPOSED. `identity_page.py` puts it in front of a person
and `record_identity.py` writes what the person confirmed. Nothing in this
module writes a factor name, a level or a unit into a plan.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import axis_reader as A                                          # noqa: E402
import geometry_proposer as GP                                   # noqa: E402
import x_reader as XR                                            # noqa: E402

PROPOSALS = "identity_proposal.csv"

#: One row per panel. The machine's columns come first; the person's, after
#: `Human_Verification_Status`, are written by `record_identity.py` and by
#: nothing else.
IDENTITY_COLUMNS = (
    "Proposal_ID", "Raster", "Raster_SHA256", "Region",
    "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1", "Spine_X",
    "Panel_Kind",
    # x: the anchors the frame measured and the label read over each one.
    "X_Anchor_Pixels", "X_Anchor_Count", "X_Anchor_Source",
    "X_Label_Read_Status", "X_Labels_Read", "X_Label_Detail", "X_Numeric",
    # series: the chromatic ink in the plot, and the legend entries read
    # beside a swatch of each colour.
    "Series_Colours", "Series_Colour_Count",
    "Series_Read_Status", "Series_Read", "Series_Detail",
    "Mark_Type_Proposed",
    # unit: the y title, split into outcome and unit where it prints one.
    "Y_Title_Read_Status", "Y_Title_Read", "Outcome_Read", "Unit_Read",
    "Y_Title_Detail",
    # n from the caption.
    "N_Read_Status", "N_Read", "N_Detail",
    # the person's columns
    "Human_Verification_Status", "Verified_By", "Verified_At",
    "X_Factor", "X_Labels", "Series_Factor", "Series", "Mark_Type",
    "Outcome_Name", "Unit", "N_Outcome", "Bar_Top_Definition",
    "Errorbar_Stem_Confirmed", "Note",
)

READ_OK, READ_REFUSED, READ_NOT_ATTEMPTED = GP.READ_OK, GP.READ_REFUSED, GP.READ_NOT_ATTEMPTED

PENDING = "PENDING"
STATUSES = (PENDING, "CONFIRMED", "REJECTED")

#: The panel kinds intake counted, and the mark types the plan can dispatch
#: for each. Which of the two a colour-or-mono kind is, the plot's own ink
#: says (`Mark_Type_Proposed`), and the person confirms.
PANEL_KINDS = ("BAR", "LINE", "SCATTER", "BOX")
MARK_TYPES_FOR = {
    "BAR": ("BAR_COLOR", "BAR_MONO"),
    "LINE": ("LINE_COLOR", "LINE_MONO"),
    "SCATTER": ("SCATTER",),
    "BOX": ("BOX_VIOLIN",),
}

#: A label must sit within this fraction of the anchor pitch of its anchor.
LABEL_HIT = 0.5
#: tesseract's word confidence below which a word is noise.
WORD_CONF = 55
#: Chromatic ink: saturation above this (0..1) is a colour, below is grey.
SATURATION = 0.28
#: A colour cluster smaller than this share of the plot's chromatic pixels is
#: an antialiasing fringe, not a series.
COLOUR_SHARE = 0.04
#: Two hues closer than this many degrees are one colour.
HUE_MERGE = 22.0
#: A legend swatch is looked for this many text-heights left of the entry.
SWATCH_REACH = 3.0


def _s(v):
    return str(v or "").strip()


def _dark(gray, threshold=A.INK):
    return np.asarray(gray) < threshold


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- x labels

def _words(img, box, scale=3, psm="11", whitelist=None):
    """[(text, x_centre, y_centre, conf, height)] tesseract reads in `box`,
    in raster coordinates."""
    if A.pytesseract is None:
        raise RuntimeError("reading a label needs pytesseract")
    left, top, right, bottom = [int(v) for v in box]
    left, top = max(0, left), max(0, top)
    right, bottom = min(img.width, right), min(img.height, bottom)
    if right - left < 8 or bottom - top < 8:
        return []
    strip = img.crop((left, top, right, bottom)).convert("L")
    pad = 8
    padded = Image.new("L", (strip.width + 2 * pad, strip.height + 2 * pad), 255)
    padded.paste(strip, (pad, pad))
    big = padded.resize((padded.width * scale, padded.height * scale), Image.LANCZOS)
    cfg = "--psm %s" % psm
    if whitelist:
        cfg += " -c tessedit_char_whitelist=%s" % whitelist
    try:
        d = A.pytesseract.image_to_data(big, config=cfg,
                                        output_type=A.pytesseract.Output.DICT)
    except Exception:
        return []
    out = []
    for txt, l_, t_, w_, h_, conf in zip(d["text"], d["left"], d["top"],
                                         d["width"], d["height"], d["conf"]):
        s = (txt or "").strip()
        if not s:
            continue
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1
        if c < WORD_CONF:
            continue
        x = left + (l_ + w_ / 2.0) / scale - pad
        y = top + (t_ + h_ / 2.0) / scale - pad
        out.append((s, x, y, c, h_ / float(scale), w_ / float(scale)))
    return out


def _is_word(text):
    """A token with a letter or a digit in it. tesseract also returns the
    punctuation it makes of tick marks and rules."""
    return re.search(r"[A-Za-z0-9]", text) is not None


def anchors_of(row):
    """The x anchors a geometry row measured: the box (mark) anchors when it
    found any, else the group anchors. (pixels, source)."""
    boxes = [float(v) for v in _s(row.get("Box_Anchor_Pixels")).split(";") if v]
    if boxes:
        return boxes, "BOX"
    groups = [float(v) for v in _s(row.get("Group_Anchor_Pixels")).split(";") if v]
    if groups:
        return groups, "GROUP"
    return [], ""


def measure_anchors(gray, frame):
    """Anchors measured afresh on `frame` - for a frame a person drew, which
    carries no measurement of its own."""
    boxes, _why = GP.find_box_anchors(gray, frame)
    if boxes:
        return [float(b) for b in boxes], "BOX"
    groups = GP.find_group_anchors(gray, frame)
    return [float(a) for a in groups], ("GROUP" if groups else "")


#: Categorical x labels stand at one pitch; a set whose gaps vary more than
#: this (coefficient of variation) is not one row of labels.
LABEL_PITCH_CV = 0.12
#: Words closer than this many text heights are one label ("D1 evening").
#: A word space is a third of a text height; the gap between two one-word
#: labels on publication S41467-023-41990-4's figure 2b is 1.1 heights.
LABEL_JOIN = 0.7


def label_strip(img, frame, region=None):
    """(top, bottom) of the strip under the baseline the labels are read in."""
    x0, x1, y0, y1 = [int(v) for v in frame]
    # The region is intake's crop and can stop at the baseline; the labels
    # under it are still this panel's, so the strip may reach a little past
    # the region - not far enough to read the next panel's title.
    ry1 = int(region[3]) + int(0.12 * (y1 - y0)) if region else img.height
    reach = max(4, min(14, (y1 - y0) // 30))
    top = y1 + reach + 2
    bottom = min(img.height, ry1, y1 + max(24, int(0.22 * (y1 - y0))))
    return top, bottom


def group_labels(words):
    """[(text, x_centre)] - words in one row, joined where they nearly touch.

    Words on one row are sorted by x; a gap wider than `LABEL_JOIN` text
    heights starts the next label. A label's position is the centre of its
    ink, first word to last.
    """
    if not words:
        return []
    rows = []
    for w in sorted(words, key=lambda w: (w[2], w[1])):
        for row in rows:
            if abs(row["y"] - w[2]) <= max(4, 0.6 * row["h"]):
                row["words"].append(w)
                break
        else:
            rows.append({"y": w[2], "h": w[4], "words": [w]})
    # the row with the most words is the label row; a second row is a
    # rotated or two-line label this reader does not read
    row = max(rows, key=lambda r: len(r["words"]))
    ws = sorted(row["words"], key=lambda w: w[1])
    labels, cur = [], [ws[0]]
    for prev, w in zip(ws, ws[1:]):
        gap = (w[1] - w[5] / 2.0) - (prev[1] + prev[5] / 2.0)
        if gap > LABEL_JOIN * max(row["h"], 1):
            labels.append(cur)
            cur = []
        cur.append(w)
    labels.append(cur)
    out = []
    for group in labels:
        left = group[0][1] - group[0][5] / 2.0
        right = group[-1][1] + group[-1][5] / 2.0
        out.append((" ".join(w[0] for w in group), (left + right) / 2.0))
    return out


def anchor_agreement(labels, anchors):
    """How the frame's measured anchors stand to the labels: AGREE when there
    is one anchor within half a pitch of each label and no other; DISAGREE
    otherwise; NO_ANCHORS when the frame measured none. A report, not a gate -
    the anchors are a heuristic of their own, wrong on a line-and-bar panel."""
    if not anchors:
        return "NO_ANCHORS"
    if len(anchors) != len(labels):
        return "DISAGREE"
    pitch = _pitch([px for _t, px in labels]) or 1.0
    for _t, px in labels:
        if min(abs(px - a) for a in anchors) > LABEL_HIT * pitch:
            return "DISAGREE"
    return "AGREE"


def _pitch(positions):
    if len(positions) < 2:
        return None
    ps = sorted(positions)
    return (ps[-1] - ps[0]) / (len(ps) - 1)


def read_x_labels(img, dark, frame, anchors, region=None):
    """(status, [(label, px)], detail, numeric).

    The strip under the baseline is read as words, the words are joined into
    labels, and the labels are the proposed positions. The check they have to
    pass is one they did not produce: a categorical axis prints its labels at
    ONE pitch, so gaps that vary refuse the set; a numeric axis has to form the
    same ladder the y axis forms. The anchors the frame measured are compared
    afterwards and reported, not obeyed - on publication S41467-023-41990-4's
    figure 3a they were two spurious bars at the far right.
    """
    x0, x1, y0, y1 = [int(v) for v in frame]
    top, bottom = label_strip(img, frame, region)
    if bottom - top < 12:
        return READ_REFUSED, [], "no room under the baseline for labels", False
    words = [w for w in _words(img, (max(0, x0 - 8), top, min(img.width, x1 + 8), bottom))
             if _is_word(w[0])]
    if not words:
        return READ_REFUSED, [], "tesseract read no word under the baseline", False
    labels = group_labels(words)
    texts = [t for t, _px in labels]
    if len(set(texts)) != len(texts):
        dup = sorted(set(t for t in texts if texts.count(t) > 1))
        return READ_REFUSED, [], "the same label reads twice: %s" % ", ".join(
            repr(t) for t in dup[:4]), False
    numeric = all(re.fullmatch(r"-?\d+(?:\.\d+)?", t) for t in texts)
    if numeric and len(labels) >= 3:
        ok, why, _r, _cv = XR.x_ladder([(float(t), px) for t, px in labels])
        if not ok:
            return READ_REFUSED, [], "numeric x labels do not form a ladder: %s" % why, True
    elif len(labels) >= 3:
        gaps = [b - a for a, b in zip([px for _t, px in labels], [px for _t, px in labels][1:])]
        cv = float(np.std(gaps) / np.mean(gaps)) if np.mean(gaps) else 1.0
        if cv > LABEL_PITCH_CV:
            return READ_REFUSED, [], "labels are not at one pitch (gap cv %.2f: %s)" % (
                cv, ", ".join("%.0f" % g for g in gaps[:6])), False
    agree = anchor_agreement(labels, anchors)
    return READ_OK, labels, "%d labels%s; frame anchors %s" % (
        len(labels), " (numeric ladder)" if numeric else "", agree.lower()), numeric


# ------------------------------------------------------------------ series

def _hsv(rgb):
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    mx = arr.max(axis=-1)
    mn = arr.min(axis=-1)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-9), 0.0)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    hue = np.zeros_like(mx)
    nz = delta > 1e-9
    rmax = nz & (mx == r)
    gmax = nz & (mx == g) & ~rmax
    bmax = nz & ~rmax & ~gmax
    hue[rmax] = (60.0 * ((g - b)[rmax] / delta[rmax])) % 360
    hue[gmax] = 60.0 * ((b - r)[gmax] / delta[gmax]) + 120
    hue[bmax] = 60.0 * ((r - g)[bmax] / delta[bmax]) + 240
    return hue, sat, mx


def _hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def plot_colours(rgb, frame, inset=0.02):
    """[(hue, share, (r, g, b))] - the chromatic colours inside the frame,
    largest share first. Grey ink is not a colour."""
    x0, x1, y0, y1 = [int(v) for v in frame]
    dx, dy = int((x1 - x0) * inset), int((y1 - y0) * inset)
    patch = np.asarray(rgb)[y0 + dy:y1 - dy, x0 + dx:x1 - dx, :3]
    if patch.size == 0:
        return []
    hue, sat, val = _hsv(patch)
    chroma = (sat > SATURATION) & (val > 0.15)
    n = int(chroma.sum())
    if n < 30:
        return []
    hues = hue[chroma]
    hist, edges = np.histogram(hues, bins=72, range=(0, 360))
    peaks = []
    for i in range(72):
        if hist[i] < max(3, COLOUR_SHARE * n / 3.0):
            continue
        if hist[i] >= hist[(i - 1) % 72] and hist[i] >= hist[(i + 1) % 72]:
            peaks.append((i * 5.0 + 2.5, int(hist[i])))
    clusters = []
    for centre, _h in sorted(peaks, key=lambda p: -p[1]):
        if any(_hue_dist(centre, c) < HUE_MERGE for c, _s, _rgb in clusters):
            continue
        near = np.array([_hue_dist(h, centre) < HUE_MERGE for h in hues])
        share = float(near.sum()) / n
        if share < COLOUR_SHARE:
            continue
        pix = patch[chroma][near]
        med = tuple(int(v) for v in np.median(pix, axis=0))
        clusters.append((centre, share, med))
    return sorted(clusters, key=lambda c: -c[1])


def _swatch_colour(rgb, x_right, y, h, reach):
    """The chromatic colour just left of a text entry, or None."""
    left = max(0, int(x_right - reach))
    top, bottom = max(0, int(y - h * 0.6)), min(rgb.shape[0], int(y + h * 0.6))
    patch = rgb[top:bottom, left:int(x_right), :3]
    if patch.size == 0:
        return None
    hue, sat, val = _hsv(patch)
    chroma = (sat > SATURATION) & (val > 0.15)
    if chroma.sum() < 6:
        return None
    hues = hue[chroma]
    hist, _e = np.histogram(hues, bins=72, range=(0, 360))
    centre = int(np.argmax(hist)) * 5.0 + 2.5
    near = np.array([_hue_dist(hh, centre) < HUE_MERGE for hh in hues])
    med = tuple(int(v) for v in np.median(patch[chroma][near], axis=0))
    return centre, med


def read_legend(img, rgb, frame, region, colours):
    """(status, [(text, (r,g,b))], detail).

    Legend entries are words with a chromatic swatch just left of them, read
    anywhere in the panel's region but the label bands. Each swatch colour is
    matched to one plot colour, and the check is both ways: every plot colour
    named once, every entry naming a plot colour.
    """
    if not colours:
        return READ_REFUSED, [], "no chromatic ink in the plot; series are not told apart by colour"
    rx0, ry0, rx1, ry1 = [int(v) for v in region]
    x0, x1, y0, y1 = [int(v) for v in frame]
    words = _words(img, (rx0, ry0, rx1, ry1), scale=2, psm="11")
    words = [w for w in words if re.search(r"[A-Za-z]{2}", w[0])]
    if not words:
        if len(colours) == 1:
            # One colour and nothing to name it: one series, unnamed. The
            # person names it or leaves it as the panel's own.
            return READ_OK, [("", colours[0][2])], "one plot colour and no legend: one series"
        return READ_REFUSED, [], "no legend words read in the panel"
    # group words into lines (same y within half a text height), in x order
    lines = []
    for w in sorted(words, key=lambda w: (w[2], w[1])):
        for line in lines:
            if abs(line["y"] - w[2]) <= max(4, 0.6 * line["h"]):
                line["words"].append(w)
                break
        else:
            lines.append({"y": w[2], "h": w[4], "words": [w]})
    arr = np.asarray(rgb)
    entries = []
    for line in lines:
        ws = sorted(line["words"], key=lambda w: w[1])
        # a line may hold several entries (horizontal legend): split where a
        # swatch stands between two words
        groups, cur = [], []
        for w in ws:
            if cur and _swatch_colour(arr, w[1] - w[5] / 2.0 - 2, w[2], line["h"],
                                      SWATCH_REACH * line["h"]):
                groups.append(cur)
                cur = []
            cur.append(w)
        if cur:
            groups.append(cur)
        for g in groups:
            first = g[0]
            x_left = first[1] - first[5] / 2.0
            sw = _swatch_colour(arr, x_left - 2, first[2], line["h"], SWATCH_REACH * line["h"])
            if sw is None:
                continue
            text = " ".join(w[0] for w in g)
            entries.append((text, sw[0], sw[1]))
    if not entries:
        if len(colours) == 1:
            return READ_OK, [("", colours[0][2])], "one plot colour and no legend entry: one series"
        return READ_REFUSED, [], "words were read but none has a colour swatch beside it"
    matched, used = [], set()
    for text, hue, med in entries:
        k = min(range(len(colours)), key=lambda i: _hue_dist(colours[i][0], hue))
        if _hue_dist(colours[k][0], hue) > HUE_MERGE:
            return READ_REFUSED, [], "legend entry %r has a colour the plot does not contain" % text
        if k in used:
            return READ_REFUSED, [], "two legend entries name the same plot colour: %r" % text
        used.add(k)
        matched.append((text, colours[k][2]))
    unnamed = [i for i in range(len(colours)) if i not in used]
    if unnamed:
        return READ_REFUSED, [], "plot colour(s) %s named by no legend entry" % ", ".join(
            "rgb%s" % (colours[i][2],) for i in unnamed)
    return READ_OK, matched, "%d legend entries, one per plot colour" % len(matched)


# ----------------------------------------------------------------- y title

def read_y_title(img, dark, frame, spine_x, region):
    """(status, title, outcome, unit, detail) - the rotated strip left of the
    numerals."""
    x0, x1, y0, y1 = [int(v) for v in frame]
    rx0 = int(region[0])
    reach = A.tick_reach(dark, int(spine_x), y0, y1, cap=max(10, (y1 - y0) // 8))
    band = A.label_band(dark, (int(spine_x), x1, y0, y1), int(spine_x) - reach, y0, y1,
                        band_max=A.band_max_for(y1 - y0))
    right = (band[0] - 3) if band else int(spine_x) - reach - 3
    if right - rx0 < 8:
        # The first ink block left of the spine was the title itself (a panel
        # with no numerals of its own). Then the whole strip is the title.
        right = int(spine_x) - reach - 3
    if right - rx0 < 8:
        return READ_REFUSED, "", "", "", "no strip left of the numerals for a title"
    strip = img.crop((rx0, y0, right, y1)).convert("L")
    # read it both ways round; the one tesseract is more confident in wins
    best = None
    for name, turned in (("bottom-up", strip.transpose(Image.ROTATE_270)),
                         ("top-down", strip.transpose(Image.ROTATE_90))):
        pad = 10
        padded = Image.new("L", (turned.width + 2 * pad, turned.height + 2 * pad), 255)
        padded.paste(turned, (pad, pad))
        big = padded.resize((padded.width * 2, padded.height * 2), Image.LANCZOS)
        try:
            d = A.pytesseract.image_to_data(big, config="--psm 6",
                                            output_type=A.pytesseract.Output.DICT)
        except Exception:
            continue
        ws = [(t.strip(), float(c)) for t, c in zip(d["text"], d["conf"])
              if (t or "").strip() and float(c) >= 0]
        good = [t for t, c in ws if c >= WORD_CONF and _is_word(t)]
        if not good:
            continue
        conf = float(np.mean([c for t, c in ws if c >= WORD_CONF and _is_word(t)]))
        text = " ".join(good)
        if best is None or conf > best[1]:
            best = (text, conf, name)
    if best is None:
        return READ_REFUSED, "", "", "", "tesseract read no word in the title strip"
    text = re.sub(r"\s+", " ", best[0]).strip(" |_-")
    # Tick marks and the panel's letter read as stray capitals after the
    # title ("(mm) NO O)", "(°C) WW"); a title ends at its unit.
    tokens = text.split(" ")
    while tokens and re.fullmatch(r"[A-Z][A-Z0-9]?[)\]]*", tokens[-1]):
        tokens.pop()
    text = " ".join(tokens)
    # A title has a word in it. Two stray letters read off a tick mark or a
    # panel letter ("Lo LG") are not one.
    if not re.search(r"[A-Za-z]{3}", text):
        return READ_REFUSED, "", "", "", "the title strip reads %r, which is not a title" % text
    outcome, unit = split_title(text)
    return READ_OK, text, outcome, unit, "%s, conf %.0f" % (best[2], best[1])


def split_title(text):
    """('Mean arterial pressure', 'mmHg') from 'Mean arterial pressure (mmHg)';
    (text, '') when no unit is printed."""
    m = re.match(r"^(.*?)\s*[\(\[]([^\)\]]+)[\)\]]\s*$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), ""


# ----------------------------------------------------------------------- n

def read_n(caption):
    """(status, n, detail) from the caption's 'n = 8'."""
    found = re.findall(r"\b[nN]\s*=\s*(\d+)", caption or "")
    distinct = sorted(set(int(v) for v in found))
    if not distinct:
        return READ_REFUSED, "", "the caption prints no n ="
    if len(distinct) > 1:
        return READ_REFUSED, "", "the caption prints several n: %s" % ", ".join(
            str(v) for v in distinct)
    return READ_OK, str(distinct[0]), "n = %d in the caption" % distinct[0]


# ------------------------------------------------------------------ propose

def propose_identity(image, geometry_row, kind="", caption="", raster_sha256=""):
    """One identity proposal row for a panel whose frame is known."""
    rgb = image.convert("RGB")
    gray = image.convert("L")
    dark = _dark(gray)
    frame = GP._frame_of(geometry_row)
    region = [int(v) for v in _s(geometry_row.get("Region")).split(",")] \
        if _s(geometry_row.get("Region")) else [0, 0, image.width, image.height]
    x0, x1, y0, y1 = frame
    spine = _s(geometry_row.get("Y_Axis_Spine_X"))
    spine_x = float(spine) if spine else x0
    row = {c: "" for c in IDENTITY_COLUMNS}
    row.update({
        "Proposal_ID": _s(geometry_row.get("Proposal_ID")),
        "Raster": _s(geometry_row.get("Raster")),
        "Raster_SHA256": raster_sha256 or _s(geometry_row.get("Raster_SHA256")),
        "Region": ",".join(str(v) for v in region),
        "Panel_X0": int(x0), "Panel_X1": int(x1), "Panel_Y0": int(y0), "Panel_Y1": int(y1),
        "Spine_X": int(spine_x), "Panel_Kind": _s(kind).upper(),
        "Human_Verification_Status": PENDING,
    })
    anchors, source = anchors_of(geometry_row)
    if not anchors:
        anchors, source = measure_anchors(gray, (int(x0), int(x1), int(y0), int(y1)))
    row["X_Anchor_Pixels"] = ";".join("%g" % a for a in anchors)
    row["X_Anchor_Count"] = len(anchors)
    row["X_Anchor_Source"] = source
    status, labels, detail, numeric = read_x_labels(image, dark, frame, anchors, region)
    row["X_Label_Read_Status"] = status
    row["X_Labels_Read"] = ";".join("%s@%g" % (t.replace(";", ","), a) for t, a in labels)
    row["X_Label_Detail"] = detail
    row["X_Numeric"] = "1" if numeric else ""

    colours = plot_colours(rgb, frame)
    row["Series_Colours"] = ";".join("%d,%d,%d" % c[2] for c in colours)
    row["Series_Colour_Count"] = len(colours)
    status, legend, detail = read_legend(image, rgb, frame, region, colours)
    row["Series_Read_Status"] = status
    row["Series_Read"] = ";".join("%s@%d,%d,%d" % ((t.replace(";", ","),) + c) for t, c in legend)
    row["Series_Detail"] = detail
    kinds = MARK_TYPES_FOR.get(row["Panel_Kind"], ())
    if len(kinds) == 2:
        row["Mark_Type_Proposed"] = kinds[0] if len(colours) >= 1 else kinds[1]
    elif kinds:
        row["Mark_Type_Proposed"] = kinds[0]

    status, title, outcome, unit, detail = read_y_title(image, dark, frame, spine_x, region)
    row["Y_Title_Read_Status"] = status
    row["Y_Title_Read"], row["Outcome_Read"], row["Unit_Read"] = title, outcome, unit
    row["Y_Title_Detail"] = detail

    status, n, detail = read_n(caption)
    row["N_Read_Status"], row["N_Read"], row["N_Detail"] = status, n, detail
    return row


def write_proposals(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(IDENTITY_COLUMNS))
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in IDENTITY_COLUMNS})
    return path


def labels_of(text):
    """[(label, px)] from 'label@px;label@px'."""
    out = []
    for part in _s(text).split(";"):
        if "@" not in part:
            continue
        label, px = part.rsplit("@", 1)
        try:
            out.append((label, float(px)))
        except ValueError:
            continue
    return out


def series_of(text):
    """[(name, (r,g,b) or None)] from 'name@r,g,b;name@r,g,b' or 'name;name'."""
    out = []
    for part in _s(text).split(";"):
        if not part:
            continue
        if "@" in part:
            name, colour = part.rsplit("@", 1)
            try:
                rgb = tuple(int(v) for v in colour.split(","))
                if len(rgb) != 3:
                    raise ValueError(colour)
            except ValueError:
                rgb = None
            out.append((name, rgb))
        else:
            out.append((part, None))
    return out


def overlay(image, row, out_path):
    """The proposal drawn on the raster: anchors with their labels, legend
    entries with their colours, the title."""
    from PIL import ImageDraw
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x0, x1, y0, y1 = [int(row[k]) for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")]
    draw.rectangle((x0, y0, x1, y1), outline=(200, 30, 30), width=2)
    font = GP._font(max(12, (y1 - y0) // 22))
    for label, px in labels_of(row.get("X_Labels_Read")):
        draw.line((px, y1 - 6, px, y1 + 14), fill=(30, 100, 200), width=2)
        draw.text((px - 4, y1 + 16), label, fill=(30, 100, 200), font=font)
    for a in [float(v) for v in _s(row.get("X_Anchor_Pixels")).split(";") if v]:
        draw.line((a, y1 - 10, a, y1 + 2), fill=(20, 150, 80), width=1)
    yy = y0 + 4
    for name, rgb in series_of(row.get("Series_Read")):
        if rgb:
            draw.rectangle((x1 + 6, yy, x1 + 22, yy + 14), fill=rgb, outline=(0, 0, 0))
        draw.text((x1 + 26, yy), name, fill=(30, 100, 200), font=font)
        yy += 18
    if _s(row.get("Y_Title_Read")):
        draw.text((x0 + 4, y0 - 18 if y0 > 20 else y0 + 2),
                  "y: " + _s(row.get("Y_Title_Read")), fill=(190, 60, 190), font=font)
    region = [int(v) for v in _s(row.get("Region")).split(",")]
    pad = 12
    ox, oy = max(0, region[0] - pad), max(0, region[1] - pad)
    canvas = canvas.crop((ox, oy, min(canvas.width, region[2] + pad + 160),
                          min(canvas.height, region[3] + pad)))
    canvas.save(out_path)
    return out_path


def overlay_origin(row):
    region = [int(v) for v in _s(row.get("Region")).split(",")]
    return max(0, region[0] - 12), max(0, region[1] - 12)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("raster")
    ap.add_argument("--geometry", required=True,
                    help="geometry_decisions.csv (CONFIRMED/SHARED rows) or a proposal file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--caption", default="")
    ap.add_argument("--kind", default="")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    image = Image.open(args.raster)
    digest = sha256_of(args.raster)
    rows = []
    with io.open(args.geometry, encoding="utf-8-sig") as fh:
        for g in csv.DictReader(fh):
            if GP._frame_of(g) is None:
                continue
            row = propose_identity(image, g, kind=args.kind, caption=args.caption,
                                   raster_sha256=digest)
            overlay(image, row, os.path.join(args.out, "%s.png" % row["Proposal_ID"]))
            rows.append(row)
            print("%s  x %s (%s)  series %s (%s)  y %s %r  n %s"
                  % (row["Proposal_ID"], row["X_Label_Read_Status"], row["X_Label_Detail"],
                     row["Series_Read_Status"], row["Series_Detail"],
                     row["Y_Title_Read_Status"], row["Y_Title_Read"], row["N_Read"]))
    print("wrote %s" % write_proposals(os.path.join(args.out, PROPOSALS), rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
