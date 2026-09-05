# -*- coding: utf-8 -*-
"""Scenarios for caption_fulltext.py - the whole caption, and what it says.

    python3 test_caption_fulltext.py

Every scenario here is one the module can fail: a fixture PDF is written by
hand, read back through the intake's own backend, and the draft rows are
produced the way `corpus_intake` produces them, so the contract under test is
the real one - the intake's bbox spelling, its line, its backend name.
"""
import csv
import hashlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus_intake as CI                                      # noqa: E402
import caption_fulltext as CF                                   # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_capfull_")


def minimal_pdf(path, pages):
    """A valid uncompressed PDF, one text line per entry: [(x, y, text)] per
    page, y from the BOTTOM as PDF has it. The same hand-written fixture as
    test_corpus_intake.py, copied rather than imported because importing that
    file runs its suite."""
    objects, kids = [], []
    first_page_object = 3
    for i, lines in enumerate(pages):
        page_obj = first_page_object + 2 * i
        content_obj = page_obj + 1
        kids.append("%d 0 R" % page_obj)
        stream = "BT /F1 11 Tf\n" + "".join(
            "1 0 0 1 %d %d Tm (%s) Tj\n" % (x, y, text.replace("(", r"\(")
                                            .replace(")", r"\)"))
            for x, y, text in lines) + "ET"
        objects.append((page_obj,
                        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                        "/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> "
                        ">> >>" % (content_obj, first_page_object + 2 * len(pages))))
        objects.append((content_obj,
                        "<< /Length %d >>\nstream\n%s\nendstream"
                        % (len(stream), stream)))
    font_obj = first_page_object + 2 * len(pages)
    objects = ([(1, "<< /Type /Catalog /Pages 2 0 R >>"),
                (2, "<< /Type /Pages /Kids [%s] /Count %d >>"
                 % (" ".join(kids), len(pages)))]
               + objects
               + [(font_obj, "<< /Type /Font /Subtype /Type1 "
                             "/BaseFont /Helvetica >>")])
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for number, body in sorted(objects):
        offsets[number] = len(out)
        out += ("%d 0 obj\n%s\nendobj\n" % (number, body)).encode("latin-1")
    start = len(out)
    highest = max(offsets)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (highest + 1)).encode()
    for number in range(1, highest + 1):
        out += ("%010d 00000 n \n" % offsets.get(number, 0)).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (highest + 1, start)).encode()
    with open(path, "wb") as fh:
        fh.write(bytes(out))
    return path


def column(x, top, *lines, step=12):
    """Lines stacked downward from `top` (bottom-origin y), one block."""
    return [(x, top - i * step, t) for i, t in enumerate(lines)]


# ---------------------------------------------------------------------------
print("what the words say the bars are")
for _text, _want in (
        ("Values are mean ± SD.", "SD"),
        ("Error bars show the standard deviation at each point.", "SD"),
        ("Data are mean ± SEM (n = 8).", "SEM"),
        ("Bars are means ± standard error of the mean.", "SEM"),
        ("Cardiopulmonary variables (mean ± SE) at baseline.", "SE"),
        ("Shaded areas are 95% CI.", "CI"),
        ("Boxes show the median and interquartile range.", "IQR"),
        ("Heart rate (mean ± 12 bpm) during tilt.", CF.DEF_PM_UNNAMED),
        ("Heart rate during tilt in eight subjects.", CF.DEF_UNSTATED),
        ("Panels A-C are mean ± SD; panel D is mean ± SEM.", CF.DEF_AMBIGUOUS),
        ("Word-final SD. Then nothing.", "SD"),
        # pdfminer's ligatures: the glyph kept, and the glyph dropped
        ("Displayed are means +/- 95% con\ufb01dence intervals.", "CI"),
        ("Data are presented as mean +/- .95 con dence intervals.", "CI"),
        ("Sedentary (SED) group vs. exercise group.", CF.DEF_UNSTATED)):
    _code, _ev = CF.errorbar_definition(_text)
    check("%r -> %s" % (_text[:48], _want), _code == _want, "%s %r" % (_code, _ev))
# REVERT: stop folding ligatures. "conﬁdence" then matches nothing, and a
# preprint whose every caption says "95% conﬁdence intervals" is UNSTATED.
# REVERT: leave control characters in. csv refuses the field and the run
# stops at the first caption that carries one.
check("a control character from a broken font does not survive into the text",
      CF._norm("Fig. 1.\x00 Heart\x1f rate") == "Fig. 1. Heart rate"
      and CF.join_lines(CF.caption_lines("Fig. 1.\x00 Heart", 0)) == "Fig. 1. Heart")
check("a ligature is folded in the evidence too",
      "confidence" in CF.errorbar_definition("means +/- 95% con\ufb01dence intervals")[1])
check("evidence quotes the words it matched",
      "standard deviation" in CF.errorbar_definition(
          "Error bars show the standard deviation at each point.")[1])
check("an unnamed ± is quoted too, so a person sees what was there",
      "±" in CF.errorbar_definition("Heart rate (mean ± 12 bpm).")[1])
check("silence has no evidence", CF.errorbar_definition("no bars")[1] == "")
# REVERT: drop the SEM/SE reconciliation. "standard error of the mean" matches
# the bare SE family through "standard error" and one statement becomes two.
check("'standard error of the mean' is one statement, not SE and SEM",
      CF.errorbar_definition("means ± standard error of the mean")[0] == "SEM")
check("ambiguity names both sides",
      "SD:" in CF.errorbar_definition("mean ± SD; panel D mean ± SEM")[1]
      and "SEM:" in CF.errorbar_definition("mean ± SD; panel D mean ± SEM")[1])

# ---------------------------------------------------------------------------
print("lines into a caption")
check("a hyphen-broken word is rejoined",
      CF.join_lines(["Relationships between stand-", "ing and supine"])
      == "Relationships between standing and supine")
check("a spaced dash is not a broken word",
      CF.join_lines(["tilt -", "supine"]) == "tilt - supine")
check("ordinary lines join with a space",
      CF.join_lines(["Fig. 1. Heart", "rate."]) == "Fig. 1. Heart rate.")
check("one line is itself", CF.join_lines(["only"]) == "only")
_block = "body text ends here\nFig. 1. Heart rate\nduring tilt.\nFig. 2. Blood\npressure."
check("the caption runs from its line to the end of the block ...",
      CF.caption_lines("Fig. 1. Heart rate\nduring tilt.\nmean ± SD.", 0)
      == ["Fig. 1. Heart rate", "during tilt.", "mean ± SD."])
# REVERT: stop honouring the next caption. Figure 1's caption then swallows
# Figure 2's whenever the two share a block, and reports Figure 2's bars.
check("... but stops before the next figure's caption",
      CF.caption_lines(_block, 1) == ["Fig. 1. Heart rate", "during tilt."])
check("an Extended Data caption also ends the previous one",
      CF.caption_lines("Fig. 1. A\nmore\nExtended Data Fig. 2 B\nx", 0) == ["Fig. 1. A", "more"])
check("a caption whose number is unreadable still ends the previous one",
      CF.caption_lines("Fig. 1. A\nmore\nFig. l. Mean changes in heart rate over time\nx", 0)
      == ["Fig. 1. A", "more"])
check("it starts at the offset, not at the block's first line",
      CF.caption_lines(_block, 1)[0].startswith("Fig. 1"))
check("blank lines inside the block are dropped",
      CF.caption_lines("Fig. 1. A\n\nB", 0) == ["Fig. 1. A", "B"])

# ---------------------------------------------------------------------------
print("the document's own statement")
_blocks = [
    (2, 0, 0, 100, 10, "Values are presented as mean ± error where appropriate."),
    (3, 0, 0, 100, 10, "Statistics. Data are presented as mean ± SEM unless noted. P < 0.05."),
    (4, 0, 0, 100, 10, "Results are expressed as mean ± SD."),
]
_code, _sent, _page = CF.document_statement(_blocks)
check("the first sentence that names a dispersion is the statement",
      (_code, _page) == ("SEM", "3"), (_code, _sent, _page))
# REVERT: accept PM_UNNAMED. Page 2's "mean ± error" then becomes the
# document's definition, and it names nothing.
check("a ± that names nothing is passed over", "error where" not in _sent, _sent)
check("the sentence is quoted", "mean ± SEM" in _sent, _sent)
check("no statement, no invention", CF.document_statement(
    [(1, 0, 0, 1, 1, "Fourteen subjects took part.")]) == ("", "", ""))
# REVERT: end a sentence at any period. ".95" then ends it, and the statement
# read is "mean +/-" - which names nothing, so the document has no statement.
check("a decimal point inside the sentence does not end it",
      CF.document_statement([(5, 0, 0, 1, 1,
          "Data are presented as mean +/- .95 confidence intervals. Next sentence.")])[0] == "CI")
check("the subject-less caption form counts: 'Displayed are means +/- 95% CI'",
      CF.document_statement([(9, 0, 0, 1, 1, "Displayed are means +/- 95% confidence intervals.")])
      == ("CI", "Displayed are means +/- 95% confidence intervals", "9"))
check("a subject-age sentence with ± is not a presentation statement",
      CF.document_statement([(1, 0, 0, 1, 1, "Subjects were aged 32 ± 4 years.")])
      == ("", "", ""))

# ---------------------------------------------------------------------------
print("through a PDF, the way the intake read it")
PDF = minimal_pdf(os.path.join(ROOT, "paper.pdf"), [
    # (The fixture font is StandardEncoding, where byte 0xB1 is an en dash,
    # so the fixture spells the sign "+/-"; the "±" scenarios are above.)
    # page 1: a body paragraph, then a 3-line caption block whose last line
    # names the bars, then a second caption in the SAME block (two figures
    # printed under one another), then a body block far below.
    column(72, 700, "Methods. Data are presented as mean +/- SEM unless",
           "otherwise stated. Fourteen subjects took part.")
    + column(72, 520, "Fig. 1. Relationships between stand-",
             "ing and supine heart rate in eight subjects.",
             "Error bars show the standard deviation.",
             "Fig. 2. Blood pressure during tilt.",
             "Values are mean +/- SEM.")
    + column(72, 300, "Body text continues here and says nothing about bars."),
    # page 2: a caption that is the last line of its block - WITH a body
    # block 17 pt below it, which the label-only rule must leave alone
    column(72, 700, "Some body text above.")
    + column(72, 500, "Fig. 3. Cardiac output during tilt.")
    + column(72, 472, "Body text resumes here and must not become the caption."),
    # page 3: the Research Square shape. "Figure 4" alone; its text 19 pt
    # below in two blocks 7 pt apart; then body text 21 pt further (beyond
    # the continuation gap); a footer off-column; then "Figure 5" and its text.
    column(72, 700, "Figure 4")
    + column(72, 670, "Cardiac output in eight subjects during tilt.",
             "Displayed are means +/- 95% confidence intervals.")
    + column(72, 640, "Asterisks mark p < .05 versus baseline.")
    + column(72, 608, "Methods continue here with unrelated body text.")
    + column(300, 560, "Page 3/4")
    + column(72, 500, "Figure 5")
    + column(72, 470, "Heart rate during the same tilt. Bars are SD.")
    + column(72, 420, "Figure 6")
    + column(72, 350, "Too far below to be Figure 6's text."),
    # page 4: three ways the chain must NOT continue. Figure 7's only
    # neighbour is body text in the OTHER column; Figure 8's text is followed
    # 9 pt later by a table caption; Figure 9's by the page footer.
    column(72, 700, "Figure 7")
    + column(330, 682, "Right-column body text at the same height.")
    + column(72, 600, "Figure 8")
    + column(72, 572, "Eight subjects. Bars are SEM.")
    + column(72, 552, "Table 1 Haemodynamic variables at rest.")
    + column(72, 480, "Figure 9")
    + column(72, 452, "Nine subjects during tilt.")
    + column(72, 432, "Page 4/4"),
])
SHA = hashlib.sha256(open(PDF, "rb").read()).hexdigest()
# THE BACKEND THIS MACHINE'S INTAKE WOULD USE - pdfminer where it is installed,
# poppler otherwise - so the suite runs on the Mac (no pdfminer) and in the VM.
# The core CI profile installs neither; there the text-only scenarios above
# are the suite, and this says so rather than crashing.
try:
    BACKEND = CI._default_backend()
except CI.BackendUnavailable:
    shutil.rmtree(ROOT, ignore_errors=True)
    print("  SKIP the PDF adapter: no text backend is installed here "
          "(pdfminer.six or poppler-utils); %d text-only scenarios ran" % PASSED[0])
    print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
    raise SystemExit(1 if FAILURES else 0)
OTHER = {"PDFMINER_TEXT_BLOCKS": "POPPLER_BBOX_LAYOUT",
         "POPPLER_BBOX_LAYOUT": "PDFMINER_TEXT_BLOCKS"}[BACKEND]
BLOCKS = CI.text_blocks(PDF, backend=BACKEND)
CANDS = CI.caption_candidates(BLOCKS)
check("the fixture yields nine captions the intake's way (%d)" % len(CANDS),
      [c["number"] for c in CANDS] == [str(i) for i in range(1, 10)],
      [c["number"] for c in CANDS])
if len(CANDS) != 9:
    print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
    raise SystemExit(1)

RUN = os.path.join(ROOT, "run")
os.makedirs(RUN)
PDFROOT = os.path.join(ROOT, "pdfs", "sub")
os.makedirs(PDFROOT)
shutil.copy(PDF, os.path.join(PDFROOT, "paper.pdf"))


def draft_row(cand, did, sha=SHA, method=BACKEND, **over):
    row = {"Draft_ID": did, "Source_Document_ID": "DOC", "Source_File": "paper.pdf",
           "Source_File_SHA256": sha, "Page": str(cand["page"]),
           "Figure_Number": "FIG" + cand["number"], "Caption_Text": cand["text"],
           "Caption_BBox": CI._bbox_text(cand["bbox"]), "Extraction_Method": method}
    row.update(over)
    return row


def write_draft(rows):
    cols = ["Draft_ID", "Source_Document_ID", "Source_File", "Source_File_SHA256",
            "Page", "Figure_Number", "Caption_Text", "Caption_BBox", "Extraction_Method"]
    with io.open(os.path.join(RUN, CF.DRAFT), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


write_draft([draft_row(CANDS[i], "DOC_D%03d" % (i + 1)) for i in range(9)])
ROWS, OUTP = CF.build(RUN, os.path.join(ROOT, "pdfs"), log=lambda *_a: None)
BY = {r["Draft_ID"]: r for r in ROWS}
check("the output is written where it says (%s)" % os.path.basename(OUTP), os.path.isfile(OUTP))
check("every column the module promises is in the file",
      list(csv.DictReader(io.open(OUTP, encoding="utf-8")).fieldnames) == list(CF.FIELDS))
check("the source file is found one directory down",
      BY["DOC_D001"]["Caption_Full_Status"] not in (CF.STATUS_NO_SOURCE,),
      BY["DOC_D001"]["Caption_Full_Status"])
check("the hash is checked and recorded", BY["DOC_D001"]["Source_SHA256_OK"] == "1")
check("figure 1's caption is its whole block from its line down",
      BY["DOC_D001"]["Caption_Full_Status"] == CF.STATUS_BLOCK
      and BY["DOC_D001"]["Caption_Full"].startswith("Fig. 1. Relationships between standing")
      and BY["DOC_D001"]["Caption_Full"].endswith("Error bars show the standard deviation."),
      BY["DOC_D001"]["Caption_Full"])
check("... and it stops before figure 2", "Fig. 2" not in BY["DOC_D001"]["Caption_Full"])
check("... in three lines", BY["DOC_D001"]["Caption_Full_Lines"] == "3")
check("so figure 1 now says SD where its first line said nothing",
      BY["DOC_D001"]["Errorbar_Definition"] == "SD"
      and CF.errorbar_definition(BY["DOC_D001"]["Caption_Line"])[0] == CF.DEF_UNSTATED)
check("figure 2, opening mid-block, gets its own two lines",
      BY["DOC_D002"]["Caption_Full"] == "Fig. 2. Blood pressure during tilt. Values are mean +/- SEM."
      and BY["DOC_D002"]["Errorbar_Definition"] == "SEM", BY["DOC_D002"]["Caption_Full"])
# REVERT: report LINE_ONLY as BLOCK. A caption the module could not extend then
# looks extended, and 287 short captions stop being a number anyone sees.
check("a caption that is its block's last line says so (LINE_ONLY)",
      BY["DOC_D003"]["Caption_Full_Status"] == CF.STATUS_LINE_ONLY
      and BY["DOC_D003"]["Caption_Full"] == "Fig. 3. Cardiac output during tilt.",
      (BY["DOC_D003"]["Caption_Full_Status"], BY["DOC_D003"]["Caption_Full"]))
# ---- the label-only rule
_f4 = BY["DOC_D004"]
# REVERT: never read below the block. "Figure 4" is then the whole caption of
# a figure whose text says "95% confidence intervals", and it counts as UNSTATED.
check("a label-only line takes the blocks directly below (LABEL_NEXT_BLOCKS)",
      _f4["Caption_Full_Status"] == CF.STATUS_LABEL_NEXT, _f4["Caption_Full_Status"])
check("... the two body blocks 7 pt apart are one caption",
      _f4["Caption_Full"] == "Figure 4 Cardiac output in eight subjects during tilt. "
      "Displayed are means +/- 95% confidence intervals. Asterisks mark p < .05 versus baseline.",
      _f4["Caption_Full"])
# REVERT: drop the continuation gap. Body text 21 pt below the caption is
# then swallowed into it, and its words become the figure's.
check("... but body text 21 pt further down is not (continuation gap)",
      "Methods continue" not in _f4["Caption_Full"])
check("... and the figure now names its dispersion", _f4["Errorbar_Definition"] == "CI")
check("the gap and block count are written down so the join is visible",
      _f4["Caption_Next_Gap"] and float(_f4["Caption_Next_Gap"]) < CF.LABEL_FIRST_GAP_MAX
      and _f4["Caption_Next_Blocks"] == "2", (_f4["Caption_Next_Gap"], _f4["Caption_Next_Blocks"]))
# REVERT: stop honouring the next label. Figure 5's text lands in Figure 4's
# caption on any page that prints two label-only figures.
check("figure 5's label ends figure 4's chain; figure 5 gets its own text",
      "Heart rate" not in _f4["Caption_Full"]
      and BY["DOC_D005"]["Caption_Full"].endswith("Bars are SD.")
      and BY["DOC_D005"]["Errorbar_Definition"] == "SD", BY["DOC_D005"]["Caption_Full"])
# REVERT: widen the first gap. The block 50 pt under "Figure 6" is then its
# caption, and nothing says it is not.
check("a label whose nearest text is too far below stays LINE_ONLY",
      BY["DOC_D006"]["Caption_Full_Status"] == CF.STATUS_LINE_ONLY
      and BY["DOC_D006"]["Caption_Full"] == "Figure 6", BY["DOC_D006"])
# REVERT: drop the column test. The other column's body text, 18 pt below
# the label at the same height, becomes figure 7's caption.
check("text in the other column is not the caption (LINE_ONLY)",
      BY["DOC_D007"]["Caption_Full_Status"] == CF.STATUS_LINE_ONLY
      and "Right-column" not in BY["DOC_D007"]["Caption_Full"], BY["DOC_D007"])
# REVERT: stop ending the chain at a table caption or a footer. Nine points
# under figure 8's text is "Table 1 ..."; under figure 9's, "Page 4/4".
check("a table caption 9 pt below ends the chain",
      BY["DOC_D008"]["Caption_Full"] == "Figure 8 Eight subjects. Bars are SEM."
      and BY["DOC_D008"]["Caption_Next_Blocks"] == "1", BY["DOC_D008"]["Caption_Full"])
check("a page footer 9 pt below ends the chain",
      BY["DOC_D009"]["Caption_Full"] == "Figure 9 Nine subjects during tilt."
      and "Page" not in BY["DOC_D009"]["Caption_Full"], BY["DOC_D009"]["Caption_Full"])
# REVERT: extend every LINE_ONLY caption. Figure 3 has a body already, and the
# body text 17 pt below it would be read as its second sentence.
check("a one-line caption WITH a body is not extended, whatever sits below",
      BY["DOC_D003"]["Caption_Full_Status"] == CF.STATUS_LINE_ONLY
      and "resumes" not in BY["DOC_D003"]["Caption_Full"], BY["DOC_D003"]["Caption_Full"])
check("label_only: 'Figure 1' / 'Fig. 2.' / 'FIGURE 3 |' are labels; a body is not",
      CF.label_only("Figure 1") and CF.label_only("Fig. 2.") and CF.label_only("FIGURE 3 |")
      and not CF.label_only("Fig. 5; Fig. 6).") and not CF.label_only("Fig. 1 Heart rate")
      and not CF.label_only("Body text"))
check("a footer line is recognised in both spellings",
      CF.ends_the_chain("Page 9/12") and CF.ends_the_chain("Page 9 of 12")
      and CF.ends_the_chain("Table 2 Haemodynamics") and not CF.ends_the_chain("Cardiac output"))

check("the document's Methods sentence is found once and put on every row",
      all(r["Doc_Errorbar_Definition"] == "SEM" and r["Doc_Errorbar_Page"] == "1"
          for r in ROWS), [(r["Doc_Errorbar_Definition"], r["Doc_Errorbar_Page"]) for r in ROWS])
check("the quoted sentence is the Methods one, not a caption",
      "Methods" in ROWS[0]["Doc_Errorbar_Evidence"] or "Data are presented" in ROWS[0]["Doc_Errorbar_Evidence"],
      ROWS[0]["Doc_Errorbar_Evidence"])
check("the summary counts what the file holds",
      "BLOCK" in CF.summary(ROWS) and "SEM" in CF.summary(ROWS))

# ---------------------------------------------------------------------------
print("what it refuses")
_wrong_sha = "0" * 64
_gone_bbox = "1.0,2.0,3.0,4.0"
write_draft([
    draft_row(CANDS[0], "DOC_D001", sha=_wrong_sha),
])
_r = {r["Draft_ID"]: r for r in CF.build(RUN, os.path.join(ROOT, "pdfs"),
                                          log=lambda *_a: None)[0]}
# REVERT: skip the hash. A replaced PDF is then read as if it were the one
# the draft came from, and captions land on rows whose pages are not its pages.
check("a source whose hash is not the draft's is not read",
      _r["DOC_D001"]["Caption_Full_Status"] == CF.STATUS_BAD_SOURCE
      and _r["DOC_D001"]["Caption_Full"] == "" and _r["DOC_D001"]["Source_SHA256_OK"] == "0",
      _r["DOC_D001"])
write_draft([
    draft_row(CANDS[0], "DOC_D001", Caption_BBox=_gone_bbox),
    draft_row(CANDS[0], "DOC_D002", Caption_Text="Fig. 1. Not the line that is there."),
    draft_row(CANDS[0], "DOC_D003", Caption_BBox=""),
    draft_row(CANDS[0], "DOC_D004", Source_File="missing.pdf"),
    draft_row(CANDS[0], "DOC_D005", Page="9"),
])
_r = {r["Draft_ID"]: r for r in CF.build(RUN, os.path.join(ROOT, "pdfs"),
                                          log=lambda *_a: None)[0]}
check("a block that is not on the page is BLOCK_NOT_FOUND, with no caption",
      _r["DOC_D001"]["Caption_Full_Status"] == CF.STATUS_NO_BLOCK and not _r["DOC_D001"]["Caption_Full"])
check("a line that is not in its block is LINE_NOT_IN_BLOCK",
      _r["DOC_D002"]["Caption_Full_Status"] == CF.STATUS_NO_LINE and not _r["DOC_D002"]["Caption_Full"])
check("a row the intake never placed is NO_CAPTION_BBOX",
      _r["DOC_D003"]["Caption_Full_Status"] == CF.STATUS_NO_BBOX)
check("a file that is not under --pdf-root is SOURCE_MISSING",
      _r["DOC_D004"]["Caption_Full_Status"] == CF.STATUS_NO_SOURCE)
check("a page the PDF does not have is BLOCK_NOT_FOUND, not a crash",
      _r["DOC_D005"]["Caption_Full_Status"] == CF.STATUS_NO_BLOCK)
check("refused rows still carry the document's statement (it was read)",
      _r["DOC_D001"]["Doc_Errorbar_Definition"] == "SEM")
check("... except when the document itself was refused",
      _r["DOC_D004"]["Doc_Errorbar_Definition"] == "")

# the bbox must match in the intake's spelling, not merely overlap
_near = CANDS[0]["bbox"]
_near = (_near[0] + 0.3, _near[1], _near[2], _near[3])
write_draft([draft_row(CANDS[0], "DOC_D001", Caption_BBox=CI._bbox_text(_near))])
_r = CF.build(RUN, os.path.join(ROOT, "pdfs"), log=lambda *_a: None)[0][0]
# REVERT: match blocks by page and line only. Then a running header that
# repeats the caption line on every page becomes the caption's block.
check("a bbox 0.3pt off is a different block", _r["Caption_Full_Status"] == CF.STATUS_NO_BLOCK,
      _r["Caption_Full_Status"])

# ---------------------------------------------------------------------------
print("the backend the intake used")


def _other_available():
    try:
        CI.text_blocks(PDF, backend=OTHER)
        return True
    except Exception:                                           # noqa: BLE001
        return False


if _other_available():
    _pb = CI.text_blocks(PDF, backend=OTHER)
    _pc = [c for c in CI.caption_candidates(_pb) if c["number"] == "1"]
    check("%s also finds figure 1 in the fixture" % OTHER, bool(_pc))
    if _pc:
        write_draft([draft_row(_pc[0], "DOC_D001", method=OTHER)])
        _r = CF.build(RUN, os.path.join(ROOT, "pdfs"), log=lambda *_a: None)[0][0]
        # REVERT: always read with the default backend. Sixteen rows of run2
        # were poppler's, and every one of them was BLOCK_NOT_FOUND.
        check("a row the intake read with %s is re-read with it" % OTHER,
              _r["Caption_Full_Status"] in (CF.STATUS_BLOCK, CF.STATUS_LINE_ONLY)
              and _r["Caption_Full"].startswith("Fig. 1."),
              (_r["Caption_Full_Status"], _r["Caption_Full"][:40]))
else:
    print("  skip only one text backend is installed here; the cross-backend "
          "scenario needs both")

# ---------------------------------------------------------------------------
print("order and grouping")
_pdf2 = minimal_pdf(os.path.join(PDFROOT, "other.pdf"),
                    [column(72, 500, "Fig. 1. Other paper's figure.", "Bars are SD.")])
_sha2 = hashlib.sha256(open(_pdf2, "rb").read()).hexdigest()
_c2 = CI.caption_candidates(CI.text_blocks(_pdf2, backend=BACKEND))[0]
write_draft([
    draft_row(CANDS[0], "DOC_D001"),
    dict(draft_row(_c2, "OTHER_D001", sha=_sha2), Source_Document_ID="OTHER", Source_File="other.pdf"),
    draft_row(CANDS[2], "DOC_D003"),
])
_rows = CF.build(RUN, os.path.join(ROOT, "pdfs"), log=lambda *_a: None)[0]
# REVERT: emit rows in file order. The output then no longer lines up with
# the draft row for row, and a person diffing the two sees a shuffle.
check("rows come out in the draft's order, not grouped by file",
      [r["Draft_ID"] for r in _rows] == ["DOC_D001", "OTHER_D001", "DOC_D003"],
      [r["Draft_ID"] for r in _rows])
check("each document gets its own statement",
      {r["Source_Document_ID"]: r["Doc_Errorbar_Definition"] for r in _rows} == {"DOC": "SEM", "OTHER": ""},
      {r["Source_Document_ID"]: r["Doc_Errorbar_Definition"] for r in _rows})
check("--only narrows to the documents named",
      [r["Draft_ID"] for r in CF.build(RUN, os.path.join(ROOT, "pdfs"), log=lambda *_a: None,
                                        only={"OTHER"})[0]] == ["OTHER_D001"])

# ---------------------------------------------------------------------------
shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
