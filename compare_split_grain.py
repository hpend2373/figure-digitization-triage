# -*- coding: utf-8 -*-
"""Four fill-split rules, one harness, the same fixtures. What each gets wrong.

    python3 compare_split_grain.py            # the table, on every fixture here
    python3 compare_split_grain.py --csv OUT  # and the same table as a file

THE ONLY THING THAT VARIES IS THE FILL RULE. Every candidate is handed the SAME
records from the same `marker_routing.route` call - the same marker scale, the
same merged-blob refusals, the same shape verdicts - and differs only in how the
OPEN/FILLED question is asked. A comparison in which two candidates saw
different marks would be measuring the mark-finder, not the rule.

    CURRENT_GLOBAL       one split over every kept mark's interior ink, with a
                         minimum class of a quarter. What `marker_routing` does.
    RELAXED_GLOBAL       the same, with the minimum class dropped to two. The
                         candidate that a reading of 464 Figure 2 as "the floor
                         is too high" would produce.
    SHAPE_CONDITIONED    one split inside each RESOLVED shape, over the marks of
                         that shape only, and no verdict at all for a shape the
                         panel declares with a single fill.
    DECLARATION_AWARE    SHAPE_CONDITIONED, and a group must also hold at least
                         three marks on each side and keep every surviving mark
                         on the same side of the boundary when any one mark is
                         dropped.

## What the columns mean

    right/wrong    scored against what was DRAWN, one-to-one, by
                   `marker_routing.match_one_to_one`. `wrong` is a mark routed
                   to a series it does not belong to - the outcome this package
                   ranks below every other, missing included.
    refused        a candidate mark this rule would not name
    invented       a record routed with no drawn mark under it
    missing        drawn marks no record was matched to
    false_split    a fill split established over a set the drawing gave ONE fill
                   class. Counted per panel, not per mark: it is the rule's
                   error, and every mark it then names is a wrong value.
    unstable       marks whose side of the boundary changes when any single
                   other mark is dropped from the set the split was taken over

`false_split` needs the truth and is therefore a FIXTURE column, not something a
reader could compute. That is the point of a fixture.
"""
import argparse
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np                                                # noqa: E402
from PIL import Image                                             # noqa: E402

import marker_routing as MRT                                      # noqa: E402
import diagnose_marker_split as D                                 # noqa: E402

#: A group must hold this many marks on each side before DECLARATION_AWARE will
#: call it two classes. Not a fraction: a fraction of a small group is one mark,
#: which is what makes SHAPE_CONDITIONED inherit the outlier problem the panel-
#: wide quarter was protecting against.
ABSOLUTE_SUPPORT = 3


def split_with_floor(values, floor):
    """`marker_routing._split`, with the minimum class size passed in.

    A COPY, DELIBERATELY. Production's `_split` decides its own floor and this
    harness has to be able to ask for another one without changing it; a
    parameter added to the real function for the benefit of a comparison is a
    production change made before the comparison it was supposed to inform.
    """
    xs = np.array(sorted(float(v) for v in values), dtype=float)
    if len(xs) < 4:
        return MRT.Split(None, 0.0, 0.0, False)
    best = None
    for cut in range(1, len(xs)):
        lo, hi = xs[:cut], xs[cut:]
        if min(len(lo), len(hi)) < floor:
            continue
        spread = lo.std() + hi.std()
        gap = hi.mean() - lo.mean()
        if spread > 1e-9:
            index = gap / spread
        else:
            index = float("inf") if gap > 1e-9 else 0.0
        if best is None or index > best[0]:
            best = (index, (lo[-1] + hi[0]) / 2.0, hi.mean() - lo.mean(), spread)
    if best is None:
        return MRT.Split(None, 0.0, 0.0, False)
    index, threshold, between, within = best
    return MRT.Split(round(float(threshold), 4), round(float(between), 4),
                     round(float(within), 4), bool(index >= MRT.SEPARATION))


def _stable(values, split, floor):
    """Marks whose side of `split` moves when any single other mark is dropped."""
    xs = sorted(float(v) for v in values)
    if split.threshold is None or not split.separates:
        return set()
    moved = set()
    for drop in range(len(xs)):
        rest = xs[:drop] + xs[drop + 1:]
        got = split_with_floor(rest, floor)
        if got.threshold is None or not got.separates:
            moved.update(range(len(xs)))
            continue
        for v in rest:
            if (v >= split.threshold) != (v >= got.threshold):
                moved.add(v)
    return moved


def verdict_before(value, split, fills):
    """`marker_routing.fill_verdict` AS IT STOOD BEFORE THIS ROUND.

    CURRENT_GLOBAL has to be the behaviour that was there, not the behaviour
    that is there now, or the row this table calls the baseline is the change
    measured against itself. The one difference is the branch that returned a
    single declared fill without measuring it.
    """
    if len(fills) == 1:
        return sorted(fills)[0]
    if not split.separates or not MRT._clear(value, split):
        return ""
    return "FILLED" if value >= split.threshold else "OPEN"


def _fills_for(record, declared_fills, mode):
    """Which fills this mark's rule is choosing between, and over which marks."""
    if mode in ("SHAPE_CONDITIONED", "DECLARATION_AWARE"):
        return declared_fills.get(record.get("shape") or "", [])
    return sorted({f for fills in declared_fills.values() for f in fills})


def assign(records, series, mode):
    """{record index: (fill, Series_ID, why)} under one candidate rule.

    THE SHAPE VERDICT AND THE MERGED REFUSAL ARE NOT THIS FUNCTION'S BUSINESS.
    They came off `route` and every candidate inherits them unchanged, so a
    mark whose shape is unresolved is unrouted under all four rules and the
    table is comparing the one thing it says it is comparing.
    """
    fills_by_shape = D.declared_fills_by_shape(series)
    names = D.declared_names(series)
    kept = [(i, r) for i, r in enumerate(records)
            if r.get("Marker_Validity_Status") == D.KEPT_STATUS]
    out = {}
    splits = {}
    unstable = set()
    if mode in ("CURRENT_GLOBAL", "RELAXED_GLOBAL"):
        values = [float(r["interior_ink"]) for _i, r in kept]
        floor = (max(2, len(values) // 4) if mode == "CURRENT_GLOBAL" else 2)
        split = split_with_floor(values, floor)
        splits[""] = split
        unstable = {v for v in _stable(values, split, floor)}
    else:
        for shape, fills in sorted(fills_by_shape.items()):
            mine = [float(r["interior_ink"]) for _i, r in kept
                    if r.get("shape") == shape]
            floor = max(2, len(mine) // 4)
            split = split_with_floor(mine, floor)
            if mode == "DECLARATION_AWARE" and split.separates:
                # ABSOLUTE SUPPORT AND STABILITY, not only a fraction. Inside a
                # shape the quarter is often one or two marks, which is the
                # outlier rule switched off exactly where the groups got small.
                low = sum(1 for v in mine if v < split.threshold)
                if min(low, len(mine) - low) < ABSOLUTE_SUPPORT:
                    split = MRT.Split(split.threshold, split.between,
                                      split.within, False)
                elif _stable(mine, split, floor):
                    split = MRT.Split(split.threshold, split.between,
                                      split.within, False)
            splits[shape] = split
            unstable |= _stable(mine, split, floor)
    for i, r in kept:
        shape = r.get("shape") or ""
        if mode in ("CURRENT_GLOBAL", "RELAXED_GLOBAL"):
            split, fills = splits[""], _fills_for(r, fills_by_shape, mode)
        else:
            split = splits.get(shape, MRT.Split(None, 0.0, 0.0, False))
            fills = fills_by_shape.get(shape, [])
            if len(fills) == 1:
                # ONE FILL DECLARED FOR THIS SHAPE. `fill_verdict` would return
                # it, because there is nothing to choose between - and calling
                # that MEASURED_MARKER_SHAPE_FILL puts a declaration's word
                # inside a method whose name says the ink decided.
                #
                # AND THE SPLIT THIS GROUP WOULD HAVE HAD IS NOT CONSULTED, so
                # it is not scored either: counting a split nothing reads as a
                # false split would charge a rule for an answer it never gave.
                splits[shape] = MRT.Split(None, 0.0, 0.0, False)
                out[i] = ("", "", "ONE_FILL_DECLARED")
                continue
        if not shape and len(fills_by_shape) > 1:
            out[i] = ("", "", "SHAPE_UNRESOLVED")
            continue
        fill = verdict_before(float(r["Fill_Score_Window"]), split, set(fills))
        if not fill:
            out[i] = ("", "", "FILL_UNRESOLVED")
            continue
        name = names.get((shape, fill))
        if name is None:
            out[i] = (fill, "", "CLASS_NOT_DECLARED")
            continue
        out[i] = (fill, name, "ROUTED")
    return out, splits, unstable


def score(rendering, root, series, truth_pairs, mode, drawn_fills=None):
    """One candidate on one rendering, scored against what was drawn."""
    image = Image.open(os.path.join(root, rendering)).convert("RGB")
    return score_route(image, None, series, truth_pairs, mode,
                       drawn_fills=drawn_fills)


def score_route(image, panel_box, series, truth_pairs, mode, drawn_fills=None,
                route_out=None):
    out = route_out if route_out is not None else MRT.route(image, panel_box, series)
    records = out["records"]
    got, splits, unstable = assign(records, series, mode)
    scale = out["marker_scale_px"] or 1.0
    marks = [(i, r) for i, r in enumerate(records)
             if r["refusal"] != "NOT_A_MARKER"]
    pair = MRT.match_one_to_one([r for _i, r in marks], truth_pairs, 0.6 * scale)
    right = wrong = refused = invented = 0
    unstable_marks = 0
    for k, (i, r) in enumerate(marks):
        j = pair.get(k)
        name = got.get(i, ("", "", "NOT_KEPT"))[1]
        if r.get("interior_ink") is not None \
                and float(r["interior_ink"]) in unstable:
            unstable_marks += 1
        if not name:
            refused += 1
        elif j is None:
            invented += 1
        elif truth_pairs[j][0] == name:
            right += 1
        else:
            wrong += 1
    # A FILL SPLIT OVER A SET THE DRAWING GAVE ONE CLASS. `drawn_fills` is
    # {scope: set of fills actually drawn}; the scope is "" for a panel-wide
    # rule and the shape for a conditioned one.
    false_split = 0
    if drawn_fills is not None:
        for scope, split in splits.items():
            if not split.separates:
                continue
            if len(drawn_fills.get(scope, set())) < 2:
                false_split += 1
    return dict(right=right, wrong=wrong, refused=refused, invented=invented,
                missing=len(truth_pairs) - len(pair),
                candidates=len(marks), false_split=false_split,
                unstable=unstable_marks,
                separates={k: bool(v.separates) for k, v in sorted(splits.items())})


def _panels():
    """Every rendering both fixture families carry, with its truth."""
    for truth_file, prefix in (("twin_scatter_truth.json", "twin"),
                               ("split_grain_truth.json", "grain")):
        path = os.path.join(HERE, truth_file)
        if not os.path.exists(path):                              # pragma: no cover
            mod = ("make_twin_scatter_fixture" if prefix == "twin"
                   else "make_split_grain_fixture")
            __import__(mod).main()
        doc = json.load(open(path, encoding="utf-8"))
        for name in sorted(doc["renderings"]):
            r = doc["renderings"][name]
            if "declared" in r:
                series = [dict(id=d["Series_ID"], shape=d["Marker_Shape"],
                               fill=d["Marker_Fill"]) for d in r["declared"]]
            else:
                series = [dict(id=sid, shape=s["shape"], fill=s["fill"])
                          for sid, s in sorted(r["series"].items())]
            truth = [(sid, cx, cy) for sid, s in sorted(r["series"].items())
                     for cx, cy in s["centres"]]
            drawn = collections.defaultdict(set)
            for sid, s in r["series"].items():
                if not s.get("centres"):
                    continue
                drawn[s["shape"]].add(s["fill"])
                drawn[""].add(s["fill"])
            yield ("%s/%s" % (prefix, name), r["file"], r["panel_box"], series,
                   truth, dict(drawn))


CANDIDATES = ("CURRENT_GLOBAL", "RELAXED_GLOBAL", "SHAPE_CONDITIONED",
              "DECLARATION_AWARE")


def table(panels=None):
    """The comparison, as a list of rows."""
    rows = []
    for label, fname, box, series, truth, drawn in (panels or _panels()):
        image = Image.open(os.path.join(HERE, fname)).convert("RGB")
        out = MRT.route(image, box, series)
        for mode in CANDIDATES:
            got = score_route(image, box, series, truth, mode,
                              drawn_fills=drawn, route_out=out)
            got.update(candidate=mode, fixture=label, drawn=len(truth))
            rows.append(got)
    return rows


COLUMNS = ("candidate", "fixture", "drawn", "candidates", "right", "wrong",
           "refused", "invented", "missing", "false_split", "unstable")


def main():                                                       # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default="")
    args = ap.parse_args()
    rows = table()
    head = "%-20s %-18s %5s %5s %6s %6s %8s %9s %8s %11s %9s" % (
        "candidate", "fixture", "drawn", "cand", "right", "wrong", "refused",
        "invented", "missing", "false_split", "unstable")
    print(head)
    print("-" * len(head))
    for mode in CANDIDATES:
        for r in [x for x in rows if x["candidate"] == mode]:
            print("%-20s %-18s %5d %5d %6d %6d %8d %9d %8d %11d %9d"
                  % (r["candidate"], r["fixture"], r["drawn"], r["candidates"],
                     r["right"], r["wrong"], r["refused"], r["invented"],
                     r["missing"], r["false_split"], r["unstable"]))
        tot = [x for x in rows if x["candidate"] == mode]
        print("%-20s %-18s %5s %5s %6d %6d %8d %9d %8d %11d %9d"
              % ("", "TOTAL", "", "", sum(x["right"] for x in tot),
                 sum(x["wrong"] for x in tot), sum(x["refused"] for x in tot),
                 sum(x["invented"] for x in tot), sum(x["missing"] for x in tot),
                 sum(x["false_split"] for x in tot),
                 sum(x["unstable"] for x in tot)))
        print()
    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(COLUMNS),
                               extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(args.csv)


if __name__ == "__main__":                                        # pragma: no cover
    main()
