# -*- coding: utf-8 -*-
"""Which panels share ONE y calibration. Proposed, measured, never applied.

    YGROUP=1 TRACE=trace.csv python3 propose.py

The pipeline assumes every panel carries its own ladder. Publication 177's
figure 2 says otherwise: five rows of three, y axis numerals printed ONCE PER
ROW, and eleven of fifteen panels refusing a ladder they were never given
anything to read. Counting those as failures measured the figure's layout, and
the round that noticed it also has to stop asking each panel for a ladder of its
own - the owner of a y scale is a ROW GROUP, not a panel.

WHAT THIS DOES NOT DO. It does not transfer a calibration, does not write
`SHARED_ROW` into any panel's `calibration` cell, and does not change what the
pipeline returns. It proposes a group, names the provider, and records the RAW
residuals a person would need to decide whether the proposal is sound:

    the axis runs' row overlap, and the group's WEAKEST pair, so a chain of
      overlaps pretending to be one row is visible rather than hidden
    baseline, axis top, axis bottom and panel height differences, unrounded
    the TICK ROW SIGNATURE of each member against the provider's, which is the
      one piece of evidence a panel with no numerals can still offer

NO TOLERANCE IS APPLIED TO ANY OF THEM. A tolerance on a baseline difference is
a constant nobody has measured yet, and the reviewer's instruction is explicit:
record the residuals, build the distribution, and only then decide. The one
threshold used at all is `ADOPT_SHARE`, which this file did not invent and which
groups the rows in the first place.

The three outcomes need no tolerance either, which is why they are the only
verdicts here:

    SHARED_ROW_CANDIDATE          exactly one calibration among the members
    Y_SCALE_GROUP_NO_PROVIDER     no member read a ladder
    Y_SCALE_GROUP_AMBIGUOUS       two members read DIFFERENT ladders
"""
import os

import axis_reader as A
import gate_trace as T

ON = os.environ.get("YGROUP", "0") != "0"

SHARED_ROW_CANDIDATE = "SHARED_ROW_CANDIDATE"
NO_PROVIDER = "Y_SCALE_GROUP_NO_PROVIDER"
AMBIGUOUS = "Y_SCALE_GROUP_AMBIGUOUS"

#: A member that read its OWN ladder and disagrees with the provider's is not a
#: tolerance question - the two read different numbers off the same row.
DISAGREES = "MEMBER_LADDER_DISAGREES"


def spine_cols(dark, box, spine_x):
    """(first, last) column of the spine's own rule, or the spine column twice.

    Measured rather than assumed, because the tick window has to start OUTSIDE
    the rule: a 2 px spine and a fixed 4 px window means every row of the axis
    reads as a tick, and the signature becomes the whole run.
    """
    for a, b, _ln in A._rules(dark, box, vertical=True):
        if a - 1 <= int(spine_x) <= b + 1:
            return int(a), int(b)
    return int(spine_x), int(spine_x)


def tick_rows(dark, box, spine_x, run, side, depth=None):
    """Row centres of the short marks abutting the spine on the label side.

    This is what a panel with no numerals can still be compared on. Depth is
    `RULE_MAX_W` - a rule is 1 to 4 columns, so a window that deep past the end
    of the rule is inside the tick and outside the plot.
    """
    depth = A.RULE_MAX_W if depth is None else int(depth)
    a, b = spine_cols(dark, box, spine_x)
    if side == "LEFT":
        lo, hi = max(0, a - depth), a
    else:
        lo, hi = min(dark.shape[1], b + 1), min(dark.shape[1], b + 1 + depth)
    if hi <= lo or run is None:
        return []
    inked = [y for y in range(max(0, int(run[0])), min(dark.shape[0], int(run[1])))
             if dark[y, lo:hi].any()]
    out, start, prev = [], None, None
    for y in inked:
        if start is None:
            start = prev = y
        elif y == prev + 1:
            prev = y
        else:
            out.append((start + prev) // 2)
            start = prev = y
    if start is not None:
        out.append((start + prev) // 2)
    return out


def _overlap_share(a, b):
    """Row overlap of two axis runs, over the SHORTER of the two."""
    if a is None or b is None:
        return 0.0
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi <= lo:
        return 0.0
    return (hi - lo) / max(1, min(a[1] - a[0], b[1] - b[0]))


def bands(panels):
    """Single-linkage row bands over the AXIS RUNS.

    Over the runs and not the boxes: an invented box can be much taller than the
    axis inside it, and grouping on boxes lets one such box pull in the row above.
    Single linkage can still CHAIN, so the group row reports the weakest pair in
    it and a chained band is visible in the output instead of being asserted away.
    """
    left = list(panels)
    out = []
    while left:
        cur = [left.pop(0)]
        moved = True
        while moved:
            moved = False
            for p in list(left):
                if any(_overlap_share(p["run"], q["run"]) >= A.ADOPT_SHARE
                       for q in cur):
                    cur.append(p)
                    left.remove(p)
                    moved = True
        out.append(sorted(cur, key=lambda p: (p["box"][0], p["box"][2])))
    return sorted(out, key=lambda g: (g[0]["run"] or (0, 0))[0])


def _residuals(target, provider):
    """Every difference, unrounded, and no verdict about any of them."""
    tr, pr = target["run"], provider["run"]
    res = {
        "overlap_share": round(_overlap_share(tr, pr), 3),
        "d_baseline": (None if target["baseline"] is None or provider["baseline"] is None
                       else int(target["baseline"]) - int(provider["baseline"])),
        "d_axis_top": (None if tr is None or pr is None else int(tr[0]) - int(pr[0])),
        "d_axis_bottom": (None if tr is None or pr is None else int(tr[1]) - int(pr[1])),
        "d_height": (target["box"][3] - target["box"][2])
                    - (provider["box"][3] - provider["box"][2]),
    }
    t, p = target["ticks"], provider["ticks"]
    res["n_ticks"] = len(t)
    res["n_provider_ticks"] = len(p)
    if t and p:
        near = [min(abs(y - q) for q in p) for y in t]
        res["tick_residual_max"] = max(near)
        res["tick_residual_med"] = sorted(near)[len(near) // 2]
    else:
        res["tick_residual_max"] = None
        res["tick_residual_med"] = None
    return res


def record(dark, panels):
    """One Y_SCALE_GROUP row per band, one Y_SCALE_MEMBER row per member.

    `panels` is a list of dicts, each with: label, box, spine, baseline, run,
    side, ladder_ok, sha. RECORDS ONLY - this function is not handed the
    proposal list and cannot change it, and the scenario asserts that from the
    signature.
    """
    if not (ON and T.ON):
        return []
    groups = []
    for gi, band in enumerate(bands(panels), 1):
        gid = "G%d" % gi
        readers = [p for p in band if p["ladder_ok"]]
        shas = sorted({p["sha"] for p in readers if p["sha"]})
        if not readers:
            status, provider = NO_PROVIDER, None
        elif len(shas) > 1:
            status, provider = AMBIGUOUS, readers[0]
        else:
            status, provider = SHARED_ROW_CANDIDATE, readers[0]
        pairs = [_overlap_share(a["run"], b["run"])
                 for i, a in enumerate(band) for b in band[i + 1:]]
        T.add("Y_SCALE_GROUP", group_id=gid, status=status,
              provider_panel=(provider or {}).get("label", ""),
              provider_box=T.box((provider or {}).get("box")) if provider else "",
              provider_calibration_sha=(provider or {}).get("sha", ""),
              n_members=len(band), n_readers=len(readers),
              n_distinct_calibrations=len(shas),
              member_panels=";".join(p["label"] for p in band),
              min_pair_overlap=(round(min(pairs), 3) if pairs else ""),
              provider_ticks=";".join(str(y) for y in
                                      (provider or {}).get("ticks", [])))
        for p in band:
            row = {"group_id": gid, "panel": p["label"], "box": T.box(p["box"]),
                   "is_provider": bool(provider and p is provider),
                   "own_ladder": bool(p["ladder_ok"]),
                   "own_calibration_sha": p["sha"] or "",
                   "ticks": ";".join(str(y) for y in p["ticks"])}
            if provider is not None and p is not provider:
                row.update(_residuals(p, provider))
                if p["ladder_ok"] and p["sha"] and provider["sha"] \
                        and p["sha"] != provider["sha"]:
                    row["conflict"] = DISAGREES
            T.add("Y_SCALE_MEMBER", **row)
        groups.append((gid, status, [p["label"] for p in band],
                       (provider or {}).get("label", "")))
    return groups
