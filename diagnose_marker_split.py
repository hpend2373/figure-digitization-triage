# -*- coding: utf-8 -*-
"""The fill axis asked of the whole panel, and asked again inside each shape.

    python3 diagnose_marker_split.py [--out DIR]
    python3 diagnose_marker_split.py --image FILE --box x0,x1,y0,y1 \
        --series 'ID:SHAPE:FILL,...' [--panel NAME] [--out DIR]

IT MEASURES AND CHANGES NOTHING. Every verdict `marker_routing` reaches is
reached by `marker_routing`; this module calls `route`, takes the records it
returns, and computes a SECOND set of numbers beside them - what the fill split
would have been had it been asked of the circles alone and of the triangles
alone. Both verdicts travel on every row, and where they differ the row says so.
Nothing here is imported by the reader, the runner or the finalizer.

## The question it exists to answer

`marker_routing.route` asks two questions of a panel: a SHAPE split over every
mark's third harmonic, and a FILL split over every mark's interior ink. The
second is asked of the whole panel at once - all the circles and all the
triangles in one distribution - and a panel drawing rings, discs, hollow
triangles and solid triangles has FOUR classes in that one set. A hollow
triangle and a hollow circle do not have the same interior ink: a triangle
inscribed in the marker box covers about half of it, so the fill window at its
centroid sees the triangle's own body where a circle's window sees the disc.

If that is true, the global fill distribution is a mixture of two effects and
its "largest gap" can fall between two SHAPES rather than between two FILLS -
in which case relaxing the minimum-cluster rule would not fix it, it would
license the wrong cut. THE FIRST QUESTION IS THE GRAIN, NOT THE CONSTANT, and
this module is what answers it before anything is changed.

## What it writes

    marks.csv    one row per candidate mark: its pixel, its shape score and
                 verdict, its interior ink, the global threshold and margin, the
                 shape group it falls in, that group's own threshold and margin,
                 and the two fill verdicts side by side
    groups.json  per shape group: how many marks, the sorted interior ink, EVERY
                 cut with its low/high counts, threshold, between, within and
                 separation index, the best cut the production floor admits, the
                 best cut an absolute floor of two admits, and a leave-one-out
                 stability count for each

BOTH ARE MACHINE-READABLE ON PURPOSE. A finding that lives only in a printed
table cannot be diffed against the next rendering.

## Publisher figures

`--image` may name a figure this repository does not carry, and the rows this
module writes about one are derived from it. `--out` therefore defaults to a
fresh temporary directory rather than anywhere inside the tree, and a caller
pointing it into the repository is choosing to.
"""
import argparse
import collections
import csv
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np                                                # noqa: E402

import marker_routing as MRT                                      # noqa: E402

#: A mark this module reasons about: `route` decided it was one marker. Marks
#: refused as furniture or as a merged pair are counted and then left out of
#: every distribution, exactly as `route` leaves them out of its own splits.
KEPT_STATUS = "SINGLE_MARKER"

#: The columns `marks.csv` carries, in this order.
MARK_COLUMNS = (
    "Panel", "Rendering", "Mark_Index", "Point_Px_X", "Point_Px_Y",
    "Marker_Scale_Px", "Marker_Validity_Status", "Refusal",
    "Third_Harmonic", "Shape_Split", "Shape_Margin", "Shape_Resolved",
    "Interior_Ink",
    "Global_Fill_Split", "Global_Fill_Index", "Global_Fill_Margin",
    "Global_Fill_Verdict", "Global_Series_ID",
    "Fill_Conditioning_Shape", "Group_N", "Group_Fill_Split",
    "Group_Fill_Index", "Group_Fill_Margin", "Group_Fill_Separates",
    "Conditional_Fill_Verdict", "Conditional_Series_ID",
    "Verdicts_Differ",
)


def cuts(values, floor=2):
    """Every cut of a sorted set that leaves at least `floor` on each side.

    THE TABLE, NOT THE WINNER. `marker_routing._split` returns the best cut its
    own floor admits and nothing about the ones it passed over, so a panel that
    does not separate says False and stops. The whole reason 464 Figure 2 is
    unresolved is a cut `_split` declined to consider, and a verdict that cannot
    name what it declined is not a measurement anybody can act on.
    """
    xs = np.array(sorted(float(v) for v in values), dtype=float)
    out = []
    for cut in range(1, len(xs)):
        lo, hi = xs[:cut], xs[cut:]
        if min(len(lo), len(hi)) < floor:
            continue
        spread = float(lo.std() + hi.std())
        between = float(hi.mean() - lo.mean())
        index = between / spread if spread > 1e-9 else float("inf")
        out.append(dict(low_n=int(len(lo)), high_n=int(len(hi)),
                        threshold=round(float(lo[-1] + hi[0]) / 2.0, 6),
                        between=round(between, 6), within=round(spread, 6),
                        index=round(index, 4)))
    return out


def best(table):
    """The highest-index entry of a cut table, or None for an empty one."""
    return max(table, key=lambda e: e["index"]) if table else None


def production_floor(n):
    """`marker_routing._split`'s own minimum class size, for `n` values."""
    return max(2, n // 4)


def stability(values, floor):
    """How often the best admissible cut survives dropping one value.

    A CUT THAT MOVES WHEN ANY ONE MARK LEAVES IS NOT A CLASS BOUNDARY. Leave
    each value out in turn, re-take the best admissible cut of what remains, and
    count how many of those agree with the full set's about WHICH SIDE each
    surviving value falls on. A boundary between two real clusters is unmoved by
    losing a member; one sitting inside a single blurred cluster jumps.

    Returns `(agreeing, tried, worst_index_seen)`. `tried` is the number of
    leave-one-out fits that produced a cut at all - at small n the floor can
    refuse every cut, and a fit that did not happen is not an agreement.
    """
    xs = sorted(float(v) for v in values)
    whole = best(cuts(xs, floor))
    if whole is None:
        return 0, 0, None
    agree, tried, worst = 0, 0, None
    for drop in range(len(xs)):
        rest = xs[:drop] + xs[drop + 1:]
        got = best(cuts(rest, max(2, len(rest) // 4) if floor > 2 else 2))
        if got is None:
            continue
        tried += 1
        worst = got["index"] if worst is None else min(worst, got["index"])
        if all((v >= whole["threshold"]) == (v >= got["threshold"])
               for v in rest):
            agree += 1
    return agree, tried, worst


def declared_fills_by_shape(series):
    """{SHAPE: sorted fills declared for it}, from a panel's declaration.

    THE DECLARATION IS NOT THE MEASUREMENT and this is the only thing taken from
    it: which fills a shape is even allowed to have. A shape declared with one
    fill has nothing to split, and a shape declared with two has a question the
    ink can answer.
    """
    by = collections.defaultdict(set)
    for spec in series:
        shape = (getattr(spec, "marker", None) or spec.get("shape") or "").upper()
        fill = (getattr(spec, "fill", None) or spec.get("fill") or "").upper()
        by[shape].add(fill)
    return {k: sorted(v) for k, v in sorted(by.items())}


def declared_names(series):
    """{(SHAPE, FILL): Series_ID}, the same mapping `route` builds."""
    out = {}
    for spec in series:
        shape = (getattr(spec, "marker", None) or spec.get("shape") or "").upper()
        fill = (getattr(spec, "fill", None) or spec.get("fill") or "").upper()
        name = getattr(spec, "name", None) or spec.get("id")
        out[(shape, fill)] = name
    return out


def _index_of(split):
    """The separation index behind a `Split`, which the namedtuple stores apart."""
    between, within = float(split["between"]), float(split["within"])
    return between / within if within else (float("inf") if between else 0.0)


def groups(records, series):
    """Per resolved shape: its marks, its cut table and its two best cuts.

    A MARK WHOSE SHAPE IS UNRESOLVED IS IN NO GROUP. That is the point of asking
    the fill question inside a shape: a mark that does not know which shape it is
    cannot be asked which fill it is either, and it appears here only in the
    `unresolved_shape` count.
    """
    fills = declared_fills_by_shape(series)
    kept = [r for r in records if r.get("Marker_Validity_Status") == KEPT_STATUS]
    out = {}
    for shape in sorted(fills):
        mine = [r for r in kept if r.get("shape") == shape]
        values = [float(r["interior_ink"]) for r in mine]
        floor = production_floor(len(values))
        table = cuts(values, 2)
        adm = best([e for e in table
                    if min(e["low_n"], e["high_n"]) >= floor])
        any_best = best(table)
        agree, tried, worst = stability(values, floor) if len(values) >= 4 else (0, 0, None)
        split = MRT._split(values) if len(values) >= 4 else MRT.Split(None, 0.0, 0.0, False)
        out[shape] = dict(
            declared_fills=fills[shape],
            n=len(mine),
            interior_ink=sorted(round(v, 4) for v in values),
            minimum_cluster=floor,
            cuts=table,
            best_admissible=adm,
            best_at_floor_two=any_best,
            production_split=dict(split._asdict()),
            production_index=round(_index_of(dict(split._asdict())), 4),
            leave_one_out_agreeing=agree,
            leave_one_out_tried=tried,
            leave_one_out_worst_index=worst)
    out["_unresolved_shape"] = sum(1 for r in kept if not r.get("shape"))
    return out


def conditional_verdict(record, group, fills):
    """OPEN/FILLED/"" for one mark under ITS OWN SHAPE's split, and why.

    THE CONTRACT IS NOT "SPLIT HARDER". A shape declared with one fill is not
    thereby measured: `route` would return that fill from `fill_verdict` because
    there is nothing to choose between, and calling that a MEASURED shape-and-
    fill identity would put a declaration's word inside a method whose name says
    the ink said it. So this returns "" with `ONE_FILL_DECLARED` rather than the
    fill, and the decision about what method such a mark deserves is left where
    it belongs.
    """
    if not record.get("shape"):
        return "", "SHAPE_UNRESOLVED"
    if len(fills) == 1:
        return "", "ONE_FILL_DECLARED"
    if group is None or len(group["interior_ink"]) < 4:
        return "", "GROUP_TOO_SMALL"
    split = MRT.Split(**group["production_split"])
    if not split.separates:
        return "", "GROUP_DOES_NOT_SEPARATE"
    value = float(record["Fill_Score_Window"])
    if not MRT._clear(value, split):
        return "", "MARK_ON_THE_BOUNDARY"
    return ("FILLED" if value >= split.threshold else "OPEN"), "GROUP_SPLIT"


def diagnose(image, panel_box, series, panel="", rendering=""):
    """Every number this module has, for one panel, without changing any."""
    out = MRT.route(image, panel_box, series)
    recs = out["records"]
    gs = groups(recs, series)
    names = declared_names(series)
    fills = declared_fills_by_shape(series)
    gsplit = out["fill_split"]
    gindex = _index_of(gsplit)
    kept = [r for r in recs if r.get("Marker_Validity_Status") == KEPT_STATUS]
    rows = []
    for i, r in enumerate(recs):
        shape = r.get("shape") or ""
        group = gs.get(shape) if shape in fills else None
        cond, why = ("", "NOT_A_KEPT_MARK")
        if r.get("Marker_Validity_Status") == KEPT_STATUS:
            cond, why = conditional_verdict(r, group, fills.get(shape, []))
        gth = gsplit["threshold"]
        ink = r.get("interior_ink")
        grp_split = (MRT.Split(**group["production_split"])
                     if group is not None else None)
        rows.append(dict(
            Panel=panel, Rendering=rendering, Mark_Index=i,
            Point_Px_X=r.get("point_px_x"), Point_Px_Y=r.get("point_px_y"),
            Marker_Scale_Px=r.get("marker_scale_px"),
            Marker_Validity_Status=r.get("Marker_Validity_Status", ""),
            Refusal=r.get("refusal", ""),
            Third_Harmonic=r.get("third_harmonic"),
            Shape_Split=out["shape_split"]["threshold"],
            Shape_Margin=(None if (r.get("third_harmonic") is None
                                   or out["shape_split"]["threshold"] is None)
                          else round(abs(float(r["third_harmonic"])
                                         - float(out["shape_split"]["threshold"])), 6)),
            Shape_Resolved=shape,
            Interior_Ink=ink,
            Global_Fill_Split=gth,
            Global_Fill_Index=round(gindex, 4),
            Global_Fill_Margin=(None if (ink is None or gth is None)
                                else round(abs(float(ink) - float(gth)), 6)),
            Global_Fill_Verdict=r.get("fill", ""),
            Global_Series_ID=r.get("Series_ID", ""),
            Fill_Conditioning_Shape=shape if group is not None else "",
            Group_N=(group["n"] if group is not None else None),
            Group_Fill_Split=(grp_split.threshold if grp_split is not None else None),
            Group_Fill_Index=(group["production_index"] if group is not None else None),
            Group_Fill_Margin=(None if (group is None or ink is None
                                        or grp_split.threshold is None)
                               else round(abs(float(ink) - float(grp_split.threshold)), 6)),
            Group_Fill_Separates=(bool(grp_split.separates)
                                  if grp_split is not None else None),
            Conditional_Fill_Verdict=cond,
            Conditional_Series_ID=(names.get((shape, cond), "") if cond else ""),
            Verdicts_Differ=bool((r.get("fill", "") or "") != (cond or "")),
            _why=why))
    return dict(panel=panel, rendering=rendering,
                marker_scale_px=out["marker_scale_px"],
                candidates=out["Candidate_Mark_Record_Count"],
                routed=out["Routed_Point_Count"],
                kept=len(kept),
                refusals=dict(collections.Counter(r["refusal"] for r in recs
                                                  if r["refusal"])),
                shape_split=out["shape_split"],
                shape_index=round(_index_of(out["shape_split"]), 4),
                global_fill_split=gsplit,
                global_fill_index=round(gindex, 4),
                global_cuts=cuts([float(r["interior_ink"]) for r in kept], 2),
                global_minimum_cluster=production_floor(len(kept)),
                groups=gs, rows=rows, route=out)


def write(report, out_dir):
    """`marks.csv` and `groups.json` for one or more diagnosed panels."""
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    reports = report if isinstance(report, list) else [report]
    marks = os.path.join(out_dir, "marks.csv")
    with open(marks, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(MARK_COLUMNS),
                           extrasaction="ignore")
        w.writeheader()
        for rep in reports:
            for row in rep["rows"]:
                w.writerow({k: ("" if row.get(k) is None else row[k])
                            for k in MARK_COLUMNS})
    blob = os.path.join(out_dir, "groups.json")
    with open(blob, "w", encoding="utf-8") as fh:
        json.dump([{k: v for k, v in rep.items()
                    if k not in ("rows", "route")} for rep in reports],
                  fh, indent=1, sort_keys=True, default=float)
        fh.write("\n")
    return marks, blob


def _fixture_panels():
    """Every twin-scatter rendering this repository carries, as diagnosis input."""
    from PIL import Image
    truth = os.path.join(HERE, "twin_scatter_truth.json")
    if not os.path.exists(truth):                                 # pragma: no cover
        import make_twin_scatter_fixture as TSF
        TSF.main()
    doc = json.load(open(truth, encoding="utf-8"))
    for name in sorted(doc["renderings"]):
        r = doc["renderings"][name]
        path = os.path.join(HERE, r["file"])
        if not os.path.exists(path):                              # pragma: no cover
            import make_twin_scatter_fixture as TSF
            TSF.main()
        series = [dict(id=sid, shape=spec["shape"], fill=spec["fill"])
                  for sid, spec in sorted(r["series"].items())]
        yield name, Image.open(path).convert("RGB"), r["panel_box"], series


def main():                                                       # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--image")
    ap.add_argument("--box", help="x0,x1,y0,y1")
    ap.add_argument("--series", help="ID:SHAPE:FILL,ID:SHAPE:FILL,...")
    ap.add_argument("--panel", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out_dir = args.out or tempfile.mkdtemp(prefix="fdt_split_")
    reports = []
    if args.image:
        from PIL import Image
        box = tuple(int(v) for v in args.box.split(","))
        series = [dict(id=p.split(":")[0], shape=p.split(":")[1].upper(),
                       fill=p.split(":")[2].upper())
                  for p in args.series.split(",")]
        reports.append(diagnose(Image.open(args.image).convert("RGB"), box,
                                series, panel=args.panel or args.image,
                                rendering=os.path.basename(args.image)))
    else:
        for name, image, box, series in _fixture_panels():
            reports.append(diagnose(image, box, series,
                                    panel="twin_scatter", rendering=name))
    marks, blob = write(reports, out_dir)
    for rep in reports:
        gs = rep["groups"]
        print("%s %s: %d candidates, %d kept, scale %.0f px"
              % (rep["panel"], rep["rendering"], rep["candidates"],
                 rep["kept"], rep["marker_scale_px"]))
        print("   shape   separates=%s index %.3f"
              % (rep["shape_split"]["separates"], rep["shape_index"]))
        gb = best(rep["global_cuts"])
        print("   fill    separates=%s index %.3f; over %d kept marks the "
              "plainest cut is %s"
              % (rep["global_fill_split"]["separates"], rep["global_fill_index"],
                 rep["kept"],
                 "none" if gb is None else "%d|%d at %.3f"
                 % (gb["low_n"], gb["high_n"], gb["index"])))
        for shape in sorted(k for k in gs if not k.startswith("_")):
            g = gs[shape]
            adm, two = g["best_admissible"], g["best_at_floor_two"]
            print("   %-9s n=%-3d fills=%s  separates=%s index %.3f"
                  % (shape, g["n"], "/".join(g["declared_fills"]),
                     g["production_split"]["separates"], g["production_index"]))
            print("             plainest %s ; admissible %s ; stable %d/%d"
                  % ("none" if two is None else "%d|%d at %.3f"
                     % (two["low_n"], two["high_n"], two["index"]),
                     "none" if adm is None else "%d|%d at %.3f"
                     % (adm["low_n"], adm["high_n"], adm["index"]),
                     g["leave_one_out_agreeing"], g["leave_one_out_tried"]))
        differ = [r for r in rep["rows"] if r["Verdicts_Differ"]]
        print("   %d of %d rows have different global and conditional verdicts"
              % (len(differ), len(rep["rows"])))
        print()
    print(marks)
    print(blob)


if __name__ == "__main__":                                        # pragma: no cover
    main()
