"""What a monochrome bar chart actually looks like, measured rather than assumed.

    python3 measure_mono_bars.py                  # print the table
    python3 measure_mono_bars.py --json OUT.json  # and write it

The measurement lives in `mono_bar_geometry`, which the production reader
imports too. This file is the driver: the spec format, the corpus of panels the
package can reach, and the table. It reads figures and decides nothing.

`_FILL_BANDS` and `_INSIDE_MIN_DENSITY` in `mark_readers.py` carry a comment
saying they were "measured on a real monochrome figure". They were - on ONE.
Publication 127 is the second, and it does not fit them: under the production
reader's binary density rule its solid bars read about 0.70, which is neither
SOLID (0.72 and up) nor HATCHED (up to 0.60) but the dead zone between the two.
What this records is `ink_mass`, threshold-free and NOT the same feature as that
binary density; the two must not be compared as though they were.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mark_readers as MR                                          # noqa: E402
import mono_bar_geometry as G                                      # noqa: E402
from mono_bar_geometry import (                                    # noqa: E402,F401
    FILL_VOCABULARY, IDENTITY_STATES, REMOTE_KINDS, SEED_DEPTH_STROKES,
    SEED_SUPPORT, THRESHOLDS, StrokeScale, _runs, fill_identities_by_figure,
    fill_identity, footprints_from_seed, refine_footprint, remote_support,
    rule_edge, seed_support, stem_band, stroke_scale, texture, trace_extent,
    trim_to_own_bar,
)


def _gray(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.uint8)
    return G._gray_from_rgb(rgb)


def measure_panel(spec):
    """`geometry_rows` for one entry of the diagnostic spec format.

    The rows come back with `spec_fill` attached: the pattern THIS SPEC lists
    for that slot, which is a human's left-to-right reading of the figure and is
    fixture truth, not a measurement and not an input to one. It is attached
    here, after the measurement, and deliberately not by `geometry_rows`: a
    per-slot fill inside the anonymous grain is a series named by where the bar
    sits, and it made the record stream depend on the order the spec listed the
    fills in. `test_measure_mono_bars` pins both - the rows are identical under
    any permutation of `fills`, and scrambling `spec_fill` afterwards changes no
    identity - so this field cannot quietly become an input again.

    What it is FOR is the one check the measurement cannot make on itself:
    whether `resolved_fill_pattern`, which came from ink and structure, agrees
    with what a person reading the printed figure says is there.
    """
    rows = G.geometry_rows(
        _gray(spec["path"]), spec["box"],
        MR.AxisCalibration.from_points([tuple(t) for t in spec["ticks"]]),
        spec["anchors"], spec["fills"], spec["group_window"],
        baseline=spec.get("baseline", 0.0), panel_id=spec["tag"],
        figure_id=spec.get("figure_id", spec["tag"]))
    for rec in rows:
        if rec.get("slot") is not None and rec["slot"] < len(spec["fills"]):
            rec["spec_fill"] = spec["fills"][rec["slot"]]
    return rows


def builtin_specs():
    """Every real or synthetic monochrome bar panel the package ships."""
    specs = [
        dict(tag="397_fig3_P3_MEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=[118, 480, 90, 470], ticks=[[150.0, 101.0], [50.0, 465.0]],
             anchors={"PRE": 187, "POST": 390}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0, figure_id="397_fig3"),
        # The second panel of the SAME figure, four pixels of axis apart from
        # the first. Sharing one calibration between them put this one's
        # baseline below its own bars and returned nothing for all four of its
        # cells, which is why the production reader takes geometry per panel -
        # and why measuring only the first panel here would have left the
        # prototype's version of that mistake undetected.
        dict(tag="397_fig3_P3_WOMEN", path=os.path.join(HERE, "397_fig3.jpeg"),
             box=[620, 1010, 88, 466], ticks=[[150.0, 95.0], [50.0, 460.0]],
             anchors={"PRE": 720, "POST": 920}, fills=["SOLID", "HATCHED"],
             group_window=75, baseline=50.0, figure_id="397_fig3"),
    ]
    truth = os.path.join(HERE, "mono_bar_fixture_truth.json")
    if os.path.exists(truth):
        with open(truth, encoding="utf-8") as fh:
            cfg = json.load(fh)
        specs.append(dict(
            tag="mono_fixture", path=os.path.join(HERE, "mono_bar_fixture.png"),
            box=cfg["panel_box"], ticks=cfg["y_ticks"],
            anchors={g: x for g, x in zip(cfg["groups"], cfg["group_x"])},
            fills=cfg["patterns"], group_window=60, baseline=0.0))
    return [s for s in specs if os.path.exists(s["path"])]


def load_specs(paths, raster_root=""):
    """Extra geometries, each checked against the raster it was measured on."""
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for spec in json.load(fh):
                # Resolved against --raster-root, then the spec's own
                # directory. The spec is versioned and the raster is not, so
                # the spec must not name a directory on the machine it was
                # written on.
                raster = spec["path"]
                if not os.path.isabs(raster):
                    for root in [r for r in (raster_root, os.path.dirname(path)) if r]:
                        candidate = os.path.join(root, raster)
                        if os.path.exists(candidate):
                            raster = candidate
                            break
                spec["path"] = raster
                if not os.path.exists(raster):
                    print("SKIP %s: %s is not on this machine" % (spec["tag"], raster))
                    continue
                want = str(spec.get("raster_sha256", "")).strip().lower()
                if want:
                    with open(raster, "rb") as fh2:
                        got = hashlib.sha256(fh2.read()).hexdigest()
                    if got != want:
                        print("SKIP %s: raster hashes %s..., the spec says %s..."
                              % (spec["tag"], got[:16], want[:16]))
                        continue
                out.append(spec)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", default="")
    ap.add_argument("--extra", action="append", default=[],
                    help="JSON of further panel geometries (repeatable)")
    ap.add_argument("--raster-root", default=os.environ.get("FDT_RASTER_ROOT", ""),
                    help="where the private rasters the geometry specs name live")
    ap.add_argument("--specs-dir", default=os.path.join(HERE, "geometry"),
                    help="directory of versioned *.geometry.json specs")
    args = ap.parse_args(argv)

    specs = builtin_specs()
    if os.path.isdir(args.specs_dir):
        specs += load_specs(sorted(
            os.path.join(args.specs_dir, f) for f in os.listdir(args.specs_dir)
            if f.endswith(".geometry.json")), raster_root=args.raster_root)
    specs += load_specs(args.extra, raster_root=args.raster_root)

    everything = []
    print("%-20s %-8s %-4s %-9s %-4s %-7s %-7s %-16s %s"
          % ("figure", "group", "slot", "spec_fill", "dir", "value", "inkmass",
             "support", "coverage/segments t=96,128,160,192"))
    for spec in specs:
        for r in measure_panel(spec):
            everything.append(r)
            if r.get("error"):
                # The provisional number is printed so the refusal can be
                # audited, and printed in brackets so it cannot be mistaken for
                # a reading. Nothing downstream may read it.
                prov = ("  (value %.2f, no fill)" % r["value"]
                        if "value" in r else
                        "  (provisional %.2f)" % r["provisional_value"]
                        if "provisional_value" in r else "")
                print("%-20s %-8s %-4s %-9s  %s%s"
                      % (r["figure"], r.get("group"), r.get("slot"),
                         r.get("spec_fill"), r["error"], prov))
                continue
            cells = " ".join("%.2f/%d" % (r["t%d" % t]["coverage_median_tile"],
                                          r["t%d" % t]["column_segments"])
                             for t in THRESHOLDS)
            print("%-20s %-8s %-4d %-9s %-4s %-7.2f %-7.3f %-16s %s"
                  % (r["figure"], r["group"], r["slot"], r["spec_fill"],
                     r["direction"], r.get("value", float("nan")), r["ink_mass"],
                     "%s%s" % (r["support"],
                               "" if not r["contradiction_px"]
                               else " !%d" % r["contradiction_px"]), cells))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(everything, fh, indent=1)
        print("\nwrote %s (%d records)" % (args.json, len(everything)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
