# -*- coding: utf-8 -*-
"""Scenarios for bundle_route.py - a bundle's answers moved into the answers each gate takes.

    python3 test_bundle_route.py

Every scenario is a way an answer could reach a gate wrongly: answered on a different page, changed without being
looked at, approved under somebody else's name, two answers on one card that disagree, a card or series that is
not there - or a whole bundle half-routed.
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
import bundle_page as BP                                         # noqa: E402
import bundle_route as BR                                        # noqa: E402
import record_dispositions as RD                                 # noqa: E402
import record_errorbar as RE                                     # noqa: E402
import record_geometry as RG                                     # noqa: E402
import record_identity as RI                                     # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_bundle_route_")
OBS = "Claude (survey)"
DISP = lambda d, v, w="": {"gate": "dispositions", "row": {"Draft_ID": d, "Disposition": v, "Which_Panels": w}}
CARD = lambda pid, **kw: dict({"gate": "identity", "proposal_id": pid}, **kw)


def it(iid, prop, options, **kw):
    return dict({"id": iid, "target": kw.pop("target", iid), "now": "", "proposal": prop, "why": "because",
                 "observed_by": OBS, "options": options + [["HOLD", "hold"]]}, **kw)


SPEC = {"schema": BP.SCHEMA, "answers_file": "bundle_answers.csv", "sections": [{"id": "X", "items": [
    it("A01", "PARTIAL", [["PARTIAL", "e,f,g", DISP("DOC_E007", "PARTIAL", "e,f,g")], ["NON_TARGET", "close", DISP("DOC_E007", "NON_TARGET")]]),
    it("A02", "SEM", [["SEM", "SEM", {"gate": "errorbar", "row": {"Source_Document_ID": "DOC", "Draft_ID": "DOC_E007",
                                                                 "Dispersion_Type": "SEM", "Errorbar_Definition_Source": "mean ± SEM",
                                                                 "Found_On_Page": "21"}}]]),
    it("F01", "OPEN", [["OPEN", "open", CARD("P__p1", series=[{"name": "ALL", "set": {"bar_fill": "OPEN"}}])],
                       ["MANUAL", "manual", CARD("P__p1", set={"Read_Route": "MANUAL"})]]),
    it("F02", "SOLID", [["SOLID", "solid", CARD("P__p1", series=[{"name": "all", "set": {"bar_fill": "SOLID"}}])]]),
    it("E02", "CLIP", [["CLIP", "clip", CARD("P__p1", set={"Panel_X1": "2156"})]]),
    it("E03", "CLIP", [["CLIP", "clip", CARD("P__p1", set={"Panel_X1": "2150"})]]),
    it("L01", "MANUAL", [["MANUAL", "both panels", [CARD("P__p1", set={"Read_Route": "MANUAL"}), CARD("P__p2", set={"Read_Route": "MANUAL"})]]]),
    it("K02", "BOX", [["BOX", "box", [{"gate": "geometry", "proposal_id": "P__p1", "set": {"Panel_X1": "2150"}},
                                      CARD("P__p1", set={"Panel_X1": "2150"}), {"gate": None, "needs": "a note for the person"}]]]),
    it("K01", "PAIRS", [["PAIRS", "pairs", {"gate": "geometry", "proposal_id": "P__p1", "set": {"Confirmed_Tick_Values": "22@273;4@1757.5"}}]]),
    it("C001", "LABEL", [["LABEL", "label", {"gate": None, "needs": "R4", "uses_text": True}],
                         ["EDIT", "edit", {"gate": None, "needs": "R4", "uses_text": True}]], text={"value": "Heart rate", "unit": "bpm"}),
]}]}
_html, ITEMS = BP.render(SPEC, ROOT, log=lambda *_a: None)
SHA = dict((i["id"], i["sha"]) for i in ITEMS["items"])
PROP = dict((i["id"], i["proposal"]) for i in ITEMS["items"])
IDENT = [{"Proposal_ID": "P__p2", "Human_Verification_Status": "CONFIRMED", "Read_Route": "AUTO", "Panel_X1": "900", "Series": "[]",
          "Verified_By": "earlier reviewer", "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": ""},
         {"Proposal_ID": "P__p1", "Human_Verification_Status": "CONFIRMED", "Read_Route": "AUTO", "Panel_X1": "2159",
          "Series": json.dumps([{"name": "ALL", "bar_fill": ""}, {"name": "Other", "bar_fill": "SOLID"}]),
          "Verified_By": "earlier reviewer", "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": "first look 09-23"}]
GEOM = [{"Proposal_ID": "P__p1", "Human_Verification_Status": "CONFIRMED", "Confirmed_Tick_Values": "22@267.5;4@1751.67",
         "Panel_X1": "2159", "Verified_By": "minyeop", "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": ""}]


def ans(iid, decision=None, seen=False, who="minyeop", **kw):
    d = decision or PROP[iid]
    row = {"Item": iid, "Section": "X", "Target_ID": iid, "Proposal": PROP[iid], "Decision": d, "Text": "", "Unit": "",
           "Seen_By_Person": "1" if seen else ("" if d == "HOLD" else "0"), "Verified_By": who,
           "Observed_By": "" if (seen or d == "HOLD") else OBS,
           "Approval_Ref": "" if (seen or d == "HOLD") else "bundle_answers.csv: %s 2026-10-16 승인" % who,
           "Decided_On": "2026-10-16", "Item_SHA256": SHA[iid], "Image_SHA256": "", "Note": ""}
    row.update(kw)
    return row


def go(answers, ident=IDENT, geom=GEOM):
    return BR.route(ITEMS, answers, [dict(r) for r in ident], [dict(r) for r in geom])


def codes(refused):
    return sorted(c for _i, ps in refused for c, _m in ps)


# --- what is routed --------------------------------------------------------------
out, unrouted, held, refused = go([ans("A01")])
row = (out["dispositions"] or [{}])[0]
check("an approved disposition goes to the dispositions gate as an approved observation",
      refused == [] and (row["Draft_ID"], row["Disposition"], row["Which_Panels"], row["Seen_By_Person"], row["Observed_By"])
      == ("DOC_E007", "PARTIAL", "e,f,g", "0", OBS) and row["Approval_Ref"], refused)
check("the row says which bundle item it came from", row.get("Note", "").startswith("bundle A01: PARTIAL"))
out, _u, _h, refused = go([ans("A01", "NON_TARGET", seen=True)])
row = out["dispositions"][0]
check("a seen answer other than the proposal goes as a seen answer", (row["Disposition"], row["Seen_By_Person"], row["Observed_By"])
      == ("NON_TARGET", "1", ""))
out, _u, _h, refused = go([ans("A02")])
row = out["errorbar"][0]
check("an approved error-bar definition carries its quote and page, and no 'verified in source'",
      (row["Dispersion_Type"], row["Errorbar_Definition_Source"], row["Found_On_Page"], row["Verified_In_Source"], row["Observed_By"])
      == ("SEM", "mean ± SEM", "21", "", OBS))
out, _u, _h, _r = go([ans("A02", seen=True)])
check("a seen error-bar answer is 'verified in source'", out["errorbar"][0]["Verified_In_Source"] == "1")
out, _u, _h, refused = go([ans("F01")])
card = out["identity"][0]
ser = json.loads(card["Series"])
check("a series effect changes that series only", refused == [] and ser[0]["bar_fill"] == "OPEN" and ser[1]["bar_fill"] == "SOLID", refused)
check("the card keeps every other field, and its old note", card["Read_Route"] == "AUTO" and card["Panel_X1"] == "2159"
      and card["Note"].startswith("first look 09-23 | bundle F01"))
check("the card row says who approved it, as an approved observation", (card["Verified_By"], card["Seen_By_Person"], card["Observed_By"])
      == ("minyeop", "0", OBS))
out, _u, _h, refused = go([ans("F01"), ans("E02")])
card = out["identity"][0]
check("two items on one card become one row with both changes", refused == [] and len(out["identity"]) == 1
      and card["Panel_X1"] == "2156" and json.loads(card["Series"])[0]["bar_fill"] == "OPEN" and "F01" in card["Note"] and "E02" in card["Note"])
out, _u, _h, refused = go([ans("L01")])
check("one answer with a list of effects writes each card", refused == [] and sorted((r["Proposal_ID"], r["Read_Route"]) for r in out["identity"])
      == [("P__p1", "MANUAL"), ("P__p2", "MANUAL")], refused)
out, unrouted, _h, refused = go([ans("K02")])
check("a list may span gates and a path still to build", refused == [] and out["geometry"][0]["Panel_X1"] == "2150"
      and out["identity"][0]["Panel_X1"] == "2150" and unrouted[0]["Needs"] == "a note for the person", refused)
out, _u, _h, refused = go([ans("K01")])
check("a geometry effect goes to the geometry gate", out["geometry"][0]["Confirmed_Tick_Values"] == "22@273;4@1757.5")
out, unrouted, _h, refused = go([ans("C001", Text="Heart rate", Unit="bpm")])
check("an answer whose path does not exist yet is kept, with what it needs and its text", refused == [] and not out
      and (unrouted[0]["Item"], unrouted[0]["Needs"], unrouted[0]["Text"], unrouted[0]["Unit"]) == ("C001", "R4", "Heart rate", "bpm"))
out, unrouted, held, refused = go([ans("A01", "HOLD")])
check("HOLD is kept as held and written to no gate", refused == [] and not out and not unrouted and len(held) == 1)

# --- what is refused -------------------------------------------------------------
# REVERT: drop the fingerprint check. An answer given on an older page would route under today's options.
check("an answer whose item fingerprint differs is refused", codes(go([ans("A01", Item_SHA256="0" * 64)])[3]) == ["STALE_ITEM"])
check("an item the item file does not have is refused", codes(go([dict(ans("A01"), Item="Z99")])[3]) == ["UNKNOWN_ITEM"])
check("a decision that is not an option is refused", codes(go([ans("A01", "DIGITIZE", seen=True)])[3]) == ["BAD_DECISION"])
check("two answers for one item are both refused", codes(go([ans("A01"), ans("A01", "HOLD")])[3]) == ["ANSWERED_TWICE", "ANSWERED_TWICE"])
check("an answer with nobody's name is refused", "UNATTRIBUTED" in codes(go([ans("A01", who="")])[3]))
# REVERT: let an unseen row differ from the proposal. Nobody saw that judgment: the proposer saw something else.
check("an unseen answer that is not the proposal is refused", codes(go([ans("A01", "NON_TARGET")])[3]) == ["UNSEEN_CHANGE"])
# REVERT: let any Observed_By stand. An approval would be filed under an observer that did not make the proposal.
check("an approved row naming another observer is refused", codes(go([ans("A01", Observed_By="someone else")])[3]) == ["OBSERVER_MISMATCH"])
check("an approval without its reference is refused (approval)", "APPROVAL_INCOMPLETE" in codes(go([ans("A01", Approval_Ref="")])[3]))
check("neither seen nor approved is refused (approval)", "NOT_SEEN_BY_PERSON" in codes(go([ans("A01", Observed_By="", Approval_Ref="")])[3]))
check("an observer approving its own observation is refused (approval)",
      "OBSERVER_IS_APPROVER" in codes(go([ans("A01", who=OBS)])[3]))
# REVERT: let an edited label route as an approval. A person's text would be filed as Claude's observation.
check("an edited label must be a seen answer", "EDIT_NOT_SEEN" in codes(go([ans("C001", "EDIT", Text="HR", Observed_By=OBS)])[3]))
check("an edited label without its text is refused", "EDIT_WITHOUT_TEXT" in codes(go([ans("C001", "EDIT", seen=True)])[3]))
check("a card the record does not have is refused", codes(go([ans("F01")], ident=[])[3]) == ["MISSING_CARD"])
check("a field the record does not have is refused", codes(go([ans("E02")], ident=[{k: v for k, v in IDENT[1].items() if k != "Panel_X1"}])[3])
      == ["UNKNOWN_FIELD"])
check("a series the card does not have is refused",
      codes(go([ans("F01")], ident=[dict(IDENT[1], Series=json.dumps([{"name": "Male"}]))])[3]) == ["UNKNOWN_SERIES"])
# REVERT: let the later item win. Two answers would set one field, and the record would keep whichever came last.
check("two items setting one field differently are refused", "CONFLICTING_EFFECTS" in codes(go([ans("E02"), ans("E03")])[3]))
check("two items setting one series field differently are refused (the series named in any case)",
      "CONFLICTING_EFFECTS" in codes(go([ans("F01"), ans("F02")])[3]))
# REVERT: write one provenance for a card two kinds of answer touched. One of them would be misfiled.
check("a seen answer and an approval on one card are refused together",
      codes(go([ans("F01", seen=True), ans("E02")])[3]) == ["MIXED_PROVENANCE"])

# --- the files ----------------------------------------------------------------------
def write(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


ip, gp, itp = os.path.join(ROOT, "identity.csv"), os.path.join(ROOT, "geometry.csv"), os.path.join(ROOT, "items.json")
write(ip, IDENT); write(gp, GEOM)
json.dump(ITEMS, io.open(itp, "w", encoding="utf-8"), ensure_ascii=False)
ap, outd = os.path.join(ROOT, "answers.csv"), os.path.join(ROOT, "routed")
write(ap, [ans("A01"), ans("A02"), ans("F01"), ans("K01"), ans("C001", Text="Heart rate", Unit="bpm"), ans("E03", "HOLD")])
rc = BR.main(["--items", itp, "--answers", ap, "--identity", ip, "--geometry", gp, "--out", outd])
names = sorted(os.listdir(outd))
check("a clean bundle writes one answer file per gate, the unrouted and held lists, and a log",
      rc == 0 and names == ["errorbar_answers.csv", "figure_disposition_answers.csv", "geometry_answers.csv", "held.csv",
                            "identity_answers.csv", "route_log.json", "unrouted.csv"], names)
head = lambda n: list(csv.reader(io.open(os.path.join(outd, n), encoding="utf-8")))[0]
check("each gate file has the columns its gate requires",
      set(RD.ANSWER_REQUIRED) <= set(head("figure_disposition_answers.csv")) and set(RE.ANSWER_REQUIRED) <= set(head("errorbar_answers.csv"))
      and set(RI.ANSWER_REQUIRED) <= set(head("identity_answers.csv")) and set(RG.ANSWER_REQUIRED) <= set(head("geometry_answers.csv")))
check("no file written is named like a record the gates write", not set(names) & set(BP.RECORD_FILES))
log = json.load(io.open(os.path.join(outd, "route_log.json"), encoding="utf-8"))
check("the log names the decision dates (the gates' --when)", log["decided_on"] == ["2026-10-16"] and log["refused"] == [])
outd2 = os.path.join(ROOT, "routed2")
write(ap, [ans("A01"), ans("A02", Item_SHA256="0" * 64)])
rc = BR.main(["--items", itp, "--answers", ap, "--out", outd2])
# REVERT: write the routable rows anyway. A bundle answered on a stale page would be half-recorded.
check("one refused row and no gate file is written", rc == 1 and sorted(os.listdir(outd2)) == ["refused.csv", "route_log.json"],
      sorted(os.listdir(outd2)))
write(ap, [{k: v for k, v in ans("A01").items() if k != "Item_SHA256"}])
try:
    BR.main(["--items", itp, "--answers", ap, "--out", os.path.join(ROOT, "routed3")])
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("an answers file that is not the page's stops, naming the column", "Item_SHA256" in stopped, stopped)
write(ap, [ans("A01")])
try:
    BR.main(["--items", itp, "--answers", ap, "--identity", ip + ".missing", "--out", os.path.join(ROOT, "routed4")])
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
# REVERT: read a card file that is named but missing as no cards. Every card answer is then refused as MISSING_CARD.
check("a card file that is named but missing stops, naming the flag", "--identity" in stopped and not os.path.exists(os.path.join(ROOT, "routed4")), stopped)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
