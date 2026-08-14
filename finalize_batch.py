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
import csv
import datetime
import hashlib
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
VERIFIED_OUTPUTS = ("figure_values_machine_qc.csv", "review_queue.csv",
                    "figure_values_raw.csv", "run_manifest.csv",
                    # The ledger of everything else. Verifying it is what makes
                    # the per-artifact hashes below trustworthy: without it the
                    # ledger could be rewritten to match tampered artifacts.
                    "panel_artifacts.csv")

FINALIZE_STAGING = ".finalize-staging"

#: Moved last. Its presence is what says a finalization committed.
FINALIZE_MARKER = "figure_values_accepted.csv"

FINALIZE_STATUSES = ("FINALIZED", "NOTHING_APPROVED", "RUN_NOT_FINALIZABLE",
                     "RUN_ARTIFACT_MODIFIED", "COMMIT_FAILED",
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


def load_reviews(path, flag):
    if not os.path.exists(path):
        flag("review", "REVIEW_FILE_MISSING",
             "%s does not exist. Nothing is approved by default" % path)
        return pd.DataFrame(columns=VALUE_REVIEW_COLUMNS)
    try:
        df = pd.read_csv(path, dtype=object).fillna("")
    except Exception as exc:
        flag("review", "REVIEW_FILE_UNREADABLE", "%s: %s" % (type(exc).__name__, exc))
        return pd.DataFrame(columns=VALUE_REVIEW_COLUMNS)
    missing = [c for c in VALUE_REVIEW_COLUMNS if c not in df.columns]
    if missing:
        flag("review", "REVIEW_SCHEMA_INCOMPLETE", ", ".join(missing))
        return pd.DataFrame(columns=VALUE_REVIEW_COLUMNS)
    return df


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
    panel_index = {}
    for _, panel in panels.iterrows():
        pid = _s(panel.get("Panel_ID"))
        prows = [r for _, r in series.iterrows()
                 if _s(r.get("Panel_ID")) == pid]
        qrows = [r for _, r in positions.iterrows()
                 if _s(r.get("Panel_ID")) == pid]
        panel_index[pid] = {
            "Mark_Type": _s(panel.get("Mark_Type")),
            "Unit_ID": _s(panel.get("Unit_ID")),
            "Source_Panel_ID": _s(panel.get("Source_Panel_ID")),
            "Figure_ID": _s(panel.get("Figure_ID")),
            "Identity_Domain_ID": _s(panel.get("Identity_Domain_ID")),
            "Cell_Map": {
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
            },
        }
    rows = (machine.to_dict("records") if hasattr(machine, "to_dict")
            else list(machine or ()))
    problems = RB.identity_provenance_problems(
        rows, panel_index,
        geometry=RB.geometry_index_from_run(run_dir),
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
                               frames=None):
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
            path = RB.resolve_artifact(run_dir, _s(art.get("Artifact_Path")))
            if path is None or not os.path.exists(path):
                # `verify_run_outputs` has already refused the whole run for
                # this; withholding the panel as well keeps the two independent.
                flag("panel:%s" % pid, "REVIEW_EVIDENCE_MISSING",
                     "the resolution rows for %s are not readable, so the "
                     "evidence behind them cannot be checked" % pid)
                withheld.add(pid)
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
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
    if not os.path.exists(path):
        return pd.DataFrame(columns=INFERENCE_REVIEW_COLUMNS)
    try:
        df = pd.read_csv(path, dtype=object).fillna("")
    except Exception as exc:
        flag("inference", "INFERENCE_FILE_UNREADABLE",
             "%s: %s" % (type(exc).__name__, exc))
        return pd.DataFrame(columns=INFERENCE_REVIEW_COLUMNS)
    missing = [c for c in INFERENCE_REVIEW_COLUMNS if c not in df.columns]
    if missing:
        flag("inference", "INFERENCE_SCHEMA_INCOMPLETE", ", ".join(missing))
        return pd.DataFrame(columns=INFERENCE_REVIEW_COLUMNS)
    return df


def inference_contract_failures(run_dir, ledger_rows, machine, decisions,
                                reviewers, flag, today=None, panels=()):
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
        tier = PROV.review_tier(_s(row.get("Identity_Method")),
                                _s(row.get("Value_Method")))
        if tier in PROV.CELL_CONFIRMATION_TIERS:
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
            listed = _inference_manifest_ids(run_dir, manifests[0], pid, flag)
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
        for iid in sorted(set(cells) - pictured):
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


def collect_inference_manifests(run_dir):
    """Every reconstructed cell this run wrote, in one list, for the template.

    Read off the ledger rather than by globbing the directory: the ledger is what
    the finalizer checks, so a file sitting in `inference-review/` that no panel
    registered would produce a template row for a cell nobody will be asked
    about.
    """
    try:
        ledger = pd.read_csv(os.path.join(run_dir, "panel_artifacts.csv"),
                             dtype=object).fillna("")
    except Exception:
        return []
    out = []
    for _, art in ledger.iterrows():
        if _s(art.get("Artifact_Type")) != RB.INFERENCE_ARTIFACT_TYPE:
            continue
        path = RB.resolve_artifact(run_dir, _s(art.get("Artifact_Path")))
        if path is None or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                out.extend(list(csv.DictReader(fh)))
        except Exception:
            continue
    return sorted(out, key=lambda r: (_s(r.get("Panel_ID")),
                                      _s(r.get("Cell_Key"))))


def _inference_manifest_ids(run_dir, artifact, pid, flag):
    """The Inference_IDs the run listed for one panel, or None if unreadable."""
    path = RB.resolve_artifact(run_dir, _s(artifact.get("Artifact_Path")))
    if path is None or not os.path.exists(path):
        flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISSING",
             "the inference manifest %s names for %s is not in the run"
             % (_s(artifact.get("Artifact_Path")) or "(blank)", pid))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except Exception as exc:
        flag("panel:%s" % pid, "INFERENCE_MANIFEST_MISSING",
             "%s's inference manifest could not be parsed (%s: %s)"
             % (pid, type(exc).__name__, exc))
        return None
    return {_s(r.get("Inference_ID")) for r in rows}


def method_contract_failures(machine, queue, ledger_rows, run_dir, flag):
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
        why = PROV.contract_failure(mark, identity, value)
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
    withheld |= _geometry_route_failures(machine, ledger_rows, run_dir, flag)
    return withheld


def _geometry_route_failures(machine, ledger_rows, run_dir, flag):
    """BAR_MONO values whose route disagrees with the figure's own answer."""
    withheld = set()
    by_row_hash = {}
    for _, art in ledger_rows.iterrows():
        if _s(art.get("Artifact_Type")) != "MONO_BAR_GEOMETRY":
            continue
        path = RB.resolve_artifact(run_dir, _s(art.get("Artifact_Path")))
        if path is None or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for geo in csv.DictReader(fh):
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
        if said and said != identity:
            flag("%s/%s" % (_s(row.get("Unit_ID")), _s(row.get("Cell_Key"))),
                 "METHOD_CONTRADICTS_GEOMETRY",
                 "the value says the figure named this bar by %s and the "
                 "geometry file this run wrote says %s. The route decides the "
                 "review tier, and the file that recorded it is attested"
                 % (identity, said))
            withheld.add(_s(row.get("Run_Panel_ID")))
    return withheld


def approved_panels(reviews, queue, reviewers, flag, today=None,
                    artifact_types=None, extra_confirmations=None):
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
    for name in VERIFIED_OUTPUTS:
        path = os.path.join(run_dir, name)
        if not os.path.exists(path):
            flag("run", "RUN_ARTIFACT_MODIFIED", "%s is gone" % name)
            ok = False
            continue
        actual = RB.file_sha256(path)
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
    try:
        ledger_df = pd.read_csv(ledger, dtype=object).fillna("")
    except Exception as exc:
        # It hashed correctly and still will not parse. Refusing is the only
        # honest answer, and it has to be a flagged refusal rather than a
        # traceback, or the run ends with no stamp explaining itself.
        flag("run", "RUN_ARTIFACT_MODIFIED",
             "panel_artifacts.csv could not be parsed (%s: %s)"
             % (type(exc).__name__, exc))
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

    registry_path = os.path.join(manifest_dir, "reviewer_registry.csv")
    if os.path.exists(registry_path):
        try:
            registry_df = pd.read_csv(registry_path, dtype=object).fillna("")
        except Exception as exc:
            flag("run", "REVIEWER_REGISTRY_CHANGED",
                 "the registry at %s could not be read (%s: %s)"
                 % (manifest_dir, type(exc).__name__, exc))
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


def finalize(run_dir, review_path=None, manifest_dir=None, run_date="",
             today=None, fault_after=None, inference_review_path=None):
    """Read a completed run plus its decisions; write the accepted file or not."""
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    review_path = review_path or os.path.join(run_dir, "value_review.csv")
    # Beside the panel decisions rather than in the run directory. The two files
    # are filled in together, `--review` is where a caller says where that is,
    # and a default anchored to the run would send a caller who moved one file
    # looking for the other in a different place.
    inference_review_path = inference_review_path or os.path.join(
        os.path.dirname(os.path.abspath(review_path)), "inference_review.csv")
    accepted_path = os.path.join(run_dir, FINALIZE_MARKER)
    stamp_path = os.path.join(run_dir, "finalize_stamp.json")
    staging = os.path.join(run_dir, FINALIZE_STAGING)

    # Whatever happens, the previous finalization does not survive this one.
    for stale in (accepted_path, stamp_path):
        if os.path.exists(stale):
            os.remove(stale)
    shutil.rmtree(staging, ignore_errors=True)

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
                   "Run_Stamp_SHA256": run_stamp_sha,
                   "Pipeline_Version": RB.PIPELINE_VERSION,
                   "Pipeline_Code_SHA256": RB.pipeline_code_sha256(),
                   "Environment": RB.environment_record(),
                   "Review_File": review_path,
                   # The decisions themselves, hashed. The stamp named the
                   # review file by path and recorded nothing about its
                   # contents, so "which decisions produced this accepted
                   # file" was answerable only by trusting that nobody had
                   # since edited the answer.
                   "Review_File_SHA256": RB.file_sha256_or_blank(review_path),
                   # The per-cell decisions, by path and by content, for the same
                   # reason. Blank when no run in this batch asked for any.
                   "Inference_Review_File": inference_review_path,
                   "Inference_Review_File_SHA256":
                       RB.file_sha256_or_blank(inference_review_path),
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

    run_stamp_path = os.path.join(run_dir, "run_stamp.json")
    run_stamp_sha = ""
    if not os.path.exists(run_stamp_path):
        run_stamp = {}
        return stop("RUN_NOT_FINALIZABLE", "no run_stamp.json in %s" % run_dir)
    # Guarded, like every other file this module reads. It was not, and the
    # accepted file and the previous stamp are deleted before this point - so
    # a truncated or non-UTF-8 `run_stamp.json` raised out of the finalizer
    # leaving the run with no result AND no stamp explaining the absence, which
    # is the one outcome this module is supposed to make impossible.
    run_stamp_sha = RB.file_sha256_or_blank(run_stamp_path)
    try:
        with open(run_stamp_path, encoding="utf-8") as fh:
            run_stamp = json.load(fh)
        if not isinstance(run_stamp, dict):
            raise ValueError("run_stamp.json holds a %s, not an object"
                             % type(run_stamp).__name__)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        run_stamp = {}
        return stop("RUN_NOT_FINALIZABLE",
                    "run_stamp.json could not be interpreted (%s: %s)"
                    % (type(exc).__name__, exc))
    # Where the manifests are, in the order that survives a moved run. The
    # stamp records an absolute path, so a run folder handed to somebody else
    # named a directory on the machine it was produced on; a `manifests/`
    # directory sitting inside the run is the one answer that travels with it.
    manifest_dir = (manifest_dir
                    or (os.path.join(run_dir, "manifests")
                        if os.path.isdir(os.path.join(run_dir, "manifests"))
                        else "")
                    or _s(run_stamp.get("Manifest_Dir"))
                    or os.path.join(run_dir, "manifests"))
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
        return stop("RUN_ARTIFACT_MODIFIED",
                    "the run this approval refers to is not the run on disk")

    try:
        machine = pd.read_csv(machine_path, dtype=object).fillna("")
        queue = pd.read_csv(queue_path, dtype=object).fillna("")
    except Exception as exc:
        # The bytes hashed correctly and still will not parse: that is a run
        # this module cannot read, not an approval it can refuse on the merits.
        return stop("RUN_NOT_FINALIZABLE",
                    "a verified run output could not be parsed (%s: %s)"
                    % (type(exc).__name__, exc))

    # The frame `verify_manifest_inputs` hashed, not the path read again. The
    # registry decides who may approve, so re-opening it after verifying it is
    # the same window the manifests were just closed against.
    reviewers = verified.get("reviewers")
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

    reviews = load_reviews(review_path, flag)
    # Which artifacts the run says each panel has. Read after the verification
    # above, so every entry here is one whose bytes have just been confirmed.
    artifact_types = {}
    try:
        ledger_rows = pd.read_csv(os.path.join(run_dir, "panel_artifacts.csv"),
                                  dtype=object).fillna("")
    except Exception as exc:
        return stop("RUN_NOT_FINALIZABLE",
                    "the artifact ledger could not be parsed (%s: %s)"
                    % (type(exc).__name__, exc))
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
    for pid in sorted(identity_contract_failures(run_dir, ledger_rows, machine,
                                                flag, frames=verified)):
        artifact_types.pop(pid, None)
    # And the runner's own value contract, re-run here on the verified files.
    # A run this module did not produce is the case it exists for, and nothing
    # pins a minimum pipeline version: a run made before a check existed arrives
    # looking complete.
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
                                               run_dir, flag)):
        artifact_types.pop(pid, None)
        contract_refused.add(pid)
    approved = approved_panels(reviews, queue, reviewers, flag, today=today,
                               artifact_types=artifact_types,
                               extra_confirmations=extra_confirmations)
    for pid in sorted(contract_refused):
        approved.pop(pid, None)

    if not approved:
        return stop("NOTHING_APPROVED",
                    "no panel carries an APPROVED decision from a registered "
                    "human against this run's fingerprints")

    # AND THE CELLS THAT WERE ASKED ABOUT ONE AT A TIME. Run over the approved
    # panels only: a panel nobody approved is already refused, and reporting its
    # unanswered per-cell questions would bury the reason it was refused.
    inference_held, inference_rejected = inference_contract_failures(
        run_dir, ledger_rows, machine,
        load_inference_reviews(inference_review_path, flag), reviewers, flag,
        today=today, panels=set(approved))
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
                    approved=len(approved))

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
            tiers.append(PROV.review_tier(identity, value))
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
                        "can finalize", approved=len(approved),
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
                        "the person who looked at it", approved=len(approved))

    keep["Value_Status"] = "HUMAN_APPROVED"
    keep["Pooling_Eligible"] = "TRUE"
    keep["Review_ID"] = [_s(approved[p].get("Review_ID")) for p in keep["Run_Panel_ID"]]
    keep["Reviewer_ID"] = [_s(approved[p].get("Reviewer_ID")) for p in keep["Run_Panel_ID"]]
    keep["Reviewed_At"] = [_s(approved[p].get("Reviewed_At")) for p in keep["Run_Panel_ID"]]
    keep["Review_Subject_SHA256"] = [
        _s(approved[p].get("Review_Subject_SHA256")) for p in keep["Run_Panel_ID"]]

    # Staged, then promoted with the accepted file last. Writing it directly and
    # stamping afterwards left a window where poolable values existed with no
    # stamp behind them - the same shape `run_batch` already fixed.
    os.makedirs(staging, exist_ok=True)
    staged_accepted = os.path.join(staging, FINALIZE_MARKER)
    keep.to_csv(staged_accepted, index=False)
    accepted_sha = RB.file_sha256(staged_accepted)
    stamp("FINALIZED", "", approved=len(approved), accepted=len(keep),
          accepted_sha=accepted_sha, directory=staging,
          blocked=blocked_count, unstated=unstated,
          inference_rejected=rejected_count)
    try:
        _promote(staging, run_dir, fault_after=fault_after)
    except Exception as exc:
        for leftover in (accepted_path,):
            if os.path.exists(leftover):
                os.remove(leftover)
        shutil.rmtree(staging, ignore_errors=True)
        flag("commit", "COMMIT_FAILED", "%s: %s" % (type(exc).__name__, exc))
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
                      inference_review_path=args.inference_review)
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
