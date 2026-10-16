# -*- coding: utf-8 -*-
"""Scenarios for bundle_items.py - the questions a census leaves, measured where they can be, and a bundle spec only
when every question has a proposal.

    python3 test_bundle_items.py

The run here is drawn: a panel whose tick pairs sit on the number glyphs six pixels outside the box with the tick
marks inside it, a panel with no marks near its pairs, grey bars, a black bar beside a grey one, a line panel, a
figure with two legends, a drawn and an undrawn panel without an outcome label, open figures.
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
import bundle_items as BI                                        # noqa: E402
import bundle_page as BP                                         # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


try:
    from PIL import Image, ImageDraw
except Exception:                                                 # pragma: no cover
    print("PIL is not installed; this suite draws its run")
    raise

ROOT = tempfile.mkdtemp(prefix="fdt_bundle_items_")
RUN, CEN, PLANS, WORK = [os.path.join(ROOT, n) for n in ("run", "census", "plans", "work")]


def write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields)); w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in fields))


os.makedirs(os.path.join(RUN, "crops"))
# r1: spine at x=100 from y=100 to 400, tick stubs left of it at 100, 250 and 400; the labels '10' and '0' would be
# drawn around rows 94 and 406 - the pairs below are put there, on the glyphs, six pixels from the marks.
im = Image.new("L", (600, 500), 255); d = ImageDraw.Draw(im)
d.rectangle((99, 100, 100, 400), fill=0)
for y in (100, 250, 400):
    d.rectangle((80, y - 1, 98, y + 1), fill=0)
im.save(os.path.join(RUN, "r1.png"))
Image.new("L", (600, 500), 255).save(os.path.join(RUN, "r3.png"))          # no marks at all
# r11: a mark near the upper pair, but the mark itself is 15 px above the box
im = Image.new("L", (600, 500), 255); d = ImageDraw.Draw(im)
d.rectangle((99, 85, 100, 400), fill=0)
for y in (85, 400):
    d.rectangle((80, y - 1, 98, y + 1), fill=0)
im.save(os.path.join(RUN, "r11.png"))
# r12: an empty (outlined) bar beside a grey one - the empty bar's inside cannot be measured
im = Image.new("L", (500, 400), 255); d = ImageDraw.Draw(im)
d.rectangle((130, 150, 170, 350), fill=255, outline=0); d.rectangle((280, 150, 320, 350), fill=215, outline=0)
im.save(os.path.join(RUN, "r12.png"))
# r2: two grey (215) bars; r5: a black bar and a grey bar; r7: a figure of two panels
for name, fills in (("r2.png", (215, 215)), ("r5.png", (0, 215))):
    im = Image.new("L", (500, 400), 255); d = ImageDraw.Draw(im)
    for x, f in zip((150, 300), fills):
        d.rectangle((x - 20, 150, x + 20, 350), fill=f, outline=0)
    im.save(os.path.join(RUN, name))
Image.new("L", (900, 400), 255).save(os.path.join(RUN, "r7.png"))
Image.new("L", (300, 200), 255).save(os.path.join(RUN, "crops", "DOC_D008.png"))
Image.new("L", (300, 200), 255).save(os.path.join(RUN, "r2b.png"))

GF = ("Proposal_ID", "Raster", "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1", "Y_Axis_Spine_X", "Confirmed_Tick_Values",
      "Human_Verification_Status", "Verified_By")
write(os.path.join(RUN, "seg", "geometry600", "geometry_decisions.csv"), GF, [
    {"Proposal_ID": "DOC_D001__p1", "Raster": "r1.png", "Panel_X0": "100", "Panel_X1": "500", "Panel_Y0": "100", "Panel_Y1": "400",
     "Y_Axis_Spine_X": "100", "Confirmed_Tick_Values": "10@94;0@406", "Human_Verification_Status": "CONFIRMED", "Verified_By": "minyeop"},
    {"Proposal_ID": "DOC_D003__p1", "Raster": "r3.png", "Panel_X0": "100", "Panel_X1": "500", "Panel_Y0": "100", "Panel_Y1": "400",
     "Confirmed_Tick_Values": "10@80;0@406", "Human_Verification_Status": "CONFIRMED", "Verified_By": "minyeop"},
    {"Proposal_ID": "DOC_D011__p1", "Raster": "r11.png", "Panel_X0": "100", "Panel_X1": "500", "Panel_Y0": "100", "Panel_Y1": "400",
     "Y_Axis_Spine_X": "100", "Confirmed_Tick_Values": "10@80;0@406", "Human_Verification_Status": "CONFIRMED", "Verified_By": "minyeop"},
    {"Proposal_ID": "DOC_D002__p1", "Raster": "r2b.png", "Panel_X0": "10", "Panel_X1": "200", "Panel_Y0": "10", "Panel_Y1": "150",
     "Human_Verification_Status": "REJECTED", "Verified_By": "minyeop"}])
IF = ("Proposal_ID", "Raster", "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1", "Mark_Type", "X_Labels", "Series_Factor", "Series",
      "Read_Route", "Human_Verification_Status", "Verified_By")
bars = json.dumps([{"label": "a", "px": 150}, {"label": "b", "px": 300}])
write(os.path.join(RUN, "seg", "identity600", "identity_decisions.csv"), IF, [
    {"Proposal_ID": "DOC_D004__p1", "Raster": "r2.png", "Panel_X0": "100", "Panel_X1": "400", "Panel_Y0": "100", "Panel_Y1": "360",
     "Mark_Type": "BAR_MONO", "X_Labels": bars, "Series": json.dumps([{"name": "All", "bar_fill": ""}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D005__p1", "Raster": "r5.png", "Panel_X0": "100", "Panel_X1": "400", "Panel_Y0": "100", "Panel_Y1": "360",
     "Mark_Type": "BAR_MONO", "X_Labels": bars, "Series": json.dumps([{"name": "All", "bar_fill": ""}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D012__p1", "Raster": "r12.png", "Panel_X0": "100", "Panel_X1": "400", "Panel_Y0": "100", "Panel_Y1": "360",
     "Mark_Type": "BAR_MONO", "X_Labels": bars, "Series": json.dumps([{"name": "All", "bar_fill": ""}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D013__p1", "Raster": "r3.png", "Panel_X0": "100", "Panel_X1": "400", "Panel_Y0": "100", "Panel_Y1": "360",
     "Mark_Type": "LINE_MONO", "Series": json.dumps([{"name": "A", "marker": ""}, {"name": "B", "marker": "SQUARE"}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D006__p1", "Raster": "r3.png", "Panel_X0": "100", "Panel_X1": "400", "Panel_Y0": "100", "Panel_Y1": "360",
     "Mark_Type": "LINE_MONO", "Series": json.dumps([{"name": "Mean"}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D007__p1", "Raster": "r7.png", "Panel_X0": "10", "Panel_X1": "400", "Panel_Y0": "10", "Panel_Y1": "390",
     "Mark_Type": "BAR_MONO", "Series_Factor": "GROUP", "Series": json.dumps([{"name": "A", "bar_fill": "SOLID"}]), "Read_Route": "AUTO"},
    {"Proposal_ID": "DOC_D007__p2", "Raster": "r7.png", "Panel_X0": "450", "Panel_X1": "890", "Panel_Y0": "10", "Panel_Y1": "390",
     "Mark_Type": "BAR_MONO", "Series_Factor": "SEX", "Series": json.dumps([{"name": "Male", "bar_fill": "SOLID"}]), "Read_Route": "AUTO"}])
write(os.path.join(RUN, "figure_intake_draft.csv"), ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page", "Figure_Crop"), [
    {"Draft_ID": "DOC_D008", "Source_Document_ID": "DOC", "Figure_Number": "FIG8", "Page": "8", "Figure_Crop": "crops/DOC_D008.png"},
    {"Draft_ID": "DOC_D009", "Source_Document_ID": "DOC", "Figure_Number": "FIG9", "Page": "9", "Figure_Crop": "crops/none.png"},
    {"Draft_ID": "DOC_D010", "Source_Document_ID": "DOC", "Figure_Number": "EXTFIG1", "Page": "10"}])
write(os.path.join(RUN, "figure_dispositions.csv"), ("Draft_ID", "Disposition", "Which_Panels"),
      [{"Draft_ID": "DOC_D009", "Disposition": "PARTIAL", "Which_Panels": "a"}])
write(os.path.join(PLANS, "plan_figures.csv"), ("Draft_ID", "Figure_Number", "Disposition", "Route", "Needs"), [
    {"Draft_ID": "DOC_D008", "Figure_Number": "FIG8", "Disposition": "UNRESOLVED", "Route": "MIXED_CAPTION_NOT_DECIDABLE"},
    {"Draft_ID": "DOC_D009", "Figure_Number": "FIG9", "Disposition": "UNRESOLVED", "Needs": "일부 패널만 — 그 패널만 추출: a"},
    {"Draft_ID": "DOC_D010", "Figure_Number": "EXTFIG1", "Disposition": "ASSOCIATION_EXTRACT", "Route": "ASSOCIATION_ONLY_NOT_TARGET"}])
M = os.path.join(CEN, "man_DOC")
write(os.path.join(M, "panel_manifest.csv"), ("Panel_ID",), [{"Panel_ID": "DOC_D001_P1"}, {"Panel_ID": "DOC_D003_P1"}, {"Panel_ID": "DOC_D011_P1"}])
write(os.path.join(M, "series_manifest.csv"), ("Panel_ID", "Series_ID"), [
    {"Panel_ID": "DOC_D004_P1", "Series_ID": "ALL"}, {"Panel_ID": "DOC_D005_P1", "Series_ID": "ALL"}, {"Panel_ID": "DOC_D006_P1", "Series_ID": "MEAN"},
    {"Panel_ID": "DOC_D012_P1", "Series_ID": "ALL"}, {"Panel_ID": "DOC_D013_P1", "Series_ID": "A"}])
write(os.path.join(M, "source_panel_inventory.csv"), ("Source_Panel_ID", "Source_Figure_ID", "Panel_Disposition"), [
    {"Source_Panel_ID": "DOC_D002_P1", "Source_Figure_ID": "DOC_D002", "Panel_Disposition": "MANUAL_DIGITIZE"},
    {"Source_Panel_ID": "DOC_D002_P2", "Source_Figure_ID": "DOC_D002", "Panel_Disposition": "GEOMETRY_NOT_AUTHORED"},
    {"Source_Panel_ID": "DOC_D008_P1", "Source_Figure_ID": "DOC_D008", "Panel_Disposition": "UNRESOLVED"},
    {"Source_Panel_ID": "DOC_D009_P1", "Source_Figure_ID": "DOC_D009", "Panel_Disposition": "UNRESOLVED"}])
FILL = "a monochrome bar series is told apart by its fill pattern - Bar_Fill_Pattern required"
write(os.path.join(CEN, "out_DOC", "manifest_problems.csv"), ("where", "check", "detail"), [
    {"where": "panels:2", "check": "CALIBRATION_OUTSIDE_PANEL", "detail": "Axis_Y tick pixel(s) [94.0, 406.0] lie outside the panel box"},
    {"where": "panels:3", "check": "CALIBRATION_OUTSIDE_PANEL", "detail": "Axis_Y tick pixel(s) [80.0, 406.0] lie outside the panel box"},
    {"where": "panels:4", "check": "CALIBRATION_OUTSIDE_PANEL", "detail": "Axis_Y tick pixel(s) [80.0] lie outside the panel box"},
    {"where": "series:5", "check": "MISSING_SERIES_DISCRIMINANT", "detail": FILL},
    {"where": "series:6", "check": "MISSING_SERIES_DISCRIMINANT", "detail": "the released LINE_MONO reader separates series by marker shape"},
    {"where": "series:2", "check": "MISSING_SERIES_DISCRIMINANT", "detail": FILL},
    {"where": "series:3", "check": "MISSING_SERIES_DISCRIMINANT", "detail": FILL},
    {"where": "series:4", "check": "MISSING_SERIES_DISCRIMINANT", "detail": "the released LINE_MONO reader separates series by marker shape"},
    {"where": "panels:DOC_D007_P2", "check": "IDENTITY_DOMAIN_FILL_CONFLICT", "detail": "the SOLID fill means SEX=MALE here and GROUP=A in DOC_D007_P1"},
    {"where": "source_panels:2", "check": "MISSING_TARGET_OUTCOME_LABEL", "detail": ""},
    {"where": "source_panels:3", "check": "MISSING_TARGET_OUTCOME_LABEL", "detail": ""},
    {"where": "source_panels:4", "check": "SOURCE_PANEL_UNRESOLVED", "detail": ""},
    {"where": "source_panels:5", "check": "SOURCE_PANEL_UNRESOLVED", "detail": ""},
    {"where": "source_panel:DOC_D010_P1", "check": "SOURCE_PANEL_RUN_LINK_MISSING", "detail": ""}])

Q, TASKS = BI.questions(CEN, RUN, PLANS, WORK, log=lambda *_a: None)

# --- the questions -------------------------------------------------------------------------
check("one question per open figure, label, series, legend and calibration", sorted(Q) == sorted([
    "X:DOC_D008", "X:DOC_D010", "C:DOC_D002__p1", "F:DOC_D004__p1:ALL", "F:DOC_D005__p1:ALL", "M:DOC_D006__p1:MEAN",
    "L:DOC_D007", "K:DOC_D001__p1", "K:DOC_D003__p1", "K:DOC_D011__p1", "F:DOC_D012__p1:ALL", "M:DOC_D013__p1:A"]), sorted(Q))
# REVERT: ask about a figure already disposed. The person answered it; what is left is drawing, not a question.
check("a figure already disposed PARTIAL is a person's task, not a question", "X:DOC_D009" not in Q
      and any("DOC_D009" in t and "PARTIAL" in t for t in TASKS), TASKS)
# REVERT: ask the label of a panel nobody drew. There is no panel yet to name.
check("an undrawn panel without a label is a task, not a question", "C:DOC_D002__p2" not in Q and any("그리지 않은 패널 1개" in t for t in TASKS))
check("a figure's question shows its crop when there is one", Q["X:DOC_D008"]["images"] and not Q["X:DOC_D010"]["images"])
k1 = Q["K:DOC_D001__p1"]
check("the tick pairs on the glyphs are measured onto the marks", k1["machine"]["proposal"] == "PAIRS"
      and k1["options"][0][2]["set"] == {"Confirmed_Tick_Values": "10@100;0@400"}, (k1["machine"], k1["options"][0][2]))
check("the measured proposal says which mark each pair moved to", "왼쪽 눈금" in k1["machine"]["why"] and "가운데" in k1["machine"]["why"])
k11 = Q["K:DOC_D011__p1"]
# REVERT: drop the box tolerance after the move. A pair moved onto a mark that is itself outside the box is still outside it.
check("a pair moved onto a mark that is itself outside the box: PAIRS is offered, BOX proposed", k11["machine"]["proposal"] == "BOX"
      and [o[0] for o in k11["options"]] == ["PAIRS", "BOX"], (k11["machine"], [o[0] for o in k11["options"]]))
k3 = Q["K:DOC_D003__p1"]
# REVERT: propose PAIRS without a mark. The pair would move nowhere and the panel stays outside its box.
check("with no mark near a pair the measured proposal is BOX", k3["machine"]["proposal"] == "BOX"
      and [o[0] for o in k3["options"]] == ["BOX"], (k3["machine"], [o[0] for o in k3["options"]]))
box = k3["options"][-1][2]
# REVERT: write the box as a card field. Neither gate takes a box from an answer, so the widened box would vanish.
check("BOX is a path still to build: the box to draw, and identity confirmed again on it", box.get("gate") is None
      and "y 79–407" in box.get("needs", "") and "정체 다시 확인" in box.get("needs", ""), box)
f4, f5 = Q["F:DOC_D004__p1:ALL"], Q["F:DOC_D005__p1:ALL"]
check("grey bars measure as OPEN, the band the reader sees", f4["machine"]["proposal"] == "OPEN" and f4["table"][3][1:] == ["OPEN", "OPEN"], f4["table"])
# REVERT: propose the first bar's band for all. A black bar and a grey bar are two fills in one series.
check("a black bar beside a grey one is MANUAL", f5["machine"]["proposal"] == "MANUAL" and "SOLID" in f5["machine"]["why"], f5["machine"])
# REVERT: propose from the bars that could be measured. An empty bar is not a measured OPEN; it is not measured.
check("a bar whose inside cannot be measured leaves the question to a look", Q["F:DOC_D012__p1:ALL"]["machine"] is None
      and Q["F:DOC_D012__p1:ALL"]["table"][3][1] == "속 칠 없음")
labels = dict((o[0], o[1]) for o in f4["options"])
# REVERT: label the options by their values alone ("SOLID", "OPEN"). A white-filled bar reads as a solid bar to a
# person, and a person answered SOLID for white bars in the 2026-10-15 bundle; to the reader it is OPEN.
check("each fill option says what the reader means by it: a white fill is OPEN, mixed fills in one series MANUAL",
      "검정" in labels["SOLID"] and "흰색" in labels["OPEN"] and "흰색" not in labels["SOLID"]
      and "x 위치마다 다름" in labels["MANUAL"], labels)
check("the fill options write that series of that card, by the card's own name", f4["options"][2][2] ==
      {"gate": "identity", "proposal_id": "DOC_D004__p1", "series": [{"name": "All", "set": {"bar_fill": "OPEN"}}]})
m6 = Q["M:DOC_D006__p1:MEAN"]
check("a marker question has no measured proposal - it needs a look", m6["machine"] is None)
check("ANY/ANY is offered only on a one-series panel", "ANY/ANY" in [o[0] for o in m6["options"]]
      and "ANY/ANY" not in [o[0] for o in Q["M:DOC_D013__p1:A"]["options"]])
l7 = Q["L:DOC_D007"]
check("two legends: MANUAL writes every panel of the figure", [e["proposal_id"] for e in l7["options"][0][2]] == ["DOC_D007__p1", "DOC_D007__p2"])
check("the fill bands are the reader's", BI.FILL_BANDS == __import__("mark_readers")._FILL_BANDS)

# --- proposals and the spec -------------------------------------------------------------------
spec, todo, problems = BI.merge(Q, TASKS, {})
# REVERT: write the spec with questions unproposed. The page would hand those judgments to the person.
check("without proposals for what needs a look: no spec, and the work list names exactly those",
      spec is None and sorted(t["key"] for t in todo) == ["C:DOC_D002__p1", "F:DOC_D012__p1:ALL", "L:DOC_D007", "M:DOC_D006__p1:MEAN",
                                                          "M:DOC_D013__p1:A", "X:DOC_D008", "X:DOC_D010"],
      sorted(t["key"] for t in todo))
check("the work list carries what to look at", all(t["options"] and t["question"] for t in todo) and
      [t for t in todo if t["key"] == "X:DOC_D008"][0]["images"])
P = {"proposals": {
    "X:DOC_D008": {"proposal": "PARTIAL", "which": "a", "why": "only a is group data", "observed_by": "Claude (PDF)"},
    "X:DOC_D010": {"proposal": "NON_TARGET", "why": "environment", "observed_by": "Claude (PDF)"},
    "C:DOC_D002__p1": {"proposal": "LABEL", "why": "y-axis title", "observed_by": "Claude (label agent)", "text": {"value": "Heart rate", "unit": "bpm"}},
    "M:DOC_D006__p1:MEAN": {"proposal": "MANUAL", "why": "the mean has no marker", "observed_by": "Claude (600 dpi)"},
    "L:DOC_D007": {"proposal": "LEGEND", "why": "a legend per column", "observed_by": "Claude (600 dpi)",
                   "extra_options": [["LEGEND", "split the legend", {"gate": None, "needs": "legend domains"}]]},
    "F:DOC_D004__p1:ALL": {"proposal": "MANUAL", "why": "overlapping individual lines", "observed_by": "Claude (600 dpi)"},
    "F:DOC_D012__p1:ALL": {"proposal": "MANUAL", "why": "an empty bar and a grey one", "observed_by": "Claude (600 dpi)"},
    "M:DOC_D013__p1:A": {"proposal": "CIRCLE/FILLED", "why": "filled circles", "observed_by": "Claude (600 dpi)"}},
    "extra_items": [{"section": "E", "id": "E01", "target": "hashes", "now": "", "proposal": "FIX", "why": "stale", "observed_by": "Claude",
                     "options": [["FIX", "fix", {"gate": None, "needs": "a fix script"}], ["HOLD", "hold"]]}],
    "section_order": ["E"], "notes": ["read me"]}
spec, todo, problems = BI.merge(Q, TASKS, P)
check("with every question proposed there is a spec", spec is not None and todo == [] and problems == [], (todo, problems))
items = dict((it["key"] if "key" in it else it["id"], it) for s in spec["sections"] for it in s["items"])
check("the spec passes the page's own checks and renders", BP.check_spec(spec, WORK) == [] and BP.render(spec, WORK, log=lambda *_a: None)[1]["items"],
      BP.check_spec(spec, WORK))
check("sections in the order asked, then the collector's; ids per section", [s["id"] for s in spec["sections"]] == ["E", "X", "C", "F", "M", "L", "K"]
      and [it["id"] for it in spec["sections"][1]["items"]] == ["X01", "X02"])
check("the person's tasks are the spec's notes", spec["notes"][0] == "read me" and any("DOC_D009" in n for n in spec["notes"]))
x8 = items["X:DOC_D008"]
check("a PARTIAL proposal brings its option, with the panels in the disposition", ["PARTIAL", "일부 패널만 읽음: a (PARTIAL)",
      BI.disp("DOC_D008", "PARTIAL", "a")] in x8["options"])
# REVERT: let Claude's proposal lose to the measured one. A look that saw overlapping lines would be overruled by a grey level.
check("a proposal from a look replaces the measured one, and says who looked", (items["F:DOC_D004__p1:ALL"]["proposal"],
      items["F:DOC_D004__p1:ALL"]["observed_by"]) == ("MANUAL", "Claude (600 dpi)"))
check("a measured proposal says it was measured", (items["F:DOC_D005__p1:ALL"]["proposal"], items["F:DOC_D005__p1:ALL"]["observed_by"])
      == ("MANUAL", BI.MACHINE) and items["K:DOC_D001__p1"]["why"].startswith("짝을"))
check("a name question carries the proposed name", items["C:DOC_D002__p1"]["text"] == {"value": "Heart rate", "unit": "bpm"})
check("every question ends with HOLD", all(it["options"][-1][0] == "HOLD" for s in spec["sections"] for it in s["items"]))
check("an extra option from the proposals is offered", "LEGEND" in [o[0] for o in items["L:DOC_D007"]["options"]])
P2 = json.loads(json.dumps(P)); P2["proposals"]["K:DOC_D999__p1"] = {"proposal": "PAIRS", "why": "x", "observed_by": "y"}
# REVERT: ignore a proposal for a question this census does not ask. It was written against another census.
check("a proposal for a question this census does not ask is refused", "STALE_PROPOSAL" in [c for c, _m in BI.merge(Q, TASKS, P2)[2]])
P2 = json.loads(json.dumps(P)); del P2["proposals"]["X:DOC_D008"]["which"]
check("PARTIAL without the panels is refused", "PARTIAL_WITHOUT_PANELS" in [c for c, _m in BI.merge(Q, TASKS, P2)[2]])
P2 = json.loads(json.dumps(P)); P2["proposals"]["C:DOC_D002__p1"]["text"] = {"value": " ", "unit": ""}
check("a name proposed without the name is refused", "LABEL_WITHOUT_TEXT" in [c for c, _m in BI.merge(Q, TASKS, P2)[2]])

# --- the command -----------------------------------------------------------------------------
sp = os.path.join(WORK, "spec.json")
rc = BI.main(["--census", CEN, "--run", RUN, "--plans", PLANS, "--work", WORK, "--spec", sp])
check("the command without proposals exits 2, writes the work list and no spec", rc == 2 and os.path.exists(os.path.join(WORK, "todo.json"))
      and not os.path.exists(sp))
pp = os.path.join(ROOT, "proposals.json")
json.dump(P, io.open(pp, "w", encoding="utf-8"), ensure_ascii=False)
rc = BI.main(["--census", CEN, "--run", RUN, "--plans", PLANS, "--work", WORK, "--spec", sp, "--proposals", pp])
check("with the proposals it writes the spec", rc == 0 and json.load(io.open(sp, encoding="utf-8"))["schema"] == BP.SCHEMA)
json.dump(P2, io.open(pp, "w", encoding="utf-8"), ensure_ascii=False)
os.remove(sp)
rc = BI.main(["--census", CEN, "--run", RUN, "--plans", PLANS, "--work", WORK, "--spec", sp, "--proposals", pp])
check("refused proposals stop the command with no spec", rc == 1 and not os.path.exists(sp))
P3 = json.loads(json.dumps(P)); P3["proposals"]["X:DOC_D010"]["proposal"] = "SOMETHING"
json.dump(P3, io.open(pp, "w", encoding="utf-8"), ensure_ascii=False)
rc = BI.main(["--census", CEN, "--run", RUN, "--plans", PLANS, "--work", WORK, "--spec", sp, "--proposals", pp])
# REVERT: skip the page's checks before writing. A spec the page will refuse would be written as if done.
check("a proposal the page would refuse (not an option) stops the command", rc == 1 and not os.path.exists(sp))

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
