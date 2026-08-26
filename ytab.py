# -*- coding: utf-8 -*-
"""The y scale groups a run proposed, and the residuals behind each one."""
import collections, csv, sys


def main(path="trY.csv"):
    rows = list(csv.DictReader(open(path)))
    passes = {(r["pid"], r["fig"]): (r["mode"], r["ink"])
              for r in rows if r["kind"] == "SELECTED_PASS"}

    def won(r):
        return passes.get((r["pid"], r["fig"])) == (r["mode"], r["ink"])

    groups = [r for r in rows if r["kind"] == "Y_SCALE_GROUP" and won(r)]
    members = [r for r in rows if r["kind"] == "Y_SCALE_MEMBER" and won(r)]
    sel = [r for r in rows if r["kind"] == "SELECTED" and won(r)]
    print("%d groups over %d panels on %d figures"
          % (len(groups), len(sel), len({(r["pid"], r["fig"]) for r in sel})))
    st = collections.Counter(r["status"] for r in groups)
    for k, v in st.most_common():
        print("  %-28s %d" % (k, v))
    prov = sum(1 for r in members if r["is_provider"] == "True")
    dep = [r for r in members if r["is_provider"] != "True" and r.get("d_baseline") != ""]
    conf = [r for r in members if r.get("conflict")]
    print("  providers %d, dependants with a provider %d, conflicts %d"
          % (prov, len(dep), len(conf)))
    own = sum(1 for r in sel if r["calibration"] == "LOCAL_LADDER")
    print("  actually calibrated panels (local ladder) %d" % own)
    # THE SUBSET A TRANSFER WOULD ACTUALLY SERVE: a member of a single-calibration
    # group that read no ladder of its own. A row where every panel reads its own
    # numerals comes back AMBIGUOUS and needs no transfer at all, so counting
    # those as a problem would be counting a well-labelled figure as one.
    cand = {(r["pid"], r["fig"], r["group_id"]) for r in groups
            if r["status"] == "ROW_BAND_ONE_PROVIDER"}
    serve = [r for r in members
             if (r["pid"], r["fig"], r["group_id"]) in cand
             and r["is_provider"] != "True" and r["own_ladder"] != "True"]
    print("  shadow transfer candidates (UNVALIDATED): %d" % len(serve))
    print("\nresiduals for THOSE panels (raw, no tolerance applied):")
    for f in ("overlap_share", "d_baseline", "d_axis_top", "d_axis_bottom",
              "d_height", "symmetric_max", "matched_max", "line_residual_px",
              "provider_unmatched", "target_unmatched"):
        v = sorted(float(r[f]) for r in serve if r.get(f) not in ("", None))
        if not v:
            print("  %-18s no values" % f); continue
        print("  %-18s n=%-3d min %-8.1f med %-8.1f max %.1f"
              % (f, len(v), v[0], v[len(v) // 2], v[-1]))
    print("\nresiduals for every dependant, transfer candidate or not:")
    for f in ("overlap_share", "d_baseline", "d_axis_top", "d_axis_bottom",
              "d_height", "symmetric_max", "matched_max", "line_residual_px",
              "provider_unmatched", "target_unmatched"):
        v = sorted(float(r[f]) for r in dep if r.get(f) not in ("", None))
        if not v:
            print("  %-18s no values" % f); continue
        print("  %-18s n=%-3d min %-8.1f q1 %-8.1f med %-8.1f q3 %-8.1f max %.1f"
              % (f, len(v), v[0], v[len(v) // 4], v[len(v) // 2],
                 v[3 * len(v) // 4], v[-1]))
    print("\nper figure:")
    for key in sorted({(r["pid"], r["fig"]) for r in groups}):
        g = [r for r in groups if (r["pid"], r["fig"]) == key]
        print("  %-5s %-10s groups %d  %s" % (
            key[0], key[1], len(g),
            ", ".join("%s[%s prov=%s n=%s]" % (x["group_id"],
                                               x["status"].replace("ROW_BAND_", ""),
                                               x["provider_panel"] or "-",
                                               x["n_members"]) for x in g)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "trY.csv")
