# -*- coding: utf-8 -*-
"""Scenarios for census_copy.py - routed answers recorded through the gates on a COPY of the run, and the census
before and after.

    python3 test_census_copy.py

The census itself (make_plan -> compile_plan -> run_batch over a whole run) needs a corpus this repository does not
carry, so here it is a stub that reads what the copy holds; the copy, the gates on the copy, the guard on the run and
the comparison are the real code. The real census was run on run2 (2026-10-16) - see SKILL.md.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import census_copy as CC                                         # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_census_copy_")


def write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields)); w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in fields))


def rd(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


# --- the copy --------------------------------------------------------------------
SRC, DST = os.path.join(ROOT, "src"), os.path.join(ROOT, "dst")
write(os.path.join(SRC, "seg", "identity600", "identity_decisions.csv"), ("Proposal_ID",), [{"Proposal_ID": "P"}])
write(os.path.join(SRC, "seg", "identity600", "identity_proposal.csv"), ("Proposal_ID",), [{"Proposal_ID": "P"}])
write(os.path.join(SRC, "figure_intake_draft.csv"), ("Draft_ID",), [{"Draft_ID": "D1"}])
os.makedirs(os.path.join(SRC, "crops"))
CC.link_tree(SRC, DST, ["seg/identity600/identity_decisions.csv", "figure_dispositions.csv"])
real = lambda p: os.path.isfile(os.path.join(DST, p)) and not os.path.islink(os.path.join(DST, p))
check("the files a gate writes are real copies", real("seg/identity600/identity_decisions.csv"))
check("their folders are real folders, everything else a link to the run",
      not os.path.islink(os.path.join(DST, "seg")) and not os.path.islink(os.path.join(DST, "seg", "identity600"))
      and os.path.islink(os.path.join(DST, "seg", "identity600", "identity_proposal.csv"))
      and os.path.islink(os.path.join(DST, "figure_intake_draft.csv")) and os.path.islink(os.path.join(DST, "crops")))
check("a record the run does not have yet is not created, only its place", not os.path.exists(os.path.join(DST, "figure_dispositions.csv")))
io.open(os.path.join(DST, "seg", "identity600", "identity_decisions.csv"), "w").write("changed\n")
# REVERT: link the written files too. The gates would write through the link into the run.
check("writing the copy's record leaves the run's record as it was",
      rd(os.path.join(SRC, "seg", "identity600", "identity_decisions.csv")) == [{"Proposal_ID": "P"}])
try:
    CC.link_tree(SRC, DST, [])
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("a copy over an existing folder is refused", "이미 있습니다" in stopped, stopped)

# --- the comparison -----------------------------------------------------------------
B = {"P1": {"plan_problems": {}, "manifest_problems": {"MISSING_SERIES_DISCRIMINANT": 3, "CALIBRATION_OUTSIDE_PANEL": 1}, "run_exit": 2},
     "P2": {"plan_problems": {}, "manifest_problems": {"SOURCE_PANEL_UNRESOLVED": 2}, "run_exit": 2}}
A = {"P1": {"plan_problems": {}, "manifest_problems": {}, "run_exit": 0},
     "P2": {"plan_problems": {}, "manifest_problems": {"SOURCE_PANEL_UNRESOLVED": 5}, "run_exit": 2},
     "P3": {"plan_problems": {"PLAN_X": 1}}}
cmp = CC.compare(B, A, [{"Panel_ID": "X1", "Panel_Disposition": "AUTO_DIGITIZE"}, {"Panel_ID": "X2", "Panel_Disposition": "AUTO_DIGITIZE"}],
                 [{"Panel_ID": "X1", "Panel_Disposition": "MANUAL_DIGITIZE"}, {"Panel_ID": "X3", "Panel_Disposition": "AUTO_DIGITIZE"}])
check("the totals say what went down and what went up", cmp["total"]["manifest_problems"] == {
    "CALIBRATION_OUTSIDE_PANEL": [1, 0], "MISSING_SERIES_DISCRIMINANT": [3, 0], "SOURCE_PANEL_UNRESOLVED": [2, 5]}
      and cmp["total"]["manifest_problems_sum"] == [6, 5])
# REVERT: report only the sum. 6 -> 5 reads as progress while one code grew from 2 to 5.
check("a code that grew is named even when the sum fell", cmp["grew"]["manifest_problems"] == {"SOURCE_PANEL_UNRESOLVED": [2, 5]}
      and cmp["grew"]["plan_problems"] == {"PLAN_X": [0, 1]})
check("each publication's change, its exit code, and one that appeared", cmp["by_pub"]["P1"]["run_exit"] == [2, 0]
      and cmp["by_pub"]["P3"]["present"] == [False, True])
check("panels whose disposition changed, and panels that came or went", cmp["panel_changes"] == {
    "X1": {"Panel_Disposition": ["AUTO_DIGITIZE", "MANUAL_DIGITIZE"]}, "X2": {"present": [True, False]}, "X3": {"present": [False, True]}})

# --- the whole step, with a stub census ------------------------------------------------
RUN = os.path.join(ROOT, "run")
write(os.path.join(RUN, "figure_intake_draft.csv"), ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page"),
      [{"Draft_ID": "DOC_D001", "Source_Document_ID": "DOC", "Figure_Number": "FIG1", "Page": "3"},
       {"Draft_ID": "DOC_D002", "Source_Document_ID": "DOC", "Figure_Number": "FIG2", "Page": "4"}])
write(os.path.join(RUN, "seg", "identity600", "identity_decisions.csv"), ("Proposal_ID",), [{"Proposal_ID": "P"}])


def stub(run, out):
    """a census that reads what the run holds: a closed figure has no unresolved panels"""
    os.makedirs(os.path.join(out, "plans"), exist_ok=True)
    write(os.path.join(out, "plans", "plan_figures.csv"), ("Draft_ID", "Figure_Number", "Page"),
          [{"Draft_ID": "DOC_D001", "Figure_Number": "FIG1", "Page": "3"}, {"Draft_ID": "DOC_D002", "Figure_Number": "FIG2", "Page": "4"}])
    json.dump({"publication_id": "DOC", "figures": [{"source_figure_id": "DOC_D002", "panels": [
        {"panel_id": "DOC_D002_P1", "disposition": "MANUAL_DIGITIZE", "target_status": "TARGET"},
        {"panel_id": "DOC_D002_P2", "disposition": "MANUAL_DIGITIZE", "target_status": "TARGET"}]}]},
        io.open(os.path.join(out, "plans", "plan_DOC.json"), "w", encoding="utf-8"))
    p = os.path.join(run, "figure_dispositions.csv")
    closed = set(r["Draft_ID"] for r in rd(p)) if os.path.exists(p) else set()
    return ({"DOC": {"plan_problems": {}, "manifest_problems": {"SOURCE_PANEL_UNRESOLVED": 2 - len(closed)}}},
            [{"Panel_ID": "DOC_D001_P1", "Panel_Disposition": "NON_TARGET_OUTCOME" if "DOC_D001" in closed else "UNRESOLVED"}])


ROUTED = os.path.join(ROOT, "routed")
APPROVED = {"Verified_By": "minyeop", "Seen_By_Person": "0", "Observed_By": "Claude (survey)", "Approval_Ref": "bundle_answers.csv: minyeop 2026-10-16"}
write(os.path.join(ROUTED, "figure_disposition_answers.csv"), ("Draft_ID", "Disposition", "Which_Panels", "Verified_By", "Seen_By_Person",
                                                              "Observed_By", "Approval_Ref", "Note"),
      [dict(APPROVED, Draft_ID="DOC_D001", Disposition="NON_TARGET", Note="bundle A01: NON_TARGET")])
OUT = os.path.join(ROOT, "out")
rc = CC.main(["--run", RUN, "--routed", ROUTED, "--when", "2026-10-16", "--out", OUT], census_fn=stub)
rec = json.load(io.open(os.path.join(OUT, "recorded.json"), encoding="utf-8"))
cmp = json.load(io.open(os.path.join(OUT, "compare.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT, "compare.json")) else {}
check("the routed answer is recorded on the copy by the gate itself", rc == 0 and rec == {"dispositions": [1, []]}, rec)
check("the copy's record is the gate's, with the approval in it", rd(os.path.join(OUT, "run_after", "figure_dispositions.csv"))[0]["Observed_By"]
      == "Claude (survey)")
# REVERT: record into the run. The answers the person has not yet seen applied would already be the record.
check("the run itself has no record written", not os.path.exists(os.path.join(RUN, "figure_dispositions.csv")))
check("the comparison is of the run before and the copy after", cmp.get("total", {}).get("manifest_problems") == {"SOURCE_PANEL_UNRESOLVED": [2, 1]}
      and cmp.get("panel_changes") == {"DOC_D001_P1": {"Panel_Disposition": ["UNRESOLVED", "NON_TARGET_OUTCOME"]}}, cmp.get("total"))
check("both censuses are kept", all(os.path.exists(os.path.join(OUT, n)) for n in ("census_before.json", "census_after.json")))

OUT2 = os.path.join(ROOT, "out2")
write(os.path.join(ROUTED, "figure_disposition_answers.csv"), ("Draft_ID", "Disposition", "Which_Panels", "Verified_By", "Seen_By_Person",
                                                              "Observed_By", "Approval_Ref", "Note"),
      [dict(APPROVED, Draft_ID="DOC_D009", Disposition="NON_TARGET")])
rc = CC.main(["--run", RUN, "--routed", ROUTED, "--when", "2026-10-16", "--out", OUT2], census_fn=stub)
# REVERT: run the census after a gate refused. The comparison would describe answers that will not be recorded.
check("a gate refusal on the copy stops before the 'after' census", rc == 1 and not os.path.exists(os.path.join(OUT2, "compare.json"))
      and json.load(io.open(os.path.join(OUT2, "recorded.json"), encoding="utf-8"))["dispositions"][1][0][1][0][0] == "NOT_PLANNED")

real_record = CC.record_on_copy


def leaky(after, routed, when, plans, gate_dirs, pdf_root=None, log=print):
    io.open(os.path.join(RUN, "seg", "identity600", "identity_decisions.csv"), "a").write("leak\n")
    return real_record(after, routed, when, plans, gate_dirs, pdf_root, log)


write(os.path.join(ROUTED, "figure_disposition_answers.csv"), ("Draft_ID", "Disposition", "Which_Panels", "Verified_By", "Seen_By_Person",
                                                              "Observed_By", "Approval_Ref", "Note"),
      [dict(APPROVED, Draft_ID="DOC_D002", Disposition="NON_TARGET")])
write(os.path.join(ROUTED, "identity_answers.csv"), ("Proposal_ID", "Human_Verification_Status", "Verified_By", "Seen_By_Person"), [])
CC.record_on_copy = leaky
try:
    CC.main(["--run", RUN, "--routed", ROUTED, "--when", "2026-10-16", "--out", os.path.join(ROOT, "out3"),
             "--identity-dir", "seg/identity600"], census_fn=stub)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
finally:
    CC.record_on_copy = real_record
# REVERT: drop the guard. A gate that writes beside its record, through a link, changes the run and nothing says so.
check("a write that reached the run through a link stops the step, naming the file", stopped.startswith("RUN_CHANGED")
      and "identity_decisions.csv" in stopped, stopped)
try:
    CC.main(["--run", RUN, "--routed", ROUTED, "--when", "2026-10-16", "--out", os.path.join(RUN, "inside")], census_fn=stub)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("an output folder inside the run is refused", "런 안에" in stopped, stopped)
EMPTY = os.path.join(ROOT, "empty_routed"); os.makedirs(EMPTY)
try:
    CC.main(["--run", RUN, "--routed", EMPTY, "--when", "2026-10-16", "--out", os.path.join(ROOT, "out4")], census_fn=stub)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("a routed folder with no gate answers is refused", "관문 답 파일이 없습니다" in stopped, stopped)
write(os.path.join(EMPTY, "errorbar_answers.csv"), ("Source_Document_ID", "Dispersion_Type", "Errorbar_Definition_Source", "Verified_In_Source"),
      [{"Source_Document_ID": "DOC", "Dispersion_Type": "SEM", "Errorbar_Definition_Source": "mean ± SEM"}])
# A name and a legend split, recorded on the copy by their own gates.
NAMED = os.path.join(ROOT, "routed_named")
write(os.path.join(NAMED, "outcome_answers.csv"), ("Panel_ID", "Decision", "Outcome_Label", "Unit") + tuple(APPROVED),
      [dict(APPROVED, Panel_ID="DOC_D002_P1", Decision="LABEL", Outcome_Label="Heart rate", Unit="bpm")])
write(os.path.join(NAMED, "legend_answers.csv"), ("Draft_ID", "Legend_Groups", "Decision") + tuple(APPROVED),
      [dict(APPROVED, Draft_ID="DOC_D002", Legend_Groups="p1|p2", Decision="LEGENDS")])
OUTN = os.path.join(ROOT, "out_named")
rc = CC.main(["--run", RUN, "--routed", NAMED, "--when", "2026-10-16", "--out", OUTN], census_fn=stub)
recn = json.load(io.open(os.path.join(OUTN, "recorded.json"), encoding="utf-8"))
# REVERT: leave the two new gates out of the copy. The names would be routed and never recorded anywhere.
check("a name and a legend split are recorded on the copy by their own gates, and not in the run",
      rc == 0 and recn == {"outcomes": [1, []], "legends": [1, []]}
      and rd(os.path.join(OUTN, "run_after", "outcome_decisions.csv"))[0]["Outcome_Label"] == "Heart rate"
      and rd(os.path.join(OUTN, "run_after", "legend_decisions.csv"))[0]["Legend_Groups"] == "p1|p2"
      and not os.path.exists(os.path.join(RUN, "outcome_decisions.csv")), recn)

import record_errorbar as REB                                    # noqa: E402
_seen, _real_reb = {}, REB.record


def _spy(*a, **k):
    _seen.update(k)
    return [], [], ""


REB.record = _spy
try:
    CC.record_on_copy(os.path.join(ROOT, "spy_after"), EMPTY, "2026-10-17", os.path.join(ROOT, "spy_plans"), {}, pdf_root=ROOT,
                      log=lambda *_a: None)
finally:
    REB.record = _real_reb
# REVERT: record error definitions on the copy without the census's plans. The figures the plan is waiting for (opened after the
# old pending list, or misread by the caption rule) are refused on the copy, and the census never shows what they change.
check("the error-bar gate on the copy reads the plans the census made", _seen.get("plans") == os.path.join(ROOT, "spy_plans"), _seen)

CALLS = []


def counted(run, out):
    CALLS.append(run)
    return stub(run, out)


def stops(argv):
    try:
        CC.main(argv, census_fn=counted)
        return ""
    except SystemExit as exc:
        return str(exc)


stopped = stops(["--run", RUN, "--routed", EMPTY, "--when", "2026-10-16", "--out", os.path.join(ROOT, "out5")])
# REVERT: record error-bar answers without the PDFs. Their quotes are re-found in the source or they are not answers.
check("error-bar answers without --pdf-root stop before any census", "--pdf-root" in stopped and not CALLS, stopped)
stopped = stops(["--run", RUN, "--routed", EMPTY, "--when", "2026-10-16", "--out", os.path.join(ROOT, "out6"), "--pdf-root", ROOT])
# REVERT: find out at the gate. The census before is minutes, and the gate then falls over on a file the run never had.
check("error-bar answers on a run without the gate's pending list stop before any census, naming it",
      "errorbar_unstated.csv" in stopped and not CALLS, stopped)

import record_dispositions as RD                                 # noqa: E402
real_rd = RD.record


def falls(*_a, **_k):
    raise OSError("disk gone")


write(os.path.join(ROUTED, "figure_disposition_answers.csv"), ("Draft_ID", "Disposition", "Which_Panels", "Verified_By", "Seen_By_Person",
                                                              "Observed_By", "Approval_Ref", "Note"),
      [dict(APPROVED, Draft_ID="DOC_D001", Disposition="NON_TARGET")])
os.remove(os.path.join(ROUTED, "identity_answers.csv"))
OUT7 = os.path.join(ROOT, "out7")
RD.record = falls
try:
    rc = CC.main(["--run", RUN, "--routed", ROUTED, "--when", "2026-10-16", "--out", OUT7], census_fn=stub)
finally:
    RD.record = real_rd
got = json.load(io.open(os.path.join(OUT7, "recorded.json"), encoding="utf-8")) if os.path.exists(os.path.join(OUT7, "recorded.json")) else {}
# REVERT: let a gate's exception through. Nothing says which gate fell or what the copy already holds.
check("a gate that falls over is a refusal: recorded, named, and no 'after' census",
      rc == 1 and got.get("dispositions", [None, [[None, [[""]]]]])[1][0][1][0][0] == "GATE_FAILED"
      and not os.path.exists(os.path.join(OUT7, "compare.json")), got)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
