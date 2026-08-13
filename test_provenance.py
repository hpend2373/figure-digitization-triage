"""What the review tier costs, and that nothing can declare its way out of it.

    python3 test_provenance.py

`provenance.py` holds two controlled vocabularies and one derivation. The
derivation is the whole point: a tier READ from a file is a tier somebody can
lower, and the first thing a pipeline that pools numbers must refuse is a value
that talks its own evidence up.
"""
import ast
import os
import shutil
import sys
import tempfile

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
print("one interpolation is three different claims")
# `INTERPOLATED_CURVE_INK` covered 160 of publication 397's 180 cells, which
# made it useless AS A TIER: R3 with a cell-level confirmation would have put 160
# signatures in front of a reviewer, 121 of them for the reader stepping over its
# own three-pixel error-bar stem. Split, the same publication asks for FIVE.
_STEM, _NONE, _MIXED = "ERRORBAR_STEM", P.NO_OCCLUSION, P.MIXED_OCCLUSION
check("a gap the reader made, no wider than the stroke, is restored furniture",
      P.interpolation_method(3, 6, 1, _STEM) == "RESTORED_MASKED_FURNITURE",
      P.interpolation_method(3, 6, 1, _STEM))
check("and costs no signature - it puts back a stroke the figure printed",
      P.value_tier("RESTORED_MASKED_FURNITURE") == "R1")
check("a gap the FIGURE drew, within its own dash period, is the same kind",
      P.interpolation_method(3, 6, 1, _NONE) == "RESTORED_LINE_PATTERN_GAP"
      and P.value_tier("RESTORED_LINE_PATTERN_GAP") == "R1")
# Local and bracketed but not fully explained - two kinds of furniture over one
# gap, or furniture over part of it. The number is measured between two real
# supports; which explanation applies is what a person has to look at.
check("a local gap nobody can attribute needs looking at, cell by cell",
      P.interpolation_method(3, 6, 1, _MIXED) == "LOCAL_BRACKETED_INTERPOLATION"
      and P.value_tier("LOCAL_BRACKETED_INTERPOLATION") == "R3")
check("and a gap wider than anything the figure draws is not rescuable",
      P.interpolation_method(22, 5, 1, _STEM) == "NONLOCAL_INTERPOLATION"
      and not P.finalizable("MEASURED_LINE_STYLE", "NONLOCAL_INTERPOLATION"))
# LOCALITY BEATS PROVENANCE. A gridline is furniture this reader removed, and a
# 22-pixel gridline gap is still a guess about a curve nobody sampled.
check("furniture we removed does not make a wide gap local",
      P.interpolation_method(22, 5, 1, "HORIZONTAL_RULE")
      == "NONLOCAL_INTERPOLATION")

print()
print("what locality is measured against, and two rules that were thrown away")
# THE REACH IS THE FIGURE'S OWN DRAWING SCALE - the thicker of the stroke that
# draws this curve and the dash gap this style uses on this panel. Both are
# measured on the figure, so the answer is the same at any rendering; a pixel
# constant would make it depend on the DPI somebody rendered at.
check("a gap wider than the stroke but inside the dash period is still local",
      P.interpolation_method(4, 2, 5, _STEM) == "RESTORED_MASKED_FURNITURE",
      P.interpolation_method(4, 2, 5, _STEM))
check("and one wider than both is not",
      P.interpolation_method(6, 2, 5, _STEM) == "NONLOCAL_INTERPOLATION")
check("a curve with no measured scale at all admits nothing",
      P.interpolation_method(1, 0, 0, _STEM) == "NONLOCAL_INTERPOLATION",
      P.interpolation_method(1, 0, 0, _STEM))
# REJECTED RULE 1: `span <= stroke + occlusion_width`. It passes 160 of 160,
# because the span between two supports IS the occluded columns plus one -
# arithmetic, not evidence. The 22-pixel gridline gap is where the two rules
# disagree, and this one has to refuse it.
check("the span-under-stroke-plus-occlusion rule would have passed this; this "
      "one refuses it",
      P.interpolation_method(22, 5, 1, "HORIZONTAL_RULE")
      == "NONLOCAL_INTERPOLATION" and 22 <= 5 + 21)
# REJECTED RULE 2: a fraction of the position spacing. Measured on 397,
# `span < 0.25 * spacing` admits 144 of the 160 and `span < 0.5 * spacing` admits
# 147 - including 23 and 24 of the 31 unattributable ones. A nine-pixel gap on a
# 33-pixel spacing passes both and fails this.
check("a fraction of the position spacing would have passed this; this one "
      "refuses it",
      P.interpolation_method(9, 4, 0, "HORIZONTAL_RULE")
      == "NONLOCAL_INTERPOLATION" and 9 < 0.5 * 33.0)

print()
print("a tier is derived by whoever needs it and written down nowhere")
# IT WAS WRITTEN ON THE ROW UNTIL v7.59, by the line whose own comment said the
# tier is derived so that nothing in a file can declare its way to a weaker
# check. Nothing read it, so nothing was wrong - but the moment it reached
# `figure_values_*.csv` and a finalizer trusted it, the principle would have been
# gone and the code would still have claimed it. A derived value that is also
# stored is two answers to one question, and the stored one is the one somebody
# can edit.
#
# Scanned out of the SOURCE, not out of one reader's output, because the readers
# that have not been written yet are the ones this has to hold for.
TIER_FIELDS = ("Review_Tier", "Value_Tier", "Identity_Tier")


def tier_writers(path):
    """Places in one file that put a tier INTO a record."""
    found = []
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        # dict(Review_Tier=...) or f(Review_Tier=...)
        if isinstance(node, ast.Call):
            found += [kw.arg for kw in node.keywords if kw.arg in TIER_FIELDS]
        # {"Review_Tier": ...}
        elif isinstance(node, ast.Dict):
            found += [k.value for k in node.keys
                      if isinstance(k, ast.Constant) and k.value in TIER_FIELDS]
        # row["Review_Tier"] = ...
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            index = node.slice
            if isinstance(index, ast.Constant) and index.value in TIER_FIELDS:
                found.append(index.value)
    return found


_PACKAGE = sorted(name for name in os.listdir(HERE)
                  if name.endswith(".py") and not name.startswith("test_"))
_writers = {name: tier_writers(os.path.join(HERE, name)) for name in _PACKAGE}
_writers = {name: hits for name, hits in _writers.items() if hits}
check("no module in the package writes a tier into a record",
      not _writers, "%r" % _writers)
# And the scan has to be able to see one, or it is a guard that cannot fire.
_probe = tempfile.mkdtemp(prefix="tierprobe_")
for _i, _src in enumerate((
        'row = dict(Value_Method="X", Review_Tier="R0")\n',
        'row = {"Review_Tier": "R0"}\n',
        'row["Review_Tier"] = "R0"\n')):
    _path = os.path.join(_probe, "wrote%d.py" % _i)
    open(_path, "w", encoding="utf-8").write(_src)
    check("the scan sees a tier written as %s"
          % ("a keyword", "a dict key", "a subscript")[_i],
          tier_writers(_path) == ["Review_Tier"], "%r" % tier_writers(_path))
_clean = os.path.join(_probe, "clean.py")
open(_clean, "w", encoding="utf-8").write(
    'import provenance\nrow = dict(Value_Method="X")\n'
    'tier = provenance.review_tier("A", "B")\n')
check("and does not flag a module that derives one instead",
      tier_writers(_clean) == [], "%r" % tier_writers(_clean))
shutil.rmtree(_probe, ignore_errors=True)

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
