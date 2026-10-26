#!/usr/bin/env python3
"""Take one synthetic figure through the whole pipeline.

    python3 examples/quickstart/quickstart.py WORK_DIR

WORK_DIR is created; nothing is written inside the repository. The figure is a
colour bar chart drawn by `tests/make_bar_fixture.py` (heart rate, two postures,
six sessions, mean +/- SD), so every number on it is known exactly.

THERE ARE TWO WAYS TO RUN IT, and the difference is the point of the package.

1. As a DEMONSTRATION (the default). The plan's only reviewer is ORCID's
   fictional demo record, so the run is `DEMO_ONLY`. The figure is read, the
   values pass the gate - and `run_batch` then refuses to leave them behind
   (`DEMO_OUTPUT_REFUSED`), because a demonstration identity cannot stand behind
   a poolable value. That refusal is the expected result.

2. As YOUR review, attested by you. Open the figure the script draws
   (`WORK_DIR/bar_fixture.png`), check that it has one panel, then run again
   with all four of these set - all four or none:

       FDT_REVIEWER_NAME="Your Name"
       FDT_REVIEWER_ORCID="0000-0000-0000-0000"   # your ORCID
       FDT_INSPECTION_DATE=YYYY-MM-DD             # the day you looked
       FDT_REGISTRATION_DATE=YYYY-MM-DD

   The run is then ATTESTED and stops at MACHINE_QC_PASSED with a review queue,
   an overlay picture and a pre-filled `value_review.csv`. What happens next is
   yours, not the script's: look at the overlay, fill in the review, run the
   preflight and the finalizer (the script prints the commands). Nothing here
   fills in a review answer for you.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FDT = os.path.join(ROOT, "fdt")
sys.path.insert(0, os.path.join(ROOT, "tests"))
import make_bar_fixture as FIXTURE                                   # noqa: E402

RUN_DATE = "2026-01-05"
ATTESTATION = ("FDT_REVIEWER_NAME", "FDT_REVIEWER_ORCID",
               "FDT_INSPECTION_DATE", "FDT_REGISTRATION_DATE")


def tool(script, *args):
    """Run one pipeline command the way a person would, and show it."""
    argv = [sys.executable, os.path.join(FDT, script)] + list(args)
    print("$ python3 fdt/%s %s" % (script, " ".join(args)))
    done = subprocess.run(argv, capture_output=True, text=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def attested_plan(plan, env):
    """The same plan, with the person who set the four variables as its reviewer."""
    plan = json.loads(json.dumps(plan))
    plan["reviewers"] = [{
        "reviewer_id": "RV_1", "name": env["FDT_REVIEWER_NAME"],
        "record_type": "HUMAN", "contact_type": "ORCID",
        "contact": env["FDT_REVIEWER_ORCID"],
        "registered_by": env["FDT_REVIEWER_NAME"],
        "registration_date": env["FDT_REGISTRATION_DATE"],
        "human_attestation": "HUMAN_CONFIRMED",
        "note": "set from FDT_REVIEWER_* by the person running the quickstart"}]
    for item in plan["documents"] + plan["figures"]:
        item["reviewer_id"] = "RV_1"
        item["inspection_date"] = env["FDT_INSPECTION_DATE"]
    return plan


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    work = os.path.abspath(argv[0])
    given = [k for k in ATTESTATION if os.environ.get(k, "").strip()]
    if given and len(given) != len(ATTESTATION):
        print("partial attestation: set all four of %s, or none"
              % ", ".join(ATTESTATION), file=sys.stderr)
        return 2
    attested = bool(given)

    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    FIXTURE.build(path=os.path.join(work, "bar_fixture.png"),
                  meta_path=os.path.join(work, "bar_fixture_truth.json"))
    with open(os.path.join(HERE, "plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    if attested:
        plan = attested_plan(plan, os.environ)
    plan_path = os.path.join(work, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1)

    manifests, out = os.path.join(work, "manifests"), os.path.join(work, "out")
    print("\n1. compile the plan into manifests")
    if tool("compile_plan.py", plan_path, manifests, "--file-root", work):
        return 1
    print("\n2. read the figure and gate the values")
    tool("run_batch.py", manifests, out, "--file-root", work, "--date", RUN_DATE)
    with open(os.path.join(out, "run_stamp.json"), encoding="utf-8") as fh:
        stamp = json.load(fh)
    print("\nrun stamp: Status=%s Run_Mode=%s Values_Read=%s"
          % (stamp.get("Status"), stamp.get("Run_Mode"), stamp.get("Values_Read")))

    if not attested:
        ok = (stamp.get("Status") == "DEMO_OUTPUT_REFUSED"
              and stamp.get("Run_Mode") == "DEMO_ONLY"
              and not os.path.exists(os.path.join(out, "figure_values_accepted.csv")))
        print("""
That refusal is the expected end of a demonstration: the figure was read and
the values passed the gate, but the only reviewer is a demo identity, so the run
leaves nothing that could be pooled.

To take it through a real review, open %s,
check it has one panel, and run again with FDT_REVIEWER_NAME, FDT_REVIEWER_ORCID,
FDT_INSPECTION_DATE and FDT_REGISTRATION_DATE set to yourself.
See docs/PROCEDURE.md for the full order of steps."""
              % os.path.join(work, "bar_fixture.png"))
        return 0 if ok else 1

    if stamp.get("Status") != "RAN" or not stamp.get("Values_Machine_QC_Passed"):
        print("the attested run did not reach MACHINE_QC_PASSED", file=sys.stderr)
        return 1
    print("\n3. write the review templates (identifiers pre-filled, answers blank)")
    if tool("finalize_batch.py", out, "--template"):
        return 1
    print("""
The run stopped at MACHINE_QC_PASSED. Nothing is poolable yet - that needs you.

  4. open   %(out)s/review_queue.csv          (Review_Mode says what to look at)
     open   %(out)s/review/P1_overlay.png     (is every label on the right bar?)
  5. fill   %(out)s/value_review.csv          Decision, Marks_Checked=CONFIRMED,
                                               Reviewer_ID=RV_1, Reviewed_At=<today>
  6. check  python3 fdt/review_preflight.py %(out)s --review %(out)s/value_review.csv
  7. accept python3 fdt/finalize_batch.py %(out)s --review %(out)s/value_review.csv

Success is %(out)s/figure_values_accepted.csv beside a finalize_stamp.json whose
Status is FINALIZED. Compare the accepted means with %(work)s/bar_fixture_truth.json.
See docs/REVIEW_RUNBOOK.md for what each confirmation claims."""
          % dict(out=out, work=work))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
