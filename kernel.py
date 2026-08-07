import pandas as pd
import numpy as np

FIG_SHAPES = ("A_CHALLENGE_TIMECOURSE", "B_CHALLENGE_2POINT", "C_LONGITUDINAL_SERIAL",
              "D_SIMPLE_PREPOST", "E_SCATTER_ASSOCIATION", "F_BINARY_EVENT",
              "G_FACTORIAL_CONDITIONS")
FIG_NULL_TOKENS = ("", "NAN", "NONE", "NOT_APPLICABLE", "NOT APPLICABLE", "NA", "N/A",
                   "N.A.", "NIL", "NULL", "-", "--", "\u2014", "\u2013",
                   "\uc5c6\uc74c", "\ud574\ub2f9\uc5c6\uc74c", "\ud574\ub2f9 \uc5c6\uc74c", "\ubbf8\uc801\uc6a9", "\ubbf8\ud574\ub2f9")
# Compact forms so "N. A.", "n / a" and "not applicable" also read as null.
FIG_NULL_COMPACT = ("", "NA", "NAN", "NONE", "NOTAPPLICABLE", "NIL", "NULL")
FIG_PHASES = ("PRE", "DURING", "POST", "RECOVERY", "DELTA", "ASSOCIATION")
FIG_FOLLOWUP_PHASES = ("DURING", "POST", "RECOVERY")
FIG_DISPERSION_TYPES = ("SD", "SE", "SEM", "CI95", "IQR", "RANGE", "NO_ERRORBAR")
FIG_ASYMMETRIC_TYPES = ("CI95", "IQR", "RANGE")
FIG_DUAL_OK = ("AGREED", "RECONCILED")
FIG_EXTRACTION_METHODS = ("DIGITIZED", "TRANSCRIBED")
# How the plotted value was located on a bar. A vector bar's data coordinate is
# the CENTRE of its stroke: reading the colour fill's edge sits 3-4 px inside a
# typical outline and biases every mean in the same direction.
# "NOT_A_BAR", not "NOT_APPLICABLE": the latter is a NULL token, so fig_is_blank
# would read a filled-in answer as an empty cell.
FIG_BAR_TOP_DEFS = ("OUTLINE_CENTER", "FILL_EDGE", "MARKER_CENTER", "NOT_A_BAR")
FIG_PANEL_RECON = ("MATCHED", "UNLISTED_PANELS_FOUND", "WORKLIST_OVERCOUNTS", "PENDING")
# Text that records a NON-ANSWER. Errorbar_Definition_Source exists to carry the
# source's own wording; a placeholder there means the SD/SE question was never
# settled, and getting it wrong scales the meta-analytic weight by sqrt(n). A
# blank-only check cannot see these, so they are named explicitly.
FIG_UNRESOLVED_MARKERS = ("PLACEHOLDER", "UNRESOLVED", "TBD", "TODO", "UNKNOWN",
                          "UNCLEAR", "NOT STATED", "NOT SPECIFIED", "NOT REPORTED",
                          "NOT GIVEN", "NOT DEFINED", "ASSUMED", "PRESUMED",
                          "GUESS", "FIXME", "XXX", "???", "HARNESS")
FIG_BOOL_TRUE = ("TRUE", "T", "YES", "Y", "1")
FIG_BOOL_FALSE = ("FALSE", "F", "NO", "N", "0")
FIG_ASSOCIATION_TYPES = {
    "PEARSON_R": "PEARSON_R", "PEARSON": "PEARSON_R",
    "PEARSON_CORRELATION": "PEARSON_R", "PEARSON_CORRELATION_COEFFICIENT": "PEARSON_R",
    "R": "PEARSON_R", "CORRELATION": "PEARSON_R", "CORRELATION_COEFFICIENT": "PEARSON_R",
    "SPEARMAN_RHO": "SPEARMAN_RHO", "SPEARMAN": "SPEARMAN_RHO",
    "SPEARMAN_CORRELATION": "SPEARMAN_RHO", "SPEARMAN_R": "SPEARMAN_RHO",
    "RHO": "SPEARMAN_RHO", "RS": "SPEARMAN_RHO",
    "KENDALL_TAU": "KENDALL_TAU", "KENDALL": "KENDALL_TAU", "TAU": "KENDALL_TAU",
    "R_SQUARED": "R_SQUARED", "R2": "R_SQUARED",
    "SLOPE": "SLOPE", "REGRESSION_SLOPE": "SLOPE", "BETA": "SLOPE",
}
FIG_BOUNDED_ASSOCIATIONS = ("PEARSON_R", "SPEARMAN_RHO", "KENDALL_TAU")


def fig_normalize_association_type(value):
    """Map a free-text association label onto the controlled vocabulary.

    Extractors write "Pearson correlation", "spearman", "r" for the same
    statistic. A range check keyed on a fixed set of exact strings silently skips
    every spelling it does not recognise, so r = 1.5 passed under the label
    "Pearson correlation". Returns (canonical_or_None, raw_upper).
    """
    raw = str(value or "").strip().upper()
    key = "_".join(w for w in raw.replace("-", " ").replace("_", " ").split())
    return FIG_ASSOCIATION_TYPES.get(key), raw

# NOTE: a bare r"predict" was removed here. "Predicted heart rate at each tilt
# angle" and "Predictors of orthostatic intolerance" are mean-difference figures,
# and routing them to E fabricates an association out of a group mean. Require
# correlation/regression wording or an explicitly reported statistic instead.
FIG_ASSOCIATION_PATTERNS = (r"correlation", r"correlat", r"regression", r"relationships? between",
                            r"\bversus\b.{0,30}\bplot\b", r"scatter", r"\br\s*=\s*[-0-9.]",
                            r"regressed", r"\bpredicted (?:by|from) (?:the )?(?:model|equation|fit)\b",
                            r"\b(?:R2|R\^2)\s*=\s*[-0-9.]", r"\b(?:rho|\u03c1)\s*=\s*[-0-9.]",
                            r"\bbeta\s*=\s*[-0-9.]", r"\bline of best fit\b",
                            r"\bleast[- ]squares\b")
FIG_BINARY_PATTERNS = (r"incidence", r"proportion of (?:subjects|participants|patients)",
                       r"percentage of (?:subjects|participants|patients)",
                       r"number of (?:subjects|participants) who", r"\bpie chart\b",
                       r"event rate", r"\bfailure to complete\b", r"\bprevalence\b")
FIG_NOTDATA_PATTERNS = (r"schemat", r"diagram", r"protocol", r"study design", r"timeline",
                        r"apparatus", r"experimental setup", r"example of", r"representative",
                        r"typical", r"photograph", r"illustrat", r"flow ?chart",
                        r"anatomic(?:al)? view", r"echographic view", r"ultrasound image",
                        r"\bMRI\b image", r"sample (?:trace|record|tracing)", r"raw (?:trace|signal)",
                        # A caption that calls itself a drawing is a schematic. "model of" is
                        # NOT listed alone - that would also exclude mathematical-model results -
                        # so it is qualified by a hardware noun.
                        r"\bdrawings?\b", r"\bline art\b",
                        r"\bmodel of (?:the |a |an |our )?(?:apparatus|device|chair|centrifuge|seat|rig|couch|sled|capsule|tilt table|harness|hardware|equipment|facility mock-?up)\b")


def fig_template_columns():
    """Input schema for digitized figure values.

    Extraction unit = Publication x Figure x Panel x Outcome. Dual extraction is
    stored as two independent readings (R1/R2) plus a consensus value, so the
    agreement check compares numbers instead of trusting a status label.
    """
    return [
        "Publication_ID", "Source_File", "Source_Page", "Source_Image",
        "Source_Caption_Verbatim", "Figure_Number", "Panel", "Data_Shape",
        "Outcome_Variable", "Outcome_Domain", "Unit",
        "Arm", "Posture_Condition", "Exposure_Phase", "Timepoint_Label", "Timepoint_Days",
        "Mean_R1", "Dispersion_R1", "Mean_R2", "Dispersion_R2",
        "Mean", "Dispersion_Value", "Errorbar_Lower", "Errorbar_Upper", "Dispersion_Type",
        "Errorbar_Definition_Source", "N_Outcome",
        "WPD_Project_File", "Axis_X_Scale", "Axis_Y_Scale",
        "Axis_Calib_X1_Value", "Axis_Calib_X1_Pixel", "Axis_Calib_X2_Value", "Axis_Calib_X2_Pixel",
        "Axis_Calib_Y1_Value", "Axis_Calib_Y1_Pixel", "Axis_Calib_Y2_Value", "Axis_Calib_Y2_Pixel",
        "Image_Resolution_Or_Hash",
        # Required, not optional: every geometry check below is gated on it, so a
        # template without this column silently skips them. The association and
        # binary schemas already carried it; the continuous one did not, and the
        # unit tests hid that by adding the key outside fig_template_columns().
        "Extraction_Method",
        "Bar_Top_Definition", "Errorbar_Stem_Confirmed",
        "Observed_Panel_Count", "Worklist_Panel_Count", "Unlisted_Panels",
        "Panel_Reconciliation_Status",
        "Extractor_1", "Extractor_2", "Independent_Verification_Status",
        "Discrepancy_Note", "Date", "Note",
    ]


def fig_binary_event_columns():
    """Schema for F_BINARY_EVENT figures (incidence / proportion / pie charts).

    An event count is not a mean: it needs events and denominators per group so a
    risk ratio or odds ratio can be computed. Never route these into the
    mean/dispersion template.
    """
    return [
        "Publication_ID", "Source_File", "Source_Page", "Source_Caption_Verbatim",
        "Figure_Number", "Panel", "Outcome_Variable", "Event_Definition",
        "Arm", "Exposure_Phase", "Timepoint_Label",
        "Events", "N_at_Risk", "Arm_Comparator", "Events_Comparator", "N_at_Risk_Comparator",
        "Effect_Measure", "P_Value_Reported",
        "Events_R1", "Events_R2",
        "N_at_Risk_R1", "N_at_Risk_R2",
        "Events_Comparator_R1", "Events_Comparator_R2",
        "N_at_Risk_Comparator_R1", "N_at_Risk_Comparator_R2",
        "Independent_Verification_Status", "Discrepancy_Note",
        "Extraction_Method",
        "WPD_Project_File", "Image_Resolution_Or_Hash", "Source_Image",
        "Extractor_1", "Extractor_2", "Date", "Note",
    ]


def fig_association_columns():
    """Schema for E_SCATTER_ASSOCIATION figures (correlation / regression plots).

    These carry an association statistic, not a group mean, so they must never be
    read with the mean-difference template.
    """
    return [
        "Publication_ID", "Source_File", "Source_Page", "Source_Caption_Verbatim",
        "Figure_Number", "Panel", "Outcome_Variable", "Predictor_Variable",
        "Association_Type", "Association_Value", "CI_Lower", "CI_Upper",
        "P_Value", "N_Pairs", "Model_Covariates",
        "Association_Value_R1", "Association_Value_R2",
        "Independent_Verification_Status", "Discrepancy_Note",
        "Extraction_Method",
        "WPD_Project_File", "Image_Resolution_Or_Hash", "Source_Image",
        "Axis_X_Scale", "Axis_Y_Scale",
        "Axis_Calib_X1_Value", "Axis_Calib_X2_Value",
        "Axis_Calib_Y1_Value", "Axis_Calib_Y2_Value",
        "Extractor_1", "Extractor_2", "Date", "Note",
    ]


def fig_default_ranges():
    """Plausible value ranges for common cardiovascular outcomes."""
    return {"Heart rate": (30, 220), "Systolic blood pressure": (60, 220),
            "Diastolic blood pressure": (30, 130), "Mean arterial pressure": (45, 150),
            "Stroke volume": (15, 200), "Cardiac output": (1.5, 20),
            "Pulse pressure": (10, 100),
            "Total peripheral resistance": (0.3, 80), "Cerebral blood flow velocity": (15, 120),
            "MSNA": (2, 100), "Plasma volume": (1200, 5500), "Peak VO2": (8, 80),
            "HRV RMSSD": (1, 300), "HRV SDNN": (1, 300), "Minute ventilation": (3, 200)}


FIG_OUTCOME_ALIASES = {
    "HR": "Heart rate", "HEART RATE": "Heart rate", "PULSE RATE": "Heart rate",
    "SBP": "Systolic blood pressure", "SYSTOLIC BP": "Systolic blood pressure",
    "SYSTOLIC PRESSURE": "Systolic blood pressure",
    "DBP": "Diastolic blood pressure", "DIASTOLIC BP": "Diastolic blood pressure",
    "DIASTOLIC PRESSURE": "Diastolic blood pressure",
    "MAP": "Mean arterial pressure", "MEAN BP": "Mean arterial pressure",
    "MEAN ARTERIAL BLOOD PRESSURE": "Mean arterial pressure",
    "SV": "Stroke volume", "STROKE INDEX": "Stroke volume",
    "CO": "Cardiac output", "CARDIAC INDEX": "Cardiac output",
    "TPR": "Total peripheral resistance", "SVR": "Total peripheral resistance",
    "SYSTEMIC VASCULAR RESISTANCE": "Total peripheral resistance",
    "CBFV": "Cerebral blood flow velocity", "MCAV": "Cerebral blood flow velocity",
    "MIDDLE CEREBRAL ARTERY VELOCITY": "Cerebral blood flow velocity",
    "MUSCLE SYMPATHETIC NERVE ACTIVITY": "MSNA",
    "PV": "Plasma volume",
    "VO2PEAK": "Peak VO2", "PEAK VO2": "Peak VO2", "VO2 PEAK": "Peak VO2", "VO2MAX": "Peak VO2",
    "RMSSD": "HRV RMSSD", "SDNN": "HRV SDNN",
    "VE": "Minute ventilation", "MINUTE VENTILATION": "Minute ventilation",
}


def fig_normalize_outcome_name(name):
    """Fold an Outcome_Variable cell onto its canonical range-table key.

    Strips a trailing unit or abbreviation parenthetical ("Heart rate (bpm)"),
    case-folds and collapses punctuation, then consults FIG_OUTCOME_ALIASES.
    Returns None when nothing matches.

    Abbreviation aliases are safe HERE and nowhere else: Outcome_Variable is a
    curated column an extractor fills from a controlled list. The same mapping
    must NOT be applied to caption prose, where CO is a control group and PV is
    a portal vein - see fig_ambiguous_tokens for that direction.
    """
    import re as _re
    if fig_is_blank(name):
        return None
    s = _re.sub(r"\([^)]*\)", " ", str(name))
    s = _re.sub(r"[\s\-_/]+", " ", s).strip().upper()
    if not s:
        return None
    if s in FIG_OUTCOME_ALIASES:
        return FIG_OUTCOME_ALIASES[s]
    for canon in fig_default_ranges():
        if _re.sub(r"[\s\-_/]+", " ", canon).strip().upper() == s:
            return canon
    return None


def fig_lookup_range(name, ranges):
    """(canonical_name, (lo, hi)) for an Outcome_Variable cell, or (None, None).

    Tries the cell verbatim first so a caller-supplied `ranges` dict with its own
    keys keeps working, then falls back to the normalized/alias form.
    """
    key = None if name is None else str(name)
    if key in ranges:
        return key, ranges[key]
    canon = fig_normalize_outcome_name(name)
    if canon is not None and canon in ranges:
        return canon, ranges[canon]
    return None, None


def fig_unresolved_marker(v):
    """The placeholder token a cell contains, or None.

    Matched on the upper-cased text, so "TODO: check paper", "assumed SE" and
    "HARNESS PLACEHOLDER - unresolved" are all caught.
    """
    if fig_is_blank(v):
        return None
    s = str(v).upper()
    for tok in FIG_UNRESOLVED_MARKERS:
        if tok in s:
            return tok
    return None


def fig_panel_name_set(v):
    """Normalized set of panel names from a free-text cell.

    "PAP", "pap", " PAP , MAP " and "MAP;PAP" must compare equal - otherwise a
    consistency check turns into a spelling check.
    """
    import re as _re
    if fig_is_blank(v):
        return frozenset()
    parts = _re.split(r"[,;/|]+|\s{2,}", str(v))
    return frozenset(p.strip().upper() for p in parts if p.strip())


def fig_as_bool(v):
    """TRUE / FALSE / None for a tri-state flag cell.

    None means "not answered" - which for a confirmation flag is NOT the same as
    FALSE, and must not silently pass as one.
    """
    if fig_is_blank(v):
        return None
    s = str(v).strip().upper()
    if s in FIG_BOOL_TRUE:
        return True
    if s in FIG_BOOL_FALSE:
        return False
    return "BAD"


def fig_is_bad_number(v):
    """True when a cell holds text that was MEANT to be a number.

    fig_as_number returns None both for an empty cell and for "abc", so a caller
    that only tests `is None` cannot tell "not filled in" from "filled in wrong" -
    and a typo silently becomes a missing value. Use this to raise NON_NUMERIC_*
    instead of MISSING_*.
    """
    return (not fig_is_blank(v)) and fig_as_number(v) is None


def fig_check_numeric(r, cols, flag, line):
    """Flag every column in `cols` whose cell is non-blank but not a number."""
    for c in cols:
        if c in r and fig_is_bad_number(r.get(c)):
            flag(line, "NON_NUMERIC_VALUE",
                 "%s=%r is not a number - a mis-typed value must not read as missing"
                 % (c, r.get(c)))


def fig_as_number(v):
    """Return a finite float, or None for blank / NaN / non-numeric input."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return f


def fig_is_blank(v):
    """True for None, NaN, empty string and the usual null tokens.

    The vocabulary covers the spellings coders actually type - "N/A", "N.A.",
    "-", an em dash, and the Korean forms - because a null spelled a way this
    function does not know reads as a real value. That is how "N/A" in a
    challenge column used to promote a pre/post study to a challenge design.
    """
    import re as _re
    if v is None:
        return True
    try:
        if isinstance(v, float) and not np.isfinite(v):
            return True
    except (TypeError, ValueError):
        pass
    s = str(v).strip().upper()
    if s in FIG_NULL_TOKENS:
        return True
    return _re.sub(r"[\s./\\_-]", "", s) in FIG_NULL_COMPACT


def fig_normalize_caption(caption):
    """Undo PDF line-break hyphenation and collapse whitespace.

    PDF text layers split words across lines as "rela- tionships", which defeats
    any keyword match. Join hyphen-space-letter sequences before screening.
    """
    import re
    cap = str(caption or "")
    cap = re.sub(r"(\w)[\u00ad-]\s+(\w)", r"\1\2", cap)
    cap = re.sub(r"\s+", " ", cap)
    return cap.strip()


def fig_split_merged_caption(caption, figure_label=None):
    """Cut a caption at the next figure label.

    A PDF text layer often runs consecutive captions together
    ("Fig. 1 Time course of ... Fig. 2 Sectional change of ..."), so the row for
    Fig. 1 carries Fig. 2's text and the row for Fig. 2 may start mid-sentence.
    Screening such a caption reads the wrong figure's wording.

    With figure_label, the text is first advanced to that label's own occurrence;
    then everything from the following label onward is dropped.
    """
    import re
    cap = fig_normalize_caption(caption)
    lab_re = r"(?:Fig(?:ure)?s?\.?\s*\d+[a-zA-Z]?)"
    if figure_label:
        key = re.escape(fig_normalize_caption(figure_label).rstrip("."))
        m = re.search(key + r"\b", cap, re.I)
        if m:
            cap = cap[m.start():]
    hits = list(re.finditer(lab_re, cap, re.I))
    start = hits[0].end() if hits and hits[0].start() == 0 else 0
    for h in hits:
        if h.start() > start:
            return cap[:h.start()].strip()
    return cap.strip()


def fig_detect_panels(caption, panel_hint=None):
    """List the panel identifiers a caption exposes, or [''] when it exposes none.

    Recognises lettered panels ("(A)", "Fig. 4A", "panels a-c") and inline
    parameter panel lists ("VI VT f HR"), which is how multi-parameter figures
    label their sub-plots. Returns [] only for an empty caption.
    """
    import re
    cap = fig_normalize_caption(caption)
    if not cap:
        return [""]
    if panel_hint:
        return [p.strip() for p in str(panel_hint).split(";") if p.strip()]
    letters = set()
    for m in re.finditer(r"\(([A-Ha-h])\)", cap):
        letters.add(m.group(1).upper())
    for m in re.finditer(r"Fig(?:ure)?s?\.?\s*\d+\s*([A-Ha-h])\b", cap):
        letters.add(m.group(1).upper())
    for m in re.finditer(r"panels?\s+([A-Ha-h])\s*(?:[-\u2013to]+)\s*([A-Ha-h])\b", cap, re.I):
        a, b = sorted([m.group(1).upper(), m.group(2).upper()])
        letters.update(chr(c) for c in range(ord(a), ord(b) + 1))
    if letters:
        return sorted(letters)
    params = fig_detect_parameter_panels(cap)
    if len(params) > 1:
        return params
    return [""]


def fig_ambiguous_tokens():
    """Tokens that must be POSITIVELY defined in the caption to count.

    These abbreviations collide with statistical, anatomical or group vocabulary
    (CI = confidence interval, PV = portal vein, CO = control group, SI = SI
    units, PP = plasma protein). A bare occurrence is not evidence; the caption
    must spell out the outcome the token stands for, e.g. "cardiac index (CI)".
    Maps token -> patterns that qualify it.
    """
    return {
        "CI": (r"cardiac index",),
        "PV": (r"plasma volume",),
        "CO": (r"cardiac output",),
        "SI": (r"stroke index",),
        "PP": (r"pulse pressure",),
        "BP": (r"blood pressure", r"\bBP\b"),
        "PV_BLOCK": (),
    }


def fig_token_denotes_outcome(token, caption):
    """True when `token` reads as its mapped outcome in this caption.

    Ambiguous tokens (fig_ambiguous_tokens) require the outcome to be named in
    prose somewhere in the caption; unambiguous ones need only appear. This is
    deliberately conservative: a missed panel stays a merged row flagged for
    visual check, while a false panel writes an off-target figure into the
    mean-difference template.
    """
    import re
    tok = str(token).upper()
    cap = fig_normalize_caption(caption)
    if not re.search(r"\b" + re.escape(tok) + r"\b", cap, re.I):
        return False
    amb = fig_ambiguous_tokens()
    if tok in amb:
        return any(re.search(p, cap, re.I) for p in amb[tok])
    return True


def fig_parameter_panel_tokens():
    """Short parameter tokens that appear as axis labels of multi-panel figures.

    Maps a token to the outcome label it denotes. Axis labels are not sentences,
    so a caption screener that only reads prose misses them - "VI VT f HR" is a
    four-panel figure whose fourth panel is heart rate.
    """
    return {"HR": "Heart rate", "MAP": "Mean arterial pressure",
            "BP": "Blood pressure", "SAP": "Systolic blood pressure",
            "DAP": "Diastolic blood pressure", "ABP": "Blood pressure",
            "SBP": "Systolic blood pressure", "DBP": "Diastolic blood pressure",
            "SV": "Stroke volume", "SI": "Stroke index", "CO": "Cardiac output",
            "CI": "Cardiac index", "TPR": "Total peripheral resistance",
            "SVR": "Total peripheral resistance", "MSNA": "MSNA",
            "BRS": "Baroreflex sensitivity", "RMSSD": "HRV RMSSD", "SDNN": "HRV SDNN",
            "PNN50": "HRV pNN50", "MCAV": "Cerebral blood flow velocity",
            "CBFV": "Cerebral blood flow velocity", "BPMCA": "Blood pressure",
            "CVRI": "Cerebrovascular resistance index", "PV": "Plasma volume",
            "VI": "Minute ventilation", "VE": "Minute ventilation", "VT": "Tidal volume",
            "VO2": "Oxygen uptake", "VCO2": "Carbon dioxide output", "FR": "Respiratory frequency",
            "PCO2": "Carbon dioxide partial pressure", "SPO2": "Oxygen saturation"}


def fig_detect_parameter_panels(caption):
    """Return the parameter tokens a caption/axis-label block exposes, in order.

    A token is kept only when fig_token_denotes_outcome confirms it is not a
    statistical or anatomical homonym in this caption.
    """
    import re
    cap = fig_normalize_caption(caption)
    toks = fig_parameter_panel_tokens()
    found = []
    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9]{0,4})\b", cap):
        t = m.group(1).upper()
        if t in toks and t not in found and fig_token_denotes_outcome(t, cap):
            found.append(t)
    return found


def fig_group_label_patterns():
    """Terms that name a GROUP or a TIMEPOINT, not an outcome.

    A caption saying "responses in women, presyncopal men and nonpresyncopal men"
    describes who was measured; "measured at baseline, presyncope and recovery"
    describes when. Neither says what was measured. If such a term sits in the
    target-outcome list, every figure about that cohort or protocol matches -
    including hormone, muscle and metabolic figures with no target outcome at all.
    Strip these before deciding a caption is on-target.

    Note the asymmetry that makes this subtle: "orthostatic tolerance" IS an
    outcome, while "at presyncope" is a timepoint and "presyncopal men" is a
    group. Screen the bare event word out and keep the outcome phrase in the
    target list (e.g. r"orthostatic toleran", r"tilt toleran", r"tolerance time").
    """
    return (r"presyncopal", r"nonpresyncopal", r"non-presyncopal",
            r"\bat presyncope\b", r"\bpresyncope and\b", r"\bpresyncope\b",
            r"\bfinishers?\b", r"\bnonfinishers?\b", r"\bfainters?\b",
            r"\bnonfainters?\b", r"\bmen\b", r"\bwomen\b", r"\bmales?\b",
            r"\bfemales?\b", r"crew ?members?", r"astronauts?", r"cosmonauts?",
            r"\bsubjects?\b", r"\bparticipants?\b", r"\bcontrols?\b",
            r"\bresponders?\b", r"\bnonresponders?\b", r"\btolerant\b",
            r"\bintolerant\b", r"\bbaseline\b", r"\brecovery\b")


def fig_strip_group_labels(caption):
    """Blank out group-label terms so they cannot pose as outcome evidence."""
    import re
    cap = fig_normalize_caption(caption)
    for p in fig_group_label_patterns():
        cap = re.sub(p, " ", cap, flags=re.I)
    return re.sub(r"\s+", " ", cap).strip()


def fig_panel_confidence(caption, tokens=None, letters=None):
    """How much the caption tells you about the panel count.

    Returns (confidence, note). Never treat a single detected token as proof of a
    single panel: captions routinely mention one variable in prose while the figure
    plots eight. A caption that names no panel key at all says nothing about the
    panel count, and a caption harvested from body text rather than the figure
    legend says less still.

      CAPTION_ENUMERATES  - two or more panel keys found; split per key
      SINGLE_KEY_ONLY     - exactly one key; the figure MAY still be multi-panel
      NO_KEY              - no key; panel structure unknown
    """
    if tokens is None:
        tokens = fig_detect_parameter_panels(fig_strip_group_labels(caption))
    if letters is None:
        letters = [x for x in fig_detect_panels(caption) if x]
    n = max(len(tokens), len(letters))
    if n >= 2:
        return "CAPTION_ENUMERATES", "panel keys in caption: %s" % (tokens or letters)
    if n == 1:
        return ("SINGLE_KEY_ONLY",
                "only %s named in caption - the figure may carry further panels; "
                "confirm the panel count visually before treating this as one panel"
                % (tokens or letters))
    return ("NO_KEY",
            "no panel key in caption - panel structure unknown, confirm visually")


def fig_screen_caption(caption, target_terms=None):
    """Classify a figure caption into a route before any digitization work.

    Returns (route, reason). Routes:
      NOT_DATA                     - schematic / representative tracing / protocol
      ASSOCIATION_ONLY_NOT_TARGET  - correlation or regression plot; needs the
                                     association schema, NOT the mean template
      NO_TARGET_OUTCOME            - a data figure whose outcome is off-target
      DIGITIZE                     - candidate for mean/dispersion extraction

    The caption is de-hyphenated first (see fig_normalize_caption): a PDF that
    prints "rela- tionships between" would otherwise slip past the association
    screen and be routed to the mean-difference template.
    """
    import re
    cap = fig_normalize_caption(caption)
    if any(re.search(p, cap, re.I) for p in FIG_NOTDATA_PATTERNS):
        return "NOT_DATA", "schematic/representative wording in caption"
    if any(re.search(p, cap, re.I) for p in FIG_BINARY_PATTERNS):
        return "BINARY_EVENT_NOT_MEAN", "event/incidence wording - needs the binary-event schema"
    if any(re.search(p, cap, re.I) for p in FIG_ASSOCIATION_PATTERNS):
        return "ASSOCIATION_ONLY_NOT_TARGET", "correlation/regression wording in caption"
    if target_terms:
        outcome_cap = fig_strip_group_labels(cap)
        if any(re.search(t, outcome_cap, re.I) for t in target_terms):
            return "DIGITIZE", "candidate for mean/dispersion extraction"
        params = fig_detect_parameter_panels(outcome_cap)
        target_params = [p for p in params
                         if any(re.search(t, fig_parameter_panel_tokens()[p], re.I) for t in target_terms)
                         and fig_token_denotes_outcome(p, outcome_cap)]
        if target_params:
            return ("PARTIAL_PANEL_TARGET",
                    "no target term in prose, but panel token(s) %s denote target outcomes - "
                    "split per panel and digitize only those" % ",".join(target_params))
        return "NO_TARGET_OUTCOME", "no target-outcome term in caption or panel labels"
    return "DIGITIZE", "candidate for mean/dispersion extraction"


def fig_classify_shape(df, timepoints_col="Timepoints", challenge_col="Challenge_Test",
                       serial_token="SERIAL"):
    """Add Data_Shape_Expected from coded timepoint structure and challenge presence.

    PUBLICATION-level triage only: it says which shapes to expect. The extraction
    unit is publication x figure x panel x outcome, one paper can carry several
    shapes, and correlation figures (E) are not predictable from study metadata -
    they must be caught per figure by fig_screen_caption.
    """
    out = df.copy()

    def one(row):
        tp = "" if fig_is_blank(row.get(timepoints_col)) else str(row.get(timepoints_col)).upper()
        serial = serial_token in tp
        # Was a literal tuple comparison, which knew "NA" but not "N/A", "-" or
        # the Korean nulls - each of those read as a challenge and pushed a
        # D_SIMPLE_PREPOST study into B_CHALLENGE_2POINT.
        chal = not fig_is_blank(row.get(challenge_col))
        if chal and serial:
            return FIG_SHAPES[0]
        if chal:
            return FIG_SHAPES[1]
        if serial:
            return FIG_SHAPES[2]
        return FIG_SHAPES[3]

    out["Data_Shape_Expected"] = out.apply(one, axis=1)
    return out


def fig_extraction_spec():
    """One instruction row per data shape: axes, series, WPD mode, pitfall."""
    rows = [
        dict(Data_Shape=FIG_SHAPES[0],
             X_Axis="time (min) or load step (-20/-40 mmHg, 0/30/60 deg)",
             Y_Axis="outcome in native units",
             Series="baseline series + exposure series (x arm if arms exist)",
             Values_Needed="mean + error bar at PRE-SPECIFIED x points only (baseline, peak load, end)",
             Required_Extra="Exposure_Phase and Timepoint_Days on every row",
             WPD_Mode="2D (X-Y) Plot; calibrate 2 x-points and 2 y-points; one Dataset per series",
             Pitfall="Log or non-linear x axis needs the WPD Log option. Overlapping series must be split by marker/colour into separate Datasets."),
        dict(Data_Shape=FIG_SHAPES[1],
             X_Axis="posture/condition category (rest -> tilt/LBNP/AG level)",
             Y_Axis="outcome in native units",
             Series="two exposure phases (PRE vs DURING, POST or RECOVERY), or per arm",
             Values_Needed="mean + error bar for EVERY condition x phase cell (>= 4 values)",
             Required_Extra="Posture_Condition AND Exposure_Phase mandatory; the same condition set must appear in BOTH phases. Acute studies pair PRE with DURING, not POST.",
             WPD_Mode="2D Bar Plot (preferred for bars) or 2D (X-Y)",
             Pitfall="Do NOT collapse the grid. Posture is a within-arm condition, NOT a separate arm: record rest-pre, challenge-pre, rest-post, challenge-post as four rows of the SAME arm. A two-column read relabels a condition contrast as a time contrast and drops half the data."),
        dict(Data_Shape=FIG_SHAPES[2],
             X_Axis="study day (FD3, FD30, R+0, R+7 ...)",
             Y_Axis="outcome in native units",
             Series="single series, or one per arm",
             Values_Needed="mean + error bar per measurement day; keep the source's own day label verbatim",
             Required_Extra="Exposure_Phase must distinguish DURING from POST - in-flight / in-bedrest days are DURING",
             WPD_Mode="2D (X-Y) Plot; calibrate each tick separately if spacing is uneven",
             Pitfall="A label like FD15 or HDT30 is DURING exposure, not recovery. Check whether the pre-exposure (L-) value is the baseline or a separate timepoint, and whether R+0 equals landing day."),
        dict(Data_Shape=FIG_SHAPES[3],
             X_Axis="pre / post (2 categories)",
             Y_Axis="outcome in native units",
             Series="single series, or one per arm",
             Values_Needed="pre mean + error, post mean + error; individual subject points too if plotted (confirms n)",
             Required_Extra="If only the change score is plotted, set Exposure_Phase=DELTA and leave the levels blank",
             WPD_Mode="2D Bar Plot; for paired-point plots read each point and compute mean/SD directly",
             Pitfall="A delta-only figure cannot yield pre and post levels - record the delta and its error and handle it as a mean difference, do not invent levels."),
        dict(Data_Shape=FIG_SHAPES[4],
             X_Axis="predictor variable (not a study phase)",
             Y_Axis="outcome variable",
             Series="one point per subject - NOT a group mean",
             Values_Needed="the reported association statistic (r, rho, beta) with CI, p and the number of PAIRS",
             Required_Extra="Use fig_association_columns(); never the mean-difference template",
             WPD_Mode="Only if the statistic is unreported: digitize the point cloud and recompute. Otherwise transcribe the reported statistic.",
             Pitfall="Reading a scatter/regression plot as a group mean fabricates a mean difference out of an association. Decide up front whether associations enter the synthesis at all; if not, mark them ASSOCIATION_ONLY_NOT_TARGET and stop."),
        dict(Data_Shape=FIG_SHAPES[5],
             X_Axis="group or phase (categorical) - often a pie/bar of incidence",
             Y_Axis="count or percentage of subjects with the event",
             Series="one series per group being compared",
             Values_Needed="Events and N_at_Risk per group (read percentages back to counts and state the denominator)",
             Required_Extra="use fig_binary_event_columns(), NOT the mean/dispersion template; Effect_Measure=RR or OR",
             WPD_Mode="Bar / Pie mode, or read the printed n/% directly when legible",
             Pitfall="An event count is not a mean. Putting incidence into the mean template invents a mean difference from a proportion; a percentage without its denominator cannot be turned back into events, so record N_at_Risk from the text even when the figure omits it."),
        dict(Data_Shape=FIG_SHAPES[6],
             X_Axis="one condition factor (workload, gravity level, LBNP step)",
             Y_Axis="outcome in native units",
             Series="the other condition factor - every cell is an exposure condition",
             Values_Needed="mean + error bar for every factor-1 x factor-2 cell",
             Required_Extra="Posture_Condition for one factor and Timepoint_Label for the other; Exposure_Phase=DURING on all rows (there is no pre-exposure baseline)",
             WPD_Mode="2D (X-Y) Plot or grouped bars; one Dataset per level of the series factor",
             Pitfall="This design has NO pre/post contrast - every point is measured under exposure. Forcing it into B (which demands PRE plus a follow-up) or A (which demands a baseline series) rejects correct data. The extractable effect is a cross-condition contrast, not an exposure effect: record it and let the synthesis decide whether such contrasts enter the pool."),
    ]
    return pd.DataFrame(rows)


def fig_validate_association(df, flag, problems, require_dual=False):
    """Value checks for the E_SCATTER_ASSOCIATION schema.

    The mean/dispersion validator cannot see these files at all - they have no
    Mean or Dispersion_Type column - so without this branch an association file
    only ever returns SCHEMA_INCOMPLETE and every value passes unchecked.
    """
    import pandas as pd
    required = ["Publication_ID", "Source_File", "Source_Page", "Figure_Number",
                "Outcome_Variable", "Predictor_Variable", "Association_Type",
                "Association_Value", "N_Pairs", "Extraction_Method",
                "Extractor_1", "Source_Caption_Verbatim"]
    digitized_only = ["Source_Image", "WPD_Project_File", "Image_Resolution_Or_Hash",
                      "Axis_X_Scale", "Axis_Y_Scale",
                      "Axis_Calib_X1_Value", "Axis_Calib_X2_Value",
                      "Axis_Calib_Y1_Value", "Axis_Calib_Y2_Value"]
    missing = [c for c in required + digitized_only if c not in df.columns]
    if missing:
        flag("-", "SCHEMA_INCOMPLETE",
             "association schema missing columns: " + ", ".join(missing))
        return pd.DataFrame(problems)
    for i, r in df.iterrows():
        line = i + 2
        for c in required:
            if fig_is_blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", "%s blank" % c)
        method = str(r.get("Extraction_Method", "")).strip().upper()
        if method and method not in FIG_EXTRACTION_METHODS:
            flag(line, "BAD_EXTRACTION_METHOD",
                 "Extraction_Method=%s (expected %s)" % (method, "/".join(FIG_EXTRACTION_METHODS)))
        if method == "DIGITIZED":
            for c in digitized_only:
                if fig_is_blank(r.get(c)):
                    flag(line, "MISSING_PROVENANCE",
                         "%s blank - a digitized value needs its image, project file and "
                         "axis calibration to be reproducible" % c)
            for ax in ("X", "Y"):
                sc = str(r.get("Axis_%s_Scale" % ax, "")).strip().upper()
                if sc and sc not in ("LINEAR", "LOG"):
                    flag(line, "BAD_AXIS_SCALE", "Axis_%s_Scale=%s" % (ax, sc))
                v1 = fig_as_number(r.get("Axis_Calib_%s1_Value" % ax))
                v2 = fig_as_number(r.get("Axis_Calib_%s2_Value" % ax))
                if v1 is not None and v2 is not None and v1 == v2:
                    flag(line, "%s_CALIB_DEGENERATE" % ax, "both calibration values equal")
                if sc == "LOG":
                    for lbl, v in (("%s1" % ax, v1), ("%s2" % ax, v2)):
                        if v is not None and v <= 0:
                            flag(line, "LOG_AXIS_NONPOSITIVE",
                                 "Axis_Calib_%s_Value=%s on a LOG axis" % (lbl, v))
        fig_check_numeric(r, ["Association_Value", "N_Pairs", "CI_Lower", "CI_Upper",
                              "P_Value", "Association_Value_R1", "Association_Value_R2",
                              "Axis_Calib_X1_Value", "Axis_Calib_X2_Value",
                              "Axis_Calib_Y1_Value", "Axis_Calib_Y2_Value"], flag, line)
        canon, raw = fig_normalize_association_type(r.get("Association_Type"))
        if raw and canon is None:
            flag(line, "BAD_ASSOCIATION_TYPE",
                 "Association_Type=%s is not in the controlled vocabulary %s - an "
                 "unrecognised label skips the range check entirely"
                 % (raw, sorted(set(FIG_ASSOCIATION_TYPES.values()))))
        val = fig_as_number(r.get("Association_Value"))
        if val is not None and canon in FIG_BOUNDED_ASSOCIATIONS and not (-1.0 - 1e-9 <= val <= 1.0 + 1e-9):
            flag(line, "ASSOCIATION_VALUE_OUT_OF_RANGE",
                 "Association_Type=%s (canonical %s) with value %s - a correlation "
                 "coefficient lies in [-1, 1]" % (raw, canon, val))
        if val is not None and canon == "R_SQUARED" and not (0.0 - 1e-9 <= val <= 1.0 + 1e-9):
            flag(line, "ASSOCIATION_VALUE_OUT_OF_RANGE",
                 "R_SQUARED=%s must lie in [0, 1]" % val)
        n = fig_as_number(r.get("N_Pairs"))
        if n is not None:
            if n < 3:
                flag(line, "N_PAIRS_TOO_SMALL",
                     "N_Pairs=%s - a correlation needs at least 3 pairs to be defined" % n)
            elif abs(n - round(n)) > 1e-9:
                flag(line, "N_INVALID", "N_Pairs=%s - must be a whole number" % n)
        lo = fig_as_number(r.get("CI_Lower"))
        hi = fig_as_number(r.get("CI_Upper"))
        if fig_is_blank(r.get("CI_Lower")) != fig_is_blank(r.get("CI_Upper")):
            flag(line, "CI_HALF_FILLED",
                 "CI_Lower=%r CI_Upper=%r - an interval needs both bounds or neither"
                 % (r.get("CI_Lower"), r.get("CI_Upper")))
        if lo is not None and hi is not None:
            if lo > hi:
                flag(line, "CI_BOUNDS_INVERTED", "CI_Lower=%s > CI_Upper=%s" % (lo, hi))
            elif val is not None and not (lo - 1e-9 <= val <= hi + 1e-9):
                flag(line, "ESTIMATE_OUTSIDE_CI",
                     "Association_Value=%s lies outside [%s, %s]" % (val, lo, hi))
            bounds = None
            if canon in FIG_BOUNDED_ASSOCIATIONS:
                bounds = (-1.0, 1.0)
            elif canon == "R_SQUARED":
                bounds = (0.0, 1.0)
            if bounds is not None:
                out = [("CI_Lower", lo), ("CI_Upper", hi)]
                bad = [(nm, v) for nm, v in out
                       if not (bounds[0] - 1e-9 <= v <= bounds[1] + 1e-9)]
                if bad:
                    flag(line, "ASSOCIATION_CI_OUT_OF_RANGE",
                         "%s with %s - the interval of a %s cannot leave [%s, %s]"
                         % (canon,
                            ", ".join("%s=%s" % (nm, v) for nm, v in bad),
                            canon, bounds[0], bounds[1]))
        p = fig_as_number(r.get("P_Value"))
        if p is not None and not (0.0 <= p <= 1.0):
            flag(line, "P_VALUE_OUT_OF_RANGE", "P_Value=%s" % p)
        v1 = fig_as_number(r.get("Association_Value_R1"))
        v2 = fig_as_number(r.get("Association_Value_R2"))
        st = str(r.get("Independent_Verification_Status", "")).strip().upper()
        if st and st not in FIG_DUAL_OK:
            flag(line, "BAD_VERIFICATION_STATUS",
                 "Independent_Verification_Status=%s (expected %s)"
                 % (st, "/".join(FIG_DUAL_OK)))
        if v1 is not None and v2 is not None:
            d = abs(v1 - v2)
            if d > 0.05 and st != "RECONCILED":
                flag(line, "DUAL_READINGS_DISAGREE",
                     "R1=%s R2=%s differ by %.3f (> 0.05) and status is %s - set "
                     "RECONCILED with a Discrepancy_Note once adjudicated; do NOT "
                     "overwrite the original readings"
                     % (v1, v2, d, st or "blank"))
            if d > 0.05 and st == "RECONCILED" and fig_is_blank(r.get("Discrepancy_Note")):
                flag(line, "RECONCILED_WITHOUT_NOTE",
                     "status RECONCILED but Discrepancy_Note is blank - record how the "
                     "disagreement was resolved")
            if val is not None and st != "RECONCILED" and not (
                    min(v1, v2) - 1e-9 <= val <= max(v1, v2) + 1e-9):
                flag(line, "CONSENSUS_OUTSIDE_READINGS",
                     "Association_Value=%s lies outside [%s, %s]" % (val, min(v1, v2), max(v1, v2)))
        if require_dual:
            if fig_is_blank(r.get("Extractor_2")):
                flag(line, "NO_SECOND_EXTRACTOR", "Extractor_2 blank")
            if v1 is None or v2 is None:
                flag(line, "NO_INDEPENDENT_READINGS",
                     "Association_Value_R1=%r R2=%r - the coefficient must be read twice"
                     % (r.get("Association_Value_R1"), r.get("Association_Value_R2")))
    return pd.DataFrame(problems)


def fig_validate_binary(df, flag, problems, require_dual=False):
    """Value checks for the F_BINARY_EVENT schema.

    Same reason as the association branch: a counts file has no Mean column, so
    it never reaches the shape-specific rules. An event count above its
    denominator, or a zero denominator, must not pass silently into an RR.
    """
    import pandas as pd
    required = ["Publication_ID", "Source_File", "Source_Page", "Figure_Number",
                "Outcome_Variable", "Event_Definition", "Arm", "Exposure_Phase",
                "Events", "N_at_Risk", "Effect_Measure", "Extraction_Method",
                "Extractor_1", "Source_Caption_Verbatim"]
    digitized_only = ["Source_Image", "WPD_Project_File", "Image_Resolution_Or_Hash"]
    CELLS = (("Events", "Events_R1", "Events_R2"),
             ("N_at_Risk", "N_at_Risk_R1", "N_at_Risk_R2"),
             ("Events_Comparator", "Events_Comparator_R1", "Events_Comparator_R2"),
             ("N_at_Risk_Comparator", "N_at_Risk_Comparator_R1", "N_at_Risk_Comparator_R2"))
    missing = [c for c in required + digitized_only if c not in df.columns]
    if missing:
        flag("-", "SCHEMA_INCOMPLETE",
             "binary-event schema missing columns: " + ", ".join(missing))
        return pd.DataFrame(problems)
    for i, r in df.iterrows():
        line = i + 2
        for c in required:
            if fig_is_blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", "%s blank" % c)
        method = str(r.get("Extraction_Method", "")).strip().upper()
        if method and method not in FIG_EXTRACTION_METHODS:
            flag(line, "BAD_EXTRACTION_METHOD",
                 "Extraction_Method=%s (expected %s)" % (method, "/".join(FIG_EXTRACTION_METHODS)))
        if method == "DIGITIZED":
            for c in digitized_only:
                if fig_is_blank(r.get(c)):
                    flag(line, "MISSING_PROVENANCE",
                         "%s blank - a digitized count needs its image and project file" % c)
        numeric_cols = [c for grp in CELLS for c in grp] + ["P_Value_Reported"]
        fig_check_numeric(r, numeric_cols, flag, line)
        for ev_c, n_c, label in (("Events", "N_at_Risk", "index"),
                                 ("Events_Comparator", "N_at_Risk_Comparator", "comparator")):
            ev = fig_as_number(r.get(ev_c))
            n = fig_as_number(r.get(n_c))
            if n is not None:
                if n <= 0:
                    flag(line, "N_AT_RISK_INVALID",
                         "%s=%s - the %s denominator must be > 0; read it from the text "
                         "when the figure gives only a percentage" % (n_c, n, label))
                elif abs(n - round(n)) > 1e-9:
                    flag(line, "N_INVALID", "%s=%s - must be a whole number" % (n_c, n))
            if ev is not None:
                if ev < 0:
                    flag(line, "EVENTS_INVALID", "%s=%s - cannot be negative" % (ev_c, ev))
                elif abs(ev - round(ev)) > 1e-9:
                    flag(line, "EVENTS_INVALID",
                         "%s=%s - must be a whole count, not a percentage" % (ev_c, ev))
                elif n is not None and n > 0 and ev > n:
                    flag(line, "EVENTS_EXCEED_N",
                         "%s=%s exceeds %s=%s - a percentage was probably stored as a count"
                         % (ev_c, ev, n_c, n))
        em = str(r.get("Effect_Measure", "")).strip().upper()
        if em and em not in ("RR", "OR", "RD", "HR"):
            flag(line, "BAD_EFFECT_MEASURE",
                 "Effect_Measure=%s (expected RR/OR/RD/HR)" % em)
        comp_blank = [fig_is_blank(r.get(c)) for c in
                      ("Arm_Comparator", "Events_Comparator", "N_at_Risk_Comparator")]
        if any(comp_blank) and not all(comp_blank):
            flag(line, "COMPARATOR_HALF_FILLED",
                 "comparator cells partly filled - a 2x2 needs arm, events and "
                 "denominator together")
        elif all(comp_blank) and em in ("RR", "OR", "HR"):
            flag(line, "COMPARATOR_MISSING_FOR_RATIO",
                 "Effect_Measure=%s needs a comparator arm; a single-arm proportion "
                 "cannot yield a ratio" % em)
        p = fig_as_number(r.get("P_Value_Reported"))
        if p is not None and not (0.0 <= p <= 1.0):
            flag(line, "P_VALUE_OUT_OF_RANGE", "P_Value_Reported=%s" % p)
        has_comp = not all(comp_blank)
        st = str(r.get("Independent_Verification_Status", "")).strip().upper()
        if st and st not in FIG_DUAL_OK:
            flag(line, "BAD_VERIFICATION_STATUS",
                 "Independent_Verification_Status=%s (expected %s)"
                 % (st, "/".join(FIG_DUAL_OK)))
        disagreed = False
        for cons_c, r1_c, r2_c in CELLS:
            if cons_c.endswith("_Comparator") and not has_comp:
                continue
            cons = fig_as_number(r.get(cons_c))
            a = fig_as_number(r.get(r1_c))
            b = fig_as_number(r.get(r2_c))
            if a is not None and b is not None:
                if a != b:
                    disagreed = True
                    if st != "RECONCILED":
                        flag(line, "DUAL_READINGS_DISAGREE",
                             "%s=%s %s=%s - counts must agree exactly; set RECONCILED "
                             "with a Discrepancy_Note once adjudicated, keeping both "
                             "original readings" % (r1_c, a, r2_c, b))
                elif cons is not None and cons != a:
                    flag(line, "CONSENSUS_OUTSIDE_READINGS",
                         "%s=%s but both readers recorded %s" % (cons_c, cons, a))
            if require_dual and (a is None or b is None):
                flag(line, "NO_INDEPENDENT_READINGS",
                     "%s=%r %s=%r - every cell of the 2x2 must be read twice"
                     % (r1_c, r.get(r1_c), r2_c, r.get(r2_c)))
        if disagreed and st == "RECONCILED" and fig_is_blank(r.get("Discrepancy_Note")):
            flag(line, "RECONCILED_WITHOUT_NOTE",
                 "status RECONCILED but Discrepancy_Note is blank - record how the "
                 "count disagreement was resolved")
        if require_dual and fig_is_blank(r.get("Extractor_2")):
            flag(line, "NO_SECOND_EXTRACTOR", "Extractor_2 blank")
    return pd.DataFrame(problems)


def fig_validate_extraction(df, ranges=None, se_sd_ratio=1.5, require_dual=False,
                            require_provenance=True, dual_tolerance_pct=5.0):
    """QC a filled extraction template with shape-specific rules.

    Returns a DataFrame of problems; empty means ready for effect conversion.
    require_dual=True demands two independent readings that actually agree
    (numeric comparison within dual_tolerance_pct), not a status label.
    """
    if ranges is None:
        ranges = fig_default_ranges()
    base_required = ["Publication_ID", "Source_File", "Source_Page", "Figure_Number",
                     "Data_Shape", "Outcome_Variable", "Unit", "Arm", "Exposure_Phase",
                     "Mean", "Dispersion_Type", "N_Outcome", "Extraction_Method",
                     "Axis_X_Scale", "Axis_Y_Scale",
                     "Axis_Calib_X1_Value", "Axis_Calib_X2_Value",
                     "Axis_Calib_Y1_Value", "Axis_Calib_Y2_Value"]
    provenance_required = ["Source_Image", "Source_Caption_Verbatim", "WPD_Project_File",
                           "Image_Resolution_Or_Hash", "Extractor_1",
                           "Axis_Calib_X1_Pixel", "Axis_Calib_X2_Pixel",
                           "Axis_Calib_Y1_Pixel", "Axis_Calib_Y2_Pixel"]
    problems = []
    unranged = {}

    def flag(row, check, detail):
        problems.append(dict(row=row, check=check, detail=detail))

    missing_cols = [c for c in base_required if c not in df.columns]
    if missing_cols:
        assoc_cols = set(fig_association_columns())
        bin_cols = set(fig_binary_event_columns())
        cols = set(df.columns)
        if {"Association_Value", "N_Pairs"} <= cols:
            return fig_validate_association(df, flag, problems, require_dual=require_dual)
        if {"Events", "N_at_Risk"} <= cols:
            return fig_validate_binary(df, flag, problems, require_dual=require_dual)
        flag("-", "SCHEMA_INCOMPLETE", "missing columns: " + ", ".join(missing_cols))
        return pd.DataFrame(problems)

    for i, r in df.iterrows():
        line = i + 2
        shape = str(r["Data_Shape"]).strip().upper()
        phase = str(r["Exposure_Phase"]).strip().upper()
        for c in base_required:
            if fig_is_blank(r[c]):
                flag(line, "MISSING_REQUIRED", c)
        if require_provenance:
            for c in provenance_required:
                if c not in df.columns or fig_is_blank(r.get(c)):
                    flag(line, "MISSING_PROVENANCE", c)
        if shape not in FIG_SHAPES:
            flag(line, "BAD_DATA_SHAPE", shape)
        if shape in (FIG_SHAPES[4], FIG_SHAPES[5]):
            flag(line, "WRONG_SCHEMA_FOR_SHAPE",
                 "%s rows belong in %s, not the mean/dispersion template"
                 % (shape, "fig_association_columns()" if shape == FIG_SHAPES[4]
                    else "fig_binary_event_columns()"))
        if phase not in FIG_PHASES:
            flag(line, "BAD_EXPOSURE_PHASE", "%s (expected one of %s)" % (phase, "/".join(FIG_PHASES)))
        if shape == FIG_SHAPES[1] and fig_is_blank(r.get("Posture_Condition")):
            flag(line, "MISSING_POSTURE_FOR_B", "B shape needs Posture_Condition")
        if shape == FIG_SHAPES[0] and fig_is_blank(r.get("Timepoint_Days")) and fig_is_blank(r.get("Timepoint_Label")):
            flag(line, "MISSING_TIMEPOINT_FOR_A", "A shape needs Timepoint_Label or Timepoint_Days")

        # ---- geometry of the read, and panel reconciliation ------------------
        # These apply to a DIGITIZED row only: a TRANSCRIBED number was copied
        # from printed text and has no bar geometry to define.
        method = str(r.get("Extraction_Method", "")).strip().upper()
        if method and method not in FIG_EXTRACTION_METHODS:
            flag(line, "BAD_EXTRACTION_METHOD",
                 "Extraction_Method=%s (expected %s)" % (method, "/".join(FIG_EXTRACTION_METHODS)))
        dtyp = str(r["Dispersion_Type"]).strip().upper()
        if method == "DIGITIZED":
            btd = str(r.get("Bar_Top_Definition", "")).strip().upper()
            if fig_is_blank(r.get("Bar_Top_Definition")):
                flag(line, "MISSING_BAR_TOP_DEFINITION",
                     "state where the value was read on the mark "
                     "(%s); NOT_A_BAR for a line or point plot" % "/".join(FIG_BAR_TOP_DEFS))
            elif btd not in FIG_BAR_TOP_DEFS:
                flag(line, "BAD_BAR_TOP_DEFINITION",
                     "Bar_Top_Definition=%s (expected %s)" % (btd, "/".join(FIG_BAR_TOP_DEFS)))
            elif btd == "FILL_EDGE":
                flag(line, "BAR_TOP_READ_AT_FILL_EDGE",
                     "the colour fill stops inside the stroke, so every mean is biased low "
                     "by half the outline width - re-read at OUTLINE_CENTER")
            stem = fig_as_bool(r.get("Errorbar_Stem_Confirmed"))
            has_disp = (fig_as_number(r.get("Dispersion_Value")) is not None
                        or fig_as_number(r.get("Errorbar_Lower")) is not None
                        or fig_as_number(r.get("Errorbar_Upper")) is not None)
            if stem == "BAD":
                flag(line, "BAD_ERRORBAR_STEM_FLAG",
                     "Errorbar_Stem_Confirmed=%r (expected TRUE/FALSE)"
                     % r.get("Errorbar_Stem_Confirmed"))
            elif has_disp and dtyp != "NO_ERRORBAR" and stem is not True:
                flag(line, "ERRORBAR_STEM_UNCONFIRMED",
                     "a dispersion was recorded but the whisker was not confirmed to connect "
                     "to the mark - significance glyphs and brackets sit in the same place")

        prs = str(r.get("Panel_Reconciliation_Status", "")).strip().upper()
        obs = fig_as_number(r.get("Observed_Panel_Count"))
        wl = fig_as_number(r.get("Worklist_Panel_Count"))
        if fig_is_blank(r.get("Panel_Reconciliation_Status")) or prs == "PENDING":
            flag(line, "PANEL_RECONCILIATION_PENDING",
                 "count the panels on screen and reconcile against the worklist - "
                 "caption-derived panel lists can only miss panels, never invent them")
        elif prs not in FIG_PANEL_RECON:
            flag(line, "BAD_PANEL_RECONCILIATION_STATUS",
                 "Panel_Reconciliation_Status=%s (expected %s)" % (prs, "/".join(FIG_PANEL_RECON)))
        else:
            if obs is None or wl is None:
                flag(line, "MISSING_PANEL_COUNT",
                     "Observed_Panel_Count and Worklist_Panel_Count are both required "
                     "once reconciliation is claimed")
            else:
                bad = [(n, v) for n, v in (("Observed_Panel_Count", obs),
                                           ("Worklist_Panel_Count", wl))
                       if v <= 0 or v != int(v)]
                for n, v in bad:
                    flag(line, "PANEL_COUNT_INVALID",
                         "%s=%g - a panel count is a positive integer" % (n, v))
                if not bad:
                    # The status is fully determined by the two counts; anything
                    # else is a contradiction, not a judgement call.
                    want = ("MATCHED" if obs == wl else
                            "UNLISTED_PANELS_FOUND" if obs > wl else "WORKLIST_OVERCOUNTS")
                    if prs != want:
                        flag(line, "PANEL_STATUS_CONTRADICTS_COUNTS",
                             "observed %d vs worklist %d implies %s, not %s"
                             % (obs, wl, want, prs))
                    if obs > wl and fig_is_blank(r.get("Unlisted_Panels")):
                        flag(line, "UNLISTED_PANELS_NOT_RECORDED",
                             "observed %d > worklist %d - name the panels the worklist omitted"
                             % (obs, wl))

        _canon, lohi = fig_lookup_range(r["Outcome_Variable"], ranges)
        if lohi is None and not fig_is_blank(r["Outcome_Variable"]) and not fig_is_blank(r["Mean"]):
            unranged.setdefault(str(r["Outcome_Variable"]).strip(), 0)
            unranged[str(r["Outcome_Variable"]).strip()] += 1
        m = fig_as_number(r["Mean"])
        if lohi is not None and not fig_is_blank(r["Mean"]):
            if m is None:
                flag(line, "NON_NUMERIC_MEAN", str(r["Mean"]))
            elif phase != "DELTA" and not (lohi[0] <= m <= lohi[1]):
                flag(line, "IMPLAUSIBLE_VALUE",
                     "%s=%s (expected %s-%s)" % (r["Outcome_Variable"], m, lohi[0], lohi[1]))

        dt = str(r["Dispersion_Type"]).strip().upper()
        if dt not in FIG_DISPERSION_TYPES:
            flag(line, "BAD_DISPERSION_TYPE", dt or "blank")
        sym = fig_as_number(r.get("Dispersion_Value"))
        lo = fig_as_number(r.get("Errorbar_Lower"))
        hi = fig_as_number(r.get("Errorbar_Upper"))
        if dt in ("SD", "SE", "SEM"):
            if sym is None and (lo is None or hi is None):
                flag(line, "MISSING_DISPERSION",
                     "%s needs Dispersion_Value or both error-bar bounds" % dt)
        elif dt in FIG_ASYMMETRIC_TYPES:
            if lo is None or hi is None:
                flag(line, "ASYMMETRIC_NEEDS_BOUNDS",
                     "%s requires Errorbar_Lower and Errorbar_Upper, not a single value" % dt)
        if fig_is_blank(r.get("Errorbar_Definition_Source")):
            flag(line, "NO_ERRORBAR_SOURCE", "record the caption wording that defines the bars")
        else:
            _tok = fig_unresolved_marker(r.get("Errorbar_Definition_Source"))
            if _tok:
                flag(line, "UNRESOLVED_ERRORBAR_DEFINITION",
                     "Errorbar_Definition_Source contains %r - Dispersion_Type=%s is then a "
                     "guess, and SD/SE confusion scales the weight by sqrt(n). Quote the "
                     "source, or record NO_ERRORBAR and leave the row out of the pooled "
                     "variance." % (_tok, dtyp or "blank"))
        if dt in ("SE", "SEM") and sym is not None and m is not None:
            n = fig_as_number(r.get("N_Outcome"))
            if n and n > 0:
                sd = sym * np.sqrt(n)
                if sd > abs(m) * se_sd_ratio:
                    flag(line, "SE_IMPLIES_HUGE_SD",
                         "SE=%s N=%s -> SD=%.1f vs mean %.1f" % (sym, n, sd, m))

        fig_check_numeric(r, ["Observed_Panel_Count", "Worklist_Panel_Count"], flag, line)
        fig_check_numeric(r, ["Mean", "Dispersion_Value", "N_Outcome",
                              "Errorbar_Lower", "Errorbar_Upper",
                              "Mean_R1", "Mean_R2", "Dispersion_R1", "Dispersion_R2",
                              "Timepoint_Days",
                              "Axis_Calib_X1_Value", "Axis_Calib_X2_Value",
                              "Axis_Calib_Y1_Value", "Axis_Calib_Y2_Value",
                              "Axis_Calib_X1_Pixel", "Axis_Calib_X2_Pixel",
                              "Axis_Calib_Y1_Pixel", "Axis_Calib_Y2_Pixel"], flag, line)
        if str(r.get("Dispersion_Type", "")).strip().upper() == "NO_ERRORBAR":
            flag(line, "NONCONVERTIBLE_NO_VARIANCE",
                 "Dispersion_Type=NO_ERRORBAR - this row carries no variance and cannot "
                 "enter a variance-weighted pool; report it descriptively")
        sym = fig_as_number(r.get("Dispersion_Value"))
        if sym is not None and sym <= 0:
            flag(line, "DISPERSION_NONPOSITIVE",
                 "Dispersion_Value=%s - an error bar of zero or less cannot be a "
                 "read value; leave blank if the figure shows none" % sym)
        n_raw = r.get("N_Outcome")
        n_val = fig_as_number(n_raw)
        if n_val is not None:
            if n_val < 1:
                flag(line, "N_INVALID", "N_Outcome=%s - must be >= 1" % n_raw)
            elif abs(n_val - round(n_val)) > 1e-9:
                flag(line, "N_INVALID", "N_Outcome=%s - must be a whole number of subjects" % n_raw)
            elif n_val == 1 and str(r.get("Dispersion_Type", "")).strip().upper() not in ("NO_ERRORBAR", ""):
                flag(line, "N_ONE_NO_DISPERSION",
                     "N_Outcome=1 with Dispersion_Type=%s - a single subject has no "
                     "sampling dispersion; use NO_ERRORBAR, or check whether this row "
                     "is really a group"
                     % str(r.get("Dispersion_Type", "")).strip().upper())
        lo = fig_as_number(r.get("Errorbar_Lower"))
        hi = fig_as_number(r.get("Errorbar_Upper"))
        if lo is not None and hi is not None:
            if lo > hi:
                flag(line, "ERRORBAR_BOUNDS_INVERTED",
                     "Errorbar_Lower=%s > Errorbar_Upper=%s" % (lo, hi))
            elif m is not None and not (lo - 1e-9 <= m <= hi + 1e-9):
                flag(line, "MEAN_OUTSIDE_ERRORBAR",
                     "Mean=%s lies outside [%s, %s]" % (m, lo, hi))
        for ax in ("X", "Y"):
            v1 = fig_as_number(r.get("Axis_Calib_%s1_Value" % ax))
            v2 = fig_as_number(r.get("Axis_Calib_%s2_Value" % ax))
            if v1 is not None and v2 is not None and v1 == v2:
                flag(line, "%s_CALIB_DEGENERATE" % ax, "both calibration values equal")
            p1 = fig_as_number(r.get("Axis_Calib_%s1_Pixel" % ax))
            p2 = fig_as_number(r.get("Axis_Calib_%s2_Pixel" % ax))
            if p1 is not None and p2 is not None and p1 == p2:
                flag(line, "%s_CALIB_PIXEL_DEGENERATE" % ax, "both calibration pixels equal")
            sc = str(r.get("Axis_%s_Scale" % ax, "")).strip().upper()
            if sc and sc not in ("LINEAR", "LOG"):
                flag(line, "BAD_AXIS_SCALE", "Axis_%s_Scale=%s" % (ax, sc))
            if sc == "LOG":
                for lbl, v in (("%s1" % ax, v1), ("%s2" % ax, v2)):
                    if v is not None and v <= 0:
                        flag(line, "LOG_AXIS_NONPOSITIVE",
                             "Axis_Calib_%s_Value=%s on a LOG axis - a log scale cannot "
                             "pass through zero or negative values; re-read the tick"
                             % (lbl, v))

        # Dual-reading comparison runs whenever two readings are PRESENT, so a
        # disagreement surfaces even when require_dual is off. require_dual only
        # adds the "a second reading must exist at all" requirements.
        m1 = fig_as_number(r.get("Mean_R1"))
        m2 = fig_as_number(r.get("Mean_R2"))
        d1 = fig_as_number(r.get("Dispersion_R1"))
        d2 = fig_as_number(r.get("Dispersion_R2"))
        st = str(r.get("Independent_Verification_Status", "")).strip().upper()
        if m1 is not None and m2 is not None:
            denom = max(abs(m1), abs(m2), 1e-9)
            diff_pct = abs(m1 - m2) / denom * 100.0
            if diff_pct > dual_tolerance_pct and st != "RECONCILED":
                flag(line, "DUAL_READINGS_DISAGREE",
                     "R1=%s R2=%s differ %.1f%% (> %.1f%%) and status is %s"
                     % (m1, m2, diff_pct, dual_tolerance_pct, st or "blank"))
            if m is not None and not (min(m1, m2) - 1e-9 <= m <= max(m1, m2) + 1e-9):
                flag(line, "CONSENSUS_OUTSIDE_READINGS",
                     "Mean=%s lies outside [%s, %s]" % (m, min(m1, m2), max(m1, m2)))
        if d1 is not None and d2 is not None:
            dd = abs(d1 - d2) / max(abs(d1), abs(d2), 1e-9) * 100.0
            if dd > dual_tolerance_pct and st != "RECONCILED":
                flag(line, "DUAL_DISPERSION_DISAGREE",
                     "R1=%s R2=%s differ %.1f%% (> %.1f%%)" % (d1, d2, dd, dual_tolerance_pct))
            if sym is not None and not (min(d1, d2) - 1e-9 <= sym <= max(d1, d2) + 1e-9):
                flag(line, "CONSENSUS_DISPERSION_OUTSIDE_READINGS",
                     "Dispersion_Value=%s lies outside [%s, %s]" % (sym, min(d1, d2), max(d1, d2)))
        if require_dual:
            if fig_is_blank(r.get("Extractor_2")):
                flag(line, "NO_SECOND_EXTRACTOR", "Extractor_2 blank")
            if m1 is None or m2 is None:
                flag(line, "NO_INDEPENDENT_READINGS",
                     "Mean_R1=%s Mean_R2=%s - a status label is not evidence of dual extraction"
                     % (r.get("Mean_R1"), r.get("Mean_R2")))
            if d1 is None or d2 is None:
                if str(r.get("Dispersion_Type", "")).strip().upper() != "NO_ERRORBAR":
                    flag(line, "NO_INDEPENDENT_DISPERSION",
                         "Dispersion_R1=%s Dispersion_R2=%s - the error bar must be read twice too"
                         % (r.get("Dispersion_R1"), r.get("Dispersion_R2")))
            if st not in FIG_DUAL_OK:
                flag(line, "NO_DUAL_EXTRACTION",
                     "Independent_Verification_Status=%s (expected %s)"
                     % (st or "blank", "/".join(FIG_DUAL_OK)))

    # Panel counts describe the FIGURE, so they cannot differ between its rows.
    # Two rows of one figure claiming 6/5 and 5/5 means somebody counted twice and
    # got different answers - and the per-row rules cannot see it.
    if {"Publication_ID", "Figure_Number"} <= set(df.columns):
        for key, gg in df.groupby(["Publication_ID", "Figure_Number"], dropna=False):
            pairs = set()
            for _, rr in gg.iterrows():
                o = fig_as_number(rr.get("Observed_Panel_Count"))
                wv = fig_as_number(rr.get("Worklist_Panel_Count"))
                if o is not None or wv is not None:
                    pairs.add((o, wv))
            if len(pairs) > 1:
                flag("-", "PANEL_COUNT_INCONSISTENT_IN_FIGURE",
                     "%s: rows disagree on the panel counts %s"
                     % (" | ".join(str(x) for x in key), sorted(pairs, key=str)))
            # Matching counts are not agreement: "6 of 5, the extra one is PAP"
            # and "6 of 5, the extra one is MAP" name different figures.
            if "Unlisted_Panels" in gg.columns:
                named = set(fig_panel_name_set(v) for v in gg["Unlisted_Panels"])
                named.discard(frozenset())
                if len(named) > 1:
                    flag("-", "UNLISTED_PANELS_INCONSISTENT_IN_FIGURE",
                         "%s: rows name different missing panels %s"
                         % (" | ".join(str(x) for x in key),
                            sorted(sorted(x) for x in named)))

    # One line per unmapped outcome name, not per row: a vocabulary gap is a
    # property of the name, and per-row noise would make the empty-table gate
    # unreachable. Silence here was the real defect - a mean of 999 bpm under the
    # label "HR" produced no flag of any kind.
    for _name, _n in sorted(unranged.items()):
        flag("-", "PLAUSIBILITY_RANGE_NOT_APPLIED",
             "no plausibility range for Outcome_Variable=%r (%d row%s); add it to "
             "`ranges` or map it in FIG_OUTCOME_ALIASES - these means were NOT range-checked"
             % (_name, _n, "" if _n == 1 else "s"))
    unit_keys = [c for c in ["Publication_ID", "Figure_Number", "Panel", "Outcome_Variable", "Arm"]
                 if c in df.columns]
    for key, g in df.groupby(unit_keys, dropna=False):
        tag = " | ".join(str(x) for x in (key if isinstance(key, tuple) else (key,)))
        shapes = set(str(x).strip().upper() for x in g["Data_Shape"])
        if len(shapes) != 1:
            flag("-", "MIXED_SHAPE_IN_UNIT", "%s: %s" % (tag, sorted(shapes)))
            continue
        shape = next(iter(shapes))
        units = set(str(x).strip() for x in g.get("Unit", pd.Series(dtype=object)) if str(x).strip())
        if len(units) > 1:
            flag("-", "MIXED_UNIT_IN_UNIT",
                 "%s: %s - one outcome cannot carry two units; convert before pooling "
                 "or split the rows" % (tag, sorted(units)))
        dtypes = set(str(x).strip().upper() for x in g.get("Dispersion_Type", pd.Series(dtype=object))
                     if str(x).strip())
        if len(dtypes) > 1:
            flag("-", "MIXED_DISPERSION_TYPE_IN_UNIT",
                 "%s: %s - SD and SE in the same figure means one of them was assumed; "
                 "read the legend and record what it says" % (tag, sorted(dtypes)))
        ph_series = g["Exposure_Phase"].astype(str).str.strip().str.upper()
        phases = set(ph_series)

        if shape == FIG_SHAPES[1]:
            follow = [p for p in FIG_FOLLOWUP_PHASES if p in phases]
            if "PRE" not in phases or not follow:
                flag("-", "B_PHASE_MISSING",
                     "%s: needs PRE plus one of %s, found %s"
                     % (tag, "/".join(FIG_FOLLOWUP_PHASES), sorted(phases)))
            else:
                pre_set = set(g.loc[ph_series == "PRE", "Posture_Condition"].astype(str).str.strip().str.upper())
                for fp in follow:
                    fol_set = set(g.loc[ph_series == fp, "Posture_Condition"].astype(str).str.strip().str.upper())
                    if pre_set != fol_set:
                        flag("-", "B_POSTURE_SET_ASYMMETRIC",
                             "%s: PRE=%s %s=%s" % (tag, sorted(pre_set), fp, sorted(fol_set)))
                if len(pre_set) < 2:
                    flag("-", "B_GRID_COLLAPSED",
                         "%s: only condition %s - a challenge study should carry rest and challenge"
                         % (tag, sorted(pre_set)))
            if "Posture_Condition" in g.columns:
                dup = g.groupby([ph_series, g["Posture_Condition"].astype(str).str.upper()]).size()
                for k2, n2 in dup.items():
                    if n2 > 1:
                        flag("-", "B_DUPLICATE_CELL", "%s: %s appears %d times" % (tag, k2, n2))

        elif shape == FIG_SHAPES[0]:
            if "PRE" not in phases or not (set(FIG_FOLLOWUP_PHASES) & phases):
                flag("-", "A_PHASE_INCOMPLETE",
                     "%s: needs PRE plus one of %s, found %s"
                     % (tag, "/".join(FIG_FOLLOWUP_PHASES), sorted(phases)))
            thin = [k2 for k2, n2 in g.groupby(ph_series).size().items() if n2 < 2]
            if thin:
                flag("-", "A_SINGLE_POINT_SERIES",
                     "%s: phase(s) %s have one x point - a time course needs >=2" % (tag, thin))

        elif shape == FIG_SHAPES[2]:
            if "PRE" not in phases:
                flag("-", "C_NO_BASELINE", "%s: no PRE baseline, found %s" % (tag, sorted(phases)))
            if not (set(FIG_FOLLOWUP_PHASES) & phases):
                flag("-", "C_NO_FOLLOWUP",
                     "%s: only %s - needs at least one DURING/POST/RECOVERY day" % (tag, sorted(phases)))
            if "Timepoint_Days" in g.columns and g["Timepoint_Days"].map(fig_is_blank).any():
                flag("-", "C_MISSING_DAYS", "%s: Timepoint_Days blank on some rows" % tag)

        elif shape == FIG_SHAPES[3]:
            if "DELTA" in phases:
                if len(phases) > 1:
                    flag("-", "D_DELTA_MIXED_WITH_LEVELS",
                         "%s: %s - a delta row cannot share a unit with level rows" % (tag, sorted(phases)))
            elif not ("PRE" in phases and (set(FIG_FOLLOWUP_PHASES) & phases)):
                flag("-", "D_NO_PREPOST_PAIR",
                     "%s: %s - needs PRE plus a follow-up phase, or Exposure_Phase=DELTA"
                     % (tag, sorted(phases)))

        elif shape == FIG_SHAPES[6]:
            if not phases <= {"DURING"}:
                flag("-", "G_PHASE_NOT_DURING",
                     "%s: %s - a factorial condition grid has no pre-exposure baseline; "
                     "use DURING on every row" % (tag, sorted(phases)))
            f1 = set(x for x in g.get("Posture_Condition", pd.Series(dtype=object))
                     .map(lambda v: "" if fig_is_blank(v) else str(v).strip().upper()) if x)
            f2 = set(x for x in g.get("Timepoint_Label", pd.Series(dtype=object))
                     .map(lambda v: "" if fig_is_blank(v) else str(v).strip().upper()) if x)
            if len(f1) < 2 or len(f2) < 2:
                flag("-", "G_NOT_A_GRID",
                     "%s: G needs >=2 levels on BOTH factors (Posture=%s, Timepoint=%s) - "
                     "a single-factor series is A_CHALLENGE_TIMECOURSE, not G"
                     % (tag, sorted(f1), sorted(f2)))
            pc_s = g.get("Posture_Condition", pd.Series(index=g.index, dtype=object)).map(
                lambda v: "" if fig_is_blank(v) else str(v).strip().upper())
            tp_s = g.get("Timepoint_Label", pd.Series(index=g.index, dtype=object)).map(
                lambda v: "" if fig_is_blank(v) else str(v).strip().upper())
            blank_rows = int(((pc_s == "") | (tp_s == "")).sum())
            if blank_rows:
                flag("-", "G_FACTOR_MISSING",
                     "%s: %d row(s) have an empty Posture_Condition or Timepoint_Label - "
                     "a blank factor cell cannot fill a grid cell; label every level"
                     % (tag, blank_rows))
            observed = set(zip(pc_s[(pc_s != "") & (tp_s != "")],
                               tp_s[(pc_s != "") & (tp_s != "")]))
            seen = {}
            for a, b in zip(pc_s, tp_s):
                if a == "" or b == "":
                    continue
                seen[(a, b)] = seen.get((a, b), 0) + 1
            for cell, n2 in seen.items():
                if n2 > 1:
                    flag("-", "G_DUPLICATE_CELL", "%s: %s appears %d times" % (tag, cell, n2))
            if len(f1) >= 2 and len(f2) >= 2:
                expected = {(a, b) for a in f1 for b in f2}
                gaps = sorted(expected - observed)
                if gaps:
                    flag("-", "G_INCOMPLETE_GRID",
                         "%s: %d of %d cells missing from the %dx%d grid: %s"
                         % (tag, len(gaps), len(expected), len(f1), len(f2), gaps[:6]))

    return pd.DataFrame(problems)
