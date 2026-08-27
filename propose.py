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
import y_scale_group as YG
import tick_ocr as TO
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
# AND WHERE THE CLIPS THEMSELVES ARE. This was the literal "clips", resolved
# against whatever the working directory happened to be - so a caller that had
# the corpus somewhere else got `OPEN_FAILED` rows and an exit code of 0.
CLIP_ROOT = os.environ.get("CLIP_ROOT", "clips")

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
# SHADOW: read a ladder off EVERY axis candidate, not just the one the search took,
# and record all of them. Reported only - production still uses the chosen axis.
# Separate from TRACE because it pays for OCR per candidate.
SHADOW = os.environ.get("SHADOW", "0") != "0" and T.ON


def _shadow_ladders(img, dark, box, chosen_x):
    """Read a ladder off every axis candidate this box had, and record them all.

    Production takes the leftmost run that ends inside the box, preferring those
    over ones clipped by the box edge. On publication 475's figure 1's panel D
    that preference picks a short vertical standing on a bar over the panel's own
    axis, which is clipped by the box's bottom edge - and nothing measured whether
    the rejected candidate would have read better. This measures it and CHANGES
    NOTHING: what the arm needs first is the evidence that the ranking is wrong.
    """
    ac = T.last("AXIS_CANDIDATES", box=T.box(box))
    fb = T.last("AXIS_FALLBACK", box=T.box(box))
    cands = []
    if ac and ac.get("candidates"):
        for c in str(ac["candidates"]).split(";"):
            if not c:
                continue
            cx, run, cls = c.split(":")
            cands.append((int(cx), cls, run))
    if fb and fb.get("selected_x") != "":
        cands.append((int(fb["selected_x"]), "fallback", ""))
    seen = set()
    for cx, cls, run in cands:
        if cx in seen:
            continue
        seen.add(cx)
        try:
            cby = A.baseline_at(dark, box, cx)
            cp = A.y_tick_labels(img, dark, box, cx, cby)
            cok, cdet, _cf, _cl, cres, ccv = A.ladder(cp)
        except Exception as exc:
            T.add("AXIS_SHADOW_LADDER", box=T.box(box), candidate_x=cx,
                  boundary=cls, run=run, chosen=(cx == chosen_x),
                  ladder_ok="", n_labels="", detail="%s: %s" % (type(exc).__name__, exc))
            continue
        T.add("AXIS_SHADOW_LADDER", box=T.box(box), candidate_x=cx, boundary=cls,
              run=run, chosen=(cx == chosen_x), baseline_y=cby,
              n_labels=len(cp), ladder_ok=bool(cok),
              resid_px=("%.2f" % cres) if cres is not None else "",
              spacing_cv=("%.4f" % ccv) if ccv is not None else "",
              detail=cdet)


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
    if SHADOW:
        _shadow_ladders(img, dark, box, sx)
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
    p = os.path.join(CLIP_ROOT, r["png"])
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
    # THE DAG BELONGS TO A PASS. `panels()` clears it per call, so after the loop
    # it holds whatever the LAST mode produced - and 475 figure 1 wins on OFF and
    # ends on GRID. Kept per pass and put back for the one that won.
    region_snap = {}
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
            if T.ON:
                region_snap[(ink, mode)] = A.snapshot_regions()
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
        A.restore_regions(region_snap.get((ink, mode)))
        T.add("SELECTED_PASS", score=str(score), n_rows=len(recs),
              n_regions=len(A.REGIONS))
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
    # THE PANELS AS THE Y SCALE GROUP SHADOW NEEDS THEM, filled in as the SELECTED
    # rows are written and handed over once, after the loop.
    ygroup = []
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
            if T.ON:
                T.add("FRAGMENT_DECISION", panel="P%02d" % i,
                      box=T.box((rec["x0"], rec["x1"], rec["y0"], rec["y1"])),
                      rule="CUT_THROUGH_AXIS", measured="", threshold="",
                      detail=rec["cut_through"])
        if covered < FRAGMENT_AREA_SHARE:
            frag.append("panels cover only %.0f%% of the raster" % (100 * covered))
            if T.ON:
                T.add("FRAGMENT_DECISION", panel="P%02d" % i,
                      box=T.box((rec["x0"], rec["x1"], rec["y0"], rec["y1"])),
                      rule="FIGURE_COVERAGE", measured="%.4f" % covered,
                      threshold="%.2f" % FRAGMENT_AREA_SHARE,
                      detail="all panel boxes together cover %.1f%% of the raster"
                             % (100 * covered))
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
            _bx = T.box((rec["x0"], rec["x1"], rec["y0"], rec["y1"]))
            # IN THIS PASS. The context already names the winning mode and ink;
            # the join behind these two rows has to name it as well.
            _ac = T.last_in_pass("AXIS_CANDIDATES", box=_bx)
            _fb = T.last_in_pass("AXIS_FALLBACK", box=_bx)
            _rid, _roots, _chain = A.provenance_of((rec["x0"], rec["x1"],
                                                    rec["y0"], rec["y1"]))
            _geom = T.axis_geometry(
                int(_ac["n_free"]) if _ac else 0,
                int(_ac["n_clipped"]) if _ac else 0,
                anchored=bool(_ac and _ac.get("selected_x") != ""),
                spine=rec.get("spine_x") is not None,
                observed=bool(_ac or _fb))
            _calib = T.calibration_method(rec.get("status") == "LADDER_OK")
            _complete = T.completeness(frag,
                                       measured=rec.get("spine_x") is not None)
            # IS THERE ANYTHING PRINTED BESIDE THIS AXIS, and does a panel in the
            # same rows to its LEFT read a ladder? A grid figure labels its y axis
            # once per row - publication 177's figure 2 is five rows of three -
            # and ten of its fifteen panels refuse the ladder because nothing is
            # printed beside them. Both are REPORTED as measured; no threshold
            # turns them into a verdict, because the counts run 2, 3, 13, 15, 24,
            # 30 and any line drawn through that is a constant nobody measured.
            _ink_cols, _ink_from = 0, None
            if rec.get("spine_x") is not None and rec.get("baseline_y") is not None:
                try:
                    _ink_cols, _ink_from = PG.label_ink(
                        gdark, (rec["x0"], rec["x1"], rec["y0"], rec["y1"]),
                        rec["spine_x"], rec["baseline_y"], floor=A.CAP_FLOOR)
                except Exception:
                    _ink_cols, _ink_from = "", ""
            _left = [o for o in recs
                     if o is not rec and o["x1"] <= rec["x0"]
                     and (min(o["y1"], rec["y1"]) - max(o["y0"], rec["y0"]))
                     >= A.ADOPT_SHARE * min(o["y1"] - o["y0"],
                                            rec["y1"] - rec["y0"])]
            T.add("SELECTED", panel="P%02d" % i, box=T.box((rec["x0"], rec["x1"],
                                                            rec["y0"], rec["y1"])),
                  # THREE ORTHOGONAL CELLS, not one composite. The old
                  # `axis_status` folded the ladder into the geometry answer, and
                  # on a grid figure that labels its y axis once per row it was
                  # reporting the LAYOUT as a property of the panel.
                  axis_geometry=_geom, calibration=_calib,
                  panel_completeness=_complete,
                  label_ink_cols=_ink_cols, label_ink_from=_ink_from,
                  row_left_panels=len(_left),
                  row_left_reader=any(o.get("status") == "LADDER_OK" for o in _left),
                  box_origin=(";".join(_roots) or "-"),
                  region_id=_rid, origin_roots=";".join(_roots),
                  constructed=(bool(_rid) and A.constructed(_rid)),
                  origin_chain=";".join(_chain[:6]),
                  spine_x=rec.get("spine_x"), baseline_y=rec.get("baseline_y"),
                  status=rec.get("status"), n_labels=rec.get("n_labels"),
                  n_bars=rec.get("n_bars"), fragment="; ".join(frag),
                  source=(rec.get("harness") or "").split(":")[0])
            if YG.ON:
                _box = (rec["x0"], rec["x1"], rec["y0"], rec["y1"])
                try:
                    _run = (A.spine_run(gdark, rec["spine_x"], rec["y0"], rec["y1"])
                            if rec.get("spine_x") is not None else None)
                    _side = (PG.label_side(gdark, _box, rec["spine_x"],
                                           rec["baseline_y"])
                             if rec.get("baseline_y") is not None else "LEFT")
                except Exception:
                    _run, _side = None, "LEFT"
                # THE ELIGIBILITY INPUTS TRAVEL WITH THE PANEL. `ladder_ok`
                # alone made a fallback column on a fragment into a provider,
                # and the three cells that say otherwise were already being
                # written to the SELECTED row and not handed over.
                try:
                    _brk = (A.axis_break(gdark, _box, rec["spine_x"])
                            if rec.get("spine_x") is not None else None)
                except Exception:
                    _brk = None
                _tr = (YG.tick_runs(gdark, _box, rec["spine_x"], _run, _side)
                       if (_run and rec.get("spine_x") is not None) else [])
                _cal = PG.calibration(rec.get("ticks", ""),
                                      ladder_ok=rec.get("status") == "LADDER_OK",
                                      axis_break=_brk)
                ygroup.append({
                    "label": "P%02d" % i, "box": _box,
                    "spine": rec.get("spine_x"), "baseline": rec.get("baseline_y"),
                    "run": tuple(_run) if _run else None, "side": _side,
                    "ladder_ok": rec.get("status") == "LADDER_OK",
                    "axis_geometry": _geom, "completeness": _complete,
                    "axis_break": _cal["axis_break"],
                    "points": _cal["points"],
                    "value_set_sha": _cal["value_set_sha"],
                    "calibration_sha": _cal["calibration_sha"],
                    "ticks": [(t0 + t1) // 2 for t0, t1, _ln in _tr],
                    "tick_lengths": [ln for _t0, _t1, ln in _tr]})
                # A SECOND ROUTE TO THE LADDER, asked per tick instead of per
                # strip, and asked of every panel rather than only the ones that
                # failed - a route tried only where the first one lost cannot be
                # compared with it. Records; changes nothing.
                if TO.ON:
                    try:
                        TO.record(img, gdark, "P%02d" % i, _box, rec["spine_x"],
                                  _side, _run,
                                  [(t0 + t1) // 2 for t0, t1, _ln in _tr],
                                  ink=ink)
                    except Exception as exc:
                        T.add("TICK_OCR_LADDER", panel="P%02d" % i,
                              box=T.box(_box), outcome="FAILED",
                              detail="%s: %s" % (type(exc).__name__, exc))
        rec.update(pid=r["pid"], fig=r["fig"], png=r["png"], panel="P%02d" % i,
                   sever_mode=mode, ink=ink, declared_axes=declared,
                   caption_panels=cap_panels, caption_row=(A.CAP_FLOOR if A.CAP_FLOOR else ""),
                   area_share="%.2f" % covered,
                   fragment="; ".join(frag))
        out.append(rec)
    # ONE HANDOVER, after every panel of the winning pass has been written. The
    # group question cannot be answered a panel at a time, and asking it inside
    # the loop would mean asking it against a half-built list.
    if T.ON and YG.ON:
        YG.record(gdark, ygroup)

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
