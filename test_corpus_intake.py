"""What the intake layer may propose, and what it may never assert.

    python3 test_corpus_intake.py     # exit 0 = all scenarios pass

The corpus is 116 publications and roughly six hundred figures, and the source
inventory needs a row per figure with a human's panel count on it. This module
is the machine's half of that: it proposes rows and marks every one PENDING.

So the scenarios here are mostly about the boundary rather than the extraction.
A caption regex that misses one caption costs a person one row on a contact
sheet. A draft that can promote itself to an inventory costs the project the one
claim the inventory exists to carry - that somebody opened the figure and
counted what is in it.

The PDF fixture is built here, byte by byte, rather than shipped: a two-page
uncompressed PDF with a caption on each page. It needs no library to make and
no network to fetch, and it means the backend adapter is exercised for real
wherever a backend exists. Where none does, those scenarios SKIP loudly and the
logic scenarios still run - the same shape as the private-raster forward test.
"""
import contextlib
import csv
import io
import os
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus_intake as CI                                      # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_intake_")


def minimal_pdf(path, pages):
    """A valid uncompressed PDF with one text line per entry of `pages`.

    Written by hand so the fixture has no build dependency and no binary in the
    repository. Offsets are computed, not guessed: a broken xref would make
    every backend scenario a skip, which is the one way this fixture could lie.
    """
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


# ---------------------------------------------------------------------------
print("a caption is a line that opens with a figure label, and little else")
# REVERT: loosen CAPTION_RE to match "Fig" anywhere in a block. Every body
# sentence mentioning a figure becomes a row somebody has to reject.
for _text, _want in (
        ("Figure 4 Average data of mean arterial pressure (MAP) spectral "
         "powers in standing and supine cosmonauts.", "4"),
        ("Fig. 2 Heart rate response to standing.", "2"),
        ("FIGURE 10 Something with two digits.", "10"),
        ("Fig 3A Panel A of the third figure.", "3A"),
        ("As Figure 4 shows, the response was larger upon standing.", None),
        ("Figures 3 and 4 are discussed together.", None),
        ("Table 2 Pre- and post-flight haemodynamic data.", None)):
    _hit = CI.CAPTION_RE.match(_text)
    check("%r -> %s" % (_text[:44], _want or "not a caption"),
          (_hit.group(1) if _hit else None) == _want,
          "%s" % (_hit.group(1) if _hit else None))
check("'Figures 3 and 4' is refused because the plural is not a label",
      not CI.CAPTION_RE.match("Figures 3 and 4 are discussed together."))
# REVERT: drop the CJK labels. `2016-2-11.pdf` - a China Astronaut Research and
# Training Center review with one figure - then reads 357 text blocks and
# proposes nothing, which on a corpus walk is indistinguishable from an article
# that has no figures.
_CJK = CI.CAPTION_RE.match("图   1. 失重/模拟失重导致心肌萎缩\n"
                           "Fig. 1. Weightlessness leads to cardiac atrophy")
check("a caption labelled 图 is a caption",
      _CJK is not None and _CJK.group(1) == "1",
      "%s" % (_CJK and _CJK.group(1)))
check("and so is the traditional 圖",
      (CI.CAPTION_RE.match("圖 2 心率反應") or [None, None])[1] == "2")
check("but the label still has to open the block",
      not CI.CAPTION_RE.match("如图 1 所示，心肌萎缩"))

print()
print("the confidence is an ordering with a reason attached, not a probability")
# REVERT: delete any one penalty in `_confidence`. Nothing refuses a row for
# scoring badly, so the only cost is silent: the row a person most needed to
# look at stops sorting to the top of the contact sheet and stops carrying the
# sentence that says what is doubtful about it.
_PAGE = [
    (2, 70.0, 100.0, 500.0, 140.0, "Body text printed above the caption."),
    (2, 70.0, 600.0, 500.0, 660.0,
     "Figure 1 Mean arterial pressure before and after spaceflight."),
]
_FULL = CI.caption_candidates(_PAGE)[0]
_score, _why = CI._confidence(_FULL, 1, _PAGE)
check("a caption with a long body, printed once, under something, scores 1.00",
      (_score, _why) == (1.0, ""), "%s %r" % (_score, _why))

_SHORT = [(2, 70.0, 100.0, 500.0, 140.0, "Body text printed above."),
          (2, 70.0, 600.0, 200.0, 660.0, "Figure 1 Pulse.")]
_short_c = CI.caption_candidates(_SHORT)[0]
_score, _why = CI._confidence(_short_c, 1, _SHORT)
check("a body too short to be a caption costs 0.4",
      _score == 0.6, "%s" % _score)
check("and the reason counts the characters, so a person can judge it",
      "%d characters" % len(_short_c["body"]) in _why, _why)

_score, _why = CI._confidence(_FULL, 3, _PAGE)
check("three blocks opening with the same label cost 0.3",
      _score == 0.7, "%s" % _score)
check("and the reason says how many there were",
      "3 blocks" in _why, _why)

# REVERT: put the same-label count back on the page. Publication 127 prints
# "Figure 7 shows the relationship..." on page 6 and Figure 7's real caption on
# page 9, and per page neither of them knows the other exists.
_SPREAD = [(6, 70.0, 40.0, 500.0, 90.0, "Text printed above, on page six."),
           (9, 70.0, 40.0, 500.0, 90.0, "Text printed above, on page nine."),
           (6, 70.0, 100.0, 500.0, 160.0,
            "Figure 7 shows the relationship between mean RR intervals and "
            "spectral powers in the standing posture."),
           (9, 70.0, 600.0, 500.0, 660.0,
            "Figure 7 Relationship between mean RR intervals (RRI) and "
            "spectral powers before and after spaceflight.")]
_spread = CI.caption_candidates(_SPREAD)
check("a label printed on two different pages is still one label twice",
      len({c["number"] for c in _spread}) == 1 and len(_spread) == 2)

# REVERT: drop the lower-case penalty. Every "Figure 5 shows ..." sentence in
# the corpus then arrives at full confidence, indistinguishable from the
# caption it refers to, and 127 proposes nine figures for an article with seven.
_score, _why = CI._confidence(_spread[0], 2, _SPREAD)
check("a label followed by a lower-case word costs 0.3 more",
      _score == 0.4, "%s" % _score)
check("and the reason quotes the word, because that is the whole difference",
      "'shows'" in _why, _why)
check("the real caption on the other page keeps the duplicate penalty only",
      CI._confidence(_spread[1], 2, _SPREAD)[0] == 0.7,
      "%s" % (CI._confidence(_spread[1], 2, _SPREAD)[0],))

_ALONE = [(2, 70.0, 600.0, 500.0, 660.0, _PAGE[1][5])]
_score, _why = CI._confidence(CI.caption_candidates(_ALONE)[0], 1, _ALONE)
check("a caption with nothing printed above it costs 0.1",
      _score == 0.9, "%s" % _score)
_worst_blocks = [(2, 70.0, 600.0, 200.0, 660.0, "Figure 1 shows")]
_worst, _worst_why = CI._confidence(
    CI.caption_candidates(_worst_blocks)[0], 2, _worst_blocks)
check("and the penalties add up rather than replacing each other",
      _worst == 0.0, "%s" % _worst)
check("so the worst row arrives carrying all four reasons",
      _worst_why.count(";") == 3, _worst_why)


def _sheet_row(draft_id, score, reason, caption="Figure 1 A caption."):
    row = {column: "" for column in CI.DRAFT_COLUMNS}
    row.update(Draft_ID=draft_id, Page=2, Figure_Number="FIG1",
               Caption_Text=caption, Confidence="%.2f" % score,
               Confidence_Reason=reason, Human_Verification_Status="PENDING")
    return row


_DOUBTFUL = _sheet_row("SD9_D002", 0.3, "the caption text is 6 characters")
_SURE = _sheet_row("SD9_D001", 1.0, "")
_sheet_html = open(CI.contact_sheet(os.path.join(ROOT, "sheet.html"),
                                    [_SURE, _DOUBTFUL]), encoding="utf-8").read()
check("the contact sheet prints the reason, not only the score",
      "the caption text is 6 characters" in _sheet_html)
check("the doubtful row is listed before the confident one",
      _sheet_html.index("SD9_D002") < _sheet_html.index("SD9_D001"))
check("and is the one marked for attention",
      _sheet_html.count("tr class='low'") == 1,
      "%d" % _sheet_html.count("tr class='low'"))

print()
print("what the machine may write is PENDING, and only PENDING")
_BLOCKS = [
    (6, 70.0, 100.0, 300.0, 140.0, "Body text about the experiment."),
    # REVERT: let `caption_candidates` look for the label anywhere in a block
    # instead of at its start. This paragraph then becomes figure 5, and the
    # article grows a figure nobody printed.
    (6, 70.0, 150.0, 300.0, 200.0,
     "Supine values fell after flight. As Figure 5 shows, the response was "
     "larger upon standing than it was at rest."),
    (6, 70.0, 620.0, 300.0, 700.0,
     "Figure 3 Average data of RR intervals (RRI) spectral powers in standing "
     "and supine cosmonauts before and after spaceflight."),
    (6, 320.0, 620.0, 560.0, 700.0,
     "Figure 4 Average data of mean arterial pressure (MAP) spectral powers "
     "in standing and supine cosmonauts before and after spaceflight."),
]
_candidates = CI.caption_candidates(_BLOCKS)
check("two captions on one page are two candidates",
      [c["number"] for c in _candidates] == ["3", "4"],
      "%s" % [c["number"] for c in _candidates])
check("and the body text is not one",
      all("Body text" not in c["text"] for c in _candidates))
_box = CI.figure_bbox(_candidates[0], _BLOCKS)
check("the figure box is the gap above the caption, not the caption",
      _box is not None and _box[3] == 620.0 and _box[1] == 200.0,
      "%s" % (_box,))
check("and its top edge is the NEAREST block above, not the highest one",
      _box[1] == max(b[4] for b in _BLOCKS if b[4] <= _candidates[0]["bbox"][1]),
      "%s" % (_box,))
# REVERT: take the nearest block above by y alone. This literature is
# two-column, so the block directly above a left-column caption is a paragraph
# in the RIGHT column at almost the same height, and the figure region
# collapses to a strip of body text. Across fifteen corpus PDFs the median crop
# went from 127 px tall to 433.
_TWOCOL = [
    (4, 55.0, 100.0, 290.0, 130.0, "Left column text, well above the figure."),
    (4, 310.0, 100.0, 545.0, 130.0, "Right column text at the same height."),
    # The right column keeps talking all the way down past the left figure.
    (4, 310.0, 140.0, 545.0, 600.0, "Right column body text continuing down "
                                    "the page past where the figure is drawn."),
    (4, 55.0, 620.0, 290.0, 660.0,
     "Figure 2 Average heart rate response to standing before and after "
     "spaceflight in five cosmonauts."),
]
_tc = CI.figure_bbox(CI.caption_candidates(_TWOCOL)[0], _TWOCOL)
check("the figure region stops at the block above IN THE SAME COLUMN",
      _tc is not None and _tc[1] == 130.0, "%s" % (_tc,))
check("and does not reach across the gutter for its width",
      _tc is not None and _tc[2] <= 290.0, "%s" % (_tc,))
check("so the region is the height of a figure, not of a text strip",
      _tc is not None and (_tc[3] - _tc[1]) > 400, "%s" % (_tc,))
check("and a caption with nothing above it gets no box",
      CI.figure_bbox({"page": 6, "bbox": (70.0, 0.0, 300.0, 40.0)},
                     [(6, 70.0, 0.0, 300.0, 40.0, "x")]) is None)


def _rows(path="", pages=None, document="SD1"):
    pdf = path or minimal_pdf(os.path.join(ROOT, "two.pdf"),
                              pages or [
                                  [(72, 700, "Body text about the design."),
                                   (72, 300, "Figure 1 Mean arterial pressure "
                                             "before and after spaceflight in "
                                             "five cosmonauts.")],
                                  [(72, 500, "Figure 2 Heart rate response to "
                                             "standing, slow and normal paced "
                                             "breathing protocols.")]])
    return pdf, CI.draft_rows(pdf, document)


_BACKEND, _NO_BACKEND = "", ""
try:
    _BACKEND = CI._default_backend()
except CI.BackendUnavailable as _exc:
    _NO_BACKEND = str(_exc)
    print("  SKIP the PDF adapter: %s" % _exc)

if _BACKEND:
    _pdf, _draft = _rows()
    check("a two-page PDF with two captions drafts two rows",
          len(_draft) == 2, "%d" % len(_draft))
    check("each row says which page it came from",
          [r["Page"] for r in _draft] == [1, 2], "%s" % [r["Page"] for r in _draft])
    check("and which backend read it",
          {r["Extraction_Method"] for r in _draft} == {_BACKEND},
          "%s" % {r["Extraction_Method"] for r in _draft})
    check("and the file it came from, by hash",
          {r["Source_File_SHA256"] for r in _draft} == {CI.file_sha256(_pdf)})
    # REVERT: let `draft_rows` copy a status in from anywhere. The machine can
    # then write the one word the whole layer exists to withhold.
    check("EVERY row is PENDING, with nobody named beside it",
          all(r["Human_Verification_Status"] == "PENDING"
              and not r["Verified_By"] and not r["Verified_At"]
              and not r["Observed_Panel_Count"] for r in _draft),
          "%s" % [r["Human_Verification_Status"] for r in _draft])
    # REVERT: count the same label per page in `draft_rows`. This is the exact
    # shape publication 127 prints - the sentence on one page, the caption on
    # another - and per page both come out at 1.00, which is the score that
    # says "nothing to look at here".
    _spread_pdf, _spread_draft = _rows(
        path=minimal_pdf(os.path.join(ROOT, "spread.pdf"), [
            [(72, 700, "Figure 2 shows the heart rate response to standing "
                       "before and after spaceflight.")],
            [(72, 700, "Body text about the protocol."),
             (72, 300, "Figure 2 Heart rate response to standing, slow and "
                       "normal paced breathing protocols.")]]),
        document="SD2")
    _by_page = {r["Page"]: r for r in _spread_draft}
    check("a label used on page 1 and page 2 is counted once for the document",
          set(_by_page) == {1, 2}
          and all("2 blocks" in r["Confidence_Reason"]
                  for r in _spread_draft),
          "%s" % [r["Confidence_Reason"] for r in _spread_draft])
    check("so the sentence scores below the caption it refers to",
          float(_by_page[1]["Confidence"]) < float(_by_page[2]["Confidence"]),
          "%s" % [(r["Page"], r["Confidence"]) for r in _spread_draft])
    check("and lands under the threshold that puts it in front of a person",
          float(_by_page[1]["Confidence"]) < CI.LOW_CONFIDENCE,
          _by_page[1]["Confidence"])
    # REVERT: let a document that proposed nothing pass without a word. It
    # leaves no row on the contact sheet, so on a walk of ninety-seven articles
    # it is indistinguishable from an article with no figures - which is how a
    # Chinese-language review with one figure went missing.
    _quiet = minimal_pdf(os.path.join(ROOT, "quiet.pdf"),
                         [[(72, 700, "A page of prose with no caption on it.")]])
    _out = io.StringIO()
    _qdir = os.path.join(ROOT, "quiet")
    with contextlib.redirect_stdout(_out):
        CI.main([_quiet, "--out", _qdir])
    _qledger = list(csv.DictReader(
        open(os.path.join(_qdir, "intake_document_status.csv"), encoding="utf-8")))
    check("a document that read fine and proposed nothing gets a ledger row",
          len(_qledger) == 1
          and _qledger[0]["Text_Backend_Status"] == "ZERO_CAPTION_CANDIDATES",
          "%s" % _qledger)
    check("and the row says what to do about it",
          _qledger[0]["Required_Action"] == "CHECK_CAPTION_STYLE",
          _qledger[0]["Required_Action"])
    check("and the walk names it on the way past",
          os.path.basename(_quiet) in _out.getvalue(), _out.getvalue()[-200:])
    check("a draft the machine just wrote has no problems",
          not CI.draft_problems(_draft), "%s" % CI.draft_problems(_draft))
    _written = CI.write_draft(os.path.join(ROOT, "draft.csv"), _draft)
    _back = list(csv.DictReader(open(_written, encoding="utf-8")))
    check("and it round-trips through the CSV unchanged",
          [r["Draft_ID"] for r in _back] == [r["Draft_ID"] for r in _draft]
          and not CI.draft_problems(_back), "%s" % CI.draft_problems(_back))
    _sheet = CI.contact_sheet(os.path.join(ROOT, "index.html"), _draft)
    _html = open(_sheet, encoding="utf-8").read()
    check("the contact sheet says every row is a proposal",
          "proposal" in _html and "CONFIRMED" in _html)
    check("and lists every drafted row",
          all(r["Draft_ID"] in _html for r in _draft))
else:
    _draft = [dict(Draft_ID="SD1_D001", Source_Document_ID="SD1",
                   Source_File="two.pdf", Source_File_SHA256="0" * 64,
                   Page=1, Page_Raster="", Page_Raster_SHA256="",
                   Figure_Number="FIG1", Caption_Text="Figure 1 A caption.",
                   Caption_BBox="1,2,3,4", Figure_BBox="0,0,10,10",
                   Extraction_Method="PDFMINER_TEXT_BLOCKS", Confidence="1.00",
                   Confidence_Reason="", Human_Verification_Status="PENDING",
                   Verified_By="", Verified_At="", Observed_Panel_Count="",
                   Note="")]



print()
print("no document leaves the walk without a row that says what happened to it")
# REVERT: go back to printing the failures and extending only the draft. A
# document with no text layer, one that read fine and proposed nothing, and one
# that is not a PDF at all then contribute ZERO rows to every file the walk
# writes - which on ninety-seven articles is indistinguishable from ninety-seven
# articles that all worked.
_LDIR = os.path.join(ROOT, "ledger")
_pdfs = [minimal_pdf(os.path.join(ROOT, "good.pdf"),
                     [[(72, 700, "Body text about the design."),
                       (72, 300, "Figure 1 Mean arterial pressure before and "
                                 "after spaceflight in five cosmonauts.")]]),
         minimal_pdf(os.path.join(ROOT, "quiet2.pdf"),
                     [[(72, 700, "A page of prose with no caption on it.")]])]
# A DOWNLOAD THAT WENT WRONG: the publisher's "access denied" page, saved
# under the name the fetcher asked for. It is not a PDF, it is not a full text,
# and nobody can do anything with it but look at what came back.
_notpdf = os.path.join(ROOT, "notapdf.pdf")
open(_notpdf, "wb").write(
    b"<html><head><title>Access denied</title></head><body>"
    b"<p>Your institution does not subscribe.</p></body></html>\n")
_pdfs.append(_notpdf)
# A FULL TEXT WITH NO PAGES. Twelve of the 116 publications on the worklist
# arrive as JATS XML or plain text, carrying 37 figures between them. The
# captions are in the file and the pictures are not, so there is nothing to
# render and nothing to crop however long anybody stares at it - and filed as
# INTAKE_FAILED, all twelve went to whoever investigates broken downloads.
_jats = os.path.join(ROOT, "jats_fulltext.xml")
open(_jats, "w", encoding="utf-8").write(
    "<?xml version='1.0'?><article><body>"
    # NOT numbered 1 and 2. A JATS body lists the figures it contains, which
    # on a paper with supplementary material or a figure in the abstract does
    # not start at one - and reading the position instead of the label is a
    # renumbering nobody asked for.
    "<fig id='f1'><label>Figure 2.</label><caption><p>Mean arterial pressure "
    "before and after spaceflight.</p></caption>"
    "<graphic xlink:href='f2.tif' xmlns:xlink='http://www.w3.org/1999/xlink'/>"
    "</fig>"
    "<fig id='f2'><label>Fig. 10</label><caption><p>Heart rate during "
    "head-down bed rest.</p></caption></fig>"
    "</body></article>")
_pdfs.append(_jats)
_plain = os.path.join(ROOT, "plain_fulltext.txt")
open(_plain, "w", encoding="utf-8").write(
    "Cardiovascular deconditioning in spaceflight\n\nAbstract. "
    "A plain-text full text with no markup and no page images.\n")
_pdfs.append(_plain)
# A VALID PDF WITH NO TEXT ON IT. This is the scanned paper - about 42% of the
# corpus is expected to be one - and it is a different job from a file that is
# not a PDF: one needs a render and an eye, the other needs somebody to look at
# what was downloaded. The backend does not raise on it; it returns nothing.
_scanned = minimal_pdf(os.path.join(ROOT, "scanned.pdf"), [[], []])
_pdfs.append(_scanned)
_lout = io.StringIO()
with contextlib.redirect_stdout(_lout):
    _lcode = CI.main(_pdfs + ["--out", _LDIR])
check("the walk writes a document sheet as well as a candidate sheet",
      os.path.exists(os.path.join(_LDIR, "documents.html"))
      and os.path.exists(os.path.join(_LDIR, "index.html")))
_ledger = list(csv.DictReader(
    open(os.path.join(_LDIR, "intake_document_status.csv"), encoding="utf-8")))
_byfile = {r["Source_File"]: r for r in _ledger}
# COMPLETENESS holds in every environment, and it is the property this file
# exists for: CI installs only `requirements-lock.txt`, so there may be no PDF
# backend at all there, and "no backend" is one of the five statuses precisely
# so the walk still accounts for every file.
check("every file handed in has exactly one row",
      len(_ledger) == len(_pdfs) and len(_byfile) == len(_pdfs),
      "%d rows for %d files" % (len(_ledger), len(_pdfs)))
check("every row carries every ledger column",
      all(set(r) == set(CI.LEDGER_COLUMNS) for r in _ledger),
      "%s" % (set(_ledger[0]) ^ set(CI.LEDGER_COLUMNS)))
check("and every row's status, render state and action are declared ones",
      not [p for p in CI.ledger_problems(_ledger, expected_files=_pdfs)],
      "%s" % CI.ledger_problems(_ledger, expected_files=_pdfs))

if not _BACKEND:
    print("  SKIP the per-status scenarios: %s" % _NO_BACKEND)
    check("with no backend installed every real PDF says so, and says to "
          "install one",
          all(r["Text_Backend_Status"] == "BACKEND_UNAVAILABLE"
              and r["Required_Action"] == "INSTALL_A_PDF_BACKEND"
              for r in _ledger
              if r["Source_File"] not in ("notapdf.pdf", "jats_fulltext.xml",
                                          "plain_fulltext.txt")),
          "%s" % [(r["Source_File"], r["Text_Backend_Status"]) for r in _ledger])
    # And the file that is not a PDF is still not a PDF. That answer needs no
    # backend, so an environment with nothing installed still routes it to the
    # person who can look at what was downloaded rather than to the one who
    # installs software.
    check("and the file that is not a PDF is still INTAKE_FAILED",
          _byfile["notapdf.pdf"]["Text_Backend_Status"] == "INTAKE_FAILED",
          _byfile["notapdf.pdf"]["Text_Backend_Status"])
else:
    # REVERT: send a document with candidates to the contact sheet whether or
    # not there is a picture on it. Confirming a figure from a Figure_BBox
    # string is agreeing with a number, which is the thing rendering exists to
    # stop - and `--render` is optional, so the DEFAULT walk is that case.
    check("the one that worked says so",
          _byfile["good.pdf"]["Text_Backend_Status"] == "TEXT_LAYER_OK",
          "%s" % _byfile["good.pdf"])
    check("but with no pages rendered it is not ready to be confirmed",
          _byfile["good.pdf"]["Required_Action"] == "RENDER_CONTACT_SHEET",
          _byfile["good.pdf"]["Required_Action"])
    check("the one with no captions is not filed as the one that worked",
          _byfile["quiet2.pdf"]["Text_Backend_Status"] == "ZERO_CAPTION_CANDIDATES",
          _byfile["quiet2.pdf"]["Text_Backend_Status"])
    # REVERT: file a valid image-only PDF and a file that is not a PDF under
    # one status. They need opposite things done to them - a page render and an
    # eye, against somebody looking at what was downloaded - and about 42% of
    # this corpus is expected to be the first. The parser tells them apart for
    # neither: it raises on neither and returns nothing for both.
    check("a valid PDF with no text on it is NO_TEXT_LAYER",
          _byfile["scanned.pdf"]["Text_Backend_Status"] == "NO_TEXT_LAYER",
          _byfile["scanned.pdf"]["Text_Backend_Status"])
    check("and is sent to a render and an eye",
          _byfile["scanned.pdf"]["Required_Action"]
          == "RENDER_AND_INVENTORY_BY_EYE",
          _byfile["scanned.pdf"]["Required_Action"])
    # REVERT: take the page count from `max(block page number)`. A paper whose
    # last pages are scanned figures then reports a shorter document, and a
    # wholly scanned one reports zero pages - which reads like a file that is
    # not a PDF at all.
    check("and its page count is the file's, not the text layer's",
          _byfile["scanned.pdf"]["Page_Count"] == "2"
          or CI.page_count(_scanned) == 0,
          "%s (page_count says %s)" % (_byfile["scanned.pdf"]["Page_Count"],
                                       CI.page_count(_scanned)))
    # REVERT: parse the text layer again inside `draft_rows`. The ledger's
    # block count and the draft's candidates then come from two parses, and the
    # second is free to fail after the first succeeded - which breaks the one
    # promise `intake_document` makes.
    _parses = []
    _real_blocks = CI.text_blocks

    def _counted(path, backend=None):
        _parses.append(path)
        return _real_blocks(path, backend=backend)

    CI.text_blocks = _counted
    try:
        CI.intake_document(_pdfs[0], "ONCE", os.path.join(ROOT, "once"))
    finally:
        CI.text_blocks = _real_blocks
    check("a document's text layer is read exactly once",
          _parses.count(_pdfs[0]) == 1, "%d parses" % _parses.count(_pdfs[0]))
    # And the count in the ledger is the one `page_count` gives, whatever that
    # is on this machine - checked by making it say something no text layer
    # could.
    _real_pc = CI.page_count
    CI.page_count = lambda p: 77
    try:
        _, _pcrow = CI.intake_document(_scanned, "PC", os.path.join(ROOT, "pc"))
    finally:
        CI.page_count = _real_pc
    check("and the page count in the ledger is the FILE's, not the parser's",
          str(_pcrow["Page_Count"]) == "77", "%s" % _pcrow["Page_Count"])

    check("a file that is not a PDF is INTAKE_FAILED, not a scanned paper",
          _byfile["notapdf.pdf"]["Text_Backend_Status"] == "INTAKE_FAILED",
          _byfile["notapdf.pdf"]["Text_Backend_Status"])
    check("and is sent to somebody who can look at it",
          _byfile["notapdf.pdf"]["Required_Action"] == "INVESTIGATE",
          _byfile["notapdf.pdf"]["Required_Action"])
    check("and says why it was refused",
          "not a PDF" in _byfile["notapdf.pdf"]["Detail"],
          _byfile["notapdf.pdf"]["Detail"][:120])
check("a walk that accounts for every file it was given exits zero",
      _lcode == 0, "%d" % _lcode)

# REVERT: check the status and the action against a vocabulary and stop. Each
# of the five exists because it needs a different thing done to it, and a
# vocabulary does not say which - so NO_TEXT_LAYER / INSTALL_A_PDF_BACKEND
# passes and a scanned page goes to whoever installs software.
_TEMPLATE = {c: "" for c in CI.LEDGER_COLUMNS}
_TEMPLATE.update(Source_Document_ID="D1", Source_File="d1.pdf",
                 Input_Path="/c/d1.pdf", Text_Backend_Status="TEXT_LAYER_OK",
                 Required_Action="CONFIRM_ON_CONTACT_SHEET",
                 Page_Render_Status="RENDERED", Text_Block_Count="9",
                 Caption_Candidate_Count="3", Text_Backend="X",
                 Document_Inventory_Status="PENDING")
check("the template this section edits is itself clean",
      not CI.ledger_problems([_TEMPLATE]), "%s" % CI.ledger_problems([_TEMPLATE]))
for _status, _wrong in (("NO_TEXT_LAYER", "INSTALL_A_PDF_BACKEND"),
                        ("BACKEND_UNAVAILABLE", "INVESTIGATE"),
                        ("INTAKE_FAILED", "CHECK_CAPTION_STYLE"),
                        ("ZERO_CAPTION_CANDIDATES", "CONFIRM_ON_CONTACT_SHEET")):
    _row = dict(_TEMPLATE, Text_Backend_Status=_status, Required_Action=_wrong,
                Detail="x", Text_Backend="", Caption_Candidate_Count="0",
                Text_Block_Count="0")
    check("%s may not ask for %s" % (_status, _wrong),
          any(c == "LEDGER_ACTION_CONTRADICTS_STATUS"
              for _n, c, _d in CI.ledger_problems([_row])),
          "%s" % CI.ledger_problems([_row]))
# REVERT: leave the action free of the render state. `--render` is optional, so
# the DEFAULT walk then tells a person to confirm figures on a sheet with no
# pictures on it - which is agreeing with a bounding box.
check("a rendered document may not still be waiting for a render",
      any(c == "LEDGER_ACTION_CONTRADICTS_RENDER" for _n, c, _d in
          CI.ledger_problems([dict(_TEMPLATE,
                                   Required_Action="RENDER_CONTACT_SHEET")])),
      "%s" % CI.ledger_problems([dict(_TEMPLATE,
                                      Required_Action="RENDER_CONTACT_SHEET")]))
check("and an unrendered one may not be sent to be confirmed",
      any(c == "LEDGER_ACTION_CONTRADICTS_RENDER" for _n, c, _d in
          CI.ledger_problems([dict(_TEMPLATE,
                                   Page_Render_Status="NOT_REQUESTED")])))
for _label, _edit, _code in (
        ("text blocks under NO_TEXT_LAYER",
         dict(Text_Backend_Status="NO_TEXT_LAYER",
              Required_Action="RENDER_AND_INVENTORY_BY_EYE",
              Text_Block_Count="9", Caption_Candidate_Count="0"),
         "LEDGER_STATUS_CONTRADICTS_COUNT"),
        ("candidates under ZERO_CAPTION_CANDIDATES",
         dict(Text_Backend_Status="ZERO_CAPTION_CANDIDATES",
              Required_Action="CHECK_CAPTION_STYLE",
              Caption_Candidate_Count="3"),
         "LEDGER_STATUS_CONTRADICTS_COUNT"),
        ("a named backend under BACKEND_UNAVAILABLE",
         dict(Text_Backend_Status="BACKEND_UNAVAILABLE",
              Required_Action="INSTALL_A_PDF_BACKEND",
              Caption_Candidate_Count="0", Text_Block_Count="0"),
         "LEDGER_STATUS_CONTRADICTS_COUNT"),
        ("a failure with nothing said about it",
         dict(Text_Backend_Status="INTAKE_FAILED", Required_Action="INVESTIGATE",
              Detail="", Text_Backend="", Caption_Candidate_Count="0",
              Text_Block_Count="0"),
         "LEDGER_FAILURE_UNEXPLAINED"),
        # REVERT: let an unparsable count become -1 and pass. A ledger whose
        # counts are text says nothing about the walk and reports clean.
        ("a candidate count that is not a number",
         dict(Caption_Candidate_Count="abc"), "LEDGER_COUNT_NOT_A_NUMBER"),
        ("a block count that is not a number",
         dict(Text_Block_Count="lots"), "LEDGER_COUNT_NOT_A_NUMBER")):
    _bad = [dict(_TEMPLATE, **_edit)]
    check("%s is refused" % _label,
          any(c == _code for _n, c, _d in CI.ledger_problems(_bad)),
          "%s" % CI.ledger_problems(_bad))

# REVERT: key completeness on the basename. A corpus keeps pub127/fulltext.pdf
# next to pub386/fulltext.pdf, and on basenames those are one document twice -
# which also hides a genuinely missing paper behind the other one's row.
_a = dict(_TEMPLATE, Input_Path="/corpus/pub127/fulltext.pdf",
          Source_File="fulltext.pdf", Source_Document_ID="PUB127")
_b = dict(_TEMPLATE, Input_Path="/corpus/pub386/fulltext.pdf",
          Source_File="fulltext.pdf", Source_Document_ID="PUB386")
_both = ["/corpus/pub127/fulltext.pdf", "/corpus/pub386/fulltext.pdf"]
check("two documents with the same basename are two documents",
      not CI.ledger_problems([_a, _b], expected_files=_both),
      "%s" % CI.ledger_problems([_a, _b], expected_files=_both))
check("and one of them going missing is still noticed",
      any(c == "LEDGER_DOCUMENT_MISSING" for _n, c, _d in
          CI.ledger_problems([_a], expected_files=_both)),
      "%s" % CI.ledger_problems([_a], expected_files=_both))
# REVERT: drop the identifier check. Source_Document_ID names the page
# directory and prefixes every Draft_ID, so two inputs sharing one write over
# each other's pages and their draft rows collide.
check("two files sharing one Source_Document_ID are refused",
      any(c == "LEDGER_DOCUMENT_ID_COLLIDES" for _n, c, _d in
          CI.ledger_problems([_a, dict(_b, Source_Document_ID="PUB127")])),
      "%s" % CI.ledger_problems([_a, dict(_b, Source_Document_ID="PUB127")]))
# REVERT: let `--document-id` take several files. They then share a page
# directory and a Draft_ID prefix, and overwrite each other silently.
_argerr = io.StringIO()
try:
    with contextlib.redirect_stderr(_argerr):
        CI.main([_pdfs[0], _pdfs[1], "--out", os.path.join(ROOT, "twoid"),
                 "--document-id", "ONE"])
    _refused = False
except SystemExit:
    _refused = True
check("--document-id refuses to name two documents at once", _refused,
      _argerr.getvalue()[-160:])
_clean = io.StringIO()
with contextlib.redirect_stdout(_clean):
    _clean_code = CI.main([_pdfs[0], "--out", os.path.join(ROOT, "ok1")])
check("so a clean walk exits zero", _clean_code == 0, "%d" % _clean_code)
# The same file twice is the cheapest way to make the ledger disagree with the
# walk, and the walk has to fail rather than report a tidy summary.
_dupe = io.StringIO()
with contextlib.redirect_stdout(_dupe):
    _dupe_code = CI.main([_pdfs[0], _pdfs[0], "--out",
                          os.path.join(ROOT, "dupe")])
check("and a walk whose ledger does not add up exits non-zero",
      _dupe_code != 0, "%d" % _dupe_code)
check("saying which document it was",
      "LEDGER_DOCUMENT_DUPLICATED" in _dupe.getvalue(),
      _dupe.getvalue()[-200:])

# REVERT: drop `expected_files` from `ledger_problems`. A walk can then write a
# ledger that is internally perfect and silently short by one document, which
# is the exact failure the file exists to make impossible.
check("a ledger missing a file the walk was given is refused",
      any(c == "LEDGER_DOCUMENT_MISSING" for _n, c, _d in CI.ledger_problems(
          _ledger[:2], expected_files=_pdfs)),
      "%s" % CI.ledger_problems(_ledger[:2], expected_files=_pdfs))
check("and one holding a document twice is too",
      any(c == "LEDGER_DOCUMENT_DUPLICATED" for _n, c, _d in
          CI.ledger_problems(_ledger + [dict(_ledger[0])],
                             expected_files=_pdfs)))
for _label, _edit, _code in (
        ("a status nobody declared", dict(Text_Backend_Status="FINE"),
         "LEDGER_STATUS_UNKNOWN"),
        ("a render status nobody declared", dict(Page_Render_Status="MAYBE"),
         "LEDGER_RENDER_STATUS_UNKNOWN"),
        ("an action nobody declared", dict(Required_Action="ASK_SOMEBODY"),
         "LEDGER_ACTION_UNKNOWN"),
        ("no candidates filed as a clean read",
         dict(Caption_Candidate_Count="0", Text_Backend_Status="TEXT_LAYER_OK"),
         "LEDGER_STATUS_CONTRADICTS_COUNT"),
        ("candidates waiting under an action that does not mention them",
         dict(Caption_Candidate_Count="4",
              Required_Action="RENDER_AND_INVENTORY_BY_EYE"),
         "LEDGER_ACTION_CONTRADICTS_STATUS"),
        ("a row with no document behind it", dict(Source_Document_ID=""),
         "LEDGER_ROW_INCOMPLETE")):
    _bad = [dict(_byfile["good.pdf"], **_edit)]
    check("%s is refused" % _label,
          any(c == _code for _n, c, _d in CI.ledger_problems(_bad)),
          "%s" % CI.ledger_problems(_bad))

print()
print("the contact sheet shows the picture, when there is one")
# REVERT: leave `--render` in the docstring and unwired. The sheet then asks a
# person to confirm a figure from a bounding-box string, which is agreeing with
# a number rather than looking at a figure - and publication 127 needed forty
# such confirmations for three digitized panels.
_RDIR = os.path.join(ROOT, "rendered")
_rout = io.StringIO()
with contextlib.redirect_stdout(_rout):
    CI.main([_pdfs[0], "--out", _RDIR, "--render", "80"])
_rledger = list(csv.DictReader(
    open(os.path.join(_RDIR, "intake_document_status.csv"), encoding="utf-8")))[0]
_rdraft = list(csv.DictReader(
    open(os.path.join(_RDIR, "figure_intake_draft.csv"), encoding="utf-8")))
# The render is recorded whether or not the TEXT backend exists - they are two
# different tools and two different columns, and a walk with a renderer and no
# text layer is exactly the NO_TEXT_LAYER case this ledger is for.
check("the render status is recorded even when nothing could read the text",
      _rledger["Page_Render_Status"] in CI.PAGE_RENDER_STATUSES,
      _rledger["Page_Render_Status"])
if _rledger["Page_Render_Status"] == "RENDERER_UNAVAILABLE":
    print("  SKIP the renderer: pdftoppm is not installed")
elif not _BACKEND:
    print("  SKIP the crop scenarios: %s" % _NO_BACKEND)
else:
    check("the ledger says the pages were rendered, and how many",
          _rledger["Page_Render_Status"] == "RENDERED"
          and _rledger["Page_Render_Count"] == "1", "%s" % _rledger)
    check("every draft row names the raster it was written from",
          all(r["Page_Raster"] and len(r["Page_Raster_SHA256"]) == 64
              for r in _rdraft), "%s" % [r["Page_Raster"] for r in _rdraft])
    check("and the raster on disk is the one the row hashes",
          all(CI.file_sha256(r["Page_Raster"]) == r["Page_Raster_SHA256"]
              for r in _rdraft))
    check("a figure crop is cut for each candidate",
          all(r["Figure_Crop"] and os.path.exists(
              os.path.join(_RDIR, r["Figure_Crop"])) for r in _rdraft),
          "%s" % [r["Figure_Crop"] for r in _rdraft])
    _rhtml = open(os.path.join(_RDIR, "index.html"), encoding="utf-8").read()
    check("and the sheet shows it rather than describing it",
          all("<img src='%s'" % r["Figure_Crop"] in _rhtml for r in _rdraft),
          _rhtml[:200])
    check("a walk with no --render says NOT_REQUESTED, not RENDER_FAILED",
          _byfile["good.pdf"]["Page_Render_Status"] == "NOT_REQUESTED",
          _byfile["good.pdf"]["Page_Render_Status"])
    # REVERT: leave the page directory alone between runs. `pdftoppm` writes
    # page-1..page-N and the collector takes every `page-*.png` it finds, so a
    # second run over a shorter document of the same ID inherits the first
    # one's tail as though those pages were its own.
    _long = minimal_pdf(os.path.join(ROOT, "long.pdf"),
                        [[(72, 300, "Figure %d A caption about the design of "
                                    "the study." % (i + 1))] for i in range(4)])
    _short = minimal_pdf(os.path.join(ROOT, "short.pdf"),
                         [[(72, 300, "Figure 1 A caption about the design of "
                                     "the study.")]])
    _SDIR = os.path.join(ROOT, "stale")
    _q = io.StringIO()
    with contextlib.redirect_stdout(_q):
        CI.intake_document(_long, "SAMEID", _SDIR, render_dpi=60)
        _, _stale_row = CI.intake_document(_short, "SAMEID", _SDIR, render_dpi=60)
    check("a re-run over a shorter document does not inherit stale pages",
          str(_stale_row["Page_Render_Count"]) == "1",
          "%s" % _stale_row["Page_Render_Count"])
    check("and a rendered document IS ready to be confirmed",
          _rledger["Required_Action"] == "CONFIRM_ON_CONTACT_SHEET",
          _rledger["Required_Action"])

    # REVERT: show the candidates and stop. Six confirmed candidates in a
    # seven-figure paper is six correct rows and a wrong inventory, and
    # `inventory_rows` cannot see it - it checks the rows that exist. The pages
    # are how a person sees the figure nothing pointed at.
    _dsheet = open(os.path.join(_RDIR, "documents.html"),
                   encoding="utf-8").read()
    _rpages = sorted(os.listdir(os.path.join(_RDIR,
                                             _rledger["Page_Raster_Dir"])))
    check("the document sheet shows every rendered page, not only the crops",
          all(name in _dsheet for name in _rpages), "%s" % _rpages)
    check("and asks for the count only a person who saw them can give",
          "Observed_Figure_Count" in _dsheet)
    check("and the ledger has somewhere to put it",
          {"Pages_Checked", "Observed_Figure_Count",
           "Document_Inventory_Status"} <= set(CI.LEDGER_COLUMNS))
    check("a document with no candidate at all still gets a section",
          "nothing here points at it" in open(
              os.path.join(_LDIR, "documents.html"), encoding="utf-8").read())

# REVERT: fall back to US Letter when the page size is unknown. This corpus is
# largely A4 (595 x 842 pt), so the guess puts a crop 3% out in x and 9% out in
# y - most of a caption's height at the bottom of a page - and the person
# confirms the wrong rectangle rather than being told there is none.
_crop_row = {"Figure_BBox": "10,10,200,200"}
_page_png = os.path.join(ROOT, "page.png")
Image.new("RGB", (1240, 1754), "white").save(_page_png)
check("a crop with no page size behind it is refused, not guessed",
      CI.crop_figure(_crop_row, _page_png, os.path.join(ROOT, "c1.png"),
                     pdf_page_size=None) is None)
_made = CI.crop_figure(_crop_row, _page_png, os.path.join(ROOT, "c2.png"),
                       pdf_page_size=(595.0, 842.0))
check("and one with A4 behind it is scaled to A4, not to Letter",
      _made is not None
      and abs(Image.open(_made).height - (190 * 1754 / 842.0 + 16)) < 3,
      "%s" % ((Image.open(_made).size,) if _made else None,))

print()
print("a crop is worth looking at, or the whole page is shown instead")
# REVERT: show `Figure_Crop` whatever it contains. `Figure_BBox` is the gap
# between a caption and whatever is printed above it, and on fifteen staged
# articles 21 of 62 crops came out under a tenth of the page - a strip of white
# with the figure an inch above it. A person shown that either confirms a
# figure they cannot see or rejects one that is there.
_CQ = os.path.join(ROOT, "cq")
os.makedirs(_CQ, exist_ok=True)
_page_png = os.path.join(_CQ, "page.png")
Image.new("RGB", (800, 1000), "white").save(_page_png)
_fat = os.path.join(_CQ, "fat.png")
Image.new("RGB", (600, 400), "white").save(_fat)
_thin = os.path.join(_CQ, "thin.png")
Image.new("RGB", (600, 40), "white").save(_thin)
check("a crop that is most of the page is ACCEPTABLE",
      CI.crop_quality(_fat, _page_png) == "ACCEPTABLE",
      CI.crop_quality(_fat, _page_png))
check("a crop under a tenth of it is THIN_CROP",
      CI.crop_quality(_thin, _page_png) == "THIN_CROP",
      CI.crop_quality(_thin, _page_png))
check("and no crop at all is NO_CROP, which is a different thing",
      CI.crop_quality("", _page_png) == "NO_CROP"
      and CI.crop_quality(_fat, "") == "NO_CROP")
# Against the PAGE, so the same figure rendered twice gives the same answer.
# A pixel threshold would call the 150 DPI render thin and the 300 DPI one fine.
_page2 = os.path.join(_CQ, "page2x.png")
Image.new("RGB", (1600, 2000), "white").save(_page2)
_thin2 = os.path.join(_CQ, "thin2x.png")
Image.new("RGB", (1200, 80), "white").save(_thin2)
check("the answer does not change with the rendering DPI",
      CI.crop_quality(_thin2, _page2) == CI.crop_quality(_thin, _page_png)
      == "THIN_CROP",
      "%s vs %s" % (CI.crop_quality(_thin2, _page2),
                    CI.crop_quality(_thin, _page_png)))
_sheet_rows = [
    dict(Draft_ID="D1", Confidence="0.90", Figure_Crop="crops/fat.png",
         Page_Raster="pages/page.png", Crop_Quality_Status="ACCEPTABLE"),
    dict(Draft_ID="D2", Confidence="0.90", Figure_Crop="crops/thin.png",
         Page_Raster="pages/page.png", Crop_Quality_Status="THIN_CROP"),
    dict(Draft_ID="D3", Confidence="0.90", Figure_Crop="",
         Page_Raster="pages/page.png", Crop_Quality_Status="NO_CROP"),
]
_cq_html = open(CI.contact_sheet(os.path.join(_CQ, "sheet.html"), _sheet_rows),
                encoding="utf-8").read()
check("the sheet shows an acceptable crop",
      "<img src='crops/fat.png'" in _cq_html)
check("and the whole page where the crop is thin",
      "<img src='crops/thin.png'" not in _cq_html
      and _cq_html.count("<img src='pages/page.png'") == 2,
      "%d page images" % _cq_html.count("<img src='pages/page.png'"))
check("and says which it is looking at, so the reader is not misled",
      "THIN_CROP - whole page shown" in _cq_html
      and "NO_CROP - whole page shown" in _cq_html)
check("an undeclared crop quality is a draft problem",
      [c for _d, c, _x in CI.draft_problems(
          [dict(Draft_ID="D9", Crop_Quality_Status="FINE",
                Human_Verification_Status="PENDING")])] == ["CROP_QUALITY_UNKNOWN"],
      "%s" % CI.draft_problems([dict(Draft_ID="D9", Crop_Quality_Status="FINE",
                                     Human_Verification_Status="PENDING")]))


print()
print("a full text with no pages is not a broken download")
# REVERT: decide on `is_a_pdf` alone. Twelve of the worklist's 116 publications
# arrive as JATS XML or plain text and carry 37 figures between them; filed as
# INTAKE_FAILED they all went to whoever investigates broken downloads, and
# what they actually need is somebody to fetch the figure from the publisher.
for _name, _kind in (("good.pdf", "PDF"), ("jats_fulltext.xml", "JATS_XML"),
                     ("plain_fulltext.txt", "PLAIN_TEXT"),
                     ("notapdf.pdf", "UNREADABLE")):
    _path = next(p for p in _pdfs if os.path.basename(p) == _name)
    check("%-20s is %s" % (_name, _kind), CI.source_kind(_path) == _kind,
          CI.source_kind(_path))
# END TO END, through the real crop: a caption printed hard against the top of
# a page has almost nothing above it, so the box is a strip and the crop cut
# from it is not a figure. This is the case the fifteen-article walk found 21
# times, and without it the whole measurement could be replaced by the constant
# ACCEPTABLE and every scenario above would still pass.
_squeezed = minimal_pdf(os.path.join(ROOT, "squeezed.pdf"),
                        [[(72, 760, "A running head above the caption."),
                          (72, 740, "Figure 1 Mean arterial pressure before "
                                    "and after spaceflight in five men.")]])
_TDIR = os.path.join(ROOT, "thincrop")
_tq = io.StringIO()
with contextlib.redirect_stdout(_tq):
    _trows, _tledger = CI.intake_document(_squeezed, "SQ", _TDIR, render_dpi=80)
if _tledger["Page_Render_Status"] != "RENDERED" or not _trows:
    print("  SKIP the end-to-end thin crop: %s"
          % _tledger["Page_Render_Status"])
else:
    check("a caption with a strip above it yields a THIN_CROP, measured",
          [r["Crop_Quality_Status"] for r in _trows] == ["THIN_CROP"],
          "%s" % [(r["Crop_Quality_Status"], r["Figure_BBox"]) for r in _trows])
    _thtml = open(os.path.join(_TDIR, "index.html"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(_TDIR, "index.html")) else \
        open(CI.contact_sheet(os.path.join(_TDIR, "s.html"), _trows),
             encoding="utf-8").read()
    check("and the sheet shows that document's page, not its strip",
          "THIN_CROP - whole page shown" in _thtml)

_empty = os.path.join(ROOT, "empty.bin")
open(_empty, "wb").write(b"")
check("an empty file is UNREADABLE, not a plain-text full text",
      CI.source_kind(_empty) == "UNREADABLE", CI.source_kind(_empty))
check("and so is a binary blob",
      CI.source_kind(_page_png) == "UNREADABLE", CI.source_kind(_page_png))

_jrow = _byfile["jats_fulltext.xml"]
_prow = _byfile["plain_fulltext.txt"]
check("a JATS full text is NO_RASTER_SOURCE",
      _jrow["Text_Backend_Status"] == "NO_RASTER_SOURCE",
      _jrow["Text_Backend_Status"])
check("and is sent to whoever can fetch the figure",
      _jrow["Required_Action"] == "OBTAIN_PUBLISHER_FIGURE",
      _jrow["Required_Action"])
check("a plain-text full text goes the same way",
      (_prow["Text_Backend_Status"], _prow["Required_Action"])
      == ("NO_RASTER_SOURCE", "OBTAIN_PUBLISHER_FIGURE"), "%s" % _prow)
check("and the broken download still does not",
      _byfile["notapdf.pdf"]["Text_Backend_Status"] == "INTAKE_FAILED",
      _byfile["notapdf.pdf"]["Text_Backend_Status"])
_jdraft = [r for r in list(csv.DictReader(
    open(os.path.join(_LDIR, "figure_intake_draft.csv"), encoding="utf-8")))
    if r["Source_File"] == "jats_fulltext.xml"]
check("its two <fig> elements are two draft rows",
      len(_jdraft) == 2, "%d rows" % len(_jdraft))
check("with the figure numbers the document itself marked up",
      [r["Figure_Number"] for r in _jdraft] == ["FIG2", "FIG10"],
      "%s" % [r["Figure_Number"] for r in _jdraft])
check("and the captions attached to them",
      all("pressure" in _jdraft[0]["Caption_Text"]
          for _ in (0,)) and "Heart rate" in _jdraft[1]["Caption_Text"],
      "%s" % [r["Caption_Text"][:40] for r in _jdraft])
check("every one of them says there is no picture",
      all(r["Crop_Quality_Status"] == "NO_CROP"
          and r["Extraction_Method"] == "JATS_FIGURE_ELEMENTS"
          for r in _jdraft), "%s" % [r["Crop_Quality_Status"] for r in _jdraft])
check("and every one is still PENDING, like every other proposal",
      all(r["Human_Verification_Status"] == CI.DRAFT_PENDING for r in _jdraft))
check("the plain text names no figures rather than inventing one",
      not [r for r in list(csv.DictReader(
          open(os.path.join(_LDIR, "figure_intake_draft.csv"), encoding="utf-8")))
          if r["Source_File"] == "plain_fulltext.txt"])


print()
print("a draft becomes an inventory only when a person says so")


def _edited(**kw):
    row = dict(_draft[0])
    row.update(kw)
    return [row]


# REVERT: drop `draft_problems` from `inventory_rows`. A draft that came back
# with a confirmation and no name, or with a count nobody counted, then becomes
# an inventory - which is the one thing this layer exists to prevent.
for _label, _row, _code in (
        ("a confirmation with nobody behind it",
         dict(Human_Verification_Status="CONFIRMED", Observed_Panel_Count="3"),
         "DRAFT_VERDICT_UNATTRIBUTED"),
        ("a confirmation with no panel count",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11"), "DRAFT_PANEL_COUNT_MISSING"),
        ("a panel count of nought",
         dict(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
              Verified_At="2026-08-11", Observed_Panel_Count="0"),
         "DRAFT_PANEL_COUNT_MISSING"),
        ("a PENDING row that names a verifier anyway",
         dict(Verified_By="RV_1"), "DRAFT_PENDING_WITH_A_VERIFIER"),
        ("a PENDING row carrying a count",
         dict(Observed_Panel_Count="3"), "DRAFT_PENDING_WITH_A_COUNT"),
        ("a status nobody declared",
         dict(Human_Verification_Status="PROBABLY"), "DRAFT_STATUS_UNKNOWN")):
    _codes = [c for _d, c, _x in CI.draft_problems(_edited(**_row))]
    check("%s is refused" % _label, _codes == [_code], "%s" % _codes)
_dupe = _draft * 2
check("and two rows with one Draft_ID are refused",
      "DRAFT_ID_DUPLICATE" in [c for _d, c, _x in CI.draft_problems(_dupe)],
      "%s" % CI.draft_problems(_dupe))

_confirmed = _edited(Human_Verification_Status="CONFIRMED", Verified_By="RV_1",
                     Verified_At="2026-08-11", Observed_Panel_Count="3",
                     Page_Raster="p6.png", Page_Raster_SHA256="a" * 64)
_rows_out, _probs = CI.inventory_rows(_confirmed, reviewer_ids={"RV_1"},
                                      publication_id=127)
check("a confirmed row becomes one source_figure_manifest row",
      len(_rows_out) == 1 and not _probs, "%s %s" % (_rows_out, _probs))
check("and it says a HUMAN counted the panels, because one did",
      _rows_out[0]["Panel_Count_Method"] == "HUMAN_VISUAL"
      and _rows_out[0]["Inventory_Status"] == "VISUALLY_VERIFIED"
      and _rows_out[0]["Reviewer_ID"] == "RV_1"
      and _rows_out[0]["Observed_Panel_Count"] == "3", "%s" % _rows_out[0])
check("and carries the raster the person actually looked at",
      _rows_out[0]["Source_Image"] == "p6.png"
      and _rows_out[0]["Source_Image_SHA256"] == "a" * 64)
# REVERT: emit the confirmed rows and report the pending ones. A half-checked
# draft then produces an inventory that says the article has one figure,
# which is a completeness claim nobody made.
_half = _confirmed + [dict(_draft[0], Draft_ID="SD1_D002")]
_rows_out, _probs = CI.inventory_rows(_half, reviewer_ids={"RV_1"})
check("a draft with one row still PENDING produces no inventory at all",
      not _rows_out and any(c == "DRAFT_NOT_FINISHED" for _d, c, _x in _probs),
      "%s %s" % (len(_rows_out), _probs))
_rows_out, _probs = CI.inventory_rows(_confirmed, reviewer_ids={"RV_OTHER"})
check("and a verifier who is not in the registry is refused",
      not _rows_out
      and any(c == "DRAFT_VERIFIER_NOT_REGISTERED" for _d, c, _x in _probs),
      "%s" % _probs)
_rejected = _edited(Human_Verification_Status="REJECTED", Verified_By="RV_1",
                    Verified_At="2026-08-11")
_rows_out, _probs = CI.inventory_rows(_rejected, reviewer_ids={"RV_1"})
check("a rejected candidate leaves no row and no complaint",
      not _rows_out and not _probs, "%s %s" % (_rows_out, _probs))

print()
print("v9.20 the label a document prints, and whether it was read at all")

# ---------------------------------------------------------------- the label
_ident = CI.figure_identifier
check("a plain caption label reads as its own number",
      _ident("Fig. 3. Mean changes") == ("FIG3", "3", "FIG", "Mean changes"),
      "%s" % (_ident("Fig. 3. Mean changes"),))
check("Extended Data is a series of its own, not a renumbering",
      _ident("Extended Data Fig. 1")[0] == "EXTFIG1",
      "%s" % (_ident("Extended Data Fig. 1"),))
check("so Extended Data Fig. 1 and Fig. 1 do not collide",
      _ident("Extended Data Fig. 1")[0] != _ident("Fig. 1")[0])
check("a supplementary figure lands in the same separate series",
      _ident("Supplementary Figure 2")[0] == "EXTFIG2")
check("a label that does not parse yields nothing, not a guess",
      _ident("Scheme A") is None and _ident("") is None)

# ------------------------------------------- a caption opens a line, not a block
_mid = [(4, 10.0, 10.0, 300.0, 200.0,
         "before and after bed rest in nine subjects.\n"
         "Fig. 3. Mean changes in plasma volume after two weeks.")]
_hit = CI.caption_candidates(_mid)
check("a caption is found when its block starts with something else",
      [h["number"] for h in _hit] == ["3"], "%s" % ([h["number"] for h in _hit],))
check("and the row records that the box is the block, not the caption",
      _hit and _hit[0]["line_offset"] == 1, "%s" % (_hit,))
_top = [(4, 10.0, 10.0, 300.0, 200.0, "Fig. 3. Mean changes in plasma volume.")]
check("a caption that does open its block still reports offset zero",
      CI.caption_candidates(_top)[0]["line_offset"] == 0)

# --------------------------------------------------- a panel letter is not a caption
_panel = [(4, 10.0, 10.0, 300.0, 90.0,
           "Figure 4A depicts plasma norepinephrine levels before flight.")]
check("a label with a panel letter is not taken as a caption",
      CI.caption_candidates(_panel) == [], "%s" % CI.caption_candidates(_panel))
_plain = [(4, 10.0, 10.0, 300.0, 90.0,
           "Figure 4 depicts plasma norepinephrine levels before flight.")]
check("and the same line without the letter still is - the rule is the "
      "suffix, not the sentence",
      [h["number"] for h in CI.caption_candidates(_plain)] == ["4"])
check("a two-digit number is not mistaken for a panel letter",
      [h["number"] for h in CI.caption_candidates(
          [(1, 0.0, 0.0, 9.0, 9.0, "Figure 12. Something.")])] == ["12"])

# A LETTER IS NOT A DIGIT, even when the page clearly meant one. Publication
# 554 prints its first caption as "Fig.l." - a lower-case L where the 1 should
# be - and both automatic readers agree on the letter, because that is what is
# in the file. Reading it as a 1 would mean reading every "Fig. a", "Fig. l"
# and "Fig. I" as a number too, and there is no way to be right about which.
# The figure stays missing and a person supplies it.
check("a label whose number is a letter is refused, not guessed",
      CI.caption_candidates(
          [(5, 0.0, 0.0, 9.0, 9.0, "Fig.l. Mean changes in time and frequency")])
      == [])
check("and the same caption with a real digit reads",
      [h["number"] for h in CI.caption_candidates(
          [(5, 0.0, 0.0, 9.0, 9.0, "Fig.1. Mean changes in time and frequency")])]
      == ["1"])

# ------------------------------------------------- XML the page broke, not poppler
check("a control character the page carried does not take out the reader",
      CI.XML_FORBIDDEN.sub("", "<a>x\x0cy</a>") == "<a>xy</a>",
      "%r" % CI.XML_FORBIDDEN.sub("", "<a>x\x0cy</a>"))
check("and ordinary text survives it untouched",
      CI.XML_FORBIDDEN.sub("", "<a>Fig. 1\u00a0caption</a>")
      == "<a>Fig. 1\u00a0caption</a>")


class _PopplerSaying(object):
    """poppler, handing back the bytes a real page carried.

    Twenty-seven of this corpus's ninety PDFs make `pdftotext -bbox-layout`
    emit a control character straight from the page into its XML. XML 1.0
    cannot carry one, so ElementTree refused the whole document and the
    backend came back "could not be read" - on a third of the corpus, with no
    sign that the fault was in the transport rather than the paper.
    """

    def __init__(self, xml):
        self.xml = xml

    def __enter__(self):
        self.real = CI.subprocess.run
        outer = self

        def fake(args, **kw):
            class R(object):
                stdout = outer.xml
                returncode = 0
            return R()
        CI.subprocess.run = fake
        return self

    def __exit__(self, *exc):
        CI.subprocess.run = self.real


_XML = ("<doc><page width='600' height='800'><block>"
        "<line><word xMin='10' yMin='20' xMax='60' yMax='30'>Fig.</word>"
        "<word xMin='62' yMin='20' xMax='70' yMax='30'>1.\x0c</word>"
        "<word xMin='72' yMin='20' xMax='140' yMax='30'>Caption</word>"
        "</line></block></page></doc>")
with _PopplerSaying(_XML):
    try:
        _pb = CI._poppler_blocks("/tmp/whatever.pdf")
        _pb_err = ""
    except Exception as _e:
        _pb, _pb_err = None, "%s: %s" % (type(_e).__name__, _e)
check("a page's own control character does not take the poppler reader out",
      _pb is not None, _pb_err)
check("and the caption on that page still reads",
      _pb and CI.caption_candidates(_pb)
      and CI.caption_candidates(_pb)[0]["number"] == "1", "%s" % (_pb,))

with _PopplerSaying(_XML.replace("1.\x0c", "1.")):
    _clean = CI._poppler_blocks("/tmp/whatever.pdf")
check("the same page without the control character reads identically - the "
      "strip removed a transport byte, not a word",
      _clean and _pb and [b[5] for b in _clean] == [b[5] for b in _pb],
      "%s vs %s" % (_clean, _pb))

# ------------------------------------------ whether the backend read the document
check("the floor is a share of the text, not a count of captions",
      0.0 < CI.TEXT_VOLUME_FLOOR < 1.0, "%s" % CI.TEXT_VOLUME_FLOOR)
check("a backend that read almost nothing has its own status",
      "TEXT_EXTRACTION_INCOMPLETE" in CI.TEXT_BACKEND_STATUSES)
check("and that status sends a person to the other backend, not to captions",
      CI.STATUS_ACTION["TEXT_EXTRACTION_INCOMPLETE"]
      == ("RETRY_WITH_OTHER_BACKEND",))
check("every status still maps to an action in the vocabulary",
      all(a in CI.REQUIRED_ACTIONS
          for acts in CI.STATUS_ACTION.values() for a in acts))
check("a missing reader reports no volume rather than raising",
      CI.independent_text_volume(os.path.join(ROOT, "does_not_exist.pdf")) == 0)

# ------------------------------------------------- a JATS label is never invented
_ext = [("Extended Data Fig. 1", "The environment."),
        ("Extended Data Fig. 2", "The biosamples."),
        ("Fig. 1", "Multi-omic changes."),
        ("Fig. 2", "Virome-wide antibody analysis."),
        ("Extended Data Fig. 3", "Paper-based assay.")]
_srows = CI._sourceless_rows("/tmp/x.xml", "SD9", "deadbeef", _ext)
_nums = [r["Figure_Number"] for r in _srows]
check("Extended Data figures keep their own numbers in their own series",
      _nums == ["EXTFIG1", "EXTFIG2", "FIG1", "FIG2", "EXTFIG3"], "%s" % _nums)
check("so the third Extended Data figure is not numbered by its position",
      _srows[4]["Figure_Number"] != "FIG5")
check("and no two figures in the document share an identifier",
      len(set(_nums)) == len(_nums))
_bad = CI._sourceless_rows("/tmp/x.xml", "SD9", "deadbeef",
                           [("Scheme A", "Not a numbered figure.")])
check("an unreadable label produces no number at all",
      _bad[0]["Figure_Number"] == "", "%r" % _bad[0]["Figure_Number"])
check("it is not numbered by where it sits in the file",
      _bad[0]["Figure_Number"] not in ("FIG1", "1"))
check("and it does not claim the document marked it up",
      _bad[0]["Confidence"] == "0.00"
      and "does not parse" in _bad[0]["Confidence_Reason"],
      "%s %s" % (_bad[0]["Confidence"], _bad[0]["Confidence_Reason"]))
check("the label the document printed is kept beside the number",
      _bad[0]["Figure_Label_Raw"] == "Scheme A"
      and _srows[0]["Figure_Label_Raw"] == "Extended Data Fig. 1")
check("a caption's own prose cannot supply the number the label lacks",
      CI._sourceless_rows("/tmp/x.xml", "SD9", "d",
                          [("", "Figure 7 shows the relationship.")]
                          )[0]["Figure_Number"] == "")

# ------------------------------------------------ a number that repeats is marked
_dup = CI._sourceless_rows("/tmp/x.xml", "SD9", "d",
                           [("Fig. 1", "Chapter one."), ("Fig. 1", "Chapter two."),
                            ("Fig. 2", "Only once.")])
check("a figure number used twice in one document says so on both rows",
      [r["Label_Repeats_In_Document"] for r in _dup] == ["2", "2", ""],
      "%s" % [r["Label_Repeats_In_Document"] for r in _dup])
check("the column is in the schema, so a reader cannot miss it",
      "Label_Repeats_In_Document" in CI.DRAFT_COLUMNS
      and "Figure_Label_Raw" in CI.DRAFT_COLUMNS)


print()
print("v9.21 what may set the edge of a figure's box")

# --------------------------------------------------- running heads and folios
def _paged(n, text, y, x0=40.0, x1=560.0):
    return (n, x0, y, x1, y + 10.0, text)

_doc = []
for _p in range(1, 7):
    _doc.append(_paged(_p, "Downloaded from journals.physiology.org", 12.0))
    _doc.append(_paged(_p, "H84%d" % _p, 780.0, 40.0, 60.0))
    _doc.append(_paged(_p, "A paragraph of body text sitting in the "
                           "left column of the page.", 200.0, 44.0, 300.0))
_furn = CI.page_furniture(_doc)
check("a header repeated on every page is furniture",
      all(id(b) in _furn for b in _doc if "Downloaded" in b[5]))
check("a folio is furniture even though its digits differ per page",
      all(id(b) in _furn for b in _doc if b[5].startswith("H84")),
      "%d of 6" % sum(1 for b in _doc if b[5].startswith("H84")
                      and id(b) in _furn))
check("body text is not furniture, however ordinary it looks",
      not any(id(b) in _furn for b in _doc if "paragraph" in b[5]))
check("the flattening is what finds a folio, not a list of words",
      CI._furniture_key("H842") == CI._furniture_key("H843")
      and CI._furniture_key("Fig. 1") != CI._furniture_key("Table 1"))
check("a document too short for repetition to mean anything has none",
      CI.page_furniture([_paged(1, "Header", 12.0),
                         _paged(2, "Header", 12.0)]) == set())
# The fixture needs a page tall enough for a middle to exist: with one block
# the page IS that block, and its only line sits in both margins at once.
_mid = []
for _p in range(1, 7):
    _mid.append(_paged(_p, "Repeated mid-page line", 400.0))
    _mid.append(_paged(_p, "Top of the page", 20.0))
    _mid.append(_paged(_p, "Foot of the page", 780.0))
check("a repeated line in the MIDDLE of the page is not furniture",
      not any(id(b) in CI.page_furniture(_mid)
              for b in _mid if "mid-page" in b[5]))
check("while the repeated lines in its margins are",
      all(id(b) in CI.page_furniture(_mid)
          for b in _mid if "Top of" in b[5] or "Foot of" in b[5]))

# a page-spanning footer used to drag the box across the gutter
_two_col = [
    _paged(4, "Downloaded from journals.physiology.org", 12.0, 40.0, 560.0),
    _paged(4, "Fig. 1. Left column caption for the first figure.",
           400.0, 44.0, 290.0),
    _paged(4, "Fig. 2. Right column caption for the second figure.",
           400.0, 310.0, 556.0),
]
for _p in (1, 2, 3, 5, 6):
    _two_col.append(_paged(_p, "Downloaded from journals.physiology.org", 12.0,
                           40.0, 560.0))
_c1 = [c for c in CI.caption_candidates(_two_col) if c["number"] == "1"][0]
_box1 = CI.figure_bbox(_c1, _two_col)
check("a caption's box stays in its own column when a footer spans the page",
      _box1 is not None and _box1[2] <= 300.0,
      "%s" % (_box1,))
_box1_furn = CI.figure_bbox(_c1, _two_col, furniture=set())
check("and with the footer left in, it reaches the other column - so the "
      "exclusion is what holds the edge",
      _box1_furn is not None and _box1_furn[2] > 300.0, "%s" % (_box1_furn,))

# ----------------------------------------- what stops the walk up the page
_cap = 250.0
check("an axis title does not stop the walk", CI.interior_floor(
      [(1, 50.0, 300.0, 90.0, 310.0, "Heart rate")], _cap) == 0.0)
check("a tick value does not stop the walk", CI.interior_floor(
      [(1, 50.0, 300.0, 70.0, 310.0, "40")], _cap) == 0.0)
check("a panel letter does not stop the walk", CI.interior_floor(
      [(1, 50.0, 300.0, 62.0, 310.0, "B")], _cap) == 0.0)
_para = (1, 44.0, 300.0, 290.0, 330.0,
         "A full paragraph of the article's body text, which is both wide "
         "and long and is where the figure's region ends.")
check("a paragraph stops it", CI.interior_floor([_para], _cap) == 330.0)
check("another caption stops it, because that region is a different figure",
      CI.interior_floor(
          [(1, 44.0, 300.0, 290.0, 330.0, "Fig. 4. Another caption.")],
          _cap) == 330.0)
check("the walk passes the labels and stops at the paragraph behind them",
      CI.interior_floor(
          [(1, 50.0, 380.0, 90.0, 390.0, "Heart rate"),
           (1, 50.0, 360.0, 70.0, 370.0, "40"),
           _para], _cap) == 330.0)
check("with nothing above it the region runs to the top of the page",
      CI.interior_floor([], _cap) == 0.0)
check("a long block that is narrow is still a label, not a paragraph",
      CI.interior_floor(
          [(1, 50.0, 300.0, 90.0, 310.0,
            "Mean arterial pressure during the tilt protocol")], _cap) == 0.0)
check("a wide block that is short is still a label",
      CI.interior_floor([(1, 44.0, 300.0, 290.0, 310.0, "mmHg")], _cap) == 0.0)

# ...and through figure_bbox, because that is where the walk is called from
_fig = [(4, 44.0, 500.0, 290.0, 520.0,
         "Fig. 1. Mean arterial pressure before and after spaceflight."),
        (4, 60.0, 300.0, 100.0, 312.0, "Heart rate"),
        (4, 60.0, 280.0, 80.0, 292.0, "40"),
        (4, 44.0, 120.0, 290.0, 180.0,
         "A full paragraph of the article's body text above the figure, "
         "wide and long, which is where this figure's region ends.")]
_fc = [c for c in CI.caption_candidates(_fig) if c["number"] == "1"][0]
_fbox = CI.figure_bbox(_fc, _fig)
check("the box reaches past the axis labels to the paragraph above them",
      _fbox is not None and abs(_fbox[1] - 180.0) < 0.01,
      "%s" % (_fbox,))
check("and stopping at the nearest block instead would cut the figure off "
      "just above its caption",
      max(b[4] for b in _fig if b[4] <= _fc["bbox"][1]) == 312.0)

# ------------------------------------------- what the crop itself can be told
try:
    from PIL import Image as _PIL
    import numpy as _np
    _IMAGING = True
except Exception as _e:                                 # pragma: no cover
    _IMAGING = False
    print("  SKIP the crop-image scenarios: %s" % _e)

if _IMAGING:
    def _canvas(w, h, marks):
        im = _PIL.new("L", (w, h), 255)
        px = im.load()
        for (x0, y0, x1, y1) in marks:
            for x in range(x0, x1):
                for y in range(y0, y1):
                    px[x, y] = 0
        return im

    _bordered = _canvas(100, 100, [(30, 30, 70, 70)])
    _trimmed = CI.trim_outer_margin(_bordered)
    check("a blank border is trimmed away",
          _trimmed.size == (40, 40), "%s" % (_trimmed.size,))

    # two panels with a gap: the gap is the FIGURE's, not a boundary
    _panels = _canvas(100, 60, [(10, 10, 40, 50), (60, 10, 90, 50)])
    _pt = CI.trim_outer_margin(_panels)
    check("an interior gap between two panels is kept, not closed on one",
          _pt.size == (80, 40), "%s" % (_pt.size,))
    check("and the gap is still white inside the trimmed picture",
          _np.asarray(_pt.convert("L"))[:, 35:45].min() == 255)

    check("ink lying against a side means the box cut the drawing",
          CI._ink_touches_side(_canvas(60, 60, [(0, 5, 40, 55)])))
    check("a picture with white margins is not called clipped",
          not CI._ink_touches_side(_canvas(60, 60, [(10, 10, 50, 50)])))
    check("one stray mark on the border is not a cut",
          not CI._ink_touches_side(_canvas(60, 60, [(0, 0, 1, 2)])))

    _cq = tempfile.mkdtemp(prefix="fdt_crop_", dir=ROOT)
    _page = os.path.join(_cq, "page.png")
    _canvas(200, 400, [(20, 20, 180, 380)]).save(_page)
    _clipped_png = os.path.join(_cq, "clipped.png")
    _canvas(120, 300, [(0, 10, 110, 290)]).save(_clipped_png)
    check("crop_quality alone still calls a clipped crop acceptable - which "
          "is why the pair exists",
          CI.crop_quality(_clipped_png, _page) == "ACCEPTABLE")
    check("EDGE_CLIPPED is in the vocabulary the ledger checks against",
          "EDGE_CLIPPED" in CI.CROP_QUALITY_STATUSES)

    _row = {"Figure_BBox": "10,10,110,290", "Draft_ID": "D1"}
    _out = os.path.join(_cq, "made.png")
    _made, _q = CI.crop_and_grade(_row, _page, _out, pdf_page_size=(200, 400))
    check("a box that cuts the drawing is graded EDGE_CLIPPED, not ACCEPTABLE",
          _q == "EDGE_CLIPPED", "%s" % _q)
    _page2 = os.path.join(_cq, "page2.png")
    _canvas(200, 400, [(60, 60, 140, 340)]).save(_page2)
    _row2 = {"Figure_BBox": "20,20,180,380", "Draft_ID": "D2"}
    _made2, _q2 = CI.crop_and_grade(_row2, _page2,
                                    os.path.join(_cq, "made2.png"),
                                    pdf_page_size=(200, 400))
    check("a box with room around the drawing is still ACCEPTABLE - the test "
          "does not fail everything",
          _q2 == "ACCEPTABLE", "%s" % _q2)
    check("a row with no box gets no crop and no grade",
          CI.crop_and_grade({"Figure_BBox": ""}, _page2,
                            os.path.join(_cq, "made3.png"),
                            pdf_page_size=(200, 400)) == ("", "NO_CROP"))

    # ...and the trim has to happen on the way to the FILE, not merely be
    # available as a function: a box far larger than its drawing must not
    # reach the sheet as a picture that is mostly white.
    _page4 = os.path.join(_cq, "page4.png")
    _canvas(200, 400, [(80, 150, 120, 250)]).save(_page4)
    _made4, _q4 = CI.crop_and_grade({"Figure_BBox": "20,20,180,380",
                                     "Draft_ID": "D4"}, _page4,
                                    os.path.join(_cq, "made4.png"),
                                    pdf_page_size=(200, 400))
    _sz = _PIL.open(_made4).size if _made4 else None
    check("the saved crop is the drawing, not the box it was cut from",
          _sz == (40, 100), "%s" % (_sz,))

    _sheet = os.path.join(_cq, "sheet.html")
    CI.contact_sheet(_sheet, [dict(_sheet_row("D1", 0.9, ""),
                                   Crop_Quality_Status="EDGE_CLIPPED",
                                   Figure_Crop="made.png",
                                   Page_Raster="page.png")], root=_cq)
    _html = io.open(_sheet, encoding="utf-8").read()
    check("a clipped crop sends the reader to the whole page instead",
          "whole page shown" in _html and "EDGE_CLIPPED" in _html)

if not _BACKEND:
    print("  SKIP the v9.20 document scenarios: %s" % _NO_BACKEND)
else:
    print()
    print("v9.20 through the whole document path")
    _lines = [[(72, 700, "Body text about the study design and its subjects."),
               (72, 300, "Figure 1 Mean arterial pressure before spaceflight.")],
              [(72, 600, "Figure 2A shows the left panel of the second figure."),
               (72, 400, "Figure 3 Heart rate response to standing upright.")]]
    _p2 = minimal_pdf(os.path.join(ROOT, "v920.pdf"), _lines)
    _r2 = CI.draft_rows(_p2, "SD920")
    _n2 = sorted(r["Figure_Number"] for r in _r2)
    check("the panel reference does not become a figure row",
          _n2 == ["FIG1", "FIG3"], "%s" % _n2)
    check("every drafted row carries the words the page printed",
          all(r["Figure_Label_Raw"] for r in _r2))
    check("a document whose numbers are all distinct marks no repeat",
          all(r["Label_Repeats_In_Document"] == "" for r in _r2))

    _dupdoc = minimal_pdf(os.path.join(ROOT, "v920dup.pdf"),
                          [[(72, 600, "Figure 1 First chapter opening figure.")],
                           [(72, 600, "Figure 1 Second chapter opening figure.")]])
    _rd = CI.draft_rows(_dupdoc, "SD921")
    check("a number printed once per chapter is marked on every row it names",
          [r["Label_Repeats_In_Document"] for r in _rd] == ["2", "2"],
          "%s" % [r["Label_Repeats_In_Document"] for r in _rd])
    check("and the rows stay separate rather than collapsing to one",
          len(_rd) == 2 and len({r["Draft_ID"] for r in _rd}) == 2)

    _out920 = tempfile.mkdtemp(prefix="fdt_v920_", dir=ROOT)
    _rows920, _led920 = CI.intake_document(_p2, "SD922", _out920)
    check("a document the backend read properly is not called incomplete",
          _led920["Text_Backend_Status"] == "TEXT_LAYER_OK",
          "%s %s" % (_led920["Text_Backend_Status"], _led920["Detail"]))

    class _Blind(object):
        """A backend that returns a little text where there is a lot."""
        def __enter__(self):
            self.real = CI.text_blocks
            CI.text_blocks = lambda path, backend=None: [
                (1, 0.0, 0.0, 9.0, 9.0, "a b")]
            return self
        def __exit__(self, *exc):
            CI.text_blocks = self.real

    with _Blind():
        _out_b = tempfile.mkdtemp(prefix="fdt_v920b_", dir=ROOT)
        _rb, _lb = CI.intake_document(_p2, "SD923", _out_b)
    check("a backend that returned 3% of the text is not filed as read",
          _lb["Text_Backend_Status"] == "TEXT_EXTRACTION_INCOMPLETE",
          "%s" % _lb["Text_Backend_Status"])
    check("it is not filed as a document with no captions",
          _lb["Text_Backend_Status"] != "ZERO_CAPTION_CANDIDATES")
    check("and it sends a person to the other backend",
          _lb["Required_Action"] == "RETRY_WITH_OTHER_BACKEND",
          "%s" % _lb["Required_Action"])
    check("the ledger says how little came out",
          "characters" in _lb["Detail"], "%s" % _lb["Detail"])

    _empty = minimal_pdf(os.path.join(ROOT, "v920none.pdf"),
                         [[(72, 600, "Body text with no figure label at all.")]])
    _out_z = tempfile.mkdtemp(prefix="fdt_v920z_", dir=ROOT)
    _rz, _lz = CI.intake_document(_empty, "SD924", _out_z)
    check("a document that really was read and has no captions still says so",
          _lz["Text_Backend_Status"] == "ZERO_CAPTION_CANDIDATES",
          "%s %s" % (_lz["Text_Backend_Status"], _lz["Detail"]))

    # THE WALK TAKES THE REMEDY IT NAMES. A ledger row reading "retry with the
    # other backend" that nobody acts on leaves the figures out of the draft:
    # the first corpus run lost twelve figures across three publications that
    # way, and a hand-run second pass found every one.
    class _BlindOnce(object):
        """A declared backend that reads almost nothing; the other is fine."""
        def __enter__(self):
            self.real = CI.text_blocks
            def fake(path, backend=None):
                if backend == "PDFMINER_TEXT_BLOCKS":
                    return [(1, 0.0, 0.0, 9.0, 9.0, "a b")]
                return self.real(path, backend=backend)
            CI.text_blocks = fake
            return self
        def __exit__(self, *exc):
            CI.text_blocks = self.real

    with _BlindOnce():
        _out_r = tempfile.mkdtemp(prefix="fdt_v921r_", dir=ROOT)
        _rr, _lr = CI.intake_document(_p2, "SD925", _out_r,
                                      backend="PDFMINER_TEXT_BLOCKS")
    check("a document the declared backend could not read is read by the other",
          _lr["Text_Backend_Status"] == "TEXT_LAYER_OK" and len(_rr) > 0,
          "%s / %d rows" % (_lr["Text_Backend_Status"], len(_rr)))
    check("and the ledger says the switch happened and why",
          "was used instead" in _lr["Detail"], "%s" % _lr["Detail"])
    check("every row records the backend that actually read it",
          all(r["Extraction_Method"] == _lr["Text_Backend"] for r in _rr),
          "%s vs %s" % ({r["Extraction_Method"] for r in _rr},
                        _lr["Text_Backend"]))

    class _BlindBoth(object):
        def __enter__(self):
            self.real = CI.text_blocks
            CI.text_blocks = lambda path, backend=None: [
                (1, 0.0, 0.0, 9.0, 9.0, "a b")]
            return self
        def __exit__(self, *exc):
            CI.text_blocks = self.real

    with _BlindBoth():
        _out_n = tempfile.mkdtemp(prefix="fdt_v921n_", dir=ROOT)
        _rn, _ln = CI.intake_document(_p2, "SD926", _out_n)
    check("when neither backend reads it, the document is still refused",
          _ln["Text_Backend_Status"] == "TEXT_EXTRACTION_INCOMPLETE",
          "%s" % _ln["Text_Backend_Status"])
    check("and the refusal names what the second one managed too",
          "did no better" in _ln["Detail"], "%s" % _ln["Detail"])

    # AND THE SWITCH IS NOT DECIDED BY WHAT COMES OUT OF IT. Here the other
    # backend finds a CAPTION where the declared one found none, and still
    # reads almost none of the page. A rule that switched on captions would
    # take it and file a one-figure inventory for a twenty-thousand-character
    # document; the volume rule refuses both and says so.
    class _CaptionBait(object):
        def __enter__(self):
            self.real = CI.text_blocks
            def fake(path, backend=None):
                if backend == "PDFMINER_TEXT_BLOCKS":
                    return [(1, 0.0, 0.0, 9.0, 9.0, "a b")]
                return [(1, 0.0, 0.0, 90.0, 20.0,
                         "Fig. 1. A caption and nothing else on the page.")]
            CI.text_blocks = fake
            return self
        def __exit__(self, *exc):
            CI.text_blocks = self.real

    with _CaptionBait():
        _out_c = tempfile.mkdtemp(prefix="fdt_v921c_", dir=ROOT)
        _rc, _lc = CI.intake_document(_p2, "SD927", _out_c,
                                      backend="PDFMINER_TEXT_BLOCKS")
    check("a backend offering a caption but no text does not win the switch",
          _lc["Text_Backend_Status"] == "TEXT_EXTRACTION_INCOMPLETE",
          "%s (%d rows)" % (_lc["Text_Backend_Status"], len(_rc)))
    check("and no draft row is written from it",
          not _rc, "%s" % [r["Figure_Number"] for r in _rc])

print()
print("the schema the rest of the package will read")
import batch_manifests as BM                                    # noqa: E402
_emitted = CI.inventory_rows(_confirmed, reviewer_ids={"RV_1"},
                             publication_id=127)[0][0]
check("every column source_figure_manifest requires is produced",
      not [c for c in BM.source_figure_manifest_columns() if c not in _emitted],
      "%s" % [c for c in BM.source_figure_manifest_columns()
              if c not in _emitted])
check("and nothing else, so a column added there is a visible failure here",
      not [c for c in _emitted if c not in BM.source_figure_manifest_columns()],
      "%s" % [c for c in _emitted if c not in BM.source_figure_manifest_columns()])

print()
# One line, one format, for the CI guard that checks the documented
# scenario count against the measured one. The sentence above it is
# for a person; this is for `verify_documented_status.py`, and a
# regex over prose is what it replaces - two suites in this package
# print no count sentence at all.
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
