# -*- coding: utf-8 -*-
"""What the gallery in `png/verify.py` actually produced, asserted.

    python3 test_visual_verification.py     # exit 0 = all scenarios pass

The gallery draws the reader back onto the figure it read. Until this file
existed its only output was four PNGs, checked by a person looking at them - so
a reader that started answering about the neighbouring bar would have produced a
picture nobody was comparing with anything, and CI would have stayed green
because CI never ran it.

THE NUMBERS IT IS COMPARED WITH ARE NOT IN THIS FILE. They are in
`verification_truth.json`, and the SHA-256 below pins it: changing a truth value
and changing this constant are one diff, which is the property that makes the
comparison auditable. They were literals inside `png/verify.py`, where a drift
could be absorbed by editing the thing it was measured against.

WHAT IS ASSERTED IS PROVENANCE, NOT ONLY AGREEMENT. `397|FIG1` reads eighteen
cells and the package prices seven of them R4 - a number exists and the review
gate will not take it. A suite that asserted only "eighteen cells agree with the
eye" would pass while that mix silently changed, and the mix is the finding.

Both halves are gated, separately and for the same reason: the publisher rasters
and the 187-figure corpus are not in this repository.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "png"))
import raster_root as RR                                          # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def done():
    print()
    print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
    print("%d scenarios run" % PASSED[0])
    if FAILURES:
        print("%d FAILED: %r" % (len(FAILURES), FAILURES))
        raise SystemExit(1)
    print("all scenarios passed")
    raise SystemExit(0)


#: The truth file this suite was written against.
TRUTH_SHA256 = "2424e511e5d2e21701e07b7ce212ca2dded51d0747355e0a6c048235ccbf3fbc"

_rasters = all(RR.check("397_fig%d.jpeg" % n)[0] for n in (1, 3))
if not _rasters:
    print(RR.skip_note("397_fig3.jpeg"))
    print("  the gallery reads publisher figures; there is nothing to assert")
    print("FDT_SCENARIOS_RUN=0")
    raise SystemExit(0)

import verify as V                                                # noqa: E402

# ONE GATE, NOT TWO. The segmentation half needs the corpus and the reading half
# needs the five rasters, and both come from the same private source - so this
# file runs all of its scenarios or none of them. Gating the two halves
# separately would give this suite THREE counts for two declared environments,
# and the count check downstream would then be comparing a number against an
# environment nobody named.
_missing = V.corpus_missing()
if _missing:
    print(RR.corpus_note(*_missing))
    print("  the segmentation scenarios need it, and this suite runs whole")
    print("FDT_SCENARIOS_RUN=0")
    raise SystemExit(0)

print("the file the readings are compared with is the one this suite pins")
_got = hashlib.sha256(open(V.TRUTH_PATH, "rb").read()).hexdigest()
check("verification_truth.json hashes what this suite declares",
      _got == TRUTH_SHA256, "%s..." % _got[:16])
# AND IT CLAIMS NOTHING IT MAY NOT CLAIM. An eye reading is not an attestation:
# no reviewer, no ORCID, no inspection date. A truth file that grew one would be
# a confirmation nobody signed, recorded by the thing being checked.
import json                                                       # noqa: E402
_doc = json.load(open(V.TRUTH_PATH, encoding="utf-8"))


def _keys(node):
    """Every field name in the document, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key).lower()
            for inner in _keys(value):
                yield inner
    elif isinstance(node, list):
        for value in node:
            for inner in _keys(value):
                yield inner


# KEYS, NOT TEXT. The first draft searched the whole serialised document, and
# the sentence explaining that no reviewer is recorded contains the word
# "reviewer" - a check that fires on its own explanation. What may not exist is
# a FIELD: a truth file that grew one would be a confirmation nobody signed,
# recorded by the thing being checked.
_fields = set(_keys(_doc))
_forbidden = sorted(f for f in _fields
                    if any(t in f for t in ("reviewer", "orcid", "attestation",
                                            "inspection", "confirmed",
                                            "signature")))
check("  and it carries no reviewer, attestation or confirmation FIELD",
      _doc["status"] == "UNATTESTED_APPROXIMATE" and not _forbidden,
      "status %s, fields %r" % (_doc.get("status"), _forbidden))

print()
print("397 Fig. 3, the released BAR_MONO path, in two passes")
G1 = V.bars_397()
check("every declared cell was measured",
      G1["cells"] == G1["declared"] == 8,
      "%d measured, %d declared" % (G1["cells"], G1["declared"]))
# THE TWO PASSES ARE THE POINT. Pass one must name NOTHING - a row that arrives
# already named came from the per-panel reader, which is the path this gallery
# used to draw and `run_batch` does not dispatch.
check("  pass one named none of them",
      G1["unnamed_after_pass_one"] == G1["cells"],
      "%d of %d still unnamed" % (G1["unnamed_after_pass_one"], G1["cells"]))
check("  and pass two named all of them off the figure's own fills",
      G1["named_by_figure"] == G1["cells"],
      "%d of %d" % (G1["named_by_figure"], G1["cells"]))
check("  every cell agrees with the eye reading inside the stated tolerance",
      G1["compared"] == 8 and G1["worst"] <= G1["tolerance"],
      "%d compared, worst %.2f > %.2f" % (G1["compared"], G1["worst"] or -1,
                                          G1["tolerance"]))
check("  and every error bar was confirmed by its own stem",
      G1["stem_confirmed"] == G1["cells"],
      "%d of %d" % (G1["stem_confirmed"], G1["cells"]))

print()
print("397 Fig. 1, two overlapping curves: what was read, and what it is worth")
G2 = V.lines_397()
check("18 of the 24 declared cells were read",
      (G2["read"], G2["declared"]) == (18, 24),
      "%d of %d" % (G2["read"], G2["declared"]))
# THE SIX ARE NOT AN ARBITRARY SIX. They are where the solid and dashed curves
# are one run of ink, and a reader that started answering there would be
# guessing which curve it had.
check("  and the six it refused are exactly the cells where the curves merge",
      G2["refused"] == [("FLUID", "4:30"), ("FLUID", "5:00"), ("FLUID", "6:00"),
                        ("NO_FLUID", "4:30"), ("NO_FLUID", "5:00"),
                        ("NO_FLUID", "6:00")],
      "%r" % (G2["refused"],))
check("  the provenance mix is the one this figure produces",
      G2["tiers"] == {"R0": 2, "R1": 9, "R4": 7, "REFUSED": 6},
      "%r" % (G2["tiers"],))
# ELEVEN, NOT EIGHTEEN. The gallery painted all eighteen the same green for a
# round, which read as eighteen usable numbers.
check("  so eleven of the eighteen are finalizable and seven are not",
      G2["finalizable"] == 11,
      "%d finalizable" % G2["finalizable"])
check("  every cell it did read agrees with the eye inside the tolerance",
      G2["worst"] <= G2["tolerance"],
      "worst %.2f > %.2f" % (G2["worst"], G2["tolerance"]))

print()
print("the segmentation half: panels found, and the ladder each one read")
if True:
    import tempfile
    _props = V.proposals_for([("475", "Fig. 2"), ("349", "Figure 3")],
                             os.path.join(tempfile.mkdtemp(prefix="fdt_vv_"),
                                          "proposals.csv"))
    for _pid, _fig, _name in (("475", "Fig. 2", "G3_segment_475fig2.png"),
                              ("349", "Figure 3", "G4_segment_349fig3.png")):
        _r = V.segmentation(_props, _pid, _fig,
                            os.path.join(HERE, "png", _name),
                            "%s %s" % (_pid, _fig))
        # THE COUNT IS THE MEASUREMENT. The proposer chooses its segmentation
        # mode by matching the number of axes counted by eye, so a run where the
        # two disagree has chosen a cut nobody validated.
        check("%s %s: the panels found are the axes counted by eye"
              % (_pid, _fig),
              _r["panels"] == _r["counted_by_eye"],
              "%d found, %d counted" % (_r["panels"], _r["counted_by_eye"]))
        check("  and every one of them read a validated tick ladder",
              _r["ladders"] == _r["panels"] and _r["statuses"] == ["LADDER_OK"],
              "%d ladders, statuses %r" % (_r["ladders"], _r["statuses"]))

print()
print("the pictures themselves")
for _name in ("G1_read_397fig3.png", "G2_read_397fig1.png"):
    _p = os.path.join(HERE, "png", _name)
    check("%s was written" % _name,
          os.path.exists(_p) and os.path.getsize(_p) > 50000,
          "%s" % (os.path.getsize(_p) if os.path.exists(_p) else "absent"))

done()
