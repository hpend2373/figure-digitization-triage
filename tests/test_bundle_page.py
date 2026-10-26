# -*- coding: utf-8 -*-
"""Scenarios for bundle_page.py - the one page that holds what is left, with a proposal on every line.

    python3 tests/test_bundle_page.py

What makes a line an answer is bundle_page.js and is tested under node (test_bundle_page.mjs). These are the
page's own refusals - every way a bundle can put a question in front of a person that it should not - and what the
page and its item file carry.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import hashlib
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

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_bundle_page_")
try:
    from PIL import Image
    for name, colour in (("fig1.png", (200, 30, 30)), ("fig2.png", (30, 30, 200))):
        Image.new("RGB", (120, 80), colour).save(os.path.join(ROOT, name))
    HAVE_PIL = True
except Exception:                                                 # pragma: no cover
    HAVE_PIL = False
    for name in ("fig1.png", "fig2.png"):
        open(os.path.join(ROOT, name), "wb").write(b"\x89PNG not really")

DISP = lambda d, v, w="": {"gate": "dispositions", "row": {"Draft_ID": d, "Disposition": v, "Which_Panels": w}}


def spec():
    return {
        "schema": BP.SCHEMA, "title": "left after the census", "answers_file": "bundle_answers.csv",
        "notes": ["person tasks are listed here"],
        "sections": [
            {"id": "B", "title": "figures", "items": [
                {"id": "B01", "target": "DOC_D001", "now": "NOT_DATA (caption screen)", "proposal": "DIGITIZE",
                 "why": "group means per time point", "observed_by": "Claude (PDF survey)",
                 "images": [{"path": "fig1.png", "caption": "Fig 1"}],
                 "options": [["DIGITIZE", "read it", DISP("DOC_D001", "DIGITIZE")],
                             ["NON_TARGET", "not a target", DISP("DOC_D001", "NON_TARGET")],
                             ["HOLD", "hold"]]}]},
            {"id": "C", "title": "outcome labels", "items": [
                {"id": "C001", "target": "DOC_D002__p1", "now": "no label", "proposal": "LABEL", "group": "C:DOC_D002",
                 "why": "y-axis title", "observed_by": "Claude (label agent)", "text": {"value": "Heart rate", "unit": "bpm"},
                 "images": [{"path": "fig2.png"}],
                 "options": [["LABEL", "as proposed", {"gate": None, "needs": "R4 outcome labels", "uses_text": True}],
                             ["EDIT", "edited", {"gate": None, "needs": "R4 outcome labels", "uses_text": True}],
                             ["HOLD", "hold"]]},
                {"id": "C002", "target": "DOC_D002__p2", "now": "BAR_MONO, fill blank", "proposal": "OPEN", "group": "C:DOC_D002",
                 "why": "grey 215 reads as open", "observed_by": "measure (bar interior)", "table": [["x", "ORT"], ["dark", "0.02"]],
                 "options": [["OPEN", "open", {"gate": "identity", "proposal_id": "DOC_D002__p2",
                                               "series": [{"name": "ALL", "set": {"bar_fill": "OPEN"}}]}],
                             ["MANUAL", "manual", {"gate": "identity", "proposal_id": "DOC_D002__p2", "set": {"Read_Route": "MANUAL"}}],
                             ["HOLD", "hold"]]}]},
        ]}


def codes(sp):
    return sorted(set(c for c, _m in BP.check_spec(sp, ROOT)))


def item(sp, iid):
    return [it for _s, it in BP.items_of(sp) if it["id"] == iid][0]


# --- the page ------------------------------------------------------------------
S = spec()
check("a complete bundle has no problems", BP.check_spec(S, ROOT) == [], BP.check_spec(S, ROOT))
HTML, ITEMS = BP.render(S, ROOT, log=lambda *_a: None)
check("the item file holds every item, in order", [i["id"] for i in ITEMS["items"]] == ["B01", "C001", "C002"])
# REVERT: pre-check an option. A pre-selected proposal is an answer nobody chose; 'fill with the proposals' is a click.
check("nothing is pre-selected", not re.search(r"<input[^>]*\schecked", HTML))
check("every option has its radio", all(HTML.count("data-q='%s'>" % i["id"]) == len(i["options"]) for i in ITEMS["items"]))
check("every proposal is marked as one", HTML.count("<span class='badge'>제안</span>") - 1 == 3)
check("the page shows each proposal's reason and who made it",
      all(BP.esc(it["why"]) in HTML and ("— 본 것: %s" % BP.esc(it["observed_by"])) in HTML for _s, it in BP.items_of(S)))
check("the answer logic on the page is bundle_page.js as tested", io.open(os.path.join(_paths.CODE, BP.LOGIC), encoding="utf-8").read() in HTML)
check("the page loads nothing from outside", not re.search(r"(src|href)=['\"]https?:", HTML))
check("a name field only where the item takes a name", HTML.count("data-text='") == 1 and "value='Heart rate'" in HTML)
check("two items of one group share one 'seen' key and say so", HTML.count("data-seen='C:DOC_D002'") == 2
      and HTML.count("(이 그림의 항목 모두)") == 2 and HTML.count("data-seen='B01'") == 1)

# --- fingerprints ----------------------------------------------------------------
fsha = lambda n: hashlib.sha256(open(os.path.join(ROOT, n), "rb").read()).hexdigest()
by = dict((i["id"], i) for i in ITEMS["items"])
check("each item carries the sha256 of the image files it shows", by["B01"]["img_sha"] == fsha("fig1.png")
      and by["C001"]["img_sha"] == fsha("fig2.png") and by["C002"]["img_sha"] == "")
check("the item fingerprint is recomputable from the spec", all(by[it["id"]]["sha"] == BP.item_sha(it) for _s, it in BP.items_of(S)))
S2 = spec(); item(S2, "B01")["options"][1][2]["row"]["Disposition"] = "NOT_DATA"
# REVERT: leave the effects out of the fingerprint. An answer approved against "close as NON_TARGET" would route
# unchanged after the option was edited to write something else.
check("changing what an option writes changes the fingerprint", BP.item_sha(item(S2, "B01")) != BP.item_sha(item(S, "B01")))
S3 = spec(); item(S3, "B01")["why"] = "a different observation"
check("changing the reason changes the fingerprint (an approval approves that observation)",
      BP.item_sha(item(S3, "B01")) != BP.item_sha(item(S, "B01")))

# --- what the page refuses ---------------------------------------------------------
S4 = spec(); item(S4, "B01")["proposal"] = ""
# REVERT: drop the proposal check. A line without a proposal hands the person a judgment, which is what the bundle removes.
check("an item without a proposal is refused", "NO_PROPOSAL" in codes(S4))
S4 = spec(); item(S4, "B01")["proposal"] = "HOLD"
check("HOLD is not a proposal", "NO_PROPOSAL" in codes(S4))
S4 = spec(); item(S4, "B01")["proposal"] = "PARTIAL"
check("a proposal that is not an option is refused", "PROPOSAL_NOT_AN_OPTION" in codes(S4))
S4 = spec(); item(S4, "B01")["why"] = " "
# REVERT: drop the reason check. A proposal without its reason cannot be approved - there is nothing to approve.
check("a proposal without its reason is refused", "NO_REASON" in codes(S4))
S4 = spec(); item(S4, "C002")["observed_by"] = ""
# REVERT: drop the observer check. An unseen answer equal to the proposal goes out as an approved observation, and an
# approved observation without Observed_By is refused by every gate (approval.APPROVAL_INCOMPLETE) - after the person
# thought it was sent.
check("a proposal without who made it is refused", "NO_OBSERVER" in codes(S4))
S4 = spec(); item(S4, "B01")["options"] = item(S4, "B01")["options"][:2]
# REVERT: let a question go without HOLD. With no way to say 'not now', the only way off the line is the proposal.
check("an item without HOLD is refused", "NO_HOLD" in codes(S4))
S4 = spec(); item(S4, "B01")["options"][0] = ["DIGITIZE", "read it"]
# REVERT: let an option say nothing about what it writes. The person approves a word, and bundle_route cannot move it.
check("an option that does not say what it writes is refused", "NO_EFFECT" in codes(S4))
S4 = spec(); item(S4, "C002")["options"][1][2] = [{"gate": "identity", "proposal_id": "DOC_D002__p2", "set": {"Read_Route": "MANUAL"}},
                                                  {"gate": "identity", "proposal_id": "DOC_D002__p3", "set": {"Read_Route": "MANUAL"}}]
check("an answer may write to several places (a list of effects)", BP.check_spec(S4, ROOT) == [], BP.check_spec(S4, ROOT))
S4 = spec(); item(S4, "C002")["options"][1][2] = [{"gate": "identity", "proposal_id": "DOC_D002__p2", "set": {"Read_Route": "MANUAL"}},
                                                  {"gate": "identity", "set": {"Read_Route": "MANUAL"}}]
check("every effect of a list is checked", "BAD_EFFECT" in codes(S4))
S4 = spec(); item(S4, "C002")["options"][1][2] = []
check("an empty list of effects says nothing about what it writes", "NO_EFFECT" in codes(S4))
S4 = spec(); item(S4, "B01")["options"][0][2] = {"gate": "spreadsheet", "row": {}}
check("an effect on an unknown gate is refused", "BAD_EFFECT" in codes(S4))
S4 = spec(); del item(S4, "B01")["options"][0][2]["row"]["Disposition"]
check("a disposition effect without the disposition is refused", "BAD_EFFECT" in codes(S4))
S4 = spec(); item(S4, "C002")["options"][0][2] = {"gate": "identity", "set": {"Read_Route": "MANUAL"}}
check("a card effect without its Proposal_ID is refused", "BAD_EFFECT" in codes(S4))
EB = lambda code, quote="": {"gate": "errorbar", "row": {"Source_Document_ID": "DOC", "Draft_ID": "DOC_D001", "Figure_Number": "FIG1",
                                                         "Page": "3", "Dispersion_Type": code, "Errorbar_Definition_Source": quote,
                                                         "Found_On_Page": "4" if quote else ""}}
S4 = spec(); item(S4, "B01")["options"][0][2] = EB("DROP"); item(S4, "B01")["options"][1][2] = EB("NO_ERRORBAR")
# REVERT: demand a quote of every error-bar answer. A figure with bars and no definition, or with no bars, cannot be answered.
check("an error-bar answer that found no definition, or saw no bars, needs no quote", BP.check_spec(S4, ROOT) == [], BP.check_spec(S4, ROOT))
S4 = spec(); item(S4, "B01")["options"][0][2] = EB("SD")
# REVERT: let a dispersion type go without the sentence. The gate refuses it later (NO_ERRORBAR_SOURCE), after a person approved it.
check("an error-bar answer that names a dispersion needs the paper's sentence", "BAD_EFFECT" in codes(S4))
S4 = spec(); item(S4, "B01")["options"][0][2] = EB("DROP", "Values are mean ± SD.")
# REVERT: let DROP carry a quote. The gate refuses DROP_WITH_QUOTE - one of the two is false.
check("an answer that found no definition may not carry one", "BAD_EFFECT" in codes(S4))
import record_errorbar as RE                                     # noqa: E402
check("the quote-free error-bar answers are the gate's own", set(BP.ERRORBAR_WITHOUT_QUOTE) == (set(RE.DISPOSITIONS) - {RE.HOLD}) | {"NO_ERRORBAR"}
      and set(BP.ERRORBAR_NO_QUOTE_ALLOWED) == set(RE.DISPOSITIONS) - {RE.HOLD}, (BP.ERRORBAR_WITHOUT_QUOTE, RE.DISPOSITIONS))
S4 = spec(); item(S4, "C002")["options"][1][2] = {"gate": "identity", "proposal_id": "DOC_D002__p2"}
check("a card effect that changes nothing is refused", "BAD_EFFECT" in codes(S4))
S4 = spec(); item(S4, "C001")["options"][0][2] = {"gate": None, "uses_text": True}
# REVERT: let 'no gate yet' go without naming the path it needs. Approved answers then wait on nothing anyone was told to build.
check("an answer with no gate must name the path it needs", "BAD_EFFECT" in codes(S4))
S4 = spec(); del item(S4, "C001")["text"]; item(S4, "C001")["options"] = [item(S4, "C001")["options"][0], ["HOLD", "hold"]]
check("an option that writes the name, on an item without a name field, is refused", "EDIT_WITHOUT_TEXT" in codes(S4))
S4 = spec(); del item(S4, "C001")["text"]
for o in item(S4, "C001")["options"][:2]:
    o[2] = {"gate": None, "needs": "R4 outcome labels"}
check("an EDIT option on an item without a name field is refused", "EDIT_WITHOUT_TEXT" in codes(S4))
S4 = spec(); item(S4, "B01")["images"][0]["path"] = "gone.png"
# REVERT: skip an image that is not there. The answer would carry no fingerprint for the picture it claims was shown.
check("an image that is not on disk is refused", "IMAGE_MISSING" in codes(S4))
S4 = spec(); S4["sections"][1]["items"][1]["id"] = "C001"
check("two items with one name are refused", "DUPLICATE_ITEM" in codes(S4))
S4 = spec(); item(S4, "B01")["options"].append(["HOLD", "again"])
check("an option listed twice is refused", "OPTION_DUPLICATE" in codes(S4))
S4 = spec(); S4["answers_file"] = "figure_dispositions.csv"
# REVERT: allow the answers file to carry a record's name. The person saves it where the gate writes, and the gate
# reads its own record as answers.
check("an answers file named like a record is refused", "ANSWERS_FILE_IS_A_RECORD" in codes(S4))
S4 = spec(); S4["schema"] = "something/else"
check("another schema is refused", "BAD_SCHEMA" in codes(S4))
S4 = spec(); S4["sections"] = []
check("a bundle with nothing to ask is refused", "NO_ITEMS" in codes(S4))

# --- the command -----------------------------------------------------------------------
bad = spec(); item(bad, "B01")["proposal"] = ""
sp, page, items = os.path.join(ROOT, "bad.json"), os.path.join(ROOT, "bad.html"), os.path.join(ROOT, "bad_items.json")
json.dump(bad, io.open(sp, "w", encoding="utf-8"), ensure_ascii=False)
try:
    BP.main([sp, "--out", page, "--items", items])
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("a refused bundle stops, naming the problem, and writes nothing",
      "NO_PROPOSAL" in stopped and not os.path.exists(page) and not os.path.exists(items), stopped[:120])
sp = os.path.join(ROOT, "good.json")
json.dump(spec(), io.open(sp, "w", encoding="utf-8"), ensure_ascii=False)
BP.main([sp, "--out", page, "--items", items])
got = json.load(io.open(items, encoding="utf-8"))
check("the command writes the page and the item file, images found beside the spec",
      os.path.exists(page) and got["answers_file"] == "bundle_answers.csv" and len(got["items"]) == 3)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
