"""What the review tier costs, and that nothing can declare its way out of it.

    python3 test_provenance.py

`provenance.py` holds two controlled vocabularies and one derivation. The
derivation is the whole point: a tier READ from a file is a tier somebody can
lower, and the first thing a pipeline that pools numbers must refuse is a value
that talks its own evidence up.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import provenance as P                                            # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


print("the tier is the worse of the two questions, never the better")
check("measured identity and measured value is the ordinary approval",
      P.review_tier("MEASURED_LINE_STYLE", "DIRECT_CURVE_INK") == "R0")
# The distinction the whole module exists for. A cell whose NUMBER came off the
# ink and whose row heading was reasoned to is wrong in one way; a cell whose
# number was reconstructed is wrong in another, and one field cannot hold both.
check("a measured number under an inferred heading is R2, not R0",
      P.review_tier("COMPLEMENT_OF_DECLARED_STYLES", "DIRECT_CURVE_INK") == "R2")
check("a reconstructed number under a measured heading is R3, not R0",
      P.review_tier("MEASURED_LINE_STYLE", "INTERPOLATED_CURVE_INK") == "R3")
check("and a good heading cannot rescue a fitted number",
      P.review_tier("MEASURED_LINE_STYLE", "FIT_FALLBACK") == "R4")
check("nor can a good number rescue a heading nobody measured",
      P.review_tier("CONTINUITY_TRACK", "DIRECT_CURVE_INK") == "R3")

print()
print("an unregistered method is not evidence of safety")
# THE FAIL-OPEN THIS REPLACES. `review_overlay` v7.51 kept a whitelist of field
# names and documented it as catching unknown FIELDS, which it could not. A
# registry that answered "unknown" with the lowest tier would be the same
# mistake with the same shape: a reader nobody taught this module about would
# pool its numbers on the strength of not being recognised.
check("an unknown identity method costs the highest tier",
      P.identity_tier("SOMETHING_NOBODY_WROTE_DOWN") == "R4")
check("an unknown value method costs the highest tier",
      P.value_tier("SOMETHING_NOBODY_WROTE_DOWN") == "R4")
check("a blank method is not a measurement either",
      P.review_tier("", "") == "R4")
check("and an unknown method is not finalizable",
      not P.finalizable("MEASURED_LINE_STYLE", "SOMETHING_NEW"))

print()
print("R4 is the tier a signature cannot buy")
# A reviewer looking at an overlay cannot tell a fitted y from a read one -
# that is exactly what the picture cannot show - so approving it would launder
# a model estimate into a pooled measurement.
check("a fitted number is not finalizable at any signature",
      not P.finalizable("MEASURED_LINE_STYLE", "FIT_FALLBACK"))
check("nor is a one-sided reading, which brackets nothing",
      not P.finalizable("MEASURED_LINE_STYLE", "EXTRAPOLATED_CURVE_INK"))
check("everything below it is",
      all(P.finalizable("MEASURED_LINE_STYLE", m)
          for m, t in P.VALUE_METHODS.items() if t != "R4"),
      "%r" % [m for m, t in P.VALUE_METHODS.items()
              if t != "R4" and not P.finalizable("MEASURED_LINE_STYLE", m)])
check("R4 is exactly the tier that is not finalizable",
      set(P.TIERS) - set(P.FINALIZABLE_TIERS) == {"R4"},
      "%r" % (P.FINALIZABLE_TIERS,))

print()
print("the vocabularies are vocabularies")
check("every registered identity method has a tier this module knows",
      set(P.IDENTITY_METHODS.values()) <= set(P.TIERS),
      "%r" % sorted(set(P.IDENTITY_METHODS.values()) - set(P.TIERS)))
check("and every value method",
      set(P.VALUE_METHODS.values()) <= set(P.TIERS),
      "%r" % sorted(set(P.VALUE_METHODS.values()) - set(P.TIERS)))
check("a method is spelled one way, in upper case",
      all(m == m.upper().strip() for m in
          list(P.IDENTITY_METHODS) + list(P.VALUE_METHODS)))
check("and the lookup does not care how the caller spelled it",
      P.value_tier(" direct_curve_ink ") == "R0")
# The tiers that need a person are named, not computed from the tier ORDER: R1
# is a declaration and needs no signature, and reading "everything above R0"
# would have demanded one.
check("a declared single series is recorded and costs no signature",
      P.identity_tier("DECLARED_SINGLE_SERIES") == "R1"
      and "R1" not in P.PANEL_CONFIRMATION_TIERS)
check("a panel-level confirmation is asked for R2 and R3",
      set(P.PANEL_CONFIRMATION_TIERS) == {"R2", "R3"},
      "%r" % (P.PANEL_CONFIRMATION_TIERS,))
check("a cell-level one only where the NUMBER was reconstructed",
      set(P.CELL_CONFIRMATION_TIERS) == {"R3"},
      "%r" % (P.CELL_CONFIRMATION_TIERS,))

print()
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
