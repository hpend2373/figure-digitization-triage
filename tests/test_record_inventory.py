# -*- coding: utf-8 -*-
"""Scenarios for record_inventory.py - the gate the inventory's two numbers go through.

    python3 tests/test_record_inventory.py

Every scenario is a way an inventory number can be written wrongly: by nobody,
with a method that does not say who looked, for a document or figure the run
does not have, as a count that is not a count, outside the pages a person set,
on a day after it was written, twice, over an earlier one without saying so, or
into the file it was read from.
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
import record_inventory as RV                                    # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_inventory_")
RUN, PLANS = os.path.join(ROOT, "run"), os.path.join(ROOT, "plans")
os.makedirs(RUN)
os.makedirs(PLANS)


def write(path, fields, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in fields))


write(os.path.join(RUN, RV.DRAFT), ("Draft_ID", "Source_Document_ID"),
      [{"Draft_ID": "DOC_D001", "Source_Document_ID": "DOC"}, {"Draft_ID": "DOC_D002", "Source_Document_ID": "DOC"},
       {"Draft_ID": "DOC_D003", "Source_Document_ID": "DOC"}])
write(os.path.join(RUN, RV.DOCUMENT_STATUS), ("Source_Document_ID", "Page_Count"),
      [{"Source_Document_ID": "DOC", "Page_Count": "12"}, {"Source_Document_ID": "BOOK", "Page_Count": "400"}])
write(os.path.join(RUN, RV.DOCUMENT_SCOPE), ("Source_Document_ID", "Page_From", "Page_To"),
      [{"Source_Document_ID": "BOOK", "Page_From": "313", "Page_To": "316"}])
write(os.path.join(PLANS, RV.PLAN_FIGURES), ("Draft_ID", "Figure_Number", "Page"),
      [{"Draft_ID": "DOC_D001", "Figure_Number": "FIG1", "Page": "3"}, {"Draft_ID": "DOC_D002", "Figure_Number": "FIG2", "Page": "4"}])
#: the day of recording - deliberately not today, so a gate that wrote today would be seen doing it
WHEN = "2026-09-30"
SEEN = {"Verified_By": "minyeop", "Seen_By_Person": "1"}
APPROVED = {"Verified_By": "minyeop", "Seen_By_Person": "0", "Observed_By": "Claude (PDF survey)",
            "Approval_Ref": "minyeop chat 2026-10-15"}


def doc(target="DOC", count="3", pages="1-12", seen_on="2026-09-29", **who):
    row = {"Level": "DOCUMENT", "Target_ID": target, "Count": count, "Article_Page_Range": pages,
           "Count_Basis": "", "Inspection_Date": seen_on, "Note": ""}
    row.update(SEEN)
    row.update(who)
    return row


def fig(target="DOC_D001", count="2", basis="AXIS_REGIONS", seen_on="2026-09-29", **who):
    row = {"Level": "FIGURE", "Target_ID": target, "Count": count, "Count_Basis": basis, "Article_Page_Range": "",
           "Inspection_Date": seen_on, "Note": ""}
    row.update(SEEN)
    row.update(who)
    return row


def run(answers, out=None, **kw):
    out = out or os.path.join(ROOT, "i%d.csv" % len(os.listdir(ROOT)))
    w, r, p = RV.record(RUN, PLANS, answers, WHEN, out_path=out, log=lambda *_a: None, **kw)
    return w, r, out


def codes(refused):
    return [c for _n, ps in refused for c, _m in ps]


# --- what is taken -----------------------------------------------------------
_w, _r, _o = run([doc(), fig()])
check("a person's document count and figure count are written", _r == [] and [(x["Level"], x["Target_ID"], x["Count"]) for x in _w]
      == [("DOCUMENT", "DOC", "3"), ("FIGURE", "DOC_D001", "2")], codes(_r))
check("the document row carries its page range, the figure row its plan number, page and document",
      _w[0]["Article_Page_Range"] == "1-12" and (_w[1]["Figure_Number"], _w[1]["Page"], _w[1]["Source_Document_ID"]) == ("FIG1", "3", "DOC"), _w)
check("Recorded_At is --when, not today", _w[0]["Recorded_At"] == WHEN and WHEN != __import__("datetime").date.today().isoformat())
check("Inspection_Date is the day it was seen, as given", _w[0]["Inspection_Date"] == "2026-09-29")
check("the file's columns are the gate's", list(csv.reader(io.open(_o, encoding="utf-8")))[0] == list(RV.FIELDS))
check("a count spelled with spaces is written as the number", run([fig(count=" 3 ")])[0][0]["Count"] == "3")
check("a page range is written as first-last", run([doc(pages=" 2 - 11 ")])[0][0]["Article_Page_Range"] == "2-11")
check("a document with no figures is a count", run([doc(count="0")])[1] == [])
_w, _r, _o = run([fig(count="1", basis="WHOLE")])
check("a figure with no axis region is one WHOLE panel", _r == [] and (_w[0]["Count"], _w[0]["Count_Basis"]) == ("1", "WHOLE"), codes(_r))

# --- who looked, and what that makes the method -----------------------------------
_w, _r, _o = run([fig(**APPROVED)])
check("an approved observation is written as one: seen 0, who looked, where approved",
      _r == [] and (_w[0]["Seen_By_Person"], _w[0]["Observed_By"], _w[0]["Approval_Ref"]) == ("0", "Claude (PDF survey)", "minyeop chat 2026-10-15"),
      (codes(_r), _w[:1]))
# REVERT: let the method follow the answer instead of who looked. A machine's
# count then goes into the batch as a person's visual count.
check("  and its method is MACHINE_PLUS_HUMAN", _w[0]["Count_Method"] == "MACHINE_PLUS_HUMAN", _w[:1])
_w, _r, _o = run([fig(Count_Method="HUMAN_VISUAL", **APPROVED)])
check("  even when the answer says HUMAN_VISUAL", _w[0]["Count_Method"] == "MACHINE_PLUS_HUMAN", _w[:1])
check("a person's own count is HUMAN_VISUAL", run([fig()])[0][0]["Count_Method"] == "HUMAN_VISUAL")
_w, _r, _o = run([fig(Verified_By="minyeop", Seen_By_Person="")])
# REVERT: take a count nobody marked as seen.
check("not seen and not approved: refused", codes(_r) == ["NOT_SEEN_BY_PERSON"] and _w == [], codes(_r))
check("an approval without its reference is refused", codes(run([fig(**dict(APPROVED, Approval_Ref=""))])[1]) == ["APPROVAL_INCOMPLETE"])
# REVERT: let a nameless answer through.
check("nobody named: refused", codes(run([fig(Verified_By="", Seen_By_Person="1")])[1]) == ["UNATTRIBUTED"])

# --- when it was seen --------------------------------------------------------------
# REVERT: drop the date check. A count dated after its own recording is a count
# nobody had made when it was written down.
check("seen after it was recorded: refused", codes(run([fig(seen_on="2026-10-01")])[1]) == ["INSPECTED_AFTER_RECORDED"])
check("seen on the day it was recorded is fine", run([fig(seen_on=WHEN)])[1] == [])
check("a date that is not a date is refused", codes(run([fig(seen_on="soon")])[1]) == ["BAD_INSPECTION_DATE"])

# --- what is not a count ------------------------------------------------------------
check("an unknown level is refused", codes(run([dict(fig(), Level="PANEL")])[1]) == ["BAD_LEVEL"])
# REVERT: take a panel count below one. The batch refuses it, and a figure with
# no axis region is one WHOLE panel, not zero.
check("a figure with zero panels is refused (WHOLE is one)", codes(run([fig(count="0")])[1]) == ["BAD_COUNT"])
check("a figure count that is not a number is refused", codes(run([fig(count="2-3")])[1]) == ["BAD_COUNT"])
check("a document count that is not a number is refused", codes(run([doc(count="?")])[1]) == ["BAD_COUNT"])
check("a negative document count is refused", codes(run([doc(count="-1")])[1]) == ["BAD_COUNT"])
check("a figure count without a basis is refused", codes(run([fig(basis="")])[1]) == ["BAD_COUNT_BASIS"])
# REVERT: let WHOLE carry any number. WHOLE says the figure is one panel.
check("WHOLE with more than one panel is refused", codes(run([fig(count="3", basis="WHOLE")])[1]) == ["WHOLE_IS_ONE"])
check("a basis on a document count is refused", codes(run([doc(Count_Basis="WHOLE")])[1]) == ["BASIS_ON_DOCUMENT"])
check("a page range on a figure count is refused", codes(run([dict(fig(), Article_Page_Range="1-3")])[1]) == ["RANGE_ON_FIGURE"])

# --- pages ----------------------------------------------------------------------------
check("a document count without a page range is refused", codes(run([doc(pages="")])[1]) == ["BAD_PAGE_RANGE"])
check("a page range that is not first-last is refused", codes(run([doc(pages="1,3")])[1]) == ["BAD_PAGE_RANGE"])
# REVERT: drop the bounds. A range past the PDF's last page counts figures in
# pages that do not exist.
check("a range past the PDF's last page is refused", codes(run([doc(pages="1-13")])[1]) == ["BAD_PAGE_RANGE"])
check("a range that runs backwards is refused", codes(run([doc(pages="5-2")])[1]) == ["BAD_PAGE_RANGE"])
# REVERT: drop the scope check. The count would be of other pages than the ones
# a person decided are this document.
check("a range that is not the person's scope is refused",
      codes(run([doc(target="BOOK", count="2", pages="1-400")])[1]) == ["RANGE_DISAGREES_WITH_SCOPE"])
check("the person's scope is taken", run([doc(target="BOOK", count="2", pages="313-316")])[1] == [])

# --- what the run does not have ----------------------------------------------------------
# REVERT: take a count for a document the run does not have.
check("a document not in the run is refused", codes(run([doc(target="OTHER")])[1]) == ["NOT_A_DOCUMENT"])
# REVERT: take a count for a figure the plan does not have.
check("a figure not in the plan is refused", codes(run([fig(target="DOC_D003")])[1]) == ["NOT_PLANNED"])
_w, _r, _o = run([fig(), fig(count="3")])
check("two counts for one figure: both refused", codes(_r) == ["ANSWERED_TWICE", "ANSWERED_TWICE"] and _w == [], codes(_r))
check("a document and a figure with the same ID are two counts",
      run([doc(target="DOC"), dict(fig(), Target_ID="DOC")])[1][0][0] == "FIGURE DOC")

# --- what is already there -----------------------------------------------------------------
_out = os.path.join(ROOT, "settled.csv")
run([fig()], out=_out)
_w, _r, _o = run([fig(count="3")], out=_out)
check("a count already recorded is not overwritten", codes(_r) == ["ALREADY_RECORDED"], codes(_r))
check("  and the earlier row stays", [r["Count"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["2"])
_w, _r, _o = run([fig(count="3")], out=_out, replace=True)
check("--replace overwrites, without adding a row",
      [r["Count"] for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == ["3"])
run([doc()], out=_out)
check("a new count's row is added to the earlier ones",
      [(r["Level"], r["Target_ID"]) for r in csv.DictReader(io.open(_out, encoding="utf-8"))] == [("DOCUMENT", "DOC"), ("FIGURE", "DOC_D001")])

# --- the files -----------------------------------------------------------------------------
try:
    RV.record(RUN, PLANS, [{"Level": "FIGURE", "Target_ID": "DOC_D001", "Count": "2"}], WHEN, out_path=os.path.join(ROOT, "x.csv"),
              log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
check("an answers file without the required columns stops, naming them", "Verified_By" in _stopped and "Inspection_Date" in _stopped, _stopped)
_same = os.path.join(ROOT, "same.csv")
write(_same, RV.FIELDS, [fig()])
try:
    RV.record(RUN, PLANS, [fig()], WHEN, out_path=_same, answers_path=_same, log=lambda *_a: None)
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
