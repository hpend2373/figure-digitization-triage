"""Independent second reading of ID 323 Figure 1.

Deliberately NOT a call into bar_reader. The frozen fixture locks in whatever
bar_reader currently produces; that proves stability, not accuracy. This module
re-reads the same raster by a different route so the two can be compared:

  bar_reader          per-row dark-width profile over the whole bar, take the
                      run wider than half the bar, use its centre
  this module         per-column topmost dark pixel inside the central 60% of
                      the bar, take the median, then add half the outline
                      thickness measured on that same bar

Different primitive (column scan vs row profile), different statistic (median vs
run centre), different way of locating the stroke centre. Agreement between them
is evidence about the figure; agreement of a fixture with itself is not.

    python crosscheck_id323.py     # prints the comparison, exit 1 on disagreement
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# Tolerances in PIXELS, not units: the panels have different scales, and what is
# being asserted is that two implementations locate the same pixel row. A
# dispersion is the difference of two readings, so it carries twice the error.
TOL_MEAN_PX = 1.0
TOL_DISP_PX = 2.5


def load():
    import raster_root as RR
    path, note = RR.check("fixtures/id323_fig1.jpeg")
    if not path:
        print(RR.skip_note("fixtures/id323_fig1.jpeg"))
        raise SystemExit(0)
    print(note)
    cfg = json.load(open(os.path.join(HERE, "fixtures/id323_fig1_panels.json")))
    exp = json.load(open(os.path.join(HERE, "fixtures/id323_fig1_expected.json")))
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    return cfg, exp, a


def masks(a):
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return ((B - R > 50) & (B - G > 40) & (B > 110),
            (R - G > 60) & (R - B > 60) & (R > 110),
            a.mean(axis=2) < 110)


def tick_rows(dark, box, n):
    x0, x1, y0, y1 = box
    sub = dark[y0:y1, x0:x1]
    ax = min(x0 + i for i, v in enumerate(sub.sum(axis=0)) if v > 0.6 * sub.shape[0])
    sl = dark[y0:y1, max(0, ax - 20):ax - 2]
    hits = [y0 + i for i, v in enumerate(sl) if v.sum() >= 2]
    out, cur = [], []
    for h in hits:
        if cur and h - cur[-1] <= 4:
            cur.append(h)
        else:
            if cur:
                out.append((cur[0] + cur[-1]) / 2.0)
            cur = [h]
    if cur:
        out.append((cur[0] + cur[-1]) / 2.0)
    assert len(out) == n, "%d ticks, expected %d" % (len(out), n)
    return out


def read(a, dark, colour, box, y2v, zero_row=None):
    """Column-scan reading of one colour's bars in one panel.

    zero_row: pixel row of the baseline. Given it, direction is decided per bar
    the same way bar_reader decides it - by which end is further from the
    baseline - but reached through this module's own column scan. Without it the
    reader assumes bars grow upward, which silently mis-reads a change-from-zero
    plot by the full height of the bar.
    """
    x0, x1, y0, y1 = box
    m = np.zeros_like(colour)
    m[y0:y1, x0:x1] = True
    c = colour & m
    xs = [x for x in range(x0, x1) if c[:, x].any()]
    groups, cur = [], []
    for x in xs:
        if cur and x - cur[-1] <= 3:
            cur.append(x)
        else:
            if len(cur) >= 15:
                groups.append(cur)
            cur = [x]
    if len(cur) >= 15:
        groups.append(cur)

    out = []
    for gp in groups:
        lo, hi = gp[0], gp[-1]
        inset = int(round((hi - lo) * 0.2))
        xcen = (lo + hi) // 2
        # Skip the centre columns: the whisker stem lives there, and an upward
        # walk from the fill edge runs straight through it onto the cap. This is
        # the same trap the row-profile reader avoids by requiring HALF the bar
        # width - a column scan has to exclude the stem explicitly.
        core = [x for x in range(lo + inset, hi - inset + 1) if abs(x - xcen) > 6]
        allfill = np.where(c[:, lo:hi + 1].any(axis=1))[0]
        if not len(allfill):
            continue
        down = (zero_row is not None
                and abs(float(allfill.max()) - zero_row) > abs(float(allfill.min()) - zero_row))
        step = 1 if down else -1
        tops, thick = [], []
        for x in core:
            fill = np.where(c[:, x])[0]
            if not len(fill):
                continue
            ftop = int(fill.max() if down else fill.min())
            # CONTIGUOUS walk away from the baseline. A filter instead of a walk
            # swallows whatever sits a few px beyond - a significance bracket -
            # and reports the bar end 7 px too far out.
            y = ftop + step
            stroke = []
            while y0 <= y < y1 and dark[y, x]:
                stroke.append(y)
                y += step
            if not stroke:
                continue
            tops.append(max(stroke) if down else min(stroke))
            thick.append(len(stroke))
        if not tops:
            continue
        t = float(np.median(tops))
        w = float(np.median(thick))
        top_centre = t - step * (w - 1) / 2.0

        xc = (lo + hi) // 2
        edge = int(top_centre)
        rng = (range(edge + 2, min(y1, edge + 90)) if down
               else range(max(y0, edge - 90), edge - 1))
        stem = [y for y in rng if dark[y, xc - 2:xc + 3].sum() >= 3]
        cap = None
        if stem:
            runs_, cur2 = [], []
            for y in stem:
                if cur2 and y - cur2[-1] <= 2:
                    cur2.append(y)
                else:
                    if cur2:
                        runs_.append(cur2)
                    cur2 = [y]
            if cur2:
                runs_.append(cur2)
            touching = [r for r in runs_
                        if ((r[0] <= edge + 5) if down else (r[-1] >= edge - 5))]
            if touching:
                s = touching[0] if down else touching[-1]
                # Same DEFINITION as bar_reader - the centre of the contiguous
                # cap stroke - reached by a different route. Independence belongs
                # in the primitive, not in what is being measured: a filter
                # without the contiguity break silently absorbed rows further
                # down and shifted the centre by up to 3 px.
                far = s[-1] if down else s[0]
                capw = []
                for n in range(8):
                    y = far - step * n
                    if not (y0 <= y < y1):
                        break
                    if dark[y, lo:hi + 1].sum() >= 0.10 * (hi - lo + 1):
                        capw.append(y)
                    elif capw:
                        break
                cap = (capw[0] + capw[-1]) / 2.0 if capw else float(far)
        out.append(dict(x=xc, mean=y2v(top_centre),
                        disp=None if cap is None else y2v(cap) - y2v(top_centre)))
    out.sort(key=lambda d: d["x"])
    return out


def main():
    cfg, exp, a = load()
    blue, red, dark = masks(a)
    got = {}
    units_per_px = {}
    for p in cfg["panels"]:
        cen = tick_rows(dark, p["box"], len(p["tick_values"]))
        vs = np.array(p["tick_values"], dtype=float)
        ys = np.array(cen, dtype=float)
        k, b = np.polyfit(ys, vs, 1)
        y2v = lambda py: float(k * py + b)          # noqa: E731
        units_per_px[p["name"]] = abs(k)
        for sname, col in (("SUPINE", blue), ("ORTHOSTASIS", red)):
            for i, r in enumerate(read(a, dark, col, tuple(p["box"]), y2v)):
                got[(p["name"], sname, cfg["sessions"][i])] = r

    dm = dd = 0.0
    n = 0
    worst = None
    for row in exp["values"]:
        key = (row["panel"], row["series"], row["session"])
        r = got.get(key)
        if r is None:
            print("  MISSING", key)
            return 1
        upx = units_per_px[row["panel"]]
        e = abs(r["mean"] - row["mean"]) / upx
        if e > dm:
            dm, worst = e, key
        if row["dispersion"] is not None and r["disp"] is not None:
            dd = max(dd, abs(r["disp"] - row["dispersion"]) / upx)
        n += 1
    print("independent re-reading of ID 323 Figure 1")
    print("  bars compared        : %d" % n)
    print("  max |delta mean|     : %.2f px  (worst %s)" % (dm, worst))
    print("  max |delta dispersion|: %.2f px" % dd)
    ok = dm <= TOL_MEAN_PX and dd <= TOL_DISP_PX
    print("  verdict              : %s (tolerances %.1f / %.1f px)"
          % ("AGREE" if ok else "DISAGREE", TOL_MEAN_PX, TOL_DISP_PX))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
