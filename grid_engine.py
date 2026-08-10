"""Universal grid + value validation for digitized figures.

Four grains, each declared once:

    figure_manifest.csv   Figure_ID   the physical figure: provenance, image,
                                      panel reconciliation
    grid_definitions.csv  Grid_ID     factors and their levels, declared ONCE and
                                      referenced by every unit that shares them
    unit_manifest.csv     Unit_ID     Figure x Panel x Outcome x Statistic: what
                                      is plotted, how it was read, axis calibration
    figure_values.csv     value       Unit_ID x Cell_Key

`kernel` is a REQUIRED argument. It used to default to None, and without it the
value checks quietly did nothing while the grid checks kept passing - a validator
that reports "0 problems" on r = 1.5 is worse than no validator.

Everything a figure needs checked runs through two universal functions:

    validate_unit()               N, dispersion vocabulary, provenance,
                                  panel reconciliation, extraction geometry
    validate_value_by_statistic() continuous / binary / association values,
                                  ranges, and dual reading on EVERY reader column

Nothing dispatches on A-G. `Display_Hint` survives to tell an extractor which
WebPlotDigitizer mode to use and is never consulted for a verdict.
"""
import itertools
import os
import re
import hashlib

import pandas as pd
from PIL import Image

FIG_STATISTIC_TYPES = ("CONTINUOUS", "BINARY_EVENT", "ASSOCIATION",
                       "QUANTILE_SUMMARY")
FIG_GRID_RULES = ("FULL", "SPARSE")
FIG_DISPLAY_HINTS = ("A_CHALLENGE_TIMECOURSE", "B_CHALLENGE_2POINT",
                     "C_LONGITUDINAL_SERIAL", "D_SIMPLE_PREPOST",
                     "E_SCATTER_ASSOCIATION", "F_BINARY_EVENT",
                     "G_FACTORIAL_CONDITIONS", "UNSPECIFIED")
FIG_BAR_TOP_DEFS = ("OUTLINE_CENTER", "FILL_EDGE", "MARKER_CENTER", "NOT_A_BAR")
FIG_PANEL_RECON = ("MATCHED", "UNLISTED_PANELS_FOUND", "WORKLIST_OVERCOUNTS", "PENDING")
FIG_EXTRACTION_METHODS = ("DIGITIZED", "TRANSCRIBED")
FIG_DISPERSION_TYPES = ("SD", "SE", "SEM", "CI95", "IQR", "RANGE", "NO_ERRORBAR")
FIG_ASYMMETRIC_TYPES = ("CI95", "IQR", "RANGE")
FIG_EFFECT_MEASURES = ("RR", "OR", "RD", "NONE")
FIG_DUAL_OK = ("AGREED", "RECONCILED")
# How the p beside an association was arrived at. The field is only provenance if
# it is checked: a Kendall p from the exact permutation test labelled
# FISHER_Z_APPROX misdescribes the one number a reader would use to judge it.
FIG_P_VALUE_METHODS = ("PEARSON_T_TEST", "SPEARMAN_T_APPROX", "SLOPE_T_TEST",
                       "R_SQUARED_F_TEST", "FISHER_Z_APPROX",
                       "KENDALL_EXACT_PERMUTATION",
                       "KENDALL_NORMAL_APPROX_N_GT_200", "SOURCE_P_REQUIRED_TIES",
                       "SOURCE_REPORTED")
# Which method may appear beside which statistic. Kendall has its own null
# distribution, so its methods are exclusive in both directions.
FIG_KENDALL_P_METHODS = ("KENDALL_EXACT_PERMUTATION", "KENDALL_NORMAL_APPROX_N_GT_200",
                         "SOURCE_P_REQUIRED_TIES")
#: Every statistic's own null distribution, named. One shared approximation for
#: all five is what this table replaces: a slope's t comes from the residual
#: variance, an R-squared's p from the model F, and a rank correlation's from a
#: permutation null that ties invalidate. `SOURCE_REPORTED` is legal everywhere
#: because the paper's own p can always be copied instead of computed.
FIG_STATISTIC_P_METHODS = {
    # Fisher's z is a Pearson-r method - it is the one place the old label was
    # not simply wrong, so a transcribed Fisher-z p is still accepted here.
    "PEARSON_R": ("PEARSON_T_TEST", "FISHER_Z_APPROX"),
    "SPEARMAN_RHO": ("SPEARMAN_T_APPROX", "SOURCE_P_REQUIRED_TIES"),
    "KENDALL_TAU": FIG_KENDALL_P_METHODS,
    "R_SQUARED": ("R_SQUARED_F_TEST",),
    "SLOPE": ("SLOPE_T_TEST",),
}
#: Methods whose validity depends on there being no ties in the ranks.
FIG_UNTIED_P_METHODS = ("KENDALL_EXACT_PERMUTATION", "KENDALL_NORMAL_APPROX_N_GT_200",
                        "SPEARMAN_T_APPROX")
#: Statistics computed on ranks, where the tie state selects the test.
FIG_RANK_STATISTICS = ("KENDALL_TAU", "SPEARMAN_RHO")
FIG_EXACT_KENDALL_MAX_N = 200
#: Whether the marks the reader found are the sample the paper describes.
FIG_POINT_COUNT_AGREEMENT = ("MATCH", "FEWER_DETECTED", "MORE_DETECTED",
                             "NO_SOURCE_N")
# Provenance is per FIELD, not per row. A scatter plot routinely gives its effect
# to the digitizer and its p to the running text, and a single unit-level
# Extraction_Method cannot say that.
FIG_FIELD_PROVENANCE = ("DIGITIZED", "TRANSCRIBED")
# Which p-methods are computed from the digitized cloud, and which are copied.
FIG_COMPUTED_P_METHODS = ("PEARSON_T_TEST", "SPEARMAN_T_APPROX", "SLOPE_T_TEST",
                          "R_SQUARED_F_TEST", "FISHER_Z_APPROX",
                          "KENDALL_EXACT_PERMUTATION",
                          "KENDALL_NORMAL_APPROX_N_GT_200")
FIG_COPIED_P_METHODS = ("SOURCE_REPORTED", "SOURCE_P_REQUIRED_TIES")
# Does zero mean "none of the quantity" (RATIO) or "no change" (CHANGE)? The
# SE-implies-an-impossible-SD heuristic compares the SD against |mean|, which is
# only meaningful on a ratio scale. A percent-change outcome legitimately sits at
# zero, so the ratio explodes and the check fires on correct data.
FIG_VALUE_SCALES = ("RATIO", "CHANGE")

_PAIR = re.compile(r"^\s*([^=]+?)\s*=\s*(.+?)\s*$")


def fig_figure_columns():
    return [
        "Figure_ID", "Publication_ID", "Source_File", "Source_Page", "Source_Image",
        "Source_Caption_Verbatim", "Figure_Number",
        "Image_Resolution_Or_Hash", "WPD_Project_File",
        "Observed_Panel_Count", "Worklist_Panel_Count", "Unlisted_Panels",
        "Panel_Reconciliation_Status", "Note",
    ]


def fig_grid_columns():
    return ["Grid_ID", "Factor_Name", "Factor_Level", "Level_Order", "Note"]


def fig_unit_columns():
    return [
        "Unit_ID", "Figure_ID", "Grid_ID", "Panel",
        "Outcome_Variable", "Outcome_Domain", "Unit",
        "Statistic_Type", "Display_Hint", "Grid_Rule", "Sparse_Justification",
        "Dispersion_Type", "Errorbar_Definition_Source", "N_Outcome", "Value_Scale",
        "Extraction_Method", "Bar_Top_Definition", "Errorbar_Stem_Confirmed",
        "Axis_X_Scale", "Axis_Y_Scale",
        "Axis_Calib_X1_Value", "Axis_Calib_X1_Pixel",
        "Axis_Calib_X2_Value", "Axis_Calib_X2_Pixel",
        "Axis_Calib_Y1_Value", "Axis_Calib_Y1_Pixel",
        "Axis_Calib_Y2_Value", "Axis_Calib_Y2_Pixel",
        "Extractor_1", "Extractor_2", "Independent_Verification_Status",
        "Discrepancy_Note", "Date", "Note",
    ]


def fig_values_columns():
    return [
        "Unit_ID", "Cell_Key",
        "Mean_R1", "Dispersion_R1", "Mean_R2", "Dispersion_R2",
        "Mean", "Dispersion_Value", "Errorbar_Lower", "Errorbar_Upper",
        "Events_R1", "Events_R2", "Events",
        "N_at_Risk_R1", "N_at_Risk_R2", "N_at_Risk",
        "Events_Comparator_R1", "Events_Comparator_R2", "Events_Comparator",
        "N_at_Risk_Comparator_R1", "N_at_Risk_Comparator_R2", "N_at_Risk_Comparator",
        "Effect_Measure",
        "Association_Type", "Association_Value_R1", "Association_Value_R2",
        "Association_Value", "CI_Lower", "CI_Upper", "P_Value", "N_Pairs",
        # Provenance is per FIELD: a scatter plot routinely gives its effect to
        # the digitizer and its p to the running text, and one unit-level
        # Extraction_Method cannot say that.
        "P_Value_Method", "P_Value_Extraction_Method",
        # Which Kendall null distribution applies depends on ties. Recording the
        # claim and where the points live is what makes it checkable rather than
        # taken on trust.
        "Ties_Present", "Point_Data_Reference",
        # N_Pairs is how many marks the reader found. These say how many the
        # paper says there are, how many distinct ones survived deduplication,
        # whether the two agree, and whether anything could be hiding behind
        # anything else.
        "Expected_N_From_Source", "Detected_Unique_Point_Count",
        "Point_Count_Agreement", "Overplotting_Possible",
        "Series_Mask_Overlap_Count",
        "Median_R1", "Median_R2", "Median",
        "Q1_R1", "Q1_R2", "Q1", "Q3_R1", "Q3_R2", "Q3",
        "Whisker_Lower_R1", "Whisker_Lower_R2", "Whisker_Lower",
        "Whisker_Upper_R1", "Whisker_Upper_R2", "Whisker_Upper",
        # What the READER found for THIS cell, as opposed to what a person
        # typed once for the whole unit. `Errorbar_Stem_Confirmed` lived only on
        # the unit manifest, so a panel where three whiskers were confirmed and
        # one was not passed on the strength of the three: the gate consulted a
        # human's single assertion and the reader's per-mark finding was
        # discarded by `to_value_records`.
        "Errorbar_Stem_Confirmed", "Bar_Top_Definition", "Bar_Direction",
        "Position_Assignment", "Calibration_Max_Residual",
        "Slot_Assignment_Residual_Px",
        # The measurement this value was read off, and who named its series. A
        # monochrome bar is identified BY ITS FILL, so a value's row heading is
        # a separate claim from its number - sometimes the reader's, sometimes a
        # person's reading of a legend recorded in `identity_resolution.csv`.
        # These carry that claim to the grain that gets pooled, where before it
        # stopped at the raw marks.
        "Geometry_Row_SHA256", "Auto_Fill_Pattern", "Resolved_Fill_Pattern",
        "Identity_Source", "Identity_Evidence_Type", "Resolution_ID",
        # The project that can re-derive THIS value. It used to be looked up on
        # the figure, where a run stored whichever panel finished first - so on
        # a six-panel figure five values named a project of somebody else's
        # marks, read off somebody else's calibration.
        "WPD_Project_File",
        "Verification_Status", "Reconciliation_Note",
        "Note",
    ]


def fig_cell_key(levels):
    return ";".join("%s=%s" % (str(f).strip().upper(), str(v).strip().upper())
                    for f, v in sorted(levels.items(), key=lambda kv: str(kv[0]).upper()))


def fig_parse_cell_key(key):
    """{factor: level}, or None when malformed.

    A repeated factor is malformed, not a last-one-wins merge: "POSTURE=SUPINE;
    POSTURE=TILT" names two cells at once and used to collapse silently.
    """
    if key is None:
        return None
    text = str(key).strip()
    if not text:
        return None
    out = {}
    for part in re.split(r"[;|]", text):
        if not part.strip():
            continue
        m = _PAIR.match(part)
        if not m:
            return None
        fac = m.group(1).strip().upper()
        if fac in out:
            return None
        out[fac] = m.group(2).strip().upper()
    return out or None


# --------------------------------------------------------------------------
# universal checkers
# --------------------------------------------------------------------------

def validate_unit(row, kernel, flag, line, figure=None):
    """N, dispersion vocabulary, extraction geometry, provenance for one unit."""
    blank, num, bad_num = kernel.fig_is_blank, kernel.fig_as_number, kernel.fig_is_bad_number
    unresolved = kernel.fig_unresolved_marker

    st = str(row.get("Statistic_Type", "")).strip().upper()
    if st not in FIG_STATISTIC_TYPES:
        flag(line, "BAD_STATISTIC_TYPE",
             "%s (expected %s)" % (st or "blank", "/".join(FIG_STATISTIC_TYPES)))
    for c in ("Unit_ID", "Figure_ID", "Grid_ID", "Panel", "Outcome_Variable", "Unit"):
        if blank(row.get(c)):
            flag(line, "MISSING_REQUIRED", c)

    method = str(row.get("Extraction_Method", "")).strip().upper()
    if method not in FIG_EXTRACTION_METHODS:
        flag(line, "BAD_EXTRACTION_METHOD",
             "%s (expected %s)" % (method or "blank", "/".join(FIG_EXTRACTION_METHODS)))

    ex1 = str(row.get("Extractor_1", "")).strip().casefold()
    ex2 = str(row.get("Extractor_2", "")).strip().casefold()
    if ex1 and ex2 and ex1 == ex2:
        flag(line, "SAME_EXTRACTOR",
             "Extractor_1 and Extractor_2 identify the same reader")

    gr = str(row.get("Grid_Rule", "")).strip().upper()
    if gr not in FIG_GRID_RULES:
        flag(line, "BAD_GRID_RULE",
             "%s (expected %s)" % (gr or "blank", "/".join(FIG_GRID_RULES)))
    elif gr == "SPARSE":
        j = row.get("Sparse_Justification")
        if blank(j) or unresolved(j):
            flag(line, "SPARSE_WITHOUT_JUSTIFICATION",
                 "Grid_Rule=SPARSE needs a real reason those cells do not exist")

    dh = str(row.get("Display_Hint", "")).strip().upper()
    if dh and dh not in FIG_DISPLAY_HINTS:
        flag(line, "BAD_DISPLAY_HINT", "%s is not a known hint" % dh)

    if st in ("CONTINUOUS", "QUANTILE_SUMMARY"):
        n = num(row.get("N_Outcome"))
        if blank(row.get("N_Outcome")):
            flag(line, "MISSING_REQUIRED", "N_Outcome")
        elif n is None:
            flag(line, "NON_NUMERIC_VALUE", "N_Outcome=%r" % row.get("N_Outcome"))
        elif n <= 0 or n != int(n):
            flag(line, "N_INVALID", "N_Outcome=%g must be a positive integer" % n)
        dt = str(row.get("Dispersion_Type", "")).strip().upper()
        if dt not in FIG_DISPERSION_TYPES:
            flag(line, "BAD_DISPERSION_TYPE",
                 "%s (expected %s)" % (dt or "blank", "/".join(FIG_DISPERSION_TYPES)))
        vs_ = str(row.get("Value_Scale", "")).strip().upper()
        if vs_ not in FIG_VALUE_SCALES:
            flag(line, "BAD_VALUE_SCALE",
                 "Value_Scale=%s (expected %s) - it decides whether an SD may exceed "
                 "the mean" % (vs_ or "blank", "/".join(FIG_VALUE_SCALES)))
        if st == "QUANTILE_SUMMARY" and dt not in ("IQR", "RANGE"):
            flag(line, "BAD_DISPERSION_TYPE",
                 "QUANTILE_SUMMARY requires IQR or RANGE, got %s" % (dt or "blank"))
        src = row.get("Errorbar_Definition_Source")
        if blank(src):
            flag(line, "NO_ERRORBAR_SOURCE", "record the wording that defines the bars")
        elif unresolved(src):
            flag(line, "UNRESOLVED_ERRORBAR_DEFINITION",
                 "contains %r - Dispersion_Type=%s is then a guess"
                 % (unresolved(src), dt))
    elif st == "ASSOCIATION" and not blank(row.get("N_Outcome")):
        # An association's n may be absent - a paper does not always give one -
        # but if it is there it is the number the reader's detected point count
        # is measured against, and `int(float("10.5"))` is 10. A sample size
        # that has to be truncated to be used is not a sample size.
        n = num(row.get("N_Outcome"))
        if n is None:
            flag(line, "NON_NUMERIC_VALUE", "N_Outcome=%r" % row.get("N_Outcome"))
        elif n <= 0 or n != int(n):
            flag(line, "N_INVALID",
                 "N_Outcome=%g must be a whole number of subjects; it is what "
                 "the detected point count is compared against" % n)

    if method == "DIGITIZED":
        btd = str(row.get("Bar_Top_Definition", "")).strip().upper()
        if blank(row.get("Bar_Top_Definition")):
            flag(line, "MISSING_BAR_TOP_DEFINITION",
                 "state where the value was read (%s)" % "/".join(FIG_BAR_TOP_DEFS))
        elif btd not in FIG_BAR_TOP_DEFS:
            flag(line, "BAD_BAR_TOP_DEFINITION", "Bar_Top_Definition=%s" % btd)
        elif btd == "FILL_EDGE":
            flag(line, "BAR_TOP_READ_AT_FILL_EDGE",
                 "the fill stops inside the stroke - every mean is biased low")
        stem = kernel.fig_as_bool(row.get("Errorbar_Stem_Confirmed"))
        if st == "CONTINUOUS" and str(row.get("Dispersion_Type", "")).upper() != "NO_ERRORBAR":
            if stem == "BAD":
                flag(line, "BAD_ERRORBAR_STEM_FLAG",
                     "Errorbar_Stem_Confirmed=%r" % row.get("Errorbar_Stem_Confirmed"))
            elif stem is not True:
                flag(line, "ERRORBAR_STEM_UNCONFIRMED",
                     "the whisker was not confirmed to connect to the mark")
        for ax in ("X", "Y"):
            for n_ in (1, 2):
                for kind in ("Value", "Pixel"):
                    c = "Axis_Calib_%s%d_%s" % (ax, n_, kind)
                    if blank(row.get(c)):
                        flag(line, "MISSING_PROVENANCE", c)
                    elif bad_num(row.get(c)):
                        flag(line, "NON_NUMERIC_VALUE", "%s=%r" % (c, row.get(c)))
            v1, v2 = num(row.get("Axis_Calib_%s1_Value" % ax)), num(row.get("Axis_Calib_%s2_Value" % ax))
            p1, p2 = num(row.get("Axis_Calib_%s1_Pixel" % ax)), num(row.get("Axis_Calib_%s2_Pixel" % ax))
            if v1 is not None and v1 == v2:
                flag(line, "%s_CALIB_DEGENERATE" % ax, "both calibration values equal")
            if p1 is not None and p1 == p2:
                flag(line, "%s_CALIB_PIXEL_DEGENERATE" % ax, "both calibration pixels equal")
            sc = str(row.get("Axis_%s_Scale" % ax, "")).strip().upper()
            if sc and sc not in ("LINEAR", "LOG"):
                flag(line, "BAD_AXIS_SCALE", "Axis_%s_Scale=%s" % (ax, sc))
        if blank(row.get("Extractor_1")):
            flag(line, "MISSING_PROVENANCE", "Extractor_1")
        for c in ("Axis_X_Scale", "Axis_Y_Scale"):
            if blank(row.get(c)):
                flag(line, "MISSING_PROVENANCE",
                     "%s - a value read off an axis of undeclared type cannot be "
                     "re-checked" % c)
        # The project that re-derives THIS value, if the row names one; the
        # figure's column only as a fallback for a hand-assembled bundle. A
        # figure-level lookup was wrong on any figure with more than one
        # digitized panel: whichever panel ran first spoke for all of them.
        if blank(row.get("WPD_Project_File")) and (
                figure is None or blank(figure.get("WPD_Project_File"))):
            flag(line, "MISSING_PROVENANCE",
                 "WPD_Project_File - a digitized value with no saved project "
                 "cannot be re-opened")
        # A log axis cannot be calibrated at zero or below: the transform is
        # undefined there, so the mapping every value depends on is meaningless.
        for ax in ("X", "Y"):
            if str(row.get("Axis_%s_Scale" % ax, "")).strip().upper() == "LOG":
                for n_ in (1, 2):
                    v = num(row.get("Axis_Calib_%s%d_Value" % (ax, n_)))
                    if v is not None and v <= 0:
                        flag(line, "LOG_AXIS_NONPOSITIVE_CALIBRATION",
                             "Axis_Calib_%s%d_Value=%g on a LOG axis" % (ax, n_, v))

    if figure is not None:
        for c in ("Source_Image", "Source_Caption_Verbatim", "Image_Resolution_Or_Hash"):
            if method == "DIGITIZED" and blank(figure.get(c)):
                flag(line, "MISSING_PROVENANCE", "%s (from Figure_ID)" % c)


def _dual(kernel, row, flag, line, cols, tol, exact=False, reconciled=False):
    """Compare R1/R2 against a consensus for one measurement.

    `reconciled` means two readers disagreed, a human adjudicated, and the
    resolution is written down. Re-raising DUAL_READINGS_DISAGREE then punishes
    the process that is supposed to handle disagreement - the consensus still
    has to lie between the two readings.
    """
    num = kernel.fig_as_number
    r1, r2, con = (num(row.get(cols[0])), num(row.get(cols[1])), num(row.get(cols[2])))
    if r1 is None or r2 is None:
        flag(line, "NO_INDEPENDENT_READINGS",
             "%s=%r %s=%r" % (cols[0], row.get(cols[0]), cols[1], row.get(cols[1])))
        return
    if not reconciled:
        if exact:
            if r1 != r2:
                flag(line, "DUAL_READINGS_DISAGREE",
                     "%s=%s %s=%s - a printed count admits no tolerance"
                     % (cols[0], r1, cols[1], r2))
        else:
            denom = max(abs(r1), abs(r2), 1e-9)
            if abs(r1 - r2) / denom * 100.0 > tol:
                flag(line, "DUAL_READINGS_DISAGREE",
                     "%s=%s %s=%s differ more than %.1f%%" % (cols[0], r1, cols[1], r2, tol))
    if con is not None and not (min(r1, r2) - 1e-9 <= con <= max(r1, r2) + 1e-9):
        flag(line, "CONSENSUS_OUTSIDE_READINGS",
             "%s=%s outside [%s, %s]" % (cols[2], con, min(r1, r2), max(r1, r2)))


def validate_value_by_statistic(row, unit, kernel, flag, line,
                                require_dual=False, dual_tolerance_pct=5.0,
                                ranges=None):
    # A documented reconciliation is the resolution of a disagreement, not a
    # second offence. The note is what makes it acceptable; without one the
    # status is checked elsewhere and fails.
    cell_status = ("" if kernel.fig_is_blank(row.get("Verification_Status"))
                   else str(row.get("Verification_Status", "")).strip().upper())
    cell_note = row.get("Reconciliation_Note")
    if cell_status and cell_status not in FIG_DUAL_OK:
        flag(line, "BAD_CELL_VERIFICATION_STATUS", cell_status)
    if cell_status == "RECONCILED" and kernel.fig_is_blank(cell_note):
        flag(line, "CELL_RECONCILED_WITHOUT_NOTE",
             "record how this individual cell was adjudicated")
    _rec = (cell_status == "RECONCILED" and not kernel.fig_is_blank(cell_note))
    """Value, range and dual-reading checks for one cell, by Statistic_Type."""
    blank, num, bad_num = kernel.fig_is_blank, kernel.fig_as_number, kernel.fig_is_bad_number
    st = str(unit.get("Statistic_Type", "")).strip().upper()

    if str(unit.get("Extraction_Method", "")).strip().upper() == "DIGITIZED":
        # WHO named this value's series, checked against WHAT backs it. The two
        # columns are written together by the runner, so a disagreement here is
        # either a hand-edited values file or a join defect - and both look
        # exactly like a correct row until somebody asks the file which values a
        # person named. The gate runs on the file, so it can answer.
        source = str(row.get("Identity_Source", "")).strip().upper()
        evidence = str(row.get("Identity_Evidence_Type", "")).strip().upper()
        resolution = str(row.get("Resolution_ID", "")).strip()
        auto_fill = str(row.get("Auto_Fill_Pattern", "")).strip().upper()
        if source or evidence or resolution:
            if source not in kernel.FIG_IDENTITY_SOURCES:
                flag(line, "BAD_IDENTITY_SOURCE",
                     "Identity_Source=%r (expected %s)"
                     % (row.get("Identity_Source"),
                        "/".join(kernel.FIG_IDENTITY_SOURCES)))
            elif source == "AUTO":
                if evidence not in kernel.FIG_AUTO_IDENTITY_EVIDENCE:
                    flag(line, "IDENTITY_SOURCE_INCONSISTENT",
                         "Identity_Source=AUTO with Identity_Evidence_Type=%r; "
                         "what the reader measures is %s"
                         % (evidence or "blank",
                            "/".join(kernel.FIG_AUTO_IDENTITY_EVIDENCE)))
                if resolution:
                    flag(line, "IDENTITY_SOURCE_INCONSISTENT",
                         "Identity_Source=AUTO carries Resolution_ID=%s; a row "
                         "the reader named was not resolved by anybody"
                         % resolution)
            else:
                if evidence not in kernel.FIG_HUMAN_IDENTITY_EVIDENCE:
                    flag(line, "IDENTITY_SOURCE_INCONSISTENT",
                         "Identity_Source=HUMAN with Identity_Evidence_Type=%r; "
                         "expected %s" % (evidence or "blank",
                                          "/".join(kernel.FIG_HUMAN_IDENTITY_EVIDENCE)))
                if not resolution:
                    flag(line, "IDENTITY_RESOLUTION_UNIDENTIFIED",
                         "Identity_Source=HUMAN with no Resolution_ID; the row "
                         "a person signed is what makes this checkable")
                if auto_fill:
                    # Both filled in means the reader DID measure a fill and a
                    # person named the bar anyway. The join refuses that at the
                    # source; a values file that says it is a values file to
                    # stop trusting.
                    flag(line, "IDENTITY_OVERRODE_MEASUREMENT",
                         "Auto_Fill_Pattern=%s beside a human identity; a "
                         "resolution supplies a fill the reader could not "
                         "measure, it does not replace one it could" % auto_fill)

    if st == "CONTINUOUS":
        kernel.fig_check_numeric(row, ["Mean", "Dispersion_Value", "Errorbar_Lower",
                                       "Errorbar_Upper", "Mean_R1", "Mean_R2",
                                       "Dispersion_R1", "Dispersion_R2"], flag, line)
        if blank(row.get("Mean")):
            flag(line, "MISSING_REQUIRED", "Mean")
        m = num(row.get("Mean"))
        # The plausibility table holds native-scale ranges (heart rate 30-220).
        # A change score lives on a different scale entirely - a -300% change is
        # absurd for other reasons, but not because 30 <= -300 <= 220 fails.
        on_native_scale = str(unit.get("Value_Scale", "")).strip().upper() != "CHANGE"
        _c, lohi = kernel.fig_lookup_range(unit.get("Outcome_Variable"),
                                           ranges or kernel.fig_default_ranges())
        if not on_native_scale:
            lohi = None
        if m is not None and lohi is not None and not (lohi[0] <= m <= lohi[1]):
            flag(line, "IMPLAUSIBLE_VALUE",
                 "%s=%s (expected %s-%s)" % (unit.get("Outcome_Variable"), m, lohi[0], lohi[1]))
        dt = str(unit.get("Dispersion_Type", "")).strip().upper()
        sym, lo, hi = (num(row.get("Dispersion_Value")), num(row.get("Errorbar_Lower")),
                       num(row.get("Errorbar_Upper")))
        if dt in ("SD", "SE", "SEM"):
            if sym is None and (lo is None or hi is None):
                flag(line, "MISSING_DISPERSION", "%s needs a value or both bounds" % dt)
            if sym is not None and sym <= 0:
                flag(line, "DISPERSION_NONPOSITIVE", "Dispersion_Value=%g" % sym)
        elif dt in FIG_ASYMMETRIC_TYPES:
            if lo is None or hi is None:
                flag(line, "ASYMMETRIC_NEEDS_BOUNDS", "%s requires both bounds" % dt)
        elif dt == "NO_ERRORBAR":
            flag(line, "NONCONVERTIBLE_NO_VARIANCE",
                 "no error bar - this row carries no weight in a variance-weighted pool")
        if lo is not None and hi is not None:
            if lo > hi:
                flag(line, "ERRORBAR_BOUNDS_INVERTED", "lower %g > upper %g" % (lo, hi))
            elif m is not None and not (lo <= m <= hi):
                flag(line, "MEAN_OUTSIDE_ERRORBAR", "mean %g outside [%g, %g]" % (m, lo, hi))
        n = num(unit.get("N_Outcome"))
        ratio_scale = str(unit.get("Value_Scale", "")).strip().upper() == "RATIO"
        if ratio_scale and dt in ("SE", "SEM") and sym is not None and m is not None and n and n > 0:
            sd = sym * (n ** 0.5)
            if sd > abs(m) * 1.5:
                flag(line, "SE_IMPLIES_HUGE_SD",
                     "SE=%s N=%g -> SD=%.1f vs mean %.1f" % (sym, n, sd, m))
        if require_dual:
            _dual(kernel, row, flag, line, ("Mean_R1", "Mean_R2", "Mean"), dual_tolerance_pct, reconciled=_rec)
            if dt != "NO_ERRORBAR":
                _dual(kernel, row, flag, line,
                      ("Dispersion_R1", "Dispersion_R2", "Dispersion_Value"), dual_tolerance_pct,
                      reconciled=_rec)

    elif st == "QUANTILE_SUMMARY":
        qcols = ["Median_R1", "Median_R2", "Median",
                 "Q1_R1", "Q1_R2", "Q1", "Q3_R1", "Q3_R2", "Q3",
                 "Whisker_Lower_R1", "Whisker_Lower_R2", "Whisker_Lower",
                 "Whisker_Upper_R1", "Whisker_Upper_R2", "Whisker_Upper"]
        kernel.fig_check_numeric(row, qcols, flag, line)
        q1, med, q3 = num(row.get("Q1")), num(row.get("Median")), num(row.get("Q3"))
        for name, value in (("Q1", q1), ("Median", med), ("Q3", q3)):
            if blank(row.get(name)):
                flag(line, "MISSING_REQUIRED", name)
            elif value is None:
                flag(line, "NON_NUMERIC_VALUE", "%s=%r" % (name, row.get(name)))
        wl, wu = num(row.get("Whisker_Lower")), num(row.get("Whisker_Upper"))
        if (wl is None) != (wu is None):
            flag(line, "WHISKER_HALF_FILLED", "give both whisker bounds or neither")
        ordered = [v for v in (wl, q1, med, q3, wu) if v is not None]
        if len(ordered) >= 3 and any(a > b for a, b in zip(ordered, ordered[1:])):
            flag(line, "QUANTILE_ORDER_INVALID",
                 "expected whisker_low <= Q1 <= median <= Q3 <= whisker_high")
        on_native_scale = str(unit.get("Value_Scale", "")).strip().upper() != "CHANGE"
        _c, lohi = kernel.fig_lookup_range(unit.get("Outcome_Variable"),
                                           ranges or kernel.fig_default_ranges())
        if on_native_scale and med is not None and lohi is not None \
                and not (lohi[0] <= med <= lohi[1]):
            flag(line, "IMPLAUSIBLE_VALUE",
                 "median %s=%s (expected %s-%s)"
                 % (unit.get("Outcome_Variable"), med, lohi[0], lohi[1]))
        if require_dual:
            for cols in (("Median_R1", "Median_R2", "Median"),
                         ("Q1_R1", "Q1_R2", "Q1"),
                         ("Q3_R1", "Q3_R2", "Q3")):
                _dual(kernel, row, flag, line, cols, dual_tolerance_pct,
                      reconciled=_rec)
            if wl is not None:
                for cols in (("Whisker_Lower_R1", "Whisker_Lower_R2", "Whisker_Lower"),
                             ("Whisker_Upper_R1", "Whisker_Upper_R2", "Whisker_Upper")):
                    _dual(kernel, row, flag, line, cols, dual_tolerance_pct,
                          reconciled=_rec)

    elif st == "BINARY_EVENT":
        kernel.fig_check_numeric(row, ["Events", "N_at_Risk", "Events_Comparator",
                                       "N_at_Risk_Comparator", "Events_R1", "Events_R2",
                                       "N_at_Risk_R1", "N_at_Risk_R2",
                                       "Events_Comparator_R1", "Events_Comparator_R2",
                                       "P_Value"], flag, line)
        e, n = num(row.get("Events")), num(row.get("N_at_Risk"))
        for nm, v in (("Events", e), ("N_at_Risk", n)):
            if blank(row.get(nm)):
                flag(line, "MISSING_REQUIRED", nm)
            elif v is not None and (v < 0 or v != int(v)):
                flag(line, "EVENTS_INVALID" if nm == "Events" else "N_AT_RISK_INVALID",
                     "%s=%g must be a non-negative integer" % (nm, v))
        if n is not None and n <= 0:
            flag(line, "N_AT_RISK_INVALID", "N_at_Risk=%g must be positive" % n)
        if e is not None and n is not None and e > n:
            flag(line, "EVENTS_EXCEED_N", "%g events of %g at risk" % (e, n))
        em = str(row.get("Effect_Measure", "")).strip().upper()
        if em and em not in FIG_EFFECT_MEASURES:
            flag(line, "BAD_EFFECT_MEASURE", "Effect_Measure=%s" % em)
        ec, nc = num(row.get("Events_Comparator")), num(row.get("N_at_Risk_Comparator"))
        if ec is not None and (ec < 0 or ec != int(ec)):
            flag(line, "EVENTS_INVALID",
                 "Events_Comparator=%g must be a non-negative integer" % ec)
        if nc is not None and (nc <= 0 or nc != int(nc)):
            flag(line, "N_AT_RISK_INVALID",
                 "N_at_Risk_Comparator=%g must be a positive integer" % nc)
        if (ec is None) != (nc is None):
            flag(line, "COMPARATOR_HALF_FILLED", "give both comparator counts or neither")
        if em in ("RR", "OR") and (ec is None or nc is None):
            flag(line, "COMPARATOR_MISSING_FOR_RATIO", "%s needs a comparator arm" % em)
        if ec is not None and nc is not None and ec > nc:
            flag(line, "EVENTS_EXCEED_N", "comparator %g events of %g" % (ec, nc))
        p = num(row.get("P_Value"))
        if p is not None and not (0 <= p <= 1):
            flag(line, "P_VALUE_OUT_OF_RANGE", "P_Value=%g" % p)
        if require_dual:
            _dual(kernel, row, flag, line, ("Events_R1", "Events_R2", "Events"), 0, exact=True, reconciled=_rec)
            _dual(kernel, row, flag, line, ("N_at_Risk_R1", "N_at_Risk_R2", "N_at_Risk"), 0, exact=True, reconciled=_rec)
            if ec is not None:
                _dual(kernel, row, flag, line,
                      ("Events_Comparator_R1", "Events_Comparator_R2", "Events_Comparator"),
                      0, exact=True, reconciled=_rec)
            if nc is not None:
                _dual(kernel, row, flag, line,
                      ("N_at_Risk_Comparator_R1", "N_at_Risk_Comparator_R2",
                       "N_at_Risk_Comparator"), 0, exact=True, reconciled=_rec)

    elif st == "ASSOCIATION":
        kernel.fig_check_numeric(row, ["Association_Value", "CI_Lower", "CI_Upper",
                                       "P_Value", "N_Pairs", "Association_Value_R1",
                                       "Association_Value_R2"], flag, line)
        # Returns (canonical_or_None, raw_upper) - unpack it. Treating the tuple
        # as the canonical value made `at` always truthy, so every range check
        # below was compared against the wrong thing and r = 1.5 passed.
        at, raw_at = kernel.fig_normalize_association_type(row.get("Association_Type"))
        if at is None:
            flag(line, "BAD_ASSOCIATION_TYPE",
                 "Association_Type=%r is not in the controlled vocabulary" % raw_at)
        if blank(row.get("Association_Value")):
            flag(line, "MISSING_REQUIRED", "Association_Value")
        v = num(row.get("Association_Value"))
        bounds = ((-1.0, 1.0) if at in ("PEARSON_R", "SPEARMAN_RHO", "KENDALL_TAU")
                  else (0.0, 1.0) if at == "R_SQUARED" else None)
        lo, hi = num(row.get("CI_Lower")), num(row.get("CI_Upper"))
        if bounds:
            if v is not None and not (bounds[0] <= v <= bounds[1]):
                flag(line, "ASSOCIATION_VALUE_OUT_OF_RANGE",
                     "%s=%g outside %s" % (at, v, bounds))
            for nm, b in (("CI_Lower", lo), ("CI_Upper", hi)):
                if b is not None and not (bounds[0] <= b <= bounds[1]):
                    flag(line, "ASSOCIATION_CI_OUT_OF_RANGE", "%s=%g outside %s" % (nm, b, bounds))
        if (lo is None) != (hi is None):
            flag(line, "CI_HALF_FILLED", "give both interval bounds or neither")
        if lo is not None and hi is not None:
            if lo > hi:
                flag(line, "CI_BOUNDS_INVERTED", "%g > %g" % (lo, hi))
            elif v is not None and not (lo <= v <= hi):
                flag(line, "ESTIMATE_OUTSIDE_CI", "%g outside [%g, %g]" % (v, lo, hi))
        np_ = num(row.get("N_Pairs"))
        if np_ is None:
            flag(line, "MISSING_REQUIRED", "N_Pairs")
        elif np_ < 3 or np_ != int(np_):
            flag(line, "N_PAIRS_TOO_SMALL", "N_Pairs=%g cannot define a correlation" % np_)
        p = num(row.get("P_Value"))
        if p is not None and not (0 <= p <= 1):
            flag(line, "P_VALUE_OUT_OF_RANGE", "P_Value=%g" % p)

        # ---- how the p was arrived at ------------------------------------
        pm = ("" if blank(row.get("P_Value_Method"))
              else str(row.get("P_Value_Method")).strip().upper())
        _uem = str(unit.get("Extraction_Method", "")).strip().upper()
        transcribed = _uem == "TRANSCRIBED"
        digitized = _uem == "DIGITIZED"
        if not pm:
            flag(line, "MISSING_P_VALUE_METHOD",
                 "an association row must say how its p was obtained (%s)"
                 % "/".join(FIG_P_VALUE_METHODS))
        elif pm not in FIG_P_VALUE_METHODS:
            flag(line, "BAD_P_VALUE_METHOD",
                 "P_Value_Method=%s (expected %s)" % (pm, "/".join(FIG_P_VALUE_METHODS)))
        elif (at in FIG_STATISTIC_P_METHODS
                and pm not in FIG_STATISTIC_P_METHODS[at]
                and pm != "SOURCE_REPORTED"):
            # One approximation used to stand beside all five statistics. The
            # label is only provenance if the row cannot carry somebody else's.
            flag(line, "P_METHOD_WRONG_FOR_STATISTIC",
                 "%s beside %s - each statistic has its own null distribution; "
                 "expected %s" % (pm, at, "/".join(FIG_STATISTIC_P_METHODS[at])))
        elif at == "KENDALL_TAU":
            if p is None and pm not in ("SOURCE_P_REQUIRED_TIES", "SOURCE_REPORTED"):
                flag(line, "P_METHOD_CLAIMS_UNCOMPUTED_P",
                     "%s reports a computed p, but P_Value is blank; ties make the "
                     "exact test inapplicable and only SOURCE_P_REQUIRED_TIES may "
                     "leave it empty" % pm)
            elif p is not None and pm in ("KENDALL_EXACT_PERMUTATION",
                                          "KENDALL_NORMAL_APPROX_N_GT_200"):
                # The two computed variants are chosen by n, so n must agree.
                if np_ is not None:
                    small = np_ <= FIG_EXACT_KENDALL_MAX_N
                    want = ("KENDALL_EXACT_PERMUTATION" if small
                            else "KENDALL_NORMAL_APPROX_N_GT_200")
                    if pm != want:
                        flag(line, "P_METHOD_CONTRADICTS_N",
                             "N_Pairs=%g selects %s, not %s" % (np_, want, pm))
        elif at == "SPEARMAN_RHO" and p is None and pm != "SOURCE_P_REQUIRED_TIES":
            flag(line, "P_METHOD_CLAIMS_UNCOMPUTED_P",
                 "%s reports a computed p, but P_Value is blank; only "
                 "SOURCE_P_REQUIRED_TIES may leave it empty" % pm)
        if p is None and pm in FIG_COMPUTED_P_METHODS:
            flag(line, "P_METHOD_CLAIMS_UNCOMPUTED_P",
                 "%s names a computation but P_Value is blank" % pm)

        # ---- field-level provenance: the effect and the p may differ ------
        pex = ("" if blank(row.get("P_Value_Extraction_Method"))
               else str(row.get("P_Value_Extraction_Method")).strip().upper())
        # Only demand a provenance once there IS a p to attribute. A Kendall row
        # still waiting for the source's p has a method but nothing to source.
        if p is not None:
            if not pex:
                flag(line, "MISSING_P_VALUE_PROVENANCE",
                     "say whether this p was computed from the digitized points or "
                     "copied from the text (%s)" % "/".join(FIG_FIELD_PROVENANCE))
            elif pex not in FIG_FIELD_PROVENANCE:
                flag(line, "BAD_P_VALUE_PROVENANCE",
                     "P_Value_Extraction_Method=%s (expected %s)"
                     % (pex, "/".join(FIG_FIELD_PROVENANCE)))
            elif pm in FIG_COMPUTED_P_METHODS and pex != "DIGITIZED":
                flag(line, "P_PROVENANCE_CONTRADICTS_METHOD",
                     "%s is computed from the point cloud, but the p is marked %s"
                     % (pm, pex))
            elif pm in FIG_COPIED_P_METHODS and p is not None and pex != "TRANSCRIBED":
                flag(line, "P_PROVENANCE_CONTRADICTS_METHOD",
                     "%s means the number came from the paper, but the p is marked %s"
                     % (pm, pex))
            elif pex == "DIGITIZED" and transcribed:
                flag(line, "P_PROVENANCE_CONTRADICTS_UNIT",
                     "the unit is Extraction_Method=TRANSCRIBED, so there is no "
                     "digitized point cloud for a computed p")

        # ---- the tie claim must be recorded, and backed by the points -----
        if at in FIG_RANK_STATISTICS:
            ties = kernel.fig_as_bool(row.get("Ties_Present"))
            if ties is None:
                flag(line, "MISSING_TIES_PRESENT",
                     "a rank statistic's null distribution depends on ties - "
                     "record Ties_Present TRUE/FALSE")
            elif ties == "BAD":
                flag(line, "BAD_TIES_PRESENT",
                     "Ties_Present=%r (expected TRUE/FALSE)" % row.get("Ties_Present"))
            elif ties is True and pm in FIG_UNTIED_P_METHODS:
                flag(line, "TIES_CONTRADICT_P_METHOD",
                     "%s assumes untied ranks, but Ties_Present=TRUE" % pm)
            elif ties is False and pm == "SOURCE_P_REQUIRED_TIES":
                flag(line, "TIES_CONTRADICT_P_METHOD",
                     "SOURCE_P_REQUIRED_TIES exists because ties block the exact "
                     "test, but Ties_Present=FALSE")
        # The point cloud is the primary record of a digitized association, not
        # an accessory to the p-value. Gating this on the p provenance let a
        # digitized r with a transcribed p - or with no p at all - pass with no
        # way to audit the effect itself. The rule is on the unit's extraction
        # method and nothing else.
        if digitized and blank(row.get("Point_Data_Reference")):
            flag(line, "MISSING_POINT_DATA_REFERENCE",
                 "a digitized association is only auditable against the points it "
                 "was computed from - record where they are, whatever the p's origin")

        # ---- did the reader count the study, or count its own blobs? ------
        # An association is a function of a point set. If the point set is not
        # the one the paper describes, the number is not the paper's number -
        # and `N_Pairs` on its own cannot show that, because it IS the count
        # that went into the calculation.
        agreement = ("" if blank(row.get("Point_Count_Agreement"))
                     else str(row.get("Point_Count_Agreement")).strip().upper())
        # Required wherever there IS a point cloud. The runner fills these, so
        # an automated row always has them - but a hand-assembled bundle, a new
        # reader, or an adapter that quietly drops a column would produce rows
        # the gate then judged on the numbers alone, which is the state this
        # whole block exists to end. A transcribed association has no cloud and
        # is not asked.
        if digitized:
            for field in ("Detected_Unique_Point_Count", "Point_Count_Agreement",
                          "Overplotting_Possible", "Series_Mask_Overlap_Count"):
                if blank(row.get(field)):
                    flag(line, "MISSING_POINT_COUNT_AUDIT",
                         "%s is blank - a digitized association must say how "
                         "many marks it found and whether that is the sample "
                         "the paper describes" % field)
            # `Expected_N_From_Source` is the one field that may legitimately be
            # empty, because the paper does not always give an n. Saying so is
            # NO_SOURCE_N; leaving both blank is saying nothing.
            if (blank(row.get("Expected_N_From_Source"))
                    and agreement and agreement != "NO_SOURCE_N"):
                flag(line, "MISSING_POINT_COUNT_AUDIT",
                     "Expected_N_From_Source is blank but Point_Count_Agreement "
                     "says %s; a comparison needs both numbers, and a source "
                     "that gives no n is Point_Count_Agreement=NO_SOURCE_N"
                     % agreement)
            elif (not blank(row.get("Expected_N_From_Source"))
                    and agreement == "NO_SOURCE_N"):
                flag(line, "POINT_COUNT_AUDIT_CONTRADICTS_SOURCE",
                     "Point_Count_Agreement=NO_SOURCE_N beside "
                     "Expected_N_From_Source=%s" % row.get("Expected_N_From_Source"))
        if agreement and agreement not in FIG_POINT_COUNT_AGREEMENT:
            flag(line, "BAD_POINT_COUNT_AGREEMENT",
                 "Point_Count_Agreement=%s (expected %s)"
                 % (agreement, "/".join(FIG_POINT_COUNT_AGREEMENT)))
        elif agreement in ("FEWER_DETECTED", "MORE_DETECTED"):
            flag(line, "POINT_COUNT_DISAGREES_WITH_SOURCE",
                 "the source declares n=%s and the reader found %s distinct marks"
                 % (row.get("Expected_N_From_Source"),
                    row.get("Detected_Unique_Point_Count")))
        unique = num(row.get("Detected_Unique_Point_Count"))
        if unique is not None and np_ is not None and unique < np_:
            flag(line, "POINT_COUNT_INCLUDES_COINCIDENT_MARKS",
                 "N_Pairs=%g was computed from more marks than the %g distinct "
                 "positions found; coincident contours were counted twice"
                 % (np_, unique))
        overlap = num(row.get("Series_Mask_Overlap_Count"))
        if overlap is not None and overlap > 0:
            flag(line, "SERIES_MASK_OVERLAP",
                 "%g detected marks fall inside another series' colour mask, so "
                 "which series they belong to is not established by colour"
                 % overlap)
        overplot = kernel.fig_as_bool(row.get("Overplotting_Possible"))
        if overplot == "BAD":
            flag(line, "BAD_OVERPLOTTING_POSSIBLE",
                 "Overplotting_Possible=%r (expected TRUE/FALSE)"
                 % row.get("Overplotting_Possible"))

        if require_dual:
            _dual(kernel, row, flag, line,
                  ("Association_Value_R1", "Association_Value_R2", "Association_Value"),
                  dual_tolerance_pct, reconciled=_rec)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def fig_validate_bundle(figures, grids, units, values, kernel,
                        require_dual=False, dual_tolerance_pct=5.0, ranges=None,
                        file_root=".", check_files=True, run_dir=None):
    """Validate the four-file bundle. `kernel` is required, not optional.

    File existence is checked by DEFAULT. A manifest pointing at an image or a
    WPD project that is not there records provenance nobody can follow, and the
    only way to notice is to look. Pass check_files=False deliberately when
    validating a CSV away from its images; the absence then goes on the record
    as a choice rather than as silence.
    """
    if kernel is None:
        raise ValueError("kernel is required: without it the value checks are inert")
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    for name, df, cols in (("figures", figures, fig_figure_columns()),
                           ("grids", grids, fig_grid_columns()),
                           ("units", units, fig_unit_columns()),
                           ("values", values, fig_values_columns())):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            flag(name, "SCHEMA_INCOMPLETE", "missing columns: " + ", ".join(missing))
    if problems:
        return pd.DataFrame(problems)

    blank, num = kernel.fig_is_blank, kernel.fig_as_number

    # Two roots, and a path may be relative to either. `file_root` is where the
    # publisher rasters live. `run_dir` is where a run wrote its own outputs -
    # the point files, the WPD projects, the overlays - and those are recorded
    # RELATIVE to it, so that a run directory can be moved or handed to someone
    # else without every provenance link in the accepted file going stale.
    _roots = [r for r in (file_root, run_dir) if r]

    def _candidates(v):
        p = str(v).strip()
        return [p] + [os.path.join(r, p) for r in _roots]

    def missing_file(v):
        if not check_files or blank(v):
            return False
        return not any(os.path.exists(c) for c in _candidates(v))

    def resolved_file(v):
        for c in _candidates(v):
            if os.path.exists(c):
                return c
        return None

    # ------------------------------------------------------------- figures
    fig = {}
    for i, r in figures.iterrows():
        line = "figures:%d" % (i + 2)
        fid = str(r["Figure_ID"]).strip()
        if not fid:
            flag(line, "MISSING_REQUIRED", "Figure_ID")
            continue
        if fid in fig:
            flag(line, "DUPLICATE_FIGURE_ID", fid)
        fig[fid] = r
        for c in ("Publication_ID", "Source_File", "Source_Page", "Figure_Number"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        if missing_file(r.get("Source_Image")):
            flag(line, "SOURCE_FILE_NOT_FOUND",
                 "Source_Image=%r is recorded but not on disk" % r.get("Source_Image"))
        # A figure with several digitized panels names several projects, one per
        # panel, because one tar cannot re-derive six panels' marks.
        for part in str(r.get("WPD_Project_File", "")).split(";"):
            if part.strip() and missing_file(part.strip()):
                flag(line, "SOURCE_FILE_NOT_FOUND",
                     "WPD_Project_File=%r is recorded but not on disk" % part.strip())
        # The image identity is part of provenance, not decoration.  A saved
        # WPD project can be perfectly reproducible against the wrong raster,
        # so verify both dimensions and the recorded SHA-256 prefix/full hash.
        image_path = resolved_file(r.get("Source_Image"))
        identity = str(r.get("Image_Resolution_Or_Hash", "")).strip()
        dim = re.search(r"(?i)(\d+)\s*x\s*(\d+)", identity) if identity else None
        digest = (re.search(r"(?i)sha256\s*:\s*([0-9a-f]{8,64})", identity)
                  if identity else None)
        if identity and not dim and not digest:
            flag(line, "IMAGE_HASH_UNPARSEABLE",
                 "expected WIDTHxHEIGHT and/or sha256:<8-64 hex>, got %r" % identity)
        if check_files and image_path and identity:
            try:
                with Image.open(image_path) as im:
                    actual_size = im.size
                if dim and actual_size != (int(dim.group(1)), int(dim.group(2))):
                    flag(line, "IMAGE_DIMENSION_MISMATCH",
                         "recorded %sx%s, actual %sx%s" %
                         (dim.group(1), dim.group(2), actual_size[0], actual_size[1]))
                if digest:
                    actual = hashlib.sha256(open(image_path, "rb").read()).hexdigest()
                    wanted = digest.group(1).lower()
                    if not actual.startswith(wanted):
                        flag(line, "IMAGE_HASH_MISMATCH",
                             "recorded sha256:%s, actual sha256:%s" % (wanted, actual))
            except (OSError, ValueError) as exc:
                flag(line, "SOURCE_IMAGE_UNREADABLE", str(exc))
        prs = str(r.get("Panel_Reconciliation_Status", "")).strip().upper()
        obs, wl = num(r.get("Observed_Panel_Count")), num(r.get("Worklist_Panel_Count"))
        if blank(r.get("Panel_Reconciliation_Status")) or prs == "PENDING":
            flag(line, "PANEL_RECONCILIATION_PENDING", "count the panels on screen")
        elif prs not in FIG_PANEL_RECON:
            flag(line, "BAD_PANEL_RECONCILIATION_STATUS", prs)
        elif obs is None or wl is None:
            flag(line, "MISSING_PANEL_COUNT", "both counts are required")
        else:
            bad = [(n_, v) for n_, v in (("Observed_Panel_Count", obs),
                                         ("Worklist_Panel_Count", wl))
                   if v <= 0 or v != int(v)]
            for n_, v in bad:
                flag(line, "PANEL_COUNT_INVALID", "%s=%g must be a positive integer" % (n_, v))
            if not bad:
                want = ("MATCHED" if obs == wl else
                        "UNLISTED_PANELS_FOUND" if obs > wl else "WORKLIST_OVERCOUNTS")
                if prs != want:
                    flag(line, "PANEL_STATUS_CONTRADICTS_COUNTS",
                         "observed %d vs worklist %d implies %s, not %s" % (obs, wl, want, prs))
                if obs > wl and blank(r.get("Unlisted_Panels")):
                    flag(line, "UNLISTED_PANELS_NOT_RECORDED", "name the omitted panels")

    # --------------------------------------------------------------- grids
    declared, orders = {}, {}
    for i, r in grids.iterrows():
        line = "grids:%d" % (i + 2)
        gid, fac, lvl = (str(r["Grid_ID"]).strip(), str(r["Factor_Name"]).strip().upper(),
                         str(r["Factor_Level"]).strip().upper())
        if not gid or not fac or not lvl:
            flag(line, "MISSING_REQUIRED", "Grid_ID / Factor_Name / Factor_Level")
            continue
        levels = declared.setdefault(gid, {}).setdefault(fac, [])
        if lvl in levels:
            flag(line, "DUPLICATE_FACTOR_LEVEL", "%s: %s=%s" % (gid, fac, lvl))
        else:
            levels.append(lvl)
        o = num(r.get("Level_Order"))
        if o is None or o != int(o):
            flag(line, "BAD_LEVEL_ORDER",
                 "%s %s=%s: Level_Order=%r must be an integer"
                 % (gid, fac, lvl, r.get("Level_Order")))
        else:
            orders.setdefault(gid, {}).setdefault(fac, []).append(int(o))
    for gid, facs in orders.items():
        for fac, os_ in facs.items():
            if len(set(os_)) != len(os_):
                flag("grid:%s" % gid, "BAD_LEVEL_ORDER",
                     "%s: Level_Order repeats %s" % (fac, sorted(os_)))
            elif sorted(os_) != list(range(min(os_), min(os_) + len(os_))):
                flag("grid:%s" % gid, "BAD_LEVEL_ORDER",
                     "%s: Level_Order is not contiguous %s" % (fac, sorted(os_)))

    # --------------------------------------------------------------- units
    unit = {}
    for i, r in units.iterrows():
        line = "units:%d" % (i + 2)
        uid = str(r["Unit_ID"]).strip()
        if not uid:
            flag(line, "MISSING_REQUIRED", "Unit_ID")
            continue
        if uid in unit:
            flag(line, "DUPLICATE_UNIT_ID", uid)
        unit[uid] = r
        fid, gid = str(r.get("Figure_ID", "")).strip(), str(r.get("Grid_ID", "")).strip()
        if fid and fid not in fig:
            flag(line, "UNKNOWN_FIGURE_ID", fid)
        if gid and gid not in declared:
            flag(line, "UNKNOWN_GRID_ID", gid)
        validate_unit(r, kernel, flag, line, figure=fig.get(fid))

    # -------------------------------------------------------------- values
    seen = {}
    for i, r in values.iterrows():
        line = "values:%d" % (i + 2)
        uid = str(r["Unit_ID"]).strip()
        if uid not in unit:
            flag(line, "UNKNOWN_UNIT_ID", uid)
            continue
        u = unit[uid]
        cell = fig_parse_cell_key(r["Cell_Key"])
        if cell is None:
            flag(line, "BAD_CELL_KEY",
                 "%r does not parse as unique FACTOR=LEVEL pairs" % r["Cell_Key"])
            continue
        decl = declared.get(str(u.get("Grid_ID", "")).strip(), {})
        if set(cell) != set(decl):
            flag(line, "FACTOR_SET_INCONSISTENT",
                 "%s: cell uses %s, grid declares %s" % (uid, sorted(cell), sorted(decl)))
            continue
        for fac, lvl in cell.items():
            if lvl not in decl[fac]:
                flag(line, "UNDECLARED_FACTOR_LEVEL",
                     "%s: %s=%s is not among %s" % (uid, fac, lvl, decl[fac]))
        # What the reader found for THIS cell outranks what a person typed once
        # for the whole unit. A panel with three confirmed whiskers and one
        # unconfirmed used to pass on the strength of the three, because the
        # gate never saw the per-mark result at all.
        if str(u.get("Extraction_Method", "")).strip().upper() == "DIGITIZED" \
                and str(u.get("Statistic_Type", "")).strip().upper() == "CONTINUOUS" \
                and str(u.get("Dispersion_Type", "")).strip().upper() != "NO_ERRORBAR" \
                and not blank(r.get("Dispersion_Value")):
            cell_stem = kernel.fig_as_bool(r.get("Errorbar_Stem_Confirmed"))
            if cell_stem == "BAD":
                flag(line, "BAD_ERRORBAR_STEM_FLAG",
                     "Errorbar_Stem_Confirmed=%r on this cell"
                     % r.get("Errorbar_Stem_Confirmed"))
            elif cell_stem is False:
                flag(line, "CELL_ERRORBAR_STEM_UNCONFIRMED",
                     "the reader could not connect this cell's whisker to its "
                     "mark, whatever the unit row asserts")
        if not blank(r.get("Position_Assignment")) and str(
                r.get("Position_Assignment")).strip().upper() != "DECLARED_ANCHOR":
            flag(line, "POSITION_INFERRED",
                 "Position_Assignment=%s - this cell's x identity was counted "
                 "off rather than matched to a declared pixel"
                 % r.get("Position_Assignment"))
        key = fig_cell_key(cell)
        if key in seen.setdefault(uid, {}):
            flag(line, "FACTORIAL_CELL_DUPLICATE",
                 "%s: %s already read on %s" % (uid, key, seen[uid][key]))
        else:
            seen[uid][key] = line
        validate_value_by_statistic(r, u, kernel, flag, line,
                                    require_dual=require_dual,
                                    dual_tolerance_pct=dual_tolerance_pct, ranges=ranges)
        # A point file that is named but absent is the same empty promise as an
        # image or a WPD project that is not there.
        if missing_file(r.get("Point_Data_Reference")):
            flag(line, "SOURCE_FILE_NOT_FOUND",
                 "Point_Data_Reference=%r is recorded but not on disk"
                 % r.get("Point_Data_Reference"))

    # ---------------------------------------------------------- the grid
    for uid, u in unit.items():
        decl = declared.get(str(u.get("Grid_ID", "")).strip())
        if not decl:
            continue
        got = set(seen.get(uid, {}))
        # Expected_Cell_Count is DERIVED, never entered: a hand-typed count is one
        # more thing that can disagree with the declaration it summarises.
        expected = set(fig_cell_key(dict(zip(decl, combo)))
                       for combo in itertools.product(*[decl[f] for f in decl]))
        for fac, levels in decl.items():
            used = set()
            for kk in got:
                pp = fig_parse_cell_key(kk)
                if pp and fac in pp:
                    used.add(pp[fac])
            for lvl in levels:
                if lvl not in used:
                    flag("unit:%s" % uid, "FACTOR_LEVEL_MISSING",
                         "%s=%s is declared but never read" % (fac, lvl))
        missing = sorted(expected - got)
        if missing and str(u.get("Grid_Rule", "")).strip().upper() != "SPARSE":
            flag("unit:%s" % uid, "FACTORIAL_CELL_MISSING",
                 "%d of %d cells absent, e.g. %s" % (len(missing), len(expected), missing[:4]))
        extra = sorted(got - expected)
        if extra:
            flag("unit:%s" % uid, "UNDECLARED_FACTOR_LEVEL",
                 "%d cells outside the declared product, e.g. %s" % (len(extra), extra[:4]))
        if require_dual:
            vs = str(u.get("Independent_Verification_Status", "")).strip().upper()
            if blank(u.get("Extractor_2")):
                flag("unit:%s" % uid, "NO_SECOND_EXTRACTOR", "Extractor_2 blank")
            if vs not in FIG_DUAL_OK:
                flag("unit:%s" % uid, "NO_DUAL_EXTRACTION",
                     "Independent_Verification_Status=%s (expected %s)"
                     % (vs or "blank", "/".join(FIG_DUAL_OK)))
            elif vs == "RECONCILED" and blank(u.get("Discrepancy_Note")):
                flag("unit:%s" % uid, "RECONCILED_WITHOUT_NOTE",
                     "write down how the disagreement was resolved")

    return pd.DataFrame(problems)


def fig_expected_cell_count(grids, grid_id):
    """Derived cell count for a Grid_ID - the only place this number comes from."""
    decl = {}
    for _, r in grids[grids["Grid_ID"] == grid_id].iterrows():
        decl.setdefault(str(r["Factor_Name"]).strip().upper(), set()).add(
            str(r["Factor_Level"]).strip().upper())
    n = 1
    for lv in decl.values():
        n *= len(lv)
    return n if decl else 0
