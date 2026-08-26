# -*- coding: utf-8 -*-
"""ANCESTOR_REGION_COMPLETION, drawn: what is inside the piece and outside the
panel's plot core, and which of the five statements refused each blob."""
import csv, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import capt

PANEL   = (22, 120, 70)
PLOT    = (10, 90, 175)
LABEL   = (200, 120, 10)
PIECE   = (150, 80, 200)
DATA    = (0, 150, 110)
REFUSED = (150, 150, 160)
RED     = (168, 52, 43)
F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 15)
FS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 12)

CLAUSE = [("c_plot_side", "plot side"), ("c_no_own_axis", "own rule"),
          ("c_shares_axis_rows", "axis rows"), ("c_no_foreign_spine", "foreign spine"),
          ("c_above_caption", "caption")]


def B(s):
    return [int(v) for v in s.split(",")]


def dash(d, b, fill, w=3, on=11, off=9):
    x0, x1, y0, y1 = b
    for x in range(x0, x1, on + off):
        d.line([(x, y0), (min(x + on, x1), y0)], fill=fill, width=w)
        d.line([(x, y1), (min(x + on, x1), y1)], fill=fill, width=w)
    for y in range(y0, y1, on + off):
        d.line([(x0, y), (x0, min(y + on, y1))], fill=fill, width=w)
        d.line([(x1, y), (x1, min(y + on, y1))], fill=fill, width=w)


def chip(d, xy, text, col, limit, font=F, pad=4):
    x, y = xy
    w = int(font.getlength(text)); h = font.size + 2 * pad - 2
    if x + w + 2 * pad > limit:
        x = max(2, limit - w - 2 * pad - 2)
    d.rectangle([x, y, x + w + 2 * pad, y + h], fill=(255, 255, 255))
    d.rectangle([x, y, x + w + 2 * pad, y + h], outline=col, width=2)
    d.text((x + pad, y + pad - 2), text, fill=col, font=font)
    return h + 3


def load(trace, pid, fig):
    rows = list(csv.DictReader(open(trace)))
    sp = [r for r in rows if r["kind"] == "SELECTED_PASS"
          and r["pid"] == pid and r["fig"] == fig][0]
    mode, ink, png = sp["mode"], sp["ink"], sp["png"]
    keep = [r for r in rows if r["pid"] == pid and r["fig"] == fig
            and r["mode"] == mode and r["ink"] == ink]
    sh = [r for r in keep if r["kind"] == "RESIDUAL_SHADOW" and r.get("plot_box")]
    comp = [r for r in keep if r["kind"] == "RESIDUAL_COMPONENT"]
    sel = [r for r in rows if r["kind"] == "SELECTED"
           and r["pid"] == pid and r["fig"] == fig]
    return png, sh, comp, sel


def why(r):
    bad = [name for k, name in CLAUSE if r[k] == "X"]
    return ", ".join(bad)


def overview(trace, pid, fig, out):
    png, sh, comp, sel = load(trace, pid, fig)
    s = sh[0]
    im = Image.open(os.path.join(ROOT, "clips", png)).convert("RGB")
    d = ImageDraw.Draw(im)
    for r in sel:
        b = B(r["box"])
        d.rectangle([b[0], b[2], b[1] - 1, b[3] - 1], outline=PANEL, width=2)
    piece = B(s["orphan"])
    dash(d, piece, PIECE, w=4)
    chip(d, (piece[0] + 6, piece[2] + 6), "piece  " + s["orphan"], PIECE, im.width)
    p = B(s["panel"]); pb = B(s["plot_box"])
    d.rectangle([p[0], p[2], p[1] - 1, p[3] - 1], outline=PANEL, width=4)
    d.rectangle([pb[0], pb[2], pb[1] - 1, pb[3] - 1], outline=PLOT, width=3)
    if s["label_box"]:
        lb = B(s["label_box"]); dash(d, lb, LABEL, w=3)
    for r in comp:
        if r["orphan"] != s["orphan"] or r["panel"] != s["panel"]:
            continue
        b = B(r["component"])
        col = DATA if r["is_data"] == "True" else REFUSED
        d.rectangle([b[0] - 1, b[2] - 1, b[1], b[3]], outline=col, width=2)
    for r in comp:
        if r["is_data"] == "True" and r["panel"] == s["panel"]:
            b = B(r["component"])
            chip(d, (b[0] + 3, b[2] - 26), "is data", DATA, im.width, FS)
    im = capt.below(
        im, "패널 C의 잔여 성분: 조각 안, 패널 plot core 밖",
        ["piece 99,384,370,664  |  panel C  101,268,499,627  |  plot core %s" % s["plot_box"],
         "components %s   measured %s   too small %s   is_data %s"
         % (s["n_components"], s["n_measured"], s["n_too_small"], s["n_data"]),
         "panel C 의 axis: anchored=%s  free=%s  clipped=%s  spine x=%s  run %s"
         % (s["axis_anchored"], s["axis_n_free"], s["axis_n_clipped"],
            s["spine_x"], s["axis_run"]),
         "DAG: ancestor_region %s -> panel_region %s   descends=%s"
         % (s["ancestor_region"], s["panel_region"], s["panel_descends_from_piece"]),
         ],
        keys=[(PANEL, "selected panel", False), (PLOT, "plot core", False),
              (LABEL, "label strip", True), (PIECE, "piece", True),
              (DATA, "component: data", False), (REFUSED, "component: refused", False)])
    im.save(out)
    return out


def closeup(trace, pid, fig, out, scale=2):
    png, sh, comp, sel = load(trace, pid, fig)
    s = sh[0]
    piece = B(s["orphan"])
    pad = 18
    im = Image.open(os.path.join(ROOT, "clips", png)).convert("RGB")
    crop = im.crop((max(0, piece[0] - pad), max(0, piece[2] - pad),
                    min(im.width, piece[1] + pad), min(im.height, piece[3] + pad)))
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    ox, oy = max(0, piece[0] - pad), max(0, piece[2] - pad)

    def M(b):
        return [(b[0] - ox) * scale, (b[1] - ox) * scale,
                (b[2] - oy) * scale, (b[3] - oy) * scale]
    d = ImageDraw.Draw(crop)
    dash(d, M(piece), PIECE, w=4)
    p, pb = M(B(s["panel"])), M(B(s["plot_box"]))
    d.rectangle([p[0], p[2], p[1], p[3]], outline=PANEL, width=4)
    d.rectangle([pb[0], pb[2], pb[1], pb[3]], outline=PLOT, width=3)
    if s["label_box"]:
        dash(d, M(B(s["label_box"])), LABEL, w=3)
    mine = [r for r in comp if r["orphan"] == s["orphan"] and r["panel"] == s["panel"]]
    for r in sorted(mine, key=lambda r: -int(r["ink_px"])):
        b = M(B(r["component"]))
        ok = r["is_data"] == "True"
        col = DATA if ok else REFUSED
        d.rectangle([b[0] - 2, b[2] - 2, b[1] + 1, b[3] + 1], outline=col, width=3)
        if int(r["ink_px"]) >= 250:
            chip(d, (b[0], max(0, b[2] - 24)),
                 ("data" if ok else why(r)) + "  %spx" % r["ink_px"],
                 col if ok else RED, crop.width, FS)
    lines = ["%-20s %-6s %-5s %s" % ("component", "ink", "data", "refused by")]
    for r in sorted(mine, key=lambda r: -int(r["ink_px"]))[:10]:
        lines.append("%-20s %-6s %-5s %s"
                     % (r["component"], r["ink_px"],
                        "YES" if r["is_data"] == "True" else "no", why(r) or "-"))
    crop = capt.below(crop, "조각 안의 성분 31개 중 1개만 data 로 통과", lines)
    crop.save(out)
    return out


if __name__ == "__main__":
    print(overview("trR.csv", "475", "Fig. 1", "png/D1_residual_475fig1.png"))
    print(closeup("trR.csv", "475", "Fig. 1", "png/D2_residual_closeup.png"))
