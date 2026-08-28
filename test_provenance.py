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
import mark_readers as MR                                          # noqa: E402



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
      # AND NEITHER CAN BAR_COLOR, from v7.84: `bar_reader` sets `cap_px` only
      # inside the branch that also confirms the stem, so a cap without one is a
      # shape it cannot produce. The line readers keep it - theirs is reachable.
      and P.dispersion_contract_failure("BAR_COLOR", "UNSTEMMED_CAP")
      and not P.dispersion_contract_failure("LINE_MONO", "UNSTEMMED_CAP")
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
# THE SAME QUESTION ON THE IDENTITY SIDE, WHICH NOTHING WAS ASKING. v9.16.
# `MEASURED_MARKER_SHAPE_FILL` was priced R0, emitted by the routed scatter
# reader, carried through the artifact and the hashes and checked by the
# finalizer's own gate - and it was in no reader's `METHOD_CONTRACT`, so the
# first routed value to reach finalization would have been withheld for a method
# its reader had in fact produced. The dispersion side has had this check since
# v7.72; the identity side is the half that was not asked.
_id_producible = {i for pairs in P.METHOD_CONTRACT.values() for i, _v in pairs}
#: Identities that reach a value row without a reader emitting one: a person's
#: resolution, and the human confirmations the ladder prices but no reader can
#: reach. Named rather than subtracted silently.
_ID_NOT_FROM_A_READER = {"HUMAN_RESOLUTION", "SOURCE_TRANSCRIBED"}
check("every identity method is producible by some reader, or named as not",
      set(P.IDENTITY_METHODS) - _id_producible <= (_ID_NOT_FROM_A_READER
                                                   | set(P.RESERVED_METHODS)),
      "%s" % sorted(set(P.IDENTITY_METHODS) - _id_producible
                    - _ID_NOT_FROM_A_READER - set(P.RESERVED_METHODS)))
check("  and the routed scatter's identity is one of them",
      not P.contract_failure("SCATTER", "MEASURED_MARKER_SHAPE_FILL",
                             "POINT_CLOUD_ASSOCIATION")
      and P.identity_tier("MEASURED_MARKER_SHAPE_FILL") == "R0",
      "%r" % (P.contract_failure("SCATTER", "MEASURED_MARKER_SHAPE_FILL",
                                 "POINT_CLOUD_ASSOCIATION"),))

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
# The pixel rows are the fixture's own, put through the same axis the verifier
# is handed: from v7.87 a curve mark's numbers are re-computed, so typing them
# would be describing a mark no reader produces.
_CURVE_AXIS = MR.AxisCalibration.from_points([(400.0, 60.0), (100.0, 162.3)])
_CURVE_CONTEXT = {"Y_Calibration": MR._calibration_record(_CURVE_AXIS)}
_full = dict(line_style_source="MEASURED", x="100",
             Value_Support_Left_Px="100", Value_Support_Right_Px="100",
             Value_Span_Px="0", Occlusion_Cause="NONE",
             Errorbar_Stem_Confirmed="TRUE",
             marker_center_px="200.0",
             mean=repr(_CURVE_AXIS.pixel_to_value(200.0)),
             Errorbar_Top_Px="190.0", Errorbar_Bottom_Px="210.0",
             dispersion=repr(abs(_CURVE_AXIS.pixel_to_value(190.0)
                                 - _CURVE_AXIS.pixel_to_value(210.0)) / 2.0))


def P_expected_line_style_methods_ctx(mark):
    """The verifier, always handed the fixture's own axis."""
    return P.expected_line_style_methods(mark, _CURVE_CONTEXT)
_verdict = P_expected_line_style_methods_ctx(_full)
check("a mark that records everything answers on all three axes",
      set(_verdict.expected) == set(P.METHOD_FIELDS) and not _verdict.problems,
      "%s" % (_verdict,))


def _axes_are_total(mark):
    """Every axis ends with an expectation or with a problem, never in silence."""
    verdict = P_expected_line_style_methods_ctx(mark)
    return len(verdict.expected) == 3 or bool(verdict.problems)


_holes = [drop for drop in sorted(_full)
          if not _axes_are_total({k: v for k, v in _full.items() if k != drop})]
check("and every field it can be missing leaves a problem behind, not a hole",
      not _holes, "silent when %s is missing" % ", ".join(_holes))
check("  including the span, which is the difference between R0 and R4",
      "Value_Span_Px" in " ".join(P_expected_line_style_methods_ctx(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}).problems)
      and "Value_Method" not in P_expected_line_style_methods_ctx(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}).expected,
      "%s" % (P_expected_line_style_methods_ctx(
          {k: v for k, v in _full.items() if k != "Value_Span_Px"}),))
# A SPAN OF ZERO IS A SPAN. `str(value or "")` turns the integer 0 into the empty
# string, and zero is the most important number this function reads - it is what
# makes a support column a direct observation rather than a carry. While the span
# defaulted to "0" the bug was invisible, because the default happened to be the
# answer.
check("a span of zero is a measurement, not a missing field",
      P_expected_line_style_methods_ctx(
          dict(_full, Value_Span_Px=0)).expected.get("Value_Method")
      == "DIRECT_CURVE_INK"
      and not P_expected_line_style_methods_ctx(
          dict(_full, Value_Span_Px=0)).problems,
      "%s" % (P_expected_line_style_methods_ctx(dict(_full, Value_Span_Px=0)),))
check("  while the same mark with no span at all is refused",
      P_expected_line_style_methods_ctx(
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
            Errorbar_Stem_Confirmed="TRUE",
            marker_center_px="200.0",
            mean=repr(_CURVE_AXIS.pixel_to_value(200.0)),
            Errorbar_Top_Px="190.0", Errorbar_Bottom_Px="210.0",
            dispersion=repr(abs(_CURVE_AXIS.pixel_to_value(190.0)
                                - _CURVE_AXIS.pixel_to_value(210.0)) / 2.0))
check("a one-sided support at a distance is a carry, and its span says so",
      P_expected_line_style_methods_ctx(_geo).expected["Value_Method"]
      == "EXTRAPOLATED_CURVE_INK"
      and not P_expected_line_style_methods_ctx(_geo).problems,
      "%s" % (P_expected_line_style_methods_ctx(_geo),))
check("  and the same columns claiming a span of zero are refused, not read as "
      "a direct observation",
      "10" in " ".join(P_expected_line_style_methods_ctx(
          dict(_geo, Value_Span_Px="0")).problems)
      and "Value_Method" not in P_expected_line_style_methods_ctx(
          dict(_geo, Value_Span_Px="0")).expected,
      "%s" % (P_expected_line_style_methods_ctx(dict(_geo, Value_Span_Px="0")),))
_bracket = dict(_geo, Value_Support_Left_Px="120",
                Value_Support_Right_Px="160", Value_Span_Px="40",
                Occlusion_Cause="ERRORBAR_STEM", Local_Stroke_Px="6",
                Expected_Dash_Gap_Px="0")
check("two columns that bracket the value and match their own gap are read",
      P_expected_line_style_methods_ctx(_bracket).expected.get("Value_Method")
      and not P_expected_line_style_methods_ctx(_bracket).problems,
      "%s" % (P_expected_line_style_methods_ctx(_bracket),))
check("  while a span narrower than the gap it claims to cross is refused",
      P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Span_Px="2")).problems,
      "a 40px gap was priced as a 2px interpolation")
check("  and supports that do not bracket the value are not an interpolation",
      P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Support_Left_Px="150",
               Value_Support_Right_Px="190", Value_Span_Px="40")).problems,
      "the value sits outside its own supports and was interpolated anyway")
check("  including the boundary: a support ON the value does not bracket it",
      P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Support_Left_Px="140",
               Value_Support_Right_Px="180", Value_Span_Px="40")).problems)
# AND THE EPSILON IS FLOAT NOISE, NOT A TOLERANCE. `right - left` and a recorded
# span are the same subtraction done twice; a pixel is a disagreement. The
# fixture is 1e-10 of a pixel, which is what 1e-9 admits - the first version of
# this scenario called that "a hundredth of a pixel", a description two orders of
# magnitude looser than the constant it was describing.
check("a ten-billionth of a pixel is the same measurement and a whole one is not",
      not P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Span_Px="40.0000000001")).problems
      and P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Span_Px="40.01")).problems
      and P_expected_line_style_methods_ctx(
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
      "neither shape" in " ".join(P_expected_line_style_methods_ctx(
          dict(_geo, Value_Support_Right_Px="")).problems)
      and "Value_Method" not in P_expected_line_style_methods_ctx(
          dict(_geo, Value_Support_Right_Px="")).expected,
      "%s" % (P_expected_line_style_methods_ctx(
          dict(_geo, Value_Support_Right_Px="")),))
check("  and it is refused whichever side is missing",
      P_expected_line_style_methods_ctx(
          dict(_geo, Value_Support_Left_Px="")).problems)
check("supports that are not numbers support nothing, span and cause "
      "notwithstanding",
      P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")).problems
      and "Value_Method" not in P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")).expected,
      "%s" % (P_expected_line_style_methods_ctx(
          dict(_bracket, Value_Support_Left_Px="foo",
               Value_Support_Right_Px="bar")),))
check("  and neither does a value whose own column is not a number",
      P_expected_line_style_methods_ctx(dict(_geo, x="somewhere")).problems)
check("the three shapes a reader does produce are named, and only those",
      P.support_shape("", "", "", "")[0] == "NO_SUPPORT"
      and P.support_shape("130", "130", "10", "140")[0] == "ONE_COLUMN"
      and P.support_shape("120", "160", "40", "140")[0] == "TWO_COLUMNS"
      and set(P.SUPPORT_SHAPES) == {"NO_SUPPORT", "ONE_COLUMN", "TWO_COLUMNS"},
      "%s" % (P.support_shape("130", "130", "10", "140"),))

# AND A CURVE'S NUMBERS ARE RE-COMPUTED TOO. v7.87. Re-deriving the METHOD from
# the support columns says how the number was got; nothing said it was the number
# those pixels produce - so a producer could move `marker_center_px`, keep the
# mean, re-stamp everything, and the value-to-mark join found two fields that
# agreed with each other. The axis is the third party.
check("a curve mark's mean is what its own row reads under this run's axis",
      not P_expected_line_style_methods_ctx(_full).problems
      and P_expected_line_style_methods_ctx(
          dict(_full, mean="999")).problems
      and P_expected_line_style_methods_ctx(
          dict(_full, marker_center_px="150.0")).problems,
      "%s" % (P_expected_line_style_methods_ctx(dict(_full, mean="999")),))
check("  and its dispersion is half the distance between its own cap rows",
      P_expected_line_style_methods_ctx(dict(_full, dispersion="99")).problems
      and P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Top_Px="")).problems
      and not P_expected_line_style_methods_ctx(
          dict(_full, dispersion=None, Errorbar_Top_Px="",
               Errorbar_Bottom_Px="")).problems,
      "%s" % (P_expected_line_style_methods_ctx(dict(_full, dispersion="99")),))
check("  and a mark with no row to have read at all answers nothing",
      P_expected_line_style_methods_ctx(
          dict(_full, marker_center_px="")).problems
      and P.expected_line_style_methods(_full, None).problems,
      "%s" % (P.expected_line_style_methods(_full, None),))

# AND "NO SPREAD" IS A FINDING, NOT A SILENCE. v7.92. The reader knows why it
# found no error bar - the two curves share a column, the ink never ends, the cap
# is not bounded - and a mark that does not say which cannot support
# NO_DISPERSION any more than a blank method can support a tier.
check("a mark with no spread and no reason supports no dispersion method",
      "Dispersion_Method" not in P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE", dispersion=None,
               Errorbar_Top_Px="", Errorbar_Bottom_Px="")).expected,
      "%s" % (P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE", dispersion=None,
               Errorbar_Top_Px="", Errorbar_Bottom_Px="")),))
check("  while one that says why does",
      P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE", dispersion=None,
               Errorbar_Top_Px="", Errorbar_Bottom_Px="",
               Dispersion_Refusal=P.MARKS_SHARE_A_COLUMN)).expected
      ["Dispersion_Method"] == "NO_DISPERSION")
check("  and a reason this registry does not price is refused",
      "Dispersion_Method" not in P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE", dispersion=None,
               Errorbar_Top_Px="", Errorbar_Bottom_Px="",
               Dispersion_Refusal="BECAUSE_I_SAID_SO")).expected,
      "%s" % (P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE", dispersion=None,
               Errorbar_Top_Px="", Errorbar_Bottom_Px="",
               Dispersion_Refusal="BECAUSE_I_SAID_SO")),))
check("  and a cap that was read beside a stem that was not is two answers",
      P_expected_line_style_methods_ctx(
          dict(_full, Errorbar_Stem_Confirmed="FALSE",
               Dispersion_Refusal=P.CAP_READ)).problems
      and P_expected_line_style_methods_ctx(
          dict(_full, Dispersion_Refusal=P.NO_BOUNDED_CAP)).problems,
      "%s" % (P_expected_line_style_methods_ctx(
          dict(_full, Dispersion_Refusal=P.NO_BOUNDED_CAP)),))

print()
print("the second reader whose methods are re-derived from its own evidence")
# v7.83. `BAR_COLOR` reaches R0 on all three axes, which means every one of its
# cells goes into a pool on the strength of three words nothing re-derived. It
# records enough to re-derive all three, and a verifier is the difference between
# "this reader could have produced that" and "this mark did".
# THE NUMBERS ARE THE CALIBRATION'S, not decoration: from v7.85 the verifier
# re-computes what each pixel row should have read under the y calibration this
# run declared, so the fixture's means and dispersion are derived here the same
# way the reader derives them rather than typed.
_AXIS = MR.AxisCalibration.from_points([(400.0, 60.0), (100.0, 162.3)])
# The declaration a bar mark is re-derived against: the axis, the anchors its x
# label is assigned from, the baseline it is measured from, and the box it has
# to be inside.
_BAR_CONTEXT = {"Y_Calibration": MR._calibration_record(_AXIS),
                "Panel_Box": [40, 600, 20, 420],
                "Baseline_Value": "0",
                "Position_Anchors": {"T0": 200.0, "T1": 300.0, "T2": 400.0},
                "Series_Discriminants": {
                    "SUPINE": {"Mask_Key": "blue", "Colour_Hex": "",
                               "Expected_Mask": "blue"}}}
_bar = dict(mask_overlap=0, own_mask_hit=1, own_mask_key="blue",
            series="SUPINE", Bar_Top_Definition="OUTLINE_CENTER",
            top_px="177.5", fill_top_px="180.0",
            mean=repr(_AXIS.pixel_to_value(177.5)),
            mean_if_read_at_fill_edge=repr(_AXIS.pixel_to_value(180.0)),
            cap_px="165.0",
            dispersion=repr(abs(_AXIS.pixel_to_value(165.0)
                                - _AXIS.pixel_to_value(177.5))),
            Errorbar_Stem_Confirmed="TRUE", Bar_Direction="UP",
            x="203.0", slot_residual_px="3.0",
            x_label="T0", Position_Assignment="DECLARED_ANCHOR")


def _bar_verdict(**over):
    return P.expected_bar_colour_methods(dict(_bar, **over), _BAR_CONTEXT)
check("a bar with its own colour, its outline and a stemmed cap answers all three",
      _bar_verdict().expected
      == {"Identity_Method": "MEASURED_COLOUR",
          "Value_Method": "BAR_OUTLINE_CENTER",
          "Dispersion_Method": "DIRECT_CONNECTED_CAP"}
      and not _bar_verdict().problems,
      "%s" % (_bar_verdict(),))
# CONTESTED INK IS NOT EVIDENCE OF IDENTITY. The run drops a mark two declared
# colours both claim rather than choosing; a producer that kept one is claiming
# MEASURED_COLOUR for ink that measured as two colours.
check("a bar another declared colour also claims supports no identity",
      "Identity_Method" not in _bar_verdict(mask_overlap=1).expected
      and _bar_verdict(mask_overlap=1).problems,
      "%s" % (_bar_verdict(mask_overlap=1),))
check("  and a mark that does not say either way is incomplete, not clean",
      _bar_verdict(mask_overlap="").problems)
# THE NUMBER CAME FROM THE OUTLINE CENTRE OR IT DID NOT, and the reader records
# what the fill edge would have read - so the claim is checkable against a second
# number the same mark carries.
check("a mean equal to the fill-edge reading did not come from the outline "
      "centre",
      _bar_verdict(mean=_bar["mean_if_read_at_fill_edge"]).problems
      and "Value_Method" not in _bar_verdict(mean=_bar["mean_if_read_at_fill_edge"]).expected,
      "%s" % (_bar_verdict(mean=_bar["mean_if_read_at_fill_edge"]),))
check("  while a bar whose outline IS its fill edge is not accused of it",
      _bar_verdict(fill_top_px="177.5",
                   mean_if_read_at_fill_edge=_bar["mean"]).expected
      .get("Value_Method") == "BAR_OUTLINE_CENTER",
      "%s" % (_bar_verdict(fill_top_px="177.5",
                           mean_if_read_at_fill_edge=_bar["mean"]),))
check("  and another edge definition is refused outright",
      _bar_verdict(Bar_Top_Definition="FILL_EDGE").problems)
# THE SPREAD FOLLOWS THE STEM AND THE CAP, which are the two facts the reader
# decides from.
check("no cap and no stem is NO_DISPERSION, and this reader has no third answer",
      _bar_verdict(Errorbar_Stem_Confirmed="FALSE", cap_px=None,
               dispersion=None).expected["Dispersion_Method"] == "NO_DISPERSION"
      and _bar_verdict(Errorbar_Stem_Confirmed="FALSE").problems,
      "%s" % (_bar_verdict(Errorbar_Stem_Confirmed="FALSE"),))
check("  and a stem with nothing measured under it is incomplete",
      _bar_verdict(dispersion=None).problems
      and _bar_verdict(cap_px=None).problems
      and "Dispersion_Method" not in _bar_verdict(top_px="").expected,
      "%s" % (_bar_verdict(cap_px=None),))
check("  and a mark that does not say whether a stem connected cannot answer",
      _bar_verdict(Errorbar_Stem_Confirmed="").problems)
# AND A BAR PLACED BY COUNTING IS REFUSED HERE TOO. `grid_engine` refuses a VALUE
# that admits to counting; a value that drops the column passes that gate, and
# the mark cannot - it is hashed.
check("a bar whose x label was counted rather than declared is refused",
      _bar_verdict(Position_Assignment="SEQUENTIAL").problems,
      "%s" % (_bar_verdict(Position_Assignment="SEQUENTIAL"),))
# AND A BAR THAT SITS AT A LABEL AND SAYS NOTHING ABOUT HOW IT GOT THERE IS
# REFUSED TOO. v7.83 checked the field only when it was filled in, so blanking
# it was the way past the check - and blanking it on the VALUE is already how a
# counted label gets past `grid_engine`.
check("  and so is one that sits at a declared label and says nothing",
      _bar_verdict(Position_Assignment="").problems,
      "%s" % (_bar_verdict(Position_Assignment=""),))
check("  while a panel with no position dimension is not asked for one",
      not _bar_verdict(x_label="", Position_Assignment="").problems)
# AND THE LABEL HAS TO BE THE ANCHOR THE MARK IS NEAREST TO. v7.86.
# `DECLARED_ANCHOR` says the reader used declared anchors; it does not say THIS
# mark is at the one it names. Two bars could exchange their labels, have their
# cells and hashes recomputed to match, and pass everything - the heading
# exchange v7.74 closed, reopened at the pixel-to-position boundary.
check("a bar filed under an anchor it is not nearest to is refused",
      "nearest the declared anchor" in " ".join(
          _bar_verdict(x_label="T1", slot_residual_px="97.0").problems),
      "%s" % (_bar_verdict(x_label="T1", slot_residual_px="97.0"),))
check("  and one whose recorded distance is not the distance it is at",
      "from its anchor" in " ".join(
          _bar_verdict(slot_residual_px="0.0").problems),
      "%s" % (_bar_verdict(slot_residual_px="0.0"),))
check("  and one that records no distance at all",
      _bar_verdict(slot_residual_px="").problems)
# THE TOLERANCE IS THE PANEL'S, and the reader's default is half the smallest
# gap between declared anchors - so a bar three pixels off its anchor is fine
# here and refused where the config says two.
check("  and one further from its anchor than the panel accepts",
      "accepts" in " ".join(P.expected_bar_colour_methods(
          _bar, dict(_BAR_CONTEXT, Slot_Tolerance_Px=2.0)).problems),
      "%s" % (P.expected_bar_colour_methods(
          _bar, dict(_BAR_CONTEXT, Slot_Tolerance_Px=2.0)),))
# The default is half the smallest gap between declared anchors, so a bar can
# never be BOTH nearest to its own anchor and beyond it - which is the point:
# the tolerance only bites when a config narrows it, or when a panel declares
# one anchor and a mark is somewhere else entirely.
check("  while the default is half the gap between the anchors themselves",
      not _bar_verdict().problems
      and "accepts" in " ".join(P.expected_bar_colour_methods(
          dict(_bar, x="900.0", slot_residual_px="700.0"),
          dict(_BAR_CONTEXT, Position_Anchors={"T0": 200.0})).problems),
      "%s" % (P.expected_bar_colour_methods(
          dict(_bar, x="900.0", slot_residual_px="700.0"),
          dict(_BAR_CONTEXT, Position_Anchors={"T0": 200.0})),))
check("  and a bar equidistant from two anchors belongs to neither",
      "not decidable" in " ".join(P.expected_bar_colour_methods(
          dict(_bar, x="250.0", slot_residual_px="50.0"),
          dict(_BAR_CONTEXT, Slot_Tolerance_Px=60.0)).problems),
      "%s" % (P.expected_bar_colour_methods(
          dict(_bar, x="250.0", slot_residual_px="50.0"),
          dict(_BAR_CONTEXT, Slot_Tolerance_Px=60.0)),))
check("  and a label the run declares no anchors for supports nothing",
      P.expected_bar_colour_methods(
          _bar, {k: v for k, v in _BAR_CONTEXT.items()
                 if k != "Position_Anchors"}).problems)
# THE BASELINE DECIDES WHICH END IS THE DATA END, and which side of it a cap can
# be on. Re-computing calibrate(top_px) says the number matches the row; it does
# not say the row was the right end.
check("a cap between the bar top and the baseline is not an error bar's cap",
      "measured outward" in " ".join(_bar_verdict(
          cap_px="185.0",
          dispersion=repr(abs(_AXIS.pixel_to_value(185.0)
                              - _AXIS.pixel_to_value(177.5)))).problems),
      "%s" % (_bar_verdict(cap_px="185.0"),))
check("  and a bar that says it grows the other way is refused",
      "grows" in " ".join(_bar_verdict(Bar_Direction="DOWN").problems),
      "%s" % (_bar_verdict(Bar_Direction="DOWN"),))
check("  and a row measured outside the panel box the run declares",
      "outside the panel box" in " ".join(_bar_verdict(
          top_px="12.0",
          mean=repr(_AXIS.pixel_to_value(12.0))).problems),
      "%s" % (_bar_verdict(top_px="12.0",
                           mean=repr(_AXIS.pixel_to_value(12.0))),))
check("  while a blank Baseline_Value is the zero the reader defaults to",
      not P.expected_bar_colour_methods(
          _bar, dict(_BAR_CONTEXT, Baseline_Value="")).problems,
      "%s" % (P.expected_bar_colour_methods(
          _bar, dict(_BAR_CONTEXT, Baseline_Value="")),))
# EVERY FIELD IT DECIDES FROM IS REQUIRED. A verifier that only refutes can be
# starved: v7.83 gave all three methods at R0 to a mark with a non-numeric
# overlap, no fill-edge reading and no cap.
_starved = dict(mask_overlap="garbage", Bar_Top_Definition="OUTLINE_CENTER",
                top_px="177.5", fill_top_px="", mean="999",
                mean_if_read_at_fill_edge="", dispersion="4.2", cap_px="",
                Errorbar_Stem_Confirmed="TRUE", x_label="T0",
                Position_Assignment="")
check("a mark that simply omits its evidence answers on no axis at all",
      not P.expected_bar_colour_methods(_starved, _BAR_CONTEXT).expected
      and len(P.expected_bar_colour_methods(_starved, _BAR_CONTEXT).problems) == 4,
      "%s" % (P.expected_bar_colour_methods(_starved, _BAR_CONTEXT),))
# AND THE OTHER HALF OF THE COLOUR EVIDENCE. v7.88. `mask_overlap=0` says no
# OTHER declared colour covers this ink; it does not say the colour THIS series
# declares does, and MEASURED_COLOUR is a claim about the second. The reader
# always knew - it found the bar in that mask - and wrote nothing down.
check("a bar that does not record its own colour claiming its ink names no "
      "series",
      "Identity_Method" not in _bar_verdict(own_mask_hit="").expected
      and "Identity_Method" not in _bar_verdict(own_mask_hit=0).expected,
      "%s" % (_bar_verdict(own_mask_hit=0),))
check("  and one found in a mask this run declares for nobody",
      "Identity_Method" not in _bar_verdict(own_mask_key="dark").expected,
      "%s" % (_bar_verdict(own_mask_key="dark"),))
check("  while the two halves together are the claim",
      _bar_verdict().expected["Identity_Method"] == "MEASURED_COLOUR")
# AND THE OTHER HALF OF THE COLOUR EVIDENCE. v7.88. `mask_overlap=0` says no
# OTHER declared colour covers this ink; it does not say the colour THIS series
# declares does, and MEASURED_COLOUR is a claim about the second. The reader
# always knew - it found the bar in that mask - and wrote nothing down.
check("a bar that does not record its own colour claiming its ink names no "
      "series",
      "Identity_Method" not in _bar_verdict(own_mask_hit="").expected
      and "Identity_Method" not in _bar_verdict(own_mask_hit=0).expected,
      "%s" % (_bar_verdict(own_mask_hit=0),))
check("  and one found in a mask this run declares for nobody",
      "Identity_Method" not in _bar_verdict(own_mask_key="dark").expected,
      "%s" % (_bar_verdict(own_mask_key="dark"),))
check("  while the two halves together are the claim",
      _bar_verdict().expected["Identity_Method"] == "MEASURED_COLOUR")
check("  and a count that is not a count says nothing about the ink",
      all("Identity_Method" not in _bar_verdict(mask_overlap=bad).expected
          for bad in ("garbage", "-1", "nan", "inf", "0.5", "")),
      "%s" % [_bar_verdict(mask_overlap=bad).expected.get("Identity_Method")
          for bad in ("garbage", "-1", "nan", "inf", "0.5", "")])
# NaN IS NOT A NUMBER, and every comparison against it is False - so a geometry
# that cannot be checked read as a geometry that agrees.
check("nan and inf are not measurements, in either verifier",
      P.finite_number("nan") is None and P.finite_number("inf") is None
      and P.finite_number("4.5") == 4.5
      and P_expected_line_style_methods_ctx(
          dict(_geo, Value_Span_Px="nan")).problems
      and _bar_verdict(top_px="nan").problems,
      "%s" % (P_expected_line_style_methods_ctx(dict(_geo, Value_Span_Px="nan")),))
check("every reader that joins to raw marks now re-derives its methods",
      set(P.EVIDENCE_VERIFIERS) == set(P.MARK_JOIN_REQUIRED)
      == {"LINE_MONO_STYLE", "BAR_COLOR", "LINE_COLOR", "LINE_MONO",
          "BOX_VIOLIN"},
      "%s" % sorted(P.EVIDENCE_VERIFIERS))
# AND THE JOIN ASKS IT THE SAME WAY IT ASKS THE OTHER ONE. The call site is table
# driven - `EVIDENCE_VERIFIERS[mark_type]` - so what has to be checked here is
# that the entry answers in the two codes the finalizer branches on.
_claimed = dict(Identity_Method="MEASURED_COLOUR",
                Value_Method="BAR_OUTLINE_CENTER",
                Dispersion_Method="DIRECT_CONNECTED_CAP")
check("a BAR_COLOR mark that cannot answer is incomplete, and one that "
      "disagrees is a contradiction",
      P.evidence_failure("BAR_COLOR", dict(_bar, mask_overlap=1), _claimed,
                         _BAR_CONTEXT)[0] == "METHOD_EVIDENCE_INCOMPLETE"
      and P.evidence_failure(
          "BAR_COLOR", dict(_bar, Errorbar_Stem_Confirmed="FALSE", cap_px=None,
                            dispersion=None),
          _claimed, _BAR_CONTEXT)[0] == "METHOD_CONTRADICTS_EVIDENCE"
      and P.evidence_failure("BAR_COLOR", _bar, _claimed, _BAR_CONTEXT)
      == ("", ""),
      "%s" % (P.evidence_failure("BAR_COLOR", _bar, _claimed, _BAR_CONTEXT),))
# AND WITHOUT THE AXIS IT ANSWERS NOTHING. A verifier handed no calibration can
# compare the mark's numbers to each other and not to the figure, and "the two
# numbers I made up agree" is not evidence that a pixel row became a value.
check("  and a verifier handed no calibration refuses rather than assuming one",
      P.evidence_failure("BAR_COLOR", _bar, _claimed)[0]
      == "METHOD_EVIDENCE_INCOMPLETE",
      "%s" % (P.evidence_failure("BAR_COLOR", _bar, _claimed),))
# THE ARITHMETIC ITSELF. Every number on a bar mark is a pixel row put through
# the panel's y calibration, and until v7.85 nothing re-computed it: a mean of
# 999 passed as long as it was not equal to the fill-edge reading.
check("a mean that is not what its own pixel row reads is refused",
      "Value_Method" not in _bar_verdict(mean="999").expected
      and _bar_verdict(mean="999").problems,
      "%s" % (_bar_verdict(mean="999"),))
check("  and so is a top_px moved while the mean stays",
      "Value_Method" not in _bar_verdict(top_px="150.0").expected,
      "%s" % (_bar_verdict(top_px="150.0"),))
check("  and a fill-edge reading that is not what the fill edge reads",
      "Value_Method" not in _bar_verdict(
          mean_if_read_at_fill_edge="42").expected)
check("a dispersion that is not the cap-to-top distance is refused",
      "Dispersion_Method" not in _bar_verdict(dispersion="9.9").expected
      and "Dispersion_Method" not in _bar_verdict(cap_px="150.0").expected,
      "%s" % (_bar_verdict(dispersion="9.9"),))
check("  while the reader's own arithmetic passes on both axes",
      _bar_verdict().expected["Value_Method"] == "BAR_OUTLINE_CENTER"
      and _bar_verdict().expected["Dispersion_Method"]
      == "DIRECT_CONNECTED_CAP")
# A LOG AXIS IS THE REASON THE CALIBRATION IS REBUILT rather than the formula
# copied: `slope * pixel + intercept` is the wrong answer on one, and two copies
# of the conversion are two chances to have only one of them right.
_LOG = MR.AxisCalibration.from_points([(400.0, 1.0), (100.0, 100.0)], scale="LOG")
_log_bar = dict(_bar, mean=repr(_LOG.pixel_to_value(177.5)),
                mean_if_read_at_fill_edge=repr(_LOG.pixel_to_value(180.0)),
                dispersion=repr(abs(_LOG.pixel_to_value(165.0)
                                    - _LOG.pixel_to_value(177.5))))
check("a log axis is re-computed as a log axis",
      P.expected_bar_colour_methods(
          _log_bar, {"Y_Calibration": MR._calibration_record(_LOG)}).expected
      == {"Identity_Method": "MEASURED_COLOUR",
          "Value_Method": "BAR_OUTLINE_CENTER",
          "Dispersion_Method": "DIRECT_CONNECTED_CAP"}
      and "Value_Method" not in P.expected_bar_colour_methods(
          _log_bar, _BAR_CONTEXT).expected,
      "%s" % (P.expected_bar_colour_methods(
          _log_bar, {"Y_Calibration": MR._calibration_record(_LOG)}),))

print()
print("the third: a coloured marker, whose every part existed already")
# v7.89. `LINE_COLOR` needed no new question - the colour pair is `BAR_COLOR`'s,
# the value is the marker centre through the panel's axis, and the spread is the
# two cap rows the reader now keeps. What is different is WHERE: a bar is found
# anywhere and assigned to the nearest anchor; a marker is looked for AT the
# declared column, so its own x must BE that column.
_MARKER_AXIS = MR.AxisCalibration.from_points([(440.0, 0.0), (40.0, 220.0)])
_MARKER_CONTEXT = {"Y_Calibration": MR._calibration_record(_MARKER_AXIS),
                   "Position_Anchors": {"T0": 149.0, "T1": 249.0},
                   "Series_Discriminants": {
                       "S_B": {"Mask_Key": "", "Colour_Hex": "#2d50dc",
                               "Expected_Mask": "S_B"}}}
_marker = dict(series="S_B", x_label="T0", x="149.0", mask_overlap=0,
               own_mask_hit=108.0, own_mask_key="S_B",
               Marker_Definition="MARKER_CENTER",
               marker_center_px="380.0",
               mean=repr(_MARKER_AXIS.pixel_to_value(380.0)),
               Errorbar_Top_Px="360.0", Errorbar_Bottom_Px="400.0",
               dispersion=repr(abs(_MARKER_AXIS.pixel_to_value(360.0)
                                   - _MARKER_AXIS.pixel_to_value(400.0)) / 2.0),
               Errorbar_Stem_Confirmed="TRUE")


def _marker_verdict(**over):
    return P.expected_line_colour_methods(dict(_marker, **over),
                                          _MARKER_CONTEXT)


check("a marker in its own colour at its declared column answers all three",
      _marker_verdict().expected
      == {"Identity_Method": "MEASURED_COLOUR",
          "Value_Method": "MARKER_CENTER",
          "Dispersion_Method": "DIRECT_CONNECTED_CAP"}
      and not _marker_verdict().problems, "%s" % (_marker_verdict(),))
check("  and the colour evidence is the same pair a bar answers with",
      not _marker_verdict(mask_overlap=1).expected.get("Identity_Method")
      and not _marker_verdict(own_mask_hit=0).expected.get("Identity_Method")
      and not _marker_verdict(own_mask_key="S_R").expected.get(
          "Identity_Method"),
      "%s" % (_marker_verdict(own_mask_hit=0),))
check("a marker read anywhere but its declared column is not this cell's",
      "the same number" in " ".join(_marker_verdict(x="152.0").problems),
      "%s" % (_marker_verdict(x="152.0"),))
check("  and one whose label the run declares no anchor for",
      _marker_verdict(x_label="T9").problems)
check("a stem says DIRECT_CONNECTED_CAP and its absence says UNSTEMMED_CAP",
      _marker_verdict(Errorbar_Stem_Confirmed="FALSE").expected
      ["Dispersion_Method"] == "UNSTEMMED_CAP"
      and _marker_verdict().expected["Dispersion_Method"]
      == "DIRECT_CONNECTED_CAP")
check("  and this reader has no NO_DISPERSION to give",
      P.dispersion_contract_failure("LINE_COLOR", "NO_DISPERSION")
      and _marker_verdict(dispersion=None, Errorbar_Top_Px="",
                          Errorbar_Bottom_Px="").problems,
      "%s" % (_marker_verdict(dispersion=None),))
check("the marker's own numbers are re-computed like every other reader's",
      _marker_verdict(mean="999").problems
      and _marker_verdict(dispersion="99").problems,
      "%s" % (_marker_verdict(mean="999"),))
check("  and a marker whose definition is not the centre is refused",
      "Value_Method" not in _marker_verdict(
          Marker_Definition="MARKER_TOP").expected)

print()
print("the fourth: a monochrome marker, named by shape or by fill or by neither")
# v7.90. A monochrome panel has no colour to name a series by, so it names it by
# the marker - and which of the three identity methods that is depends on what
# the MANIFEST declared, not on what the reader felt like. All three are
# re-derivable from the measurement and the declaration together.
_MONO_CONTEXT = {"Y_Calibration": MR._calibration_record(_MARKER_AXIS),
                 "Position_Anchors": {"T0": 149.0, "T1": 249.0},
                 "Series_Discriminants": {
                     "S_1": {"Marker_Shape": "CIRCLE", "Marker_Fill": "ANY"},
                     "S_FILL": {"Marker_Shape": "ANY", "Marker_Fill": "FILLED"},
                     "S_ONLY": {"Marker_Shape": "ANY", "Marker_Fill": "ANY"}}}
_mono = dict(series="S_1", x_label="T0", x="149.0",
             Marker_Definition="CIRCLE", Marker_Fill="FILLED",
             marker_fill_ratio="0.91", marker_area_px="120",
             marker_center_px="380.0",
             mean=repr(_MARKER_AXIS.pixel_to_value(380.0)),
             Errorbar_Top_Px="360.0", Errorbar_Bottom_Px="400.0",
             dispersion=repr(abs(_MARKER_AXIS.pixel_to_value(360.0)
                                 - _MARKER_AXIS.pixel_to_value(400.0)) / 2.0),
             Errorbar_Stem_Confirmed="TRUE")


def _mono_verdict(**over):
    return P.expected_line_mono_methods(dict(_mono, **over), _MONO_CONTEXT)


check("a marker of the shape its series declares is named by that shape",
      _mono_verdict().expected
      == {"Identity_Method": "MEASURED_MARKER_SHAPE",
          "Value_Method": "MARKER_CENTER",
          "Dispersion_Method": "DIRECT_CONNECTED_CAP"}
      and not _mono_verdict().problems, "%s" % (_mono_verdict(),))
check("  and one that measured as another shape is refused",
      "Identity_Method" not in _mono_verdict(
          Marker_Definition="SQUARE").expected,
      "%s" % (_mono_verdict(Marker_Definition="SQUARE"),))
check("a series told apart by FILL is named by the fill it measured",
      _mono_verdict(series="S_FILL").expected["Identity_Method"]
      == "MEASURED_MARKER_FILL"
      and "Identity_Method" not in _mono_verdict(
          series="S_FILL", Marker_Fill="OPEN",
          marker_fill_ratio="0.02").expected,
      "%s" % (_mono_verdict(series="S_FILL"),))
check("  and one series declared with neither is R1, not R0",
      _mono_verdict(series="S_ONLY").expected["Identity_Method"]
      == "DECLARED_SINGLE_SERIES"
      and P.identity_tier("DECLARED_SINGLE_SERIES") == "R1")
check("the fill state has to be the ratio's own answer",
      _mono_verdict(marker_fill_ratio="0.10").problems
      and _mono_verdict(Marker_Fill="OPEN",
                        marker_fill_ratio="0.10").expected
      .get("Identity_Method") == "MEASURED_MARKER_SHAPE"
      and P.MARKER_FILLED_RATIO == 0.58,
      "%s" % (_mono_verdict(marker_fill_ratio="0.10"),))
check("  and a fill state with no ratio behind it is not a measurement",
      _mono_verdict(marker_fill_ratio="").problems)
check("a monochrome marker is FOUND, so it is nearest-anchor like a bar",
      _mono_verdict(x="151.0").expected["Identity_Method"]
      == "MEASURED_MARKER_SHAPE"
      and _mono_verdict(x="248.0").problems,
      "%s" % (_mono_verdict(x="248.0"),))
check("all three spreads this reader can produce are re-derived",
      _mono_verdict(Errorbar_Stem_Confirmed="FALSE").expected
      ["Dispersion_Method"] == "UNSTEMMED_CAP"
      and _mono_verdict(dispersion=None, Errorbar_Top_Px="",
                        Errorbar_Bottom_Px="").expected["Dispersion_Method"]
      == "NO_DISPERSION"
      and _mono_verdict(Errorbar_Top_Px="").problems
      and "Dispersion_Method" not in _mono_verdict(
          Errorbar_Top_Px="").expected
      and "Dispersion_Method" not in _mono_verdict(dispersion=None).expected,
      "%s" % (_mono_verdict(dispersion=None, Errorbar_Top_Px="",
                            Errorbar_Bottom_Px=""),))
check("  and the numbers are re-computed like every other reader's",
      _mono_verdict(mean="999").problems
      and _mono_verdict(dispersion="99").problems)
check("a series this run does not declare cannot be measured as one",
      _mono_verdict(series="S_NOWHERE").problems,
      "%s" % (_mono_verdict(series="S_NOWHERE"),))

print()
print("the fifth: a box, whose evidence is five lines and their widths")
# v7.91. The last of the five join readers, and the most literal evidence in the
# package: five horizontal lines, three of them wide enough to be the box. The
# reader refuses a panel that does not show all five - a violin with a median
# dot is not a five-number summary - and the verifier re-derives that refusal
# from what was recorded rather than trusting that it happened.
_BOX_AXIS = MR.AxisCalibration.from_points([(450.0, 0.0), (50.0, 100.0)])
_box_rows = [370.0, 330.0, 274.0, 206.0, 122.0]
_BOX_CONTEXT = {"Y_Calibration": MR._calibration_record(_BOX_AXIS),
                "Position_Anchors": {"G0": 200.0, "G1": 400.0},
                "Series_Discriminants": {"S_ONE": {}}}
_box = dict(x_label="G0", x="200.0", Marker_Definition="BOX_OVERLAY",
            Summary_Type="MEDIAN_IQR_RANGE",
            Box_Line_Rows_Px=";".join(repr(r) for r in _box_rows),
            Box_Line_Widths_Px="14;26;26;26;14",
            whisker_lower=repr(_BOX_AXIS.pixel_to_value(370.0)),
            q1=repr(_BOX_AXIS.pixel_to_value(330.0)),
            median=repr(_BOX_AXIS.pixel_to_value(274.0)),
            q3=repr(_BOX_AXIS.pixel_to_value(206.0)),
            whisker_upper=repr(_BOX_AXIS.pixel_to_value(122.0)))


def _box_verdict(**over):
    return P.expected_box_violin_methods(dict(_box, **over), _BOX_CONTEXT)


check("a box of five lines answers all three, and its identity is R1",
      _box_verdict().expected
      == {"Identity_Method": "DECLARED_SINGLE_SERIES",
          "Value_Method": "BOX_GEOMETRY",
          "Dispersion_Method": "DIRECT_BOX_GEOMETRY"}
      and not _box_verdict().problems
      and P.identity_tier("DECLARED_SINGLE_SERIES") == "R1",
      "%s" % (_box_verdict(),))
check("  and a panel that declares two series cannot claim one was declared",
      P.expected_box_violin_methods(
          _box, dict(_BOX_CONTEXT,
                     Series_Discriminants={"A": {}, "B": {}})).problems,
      "%s" % (P.expected_box_violin_methods(
          _box, dict(_BOX_CONTEXT, Series_Discriminants={"A": {}, "B": {}})),))
check("four lines are not a five-number summary",
      _box_verdict(Box_Line_Rows_Px="370.0;330.0;274.0;206.0",
                   Box_Line_Widths_Px="14;26;26;26").problems,
      "%s" % (_box_verdict(Box_Line_Rows_Px="370.0;330.0;274.0;206.0",
                           Box_Line_Widths_Px="14;26;26;26"),))
check("  and neither is a violin with one wide line through it",
      "at least" in " ".join(
          _box_verdict(Box_Line_Widths_Px="14;8;26;8;14").problems)
      and MR.BOX_LINE_MIN_WIDTH_PX == 20,
      "%s" % (_box_verdict(Box_Line_Widths_Px="14;8;26;8;14"),))
check("the box has to sit between its own whisker caps",
      "not between its two cap lines" in " ".join(
          _box_verdict(Box_Line_Widths_Px="26;26;26;14;14").problems),
      "%s" % (_box_verdict(Box_Line_Widths_Px="26;26;26;14;14"),))
check("every one of the five numbers is its own row through the axis",
      all(_box_verdict(**{name: "999"}).problems
          for name in ("whisker_lower", "q1", "median", "q3",
                       "whisker_upper")),
      "%s" % (_box_verdict(median="999"),))
check("  and a box that records no rows records no evidence",
      _box_verdict(Box_Line_Rows_Px="").problems
      and "Value_Method" not in _box_verdict(Box_Line_Rows_Px="").expected)
check("  and one whose panel has no axis cannot be re-computed at all",
      P.expected_box_violin_methods(
          _box, {k: v for k, v in _BOX_CONTEXT.items()
                 if k != "Y_Calibration"}).problems)

print()
print("FDT_SCENARIOS_RUN=%d" % (PASSED[0] + len(FAILURES)))
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
