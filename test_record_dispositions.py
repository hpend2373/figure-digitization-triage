# -*- coding: utf-8 -*-
"""Scenarios for record_dispositions.py - the gate a figure's disposition goes through.

    python3 test_record_dispositions.py

Every scenario is a way a disposition can be written wrongly: by nobody, for a
figure the plan does not have, twice, with panels where none belong or without
them where they do, over an earlier one without saying so, or into the file it
was read from.
"""
import csv
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_dispositions as RD                                  # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_dispositions_")
RUN, PLANS = os.path.join(ROOT, "run"), os.path.join(ROOT, "plans")
os.makedirs(RUN)
os.makedirs(PLANS)


def write(path, fields, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in fields))


write(os.path.join(RUN, RD.DRAFT), ("Draft_ID", "Source_Document_ID"),
      [{"Draft_ID": "DOC_D001", "Source_Document_ID": "DOC"}, {"Draft_ID": "DOC_D002", "Source_Document_ID": "DOC"},
       {"Draft_ID": "DOC_D003", "Source_Document_ID": "DOC"}])
write(os.path.join(PLANS, RD.PLAN_FIGURES), ("Draft_ID", "Figure_Number", "Page"),
      [{"Draft_ID": "DOC_D001", "Figure_Number": "FIG1", "Page": "3"}, {"Draft_ID": "DOC_D002", "Figure_Number": "FIG2", "Page": "4"}])
#: the day the figure was seen - deliberately not today, so a gate that wrote today would be seen doing it
WHEN = "2026-09-30"
SEEN = {"Verified_By": "minyeop", "Seen_By_Person": "1"}
APPROVED = {"Verified_By": "minyeop", "Seen_By_Person": "0", "Observed_By": "Claude (PDF survey)",
            "Approval_Ref": "minyeop chat 2026-10-14"}


def answer(did, disp, panels="", **who):
    row = {"Draft_ID": did, "Disposition": disp, "Which_Panels": panels, "Note": ""}
    row.update(who or SEEN)
    return row


def run(answers, out=None, **kw):
    out = out or os.path.join(ROOT, "d%d.csv" % len(os.listdir(ROOT)))
    w, r, p = RD.record(RUN, PLANS, answers, WHEN, out_path=out, log=lambda *_a: None, **kw)
    return w, r, out


def codes(refused):
    return [c for _n, ps in refused for c, _m in ps]


# --- what is taken -----------------------------------------------------------
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET")])
check("a person's disposition is written", _r == [] and [(x["Draft_ID"], x["Disposition"]) for x in _w] == [("DOC_D001", "NON_TARGET")], codes(_r))
check("the row carries the plan's figure number and page and the draft's document",
      (_w[0]["Figure_Number"], _w[0]["Page"], _w[0]["Source_Document_ID"]) == ("FIG1", "3", "DOC"), _w[0])
check("Recorded_At is --when, not today", _w[0]["Recorded_At"] == WHEN and WHEN != __import__("datetime").date.today().isoformat())
check("the file's columns are the gate's", list(csv.reader(io.open(_o, encoding="utf-8")))[0] == list(RD.FIELDS))
for _d in ("DIGITIZE", "ASSOCIATION", "NOT_DATA", "RECROP", "REDRAW"):
    check("%s is a disposition" % _d, run([answer("DOC_D001", _d)])[1] == [])
_w, _r, _o = run([answer("DOC_D002", "PARTIAL", "b")])
check("PARTIAL is written with its panels", _r == [] and _w[0]["Which_Panels"] == "b", codes(_r))

# --- who says so ---------------------------------------------------------------
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET", Verified_By="minyeop", Seen_By_Person="")])
# REVERT: take a disposition nobody marked as seen. The one thing the gate
# carries - that someone looked - is gone.
check("not seen and not approved: refused", codes(_r) == ["NOT_SEEN_BY_PERSON"] and _w == [], codes(_r))
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET", **APPROVED)])
check("an approved observation is written as one: seen 0, who looked, where approved",
      _r == [] and (_w[0]["Seen_By_Person"], _w[0]["Observed_By"], _w[0]["Approval_Ref"]) == ("0", "Claude (PDF survey)", "minyeop chat 2026-10-14"),
      (codes(_r), _w[:1]))
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET", **dict(APPROVED, Approval_Ref=""))])
check("an approval without its reference is refused", codes(_r) == ["APPROVAL_INCOMPLETE"], codes(_r))
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET", Verified_By="", Seen_By_Person="1")])
# REVERT: let a nameless answer through.
check("nobody named: refused", codes(_r) == ["UNATTRIBUTED"], codes(_r))
_w, _r, _o = run([answer("DOC_D001", "NON_TARGET", Verified_By="minyeop", Seen_By_Person="1", Observed_By="x", Approval_Ref="y")])
check("a person's own look leaves the approval columns empty", (_w[0]["Observed_By"], _w[0]["Approval_Ref"]) == ("", ""), _w[:1])

# --- what is not a disposition -------------------------------------------------
check("an unknown disposition is refused", codes(run([answer("DOC_D001", "MAYBE")])[1]) == ["BAD_DISPOSITION"])
check("HOLD is not written", codes(run([answer("DOC_D001", "HOLD")])[1]) == ["HELD"])
# REVERT: drop the panel check. "Some panels" with no name tells the next
# person nothing, and panels on a whole-figure disposition mean nothing.
check("PARTIAL without panels is refused", codes(run([answer("DOC_D001", "PARTIAL")])[1]) == ["PARTIAL_WITHOUT_PANELS"])
check("panels on another disposition are refused", codes(run([answer("DOC_D001", "NOT_DATA", "a")])[1]) == ["PANELS_WITHOUT_PARTIAL"])
# REVERT: take an answer for a figure the plan does not have.
check("a figure not in the plan is refused", codes(run([answer("DOC_D003", "NOT_DATA")])[1]) == ["NOT_PLANNED"])
_w, _r, _o = run([answer("DOC_D001", "NOT_DATA"), answer("DOC_D001", "NON_TARGET")])
check("two dispositions for one figure: both refused", codes(_r) == ["ANSWERED_TWICE", "ANSWERED_TWICE"] and _w == [], codes(_r))

# --- what is already there -----------------------------------------------------
_out = os.path.join(ROOT, "settled.csv")
run([answer("DOC_D001", "NOT_DATA")], out=_out)
_w, _r, _o = run([answer("DOC_D001", "DIGITIZE")], out=_out)
check("a figure already disposed is not overwritten", codes(_r) == ["ALREADY_DECIDED"], codes(_r))
check("  and the earlier row stays", [r["Disposition"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["NOT_DATA"])
_w, _r, _o = run([answer("DOC_D001", "DIGITIZE")], out=_out, replace=True)
check("--replace overwrites, without adding a row",
      [r["Disposition"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["DIGITIZE"])
run([answer("DOC_D002", "RECROP")], out=_out)
check("a new figure's row is added to the earlier ones",
      [r["Draft_ID"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["DOC_D001", "DOC_D002"])

# --- the files -----------------------------------------------------------------
try:
    RD.record(RUN, PLANS, [{"Draft_ID": "DOC_D001", "Disposition": "NOT_DATA"}], WHEN, out_path=os.path.join(ROOT, "x.csv"),
              log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
check("an answers file without the required columns stops, naming them", "Verified_By" in _stopped and "Seen_By_Person" in _stopped, _stopped)
_same = os.path.join(ROOT, "same.csv")
write(_same, ("Draft_ID", "Disposition", "Verified_By", "Seen_By_Person"), [answer("DOC_D001", "NOT_DATA")])
try:
    RD.record(RUN, PLANS, [answer("DOC_D001", "NOT_DATA")], WHEN, out_path=_same, answers_path=_same, log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
# REVERT: let the answers file be the file written. The gate reads what it
# wrote as answers and overwrites the original in its own shape.
check("the answers file is never the file written", "같습니다" in _stopped, _stopped)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
