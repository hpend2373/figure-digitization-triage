"""Declarative execution layer: what to read, and how, stated before any run.

The four grains in `grid_engine.py` describe the DATA - what a figure claims.
These four describe the RUN - where the marks are, which reader sees them, and
what each mark means. Keeping them apart matters: a value file must be reviewable
by someone who never touches a raster, and a run file must be re-executable by
someone who never reads the paper.

    panel_manifest.csv     one row per readable panel: box, mark type, axis
                           calibration, and the unit it fills
    series_manifest.csv    one row per series within a panel: how the reader
                           tells it apart, and which factor level it IS
    position_manifest.csv  one row per x position within a panel: where it is,
                           and which factor level it IS
    reader_config.csv      long-form option table, one row per option

Two rules run through all of it.

**Identity is declared, never inferred.** A series is a factor level because the
manifest says so, not because it was drawn second. A position is DI19 because
the manifest says so, not because it is the fourth bar from the left. When a
reader cannot resolve a mark, the cell stays empty and the grid engine names the
hole - nothing shifts to fill it.

**Every option is validated against the reader that will receive it.** An option
misspelled, or correct but meaningless for this mark type, is an error before the
run rather than a default silently applied during it. That is the difference
between a config file and a suggestion.
"""
import hashlib
import json
import os

import pandas as pd


# --------------------------------------------------------------------------
# vocabularies
# --------------------------------------------------------------------------

#: Mark types the batch layer can dispatch. A superset of `MARK_TYPES` would be
#: a lie; a subset means a manifest can name a reader the runner cannot call.
BATCH_MARK_TYPES = ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO",
                    "SCATTER", "BOX_VIOLIN")

#: Which mark types locate marks at declared x positions, and therefore require
#: rows in `position_manifest.csv`. SCATTER does not: its x IS data.
POSITIONAL_MARK_TYPES = ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO",
                         "BOX_VIOLIN")

#: Which mark types separate series by colour and therefore need one.
COLOUR_MARK_TYPES = ("BAR_COLOR", "LINE_COLOR")

#: Which mark types separate series by drawn form rather than by colour.
MONO_MARK_TYPES = ("BAR_MONO", "LINE_MONO")

#: Mark types this project has a name and a design for, but no released reader.
#: Naming them is better than silence: a manifest that declares one gets told
#: why it cannot run and where the work stands, instead of being quietly
#: routed to a reader that ignores half its declaration.
UNRELEASED_MARK_TYPES = {
    "LINE_MONO_STYLE": ("monochrome lines separated by SOLID/DASHED line style "
                        "rather than by marker. Built and measured but not "
                        "released - it emits cells where two curves cross "
                        "instead of dropping them. See wip/line_style_mono.py"),
}

MARKER_SHAPES = ("CIRCLE", "TRIANGLE", "SQUARE", "DIAMOND", "NONE")
MARKER_FILLS = ("OPEN", "FILLED", "ANY")
LINE_STYLES = ("SOLID", "DASHED", "DOTTED", "NONE")
BAR_FILL_PATTERNS = ("SOLID", "HATCHED", "OPEN", "NONE")
AXIS_SCALES = ("LINEAR", "LOG")

#: Associations `summarize_association` can compute from a digitized cloud.
SCATTER_ASSOCIATION_TYPES = ("PEARSON_R", "SPEARMAN_RHO", "KENDALL_TAU",
                             "R_SQUARED", "SLOPE")

#: How a panel is meant to be handled. AUTO means the runner reads it; MANUAL
#: means a human already decided the reader cannot, and the runner emits a
#: queue row instead of attempting it and reporting a plausible number.
PANEL_MODES = ("AUTO", "MANUAL")

#: Why a panel that EXISTS is or is not being extracted. Every panel in a
#: declared figure gets a row, including the ones nobody wants - deleting them
#: is what let a five-figure publication be declared as fourteen panels when it
#: has thirty-six, with every figure reporting MATCHED.
PANEL_DISPOSITIONS = (
    "EXTRACT",                 # a target outcome, to be read
    "NON_TARGET",              # a real panel, outside this review's outcomes
    "NO_SUMMARY_STATISTIC",    # individual traces, n=1, nothing to pool
    "DUPLICATE_OF_TABLE",      # the same numbers are tabulated in the text
)

#: Dispositions that mean "do not read this", so the runner does not try.
NON_EXTRACT_DISPOSITIONS = tuple(d for d in PANEL_DISPOSITIONS if d != "EXTRACT")

#: Terminal states a panel can reach in a run. Every panel lands on exactly one.
RUN_STATES = (
    "AUTO_PASS",                 # read, converted, and clean through the gate
    "NOT_TARGETED",              # a real panel this review does not extract
    "NO_READER_AVAILABLE",       # correctly declared, but no released reader
    "MANUAL_POINT_READ",         # reader produced nothing usable; hand-digitize
    "SERIES_IDENTITY_UNRESOLVED",  # marks found, but which series is ambiguous
    "PANEL_GEOMETRY_UNRESOLVED",   # box or calibration cannot be trusted
    "NO_VARIANCE",               # centres read, dispersion absent or unconfirmed
    "NOT_CONVERTIBLE",           # the mark cannot become the declared statistic
    "QC_FAILED",                 # values produced, but the grid gate rejected them
)


# --------------------------------------------------------------------------
# reader options: name -> (parser, applies-to)
# --------------------------------------------------------------------------

def _as_int(v):
    f = float(v)
    if f != int(f):
        raise ValueError("expected a whole number, got %r" % v)
    return int(f)


def _as_float(v):
    return float(v)


def _as_bool(v):
    s = str(v).strip().upper()
    if s in ("TRUE", "T", "YES", "1"):
        return True
    if s in ("FALSE", "F", "NO", "0"):
        return False
    raise ValueError("expected TRUE or FALSE, got %r" % v)


def _grey(v):
    """A 8-bit grey threshold. Outside 0-255 it selects everything or nothing."""
    if not (0 <= v <= 255):
        raise ValueError("a grey threshold must be 0-255, got %r" % v)
    return v


def _positive(v):
    if v <= 0:
        raise ValueError("must be greater than zero, got %r" % v)
    return v


def _non_negative(v):
    if v < 0:
        raise ValueError("must not be negative, got %r" % v)
    return v


def _at_least_one(v):
    if v < 1:
        raise ValueError("must be at least 1, got %r" % v)
    return v


def _anything(v):
    return v


#: option -> (parser, mark types that accept it, the reader keyword it becomes,
#:            range check). The range check is not decoration: `threshold=-1`
#: selects no pixels at all and `max_marker_area=10` below `min_marker_area=500`
#: selects no contours, and both of those used to pass validation and then
#: produce an empty panel that looked like an unreadable figure.
READER_OPTIONS = {
    "threshold":        (_as_int, ("BAR_MONO", "LINE_MONO", "BOX_VIOLIN"),
                         "threshold", _grey),
    "stem_threshold":   (_as_int, ("BAR_MONO",), "stem_threshold", _grey),
    "group_window":     (_as_int, ("BAR_MONO",), "group_window", _positive),
    "colour_tolerance": (_as_float, COLOUR_MARK_TYPES + ("SCATTER",), None,
                         _non_negative),
    "x_window":         (_as_int, ("LINE_COLOR", "LINE_MONO"), "x_window", _positive),
    "half_window":      (_as_int, ("BOX_VIOLIN",), "half_window", _positive),
    "min_marker_area":  (_as_float, ("SCATTER",), "min_area", _positive),
    "max_marker_area":  (_as_float, ("SCATTER",), "max_area", _positive),
    "min_bar_px":       (_as_int, ("BAR_COLOR", "BAR_MONO"), "min_bar_px", _positive),
    "stem_half_width":  (_as_int, ("BAR_COLOR",), "stem_half_width", _positive),
    "max_whisker_px":   (_as_int, ("BAR_COLOR",), "max_whisker_px", _positive),
    "stem_required":    (_as_bool, ("BAR_COLOR",), "stem_required", _anything),
    "baseline_value":   (_as_float, ("BAR_COLOR", "BAR_MONO"), "baseline_value",
                         _anything),
    # BAR_COLOR only. `read_monochrome_bar_panel` derives its slot count from
    # the number of declared series and has no n_slots parameter at all - the
    # manifest used to accept the option here, and the run then died with a
    # TypeError that surfaced as PANEL_GEOMETRY_UNRESOLVED. A reader-signature
    # introspection test now makes that class of mismatch impossible to ship.
    "n_slots":          (_as_int, ("BAR_COLOR",), "n_slots", _at_least_one),
    "dual_tolerance_pct": (_as_float, BATCH_MARK_TYPES, None, _non_negative),
}

#: Options that only make sense against each other.
PAIRED_OPTION_RULES = (
    ("min_marker_area", "max_marker_area",
     lambda lo, hi: lo < hi,
     "min_marker_area must be below max_marker_area, or no contour can match"),
)


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------

def panel_manifest_columns():
    return [
        "Panel_ID", "Figure_ID", "Unit_ID", "Panel_Label", "Mark_Type",
        "Image_Path",
        # the plot area, in image pixels
        "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1",
        # where the axes live, so a human re-checking calibration knows where to
        # look and a future tick-finder has somewhere to search
        "Axis_X_Region", "Axis_Y_Region",
        "Axis_X_Scale", "Axis_Y_Scale",
        # "v1:px1;v2:px2" - at least two points per axis in use
        "Axis_X_Ticks", "Axis_Y_Ticks",
        "Baseline_Value", "Panel_Disposition",
        # which association a scatter panel is meant to yield. It is a run
        # instruction, not a finding: the paper says which statistic it reports,
        # and the reader must not pick one by looking at the points.
        "Association_Type",
        "Config_ID", "Panel_Mode", "Note",
    ]


def series_manifest_columns():
    return [
        "Panel_ID", "Series_ID",
        # colour readers
        "Colour_Hex", "Colour_Tolerance", "Mask_Key",
        # monochrome readers
        "Marker_Shape", "Marker_Fill", "Line_Style", "Bar_Fill_Pattern",
        # what the series MEANS - this is what reaches the Cell_Key
        "Factor_Name", "Factor_Level", "Note",
    ]


def position_manifest_columns():
    return [
        "Panel_ID", "Position_ID", "X_Pixel", "Slot_Index", "Display_Order",
        # what the position MEANS
        "Factor_Name", "Factor_Level", "Timepoint_Label", "Timepoint_Days",
        "Note",
    ]


def reader_config_columns():
    return ["Config_ID", "Option", "Value", "Note"]


BATCH_TEMPLATES = (
    ("panel_manifest", panel_manifest_columns),
    ("series_manifest", series_manifest_columns),
    ("position_manifest", position_manifest_columns),
    ("reader_config", reader_config_columns),
)


# --------------------------------------------------------------------------
# small parsers, each of which fails loudly
# --------------------------------------------------------------------------

def blank(v):
    return v is None or (isinstance(v, float) and v != v) or not str(v).strip()


def parse_ticks(text):
    """'0:450;20:50' -> [(0.0, 450.0), (20.0, 50.0)].

    Two distinct pixels are required. One tick cannot define a scale, and two
    ticks at the same pixel define an infinite one - both have shipped as
    'calibrated' in real projects.
    """
    pairs = []
    for chunk in str(text).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError("tick %r is not value:pixel" % chunk)
        v, px = chunk.split(":", 1)
        pairs.append((float(v), float(px)))
    if len(pairs) < 2:
        raise ValueError("need at least two ticks, got %d" % len(pairs))
    if len({p for _, p in pairs}) < 2:
        raise ValueError("all ticks share one pixel row")
    if len({v for v, _ in pairs}) < 2:
        raise ValueError("all ticks share one value")
    return pairs


def parse_box(text):
    """'x0,x1,y0,y1' -> a 4-tuple of ints, ordered and non-degenerate."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 4:
        raise ValueError("expected x0,x1,y0,y1, got %r" % text)
    x0, x1, y0, y1 = (int(round(float(p))) for p in parts)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("degenerate or inverted box %r" % text)
    return x0, x1, y0, y1


def parse_colour(text):
    """'#1e50dc' or '30,80,220' -> (r, g, b)."""
    s = str(text).strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) != 6:
            raise ValueError("hex colour must be 6 digits, got %r" % text)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError("expected #rrggbb or r,g,b, got %r" % text)
    rgb = tuple(int(p) for p in parts)
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError("colour channel out of range in %r" % text)
    return rgb


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def load_reader_configs(config_df, mark_type_by_config, flag):
    """Long-form option rows -> {Config_ID: {option: parsed value}}.

    `mark_type_by_config` maps a Config_ID to the set of mark types that use it,
    so an option can be rejected for the reader that would actually receive it
    rather than merely for existing.
    """
    out = {}
    for i, r in config_df.iterrows():
        line = "reader_config:%d" % (i + 2)
        cid = str(r.get("Config_ID", "")).strip()
        opt = str(r.get("Option", "")).strip()
        if not cid or not opt:
            flag(line, "MISSING_REQUIRED", "Config_ID and Option are required")
            continue
        if opt not in READER_OPTIONS:
            flag(line, "UNKNOWN_READER_OPTION",
                 "%r is not a reader option; a misspelled option is silently "
                 "ignored otherwise, and the run reports the default as if it "
                 "had been chosen" % opt)
            continue
        parser, applies, _, check = READER_OPTIONS[opt]
        bucket = out.setdefault(cid, {})
        if opt in bucket:
            flag(line, "DUPLICATE_READER_OPTION",
                 "%s is set twice in config %s" % (opt, cid))
            continue
        try:
            bucket[opt] = check(parser(r.get("Value")))
        except (TypeError, ValueError) as exc:
            flag(line, "BAD_READER_OPTION_VALUE", "%s=%r: %s" % (opt, r.get("Value"), exc))
            bucket.pop(opt, None)
            continue
        used_by = mark_type_by_config.get(cid, set())
        wrong = sorted(m for m in used_by if m not in applies)
        if wrong:
            flag(line, "OPTION_WRONG_FOR_MARK_TYPE",
                 "%s does not apply to %s (accepted by %s)"
                 % (opt, ", ".join(wrong), ", ".join(applies)))
    for cid, bucket in out.items():
        for a, b, ok, message in PAIRED_OPTION_RULES:
            if a in bucket and b in bucket and not ok(bucket[a], bucket[b]):
                flag("config:%s" % cid, "READER_OPTIONS_CONTRADICT",
                     "%s=%r, %s=%r - %s" % (a, bucket[a], b, bucket[b], message))
    return out


def validate_batch_manifests(panels, series, positions, configs, units=None,
                             figures=None, file_root=".", check_files=True):
    """Reject an unrunnable batch before a single raster is opened.

    Returns a DataFrame of problems - empty means the run may proceed. The
    checks are deliberately cheap and total: reading 160 publications and
    discovering on figure 140 that a Config_ID was misspelled is an expensive
    way to learn it.
    """
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    frames = (("panels", panels, panel_manifest_columns()),
              ("series", series, series_manifest_columns()),
              ("positions", positions, position_manifest_columns()),
              ("configs", configs, reader_config_columns()))
    for name, df, cols in frames:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            flag(name, "SCHEMA_INCOMPLETE", "missing columns: " + ", ".join(missing))
    if problems:
        return pd.DataFrame(problems)

    def resolve(p):
        p = str(p).strip()
        if os.path.exists(p):
            return p
        q = os.path.join(file_root, p)
        return q if os.path.exists(q) else None

    unit_index = {}
    if units is not None:
        for _, u in units.iterrows():
            unit_index[str(u.get("Unit_ID", "")).strip()] = u
    figure_index = {}
    if figures is not None:
        for _, f in figures.iterrows():
            figure_index[str(f.get("Figure_ID", "")).strip()] = f

    # -------------------------------------------------------------- panels
    panel_index, panel_mark, mark_by_config, panel_disposition = {}, {}, {}, {}
    panels_by_figure = {}
    for i, r in panels.iterrows():
        line = "panels:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        if not pid:
            flag(line, "MISSING_REQUIRED", "Panel_ID")
            continue
        if pid in panel_index:
            flag(line, "DUPLICATE_PANEL_ID", pid)
            continue
        panel_index[pid] = r
        panels_by_figure.setdefault(str(r.get("Figure_ID", "")).strip(), []).append(pid)
        disposition = str(r.get("Panel_Disposition", "")).strip().upper() or "EXTRACT"
        if disposition not in PANEL_DISPOSITIONS:
            flag(line, "BAD_PANEL_DISPOSITION",
                 "Panel_Disposition=%s (expected %s)"
                 % (disposition, "/".join(PANEL_DISPOSITIONS)))
            disposition = "EXTRACT"
        panel_disposition[pid] = disposition
        required = ("Figure_ID", "Image_Path")
        if disposition == "EXTRACT":
            required += ("Unit_ID", "Mark_Type")
        for c in required:
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        if disposition in NON_EXTRACT_DISPOSITIONS:
            # A record that this panel exists and why it is not being read. It
            # needs no reader, no calibration, no series and no positions - only
            # a reason. Demanding the rest is what makes people delete the row.
            if blank(r.get("Note")):
                flag(line, "MISSING_DISPOSITION_REASON",
                     "Panel_Disposition=%s - say in Note why this panel is not "
                     "extracted, or a reviewer cannot tell a decision from an "
                     "oversight" % disposition)
            continue
        mark = str(r.get("Mark_Type", "")).strip().upper()
        # An unreleased mark type is NOT a manifest error. The file is correct;
        # the software is behind it. Rejecting the batch would mean one panel
        # nobody can read yet stops every panel that can be - on publication 397
        # that was two line figures blocking twenty-four readable bar cells.
        # It validates, and the RUN gives it NO_READER_AVAILABLE.
        if mark and mark not in BATCH_MARK_TYPES and mark not in UNRELEASED_MARK_TYPES:
            flag(line, "BAD_MARK_TYPE",
                 "Mark_Type=%s (expected %s)" % (mark, "/".join(BATCH_MARK_TYPES)))
        panel_mark[pid] = mark
        mode = str(r.get("Panel_Mode", "")).strip().upper() or "AUTO"
        if mode not in PANEL_MODES:
            flag(line, "BAD_PANEL_MODE",
                 "Panel_Mode=%s (expected %s)" % (mode, "/".join(PANEL_MODES)))
        cid = str(r.get("Config_ID", "")).strip()
        if cid and mark:
            mark_by_config.setdefault(cid, set()).add(mark)

        box = r.get("Panel_X0")
        if all(not blank(r.get(c)) for c in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")):
            try:
                box = parse_box(",".join(str(r.get(c)) for c in
                                         ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")))
            except ValueError as exc:
                flag(line, "BAD_PANEL_BOX", str(exc))
                box = None
        else:
            flag(line, "MISSING_REQUIRED", "Panel_X0/X1/Y0/Y1")
            box = None

        img = resolve(r.get("Image_Path")) if not blank(r.get("Image_Path")) else None
        if check_files and not blank(r.get("Image_Path")) and img is None:
            flag(line, "SOURCE_FILE_NOT_FOUND",
                 "Image_Path=%r is not on disk" % r.get("Image_Path"))
        elif check_files and img is not None and box is not None:
            try:
                from PIL import Image as _Image
                w, h = _Image.open(img).size
            except Exception as exc:                              # pragma: no cover
                flag(line, "IMAGE_UNREADABLE", "%s: %s" % (img, exc))
            else:
                if box[1] > w or box[3] > h:
                    flag(line, "PANEL_BOX_OUTSIDE_IMAGE",
                         "box %s exceeds the %dx%d raster" % ((box,), w, h))

        for axis in ("X", "Y"):
            scale = str(r.get("Axis_%s_Scale" % axis, "")).strip().upper()
            ticks = r.get("Axis_%s_Ticks" % axis)
            needed = (axis == "Y") or mark == "SCATTER"
            if blank(ticks):
                if needed:
                    flag(line, "MISSING_AXIS_CALIBRATION",
                         "Axis_%s_Ticks - %s reads values off this axis" % (axis, mark))
                continue
            if scale and scale not in AXIS_SCALES:
                flag(line, "BAD_AXIS_SCALE", "Axis_%s_Scale=%s" % (axis, scale))
            try:
                pairs = parse_ticks(ticks)
            except ValueError as exc:
                flag(line, "BAD_AXIS_CALIBRATION", "Axis_%s_Ticks: %s" % (axis, exc))
                continue
            if scale == "LOG" and any(v <= 0 for v, _ in pairs):
                flag(line, "BAD_AXIS_CALIBRATION",
                     "Axis_%s_Ticks has a non-positive value on a LOG axis" % axis)
            if box is not None:
                lo, hi = (box[0], box[1]) if axis == "X" else (box[2], box[3])
                outside = [px for _, px in pairs if not (lo - 5 <= px <= hi + 5)]
                if outside:
                    flag(line, "CALIBRATION_OUTSIDE_PANEL",
                         "Axis_%s tick pixel(s) %s lie outside the panel box - the "
                         "box and the calibration describe different panels"
                         % (axis, outside))
        if not blank(r.get("Unit_ID")) and unit_index:
            uid = str(r.get("Unit_ID")).strip()
            if uid not in unit_index:
                flag(line, "UNIT_NOT_FOUND",
                     "Unit_ID=%s is not in the unit manifest" % uid)
            else:
                ustat = str(unit_index[uid].get("Statistic_Type", "")).strip().upper()
                if mark == "BOX_VIOLIN" and ustat not in ("QUANTILE_SUMMARY", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "a box/violin yields a five-number summary, but the unit "
                         "declares Statistic_Type=%s" % ustat)
                if mark == "SCATTER" and ustat not in ("ASSOCIATION", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "a scatter yields an association, but the unit declares "
                         "Statistic_Type=%s" % ustat)
                if mark in ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO") \
                        and ustat not in ("CONTINUOUS", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "%s yields mean/dispersion, but the unit declares "
                         "Statistic_Type=%s" % (mark, ustat))
        if mark == "SCATTER":
            at = str(r.get("Association_Type", "")).strip().upper()
            if not at:
                flag(line, "MISSING_ASSOCIATION_TYPE",
                     "a scatter panel must declare which association it yields; "
                     "letting the reader default to one means the paper's choice "
                     "of statistic is decided by this file instead (%s)"
                     % "/".join(SCATTER_ASSOCIATION_TYPES))
            elif at not in SCATTER_ASSOCIATION_TYPES:
                flag(line, "BAD_ASSOCIATION_TYPE",
                     "Association_Type=%s (expected %s)"
                     % (at, "/".join(SCATTER_ASSOCIATION_TYPES)))
        elif not blank(r.get("Association_Type")):
            flag(line, "ASSOCIATION_TYPE_NOT_APPLICABLE",
                 "Association_Type is set on a %s panel, which yields no "
                 "association" % mark)

    # Every panel the figure says exists must have a row here. Without this the
    # batch layer can quietly declare a subset: publication 397 was declared as
    # fourteen panels of thirty-six, and every figure still reported MATCHED
    # because each virtual figure counted only the panels it had been given.
    # The figure grain reconciles the figure against the SCREEN; this reconciles
    # the run against the figure grain, and both are needed.
    for fid, f in figure_index.items():
        declared = panels_by_figure.get(fid, [])
        observed = f.get("Observed_Panel_Count")
        try:
            observed = int(float(str(observed).strip()))
        except (TypeError, ValueError):
            continue                       # the figure grain reports that itself
        if len(declared) != observed:
            flag("figures:%s" % fid, "PANEL_MANIFEST_INCOMPLETE",
                 "the figure manifest says %d panels and panel_manifest declares "
                 "%d (%s). Record every panel, using Panel_Disposition to say "
                 "which are not extracted - a panel with no row is invisible to "
                 "reconciliation" % (observed, len(declared),
                                     ", ".join(sorted(declared)) or "none"))
    for fid in sorted(set(panels_by_figure) - set(figure_index)):
        if figure_index:
            flag("panels:%s" % fid, "FIGURE_NOT_FOUND",
                 "panels reference Figure_ID=%s, which the figure manifest does "
                 "not declare" % fid)

    # -------------------------------------------------------------- series
    seen_series, factors_by_panel = set(), {}
    for i, r in series.iterrows():
        line = "series:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        sid = str(r.get("Series_ID", "")).strip()
        if not pid or not sid:
            flag(line, "MISSING_REQUIRED", "Panel_ID and Series_ID are required")
            continue
        if pid not in panel_index:
            flag(line, "PANEL_NOT_FOUND", pid)
            continue
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            flag(line, "SERIES_ON_NON_EXTRACT_PANEL",
                 "%s is %s, so its series will never be read; delete the row or "
                 "change the disposition"
                 % (pid, panel_disposition.get(pid)))
            continue
        if (pid, sid) in seen_series:
            flag(line, "DUPLICATE_SERIES_ID", "%s/%s" % (pid, sid))
            continue
        seen_series.add((pid, sid))
        mark = panel_mark.get(pid, "")
        if blank(r.get("Factor_Name")) or blank(r.get("Factor_Level")):
            flag(line, "MISSING_SERIES_IDENTITY",
                 "a series without a Factor_Name/Factor_Level cannot become a "
                 "Cell_Key, so its numbers would have nowhere to go")
        else:
            factors_by_panel.setdefault(pid, set()).add(
                str(r.get("Factor_Name")).strip().upper())
        for col, vocab in (("Marker_Shape", MARKER_SHAPES),
                           ("Marker_Fill", MARKER_FILLS),
                           ("Line_Style", LINE_STYLES),
                           ("Bar_Fill_Pattern", BAR_FILL_PATTERNS)):
            v = str(r.get(col, "")).strip().upper()
            if v and v not in vocab:
                flag(line, "BAD_SERIES_%s" % col.upper(),
                     "%s=%s (expected %s)" % (col, v, "/".join(vocab)))
        if mark in COLOUR_MARK_TYPES:
            if mark == "BAR_COLOR":
                if blank(r.get("Mask_Key")):
                    flag(line, "MISSING_SERIES_DISCRIMINANT",
                         "BAR_COLOR separates series by colour mask - Mask_Key required")
            elif blank(r.get("Colour_Hex")):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "%s separates series by colour - Colour_Hex required" % mark)
        if not blank(r.get("Colour_Hex")):
            try:
                parse_colour(r.get("Colour_Hex"))
            except ValueError as exc:
                flag(line, "BAD_SERIES_COLOUR", str(exc))
        if mark in UNRELEASED_MARK_TYPES:
            # Still checked, on the rules the reader WOULD use, so the manifest
            # is ready the day the reader ships rather than wrong and unnoticed.
            style = str(r.get("Line_Style", "")).strip().upper()
            if style in ("", "NONE"):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "%s separates series by line style - declare Line_Style"
                     % mark)
        elif mark == "LINE_MONO":
            # The released LINE_MONO reader separates series by MARKER geometry
            # and never looks at Line_Style. Accepting a series declared purely
            # as SOLID-versus-DASHED let a manifest describe a figure the shipped
            # reader cannot read, and the run then matched marks by shape alone -
            # the manifest contract has to say what the reader actually does,
            # not what the module is eventually meant to do.
            shape = str(r.get("Marker_Shape", "")).strip().upper()
            if shape in ("", "NONE"):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "the released LINE_MONO reader separates series by marker "
                     "shape and fill - declare Marker_Shape. Series told apart "
                     "only by SOLID/DASHED need %s, which has no released reader"
                     % "/".join(sorted(UNRELEASED_MARK_TYPES)))
            elif str(r.get("Line_Style", "")).strip().upper() not in ("", "NONE"):
                flag(line, "LINE_STYLE_NOT_READ",
                     "Line_Style is recorded but the released LINE_MONO reader "
                     "does not use it; the series will be matched by marker "
                     "geometry alone. Blank it, or the manifest promises a "
                     "discriminant the run will not apply")
        if mark == "BAR_MONO" and str(r.get("Bar_Fill_Pattern", "")).strip().upper() \
                in ("", "NONE"):
            flag(line, "MISSING_SERIES_DISCRIMINANT",
                 "a monochrome bar series is told apart by its fill pattern - "
                 "Bar_Fill_Pattern required")

    for pid, r in panel_index.items():
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            continue
        if not any(p == pid for p, _ in seen_series):
            flag("panels:%s" % pid, "PANEL_HAS_NO_SERIES",
                 "nothing declares what the marks in this panel mean")

    # Two series of one panel that are told apart by nothing are not two series.
    for pid in panel_index:
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            continue
        mark = panel_mark.get(pid, "")
        rows = [r for _, r in series.iterrows()
                if str(r.get("Panel_ID", "")).strip() == pid]
        if mark in UNRELEASED_MARK_TYPES:
            keys = [str(r.get("Line_Style", "")).strip().upper() for r in rows]
        elif mark in MONO_MARK_TYPES:
            keys = [(str(r.get("Marker_Shape", "")).strip().upper(),
                     str(r.get("Marker_Fill", "")).strip().upper(),
                     str(r.get("Line_Style", "")).strip().upper(),
                     str(r.get("Bar_Fill_Pattern", "")).strip().upper()) for r in rows]
        elif mark in COLOUR_MARK_TYPES:
            keys = [(str(r.get("Colour_Hex", "")).strip().upper(),
                     str(r.get("Mask_Key", "")).strip().upper()) for r in rows]
        else:
            continue
        if len(keys) != len(set(keys)):
            flag("panels:%s" % pid, "SERIES_NOT_SEPARABLE",
                 "two series in this panel carry identical discriminants, so no "
                 "reader can tell them apart and neither can a reviewer")

    # ------------------------------------------------------------ positions
    seen_pos = set()
    for i, r in positions.iterrows():
        line = "positions:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        qid = str(r.get("Position_ID", "")).strip()
        if not pid or not qid:
            flag(line, "MISSING_REQUIRED", "Panel_ID and Position_ID are required")
            continue
        if pid not in panel_index:
            flag(line, "PANEL_NOT_FOUND", pid)
            continue
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            continue
        if (pid, qid) in seen_pos:
            flag(line, "DUPLICATE_POSITION_ID", "%s/%s" % (pid, qid))
            continue
        seen_pos.add((pid, qid))
        if blank(r.get("Factor_Name")) or blank(r.get("Factor_Level")):
            flag(line, "MISSING_POSITION_IDENTITY",
                 "a position without a Factor_Name/Factor_Level cannot become a "
                 "Cell_Key")
        else:
            factors_by_panel.setdefault(pid, set()).add(
                str(r.get("Factor_Name")).strip().upper())
        mark = panel_mark.get(pid, "")
        if blank(r.get("X_Pixel")) and blank(r.get("Slot_Index")):
            flag(line, "MISSING_POSITION_GEOMETRY",
                 "give X_Pixel, or Slot_Index for a slot-based bar panel")
        if not blank(r.get("X_Pixel")):
            try:
                x = float(r.get("X_Pixel"))
            except (TypeError, ValueError):
                flag(line, "BAD_X_PIXEL", "X_Pixel=%r" % r.get("X_Pixel"))
            else:
                row = panel_index[pid]
                try:
                    box = parse_box(",".join(str(row.get(c)) for c in
                                             ("Panel_X0", "Panel_X1",
                                              "Panel_Y0", "Panel_Y1")))
                except ValueError:
                    box = None
                if box is not None and not (box[0] <= x <= box[1]):
                    flag(line, "POSITION_OUTSIDE_PANEL",
                         "X_Pixel=%g is outside the panel box x range %d-%d"
                         % (x, box[0], box[1]))
        if not blank(r.get("Timepoint_Days")):
            try:
                float(r.get("Timepoint_Days"))
            except (TypeError, ValueError):
                flag(line, "BAD_TIMEPOINT_DAYS", "%r" % r.get("Timepoint_Days"))
        if mark == "SCATTER":
            flag(line, "POSITION_NOT_APPLICABLE",
                 "a scatter's x is data, not a declared position; delete this row "
                 "or the reader will be given a grid it does not use")

    for pid, mark in panel_mark.items():
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            continue
        if mark in UNRELEASED_MARK_TYPES and not any(p == pid for p, _ in seen_pos):
            flag("panels:%s" % pid, "PANEL_HAS_NO_POSITIONS",
                 "%s will read at declared x positions and none are declared"
                 % mark)
        if mark in POSITIONAL_MARK_TYPES and not any(p == pid for p, _ in seen_pos):
            flag("panels:%s" % pid, "PANEL_HAS_NO_POSITIONS",
                 "%s reads at declared x positions and none are declared" % mark)

    # A factor cannot be both the series axis and the position axis of one panel.
    for pid in panel_index:
        if panel_disposition.get(pid) in NON_EXTRACT_DISPOSITIONS:
            continue
        s_factors = {str(r.get("Factor_Name", "")).strip().upper()
                     for _, r in series.iterrows()
                     if str(r.get("Panel_ID", "")).strip() == pid
                     and not blank(r.get("Factor_Name"))}
        p_factors = {str(r.get("Factor_Name", "")).strip().upper()
                     for _, r in positions.iterrows()
                     if str(r.get("Panel_ID", "")).strip() == pid
                     and not blank(r.get("Factor_Name"))}
        overlap = sorted(s_factors & p_factors)
        if overlap:
            flag("panels:%s" % pid, "FACTOR_ON_BOTH_AXES",
                 "%s labels both the series and the positions of this panel; the "
                 "Cell_Key would carry it twice" % ", ".join(overlap))
        if len(s_factors) > 1:
            flag("panels:%s" % pid, "SERIES_FACTOR_INCONSISTENT",
                 "the series of one panel name %d different factors (%s)"
                 % (len(s_factors), ", ".join(sorted(s_factors))))
        if len(p_factors) > 1:
            flag("panels:%s" % pid, "POSITION_FACTOR_INCONSISTENT",
                 "the positions of one panel name %d different factors (%s)"
                 % (len(p_factors), ", ".join(sorted(p_factors))))

    # -------------------------------------------------------------- configs
    parsed = load_reader_configs(configs, mark_by_config, flag)
    for pid, r in panel_index.items():
        cid = str(r.get("Config_ID", "")).strip()
        if cid and cid not in parsed:
            flag("panels:%s" % pid, "CONFIG_NOT_FOUND",
                 "Config_ID=%s has no rows in reader_config" % cid)

    return pd.DataFrame(problems)


def config_hash(configs):
    """Stable digest of the option table, for the run's reproducibility stamp."""
    rows = sorted(
        (str(r.get("Config_ID", "")).strip(), str(r.get("Option", "")).strip(),
         str(r.get("Value", "")).strip())
        for _, r in configs.iterrows())
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
