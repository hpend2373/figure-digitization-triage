# -*- coding: utf-8 -*-
"""Stage 2 - does the page SHOW what the files hold?

    python3 display_checks.py <run dir>      # every built part; exit 0 = all pass

Stage 1 (`verify_intake_images`, `roundtrip`) proves the files: whole, named,
cut from their boxes. Stage 3 (`validate_regions`, the census) asks what is
in them. Between the two is the page a person actually looks at, and nothing
checked it: an image can be embedded distorted, downscaled past counting, or
with the box drawn on the wrong part of the page, and every file-level check
still passes. These are the three questions this module asks of every open
card, by decoding the pictures the HTML carries and comparing them with the
files they were made from.

    zoom_matches_crop      the click-to-zoom image has the crop's own pixel
                           size - nothing was thrown away before a person
                           counts axis regions in it
    thumb_keeps_aspect     the grid thumbnail has the crop's aspect ratio
    page_box_drawn_where_the_row_says
                           the red outline on the page view runs along the
                           edges of `Figure_BBox` (raster convention: y down),
                           which is the display-layer half of the round-trip
                           check - the same mirror that fooled the census on
                           2026-09-02 would put this outline on the wrong half
                           of the page

Boxes here are in the draft's convention, y down from the top; the page view
is a thumbnail of the raster, so points scale to its pixels by width/points.
"""
import base64
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

#: Red as `build_sheet2.page_view` draws it, after JPEG. Wide enough for the
#: compression bleed, narrow enough that a red bar in a bar chart (usually
#: lighter or bluer) does not pass.
RED = lambda r, g, b: r >= 140 and g <= 90 and b <= 90
#: How much of each expected edge must be red for the outline to count as
#: drawn there. The outline is 3px+ wide before thumbnailing, so a correctly
#: placed box covers its edges almost completely; a mirrored one covers none.
EDGE_COVER = 0.55
#: Tolerance around the expected edge, in page-view pixels.
EDGE_TOL = 6

_DIV = re.compile(r"<div class='fig[^']*' data-id='([^']+)'")
_IMG = re.compile(r"<img class='thumb' src='(data:[^']+)' alt=''"
                  r"(?: data-zoom='(data:[^']+)')?(?: data-page='(data:[^']+)')?>")


def cards(html):
    """[{Draft_ID, thumb, zoom, page}] for EVERY card in one part's HTML.

    Every card, not every card with a picture: a NO_CROP row or a publisher's
    figure file renders without the thumb, and a parser that only saw cards
    with pictures could not say whether the page listed all the rows.
    """
    starts = list(_DIV.finditer(html))
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
        body = html[m.end():end]
        img = _IMG.search(body)
        out.append({"Draft_ID": m.group(1),
                    "thumb": img.group(1) if img else "",
                    "zoom": (img.group(2) or "") if img else "",
                    "page": (img.group(3) or "") if img else ""})
    return out


def decode(data_uri):
    from PIL import Image
    head, _, payload = data_uri.partition(",")
    return Image.open(io.BytesIO(base64.b64decode(payload)))


def zoom_matches_crop(card, crop_path, max_width=0):
    if not card["zoom"]:
        return False, "확대 이미지가 없다"
    z = decode(card["zoom"])
    from PIL import Image
    c = Image.open(crop_path)
    want = c.size
    if max_width and c.width > max_width:
        want = (max_width, max(1, round(c.height * max_width / c.width)))
    if z.size != want:
        return False, "확대 %sx%s vs 크롭 %sx%s" % (z.size + want)
    return True, "%dx%d" % z.size


def thumb_keeps_aspect(card, crop_path, tolerance=0.02):
    from PIL import Image
    t = decode(card["thumb"])
    c = Image.open(crop_path)
    a, b = t.width / float(t.height), c.width / float(c.height)
    # PIXELS ARE WHOLE NUMBERS AND RATIOS ARE NOT. A 1150x40 crop thumbnailed
    # to 300 wide wants to be 10.43 pixels tall and can only be 10, so its
    # ratio reads 30.0 against the crop's 28.75 - 4% out, and every bit of it
    # rounding. Called a distortion, that verdict falls on exactly the flattest
    # crops, which is the shape THIN_CROP rows have - the rows this check
    # started seeing the day blocked rows began carrying their pictures. So a
    # ratio the thumbnail's integer size can explain passes, and the flat
    # tolerance still catches anything wider than rounding.
    lo = (t.width - 0.5) / (t.height + 0.5)
    hi = (t.width + 0.5) / max(t.height - 0.5, 0.5)
    if lo <= b <= hi:
        return True, "%.3f (반올림 범위 %.3f~%.3f 안)" % (a, lo, hi)
    if abs(a - b) / b > tolerance:
        return False, "썸네일 비율 %.3f vs 크롭 %.3f" % (a, b)
    return True, "%.3f" % a


def _edge_cover(px, size, x0, y0, x1, y1, tol):
    """Fraction of each of the four expected edges that is red."""
    W, H = size
    out = []
    # top and bottom: walk x, look for red within tol of the edge y
    for ye in (y0, y1):
        hits = total = 0
        for x in range(max(0, int(x0)), min(W, int(x1))):
            total += 1
            if any(RED(*px[x, y][:3]) for y in range(max(0, int(ye - tol)),
                                                    min(H, int(ye + tol) + 1))):
                hits += 1
        out.append(hits / float(total) if total else 0.0)
    for xe in (x0, x1):
        hits = total = 0
        for y in range(max(0, int(y0)), min(H, int(y1))):
            total += 1
            if any(RED(*px[x, y][:3]) for x in range(max(0, int(xe - tol)),
                                                    min(W, int(xe + tol) + 1))):
                hits += 1
        out.append(hits / float(total) if total else 0.0)
    return out


def page_box_drawn_where_the_row_says(card, row, tol=EDGE_TOL, cover=EDGE_COVER):
    if not card["page"]:
        return False, "페이지 뷰가 없다"
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
        x0, y0, x1, y1 = [float(v) for v in row["Figure_BBox"].split(",")]
    except (KeyError, ValueError):
        return False, "행에 기하가 없다"
    im = decode(card["page"]).convert("RGB")
    sx, sy = im.width / pw, im.height / ph
    ex = (min(x0, x1) * sx, min(y0, y1) * sy, max(x0, x1) * sx, max(y0, y1) * sy)
    # 상자가 페이지 밖으로 나가면 그 변은 그려지지 않으므로 페이지 안으로 자른다
    ex = (max(0.0, ex[0]), max(0.0, ex[1]),
          min(im.width - 1.0, ex[2]), min(im.height - 1.0, ex[3]))
    covers = _edge_cover(im.load(), im.size, *ex, tol=tol)
    ok = all(c >= cover for c in covers)
    return ok, "변 덮임 위·아래·왼·오 = %s" % "/".join("%.2f" % c for c in covers)


def check_run(run, parts, draft_rows, zoom_max_width=0):
    """[(Draft_ID, check, detail)] for every open card in `parts` that fails."""
    by_id = {d["Draft_ID"]: d for d in draft_rows}
    problems, seen = [], 0
    for part in parts:
        html = io.open(part, encoding="utf-8").read()
        for card in cards(html):
            row = by_id.get(card["Draft_ID"])
            if row is None:
                problems.append((card["Draft_ID"], "card", "초안에 없는 행"))
                continue
            if not card["zoom"]:
                continue        # rows without a picture carry no zoom
            seen += 1
            crop = os.path.join(run, row.get("Figure_Crop") or "")
            if not os.path.exists(crop):
                problems.append((card["Draft_ID"], "crop", "크롭 파일 없음"))
                continue
            for name, fn in (("zoom", lambda: zoom_matches_crop(card, crop, zoom_max_width)),
                             ("thumb", lambda: thumb_keeps_aspect(card, crop)),
                             ("page_box", lambda: page_box_drawn_where_the_row_says(card, row))):
                ok, detail = fn()
                if not ok:
                    problems.append((card["Draft_ID"], name, detail))
    return problems, seen


def main(run):
    import paths as P
    parts = P.parts_for(P.SHEET) if P.SHEET.startswith(run) else P.parts_for(
        os.path.join(run, "panel_count_contact_sheet.html"))
    if not parts:
        raise SystemExit("빌드된 시트가 없습니다: %s" % run)
    draft = list(csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    problems, seen = check_run(run, parts, draft,
                               int(os.environ.get("FDT_ZOOM_MAX_WIDTH", "0")))
    for did, name, detail in problems[:40]:
        print("  FAIL %-10s %-44s %s" % (name, did[-44:], detail))
    print("2단계 화면 검사: 열린 카드 %d개 · 문제 %d개 · %s"
          % (seen, len(problems), "통과" if not problems else "REFUSED"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
