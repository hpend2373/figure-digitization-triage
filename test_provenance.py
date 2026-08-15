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
# R4 IS NOT A TIER THAT ASKS, IT IS THE TIER THAT REFUSES. `run_batch` prices
# every panel's values to decide whether to put the inference question on it, and
# a blank pair prices at R4 - so if R4 were also a confirmation tier, every panel
# read by a reader that does not answer these questions would carry a question
# nobody could act on. Which is the thing this file's own comments say a
# confirmation column must never be.
check("R4 asks for no confirmation, because it grants no finalization",
      "R4" not in P.PANEL_CONFIRMATION_TIERS
      and "R4" not in P.CELL_CONFIRMATION_TIERS
      and "R4" not in P.FINALIZABLE_TIERS,
      "%r / %r" % (P.PANEL_CONFIRMATION_TIERS, P.CELL_CONFIRMATION_TIERS))

print()
print("the weight has provenance too, and it is not the mean's")
# v7.70. `Identity_Method` and `Value_Method` are both about the MEAN. In a
# continuous meta-analysis the DISPERSION is often what decides the weight, and a
# cell whose mean came straight off the ink and whose error bar was read from a
# cap no stem connects to it priced R0 on both axes and went into the pool.
check("a cap a stem was followed to is the strongest thing a figure offers",
      P.dispersion_tier("DIRECT_CONNECTED_CAP") == "R0"
      and P.dispersion_tier("DIRECT_BOX_GEOMETRY") == "R0")
check("ink at the right distance with nothing joining it is a person's question",
      P.dispersion_tier("UNSTEMMED_CAP") == "R3"
      and P.dispersion_tier("RESTORED_MASKED_CAP") == "R3"
      and P.dispersion_tier("INTERPOLATED_DISPERSION") == "R3")
check("and a spread a model produced is not rescuable by a signature",
      P.dispersion_tier("FITTED_DISPERSION") == "R4"
      and "R4" not in P.FINALIZABLE_TIERS)
# NO DISPERSION IS A STATEMENT, NOT A SILENCE. Whether a value without a weight
# may be pooled is the unit's question and `NO_VARIANCE` already answers it, so
# pricing the absence as unsafe would refuse a legitimate cell twice.
check("a cell with no error bar claims nothing and is doubted for nothing",
      P.dispersion_tier("NO_DISPERSION") == "R0"
      and P.dispersion_tier("", has_dispersion=False) == "R0")
check("while a NUMBER with no account of itself takes the highest tier",
      P.dispersion_tier("", has_dispersion=True) == "R4"
      and P.dispersion_tier("A_METHOD_FROM_2027") == "R4")
# THE ROW IS WHAT A GATE PRICES, and the row has three axes.
_row = dict(Identity_Method="MEASURED_COLOUR", Value_Method="MARKER_CENTER")
check("a row is priced over all three, not over the two about the mean",
      P.row_tier(_row) == "R0"
      and P.row_tier(dict(_row, Dispersion_Value="1.2",
                          Dispersion_Method="DIRECT_CONNECTED_CAP")) == "R0"
      and P.row_tier(dict(_row, Dispersion_Value="1.2",
                          Dispersion_Method="UNSTEMMED_CAP")) == "R3"
      and P.row_tier(dict(_row, Dispersion_Value="1.2")) == "R4",
      P.row_tier(dict(_row, Dispersion_Value="1.2",
                      Dispersion_Method="UNSTEMMED_CAP")))
check("  and a five-number summary's quartiles count as a dispersion",
      P.row_tier(dict(_row, Q1="3", Q3="7")) == "R4"
      and P.row_tier(dict(_row, Q1="3", Q3="7",
                          Dispersion_Method="DIRECT_BOX_GEOMETRY")) == "R0",
      P.row_tier(dict(_row, Q1="3", Q3="7")))
check("and a reader cannot claim a spread its own geometry does not offer",
      P.dispersion_contract_failure("BOX_VIOLIN", "DIRECT_CONNECTED_CAP")
      and P.dispersion_contract_failure("SCATTER", "UNSTEMMED_CAP")
      and not P.dispersion_contract_failure("BAR_COLOR", "UNSTEMMED_CAP")
      and not P.dispersion_contract_failure("A_READER_FROM_2027", "ANYTHING"),
      P.dispersion_contract_failure("BOX_VIOLIN", "DIRECT_CONNECTED_CAP"))

# A METHOD IS EITHER PRODUCIBLE OR RESERVED, AND THE FILE SAYS WHICH. v7.72.
# `RESTORED_MASKED_CAP` sat in the registry and in one reader's contract for a
# release looking exactly like a capability, with no emitter and no forward test
# behind it. A vocabulary ahead of the readers is deliberate; a vocabulary that
# does not say so is a claim about software that does not exist.
_producible = {m for methods in P.DISPERSION_CONTRACT.values() for m in methods}
check("every dispersion method is producible by some reader or reserved",
      set(P.DISPERSION_METHODS) == _producible | set(P.RESERVED_METHODS),
      "%s" % sorted(set(P.DISPERSION_METHODS)
                    - _producible - set(P.RESERVED_METHODS)))
check("  and none is both, which would be a contract contradicting itself",
      not (_producible & set(P.RESERVED_METHODS)),
      "%s" % sorted(_producible & set(P.RESERVED_METHODS)))
check("  and a reserved method still has a tier, so it is priced when it lands",
      all(P.dispersion_tier(m) in P.TIERS for m in P.RESERVED_METHODS
          if m in P.DISPERSION_METHODS))

print()
print("an occlusion cause this registry cannot name is a defect, not a tier")
# v7.66. `interpolation_method` tested for NONE and for MIXED and returned the
# FURNITURE answer for everything else - so a reader emitting `ERROR_BAR_STEM`
# for `ERRORBAR_STEM`, one character, had its unexplained gap priced at R1: the
# tier that asks for no signature at all. Everywhere else in this file an
# unregistered token costs the HIGHEST tier, and the token these methods are
# derived from had the opposite rule.
_reach = dict(span=1, stroke=3, dash_gap=0)
check("a cause the registry knows is priced by which cause it is",
      P.interpolation_method(occlusion="ERRORBAR_STEM", **_reach)
      == "RESTORED_MASKED_FURNITURE"
      and P.interpolation_method(occlusion=P.NO_OCCLUSION, **_reach)
      == "RESTORED_LINE_PATTERN_GAP"
      and P.interpolation_method(occlusion=P.MIXED_OCCLUSION, **_reach)
      == "LOCAL_BRACKETED_INTERPOLATION")
for _typo in ("ERROR_BAR_STEM", "errorbar_stem", "", "GRIDLINE", None):
    try:
        _got = P.interpolation_method(occlusion=_typo, **_reach)
    except ValueError:
        _got = None
    check("  and one it does not is refused rather than read as furniture (%r)"
          % (_typo,), _got is None, "returned %r" % (_got,))
# ONE VOCABULARY. The reader named its masks in string literals and this module
# tested for two of them; the copy is what let them drift.
import line_style_mono as _LSM                                     # noqa: E402
check("and the reader's causes are built from this list, not spelled again",
      set(_LSM.BLIND_CAUSES) | {P.NO_OCCLUSION, P.MIXED_OCCLUSION}
      == set(P.OCCLUSION_CAUSES)
      and P.NO_OCCLUSION not in _LSM.BLIND_CAUSES
      and P.MIXED_OCCLUSION not in _LSM.BLIND_CAUSES,
      "%r vs %r" % (_LSM.BLIND_CAUSES, P.OCCLUSION_CAUSES))
# And every cause the reader can actually put on a row survives the round trip -
# a vocabulary that raises on its own reader's output would stop every batch.
for _cause in _LSM.BLIND_CAUSES:
    check("  %s is a cause this registry prices" % _cause,
          P.interpolation_method(occlusion=_cause, **_reach)
          == "RESTORED_MASKED_FURNITURE")

print()
print("a re-derivation that cannot answer says so, and does not stay quiet")
# v7.76. `expected_line_style_methods` returned only the axes it could answer, so
# an axis it could NOT answer was absent from the dict - and an absent expectation
# compared equal to whatever the value claimed. A verifier that fails to refute is
# not a weaker check than one that refutes; on the axis it skipped it is no check
# at all, and it looks identical from the outside.
# `x` is the value's own column, and every reader mark carries it: from v7.81 a
# support geometry without it cannot be measured, which is the point - a support
# column means nothing until you know where the value sits.
_full = dict(line_style_source="MEASURED", x="100",
             Value_Support_Left_Px="100", Value_Support_Right_Px="100",
             Value_Span_Px="0", Occlusion_Cause="NONE",
             Errorbar_Stem_Confirmed="TRUE")
_verdict = P.expected_line_style_methods(_full)
check("a mark that records everything answers on all three axes",
      set(_verdict.expected) == set(P.METHOD_FIELDS) and not _verdict.problems,
      "%s" % (_verdict,))


def _axes_are_total(mark):
    """Every axis ends with an expectation or with a problem, never in silence."""
    verdict = P.expected_line_style_methods(mark)
    return len(verdict.expected) == 3 or bool(verdict.problems)


_holes = [drop for drop in sorted(_full)
          if not _axes_are_total({k: v for k, v in _full.items() if k != drop})]
check("and every field it can be missing leaves a problem behind, not a hole",
      not _holes, "silent when %s is missing" % ", ".join(_holes))
check("  including the span, which is the difference between R0 and R4",
      "Value_Span_Px" in " ".join(P.expected_line_style_methods(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}).problems)
      and "Value_Method" not in P.expected_line_style_methods(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}).expected,
      "%s" % (P.expected_line_style_methods(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}),))
# A SPAN OF ZERO IS A SPAN. `str(value or "")` turns the integer 0 into the empty
# string, and zero is the most important number this function reads - it is what
# makes a support column a direct observation rather than a carry. While the span
# defaulted to "0" the bug was invisible, because the default happened to be the
# answer.
check("a span of zero is a measurement, not a missing field",
      P.expected_line_style_methods(
          dict(_full, Value_Span_Px=0)).expected.get("Value_Method")
      == "DIRECT_CURVE_INK"
      and not P.expected_line_style_methods(
          dict(_full, Value_Span_Px=0)).problems,
      "%s" % (P.expected_line_style_methods(dict(_full, Value_Span_Px=0)),))
check("  while the same mark with no span at all is refused",
      P.expected_line_style_methods(
          dict(_full, Value_Span_Px="")).problems, "no problem reported")
# AND THE TWO FINDINGS ARE TWO CODES. "Your evidence says something else" and
# "your evidence says nothing" ask a reviewer for different work.
check("a mark that contradicts the value is reported as a contradiction",
      P.evidence_failure("LINE_MONO_STYLE", _full,
                         dict(Identity_Method="MEASURED_LINE_STYLE",
                              Value_Method="FIT_FALLBACK",
                              Dispersion_Method="DIRECT_CONNECTED_CAP"))[0]
      == "METHOD_CONTRADICTS_EVIDENCE")
check("  and a mark that cannot answer is reported as incomplete",
      P.evidence_failure("LINE_MONO_STYLE",
                         {k: v for k, v in _full.items()
                          if k != "Errorbar_Stem_Confirmed"},
                         dict(Identity_Method="MEASURED_LINE_STYLE",
                              Value_Method="DIRECT_CURVE_INK",
                              Dispersion_Method="DIRECT_CONNECTED_CAP"))[0]
      == "METHOD_EVIDENCE_INCOMPLETE",
      "%s" % (P.evidence_failure("LINE_MONO_STYLE",
                                 {k: v for k, v in _full.items()
                                  if k != "Errorbar_Stem_Confirmed"},
                                 dict(Identity_Method="MEASURED_LINE_STYLE",
                                      Value_Method="DIRECT_CURVE_INK",
                                      Dispersion_Method="DIRECT_CONNECTED_CAP")),))
check("  and a mark whose two columns give a cause nobody prices is incomplete too",
      P.evidence_failure("LINE_MONO_STYLE",
                         dict(_full, Value_Support_Right_Px="140",
                              Value_Span_Px="40", Occlusion_Cause="SMUDGE"),
                         dict(Identity_Method="MEASURED_LINE_STYLE",
                              Value_Method="DIRECT_CURVE_INK",
                              Dispersion_Method="DIRECT_CONNECTED_CAP"))[0]
      == "METHOD_EVIDENCE_INCOMPLETE")

print()
print("the support columns, the span and the x have to agree with each other")
# v7.79. Each field was read on its own - is there a support, are there two, is
# the span zero - so a mark whose numbers are internally impossible answered every
# question and got a tier. This is the general form of the nine one-sided carries
# v7.73 found on 397: there the SPAN was ignored, here the span is believed
# without checking it against the columns and the value's own x.
_geo = dict(line_style_source="MEASURED", x="140",
            Value_Support_Left_Px="130", Value_Support_Right_Px="130",
            Value_Span_Px="10", Occlusion_Cause="NONE",
            Errorbar_Stem_Confirmed="TRUE")
check("a one-sided support at a distance is a carry, and its span says so",
      P.expected_line_style_methods(_geo).expected["Value_Method"]
      == "EXTRAPOLATED_CURVE_INK"
      and not P.expected_line_style_methods(_geo).problems,
      "%s" % (P.expected_line_style_methods(_geo),))
check("  and the same columns claiming a span of zero are refused, not read as "
      "a direct observation",
      "10" in " ".join(P.expected_line_style_methods(
          dict(_geo, Value_Span_Px="0")).problems)
      and "Value_Method" not in P.expected_line_style_methods(
          dict(_geo, Value_Span_Px="0")).expected,
      "%s" % (P.expected_line_style_methods(dict(_geo, Value_Span_Px="0")),))
_bracket = dict(_geo, Value_Support_Left_Px="120",
                Value_Support_Right_Px="160", Value_Span_Px="40",
                Occlusion_Cause="ERRORBAR_STEM", Local_Stroke_Px="6",
                Expected_Dash_Gap_Px="0")
check("two columns that bracket the value and match their own gap are read",
      P.expected_line_style_methods(_bracket).expected.get("Value_Method")
      and not P.expected_line_style_methods(_bracket).problems,
      "%s" % (P.expected_line_style_methods(_bracket),))
check("  while a span narrower than the gap it claims to cross is refused",
      P.expected_line_style_methods(
          dict(_bracket, Value_Span_Px="2")).problems,
      "a 40px gap was priced as a 2px interpolation")
check("  and supports that do not bracket the value are not an interpolation",
      P.expected_line_style_methods(
          dict(_bracket, Value_Support_Left_Px="150",
               Value_Support_Right_Px="190", Value_Span_Px="40")).problems,
      "the value sits outside its own supports and was interpolated anyway")
check("  including the boundary: a support ON the value does not bracket it",
      P.expected_line_style_methods(
          dict(_bracket, Value_Support_Left_Px="140",
               Value_Support_Right_Px="180", Value_Span_Px="40")).problems)
# AND THE EPSILON IS FLOAT NOISE, NOT A TOLERANCE. `right - left` and a recorded
# span are the same subtraction done twice; a pixel is a disagreement. The
# fixture is 1e-10 of a pixel, which is what 1e-9 admits - the first version of
# this scenario called that "a hundredth of a pixel", a description two orders of
# magnitude looser than the constant it was describing.
check("a ten-billionth of a pixel is the same measurement and a whole one is not",
      not P.expected_line_style_methods(
          dict(_bracket, Value_Span_Px="40.0000000001")).problems
      and P.expected_line_style_methods(
          dict(_bracket, Value_Span_Px="40.01")).problems
      and P.expected_line_style_methods(
          dict(_bracket, Value_Span_Px="41")).problems
      and P.PIXEL_EPSILON == 1e-9)
# THE SHAPE OF THE EVIDENCE IS A CONTRACT, not a best effort. v7.81. The geometry
# check returned "" whenever a field was missing or unparseable, and the caller
# then fell through to a branch that derived a method anyway - so the two shapes
# no reader in this package produces were the two that bought a tier.
# AND IT IS DIAGNOSED AS THE SHAPE PROBLEM IT IS. A blank column and a column
# reading "foo" are different mistakes - one is a producer that encodes one-sided
# support the way no reader here does, the other is a corrupt field - and a
# reviewer given "not a number" for a blank goes looking for the wrong thing.
check("one support column recorded and the other blank is neither shape",
      "neither shape" in " ".join(P.expected_line_style_methods(
          dict(_geo, Value_Support_Right_Px="")).problems)
      and "Value_Method" not in P.expected_line_style_methods(
          dict(_geo, Value_Support_Right_Px="")).expected,
      "%s" % (P.expected_line_style_methods(
          dict(_geo, Value_Support_Right_Px="")),))
check("  and it is refused whichever side is missing",
      P.expected_line_style_methods(
          dict(_geo, Value_Support_Left_Px="")).problems)
check("supports that are not numbers support nothing, span and cause "
      "notwithstanding",
      P.expected_line_style_methods(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")).problems
      and "Value_Method" not in P.expected_line_style_methods(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")).expected,
      "%s" % (P.expected_line_style_methods(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")),))
check("  and neither does a value whose own column is not a number",
      P.expected_line_style_methods(dict(_geo, x="somewhere")).problems)
check("the three shapes a reader does produce are named, and only those",
      P.support_shape("", "", "", "")[0] == "NO_SUPPORT"
      and P.support_shape("130", "130", "10", "140")[0] == "ONE_COLUMN"
      and P.support_shape("120", "160", "40", "140")[0] == "TWO_COLUMNS"
      and set(P.SUPPORT_SHAPES) == {"NO_SUPPORT", "ONE_COLUMN", "TWO_COLUMNS"},
      "%s" % (P.support_shape("130", "130", "10", "140"),))

print()
print("the second reader whose methods are re-derived from its own evidence")
# v7.83. `BAR_COLOR` reaches R0 on all three axes, which means every one of its
# cells goes into a pool on the strength of three words nothing re-derived. It
# records enough to re-derive all three, and a verifier is the difference between
# "this reader could have produced that" and "this mark did".
_bar = dict(mask_overlap=0, Bar_Top_Definition="OUTLINE_CENTER",
            top_px="177.5", fill_top_px="180.0", mean="116.76",
            mean_if_read_at_fill_edge="115.91", dispersion="4.2",
            Errorbar_Stem_Confirmed="TRUE", Position_Assignment="DECLARED_ANCHOR")
check("a bar with its own colour, its outline and a stemmed cap answers all three",
      P.expected_bar_colour_methods(_bar).expected
      == {"Identity_Method": "MEASURED_COLOUR",
          "Value_Method": "BAR_OUTLINE_CENTER",
          "Dispersion_Method": "DIRECT_CONNECTED_CAP"}
      and not P.expected_bar_colour_methods(_bar).problems,
      "%s" % (P.expected_bar_colour_methods(_bar),))
# CONTESTED INK IS NOT EVIDENCE OF IDENTITY. The run drops a mark two declared
# colours both claim rather than choosing; a producer that kept one is claiming
# MEASURED_COLOUR for ink that measured as two colours.
check("a bar another declared colour also claims supports no identity",
      "Identity_Method" not in P.expected_bar_colour_methods(
          dict(_bar, mask_overlap=1)).expected
      and P.expected_bar_colour_methods(dict(_bar, mask_overlap=1)).problems,
      "%s" % (P.expected_bar_colour_methods(dict(_bar, mask_overlap=1)),))
check("  and a mark that does not say either way is incomplete, not clean",
      P.expected_bar_colour_methods(dict(_bar, mask_overlap="")).problems)
# THE NUMBER CAME FROM THE OUTLINE CENTRE OR IT DID NOT, and the reader records
# what the fill edge would have read - so the claim is checkable against a second
# number the same mark carries.
check("a mean equal to the fill-edge reading did not come from the outline "
      "centre",
      P.expected_bar_colour_methods(
          dict(_bar, mean=_bar["mean_if_read_at_fill_edge"])).problems
      and "Value_Method" not in P.expected_bar_colour_methods(
          dict(_bar, mean=_bar["mean_if_read_at_fill_edge"])).expected,
      "%s" % (P.expected_bar_colour_methods(
          dict(_bar, mean=_bar["mean_if_read_at_fill_edge"])),))
check("  while a bar whose outline IS its fill edge is not accused of it",
      P.expected_bar_colour_methods(
          dict(_bar, fill_top_px="177.5",
               mean=_bar["mean_if_read_at_fill_edge"])).expected
      .get("Value_Method") == "BAR_OUTLINE_CENTER")
check("  and another edge definition is refused outright",
      P.expected_bar_colour_methods(
          dict(_bar, Bar_Top_Definition="FILL_EDGE")).problems)
# THE SPREAD FOLLOWS THE STEM AND THE CAP, which are the two facts the reader
# decides from.
check("a cap with no stem is UNSTEMMED_CAP, and no cap at all is NO_DISPERSION",
      P.expected_bar_colour_methods(
          dict(_bar, Errorbar_Stem_Confirmed="FALSE")).expected
      ["Dispersion_Method"] == "UNSTEMMED_CAP"
      and P.expected_bar_colour_methods(
          dict(_bar, Errorbar_Stem_Confirmed="FALSE", dispersion=None)).expected
      ["Dispersion_Method"] == "NO_DISPERSION"
      and P.dispersion_tier("UNSTEMMED_CAP") == "R3",
      "%s" % (P.expected_bar_colour_methods(
          dict(_bar, Errorbar_Stem_Confirmed="FALSE")),))
check("  and a stem with nothing measured under it is incomplete",
      P.expected_bar_colour_methods(
          dict(_bar, dispersion=None)).problems)
check("  and a mark that does not say whether a stem connected cannot answer",
      P.expected_bar_colour_methods(
          dict(_bar, Errorbar_Stem_Confirmed="")).problems)
# AND A BAR PLACED BY COUNTING IS REFUSED HERE TOO. `grid_engine` refuses a VALUE
# that admits to counting; a value that drops the column passes that gate, and
# the mark cannot - it is hashed.
check("a bar whose x label was counted rather than declared is refused",
      P.expected_bar_colour_methods(
          dict(_bar, Position_Assignment="SEQUENTIAL")).problems,
      "%s" % (P.expected_bar_colour_methods(
          dict(_bar, Position_Assignment="SEQUENTIAL")),))
check("  while a panel that declares no positions is not asked for one",
      not P.expected_bar_colour_methods(
          dict(_bar, Position_Assignment="")).problems)
check("two of the seven readers now re-derive their methods, and the table says "
      "which",
      set(P.EVIDENCE_VERIFIERS) == {"LINE_MONO_STYLE", "BAR_COLOR"},
      "%s" % sorted(P.EVIDENCE_VERIFIERS))
# AND THE JOIN ASKS IT THE SAME WAY IT ASKS THE OTHER ONE. The call site is table
# driven - `EVIDENCE_VERIFIERS[mark_type]` - so what has to be checked here is
# that the entry answers in the two codes the finalizer branches on.
_claimed = dict(Identity_Method="MEASURED_COLOUR",
                Value_Method="BAR_OUTLINE_CENTER",
                Dispersion_Method="DIRECT_CONNECTED_CAP")
check("a BAR_COLOR mark that cannot answer is incomplete, and one that "
      "disagrees is a contradiction",
      P.evidence_failure("BAR_COLOR", dict(_bar, mask_overlap=1),
                         _claimed)[0] == "METHOD_EVIDENCE_INCOMPLETE"
      and P.evidence_failure(
          "BAR_COLOR", dict(_bar, Errorbar_Stem_Confirmed="FALSE"),
          _claimed)[0] == "METHOD_CONTRADICTS_EVIDENCE"
      and P.evidence_failure("BAR_COLOR", _bar, _claimed) == ("", ""),
      "%s" % (P.evidence_failure("BAR_COLOR", _bar, _claimed),))

print()
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
