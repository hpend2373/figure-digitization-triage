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
