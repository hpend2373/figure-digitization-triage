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
    "Page", "Page_Raster", "Page_Raster_SHA256",
    "Figure_Number", "Caption_Text", "Caption_BBox", "Figure_BBox",
    "Extraction_Method", "Confidence", "Confidence_Reason",
    "Human_Verification_Status", "Verified_By", "Verified_At",
    "Observed_Panel_Count", "Note",
)

#: The only status a machine may write, and the two a person may.
DRAFT_PENDING = "PENDING"
DRAFT_STATUSES = (DRAFT_PENDING, "CONFIRMED", "REJECTED")

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
    above = [b for b in blocks if b[0] == page and b[4] <= top]
    lower_edge = max((b[4] for b in above), default=0.0)
    left = min([b[1] for b in blocks if b[0] == page] or [0.0])
    right = max([b[3] for b in blocks if b[0] == page]
                or [page_size[0] if page_size else 0.0])
    if lower_edge >= top:
        return None
    return (left, lower_edge, right, top)


def draft_rows(path, document_id, backend=None, page_rasters=None):
    """One draft row per caption candidate, all of them PENDING.

    `page_rasters` is {page: path} when the pages have been rendered; the row
    then carries the raster and its hash, so the thing a person looked at on the
    contact sheet is the thing the row was written from.
    """
    method = backend or _default_backend()
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


def contact_sheet(path, rows, title=""):
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
             "code{font:12px ui-monospace,monospace;color:#555}</style>",
             "<h1>%s</h1>" % esc(title or "figure intake draft"),
             "<p>Every row is a <b>proposal</b>. Nothing here is an inventory "
             "until a person sets <code>Human_Verification_Status</code> to "
             "CONFIRMED or REJECTED, writes their <code>Reviewer_ID</code> and "
             "the date, and - for a confirmed row - counts the panels. "
             "Lowest confidence first.</p>",
             "<table><tr><th>draft<th>page<th>figure<th>caption<th>confidence"
             "<th>panels</th></tr>"]
    for row in ordered:
        low = float(row.get("Confidence") or 0) < LOW_CONFIDENCE
        parts.append(
            "<tr class='%s'><td><code>%s</code><td>%s<td>%s<td>%s<br>"
            "<code>caption %s | figure %s | %s</code><td>%s<br><code>%s</code>"
            "<td>%s</tr>"
            % ("low" if low else "", esc(row.get("Draft_ID")), esc(row.get("Page")),
               esc(row.get("Figure_Number")), esc(row.get("Caption_Text"))[:300],
               esc(row.get("Caption_BBox")), esc(row.get("Figure_BBox")),
               esc(row.get("Extraction_Method")), esc(row.get("Confidence")),
               esc(row.get("Confidence_Reason")),
               esc(row.get("Observed_Panel_Count")) or "&mdash;"))
    parts.append("</table>")
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
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    every, unreadable, silent = [], [], []
    for path in args.pdfs:
        stem = os.path.splitext(os.path.basename(path))[0]
        did = args.document_id or re.sub(r"[^A-Za-z0-9]+", "_", stem).upper()[:64]
        try:
            rows = draft_rows(path, did, backend=args.backend or None)
        except BackendUnavailable as exc:
            print("SKIP %s: %s" % (path, exc))
            continue
        except NotReadable as exc:
            # A corpus walk stops for nothing: this is the row that needs a
            # page render and a person, and saying so is the answer.
            print("NO TEXT LAYER %s: %s" % (path, exc))
            unreadable.append(path)
            continue
        every.extend(rows)
        if not rows:
            # A document that read fine and proposed nothing is the one nobody
            # notices: it leaves no row on the contact sheet, so it looks like
            # an article with no figures rather than a pattern that missed
            # them. `2016-2-11.pdf` was that document until `图` went in.
            silent.append(path)
        print("%-40s %d caption candidate(s)" % (os.path.basename(path), len(rows)))
    draft = write_draft(os.path.join(args.out, "figure_intake_draft.csv"), every)
    sheet = contact_sheet(os.path.join(args.out, "index.html"), every,
                          title="figure intake draft (%d row(s))" % len(every))
    low = [r for r in every if float(r["Confidence"]) < LOW_CONFIDENCE]
    print("wrote %s and %s" % (draft, sheet))
    print("%d row(s), %d below confidence %.1f - all PENDING until somebody "
          "says otherwise" % (len(every), len(low), LOW_CONFIDENCE))
    if unreadable:
        print("%d file(s) have no text layer this backend can read; they need "
              "a page render and a human pass:" % len(unreadable))
        for path in unreadable:
            print("  %s" % path)
    if silent:
        print("%d file(s) read but proposed nothing, which is not the same as "
              "having no figures - check the caption style by hand:"
              % len(silent))
        for path in silent:
            print("  %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
