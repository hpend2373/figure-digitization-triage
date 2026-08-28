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

WHAT THE ROUTED READER DOES WITH IT, on the clip this corpus carries:

    marker scale measured                13 px off the panel's own components
    candidate marks                      33, of which 6 are not markers
    the SHAPE axis                       SEPARATES, index 4.33
    the FILL axis                        does NOT, and this is the whole finding
    marks routed                         0
    every mark's answer                  MARKER_FILL_UNRESOLVED

So this is a NEGATIVE forward test, and it is negative for a reason that is one
number rather than a shrug. The interior-ink distribution of these 31 marks has
a plain gap: 25 of them between 0.11 and 0.54, six between 0.78 and 1.00. Split
there and the separation index is 2.70, comfortably over the 2.0 this package
requires. `marker_routing._split` will not take that cut, because it refuses a
cluster holding fewer than a quarter of the marks - "an outlier is not a class" -
and six of thirty-one is under a quarter. The best cut it will take is 24/7,
which scores 1.858, and 1.858 is under 2.0, so the panel establishes no fill
split and every mark is refused.

    THE QUESTION THIS PUTS TO A PERSON, and does not answer: is a class holding
    six of thirty-one marks an outlier, or is it the smaller of four series a
    figure actually drew? On `twin_scatter_*.jpeg` the four series are 10, 8, 6
    and 6 of 30, so the fixture's own smallest class is a fifth - and the fixture
    never exercised the rule, because its FILL classes are 16 and 14. A real
    four-series panel with unequal groups is where the quarter bites.

Nothing here changes that constant to make this figure read. Widening a guard so
a wanted answer appears is the move this package refuses everywhere else, and
the measurement above is what the decision should be made on rather than the
wish. Until it is made, 464 Figure 2 stays a refusal - and the refusal is now
per mark, with the evidence recorded, instead of a panel nobody could look at.

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
    """Every number this forward test pins, off the real clip."""
    from PIL import Image
    import marker_routing as MRT
    rows = [r for r in csv.DictReader(open(props_csv, encoding="utf-8"))
            if r.get("panel") and r["pid"] == "464" and r["fig"] == "Fig. 2"]
    if not rows:                                              # pragma: no cover
        raise SystemExit("%s carries no panel row for 464 Fig. 2" % props_csv)
    prop = rows[0]
    box = (int(prop["plot_x0"]), int(prop["plot_x1"]),
           int(prop["plot_y0"]), int(prop["plot_y1"]))
    image = Image.open(os.path.join(root or corpus_root() or HERE,
                                    CLIP)).convert("RGB")
    declared = [dict(id=s["Series_ID"], shape=s["Marker_Shape"],
                     fill=s["Marker_Fill"]) for s in SERIES]
    out = MRT.route(image, box, declared)
    marks = [r for r in out["records"] if r["refusal"] != "NOT_A_MARKER"]
    fill_values = [r["interior_ink"] for r in marks
                   if r["refusal"] in ("", "MARKER_FILL_UNRESOLVED")]
    return dict(
        panel_box=box,
        marker_scale_px=out["marker_scale_px"],
        candidates=out["Candidate_Mark_Record_Count"],
        routed=out["Routed_Point_Count"],
        unresolved=out["Unresolved_Candidate_Count"],
        refusals=dict(collections.Counter(r["refusal"] for r in out["records"]
                                          if r["refusal"])),
        shape_separates=bool(out["shape_split"]["separates"]),
        shape_index=round(_index(out["shape_split"]), 4),
        fill_separates=bool(out["fill_split"]["separates"]),
        fill_index=round(_index(out["fill_split"]), 4),
        fill_cuts=_best_cuts(fill_values),
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
    m = measure(props, root=root)
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
    print("  the fill distribution    %d marks; the plainest cut is %d|%d at "
          "index %.3f" % (cuts["n"], cuts["largest"][1], cuts["largest"][2],
                          cuts["largest"][0]))
    print("  the cut _split may take  %d|%d at index %.3f, because a class must "
          "hold at least %d" % (cuts["admissible"][1], cuts["admissible"][2],
                                cuts["admissible"][0], cuts["minimum_cluster"]))
    print()
    print("  So the panel does not establish its fill axis and routes nothing.")
    print("  The question this leaves for a person: is a class holding %d of %d"
          % (cuts["largest"][2], cuts["n"]))
    print("  marks an outlier, or the smaller of four series the figure drew?")
    print("  Nothing here changes the constant to make the answer come out.")


if __name__ == "__main__":                                    # pragma: no cover
    main()
