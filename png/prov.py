# -*- coding: utf-8 -*-
"""Which selected panels were CUT out of the figure and which were INVENTED,
and how well defended each one's axis is."""
import collections, csv, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import capt

CUT = (22, 120, 70)
MADE = (200, 120, 10)
BG, INK, MUTE = (247, 249, 247), (23, 29, 26), (95, 109, 102)
STATUS = {"ANCHOR_FREE": (0, 150, 110), "ANCHOR_CLIPPED": (10, 90, 175),
          "FALLBACK_LONGEST": (200, 120, 10),
          "GEOMETRY_UNRESOLVED": (168, 52, 43),
          "GEOMETRY_UNOBSERVED": (120, 120, 130)}
ORDER = ["ANCHOR_FREE", "ANCHOR_CLIPPED", "FALLBACK_LONGEST",
         "GEOMETRY_UNRESOLVED", "GEOMETRY_UNOBSERVED"]
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def B(s):
    return [int(v) for v in s.split(",")]


def selected(path):
    rows = list(csv.DictReader(open(path)))
    passes = {(r["pid"], r["fig"]): (r["mode"], r["ink"])
              for r in rows if r["kind"] == "SELECTED_PASS"}
    sel = [r for r in rows if r["kind"] == "SELECTED"
           and passes.get((r["pid"], r["fig"])) == (r["mode"], r["ink"])]
    return rows, sel


def matrix(trace, out):
    """The cross-tab, twice: as it first read, and with the shared-axis panels
    held apart - which is the difference between a finding and an artefact."""
    _rows, sel = selected(trace)

    def tab_of(subset):
        t = collections.Counter()
        for r in subset:
            t[("constructed" if r["constructed"] == "True" else "cut",
               r["axis_geometry"] or "?")] += 1
        return t

    own = [r for r in sel if r["row_left_reader"] != "True"]
    blocks = [("선택된 패널 전체", sel), ("같은 행 왼쪽에 ladder 를 읽는 패널이 없는 것만", own)]
    tf, hf, cf = capt.kr(26), ImageFont.truetype(MONO, 16), ImageFont.truetype(MONO, 30)
    W = 1500
    H = 104 + len(blocks) * 196
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((34, 26), "선택된 패널의 박스 출처 x 축의 근거", font=capt.kr(28), fill=INK)
    y = 108
    for title, subset in blocks:
        tab = tab_of(subset)
        d.text((34, y - 32), "%s  (n=%d)" % (title, len(subset)), font=capt.kr(19),
               fill=MUTE)
        x0, cw, rh = 320, 220, 56
        for j, c in enumerate(ORDER):
            d.text((x0 + j * cw, y), c, font=hf,
                   fill=STATUS.get(c, MUTE))
        d.text((x0 + len(ORDER) * cw, y), "TOTAL", font=hf, fill=MUTE)
        for i, origin in enumerate(("cut", "constructed")):
            col = CUT if origin == "cut" else MADE
            yy = y + 30 + i * rh
            d.text((34, yy + 6), origin, font=capt.kr(22), fill=col)
            tot = 0
            for j, c in enumerate(ORDER):
                n = tab[(origin, c)]
                tot += n
                d.text((x0 + j * cw, yy), "%d" % n, font=cf,
                       fill=INK if n else (205, 210, 207))
            d.text((x0 + len(ORDER) * cw, yy), "%d" % tot, font=cf, fill=col)
        y += 196
        d.line([(24, y - 66), (W - 24, y - 66)], fill=(215, 220, 217), width=2)
    figs = {(r["pid"], r["fig"]) for r in sel}
    made = {(r["pid"], r["fig"]) for r in sel if r["constructed"] == "True"}
    refused = [r for r in sel if r["status"] != "LADDER_OK"]
    blank = [r for r in refused if int(r["label_ink_cols"] or 0) <= 4]
    lines = [
        "invented boxes: %d of %d panels, on %d of %d figures"
        % (sum(1 for r in sel if r["constructed"] == "True"), len(sel),
           len(made), len(figs)),
        "roots: " + ", ".join("%s %d" % kv for kv in collections.Counter(
            r["origin_roots"] or "-" for r in sel).most_common()),
        "refused ladders: %d, of which %d have 4 or fewer inked columns beside"
        " the axis" % (len(refused), len(blank)),
        "  - a grid figure prints its y numerals once per row; those are"
        " refusals of a blank strip",
    ]
    im = capt.below(im, "%d개 도표, 선택된 패널 %d개" % (len(figs), len(sel)), lines,
                    minw=W)
    im.save(out)
    return out


def on_figure(trace, pid, fig, out):
    """One figure, its panels coloured by origin and labelled by axis status."""
    rows, sel = selected(trace)
    mine = [r for r in sel if r["pid"] == pid and r["fig"] == fig]
    png = mine[0]["png"]
    im = Image.open(os.path.join(ROOT, "clips", png)).convert("RGB")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(MONO, 15)
    for r in mine:
        b = B(r["box"])
        made = r["constructed"] == "True"
        col = MADE if made else CUT
        d.rectangle([b[0], b[2], b[1] - 1, b[3] - 1], outline=col, width=4)
        txt = "%s  %s  %s" % (r["panel"], "INVENTED" if made else "cut",
                              (r["axis_geometry"] or "?"))
        w = int(f.getlength(txt))
        x = min(b[0] + 5, im.width - w - 14)
        d.rectangle([x, b[2] + 5, x + w + 8, b[2] + 5 + f.size + 6], fill=(255, 255, 255))
        d.rectangle([x, b[2] + 5, x + w + 8, b[2] + 5 + f.size + 6], outline=col, width=2)
        d.text((x + 4, b[2] + 7), txt, font=f, fill=col)
    lines = ["%-4s %-19s %-9s %-16s %-5s %-7s %s"
             % ("", "box", "origin", "axis", "ink", "l.reads", "ladder")]
    for r in mine:
        lines.append("%-4s %-19s %-9s %-16s %-5s %-7s %s"
                     % (r["panel"], r["box"],
                        "INVENTED" if r["constructed"] == "True" else "cut",
                        (r["axis_geometry"] or "?"),
                        r["label_ink_cols"],
                        "yes" if r["row_left_reader"] == "True" else "-",
                        r["status"]))
    im = capt.below(im, "%s %s: 잘라낸 박스와 만들어낸 박스" % (pid, fig), lines,
                    keys=[(CUT, "cut out of the figure", False),
                          (MADE, "invented by a transform", False)])
    im.save(out)
    return out


if __name__ == "__main__":
    print(matrix("trP.csv", "png/E1_provenance_matrix.png"))
    print(on_figure("trP.csv", "177", "Fig. 2", "png/E2_shared_axis_177fig2.png"))
    print(on_figure("trP.csv", "475", "Fig. 1", "png/E3_provenance_475fig1.png"))
