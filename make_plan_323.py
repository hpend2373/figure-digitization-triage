"""Write `plan_323.json` from the declarations `build_id323.py` already holds.

    python3 make_plan_323.py [OUTPUT.json] [RASTER_DIR]

Publication 323 is the corpus's only figure whose caption STATES what its error
bars are - "Data are given for a group of 10 subjects (Mean +/- SEM)" - and that
is the one declaration publication 397 cannot make. 397's units are held by
`UNRESOLVED_ERRORBAR_DEFINITION` on every panel, so no value of its 123 reaches a
review queue and `PILOT.md` steps 4 and 5 have never been walked on a real
figure. This plan exists to make that walk possible.

NOTHING HERE IS A NEW CLAIM ABOUT THE PUBLICATION. Every declaration is read out
of `build_id323.py`, which ships, runs in CI and has produced the package's
hand-reconciled worked example since v7.2: the panel boxes, the printed tick
values, the two series and their colour masks, the factor levels, the caption
verbatim, `Dispersion_Type=SEM` and its source, `N_Outcome=10`,
`Bar_Top_Definition` and `Errorbar_Stem_Confirmed`. The geometry that is
MEASURED rather than declared - each panel's tick pixel rows and each
timepoint's group centre - is measured here from the same raster by the same
functions, because retyping measured numbers into JSON by hand would put
transcription errors into the document that exists to remove them.

## What this record does and does not claim

The document record covers PAGES 4-5 and the two figures printed there, and
within that range its inventory is complete. The article has four figures;
Figures 3 and 4 are a PSI spectrum and three panels of PSI and spectral density,
their rasters are not held here, and the source layer refuses - correctly, in
`compile_plan` and again in `batch_manifests` - to inventory a figure whose raster
the package does not have. `Article_Page_Range` is where that bound is stated, so
this is a narrower true claim rather than a wider unverifiable one. Whether those
two figures are in scope for this review is undecided and is not decided here.

The reviewer is ORCID's fictional demonstration record, so a run built from this
plan is `DEMO_ONLY` and accepts nothing: 102 values pass machine QC and
`DEMO_OUTPUT_REFUSED` writes none of them. Registering the person who actually
inspected the figures is the remaining step, and it is an attestation - which is
why nothing in this file makes it.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from bar_reader import (colour_masks, read_bar_panel,             # noqa: E402
                        x_category_columns)

#: `build_id323.py` runs a whole extraction on import, so it is read as DATA:
#: everything above `figs=[]` is declaration and nothing below it is. The same
#: split `make_plan_397.py` uses on the 397 pilot.
_MARKER = "figs=[];grids=[]"
_SOURCE = open(os.path.join(HERE, "build_id323.py"), encoding="utf-8").read()
_NS = {"__file__": os.path.join(HERE, "build_id323.py"), "__name__": "plan_323"}
exec(compile(_SOURCE[:_SOURCE.index(_MARKER)], "build_id323.py", "exec"), _NS)

FIGS = _NS["FIGS"]
SESSIONS = _NS["SESS"]
CAPTION_SOURCE = _NS["SRC"]

#: WHAT THE METHODS SAY, which is what `INSTALL.md` has been asking for. The open
#: list has carried "ID 323 and 397 both need their SD/SEM wording resolved from
#: the methods text" since v7.2, and `build_id323` declares SEM on the CAPTION
#: alone. For 323 the methods text settles it, and it settles it the same way, so
#: the declaration is unchanged and its evidence is now the sentence the open item
#: asked for. Quoted rather than summarised: `Errorbar_Definition_Source` is read
#: by `fig_unresolved_marker`, and a paraphrase is not a source.
#:
#: 397 is NOT resolved by this. Its own methods are silent, which is why its
#: source string still contains "NOT STATED" and its units are still held.
METHODS_SOURCE = (
    'methods (Statistics): "The values are given as mean and SEM, besides '
    'anthropometric data and time intervals which are given as mean and SD." '
    "The hemodynamic values of Figures 1 and 2 are the former. Caption of both "
    "figures, verbatim, agreeing: " + _NS["SRC"])
ticks_of = _NS["ticks_of"]

#: 323's outcome names are the panel labels; the domain is the one this package
#: has, and the unit comes with the panel.
DOMAIN = "CV_HEMO"

DOCUMENT_ID = "SD323_MAIN"
SOURCE_FILE = "323_10.3389_fphys.2020.00455.pdf"


def _number(fid):
    """`1` from `323|FIG1`."""
    return fid.split("FIG")[1]


def _panel_id(fid, name):
    """`P1_SAP` from `323|FIG1` and `SAP` - a run panel id, not a figure key."""
    return "P%s_%s" % (_number(fid), name)


def _view_id(fid):
    """`F323_1`. `build_id323`'s own ids are pipe-separated figure KEYS, which
    the plan layer refuses as unsafe - and rightly: these become manifest
    foreign keys and a `|` in one is a delimiter inside a value."""
    return "F323_%s" % _number(fid)


def _grid_id(fig):
    """`G_SESSION6_POSTURE2` from `GRID|SESSION6xPOSTURE2`, for the same reason."""
    return "G_" + fig["gid"].split("|", 1)[1].replace("x", "_")


def _series_blocks(series):
    # THE MASK AND NOTHING ELSE. Declaring `Colour_Hex` beside `Mask_Key` is
    # `SERIES_DISCRIMINANT_AMBIGUOUS`, and rightly so: two discriminants for one
    # series is two answers to "which ink is this", and the reader can only obey
    # one. `build_id323` declares the mask, so the mask is what this carries.
    # THE FACTOR A SINGLE SERIES CARRIES IS STILL A FACTOR. `ARM` was wrong
    # twice over: 323 has no arms, and the grid did not declare it - the runner
    # puts a series factor into every `Cell_Key` whether or not the series is
    # alone, so Figure 2's values came out as `ARM=RESPONSE;TIMEPOINT=B-1`
    # against a grid of `{TIMEPOINT}` and every one of them was
    # `FACTOR_SET_INCONSISTENT`. `SERIES` is what it is, it is declared in the
    # grid beside `TIMEPOINT`, and the cell count is unchanged at 6x1.
    return [dict(series_id=name,
                 factor="POSTURE" if len(series) > 1 else "SERIES",
                 level=name, mask_key=key,
                 marker="NONE", line_style="NONE", bar_fill="SOLID",
                 note="build_id323 declares the %s mask for %s" % (key, name))
            for name, key in sorted(series.items())]


def _positions(centres, levels):
    """One x per category, as the FIGURE prints it.

    `x_category_columns` reads the panel's own category row, so a category that
    drew no bar still gets its place. The first version of this function averaged
    the x of the bars that WERE read and fitted the rest - which is the reading
    that produced the v8.6 defect, and it announced itself immediately: fitting
    323 FIG2 DAP's five bars as if they were slots 0..4 put the sixth at x=2027,
    outside the panel, and `POSITION_OUTSIDE_PANEL` caught it.
    """
    if centres is None or len(centres) != len(levels):
        raise SystemExit(
            "BLOCKED: this panel does not print %d categories where a reader can "
            "find them, and nothing here may invent where they are"
            % len(levels))
    return [dict(position_id=level, factor="TIMEPOINT", level=level,
                 x_pixel=int(round(centre)), slot_index=order,
                 display_order=order, timepoint_label=level)
            for order, (level, centre) in enumerate(zip(levels, centres))]


def build(raster_root=None):
    """The whole plan, as a dict."""
    root = raster_root or HERE
    reviewers = [dict(
        reviewer_id="RV_INSPECTOR", name="Josiah Carberry",
        record_type="DEMO_IDENTITY", contact_type="ORCID",
        contact="0000-0002-1825-0097", registered_by="Josiah Carberry",
        registration_date="2026-08-17", human_attestation="DEMO_EXAMPLE",
        note="ORCID's fictional demonstration record; pilot_323.py replaces it")]
    documents = [dict(
        document_id=DOCUMENT_ID, role="MAIN_ARTICLE", source_file=SOURCE_FILE,
        # THE RANGE IS PART OF THE CLAIM, which is what `Article_Page_Range` is
        # for. The article has FOUR figures; this document record covers pages
        # 4-5 and the two figures printed there, and within that range the
        # inventory is complete. A narrower true claim rather than a wider one
        # that would need Figures 3 and 4 on disk to be checkable - the source
        # layer refuses to inventory a figure whose raster the package does not
        # hold, in `compile_plan` and again in `batch_manifests`, and that rule
        # is right.
        #
        # SAID OUT LOUD so nobody reads this as "the article has two figures":
        # Figures 3 and 4 are a PSI spectrum and three panels of PSI and
        # spectral density, and whether they are in scope for this review is
        # undecided. Widening this record to four is what admitting them costs.
        page_range="pages 4-5 (Figures 1 and 2); the article's Figures 3 and 4 "
                   "are outside this record and their rasters are not held",
        observed_figure_count=2, inventory_status="VISUALLY_VERIFIED",
        figure_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
        inspection_date="2026-08-17",
        note="two figures on pages 4-5, both inventoried. The reviewer is the "
             "demonstration identity unless pilot_323.py is given a real one, "
             "and the run is DEMO_ONLY either way")]
    grids, figures, units, views = [], [], [], {}
    # THE DEFAULTS, EXCEPT THE ONE build_id323 PASSES. It calls
    # `read_bar_panel(masks, box, ticks, series, baseline_value=0.0)` and takes
    # every other option as it comes, so declaring anything else here would be
    # this file tuning a reader the worked example did not tune.
    configs = [dict(config_id="C_COLOUR_BAR", options=dict(baseline_value=0.0))]
    for fig in FIGS:
        fid = fig["fid"]
        image = os.path.join(root, fig["img"])
        raster = Image.open(image).convert("RGB")
        masks = colour_masks(raster)
        # AND THE GRID DECLARES IT. `build_id323`'s factor table is the
        # analysis grid; a panel with one series still has that series in every
        # cell key, so the grid this plan compiles has to name it or the two
        # grains disagree by construction.
        factors = dict(fig["factors"])
        if len(fig["series"]) == 1:
            factors["SERIES"] = sorted(fig["series"])
        grids.append(dict(grid_id=_grid_id(fig), factors=factors))
        views[_view_id(fid)] = dict(caption=fig["cap"])
        panels = []
        for name, box, tick_values, outcome, unit in fig["panels"]:
            pid = _panel_id(fid, name)
            uid = "U_" + pid
            rows = ticks_of(masks["dark"], box, len(tick_values))
            y_ticks = [[float(v), float(p)] for v, p in zip(tick_values, rows)]
            levels = fig["factors"]["TIMEPOINT"]
            centres = x_category_columns(masks["dark"], box, len(levels))
            panels.append(dict(
                panel_id=pid, label=name, outcome_label="%s (%s)" % (outcome, unit),
                target_status="TARGET", disposition="AUTO_DIGITIZE",
                reason="reader/run manifest configured",
                note=("this panel is one build_id323 lists as UNLISTED on the "
                      "original worklist" if name == fig["unlisted"] else ""),
                read=dict(
                    mark_type="BAR_COLOR", unit_id=uid, figure_view=_view_id(fid),
                    box=list(box), y_ticks=y_ticks, y_scale="LINEAR",
                    x_scale="LINEAR", baseline=0.0,
                    config_id=configs[0]["config_id"], panel_mode="AUTO",
                    note="tick rows and printed category columns measured "
                         "from %s" % fig["img"],
                    series=_series_blocks(fig["series"]),
                    positions=_positions(centres, levels))))
            units.append(dict(
                unit_id=uid, panel_id=pid, figure_view=_view_id(fid),
                grid_id=_grid_id(fig), panel=name,
                outcome_name=outcome, domain=DOMAIN, unit=unit,
                statistic="CONTINUOUS",
                # THE DECLARATION THIS PLAN EXISTS FOR, and it is build_id323's,
                # not this file's: the caption states it in words.
                dispersion_type="SEM", errorbar_source=METHODS_SOURCE,
                n_outcome=10, n_source="caption",
                bar_top_definition="OUTLINE_CENTER",
                errorbar_stem_confirmed="TRUE",
                value_scale=fig["scale"],
                x_calibration=[[0, box[0]], [1, box[1]]]))
        figures.append(dict(
            source_figure_id="SF323_%s" % _number(fid),
            document_id=DOCUMENT_ID, figure_number="FIG%s" % _number(fid),
            source_file=SOURCE_FILE, source_page=fig["page"], image=fig["img"],
            observed_panel_count=fig["obs"], inventory_status="VISUALLY_VERIFIED",
            panel_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
            inspection_date="2026-08-17",
            note="panel count and the unlisted panel are build_id323's, which "
                 "has shipped them since v7.2",
            panels=panels))
    return dict(schema="figure-digitization-triage/extraction-plan/1",
                publication_id=323, reviewers=reviewers, documents=documents,
                grids=grids, reader_configs=configs, figure_views=views,
                figures=figures, units=units)


def main(argv):
    out = argv[0] if argv else os.path.join(HERE, "plan_323.json")
    root = argv[1] if len(argv) > 1 else HERE
    plan = build(root)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %s: %d figure(s), %d panel(s), %d unit(s)"
          % (out, len(plan["figures"]),
             sum(len(f["panels"]) for f in plan["figures"]), len(plan["units"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
