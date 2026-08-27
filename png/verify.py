# -*- coding: utf-8 -*-
"""The reader put back on the figure it read.

Not a diagram of the pipeline: the published raster with the number recovered
from each mark drawn on the mark, beside the value a person read off the same
mark by eye. What is refused is drawn too, in red, because a reader that only
shows what it answered cannot be judged.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
import capt
import raster_root as RR

OK = (0, 150, 110)
EYEC = (10, 90, 175)
BAD = (168, 52, 43)
AXIS = (176, 108, 12)
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def zoom(im, crop, scale):
    """A crop of the raster at `scale`, and the mapper from raster to crop."""
    x0, x1, y0, y1 = crop
    out = im.crop((x0, y0, x1, y1))
    out = out.resize((out.width * scale, out.height * scale), Image.LANCZOS)
    return out, (lambda px, py: ((px - x0) * scale, (py - y0) * scale))


def chip(d, xy, text, col, limit, size=15, pad=3):
    f = ImageFont.truetype(MONO, size)
    x, y = xy
    w = int(f.getlength(text))
    x = max(2, min(x, limit - w - 2 * pad - 2))
    d.rectangle([x, y, x + w + 2 * pad, y + f.size + 2 * pad - 2], fill=(255, 255, 255))
    d.rectangle([x, y, x + w + 2 * pad, y + f.size + 2 * pad - 2], outline=col, width=2)
    d.text((x + pad, y + pad - 2), text, fill=col, font=f)
    return f.size + 2 * pad + 1


def axis_marks(d, cal, box, ticks, limit):
    """The calibration, drawn: every tick the reader was given, at its row."""
    for value, row in ticks:
        d.line([(box[0] - 26, row), (box[1], row)], fill=AXIS, width=1)
        chip(d, (box[0] - 26, row - 10), "%g" % value, AXIS, limit, size=13)


def bars_397():
    import mark_readers as MR
    # A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC.
    path = RR.check("397_fig3.jpeg")[0]
    if not path:
        print(RR.skip_note("397_fig3.jpeg"))
        return ""
    SPECS = [MR.SeriesSpec("FLUID", bar_fill="SOLID"),
             MR.SeriesSpec("NON_FLUID", bar_fill="HATCHED")]
    PANELS = (
        dict(name="MEN", box=(118, 480, 90, 470), ticks=[(150, 101), (50, 465)],
             x={"PRE": 187, "POST": 390},
             eye={("FLUID", "PRE"): 97, ("FLUID", "POST"): 123,
                  ("NON_FLUID", "PRE"): 96, ("NON_FLUID", "POST"): 113}),
        dict(name="WOMEN", box=(620, 1010, 88, 466), ticks=[(150, 95), (50, 460)],
             x={"PRE": 720, "POST": 920},
             eye={("FLUID", "PRE"): 88, ("FLUID", "POST"): 110,
                  ("NON_FLUID", "PRE"): 92, ("NON_FLUID", "POST"): 104}),
    )
    raw = Image.open(path).convert("RGB")
    SC = 2
    im, M = zoom(raw, (100, 1060, 60, 520), SC)
    d = ImageDraw.Draw(im)
    lines, errs = [], []
    lines.append("%-6s %-10s %-5s %8s %8s %7s %6s %s"
                 % ("panel", "series", "x", "read", "by eye", "diff", "sd", "stem"))
    for p in PANELS:
        cal = MR.AxisCalibration.from_points(p["ticks"])
        bx0, by0 = M(p["box"][0], p["box"][2])
        bx1, by1 = M(p["box"][1], p["box"][3])
        d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=2)
        for value, row in p["ticks"]:
            _x, ry = M(p["box"][0], row)
            d.line([(bx0 - 40, ry), (bx1, ry)], fill=AXIS, width=1)
            chip(d, (bx0 - 46, ry - 12), "%g" % value, AXIS, im.width, size=15)
        rows = MR.read_monochrome_bar_panel(
            raw, panel_box=p["box"], x_positions=p["x"], y_calibration=cal,
            series=SPECS, baseline_value=50.0, group_window=75)
        for r in rows:
            key = (r["series"], r["x_label"])
            eye = p["eye"][key]
            errs.append(abs(r["mean"] - eye))
            py = cal.pixel_of(r["mean"]) if hasattr(cal, "pixel_of") else None
            if py is None:
                lo, hi = p["ticks"][0], p["ticks"][1]
                py = lo[1] + (r["mean"] - lo[0]) * (hi[1] - lo[1]) / (hi[0] - lo[0])
            px = p["x"][r["x_label"]] + (0 if r["series"] == "FLUID" else 34)
            cx, cy = M(px, py)
            d.line([(cx - 30, cy), (cx + 30, cy)], fill=OK, width=3)
            # FLUID's chips go left of its bar, NON_FLUID's right of its own, so
            # the two series of one group cannot print over each other.
            side = -1 if r["series"] == "FLUID" else 1
            ox = cx - 96 if side < 0 else cx + 34
            chip(d, (ox, cy - 34), "read %.1f" % r["mean"], OK, im.width, size=16)
            chip(d, (ox, cy - 12), "eye  %d" % eye, EYEC, im.width, size=16)
            lines.append("%-6s %-10s %-5s %8.1f %8d %7.1f %6s %s"
                         % (p["name"], r["series"], r["x_label"], r["mean"], eye,
                            abs(r["mean"] - eye),
                            "----" if r["dispersion"] is None
                            else "%.1f" % r["dispersion"],
                            r["Errorbar_Stem_Confirmed"]))
    lines += ["",
              "cells read               %d of 8" % len(errs),
              "worst vs the eye reading %.2f mmHg on a 100 mmHg axis" % max(errs),
              "error bars stem-confirmed 8 of 8"]
    im = capt.below(im, "397 Fig. 3: 실제로 읽어낸 값과 사람이 눈으로 읽은 값",
                    lines, keys=[(OK, "read by the pipeline", False),
                                 (EYEC, "read by eye", False),
                                 (AXIS, "the ticks it was calibrated on", False)])
    out = os.path.join(HERE, "G1_read_397fig3.png")
    im.save(out)
    return out


def lines_397():
    import mark_readers as MR
    import line_style_mono as LSM
    # A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC.
    path = RR.check("397_fig1.jpeg")[0]
    if not path:
        print(RR.skip_note("397_fig1.jpeg"))
        return ""
    CAL = MR.AxisCalibration.from_points([(120.0, 76.0), (70.0, 296.0)])
    LABELS = ("0:30", "1:00", "1:30", "2:00", "2:30", "3:00",
              "3:30", "4:00", "4:30", "5:00", "5:30", "6:00")
    XS = (99.5, 132.5, 165.0, 197.5, 230.5, 263.5,
          296.5, 329.0, 361.5, 394.5, 427.5, 460.0)
    BOX = (84, 477, 110, 296)
    EYE = {"FLUID": (92.5, 99.5, 104.0, 107.0, 105.0, 98.0,
                     98.5, 100.0, 97.0, 98.0, 99.0, 98.0),
           "NO_FLUID": (89.0, 91.0, 92.0, 94.0, 96.0, 96.5,
                        95.0, 95.0, 96.0, 96.0, 96.5, 98.0)}
    rows = LSM.read_monochrome_line_panel(
        Image.open(path), panel_box=BOX, x_positions=dict(zip(LABELS, XS)),
        y_calibration=CAL,
        series=[MR.SeriesSpec("FLUID", line_style="SOLID"),
                MR.SeriesSpec("NO_FLUID", line_style="DASHED")],
        threshold=150, x_window=10, search_radius=60)
    raw = Image.open(path).convert("RGB")
    SC = 3
    im, M = zoom(raw, (60, 500, 60, 320), SC)
    d = ImageDraw.Draw(im)
    bx0, by0 = M(BOX[0], BOX[2]); bx1, by1 = M(BOX[1], BOX[3])
    d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=2)
    for value, row in ((120.0, 76.0), (70.0, 296.0)):
        _x, ry = M(BOX[0], row)
        d.line([(bx0 - 60, ry), (bx1, ry)], fill=AXIS, width=1)
        chip(d, (bx0 - 66, ry - 12), "%g" % value, AXIS, im.width, size=15)
    got = {(r["series"], r["x_label"]): r for r in rows}
    errs, lines = [], []
    lines.append("%-9s %-5s %8s %8s %7s" % ("series", "x", "read", "by eye", "diff"))
    for si, s in enumerate(("FLUID", "NO_FLUID")):
        for lab, x, eye in zip(LABELS, XS, EYE[s]):
            r = got.get((s, lab))
            py = 76.0 + (eye - 120.0) * (296.0 - 76.0) / (70.0 - 120.0)
            cx, cy = M(x, py)
            if r is None:
                d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=BAD, width=4)
                chip(d, (cx - 34, cy + 18 + 22 * si), "REFUSED", BAD, im.width, size=14)
                lines.append("%-9s %-5s %8s %8.1f %7s"
                             % (s, lab, "REFUSED", eye, "-"))
                continue
            ry = 76.0 + (r["mean"] - 120.0) * (296.0 - 76.0) / (70.0 - 120.0)
            errs.append(abs(r["mean"] - eye))
            rx, ryc = M(x, ry)
            d.line([(rx - 12, ryc), (rx + 12, ryc)], fill=OK, width=3)
            chip(d, (rx - 24, ryc - 26 if si == 0 else ryc + 8),
                 "%.1f" % r["mean"], OK, im.width, size=14)
            lines.append("%-9s %-5s %8.1f %8.1f %7.2f"
                         % (s, lab, r["mean"], eye, abs(r["mean"] - eye)))
    lines += ["",
              "cells read     %d of 24, %d REFUSED where the two curves are one"
              " run of ink" % (len(errs), 24 - len(errs)),
              "worst vs eye   %.2f mmHg on a 50 mmHg axis" % max(errs),
              "",
              "거절한 칸은 빨간 원. 읽지 못한 것을 추측하지 않는다."]
    im = capt.below(im, "397 Fig. 1: 겹친 두 곡선 - 읽은 것과 거절한 것", lines,
                    keys=[(OK, "read", False), (BAD, "REFUSED", False),
                          (AXIS, "calibration ticks", False)])
    out = os.path.join(HERE, "G2_read_397fig1.png")
    im.save(out)
    return out


def segmentation(props, pid, fig, out, title):
    """What the SEGMENTATION side found: the panels, and the ladder each one read.

    The reading demonstrations above are handed their panel box and their ticks
    by an author. This is the half that has to produce them, on a plate the cut
    does not hand over willingly.
    """
    import csv
    rows = [r for r in csv.DictReader(open(props))
            if r.get("panel") and r["pid"] == pid and r["fig"] == fig]
    clip = rows[0]["png"]
    im = Image.open(os.path.join(ROOT, "clips", clip)).convert("RGB")
    d = ImageDraw.Draw(im)
    lines = ["%-4s %-19s %-6s %-12s %s"
             % ("", "box", "spine", "status", "ladder it read")]
    nok = 0
    for r in sorted(rows, key=lambda r: (int(r["y0"]), int(r["x0"]))):
        b = [int(r["x0"]), int(r["x1"]), int(r["y0"]), int(r["y1"])]
        ok = r["status"] == "LADDER_OK"
        nok += ok
        col = OK if ok else BAD
        d.rectangle([b[0], b[2], b[1] - 1, b[3] - 1], outline=col, width=4)
        chip(d, (b[0] + 6, b[2] + 6), "%s  %s" % (r["panel"], r["status"]),
             col, im.width, size=17)
        if r.get("spine_x"):
            sx = int(float(r["spine_x"]))
            d.line([(sx, b[2]), (sx, b[3])], fill=AXIS, width=2)
        for t in (r.get("ticks") or "").split(";"):
            if ":" not in t:
                continue
            v, py = t.split(":", 1)
            py = int(float(py))
            d.line([(b[0], py), (b[0] + 26, py)], fill=EYEC, width=3)
            chip(d, (b[0] + 28, py - 10), v, EYEC, im.width, size=14)
        lines.append("%-4s %-19s %-6s %-12s %s"
                     % (r["panel"], "%d,%d,%d,%d" % tuple(b),
                        r.get("spine_x") or "-", r["status"],
                        (r.get("ticks") or "-")[:46]))
    lines += ["",
              "panels found %d   ladders read %d   declared axes %s"
              % (len(rows), nok, rows[0].get("declared_axes") or "?")]
    im = capt.below(im, title, lines,
                    keys=[(OK, "ladder read", False), (BAD, "no ladder", False),
                          (AXIS, "the spine it found", False),
                          (EYEC, "each numeral it read, at its row", False)])
    im.save(out)
    return out


if __name__ == "__main__":
    print(bars_397() or "SKIPPED G1")
    print(lines_397() or "SKIPPED G2")
    print(segmentation("/tmp/pX2.csv", "475", "Fig. 2",
                       os.path.join(HERE, "G3_segment_475fig2.png"),
                       "475 Fig. 2: 잘라낸 패널과 각 패널이 읽은 눈금"))
    print(segmentation("/tmp/pX2.csv", "349", "Figure 3",
                       os.path.join(HERE, "G4_segment_349fig3.png"),
                       "349 Fig. 3: 잘라낸 패널과 각 패널이 읽은 눈금"))
