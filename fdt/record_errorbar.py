# -*- coding: utf-8 -*-
"""사람이 찾아온 오차 정의를 파이프라인에 넣는 문.

    python3 fdt/record_errorbar.py --run RUN --answers errorbar_found.csv \
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

run2 2026-10-14부터 세 가지를 더 받습니다.
  * 사람이 원문을 직접 확인하지 않고 승인한 관찰(`approval`): Verified_In_Source가
    비고 Verified_By(승인한 사람)·Observed_By(본 것)·Approval_Ref(승인한 자리)가
    모두 있는 답. 기록에는 Verified_By_Person=0으로 남고, 인용문은 여전히 원문에서
    다시 찾아집니다.
  * 그림 하나의 답(Draft_ID): 같은 묶음의 문서 답보다 그 그림에서 이깁니다.
  * 같은 논문의 다른 요소(표, 다른 그림)가 말한 정의를 이 그림에 쓰는 답
    (Definition_Basis=BORROWED, Note에 어디서 왜). 계획서가 그 가정을 값까지
    들고 갑니다(`make_plan.BORROWED_NOTE`).
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

import approval                                                   # noqa: E402
import corpus_intake as CI                                        # noqa: E402
import caption_fulltext as CF                                     # noqa: E402
import kernel                                                     # noqa: E402

DRAFT = "figure_intake_draft.csv"
UNSTATED = "errorbar_unstated.csv"
DECISIONS = "errorbar_decisions.csv"

#: `--plans`(make_plan의 출력 폴더)를 주면 계획서도 기다리는 그림을 댑니다. `errorbar_unstated.csv`는
#: 패널을 세기 전에 만든 목록이라 그 뒤의 일을 모릅니다 - run2(2026-10-17)에서 나중에 열린 그림
#: 둘(막대 없는 그림, 정의 없는 막대)과 규칙이 캡션을 잘못 읽은 그림 둘(회귀선 띠의
#: '95% confidence intervals'가 CI95로 읽힘)이 NOT_PENDING이었습니다.
#: 계획서에서 오는 그림은 둘입니다: 어디서도 정의를 찾지 못한 그림(출처 빈칸), 그리고 규칙이 캡션·문서에서
#: 읽은 정의를 단 그림(READ_BY_RULE) - 뒤의 것은 사람이 고치는 답만 받습니다(Note에 왜, 읽기와 다른 종류).
#: 사람의 판정(DECISION)이 이미 있는 그림은 기다리는 그림이 아닙니다(--replace의 일).
PLAN_FIGURES = "plan_figures.csv"
READ_BY_RULE = ("CAPTION", "DOCUMENT")

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
          "Verified_By_Person", "Recorded_Via", "Recorded_At", "Note",
          # run2 2026-10-14: 사람이 직접 확인하지 않은 답(승인된 관찰)이 들어올
          # 길이 생기면서 붙은 칸들. 직접 확인한 답에서는 뒤의 둘이 비고,
          # Verified_By_Person이 "0"이면 누가 무엇을 보았고 누가 어디서
          # 승인했는지가 여기 있습니다(`approval`).
          "Verified_By", "Observed_By", "Approval_Ref", "Definition_Basis")

#: 정의가 이 그림이 아니라 같은 논문의 다른 요소(표, 다른 그림)에 대해 쓰인
#: 문장에서 온 답(run2 2026-10-14 결정 R9·R10). 인용문은 여전히 원문에서 다시
#: 찾아지고, 이 표시는 그 문장이 이 그림에 대한 것이라는 것이 가정임을 기록에
#: 남깁니다 - 계획서가 그 가정을 값까지 들고 가서 민감도 분석에서 뺄 수 있게.
BORROWED = "BORROWED"
#: 정의가 문장이 아니라 그림에서 잰 것인 답(2026-10-20, 사람의 결정 D01: 논문은 "mean ± SD"라고 하는데 그림의
#: 막대가 그려진 개인 값들의 SE와 맞음 - 서로를 보지 않은 두 검사가 22칸에서). 인용문 자리에는 무엇을 어떻게
#: 쟀는지를 적고, 그것은 원문에서 찾지 않습니다 - 원문에 없는 것이 이 답의 까닭입니다. 그래서 Note(잰 방법과
#: 숫자)와 사람의 이름이 반드시 있어야 하고, 계획서가 그 사실을 값까지 들고 갑니다(`make_plan.MEASURED_NOTE`).
MEASURED = "MEASURED"
DEFINITION_BASES = ("", BORROWED, MEASURED)

#: 답 CSV가 반드시 들고 와야 하는 열. 없는 열은 빈칸이 아니라 다른 파일이라는
#: 뜻입니다 - 검토 페이지가 아닌 무언가를 먹이면 여기서 멎습니다.
ANSWER_REQUIRED = ("Source_Document_ID", "Dispersion_Type",
                   "Errorbar_Definition_Source", "Verified_In_Source")

_WORD = re.compile(r"[^0-9a-z]+")
#: PDF 배경이 이름을 모르는 글자를 내놓는 모양. poppler와 pdfminer가 `±`를
#: 이렇게 적습니다 - 글자가 아니라 "여기 글자가 하나 있는데 뭔지 모르겠다"는
#: 표시입니다. 낱말로 세면 문장 한가운데에 `cid 2` 두 낱말이 끼고, 뷰어에서
#: 그대로 긁어 온 진짜 문장이 원문에 없는 문장이 됩니다.
#:
#: run2에서 인용문 41개 중 14개가 이것 하나로 거부됐습니다. 거부 문구는
#: "낱말이 바뀌었거나, 서로 다른 문장의 조각이 이어 붙었습니다" - 정직하게
#: 옮겨 적은 사람에게 지어냈다고 말하는 문이었습니다.
#:
#: `_key`에서만 씁니다. `_soft`(규칙 대조)에서도 지워 봤지만 죽는 시나리오가
#: 없었습니다 - 이 표시는 `±`가 있던 자리에 서고, 종류를 알아보는 규칙은
#: 이어진 낱말을 찾으므로 그 자리에 무엇이 끼든 답이 바뀌지 않습니다.
#: 관측되지 않는 가드는 장식이라 넣지 않습니다.
_CID = re.compile(r"\(\s*cid\s*:\s*\d+\s*\)", re.I)
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
    flat = _CID.sub(" ", CF._norm(text)).lower()
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
    who = (answer.get("Verified_By") or "").strip()
    basis = (answer.get("Definition_Basis") or "").strip().upper()

    # 사람이 직접 확인했다고 말하지 않은 답은 답이 아닙니다 - 사람이 승인한
    # 관찰(`approval`)이 아니라면. 이 문이 지키는 것은 값의 모양이 아니라 "누가
    # 보았는가"이고, 그것은 에이전트가 대신 채울 수 없습니다. 승인된 관찰은
    # 기록에 Verified_By_Person=0으로, 본 것과 승인한 사람과 승인한 자리와 함께
    # 남습니다.
    if not is_true(answer.get("Verified_In_Source")):
        for c, m in approval.seen_problems(dict(answer, Seen_By_Person=""), who,
                                           "검토 페이지에서 \"직접 확인했습니다\"를 표시하지 "
                                           "않았습니다. 표시가 없는 답은 적지 않습니다."):
            problems.append(("NOT_VERIFIED_BY_PERSON" if c == "NOT_SEEN_BY_PERSON" else c, m))
        if not who and (answer.get("Observed_By") or answer.get("Approval_Ref")):
            problems.append(("UNATTRIBUTED", "사람이 확인하지 않은 답인데 누가 승인했는지"
                                             "(Verified_By)가 없습니다."))

    if basis not in DEFINITION_BASES:
        problems.append(("BAD_DEFINITION_BASIS", "Definition_Basis=%r은 빈칸이나 %s여야 "
                                                 "합니다." % (basis, "/".join(DEFINITION_BASES[1:]))))
    elif basis == MEASURED:
        if code not in DISPERSION_TYPES or code == "NO_ERRORBAR":
            problems.append(("MEASURED_WITHOUT_DEFINITION",
                             "그림에서 쟀다면서 답이 %s입니다. 잰 것은 분산의 종류여야 "
                             "합니다." % (code or "(빈칸)")))
        if not (answer.get("Note") or "").strip():
            problems.append(("MEASURED_UNEXPLAINED",
                             "무엇을 어떻게 쟀는지(칸 수, 비, 누가)를 Note에 적어야 "
                             "합니다. 그것이 이 답의 근거입니다."))
        if not who:
            problems.append(("UNATTRIBUTED", "그림에서 잰 정의를 누가 정했는지"
                                             "(Verified_By)가 없습니다."))
    elif basis == BORROWED:
        if code not in DISPERSION_TYPES or code == "NO_ERRORBAR":
            problems.append(("BORROWED_WITHOUT_DEFINITION",
                             "다른 요소의 정의를 빌렸다면서 답이 %s입니다. 빌린 것은 "
                             "분산의 종류여야 합니다." % (code or "(빈칸)")))
        if not (answer.get("Note") or "").strip():
            problems.append(("BORROWED_UNEXPLAINED",
                             "어느 요소(표 몇, 그림 몇)의 정의를 왜 이 그림에 쓰는지 "
                             "Note에 적어야 합니다. 그것이 이 답의 가정입니다."))

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

    if basis == MEASURED:
        # 인용문 자리는 잰 것의 기술입니다. 비어 있으면 harness가 막고(NO_ERRORBAR_SOURCE),
        # 그 밖의 문장 검사(종류를 말하는가, 원문에 있는가, 몇 쪽인가)는 문장이 아니니 묻지 않습니다.
        if not quote:
            problems.append(("NO_ERRORBAR_SOURCE",
                             "그림에서 잰 정의는 무엇을 어떻게 쟀는지를 인용문 자리에 "
                             "적어야 합니다."))
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


def load_pending(run, plans=None):
    """{문서: [미정 행]} - 아직 정의가 없는 행들. `plans`가 있으면 계획서가 기다리는 그림도
    (`From_Plan`; 규칙이 읽은 정의가 있으면 `Reading`·`Reading_Type`)."""
    path = os.path.join(run, UNSTATED)
    pending = {}
    if plans is None or os.path.exists(path):
        for row in csv.DictReader(io.open(path, encoding="utf-8")):
            pending.setdefault(row["Source_Document_ID"], []).append(row)
    if plans is None:
        return pending
    listed = set(r["Draft_ID"] for rows in pending.values() for r in rows)
    drafts = dict((r["Draft_ID"], r) for r in csv.DictReader(io.open(os.path.join(run, DRAFT), encoding="utf-8")))
    for r in csv.DictReader(io.open(os.path.join(plans, PLAN_FIGURES), encoding="utf-8")):
        did = (r.get("Draft_ID") or "").strip()
        kind = (r.get("Errorbar_Source_Kind") or "").strip().upper()
        if did in listed or did not in drafts or kind not in ("",) + READ_BY_RULE:
            continue
        d = drafts[did]
        pending.setdefault(d["Source_Document_ID"], []).append(dict(
            Source_Document_ID=d["Source_Document_ID"], Draft_ID=did,
            Page=(r.get("Page") or d.get("Page") or "").strip(),
            Figure_Number=(r.get("Figure_Number") or d.get("Figure_Number") or "").strip(),
            Reading=kind, Reading_Type=(r.get("Dispersion_Type") or "").strip().upper(), From_Plan="1"))
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
           replace=False, log=print, plans=None):
    """(적힌 행, 거절된 (문서, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 검토 페이지가 내려준 "
                         "파일이 맞습니까?" % ", ".join(missing))
    pending = load_pending(run, plans)
    out_path = out_path or os.path.join(run, DECISIONS)
    existing = load_decisions(run, out_path)
    settled = set(r["Draft_ID"] for r in existing)

    written, refused = [], []
    # 한 그림만의 답(Draft_ID가 있는 줄). 같은 묶음에 문서 전체의 답이 함께
    # 있으면, 그 그림은 문서의 답이 아니라 그림의 답을 받습니다 - 한 논문에서
    # 그림 하나만 다른 경우(상자 그림 하나, 막대 없는 그림 하나)가 실제로
    # 있습니다. 같은 자리에 답이 둘이면 어느 쪽인지 이 문은 모릅니다.
    named, seen_keys, twice = set(), {}, set()
    for answer in answers:
        doc = (answer.get("Source_Document_ID") or "").strip()
        did = (answer.get("Draft_ID") or "").strip()
        if did:
            named.add(did)
        k = (doc, did)
        if k in seen_keys:
            twice.add(k)
        seen_keys[k] = True
    for answer in answers:
        doc = (answer.get("Source_Document_ID") or "").strip()
        did = (answer.get("Draft_ID") or "").strip()
        if (doc, did) in twice:
            refused.append((did or doc, [("ANSWERED_TWICE",
                                          "%s에 답이 둘 있습니다. 하나만 내 주십시오."
                                          % (did or doc))]))
            continue
        rows = pending.get(doc)
        if rows and did:
            rows = [r for r in rows if r["Draft_ID"] == did]
        elif rows:
            # 계획서에서 온 그림은 그림의 답만 받습니다. 문서의 답이 계획서의 그림까지 덮으면, 규칙이
            # 캡션에서 맞게 읽은 그림의 정의가 같은 논문의 다른 그림을 위한 답으로 바뀝니다.
            rows = [r for r in rows if r["Draft_ID"] not in named and not r.get("From_Plan")]
        if not rows:
            refused.append((did or doc, [("NOT_PENDING",
                                          "%s는 정의를 기다리는 목록에 없습니다. "
                                          "이미 정해졌거나, 이 run의 것이 "
                                          "아닙니다." % (did or doc))]))
            continue
        source, why = read_source(run, doc, pdf_root)
        problems = check_answer(answer, source)
        # 그림에서 잰 답은 원문에서 아무것도 찾지 않으니 원문이 없어도 됩니다.
        measured = (answer.get("Definition_Basis") or "").strip().upper() == MEASURED
        if source is None and why and not measured and not any(c == "SOURCE_UNREADABLE"
                                                               for c, _m in problems):
            problems.append(("SOURCE_UNREADABLE", why))
        if problems:
            refused.append((doc, problems))
            continue
        code = (answer.get("Dispersion_Type") or "").strip().upper()
        for row in rows:
            if row.get("Reading") in READ_BY_RULE:
                # 규칙이 읽은 정의를 사람이 고치는 답. 고친 까닭이 기록에 없으면 다음 사람은 규칙의
                # 읽기와 사람의 답 가운데 어느 쪽이 맞는지 다시 찾아야 합니다.
                if not (answer.get("Note") or "").strip():
                    refused.append((row["Draft_ID"], [("CORRECTION_UNEXPLAINED",
                                    "규칙이 %s에서 %s로 읽은 그림입니다. 고치는 까닭을 Note에 적어 주십시오."
                                    % (row["Reading"], row.get("Reading_Type") or "(빈칸)"))]))
                    continue
                if code == row.get("Reading_Type"):
                    refused.append((row["Draft_ID"], [("SAME_AS_READING",
                                    "규칙의 읽기(%s)와 같은 답입니다 - 적을 것이 없습니다." % code)]))
                    continue
            if row["Draft_ID"] in settled and not replace:
                refused.append((row["Draft_ID"],
                                [("ALREADY_DECIDED",
                                  "이 행은 이미 판정되어 있습니다. 바꾸려면 "
                                  "--replace로 다시 부르십시오.")]))
                continue
            prov = approval.provenance(dict(answer, Seen_By_Person=answer.get("Verified_In_Source")))
            written.append(dict(
                Draft_ID=row["Draft_ID"], Source_Document_ID=doc,
                Figure_Number=row.get("Figure_Number", ""),
                Page=row.get("Page", ""), Dispersion_Type=code,
                Errorbar_Definition_Source=(
                    answer.get("Errorbar_Definition_Source") or "").strip(),
                Found_On_Page=(answer.get("Found_On_Page") or "").strip(),
                Verified_By_Person=prov["Seen_By_Person"], Recorded_Via=via, Recorded_At=when,
                Note=(answer.get("Note") or "").strip(),
                Verified_By=(answer.get("Verified_By") or "").strip(),
                Observed_By=prov["Observed_By"], Approval_Ref=prov["Approval_Ref"],
                Definition_Basis=(answer.get("Definition_Basis") or "").strip().upper()))

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
    ap.add_argument("--plans", help="make_plan의 출력 폴더 - 계획서가 기다리는 그림과 규칙이 읽은 정의를 고치는 답도 받음")
    args = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(args.answers, encoding="utf-8")))
    _w, refused, path = record(
        os.path.expanduser(args.run), answers,
        os.path.expanduser(args.pdf_root), args.when,
        out_path=args.out, via=args.via, replace=args.replace,
        plans=os.path.expanduser(args.plans) if args.plans else None)
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
