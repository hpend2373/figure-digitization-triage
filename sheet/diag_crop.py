# -*- coding: utf-8 -*-
"""What drove the box, on the fifteen crops the audit failed.

`figure_bbox` takes the gap above a caption and gives it the horizontal extent
of every block that overlaps the caption. Two guesses to test, one per failure
kind the audit named:

  mixed_figures    the horizontal union reaches the figure NEXT to this one,
                   because some block - a full-width header, a spanning line -
                   overlaps the caption and drags left/right across the page.
  clipped_target   the vertical bound stops at the nearest block above, and
                   that block is INSIDE the figure: an axis label, a legend,
                   a panel letter that came out as text.

Measured, not argued: for each failed crop this prints the block that set each
edge and how much of the page the box covers.
"""
import collections
import csv
import io
import json
import os
import sys

sys.path.insert(0, "/home/claude/geo/verify")
import corpus_intake as CI                                        # noqa: E402

AUDIT = ("/mnt/user-data/uploads/Downloads/include_fulltext_bundle/outputs/"
         "2026-08-28-contact-sheet-audit/confirmed_image_defects.csv")
DEFECTS = list(csv.DictReader(io.open(AUDIT, encoding="utf-8-sig")))
ROWS = json.load(open("/tmp/intake/crosscheck.json"))
BYPID = {r["pid"]: r for r in ROWS}
PATHS = {l.strip().rsplit("/", 1)[-1]: l.strip()
         for l in io.open("/tmp/wl/staged_paths.txt", encoding="utf-8")
         if l.strip()}

blocks_cache = {}


def blocks_for(pid):
    if pid not in blocks_cache:
        blocks_cache[pid] = CI.text_blocks(PATHS[BYPID[pid]["file"]])
    return blocks_cache[pid]


print("%-5s %-6s %-18s %-22s %-22s %s"
      % ("pid", "라벨", "결함", "가로를 정한 블록", "위 경계를 정한 블록", "면적비"))
kinds = collections.Counter()
wide_cause = collections.Counter()
for d in DEFECTS:
    pid, label, page = d["pid"], d["label"], int(d["page"])
    if pid not in BYPID:
        continue
    bl = blocks_for(pid)
    cands = [c for c in CI.caption_candidates(bl)
             if c["page"] == page and "FIG" + c["number"].upper() == label]
    if not cands:
        print("%-5s %-6s %-18s (이 라벨의 캡션 후보를 못 찾음)" % (pid, label, d["kind"]))
        continue
    c = cands[0]
    cx0, cx1 = c["bbox"][0], c["bbox"][2]
    top = c["bbox"][1]
    same = [b for b in bl if b[0] == page]
    column = [b for b in same if min(cx1, b[3]) - max(cx0, b[1]) > 0] or same
    above = [b for b in column if b[4] <= top]
    left_b = min(column, key=lambda b: b[1])
    right_b = max(column, key=lambda b: b[3])
    edge_b = max(above, key=lambda b: b[4]) if above else None
    box = CI.figure_bbox(c, bl)
    page_w = max(b[3] for b in same)
    frac = ((box[2] - box[0]) / page_w) if box else 0.0
    cap_frac = (cx1 - cx0) / page_w
    kinds[d["kind"]] += 1
    # is the horizontal extent wider than the caption's own line?
    if frac > cap_frac * 1.25:
        wide_cause[d["kind"]] += 1
    print("%-5s %-6s %-18s %-22s %-22s 가로 %.2f쪽폭 (캡션 %.2f)"
          % (pid, label, d["kind"],
             ("%.0f..%.0f %r" % (left_b[1], right_b[3],
                                 " ".join(left_b[5].split())[:12])),
             (("y=%.0f %r" % (edge_b[4], " ".join(edge_b[5].split())[:12]))
              if edge_b else "(위에 아무것도 없음)"),
             frac, cap_frac))

print()
print("결함 종류:", dict(kinds))
print("그중 가로가 캡션보다 25%% 이상 넓은 건:", dict(wide_cause))
