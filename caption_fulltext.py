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
#: A boundary that a mangled plus-minus does not destroy. Two journals in this
#: corpus print "±" as a digit - "mean6SD", "means6SE with n57" - and `\b`
#: sees no boundary between "6" and "S", so `\bSD\b` misses the only sentence
#: in the paper that names the bars. Both papers were filed under "the body
#: never says", which is the most confident thing this module can say and so
#: the worst place for it to be wrong. A letter on either side still refuses
#: ("USD", "SDS"); a digit or a symbol does not.
#: THE PLURAL "s" IS LOWERCASE, and saying so is what keeps three real words
#: out: "SDS" (sodium dodecyl sulfate), "SES" (socioeconomic status) and
#: "SEMS" (self-expandable metallic stent) all read as a plural abbreviation
#: under a case-insensitive `s?`. "means and SDs" is the form a paper writes.
_L, _R, _S = r"(?<![A-Za-z])", r"(?![A-Za-z])", r"(?-i:s)?"
DEFINITIONS = (
    ("SEM", re.compile(_L + r"S\.?\s?E\.?\s?M\.?" + _S + _R
                       + r"|standard\s+errors?\s+of\s+the\s+means?", re.I)),
    # THE PERIOD BELONGS TO THE LOOKAHEAD. `S.E.M.`은 `S.E`까지 SE로 읽히고
    # 나서 `(?!\s?M)`이 뒤의 `.M`을 보지 못해 통과합니다 - 그래서 한 문장이
    # SEM과 SE를 동시에 말하는 것이 되고, `record_errorbar`는 그것을
    # QUOTE_SAYS_ANOTHER_TYPE으로 거부합니다. 논문이 `s.e.m.`이라고 적는
    # 것은 흔한 일이고, 그 문장은 SEM 하나만 말합니다. run2의 캡션 644개
    # 중 판정이 달라지는 것은 한 개뿐이고, 그 하나는 SE·SEM 둘 다에서
    # SEM 하나로 좁혀집니다.
    ("SE",  re.compile(_L + r"S\.?E\.?" + _S + _R + r"(?!\.?\s?M)"
                       + r"|standard\s+errors?\b(?!\s+of\s+the\s+mean)", re.I)),
    ("SD",  re.compile(_L + r"S\.?D\.?" + _S + _R + r"|standard\s+deviations?", re.I)),
    ("CI",  re.compile(r"\b9[05]\s*%\s*(?:CIs?|con(?:fi|\s)?dence)"
                       r"|con(?:fi|\s)?dence\s+intervals?|\bCIs?\b", re.I)),
    # IQR is as often spelled out as abbreviated: "median and 25th and 75th
    # percentiles" is the whole of what one paper here says about its boxes.
    ("IQR", re.compile(r"\bIQRs?\b|inter-?quartile"
                       r"|\b25\s?th\s*(?:and|to|[-\u2013\u2014])\s*75\s?th\s+percentiles?", re.I)),
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
#: What a document can call the thing it is presenting. "changes" is here
#: because one paper says only "The percent changes were displayed as mean6SD".
_SUBJECT = (r"data|values?|results|variables|measurements|numbers|changes?|"
            r"error\s+bars?|bars?|whiskers|points?|lines?|responses?")
STATEMENT = re.compile(
    r"(?:"
    r"%(in)s{0,120}\b(?:%(subj)s)\b%(in)s{0,60}\b"
    r"(?:are|were|is|was|be)\b%(in)s{0,40}\b(?:presented|expressed|shown|given|"
    r"reported|displayed|represented|plotted|depicted|summari[sz]ed|indicated)"
    r"|"
    # the subject-less form a caption uses: "Displayed are means +/- 95% CI"
    r"\b(?:displayed|shown|presented|plotted|given)\s+(?:are|is)\s+(?:the\s+)?"
    r"(?:means?|medians?|averages?)"
    r"|"
    # ACTIVE VOICE, which one paper uses and the passive branches cannot see:
    # "Fig. 1 and Fig. 2 show the physiological responses (30-min means and
    # SEMs) of men and women". A sentence only becomes the document's
    # statement when it also NAMES a dispersion, so widening the verb here
    # cannot on its own promote a sentence that says nothing.
    r"%(in)s{0,60}\b(?:shows?|displays?|presents?|reports?|gives?)\b"
    r"%(in)s{0,60}\b(?:%(subj)s|means?|medians?|averages?)\b"
    r")%(in)s{0,200}" % {"in": _IN, "subj": _SUBJECT},
    re.I)

FIELDS = ("Draft_ID", "Source_Document_ID", "Page", "Figure_Number",
          "Caption_Line", "Caption_Full", "Caption_Full_Status",
          "Caption_Full_Lines", "Errorbar_Definition", "Errorbar_Evidence",
          "Doc_Errorbar_Definition", "Doc_Errorbar_Evidence",
          "Doc_Errorbar_Page", "Source_SHA256_OK",
          "Caption_Next_Gap", "Caption_Next_Blocks",
          # 상자그림은 종류 하나로 적을 수 없습니다. 읽은 표시들을
          # "CENTER=MEDIAN;BOX=P25_P75;WHISKER=MIN_MAX"로 싣고, 계획서가 이
          # 그림을 `QUANTILE_SUMMARY`로 보냅니다 - 평평한 연속형 템플릿에는
          # 중앙값을 적을 자리가 없습니다.
          "Box_Elements", "Box_Evidence")


def box_elements_text(elements):
    """{표시: 뜻}을 CSV 한 칸에. 순서는 `FIG_MARKED_ELEMENTS`를 따릅니다 -
    사전의 순서를 그대로 쓰면 같은 읽기가 파이썬 판마다 다른 글자가 됩니다."""
    order = ("CENTER", "ERRORBAR", "BOX", "WHISKER")
    return ";".join("%s=%s" % (k, elements[k]) for k in order if k in elements)


def box_elements_of(text):
    """{표시: 뜻} - `box_elements_text`가 만든 칸을 되읽습니다."""
    out = {}
    for part in str(text or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


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


#: 예외절을 여는 말. 논문이 기본 규칙을 적고 나서 한 갈래만 따로 적을 때 씁니다.
#: `unless otherwise stated`는 여기 없습니다 - 그것은 예외의 내용을 말하지 않는
#: 기본값 선언이고, 코퍼스의 다섯 편이 그 모양인데 전부 지금 옳게 처리됩니다.
EXCEPTION_OPENS = re.compile(
    r"\b(?:except(?:ing)?|besides|apart\s+from|other\s+than)\b", re.I)

#: 그 예외절이 **그림**을 가리키는가. 가리키지 않으면 이 규칙은 손대지 않습니다 -
#: "besides anthropometric data and time intervals"가 그림을 포함하는지는 논문이
#: 말하지 않았고, 그것을 정하는 것은 읽는 사람의 일입니다.
FIGURE_SCOPE = re.compile(
    r"graphical\s+representations?|graphical\s+data"
    r"|\bfigures?\b|\bgraphs?\b|\bplots?\b", re.I)

#: 줄 끝에서 잘린 낱말을 붙입니다. 실제로 걸린 문장이 "graphical representa- tions"
#: 였습니다 - 붙이지 않으면 그림을 가리키는 말을 못 알아봅니다. 이어 붙인 것은
#: 대조용이고, 증거로 내보내는 글자는 원문 그대로입니다.
_BROKEN_WORD = re.compile(r"(\w)-\s+(\w)")


def figure_exception(text):
    """(code, 예외절) - "…, except <그림>, which use X" 문장이 그림에 주는 답.

    한 문장이 두 종류를 말할 때 그것이 늘 애매한 것은 아닙니다. 논문이
    **어느 갈래가 어느 종류인지 말하고 있고 그 갈래가 그림이면**, 그 문장은
    그림에 대해 애매하지 않습니다. 실제 문장:

        Data are presented as means ± SD, except graphical
        representations, which use SE

    이것을 AMBIGUOUS로 두면 사람은 논문이 이미 답한 것을 다시 판정합니다.
    반대로 예외절이 그림을 가리키지 않으면("besides anthropometric data")
    아무것도 하지 않습니다 - 그 갈래에 그림이 드는지는 논문의 말이 아닙니다.

    코드를 못 정하면 ("", "")를 냅니다: 예외절이 없거나, 그림을 가리키지
    않거나, 예외절 안에서도 종류가 하나로 좁혀지지 않을 때.
    """
    flat = _norm(text)
    m = EXCEPTION_OPENS.search(flat)
    if not m:
        return "", ""
    tail = flat[m.end():]
    if not FIGURE_SCOPE.search(_BROKEN_WORD.sub(r"\1\2", tail)):
        return "", ""
    hits = []
    for code, rx in DEFINITIONS:
        found = rx.search(tail)
        if found:
            hits.append(code)
    if len(set(hits)) != 1:
        return "", ""
    return hits[0], flat[m.start():][:160].strip()


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
        # 논문이 그림만 따로 적었으면 그 문장은 그림에 대해 애매하지 않습니다.
        code, clause = figure_exception(text)
        if code:
            return code, clause
        return DEF_AMBIGUOUS, " | ".join("%s: %s" % h for h in hits)
    if hits:
        return hits[0]
    m = PLUS_MINUS.search(text)
    if m:
        a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
        return DEF_PM_UNNAMED, text[a:b].strip()
    return DEF_UNSTATED, ""


#: 상자그림을 설명하겠다고 여는 말. 이 말이 없으면 아래를 보지 않습니다 -
#: "The black box in front of the subject's head"도 box를 말하고 median을
#: 말하는 문장이 같은 캡션에 있을 수 있습니다.
BOX_OPENS = re.compile(
    r"box\s*-?\s*(?:and\s*-?\s*whiskers?\s*)?plots?\s+"
    r"(?:indicate|show|shows|represent|represents|display|displays|are|give)\b",
    re.I)

#: 여는 말 뒤에서 찾는 표시들. 낱말이 아니라 **짝**을 봅니다: 25th 하나만으로는
#: 상자의 아래위를 알 수 없고, minimum 하나만으로는 수염이 어디까지인지 알 수
#: 없습니다.
_BOX_P25_P75 = re.compile(r"25\s?th\s+percentile", re.I), \
               re.compile(r"75\s?th\s+percentile", re.I)
_WHISKER_MIN_MAX = re.compile(r"\bminimum\b|\bmin\b", re.I), \
                   re.compile(r"\bmaximum\b|\bmax\b", re.I)
_CENTER_MEDIAN = re.compile(r"\bmedians?\b", re.I)


def box_elements(text):
    """({표시: 뜻}, 근거 문장) - 상자그림이 무엇을 나타내는지 캡션이 말한 것.

    `errorbar_definition`은 계열 하나에 종류 하나를 냅니다. 상자그림은 그렇게
    적을 수 없습니다 - 중앙선·상자·수염이 각각 다른 것을 말하고, 그 셋을
    `IQR` 한 토큰으로 뭉치면 상자가 25-75인지 수염이 어디까지인지가 사라집니다.
    사라진 채로 디지타이즈하면 수는 나오고 그 수는 다른 값입니다.

    코퍼스에서 이 모양으로 적은 논문은 하나뿐이고, 문장은 이것입니다:

        Box plots indicate minimum, 25th percentile, median, 75th percentile,
        and maximum values.

    찾은 것만 냅니다. 여는 말 뒤가 잘려 있으면(그 논문 FIG9가 그렇습니다) 빈
    사전을 내고, 그 그림은 사람에게 갑니다 - 반쯤 읽은 문장으로 답을 짓는 것이
    이 파이프라인이 하지 않기로 한 일입니다.
    """
    flat = _norm(text)
    m = BOX_OPENS.search(flat)
    if not m:
        return {}, ""
    tail = flat[m.end():]
    out = {}
    if _CENTER_MEDIAN.search(tail):
        out["CENTER"] = "MEDIAN"
    lo, hi = _BOX_P25_P75
    if lo.search(tail) and hi.search(tail):
        out["BOX"] = "P25_P75"
    lo, hi = _WHISKER_MIN_MAX
    if lo.search(tail) and hi.search(tail):
        out["WHISKER"] = "MIN_MAX"
    if not out:
        return {}, ""
    return out, flat[m.start():m.start() + 180].strip()


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
            "Box_Elements": "", "Box_Evidence": "",
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
        marks, mev = box_elements(full)
        if marks:
            base["Box_Elements"] = box_elements_text(marks)
            base["Box_Evidence"] = mev
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
