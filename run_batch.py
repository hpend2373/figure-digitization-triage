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

                       identity_resolution.csv is OPTIONAL. It holds the series
                       identities a person supplied for bars whose fill the
                       reader could not sample - publication 127 prints two,
                       fifteen pixels tall - and most batches need none. Absent
                       means "nobody named anything", and such a cell is queued
                       rather than guessed. It is hashed into the stamp either
                       way, so adding one later changes the fingerprint every
                       approval is bound to.

                       axis_manifest.csv is OPTIONAL. One row per printed
                       SCALE, for the panels that print more than one y axis
                       over a single drawing - a panel row can hold one ladder
                       and a figure with a left scale at 10-35 and a right one
                       at 20-90 has two. A series then names the axis it was
                       read on. Absent means the panel's own Axis_Y_Ticks is
                       the only scale, which is true of every batch in the
                       corpus but the twin-axis ones.
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
import csv
import hashlib
import json
import os
import re
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
import line_style_mono as LINE_STYLE                               # noqa: E402
import mark_readers as MR                                          # noqa: E402
import mono_bar_geometry as MONO_GEOMETRY                          # noqa: E402
import provenance as PROV                                          # noqa: E402
import review_overlay as OVERLAY                                   # noqa: E402

PIPELINE_VERSION = "9.24"
#: Every file whose contents can change a number this pipeline writes down.
#: Hashed together into `Pipeline_Code_SHA256` and stamped on the run, so a
#: value that moved between two batches can be attributed to the code that
#: produced it instead of argued about.
#:
#: A file that measures and is NOT listed here is the failure mode this stamp
#: exists to prevent: `mono_bar_geometry.py` holds the whole monochrome bar
#: measurement - stroke, footprint, extent, cap, texture - and for three commits
#: it was absent, so editing the function that decides where a bar top is left
#: the stamp identical and the batch looked reproducible.
#: `test_run_batch` asserts every module `run_batch` reaches is in this tuple.
PIPELINE_CODE_FILES = (
    "run_batch.py", "batch_manifests.py", "grid_engine.py", "kernel.py",
    "mark_readers.py", "mono_bar_geometry.py", "bar_reader.py",
    # THE TWIN-AXIS SCATTER PATH. `axis_grain` is reached through
    # `batch_manifests`, which validates an axis manifest against it;
    # `marker_routing` and `scatter_points` are reached from the SCATTER branch
    # of `run_panel`. All three measure, so all three are in the stamp: a run
    # whose marker routing changed and whose stamp did not would be two
    # different readings under one hash.
    "axis_grain.py", "marker_routing.py", "scatter_points.py",
    "make_wpd_project.py", "review_overlay.py", "finalize_batch.py",
    "compile_plan.py",
    # BOTH ADDED IN v7.54, BOTH PRODUCTION SINCE v7.44 AND v7.53. The reader
    # `reader_functions()` dispatches LINE_MONO_STYLE to lives in
    # `line_style_mono`, and its `_ink_at` decides the MEAN of 174 of the 180
    # cells publication 397's line panels produce; `provenance` decides the
    # method and review tier every one of them carries. Neither was hashed, so
    # `_ink_at` could be rewritten between two batches and the stamp would say
    # the two runs were produced by identical code.
    #
    # The reachability guard in `test_run_batch` was supposed to make this
    # impossible and did not, because it walked the MODULE OBJECTS bound as
    # attributes of each module: `line_style_mono` is imported inside
    # `reader_functions()`, so what run_batch binds is the function, and the
    # module never appears in `vars(run_batch)`. The guard now follows the
    # imports each file DECLARES, which is a property of the source rather than
    # of where an import statement happens to sit. Since v9.15 this file also
    # imports the module at the top, for the panel-note channel the loop clears
    # and folds - which does not make the guard's design any less necessary: the
    # reader itself is still reached through `reader_functions()`.
    "line_style_mono.py", "provenance.py",
)


#: Mark_Type -> the function that actually receives the reader keywords, so a
#: test can introspect it. Declaring that an option "applies to" a mark type is
#: a promise about a function signature, and a promise nobody checks is how
#: `n_slots` came to be accepted for BAR_MONO, pass validation, and then raise
#: TypeError mid-run - which surfaced as PANEL_GEOMETRY_UNRESOLVED, a message
#: about the figure for a defect in this table.
def reader_functions():
    from bar_reader import read_bar_colour_panel
    from line_style_mono import read_monochrome_line_panel
    return {
        "BAR_COLOR": read_bar_colour_panel,
        # The two-pass geometry reader. It measures a panel and names no
        # series; `measure_bar_mono_figures` calls it before the panel loop and
        # the figure resolves the identities. `read_monochrome_bar_panel` is
        # still here and still correct for what it does - one panel, one
        # absolute fill density - which is why it is no longer what BAR_MONO
        # dispatches to.
        "BAR_MONO": MR.read_monochrome_bar_geometry,
        "LINE_COLOR": MR.read_line_marker_panel,
        "LINE_MONO": MR.read_monochrome_marker_panel,
        "LINE_MONO_STYLE": read_monochrome_line_panel,
        "SCATTER": MR.read_scatter_panel,
        "BOX_VIOLIN": MR.read_box_violin_panel,
    }


#: Mark_Type -> the reader that will REPLACE the entry in `reader_functions()`,
#: declared before it is wired so the option contract can be checked now rather
#: than discovered at the switchover.
#:
#: `read_monochrome_bar_geometry` measures a BAR_MONO panel and leaves the
#: identity open, which is a change to the CALLER and not to a reader - so it
#: cannot simply be dropped into the table above. But the manifest already
#: declares five options for BAR_MONO, and a successor that does not take all
#: five is either a TypeError on the first batch after the switch or, worse, a
#: setting a person wrote in a manifest, validated, and silently ignored. The
#: same introspection that guards `reader_functions()` guards this.
#: Empty, and kept. It held `BAR_MONO` while the geometry reader was written
#: and could not yet be dispatched to, so the option contract was checked
#: against it several commits before the switchover instead of being discovered
#: at it. The next reader that has to be built before it can be wired goes
#: here, and the introspection that guards `reader_functions()` guards it too.
SUCCESSOR_READERS = {}


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

#: Manifests a batch may legitimately not have. `identity_resolution.csv` is
#: empty for every publication whose fills the reader could measure, and making
#: it mandatory would put an empty file in 116 manifest directories - which is
#: how a required file becomes a file nobody reads. Absent means "no cell was
#: named by a person", which is a different claim from "this batch has nothing
#: to say about identities", and the run manifest records which panels are still
#: waiting for one either way.
OPTIONAL_MANIFEST_FILES = {
    "resolutions": "identity_resolution.csv",
    # A SECOND Y SCALE OVER ONE PANEL, for the figures that print one. A panel
    # with a single y axis says so on its own row exactly as before, so this
    # file is absent for every batch in the corpus but the twin-axis ones - and
    # a required file that is empty in 116 directories is a file nobody reads.
    "axes": "axis_manifest.csv",
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
    # And what the VALUES ask on top of it. A cell whose series was reasoned to
    # rather than measured needs `Inference_Checked` from whoever signs for the
    # panel, whatever mode the panel is reviewed in - see
    # `inference_confirmations`. Informative here and re-derived by the
    # finalizer: a queue that could lower its own requirement by writing 0 would
    # be a requirement in name only.
    "Inference_Cells",
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

#: And in `Inference_Confirmed`, one row per reconstructed cell. REJECTED is
#: here so that seeing a bad reconstruction costs the CELL and not the panel: a
#: reviewer who can tell that one interpolation is wrong should not have to throw
#: away the nineteen values beside it, and a blank row - which is neither answer -
#: holds the panel instead, because nobody said whether they looked.
INFERENCE_DECISIONS = ("CONFIRMED", "REJECTED")

#: What a queued panel offers a reviewer, and which `panel_artifacts.csv`
#: Artifact_Type must therefore be present for it. `OVERLAY` is the normal case. `WPD_ONLY` exists because
#: `draw_panel_overlay` never raises - a picture that cannot be painted must not
#: fail a panel that produced values - so a panel can legitimately reach the
#: queue with a project and no overlay. What it may NOT do is reach the queue
#: claiming a review nobody can perform.
#: Mode -> every `panel_artifacts.csv` Artifact_Type it requires. A TUPLE, not
#: one type: a review that needs three artifacts to be performable - the
#: numbers, the pictures and the index that ties them together - cannot declare
#: one of them and hope. The finalizer refuses an approval for a mode whose
#: artifacts are not all in the ledger.
REVIEW_MODES = {
    "OVERLAY": ("OVERLAY",), "WPD_ONLY": ("WPD_PROJECT",),
    # AND NO `OVERLAY_INFERRED` / `OVERLAY_INFERRED_CELLS`. v7.62 and v7.63 made
    # those two modes, and v7.65 folded them back in here - see
    # `inference_confirmations` for why. A mode is what a reviewer OPENS, and
    # both of them opened the same overlay as `OVERLAY`; what they actually
    # carried was an extra question, which belongs to the VALUES and reaches
    # every mode once it is derived from them. As two modes it reached one:
    # teaching BAR_MONO to answer the provenance questions put R2 cells on panels
    # queued `BAR_MONO_GEOMETRY`, where no mode name could ask about them.
    # Four, and the row pictures the index links to. See
    # `GEOMETRY_ARTIFACT_TYPES`.
    #
    # AND THE OVERLAY, which was missing until v7.96. Both geometry modes ask a
    # person for `Marks_Checked` - "the labels sit on the marks a reader would
    # give them" - and the only picture that shows a label on a mark is the
    # panel overlay. A row crop shows one bar with no label; the calibration
    # panel shows the axis. So the mode demanded a claim and required no
    # artifact a person could make it from: a run holding the five geometry
    # files and no overlay passed the requirement, and `PILOT.md` sent its
    # reviewer to a picture the mode did not guarantee was there.
    "BAR_MONO_GEOMETRY": ("OVERLAY", "MONO_BAR_GEOMETRY", "GEOMETRY_REVIEW_INDEX",
                          "CALIBRATION_PANEL", "CALIBRATION_PANEL_META",
                          "GEOMETRY_ROW_CROP"),
    # The same review, plus the rows a person signed. A separate mode rather
    # than a sixth entry above, because the requirement is per PANEL: most
    # BAR_MONO panels have no human-named cell, and a mode that demanded an
    # identity file from all of them would make the file mandatory - which is
    # how `Identity_Checked` becomes a column everybody types CONFIRMED into.
    "BAR_MONO_GEOMETRY_RESOLVED": ("OVERLAY", "MONO_BAR_GEOMETRY",
                                   "GEOMETRY_REVIEW_INDEX",
                                   "CALIBRATION_PANEL", "CALIBRATION_PANEL_META",
                                   "GEOMETRY_ROW_CROP", "IDENTITY_RESOLUTION"),
}

#: Mode -> what the reviewer must SAY they checked, as columns of
#: `value_review.csv`. `Decision=APPROVED` on its own is a signature on a
#: filename: it does not distinguish a person who opened the overlay and
#: compared every mark from a person who typed APPROVED down a column. Each
#: named check is a separate assertion, and the finalizer requires every one
#: its mode declares.
#:
#: Both modes here offer a picture of the marks and nothing else, so both ask
#: the one question that picture can answer. A mode that also puts the AXIS in
#: front of the reviewer will ask about the axis, and will do it when there is
#: such a mode - a confirmation field nobody can act on is worse than none.
REVIEW_CONFIRMATIONS = {
    "OVERLAY": ("Marks_Checked",), "WPD_ONLY": ("Marks_Checked",),
    # This mode puts the AXIS in front of the reviewer, so it asks about the
    # axis. A printed 30 typed as 3 makes every bar in the panel ten times too
    # small together and no arithmetic catches it; the panel picture is the
    # only place it shows, and a reviewer who did not look at it has not
    # checked the one thing this mode exists for.
    "BAR_MONO_GEOMETRY": ("Marks_Checked", "Axis_Labels_Checked",
                          "Calibration_Checked"),
    # And, for a panel where a person named a series the reader could not, that
    # the naming was checked. It is the one claim in this whole pipeline with no
    # measurement behind it: the value is the reader's, the axis is the
    # reader's, and WHICH SERIES the bar belongs to is somebody's reading of a
    # legend. An approval that does not say so out loud is an approval of a
    # number whose row heading came from nowhere in particular.
    "BAR_MONO_GEOMETRY_RESOLVED": ("Marks_Checked", "Axis_Labels_Checked",
                                   "Calibration_Checked", "Identity_Checked"),
}

#: What a reviewer writes in a confirmation column. Blank is not CONFIRMED.
REVIEW_CONFIRMED = "CONFIRMED"

#: The confirmation that is asked for by the VALUES rather than by the mode.
INFERENCE_CONFIRMATION = "Inference_Checked"


def inference_confirmations(values):
    """The extra confirmation this panel's own values ask for, if any.

    ## Why this is derived and not a mode

    v7.62 and v7.63 shipped `OVERLAY_INFERRED` and `OVERLAY_INFERRED_CELLS`,
    modes whose required artifacts were the ordinary overlay's and whose only
    real content was one more question. That works until a panel that is not
    reviewed through an overlay holds an inferred cell - and v7.65 made exactly
    that panel, by teaching `BAR_MONO` to say when it named a bar against a
    prototype formed in another group of the figure. Those panels are queued
    `BAR_MONO_GEOMETRY`, and no amount of mode naming reaches them without a
    combinatorial table: two geometry modes times inferred-or-not is four modes
    for one question.

    So the question follows the evidence. A mode says what a reviewer OPENS;
    this says what the values in front of them additionally require, and it
    composes with every mode there is or ever will be.

    The same shape `identity_contract_failures` already uses for
    `IDENTITY_EVIDENCE`, and for the same reason recorded there: the condition is
    in the rows, so the check reads the rows.
    """
    for value in values:
        if PROV.row_tier(value) in PROV.PANEL_CONFIRMATION_TIERS:
            return (INFERENCE_CONFIRMATION,)
    return ()


def sha256_of_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256_or_blank(path):
    try:
        return file_sha256(path)
    except Exception:
        return ""


def _blank_text(value):
    """The text a CSV would carry for this cell: None and NaN are both empty.

    The review subject is a fingerprint of the run's own files, so it has to be
    computable FROM those files. Anything that distinguishes `None` from `""`
    makes it computable only by the process that happened to hold the None.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value != value:      # NaN
        return ""
    return "%s" % value


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
    ] + ["artifact:%s|%s|%s|%s" % (item[0], os.path.basename(_s(item[1])),
                                   item[2],
                                   _s(item[3]) if len(item) > 3 else "")
         for item in sorted(artifacts)]
    for row in sorted(values, key=lambda r: _s(r.get("Cell_Key"))):
        material.append("value:" + "|".join(
            # AS THE FILE CARRIES IT (v9.6). This was `row.get(k, "")` through
            # `%s`, so a Python `None` in the runner's own dict hashed as the
            # four characters "None" while the CSV a reviewer opens - and the
            # CSV the finalizer re-reads - has an empty cell there. The subject
            # was therefore NOT recomputable from the run's own outputs: only
            # the producer could check it, which is the one thing a fingerprint
            # must not be. Two blanks are one blank.
            "%s=%s" % (k, _blank_text(row.get(k))) for k in sorted(row)
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

#: WHAT BECOMES OF A VALUE NO SIGNATURE CAN FINALIZE. `finalize` refuses an R4
#: cell - the fitted curve produced the number, or it was carried sideways from
#: one side, or interpolated across a stretch wider than anything the figure
#: draws - and until now that was the end of it: the value was dropped from the
#: accepted file, counted on the stamp, and became nobody's work. A reviewer met
#: "26 of 123 refused" AFTER approving the panel, with no list of which.
#:
#: A separate file rather than more rows in `manual_queue_cells.csv`, because the
#: claim is different at both grains. That queue is cells a reader could not read
#: on panels that went to a person; these are cells a reader DID read, on panels
#: that passed, whose numbers a model made. Filing them together would put panels
#: in the manual queue that nobody needs to digitize by hand.
METHOD_BLOCKED_COLUMNS = [
    "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Cell_Key",
    # All three, because any one of them can be the axis that refused the row -
    # and the person picking this work up needs to know WHICH. A list that names
    # two of the three would send somebody to re-read a mean whose mean was fine.
    "Identity_Method", "Value_Method", "Dispersion_Method",
    # NOT a review tier. Tiers are derived by whoever needs one and written into
    # no file, which `test_provenance` enforces by parsing this module. What goes
    # here is the STATE of the cell and the work it implies.
    "Cell_State", "Next_Action",
    "Image_Path", "Detail",
]

#: The only state this file records today. A second one would mean a value
#: refused for a reason that is not "a model made this number".
METHOD_BLOCKED_STATE = "MODEL_ESTIMATE_ONLY"
METHOD_BLOCKED_ACTION = "MANUAL_REDIGITIZATION"

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


#: The columns an absent optional manifest comes back with. Keyed rather than
#: hard-coded, because there are two of them now and the first one's columns
#: were spelled into the loader - which is how an absent second file would have
#: come back with `identity_resolution`'s columns and failed its schema check
#: with a message about the wrong file.
_OPTIONAL_COLUMNS = {"resolutions": lambda: BM.identity_resolution_columns(),
                     "axes": lambda: BM.axis_manifest_columns()}


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
    for key, name in OPTIONAL_MANIFEST_FILES.items():
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            # An empty frame WITH the columns, so every reader downstream sees
            # the same shape whether the file was there or not - a `KeyError` on
            # `Resolution_ID` for the batches that need no resolutions is the
            # bug an optional manifest invites.
            out[key] = pd.DataFrame(columns=_OPTIONAL_COLUMNS[key]())
            continue
        try:
            out[key] = pd.read_csv(path, dtype=object).fillna("")
        except Exception as exc:
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
    # The same resolution `batch_manifests.colour_tolerance_for` uses, from the
    # same table: series, then config, then the reader's own default. Two copies
    # of that order are two chances for the validator to check a figure the run
    # does not read.
    tolerance = (options or {}).get(
        "colour_tolerance",
        BM.COLOUR_TOLERANCE_DEFAULTS.get(_upper(mark_type), 70.0))
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
                 overlay=None, artifacts=(), inference_crops=None):
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
        # {Cell_Key: path} for the cells whose NUMBER was reconstructed. Keyed by
        # cell rather than by `Inference_ID`, because the id is derived from the
        # value AFTER the grid gate has run - two readers of one unit reconcile
        # to a midpoint - and a picture named for an id the run then does not
        # produce is a picture nobody can find. The ledger ties the two together
        # when the manifest is written.
        self.inference_crops = dict(inference_crops or {})


#: Everything a run leaves on disk that a person looks at or a script re-derives
#: from. The four CSVs were hashed and re-checked; these were not, so the
#: picture a reviewer approved could be swapped for a different picture after
#: they approved it and the finalizer had nothing to say.
#: The routed scatter's durable point file, in the ledger under its own type so
#: the finalizer can find it the way it finds the geometry file - by type,
#: never by a path computed now.
SP_ARTIFACT_TYPE = "SCATTER_POINTS"
#: THE TWO GRAINS UNDER THE POINT FILE. A point file holds only ROUTED points,
#: so the marks a fill split REFUSED - the ones that made the group what it is -
#: are exactly the ones it cannot carry, and a group's N and distribution could
#: never be rebuilt from it. These two can be, and a point cites both by hash.
SP_CANDIDATE_TYPE = "SCATTER_MARKER_CANDIDATES"
SP_GROUP_TYPE = "SCATTER_FILL_GROUPS"

PANEL_ARTIFACT_TYPES = ("OVERLAY", "WPD_PROJECT", "RAW_MARKS", "POINT_DATA",
                        SP_ARTIFACT_TYPE, SP_CANDIDATE_TYPE, SP_GROUP_TYPE)
#: `Artifact_Reference` names the row an artifact belongs to when one artifact
#: is not enough on its own. It exists for `IDENTITY_EVIDENCE`: the finalizer has
#: to re-derive "every file-backed resolution has its evidence here", and the
#: only honest join for that is the `Resolution_ID` the copy was made for.
#: Matching on filename would work until two resolutions cite crops with the
#: same basename.
PANEL_ARTIFACT_COLUMNS = ["Panel_ID", "Artifact_Type", "Artifact_Path", "SHA256",
                          "Artifact_Reference"]


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


#: The four things a BAR_MONO geometry review needs in front of it, and the
#: `panel_artifacts.csv` types they are registered under.
#:
#:   MONO_BAR_GEOMETRY      the numbers, canonical and hash-verifiable
#:   GEOMETRY_REVIEW_INDEX  the contact sheet that ties rows to pictures
#:   CALIBRATION_PANEL      the panel with the axis in frame
#:   CALIBRATION_PANEL_META what that picture drew, as data
#:
#: All four, per panel. The CSV and the index are written once for the run and
#: registered against every panel they cover, because an approval is per panel
#: and "the file existed somewhere in the run" is not the claim being made.
GEOMETRY_ARTIFACT_TYPES = ("MONO_BAR_GEOMETRY", "GEOMETRY_REVIEW_INDEX",
                           "CALIBRATION_PANEL", "CALIBRATION_PANEL_META")

#: And one per geometry ROW. The index links to these; the finalizer re-hashes
#: only what the ledger names, so a row crop left out of it can be replaced
#: with a picture of a different bar and nothing downstream disagrees. There is
#: no count to declare - a panel has as many as it has rows - which is why this
#: is a separate type rather than a fifth entry in the tuple above.
GEOMETRY_ROW_ARTIFACT_TYPE = "GEOMETRY_ROW_CROP"

#: The rows a person signed, copied into the run so the approval is bound to
#: them. `identity_resolution.csv` lives in the manifest directory and is hashed
#: with the other manifests, which is what makes it un-editable after the fact -
#: but the reviewer of a PANEL is being asked about that panel's resolutions,
#: and a ledger entry per panel is what lets the finalizer check they were there
#: to be read.
IDENTITY_ARTIFACT_TYPE = "IDENTITY_RESOLUTION"

#: The evidence bytes themselves, copied into the run. Registering the rows and
#: not the thing they point at protects the hash STRING and not the evidence: a
#: legend crop edited after the run leaves `identity__<Panel_ID>.csv`, the ledger
#: and `Review_Subject_SHA256` all unchanged. And a run directory handed to
#: somebody else did not contain the picture its own review mode asks them to
#: look at.
IDENTITY_EVIDENCE_ARTIFACT_TYPE = "IDENTITY_EVIDENCE"


def write_geometry_review(out_dir, pairs, pad=24):
    """The BAR_MONO geometry artifacts for one run, written once.

    `pairs` is [(image_path, record), ...] - every measured geometry row of the
    run beside the page it came from - AFTER `fill_identities_by_figure`, which
    `canonical_artifact_rows` enforces: a geometry file written before the
    figure has answered says `Auto_Identity_Status: NOT_CALIBRATED` for every
    row of a figure that was resolved in memory a moment later.

    Returns {panel_id: [(TYPE, path), ...]}, ready for `panel_artifacts.csv`.
    Raises rather than returning half a review: unlike an overlay, these are
    what the approval is OF, so a run that cannot write them has not produced
    a reviewable BAR_MONO panel and must say so.
    """
    try:
        return _write_geometry_review(out_dir, pairs, pad=pad)
    except GeometryReviewError:
        raise
    except Exception as exc:
        # `canonical_artifact_rows` and `verify_artifact` raise ValueError, and
        # a caller that catches only GeometryReviewError let those past - so a
        # geometry file that would not verify came out of the runner as a bare
        # traceback instead of a run state.
        raise GeometryReviewError("%s: %s" % (type(exc).__name__, exc)) from exc


def _write_geometry_review(out_dir, pairs, pad=24):
    records = [r for _i, r in pairs]
    review_dir = os.path.join(out_dir, "geometry-review")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "mono_bar_geometry.csv")
    rows = MONO_GEOMETRY.canonical_artifact_rows(records)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=list(MONO_GEOMETRY.GEOMETRY_ARTIFACT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    # Read it back before anyone is asked to approve it. The reader recomputes
    # every row hash, the figure verdict and the calibration arithmetic, so a
    # geometry file that cannot be verified never reaches a queue.
    with open(csv_path, encoding="utf-8") as fh:
        MONO_GEOMETRY.verify_artifact(list(csv.DictReader(fh)))
    # Only the failures THIS call produced. `_FAILURES` is the run's overlay
    # log and resetting it here would erase every panel overlay failure that
    # happened before - a helper that quietly depends on being called first.
    before = len(OVERLAY.failures())
    OVERLAY.write_row_crops(review_dir, pairs)
    mine = OVERLAY.failures()[before:]
    if mine:
        raise GeometryReviewError(
            "the geometry review could not be drawn: %s" % "; ".join(mine))
    index = os.path.join(review_dir, "index.html")
    out = {}
    for record in records:
        pid = _s(record.get("figure"))
        if not pid or pid in out:
            continue
        stem = os.path.join(review_dir, "panel__%s.png" % "".join(
            c if (c.isalnum() or c in "-_") else "_" for c in pid))
        meta = os.path.splitext(stem)[0] + ".json"
        # Every row of this panel, by name. A row whose picture is missing is
        # a row nobody can check, and the index links to it either way.
        crops = []
        for row in records:
            if _s(row.get("figure")) != pid:
                continue
            crops.append(os.path.join(review_dir, OVERLAY.row_crop_name(row)))
        missing = [p for p in [csv_path, index, stem, meta] + crops
                   if not os.path.exists(p)]
        if missing:
            raise GeometryReviewError(
                "panel %s cannot be reviewed: %s was not written"
                % (pid, ", ".join(os.path.basename(p) for p in missing)))
        out[pid] = (list(zip(GEOMETRY_ARTIFACT_TYPES,
                             (csv_path, index, stem, meta)))
                    + [(GEOMETRY_ROW_ARTIFACT_TYPE, p) for p in crops])
    return out


#: The cells whose NUMBER was reasoned to rather than read - the R3 tier - listed
#: per panel so a reviewer can be asked about each one by name.
#:
#: Registered in `panel_artifacts.csv` like the geometry bundle, which is what
#: makes it part of `Review_Subject_SHA256`: the LIST of questions is bound into
#: the panel's approval, so a run that produces one more interpolated cell than
#: the run somebody signed for is a stale approval rather than an unnoticed
#: extra. The finalizer re-hashes it with every other ledger artifact.
INFERENCE_ARTIFACT_TYPE = "INFERENCE_MANIFEST"

#: And one picture per cell on that list, registered against the `Inference_ID`
#: it belongs to. The manifest gives a reviewer the support columns, the span and
#: the occlusion cause as NUMBERS; this is the same claim as a picture, because
#: holding a pixel coordinate in your head against a printed figure is arithmetic
#: performed by somebody who cannot check it. `finalize` requires one per cell it
#: asks about - a per-cell confirmation with no picture of that cell is the
#: signature on a filename this package refuses everywhere else.
INFERENCE_CONTEXT_ARTIFACT_TYPE = "INFERENCE_CONTEXT"

#: Enough to find the cell in the picture and to judge the reasoning that
#: produced its number. The geometry columns are the ones that justify a LOCAL
#: interpolation - how wide the unread stretch was, what covered it, how thick
#: the stroke is - and they are blank for readers that do not measure them,
#: which is visible in the file rather than absent from it.
INFERENCE_MANIFEST_COLUMNS = [
    "Inference_ID", "Panel_ID", "Source_Panel_ID", "Unit_ID", "Cell_Key",
    "Identity_Method", "Value_Method", "Mean", "Dispersion_Value",
    "Value_Span_Px", "Value_Support_Left_Px", "Value_Support_Right_Px",
    "Occlusion_Cause", "Occlusion_Width_Px", "Local_Stroke_Px",
    "Expected_Dash_Gap_Px",
    # Whether the forward and backward traces agreed about this cell, or the
    # more conservative of two disagreeing readings was taken. It is part of what
    # a person is being asked to accept, so it is on the row they read - and
    # therefore in the identifier below.
    "Trace_Agreement",
    # AND THE SPREAD, from v7.71. A cell can be asked about at this grain because
    # its NUMBER was reconstructed or because its ERROR BAR came off a cap nothing
    # connects to the mark - `row_tier` has priced both since v7.70 and this list
    # named only the first, so the row a reviewer read said nothing about the
    # question they were being asked, and the identifier below did not change when
    # the answer to it did.
    "Dispersion_Method", "Errorbar_Lower", "Errorbar_Upper",
    "Errorbar_Stem_Confirmed",
]

#: What an `Inference_ID` is derived FROM: EVERY COLUMN OF THE ROW THE REVIEWER
#: READS, which is what makes the identifier a hash of the question rather than a
#: label on it. Not a counter - a counter renumbers when a cell is added, so
#: every confirmation in the file would silently move to a different cell.
#:
#: ## Why the whole row and not just the answer
#:
#: v7.63 hashed the cell, the two methods and the number. That binds the
#: OUTPUT and not the EVIDENCE, and the two can move independently: a re-run
#: whose supports shift from 101-104 to 96-109 and whose occlusion goes from
#: ERRORBAR_STEM to MIXED can land on the same mean by coincidence, and did not
#: have to land on it by much of one - a curve is smooth over a few pixels. The
#: identifier was then unchanged, and a confirmation given against the first
#: reconstruction attached itself to the second.
#:
#: The panel's `Review_Subject_SHA256` does go stale in that case, so the PANEL
#: has to be approved again - but the two files are filled in by different people
#: at different times, and nothing made the cell-level answer expire with the
#: panel-level one. What a person confirms at this grain is "this reconstruction,
#: from these supports, across this occlusion, at this drawing scale", and every
#: one of those is a column here.
#:
#: Every field must be one the VALUE ROW carries, because `finalize` re-derives
#: these identifiers from `figure_values_machine_qc.csv` rather than trusting the
#: manifest. That is why the raster hash is not in the recipe: it is not on the
#: value row, and the panel signature covers it.
INFERENCE_IDENTITY_FIELDS = tuple(c for c in INFERENCE_MANIFEST_COLUMNS
                                  if c != "Inference_ID")


def _canon_field(value):
    """One spelling for a number that has been through a CSV and one that has not.

    The run derives these identifiers from value records in memory and `finalize`
    derives them again from the file those records were written to, so `90.0` the
    float and `"90.0"` the string have to hash the same - and so do `"90"` and
    `"90.0"`, which is the same number written by two different writers.
    """
    text = _s(value)
    if not text:
        return ""
    try:
        return repr(float(text))
    except (TypeError, ValueError):
        return text


def _blocked_detail(value, identity, method):
    """Which axis refused this cell, in the words of the person who re-reads it."""
    if not (identity and method):
        return "nothing says how this number was got"
    if PROV.review_tier(identity, method) not in PROV.FINALIZABLE_TIERS:
        return "%s: the number was not read off the ink" % method
    spread = _s(value.get("Dispersion_Method"))
    return ("%s: the number is measured and the SPREAD is not"
            % (spread or "nothing says how the spread was got"))


def inference_id(record, panel_id=""):
    """A content-derived identifier for one cell's reconstructed value.

    Stable across re-runs that reproduce the cell AND its evidence; different the
    moment any column of `INFERENCE_IDENTITY_FIELDS` moves. Uniqueness within a
    run follows from the value contract - one row per (Unit_ID, Cell_Key) - rather
    than from a check here that nothing could reach.
    """
    material = "|".join(
        "%s=%s" % (key, _canon_field(panel_id)
                   if key == "Panel_ID" and panel_id
                   else _canon_field(record.get(key)))
        for key in INFERENCE_IDENTITY_FIELDS)
    return "INF_" + sha256_of_text(material)[:16]


def write_inference_manifests(out_dir, rows_by_panel):
    """{Panel_ID: [(TYPE, path)]} for the panels holding a reconstructed value.

    One CSV per panel rather than one for the run, for the reason
    `identity__<Panel_ID>.csv` is per panel: an approval is per panel, and "the
    file existed somewhere in the run" is not the claim being made.
    """
    out = {}
    if not rows_by_panel:
        return out
    review_dir = os.path.join(out_dir, "inference-review")
    os.makedirs(review_dir, exist_ok=True)
    for pid, rows in sorted(rows_by_panel.items()):
        if not rows:
            continue
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in pid)
        path = os.path.join(review_dir, "inference__%s.csv" % safe)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=INFERENCE_MANIFEST_COLUMNS)
            writer.writeheader()
            for row in sorted(rows, key=lambda r: _s(r.get("Cell_Key"))):
                record = {c: _s(row.get(c)) for c in INFERENCE_MANIFEST_COLUMNS}
                record["Panel_ID"] = pid
                record["Inference_ID"] = inference_id(row, panel_id=pid)
                writer.writerow(record)
        out[pid] = [(INFERENCE_ARTIFACT_TYPE, path)]
    return out


def write_identity_resolutions(out_dir, rows_by_panel, file_root="."):
    """{Panel_ID: [(TYPE, path)]} for the panels a person named.

    One CSV per panel, the manifest's own columns, verbatim - not a summary and
    not a join: what a reviewer is asked to check is what was written, including
    the evidence and the row hash it was written against.

    And the EVIDENCE ITSELF, copied in. `check_identity_resolution` hashes the
    legend crop or the page image at validation time, which protects the hash
    STRING in the manifest and nothing else: edit or delete the file afterwards
    and `identity__<Panel_ID>.csv`, the ledger and `Review_Subject_SHA256` are
    all unchanged, so `Identity_Checked=CONFIRMED` could be given against
    evidence that no longer exists. Hand somebody only the run directory and the
    evidence was not in it at all.

    So the bytes travel with the run, are re-hashed after the copy, and are
    registered as `IDENTITY_EVIDENCE` - which the finalizer re-hashes with every
    other ledger artifact. A copy that does not match refuses the bundle rather
    than being registered: a review whose evidence cannot be reproduced is not a
    review.

    `REVIEWER_INSPECTION` has no file to copy - that is what makes it the
    weakest evidence there is - and carries a mandatory Note instead.
    """
    out = {}
    if not rows_by_panel:
        return out
    review_dir = os.path.join(out_dir, "geometry-review")
    os.makedirs(review_dir, exist_ok=True)
    columns = BM.identity_resolution_columns()
    for pid, rows in sorted(rows_by_panel.items()):
        if not rows:
            continue
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in pid)
        path = os.path.join(review_dir, "identity__%s.csv" % safe)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({c: _s(row.get(c)) for c in columns})
        artifacts = [(IDENTITY_ARTIFACT_TYPE, path)]
        for row in rows:
            if _upper(row.get("Evidence_Type")) not in BM.FILE_EVIDENCE_TYPES:
                continue
            declared = _s(row.get("Evidence_Artifact"))
            want = _s(row.get("Evidence_Artifact_SHA256")).lower()
            # Confined here as well as in the validator, because the validator's
            # copy of this rule sits behind `check_files`. Skipping a CONTENT
            # hash when file checking is off is a defensible choice; letting a
            # path escape the corpus is not, and this is the code that actually
            # opens the file - so an absolute path from anywhere on the machine
            # could be copied into the run and registered as evidence.
            root = os.path.realpath(file_root)
            source = os.path.realpath(
                declared if os.path.isabs(declared)
                else os.path.join(root, declared))
            rid = _s(row.get("Resolution_ID"))
            if source != root and not source.startswith(root + os.sep):
                raise GeometryReviewError(
                    "IDENTITY_EVIDENCE_OUTSIDE_ROOT: the evidence for %s (%s) "
                    "resolves outside %s, so it is not evidence from this "
                    "corpus" % (rid, declared, root))
            base = "".join(c if (c.isalnum() or c in ".-_") else "_"
                           for c in os.path.basename(declared))
            dest = os.path.join(review_dir, "evidence__%s__%s" % (rid, base))
            try:
                shutil.copyfile(source, dest)
            except OSError as exc:
                raise GeometryReviewError(
                    "the evidence for %s could not be copied into the run: "
                    "%s (%s)" % (rid, declared, exc))
            got = file_sha256(dest)
            if want and got != want:
                raise GeometryReviewError(
                    "the evidence for %s copied as %s... and the resolution "
                    "says %s...; a review whose evidence cannot be reproduced "
                    "is not a review" % (rid, got[:16], want[:16]))
            artifacts.append((IDENTITY_EVIDENCE_ARTIFACT_TYPE, dest, rid))
        out[pid] = artifacts
    return out


class GeometryReviewError(Exception):
    """A BAR_MONO panel whose review artifacts could not be written.

    Not a drawing failure to be logged and stepped over. An overlay is a review
    AID - a panel with values and no picture is still reviewable through its
    WPD project - and these are the review itself: the numbers, the pictures
    and the index tying them together. A panel missing one of them cannot be
    approved, so the run has to say that rather than queue it and let the
    finalizer discover it later.
    """


def _review_crop(panel, box):
    """The plot area unioned with whatever the manifest says the axes occupy.

    `Axis_X_Region` and `Axis_Y_Region` exist so a person re-checking a
    calibration knows where to look. That is the same rectangle the panel
    picture has to include, and estimating it as a fraction of the panel - the
    fallback - crops away long tick labels, units printed beside the numbers,
    and any axis drawn away from the plot box. A field that is filled in and
    not used is worse than one that is blank, so a region that does not parse
    refuses the panel rather than being ignored.
    """
    x0, x1, y0, y1 = box
    for column in ("Axis_X_Region", "Axis_Y_Region"):
        text = _s(panel.get(column))
        if not text:
            continue
        try:
            rx0, rx1, ry0, ry1 = BM.parse_box(text)
        except ValueError as exc:
            raise ValueError(
                "%s=%r is not x0,x1,y0,y1: %s" % (column, text, exc))
        x0, x1 = min(x0, rx0), max(x1, rx1)
        y0, y1 = min(y0, ry0), max(y1, ry1)
    if (x0, x1, y0, y1) == tuple(box):
        return None                       # nothing declared; the picture says so
    return [x0, x1, y0, y1]


def measure_bar_mono_figures(panels, positions_by_panel, series_by_panel,
                             options_by_config, file_root="."):
    """Every BAR_MONO panel of the batch, measured anonymously and then named.

    The two-pass shape, and it has to be two passes because identity is
    figure-local and geometry is panel-local. A panel loop that reads a panel
    and names its series in the same step can only name them from what one
    panel holds - an absolute fill density against `_FILL_BANDS`, measured on
    one figure and wrong on the second. So: measure every panel of the batch
    with no series named, group the rows by `Figure_ID`, and let the FIGURE say
    what its fills mean.

    Returns (rows_by_panel, pairs, refusals):

      rows_by_panel  {Panel_ID: [record, ...]} for the panel loop to read its
                     values out of, identities already resolved
      pairs          [(image_path, record), ...] for the review bundle
      refusals       {Panel_ID: (state, detail)} for a panel this pass could
                     not measure at all - the panel loop turns them into the
                     outcome, because that is where a run state belongs
    """
    rows_by_panel, pairs, refusals = {}, [], {}
    for panel in panels:
        pid = _s(panel.get("Panel_ID"))
        if _upper(panel.get("Mark_Type")) != "BAR_MONO":
            continue
        if (_upper(panel.get("Panel_Mode")) or "AUTO") != "AUTO":
            continue
        image_path = _s(panel.get("Image_Path"))
        resolved = (image_path if os.path.exists(image_path)
                    else os.path.join(file_root, image_path))
        series_rows = series_by_panel.get(pid, [])
        fills = [_upper(r.get("Bar_Fill_Pattern")) for r in series_rows]
        options = options_by_config.get(_s(panel.get("Config_ID")), {})
        kwargs = _reader_kwargs(options, "BAR_MONO")
        if BM.blank(panel.get("Baseline_Value")):
            kwargs.setdefault("baseline_value", 0.0)
        else:
            kwargs["baseline_value"] = float(panel.get("Baseline_Value"))
        try:
            box = BM.parse_box(",".join(
                _s(panel.get(c)) for c in
                ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")))
            ycal = _calibration(panel, "Y")
            image = Image.open(resolved).convert("RGB")
            rows = MR.read_monochrome_bar_geometry(
                image, box, _x_positions(positions_by_panel.get(pid, [])),
                ycal, fills, review_crop_box=_review_crop(panel, box),
                panel_id=pid,
                # The DOMAIN, not the view: which panels share a printed legend
                # is what decides whose fills calibrate whose, and it is only
                # the same question as "which figure is this" when a figure has
                # one legend. `compile_plan` defaults the domain to the view, so
                # a plan that does not distinguish them behaves as before.
                identity_domain_id=(_s(panel.get("Identity_Domain_ID"))
                                    or _s(panel.get("Figure_ID")) or pid),
                # And the provenance view alongside it, never instead of it.
                # The artifact states both; a reader that was handed only one
                # of them wrote the domain into a column called `Figure_ID`.
                figure_id=_s(panel.get("Figure_ID")), **kwargs)
        except MR.UnsupportedCapabilityError as exc:
            refusals[pid] = ("NO_READER_AVAILABLE", "%s" % exc)
            continue
        except (MR.GeometryResolutionError, ValueError, OSError) as exc:
            refusals[pid] = ("PANEL_GEOMETRY_UNRESOLVED",
                             "%s: %s" % (type(exc).__name__, exc))
            continue
        except Exception as exc:
            raise InternalReaderError(
                "measuring BAR_MONO panel %s raised %s: %s"
                % (pid, type(exc).__name__, exc)) from exc
        rows_by_panel[pid] = rows
        pairs.extend((resolved, r) for r in rows)
    if pairs:
        MONO_GEOMETRY.fill_identities_by_figure([r for _i, r in pairs])
    return rows_by_panel, pairs, refusals


class IdentityResolutionError(Exception):
    """A human-supplied identity that does not apply to this measurement.

    Not a manifest problem, because detecting it needs the raster:
    `check_identity_resolution` has already checked everything that can be
    checked on paper. Not a per-cell skip either - it refuses the whole panel.
    A resolution that names a bar this measurement does not have, or one the
    reader named itself, means the person was reading a DIFFERENT measurement of
    this panel, and their other rows for it are then equally unsafe.
    """


def apply_identity_resolutions(records, resolution_rows):
    """{(group, slot): identity} for the cells a person named, or refuse.

    The three things that cannot be checked before the panel is measured:

    * the row exists - a resolution naming a bar the reader never found
    * the reader had NOT already named it - `identity_resolution.csv` supplies
      an identity that is missing, it does not overrule one that is present.
      That is the whole difference between this file and an override channel,
      and it is enforced here because only the measurement knows
    * the measurement it was written against is the one in hand -
      `Geometry_Row_SHA256` on the resolution against the row's own stamp

    And one that needs the auto identities and the human ones TOGETHER: a group
    where the figure named slot 0 STIPPLED and a person named slot 1 STIPPLED
    too. Neither row breaks a rule on its own - the human's target really was
    unnamed - and the result is two marks for one series in one group, which
    surfaces much later as a duplicate factorial cell: fail-closed, but blaming
    the grid for something the identities did.

    Raises `IdentityResolutionError` for any of them.
    """
    by_slot = {(_s(r.get("group")), r.get("slot")): r for r in records
               if r.get("slot") is not None}
    out = {}
    for row in resolution_rows:
        group = _s(row.get("Group_ID"))
        slot = int(float(_s(row.get("Geometry_Slot"))))
        rid = _s(row.get("Resolution_ID"))
        record = by_slot.get((group, slot))
        if record is None:
            raise IdentityResolutionError(
                "IDENTITY_RESOLUTION_NO_SUCH_ROW: %s names %s/slot %d and the "
                "measurement has no such row (it has %s)"
                % (rid, group, slot,
                   ", ".join("%s/slot %s" % k for k in sorted(
                       by_slot, key=lambda k: (k[0], k[1]))) or "none"))
        if not MONO_GEOMETRY.measurement_usable(record):
            raise IdentityResolutionError(
                "IDENTITY_RESOLUTION_ON_A_REFUSAL: %s names %s/slot %d, whose "
                "measurement was refused (%s). An identity cannot rescue a "
                "number that was never read"
                % (rid, group, slot, _s(record.get("error")) or "no value"))
        if _s(record.get("resolved_fill_pattern")):
            raise IdentityResolutionError(
                "IDENTITY_RESOLUTION_OVERRIDES_MEASUREMENT: %s names %s/slot "
                "%d, which the figure already resolved as %s. This file "
                "supplies identities the reader could not measure; it does not "
                "overrule ones it did"
                % (rid, group, slot, _s(record.get("resolved_fill_pattern"))))
        stamped = _s(record.get("geometry_row_sha256"))
        want = _s(row.get("Geometry_Row_SHA256")).lower()
        if stamped and want and stamped != want:
            raise IdentityResolutionError(
                "IDENTITY_RESOLUTION_STALE: %s was written against row %s... "
                "and %s/slot %d now measures %s.... Re-read the bar in this "
                "run's mono_bar_geometry.csv before naming it"
                % (rid, want[:16], group, slot, stamped[:16]))
        out[(group, slot)] = dict(
            series=_s(row.get("Resolved_Series_ID")),
            pattern=_upper(row.get("Resolved_Fill_Pattern")),
            resolution=rid,
            evidence=_upper(row.get("Evidence_Type")))
    # Auto and human together, per group, before any of it is read as a value.
    auto_fill = {}
    for record in records:
        if record.get("slot") is None:
            continue
        pattern = _upper(record.get("resolved_fill_pattern"))
        if pattern and MONO_GEOMETRY.measurement_usable(record):
            auto_fill.setdefault(_s(record.get("group")), {})[pattern] = \
                record.get("slot")
    for (group, slot), identity in sorted(out.items(),
                                          key=lambda kv: (kv[0][0], kv[0][1])):
        clash = auto_fill.get(group, {}).get(identity["pattern"])
        if clash is not None:
            raise IdentityResolutionError(
                "IDENTITY_RESOLUTION_CONFLICTS_WITH_MEASUREMENT: %s names "
                "%s/slot %d as %s, and the figure already read slot %s of the "
                "same group as %s. One group holds one bar per series, so this "
                "would put two values in one cell"
                % (identity["resolution"], group, slot, identity["pattern"],
                   clash, identity["pattern"]))
    return out


def _geometry_marks(records, series_rows, positions, resolved=None):
    """Resolved geometry rows, in the shape the panel loop already reads.

    The identity comes from `resolved_fill_pattern` - what the FIGURE said the
    bar's fill is - matched against the `Bar_Fill_Pattern` each series declares.
    A bar the figure could not name goes to `resolved`, which is what a person
    wrote in `identity_resolution.csv`; a bar in neither yields no mark, so its
    cell goes missing and is queued.

    Every mark carries where its identity came from. `Identity_Source` is AUTO
    or HUMAN, `Identity_Evidence_Type` is what backs it, and `Resolution_ID`
    points at the row a person signed - so a value in
    `figure_values_accepted.csv` can be asked "who named this series", which
    before this stopped at the raw marks and was answerable only by reading two
    files side by side.
    """
    by_fill = {}
    for row in series_rows:
        by_fill.setdefault(_upper(row.get("Bar_Fill_Pattern")), []).append(
            _s(row.get("Series_ID")))
    resolved = dict(resolved or {})
    out = []
    for record in records:
        # `measurement_usable`, not "no error": BAR_TOO_SMALL_TO_SAMPLE is a
        # complaint about the FILL, and the mean and dispersion of a bar with no
        # interior are measured exactly as on any other bar. Filed as an error
        # like every other code it dropped publication 127's two fifteen-pixel
        # values for a reason that was never about the values.
        if not MONO_GEOMETRY.measurement_usable(record):
            continue
        pattern = _upper(record.get("resolved_fill_pattern"))
        human = resolved.get((_s(record.get("group")), record.get("slot")))
        if pattern:
            named = by_fill.get(pattern, [])
            if len(named) != 1:
                # No series declares this fill, or two do. Either way the bar
                # cannot be attributed, and a mark with a guessed series is the
                # failure this whole design exists to prevent.
                continue
            series, identity = named[0], dict(
                Identity_Source="AUTO",
                Identity_Evidence_Type=BM.AUTO_IDENTITY_EVIDENCE[0],
                Resolution_ID="", Auto_Fill_Pattern=pattern,
                Resolved_Fill_Pattern=pattern,
                # WHICH ROUTE the figure took to that pattern, straight off the
                # geometry record. `MEASURED_FILL_RELATION` is a complete group
                # assigned from relations between its own measured samples;
                # `FIGURE_PROTOTYPE_MATCH` is an incomplete group's sample landing
                # inside a range formed in OTHER groups of the figure - the same
                # answer with the evidence one step further away, which is R2 and
                # asks a person to confirm it. Copied, never re-decided here.
                Identity_Method=_s(record.get("identity_method")))
        elif human:
            series, pattern = human["series"], human["pattern"]
            identity = dict(
                Identity_Source="HUMAN",
                Identity_Evidence_Type=human["evidence"],
                Resolution_ID=human["resolution"],
                # Blank, and it must stay blank: the reader measured no fill for
                # this bar. Filling it in with the person's answer is the audit
                # trail saying the machine decided something a person did.
                Auto_Fill_Pattern="",
                Resolved_Fill_Pattern=pattern,
                # A person, on the channel that already exists for it: the
                # resolution row, its evidence and the reviewer are all in
                # `identity_resolution.csv` and re-checked by
                # `identity_contract_failures`. R0 - not because a person cannot
                # be wrong, but because this is the strongest evidence the ladder
                # has and there is no further signature to ask for.
                Identity_Method="HUMAN_RESOLUTION")
        else:
            continue
        out.append(dict(
            identity,
            series=series, x_label=_s(record.get("group")),
            mean=record.get("value"), dispersion=record.get("dispersion"),
            top_px=record.get("edge_px_image"),
            cap_px=record.get("cap_px_image"),
            fill_pattern=pattern,
            fill_density=record.get("ink_mass"),
            order=record.get("slot"),
            x=(sum(record["footprint_px_image"]) / 2.0
               if record.get("footprint_px_image") else None),
            Bar_Direction=_upper(record.get("direction")),
            Bar_Top_Definition="OUTLINE_CENTER",
            # The top edge this reader walked to, in outline-centre terms - the
            # same measurement `Bar_Top_Definition` names, in the vocabulary the
            # tier registry prices. A bar too small to sample its own fill still
            # has a measured top, which is why the identity can be missing from
            # a row whose number is not.
            Value_Method="BAR_OUTLINE_CENTER",
            # `_mono_bar_errorbar` walks up from the bar top and only reports a
            # cap it reached along a stem, so a dispersion on a monochrome bar is
            # a connected cap or it is nothing.
            Dispersion_Method=("DIRECT_CONNECTED_CAP"
                               if record.get("dispersion") is not None
                               else "NO_DISPERSION"),
            Errorbar_Stem_Confirmed=("TRUE" if record.get("dispersion")
                                     is not None else "FALSE"),
            Geometry_Row_SHA256=_s(record.get("geometry_row_sha256")),
        ))
    return out


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


def _routed_scatter(panel, series_rows, axes, image, box, image_path, kwargs,
                    annotations):
    """Route a monochrome scatter and calibrate every point against its own axis.

    Returns `{"points": [...], "meta": {...}}` or `{"refusal": "..."}`. The
    points come back in the shape `_scatter_outcome` groups by - `series`, plus
    the area and overlap columns `point_count_audit` reads - with their values
    already computed, because a twin-axis panel has no single y calibration for
    anything downstream to apply.

    A PANEL WITH NO X AXIS IN THE MANIFEST IS REFUSED HERE rather than defaulted
    to the panel row's ladder. The whole point of the grain is that a point says
    which scale it was read on, and half the answer coming from another file is
    the ambiguity it was built to remove; the manifest layer refuses such a
    manifest too, so this is the second of two.
    """
    import scatter_points as SP
    x_axes = [a for a in axes if a["Dimension"] == "X"]
    if len(x_axes) != 1:
        return dict(refusal="this panel's axis manifest declares %d x axes; a "
                            "point cloud is read on exactly one"
                            % len(x_axes))
    declared = [dict(Series_ID=_s(r.get("Series_ID")),
                     Marker_Shape=_upper(r.get("Marker_Shape")),
                     Marker_Fill=_upper(r.get("Marker_Fill")),
                     Axis_ID=_s(r.get("Axis_ID")))
                for r in series_rows]
    unnamed = [d["Series_ID"] for d in declared if not d["Axis_ID"]]
    if unnamed:
        return dict(refusal="this panel declares an axis manifest and %s names "
                            "no Axis_ID; on a panel with more than one scale a "
                            "series that does not say which it is on cannot be "
                            "calibrated" % ", ".join(sorted(unnamed)))
    try:
        points, meta = SP.read_routed_scatter_panel(
            image, box, declared, axes, _s(panel.get("Panel_ID")),
            file_sha256(image_path), x_axes[0]["Axis_ID"],
            threshold=kwargs.get("threshold", 150) or 150,
            exclude_boxes=annotations)
    except ValueError as exc:
        return dict(refusal="%s" % exc)
    # A POINT THAT WAS NOT CALIBRATED IS NOT A POINT. `stamp_points` returns it
    # with its pixel, its refusal and no value - because a series whose axis is
    # not a Y axis of this panel has no scale to be read on - and a value row
    # built from it would be a number with no arithmetic behind it. They are
    # dropped here, and where that leaves nothing the panel is refused NAMING
    # THE REASON rather than reported as an empty read.
    refused = sorted({_s(p.get("refusal")) for p in points if p.get("refusal")})
    points = [p for p in points if not p.get("refusal")]
    if not points:
        return dict(refusal="every routed mark was refused a scale: %s"
                            % (", ".join(refused) or "no series named an axis "
                               "this panel declares"))
    for p in points:
        # THE COLUMNS THE AUDIT READS, under the names it reads them by. It
        # counts distinct pixels and looks for a blob too big to be one marker;
        # the routed reader has already refused those as MARKER_MERGED, so this
        # is a second net rather than the first.
        p["series"] = p.get("Series_ID")
        p["marker_area_px"] = p.get("area_px")
        p["mask_overlap"] = 0
    return dict(points=points, meta=meta, axes=axes, refused=refused,
                x_axis_id=x_axes[0]["Axis_ID"], series=declared)


def _axis_manifest(axis_rows):
    """The panel's axis rows as `axis_grain` takes them, ticks parsed.

    `Calibration_Points` is spelled `value:pixel;value:pixel` in the file, the
    same as `Axis_Y_Ticks`, so a person moving a ladder between the two is not
    also translating it. The manifest layer has already refused a row that does
    not parse, so this only has to parse.
    """
    out = []
    for r in axis_rows or ():
        out.append(dict(
            Axis_ID=_s(r.get("Axis_ID")), Panel_ID=_s(r.get("Panel_ID")),
            Dimension=_upper(r.get("Dimension")), Side=_upper(r.get("Side")),
            Unit=_s(r.get("Unit")), Scale=_upper(r.get("Scale")) or "LINEAR",
            Calibration_Points=[[float(v), float(px)] for v, px in
                                (chunk.split(":") for chunk in
                                 _s(r.get("Calibration_Points")).split(";")
                                 if chunk.strip())]))
    return out


def run_panel(panel, series_rows, position_rows, options, unit, raw_dir,
              file_root=".", project_dir=None, review_dir=None, geometry=None,
              geometry_refusal=None, resolutions=(), inference_dir=None,
              config_rows=(), axis_rows=(), output_dir=None):
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
    if geometry_refusal:
        # Applied HERE, after the panel's declaration is known. Returned from
        # the loop instead, the outcome carried `Cells_Declared=0` and no
        # missing cells - so a panel of eighteen cells whose raster vanished
        # between validation and the geometry pass read as "0 / 0", which is
        # the understatement the panel loop's own early returns were fixed for.
        return PanelOutcome(geometry_refusal[0], declared=declared,
                            missing=all_cells, detail=geometry_refusal[1])

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
    #: What the routed reader established, or None where the panel read the way
    #: it always did. Set inside the dispatch and read at the outcome, which are
    #: two hundred lines apart.
    routed = None

    try:
        if mark == "SCATTER":
            # The panel says where its annotations are; the manifest layer has
            # already checked each box meets the plot area and does not swallow
            # it, so this only has to parse.
            annotations = [BM.parse_box(chunk) for chunk in
                           _s(panel.get("Annotation_Boxes")).split(";") if chunk.strip()]
            axes = _axis_manifest(axis_rows)
            if axes:
                # THE AXIS MANIFEST IS THE SWITCH. A panel whose y scale is a
                # grain of its own is a panel `read_scatter_panel` cannot read -
                # it takes ONE y calibration - so the routed reader takes it
                # instead, tells the series apart by marker shape and fill, and
                # calibrates each point against the axis its series names. A
                # panel with no axis rows reads exactly as before.
                routed = _routed_scatter(panel, series_rows, axes, image, box,
                                         resolved, kwargs, annotations)
                if routed.get("refusal"):
                    return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                                        detail=routed["refusal"])
                rows = routed["points"]
            else:
                rows = MR.read_panel("SCATTER", image=image, panel_box=box,
                                     x_calibration=xcal, y_calibration=ycal,
                                     series=_series_specs(series_rows, mark, options),
                                     exclude_boxes=annotations, **kwargs)
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
        elif mark in ("LINE_MONO", "LINE_MONO_STYLE"):
            # Same call for both. They differ in what the reader looks at -
            # marker geometry against stroke pattern - and the manifest has
            # already been checked against the right discriminant for each.
            #
            # The reader's panel note is cleared by the PANEL LOOP, not here:
            # this branch is only reached once the box parses and the raster
            # opens, so clearing it here left every earlier exit able to inherit
            # the previous panel's diagnosis.
            rows = MR.read_panel(mark, image=image, panel_box=box,
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
            default_tolerance = float(options.get(
                "colour_tolerance", BM.COLOUR_TOLERANCE_DEFAULTS["BAR_COLOR"]))
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
            # Measured before the panel loop started, and NAMED by its figure.
            # This branch used to call `read_monochrome_bar_panel`, which
            # decides identity inside one panel from an absolute fill density -
            # measured on one figure and wrong on the second. What arrives here
            # is a resolution the whole figure agreed on.
            if not geometry:
                return PanelOutcome(
                    "PANEL_GEOMETRY_UNRESOLVED", declared=declared,
                    missing=all_cells,
                    detail="the geometry pass produced nothing for this panel")
            try:
                human_identities = apply_identity_resolutions(geometry,
                                                             resolutions)
            except IdentityResolutionError as exc:
                # The whole panel. A resolution written against a different
                # measurement of this panel makes every other resolution for it
                # suspect, so nothing here is read on the strength of the rows
                # that happened to still match.
                return PanelOutcome(
                    "SERIES_IDENTITY_UNRESOLVED", declared=declared,
                    missing=all_cells, detail="%s" % exc)
            rows = _geometry_marks(geometry, series_rows, position_rows,
                                   resolved=human_identities)
            if not rows:
                # Why, not just "nothing". Every row of this panel refused,
                # and the reasons are on the rows - reported as "the reader
                # resolved no marks" they were only findable by opening
                # `mono_bar_geometry.csv`, so the run manifest and the manual
                # queue lost the one thing a person would act on.
                reasons = sorted({_s(r.get("error")) for r in geometry
                                  if r.get("error")})
                if reasons:
                    return PanelOutcome(
                        "PANEL_GEOMETRY_UNRESOLVED", declared=declared,
                        missing=all_cells, detail="; ".join(reasons))
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
        # "the reader resolved no marks" is where a figure's worth of
        # gridlines-read-as-curves hid: the panel was routed to manual with
        # nothing a person could act on, and the BAR_MONO geometry branch above
        # learned the same lesson from its own per-row reasons. What the LINE
        # readers know about a panel is a panel-level note, folded onto whatever
        # outcome this returns by the panel loop - here, and equally on the exits
        # that DO produce rows, which is the half v9.14 left out.
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
                                project_dir, review_dir=review_dir, box=box,
                                routed=routed, output_dir=output_dir)

    # ---- relabel reader output with the DECLARED identity before it becomes a
    # ---- value row. The reader never learns what a series means.
    converted, kept = [], []
    # A MARK TWO DECLARED COLOURS BOTH CLAIM IS NOT A MARK EITHER OF THEM NAMED.
    # The colour readers measure this per mark (`mask_overlap`); the decision is
    # here, because dropping a value is a batch-layer judgement and because the
    # cell then goes missing, is queued, and is read by a person - which is the
    # right outcome for ink that does not separate the series drawn on it.
    #
    # Left in, the grid is COMPLETE and wrong in the way nothing else catches:
    # two series holding one printed mark, no cell missing and no count off.
    contested = [row for row in rows if int(row.get("mask_overlap") or 0)]
    rows = [row for row in rows if not int(row.get("mask_overlap") or 0)]
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
    envelope = dict(mark_envelope_header(panel, file_sha256(resolved),
                                         MR.READER_VERSION,
                                         series_rows=series_rows,
                                         position_rows=position_rows,
                                         config_rows=config_rows),
                    schema=MARK_DATA_SCHEMA, Source_Image=resolved)
    envelope["marks"] = stamp_marks(_jsonable(kept), envelope)
    # Back onto the value rows, in the order `to_value_records` preserves - the
    # same pairing the inference crops rely on. This is what lets a value be
    # joined to the mark it was made from rather than merely to the panel.
    for record, stamped in zip(records, envelope["marks"]):
        record["Mark_Record_SHA256"] = stamped["Mark_Record_SHA256"]
        record["Method_Attestation_SHA256"] = stamped["Method_Attestation_SHA256"]
    try:
        with open(raw_path, "w", encoding="utf-8") as fh:
            # `allow_nan=False`: Python writes bare `NaN` and `Infinity`, which
            # are not JSON, and a mark carrying one passed every
            # `abs(a - b) > EPSILON` check downstream because every comparison
            # against NaN is False - a geometry that cannot be checked reading
            # as one that agrees.
            json.dump(envelope, fh, indent=1, sort_keys=True, allow_nan=False)
    except ValueError as exc:
        # A DEFECT HERE, NOT A DIFFICULT FIGURE, and therefore the same answer
        # this module gives a KeyError from a renamed field: stop the batch and
        # say which panel. A reader that computes a NaN has a bug, and a run
        # that quietly refused that panel would hide it behind a queue row
        # somebody would spend an afternoon re-reading by hand.
        if os.path.exists(raw_path):
            os.remove(raw_path)
        raise InternalReaderError(
            "reader %s on panel %s produced a value JSON cannot express: %s"
            % (mark, pid, exc)) from exc

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
    contested_note = ("" if not contested else
                      "%d mark(s) were claimed by more than one declared "
                      "colour and were not attributed to any series; declare "
                      "colours further apart than their tolerances, or read "
                      "these cells by hand" % len(contested))
    # ---- one picture per reconstructed cell.
    #
    # Drawn HERE and nowhere later, because this is the only place that holds the
    # raster, the panel box and the mark's own pixels at the same time. The value
    # rows keep the support columns but not the row the value sits on, and the
    # manifest is written after the grid gate, by which point the image is closed
    # and the calibration is gone.
    #
    # `records` comes back from `to_value_records` in the order of `converted`,
    # which is what lets a mark be paired with the cell key its value landed in.
    crops = {}
    if inference_dir:
        for mark, record in zip(converted, records):
            # The VALUE axis, not the row: this picture shows the two columns
            # a number was interpolated between, and a cell that is R3 because
            # of its error bar has no such columns to picture.
            if PROV.value_tier(_s(record.get("Value_Method"))) \
                    not in PROV.CELL_CONFIRMATION_TIERS:
                continue
            safe = "".join(c if (c.isalnum() or c in "-_") else "_"
                           for c in "%s__%s" % (pid, record["Cell_Key"]))
            drawn = OVERLAY.draw_inference_context(
                os.path.join(inference_dir, "context__%s.png" % safe),
                resolved, box, mark,
                title="%s  %s" % (pid, record["Cell_Key"]),
                subtitle="%s: span %s px between columns %s and %s, over %s"
                         % (_s(record.get("Value_Method")),
                            _s(record.get("Value_Span_Px")),
                            _s(record.get("Value_Support_Left_Px")),
                            _s(record.get("Value_Support_Right_Px")),
                            _s(record.get("Occlusion_Cause")) or "nothing this "
                            "reader removed"))
            if drawn:
                crops[record["Cell_Key"]] = drawn
    return PanelOutcome("AUTO_PASS", values=records, raw=raw_path, project=project,
                        overlay=overlay, inference_crops=crops,
                        artifacts=_panel_artifacts(raw_marks=[raw_path],
                                                   project=project, overlay=overlay),
                        declared=declared, read=len(records),
                        with_dispersion=with_disp, missing=missing,
                        detail="; ".join(
                            part for part in
                            (("" if not missing else
                              "%d of %d declared cells were not resolved"
                              % (len(missing), declared)), contested_note)
                            if part))


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


#: A BAR_MONO value's identity provenance, and what each column may hold. The
#: gate in `grid_engine` checks these against each other and cannot REQUIRE
#: them: the values file carries no mark type, and a line panel's rows
#: legitimately say nothing about fills. So the requirement lives here, where
#: `Run_Panel_ID` and the panel manifest are both in hand.
IDENTITY_PROVENANCE_COLUMNS = ("Geometry_Row_SHA256", "Resolved_Fill_Pattern",
                               "Identity_Source", "Identity_Evidence_Type")

#: Every column only a monochrome bar's value can legitimately carry. Their
#: presence on a row bound to any other mark type is a value that has been moved.
MONO_PROVENANCE_COLUMNS = IDENTITY_PROVENANCE_COLUMNS + ("Auto_Fill_Pattern",
                                                        "Resolution_ID")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def geometry_index(records):
    """{(Panel_ID, Geometry_Row_SHA256): [row]} for the foreign-key check.

    Takes geometry RECORDS or the rows of `mono_bar_geometry.csv` - the field
    names differ, so both spellings are read - which is what lets the check be
    re-run from the files a run leaves behind. `Group_ID` is kept as well as the
    numbers: a value can cite the right measurement, carry its mean and its
    dispersion, and still be filed under a different timepoint, and the group is
    the only thing that says which one it belongs to.
    """
    out = {}
    for rec in (records or ()):
        pid = _s(rec.get("Panel_ID") if rec.get("Panel_ID") is not None
                 else rec.get("figure"))
        digest = _s(rec.get("Geometry_Row_SHA256")
                    or rec.get("geometry_row_sha256")).lower()
        if not pid or not digest:
            continue
        mean = rec.get("Mean") if "Mean" in rec else rec.get("value")
        disp = (rec.get("Dispersion_Value") if "Dispersion_Value" in rec
                else rec.get("dispersion"))
        auto = (rec.get("Auto_Fill_Pattern") if "Auto_Fill_Pattern" in rec
                else rec.get("resolved_fill_pattern"))
        group = rec.get("Group_ID") if "Group_ID" in rec else rec.get("group")
        slot = (rec.get("Geometry_Slot") if "Geometry_Slot" in rec
                else rec.get("slot"))
        # Both identifiers, so the caller can hold the artifact to the panel
        # manifest. They were ONE field until the domain was split out, so the
        # `Figure_ID` column carried whichever of the two the reader had been
        # handed and nothing could tell.
        out.setdefault((pid, digest), []).append(
            dict(Mean=mean, Dispersion_Value=disp,
                 Auto_Fill_Pattern=_upper(auto), Group_ID=_s(group),
                 Geometry_Slot=_s(slot),
                 Figure_ID=_s(rec.get("Figure_ID")
                              if "Figure_ID" in rec else rec.get("figure_id")),
                 Identity_Domain_ID=_s(
                     rec.get("Identity_Domain_ID")
                     if "Identity_Domain_ID" in rec
                     else rec.get("identity_domain_id"))))
    return out


def geometry_index_from_run(output_dir):
    """The index, built from the file the run wrote and read back to verify.

    Not from the records still in memory. Nothing today edits a record after the
    artifact is written, but if anything ever does, an index built from memory
    compares the edited numbers with themselves and the check passes while
    `mono_bar_geometry.csv` - the thing a reviewer opens and the finalizer
    re-hashes - says something else. The durable file is the one the value has
    to agree with.
    """
    path = os.path.join(output_dir, "mono_bar_geometry.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return geometry_index(list(csv.DictReader(fh)))


def resolution_index(rows_by_panel):
    """{(Panel_ID, Resolution_ID): row} for the human half of the foreign key.

    A `Resolution_ID` on a value that is only checked for being non-blank is a
    label, not a reference: swap two of a panel's resolutions on their values and
    every other check still passes - the numbers are right, the hash is right,
    the fill is right - while the accepted file cites the wrong evidence, the
    wrong reviewer and the wrong reading.
    """
    out = {}
    for pid, rows in (rows_by_panel or {}).items():
        for row in rows:
            rid = _s(row.get("Resolution_ID"))
            if rid:
                out[(_s(pid), rid)] = row
    return out


def _as_number(value):
    try:
        return float(_s(value))
    except (TypeError, ValueError):
        return None


def identity_provenance_problems(values, panel_index, geometry=None,
                                resolutions=None):
    """[(where, check, detail)] for values whose provenance does not hold up.

    Two things the grid gate cannot do.

    IT CANNOT REQUIRE the identity columns. Its own identity block only fires
    when one of them is filled, which is right for a file that cannot know what
    drew the panel - a line panel's rows say nothing about fills, quite
    legitimately - and wrong as the only defence: delete the six columns from a
    monochrome value and the mean and the SE are still fine, the gate says
    nothing, and the value is reviewable and poolable with no way to ask which
    bar it came from or who decided which series it was.

    AND IT CANNOT FOLLOW `Geometry_Row_SHA256` anywhere. Checking that it looks
    like a SHA-256 establishes that the value carries sixty-four hex characters,
    not that it came from that measurement: a fabricated digest, or another
    bar's real one, passes a format check exactly as well. With `geometry` -
    `{(Panel_ID, hash): [row]}` from `geometry_index` - the column becomes a
    foreign key, and the mean, the dispersion and the measured fill are compared
    against the row it names.

    The PANEL BINDING is checked first, for every value and not only the
    monochrome ones, because it is what decides which rules apply. A row whose
    `Run_Panel_ID` names a colour panel is skipped by the identity rules and is
    then selected by the finalizer under that panel's approval - so a mis-stamped
    row would be reviewed as somebody else's panel and pooled.

    `panel_index` is `{Panel_ID: {"Mark_Type": ..., "Unit_ID": ...}}`. Every
    input comes from a file the run writes, so this can be re-run from
    `figure_values_raw.csv`, `run_manifest.csv` and `mono_bar_geometry.csv`.
    """
    out = []
    rows = (values.to_dict("records") if hasattr(values, "to_dict") else
            list(values))
    geometry = dict(geometry or {})
    claimed = {}
    for i, row in enumerate(rows):
        pid = _s(row.get("Run_Panel_ID"))
        where = "values:%d" % (i + 2)
        if not pid:
            out.append((where, "IDENTITY_PANEL_BINDING_MISSING",
                        "this value names no Run_Panel_ID, so nothing says "
                        "which panel produced it - and the reader's rules, the "
                        "review it is approved under and the raster it came "
                        "from are all properties of that panel"))
            continue
        if pid not in panel_index:
            out.append((where, "IDENTITY_PANEL_BINDING_UNKNOWN",
                        "Run_Panel_ID=%s is not a declared panel" % pid))
            continue
        panel = panel_index[pid]
        want_unit = _s(panel.get("Unit_ID"))
        got_unit = _s(row.get("Unit_ID"))
        if not want_unit:
            # A panel without a declared unit cannot bind anything, and the
            # manifest layer requires one - so reaching here means the caller's
            # index was built from something other than a validated manifest.
            out.append((where, "IDENTITY_PANEL_DECLARATION_INCOMPLETE",
                        "Run_Panel_ID=%s declares no Unit_ID, so there is "
                        "nothing to bind this value to" % pid))
            continue
        if got_unit != want_unit:
            # Blank counts, exactly as it does for Source_Panel_ID. The runner's
            # grid gate stops a blank Unit_ID in a normal run, but this check
            # exists for runs it did not make, where trusting an earlier gate is
            # the assumption being tested - and the finalizer selects values by
            # Run_Panel_ID alone, so a unit-less row under an approved panel
            # would be accepted.
            out.append((where, "IDENTITY_PANEL_BINDING_CONTRADICTS_UNIT",
                        "this value is Unit_ID=%s and Run_Panel_ID=%s reads "
                        "Unit_ID=%s; one of the two is somebody else's"
                        % (got_unit or "blank", pid, want_unit)))
            continue
        want_source = _s(panel.get("Source_Panel_ID"))
        got_source = _s(row.get("Source_Panel_ID"))
        if not want_source:
            # The declaration's own half, as for Unit_ID. The manifest layer
            # requires it, so a panel index without one was not built from a
            # validated manifest - and this check exists for runs whose
            # manifest layer is the thing in question.
            out.append((where, "IDENTITY_PANEL_DECLARATION_INCOMPLETE",
                        "Run_Panel_ID=%s declares no Source_Panel_ID, so this "
                        "value is not bound to a physical panel" % pid))
            continue
        if got_source != want_source:
            # Blank counts. `got_source and ...` let a DELETED Source_Panel_ID
            # through, and that column is the physical panel in the publisher's
            # figure - the link between a number and the thing a person can put
            # a finger on. Its own code, too: "filed under the wrong physical
            # panel" is not the unit disagreeing.
            out.append((where, "IDENTITY_PANEL_BINDING_CONTRADICTS_SOURCE",
                        "this value is Source_Panel_ID=%s and Run_Panel_ID=%s "
                        "was declared against %s"
                        % (got_source or "blank", pid, want_source)))
            continue
        mark = _upper(panel.get("Mark_Type"))
        if mark != "BAR_MONO":
            # A monochrome value re-stamped onto a panel of the SAME UNIT - which
            # this package allows several panels to build - passed the unit check
            # and then skipped every identity rule because the panel it now names
            # is a line panel. Nothing else looks at the combination, so the
            # provenance columns themselves are the evidence: only a monochrome
            # bar has them, so their presence on a colour panel's row is a value
            # that has been moved.
            moved = [c for c in MONO_PROVENANCE_COLUMNS if _s(row.get(c))]
            if moved:
                out.append((where,
                            "IDENTITY_PANEL_BINDING_CONTRADICTS_MARK_TYPE",
                            "this value carries %s and Run_Panel_ID=%s is "
                            "Mark_Type=%s; a fill identity is a BAR_MONO fact"
                            % (", ".join(moved), pid, mark or "(blank)")))
            continue
        absent = [c for c in IDENTITY_PROVENANCE_COLUMNS if not _s(row.get(c))]
        if absent:
            out.append((where, "IDENTITY_PROVENANCE_MISSING",
                        "%s is a BAR_MONO value and carries no %s. A "
                        "monochrome bar is identified BY ITS FILL, so which "
                        "series this number belongs to is a claim of its own "
                        "and has to travel with it" % (pid, ", ".join(absent))))
            continue
        digest = _s(row.get("Geometry_Row_SHA256"))
        if not _HEX64.match(digest):
            out.append((where, "IDENTITY_PROVENANCE_MISSING",
                        "Geometry_Row_SHA256=%r is not a SHA-256; it is what "
                        "binds this value to the anonymous row it was measured "
                        "from" % digest))
        resolved = _upper(row.get("Resolved_Fill_Pattern"))
        if resolved not in MONO_GEOMETRY.FILL_VOCABULARY:
            out.append((where, "IDENTITY_PROVENANCE_MISSING",
                        "Resolved_Fill_Pattern=%r is not a fill this reader "
                        "distinguishes (%s)"
                        % (resolved, "/".join(MONO_GEOMETRY.FILL_VOCABULARY))))
        source = _upper(row.get("Identity_Source"))
        evidence = _upper(row.get("Identity_Evidence_Type"))
        resolution = _s(row.get("Resolution_ID"))
        auto = _upper(row.get("Auto_Fill_Pattern"))
        if source == "AUTO":
            if evidence not in BM.AUTO_IDENTITY_EVIDENCE:
                out.append((where, "IDENTITY_SOURCE_INCONSISTENT",
                            "Identity_Source=AUTO with "
                            "Identity_Evidence_Type=%s" % (evidence or "blank")))
            if resolution:
                out.append((where, "IDENTITY_SOURCE_INCONSISTENT",
                            "Identity_Source=AUTO carries Resolution_ID=%s"
                            % resolution))
            if auto != resolved:
                # The reader measured one fill and the row was filed under
                # another. Nothing else in the chain compares the two, so a
                # mis-join between the geometry rows and the series manifest
                # would arrive as a correct-looking value under the wrong
                # series heading.
                out.append((where, "IDENTITY_FILL_MISMATCH",
                            "Auto_Fill_Pattern=%s but Resolved_Fill_Pattern=%s; "
                            "for an automatic identity they are the same fact"
                            % (auto or "blank", resolved)))
        elif source == "HUMAN":
            if evidence not in BM.HUMAN_IDENTITY_EVIDENCE:
                out.append((where, "IDENTITY_SOURCE_INCONSISTENT",
                            "Identity_Source=HUMAN with "
                            "Identity_Evidence_Type=%s" % (evidence or "blank")))
            if not resolution:
                out.append((where, "IDENTITY_RESOLUTION_UNIDENTIFIED",
                            "Identity_Source=HUMAN with no Resolution_ID"))
            if auto:
                out.append((where, "IDENTITY_OVERRODE_MEASUREMENT",
                            "Auto_Fill_Pattern=%s beside a human identity"
                            % auto))
        else:
            out.append((where, "IDENTITY_PROVENANCE_MISSING",
                        "Identity_Source=%r (expected %s)"
                        % (source, "/".join(K.FIG_IDENTITY_SOURCES))))
        if not geometry:
            # The same strictness the cell map gets. A caller that does not hand
            # over the measurements is not entitled to a pass on the checks they
            # would make, and `geometry` quietly disabling the foreign key is
            # exactly the refactor this would otherwise survive.
            out.append((where, "IDENTITY_GEOMETRY_INDEX_MISSING",
                        "%s is a BAR_MONO value and no geometry was supplied "
                        "(an absent mono_bar_geometry.csv reads the same way), "
                        "so the measurement it names cannot be looked up" % pid))
            continue
        # The column as a FOREIGN KEY. Without this the chain guaranteed that
        # the geometry file is internally valid and that the value carries
        # something hash-shaped - not that this mean came out of that row.
        found = geometry.get((pid, digest.lower()))
        if not found:
            out.append((where, "IDENTITY_GEOMETRY_ROW_UNKNOWN",
                        "Geometry_Row_SHA256=%s... names no row of %s in "
                        "mono_bar_geometry.csv" % (digest[:16], pid)))
            continue
        if len(found) > 1:
            out.append((where, "IDENTITY_GEOMETRY_ROW_UNKNOWN",
                        "Geometry_Row_SHA256=%s... matches %d rows of %s; a "
                        "measurement hash names one bar"
                        % (digest[:16], len(found), pid)))
            continue
        seen_at = claimed.setdefault((pid, digest.lower()), where)
        if seen_at != where:
            # Two values off one bar. The likeliest way to get here is a hash
            # copied from another row whose numbers happen to agree, which the
            # comparisons below cannot see.
            out.append((where, "IDENTITY_GEOMETRY_ROW_REUSED",
                        "%s already claims measurement %s... of %s; one bar is "
                        "one value" % (seen_at, digest[:16], pid)))
            continue
        measured = found[0]
        # The artifact's own identifiers, held to the panel manifest. The
        # geometry file is where a reviewer and the finalizer look up which
        # figure a measurement belongs to and which panels calibrated each
        # other's fills; a `Figure_ID` column that quietly holds the domain -
        # which is what it held while the reader took one identifier - makes
        # both of those answers wrong while every hash still recomputes.
        declared_panel = panel_index.get(pid) or {}
        for column, label in (("Figure_ID", "figure view"),
                              ("Identity_Domain_ID", "identity domain")):
            want = _s(declared_panel.get(column))
            got = _s(measured.get(column))
            if want and got and want != got:
                out.append((where, "IDENTITY_GEOMETRY_ROW_MISMATCH",
                            "measurement %s... says its %s is %s and panel %s "
                            "is declared as %s"
                            % (digest[:16], label, got, pid, want)))
        for column, label in (("Mean", "Mean"),
                              ("Dispersion_Value", "Dispersion_Value")):
            want_num = _as_number(measured.get(column))
            got_num = _as_number(row.get(column))
            if want_num is None and got_num is None:
                continue
            if (want_num is None) != (got_num is None) or \
                    abs(want_num - got_num) > 5e-4:
                out.append((where, "IDENTITY_GEOMETRY_ROW_MISMATCH",
                            "%s=%s and measurement %s... reads %s. The hash "
                            "says where this number came from; these are two "
                            "different numbers"
                            % (label, _s(row.get(column)) or "blank",
                               digest[:16],
                               _s(measured.get(column)) or "blank")))
        measured_fill = _upper(measured.get("Auto_Fill_Pattern"))
        if source == "AUTO" and measured_fill != resolved:
            out.append((where, "IDENTITY_GEOMETRY_ROW_MISMATCH",
                        "this value is filed under %s and measurement %s... "
                        "was read as %s"
                        % (resolved, digest[:16], measured_fill or "no fill")))
        if source == "HUMAN" and measured_fill:
            out.append((where, "IDENTITY_OVERRODE_MEASUREMENT",
                        "measurement %s... was read as %s, so this bar did not "
                        "need naming by hand"
                        % (digest[:16], measured_fill)))
        # THE CELL. Everything above ties the value to a measurement; nothing
        # above says the value is filed under the right heading. Two bars of one
        # panel, each citing its own row with its own mean and its own fill, and
        # their Cell_Keys exchanged: every check so far passes, the grid is
        # complete because both timepoints exist, and the two numbers are
        # swapped. The group the measurement came from is what decides the
        # position level, and the identity decides the series level.
        series_id = ""
        if source == "HUMAN":
            resolution_row = (resolutions or {}).get((pid, resolution))
            if resolution_row is None:
                # A `Resolution_ID` checked only for being non-blank is a label.
                # Swap two of a panel's resolutions on their values and the
                # numbers, the hash and the fill all still agree while the
                # accepted file cites the wrong evidence and the wrong reading.
                out.append((where, "IDENTITY_RESOLUTION_FOREIGN_KEY_MISMATCH",
                            "Resolution_ID=%s is not a resolution of %s"
                            % (resolution or "(blank)", pid)))
                continue
            for column, got_value in (("Geometry_Row_SHA256", digest.lower()),
                                      ("Resolved_Fill_Pattern", resolved),
                                      ("Evidence_Type", evidence)):
                want_value = _s(resolution_row.get(column))
                want_value = (want_value.lower()
                              if column == "Geometry_Row_SHA256"
                              else _upper(want_value))
                if want_value and want_value != got_value:
                    out.append(
                        (where, "IDENTITY_RESOLUTION_FOREIGN_KEY_MISMATCH",
                         "resolution %s reads %s=%s and this value says %s"
                         % (resolution, column, want_value or "blank",
                            got_value or "blank")))
            series_id = _s(resolution_row.get("Resolved_Series_ID"))
        cell_map = panel.get("Cell_Map")
        if not cell_map:
            # Fail closed. The mapping comes from the position and series
            # manifests, which the runner has in hand; a caller that does not
            # pass them is not entitled to a pass on the check they would make.
            out.append((where, "IDENTITY_CELL_MAP_MISSING",
                        "%s declares positions and series and none were "
                        "supplied, so the cell this value is filed under cannot "
                        "be checked against the bar it was measured from" % pid))
            continue
        levels = GE.fig_parse_cell_key(_s(row.get("Cell_Key"))) or {}
        group = _s(measured.get("Group_ID"))
        position_factor = _upper(cell_map.get("position_factor"))
        want_level = _s(cell_map.get("position_levels", {}).get(group))
        if position_factor and not want_level:
            # A map that is present and does not cover this row. Skipping it
            # silently is the same fail-open as having no map at all, one entry
            # further down.
            out.append((where, "IDENTITY_CELL_MAP_INCOMPLETE",
                        "measurement %s... is group %s and %s declares no "
                        "position with that ID" % (digest[:16], group, pid)))
        if position_factor and want_level:
            got_level = _s(levels.get(position_factor))
            if got_level.upper() != want_level.upper():
                out.append((where, "IDENTITY_GEOMETRY_CELL_MISMATCH",
                            "measurement %s... is group %s (%s=%s) and this "
                            "value is filed under %s=%s"
                            % (digest[:16], group, position_factor, want_level,
                               position_factor, got_level or "nothing")))
        series_factor = _upper(cell_map.get("series_factor"))
        if not series_id:
            series_id = _s(cell_map.get("series_by_fill", {}).get(resolved))
        want_series = _s(cell_map.get("series_levels", {}).get(series_id))
        if series_factor and not want_series:
            out.append((where, "IDENTITY_CELL_MAP_INCOMPLETE",
                        "this value's series is %s and %s declares no series "
                        "with that ID" % (series_id or "unknown", pid)))
        if series_factor and want_series:
            got_series = _s(levels.get(series_factor))
            if got_series.upper() != want_series.upper():
                out.append((where, "IDENTITY_GEOMETRY_CELL_MISMATCH",
                            "this value's series is %s (%s=%s) and it is filed "
                            "under %s=%s"
                            % (series_id, series_factor, want_series,
                               series_factor, got_series or "nothing")))
    return out


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


#: THE CONDITIONS A MARK WAS MEASURED UNDER. Inside `Mark_Record_SHA256`,
#: because a pixel is only a measurement relative to them - and therefore
#: re-derivable from the panel manifest and the run manifest, which is what makes
#: the hash checkable by somebody who did not produce the run.
MARK_ENVELOPE_FIELDS = ("Panel_ID", "Unit_ID", "Mark_Type", "Panel_Box",
                        "X_Calibration", "Y_Calibration", "Image_SHA256",
                        "Reader_Version",
                        # AND EVERYTHING ELSE THE RUN DECLARED about how this
                        # panel would be measured: the baseline, the reader
                        # options, the series discriminants, the position
                        # columns. Named fields are the conditions a pixel is
                        # relative to; this is the rest of the instruction.
                        "Measurement_Declaration_SHA256")


def _declared_rows(rows, key):
    """Rows as text, in a stable order: a declaration, not a frame."""
    out = []
    for row in rows or ():
        item = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        out.append({str(k): _s(v) for k, v in item.items()})
    return sorted(out, key=lambda r: (_s(r.get(key)), json.dumps(r, sort_keys=True)))


def measurement_declaration_sha256(panel, series_rows, position_rows,
                                   config_rows, image_sha256, reader_version):
    """Everything the run declared about HOW this panel would be measured.

    The panel box, the ticks and the raster hash were bound to the marks first,
    because those are the conditions a pixel is a measurement relative to. They
    are not all of them. `Baseline_Value` decides where a bar is measured from,
    the reader options decide the threshold and the tolerances, the series rows
    decide what counts as which series, and `X_Pixel` decides which column a
    position IS - and a producer could declare one set, read the figure under
    another, and hash the marks under the second with every check passing.

    WHOLE ROWS, not a curated subset. A list of the measurement-relevant columns
    is a list that drifts behind the manifests: a column added next year would be
    outside the digest by default, and nothing would say so. The manifests are
    hashed into the run stamp anyway, so an unrelated edit is already a refusal
    with a clearer name than this one would give.

    What this binds is the CLAIM: marks read under one declaration cannot be
    presented under another. It does not prove the producer obeyed its own
    declaration - nothing in an artifact can - and that is why the digest sits
    inside `Mark_Record_SHA256` rather than beside it.
    """
    return sha256_of_text(json.dumps({
        "panel": _declared_rows([panel], "Panel_ID")[0] if panel is not None
                 else {},
        "series": _declared_rows(series_rows, "Series_ID"),
        "positions": _declared_rows(position_rows, "Position_ID"),
        "reader_config": _declared_rows(config_rows, "Option"),
        "Image_SHA256": _s(image_sha256),
        "Reader_Version": _s(reader_version),
    }, sort_keys=True))


def mark_envelope_header(panel, image_sha256, reader_version, series_rows=(),
                         position_rows=(), config_rows=()):
    """The envelope a panel's marks must have been read under.

    ONE CONSTRUCTION, TWO CALLERS. `_read_panel` builds the envelope with this
    and `finalize_batch` re-derives it from the VERIFIED panel manifest and run
    manifest to compare - so a producer cannot read a figure under a calibration
    or a panel box nobody declared, hash its marks under those, and present a run
    where the marks, the values and both hashes agree with each other.

    Everything here comes from the panel row: the box is the four declared
    corners and the calibrations are fitted from the declared ticks, exactly as
    the reader fits them. `Image_SHA256` and `Reader_Version` are what the RUN
    recorded, because a run made by an older reader is a run this module still
    has to be able to check.
    """
    return {
        "Panel_ID": _s(panel.get("Panel_ID")),
        "Unit_ID": _s(panel.get("Unit_ID")),
        "Mark_Type": _upper(panel.get("Mark_Type")),
        "Panel_Box": list(BM.parse_box(",".join(
            _s(panel.get(c)) for c in
            ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")))),
        "X_Calibration": MR._calibration_record(_calibration(panel, "X")),
        "Y_Calibration": MR._calibration_record(_calibration(panel, "Y")),
        "Image_SHA256": _s(image_sha256),
        "Reader_Version": _s(reader_version),
        "Measurement_Declaration_SHA256": measurement_declaration_sha256(
            panel, series_rows, position_rows, config_rows, image_sha256,
            reader_version),
    }


#: Bumped to /2 in v7.72: every mark carries a measurement hash and an
#: attestation over the methods read off it, so a value row can be joined to the
#: mark it was made from and the join can be checked by somebody who did not make
#: either.
MARK_DATA_SCHEMA = "figure-digitization-triage/mark-data/3"

#: The fields a mark's METHODS are written in. Outside the measurement hash, for
#: the reason `mono_bar_geometry.UNHASHED_FIELDS` exists: how a measurement was
#: interpreted is a different claim from what was measured, and a hash that mixes
#: them cannot answer "is this the same mark" after an identity is resolved.
MARK_METHOD_FIELDS = tuple(PROV.METHOD_FIELDS)


def mark_record_sha256(mark, envelope):
    """WHAT WAS MEASURED: this mark's own geometry, under this calibration.

    The panel box, the calibration and the raster hash are in it because a pixel
    is only a measurement relative to them - the same reason `write_point_data`
    refuses to store a value without the pixel and the calibration that produced
    it.
    """
    material = {k: v for k, v in mark.items()
                if k not in MARK_METHOD_FIELDS
                and k not in ("Mark_Record_SHA256",
                              "Method_Attestation_SHA256")}
    return sha256_of_text(json.dumps(
        {"mark": material,
         "Panel_Box": envelope.get("Panel_Box"),
         "X_Calibration": envelope.get("X_Calibration"),
         "Y_Calibration": envelope.get("Y_Calibration"),
         "Image_SHA256": envelope.get("Image_SHA256"),
         "Panel_ID": envelope.get("Panel_ID"),
         # /3: and the rest of the instruction the panel was read under. A mark
         # measured under one baseline, threshold or series declaration is not
         # the same mark under another, and until it was in here the two hashed
         # identically.
         "Measurement_Declaration_SHA256":
             envelope.get("Measurement_Declaration_SHA256")},
        sort_keys=True, default=float))


def method_attestation_sha256(mark, record_sha):
    """HOW IT WAS READ: the three methods, bound to the measurement.

    Two hashes rather than one, exactly as `Geometry_Row_SHA256` and
    `Auto_Identity_SHA256` are two: an identity resolved later must not move the
    hash that answers "is this the same measurement", and a method swapped later
    must not hide behind one that does.
    """
    return sha256_of_text(json.dumps(
        dict({f: _s(mark.get(f)) for f in MARK_METHOD_FIELDS},
             Mark_Record_SHA256=record_sha), sort_keys=True))


def stamp_marks(marks, envelope):
    """Every mark with its two hashes, ready to be written and joined to."""
    out = []
    for mark in marks:
        record_sha = mark_record_sha256(mark, envelope)
        out.append(dict(mark, Mark_Record_SHA256=record_sha,
                        Method_Attestation_SHA256=method_attestation_sha256(
                            mark, record_sha)))
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
                     review_dir=None, box=None, routed=None, output_dir=None):
    """A scatter yields one association per series, each with its point file.

    `routed` is what `_routed_scatter` established, or None for a panel with one
    y axis. Where it is given, two things change and nothing else does: each
    series' point file is written under the calibration of ITS OWN axis rather
    than the panel's, and the panel leaves a `scatter_points.csv` carrying the
    eighteen measurements the routing rested on. Every gate below - the count
    audit, the printed association, the three-point floor, the all-or-nothing
    refusal - applies to both, because none of them is about how the series were
    told apart.
    """
    pid = _s(panel.get("Panel_ID"))
    unit_id = _s(panel.get("Unit_ID"))
    if statistic and statistic != "ASSOCIATION":
        return PanelOutcome("NOT_CONVERTIBLE", declared=declared,
                            detail="a scatter cannot become Statistic_Type=%s"
                                   % statistic)
    association = _upper(panel.get("Association_Type"))
    printed_association = None
    if _s(panel.get("Association_Value_Printed")):
        printed_association = float(_s(panel.get("Association_Value_Printed")))
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
        # HOW THE SERIES WAS NAMED, off the points themselves - the reader put it
        # on each one, and every point here belongs to this series. Read rather
        # than re-decided, so the value row and its point file cannot disagree
        # about what identified them.
        summary["Identity_Method"] = _s(mine[0].get("Identity_Method"))
        # And how the NUMBER was got, which is not how the points were got: each
        # point is a measured marker centre, and the association is a statistic
        # over the set of them.
        summary["Value_Method"] = "POINT_CLOUD_ASSOCIATION"
        # An association cell has no dispersion of its own: the confidence
        # interval, where the paper gives one, is transcribed rather than read.
        summary["Dispersion_Method"] = "NO_DISPERSION"
        # AND WHERE THE PAPER PRINTS THE ANSWER, IT IS CHECKED AGAINST IT. A
        # figure that says `r = 0.91` beside its cloud has declared the value
        # the point set has to produce, and a digitized set that does not is not
        # the study's - which the count cannot show. Publication 177 panel C
        # matches its declared 48 pairs EXACTLY and computes 0.25 against a
        # printed 0.17, because a count says how many marks were found and
        # nothing about where they are.
        if printed_association is not None:
            gap = abs(float(summary["Association_Value"]) - printed_association)
            if gap > MR.PRINTED_ASSOCIATION_TOLERANCE:
                disputed.append(
                    "%s: the source prints %s = %g and the digitized points give "
                    "%.4f, a gap of %.4f against a tolerance of %g"
                    % (sid, association or "the association", printed_association,
                       summary["Association_Value"], gap,
                       MR.PRINTED_ASSOCIATION_TOLERANCE))
                continue
        planned.append((sid, factor, level, mine, summary))

    # ---- every refusal, BEFORE a single file is written --------------------
    # A scatter panel is all or nothing. It used to write each planned series'
    # point file and then discover that another series was too sparse: the
    # panel returned MANUAL_POINT_READ carrying no values, no raw and no
    # artifacts, while the written file stayed in raw/ named by no ledger - and
    # the missing list held only the sparse series, so `manual_queue_cells.csv`
    # excluded the series whose numbers had just been thrown away. A hand
    # digitizer following the queue would never see it. Cells_Read said 1 and
    # `figure_values_raw.csv` had none.
    #
    # There is no channel for merging a partial automatic result with a later
    # hand reading, so a partial result is not a result. Every exit below
    # reports the WHOLE panel as unread.
    all_scatter_cells = sorted(_all_cells(series_level, {}))
    if disputed:
        # Not NOT_CONVERTIBLE: the marks are readable, they just do not add up
        # to a point set anybody can vouch for. That is a counting job for a
        # person.
        return PanelOutcome(
            "MANUAL_POINT_READ", declared=declared, read=0,
            detail="the detected points cannot be reconciled with the source, "
                   "so no association was computed - " + "; ".join(disputed),
            missing=all_scatter_cells)
    if short and planned:
        return PanelOutcome(
            "MANUAL_POINT_READ", declared=declared, read=0,
            detail="some series were too sparse to summarize, so the panel is "
                   "read by hand as a whole rather than half automatically: "
                   + "; ".join(short),
            missing=all_scatter_cells)
    if not planned:
        return PanelOutcome(
            "NOT_CONVERTIBLE", declared=declared, read=0,
            detail="no series reached three points: " + "; ".join(short),
            missing=all_scatter_cells)

    # EACH SERIES ON ITS OWN SCALE, where the panel has more than one. The point
    # writer re-derives every value from its own pixel before it writes, so
    # handing it the panel's single calibration for a twin-axis panel would not
    # write a wrong file - it would refuse to write at all, which is the right
    # failure and the wrong place for it.
    cal_of = {}
    if routed:
        import axis_grain as AG
        cals = AG.calibrations(routed["axes"])
        axis_of, _refused = AG.series_axis(routed["series"], routed["axes"],
                                           panel_id=pid)
        cal_of = {sid: cals[axis] for sid, axis in axis_of.items()}
        xcal = cals[routed["x_axis_id"]]
    records, raw_files = [], []
    for sid, factor, level, mine, summary in planned:
        cell_key = GE.fig_cell_key({factor: level})
        path = os.path.join(raw_dir, "%s_%s_points.json" % (pid, sid))
        MR.write_point_data(mine, path, unit_id=unit_id, cell_key=cell_key,
                            source_image=image_path, image_sha256=sha,
                            x_calibration=xcal,
                            y_calibration=cal_of.get(sid, ycal),
                            panel_id=pid, reader="SCATTER")
        raw_files.append(path)
        made = MR.to_value_records(
            [summary], "ASSOCIATION", unit_id,
            cell_levels={factor: level}, point_data_reference=path)
        # THE RESIDUAL OF THE CALIBRATION THIS SERIES WAS READ UNDER, set here
        # where `sid` is in scope. Set in the loop below instead, it came off
        # the panel's single `ycal` for every series - so a right-hand series
        # carried the left-hand ladder's residual, which is exactly the
        # confusion the axis grain exists to end.
        cal = cal_of.get(sid)
        if cal is not None:
            for record in made:
                record["Calibration_Max_Residual"] = float(
                    getattr(cal, "max_residual", 0.0))
        records.extend(made)
    if ycal is not None:
        for record in records:
            record.setdefault("Calibration_Max_Residual",
                              float(getattr(ycal, "max_residual", 0.0)))
    # THE PANEL'S OWN ROUTED-POINT FILE, written once, read back and verified
    # before anybody is asked to look at the overlay. `write_point_data` records
    # a cloud; this records how each mark's SERIES was decided - eighteen
    # measurements, two thresholds and the margin this mark cleared them by -
    # which is the evidence the finalizer holds a routed value's identity route
    # against.
    point_artifact = None
    candidate_artifact = group_artifact = None
    if routed and output_dir:
        import scatter_points as SP
        # THE TWO GRAINS FIRST, because the point file cites them. Each is
        # appended to across a run's panels exactly as the point file is, and
        # each is read back and verified before this panel is allowed to pass.
        for name, columns, made in (
                ("scatter_marker_candidates.csv", SP.CANDIDATE_COLUMNS,
                 routed["meta"].get("candidate_rows") or []),
                ("scatter_fill_groups.csv", SP.GROUP_COLUMNS,
                 routed["meta"].get("group_rows") or [])):
            path = os.path.join(output_dir, name)
            prior = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    prior = list(csv.DictReader(fh))
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(columns))
                w.writeheader()
                w.writerows(prior + [{k: ("" if r.get(k) is None else r[k])
                                      for k in columns} for r in made])
            if name.startswith("scatter_marker"):
                candidate_artifact = path
            else:
                group_artifact = path
        with open(candidate_artifact, encoding="utf-8") as fh:
            cands_back = [r for r in csv.DictReader(fh)
                          if _s(r.get("Panel_ID")) == pid]
        with open(group_artifact, encoding="utf-8") as fh:
            groups_back = [r for r in csv.DictReader(fh)
                           if _s(r.get("Panel_ID")) == pid]
        bad = (SP.verify_candidates(cands_back)
               + SP.verify_groups(groups_back, cands_back))
        if bad:
            raise InternalReaderError(
                "the routed scatter's candidate and group files do not verify "
                "for panel %s: %s" % (pid, "; ".join(bad[:3])))
        point_artifact = os.path.join(output_dir, "scatter_points.csv")
        rows_out = SP.artifact_rows(
            [p for _s_, _f_, _l_, mine, _sum_ in planned for p in mine])
        existing = []
        if os.path.exists(point_artifact):
            with open(point_artifact, encoding="utf-8") as fh:
                existing = list(csv.DictReader(fh))
        with open(point_artifact, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh,
                                    fieldnames=list(SP.POINT_ARTIFACT_COLUMNS))
            writer.writeheader()
            writer.writerows(existing + rows_out)
        with open(point_artifact, encoding="utf-8") as fh:
            back = [r for r in csv.DictReader(fh)
                    if _s(r.get("Panel_ID")) == pid]
        bad = (SP.verify_artifact(back, routed["series"], routed["axes"], pid,
                                  sha)
               + SP.verify_citations(back, cands_back, groups_back))
        if bad:
            raise InternalReaderError(
                "scatter_points.csv does not verify for panel %s: %s"
                % (pid, "; ".join(bad[:3])))
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
                                                   overlay=overlay)
                        + ([(SP_CANDIDATE_TYPE, candidate_artifact),
                            (SP_GROUP_TYPE, group_artifact)]
                           if candidate_artifact else [])
                        + ([(SP_ARTIFACT_TYPE, point_artifact)]
                           if point_artifact else []),
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
    # The cells whose numbers a model made. A previous run's copy left beside
    # this run's values is a work list for measurements that no longer exist.
    "method_blocked_cells.csv",
    # The BAR_MONO geometry bundle. Left behind, a previous run's panel
    # picture sits beside this run's numbers and passes the writer's existence
    # check, so an approval could be given against a picture of a different
    # measurement.
    "mono_bar_geometry.csv",
    # THE ROUTED SCATTER'S POINT FILE. Same reason as the geometry file above: a
    # stale one beside fresh values passes every existence check there is.
    "scatter_points.csv",
    # And the two grains beneath it, for the same reason.
    "scatter_marker_candidates.csv", "scatter_fill_groups.csv",
    "source_panel_coverage.csv",
)
CANONICAL_DIRS = ("raw", "projects", "review", "geometry-review",
                  # A previous run's list of reconstructed cells left beside this
                  # run's numbers is a list of questions about measurements that
                  # no longer exist, sitting where the finalizer looks for this
                  # run's.
                  "inference-review")
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


def withdraw_commit(output_dir, run_date, detail, run_mode="ATTESTED",
                    document_bytes_bound="NO_DOCUMENTS"):
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
                run_date, run_mode=run_mode, detail=detail,
                document_bytes_bound=document_bytes_bound)


#: Every verdict a run directory can carry. RAN is the only one under which
#: `figure_values_accepted.csv` may exist.
RUN_STATUSES = ("RAN", "MANIFEST_REJECTED", "INPUT_LOAD_FAILED",
                "PROMOTE_FAILED", "DEMO_OUTPUT_REFUSED",
                "GEOMETRY_REVIEW_FAILED", "INTERNAL_ERROR")


def write_stamp(path, status, run_date, cfg_hash="", manifest_hashes=None,
                panels=0, read=0, accepted=0, machine_qc=0, qc_problems=0,
                problems=0, detail="", run_mode="ATTESTED",
                output_sha256=None, reviewer_registry_sha256="",
                manifest_dir="", method_blocked=0, gate_passed=None,
                document_bytes_bound="NO_DOCUMENTS"):
    """The run's verdict, written on EVERY outcome including a rejection.

    A rejected run used to write no stamp at all, which left the previous run's
    stamp in place claiming `Values_Accepted=8`. A stamp that is absent when
    things go wrong is worse than no stamp at all - it is only ever there to
    reassure.

    `gate_passed` defaults to `machine_qc` because on a run that kept its
    results the two ARE the same number, and a caller that has only one of them
    has that one. They come apart on a refusal, which is the whole reason the
    second field exists.
    """
    if gate_passed is None:
        gate_passed = machine_qc
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "figure-digitization-triage/run-stamp/8",
            "Status": status, "Run_Mode": run_mode, "Run_Date": run_date,
            # WHAT THE INVENTORY RESTS ON. ALL, PARTIAL, NONE or NO_DOCUMENTS,
            # from `Source_File_SHA256` (v9.2). Every raster in this package has
            # been hashed since the first release and the article they were cut
            # out of was a filename, so a stamp that says nothing about the
            # document reads as though the document were covered too.
            "Source_Document_Bytes_Bound": document_bytes_bound,
            # How many of the values this run produced no signature will be able
            # to finalize, and which are therefore already somebody's work in
            # `method_blocked_cells.csv`. On the RUN stamp because that is where
            # a person looks before spending an afternoon reviewing: a panel
            # whose numbers a model made is worth knowing about first.
            "Values_Method_Blocked": method_blocked,
            "Reader_Version": MR.READER_VERSION,
            "Pipeline_Version": PIPELINE_VERSION,
            "Pipeline_Code_SHA256": pipeline_code_sha256(),
            "Environment": environment_record(),
            "Config_SHA256": cfg_hash,
            "Manifest_SHA256": manifest_hashes or {},
            "Panels": panels, "Values_Read": read,
            # TWO TALLIES, BECAUSE A REFUSAL SEPARATES THEM.
            # `Values_Machine_QC_Passed` is how many gate-passing values this
            # run KEPT, and a refusal keeps none - so on `DEMO_OUTPUT_REFUSED`
            # it is 0, correctly. `Values_Gate_Passed` is the GATE's own tally:
            # how many values cleared machine QC before anything decided what to
            # do with them. Until v9.2 only the first field existed, so the one
            # number that says how much work a refused run actually did survived
            # in the `Detail` sentence and nowhere a program could read it -
            # `test_compile_plan` had to parse the prose to assert 102.
            "Values_Gate_Passed": gate_passed,
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
        resolutions=m.get("resolutions"), axes=m.get("axes"),
        requested_run_mode=requested_run_mode,
        file_root=file_root,
        check_files=check_files)
    # Derived even when the batch is rejected, so the stamp on a failed run
    # still says which kind of run it would have been.
    derived = BM.derive_run_mode(m["reviewers"], m["source_documents"],
                                 m["source_figures"])
    run_mode = ("DEMO_ONLY" if "DEMO_ONLY" in (derived, requested_run_mode)
                else "ATTESTED")
    # Read off the manifests rather than passed in, and read even when the batch
    # is rejected: a run refused for one bad column still says what its
    # inventory would have rested on.
    bytes_bound = BM.document_bytes_bound(m["source_documents"])
    if len(problems):
        problems.to_csv(os.path.join(output_dir, "manifest_problems.csv"),
                        index=False)
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "MANIFEST_REJECTED", run_date, run_mode=run_mode,
                    manifest_dir=os.path.realpath(manifest_dir),
                    document_bytes_bound=bytes_bound,
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
    # Where the per-cell pictures and the per-panel lists of reconstructed cells
    # both live. Made unconditionally, like `review/`: a run with none of them
    # leaves it empty rather than making its absence mean two things.
    inference_dir = os.path.join(output_dir, "inference-review")
    os.makedirs(inference_dir, exist_ok=True)
    # Module state, cleared per run. An agent working through 116 publications
    # in one process would otherwise carry every previous run's drawing
    # failures into this run's stamp, naming panels this run never saw.
    OVERLAY.reset_failures()

    options_by_config = BM.load_reader_configs(
        m["configs"],
        {_s(r.get("Config_ID")): {_upper(r.get("Mark_Type"))}
         for _, r in m["panels"].iterrows() if not BM.blank(r.get("Config_ID"))},
        lambda *a: None)
    cfg_hash = BM.config_hash(m["configs"])
    units_by_id = {_s(u.get("Unit_ID")): u for _, u in m["units"].iterrows()}

    series_by_panel, positions_by_panel, axes_by_panel = {}, {}, {}
    for _, r in m["series"].iterrows():
        series_by_panel.setdefault(_s(r.get("Panel_ID")), []).append(r)
    for _, r in m["positions"].iterrows():
        positions_by_panel.setdefault(_s(r.get("Panel_ID")), []).append(r)
    for _, r in m.get("axes", pd.DataFrame()).iterrows():
        axes_by_panel.setdefault(_s(r.get("Panel_ID")), []).append(r)

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
    crops_by_panel = {}
    artifacts_by_panel = {}
    # ---- the geometry pass, BEFORE the panel loop.
    #
    # Identity is figure-local and geometry is panel-local, so a loop that
    # reads a panel and names its series in the same step can only name them
    # from what one panel holds. Every BAR_MONO panel of the batch is measured
    # here with no series named, the rows are grouped by Figure_ID, and the
    # FIGURE says what its fills mean; the loop below reads its values out of
    # the answer.
    geometry_rows_by_panel, geometry_pairs, geometry_refusals = (
        measure_bar_mono_figures(
            [row for _, row in m["panels"].iterrows()], positions_by_panel,
            series_by_panel, options_by_config, file_root=file_root))
    resolutions_by_panel = {}
    for _, row in m.get("resolutions", pd.DataFrame()).iterrows():
        resolutions_by_panel.setdefault(_s(row.get("Panel_ID")), []).append(row)
    geometry_artifacts = {}
    if geometry_pairs:
        try:
            # Into the run directory, like `raw/`, `projects/` and `review/`.
            # Written into staging instead, the ledger records
            # `.staging/mono_bar_geometry.csv` and the promotion moves the file
            # out from under that path.
            geometry_artifacts = write_geometry_review(output_dir,
                                                       geometry_pairs)
            # Beside the geometry bundle, and only for the panels that have
            # them. Written even if the join then refuses the panel: the ledger
            # records what this run wrote, and a refused resolution is exactly
            # the thing somebody needs to open. Inside this `try`, because the
            # evidence copy can refuse too - and a review bundle whose evidence
            # is not in it is not a reviewable bundle.
            for pid_, artifacts_ in write_identity_resolutions(
                    output_dir,
                    {p: r for p, r in resolutions_by_panel.items()
                     if p in geometry_artifacts},
                    file_root=file_root).items():
                geometry_artifacts[pid_] = (geometry_artifacts.get(pid_, [])
                                            + artifacts_)
        except GeometryReviewError as exc:
            # Not a panel outcome: the bundle is written once for the run, so a
            # failure here is every BAR_MONO panel at once and there is nothing
            # partial to queue.
            clear_outputs(output_dir)
            write_stamp(os.path.join(output_dir, "run_stamp.json"),
                        "GEOMETRY_REVIEW_FAILED", run_date, run_mode=run_mode,
                        document_bytes_bound=bytes_bound,
                        manifest_hashes=manifest_hashes, detail="%s" % exc)
            return dict(status="GEOMETRY_REVIEW_FAILED", detail="%s" % exc,
                        panels=0, values=0, machine_qc=0, accepted=0,
                        problems=0)
    config_rows_by_id = {}
    for _, row in m["configs"].iterrows():
        config_rows_by_id.setdefault(_s(row.get("Config_ID")), []).append(row)
    for _, panel in m["panels"].iterrows():
        pid = _s(panel.get("Panel_ID"))
        unit = units_by_id.get(_s(panel.get("Unit_ID")))
        options = options_by_config.get(_s(panel.get("Config_ID")), {})
        # THE READER'S PANEL-NOTE CHANNEL, CLEARED HERE FOR EVERY PANEL. It was
        # cleared inside the LINE_MONO_STYLE dispatch, which is only reached once
        # the box parses and the raster opens: a line panel whose geometry
        # refuses would then have been folded the PREVIOUS panel's diagnosis,
        # over 116 publications, with nothing to say it was not its own.
        LINE_STYLE.reset_panel_notes()
        try:
            outcome = run_panel(
                panel, series_by_panel.get(pid, []),
                positions_by_panel.get(pid, []), options, unit,
                raw_dir, file_root=file_root, project_dir=project_dir,
                config_rows=config_rows_by_id.get(
                    _s(panel.get("Config_ID")), []),
                review_dir=review_dir,
                geometry=geometry_rows_by_panel.get(pid),
                geometry_refusal=geometry_refusals.get(pid),
                resolutions=resolutions_by_panel.get(pid, ()),
                inference_dir=inference_dir,
                axis_rows=axes_by_panel.get(pid, ()),
                output_dir=output_dir)
        except InternalReaderError as exc:
            # The whole batch stops. A defect in a reader is not confined to the
            # panel that happened to trip it, and 115 more publications read by
            # the same broken code is a worse outcome than a loud halt.
            clear_outputs(output_dir)
            write_stamp(os.path.join(output_dir, "run_stamp.json"),
                        "INTERNAL_ERROR", run_date, run_mode=run_mode,
                        document_bytes_bound=bytes_bound,
                        manifest_hashes=manifest_hashes,
                        detail="%s" % exc)
            raise
        # WHAT THE READER SAID ABOUT THE PANEL, ON EVERY EXIT AND NOT ONLY ON
        # SILENCE. v9.14 folded these notes in the `if not rows` branch alone,
        # which is the defect v9.15 fixes one level down: the panel that made the
        # refusal necessary emitted eight cells and looked healthy. A note about
        # cells that were refused belongs on the outcome that emitted the others.
        _notes = LINE_STYLE.panel_notes()
        if _notes:
            outcome.detail = "; ".join(
                ([outcome.detail] if outcome.detail else []) + _notes)
        overlays_by_panel[pid] = (_run_relative(outcome.overlay, output_dir)
                                  if outcome.overlay else "")
        if outcome.inference_crops:
            crops_by_panel[pid] = outcome.inference_crops
        if outcome.project:
            projects_by_panel[pid] = _run_relative(outcome.project, output_dir)
        # Hashed the moment they are written, before anything else touches the
        # directory - so what the manifest records is what the run produced.
        #
        # Recorded RELATIVE to the output directory. An absolute path breaks
        # when the run directory is moved or copied; a bare relative one breaks
        # when the finalizer is launched from a different working directory,
        # which is the normal case for a scheduler or an agent. Either way the
        # finalizer reports RUN_ARTIFACT_MODIFIED for a file that is sitting
        # right there - safe, but a false refusal nobody can act on.
        # Producers hand over (TYPE, path) or (TYPE, path, reference); the
        # reference is blank for everything that stands on its own.
        artifacts_by_panel[pid] = [
            (item[0], _run_relative(item[1], output_dir),
             file_sha256_or_blank(item[1]),
             _s(item[2]) if len(item) > 2 else "")
            for item in (list(outcome.artifacts)
                         + geometry_artifacts.get(pid, []))]
        # Stamp the panel onto every value it produced. A unit is normally one
        # panel, but nothing forbids two panels feeding one - and keying panel
        # state by Unit_ID meant the LAST panel's state won, so a unit whose
        # first panel failed and whose second passed came out ACCEPTED. Each
        # value now carries where it came from and is judged on that.
        for record in outcome.values:
            record["Run_Panel_ID"] = pid
            record["Source_Panel_ID"] = _s(panel.get("Source_Panel_ID"))
            # Every path a value carries into the accepted file is recorded
            # relative to the run. They used to be absolute, so handing the
            # finished data to another folder or another machine left
            # `Point_Data_Reference` and `WPD_Project_File` pointing at a
            # directory that exists only on the machine the run happened on -
            # the provenance link is the whole reason those columns are there.
            for column in ("Point_Data_Reference", "WPD_Project_File"):
                if record.get(column):
                    record[column] = _run_relative(record[column], output_dir)
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
            "Raw_Data_File": ";".join(
                _run_relative(p, output_dir)
                for p in (outcome.raw or "").split(";") if p),
            "WPD_Project_File": (_run_relative(outcome.project, output_dir)
                                 if outcome.project else ""),
            "Run_Date": run_date,
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
    # Written unconditionally. Only the project column above is conditional -
    # but the WRITE used to sit inside that condition too, so a batch where
    # every panel was manual or unreadable produced no `figure_manifest.csv` at
    # all, while `CANONICAL_OUTPUTS` and the documentation both call it a run
    # output. The runs with nothing automatic in them are exactly the ones
    # somebody audits by hand.
    figures.to_csv(os.path.join(work_dir, "figure_manifest.csv"), index=False)

    qc = GE.fig_validate_bundle(figures, m["grids"], m["units"], values_df,
                                kernel=K, file_root=file_root,
                                # Outputs are recorded relative to the run, so
                                # the gate needs to know where the run is.
                                run_dir=output_dir,
                                check_files=check_files)
    # The mark-aware half of the identity contract, appended to the gate's own
    # problems so it blames the same units, lands in `qc_problems.csv`, and
    # flips the panel to QC_FAILED through the pass below. The gate cannot make
    # this check: the values file carries no mark type, and a line panel's rows
    # say nothing about fills quite legitimately.
    # `values`, not `values_df`: the frame is projected onto
    # `fig_values_columns()`, which does not include `Run_Panel_ID` - so the
    # frame cannot say which panel a row came from and this check would find
    # nothing on every row. The two are in the same order, so a `values:%d` from
    # here names the same line the gate would.
    _panel_provenance = {}
    for _, _panel_row in m["panels"].iterrows():
        _pid = _s(_panel_row.get("Panel_ID"))
        _series_rows = series_by_panel.get(_pid, [])
        _position_rows = positions_by_panel.get(_pid, [])
        _panel_provenance[_pid] = {
            "Mark_Type": _s(_panel_row.get("Mark_Type")),
            "Unit_ID": _s(_panel_row.get("Unit_ID")),
            "Source_Panel_ID": _s(_panel_row.get("Source_Panel_ID")),
            "Figure_ID": _s(_panel_row.get("Figure_ID")),
            "Identity_Domain_ID": _s(_panel_row.get("Identity_Domain_ID")),
            # What a cell of this panel is MADE of, so a value can be checked
            # against the bar it was measured from and not only against itself.
            "Cell_Map": {
                "position_factor": next(
                    (_upper(r.get("Factor_Name")) for r in _position_rows
                     if not BM.blank(r.get("Factor_Name"))), ""),
                "position_levels": {_s(r.get("Position_ID")):
                                    _s(r.get("Factor_Level"))
                                    for r in _position_rows},
                "series_factor": next(
                    (_upper(r.get("Factor_Name")) for r in _series_rows
                     if not BM.blank(r.get("Factor_Name"))), ""),
                "series_levels": {_s(r.get("Series_ID")):
                                  _s(r.get("Factor_Level"))
                                  for r in _series_rows},
                "series_by_fill": {_upper(r.get("Bar_Fill_Pattern")):
                                   _s(r.get("Series_ID"))
                                   for r in _series_rows
                                   if not BM.blank(r.get("Bar_Fill_Pattern"))},
            },
        }
    _identity_problems = identity_provenance_problems(
        values, _panel_provenance,
        # From the FILE, which has been written and read back and verified - not
        # from the records still in memory, which an edit after the write would
        # let compare against themselves.
        geometry=geometry_index_from_run(output_dir),
        resolutions=resolution_index(resolutions_by_panel))
    if _identity_problems:
        qc = pd.concat(
            [qc, pd.DataFrame([dict(where=w, check=c, detail=d)
                               for w, c, d in _identity_problems])],
            ignore_index=True) if len(qc) else pd.DataFrame(
                [dict(where=w, check=c, detail=d)
                 for w, c, d in _identity_problems])

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
            # APPENDED, not replaced. The gate says WHICH CHECK refused the
            # unit; the reader's own detail says what happened to the panel, and
            # the two are different halves of the same answer. Overwritten, a
            # panel whose marks two declared colours both claimed reported
            # `FACTORIAL_CELL_MISSING` and nothing about the colours - the cell
            # went missing for a reason the run had measured and then discarded.
            row["Detail"] = "; ".join(part for part in (
                "the grid gate rejected this unit's values: %s"
                % ", ".join(sorted(blamed[uid])), _s(row.get("Detail")))
                if part)
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

    # ---- and the cells no signature will ever be able to finalize.
    #
    # Priced from the same two fields as everything else, and written down as
    # WORK: `finalize` will refuse these whatever a reviewer says, so the person
    # who has to re-read them by hand should not have to discover that from a
    # count on a stamp after approving the panel. Only machine-QC-passed values,
    # for the same reason the inference manifest takes only those - a cell the
    # gate already refused is somebody else's problem and has its own queue.
    #
    # The panel still goes to review: its other cells are fine, and the picture
    # is still the thing that says so.
    run_by_panel = {row["Panel_ID"]: row for row in run_rows}
    blocked_rows = []
    for value in machine_qc_df.to_dict("records"):
        identity = _s(value.get("Identity_Method"))
        method = _s(value.get("Value_Method"))
        if PROV.row_tier(value) in PROV.FINALIZABLE_TIERS:
            continue
        pid_ = _s(value.get("Run_Panel_ID"))
        source = run_by_panel.get(pid_, {})
        blocked_rows.append({
            "Panel_ID": pid_,
            "Source_Panel_ID": _s(value.get("Source_Panel_ID")),
            "Figure_ID": _s(source.get("Figure_ID")),
            "Unit_ID": _s(value.get("Unit_ID")),
            "Cell_Key": _s(value.get("Cell_Key")),
            "Identity_Method": identity, "Value_Method": method,
            "Dispersion_Method": _s(value.get("Dispersion_Method")),
            "Cell_State": METHOD_BLOCKED_STATE,
            "Next_Action": METHOD_BLOCKED_ACTION,
            "Image_Path": _s(source.get("Image_Path")),
            "Detail": _blocked_detail(value, identity, method),
        })
    blocked_df = pd.DataFrame(blocked_rows, columns=METHOD_BLOCKED_COLUMNS)

    # ---- the cells a person will be asked about one at a time.
    #
    # Written HERE, after the values are priced and before the review queue is
    # built, because the queue's `Review_Subject_SHA256` hashes the panel's
    # artifacts - so the list of questions has to exist before the subject of the
    # approval is computed. Only MACHINE_QC_PASSED values: a cell the gate
    # refused is not queued for anybody, and asking a reviewer to confirm the
    # reconstruction of a value that will never be pooled spends the one thing
    # this whole ladder is trying not to waste.
    inference_rows = {}
    for value in machine_qc_df.to_dict("records"):
        if PROV.row_tier(value) in PROV.CELL_CONFIRMATION_TIERS:
            inference_rows.setdefault(_s(value.get("Run_Panel_ID")),
                                      []).append(value)
    for pid_, artifacts_ in write_inference_manifests(output_dir,
                                                      inference_rows).items():
        artifacts_by_panel[pid_] = artifacts_by_panel.get(pid_, []) + [
            (item[0], _run_relative(item[1], output_dir),
             file_sha256_or_blank(item[1]), "") for item in artifacts_]
    # AND THE PICTURE OF EACH ONE, drawn in the panel loop and registered here -
    # under the `Inference_ID` the manifest just derived, which is the join
    # between a file named for a cell and a question named for its evidence.
    # `Artifact_Reference` exists for exactly this: `IDENTITY_EVIDENCE` is
    # registered against the `Resolution_ID` it belongs to for the same reason.
    for pid_, rows_ in sorted(inference_rows.items()):
        for value in rows_:
            drawn = crops_by_panel.get(pid_, {}).get(_s(value.get("Cell_Key")))
            if not drawn:
                continue
            artifacts_by_panel.setdefault(pid_, []).append(
                (INFERENCE_CONTEXT_ARTIFACT_TYPE,
                 _run_relative(drawn, output_dir), file_sha256_or_blank(drawn),
                 inference_id(value, panel_id=pid_)))

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
        elif disposition == "GEOMETRY_NOT_AUTHORED":
            # Not queued and not closed. Nothing in this run will touch it and
            # nothing has decided it cannot be touched: it is waiting on a
            # person to measure it, and the inventory says which panels those
            # are rather than burying them in the UNRESOLVED bucket.
            coverage_status = "AWAITING_GEOMETRY"
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
        # Does this panel hold a cell whose evidence asks a person a question
        # beyond "are the marks in the right places"? Priced from the two
        # provenance fields the values carry, not declared anywhere: a panel
        # cannot opt out of the question by leaving a column blank.
        # No statedness test needed, and one was written and removed: a blank
        # pair prices at R4, and R4 is not a tier that ASKS for a confirmation -
        # it is the tier that refuses the value outright, in `finalize`. So a
        # reader that does not answer these questions cannot put the question on
        # its panel, and nothing here has to say so twice.
        mine = [v for v in machine_qc_df.to_dict("records")
                if _s(v.get("Run_Panel_ID")) == row["Panel_ID"]]
        # How many of this panel's cells were reasoned to rather than measured -
        # a COUNT in its own column, not a variant of the mode. The mode says
        # what to open; this says what the values in front of you additionally
        # ask, and the finalizer re-derives it rather than trusting the number
        # here. Zero for most panels, which is what keeps `Inference_Checked`
        # from becoming a column everybody types CONFIRMED into.
        inferred_cells = sum(1 for v in mine if PROV.row_tier(v)
                             in PROV.PANEL_CONFIRMATION_TIERS)
        mode = ("BAR_MONO_GEOMETRY_RESOLVED"
                if row["Panel_ID"] in geometry_artifacts
                and resolutions_by_panel.get(row["Panel_ID"])
                else "BAR_MONO_GEOMETRY" if row["Panel_ID"] in geometry_artifacts
                else "OVERLAY" if overlay_file
                else ("WPD_ONLY" if row["WPD_Project_File"] else ""))
        review_rows.append({
            "Panel_ID": row["Panel_ID"], "Source_Panel_ID": row["Source_Panel_ID"],
            "Figure_ID": row["Figure_ID"], "Unit_ID": row["Unit_ID"],
            "Mark_Type": row["Mark_Type"],
            "Cells_Read": row["Cells_Read"], "Cells_Declared": row["Cells_Declared"],
            "Review_Mode": mode,
            "Inference_Cells": inferred_cells,
            "Overlay_File": overlay_file,
            "WPD_Project_File": row["WPD_Project_File"],
            "Raw_Data_File": row["Raw_Data_File"],
            "Review_Subject_SHA256": review_subject_sha256(
                row, mine, manifest_hashes, environment_record(),
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
          "SHA256": digest, "Artifact_Reference": reference}
         for pid in sorted(artifacts_by_panel)
         for kind, path, digest, reference in artifacts_by_panel[pid]],
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
        # The whole cleanup contract, not a hand-kept list beside it. The
        # geometry bundle is written at its final path like `raw/` and
        # `projects/`, and it holds means, dispersions and auto identities -
        # so a refusal that named only three directories returned zero
        # accepted values and left the finer measurements on disk.
        clear_outputs(output_dir)
        detail = ("%d values passed the gate under a DEMO_ONLY reviewer "
                  "registry. Register the person who actually inspected the "
                  "figures and re-run; a demonstration identity cannot stand "
                  "behind a poolable value" % len(machine_qc_df))
        write_stamp(os.path.join(output_dir, "run_stamp.json"),
                    "DEMO_OUTPUT_REFUSED", run_date, run_mode=run_mode,
                    manifest_dir=os.path.realpath(manifest_dir),
                    document_bytes_bound=bytes_bound,
                    cfg_hash=cfg_hash, manifest_hashes=manifest_hashes,
                    panels=len(run_df), read=len(raw_df), accepted=0,
                    # KEPT NOTHING, AND THE GATE STILL COUNTED. `machine_qc`
                    # stays 0 because that is the truth about what survived this
                    # run; `gate_passed` is the number the refusal is ABOUT, and
                    # before v9.2 it existed only inside `detail` below.
                    machine_qc=0, gate_passed=len(machine_qc_df),
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
    blocked_df.to_csv(os.path.join(work_dir, "method_blocked_cells.csv"),
                      index=False)
    qc.to_csv(os.path.join(work_dir, "qc_problems.csv"), index=False)
    coverage_df.to_csv(os.path.join(work_dir, "source_panel_coverage.csv"), index=False)
    write_stamp(os.path.join(work_dir, "run_stamp.json"), "RAN", run_date,
                run_mode=run_mode, detail=stamp_detail,
                manifest_dir=os.path.realpath(manifest_dir),
                document_bytes_bound=bytes_bound,
                cfg_hash=cfg_hash, manifest_hashes=manifest_hashes,
                panels=len(run_df), read=len(raw_df), accepted=0,
                machine_qc=len(machine_qc_df),
                method_blocked=len(blocked_df),
                qc_problems=int(len(qc)),
                # What the finalizer must find unchanged. Everything it reads
                # to decide whether a value is poolable is hashed here, so a
                # file edited between the run and the approval is a refusal
                # rather than an input.
                # Hashed as BYTES, not as decoded text. Text hashing goes
                # through an encoding and a newline convention, so two files
                # that differ on disk can hash the same and one that does not
                # decode cannot be hashed at all. The verifier does the same.
                output_sha256={
                    name: file_sha256(os.path.join(work_dir, name))
                    for name in ("figure_values_machine_qc.csv",
                                 "review_queue.csv", "figure_values_raw.csv",
                                 "run_manifest.csv", "panel_artifacts.csv")},
                reviewer_registry_sha256=manifest_hashes.get("reviewers", ""))
    try:
        promote(work_dir, output_dir, fault_after=fault_after)
    except Exception as exc:
        withdraw_commit(output_dir, run_date, "%s: %s" % (type(exc).__name__, exc),
                        run_mode=run_mode, document_bytes_bound=bytes_bound)
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
    if summary["status"] == "GEOMETRY_REVIEW_FAILED":
        # Its own branch, because the summary it returns has no `states`,
        # `qc_problems` or `manual_queue` - the run stopped before there were
        # any. The print below assumed every non-rejected summary had all
        # three, so this status reached a person as a KeyError traceback.
        print("GEOMETRY_REVIEW_FAILED: %s" % summary["detail"])
        print("no BAR_MONO panel can be reviewed, so nothing was written")
        return 5
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
