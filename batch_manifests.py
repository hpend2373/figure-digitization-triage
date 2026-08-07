"""Declarative execution layer: what to read, and how, stated before any run.

The four grains in `grid_engine.py` describe the DATA - what a figure claims.
The first three manifests below describe SOURCE COMPLETENESS; the remaining four
describe the RUN - where the marks are, which reader sees them, and
what each mark means. Keeping them apart matters: a value file must be reviewable
by someone who never touches a raster, and a run file must be re-executable by
someone who never reads the paper.

    source_document_manifest.csv one row per article/supplement/chapter source
    source_figure_manifest.csv one row per physical publisher figure
    source_panel_inventory.csv one row per visible plot region, including panels
                               that will not be digitized
    panel_manifest.csv     one row per readable panel: box, mark type, axis
                           calibration, and the unit it fills
    series_manifest.csv    one row per series within a panel: how the reader
                           tells it apart, and which factor level it IS
    position_manifest.csv  one row per x position within a panel: where it is,
                           and which factor level it IS
    reader_config.csv      long-form option table, one row per option

Two rules run through all of it.

**Identity is declared, never inferred.** A series is a factor level because the
manifest says so, not because it was drawn second. A position is DI19 because
the manifest says so, not because it is the fourth bar from the left. When a
reader cannot resolve a mark, the cell stays empty and the grid engine names the
hole - nothing shifts to fill it.

**Every option is validated against the reader that will receive it.** An option
misspelled, or correct but meaningless for this mark type, is an error before the
run rather than a default silently applied during it. That is the difference
between a config file and a suggestion.
"""
import hashlib
import json
import os
import re
import unicodedata

import pandas as pd


# --------------------------------------------------------------------------
# vocabularies
# --------------------------------------------------------------------------

#: Mark types the batch layer can dispatch. A superset of `MARK_TYPES` would be
#: a lie; a subset means a manifest can name a reader the runner cannot call.
BATCH_MARK_TYPES = ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO",
                    "SCATTER", "BOX_VIOLIN")

#: Which mark types locate marks at declared x positions, and therefore require
#: rows in `position_manifest.csv`. SCATTER does not: its x IS data.
POSITIONAL_MARK_TYPES = ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO",
                         "BOX_VIOLIN")

#: Which mark types separate series by colour and therefore need one.
COLOUR_MARK_TYPES = ("BAR_COLOR", "LINE_COLOR")

#: Which mark types separate series by drawn form rather than by colour.
MONO_MARK_TYPES = ("BAR_MONO", "LINE_MONO")

#: What the batch layer can actually EXECUTE, per statistic type, and how.
#:
#: `grid_engine` validates four statistic types. The batch layer has raster
#: readers for two of them. `BINARY_EVENT` has a source-panel disposition
#: (`BINARY_EXTRACT`) and a validator and no reader; a transcribed value has a
#: validator and no input channel at all, because `run_batch` sends every run
#: panel to a raster reader. So a manifest could declare a statistic this
#: package validates, be told nothing, and then be routed to a reader that
#: cannot produce it.
#:
#: A capability the package does not have should be a sentence, not a discovery.
CAPABILITY_MATRIX = {
    "CONTINUOUS": ("AUTO_SUPPORTED",
                   "BAR_COLOR, BAR_MONO, LINE_COLOR and LINE_MONO read means "
                   "and error bars at declared positions"),
    "ASSOCIATION": ("AUTO_SUPPORTED",
                    "SCATTER digitizes the cloud and summarizes it; the paper "
                    "declares which association it reports"),
    "QUANTILE_SUMMARY": ("AUTO_SUPPORTED",
                         "BOX_VIOLIN reads a five-number summary at declared "
                         "positions, one series per panel"),
    "BINARY_EVENT": ("VALIDATOR_ONLY",
                     "the grid engine checks events against N at risk, but no "
                     "released reader produces counts from a raster. Inventory "
                     "the panel as BINARY_EXTRACT and transcribe the numbers"),
}

#: Statistic types the validator understands and the runner cannot execute.
VALIDATOR_ONLY_STATISTICS = tuple(
    k for k, (status, _) in sorted(CAPABILITY_MATRIX.items())
    if status == "VALIDATOR_ONLY")


#: Mark types this project has a name and a design for, but no released reader.
#: Naming them is better than silence: a manifest that declares one gets told
#: why it cannot run and where the work stands, instead of being quietly
#: routed to a reader that ignores half its declaration.
UNRELEASED_MARK_TYPES = {
    "LINE_MONO_STYLE": ("monochrome lines separated by SOLID/DASHED line style "
                        "rather than by marker. Built and measured but not "
                        "released - it emits cells where two curves cross "
                        "instead of dropping them. See wip/line_style_mono.py"),
}

MARKER_SHAPES = ("CIRCLE", "TRIANGLE", "SQUARE", "DIAMOND", "NONE")
MARKER_FILLS = ("OPEN", "FILLED", "ANY")
LINE_STYLES = ("SOLID", "DASHED", "DOTTED", "NONE")
BAR_FILL_PATTERNS = ("SOLID", "HATCHED", "OPEN", "NONE")
AXIS_SCALES = ("LINEAR", "LOG")

#: Associations `summarize_association` can compute from a digitized cloud.
SCATTER_ASSOCIATION_TYPES = ("PEARSON_R", "SPEARMAN_RHO", "KENDALL_TAU",
                             "R_SQUARED", "SLOPE")

#: How a panel is meant to be handled. AUTO means the runner reads it; MANUAL
#: means a human already decided the reader cannot, and the runner emits a
#: queue row instead of attempting it and reporting a plausible number.
PANEL_MODES = ("AUTO", "MANUAL")

#: Terminal states a panel can reach in a run. Every panel lands on exactly one.
RUN_STATES = (
    "AUTO_PASS",                 # read, converted, and clean through the gate
    "NO_READER_AVAILABLE",       # correctly declared, but no released reader
    "MANUAL_POINT_READ",         # reader produced nothing usable; hand-digitize
    "SERIES_IDENTITY_UNRESOLVED",  # marks found, but which series is ambiguous
    "PANEL_GEOMETRY_UNRESOLVED",   # box or calibration cannot be trusted
    "NO_VARIANCE",               # centres read, dispersion absent or unconfirmed
    "NOT_CONVERTIBLE",           # the mark cannot become the declared statistic
    "QC_FAILED",                 # values produced, but the grid gate rejected them
)

# Source completeness is deliberately independent of reader capability.  A
# panel may be closed as non-target or not-data, or queued because no reader is
# available, but it may not disappear simply because nobody created a run row.
SOURCE_INVENTORY_STATUSES = ("VISUALLY_VERIFIED", "PENDING")
SOURCE_PANEL_COUNT_METHODS = ("HUMAN_VISUAL", "MACHINE_PLUS_HUMAN")
SOURCE_DOCUMENT_ROLES = ("MAIN_ARTICLE", "SUPPLEMENT", "APPENDIX",
                         "PROCEEDINGS_CHAPTER")


REVIEWER_ATTESTATIONS = ("HUMAN_CONFIRMED", "AUTOMATED_AGENT", "DEMO_EXAMPLE")

#: Whether a registry row describes a person or an illustration.
#:
#: The run mode used to be an argument: `run_batch(..., run_mode="DEMO_ONLY")`.
#: That is the caller's promise about the manifests, and a promise made at one
#: call site does not travel with the files. Running the demonstration and then
#: replaying its own manifests through the plain CLI produced Status=RAN,
#: Run_Mode=ATTESTED - the same fictional reviewer, now unqualified. Whether a
#: run may produce poolable values is a property of who attested it, so it is
#: recorded next to them and derived from there.
REVIEWER_RECORD_TYPES = ("HUMAN", "DEMO_IDENTITY")

#: Which attestation each record type may hold. A demo row cannot claim
#: HUMAN_CONFIRMED and a human row cannot hide behind DEMO_EXAMPLE, so editing
#: either column alone cannot quietly change what the row means.
_ATTESTATION_FOR_RECORD = {"HUMAN": ("HUMAN_CONFIRMED", "AUTOMATED_AGENT"),
                           "DEMO_IDENTITY": ("DEMO_EXAMPLE",)}
REVIEWER_CONTACT_TYPES = ("EMAIL", "ORCID")

# Whole-name tokens that name a class of software rather than a person.  This
# list is a courtesy check, NOT the guarantee - it is unbounded by construction
# and anyone determined to write a person's name where there is no person will
# succeed.  What makes the attestation auditable is `Reviewer_Contact` plus
# `Human_Attestation`, both of which name someone who can be asked.  The check
# fires only when EVERY token of the name is one of these, so that a real
# Claude Bernard registers without argument and a bare `Claude` does not.
NON_HUMAN_NAME_TOKENS = frozenset((
    "AI", "BOT", "LLM", "GPT", "CHATGPT", "CODEX", "CLAUDE", "COPILOT",
    "GEMINI", "LLAMA", "ROBOT", "SCRIPT", "AUTO", "AUTOMATED", "AUTOMATION",
    "MACHINE", "AGENT", "ASSISTANT", "MODEL", "SYSTEM", "PIPELINE", "TOOL",
))

#: The shape an identifier must have to be safe as part of a filename.
#:
#: `Panel_ID` and `Series_ID` are interpolated straight into artifact names -
#: `{Panel_ID}_marks.json`, `{Panel_ID}.tar`, `{Panel_ID}_{Series_ID}_points.json`
#: - and nothing checked them. `Panel_ID="../../escaped"` wrote `escaped.tar` and
#: `escaped_marks.json` two directories above the output root, and the batch
#: still reported ACCEPTED. In a workflow where an agent drafts the manifests,
#: a mistyped ID is enough; it does not take malice.
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Which columns hold an identifier that becomes part of a path.
PATH_FORMING_ID_COLUMNS = {
    "panels": ("Panel_ID", "Config_ID"),
    "series": ("Panel_ID", "Series_ID"),
    "positions": ("Panel_ID", "Position_ID"),
    "configs": ("Config_ID",),
    "source_panels": ("Source_Panel_ID",),
    "source_figures": ("Source_Figure_ID",),
    "source_documents": ("Source_Document_ID",),
    "reviewers": ("Reviewer_ID",),
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
_ORCID_RE = re.compile(r"^(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])$")


def name_tokens(value):
    """Alphanumeric tokens of a personal name, Unicode-aware.

    The first version of this used `re.sub(r"[^0-9A-Za-z]", "", who)`, which is
    a statement that names are written in the Latin alphabet.  It rejected
    `김민엽`, `李明` and `홍길동` outright - every CJK character was stripped, the
    remainder was empty, and the person who actually did the inspection could
    not record that they had.  A validator that refuses the reviewer's own name
    does not make the attestation stronger; it makes it impossible.

    NFKC first, because `ＡＢ` and `AB` are the same two letters and only one of
    them is typed on purpose.
    """
    normalized = unicodedata.normalize("NFKC", str(value))
    token, out = [], []
    for ch in normalized:
        if ch.isalnum():
            token.append(ch)
        elif token:
            out.append("".join(token))
            token = []
    if token:
        out.append("".join(token))
    return out


def orcid_checksum_ok(digits):
    """ISO 7064 MOD 11-2, the check digit ORCID actually uses.

    Worth doing: it is the one identity field in this package that can be
    checked without asking anybody, and a mistyped ORCID is indistinguishable
    from a fabricated one until somebody tries to write to it.
    """
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    remainder = total % 11
    expected = (12 - remainder) % 11
    return ("X" if expected == 10 else str(expected)) == digits[-1].upper()


def check_reviewer_registry(reviewers, flag, kernel=None):
    """The ledger the source manifests point at, and the only place a name lives.

    `Inspector` was free text on every source row, which made it unverifiable
    twice over: nothing connected two spellings of the same person, and nothing
    distinguished a person from a process.  A foreign key into a registered
    ledger fixes the first completely and the second as far as software can -
    registering a non-person now takes a deliberate, attributable, reviewable
    act instead of typing three letters into a column nobody reads.

    `Human_Attestation` is a declared enum, not a cryptographic signature. It
    says a person typed HUMAN_CONFIRMED next to a contact; it does not prove
    who typed it. What it buys is traceability - a row that can be asked about -
    and calling it anything stronger would overstate it.
    """
    import datetime
    if kernel is None:
        import kernel as kernel_module
        kernel = kernel_module
    index = {}
    for i, r in reviewers.iterrows():
        line = "reviewers:%d" % (i + 2)
        rid = str(r.get("Reviewer_ID", "")).strip()
        if not rid:
            flag(line, "MISSING_REQUIRED", "Reviewer_ID")
            continue
        if rid in index:
            flag(line, "DUPLICATE_REVIEWER_ID", rid)
            continue
        index[rid] = r
        for c in ("Reviewer_Name", "Reviewer_Record_Type", "Contact_Type",
                  "Reviewer_Contact", "Registered_By", "Registration_Date",
                  "Human_Attestation"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)

        for field in ("Reviewer_ID", "Reviewer_Name", "Reviewer_Contact",
                      "Registered_By"):
            value = str(r.get(field, "")).strip()
            marker = kernel.fig_unresolved_marker(value)
            if marker:
                flag(line, "UNRESOLVED_REVIEWER_IDENTITY",
                     "%s contains %r - a reviewer nobody can name is not a "
                     "reviewer" % (field, marker))

        for field in ("Reviewer_Name", "Registered_By"):
            value = str(r.get(field, "")).strip()
            if not value:
                continue
            tokens = name_tokens(value)
            glyphs = sum(len(t) for t in tokens)
            # Version numbers do not rescue a model name: `GPT-4` splits into
            # GPT and 4, only the letters carry the claim, and `gpt4` is the
            # same token with the hyphen left out.
            worded = [t for t in tokens if any(ch.isalpha() for ch in t)]
            if glyphs < 2 or not worded:
                flag(line, "UNRESOLVED_REVIEWER_IDENTITY",
                     "%s=%r is not a name - the point of the field is that "
                     "somebody can be asked about the count" % (field, value))
            elif all(t.upper().rstrip("0123456789") in NON_HUMAN_NAME_TOKENS
                     for t in worded):
                flag(line, "REVIEWER_NOT_HUMAN",
                     "%s=%r names a class of software, not a person. If a real "
                     "person is meant, record the full name; no software counted "
                     "the panels in a published figure" % (field, value))

        record_type = str(r.get("Reviewer_Record_Type", "")).strip().upper()
        if record_type and record_type not in REVIEWER_RECORD_TYPES:
            flag(line, "BAD_REVIEWER_RECORD_TYPE",
                 "%r is not one of %s" % (record_type, ", ".join(REVIEWER_RECORD_TYPES)))

        attestation = str(r.get("Human_Attestation", "")).strip().upper()
        if attestation and attestation not in REVIEWER_ATTESTATIONS:
            flag(line, "BAD_HUMAN_ATTESTATION",
                 "%r is not one of %s" % (attestation, ", ".join(REVIEWER_ATTESTATIONS)))
        elif (record_type in _ATTESTATION_FOR_RECORD and attestation
                and attestation not in _ATTESTATION_FOR_RECORD[record_type]):
            flag(line, "REVIEWER_RECORD_TYPE_MISMATCH",
                 "Reviewer_Record_Type=%s with Human_Attestation=%s. A %s row "
                 "may only hold %s - the two columns say what the row is, and "
                 "they have to agree"
                 % (record_type, attestation, record_type,
                    " or ".join(_ATTESTATION_FOR_RECORD[record_type])))
        elif attestation == "AUTOMATED_AGENT":
            flag(line, "REVIEWER_NOT_HUMAN",
                 "%s is declared AUTOMATED_AGENT. The panel count is only "
                 "evidence because a person opened the figure and looked at it, "
                 "so an automated agent cannot hold that attestation" % rid)

        ctype = str(r.get("Contact_Type", "")).strip().upper()
        contact = str(r.get("Reviewer_Contact", "")).strip()
        if ctype and ctype not in REVIEWER_CONTACT_TYPES:
            flag(line, "BAD_CONTACT_TYPE",
                 "%r is not one of %s" % (ctype, ", ".join(REVIEWER_CONTACT_TYPES)))
        elif contact and ctype == "EMAIL" and not _EMAIL_RE.match(contact):
            flag(line, "BAD_REVIEWER_CONTACT",
                 "Reviewer_Contact=%r is not an address anyone could write to" % contact)
        elif contact and ctype == "ORCID":
            m = _ORCID_RE.match(contact)
            if not m:
                flag(line, "BAD_REVIEWER_CONTACT",
                     "Reviewer_Contact=%r is not an ORCID (0000-0000-0000-0000)" % contact)
            elif not orcid_checksum_ok(contact.replace("-", "")):
                flag(line, "BAD_REVIEWER_CONTACT",
                     "ORCID %s fails its ISO 7064 check digit - it is a typo or "
                     "it was made up" % contact)

        when = str(r.get("Registration_Date", "")).strip()
        if when:
            try:
                parsed = datetime.date.fromisoformat(when)
            except ValueError:
                flag(line, "BAD_REGISTRATION_DATE",
                     "Registration_Date=%r is not an ISO date (YYYY-MM-DD)" % when)
            else:
                if parsed > datetime.date.today():
                    flag(line, "BAD_REGISTRATION_DATE",
                         "Registration_Date=%s is in the future" % when)
    return index


def referenced_reviewer_ids(*frames):
    """Every Reviewer_ID an inventory actually leans on."""
    out = set()
    for df in frames:
        if df is None or not len(df) or "Reviewer_ID" not in getattr(df, "columns", ()):
            continue
        for value in df["Reviewer_ID"]:
            rid = str(value).strip()
            if rid:
                out.add(rid)
    return out


def derive_run_mode(reviewers, *inventory_frames):
    """DEMO_ONLY if any reviewer this inventory rests on is an illustration.

    Derived, not asked for. An unreferenced DEMO_IDENTITY row sitting in the
    registry is harmless - nobody attested anything with it - so only the rows
    the source manifests actually name are consulted.
    """
    if reviewers is None or not len(reviewers):
        return "ATTESTED"
    used = referenced_reviewer_ids(*inventory_frames)
    for _, r in reviewers.iterrows():
        rid = str(r.get("Reviewer_ID", "")).strip()
        if used and rid not in used:
            continue
        if str(r.get("Reviewer_Record_Type", "")).strip().upper() == "DEMO_IDENTITY":
            return "DEMO_ONLY"
    return "ATTESTED"


def check_attestation(row, line, flag, reviewer_index=None, kernel=None):
    """The one human act this whole layer rests on has to be a real answer.

    No software can count the panels in an arbitrary published figure, so the
    inventory's correctness reduces to a person having opened it and looked.
    Everything above this - coverage, routing, the queue - is only as good as
    that attestation, which makes it the single most important field in the
    package and the one most worth being strict about.

    Requiring it to be non-blank is not enough: `Inspector=TBD` and
    `Inspection_Date=soon` both passed, and so did `2026-13-45`, which is not a
    date at all. That is the same defect as a hedged `Errorbar_Definition_Source`
    - a non-answer occupying the field that is supposed to hold the answer - and
    it is worse here, because there is no second source to fall back on.

    Checking the spelling of a free-text name was the next version of the same
    mistake. `Reviewer_ID` is now a foreign key: the name, the contact and the
    human attestation live once in `reviewer_registry.csv`, and this row either
    points at a registered person or does not run.
    """
    import datetime
    if kernel is None:
        import kernel as kernel_module
        kernel = kernel_module
    who = str(row.get("Reviewer_ID", "")).strip()
    when = str(row.get("Inspection_Date", "")).strip()
    for field, value in (("Reviewer_ID", who), ("Inspection_Date", when)):
        marker = kernel.fig_unresolved_marker(value)
        if marker:
            flag(line, "UNRESOLVED_INVENTORY_ATTESTATION",
                 "%s contains %r. Nobody has looked at this figure yet, and the "
                 "panel count below is therefore not evidence of anything"
                 % (field, marker))
    if who and reviewer_index is not None and who not in reviewer_index:
        flag(line, "REVIEWER_NOT_REGISTERED",
             "Reviewer_ID=%r is not in reviewer_registry.csv. Register the "
             "person who did the inspection before their count is used" % who)
    if when:
        try:
            parsed = datetime.date.fromisoformat(when)
        except ValueError:
            flag(line, "BAD_INSPECTION_DATE",
                 "Inspection_Date=%r is not an ISO date (YYYY-MM-DD). A free-text "
                 "date cannot be compared with anything, which is the only "
                 "reason to record one" % when)
        else:
            if parsed > datetime.date.today():
                flag(line, "BAD_INSPECTION_DATE",
                     "Inspection_Date=%s is in the future - an inspection that "
                     "has not happened is not an inspection" % when)
SOURCE_TARGET_STATUSES = ("TARGET", "NON_TARGET", "NOT_DATA", "UNCERTAIN")
SOURCE_PANEL_DISPOSITIONS = (
    "AUTO_DIGITIZE",
    "MANUAL_DIGITIZE",
    "NO_READER_AVAILABLE",
    "ASSOCIATION_EXTRACT",
    "BINARY_EXTRACT",
    "NO_SUMMARY_STATISTIC",
    "NON_TARGET_OUTCOME",
    "NOT_DATA",
    "DUPLICATE_OR_DECORATIVE",
    "UNRESOLVED",
)

_TARGET_DISPOSITIONS = {
    "AUTO_DIGITIZE", "MANUAL_DIGITIZE", "NO_READER_AVAILABLE",
    "ASSOCIATION_EXTRACT", "BINARY_EXTRACT", "NO_SUMMARY_STATISTIC",
}
_RUN_LINK_REQUIRED = {"AUTO_DIGITIZE", "ASSOCIATION_EXTRACT", "BINARY_EXTRACT"}
_CLOSED_WITHOUT_READER = {
    "MANUAL_DIGITIZE", "NO_READER_AVAILABLE", "NO_SUMMARY_STATISTIC",
    "NON_TARGET_OUTCOME", "NOT_DATA", "DUPLICATE_OR_DECORATIVE",
}


# --------------------------------------------------------------------------
# reader options: name -> (parser, applies-to)
# --------------------------------------------------------------------------

def _as_int(v):
    f = float(v)
    if f != int(f):
        raise ValueError("expected a whole number, got %r" % v)
    return int(f)


def _as_float(v):
    return float(v)


def _as_bool(v):
    s = str(v).strip().upper()
    if s in ("TRUE", "T", "YES", "1"):
        return True
    if s in ("FALSE", "F", "NO", "0"):
        return False
    raise ValueError("expected TRUE or FALSE, got %r" % v)


def _grey(v):
    """A 8-bit grey threshold. Outside 0-255 it selects everything or nothing."""
    if not (0 <= v <= 255):
        raise ValueError("a grey threshold must be 0-255, got %r" % v)
    return v


def _positive(v):
    if v <= 0:
        raise ValueError("must be greater than zero, got %r" % v)
    return v


def _non_negative(v):
    if v < 0:
        raise ValueError("must not be negative, got %r" % v)
    return v


def _at_least_one(v):
    if v < 1:
        raise ValueError("must be at least 1, got %r" % v)
    return v


def _anything(v):
    return v


#: option -> (parser, mark types that accept it, the reader keyword it becomes,
#:            range check). The range check is not decoration: `threshold=-1`
#: selects no pixels at all and `max_marker_area=10` below `min_marker_area=500`
#: selects no contours, and both of those used to pass validation and then
#: produce an empty panel that looked like an unreadable figure.
READER_OPTIONS = {
    "threshold":        (_as_int, ("BAR_MONO", "LINE_MONO", "BOX_VIOLIN"),
                         "threshold", _grey),
    "stem_threshold":   (_as_int, ("BAR_MONO",), "stem_threshold", _grey),
    "group_window":     (_as_int, ("BAR_MONO",), "group_window", _positive),
    # Consumed by the RUNNER, not passed to a reader: LINE_COLOR and SCATTER
    # take it through SeriesSpec, and BAR_COLOR now builds each series' mask
    # from its Colour_Hex at this tolerance. It used to be a no-op for
    # BAR_COLOR - declared, validated, and changing nothing.
    "colour_tolerance": (_as_float, COLOUR_MARK_TYPES + ("SCATTER",), None,
                         _non_negative),
    "x_window":         (_as_int, ("LINE_COLOR", "LINE_MONO"), "x_window", _positive),
    "half_window":      (_as_int, ("BOX_VIOLIN",), "half_window", _positive),
    "min_marker_area":  (_as_float, ("SCATTER",), "min_area", _positive),
    "max_marker_area":  (_as_float, ("SCATTER",), "max_area", _positive),
    "min_bar_px":       (_as_int, ("BAR_COLOR", "BAR_MONO"), "min_bar_px", _positive),
    "stem_half_width":  (_as_int, ("BAR_COLOR",), "stem_half_width", _positive),
    "max_whisker_px":   (_as_int, ("BAR_COLOR",), "max_whisker_px", _positive),
    "stem_required":    (_as_bool, ("BAR_COLOR",), "stem_required", _anything),
    "baseline_value":   (_as_float, ("BAR_COLOR", "BAR_MONO"), "baseline_value",
                         _anything),
    # BAR_COLOR only. `read_monochrome_bar_panel` derives its slot count from
    # the number of declared series and has no n_slots parameter at all - the
    # manifest used to accept the option here, and the run then died with a
    # TypeError that surfaced as PANEL_GEOMETRY_UNRESOLVED. A reader-signature
    # introspection test now makes that class of mismatch impossible to ship.
    # `n_slots` is gone. It existed so a colour bar panel could rebuild its own
    # x spacing from the bars it happened to detect - which is inference, and
    # got the labels wrong whenever the leftmost bar of a series was invisible.
    # BAR_COLOR now matches bars to the pixels in `position_manifest.csv`, so
    # the count is not something a config file needs to say.
    "slot_tolerance_px": (_as_float, ("BAR_COLOR",), "slot_tolerance_px",
                          _positive),
    "dual_tolerance_pct": (_as_float, BATCH_MARK_TYPES, None, _non_negative),
}

#: Options that only make sense against each other.
PAIRED_OPTION_RULES = (
    ("min_marker_area", "max_marker_area",
     lambda lo, hi: lo < hi,
     "min_marker_area must be below max_marker_area, or no contour can match"),
)


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------

def panel_manifest_columns():
    return [
        "Panel_ID", "Source_Panel_ID", "Figure_ID", "Unit_ID", "Panel_Label", "Mark_Type",
        "Image_Path",
        # the plot area, in image pixels
        "Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1",
        # where the axes live, so a human re-checking calibration knows where to
        # look and a future tick-finder has somewhere to search
        "Axis_X_Region", "Axis_Y_Region",
        "Axis_X_Scale", "Axis_Y_Scale",
        # "v1:px1;v2:px2" - at least two points per axis in use
        "Axis_X_Ticks", "Axis_Y_Ticks",
        "Baseline_Value",
        # which association a scatter panel is meant to yield. It is a run
        # instruction, not a finding: the paper says which statistic it reports,
        # and the reader must not pick one by looking at the points.
        "Association_Type",
        "Config_ID", "Panel_Mode", "Note",
    ]


def series_manifest_columns():
    return [
        "Panel_ID", "Series_ID",
        # colour readers
        "Colour_Hex", "Colour_Tolerance", "Mask_Key",
        # monochrome readers
        "Marker_Shape", "Marker_Fill", "Line_Style", "Bar_Fill_Pattern",
        # what the series MEANS - this is what reaches the Cell_Key
        "Factor_Name", "Factor_Level", "Note",
    ]


def position_manifest_columns():
    return [
        "Panel_ID", "Position_ID", "X_Pixel", "Slot_Index", "Display_Order",
        # what the position MEANS
        "Factor_Name", "Factor_Level", "Timepoint_Label", "Timepoint_Days",
        "Note",
    ]


def reader_config_columns():
    return ["Config_ID", "Option", "Value", "Note"]


def reviewer_registry_columns():
    """The people whose visual inspections this package is allowed to trust.

    Small by nature - a 160-publication review has a handful of extractors - and
    worth keeping by hand.  Every `Reviewer_ID` in the source manifests must
    appear here, which is what turns `Inspector` from an unverifiable string
    into something a second reader can audit.
    """
    return [
        "Reviewer_ID", "Reviewer_Name", "Reviewer_Record_Type", "Contact_Type",
        "Reviewer_Contact", "Registered_By", "Registration_Date",
        "Human_Attestation", "Note",
    ]


def source_figure_manifest_columns():
    """Physical figures, before any outcome-specific virtual split."""
    return [
        "Source_Figure_ID", "Source_Document_ID", "Publication_ID", "Figure_Number", "Source_File",
        "Source_Page", "Source_Image", "Source_Image_SHA256", "Observed_Panel_Count",
        "Inventory_Status", "Panel_Count_Method", "Reviewer_ID",
        "Inspection_Date", "Note",
    ]


def source_document_manifest_columns():
    """One row per source document whose full article range was inventoried."""
    return [
        "Source_Document_ID", "Publication_ID", "Document_Role", "Source_File",
        "Article_Page_Range", "Observed_Figure_Count", "Inventory_Status",
        "Figure_Count_Method", "Reviewer_ID", "Inspection_Date", "Note",
    ]


def source_panel_inventory_columns():
    """One row per visually distinct source subpanel in a physical figure.

    Include plots, photographs, schematics and table/inset panels.  Whether a
    panel contains extractable data is its disposition, not a reason to omit it.
    """
    return [
        "Source_Panel_ID", "Source_Figure_ID", "Panel_Label", "Outcome_Label",
        "Target_Status", "Panel_Disposition", "Disposition_Reason", "Note",
    ]


BATCH_TEMPLATES = (
    ("reviewer_registry", reviewer_registry_columns),
    ("source_document_manifest", source_document_manifest_columns),
    ("source_figure_manifest", source_figure_manifest_columns),
    ("source_panel_inventory", source_panel_inventory_columns),
    ("panel_manifest", panel_manifest_columns),
    ("series_manifest", series_manifest_columns),
    ("position_manifest", position_manifest_columns),
    ("reader_config", reader_config_columns),
)


# --------------------------------------------------------------------------
# small parsers, each of which fails loudly
# --------------------------------------------------------------------------

def blank(v):
    return v is None or (isinstance(v, float) and v != v) or not str(v).strip()


def parse_ticks(text):
    """'0:450;20:50' -> [(0.0, 450.0), (20.0, 50.0)].

    Two distinct pixels are required. One tick cannot define a scale, and two
    ticks at the same pixel define an infinite one - both have shipped as
    'calibrated' in real projects.
    """
    pairs = []
    for chunk in str(text).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError("tick %r is not value:pixel" % chunk)
        v, px = chunk.split(":", 1)
        pairs.append((float(v), float(px)))
    if len(pairs) < 2:
        raise ValueError("need at least two ticks, got %d" % len(pairs))
    if len({p for _, p in pairs}) < 2:
        raise ValueError("all ticks share one pixel row")
    if len({v for v, _ in pairs}) < 2:
        raise ValueError("all ticks share one value")
    return pairs


def parse_box(text):
    """'x0,x1,y0,y1' -> a 4-tuple of ints, ordered and non-degenerate."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 4:
        raise ValueError("expected x0,x1,y0,y1, got %r" % text)
    x0, x1, y0, y1 = (int(round(float(p))) for p in parts)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("degenerate or inverted box %r" % text)
    return x0, x1, y0, y1


def parse_colour(text):
    """'#1e50dc' or '30,80,220' -> (r, g, b)."""
    s = str(text).strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) != 6:
            raise ValueError("hex colour must be 6 digits, got %r" % text)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError("expected #rrggbb or r,g,b, got %r" % text)
    rgb = tuple(int(p) for p in parts)
    if not all(0 <= c <= 255 for c in rgb):
        raise ValueError("colour channel out of range in %r" % text)
    return rgb


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def load_reader_configs(config_df, mark_type_by_config, flag):
    """Long-form option rows -> {Config_ID: {option: parsed value}}.

    `mark_type_by_config` maps a Config_ID to the set of mark types that use it,
    so an option can be rejected for the reader that would actually receive it
    rather than merely for existing.
    """
    out = {}
    for i, r in config_df.iterrows():
        line = "reader_config:%d" % (i + 2)
        cid = str(r.get("Config_ID", "")).strip()
        opt = str(r.get("Option", "")).strip()
        if not cid or not opt:
            flag(line, "MISSING_REQUIRED", "Config_ID and Option are required")
            continue
        if opt not in READER_OPTIONS:
            flag(line, "UNKNOWN_READER_OPTION",
                 "%r is not a reader option; a misspelled option is silently "
                 "ignored otherwise, and the run reports the default as if it "
                 "had been chosen" % opt)
            continue
        parser, applies, _, check = READER_OPTIONS[opt]
        bucket = out.setdefault(cid, {})
        if opt in bucket:
            flag(line, "DUPLICATE_READER_OPTION",
                 "%s is set twice in config %s" % (opt, cid))
            continue
        try:
            bucket[opt] = check(parser(r.get("Value")))
        except (TypeError, ValueError) as exc:
            flag(line, "BAD_READER_OPTION_VALUE", "%s=%r: %s" % (opt, r.get("Value"), exc))
            bucket.pop(opt, None)
            continue
        used_by = mark_type_by_config.get(cid, set())
        wrong = sorted(m for m in used_by if m not in applies)
        if wrong:
            flag(line, "OPTION_WRONG_FOR_MARK_TYPE",
                 "%s does not apply to %s (accepted by %s)"
                 % (opt, ", ".join(wrong), ", ".join(applies)))
    for cid, bucket in out.items():
        for a, b, ok, message in PAIRED_OPTION_RULES:
            if a in bucket and b in bucket and not ok(bucket[a], bucket[b]):
                flag("config:%s" % cid, "READER_OPTIONS_CONTRADICT",
                     "%s=%r, %s=%r - %s" % (a, bucket[a], b, bucket[b], message))
    return out


def validate_batch_manifests(panels, series, positions, configs, units=None,
                             source_documents=None, source_figures=None, source_panels=None,
                             reviewers=None, requested_run_mode=None,
                             file_root=".", check_files=True):
    """Reject an unrunnable batch before a single raster is opened.

    Returns a DataFrame of problems - empty means the run may proceed. The
    checks are deliberately cheap and total: reading 160 publications and
    discovering on figure 140 that a Config_ID was misspelled is an expensive
    way to learn it.
    """
    problems = []

    def flag(where, check, detail):
        problems.append(dict(where=where, check=check, detail=detail))

    if source_documents is None:
        source_documents = pd.DataFrame()
    if source_figures is None:
        source_figures = pd.DataFrame()
    if source_panels is None:
        source_panels = pd.DataFrame()
    if reviewers is None:
        reviewers = pd.DataFrame()
    frames = (("reviewers", reviewers, reviewer_registry_columns()),
              ("source_documents", source_documents, source_document_manifest_columns()),
              ("source_figures", source_figures, source_figure_manifest_columns()),
              ("source_panels", source_panels, source_panel_inventory_columns()),
              ("panels", panels, panel_manifest_columns()),
              ("series", series, series_manifest_columns()),
              ("positions", positions, position_manifest_columns()),
              ("configs", configs, reader_config_columns()))
    for name, df, cols in frames:
        missing = [c for c in cols if c not in df.columns]
        if missing:
            flag(name, "SCHEMA_INCOMPLETE", "missing columns: " + ", ".join(missing))
        # A renamed column is the one schema change that can pass silently: the
        # old column is simply ignored, so a manifest that still records who
        # looked at the figure reads as one where nobody did.
        if "Inspector" in getattr(df, "columns", ()):
            flag(name, "LEGACY_INSPECTOR_COLUMN",
                 "Inspector was replaced by Reviewer_ID, a foreign key into "
                 "reviewer_registry.csv. Register each inspector once, then put "
                 "their Reviewer_ID here and delete the Inspector column")
    if problems:
        return pd.DataFrame(problems)

    # Identifiers become filenames, so they are checked before anything is
    # written with them - not by the code that writes, which would be one
    # forgotten call site away from the escape it is meant to stop.
    for name, df in (("reviewers", reviewers), ("source_documents", source_documents),
                     ("source_figures", source_figures), ("source_panels", source_panels),
                     ("panels", panels), ("series", series),
                     ("positions", positions), ("configs", configs)):
        for column in PATH_FORMING_ID_COLUMNS.get(name, ()):
            if column not in getattr(df, "columns", ()):
                continue
            for i, value in enumerate(df[column]):
                text = str(value).strip()
                if text and not SAFE_ID.match(text):
                    flag("%s:%d" % (name, i + 2), "UNSAFE_ID",
                         "%s=%r is interpolated into an artifact filename. "
                         "Allowed: letters, digits, dot, underscore, hyphen, "
                         "starting with a letter or digit, at most 128 characters"
                         % (column, text))

    reviewer_index = check_reviewer_registry(reviewers, flag)

    # A caller may demote a real run to a demonstration - that only throws
    # results away. It may not promote a demonstration to an attested run, and
    # asking to is an error rather than a silent correction: the point of
    # saying ATTESTED out loud is that somebody believed it.
    derived_mode = derive_run_mode(reviewers, source_documents, source_figures)
    if requested_run_mode == "ATTESTED" and derived_mode == "DEMO_ONLY":
        demo_ids = sorted(
            str(r.get("Reviewer_ID", "")).strip()
            for _, r in reviewers.iterrows()
            if str(r.get("Reviewer_Record_Type", "")).strip().upper() == "DEMO_IDENTITY")
        flag("reviewers", "RUN_MODE_REVIEWER_MISMATCH",
             "run_mode=ATTESTED was requested, but the inventory is attested by "
             "%s, which is Reviewer_Record_Type=DEMO_IDENTITY. Register the "
             "person who inspected the figures; a demonstration identity cannot "
             "be promoted by the caller" % ", ".join(demo_ids))

    root = os.path.realpath(file_root)
    _hash_cache = {}

    def sha256_of_file(path):
        """Hash a raster once per validation, however many rows name it."""
        if path not in _hash_cache:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            _hash_cache[path] = h.hexdigest()
        return _hash_cache[path]

    def resolve(p):
        """A declared image path, confined to `file_root`.

        The old version tried the string as given first, so an absolute path
        anywhere on the machine resolved happily, and `../` walked out of the
        root without comment. A manifest names a figure inside the corpus; it
        does not get to name a file outside it.
        """
        p = str(p).strip()
        if not p:
            return None
        candidate = p if os.path.isabs(p) else os.path.join(root, p)
        real = os.path.realpath(candidate)
        if real != root and not real.startswith(root + os.sep):
            return None
        return real if os.path.exists(real) else None

    unit_index = {}
    if units is not None:
        for _, u in units.iterrows():
            unit_index[str(u.get("Unit_ID", "")).strip()] = u

    # ----------------------------------------------------- source completeness
    # Figure_ID may be an outcome-specific virtual view.  It is therefore
    # forbidden as the completeness namespace: only Source_Figure_ID can prove
    # that every visible panel in the publisher's physical figure was handled.
    source_document_index = {}
    for i, r in source_documents.iterrows():
        line = "source_documents:%d" % (i + 2)
        sdid = str(r.get("Source_Document_ID", "")).strip()
        if not sdid:
            flag(line, "MISSING_REQUIRED", "Source_Document_ID")
            continue
        if sdid in source_document_index:
            flag(line, "DUPLICATE_SOURCE_DOCUMENT_ID", sdid)
            continue
        source_document_index[sdid] = r
        for c in ("Publication_ID", "Document_Role", "Source_File",
                  "Article_Page_Range", "Observed_Figure_Count",
                  "Inventory_Status", "Figure_Count_Method", "Reviewer_ID",
                  "Inspection_Date"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        check_attestation(r, line, flag, reviewer_index)
        role = str(r.get("Document_Role", "")).strip().upper()
        if role not in SOURCE_DOCUMENT_ROLES:
            flag(line, "BAD_SOURCE_DOCUMENT_ROLE", role)
        status = str(r.get("Inventory_Status", "")).strip().upper()
        method = str(r.get("Figure_Count_Method", "")).strip().upper()
        if status not in SOURCE_INVENTORY_STATUSES:
            flag(line, "BAD_SOURCE_INVENTORY_STATUS", status)
        elif status != "VISUALLY_VERIFIED":
            flag(line, "SOURCE_DOCUMENT_NOT_VERIFIED",
                 "review the full article/supplement range before execution")
        if method not in SOURCE_PANEL_COUNT_METHODS:
            flag(line, "BAD_SOURCE_FIGURE_COUNT_METHOD", method)
        try:
            count = _as_int(r.get("Observed_Figure_Count"))
            if count < 0:
                raise ValueError("must not be negative")
        except (TypeError, ValueError) as exc:
            flag(line, "SOURCE_FIGURE_COUNT_INVALID", str(exc))

    source_figure_index = {}
    source_figures_by_document = {}
    # The one hash every other layer is measured against. A figure is the raster
    # it names; if the file changed, the panel count, the boxes and the
    # calibrations were all taken from something else.
    source_figure_sha = {}
    for i, r in source_figures.iterrows():
        line = "source_figures:%d" % (i + 2)
        sfid = str(r.get("Source_Figure_ID", "")).strip()
        if not sfid:
            flag(line, "MISSING_REQUIRED", "Source_Figure_ID")
            continue
        if sfid in source_figure_index:
            flag(line, "DUPLICATE_SOURCE_FIGURE_ID", sfid)
            continue
        source_figure_index[sfid] = r
        sdid = str(r.get("Source_Document_ID", "")).strip()
        source_figures_by_document.setdefault(sdid, []).append(sfid)
        if sdid not in source_document_index:
            flag(line, "SOURCE_DOCUMENT_NOT_FOUND", sdid)
        elif str(r.get("Publication_ID", "")).strip() != str(
                source_document_index[sdid].get("Publication_ID", "")).strip():
            flag(line, "SOURCE_DOCUMENT_PUBLICATION_MISMATCH",
                 "%s belongs to Publication_ID=%s, not %s" % (
                     sdid, source_document_index[sdid].get("Publication_ID"),
                     r.get("Publication_ID")))
        for c in ("Source_Document_ID", "Publication_ID", "Figure_Number", "Source_File", "Source_Page",
                  "Source_Image", "Source_Image_SHA256", "Observed_Panel_Count",
                  "Inventory_Status", "Panel_Count_Method", "Reviewer_ID",
                  "Inspection_Date"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        check_attestation(r, line, flag, reviewer_index)
        declared_sha = str(r.get("Source_Image_SHA256", "")).strip().lower()
        source_figure_sha[sfid] = declared_sha
        if check_files and declared_sha:
            resolved_source = resolve(r.get("Source_Image"))
            if resolved_source is None:
                flag(line, "SOURCE_FILE_NOT_FOUND",
                     "Source_Image=%r is not on disk under %s"
                     % (r.get("Source_Image"), root))
            else:
                actual = sha256_of_file(resolved_source)
                if actual != declared_sha:
                    flag(line, "SOURCE_IMAGE_HASH_MISMATCH",
                         "Source_Image_SHA256 says %s..., the file on disk is "
                         "%s.... The inventory was taken from a different raster "
                         "than the one that will be read"
                         % (declared_sha[:16], actual[:16]))
        try:
            count = _as_int(r.get("Observed_Panel_Count"))
            if count < 1:
                raise ValueError("must be at least 1")
        except (TypeError, ValueError) as exc:
            flag(line, "SOURCE_PANEL_COUNT_INVALID", str(exc))
        status = str(r.get("Inventory_Status", "")).strip().upper()
        method = str(r.get("Panel_Count_Method", "")).strip().upper()
        if status not in SOURCE_INVENTORY_STATUSES:
            flag(line, "BAD_SOURCE_INVENTORY_STATUS", status)
        elif status != "VISUALLY_VERIFIED":
            flag(line, "SOURCE_INVENTORY_NOT_VERIFIED",
                 "the physical figure must be counted on screen before execution")
        if method not in SOURCE_PANEL_COUNT_METHODS:
            flag(line, "BAD_SOURCE_PANEL_COUNT_METHOD", method)

    for sdid, r in source_document_index.items():
        try:
            observed = _as_int(r.get("Observed_Figure_Count"))
        except (TypeError, ValueError):
            continue
        inventoried = len(source_figures_by_document.get(sdid, ()))
        if inventoried != observed:
            flag("source_document:%s" % sdid, "SOURCE_FIGURE_COVERAGE_INCOMPLETE",
                 "document has %d visible figures but source figure manifest has %d"
                 % (observed, inventoried))

    source_panel_index = {}
    source_panels_by_figure = {}
    for i, r in source_panels.iterrows():
        line = "source_panels:%d" % (i + 2)
        spid = str(r.get("Source_Panel_ID", "")).strip()
        sfid = str(r.get("Source_Figure_ID", "")).strip()
        if not spid or not sfid:
            flag(line, "MISSING_REQUIRED", "Source_Panel_ID and Source_Figure_ID")
            continue
        if spid in source_panel_index:
            flag(line, "DUPLICATE_SOURCE_PANEL_ID", spid)
            continue
        source_panel_index[spid] = r
        source_panels_by_figure.setdefault(sfid, []).append(spid)
        if sfid not in source_figure_index:
            flag(line, "SOURCE_FIGURE_NOT_FOUND", sfid)
        for c in ("Panel_Label", "Target_Status", "Panel_Disposition",
                  "Disposition_Reason"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        target = str(r.get("Target_Status", "")).strip().upper()
        disposition = str(r.get("Panel_Disposition", "")).strip().upper()
        if target not in SOURCE_TARGET_STATUSES:
            flag(line, "BAD_TARGET_STATUS", target)
        if disposition not in SOURCE_PANEL_DISPOSITIONS:
            flag(line, "BAD_PANEL_DISPOSITION", disposition)
        if target == "TARGET":
            if blank(r.get("Outcome_Label")):
                flag(line, "MISSING_TARGET_OUTCOME_LABEL",
                     "a target panel must name the outcome visible on screen")
            if disposition not in _TARGET_DISPOSITIONS:
                flag(line, "TARGET_DISPOSITION_CONTRADICTION",
                     "TARGET cannot be closed as %s" % disposition)
        elif target == "NON_TARGET" and disposition != "NON_TARGET_OUTCOME":
            flag(line, "TARGET_DISPOSITION_CONTRADICTION",
                 "NON_TARGET requires NON_TARGET_OUTCOME, not %s" % disposition)
        elif target == "NOT_DATA" and disposition not in (
                "NOT_DATA", "DUPLICATE_OR_DECORATIVE"):
            flag(line, "TARGET_DISPOSITION_CONTRADICTION",
                 "NOT_DATA cannot be routed as %s" % disposition)
        elif target == "UNCERTAIN" or disposition == "UNRESOLVED":
            flag(line, "SOURCE_PANEL_UNRESOLVED",
                 "visually classify the panel before execution")

    for sfid, r in source_figure_index.items():
        try:
            observed = _as_int(r.get("Observed_Panel_Count"))
        except (TypeError, ValueError):
            continue
        inventoried = len(source_panels_by_figure.get(sfid, ()))
        if inventoried != observed:
            flag("source_figure:%s" % sfid, "SOURCE_PANEL_COVERAGE_INCOMPLETE",
                 "physical figure has %d visible panels but inventory has %d; "
                 "virtual Figure_ID counts cannot satisfy this gate"
                 % (observed, inventoried))

    # A source-panel label is local to its physical figure.  Duplicate labels
    # within one source figure usually mean the same panel was inventoried twice.
    for sfid, ids in source_panels_by_figure.items():
        labels = [str(source_panel_index[x].get("Panel_Label", "")).strip().upper()
                  for x in ids]
        if len(labels) != len(set(labels)):
            flag("source_figure:%s" % sfid, "DUPLICATE_SOURCE_PANEL_LABEL",
                 "Panel_Label must be unique within a physical figure")

    # -------------------------------------------------------------- panels
    panel_index, panel_mark, mark_by_config = {}, {}, {}
    for i, r in panels.iterrows():
        line = "panels:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        if not pid:
            flag(line, "MISSING_REQUIRED", "Panel_ID")
            continue
        if pid in panel_index:
            flag(line, "DUPLICATE_PANEL_ID", pid)
            continue
        panel_index[pid] = r
        for c in ("Source_Panel_ID", "Figure_ID", "Unit_ID", "Mark_Type", "Image_Path"):
            if blank(r.get(c)):
                flag(line, "MISSING_REQUIRED", c)
        spid = str(r.get("Source_Panel_ID", "")).strip()
        if spid and spid not in source_panel_index:
            flag(line, "SOURCE_PANEL_NOT_IN_INVENTORY", spid)
        elif spid:
            disposition = str(source_panel_index[spid].get(
                "Panel_Disposition", "")).strip().upper()
            if disposition in ("NON_TARGET_OUTCOME", "NOT_DATA",
                               "DUPLICATE_OR_DECORATIVE"):
                flag(line, "RUN_PANEL_CONTRADICTS_DISPOSITION",
                     "%s is linked to a run panel but inventory says %s"
                     % (spid, disposition))
        mark = str(r.get("Mark_Type", "")).strip().upper()
        # An unreleased mark type is NOT a manifest error. The file is correct;
        # the software is behind it. Rejecting the batch would mean one panel
        # nobody can read yet stops every panel that can be - on publication 397
        # that was two line figures blocking twenty-four readable bar cells.
        # It validates, and the RUN gives it NO_READER_AVAILABLE.
        if mark and mark not in BATCH_MARK_TYPES and mark not in UNRELEASED_MARK_TYPES:
            flag(line, "BAD_MARK_TYPE",
                 "Mark_Type=%s (expected %s)" % (mark, "/".join(BATCH_MARK_TYPES)))
        panel_mark[pid] = mark
        mode = str(r.get("Panel_Mode", "")).strip().upper() or "AUTO"
        if mode not in PANEL_MODES:
            flag(line, "BAD_PANEL_MODE",
                 "Panel_Mode=%s (expected %s)" % (mode, "/".join(PANEL_MODES)))
        cid = str(r.get("Config_ID", "")).strip()
        if cid and mark:
            mark_by_config.setdefault(cid, set()).add(mark)

        box = r.get("Panel_X0")
        if all(not blank(r.get(c)) for c in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")):
            try:
                box = parse_box(",".join(str(r.get(c)) for c in
                                         ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")))
            except ValueError as exc:
                flag(line, "BAD_PANEL_BOX", str(exc))
                box = None
        else:
            flag(line, "MISSING_REQUIRED", "Panel_X0/X1/Y0/Y1")
            box = None

        img = resolve(r.get("Image_Path")) if not blank(r.get("Image_Path")) else None
        if check_files and not blank(r.get("Image_Path")) and img is None:
            flag(line, "SOURCE_FILE_NOT_FOUND",
                 "Image_Path=%r is not on disk" % r.get("Image_Path"))
        # The chain the reader is actually going to walk:
        #     panel.Image_Path -> its bytes
        #     panel.Source_Panel_ID -> source_panel.Source_Figure_ID
        #                           -> source_figure.Source_Image_SHA256
        # These were separate declarations that nobody joined, so a panel could
        # read image A while its inventory row, its provenance and its
        # reconciliation all described image B, with every file individually
        # valid. One hash, checked here, is what makes Source_Figure_ID mean
        # something.
        if check_files and img is not None and spid and spid in source_panel_index:
            owning = str(source_panel_index[spid].get("Source_Figure_ID", "")).strip()
            expected = source_figure_sha.get(owning, "")
            if expected:
                actual = sha256_of_file(img)
                if actual != expected:
                    flag(line, "PANEL_IMAGE_NOT_ITS_SOURCE_FIGURE",
                         "Image_Path hashes to %s..., but %s belongs to %s whose "
                         "Source_Image_SHA256 is %s.... The values would be read "
                         "from one raster and attributed to another"
                         % (actual[:16], spid, owning, expected[:16]))
        if check_files and img is not None and box is not None:
            try:
                from PIL import Image as _Image
                w, h = _Image.open(img).size
            except Exception as exc:                              # pragma: no cover
                flag(line, "IMAGE_UNREADABLE", "%s: %s" % (img, exc))
            else:
                if box[1] > w or box[3] > h:
                    flag(line, "PANEL_BOX_OUTSIDE_IMAGE",
                         "box %s exceeds the %dx%d raster" % ((box,), w, h))

        for axis in ("X", "Y"):
            scale = str(r.get("Axis_%s_Scale" % axis, "")).strip().upper()
            ticks = r.get("Axis_%s_Ticks" % axis)
            needed = (axis == "Y") or mark == "SCATTER"
            if blank(ticks):
                if needed:
                    flag(line, "MISSING_AXIS_CALIBRATION",
                         "Axis_%s_Ticks - %s reads values off this axis" % (axis, mark))
                continue
            if scale and scale not in AXIS_SCALES:
                flag(line, "BAD_AXIS_SCALE", "Axis_%s_Scale=%s" % (axis, scale))
            try:
                pairs = parse_ticks(ticks)
            except ValueError as exc:
                flag(line, "BAD_AXIS_CALIBRATION", "Axis_%s_Ticks: %s" % (axis, exc))
                continue
            if scale == "LOG" and any(v <= 0 for v, _ in pairs):
                flag(line, "BAD_AXIS_CALIBRATION",
                     "Axis_%s_Ticks has a non-positive value on a LOG axis" % axis)
            if box is not None:
                lo, hi = (box[0], box[1]) if axis == "X" else (box[2], box[3])
                outside = [px for _, px in pairs if not (lo - 5 <= px <= hi + 5)]
                if outside:
                    flag(line, "CALIBRATION_OUTSIDE_PANEL",
                         "Axis_%s tick pixel(s) %s lie outside the panel box - the "
                         "box and the calibration describe different panels"
                         % (axis, outside))
        if not blank(r.get("Unit_ID")) and unit_index:
            uid = str(r.get("Unit_ID")).strip()
            if uid not in unit_index:
                flag(line, "UNIT_NOT_FOUND",
                     "Unit_ID=%s is not in the unit manifest" % uid)
            else:
                ustat = str(unit_index[uid].get("Statistic_Type", "")).strip().upper()
                # A statistic the validator understands and the runner cannot
                # execute is a sentence, not a discovery halfway through a run.
                if ustat in VALIDATOR_ONLY_STATISTICS and \
                        str(r.get("Panel_Mode", "")).strip().upper() != "MANUAL":
                    flag(line, "UNSUPPORTED_CAPABILITY",
                         "Statistic_Type=%s is %s: %s"
                         % ((ustat,) + CAPABILITY_MATRIX[ustat]))
                if mark == "BOX_VIOLIN" and ustat not in ("QUANTILE_SUMMARY", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "a box/violin yields a five-number summary, but the unit "
                         "declares Statistic_Type=%s" % ustat)
                if mark == "SCATTER" and ustat not in ("ASSOCIATION", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "a scatter yields an association, but the unit declares "
                         "Statistic_Type=%s" % ustat)
                if mark in ("BAR_COLOR", "BAR_MONO", "LINE_COLOR", "LINE_MONO") \
                        and ustat not in ("CONTINUOUS", ""):
                    flag(line, "MARK_TYPE_CONTRADICTS_STATISTIC",
                         "%s yields mean/dispersion, but the unit declares "
                         "Statistic_Type=%s" % (mark, ustat))
        if mark == "SCATTER":
            at = str(r.get("Association_Type", "")).strip().upper()
            if not at:
                flag(line, "MISSING_ASSOCIATION_TYPE",
                     "a scatter panel must declare which association it yields; "
                     "letting the reader default to one means the paper's choice "
                     "of statistic is decided by this file instead (%s)"
                     % "/".join(SCATTER_ASSOCIATION_TYPES))
            elif at not in SCATTER_ASSOCIATION_TYPES:
                flag(line, "BAD_ASSOCIATION_TYPE",
                     "Association_Type=%s (expected %s)"
                     % (at, "/".join(SCATTER_ASSOCIATION_TYPES)))
        elif not blank(r.get("Association_Type")):
            flag(line, "ASSOCIATION_TYPE_NOT_APPLICABLE",
                 "Association_Type is set on a %s panel, which yields no "
                 "association" % mark)

    # -------------------------------------------------------------- series
    # How many series each panel declares, before any reader sees it. Needed
    # because a capability limit is a property of the panel as declared, not
    # something to discover halfway through reading it.
    series_count = {}
    for _, r in series.iterrows():
        series_count[str(r.get("Panel_ID", "")).strip()] = series_count.get(
            str(r.get("Panel_ID", "")).strip(), 0) + 1
    for pid_, r in panel_mark.items():
        if str(r).strip().upper() == "BOX_VIOLIN" and series_count.get(pid_, 0) > 1:
            flag("panel:%s" % pid_, "UNSUPPORTED_CAPABILITY",
                 "BOX_VIOLIN declares %d series. The released reader finds boxes "
                 "at declared x positions and cannot tell overlaid groups apart, "
                 "so the extra series would come out as missing cells rather "
                 "than as an error. Declare one series for the panel, or set "
                 "Panel_Mode=MANUAL until a grouped box reader ships"
                 % series_count[pid_])

    seen_series, factors_by_panel = set(), {}
    for i, r in series.iterrows():
        line = "series:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        sid = str(r.get("Series_ID", "")).strip()
        if not pid or not sid:
            flag(line, "MISSING_REQUIRED", "Panel_ID and Series_ID are required")
            continue
        if pid not in panel_index:
            flag(line, "PANEL_NOT_FOUND", pid)
            continue
        if (pid, sid) in seen_series:
            flag(line, "DUPLICATE_SERIES_ID", "%s/%s" % (pid, sid))
            continue
        seen_series.add((pid, sid))
        mark = panel_mark.get(pid, "")
        if blank(r.get("Factor_Name")) or blank(r.get("Factor_Level")):
            flag(line, "MISSING_SERIES_IDENTITY",
                 "a series without a Factor_Name/Factor_Level cannot become a "
                 "Cell_Key, so its numbers would have nowhere to go")
        else:
            factors_by_panel.setdefault(pid, set()).add(
                str(r.get("Factor_Name")).strip().upper())
        for col, vocab in (("Marker_Shape", MARKER_SHAPES),
                           ("Marker_Fill", MARKER_FILLS),
                           ("Line_Style", LINE_STYLES),
                           ("Bar_Fill_Pattern", BAR_FILL_PATTERNS)):
            v = str(r.get(col, "")).strip().upper()
            if v and v not in vocab:
                flag(line, "BAD_SERIES_%s" % col.upper(),
                     "%s=%s (expected %s)" % (col, v, "/".join(vocab)))
        if mark in COLOUR_MARK_TYPES:
            if mark == "BAR_COLOR":
                if blank(r.get("Mask_Key")) and blank(r.get("Colour_Hex")):
                    flag(line, "MISSING_SERIES_DISCRIMINANT",
                         "BAR_COLOR separates series by colour - give "
                         "Colour_Hex, or Mask_Key for one of the built-in masks")
            elif blank(r.get("Colour_Hex")):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "%s separates series by colour - Colour_Hex required" % mark)
        if not blank(r.get("Colour_Hex")):
            try:
                parse_colour(r.get("Colour_Hex"))
            except ValueError as exc:
                flag(line, "BAD_SERIES_COLOUR", str(exc))
        if mark in UNRELEASED_MARK_TYPES:
            # Still checked, on the rules the reader WOULD use, so the manifest
            # is ready the day the reader ships rather than wrong and unnoticed.
            style = str(r.get("Line_Style", "")).strip().upper()
            if style in ("", "NONE"):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "%s separates series by line style - declare Line_Style"
                     % mark)
        elif mark == "LINE_MONO":
            # The released LINE_MONO reader separates series by MARKER geometry
            # and never looks at Line_Style. Accepting a series declared purely
            # as SOLID-versus-DASHED let a manifest describe a figure the shipped
            # reader cannot read, and the run then matched marks by shape alone -
            # the manifest contract has to say what the reader actually does,
            # not what the module is eventually meant to do.
            shape = str(r.get("Marker_Shape", "")).strip().upper()
            if shape in ("", "NONE"):
                flag(line, "MISSING_SERIES_DISCRIMINANT",
                     "the released LINE_MONO reader separates series by marker "
                     "shape and fill - declare Marker_Shape. Series told apart "
                     "only by SOLID/DASHED need %s, which has no released reader"
                     % "/".join(sorted(UNRELEASED_MARK_TYPES)))
            elif str(r.get("Line_Style", "")).strip().upper() not in ("", "NONE"):
                flag(line, "LINE_STYLE_NOT_READ",
                     "Line_Style is recorded but the released LINE_MONO reader "
                     "does not use it; the series will be matched by marker "
                     "geometry alone. Blank it, or the manifest promises a "
                     "discriminant the run will not apply")
        if mark == "BAR_MONO" and str(r.get("Bar_Fill_Pattern", "")).strip().upper() \
                in ("", "NONE"):
            flag(line, "MISSING_SERIES_DISCRIMINANT",
                 "a monochrome bar series is told apart by its fill pattern - "
                 "Bar_Fill_Pattern required")

    for pid, r in panel_index.items():
        if not any(p == pid for p, _ in seen_series):
            flag("panels:%s" % pid, "PANEL_HAS_NO_SERIES",
                 "nothing declares what the marks in this panel mean")

    linked_source_panels = {
        str(r.get("Source_Panel_ID", "")).strip()
        for _, r in panels.iterrows() if not blank(r.get("Source_Panel_ID"))
    }
    for spid, r in source_panel_index.items():
        disposition = str(r.get("Panel_Disposition", "")).strip().upper()
        if disposition in _RUN_LINK_REQUIRED and spid not in linked_source_panels:
            flag("source_panel:%s" % spid, "SOURCE_PANEL_RUN_LINK_MISSING",
                 "%s requires at least one panel_manifest row" % disposition)

    # Two series of one panel that are told apart by nothing are not two series.
    for pid in panel_index:
        mark = panel_mark.get(pid, "")
        rows = [r for _, r in series.iterrows()
                if str(r.get("Panel_ID", "")).strip() == pid]
        if mark in UNRELEASED_MARK_TYPES:
            keys = [str(r.get("Line_Style", "")).strip().upper() for r in rows]
        elif mark in MONO_MARK_TYPES:
            keys = [(str(r.get("Marker_Shape", "")).strip().upper(),
                     str(r.get("Marker_Fill", "")).strip().upper(),
                     str(r.get("Line_Style", "")).strip().upper(),
                     str(r.get("Bar_Fill_Pattern", "")).strip().upper()) for r in rows]
        elif mark in COLOUR_MARK_TYPES:
            keys = [(str(r.get("Colour_Hex", "")).strip().upper(),
                     str(r.get("Mask_Key", "")).strip().upper()) for r in rows]
        else:
            continue
        if len(keys) != len(set(keys)):
            flag("panels:%s" % pid, "SERIES_NOT_SEPARABLE",
                 "two series in this panel carry identical discriminants, so no "
                 "reader can tell them apart and neither can a reviewer")

    # ------------------------------------------------------------ positions
    seen_pos = set()
    for i, r in positions.iterrows():
        line = "positions:%d" % (i + 2)
        pid = str(r.get("Panel_ID", "")).strip()
        qid = str(r.get("Position_ID", "")).strip()
        if not pid or not qid:
            flag(line, "MISSING_REQUIRED", "Panel_ID and Position_ID are required")
            continue
        if pid not in panel_index:
            flag(line, "PANEL_NOT_FOUND", pid)
            continue
        if (pid, qid) in seen_pos:
            flag(line, "DUPLICATE_POSITION_ID", "%s/%s" % (pid, qid))
            continue
        seen_pos.add((pid, qid))
        if blank(r.get("Factor_Name")) or blank(r.get("Factor_Level")):
            flag(line, "MISSING_POSITION_IDENTITY",
                 "a position without a Factor_Name/Factor_Level cannot become a "
                 "Cell_Key")
        else:
            factors_by_panel.setdefault(pid, set()).add(
                str(r.get("Factor_Name")).strip().upper())
        mark = panel_mark.get(pid, "")
        # `Slot_Index` used to satisfy this on its own, and `_x_positions` only
        # ever passes rows that have an `X_Pixel` - so a Slot_Index-only
        # manifest validated and then reached the reader as an empty position
        # map, which surfaces as an unreadable figure. No released reader is
        # slot-based. Slot_Index stays in the schema as an ordering hint for the
        # day one ships; until then it is not geometry.
        if blank(r.get("X_Pixel")):
            if blank(r.get("Slot_Index")):
                flag(line, "MISSING_POSITION_GEOMETRY", "give X_Pixel")
            else:
                flag(line, "UNSUPPORTED_CAPABILITY",
                     "Slot_Index=%s with no X_Pixel. Every released positional "
                     "reader matches marks to declared pixels; a slot index is "
                     "an ordering hint, and this row would reach the reader as "
                     "no position at all" % r.get("Slot_Index"))
        if not blank(r.get("X_Pixel")):
            try:
                x = float(r.get("X_Pixel"))
            except (TypeError, ValueError):
                flag(line, "BAD_X_PIXEL", "X_Pixel=%r" % r.get("X_Pixel"))
            else:
                row = panel_index[pid]
                try:
                    box = parse_box(",".join(str(row.get(c)) for c in
                                             ("Panel_X0", "Panel_X1",
                                              "Panel_Y0", "Panel_Y1")))
                except ValueError:
                    box = None
                if box is not None and not (box[0] <= x <= box[1]):
                    flag(line, "POSITION_OUTSIDE_PANEL",
                         "X_Pixel=%g is outside the panel box x range %d-%d"
                         % (x, box[0], box[1]))
        if not blank(r.get("Timepoint_Days")):
            try:
                float(r.get("Timepoint_Days"))
            except (TypeError, ValueError):
                flag(line, "BAD_TIMEPOINT_DAYS", "%r" % r.get("Timepoint_Days"))
        if mark == "SCATTER":
            flag(line, "POSITION_NOT_APPLICABLE",
                 "a scatter's x is data, not a declared position; delete this row "
                 "or the reader will be given a grid it does not use")

    for pid, mark in panel_mark.items():
        if mark in UNRELEASED_MARK_TYPES and not any(p == pid for p, _ in seen_pos):
            flag("panels:%s" % pid, "PANEL_HAS_NO_POSITIONS",
                 "%s will read at declared x positions and none are declared"
                 % mark)
        if mark in POSITIONAL_MARK_TYPES and not any(p == pid for p, _ in seen_pos):
            flag("panels:%s" % pid, "PANEL_HAS_NO_POSITIONS",
                 "%s reads at declared x positions and none are declared" % mark)

    # A factor cannot be both the series axis and the position axis of one panel.
    for pid in panel_index:
        s_factors = {str(r.get("Factor_Name", "")).strip().upper()
                     for _, r in series.iterrows()
                     if str(r.get("Panel_ID", "")).strip() == pid
                     and not blank(r.get("Factor_Name"))}
        p_factors = {str(r.get("Factor_Name", "")).strip().upper()
                     for _, r in positions.iterrows()
                     if str(r.get("Panel_ID", "")).strip() == pid
                     and not blank(r.get("Factor_Name"))}
        overlap = sorted(s_factors & p_factors)
        if overlap:
            flag("panels:%s" % pid, "FACTOR_ON_BOTH_AXES",
                 "%s labels both the series and the positions of this panel; the "
                 "Cell_Key would carry it twice" % ", ".join(overlap))
        if len(s_factors) > 1:
            flag("panels:%s" % pid, "SERIES_FACTOR_INCONSISTENT",
                 "the series of one panel name %d different factors (%s)"
                 % (len(s_factors), ", ".join(sorted(s_factors))))
        if len(p_factors) > 1:
            flag("panels:%s" % pid, "POSITION_FACTOR_INCONSISTENT",
                 "the positions of one panel name %d different factors (%s)"
                 % (len(p_factors), ", ".join(sorted(p_factors))))

    # -------------------------------------------------------------- configs
    parsed = load_reader_configs(configs, mark_by_config, flag)
    for pid, r in panel_index.items():
        cid = str(r.get("Config_ID", "")).strip()
        if cid and cid not in parsed:
            flag("panels:%s" % pid, "CONFIG_NOT_FOUND",
                 "Config_ID=%s has no rows in reader_config" % cid)

    return pd.DataFrame(problems)


def config_hash(configs):
    """Stable digest of the option table, for the run's reproducibility stamp."""
    rows = sorted(
        (str(r.get("Config_ID", "")).strip(), str(r.get("Option", "")).strip(),
         str(r.get("Value", "")).strip())
        for _, r in configs.iterrows())
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
