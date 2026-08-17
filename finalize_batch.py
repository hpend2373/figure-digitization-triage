"""Turn machine-QC-passed values into poolable ones, if a person says so.

    python3 finalize_batch.py RUN_DIR [--review value_review.csv] [--date YYYY-MM-DD]

`run_batch.py` stops at `figure_values_machine_qc.csv`. That file means the
machine could find nothing wrong: the reader produced marks, the grid gate found
no holes and no contradictions, and every provenance field resolved. It does not
mean anybody looked at where the marks landed.

That distinction is the whole reason this file exists. A colour bar reader that
anchors slots to detected bars rather than declared ones will silently rename
real readings when the first bar is invisible; a monochrome reader will read a
crisp, plausible, wrong number off a hatched bar whose outline it clipped. Both
produce output the gate has nothing to say about. The only thing that catches
them is a person looking at the overlay and noticing that `FLUID / POST` is
sitting on the bar next door.

So:

    AUTO_EXTRACTED      the reader produced marks
    MACHINE_QC_PASSED   the gate found nothing wrong          <- run_batch ends
    HUMAN_APPROVED      a registered person looked and agreed <- value_review.csv
    POOLING_ELIGIBLE    written here, and nowhere else

Four rules make the approval mean something.

**The approval names the extraction, not the panel.** Each review row carries a
`Review_Subject_SHA256` over the values themselves, every manifest, the raw
marks, the WPD project and the environment that produced them. Change any of
those and the approval is stale, not inherited.

**The run must be untouched.** `run_stamp.json` records the SHA-256 of every
file this module reads, and they are recomputed before any decision is
consulted. Approving an overlay and then editing a Mean is `RUN_ARTIFACT_MODIFIED`.

**A duplicated decision voids the panel.** Two decisions for one panel used to
resolve to whichever came first in the file, so APPROVED-then-REJECTED
approved and REJECTED-then-APPROVED did not. A scientific result must not
depend on CSV row order.

**The approver is a registered human.** `Reviewer_ID` must resolve to a
`Reviewer_Record_Type=HUMAN` row in `reviewer_registry.csv`. A DEMO_IDENTITY
cannot approve, and neither can a name typed into the decision file.

**A DEMO_ONLY run cannot be finalized at all.** No number of approvals promotes
a demonstration.

**Absence is refusal.** A panel with no decision row is not approved. The
default is always the empty file.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import io
import json
import os
import shutil
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import run_batch as RB                                             # noqa: E402
import grid_engine as GE                                           # noqa: E402
import provenance as PROV                                          # noqa: E402

FINALIZE_SCHEMA = "figure-digitization-triage/finalize-stamp/1"

#: `Marks_Checked` is not decoration beside `Decision`. An approval says a
#: person agreed; it does not say what they looked at, and the two are
#: different claims - the whole point of queueing a panel with an artifact is
#: that somebody opens it. `RB.REVIEW_CONFIRMATIONS` says which of these a mode
#: requires, so a mode that shows more can ask for more.
VALUE_REVIEW_COLUMNS = [
    "Review_ID", "Panel_ID", "Review_Subject_SHA256", "Reviewer_ID", "Decision",
    # `Identity_Checked` is the last of the four and the only one about a claim
    # with no measurement behind it: for a bar whose fill could not be sampled,
    # WHICH SERIES it belongs to is somebody's reading of a legend, recorded in
    # `identity_resolution.csv`. Required only by
    # `BAR_MONO_GEOMETRY_RESOLVED` - the panels that actually have such a cell.
    "Marks_Checked", "Axis_Labels_Checked", "Calibration_Checked",
    "Identity_Checked",
    # The fifth, and the only one about how the EVIDENCE was got rather than
    # about what the picture shows. Required by `OVERLAY_INFERRED` - the panels
    # that actually hold a cell whose series was reasoned to rather than
    # measured. The overlay stars those marks and counts them in its footer, so
    # the question is one the reviewer can act on.
    "Inference_Checked",
    "Reviewed_At", "Note",
]

#: Files the finalizer reads to decide whether a value is poolable. Each is
#: hashed by the run and re-hashed here.
#: Artifact types whose CONTENT a contract check interprets, rather than only
#: hashing. These are the ones that have to be kept from the read that hashed
#: them: a PNG or an HTML sheet is evidence a PERSON looks at and this module
#: never parses, so its digest is the whole of what the finalizer needs.
#:
#: v8.2. Until this list existed, `verify_run_outputs` hashed each of these and
#: then `identity_contract_failures`, `collect_inference_manifests`, the
#: mark-evidence join, the point-cloud check and the geometry route check each
#: opened the ones they wanted AGAIN. Swap a geometry file between the hash and
#: the read and it becomes the evidence for a route it does not support, with
#: the ledger still naming the file that was hashed.
STRUCTURED_ARTIFACTS = ("IDENTITY_RESOLUTION", "INFERENCE_MANIFEST",
                        "RAW_MARKS", "POINT_DATA", "MONO_BAR_GEOMETRY")

VERIFIED_OUTPUTS = ("figure_values_machine_qc.csv", "review_queue.csv",
                    "figure_values_raw.csv", "run_manifest.csv",
                    # The ledger of everything else. Verifying it is what makes
                    # the per-artifact hashes below trustworthy: without it the
                    # ledger could be rewritten to match tampered artifacts.
                    "panel_artifacts.csv")

#: Findings that report a value EXCLUDED from an otherwise successful
#: finalization, rather than a reason the finalization cannot happen.
#:
#: The distinction is the preflight's exit code. A reviewer who correctly REJECTS
#: one reconstruction has done the review right, and the run finalizes without
#: that cell - so a preflight that returned "problems found" for it told the
#: first real pilot that its own designed-in rejection was a failure. These three
#: are the ways a value can be dropped while its panel still finalizes; every
#: other code is a refusal.
#:
#: Grouping only, never gating: the exit code follows the finalizer's STATUS,
#: because a panel refused for one reason while another panel finalizes puts a
#: refusal code in the problem list of a FINALIZED run, and a check that read
#: this set as "the finalization succeeded" would be wrong about that run.
NONFATAL_CHECKS = frozenset((
    "INFERENCE_REJECTED",
    "VALUE_METHOD_NOT_FINALIZABLE",
    "VALUE_METHOD_UNSTATED",
))

FINALIZE_STAGING = ".finalize-staging"

#: Moved last. Its presence is what says a finalization committed.
FINALIZE_MARKER = "figure_values_accepted.csv"

#: The one status that means values became poolable. Named because two modules
#: branch on it and a string in both is a string that can drift apart.
FINALIZED_STATUS = "FINALIZED"

FINALIZE_STATUSES = ("FINALIZED", "NOTHING_APPROVED", "RUN_NOT_FINALIZABLE",
                     "RUN_ARTIFACT_MODIFIED",
                     # The manifests are the ones the run validated and they do
                     # not satisfy the contract this package holds today (v9.4).
                     # Distinct from RUN_ARTIFACT_MODIFIED because nothing was
                     # modified: the run was produced under an earlier contract,
                     # and what it needs is a re-run rather than an
                     # investigation into who edited what.
                     "RUN_MANIFEST_CONTRACT_INVALID", "COMMIT_FAILED",
                     # Panels were approved and every value under them was read
                     # at a tier no signature can finalize. Distinct from
                     # NOTHING_APPROVED, which is about the decisions; this is
                     # about the evidence, and the two need different answers
                     # from whoever reads the stamp.
                     "NOTHING_FINALIZABLE")


#: One row per cell whose NUMBER was reconstructed, answered one at a time.
#:
#: A separate FILE rather than more columns on the panel's decision, because the
#: grain is different: a panel has one decision row and as many reconstructed
#: cells as it has. `Inference_ID` is content-derived by the run
#: (`RB.inference_id`) and pre-filled into this file, so a reviewer never types a
#: hash - and a confirmation cannot be moved onto a different cell by editing a
#: row number.
INFERENCE_REVIEW_COLUMNS = [
    "Inference_ID", "Panel_ID", "Unit_ID", "Cell_Key", "Reviewer_ID",
    # CONFIRMED or REJECTED, and the difference is what keeps this gate from
    # throwing away a panel over one bad cell. A missing row is neither: it says
    # nobody answered, and an unanswered question is not a refusal a reader can
    # act on.
    "Inference_Confirmed",
    "Reviewed_At", "Note",
]


def value_review_columns():
    return list(VALUE_REVIEW_COLUMNS)


def inference_review_columns():
    return list(INFERENCE_REVIEW_COLUMNS)


def write_review_template(path, review_queue):
    """One unfilled decision row per panel awaiting review.

    Pre-filling the fingerprint is the point: a reviewer should not have to
    compute or copy it, and a row whose fingerprint they did not touch is one
    they cannot accidentally point at a different run.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(VALUE_REVIEW_COLUMNS)
        for i, (_, r) in enumerate(review_queue.iterrows(), 1):
            w.writerow(["R%03d" % i, r.get("Panel_ID", ""),
                        r.get("Review_Subject_SHA256", "")]
                       + [""] * (len(VALUE_REVIEW_COLUMNS) - 3))
    return path


def write_inference_template(path, manifest_rows):
    """One unfilled row per reconstructed cell, with its identity pre-filled.

    `manifest_rows` is what the run wrote into `inference-review/`, so the file a
    person fills in cannot name a cell this run did not produce - and the
    exact-set contract in `finalize` is then about their ANSWERS rather than
    about their typing.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(INFERENCE_REVIEW_COLUMNS)
        for row in manifest_rows:
            w.writerow([_s(row.get(c)) for c in ("Inference_ID", "Panel_ID",
                                                 "Unit_ID", "Cell_Key")]
                       + [""] * (len(INFERENCE_REVIEW_COLUMNS) - 4))
    return path


def _s(v):
    return "" if v is None else str(v).strip()


def human_reviewers(reviewers):
    """The Reviewer_IDs that may stand behind a number.

    One reading of the registry for both files that carry a signature. It was
    inline in `approved_panels`, and the per-cell contract needs the same answer
    - a copy would be a second place for `Reviewer_Record_Type` to be spelled.
    """
    human = set()
    if reviewers is not None and "Reviewer_ID" in getattr(reviewers, "columns", ()):
        for _, r in reviewers.iterrows():
            if _s(r.get("Reviewer_Record_Type")).upper() == "HUMAN":
                human.add(_s(r.get("Reviewer_ID")))
    return human


def read_decisions(path, columns, flag, where, unreadable, incomplete,
                   absent=None):
    """(frame, sha256) - the decisions, and a hash OF THE BYTES THEY CAME FROM.

    Hashed once, parsed from the same bytes. The stamp used to name the review
    file and then hash the path again after the verdict was decided, so a
    spreadsheet autosave landing in between produced an accepted file decided
    from one set of decisions and a `Review_File_SHA256` naming another - the
    exact question the hash exists to answer, answered wrong, with nothing in the
    run saying so. It is the same fix the manifests got: hash the bytes, then
    parse the bytes you hashed.

    The codes are ARGUMENTS rather than built from a name, so every code this
    module can emit is a literal somebody can grep for.
    """
    if not os.path.exists(path):
        if absent:
            flag(where, absent,
                 "%s does not exist. Nothing is approved by default" % path)
        return pd.DataFrame(columns=columns), ""
    # DECLARED FIRST, so a refusal records the bytes that CAUSED it. The parse
    # branch used to hash the path again, which named whatever was on disk
    # afterwards - a smaller window than the one this function closes, on the
    # audit rather than on the accepted values, and the same shape.
    digest = ""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha256(data).hexdigest()
        df = pd.read_csv(io.BytesIO(data), dtype=object).fillna("")
    except Exception as exc:
        # AND A BLANK IS THE HONEST ANSWER when the read itself failed. The
        # fallback here used to be `file_sha256_or_blank(path)`, which opens the
        # path a SECOND time: a file this run could not read, hashed anyway,
        # recorded a 64-character digest beside a status saying the decisions
        # could not be parsed - and the digest named whatever the retry found,
        # which is by construction not the bytes that caused the refusal. If the
        # bytes were read and only the parse failed, `digest` is theirs and is
        # recorded; if the read failed, this run has no bytes to name.
        flag(where, unreadable, "%s: %s" % (type(exc).__name__, exc))
        return pd.DataFrame(columns=columns), digest
    missing = [c for c in columns if c not in df.columns]
    if missing:
        flag(where, incomplete, ", ".join(missing))
        return pd.DataFrame(columns=columns), digest
    return df, digest


def load_reviews(path, flag):
    return read_decisions(path, VALUE_REVIEW_COLUMNS, flag, "review",
                          "REVIEW_FILE_UNREADABLE", "REVIEW_SCHEMA_INCOMPLETE",
                          absent="REVIEW_FILE_MISSING")[0]


def verify_manifest_inputs(manifest_dir, run_stamp, flag):
    """Are these the manifests the run validated, frame by frame?

    `Reviewer_Registry_SHA256` was checked and the other eleven were not, which
    was defensible while the finalizer only read the registry. It re-derives the
    BAR_MONO value contract from the panel, series and position manifests now,
    so an edit to any of them changes what "correct" means: swap two
    `Factor_Level`s in `position_manifest.csv` after the run and the cell check
    is done against a mapping nobody approved.

    Compared as FRAMES rather than as bytes, because that is how the run hashed
    them - a re-saved CSV with a different line ending is the same manifest.

    Returns the verified frames, or None. They are RETURNED rather than dropped
    so the checks that re-derive the value contract read the frames that were
    verified instead of opening the same files again.
    """
    recorded = run_stamp.get("Manifest_SHA256")
    if not isinstance(recorded, dict) or not recorded:
        flag("run", "RUN_NOT_FINALIZABLE",
             "the run stamp carries no Manifest_SHA256, so there is nothing to "
             "check the manifests against")
        return None
    try:
        frames = RB.load_manifests(manifest_dir)
    except Exception as exc:
        flag("run", "RUN_NOT_FINALIZABLE",
             "the manifests this run was produced from could not be loaded "
             "(%s: %s)" % (type(exc).__name__, exc))
        return None
    if set(recorded) != set(frames):
        # Includes the optional one: `load_manifests` substitutes an empty frame
        # with the right columns when `identity_resolution.csv` is absent, so
        # "there were no resolutions" has a hash like everything else and adding
        # a resolution file after the run is a changed set, not a silent extra.
        flag("run", "RUN_MANIFEST_SET_CHANGED",
             "the run recorded %s and this directory holds %s"
             % (", ".join(sorted(recorded)), ", ".join(sorted(frames))))
        return None
    ok = True
    for name in sorted(frames):
        actual = RB.frame_sha256(frames[name])
        if actual != _s(recorded.get(name)):
            flag("run", "RUN_MANIFEST_MODIFIED",
                 "%s is not the manifest the run validated: it hashes %s... "
                 "and the run recorded %s..."
                 % (name, actual[:16], _s(recorded.get(name))[:16] or "(nothing)"))
            ok = False
    return frames if ok else None


#: A panel the manifests do not describe. Named rather than written inline so
#: the two callers cannot disagree about what "no declaration" looks like.
EMPTY_CELL_MAP = {"position_factor": "", "position_levels": {},
                  "series_factor": "", "series_levels": {},
                  "series_by_fill": {}}


def cell_maps(frames):
    """{Panel_ID: Cell_Map} from the VERIFIED manifests.

    One construction, two readers. `value_contract_failures` re-derives the
    BAR_MONO identity contract from it and `_mark_evidence_failures` re-derives
    the `Cell_Key` a mark's own series and position ids should have produced, and
    those two must not be able to disagree about which level `S2` names: a value
    could then satisfy one check against one mapping and the other against
    another, which is the fail-open a shared frame exists to prevent.

    `Factor_Name` is taken panel-wide rather than per row, because a `Cell_Key`
    has one factor per axis - the same reading `run_batch._read_panel` takes when
    it builds the key in the first place.
    """
    panels = frames["panels"] if frames is not None and "panels" in frames \
        else pd.DataFrame()
    series = frames["series"] if frames is not None and "series" in frames \
        else pd.DataFrame()
    positions = frames["positions"] if frames is not None \
        and "positions" in frames else pd.DataFrame()
    by_panel_series, by_panel_position = {}, {}
    for _, r in series.iterrows():
        by_panel_series.setdefault(_s(r.get("Panel_ID")), []).append(r)
    for _, r in positions.iterrows():
        by_panel_position.setdefault(_s(r.get("Panel_ID")), []).append(r)
    out = {}
    for _, panel in panels.iterrows():
        pid = _s(panel.get("Panel_ID"))
        prows = by_panel_series.get(pid, [])
        qrows = by_panel_position.get(pid, [])
        out[pid] = {
            "position_factor": next(
                (_s(r.get("Factor_Name")).upper() for r in qrows
                 if _s(r.get("Factor_Name"))), ""),
            "position_levels": {_s(r.get("Position_ID")):
                                _s(r.get("Factor_Level")) for r in qrows},
            "series_factor": next(
                (_s(r.get("Factor_Name")).upper() for r in prows
                 if _s(r.get("Factor_Name"))), ""),
            "series_levels": {_s(r.get("Series_ID")):
                              _s(r.get("Factor_Level")) for r in prows},
            "series_by_fill": {_s(r.get("Bar_Fill_Pattern")).upper():
                               _s(r.get("Series_ID")) for r in prows
                               if _s(r.get("Bar_Fill_Pattern"))},
        }
    return out


def value_contract_failures(run_dir, frames, machine, flag):
    """Panels whose values fail the runner's own BAR_MONO contract, re-derived.

    The SAME function the runner uses - `identity_provenance_problems` - run
    again here on the verified files, because a run this module did not produce
    is the case it exists for. Nothing pins a minimum pipeline version, so a run
    made before a given check existed arrives looking complete: v7.29-v7.31 runs
    carry per-bar hashes and means that agree while their `Cell_Key`s could have
    been exchanged, which is the one failure with no arithmetic signature. This
    module is where that is caught for them.

    Every input has already been through `verify_run_outputs`: the manifests are
    hashed into the run stamp and `mono_bar_geometry.csv` is one of the run's
    own outputs, so re-reading them here is re-reading what was approved.
    """
    withheld = set()
    missing = [k for k in ("panels", "series", "positions") if k not in (frames or {})]
    if missing:
        flag("run", "RUN_NOT_FINALIZABLE",
             "the verified manifests do not include %s, so this run's values "
             "cannot be re-checked" % ", ".join(missing))
        return {"*"}
    panels, series = frames["panels"], frames["series"]
    positions = frames["positions"]
    resolutions = {}
    for _, row in (frames.get("resolutions")
                   if frames.get("resolutions") is not None
                   else pd.DataFrame()).iterrows():
        resolutions.setdefault(_s(row.get("Panel_ID")), []).append(row)
    maps = cell_maps(frames)
    panel_index = {}
    for _, panel in panels.iterrows():
        pid = _s(panel.get("Panel_ID"))
        panel_index[pid] = {
            "Mark_Type": _s(panel.get("Mark_Type")),
            "Unit_ID": _s(panel.get("Unit_ID")),
            "Source_Panel_ID": _s(panel.get("Source_Panel_ID")),
            "Figure_ID": _s(panel.get("Figure_ID")),
            "Identity_Domain_ID": _s(panel.get("Identity_Domain_ID")),
            "Cell_Map": maps.get(pid, EMPTY_CELL_MAP),
        }
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    problems = RB.identity_provenance_problems(
        rows, panel_index,
        geometry=geometry_index_of(run_dir, frames),
        resolutions=RB.resolution_index(resolutions))
    for where, code, detail in problems:
        try:
            index = int(where.split(":", 1)[1]) - 2
        except (IndexError, ValueError):        # pragma: no cover - defensive
            index = -1
        pid = _s(rows[index].get("Run_Panel_ID")) if 0 <= index < len(rows) else ""
        flag("panel:%s" % (pid or "?"), code, detail)
        withheld.add(pid)
    return withheld


def grid_contract_failures(frames, machine, flag):
    """Panels whose UNITS fail the CURRENT grid gate, re-run on the verified run.

    v9.4 re-ran `validate_batch_manifests` over the verified manifests, which is
    the source/run-manifest half of the contract. The data half lives in
    `GE.fig_validate_bundle` - the factor sets, the declared levels, the cell
    product, the dispersion and transformation rules - and that half was still
    the version in force when the run was made.

    The gap has no arithmetic signature. A historical producer whose grid
    declares `ARM = CONTROL | TREATED` and whose series declares `ARM=PLACEBO`
    writes values whose `Cell_Key` is `ARM=PLACEBO`: the marks agree with the
    values, the values agree with the manifests they were built from, every hash
    matches, and `validate_batch_manifests` cannot see it because it is not given
    `grid_definitions` at all. Today's gate says `UNDECLARED_FACTOR_LEVEL`.

    Three choices make this a check rather than a blunt instrument.

    **The gate is re-run on the RAW values**, which is the frame the runner gave
    it. Running it on `figure_values_machine_qc.csv` would judge cell coverage
    against a file the run's own gate had already filtered, so every unit that
    legitimately lost a cell would come back `FACTORIAL_CELL_MISSING` - a refusal
    manufactured by the re-check rather than found by it.

    **Only units with something left to lose are withheld.** A unit whose rows
    all failed the historical gate has nothing in `figure_values_machine_qc.csv`,
    so no approval can turn its values into accepted ones and there is nothing
    for this to protect. A unit that DID put values through the old gate and
    fails today's is exactly the case this exists for.

    **`check_files=False`.** The gate would otherwise look for the rasters the
    manifests name, and an approval must not depend on a corpus directory the
    approver does not have. The raster each panel was read from is covered by the
    review subject.
    """
    withheld = set()
    outputs = (frames or {}).get("frames") or {}
    raw = outputs.get("figure_values_raw.csv")
    missing = [k for k in ("figures", "grids", "units", "panels")
               if (frames or {}).get(k) is None]
    if raw is None or missing:
        flag("run", "RUN_NOT_FINALIZABLE",
             "the verified run does not include %s, so its values cannot be "
             "re-checked against the current grid contract"
             % ", ".join(missing + ([] if raw is not None
                                    else ["figure_values_raw.csv"])))
        return {"*"}
    values = pd.DataFrame(
        [{c: r.get(c, "") for c in GE.fig_values_columns()}
         for r in raw.to_dict("records")],
        columns=GE.fig_values_columns())
    # THE FIGURES FRAME THE RUNNER GAVE THE GATE, rebuilt. `run_batch` fills
    # `WPD_Project_File` on the figure from the projects its panels wrote before
    # it calls the gate - an automated run has no human-saved project, so it
    # saves its own - and `figure_manifest.csv` in the manifest directory has the
    # column blank. Re-running the gate against the manifest copy therefore
    # reports `MISSING_PROVENANCE: WPD_Project_File` on every digitized unit of
    # every healthy run: a refusal invented by the re-check. The projects are
    # named by the run's own verified value rows, so they are read from there.
    figures = frames["figures"].copy()
    if "WPD_Project_File" in figures.columns:
        unit_figure = {_s(u.get("Unit_ID")): _s(u.get("Figure_ID"))
                       for _, u in frames["units"].iterrows()}
        by_figure = {}
        for row in raw.to_dict("records"):
            project = _s(row.get("WPD_Project_File"))
            fig_id = unit_figure.get(_s(row.get("Unit_ID")), "")
            if project and fig_id and project not in by_figure.get(fig_id, []):
                by_figure.setdefault(fig_id, []).append(project)
        figures["WPD_Project_File"] = [
            (";".join(by_figure.get(_s(r.get("Figure_ID")), []))
             if BM.blank(r.get("WPD_Project_File")) else r.get("WPD_Project_File"))
            for _, r in figures.iterrows()]
    qc = GE.fig_validate_bundle(figures, frames["grids"],
                                frames["units"], values, kernel=RB.K,
                                check_files=False)
    if not len(qc):
        return withheld
    blamed = RB._units_named_by(qc, values, frames["units"],
                               figures_df=figures,
                               grids_df=frames["grids"])
    if not blamed:
        return withheld
    at_risk = {_s(r.get("Unit_ID")) for r in (
        machine.to_dict("records") if hasattr(machine, "to_dict")
        else list(machine or ()))}
    panels_of_unit = {}
    for _, panel in frames["panels"].iterrows():
        panels_of_unit.setdefault(_s(panel.get("Unit_ID")), []).append(
            _s(panel.get("Panel_ID")))
    for uid in sorted(blamed):
        if uid not in at_risk:
            continue
        for pid in panels_of_unit.get(uid, []) or ["?"]:
            flag("panel:%s" % pid, "RUN_GRID_CONTRACT_INVALID",
                 "%s put values through the gate this run was made with and "
                 "fails the current one: %s. The values and the manifests agree "
                 "with each other; what they do not satisfy is the contract this "
                 "package holds now, so the run needs re-running before its "
                 "values are approved" % (uid, ", ".join(sorted(blamed[uid]))))
            withheld.add(pid)
    return withheld


def resolution_copy_failures(rows_by_panel, frames, flag):
    """The run's copies of the resolution rows, checked ONCE and against the run.

    Three things, and the first two are only visible when every panel's copy is
    in hand at the same time.

    THE SHARED CHECKER IS CALLED ONCE. `check_identity_resolution` keeps
    `Resolution_ID` unique across the frame it is given, so calling it per panel
    - which is how this started - made the identifier unique per panel and
    global nowhere: two panels could both hold IR001, one identifier naming two
    different decisions, and the evidence filenames are built from that
    identifier too.

    THE COPY IS THE MANIFEST. `identity_resolution.csv` is verified against the
    run stamp and `identity__<Panel_ID>.csv` against the artifact ledger, and
    nothing compared the two - so a run copy could name a different reviewer, a
    different evidence file or a different date, be internally valid, hash
    correctly, and leave `Resolution_ID` pointing at two different rows.

    AND THE REGISTRY'S OWN PROBLEMS ARE NOT SWALLOWED. The reviewer index was
    built with a flag callback that threw everything away, and
    `check_reviewer_registry` indexes a row before it validates it - so a
    registry entry with a malformed ORCID or a mismatched record type still
    counted as "a registered HUMAN" for a resolution.
    """
    problems, withheld = [], set()
    columns = BM.identity_resolution_columns()
    reviewers = frames.get("reviewers") if frames else None
    if reviewers is None:
        flag("run", "RUN_NOT_FINALIZABLE",
             "the verified manifests carry no reviewer registry, so the "
             "resolutions cannot be checked against it")
        return set(rows_by_panel)
    registry_problems = []
    index = BM.check_reviewer_registry(
        reviewers,
        lambda where, code, detail: registry_problems.append((code, detail)))
    if registry_problems:
        for code, detail in registry_problems:
            flag("run", "REVIEW_IDENTITY_REVIEWER_INVALID", "%s: %s" % (code, detail))
        withheld |= set(rows_by_panel)
    # Pre-scanned, before the shared checker: it reports a duplicate on the
    # SECOND occurrence, so charging the problem to that row's panel let the
    # first panel through - and a duplicated identifier is a property of both
    # panels, neither of which can be said to own IR001.
    by_id = {}
    for pid, rows in sorted(rows_by_panel.items()):
        for row in rows:
            by_id.setdefault(_s(row.get("Resolution_ID")), []).append(pid)
    for rid, pids in sorted(by_id.items()):
        if len(pids) > 1:
            flag("run", "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
                 "resolution %s is used by %s; one identifier names one "
                 "decision" % (rid or "(blank)", ", ".join(sorted(set(pids)))))
            withheld |= set(pids)
    every = [row for pid in sorted(rows_by_panel) for row in rows_by_panel[pid]]
    if every:
        BM.check_identity_resolution(
            pd.DataFrame(every, columns=columns),
            frames.get("panels", pd.DataFrame()),
            frames.get("series", pd.DataFrame()),
            lambda where, code, detail: problems.append((where, code, detail)),
            reviewer_index=index, check_files=False)
    for where, code, detail in problems:
        # `identity_resolution:<row>` back to the panel it came from, so a
        # problem is charged to the panel that is withheld for it.
        try:
            row = every[int(where.split(":", 1)[1]) - 2]
        except (IndexError, ValueError):
            row = {}
        pid = _s(row.get("Panel_ID")) or "?"
        flag("panel:%s" % pid, "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
             "the run's resolution rows do not pass the manifest contract: "
             "%s - %s" % (code, detail))
        withheld |= ({pid} if pid in rows_by_panel else set(rows_by_panel))
    # The copy against the manifest, keyed by Resolution_ID rather than by row
    # order, so a re-ordered file is the same file and a changed field is not.
    declared = {}
    frame = frames.get("resolutions")
    if frame is not None:
        for _, row in frame.iterrows():
            declared.setdefault(_s(row.get("Panel_ID")), []).append(
                [_s(row.get(c)) for c in columns])
    for pid in declared:
        declared[pid].sort()
    # The UNION of the two sides. Walking the run's copies alone answers "is
    # each copy right" and never asks "is each manifest row copied": a panel the
    # verified manifest resolves and the run never copied has no key in
    # `rows_by_panel`, so it was compared against nothing. On a run this
    # producer just made, the missing copy trips the evidence checks first - but
    # the contract here is that a run made by SOMEBODY ELSE is held to the same
    # rules, and the other producer is exactly the one that omits a file.
    for pid in sorted(set(declared) | set(rows_by_panel)):
        # Sorted LISTS, not dicts keyed by Resolution_ID: a dict drops a
        # repeated identifier silently, which is the one thing this comparison
        # must not do. Row ORDER still does not matter.
        copied = sorted([[_s(r.get(c)) for c in columns]
                         for r in rows_by_panel.get(pid, [])])
        if copied != declared.get(pid, []):
            flag("panel:%s" % pid, "IDENTITY_RESOLUTION_COPY_MISMATCH",
                 "the resolutions copied into the run for %s are not the ones "
                 "in the manifest the run validated%s"
                 % (pid, "" if pid in rows_by_panel
                    else " - the run copied none of them"))
            withheld.add(pid)
    return withheld


def identity_contract_failures(run_dir, ledger_rows, machine, flag,
                               frames=None, artifacts=None):
    """Panels whose human-named identities do not hold up against this run.

    Two things, both re-derived here rather than taken from the producer's word,
    because nothing pins a minimum pipeline version: a run made by an older or a
    tampered producer arrives with a complete-looking ledger.

    `IDENTITY_RESOLUTION` says which resolutions a panel was read under, and
    `Evidence_Type` says whether each one rests on a FILE. If it does, the bytes
    of that file have to be in the run and in the ledger - otherwise
    `Identity_Checked=CONFIRMED` is a confirmation of a hash string in a
    manifest, and the reviewer who received the run directory never had the
    picture to look at.

    Deliberately not expressed as a required artifact type on the review mode: a
    panel whose resolutions are all `REVIEWER_INSPECTION` has no evidence file,
    so a static requirement would refuse a correct panel. The condition is in
    the rows, so the check reads the rows.

    Returns the set of Panel_IDs to withhold. The hashes themselves are checked
    by `verify_run_outputs`, which has already run; what this adds is that the
    right ones EXIST, that each one matches what the resolution declared, and
    that every value claiming a human identity cites a resolution this panel
    actually has - with the same row hash, fill and evidence type. A
    `Resolution_ID` that is only non-blank is a label: exchange two of a panel's
    resolutions on their values and the numbers still agree while the accepted
    file cites the wrong evidence and the wrong reading.
    """
    withheld = set()
    copied_rows = {}
    rows_by_panel = {}
    machine_rows = (machine.to_dict("records")
                    if hasattr(machine, "to_dict") else list(machine or ()))
    for row in machine_rows:
        rows_by_panel.setdefault(_s(row.get("Run_Panel_ID")), []).append(row)
    by_panel = {}
    for _, art in ledger_rows.iterrows():
        by_panel.setdefault(_s(art.get("Panel_ID")), []).append(art)
    # Panels whose VALUES say a person named a series. Driven from the values,
    # not from the ledger: a panel with human-resolved values and no
    # IDENTITY_RESOLUTION artifact at all used to fall out of the loop below at
    # `if not resolutions: continue`, which is the fail-open case exactly.
    human_panels = {pid for pid, rows in rows_by_panel.items()
                    if any(_s(r.get("Identity_Source")).upper() == "HUMAN"
                           for r in rows)}
    for pid in sorted(human_panels - set(by_panel)):
        flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
             "%s has values a person named and no artifacts at all" % pid)
        withheld.add(pid)
    for pid, arts in sorted(by_panel.items()):
        resolutions = [a for a in arts
                       if _s(a.get("Artifact_Type")) == RB.IDENTITY_ARTIFACT_TYPE]
        if len(resolutions) > 1:
            flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                 "%s carries %d IDENTITY_RESOLUTION artifacts; a panel is read "
                 "under one set of resolutions"
                 % (pid, len(resolutions)))
            withheld.add(pid)
            continue
        if not resolutions:
            if pid in human_panels:
                flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                     "%s has values a person named and no IDENTITY_RESOLUTION "
                     "artifact, so there is nothing to check them against" % pid)
                withheld.add(pid)
            continue
        evidence = {}
        for a in arts:
            if _s(a.get("Artifact_Type")) != RB.IDENTITY_EVIDENCE_ARTIFACT_TYPE:
                continue
            # A list, not an assignment. Keyed by reference and assigned, a
            # second entry for one Resolution_ID silently replaced the first -
            # so which of two files a panel was approved against depended on
            # ledger ORDER. One reference, one file, checked below.
            evidence.setdefault(_s(a.get("Artifact_Reference")), []).append(a)
        for art in resolutions:
            path, blob = artifact_data(run_dir, art, artifacts)
            if path is None or blob is None:
                # `verify_run_outputs` has already refused the whole run for
                # this; withholding the panel as well keeps the two independent.
                flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                     "the resolution rows for %s are not readable, so the "
                     "evidence behind them cannot be checked" % pid)
                withheld.add(pid)
                continue
            try:
                rows = list(csv.DictReader(
                    io.StringIO(blob.decode("utf-8"))))
            except Exception as exc:
                flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                     "the resolution rows for %s could not be parsed (%s: %s)"
                     % (pid, type(exc).__name__, exc))
                withheld.add(pid)
                continue
            declared, duplicated = {}, set()
            for row in rows:
                rid = _s(row.get("Resolution_ID"))
                if rid in declared:
                    duplicated.add(rid)
                declared[rid] = row
            # A CSV the producer wrote is still an input to THIS module, and a
            # dict comprehension over it let the last row of a repeated
            # Resolution_ID win. Which of two rows a value was checked against
            # would then depend on file order.
            for rid in sorted(duplicated):
                flag("panel:%s" % pid, "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
                     "resolution %s appears twice in %s's resolution rows"
                     % (rid, pid))
                withheld.add(pid)
            # And a row with a blank key field is a wildcard: the comparisons
            # below skip an empty `want`, so a resolution missing its row hash
            # would match any value that cited it.
            for row in rows:
                blanks = [c for c in ("Resolution_ID", "Panel_ID",
                                      "Geometry_Row_SHA256",
                                      "Resolved_Series_ID",
                                      "Resolved_Fill_Pattern", "Evidence_Type")
                          if not _s(row.get(c))]
                if blanks:
                    flag("panel:%s" % pid, "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
                         "a resolution row of %s leaves %s blank, which would "
                         "match any value that cited it"
                         % (pid, ", ".join(blanks)))
                    withheld.add(pid)
                elif _s(row.get("Panel_ID")) != pid:
                    flag("panel:%s" % pid, "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
                         "a resolution row filed under %s reads Panel_ID=%s"
                         % (pid, _s(row.get("Panel_ID"))))
                    withheld.add(pid)
            copied_rows[pid] = rows
            # Every value that says a person named its series has to cite one of
            # THESE rows, and to agree with it.
            for value in rows_by_panel.get(pid, []):
                if _s(value.get("Identity_Source")).upper() != "HUMAN":
                    continue
                rid = _s(value.get("Resolution_ID"))
                cited = declared.get(rid)
                if cited is None:
                    flag("panel:%s" % pid,
                         "REVIEW_IDENTITY_RESOLUTION_UNKNOWN",
                         "a value of %s cites Resolution_ID=%s, which is not a "
                         "resolution this run recorded for it"
                         % (pid, rid or "(blank)"))
                    withheld.add(pid)
                    continue
                for column, got in (
                        ("Geometry_Row_SHA256",
                         _s(value.get("Geometry_Row_SHA256")).lower()),
                        ("Resolved_Fill_Pattern",
                         _s(value.get("Resolved_Fill_Pattern")).upper()),
                        ("Evidence_Type",
                         _s(value.get("Identity_Evidence_Type")).upper())):
                    want = _s(cited.get(column))
                    want = (want.lower() if column == "Geometry_Row_SHA256"
                            else want.upper())
                    if want and want != got:
                        flag("panel:%s" % pid,
                             "REVIEW_IDENTITY_RESOLUTION_MISMATCH",
                             "a value of %s cites resolution %s, which reads "
                             "%s=%s while the value says %s"
                             % (pid, rid, column, want or "blank",
                                got or "blank"))
                        withheld.add(pid)
            for row in rows:
                if _s(row.get("Evidence_Type")).upper() \
                        not in BM.FILE_EVIDENCE_TYPES:
                    continue
                rid = _s(row.get("Resolution_ID"))
                copies = evidence.get(rid) or []
                if len(copies) > 1:
                    flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                         "resolution %s has %d IDENTITY_EVIDENCE artifacts in "
                         "the ledger; one resolution rests on one file, and "
                         "which of them was approved cannot be decided by "
                         "ledger order" % (rid, len(copies)))
                    withheld.add(pid)
                    continue
                got = copies[0] if copies else None
                if got is None:
                    flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                         "resolution %s rests on %s (%s) and this run carries "
                         "no IDENTITY_EVIDENCE for it. A run made before the "
                         "evidence was copied in cannot be finalized"
                         % (rid, _s(row.get("Evidence_Type")),
                            _s(row.get("Evidence_Artifact"))))
                    withheld.add(pid)
                    continue
                want = _s(row.get("Evidence_Artifact_SHA256")).lower()
                if want and _s(got.get("SHA256")).lower() != want:
                    flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                         "resolution %s declares evidence %s... and the run "
                         "carries %s...; the copy is not the file that was "
                         "signed" % (rid, want[:16],
                                     _s(got.get("SHA256"))[:16] or "(nothing)"))
                    withheld.add(pid)
    # Once, over every panel's copy at the same time: uniqueness of
    # `Resolution_ID` is a property of the RUN, not of a panel, and so is the
    # comparison against the manifest the run validated.
    withheld |= resolution_copy_failures(copied_rows, frames or {}, flag)
    return withheld


def load_inference_reviews(path, flag):
    """The per-cell decisions, or an empty frame and a flag saying why.

    A MISSING file is not an error on its own: most runs hold no reconstructed
    value, and demanding the file from every run would be a refusal with nothing
    behind it. The panels that need it are refused by
    `inference_contract_failures`, which knows which cells were asked about.
    """
    return read_decisions(path, INFERENCE_REVIEW_COLUMNS, flag, "inference",
                          "INFERENCE_FILE_UNREADABLE",
                          "INFERENCE_SCHEMA_INCOMPLETE")[0]


def inference_contract_failures(run_dir, ledger_rows, machine, decisions,
                                reviewers, flag, today=None, panels=(),
                                artifacts=None):
    """The exact-set contract for cells whose NUMBER was reconstructed.

    Returns `(withheld_panels, rejected_ids)`.

    ## Why an exact set, and not "every row is signed"

    `R3` is the tier where the number came from neighbouring ink rather than from
    ink at the cell - a bracketed interpolation across a masked stretch, or the
    edge of a run too thick to be one stroke. A panel-level "I looked at the
    inferences" cannot carry it: one wrong cell in twenty does not show up in a
    single answer, and the overlay draws a mark either way.

    So the questions are enumerated, and the answers have to match the questions
    exactly:

        MISSING     an unanswered question holds the panel. Nobody said whether
                    they looked, and a partial answer does not say which part.
        DUPLICATE   two answers for one cell cannot be told apart in an audit,
                    and which one wins would be the order of the rows.
        UNKNOWN     an answer to a question this run did not ask means the person
                    was working from a different list of cells.
        REJECTED    an answer, and it costs the CELL rather than the panel. A
                    reviewer who can see that one reconstruction is wrong should
                    not have to throw away the nineteen beside it.

    ## Derived from the values, not from the ledger

    Which cells need asking about is recomputed here from `Identity_Method` and
    `Value_Method`, exactly as the run computed it - not read out of the run's own
    manifest. Nothing pins a minimum pipeline version, so a run made by an older
    or a tampered producer arrives with a complete-looking ledger and no manifest
    at all, and taking the producer's list would make that the fail-open case.
    The manifest is then checked AGAINST the recomputed set, because it is what
    the reviewer actually read.
    """
    today = today or datetime.date.today()
    human = human_reviewers(reviewers)
    withheld, rejected = set(), set()
    machine_rows = (machine.to_dict("records")
                    if hasattr(machine, "to_dict") else list(machine or ()))
    asked = {}
    for row in machine_rows:
        pid = _s(row.get("Run_Panel_ID"))
        if panels and pid not in panels:
            continue
        # THE ROW, over all three axes. A cell can reach R3 because its NUMBER
        # was reconstructed or because its SPREAD came off a cap nothing connects
        # to the mark, and both are questions for a person about that one cell.
        # Priced with `review_tier` here, this function asked about the first and
        # not the second - and the two-axis version of the same derivation was
        # already fixed in the runner, which is how the two came apart.
        if PROV.row_tier(row) in PROV.CELL_CONFIRMATION_TIERS:
            asked.setdefault(pid, {})[RB.inference_id(row, panel_id=pid)] = row
    by_panel = {}
    for _, art in ledger_rows.iterrows():
        by_panel.setdefault(_s(art.get("Panel_ID")), []).append(art)
    # Answers first, so a row naming a panel that asked nothing is reported as
    # what it is rather than falling out of the loop below.
    answers, counted = {}, {}
    for i, (_, row) in enumerate(decisions.iterrows()):
        iid = _s(row.get("Inference_ID"))
        pid = _s(row.get("Panel_ID"))
        counted[(pid, iid)] = counted.get((pid, iid), 0) + 1
        answers.setdefault(pid, {})[iid] = ("inference:%d" % (i + 2), row)
    for (pid, iid), n in sorted(counted.items()):
        if n > 1 and pid in asked:
            flag("panel:%s" % pid, "INFERENCE_CONFIRMATION_DUPLICATE",
                 "%d rows answer for %s; none of them is applied, because "
                 "which one wins would otherwise be the order of the rows"
                 % (n, iid or "(blank Inference_ID)"))
            withheld.add(pid)
    for pid, unknown in sorted(answers.items()):
        for iid in sorted(set(unknown) - set(asked.get(pid, {}))):
            flag("panel:%s" % pid, "INFERENCE_CONFIRMATION_UNKNOWN",
                 "a decision answers for %s, which is not a reconstructed cell "
                 "this run produced for %s. The answers were written against a "
                 "different list of cells"
                 % (iid or "(blank Inference_ID)", pid or "(blank Panel_ID)"))
            if pid in panels:
                withheld.add(pid)
    for pid, cells in sorted(asked.items()):
        # The list the reviewer read, checked against the list just recomputed.
        manifests = [a for a in by_panel.get(pid, ())
                     if _s(a.get("Artifact_Type")) == RB.INFERENCE_ARTIFACT_TYPE]
        if len(manifests) != 1:
            flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISSING",
                 "%s holds %d reconstructed value(s) and carries %d %s "
                 "artifact(s); the cells a person was asked about are not in "
                 "this run" % (pid, len(cells), len(manifests),
                               RB.INFERENCE_ARTIFACT_TYPE))
            withheld.add(pid)
        else:
            listed = _inference_manifest_ids(run_dir, manifests[0], pid, flag,
                                             artifacts=artifacts)
            if listed is None:
                withheld.add(pid)
            elif listed != set(cells):
                flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISMATCH",
                     "%s's inference manifest lists %d cell(s) and this run's "
                     "values hold %d; the questions a person read are not the "
                     "questions these values ask"
                     % (pid, len(listed), len(cells)))
                withheld.add(pid)
        # A PICTURE OF EVERY CELL BEING ASKED ABOUT. Registered against the
        # `Inference_ID` it belongs to, so a panel that produced three
        # reconstructed cells and two crops is refused rather than reviewed on
        # two thirds of its evidence.
        pictured = {_s(a.get("Artifact_Reference")) for a in by_panel.get(pid, ())
                    if _s(a.get("Artifact_Type"))
                    == RB.INFERENCE_CONTEXT_ARTIFACT_TYPE}
        # ONLY THE CELLS WHOSE NUMBER WAS RECONSTRUCTED. The context crop pictures
        # the two columns a value was interpolated between, which a cell that is
        # R3 because of its ERROR BAR does not have: its evidence is the whisker
        # on the panel overlay, and demanding a support crop for it would refuse a
        # panel for the absence of a picture that cannot be drawn.
        wants_picture = {iid for iid, r in cells.items()
                         if PROV.value_tier(_s(r.get("Value_Method")))
                         in PROV.CELL_CONFIRMATION_TIERS}
        for iid in sorted(wants_picture - pictured):
            row = cells[iid]
            flag("panel:%s" % pid, "INFERENCE_CONTEXT_MISSING",
                 "%s/%s is asked about by name and this run carries no picture "
                 "of it (%s). The row gives its supports and its span as pixel "
                 "numbers, and a confirmation given against numbers nobody can "
                 "see the figure behind is a signature on a filename"
                 % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key")), iid))
            withheld.add(pid)
        given = answers.get(pid, {})
        for iid in sorted(cells):
            if counted.get((pid, iid), 0) > 1:
                continue                      # already withheld, above
            entry = given.get(iid)
            if entry is None:
                row = cells[iid]
                flag("panel:%s" % pid, "INFERENCE_CONFIRMATION_MISSING",
                     "%s/%s was read as %s and nobody answered for it "
                     "(%s). An approval of the panel does not say this "
                     "reconstruction was looked at"
                     % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key")),
                        _s(row.get("Value_Method")) or "(blank)", iid))
                withheld.add(pid)
                continue
            line, row = entry
            verdict = _s(row.get("Inference_Confirmed")).upper()
            if verdict not in RB.INFERENCE_DECISIONS:
                flag(line, "BAD_INFERENCE_DECISION",
                     "Inference_Confirmed=%r is not one of %s"
                     % (_s(row.get("Inference_Confirmed")),
                        ", ".join(RB.INFERENCE_DECISIONS)))
                withheld.add(pid)
                continue
            rid = _s(row.get("Reviewer_ID"))
            if rid not in human:
                flag(line, "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED",
                     "Reviewer_ID=%r is not a Reviewer_Record_Type=HUMAN row in "
                     "reviewer_registry.csv" % rid)
                withheld.add(pid)
                continue
            when = _s(row.get("Reviewed_At"))
            try:
                stamped = datetime.datetime.fromisoformat(
                    when.replace("Z", "+00:00"))
            except ValueError:
                flag(line, "BAD_REVIEWED_AT",
                     "Reviewed_At=%r is not an ISO timestamp" % when)
                withheld.add(pid)
                continue
            if stamped.date() > today:
                flag(line, "BAD_REVIEWED_AT",
                     "Reviewed_At=%s is in the future" % when)
                withheld.add(pid)
                continue
            if verdict == "REJECTED":
                row_ = cells[iid]
                flag("%s/%s" % (_s(row_.get("Unit_ID")),
                                _s(row_.get("Cell_Key"))),
                     "INFERENCE_REJECTED",
                     "the person who looked at this reconstruction refused it; "
                     "the value is not accepted and the panel is not held for it")
                rejected.add((pid, iid))
    return withheld, rejected


def collect_inference_manifests(run_dir, artifacts=None, ledger=None):
    """Every reconstructed cell this run wrote, in one list, for the template.

    Read off the ledger rather than by globbing the directory: the ledger is what
    the finalizer checks, so a file sitting in `inference-review/` that no panel
    registered would produce a template row for a cell nobody will be asked
    about.
    """
    # THE VERIFIED LEDGER WHEN THE CALLER HAS ONE. v8.3: the preflight called
    # this with a run directory and nothing else, so the one diagnosis a reviewer
    # is told to require - "0 bundle problems" - was built by re-reading the
    # ledger AND the manifests it points at, two reads after the verdict above it
    # was decided. The template command has no verified run and still passes a
    # path, which is what the fallback is for.
    if ledger is None:
        try:
            ledger = pd.read_csv(os.path.join(run_dir, "panel_artifacts.csv"),
                                 dtype=object).fillna("")
        except Exception:
            return []
    out = []
    for _, art in ledger.iterrows():
        if _s(art.get("Artifact_Type")) != RB.INFERENCE_ARTIFACT_TYPE:
            continue
        path, blob = artifact_data(run_dir, art, artifacts)
        if path is None or blob is None:
            continue
        try:
            out.extend(list(csv.DictReader(io.StringIO(blob.decode("utf-8")))))
        except Exception:
            continue
    return sorted(out, key=lambda r: (_s(r.get("Panel_ID")),
                                      _s(r.get("Cell_Key"))))


def _inference_manifest_ids(run_dir, artifact, pid, flag, artifacts=None):
    """The Inference_IDs the run listed for one panel, or None if unreadable."""
    path, blob = artifact_data(run_dir, artifact, artifacts)
    if path is None or blob is None:
        flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISSING",
             "the inference manifest %s names for %s is not in the run"
             % (_s(artifact.get("Artifact_Path")) or "(blank)", pid))
        return None
    try:
        rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8"))))
    except Exception as exc:
        flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISSING",
             "%s's inference manifest could not be parsed (%s: %s)"
             % (pid, type(exc).__name__, exc))
        return None
    return {_s(r.get("Inference_ID")) for r in rows}


def method_contract_failures(machine, queue, ledger_rows, run_dir, flag,
                             frames, artifacts=None):
    """Panels whose values claim a method their reader could not have reached.

    Two checks, and the second is the one with teeth.

    ## The pair against the reader

    `provenance.METHOD_CONTRACT` says which (identity, value) pairs each mark
    type produces. A row claiming `MEASURED_LINE_STYLE` on a `BOX_VIOLIN` panel,
    or `HUMAN_RESOLUTION` on a `LINE_COLOR` one, did not come from the reader the
    queue says read it - and every hash in the run is correct, because whoever
    produced it wrote it that way from the start. Blank and unregistered methods
    are already refused by tier; this closes the pairs that are registered,
    priced cheaply, and impossible.

    ## The pair against the evidence

    A pair the reader COULD have produced still has to be the one THIS row's
    evidence supports, and only a durable artifact can say. `BAR_MONO` has one:
    `mono_bar_geometry.csv` carries `Auto_Identity_Method` per row inside
    `Auto_Identity_SHA256`, so a value claiming it read a bar's fill in relation
    to its own group, for a bar the figure actually named by matching another
    group's prototypes, is refused here - R0 bought at R2's expense.

    `HUMAN_RESOLUTION` is checked the other way round: it is R0, and the only
    thing that makes it R0 is that a registered person signed a resolution row
    with evidence behind it. So it must arrive with `Identity_Source=HUMAN` and a
    `Resolution_ID`, which `identity_contract_failures` then joins to the
    resolution and its evidence file.

    The other five readers have no comparable artifact, and this function does
    not pretend otherwise.
    """
    withheld = set()
    mark_of = {_s(r.get("Panel_ID")): _s(r.get("Mark_Type")).upper()
               for _, r in queue.iterrows()}
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    for row in rows:
        pid = _s(row.get("Run_Panel_ID"))
        mark = mark_of.get(pid)
        if not mark:
            continue
        identity = _s(row.get("Identity_Method"))
        value = _s(row.get("Value_Method"))
        # A pair with a blank half is refused by tier already, with a clearer
        # reason than this one could give: "nothing says how this number was
        # got" is what a reviewer needs to read, not "LINE_COLOR does not
        # produce blank/MARKER_CENTER". Both findings are true; the tier gate
        # has the useful one, and two flags on one row is one too many.
        if not (identity and value):
            continue
        why = (PROV.contract_failure(mark, identity, value)
               or PROV.dispersion_contract_failure(
                   mark, _s(row.get("Dispersion_Method"))))
        if why:
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_NOT_POSSIBLE_FOR_READER", why)
            withheld.add(pid)
        if identity == "HUMAN_RESOLUTION" and (
                _s(row.get("Identity_Source")).upper() != "HUMAN"
                or not _s(row.get("Resolution_ID"))):
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_NOT_POSSIBLE_FOR_READER",
                 "Identity_Method=HUMAN_RESOLUTION with Identity_Source=%s and "
                 "Resolution_ID=%s. It is R0 because a registered person signed "
                 "a resolution row with evidence behind it, and this row cites "
                 "neither" % (_s(row.get("Identity_Source")) or "(blank)",
                              _s(row.get("Resolution_ID")) or "(blank)"))
            withheld.add(pid)
    withheld |= _geometry_route_failures(machine, ledger_rows, run_dir, flag,
                                         artifacts=artifacts)
    withheld |= _point_route_failures(machine, ledger_rows, run_dir, flag,
                                      artifacts=artifacts)
    withheld |= _mark_evidence_failures(machine, queue, ledger_rows, run_dir,
                                        flag, panel_expectations(frames),
                                        artifacts=artifacts)
    return withheld


#: The value columns a MARK's own measurement decides, and the mark field each
#: one is copied from by `mark_readers.to_value_records`. Asserted against that
#: function by the suite rather than trusted: a reader that starts carrying a
#: tenth number would otherwise be bound to the mark in nine.
MARK_VALUE_FIELDS = (
    ("Mean", "mean"),
    ("Dispersion_Value", "dispersion"),
    ("Errorbar_Lower", "errorbar_lower"),
    ("Errorbar_Upper", "errorbar_upper"),
    ("Median", "median"),
    ("Q1", "q1"),
    ("Q3", "q3"),
    ("Whisker_Lower", "whisker_lower"),
    ("Whisker_Upper", "whisker_upper"),
)


def panel_expectations(frames):
    """{Panel_ID: {cell_map, envelope}} - what a panel's marks must look like.

    Two questions with one answer each, built together because both are
    re-derivations of the same declaration: which cell a mark's series and
    position name, and under what conditions the panel was measured.

    The envelope half is the one the mark hashes rest on. `Mark_Record_SHA256`
    covers the panel box, both calibrations and the raster hash - correctly, a
    pixel is only a measurement relative to them - and until v7.80 the finalizer
    re-hashed those from the ARTIFACT'S OWN copy of them. A producer could
    therefore declare one tick mapping in `panel_manifest.csv`, read the figure
    under another, hash the marks under the second, and hand over a run in which
    the marks, the values and both hashes agreed with each other perfectly. The
    only thing that disagreed was the manifest the run was validated against, and
    nothing compared them.

    `None` for a panel the run manifest has no row for: a value citing marks from
    a panel this run does not say it read is refused rather than measured against
    a declaration nobody made.

    `frames` carries both halves of what was verified: the manifest frames the
    run was validated against, and under `outputs` the rows of the run's own
    outputs as they were when their bytes were hashed.
    """
    maps = cell_maps(frames)
    panels = {}
    if frames is not None and "panels" in frames:
        panels = {_s(p.get("Panel_ID")): p
                  for _, p in frames["panels"].iterrows()}
    # The declared rows the measurement digest is taken over, grouped the way
    # the runner groups them.
    series_by_panel, positions_by_panel, configs_by_id = {}, {}, {}
    for key, target, group in (("series", series_by_panel, "Panel_ID"),
                               ("positions", positions_by_panel, "Panel_ID"),
                               ("configs", configs_by_id, "Config_ID")):
        frame = (frames or {}).get(key)
        if frame is None:
            continue
        for _, row in frame.iterrows():
            target.setdefault(_s(row.get(group)), []).append(row)
    # THE ROWS `verify_run_outputs` HASHED, not the path opened again. Read here
    # a second time, a save landing in between would have this module comparing
    # an artifact against a declaration nobody verified.
    run_rows = {_s(row.get("Panel_ID")): row
                for row in (frames or {}).get("outputs", {})
                .get("run_manifest.csv", [])}
    out = {}
    for pid in set(maps) | set(panels) | set(run_rows):
        envelope = None
        panel, run_row = panels.get(pid), run_rows.get(pid)
        if panel is not None and run_row is not None:
            try:
                envelope = RB.mark_envelope_header(
                    panel, _s(run_row.get("Image_SHA256")),
                    _s(run_row.get("Reader_Version")),
                    series_rows=series_by_panel.get(pid, []),
                    position_rows=positions_by_panel.get(pid, []),
                    config_rows=configs_by_id.get(
                        _s(panel.get("Config_ID")), []))
            except Exception:
                # A box that does not parse or ticks that will not fit: the run
                # refused this panel long before here, and a value that reached
                # this module claiming marks from it has no declaration behind
                # it. Left as None, which is refused rather than compared.
                envelope = None
        out[pid] = {"cell_map": maps.get(pid, EMPTY_CELL_MAP),
                    "envelope": envelope,
                    "context": (None if envelope is None else
                                _verifier_context(
                                    envelope, panel,
                                    positions_by_panel.get(pid, []),
                                    configs_by_id.get(
                                        _s(panel.get("Config_ID")), []),
                                    series_by_panel.get(pid, [])))}
    return out


def _verifier_context(envelope, panel, position_rows, config_rows,
                      series_rows=()):
    """What a verifier may re-derive a mark against: the run's own declaration.

    A SUPERSET of the hashed envelope, and deliberately not part of it. The
    envelope is what the artifact must carry and agree with; this is what THIS
    MODULE knows from the manifests and hands to the re-derivation, and adding
    the anchors to the artifact instead would only give a producer one more
    field to write correctly.

    The anchors are what `bar_reader` assigns x labels from - nearest declared
    column within a tolerance - so with them a verifier can ask whether a mark
    is at the position it says it is, rather than taking the label's word for
    it. `Baseline_Value` is where a bar is measured FROM, which decides both
    which end of the body is the data end and which side of it a cap can be on.
    """
    anchors = {}
    for row in position_rows:
        pixel = PROV.finite_number(row.get("X_Pixel"))
        if pixel is not None:
            anchors[_s(row.get("Position_ID"))] = pixel
    tolerance = None
    for row in config_rows:
        if _s(row.get("Option")) != "slot_tolerance_px":
            continue
        try:
            # THE DECLARED PARSER, not `float()`: the run reads this option
            # through `READER_OPTIONS` and a second reading of the same text is
            # a second chance to disagree about it.
            tolerance = BM.READER_OPTIONS["slot_tolerance_px"][0](
                row.get("Value"))
        except Exception:
            tolerance = None
    # WHICH MASK EACH SERIES IS. `bar_reader` finds a bar in the mask its series
    # declares - a named built-in under `Mask_Key`, or one built from
    # `Colour_Hex` and keyed by the series id - and records which one it was
    # found in. Without the declaration here, "found in its own mask" could only
    # be checked against the mark's word for what its own mask is.
    discriminants = {}
    for row in series_rows:
        sid = _s(row.get("Series_ID"))
        discriminants[sid] = {
            "Mask_Key": _s(row.get("Mask_Key")),
            "Colour_Hex": _s(row.get("Colour_Hex")),
            "Expected_Mask": _s(row.get("Mask_Key")) or sid,
            # And what a MONOCHROME series is told apart by, which is a marker
            # rather than a colour: the shape the manifest declares, or the fill
            # when every series is the same shape.
            "Marker_Shape": _s(row.get("Marker_Shape")),
            "Marker_Fill": _s(row.get("Marker_Fill")),
            "Line_Style": _s(row.get("Line_Style")),
        }
    return dict(envelope, Position_Anchors=anchors,
                Slot_Tolerance_Px=tolerance,
                Series_Discriminants=discriminants,
                Baseline_Value=_s(panel.get("Baseline_Value")))


def _canonical(value):
    """Comparable across a JSON round trip, and across int/float spelling.

    `12` and `12.0` are the same pixel, and a producer that writes its panel box
    as floats has not measured under a different box - refusing it would be this
    module inventing a disagreement out of a JSON encoder's habits. Strings stay
    exact: `LINEAR` and `linear` are two declarations.
    """
    def norm(item):
        if isinstance(item, bool):
            return item
        if isinstance(item, (int, float)):
            return float(item)
        if isinstance(item, dict):
            return {k: norm(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [norm(v) for v in item]
        return item

    return json.dumps(norm(value), sort_keys=True, default=float)


def _same_number(text, number):
    """Is this value column the mark's own number?

    Compared as NUMBERS, not as text: the run wrote a float through pandas and
    this reads a string back, so "12.0" and 12.0 are the same measurement while
    "12.0" and 12.5 are not. Blank on the value side is skipped by the caller -
    a statistic a row does not carry is not a contradiction - but a blank MARK
    under a number is one, and lands here as a mismatch.
    """
    if number is None:
        return False
    try:
        return float(text) == float(number)
    except (TypeError, ValueError):
        return False


def _expected_cell_key(mark, cell_map):
    """The `Cell_Key` this mark's own series and position ids name.

    `run_batch._read_panel` builds the key by looking each id up in the panel's
    series and position manifests; this repeats that lookup on the VERIFIED
    frames. Returns (key, problem) and never guesses: an id no manifest declares
    gives no key, because a key derived from a mapping nobody approved would
    agree with whatever the value happened to say.
    """
    levels = {}
    sid, qid = _s(mark.get("series")), _s(mark.get("x_label"))
    if sid:
        if sid not in cell_map["series_levels"] or not cell_map["series_factor"]:
            return None, ("the mark was read as series %s and the verified "
                          "manifests declare no such series for this panel" % sid)
        levels[cell_map["series_factor"]] = cell_map["series_levels"][sid]
    if qid:
        if qid not in cell_map["position_levels"] \
                or not cell_map["position_factor"]:
            return None, ("the mark sits at position %s and the verified "
                          "manifests declare no such position for this panel"
                          % qid)
        levels[cell_map["position_factor"]] = cell_map["position_levels"][qid]
    if not levels:
        return None, ("the mark carries neither a series nor a position, so "
                      "there is no cell it can be the measurement of")
    return GE.fig_cell_key(levels), None


def _mark_evidence_failures(machine, queue, ledger_rows, run_dir, flag,
                            expected, artifacts=None):
    """Values joined to the MARK they were made from, and checked against it.

    The matrix says which methods a reader can produce. This says which one THIS
    row's own evidence came to - the difference between "possible" and "true", and
    the thing five of the seven readers had no durable artifact for.

    ## The mark is checked against itself first

    Both of a mark's hashes are RECOMPUTED from its own fields before it is
    indexed. Until v7.74 they were read off the artifact and only the value's
    copy was ever recomputed, so a doctored measurement whose hash was updated to
    match it joined perfectly: the artifact was self-consistent and the value
    agreed with it, and the only thing that would have disagreed - the pixels the
    mark was measured from - was not in the comparison. The record hash covers
    the panel box, the calibration and the raster hash for exactly that reason.

    ## Then the value is checked against the mark

        the mark exists       a value citing a `Mark_Record_SHA256` no raw-mark
                              artifact carries is a value with no evidence
        one mark, one value   two values citing one mark means one of them was
                              made from something else
        the methods agree     exactly, blank included: an artifact that says
                              nothing does not support a claim
        the attestation holds recomputed from the mark's own fields, so swapping
                              a method inside the artifact is caught too
        THE NUMBERS AGREE     `Mean`, the dispersion, the bounds and the
                              quartiles are the mark's own, compared as numbers
        THE CELL AGREES       the mark's series and position ids, looked up in
                              the verified manifests, name this row's `Cell_Key`

    The last two are what makes this a value-to-cell join rather than a
    method-provenance one. Without them two values in one panel that were read
    the same way could EXCHANGE their marks and every check above still passed:
    both hashes existed, neither was shared, the methods matched because they
    were identical, and nothing compared the numbers. A `Cell_Key` swap had no
    arithmetic signature at all.

    Panels whose mark type has an `EVIDENCE_VERIFIER` get one more: the three
    methods are RE-DERIVED from the measurements and compared. The rest are held
    to the join, which is weaker and is not pretended otherwise.
    """
    withheld = set()
    mark_of = {_s(r.get("Panel_ID")): _s(r.get("Mark_Type")).upper()
               for _, r in queue.iterrows()}
    by_hash, duplicated = {}, set()
    joinable = set()                  # panels whose marks can be joined to
    for _, art in ledger_rows.iterrows():
        if _s(art.get("Artifact_Type")) != "RAW_MARKS":
            continue
        path, blob = artifact_data(run_dir, art, artifacts)
        if path is None or blob is None:
            continue
        try:
            envelope = json.loads(blob.decode("utf-8"))
        except Exception:
            continue                  # verify_run_outputs owns unreadable bytes
        panel = _s(envelope.get("Panel_ID")) or _s(art.get("Panel_ID"))
        if _s(envelope.get("schema")) != RB.MARK_DATA_SCHEMA:
            # AN OLDER PRODUCER, AND THE JOIN IS NOT THERE. Skipped until v7.75,
            # which made every check above conditional on the producer's own
            # choice of schema: a run written to `mark-data/1` had no join, no
            # numbers compared and no cell derived, and finalized on the method
            # matrix alone. The version that cannot be checked is the version
            # that must not be finalized.
            flag("panel:%s" % panel, "MARK_EVIDENCE_SCHEMA_UNSUPPORTED",
                 "%s's raw marks are written as %s and this module can only "
                 "join %s; a value cannot be checked against a mark whose "
                 "record hash does not exist"
                 % (panel, _s(envelope.get("schema")) or "(no schema)",
                    RB.MARK_DATA_SCHEMA))
            withheld.add(panel)
            continue
        # THE CONDITIONS THE MARKS WERE MEASURED UNDER, against the ones the
        # run was validated against. Everything below re-hashes the envelope's
        # own copy of the box, the calibrations and the raster hash, so an
        # artifact that is internally perfect and externally undeclared passed
        # every check in this function.
        want = expected.get(panel, {}).get("envelope")
        if want is None:
            flag("panel:%s" % panel, "MARK_ENVELOPE_CONTRADICTS_RUN",
                 "%s's raw marks cite a panel this run's manifests do not "
                 "declare, so there is nothing to check the conditions they "
                 "were measured under against" % (panel or "(unnamed)"))
            withheld.add(panel)
            continue
        got = {k: envelope.get(k) for k in RB.MARK_ENVELOPE_FIELDS}
        if _canonical(got) != _canonical(want):
            differ = [k for k in RB.MARK_ENVELOPE_FIELDS
                      if _canonical(got.get(k)) != _canonical(want.get(k))]
            flag("panel:%s" % panel, "MARK_ENVELOPE_CONTRADICTS_RUN",
                 "%s's marks were measured under a %s this run did not declare "
                 "(%s against %s). Every hash below rests on these numbers, so "
                 "an artifact that agrees with itself about them still has to "
                 "agree with the manifests"
                 % (panel, ", ".join(differ),
                    "; ".join(_canonical(got.get(k))[:60] for k in differ),
                    "; ".join(_canonical(want.get(k))[:60] for k in differ)))
            withheld.add(panel)
            continue
        joinable.add(panel)
        header = {k: v for k, v in envelope.items() if k != "marks"}
        for mark in envelope.get("marks") or []:
            # RECOMPUTED, and the recomputed value is what the index is keyed by.
            # A mark whose stated hash was edited to match an edited measurement
            # would otherwise be found under the name it gave itself.
            key = RB.mark_record_sha256(mark, header)
            if _s(mark.get("Mark_Record_SHA256")) != key:
                flag("panel:%s" % panel, "MARK_RECORD_HASH_MISMATCH",
                     "a mark in %s's raw marks does not hash to the "
                     "Mark_Record_SHA256 it carries (%s... against %s...); its "
                     "measurement, its calibration or its panel box was changed "
                     "after the run"
                     % (panel, key[:16],
                        _s(mark.get("Mark_Record_SHA256"))[:16] or "(blank)"))
                withheld.add(panel)
                continue
            if _s(mark.get("Method_Attestation_SHA256")) \
                    != RB.method_attestation_sha256(mark, key):
                flag("panel:%s" % panel, "METHOD_ATTESTATION_STALE",
                     "mark %s... in %s's raw marks carries methods that do not "
                     "hash to its own attestation; one of them was rewritten "
                     "after the run" % (key[:16], panel))
                withheld.add(panel)
                continue
            if key in by_hash:
                duplicated.add(key)
            by_hash[key] = (panel, mark)
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    claimed_by = {}
    for row in rows:
        pid = _s(row.get("Run_Panel_ID"))
        key = _s(row.get("Mark_Record_SHA256"))
        if not key:
            # A BLANK IS NOT AN EXEMPTION. Skipped until v7.75 as "a reader that
            # does not stamp its marks", which was true of every reader once and
            # is true of none of the five now - so the blank that used to mean
            # "this reader has not been taught" came to mean "this value opted
            # out of the only evidence it has". `PROV.MARK_JOIN_REQUIRED` names
            # the readers with no other durable route; a panel that HAS joinable
            # marks is held to them whatever its type, because the run itself
            # says the evidence was there to cite.
            if mark_of.get(pid) in PROV.MARK_JOIN_REQUIRED or pid in joinable:
                flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                     "MARK_EVIDENCE_MISSING",
                     "this value carries no Mark_Record_SHA256, and %s"
                     % ("its panel's raw marks carry one for every mark in it"
                        if pid in joinable else
                        "a %s value has no durable evidence of its own besides "
                        "the mark it was read from" % mark_of.get(pid)))
                withheld.add(pid)
            continue
        if not by_hash and mark_of.get(pid) not in PROV.MARK_JOIN_REQUIRED \
                and pid not in joinable:
            continue                  # nothing in this run to join against
        claimed_by.setdefault(key, []).append(row)
    for key, sharing in sorted(claimed_by.items()):
        if len(sharing) > 1:
            for row in sharing:
                flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                     "MARK_EVIDENCE_SHARED",
                     "%d values cite the same mark %s; one printed mark is one "
                     "measurement, and which of them it belongs to cannot be "
                     "decided by row order" % (len(sharing), key[:16]))
                withheld.add(_s(row.get("Run_Panel_ID")))
    for key, sharing in sorted(claimed_by.items()):
        row = sharing[0]
        pid = _s(row.get("Run_Panel_ID"))
        where = "%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key")))
        if key in duplicated:
            flag(where, "MARK_EVIDENCE_MISSING",
                 "the raw marks carry %s twice, so the mark this value was made "
                 "from cannot be identified" % key[:16])
            withheld.add(pid)
            continue
        if key not in by_hash:
            flag(where, "MARK_EVIDENCE_MISSING",
                 "this value cites mark %s and no raw-mark artifact in the run "
                 "carries it" % key[:16])
            withheld.add(pid)
            continue
        mark_panel, mark = by_hash[key]
        if mark_panel and pid and mark_panel != pid:
            flag(where, "MARK_EVIDENCE_MISSING",
                 "this value is filed under %s and the mark it cites was read "
                 "from %s" % (pid, mark_panel))
            withheld.add(pid)
            continue
        wrong = [f for f in PROV.METHOD_FIELDS
                 if _s(row.get(f)) != _s(mark.get(f))]
        if wrong:
            flag(where, "METHOD_CONTRADICTS_MARK",
                 "the value and the mark it was made from disagree about %s (%s "
                 "against %s)"
                 % (", ".join(wrong),
                    "/".join(_s(row.get(f)) or "nothing" for f in wrong),
                    "/".join(_s(mark.get(f)) or "nothing" for f in wrong)))
            withheld.add(pid)
            continue
        want = RB.method_attestation_sha256(mark, key)
        if _s(row.get("Method_Attestation_SHA256")) != want:
            flag(where, "METHOD_ATTESTATION_STALE",
                 "the methods on this mark do not hash to the attestation the "
                 "value carries; something rewrote one of them after the run")
            withheld.add(pid)
            continue
        # THE NUMBERS. A value column this row does not carry is not a
        # contradiction - `to_value_records` writes the quartiles for a quantile
        # summary and the mean for a continuous one, and neither is missing the
        # other's - but a number that is NOT the mark's own is one, and this is
        # the only check that can see it.
        off = [(col, row.get(col), mark.get(field))
               for col, field in MARK_VALUE_FIELDS
               if not BM.blank(row.get(col))
               and not _same_number(row.get(col), mark.get(field))]
        if off:
            flag(where, "VALUE_CONTRADICTS_MARK",
                 "the value and the mark it cites disagree about %s"
                 % "; ".join("%s (%s against the mark's %s)"
                             % (col, _s(text) or "(blank)",
                                "(nothing)" if number is None else number)
                             for col, text, number in off))
            withheld.add(pid)
            continue
        # AND THE CELL. The mark's own series and position ids, looked up in the
        # manifests the run was validated against - so a value that carries the
        # right number under the wrong heading is refused, which is the one
        # failure with no arithmetic signature.
        wanted, why = _expected_cell_key(
            mark, expected.get(pid, {}).get("cell_map", EMPTY_CELL_MAP))
        if why:
            flag(where, "MARK_CELL_UNDECLARED", why)
            withheld.add(pid)
            continue
        if _s(row.get("Cell_Key")) != wanted:
            flag(where, "CELL_CONTRADICTS_MARK",
                 "this value is filed under %s and the mark it cites was read "
                 "from the cell the manifests call %s"
                 % (_s(row.get("Cell_Key")) or "(blank)", wanted))
            withheld.add(pid)
            continue
        code, why = PROV.evidence_failure(
            mark_of.get(pid), mark, row,
            context=expected.get(pid, {}).get("context"))
        if code:
            flag(where, code, why)
            withheld.add(pid)
    return withheld


def _point_route_failures(machine, ledger_rows, run_dir, flag,
                          artifacts=None):
    """Association rows whose identity disagrees with their own point cloud.

    The scatter reader names each POINT and `_scatter_outcome` copies the answer
    onto the summary; from v7.70 the point file records it too, so the copy can be
    checked against the cloud it was copied from. A summary claiming
    `MEASURED_COLOUR` over points read from a grey threshold was un-refutable
    while the artifact carried only coordinates.
    """
    withheld = set()
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    # THE LEDGER ROW A VALUE'S REFERENCE NAMES, matched on the run-relative path
    # the ledger recorded rather than on a realpath computed now. A value cites
    # `Point_Data_Reference`; the ledger says which artifact that is; the
    # snapshot is keyed on the ledger's identity. Nothing in that chain asks the
    # filesystem what a symlink currently points at.
    def _norm(text):
        return _s(text).replace("\\", "/").strip("/")

    by_reference = {}
    for _, art in ledger_rows.iterrows():
        if _s(art.get("Artifact_Type")) != "POINT_DATA":
            continue
        for alias in (_norm(art.get("Artifact_Path")),
                      _norm(art.get("Artifact_Reference"))):
            if alias:
                by_reference[alias] = art
    for row in rows:
        identity = _s(row.get("Identity_Method"))
        reference = _s(row.get("Point_Data_Reference"))
        if not identity or not reference:
            continue
        art = by_reference.get(_norm(reference))
        if art is None:
            continue                  # not a point-backed row, or not in the run
        path, blob = artifact_data(run_dir, art, artifacts)
        if blob is None:
            continue
        try:
            cloud = json.loads(blob.decode("utf-8"))
            # RE-DERIVED FROM THE POINTS, not read off the record. The writer
            # leaves the record-level field EMPTY when its points disagree, and a
            # check that only compared non-blank answers read that silence as
            # consent: a cloud that could not agree how its series was named
            # bought whatever the association row claimed.
            point_methods = {_s(pt.get("Identity_Method"))
                             for pt in (cloud.get("points") or [])}
            said = _s(cloud.get("Identity_Method"))
        except Exception as exc:
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_CONTRADICTS_POINTS",
                 "the point cloud this association was computed from could not "
                 "be read (%s: %s)" % (type(exc).__name__, exc))
            withheld.add(_s(row.get("Run_Panel_ID")))
            continue
        if len(point_methods) != 1 or not next(iter(point_methods)):
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_EVIDENCE_UNRESOLVED",
                 "the association says its series was named by %s and its point "
                 "cloud does not agree with itself about that (%s). A claim its "
                 "own evidence cannot support is not a claim this module may "
                 "accept" % (identity, ", ".join(sorted(m or "(blank)"
                                                        for m in point_methods))
                             or "no points"))
            withheld.add(_s(row.get("Run_Panel_ID")))
            continue
        sole = next(iter(point_methods))
        if said != sole or identity != sole:
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_CONTRADICTS_POINTS",
                 "the association says %s, its point file's record says %s, and "
                 "every point in it says %s"
                 % (identity, said or "(blank)", sole))
            withheld.add(_s(row.get("Run_Panel_ID")))
    return withheld


def _geometry_route_failures(machine, ledger_rows, run_dir, flag,
                             artifacts=None):
    """BAR_MONO values whose route disagrees with the figure's own answer."""
    withheld = set()
    by_row_hash = {}
    for _, art in ledger_rows.iterrows():
        if _s(art.get("Artifact_Type")) != "MONO_BAR_GEOMETRY":
            continue
        path, blob = artifact_data(run_dir, art, artifacts)
        if path is None or blob is None:
            continue
        try:
            for geo in csv.DictReader(io.StringIO(blob.decode("utf-8"))):
                by_row_hash[_s(geo.get("Geometry_Row_SHA256"))] = geo
        except Exception as exc:
            flag("run", "METHOD_NOT_POSSIBLE_FOR_READER",
                 "the geometry file could not be read, so no BAR_MONO route "
                 "can be checked against it (%s: %s)"
                 % (type(exc).__name__, exc))
        break
    if not by_row_hash:
        return withheld
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    for row in rows:
        identity = _s(row.get("Identity_Method"))
        # A human resolution is not in the geometry file by construction - that
        # file carries what the FIGURE said - and is checked against the
        # resolution rows instead.
        if not identity or identity == "HUMAN_RESOLUTION":
            continue
        geo = by_row_hash.get(_s(row.get("Geometry_Row_SHA256")))
        if geo is None:
            continue
        said = _s(geo.get("Auto_Identity_Method"))
        # BLANK IS A CONTRADICTION HERE. A geometry row exists for this bar and
        # says nothing about the route the figure took to name it, while the value
        # claims one - so the claim has no evidence rather than disagreeing
        # evidence, and reading the silence as consent is the fail-open this whole
        # function exists to close. A row that names no pattern at all is skipped
        # above; this one did name a pattern.
        if said != identity:
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_CONTRADICTS_GEOMETRY",
                 "the value says the figure named this bar by %s and the "
                 "geometry file this run wrote says %s. The route decides the "
                 "review tier, and the file that recorded it is attested"
                 % (identity, said or "nothing"))
            withheld.add(_s(row.get("Run_Panel_ID")))
    return withheld


#: What a run may declare about who is allowed to sign it. `NOT_DECLARED` is the
#: default and the honest name for it: the package has NOT decided whether one
#: person may both resolve an identity and approve the panel that rests on it,
#: and a default that silently permits it should say so rather than call itself
#: something reassuring.
#:
#: `DISTINCT_RESOLVER_APPROVER` is the contract the first pilot runs under. It is
#: a per-RUN declaration, not a per-publication rule: any run may ask for it, and
#: what it asks for is the same thing everywhere - the person who wrote a series
#: name into `identity_resolution.csv` is not the person who signs the panel that
#: name lands in.
SEPARATION_POLICIES = ("NOT_DECLARED", "DISTINCT_RESOLVER_APPROVER")
DISTINCT_RESOLVERS = "DISTINCT_RESOLVER_APPROVER"
NO_POLICY = "NOT_DECLARED"


def canonical_policy(declared):
    """The policy this finalization runs under, or None if it is not one of ours.

    v7.96 defined `SEPARATION_POLICIES` and then never consulted it: enforcement
    was a single `== DISTINCT_RESOLVER_APPROVER`, and the stamp recorded whatever
    string the caller passed. So a library caller could write

        finalize(run_dir, separation_policy="DISTINCT_REVIEWERS")

    and get an accepted file whose stamp names a strict-sounding policy that was
    never applied - the worst shape a governance record can take, because it is
    the record itself that is wrong. A vocabulary that is declared and not
    checked is a comment.
    """
    text = _s(declared) or NO_POLICY
    return text if text in SEPARATION_POLICIES else None


def manifest_directory(run_dir, manifest_dir=None, run_stamp=None):
    """Where this run's manifests are, in the order that survives a moved run.

    The stamp records an ABSOLUTE path, so a run folder handed to somebody else
    names a directory on the machine that produced it; a `manifests/` directory
    inside the run is the one answer that travels with it. Hence: what the caller
    said, then the copy inside the run, then the stamp, then the copy inside the
    run again as the path to name in the error.

    ONE IMPLEMENTATION, because the preflight needs the same answer. v7.97's
    `--second` resolved it as `--manifests or RUN/manifests`, missing the stamp
    fallback - so on a run whose manifests live outside it the registry came back
    unreadable, `second_problems` skipped its HUMAN check without saying so, and
    an unregistered second reader passed the one flag that exists to catch them.
    A second copy of a path rule is a second answer to the same question.
    """
    run_stamp = run_stamp or {}
    inside = os.path.join(run_dir, "manifests")
    return (manifest_dir
            or (inside if os.path.isdir(inside) else "")
            or _s(run_stamp.get("Manifest_Dir"))
            or inside)


def person_keys(reviewers):
    """Reviewer_ID -> the PERSON behind it, where the registry can prove one.

    `Reviewer_ID` identifies a ROW, not a human being, and the registry only
    refuses a duplicated ID. Register one person twice under two IDs and a check
    that compares IDs reports two people:

        RV_RESOLVER   ORCID 0000-0002-1825-0097
        RV_APPROVER   ORCID 0000-0002-1825-0097

    So the key is the CONTACT, normalized. An ORCID identifies a PERSON; an email
    address identifies a mailbox somebody may share, hand over or change, and two
    different addresses prove nothing about two different people. That is why the
    separation contract requires an ORCID on both sides and refuses rather than
    guessing when one is missing - see `REVIEWER_IDENTITY_UNPROVABLE`. A reviewer
    with no usable contact gets no key at all, and the caller decides what that
    means.
    """
    out = {}
    if reviewers is None or "Reviewer_ID" not in getattr(reviewers, "columns", ()):
        return out
    for _, r in reviewers.iterrows():
        ctype = _s(r.get("Contact_Type")).upper()
        contact = _s(r.get("Reviewer_Contact"))
        rid = _s(r.get("Reviewer_ID"))
        if not rid or not contact:
            continue
        if ctype == "ORCID":
            out[rid] = "ORCID:%s" % contact.upper()
        elif ctype == "EMAIL":
            out[rid] = "EMAIL:%s" % contact.lower()
    return out


def resolution_reviewers(run_dir, ledger_rows, artifacts=None):
    """Panel_ID -> the Reviewer_IDs that named a series by hand on that panel.

    Read off the `IDENTITY_RESOLUTION` artifact the run copied in, which
    `verify_run_outputs` has already re-hashed, rather than off the manifest
    directory: the question is who signed the resolutions THIS RUN was read
    under.
    """
    out = {}
    for _, art in ledger_rows.iterrows():
        if _s(art.get("Artifact_Type")) != RB.IDENTITY_ARTIFACT_TYPE:
            continue
        path, blob = artifact_data(run_dir, art, artifacts)
        if path is None or blob is None:
            continue
        try:
            rows = pd.read_csv(io.BytesIO(blob), dtype=object).fillna("")
        except Exception:
            continue
        for _, row in rows.iterrows():
            rid = _s(row.get("Reviewer_ID"))
            if rid:
                out.setdefault(_s(art.get("Panel_ID")), set()).add(rid)
    return out


def approved_panels(reviews, queue, reviewers, flag, today=None,
                    artifact_types=None, extra_confirmations=None,
                    resolvers=None, separation_policy=None, people=None):
    """Panel_ID -> the review row that approves it. Everything else is refused.

    `extra_confirmations` is {Panel_ID: (column, ...)} for the questions this
    panel's own VALUES ask on top of the ones its mode asks - see
    `RB.inference_confirmations`. Passed in rather than read off the queue: the
    queue prints the count for a reviewer to see, and a requirement a run could
    lower by printing a different number is not a requirement.
    """
    today = today or datetime.date.today()
    human = human_reviewers(reviewers)
    expected = {_s(r.get("Panel_ID")): _s(r.get("Review_Subject_SHA256"))
                for _, r in queue.iterrows()}
    # What each queued panel said a reviewer would be looking at. A scatter used
    # to reach the queue with `Overlay_File=""`, so "open the overlay and
    # approve only if every mark sits where a reader would put it" pointed at
    # nothing. The queue now declares its review mode, and the ledger - already
    # re-hashed by `verify_run_outputs` - is what says the artifact is there.
    # Checking the ledger rather than the queue's own path column is also what
    # lets a run directory be moved: the ledger's paths are run-relative.
    review_mode = {_s(r.get("Panel_ID")): _s(r.get("Review_Mode"))
                   for _, r in queue.iterrows()}
    artifact_types = artifact_types or {}

    # A duplicated decision voids the panel outright. Keeping the first made a
    # scientific result depend on CSV row order: APPROVED then REJECTED
    # approved, REJECTED then APPROVED did not.
    counts, id_counts = {}, {}
    for _, r in reviews.iterrows():
        counts[_s(r.get("Panel_ID"))] = counts.get(_s(r.get("Panel_ID")), 0) + 1
        id_counts[_s(r.get("Review_ID"))] = id_counts.get(
            _s(r.get("Review_ID")), 0) + 1
    voided = {p for p, n in counts.items() if p and n > 1}
    for panel in sorted(voided):
        flag("panel:%s" % panel, "DUPLICATE_REVIEW",
             "%d decisions exist for this panel; none is applied, because "
             "which one wins would otherwise be the order of the rows"
             % counts[panel])
    # A Review_ID identifies a decision. Two decisions wearing one identifier
    # cannot be told apart in an audit, so neither is applied.
    reused = {i for i, n in id_counts.items() if i and n > 1}
    for review_id in sorted(reused):
        flag("review:%s" % review_id, "DUPLICATE_REVIEW_ID",
             "%d rows share this Review_ID; none of them is applied" % id_counts[review_id])

    out = {}
    for i, r in reviews.iterrows():
        line = "review:%d" % (i + 2)
        pid = _s(r.get("Panel_ID"))
        if pid in voided or _s(r.get("Review_ID")) in reused:
            continue
        decision = _s(r.get("Decision")).upper()
        if not pid:
            flag(line, "MISSING_REQUIRED", "Panel_ID")
            continue
        # A duplicated Review_ID voided its rows, and a blank one did not - so
        # the identifier a decision is audited by could simply be left out, and
        # the accepted file carried `Review_ID=""` on every value. It also ends
        # up in a CSV column somebody will join on, so it takes the same SAFE_ID
        # rule as every other identifier in this package.
        rid_ = _s(r.get("Review_ID"))
        if not rid_:
            flag(line, "MISSING_REQUIRED",
                 "Review_ID - a decision with no identifier cannot be cited, "
                 "audited or withdrawn")
            continue
        if not BM.SAFE_ID.match(rid_):
            flag(line, "UNSAFE_ID",
                 "Review_ID=%r; identifiers must match %s"
                 % (rid_, BM.SAFE_ID.pattern))
            continue
        if pid not in expected:
            flag(line, "REVIEW_PANEL_NOT_IN_QUEUE",
                 "%s did not pass machine QC in this run, so there is nothing "
                 "for a decision to apply to" % pid)
            continue
        if decision and decision not in RB.REVIEW_DECISIONS:
            flag(line, "BAD_REVIEW_DECISION",
                 "%r is not one of %s" % (decision, ", ".join(RB.REVIEW_DECISIONS)))
            continue
        if decision != "APPROVED":
            continue

        rid = _s(r.get("Reviewer_ID"))
        if rid not in human:
            flag(line, "REVIEWER_NOT_HUMAN_OR_NOT_REGISTERED",
                 "Reviewer_ID=%r is not a Reviewer_Record_Type=HUMAN row in "
                 "reviewer_registry.csv" % rid)
            continue
        mode = review_mode.get(pid, "")
        if mode not in RB.REVIEW_MODES:
            flag(line, "REVIEW_MODE_UNKNOWN",
                 "the queue says Review_Mode=%r for %s; expected %s"
                 % (mode, pid, "/".join(sorted(RB.REVIEW_MODES))))
            continue
        absent = [t for t in RB.REVIEW_MODES[mode]
                  if t not in artifact_types.get(pid, set())]
        if absent:
            flag(line, "REVIEW_ARTIFACT_MISSING",
                 "%s was queued for %s review, and the run's artifact ledger "
                 "carries no %s for it. There is nothing this approval can be "
                 "an approval of" % (pid, mode, "/".join(absent)))
            continue
        # AND, WHERE THE RUN DECLARED IT, THAT THE SIGNATURE IS NOT THE
        # RESOLVER'S OWN. v7.96. `identity_resolution.csv` carries the
        # Reviewer_ID of the person who named a series the reader could not, and
        # `value_review.csv` carries the Reviewer_ID of the person approving the
        # panel that naming lands in. The two being the same person is one
        # reading of a legend confirming itself - `Identity_Checked=CONFIRMED`
        # meaning "yes, I am still of the same opinion". `PILOT.md` said two
        # people and nothing checked it, so a run could say the words and
        # finalize anyway.
        mine = (resolvers or {}).get(pid, set())
        # THE CONTRACT IS ABOUT A PAIR, so it applies where the pair exists.
        # v7.97 checked every approved panel, `mine` empty or not, which quietly
        # made `DISTINCT_RESOLVER_APPROVER` mean "and every approver under this
        # policy must hold an ORCID" - a wider rule than its name, arrived at by
        # accident. A panel nobody hand-resolved has no resolver for the approver
        # to be distinct FROM, so it is satisfied with nothing to check. If the
        # wider rule is ever wanted it gets its own name in `SEPARATION_POLICIES`.
        if separation_policy == DISTINCT_RESOLVERS and mine:
            keys = people or {}
            # COMPARED AS PEOPLE, NOT AS ROW IDENTIFIERS. v7.96 compared
            # Reviewer_IDs, and a Reviewer_ID identifies a ROW: register one
            # person twice under two IDs with the same ORCID and the check
            # reported two reviewers. The registry refuses a duplicated ID and
            # nothing refuses a duplicated PERSON, which is not only how somebody
            # games this - it is what a registry merge or an ID-convention change
            # produces by accident.
            unproven = [who for who in sorted(mine | {rid})
                        if not keys.get(who, "").startswith("ORCID:")]
            if unproven:
                flag(line, "REVIEWER_IDENTITY_UNPROVABLE",
                     "%s runs under %s, and %s %s registered without an ORCID. "
                     "Two Reviewer_IDs are two rows; an email address is a "
                     "mailbox. Nothing here can establish that these are two "
                     "people, so the panel is refused rather than assumed"
                     % (pid, DISTINCT_RESOLVERS, "/".join(unproven),
                        "is" if len(unproven) == 1 else "are"))
                continue
            clash = sorted(who for who in mine
                           if who != rid and keys.get(who) == keys.get(rid))
            if rid in mine or clash:
                flag(line, "RESOLVER_IS_APPROVER",
                     "%s runs under %s, and %s both resolved an identity on "
                     "this panel and signed it%s. A person confirming their own "
                     "reading of a legend is not a second reading of it"
                     % (pid, DISTINCT_RESOLVERS, rid,
                        "" if rid in mine
                        else " - registered twice, as %s and %s, against %s"
                        % (rid, "/".join(clash), keys.get(rid))))
                continue
        wanted = tuple(RB.REVIEW_CONFIRMATIONS.get(mode, ())) + tuple(
            (extra_confirmations or {}).get(pid, ()))
        unconfirmed = [c for c in wanted
                       if _s(r.get(c)).upper() != RB.REVIEW_CONFIRMED]
        if unconfirmed:
            flag(line, "REVIEW_CONFIRMATION_MISSING",
                 "%s was queued for %s review and the decision does not say "
                 "%s was checked. APPROVED alone is a signature on a filename"
                 % (pid, mode, "/".join(unconfirmed)))
            continue
        got = _s(r.get("Review_Subject_SHA256"))
        if got != expected[pid]:
            flag(line, "APPROVAL_STALE",
                 "the approval is for subject %s..., this run produced "
                 "%s.... The values, the manifests, the artifacts or the "
                 "environment changed since somebody looked"
                 % (got[:16] or "(blank)", expected[pid][:16]))
            continue
        when = _s(r.get("Reviewed_At"))
        try:
            stamped = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            flag(line, "BAD_REVIEWED_AT",
                 "Reviewed_At=%r is not an ISO timestamp" % when)
            continue
        if stamped.date() > today:
            flag(line, "BAD_REVIEWED_AT",
                 "Reviewed_At=%s is in the future" % when)
            continue
        out[pid] = r
    return out


def geometry_index_of(run_dir, verified, artifacts=None):
    """The BAR_MONO geometry index, from the bytes that were hashed.

    `RB.geometry_index_from_run` opens `mono_bar_geometry.csv` in the run
    directory - the same file the ledger names as `MONO_BAR_GEOMETRY` and
    `verify_run_outputs` has already hashed. It was the eighth structured read
    and the one that decides `IDENTITY_GEOMETRY_ROW_UNKNOWN`, so a geometry file
    swapped after verification made every human-resolved value cite a row that
    no longer existed.
    """
    artifacts = artifacts if artifacts is not None else \
        (verified or {}).get("artifact_bytes")
    ledger = (verified or {}).get("frames", {}).get("panel_artifacts.csv")
    if artifacts is None or ledger is None:
        return RB.geometry_index_from_run(run_dir)
    for _, art in ledger.iterrows():
        if _s(art.get("Artifact_Type")) != "MONO_BAR_GEOMETRY":
            continue
        _path, blob = artifact_data(run_dir, art, artifacts)
        if blob is None:
            continue
        return RB.geometry_index(
            list(csv.DictReader(io.StringIO(blob.decode("utf-8")))))
    return {}


def artifact_key(art):
    """The LEDGER's identity for an artifact, independent of the filesystem.

    v8.3. The snapshot was keyed on `os.path.realpath(path)` and looked up the
    same way, so the key was recomputed against the filesystem AFTER
    verification: re-point a symlink in between and the lookup misses (evidence
    that is present reads as absent) or, worse, hits another artifact's entry.
    The bytes were immutable and the address for them was not.

    So the key is what the ledger recorded - type, panel, reference, the
    run-relative path as written, and the SHA-256 the run put beside it. None of
    it is read off disk, so nothing between the hash and the read can change
    which entry a row resolves to. Containment and the symlink target are checked
    once, in the verification loop, on the path that was actually read.
    """
    return "|".join([
        _s(art.get("Artifact_Type")), _s(art.get("Panel_ID")),
        _s(art.get("Artifact_Reference")),
        _s(art.get("Artifact_Path")).replace("\\", "/").strip("/"),
        _s(art.get("SHA256")).lower(),
    ])


def artifact_data(run_dir, art, artifacts=None):
    """The bytes `verify_run_outputs` hashed for this artifact, or a fresh read.

    `artifacts` is `RunSnapshot.artifacts` - the structured artifacts kept from
    the read that hashed them. When it is given, an artifact absent from it was
    either not structured or did not match its recorded hash, and the answer is
    "no bytes" rather than "open the path and see": a file whose digest failed is
    already a refusal, and reading it anyway is the second read this layer
    exists to remove.

    When it is None the path is read, which is what a direct caller with no
    verified run behind it needs - `collect_inference_manifests(run_dir)` from a
    template command, and the scenarios. `validate_finalization` always passes
    the snapshot, so the finalization contract never takes that branch.

    `art` is the LEDGER ROW, not a path: with a snapshot the answer comes from
    what the run recorded and the filesystem is not consulted at all.

    Returns `(path, data)`; `data` is None when there is nothing to interpret,
    and `path` is the recorded path when the snapshot answered - enough for a
    message, and never used to open anything.
    """
    recorded = _s(art.get("Artifact_Path"))
    if artifacts is not None:
        return (recorded or None), artifacts.get(artifact_key(art))
    path = RB.resolve_artifact(run_dir, recorded)
    if path is None or not os.path.exists(path):
        return path, None
    try:
        with open(path, "rb") as fh:
            return path, fh.read()
    except Exception:
        return path, None


def read_verified_bytes(path):
    """The bytes and their digest, from one read. Everything else builds on it.

    Splitting this out is what makes the rule apply to a format other than CSV:
    `run_stamp.json` was hashed with `file_sha256(path)` and then opened again
    with `json.load`, so `Run_Mode`, `Status`, `Output_SHA256` and `Manifest_Dir`
    were all interpreted from a file that need not be the one the stamp names. A
    DEMO_ONLY run hashed and an ATTESTED run parsed is the whole finalization
    contract decided on bytes nobody recorded.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except Exception as exc:
        return b"", "", "%s: %s" % (type(exc).__name__, exc)
    return data, hashlib.sha256(data).hexdigest(), ""


def read_verified_json(path):
    """One read: hash THOSE bytes, parse THOSE bytes, as JSON."""
    data, digest, error = read_verified_bytes(path)
    if error:
        return None, digest, error
    try:
        value = json.loads(data.decode("utf-8"))
    except Exception as exc:
        return None, digest, "%s: %s" % (type(exc).__name__, exc)
    return value, digest, ""


def read_verified_csv(path):
    """One read: hash THOSE bytes, parse THOSE bytes. Never the path twice.

    Everything downstream of a hash check has to be derived from the bytes that
    were hashed, or the check names a file and the decision uses another. The
    package closed this on decision files (v7.79), on the manifest frames
    (v7.80) and on the reviewer registry (v7.99) one at a time; this is the same
    fix as a function, so the run outputs stop being the last place with the
    hole in it.

    Returns `(frame, sha256, error)`. `frame` is None when the bytes will not
    parse, and `sha256` is still the digest of what was on disk - a refusal that
    records the hash of the thing that caused it is worth more than one that
    records nothing.
    """
    data, digest, error = read_verified_bytes(path)
    if error:
        return None, digest, error
    try:
        return (pd.read_csv(io.BytesIO(data), dtype=object).fillna(""),
                digest, "")
    except Exception as exc:
        return None, digest, "%s: %s" % (type(exc).__name__, exc)


def verify_run_outputs(run_dir, run_stamp, manifest_dir, flag, verified=None):
    """The run must be the run that was reviewed, byte for byte.

    The finalizer re-reads four files to decide whether a value is poolable, and
    trusted every one of them. So: run, look at a correct overlay, approve it,
    then edit a Mean in `figure_values_machine_qc.csv` and finalize - the edited
    number came out HUMAN_APPROVED. The reviewer registry had the same hole from
    the other side, since `--manifests` takes any directory.
    """
    # The type, not only the presence. `run_stamp.json` can be a well-formed
    # JSON object with a malformed field inside it - `Output_SHA256: ["x"]` is
    # valid JSON - and `recorded.get(name)` on a list raises AttributeError.
    # That exception left the finalizer with the accepted file and the previous
    # stamp already deleted and no new stamp explaining why, which is the shape
    # the top-level stamp guard exists to prevent. A guard on the outside of a
    # structure is not a guard on what is inside it.
    recorded = run_stamp.get("Output_SHA256")
    if not isinstance(recorded, dict):
        flag("run", "RUN_STAMP_SCHEMA_INVALID",
             "Output_SHA256 is %s; it must be an object mapping each verified "
             "output to its SHA-256" % type(recorded).__name__)
        return False
    if not recorded:
        flag("run", "RUN_ARTIFACT_MODIFIED",
             "run_stamp.json records no Output_SHA256 - this run predates "
             "output verification and cannot be finalized")
        return False
    off_type = sorted(k for k, v in recorded.items() if not isinstance(v, str))
    if off_type:
        flag("run", "RUN_STAMP_SCHEMA_INVALID",
             "Output_SHA256 holds a non-string hash for %s" % ", ".join(off_type))
        return False
    ok = True
    # KEPT LOCALLY WHETHER OR NOT A CALLER WANTS THEM. `verified` is the caller's
    # collecting dict and is optional; the frames are not optional to THIS
    # function, which checks the artifact ledger against itself. Reading them
    # only when somebody asked was how the ledger ended up being opened twice.
    parsed = {}
    for name in VERIFIED_OUTPUTS:
        path = os.path.join(run_dir, name)
        if not os.path.exists(path):
            flag("run", "RUN_ARTIFACT_MODIFIED", "%s is gone" % name)
            ok = False
            continue
        # ONE READ. `RB.file_sha256(path)` then `open(path)` was two, and the
        # window between them is the whole point of hashing: the ledger could be
        # hashed as A and parsed as B, and the artifact checks would run against
        # rows the run stamp never approved. Same for the queue, which carries
        # `Review_Mode` and `Review_Subject_SHA256`.
        frame, actual, error = read_verified_csv(path)
        if actual == recorded.get(name) and frame is not None:
            parsed[name] = frame
            if verified is not None:
                verified.setdefault("frames", {})[name] = frame
                # The list-of-dicts view the older consumers take, derived from
                # the SAME frame rather than from another read of the file.
                verified.setdefault("outputs", {})[name] = frame.to_dict(
                    "records")
        if actual == recorded.get(name) and frame is None:
            # HASHING SAYS THE BYTES DID NOT CHANGE. It does not say they are a
            # run output. A malformed CSV whose digest matches used to pass this
            # loop and only be noticed if something downstream happened to want
            # the frame - and `figure_values_raw.csv` is wanted by nothing here.
            flag("run", "RUN_OUTPUT_UNREADABLE",
                 "%s matches its recorded hash and will not parse (%s)"
                 % (name, error or "no reason given"))
            ok = False
            continue
        if actual != recorded.get(name):
            flag("run", "RUN_ARTIFACT_MODIFIED",
                 "%s hashes to %s..., the run recorded %s.... It was edited "
                 "after the run that produced it"
                 % (name, actual[:16], _s(recorded.get(name))[:16] or "(nothing)"))
            ok = False
    # ---- the artifacts the person actually looked at ----------------------
    # Four CSVs were verified and nothing else, so the numbers could not be
    # edited but the picture could. Replace `review/P1_overlay.png` with a
    # different panel's overlay, or with a blank rectangle, and the approval
    # bound to it still finalized: the reviewer's decision says "I looked at
    # this and it is right", and nothing established what "this" was.
    ledger = os.path.join(run_dir, "panel_artifacts.csv")
    if not os.path.exists(ledger):
        flag("run", "RUN_ARTIFACT_MODIFIED",
             "panel_artifacts.csv is missing - this run predates artifact "
             "verification and cannot be finalized")
        return False
    # THE FRAME THE LOOP ABOVE PARSED FROM THE BYTES IT HASHED. Re-reading the
    # path here made the ledger that declares a panel's artifacts and the ledger
    # the artifact hashes are checked against two different reads: strike a row
    # from the second and its file stops being checked at all, while the decider
    # still believes the artifact is there.
    artifact_bytes = {}
    ledger_df = parsed.get("panel_artifacts.csv")
    if ledger_df is None:
        # It hashed correctly and still will not parse. Refusing is the only
        # honest answer, and it has to be a flagged refusal rather than a
        # traceback, or the run ends with no stamp explaining itself.
        flag("run", "RUN_ARTIFACT_MODIFIED",
             "panel_artifacts.csv could not be parsed")
        return False
    for _, art in ledger_df.iterrows():
        recorded_path = _s(art.get("Artifact_Path"))
        recorded_hash = _s(art.get("SHA256"))
        label = "%s %s" % (_s(art.get("Artifact_Type")),
                           os.path.basename(recorded_path))
        # Ledger paths are relative to the run directory, so the check survives
        # the directory being moved and the finalizer being launched from
        # anywhere. A path that resolves outside the run is not an artifact of
        # this run and is refused rather than read.
        path = RB.resolve_artifact(run_dir, recorded_path)
        if path is None:
            flag("panel:%s" % _s(art.get("Panel_ID")), "ARTIFACT_PATH_OUTSIDE_RUN",
                 "the ledger names %s at %r, which is outside the run directory"
                 % (label, recorded_path))
            ok = False
            continue
        if not os.path.exists(path):
            flag("panel:%s" % _s(art.get("Panel_ID")), "RUN_ARTIFACT_MODIFIED",
                 "%s is gone; the run recorded it at %s" % (label, recorded_path))
            ok = False
            continue
        # ONE READ FOR THE STRUCTURED ONES, and the bytes are kept. The others
        # are hashed and nothing more, because nothing here interprets them.
        if _s(art.get("Artifact_Type")) in STRUCTURED_ARTIFACTS:
            data, actual, _err = read_verified_bytes(path)
            if actual == recorded_hash:
                artifact_bytes[artifact_key(art)] = data
        else:
            actual = RB.file_sha256(path)
        if actual != recorded_hash:
            flag("panel:%s" % _s(art.get("Panel_ID")), "RUN_ARTIFACT_MODIFIED",
                 "%s hashes to %s..., the run recorded %s.... The reviewer "
                 "approved what the run produced, not this"
                 % (label, actual[:16], recorded_hash[:16] or "(nothing)"))
            ok = False

    # EVERY manifest, not only the registry. The run stamp has carried
    # `Manifest_SHA256` for every input frame since the beginning and this
    # module never read it, so a panel box, a series' declared fill or a
    # position's Factor_Level could be edited after the run and the approval
    # still stood - and now that the finalizer RE-DERIVES the value contract
    # from these files, an edited mapping would be the thing it checks against.
    # Exchange two Factor_Levels in `position_manifest.csv` after the run and
    # the cell check would either refuse a correct run or bless a wrong one.
    frames = verify_manifest_inputs(manifest_dir, run_stamp, flag)
    if frames is None:
        ok = False
    elif verified is not None:
        # Handed to the caller rather than re-read. The gap between "these
        # bytes hash correctly" and "open them again and re-derive the value
        # contract from them" is a gap: it is the same file twice, and the
        # sentence this module makes is that the contract runs on the frames
        # that were verified.
        verified.update(frames)
    manifest_frames = frames or {}
    # AND THE CONTRACT THOSE FRAMES HAVE TO SATISFY TODAY, not the one that was
    # in force when the run was made. Hashing answers "are these the manifests
    # the run validated"; it says nothing about whether what they declare is
    # coherent, because the run's own validator is the thing that answered that -
    # in whatever version it happened to be.
    #
    # The gap is a completed run from an older producer. A v9.0-era set could
    # exchange the `Unit_ID` of two panels of one figure (v9.1 closed that in the
    # plan layer, v9.3 in the manifests): its numbers are right, its hashes are
    # right, and one panel's values sit under the other panel's outcome. The
    # finalizer used to confirm the hashes and approve it, so every contract this
    # package has added since a run was produced was a contract that run escaped.
    # Re-running the CURRENT validator over the VERIFIED frames closes that: a
    # run may only be finalized under the semantics of the package doing the
    # finalizing.
    #
    # `check_files=False`, because this is a check on what the manifests SAY. The
    # rasters were hashed at run time and are hashed again as review subjects;
    # re-reading them here would make finalization depend on a corpus directory
    # that a reviewer approving values does not need to have.
    if frames is not None:
        contract = BM.validate_batch_manifests(
            frames.get("panels"), frames.get("series"), frames.get("positions"),
            frames.get("configs"), units=frames.get("units"),
            source_documents=frames.get("source_documents"),
            source_figures=frames.get("source_figures"),
            source_panels=frames.get("source_panels"),
            reviewers=frames.get("reviewers"),
            resolutions=frames.get("resolutions"),
            check_files=False)
        if len(contract):
            # Reported to the caller so the REFUSAL can say what happened. The
            # generic verification status is `RUN_ARTIFACT_MODIFIED`, whose
            # sentence is "the run this approval refers to is not the run on
            # disk" - and here nothing was modified: the manifests are exactly
            # the ones the run validated, and they do not satisfy the contract
            # this package holds today. A true refusal under a false heading is
            # the kind of thing somebody debugs for an afternoon.
            if verified is not None:
                verified["contract_problems"] = sorted(set(contract["check"]))
            for code in sorted(set(contract["check"])):
                rows = contract[contract["check"] == code]
                flag("run", "RUN_MANIFEST_CONTRACT_INVALID",
                     "%s (%d row(s), e.g. %s: %s). The manifests are the ones "
                     "the run validated and they do not satisfy the contract "
                     "this package holds now - the run was produced under an "
                     "earlier one. Re-run it before approving its values"
                     % (code, len(rows), _s(rows.iloc[0].get("where")),
                        _s(rows.iloc[0].get("detail"))[:160]))
            ok = False
    if verified is not None:
        verified["artifact_bytes"] = artifact_bytes

    registry_path = os.path.join(manifest_dir, "reviewer_registry.csv")
    if os.path.exists(registry_path):
        # FROM THE VERIFIED FRAMES, not another read of the same path.
        # `verify_manifest_inputs` has already read and hashed this file; opening
        # it again let one producer output satisfy the manifest check with one
        # registry and this check with another.
        registry_df = manifest_frames.get("reviewers")
        if registry_df is None:
            flag("run", "REVIEWER_REGISTRY_CHANGED",
                 "the registry at %s is not among the verified manifests"
                 % manifest_dir)
            return False
        actual = RB.frame_sha256(registry_df)
        if actual != _s(run_stamp.get("Reviewer_Registry_SHA256")):
            flag("run", "REVIEWER_REGISTRY_CHANGED",
                 "the registry at %s is not the one the run validated. An "
                 "approver cannot be added between the run and the approval"
                 % manifest_dir)
            ok = False
    return ok


def _promote(staging, run_dir, fault_after=None):
    """Move the finalization into place, the accepted file last.

    The same shape as `run_batch.promote`, for the same reason: the accepted
    file is the commit marker, so a process killed partway leaves a stamp
    explaining an incomplete finalization rather than poolable values with no
    stamp behind them.
    """
    names = sorted(os.listdir(staging))
    ordered = ([n for n in names if n != FINALIZE_MARKER]
               + [n for n in names if n == FINALIZE_MARKER])
    for i, name in enumerate(ordered):
        if fault_after is not None and i == fault_after:
            raise RuntimeError("fault injected after promoting %d of %d files"
                               % (i, len(ordered)))
        shutil.move(os.path.join(staging, name), os.path.join(run_dir, name))
    shutil.rmtree(staging, ignore_errors=True)


#: What a finalization DECIDED, before anything is written. `keep` is the frame
#: that would be accepted and is None on every refusal.
#: The bytes this finalization decided from, parsed once and carried out with
#: the answer. Every field is None until the read that fills it has happened, so
#: a refusal that never got past the run stamp carries an empty snapshot and says
#: so rather than inviting a caller to open the path itself.
#:
#: THIS IS THE SHAPE OF THE FIX, generalised. `read_decisions` closed
#: hash-then-reopen on the decision files (v7.79), `verify_manifest_inputs` on
#: the manifests (v7.80), and v7.99 on the reviewer registry - each time by
#: keeping what was read instead of re-opening the path. Anything downstream that
#: still opens a path is deciding from bytes nobody hashed, and the caller that
#: needs those rows is usually the preflight, one process boundary away from the
#: decision it is supposed to agree with.
RunSnapshot = collections.namedtuple(
    "RunSnapshot",
    "run_stamp reviewers machine queue ledger reviews inference_reviews "
    "artifacts")
EMPTY_SNAPSHOT = RunSnapshot(None, None, None, None, None, None, None, None)

Verdict = collections.namedtuple(
    "Verdict",
    "status detail problems approved keep blocked unstated inference_rejected "
    "run_stamp_sha review_sha inference_sha snapshot")
#: `reviewers` is the registry frame THIS verdict was decided against, verified
#: with every other manifest before it was parsed, and None on a refusal that
#: never got that far. It travels with the verdict because the preflight's
#: `--second` identity checks need the same rows: re-reading the registry from a
#: path afterwards is the hash-then-reopen shape this package closes everywhere
#: else, and a re-read that FAILS made those checks skip themselves in silence.


def review_paths(run_dir, review_path=None, inference_review_path=None):
    """Where the two decision files are, resolved once for both callers.

    Beside the panel decisions rather than in the run directory. The two files
    are filled in together, `--review` is where a caller says where that is, and
    a default anchored to the run would send a caller who moved one file looking
    for the other in a different place.
    """
    review_path = review_path or os.path.join(run_dir, "value_review.csv")
    inference_review_path = inference_review_path or os.path.join(
        os.path.dirname(os.path.abspath(review_path)), "inference_review.csv")
    return review_path, inference_review_path


def validate_finalization(run_dir, review_path=None, manifest_dir=None,
                          today=None, inference_review_path=None,
                          separation_policy=None):
    """Everything a finalization decides, deciding nothing on disk.

    ONE FUNCTION, TWO CALLERS. `finalize` wraps this and writes; `review_preflight`
    calls it and prints. Until v7.77 the preflight answered overlapping questions
    through its own code, so it could report a clean bundle that the finalizer then
    refused - and a preflight that disagrees with the thing it is a preflight for
    is worse than none, because the reviewer trusts it and signs.

    It reads files and returns a `Verdict`. Nothing here creates, deletes or
    promotes anything: the scenario that proves it walks the run directory before
    and after, the same way the preflight's own no-write claim is checked.
    """
    problems = []
    # A one-slot box rather than a bare name: `stop` is a closure and reads it
    # at call time, and none of these is known until the read that fills it.
    snapshot = [EMPTY_SNAPSHOT]

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    review_path, inference_review_path = review_paths(
        run_dir, review_path, inference_review_path)
    # Hashed when they are READ, and carried out with the verdict. Blank until
    # the read happens, which is after the run's own outputs are verified: a
    # refusal that never opened the decisions records no hash for them, which is
    # the truth.
    review_sha = inference_sha = ""

    def stop(status, detail, approved=None, blocked=0, unstated=0):
        # The approved PANELS travel with the refusal, not a count of them: the
        # stamp reports how many were approved even when none of their values
        # could be finalized, and a refusal that reported zero approvals said the
        # reviewer had not signed when they had.
        return Verdict(status, detail, problems, approved or {}, None, blocked,
                       unstated, 0, run_stamp_sha, review_sha, inference_sha,
                       snapshot[0])

    run_stamp_path = os.path.join(run_dir, "run_stamp.json")
    run_stamp_sha = ""
    # THE POLICY IS CANONICALISED FIRST, and an unrecognised one stops the
    # finalization before anything else is read. Everything downstream - the
    # approval check, the verdict, the stamp - is given `policy`, never the raw
    # argument, so a stamp cannot name a contract that was not the one applied.
    policy = canonical_policy(separation_policy)
    if policy is None:
        flag("review-policy", "BAD_REVIEWER_SEPARATION_POLICY",
             "%r is not one of %s. A policy the enforcement does not recognise "
             "would be recorded in the stamp and applied to nothing"
             % (_s(separation_policy), "/".join(SEPARATION_POLICIES)))
        return stop("RUN_NOT_FINALIZABLE",
                    "the reviewer-separation policy is not one this package "
                    "enforces")
    if not os.path.exists(run_stamp_path):
        run_stamp = {}
        return stop("RUN_NOT_FINALIZABLE", "no run_stamp.json in %s" % run_dir)
    # Guarded, like every other file this module reads. It was not, and the
    # accepted file and the previous stamp are deleted before this point - so
    # a truncated or non-UTF-8 `run_stamp.json` raised out of the finalizer
    # leaving the run with no result AND no stamp explaining the absence, which
    # is the one outcome this module is supposed to make impossible.
    # ONE READ, and the digest is of the bytes that were parsed. `file_sha256`
    # then `json.load` was two: `Status`, `Run_Mode`, `Output_SHA256` and
    # `Manifest_Dir` all came out of the second, while `Run_Stamp_SHA256` named
    # the first. A DEMO_ONLY stamp hashed and an ATTESTED stamp parsed decides
    # the whole finalization contract on bytes nobody recorded.
    run_stamp, run_stamp_sha, stamp_error = read_verified_json(run_stamp_path)
    if stamp_error or not isinstance(run_stamp, dict):
        detail = stamp_error or ("run_stamp.json holds a %s, not an object"
                                 % type(run_stamp).__name__)
        run_stamp = {}
        return stop("RUN_NOT_FINALIZABLE",
                    "run_stamp.json could not be interpreted (%s)" % detail)
    snapshot[0] = snapshot[0]._replace(run_stamp=run_stamp)
    # Where the manifests are, in the order that survives a moved run. The
    # stamp records an absolute path, so a run folder handed to somebody else
    # named a directory on the machine it was produced on; a `manifests/`
    # directory sitting inside the run is the one answer that travels with it.
    manifest_dir = manifest_directory(run_dir, manifest_dir, run_stamp)
    if run_stamp.get("Status") != "RAN":
        return stop("RUN_NOT_FINALIZABLE",
                    "the run says Status=%s; only a completed run can be "
                    "finalized" % run_stamp.get("Status"))
    if run_stamp.get("Run_Mode") != "ATTESTED":
        return stop("RUN_NOT_FINALIZABLE",
                    "the run says Run_Mode=%s. No number of approvals promotes a "
                    "demonstration" % run_stamp.get("Run_Mode"))

    # ---- verify BEFORE parsing --------------------------------------------
    # Hashing is bytes; parsing is interpretation. Doing them the other way
    # round meant a `figure_values_machine_qc.csv` with a broken quote raised
    # out of `pd.read_csv` before verification ran - and by then the previous
    # accepted file and stamp had already been deleted, so the run was left
    # with neither a result nor a stamp saying why. Every failure this module
    # can reach has to end in a stamp.
    machine_path = os.path.join(run_dir, "figure_values_machine_qc.csv")
    queue_path = os.path.join(run_dir, "review_queue.csv")
    for path in (machine_path, queue_path):
        if not os.path.exists(path):
            return stop("RUN_NOT_FINALIZABLE", "%s is missing" % path)

    verified = {}
    if not verify_run_outputs(run_dir, run_stamp, manifest_dir, flag,
                              verified=verified):
        if verified.get("contract_problems"):
            # Nothing was modified. The manifests hash exactly as the run
            # recorded them and they do not satisfy the contract this package
            # holds now - which is what happens to a run produced under an
            # earlier one, and is a different sentence from "not the run on
            # disk".
            return stop("RUN_MANIFEST_CONTRACT_INVALID",
                        "the manifests are the ones this run validated and they "
                        "do not satisfy the current manifest contract (%s). The "
                        "run was produced under an earlier one; re-run it before "
                        "approving its values"
                        % ", ".join(verified["contract_problems"]))
        return stop("RUN_ARTIFACT_MODIFIED",
                    "the run this approval refers to is not the run on disk")

    # THE FRAMES `verify_run_outputs` PARSED FROM THE BYTES IT HASHED, not the
    # paths opened again. Re-reading here is the hash-then-reopen window closed
    # everywhere else in this module: between the two reads an autosave or a
    # swap puts the decision on rows the hash never covered.
    frames = verified.get("frames", {})
    machine = frames.get("figure_values_machine_qc.csv")
    queue = frames.get("review_queue.csv")
    if machine is None or queue is None:
        # The bytes hashed correctly and still will not parse: that is a run
        # this module cannot read, not an approval it can refuse on the merits.
        return stop("RUN_NOT_FINALIZABLE",
                    "a verified run output could not be parsed")

    # The frame `verify_manifest_inputs` hashed, not the path read again. The
    # registry decides who may approve, so re-opening it after verifying it is
    # the same window the manifests were just closed against.
    reviewers = verified.get("reviewers")
    snapshot[0] = snapshot[0]._replace(reviewers=reviewers, machine=machine,
                                       queue=queue)
    if reviewers is None:
        return stop("RUN_NOT_FINALIZABLE",
                    "the verified manifests carry no reviewer_registry.csv, so "
                    "no approver can be checked")
    # And validated once, here, for every panel - not only for the panels that
    # carry a human resolution. A legacy run's approver could otherwise pass on
    # `Reviewer_Record_Type=HUMAN` alone while the registry row itself is
    # malformed.
    registry_problems = []
    BM.check_reviewer_registry(
        reviewers,
        lambda where, code, detail: registry_problems.append((code, detail)))
    for code, detail in registry_problems:
        flag("run", "REVIEWER_REGISTRY_INVALID", "%s: %s" % (code, detail))
    if registry_problems:
        return stop("RUN_NOT_FINALIZABLE",
                    "the reviewer registry this run was validated against does "
                    "not pass the registry contract")

    reviews, review_sha = read_decisions(
        review_path, VALUE_REVIEW_COLUMNS, flag, "review",
        "REVIEW_FILE_UNREADABLE", "REVIEW_SCHEMA_INCOMPLETE",
        absent="REVIEW_FILE_MISSING")
    snapshot[0] = snapshot[0]._replace(reviews=reviews)
    # Which artifacts the run says each panel has. Read after the verification
    # above, so every entry here is one whose bytes have just been confirmed.
    artifact_types = {}
    ledger_rows = frames.get("panel_artifacts.csv")
    if ledger_rows is None:
        return stop("RUN_NOT_FINALIZABLE",
                    "the artifact ledger could not be parsed")
    snapshot[0] = snapshot[0]._replace(ledger=ledger_rows)
    for _, art in ledger_rows.iterrows():
        artifact_types.setdefault(_s(art.get("Panel_ID")), set()).add(
            _s(art.get("Artifact_Type")))
    # Re-derived here, not taken from the producer's promise. The review mode's
    # artifact tuple cannot express "and the evidence for every file-backed
    # resolution", because a panel resolved only by REVIEWER_INSPECTION has no
    # evidence file at all - so the requirement is conditional on what the
    # resolution rows say, and reading them is the only way to know. Without
    # this the finalizer accepted any run whose producer had not copied the
    # evidence in, including every run made before it started doing so.
    artifacts = verified.get("artifact_bytes")
    snapshot[0] = snapshot[0]._replace(artifacts=artifacts)
    for pid in sorted(identity_contract_failures(run_dir, ledger_rows, machine,
                                                flag, frames=verified,
                                                artifacts=artifacts)):
        artifact_types.pop(pid, None)
    # And the runner's own value contract, re-run here on the verified files.
    # A run this module did not produce is the case it exists for, and nothing
    # pins a minimum pipeline version: a run made before a check existed arrives
    # looking complete.
    # AND THE DATA HALF OF THE CURRENT CONTRACT (v9.5). The manifests were
    # re-validated during verification; the grid gate is where the factor sets,
    # the declared levels and the cell product live, and it was still the version
    # the run was made with.
    for pid in sorted(grid_contract_failures(verified, machine, flag)):
        if pid == "*":
            return stop("RUN_NOT_FINALIZABLE",
                        "this run's values could not be re-checked against the "
                        "current grid contract")
        artifact_types.pop(pid, None)
    for pid in sorted(value_contract_failures(run_dir, verified, machine,
                                              flag)):
        if pid == "*":
            return stop("RUN_NOT_FINALIZABLE",
                        "this run's values could not be re-checked against the "
                        "manifests it was produced from")
        artifact_types.pop(pid, None)
    # What each panel's own values ask on top of its mode. Re-derived here from
    # `Identity_Method` and `Value_Method`, exactly as the run derived the count
    # it printed in the queue - so a run that printed zero cannot buy a panel an
    # approval that skips the question.
    contract_refused = set()
    values_by_panel = {}
    for value in machine.to_dict("records"):
        values_by_panel.setdefault(_s(value.get("Run_Panel_ID")), []).append(value)
    extra_confirmations = {pid: RB.inference_confirmations(rows)
                           for pid, rows in values_by_panel.items()}
    # A METHOD IS A CLAIM ABOUT EVIDENCE, AND EVIDENCE IS WHAT THIS MODULE
    # CHECKS. Withheld before the approvals are read, like the other contracts:
    # a panel whose values claim a route their reader could not have taken is
    # not a panel an approval can rescue.
    for pid in sorted(method_contract_failures(machine, queue, ledger_rows,
                                               run_dir, flag, frames=verified,
                                               artifacts=artifacts)):
        artifact_types.pop(pid, None)
        contract_refused.add(pid)
    approved = approved_panels(reviews, queue, reviewers, flag, today=today,
                               artifact_types=artifact_types,
                               extra_confirmations=extra_confirmations,
                               resolvers=resolution_reviewers(
                                   run_dir, ledger_rows, artifacts),
                               separation_policy=policy,
                               people=person_keys(reviewers))
    for pid in sorted(contract_refused):
        approved.pop(pid, None)

    if not approved:
        return stop("NOTHING_APPROVED",
                    "no panel carries an APPROVED decision from a registered "
                    "human against this run's fingerprints")

    # AND THE CELLS THAT WERE ASKED ABOUT ONE AT A TIME. Run over the approved
    # panels only: a panel nobody approved is already refused, and reporting its
    # unanswered per-cell questions would bury the reason it was refused.
    inference_reviews, inference_sha = read_decisions(
        inference_review_path, INFERENCE_REVIEW_COLUMNS, flag, "inference",
        "INFERENCE_FILE_UNREADABLE", "INFERENCE_SCHEMA_INCOMPLETE")
    snapshot[0] = snapshot[0]._replace(inference_reviews=inference_reviews)
    inference_held, inference_rejected = inference_contract_failures(
        run_dir, ledger_rows, machine,
        inference_reviews, reviewers, flag,
        today=today, panels=set(approved), artifacts=artifacts)
    for pid in sorted(inference_held):
        approved.pop(pid, None)
    if not approved:
        return stop("NOTHING_APPROVED",
                    "every approved panel holds a reconstructed value whose "
                    "per-cell confirmation is missing, duplicated or answers a "
                    "question this run did not ask")

    keep = machine[machine["Run_Panel_ID"].isin(approved)].copy() if len(machine) \
        else machine.copy()
    if not len(keep):
        return stop("NOTHING_APPROVED",
                    "the approved panels produced no machine-QC-passed values",
                    approved=approved)

    # AN APPROVAL CANNOT BUY A NUMBER A MODEL MADE.
    #
    # `Identity_Method` and `Value_Method` say how the series was named and how
    # the number was got, and `provenance.review_tier` prices the pair. R4 is the
    # tier for a value that was not read off the ink at all - the fitted curve
    # produced it, or the nearest observation was carried sideways with nothing
    # bracketing it - and a reviewer looking at an overlay CANNOT TELL A FITTED y
    # FROM A READ ONE. That is exactly what the picture cannot show, so an
    # APPROVED decision over such a value is a signature on something nobody
    # could have checked.
    #
    # ## A blank pair is refused too, and for four releases it was not
    #
    # `review_tier("", "")` is R4, and that is right where it is: an unregistered
    # method must not look safer than a registered bad one. v7.61 nevertheless
    # blocked only a pair that was STATED, because applying it to blank would
    # have refused every value in the package - five of the six readers answered
    # neither question then, `pilot_beckers` would have stopped reaching
    # POOLING_ELIGIBLE and every scenario in `test_finalize` would have gone
    # dark. That was a shutdown rather than a safety improvement, and the
    # exception was written down as temporary in as many words: "when the other
    # readers can answer, the blank case becomes a block and the count goes to
    # zero on its own".
    #
    # v7.64 and v7.65 taught all six. Publication 397 states 123 of 123, the
    # count went to zero, and v7.66 removed the exception. What it protected at
    # the end was not this package's output but somebody else's: an older
    # producer, a hand-built values file, a reader with a typo in one of the two
    # column names. This module exists to be producer-independent, and a
    # provenance gate that waives itself whenever the provenance is missing is
    # the one shape that cannot be.
    #
    # HALF-BLANK IS BLANK. `review_tier` prices the PAIR, not the better half: a
    # row naming how the number was got and not how the series was named is a
    # number with no series behind it.
    blocked_count = unstated = 0
    if len(keep):
        stated, tiers = [], []
        for _, row in keep.iterrows():
            identity = _s(row.get("Identity_Method"))
            value = _s(row.get("Value_Method"))
            stated.append(bool(identity and value))
            # THE ROW, not the pair: `row_tier` prices the dispersion as well,
            # and a cell whose mean came off the ink and whose error bar was read
            # from a cap no stem connects to it is not an R0 cell. A caller that
            # reaches for `review_tier` here is asking about the mean and
            # answering for the value.
            tiers.append(PROV.row_tier(row))
        # THE BLANK EXCEPTION IS GONE - v7.66. Until now a row was blocked only
        # if it was STATED and priced at an unfinalizable tier; a blank or
        # half-blank pair was counted, flagged and accepted. That branch was
        # written in v7.61 for a package where five of the six readers answered
        # neither question, and wiring blank straight into this gate then refused
        # every value there was. v7.64 and v7.65 taught all six - publication 397
        # states 123 of 123 - so the exception now protects nothing this package
        # produces, and what it does protect is a run made by SOMETHING ELSE:
        # an older producer, a hand-built values file, a reader with a typo in one
        # of the two column names. `review_tier("", "")` has always been R4, and
        # the whole point of pricing an unregistered method at the top is that a
        # gate then acts on it.
        #
        # HALF-BLANK IS BLANK. A row naming a value method and no identity method
        # is a number with no series behind it, and `review_tier` already prices
        # the pair rather than the better half.
        blocked = [tier not in PROV.FINALIZABLE_TIERS for tier in tiers]
        unstated = sum(1 for is_stated in stated if not is_stated)
        blocked_count = sum(1 for b in blocked if b)
        if unstated:
            flag("run", "VALUE_METHOD_UNSTATED",
                 "%d of %d approved values do not say how they were got, and "
                 "are refused. A value whose provenance is absent is not a value "
                 "whose provenance is good - every reader in this package answers "
                 "both questions, so a row that does not was produced by "
                 "something else" % (unstated, len(keep)))
        if any(blocked):
            for (_, row), is_blocked, tier, is_stated in zip(
                    keep.iterrows(), blocked, tiers, stated):
                if not is_blocked:
                    continue
                flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                     ("VALUE_METHOD_NOT_FINALIZABLE" if is_stated
                      else "VALUE_METHOD_UNSTATED"),
                     "Identity_Method=%s Value_Method=%s is %s: %s"
                     % (_s(row.get("Identity_Method")) or "(blank)",
                        _s(row.get("Value_Method")) or "(blank)", tier,
                        "the number was not read off the ink, and an overlay "
                        "cannot show a reviewer the difference" if is_stated
                        else "nothing says how this number was got, so nothing "
                             "can say it is safe to pool"))
            keep = keep[[not b for b in blocked]].copy()
        if not len(keep):
            return stop("NOTHING_FINALIZABLE",
                        "every approved value was read at a tier no signature "
                        "can finalize", approved=approved,
                        blocked=blocked_count, unstated=unstated)

    # And the reconstructions a person looked at and refused. Dropped here rather
    # than in the contract above, so that a REJECTED cell costs one value while a
    # MISSING answer costs the panel - the difference between an answer and a
    # silence.
    rejected_count = 0
    if inference_rejected and len(keep):
        dropped = [(_s(row.get("Run_Panel_ID")),
                    RB.inference_id(row, panel_id=_s(row.get("Run_Panel_ID"))))
                   in inference_rejected for _, row in keep.iterrows()]
        rejected_count = sum(1 for d in dropped if d)
        if rejected_count:
            keep = keep[[not d for d in dropped]].copy()
        if not len(keep):
            return stop("NOTHING_FINALIZABLE",
                        "every approved value's reconstruction was refused by "
                        "the person who looked at it", approved=approved)

    keep["Value_Status"] = "HUMAN_APPROVED"
    keep["Pooling_Eligible"] = "TRUE"
    keep["Review_ID"] = [_s(approved[p].get("Review_ID")) for p in keep["Run_Panel_ID"]]
    keep["Reviewer_ID"] = [_s(approved[p].get("Reviewer_ID")) for p in keep["Run_Panel_ID"]]
    keep["Reviewed_At"] = [_s(approved[p].get("Reviewed_At")) for p in keep["Run_Panel_ID"]]
    keep["Review_Subject_SHA256"] = [
        _s(approved[p].get("Review_Subject_SHA256")) for p in keep["Run_Panel_ID"]]
    return Verdict("FINALIZED", "", problems, approved, keep, blocked_count,
                   unstated, rejected_count, run_stamp_sha, review_sha,
                   inference_sha, snapshot[0])


def finalize(run_dir, review_path=None, manifest_dir=None, run_date="",
             today=None, fault_after=None, inference_review_path=None,
             separation_policy=None):
    """Read a completed run plus its decisions; write the accepted file or not.

    The DECIDING is `validate_finalization`, which the preflight calls too. What
    is left here is the writing, and the order it is written in: the previous
    finalization is removed first, the new one is staged, and the accepted file
    is promoted last - so poolable values never exist without a stamp behind
    them.
    """
    review_path, inference_review_path = review_paths(
        run_dir, review_path, inference_review_path)
    accepted_path = os.path.join(run_dir, FINALIZE_MARKER)
    stamp_path = os.path.join(run_dir, "finalize_stamp.json")
    staging = os.path.join(run_dir, FINALIZE_STAGING)

    # Whatever happens, the previous finalization does not survive this one.
    for stale in (accepted_path, stamp_path):
        if os.path.exists(stale):
            os.remove(stale)
    shutil.rmtree(staging, ignore_errors=True)

    verdict = validate_finalization(
        run_dir, review_path=review_path, manifest_dir=manifest_dir,
        today=today, inference_review_path=inference_review_path,
        separation_policy=separation_policy)
    problems = verdict.problems

    def stamp(status, detail, approved=0, accepted=0, accepted_sha="",
              directory=None, blocked=0, unstated=0, inference_rejected=0):
        payload = {"schema": FINALIZE_SCHEMA, "Status": status,
                   "Run_Date": run_date, "Panels_Approved": approved,
                   "Values_Accepted": accepted,
                   # How many approved values this finalization REFUSED because
                   # the number was not read off the ink, and how many could not
                   # be asked because their reader does not answer yet. A run
                   # that accepted forty values out of forty is a different
                   # artifact from one that accepted forty out of a hundred, and
                   # the stamp said the same thing for both.
                   "Values_Method_Blocked": blocked,
                   "Values_Method_Unstated": unstated,
                   # And how many reconstructions a person looked at and
                   # refused. A cell nobody answered for holds its panel and is
                   # not counted here: the two are different outcomes and the
                   # stamp said nothing about either.
                   "Values_Inference_Rejected": inference_rejected,
                   "Accepted_SHA256": accepted_sha,
                   "Run_Stamp_SHA256": verdict.run_stamp_sha,
                   "Pipeline_Version": RB.PIPELINE_VERSION,
                   "Pipeline_Code_SHA256": RB.pipeline_code_sha256(),
                   "Environment": RB.environment_record(),
                   "Review_File": review_path,
                   # The decisions themselves, hashed. The stamp named the
                   # review file by path and recorded nothing about its
                   # contents, so "which decisions produced this accepted
                   # file" was answerable only by trusting that nobody had
                   # since edited the answer.
                   # THE BYTES THE VERDICT WAS DECIDED FROM, hashed when they
                   # were read rather than re-hashed from the path afterwards. A
                   # save landing between the decision and the stamp used to
                   # produce an accepted file decided from one review and a hash
                   # naming another.
                   "Review_File_SHA256": verdict.review_sha,
                   # The per-cell decisions, by path and by content, for the same
                   # reason. Blank when no run in this batch asked for any.
                   "Inference_Review_File": inference_review_path,
                   "Inference_Review_File_SHA256": verdict.inference_sha,
                   # UNDER WHAT POLICY. A CLI flag that leaves no trace is a
                   # claim nobody can check afterwards: an accepted file has to
                   # be able to say whether resolver-approver separation was
                   # required of it, and NOT_DECLARED has to be as visible as
                   # the declaration.
                   # WHAT WAS APPLIED, canonicalised - never the caller's raw
                   # string. `UNRECOGNIZED` can only appear on a refusal, where
                   # the problem list names the token that was rejected: a stamp
                   # is a governance record, and echoing back an unenforced
                   # policy is the one way it can lie.
                   "Reviewer_Separation_Policy": (
                       canonical_policy(separation_policy) or "UNRECOGNIZED"),
                   "Problems": problems, "Detail": detail}
        with open(os.path.join(directory or run_dir, "finalize_stamp.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)

    def stop(status, detail, approved=0, accepted=0, blocked=0, unstated=0):
        # The counts travel with the refusal too. A NOTHING_FINALIZABLE stamp
        # reporting `Values_Method_Blocked: 0` says the opposite of what
        # happened: it refused everything and then reported refusing nothing,
        # and the problem list was the only place the truth survived.
        stamp(status, detail, approved=approved, accepted=accepted,
              blocked=blocked, unstated=unstated)
        return dict(status=status, approved=approved, accepted=accepted,
                    problems=problems, detail=detail)

    if verdict.status != "FINALIZED":
        return stop(verdict.status, verdict.detail,
                    approved=len(verdict.approved), blocked=verdict.blocked,
                    unstated=verdict.unstated)
    keep, approved = verdict.keep, verdict.approved

    # Staged, then promoted with the accepted file last. Writing it directly and
    # stamping afterwards left a window where poolable values existed with no
    # stamp behind them - the same shape `run_batch` already fixed.
    os.makedirs(staging, exist_ok=True)
    staged_accepted = os.path.join(staging, FINALIZE_MARKER)
    keep.to_csv(staged_accepted, index=False)
    accepted_sha = RB.file_sha256(staged_accepted)
    stamp("FINALIZED", "", approved=len(approved), accepted=len(keep),
          accepted_sha=accepted_sha, directory=staging,
          blocked=verdict.blocked, unstated=verdict.unstated,
          inference_rejected=verdict.inference_rejected)
    try:
        _promote(staging, run_dir, fault_after=fault_after)
    except Exception as exc:
        for leftover in (accepted_path,):
            if os.path.exists(leftover):
                os.remove(leftover)
        shutil.rmtree(staging, ignore_errors=True)
        problems.append(dict(where="commit", check="COMMIT_FAILED",
                             detail="%s: %s" % (type(exc).__name__, exc)))
        return stop("COMMIT_FAILED",
                    "the finalization did not complete; nothing is poolable")
    return dict(status="FINALIZED", approved=len(approved), accepted=len(keep),
                problems=problems, detail="")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--review", default=None,
                    help="the decision file (default RUN_DIR/value_review.csv)")
    ap.add_argument("--inference-review", default=None,
                    help="the per-cell decision file for reconstructed values "
                         "(default beside --review, as inference_review.csv)")
    ap.add_argument("--manifests", default=None,
                    help="the manifest directory (default RUN_DIR/manifests)")
    ap.add_argument("--date", default="")
    ap.add_argument("--template", action="store_true",
                    help="write an unfilled decision file from review_queue.csv "
                         "and exit")
    ap.add_argument("--distinct-reviewers", action="store_true",
                    help="require that nobody both resolved an identity on a "
                         "panel and signed it. Recorded in the stamp either "
                         "way, because an accepted file has to be able to say "
                         "which policy it was finalized under")
    args = ap.parse_args(argv)

    if args.template:
        queue_path = os.path.join(args.run_dir, "review_queue.csv")
        if not os.path.exists(queue_path):
            print("no review_queue.csv in %s" % args.run_dir)
            return 2
        out = args.review or os.path.join(args.run_dir, "value_review.csv")
        write_review_template(out, pd.read_csv(queue_path, dtype=object).fillna(""))
        print("wrote %s - fill Decision, Reviewer_ID and Reviewed_At" % out)
        # And the per-cell questions, when the run asked any. Written from the
        # run's own manifests, so the Inference_IDs are pre-filled: a reviewer
        # who had to copy a hash by hand would be one typo away from confirming
        # a different cell, and the exact-set contract would report it as an
        # answer to a question nobody asked.
        cells = collect_inference_manifests(args.run_dir)
        if cells:
            inf_out = args.inference_review or os.path.join(
                os.path.dirname(os.path.abspath(out)), "inference_review.csv")
            write_inference_template(inf_out, cells)
            print("wrote %s - %d reconstructed value(s); fill Reviewer_ID, "
                  "Inference_Confirmed and Reviewed_At for every row"
                  % (inf_out, len(cells)))
        return 0

    result = finalize(args.run_dir, review_path=args.review,
                      manifest_dir=args.manifests, run_date=args.date,
                      inference_review_path=args.inference_review,
                      separation_policy=(DISTINCT_RESOLVERS
                                         if args.distinct_reviewers else None))
    for p in result["problems"]:
        print("  %-10s %-38s %s" % (p["where"], p["check"], p["detail"]))
    print("%s | panels approved %d | values accepted %d"
          % (result["status"], result["approved"], result["accepted"]))
    if result["status"] == "FINALIZED":
        print("pool from figure_values_accepted.csv")
        return 0
    print(result["detail"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
