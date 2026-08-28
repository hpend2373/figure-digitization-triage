# -*- coding: utf-8 -*-
"""The routed reader on a REAL twin-axis scatter, and the one number it turns on.

    python3 forward_test_464_scatter.py [PROPOSALS_CSV]

Publication 464 Figure 2 is the figure the whole twin-axis capability was built
for: total peripheral resistance against central venous pressure as open and
filled CIRCLES on a left scale at 10-35, a splanchnic resistance index as open
and filled TRIANGLES on a right scale at 20-90, one shared x, a dashed
regression line through each cloud. `read_scatter_panel` refuses it, and asked
instead for ONE monochrome series the same panel returns 247 marks and
r = 0.008 where both clouds fall steeply.

WHAT v9.15 MEASURED ON THE CLIP, and it is history rather than a current result:

    marker scale measured                13 px off the panel's own components
    candidate marks                      33, of which 6 are not markers
    the SHAPE axis                       SEPARATED, index 4.33
    the PANEL-WIDE FILL axis             did NOT: 25 marks between 0.11 and
                                         0.54, six between 0.78 and 1.00, and
                                         `_split` declined the 25|6 cut because
                                         six of thirty-one is under a quarter.
                                         The best cut it would take was 24|7 at
                                         1.858, under the 2.0 required.
    marks routed                         0

THAT WAS A RESULT ABOUT A GRAIN THIS PACKAGE NO LONGER USES. v9.16 asks the fill
question inside each measured SHAPE, because the interior-ink window of a hollow
triangle is not a hollow circle's and a panel-wide split pools two distributions
into one - which is exactly what a low band running from 0.11 to 0.54 looks like.
The 25 in that band are open circles AND open triangles together, and their
combined spread is what held the index at 1.858.

So the honest statement of 464 Figure 2's status is:

    under v9.15's panel-wide grain     negative, for a reason that was one number
    under v9.16's per-shape grain      NOT MEASURED

and this script does not guess which way it will go. It prints the panel-wide
diagnostic AND each shape's own group, and its verdict follows the routed count
it actually observed. Promoting 464 to a positive forward test needs more than a
non-zero count in any case: `png/verify.py` and this package's own rules ask for
a human-reviewed marker truth file bound to the clip's SHA-256, and there is
none.

Nothing here changes a constant to make this figure read. Widening a guard so a
wanted answer appears is the move this package refuses everywhere else.

`PROPOSALS_CSV` is `propose.py` output holding a panel row for 464|Fig. 2. With
no argument the proposer is run over the corpus clip, which takes about a
minute.
"""
import collections
import csv
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CLIP = "clips/ID464__fig2.png"
#: The four series the figure draws, in the vocabulary the router declares in.
SERIES = (dict(Series_ID="TPR_OPEN", Marker_Shape="CIRCLE", Marker_Fill="OPEN",
               Axis_ID="Y_LEFT"),
          dict(Series_ID="TPR_FILLED", Marker_Shape="CIRCLE",
               Marker_Fill="FILLED", Axis_ID="Y_LEFT"),
          dict(Series_ID="SVRI_OPEN", Marker_Shape="TRIANGLE",
               Marker_Fill="OPEN", Axis_ID="Y_RIGHT"),
          dict(Series_ID="SVRI_FILLED", Marker_Shape="TRIANGLE",
               Marker_Fill="FILLED", Axis_ID="Y_RIGHT"))


def _index(split):
    """The separation index behind a `Split`, which the namedtuple stores apart."""
    return (float(split["between"]) / float(split["within"])
            if float(split["within"]) else float("inf"))


def _best_cuts(values):
    """(largest index at any cut, largest at an ADMISSIBLE one), with sizes.

    The second is what `_split` may take; the first is what the distribution
    plainly shows. Where they differ, the minimum-cluster rule is the whole
    reason a panel does not separate, and that is a sentence somebody can act
    on rather than a False nobody can interrogate.
    """
    import numpy as np
    xs = np.array(sorted(float(v) for v in values), dtype=float)
    floor = max(2, len(xs) // 4)
    any_best, adm_best = None, None
    for cut in range(1, len(xs)):
        lo, hi = xs[:cut], xs[cut:]
        if min(len(lo), len(hi)) < 2:
            continue
        spread = lo.std() + hi.std()
        index = ((hi.mean() - lo.mean()) / spread if spread > 1e-9
                 else float("inf"))
        entry = (round(float(index), 4), len(lo), len(hi))
        if any_best is None or index > any_best[0]:
            any_best = entry
        if min(len(lo), len(hi)) >= floor and (adm_best is None
                                               or index > adm_best[0]):
            adm_best = entry
    return dict(largest=any_best, admissible=adm_best, minimum_cluster=floor,
                n=int(len(xs)))


def corpus_root():
    """The first root holding the corpus this figure lives in, or "".

    THE SAME PRIVATE SOURCE AS THE RASTERS. 464 Figure 2 is a publisher figure;
    this repository is public and does not carry it, so without a root there is
    nothing to measure and this script says so and exits 0 rather than failing.
    """
    import raster_root as RR
    for root in [HERE] + RR.roots():
        if all(os.path.exists(os.path.join(root, n))
               for n in ("dig201.csv", "clips201.csv", CLIP)):
            return root
    return ""


def proposals(out_csv=None, root=None):
    """Run `propose.py` over the 464 clip and return the CSV it wrote."""
    root = root or corpus_root() or HERE
    out_csv = out_csv or os.path.join(tempfile.mkdtemp(prefix="fdt_464_"),
                                      "p464.csv")
    env = dict(os.environ, FIGS="464|Fig. 2", OUT=out_csv,
               DIG=os.path.join(root, "dig201.csv"),
               CLIPS=os.path.join(root, "clips201.csv"),
               CAPS=os.path.join(root, "captions.csv"),
               CLIP_ROOT=os.path.join(root, "clips"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "propose.py")],
                       cwd=root, env=env, capture_output=True, text=True)
    if r.returncode != 0:                                     # pragma: no cover
        raise SystemExit("propose.py failed:\n%s%s" % (r.stdout, r.stderr))
    return out_csv


def measure(props_csv, root=None):
    """Every number this forward test reports, off the real clip."""
    from PIL import Image
    rows = [r for r in csv.DictReader(open(props_csv, encoding="utf-8"))
            if r.get("panel") and r["pid"] == "464" and r["fig"] == "Fig. 2"]
    if not rows:                                              # pragma: no cover
        raise SystemExit("%s carries no panel row for 464 Fig. 2" % props_csv)
    prop = rows[0]
    box = (int(prop["plot_x0"]), int(prop["plot_x1"]),
           int(prop["plot_y0"]), int(prop["plot_y1"]))
    image = Image.open(os.path.join(root or corpus_root() or HERE,
                                    CLIP)).convert("RGB")
    return measure_panel(image, box)


def measure_panel(image, box):
    """The same numbers off ANY rendering of this panel, so the reporting path
    can be exercised on a figure this repository is allowed to hold."""
    import marker_routing as MRT
    declared = [dict(id=s["Series_ID"], shape=s["Marker_Shape"],
                     fill=s["Marker_Fill"]) for s in SERIES]
    out = MRT.route(image, box, declared)
    marks = [r for r in out["records"] if r["refusal"] != "NOT_A_MARKER"]
    fill_values = [r["interior_ink"] for r in marks
                   if r["refusal"] in ("", "MARKER_FILL_UNRESOLVED")]
    # THE GROUPS THE READER ACTUALLY ROUTES ON, since v9.16. Reporting only the
    # panel-wide split would be reporting a diagnostic as if it were the verdict
    # - which is what this script did for one release.
    groups = {}
    for shape, g in sorted((out.get("fill_groups") or {}).items()):
        kept = [r for r in marks
                if r.get("shape") == shape
                and r.get("Marker_Validity_Status") == "SINGLE_MARKER"]
        groups[shape] = dict(
            n=g["n"], low_n=g["low_n"], high_n=g["high_n"],
            threshold=g["split"]["threshold"],
            separates=bool(g["split"]["separates"]), index=g["index"],
            minimum=g["minimum"],
            interior_ink=sorted(round(float(r["interior_ink"]), 4)
                                for r in kept),
            cuts=_best_cuts([r["interior_ink"] for r in kept])
            if len(kept) >= 4 else None)
    return dict(
        panel_box=box,
        marker_scale_px=out["marker_scale_px"],
        candidates=out["Candidate_Mark_Record_Count"],
        routed=out["Routed_Point_Count"],
        unresolved=out["Unresolved_Candidate_Count"],
        refusals=dict(collections.Counter(r["refusal"] for r in out["records"]
                                          if r["refusal"])),
        by_series=dict(collections.Counter(r["Series_ID"] for r in marks
                                           if r.get("Series_ID"))),
        unresolved_by_reason=dict(collections.Counter(
            r["refusal"] for r in marks if r["refusal"])),
        identity_methods=sorted({r["Identity_Method"] for r in marks
                                 if r.get("Identity_Method")}),
        shape_separates=bool(out["shape_split"]["separates"]),
        shape_index=round(_index(out["shape_split"]), 4),
        fill_separates=bool(out["fill_split"]["separates"]),
        fill_index=round(_index(out["fill_split"]), 4),
        fill_cuts=_best_cuts(fill_values),
        groups=groups,
        declared_series=[s["Series_ID"] for s in SERIES],
        separation_required=MRT.SEPARATION)


def main():                                                   # pragma: no cover
    import raster_root as RR
    root = corpus_root()
    if not root and len(sys.argv) <= 1:
        print(RR.corpus_note(CLIP))
        print("  464 Figure 2 is a publisher figure and is not in this "
              "repository; this forward test needs the corpus")
        return
    props = sys.argv[1] if len(sys.argv) > 1 else proposals(root=root)
    report(measure(props, root=root))


def report(m):                                                # pragma: no cover
    """Everything the measurement says, and a verdict that follows from it."""
    print("464 Figure 2, routed on %s" % CLIP)
    print("  panel box                %r" % (m["panel_box"],))
    print("  marker scale             %.0f px, measured off the panel"
          % m["marker_scale_px"])
    print("  candidate marks          %d" % m["candidates"])
    print("  routed                   %d" % m["routed"])
    print("  unresolved               %d  %r" % (m["unresolved"], m["refusals"]))
    print("  shape axis separates     %s, index %.3f (needs %.1f)"
          % (m["shape_separates"], m["shape_index"], m["separation_required"]))
    print("  fill axis separates      %s, index %.3f (needs %.1f)"
          % (m["fill_separates"], m["fill_index"], m["separation_required"]))
    cuts = m["fill_cuts"]
    if cuts["largest"] and cuts["admissible"]:
        print("  the pooled distribution  %d marks; the plainest cut is %d|%d "
              "at index %.3f" % (cuts["n"], cuts["largest"][1],
                                 cuts["largest"][2], cuts["largest"][0]))
        print("  the cut _split may take  %d|%d at index %.3f, because a class "
              "must hold at least %d"
              % (cuts["admissible"][1], cuts["admissible"][2],
                 cuts["admissible"][0], cuts["minimum_cluster"]))
    # AND THE GROUPS THE READER ROUTES ON. The panel-wide numbers above are a
    # diagnostic; these are the verdict.
    print()
    print("  the fill question, asked inside each measured shape:")
    for shape, g in sorted(m["groups"].items()):
        print("    %-9s n=%-3d %-4s index %-8s threshold %-8s (min class %d)"
              % (shape, g["n"], "yes" if g["separates"] else "NO",
                 g["index"], g["threshold"], g["minimum"]))
        if g["cuts"] and g["cuts"]["largest"] and g["cuts"]["admissible"]:
            print("              plainest %d|%d at %.3f; admissible %d|%d at "
                  "%.3f"
                  % (g["cuts"]["largest"][1], g["cuts"]["largest"][2],
                     g["cuts"]["largest"][0], g["cuts"]["admissible"][1],
                     g["cuts"]["admissible"][2], g["cuts"]["admissible"][0]))
    print()
    print("  routed, by series        %r" % (m["by_series"] or "nothing",))
    print("  unresolved, by reason    %r" % (m["unresolved_by_reason"] or {},))
    print("  identity methods         %r" % (m["identity_methods"] or [],))
    print()
    # THE VERDICT FOLLOWS THE COUNT. It used to be a sentence printed whatever
    # happened, written when the panel-wide grain was the grain and left behind
    # when it stopped being - so a run that routed marks would still have said
    # the panel routes nothing.
    if not m["routed"]:
        print("  NEGATIVE: this panel routes nothing. %s"
              % ("no shape group establishes a fill split"
                 if not any(g["separates"] for g in m["groups"].values())
                 else "the shape axis does not separate"
                 if not m["shape_separates"]
                 else "every mark was refused for a reason above"))
    else:
        missing = [s for s in m["declared_series"] if s not in m["by_series"]]
        print("  %d of %d candidate marks routed, across %d of the four "
              "declared series." % (m["routed"], m["candidates"],
                                    len(m["by_series"])))
        if missing:
            print("  %s produced no point." % ", ".join(missing))
        print()
        print("  THIS IS NOT A POSITIVE FORWARD TEST AND MUST NOT BE READ AS ONE.")
        print("  A routed count is not an accuracy: there is no human-reviewed")
        print("  marker truth for this clip, bound to its SHA-256, so nothing")
        print("  here can say how many of these are RIGHT. Until that file")
        print("  exists the only claims this script makes are the counts, the")
        print("  split evidence and the refusal reasons above.")


if __name__ == "__main__":                                    # pragma: no cover
    main()
