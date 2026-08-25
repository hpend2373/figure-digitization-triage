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
KINDS = ("AXIS_CANDIDATES", "ORPHAN", "GATE", "POST", "SELECTED")


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
