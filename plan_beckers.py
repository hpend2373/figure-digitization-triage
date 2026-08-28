# -*- coding: utf-8 -*-
"""Beckers 2007's extraction plan, apart from the figure it is a plan about.

    import plan_beckers as PB
    PB.build_plan(pdf_name, raster, image_sha256, reviewer, inspection_date)

WHY THIS IS A MODULE. `pilot_beckers.py` refuses to run without the publisher
PDF - correctly; it is not redistributable and nothing can be read off a figure
that is not there - and the plan was built INSIDE that refusal. So CI, which has
never had the PDF, has never compiled this plan, and it drifted seventeen
releases behind the compiler: `PLAN_DOCUMENT_BYTES_UNDECLARED` (v9.2) and
`PLAN_UNIT_NAMES_NO_PANEL` (v9.1) both landed while nothing was looking, and the
pilot the package points at as its one worked example to POOLING_ELIGIBLE could
not compile at all.

A plan is a DECLARATION. Its shape can be checked without the figure, and now is:
`test_compile_plan.py` builds this one over a placeholder raster and asserts the
compiler finds nothing wrong with it that is not the absence of the file itself.
"""
import os

#: The five post-flight sessions, in the order the figures print them.
SESSIONS = [("L-30", -30), ("R+1", 1), ("R+4", 4), ("R+9", 9), ("R+25", 25)]

PANELS = [
    dict(pid="P_APEN_SUPINE", fig="SF_BECKERS_F1", view="F_APEN_SUPINE",
         number="FIG1", label="Fig 1", posture="SUPINE", grid="G_SUPINE",
         unit_id="U_APEN_SUPINE",
         box=[305, 1176, 2021, 2744], ticks=[[1.3, 2019.5], [0.2, 2746.0]],
         y_region="182,302,2009,2756", x_region="302,1179,2746,2866",
         xs=[459.5, 601.0, 741.5, 881.5, 1024.0],
         caption="Fig. 1: Evolution of ApEn (mean +/- 95% confidence interval) "
                 "in supine position up to 25 days after return to earth."),
    dict(pid="P_APEN_STANDING", fig="SF_BECKERS_F2", view="F_APEN_STANDING",
         number="FIG2", label="Fig 2", posture="STANDING", grid="G_STANDING",
         unit_id="U_APEN_STANDING",
         box=[1449, 2254, 2051, 2718], ticks=[[1.3, 2049.5], [0.2, 2720.0]],
         y_region="1326,1446,2039,2730", x_region="1446,2257,2720,2840",
         xs=[1591.0, 1721.5, 1851.5, 1981.5, 2113.0],
         caption="Fig. 2: Evolution of ApEn (mean +/- 95% confidence interval) "
                 "in standing position up to 25 days after return to earth."),
]


def build_plan(source_file, source_file_sha256, raster, image_sha256, reviewer,
               inspection_date):
    """The plan as a document, over whatever rendering it is being run on."""
    return {
        "schema": "figure-digitization-triage/extraction-plan/1",
        "publication_id": "PUB_BECKERS2007",
        "reviewers": [reviewer],
        "documents": [dict(
            document_id="SD_BECKERS", role="MAIN_ARTICLE",
            source_file=source_file,
            # WHICH BYTES THAT ARTICLE WAS. v9.2 made the figure inventory a claim
            # about a named document rather than about a filename, and this plan was
            # last touched before that; the pilot ran only where the publisher PDF
            # was on disk, so CI never compiled it and the drift was invisible for
            # seventeen releases.
            source_file_sha256=source_file_sha256,
            page_range="98-101",
            observed_figure_count=2, inventory_status="VISUALLY_VERIFIED",
            figure_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
            inspection_date=inspection_date,
            note="Beckers 2007, Microgravity Sci Technol XIX-5/6, 98-101")],
        "grids": [dict(grid_id=p["grid"],
                       factors={"SESSION": [s for s, _d in SESSIONS],
                                "POSTURE": [p["posture"]]},
                       note="one posture at five sessions") for p in PANELS],
        "reader_configs": [dict(config_id="C_APEN", options=dict(
            threshold=170, x_window=18, whisker_search_px=280,
            marker_half_height=8, stem_px=4))],
        "figure_views": {p["view"]: dict(caption=p["caption"],
                                         note="one panel, one series, five sessions")
                         for p in PANELS},
        "figures": [dict(
            source_figure_id=p["fig"], document_id="SD_BECKERS",
            figure_number=p["number"], source_file=source_file,
            source_page=3, image=raster,
            image_sha256=image_sha256,
            observed_panel_count=1, inventory_status="VISUALLY_VERIFIED",
            panel_count_method="HUMAN_VISUAL", reviewer_id="RV_INSPECTOR",
            inspection_date=inspection_date, caption=p["caption"],
            panels=[dict(
                panel_id=p["pid"], label=p["label"],
                outcome_label="ApEn %s" % p["posture"].lower(),
                target_status="TARGET", disposition="AUTO_DIGITIZE",
                reason="the figure is the only source of these means at these "
                       "sessions",
                read=dict(
                    mark_type="LINE_MONO", unit_id=p["unit_id"],
                    figure_view=p["view"], box=p["box"], y_ticks=p["ticks"],
                    y_scale="LINEAR", x_scale="LINEAR", config_id="C_APEN",
                    axis_y_region=p["y_region"], axis_x_region=p["x_region"],
                    series=[dict(series_id="S_APEN", factor="POSTURE",
                                 level=p["posture"], marker="ANY",
                                 marker_fill="OPEN")],
                    positions=[dict(position_id="%s_%d" % (p["number"], i),
                                    factor="SESSION", level=level,
                                    x_pixel=x, timepoint_label=level,
                                    timepoint_days=days)
                               for i, ((level, days), x)
                               in enumerate(zip(SESSIONS, p["xs"]))]))])
            for p in PANELS],
        "units": [dict(
            unit_id=p["unit_id"], figure_view=p["view"], grid_id=p["grid"],
            panel=p["label"],
            # AND WHICH PANEL FILLS IT, said on the unit as well as on the panel.
            # v9.1: the binding has to be declared on both sides or a swap between
            # two panels puts each posture's numbers under the other's outcome with
            # every downstream check still agreeing.
            panel_id=p["pid"],
            outcome_name="Approximate entropy of RR intervals",
            domain="AUTONOMIC", unit="dimensionless", statistic="CONTINUOUS",
            dispersion_type="CI95", n_outcome=5, n_source="TEXT_METHODS",
            bar_top_definition="MARKER_CENTER", errorbar_stem_confirmed="TRUE",
            errorbar_source="CAPTION", grid_rule="FULL", value_scale="RATIO",
            # ApEn is a bounded, roughly symmetric index and the paper analyses it
            # untransformed - it prints means and SEMs of the index itself.
            analysis_transformation="UNTRANSFORMED",
            distribution_shape="SYMMETRIC", transformation_source="",
            note="caption states mean +/- 95% confidence interval",
            x_calibration=[[0, p["xs"][0]], [4, p["xs"][-1]]]) for p in PANELS],
    }

