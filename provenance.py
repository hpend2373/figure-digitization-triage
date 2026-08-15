"""How a value and its series identity were decided, and what that costs a reviewer.

Every reader answers two questions about every cell - WHICH SERIES is this, and
WHAT IS THE NUMBER - and until now it answered them in reader-local fields that
stopped at the raw marks. `line_style_source` was the first, `identity_status`
and `fill_sample_status` were already there, and nothing downstream could
compare them because nothing downstream shared a vocabulary.

## Why two questions and not one

    Identity_Source   WHO decided        AUTO / HUMAN
    Identity_Method   HOW it was decided MEASURED_LINE_STYLE / ELIMINATION / ...
    Value_Method      HOW THE NUMBER
                      was arrived at     DIRECT_CURVE_INK / INTERPOLATED / ...

`AUTO/HUMAN` and `MEASURED/ELIMINATION` are different questions and one field
cannot hold both: a series named by elimination is still named automatically.
And identity and value carry DIFFERENT RISK. A cell whose mean came off the ink
and whose row heading was reasoned to is wrong in one way; a cell whose NUMBER
was reconstructed is wrong in another, and a panel-level "I looked at the
starred marks" answers the first and not the second.

## The review tier is derived, never declared

    review_tier(identity_method, value_method) = max of the two

so nobody can weaken a check by writing a lower tier in a file. A method this
module has never heard of takes the HIGHEST tier rather than the lowest: an
unregistered method is not evidence of safety.

    R0  measured          off the ink, both questions          the ordinary
                                                              panel approval
    R1  declared          one series was declared, so every    provenance
                          mark is that series - no competing   recorded, no
                          identity to get wrong                extra signature
    R2  identity inferred  the NUMBER is measured; only the    panel-level
                          row heading was reasoned to         confirmation
    R3  value             the number was reconstructed from    CELL-level
        reconstructed     neighbouring ink or from continuity  confirmation
    R4  model estimate    there was not enough ink and a fit   not finalizable;
                          produced the number                 re-read by hand

R4 is the one that cannot be bought with a signature. A reviewer looking at an
overlay cannot tell a fitted y from a read one - that is exactly what the
picture cannot show - so approving it would launder a model estimate into a
pooled measurement.
"""

import collections
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TIERS = ("R0", "R1", "R2", "R3", "R4")


#: HOW a series was named. The tier is the review this method costs.
IDENTITY_METHODS = {
    # off the ink
    "MEASURED_COLOUR": "R0",
    "MEASURED_MARKER_SHAPE": "R0",
    "MEASURED_MARKER_FILL": "R0",
    "MEASURED_LINE_STYLE": "R0",
    "MEASURED_FILL_RELATION": "R0",
    # a declaration, not a measurement - and no competing identity to get wrong
    "DECLARED_SINGLE_SERIES": "R1",
    # reasoned to, with the number still measured
    "COMPLEMENT_OF_DECLARED_STYLES": "R2",
    "FIGURE_PROTOTYPE_MATCH": "R2",
    # reasoned to across x, which is what merged ink needs
    "CONTINUITY_TRACK": "R3",
    # a person, on the cell-level channel that already exists for it
    "HUMAN_RESOLUTION": "R0",
}

#: A gap between two supports that no blind mask covers: a dash gap, a dotted
#: gap, or a stroke that fell under the threshold. All three are the FIGURE's
#: doing rather than the reader's, which is the distinction that matters.
NO_OCCLUSION = "NONE"
#: More than one kind of furniture over one gap, or furniture over only part of
#: it. Not "furniture", because the claim is that the WHOLE gap is explained.
MIXED_OCCLUSION = "MIXED"

#: The furniture a reader may claim to have removed over a whole gap. ONE
#: vocabulary, here, and `line_style_mono.BLIND_CAUSES` is built from it: the
#: reader named its masks in string literals and this module tested for two of
#: them, so `ERROR_BAR_STEM` for `ERRORBAR_STEM` - one character - would have
#: fallen through `interpolation_method` to the FURNITURE branch and priced an
#: unexplained gap at R1.
#:
#: That is the fail-open this file refuses everywhere else: an unregistered
#: identity or value method costs R4 rather than R0, and the token those methods
#: are DERIVED FROM had the opposite rule. It is a defect in a reader rather than
#: a property of a figure, so it raises instead of pricing - the same reasoning
#: `InternalReaderError` is built on, where one reader's defect stops the batch
#: rather than mis-reading 115 more publications quietly.
OCCLUSION_CAUSES = ("ERRORBAR_STEM", "HORIZONTAL_RULE", "WHISKER_CAP",
                    MIXED_OCCLUSION, NO_OCCLUSION)


def interpolation_method(span, stroke, dash_gap, occlusion):
    """Which of the four bracketed interpolations this one is.

    `INTERPOLATED_CURVE_INK` was one name over three different things, and on
    publication 397 it covered 160 of 180 cells - which made it useless as a
    review tier: R3 with a cell-level confirmation would have put 160 signatures
    in front of a reviewer, 121 of them for the reader stepping over its own
    three-pixel error-bar stem. A confirmation that fires on almost everything
    is the checkbox people learn to click.

    TWO INDEPENDENT QUESTIONS, and the measurements for both are on the row:

      WAS THE GAP OURS?   `occlusion` names the furniture this reader removed
                          over every column of the gap, or says NONE (the
                          figure drew no ink there) or MIXED (only partly
                          explained, which is not explained).

      WAS IT LOCAL?       the span against THE FIGURE'S OWN DRAWING SCALE -
                          the stroke that draws this curve and the dash gap
                          this style uses on this panel.

    LOCALITY IS NOT A FRACTION OF ANYTHING. Two candidate rules were measured
    and thrown away first. `span <= stroke + occlusion_width` passes 160 of 160,
    because the span between two supports IS the occluded columns plus one -
    arithmetic, not evidence. A fraction of the position spacing is blunt:
    `span < 0.25 * spacing` admits 144 including 23 of the 31 MIXED. Against the
    drawing scale, `span <= max(stroke, dash_gap)` admits all 121 stem
    restorations, NONE of the 8 gridline gaps, and 5 of the 31 MIXED - and it
    says the same thing at any rendering, because both references are measured
    on the figure rather than chosen in pixels.
    """
    if occlusion not in OCCLUSION_CAUSES:
        raise ValueError(
            "Occlusion_Cause=%r is not one of %s. An unrecognised cause cannot "
            "be priced: the branch below would read it as furniture this reader "
            "removed and charge R1 for a gap nobody has explained"
            % (occlusion, "/".join(OCCLUSION_CAUSES)))
    reach = max(float(stroke or 0), float(dash_gap or 0))
    if float(span or 0) > reach:
        # Wider than anything the figure draws at this scale. Whatever covered
        # it, the ink between the supports was not this curve's own width.
        return "NONLOCAL_INTERPOLATION"
    if occlusion == NO_OCCLUSION:
        return "RESTORED_LINE_PATTERN_GAP"
    if occlusion == MIXED_OCCLUSION:
        return "LOCAL_BRACKETED_INTERPOLATION"
    return "RESTORED_MASKED_FURNITURE"


#: HOW the number was arrived at.
VALUE_METHODS = {
    "BAR_OUTLINE_CENTER": "R0",
    "MARKER_CENTER": "R0",
    "BOX_GEOMETRY": "R0",
    # An r, a rho or a tau, computed from measured marker centres. R0 because
    # every coordinate in it was read off the ink and the point file ships beside
    # the value; whether the reader found ALL the study's points is a different
    # question, and one no tier can answer - `Point_Count_Agreement` and
    # `Overplotting_Possible` gate it, and a panel that fails them produces no
    # association at all rather than one at a worse tier.
    "POINT_CLOUD_ASSOCIATION": "R0",
    "DIRECT_CURVE_INK": "R0",
    "MANUAL_DIGITIZED": "R0",
    # A GAP THIS READER MADE, no wider than the figure's own drawing scale. The
    # stem, rule or cap covering every column of it was removed so a tall glyph
    # could not be traced as a curve, and that removal takes the curve's own two
    # or three pixels with it. Stepping back over it restores a printed stroke;
    # it does not reconstruct anything the figure did not draw. R1, and no
    # signature: 121 of 397's 180 cells are this, and a confirmation that fires
    # on two thirds of every panel is one people learn to click.
    "RESTORED_MASKED_FURNITURE": "R1",
    # A gap the FIGURE drew - a dash or dotted gap - no wider than the dash
    # period measured on this panel. Also a printed stroke, restored.
    "RESTORED_LINE_PATTERN_GAP": "R1",
    # Local and bracketed, but the gap is not fully explained: two kinds of
    # furniture over it, or furniture over part of it. The number is still
    # measured between two real supports, and which of the two explanations
    # applies is what a person has to look at. Cell-level confirmation.
    "LOCAL_BRACKETED_INTERPOLATION": "R3",
    # Wider than anything this figure draws at this scale. A guess about a curve
    # nobody sampled, and not rescuable by a signature.
    "NONLOCAL_INTERPOLATION": "R4",
    # Kept for the readers that have not been taught the four above. Anything
    # still emitting it has not measured its own locality, and until it does the
    # honest tier is the one that asks for the most.
    "INTERPOLATED_CURVE_INK": "R3",
    # the top or bottom edge of a run of ink too thick to be one stroke
    "MERGED_RUN_EDGE": "R3",
    # ink on ONE side only. Not interpolation: nothing brackets the answer.
    "EXTRAPOLATED_CURVE_INK": "R4",
    # no usable ink at all; the fitted curve produced the number
    "FIT_FALLBACK": "R4",
}

#: What an unregistered method costs. The highest, because an unregistered
#: method is not evidence of safety - it is a reader this file has not been
#: taught about, and the tier is the only thing standing between it and a
#: pooled number.
UNKNOWN_TIER = "R4"

#: WHICH PAIRS EACH READER MAY CLAIM. The registry prices a method; this says
#: whether the reader that produced the row could have arrived at it.
#:
#: ## Why a matrix, and why it is not enough on its own
#:
#: Blank and unregistered methods are refused, so the remaining way to buy a
#: cheap tier is to write down a REGISTERED method that is not the one the
#: evidence supports: `MEASURED_FILL_RELATION` for a bar matched against another
#: group's prototypes (R2 -> R0), `MEASURED_LINE_STYLE` for a style named by
#: elimination (R2 -> R0), `DIRECT_CURVE_INK` for a number a fit produced
#: (R4 -> R0). Every file hash in the run is then correct: the values were
#: written that way by whoever produced them.
#:
#: This table closes the crudest version - a pair no reader of that mark type
#: could ever emit, like `BOX_VIOLIN` claiming it measured a line style, or
#: `LINE_COLOR` claiming a human resolution it has no channel for. What it
#: cannot do is check a pair that reader COULD have emitted against what this
#: particular row's evidence actually was; that needs a durable artifact to
#: compare with, which is why `BAR_MONO` additionally carries
#: `Auto_Identity_Method` in `mono_bar_geometry.csv` and the finalizer joins on
#: it. The other readers have no equivalent artifact yet, and saying so is worth
#: more than a matrix that implies they do.
METHOD_CONTRACT = {
    "LINE_COLOR": {("MEASURED_COLOUR", "MARKER_CENTER")},
    "LINE_MONO": {("MEASURED_MARKER_SHAPE", "MARKER_CENTER"),
                  ("MEASURED_MARKER_FILL", "MARKER_CENTER"),
                  ("DECLARED_SINGLE_SERIES", "MARKER_CENTER")},
    # The one reader that reconstructs values, so the one with a value method
    # per gap. Its identity is measured off the ink or named by elimination.
    "LINE_MONO_STYLE": {(identity, value)
                        for identity in ("MEASURED_LINE_STYLE",
                                         "COMPLEMENT_OF_DECLARED_STYLES",
                                         "CONTINUITY_TRACK")
                        for value in ("DIRECT_CURVE_INK",
                                      "RESTORED_MASKED_FURNITURE",
                                      "RESTORED_LINE_PATTERN_GAP",
                                      "LOCAL_BRACKETED_INTERPOLATION",
                                      "INTERPOLATED_CURVE_INK",
                                      "MERGED_RUN_EDGE",
                                      "NONLOCAL_INTERPOLATION",
                                      "EXTRAPOLATED_CURVE_INK",
                                      "FIT_FALLBACK")},
    "BAR_COLOR": {("MEASURED_COLOUR", "BAR_OUTLINE_CENTER")},
    "BAR_MONO": {("MEASURED_FILL_RELATION", "BAR_OUTLINE_CENTER"),
                 ("FIGURE_PROTOTYPE_MATCH", "BAR_OUTLINE_CENTER"),
                 ("HUMAN_RESOLUTION", "BAR_OUTLINE_CENTER")},
    "BOX_VIOLIN": {("DECLARED_SINGLE_SERIES", "BOX_GEOMETRY")},
    "SCATTER": {("MEASURED_COLOUR", "POINT_CLOUD_ASSOCIATION"),
                ("DECLARED_SINGLE_SERIES", "POINT_CLOUD_ASSOCIATION")},
}


#: And which dispersion methods each reader can reach. Separate from the pair
#: table because the axis is separate: a reader's spread comes from its own
#: geometry, and `BOX_VIOLIN` claiming it followed a stem to a cap is as
#: impossible as `LINE_COLOR` claiming a human resolution.
DISPERSION_CONTRACT = {
    # NOT `NO_DISPERSION`: `read_line_marker_panel` takes the connected column
    # through the marker as the extent, so every mark it emits has one. The same
    # reachability question `UNSTEMMED_CAP` failed for BAR_COLOR in v7.84, asked
    # of this reader while writing its verifier.
    "LINE_COLOR": {"DIRECT_CONNECTED_CAP", "UNSTEMMED_CAP"},
    "LINE_MONO": {"DIRECT_CONNECTED_CAP", "UNSTEMMED_CAP", "NO_DISPERSION"},
    # NOT `RESTORED_MASKED_CAP`: it is reserved, and listing it here said this
    # reader could produce it, which is what a contract is for saying.
    "LINE_MONO_STYLE": {"DIRECT_CONNECTED_CAP", "NO_DISPERSION"},
    # NOT `UNSTEMMED_CAP`: `bar_reader` sets `cap_px` only inside the branch
    # that also sets `stem_ok`, so a cap without a stem is a shape it cannot
    # produce. Listing it said this reader could, which is what a contract is
    # for saying - the same mistake `RESTORED_MASKED_CAP` was removed from
    # LINE_MONO_STYLE for. The line readers keep it: theirs is reachable.
    "BAR_COLOR": {"DIRECT_CONNECTED_CAP", "NO_DISPERSION"},
    "BAR_MONO": {"DIRECT_CONNECTED_CAP", "NO_DISPERSION"},
    "BOX_VIOLIN": {"DIRECT_BOX_GEOMETRY"},
    "SCATTER": {"NO_DISPERSION"},
}


#: THE READERS WITH NO DURABLE ROUTE OF THEIR OWN. `BAR_MONO` writes
#: `mono_bar_geometry.csv` and `SCATTER` writes a point cloud, and both are joined
#: to their values by hashes that predate the mark join. These five have neither:
#: the raw marks are the only durable record of what was measured, so a value of
#: theirs that cites no mark cites nothing at all, and until v7.75 that blank was
#: read as "a reader that does not stamp its marks" and skipped.
#:
#: Keyed by `Mark_Type` because that is what the queue records and what
#: `METHOD_CONTRACT` is keyed by; a reader added later is refused by the matrix
#: until it appears in both.
MARK_JOIN_REQUIRED = frozenset((
    "LINE_COLOR", "LINE_MONO", "LINE_MONO_STYLE", "BAR_COLOR", "BOX_VIOLIN",
))


#: PRICED, AND NOT YET PRODUCIBLE. A method in this set has a tier and a place in
#: the ladder and no reader that can emit it: the vocabulary is ahead of the
#: readers on purpose, because pricing a case before meeting it is how the ladder
#: stays a ladder rather than a list of whatever the last figure needed.
#:
#: Saying so is the point. `RESTORED_MASKED_CAP` sat in the registry and in one
#: reader's contract for a release looking exactly like a capability - and a
#: capability nothing produces and no forward test exercises is a claim about
#: software that does not exist. What it needs before it becomes one:
#:
#:   the reader keeps its cap masks apart instead of one `blind` union
#:   a candidate cap with ink on BOTH sides of the covered stretch
#:   the whole stretch explained by one known mask
#:   the restored cap width inside the panel's own measured cap widths
#:   a real figure where that happens, read against a person's reading
#:
#: `SOURCE_TRANSCRIBED` is reserved for a different reason: it belongs to a value
#: copied from the paper's text, and no reader reads text.
RESERVED_METHODS = frozenset((
    "RESTORED_MASKED_CAP", "INTERPOLATED_DISPERSION", "FITTED_DISPERSION",
    "DIRECT_BOUND_PAIR", "SOURCE_TRANSCRIBED",
))


def dispersion_contract_failure(mark_type, dispersion_method):
    """Why this reader could not have got its spread that way, or ""."""
    allowed = DISPERSION_CONTRACT.get(str(mark_type or "").strip().upper())
    text = str(dispersion_method or "").strip()
    if allowed is None or not text:
        return ""
    if text in allowed:
        return ""
    return ("%s cannot produce Dispersion_Method=%s; its spread comes from %s"
            % (mark_type, text, " or ".join(sorted(allowed))))


#: The three method fields, in one place, because everything that carries or
#: compares them has to carry or compare all three.
METHOD_FIELDS = ("Identity_Method", "Value_Method", "Dispersion_Method")


#: What a re-derivation came to: the methods the evidence implies, and the
#: questions it could not answer. Two fields rather than one dict, because
#: "the evidence says DIRECT_CURVE_INK" and "the evidence does not say" are
#: different answers and collapsing them is how a partial verifier passes: an
#: axis it could not derive was simply absent from the dict, and an absent
#: expectation compared equal to whatever the value claimed.
EvidenceVerdict = collections.namedtuple("EvidenceVerdict",
                                         "expected problems")


def _off_by(recorded, expected):
    """Is this number NOT the one the arithmetic produces?

    Compared exactly, up to the same float noise the pixel geometry allows.
    Both sides are the same formula on the same numbers - the reader ran
    `pixel_to_value` at read time and this runs it again on the calibration the
    run declared - so a difference is a different measurement, not a rounding.
    Scaled by the magnitude, because an axis in millilitres and an axis in
    milliseconds do not share an absolute tolerance.

    Both arguments are numbers by the time this is called: every caller has
    already refused a mark that is missing one, and a `None` here would be this
    function inventing a comparison rather than making one.
    """
    return abs(recorded - expected) > PIXEL_EPSILON * max(1.0, abs(expected))


def finite_number(value):
    """`value` as a float, or None if it is not one - and NaN is not one.

    `float("nan")` succeeds, and every comparison against NaN is False, so a
    mark carrying `nan` passed each `abs(a - b) > EPSILON` test in this module
    silently: a geometry that cannot be checked read as a geometry that agrees.
    `inf` is the same shape from the other side.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


#: What two pixel measurements may differ by and still be the same measurement.
#: FLOAT NOISE, NOT A TOLERANCE: `right - left` and a recorded span are the same
#: subtraction done twice, and a hundredth of a pixel is not a distance any
#: reader means. Widening this to absorb a real disagreement would be widening a
#: constant to make something pass.
PIXEL_EPSILON = 1e-9


#: What a LINE_MONO_STYLE mark's support columns can legitimately look like, and
#: what each shape means. `_ink_at` writes the SAME column into both fields when
#: the ink is on one side only, so "one side recorded and the other blank" is not
#: this reader's one-sided encoding - it is a shape no reader in this package
#: produces, and a shape nothing can be re-derived from.
SUPPORT_SHAPES = ("NO_SUPPORT", "ONE_COLUMN", "TWO_COLUMNS")


def support_shape(left, right, span, target):
    """(shape, problem) for a mark's support geometry. One of them is always "".

    EXACT, not best-effort. v7.79 checked the three geometric relations and
    returned "" whenever a field was missing or unparseable, and the caller then
    fell through to a branch that derived a method anyway:

        left=130, right=""      -> read as one-sided, which this reader never
                                   writes; DIRECT_CURVE_INK at R0
        left="foo", right="bar" -> read as bracketed, and the method came from
                                   the span and the cause alone

    So the shape is decided first and every other shape is a refusal. A verifier
    that guesses at malformed evidence is a verifier that can be fed.
    """
    number = finite_number

    if not left and not right:
        return "NO_SUPPORT", ""
    if not left or not right:
        return "", ("the mark records one support column (%s) and leaves the "
                    "other blank. A value read from ink on one side carries the "
                    "same column in both fields; this is neither shape"
                    % (left or right))
    left_px, right_px = number(left), number(right)
    span_px, target_px = number(span), number(target)
    unreadable = [name for name, value in (("Value_Support_Left_Px", left_px),
                                           ("Value_Support_Right_Px", right_px),
                                           ("Value_Span_Px", span_px),
                                           ("x", target_px))
                  if value is None]
    if unreadable:
        return "", ("the mark's %s %s not a number, and a geometry that cannot "
                    "be measured cannot support a method"
                    % (", ".join(unreadable),
                       "are" if len(unreadable) > 1 else "is"))
    if left_px == right_px:
        want = abs(left_px - target_px)
        if abs(span_px - want) > PIXEL_EPSILON:
            return "", ("the mark was read from column %s and sits at %s, which "
                        "is %s away, and it records a span of %s"
                        % (left, target, want, span))
        return "ONE_COLUMN", ""
    if not left_px < target_px < right_px:
        return "", ("the mark sits at %s and its supports are %s and %s, which "
                    "do not bracket it - an interpolation is between two columns "
                    "and this is not between them" % (target, left, right))
    want = right_px - left_px
    if abs(span_px - want) > PIXEL_EPSILON:
        return "", ("the mark was measured between %s and %s, a gap of %s, and "
                    "it records a span of %s" % (left, right, want, span))
    return "TWO_COLUMNS", ""


def expected_line_style_methods(mark, context=None):
    """The three methods a LINE_MONO_STYLE mark's own evidence implies.

    RE-DERIVED, not read. The matrix says which methods a reader COULD emit; this
    says which one THIS mark's measurements come to, and the difference is the
    whole gap between "possible" and "true". Everything below is on the mark
    record already, because `line_style_mono` had to measure it to decide - so
    nothing new is trusted, and a value row claiming a cheaper method than its own
    ink supports has no way through.

    `context` carries the run's own declaration, and from v7.87 this reader uses
    it the way `BAR_COLOR`'s does: every number on the mark is a pixel row put
    through the panel's y calibration, and the rows are on the record - the
    marker centre the value was read at, and the two cap rows a spread was
    measured between. Re-deriving the METHOD from the support columns says how
    the number was got; re-computing the number says it is the one those pixels
    produce.

    TOTAL from v7.76: every axis ends with an expectation or with a problem, and
    never with silence. Until then the function returned only what it could answer
    and the caller compared only that, so a mark missing the evidence for an axis
    bought whatever the value claimed on it - the fail-open this whole family of
    checks keeps arriving at from a new direction. `_axes_are_total` asserts the
    invariant over generated marks rather than trusting this docstring.
    """
    def field(name):
        # NOT `or ""`. A span of ZERO is the most important value this function
        # reads - it is what makes a support column a direct observation rather
        # than a carry - and `0 or ""` is the empty string. While the span
        # defaulted to "0" the bug was invisible, because the default happened to
        # be the answer; taking the default away made every direct observation
        # read as evidence that was never recorded.
        value = mark.get(name)
        return "" if value is None else str(value).strip()

    out, problems = {}, []
    source = field("line_style_source")
    if source:
        out["Identity_Method"] = ("MEASURED_LINE_STYLE" if source == "MEASURED"
                                  else "COMPLEMENT_OF_DECLARED_STYLES"
                                  if source == "COMPLEMENT_OF_DECLARED_STYLES"
                                  else source)
    else:
        problems.append("the mark records no line_style_source, so how its "
                        "series was named cannot be re-derived")
    left = field("Value_Support_Left_Px")
    right = field("Value_Support_Right_Px")
    span = field("Value_Span_Px")
    target = field("x")
    shape, why = support_shape(left, right, span, target)
    if why:
        problems.append(why)
    elif shape == "NO_SUPPORT":
        # No ink either side: the fit produced the number, whatever else the row
        # says about spans and occlusions.
        out["Value_Method"] = "FIT_FALLBACK"
    elif shape == "TWO_COLUMNS":
        cause = field("Occlusion_Cause")
        if cause in OCCLUSION_CAUSES:
            out["Value_Method"] = interpolation_method(
                mark.get("Value_Span_Px"), mark.get("Local_Stroke_Px"),
                mark.get("Expected_Dash_Gap_Px"), cause)
        else:
            problems.append("the mark was measured between two columns and "
                            "gives its occlusion cause as %s, which is not one "
                            "this registry prices"
                            % (cause or "nothing"))
    else:
        # ONE COLUMN, AND THE SPAN SAYS WHICH KIND. `_ink_at` reports the single
        # supporting column in BOTH fields when the ink is on one side only, and
        # the span is then the distance it was carried sideways; a directly
        # observed value is the same column with a span of zero - and
        # `support_shape` has already checked that the span IS that distance.
        #
        # The first version of this verifier read `left == right` as DIRECT and
        # disagreed with the reader on 9 of publication 397's 87 line marks - all
        # nine one-sided carries at a non-zero span, which is the case that most
        # needs to keep its R4. Running the derivation against a real figure is
        # what found it; the fixtures agreed with it perfectly.
        out["Value_Method"] = ("DIRECT_CURVE_INK" if abs(float(span)) <= PIXEL_EPSILON
                               else "EXTRAPOLATED_CURVE_INK")
    stem = field("Errorbar_Stem_Confirmed").upper()
    if stem in ("TRUE", "FALSE"):
        out["Dispersion_Method"] = ("DIRECT_CONNECTED_CAP" if stem == "TRUE"
                                    else "NO_DISPERSION")
    else:
        problems.append("the mark does not say whether a stem connected its cap "
                        "(Errorbar_Stem_Confirmed=%s), so how its spread was got "
                        "cannot be re-derived" % (stem or "blank"))
    problems.extend(_curve_arithmetic_problems(field, finite_number, context))
    return EvidenceVerdict(out, problems)


def _curve_arithmetic_problems(field, number, context):
    """Do this mark's own pixel rows produce its own numbers?

    The same question v7.85 asked of a bar, and the answer was the same shape:
    until it was asked, a producer could move `marker_center_px`, keep the mean
    or invent one, re-stamp everything, and the value-to-mark join found two
    fields that agreed with each other. The axis is the third party.

        mean         == calibrate(marker_center_px)
        dispersion   == |calibrate(top) - calibrate(bottom)| / 2

    The two cap rows were added to the reader in v7.87 for this: it kept the
    calibrated bounds and threw the pixels away, so the conversion was a claim
    nothing downstream could repeat. A mark with no dispersion needs neither.
    """
    import mark_readers as MR                                      # noqa: E402
    axis = MR.calibration_from_record((context or {}).get("Y_Calibration"))
    centre, mean = number(field("marker_center_px")), number(field("mean"))
    spread = number(field("dispersion"))
    top, bottom = (number(field("Errorbar_Top_Px")),
                   number(field("Errorbar_Bottom_Px")))
    if centre is None or mean is None:
        return ["the mark records no %s, so the number it reports cannot be "
                "re-computed from the pixels it was read at"
                % ("marker_center_px" if centre is None else "mean")]
    if axis is None:
        return ["this run declares no y calibration for the panel, so what the "
                "mark's own pixel row should have read cannot be re-computed"]
    problems = []
    if _off_by(mean, axis.pixel_to_value(centre)):
        problems.append("the mark was read at row %s, which is %s under this "
                        "run's y calibration, and it reports %s"
                        % (centre, axis.pixel_to_value(centre), mean))
    if spread is None:
        return problems
    if top is None or bottom is None:
        problems.append("the mark reports a dispersion of %s and no cap rows to "
                        "have measured it between" % spread)
    elif _off_by(spread, abs(axis.pixel_to_value(top)
                             - axis.pixel_to_value(bottom)) / 2.0):
        problems.append("the cap rows %s and %s are %s apart under this run's y "
                        "calibration, half of which is %s, and the mark reports "
                        "a dispersion of %s"
                        % (top, bottom,
                           abs(axis.pixel_to_value(top)
                               - axis.pixel_to_value(bottom)),
                           abs(axis.pixel_to_value(top)
                               - axis.pixel_to_value(bottom)) / 2.0, spread))
    return problems


def expected_bar_colour_methods(mark, context=None):
    """The three methods a BAR_COLOR mark's own evidence implies.

    The second verifier, and the reader worth doing next: `BAR_COLOR` reaches
    R0 on every axis, which means every one of its cells goes into a pool on the
    strength of three words nothing re-derived.

        identity     the bar was found in a mask built from the colour this
                     series declares - unless ANOTHER declared colour's mask
                     claims the same ink, and then the bar is not evidence of
                     either identity
        value        `Bar_Top_Definition` says which edge the number came from,
                     and the reader records what the number WOULD have been at
                     the fill edge. A mean equal to that one, from a bar whose
                     fill edge is a different pixel row, was not read at the
                     outline centre whatever the field says
        dispersion   the stem and the cap, the two facts the reader decides
                     from: a cap a stem reaches is DIRECT_CONNECTED_CAP and no
                     cap at all is NO_DISPERSION. This reader has no third
                     answer - see `DISPERSION_CONTRACT`

    EVERY FIELD IT DECIDES FROM IS REQUIRED. v7.83 asked whether a field
    contradicted the claim and let a missing one through, so a mark carrying
    `mask_overlap="garbage"`, no fill-edge reading and no cap took all three
    methods at R0: the identity because a non-number is not positive, the value
    because the fill-edge comparison was skipped, the spread because a number
    was present. A verifier that only refutes is a verifier that can be starved.

    `Position_Assignment` is checked whenever the mark sits at a declared
    x_label. It is not a method - it says whether the label came from a declared
    anchor or from counting bars left to right - and `grid_engine` refuses a
    VALUE that admits to counting. A value that drops the column passes that
    gate, and the mark cannot: it is hashed.
    """
    def field(name):
        value = mark.get(name)
        return "" if value is None else str(value).strip()

    def number(name):
        return finite_number(field(name))

    out, problems = {}, []
    # WHAT THE PIXELS SHOULD HAVE READ, under the calibration the run declared.
    # Not the artifact's own copy of it: `finalize_batch` hands the envelope it
    # re-derived from the verified manifests, so this is the figure's axis
    # rather than the producer's claim about it.
    # IMPORTED HERE, not at the top: `mono_bar_geometry` imports this module and
    # `mark_readers` imports that one, so a module-level import closes a cycle
    # and leaves whichever gets there first half-built. The conversion lives in
    # `mark_readers` because that is where the calibration is fitted, and one
    # copy of `slope * pixel + intercept` is the point - a second one would be
    # wrong on a log axis eventually.
    import mark_readers as MR                                      # noqa: E402
    axis = MR.calibration_from_record((context or {}).get("Y_Calibration"))
    # THE COLOUR PAIR, shared with `LINE_COLOR`: no other declared mask over the
    # ink, this series' own mask over it, and that mask being the one the run
    # declares. Half of it was missing until v7.88 - `mask_overlap=0` says no
    # OTHER colour covers the ink, and `MEASURED_COLOUR` is a claim about this
    # one.
    identity = _colour_identity_problems(field, number, context)
    if identity:
        problems.extend(identity)
    else:
        out["Identity_Method"] = "MEASURED_COLOUR"
    edge = field("Bar_Top_Definition").upper()
    top, fill = number("top_px"), number("fill_top_px")
    mean, at_fill = number("mean"), number("mean_if_read_at_fill_edge")
    missing = [name for name, value in (("top_px", top), ("fill_top_px", fill),
                                        ("mean", mean),
                                        ("mean_if_read_at_fill_edge", at_fill))
               if value is None]
    if edge != "OUTLINE_CENTER":
        problems.append("the mark gives its Bar_Top_Definition as %s, and this "
                        "reader measures the outline centre"
                        % (edge or "nothing"))
    elif missing:
        # THE FILL-EDGE READING IS EVIDENCE, not an optional extra. It is the
        # only thing on the mark that can tell an outline-centre reading from a
        # fill-edge one, so a mark without it cannot support the claim - and
        # skipping the comparison when it was absent is what let a producer
        # simply not write it.
        problems.append("the mark records no %s, so which edge its number came "
                        "from cannot be re-derived" % ", ".join(missing))
    elif abs(top - fill) > PIXEL_EPSILON and abs(mean - at_fill) <= PIXEL_EPSILON:
        problems.append("the mark's mean is what its FILL EDGE would have read "
                        "(%s) and its outline centre is a different row (%s "
                        "against %s), so the number did not come from the "
                        "outline centre it claims" % (at_fill, top, fill))
    elif axis is None:
        # THE ARITHMETIC IS THE CLAIM. Without the axis this module can compare
        # the mark's numbers to each other and not to the figure, and "the two
        # numbers I made up are consistent" is not evidence that a pixel row was
        # converted to a value.
        problems.append("this run declares no y calibration for the panel, so "
                        "what the mark's own pixel rows should have read cannot "
                        "be re-computed")
    elif _off_by(mean, axis.pixel_to_value(top)) \
            or _off_by(at_fill, axis.pixel_to_value(fill)):
        problems.append("the mark's pixel rows do not produce its numbers under "
                        "this run's y calibration: %s reads %s and the mark says "
                        "%s; %s reads %s and the mark says %s"
                        % (top, axis.pixel_to_value(top), mean,
                           fill, axis.pixel_to_value(fill), at_fill))
    else:
        out["Value_Method"] = "BAR_OUTLINE_CENTER"
    stem = field("Errorbar_Stem_Confirmed").upper()
    cap, spread = number("cap_px"), number("dispersion")
    if stem not in ("TRUE", "FALSE"):
        problems.append("the mark does not say whether a stem connected its cap "
                        "(Errorbar_Stem_Confirmed=%s), so how its spread was got "
                        "cannot be re-derived" % (stem or "blank"))
    elif stem == "TRUE" and (cap is None or spread is None or top is None):
        problems.append("the mark says a stem connected its cap and records no "
                        "%s for it to have measured"
                        % ("cap_px" if cap is None else
                           "dispersion" if spread is None else "top_px"))
    elif stem == "TRUE" and axis is None:
        problems.append("this run declares no y calibration for the panel, so "
                        "what the cap this mark followed should have measured "
                        "cannot be re-computed")
    elif stem == "TRUE" and _off_by(
            spread, abs(axis.pixel_to_value(cap) - axis.pixel_to_value(top))):
        problems.append("the cap at row %s and the bar top at row %s are %s "
                        "apart under this run's y calibration, and the mark "
                        "records a dispersion of %s"
                        % (cap, top,
                           abs(axis.pixel_to_value(cap)
                               - axis.pixel_to_value(top)), spread))
    elif stem == "TRUE":
        out["Dispersion_Method"] = "DIRECT_CONNECTED_CAP"
    elif cap is None and spread is None:
        out["Dispersion_Method"] = "NO_DISPERSION"
    else:
        # NO THIRD ANSWER. This reader accepts a cap only when a stem physically
        # reaches it, so "a cap and no stem" is not an unstemmed cap it declined
        # to follow - it is a mark whose three fields disagree with each other.
        problems.append("the mark says no stem connected a cap and still "
                        "records cap_px=%s and dispersion=%s; this reader "
                        "measures a cap only through a stem"
                        % (field("cap_px") or "nothing",
                           field("dispersion") or "nothing"))
    placed, label = field("Position_Assignment").upper(), field("x_label")
    if label and placed != "DECLARED_ANCHOR":
        problems.append("this bar sits at %s and its label came from %s rather "
                        "than from a declared anchor"
                        % (label, placed or "nothing recorded"))
    elif placed and placed != "DECLARED_ANCHOR":
        problems.append("this bar's x label came from %s rather than from a "
                        "declared anchor" % placed)
    elif label:
        problems.extend(_anchor_problems(mark, number("x"),
                                         number("slot_residual_px"), label,
                                         context))
    if axis is not None:
        problems.extend(_baseline_problems(field, number, axis, context))
    return EvidenceVerdict(out, problems)


def _anchor_problems(mark, x_px, residual, label, context):
    """Is this bar AT the position it says it is?

    `DECLARED_ANCHOR` was taken as the whole answer, and it is only half of one:
    it says the reader used declared anchors, not that THIS mark is nearest to
    the one it names. Two bars in a panel could exchange their `x_label`s, have
    their cells and hashes recomputed to match, and pass everything - the
    heading exchange v7.74 closed, reopened at the pixel-to-position boundary.

    `bar_reader` assigns the NEAREST declared column within a tolerance, and
    records the distance it accepted, so all of it is re-derivable from the
    verified position rows.
    """
    anchors = (context or {}).get("Position_Anchors") or {}
    if not anchors:
        return ["this bar carries the label %s and this run declares no anchor "
                "pixels for the panel, so nothing says the mark is at it"
                % label]
    if x_px is None:
        return ["the mark records no x column, so the position it was assigned "
                "to cannot be re-derived"]
    distances = sorted((abs(x_px - px), pid) for pid, px in anchors.items())
    nearest, closest = distances[0][1], distances[0][0]
    problems = []
    if len(distances) > 1 and abs(distances[1][0] - closest) <= PIXEL_EPSILON:
        problems.append("the mark at column %s is the same distance from %s and "
                        "%s, so which position it belongs to is not decidable"
                        % (x_px, nearest, distances[1][1]))
    elif label != nearest:
        problems.append("the mark sits at column %s, which is nearest the "
                        "declared anchor for %s (%s away), and it is filed under "
                        "%s" % (x_px, nearest, closest, label))
    if residual is None:
        problems.append("the mark records no slot_residual_px, so how far it "
                        "was from the anchor it was assigned to is not stated")
    elif abs(residual - abs(x_px - anchors.get(label, x_px))) > PIXEL_EPSILON:
        problems.append("the mark says it landed %s from its anchor and it is "
                        "%s from the one it names"
                        % (residual, abs(x_px - anchors.get(label, x_px))))
    # THE READER'S OWN DEFAULT, reproduced rather than approximated: half the
    # smallest gap between declared anchors, and the panel's width when there is
    # only one anchor to be near. A tolerance guessed differently here would
    # refuse marks the run accepted, or accept marks it refused.
    tolerance = (context or {}).get("Slot_Tolerance_Px")
    if tolerance is None:
        spans = sorted(anchors.values())
        gaps = [b - a for a, b in zip(spans, spans[1:])]
        box = (context or {}).get("Panel_Box") or []
        width = (abs(finite_number(box[1]) - finite_number(box[0]))
                 if len(box) == 4 and finite_number(box[0]) is not None
                 and finite_number(box[1]) is not None else None)
        tolerance = 0.5 * min(gaps) if gaps else width
    if tolerance is not None and closest > float(tolerance) + PIXEL_EPSILON:
        problems.append("the mark at column %s is %s from the nearest declared "
                        "anchor, and this panel accepts %s"
                        % (x_px, closest, tolerance))
    return problems


def _baseline_problems(field, number, axis, context):
    """Which end of the bar was measured, and which side of it the cap is on.

    A bar is measured from its BASELINE: the data end is the end further from
    it, and the cap is further still. Re-computing `calibrate(top_px)` says the
    number matches the row; it does not say the row was the right end. Move the
    cap to between the top and the baseline, update the dispersion to the new
    distance, and the arithmetic is perfect while the cap is not an error bar's.
    """
    declared = (context or {}).get("Baseline_Value")
    top, cap = number("top_px"), number("cap_px")
    if top is None:
        return []                 # already refused where the value is derived
    text = "" if declared is None else str(declared).strip()
    # BLANK IS THE READER'S DEFAULT, which is zero: `run_panel` passes
    # `baseline_value=0.0` when the panel declares none, so a blank here is a
    # declaration of zero rather than an absence.
    baseline = finite_number(text) if text else 0.0
    if baseline is None:
        return ["this run declares Baseline_Value=%s, which is not a number a "
                "bar can be measured from" % declared]
    try:
        baseline_px = axis.value_to_pixel(baseline)
    except (ValueError, ZeroDivisionError):
        return ["this run's y calibration cannot place the declared baseline "
                "%s on the panel" % declared]
    problems = []
    box = (context or {}).get("Panel_Box") or []
    rows = [("top_px", top), ("fill_top_px", number("fill_top_px")),
            ("cap_px", cap)]
    if len(box) == 4:
        low, high = sorted((finite_number(box[2]), finite_number(box[3])))
        outside = ["%s=%s" % (name, value) for name, value in rows
                   if value is not None and not low <= value <= high]
        if outside:
            problems.append("the mark was measured at %s, outside the panel box "
                            "this run declares (%s to %s)"
                            % (", ".join(outside), low, high))
    said = field("Bar_Direction").upper()
    grows = "UP" if top < baseline_px else "DOWN"
    if said and said != grows:
        problems.append("the mark says the bar grows %s and its top row (%s) is "
                        "on the %s side of the declared baseline (%s)"
                        % (said, top, grows, baseline_px))
    if cap is not None and abs(cap - baseline_px) <= abs(top - baseline_px):
        problems.append("the cap at row %s is no further from the declared "
                        "baseline (%s) than the bar top at %s, and an error bar "
                        "is measured outward from the data end"
                        % (cap, baseline_px, top))
    return problems


def _colour_identity_problems(field, number, context):
    """Was this mark measured as the series it says, and only as that series?

    Two halves and a name, shared by every reader that names a series by
    colour: no OTHER declared mask over the ink, this series' OWN mask over it,
    and the mask it was found in being the one this run declares. The units
    differ - a bar samples one pixel inside its body, a marker counts its own
    ink across the marker - and the question does not.
    """
    overlap, overlap_px = field("mask_overlap"), number("mask_overlap")
    own, own_px = field("own_mask_hit"), number("own_mask_hit")
    declared = ((context or {}).get("Series_Discriminants")
                or {}).get(field("series")) or {}
    if not overlap or overlap_px is None or overlap_px < 0 \
            or overlap_px != int(overlap_px):
        return ["the mark gives mask_overlap as %s, which is not a count of the "
                "other declared colours claiming its ink, so its identity "
                "cannot be re-derived" % (overlap or "nothing")]
    if overlap_px > 0:
        return ["%d other declared colour(s) claim this mark's own ink; a "
                "contested mark is not evidence of either identity, and the run "
                "drops it rather than choosing" % int(overlap_px)]
    if not own or own_px is None or own_px < 1:
        return ["the mark does not record its own declared colour claiming its "
                "ink (own_mask_hit=%s), so nothing says it was measured as this "
                "series rather than merely not measured as another"
                % (own or "nothing")]
    if declared and field("own_mask_key") != declared.get("Expected_Mask"):
        return ["the mark was found in the mask %s and this run declares %s for "
                "series %s" % (field("own_mask_key") or "nothing",
                               declared.get("Expected_Mask") or "nothing",
                               field("series") or "(unnamed)")]
    return []


def expected_line_colour_methods(mark, context=None):
    """The three methods a LINE_COLOR mark's own evidence implies.

    The third verifier, and the one that needed no new question: every part of
    it exists already. The identity is the colour pair `BAR_COLOR` answers with,
    the value is the marker centre through the panel's axis, and the spread is
    the two cap rows - `_marker_and_errorbar` follows a stem from the mark to the
    cap and says whether it found one on both sides.

    `NO_DISPERSION` is not among the answers: this reader takes the connected
    column through the marker as the extent, so every mark it emits has one -
    see `DISPERSION_CONTRACT`.

    WHERE THE MARK SITS is checked differently from a bar's. A bar is found
    anywhere and assigned to the nearest declared anchor; a marker is looked for
    AT the declared column, so its own x must BE that column rather than merely
    be nearest to it.
    """
    def field(name):
        value = mark.get(name)
        return "" if value is None else str(value).strip()

    def number(name):
        return finite_number(field(name))

    out, problems = {}, []
    identity = _colour_identity_problems(field, number, context)
    if identity:
        problems.extend(identity)
    else:
        out["Identity_Method"] = "MEASURED_COLOUR"
    definition = field("Marker_Definition").upper()
    if definition != "MARKER_CENTER":
        problems.append("the mark gives its Marker_Definition as %s, and this "
                        "reader measures the marker centre"
                        % (definition or "nothing"))
    else:
        out["Value_Method"] = "MARKER_CENTER"
    stem = field("Errorbar_Stem_Confirmed").upper()
    if stem not in ("TRUE", "FALSE"):
        problems.append("the mark does not say whether a stem connected its cap "
                        "(Errorbar_Stem_Confirmed=%s), so how its spread was got "
                        "cannot be re-derived" % (stem or "blank"))
    elif number("dispersion") is None:
        problems.append("the mark reports no dispersion, and this reader takes "
                        "the connected column through the marker as one for "
                        "every mark it emits")
    else:
        out["Dispersion_Method"] = ("DIRECT_CONNECTED_CAP" if stem == "TRUE"
                                    else "UNSTEMMED_CAP")
    anchors = (context or {}).get("Position_Anchors") or {}
    label, x_px = field("x_label"), number("x")
    if label and anchors:
        declared_x = anchors.get(label)
        if declared_x is None:
            problems.append("the mark carries the label %s and this run declares "
                            "no anchor pixel for it" % label)
        elif x_px is None or abs(x_px - declared_x) > PIXEL_EPSILON:
            problems.append("the mark was read at column %s and this run "
                            "declares %s sits at %s - this reader looks AT the "
                            "declared column, so the two are the same number or "
                            "the mark is not this cell's"
                            % (field("x") or "nothing", label, declared_x))
    elif label:
        problems.append("the mark carries the label %s and this run declares no "
                        "anchor pixels for the panel, so nothing says the mark "
                        "is at it" % label)
    problems.extend(_curve_arithmetic_problems(field, finite_number, context))
    return EvidenceVerdict(out, problems)


#: What `mark_readers` calls a filled marker: the share of the marker's own
#: outline that is ink. Named here because the verifier re-derives the fill
#: claim from the ratio the reader recorded, and two copies of the threshold
#: would eventually disagree about a marker on the line.
MARKER_FILLED_RATIO = 0.58


def expected_line_mono_methods(mark, context=None):
    """The three methods a LINE_MONO mark's own evidence implies.

    A monochrome panel has no colour to name a series by, so it names it by the
    marker: the SHAPE the manifest declares, or the FILL when every series is the
    same shape, or nothing at all when one series was declared and there is
    nothing to tell apart. The reader records what it measured - the shape it
    classified, the fill state and the ratio behind it - so each of the three
    identity methods is re-derivable from the measurement and the declaration
    together.

        MEASURED_MARKER_SHAPE      the series declares a shape, and the marker
                                   was classified as that shape
        MEASURED_MARKER_FILL       the series declares no shape and a fill, and
                                   the marker measured as that fill
        DECLARED_SINGLE_SERIES     neither was declared: nothing about the mark
                                   was compared with anything, which is R1

    The value and the spread are the marker centre and the cap rows, checked by
    the same arithmetic every other reader's are.
    """
    def field(name):
        value = mark.get(name)
        return "" if value is None else str(value).strip()

    def number(name):
        return finite_number(field(name))

    out, problems = {}, []
    declared = ((context or {}).get("Series_Discriminants")
                or {}).get(field("series")) or {}
    shape = field("Marker_Definition").upper()
    fill = field("Marker_Fill").upper()
    ratio = number("marker_fill_ratio")
    want_shape = _s_upper(declared.get("Marker_Shape"))
    want_fill = _s_upper(declared.get("Marker_Fill"))
    if not declared:
        problems.append("this run declares no series %s for the panel, so what "
                        "the marker had to look like to be it is not stated"
                        % (field("series") or "(unnamed)"))
    elif not shape:
        problems.append("the mark records no measured marker shape, so how its "
                        "series was named cannot be re-derived")
    elif want_shape and want_shape != "ANY":
        if shape != want_shape:
            problems.append("the mark measured as a %s and this run declares "
                            "series %s is a %s"
                            % (shape, field("series"), want_shape))
        else:
            out["Identity_Method"] = "MEASURED_MARKER_SHAPE"
    elif want_fill and want_fill != "ANY":
        if fill != want_fill:
            problems.append("the mark measured as %s and this run declares "
                            "series %s is %s"
                            % (fill or "nothing", field("series"), want_fill))
        else:
            out["Identity_Method"] = "MEASURED_MARKER_FILL"
    else:
        out["Identity_Method"] = "DECLARED_SINGLE_SERIES"
    # AND THE FILL STATE IS THE RATIO'S OWN ANSWER. The reader calls a marker
    # filled when at least `MARKER_FILLED_RATIO` of its outline is ink; a mark
    # whose state and ratio disagree was not classified by this reader.
    if fill in ("FILLED", "OPEN") and ratio is not None:
        should = "FILLED" if ratio >= MARKER_FILLED_RATIO else "OPEN"
        if fill != should:
            problems.append("the mark says its marker is %s and %s of its "
                            "outline is ink, which is %s"
                            % (fill, ratio, should))
    elif fill in ("FILLED", "OPEN"):
        problems.append("the mark says its marker is %s and records no fill "
                        "ratio it was measured from" % fill)
    if not shape:
        pass                      # already refused above
    else:
        out["Value_Method"] = "MARKER_CENTER"
    stem = field("Errorbar_Stem_Confirmed").upper()
    spread = number("dispersion")
    rows = (number("Errorbar_Top_Px"), number("Errorbar_Bottom_Px"))
    if stem not in ("TRUE", "FALSE"):
        problems.append("the mark does not say whether a stem connected its cap "
                        "(Errorbar_Stem_Confirmed=%s), so how its spread was got "
                        "cannot be re-derived" % (stem or "blank"))
    elif spread is None and rows == (None, None):
        out["Dispersion_Method"] = "NO_DISPERSION"
    elif spread is None or None in rows:
        problems.append("the mark reports a spread of %s between rows %s and "
                        "%s, and a spread is both or neither"
                        % (field("dispersion") or "nothing",
                           field("Errorbar_Top_Px") or "nothing",
                           field("Errorbar_Bottom_Px") or "nothing"))
    else:
        out["Dispersion_Method"] = ("DIRECT_CONNECTED_CAP" if stem == "TRUE"
                                    else "UNSTEMMED_CAP")
    problems.extend(_nearest_anchor_problems(field, number, context))
    problems.extend(_curve_arithmetic_problems(field, finite_number, context))
    return EvidenceVerdict(out, problems)


def _s_upper(value):
    return "" if value is None else str(value).strip().upper()


def _nearest_anchor_problems(field, number, context):
    """Is this mark nearest to the anchor it is filed under?

    A monochrome marker is FOUND rather than looked up: the reader takes the
    centroid of the blob it classified, so its x is a measurement and not the
    declared column. Nearest-anchor is therefore the question, as it is for a
    bar - and unlike a bar, this reader records no residual to check.
    """
    anchors = (context or {}).get("Position_Anchors") or {}
    label, x_px = field("x_label"), number("x")
    if not label:
        return []
    if not anchors:
        return ["the mark carries the label %s and this run declares no anchor "
                "pixels for the panel, so nothing says the mark is at it" % label]
    if x_px is None:
        return ["the mark records no x column, so the position it was assigned "
                "to cannot be re-derived"]
    distances = sorted((abs(x_px - px), pid) for pid, px in anchors.items())
    if len(distances) > 1 and abs(distances[1][0] - distances[0][0]) <= PIXEL_EPSILON:
        return ["the mark at column %s is the same distance from %s and %s, so "
                "which position it belongs to is not decidable"
                % (x_px, distances[0][1], distances[1][1])]
    if label != distances[0][1]:
        return ["the mark sits at column %s, which is nearest the declared "
                "anchor for %s (%s away), and it is filed under %s"
                % (x_px, distances[0][1], distances[0][0], label)]
    return []


#: Mark type -> the function that re-derives its methods from its own evidence.
#:
#: One entry today, and the one worth having first: `LINE_MONO_STYLE` produces
#: every value method there is, reaches R2, R3 and R4 on real figures, and already
#: carries the support columns, the occlusion cause and the drawing scale its
#: decision was made from. A mark type absent from this table is checked by the
#: matrix and by the artifact join, and not by re-derivation - which is a real
#: difference in strength and is written down rather than implied away.
EVIDENCE_VERIFIERS = {"LINE_MONO_STYLE": expected_line_style_methods,
                      "BAR_COLOR": expected_bar_colour_methods,
                      "LINE_COLOR": expected_line_colour_methods,
                      "LINE_MONO": expected_line_mono_methods}


def evidence_failure(mark_type, mark, claimed, context=None):
    """(code, detail) for a mark whose evidence does not support its methods.

    `claimed` is the value row's three fields. Blank on either side is a failure:
    evidence that says nothing does not support a claim, which is the shape two
    earlier joins had to learn twice.

    `context` is the panel's envelope AS THIS MODULE RE-DERIVED IT from the
    verified manifests, not the artifact's own copy: a verifier that recomputed a
    mark's numbers under the producer's calibration would be checking the
    artifact against itself.

    Two codes, because they are two findings and a reviewer acts differently on
    each. `METHOD_CONTRADICTS_EVIDENCE` says the mark's own measurements come to a
    different method than the value claims - somebody is wrong, and the ink says
    which. `METHOD_EVIDENCE_INCOMPLETE` says the mark did not record enough to
    answer, so nothing can be checked: not a contradiction, and equally not a
    pass. Before v7.76 the second was silence, and silence compared equal.
    """
    verifier = EVIDENCE_VERIFIERS.get(str(mark_type or "").strip().upper())
    if verifier is None:
        return "", ""
    verdict = verifier(mark, context)
    wrong = []
    for field, want in sorted(verdict.expected.items()):
        got = str(claimed.get(field, "") or "").strip()
        if got != want:
            wrong.append("%s: the evidence supports %s and the value says %s"
                         % (field, want, got or "nothing"))
    if wrong:
        return "METHOD_CONTRADICTS_EVIDENCE", "; ".join(wrong)
    if verdict.problems:
        return ("METHOD_EVIDENCE_INCOMPLETE",
                "the mark cannot answer for the methods this value claims: %s"
                % "; ".join(verdict.problems))
    return "", ""


def contract_failure(mark_type, identity_method, value_method):
    """Why this pair cannot have come from this reader, or "" if it could.

    A mark type this table has never heard of is not an error here: the caller
    knows whether an unknown reader is possible, and refusing one would make
    adding a reader a two-file change with a failure in the middle.
    """
    allowed = METHOD_CONTRACT.get(str(mark_type or "").strip().upper())
    if allowed is None:
        return ""
    pair = (str(identity_method or "").strip(), str(value_method or "").strip())
    if pair in allowed:
        return ""
    return ("%s cannot produce Identity_Method=%s Value_Method=%s; it produces %s"
            % (mark_type, pair[0] or "(blank)", pair[1] or "(blank)",
               " or ".join("%s/%s" % p for p in sorted(allowed))))


#: Tiers whose values a run may finalize at all. R4 is a model estimate: a
#: reviewer looking at an overlay cannot tell a fitted y from a read one, so
#: approving it would launder an estimate into a measurement.
FINALIZABLE_TIERS = ("R0", "R1", "R2", "R3")

#: Tiers that need a panel-level confirmation that the inferences were looked at.
PANEL_CONFIRMATION_TIERS = ("R2", "R3")

#: Tiers that need a confirmation per CELL, because one wrong cell in twenty
#: does not show up in a panel-level answer.
CELL_CONFIRMATION_TIERS = ("R3",)


def identity_tier(method):
    return IDENTITY_METHODS.get(str(method or "").strip().upper(), UNKNOWN_TIER)


def value_tier(method):
    return VALUE_METHODS.get(str(method or "").strip().upper(), UNKNOWN_TIER)


#: HOW THE DISPERSION WAS GOT - the third axis, and in a continuous
#: meta-analysis often the one that decides the weight.
#:
#: `Identity_Method` and `Value_Method` are both about the MEAN. A cell whose
#: mean came straight off the ink and whose error bar was reconstructed, or read
#: off a cap that no stem connects to the mark, priced R0 on both axes and went
#: into the pool with a weight nobody had checked. `Errorbar_Stem_Confirmed` is a
#: boolean about ONE of these cases and says nothing about the rest.
DISPERSION_METHODS = {
    # A cap this reader followed a stem to, from this mark. The strongest thing
    # a figure offers.
    "DIRECT_CONNECTED_CAP": "R0",
    # Both bounds read directly - an interval drawn as two ends rather than as a
    # bar with caps.
    "DIRECT_BOUND_PAIR": "R0",
    # The box's own quartile lines, all three required present before the reader
    # emits anything at all.
    "DIRECT_BOX_GEOMETRY": "R0",
    # Copied from the paper's text or table, not measured off the figure.
    "SOURCE_TRANSCRIBED": "R0",
    # Ink at the right distance with nothing joining it to the mark. It may be a
    # cap; it may be a significance glyph, which sits exactly where a cap is and
    # is the same colour. That is a question for a person, per cell.
    "UNSTEMMED_CAP": "R3",
    # A cap the reader restored across furniture it had removed itself, the same
    # claim `RESTORED_MASKED_FURNITURE` makes about a mean.
    "RESTORED_MASKED_CAP": "R3",
    # Reconstructed from neighbouring cells rather than from this one's ink.
    "INTERPOLATED_DISPERSION": "R3",
    # A model produced it. No signature can finalize that, exactly as for a mean.
    "FITTED_DISPERSION": "R4",
    # THIS CELL HAS NO DISPERSION, and that is a statement rather than a silence.
    # Priced R0 because nothing is claimed: whether a value without a weight may
    # be pooled is the unit's question, and `NO_VARIANCE` already answers it.
    "NO_DISPERSION": "R0",
}


def dispersion_tier(dispersion_method, has_dispersion=True):
    """What this cell's dispersion costs a reviewer.

    `has_dispersion=False` is the cell with no error bar at all: nothing is
    claimed, so nothing is doubted. With a number present, a blank method is a
    number with no account of itself and takes the highest tier - the same rule
    the other two axes follow, for the same reason.
    """
    if not has_dispersion:
        return TIERS[0]
    text = str(dispersion_method or "").strip()
    if not text:
        return UNKNOWN_TIER
    return DISPERSION_METHODS.get(text, UNKNOWN_TIER)


def review_tier(identity_method, value_method):
    """The worse of the two tiers. Derived here and never read from a file."""
    return max(identity_tier(identity_method), value_tier(value_method))


#: Which columns `row_tier` reads a dispersion out of. A five-number summary has
#: no `Dispersion_Value` and is not a cell without dispersion: its quartiles ARE
#: the spread, and pricing them as "nothing claimed" would let a box panel skip
#: the axis entirely.
DISPERSION_VALUE_FIELDS = ("Dispersion_Value", "Q1", "Q3", "Errorbar_Lower",
                           "Errorbar_Upper")


def row_tier(row):
    """What one VALUE ROW costs, over all three axes.

    The row-shaped question, and the one every gate should ask: a caller that
    reaches for `review_tier` alone is asking about the mean and pricing the
    cell. Whether the row has a dispersion at all is read off the row rather
    than declared, so a reader that emits no method for a cell with no error bar
    is not punished for a silence about nothing.
    """
    has_dispersion = any(
        str(row.get(field, "") or "").strip() not in ("", "None")
        for field in DISPERSION_VALUE_FIELDS)
    return max(review_tier(str(row.get("Identity_Method", "") or ""),
                           str(row.get("Value_Method", "") or "")),
               dispersion_tier(str(row.get("Dispersion_Method", "") or ""),
                               has_dispersion))


def row_finalizable(row):
    """Whether a VALUE ROW may be finalized at all, over all three axes.

    The one a gate should call. `finalizable` below asks the same question of the
    two axes about the MEAN, which is a narrower question than it sounds like:
    from v7.70 a row can be unfinalizable because of its SPREAD, and a caller
    reaching for the shorter name would not see it. Both are kept because they
    answer different questions and the shorter one is used by scenarios about the
    mean; nothing in the pipeline gates on it.
    """
    return row_tier(row) in FINALIZABLE_TIERS


def finalizable(identity_method, value_method):
    """The two axes about the MEAN only - see `row_finalizable`."""
    return review_tier(identity_method, value_method) in FINALIZABLE_TIERS
