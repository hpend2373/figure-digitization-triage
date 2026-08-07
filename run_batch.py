"""Read a whole batch of declared panels, and say honestly what it could not do.

    python3 run_batch.py MANIFEST_DIR OUTPUT_DIR [--file-root DIR]
                         [--date YYYY-MM-DD] [--demo-only]

Exit 0 means the run completed, NOT that everything read cleanly. QC problems
are a result: publication 397 ships with 108 of them because its dispersion
definition is unresolved, and a run reproducing them has done its job exactly.
Read `run_stamp.json` for the verdict. Non-zero exits are 2 manifests rejected,
3 inputs unloadable, 4 demo output refused, 5 an internal defect.

The run mode is derived from `reviewer_registry.csv`: a reviewer recorded as
`Reviewer_Record_Type=DEMO_IDENTITY` makes the run DEMO_ONLY, which executes in
full but refuses (exit 4) rather than writing values a fictional reviewer would
appear to have attested. `--demo-only` demotes a real registry; `--attested`
asserts a real one and fails with RUN_MODE_REVIEWER_MISMATCH if it is not.

Input  (MANIFEST_DIR): all eleven are mandatory - a missing one is
                       INPUT_LOAD_FAILED, not a default

                       reviewer_registry.csv, source_document_manifest.csv,
                       source_figure_manifest.csv, source_panel_inventory.csv,
                       figure_manifest.csv, grid_definitions.csv,
                       unit_manifest.csv, panel_manifest.csv,
                       series_manifest.csv, position_manifest.csv,
                       reader_config.csv
Output (OUTPUT_DIR):   figure_values_machine_qc.csv <- passed the gate; NOT poolable
                       review_queue.csv            <- one row per panel a person
                                                      must now look at
                       review/<Panel_ID>_overlay.png <- what the reader saw,
                                                      drawn on what it read
                       figure_values_raw.csv       <- everything read, with
                                                      Value_Status/QC_Codes per row
                       source_panel_coverage.csv   <- one row per physical panel
                       run_manifest.csv, manual_queue.csv, qc_problems.csv,
                       figure_manifest.csv, run_stamp.json, raw/, projects/

**This module does not write `figure_values_accepted.csv`.** It stops at
MACHINE_QC_PASSED, which means the gate found nothing wrong - a different claim
from a person having looked at where the marks landed. `finalize_batch.py` reads
`value_review.csv` and writes the accepted file for approved panels only.

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
import review_overlay as OVERLAY                                   # noqa: E402

PIPELINE_VERSION = "7.20"
PIPELINE_CODE_FILES = (
    "run_batch.py", "batch_manifests.py", "grid_engine.py", "kernel.py",
    "mark_readers.py", "bar_reader.py", "make_wpd_project.py",
    "review_overlay.py", "finalize_batch.py", "compile_plan.py",
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
    "reviewers": "reviewer_registry.csv",
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

REVIEW_QUEUE_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type",
    "Cells_Read", "Cells_Declared",
    # HOW this panel can be judged. The protocol says to open the overlay for
    # every queued row, and a scatter had none - so the column was silently
    # empty and an approval was a statement about nothing in particular. A
    # panel now declares what a reviewer will actually be looking at, and the
    # finalizer refuses an approval whose declared artifact is not there.
    "Review_Mode",
    "Overlay_File", "WPD_Project_File", "Raw_Data_File",
    # What the approval is an approval OF: the values, the manifests, the
    # artifacts and the environment. Change any of them and this changes, which
    # is what makes a stale approval visible instead of inherited.
    "Review_Subject_SHA256",
    # Filled in by a person, then read by finalize_batch.py.
    "Decision", "Reviewer_ID", "Reviewed_At", "Note",
]

#: What a reviewer is allowed to write in `Decision`.
REVIEW_DECISIONS = ("APPROVED", "REJECTED")

#: What a queued panel offers a reviewer, and which `panel_artifacts.csv`
#: Artifact_Type must therefore be present for it. `OVERLAY` is the normal case. `WPD_ONLY` exists because
#: `draw_panel_overlay` never raises - a picture that cannot be painted must not
#: fail a panel that produced values - so a panel can legitimately reach the
#: queue with a project and no overlay. What it may NOT do is reach the queue
#: claiming a review nobody can perform.
REVIEW_MODES = {"OVERLAY": "OVERLAY", "WPD_ONLY": "WPD_PROJECT"}


def sha256_of_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256_or_blank(path):
    try:
        return file_sha256(path)
    except Exception:
        return ""


def review_subject_sha256(run_row, values, manifest_hashes, environment,
                          artifacts=()):
    """Everything a person is actually approving when they approve a panel.

    The first version hashed the panel id, the unit id, the mark type, the image
    hash, the config hash, the reader version, the pipeline code hash and the
    cell count - and its docstring claimed an approval went stale whenever "the
    image, the config, the reader or the pipeline" changed. The guarantee was
    narrower than the sentence. None of these were covered:

        the Mean and Dispersion_Value the person read off the overlay
        the Cell_Key each value carries
        the Factor_Name/Factor_Level a series or position MEANS
        the panel box and the axis ticks
        the unit and grid manifests
        the OpenCV version that found the marks
        the raw mark JSON, the WPD project and the overlay PNG

    So an approval survived swapping CONTROL and TREATED, editing a Mean, or
    changing the library that produced it. What a reviewer approves is a
    picture of particular numbers, and the subject of the approval has to be
    those numbers.

    The manifest hashes are taken whole rather than sliced per panel. That
    expires some approvals that did not need to expire - edit one unrelated
    panel's box and every decision in the batch goes stale - which is the right
    way round: re-approving work you already looked at costs an afternoon, and
    a stale approval surviving costs the analysis.
    """
    material = [
        "run_row:" + "|".join("%s=%s" % (k, run_row.get(k, "")) for k in (
            "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type",
            "Run_State", "Cells_Declared", "Cells_Read", "Image_SHA256",
            "Config_SHA256", "Reader_Version", "Pipeline_Version",
            "Pipeline_Code_SHA256")),
        "manifests:" + json.dumps(manifest_hashes, sort_keys=True),
        "environment:" + json.dumps(environment, sort_keys=True),
        # Every artifact this panel produced, by type and content. This used to
        # be two lines - `raw:` and `project:` - each hashing one path out of
        # the run row. The overlay, the picture the person is actually looking
        # at, was named in the docstring above and hashed nowhere; and a
        # multi-series scatter's `Raw_Data_File` is several paths joined with
        # ";", which is not a file, so it hashed to the empty string and the
        # point clouds were not in the subject at all.
        #
        # Basenames, not full paths: the subject is what the person saw, and
        # moving the output directory does not change that.
    ] + ["artifact:%s|%s|%s" % (kind, os.path.basename(_s(path)), digest)
         for kind, path, digest in sorted(artifacts)]
    for row in sorted(values, key=lambda r: _s(r.get("Cell_Key"))):
        material.append("value:" + "|".join(
            "%s=%s" % (k, row.get(k, "")) for k in sorted(row)
            if k not in ("Note", "Reconciliation_Note")))
    return sha256_of_text("\n".join(material))


MANUAL_QUEUE_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type", "Run_State",
    # A COUNT, not a list. This joined cell keys with ";" - and a Cell_Key is
    # itself FACTOR=LEVEL pairs joined by ";", so "ARM=A;T=1;ARM=B;T=1" could
    # not be split back into the two cells it came from. The list lives in
    # `manual_queue_cells.csv`, one row per cell, where it can be counted,
    # filtered and joined.
    "Missing_Cell_Count", "Image_Path", "Panel_Box", "Detail",
]

MANUAL_QUEUE_CELL_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Run_State", "Cell_Key",
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


def environment_record():
    """Everything outside this package that a value depended on.

    A run recorded its own code hash and nothing about what that code ran on.
    Contour finding, raster decoding and least-squares fitting all live in
    libraries this package pins only by lower bound, and a bar top found at row
    312 by one OpenCV and row 313 by the next is a different number in the
    accepted file. Reproducing a run means reproducing this too, so the run
    writes it down instead of leaving it to be reconstructed from a memory of
    which machine it was on.
    """
    import platform
    versions = {}
    for name in ("numpy", "pandas", "PIL", "cv2"):
        try:
            module = __import__(name)
        except Exception:                                    # pragma: no cover
            versions[name] = "not installed"
        else:
            versions[name] = str(getattr(module, "__version__", "unknown"))
    return {
        "Python": platform.python_version(),
        "Implementation": platform.python_implementation(),
        "Platform": platform.platform(),
        "Libraries": versions,
    }


def pipeline_code_sha256():
    h = hashlib.sha256()
    for name in PIPELINE_CODE_FILES:
        path = os.path.join(HERE, name)
        h.update(name.encode("utf-8") + b"\0")
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


class InternalReaderError(Exception):
    """A reader raised something it was not built to raise.

    Not a figure problem, and not a queue row. `run_panel` wrapped every reader
    call in `except Exception` and reported the result as
    PANEL_GEOMETRY_UNRESOLVED, so a TypeError from a misspelled keyword reached
    a human as "re-read this figure". Over 116 publications that turns a defect
    in this package into hours of correct manual work that nobody knows was
    unnecessary - and leaves the defect in place for the next batch.

    This stops the run and keeps the traceback.
    """


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
                 declared=0, read=0, with_dispersion=0, missing=(), project=None,
                 overlay=None, artifacts=()):
        self.state = state
        self.values = values or []
        self.detail = detail
        self.raw = raw
        self.project = project
        self.overlay = overlay
        self.declared = declared
        self.read = read
        self.with_dispersion = with_dispersion
        self.missing = list(missing)
        # Every file this panel produced that a person might look at or a
        # script might re-derive from, as (TYPE, path) pairs. `raw` was a
        # single string, and a multi-series scatter joined its point files with
        # ";" - so the one thing that hashed it got a path that does not exist
        # and recorded an empty hash. A list cannot be joined into a lie.
        self.artifacts = list(artifacts)


#: Everything a run leaves on disk that a person looks at or a script re-derives
#: from. The four CSVs were hashed and re-checked; these were not, so the
#: picture a reviewer approved could be swapped for a different picture after
#: they approved it and the finalizer had nothing to say.
PANEL_ARTIFACT_TYPES = ("OVERLAY", "WPD_PROJECT", "RAW_MARKS", "POINT_DATA")
PANEL_ARTIFACT_COLUMNS = ["Panel_ID", "Artifact_Type", "Artifact_Path", "SHA256"]


def _run_relative(path, run_dir):
    """An artifact path as the run directory sees it: `review/P1_overlay.png`.

    The ledger has to survive `mv OUT /elsewhere` and has to be readable from a
    process whose working directory is not the one the run had. Neither an
    absolute path nor a bare relative one does both.
    """
    try:
        return os.path.relpath(os.path.realpath(path),
                               os.path.realpath(run_dir)).replace(os.sep, "/")
    except ValueError:                                          # pragma: no cover
        # Different drives on Windows. Falling back to the absolute path keeps
        # the ledger honest; `resolve_artifact` will refuse it as outside.
        return path


def resolve_artifact(run_dir, recorded):
    """The absolute path a ledger entry names, or None if it escapes the run.

    A relative entry is joined to the run directory. Anything that resolves
    outside it is refused rather than read: a ledger is a statement about what
    this run wrote into its own directory, and `../../etc/passwd` is not that.
    """
    root = os.path.realpath(run_dir)
    candidate = os.path.realpath(os.path.join(root, recorded))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate


def _panel_artifacts(raw_marks=(), point_data=(), project=None, overlay=None):
    """(TYPE, path) pairs for one panel, in a fixed order, skipping what is absent."""
    out = []
    if overlay:
        out.append(("OVERLAY", overlay))
    if project:
        out.append(("WPD_PROJECT", project))
    for path in raw_marks:
        if path:
            out.append(("RAW_MARKS", path))
    for path in point_data:
        if path:
            out.append(("POINT_DATA", path))
    return out


def run_panel(panel, series_rows, position_rows, options, unit, raw_dir,
              file_root=".", project_dir=None, review_dir=None):
    """Read one declared panel. Returns a PanelOutcome; never raises for data."""
    pid = _s(panel.get("Panel_ID"))
    mark = _upper(panel.get("Mark_Type"))
    statistic = _upper(unit.get("Statistic_Type")) if unit is not None else ""
    mode = _upper(panel.get("Panel_Mode")) or "AUTO"

    # What this panel CLAIMS, computed first and used by every exit below.
    #
    # `Panel_Mode=MANUAL` returned before any of this, and so did an unopenable
    # raster and an unparseable box, so those panels reported Cells_Declared=0
    # and Missing_Cells="". A manual panel with twenty-four cells came out as
    # "MANUAL_POINT_READ 0 / 0" - the queue understated the hand-digitizing left
    # to do, on exactly the panels that are nothing but hand-digitizing. Only
    # the unreleased-mark-type path bothered to compute it, so two paths out of
    # three lied about the same thing.
    series_level = {_s(r.get("Series_ID")): (_upper(r.get("Factor_Name")),
                                             _s(r.get("Factor_Level")))
                    for r in series_rows}
    position_level = {_s(r.get("Position_ID")): (_upper(r.get("Factor_Name")),
                                                 _s(r.get("Factor_Level")))
                      for r in position_rows}
    series_factor = next((f for f, _ in series_level.values() if f), None)
    position_factor = next((f for f, _ in position_level.values() if f), None)
    declared = max(1, len(series_level)) * max(1, len(position_level))
    all_cells = sorted(_all_cells(series_level, position_level))

    if mark in BM.UNRELEASED_MARK_TYPES:
        # Decided before the image is opened: there is nothing to try.
        return PanelOutcome(
            "NO_READER_AVAILABLE", declared=declared,
            detail="%s: %s" % (mark, BM.UNRELEASED_MARK_TYPES[mark]),
            missing=all_cells)
    if mode == "MANUAL":
        return PanelOutcome(
            "MANUAL_POINT_READ", declared=declared, missing=all_cells,
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
    except (ValueError, OSError) as exc:
        # A box that does not parse, a calibration that cannot be fitted, a
        # raster that will not open. All three are about the figure.
        return PanelOutcome("PANEL_GEOMETRY_UNRESOLVED", declared=declared,
                            missing=all_cells,
                            detail="%s: %s" % (type(exc).__name__, exc))
    except Exception as exc:
        raise InternalReaderError(
            "preparing panel %s raised %s: %s"
            % (pid, type(exc).__name__, exc)) from exc

    kwargs = _reader_kwargs(options, mark)

    try:
        if mark == "SCATTER":
            rows = MR.read_panel("SCATTER", image=image, panel_box=box,
                                 x_calibration=xcal, y_calibration=ycal,
                                 series=_series_specs(series_rows, mark, options),
                                 **kwargs)
        elif mark == "BOX_VIOLIN":
            # The released reader finds boxes at declared x positions and does
            # not tell two overlaid groups apart. The batch layer requires a
            # series row on every positional panel, so a two-series box panel
            # validated, ran, and produced half a grid - the reader's rows
            # carried no series at all and every TREATED cell came out missing.
            # One declared series is honoured; more is refused before the run.
            if len(series_level) != 1:
                raise MR.UnsupportedCapabilityError(
                    "BOX_VIOLIN reads boxes at declared x positions and cannot "
                    "separate %d series drawn in one panel. Declare one series "
                    "for the whole panel, or route the panel to MANUAL until a "
                    "grouped box reader ships" % len(series_level))
            rows = MR.read_panel("BOX_VIOLIN", image=image, panel_box=box,
                                 x_positions=_x_positions(position_rows),
                                 y_calibration=ycal, **kwargs)
            # The reader returns positions; the single declared series is what
            # they mean. Stamped here so the relabel below is the same code path
            # as every other mark type.
            only = next(iter(series_level))
            for row in rows:
                row["series"] = only
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
            # The same AxisCalibration every other reader gets, so LOG is a
            # scale rather than a silent linear fit, and the declared x pixels
            # rather than a pitch reconstructed from whatever was detected.
            # Each series reads through a mask built from ITS OWN declared
            # colour. `Mask_Key` picked one of three hard-coded masks tuned on
            # one publication, so a figure drawn in green and purple had no way
            # through - while `Colour_Hex` was required, validated and ignored,
            # and `colour_tolerance` was an option with no reader keyword.
            # Mask_Key still works where it is declared, for the two worked
            # examples that use it.
            default_tolerance = float(options.get("colour_tolerance", 60.0))
            declared_colours, mapping = {}, {}
            for r in series_rows:
                sid = _s(r.get("Series_ID"))
                if not BM.blank(r.get("Mask_Key")):
                    # Case-folded, because the mask names are lower case and a
                    # manifest is written by a person. The validator refuses a
                    # key that names no mask, so this can only be a spelling.
                    mapping[sid] = _s(r.get("Mask_Key")).casefold()
                    continue
                tol = (float(r.get("Colour_Tolerance"))
                       if not BM.blank(r.get("Colour_Tolerance"))
                       else default_tolerance)
                declared_colours[sid] = (_s(r.get("Colour_Hex")), tol)
                mapping[sid] = sid
            kwargs["declared_colours"] = declared_colours
            if BM.blank(panel.get("Baseline_Value")):
                kwargs.setdefault("baseline_value", 0.0)
            else:
                kwargs["baseline_value"] = float(panel.get("Baseline_Value"))
            rows = MR.read_panel("BAR_COLOR", image=image, panel_box=box,
                                 y_calibration=ycal,
                                 x_positions=_x_positions(position_rows),
                                 series=mapping, **kwargs)
            # Belt and braces: if the anchors were empty the reader would fall
            # back to counting bars off left to right, and a batch value must
            # never carry a position nobody declared.
            inferred = [r_ for r_ in rows
                        if r_.get("Position_Assignment") != "DECLARED_ANCHOR"]
            if inferred:
                return PanelOutcome(
                    "SERIES_IDENTITY_UNRESOLVED", declared=declared,
                    missing=sorted(_all_cells(series_level, position_level)),
                    detail="%d bar(s) were positioned by sequence rather than "
                           "by a declared X_Pixel" % len(inferred))
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
    except MR.SeriesIdentityError as exc:
        return PanelOutcome("SERIES_IDENTITY_UNRESOLVED", declared=declared,
                            missing=sorted(_all_cells(series_level, position_level)),
                            detail="%s" % exc)
    except MR.UnsupportedCapabilityError as exc:
        return PanelOutcome("NO_READER_AVAILABLE", declared=declared,
                            missing=sorted(_all_cells(series_level, position_level)),
                            detail="%s" % exc)
    except (MR.GeometryResolutionError, ValueError, OSError) as exc:
        return PanelOutcome("PANEL_GEOMETRY_UNRESOLVED", declared=declared,
                            missing=sorted(_all_cells(series_level, position_level)),
                            detail="%s: %s" % (type(exc).__name__, exc))
    except Exception as exc:
        # TypeError, KeyError, AttributeError, IndexError - a reader raising one
        # of these is a defect in this package, not a difficult figure.
        raise InternalReaderError(
            "reader %s on panel %s raised %s: %s"
            % (mark, pid, type(exc).__name__, exc)) from exc

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
                                project_dir, review_dir=review_dir, box=box)

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
    overlay = None
    if review_dir:
        overlay = OVERLAY.draw_panel_overlay(
            os.path.join(review_dir, "%s_overlay.png" % pid), resolved, box, kept,
            title="%s  %s  %s" % (pid, unit_id, mark),
            subtitle="%d marks read of %d declared cells - approve only if each "
                     "label sits on the mark a reader would give it"
                     % (len(kept), declared),
            series_order=sorted(series_level))
    with_disp = sum(1 for r in records
                    if r.get("Dispersion_Value") is not None or r.get("Q1") is not None)
    # The calibration's own residual, on every row it produced. It was computed
    # inside `bar_reader` and returned under a name nothing read; on a log axis
    # misread as linear it is 332 axis units, which is the loudest single number
    # available and was going straight into the bin.
    if ycal is not None:
        for record in records:
            record.setdefault("Calibration_Max_Residual",
                              float(getattr(ycal, "max_residual", 0.0)))
    for record in records:
        record.setdefault("WPD_Project_File", project or "")
    seen = {r["Cell_Key"] for r in records}
    missing = sorted(_all_cells(series_level, position_level) - seen)
    return PanelOutcome("AUTO_PASS", values=records, raw=raw_path, project=project,
                        overlay=overlay,
                        artifacts=_panel_artifacts(raw_marks=[raw_path],
                                                   project=project, overlay=overlay),
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
    """EVERY declared reference point, in the form WPD stores them.

    This took `[:2]`, so a panel calibrated on four ticks saved a project a
    reviewer could only re-derive from two of them. The residual that made the
    four-tick fit worth doing was invisible in the artifact that exists to let
    somebody check the fit.
    """
    out = []
    for axis, cal, key in (("x", xcal, "Axis_X_Ticks"), ("y", ycal, "Axis_Y_Ticks")):
        if cal is None or BM.blank(panel.get(key)):
            continue
        for value, pixel in BM.parse_ticks(panel.get(key)):
            if axis == "x":
                out.append(dict(px=float(pixel), py=0.0, dx=value, dy=""))
            else:
                out.append(dict(px=0.0, py=float(pixel), dx="", dy=value))
    return out


#: Every grain the grid gate can charge a problem to, and how wide the damage
#: is. A problem at a coarse grain condemns everything under it: a figure whose
#: raster is not the raster that was read poisons every unit measured from it,
#: however clean each unit looked on its own.
QC_SCOPES = ("unit", "units", "values", "figures", "grids", "grid")


def _units_named_by(qc, values_df, units_df, figures_df=None, grids_df=None):
    """Unit_ID -> the set of gate codes charged to it, including inherited ones.

    The gate locates a problem the way a reviewer would open the file - by grain
    and row (`values:14`, `figures:2`) or by name (`unit:U1`, `grid:G_TIME`).
    All of those have to resolve back to a Unit_ID, or a rejected panel keeps
    reporting AUTO_PASS in run_manifest.csv while qc_problems.csv says
    otherwise. Two files disagreeing about the same unit is worse than either
    being wrong.

    This used to read only `unit:`, `units:` and `values:`, and silently dropped
    everything coarser. `IMAGE_HASH_MISMATCH` is charged to `figures:2`, so a
    batch could be told in writing that the raster it read was not the raster
    the manifest names - nine times over - and still write every value into
    `figure_values_accepted.csv`. That is the one invariant this package exists
    to hold, and it was resolving a string prefix to decide it.

    Two rules make the resolution safe rather than merely wider:

    **Inheritance is downward and total.** A `figures:` problem condemns every
    unit of that figure; a `grid:` problem condemns every unit declaring that
    grid. A unit is only as trustworthy as the figure it was measured from.

    **An unrecognised scope condemns everything.** If the gate grows a grain
    this function has not been taught, the batch fails closed and says so rather
    than quietly ignoring it - the failure mode above, exactly, one grain along.
    """
    out = {}
    units_df = units_df if units_df is not None else pd.DataFrame()
    all_units = ([str(u).strip() for u in units_df["Unit_ID"]]
                 if "Unit_ID" in getattr(units_df, "columns", ()) else [])

    def charge(uids, code):
        for uid in uids:
            if uid:
                out.setdefault(uid, set()).add(code)

    def by_row(frame, where, column):
        try:
            idx = int(where.split(":", 1)[1]) - 2
        except ValueError:
            return None
        if frame is None or not (0 <= idx < len(frame)):
            return None
        if column not in getattr(frame, "columns", ()):
            return None
        return str(frame.iloc[idx][column]).strip()

    def units_of(column, value):
        if not value or column not in getattr(units_df, "columns", ()):
            return []
        return [str(u.get("Unit_ID", "")).strip() for _, u in units_df.iterrows()
                if str(u.get(column, "")).strip() == value]

    for _, p in qc.iterrows():
        where, code = str(p.get("where", "")), str(p.get("check", ""))
        scope = where.split(":", 1)[0] if ":" in where else where
        if scope == "unit":
            charge([where.split(":", 1)[1]], code)
        elif scope == "units":
            charge([by_row(units_df, where, "Unit_ID")], code)
        elif scope == "values":
            charge([by_row(values_df, where, "Unit_ID")], code)
        elif scope == "figures":
            charge(units_of("Figure_ID", by_row(figures_df, where, "Figure_ID")), code)
        elif scope == "grids":
            charge(units_of("Grid_ID", by_row(grids_df, where, "Grid_ID")), code)
        elif scope == "grid":
            charge(units_of("Grid_ID", where.split(":", 1)[1]), code)
        else:
            charge(all_units, "UNATTRIBUTED_QC_SCOPE:%s" % (where or "?"))
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
                     image_path, xcal, ycal, raw_dir, declared, project_dir=None,
                     review_dir=None, box=None):
    """A scatter yields one association per series, each with its point file."""
    pid = _s(panel.get("Panel_ID"))
    unit_id = _s(panel.get("Unit_ID"))
    if statistic and statistic != "ASSOCIATION":
        return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                            detail="a scatter cannot become Statistic_Type=%s"
                                   % statistic)
    association = _upper(panel.get("Association_Type"))
    sha = file_sha256(image_path)
    # What the paper says this scatter contains. A count the reader can be
    # measured against, rather than one it declares by counting itself.
    expected_n = _s(unit.get("N_Outcome"))
    # Every series is audited and summarized BEFORE anything is written. The
    # point files used to be written inside this loop, so a panel that a later
    # series sent to MANUAL_POINT_READ left point JSONs on disk that no ledger
    # named and no run row referenced - files a run produced and did not admit
    # to. Nothing here touches the filesystem.
    planned, short, disputed = [], [], []
    for sid, (factor, level) in sorted(series_level.items()):
        mine = [p for p in points if p.get("series") == sid]
        if len(mine) < 3:
            short.append("%s (%d points)" % (sid, len(mine)))
            continue
        audit = MR.point_count_audit(mine, expected_n)
        if audit["Point_Count_Agreement"] in ("FEWER_DETECTED", "MORE_DETECTED"):
            # The association is a function of the point set, so a point set
            # that is not the study's point set produces a number that is not
            # the study's association. Stop before computing it.
            disputed.append(
                "%s: the source declares n=%s, the reader found %d distinct "
                "marks (%d contours, %d claimed by another series' mask)"
                % (sid, audit["Expected_N_From_Source"],
                   audit["Detected_Unique_Point_Count"], len(mine),
                   audit["Series_Mask_Overlap_Count"]))
            continue
        if (audit["Overplotting_Possible"] == "TRUE"
                and audit["Point_Count_Agreement"] == "NO_SOURCE_N"):
            # Overplotting evidence with nothing to check the count against.
            # A blob wider than a marker, or two centroids a pixel apart, means
            # marks may be hiding behind marks - and where the paper gives no n
            # there is no second opinion. Detected == expected is what makes a
            # merged blob tolerable; here there is no expected.
            disputed.append(
                "%s: %d marks read with signs of overplotting (%d distinct of "
                "%d contours) and no declared n to check the count against"
                % (sid, len(mine), audit["Detected_Unique_Point_Count"],
                   len(mine)))
            continue
        summary = dict(MR.summarize_association(mine, association), **audit)
        planned.append((sid, factor, level, mine, summary))

    records, raw_files = [], []
    if not (disputed or (not planned)):
        for sid, factor, level, mine, summary in planned:
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
    if ycal is not None:
        for record in records:
            record.setdefault("Calibration_Max_Residual",
                              float(getattr(ycal, "max_residual", 0.0)))
    if disputed:
        # Not NOT_CONVERTIBLE: the marks are readable, they just do not add up
        # to a point set anybody can vouch for. That is a counting job for a
        # person. No point file was written, so there is nothing on disk the
        # ledger does not name.
        return PanelOutcome(
            "MANUAL_POINT_READ", declared=declared, read=0,
            detail="the detected points cannot be reconciled with the source, "
                   "so no association was computed - " + "; ".join(disputed),
            missing=sorted(_all_cells(series_level, {})))
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
    for record in records:
        record.setdefault("WPD_Project_File", project or "")
    # A scatter went into the review queue with `Overlay_File=""`. The review
    # protocol says to open the overlay for every queued panel and approve only
    # if each mark sits where a reader would put it - so an empty overlay column
    # is an approval with nothing to approve against. The reader has had
    # `point_px_x`/`point_px_y` all along; nobody passed it a review directory.
    overlay = None
    if review_dir and box is not None:
        overlay = OVERLAY.draw_panel_overlay(
            os.path.join(review_dir, "%s_overlay.png" % pid), image_path, box,
            [p for _s_, _f_, _l_, mine, _sum_ in planned for p in mine],
            title="%s  %s  SCATTER" % (pid, unit_id),
            subtitle="%d points read in %d series - approve only if every "
                     "cross sits on a printed marker and none is missed"
                     % (len(records) and sum(len(m) for _a, _b, _c, m, _d in planned),
                        len(planned)),
            series_order=sorted(series_level),
            # Thirty labelled crosses cover the cloud they exist to show.
            label_marks=False)
    return PanelOutcome("AUTO_PASS", values=records, raw=";".join(raw_files),
                        project=project, overlay=overlay,
                        declared=declared, read=len(records),
                        # One entry per point file. `raw` stays a ";"-joined
                        # string for the run manifest column, but nothing
                        # hashes that string as a path any more.
                        artifacts=_panel_artifacts(point_data=raw_files,
                                                   project=project,
                                                   overlay=overlay),
                        with_dispersion=len(records))


# --------------------------------------------------------------------------
# the batch
# --------------------------------------------------------------------------

#: Everything a run owns in its output directory. A run clears all of it before
#: doing anything else, so no output can outlive the run that produced it.
CANONICAL_OUTPUTS = (
    # `figure_values_accepted.csv` is NOT written by this module any more - it is
    # `finalize_batch.py`'s output. It stays on this list because a new run must
    # still delete the last finalization: values approved against a previous run
    # are not approved against this one, and a stale accepted file sitting beside
    # fresh raw values is the most poolable thing in the directory.
    "figure_values_accepted.csv", "finalize_stamp.json", "review_queue.csv",
    "figure_values_machine_qc.csv", "figure_values_raw.csv", "figure_values.csv",
    "run_manifest.csv", "manual_queue.csv", "qc_problems.csv",
    "manifest_problems.csv", "run_stamp.json", "figure_manifest.csv",
    "manual_queue_cells.csv", "panel_artifacts.csv",
    "source_panel_coverage.csv",
)
CANONICAL_DIRS = ("raw", "projects", "review")
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
COMMIT_MARKER = "figure_values_machine_qc.csv"

#: Whether the run stands behind its own output.
#:
#: DEMO_ONLY exists because a worked example needs an identity and must not be
#: allowed to lend that identity to real numbers. The pilot shipped a fictional
#: reviewer with a `Note` that said "EXAMPLE - replace before treating any
#: output as data", and a note is a request, not a gate: the only thing actually
#: keeping the demo harmless was that the dispersion definition happened to be
#: unresolved, so nothing was accepted. Resolve it and the same fictional
#: registry row would have signed off poolable values. A property that holds by
#: coincidence is not a property.
RUN_MODES = ("ATTESTED", "DEMO_ONLY")


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


def withdraw_commit(output_dir, run_date, detail, run_mode="ATTESTED"):
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
                run_date, run_mode=run_mode, detail=detail)


#: Every verdict a run directory can carry. RAN is the only one under which
#: `figure_values_accepted.csv` may exist.
RUN_STATUSES = ("RAN", "MANIFEST_REJECTED", "INPUT_LOAD_FAILED",
                "PROMOTE_FAILED", "DEMO_OUTPUT_REFUSED", "INTERNAL_ERROR")


def write_stamp(path, status, run_date, cfg_hash="", manifest_hashes=None,
                panels=0, read=0, accepted=0, machine_qc=0, qc_problems=0,
                problems=0, detail="", run_mode="ATTESTED",
                output_sha256=None, reviewer_registry_sha256="",
                manifest_dir=""):
    """The run's verdict, written on EVERY outcome including a rejection.

    A rejected run used to write no stamp at all, which left the previous run's
    stamp in place claiming `Values_Accepted=8`. A stamp that is absent when
    things go wrong is worse than no stamp at all - it is only ever there to
    reassure.
    """
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "figure-digitization-triage/run-stamp/7",
            "Status": status, "Run_Mode": run_mode, "Run_Date": run_date,
            "Reader_Version": MR.READER_VERSION,
            "Pipeline_Version": PIPELINE_VERSION,
            "Pipeline_Code_SHA256": pipeline_code_sha256(),
            "Environment": environment_record(),
            "Config_SHA256": cfg_hash,
            "Manifest_SHA256": manifest_hashes or {},
            "Panels": panels, "Values_Read": read,
            "Values_Machine_QC_Passed": machine_qc, "Values_Accepted": accepted,
            "QC_Problems": qc_problems, "Manifest_Problems": problems,
            "Output_SHA256": output_sha256 or {},
            "Reviewer_Registry_SHA256": reviewer_registry_sha256,
            # Where the manifests came from, so the finalizer does not have to
            # be told. The README's own three commands put them beside the run
            # rather than inside it, and the finalizer defaulted to
            # OUT/manifests - so following the documentation produced a run
            # whose registry the finalizer could not find.
            "Manifest_Dir": manifest_dir,
            "Detail": detail,
        }, fh, indent=1, sort_keys=True)


def run_batch(manifest_dir, output_dir, file_root=".", run_date="",
              check_files=True, fault_after=None, run_mode=None):
    """Validate, read, convert, gate, and report. Returns a summary dict.

    The run mode is DERIVED from `reviewer_registry.csv`: if any reviewer the
    source inventory names is `Reviewer_Record_Type=DEMO_IDENTITY`, the run is
    DEMO_ONLY. It executes in full - the point of a demo is to show what the
    pipeline does - but if it reaches the end holding values the grid gate
    accepted, it writes none of them and returns DEMO_OUTPUT_REFUSED. A
    demonstration identity may produce a queue, a coverage ledger and a list of
    QC failures; it may not produce a row anybody could pool.

    It was an argument before, and that was the bug: an argument is the
    caller's promise about the manifests, and replaying the demonstration's own
    manifests through the plain CLI dropped the promise on the floor -
    Status=RAN, Run_Mode=ATTESTED, same fictional reviewer. Pass
    `run_mode="DEMO_ONLY"` to demote a real registry; passing "ATTESTED" over a
    demo registry is RUN_MODE_REVIEWER_MISMATCH, not a promotion.

    `fault_after` is a test hook that aborts promotion partway through; it has
    no effect on a normal run.
    """
    if run_mode is not None and run_mode not in RUN_MODES:
        raise ValueError("run_mode must be None (derive from the registry) or "
                         "one of %s, got %r" % (", ".join(RUN_MODES), run_mode))
    requested_run_mode = run_mode
    # Until the manifests load there is nothing to derive from, so an early
    # failure stamps what the caller asked for rather than inventing a verdict.
    run_mode = requested_run_mode or "ATTESTED"
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
                    "INPUT_LOAD_FAILED", run_date, run_mode=run_mode,
                    manifest_dir=os.path.realpath(manifest_dir),
                    detail="%s: %s" % (type(exc).__name__, exc))
        raise
    manifest_hashes = {k: frame_sha256(v) for k, v in sorted(m.items())}

    problems = BM.validate_batch_manifests(
        m["panels"], m["series"], m["positions"], m["configs"],
        units=m["units"], source_documents=m["source_documents"],
        source_figures=m["source_figures"],
        source_panels=m["source_panels"], reviewers=m["reviewers"],
        requested_run_mode=requested_run_mode,
        file_root=file_root,
        check_files=check_files)
    # Derived even when the batch is rejected, so the stamp on a failed run
    # still says which kind of run it would have been.
    derived = BM.derive_run_mode(m["reviewers"], m["source_documents"],
                                 m["source_figures"])
    run_mode = ("DEMO_ONLY" if "DEMO_ONLY" in (derived, requested_run_mode)
                else "ATTESTED")
    if len(problems):
        problems.to_csv(os.path.join(output_dir, "manifest_problems.csv"),
                        index=False)
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "MANIFEST_REJECTED", run_date, run_mode=run_mode,
                    manifest_dir=os.path.realpath(manifest_dir),
                    manifest_hashes=manifest_hashes, problems=len(problems))
        return dict(status="MANIFEST_REJECTED", problems=len(problems),
                    values=0, accepted=0, run_mode=run_mode,
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
    review_dir = os.path.join(output_dir, "review")
    os.makedirs(review_dir, exist_ok=True)

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

    values, run_rows = [], []
    # A panel gets exactly one queue entry, keyed so a later pass revises it
    # instead of contradicting it. Inventory-only panels have no Panel_ID to
    # key on and no state that can change, so they are a plain list appended
    # after, which also keeps the file's row order what it was.
    queue_by_panel, unlinked_queue_rows = {}, []
    # Was `projects_by_figure`, filled with `setdefault` - so a figure with six
    # auto panels recorded the first panel's project and the other five vanished
    # from the figure manifest. The project the gate checked was then a
    # different panel's marks and a different panel's calibration.
    projects_by_panel = {}
    overlays_by_panel = {}
    artifacts_by_panel = {}
    for _, panel in m["panels"].iterrows():
        pid = _s(panel.get("Panel_ID"))
        unit = units_by_id.get(_s(panel.get("Unit_ID")))
        options = options_by_config.get(_s(panel.get("Config_ID")), {})
        try:
            outcome = run_panel(panel, series_by_panel.get(pid, []),
                                positions_by_panel.get(pid, []), options, unit,
                                raw_dir, file_root=file_root,
                                project_dir=project_dir, review_dir=review_dir)
        except InternalReaderError as exc:
            # The whole batch stops. A defect in a reader is not confined to the
            # panel that happened to trip it, and 115 more publications read by
            # the same broken code is a worse outcome than a loud halt.
            clear_outputs(output_dir)
            write_stamp(os.path.join(output_dir, "run_stamp.json"),
                        "INTERNAL_ERROR", run_date, run_mode=run_mode,
                        manifest_hashes=manifest_hashes,
                        detail="%s" % exc)
            raise
        overlays_by_panel[pid] = outcome.overlay or ""
        if outcome.project:
            projects_by_panel[pid] = outcome.project
        # Hashed the moment they are written, before anything else touches the
        # directory - so what the manifest records is what the run produced.
        #
        # Recorded RELATIVE to the output directory. An absolute path breaks
        # when the run directory is moved or copied; a bare relative one breaks
        # when the finalizer is launched from a different working directory,
        # which is the normal case for a scheduler or an agent. Either way the
        # finalizer reports RUN_ARTIFACT_MODIFIED for a file that is sitting
        # right there - safe, but a false refusal nobody can act on.
        artifacts_by_panel[pid] = [
            (kind, _run_relative(path, output_dir), file_sha256_or_blank(path))
            for kind, path in outcome.artifacts]
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
            # Keyed by panel, not appended. A panel that read most of its cells
            # returns AUTO_PASS with a missing list, so it entered the queue
            # here as AUTO_PASS; the grid gate then found the same missing cells
            # and appended a SECOND row saying QC_FAILED. One panel, two rows,
            # two different terminal states, and `manual_queue_cells.csv`
            # attributing the missing cells to the state the run manifest no
            # longer claimed.
            queue_by_panel[pid] = {
                "Panel_ID": pid, "Source_Panel_ID": _s(panel.get("Source_Panel_ID")),
                "Figure_ID": _s(panel.get("Figure_ID")),
                "Unit_ID": _s(panel.get("Unit_ID")),
                "Mark_Type": _upper(panel.get("Mark_Type")),
                "Run_State": outcome.state,
                "Missing_Cell_Count": len(outcome.missing),
                "_cells": list(outcome.missing),
                "Image_Path": image_path,
                "Panel_Box": ",".join(_s(panel.get(c)) for c in
                                      ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")),
                "Detail": outcome.detail,
            }

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
        unlinked_queue_rows.append({
            "Panel_ID": "", "Source_Panel_ID": spid, "Figure_ID": "",
            "Unit_ID": "", "Mark_Type": "",
            "Run_State": ("NO_READER_AVAILABLE" if disposition ==
                          "NO_READER_AVAILABLE" else "MANUAL_POINT_READ"),
            "Missing_Cell_Count": "", "Image_Path": _s(sf.get("Source_Image")),
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
    if projects_by_panel and "WPD_Project_File" in figures.columns:
        # A figure gets EVERY project its panels produced, in panel order, so
        # the column can still answer "is this figure re-openable" without
        # claiming one panel's tar speaks for six.
        by_figure = {}
        for _, p in m["panels"].iterrows():
            project = projects_by_panel.get(_s(p.get("Panel_ID")))
            if project:
                by_figure.setdefault(_s(p.get("Figure_ID")), []).append(project)
        figures["WPD_Project_File"] = [
            (";".join(by_figure.get(_s(r.get("Figure_ID")), []))
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
        blamed = _units_named_by(qc, values_df, m["units"],
                                 figures_df=m["figures"], grids_df=m["grids"])
        for row in run_rows:  # noqa: B007
            uid = row["Unit_ID"]
            if row["Run_State"] != "AUTO_PASS" or not uid or uid not in blamed:
                continue
            row["Run_State"] = "QC_FAILED"
            row["Detail"] = ("the grid gate rejected this unit's values: %s"
                             % ", ".join(sorted(blamed[uid])))
            # Update the panel's existing queue entry rather than adding a
            # second one, and keep the missing cells it already carried. The
            # old code appended, with the removed `Missing_Cells` key and no
            # `_cells`, so a partially-read panel appeared twice - once
            # AUTO_PASS with its cells, once QC_FAILED with an empty count -
            # and `manual_queue_cells.csv` filed those cells under a state the
            # run manifest had already withdrawn.
            existing = queue_by_panel.get(row["Panel_ID"])
            if existing is None:
                existing = queue_by_panel[row["Panel_ID"]] = {
                    "Panel_ID": row["Panel_ID"],
                    "Source_Panel_ID": row["Source_Panel_ID"],
                    "Figure_ID": row["Figure_ID"],
                    "Unit_ID": uid, "Mark_Type": row["Mark_Type"],
                    "Missing_Cell_Count": 0, "_cells": [],
                    "Image_Path": row["Image_Path"], "Panel_Box": "",
                }
            existing["Run_State"] = "QC_FAILED"
            existing["Detail"] = row["Detail"]

    run_df = pd.DataFrame(run_rows, columns=RUN_MANIFEST_COLUMNS)
    # Assembled once, AFTER every state revision, so the queue and the run
    # manifest cannot tell a reviewer two different stories about one panel.
    queue_rows = list(queue_by_panel.values()) + unlinked_queue_rows
    queue_cell_rows = []
    for row in queue_rows:
        for cell in row.pop("_cells", []):
            queue_cell_rows.append({
                "Panel_ID": row["Panel_ID"],
                "Source_Panel_ID": row["Source_Panel_ID"],
                "Figure_ID": row["Figure_ID"], "Unit_ID": row["Unit_ID"],
                "Run_State": row["Run_State"], "Cell_Key": cell})
    queue_df = pd.DataFrame(queue_rows, columns=MANUAL_QUEUE_COLUMNS)
    queue_cells_df = pd.DataFrame(queue_cell_rows,
                                  columns=MANUAL_QUEUE_CELL_COLUMNS)

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
    # Same inheritance as the run-manifest pass above, and it has to be the same
    # call: this is the one that writes Pooling_Eligible onto each row, so a
    # narrower view here would put a value in the accepted file that the run
    # manifest has already marked QC_FAILED.
    blamed = (_units_named_by(qc, values_df, m["units"],
                              figures_df=m["figures"], grids_df=m["grids"])
              if len(qc) else {})
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
            statuses.append("MACHINE_QC_PASSED")
        codes.append(";".join(unit_codes))
        # Nothing this module writes is poolable. MACHINE_QC_PASSED means the
        # machine could find nothing wrong with it, which is a different claim
        # from a person having looked at where the reader put its marks.
        eligible.append("FALSE")
    raw_df = values_df.copy()
    raw_df["Run_Panel_ID"] = run_panel_ids
    raw_df["Source_Panel_ID"] = source_panel_ids
    raw_df["Value_Status"] = statuses
    raw_df["QC_Codes"] = codes
    raw_df["Pooling_Eligible"] = eligible
    machine_qc_df = raw_df[raw_df["Value_Status"] == "MACHINE_QC_PASSED"].copy()

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

    # The demo gate, placed before a single output file is written. Refusing
    # after promotion would mean deleting a file somebody may already have read;
    # refusing here means the only thing this run leaves behind is the stamp
    # saying why. `clear_outputs` has already run, so there is nothing stale to
    # be mistaken for a result.
    # The review queue: one row per panel a person now has to look at, with the
    # picture, the project and the run fingerprint the approval will be bound to.
    review_rows = []
    for row in run_rows:
        if row["Run_State"] != "AUTO_PASS":
            continue
        overlay_file = overlays_by_panel.get(row["Panel_ID"], "")
        # What a reviewer will actually be looking at, declared rather than
        # assumed. A scatter reached this queue with `Overlay_File=""` and the
        # protocol still said "open the overlay", so the instruction pointed at
        # nothing. A panel with neither a picture nor a project would get a
        # blank mode here - it cannot, because a digitized value with no saved
        # project is already MISSING_PROVENANCE at the gate, but the finalizer
        # refuses a blank mode anyway rather than trusting that ordering.
        mode = ("OVERLAY" if overlay_file
                else ("WPD_ONLY" if row["WPD_Project_File"] else ""))
        review_rows.append({
            "Panel_ID": row["Panel_ID"], "Source_Panel_ID": row["Source_Panel_ID"],
            "Figure_ID": row["Figure_ID"], "Unit_ID": row["Unit_ID"],
            "Mark_Type": row["Mark_Type"],
            "Cells_Read": row["Cells_Read"], "Cells_Declared": row["Cells_Declared"],
            "Review_Mode": mode,
            "Overlay_File": overlay_file,
            "WPD_Project_File": row["WPD_Project_File"],
            "Raw_Data_File": row["Raw_Data_File"],
            "Review_Subject_SHA256": review_subject_sha256(
                row, [v for v in machine_qc_df.to_dict("records")
                      if _s(v.get("Run_Panel_ID")) == row["Panel_ID"]],
                manifest_hashes, environment_record(),
                artifacts=artifacts_by_panel.get(row["Panel_ID"], [])),
            "Decision": "", "Reviewer_ID": "", "Reviewed_At": "", "Note": "",
        })
    review_df = pd.DataFrame(review_rows, columns=REVIEW_QUEUE_COLUMNS)
    # One row per artifact, for every panel that produced one - not only the
    # ones awaiting review. A panel that failed still has a picture and a point
    # file somebody may look at, and the ledger is the record of what this run
    # wrote, not of what it wants approved.
    artifact_df = pd.DataFrame(
        [{"Panel_ID": pid, "Artifact_Type": kind, "Artifact_Path": path,
          "SHA256": digest}
         for pid in sorted(artifacts_by_panel)
         for kind, path, digest in artifacts_by_panel[pid]],
        columns=PANEL_ARTIFACT_COLUMNS)
    # An empty review directory beside twelve panels awaiting review would read
    # as "nothing to look at". Say which pictures could not be drawn.
    overlay_failures = OVERLAY.failures()
    stamp_detail = ("" if not overlay_failures else
                    "%d review overlay(s) could not be drawn: %s"
                    % (len(overlay_failures), "; ".join(overlay_failures[:5])))

    if run_mode == "DEMO_ONLY" and len(machine_qc_df):
        shutil.rmtree(work_dir, ignore_errors=True)
        # raw/ and projects/ are written at their final paths, because the
        # value rows have to name them. They are digitized data too - a point
        # cloud is the reading, not a note about it - so a refusal that left
        # them behind would refuse the summary and keep the measurements.
        for leftover in ("raw", "projects", "review"):
            shutil.rmtree(os.path.join(output_dir, leftover), ignore_errors=True)
        detail = ("%d values passed the gate under a DEMO_ONLY reviewer "
                  "registry. Register the person who actually inspected the "
                  "figures and re-run; a demonstration identity cannot stand "
                  "behind a poolable value" % len(machine_qc_df))
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "DEMO_OUTPUT_REFUSED", run_date, run_mode=run_mode,
                    manifest_dir=os.path.realpath(manifest_dir),
                    cfg_hash=cfg_hash, manifest_hashes=manifest_hashes,
                    panels=len(run_df), read=len(raw_df), accepted=0,
                    qc_problems=int(len(qc)), detail=detail)
        return dict(status="DEMO_OUTPUT_REFUSED", panels=len(run_df),
                    values=0, accepted=0, would_accept=len(machine_qc_df),
                    run_mode=run_mode, detail=detail)

    raw_df.to_csv(os.path.join(work_dir, "figure_values_raw.csv"), index=False)
    machine_qc_df.to_csv(os.path.join(work_dir, "figure_values_machine_qc.csv"),
                         index=False)
    review_df.to_csv(os.path.join(work_dir, "review_queue.csv"), index=False)
    artifact_df.to_csv(os.path.join(work_dir, "panel_artifacts.csv"), index=False)
    run_df.to_csv(os.path.join(work_dir, "run_manifest.csv"), index=False)
    queue_df.to_csv(os.path.join(work_dir, "manual_queue.csv"), index=False)
    queue_cells_df.to_csv(os.path.join(work_dir, "manual_queue_cells.csv"),
                          index=False)
    qc.to_csv(os.path.join(work_dir, "qc_problems.csv"), index=False)
    coverage_df.to_csv(os.path.join(work_dir, "source_panel_coverage.csv"), index=False)
    write_stamp(os.path.join(work_dir, "run_stamp.json"), "RAN", run_date,
                run_mode=run_mode, detail=stamp_detail,
                manifest_dir=os.path.realpath(manifest_dir),
                cfg_hash=cfg_hash, manifest_hashes=manifest_hashes,
                panels=len(run_df), read=len(raw_df), accepted=0,
                machine_qc=len(machine_qc_df),
                qc_problems=int(len(qc)),
                # What the finalizer must find unchanged. Everything it reads
                # to decide whether a value is poolable is hashed here, so a
                # file edited between the run and the approval is a refusal
                # rather than an input.
                output_sha256={
                    name: sha256_of_text(
                        open(os.path.join(work_dir, name), encoding="utf-8").read())
                    for name in ("figure_values_machine_qc.csv",
                                 "review_queue.csv", "figure_values_raw.csv",
                                 "run_manifest.csv", "panel_artifacts.csv")},
                reviewer_registry_sha256=manifest_hashes.get("reviewers", ""))
    try:
        promote(work_dir, output_dir, fault_after=fault_after)
    except Exception as exc:
        withdraw_commit(output_dir, run_date, "%s: %s" % (type(exc).__name__, exc),
                        run_mode=run_mode)
        raise

    counts = run_df["Run_State"].value_counts().to_dict() if len(run_df) else {}
    return dict(status="RAN", panels=len(run_df), values=len(raw_df),
                accepted=0, machine_qc=len(machine_qc_df), qc_problems=int(len(qc)),
                states=counts, manual_queue=len(queue_df),
                run_mode=run_mode, config_sha256=cfg_hash)


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
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--demo-only", action="store_true",
                      help="demote: treat a real registry as illustrative and "
                           "refuse to write any value the gate accepts")
    mode.add_argument("--attested", action="store_true",
                      help="assert the registry is real; fails with "
                           "RUN_MODE_REVIEWER_MISMATCH if it is not")
    args = ap.parse_args(argv)
    requested = ("DEMO_ONLY" if args.demo_only else
                 "ATTESTED" if args.attested else None)
    try:
        summary = run_batch(args.manifest_dir, args.output_dir,
                            file_root=args.file_root, run_date=args.date,
                            check_files=not args.no_file_check,
                            run_mode=requested)
    except InternalReaderError as exc:
        import traceback
        traceback.print_exc()
        print("INTERNAL_ERROR: %s" % exc)
        print("this is a defect in the package, not a difficult figure - the "
              "batch stopped and run_stamp.json records Status=INTERNAL_ERROR")
        return 5
    except ManifestLoadError as exc:
        print("inputs could not be loaded: %s" % exc)
        print("the output directory was cleared and run_stamp.json records "
              "Status=INPUT_LOAD_FAILED")
        return 3
    if summary["status"] == "DEMO_OUTPUT_REFUSED":
        print("DEMO_OUTPUT_REFUSED: %s" % summary["detail"])
        return 4
    if summary["status"] == "MANIFEST_REJECTED":
        print("manifests rejected: %d problems" % summary["problems"])
        for code in summary["detail"]:
            print("  " + code)
        print("see manifest_problems.csv")
        return 2
    print("panels %d | values read %d | MACHINE_QC_PASSED %d | qc problems %d "
          "| manual queue %d"
          % (summary["panels"], summary["values"], summary["machine_qc"],
             summary["qc_problems"], summary["manual_queue"]))
    for state, n in sorted(summary["states"].items()):
        print("  %-28s %d" % (state, n))
    print("review the panels in review_queue.csv; finalize_batch.py writes "
          "figure_values_accepted.csv, and nothing else does")
    # A QC problem is a RESULT, not a failure of the run. Publication 397 is in
    # the package precisely because its dispersion definition is unresolved, so
    # a run that reproduces those 108 problems has done its job exactly. Exit 1
    # made that success indistinguishable from a crash, and CI called it red.
    return 0 if summary["status"] == "RAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
