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
    """One record per declared bar of one panel.

    Row coordinates come in two frames and both are named in every field that
    carries one. `*_row_panel` counts from the top of the panel BOX, which is
    what every array in this file is sliced to; `*_px_image` counts from the top
    of the page, which is what an axis calibration takes. Publication 127's
    panels start at page rows 620, 1580 and 2510, so a panel row handed to a
    calibration is out by that much: the error bar drawn 25 px above a bar top
    reported a dispersion of 142 units instead of 8.3.
    """
    gray = _gray(spec["path"])
    box = spec["box"]
    x0, x1, y0, y1 = map(int, box)
    # Calibration first, because the stroke is the thickness of the rule at the
    # BASELINE and the baseline is where the calibration says the zero is.
    cal = MR.AxisCalibration.from_points([tuple(t) for t in spec["ticks"]])
    zero = int(round(cal.value_to_pixel(spec.get("baseline", 0.0)))) - y0
    scale = stroke_scale(gray, box, baseline_row=zero)
    fills = spec["fills"]
    records = []
    if not scale.ok:
        return [dict(figure=spec["tag"], group=None, stroke=scale.as_dict(),
                     error="STROKE_SCALE_UNRESOLVED")]
    stroke = scale.value_px
    figure_id = spec.get("figure_id", spec["tag"])
    for label, gx in spec["anchors"].items():
        gw = spec["group_window"]
        window = (max(x0, int(gx) - gw), min(x1, int(gx) + gw + 1))
        # Direction is measured, not declared: whichever side of the baseline
        # carries seed support is the side the bars are on.
        support = {}
        for candidate in ("UP", "DOWN"):
            segs, pers = seed_support(gray, box, zero, stroke, window,
                                      direction=candidate)
            support[candidate] = (sum(len(g) for g in segs), segs, pers)
        (up_total, up_segs, up_pers) = support["UP"]
        (down_total, down_segs, down_pers) = support["DOWN"]
        # Nothing on either side of the baseline. Falling through to the tie
        # test does not catch this - `min(0, 0) > 0` is false - so the group
        # went on to footprint an empty segment list, got no footprints back,
        # and DISAPPEARED: no record, no error, and a panel that quietly
        # reported fewer bars than it declared.
        if max(up_total, down_total) == 0:
            records.append(dict(figure=spec["tag"], group=label,
                                error="NO_SEED_SUPPORT",
                                up_support=0, down_support=0,
                                window=[int(window[0]), int(window[1])]))
            continue
        # A tie is not UP. Checking UP first and only replacing on a strictly
        # greater total meant an equal split - possible on a very short bar, or
        # on baseline noise - silently declared the bars upward.
        margin = max(2 * stroke, int(round(0.10 * max(up_total, down_total))))
        if abs(up_total - down_total) <= margin and min(up_total, down_total) > 0:
            records.append(dict(figure=spec["tag"], group=label,
                                error="BAR_DIRECTION_UNRESOLVED",
                                up_support=up_total, down_support=down_total,
                                margin=margin))
            continue
        direction = "UP" if up_total >= down_total else "DOWN"
        segments = up_segs if direction == "UP" else down_segs
        persistence = up_pers if direction == "UP" else down_pers
        # Does the group run off the end of the window it was given? If the
        # outermost column of the window is itself seeded, the bar there has no
        # measured right (or left) edge - and `footprints_from_seed` divides the
        # span it CAN see by the declared bar count, so a window 22 px short on
        # publication 127 moved every boundary and put the neighbouring bar's
        # right stroke inside the last bar's footprint. The last bar then traced
        # its neighbour's outline and read 3.37 where the bar was 1.5.
        #
        # An anchor that is off-centre is a geometry error and this is where it
        # becomes visible, so it must refuse rather than widen the window
        # itself: widening would move the boundary again with nothing to check
        # it against.
        clipped = [side for side, v in (("LEFT", persistence[0]),
                                        ("RIGHT", persistence[-1]))
                   if v >= SEED_SUPPORT]
        if clipped:
            records.append(dict(figure=spec["tag"], group=label,
                                error="GROUP_WINDOW_CLIPPED", clipped_at=clipped,
                                direction=direction,
                                window=[int(window[0]), int(window[1])],
                                seed_extent=[int(segments[0][0]),
                                             int(segments[-1][-1])] if segments else None))
            continue
        prints, bounds = footprints_from_seed(segments, len(fills))
        for k, fp in enumerate(prints):
            rec = dict(figure=spec["tag"], figure_id=figure_id, group=label,
                       slot=k, declared=fills[k], stroke_px=stroke,
                       direction=direction,
                       # What the group is SUPPOSED to hold, on every record.
                       # Without it a group is only knowable from the records
                       # that came back, so a record lost to a defect takes its
                       # declaration with it and the remainder looks complete.
                       declared_group_size=len(fills),
                       declared_group_patterns=sorted(fills))
            if fp is None:
                rec["error"] = "NO_SEED_SUPPORT"
                records.append(rec)
                continue
            # The bar end and the footprint, refined against each other.
            fp0 = fp
            fp, edge, method, dropped, refusal, detail = refine_footprint(
                fp0,
                lambda f: trace_extent(gray, box, window, f, zero, stroke,
                                       direction=direction),
                lambda f, e: trim_to_own_bar(gray, box, window, f, e, zero,
                                             stroke, direction=direction))
            if dropped:
                rec["trimmed_columns"] = dropped
                rec["provisional_footprint"] = [int(fp0[0]), int(fp0[1])]
            if refusal:
                rec["error"] = refusal
                rec.update(detail)
                records.append(rec)
                continue
            remote = remote_support(gray, box, window, fp, edge, zero, stroke,
                                    direction=direction)
            body = [r for r in remote if r["kind"] == "BODY_CONTINUATION"]
            unresolved = [r for r in remote
                          if r["kind"] == "UNRESOLVED_REMOTE_SUPPORT"]
            caps = [r for r in remote if r["kind"] == "ERRORBAR_CAP"]
            cap_row = caps[0]["centre_row_panel"] if caps else None
            rec.update(slot_bounds=(list(bounds[k]) if bounds[k] else None),
                       # Both frames, both named. The bare `cap_px` this
                       # replaced held a PANEL row under a name the production
                       # reader uses for a PAGE row, and the production reader
                       # feeds it straight to a calibration.
                       edge_row_panel=round(edge, 1),
                       edge_px_image=round(y0 + edge, 1),
                       cap_row_panel=cap_row,
                       cap_px_image=(None if cap_row is None else y0 + cap_row),
                       support=method, remote=remote,
                       # Only a body continuation says the walk was wrong.
                       contradiction_px=(min(r["distance_px"] for r in body)
                                         if body else 0),
                       footprint=[int(fp[0]), int(fp[1])],
                       footprint_width=int(fp[1] - fp[0] + 1),
                       seed_segments=len([s for s in segments
                                          if fp[0] <= s[0] <= fp[1]]))
            # Fail closed, and closed means the number does not exist. The
            # previous version put the classification in the record and then
            # carried on to write `value` and a full texture block anyway, so a
            # bar whose top was in doubt entered the fill-identity step as a
            # clean prototype sample - which is the one place where a wrong
            # number does the most damage, because it becomes the definition
            # every other bar is matched against.
            #
            # BODY_CONTINUATION means the top is known to be wrong.
            # UNRESOLVED_REMOTE_SUPPORT means it is not known to be right, which
            # for a prototype is the same thing.
            reason = ("BAR_EXTENT_UNRESOLVED" if body else
                      "REMOTE_SUPPORT_UNRESOLVED" if unresolved else "")
            if reason:
                rec["error"] = reason
                rec["provisional_value"] = round(cal.pixel_to_value(y0 + edge), 3)
                records.append(rec)
                continue
            rec["value"] = round(cal.pixel_to_value(y0 + edge), 3)
            # The dispersion the cap implies, computed HERE rather than left to
            # a caller, because computing it is what proves the two rows are in
            # the same frame. A cap row in panel coordinates against a mean in
            # page coordinates produces a number - it just is not a dispersion.
            if cap_row is not None:
                rec["dispersion"] = round(
                    abs(cal.pixel_to_value(y0 + cap_row) - rec["value"]), 3)
            tex = texture(gray, box, window, fp, edge, zero, stroke,
                          direction=direction)
            if tex is None:
                rec["error"] = "BAR_TOO_SMALL_TO_SAMPLE"
            else:
                rec.update(tex)
            # Whether a fill was SAMPLED, which is not whether the series was
            # IDENTIFIED. This function measures one panel and identity is
            # figure-local, so nothing here can name a series; the two were one
            # field called `identity_status` and the forward tests were counting
            # samples while saying "identities". `fill_identities_by_figure`
            # sets `identity_status` and `resolved_fill_pattern`.
            #
            # `declared` is the spec's DECLARATION, to be checked against what
            # the fill measures - never an identification. Calling a bar OPEN
            # because it is the first slot is identifying a series by position.
            rec["fill_sample_status"] = ("MEASURED" if tex is not None
                                         else "UNRESOLVED_NO_INTERIOR")
            rec["identity_status"] = "NOT_CALIBRATED"
            records.append(rec)
    return records


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
          % ("figure", "group", "slot", "declared", "dir", "value", "inkmass",
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
                         r.get("declared"), r["error"], prov))
                continue
            cells = " ".join("%.2f/%d" % (r["t%d" % t]["coverage_median_tile"],
                                          r["t%d" % t]["column_segments"])
                             for t in THRESHOLDS)
            print("%-20s %-8s %-4d %-9s %-4s %-7.2f %-7.3f %-16s %s"
                  % (r["figure"], r["group"], r["slot"], r["declared"],
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
