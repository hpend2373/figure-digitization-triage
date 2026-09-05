# -*- coding: utf-8 -*-
"""사람이 찾아온 오차 정의를 파이프라인에 넣는 문.

    python3 record_errorbar.py --run RUN --answers errorbar_found.csv \
                               --pdf-root ~/Downloads/spacecv_fulltext_pdfs

검토 페이지(`errorbar_review_page.py`)가 내려주는 답 CSV를 받아
`errorbar_decisions.csv`로 옮깁니다. 옮기기 전에 답을 원문과 대조합니다.

이 문이 있는 이유는 하나입니다. 이 자리에서 틀리면 SD와 SE를 맞바꾸는 것이고,
그러면 메타분석 가중치가 sqrt(n)만큼 틀립니다 - 그리고 그 틀림은 값이 다 뽑히고
풀링이 끝난 다음에야, 그것도 아무 표시 없이 드러납니다. 어시스턴트가 만들어
보낸 24개 인용문을 사람이 대조했을 때 둘이 원문에 없는 이어붙이기였습니다.
사람이 직접 옮겨 적어도 같은 일이 일어납니다. 그래서 모든 인용문은 문서에서
다시 찾아집니다.

이 모듈은 판정하지 않습니다. 정의를 고르는 것도, 못 찾았다고 정하는 것도
사람입니다. 이 모듈이 하는 일은 사람이 고른 답이 사람이 댄 근거와 맞는지
보는 것뿐이고, 맞지 않으면 그 행을 적지 않습니다.
"""
import argparse
import csv
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import corpus_intake as CI                                        # noqa: E402
import caption_fulltext as CF                                     # noqa: E402
import kernel                                                     # noqa: E402

DRAFT = "figure_intake_draft.csv"
UNSTATED = "errorbar_unstated.csv"
DECISIONS = "errorbar_decisions.csv"

#: 계획서가 실제로 받는 분산 종류. `kernel`에서 가져옵니다 - 여기에 손으로
#: 적어 두면 kernel이 바뀔 때 이 문만 옛 어휘를 받아들이게 됩니다.
DISPERSION_TYPES = tuple(kernel.FIG_DISPERSION_TYPES)

#: 분산 종류가 아닌 처분들. 값을 읽지 않고 행을 어디로 보낼지만 정합니다.
DROP = "DROP"                # 정의를 못 찾음 - 풀에서 뺌
NOT_DATA = "NOT_DATA"        # 데이터 그림이 아님
HOLD = "HOLD"                # 아직 정하지 않음 - 적지 않음
DISPOSITIONS = (DROP, NOT_DATA, HOLD)

#: 사람이 고른 종류를 인용문이 실제로 말하는지 보는 자리. `caption_fulltext`의
#: 것을 그대로 쓰되 `CI`를 계획서의 이름인 `CI95`로 옮기고, 그 다섯이 다루지
#: 않는 `RANGE`만 여기서 더합니다.
CLAIM = dict((("CI95" if code == "CI" else code), rx)
             for code, rx in CF.DEFINITIONS)
CLAIM["RANGE"] = re.compile(r"\brange[sd]?\b|\bminimum\s+(?:and|to)\s+maximum\b"
                            r"|\bmin(?:imum)?\s*(?:[-–—]|to)\s*max(?:imum)?\b",
                            re.I)

FIELDS = ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page",
          "Dispersion_Type", "Errorbar_Definition_Source", "Found_On_Page",
          "Verified_By_Person", "Recorded_Via", "Recorded_At", "Note")

#: 답 CSV가 반드시 들고 와야 하는 열. 없는 열은 빈칸이 아니라 다른 파일이라는
#: 뜻입니다 - 검토 페이지가 아닌 무언가를 먹이면 여기서 멎습니다.
ANSWER_REQUIRED = ("Source_Document_ID", "Dispersion_Type",
                   "Errorbar_Definition_Source", "Verified_In_Source")

_WORD = re.compile(r"[^0-9a-z]+")
_HYPHEN_BREAK = re.compile(r"([a-z])-\s+([a-z])", re.I)
#: 인쇄용 글자들. PDF 뷰어에서 긁으면 따라오고, 낱말 사이에 끼면 낱말이
#: 붙어 있지 않은 것처럼 보입니다 - `Standard "deviations"`가 `standard\s+
#: deviations`와 어긋나는 것이 그것입니다.
_TYPOGRAPHY = {u"\u201c": " ", u"\u201d": " ", u"\u2018": " ", u"\u2019": "'",
               u"\u00ab": " ", u"\u00bb": " ", u"\u2013": "-", u"\u2014": "-",
               u"\u2212": "-"}


def _soft(text):
    """문장을 규칙에 걸어 보기 전의 모양. 글자는 남기고 인쇄용 기호만 없앱니다.

    마침표는 남습니다 - `S.D.`와 `S.E.M.`이 그 마침표로 알아보아지기 때문에,
    낱말만 남기는 `_key`로는 이 검사를 할 수 없습니다.
    """
    flat = CF._norm(text)
    for glyph, plain in _TYPOGRAPHY.items():
        flat = flat.replace(glyph, plain)
    flat = _HYPHEN_BREAK.sub(r"\1\2", flat)
    return " ".join(flat.split())


def _key(text):
    """문장을 비교할 수 있는 모양으로. 낱말과 그 차례만 남깁니다.

    사람은 PDF 뷰어에서 문장을 긁어 옵니다. 그 과정에서 곱슬따옴표가 곧은
    것으로, en dash가 hyphen으로, `±`가 깨진 글꼴에서는 숫자 6으로 바뀝니다.
    줄바꿈 자리의 hyphen도 붙습니다. 그것들 때문에 진짜 원문을 거부하면 이 문은
    사람이 우회하는 문이 되고, 우회되는 문은 없느니만 못합니다.

    낱말의 차례는 남습니다. 서로 다른 문장에서 조각을 떼어 이어 붙인 인용문은
    그 차례가 원문에 없으므로 여전히 걸립니다 - 이 문이 실제로 잡아야 하는 것이
    그것입니다.
    """
    flat = CF._norm(text).lower()
    flat = _HYPHEN_BREAK.sub(r"\1\2", flat)
    return " ".join(_WORD.sub(" ", flat).split())


def hedge_in(text):
    """인용문이 논문의 진술이 아니라 추정을 담고 있으면 그 표식."""
    up = _soft(text).upper()
    for marker in kernel.FIG_UNRESOLVED_MARKERS:
        if marker in up:
            return marker
    return ""


def is_true(value):
    return str(value or "").strip().upper() in kernel.FIG_BOOL_TRUE


class Source(object):
    """한 문서의 본문 - 쪽별로, 그리고 통째로."""

    def __init__(self, blocks):
        self.by_page = {}
        for page, _x0, _y0, _x1, _y1, text in blocks:
            self.by_page.setdefault(str(page), []).append(text)
        self.pages = dict((p, _key(" ".join(t))) for p, t in self.by_page.items())
        self.whole = " ".join(self.pages[p] for p in sorted(self.pages))
        self.blocks = blocks

    def holds(self, quote):
        return _key(quote) in self.whole

    def page_of(self, quote):
        want = _key(quote)
        return sorted(p for p, text in self.pages.items() if want in text)


def check_answer(answer, source, pending_pages=()):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다.

    문제는 코드와 사람이 읽을 말로 됩니다. 코드만 내면 사람은 무엇을 고쳐야
    하는지 모르고, 말만 내면 시나리오가 무엇을 붙잡는지 모릅니다.
    """
    problems = []
    doc = (answer.get("Source_Document_ID") or "").strip()
    code = (answer.get("Dispersion_Type") or "").strip().upper()
    quote = (answer.get("Errorbar_Definition_Source") or "").strip()
    page = (answer.get("Found_On_Page") or "").strip()

    # 사람이 직접 확인했다고 말하지 않은 답은 답이 아닙니다. 이 문이 지키는
    # 것은 값의 모양이 아니라 "누가 보았는가"이고, 그것은 에이전트가 대신
    # 채울 수 없습니다.
    if not is_true(answer.get("Verified_In_Source")):
        problems.append(("NOT_VERIFIED_BY_PERSON",
                         "검토 페이지에서 \"직접 확인했습니다\"를 표시하지 "
                         "않았습니다. 표시가 없는 답은 적지 않습니다."))

    if code in DISPOSITIONS:
        pass
    elif code not in DISPERSION_TYPES:
        problems.append(("BAD_DISPERSION_TYPE",
                         "%r은 계획서가 받는 값이 아닙니다. 받는 값: %s"
                         % (code or "(빈칸)",
                            ", ".join(DISPERSION_TYPES + DISPOSITIONS))))
        return problems

    marker = hedge_in(quote)
    if marker:
        problems.append(("UNRESOLVED_ERRORBAR_DEFINITION",
                         "인용문에 \"%s\"가 들어 있습니다. 그것은 논문의 진술이 "
                         "아니라 추정이고, harness가 같은 이름으로 거부합니다."
                         % marker))

    if code == HOLD:
        problems.append(("HELD", "아직 정하지 않은 답입니다."))
        return problems

    if code in (DROP, NOT_DATA):
        if quote:
            problems.append(("%s_WITH_QUOTE" % code,
                             "정의를 못 찾았다고 하면서 인용문을 달았습니다. "
                             "둘 중 하나만 참입니다."))
        # 못 찾았다는 답을, 문서에 대고 한 번 더 봅니다. 문서가 스스로
        # 말하고 있는데 못 찾았다고 적으면 그 행은 되살릴 수 없게 버려집니다.
        if source is not None and code == DROP:
            found, sentence, where = CF.document_statement(source.blocks)
            if found:
                problems.append(("DROP_BUT_DOCUMENT_STATES",
                                 "%s쪽이 \"%s\"라고 말합니다 (%s). 정말 못 "
                                 "찾은 것인지 다시 보십시오."
                                 % (where, sentence[:120], found)))
        return problems

    if code == "NO_ERRORBAR":
        # 막대가 없다는 것은 그림을 본 사람의 말이지 문장이 아닙니다.
        # 인용문을 요구하지 않습니다.
        return problems

    if not quote:
        problems.append(("NO_ERRORBAR_SOURCE",
                         "%s이라고 적으려면 논문이 그렇게 말한 문장이 있어야 "
                         "합니다. 빈칸은 harness가 같은 이름으로 거부합니다."
                         % code))
        return problems

    rx = CLAIM.get(code)
    if rx is not None and not rx.search(_soft(quote)):
        problems.append(("QUOTE_DOES_NOT_SAY_TYPE",
                         "%s을 골랐는데 인용한 문장은 %s을 말하지 않습니다."
                         % (code, code)))
    other = [name for name, pat in sorted(CLAIM.items())
             if name != code and pat.search(_soft(quote))]
    if other:
        problems.append(("QUOTE_SAYS_ANOTHER_TYPE",
                         "인용한 문장은 %s을 말합니다. %s을 고른 근거가 이 "
                         "문장이라면 둘 중 하나가 틀렸습니다."
                         % (", ".join(other), code)))

    if source is None:
        problems.append(("SOURCE_UNREADABLE",
                         "%s의 원문을 읽지 못해 인용문을 대조하지 못했습니다."
                         % doc))
        return problems

    if not source.holds(quote):
        problems.append(("QUOTE_NOT_IN_SOURCE",
                         "이 문장은 문서에 없습니다. 낱말이 바뀌었거나, 서로 "
                         "다른 문장의 조각이 이어 붙었습니다."))
        return problems

    if not page:
        problems.append(("PAGE_MISSING",
                         "쪽을 적지 않았습니다. 인용문은 %s쪽에 있습니다."
                         % ", ".join(source.page_of(quote))))
    elif page not in source.page_of(quote):
        problems.append(("QUOTE_NOT_ON_PAGE",
                         "%s쪽이라고 적었는데 이 문장은 %s쪽에 있습니다."
                         % (page, ", ".join(source.page_of(quote)) or "어느 쪽도 아닌")))
    return problems


def load_pending(run):
    """{문서: [미정 행]} - 아직 정의가 없는 행들만."""
    path = os.path.join(run, UNSTATED)
    pending = {}
    for row in csv.DictReader(io.open(path, encoding="utf-8")):
        pending.setdefault(row["Source_Document_ID"], []).append(row)
    return pending


def load_decisions(run, path=None):
    path = path or os.path.join(run, DECISIONS)
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8")))


def read_source(run, doc, pdf_root):
    """(Source, 실패 사유). 초안이 쓴 백엔드로, 초안이 읽은 그 파일을."""
    draft = csv.DictReader(io.open(os.path.join(run, DRAFT), encoding="utf-8"))
    rows = [r for r in draft if r["Source_Document_ID"] == doc]
    if not rows:
        return None, "초안에 %s가 없습니다" % doc
    name = (rows[0].get("Source_File") or "").strip()
    backend = (rows[0].get("Extraction_Method") or "").strip() or None
    want = (rows[0].get("Source_File_SHA256") or "").strip().lower()
    path = CF.resolve_source(pdf_root, name) if name else None
    if path is None:
        return None, "%s를 찾지 못했습니다" % name
    # 초안이 읽은 파일과 다른 파일이면, 그 쪽 번호는 이 draft의 쪽이 아닙니다.
    if want and CF.sha256_of(path) != want:
        return None, "%s의 해시가 초안과 다릅니다" % name
    try:
        return Source(CI.text_blocks(path, backend=backend)), ""
    except Exception as exc:                                     # noqa: BLE001
        return None, "%s를 읽지 못했습니다 (%s)" % (name, type(exc).__name__)


def record(run, answers, pdf_root, when, out_path=None, via="REVIEW_PAGE",
           replace=False, log=print):
    """(적힌 행, 거절된 (문서, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 검토 페이지가 내려준 "
                         "파일이 맞습니까?" % ", ".join(missing))
    pending = load_pending(run)
    out_path = out_path or os.path.join(run, DECISIONS)
    existing = load_decisions(run, out_path)
    settled = set(r["Draft_ID"] for r in existing)

    written, refused = [], []
    for answer in answers:
        doc = (answer.get("Source_Document_ID") or "").strip()
        rows = pending.get(doc)
        if not rows:
            refused.append((doc, [("NOT_PENDING",
                                   "%s는 정의를 기다리는 문서 목록에 없습니다. "
                                   "이미 정해졌거나, 이 run의 문서가 "
                                   "아닙니다." % doc)]))
            continue
        source, why = read_source(run, doc, pdf_root)
        problems = check_answer(answer, source)
        if source is None and why and not any(c == "SOURCE_UNREADABLE"
                                              for c, _m in problems):
            problems.append(("SOURCE_UNREADABLE", why))
        if problems:
            refused.append((doc, problems))
            continue
        code = (answer.get("Dispersion_Type") or "").strip().upper()
        for row in rows:
            if row["Draft_ID"] in settled and not replace:
                refused.append((row["Draft_ID"],
                                [("ALREADY_DECIDED",
                                  "이 행은 이미 판정되어 있습니다. 바꾸려면 "
                                  "--replace로 다시 부르십시오.")]))
                continue
            written.append(dict(
                Draft_ID=row["Draft_ID"], Source_Document_ID=doc,
                Figure_Number=row.get("Figure_Number", ""),
                Page=row.get("Page", ""), Dispersion_Type=code,
                Errorbar_Definition_Source=(
                    answer.get("Errorbar_Definition_Source") or "").strip(),
                Found_On_Page=(answer.get("Found_On_Page") or "").strip(),
                Verified_By_Person="1", Recorded_Via=via, Recorded_At=when,
                Note=(answer.get("Note") or "").strip()))

    keep = [r for r in existing
            if r["Draft_ID"] not in set(w["Draft_ID"] for w in written)]
    merged = keep + written
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for row in merged:
            w.writerow(dict((k, row.get(k, "")) for k in FIELDS))
    os.replace(tmp, out_path)

    for doc, problems in refused:
        log("거절 %s" % doc)
        for code, message in problems:
            log("     %-32s %s" % (code, message))
    log("적음 %d행 · 거절 %d · 판정 전체 %d행"
        % (len(written), len(refused), len(merged)))
    return written, refused, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--pdf-root", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="REVIEW_PAGE")
    ap.add_argument("--when", required=True,
                    help="사람이 확인한 날짜. 오늘로 채우지 않습니다 - "
                         "언제 보았는지는 이 프로그램이 아는 것이 아닙니다.")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(args.answers, encoding="utf-8")))
    _w, refused, path = record(
        os.path.expanduser(args.run), answers,
        os.path.expanduser(args.pdf_root), args.when,
        out_path=args.out, via=args.via, replace=args.replace)
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
