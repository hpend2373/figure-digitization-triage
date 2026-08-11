"""Turn a folder of publisher PDFs into a DRAFT figure inventory to check.

    python3 corpus_intake.py PDF [PDF ...] --out DRAFT_DIR [--render]

The step before `compile_plan.py`. A publication's manifests start from a claim
nobody can automate - "this article has seven figures and this one has three
panels" - and until now that claim was typed by hand, once per figure, for every
article in the corpus. Publication 127 cost forty source-panel rows to digitize
three panels. At 116 publications that is the whole project's bottleneck, and
skipping the claim is not an option: it is what stops a figure disappearing
because nobody made a row for it.

So this proposes and never asserts. It reads the PDF's own text layer with
coordinates, finds the caption candidates, links each to the page region it
labels, and writes a draft row per figure with:

    where it came from   Source_Document_ID, Page, Page_Raster_SHA256
    what it says         Figure_Number, Caption_Text, Caption_BBox, Figure_BBox
    how it was found     Extraction_Method, Confidence
    who has checked it   Human_Verification_Status, Verified_By, Verified_At

`Human_Verification_Status` starts at `PENDING` and there is no path by which
this module writes anything else: `draft_rows` sets the word literally, and
`inventory_rows` refuses to turn a draft into `source_figure_manifest` rows
unless every row in it says `CONFIRMED` with a registered person and a panel
count beside it. The machine's job ends at "here is what I think is on page 6".

**Every document leaves a row, whatever happened to it.** The draft is a row
per CAPTION, so a document that read fine and proposed nothing, or that has no
text layer, or that nothing could open, contributed nothing to any file the walk
wrote - and on ninety-seven articles that is indistinguishable from ninety-seven
that worked. `intake_document_status.csv` is one row per PDF with what the
backend did, how many pages and candidates there were, whether the pages were
rendered, and WHAT HAS TO HAPPEN NEXT. `ledger_problems` refuses a walk whose
ledger does not account for every file it was handed, and `main` exits non-zero
when it does not.

**`--render` renders.** Every page to PNG, hashed into the draft row, and a
figure crop per candidate cut from the page and shown on the contact sheet - so
a person confirming a figure is looking at the figure rather than agreeing with
a bounding-box string. It is a LOOK-AT raster: the geometry a reader uses is
measured against a versioned spec at its own resolution, and mixing the two is
how a plan ends up pointing at a rendering it was not written against.

**The panel count is deliberately not proposed.** Counting the axes regions in a
printed figure is the one judgement the source inventory exists to record, its
method column says `HUMAN_VISUAL`, and a proposed count is a number a tired
person clicks past. The draft carries the figure's bounding box so a contact
sheet can show the picture, and the count comes from the person looking at it.

The PDF backend is optional, like `cv2` elsewhere in this package: `pdfminer.six`
if it is installed, `pdftotext -bbox-layout` from poppler if it is not, and a
refusal naming both if neither is. Which one ran is recorded per row, because a
caption box from one is not necessarily a caption box from the other.
"""
import argparse
import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: What a draft row carries. Every column is either evidence or provenance;
#: there is no column for a conclusion this module is allowed to reach.
DRAFT_COLUMNS = (
    "Draft_ID", "Source_Document_ID", "Source_File", "Source_File_SHA256",
    "Page", "Page_Raster", "Page_Raster_SHA256", "Figure_Crop",
    "Figure_Number", "Caption_Text", "Caption_BBox", "Figure_BBox",
    "Extraction_Method", "Confidence", "Confidence_Reason",
    "Human_Verification_Status", "Verified_By", "Verified_At",
    "Observed_Panel_Count", "Note",
)

#: The only status a machine may write, and the two a person may.
DRAFT_PENDING = "PENDING"
DRAFT_STATUSES = (DRAFT_PENDING, "CONFIRMED", "REJECTED")

#: One row per PDF the walk was given, whatever happened to it. The draft is a
#: row per CAPTION, so a document that read fine and proposed nothing leaves no
#: row at all - and on a walk of ninety-seven articles that is indistinguishable
#: from an article with no figures. The console said so; a console line is not
#: a record. This file is the record, and `ledger_problems` refuses a walk whose
#: ledger does not account for every file it was handed.
LEDGER_COLUMNS = (
    "Source_Document_ID", "Source_File", "Source_File_SHA256",
    "Text_Backend", "Text_Backend_Status", "Page_Count", "Text_Block_Count",
    "Caption_Candidate_Count", "Low_Confidence_Count",
    "Page_Render_Status", "Page_Render_Count", "Page_Raster_Dir",
    "Required_Action", "Detail",
    # The DOCUMENT-level claim, which no candidate row can make. Six confirmed
    # candidates in a seven-figure paper is six correct rows and a wrong
    # inventory, and the only thing that catches it is somebody who has seen
    # every page saying how many figures are on them.
    "Pages_Checked", "Observed_Figure_Count", "Document_Inventory_Status",
    # And which file this row is about, in full. `Source_File` is a basename,
    # and a corpus keeps `pub127/fulltext.pdf` beside `pub386/fulltext.pdf`.
    "Input_Path",
)

#: Where a document's own inventory stands. `VISUALLY_VERIFIED` is the only one
#: that lets its candidates become `source_figure_manifest` rows.
DOCUMENT_INVENTORY_STATUSES = ("PENDING", "VISUALLY_VERIFIED", "BLOCKED")

#: What the text layer did. Four of these are the reasons a document reaches a
#: person, and each needs a different thing done to it.
TEXT_BACKEND_STATUSES = (
    # the ordinary case: text came off the page and captions were proposed
    "TEXT_LAYER_OK",
    # text came off and no block opens with a figure label. NOT the same as
    # having no figures, and the pattern is what to check.
    "ZERO_CAPTION_CANDIDATES",
    # a scan, or not a PDF. Needs a page render and a person.
    "NO_TEXT_LAYER",
    # nothing is installed that can read a PDF. Needs an install, not a person.
    "BACKEND_UNAVAILABLE",
    # anything else, recorded rather than raised, because a corpus walk that
    # stops on file 41 has told you nothing about files 42 to 97.
    "INTAKE_FAILED",
)

#: Whether the pages were turned into pictures, and why not when they were not.
PAGE_RENDER_STATUSES = ("NOT_REQUESTED", "RENDERED", "RENDERER_UNAVAILABLE",
                        "RENDER_FAILED")

#: What has to happen next, per document. This is the column a person sorts on.
REQUIRED_ACTIONS = (
    "CONFIRM_ON_CONTACT_SHEET",   # the normal path: rows exist, check them
    "RENDER_CONTACT_SHEET",       # rows exist and there is no picture to check
    "INSTALL_A_PAGE_RENDERER",    # rows exist, a render was asked for, none came
    "CHECK_CAPTION_STYLE",        # read fine, proposed nothing
    "RENDER_AND_INVENTORY_BY_EYE",  # a real PDF with no text layer
    "INSTALL_A_PDF_BACKEND",      # nothing to read with
    "INVESTIGATE",                # it is not a PDF, or it broke
)

#: Status to action, ONE to one. The five statuses exist because each needs a
#: different thing done to it, and a vocabulary check does not say that: a row
#: reading NO_TEXT_LAYER / INSTALL_A_PDF_BACKEND passes every check and sends a
#: scanned page to whoever installs software. The mapping is the contract.
#:
#: TEXT_LAYER_OK is the exception with three answers, because whether there is
#: a PICTURE to confirm against is a property of the RENDERER, which is a
#: different tool from the text backend and fails independently of it.
STATUS_ACTION = {
    "ZERO_CAPTION_CANDIDATES": ("CHECK_CAPTION_STYLE",),
    "NO_TEXT_LAYER": ("RENDER_AND_INVENTORY_BY_EYE",),
    "BACKEND_UNAVAILABLE": ("INSTALL_A_PDF_BACKEND",),
    "INTAKE_FAILED": ("INVESTIGATE",),
    "TEXT_LAYER_OK": ("CONFIRM_ON_CONTACT_SHEET", "RENDER_CONTACT_SHEET",
                      "INSTALL_A_PAGE_RENDERER"),
}

#: And the render state decides WHICH of the three. Confirming a figure from a
#: bounding-box string is agreeing with a number, so a document whose pages were
#: never rendered is not ready for a contact sheet - it is waiting for one.
RENDER_ACTION = {
    "RENDERED": "CONFIRM_ON_CONTACT_SHEET",
    "NOT_REQUESTED": "RENDER_CONTACT_SHEET",
    "RENDERER_UNAVAILABLE": "INSTALL_A_PAGE_RENDERER",
    "RENDER_FAILED": "INSTALL_A_PAGE_RENDERER",
}

#: How the text came off the page. Recorded per row: a caption box from
#: pdfminer and one from poppler are not the same measurement, and a draft that
#: mixes them without saying so cannot be re-derived.
EXTRACTION_METHODS = ("PDFMINER_TEXT_BLOCKS", "POPPLER_BBOX_LAYOUT",
                      "PAGE_RENDER_PENDING_HUMAN")

#: A caption is a line that opens with a figure label. Deliberately narrow: the
#: cost of missing one is a person adding a row on the contact sheet, and the
#: cost of inventing one is a row in the inventory that no figure answers to.
#:
#: `图` / `圖` because this corpus is not all in English. The China Astronaut
#: Research and Training Center papers label their figures `图 1.` with an
#: English `Fig. 1.` underneath, and with a Latin-only pattern the whole
#: article came back as zero candidates - which reads exactly like an article
#: with no figures in it.
CAPTION_RE = re.compile(
    r"^\s*(?:Fig(?:ure)?\.?|FIG(?:URE)?\.?|图|圖)\s*"
    r"([0-9]{1,2}[A-Za-z]?)\b[\s.:–-]*(.*)",
    re.S)

#: Below this a row is still a draft, but the contact sheet should put it first.
LOW_CONFIDENCE = 0.6


class BackendUnavailable(Exception):
    """No PDF text backend is installed, so nothing can be proposed."""


class NotReadable(Exception):
    """A file the backend could not read as a PDF.

    Its own type, because "poppler is not installed" and "this .pdf is a
    scanned image with no text layer, or is not a PDF at all" are different
    answers: the first is fixed by installing something and the second by
    rendering the page and asking a person. A corpus walk reports both and
    stops for neither.
    """


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bbox_text(box):
    return "" if not box else ",".join("%.1f" % float(v) for v in box)


def page_count(path):
    """How many pages the PDF has, independently of any text backend.

    `max(block page number)` is not a page count: a paper whose last three
    pages are scanned figures reports a shorter document, and a scanned paper
    reports zero pages - which then looks like a file that is not a PDF. Read
    off the file's own structure, with poppler as the fallback, so the number
    survives a document with no text in it at all.
    """
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_pages
        return sum(1 for _ in extract_pages(path))
    except Exception:
        pass
    from shutil import which
    if which("pdfinfo"):
        try:
            out = subprocess.run(["pdfinfo", path], capture_output=True,
                                 text=True, check=True).stdout
            for line in out.splitlines():
                if line.startswith("Pages:"):
                    return int(line.split(":", 1)[1].strip())
        except Exception:
            pass
    return 0


def is_a_pdf(path):
    """Does this file begin with a PDF header?

    The cheapest true statement available, and the one that separates the two
    failures a walk must not confuse: a SCANNED paper is a valid PDF whose
    pages are pictures, and needs a render and an eye; a truncated download or
    an HTML error page saved as `.pdf` needs somebody to look at a stack trace.
    Filed together, 42% of this corpus goes to the wrong queue.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def text_blocks(path, backend=None):
    """[(page, x0, y0, x1, y1, text)] for a PDF, in reading order per page.

    Page numbers are 1-based, matching what `pdftoppm -f N` renders and what a
    person reads off the PDF viewer. Coordinates are PDF points with the origin
    at the TOP left - pdfminer reports from the bottom, so it is flipped here
    once rather than at every call site.
    """
    chosen = backend or _default_backend()
    try:
        if chosen == "PDFMINER_TEXT_BLOCKS":
            return _pdfminer_blocks(path)
        if chosen == "POPPLER_BBOX_LAYOUT":
            return _poppler_blocks(path)
    except Exception as exc:
        raise NotReadable("%s could not be read by %s (%s: %s)"
                          % (path, chosen, type(exc).__name__, exc)) from exc
    raise BackendUnavailable("%r is not a text backend (%s)"
                             % (chosen, "/".join(EXTRACTION_METHODS[:2])))


def _default_backend():
    try:
        import pdfminer.high_level                             # noqa: F401
    except Exception:
        pass
    else:
        return "PDFMINER_TEXT_BLOCKS"
    from shutil import which
    if which("pdftotext"):
        return "POPPLER_BBOX_LAYOUT"
    raise BackendUnavailable(
        "no PDF text backend: install pdfminer.six, or poppler-utils for "
        "pdftotext -bbox-layout")


def _pdfminer_blocks(path):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer
    out = []
    for number, layout in enumerate(extract_pages(path), start=1):
        height = float(layout.height)
        for element in layout:
            if not isinstance(element, LTTextContainer):
                continue
            text = element.get_text().strip()
            if not text:
                continue
            x0, y0, x1, y1 = element.bbox
            # PDF y grows upward; every consumer here thinks in page order.
            out.append((number, float(x0), height - float(y1),
                        float(x1), height - float(y0), text))
    return out


def _poppler_blocks(path):
    xml = subprocess.run(["pdftotext", "-bbox-layout", path, "-"],
                         capture_output=True, text=True, check=True).stdout
    root = ET.fromstring(xml)
    ns = {"x": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    out = []
    tag = (lambda name: "{%s}%s" % (ns["x"], name)) if ns else (lambda name: name)
    for number, page in enumerate(root.iter(tag("page")), start=1):
        for block in page.iter(tag("block")):
            words, box = [], None
            for word in block.iter(tag("word")):
                words.append((word.text or "").strip())
                here = (float(word.get("xMin")), float(word.get("yMin")),
                        float(word.get("xMax")), float(word.get("yMax")))
                box = here if box is None else (
                    min(box[0], here[0]), min(box[1], here[1]),
                    max(box[2], here[2]), max(box[3], here[3]))
            text = " ".join(w for w in words if w).strip()
            if text and box:
                out.append((number, box[0], box[1], box[2], box[3], text))
    return out


def caption_candidates(blocks):
    """The blocks that open with a figure label, as (page, number, text, bbox).

    One row per label. A caption printed twice on a page - a running header, a
    cross-reference in the body that happens to start a block - produces two
    candidates, and `draft_rows` scores both down rather than picking.
    """
    out = []
    for page, x0, y0, x1, y1, text in blocks:
        match = CAPTION_RE.match(text)
        if not match:
            continue
        out.append(dict(page=page, number=match.group(1),
                        text=" ".join(text.split()),
                        bbox=(x0, y0, x1, y1),
                        body=" ".join(match.group(2).split())))
    return out


def _confidence(candidate, same_label, blocks):
    """How much of a caption this looks like, and why in words.

    Not a probability. It orders the contact sheet: the rows a person should
    look at first are the ones with a reason attached.
    """
    reasons, score = [], 1.0
    if len(candidate["body"]) < 25:
        score -= 0.4
        reasons.append("the caption text is %d characters, so this may be a "
                       "cross-reference rather than a caption"
                       % len(candidate["body"]))
    if same_label > 1:
        score -= 0.3
        reasons.append("%d blocks in this document open with the same label"
                       % same_label)
    # Publication 127's forward run: page 6 carries a paragraph beginning
    # "Figure 7 shows the relationship between mean RRI and spectral powers",
    # and Figure 7's real caption is on page 9. A caption names its subject -
    # "Figure 5 Results from systolic arterial pressure" - and a sentence
    # about a figure continues in the third person. The first word after the
    # label being lower case is the whole difference, and it costs a score
    # rather than the row, because a caption that really does open with a
    # lower-case symbol must still reach the contact sheet.
    first = (candidate["body"].split(" ") or [""])[0]
    if first[:1].islower():
        score -= 0.3
        reasons.append("the label is followed by %r in lower case, so this "
                       "reads as a sentence about the figure rather than the "
                       "figure's own caption" % first)
    above = [b for b in blocks
             if b[0] == candidate["page"] and b[4] <= candidate["bbox"][1]]
    if not above:
        score -= 0.1
        reasons.append("nothing is printed above it on the page, which is "
                       "unusual for a caption")
    return max(0.0, round(score, 2)), "; ".join(reasons)


def figure_bbox(candidate, blocks, page_size=None):
    """The page region the caption most likely labels: the gap above it.

    A caption sits under its figure in this literature, so the region is
    bounded by the caption's top and by whatever text block is next above it.
    This is a LOOK HERE for a contact sheet, not a crop anybody measures from -
    the geometry a reader uses comes from the plan, measured on a raster.
    """
    page, top = candidate["page"], candidate["bbox"][1]
    cx0, cx1 = candidate["bbox"][0], candidate["bbox"][2]
    # IN THE SAME COLUMN. This literature is two-column, and taking the nearest
    # block above by y alone reaches across the gutter: the block directly
    # above a left-column caption is usually a paragraph in the RIGHT column at
    # almost the same height, so the region collapses to a sliver. Measured on
    # fifteen corpus PDFs, that is the difference between a crop a person can
    # confirm a figure from and a 848x33 strip of body text.
    #
    # "Same column" is horizontal overlap with the caption, which needs no
    # column detection and degrades to the old behaviour on a single-column
    # page, where everything overlaps everything.
    def overlaps(block):
        return min(cx1, block[3]) - max(cx0, block[1]) > 0

    same_page = [b for b in blocks if b[0] == page]
    column = [b for b in same_page if overlaps(b)] or same_page
    above = [b for b in column if b[4] <= top]
    lower_edge = max((b[4] for b in above), default=0.0)
    left = min([b[1] for b in column] or [0.0])
    right = max([b[3] for b in column]
                or [page_size[0] if page_size else 0.0])
    if lower_edge >= top:
        return None
    return (left, lower_edge, right, top)


def draft_rows(path, document_id, backend=None, page_rasters=None,
               blocks=None):
    """One draft row per caption candidate, all of them PENDING.

    `page_rasters` is {page: path} when the pages have been rendered; the row
    then carries the raster and its hash, so the thing a person looked at on the
    contact sheet is the thing the row was written from.

    `blocks` is the already-parsed text layer. The caller usually has it - it
    needed the block count to decide what kind of document this is - and
    parsing twice is not only twice the cost over 116 papers: the ledger's
    `Text_Block_Count` and the draft's candidates then come from two different
    parses, and the second one is free to fail after the first succeeded, which
    breaks the "never raises" contract the ledger depends on.
    """
    method = backend or _default_backend()
    if blocks is None:
        blocks = text_blocks(path, backend=method)
    candidates = caption_candidates(blocks)
    # Counted across the DOCUMENT, not the page. Publication 127 prints the
    # sentence "Figure 7 shows the relationship..." on page 6 and Figure 7's
    # caption on page 9; per page, neither knows about the other and both come
    # out at full confidence.
    labels = {}
    for candidate in candidates:
        labels[candidate["number"]] = labels.get(candidate["number"], 0) + 1
    digest = file_sha256(path)
    rows = []
    for i, candidate in enumerate(candidates, start=1):
        score, why = _confidence(candidate, labels[candidate["number"]], blocks)
        raster = (page_rasters or {}).get(candidate["page"], "")
        rows.append({
            "Draft_ID": "%s_D%03d" % (document_id, i),
            "Source_Document_ID": document_id,
            "Source_File": os.path.basename(path),
            "Source_File_SHA256": digest,
            "Page": candidate["page"],
            "Page_Raster": raster,
            "Page_Raster_SHA256": file_sha256(raster) if raster else "",
            "Figure_Crop": "",
            "Figure_Number": "FIG%s" % candidate["number"],
            "Caption_Text": candidate["text"],
            "Caption_BBox": _bbox_text(candidate["bbox"]),
            "Figure_BBox": _bbox_text(figure_bbox(candidate, blocks)),
            "Extraction_Method": method,
            "Confidence": "%.2f" % score,
            "Confidence_Reason": why,
            # The only value this module may write. A draft is a question.
            "Human_Verification_Status": DRAFT_PENDING,
            "Verified_By": "", "Verified_At": "",
            "Observed_Panel_Count": "",
            "Note": "",
        })
    return rows


def render_pages(path, out_dir, dpi=150, first=None, last=None):
    """Every page of a PDF as a PNG, or a refusal naming the renderer.

    Returns ({page: png_path}, status). `pdftoppm` because it is what the rest
    of this project already renders publisher pages with, and because the page
    a person confirms on the contact sheet has to be reproducible from the file
    plus a command - not from whatever a library happened to do.

    The DPI is deliberately low. This raster is a PICTURE TO LOOK AT, not a
    raster anybody measures on: the geometry a reader uses is measured against
    a versioned spec at its own resolution, and mixing the two is how a plan
    ends up pointing at a rendering it was not written against.
    """
    from shutil import which
    if not which("pdftoppm"):
        return {}, "RENDERER_UNAVAILABLE"
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, "page")
    cmd = ["pdftoppm", "-r", str(int(dpi)), "-png"]
    if first:
        cmd += ["-f", str(int(first))]
    if last:
        cmd += ["-l", str(int(last))]
    try:
        subprocess.run(cmd + [path, stem], capture_output=True, check=True)
    except Exception:
        return {}, "RENDER_FAILED"
    out = {}
    for name in sorted(os.listdir(out_dir)):
        if not name.startswith("page-") or not name.endswith(".png"):
            continue
        try:
            number = int(name[len("page-"):-len(".png")])
        except ValueError:
            continue
        out[number] = os.path.join(out_dir, name)
    return out, ("RENDERED" if out else "RENDER_FAILED")


def crop_figure(row, page_raster, out_path, pdf_page_size=None, pad=8):
    """The figure region of a page raster, as its own PNG, or None.

    `Figure_BBox` is in PDF points and the raster is in pixels, so the scale
    comes from the two heights rather than from the DPI the caller thinks it
    asked for - a renderer that rounded the page to an even pixel count would
    otherwise shift every crop by a hair, and the crop is the thing a person
    decides "yes, that is a figure" from.
    """
    box = str(row.get("Figure_BBox", "")).strip()
    if not box or not page_raster or not os.path.exists(page_raster):
        return None
    try:
        from PIL import Image
    except Exception:                                   # pragma: no cover
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in box.split(",")]
    except ValueError:
        return None
    image = Image.open(page_raster)
    if not pdf_page_size:
        # Without the page's real size in points there is no scale, and
        # guessing US Letter puts an A4 crop 9% out in y - which is a caption's
        # height at the bottom of a page. No crop is an honest answer; a
        # mis-scaled one is a person confirming the wrong rectangle.
        return None
    sx = image.width / float(pdf_page_size[0])
    sy = image.height / float(pdf_page_size[1])
    left = max(0, int(x0 * sx) - pad)
    top = max(0, int(y0 * sy) - pad)
    right = min(image.width, int(x1 * sx) + pad)
    bottom = min(image.height, int(y1 * sy) + pad)
    if right - left < 8 or bottom - top < 8:
        return None
    image.crop((left, top, right, bottom)).save(out_path)
    return out_path


def ledger_row(path, document_id, **kw):
    """One row about one document, with every column present."""
    row = {c: "" for c in LEDGER_COLUMNS}
    row.update(Source_Document_ID=document_id,
               Source_File=os.path.basename(path), Input_Path=path,
               Page_Render_Status="NOT_REQUESTED",
               Document_Inventory_Status="PENDING")
    row.update(kw)
    return row


def write_ledger(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(LEDGER_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in LEDGER_COLUMNS})
    return path


def ledger_problems(rows, expected_files=()):
    """[(Source_File, code, detail)] for a ledger that cannot be what it says.

    The point of the file is COMPLETENESS, so the checks are about the walk and
    not about any one document: every file handed in has a row, no file has
    two, and every row's status and action are ones this module defines. A
    ledger that quietly omits the file that failed is worse than no ledger,
    because it reads as a clean run.
    """
    out = []
    seen, ids = {}, {}
    for row in rows:
        name = str(row.get("Source_File", "")).strip()
        key = str(row.get("Input_Path", "")).strip() or name
        did = str(row.get("Source_Document_ID", "")).strip()
        if not name or not did:
            out.append((name, "LEDGER_ROW_INCOMPLETE",
                        "a ledger row with no Source_File or no "
                        "Source_Document_ID"))
            continue
        # Keyed on the PATH. A corpus keeps `pub127/fulltext.pdf` next to
        # `pub386/fulltext.pdf`, and on basenames those are one document twice
        # - which then also hides a genuinely missing file behind the other's
        # row, so the completeness check reports clean while a paper is gone.
        seen.setdefault(key, []).append(did)
        ids.setdefault(did, []).append(key)
        status = str(row.get("Text_Backend_Status", "")).strip()
        if status not in TEXT_BACKEND_STATUSES:
            out.append((name, "LEDGER_STATUS_UNKNOWN",
                        "%r is not %s" % (status,
                                          "/".join(TEXT_BACKEND_STATUSES))))
        render = str(row.get("Page_Render_Status", "")).strip()
        if render not in PAGE_RENDER_STATUSES:
            out.append((name, "LEDGER_RENDER_STATUS_UNKNOWN",
                        "%r is not %s" % (render,
                                          "/".join(PAGE_RENDER_STATUSES))))
        action = str(row.get("Required_Action", "")).strip()
        if action not in REQUIRED_ACTIONS:
            out.append((name, "LEDGER_ACTION_UNKNOWN",
                        "%r is not %s" % (action, "/".join(REQUIRED_ACTIONS))))
        # ONE STATUS, ONE ACTION. The five statuses exist because each needs a
        # different thing done to it, and checking both against a vocabulary
        # does not say that: NO_TEXT_LAYER / INSTALL_A_PDF_BACKEND passed every
        # check and sent a scanned page to whoever installs software.
        elif status in STATUS_ACTION \
                and action not in STATUS_ACTION[status]:
            out.append((name, "LEDGER_ACTION_CONTRADICTS_STATUS",
                        "%s says %s, and the action for it is %s"
                        % (name, status, " or ".join(STATUS_ACTION[status]))))
        elif status == "TEXT_LAYER_OK":
            render = str(row.get("Page_Render_Status", "")).strip()
            wanted = RENDER_ACTION.get(render)
            if wanted and action != wanted:
                out.append((name, "LEDGER_ACTION_CONTRADICTS_RENDER",
                            "the pages are %s and the action says %s; with %s "
                            "it is %s" % (render, action, render, wanted)))
        # And the counts have to agree with the status they were filed under.
        # A blank or unparsable count used to become -1 and pass everything.
        raw = str(row.get("Caption_Candidate_Count", "")).strip()
        blocks_raw = str(row.get("Text_Block_Count", "")).strip()
        try:
            count = int(raw) if raw else 0
        except ValueError:
            out.append((name, "LEDGER_COUNT_NOT_A_NUMBER",
                        "Caption_Candidate_Count=%r" % raw))
            continue
        try:
            blocks = int(blocks_raw) if blocks_raw else 0
        except ValueError:
            out.append((name, "LEDGER_COUNT_NOT_A_NUMBER",
                        "Text_Block_Count=%r" % blocks_raw))
            continue
        for wrong, code, detail in (
                (status == "TEXT_LAYER_OK" and count < 1,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "no caption candidates and the status says the text layer was "
                 "fine; that is ZERO_CAPTION_CANDIDATES"),
                (status == "TEXT_LAYER_OK" and blocks < 1,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "no text blocks and the status says the text layer was fine"),
                (status == "ZERO_CAPTION_CANDIDATES" and count != 0,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "%d candidate(s) under ZERO_CAPTION_CANDIDATES" % count),
                (status == "ZERO_CAPTION_CANDIDATES" and blocks < 1,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "no text blocks either; that is NO_TEXT_LAYER"),
                (status == "NO_TEXT_LAYER" and blocks != 0,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "%d text block(s) under NO_TEXT_LAYER" % blocks),
                (status == "NO_TEXT_LAYER" and count != 0,
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "%d candidate(s) under NO_TEXT_LAYER" % count),
                (status == "BACKEND_UNAVAILABLE"
                 and str(row.get("Text_Backend", "")).strip(),
                 "LEDGER_STATUS_CONTRADICTS_COUNT",
                 "a backend is named under BACKEND_UNAVAILABLE"),
                (status == "INTAKE_FAILED"
                 and not str(row.get("Detail", "")).strip(),
                 "LEDGER_FAILURE_UNEXPLAINED",
                 "INTAKE_FAILED with nothing in Detail")):
            if wrong:
                out.append((name, code, detail))
    for key, dids in sorted(seen.items()):
        if len(dids) > 1:
            out.append((key, "LEDGER_DOCUMENT_DUPLICATED",
                        "%s appears %d times" % (key, len(dids))))
    # And one identifier per document, because `Source_Document_ID` names the
    # page directory and prefixes every `Draft_ID`: two inputs sharing one is
    # two documents writing over each other's pages.
    for did, keys in sorted(ids.items()):
        if len(set(keys)) > 1:
            out.append((did, "LEDGER_DOCUMENT_ID_COLLIDES",
                        "%s is the identifier of %d different files: %s"
                        % (did, len(set(keys)), ", ".join(sorted(set(keys))))))
    for path in expected_files:
        if path not in seen and os.path.basename(path) not in seen:
            out.append((os.path.basename(path), "LEDGER_DOCUMENT_MISSING",
                        "%s was walked and the ledger does not account for it"
                        % path))
    return out


def write_draft(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(DRAFT_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in DRAFT_COLUMNS})
    return path


def draft_problems(rows):
    """[(Draft_ID, code, detail)] for a draft that cannot be what it says.

    Checked when a draft is READ, not only when it is written, because the file
    goes to a person and comes back edited. What a person may change is the
    status, the panel count, the note and their own name; what they may not do
    is confirm a row without saying who they are, or leave a machine's
    `PENDING` beside a panel count nobody counted.
    """
    out = []
    seen = set()
    for row in rows:
        did = str(row.get("Draft_ID", "")).strip()
        if not did:
            out.append(("", "DRAFT_ID_MISSING", "a draft row with no Draft_ID"))
            continue
        if did in seen:
            out.append((did, "DRAFT_ID_DUPLICATE", did))
        seen.add(did)
        status = str(row.get("Human_Verification_Status", "")).strip().upper()
        if status not in DRAFT_STATUSES:
            out.append((did, "DRAFT_STATUS_UNKNOWN",
                        "%r is not %s" % (status, "/".join(DRAFT_STATUSES))))
            continue
        who = str(row.get("Verified_By", "")).strip()
        when = str(row.get("Verified_At", "")).strip()
        count = str(row.get("Observed_Panel_Count", "")).strip()
        if status == DRAFT_PENDING:
            if who or when:
                out.append((did, "DRAFT_PENDING_WITH_A_VERIFIER",
                            "%s is still PENDING and names %s as its verifier"
                            % (did, who or when)))
            if count:
                out.append((did, "DRAFT_PENDING_WITH_A_COUNT",
                            "%s carries Observed_Panel_Count=%s and nobody has "
                            "confirmed the figure exists" % (did, count)))
            continue
        if not who or not when:
            out.append((did, "DRAFT_VERDICT_UNATTRIBUTED",
                        "%s says %s and does not say who or when"
                        % (did, status)))
        if status == "CONFIRMED":
            # The one number the inventory exists to carry, and the one this
            # module refuses to guess.
            try:
                value = int(count)
                if value < 1:
                    raise ValueError
            except ValueError:
                out.append((did, "DRAFT_PANEL_COUNT_MISSING",
                            "%s is CONFIRMED with Observed_Panel_Count=%r; the "
                            "count is what a person is being asked for"
                            % (did, count)))
    return out


def inventory_rows(rows, reviewer_ids=(), publication_id=""):
    """`source_figure_manifest` rows from a draft, or a refusal.

    The join between the two halves of this design. Every row it emits came
    from a draft row a named person marked CONFIRMED with a panel count, and
    `Panel_Count_Method` is `HUMAN_VISUAL` because that is what happened. A
    draft still holding a PENDING row does not produce a partial inventory: the
    caller gets the problems and no rows, because "these three figures are the
    article" is a claim about the whole article.
    """
    problems = list(draft_problems(rows))
    confirmed = [r for r in rows
                 if str(r.get("Human_Verification_Status", "")).strip().upper()
                 == "CONFIRMED"]
    pending = [r for r in rows
               if str(r.get("Human_Verification_Status", "")).strip().upper()
               == DRAFT_PENDING]
    if pending:
        problems.append(("", "DRAFT_NOT_FINISHED",
                         "%d row(s) are still PENDING, so the figure list is "
                         "not yet an inventory" % len(pending)))
    for row in confirmed:
        who = str(row.get("Verified_By", "")).strip()
        if reviewer_ids and who not in reviewer_ids:
            problems.append((str(row.get("Draft_ID", "")),
                             "DRAFT_VERIFIER_NOT_REGISTERED", who))
    if problems:
        return [], problems
    out = []
    for row in confirmed:
        out.append({
            "Source_Figure_ID": "SF_%s" % str(row.get("Draft_ID", "")).strip(),
            "Source_Document_ID": str(row.get("Source_Document_ID", "")).strip(),
            "Publication_ID": publication_id,
            "Figure_Number": str(row.get("Figure_Number", "")).strip(),
            "Source_File": str(row.get("Source_File", "")).strip(),
            "Source_Page": str(row.get("Page", "")).strip(),
            "Source_Image": str(row.get("Page_Raster", "")).strip(),
            "Source_Image_SHA256": str(row.get("Page_Raster_SHA256", "")).strip(),
            "Observed_Panel_Count": str(row.get("Observed_Panel_Count", "")).strip(),
            "Inventory_Status": "VISUALLY_VERIFIED",
            "Panel_Count_Method": "HUMAN_VISUAL",
            "Reviewer_ID": str(row.get("Verified_By", "")).strip(),
            "Inspection_Date": str(row.get("Verified_At", "")).strip(),
            "Note": str(row.get("Note", "")).strip()
                    or "confirmed on the intake contact sheet",
        })
    return out, []


def contact_sheet(path, rows, title="", root=None):
    """One page listing every draft row, lowest confidence first.

    The point of the sheet is that a person answers three questions per row -
    is this a figure, how many panels, is the caption right - so the rows most
    likely to be wrong are at the top and every row shows the reason it scored
    what it did.
    """
    def esc(text):
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    ordered = sorted(rows, key=lambda r: (float(r.get("Confidence") or 0),
                                          str(r.get("Draft_ID"))))
    parts = ["<!doctype html><meta charset='utf-8'><title>intake draft</title>",
             "<style>body{font:14px/1.5 system-ui,sans-serif;margin:2rem;max-width:60rem}"
             "tr.low td{background:#fff6e5}td,th{border-bottom:1px solid #ddd;"
             "padding:.4rem .6rem;vertical-align:top;text-align:left}"
             "code{font:12px ui-monospace,monospace;color:#555}"
             "img{max-width:16rem;max-height:12rem;border:1px solid #ccc}"
             "</style>",
             "<h1>%s</h1>" % esc(title or "figure intake draft"),
             "<p>Every row is a <b>proposal</b>. Nothing here is an inventory "
             "until a person sets <code>Human_Verification_Status</code> to "
             "CONFIRMED or REJECTED, writes their <code>Reviewer_ID</code> and "
             "the date, and - for a confirmed row - counts the panels. "
             "Lowest confidence first.</p>",
             "<table><tr><th>draft<th>picture<th>page<th>figure<th>caption"
             "<th>confidence<th>panels</th></tr>"]
    for row in ordered:
        low = float(row.get("Confidence") or 0) < LOW_CONFIDENCE
        # The PICTURE, when the pages were rendered. A person confirming a
        # figure from a bounding-box string is not confirming a figure; they
        # are agreeing with a number. The crop is the whole reason `--render`
        # exists, and the row records which raster it was cut from.
        crop = str(row.get("Figure_Crop", "")).strip()
        picture = ("<a href='%s'><img src='%s' loading='lazy'></a>"
                   % (esc(crop), esc(crop))) if crop else "&mdash;"
        parts.append(
            "<tr class='%s'><td><code>%s</code><td>%s<td>%s<td>%s<td>%s<br>"
            "<code>caption %s | figure %s | %s</code><td>%s<br><code>%s</code>"
            "<td>%s</tr>"
            % ("low" if low else "", esc(row.get("Draft_ID")), picture,
               esc(row.get("Page")),
               esc(row.get("Figure_Number")), esc(row.get("Caption_Text"))[:300],
               esc(row.get("Caption_BBox")), esc(row.get("Figure_BBox")),
               esc(row.get("Extraction_Method")), esc(row.get("Confidence")),
               esc(row.get("Confidence_Reason")),
               esc(row.get("Observed_Panel_Count")) or "&mdash;"))
    parts.append("</table>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


def intake_document(path, document_id, out_dir, backend=None, render_dpi=0,
                    input_path=""):
    """One document in; (draft rows, ledger row) out. Never raises.

    The whole point of the pair is that the SECOND value always exists. A walk
    of ninety-seven articles has to say something about all ninety-seven, and
    the failures are the ones worth saying something about.
    """
    # STALE PAGES FIRST. `pdftoppm` writes page-1..page-N and the collector
    # takes every `page-*.png` it finds, so a second run over a shorter
    # document of the same ID inherits the first one's tail as though those
    # pages were its own.
    page_dir = os.path.join(out_dir, "pages", document_id)
    crop_dir = os.path.join(out_dir, "crops", document_id)
    for stale in (page_dir, crop_dir):
        shutil.rmtree(stale, ignore_errors=True)
    rasters, render_status = {}, "NOT_REQUESTED"
    if render_dpi:
        rasters, render_status = render_pages(path, page_dir, dpi=render_dpi)
    base = dict(Page_Render_Status=render_status,
                Page_Render_Count=len(rasters) or "",
                Page_Raster_Dir=(os.path.relpath(page_dir, out_dir)
                                 if rasters else ""),
                Input_Path=input_path or path)

    def refuse(status, detail, **extra):
        return [], ledger_row(path, document_id, Text_Backend_Status=status,
                              Required_Action=STATUS_ACTION[status][0],
                              Detail=detail, **dict(base, **extra))

    try:
        digest = file_sha256(path)
    except OSError as exc:
        return refuse("INTAKE_FAILED", "%s: %s" % (type(exc).__name__, exc))
    base["Source_File_SHA256"] = digest
    # A FILE THAT IS NOT A PDF is not a scanned paper. One needs a render and
    # an eye, the other needs somebody to look at what was downloaded, and
    # filing them together sends whichever is more common to the wrong queue.
    if not is_a_pdf(path):
        return refuse("INTAKE_FAILED",
                      "the file does not begin with a PDF header")
    pages = page_count(path)
    base["Page_Count"] = pages or ""
    method = backend
    try:
        method = method or _default_backend()
    except BackendUnavailable as exc:
        return refuse("BACKEND_UNAVAILABLE", str(exc), Caption_Candidate_Count=0)
    base["Text_Backend"] = method
    try:
        blocks = text_blocks(path, backend=method)
    except NotReadable as exc:
        blocks = None
        failure = str(exc)
    except Exception as exc:                            # pragma: no cover
        return refuse("INTAKE_FAILED", "%s: %s" % (type(exc).__name__, exc))
    else:
        failure = ""
    # A VALID PDF WITH NO TEXT is the scanned-paper case, and the backend does
    # not have to raise to produce it: pdfminer walks an image-only page
    # happily and returns nothing. Whether the parse threw or came back empty
    # is a fact about the parser; whether there is text on the page is the fact
    # the queue is sorted on.
    if blocks is None or not blocks:
        return refuse("NO_TEXT_LAYER",
                      failure or "%d page(s) and no text block on any of them"
                      % pages,
                      Text_Block_Count=0, Caption_Candidate_Count=0)
    rows = draft_rows(path, document_id, backend=method, page_rasters=rasters,
                      blocks=blocks)
    low = sum(1 for r in rows if float(r["Confidence"]) < LOW_CONFIDENCE)
    base.update(Text_Block_Count=len(blocks), Caption_Candidate_Count=len(rows),
                Low_Confidence_Count=low)
    if not rows:
        return refuse("ZERO_CAPTION_CANDIDATES",
                      "%d text blocks and no block opens with a figure label"
                      % len(blocks))
    if rasters:
        os.makedirs(crop_dir, exist_ok=True)
        sizes = page_sizes(path, rasters=rasters)
        for row in rows:
            made = crop_figure(
                row, rasters.get(row["Page"], ""),
                os.path.join(crop_dir, "%s.png" % row["Draft_ID"]),
                pdf_page_size=sizes.get(row["Page"]))
            row["Figure_Crop"] = (os.path.relpath(made, out_dir) if made else "")
    # And the action depends on whether there is a PICTURE to confirm against.
    # A contact sheet with no image on it asks a person to agree with a
    # bounding box, which is the thing rendering exists to stop.
    return rows, ledger_row(path, document_id,
                            Text_Backend_Status="TEXT_LAYER_OK",
                            Required_Action=RENDER_ACTION.get(
                                render_status, "RENDER_CONTACT_SHEET"),
                            **base)


def page_sizes(path, rasters=None):
    """{page: (width_pt, height_pt)} so a crop can be scaled to its raster.

    Tried three ways, because the fallback was a guess: `image.width / 612.0`
    assumes US Letter, and this corpus is largely A4 (595 x 842 pt), so a crop
    on a poppler-only machine came out scaled by 1.03 in x and 1.09 in y - off
    by most of a caption's height at the bottom of a page. pypdf and pdfminer
    read the MediaBox; poppler's `pdfinfo` prints it; and failing all three the
    caller is told nothing rather than told Letter.
    """
    try:
        from pypdf import PdfReader
        return {n: (float(p.mediabox.width), float(p.mediabox.height))
                for n, p in enumerate(PdfReader(path).pages, start=1)}
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_pages
        return {n: (float(layout.width), float(layout.height))
                for n, layout in enumerate(extract_pages(path), start=1)}
    except Exception:
        pass
    from shutil import which
    if which("pdfinfo"):
        try:
            out = subprocess.run(["pdfinfo", path], capture_output=True,
                                 text=True, check=True).stdout
            for line in out.splitlines():
                if line.startswith("Page size:"):
                    parts = line.split(":", 1)[1].split()
                    w, h = float(parts[0]), float(parts[2])
                    pages = page_count(path) or len(rasters or {}) or 1
                    return {n: (w, h) for n in range(1, pages + 1)}
        except Exception:
            pass
    return {}


def document_sheet(path, ledger, rows_by_document, out_dir, title=""):
    """Every PAGE of every document, with its candidates listed beside it.

    The candidate sheet answers "is each of these six a figure". It cannot
    answer "are these six all of them", and that is the claim the source
    inventory exists to carry: a paper with seven figures whose caption pattern
    missed one comes back with six confirmed rows and looks complete.
    `inventory_rows` cannot catch it either - it checks the rows that exist.

    So this shows the pages. A person scrolls a document, counts the figures
    they can see, and types that number; a figure with no candidate beside it
    is visible precisely because the page is on the screen and nothing is
    pointing at it.
    """
    def esc(text):
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    parts = ["<!doctype html><meta charset='utf-8'><title>%s</title>" % esc(title),
             "<style>body{font:14px/1.6 system-ui,sans-serif;margin:2rem}"
             "h2{margin:2.5rem 0 .3rem;font-size:1.1rem}"
             ".doc{border-top:2px solid #333;padding-top:.4rem}"
             ".pages{display:flex;flex-wrap:wrap;gap:.6rem;margin:.6rem 0}"
             ".page{width:11rem}.page img{width:100%;border:1px solid #ccc}"
             ".page .n{font:11px ui-monospace,monospace;color:#666}"
             ".cand{background:#f6f9f6;border-left:3px solid #1b5e20;"
             "padding:.3rem .6rem;margin:.2rem 0;font-size:12.5px}"
             ".none{background:#fff3e0;border-left:3px solid #e65100;"
             "padding:.4rem .7rem;font-size:12.5px}"
             "code{font:12px ui-monospace,monospace;color:#555}</style>",
             "<h1>%s</h1>" % esc(title or "document review"),
             "<p>One section per document, every page in it. The candidate list "
             "under each document is what the caption pattern found; the pages "
             "are how you tell whether it found <b>all of them</b>. Count the "
             "figures you can see and write that number in "
             "<code>Observed_Figure_Count</code>, then mark "
             "<code>Pages_Checked</code>. A figure with no candidate beside it "
             "is one you add by hand.</p>"]
    for entry in ledger:
        did = str(entry.get("Source_Document_ID", ""))
        parts.append("<div class='doc'><h2>%s <code>%s</code></h2>"
                     % (esc(entry.get("Source_File")), esc(did)))
        parts.append("<p><code>%s</code> &middot; %s page(s) &middot; %s "
                     "candidate(s) &middot; next: <b>%s</b></p>"
                     % (esc(entry.get("Text_Backend_Status")),
                        esc(entry.get("Page_Count")),
                        esc(entry.get("Caption_Candidate_Count")),
                        esc(entry.get("Required_Action"))))
        cands = rows_by_document.get(did, [])
        if cands:
            for row in cands:
                parts.append("<div class='cand'><code>%s</code> page %s "
                             "&middot; %s &middot; confidence %s<br>%s</div>"
                             % (esc(row.get("Draft_ID")), esc(row.get("Page")),
                                esc(row.get("Figure_Number")),
                                esc(row.get("Confidence")),
                                esc(row.get("Caption_Text"))[:200]))
        else:
            parts.append("<div class='none'>No candidate at all. Whatever is "
                         "in this document, nothing here points at it.</div>")
        raster_dir = str(entry.get("Page_Raster_Dir") or "")
        pages = []
        if raster_dir and os.path.isdir(os.path.join(out_dir, raster_dir)):
            pages = sorted(os.listdir(os.path.join(out_dir, raster_dir)))
        if pages:
            parts.append("<div class='pages'>")
            for name in pages:
                rel = os.path.join(raster_dir, name)
                parts.append("<div class='page'><a href='%s'><img src='%s' "
                             "loading='lazy'></a><div class='n'>%s</div></div>"
                             % (esc(rel), esc(rel), esc(name)))
            parts.append("</div>")
        else:
            parts.append("<div class='none'>The pages were not rendered, so "
                         "there is nothing here to count figures on. Run the "
                         "walk again with <code>--render</code>.</div>")
        parts.append("</div>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--document-id", default="",
                    help="Source_Document_ID for a single PDF; defaults to the "
                         "file stem, upper-cased")
    ap.add_argument("--backend", default="", choices=("",) + EXTRACTION_METHODS[:2])
    ap.add_argument("--render", nargs="?", type=int, const=150, default=0,
                    metavar="DPI",
                    help="render every page to PNG at this DPI (default 150) "
                         "so the contact sheet shows the picture. A LOOK-AT "
                         "raster, never one to measure on")
    args = ap.parse_args(argv)
    if args.document_id and len(args.pdfs) > 1:
        ap.error("--document-id names ONE document; %d files were given, and "
                 "they would share a page directory and a Draft_ID prefix"
                 % len(args.pdfs))
    os.makedirs(args.out, exist_ok=True)
    every, ledger = [], []
    for path in args.pdfs:
        stem = os.path.splitext(os.path.basename(path))[0]
        did = args.document_id or re.sub(r"[^A-Za-z0-9]+", "_", stem).upper()[:64]
        rows, status = intake_document(path, did, args.out,
                                       backend=args.backend or None,
                                       render_dpi=args.render,
                                       input_path=path)
        every.extend(rows)
        ledger.append(status)
        print("%-44s %-24s %s" % (os.path.basename(path)[:44],
                                  status["Text_Backend_Status"],
                                  status["Required_Action"]))
    draft = write_draft(os.path.join(args.out, "figure_intake_draft.csv"), every)
    book = write_ledger(os.path.join(args.out, "intake_document_status.csv"),
                        ledger)
    sheet = contact_sheet(os.path.join(args.out, "index.html"), every,
                          title="figure intake draft (%d row(s))" % len(every),
                          root=args.out)
    by_document = {}
    for row in every:
        by_document.setdefault(row["Source_Document_ID"], []).append(row)
    pages_sheet = document_sheet(
        os.path.join(args.out, "documents.html"), ledger, by_document, args.out,
        title="document review (%d document(s), %d candidate(s))"
              % (len(ledger), len(every)))
    print("and %s - every page, for counting the figures nothing pointed at"
          % pages_sheet)
    low = [r for r in every if float(r["Confidence"]) < LOW_CONFIDENCE]
    print("wrote %s, %s and %s" % (draft, book, sheet))
    print("%d row(s), %d below confidence %.1f - all PENDING until somebody "
          "says otherwise" % (len(every), len(low), LOW_CONFIDENCE))
    # The ledger is the answer to "did anything disappear", so it is checked
    # against the list of files this walk was actually given.
    problems = ledger_problems(ledger, expected_files=args.pdfs)
    for name, code, detail in problems:
        print("LEDGER %-34s %s: %s" % (name[:34], code, detail))
    by_action = {}
    for row in ledger:
        by_action.setdefault(row["Required_Action"], []).append(row["Source_File"])
    for action in REQUIRED_ACTIONS:
        names = by_action.get(action, [])
        if not names:
            continue
        print("%-28s %3d document(s)" % (action, len(names)))
        if action != "CONFIRM_ON_CONTACT_SHEET":
            for name in names:
                print("    %s" % name)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
