"""Reusable raster readers for non-bar scientific figures.

Readers return geometry and values only.  They do not infer study arms or
timepoints; callers supply those labels and the four-grain grid validator checks
that every declared cell is represented.
"""
from dataclasses import dataclass
import math

import numpy as np
import cv2
from PIL import Image


def _runs(indices, gap=1):
    out, cur = [], []
    for value in sorted(int(v) for v in indices):
        if cur and value - cur[-1] <= gap:
            cur.append(value)
        else:
            if cur:
                out.append(cur)
            cur = [value]
    if cur:
        out.append(cur)
    return out


@dataclass(frozen=True)
class AxisCalibration:
    slope: float
    intercept: float
    scale: str = "LINEAR"

    @classmethod
    def from_points(cls, points, scale="LINEAR"):
        """Fit pixel -> value from ``[(value, pixel), ...]``."""
        scale = str(scale).upper()
        values = np.asarray([p[0] for p in points], dtype=float)
        pixels = np.asarray([p[1] for p in points], dtype=float)
        if len(points) < 2 or len(set(pixels)) < 2:
            raise ValueError("axis calibration needs two distinct pixels")
        if scale == "LOG":
            if np.any(values <= 0):
                raise ValueError("LOG calibration values must be positive")
            values = np.log(values)
        elif scale != "LINEAR":
            raise ValueError("scale must be LINEAR or LOG")
        slope, intercept = np.polyfit(pixels, values, 1)
        return cls(float(slope), float(intercept), scale)

    def pixel_to_value(self, pixel):
        raw = self.slope * float(pixel) + self.intercept
        return float(np.exp(raw) if self.scale == "LOG" else raw)

    def value_to_pixel(self, value):
        raw = np.log(float(value)) if self.scale == "LOG" else float(value)
        return float((raw - self.intercept) / self.slope)


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    rgb: tuple | None = None
    marker: str = "CIRCLE"
    fill: str = "ANY"
    tolerance: float = 70.0


def _rgb_mask(rgb, target, tolerance):
    arr = np.asarray(rgb, dtype=float)
    target = np.asarray(target, dtype=float)
    return np.linalg.norm(arr - target, axis=2) <= float(tolerance)


def _marker_and_errorbar(mask, x, y0, y1, half_window=12):
    """Return marker centre and connected whisker extent at an expected x."""
    h, w = mask.shape
    xa, xb = max(0, int(round(x)) - half_window), min(w, int(round(x)) + half_window + 1)
    patch = mask[max(0, y0):min(h, y1), xa:xb]
    counts = patch.sum(axis=1)
    groups = _runs(np.where(counts >= 5)[0], gap=1)
    if not groups:
        return None
    # Caps are wide but only 1-3 rows.  A marker is thick in both dimensions.
    marker = max(groups, key=lambda g: (len(g), float(counts[g].sum())))
    if len(marker) < 4:
        return None
    cy = max(0, y0) + float(np.mean(marker))
    xc = int(round(x))
    col = mask[:, max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    supports = _runs(np.where(col)[0], gap=2)
    connected = [g for g in supports if g[0] - 2 <= cy <= g[-1] + 2]
    whisker = max(connected, key=len) if connected else marker
    # Horizontal cap strokes form short, wide row groups on either side of the
    # much taller marker group.  Use their stroke centres rather than the outer
    # pixels, otherwise every SD is inflated by half a cap stroke at both ends.
    above = [g for g in groups if g[-1] < marker[0]]
    below = [g for g in groups if g[0] > marker[-1]]
    top = float(np.mean(max(above, key=lambda g: g[-1]))) if above else float(whisker[0])
    bottom = float(np.mean(min(below, key=lambda g: g[0]))) if below else float(whisker[-1])
    return cy, top, bottom, bool(above and below)


def _errorbar_around_marker(mask, x, cy, y0, y1, half_window=8,
                            marker_half_height=8, search_radius=28):
    """Find cap centres attached to a known monochrome marker.

    Marker discovery and whisker discovery are deliberately separate.  In a
    black multi-series plot a vertical whisker is physically joined to the
    marker, so contour geometry alone turns a circle into a tall irregular
    object.  Once the marker centre is known, however, cap rows are simply the
    nearest wide dark strokes above and below it whose stem crosses the marker.
    """
    h, w = mask.shape
    xc = int(round(x))
    ya = max(int(y0), int(round(cy - search_radius)))
    yb = min(int(y1), int(round(cy + search_radius + 1)))
    xa, xb = max(0, xc - half_window), min(w, xc + half_window + 1)
    patch = mask[ya:yb, xa:xb]
    if patch.size == 0:
        return None
    counts = patch.sum(axis=1)
    groups = _runs(np.where(counts >= 5)[0], gap=1)
    above = [g for g in groups if ya + g[-1] < cy - marker_half_height]
    below = [g for g in groups if ya + g[0] > cy + marker_half_height]
    if not above or not below:
        return None
    top_group = max(above, key=lambda g: g[-1])
    bottom_group = min(below, key=lambda g: g[0])
    top = ya + float(np.mean(top_group))
    bottom = ya + float(np.mean(bottom_group))
    # A true error-bar stem reaches from each cap to the marker at x.  Allow a
    # one-pixel antialiasing gap, but do not accept significance brackets.
    upper_stem = mask[max(0, int(top)):min(h, int(cy - marker_half_height) + 1),
                      max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    lower_stem = mask[max(0, int(cy + marker_half_height)):min(h, int(bottom) + 1),
                      max(0, xc - 1):min(w, xc + 2)].any(axis=1)
    stem_confirmed = bool(len(upper_stem) and len(lower_stem)
                          and upper_stem.mean() >= 0.70
                          and lower_stem.mean() >= 0.70)
    return top, bottom, stem_confirmed


def read_line_marker_panel(image, panel_box, x_positions, y_calibration, series,
                           x_window=12):
    """Read coloured line/marker series at caller-declared x positions.

    The expected x grid is supplied explicitly.  Missing markers remain missing
    so the grid engine, rather than a left-to-right counter, identifies the cell.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    for spec in series:
        if spec.rgb is None:
            raise ValueError("coloured line reader requires SeriesSpec.rgb")
        mask = _rgb_mask(rgb, spec.rgb, spec.tolerance)
        region = np.zeros_like(mask)
        region[max(0, y0):min(mask.shape[0], y1), max(0, x0):min(mask.shape[1], x1)] = True
        mask &= region
        for order, (label, x) in enumerate(x_positions.items()):
            found = _marker_and_errorbar(mask, x, y0, y1, half_window=x_window)
            if found is None:
                continue
            cy, top, bottom, stem = found
            upper = max(y_calibration.pixel_to_value(top), y_calibration.pixel_to_value(bottom))
            lower = min(y_calibration.pixel_to_value(top), y_calibration.pixel_to_value(bottom))
            mean = y_calibration.pixel_to_value(cy)
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(x),
                marker_center_px=cy, mean=mean,
                errorbar_lower=lower, errorbar_upper=upper,
                dispersion=(upper - lower) / 2.0,
                Marker_Definition="MARKER_CENTER",
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


def _contour_marker_shape(contour):
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return "UNKNOWN"
    approx = cv2.approxPolyDP(contour, 0.06 * perimeter, True)
    vertices = len(approx)
    area = cv2.contourArea(contour)
    circularity = 4.0 * np.pi * area / (perimeter * perimeter)
    # Rasterisation and a one-pixel connecting line can simplify a circle to
    # four or five polygon vertices.  Circularity is more stable than vertex
    # count for that case and remains well above a diamond's value.
    if circularity >= 0.84:
        return "CIRCLE"
    if vertices == 3:
        return "TRIANGLE"
    if vertices == 4:
        pts = approx[:, 0, :]
        # A diamond has a single extreme point at its top; an axis-aligned
        # square has a horizontal top edge.  Both remain valid marker classes.
        top_count = int((pts[:, 1] == pts[:, 1].min()).sum())
        return "DIAMOND" if top_count == 1 else "SQUARE"
    return "CIRCLE" if vertices >= 5 and circularity >= 0.55 else "UNKNOWN"


def read_monochrome_marker_panel(image, panel_box, x_positions, y_calibration,
                                 series, x_window=18, threshold=150):
    """Separate black multi-series plots by marker geometry.

    Thin connecting lines are removed with a small morphological opening.  The
    adapter intentionally emits no value for a marker whose shape is ambiguous;
    the grid gate then routes that cell to manual WPD instead of guessing a
    series identity.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    dark = (gray < int(threshold)).astype(np.uint8) * 255
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    expected = list(series)
    for order, (label, x) in enumerate(x_positions.items()):
        xa, xb = max(x0, int(round(x)) - x_window), min(x1, int(round(x)) + x_window + 1)
        crop = dark[max(0, y0):min(dark.shape[0], y1), xa:xb]
        candidates = []
        # Open markers are defined by an enclosed white hole.  Detect that hole
        # before morphology: a thin outline may otherwise be erased, while its
        # enclosed region remains an unambiguous OPEN-vs-FILLED signal.
        white = (crop == 0).astype(np.uint8)
        nlab, labels, stats_, cents = cv2.connectedComponentsWithStats(white, 8)
        for lab in range(1, nlab):
            bx, by, bw, bh, area = stats_[lab]
            if bx == 0 or by == 0 or bx + bw == crop.shape[1] or by + bh == crop.shape[0]:
                continue
            if not (12 <= area <= 300 and 4 <= min(bw, bh) and max(bw, bh) <= 24):
                continue
            component = (labels == lab).astype(np.uint8) * 255
            holes, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not holes:
                continue
            contour = max(holes, key=cv2.contourArea)
            shape = _contour_marker_shape(contour)
            if shape not in {s.marker.upper() for s in expected}:
                continue
            cx, cy = cents[lab]
            candidates.append((shape, "OPEN", xa + cx, y0 + cy,
                               float(cv2.contourArea(contour)), 0.0))
        # Filled markers may be connected to a whisker and a line.  A distance
        # transform keeps the thick marker core while eliminating one-pixel
        # lines and caps, so its geometry remains classifiable.
        distance = cv2.distanceTransform((crop > 0).astype(np.uint8), cv2.DIST_L2, 5)
        cores = (distance >= 2.2).astype(np.uint8) * 255
        contours, _ = cv2.findContours(cores, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            bx, by, bw, bh = cv2.boundingRect(contour)
            if area < 20 or min(bw, bh) < 6 or max(bw, bh) > 28:
                continue
            shape = _contour_marker_shape(contour)
            if shape not in {s.marker.upper() for s in expected}:
                continue
            moment = cv2.moments(contour)
            if moment["m00"] == 0:
                continue
            cx = xa + moment["m10"] / moment["m00"]
            cy = y0 + moment["m01"] / moment["m00"]
            inside = np.zeros_like(cores)
            cv2.drawContours(inside, [contour], -1, 255, thickness=-1)
            denom = max(1, int((inside > 0).sum()))
            fill_ratio = float(((cores > 0) & (inside > 0)).sum()) / denom
            if fill_ratio >= 0.58:
                candidates.append((shape, "FILLED", cx, cy, area, fill_ratio))
        # At most one mark of a given series may occupy a declared x cell.  If
        # two candidates survive, keep neither: series identity is unresolved.
        for spec in expected:
            shape = spec.marker.upper()
            wanted_fill = spec.fill.upper()
            if wanted_fill not in ("ANY", "OPEN", "FILLED"):
                raise ValueError("SeriesSpec.fill must be ANY, OPEN or FILLED")
            matches = [c for c in candidates if c[0] == shape and
                       (wanted_fill == "ANY" or c[1] == wanted_fill)]
            if len(matches) != 1:
                continue
            _, fill_state, cx, cy, area, fill_ratio = matches[0]
            whisker = _errorbar_around_marker(dark > 0, x, cy, y0, y1)
            lower = upper = dispersion = None
            stem = False
            if whisker is not None:
                top, bottom, stem = whisker
                upper = max(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                lower = min(y_calibration.pixel_to_value(top),
                            y_calibration.pixel_to_value(bottom))
                dispersion = (upper - lower) / 2.0
            out.append(dict(
                series=spec.name, order=order, x_label=label, x=float(cx),
                marker_center_px=float(cy), mean=y_calibration.pixel_to_value(cy),
                dispersion=dispersion, errorbar_lower=lower, errorbar_upper=upper,
                Marker_Definition=shape,
                Marker_Fill=fill_state, marker_fill_ratio=fill_ratio,
                Errorbar_Stem_Confirmed="TRUE" if stem else "FALSE",
                marker_area_px=float(area),
            ))
    out.sort(key=lambda row: (row["series"], row["order"]))
    return out


def read_scatter_panel(image, panel_box, x_calibration, y_calibration, series,
                       min_area=12, max_area=500):
    """Read coloured or a single monochrome scatter series.

    Multiple monochrome series require marker-identity routing rather than a
    shared threshold and therefore fail closed here.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    for spec in series:
        if spec.rgb is None:
            if len(series) != 1:
                raise ValueError("multiple monochrome scatter series need explicit marker routing")
            gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            mask = (gray < 150).astype(np.uint8) * 255
        else:
            mask = _rgb_mask(rgb, spec.rgb, spec.tolerance).astype(np.uint8) * 255
        crop = mask[max(0, y0):min(mask.shape[0], y1), max(0, x0):min(mask.shape[1], x1)]
        opened = cv2.morphologyEx(
            crop, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if not (min_area <= area <= max_area):
                continue
            _, _, bw, bh = cv2.boundingRect(contour)
            if max(bw, bh) > 35 or min(bw, bh) < 3:
                continue
            moment = cv2.moments(contour)
            if moment["m00"] == 0:
                continue
            px = x0 + moment["m10"] / moment["m00"]
            py = y0 + moment["m01"] / moment["m00"]
            points.append(dict(
                series=spec.name, point_px_x=float(px), point_px_y=float(py),
                x_value=x_calibration.pixel_to_value(px),
                y_value=y_calibration.pixel_to_value(py),
                Marker_Definition=spec.marker.upper(), marker_area_px=float(area),
            ))
        points.sort(key=lambda row: (row["x_value"], row["y_value"]))
        for order, row in enumerate(points):
            row["order"] = order
            out.append(row)
    return out


def _average_ranks(values):
    """Average ranks for ties, equivalent to rankdata(method='average')."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def _pearson(x, y):
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        raise ValueError("association needs variation on both axes")
    return float(np.corrcoef(x, y)[0, 1])


def _normal_p_from_r(r, n):
    """Two-sided Fisher-z normal approximation; None when n is too small."""
    if n <= 3:
        return None
    if abs(r) >= 1:
        return 0.0
    z = math.atanh(r) * math.sqrt(n - 3)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def _kendall_exact_two_sided(n, observed_s):
    """Exact two-sided no-tie Kendall p from the inversion-count distribution."""
    # counts[k] is the number of permutations of m items with k inversions.
    counts = [1]
    for m in range(2, n + 1):
        max_inv = m * (m - 1) // 2
        prefix = [0]
        for count in counts:
            prefix.append(prefix[-1] + count)
        new = []
        for k in range(max_inv + 1):
            left = max(0, k - (m - 1))
            right = min(k, len(counts) - 1)
            new.append(prefix[right + 1] - prefix[left])
        counts = new
    total_pairs = n * (n - 1) // 2
    extreme = sum(count for inversions, count in enumerate(counts)
                  if abs(total_pairs - 2 * inversions) >= abs(observed_s))
    return float(extreme / math.factorial(n))


def _kendall_tau_b(x, y):
    concordant = discordant = tie_x = tie_y = 0
    for i in range(len(x) - 1):
        for j in range(i + 1, len(x)):
            dx, dy = x[j] - x[i], y[j] - y[i]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tie_x += 1
            elif dy == 0:
                tie_y += 1
            elif dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    den = math.sqrt((concordant + discordant + tie_x)
                    * (concordant + discordant + tie_y))
    if den == 0:
        raise ValueError("Kendall tau needs comparable pairs")
    tau = (concordant - discordant) / den
    n = len(x)
    has_ties = len(set(x)) < n or len(set(y)) < n
    if has_ties:
        # An exact conditional permutation test with ties requires a different
        # null distribution.  Do not silently substitute the no-tie normal
        # approximation; retain the tau and require the source's reported p.
        return float(tau), None, "SOURCE_P_REQUIRED_TIES"
    observed_s = concordant - discordant
    if n <= 200:
        return (float(tau), _kendall_exact_two_sided(n, observed_s),
                "KENDALL_EXACT_PERMUTATION")
    # Very large scatterplots would make the exact big-integer distribution
    # unnecessarily costly; the asymptotic no-tie variance is accurate there.
    z = tau * math.sqrt(9 * n * (n - 1) / (2 * (2 * n + 5)))
    return (float(tau), float(math.erfc(abs(z) / math.sqrt(2.0))),
            "KENDALL_NORMAL_APPROX_N_GT_200")


def summarize_association(points, association_type="PEARSON_R"):
    """Calculate a reported association from preserved digitized coordinates."""
    kind = str(association_type).strip().upper()
    x = np.asarray([p["x_value"] for p in points], dtype=float)
    y = np.asarray([p["y_value"] for p in points], dtype=float)
    if len(x) < 3:
        raise ValueError("at least three pairs are required")
    if kind == "PEARSON_R":
        value = _pearson(x, y)
        p = _normal_p_from_r(value, len(x))
    elif kind == "SPEARMAN_RHO":
        value = _pearson(_average_ranks(x), _average_ranks(y))
        p = _normal_p_from_r(value, len(x))
    elif kind == "KENDALL_TAU":
        value, p, p_method = _kendall_tau_b(x, y)
    elif kind == "R_SQUARED":
        r = _pearson(x, y)
        p = _normal_p_from_r(r, len(x))
        value = r * r
    elif kind == "SLOPE":
        value = float(np.polyfit(x, y, 1)[0])
        p = _normal_p_from_r(_pearson(x, y), len(x))
    else:
        raise ValueError("unsupported association type: %s" % association_type)
    ties = bool(len(set(x)) < len(x) or len(set(y)) < len(y))
    method = p_method if kind == "KENDALL_TAU" else "FISHER_Z_APPROX"
    return dict(Association_Type=kind, Association_Value=float(value),
                P_Value=None if p is None else float(p), N_Pairs=int(len(x)),
                P_Value_Method=method,
                # Every p this function returns was computed from the digitized
                # cloud, so it says so. A p copied out of the running text is
                # marked TRANSCRIBED by whoever copies it - the validator will
                # not let a computed method carry that label.
                P_Value_Extraction_Method=("" if p is None else "DIGITIZED"),
                # The tie state is the evidence behind the Kendall method choice.
                # Emitting it means the validator can contradict the reader
                # instead of trusting it.
                Ties_Present="TRUE" if ties else "FALSE")


def read_box_violin_panel(image, panel_box, x_positions, y_calibration,
                          half_window=18, threshold=100):
    """Read five-number summaries from boxes or box-overlaid violins.

    A density silhouette alone does not identify quartiles.  In that case this
    function returns no value and leaves the grid cell for manual review.
    """
    rgb = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    dark = gray < int(threshold)
    x0, x1, y0, y1 = map(int, panel_box)
    out = []
    for order, (label, x) in enumerate(x_positions.items()):
        xa, xb = max(x0, int(round(x)) - half_window), min(x1, int(round(x)) + half_window + 1)
        counts = dark[max(0, y0):min(dark.shape[0], y1), xa:xb].sum(axis=1)
        line_groups = _runs(np.where(counts >= 10)[0], gap=1)
        lines = []
        for group in line_groups:
            centre = y0 + float(np.mean(group))
            width = int(max(counts[group]))
            lines.append((centre, width))
        # Whisker caps + Q3 + median + Q1 must all be visible.  A pure violin,
        # or a violin with only a median dot, is not convertible to an IQR.
        if len(lines) != 5:
            continue
        box_lines = [row for row in lines if row[1] >= 20]
        if len(box_lines) != 3:
            continue
        values = sorted(y_calibration.pixel_to_value(row[0]) for row in lines)
        qvalues = sorted(y_calibration.pixel_to_value(row[0]) for row in box_lines)
        out.append(dict(
            order=order, x_label=label, x=float(x),
            whisker_lower=values[0], q1=qvalues[0], median=qvalues[1],
            q3=qvalues[2], whisker_upper=values[-1],
            Summary_Type="MEDIAN_IQR_RANGE", Marker_Definition="BOX_OVERLAY",
        ))
    return out


MARK_TYPES = ("BAR_COLOR", "LINE_COLOR", "LINE_MONO", "SCATTER", "BOX_VIOLIN")


def read_panel(mark_type, **kwargs):
    """Dispatch a declared graphical mark to its reader adapter.

    Routing is explicit and fails closed.  Caption words or study identities
    never silently select a numerical reader.
    """
    kind = str(mark_type).strip().upper()
    if kind == "LINE_COLOR":
        return read_line_marker_panel(**kwargs)
    if kind == "LINE_MONO":
        return read_monochrome_marker_panel(**kwargs)
    if kind == "SCATTER":
        return read_scatter_panel(**kwargs)
    if kind == "BOX_VIOLIN":
        return read_box_violin_panel(**kwargs)
    if kind == "BAR_COLOR":
        from bar_reader import colour_masks, read_bar_panel
        image = kwargs.pop("image")
        masks = colour_masks(image.convert("RGB") if isinstance(image, Image.Image) else image)
        return read_bar_panel(masks=masks, **kwargs)
    raise ValueError("unknown mark type %r; expected %s" % (mark_type, "/".join(MARK_TYPES)))


#: Every column an ASSOCIATION cell must carry from the reader into the values
#: file. The validator gates on all seven; the adapter used to copy five, so two
#: reader-supplied provenance fields died between the reader and the gate. Keep
#: this list and `fig_values_columns()` in step - `test_mark_readers.py` asserts
#: the containment, so adding a field to one and not the other fails the suite.
ASSOCIATION_CARRIED = (
    "Association_Type", "Association_Value", "P_Value", "P_Value_Method",
    "N_Pairs", "P_Value_Extraction_Method", "Ties_Present",
    "Point_Data_Reference",
)


def write_point_data(points, path):
    """Persist the digitized point cloud an association was computed from.

    A digitized r or tau is a claim about a set of coordinates nobody else can
    see. Writing them next to the value is what makes the claim checkable, and
    the validator requires the path on every digitized association row.
    Returns `path`, so it composes into a `to_value_records` call.
    """
    import json
    import os
    rows = [{"x_value": float(p["x_value"]), "y_value": float(p["y_value"])}
            for p in points]
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"n_pairs": len(rows), "points": rows}, fh, indent=1, sort_keys=True)
    return path


def _cell_key(levels):
    return ";".join("%s=%s" % (str(k).strip().upper(), str(v).strip().upper())
                    for k, v in sorted(levels.items(), key=lambda item: str(item[0]).upper()))


def to_value_records(rows, statistic_type, unit_id, x_factor=None,
                     series_factor=None, cell_levels=None,
                     point_data_reference=None):
    """Convert adapter rows into the common Unit_ID x Cell_Key grain.

    `point_data_reference` fills that column on ASSOCIATION rows that do not
    already carry one. `summarize_association` cannot know where the caller
    chose to write the points, so the path enters here; pass the return value
    of `write_point_data`.
    """
    kind = str(statistic_type).strip().upper()
    out = []
    for row in rows:
        levels = dict(cell_levels or {})
        if x_factor:
            if "x_label" not in row:
                raise ValueError("%s needs x_label for factor %s" % (kind, x_factor))
            levels[x_factor] = row["x_label"]
        if series_factor:
            if "series" not in row:
                raise ValueError("%s needs series for factor %s" % (kind, series_factor))
            levels[series_factor] = row["series"]
        if not levels:
            raise ValueError("at least one Cell_Key factor must be supplied")
        record = dict(Unit_ID=unit_id, Cell_Key=_cell_key(levels))
        if kind == "CONTINUOUS":
            record.update(Mean=row.get("mean"), Dispersion_Value=row.get("dispersion"),
                          Errorbar_Lower=row.get("errorbar_lower"),
                          Errorbar_Upper=row.get("errorbar_upper"))
        elif kind == "QUANTILE_SUMMARY":
            record.update(Median=row.get("median"), Q1=row.get("q1"), Q3=row.get("q3"),
                          Whisker_Lower=row.get("whisker_lower"),
                          Whisker_Upper=row.get("whisker_upper"))
        elif kind == "ASSOCIATION":
            # Every field the validator gates on must survive the adapter. The
            # three provenance columns were dropped here, so a reader that
            # emitted them correctly still produced rows the gate then failed -
            # or worse, rows that passed because the gate saw blanks it read as
            # "not applicable". ASSOCIATION_CARRIED is asserted by the tests.
            for key in ASSOCIATION_CARRIED:
                record[key] = row.get(key)
            if not record.get("Point_Data_Reference") and point_data_reference:
                record["Point_Data_Reference"] = point_data_reference
        else:
            raise ValueError("unsupported statistic type %r" % statistic_type)
        out.append(record)
    return out
