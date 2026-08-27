# -*- coding: utf-8 -*-
"""The reader put back on the figure it read.

Not a diagram of the pipeline: the published raster with the number recovered
from each mark drawn on the mark, beside the value a person read off the same
mark by eye. What is refused is drawn too, in red, because a reader that only
shows what it answered cannot be judged.
"""
import collections
import os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
import capt
import raster_root as RR

OK = (0, 150, 110)
EYEC = (10, 90, 175)
BAD = (168, 52, 43)
AXIS = (176, 108, 12)
#: ONE COLOUR PER REVIEW TIER, and the tier is `provenance.review_tier`'s, not a
#: judgment made here. G2 painted all eighteen of its cells the same green while
#: the package priced two of them R0, nine R1 and seven R4 - and R4 is not
#: finalizable, so a third of that picture was showing numbers no run may pool
#: as if they were the same answer as the rest.
TIER_COLOUR = {"R0": (0, 150, 110), "R1": (95, 145, 35), "R2": (200, 150, 0),
               "R3": (205, 110, 20), "R4": (150, 30, 110)}
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


#: The eye readings, as DATA. They were literals in this file, which made the
#: comparison unauditable: a reader whose output drifted could be made to agree
#: by editing the numbers it is compared with, in the same file, in the same
#: commit. `test_visual_verification.py` pins this file's SHA-256.
TRUTH_PATH = os.path.join(ROOT, "verification_truth.json")


def truth(figure):
    """{(panel, series, x): value}, the tolerance, and the axis span."""
    import json
    doc = json.load(open(TRUTH_PATH, encoding="utf-8"))
    for fig in doc["figures"]:
        if fig["figure"] == figure:
            return (dict(((c["panel"], c["series"], c["x"]), c["value"])
                         for c in fig["cells"]),
                    float(fig["tolerance"]), float(fig["axis_span"]),
                    fig["unit"])
    raise SystemExit("%s carries no readings for %s" % (TRUTH_PATH, figure))


def panel_count(figure):
    """The number of axes counted by eye on one corpus figure."""
    import json
    doc = json.load(open(TRUTH_PATH, encoding="utf-8"))
    for row in doc["panel_counts"]:
        if row["figure"] == figure:
            return int(row["axes_counted_by_eye"])
    raise SystemExit("%s carries no panel count for %s" % (TRUTH_PATH, figure))


def zoom(im, crop, scale):
    """A crop of the raster at `scale`, and the mapper from raster to crop."""
    x0, x1, y0, y1 = crop
    out = im.crop((x0, y0, x1, y1))
    out = out.resize((out.width * scale, out.height * scale), Image.LANCZOS)
    return out, (lambda px, py: ((px - x0) * scale, (py - y0) * scale))


def chip(d, xy, text, col, limit, size=15, pad=3):
    f = ImageFont.truetype(MONO, size)
    x, y = xy
    w = int(f.getlength(text))
    x = max(2, min(x, limit - w - 2 * pad - 2))
    d.rectangle([x, y, x + w + 2 * pad, y + f.size + 2 * pad - 2], fill=(255, 255, 255))
    d.rectangle([x, y, x + w + 2 * pad, y + f.size + 2 * pad - 2], outline=col, width=2)
    d.text((x + pad, y + pad - 2), text, fill=col, font=f)
    return f.size + 2 * pad + 1


def axis_marks(d, cal, box, ticks, limit):
    """The calibration, drawn: every tick the reader was given, at its row."""
    for value, row in ticks:
        d.line([(box[0] - 26, row), (box[1], row)], fill=AXIS, width=1)
        chip(d, (box[0] - 26, row - 10), "%g" % value, AXIS, limit, size=13)


def bars_397():
    """397 Fig. 3 read by the PRODUCTION BAR_MONO path, in its two passes.

    This drew `read_monochrome_bar_panel` for one round, which is not what
    `run_batch` dispatches. That reader decides which bar is which INSIDE one
    panel, from an absolute fill density against bands measured on a single
    figure; the released path measures the geometry with the identity left open
    (`identity_status: NOT_CALIBRATED`, empty `resolved_fill_pattern`) and then
    names the fills across the whole figure in
    `mono_bar_geometry.fill_identities_by_figure`. A gallery that shows the
    easier path shows a picture nobody's run produces.
    """
    import mark_readers as MR
    import mono_bar_geometry as MONO_GEOMETRY
    # A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC.
    path = RR.check("397_fig3.jpeg")[0]
    if not path:
        print(RR.skip_note("397_fig3.jpeg"))
        return {}
    # THE FIGURE'S LEGEND, which is a declaration and not a measurement: it says
    # this figure prints two fills and what each MEANS. Which bar carries which
    # is what the second pass answers, off the figure's own ink.
    LEGEND = {"SOLID": "FLUID", "HATCHED": "NON_FLUID"}
    FIGURE = "397|FIG3"
    EYE, TOL, SPAN, UNIT = truth(FIGURE)
    PANELS = (
        dict(name="MEN", box=(118, 480, 90, 470), ticks=[(150, 101), (50, 465)],
             x={"PRE": 187, "POST": 390}),
        dict(name="WOMEN", box=(620, 1010, 88, 466), ticks=[(150, 95), (50, 460)],
             x={"PRE": 720, "POST": 920}),
    )
    raw = Image.open(path).convert("RGB")
    SC = 2
    im, M = zoom(raw, (100, 1060, 60, 520), SC)
    d = ImageDraw.Draw(im)

    # PASS ONE: every panel measured, nothing named.
    measured = []
    for p in PANELS:
        cal = MR.AxisCalibration.from_points(p["ticks"])
        rows = MR.read_monochrome_bar_geometry(
            raw, p["box"], p["x"], cal, sorted(LEGEND),
            baseline_value=50.0, group_window=75,
            panel_id="%s|%s" % (FIGURE, p["name"]),
            identity_domain_id=FIGURE, figure_id=FIGURE)
        measured.append((p, cal, rows))
    unnamed = sum(1 for _p, _c, rows in measured for r in rows
                  if r["identity_status"] == "NOT_CALIBRATED")
    # PASS TWO: the fills named once, across the whole figure.
    MONO_GEOMETRY.fill_identities_by_figure(
        [r for _p, _c, rows in measured for r in rows])

    lines, errs = [], []
    resolved = stems = 0
    lines.append("%-6s %-9s %-5s %-8s %8s %8s %7s %6s %s"
                 % ("panel", "series", "x", "fill", "read", "by eye", "diff",
                    "sd", "stem"))
    for p, cal, rows in measured:
        upx = abs((p["ticks"][1][0] - p["ticks"][0][0])
                  / float(p["ticks"][1][1] - p["ticks"][0][1]))
        bx0, by0 = M(p["box"][0], p["box"][2])
        bx1, by1 = M(p["box"][1], p["box"][3])
        d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=2)
        for value, row in p["ticks"]:
            _x, ry = M(p["box"][0], row)
            d.line([(bx0 - 40, ry), (bx1, ry)], fill=AXIS, width=1)
            chip(d, (bx0 - 46, ry - 12), "%g" % value, AXIS, im.width, size=15)
        for r in rows:
            fill = r["resolved_fill_pattern"]
            named = r["identity_status"] == "RESOLVED" and fill in LEGEND
            resolved += bool(named)
            series = LEGEND.get(fill, "?")
            eye = EYE.get((p["name"], series, r["group"]))
            cap = next((x for x in (r.get("remote") or [])
                        if x["kind"] == "ERRORBAR_CAP"), None)
            stems += cap is not None
            sd = "----" if cap is None else "%.1f" % (cap["distance_px"] * upx)
            # THE BAR IT ACTUALLY MEASURED, not a nominal x. `footprint_px_image`
            # is where the ink was; drawing on the declared centre would hide a
            # reader that answered about the neighbouring bar.
            fx0, fx1 = r["footprint_px_image"]
            py = cal.value_to_pixel(r["value"])
            cx, cy = M((fx0 + fx1) / 2.0, py)
            col = OK if named else BAD
            d.line([(cx - 30, cy), (cx + 30, cy)], fill=col, width=3)
            side = -1 if r["slot"] == 0 else 1
            ox = cx - 96 if side < 0 else cx + 34
            below = chip(d, (ox, cy - 34), "read %.1f" % r["value"], col,
                         im.width, size=16)
            if eye is None:
                chip(d, (ox, cy - 34 + below), "no eye cell", BAD, im.width, size=16)
            else:
                errs.append(abs(r["value"] - eye))
                chip(d, (ox, cy - 12), "eye  %d" % eye, EYEC, im.width, size=16)
            lines.append("%-6s %-9s %-5s %-8s %8.1f %8s %7s %6s %s"
                         % (p["name"], series, r["group"], fill or "-", r["value"],
                            "-" if eye is None else "%d" % eye,
                            "-" if eye is None else "%.1f" % abs(r["value"] - eye),
                            sd, "TRUE" if cap is not None else "FALSE"))
    declared = len(EYE)
    total = sum(len(rows) for _p, _c, rows in measured)
    # COUNTED FROM THE ROWS. Every one of these four numbers was a literal in
    # this caption for one round - "8 of 8" printed whatever the reader did.
    lines += ["",
              "bars measured             %d, against %d declared cells" % (total, declared),
              "unnamed after pass one    %d of %d" % (unnamed, total),
              "named by the figure's own fills %d of %d" % (resolved, total),
              "compared with an eye reading    %d" % len(errs),
              "worst vs the eye reading  %s"
              % ("-" if not errs else
                 "%.2f %s on a %g %s axis, tolerance %g"
                 % (max(errs), UNIT, SPAN, UNIT, TOL)),
              "error bars stem-confirmed %d of %d" % (stems, total),
              # AND WHERE THEY STOP. Eight bars agreeing with the eye is not
              # eight usable numbers: this publication does not say whether its
              # error bars are SD or SEM, so machine QC passes nothing on it and
              # the finalizer has nothing to accept. `test_visual_verification`
              # measures that by running the worked example rather than taking
              # this line's word for it.
              "accepted by the pipeline  0 — 397 does not say whether its error "
              "bars are SD or SEM, and no reader can fix that"]
    im = capt.below(im, "397 Fig. 3: released BAR_MONO 2-pass — 읽은 값과 눈으로 읽은 값",
                    lines, keys=[(OK, "read, and named by the figure's fills", False),
                                 (BAD, "measured but not named", False),
                                 (EYEC, "read by eye", False),
                                 (AXIS, "the ticks it was calibrated on", False)])
    out = os.path.join(HERE, "G1_read_397fig3.png")
    im.save(out)
    # THE FACTS, so a suite can assert them. A gallery whose only output is a
    # picture is checked by a person looking at it, which is not a check that
    # runs in CI.
    return dict(out=out, cells=total, declared=declared,
                unnamed_after_pass_one=unnamed, named_by_figure=resolved,
                stem_confirmed=stems, compared=len(errs),
                worst=max(errs) if errs else None, tolerance=TOL)


def lines_397():
    import mark_readers as MR
    import line_style_mono as LSM
    # A PUBLISHER FIGURE, AND THIS REPOSITORY IS PUBLIC.
    path = RR.check("397_fig1.jpeg")[0]
    if not path:
        print(RR.skip_note("397_fig1.jpeg"))
        return {}
    CAL = MR.AxisCalibration.from_points([(120.0, 76.0), (70.0, 296.0)])
    LABELS = ("0:30", "1:00", "1:30", "2:00", "2:30", "3:00",
              "3:30", "4:00", "4:30", "5:00", "5:30", "6:00")
    XS = (99.5, 132.5, 165.0, 197.5, 230.5, 263.5,
          296.5, 329.0, 361.5, 394.5, 427.5, 460.0)
    BOX = (84, 477, 110, 296)
    EYES, TOL, SPAN, UNIT = truth("397|FIG1")
    EYE = {s: tuple(EYES[("MAP", s, lab)] for lab in LABELS)
           for s in ("FLUID", "NO_FLUID")}
    rows = LSM.read_monochrome_line_panel(
        Image.open(path), panel_box=BOX, x_positions=dict(zip(LABELS, XS)),
        y_calibration=CAL,
        series=[MR.SeriesSpec("FLUID", line_style="SOLID"),
                MR.SeriesSpec("NO_FLUID", line_style="DASHED")],
        threshold=150, x_window=10, search_radius=60)
    raw = Image.open(path).convert("RGB")
    SC = 3
    im, M = zoom(raw, (60, 500, 60, 320), SC)
    d = ImageDraw.Draw(im)
    bx0, by0 = M(BOX[0], BOX[2]); bx1, by1 = M(BOX[1], BOX[3])
    d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=2)
    for value, row in ((120.0, 76.0), (70.0, 296.0)):
        _x, ry = M(BOX[0], row)
        d.line([(bx0 - 60, ry), (bx1, ry)], fill=AXIS, width=1)
        chip(d, (bx0 - 66, ry - 12), "%g" % value, AXIS, im.width, size=15)
    # THE PACKAGE'S OWN PRICE FOR EACH CELL, and not the reader's word for it.
    # `review_tier` was fed the reader's OWN `Identity_Method` and `Value_Method`,
    # so the colours were the reader's self-report: a regression that wrote a
    # cheaper method would have been believed by the picture and by the tier
    # function alike. The pipeline has a verifier for exactly this -
    # `expected_line_style_methods` re-derives both from the mark's recorded
    # evidence, and `evidence_failure` is what run_batch uses to refuse a value
    # whose methods its own ink does not support. The tier drawn below is the
    # VERIFIED one, and a cell where the two disagree is drawn as a failure
    # rather than coloured by either.
    import provenance as PV
    CONTEXT = {"Y_Calibration": MR._calibration_record(CAL)}
    MARK_TYPE = "LINE_MONO_STYLE"
    got = {(r["series"], r["x_label"]): r for r in rows}
    errs, lines = [], []
    tiers = collections.Counter()
    disagreed = []
    lines.append("%-9s %-5s %7s %7s %6s %-30s %-26s %-5s %s"
                 % ("series", "x", "value", "by eye", "diff",
                    "how it was named (re-derived)",
                    "where the number came from", "tier", "reader agrees"))
    for si, s in enumerate(("FLUID", "NO_FLUID")):
        for lab, x, eye in zip(LABELS, XS, EYE[s]):
            r = got.get((s, lab))
            py = 76.0 + (eye - 120.0) * (296.0 - 76.0) / (70.0 - 120.0)
            cx, cy = M(x, py)
            if r is None:
                d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=BAD, width=4)
                chip(d, (cx - 34, cy + 18 + 22 * si), "REFUSED", BAD, im.width, size=14)
                lines.append("%-9s %-5s %7s %7.1f %6s %-30s %-26s %-5s %s"
                             % (s, lab, "NONE", eye, "-", "-", "no value emitted",
                                "-", "-"))
                tiers["NO_VALUE"] += 1
                continue
            # RE-DERIVED FROM THE MARK, then compared with what the mark claims.
            verdict = PV.expected_line_style_methods(r, CONTEXT)
            claimed = {k: r.get(k, "") for k in
                       ("Identity_Method", "Value_Method", "Dispersion_Method")}
            code, detail = PV.evidence_failure(MARK_TYPE, r, claimed, CONTEXT)
            v_identity = verdict.expected.get("Identity_Method", "")
            v_value = verdict.expected.get("Value_Method", "")
            tier = PV.review_tier(v_identity, v_value)
            agrees = not code and tier == PV.review_tier(
                claimed["Identity_Method"], claimed["Value_Method"])
            if not agrees:
                disagreed.append((s, lab, code or "TIER_DIFFERS", detail))
            tiers[tier] += 1
            col = BAD if not agrees else TIER_COLOUR.get(tier, BAD)
            ry = 76.0 + (r["mean"] - 120.0) * (296.0 - 76.0) / (70.0 - 120.0)
            errs.append(abs(r["mean"] - eye))
            rx, ryc = M(x, ry)
            d.line([(rx - 12, ryc), (rx + 12, ryc)], fill=col, width=3)
            # A CELL THE REVIEW GATE WILL NOT TAKE gets a ring as well as the
            # colour: it has a number, which is exactly why it needs saying.
            if tier not in PV.FINALIZABLE_TIERS:
                d.ellipse([rx - 15, ryc - 15, rx + 15, ryc + 15], outline=col, width=3)
            chip(d, (rx - 26, ryc - 26 if si == 0 else ryc + 8),
                 "%.1f %s%s" % (r["mean"], tier, "" if agrees else " !"),
                 col, im.width, size=14)
            lines.append("%-9s %-5s %7.1f %7.1f %6.2f %-30s %-26s %-5s %s"
                         % (s, lab, r["mean"], eye, abs(r["mean"] - eye),
                            v_identity or "?", v_value or "?", tier,
                            "yes" if agrees else (code or "tier differs")))
    # COUNTED, NOT WRITTEN DOWN. `24` and `50 mmHg` were literals here: a
    # reader that stopped emitting a cell would have printed "24 of 24" and a
    # recalibration would have printed the old span.
    declared = len(EYES)
    span = SPAN
    eligible = sum(n for t, n in tiers.items() if t in PV.FINALIZABLE_TIERS)
    blocked = sum(n for t, n in tiers.items()
                  if t not in PV.FINALIZABLE_TIERS and t != "NO_VALUE")
    # NOT "READ" AND NOT "FINALIZABLE". Seven of these carry
    # NONLOCAL_INTERPOLATION or EXTRAPOLATED_CURVE_INK - a number was EMITTED,
    # and calling it "read" says the ink was there. And the eleven that clear the
    # method gate are not finalizable either: this publication does not say
    # whether its error bars are SD or SEM, so `pilot_397` ends every run with
    # Values_Accepted=0 and no reader can fix that. What the method tier decides
    # is ELIGIBILITY, one gate of several.
    lines += ["",
              "declared cells               %d" % declared,
              "values emitted               %d" % len(errs),
              "no value emitted             %d, where the two curves are one run"
              " of ink" % (declared - len(errs)),
              "method-eligible (R0-R3)      %d" % eligible,
              "method-blocked estimates     %d, R4: a number exists and the "
              "method gate refuses it" % blocked,
              "accepted by the pipeline     0 — 397 does not say whether its "
              "error bars are SD or SEM",
              "by verified tier             " + "  ".join(
                  "%s %d" % (t, tiers[t]) for t in PV.TIERS if tiers[t]),
              "reader's methods re-derived  %d of %d agree"
              % (len(errs) - len(disagreed), len(errs)),
              "worst vs eye                 %.2f %s on a %g %s axis, tolerance %g"
              % (max(errs), UNIT, span, UNIT, TOL)]
    if disagreed:
        lines += ["", "THE MARK'S EVIDENCE DOES NOT SUPPORT ITS OWN METHODS:"]
        lines += ["  %s %s  %s  %s" % (a, b, c, d[:70]) for a, b, c, d in disagreed]
    lines += ["",
              "값이 없는 칸은 빨간 원. 고리를 두른 칸은 숫자는 있으나 R4로 방법"
              " 게이트가 거절한다. 등급은 reader의 자기 신고가 아니라 mark 증거에서"
              " 다시 유도한 것이다."]
    keys = [(TIER_COLOUR[t], "%s  %d cell(s)%s"
             % (t, tiers[t], "" if t in PV.FINALIZABLE_TIERS else " — method-blocked"),
             False) for t in PV.TIERS if tiers[t]]
    im = capt.below(im, "397 Fig. 1: 겹친 두 곡선 — 방출된 값과 증거에서 다시 유도한 등급",
                    lines,
                    keys=keys + [(BAD, "no value emitted, or evidence disagrees",
                                  False),
                                 (AXIS, "calibration ticks", False)])
    out = os.path.join(HERE, "G2_read_397fig1.png")
    im.save(out)
    return dict(out=out, declared=declared, emitted=len(errs),
                eligible=eligible, blocked=blocked, disagreed=disagreed,
                no_value=sorted(k for k in
                               ((s, lab) for s in ("FLUID", "NO_FLUID")
                                for lab in LABELS) if k not in
                               {(r["series"], r["x_label"]) for r in rows}),
                tiers=dict(tiers), worst=max(errs), tolerance=TOL)


def segmentation(props, pid, fig, out, title):
    """What the SEGMENTATION side found: the panels, and the ladder each one read.

    The reading demonstrations above are handed their panel box and their ticks
    by an author. This is the half that has to produce them, on a plate the cut
    does not hand over willingly.
    """
    import csv
    rows = [r for r in csv.DictReader(open(props))
            if r.get("panel") and r["pid"] == pid and r["fig"] == fig]
    if not rows:
        # NAMED, not an IndexError two lines down. "no panel rows for 475 Fig. 2"
        # is a diagnosis; "list index out of range" sends the reader into this
        # file instead of to the clip that would not open.
        raise SystemExit("%s carries no panel rows for %s %s"
                         % (props, pid, fig))
    clip = rows[0]["png"]
    im = Image.open(os.path.join(corpus_root() or ROOT, "clips", clip)).convert("RGB")
    d = ImageDraw.Draw(im)
    lines = ["%-4s %-19s %-6s %-12s %s"
             % ("", "box", "spine", "status", "ladder it read")]
    nok = 0
    for r in sorted(rows, key=lambda r: (int(r["y0"]), int(r["x0"]))):
        b = [int(r["x0"]), int(r["x1"]), int(r["y0"]), int(r["y1"])]
        ok = r["status"] == "LADDER_OK"
        nok += ok
        col = OK if ok else BAD
        d.rectangle([b[0], b[2], b[1] - 1, b[3] - 1], outline=col, width=4)
        chip(d, (b[0] + 6, b[2] + 6), "%s  %s" % (r["panel"], r["status"]),
             col, im.width, size=17)
        if r.get("spine_x"):
            sx = int(float(r["spine_x"]))
            d.line([(sx, b[2]), (sx, b[3])], fill=AXIS, width=2)
        for t in (r.get("ticks") or "").split(";"):
            if ":" not in t:
                continue
            v, py = t.split(":", 1)
            py = int(float(py))
            d.line([(b[0], py), (b[0] + 26, py)], fill=EYEC, width=3)
            chip(d, (b[0] + 28, py - 10), v, EYEC, im.width, size=14)
        lines.append("%-4s %-19s %-6s %-12s %s"
                     % (r["panel"], "%d,%d,%d,%d" % tuple(b),
                        r.get("spine_x") or "-", r["status"],
                        (r.get("ticks") or "-")[:46]))
    lines += ["",
              "panels found %d   ladders read %d   declared axes %s"
              % (len(rows), nok, rows[0].get("declared_axes") or "?")]
    im = capt.below(im, title, lines,
                    keys=[(OK, "ladder read", False), (BAD, "no ladder", False),
                          (AXIS, "the spine it found", False),
                          (EYEC, "each numeral it read, at its row", False)])
    im.save(out)
    return dict(out=out, panels=len(rows), ladders=nok,
                declared_axes=int(rows[0].get("declared_axes") or 0),
                counted_by_eye=panel_count("%s|%s" % (pid, fig)),
                statuses=sorted({r["status"] for r in rows}))


def scatter_fixtures():
    """The scatter reader on the six renderings this repository DOES carry.

    THE ONLY PANEL HERE THAT A FRESH CLONE CAN DRAW. Every other picture in this
    gallery needs a publisher figure; these six are generated by
    `make_scatter_fixture.py` from twelve declared pairs, so the reading can be
    checked against the drawing rather than against an eye.

    What they are FOR is the trap in `read_scatter_panel`'s docstring: the area
    bounds used to be absolute pixels, and on publication 177 Figure 4 at 600
    dpi they rejected every data point and returned four letters of the printed
    "r = 0.91" as the cloud - r = -0.47. The same drawing at a third of the size
    returns twenty-two marks instead of four. So the fixtures are ONE drawing
    rendered three sizes apart, and the scenario that matters is that the
    renderings agree with each other.
    """
    import json
    import make_scatter_fixture as SF
    import mark_readers as MR
    truth = json.load(open(os.path.join(ROOT, "scatter_fixture_truth.json"),
                           encoding="utf-8"))
    import numpy as np
    rows, facts = [], {}
    shown = None
    for name in sorted(truth["renderings"]):
        r = truth["renderings"][name]
        path = os.path.join(ROOT, r["file"])
        if not os.path.exists(path):
            SF.main()
        im = Image.open(path).convert("RGB")
        want = sorted(tuple(p) for p in r["pairs"])
        xcal = MR.AxisCalibration.from_points([tuple(p) for p in r["x_ticks"]])
        ycal = MR.AxisCalibration.from_points([tuple(p) for p in r["y_ticks"]])

        def read(exclude):
            return MR.read_scatter_panel(
                im, panel_box=tuple(r["panel_box"]), x_calibration=xcal,
                y_calibration=ycal,
                series=[MR.SeriesSpec("S", rgb=None, marker=truth["marker"])],
                exclude_boxes=exclude)

        got = read([r["annotation_box"]])
        left_in = read(None)
        pairs = sorted((p["x_value"], p["y_value"]) for p in got)
        # IN UNITS OF THE AXIS SPAN, so three renderings are held to one
        # standard rather than to three pixel tolerances.
        xs = abs(r["x_ticks"][1][0] - r["x_ticks"][0][0])
        ys = abs(r["y_ticks"][1][0] - r["y_ticks"][0][0])
        ok = len(pairs) == len(want)
        dx = (max(abs(a[0] - b[0]) for a, b in zip(pairs, want)) / xs) if ok else None
        dy = (max(abs(a[1] - b[1]) for a, b in zip(pairs, want)) / ys) if ok else None
        true_r = float(np.corrcoef([p[0] for p in want],
                                   [p[1] for p in want])[0, 1])
        assoc = (MR.summarize_association(got, "PEARSON_R")["Association_Value"]
                 if ok else None)
        rows.append(dict(name=name, scale=r["scale"], found=len(pairs),
                         pairs=len(want), with_annotation=len(left_in),
                         dx=dx, dy=dy, assoc=assoc, true_r=true_r))
        facts[name] = rows[-1]
        if name == "large":
            shown = (im, r, got, pairs, want)
    im, r, got, pairs, want = shown
    SC = 1
    box = tuple(r["panel_box"])
    view, M = zoom(im, (box[0] - 120, box[1] + 40, box[2] - 60, box[3] + 140), SC)
    d = ImageDraw.Draw(view)
    bx0, by0 = M(box[0], box[2])
    bx1, by1 = M(box[1], box[3])
    d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=3)
    ax0, ax1, ay0, ay1 = r["annotation_box"]
    qx0, qy0 = M(ax0, ay0)
    qx1, qy1 = M(ax1, ay1)
    # WHAT THE PANEL DECLARED IS NOT DATA. Drawn, because the declaration is the
    # only thing separating those glyphs from marks: `0` IS a small circle.
    d.rectangle([qx0, qy0, qx1, qy1], outline=BAD, width=3)
    chip(d, (qx0, qy0 - 26), "declared annotation, excluded", BAD, view.width, size=17)
    for p in got:
        cx, cy = M(p["point_px_x"], p["point_px_y"])
        d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], outline=OK, width=3)
    lines = ["%-9s %5s %7s %7s %9s %9s %8s %8s"
             % ("rendering", "scale", "found", "drawn", "dx/span", "dy/span",
                "r read", "r drawn")]
    for row in rows:
        lines.append("%-9s %5s %7d %7d %9s %9s %8s %8.4f"
                     % (row["name"], row["scale"], row["found"], row["pairs"],
                        "-" if row["dx"] is None else "%.4f" % row["dx"],
                        "-" if row["dy"] is None else "%.4f" % row["dy"],
                        "-" if row["assoc"] is None else "%.4f" % row["assoc"],
                        row["true_r"]))
    a_small, a_large = facts.get("small"), facts.get("large")
    worst_between = None
    if a_small and a_large and a_small["found"] == a_large["found"]:
        # THE SCENARIO THE ABSOLUTE NUMBERS CANNOT PASS: one rendering read 22
        # marks and the other 4, off one drawing.
        worst_between = max(abs(a_small["assoc"] - a_large["assoc"]), 0.0)
    lines += ["",
              "one drawing, %d renderings, %d declared pairs each (%d in overlap)"
              % (len(rows), rows[0]["pairs"],
                 max(row["pairs"] for row in rows)),
              "with the annotation left IN, the larger renderings return more "
              "marks than the figure has points:",
              "  " + "  ".join("%s %d" % (row["name"], row["with_annotation"])
                               for row in rows),
              "r read vs r drawn, worst over the renderings: %.4f"
              % max(abs(row["assoc"] - row["true_r"]) for row in rows
                    if row["assoc"] is not None),
              "small vs large, same drawing: r differs by %s"
              % ("-" if worst_between is None else "%.4f" % worst_between)]
    view = capt.below(
        view, "합성 산점도 6렌더링: 그린 것과 읽은 것 (공개 저장소만으로 재현됨)",
        lines, keys=[(OK, "read by the pipeline", False),
                     (BAD, "declared annotation, not data", False),
                     (AXIS, "the panel box it was given", False)])
    out = os.path.join(HERE, "G5_scatter_fixtures.png")
    view.save(out)
    return dict(out=out, renderings=facts, rows=rows,
                r_between=worst_between)


def scatter_real(props):
    """A REAL four-series monochrome scatter, and what the reader does with it.

    ID 464 Figure 2 draws total peripheral resistance against central venous
    pressure as open and filled CIRCLES on the left axis, and a splanchnic
    resistance index as open and filled TRIANGLES on a right axis with a
    different scale, with a dashed regression line through each cloud.

    `read_scatter_panel` REFUSES it: more than one monochrome series needs
    explicit marker routing, and a shared threshold cannot supply it. This panel
    exists to show what that refusal is worth, by doing the thing the refusal
    prevents - asking for ONE monochrome series and taking what comes back.

    The corpus routes this figure to DIGITIZE_TWIN_AXIS with `target_axes = 0`,
    and nothing in this package has a vocabulary for a second y axis, so no
    value from it is offered for digitizing by either route.
    """
    import csv
    import mark_readers as MR
    clip = "clips/ID464__fig2.png"
    path, note = RR.check(clip, extra=corpus_root() or ROOT)
    if not path:
        print(RR.corpus_note(clip))
        return {}
    rows = [r for r in csv.DictReader(open(props))
            if r.get("panel") and r["pid"] == "464" and r["fig"] == "Fig. 2"]
    if not rows:
        raise SystemExit("%s carries no panel rows for 464 Fig. 2" % props)
    prop = rows[0]
    box = (int(prop["plot_x0"]), int(prop["plot_x1"]),
           int(prop["plot_y0"]), int(prop["plot_y1"]))
    # THE LADDER THE PROPOSER READ, off the figure, not declared here.
    ladder = [(float(v), float(px)) for v, px in
              (pair.split(":") for pair in prop["ticks"].split(";") if pair)]
    xladder = [(float(v), float(px)) for v, px in
               (pair.split(":") for pair in prop["x_ticks"].split(";") if pair)]
    ycal = MR.AxisCalibration.from_points(ladder)
    xcal = MR.AxisCalibration.from_points(xladder)

    four = [MR.SeriesSpec("TPR_OPEN", marker="CIRCLE", fill="OPEN"),
            MR.SeriesSpec("TPR_FILLED", marker="CIRCLE", fill="FILLED"),
            MR.SeriesSpec("SVRI_OPEN", marker="TRIANGLE", fill="OPEN"),
            MR.SeriesSpec("SVRI_FILLED", marker="TRIANGLE", fill="FILLED")]
    im = Image.open(path).convert("RGB")
    refusal = ""
    try:
        MR.read_scatter_panel(im, panel_box=box, x_calibration=xcal,
                              y_calibration=ycal, series=four)
    except ValueError as exc:
        refusal = "%s" % exc
    # AND WHAT THE SHORTCUT RETURNS, which is the reason the refusal is right.
    shortcut = MR.read_scatter_panel(
        im, panel_box=box, x_calibration=xcal, y_calibration=ycal,
        series=[MR.SeriesSpec("ONE", rgb=None, marker="CIRCLE")])
    assoc = MR.summarize_association(shortcut, "PEARSON_R")
    areas = sorted(p["marker_area_px"] for p in shortcut)
    xs = [p["x_value"] for p in shortcut]

    SC = 2
    view, M = zoom(im, (0, im.width, 0, im.height), SC)
    d = ImageDraw.Draw(view)
    bx0, by0 = M(box[0], box[2])
    bx1, by1 = M(box[1], box[3])
    d.rectangle([bx0, by0, bx1, by1], outline=AXIS, width=3)
    for value, row in ladder:
        _x, ry = M(box[0], row)
        d.line([(bx0 - 30, ry), (bx0, ry)], fill=AXIS, width=2)
        chip(d, (bx0 - 84, ry - 11), "%g" % value, AXIS, view.width, size=15)
    for p in shortcut:
        cx, cy = M(p["point_px_x"], p["point_px_y"])
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], outline=BAD, width=2)
    lines = [
        "the reader, asked for the four series this figure draws:",
        "  ValueError: %s" % refusal,
        "",
        "the same panel, asked for ONE monochrome series - the shortcut the",
        "refusal prevents:",
        "  marks returned            %d" % len(shortcut),
        "  marker area px, min/med/max  %g / %g / %g"
        % (areas[0], areas[len(areas) // 2], areas[-1]),
        "  x range read              %.2f to %.2f, on an axis that ends at %g"
        % (min(xs), max(xs), max(v for v, _px in xladder)),
        "  Pearson r                 %.3f, P = %.2f, N = %d"
        % (assoc["Association_Value"], assoc["P_Value"], assoc["N_Pairs"]),
        "",
        "  두 구름 모두 눈으로 보아 뚜렷한 음의 관계인데, 지름길이 내놓은 값은",
        "  r = %.3f, P = %.2f 이다. 이것이 fail-closed 가 막는 것이다."
        % (assoc["Association_Value"], assoc["P_Value"]),
        "",
        "the segmentation side, on the same figure:",
        "  panels found              %d, and the corpus declares %s axis(es)"
        % (len(rows), prop["declared_axes"]),
        "  the ladder it read        %s" % prop["ticks"],
        "  ladder residual           %s px" % prop["resid_px"],
        "  the RIGHT axis            no ladder: the figure prints a second y",
        "                            scale and nothing here has a vocabulary",
        "                            for one",
    ]
    view = capt.below(
        view, "464 Fig. 2 — 실제 4계열 흑백 산점도: 거절과, 거절이 막는 것",
        lines, keys=[(BAD, "what the one-series shortcut returned", False),
                     (AXIS, "the box and ladder the proposer found", False)])
    out = os.path.join(HERE, "G6_scatter_464fig2.png")
    view.save(out)
    return dict(out=out, refusal=refusal, shortcut=len(shortcut),
                assoc=assoc["Association_Value"], p=assoc["P_Value"],
                area_median=areas[len(areas) // 2],
                x_max_read=max(xs), x_axis_max=max(v for v, _px in xladder),
                panels=len(rows), declared_axes=int(prop["declared_axes"] or 0),
                residual=float(prop["resid_px"]))


#: What the segmentation half needs, and what this repository does not carry.
CORPUS = RR.CORPUS_FILES
#: The clips the segmentation scenarios assert against, pinned in raster_root.
CORPUS_CLIPS = ("clips/ID475__fig2.png", "clips/ID349__fig3.png")


def corpus_root():
    """The first root that holds the whole corpus, or "".

    THE SAME PRIVATE SOURCE AS THE RASTERS. The corpus is publisher figures and
    their metadata; a run that is allowed to see the ten pinned figures is the
    same run that is allowed to see these, so they travel together under
    `FDT_RASTER_ROOT` rather than needing a second secret nobody would set.

    AND THE TWO ASSERTED CLIPS MUST HASH. A root holding a different rendering
    of 475 Figure 2 segments differently, and the scenario that says six panels
    were cut would then be measuring another picture. `RR.check` raises on a
    mismatch, which is the right answer: present-and-wrong is not absent.
    """
    for root in [ROOT] + RR.roots():
        if not all(os.path.exists(os.path.join(root, n)) for n in CORPUS):
            continue
        if not all(os.path.exists(os.path.join(root, c)) for c in CORPUS_CLIPS):
            continue
        for clip in CORPUS_CLIPS:
            RR.check(clip, extra=root)
        return root
    return ""


def corpus_missing():
    """The corpus inputs no root holds, in the order propose.py needs them."""
    if corpus_root():
        return []
    missing = None
    for root in [ROOT] + RR.roots():
        gone = [n for n in tuple(CORPUS) + CORPUS_CLIPS
                if not os.path.exists(os.path.join(root, n))]
        if missing is None or len(gone) < len(missing):
            missing = gone
    return missing or list(CORPUS)


def proposals_for(keys, out_csv):
    """Run the proposer over just these figures, and return the CSV it wrote.

    This read `/tmp/pX2.csv` - a file left behind by a corpus run on one
    machine. Two pictures in this gallery could therefore not be regenerated
    from a fresh checkout, which makes them illustrations rather than output.
    The proposer takes 90 seconds on two figures, so there is no reason for the
    dependency to exist: it is run here, on the clips this repository carries.
    """
    import csv
    import subprocess
    root = corpus_root()
    if not root:
        raise SystemExit(RR.corpus_note(*corpus_missing()))
    # EVERY INPUT NAMED, none defaulted. `propose.py` resolves all four against
    # its working directory when they are not given, which is how a run with the
    # corpus somewhere else produced `OPEN_FAILED` rows and exit 0. `captions.csv`
    # is named too although it is optional: a caption scan that is present under
    # one root and absent under another changes `caption_panels`, and a proposal
    # that silently had no captions is a different measurement.
    env = dict(os.environ, FIGS=";".join("%s|%s" % k for k in keys), OUT=out_csv,
               DIG=os.path.join(root, "dig201.csv"),
               CLIPS=os.path.join(root, "clips201.csv"),
               CAPS=os.path.join(root, "captions.csv"),
               CLIP_ROOT=os.path.join(root, "clips"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "propose.py")],
                       cwd=root, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("propose.py failed:\n%s%s" % (r.stdout, r.stderr))
    # AND THE EXACT SET CAME BACK. The proposer exits 0 having written an
    # `OPEN_FAILED` row for a clip it could not open, so a zero return code is
    # not evidence that anything was segmented. Without this check the failure
    # arrived four frames later as an IndexError on `rows[0]`.
    got = {(row["pid"], row["fig"]) for row in csv.DictReader(open(out_csv))
           if row.get("panel")}
    want = set(keys)
    if got != want:
        raise SystemExit(
            "propose.py returned panel rows for %r, asked for %r. A figure with "
            "no panel rows is a clip it could not open or could not cut, and it "
            "exits 0 either way.\n%s%s" % (sorted(got), sorted(want),
                                           r.stdout, r.stderr))
    print(r.stdout.strip().splitlines()[0])
    return out_csv


if __name__ == "__main__":
    import tempfile
    # THE ONE PANEL A FRESH CLONE CAN DRAW, first, so a reader with no access
    # to the publisher figures still gets a picture out of this file.
    print(scatter_fixtures()["out"])
    print((bars_397() or {}).get("out") or "SKIPPED G1")
    print((lines_397() or {}).get("out") or "SKIPPED G2")
    FIGURES = (("475", "Fig. 2", "G3_segment_475fig2.png",
                "475 Fig. 2: 잘라낸 패널과 각 패널이 읽은 눈금"),
               ("349", "Figure 3", "G4_segment_349fig3.png",
                "349 Fig. 3: 잘라낸 패널과 각 패널이 읽은 눈금"))
    if corpus_missing():
        print(RR.corpus_note(*corpus_missing()))
        print("SKIPPED G3, G4")
    else:
        # 464 IS ASKED FOR TOO, and it draws no segmentation panel: `scatter_real`
        # needs the box and the ladder the proposer found for it, and asking for
        # it here is what keeps that one subprocess call.
        props = proposals_for([(pid, fig) for pid, fig, _o, _t in FIGURES]
                              + [("464", "Fig. 2")],
                              os.path.join(tempfile.mkdtemp(prefix="fdt_props_"),
                                           "proposals.csv"))
        for pid, fig, name, title in FIGURES:
            print(segmentation(props, pid, fig,
                               os.path.join(HERE, name), title)["out"])
        print((scatter_real(props) or {}).get("out") or "SKIPPED G6")
