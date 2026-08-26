# -*- coding: utf-8 -*-
"""Selected panels, by how their box was arrived at and how defended its axis is."""
import collections, csv, sys

ORDER = ["ANCHOR_FREE", "ANCHOR_CLIPPED", "FALLBACK_LONGEST",
         "GEOMETRY_UNRESOLVED", "GEOMETRY_UNOBSERVED"]


def rows_of(path):
    rows = list(csv.DictReader(open(path)))
    passes = {(r["pid"], r["fig"]): (r["mode"], r["ink"])
              for r in rows if r["kind"] == "SELECTED_PASS"}
    return [r for r in rows if r["kind"] == "SELECTED"
            and passes.get((r["pid"], r["fig"])) == (r["mode"], r["ink"])]


def table(sel):
    tab = collections.Counter()
    for r in sel:
        origin = "constructed" if r["constructed"] == "True" else "cut"
        tab[(origin, r["axis_geometry"] or "?")] += 1
    return tab


def main(path):
    sel = rows_of(path)
    figs = {(r["pid"], r["fig"]) for r in sel}
    print("%d selected panels on %d figures" % (len(sel), len(figs)))
    tab = table(sel)
    cols = [c for c in ORDER if any(k[1] == c for k in tab)]
    cols += sorted({k[1] for k in tab} - set(cols))
    print("%-13s %s  %s" % ("box origin",
                            "  ".join("%-19s" % c for c in cols), "total"))
    for origin in ("cut", "constructed"):
        n = sum(v for k, v in tab.items() if k[0] == origin)
        print("%-13s %s  %5d" % (origin,
              "  ".join("%-19d" % tab[(origin, c)] for c in cols), n))
    print()
    roots = collections.Counter(r["origin_roots"] or "-" for r in sel)
    print("roots:", ", ".join("%s %d" % kv for kv in roots.most_common()))
    print()
    bad = [r for r in sel if r["constructed"] == "True"]
    print("the constructed boxes:")
    for r in sorted(bad, key=lambda r: (r["pid"], r["fig"], r["panel"])):
        print("  %-5s %-10s %-4s %-19s %-22s %-20s %s"
              % (r["pid"], r["fig"], r["panel"], r["box"], r["axis_geometry"],
                 r["origin_roots"], r["status"]))
    print()
    per = collections.Counter((r["pid"], r["fig"]) for r in bad)
    print("figures with at least one constructed panel: %d of %d"
          % (len(per), len(figs)))
    lad = collections.Counter()
    for r in sel:
        origin = "constructed" if r["constructed"] == "True" else "cut"
        lad[(origin, r["status"] == "LADDER_OK")] += 1
    for origin in ("cut", "constructed"):
        tot = lad[(origin, True)] + lad[(origin, False)]
        if tot:
            print("%-12s ladder reads %d of %d (%.0f%%)"
                  % (origin, lad[(origin, True)], tot,
                     100.0 * lad[(origin, True)] / tot))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "trP.csv")
