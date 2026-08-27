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

The outcomes need no tolerance either, which is why they are the only verdicts
here - and they are named for what the evidence supports, which is that a
provider is PRESENT and the transfer is UNVALIDATED:

    ROW_BAND_ONE_PROVIDER              one eligible reader in the band
    ROW_BAND_MANY_PROVIDERS            more than one, with the distance between
                                       their lines reported and not judged
    ROW_BAND_NO_PROVIDER               no member read a ladder at all
    ROW_BAND_NO_ELIGIBLE_PROVIDER      a member read one and may not lend it
"""
import os

import axis_reader as A
import gate_trace as T

ON = os.environ.get("YGROUP", "0") != "0"

#: WHAT THE BAND CAN SAY ABOUT ITS PROVIDER. Named down from
#: `SHARED_ROW_CANDIDATE`, which claimed a shared scale had been found: what a
#: band with one eligible reader in it actually says is that a provider is
#: PRESENT and the transfer is UNVALIDATED. Nothing here has been checked against
#: a masked-label corpus, so nothing here may be named as if it had.
ONE_PROVIDER = "ROW_BAND_ONE_PROVIDER"
MANY_PROVIDERS = "ROW_BAND_MANY_PROVIDERS"
NO_PROVIDER = "ROW_BAND_NO_PROVIDER"
NO_ELIGIBLE = "ROW_BAND_NO_ELIGIBLE_PROVIDER"

#: `Y_SCALE_GROUP_AMBIGUOUS` was a VERDICT reached by comparing value-set
#: hashes, and both of its answers were wrong in a knowable way: two panels
#: printing the same numbers at different rows hashed the same, and one OCR miss
#: made a panel that had not moved hash differently. It is retired for a COUNT
#: plus a measured residual - `n_providers` and `cross_provider_max_resid_px` -
#: because deciding whether two lines are the same line needs a tolerance and
#: this file has no business inventing one.

#: HOW THE BAND WAS FORMED. Single linkage can walk from one row to the next
#: through overlapping middles; the band then reports CHAINED and a reader can
#: see it, which is the whole reason the field exists.
LINKAGE_COMPLETE = "COMPLETE_LINKAGE"
LINKAGE_CHAINED = "CHAINED"

#: WHETHER A TRANSFER HAS BEEN VALIDATED. One value, and it is the only one this
#: package may write.
TRANSFER_UNVALIDATED = "UNVALIDATED"

#: WHY A READER MAY OR MAY NOT LEND ITS LADDER. A ladder can be read off a
#: fallback column, off a fragment, and across an axis break - publication 475's
#: figure 1 panel C reads one off a column no candidate search found - so
#: `ladder_ok` alone is not provider material.
ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
ELIGIBILITY_UNKNOWN = "UNKNOWN"

#: A member that read its OWN ladder and whose points do not lie on the
#: provider's line is not a tolerance question at the value level - but the
#: DISTANCE between the two lines is a measurement, and it is reported instead of
#: judged.
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


def tick_runs(dark, box, spine_x, run, side, limit=None):
    """[(row_top, row_bottom, length)] for each mark ATTACHED to the spine.

    The first version asked only whether any ink lay in a four-column window
    outside the rule, and on publication 177's figure 1 that let a numeral's
    stroke, a significance bracket and the ink around the baseline in: panel P01
    came back with six "ticks" at 36, 111, 187, 248, 253, 261 where the axis has
    four. A tick mark is not ink near the spine, it is ink CONNECTED to it, and
    the fix is to walk outward from the rule's own edge and stop at the first
    blank column.

    NO WIDTH CAP. Capping the length would need a constant nobody has measured,
    so the length is RECORDED per mark and a reader can see the distribution. The
    outer bound is `LABEL_BAND_MAX`, which this file did not invent and which
    already means "past here is the panel next door".
    """
    limit = A.LABEL_BAND_MAX if limit is None else int(limit)
    a, b = spine_cols(dark, box, spine_x)
    h, w = dark.shape
    if run is None:
        return []
    out, open_run = [], None
    for y in range(max(0, int(run[0])), min(h, int(run[1]))):
        length = 0
        # ATTACHED, WITH ONE STROKE OF SLACK. Strict adjacency to the rule's own
        # column was tried and measured: on publication 177's figure 2 it dropped
        # two of panel P01's four ticks, because a scan leaves an antialiased
        # column between the tick and the rule that falls under the ink
        # threshold. The slack is `RULE_MAX_W` - the same constant that says a
        # rule is 1 to 4 columns wide - and it is not enough to reach a numeral
        # twenty pixels out, which is what the walk exists to exclude.
        if side == "LEFT":
            x = a - 1
            while x >= 0 and a - x <= A.RULE_MAX_W and not dark[y, x]:
                x -= 1
            while x >= 0 and a - x <= limit and dark[y, x]:
                length += 1
                x -= 1
        else:
            x = b + 1
            while x < w and x - b <= A.RULE_MAX_W and not dark[y, x]:
                x += 1
            while x < w and x - b <= limit and dark[y, x]:
                length += 1
                x += 1
        if length:
            if open_run is None:
                open_run = [y, y, length]
            else:
                open_run[1] = y
                open_run[2] = max(open_run[2], length)
        elif open_run is not None:
            out.append(tuple(open_run))
            open_run = None
    if open_run is not None:
        out.append(tuple(open_run))
    return out


def tick_rows(dark, box, spine_x, run, side, limit=None):
    """Row centres of the marks attached to the spine, for comparison."""
    return [(t0 + t1) // 2 for t0, t1, _ln in
            tick_runs(dark, box, spine_x, run, side, limit)]


def match_ticks(target, provider):
    """Mutual nearest neighbours between two tick lists, both ways.

    The first version measured, for each TARGET tick, the distance to the nearest
    provider tick - and nothing else. Publication 177's figure 2 panel P02 then
    reported a residual of 1 px against a provider with three ticks P02 does not
    have at all: a one-way residual cannot see a missing tick, only a misplaced
    one.

    Mutual nearest neighbour, so the pairing is one to one and needs NO SKIP
    PENALTY - a dynamic program would need one, and it would be a constant.
    Everything unpaired is counted and reported on both sides.
    """
    if not target or not provider:
        return {"tick_match_count": 0,
                "target_unmatched": len(target), "provider_unmatched": len(provider),
                "target_to_provider_max": None, "provider_to_target_max": None,
                "symmetric_max": None, "matched_max": None}
    t2p = {i: min(range(len(provider)), key=lambda j: abs(target[i] - provider[j]))
           for i in range(len(target))}
    p2t = {j: min(range(len(target)), key=lambda i: abs(provider[j] - target[i]))
           for j in range(len(provider))}
    pairs = [(i, j) for i, j in t2p.items() if p2t[j] == i]
    t_near = [abs(target[i] - provider[t2p[i]]) for i in range(len(target))]
    p_near = [abs(provider[j] - target[p2t[j]]) for j in range(len(provider))]
    return {
        "tick_match_count": len(pairs),
        "target_unmatched": len(target) - len(pairs),
        "provider_unmatched": len(provider) - len(pairs),
        "target_to_provider_max": max(t_near),
        "provider_to_target_max": max(p_near),
        "symmetric_max": max(max(t_near), max(p_near)),
        "matched_max": (max(abs(target[i] - provider[j]) for i, j in pairs)
                        if pairs else None),
    }


def eligibility(p):
    """Whether this reader's ladder may be offered to the rest of its row.

    A ladder proves that numerals were read beside SOME column. It does not
    prove the column is the panel's axis, that the box is the whole panel, or
    that the axis is unbroken - and publication 475's figure 1's panel C reads
    one off a column no candidate search ever found. So the reasons are listed
    and the answer is UNKNOWN when the inputs were not supplied, never ELIGIBLE
    by default.
    """
    why = []
    if not p.get("ladder_ok"):
        why.append("no local ladder")
    for key, bad, note in (("axis_geometry", ("GEOMETRY_UNRESOLVED",
                                              "GEOMETRY_UNOBSERVED",
                                              "FALLBACK_LONGEST"), "axis %s"),
                           ("completeness", ("FRAGMENT",), "box %s"),
                           ("axis_break", None, "axis %s")):
        v = p.get(key)
        if v in (None, ""):
            return ELIGIBILITY_UNKNOWN, ["%s not supplied" % key]
        if key == "axis_break":
            if v != "NONE":
                why.append(note % v)
        elif v in bad:
            why.append(note % v)
    return (INELIGIBLE if why else ELIGIBLE), why


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


def line_residual(target, provider):
    """How far the TARGET's own ladder points sit from the PROVIDER's line, in px.

    The only comparison of two calibrations that does not need a tolerance: fit
    the provider's (value, pixel) points, then ask where the target's values
    would land on that line and how far that is from where the target actually
    read them. Reported; no verdict.
    """
    import panel_geometry as G
    tp, pp = target.get("points") or [], provider.get("points") or []
    if len(pp) < 2 or not tp:
        return None
    slope, inter, _r = G.fit_line(pp)
    if not slope:
        return None
    return max(abs(px - (v - inter) / slope) for v, px in tp)


def transfer_error(target, provider):
    """What a SHARED_ROW transfer would get WRONG, in the target's own units.

    THE METAMORPHIC TEST NEEDS NO MASKING. The corpus already contains row bands
    where BOTH panels read their own ladder, and those pairs carry their own
    ground truth: transfer the provider's line onto the target's tick pixels, and
    compare with what the target actually read there. If "one row band" implied
    "one y scale", the error would be zero.

    Reported in two forms, because neither alone is comparable across figures:

        max_abs   the largest disagreement in the target's own units
        max_rel   the same, over the target's own value RANGE - dimensionless,
                  so a panel measuring mmHg and one measuring l/min/m2 can be put
                  in the same distribution

    NO VERDICT. A tolerance on `max_rel` is exactly the constant this whole line
    of work is waiting on, and it is what the distribution is being built to
    decide.
    """
    import panel_geometry as G
    tp, pp = target.get("points") or [], provider.get("points") or []
    # NO LENGTH TEST OF ITS OWN. `fit_line` answers None for anything it cannot
    # fit, and a second check in front of it was tried and reverted nothing -
    # decoration, by this package's rule.
    if not tp or not pp:
        return None
    ps, pi, _r = G.fit_line(pp)
    ts, ti, _r2 = G.fit_line(tp)
    if not ps or not ts:
        return None
    errs = [abs((ps * px + pi) - v) for v, px in tp]
    lo = min(v for v, _px in tp)
    hi = max(v for v, _px in tp)
    span = abs(hi - lo)
    return {
        "transfer_max_abs": max(errs),
        "transfer_max_rel": (max(errs) / span) if span else None,
        "target_span": span,
        "slope_rel_err": abs(ps - ts) / abs(ts) if ts else None,
        "intercept_diff": pi - ti,
    }


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
    res["n_ticks"] = len(target["ticks"])
    res["n_provider_ticks"] = len(provider["ticks"])
    res.update(match_ticks(target["ticks"], provider["ticks"]))
    res["line_residual_px"] = line_residual(target, provider)
    return res


def record(dark, panels):
    """One Y_SCALE_GROUP row per band, one Y_SCALE_MEMBER row per member.

    `panels` is a list of dicts, each with: label, box, spine, baseline, run,
    side, ladder_ok, ticks, points, value_set_sha, calibration_sha, and - for the
    eligibility question - axis_geometry, completeness, axis_break. RECORDS ONLY:
    this function is not handed the proposal list and cannot change it, and the
    scenario asserts that from the signature.

    NOTHING HERE IS A VALIDATED TRANSFER. Every group row carries
    `transfer=UNVALIDATED`, which is the only value this package may write into
    that cell, and the status names say "a provider is present", not "a scale is
    shared".
    """
    if not (ON and T.ON):
        return []
    groups = []
    for gi, band in enumerate(bands(panels), 1):
        gid = "G%d" % gi
        for p in band:
            p["eligibility"], p["ineligible_why"] = eligibility(p)
        readers = [p for p in band if p["ladder_ok"]]
        usable = [p for p in readers if p["eligibility"] == ELIGIBLE]
        if not readers:
            status, provider = NO_PROVIDER, None
        elif not usable:
            status, provider = NO_ELIGIBLE, None
        elif len(usable) > 1:
            status, provider = MANY_PROVIDERS, usable[0]
        else:
            status, provider = ONE_PROVIDER, usable[0]
        pairs = [_overlap_share(a["run"], b["run"])
                 for i, a in enumerate(band) for b in band[i + 1:]]
        weakest = min(pairs) if pairs else None
        # TWO PROVIDERS IN ONE BAND IS A COUNT AND A DISTANCE, not a verdict.
        cross = None
        if len(usable) > 1:
            cross = max(x for x in (line_residual(q, usable[0])
                                    for q in usable[1:]) if x is not None) \
                    if any(line_residual(q, usable[0]) is not None
                           for q in usable[1:]) else None
        T.add("Y_SCALE_GROUP", group_id=gid, status=status,
              transfer=TRANSFER_UNVALIDATED,
              linkage=(LINKAGE_COMPLETE if (weakest is None
                                            or weakest >= A.ADOPT_SHARE)
                       else LINKAGE_CHAINED),
              provider_panel=(provider or {}).get("label", ""),
              provider_box=T.box((provider or {}).get("box")) if provider else "",
              provider_calibration_sha=(provider or {}).get("calibration_sha", ""),
              provider_value_set_sha=(provider or {}).get("value_set_sha", ""),
              provider_eligibility=(provider or {}).get("eligibility", ""),
              n_members=len(band), n_readers=len(readers),
              n_eligible_providers=len(usable),
              n_distinct_calibrations=len({p["calibration_sha"] for p in readers
                                           if p.get("calibration_sha")}),
              cross_provider_max_resid_px=cross,
              member_panels=";".join(p["label"] for p in band),
              min_pair_overlap=(round(weakest, 3) if weakest is not None else ""),
              provider_ticks=";".join(str(y) for y in
                                      (provider or {}).get("ticks", [])),
              provider_tick_lengths=";".join(
                  str(n) for n in (provider or {}).get("tick_lengths") or []))
        for p in band:
            row = {"group_id": gid, "panel": p["label"], "box": T.box(p["box"]),
                   "is_provider": bool(provider and p is provider),
                   "own_ladder": bool(p["ladder_ok"]),
                   "eligibility": p["eligibility"],
                   "ineligible_why": "; ".join(p["ineligible_why"]),
                   "own_value_set_sha": p.get("value_set_sha") or "",
                   "own_calibration_sha": p.get("calibration_sha") or "",
                   "ticks": ";".join(str(y) for y in p["ticks"]),
                   # THE LENGTHS, so a 1 px mark and a 6 px one stop counting
                   # alike. Capping them would need a constant nobody has
                   # measured; showing them is what builds the distribution.
                   "tick_lengths": ";".join(str(n) for n in
                                            p.get("tick_lengths") or [])}
            if provider is not None and p is not provider:
                row.update(_residuals(p, provider))
                te = transfer_error(p, provider)
                if te:
                    row.update(te)
                if p["ladder_ok"] and p.get("calibration_sha") \
                        and provider.get("calibration_sha") \
                        and p["calibration_sha"] != provider["calibration_sha"]:
                    row["conflict"] = DISAGREES
            T.add("Y_SCALE_MEMBER", **row)
        # THE METAMORPHIC PAIRS: every ORDERED pair in the band where both read
        # their own ladder, so the transfer has a ground truth to be wrong
        # against. Not restricted to the provider - the question is what the BAND
        # RELATION implies, and eligibility is a separate question about lending.
        for a in band:
            for b in band:
                if a is b or not (a["ladder_ok"] and b["ladder_ok"]):
                    continue
                te = transfer_error(a, b)
                if te is None:
                    continue
                # AND THE EVIDENCE A TARGET WITHOUT A LADDER WOULD STILL HAVE.
                # `same_calibration` cannot license a transfer - a pair whose
                # calibrations agree is a pair that both read, and needs none.
                # The tick signature and the geometry ARE available when the
                # target reads nothing, so they are carried on the same row and
                # the question becomes whether they predict the error.
                tm = match_ticks(a["ticks"], b["ticks"])
                T.add("TRANSFER_CHECK", group_id=gid, target=a["label"],
                      source=b["label"], status=status,
                      target_box=T.box(a["box"]), source_box=T.box(b["box"]),
                      source_eligibility=b["eligibility"],
                      overlap_share=round(_overlap_share(a["run"], b["run"]), 3),
                      same_calibration=(a.get("calibration_sha")
                                        == b.get("calibration_sha")),
                      d_baseline=(None if a["baseline"] is None
                                  or b["baseline"] is None
                                  else int(a["baseline"]) - int(b["baseline"])),
                      d_axis_top=(None if not (a["run"] and b["run"])
                                  else int(a["run"][0]) - int(b["run"][0])),
                      d_axis_bottom=(None if not (a["run"] and b["run"])
                                     else int(a["run"][1]) - int(b["run"][1])),
                      **dict(tm, **te))
        groups.append((gid, status, [p["label"] for p in band],
                       (provider or {}).get("label", "")))
    return groups
