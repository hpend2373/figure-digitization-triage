# -*- coding: utf-8 -*-
"""Old box and new box on the same page, so a person can see which is right.

    python3 compare_regions.py <run> <out.png> <Draft_ID>...

Red is `Figure_BBox` - the gap above the caption that the sheet has been
cutting from. Blue is `Validated_Figure_BBox` - the union of what the PDF
actually draws, after clustering and caption assignment. A cell says which
row it is and what each side answered.
"""
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFont
Image.MAX_IMAGE_PIXELS = None

F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def box_px(box, size, page_pt):
    """Points to pixels. BOTH boxes are already in the raster's convention -
    y downward from the top - because `validate_regions` converts what
    pdfminer says before writing it. Flipping here as well would mirror them
    both back, which is the mistake this comment exists to prevent."""
    if not box:
        return None
    w, h = size
    pw, ph = page_pt
    sx, sy = w / pw, h / ph
    x0, y0, x1, y1 = box
    return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)


def cell(row, val, run, size):
    tile = Image.new("RGB", (size, size + 40), "white")
    d = ImageDraw.Draw(tile)
    pr = row.get("Page_Raster") or ""
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except ValueError:
        pw = ph = 0.0
    if not pr or not os.path.exists(pr) or pw <= 0:
        d.text((8, size // 2), "페이지 없음", fill="red",
               font=ImageFont.truetype(F, 18))
        return tile
    im = Image.open(pr).convert("RGB")
    old = box_px(_parse(row.get("Figure_BBox")), im.size, (pw, ph))
    new = box_px(_parse(val.get("PDF_BBox") or val.get("Validated_Figure_BBox")),
                 im.size, (pw, ph))
    ras = box_px(_parse(val.get("Raster_BBox")), im.size, (pw, ph))
    keep = [b for b in (old, new, ras) if b]
    L = max(0, min(b[0] for b in keep) - 60) if keep else 0
    T = max(0, min(b[1] for b in keep) - 60) if keep else 0
    R = min(im.size[0], max(b[2] for b in keep) + 60) if keep else im.size[0]
    B = min(im.size[1], max(b[3] for b in keep) + 60) if keep else im.size[1]
    view = im.crop((int(L), int(T), int(R), int(B)))
    k = min(size / view.size[0], size / view.size[1])
    view = view.resize((max(1, int(view.size[0] * k)),
                        max(1, int(view.size[1] * k))), Image.LANCZOS)
    vd = ImageDraw.Draw(view)
    # 빨강 = 지금 상자(글자 걸음) · 파랑 = PDF 객체 · 초록 = 래스터 잉크
    for b, colour, wide in ((old, (230, 0, 0), 3), (new, (0, 80, 235), 3),
                            (ras, (0, 150, 40), 3)):
        if not b:
            continue
        vd.rectangle([int((b[0] - L) * k), int((b[1] - T) * k),
                      int((b[2] - L) * k) - 1, int((b[3] - T) * k) - 1],
                     outline=colour, width=wide)
    tile.paste(view, ((size - view.size[0]) // 2, (size - view.size[1]) // 2))
    return tile


def _parse(text):
    try:
        x0, y0, x1, y1 = [float(v) for v in str(text).split(",")]
    except ValueError:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def main(run, out, ids, cols=4, size=430, first=1):
    import roundtrip
    roundtrip.selfcheck(run)
    draft = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8"))}
    val = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "validated_regions.csv"), encoding="utf-8"))}
    cen = {}
    p = os.path.join(run, "crop_visual_census.csv")
    if os.path.exists(p):
        cen = {r["Draft_ID"]: r for r in csv.DictReader(
            io.open(p, encoding="utf-8"))}
    rows_n = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (size + 6) + 6,
                              rows_n * (size + 46) + 6), "white")
    for i, did in enumerate(ids):
        t = cell(draft[did], val.get(did, {}), run, size)
        d = ImageDraw.Draw(t)
        d.rectangle([0, size, size, size + 39], fill=(245, 245, 245))
        d.text((5, size + 2), "%d %s" % (first + i, did[:36]), fill=(0, 0, 0),
               font=ImageFont.truetype(F, 15))
        d.text((5, size + 20), "합의=%s  PDF=%s  래스터=%s"
               % ((val.get(did) or {}).get("Agreement", "-"),
                  (val.get(did) or {}).get("PDF_Code", "-"),
                  (val.get(did) or {}).get("Raster_Code", "-")),
               fill=(90, 90, 90), font=ImageFont.truetype(F, 12))
        d.rectangle([0, 0, size - 1, size + 39], outline=(170, 170, 170))
        sheet.paste(t, (6 + (i % cols) * (size + 6),
                        6 + (i // cols) * (size + 46)))
    sheet.save(out, optimize=True)
    print("%s  %d칸  %.1f MB" % (out, len(ids), os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    _args = sys.argv[3:]
    _first = 1
    if _args and _args[0] == "--first":
        _first, _args = int(_args[1]), _args[2:]
    main(sys.argv[1], sys.argv[2], _args, first=_first)
