"""What a monochrome bar chart actually looks like, measured rather than assumed.

    python3 measure_mono_bars.py            # print the table
    python3 measure_mono_bars.py --json OUT # and write it

`_FILL_BANDS` and `_INSIDE_MIN_DENSITY` carry a comment saying they were
"measured on a real monochrome figure". They were - on ONE. Publication 127 is
the second, and it disagrees with every one of them: its solid fill reads
0.697-0.737 against a band that starts at 0.72, its stipple rows read 0.10
against a floor of 0.15, and its open bar's right stroke does not fall in the
last two columns of the slot the reader gave it.

This script is the evidence a replacement has to be justified by. It reports,
for every declared bar of every real monochrome figure in the package, the
quantities a reader could key on - and it deliberately reports them in units
that are RATIOS of something else in the same figure, because that is the only
kind of number that can survive a different journal, a different DPI and a
different scan.

It reads figures; it decides nothing. Nothing in the package imports it.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mark_readers as MR                                          # noqa: E402

try:
    import cv2
except ImportError:                                                # pragma: no cover
    cv2 = None


def _dark(path, threshold=128):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    if cv2 is not None:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    else:                                                          # pragma: no cover
        gray = rgb.mean(axis=2)
    return gray < threshold


def _runs(indices, gap=1):
    out, cur = [], []
    for i in indices:
        if cur and i - cur[-1] > gap:
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def stroke_scale(dark, box):
    """The figure's own line weight, in pixels, from its baseline rule.

    Every threshold this reader needs is a multiple of the thickness of the
    lines the figure is drawn with. That is a property of the raster - the DPI
    it was rendered at, the weight the journal draws axes with - and it is
    measurable in the panel itself, which is what makes it usable in place of a
    constant somebody typed after looking at one publication.
    """
    x0, x1, y0, y1 = map(int, box)
    strip = dark[y0:y1, x0:x1]
    wide = np.where(strip.sum(axis=1) > 0.5 * strip.shape[1])[0]
    if not len(wide):
        return 1
    return max(1, max(len(g) for g in _runs(list(wide))))


def slot_report(dark, box, ticks, anchors, fills, group_window, baseline=0.0):
    """One record per declared bar: geometry, then texture, all in ratios."""
    x0, x1, y0, y1 = map(int, box)
    cal = MR.AxisCalibration.from_points(ticks)
    zero = int(round(cal.value_to_pixel(baseline))) - y0
    thick = stroke_scale(dark, box)
    n = len(fills)
    records = []
    for label, gx in anchors.items():
        xa, xb = max(x0, gx - group_window), min(x1, gx + group_window + 1)
        band = dark[y0:y1, xa:xb]
        column = band.sum(axis=0)
        idx = [i for i, v in enumerate(column) if v > 0.06 * band.shape[0]]
        if not idx:
            continue
        lo, hi = idx[0], idx[-1]
        pitch = (hi - lo + 1) / float(n)
        for k in range(n):
            sa = int(round(lo + k * pitch)) + 2
            sb = int(round(lo + (k + 1) * pitch)) - 2
            slot = band[:, sa:sb]
            width = sb - sa
            # The seed band sits ABOVE the baseline rule, not on it. Starting at
            # the baseline row means every column of every slot is dark because
            # the rule itself is dark, and the footprint comes out as the whole
            # slot for a bar that is mostly white.
            top = max(0, zero - thick - 3 * thick)
            bottom = max(1, zero - thick)
            seed = slot[top:bottom]
            persistence = seed.mean(axis=0) if seed.size else np.zeros(width)
            keep = [i for i, v in enumerate(persistence) if v >= 0.25]
            segs = [g for g in _runs(keep, gap=max(2, thick))
                    if len(g) >= max(2, thick // 2)]
            record = dict(group=label, slot=k, declared=fills[k], width=width,
                          stroke_px=thick,
                          seed_segments=[(int(g[0]), int(g[-1]), len(g)) for g in segs])
            if segs:
                fx0, fx1 = int(segs[0][0]), int(segs[-1][-1])
                record.update(footprint=(fx0, fx1), footprint_width=fx1 - fx0 + 1,
                              # How much of the footprint the seed band actually
                              # inks. An open bar's two strokes cover a few per
                              # cent; a solid fill covers all of it. This is the
                              # same question `_FILL_BANDS` asks, asked where the
                              # bar is certainly present.
                              seed_coverage=round(float(
                                  persistence[fx0:fx1 + 1].mean()), 4),
                              seed_segment_count=len(segs))
            records.append(record)
    return records


def figures():
    """Every real monochrome bar figure in the package, with known geometry."""
    out = [
        dict(tag="397_fig3_P3_MEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=(118, 480, 90, 470), ticks=[(150.0, 101.0), (50.0, 465.0)],
             anchors={"PRE": 187, "POST": 390}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0),
        dict(tag="mono_fixture", path=os.path.join(HERE, "mono_bar_fixture.png"),
             box=None, ticks=None, anchors=None, fills=None, group_window=None),
    ]
    return [f for f in out if f["box"] and os.path.exists(f["path"])]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", default="")
    ap.add_argument("--extra", default="",
                    help="JSON file of additional figure geometries to measure")
    args = ap.parse_args(argv)

    specs = figures()
    if args.extra:
        with open(args.extra, encoding="utf-8") as fh:
            for spec in json.load(fh):
                spec["anchors"] = {k: int(v) for k, v in spec["anchors"].items()}
                spec["ticks"] = [tuple(t) for t in spec["ticks"]]
                specs.append(spec)

    everything = []
    for spec in specs:
        if not os.path.exists(spec["path"]):
            print("SKIP %s: %s is not here" % (spec["tag"], spec["path"]))
            continue
        dark = _dark(spec["path"])
        rows = slot_report(dark, spec["box"], spec["ticks"], spec["anchors"],
                           spec["fills"], spec["group_window"],
                           baseline=spec.get("baseline", 0.0))
        for r in rows:
            r["figure"] = spec["tag"]
            everything.append(r)
            print("%-22s %-9s slot%d %-8s w=%3d stroke=%d foot=%s cover=%s segs=%d"
                  % (spec["tag"], r["group"], r["slot"], r["declared"], r["width"],
                     r["stroke_px"], r.get("footprint"), r.get("seed_coverage"),
                     r.get("seed_segment_count", 0)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(everything, fh, indent=1)
        print("\nwrote %s (%d records)" % (args.json, len(everything)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
