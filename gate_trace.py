# -*- coding: utf-8 -*-
"""Where each component went, and what refused it.

Named `gate_trace` and not `trace`: the standard library owns that name, and a
module in the package directory shadowing it is a defect waiting for the first
import that wanted the other one.

    TRACE=trace.csv python3 propose.py

The overlay draws one red box for three different failures - a refused ladder, a
fragment flag, and a vertical that is not an axis promoted to a panel - and the
footer counts two of them. So a picture of publication 475's figure 1 shows that
the harness failed and not WHERE, and the four rounds before this one were spent
guessing at that difference. `VERT` was the clearest case: it was recorded as "no
effect" twice, and the second reading showed it had never reached the six
statements at all.

Nothing here decides anything. With `TRACE` unset every function is a branch not
taken, so the pipeline's output is byte-identical - `harness_compare` is how that
is checked rather than asserted. What it records is:

    AXIS_CANDIDATES   every long vertical the anchor search saw, which one it
                      took, and why - so "the blue line is on an error bar"
                      becomes a row that names the column it should have taken
    ORPHAN            every piece the cut discarded, and whether it was OFFERED
                      to the six statements or refused before them, with the
                      refusal named
    GATE              the six verdicts for a piece that was offered
    POST              what happened to an accepted piece afterwards
    SELECTED          the rows that survived into the proposal

A refusal BEFORE the gate and a refusal BY the gate are different repairs, and
until they are separate rows the harness cannot tell which one it is looking at.
"""
import collections
import csv
import os

#: TRACE names the file to write, so its VALUE is a path and emptiness is the
#: only sensible off - but "TRACE=0" would then write a file called "0", which is
#: not what anyone means by it.
ON = os.environ.get("TRACE", "") not in ("", "0")
PATH = (os.environ.get("TRACE") if ON else "") or "trace.csv"
ROWS = []
CTX = {"pid": "", "fig": "", "png": "", "mode": "", "ink": ""}

#: Kinds, in the order a component meets them.
KINDS = ("CUT", "REGION", "AXIS_CANDIDATES", "AXIS_FALLBACK", "AXIS_SHADOW_LADDER",
         "ORPHAN", "PIECE_RELATION", "GATE", "GATE_WHY", "GATE_SHADOW",
         "GATE_SHADOW_WHY", "RESIDUAL_SHADOW", "RESIDUAL_COMPONENT",
         "Y_SCALE_GROUP", "Y_SCALE_MEMBER", "TICK_OCR", "TICK_OCR_LADDER",
         "POST_ADOPTION_SHADOW", "POST",
         "FRAGMENT_DECISION", "SELECTED_PASS", "SELECTED")

#: THREE QUESTIONS, THREE ANSWERS. The single `axis_status` mixed them, and on
#: publication 177's figure 2 the mixture measured the figure's LAYOUT: a panel
#: whose box and spine are both right, printed in a grid that labels its y axis
#: once per row, came back as AXIS_GEOMETRY_ONLY - which reads as a defect and is
#: not one. Reported, never acted on; promoting or demoting a box on any of these
#: is a change to what the pipeline returns and belongs to its own arm.
#:
#: HOW THE SPINE COLUMN WAS ARRIVED AT. Nothing here about numerals.
ANCHOR_FREE = "ANCHOR_FREE"                  # a run ending inside the box was taken
ANCHOR_CLIPPED = "ANCHOR_CLIPPED"            # only runs cut by the box's edges existed
FALLBACK_LONGEST = "FALLBACK_LONGEST"        # no anchor; the plain longest vertical
GEOMETRY_UNRESOLVED = "GEOMETRY_UNRESOLVED"  # no spine column at all
GEOMETRY_UNOBSERVED = "GEOMETRY_UNOBSERVED"  # no candidate row for this box in this pass

#: WHERE THE VALUE MAPPING COMES FROM. `SHARED_ROW` is PROPOSED by the
#: `Y_SCALE_GROUP` shadow and is never written here; `MANUAL` is human-only and
#: nothing in this package may write it - see PILOT.md.
LOCAL_LADDER = "LOCAL_LADDER"
SHARED_ROW = "SHARED_ROW"
CALIBRATION_NONE = "NONE"
CALIBRATION_MANUAL = "MANUAL"

#: WHETHER THE BOX IS THE WHOLE PANEL.
COMPLETE = "COMPLETE"
FRAGMENT = "FRAGMENT"
COMPLETENESS_UNKNOWN = "UNKNOWN"

#: The old composite, kept only so that the one attested state has a name that
#: says what it is attested BY. `AXIS_ATTESTED` was read as "this axis is good".
LOCAL_LADDER_ATTESTED = "LOCAL_LADDER_ATTESTED"


def axis_geometry(n_free, n_clipped, anchored, spine=True, observed=True):
    """How the spine column was found. INDEPENDENT OF THE LADDER.

    `anchored` is whether `_axis_anchor` returned anything at all; when it did
    not, the spine came from the plain longest-vertical fallback and that is a
    different fact from a badly chosen candidate. A box whose every candidate is
    cut by its own edges is the weakest case - publication 475's figure 1
    promotes one to a panel - and it is named so that it can be counted before
    anything is done about it.

    THE LADDER IS NOT AN ARGUMENT HERE, and that absence is the whole point of the
    split: the same geometry must give the same answer whether or not the figure
    printed numerals beside it. `spine` separates "the fallback answered" from
    "there is no axis here at all", and `observed` separates both from "this box
    has no candidate row in this pass" - a join that found nothing, which must not
    be reported as a measurement that found nothing.
    """
    if not spine:
        return GEOMETRY_UNRESOLVED
    if not observed:
        return GEOMETRY_UNOBSERVED
    if not anchored:
        return FALLBACK_LONGEST
    return ANCHOR_FREE if n_free else ANCHOR_CLIPPED


def calibration_method(ladder_ok):
    """Where this panel's value mapping came from.

    Only two of the four values can be reached from inside a single panel:
    it read its own numerals, or it did not. `SHARED_ROW` needs another panel
    and is proposed by a shadow; `MANUAL` needs a person.
    """
    return LOCAL_LADDER if ladder_ok else CALIBRATION_NONE


def completeness(fragment_flags, measured=True):
    if not measured:
        return COMPLETENESS_UNKNOWN
    return FRAGMENT if fragment_flags else COMPLETE


def context(**kw):
    CTX.update({k: ("" if v is None else v) for k, v in kw.items()})


def reset():
    del ROWS[:]


def add(kind, **fields):
    if not ON:
        return
    row = dict(CTX)
    row["kind"] = kind
    for k, v in fields.items():
        row[k] = "" if v is None else v
    ROWS.append(row)


def box(b):
    return "%d,%d,%d,%d" % tuple(int(v) for v in b) if b is not None else ""


def dump(path=None):
    """One CSV, columns in a stable order, `kind` deciding what a row means."""
    if not ON:
        return None
    path = path or PATH
    order = ["pid", "fig", "png", "mode", "ink", "kind"]
    rest = []
    for r in ROWS:
        for k in r:
            if k not in order and k not in rest:
                rest.append(k)
    cols = order + rest
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for r in ROWS:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


def last(kind, **match):
    """The most recent row of `kind` matching every given field, or None.

    The SELECTED row is written after the search that produced it, and the two
    have to be joined on the box. Joining in the reader instead would mean every
    consumer of the trace re-deriving which pass a row belongs to.
    """
    for row in reversed(ROWS):
        if row.get("kind") != kind:
            continue
        if all(str(row.get(k, "")) == str(v) for k, v in match.items()):
            return row
    return None


def last_in_pass(kind, **match):
    """`last`, restricted to the pass the CONTEXT names.

    `last` matches on the fields it is given and nothing else, so a box value
    that two modes both produced is joined to whichever mode wrote it LAST -
    which is the last one iterated, not the one that won. The SELECTED row's
    axis status was being read that way: the row said OFF because the context
    said OFF, and the candidate count behind it could have come from GRID. The
    same defect as the mislabelled SELECTED rows, one join further down.

    Every context field that is set is part of the match, `png` and `fig`
    included: two figures in one run share mode and ink, and can share a box.
    """
    ctx = {k: v for k, v in CTX.items() if v != ""}
    ctx.update(match)
    return last(kind, **ctx)


def summary():
    """Counts per kind and per outcome, for a person reading a terminal."""
    if not ROWS:
        return "TRACE: nothing recorded"
    per = collections.Counter(r["kind"] for r in ROWS)
    out = ["TRACE: " + ", ".join("%s %d" % (k, per[k]) for k in KINDS if per[k])]
    ref = collections.Counter(r.get("outcome", "") for r in ROWS if r["kind"] == "ORPHAN")
    if ref:
        out.append("  orphan outcomes: " + ", ".join(
            "%s %d" % (k or "?", v) for k, v in sorted(ref.items(), key=lambda t: -t[1])))
    return "\n".join(out)
