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


#: The three masks this reader was born with, and the only values `Mask_Key`
#: may take. Lower case, because that is the key `colour_masks` returns - a
#: manifest saying `Mask_Key=BLUE` used to validate and then raise `KeyError`
#: inside the reader, which aborts the whole batch as an INTERNAL_ERROR.
#: `batch_manifests.BAR_COLOR_MASK_KEYS` must equal this; the suite asserts it.
BUILTIN_MASK_KEYS = ("blue", "red", "dark")


def colour_masks(rgb, declared=None):
    """Boolean masks from an RGB uint8 array.

    `blue`, `red` and `dark` are the three this reader was born with, tuned on
    one publication. They are kept because `dark` is what finds outlines and
    error bars, and because two worked examples name them - but they are not a
    colour model. A figure drawn in green and purple, or in two pastels, had no
    way through: `Colour_Hex` was required on the series manifest, validated,
    and then ignored, while `colour_tolerance` was offered as a BAR_COLOR
    option whose reader keyword is None.

    `declared` is {name: (hex, tolerance)} and produces one mask per series from
    what the manifest actually says, which is the version that generalises.
    """
    a = np.asarray(rgb).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    out = {
        "blue": (B - R > 50) & (B - G > 40) & (B > 110),
        "red": (R - G > 60) & (R - B > 60) & (R > 110),
        "dark": a.mean(axis=2) < 110,
    }
    for name, (colour, tolerance) in (declared or {}).items():
        out[name] = colour_mask(a, colour, tolerance)
    return out


def colour_mask(rgb, colour, tolerance=60.0):
    """Pixels within `tolerance` of `colour`, by Euclidean RGB distance.

    Euclidean RGB is crude next to a perceptual space, and it is what the
    monochrome and marker readers already use for the same job - one distance
    metric across the package beats a better one in a single reader. The
    tolerance is per series and declared, because how far apart two printed
    colours are is a fact about the figure.
    """
    a = np.asarray(rgb).astype(float)
    if isinstance(colour, str):
        text = colour.strip().lstrip("#")
        colour = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    target = np.asarray(colour, dtype=float)
    return np.sqrt(((a - target) ** 2).sum(axis=2)) <= float(tolerance)


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


def _claimed_by_others(others, px, py, radius=1):
    """How many OTHER series masks cover this bar's own ink."""
    hits = 0
    for mask in others:
        r0, r1 = max(0, int(round(py)) - radius), int(round(py)) + radius + 1
        c0, c1 = max(0, int(round(px)) - radius), int(round(px)) + radius + 1
        if mask[r0:r1, c0:c1].any():
            hits += 1
    return hits


def read_bar_panel(masks, panel_box, ticks=None, series=None, min_bar_px=15,
                   stem_half_width=3, max_whisker_px=90, stem_required=True,
                   baseline_value=0.0, y_calibration=None, x_positions=None,
                   slot_tolerance_px=None):
    """Read every bar of one panel.

    masks         : dict from colour_masks
    panel_box     : (x0, x1, y0, y1) bounding the plot area
    y_calibration : a shared `mark_readers.AxisCalibration`. LINEAR or LOG.
    ticks         : [(value, pixel_row), ...] - only a fallback for direct
                    callers; the batch layer always passes `y_calibration`
    series        : {series_name: mask_key}, e.g. {"SUPINE": "blue"}
    x_positions   : {Position_ID: x_pixel} declared in `position_manifest.csv`.
                    Bars are matched to these anchors, never to each other.

    Each returned bar carries the provenance flags the template requires.

    This used to fit its own linear map with `np.polyfit`, which meant
    `Axis_Y_Scale=LOG` validated, ran, and produced values off by an order of
    magnitude - the only monochrome-free reader that did not use the shared
    calibration was also the only one that could not read a log axis.
    """
    from mark_readers import AxisCalibration, GeometryResolutionError

    x0, x1, y0, y1 = panel_box
    dark = masks["dark"]
    if y_calibration is None:
        if not ticks:
            raise ValueError("read_bar_panel needs y_calibration or ticks")
        y_calibration = AxisCalibration.from_points(ticks)
    y2v = y_calibration.pixel_to_value
    resid = float(getattr(y_calibration, "max_residual", 0.0))
    # Pixel row of the baseline the bars grow from. On a log axis zero is not a
    # row on the paper, and the old code inverted a second linear fit to invent
    # one - a number inside the panel, used silently to decide which way every
    # bar grows.
    if y_calibration.scale == "LOG" and baseline_value <= 0:
        raise GeometryResolutionError(
            "baseline_value must be positive on a LOG axis, got %r"
            % baseline_value)
    zero_row = y_calibration.value_to_pixel(baseline_value)
    out = []
    # Every other series' mask, for the overlap question below. Two declared
    # colours closer than the sum of their tolerances make two masks over one
    # printed bar, and reading them independently fills the grid twice.
    others_of = {sname: [masks[k] for other, k in series.items()
                         if other != sname and k in masks]
                 for sname in series}
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
                # A magnitude, always. The whisker points away from zero, so a
                # down bar's signed difference is negative - and the grid gate
                # rejects Dispersion_Value <= 0, so a correctly-read down bar
                # failed end to end while both components had passing tests.
                # Direction is kept, in the field whose job that is.
                dispersion=None if cap_c is None else abs(y2v(cap_c) - y2v(top_c)),
                dispersion_signed=(None if cap_c is None
                                   else y2v(cap_c) - y2v(top_c)),
                Bar_Direction="DOWN" if down else "UP",
                Bar_Top_Definition="OUTLINE_CENTER",
                # WHICH SERIES this bar is, and how its number was got. The bar
                # was found in a mask built from the colour this series declares,
                # so the identity rests on measured colour - the same claim
                # LINE_COLOR makes, for the same reason.
                #
                # WHICH x IT SITS AT is a different question with its own field:
                # `Position_Assignment` below says whether the label came from a
                # declared anchor or from counting left to right. A provenance
                # method for the series identity does not speak for that, and
                # `run_batch` refuses SEQUENTIAL outright rather than pricing it.
                Identity_Method="MEASURED_COLOUR",
                Value_Method="BAR_OUTLINE_CENTER",
                # A cap is only accepted here when a vertical stem physically
                # connects it to the bar top - the whole reason this reader
                # exists in the shape it does, because significance glyphs sit
                # exactly where a cap is and are the same colour. Recorded as
                # provenance as well as a boolean, so the tier follows it.
                Dispersion_Method=("DIRECT_CONNECTED_CAP" if stem_ok
                                   else "NO_DISPERSION" if cap_c is None
                                   else "UNSTEMMED_CAP"),
                # Sampled INSIDE the bar rather than at its top edge: the top is
                # an outline a neighbouring colour's antialiasing can reach, and
                # what is being asked is whether another series' mask claims this
                # bar's own ink.
                mask_overlap=_claimed_by_others(
                    others_of.get(sname, ()), xc,
                    top_c + (-4 if down else 4)),
                Errorbar_Stem_Confirmed="TRUE" if stem_ok else "FALSE",
                calib_max_resid=resid,
            ))
    out.sort(key=lambda d: (d["series"], d["x"]))
    if x_positions:
        # Identity is declared, never inferred. Each bar goes to the NEAREST
        # DECLARED anchor, and one that is not near any of them is dropped so
        # the cell stays missing for the grid gate to name.
        #
        # The previous version rebuilt a pitch from the detected bars: global
        # min/max for the spacing, each series' own leftmost bar for the origin.
        # Two failure modes followed, both silent. A series whose FIRST bar was
        # invisible had every later bar shifted one label left. And when a whole
        # slot went undetected the derived pitch collapsed - measured 123 px to
        # 108 px on the signed fixture - so a real slot-4 bar was emitted as
        # slot 5. Neither produced a large residual, so the residual could not
        # have caught them even if anything had been reading it.
        anchors = sorted(x_positions.items(), key=lambda kv: float(kv[1]))
        spans = [abs(float(b[1]) - float(a[1]))
                 for a, b in zip(anchors, anchors[1:])]
        tolerance = (float(slot_tolerance_px) if slot_tolerance_px is not None
                     else (0.5 * min(spans) if spans else float(x1 - x0)))
        kept = []
        for d in out:
            best, distance = None, None
            for i, (pid, px) in enumerate(anchors):
                gap = abs(d["x"] - float(px))
                if distance is None or gap < distance:
                    best, distance = i, gap
            if best is None or distance > tolerance:
                continue
            d["order"] = best
            d["x_label"] = anchors[best][0]
            d["slot_residual_px"] = float(distance)
            d["Position_Assignment"] = "DECLARED_ANCHOR"
            kept.append(d)
        # Two bars of one series claiming one position is an ambiguity, not a
        # duplicate: neither can be trusted, so both go.
        seen = {}
        for d in kept:
            seen.setdefault((d["series"], d["order"]), []).append(d)
        out = [group[0] for group in seen.values() if len(group) == 1]
        out.sort(key=lambda d: (d["series"], d["order"]))
    else:
        # No declared anchors: count the bars off left to right and SAY SO. This
        # is the inference the batch layer must never do - a bar that could not
        # be seen shifts every label after it - so the marker is on every row
        # and `run_batch` refuses it. It stays reachable for direct callers
        # working a single figure by hand, where the panel is in front of them.
        for s_name in set(d["series"] for d in out):
            for i, d in enumerate([d for d in out if d["series"] == s_name]):
                d["order"] = i
                d["Position_Assignment"] = "SEQUENTIAL"
    return out
