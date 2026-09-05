# -*- coding: utf-8 -*-
"""The whole caption, and what it says the error bars are.

    python3 caption_fulltext.py RUN_DIR --pdf-root DIR [--out FILE]

WHY THIS EXISTS. `corpus_intake.py` keeps ONE LINE of each caption - the line
that opens with the figure label - because one line is all it needs to say
"there is a figure here". Across run2 that line has a median length of 74
characters and is cut mid-word ("Relationships between stand-"). The sentence
that says what the error bars are ("Error bars show the standard deviation at
each point") is at the END of the caption, or in the Methods, and the pilot on
publication 397 finished with 0 accepted values for exactly this reason: the
paper never said whether the bars were SD or SEM, and a value whose dispersion
is unnamed cannot be pooled. Before anyone plans 481 figures, this module says
how many of them can be planned at all.

WHAT IT DOES. For every draft row it re-reads the page with the same backend
the intake used, finds the block the caption line came from, and takes that
block from the caption line down. Then it names the dispersion the caption
declares, and separately the one the document declares for itself ("Data are
presented as mean ± SEM"), with the sentence it read it from.

WHAT IT REFUSES.
  * A source file whose SHA-256 is not the one the draft recorded is not read.
  * A caption whose block cannot be found on the page again is `BLOCK_NOT_FOUND`,
    and one whose line is not in that block is `LINE_NOT_IN_BLOCK`. Nothing
    is reconstructed from a different block.
  * A caption that is the last line of its block is `LINE_ONLY`. The rest of it
    may be in the block below, but so is the body text, so this module does
    not go there - with ONE exception: a line that is nothing but a label
    ("Figure 1") cannot be a caption, and its text is taken from the blocks
    directly below under measured limits (`LABEL_*`), reported as
    `LABEL_NEXT_BLOCKS` with the gap and block count so a reader can see it
    was reconstructed. Everything else is counted, not guessed.
  * The dispersion columns are EVIDENCE, not a verdict. `Errorbar_Definition`
    names what the words say and `Errorbar_Evidence` quotes them; a caption
    naming two things is `AMBIGUOUS`, a "±" with no name is `PM_UNNAMED`, and
    silence is `UNSTATED`. The plan's `Errorbar_Definition_Source` is still
    written by a person who has read the paper.
"""
import argparse
import csv
import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import corpus_intake as CI                                      # noqa: E402

DRAFT = "figure_intake_draft.csv"
OUT = "caption_fulltext.csv"

STATUS_BLOCK = "BLOCK"                  # the block, from the caption line down
STATUS_LINE_ONLY = "LINE_ONLY"          # caption is the block's last line
STATUS_NO_BLOCK = "BLOCK_NOT_FOUND"     # the intake's block is not on the page
STATUS_NO_LINE = "LINE_NOT_IN_BLOCK"    # the block is there, the line is not
STATUS_NO_SOURCE = "SOURCE_MISSING"     # no such file under --pdf-root
STATUS_BAD_SOURCE = "SOURCE_SHA_MISMATCH"
STATUS_UNREADABLE = "SOURCE_UNREADABLE"
STATUS_NO_BBOX = "NO_CAPTION_BBOX"      # a row the intake never placed
STATUS_LABEL_NEXT = "LABEL_NEXT_BLOCKS"  # label-only line; body read from the blocks below

#: THE ONE PLACE THIS MODULE READS OUTSIDE THE CAPTION'S OWN BLOCK, and only
#: when the caption line is nothing but a label. "Figure 1" on its own cannot
#: be a caption; the text has to be somewhere, and in the two Research Square
#: preprints of run2 (nine rows) it is the block directly below. Measured
#: there: the first body block starts 14.5-21.7 pt under the label, the
#: paragraph continues in blocks 4-6 pt apart (pdfminer splits it), and what
#: comes after is 30 pt or more away, or a "Page 9/12" footer that does not
#: share the column, or the next figure's label. The thresholds sit in those
#: gaps rather than on the data.
LABEL_FIRST_GAP_MAX = 30.0     # label bottom -> first body block top, pt
LABEL_CONT_GAP_MAX = 10.0      # between consecutive body blocks, pt
LABEL_COLUMN_OVERLAP = 0.5     # share of the narrower width the blocks must share
LABEL_MAX_BLOCKS = 6
PAGE_FOOTER = re.compile(r"^\s*(?:page\s+\d+(?:\s*(?:/|of)\s*\d+)?|\d+\s*/\s*\d+)\s*$", re.I)
TABLE_LABEL = re.compile(r"^\s*(?:Table|TABLE)\s*[0-9]", re.I)

#: What a caption can say its bars are. Order matters only for the evidence
#: string; the verdict is AMBIGUOUS whenever more than one family matches.
DEFINITIONS = (
    ("SEM", re.compile(r"\bS\.?\s?E\.?\s?M\.?\b|standard\s+errors?\s+of\s+the\s+means?", re.I)),
    ("SE",  re.compile(r"\bS\.?E\.?s?\b(?!\s?M)|standard\s+errors?\b(?!\s+of\s+the\s+mean)", re.I)),
    ("SD",  re.compile(r"\bS\.?D\.?s?\b|standard\s+deviations?", re.I)),
    ("CI",  re.compile(r"\b9[05]\s*%\s*(?:CIs?|con(?:fi|\s)?dence)|con(?:fi|\s)?dence\s+intervals?|\bCIs?\b", re.I)),
    ("IQR", re.compile(r"\bIQRs?\b|inter-?quartile", re.I)),
)
PLUS_MINUS = re.compile(r"±|\+/-|\+/−|plus\s+or\s+minus", re.I)

DEF_AMBIGUOUS = "AMBIGUOUS"
DEF_PM_UNNAMED = "PM_UNNAMED"
DEF_UNSTATED = "UNSTATED"

#: A sentence in which the document says how it presents its numbers. This is
#: the Methods sentence a person would look for by hand; the module only finds
#: it and quotes it.
#: A character that does not end a sentence: anything but a period, or a
#: period with no space after it. "mean +/- .95 confidence intervals" has a
#: period in it that ends nothing, and reading it as the end of the sentence
#: left "mean +/-" - a statement that named no dispersion.
_IN = r"(?:\.(?!\s|$)|[^.])"
STATEMENT = re.compile(
    r"(?:"
    r"%(in)s{0,120}\b(?:data|values?|results|variables|measurements|numbers|"
    r"error\s+bars?|bars?|whiskers|points?|lines?)\b%(in)s{0,60}\b"
    r"(?:are|were|is|was|be)\b%(in)s{0,40}\b(?:presented|expressed|shown|given|"
    r"reported|displayed|represented|plotted|depicted|summari[sz]ed|indicated)"
    r"|"
    # the subject-less form a caption uses: "Displayed are means +/- 95% CI"
    r"\b(?:displayed|shown|presented|plotted|given)\s+(?:are|is)\s+(?:the\s+)?"
    r"(?:means?|medians?|averages?)"
    r")\b%(in)s{0,200}" % {"in": _IN},
    re.I)

FIELDS = ("Draft_ID", "Source_Document_ID", "Page", "Figure_Number",
          "Caption_Line", "Caption_Full", "Caption_Full_Status",
          "Caption_Full_Lines", "Errorbar_Definition", "Errorbar_Evidence",
          "Doc_Errorbar_Definition", "Doc_Errorbar_Evidence",
          "Doc_Errorbar_Page", "Source_SHA256_OK",
          "Caption_Next_Gap", "Caption_Next_Blocks")


#: Typographic ligatures as pdfminer hands them over. A PDF that sets
#: "confidence" with an fi ligature comes back as "conﬁdence" - 264 of them
#: in run2's captions - and one that dropped the glyph comes back as
#: "con dence". The CI pattern above tolerates the gap; this folds the glyph.
LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}


#: C0 control characters other than whitespace. pdfminer hands them over
#: from broken fonts, and Python's csv writer refuses a field that holds one
#: ("need to escape, but no escapechar set") - which stopped a whole run over
#: one caption on page 9 of one preprint.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _norm(text):
    text = _CONTROL.sub(" ", str(text or ""))
    for glyph, plain in LIGATURES.items():
        text = text.replace(glyph, plain)
    return " ".join(text.split())


def _bbox_key(text):
    """The intake's own bbox spelling, so equality is exact rather than close."""
    try:
        return CI._bbox_text([float(v) for v in str(text).split(",")])
    except (TypeError, ValueError):
        return ""


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_block(blocks, page, caption_bbox, caption_line):
    """(block, line_offset) for the block the intake took this caption from.

    The block is identified by page and by the bbox the intake wrote, in the
    intake's own spelling; the line by its normalised text. Returns
    (None, STATUS) when either is missing.
    """
    want = _bbox_key(caption_bbox)
    if not want:
        return None, STATUS_NO_BBOX
    line = _norm(caption_line)
    found = None
    for b in blocks:
        if b[0] != page:
            continue
        if CI._bbox_text(b[1:5]) != want:
            continue
        found = b
        for offset, raw in enumerate(b[5].splitlines()):
            if _norm(raw) == line:
                return (b, offset), STATUS_BLOCK
    return None, (STATUS_NO_LINE if found else STATUS_NO_BLOCK)


def opens_another_caption(line):
    """Whether a line starts a different figure's caption."""
    return bool(CI.CAPTION_RE.match(line) or CI.EXTENDED_RE.match(line)
                or CI.unreadable_label(line))


def caption_lines(block_text, offset):
    """The caption's lines: from `offset` to the end of the block, stopping
    before a line that opens another caption."""
    lines = block_text.splitlines()
    out = []
    for i, raw in enumerate(lines[offset:]):
        if i and opens_another_caption(raw):
            break
        if raw.strip():
            out.append(_norm(raw))
    return out


def label_only(line):
    """Whether a caption line is nothing but its label ("Figure 1", "Fig. 2.")."""
    m = CI.CAPTION_RE.match(line or "") or CI.EXTENDED_RE.match(line or "")
    if not m:
        return False
    return not m.group(2).strip(" .|:\u2013-\u2014")


def _overlap_share(a, b):
    """Horizontal overlap of two boxes as a share of the narrower one."""
    ox = min(a[3], b[3]) - max(a[1], b[1])
    w = min(a[3] - a[1], b[3] - b[1])
    return ox / w if w > 0 else 0.0


def ends_the_chain(first_line):
    """A block that is not caption text: another label, a table, a footer."""
    return bool(opens_another_caption(first_line) or TABLE_LABEL.match(first_line)
                or PAGE_FOOTER.match(first_line))


def blocks_below_label(blocks, label_block):
    """The body blocks of a label-only caption: [(gap, block)], possibly empty.

    Nearest block first. Each must share the column with the block before it,
    start within the gap the data allows, and not itself be a label, a table
    or a footer. Anything else ends the chain - including silence.
    """
    page = label_block[0]
    below = sorted((b for b in blocks if b[0] == page and b is not label_block
                    and b[2] >= label_block[4] - 0.5), key=lambda b: b[2])
    out, prev, limit = [], label_block, LABEL_FIRST_GAP_MAX
    for b in below:
        gap = b[2] - prev[4]
        if gap > limit:
            break
        if _overlap_share(prev, b) < LABEL_COLUMN_OVERLAP:
            continue                      # a footer or the other column
        first = (b[5].splitlines() or [""])[0]
        if ends_the_chain(first):
            break
        out.append((gap, b))
        if len(out) >= LABEL_MAX_BLOCKS:
            break
        prev, limit = b, LABEL_CONT_GAP_MAX
    return out


def join_lines(lines):
    """Lines into a paragraph. A line ending in a hyphen is a broken word,
    which the intake's own captions show ("stand-" / "ing")."""
    text = ""
    for line in lines:
        if not text:
            text = line
        elif text.endswith("-") and not text.endswith(" -"):
            text = text[:-1] + line
        else:
            text = text + " " + line
    return text


def errorbar_definition(text):
    """(code, evidence) for what a text says its dispersion is.

    Evidence is the matched words with a little context, so a person can see
    why without opening the paper. `SE` alone is kept apart from `SEM`: papers
    write "SE" for the standard error of the mean, but the module does not
    decide that for them.
    """
    text = _norm(text)
    hits = []
    for code, rx in DEFINITIONS:
        m = rx.search(text)
        if m:
            a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
            hits.append((code, text[a:b].strip()))
    # No SEM/SE reconciliation here: the SE pattern itself refuses "SEM",
    # "S.E.M." and "standard error of the mean", so the two families never
    # both match one statement. A branch that reconciled them survived every
    # scenario - it was decoration, and it is gone.
    codes = [c for c, _ in hits]
    if len(set(codes)) > 1:
        return DEF_AMBIGUOUS, " | ".join("%s: %s" % h for h in hits)
    if hits:
        return hits[0]
    m = PLUS_MINUS.search(text)
    if m:
        a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
        return DEF_PM_UNNAMED, text[a:b].strip()
    return DEF_UNSTATED, ""


def document_statement(blocks):
    """(code, sentence, page) for the first sentence in which the document
    says how its values are presented AND names a dispersion. ("", "", "")
    when there is none."""
    for page, _x0, _y0, _x1, _y1, text in blocks:
        flat = _norm(text)
        for m in STATEMENT.finditer(flat):
            sentence = m.group(0).strip()
            code, _ev = errorbar_definition(sentence)
            if code not in (DEF_UNSTATED, DEF_PM_UNNAMED):
                return code, sentence[:300], str(page)
    return "", "", ""


def resolve_source(pdf_root, name):
    """The file for a draft's bare `Source_File` name, searched one level of
    subdirectories deep, or None."""
    direct = os.path.join(pdf_root, name)
    if os.path.isfile(direct):
        return direct
    try:
        for sub in sorted(os.listdir(pdf_root)):
            p = os.path.join(pdf_root, sub, name)
            if os.path.isfile(p):
                return p
    except OSError:
        pass
    return None


def rows_for_document(doc_rows, blocks, failure=None, sha_ok=""):
    """Output rows for one document's draft rows.

    `blocks` is the page text, or None when the document could not be read -
    then `failure` is the status every row gets and nothing is reconstructed.
    `sha_ok` is "1" (verified), "0" (mismatch) or "" (not checked).
    """
    doc_def, doc_ev, doc_page = document_statement(blocks) if blocks else ("", "", "")
    out = []
    for r in doc_rows:
        base = {
            "Draft_ID": r["Draft_ID"], "Source_Document_ID": r["Source_Document_ID"],
            "Page": r.get("Page", ""), "Figure_Number": r.get("Figure_Number", ""),
            "Caption_Line": _norm(r.get("Caption_Text")),
            "Caption_Full": "", "Caption_Full_Status": "", "Caption_Full_Lines": "",
            "Errorbar_Definition": "", "Errorbar_Evidence": "",
            "Doc_Errorbar_Definition": doc_def, "Doc_Errorbar_Evidence": doc_ev,
            "Doc_Errorbar_Page": doc_page,
            "Source_SHA256_OK": sha_ok,
            "Caption_Next_Gap": "", "Caption_Next_Blocks": "",
        }
        if blocks is None:
            base["Caption_Full_Status"] = failure or STATUS_UNREADABLE
            out.append(base)
            continue
        try:
            page = int(str(r.get("Page") or "").strip())
        except ValueError:
            page = None
        hit, status = (None, STATUS_NO_BBOX) if page is None else find_block(
            blocks, page, r.get("Caption_BBox", ""), r.get("Caption_Text", ""))
        if hit is None:
            base["Caption_Full_Status"] = status
            out.append(base)
            continue
        block, offset = hit
        lines = caption_lines(block[5], offset)
        status = STATUS_BLOCK if len(lines) > 1 else STATUS_LINE_ONLY
        if status == STATUS_LINE_ONLY and label_only(lines[0]):
            tail = blocks_below_label(blocks, block)
            if tail:
                for _gap, b in tail:
                    lines += caption_lines(b[5], 0)
                status = STATUS_LABEL_NEXT
                base["Caption_Next_Gap"] = "%.1f" % tail[0][0]
                base["Caption_Next_Blocks"] = str(len(tail))
        full = join_lines(lines)
        base["Caption_Full"] = full
        base["Caption_Full_Lines"] = str(len(lines))
        base["Caption_Full_Status"] = status
        code, ev = errorbar_definition(full)
        base["Errorbar_Definition"], base["Errorbar_Evidence"] = code, ev
        out.append(base)
    return out


def build(run, pdf_root, out_path=None, log=print, only=None):
    draft = list(csv.DictReader(io.open(os.path.join(run, DRAFT), encoding="utf-8")))
    # THE BACKEND THE INTAKE USED, per document. Sixteen rows of run2 came
    # through poppler because pdfminer read too little of their PDF; the
    # blocks pdfminer gives for those pages are different blocks with
    # different boxes, and every caption of theirs was BLOCK_NOT_FOUND until
    # this read `Extraction_Method` instead of assuming.
    by_file = {}
    for r in draft:
        if only and r["Source_Document_ID"] not in only:
            continue
        key = ((r.get("Source_File") or "").strip(),
               (r.get("Extraction_Method") or "").strip() or None)
        by_file.setdefault(key, []).append(r)
    rows = []
    for (name, backend), doc_rows in sorted(by_file.items(), key=str):
        want = (doc_rows[0].get("Source_File_SHA256") or "").strip().lower()
        path = resolve_source(pdf_root, name) if name else None
        if path is None:
            rows += rows_for_document(doc_rows, None, STATUS_NO_SOURCE)
            log("  없음   %s" % name)
            continue
        if want and sha256_of(path) != want:
            # THE FILE IS NOT THE ONE THE DRAFT READ. Reading it anyway would
            # attach captions to rows whose pages may not be its pages.
            rows += rows_for_document(doc_rows, None, STATUS_BAD_SOURCE, sha_ok="0")
            log("  해시 불일치 %s" % name)
            continue
        sha_ok = "1" if want else ""
        try:
            blocks = CI.text_blocks(path, backend=backend)
        except Exception as exc:                                # noqa: BLE001
            rows += rows_for_document(doc_rows, None, STATUS_UNREADABLE, sha_ok=sha_ok)
            log("  읽지 못함 %s (%s)" % (name, type(exc).__name__))
            continue
        rows += rows_for_document(doc_rows, blocks, sha_ok=sha_ok)
    order = {r["Draft_ID"]: i for i, r in enumerate(draft)}
    rows.sort(key=lambda r: order.get(r["Draft_ID"], 1 << 30))
    out_path = out_path or os.path.join(run, OUT)
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, out_path)
    return rows, out_path


def summary(rows):
    import collections
    st = collections.Counter(r["Caption_Full_Status"] for r in rows)
    got = [r for r in rows if r["Caption_Full_Status"] in (STATUS_BLOCK, STATUS_LINE_ONLY, STATUS_LABEL_NEXT)]
    de = collections.Counter(r["Errorbar_Definition"] for r in got)
    docs = {r["Source_Document_ID"]: r["Doc_Errorbar_Definition"] for r in rows}
    dd = collections.Counter(v or "(없음)" for v in docs.values())
    return ("행 %d · 상태 %s\n캡션 오차 정의 %s\n문서 진술 (문서 %d) %s"
            % (len(rows), dict(st), dict(de), len(docs), dict(dd)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run")
    ap.add_argument("--pdf-root", required=True)
    ap.add_argument("--out")
    ap.add_argument("--only", nargs="*", help="Source_Document_ID들만")
    a = ap.parse_args(argv)
    rows, out = build(a.run, a.pdf_root, a.out, only=set(a.only or []) or None)
    print(summary(rows))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
