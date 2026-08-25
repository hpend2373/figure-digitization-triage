"""One proposal row per detected panel, for every digitize-family figure.

Three things happen here that the shipped proposer does not do.

  A SEGMENTATION SEARCH. No single rule for "is this whitespace band interior to a
  panel" is right on 187 heterogeneous figures, so all three are tried and the one
  whose panel count equals the number of axes I counted BY EYE is kept. The count
  is an independent, human-authored number, which is what makes choosing on it a
  measurement rather than a fit. Where no mode matches it, the tie is broken by the
  number of validated tick ladders and then by preferring the merged reading.

  A FRAGMENT TEST. A box that cuts through its own axis, or a set of boxes that
  together cover almost none of the figure, is not a panel set. Those are flagged
  and are not offered for digitizing, because a correct tick ladder on a box a
  third of the plot wide is the worst kind of wrong.

  THE X AXIS, three ways, with a cross-check between two of them.

Everything emitted is PROPOSED. Nothing here writes a confirmation.
"""
import csv, os, collections
import numpy as np
from PIL import Image
import axis_reader as A
import gate_trace as T
import panel_geometry as PG
import x_reader as X

MODES = ("OFF", "PLAIN", "CAP", "GRID")
FRAGMENT_AREA_SHARE = 0.25   # panels covering less than this of the raster are pieces

# The three corpus tables this driver reads are NOT in the repository - they are
# the worklist, the clip index and the caption scan of a particular 187-figure
# corpus. Named here rather than hard-coded so the driver is pointable at another
# one; `axis_reader`, `x_reader` and `continuity` need none of them.
DIG = os.environ.get("DIG", "dig201.csv")        # pid, fig, declared axis count
CLIPS = os.environ.get("CLIPS", "clips201.csv")  # pid, fig, png, status
CAPS = os.environ.get("CAPS", "captions.csv")    # written by capscan.py

figs = {(r["pid"], r["fig"]): r for r in csv.DictReader(open(DIG))}
# THE FIGURE'S OWN STATEMENT OF ITS PANELS, read once by `capscan.py`.
caps = {}
if os.path.exists(CAPS):
    for _r in csv.DictReader(open(CAPS)):
        caps[(_r["pid"], _r["fig"])] = _r
rows = [r for r in csv.DictReader(open(CLIPS)) if r["status"] == "READ"]
_only = os.environ.get("FIGS")
if _only:
    _keys = {tuple(t.split("|")) for t in _only.split(";") if t.strip()}
    rows = [r for r in rows if (r["pid"], r["fig"]) in _keys]

REINK = os.environ.get("REINK", "1") != "0"   # harness: the figure states its own ink
NEAR = os.environ.get("NEAR", "1") != "0"     # harness: you cannot read more axes than the figure has


_cache = {}
def measure(png, img, dark, box, kind):
    key = (png, box, A.INK)
    if key in _cache:
        rec = dict(_cache[key]); rec["kind"] = kind; return rec
    rec = dict(x0=box[0], x1=box[1], y0=box[2], y1=box[3], kind=kind)
    sx, by = A.spine_and_baseline(dark, box)
    anchor = A.axis_anchor(dark, box) if A.CAP else None
    if anchor is not None and abs(anchor[0] - sx) > 3:
        sx = anchor[0]
        by = A.baseline_at(dark, box, sx)
        rec["anchor"] = "AXIS_REANCHORED: the longest vertical in this box is clipped by " \
                        "its own edge, so the axis was taken from the run at x=%d that " \
                        "ends inside it" % sx
    pairs = A.y_tick_labels(img, dark, box, sx, by)
    ok, detail, _f, _l, resid, cv = A.ladder(pairs)
    brk = ""
    if ok and pairs:
        lo = min(p[1] for p in pairs); hi = max(p[1] for p in pairs)
        step = (hi - lo) / max(1, len(pairs) - 1)
        if by - hi > 1.5 * step:
            brk = "AXIS_BREAK_SUSPECT: baseline is %.0f px below the lowest label, %.1f tick steps" % (by - hi, (by - hi) / step)
    cut = A.axis_break(dark, box, sx)
    if cut is not None:
        brk = ((brk + "; ") if brk else "") + (
            "AXIS_BREAK: the spine is cut at rows %d-%d, so the ladder covers only the "
            "segment above it and Baseline_Value must not be assumed 0 at the baseline" % cut)
    tk = X.tick_marks(dark, box, sx, by)
    xl = X.x_tick_labels(img, dark, box, sx, by)
    xok, xdet, _xr, _xc = X.x_ladder(xl)
    hit, hdet = X.labels_over_ticks(xl, tk)
    bars = X.bar_centres(dark, box, sx, by)
    if xok and hit:      xstatus = "X_CALIBRATED"
    elif xok:            xstatus = "X_LADDER_ONLY"
    elif len(bars) >= 2: xstatus = "X_BAR_POSITIONS"
    elif len(tk) >= 2:   xstatus = "X_MARKS_ONLY"
    else:                xstatus = "X_NOT_READ"
    rec.update(spine_x=sx, baseline_y=by, n_labels=len(pairs),
               ticks=";".join("%g:%g" % (v, round(px, 1)) for v, px in pairs),
               status="LADDER_OK" if ok else "LADDER_REFUSED", detail=detail, flag=brk,
               resid_px=("%.2f" % resid) if resid is not None else "",
               spacing_cv=("%.4f" % cv) if cv is not None else "",
               cut_through=A.cut_through_axis(dark, box, sx, by),
               x_status=xstatus, n_xticks=len(tk), n_xlabels=len(xl),
               x_ticks=";".join("%g:%g" % (v, round(c, 1)) for v, c in xl),
               x_marks=";".join("%g" % round(t, 1) for t in tk),
               n_bars=len(bars),
               bar_centres=";".join("%g" % round(b[1], 1) for b in bars),
               bar_widths=";".join("%g" % (b[2] - b[0] + 1) for b in bars),
               x_detail=xdet + " | " + hdet)
    _cache[key] = dict(rec)
    return rec


def _y_overlap(a, b):
    """Share of the shorter box's height that the two boxes have in common."""
    lo = max(a.get("y0", 0), b.get("y0", 0))
    hi = min(a.get("y1", 0), b.get("y1", 0))
    short = min(a.get("y1", 0) - a.get("y0", 0), b.get("y1", 0) - b.get("y0", 0))
    return (hi - lo) / short if short > 0 else 0.0


def _same_baseline(a, b, tol=3):
    """Do these two rows stand on one x axis, in one column of the figure?"""
    try:
        by1, by2 = float(a["baseline_y"]), float(b["baseline_y"])
    except (TypeError, ValueError, KeyError):
        return False
    if abs(by1 - by2) > tol:
        return False
    xov = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    xsh = min(a["x1"] - a["x0"], b["x1"] - b["x0"])
    return xsh > 0 and xov / xsh > 0.5 and _y_overlap(a, b) > 0.5


def collapse_same_axis(dark, recs):
    """One axis line is one panel. Keep the row that MEASURED best on it."""
    keyed = []
    for rec in recs:
        sx = rec.get("spine_x")
        run = None
        if sx is not None and rec.get("y0") is not None:
            try:
                run = A.spine_run(dark, sx, rec["y0"], rec["y1"])
            except Exception:
                run = None
        keyed.append((rec, sx, run))

    def _rank(t):
        rec = t[0]
        area = ((rec.get("x1") or 0) - (rec.get("x0") or 0)) * \
               ((rec.get("y1") or 0) - (rec.get("y0") or 0))
        return (rec.get("status") == "LADDER_OK", rec.get("n_labels") or 0, area)
    keyed.sort(key=_rank, reverse=True)
    kept = []
    for rec, sx, run in keyed:
        if run is None or sx is None:
            kept.append((rec, sx, run)); continue
        if any(orun is not None and osx is not None
               and abs(osx - sx) <= 3 and abs(orun[0] - run[0]) <= 3
               and abs(orun[1] - run[1]) <= 3
               and min(o["x1"], rec["x1"]) - max(o["x0"], rec["x0"]) > 0
               and _y_overlap(o, rec) > 0.5
               for o, osx, orun in kept):
            continue
        # SAME BASELINE, SAME PANEL. Stacked panels differ in baseline, side-by-side
        # panels do not overlap in x, and an inset has its own baseline.
        if A.BROAD and any(_same_baseline(o, rec) for o, _osx, _orun in kept):
            continue
        kept.append((rec, sx, run))
    return [rec for rec, _sx, _run in kept]


out = []
for r in rows:
    p = os.path.join("clips", r["png"])
    declared = int((figs.get((r["pid"], r["fig"])) or {}).get("axes") or 0)
    try:
        img = Image.open(p)
        grey = np.asarray(img.convert("L"))
        _a, dark = A._dark(img)
        area = float(dark.shape[0] * dark.shape[1])
    except Exception as exc:
        out.append(dict(pid=r["pid"], fig=r["fig"], png=r["png"], panel="", status="OPEN_FAILED",
                        detail="%s: %s" % (type(exc).__name__, exc)))
        continue
    T.context(pid=r["pid"], fig=r["fig"], png=r["png"])
    cap = caps.get((r["pid"], r["fig"]), {})
    A.CAP_FLOOR = int(cap["cap_y"]) if cap.get("cap_y") else None
    cap_panels = cap.get("panels") or ""
    A.FIG_TARGET = max(len(cap_panels), declared)
    best = None
    figure_refusals = {}
    # THE SECOND THRESHOLD IS ASKED ONLY OF A FIGURE THAT CAME UP SHORT, and asked
    # the same way: all four modes, same score, ladder still deciding.
    inks = [A.INK_DEFAULT]
    if REINK:
        _t = A.figure_ink(grey)
        if _t != A.INK_DEFAULT:
            inks.append(_t)
    for ink in inks:
        A.INK = ink
        if ink != A.INK_DEFAULT:
            if best is not None and best[0][0]:
                break                      # a mode already matched; nothing to ask
            _a, dark = A._dark(img)
        for mode in MODES:
            A.SEVER_MODE = mode
            T.context(mode=mode, ink=ink)
            try:
                boxes, _d, loose = A.panels(p, loose=True)
            except Exception as exc:
                continue
            # A MODE THAT SHREDS THE FIGURE CANNOT BE THE RIGHT MODE, and measuring its
            # cells costs exactly what measuring real ones costs. The selection below
            # would never pick it - it prefers the count matching the axes I counted by
            # eye, then fewer panels - so evaluating it is pure cost. GRID can emit 24
            # cells for a six-panel plate; skipping those took the run from an hour and
            # three quarters back to half an hour.
            tags = dict(A.HARNESS_TAG)
            figure_refusals[(ink, mode)] = list(A.FIGURE_BOXES)
            # THE GATE COUNTS WHAT THE CUT PRODUCED, NOT WHAT THE HARNESS PUT BACK.
            _added = ("EXTENDED_TO_SPINE", "ADOPTED_ORPHAN")
            n_cut = sum(1 for b in boxes + loose
                        if not tags.get(tuple(b), "").startswith(_added))
            if declared and n_cut > 3 * declared:
                continue
            cand = [(b, "") for b in boxes] + [(b, "Y_AXIS_ONLY") for b in loose]
            recs = []
            for b, kind in cand:
                try:
                    rec = measure(r["png"], img, dark, b, kind)
                except Exception as exc:
                    rec = dict(x0=b[0], x1=b[1], y0=b[2], y1=b[3], kind=kind,
                               status="MEASURE_FAILED",
                               detail="%s: %s" % (type(exc).__name__, exc))
                if kind == "Y_AXIS_ONLY" and rec.get("status") != "LADDER_OK":
                    continue
                note = tags.get(tuple(b), "")
                if rec.get("anchor"):
                    note = (note + " | " if note else "") + rec["anchor"]
                rec["harness"] = note
                recs.append(rec)
            if A.SNAP:
                recs = collapse_same_axis(dark, recs)
            n_ok = sum(1 for x in recs if x.get("status") == "LADDER_OK")
            # A COUNT MATCH THAT READS NOTHING IS NOT EVIDENCE.
            matched = bool(declared and len(recs) == declared and (n_ok or not A.BROAD))
            score = A.mode_score(matched, n_ok, len(recs), declared, near=NEAR)
            if os.environ.get("SCOREDEBUG"):
                print("   ink=%-4s %-6s recs=%-3d n_ok=%-3d matched=%s score=%s"
                      % (ink, mode, len(recs), n_ok, matched, score))
            if best is None or score > best[0]:
                best = (score, mode, recs, ink)
    A.INK = A.INK_DEFAULT
    if best is None or not best[2]:
        out.append(dict(pid=r["pid"], fig=r["fig"], png=r["png"], panel="", status="NO_PANEL",
                        detail="no mode of the cut produced a block holding an axis"))
        continue
    score, mode, recs, ink = best
    # THE CONTEXT MUST NAME THE PASS THAT WON, not the last one iterated. The first
    # trace of publication 475's figure 1 labelled its SELECTED rows GRID at ink 151
    # because that was simply the last combination tried, and the run had chosen OFF
    # at 140. A trace that mislabels which pass it is describing is worse than none.
    T.context(mode=mode, ink=ink)
    if T.ON:
        T.add("SELECTED_PASS", score=str(score), n_rows=len(recs))
    ink_note = ("" if ink == A.INK_DEFAULT else
                "RE_INKED: at the shipped threshold this figure came up short of the "
                "%d axes recorded for it, so it was cut again at the grey the figure "
                "itself separates from its paper (%d, not %d)"
                % (declared, ink, A.INK_DEFAULT))
    # THE REFUSED FIGURE BOX IS STILL REPORTED.
    for _b, _why in figure_refusals.get((ink, mode), []):
        out.append(dict(pid=r["pid"], fig=r["fig"], png=r["png"], panel="",
                        x0=_b[0], x1=_b[1], y0=_b[2], y1=_b[3],
                        status="FIGURE_BOX_REFUSED", sever_mode=mode,
                        declared_axes=declared, harness=_why, detail=_why))
    harness_hits = sum(1 for x in recs if x.get("harness"))
    covered = sum((x["x1"] - x["x0"]) * (x["y1"] - x["y0"]) for x in recs) / area
    # THE THREE BOXES ARE DERIVED, NOT DECIDED. `panel_geometry` reads the raster
    # at the ink the winning mode used - `dark` in scope here belongs to whichever
    # ink was tried LAST, which is not always the one that won - and writes only
    # into new columns. Nothing above this line can see any of it.
    try:
        A.INK = ink
        _ga, gdark = A._dark(img)
    finally:
        A.INK = A.INK_DEFAULT
    # THE BOUND IS THE NEIGHBOUR'S EDGE, NOT ITS AXIS. A panel to the left ends
    # at its right-hand edge; stopping at its spine hands its plot to the panel
    # next door.
    others = [(x["x0"], x["x1"], x["y0"], x["y1"]) for x in recs]
    for i, rec in enumerate(sorted(recs, key=lambda x: (x["y0"], x["x0"])), 1):
        frag = []
        if rec.get("cut_through"):
            frag.append(rec["cut_through"])
        if covered < FRAGMENT_AREA_SHARE:
            frag.append("panels cover only %.0f%% of the raster" % (100 * covered))
        if ink_note:
            rec["harness"] = (rec.get("harness") + " | " if rec.get("harness") else "") + ink_note
        if rec.get("spine_x") is not None and rec.get("baseline_y") is not None:
            try:
                mine = (rec["x0"], rec["x1"], rec["y0"], rec["y1"])
                nb = [o for o in others if o != mine]
                rec.update(PG.as_columns(PG.geometry(
                    gdark, mine, rec["spine_x"], rec["baseline_y"],
                    floor=A.CAP_FLOOR, neighbours=nb,
                    ticks=rec.get("ticks", ""))))
            except Exception as exc:
                # A REPORTING COLUMN MAY NOT END A RUN. It may not go quiet
                # either: an empty cell and no reason is how a column stops
                # being read.
                rec["geom_note"] = "GEOMETRY_FAILED: %s: %s" % (type(exc).__name__, exc)
        if T.ON:
            T.add("SELECTED", panel="P%02d" % i, box=T.box((rec["x0"], rec["x1"],
                                                            rec["y0"], rec["y1"])),
                  spine_x=rec.get("spine_x"), baseline_y=rec.get("baseline_y"),
                  status=rec.get("status"), n_labels=rec.get("n_labels"),
                  n_bars=rec.get("n_bars"), fragment="; ".join(frag),
                  source=(rec.get("harness") or "").split(":")[0])
        rec.update(pid=r["pid"], fig=r["fig"], png=r["png"], panel="P%02d" % i,
                   sever_mode=mode, ink=ink, declared_axes=declared,
                   caption_panels=cap_panels, caption_row=(A.CAP_FLOOR if A.CAP_FLOOR else ""),
                   area_share="%.2f" % covered,
                   fragment="; ".join(frag))
        out.append(rec)

cols = ["pid", "fig", "png", "panel", "kind", "sever_mode", "ink", "declared_axes",
        "caption_panels", "caption_row",
        "x0", "x1", "y0", "y1", "spine_x", "baseline_y", "n_labels", "ticks",
        "resid_px", "spacing_cv", "status", "flag", "fragment", "area_share",
        "detail", "x_status", "n_xticks", "n_xlabels", "x_ticks", "x_marks",
        "n_bars", "bar_centres", "bar_widths", "x_detail", "harness",
        # ADDITIVE, and measured to be so. `x0/x1/y0/y1` above stay exactly what
        # they were - `harness_compare` reports zero shared-column mismatches
        # across this change - and these say which PART of that box each
        # consumer should be reading.
        "plot_x0", "plot_x1", "plot_y0", "plot_y1",
        "label_x0", "label_x1", "label_y0", "label_y1", "label_side",
        "numeral_x0", "numeral_x1",
        "review_x0", "review_x1", "review_y0", "review_y1",
        "axis_sig", "ladder_sig", "geom_note"]
with open(os.environ.get("OUT", "proposals.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for rec in out:
        w.writerow({c: rec.get(c, "") for c in cols})
print("figures %d -> panel rows %d" % (len(rows), len(out)))
print(dict(collections.Counter(x["status"] for x in out)))
print(dict(collections.Counter(x.get("x_status", "") for x in out)))
print("mode chosen:", dict(collections.Counter(x.get("sever_mode", "") for x in out if x["panel"])))
print("count matched declared axes on %d figures"
      % len({(x["pid"], x["fig"]) for x in out if x["panel"] and x.get("declared_axes")
             and len([y for y in out if y["png"] == x["png"] and y["panel"]]) == x["declared_axes"]}))
print("fragment-flagged panels:", sum(1 for x in out if x.get("fragment")))
if T.ON:
    print(T.summary())
    print("trace written:", T.dump())
