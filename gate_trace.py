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

ON = bool(os.environ.get("TRACE"))
PATH = os.environ.get("TRACE") or "trace.csv"
ROWS = []
CTX = {"pid": "", "fig": "", "png": "", "mode": "", "ink": ""}

#: Kinds, in the order a component meets them.
KINDS = ("CUT", "AXIS_CANDIDATES", "AXIS_FALLBACK", "AXIS_SHADOW_LADDER",
         "ORPHAN", "GATE", "GATE_WHY", "GATE_SHADOW", "GATE_SHADOW_WHY", "POST",
         "FRAGMENT_DECISION", "SELECTED_PASS", "SELECTED")

#: How well defended the axis a row was measured on actually is. REPORTED, never
#: acted on: promoting or demoting a box on this is a change to what the pipeline
#: returns and belongs to its own arm.
AXIS_ATTESTED = "AXIS_ATTESTED"            # a candidate whose ladder reads
AXIS_GEOMETRY_ONLY = "AXIS_GEOMETRY_ONLY"  # looks like an axis, no ladder behind it
AXIS_FALLBACK_ONLY = "AXIS_FALLBACK"       # no candidate passed; longest vertical
AXIS_UNRESOLVED = "AXIS_UNRESOLVED"        # every candidate cut by the box's edges


def axis_status(n_free, n_clipped, anchored, ladder_ok):
    """The four states the overlay had been drawing as one blue line.

    `anchored` is whether `_axis_anchor` returned anything at all; when it did
    not, the spine came from the plain longest-vertical fallback and that is a
    different fact from a badly chosen candidate. A box whose every candidate is
    cut by its own edges is the weakest case of all - publication 475's figure 1
    promotes one to a panel - and it is named so that it can be counted before
    anything is done about it.
    """
    if not anchored:
        return AXIS_FALLBACK_ONLY
    if n_free == 0 and n_clipped > 0:
        return AXIS_UNRESOLVED
    return AXIS_ATTESTED if ladder_ok else AXIS_GEOMETRY_ONLY


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
