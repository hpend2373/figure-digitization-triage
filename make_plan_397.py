"""Write `plan_397.json` from the declarations `pilot_397.py` already holds.

A one-off migration, kept because it is the honest way to produce the first
plan: the facts about publication 397 were established by measuring the
rasters, and retyping them into JSON by hand would introduce transcription
errors into the very document that exists to remove them.

Run it again after changing the pilot and diff the JSON.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The pilot runs a batch on import, so it is read as data rather than imported:
# everything above `_SOURCE_SPECS` is declaration, and nothing below it is.
SOURCE = open(os.path.join(HERE, "pilot_397.py"), encoding="utf-8").read()
NS = {"__file__": os.path.join(HERE, "pilot_397.py"), "__name__": "plan_source"}
exec(compile(SOURCE[:SOURCE.index("write(MANIFESTS)")], "pilot_397.py", "exec"), NS)

SESSIONS = NS["SESSIONS"]
HDT = NS["HDT"]
BAR_FIGURES = NS["BAR_FIGURES"]
LINE_FIGURES = NS["LINE_FIGURES"]
SPECS = NS["_SOURCE_SPECS"]
BAR_SRC = NS["BAR_ERRORBAR_SOURCE"]
LINE_SRC = NS["LINE_ERRORBAR_SOURCE"]

# Panel_ID -> the read block, built from the same tuples the pilot uses.
READ = {}
UNITS = []
VIEW_CAPTIONS = {}


def ticks(text):
    return [[float(p.split(":")[0]), float(p.split(":")[1])]
            for p in text.split(";")]


for fid, image, outcome, unit, domain, rows in BAR_FIGURES:
    VIEW_CAPTIONS[fid] = "%s, fluid versus non-fluid, by sex" % outcome
    for pid, sex, box, tick_text, xs in rows:
        uid = "U_" + pid
        READ[pid] = dict(
            mark_type="BAR_MONO", unit_id=uid, figure_view=fid, box=list(box),
            y_ticks=ticks(tick_text), y_scale="LINEAR", x_scale="LINEAR",
            baseline=float(tick_text.split(";")[1].split(":")[0]),
            config_id="C_BAR", panel_mode="AUTO",
            note="baseline is the axis minimum, not zero",
            series=[dict(series_id=s, factor="ARM", level=s, bar_fill=fill,
                         marker="NONE", line_style="NONE",
                         note="legend: %s = %s" % (fill.lower(), s))
                    for s, fill in (("FLUID", "SOLID"), ("NON_FLUID", "HATCHED"))],
            positions=[dict(position_id=level, factor="SESSION", level=level,
                            x_pixel=xs[level], timepoint_label=printed)
                       for level, printed in SESSIONS])
        UNITS.append(dict(
            unit_id=uid, figure_view=fid, grid_id="G_SESSION", panel=sex,
            outcome_name=outcome, domain=domain, unit=unit,
            statistic="CONTINUOUS", dispersion_type="SD", n_outcome=10,
            n_source="caption", bar_top_definition="OUTLINE_CENTER",
            errorbar_stem_confirmed="TRUE", errorbar_source=BAR_SRC,
            x_calibration=[[0, 100], [1, 400]]))

for fid, image, rows in LINE_FIGURES:
    VIEW_CAPTIONS[fid] = ("%s over head-down tilt, fluid versus non-fluid, by sex"
                          % ", ".join(sorted({o for _p, _s, o, _u, _b, _t, _x
                                              in rows})))
    for pid, sex, outcome, unit, box, tick_text, x_pixels in rows:
        uid = "U_" + pid
        READ[pid] = dict(
            mark_type="LINE_MONO_STYLE", unit_id=uid, figure_view=fid,
            box=list(box), y_ticks=ticks(tick_text), y_scale="LINEAR",
            x_scale="LINEAR", panel_mode="AUTO",
            series=[dict(series_id=s, factor="ARM", level=s, line_style=style,
                         marker="NONE", note="legend: %s" % style.lower())
                    for s, style in (("FLUID", "SOLID"), ("NON_FLUID", "DASHED"))],
            positions=[dict(position_id=t.replace(":", "_"),
                            factor="TIMEPOINT", level=t, timepoint_label=t,
                            x_pixel=x_pixels[o])
                       for o, t in enumerate(HDT)])
        UNITS.append(dict(
            unit_id=uid, figure_view=fid, grid_id="G_HDT", panel=sex,
            outcome_name=outcome, domain="CV_HEMO", unit=unit,
            statistic="CONTINUOUS", dispersion_type="SEM", n_outcome=10,
            n_source="text p.90", bar_top_definition="NOT_A_BAR",
            errorbar_stem_confirmed="TRUE", errorbar_source=LINE_SRC,
            x_calibration=[[0, 100], [1, 400]]))

# Figure 5 is two named individuals beat by beat: not a summary statistic, and
# no reader will ever change that. It is declared MANUAL so the panels stay
# counted rather than quietly absent.
VIEW_CAPTIONS["F397_5"] = (
    "Beat-to-beat heart rate and mean arterial pressure for two individual "
    "subjects (Y01, Y07) during no-fluid and fluid-loading head-down tilt")
for pid, label, box in (("P5_NOFLUID", "NO_FLUID_HDT", [84, 430, 60, 300]),
                        ("P5_FLUID", "FLUID_HDT", [520, 870, 60, 300])):
    READ[pid] = dict(
        mark_type="LINE_MONO", unit_id="U_" + pid, figure_view="F397_5",
        box=box, y_ticks=ticks("100:60;50:290"), y_scale="LINEAR",
        x_scale="LINEAR", panel_mode="MANUAL",
        note="n=1 per curve, beat-to-beat: no summary statistic exists to read",
        series=[dict(series_id=s, factor="ARM", level=s, marker=shape,
                     marker_fill="ANY", note="named individual subject")
                for s, shape in (("Y01", "CIRCLE"), ("Y07", "SQUARE"))],
        positions=[dict(position_id=t.replace(":", "_"), factor="TIMEPOINT",
                        level=t, timepoint_label=t,
                        x_pixel=box[0] + 25
                        + round(o * (box[1] - box[0] - 40) / (len(HDT) - 1)))
                   for o, t in enumerate(HDT)])
    UNITS.append(dict(
        unit_id="U_" + pid, figure_view="F397_5", grid_id="G_HDT", panel=label,
        outcome_name="Heart rate", domain="CV_HEMO", unit="bpm",
        statistic="CONTINUOUS", dispersion_type="NO_ERRORBAR", n_outcome=1,
        n_source="figure", bar_top_definition="NOT_A_BAR",
        errorbar_stem_confirmed="FALSE",
        errorbar_source=(
            "caption Fig. 5: 'Physiological responses (3-min means) of Y01 and "
            "Y07' - single traces, no error bars are drawn"),
        x_calibration=[[0, 100], [1, 400]],
        note="single-subject trace - not a group summary"))

PLAN = {
    "schema": "figure-digitization-triage/extraction-plan/1",
    "publication_id": 397,
    "reviewers": [dict(
        reviewer_id="RV_INSPECTOR", name="Josiah Carberry",
        record_type="DEMO_IDENTITY", contact_type="ORCID",
        contact="0000-0002-1825-0097", registered_by="Josiah Carberry",
        registration_date="2026-08-07", human_attestation="DEMO_EXAMPLE",
        note="ORCID's fictional demonstration record")],
    "documents": [dict(
        document_id="SD397_MAIN", role="MAIN_ARTICLE", source_file="397.pdf",
        page_range="full target article", observed_figure_count=5,
        inventory_status="VISUALLY_VERIFIED", figure_count_method="HUMAN_VISUAL",
        reviewer_id="RV_INSPECTOR", inspection_date="2026-08-07",
        note="all five publisher figures inventoried")],
    "grids": [
        dict(grid_id="G_SESSION", factors={"ARM": ["FLUID", "NON_FLUID"],
                                           "SESSION": [s for s, _ in SESSIONS]}),
        dict(grid_id="G_HDT", factors={"ARM": ["FLUID", "NON_FLUID"],
                                       "TIMEPOINT": list(HDT)}),
    ],
    "reader_configs": [dict(config_id="C_BAR", options={
        "group_window": 75, "threshold": 128, "stem_threshold": 200})],
    "figure_views": {k: {"caption": v} for k, v in sorted(VIEW_CAPTIONS.items())},
    "figures": [],
    "units": UNITS,
}

for number, specs in sorted(SPECS.items()):
    PLAN["figures"].append(dict(
        source_figure_id="SF397_%d" % number, document_id="SD397_MAIN",
        figure_number="FIG%d" % number, source_file="397.pdf", source_page=0,
        image="397_fig%d.jpeg" % number, observed_panel_count=len(specs),
        inventory_status="VISUALLY_VERIFIED", panel_count_method="HUMAN_VISUAL",
        reviewer_id="RV_INSPECTOR", inspection_date="2026-08-07",
        note="counted on the full publisher raster",
        panels=[dict(
            panel_id=pid, label="P%02d" % order, outcome_label=outcome,
            target_status=target, disposition=disposition,
            reason=("reader/run manifest configured" if pid in READ else
                    "visible panel inventoried; reader not configured"),
            read=READ.get(pid))
            for order, (pid, outcome, target, disposition)
            in enumerate(specs, 1)]))

OUT = os.path.join(HERE, "plan_397.json")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(PLAN, fh, indent=1, sort_keys=False, ensure_ascii=False)
    fh.write("\n")
print("%s  (%d figures, %d inventoried panels, %d configured, %d units)"
      % (OUT, len(PLAN["figures"]),
         sum(len(f["panels"]) for f in PLAN["figures"]), len(READ), len(UNITS)))
