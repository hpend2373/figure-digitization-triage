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
`Panel_Fingerprint` over the image hash, the config hash, the reader version,
the pipeline code hash and the cell count. Re-run with different code and every
prior approval goes stale; it is not inherited.

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
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                       # noqa: E402
import run_batch as RB                                             # noqa: E402

FINALIZE_SCHEMA = "figure-digitization-triage/finalize-stamp/1"

VALUE_REVIEW_COLUMNS = [
    "Review_ID", "Panel_ID", "Panel_Fingerprint", "Reviewer_ID", "Decision",
    "Reviewed_At", "Note",
]

FINALIZE_STATUSES = ("FINALIZED", "NOTHING_APPROVED", "RUN_NOT_FINALIZABLE",
                     "REVIEW_REJECTED")


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
                        r.get("Panel_Fingerprint", ""), "", "", "", ""])
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


def approved_panels(reviews, queue, reviewers, flag, today=None):
    """Panel_ID -> the review row that approves it. Everything else is refused."""
    today = today or datetime.date.today()
    human = set()
    if reviewers is not None and "Reviewer_ID" in getattr(reviewers, "columns", ()):
        for _, r in reviewers.iterrows():
            if _s(r.get("Reviewer_Record_Type")).upper() == "HUMAN":
                human.add(_s(r.get("Reviewer_ID")))
    expected = {_s(r.get("Panel_ID")): _s(r.get("Panel_Fingerprint"))
                for _, r in queue.iterrows()}

    out, seen = {}, {}
    for i, r in reviews.iterrows():
        line = "review:%d" % (i + 2)
        pid = _s(r.get("Panel_ID"))
        decision = _s(r.get("Decision")).upper()
        if not pid:
            flag(line, "MISSING_REQUIRED", "Panel_ID")
            continue
        if pid not in expected:
            flag(line, "REVIEW_PANEL_NOT_IN_QUEUE",
                 "%s did not pass machine QC in this run, so there is nothing "
                 "for a decision to apply to" % pid)
            continue
        if pid in seen:
            flag(line, "DUPLICATE_REVIEW",
                 "%s already has a decision at %s" % (pid, seen[pid]))
            continue
        seen[pid] = line
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
        got = _s(r.get("Panel_Fingerprint"))
        if got != expected[pid]:
            flag(line, "APPROVAL_STALE",
                 "the approval is for fingerprint %s..., this run produced "
                 "%s.... The image, the config, the reader or the pipeline "
                 "changed since somebody looked"
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


def finalize(run_dir, review_path=None, manifest_dir=None, run_date="", today=None):
    """Read a completed run plus its decisions; write the accepted file or not."""
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    review_path = review_path or os.path.join(run_dir, "value_review.csv")
    manifest_dir = manifest_dir or os.path.join(run_dir, "manifests")
    accepted_path = os.path.join(run_dir, "figure_values_accepted.csv")
    stamp_path = os.path.join(run_dir, "finalize_stamp.json")

    # Whatever happens, the previous finalization does not survive this one.
    if os.path.exists(accepted_path):
        os.remove(accepted_path)

    def stop(status, detail, approved=0, accepted=0):
        with open(stamp_path, "w", encoding="utf-8") as fh:
            json.dump({"schema": FINALIZE_SCHEMA, "Status": status,
                       "Run_Date": run_date, "Panels_Approved": approved,
                       "Values_Accepted": accepted,
                       "Pipeline_Version": RB.PIPELINE_VERSION,
                       "Pipeline_Code_SHA256": RB.pipeline_code_sha256(),
                       "Review_File": review_path,
                       "Problems": problems, "Detail": detail},
                      fh, indent=1, sort_keys=True)
        return dict(status=status, approved=approved, accepted=accepted,
                    problems=problems, detail=detail)

    run_stamp_path = os.path.join(run_dir, "run_stamp.json")
    if not os.path.exists(run_stamp_path):
        return stop("RUN_NOT_FINALIZABLE", "no run_stamp.json in %s" % run_dir)
    with open(run_stamp_path, encoding="utf-8") as fh:
        run_stamp = json.load(fh)
    if run_stamp.get("Status") != "RAN":
        return stop("RUN_NOT_FINALIZABLE",
                    "the run says Status=%s; only a completed run can be "
                    "finalized" % run_stamp.get("Status"))
    if run_stamp.get("Run_Mode") != "ATTESTED":
        return stop("RUN_NOT_FINALIZABLE",
                    "the run says Run_Mode=%s. No number of approvals promotes a "
                    "demonstration" % run_stamp.get("Run_Mode"))

    machine_path = os.path.join(run_dir, "figure_values_machine_qc.csv")
    queue_path = os.path.join(run_dir, "review_queue.csv")
    for path in (machine_path, queue_path):
        if not os.path.exists(path):
            return stop("RUN_NOT_FINALIZABLE", "%s is missing" % path)
    machine = pd.read_csv(machine_path, dtype=object).fillna("")
    queue = pd.read_csv(queue_path, dtype=object).fillna("")

    try:
        reviewers = pd.read_csv(os.path.join(manifest_dir, "reviewer_registry.csv"),
                                dtype=object).fillna("")
    except Exception as exc:
        return stop("RUN_NOT_FINALIZABLE",
                    "reviewer_registry.csv could not be read from %s (%s)"
                    % (manifest_dir, exc))

    reviews = load_reviews(review_path, flag)
    approved = approved_panels(reviews, queue, reviewers, flag, today=today)

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
    keep["Panel_Fingerprint"] = [_s(approved[p].get("Panel_Fingerprint"))
                                 for p in keep["Run_Panel_ID"]]
    keep.to_csv(accepted_path, index=False)
    return stop("FINALIZED", "", approved=len(approved), accepted=len(keep))


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
