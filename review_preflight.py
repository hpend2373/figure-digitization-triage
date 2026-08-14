"""Everything about a review that can be checked without looking at the figure.

    python3 review_preflight.py OUT/ [--review value_review.csv]
                                     [--inference inference_review.csv]
                                     [--second other_reviewer/]

A human review of an R2 or R3 panel is a person looking at ink and saying what
they see. Nothing here does that, and nothing here may: the attestation in
`value_review.csv` is a claim about what somebody saw, and a program filling it
in is the one failure this whole package is built to prevent.

What a program CAN do is everything around it, and doing it badly is how a review
becomes a formality:

    say which cells are going to be asked about, and why, before anybody starts
    check the bundle is complete - every question has its picture and its row
    check the answers are complete - no blank, no duplicate, no answer to a
        question this run did not ask
    compare two reviewers who worked independently, cell by cell
    say what WOULD happen at finalization, without finalizing

The last one matters most for a first pilot. `finalize` refuses a panel for eight
different reasons and a reviewer should meet none of them for the first time
after signing.

Exit status is 0 when the bundle and the answers are consistent, 2 when they are
not, and 1 when the run cannot be read at all. Nothing here writes to the run.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pandas as pd                                                # noqa: E402

import finalize_batch as FIN                                       # noqa: E402
import provenance as PROV                                          # noqa: E402
import run_batch as RB                                             # noqa: E402


def _s(value):
    return "" if value is None else str(value).strip()


def _read(path, columns=None):
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns or [])
    return pd.read_csv(path, dtype=object).fillna("")


def questions(run_dir):
    """Every cell this run will ask a person about, with the reason.

    Derived from the values exactly as `run_batch` and `finalize` derive it -
    `row_tier` over the three provenance axes - so a reviewer preparing with this
    and a finalizer refusing with that cannot disagree about which cells are in
    play.
    """
    machine = _read(os.path.join(run_dir, "figure_values_machine_qc.csv"))
    out = []
    for _, row in machine.iterrows():
        tier = PROV.row_tier(row)
        if tier not in PROV.PANEL_CONFIRMATION_TIERS:
            continue
        panel = _s(row.get("Run_Panel_ID"))
        out.append({
            "Panel_ID": panel,
            "Unit_ID": _s(row.get("Unit_ID")),
            "Cell_Key": _s(row.get("Cell_Key")),
            "Tier": tier,
            "Inference_ID": (RB.inference_id(row, panel_id=panel)
                             if tier in PROV.CELL_CONFIRMATION_TIERS else ""),
            # WHY, in the words of the question. A reviewer told "confirm the
            # inference" and given a cell key has to reconstruct what is being
            # asked; the three methods say it.
            "Asked_Because": _asked_because(row),
        })
    return sorted(out, key=lambda r: (r["Panel_ID"], r["Cell_Key"]))


def _asked_because(row):
    identity = _s(row.get("Identity_Method"))
    value = _s(row.get("Value_Method"))
    spread = _s(row.get("Dispersion_Method"))
    if PROV.identity_tier(identity) in PROV.PANEL_CONFIRMATION_TIERS:
        return "the SERIES was reasoned to: %s" % identity
    if PROV.value_tier(value) in PROV.CELL_CONFIRMATION_TIERS:
        return "the NUMBER was reconstructed: %s" % value
    return "the SPREAD needs a look: %s" % (spread or "unstated")


def bundle_problems(run_dir):
    """What is missing from the bundle a reviewer is about to open."""
    problems = []
    ledger = _read(os.path.join(run_dir, "panel_artifacts.csv"))
    pictured = {_s(r.get("Artifact_Reference"))
                for _, r in ledger.iterrows()
                if _s(r.get("Artifact_Type"))
                == RB.INFERENCE_CONTEXT_ARTIFACT_TYPE}
    listed = {_s(r.get("Inference_ID"))
              for r in FIN.collect_inference_manifests(run_dir)}
    machine = _read(os.path.join(run_dir, "figure_values_machine_qc.csv"))
    for question in questions(run_dir):
        iid = question["Inference_ID"]
        if not iid:
            continue
        if iid not in listed:
            problems.append(("%s/%s" % (question["Unit_ID"],
                                        question["Cell_Key"]),
                             "not on the panel's inference manifest"))
        # Only the reconstructed NUMBERS get a crop; a cell asked about for its
        # spread is judged on the panel overlay, which `finalize` matches.
        row = next((r for _, r in machine.iterrows()
                    if _s(r.get("Cell_Key")) == question["Cell_Key"]
                    and _s(r.get("Run_Panel_ID")) == question["Panel_ID"]),
                   None)
        if row is None:
            continue
        if (PROV.value_tier(_s(row.get("Value_Method")))
                in PROV.CELL_CONFIRMATION_TIERS and iid not in pictured):
            problems.append(("%s/%s" % (question["Unit_ID"],
                                        question["Cell_Key"]),
                             "no context picture is registered for it"))
    return problems


def answer_problems(run_dir, review_path, inference_path):
    """What is missing from the answers, before a finalizer is asked."""
    problems = []
    asked = {q["Inference_ID"]: q for q in questions(run_dir)
             if q["Inference_ID"]}
    answers = _read(inference_path, FIN.inference_review_columns())
    seen = {}
    for _, row in answers.iterrows():
        iid = _s(row.get("Inference_ID"))
        seen.setdefault(iid, []).append(row)
        if iid not in asked:
            problems.append((iid or "(blank)",
                             "answers a question this run did not ask"))
    for iid, question in sorted(asked.items()):
        rows = seen.get(iid, [])
        if not rows:
            problems.append(("%s/%s" % (question["Unit_ID"],
                                        question["Cell_Key"]),
                             "has no answer (%s)" % question["Asked_Because"]))
            continue
        if len(rows) > 1:
            problems.append((iid, "has %d answers" % len(rows)))
            continue
        verdict = _s(rows[0].get("Inference_Confirmed")).upper()
        if verdict not in RB.INFERENCE_DECISIONS:
            problems.append((iid, "says %r, which is neither %s"
                             % (verdict, " nor ".join(RB.INFERENCE_DECISIONS))))
    # And the panel decisions, for the confirmation the values ask for.
    reviews = _read(review_path, FIN.value_review_columns())
    queue = _read(os.path.join(run_dir, "review_queue.csv"))
    machine = _read(os.path.join(run_dir, "figure_values_machine_qc.csv"))
    by_panel = {}
    for _, row in machine.iterrows():
        by_panel.setdefault(_s(row.get("Run_Panel_ID")), []).append(row)
    for _, panel in queue.iterrows():
        pid = _s(panel.get("Panel_ID"))
        wanted = (tuple(RB.REVIEW_CONFIRMATIONS.get(
            _s(panel.get("Review_Mode")), ()))
            + RB.inference_confirmations(by_panel.get(pid, [])))
        decision = next((r for _, r in reviews.iterrows()
                         if _s(r.get("Panel_ID")) == pid), None)
        if decision is None:
            problems.append((pid, "has no decision row"))
            continue
        for column in wanted:
            if _s(decision.get(column)).upper() != RB.REVIEW_CONFIRMED:
                problems.append((pid, "does not say %s was checked" % column))
    return problems


def disagreements(first, second):
    """Where two independent reviewers answered the same cell differently.

    Both files are read as answers to the SAME questions - the identifiers are
    content-derived, so two reviewers working from two copies of the bundle
    produce comparable rows without agreeing on anything first.
    """
    def verdicts(path):
        return {_s(r.get("Inference_ID")):
                _s(r.get("Inference_Confirmed")).upper()
                for _, r in _read(path, FIN.inference_review_columns()).iterrows()}

    one, two = verdicts(first), verdicts(second)
    out = []
    for iid in sorted(set(one) | set(two)):
        if one.get(iid) != two.get(iid):
            out.append((iid, one.get(iid) or "(no answer)",
                        two.get(iid) or "(no answer)"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--review", default=None)
    ap.add_argument("--inference", default=None)
    ap.add_argument("--second", default=None,
                    help="a second reviewer's inference_review.csv, to compare")
    args = ap.parse_args(argv)

    if not os.path.exists(os.path.join(args.run_dir, "run_stamp.json")):
        print("%s is not a run directory" % args.run_dir)
        return 1
    review = args.review or os.path.join(args.run_dir, "value_review.csv")
    inference = args.inference or os.path.join(
        os.path.dirname(os.path.abspath(review)), "inference_review.csv")

    asked = questions(args.run_dir)
    print("%d cell(s) will be asked about" % len(asked))
    for q in asked:
        print("  %-14s %-34s %s  %s"
              % (q["Panel_ID"], q["Cell_Key"], q["Tier"], q["Asked_Because"]))
    bundle = bundle_problems(args.run_dir)
    for where, why in bundle:
        print("  BUNDLE   %-34s %s" % (where, why))
    answers = answer_problems(args.run_dir, review, inference)
    for where, why in answers:
        print("  ANSWERS  %-34s %s" % (where, why))
    if args.second:
        for iid, a, b in disagreements(inference, args.second):
            print("  DIFFER   %-34s %s against %s" % (iid, a, b))
    print("%d bundle problem(s), %d answer problem(s)"
          % (len(bundle), len(answers)))
    # WHAT WOULD HAPPEN, without doing it. `finalize` is not called: it writes,
    # and a preflight that finalizes is not a preflight.
    print("nothing here signs anything: the confirmations are a person's claim "
          "about what they saw")
    return 2 if (bundle or answers) else 0


if __name__ == "__main__":
    raise SystemExit(main())
