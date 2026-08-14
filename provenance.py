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


def review_tier(identity_method, value_method):
    """The worse of the two tiers. Derived here and never read from a file."""
    return max(identity_tier(identity_method), value_tier(value_method))


def finalizable(identity_method, value_method):
    return review_tier(identity_method, value_method) in FINALIZABLE_TIERS
