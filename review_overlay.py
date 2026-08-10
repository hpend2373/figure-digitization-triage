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
import os

from PIL import Image, ImageDraw

#: Distinct enough to tell apart on a greyscale journal figure, in order.
SERIES_COLOURS = ((214, 39, 40), (31, 119, 180), (44, 160, 44), (148, 103, 189),
                  (255, 127, 14), (23, 190, 207))
MISSING_COLOUR = (120, 120, 120)
PAD = 12
FOOTER = 58
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

        canvas = Image.new("RGB", (crop.width + LABEL_MARGIN,
                                   crop.height + FOOTER), "white")
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
            label = "%s/%s" % (mark.get("series", "?"), mark.get("x_label", "?"))
            value = mark.get("mean", mark.get("median"))
            if value is not None:
                label += " %.4g" % float(value)
            ly = min(max(4, my - 5 + (slot % 4 - 1.5) * 13),
                     crop.height - 14)
            draw.line((mx + 10, my, mx + 16, ly + 5), fill=colour, width=1)
            draw.text((mx + 18, ly), label, fill=colour, font=font)

        draw.text((6, crop.height + 6), title or os.path.basename(image_path),
                  fill=(0, 0, 0), font=font)
        draw.text((6, crop.height + 20), subtitle, fill=(70, 70, 70), font=font)
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
        fh.write("<h1>%d rows, %d pictures</h1>\n"
                 % (len(records), len(written)))
        fh.write("<p>%s</p>\n" % " &nbsp; ".join(
            "<span style='color:rgb(%d,%d,%d)'>&#9644; %s</span>"
            % (c[0], c[1], c[2], name) for name, c in CROP_MARKS))
        for got, record in written:
            fh.write("<figure><img src='%s'>\n" % os.path.basename(got))
            fh.write("<figcaption>%s / %s / slot %s &mdash; mean %s, "
                     "dispersion %s, fill %s%s<br><code>%s</code></figcaption>"
                     "</figure>\n" % (
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
    return written and [p for p, _r in written] or []
