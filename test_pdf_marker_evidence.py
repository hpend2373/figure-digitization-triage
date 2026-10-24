"""Synthetic source paths, source binding, and the public read-only entry."""
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pdf_marker_evidence as M

checks = {}


def check(name, condition):
    assert name not in checks, name
    checks[name] = bool(condition)
    assert condition, name


def refused(name, call, reason):
    try:
        call()
    except M.EvidenceError as exc:
        check(name, reason in str(exc))
    else:
        raise AssertionError(name + " did not refuse")


def circle(x=20, y=20, fill=1):
    r, k = 3, 1.656854
    return [([0, 0, 0, fill], b"k"), ([x+r, y], b"m"),
            ([x+r, y+k, x+k, y+r, x, y+r], b"c"),
            ([x-k, y+r, x-r, y+k, x-r, y], b"c"),
            ([x-r, y-k, x-k, y-r, x, y-r], b"c"),
            ([x+k, y-r, x+r, y-k, x+r, y], b"c"), ([], b"f")]


def tiny_pdf(ops):
    stream = ("\n".join(" ".join(str(x) for x in values) + " " + op.decode()
                        for values, op in ops) + "\n").encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 80 80] "
               b"/Resources << >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
               + stream + b"endstream"]
    result = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(result)
    result += b"xref\n0 5\n0000000000 65535 f \n"
    result += b"".join(("%010d 00000 n \n" % offset).encode() for offset in offsets[1:])
    return result + b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"


ops = circle()
one = M.scan_operations(ops)
check("one filled path and its center", len(one["markers"]) == 1 and one["markers"][0]["center"] == [20, 20])
check("paint and fill retained", one["markers"][0]["paint"] == "f" and one["markers"][0]["fill"] == [0, 0, 0, 1])
overlap = M.scan_operations(circle() + circle(y=20.5, fill=0))
check("overdraw keeps both source centers", len(overlap["markers"]) == 2 and overlap["markers"][0]["center"] != overlap["markers"][1]["center"])
check("same center fills are not deduplicated", len(M.scan_operations(circle()+circle(fill=0))["markers"]) == 2)
outline = circle()[1:-1] + [([], b"s")]
combined = M.scan_operations(circle()+outline)
check("adjacent outline is not another mean", len(combined["markers"]) == 1 and "outline_operation_range" in combined["markers"][0])
check("stroke only states coverage limit", M.scan_operations(outline)["coverage_limits"][0]["reason"].startswith("STROKE_ONLY"))
check("XObjects are an explicit coverage limit", M.scan_operations([(["/Image"], b"Do")])["coverage_limits"][0]["reason"] == "XOBJECT_CONTENT_NOT_INSPECTED")
open_path = copy.deepcopy(ops)
open_path[-2][0][-1] += 1
check("unclosed curve not a circle proposal", not M.scan_operations(open_path)["markers"])
check("rectangle not a marker path", not M.scan_operations([([0,0,2,2], b"re"), ([], b"f")])["markers"])
transformed = M.scan_operations([([2,0,0,2,5,7], b"cm")] + circle())
check("page transform applied once", transformed["markers"][0]["center"] == [45,47])
restored = M.scan_operations([([], b"q"), ([2,0,0,2,5,7], b"cm")] + circle() + [([], b"Q")] + circle())
check("graphics state restored", [p["center"] for p in restored["markers"]] == [[45,47],[20,20]])
check("anisotropic ellipse is not circle proposal", not M.scan_operations([([2,0,0,1,0,0], b"cm")]+circle())["markers"])
refused("graphics stack underflow", lambda: M.scan_operations([([],b"Q")]), "UNDERFLOW")
refused("unbalanced graphics stack", lambda: M.scan_operations([([],b"q")]), "UNBALANCED")
refused("unsupported color space", lambda: M.scan_operations([(["/Pattern"],b"cs")]), "COLOR_SPACE")
device = M.scan_operations([(["/DeviceGray"],b"cs"),([1],b"sc")]+circle()[1:])
check("declared device color space", device["markers"][0]["fill_space"] == "GRAY" and device["markers"][0]["fill"] == [1])
initial = M.scan_operations([(["/DeviceCMYK"],b"cs")]+circle()[1:])
check("CMYK initial color is black", initial["markers"][0]["fill"] == [0,0,0,1])
refused("nonfinite transform", lambda: M.scan_operations([([float('nan'),0,0,1,0,0],b"cm")]), "NONFINITE")
refused("transform inside path", lambda: M.scan_operations(circle()[:2]+[([1,0,0,1,0,0],b"cm")]), "INSIDE_PATH")
check("media origin and inverted y", M.native_center([20,30],[5,5,85,105],[10,20],144) == [20,130])
first = M.native_center([20,30],[5,5,85,105],[10,20],144)
second = M.native_center([20,30],[5,5,85,105],[20,40],288)
check("resolution consistency", second == [2*x for x in first])
refused("zero raster scale", lambda: M.native_center([1,1],[0,0,5,5],[0,0],0), "INVALID")
refused("blank pixel not zero", lambda: M.native_center([None,1],[0,0,5,5],[0,0],72), "NONNUMERIC")
refused("boolean not a coordinate", lambda: M.native_center([True,1],[0,0,5,5],[0,0],72), "BAD_GRAPHICS")

raw = tiny_pdf(circle() + circle(y=20.5, fill=0))
with patch.object(M, "_load_page", return_value=(circle()+circle(y=20.5,fill=0), [0,0,80,80])):
    report = M.inspect_pdf(raw, 1)
    evidence = M.marker_evidence(report, report["markers"][1])
    check("proposal never approval or pooling", report["status"] == "PROPOSAL_ONLY" and report["human_review_required"] and not report["pooling_eligible"])
    check("source evidence verifies", M.verify_pdf_evidence(raw,evidence) == evidence["marker"])
    refused("changed PDF refuses evidence", lambda: M.verify_pdf_evidence(raw+b"\n", evidence), "SOURCE_PDF_MODIFIED")
    wrong = copy.deepcopy(evidence)
    wrong["marker"]["center"][1] += 1
    refused("changed center refuses evidence", lambda: M.verify_pdf_evidence(raw, wrong), "SOURCE_MARKER_MODIFIED")
    wrong = copy.deepcopy(evidence)
    wrong["method"] = "MODEL_ESTIMATE"
    refused("unknown evidence method", lambda: M.verify_pdf_evidence(raw, wrong), "UNKNOWN_EVIDENCE")
    refused("marker must belong to report", lambda: M.marker_evidence(report, {"center":[1,2]}), "NOT_IN_REPORT")
    with tempfile.TemporaryDirectory() as tmp:
        source, target = Path(tmp)/"synthetic.pdf", Path(tmp)/"proposals.json"
        source.write_bytes(raw)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = M.main([str(source),"--page","1","--out",str(Path(tmp)/"figure_values_accepted.csv")])
        check("CLI cannot write accepted CSV", rc == 2 and not (Path(tmp)/"figure_values_accepted.csv").exists())
        check("CLI writes source-bound proposal JSON", M.main([str(source),"--page","1","--out",str(target)]) == 0 and json.loads(target.read_text())["pdf_sha256"] == hashlib.sha256(raw).hexdigest())
        before = target.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            rc = M.main([str(source),"--page","1","--out",str(target)])
        check("CLI refuses output overwrite", rc == 2 and target.read_bytes() == before)
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = M.main([str(source),"--page","1"])
        check("CLI calls the inspector", rc == 0 and len(json.loads(stdout.getvalue())["markers"]) == 2)

# Same count in both CI profiles. The full profile opens an independently
# specified source PDF; the core profile proves that missing PDF support fails.
if importlib.util.find_spec("pypdf"):
    actual = M.inspect_pdf(raw, 1)
    check("declared backend forward contract", [p["center"] for p in actual["markers"]] == [[20,20],[20,20.5]])
    refused("page range checked", lambda: M.inspect_pdf(raw,2), "PAGE_OUT_OF_RANGE")
else:
    refused("declared backend forward contract", lambda: M.inspect_pdf(raw,1), "PDF_BACKEND_UNAVAILABLE")
    refused("page range checked", lambda: M.inspect_pdf(raw,2), "PDF_BACKEND_UNAVAILABLE")

print("FDT_SCENARIOS_RUN=%d" % len(checks))
