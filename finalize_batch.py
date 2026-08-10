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

FINALIZE_SCHEMA = "figure-digitization-triage/finalize-stamp/1"

#: `Marks_Checked` is not decoration beside `Decision`. An approval says a
#: person agreed; it does not say what they looked at, and the two are
#: different claims - the whole point of queueing a panel with an artifact is
#: that somebody opens it. `RB.REVIEW_CONFIRMATIONS` says which of these a mode
#: requires, so a mode that shows more can ask for more.
VALUE_REVIEW_COLUMNS = [
    "Review_ID", "Panel_ID", "Review_Subject_SHA256", "Reviewer_ID", "Decision",
    "Marks_Checked",
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
                     "RUN_ARTIFACT_MODIFIED", "COMMIT_FAILED")


def value_review_columns():
    return list(VALUE_REVIEW_COLUMNS)


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


def _s(v):
    return "" if v is None else str(v).strip()


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


def approved_panels(reviews, queue, reviewers, flag, today=None,
                    artifact_types=None):
    """Panel_ID -> the review row that approves it. Everything else is refused."""
    today = today or datetime.date.today()
    human = set()
    if reviewers is not None and "Reviewer_ID" in getattr(reviewers, "columns", ()):
        for _, r in reviewers.iterrows():
            if _s(r.get("Reviewer_Record_Type")).upper() == "HUMAN":
                human.add(_s(r.get("Reviewer_ID")))
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
        unconfirmed = [c for c in RB.REVIEW_CONFIRMATIONS.get(mode, ())
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


def verify_run_outputs(run_dir, run_stamp, manifest_dir, flag):
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
             today=None, fault_after=None):
    """Read a completed run plus its decisions; write the accepted file or not."""
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    review_path = review_path or os.path.join(run_dir, "value_review.csv")
    accepted_path = os.path.join(run_dir, FINALIZE_MARKER)
    stamp_path = os.path.join(run_dir, "finalize_stamp.json")
    staging = os.path.join(run_dir, FINALIZE_STAGING)

    # Whatever happens, the previous finalization does not survive this one.
    for stale in (accepted_path, stamp_path):
        if os.path.exists(stale):
            os.remove(stale)
    shutil.rmtree(staging, ignore_errors=True)

    def stamp(status, detail, approved=0, accepted=0, accepted_sha="",
              directory=None):
        payload = {"schema": FINALIZE_SCHEMA, "Status": status,
                   "Run_Date": run_date, "Panels_Approved": approved,
                   "Values_Accepted": accepted,
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
                   "Problems": problems, "Detail": detail}
        with open(os.path.join(directory or run_dir, "finalize_stamp.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)

    def stop(status, detail, approved=0, accepted=0):
        stamp(status, detail, approved=approved, accepted=accepted)
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

    if not verify_run_outputs(run_dir, run_stamp, manifest_dir, flag):
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

    try:
        reviewers = pd.read_csv(os.path.join(manifest_dir, "reviewer_registry.csv"),
                                dtype=object).fillna("")
    except Exception as exc:
        return stop("RUN_NOT_FINALIZABLE",
                    "reviewer_registry.csv could not be read from %s (%s)"
                    % (manifest_dir, exc))

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
    approved = approved_panels(reviews, queue, reviewers, flag, today=today,
                               artifact_types=artifact_types)

    if not approved:
        return stop("NOTHING_APPROVED",
                    "no panel carries an APPROVED decision from a registered "
                    "human against this run's fingerprints")

    keep = machine[machine["Run_Panel_ID"].isin(approved)].copy() if len(machine) \
        else machine.copy()
    if not len(keep):
        return stop("NOTHING_APPROVED",
                    "the approved panels produced no machine-QC-passed values",
                    approved=len(approved))

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
          accepted_sha=accepted_sha, directory=staging)
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
        return 0

    result = finalize(args.run_dir, review_path=args.review,
                      manifest_dir=args.manifests, run_date=args.date)
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
