# -*- coding: utf-8 -*-
"""Scenarios for record_block_reviews.py - the gate a blocked draft row goes back through.

    python3 tests/test_record_block_reviews.py

Every scenario is a way a block can be lifted wrongly: by nobody, for a row that
is not blocked, for a duplicate, for a figure number the plan already holds, for
a row with no number, twice, over an earlier review without saying so, or into
the file it was read from.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import csv
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_block_reviews as RB                                # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_blockreview_")
RUN, PLANS = os.path.join(ROOT, "run"), os.path.join(ROOT, "plans")
os.makedirs(RUN)
os.makedirs(PLANS)


def write(path, fields, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in fields))


# D001 FIG1 in the plan; D002 FIG6 blocked (the person disputed it); D003 FIG1 blocked and its number is in the plan;
# D004 a duplicate of D001; D005 blocked with no number; D006 blocked but answered on the sheet (so live); D007 FIG7 blocked.
write(os.path.join(RUN, RB.DRAFT), ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page"),
      [{"Draft_ID": "DOC_D00%d" % i, "Source_Document_ID": "DOC", "Figure_Number": n, "Page": str(i + 1)}
       for i, n in ((1, "FIG1"), (2, "FIG6"), (3, "Figure 1"), (4, "FIG1"), (5, ""), (6, "FIG8"), (7, "FIG7"))])
write(os.path.join(RUN, RB.BLOCKS), ("Draft_ID", "Count_Blocked", "Reason", "Duplicate_Of"),
      [{"Draft_ID": "DOC_D002", "Count_Blocked": "1", "Reason": "caption read by one reader only"},
       {"Draft_ID": "DOC_D003", "Count_Blocked": "1", "Reason": "a mention in the text"},
       {"Draft_ID": "DOC_D004", "Count_Blocked": "1", "Duplicate_Of": "DOC_D001"},
       {"Draft_ID": "DOC_D005", "Count_Blocked": "1", "Reason": "number not read"},
       {"Draft_ID": "DOC_D006", "Count_Blocked": "1", "Reason": "already answered"},
       {"Draft_ID": "DOC_D007", "Count_Blocked": "1", "Reason": "thin crop"}])
write(os.path.join(RUN, RB.COUNTS), ("Draft_ID", "Entry_Status"),
      [{"Draft_ID": "DOC_D002", "Entry_Status": "BLOCK_DISPUTED"}, {"Draft_ID": "DOC_D006", "Entry_Status": "ENTERED"}])
write(os.path.join(PLANS, RB.PLAN_FIGURES), ("Draft_ID", "Figure_Number", "Page"),
      [{"Draft_ID": "DOC_D001", "Figure_Number": "FIG1", "Page": "2"}])
# (D006 is left out of these plans on purpose: plans made before the sheet answer; the answer alone makes the row live.)
WHEN = "2026-09-30"
SEEN = {"Verified_By": "minyeop", "Seen_By_Person": "1"}
APPROVED = {"Verified_By": "minyeop", "Seen_By_Person": "0", "Observed_By": "Claude (PDF survey)", "Approval_Ref": "minyeop chat"}


def answer(did, choice="UNBLOCK", **who):
    row = {"Draft_ID": did, "Decision": choice, "Note": ""}
    row.update(SEEN)
    row.update(who)
    return row


def run(answers, out=None, **kw):
    out = out or os.path.join(ROOT, "b%d.csv" % len(os.listdir(ROOT)))
    w, r, p = RB.record(RUN, PLANS, answers, WHEN, out_path=out, log=lambda *_a: None, **kw)
    return w, r, out


def codes(refused):
    return [c for _n, ps in refused for c, _m in ps]


# --- what is taken -----------------------------------------------------------
_w, _r, _o = run([answer("DOC_D002")])
check("a blocked row a person says is a figure is unblocked", _r == [] and [(x["Draft_ID"], x["Decision"]) for x in _w] == [("DOC_D002", "UNBLOCK")], codes(_r))
check("the row carries the draft's document, number, page and the block it lifts",
      (_w[0]["Source_Document_ID"], _w[0]["Figure_Number"], _w[0]["Page"], _w[0]["Block_Reason"]) == ("DOC", "FIG6", "3", "caption read by one reader only"), _w[0])
check("Recorded_At is --when, not today", _w[0]["Recorded_At"] == WHEN and WHEN != __import__("datetime").date.today().isoformat())
check("the file's columns are the gate's", list(csv.reader(io.open(_o, encoding="utf-8")))[0] == list(RB.FIELDS))
check("KEEP is an answer", run([answer("DOC_D003", "KEEP")])[1] == [])
_w, _r, _o = run([answer("DOC_D007", **APPROVED)])
check("an approved observation is written as one", _r == [] and (_w[0]["Seen_By_Person"], _w[0]["Observed_By"]) == ("0", "Claude (PDF survey)"), codes(_r))
check("the gate's open answers are make_plan's", RB.ANSWERED_ON_AN_OPEN_ROW == __import__("make_plan").ANSWERED_ON_AN_OPEN_ROW)

# --- who says so ---------------------------------------------------------------
# REVERT: take an unblock nobody marked as seen.
check("not seen and not approved: refused", codes(run([answer("DOC_D002", Seen_By_Person="")])[1]) == ["NOT_SEEN_BY_PERSON"])
check("an approval without its reference is refused", codes(run([answer("DOC_D002", **dict(APPROVED, Approval_Ref=""))])[1]) == ["APPROVAL_INCOMPLETE"])
# REVERT: let a nameless answer through.
check("nobody named: refused", codes(run([answer("DOC_D002", Verified_By="")])[1]) == ["UNATTRIBUTED"])

# --- what cannot be unblocked ----------------------------------------------------
check("an unknown decision is refused", codes(run([answer("DOC_D002", "OPEN")])[1]) == ["BAD_DECISION"])
check("HOLD is not written", codes(run([answer("DOC_D002", "HOLD")])[1]) == ["HELD"])
# REVERT: take a review for a row the run does not have.
check("a row not in the draft is refused", codes(run([answer("DOC_D009")])[1]) == ["NOT_A_DRAFT"])
# REVERT: unblock a duplicate. One figure would be counted twice.
check("a duplicate row is refused", codes(run([answer("DOC_D004")])[1]) == ["DUPLICATE_ROW"])
# REVERT: drop the not-blocked check. A review would be written for rows the plan already reads.
check("a row in the plan is not blocked: refused", codes(run([answer("DOC_D001")])[1]) == ["NOT_BLOCKED"])
check("a blocked row answered on the sheet is live: refused", codes(run([answer("DOC_D006")])[1]) == ["NOT_BLOCKED"])
# REVERT: drop the number check. FIG1 would be in the plan twice, and the batch's coverage would count it twice.
check("a figure number the plan already holds is refused (spelled differently)", codes(run([answer("DOC_D003")])[1]) == ["FIGURE_NUMBER_TAKEN"])
check("a row with no figure number is refused", codes(run([answer("DOC_D005")])[1]) == ["NO_FIGURE_NUMBER"])
_w, _r, _o = run([answer("DOC_D002"), answer("DOC_D002", "KEEP")])
check("two answers for one row: both refused", codes(_r) == ["ANSWERED_TWICE", "ANSWERED_TWICE"] and _w == [], codes(_r))

# --- what is already there -----------------------------------------------------
_out = os.path.join(ROOT, "settled.csv")
run([answer("DOC_D002", "KEEP")], out=_out)
_w, _r, _o = run([answer("DOC_D002")], out=_out)
check("a row already reviewed is not overwritten", codes(_r) == ["ALREADY_REVIEWED"], codes(_r))
_w, _r, _o = run([answer("DOC_D002")], out=_out, replace=True)
check("--replace overwrites, without adding a row",
      [r["Decision"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["UNBLOCK"])
run([answer("DOC_D007")], out=_out)
check("a new row's review is added to the earlier ones",
      [r["Draft_ID"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["DOC_D002", "DOC_D007"])

# --- the files -------------------------------------------------------------------
try:
    RB.record(RUN, PLANS, [{"Draft_ID": "DOC_D002", "Decision": "UNBLOCK"}], WHEN, out_path=os.path.join(ROOT, "x.csv"), log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
check("an answers file without the required columns stops, naming them", "Verified_By" in _stopped and "Seen_By_Person" in _stopped, _stopped)
_same = os.path.join(ROOT, "same.csv")
write(_same, RB.FIELDS, [answer("DOC_D002")])
try:
    RB.record(RUN, PLANS, [answer("DOC_D002")], WHEN, out_path=_same, answers_path=_same, log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
# REVERT: let the answers file be the file written.
check("the answers file is never the file written", "같습니다" in _stopped, _stopped)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
