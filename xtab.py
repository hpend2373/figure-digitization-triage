# -*- coding: utf-8 -*-
"""Does "one row band" imply "one y scale"? The pairs that can answer it."""
import collections, csv, sys


def main(path="trX.csv"):
    rows = list(csv.DictReader(open(path)))
    passes = {(r["pid"], r["fig"]): (r["mode"], r["ink"])
              for r in rows if r["kind"] == "SELECTED_PASS"}

    def won(r):
        return passes.get((r["pid"], r["fig"])) == (r["mode"], r["ink"])

    chk = [r for r in rows if r["kind"] == "TRANSFER_CHECK" and won(r)]
    sel = [r for r in rows if r["kind"] == "SELECTED" and won(r)]
    figs = {(r["pid"], r["fig"]) for r in sel}
    print("%d ordered pairs on %d figures (%d panels)"
          % (len(chk), len(figs), len(sel)))
    if not chk:
        return
    rel = sorted(float(r["transfer_max_rel"]) for r in chk
                 if r["transfer_max_rel"] not in ("", None))
    print("\ntransfer_max_rel - the transfer's worst error over the target's own range")
    q = lambda f: rel[min(len(rel) - 1, int(f * len(rel)))]
    print("  n=%d  min %.4f  q1 %.4f  med %.4f  q3 %.4f  max %.1f"
          % (len(rel), rel[0], q(.25), q(.5), q(.75), rel[-1]))
    for t in (0.001, 0.01, 0.05, 0.1, 0.5, 1.0):
        n = sum(1 for v in rel if v <= t)
        print("    within %-6s : %3d of %d  (%.0f%%)" % (t, n, len(rel),
                                                         100.0 * n / len(rel)))
    same = [r for r in chk if r["same_calibration"] == "True"]
    diff = [r for r in chk if r["same_calibration"] != "True"]
    print("\n  pairs whose calibration_sha agrees: %d; differs: %d"
          % (len(same), len(diff)))
    for name, sub in (("agree", same), ("differ", diff)):
        v = sorted(float(r["transfer_max_rel"]) for r in sub
                   if r["transfer_max_rel"] not in ("", None))
        if v:
            print("    %-7s n=%-3d med %.4f  max %.1f" % (name, len(v),
                                                          v[len(v) // 2], v[-1]))
    # THE QUESTION THAT DECIDES THE LINE: is there a band-level signal, available
    # when the target reads NOTHING, that predicts the error?
    print("\ndoes the evidence a ladderless target would have predict the error?")
    for field, lo_is_good in (("symmetric_max", True), ("matched_max", True),
                              ("provider_unmatched", True),
                              ("d_baseline", True), ("d_axis_top", True),
                              ("overlap_share", False)):
        pairs = [(abs(float(r[field])), float(r["transfer_max_rel"]))
                 for r in chk
                 if r.get(field) not in ("", None)
                 and r["transfer_max_rel"] not in ("", None)]
        if len(pairs) < 4:
            print("  %-20s too few values" % field); continue
        pairs.sort()
        half = len(pairs) // 2
        good = [e for _v, e in pairs[:half]]
        bad = [e for _v, e in pairs[half:]]
        if not lo_is_good:
            good, bad = bad, good
        gm = sorted(good)[len(good) // 2]
        bm = sorted(bad)[len(bad) // 2]
        print("  %-20s n=%-3d  better half med rel %.4f   worse half med rel %.4f"
              % (field, len(pairs), gm, bm))

    print("\nthe worst pairs:")
    for r in sorted(chk, key=lambda r: -float(r["transfer_max_rel"] or 0))[:8]:
        print("  %-5s %-10s %s <- %s  rel %-10s abs %-10s slope_err %s"
              % (r["pid"], r["fig"], r["target"], r["source"],
                 (r["transfer_max_rel"] or "")[:9], (r["transfer_max_abs"] or "")[:9],
                 (r["slope_rel_err"] or "")[:8]))
    print("\nthe best pairs:")
    for r in sorted(chk, key=lambda r: float(r["transfer_max_rel"] or 0))[:8]:
        print("  %-5s %-10s %s <- %s  rel %-10s abs %-10s"
              % (r["pid"], r["fig"], r["target"], r["source"],
                 (r["transfer_max_rel"] or "")[:9], (r["transfer_max_abs"] or "")[:9]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "trX.csv")
