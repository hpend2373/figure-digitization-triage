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
import record_legends as RLG                                     # noqa: E402
import record_outcomes as RO                                     # noqa: E402

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
    it("E02", "UNIT", [["UNIT", "unit", CARD("P__p1", set={"Unit": "mmHg"})]]),
    it("E03", "UNIT", [["UNIT", "unit", CARD("P__p1", set={"Unit": "kPa"})]]),
    it("L01", "MANUAL", [["MANUAL", "both panels", [CARD("P__p1", set={"Read_Route": "MANUAL"}), CARD("P__p2", set={"Read_Route": "MANUAL"})]]]),
    it("K02", "TOP", [["TOP", "top", [{"gate": "geometry", "proposal_id": "P__p1", "set": {"Y_Tick_Top_Value": "25"}},
                                      CARD("P__p1", set={"Mark_Type": "BAR_MONO"}), {"gate": None, "needs": "a note for the person"}]]]),
    it("K01", "PAIRS", [["PAIRS", "pairs", {"gate": "geometry", "proposal_id": "P__p1", "set": {"Confirmed_Tick_Values": "22@273;4@1757.5"}}]]),
    it("C001", "LABEL", [["LABEL", "label", {"gate": None, "needs": "R4", "uses_text": True}],
                         ["EDIT", "edit", {"gate": None, "needs": "R4", "uses_text": True}]], text={"value": "Heart rate", "unit": "bpm"}),
    it("C002", "LABEL", [["LABEL", "label", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D002_P1", "Decision": "LABEL"}, "uses_text": True}],
                         ["EDIT", "edit", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D002_P1", "Decision": "LABEL"}, "uses_text": True}],
                         ["NON_TARGET", "close", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D002_P1", "Decision": "NON_TARGET"}}]],
       text={"value": "Stroke volume", "unit": "mL"}),
    it("L02", "LEGEND", [["LEGEND", "a legend per panel", {"gate": "legends", "row": {"Draft_ID": "DOC_D003", "Decision": "LEGENDS",
                                                                                          "Legend_Groups": "p1|p2"}}]]),
]}]}
_html, ITEMS = BP.render(SPEC, ROOT, log=lambda *_a: None)
SHA = dict((i["id"], i["sha"]) for i in ITEMS["items"])
PROP = dict((i["id"], i["proposal"]) for i in ITEMS["items"])
IDENT = [{"Proposal_ID": "P__p2", "Human_Verification_Status": "CONFIRMED", "Read_Route": "AUTO", "Panel_X1": "900", "Series": "[]",
          "Unit": "", "Mark_Type": "",
          "Verified_By": "earlier reviewer", "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": ""},
         {"Proposal_ID": "P__p1", "Human_Verification_Status": "CONFIRMED", "Read_Route": "AUTO", "Panel_X1": "2159",
          "Unit": "", "Mark_Type": "BAR",
          "Series": json.dumps([{"name": "ALL", "bar_fill": ""}, {"name": "Other", "bar_fill": "SOLID"}]),
          "Verified_By": "earlier reviewer", "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": "first look 09-23"}]
GEOM = [{"Proposal_ID": "P__p1", "Human_Verification_Status": "CONFIRMED", "Confirmed_Tick_Values": "22@267.5;4@1751.67",
         "Y_Tick_Top_Value": "22", "Frame_Source": "",
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
      and card["Unit"] == "mmHg" and json.loads(card["Series"])[0]["bar_fill"] == "OPEN" and "F01" in card["Note"] and "E02" in card["Note"])
out, _u, _h, refused = go([ans("L01")])
check("one answer with a list of effects writes each card", refused == [] and sorted((r["Proposal_ID"], r["Read_Route"]) for r in out["identity"])
      == [("P__p1", "MANUAL"), ("P__p2", "MANUAL")], refused)
out, unrouted, _h, refused = go([ans("K02")])
check("a list may span gates and a path still to build", refused == [] and out["geometry"][0]["Y_Tick_Top_Value"] == "25"
      and out["identity"][0]["Mark_Type"] == "BAR_MONO" and unrouted[0]["Needs"] == "a note for the person", refused)
out, _u, _h, refused = go([ans("K01")])
check("a geometry effect goes to the geometry gate", out["geometry"][0]["Confirmed_Tick_Values"] == "22@273;4@1757.5")
out, unrouted, _h, refused = go([ans("C001", Text="Heart rate", Unit="bpm")])
check("an answer whose path does not exist yet is kept, with what it needs and its text", refused == [] and not out
      and (unrouted[0]["Item"], unrouted[0]["Needs"], unrouted[0]["Text"], unrouted[0]["Unit"]) == ("C001", "R4", "Heart rate", "bpm"))
out, _u, _h, refused = go([ans("C002", Text="Stroke volume", Unit="mL")])
# REVERT: route the decision without the name. The outcome gate would receive LABEL with nothing to write.
check("a name goes to the outcome gate with the name and unit the page carried", refused == []
      and (out["outcomes"][0]["Panel_ID"], out["outcomes"][0]["Decision"], out["outcomes"][0]["Outcome_Label"], out["outcomes"][0]["Unit"])
      == ("DOC_D002_P1", "LABEL", "Stroke volume", "mL"), (refused, out.get("outcomes")))
out, _u, _h, refused = go([ans("C002", "EDIT", seen=True, Text="SV", Unit="mL")])
check("an edited name goes as the person typed it, as a seen answer", (out["outcomes"][0]["Outcome_Label"], out["outcomes"][0]["Seen_By_Person"])
      == ("SV", "1"), out.get("outcomes"))
out, _u, _h, refused = go([ans("C002", "NON_TARGET", seen=True)])
check("'not a target' goes without a name", (out["outcomes"][0]["Decision"], out["outcomes"][0]["Outcome_Label"]) == ("NON_TARGET", ""))
out, _u, _h, refused = go([ans("L02")])
check("a legend split goes to the legend gate as an approved observation",
      (out["legends"][0]["Draft_ID"], out["legends"][0]["Legend_Groups"], out["legends"][0]["Observed_By"]) == ("DOC_D003", "p1|p2", OBS))
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
check("a field the record does not have is refused", codes(go([ans("E02")], ident=[{k: v for k, v in IDENT[1].items() if k != "Unit"}])[3])
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

# --- what the gates take from an answer ------------------------------------------------
ITEMS2 = json.loads(json.dumps(ITEMS))
ITEMS2["items"].append({"id": "Z01", "sec": "X", "group": "Z01", "target": "P__p1", "now": "", "proposal": "CLIP",
                        "observed_by": OBS, "text": None, "sha": "c" * 64, "img_sha": "",
                        "options": [["CLIP", "clip", CARD("P__p1", set={"Panel_X1": "2156"})], ["HOLD", "hold"]]})
z = dict(ans("A01"), Item="Z01", Proposal="CLIP", Decision="CLIP", Item_SHA256="c" * 64)
# REVERT: route any field the card has. The identity gate rebuilds the card from its proposal and keeps only the
# fields it takes, so a changed box would be routed, "recorded", and gone.
check("a card field the gate does not take from an answer is refused",
      codes(BR.route(ITEMS2, [z], [dict(r) for r in IDENT], [dict(r) for r in GEOM])[3]) == ["FIELD_NOT_TAKEN"])
bad_spec = json.loads(json.dumps(SPEC))
bad_spec["sections"][0]["items"].append(it("Z02", "CLIP", [["CLIP", "clip", CARD("P__p1", set={"Panel_X1": "2156"})]]))
check("... and a page with such an option is not built",
      any(c == "BAD_EFFECT" and "Panel_X1" in m for c, m in BP.check_spec(bad_spec, ROOT)))
bad_spec = json.loads(json.dumps(SPEC))
bad_spec["sections"][0]["items"].append(it("Z03", "OPEN", [["OPEN", "open", {"gate": "geometry", "proposal_id": "P__p1",
                                                                            "series": [{"name": "ALL", "set": {"bar_fill": "OPEN"}}]}]]))
check("... nor one that names series on a geometry card, which has none",
      any(c == "BAD_EFFECT" and "Series" in m for c, m in BP.check_spec(bad_spec, ROOT)))


def taken(module, fn_name):
    """The answer fields a gate's record() copies into the card, read off its code."""
    import inspect
    import re
    src = inspect.getsource(getattr(module, fn_name))
    names = set(re.findall(r'answer\.get\("([A-Za-z_]+)"\)', src))
    # a field copied through a helper - "Read_Route": route_of(answer)
    names |= set(re.findall(r'"([A-Za-z_]+)":\s*[A-Za-z_]+\(answer\)', src))
    for const in re.findall(r'answer\.get\(([A-Z_]+)\)', src):
        names.add(getattr(module, const))
    return names - {"Proposal_ID", "Verified_By", "Note"}


# REVERT: list a field the gate does not copy. Its effect would pass this router and vanish in the gate.
for gate, mod in (("identity", RI), ("geometry", RG)):
    check("every card field this router passes is one the %s gate copies from an answer" % gate,
          set(BP.CARD_TAKES[gate]) <= taken(mod, "record"), sorted(set(BP.CARD_TAKES[gate]) - taken(mod, "record")))

GP = RG.GP
GDIR = os.path.join(ROOT, "geometry_gate")
os.makedirs(GDIR)
READER = {"Proposal_ID": "P__p1", "Raster": "fig.png", "Region": "0,0,220,160",
          "Panel_X0": "10", "Panel_X1": "200", "Panel_Y0": "5", "Panel_Y1": "150",
          "Y_Tick_Pixels": "10;50;90", "Y_Tick_Count": "3", "Y_Tick_Read_Status": GP.READ_OK,
          "Y_Tick_Read_Values": "30@10;20@50;10@90", "Y_Tick_Read_First": "30", "Y_Tick_Read_Last": "10",
          "Human_Verification_Status": GP.PROPOSAL_PENDING}
GP.write_proposals(os.path.join(GDIR, RG.PROPOSALS), [READER])
DRAWN_CARD = dict(GP.with_drawn_frame(READER, [12, 198, 6, 148]), Human_Verification_Status="CONFIRMED",
                  Y_Tick_Top_Value="30", Y_Tick_Bottom_Value="10", Confirmed_Tick_Values="30@20;10@140",
                  Verified_By="minyeop", Verified_At="2026-09-23", Seen_By_Person="1", Observed_By="", Approval_Ref="", Note="")
DRAWN_CARD = dict((k, str(v)) for k, v in DRAWN_CARD.items())
out, _u, _h, refused = BR.route(ITEMS, [ans("K01")], [dict(r) for r in IDENT], [dict(DRAWN_CARD)])
grow = (out.get("geometry") or [{}])[0]
# REVERT: send a drawn card without its frame. record_geometry rebuilds the row on the reader's frame, and the
# frame a person drew is replaced by the one the reader found - while only the tick pairs were meant to change.
check("a card on a frame a person drew carries that frame", refused == [] and grow.get("Drawn_Frame") == "12,198,6,148", grow.get("Drawn_Frame"))
written, turned, _p = RG.record(GDIR, [dict(grow, Confirmed_Tick_Values="30@22;10@140")], "2026-10-16",
                                out_path=os.path.join(GDIR, RG.DECISIONS), replace=True, log=lambda *_a: None)
wrow = (written or [{}])[0]
check("... and the geometry gate records the new pairs on the drawn frame, not the reader's",
      not turned and (str(wrow.get("Panel_X0")), str(wrow.get("Panel_Y1")), wrow.get("Frame_Source"), wrow.get("Confirmed_Tick_Values"))
      == ("12", "148", GP.FRAME_DRAWN, "30@22;10@140"), (turned, {k: wrow.get(k) for k in ("Panel_X0", "Panel_Y1", "Frame_Source")}))
out, _u, _h, refused = BR.route(ITEMS, [ans("K01")], [dict(r) for r in IDENT], [dict(GEOM[0])])
check("a card on the reader's frame carries no drawn frame", "Drawn_Frame" not in out["geometry"][0])

# --- the files ----------------------------------------------------------------------
def write(path, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


ip, gp, itp = os.path.join(ROOT, "identity.csv"), os.path.join(ROOT, "geometry.csv"), os.path.join(ROOT, "items.json")
write(ip, IDENT); write(gp, GEOM)
json.dump(ITEMS, io.open(itp, "w", encoding="utf-8"), ensure_ascii=False)
ap, outd = os.path.join(ROOT, "answers.csv"), os.path.join(ROOT, "routed")
write(ap, [ans("A01"), ans("A02"), ans("F01"), ans("K01"), ans("C001", Text="Heart rate", Unit="bpm"), ans("E03", "HOLD"),
           ans("C002", Text="Stroke volume", Unit="mL"), ans("L02")])
rc = BR.main(["--items", itp, "--answers", ap, "--identity", ip, "--geometry", gp, "--out", outd])
names = sorted(os.listdir(outd))
check("a clean bundle writes one answer file per gate, the unrouted and held lists, and a log",
      rc == 0 and names == ["errorbar_answers.csv", "figure_disposition_answers.csv", "geometry_answers.csv", "held.csv",
                            "identity_answers.csv", "legend_answers.csv", "outcome_answers.csv", "route_log.json", "unrouted.csv"], names)
head = lambda n: list(csv.reader(io.open(os.path.join(outd, n), encoding="utf-8")))[0]
check("each gate file has the columns its gate requires",
      set(RD.ANSWER_REQUIRED) <= set(head("figure_disposition_answers.csv")) and set(RE.ANSWER_REQUIRED) <= set(head("errorbar_answers.csv"))
      and set(RI.ANSWER_REQUIRED) <= set(head("identity_answers.csv")) and set(RG.ANSWER_REQUIRED) <= set(head("geometry_answers.csv"))
      and set(RO.ANSWER_REQUIRED) <= set(head("outcome_answers.csv")) and set(RLG.ANSWER_REQUIRED) <= set(head("legend_answers.csv")))
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
