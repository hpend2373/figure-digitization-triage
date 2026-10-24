# -*- coding: utf-8 -*-
"""Scenarios for move_panels.py - drawn panels whose crop held another figure, moved to that figure with their cards.

    python3 test_move_panels.py

Every scenario is a way a move could leave the records disagreeing with each other: a box under the new figure and
its card under the old name, a shared axis still pointing at the old name, an outcome left behind, a move across
papers, onto a figure someone already drew, over a name already taken, or half-written.
"""
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_plan as MP                                           # noqa: E402
import move_panels as MV                                         # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_move_panels_")
A, B, C = "DOC_D004", "DOC_D005", "OTHER_D001"


def w(run, rel, fields, rows):
    path = os.path.join(run, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        for r in rows:
            wr.writerow(dict((k, r.get(k, "")) for k in fields))


def rows(run, rel):
    return list(csv.DictReader(io.open(os.path.join(run, rel), encoding="utf-8-sig")))


def make_run(name, extra=None):
    run = os.path.join(ROOT, name)
    if os.path.exists(run):
        shutil.rmtree(run)
    os.makedirs(run)
    w(run, MV.DRAFT, ("Draft_ID", "Source_Document_ID", "Figure_Number"),
      [{"Draft_ID": A, "Source_Document_ID": "DOC", "Figure_Number": "FIG4"},
       {"Draft_ID": B, "Source_Document_ID": "DOC", "Figure_Number": "FIG5"},
       {"Draft_ID": C, "Source_Document_ID": "OTHER", "Figure_Number": "FIG1"}])
    w(run, MV.PANEL_DECISIONS, ("Draft_ID", "Panel_Index", "X0", "Mark_Type", "Crop_SHA256", "Verdict", "Verified_By",
                                "Verified_At", "Note"),
      [{"Draft_ID": A, "Panel_Index": str(i), "X0": str(100 * i), "Mark_Type": "BAR", "Crop_SHA256": "aaa",
        "Verdict": "PANELS", "Verified_By": "minyeop", "Verified_At": "2026-09-13"} for i in (1, 2, 3, 4)]
      + [{"Draft_ID": B, "Panel_Index": "0", "Crop_SHA256": "bbb", "Verdict": "NO_PANELS", "Verified_By": "minyeop",
          "Verified_At": "2026-09-13"}])
    w(run, MV.REGIONS, ("Draft_ID", "Panel_Index", "Raster_600", "Region_600"),
      [{"Draft_ID": A, "Panel_Index": str(i), "Raster_600": "seg/regions600/%s_600.png" % A, "Region_600": "%d,0,9,9" % i}
       for i in (1, 2, 3, 4)])
    for d, kind in (("geometry600", "geometry"), ("identity600", "identity")):
        for f in ("%s_decisions.csv" % kind, "%s_proposal.csv" % kind):
            w(run, os.path.join("seg", d, f), ("Proposal_ID", "Raster", "Human_Verification_Status", "Y_Axis_Shared_With",
                                               "Outcome_Name", "Note"),
              [{"Proposal_ID": "%s__p%d" % (A, i), "Raster": "seg/regions600/%s_600.png" % A,
                "Human_Verification_Status": "CONFIRMED", "Y_Axis_Shared_With": ("%s__p2" % A) if i == 4 else "",
                "Outcome_Name": "Outcome %d" % i} for i in (1, 2, 3, 4)])
        open(os.path.join(run, "seg", d, "%s__p2.png" % A), "wb").write(b"png-p2-" + kind.encode())
    w(run, MV.OUTCOMES, ("Panel_ID", "Draft_ID", "Panel_Index", "Decision", "Outcome_Label", "Note"),
      [{"Panel_ID": "%s_P2" % A, "Draft_ID": A, "Panel_Index": "2", "Decision": "LABEL", "Outcome_Label": "SBP variability"},
       {"Panel_ID": "%s_P1" % A, "Draft_ID": A, "Panel_Index": "1", "Decision": "LABEL", "Outcome_Label": "IBI"}])
    if extra:
        extra(run)
    return run


def fingerprint(run):
    out = {}
    for d, _dirs, files in os.walk(run):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, run)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def go(run, *extra, panels="2,4", src=A, dst=B, ref="remaining_answers.csv R01 MOVE: minyeop"):
    return MV.main(["--run", run, "--from", src, "--panels", panels, "--to", dst, "--when", "2026-10-18",
                    "--approval-ref", ref] + list(extra))


def refused(run, **kw):
    before = fingerprint(run)
    try:
        go(run, "--write", **kw)
        code = ""
    except MV.Refused as exc:
        code = exc.code
    return code, fingerprint(run) == before


# --- looking first -----------------------------------------------------------------------------------------
print("dry run")
R0 = make_run("dry")
before = fingerprint(R0)
rc = go(R0, "--log", os.path.join(ROOT, "dry.json"))
log = json.load(io.open(os.path.join(ROOT, "dry.json"), encoding="utf-8"))
# REVERT: write without --write. A move is looked at before it is made.
check("without --write nothing changes, and the plan names every file it would touch",
      rc == 0 and fingerprint(R0) == before and log["written"] is False
      and set(log["files"]) >= {MV.PANEL_DECISIONS, MV.REGIONS, MV.OUTCOMES,
                                os.path.join("seg", "geometry600", "geometry_decisions.csv"),
                                os.path.join("seg", "identity600", "identity_proposal.csv")}, log)

# --- the move ------------------------------------------------------------------------------------------------
print("move")
R1 = make_run("move")
go(R1, "--write")
pd = rows(R1, MV.PANEL_DECISIONS)
check("the drawn boxes move: the source keeps P1·P3, the target gets P1·P2 in the order given",
      sorted((r["Draft_ID"], r["Panel_Index"], r["X0"]) for r in pd if r["Verdict"] == "PANELS")
      == sorted([(A, "1", "100"), (A, "3", "300"), (B, "1", "200"), (B, "2", "400")]),
      [(r["Draft_ID"], r["Panel_Index"], r["X0"]) for r in pd])
# REVERT: keep the target's 'no panels' row. The figure would say it has no panels and two panels at once.
check("the target's 'no panels' row goes, since it now has panels", not [r for r in pd if r["Draft_ID"] == B and r["Verdict"] == "NO_PANELS"])
check("each moved box says where it came from and who decided",
      all("moved from %s P" % A in r["Note"] and "R01 MOVE" in r["Note"] for r in pd if r["Draft_ID"] == B))
rg = rows(R1, MV.REGIONS)
check("the 600 DPI regions move with their boxes, the raster path unchanged",
      sorted((r["Draft_ID"], r["Panel_Index"], r["Region_600"]) for r in rg if r["Draft_ID"] == B)
      == [(B, "1", "2,0,9,9"), (B, "2", "4,0,9,9")] and all(r["Raster_600"].endswith("%s_600.png" % A) for r in rg))
for d, kind in (("geometry600", "geometry"), ("identity600", "identity")):
    for f in ("%s_decisions.csv" % kind, "%s_proposal.csv" % kind):
        cards = dict((r["Proposal_ID"], r) for r in rows(R1, os.path.join("seg", d, f)))
        # REVERT: rename only the decision files. A later --replace rebuilds the card from its proposal row, and the
        # proposal would still be under the old name.
        check("%s: the cards are renamed, values untouched" % f,
              sorted(cards) == sorted(["%s__p1" % A, "%s__p3" % A, "%s__p1" % B, "%s__p2" % B])
              and cards["%s__p1" % B]["Outcome_Name"] == "Outcome 2" and cards["%s__p2" % B]["Outcome_Name"] == "Outcome 4",
              sorted(cards))
        # REVERT: rename the Proposal_ID only. The shared axis would point at a card that no longer exists.
        check("%s: a card naming a moved card (a shared axis) names it by its new name" % f,
              cards["%s__p2" % B]["Y_Axis_Shared_With"] == "%s__p1" % B, cards["%s__p2" % B]["Y_Axis_Shared_With"])
    check("%s: the overlay is copied under the new name, the old one kept" % d,
          open(os.path.join(R1, "seg", d, "%s__p1.png" % B), "rb").read() == b"png-p2-" + kind.encode()
          and os.path.exists(os.path.join(R1, "seg", d, "%s__p2.png" % A)))
oc = dict((r["Panel_ID"], r) for r in rows(R1, MV.OUTCOMES))
# REVERT: leave the outcome file. The moved panel would lose its name and the old name would name nothing.
check("the outcome name moves with its panel; one not moved stays",
      ("%s_P1" % B) in oc and (oc["%s_P1" % B]["Draft_ID"], oc["%s_P1" % B]["Panel_Index"], oc["%s_P1" % B]["Outcome_Label"])
      == (B, "1", "SBP variability") and ("%s_P2" % A) not in oc and ("%s_P1" % A) in oc, sorted(oc))
geometry, identity, regions, drawn = MP.load_confirmations(R1)
check("make_plan reads the target as a figure with two drawn panels and their confirmed cards",
      [r["Panel_Index"] for r in drawn[B] if r["Verdict"] == "PANELS"] == ["1", "2"]
      and "%s__p1" % B in geometry and "%s__p2" % B in identity and [r["Panel_Index"] for r in regions[B]] == ["1", "2"])
check("... and the source as a figure with the two it kept",
      [r["Panel_Index"] for r in drawn[A]] == ["1", "3"] and "%s__p2" % A not in geometry)
code, same = refused(R1)
# REVERT: allow moving panels that are not there. A second run would 'move' nothing and report success.
check("the same move again is refused: those panels are no longer the source's", code == "NO_SUCH_PANEL" and same, code)

# --- refusals --------------------------------------------------------------------------------------------------
print("refusals")
# REVERT: drop the same-draft check.
check("onto itself", refused(make_run("same"), dst=A) == ("SAME_DRAFT", True))
# REVERT: drop the document check. A panel would be credited to another paper's figure.
check("across papers", refused(make_run("other"), dst=C) == ("OTHER_DOCUMENT", True))
check("a panel the source does not have", refused(make_run("missing"), panels="2,9") == ("NO_SUCH_PANEL", True))
check("one panel twice", refused(make_run("twice"), panels="2,2") == ("NO_SUCH_PANEL", True))


def target_drawn(run):
    with io.open(os.path.join(run, MV.PANEL_DECISIONS), "a", encoding="utf-8", newline="") as fh:
        fh.write("%s,1,10,BAR,bbb,PANELS,minyeop,2026-10-01,\n" % B)


# REVERT: move onto drawn panels. The two sets would share numbers, or interleave.
check("onto a figure someone already drew", refused(make_run("drawn", target_drawn)) == ("TARGET_HAS_PANELS", True))


def card_taken(run):
    with io.open(os.path.join(run, "seg", "identity600", "identity_proposal.csv"), "a", encoding="utf-8", newline="") as fh:
        fh.write("%s__p1,x,PENDING,,,\n" % B)


# REVERT: overwrite a card already under the new name.
check("over a card name already taken", refused(make_run("taken", card_taken)) == ("ID_TAKEN", True))


def outcome_taken(run):
    with io.open(os.path.join(run, MV.OUTCOMES), "a", encoding="utf-8", newline="") as fh:
        fh.write("%s_P2,%s,2,NON_TARGET,,\n" % (B, B))


check("over an outcome name already taken", refused(make_run("otaken", outcome_taken)) == ("ID_TAKEN", True))


def overlay_taken(run):
    open(os.path.join(run, "seg", "geometry600", "%s__p1.png" % B), "wb").write(b"other")


check("over an overlay file already there", refused(make_run("ovtaken", overlay_taken)) == ("ID_TAKEN", True))


def legends(run):
    w(run, MV.LEGENDS, ("Draft_ID", "Legend_Groups"), [{"Draft_ID": A, "Legend_Groups": "p1,p3|p2,p4"}])


# REVERT: move under a legend grouping. 'p2,p4' would name panels the figure no longer has.
check("from a figure with legend groups", refused(make_run("legend", legends)) == ("LEGENDS", True))
# REVERT: move without saying who decided.
check("without an approval reference", refused(make_run("noref"), ref=" ") == ("NO_APPROVAL", True))

shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
