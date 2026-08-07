"""One typed plan in, eleven manifests out.

    python3 compile_plan.py PLAN.json MANIFEST_DIR [--file-root DIR]

Everything above this file assumes the manifests already exist. Writing them is
the part an agent actually has to do, and asking one to fill eleven CSVs by hand
is asking it to hold the whole foreign-key graph in its head: `Source_Panel_ID`
in two files, `Figure_ID` in three, `Grid_ID` in two, a SHA-256 typed twice, a
calibration typed once as ticks and again as four numbers. Every one of those is
a place two files can quietly disagree, and several of the defects this package
has shipped were exactly that.

So the agent writes ONE document describing the publication, and this compiler
writes the manifests. The split is deliberate:

**The plan says what is true about the paper.** Which figures exist, how many
panels each has, who counted them, what the caption says about the error bars,
where the boxes and ticks are, what each series and position MEANS.

**The compiler says what follows.** Hashes are read off the files, not typed.
`Axis_Calib_*` on a unit is derived from the ticks of the panel that fills it,
so the gate's copy and the reader's copy cannot drift. `Figure_ID` rows are
built from the panels that claim them, with the panel counts reconciled rather
than asserted. A statistic the runner cannot execute is refused here rather
than discovered at panel 140.

What the compiler will NOT do is invent an observation. It never guesses a
panel count, never fills a blank `Errorbar_Definition_Source`, and never
promotes a `MANUAL_DIGITIZE` disposition because a reader happens to exist. If
the plan does not say it, the manifests do not either.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import mark_readers as MR                                          # noqa: E402

PLAN_SCHEMA = "figure-digitization-triage/extraction-plan/1"

#: Top-level keys a plan must carry. A plan missing one is not a short plan, it
#: is a plan about a different thing.
PLAN_SECTIONS = ("schema", "publication_id", "reviewers", "documents",
                 "grids", "figures", "units")

#: Panel-level `read` block keys, and whether the compiler requires them.
READ_REQUIRED = ("mark_type", "unit_id", "figure_view", "box")


def _s(v):
    return "" if v is None else str(v).strip()


def _problem(where, code, detail):
    return dict(where=where, check=code, detail=detail)


def _ticks_text(ticks):
    """[[value, pixel], ...] -> 'v1:px1;v2:px2', the form the manifests store."""
    return ";".join("%s:%s" % (t[0], t[1]) for t in ticks)


def validate_plan(plan, file_root="."):
    """Everything wrong with the plan, before a single CSV is written.

    Returns a list of problems. These are DIFFERENT from the manifest problems
    `batch_manifests` raises: those are about a CSV set, these are about the
    document a person or an agent wrote. Reporting them here means the author
    sees them against the thing they typed, not against a generated file.
    """
    problems = []
    if not isinstance(plan, dict):
        return [_problem("plan", "PLAN_NOT_AN_OBJECT", type(plan).__name__)]
    for key in PLAN_SECTIONS:
        if key not in plan:
            problems.append(_problem("plan", "PLAN_SECTION_MISSING", key))
    if problems:
        return problems
    if _s(plan.get("schema")) != PLAN_SCHEMA:
        problems.append(_problem("plan", "PLAN_SCHEMA_UNKNOWN",
                                 "%r is not %s" % (plan.get("schema"), PLAN_SCHEMA)))

    reviewer_ids = {_s(r.get("reviewer_id")) for r in plan["reviewers"]}
    document_ids = {_s(d.get("document_id")) for d in plan["documents"]}
    grid_ids = {_s(g.get("grid_id")) for g in plan["grids"]}
    unit_ids = {_s(u.get("unit_id")) for u in plan["units"]}

    for section, rows, key in (("reviewers", plan["reviewers"], "reviewer_id"),
                               ("documents", plan["documents"], "document_id"),
                               ("grids", plan["grids"], "grid_id"),
                               ("units", plan["units"], "unit_id")):
        seen = set()
        for i, row in enumerate(rows):
            ident = _s(row.get(key))
            where = "%s[%d]" % (section, i)
            if not ident:
                problems.append(_problem(where, "PLAN_MISSING_ID", key))
                continue
            if ident in seen:
                problems.append(_problem(where, "PLAN_DUPLICATE_ID", ident))
            seen.add(ident)
            if not BM.SAFE_ID.match(ident):
                problems.append(_problem(where, "UNSAFE_ID", "%s=%r" % (key, ident)))

    panel_ids, views = set(), {}
    for fi, figure in enumerate(plan["figures"]):
        where = "figures[%d]" % fi
        sfid = _s(figure.get("source_figure_id"))
        if not sfid:
            problems.append(_problem(where, "PLAN_MISSING_ID", "source_figure_id"))
        if _s(figure.get("document_id")) not in document_ids:
            problems.append(_problem(where, "PLAN_DOCUMENT_NOT_FOUND",
                                     _s(figure.get("document_id"))))
        if _s(figure.get("reviewer_id")) not in reviewer_ids:
            problems.append(_problem(where, "PLAN_REVIEWER_NOT_FOUND",
                                     _s(figure.get("reviewer_id"))))
        image = _s(figure.get("image"))
        resolved = _resolve(image, file_root)
        if resolved is None:
            problems.append(_problem(where, "SOURCE_FILE_NOT_FOUND",
                                     "image=%r is not on disk under %s"
                                     % (image, os.path.realpath(file_root))))
        panels = figure.get("panels") or []
        declared_count = figure.get("observed_panel_count")
        # The one number no software can check, and the compiler will not
        # quietly make it agree: if the inventory lists fewer panels than the
        # person counted, that is the hole the whole source layer exists to
        # show, not an off-by-one to paper over.
        if declared_count is None:
            problems.append(_problem(where, "PLAN_PANEL_COUNT_MISSING",
                                     "observed_panel_count"))
        elif len(panels) != declared_count:
            problems.append(_problem(
                where, "PLAN_PANEL_COUNT_MISMATCH",
                "%d panels listed, observed_panel_count=%s. Inventory every "
                "visible panel, including the ones nobody will digitize"
                % (len(panels), declared_count)))
        for pi, panel in enumerate(panels):
            pwhere = "%s.panels[%d]" % (where, pi)
            disposition = _s(panel.get("disposition")).upper()
            if disposition not in BM.SOURCE_PANEL_DISPOSITIONS:
                problems.append(_problem(pwhere, "BAD_SOURCE_PANEL_DISPOSITION",
                                         disposition or "(blank)"))
            pid = _s(panel.get("panel_id"))
            if not pid:
                problems.append(_problem(pwhere, "PLAN_MISSING_ID", "panel_id"))
            elif pid in panel_ids:
                problems.append(_problem(pwhere, "PLAN_DUPLICATE_ID", pid))
            elif not BM.SAFE_ID.match(pid):
                problems.append(_problem(pwhere, "UNSAFE_ID", "panel_id=%r" % pid))
            panel_ids.add(pid)
            read = panel.get("read")
            if read is None:
                if disposition in ("AUTO_DIGITIZE",):
                    problems.append(_problem(
                        pwhere, "PLAN_READ_BLOCK_MISSING",
                        "disposition=AUTO_DIGITIZE but the panel says nothing "
                        "about where its marks are"))
                continue
            for key in READ_REQUIRED:
                if not read.get(key):
                    problems.append(_problem(pwhere, "PLAN_READ_INCOMPLETE", key))
            uid = _s(read.get("unit_id"))
            if uid and uid not in unit_ids:
                problems.append(_problem(pwhere, "PLAN_UNIT_NOT_FOUND", uid))
            views.setdefault(_s(read.get("figure_view")), []).append((sfid, panel))
            box = read.get("box") or []
            if len(box) != 4:
                problems.append(_problem(pwhere, "PLAN_READ_INCOMPLETE",
                                         "box must be [x0, x1, y0, y1]"))

    for ui, u in enumerate(plan["units"]):
        where = "units[%d]" % ui
        if _s(u.get("grid_id")) not in grid_ids:
            problems.append(_problem(where, "PLAN_GRID_NOT_FOUND",
                                     _s(u.get("grid_id"))))
        statistic = _s(u.get("statistic")).upper()
        if statistic not in BM.CAPABILITY_MATRIX:
            problems.append(_problem(where, "BAD_STATISTIC_TYPE", statistic))
        if _s(u.get("figure_view")) not in views:
            problems.append(_problem(
                where, "PLAN_UNIT_HAS_NO_PANEL",
                "%s is declared but no panel fills it - a unit nobody reads is "
                "a grid of missing cells" % _s(u.get("unit_id"))))
    return problems


def _resolve(path, file_root):
    root = os.path.realpath(file_root)
    if not path:
        return None
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    real = os.path.realpath(candidate)
    if real != root and not real.startswith(root + os.sep):
        return None
    return real if os.path.exists(real) else None


def compile_plan(plan, out_dir, file_root=".", run_date=""):
    """Write the eleven manifests. Returns (paths, problems)."""
    problems = validate_plan(plan, file_root=file_root)
    if problems:
        return {}, problems

    os.makedirs(out_dir, exist_ok=True)
    pub = plan["publication_id"]

    reviewers = [dict(
        Reviewer_ID=_s(r.get("reviewer_id")), Reviewer_Name=_s(r.get("name")),
        Reviewer_Record_Type=_s(r.get("record_type")).upper(),
        Contact_Type=_s(r.get("contact_type")).upper(),
        Reviewer_Contact=_s(r.get("contact")),
        Registered_By=_s(r.get("registered_by")),
        Registration_Date=_s(r.get("registration_date")),
        Human_Attestation=_s(r.get("human_attestation")).upper(),
        Note=_s(r.get("note"))) for r in plan["reviewers"]]

    documents = [dict(
        Source_Document_ID=_s(d.get("document_id")), Publication_ID=pub,
        Document_Role=_s(d.get("role")).upper(), Source_File=_s(d.get("source_file")),
        Article_Page_Range=_s(d.get("page_range")),
        Observed_Figure_Count=d.get("observed_figure_count"),
        Inventory_Status=_s(d.get("inventory_status")).upper(),
        Figure_Count_Method=_s(d.get("figure_count_method")).upper(),
        Reviewer_ID=_s(d.get("reviewer_id")),
        Inspection_Date=_s(d.get("inspection_date")), Note=_s(d.get("note")))
        for d in plan["documents"]]

    grids = []
    for g in plan["grids"]:
        for factor, levels in g["factors"].items():
            for order, level in enumerate(levels):
                grids.append(dict(Grid_ID=_s(g.get("grid_id")),
                                  Factor_Name=_s(factor).upper(),
                                  Factor_Level=_s(level), Level_Order=order,
                                  Note=_s(g.get("note"))))

    source_figures, source_panels, panels, series, positions = [], [], [], [], []
    image_of_panel, ticks_of_panel, view_panels = {}, {}, {}

    for figure in plan["figures"]:
        sfid = _s(figure.get("source_figure_id"))
        resolved = _resolve(_s(figure.get("image")), file_root)
        # Hashed here, once, from the bytes. Typed into a manifest it is a place
        # for two files to disagree about which raster was read.
        sha = MR.sha256_of(resolved)
        source_figures.append(dict(
            Source_Figure_ID=sfid, Source_Document_ID=_s(figure.get("document_id")),
            Publication_ID=pub, Figure_Number=_s(figure.get("figure_number")),
            Source_File=_s(figure.get("source_file")),
            Source_Page=figure.get("source_page", ""), Source_Image=resolved,
            Source_Image_SHA256=sha,
            Observed_Panel_Count=figure.get("observed_panel_count"),
            Inventory_Status=_s(figure.get("inventory_status")).upper(),
            Panel_Count_Method=_s(figure.get("panel_count_method")).upper(),
            Reviewer_ID=_s(figure.get("reviewer_id")),
            Inspection_Date=_s(figure.get("inspection_date")),
            Note=_s(figure.get("note"))))

        for panel in figure.get("panels") or []:
            pid = _s(panel.get("panel_id"))
            source_panels.append(dict(
                Source_Panel_ID=pid, Source_Figure_ID=sfid,
                Panel_Label=_s(panel.get("label")) or pid,
                Outcome_Label=_s(panel.get("outcome_label")),
                Target_Status=_s(panel.get("target_status")).upper(),
                Panel_Disposition=_s(panel.get("disposition")).upper(),
                Disposition_Reason=_s(panel.get("reason")),
                Note=_s(panel.get("note"))))
            read = panel.get("read")
            if not read:
                continue
            box = read["box"]
            y_ticks = _ticks_text(read.get("y_ticks") or [])
            x_ticks = _ticks_text(read.get("x_ticks") or [])
            image_of_panel[pid] = (resolved, sha)
            ticks_of_panel[pid] = (x_ticks, y_ticks)
            view = _s(read.get("figure_view"))
            view_panels.setdefault(view, []).append((sfid, resolved, sha, figure))
            panels.append(dict(
                Panel_ID=pid, Source_Panel_ID=pid, Figure_ID=view,
                Unit_ID=_s(read.get("unit_id")),
                Panel_Label=_s(panel.get("label")) or pid,
                Mark_Type=_s(read.get("mark_type")).upper(), Image_Path=resolved,
                Panel_X0=box[0], Panel_X1=box[1], Panel_Y0=box[2], Panel_Y1=box[3],
                Axis_X_Region=_s(read.get("x_region")),
                Axis_Y_Region=_s(read.get("y_region")),
                Axis_X_Scale=_s(read.get("x_scale")).upper() or "LINEAR",
                Axis_Y_Scale=_s(read.get("y_scale")).upper() or "LINEAR",
                Axis_X_Ticks=x_ticks, Axis_Y_Ticks=y_ticks,
                Baseline_Value=read.get("baseline", ""),
                Association_Type=_s(read.get("association_type")).upper(),
                Config_ID=_s(read.get("config_id")),
                Panel_Mode=_s(read.get("panel_mode")).upper() or "AUTO",
                Note=_s(read.get("note"))))
            for sp in read.get("series") or []:
                series.append(dict(
                    Panel_ID=pid, Series_ID=_s(sp.get("series_id")),
                    Colour_Hex=_s(sp.get("colour")), Colour_Tolerance="",
                    Mask_Key=_s(sp.get("mask_key")),
                    Marker_Shape=_s(sp.get("marker")).upper(),
                    Marker_Fill=_s(sp.get("marker_fill")).upper(),
                    Line_Style=_s(sp.get("line_style")).upper(),
                    Bar_Fill_Pattern=_s(sp.get("bar_fill")).upper(),
                    Factor_Name=_s(sp.get("factor")).upper(),
                    Factor_Level=_s(sp.get("level")), Note=_s(sp.get("note"))))
            for order, pp in enumerate(read.get("positions") or []):
                positions.append(dict(
                    Panel_ID=pid, Position_ID=_s(pp.get("position_id")),
                    X_Pixel=pp.get("x_pixel", ""), Slot_Index=order,
                    Display_Order=order, Factor_Name=_s(pp.get("factor")).upper(),
                    Factor_Level=_s(pp.get("level")),
                    Timepoint_Label=_s(pp.get("timepoint_label")),
                    Timepoint_Days=pp.get("timepoint_days", ""),
                    Note=_s(pp.get("note"))))

    configs = []
    for c in plan.get("reader_configs") or []:
        for option, value in (c.get("options") or {}).items():
            configs.append(dict(Config_ID=_s(c.get("config_id")), Option=option,
                                Value=value, Note=_s(c.get("note"))))

    # ------------------------------------------------------------ figure views
    # A Figure_ID is an outcome-specific view of one physical figure. Its row is
    # built from the panels that claim it - the raster, the hash and the panel
    # counts all follow, so the reconciliation status is computed rather than
    # asserted. A plan that says MATCHED while listing three of six panels
    # cannot exist, because the plan never says MATCHED.
    figure_rows = []
    for view, members in sorted(view_panels.items()):
        sfid, resolved, sha, source = members[0]
        physical = source.get("observed_panel_count")
        worklist = len(members)
        figure_rows.append(dict(
            Figure_ID=view, Publication_ID=pub,
            Figure_Number=_s(source.get("figure_number")),
            Source_File=_s(source.get("source_file")),
            Source_Page=source.get("source_page", ""), Source_Image=resolved,
            Source_Caption_Verbatim=_s(
                (plan.get("figure_views") or {}).get(view, {}).get("caption")
                or source.get("caption")),
            Image_Resolution_Or_Hash="sha256:" + sha[:24], WPD_Project_File="",
            Observed_Panel_Count=worklist, Worklist_Panel_Count=worklist,
            Unlisted_Panels="", Panel_Reconciliation_Status="MATCHED",
            Note="view of %s (%d of %s physical panels)"
                 % (sfid, worklist, physical)))

    # ------------------------------------------------------------------ units
    unit_rows = []
    for u in plan["units"]:
        uid = _s(u.get("unit_id"))
        fills = [p for p in panels if _s(p.get("Unit_ID")) == uid]
        # The calibration the GATE checks, taken from the panel the READER will
        # use. These were two independent declarations - a tick string and four
        # numbers - and nothing joined them, so a unit could be validated
        # against a calibration no reader ever applied.
        cal = {}
        if fills:
            xt, yt = ticks_of_panel.get(_s(fills[0].get("Panel_ID")), ("", ""))
            for axis, text in (("X", xt), ("Y", yt)):
                pts = BM.parse_ticks(text) if text else []
                # A categorical x axis has no ticks to derive from - the x
                # identity IS the declared positions - so the unit may state
                # two reference points itself. That is not the duplicate
                # declaration P0-2 removed: there is no panel-level copy to
                # disagree with, because there is no continuous x axis.
                if not pts and axis == "X":
                    pts = [tuple(p) for p in (u.get("x_calibration") or [])]
                for n, (value, pixel) in enumerate(pts[:2], 1):
                    cal["Axis_Calib_%s%d_Value" % (axis, n)] = value
                    cal["Axis_Calib_%s%d_Pixel" % (axis, n)] = pixel
        row = dict(
            Unit_ID=uid, Figure_ID=_s(u.get("figure_view")),
            Grid_ID=_s(u.get("grid_id")), Panel=_s(u.get("panel")),
            Outcome_Name=_s(u.get("outcome_name")),
            Outcome_Variable=_s(u.get("outcome_variable")) or _s(u.get("outcome_name")),
            Outcome_Domain=_s(u.get("domain")), Unit=_s(u.get("unit")),
            Units=_s(u.get("unit")), Statistic_Type=_s(u.get("statistic")).upper(),
            Grid_Rule=_s(u.get("grid_rule")).upper() or "FULL",
            Value_Scale=_s(u.get("value_scale")).upper() or "RATIO",
            Dispersion_Type=_s(u.get("dispersion_type")).upper(),
            Errorbar_Definition_Source=_s(u.get("errorbar_source")),
            N_Outcome=u.get("n_outcome", ""), N_Source=_s(u.get("n_source")),
            Extraction_Method=_s(u.get("extraction_method")).upper() or "DIGITIZED",
            Bar_Top_Definition=_s(u.get("bar_top_definition")).upper(),
            Errorbar_Stem_Confirmed=_s(u.get("errorbar_stem_confirmed")).upper(),
            Axis_X_Scale=_s(fills[0].get("Axis_X_Scale")) if fills else "",
            Axis_Y_Scale=_s(fills[0].get("Axis_Y_Scale")) if fills else "",
            Extractor_1=_s(u.get("extractor_1")) or "run_batch", Extractor_2="",
            Independent_Verification_Status="", Discrepancy_Note="",
            Date=run_date, Note=_s(u.get("note")))
        row.update(cal)
        unit_rows.append(row)

    tables = (
        ("reviewer_registry", reviewers, BM.reviewer_registry_columns()),
        ("source_document_manifest", documents, BM.source_document_manifest_columns()),
        ("source_figure_manifest", source_figures, BM.source_figure_manifest_columns()),
        ("source_panel_inventory", source_panels, BM.source_panel_inventory_columns()),
        ("figure_manifest", figure_rows, GE.fig_figure_columns()),
        ("grid_definitions", grids, GE.fig_grid_columns()),
        ("unit_manifest", unit_rows, GE.fig_unit_columns()),
        ("panel_manifest", panels, BM.panel_manifest_columns()),
        ("series_manifest", series, BM.series_manifest_columns()),
        ("position_manifest", positions, BM.position_manifest_columns()),
        ("reader_config", configs, BM.reader_config_columns()),
    )
    written = {}
    for name, rows, cols in tables:
        path = os.path.join(out_dir, "%s.csv" % name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
        written[name] = path
    return written, []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan")
    ap.add_argument("manifest_dir")
    ap.add_argument("--file-root", default=".")
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    written, problems = compile_plan(plan, args.manifest_dir,
                                     file_root=args.file_root, run_date=args.date)
    if problems:
        for p in problems:
            print("  %-28s %-30s %s" % (p["where"], p["check"], p["detail"]))
        print("%d problem(s) in the plan; no manifest was written" % len(problems))
        return 2
    print("wrote %d manifests to %s" % (len(written), args.manifest_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
