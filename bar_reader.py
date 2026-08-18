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


def axis_column(dark, panel_box, coverage=0.6):
    """The pixel column of the panel's y axis, or None.

    The leftmost column whose ink spans most of the panel's height. Used to keep
    the category scan below off the axis and its printed label, which are ink at
    every row and would otherwise read as a seventh category.
    """
    x0, x1, y0, y1 = (int(v) for v in panel_box)
    sub = dark[y0:y1, x0:x1]
    if not sub.size:
        return None
    hits = [x0 + i for i, v in enumerate(sub.sum(axis=0))
            if v > coverage * sub.shape[0]]
    return min(hits) if hits else None


def x_category_columns(dark, panel_box, count, band=34, step=4, gap=8,
                       uniformity=0.05):
    """The x pixel of each printed category on a categorical panel, or None.

    WHY THIS EXISTS. `read_bar_panel` numbers its bars by nearest DECLARED slot
    when it is given `x_positions` and by SEQUENCE over the runs it found when it
    is not. Sequence is right only while every category has a visible bar. A bar
    whose mean is zero draws nothing at all, so the row SHORTENS instead of
    leaving a hole and every bar after the gap inherits the label before it -
    which is what happened to `323|FIG2|DAP`, where `DI19` is a printed error bar
    around a mean of zero and two cells were filed one timepoint early.

    The figure itself has the answer, printed at every category whether or not
    that category drew a bar. This slides a band down the panel and keeps the one
    that yields EXACTLY `count` clusters of ink at nearly even spacing: on a panel
    with a gap the bars cannot produce that and the printed labels can, so the
    labels win without this having to know which it read.

    NONE RATHER THAN A GUESS. No band that qualifies means the panel does not
    say where its categories are, and the caller must refuse - a grid fitted from
    the bars that WERE found is exactly the reading that produced the defect.
    `uniformity` is the coefficient of variation of the gaps; the twelve panels of
    publication 323 come in under 0.013, and a row of clusters that is not evenly
    spaced is not a category axis.
    """
    # TWO OR MORE, because the contract is a SPACING and one cluster has none.
    # `count=1` used to fall through the loop and return None whatever the panel
    # printed, which reads as "this panel does not say" when the truth is that
    # this function cannot be asked. A one-category panel needs a different
    # question and does not have one here.
    if count < 2:
        raise ValueError("a category axis needs at least two categories to have "
                         "a spacing; got count=%r" % (count,))
    x0, x1, y0, y1 = (int(v) for v in panel_box)
    axis = axis_column(dark, panel_box)
    left = (axis + 6) if axis is not None else x0
    best = None
    for top in range(y0, max(y0 + 1, y1 - band), step):
        strip = dark[top:top + band, x0:x1]
        if not strip.size:
            continue
        cols = [x0 + i for i, v in enumerate(strip.sum(axis=0))
                if v and x0 + i > left]
        groups = [g for g in runs(cols, gap) if len(g) > 2]
        if len(groups) != count:
            continue
        centres = [(g[0] + g[-1]) / 2.0 for g in groups]
        gaps = [b - a for a, b in zip(centres, centres[1:])]
        if not gaps or min(gaps) <= 0:
            continue
        mean = sum(gaps) / len(gaps)
        spread = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
        score = spread / mean
        if score > uniformity:
            continue
        span = centres[-1] - centres[0]
        # The most even row wins, and the widest of equally even rows: a band
        # that clipped the outermost category is even and short.
        if best is None or (score, -span) < (best[0], -best[1]):
            best = (score, span, top, centres)
    return None if best is None else best[3]


#: The three masks this reader was born with, and the only values `Mask_Key`
#: may take. Lower case, because that is the key `colour_masks` returns - a
#: manifest saying `Mask_Key=BLUE` used to validate and then raise `KeyError`
#: inside the reader, which aborts the whole batch as an INTERNAL_ERROR.
#: `batch_manifests.BAR_COLOR_MASK_KEYS` must equal this; the suite asserts it.
BUILTIN_MASK_KEYS = ("blue", "red", "dark")


def colour_masks(rgb, declared=None, threshold=110):
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
        # WHAT COUNTS AS INK. `dark` is what finds outlines, stems and caps,
        # and 110 was a number tuned on one publication. Publication 177 draws
        # its error bars in a grey whose median is 128, so at 110 the whiskers
        # of a whole figure are invisible: every cell came back NO_VARIANCE
        # while the bars themselves read cleanly. A greyscale print does not owe
        # this reader a particular ink level, so the level is declarable
        # (`threshold`, as BAR_MONO and the line readers already take it) and
        # 110 stays the default.
        "dark": a.mean(axis=2) < threshold,
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


def _covers(mask, px, py, radius=1):
    """Does this mask cover the pixel a bar was sampled at?"""
    r0, r1 = max(0, int(round(py)) - radius), int(round(py)) + radius + 1
    c0, c1 = max(0, int(round(px)) - radius), int(round(px)) + radius + 1
    return bool(mask[r0:r1, c0:c1].any())


def _claimed_by_others(others, px, py, radius=1):
    """How many OTHER series masks cover this bar's own ink."""
    return sum(1 for mask in others if _covers(mask, px, py, radius))


def joined_to_baseline(col, panel_box, band_lo, band_hi):
    """The part of `col` that is ONE PIECE OF INK reaching the baseline band.

    WHY A COLUMN TEST IS NOT ENOUGH. `read_bar_panel` asks each column whether
    this colour appears anywhere near the baseline, and keeps the column if it
    does. On a hard-edged drawing that is the same question as "is this column
    part of a bar", and on a printed figure it is not.

    A rasterised journal page lays a ramp of intermediate greys along every
    edge, and a JPEG scatters more of them across the middles. The MIDDLE grey
    of a three-group palette lands on those ramps: masking #666666 on
    publication 177 marks the edges of the black bars, the edges of the light
    grey bars, the fade of the baseline rule and the descenders of the
    significance brackets. Each of those has SOME pixel near the baseline, so
    every one of their columns passed, the fragment-merge rule joined them, and
    the third group's bar came back as a run three bars wide whose top belonged
    to somebody else - 656 pg/ml against a printed 380, and 100 against 24.

    Dust is not a bar because it is not JOINED to anything: the smear along a
    neighbour's edge is a scatter of separate specks, and this returns only the
    connected components that reach the band. Measured on 177's six panels, the
    three real bars per panel survive at 96-100% of their own bounding box and
    every smear disappears; before this the same panels produced up to seven
    candidate runs for one bar.

    Components are grown over ROW RUNS rather than pixels - a few thousand runs
    against a million pixels - so this costs nothing next to building the mask.
    """
    x0, x1, y0, y1 = (int(v) for v in panel_box)
    parent, rows, prev = {}, {}, []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for y in range(y0, y1):
        idx = np.flatnonzero(col[y, x0:x1])
        cur = []
        for r in runs((idx + x0).tolist()):
            key = (y, r[0])
            parent[key] = key
            for plo, phi, pkey in prev:
                # 8-connected: a diagonal touch is still one piece of ink, and
                # an antialiased edge is exactly one pixel wide per row.
                if r[0] <= phi + 1 and plo <= r[-1] + 1:
                    union(pkey, key)
            cur.append((r[0], r[-1], key))
        rows[y] = cur
        prev = cur
    seeds = {find(k) for y in range(max(y0, band_lo), min(y1, band_hi))
             for _lo, _hi, k in rows.get(y, ())}
    out = np.zeros_like(col)
    for y, cur in rows.items():
        for lo, hi, key in cur:
            if find(key) in seeds:
                out[y, lo:hi + 1] = True
    return out


def read_bar_colour_panel(image, panel_box, declared_colours=None, threshold=110,
                          ticks=None, series=None, min_bar_px=15,
                          stem_half_width=3, max_whisker_px=90, stem_required=True,
                          baseline_value=0.0, y_calibration=None, x_positions=None,
                          slot_tolerance_px=None):
    """BAR_COLOR from a RASTER: build the masks at the declared ink level, read.

    `read_bar_panel` is given masks and never sees the image, so the ink level
    could not be one of its parameters - and `READER_OPTIONS` promises that an
    option applying to a mark type names a parameter of that mark's reader. This
    is the function that keeps the promise: every BAR_COLOR option is in its
    signature, and `run_batch.reader_functions` points here.
    """
    masks = colour_masks(image, declared=declared_colours, threshold=threshold)
    return read_bar_panel(
        masks, panel_box, ticks=ticks, series=series, min_bar_px=min_bar_px,
        stem_half_width=stem_half_width, max_whisker_px=max_whisker_px,
        stem_required=stem_required, baseline_value=baseline_value,
        y_calibration=y_calibration, x_positions=x_positions,
        slot_tolerance_px=slot_tolerance_px)


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
        # A BAR GROWS FROM THE BASELINE. A significance bracket does not: it is a
        # rule floating above the bars, drawn in the same ink, and its columns
        # joined two bars into one run that then read as a single bar whose top
        # was the bracket. Requiring a column to carry ink AT the baseline is
        # what a bar is, and it costs a zero-height bar nothing - its error bar
        # still stands there.
        # The band has to clear the ZERO LINE, which is drawn over the fill: on
        # publication 323 a bar's own colour is missing for the few rows the
        # rule covers, and a band that only looked at those rows found no bar at
        # all - 107 readings became 81. So the line's own thickness is measured
        # here (rows near the baseline whose ink spans the panel) and the band
        # reaches past it.
        stroke = sum(1 for y in range(max(y0, int(round(zero_row)) - 6),
                                      min(y1, int(round(zero_row)) + 7))
                     if dark[y, x0:x1].sum() >= 0.6 * (x1 - x0))
        reach = stroke + 8
        band_lo = max(y0, int(round(zero_row)) - reach)
        band_hi = min(y1, int(round(zero_row)) + reach + 1)
        col = joined_to_baseline(col, (x0, x1, y0, y1), band_lo, band_hi)
        # THE RULE ITSELF IS NOT A BAR. Where the baseline is drawn in a bar's
        # own ink - which it is whenever a group is printed black - the rule
        # runs across the panel behind the whole row, and a column of it is not
        # a column of any bar. On `greyscale_group_fixture.png` it welded the y
        # axis to the first bar: the run came out 132 pixels wide against a
        # drawn 100, its centre moved 17 pixels off the stem, and the error bar
        # was lost. So a bar's columns are the columns with ink ABOVE the rule,
        # whose thickness is the `stroke` measured just above.
        rule_lo = max(y0, int(round(zero_row)) - stroke)
        rule_hi = min(y1, int(round(zero_row)) + stroke + 1)
        outside = col.copy()
        outside[rule_lo:rule_hi, :] = False
        xs = [x for x in range(x0, x1) if outside[:, x].any()]
        # A bar whose value is near the baseline can be split into two colour
        # slivers: its own stroke plus the zero line cover the fill except at the
        # left and right edges. Two fragments of one bar sit far closer together
        # than two bars do, so merge across a gap that is small relative to the
        # fragments themselves. Measured on a real figure: fragment gaps 4-16 px
        # against widths 17-29, neighbouring-bar gaps 67-70 against widths ~61.
        def merge(columns):
            out_runs = []
            for r in (p for p in runs(columns, 3) if len(p) >= 8):
                if out_runs and (r[0] - out_runs[-1][-1]) < 0.5 * (len(out_runs[-1])
                                                                   + len(r)):
                    out_runs[-1] = (out_runs[-1]
                                    + list(range(out_runs[-1][-1] + 1, r[0])) + r)
                else:
                    out_runs.append(list(r))
            return [r for r in out_runs if len(r) >= min_bar_px]

        merged = merge(xs)
        # ...AND A BAR OF HEIGHT ZERO IS NOTHING BUT THE RULE. Publication 323
        # has two: `-0.318` and `0.421` on its change-from-zero panels, two and
        # three rows of colour lying inside the line, each with an error bar
        # standing on it. Dropping every rule-only run would delete them, and
        # keeping every one puts back the phantoms. What tells them apart is
        # what is drawn ON them: a run with no ink above the rule is a bar only
        # if a stem reaches out of it, which is decided below with the same test
        # every other bar's whisker gets.
        flat = [x for x in range(x0, x1)
                if col[:, x].any() and not outside[:, x].any()]
        candidates = ([(r, False) for r in merged]
                      + [(r, True) for r in merge(flat)])
        for order, (rr, rule_only) in enumerate(candidates):
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

            # (1) outline centre, not the fill edge - and the outline has to be
            # ink the fill RUNS INTO. The group nearest the fill edge was taken
            # whatever the gap between them, which is two mistakes in one: a
            # bracket sixty pixels above a bar was read as its outline, and when
            # the whisker is the bar's OWN colour the fill edge is the whisker's
            # tip, with the bar ninety pixels below and no outline in the window
            # at all. On publication 177 that returned the cap as the mean - 314
            # against a printed 205 - silently.
            def _outline_at(anchor):
                span = (range(anchor, min(dark.shape[0] - 1, anchor + 70) + 1)
                        if down else range(max(0, anchor - 70), anchor + 1))
                prof = [(y, int(dark[y, xlo:xhi + 1].sum())) for y in span]
                wide = [y for y, c in prof if c >= 0.5 * w]
                if not wide:
                    return None
                return runs(wide)[0] if down else runs(wide)[-1]

            # ...AND WITH NO WHITE BETWEEN IT AND THE BAR. Proximity is the
            # wrong test for this: on a JPEG the topmost pixels of a fill fade
            # out over several rows, so "within two pixels of the fill edge"
            # rejected the real outline of nineteen of publication 323's bars
            # and moved their frozen means by up to 5.5 units. CONNECTEDNESS is
            # the test that holds - ink all the way from the outline down into
            # the bar - and it is what the bracket fails. The bracket of
            # `whisker_bracket_fixture.png` drops a short vertical onto each bar
            # it spans, so its top row IS the top row of this colour in these
            # columns and the test above accepts it. What it is not is connected:
            # a hundred rows of white lie between the bracket's descender and
            # the whisker below it, and a bar's outline never has white under it.
            # ANY ink, not this series' colour: a bar's outline stroke is
            # commonly darker than its fill and so is not in the colour mask at
            # all. What must be unbroken is the paper being marked, which is
            # what tells an outline apart from a bracket floating over white.
            ink = dark[:, xlo:xhi + 1].any(axis=1)

            def _touches_body(g):
                if body is None:
                    return True
                near_g = g[0] if down else g[-1]
                far_body = body[-1] if down else body[0]
                lo, hi = sorted((int(near_g), int(far_body)))
                # MEASURED, not chosen: over publication 323's 72 bars the run
                # from the outline into the fill has no unmarked row at all in
                # 70 of them and exactly one in the other two - a JPEG dropping
                # a single faint row. The bracket of the fixture has more than a
                # hundred. Two orders of magnitude apart, so two rows is the
                # line and nothing near it is a judgement call.
                return int((~ink[lo:hi + 1]).sum()) <= 2

            body_rows = [y for y in range(int(filled.min()), int(filled.max()) + 1)
                         if col[y, xlo:xhi + 1].sum() >= 0.5 * w]
            body = max(runs(body_rows), key=len) if body_rows else None
            outline = _outline_at(fill_top)
            if outline is not None and not _touches_body(outline):
                outline = None
            if outline is None:
                # The fill edge is not a bar edge. The bar is the WIDE part of
                # this colour; a whisker is a few pixels across and cannot be.
                if body is not None:
                    anchor = body[-1] if down else body[0]
                    outline = _outline_at(anchor) or [anchor]
                else:
                    # Nothing wide anywhere: a bar whose mean is at the baseline
                    # draws no bar, and its error bar is all there is to read.
                    outline = [fill_top]
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
                # NO CAP MEANS NO DISPERSION. This used to fall back to `far` -
                # the far end of the stem run - and report it as a cap, under
                # `DIRECT_CONNECTED_CAP`, which is a claim that a cap was
                # measured. Two things make it false, and publication 177 has
                # both. A JPEG can drop four rows out of a stem, and then the
                # run stops at the hole and its end is the middle of the
                # whisker: 2.2 pg/ml reported against a printed 6. And a cap can
                # be printed lighter than the declared ink level, so only the
                # stem is ink and its end is half a stroke off the truth.
                # Neither can be told from a bracket's descender without a
                # constant, and a cell with no dispersion goes to a person -
                # which is the outcome a figure this reader cannot finish
                # reading is supposed to have.
                cap_c = (caps[0] + caps[-1]) / 2.0 if caps else None

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
                # THE METHOD DESCRIBES WHAT PRODUCED THE NUMBER, so with no cap
                # there is no number and no method. Asking about the stem first
                # let a stem-confirmed bar with no cap say DIRECT_CONNECTED_CAP
                # beside an empty dispersion.
                Dispersion_Method=("NO_DISPERSION" if cap_c is None
                                   else "DIRECT_CONNECTED_CAP" if stem_ok
                                   else "UNSTEMMED_CAP"),
                # Sampled INSIDE the bar rather than at its top edge: the top is
                # an outline a neighbouring colour's antialiasing can reach, and
                # what is being asked is whether another series' mask claims this
                # bar's own ink.
                mask_overlap=_claimed_by_others(
                    others_of.get(sname, ()), xc,
                    top_c + (-4 if down else 4)),
                # AND WHETHER THIS SERIES' OWN MASK CLAIMS IT, at the same
                # pixel. `mask_overlap=0` says no OTHER declared colour covers
                # this ink; it does not say the colour this series declares
                # does. Without both, `MEASURED_COLOUR` rests on the reader
                # having found the bar in its own mask - true, and not written
                # down anywhere a checker could read. One number each, from the
                # same sample point, so the pair is comparable.
                own_mask_hit=int(_covers(masks[key], xc,
                                         top_c + (-4 if down else 4))),
                own_mask_key=key,
                Errorbar_Stem_Confirmed="TRUE" if stem_ok else "FALSE",
                calib_max_resid=resid,
                _rule_only=rule_only,
            ))
    out = [d for d in out
           if not d.pop("_rule_only") or d["Errorbar_Stem_Confirmed"] == "TRUE"]
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
