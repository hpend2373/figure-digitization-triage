# -*- coding: utf-8 -*-
"""Scenarios for record_errorbar.py - the gate a person's answer goes through.

    python3 test_record_errorbar.py

The module's whole job is to refuse an answer that does not survive being
compared with the paper, so every scenario here is a way an answer can be
wrong: a quote spliced out of two sentences, a type the quote does not say, a
page nobody checked, a drop over a document that states its own dispersion.
The fixtures are real PDFs read through the intake's own backend, because the
comparison under test is against the text a backend actually hands over -
ligatures, broken glyphs and all - and not against a Python string.
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
import corpus_intake as CI                                       # noqa: E402
import record_errorbar as RE                                     # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_record_")

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



def column(x, top, *lines):
    return [(x, top - 14 * i, text) for i, text in enumerate(lines)]


# --- 원문 없이도 정해지는 것들 ------------------------------------------------
# 답의 모양과 인용문이 무엇을 말하는지는 PDF 어댑터 없이도 정해집니다. core CI
# 프로파일에는 백엔드가 하나도 없으므로, 그곳에서는 이 아래가 이 파일의 전부가
# 됩니다 - 멎는 대신에.
FLAT = RE.Source([
    (1, 0, 0, 100, 10, "Figure 1. Heart rate during head-down tilt."),
    (1, 0, 0, 100, 10, "The vertical bars in Figure 1 show the scatter."),
    (2, 0, 0, 100, 10,
     "Standard deviations are indicated by the vertical bars in Figure 1."),
    # PDF 배경이 `±`에 이름을 못 붙인 쪽. 뷰어에서는 "Values are means ± SE."
    # 로 보이고, 어댑터가 내주는 글자는 이것입니다.
    (3, 0, 0, 100, 10, "Values are means (cid:2) SE. Bars show the spread."),
])
SD_IN_FLAT = "Standard deviations are indicated by the vertical bars in Figure 1."


def codes(answer, source=FLAT):
    return [c for c, _m in RE.check_answer(answer, source)]


def plain(doc, code, quote="", page="", verified="1"):
    return {"Source_Document_ID": doc, "Dispersion_Type": code,
            "Errorbar_Definition_Source": quote, "Found_On_Page": page,
            "Verified_In_Source": verified}


check("사람이 확인한 답은 통과한다", codes(plain("D", "SD", SD_IN_FLAT, "2")) == [],
      codes(plain("D", "SD", SD_IN_FLAT, "2")))
check("표시가 없으면 통과하지 못한다",
      "NOT_VERIFIED_BY_PERSON" in codes(plain("D", "SD", SD_IN_FLAT, "2", verified="")))
check("표시는 kernel이 참으로 치는 말이면 된다",
      codes(plain("D", "SD", SD_IN_FLAT, "2", verified="yes")) == []
      and codes(plain("D", "SD", SD_IN_FLAT, "2", verified="TRUE")) == [])
# --- 사람이 승인한 관찰 (run2 2026-10-14) ------------------------------------
# 사람이 원문을 직접 확인하지 않은 답은, 누가 무엇을 보았고 누가 어디서
# 승인했는지를 모두 들고 올 때만 들어옵니다(`approval`). 셋 중 하나라도 비면
# 그 답은 되돌아볼 곳이 없는 답입니다.
APPROVED = {"Verified_By": "minyeop", "Observed_By": "Claude (PDF survey)",
            "Approval_Ref": "minyeop chat 2026-10-14"}
check("승인된 관찰은 통과한다", codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **APPROVED)) == [],
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **APPROVED)))
# REVERT: take an answer that names what looked but not where it was approved.
check("승인한 자리가 없으면 통과하지 못한다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **dict(APPROVED, Approval_Ref=""))) == ["APPROVAL_INCOMPLETE"])
check("본 것이 없으면 통과하지 못한다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **dict(APPROVED, Observed_By=""))) == ["APPROVAL_INCOMPLETE"])
check("본 것과 승인한 사람이 같으면 본 답이지 승인된 관찰이 아니다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **dict(APPROVED, Observed_By="minyeop"))) == ["OBSERVER_IS_APPROVER"])
# REVERT: let an approval through with nobody named as the approver. The record
# then says someone approved it, and not who.
check("누가 승인했는지 없으면 통과하지 못한다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2", verified="0"), **dict(APPROVED, Verified_By=""))) == ["UNATTRIBUTED"])
check("승인된 관찰도 인용문은 원문에서 다시 찾아진다",
      "QUOTE_NOT_IN_SOURCE" in codes(dict(plain("D", "SD", "Standard deviations are shown.", "2", verified="0"), **APPROVED)))

# --- 다른 요소의 정의를 빌린 답 (run2 2026-10-14 R9·R10) -------------------------
BORROW = {"Definition_Basis": "BORROWED", "Note": "Table 4 title; Fig. 3 bar lengths match the table's SD"}
check("빌린 정의는 Note와 함께면 통과한다", codes(dict(plain("D", "SD", SD_IN_FLAT, "2"), **BORROW)) == [],
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2"), **BORROW)))
# REVERT: borrow without saying from where. The assumption the record exists to
# keep is then nowhere.
check("어디서 빌렸는지 없으면 통과하지 못한다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2"), **dict(BORROW, Note=""))) == ["BORROWED_UNEXPLAINED"])
check("빌린 것이 처분이면 통과하지 못한다",
      codes(dict(plain("D", "DROP"), **BORROW)) == ["BORROWED_WITHOUT_DEFINITION"])
check("빌린 것이 '막대 없음'이면 통과하지 못한다",
      codes(dict(plain("D", "NO_ERRORBAR"), **BORROW)) == ["BORROWED_WITHOUT_DEFINITION"])
check("빌림의 이름은 정해진 것 하나뿐이다",
      codes(dict(plain("D", "SD", SD_IN_FLAT, "2"), **dict(BORROW, Definition_Basis="GUESSED"))) == ["BAD_DEFINITION_BASIS"])
check("빌린 인용문도 원문에서 다시 찾아진다",
      "QUOTE_NOT_IN_SOURCE" in codes(dict(plain("D", "SD", "Means (SD) of all tables.", "2"), **BORROW)))

# --- 그림에서 잰 정의 (2026-10-20 결정 D01) ------------------------------------
# 논문은 SD라고 하는데 그림의 막대가 개인 값의 SE와 맞는 경우. 인용문 자리는 잰 것의
# 기술이라 원문에서 찾지 않고, 대신 Note와 이름이 있어야 합니다.
MEASURE = {"Definition_Basis": "MEASURED", "Verified_By": "minyeop",
           "Note": "two independent checks, 22 cells, bar/SD median 0.453"}
_MSRC = "Measured on the figure: in 22 cells the bar is the SE of the five plotted values"
check("그림에서 잰 정의는 Note와 함께면 원문에 없어도 통과한다",
      codes(dict(plain("D", "SE", _MSRC, ""), **MEASURE)) == [], codes(dict(plain("D", "SE", _MSRC, ""), **MEASURE)))
check("  승인된 관찰로도 통과한다",
      codes(dict(plain("D", "SE", _MSRC, "", verified="0"), **dict(MEASURE, **APPROVED))) == [])
# REVERT: take a measured definition without saying how it was measured.
check("  잰 방법이 없으면 통과하지 못한다",
      codes(dict(plain("D", "SE", _MSRC, ""), **dict(MEASURE, Note=""))) == ["MEASURED_UNEXPLAINED"])
check("  잰 것의 기술이 없으면 통과하지 못한다",
      codes(dict(plain("D", "SE", "", ""), **MEASURE)) == ["NO_ERRORBAR_SOURCE"])
check("  누가 정했는지 없으면 통과하지 못한다",
      codes(dict(plain("D", "SE", _MSRC, ""), **dict(MEASURE, Verified_By=""))) == ["UNATTRIBUTED"])
check("  잰 것이 처분이면 통과하지 못한다",
      codes(dict(plain("D", "DROP"), **MEASURE)) == ["MEASURED_WITHOUT_DEFINITION"])
check("  잰 기술도 추정의 말이면 막힌다",
      "UNRESOLVED_ERRORBAR_DEFINITION" in codes(dict(plain("D", "SE", "The bars are probably SE", ""), **MEASURE)))
check("어휘 밖의 종류는 그 자리에서 멈춘다",
      codes(plain("D", "STDEV", SD_IN_FLAT, "2")) == ["BAD_DISPERSION_TYPE"])
check("추정하는 말은 harness의 이름으로 걸린다",
      "UNRESOLVED_ERRORBAR_DEFINITION"
      in codes(plain("D", "SD", "The bars are probably standard deviations.", "2")))
check("인용문 없는 종류는 걸린다",
      codes(plain("D", "SD", "", "2")) == ["NO_ERRORBAR_SOURCE"])
check("막대가 없다는 답만 인용문을 요구받지 않는다",
      codes(plain("D", "NO_ERRORBAR", "", "")) == [])
check("인용문이 고른 종류를 말하지 않으면 걸린다",
      codes(plain("D", "SD", "The vertical bars in Figure 1 show the scatter.", "1"))
      == ["QUOTE_DOES_NOT_SAY_TYPE"])
check("인용문이 다른 종류를 말하면 걸린다",
      "QUOTE_SAYS_ANOTHER_TYPE" in codes(plain("D", "SEM", SD_IN_FLAT, "2")))
# REVERT: `(cid:N)`을 낱말로 센다. 뷰어에서 그대로 긁어 온 진짜 문장이 원문에
# 없는 문장이 되고, 거부 문구는 "서로 다른 문장의 조각이 이어 붙었습니다"
# 입니다 - 정직하게 옮겨 적은 사람에게 지어냈다고 말하는 문. run2에서 인용문
# 41개 중 14개가 이것 하나로 거부됐고, 되살아난 14개는 전부 적어 낸 그 쪽에
# 있었습니다.
check("배경이 이름을 못 붙인 글자는 낱말로 세지 않는다",
      codes(plain("D", "SE", "Values are means ± SE.", "3")) == [],
      codes(plain("D", "SE", "Values are means ± SE.", "3")))
check("  그 글자를 그대로 적어 내도 같은 문장으로 본다",
      codes(plain("D", "SE", "Values are means (cid:2) SE.", "3")) == [],
      codes(plain("D", "SE", "Values are means (cid:2) SE.", "3")))
# 그리고 이것이 문을 열어 주는 것은 아닙니다 - 이어 붙인 인용문은 여전히
# 걸립니다. 낱말의 차례가 원문에 없기 때문입니다.
check("  그래도 이어 붙인 문장은 여전히 문서에 없다",
      codes(plain("D", "SE", "Values are means ± SE in Figure 1.", "3"))
      == ["QUOTE_NOT_IN_SOURCE"],
      codes(plain("D", "SE", "Values are means ± SE in Figure 1.", "3")))
check("서로 다른 문장의 조각을 이어 붙이면 문서에 없다",
      codes(plain("D", "SD",
                  "Standard deviations are indicated by the scatter.", "2"))
      == ["QUOTE_NOT_IN_SOURCE"])
check("곱슬따옴표와 줄바꿈 hyphen은 같은 문장으로 본다",
      codes(plain("D", "SD",
                  u"Standard \u201cdeviations\u201d are indi- cated by the "
                  u"vertical bars in Figure 1.", "2")) == [],
      codes(plain("D", "SD",
                  u"Standard \u201cdeviations\u201d are indi- cated by the "
                  u"vertical bars in Figure 1.", "2")))
check("쪽을 적지 않으면 걸린다", codes(plain("D", "SD", SD_IN_FLAT)) == ["PAGE_MISSING"])
check("틀린 쪽은 걸린다",
      codes(plain("D", "SD", SD_IN_FLAT, "1")) == ["QUOTE_NOT_ON_PAGE"])
check("아직 정하지 않은 답은 걸린다", codes(plain("D", RE.HOLD)) == ["HELD"])
check("못 찾았다면서 인용문을 달면 걸린다",
      "DROP_WITH_QUOTE" in codes(plain("D", RE.DROP, SD_IN_FLAT, "2")))


PDFS = os.path.join(ROOT, "pdfs")
RUN = os.path.join(ROOT, "run")
os.makedirs(PDFS)
os.makedirs(RUN)

# DOC_A: the definition is in the prose, in a sentence `document_statement`
# does not recognise - which is exactly why its rows are waiting for a person.
SD_LINE = "Standard deviations are indicated by the vertical bars in Figure 1."
SCATTER_LINE = "The vertical bars in Figure 1 show the scatter of the observations."
SEM_LINE = "Values in Figure 2 are given as standard errors of the mean."
minimal_pdf(os.path.join(PDFS, "a.pdf"), [
    column(60, 700,
           "Figure 1. Heart rate during head-down tilt.",
           "Figure 2. Stroke volume during head-down tilt.",
           SCATTER_LINE),
    column(60, 700,
           SD_LINE,
           SEM_LINE,
           "Subjects were 24 years of age at entry."),
])
# DOC_B: not one dispersion word in it. A drop here is a drop.
minimal_pdf(os.path.join(PDFS, "b.pdf"), [
    column(60, 700,
           "Figure 1. Cardiac output during tilt.",
           "Cardiac output rose during tilt in every participant."),
])
# DOC_C: the document says how its values are presented, in so many words.
minimal_pdf(os.path.join(PDFS, "c.pdf"), [
    column(60, 700,
           "Figure 1. Mean arterial pressure.",
           "Data are presented as means and standard deviations."),
])


def sha(name):
    h = hashlib.sha256()
    h.update(open(os.path.join(PDFS, name), "rb").read())
    return h.hexdigest()


minimal_pdf(os.path.join(PDFS, "d.pdf"), [
    column(60, 700,
           "Figure 1. Blood pressure.",
           "Bars are standard deviations of the group mean."),
])

# (Draft_ID, 문서, 파일, 그림, 쪽, 초안이 쓴 백엔드)
DRAFT = (
    ("DOC_A_D001", "DOC_A", "a.pdf", "FIG1", "1"),
    ("DOC_A_D002", "DOC_A", "a.pdf", "FIG2", "1"),
    ("DOC_B_D001", "DOC_B", "b.pdf", "FIG1", "1"),
    ("DOC_C_D001", "DOC_C", "c.pdf", "FIG1", "1"),
    ("DOC_D_D001", "DOC_D", "d.pdf", "FIG1", "1", "JATS_FIGURE_ELEMENTS"),
)
#: 대기 목록을 만든 뒤에 생긴 그림들 - 초안에는 있고 errorbar_unstated.csv에는 없습니다.
LATER = (
    ("DOC_A_D003", "DOC_A", "a.pdf", "FIG3", "1"),
    ("DOC_A_D004", "DOC_A", "a.pdf", "FIG4", "1"),
    ("DOC_B_D002", "DOC_B", "b.pdf", "FIG2", "1"),
    ("DOC_C_D002", "DOC_C", "c.pdf", "FIG2", "1"),
)
try:
    BACKEND = CI._default_backend()
except CI.BackendUnavailable:
    shutil.rmtree(ROOT, ignore_errors=True)
    print("  SKIP the PDF adapter: no text backend is installed here "
          "(pdfminer.six or poppler-utils); %d text-only scenarios ran" % PASSED[0])
    print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
    raise SystemExit(1 if FAILURES else 0)
with io.open(os.path.join(RUN, RE.DRAFT), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Draft_ID", "Source_Document_ID", "Source_File",
                "Source_File_SHA256", "Page", "Figure_Number",
                "Extraction_Method"])
    for row in DRAFT + LATER:
        did, doc, name, fig, page = row[:5]
        w.writerow([did, doc, name, sha(name), page, fig,
                    row[5] if len(row) > 5 else BACKEND])


def write_unstated(rows=DRAFT, path=None):
    path = path or os.path.join(RUN, RE.UNSTATED)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Source_Document_ID", "Draft_ID", "Page", "Figure_Number"])
        for row in rows:
            did, doc, _name, fig, page = row[:5]
            w.writerow([doc, did, page, fig])
    return path


write_unstated()


#: 사람이 논문을 본 날. 이 프로그램이 도는 날이 아닙니다 - 판정을 몇 주 뒤에
#: 옮겨 적는 일이 실제로 있고, 그때 오늘 날짜가 박히면 그 행은 언제 확인된
#: 것인지 알 수 없게 됩니다.
WHEN = "2026-08-30"


def answer(doc, code, quote="", page="", verified="1", **extra):
    row = {"Source_Document_ID": doc, "Dispersion_Type": code,
           "Errorbar_Definition_Source": quote, "Found_On_Page": page,
           "Verified_In_Source": verified, "Recorded_At": WHEN}
    row.update(extra)
    return row


def run(answers, decisions=None, **kw):
    """A fresh decisions file per scenario, so one scenario cannot pass
    because another one wrote the row first."""
    out = os.path.join(ROOT, decisions or ("d%d.csv" % len(os.listdir(ROOT))))
    if decisions and os.path.exists(out):
        pass
    return RE.record(RUN, answers, PDFS, WHEN, out_path=out,
                     log=lambda *_a: None, **kw) + (out,)


def problems_of(refused):
    return [code for _who, probs in refused for code, _msg in probs]


# --- the answer that survives ----------------------------------------------
_w, _r, _path, _out = run([answer("DOC_A", "SD", SD_LINE, "2")])
check("확인된 답은 그 문서의 미정 행 전부에 적힌다",
      sorted(r["Draft_ID"] for r in _w) == ["DOC_A_D001", "DOC_A_D002"],
      [r["Draft_ID"] for r in _w])
check("적힌 행은 사람이 고른 종류를 그대로 든다",
      {r["Dispersion_Type"] for r in _w} == {"SD"})
check("인용문은 사람이 준 그대로 적힌다",
      {r["Errorbar_Definition_Source"] for r in _w} == {SD_LINE})
check("Recorded_At은 --when이 준 날이지 오늘이 아니다",
      {r["Recorded_At"] for r in _w} == {WHEN}
      and WHEN != __import__("datetime").date.today().isoformat(),
      [r["Recorded_At"] for r in _w])
check("Verified_By_Person은 사람이 표시했을 때만 1이 된다",
      {r["Verified_By_Person"] for r in _w} == {"1"})
_disk = list(csv.DictReader(io.open(_out, encoding="utf-8")))
check("적힌 것은 파일에도 그대로 있다",
      sorted(r["Draft_ID"] for r in _disk) == ["DOC_A_D001", "DOC_A_D002"])
check("파일의 열은 판정 파일의 열이다",
      list(csv.reader(io.open(_out, encoding="utf-8")))[0] == list(RE.FIELDS))

# --- who says so -----------------------------------------------------------
_w, _r, _path, _out = run([answer("DOC_A", "SD", SD_LINE, "2", verified="")])
# REVERT: accept an answer nobody ticked. The one thing this gate exists to
# carry - that a person opened the paper - stops being carried, silently.
check("직접 확인 표시가 없으면 적지 않는다",
      problems_of(_r) == ["NOT_VERIFIED_BY_PERSON"] and _w == [],
      problems_of(_r))
check("거절된 답은 파일에 한 줄도 남기지 않는다",
      list(csv.DictReader(io.open(_out, encoding="utf-8"))) == [])

# --- the vocabulary --------------------------------------------------------
_w, _r, _p, _o = run([answer("DOC_A", "STDEV", SD_LINE, "2")])
check("계획서가 받지 않는 종류는 거절한다",
      problems_of(_r) == ["BAD_DISPERSION_TYPE"], problems_of(_r))
check("어휘는 kernel의 것이지 이 파일에 손으로 적은 것이 아니다",
      RE.DISPERSION_TYPES == tuple(__import__("kernel").FIG_DISPERSION_TYPES))

_w, _r, _p, _o = run([answer("DOC_A", "", SD_LINE, "2")])
check("종류를 고르지 않은 답도 거절한다",
      problems_of(_r) == ["BAD_DISPERSION_TYPE"], problems_of(_r))

# --- the hedge -------------------------------------------------------------
_hedged = "The bars are probably standard deviations."
_w, _r, _p, _o = run([answer("DOC_A", "SD", _hedged, "2")])
check("추정하는 말이 든 인용문은 harness가 쓰는 이름으로 거절한다",
      "UNRESOLVED_ERRORBAR_DEFINITION" in problems_of(_r), problems_of(_r))

# --- the quote itself ------------------------------------------------------
_w, _r, _p, _o = run([answer("DOC_A", "SD", "", "2")])
check("인용문 없는 SD는 거절한다",
      problems_of(_r) == ["NO_ERRORBAR_SOURCE"], problems_of(_r))

_w, _r, _p, _o = run([answer("DOC_A", "NO_ERRORBAR", "", "")])
check("막대가 없다는 답은 인용문 없이도 적힌다",
      len(_w) == 2 and _r == [], (len(_w), problems_of(_r)))

_w, _r, _p, _o = run([answer("DOC_A", "SD", SCATTER_LINE, "1")])
check("인용문이 고른 종류를 말하지 않으면 거절한다",
      problems_of(_r) == ["QUOTE_DOES_NOT_SAY_TYPE"], problems_of(_r))

_w, _r, _p, _o = run([answer("DOC_A", "SEM", SD_LINE, "2")])
check("인용문이 다른 종류를 말하면 그 이름을 대며 거절한다",
      "QUOTE_SAYS_ANOTHER_TYPE" in problems_of(_r)
      and "SD" in " ".join(m for _w2, ps in _r for _c, m in ps),
      problems_of(_r))

# THE SPLICE. Both halves are in the document, in different sentences; the
# sentence as quoted is not. Two of the twenty-four quotes an assistant
# returned for this corpus were exactly this shape.
_splice = "Standard deviations are indicated by the scatter of the observations."
_w, _r, _p, _o = run([answer("DOC_A", "SD", _splice, "2")])
check("서로 다른 문장을 이어 붙인 인용문은 문서에 없으므로 거절한다",
      problems_of(_r) == ["QUOTE_NOT_IN_SOURCE"], problems_of(_r))

_w, _r, _p, _o = run([answer("DOC_A", "SD",
                             u"Standard “deviations” are indi- "
                             u"cated by the vertical bars in Figure 1.", "2")])
# REVERT: compare the text as typed. Every quote a person pastes out of a PDF
# viewer is then refused for a curly quote or a line-break hyphen, and the
# gate becomes the thing people work around.
check("곱슬따옴표와 줄바꿈 hyphen은 같은 문장으로 본다",
      len(_w) == 2 and _r == [], (len(_w), problems_of(_r)))

# --- the page --------------------------------------------------------------
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "")])
check("쪽을 적지 않으면 거절하고 어느 쪽인지 말해 준다",
      problems_of(_r) == ["PAGE_MISSING"]
      and "2" in " ".join(m for _w2, ps in _r for _c, m in ps),
      problems_of(_r))

_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "1")])
check("틀린 쪽을 적으면 거절하고 맞는 쪽을 말해 준다",
      problems_of(_r) == ["QUOTE_NOT_ON_PAGE"]
      and "2" in " ".join(m for _w2, ps in _r for _c, m in ps),
      problems_of(_r))

# --- the drop --------------------------------------------------------------
_w, _r, _p, _o = run([answer("DOC_B", RE.DROP, "", "")])
check("낱말조차 없는 문서의 \"못 찾음\"은 적힌다",
      len(_w) == 1 and _r == [], (len(_w), problems_of(_r)))

_w, _r, _p, _o = run([answer("DOC_C", RE.DROP, "", "")])
# REVERT: record the drop. A row whose definition the document states plainly
# is thrown out of the pool, and nothing will ever bring it back.
check("문서가 스스로 정의를 말하는데 못 찾았다고 하면 거절한다",
      problems_of(_r) == ["DROP_BUT_DOCUMENT_STATES"], problems_of(_r))
check("거절하면서 그 문장을 보여 준다",
      "standard deviations" in " ".join(m for _w2, ps in _r
                                        for _c, m in ps).lower(),
      [m for _w2, ps in _r for _c, m in ps])

_w, _r, _p, _o = run([answer("DOC_B", RE.DROP, SD_LINE, "1")])
check("못 찾았다면서 인용문을 달면 거절한다",
      "DROP_WITH_QUOTE" in problems_of(_r), problems_of(_r))

_w, _r, _p, _o = run([answer("DOC_B", RE.HOLD, "", "")])
check("아직 정하지 않은 답은 적지 않는다",
      problems_of(_r) == ["HELD"] and _w == [], problems_of(_r))

# --- what is already settled ----------------------------------------------
_w1, _r1, _p1, _out1 = run([answer("DOC_A", "SD", SD_LINE, "2")],
                           decisions="settled.csv")
_w2, _r2, _p2 = RE.record(RUN, [answer("DOC_A", "SD", SD_LINE, "2")],
                          PDFS, "2026-08-31", out_path=_out1,
                          log=lambda *_a: None)
check("이미 판정된 행은 덮지 않는다",
      problems_of(_r2) == ["ALREADY_DECIDED", "ALREADY_DECIDED"], problems_of(_r2))
_disk = list(csv.DictReader(io.open(_out1, encoding="utf-8")))
check("덮지 않은 판정은 파일에 그대로 남는다",
      {r["Dispersion_Type"] for r in _disk} == {"SD"},
      [r["Dispersion_Type"] for r in _disk])
_w3, _r3, _p3 = RE.record(RUN, [answer("DOC_A", "SEM", SEM_LINE, "2")], PDFS,
                          "2026-08-31", out_path=_out1, replace=True,
                          log=lambda *_a: None)
_disk = list(csv.DictReader(io.open(_out1, encoding="utf-8")))
check("--replace로 부르면 덮는다",
      {r["Dispersion_Type"] for r in _disk} == {"SEM"},
      [r["Dispersion_Type"] for r in _disk])
check("덮어도 행이 늘지 않는다", len(_disk) == 2, len(_disk))

# 다른 문서의 판정은 건드리지 않는다.
_wb, _rb, _pb = RE.record(RUN, [answer("DOC_B", RE.DROP, "", "")], PDFS,
                          "2026-08-31", out_path=_out1, log=lambda *_a: None)
_disk = list(csv.DictReader(io.open(_out1, encoding="utf-8")))
check("새 판정은 먼저 있던 판정에 더해진다",
      sorted(r["Draft_ID"] for r in _disk)
      == ["DOC_A_D001", "DOC_A_D002", "DOC_B_D001"],
      [r["Draft_ID"] for r in _disk])

# --- an approved observation, a borrowed definition, one figure -------------
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", verified="0", **APPROVED)])
check("승인된 관찰은 Verified_By_Person=0으로, 본 것·승인한 사람·자리와 함께 적힌다",
      _r == [] and {(r["Verified_By_Person"], r["Verified_By"], r["Observed_By"], r["Approval_Ref"]) for r in _w}
      == {("0", "minyeop", "Claude (PDF survey)", "minyeop chat 2026-10-14")}, (problems_of(_r), _w[:1]))
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", **APPROVED)])
check("사람이 직접 확인한 답에는 승인 칸이 남지 않는다",
      {(r["Verified_By_Person"], r["Observed_By"], r["Approval_Ref"]) for r in _w} == {("1", "", "")}, _w[:1])
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", **BORROW)])
check("빌린 정의는 Definition_Basis=BORROWED로 적힌다",
      {r["Definition_Basis"] for r in _w} == {"BORROWED"} and len(_w) == 2, _w[:1])
_w, _r, _p = RE.record(RUN, [answer("DOC_A", "SE", _MSRC, "", verified="", Draft_ID="DOC_A_D002",
                                     **dict(MEASURE, **APPROVED))], os.path.join(ROOT, "no_pdfs_here"), WHEN,
                       out_path=os.path.join(ROOT, "measured.csv"), log=lambda *_a: None)
# REVERT: ask for the source of a measured answer. The figure's measurement is
# then refused for want of a document it never quoted.
check("그림에서 잰 답은 원문이 없어도 MEASURED로, 승인 칸과 함께 적힌다",
      _r == [] and [(r["Draft_ID"], r["Definition_Basis"], r["Verified_By_Person"]) for r in _w]
      == [("DOC_A_D002", "MEASURED", "0")], (problems_of(_r), _w[:1]))
_w, _r, _p, _o = run([answer("DOC_A", "NO_ERRORBAR", Draft_ID="DOC_A_D002")])
# REVERT: ignore Draft_ID. One figure's answer then lands on every figure of
# the paper, and a box plot takes the bar charts' definition, or the reverse.
check("그림 하나의 답은 그 그림에만 적힌다", [r["Draft_ID"] for r in _w] == ["DOC_A_D002"], [r["Draft_ID"] for r in _w])
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2"), answer("DOC_A", "NO_ERRORBAR", Draft_ID="DOC_A_D002")])
check("문서의 답과 그림의 답이 함께면, 그 그림은 그림의 답을 받는다",
      sorted((r["Draft_ID"], r["Dispersion_Type"]) for r in _w) == [("DOC_A_D001", "SD"), ("DOC_A_D002", "NO_ERRORBAR")],
      sorted((r["Draft_ID"], r["Dispersion_Type"]) for r in _w))
_w, _r, _p, _o = run([answer("DOC_A", "NO_ERRORBAR", Draft_ID="DOC_A_D009")])
check("기다리는 목록에 없는 그림은 거절한다", problems_of(_r) == ["NOT_PENDING"] and _w == [], problems_of(_r))
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2"), answer("DOC_A", "NO_ERRORBAR")])
# REVERT: let two answers for one place both through. The file then holds two
# rows for one figure, and which one a plan reads depends on the order.
check("한 자리에 답이 둘이면 둘 다 거절한다", problems_of(_r) == ["ANSWERED_TWICE", "ANSWERED_TWICE"] and _w == [], problems_of(_r))

# --- what the plan is waiting for (run2 2026-10-17) -------------------------
PLANS = os.path.join(ROOT, "plans")
os.makedirs(PLANS)
with io.open(os.path.join(PLANS, RE.PLAN_FIGURES), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Draft_ID", "Figure_Number", "Page", "Dispersion_Type", "Errorbar_Source_Kind"])
    w.writerow(["DOC_A_D001", "FIG1", "1", "", ""])           # also in the old list - the old list's row stands
    w.writerow(["DOC_A_D003", "FIG3", "1", "", ""])           # opened after the list was made, no definition anywhere
    w.writerow(["DOC_A_D004", "FIG4", "1", "SD", "DECISION"])  # a person already decided
    w.writerow(["DOC_B_D002", "FIG2", "1", "NO_ERRORBAR", "DOCUMENT"])
    w.writerow(["DOC_C_D002", "FIG2", "1", "CI95", "CAPTION"])  # the rule read a regression band as the bars
    w.writerow(["DOC_Z_D001", "FIG1", "1", "", ""])           # not in this draft
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", Draft_ID="DOC_A_D003")])
check("계획서를 주지 않으면 목록 밖의 그림은 그대로 NOT_PENDING", problems_of(_r) == ["NOT_PENDING"], problems_of(_r))
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", Draft_ID="DOC_A_D003")], plans=PLANS)
# REVERT: read the old list only. A figure opened after it was made can never get a definition.
check("계획서가 정의를 기다리는 그림은 그림의 답으로 적힌다", [(r["Draft_ID"], r["Figure_Number"]) for r in _w] == [("DOC_A_D003", "FIG3")]
      and _r == [], (problems_of(_r), _w))
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2", Draft_ID="DOC_A_D001")], plans=PLANS)
# REVERT: add the plan's row for a figure the old list already has. The figure is then pending twice and written twice.
check("옛 목록에도 있는 그림은 한 번만 적힌다", [r["Draft_ID"] for r in _w] == ["DOC_A_D001"], [r["Draft_ID"] for r in _w])
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2")], plans=PLANS)
# REVERT: let a document's answer reach the plan's figures. A figure whose caption the rule read right takes another figure's answer.
check("문서의 답은 계획서에서 온 그림에 닿지 않는다", sorted(r["Draft_ID"] for r in _w) == ["DOC_A_D001", "DOC_A_D002"], [r["Draft_ID"] for r in _w])
_w, _r, _p, _o = run([answer("DOC_A", "SEM", SEM_LINE, "2", Draft_ID="DOC_A_D004")], plans=PLANS)
check("사람이 이미 정한 그림은 기다리는 그림이 아니다", problems_of(_r) == ["NOT_PENDING"], problems_of(_r))
_w, _r, _p, _o = run([answer("DOC_Z", "SD", SD_LINE, "2", Draft_ID="DOC_Z_D001")], plans=PLANS)
check("초안에 없는 그림은 계획서에 있어도 받지 않는다", problems_of(_r) == ["NOT_PENDING"], problems_of(_r))
FIX = answer("DOC_C", "SD", "Data are presented as means and standard deviations.", "1", Draft_ID="DOC_C_D002",
             Note="the caption's 95% CI is the regression band; the bars are SD per the statistics section")
_w, _r, _p, _o = run([FIX], plans=PLANS)
check("규칙의 읽기를 고치는 답은 까닭과 함께 적힌다", [(r["Draft_ID"], r["Dispersion_Type"]) for r in _w] == [("DOC_C_D002", "SD")]
      and "regression band" in _w[0]["Note"], (problems_of(_r), _w))
_w, _r, _p, _o = run([dict(FIX, Note="")], plans=PLANS)
# REVERT: take a correction without its reason. The record then holds two readings and nothing says which is right.
check("까닭 없는 고침은 적지 않는다", problems_of(_r) == ["CORRECTION_UNEXPLAINED"] and _w == [], problems_of(_r))
_w, _r, _p, _o = run([answer("DOC_B", "NO_ERRORBAR", Draft_ID="DOC_B_D002", Note="no bars")], plans=PLANS)
# REVERT: write an answer the rule already read. It looks like a person's decision and changes nothing.
check("규칙의 읽기와 같은 답은 적을 것이 없다", problems_of(_r) == ["SAME_AS_READING"] and _w == [], problems_of(_r))
_w, _r, _p, _o = run([answer("DOC_B", RE.DROP, Draft_ID="DOC_B_D002", Note="bars, no definition")], plans=PLANS)
check("규칙의 읽기와 다른 처분도 고침이다", [(r["Draft_ID"], r["Dispersion_Type"]) for r in _w] == [("DOC_B_D002", "DROP")], problems_of(_r))

# --- what is not being asked ----------------------------------------------
_w, _r, _p, _o = run([answer("DOC_Z", "SD", SD_LINE, "2")])
check("기다리는 목록에 없는 문서는 거절한다",
      problems_of(_r) == ["NOT_PENDING"], problems_of(_r))

# --- the file the person hands over ---------------------------------------
try:
    RE.record(RUN, [{"Source_Document_ID": "DOC_A", "Dispersion_Type": "SD"}],
              PDFS, "2026-09-05", out_path=os.path.join(ROOT, "x.csv"),
              log=lambda *_a: None)
    _stopped = ""
except SystemExit as exc:
    _stopped = str(exc)
check("검토 페이지가 내려준 파일이 아니면 멎고 없는 열을 댄다",
      "Errorbar_Definition_Source" in _stopped and "Verified_In_Source" in _stopped,
      _stopped)

# --- the file the draft read ----------------------------------------------
_backup = open(os.path.join(PDFS, "a.pdf"), "rb").read()
minimal_pdf(os.path.join(PDFS, "a.pdf"),
            [column(60, 700, "A different rendering of the same paper.")])
_w, _r, _p, _o = run([answer("DOC_A", "SD", SD_LINE, "2")])
# REVERT: read whatever file is there. The pages the person cited are then
# not the pages of the document the draft measured, and nothing says so.
check("초안이 읽은 파일이 아니면 대조하지 않고 거절한다",
      "SOURCE_UNREADABLE" in problems_of(_r), problems_of(_r))
open(os.path.join(PDFS, "a.pdf"), "wb").write(_backup)

os.rename(os.path.join(PDFS, "b.pdf"), os.path.join(PDFS, "b.hidden"))
_w, _r, _p, _o = run([answer("DOC_B", RE.DROP, "", "")])
check("원문이 없으면 못 찾았다는 답도 적지 않는다",
      "SOURCE_UNREADABLE" in problems_of(_r), problems_of(_r))
os.rename(os.path.join(PDFS, "b.hidden"), os.path.join(PDFS, "b.pdf"))

# THE BACKEND THE DRAFT USED, not the one this machine happens to prefer.
# DOC_D's intake came from a JATS full text: it has figures and captions and
# no page coordinates at all. Opening its PDF with the default reader would
# produce a page number that is not the page the draft is about.
_w, _r, _p, _o = run([answer("DOC_D", "SD",
                             "Bars are standard deviations of the group mean.",
                             "1")])
check("초안이 쓴 백엔드로 읽지 못하면 다른 것으로 바꿔 읽지 않는다",
      "SOURCE_UNREADABLE" in problems_of(_r) and _w == [], problems_of(_r))

# ---------------------------------------------------------------------------
shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
