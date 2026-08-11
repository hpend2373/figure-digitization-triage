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


_BACKEND = ""
try:
    _BACKEND = CI._default_backend()
except CI.BackendUnavailable as _exc:
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
_notpdf = os.path.join(ROOT, "notapdf.pdf")
open(_notpdf, "wb").write(b"this is not a PDF at all\n" * 40)
_pdfs.append(_notpdf)
_lout = io.StringIO()
with contextlib.redirect_stdout(_lout):
    _lcode = CI.main(_pdfs + ["--out", _LDIR])
_ledger = list(csv.DictReader(
    open(os.path.join(_LDIR, "intake_document_status.csv"), encoding="utf-8")))
_byfile = {r["Source_File"]: r for r in _ledger}
check("every file handed in has exactly one row",
      len(_ledger) == 3 and len(_byfile) == 3, "%d rows" % len(_ledger))
check("the one that worked says so",
      _byfile["good.pdf"]["Text_Backend_Status"] == "TEXT_LAYER_OK"
      and _byfile["good.pdf"]["Required_Action"] == "CONFIRM_ON_CONTACT_SHEET",
      "%s" % _byfile["good.pdf"])
check("the one with no captions is not filed as the one that worked",
      _byfile["quiet2.pdf"]["Text_Backend_Status"] == "ZERO_CAPTION_CANDIDATES",
      _byfile["quiet2.pdf"]["Text_Backend_Status"])
# REVERT: file a NotReadable as INTAKE_FAILED, or as a clean read. The three
# outcomes need three different things done to them - a page render and a
# person, an install, and somebody looking at a stack trace - and collapsing
# them is what makes a ledger a list rather than a work queue.
check("and the one that is not a PDF is a row, not an exception",
      _byfile["notapdf.pdf"]["Text_Backend_Status"] == "NO_TEXT_LAYER",
      _byfile["notapdf.pdf"]["Text_Backend_Status"])
check("which asks for a render and a person, not for a reread",
      _byfile["notapdf.pdf"]["Required_Action"] == "RENDER_AND_INVENTORY_BY_EYE",
      _byfile["notapdf.pdf"]["Required_Action"])
check("and says what the backend actually complained about",
      "notapdf.pdf" in _byfile["notapdf.pdf"]["Detail"],
      _byfile["notapdf.pdf"]["Detail"][:120])
check("every row carries every ledger column",
      all(set(r) == set(CI.LEDGER_COLUMNS) for r in _ledger),
      "%s" % (set(_ledger[0]) ^ set(CI.LEDGER_COLUMNS)))
check("a walk whose ledger accounts for every file it was given is clean",
      not CI.ledger_problems(_ledger, expected_files=_pdfs)
      and _lcode == 0,
      "%s" % CI.ledger_problems(_ledger, expected_files=_pdfs))
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
         "LEDGER_ACTION_CONTRADICTS_COUNT"),
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
if _rledger["Page_Render_Status"] == "RENDERER_UNAVAILABLE":
    print("  SKIP the renderer: pdftoppm is not installed")
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
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
