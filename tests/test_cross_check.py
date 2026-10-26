# -*- coding: utf-8 -*-
"""Scenarios for cross_check.py - a second, blinded check that lets agreed items be written without the person.

    python3 tests/test_cross_check.py

Every scenario is a way an item could be written without the person when it should not have been: the second
check saw the proposal, it disagreed, it was unsure, it gave no evidence, it spelled the name differently, the item
was a new path or a person's own text, it shares a card with an item the person still has to answer, the second
check is the proposer under another hat - or an automatically written line that the gates would refuse.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bundle_page as BP                                         # noqa: E402
import bundle_route as BR                                        # noqa: E402
import cross_check as XC                                         # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def stops(fn, *a, **kw):
    """The SystemExit message, or "" if it did not stop."""
    try:
        fn(*a, **kw)
    except SystemExit as exc:
        return str(exc)
    return ""


ROOT = tempfile.mkdtemp(prefix="fdt_cross_check_")
OBS = "Claude (survey)"
VER = "Claude (blinded second check)"
WHY = "the caption says mean +/- SEM on page 4"
FACTS = "the proposer found the panel twice"
NOW = "pending: the proposer's own reading"
CARD = lambda pid, **kw: dict({"gate": "identity", "proposal_id": pid}, **kw)


def it(iid, prop, options, **kw):
    return dict({"id": iid, "target": kw.pop("target", iid), "now": NOW, "facts": FACTS, "proposal": prop, "why": WHY,
                 "observed_by": OBS, "options": options + [["HOLD", "hold"]]}, **kw)


CLOSE = lambda pid: {"gate": "outcomes", "row": {"Panel_ID": pid, "Decision": "NON_TARGET"}}
SPEC = {"schema": BP.SCHEMA, "answers_file": "bundle_answers.csv", "title": "t", "notes": ["n"], "sections": [
    {"id": "H", "title": "panels", "items": [
        it("A01", "CLOSE", [["CLOSE", "close", [CLOSE("DOC_D002_P1"), CLOSE("DOC_D002_P2")]],
                            ["READ", "read by hand", {"gate": None, "needs": "manual values path"}]]),
        it("A02", "SEM", [["SEM", "SEM", {"gate": "errorbar", "row": {"Source_Document_ID": "DOC", "Draft_ID": "DOC_D003",
                                                                     "Dispersion_Type": "SEM",
                                                                     "Errorbar_Definition_Source": "mean ± SEM",
                                                                     "Found_On_Page": "4"}}],
                          ["SD", "SD", {"gate": "errorbar", "row": {"Source_Document_ID": "DOC", "Draft_ID": "DOC_D003",
                                                                   "Dispersion_Type": "SD",
                                                                   "Errorbar_Definition_Source": "mean ± SD",
                                                                   "Found_On_Page": "4"}}]]),
        it("C01", "LABEL", [["LABEL", "label", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D004_P1", "Decision": "LABEL"},
                                                "uses_text": True}],
                            ["EDIT", "edit", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D004_P1", "Decision": "LABEL"},
                                              "uses_text": True}],
                            ["NON_TARGET", "close", CLOSE("DOC_D004_P1")]], text={"value": "Heart rate", "unit": "bpm"}),
        it("C02", "LABEL", [["LABEL", "label", {"gate": "outcomes", "row": {"Panel_ID": "DOC_D004_P2", "Decision": "LABEL"},
                                                "uses_text": True}],
                            ["NON_TARGET", "close", CLOSE("DOC_D004_P2")]], text={"value": "Stroke volume", "unit": "mL"}),
    ]},
    {"id": "F", "title": "cards", "items": [
        it("F01", "OPEN", [["OPEN", "open", CARD("P__p1", series=[{"name": "ALL", "set": {"bar_fill": "OPEN"}}])],
                           ["SOLID", "solid", CARD("P__p1", series=[{"name": "ALL", "set": {"bar_fill": "SOLID"}}])]]),
        it("F02", "UNIT", [["UNIT", "unit", CARD("P__p1", set={"Unit": "mmHg"})]]),
        it("F03", "UNIT", [["UNIT", "unit", CARD("P__p2", set={"Unit": "bpm"})]]),
    ]},
    {"id": "G", "title": "paths", "items": [
        it("G01", "BUILD", [["BUILD", "build the path", {"gate": None, "needs": "new gate"}]], target="fdt:record_manual_values"),
        it("X01", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D005_P1")]], person_only=True),
        it("Y01", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P1")]]),
        it("Y02", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P2")]]),
        it("Y03", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P3")]]),
        it("Y04", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P4")]]),
        it("Y05", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P5")]]),
        it("Y06", "CLOSE", [["CLOSE", "close", CLOSE("DOC_D006_P6")]]),
    ]},
]}
_html, ITEMS = BP.render(SPEC, ROOT, log=lambda *_a: None)
IDENT = [{"Proposal_ID": pid, "Human_Verification_Status": "CONFIRMED", "Read_Route": "AUTO", "Panel_X1": "900", "Unit": "",
          "Mark_Type": "BAR", "Series": json.dumps([{"name": "ALL", "bar_fill": ""}]), "Verified_By": "earlier reviewer",
          "Seen_By_Person": "1", "Observed_By": "", "Approval_Ref": "", "Note": ""} for pid in ("P__p1", "P__p2")]


def V(iid, choice=None, conf="HIGH", ev=("p.4: 'mean ± SEM'",), **kw):
    d = {"id": iid, "choice": choice if choice is not None else [i for i in ITEMS["items"] if i["id"] == iid][0]["proposal"],
         "confidence": conf, "evidence": list(ev)}
    d.update(kw)
    return d


BASE = [V("A01"), V("A02", choice="sem"), V("C01", text="heart  RATE", unit=" BPM"), V("C02", text="Cardiac output", unit="L/min"),
        V("F01", choice="SOLID"), V("F02"), V("F03"), V("G01"), V("X01"),
        V("Y01", conf="LOW"), V("Y02", ev=("", "  ")), V("Y03", choice="HOLD"), V("Y04", choice="MAYBE")]          # Y05: none


def doc(verdicts, verifier=VER):
    return {"verifier": verifier, "verdicts": verdicts}


def go(verdicts=BASE, verifier=VER, approver="minyeop", ref="chat 2026-10-18 'automate checks like this'", items=None,
       spec=None):
    return XC.split(spec or SPEC, items or ITEMS, doc(verdicts, verifier), approver, ref, "2026-10-18",
                    "bundle_answers.csv", "ab" * 32)


# --- brief: what the second check is given ---------------------------------------------------------------------
print("brief")
B = XC.brief(SPEC, rules="close what is not a target outcome")
dump = json.dumps(B, ensure_ascii=False)
# REVERT: put the proposal into the brief. Agreement then only says the second check can read.
check("no item in the brief carries a blinded field", all(not set(XC.BLINDED) & set(b) for b in B["items"]),
      [sorted(set(XC.BLINDED) & set(b)) for b in B["items"]])
check("nor does the proposer's reasoning, facts, current-state note or name appear anywhere in it",
      not [s for s in (WHY, FACTS, NOW, OBS) if s in dump], [s for s in (WHY, FACTS, NOW, OBS) if s in dump])
# REVERT: hand the options over with their effects. The effects name the rows the proposer would write.
check("options come without their effects", '"gate"' not in dump and "needs" not in dump and "Panel_ID" not in dump)
check("the proposed name is not in the brief, but the brief says a name must be written",
      "Heart rate" not in dump and [b for b in B["items"] if b["id"] == "C01"][0].get("names")
      and [b for b in B["items"] if b["id"] == "C01"][0]["options"][0] == ["LABEL", "label", True])
check("the review's rules travel with the brief, and every item is asked",
      B["rules"] == "close what is not a target outcome" and [b["id"] for b in B["items"]] == [i["id"] for i in ITEMS["items"]])

# --- split: where each item goes -------------------------------------------------------------------------------
print("split")
rows, person, rec = go()
to = dict((r["id"], (r["to"], r["code"])) for r in rec["items"])
check("an agreed, confident, evidenced item is written automatically", to["A01"] == ("AUTO", "AGREE") and to["F03"] == ("AUTO", "AGREE"), to)
check("a choice in another case is the same choice", to["A02"] == ("AUTO", "AGREE"), to["A02"])
# REVERT: compare names exactly. 'heart  RATE' is the name the proposal wrote.
check("a name that differs only in case and spacing agrees", to["C01"] == ("AUTO", "AGREE"), to["C01"])
# REVERT: drop the name comparison. Two checks that agree a panel is named but not on its name have not agreed.
check("a different name goes to the person", to["C02"] == ("PERSON", "TEXT_DIFFERS"), to["C02"])
# REVERT: drop the disagreement check.
check("a disagreement goes to the person", to["F01"] == ("PERSON", "DISAGREE"), to["F01"])
# REVERT: drop the shared-card move. F02 and F01 would then be routed from the same card row twice.
check("an agreed item on the same card as a disagreement goes too", to["F02"] == ("PERSON", "SHARED_CARD"), to["F02"])
# REVERT: drop the new-path check. Building a gate is the person's call however sure two checks are.
check("a new path goes to the person even when both agree", to["G01"] == ("PERSON", "PERSON_ONLY"), to["G01"])
check("an item marked for the person goes to the person", to["X01"] == ("PERSON", "PERSON_ONLY"), to["X01"])
# REVERT: drop the confidence check.
check("an unsure agreement goes to the person", to["Y01"] == ("PERSON", "LOW_CONFIDENCE"), to["Y01"])
# REVERT: drop the evidence check. Blank evidence is no evidence.
check("an agreement without evidence goes to the person", to["Y02"] == ("PERSON", "NO_EVIDENCE"), to["Y02"])
check("the second check holding goes to the person, named as such", to["Y03"] == ("PERSON", "VERIFIER_HELD"), to["Y03"])
check("an answer that is not an option goes to the person, named as such", to["Y04"] == ("PERSON", "UNKNOWN_CHOICE"), to["Y04"])
check("an item the second check did not answer goes to the person", to["Y05"] == ("PERSON", "NO_VERDICT"), to["Y05"])
check("the record counts both sides and keeps the spec's order",
      rec["auto"] == len(rows) == 4 and rec["person"] == 11 and [r["id"] for r in rec["items"]] == [i["id"] for i in ITEMS["items"]],
      (rec["auto"], rec["person"], [r["id"] for r in rec["items"]]))
edit_spec = json.loads(json.dumps(SPEC))
edit_spec["sections"][0]["items"][2]["proposal"] = "EDIT"
_h, edit_items = BP.render(edit_spec, ROOT, log=lambda *_a: None)
_r, _p, erec = go([V("C01", choice="EDIT", text="Heart rate", unit="bpm")], items=edit_items, spec=edit_spec)
# REVERT: let an EDIT proposal through. A person's own text cannot be an approved observation (EDIT_NOT_SEEN).
check("an EDIT proposal goes to the person", [r["code"] for r in erec["items"] if r["id"] == "C01"] == ["PERSON_ONLY"], erec["items"][2])

# --- the automatic lines -----------------------------------------------------------------------------------------
print("automatic lines")
R = dict((r["Item"], r) for r in rows)
# REVERT: mark the automatic line as seen. Nobody looked; the record must say so.
check("an automatic line says the person did not see it", all(r["Seen_By_Person"] == "0" for r in rows))
check("it is approved by the person who gave the standing approval, observed by the proposer",
      all(r["Verified_By"] == "minyeop" and r["Observed_By"] == OBS for r in rows))
check("its approval names the standing approval, the second check and the verdicts' hash",
      all("minyeop" in r["Approval_Ref"] and "automate checks like this" in r["Approval_Ref"] and VER in r["Approval_Ref"]
          and "abababababab" in r["Approval_Ref"] for r in rows), rows[0]["Approval_Ref"])
# REVERT: write the second check's spelling. The name recorded is the one the proposal showed.
check("a name is written as the proposal wrote it", (R["C01"]["Text"], R["C01"]["Unit"]) == ("Heart rate", "bpm"),
      (R["C01"]["Text"], R["C01"]["Unit"]))
check("the second check's evidence is in the note", R["A01"]["Note"].startswith("AI 교차 검증: p.4"), R["A01"]["Note"])
out, unrouted, held, refused = BR.route(ITEMS, rows, IDENT)
# REVERT: any of the line's provenance or fingerprints. The gates refuse what this module writes.
check("every automatic line passes bundle_route", refused == [] and len(out["outcomes"]) == 3 and len(out["errorbar"]) == 1
      and len(out["identity"]) == 1, (refused, dict((k, len(v)) for k, v in out.items())))
check("and reaches the gate as an approved observation",
      all(r["Seen_By_Person"] == "0" and r["Observed_By"] == OBS for r in out["outcomes"])
      and out["identity"][0]["Seen_By_Person"] == "0" and out["errorbar"][0]["Observed_By"] == OBS)
js = io.open(os.path.join(_paths.CODE, "bundle_page.js"), encoding="utf-8").read()
cols = re.findall(r"'([A-Za-z_0-9]+)'", re.search(r"var CSV_COLUMNS = \[(.*?)\];", js, re.S).group(1))
check("the automatic answers file has the page's columns", tuple(cols) == XC.CSV_COLUMNS, cols)

# --- what the person is left with ---------------------------------------------------------------------------------
print("person page")
pids = [i["id"] for s in person["sections"] for i in s["items"]]
check("the person's spec holds only the items sent to the person", pids == [r["id"] for r in rec["items"] if r["to"] == "PERSON"], pids)
pf = dict((i["id"], i) for s in person["sections"] for i in s["items"])
# REVERT: leave facts as they were. The person would not see that a second check disagreed, or what it found.
check("each says why it came to the person and what the second check answered",
      pf["F01"]["facts"].startswith("[AI 교차 검증 → 사람: DISAGREE") and "SOLID" in pf["F01"]["facts"]
      and pf["F01"]["facts"].endswith(FACTS), pf["F01"]["facts"])
check("the page's notes count what was written without the person", "4항목" in person["notes"][0] and person["notes"][1:] == ["n"])
_h2, PITEMS = BP.render(person, ROOT, log=lambda *_a: None)
same = dict((i["id"], i["sha"]) for i in ITEMS["items"])
check("the person's page asks the same items (same fingerprints), so one route takes both answer files",
      all(i["sha"] == same[i["id"]] for i in PITEMS["items"]))


def pans(iid, decision=None):
    i = [x for x in PITEMS["items"] if x["id"] == iid][0]
    return {"Item": iid, "Section": i["sec"], "Target_ID": i["target"], "Proposal": i["proposal"],
            "Decision": decision or i["proposal"], "Text": "", "Unit": "", "Seen_By_Person": "1", "Verified_By": "minyeop",
            "Observed_By": "", "Approval_Ref": "", "Decided_On": "2026-10-18", "Item_SHA256": i["sha"], "Image_SHA256": "",
            "Note": ""}


merged, unanswered = XC.merge(rows, [pans("F01", "SOLID"), pans("F02"), pans("Y01")], rec)
out, unrouted, held, refused = BR.route(ITEMS, merged, IDENT)
check("merged answers route once against the original items, card answers on one row",
      refused == [] and len(out["identity"]) == 2 and len(merged) == 7, refused)
check("merge names the person's unanswered items", "G01" in unanswered and "Y05" in unanswered and "F01" not in unanswered, unanswered)
# REVERT: let the person file carry an automatic item. That item would then be answered twice.
check("an answer from the person's file to an item already written automatically stops",
      "A01" in stops(XC.merge, rows, [pans("F01"), dict(pans("F01"), Item="A01")], rec))
# REVERT: take any automatic file. One from another run would be merged with this run's person answers.
check("an automatic file that is not this record's stops", stops(XC.merge, rows[:-1], [], rec) != "")

# --- what stops ----------------------------------------------------------------------------------------------------
print("stops")
# REVERT: drop the self-check. The proposer re-reading its own proposal is one look, not two.
check("a second check named like the proposer stops", "교차 검증" in stops(go, verifier=" claude (SURVEY)".strip()))
check("a proposer named like the approver stops", OBS in stops(go, approver=OBS))
check("verdicts that do not say who checked stop", "verifier" in stops(go, verifier=""))
check("a split without the standing approval stops", "--approver" in stops(go, approver="") and "--approval-ref" in stops(go, ref=" "))
check("two verdicts for one item stop", "A01" in stops(go, verdicts=[V("A01"), V("A01")]))
check("a verdict for an item not in the brief stops", "Z99" in stops(go, verdicts=[V("A01"), {"id": "Z99", "choice": "X"}]))
short = {"answers_file": ITEMS["answers_file"], "items": [i for i in ITEMS["items"] if i["id"] != "A02"]}
msg = stops(go, items=short, verdicts=[V("A01")])
# REVERT: skip spec items the items file lacks. The page and the items file would then be from different builds.
check("an items file from another build stops, naming the missing item", "A02" in msg and "항목 파일" in msg, msg)

# --- CLI -------------------------------------------------------------------------------------------------------
print("cli")
sp, ip, vp, rp = [os.path.join(ROOT, n) for n in ("spec.json", "items.json", "verdicts.json", "rules.md")]
json.dump(SPEC, io.open(sp, "w", encoding="utf-8"), ensure_ascii=False)
json.dump(ITEMS, io.open(ip, "w", encoding="utf-8"), ensure_ascii=False)
json.dump(doc(BASE), io.open(vp, "w", encoding="utf-8"), ensure_ascii=False)
io.open(rp, "w", encoding="utf-8").write("rules")
bp = os.path.join(ROOT, "brief.json")
rc = XC.main(["brief", "--spec", sp, "--out", bp, "--rules", rp])
check("brief writes the brief with the rules", rc == 0 and json.load(io.open(bp, encoding="utf-8"))["rules"] == "rules")
od = os.path.join(ROOT, "split")
rc = XC.main(["split", "--spec", sp, "--items", ip, "--verdicts", vp, "--approver", "minyeop", "--approval-ref", "chat",
              "--when", "2026-10-18", "--answers-file", "bundle_answers.csv", "--out", od])
check("split writes the automatic answers, the person's spec and the record",
      rc == 0 and sorted(os.listdir(od)) == ["auto_answers.csv", "cross_check.json", "person_spec.json"], os.listdir(od))
idp = os.path.join(ROOT, "identity.csv")
with io.open(idp, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(IDENT[0]))
    w.writeheader()
    w.writerows(IDENT)
rc = BR.main(["--items", ip, "--answers", os.path.join(od, "auto_answers.csv"), "--identity", idp, "--out", os.path.join(ROOT, "routed")])
check("bundle_route takes the automatic answers file as it is", rc == 0 and not os.path.exists(os.path.join(ROOT, "routed", "refused.csv")))
vsha = XC.sha(vp, 12)
check("the record carries the verdicts file's hash", json.load(io.open(os.path.join(od, "cross_check.json"), encoding="utf-8"))
      ["verdicts_sha256"].startswith(vsha))
pa = os.path.join(ROOT, "person_answers.csv")
XC.write_csv(pa, [pans("F01", "SOLID")])
mp = os.path.join(ROOT, "merged.csv")
rc = XC.main(["merge", "--auto", os.path.join(od, "auto_answers.csv"), "--person", pa, "--record", os.path.join(od, "cross_check.json"),
              "--out", mp])
check("merge writes one answers file", rc == 0 and len(XC.read_csv(mp)) == 5)
io.open(pa, "w", encoding="utf-8").write("Item,Decision\nF01,SOLID\n")
check("a person file without the page's columns stops", "Item_SHA256" in stops(XC.read_csv, pa))

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
