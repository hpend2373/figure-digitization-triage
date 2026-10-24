"""Inspect painted circle-like PDF paths as source evidence, never as approval.

Only page-content paths are inspected. XObjects and stroke-only circles are
reported as coverage limits. A path is a proposal until its role in the source
figure is checked: a legend glyph or a letter can also be a closed path.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import sys

SCHEMA = "fdt/pdf-marker-evidence/1"
METHOD = "PDF_CLOSED_CUBIC_PATH_BOUNDS_CENTER"


class EvidenceError(ValueError):
    pass


def _numbers(values, length):
    if len(values) != length or any(isinstance(x, bool) for x in values):
        raise EvidenceError("BAD_GRAPHICS_OPERANDS")
    try:
        result = [float(x) for x in values]
    except (TypeError, ValueError) as exc:
        raise EvidenceError("NONNUMERIC_GRAPHICS_OPERANDS") from exc
    if not all(math.isfinite(x) for x in result):
        raise EvidenceError("NONFINITE_GRAPHICS_OPERANDS")
    return result


def _multiply(a, b):
    u, v, w, z, tx, ty = a
    aa, bb, cc, dd, xx, yy = b
    return [u*aa+w*bb, v*aa+z*bb, u*cc+w*dd, v*cc+z*dd,
            u*xx+w*yy+tx, v*xx+z*yy+ty]


def _point(matrix, x, y):
    a, b, c, d, e, f = matrix
    return [a*x+c*y+e, b*x+d*y+f]


def scan_operations(operations):
    """Return filled path proposals; never merge two fills by position."""
    ctm, fill, space = [1, 0, 0, 1, 0, 0], [0.0], "GRAY"
    stack, paths, limits, path, names, points = [], [], [], [], [], []
    start = None
    for index, (values, operator) in enumerate(operations):
        op = operator.decode("ascii") if isinstance(operator, bytes) else operator
        if op == "q":
            stack.append((list(ctm), list(fill), space))
        elif op == "Q":
            if not stack:
                raise EvidenceError("GRAPHICS_STACK_UNDERFLOW")
            ctm, fill, space = stack.pop()
        elif op == "cm":
            if path:
                raise EvidenceError("TRANSFORM_INSIDE_PATH_UNSUPPORTED")
            ctm = _multiply(ctm, _numbers(values, 6))
        elif op in ("k", "g", "rg"):
            n, space = {"k": (4, "CMYK"), "g": (1, "GRAY"),
                        "rg": (3, "RGB")}[op]
            fill = _numbers(values, n)
        elif op == "cs":
            devices = {"/DeviceGray": ("GRAY", 1),
                       "/DeviceRGB": ("RGB", 3),
                       "/DeviceCMYK": ("CMYK", 4)}
            if len(values) != 1 or str(values[0]) not in devices:
                raise EvidenceError("FILL_COLOR_SPACE_UNSUPPORTED")
            space, n = devices[str(values[0])]
            fill = [0.0, 0.0, 0.0, 1.0] if space == "CMYK" else [0.0]*n
        elif op in ("sc", "scn"):
            fill = _numbers(values, {"GRAY": 1, "RGB": 3, "CMYK": 4}[space])
        elif op == "Do":
            limits.append({"operator_index": index,
                           "reason": "XOBJECT_CONTENT_NOT_INSPECTED"})
        elif op == "m":
            if not path:
                start = index
            coords = _numbers(values, 2)
            path.append({"operator": op, "operands": coords})
            names.append(op)
            points.append(_point(ctm, *coords))
        elif op == "c":
            coords = _numbers(values, 6)
            path.append({"operator": op, "operands": coords})
            names.append(op)
            points.extend(_point(ctm, *coords[j:j+2]) for j in (0, 2, 4))
        elif op in ("l", "v", "y", "re"):
            names.append(op)
        elif op == "h":
            pass
        elif op in ("f", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
            circle = None
            if names == ["m", "c", "c", "c", "c"] and len(points) == 13:
                xs, ys = zip(*points)
                bounds = [min(xs), min(ys), max(xs), max(ys)]
                width, height = bounds[2]-bounds[0], bounds[3]-bounds[1]
                closed = math.dist(points[0], points[-1]) <= 1e-7
                if closed and width > 0 and height > 0 and abs(width-height) <= max(width, height)*0.02:
                    circle = {"operation_start": start, "operation_end": index,
                              "paint": op, "fill_space": space, "fill": list(fill),
                              "bounds": bounds,
                              "center": [(bounds[0]+bounds[2])/2,
                                         (bounds[1]+bounds[3])/2],
                              "path": path}
            if circle and op in ("S", "s"):
                # The adjacent outline is part of the previous filled glyph.
                previous = paths[-1] if paths else None
                if (previous and previous["operation_end"]+1 == start
                        and previous["bounds"] == circle["bounds"]
                        and previous["path"] == path):
                    previous["outline_operation_range"] = [start, index]
                else:
                    limits.append({"operator_index": start,
                                   "reason": "STROKE_ONLY_CIRCLE_NOT_A_FILLED_PATH"})
            elif circle and op != "n":
                paths.append(circle)
            path, names, points, start = [], [], [], None
    if stack:
        raise EvidenceError("UNBALANCED_GRAPHICS_STACK")
    return {"markers": paths, "coverage_limits": limits}


def native_center(center, media_box, raster_origin_px, dpi):
    """Explicit page-to-raster conversion; no outcome axis is inferred."""
    x, y = _numbers(center, 2)
    left, bottom, right, top = _numbers(media_box, 4)
    ox, oy = _numbers(raster_origin_px, 2)
    scale = _numbers([dpi], 1)[0]/72
    if not (right > left and top > bottom and scale > 0):
        raise EvidenceError("INVALID_PAGE_OR_RASTER_SCALE")
    return [(x-left)*scale-ox, (top-y)*scale-oy]


def _load_page(pdf_bytes, page_number):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EvidenceError("PDF_BACKEND_UNAVAILABLE: install requirements-intake.txt") from exc
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted:
            raise EvidenceError("ENCRYPTED_PDF_UNSUPPORTED")
        if isinstance(page_number, bool) or not 1 <= page_number <= len(reader.pages):
            raise EvidenceError("PAGE_OUT_OF_RANGE")
        page = reader.pages[page_number-1]
        if int(page.get("/Rotate", 0)) % 360:
            raise EvidenceError("ROTATED_PAGE_UNSUPPORTED")
        content = page.get_contents()
        return (content.operations if content is not None else [],
                [float(x) for x in page.mediabox])
    except EvidenceError:
        raise
    except Exception as exc:
        raise EvidenceError("PDF_CONTENT_UNREADABLE") from exc


def inspect_pdf(pdf_bytes, page_number):
    ops, media_box = _load_page(pdf_bytes, page_number)
    result = scan_operations(ops)
    return dict(result, schema=SCHEMA, method=METHOD, status="PROPOSAL_ONLY",
                pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                page=page_number, media_box=media_box,
                human_review_required=True, pooling_eligible=False,
                count_unit="painted filled paths, not inferred data points")


def marker_evidence(report, marker):
    if report.get("schema") != SCHEMA or marker not in report["markers"]:
        raise EvidenceError("MARKER_NOT_IN_REPORT")
    return {"schema": SCHEMA, "method": METHOD,
            "pdf_sha256": report["pdf_sha256"], "page": report["page"],
            "marker": marker}


def verify_pdf_evidence(pdf_bytes, evidence):
    if evidence.get("schema") != SCHEMA or evidence.get("method") != METHOD:
        raise EvidenceError("UNKNOWN_EVIDENCE_METHOD")
    if hashlib.sha256(pdf_bytes).hexdigest() != evidence.get("pdf_sha256"):
        raise EvidenceError("SOURCE_PDF_MODIFIED")
    report = inspect_pdf(pdf_bytes, evidence["page"])
    if evidence.get("marker") not in report["markers"]:
        raise EvidenceError("SOURCE_MARKER_MODIFIED")
    return evidence["marker"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, required=True, help="one-based page")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        # One read supplies both the source hash and the parsed PDF.
        report = inspect_pdf(args.pdf.read_bytes(), args.page)
        text = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
        if args.out:
            if args.out.suffix.lower() != ".json":
                raise EvidenceError("PROPOSAL_JSON_REQUIRED")
            with args.out.open("x", encoding="utf-8") as fh:
                fh.write(text)
        else:
            print(text, end="")
    except (OSError, EvidenceError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
