"""Draw what the reader saw, on top of what it read it from.

A WebPlotDigitizer project is the right artifact for re-deriving a number. It is
the wrong artifact for the question a reviewer actually has to answer 116 times,
which is "did it put the marks in the right places". That question is answered
by looking, and looking needs a picture.

So each auto-digitized panel also gets one PNG: the panel as printed, every mark
the reader placed drawn on it, and each mark labelled with the identity the
manifest gave it and the value that identity will carry into the analysis. If
the bar the overlay calls `FLUID / POST` is the bar a human would call
`FLUID / POST`, the cell is right; if it is one bar to the left, the reviewer
sees that in a second rather than reconstructing it from a tar of JSON.

The overlay is a review aid and nothing else. It is never read back, nothing is
derived from it, and its absence cannot change a value - it exists so that the
approval in `value_review.csv` is a judgement about the extraction rather than a
signature on a filename.
"""
import json
import os

from PIL import Image, ImageDraw

#: Distinct enough to tell apart on a greyscale journal figure, in order.
SERIES_COLOURS = ((214, 39, 40), (31, 119, 180), (44, 160, 44), (148, 103, 189),
                  (255, 127, 14), (23, 190, 207))
MISSING_COLOUR = (120, 120, 120)
PAD = 12
FOOTER = 58
#: One more line of footer, for the key to the star on an inferred label.
INFERRED_NOTE_HEIGHT = 16
#: Room to the right for labels, so a value is never clipped by the panel edge.
LABEL_MARGIN = 150

#: Why an overlay could not be drawn, in the order it happened.
_FAILURES = []


def reset_failures():
    """Forget the previous run's drawing failures.

    `_FAILURES` is module state, and a batch runner processing 116 publications
    in one process is the normal case here - so without this the second run's
    stamp inherits the first run's "3 overlays could not be drawn", naming
    panels that are not in it. Called at the top of every `run_batch`.
    """
    _FAILURES.clear()


def failures():
    return list(_FAILURES)


def _font():
    """The default bitmap font, deliberately.

    A TrueType face would be prettier and is not installed everywhere; an
    overlay that raises on a machine without DejaVu is worse than a plain one.
    """
    try:
        from PIL import ImageFont
        return ImageFont.load_default()
    except Exception:                                            # pragma: no cover
        return None


def _mark_y(mark):
    """The pixel row the reader called this mark's centre.

    Bars report `top_px`, markers report `marker_center_px`, scatter points
    report `point_px_y`. They are the same question asked of three readers.
    """
    for key in ("marker_center_px", "top_px", "point_px_y", "median_px"):
        value = mark.get(key)
        if value is not None:
            return float(value)
    return None


#: Reader fields that say HOW a mark's series was decided, and the one value in
#: each that means "off the ink". Anything else in one of these fields is an
#: inference and the overlay stars it.
#:
#: THIS LIST IS NOT THE GUARD IT WAS FIRST DOCUMENTED AS. The comment here used
#: to claim that "a provenance field this file has never heard of would
#: otherwise pass as a measurement", which is exactly backwards: a whitelist of
#: FIELD NAMES protects against an unknown TOKEN in a field it knows, and is
#: blind to a field it does not. A future reader emitting
#: `marker_identity_source = "ELIMINATION"` and forgetting to register it here
#: would have drawn a plain, unstarred mark, and the docstring would have said
#: it could not happen. A guarantee written down and not implemented is worse
#: than the gap it describes.
#:
#: So the real guard is the SUFFIX below, not this list. A key that looks like
#: provenance and is not understood makes the mark UNKNOWN rather than
#: measured: the picture asks the reviewer to look instead of quietly claiming
#: the ink named it.
IDENTITY_SOURCE_FIELDS = (("line_style_source", "MEASURED"),)

#: How a reader names a provenance field. Everything matching this and not in
#: `IDENTITY_SOURCE_FIELDS` is provenance this picture cannot interpret.
#: A convention can still be side-stepped by a field named nothing like this,
#: and that is a real limit rather than a covered case - `test_mark_readers`
#: pins the convention against what the readers actually emit, which is the
#: only place it can be checked mechanically.
PROVENANCE_SUFFIXES = ("_source", "_method")


#: What an inferred mark's label carries, and the key that explains it. A star,
#: not a phrase: a label has 150 pixels and a sentence in each would cover the
#: panel it points at.
INFERRED_MARK_SUFFIX = " *"


#: What a mark carrying provenance this file cannot interpret is labelled with.
UNKNOWN_MARK_SUFFIX = " ?"


def inferred_note(marks):
    """The footer key for starred and questioned marks, or "" if none."""
    lines = []
    starred = sum(1 for m in marks if _inferred_identity(m))
    if starred:
        lines.append("* %d mark(s): SERIES named by elimination, not read off "
                     "the ink - check these first" % starred)
    unknown = sorted({key for m in marks for key in unreadable_provenance(m)})
    if unknown:
        # Named, not just counted: the fix is to register the field, and the
        # person reading this picture is the person who can say so.
        lines.append("? %d mark(s) carry provenance this overlay cannot read "
                     "(%s) - treat as unverified" % (
                         sum(1 for m in marks if unreadable_provenance(m)),
                         ", ".join(unknown)))
    return "\n".join(lines)


def mark_label(mark):
    """What one mark says about itself on the picture."""
    label = "%s/%s" % (mark.get("series", "?"), mark.get("x_label", "?"))
    value = mark.get("mean", mark.get("median"))
    if value is not None:
        label += " %.4g" % float(value)
    # WHICH SERIES A MARK BELONGS TO IS NOT ALWAYS MEASURED. A monochrome line
    # reader whose window was too blinded to measure a stroke pattern names the
    # last curve by elimination, and that cell is the one a reviewer should
    # look at hardest - it is the whole question this picture exists to answer.
    # Unmarked, it looked exactly like a cell read off the ink.
    if _inferred_identity(mark):
        label += INFERRED_MARK_SUFFIX
    if unreadable_provenance(mark):
        label += UNKNOWN_MARK_SUFFIX
    return label


def _inferred_identity(mark):
    """True when this mark's SERIES was reasoned to rather than measured."""
    for field, measured in IDENTITY_SOURCE_FIELDS:
        value = str(mark.get(field, "") or "")
        if value and value != measured:
            return True
    return False


def unreadable_provenance(mark):
    """Provenance keys on this mark that the overlay cannot interpret.

    A mark is only as trustworthy as the picture's ability to say how it was
    decided. A key this file does not understand is not a measurement and must
    not be drawn as one.
    """
    known = {field for field, _measured in IDENTITY_SOURCE_FIELDS}
    return sorted(key for key in mark
                  if key not in known
                  and any(key.endswith(s) for s in PROVENANCE_SUFFIXES)
                  and str(mark.get(key) or ""))


def draw_panel_overlay(path, image_path, panel_box, marks, title="",
                       subtitle="", series_order=(), label_marks=True):
    """Write one review PNG. Returns the path, or None if it could not be drawn.

    Never raises: a panel that produced values must not fail its run because
    its picture could not be painted.

    `label_marks=False` draws the crosses and the legend without per-mark text.
    A time course has six labelled points and reads well; a scatter has thirty
    and the labels cover the cloud they are there to let somebody judge.
    """
    try:
        source = Image.open(image_path).convert("RGB")
        x0, x1, y0, y1 = (int(v) for v in panel_box)
        crop = source.crop((max(0, x0 - PAD), max(0, y0 - PAD),
                            min(source.width, x1 + PAD),
                            min(source.height, y1 + PAD)))
        ox, oy = max(0, x0 - PAD), max(0, y0 - PAD)

        # A STAR ON A LABEL NEEDS A KEY, and the key needs a line of its own:
        # appended to the subtitle it ran off the right edge of a 570-pixel
        # canvas and read "* 4 of them: the SERIE".
        note = inferred_note(marks)
        footer = FOOTER + INFERRED_NOTE_HEIGHT * len(note.splitlines())
        canvas = Image.new("RGB", (crop.width + LABEL_MARGIN,
                                   crop.height + footer), "white")
        canvas.paste(crop, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _font()

        order = list(series_order) or sorted(
            {str(m.get("series", "")) for m in marks})
        colour_of = {s: SERIES_COLOURS[i % len(SERIES_COLOURS)]
                     for i, s in enumerate(order)}

        draw.rectangle((x0 - ox, y0 - oy, x1 - ox, y1 - oy),
                       outline=(160, 160, 160))

        # Labels are staggered by mark order. Four bars in a 400-pixel panel put
        # four labels on top of each other otherwise, and an unreadable label is
        # the same as no label for the person who has to judge it.
        for slot, mark in enumerate(marks):
            mx = mark.get("x", mark.get("point_px_x"))
            my = _mark_y(mark)
            if mx is None or my is None:
                continue
            mx, my = float(mx) - ox, float(my) - oy
            colour = colour_of.get(str(mark.get("series", "")), MISSING_COLOUR)
            draw.line((mx - 9, my, mx + 9, my), fill=colour, width=2)
            draw.line((mx, my - 5, mx, my + 5), fill=colour, width=2)
            cap = mark.get("cap_px")
            if cap is not None:
                cy = float(cap) - oy
                draw.line((mx, my, mx, cy), fill=colour, width=1)
                draw.line((mx - 5, cy, mx + 5, cy), fill=colour, width=1)
            if not label_marks:
                continue
            label = mark_label(mark)
            ly = min(max(4, my - 5 + (slot % 4 - 1.5) * 13),
                     crop.height - 14)
            draw.line((mx + 10, my, mx + 16, ly + 5), fill=colour, width=1)
            draw.text((mx + 18, ly), label, fill=colour, font=font)

        draw.text((6, crop.height + 6), title or os.path.basename(image_path),
                  fill=(0, 0, 0), font=font)
        draw.text((6, crop.height + 20), subtitle, fill=(70, 70, 70), font=font)
        for i, line in enumerate(note.splitlines()):
            draw.text((6, crop.height + 50 + i * INFERRED_NOTE_HEIGHT), line,
                      fill=(150, 80, 0), font=font)
        x = 6
        draw.text((x, crop.height + 36), "series:", fill=(70, 70, 70), font=font)
        x += 46
        for s in order:
            draw.rectangle((x, crop.height + 36, x + 9, crop.height + 45),
                           fill=colour_of[s])
            draw.text((x + 13, crop.height + 36), s, fill=(70, 70, 70), font=font)
            x += 24 + 7 * len(s)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        canvas.save(path)
        return path
    except Exception as exc:
        # Swallowed on purpose - a picture that could not be painted must not
        # fail a panel that produced values - but not silently: an empty review
        # directory beside twelve panels awaiting review is a lie of omission.
        _FAILURES.append("%s: %s: %s" % (os.path.basename(path),
                                         type(exc).__name__, exc))
        return None


# ---------------------------------------------------------------- row crops
#
# The panel overlay answers "did it put the marks in the right places" for a
# panel. The geometry artifact is finer than a panel - one row per BAR - and a
# reviewer checking eighteen rows of `mono_bar_geometry.csv` against a 600 DPI
# page render is doing arithmetic on page coordinates by hand.
#
# So each geometry row can also get its own PNG: this bar, cropped from the page
# it was measured on, with the four numbers the row claims drawn on it - the
# baseline, the bar top, the error-bar cap and the footprint's own columns.
#
# Same contract as the overlay. A crop is a review aid: it is never read back,
# nothing is derived from it, and its absence cannot change a value. What it
# adds is BINDING - the filename and the caption both carry
# `Geometry_Row_SHA256`, so a picture cannot be quietly matched to the wrong
# row, and a crop left over from an earlier run cannot pass for this one.

#: What each drawn line means, and the colour it is drawn in.
CROP_MARKS = (("baseline", (120, 120, 120)), ("bar top", (214, 39, 40)),
              ("error bar", (31, 119, 180)), ("footprint", (44, 160, 44)))


def _crop_box(record, pad):
    """The page rectangle to cut, from the record alone."""
    box = record.get("panel_box")
    fp = record.get("footprint_px_image")
    if not box:
        return None
    x0, x1, y0, y1 = (int(v) for v in box)
    if fp:
        left, right = int(fp[0]) - pad, int(fp[1]) + pad
    elif record.get("window"):
        left, right = int(record["window"][0]) - pad, int(record["window"][1]) + pad
    else:
        left, right = x0, x1
    # The vertical span comes from the row only when the row FOUND a bar. A
    # refusal carries `zero_px_image` like every other row - it is in the base -
    # and cropping to the baseline alone gives a 48 px strip of the axis, which
    # is a picture of nothing. What a reviewer needs to see for
    # STROKE_SCALE_UNRESOLVED or NO_SEED_SUPPORT is the whole panel.
    if record.get("edge_px_image") is None:
        top, bottom = y0, y1
    else:
        rows = [v for v in (record.get("zero_px_image"),
                            record.get("edge_px_image"),
                            record.get("cap_px_image")) if v is not None]
        top, bottom = int(min(rows)) - pad, int(max(rows)) + pad
    return (max(x0 - pad, left), max(y0 - pad, top),
            min(x1 + pad, right), min(y1 + pad, bottom))


def draw_row_crop(path, image_path, record, pad=24):
    """One geometry row, as the picture it was measured from.

    Takes the record and nothing else - which is why `geometry_rows` puts
    `panel_box`, `zero_px_image` and `footprint_px_image` on every row it
    returns. A crop that needed the spec as well could be drawn from a
    different panel's geometry and look perfectly reasonable.

    Returns the path, or None if it could not be drawn.
    """
    try:
        from PIL import Image as _Image
        _Image.MAX_IMAGE_PIXELS = None
        box = _crop_box(record, pad)
        if box is None:
            raise ValueError("the record carries no panel_box")
        page = _Image.open(image_path).convert("RGB")
        crop = page.crop(box)
        canvas = _Image.new("RGB", (max(crop.width, 320), crop.height + FOOTER),
                            (255, 255, 255))
        canvas.paste(crop, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _font()
        ox, oy = box[0], box[1]

        def hline(page_row, colour):
            if page_row is None:
                return
            y = int(round(float(page_row))) - oy
            if 0 <= y < crop.height:
                draw.line((0, y, crop.width - 1, y), fill=colour, width=1)

        hline(record.get("zero_px_image"), CROP_MARKS[0][1])
        hline(record.get("edge_px_image"), CROP_MARKS[1][1])
        hline(record.get("cap_px_image"), CROP_MARKS[2][1])
        fp = record.get("footprint_px_image")
        if fp:
            for column in (int(fp[0]), int(fp[1])):
                x = column - ox
                if 0 <= x < crop.width:
                    draw.line((x, 0, x, crop.height - 1),
                              fill=CROP_MARKS[3][1], width=1)
        # The caption is the row, in the row's own words. `value` and
        # `dispersion` are what this picture is evidence FOR, and the hash is
        # what says which row it is evidence for.
        def num(key, fmt="%.3f"):
            v = record.get(key)
            return "-" if v is None else fmt % float(v)

        head = "%s / %s / slot %s" % (record.get("figure"), record.get("group"),
                                      record.get("slot"))
        body = "mean %s   dispersion %s   fill %s%s" % (
            num("value"), num("dispersion"),
            record.get("resolved_fill_pattern") or "-",
            "   %s" % record["error"] if record.get("error") else "")
        tail = "row %s   figure %s" % (
            str(record.get("geometry_row_sha256", ""))[:16] or "UNSTAMPED",
            record.get("figure_id"))
        for n, text in enumerate((head, body, tail)):
            draw.text((6, crop.height + 6 + 14 * n), text,
                      fill=(0, 0, 0) if not n else (70, 70, 70), font=font)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        canvas.save(path)
        return path
    except Exception as exc:
        _FAILURES.append("%s: %s: %s" % (os.path.basename(path),
                                         type(exc).__name__, exc))
        return None


def row_crop_name(record):
    """A filename a person can sort and a machine cannot mismatch.

    The row's own identity, then the first twelve characters of its
    measurement hash. Two runs of the same panel that measured it differently
    produce two different files rather than one overwriting the other, and a
    crop cannot be matched to a row it was not drawn from.
    """
    def clean(value):
        text = "-" if value is None else str(value)
        return "".join(c if (c.isalnum() or c in "-_") else "_" for c in text)

    return "%s__%s__slot%s__%s.png" % (
        clean(record.get("figure")), clean(record.get("group")),
        clean(record.get("slot")),
        str(record.get("geometry_row_sha256", "unstamped"))[:12])


def _nice_step(span, want=6):
    """A round axis step: 1, 2 or 5 times a power of ten."""
    if span <= 0:
        return 1.0
    import math
    raw = span / float(max(1, want))
    power = 10.0 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for mult in (1.0, 2.0, 5.0, 10.0):
        if raw <= mult * power:
            return mult * power
    return 10.0 * power                                        # pragma: no cover


def _reference_values(calibration, lo, hi):
    """Round values to hang a faint guide line on, between `lo` and `hi`.

    A LOG axis is not a linear one with different numbers on it. A step of
    `(hi - lo) / 6` on an axis printed 1, 10, 100, 1000 produces 200, 400, 600,
    800 - none of which is a decade, and none of which is beside anything the
    page prints. On LOG the guides are 1, 2 and 5 times each power of ten.
    """
    import math
    if str(calibration.get("scale")) == "LOG":
        out = []
        if lo <= 0:
            lo = min(v for v in (hi,) if v > 0) / 1000.0 if hi > 0 else 1.0
        for power in range(int(math.floor(math.log10(lo))),
                           int(math.ceil(math.log10(hi))) + 1):
            for mult in (1.0, 2.0, 5.0):
                value = mult * 10.0 ** power
                if lo <= value <= hi:
                    out.append(value)
        return out
    step = _nice_step(hi - lo)
    first = math.ceil(lo / step) * step
    out, value = [], first
    while value <= hi + 1e-9:
        out.append(round(value, 6))
        value += step
    return out


def _value_at(calibration, pixel):
    import math
    raw = calibration["slope"] * float(pixel) + calibration["intercept"]
    return math.exp(raw) if calibration.get("scale") == "LOG" else raw


def _pixel_at(calibration, value):
    import math
    raw = math.log(float(value)) if calibration.get("scale") == "LOG" else float(value)
    return (raw - calibration["intercept"]) / calibration["slope"]


def draw_panel_geometry(path, image_path, records, pad=24):
    """The whole panel, with the AXIS in frame and the calibration drawn on it.

    A crop of one bar shows that the reader found the bar. It cannot show that
    the reader knows what the bar is WORTH - that is the axis, and the axis is
    printed outside the panel box. So this picture crops wide enough to include
    the tick labels and then draws, from the calibration each row carries, a
    line at every round value across the panel, labelled.

    If the line the calibration calls 30 does not sit on the printed 30, the
    values are wrong by a scale factor and every bar in the panel is wrong
    together - which is invisible in a per-bar crop, because each bar still
    looks like a bar. That is the failure this picture exists for.

    Every bar's measured top and cap are drawn too, labelled with the value the
    row carries, so "the bar the reader called 5.31" can be read off the
    printed axis by eye.

    Returns a dict - not a path - because what the picture DREW has to be
    checkable without looking at it. Text rendered into a PNG is pixels, not a
    string: a test that searches the file's bytes for a caption finds nothing
    on a correct picture and would have to be written to pass anyway. The same
    dict is written beside the PNG as `<name>.json` and printed into
    `index.html` in words.

        {"path": ..., "axis_ticks": [{"value": 0.0, "pixel": 1234.0}, ...],
         "axis_line_count": 4, "crop_box": [...], "crop_source": "DECLARED",
         "calibration": {...}}

    Returns None if it could not be drawn.
    """
    try:
        from PIL import Image as _Image
        _Image.MAX_IMAGE_PIXELS = None
        rows = [r for r in records if r.get("panel_box")]
        if not rows:
            raise ValueError("no record carries a panel_box")
        # One panel, one axis. This function takes the calibration, the panel
        # box and the review crop off the FIRST row it is handed and draws
        # every other row's bar against them, so rows that disagree would be
        # drawn against an axis that is not theirs - and a diagnostic call does
        # not go through `verify_artifact`, which is where that is otherwise
        # caught.
        for field in ("calibration", "panel_box", "zero_px_image",
                      "review_crop_box"):
            distinct = {json.dumps(r.get(field), sort_keys=True) for r in rows}
            if len(distinct) > 1:
                raise ValueError(
                    "the rows disagree about %s, so there is no one panel to "
                    "draw: %d different values" % (field, len(distinct)))
        x0, x1, y0, y1 = (int(v) for v in rows[0]["panel_box"])
        page = _Image.open(image_path).convert("RGB")
        # Where a reviewer has to look. DECLARED when the caller said - the
        # plot area unioned with the manifest's axis regions - and ESTIMATED
        # when it did not. The estimate is a fraction of the panel, which is a
        # guess: an axis printed far from the plot box, a panel box drawn
        # tightly around the bars, a long tick label or a unit printed beside
        # the numbers, and the picture crops away the very thing it is for.
        declared = rows[0].get("review_crop_box")
        if declared:
            rx0, rx1, ry0, ry1 = (int(v) for v in declared)
            source = "DECLARED"
        else:
            rx0 = x0 - int(0.22 * (x1 - x0))
            rx1 = x1
            ry0, ry1 = y0, y1 + int(0.12 * (y1 - y0))
            source = "ESTIMATED"
        box = (max(0, min(rx0, x0) - pad), max(0, min(ry0, y0) - pad),
               min(page.width, max(rx1, x1) + pad),
               min(page.height, max(ry1, y1) + pad))
        crop = page.crop(box)
        canvas = _Image.new("RGB", (max(crop.width, 420), crop.height + FOOTER),
                            (255, 255, 255))
        canvas.paste(crop, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _font()
        ox, oy = box[0], box[1]

        #: Where the plot area starts inside the crop. Everything left of it is
        #: the printed axis, and nothing is drawn there.
        plot_left = max(0, x0 - ox)
        cal = next((r["calibration"] for r in rows if r.get("calibration")), None)

        def label_at(y, text, colour):
            """On the RIGHT. The printed tick labels are on the LEFT - they are
            the thing this picture exists to be compared against - and a label
            drawn over them hides the one number the comparison needs."""
            draw.text((crop.width - 8 - 6 * len(text), max(0, y - 11)), text,
                      fill=colour, font=font)

        # ---- the points a PERSON typed, drawn first and drawn solid.
        #
        # These are the calibration. Everything the panel is worth follows from
        # them, and a printed 30 typed as 3 is a wrong number sitting HERE - so
        # this is the pair a reviewer compares with the page. Guide lines at
        # round values are a convenience and were, until now, the only thing
        # drawn: on an axis calibrated at 2.5 and 7.5 the picture showed 3, 4,
        # 5, 6, 7 and neither number anybody had entered.
        declared, generated = [], []
        if cal:
            for value, pixel in cal.get("points") or []:
                y = int(round(float(pixel))) - oy
                if 0 <= y < crop.height:
                    draw.line((plot_left, y, crop.width - 1, y),
                              fill=(200, 120, 0), width=3)
                    label_at(y, "%g" % round(float(value), 6), (200, 120, 0))
                declared.append(dict(value=float(value), pixel=float(pixel)))
        if cal and cal.get("slope"):
            lo, hi = _value_at(cal, y1), _value_at(cal, y0)
            lo, hi = min(lo, hi), max(lo, hi)
            spoken = {round(float(v), 6) for v, _px in cal.get("points") or []}
            for value in _reference_values(cal, lo, hi):
                if round(float(value), 6) in spoken:
                    continue                 # already drawn, and drawn solid
                pixel = _pixel_at(cal, value)
                y = int(round(pixel)) - oy
                if 0 <= y < crop.height:
                    # Dashed and pale, because these are a reading aid and not
                    # evidence: nobody typed them.
                    for x in range(plot_left, crop.width - 1, 12):
                        draw.line((x, y, min(x + 5, crop.width - 1), y),
                                  fill=(240, 190, 130), width=1)
                    label_at(y, "%g" % round(value, 6), (240, 190, 130))
                generated.append(dict(value=float(round(value, 6)),
                                      pixel=float(pixel)))
        # The baseline the measurement actually used, over the top of them.
        zero = rows[0].get("zero_px_image")
        if zero is not None:
            y = int(round(float(zero))) - oy
            if 0 <= y < crop.height:
                draw.line((plot_left, y, crop.width - 1, y),
                          fill=(120, 120, 120), width=2)
        for record in rows:
            fp = record.get("footprint_px_image")
            edge = record.get("edge_px_image")
            if fp and edge is not None:
                a, b = int(fp[0]) - ox, int(fp[1]) - ox
                y = int(round(float(edge))) - oy
                if 0 <= y < crop.height:
                    draw.line((a, y, b, y), fill=(214, 39, 40), width=2)
                    draw.text((a, max(0, y - 12)),
                              "-" if record.get("value") is None
                              else "%.3g" % record["value"],
                              fill=(214, 39, 40), font=font)
                for column in (a, b):
                    if 0 <= column < crop.width:
                        draw.line((column, max(0, y), column, crop.height - 1),
                                  fill=(44, 160, 44), width=1)
            cap = record.get("cap_px_image")
            if fp and cap is not None:
                a, b = int(fp[0]) - ox, int(fp[1]) - ox
                y = int(round(float(cap))) - oy
                if 0 <= y < crop.height:
                    draw.line((a, y, b, y), fill=(31, 119, 180), width=1)
        head = ("%s   %d rows   %d declared calibration points, %d guide lines"
                " (%s crop)" % (rows[0].get("figure"), len(rows),
                                len(declared), len(generated), source))
        # px per LOG-unit is not px per unit. On a log axis the slope maps
        # pixels to the logarithm, so the reciprocal is a decade width in
        # disguise and printing it as "px/unit" invites reading it as one.
        unit = ("px/log-unit" if cal and cal.get("scale") == "LOG"
                else "px/unit")
        tail = ("calibration %.6g %s, residual %.3g, %d point(s)   figure %s"
                % (1.0 / cal["slope"] if cal and cal.get("slope") else float("nan"),
                   unit, cal.get("max_residual", 0.0) if cal else float("nan"),
                   len(declared), rows[0].get("figure_id")))
        draw.text((6, crop.height + 6), head, fill=(0, 0, 0), font=font)
        draw.text((6, crop.height + 20), tail, fill=(70, 70, 70), font=font)
        draw.text((6, crop.height + 34),
                  "solid orange = a calibration point somebody typed; dashed "
                  "= guide only; grey = baseline; red = bar top; blue = error bar",
                  fill=(70, 70, 70), font=font)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        canvas.save(path)
        meta = dict(path=path, file=os.path.basename(path),
                    declared_calibration_points=declared,
                    generated_reference_ticks=generated,
                    plot_left_in_crop=int(plot_left),
                    crop_box=[int(v) for v in box], crop_source=source,
                    calibration=cal, panel_id=rows[0].get("figure"),
                    figure_id=rows[0].get("figure_id"), rows=len(rows))
        # The sidecar records the BASENAME and not the path it was written to.
        # A run bundle gets moved, and an absolute path baked into an artifact
        # is a claim that stops being true the first time somebody copies the
        # directory.
        with open(os.path.splitext(path)[0] + ".json", "w",
                  encoding="utf-8") as fh:
            json.dump({k: v for k, v in meta.items() if k != "path"}, fh,
                      sort_keys=True, indent=1)
        return meta
    except Exception as exc:
        _FAILURES.append("%s: %s: %s" % (os.path.basename(path),
                                         type(exc).__name__, exc))
        return None


#: How much of the figure to keep either side of the two supports, as a multiple
#: of the span between them - with a floor, because a three-pixel span zoomed to
#: three pixels of context is a picture of nothing.
CONTEXT_MARGIN, CONTEXT_MIN_PAD, CONTEXT_HALF_HEIGHT = 3.0, 40, 60


def draw_inference_context(path, image_path, panel_box, mark, title="",
                           subtitle=""):
    """One picture of one reconstructed cell, for the person confirming it.

    The R3 contract asks a reviewer to say whether a NUMBER that came from
    neighbouring ink is sound. Everything they need to judge that is on the
    manifest row - the two supporting columns, the span between them, what
    covered it, the stroke and dash scale it has to be local against - and all of
    it is in PIXELS. Holding a coordinate in your head against a printed figure
    is not reviewing; it is arithmetic performed by a person who cannot check it.

    So this draws the arithmetic: the stretch of figure between the two supports,
    each support marked where the ink actually is, the target column the value
    was placed at, and the value's own row. What it does NOT draw is the
    occlusion mask - that lives in the reader's memory at read time and nothing
    downstream has it - so the cause is named in the caption rather than shaded,
    and the caption says which of the two it is.

    Never raises, like every other picture here: a crop that cannot be painted is
    recorded in `failures()`. What it must not do is come back with a picture of
    the wrong thing, so a mark with no supports and no centre returns None rather
    than a crop of the panel's top-left corner.
    """
    try:
        left = mark.get("Value_Support_Left_Px")
        right = mark.get("Value_Support_Right_Px")
        cx = mark.get("x", mark.get("point_px_x"))
        cy = _mark_y(mark)
        if cy is None or cx is None or left is None or right is None:
            return None
        left, right, cx, cy = float(left), float(right), float(cx), float(cy)
        x0, x1, y0, y1 = (int(v) for v in panel_box)
        span = max(abs(right - left), 1.0)
        pad = max(CONTEXT_MIN_PAD, int(round(CONTEXT_MARGIN * span)))
        source = Image.open(image_path).convert("RGB")
        cropbox = (max(0, int(min(left, cx) - pad)),
                   max(0, int(cy - CONTEXT_HALF_HEIGHT)),
                   min(source.width, int(max(right, cx) + pad)),
                   min(source.height, int(cy + CONTEXT_HALF_HEIGHT)))
        if cropbox[2] - cropbox[0] < 4 or cropbox[3] - cropbox[1] < 4:
            return None
        crop = source.crop(cropbox)
        ox, oy = cropbox[0], cropbox[1]
        scale = 3
        crop = crop.resize((crop.width * scale, crop.height * scale),
                           Image.NEAREST)
        canvas = Image.new("RGB", (crop.width, crop.height + FOOTER), "white")
        canvas.paste(crop, (0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _font()
        top, bottom = 0, crop.height
        # The two columns the answer was measured BETWEEN, in the colour of a
        # measurement, and the column it was placed AT in the colour of a
        # reconstruction. A reviewer who sees the target line sitting outside its
        # own two supports is looking at the defect this picture exists for.
        for at, colour in ((left, (31, 119, 180)), (right, (31, 119, 180))):
            sx = (at - ox) * scale
            draw.line((sx, top, sx, bottom), fill=colour, width=1)
        tx, ty = (cx - ox) * scale, (cy - oy) * scale
        draw.line((tx, top, tx, bottom), fill=(214, 39, 40), width=1)
        draw.line((tx - 9, ty, tx + 9, ty), fill=(214, 39, 40), width=2)
        draw.line((tx, ty - 9, tx, ty + 9), fill=(214, 39, 40), width=2)
        draw.text((6, crop.height + 6), title, fill=(0, 0, 0), font=font)
        draw.text((6, crop.height + 20), subtitle, fill=(70, 70, 70), font=font)
        draw.text((6, crop.height + 36),
                  "blue: the two columns with ink   red: where the value was "
                  "placed", fill=(70, 70, 70), font=font)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        canvas.save(path)
        return path
    except Exception as exc:
        _FAILURES.append("%s: %s: %s" % (os.path.basename(path),
                                         type(exc).__name__, exc))
        return None


def write_row_crops(directory, pairs, pad=24):
    """A folder of pictures, one per geometry row, plus a contact sheet.

    `pairs` is [(image_path, record), ...] - the PAGE each row was measured on
    beside the row - because a figure is several panels and its panels can be
    on different pages. Taking one image path and a list of records meant a
    caller with three panels had to call this three times, and each call
    rewrote `index.html`: the folder ended up with eighteen pictures and a
    contact sheet listing the last six. A sheet that under-reports the folder
    it sits in is worse than no sheet, because it is the thing a reviewer
    counts against.

    Returns the list of paths written. A row that could not be drawn is
    recorded in `failures()` and skipped; eighteen rows and seventeen pictures
    is a thing a reviewer must be able to notice, so the sheet says how many
    rows there were.
    """
    os.makedirs(directory, exist_ok=True)
    # Panels first, in the order they arrived. A row crop shows the bar; only
    # the panel picture shows the AXIS, and a reviewer who cannot see the axis
    # cannot tell a bar read correctly from a whole panel read at the wrong
    # scale - every bar still looks like a bar.
    panels, order = {}, []
    for image_path, record in pairs:
        key = record.get("figure")
        if key not in panels:
            panels[key], order = (image_path, []), order + [key]
        panels[key][1].append(record)
    panel_pictures = {}
    for key in order:
        image_path, records_here = panels[key]
        name = "panel__%s.png" % "".join(
            c if (c.isalnum() or c in "-_") else "_" for c in str(key))
        got = draw_panel_geometry(os.path.join(directory, name), image_path,
                                  records_here, pad=pad)
        if got:
            panel_pictures[key] = got
    written = []
    for image_path, record in pairs:
        name = row_crop_name(record)
        got = draw_row_crop(os.path.join(directory, name), image_path, record,
                            pad=pad)
        if got:
            written.append((got, record))
    records = [r for _i, r in pairs]
    index = os.path.join(directory, "index.html")
    with open(index, "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset='utf-8'>\n")
        fh.write("<title>geometry rows</title>\n")
        fh.write("<style>body{font:13px system-ui;margin:24px}"
                 "figure{margin:0 0 28px}img{border:1px solid #ccc;max-width:100%}"
                 "figcaption{color:#444;margin-top:4px}code{color:#888}"
                 "</style>\n")
        fh.write("<h1>%d rows, %d pictures, %d panels</h1>\n"
                 % (len(records), len(written), len(panel_pictures)))
        fh.write("<p>%s &nbsp; <span style='color:rgb(200,120,0)'>&#9644; "
                 "the calibration's own idea of each round value</span></p>\n"
                 % " &nbsp; ".join(
                     "<span style='color:rgb(%d,%d,%d)'>&#9644; %s</span>"
                     % (c[0], c[1], c[2], name) for name, c in CROP_MARKS))
        fh.write("<p>Check the panel picture first: if the orange line the "
                 "calibration calls 10 does not sit on the printed 10, every "
                 "bar in that panel is wrong together and no per-bar crop "
                 "will show it.</p>\n")
        for key in order:
            fh.write("<h2>%s</h2>\n" % key)
            if key in panel_pictures:
                meta = panel_pictures[key]
                fh.write("<figure><img src='%s'>\n"
                         % os.path.basename(meta["path"]))
                # In WORDS, not only in the picture. A reviewer comparing the
                # orange numbers with the printed ones should not have to read
                # them off a rendering, and a test should not have to either.
                fh.write("<figcaption>the whole panel, with the axis in frame"
                         " &mdash; %s crop. Calibration points somebody typed:"
                         " <b>%s</b>. Guide lines: %s."
                         "</figcaption></figure>\n"
                         % (meta["crop_source"],
                            ", ".join("%g" % t["value"] for t in
                                      meta["declared_calibration_points"])
                            or "none",
                            ", ".join("%g" % t["value"] for t in
                                      meta["generated_reference_ticks"])
                            or "none"))
            else:
                fh.write("<p><em>no panel picture could be drawn</em></p>\n")
            for got, record in written:
                if record.get("figure") != key:
                    continue
                fh.write("<figure><img src='%s'>\n" % os.path.basename(got))
                fh.write("<figcaption>%s / %s / slot %s &mdash; mean %s, "
                         "dispersion %s, fill %s%s<br><code>%s</code>"
                         "</figcaption></figure>\n" % (
                             record.get("figure"), record.get("group"),
                             record.get("slot"),
                             "-" if record.get("value") is None
                             else "%.3f" % record["value"],
                             "-" if record.get("dispersion") is None
                             else "%.3f" % record["dispersion"],
                             record.get("resolved_fill_pattern") or "-",
                             " &mdash; %s" % record["error"]
                             if record.get("error") else "",
                             record.get("geometry_row_sha256", "UNSTAMPED")))
    return ([panel_pictures[k]["path"] for k in order if k in panel_pictures]
            + [p for p, _r in written])
