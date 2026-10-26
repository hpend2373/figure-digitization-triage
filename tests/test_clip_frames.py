# -*- coding: utf-8 -*-
"""Scenarios for clip_frames.py (a drawn frame a few pixels past the picture, cut back on both cards).

    python3 tests/test_clip_frames.py

Each scenario is a way a clip could change more than the pixels outside the picture: one card moved and
not the other, a person's confirmation lost or rewritten, a stale proposal riding in on the re-record,
a clip nobody saw, or a half-written run when one gate says no.
"""
import _paths  # noqa: E402,F401  (puts fdt/ on sys.path)
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clip_frames as C                                          # noqa: E402
import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import record_geometry as RG                                     # noqa: E402
import record_identity as RI                                     # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_clip_frames_")
GDIR, IDIR = os.path.join("seg", "geometry"), os.path.join("seg", "identity")
LABELS = json.dumps([{"label": "Pre", "px": 175}, {"label": "D1", "px": 325}])
SERIES = json.dumps([{"name": "Fluid", "colour": "", "line_style": "", "marker": "", "marker_fill": "", "bar_fill": "SOLID"},
                     {"name": "Control", "colour": "", "line_style": "", "marker": "", "marker_fill": "", "bar_fill": "HATCHED"}])
SEEN = {"Verified_By": "minyeop", "Seen_By_Person": "1"}


def build(run, drawn="20,503,10,280", inside="20,480,10,280", ident_seen=None):
    """A run with two panels on one 500x300 picture: GP001 drawn 3 px past the right edge, GP002 inside."""
    if os.path.exists(run):
        shutil.rmtree(run)
    os.makedirs(os.path.join(run, "seg", "regions"))
    os.makedirs(os.path.join(run, GDIR))
    os.makedirs(os.path.join(run, IDIR))
    Image.new("RGB", (500, 300), "white").save(os.path.join(run, "seg", "regions", "fig.png"))
    base = dict((c, "") for c in GP.PROPOSAL_COLUMNS)
    base.update({"Raster": "seg/regions/fig.png", "Region": "0,0,500,300", "Panel_X0": "30", "Panel_X1": "470",
                 "Panel_Y0": "15", "Panel_Y1": "270", "Human_Verification_Status": GP.PROPOSAL_PENDING})
    GP.write_proposals(os.path.join(run, GDIR, RG.PROPOSALS), [dict(base, Proposal_ID="GP001"), dict(base, Proposal_ID="GP002")])
    geo = [dict(SEEN, Proposal_ID=pid, Human_Verification_Status="CONFIRMED", Y_Tick_Top_Value="30", Y_Tick_Bottom_Value="0",
                Confirmed_Tick_Values="30@20;0@260", Drawn_Frame=frame, Note="첫 확인")
           for pid, frame in (("GP001", drawn), ("GP002", inside))]
    w, r, _p = RG.record(os.path.join(run, GDIR), geo, "2026-09-23", log=lambda *_a: None)
    assert len(w) == 2 and not r, r
    ip = dict((c, "") for c in IP.IDENTITY_COLUMNS)
    ip.update({"Raster": "seg/regions/fig.png", "Region": "0,0,500,300", "Panel_Kind": "BAR", "Outcome_Read": "Heart rate",
               "Mark_Type_Proposed": "BAR_MONO", "Human_Verification_Status": IP.PENDING})
    rows = []
    for pid, frame in (("GP001", drawn), ("GP002", inside)):
        x0, x1, y0, y1 = frame.split(",")
        rows.append(dict(ip, Proposal_ID=pid, Panel_X0=x0, Panel_X1=x1, Panel_Y0=y0, Panel_Y1=y1))
    IP.write_proposals(os.path.join(run, IDIR, RI.PROPOSALS), rows)
    ident = [dict(SEEN, Proposal_ID=pid, Human_Verification_Status="CONFIRMED", X_Factor="TIMEPOINT", X_Labels=LABELS,
                  Series_Factor="ARM", Series=SERIES, Mark_Type="BAR_MONO", Outcome_Name="Heart rate", Unit="bpm",
                  N_Outcome="8", Bar_Top_Definition="OUTLINE_CENTER", Errorbar_Stem_Confirmed="TRUE", Read_Route="AUTO",
                  Note="첫 확인") for pid in ("GP001", "GP002")]
    if ident_seen:
        ident[0].update(ident_seen)
    w, r, _p = RI.record(os.path.join(run, IDIR), ident, "2026-09-23", log=lambda *_a: None)
    assert len(w) == 2 and not r, r
    return run


def cards(run):
    g = dict((r["Proposal_ID"], r) for r in C.rd(os.path.join(run, GDIR, RG.DECISIONS)))
    i = dict((r["Proposal_ID"], r) for r in C.rd(os.path.join(run, IDIR, RI.DECISIONS)))
    return g, i


def digest(run):
    out = {}
    for d, _s, files in os.walk(run):
        for f in files:
            out[os.path.relpath(os.path.join(d, f), run)] = hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
    return out


def clip(run, answers, when="2026-10-16"):
    todo, refused = C.plan(run, answers, GDIR, IDIR)
    if refused:
        return [], [], refused
    return C.apply(run, todo, when, GDIR, IDIR, log=lambda *_a: None)


def codes(refused):
    return sorted(c for _n, ps in refused for c, _m in ps)


def ans(pid="GP001", **kw):
    return dict(SEEN, Proposal_ID=pid, Note="", **kw)


# --- the clip ---------------------------------------------------------------------------
check("clipped() cuts only what is outside the picture", C.clipped([-4, 503, 10, 302], (500, 300)) == [0, 500, 10, 300]
      and C.clipped([20, 480, 10, 280], (500, 300)) == [20, 480, 10, 280])
RUN = build(os.path.join(ROOT, "run"))
g0, i0 = cards(RUN)
before = digest(RUN)
gw, iw, bad = clip(RUN, [ans()])
g1, i1 = cards(RUN)
# REVERT: clip one card only. make_plan reads identity only on the frame geometry stands on, and the panel would drop out.
check("both cards stand on the clipped frame", not bad and [C.frame_of(g1["GP001"]), C.frame_of(i1["GP001"])] == [[20, 500, 10, 280]] * 2,
      (bad, C.frame_of(g1["GP001"]), C.frame_of(i1["GP001"])))
check("the axis strip follows the frame", g1["GP001"]["Axis_X_Region"] == "20,500,280,300", g1["GP001"]["Axis_X_Region"])
check("the identity proposal row is clipped too, so the next re-record does not put the pixels back",
      [r["Panel_X1"] for r in C.rd(os.path.join(RUN, IDIR, RI.PROPOSALS)) if r["Proposal_ID"] == "GP001"] == ["500"])
check("... and the original proposal file is kept beside it",
      [r["Panel_X1"] for r in C.rd(os.path.join(RUN, IDIR, RI.PROPOSALS + ".before_clip_2026-10-16"))
       if r["Proposal_ID"] == "GP001"] == ["503"])
# REVERT: rebuild the answer from the proposal. The person's ticks, series and outcome would be the reader's again.
check("the person's geometry is carried unchanged", all(g1["GP001"][k] == g0["GP001"][k] for k in C.GEOMETRY_CARRY),
      [(k, g0["GP001"][k], g1["GP001"][k]) for k in C.GEOMETRY_CARRY if g1["GP001"][k] != g0["GP001"][k]])
check("the person's identity is carried unchanged", all(i1["GP001"][k] == i0["GP001"][k] for k in C.IDENTITY_CARRY),
      [(k, i0["GP001"][k], i1["GP001"][k]) for k in C.IDENTITY_CARRY if i1["GP001"][k] != i0["GP001"][k]])
check("nothing outside the frame, the axis strip and the record's who/when changed on either card",
      not C._drift(g0["GP001"], g1["GP001"]) and not C._drift(i0["GP001"], i1["GP001"]))
# REVERT: drop the original verification from the note. The card would read as first confirmed on the clip date.
check("the card says what was clipped and who first confirmed it, and keeps its old note",
      all("[20, 503, 10, 280] -> [20, 500, 10, 280]" in c["Note"] and "원래 확인: minyeop 2026-09-23 (본 답)" in c["Note"]
          and "첫 확인" in c["Note"] for c in (g1["GP001"], i1["GP001"])), g1["GP001"]["Note"])
check("the clip is dated on the day it was decided", g1["GP001"]["Verified_At"] == i1["GP001"]["Verified_At"] == "2026-10-16")
check("the panel inside the picture is not touched", g1["GP002"] == g0["GP002"] and i1["GP002"] == i0["GP002"])
after = digest(RUN)
check("nothing else in the run changed", sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
      == sorted([os.path.join(GDIR, RG.DECISIONS), os.path.join(IDIR, RI.DECISIONS), os.path.join(IDIR, RI.PROPOSALS),
                 os.path.join(IDIR, RI.PROPOSALS + ".before_clip_2026-10-16")]))
# REVERT: drop the NOTHING_TO_CLIP check. A second run would re-date a confirmation that did not change.
check("a frame already inside the picture is refused, not re-recorded", codes(clip(RUN, [ans()])[2]) == ["NOTHING_TO_CLIP"])

RUN = build(os.path.join(ROOT, "run"))
gw, iw, bad = clip(RUN, [ans(Seen_By_Person="0", Observed_By="Claude (clip_frames)", Approval_Ref="bundle E02: minyeop 2026-10-16")])
g1, i1 = cards(RUN)
check("an approved clip is recorded as one, on both cards", not bad and all(
    (c["Seen_By_Person"], c["Observed_By"], c["Approval_Ref"]) == ("0", "Claude (clip_frames)", "bundle E02: minyeop 2026-10-16")
    for c in (g1["GP001"], i1["GP001"])), bad)
R3 = {"Seen_By_Person": "0", "Observed_By": "Claude (rule R3)", "Approval_Ref": "chat 2026-10-14"}
# REVERT: let the clip's provenance replace the card's. A card whose series a rule changed would read as seen by a person.
RUN = build(os.path.join(ROOT, "run"), ident_seen=R3)
gw, iw, bad = clip(RUN, [ans()])
g1, i1 = cards(RUN)
check("a card that was an approved observation stays one when a person sees the clip",
      not bad and (i1["GP001"]["Seen_By_Person"], i1["GP001"]["Observed_By"], i1["GP001"]["Approval_Ref"])
      == ("0", "Claude (rule R3)", "chat 2026-10-14") and g1["GP001"]["Seen_By_Person"] == "1", (bad, i1.get("GP001", {}).get("Seen_By_Person")))
check("... and its note says how it was first confirmed", "(승인된 관찰: Claude (rule R3))" in i1["GP001"]["Note"], i1["GP001"]["Note"])
RUN = build(os.path.join(ROOT, "run"), ident_seen=R3)
gw, iw, bad = clip(RUN, [ans(Seen_By_Person="0", Observed_By="Claude (clip_frames)", Approval_Ref="bundle E02")])
i1 = cards(RUN)[1]
check("an approved observation clipped by an approved clip carries both observers and both approvals",
      not bad and (i1["GP001"]["Observed_By"], i1["GP001"]["Approval_Ref"])
      == ("Claude (rule R3) ; Claude (clip_frames)", "chat 2026-10-14 ; bundle E02"), (bad, i1.get("GP001", {}).get("Observed_By")))
RUN = build(os.path.join(ROOT, "run"))
rows = C.rd(os.path.join(RUN, GDIR, RG.DECISIONS))
for r in rows:
    r["Seen_By_Person"] = ""
GP.write_proposals(os.path.join(RUN, GDIR, RG.DECISIONS), rows)
gw, iw, bad = clip(RUN, [ans()])
g1 = cards(RUN)[0]
check("a card from before the provenance column is read as the seen answer its gate took, and says so",
      not bad and g1["GP001"]["Seen_By_Person"] == "1" and "(본 답, 이 칸이 생기기 전 기록)" in g1["GP001"]["Note"], bad)


def refused_untouched(name, answers, expect, run=None):
    run = run or build(os.path.join(ROOT, "run"))
    was = digest(run)
    got = codes(clip(run, answers)[2])
    check(name, expect in got and digest(run) == was, (got, sorted(k for k in digest(run) if digest(run)[k] != was.get(k))))


# REVERT: drop the seen/approved check. A clip nobody looked at would re-date a person's confirmation.
refused_untouched("a clip neither seen nor approved is refused and nothing is written", [ans(Seen_By_Person="")], "NOT_SEEN_BY_PERSON")
refused_untouched("a panel with no cards is refused", [ans("GP009")], "MISSING_CARD")
RUN = build(os.path.join(ROOT, "run"))
os.remove(os.path.join(RUN, "seg", "regions", "fig.png"))
refused_untouched("a picture that is not there is refused (its size is the clip)", [ans()], "RASTER_MISSING", RUN)
# REVERT: drop the CARDS_DISAGREE check. Identity confirmed on another frame would be re-recorded onto this one.
RUN = build(os.path.join(ROOT, "run"))
rows = C.rd(os.path.join(RUN, IDIR, RI.DECISIONS))
for r in rows:
    if r["Proposal_ID"] == "GP001":
        r["Panel_X0"] = "25"
IP.write_proposals(os.path.join(RUN, IDIR, RI.DECISIONS), rows)
refused_untouched("cards on different frames are refused", [ans()], "CARDS_DISAGREE", RUN)
# REVERT: drop the drift check. A proposal re-made after the card was written would ride in on the re-record.
RUN = build(os.path.join(ROOT, "run"))
rows = C.rd(os.path.join(RUN, IDIR, RI.PROPOSALS))
for r in rows:
    r["Outcome_Read"] = "Stroke volume"
IP.write_proposals(os.path.join(RUN, IDIR, RI.PROPOSALS), rows)
refused_untouched("a proposal re-made since the card was written is refused, nothing written", [ans()], "PROPOSAL_DRIFTED", RUN)
# REVERT: drop the other-card check. Re-writing the file through the gate would quietly reshape cards nobody clipped.
RUN = build(os.path.join(ROOT, "run"))
path = os.path.join(RUN, GDIR, RG.DECISIONS)
rows = C.rd(path)
with io.open(path, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ["Old_Column"])
    w.writeheader()
    for r in rows:
        w.writerow(dict(r, Old_Column="kept"))
refused_untouched("a re-write that would change a card nobody clipped is refused", [ans()], "OTHER_CARD_CHANGED", RUN)
# A gate saying no in the rehearsal: the geometry card's shared axis points at a panel the gate cannot find confirmed.
RUN = build(os.path.join(ROOT, "run"))
rows = C.rd(os.path.join(RUN, GDIR, RG.DECISIONS))
for r in rows:
    if r["Proposal_ID"] == "GP001":
        r.update(Human_Verification_Status="SHARED", Y_Axis_Shared_With="GP404", Y_Tick_Top_Value="", Y_Tick_Bottom_Value="")
GP.write_proposals(os.path.join(RUN, GDIR, RG.DECISIONS), rows)
refused_untouched("a gate's refusal in the rehearsal stops the clip, nothing written", [ans()], "SHARED_TARGET_UNKNOWN", RUN)
# REVERT: let a gate's stop escape. The command would die mid-way with the run half-checked and no refusal listed.
RUN = build(os.path.join(ROOT, "run"))
rows = C.rd(os.path.join(RUN, GDIR, RG.DECISIONS))
for r in rows:
    if r["Proposal_ID"] == "GP001":
        r.update(Human_Verification_Status="SHARED", Y_Axis_Shared_With="GP002")
GP.write_proposals(os.path.join(RUN, GDIR, RG.DECISIONS), rows)
refused_untouched("a gate that stops on the whole file is a refusal, nothing written", [ans()], "GATE_STOPPED", RUN)

# --- the command line -------------------------------------------------------------------
RUN = build(os.path.join(ROOT, "run"))
ap = os.path.join(ROOT, "clip_answers.csv")


def write_answers(rows):
    with io.open(ap, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


argv = ["--run", RUN, "--answers", ap, "--when", "2026-10-16", "--geometry-dir", GDIR, "--identity-dir", IDIR]
write_answers([ans(Seen_By_Person="")])
check("the command refuses an unseen clip with exit 1", C.main(argv) == 1 and C.frame_of(cards(RUN)[0]["GP001"])[1] == 503)
write_answers([ans()])
check("... and clips a seen one with exit 0", C.main(argv) == 0 and C.frame_of(cards(RUN)[0]["GP001"])[1] == 500)
check("... and says no (exit 1) when there is nothing left to clip", C.main(argv) == 1)
write_answers([{"Proposal_ID": "GP001"}])
try:
    C.main(argv)
    stopped = ""
except SystemExit as exc:
    stopped = str(exc)
check("an answers file without who saw it stops, naming the column", "Verified_By" in stopped, stopped)

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
