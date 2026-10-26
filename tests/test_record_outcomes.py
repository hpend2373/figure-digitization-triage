# -*- coding: utf-8 -*-
"""Scenarios for record_outcomes.py (a panel's outcome name, or "not a target") and
record_legends.py (which panels of a figure share a printed legend).

    python3 tests/test_record_outcomes.py

Each scenario is a way a name or a legend could reach the plan wrongly: unseen and unapproved, for a panel
the plan does not have, a guess written as a name, a name on a closed panel, two legends claiming one panel.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import csv
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_legends as RL                                      # noqa: E402
import record_outcomes as RO                                     # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_record_outcomes_")
RUN, PLANS = os.path.join(ROOT, "run"), os.path.join(ROOT, "plans")
os.makedirs(RUN)
os.makedirs(PLANS)
json.dump({"publication_id": "PUB", "figures": [
    {"source_figure_id": "PUB_D001", "panels": [
        {"panel_id": "PUB_D001_P1", "disposition": "MANUAL_DIGITIZE", "target_status": "TARGET"},
        {"panel_id": "PUB_D001_P2", "disposition": "NOT_DATA", "target_status": "NOT_DATA"},
        {"panel_id": "PUB_D001_P3", "disposition": "NO_SUMMARY_STATISTIC"}]},
    {"source_figure_id": "PUB_D002", "panels": [
        {"panel_id": "PUB_D002_P1", "disposition": "NON_TARGET_OUTCOME"},
        {"panel_id": "PUB_D002_P2", "disposition": "GEOMETRY_NOT_AUTHORED", "target_status": "TARGET"},
        {"panel_id": "PUB_D002_P3", "disposition": "NON_TARGET_OUTCOME", "target_status": "NON_TARGET",
         "reason": "outcome_decisions: minyeop — 이 리뷰의 결과가 아님"},
        {"panel_id": "PUB_D002_P4", "disposition": "NON_TARGET_OUTCOME", "target_status": "NON_TARGET",
         "reason": "figure_dispositions: NON_TARGET"}]}]},
    io.open(os.path.join(PLANS, "plan_PUB.json"), "w", encoding="utf-8"))
OUT = os.path.join(RUN, RO.DECISIONS)
SEEN = {"Verified_By": "minyeop", "Seen_By_Person": "1"}
APPROVED = {"Verified_By": "minyeop", "Seen_By_Person": "0", "Observed_By": "Claude (bundle)",
            "Approval_Ref": "bundle_answers.csv: minyeop 2026-10-16"}


def ans(pid, decision="LABEL", label="Heart rate", unit="bpm", **kw):
    row = dict(SEEN, Panel_ID=pid, Decision=decision, Outcome_Label=label if decision == "LABEL" else "",
               Unit=unit if decision == "LABEL" else "", Note="")
    row.update(kw)
    return row


def run(answers, **kw):
    if os.path.exists(OUT) and not kw.pop("keep", False):
        os.remove(OUT)
    return RO.record(RUN, PLANS, answers, "2026-10-16", log=lambda *_a: None, **kw)


def codes(refused):
    return sorted(c for _n, ps in refused for c, _m in ps)


# --- outcomes ------------------------------------------------------------------------
w, r, _p = run([ans("PUB_D001_P1"), ans("PUB_D001_P3", "NON_TARGET")])
rows = dict((x["Panel_ID"], x) for x in csv.DictReader(io.open(OUT, encoding="utf-8")))
check("a seen name and a seen 'not a target' are written, one row per panel", not r and sorted(rows) == ["PUB_D001_P1", "PUB_D001_P3"]
      and (rows["PUB_D001_P1"]["Outcome_Label"], rows["PUB_D001_P1"]["Unit"], rows["PUB_D001_P3"]["Decision"])
      == ("Heart rate", "bpm", "NON_TARGET"), r)
check("the row carries its figure, index, publication, who and when", (rows["PUB_D001_P1"]["Draft_ID"], rows["PUB_D001_P1"]["Panel_Index"],
      rows["PUB_D001_P1"]["Publication_ID"], rows["PUB_D001_P1"]["Verified_By"], rows["PUB_D001_P1"]["Recorded_At"])
      == ("PUB_D001", "1", "PUB", "minyeop", "2026-10-16"))
w, r, _p = run([ans("PUB_D001_P1", **APPROVED)])
check("an approved observation is written as one, with who saw it and where it was approved",
      not r and (w[0]["Seen_By_Person"], w[0]["Observed_By"]) == ("0", "Claude (bundle)") and w[0]["Approval_Ref"], r)
# REVERT: drop the seen/approved check. A name nobody looked at would be filed as the panel's outcome.
check("neither seen nor approved is refused", "NOT_SEEN_BY_PERSON" in codes(run([ans("PUB_D001_P1", Seen_By_Person="")])[1]))
check("nobody's name is refused", "UNATTRIBUTED" in codes(run([ans("PUB_D001_P1", Verified_By="")])[1]))
# REVERT: take any Panel_ID. An answer from another run's plan would name a panel this plan does not have.
check("a panel the plan does not have is refused", codes(run([ans("PUB_D001_P9")])[1]) == ["NOT_PLANNED"])
check("a figure id where a panel id belongs is refused", codes(run([ans("PUB_D001")])[1]) == ["NOT_PLANNED"])
# REVERT: name closed panels too. A NOT_DATA panel would carry an outcome the plan never asks it to read.
check("a name on a panel the plan closed is refused", codes(run([ans("PUB_D001_P2")])[1]) == ["PANEL_CLOSED"])
check("a name on a panel closed as not a target is refused", codes(run([ans("PUB_D002_P1")])[1]) == ["PANEL_CLOSED"])
check("... but a panel with no status of its own takes the one its disposition implies (NO_SUMMARY_STATISTIC is a target)",
      not run([ans("PUB_D001_P3")])[1])
# REVERT: accept any text. 'unknown' is worse than no name: the panel looks named and is not.
for guess in ("TBD", "unknown outcome", "HR (assumed)", "N/A"):
    check("a guess is not a name: %r" % guess, codes(run([ans("PUB_D001_P1", label=guess)])[1]) == ["LABEL_IS_A_PLACEHOLDER"],
          codes(run([ans("PUB_D001_P1", label=guess)])[1]))
check("an empty name is refused", codes(run([ans("PUB_D001_P1", label=" ")])[1]) == ["LABEL_WITHOUT_TEXT"])
check("'not a target' with a name is refused", codes(run([ans("PUB_D001_P1", "NON_TARGET", Outcome_Label="Heart rate")])[1])
      == ["NON_TARGET_WITH_LABEL"])
check("HOLD is not written", codes(run([ans("PUB_D001_P1", "HOLD")])[1]) == ["HELD"] and not list(csv.DictReader(io.open(OUT, encoding="utf-8"))))
check("an unknown decision is refused", codes(run([ans("PUB_D001_P1", "MAYBE")])[1]) == ["BAD_DECISION"])
check("two answers for one panel are both refused", codes(run([ans("PUB_D001_P1"), ans("PUB_D001_P1", "NON_TARGET")])[1])
      == ["ANSWERED_TWICE", "ANSWERED_TWICE"])
run([ans("PUB_D001_P1")])
# REVERT: overwrite silently. A second bundle would replace a person's earlier name without anyone choosing to.
check("a panel already written is not rewritten without --replace",
      codes(run([ans("PUB_D001_P1", label="Stroke volume")], keep=True)[1]) == ["ALREADY_DECIDED"])
w, r, _p = run([ans("PUB_D001_P1", label="Stroke volume")], keep=True, replace=True)
check("... and is with it, the other rows kept", not r and [x["Outcome_Label"] for x in csv.DictReader(io.open(OUT, encoding="utf-8"))]
      == ["Stroke volume"])
# --- reopening a panel this gate closed ---------------------------------------------------
def closed_first(*pids):
    run([ans(p, "NON_TARGET") for p in pids])


closed_first("PUB_D002_P3")
w, r, _p = run([ans("PUB_D002_P3", label="Systolic blood pressure", unit="mmHg")], keep=True, replace=True)
rows = dict((x["Panel_ID"], x) for x in csv.DictReader(io.open(OUT, encoding="utf-8")))
# REVERT: refuse every name on a closed panel. A panel this gate closed by mistake could never be named again.
check("a panel closed only by this gate's own NON_TARGET is reopened by --replace LABEL, the row replaced",
      not r and (rows["PUB_D002_P3"]["Decision"], rows["PUB_D002_P3"]["Outcome_Label"]) == ("LABEL", "Systolic blood pressure"),
      (r, rows.get("PUB_D002_P3")))
closed_first("PUB_D002_P3")
# REVERT: reopen without --replace. A second bundle would quietly undo a person's "not a target".
check("... not without --replace", codes(run([ans("PUB_D002_P3")], keep=True)[1]) == ["PANEL_CLOSED"],
      codes(run([ans("PUB_D002_P3")], keep=True)[1]))
# REVERT: drop the check that the closure came from this gate. A figure's disposition would be overruled from here.
run([ans("PUB_D002_P3", "NON_TARGET")])
check("a panel the figure's disposition closed is not reopened here, even with a NON_TARGET row of its own",
      codes(run([ans("PUB_D002_P4", "NON_TARGET")], keep=True)[1]) == [] and
      codes(run([ans("PUB_D002_P4")], keep=True, replace=True)[1]) == ["PANEL_CLOSED"])
# REVERT: reopen on the plan's word alone. A plan from before the record (or from another run) would reopen a panel
# nobody here closed.
check("a plan saying 'closed by outcome' with no NON_TARGET row in the record is not reopened",
      codes(run([ans("PUB_D002_P3")], replace=True)[1]) == ["PANEL_CLOSED"])
check("NOT_DATA is never reopened here", codes(run([ans("PUB_D001_P2")], replace=True)[1]) == ["PANEL_CLOSED"])
ap = os.path.join(ROOT, "answers.csv")
with io.open(OUT, encoding="utf-8") as fh:
    io.open(ap, "w", encoding="utf-8").write(fh.read())
try:
    RO.record(RUN, PLANS, [ans("PUB_D002_P2")], "2026-10-16", out_path=ap, answers_path=ap, log=lambda *_a: None)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("an answers file that is the record itself stops", "같습니다" in stopped, stopped)
try:
    RO.record(RUN, PLANS, [{"Panel_ID": "PUB_D001_P1"}], "2026-10-16", log=lambda *_a: None)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("an answers file without the gate's columns stops, naming them", "Decision" in stopped, stopped)

# --- legends -------------------------------------------------------------------------
LOUT = os.path.join(RUN, RL.DECISIONS)


def lans(did="PUB_D001", groups="p1|p3", **kw):
    row = dict(SEEN, Draft_ID=did, Legend_Groups=groups, Decision="LEGENDS", Note="")
    row.update(kw)
    return row


def lrun(answers, **kw):
    if os.path.exists(LOUT) and not kw.pop("keep", False):
        os.remove(LOUT)
    return RL.record(RUN, PLANS, answers, "2026-10-16", log=lambda *_a: None, **kw)


w, r, _p = lrun([lans(groups=" P3 | p1 ")])
check("a figure's legends are written, one group per legend, in a canonical order", not r and w[0]["Legend_Groups"] == "p1|p3"
      and w[0]["Publication_ID"] == "PUB", r)
# REVERT: let one panel sit in two legends. Its fills would mean two things and the domain check could not say which.
check("a panel in two legends is refused", "PANEL_IN_TWO_LEGENDS" in codes(lrun([lans(groups="p1,p3|p3")])[1]))
check("a panel the figure does not have is refused", codes(lrun([lans(groups="p1|p4")])[1]) == ["NOT_A_PANEL"])
check("one legend is the default and is not written", codes(lrun([lans(groups="p1,p3")])[1]) == ["ONE_LEGEND"])
check("a group that is not panel numbers is refused", codes(lrun([lans(groups="A|B")])[1]) == ["BAD_LEGEND_GROUPS"])
check("an empty legend is refused", codes(lrun([lans(groups="p1||p3")])[1]) == ["BAD_LEGEND_GROUPS"])
check("a figure the plan does not have is refused", codes(lrun([lans(did="PUB_D009")])[1]) == ["NOT_PLANNED"])
check("neither seen nor approved is refused", "NOT_SEEN_BY_PERSON" in codes(lrun([lans(Seen_By_Person="")])[1]))
check("HOLD is not written", codes(lrun([lans(Decision="HOLD")])[1]) == ["HELD"])
lrun([lans()])
check("a figure already written is not rewritten without --replace", codes(lrun([lans(groups="p3|p1")], keep=True)[1]) == ["ALREADY_DECIDED"])

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
