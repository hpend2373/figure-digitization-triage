# -*- coding: utf-8 -*-
"""Measure the text walk against the two independent detectors, then try a
better walk on the same blocks and measure again.

    python3 walk_experiment.py <run> [seconds]

For every draft row whose regions table holds a validated box, the current
`figure_bbox` and a candidate replacement are run on the SAME text blocks, and
each box's IoU with the validated region is recorded. The score is the share
of rows at IoU >= 0.5 - the threshold `validate_regions` uses to call the
text walk in agreement. Blocks are cached per document under <run>/.blocks/.
"""
import csv
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus_intake as CI                                       # noqa: E402


def _box(t):
    try:
        x0, y0, x1, y1 = [float(v) for v in str(t).split(",")]
    except ValueError:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def iou(a, b):
    if not a or not b:
        return 0.0
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def blocks_for(run, doc, path):
    cache = os.path.join(run, ".blocks", doc + ".json")
    if os.path.exists(cache):
        return [tuple(b) for b in json.loads(io.open(cache, encoding="utf-8").read())]
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    blocks = CI.text_blocks(path, backend="PDFMINER_TEXT_BLOCKS")
    io.open(cache, "w", encoding="utf-8").write(json.dumps(blocks, ensure_ascii=False))
    return blocks


def candidate_for(blocks, row):
    """Rebuild the caption candidate dict `figure_bbox` expects, from the row."""
    cap = _box(row.get("Caption_BBox"))
    if cap is None:
        return None
    return {"page": int(row["Page"]), "bbox": cap, "text": row.get("Caption_Text", "")}


# ------------------------------------------------------------ the new walk
def figure_bbox_v2(candidate, blocks, page_size=None, furniture=None):
    """The walk, with two things it did not do before.

    STOP UNDER THE RUNNING HEAD - WHEN THERE IS ONE. When no block stops the
    walk, the region used to reach y=0 and so took in the running head and the
    top margin. Furniture blocks are kept out of the walk on purpose (they must
    not set an edge from mid-page), but where a page HAS a running head above
    the caption, the region stops at its bottom. A page with no furniture at
    all keeps the old behaviour: no evidence of a header, nothing to stop at.

    WIDTH FROM THE COLUMN, NOT FROM THE WHOLE PAGE. `left/right` came from
    every block overlapping the caption's x-range, which on a two-column page
    includes full-width paragraphs and so reached across the gutter. When the
    caption is a column caption (narrower than COLUMN_SHARE of the page's text
    width), blocks wider than WIDE_SHARE of it are left out of the width - they
    are the page's, not the column's. A full-width caption keeps everything.
    """
    page, top = candidate["page"], candidate["bbox"][1]
    cx0, cx1 = candidate["bbox"][0], candidate["bbox"][2]

    def overlaps(block):
        return min(cx1, block[3]) - max(cx0, block[1]) > 0

    skip = CI.page_furniture(blocks) if furniture is None else furniture
    on_page = [b for b in blocks if b[0] == page]
    same_page = [b for b in on_page if id(b) not in skip]
    if not same_page:
        return None
    text_w = max(b[3] for b in on_page) - min(b[1] for b in on_page)
    column = [b for b in same_page if overlaps(b)] or same_page
    above = sorted([b for b in column if b[4] <= top], key=lambda b: -b[4])
    lower_edge = CI.interior_floor(above, cx1 - cx0)
    if lower_edge <= 0.0:
        height = max((b[4] for b in blocks), default=0.0) or 1.0
        heads = [b[4] for b in on_page if id(b) in skip and b[4] <= top
                 and b[4] <= 0.15 * height]
        if heads:
            lower_edge = max(heads)
    if lower_edge >= top:
        return None
    # ONLY ON A PAGE THAT HAS COLUMNS. A short caption on a one-column page is
    # just a short caption; the wide paragraphs there are the column. The page
    # is two-column when narrow blocks sit on both sides of its middle.
    two_col = two_column(on_page, text_w) and not os.environ.get('NO_WIDTH')
    narrow_caption = (cx1 - cx0) < COLUMN_SHARE * text_w
    width_blocks = [b for b in column
                    if not (two_col and narrow_caption
                            and (b[3] - b[1]) > WIDE_SHARE * text_w)]
    xs0 = [cx0] + [b[1] for b in width_blocks]
    xs1 = [cx1] + [b[3] for b in width_blocks]
    return (min(xs0), lower_edge, max(xs1), top)


def two_column(on_page, text_w):
    """True when narrow blocks sit on both sides of the page's middle."""
    if not on_page:
        return False
    left_edge = min(b[1] for b in on_page)
    mid = left_edge + text_w / 2.0
    narrow = [b for b in on_page if (b[3] - b[1]) < 0.55 * text_w]
    lefts = [b for b in narrow if b[3] <= mid + 0.04 * text_w]
    rights = [b for b in narrow if b[1] >= mid - 0.04 * text_w]
    return len(lefts) >= 3 and len(rights) >= 3


#: A caption narrower than this share of the page's text width sits in one
#: column of a multi-column page.
COLUMN_SHARE = 0.6
#: A block wider than this share of the page's text width spans columns.
WIDE_SHARE = 0.7


def main(run, budget):
    draft = list(csv.DictReader(io.open(os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    ledger = {r["Source_Document_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "intake_document_status.csv"), encoding="utf-8"))}
    reg_path = os.path.join(run, "validated_regions.csv.before-recut-2026-09-02")
    if not os.path.exists(reg_path):
        reg_path = os.path.join(run, "validated_regions.csv")
    regions = {r["Draft_ID"]: r for r in csv.DictReader(io.open(reg_path, encoding="utf-8"))}
    t0 = time.time()
    rows_out, skipped_docs = [], 0
    by_doc = {}
    for d in draft:
        by_doc.setdefault(d["Source_Document_ID"], []).append(d)
    for doc, rows in sorted(by_doc.items()):
        if time.time() - t0 > budget:
            skipped_docs += 1
            continue
        src = ledger[doc]["Input_Path"]
        if not os.path.exists(src):
            continue
        try:
            blocks = blocks_for(run, doc, src)
        except Exception as exc:                                 # noqa: BLE001
            print("  블록 실패 %s: %s" % (doc, str(exc)[:60]))
            continue
        furniture = CI.page_furniture(blocks)
        for d in rows:
            reg = regions.get(d["Draft_ID"])
            if not reg or not reg.get("Validated_Figure_BBox"):
                continue
            validated = _box(reg["Validated_Figure_BBox"])
            cand = candidate_for(blocks, d)
            if cand is None:
                continue
            old = CI.figure_bbox(cand, blocks, furniture=furniture)
            new = figure_bbox_v2(cand, blocks, furniture=furniture)
            rows_out.append({"Draft_ID": d["Draft_ID"], "iou_old": iou(old, validated),
                             "iou_new": iou(new, validated),
                             "iou_recorded": iou(_box(d.get("Proposal_Figure_BBox") or d["Figure_BBox"]), validated),
                             "old": old, "new": new, "validated": validated})
    n = len(rows_out)
    if not n:
        print("측정할 행이 없습니다"); return 1
    agree = lambda k: sum(1 for r in rows_out if r[k] >= 0.5)
    print("검증 상자가 있는 행 %d (건너뛴 문서 %d)" % (n, skipped_docs))
    print("  기록된 상자(초안)  IoU>=0.5: %3d  (%.0f%%)" % (agree("iou_recorded"), 100.0 * agree("iou_recorded") / n))
    print("  지금 걸음(재계산)  IoU>=0.5: %3d  (%.0f%%)" % (agree("iou_old"), 100.0 * agree("iou_old") / n))
    print("  새 걸음            IoU>=0.5: %3d  (%.0f%%)" % (agree("iou_new"), 100.0 * agree("iou_new") / n))
    better = sum(1 for r in rows_out if r["iou_new"] > r["iou_old"] + 0.05)
    worse = sum(1 for r in rows_out if r["iou_new"] < r["iou_old"] - 0.05)
    print("  행 단위: 좋아짐 %d · 나빠짐 %d · 그대로 %d" % (better, worse, n - better - worse))
    out = os.path.join(run, "walk_experiment.csv")
    with io.open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Draft_ID", "iou_recorded", "iou_old", "iou_new", "old", "new", "validated"])
        w.writeheader()
        for r in rows_out:
            w.writerow({k: ("%.3f" % v if isinstance(v, float) else v) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 150))
