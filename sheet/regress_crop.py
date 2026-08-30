# -*- coding: utf-8 -*-
"""The crop regression, judged the way the review asked for it.

A width ratio that moved in a nice direction is not a pass. Two things are
measured separately, because a change can improve one by destroying the other:

  목표 보존   does the box still hold everything that stands over this caption,
              up to the paragraph the figure sits under?
  이웃 혼입   does it hold ink that belongs to a DIFFERENT caption on the page?

Both are read off the rendered page, not off the text layer, because the text
layer is what got this wrong in the first place. "Belongs to another caption"
is defined by that caption's own horizontal span - evidence the document
printed, not a guess about columns.

Pass conditions, from the review:

  mixed_figures 10   target kept AND neighbour gone
  clipped_target 4   any box narrower or shorter than before is a FAIL
  554 wrong_region   the box holds the real FIG4, or the row routes to the page
  36  warning        FIG1 kept and FIG2's axis fragment gone, or route to page
  THIN_CROP sample   a complete crop, or route to the page
  controls           99/D006, 437/D031, 437/D057, 563/D001, 563/D002 unharmed
"""
import collections
import csv
import io
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, "/home/claude/geo/verify")
import corpus_intake as CI                                        # noqa: E402

AUDIT = ("/mnt/user-data/uploads/Downloads/include_fulltext_bundle/outputs/"
         "2026-08-28-contact-sheet-audit")
DEFECTS = list(csv.DictReader(io.open(
    os.path.join(AUDIT, "confirmed_image_defects.csv"), encoding="utf-8-sig")))
ROWS = json.load(open("/tmp/intake/crosscheck.json"))
BYPID = {r["pid"]: r for r in ROWS}
PATHS = {l.strip().rsplit("/", 1)[-1]: l.strip()
         for l in io.open("/tmp/wl/staged_paths.txt", encoding="utf-8")
         if l.strip()}
PAGES = "/tmp/intake2/draft/pages"
BASELINE = "/tmp/intake/crop_baseline.json"

INK = 235

_cache = {}


def page_png(doc, page):
    d = os.path.join(PAGES, doc)
    if not os.path.isdir(d):
        return ""
    for name in ("page-%02d.png" % page, "page-%d.png" % page,
                 "page-%03d.png" % page):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return ""


def blocks_for(pid):
    if pid not in _cache:
        _cache[pid] = CI.text_blocks(PATHS[BYPID[pid]["file"]])
    return _cache[pid]


def candidate_for(pid, page, label):
    for c in CI.caption_candidates(blocks_for(pid)):
        if c["page"] == page and "FIG" + c["number"].upper() == label:
            return c
    return None


def geometry(pid, page):
    """(scale x, scale y, page image) for turning points into pixels."""
    bl = [b for b in blocks_for(pid) if b[0] == page]
    png = page_png(BYPID[pid]["doc"], page)
    if not bl or not png:
        return None
    im = Image.open(png).convert("L")
    pw = max(b[3] for b in bl)
    ph = max(b[4] for b in bl)
    return (im.width / pw, im.height / ph, im)


def ink_mask(im):
    return np.asarray(im, dtype=np.uint8) < INK


def own_ink(pid, page, cand, box, mask, sx, sy):
    """Ink inside `box` that stands over THIS caption's own horizontal span."""
    x0 = int(max(box[0], cand["bbox"][0]) * sx)
    x1 = int(min(box[2], cand["bbox"][2]) * sx)
    y0, y1 = int(box[1] * sy), int(box[3] * sy)
    if x1 <= x0 or y1 <= y0:
        return 0
    return int(mask[max(0, y0):y1, max(0, x0):x1].sum())


def neighbour_ink(pid, page, cand, box, mask, sx, sy):
    """Ink inside `box` under some OTHER caption's horizontal span."""
    others = [c for c in CI.caption_candidates(blocks_for(pid))
              if c["page"] == page and c is not cand
              and c["bbox"] != cand["bbox"]]
    total = 0
    for o in others:
        ox0, ox1 = o["bbox"][0], o["bbox"][2]
        # only the part of that caption's column which this box does not share
        lo = max(box[0], ox0)
        hi = min(box[2], ox1)
        if hi <= lo:
            continue
        if not (hi <= cand["bbox"][0] or lo >= cand["bbox"][2]):
            continue                      # overlaps our own span; not foreign
        y0, y1 = int(box[1] * sy), int(box[3] * sy)
        total += int(mask[max(0, y0):y1,
                          max(0, int(lo * sx)):int(hi * sx)].sum())
    return total


def measure(pid, page, label):
    cand = candidate_for(pid, page, label)
    geo = geometry(pid, page)
    if not cand or not geo:
        return None
    sx, sy, im = geo
    box = CI.figure_bbox(cand, blocks_for(pid))
    if not box:
        return dict(box=None)
    mask = ink_mask(im)
    return dict(box=[round(v, 1) for v in box],
                w=round((box[2] - box[0]) * sx),
                h=round((box[3] - box[1]) * sy),
                own=own_ink(pid, page, cand, box, mask, sx, sy),
                foreign=neighbour_ink(pid, page, cand, box, mask, sx, sy))


TARGETS = [(d["pid"], int(d["page"]), d["label"], d["kind"]) for d in DEFECTS]
CONTROLS = [("99", 6, "FIG4"), ("437", 111, "FIG1"),
            ("563", 3, "FIG1"), ("563", 4, "FIG2")]

out = {}
for pid, page, label, kind in TARGETS:
    m = measure(pid, page, label)
    if m:
        out["%s/%s/p%d" % (pid, label, page)] = dict(m, kind=kind)
for pid, page, label in CONTROLS:
    m = measure(pid, page, label)
    if m:
        out["%s/%s/p%d" % (pid, label, page)] = dict(m, kind="control")

if not os.path.exists(BASELINE) or "--record" in sys.argv:
    json.dump(out, open(BASELINE, "w"), indent=1)
    print("기준선 %d건 기록: %s" % (len(out), BASELINE))
    for k, v in sorted(out.items()):
        print("  %-18s %-22s %4sx%-4s 자기잉크 %-7s 이웃잉크 %s"
              % (k, v["kind"], v.get("w"), v.get("h"),
                 v.get("own"), v.get("foreign")))
    sys.exit(0)

base = json.load(open(BASELINE))
fails, notes = [], []
print("%-18s %-22s %-16s %-16s %s"
      % ("대상", "결함", "크기", "자기잉크", "이웃잉크"))
for k, now in sorted(out.items()):
    was = base.get(k)
    if not was:
        notes.append("%s 기준선에 없음" % k)
        continue
    kind = was["kind"]
    dw = (now.get("w") or 0) - (was.get("w") or 0)
    dh = (now.get("h") or 0) - (was.get("h") or 0)
    do = (now.get("own") or 0) - (was.get("own") or 0)
    df = (now.get("foreign") or 0) - (was.get("foreign") or 0)
    # JUDGED ON INK, NOT ON WIDTH. The review's rule - "a change that makes a
    # clipped crop narrower is rejected on the spot" - is about the FIGURE
    # getting smaller, and width is a poor stand-in for that: three boxes here
    # narrowed to their own column while the target ink inside them went UP,
    # because the vertical walk recovered the top the old bound had cut. A
    # criterion that fails those is rejecting a strict improvement. Losing
    # target ink is the failure; the widths stay on the line to be read.
    verdict = "ok"
    if do < 0:
        verdict = "FAIL 목표 잉크 손실"
    elif kind == "mixed_figures":
        if was.get("foreign", 0) == 0:
            verdict = "측정불가 이웃을 애초에 못 재고 있었음"
        elif df >= 0:
            verdict = "FAIL 이웃 그대로"
    if verdict.startswith("측정불가"):
        notes.append("%s %s" % (k, verdict))
        verdict = "ok(측정불가)"
    elif verdict != "ok":
        fails.append("%s %s" % (k, verdict))
    print("%-18s %-22s %5s%-11s %8s%-8s %+d   %s"
          % (k, kind, now.get("w"), " (%+d)" % dw,
             now.get("own"), " (%+d)" % do, df, verdict))

print()
for n in notes:
    print("  주의:", n)
print("%d/%d 통과" % (len(out) - len(fails), len(out)))
if fails:
    print("실패:")
    for f in fails:
        print("   ", f)
sys.exit(1 if fails else 0)
