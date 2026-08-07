"""Read a whole batch of declared panels, and say honestly what it could not do.

    python3 run_batch.py MANIFEST_DIR OUTPUT_DIR [--file-root DIR] [--date YYYY-MM-DD]

Input  (MANIFEST_DIR): source_document_manifest.csv, source_figure_manifest.csv,
                       source_panel_inventory.csv,
                       figure_manifest.csv, grid_definitions.csv,
                       unit_manifest.csv, panel_manifest.csv,
                       series_manifest.csv, position_manifest.csv,
                       reader_config.csv
Output (OUTPUT_DIR):   figure_values_accepted.csv  <- the only file to pool from
                       figure_values_raw.csv       <- everything read, with
                                                      Value_Status/QC_Codes/
                                                      Pooling_Eligible per row
                       run_manifest.csv, manual_queue.csv, qc_problems.csv,
                       run_stamp.json, raw/, projects/

The design commitment is that **a panel the reader could not do is louder than a
panel it could**. Every panel lands on exactly one state, and everything short of
AUTO_PASS goes to `manual_queue.csv` with the reason attached. Nothing is
estimated to keep a row alive, and no cell is filled by position because its
neighbour was readable.

Three properties are worth naming, because each is a failure mode this project
has actually hit:

1. **Manifests are validated before a raster is opened.** A misspelled option or
   a box that does not fit its image is an error at second zero, not at panel 140.
2. **Identity comes from the manifest.** A series is a factor level because
   `series_manifest.csv` says so. A reader that cannot tell two marks apart
   returns neither, and the cell stays empty for the grid gate to name.
3. **The run records what would have to be equal for it to be reproducible**:
   image hash, config hash, reader version, manifest hashes, run date. A second
   run over the same inputs is compared cell by cell, not trusted.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

import pandas as pd
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import grid_engine as GE                                           # noqa: E402
import kernel as K                                                 # noqa: E402
import make_wpd_project as WPD                                     # noqa: E402
import mark_readers as MR                                          # noqa: E402

PIPELINE_VERSION = "7.8"
PIPELINE_CODE_FILES = (
    "run_batch.py", "batch_manifests.py", "grid_engine.py", "kernel.py",
    "mark_readers.py", "bar_reader.py", "make_wpd_project.py",
)


#: Mark_Type -> the function that actually receives the reader keywords, so a
#: test can introspect it. Declaring that an option "applies to" a mark type is
#: a promise about a function signature, and a promise nobody checks is how
#: `n_slots` came to be accepted for BAR_MONO, pass validation, and then raise
#: TypeError mid-run - which surfaced as PANEL_GEOMETRY_UNRESOLVED, a message
#: about the figure for a defect in this table.
def reader_functions():
    from bar_reader import read_bar_panel
    return {
        "BAR_COLOR": read_bar_panel,
        "BAR_MONO": MR.read_monochrome_bar_panel,
        "LINE_COLOR": MR.read_line_marker_panel,
        "LINE_MONO": MR.read_monochrome_marker_panel,
        "SCATTER": MR.read_scatter_panel,
        "BOX_VIOLIN": MR.read_box_violin_panel,
    }


MANIFEST_FILES = {
    "source_documents": "source_document_manifest.csv",
    "source_figures": "source_figure_manifest.csv",
    "source_panels": "source_panel_inventory.csv",
    "figures": "figure_manifest.csv",
    "grids": "grid_definitions.csv",
    "units": "unit_manifest.csv",
    "panels": "panel_manifest.csv",
    "series": "series_manifest.csv",
    "positions": "position_manifest.csv",
    "configs": "reader_config.csv",
}

RUN_MANIFEST_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type", "Run_State",
    "Cells_Declared", "Cells_Read", "Cells_With_Dispersion",
    "Image_Path", "Image_SHA256", "Config_ID", "Config_SHA256",
    "Reader_Version", "Pipeline_Version", "Pipeline_Code_SHA256",
    "Raw_Data_File", "WPD_Project_File", "Run_Date", "Detail",
]

MANUAL_QUEUE_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type", "Run_State",
    "Missing_Cells", "Image_Path", "Panel_Box", "Detail",
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _s(v):
    return "" if v is None else str(v).strip()


def _upper(v):
    return _s(v).upper()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frame_sha256(df):
    return hashlib.sha256(
        df.to_csv(index=False).encode("utf-8")).hexdigest()


def pipeline_code_sha256():
    h = hashlib.sha256()
    for name in PIPELINE_CODE_FILES:
        path = os.path.join(HERE, name)
        h.update(name.encode("utf-8") + b"\0")
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


class ManifestLoadError(Exception):
    """A manifest could not be read at all - missing, malformed or unreadable.

    A plain Exception on purpose. This used to be `SystemExit`, which derives
    from BaseException, so the obvious `except Exception` around the load would
    have sailed straight past it and the caller would never have got the chance
    to record what happened.
    """


def load_manifests(directory):
    out, missing, broken = {}, [], []
    for key, name in MANIFEST_FILES.items():
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            missing.append(name)
            continue
        try:
            out[key] = pd.read_csv(path, dtype=object).fillna("")
        except Exception as exc:                 # malformed CSV, encoding, perms
            broken.append("%s (%s: %s)" % (name, type(exc).__name__, exc))
    if missing or broken:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(sorted(missing)))
        if broken:
            parts.append("unreadable: " + "; ".join(sorted(broken)))
        raise ManifestLoadError("cannot load manifests from %s - %s"
                                % (directory, " | ".join(parts)))
    return out


def _calibration(row, axis):
    text = row.get("Axis_%s_Ticks" % axis)
    if BM.blank(text):
        return None
    scale = _upper(row.get("Axis_%s_Scale" % axis)) or "LINEAR"
    return MR.AxisCalibration.from_points(BM.parse_ticks(text), scale=scale)


def _reader_kwargs(options, mark_type):
    """Translate declared options into the keywords this reader accepts."""
    out = {}
    for name, value in (options or {}).items():
        _, applies, keyword, _check = BM.READER_OPTIONS[name]
        if keyword and mark_type in applies:
            out[keyword] = value
    return out


def _series_specs(rows, mark_type, options):
    tolerance = (options or {}).get("colour_tolerance", 70.0)
    specs = []
    for r in rows:
        rgb = None
        if not BM.blank(r.get("Colour_Hex")):
            rgb = BM.parse_colour(r.get("Colour_Hex"))
        own = r.get("Colour_Tolerance")
        specs.append(MR.SeriesSpec(
            name=_s(r.get("Series_ID")), rgb=rgb,
            marker=(_upper(r.get("Marker_Shape")) or "CIRCLE"),
            fill=(_upper(r.get("Marker_Fill")) or "ANY"),
            tolerance=(float(own) if not BM.blank(own) else float(tolerance)),
            bar_fill=_upper(r.get("Bar_Fill_Pattern")),
            line_style=_upper(r.get("Line_Style")),
        ))
    return specs


def _x_positions(rows):
    """Position_ID -> x pixel, in declared display order."""
    def order(r):
        v = r.get("Display_Order")
        return (float(v) if not BM.blank(v) else float(r.get("X_Pixel") or 0.0))
    return {_s(r.get("Position_ID")): float(r.get("X_Pixel"))
            for r in sorted(rows, key=order) if not BM.blank(r.get("X_Pixel"))}


# --------------------------------------------------------------------------
# one panel
# --------------------------------------------------------------------------

class PanelOutcome(object):
    def __init__(self, state, values=None, detail="", raw=None,
                 declared=0, read=0, with_dispersion=0, missing=(), project=None):
        self.state = state
        self.values = values or []
        self.detail = detail
        self.raw = raw
        self.project = project
        self.declared = declared
        self.read = read
        self.with_dispersion = with_dispersion
        self.missing = list(missing)


def run_panel(panel, series_rows, position_rows, options, unit, raw_dir,
              file_root=".", project_dir=None):
    """Read one declared panel. Returns a PanelOutcome; never raises for data."""
    pid = _s(panel.get("Panel_ID"))
    mark = _upper(panel.get("Mark_Type"))
    statistic = _upper(unit.get("Statistic_Type")) if unit is not None else ""
    mode = _upper(panel.get("Panel_Mode")) or "AUTO"
    if mark in BM.UNRELEASED_MARK_TYPES:
        # Decided before the image is opened: there is nothing to try.
        series_level = {_s(r.get("Series_ID")): (_upper(r.get("Factor_Name")),
                                                 _s(r.get("Factor_Level")))
                        for r in series_rows}
        position_level = {_s(r.get("Position_ID")): (_upper(r.get("Factor_Name")),
                                                     _s(r.get("Factor_Level")))
                          for r in position_rows}
        return PanelOutcome(
            "NO_READER_AVAILABLE",
            declared=max(1, len(series_level)) * max(1, len(position_level)),
            detail="%s: %s" % (mark, BM.UNRELEASED_MARK_TYPES[mark]),
            missing=sorted(_all_cells(series_level, position_level)))
    if mode == "MANUAL":
        return PanelOutcome("MANUAL_POINT_READ",
                            detail="Panel_Mode=MANUAL: declared unreadable before the run")

    image_path = _s(panel.get("Image_Path"))
    resolved = image_path if os.path.exists(image_path) \
        else os.path.join(file_root, image_path)
    try:
        box = BM.parse_box(",".join(_s(panel.get(c)) for c in
                                    ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")))
        ycal = _calibration(panel, "Y")
        xcal = _calibration(panel, "X")
        image = Image.open(resolved).convert("RGB")
    except Exception as exc:
        return PanelOutcome("PANEL_GEOMETRY_UNRESOLVED",
                            detail="%s: %s" % (type(exc).__name__, exc))

    series_level = {_s(r.get("Series_ID")): (_upper(r.get("Factor_Name")),
                                             _s(r.get("Factor_Level")))
                    for r in series_rows}
    position_level = {_s(r.get("Position_ID")): (_upper(r.get("Factor_Name")),
                                                 _s(r.get("Factor_Level")))
                      for r in position_rows}
    series_factor = next((f for f, _ in series_level.values() if f), None)
    position_factor = next((f for f, _ in position_level.values() if f), None)
    kwargs = _reader_kwargs(options, mark)
    declared = max(1, len(series_level)) * max(1, len(position_level))

    try:
        if mark == "SCATTER":
            rows = MR.read_panel("SCATTER", image=image, panel_box=box,
                                 x_calibration=xcal, y_calibration=ycal,
                                 series=_series_specs(series_rows, mark, options),
                                 **kwargs)
        elif mark == "BOX_VIOLIN":
            rows = MR.read_panel("BOX_VIOLIN", image=image, panel_box=box,
                                 x_positions=_x_positions(position_rows),
                                 y_calibration=ycal, **kwargs)
        elif mark == "LINE_COLOR":
            rows = MR.read_panel("LINE_COLOR", image=image, panel_box=box,
                                 x_positions=_x_positions(position_rows),
                                 y_calibration=ycal,
                                 series=_series_specs(series_rows, mark, options),
                                 **kwargs)
        elif mark == "LINE_MONO":
            rows = MR.read_panel("LINE_MONO", image=image, panel_box=box,
                                 x_positions=_x_positions(position_rows),
                                 y_calibration=ycal,
                                 series=_series_specs(series_rows, mark, options),
                                 **kwargs)
        elif mark == "BAR_COLOR":
            ticks = [(v, px) for v, px in BM.parse_ticks(panel.get("Axis_Y_Ticks"))]
            mapping = {_s(r.get("Series_ID")): _s(r.get("Mask_Key"))
                       for r in series_rows}
            if BM.blank(panel.get("Baseline_Value")):
                kwargs.setdefault("baseline_value", 0.0)
            else:
                kwargs["baseline_value"] = float(panel.get("Baseline_Value"))
            kwargs.setdefault("n_slots", len(position_level) or None)
            rows = MR.read_panel("BAR_COLOR", image=image, panel_box=box,
                                 ticks=ticks, series=mapping, **kwargs)
            order_to_position = [pid_ for pid_, _ in sorted(
                position_level.items(),
                key=lambda kv: _position_order(position_rows, kv[0]))]
            for row in rows:
                idx = row.get("order")
                row["x_label"] = (order_to_position[idx]
                                  if isinstance(idx, int) and 0 <= idx < len(order_to_position)
                                  else None)
            rows = [r for r in rows if r.get("x_label")]
        elif mark == "BAR_MONO":
            if BM.blank(panel.get("Baseline_Value")):
                kwargs.setdefault("baseline_value", 0.0)
            else:
                kwargs["baseline_value"] = float(panel.get("Baseline_Value"))
            rows = MR.read_panel("BAR_MONO", image=image, panel_box=box,
                                 x_positions=_x_positions(position_rows),
                                 y_calibration=ycal,
                                 series=_series_specs(series_rows, mark, options),
                                 **kwargs)
        elif mark in BM.UNRELEASED_MARK_TYPES:
            return PanelOutcome(
                "NO_READER_AVAILABLE", declared=declared,
                detail="%s: %s" % (mark, BM.UNRELEASED_MARK_TYPES[mark]),
                missing=sorted(_all_cells(series_level, position_level)))
        else:
            return PanelOutcome("NOT_CONVERTIBLE",
                                detail="no reader for Mark_Type=%s" % mark)
    except Exception as exc:
        return PanelOutcome("PANEL_GEOMETRY_UNRESOLVED",
                            detail="%s: %s" % (type(exc).__name__, exc))

    if not rows:
        return PanelOutcome("MANUAL_POINT_READ", declared=declared,
                            detail="the reader resolved no marks in this panel",
                            missing=sorted(_all_cells(series_level, position_level)))

    # ---- a series that produced nothing while its neighbours did is not an
    # ---- empty series: it is an unresolved identity, and it says so.
    if series_level and mark != "SCATTER":
        produced = {r.get("series") for r in rows}
        silent = sorted(set(series_level) - produced)
        if silent and len(silent) < len(series_level):
            return PanelOutcome(
                "SERIES_IDENTITY_UNRESOLVED", declared=declared, read=len(rows),
                detail="series %s produced no marks while %s did - the reader "
                       "cannot separate this panel's series reliably"
                       % (", ".join(silent), ", ".join(sorted(produced))),
                missing=sorted(_all_cells(series_level, position_level)))

    unit_id = _s(panel.get("Unit_ID"))
    raw_path = os.path.join(raw_dir, "%s_marks.json" % pid)

    if mark == "SCATTER":
        return _scatter_outcome(rows, panel, series_level, series_factor, unit,
                                statistic, resolved, xcal, ycal, raw_dir, declared,
                                project_dir)

    # ---- relabel reader output with the DECLARED identity before it becomes a
    # ---- value row. The reader never learns what a series means.
    converted, kept = [], []
    for row in rows:
        sid = row.get("series")
        qid = row.get("x_label")
        levels = {}
        if sid is not None:
            if sid not in series_level:
                continue
            levels[series_level[sid][0]] = series_level[sid][1]
        if qid is not None:
            if qid not in position_level:
                continue
            levels[position_level[qid][0]] = position_level[qid][1]
        if not levels:
            continue
        kept.append(row)
        converted.append(dict(row, series=(series_level[sid][1] if sid is not None else None),
                              x_label=(position_level[qid][1] if qid is not None else None)))

    if not converted:
        return PanelOutcome("MANUAL_POINT_READ", declared=declared,
                            detail="no mark could be matched to a declared series "
                                   "and position",
                            missing=sorted(_all_cells(series_level, position_level)))

    if statistic == "QUANTILE_SUMMARY":
        usable = [r for r in converted if r.get("q1") is not None
                  and r.get("q3") is not None and r.get("median") is not None]
        if not usable:
            return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                                read=len(converted),
                                detail="the marks carry no quartiles, so they "
                                       "cannot become a five-number summary")
        converted = usable
    elif statistic == "CONTINUOUS":
        if all(r.get("dispersion") is None for r in converted):
            state = "NO_VARIANCE"
        elif all(_upper(r.get("Errorbar_Stem_Confirmed")) == "FALSE"
                 for r in converted):
            state = "NO_VARIANCE"
        else:
            state = None
        if state:
            return PanelOutcome(
                state, declared=declared, read=len(converted),
                detail="centres were read but no dispersion survived stem "
                       "confirmation; the panel cannot contribute a weight")

    records = MR.to_value_records(
        converted, statistic or "CONTINUOUS", unit_id,
        x_factor=(position_factor if any(r.get("x_label") for r in converted) else None),
        series_factor=(series_factor if any(r.get("series") for r in converted) else None))
    with open(raw_path, "w", encoding="utf-8") as fh:
        json.dump({"schema": "figure-digitization-triage/mark-data/1",
                   "Panel_ID": pid, "Unit_ID": unit_id, "Mark_Type": mark,
                   "Source_Image": resolved, "Image_SHA256": file_sha256(resolved),
                   "Reader_Version": MR.READER_VERSION,
                   "Y_Calibration": MR._calibration_record(ycal),
                   "X_Calibration": MR._calibration_record(xcal),
                   "Panel_Box": list(box), "marks": _jsonable(kept)},
                  fh, indent=1, sort_keys=True)

    project = None
    if project_dir:
        project = write_panel_project(
            os.path.join(project_dir, "%s.tar" % pid),
            dict(panel, Image_Path=resolved), kept, xcal, ycal)
    with_disp = sum(1 for r in records
                    if r.get("Dispersion_Value") is not None or r.get("Q1") is not None)
    seen = {r["Cell_Key"] for r in records}
    missing = sorted(_all_cells(series_level, position_level) - seen)
    return PanelOutcome("AUTO_PASS", values=records, raw=raw_path, project=project,
                        declared=declared, read=len(records),
                        with_dispersion=with_disp, missing=missing,
                        detail=("" if not missing else
                                "%d of %d declared cells were not resolved"
                                % (len(missing), declared)))


def write_panel_project(path, panel, marks, xcal, ycal):
    """Emit a WebPlotDigitizer project for one automatically read panel.

    The gate requires a saved project on every digitized row, and it is right
    to: "the reader said so" is not something a second person can check. An
    automated run has no human-saved project, so it saves one - the raster, the
    calibration it used, and every mark it placed, in a file that opens in WPD.
    A reviewer can then look at where the reader thought the marks were, which
    is the only cheap way to catch a systematically misplaced series.
    """
    image_path = _s(panel.get("Image_Path"))
    if not os.path.exists(image_path):
        return None
    axes = [dict(name="XY", isLogX=(_upper(panel.get("Axis_X_Scale")) == "LOG"),
                 isLogY=(_upper(panel.get("Axis_Y_Scale")) == "LOG"),
                 calibrationPoints=_calibration_points(panel, xcal, ycal))]
    grouped = {}
    for m in marks:
        key = str(m.get("series") or "ALL")
        px = m.get("point_px_x")
        py = m.get("point_px_y", m.get("marker_center_px", m.get("top_px")))
        if px is None:
            px = m.get("x")
        if px is None or py is None:
            continue
        grouped.setdefault(key, []).append(dict(x=float(px), y=float(py), value=None))
    if not grouped:
        return None
    datasets = [dict(name=name, axesName="XY", data=pts)
                for name, pts in sorted(grouped.items())]
    return WPD.write_project(path, image_path, axes, datasets)


def _calibration_points(panel, xcal, ycal):
    """Two x and two y reference points, in the form WPD stores them."""
    out = []
    for axis, cal, key in (("x", xcal, "Axis_X_Ticks"), ("y", ycal, "Axis_Y_Ticks")):
        if cal is None or BM.blank(panel.get(key)):
            continue
        for value, pixel in BM.parse_ticks(panel.get(key))[:2]:
            if axis == "x":
                out.append(dict(px=float(pixel), py=0.0, dx=value, dy=""))
            else:
                out.append(dict(px=0.0, py=float(pixel), dx="", dy=value))
    return out


def _units_named_by(qc, values_df, units_df):
    """Unit_ID -> the set of gate codes charged to it.

    The gate locates a problem the way a reviewer would open the file - by grain
    and row (`values:14`) or by unit (`unit:U1`). Both have to resolve back to a
    Unit_ID, or a rejected panel keeps reporting AUTO_PASS in run_manifest.csv
    while qc_problems.csv says otherwise. Two files disagreeing about the same
    unit is worse than either being wrong.
    """
    out = {}
    for _, p in qc.iterrows():
        where, code = str(p.get("where", "")), str(p.get("check", ""))
        uid = None
        if where.startswith("unit:"):
            uid = where.split(":", 1)[1]
        elif where.startswith("values:") or where.startswith("units:"):
            frame = values_df if where.startswith("values:") else units_df
            try:
                idx = int(where.split(":", 1)[1]) - 2
            except ValueError:
                idx = -1
            if 0 <= idx < len(frame) and "Unit_ID" in frame.columns:
                uid = str(frame.iloc[idx]["Unit_ID"]).strip()
        if uid:
            out.setdefault(uid, set()).add(code)
    return out


def _position_order(position_rows, position_id):
    for r in position_rows:
        if _s(r.get("Position_ID")) == position_id:
            v = r.get("Display_Order")
            if not BM.blank(v):
                return float(v)
            v = r.get("X_Pixel")
            if not BM.blank(v):
                return float(v)
    return 0.0


def _all_cells(series_level, position_level):
    """Every Cell_Key the manifests declare for this panel."""
    out = set()
    slevels = list(series_level.values()) or [(None, None)]
    plevels = list(position_level.values()) or [(None, None)]
    for sf, sl in slevels:
        for pf, pl in plevels:
            levels = {}
            if sf:
                levels[sf] = sl
            if pf:
                levels[pf] = pl
            if levels:
                out.add(GE.fig_cell_key(levels))
    return out


def _jsonable(rows):
    out = []
    for r in rows:
        item = {}
        for k, v in r.items():
            try:
                json.dumps(v)
                item[k] = v
            except TypeError:
                item[k] = float(v)
        out.append(item)
    return out


def _scatter_outcome(points, panel, series_level, series_factor, unit, statistic,
                     image_path, xcal, ycal, raw_dir, declared, project_dir=None):
    """A scatter yields one association per series, each with its point file."""
    pid = _s(panel.get("Panel_ID"))
    unit_id = _s(panel.get("Unit_ID"))
    if statistic and statistic != "ASSOCIATION":
        return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                            detail="a scatter cannot become Statistic_Type=%s"
                                   % statistic)
    association = _upper(panel.get("Association_Type"))
    sha = file_sha256(image_path)
    records, raw_files, short = [], [], []
    for sid, (factor, level) in sorted(series_level.items()):
        mine = [p for p in points if p.get("series") == sid]
        if len(mine) < 3:
            short.append("%s (%d points)" % (sid, len(mine)))
            continue
        summary = MR.summarize_association(mine, association)
        cell_key = GE.fig_cell_key({factor: level})
        path = os.path.join(raw_dir, "%s_%s_points.json" % (pid, sid))
        MR.write_point_data(mine, path, unit_id=unit_id, cell_key=cell_key,
                            source_image=image_path, image_sha256=sha,
                            x_calibration=xcal, y_calibration=ycal,
                            panel_id=pid, reader="SCATTER")
        raw_files.append(path)
        records.extend(MR.to_value_records(
            [summary], "ASSOCIATION", unit_id,
            cell_levels={factor: level}, point_data_reference=path))
    if not records:
        return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                            detail="no series reached three points: " + "; ".join(short))
    if short:
        return PanelOutcome(
            "MANUAL_POINT_READ", declared=declared, read=len(records),
            detail="some series were too sparse to summarize: " + "; ".join(short),
            missing=sorted(_all_cells(series_level, {}) -
                           {r["Cell_Key"] for r in records}))
    project = None
    if project_dir:
        project = write_panel_project(
            os.path.join(project_dir, "%s.tar" % pid),
            dict(panel, Image_Path=image_path), points, xcal, ycal)
    return PanelOutcome("AUTO_PASS", values=records, raw=";".join(raw_files),
                        project=project, declared=declared, read=len(records),
                        with_dispersion=len(records))


# --------------------------------------------------------------------------
# the batch
# --------------------------------------------------------------------------

#: Everything a run owns in its output directory. A run clears all of it before
#: doing anything else, so no output can outlive the run that produced it.
CANONICAL_OUTPUTS = (
    "figure_values_accepted.csv", "figure_values_raw.csv", "figure_values.csv",
    "run_manifest.csv", "manual_queue.csv", "qc_problems.csv",
    "manifest_problems.csv", "run_stamp.json", "figure_manifest.csv",
    "source_panel_coverage.csv",
)
CANONICAL_DIRS = ("raw", "projects")
STAGING = ".staging"


def clear_outputs(output_dir):
    """Remove every output a previous run left, before this one starts.

    This runs BEFORE validation, and that ordering is the whole point. A run
    that clears up after itself only cleans up when it gets that far: reject a
    manifest and the previous run's `figure_values_accepted.csv` is still
    sitting there, newer than nothing and older than the failure nobody can see
    from inside the file. Somebody pools it.
    """
    for name in CANONICAL_OUTPUTS:
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            os.remove(path)
    for name in CANONICAL_DIRS + (STAGING,):
        path = os.path.join(output_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path)


#: The last file moved into place. Its presence is what says a run committed.
COMMIT_MARKER = "figure_values_accepted.csv"


def promote(work_dir, output_dir, fault_after=None):
    """Move a completed run's outputs into place, marker last.

    A directory rename would be genuinely atomic and is not available here: the
    value rows NAME their point files and WPD projects, so those have to be
    written at their final paths, and a rename would only cover the summary
    CSVs. What is available is an ORDER.

    `figure_values_accepted.csv` moves last and nothing else depends on it, so
    it works as a commit marker. Die partway and the pooling file is the one
    thing that is not there - the failure mode is "no result", not "a result
    missing its audit trail". Everything else is promoted first precisely so
    that, if the marker does land, the files explaining it already have.

    Promotion is then verified: if any expected file failed to arrive the marker
    is withdrawn, because a marker whose evidence is incomplete is worse than no
    marker. `fault_after` is a test hook - the suite injects a failure partway
    through and asserts the directory is not poolable afterwards.
    """
    names = sorted(os.listdir(work_dir))
    ordered = ([n for n in names if n != COMMIT_MARKER]
               + [n for n in names if n == COMMIT_MARKER])
    for i, name in enumerate(ordered):
        if fault_after is not None and i >= fault_after:
            raise RuntimeError(
                "fault injected after promoting %d of %d files" % (i, len(ordered)))
        src, dst = os.path.join(work_dir, name), os.path.join(output_dir, name)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
    absent = [n for n in ordered
              if not os.path.exists(os.path.join(output_dir, n))]
    if absent:
        raise RuntimeError("promotion incomplete, missing: " + ", ".join(absent))
    shutil.rmtree(work_dir, ignore_errors=True)


def withdraw_commit(output_dir, run_date, detail):
    """Undo a half-finished promotion: no marker, and a stamp that says why.

    Called when `promote` raises. The accepted file is removed whether or not it
    made it across, the staging directory is dropped, and the stamp is rewritten
    to PROMOTE_FAILED with zero accepted - so a directory left by a killed
    process reads as a failure rather than as a small result.
    """
    marker = os.path.join(output_dir, COMMIT_MARKER)
    if os.path.exists(marker):
        os.remove(marker)
    shutil.rmtree(os.path.join(output_dir, STAGING), ignore_errors=True)
    write_stamp(os.path.join(output_dir, "run_stamp.json"), "PROMOTE_FAILED",
                run_date, detail=detail)


#: Every verdict a run directory can carry. RAN is the only one under which
#: `figure_values_accepted.csv` may exist.
RUN_STATUSES = ("RAN", "MANIFEST_REJECTED", "INPUT_LOAD_FAILED", "PROMOTE_FAILED")


def write_stamp(path, status, run_date, cfg_hash="", manifest_hashes=None,
                panels=0, read=0, accepted=0, qc_problems=0, problems=0,
                detail=""):
    """The run's verdict, written on EVERY outcome including a rejection.

    A rejected run used to write no stamp at all, which left the previous run's
    stamp in place claiming `Values_Accepted=8`. A stamp that is absent when
    things go wrong is worse than no stamp at all - it is only ever there to
    reassure.
    """
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "figure-digitization-triage/run-stamp/4",
            "Status": status, "Run_Date": run_date,
            "Reader_Version": MR.READER_VERSION,
            "Pipeline_Version": PIPELINE_VERSION,
            "Pipeline_Code_SHA256": pipeline_code_sha256(),
            "Config_SHA256": cfg_hash,
            "Manifest_SHA256": manifest_hashes or {},
            "Panels": panels, "Values_Read": read, "Values_Accepted": accepted,
            "QC_Problems": qc_problems, "Manifest_Problems": problems,
            "Detail": detail,
        }, fh, indent=1, sort_keys=True)


def run_batch(manifest_dir, output_dir, file_root=".", run_date="",
              check_files=True, fault_after=None):
    """Validate, read, convert, gate, and report. Returns a summary dict.

    `fault_after` is a test hook that aborts promotion partway through; it has
    no effect on a normal run.
    """
    # Clear BEFORE anything can fail, including the load. Reading the manifests
    # first looked harmless and was not: a missing directory, a malformed CSV or
    # an unreadable file raised before `clear_outputs` was ever called, so the
    # previous run's accepted file and its `Status=RAN` stamp both survived a
    # run that never happened. "Nothing outlives the run that replaces it" only
    # holds if the clearing is the first thing the run does.
    os.makedirs(output_dir, exist_ok=True)
    clear_outputs(output_dir)
    try:
        m = load_manifests(manifest_dir)
    except Exception as exc:
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "INPUT_LOAD_FAILED", run_date,
                    detail="%s: %s" % (type(exc).__name__, exc))
        raise
    manifest_hashes = {k: frame_sha256(v) for k, v in sorted(m.items())}

    problems = BM.validate_batch_manifests(
        m["panels"], m["series"], m["positions"], m["configs"],
        units=m["units"], source_documents=m["source_documents"],
        source_figures=m["source_figures"],
        source_panels=m["source_panels"], file_root=file_root,
        check_files=check_files)
    if len(problems):
        problems.to_csv(os.path.join(output_dir, "manifest_problems.csv"),
                        index=False)
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "MANIFEST_REJECTED", run_date,
                    manifest_hashes=manifest_hashes, problems=len(problems))
        return dict(status="MANIFEST_REJECTED", problems=len(problems),
                    values=0, accepted=0,
                    detail=sorted(set(problems["check"])))

    # Only now, once the batch is known to be runnable, does anything get
    # created. The point clouds and WPD projects live at their final paths
    # because the value rows have to NAME them - staging a file whose path is
    # recorded inside another file means rewriting paths, and a path rewrite is
    # a place for a stale reference to survive. The summary CSVs, which name
    # nothing, are staged and promoted in one move at the end.
    work_dir = os.path.join(output_dir, STAGING)
    os.makedirs(work_dir, exist_ok=True)
    raw_dir = os.path.join(output_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    project_dir = os.path.join(output_dir, "projects")
    os.makedirs(project_dir, exist_ok=True)

    options_by_config = BM.load_reader_configs(
        m["configs"],
        {_s(r.get("Config_ID")): {_upper(r.get("Mark_Type"))}
         for _, r in m["panels"].iterrows() if not BM.blank(r.get("Config_ID"))},
        lambda *a: None)
    cfg_hash = BM.config_hash(m["configs"])
    units_by_id = {_s(u.get("Unit_ID")): u for _, u in m["units"].iterrows()}

    series_by_panel, positions_by_panel = {}, {}
    for _, r in m["series"].iterrows():
        series_by_panel.setdefault(_s(r.get("Panel_ID")), []).append(r)
    for _, r in m["positions"].iterrows():
        positions_by_panel.setdefault(_s(r.get("Panel_ID")), []).append(r)

    values, run_rows, queue_rows, projects_by_figure = [], [], [], {}
    for _, panel in m["panels"].iterrows():
        pid = _s(panel.get("Panel_ID"))
        unit = units_by_id.get(_s(panel.get("Unit_ID")))
        options = options_by_config.get(_s(panel.get("Config_ID")), {})
        outcome = run_panel(panel, series_by_panel.get(pid, []),
                            positions_by_panel.get(pid, []), options, unit,
                            raw_dir, file_root=file_root, project_dir=project_dir)
        if outcome.project:
            projects_by_figure.setdefault(_s(panel.get("Figure_ID")), outcome.project)
        # Stamp the panel onto every value it produced. A unit is normally one
        # panel, but nothing forbids two panels feeding one - and keying panel
        # state by Unit_ID meant the LAST panel's state won, so a unit whose
        # first panel failed and whose second passed came out ACCEPTED. Each
        # value now carries where it came from and is judged on that.
        for record in outcome.values:
            record["Run_Panel_ID"] = pid
            record["Source_Panel_ID"] = _s(panel.get("Source_Panel_ID"))
        values.extend(outcome.values)
        image_path = _s(panel.get("Image_Path"))
        resolved = image_path if os.path.exists(image_path) \
            else os.path.join(file_root, image_path)
        run_rows.append({
            "Panel_ID": pid, "Source_Panel_ID": _s(panel.get("Source_Panel_ID")),
            "Figure_ID": _s(panel.get("Figure_ID")),
            "Unit_ID": _s(panel.get("Unit_ID")),
            "Mark_Type": _upper(panel.get("Mark_Type")),
            "Run_State": outcome.state, "Cells_Declared": outcome.declared,
            "Cells_Read": outcome.read,
            "Cells_With_Dispersion": outcome.with_dispersion,
            "Image_Path": image_path,
            "Image_SHA256": (file_sha256(resolved) if os.path.exists(resolved) else ""),
            "Config_ID": _s(panel.get("Config_ID")), "Config_SHA256": cfg_hash,
            "Reader_Version": MR.READER_VERSION,
            "Pipeline_Version": PIPELINE_VERSION,
            "Pipeline_Code_SHA256": pipeline_code_sha256(),
            "Raw_Data_File": outcome.raw or "",
            "WPD_Project_File": outcome.project or "", "Run_Date": run_date,
            "Detail": outcome.detail,
        })
        if outcome.state != "AUTO_PASS" or outcome.missing:
            queue_rows.append({
                "Panel_ID": pid, "Source_Panel_ID": _s(panel.get("Source_Panel_ID")),
                "Figure_ID": _s(panel.get("Figure_ID")),
                "Unit_ID": _s(panel.get("Unit_ID")),
                "Mark_Type": _upper(panel.get("Mark_Type")),
                "Run_State": outcome.state,
                "Missing_Cells": ";".join(outcome.missing),
                "Image_Path": image_path,
                "Panel_Box": ",".join(_s(panel.get(c)) for c in
                                      ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")),
                "Detail": outcome.detail,
            })

    # Inventory-only target panels are actionable work, not merely a coverage
    # statistic.  They have no geometry/config yet, so they cannot enter the
    # reader loop; put them in the same manual queue with their physical image
    # and stated reason.  This is what lets a 100-paper batch expose every
    # unconfigured target panel without inventing dummy reader manifests.
    linked_source_ids = {
        _s(r.get("Source_Panel_ID")) for _, r in m["panels"].iterrows()
        if _s(r.get("Source_Panel_ID"))
    }
    source_fig_by_id = {
        _s(r.get("Source_Figure_ID")): r for _, r in m["source_figures"].iterrows()
    }
    for _, sr in m["source_panels"].iterrows():
        spid = _s(sr.get("Source_Panel_ID"))
        disposition = _upper(sr.get("Panel_Disposition"))
        if spid in linked_source_ids or disposition not in (
                "MANUAL_DIGITIZE", "NO_READER_AVAILABLE"):
            continue
        sf = source_fig_by_id.get(_s(sr.get("Source_Figure_ID")), {})
        queue_rows.append({
            "Panel_ID": "", "Source_Panel_ID": spid, "Figure_ID": "",
            "Unit_ID": "", "Mark_Type": "",
            "Run_State": ("NO_READER_AVAILABLE" if disposition ==
                          "NO_READER_AVAILABLE" else "MANUAL_POINT_READ"),
            "Missing_Cells": "", "Image_Path": _s(sf.get("Source_Image")),
            "Panel_Box": "",
            "Detail": "%s | %s | %s" % (
                _s(sr.get("Panel_Label")), _s(sr.get("Outcome_Label")),
                _s(sr.get("Disposition_Reason"))),
        })

    values_df = pd.DataFrame(
        [{c: r.get(c, "") for c in GE.fig_values_columns()} for r in values],
        columns=GE.fig_values_columns())

    # The gate requires a re-openable project on every digitized row, and it is
    # right to. An automated run has no human-saved one, so it saved its own -
    # the raster, the calibration it used and every mark it placed. Record that
    # against the figure rather than leaving the column blank and arguing the
    # requirement does not apply to machines; it applies most to machines.
    figures = m["figures"].copy()
    if projects_by_figure and "WPD_Project_File" in figures.columns:
        figures["WPD_Project_File"] = [
            (projects_by_figure.get(_s(r.get("Figure_ID")), "")
             if BM.blank(r.get("WPD_Project_File")) else r.get("WPD_Project_File"))
            for _, r in figures.iterrows()]
        figures.to_csv(os.path.join(work_dir, "figure_manifest.csv"), index=False)

    qc = GE.fig_validate_bundle(figures, m["grids"], m["units"], values_df,
                                kernel=K, file_root=file_root,
                                check_files=check_files)

    # A panel whose values the gate rejected did not pass, whatever the reader
    # thought of them. Re-state it here, so run_manifest.csv and qc_problems.csv
    # cannot tell a reviewer two different stories about the same unit.
    if len(qc):
        blamed = _units_named_by(qc, values_df, m["units"])
        for row in run_rows:  # noqa: B007
            uid = row["Unit_ID"]
            if row["Run_State"] != "AUTO_PASS" or not uid or uid not in blamed:
                continue
            row["Run_State"] = "QC_FAILED"
            row["Detail"] = ("the grid gate rejected this unit's values: %s"
                             % ", ".join(sorted(blamed[uid])))
            queue_rows.append({
                "Panel_ID": row["Panel_ID"],
                "Source_Panel_ID": row["Source_Panel_ID"],
                "Figure_ID": row["Figure_ID"],
                "Unit_ID": uid, "Mark_Type": row["Mark_Type"],
                "Run_State": "QC_FAILED", "Missing_Cells": "",
                "Image_Path": row["Image_Path"], "Panel_Box": "",
                "Detail": row["Detail"],
            })

    run_df = pd.DataFrame(run_rows, columns=RUN_MANIFEST_COLUMNS)
    queue_df = pd.DataFrame(queue_rows, columns=MANUAL_QUEUE_COLUMNS)

    # ---- what a downstream reader is allowed to pool ----------------------
    # There is deliberately no file called `figure_values.csv` any more. One
    # existed, it held every value the readers produced, and on publication 397
    # it carried eight means whose SD-versus-SEM was unresolved while both
    # panels sat at QC_FAILED in a different file. Anyone reading "the values
    # file" - which is the obvious thing to do - would have pooled them.
    #
    # The safe file is now the one with the plainest name, the unsafe one
    # carries its own verdict in every row, and neither can be mistaken for the
    # other by a script that does not know to join.
    panel_state = {r["Panel_ID"]: r["Run_State"] for r in run_rows}
    # A unit's state, when it has to be summarised, is the WORST of the panels
    # that build it - never the last one seen. Only used as a fallback for a row
    # whose Source_Panel_ID is somehow missing; the per-row link is primary.
    unit_state = {}
    for r in run_rows:
        uid = r["Unit_ID"]
        if not uid:
            continue
        if r["Run_State"] != "AUTO_PASS" or uid not in unit_state:
            unit_state[uid] = r["Run_State"]
    blamed = _units_named_by(qc, values_df, m["units"]) if len(qc) else {}
    run_panel_ids = [_s(rec.get("Run_Panel_ID")) for rec in values]
    source_panel_ids = [_s(rec.get("Source_Panel_ID")) for rec in values]
    statuses, codes, eligible = [], [], []
    for i, (_, row) in enumerate(values_df.iterrows()):
        uid = _s(row.get("Unit_ID"))
        unit_codes = sorted(blamed.get(uid, ()))
        pid = run_panel_ids[i] if i < len(run_panel_ids) else ""
        own = panel_state.get(pid) or unit_state.get(uid, "")
        # Both tests, and the second is the one that is easy to miss. A unit
        # built from two panels where one failed and the other filled the whole
        # grid leaves the gate nothing to complain about - the cells are all
        # there. But nobody knows whether the panel that could not be read would
        # have agreed with the one that could, and "the readable half says so"
        # is not a reading of the figure.
        worst = unit_state.get(uid, own)
        if unit_codes:
            statuses.append("QC_FAILED")
        elif own != "AUTO_PASS" or worst != "AUTO_PASS":
            statuses.append("PANEL_NOT_PASSED")
        else:
            statuses.append("ACCEPTED")
        codes.append(";".join(unit_codes))
        eligible.append("TRUE" if statuses[-1] == "ACCEPTED" else "FALSE")
    raw_df = values_df.copy()
    raw_df["Run_Panel_ID"] = run_panel_ids
    raw_df["Source_Panel_ID"] = source_panel_ids
    raw_df["Value_Status"] = statuses
    raw_df["QC_Codes"] = codes
    raw_df["Pooling_Eligible"] = eligible
    accepted_df = raw_df[raw_df["Pooling_Eligible"] == "TRUE"].copy()

    # Source-level coverage is the antidote to virtual Figure_IDs masking
    # omissions.  Every physical panel appears exactly once here, including
    # non-target, not-data, manual and no-reader panels.  The accepted values
    # file remains the pooling surface; this is the completeness ledger.
    runs_by_source = {}
    for _, rr in run_df.iterrows():
        spid = _s(rr.get("Source_Panel_ID"))
        if spid:
            runs_by_source.setdefault(spid, []).append(rr)
    coverage_rows = []
    for _, sr in m["source_panels"].iterrows():
        spid = _s(sr.get("Source_Panel_ID"))
        linked = runs_by_source.get(spid, [])
        states = sorted({_s(x.get("Run_State")) for x in linked if _s(x.get("Run_State"))})
        disposition = _upper(sr.get("Panel_Disposition"))
        if linked:
            coverage_status = ("AUTO_PASS" if states == ["AUTO_PASS"]
                               else "QUEUED_OR_FAILED")
        elif disposition in ("MANUAL_DIGITIZE", "NO_READER_AVAILABLE"):
            coverage_status = "QUEUED_SOURCE_ONLY"
        elif disposition in BM._CLOSED_WITHOUT_READER:
            coverage_status = "CLOSED_%s" % disposition
        else:
            coverage_status = "UNRESOLVED"
        rec = {c: sr.get(c, "") for c in BM.source_panel_inventory_columns()}
        rec.update({
            "Linked_Run_Panel_Count": len(linked),
            "Linked_Panel_IDs": ";".join(sorted({_s(x.get("Panel_ID")) for x in linked})),
            "Run_States": ";".join(states),
            "Coverage_Status": coverage_status,
        })
        coverage_rows.append(rec)
    coverage_df = pd.DataFrame(coverage_rows)

    raw_df.to_csv(os.path.join(work_dir, "figure_values_raw.csv"), index=False)
    accepted_df.to_csv(os.path.join(work_dir, "figure_values_accepted.csv"),
                       index=False)
    run_df.to_csv(os.path.join(work_dir, "run_manifest.csv"), index=False)
    queue_df.to_csv(os.path.join(work_dir, "manual_queue.csv"), index=False)
    qc.to_csv(os.path.join(work_dir, "qc_problems.csv"), index=False)
    coverage_df.to_csv(os.path.join(work_dir, "source_panel_coverage.csv"), index=False)
    write_stamp(os.path.join(work_dir, "run_stamp.json"), "RAN", run_date,
                cfg_hash=cfg_hash, manifest_hashes=manifest_hashes,
                panels=len(run_df), read=len(raw_df), accepted=len(accepted_df),
                qc_problems=int(len(qc)))
    try:
        promote(work_dir, output_dir, fault_after=fault_after)
    except Exception as exc:
        withdraw_commit(output_dir, run_date, "%s: %s" % (type(exc).__name__, exc))
        raise

    counts = run_df["Run_State"].value_counts().to_dict() if len(run_df) else {}
    return dict(status="RAN", panels=len(run_df), values=len(raw_df),
                accepted=len(accepted_df), qc_problems=int(len(qc)),
                states=counts, manual_queue=len(queue_df),
                config_sha256=cfg_hash)


def emit_templates(directory):
    """Write the four blank batch templates, generated from the column functions."""
    import csv
    os.makedirs(directory, exist_ok=True)
    written = []
    for name, fn in BM.BATCH_TEMPLATES:
        path = os.path.join(directory, "%s_TEMPLATE.csv" % name)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(fn())
        written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manifest_dir")
    ap.add_argument("output_dir")
    ap.add_argument("--file-root", default=".")
    ap.add_argument("--date", default="")
    ap.add_argument("--no-file-check", action="store_true")
    args = ap.parse_args(argv)
    try:
        summary = run_batch(args.manifest_dir, args.output_dir,
                            file_root=args.file_root, run_date=args.date,
                            check_files=not args.no_file_check)
    except ManifestLoadError as exc:
        print("inputs could not be loaded: %s" % exc)
        print("the output directory was cleared and run_stamp.json records "
              "Status=INPUT_LOAD_FAILED")
        return 3
    if summary["status"] == "MANIFEST_REJECTED":
        print("manifests rejected: %d problems" % summary["problems"])
        for code in summary["detail"]:
            print("  " + code)
        print("see manifest_problems.csv")
        return 2
    print("panels %d | values read %d | ACCEPTED %d | qc problems %d | queue %d"
          % (summary["panels"], summary["values"], summary["accepted"],
             summary["qc_problems"], summary["manual_queue"]))
    for state, n in sorted(summary["states"].items()):
        print("  %-28s %d" % (state, n))
    print("pool from figure_values_accepted.csv; figure_values_raw.csv carries "
          "everything read, with Value_Status on every row")
    return 0 if summary["qc_problems"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
