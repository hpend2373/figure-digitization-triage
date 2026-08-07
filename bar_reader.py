"""Read grouped bar panels off a figure raster.

Companion to figure-digitization-triage: this fills the template, the kernel
validates it. Two geometric facts drive the design, both found on real figures:

1. A vector bar's data coordinate is the CENTRE of its stroke. The colour fill
   stops inside the outline, so reading the fill edge biases every mean in the
   same direction by half the stroke width. Emitted as
   Bar_Top_Definition=OUTLINE_CENTER.
2. Significance glyphs (@ * #) and comparison brackets sit directly above the
   bars, exactly where an error-bar cap is, and they are the same colour. A cap
   is only accepted when a vertical stem physically connects it to the bar top.
   Emitted as Errorbar_Stem_Confirmed.
3. A bar's value sits at the end AWAY FROM THE BASELINE. On a change-from-zero
   plot the bars hang downward, and the same panel can carry both directions, so
   direction is decided per bar against the calibrated zero row - never per
   figure, and never by assuming bars grow upward.
"""
import numpy as np


def runs(idx, gap=1):
    """Group a sorted index list into contiguous runs, tolerating `gap` holes."""
    out, cur = [], []
    for i in idx:
        if cur and i - cur[-1] <= gap:
            cur.append(i)
        else:
            if cur:
                out.append(cur)
            cur = [i]
    if cur:
        out.append(cur)
    return out


def colour_masks(rgb):
    """Blue / red / dark boolean masks from an RGB uint8 array."""
    a = np.asarray(rgb).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return {
        "blue": (B - R > 50) & (B - G > 40) & (B > 110),
        "red": (R - G > 60) & (R - B > 60) & (R > 110),
        "dark": a.mean(axis=2) < 110,
    }


def calibrate(ticks):
    """Least-squares pixel->value map from [(value, pixel_row), ...].

    Returns (fn, max_abs_residual). The residual is the audit number: on a
    linear axis it should be a small fraction of one tick step.
    """
    vs = np.array([t[0] for t in ticks], dtype=float)
    ys = np.array([t[1] for t in ticks], dtype=float)
    k, b = np.polyfit(ys, vs, 1)
    resid = float(np.abs(vs - (k * ys + b)).max())
    return (lambda py: float(k * py + b)), resid


def read_bar_panel(masks, panel_box, ticks, series, min_bar_px=15,
                   stem_half_width=3, max_whisker_px=90, stem_required=True,
                   baseline_value=0.0, n_slots=None):
    """Read every bar of one panel.

    masks       : dict from colour_masks
    panel_box   : (x0, x1, y0, y1) bounding the plot area
    ticks       : [(value, pixel_row), ...] for the y axis
    series      : {series_name: mask_key}, e.g. {"SUPINE": "blue"}

    Each returned bar carries the two provenance flags the template requires.
    """
    x0, x1, y0, y1 = panel_box
    dark = masks["dark"]
    y2v, resid = calibrate(ticks)
    # Pixel row of the baseline the bars grow from, by inverting the calibration.
    vs = np.array([t[0] for t in ticks], dtype=float)
    ys = np.array([t[1] for t in ticks], dtype=float)
    kk, bb = np.polyfit(vs, ys, 1)
    zero_row = float(kk * baseline_value + bb)
    out = []
    for sname, key in series.items():
        m = np.zeros_like(dark)
        m[y0:y1, x0:x1] = True
        col = masks[key] & m
        xs = [x for x in range(x0, x1) if col[:, x].any()]
        # A bar whose value is near the baseline can be split into two colour
        # slivers: its own stroke plus the zero line cover the fill except at the
        # left and right edges. Two fragments of one bar sit far closer together
        # than two bars do, so merge across a gap that is small relative to the
        # fragments themselves. Measured on a real figure: fragment gaps 4-16 px
        # against widths 17-29, neighbouring-bar gaps 67-70 against widths ~61.
        pieces = [r for r in runs(xs, 3) if len(r) >= 8]
        merged = []
        for r in pieces:
            if merged and (r[0] - merged[-1][-1]) < 0.5 * (len(merged[-1]) + len(r)):
                merged[-1] = merged[-1] + list(range(merged[-1][-1] + 1, r[0])) + r
            else:
                merged.append(list(r))
        for order, rr in enumerate(r for r in merged if len(r) >= min_bar_px):
            xlo, xhi = rr[0], rr[-1]
            w = xhi - xlo + 1
            xc = (xlo + xhi) // 2
            filled = np.where(col[:, xlo:xhi + 1].any(axis=1))[0]

            # (3) which way does this bar grow? The value is the end away from
            # the baseline; DOWN bars are read at their bottom, UP bars at their
            # top. Decided per bar, because one panel can carry both.
            down = abs(float(filled.max()) - zero_row) > abs(float(filled.min()) - zero_row)
            fill_top = int(filled.max() if down else filled.min())
            step = 1 if down else -1

            # (1) outline centre, not the fill edge
            span = range(fill_top, min(dark.shape[0] - 1, fill_top + 70) + 1) if down \
                else range(max(0, fill_top - 70), fill_top + 1)
            prof = [(y, int(dark[y, xlo:xhi + 1].sum())) for y in span]
            wide = [y for y, c in prof if c >= 0.5 * w]
            groups = runs(wide)
            outline = (groups[0] if down else groups[-1]) if wide else [fill_top]
            top_c = (outline[0] + outline[-1]) / 2.0

            # (2) a cap counts only if a stem reaches the bar end, on the far
            # side from the baseline
            edge = outline[-1] if down else outline[0]
            rng = (range(edge + 1, min(dark.shape[0], edge + max_whisker_px)) if down
                   else range(max(0, edge - max_whisker_px), edge))
            stem_rows = [y for y in rng
                         if dark[y, xc - stem_half_width:xc + stem_half_width + 1].sum() >= 3]
            allseg = runs(stem_rows, 2)
            # stem_required=False reproduces the defective behaviour on purpose,
            # so the regression suite can show the glyph trap is real rather than
            # merely asserting the fixed reader happens to be right.
            if stem_required:
                seg = [s for s in allseg
                       if ((s[0] <= edge + 4) if down else (s[-1] >= edge - 4))]
            else:
                seg = (allseg[-1:] if down else allseg[:1]) if allseg else []
            cap_c, stem_ok = None, False
            if seg:
                s = seg[0] if down else seg[-1]
                stem_ok = True
                # Centre of the cap STROKE, not its top edge. Taking s[0] alone
                # put the cap half a stroke high and inflated every dispersion.
                # The width band must be generous: a cap is anywhere from a
                # third to most of the bar width, and an upper bound of 0.55*w
                # silently rejected real caps and fell back to the edge.
                # The cap sits at the OUTER end of the whisker and its stroke
                # extends back toward the bar, so walk inward from `far` - the
                # opposite of the direction the bar grows.
                far = s[-1] if down else s[0]
                inward = -step
                caps = []
                for n in range(8):
                    y = far + inward * n
                    if not (0 <= y < dark.shape[0]):
                        break
                    if 0.10 * w <= dark[y, xlo:xhi + 1].sum() <= 0.95 * w:
                        caps.append(y)
                    elif caps:
                        break
                cap_c = (caps[0] + caps[-1]) / 2.0 if caps else float(far)

            out.append(dict(
                series=sname, order=order, x=xc, bar_width=w,
                top_px=top_c, fill_top_px=float(fill_top), cap_px=cap_c,
                mean=y2v(top_c),
                mean_if_read_at_fill_edge=y2v(float(fill_top)),
                dispersion=None if cap_c is None else y2v(cap_c) - y2v(top_c),
                Bar_Direction="DOWN" if down else "UP",
                Bar_Top_Definition="OUTLINE_CENTER",
                Errorbar_Stem_Confirmed="TRUE" if stem_ok else "FALSE",
                calib_max_resid=resid,
            ))
    out.sort(key=lambda d: (d["series"], d["x"]))
    if n_slots:
        # Assign each bar to the nearest of n_slots evenly spaced positions
        # instead of counting them off left to right. A bar that could not be
        # seen - a value so close to the baseline that its fill is covered -
        # otherwise shifts every label after it, which silently renames real
        # readings instead of leaving a hole the grid engine can catch.
        xs_all = [d["x"] for d in out]
        if xs_all:
            lo, hi = min(xs_all), max(xs_all)
            pitch = (hi - lo) / (n_slots - 1) if n_slots > 1 else 1.0
            for s in set(d["series"] for d in out):
                grp = [d for d in out if d["series"] == s]
                gl = min(d["x"] for d in grp)
                for d in grp:
                    d["order"] = int(round((d["x"] - gl) / pitch)) if pitch else 0
                    d["slot_residual_px"] = abs((d["x"] - gl) - d["order"] * pitch)
    else:
        for s in set(d["series"] for d in out):
            for i, d in enumerate([d for d in out if d["series"] == s]):
                d["order"] = i
    return out
