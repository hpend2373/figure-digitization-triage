"""Everything about a review that can be checked without looking at the figure.

    python3 review_preflight.py OUT/ [--review value_review.csv]
                                     [--inference inference_review.csv]
                                     [--manifests MANIFEST_DIR]
                                     [--second other_inference_review.csv]
                                     [--distinct-reviewers]
                                     [--require-all-values]

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

Exit status is the FINALIZER's answer, not a count of lines printed: 0 when the
run would finalize, 2 when it would not, and 1 when the run cannot be read at
all. A reconstruction a person correctly REJECTED is a review done right - the
run finalizes without that cell - so it is reported as an exclusion and does not
fail the preflight. Pass `--require-all-values` when a batch is only acceptable
whole - it fails on any excluded value AND on any refused panel. Nothing here
writes to the run.
"""
import argparse
import collections
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


def _read(path, columns=None, problems=None):
    """A frame, or an empty one and a problem: never a traceback.

    The preflight reads several of the same CSVs the finalizer does. Unguarded,
    a malformed `value_review.csv` raised out of `pd.read_csv` here - so the
    reviewer got a stack trace where the finalizer would have given them
    `REVIEW_FILE_UNREADABLE` and a line saying which file, which is the whole
    difference between a tool and a crash.
    """
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns or [])
    try:
        return pd.read_csv(path, dtype=object).fillna("")
    except Exception as exc:
        if problems is not None:
            problems.append((os.path.basename(path),
                             "could not be parsed (%s: %s)"
                             % (type(exc).__name__, exc)))
        return pd.DataFrame(columns=columns or [])


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


def would_refuse(run_dir, review_path, inference_path, today=None,
                 manifest_dir=None, separation_policy=None):
    """What the finalizer would say, run through the finalizer's own function.

    `FIN.validate_finalization` decides; `FIN.finalize` wraps it and writes. This
    calls the decider, so the preflight cannot report a clean bundle that the
    finalizer then refuses - which it could while the two answered overlapping
    questions through separate code, and which is the worst failure a preflight
    has, because the reviewer trusts it and signs.

    `manifest_dir` is passed through for the same reason it exists on the
    finalizer: a run that has been moved, or one whose manifests live outside it,
    is checked against the manifests the CALLER names. One shared function with
    two different inputs is not parity - the preflight would fail on the run
    directory while `finalize_batch.py --manifests DIR` succeeded.

    Returns (status, [(where, check, detail)]).
    """
    verdict = FIN.validate_finalization(
        run_dir, review_path=review_path, inference_review_path=inference_path,
        today=today, manifest_dir=manifest_dir,
        separation_policy=separation_policy)
    return verdict.status, [(_s(p.get("where")), _s(p.get("check")),
                             _s(p.get("detail"))) for p in verdict.problems]


def disagreements(first, second):
    """Where two independent reviewers answered the same cell differently.

    Both files are read as answers to the SAME questions - the identifiers are
    content-derived, so two reviewers working from two copies of the bundle
    produce comparable rows without agreeing on anything first.

    A file that answers one cell TWICE is a problem, not a merge. The first
    version built each side with a dict comprehension, so the second row silently
    won and two reviewers who each contradicted themselves could be reported as
    agreeing.
    """
    def verdicts(path):
        out, seen = {}, collections.Counter()
        for _, r in _read(path, FIN.inference_review_columns()).iterrows():
            iid = _s(r.get("Inference_ID"))
            seen[iid] += 1
            out[iid] = _s(r.get("Inference_Confirmed")).upper()
        return out, {iid: n for iid, n in seen.items() if n > 1}

    one, dup_one = verdicts(first)
    two, dup_two = verdicts(second)
    # COUNTED, not "at least twice". The first version deduplicated the list of
    # duplicates and then counted occurrences IN THAT LIST, so three answers to
    # one cell reported as two - a number that is wrong in the direction of
    # looking smaller.
    out = [(iid, "(answered %d times)" % n, "")
           for iid, n in sorted(dup_one.items())]
    out += [(iid, "", "(answered %d times)" % n)
            for iid, n in sorted(dup_two.items())]
    for iid in sorted(set(one) | set(two)):
        if iid in dup_one or iid in dup_two:
            continue                  # already reported, and its verdict is moot
        if one.get(iid) != two.get(iid):
            out.append((iid, one.get(iid) or "(no answer)",
                        two.get(iid) or "(no answer)"))
    return out


def second_comparison(inference_path, second_path):
    """What a `--second` run actually compared, and the cells it disagreed on.

    `--second` reads two `inference_review.csv` files, so the channel it compares
    is the per-cell CONFIRMED/REJECTED one and NOTHING ELSE: not the panel
    decision, not the confirmations a mode asks for, not an identity somebody
    resolved by hand. On a run with no reconstructed cell it therefore compares
    nothing at all - and v7.94 offered exactly that as the fallback when a
    second person was impossible, on a first pilot the file itself says has no
    R3 cell. Two empty files agree, the flag prints nothing, and one person
    doing both roles reads as an independent check having happened.

    Returns `(compared, differences)`. `compared` is the cells that were
    ACTUALLY compared - answered exactly once, with a verdict this package
    accepts, on BOTH sides. v7.95 counted the UNION and over-reported in the one
    direction that matters: five answers against an empty file read as five
    cells compared, when nothing was compared at all. On an R3 pilot that is the
    same failure the two-empty-files case is, one reviewer short instead of two.
    """
    def answered(path):
        out, seen = {}, collections.Counter()
        for _, r in _read(path, FIN.inference_review_columns()).iterrows():
            iid = _s(r.get("Inference_ID"))
            if not iid:
                continue
            seen[iid] += 1
            out[iid] = _s(r.get("Inference_Confirmed")).upper()
        return {iid: verdict for iid, verdict in out.items()
                if seen[iid] == 1 and verdict in RB.INFERENCE_DECISIONS}

    one, two = answered(inference_path), answered(second_path)
    return (sorted(set(one) & set(two)),
            disagreements(inference_path, second_path))


def second_problems(inference_path, second_path, reviewers=None):
    """Why a `--second` run is not evidence that a second PERSON reviewed.

    Counting the cells both files answered says the two files agree. It says
    nothing about where the second file came from, and v7.96 checked nothing
    else - so

        review_preflight.py OUT --inference review_A.csv --second review_A.csv

    exited 0 on a complete answer set, and so did a copy of that file carrying
    the same `Reviewer_ID`. A flag whose whole purpose is to evidence independent
    review has to establish that the second reading is somebody else's.

    Three things, and none of them is the comparison itself: the two files are
    two files, each compared cell was answered by two DIFFERENT people, and both
    of those people are registered HUMAN reviewers. The identity comparison is
    on `Reviewer_ID` here rather than on a person key, because the per-cell file
    is not the panel signature and `--second` is not part of the finalization
    contract - it is a read-only qualification check a person runs to see whether
    two independent readings exist. What makes it worth running is that it can
    now say NO.
    """
    problems = []
    if os.path.realpath(inference_path) == os.path.realpath(second_path):
        problems.append(("--second",
                         "is the same file as --inference; a file agrees with "
                         "itself"))
    human = FIN.human_reviewers(reviewers) if reviewers is not None else None

    def by_cell(path):
        out = {}
        for _, r in _read(path, FIN.inference_review_columns()).iterrows():
            iid = _s(r.get("Inference_ID"))
            if iid:
                out.setdefault(iid, []).append(_s(r.get("Reviewer_ID")))
        return out

    first, second = by_cell(inference_path), by_cell(second_path)
    for iid in sorted(set(first) & set(second)):
        who_one = [w for w in first[iid] if w]
        who_two = [w for w in second[iid] if w]
        if not who_one or not who_two:
            problems.append((iid, "an answer with no Reviewer_ID cannot be "
                                  "attributed to a second reader"))
            continue
        if set(who_one) & set(who_two):
            problems.append((iid, "both answers are %s; one person answering "
                                  "twice is not two readings"
                             % "/".join(sorted(set(who_one) & set(who_two)))))
            continue
        if human is not None:
            outside = sorted({w for w in who_one + who_two if w not in human})
            if outside:
                problems.append((iid, "%s is not a registered HUMAN reviewer"
                                 % "/".join(outside)))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--review", default=None)
    ap.add_argument("--inference", default=None)
    ap.add_argument("--manifests", default=None, metavar="DIR",
                    help="the manifests this run was produced from, when they "
                         "are not inside it. The same argument finalize_batch.py "
                         "takes, and it must be the same directory")
    ap.add_argument("--second", default=None, metavar="FILE",
                    help="a second reviewer's inference_review.csv file, to "
                         "compare cell by cell. THIS CHANNEL ONLY: it cannot "
                         "compare panel decisions, the confirmations a mode "
                         "asks for, or a hand-resolved identity, so on a run "
                         "with no reconstructed cell it compares nothing and "
                         "says so")
    ap.add_argument("--distinct-reviewers", action="store_true",
                    help="the finalizer's --distinct-reviewers, asked in "
                         "advance: refuse a panel whose approver also resolved "
                         "an identity on it. The two must be given the same "
                         "flag or they answer different questions")
    ap.add_argument("--require-all-values", action="store_true",
                    help="fail unless the whole batch went through: no value "
                         "excluded AND no panel refused. Off by default, because "
                         "a REJECTED reconstruction is a review done right and "
                         "the run finalizes without that cell")
    args = ap.parse_args(argv)

    if not os.path.exists(os.path.join(args.run_dir, "run_stamp.json")):
        print("%s is not a run directory" % args.run_dir)
        return 1
    review, inference = FIN.review_paths(args.run_dir, args.review,
                                         args.inference)

    # THE SHARED VERDICT FIRST. Everything below it is help for a person; this is
    # the answer, and it comes from the function the finalizer decides with. Run
    # last, a malformed decision file crashed the preflight's own reading of it
    # before the finalizer's structured refusal was ever reached.
    status, refusals = would_refuse(
        args.run_dir, review, inference, manifest_dir=args.manifests,
        separation_policy=(FIN.DISTINCT_RESOLVERS
                           if args.distinct_reviewers else None))
    excluded = [r for r in refusals if r[1] in FIN.NONFATAL_CHECKS]
    blocking = [r for r in refusals if r[1] not in FIN.NONFATAL_CHECKS]
    print("the finalizer would say %s" % status)
    for where, check, detail in blocking:
        print("  WOULD    %-34s %s: %s" % (where, check, detail))
    for where, check, detail in excluded:
        print("  EXCLUDED %-34s %s: %s" % (where, check, detail))

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
    compared = differ = None
    second_bad = []
    if args.second:
        compared, differ = second_comparison(inference, args.second)
        # WHO the second reading came from, which needs the registry. Loaded
        # from the same directory the finalizer was pointed at, and skipped
        # rather than guessed when it cannot be read - a missing registry is
        # already `RUN_NOT_FINALIZABLE` above.
        mdir = args.manifests or os.path.join(args.run_dir, "manifests")
        registry = None
        try:
            registry = RB.load_manifests(mdir).get("reviewers")
        except Exception:
            registry = None
        second_bad = second_problems(inference, args.second, registry)
        for where, why in second_bad:
            print("  SECOND   %-34s %s" % (where, why))
        for iid, a, b in differ:
            print("  DIFFER   %-34s %s against %s" % (iid, a, b))
        # BOTH NUMBERS, because they answer different questions. The asked count
        # is the size of the job; the compared count is how much of it two people
        # actually did twice. Printing only the second let a five-question run
        # with one reviewer's file missing read as "5 compared".
        print("  SECOND   %d of %d reconstructed cell(s) compared twice. "
              "--second reads two inference_review.csv files and compares that "
              "channel only: not the panel decision, not the confirmations its "
              "mode asks for, not a hand-resolved identity"
              % (len(compared), len([q for q in asked if q["Inference_ID"]])))
        if not compared:
            print("  SECOND   nothing was compared, so no independent check "
                  "happened here. Two people, or none")
        print("  SECOND   this is a read-only qualification check, not part of "
              "the finalization contract: the finalizer reads --inference and "
              "never the second file")
    print("%d bundle problem(s), %d answer problem(s), %d refusal(s), "
          "%d value(s) excluded"
          % (len(bundle), len(answers), len(blocking), len(excluded)))
    print("nothing here signs anything: the confirmations are a person's claim "
          "about what they saw")
    # THE EXIT CODE IS THE FINALIZER'S ANSWER, not a count of lines printed. It
    # was "any problem at all", which made a correctly REJECTED reconstruction -
    # a review done right, and the case the first pilot is designed around -
    # indistinguishable from an unanswered question.
    if status != FIN.FINALIZED_STATUS:
        return 2
    # AND A `--second` THAT DID NOT ACTUALLY COMPARE IS NOT AN INDEPENDENT CHECK.
    # v7.95 for the empty case, v7.96 for the rest. Asking for one and being told
    # nothing is the failure this exit code exists for: a run with no
    # reconstructed cell has no per-cell channel, the two files are two empty
    # templates, and the flag agreeing with itself is what a single reviewer
    # doing both roles would see.
    #
    # THREE MORE WAYS TO GET NOTHING while looking like something, all of them
    # exit 2 now: a cell one file answered and the other did not, a cell answered
    # twice on either side, and a cell the two answered DIFFERENTLY. The last is
    # not a bundle problem and not a refusal - the finalizer only ever reads the
    # first file, so a second reviewer who disagrees changes nothing it can see.
    # Reporting the difference and exiting 0 was telling a person the review
    # passed while the two readings of the ink contradicted each other.
    if compared is not None:
        every = {q["Inference_ID"] for q in asked if q["Inference_ID"]}
        if not compared or set(compared) != every or differ or second_bad:
            return 2
    # THE WHOLE BATCH, which is what the name says. Checking only `excluded`
    # let a run pass strict mode with a panel refused beside the one that
    # finalized - values lost, and the flag that exists to notice that said
    # nothing.
    if args.require_all_values and (excluded or blocking):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
