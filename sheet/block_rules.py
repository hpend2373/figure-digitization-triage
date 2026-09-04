# -*- coding: utf-8 -*-
"""Which rows of the panel-count sheet may not take a number, and why.

Separate from the sheet builder, and holding no data of its own, because this
is the safety rule: it decides whether a person is allowed to type a panel
count against a picture. The builder reads a draft that cannot be published -
the crops come from publisher PDFs - so a rule that lived inside it could not
be reproduced from this repository, which is exactly what the fifth audit
said.

Two keys, and the difference between them is the whole point.

    Draft_ID              `<document>_D001`, `_D002`. A POSITION in one walk's
                          output. Recovering a caption inserts a row and every
                          later ordinal shifts.
    (pid, label, page)    what the document PRINTS. Stable across rebuilds.

The audits record defects against figures; the draft records rows. Keying the
first onto the second by Draft_ID put three crops a person had judged wrong
back in play with their inputs open, and left eight it had judged fixed still
blocked. Nothing here uses Draft_ID as an identity.
"""

import os
import re
import sys

import census as _census

# `__file__` is absent when this module's source is exec'd into a synthetic
# module, which a scenario does on purpose; the import is best-effort either
# way and the fallback below is the same string.
if "__file__" in globals():                           # pragma: no cover
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
try:                                                  # pragma: no cover
    from corpus_intake import UNREADABLE_NUMBER_REASON
except Exception:                                     # pragma: no cover
    # THE INTAKE IS THE AUTHORITY ON ITS OWN WORDING, and this module runs in
    # trees where it is not importable (the sheet ships without it). The
    # fallback is the same string, and `test_sheet_blocks` asserts the two
    # agree wherever the intake CAN be imported - a copy nobody compares is a
    # copy that drifts.
    UNREADABLE_NUMBER_REASON = (
        "the line opens like a caption but its number reads as")

#: A caption that reads like a sentence of the body: "Figure 4 shows the
#: hemodynamic...", "Fig. 5, and separate analysis...", "Figure 1 contrasts
#: the depressive effect...". ON ITS OWN THIS PROVES NOTHING. One book in run2
#: writes every caption that way ("Fig. 1 Shows the Transient Inspiratory
#: Occlusion paradigm") with the figure sitting right above it, and both of
#: those rows are countable. The pattern becomes evidence only together with
#: the two facts `phantom_reason` asks for.
#: WHAT A NUMBER LOOKS LIKE IN A SCANNED LINE. `1` is read as `l` or `I` often
#: enough that the eight rows nobody could number were all one of these -
#: keying the body-sentence test on `\d+` made it blind to exactly the lines
#: whose number would not parse, which are the lines it most needed to see.
_FIGNUM = r"(?:\d{1,2}|[lI])"
#: `Figures 1 and 2`, `Figs 3 and 4`, `Figures 2, 3, and 4` - a sentence names
#: several figures, and the singular-only pattern saw none of them.
#: `, ` / ` and ` / ` & ` / `, and ` - the last one first, or the comma eats
#: the separator and the final figure of `Figures 2, 3, and 4` is never named.
_SEP = r"(?:\s*,\s*and\s+|\s*,\s*|\s*&\s*|\s+and\s+)"
_FIGLIST = r"%s(?:[A-Za-z])?(?:%s%s(?:[A-Za-z])?)*" % (_FIGNUM, _SEP, _FIGNUM)
#: TWO OR MORE FIGURES IN ONE LINE IS A SENTENCE ON ITS OWN EVIDENCE. A
#: caption names the figure it sits under; only prose says "Figures 1 and 2".
#: This one needs no verb after it, because the verb often falls outside the
#: line the intake captured ("Figs 3 and 4. All the LBNP tests caused...").
BODY_MULTI = re.compile(
    r"^(?:Figs?|Figures?)\.?\s*(?P<nums>%s(?:[A-Za-z])?(?:%s%s(?:[A-Za-z])?)+)"
    % (_FIGNUM, _SEP, _FIGNUM), re.I)
BODY_REFERENCE = re.compile(
    r"^(Figs?|Figures?)\.?\s*(?P<nums>" + _FIGLIST + r")\s*"
    r"(?P<tail>\)|,|and\b|shows?\b|presents?\b|"
    r"illustrates?\b|contrasts?\b|depicts?\b|demonstrates?\b|"
    r"summari[sz]es?\b|compares?\b|displays?\b|gives?\b|indicates?\b|"
    r"represents?\b|confirms?\b|reveals?\b|reports?\b|plots?\b|lists?\b|"
    r"provides?\b|describes?\b|documents?\b|highlights?\b|which\b)", re.I)
_NUM_IN_LIST = re.compile(_FIGNUM)


def mentioned_figures(text):
    """The figures a body sentence names, as stored labels, or ().

    `Figures 1 and 2 show...` -> ("FIG1", "FIG2"). `l` and `I` are read as 1,
    the same OCR slip that stopped the row being numbered in the first place.
    Returns () for anything that does not read as a sentence of the body, so
    a real caption never lands here.
    """
    text = str(text or "").strip()
    m = BODY_MULTI.match(text) or BODY_REFERENCE.match(text)
    if not m:
        return ()
    out = []
    for token in _NUM_IN_LIST.findall(m.group("nums")):
        label = "FIG%d" % (1 if token in ("l", "I") else int(token))
        if label not in out:
            out.append(label)
    return tuple(out)

#: The proposer codes that mean "nothing figure-sized on this page at all".
NO_CANDIDATE = "NO_CANDIDATE"


def body_reference(text):
    """Does this caption read like a sentence of the body?"""
    text = str(text or "").strip()
    return bool(BODY_MULTI.match(text) or BODY_REFERENCE.match(text))


#: `blocked_of` says a row is blocked with this exact value, because that is
#: what `build_sheet2.BLOCK` holds - the string "1". Reading it as a plain
#: truth value made every row look blocked ("0" is a non-empty string) and the
#: whole check silently returned nothing.
BLOCKED_MARK = "1"


def mentions_held(row, rows_of_document, blocked_of):
    """Figures this row's line names that another row already holds.

    [(label, Draft_ID)] for each figure the sentence names that has its own,
    countable row in the same document - and () when the line is not a body
    sentence, or names nothing anybody else holds.

    THIS IS NOT A VERDICT AND MUST NOT BLOCK. Whether a line is a caption or
    a sentence cannot be settled from the text - this package learned that
    once already, when a regex written to catch prose caught half the real
    captions too. What it can do is put on the card what it already knows, so
    a person looking at eight rows they cannot number is not left guessing
    which figure to draw. Every one of those eight named figures that this
    document had already counted; none of them could be seen, because the
    duplicate rule and the phantom rule both key on a figure number and these
    are precisely the rows that have none.
    """
    held = []
    for label in mentioned_figures(row.get("Caption_Text")):
        for other in rows_of_document:
            if other.get("Draft_ID") == row.get("Draft_ID"):
                continue
            if (str(other.get("Figure_Number") or "").strip().upper() == label
                    and str(blocked_of.get(other["Draft_ID"], "")).strip()
                    != BLOCKED_MARK):
                held.append((label, other["Draft_ID"]))
                break
    return tuple(held)


def twin_map(draft):
    """Draft_ID -> (twin Draft_ID, twin page) for rows whose figure number
    has another row on an ADJACENT page of the same document.

    Adjacent only. A 350-page book repeats FIG1 in every chapter; a row on
    page 209 has forty "twins" by number alone and exactly one that matters,
    the one on page 210. Reads no files: the caller hands it the draft rows.
    """
    by = {}
    for r in draft:
        try:
            page = int(str(r.get("Page") or "").strip())
        except ValueError:
            continue
        key = (r.get("Source_Document_ID"), r.get("Figure_Number"))
        by.setdefault(key, []).append((page, r["Draft_ID"]))
    out = {}
    for (doc, fig), rows in by.items():
        for page, did in rows:
            for other_page, other in rows:
                if other != did and abs(other_page - page) == 1:
                    out[did] = (other, other_page)
                    break
    return out


def phantom_reason(row, codes=(), twin=None):
    """This row is the body's MENTION of a figure that lives a page over - or ''.

    On 2026-09-03 a person asked whether some captions sit on one page with
    their figure on another. Running both detectors on the neighbouring pages
    of the 57 rows nobody could place found 15 with a figure-sized region next
    door - and reading those rows' "captions" found "Figure 4 shows the
    hemodynamic and neural responses", a sentence from the Results. The intake
    had taken the body's mention for the caption; the real caption, under the
    real figure, was on the next page and (for eight of them) already had a row
    of its own. Counting such a row counts that figure twice.

    THREE FACTS, ALL REQUIRED, because each alone is innocent:
      1. the caption reads like a sentence of the body (see BODY_REFERENCE -
         one book writes real captions that way);
      2. neither detector found a figure-sized region on THIS page (a real
         caption has its figure beside it, and the detectors find it);
      3. the same figure has a row of its own on an adjacent page (`twin`).
    A row that meets all three is not a figure. Drawing a box on it cannot
    make it one - the only thing to draw would be the neighbour's figure, and
    that already has a row.
    """
    if not (twin and body_reference(row.get("Caption_Text"))):
        return ""
    codes = tuple(str(c or "").strip() for c in codes)
    if len(codes) != 2 or any(c != NO_CANDIDATE for c in codes):
        return ""
    other, other_page = twin
    return ("본문에서 그림을 언급한 문장이 캡션으로 잡힌 행입니다 — 이 쪽에는 그림 "
            "크기의 영역이 없고, 같은 그림이 p.%s의 %s 행으로 이미 있습니다. 이 행을 "
            "세면 그 그림을 두 번 세는 것입니다." % (other_page, other))

#: What the third and fourth audits judged still wrong after the crop round,
#: keyed by what the page prints. These take no number whatever the crop
#: grader says about them - the grader is an ink measurement and the finding
#: was made by looking. Removing one requires a person comparing the crop to
#: the source and saying so.
#:
#: AND A FINDING HERE IS A STATEMENT ABOUT A PICTURE. Every entry was made by
#: somebody looking at one crop and saying what was wrong with it; three of
#: them say so outright ("다시 자르면 열립니다", "사람이 지정하기 전에는").
#: For a long time nothing could act on that: the table was keyed by the
#: figure, so a finding outlived every crop the row ever had. On 2026-09-02 a
#: person drew the boxes for ten rows by hand, and two of them stayed blocked
#: by findings about crops that no longer existed - the harness had asked the
#: question and then ignored the answer. `lapsed` below is the rule that
#: fixes it, and `HUMAN_CUT` is what makes it checkable rather than assumed.
STILL_WRONG = {
    ("437", "FIG2", "176"): "3차 감사: FIG3 그래프가 여전히 함께 보입니다",
    ("516", "FIG5", "6"): "3차 감사: 위쪽 막대 두 개뿐이고 아래 그래프가 빠집니다",
    ("99", "FIG1", "4"): "3차 감사: 아래 PSD 그래프들이 계속 빠집니다",
    ("554", "FIG4", "5"): "3차 감사: 대부분 빈 영역이고 실제 FIG4 막대그래프가 없습니다",
    ("700", "FIG1", "3"): "3차 감사: Session B가 계속 없습니다",
    ("397", "FIG1", "4"): "3차 감사: 여전히 잘려 있습니다",
    ("518", "FIG1", "3"): "3차 감사: 원문은 그래프 4개인데 일부만 보입니다",
    ("159", "FIG3", "5"): "3차 감사: 원문은 A/B/C인데 A와 B의 시작만 보입니다",
    # 2026-09-01, run2 감사. 열린 415행에서 층화 표본 15개를 눈으로 본 결과 나온
    # 두 건입니다. 둘 다 "잘림"보다 나쁩니다 - 상자가 캡션 위쪽 한 단을 집었고
    # 그림은 그 옆에 있습니다. 크기 하한(200px)은 이런 상자를 잡지 못합니다:
    # 상자 자체는 크고, 안에 든 것이 그림이 아닐 뿐입니다.
    ("177", "FIG3", "5"): "run2 감사: 상자가 캡션 위 한 단이고 6패널 그림은 "
                          "오른쪽에 있습니다",
    ("531", "FIG1", "3"): "run2 감사: 상자가 캡션 위 빈 영역이고 MSNA 기록 두 "
                          "개는 오른쪽에 있습니다",

    # 2026-09-02, 사람 검토. `figure_regions.py`가 낸 두 번째 상자와 지금
    # 상자가 크게 어긋난 22행 중 앞의 12행을 사람이 나란히 보고 판정한
    # 결과입니다. 아래 아홉 건은 **어느 상자도** 대상 그림을 제대로 잡지
    # 못했습니다 - 다시 자르는 것으로는 풀리지 않으므로, 그림을 사람이 지정
    # 하기 전에는 계수 불가입니다.
    ("61", "FIG2", "4"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                         "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("61", "FIG4", "6"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                         "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("437", "FIG1", "118"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                            "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("437", "FIG1", "315"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                            "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("687", "FIG2", "4"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                          "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("687", "FIG4", "5"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                          "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("122", "FIG2", "3"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                          "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("571", "FIG3", "4"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                          "상자도 대상 그림을 제대로 잡지 못했습니다",
    ("574", "FIG3", "5"): "사람 검토(2026-09-02): 지금 상자도 PDF 기준 새 "
                          "상자도 대상 그림을 제대로 잡지 못했습니다",

    # 같은 검토에서, 새 상자가 맞다고 판정된 세 건입니다. 그림이 어디인지는
    # 밝혀졌지만 시트가 보여 주는 크롭은 여전히 옛 상자에서 잘린 것이므로,
    # 지금 화면으로는 셀 수 없습니다. 다시 자르면 열립니다.
    ("345", "FIG2", "4"): "사람 검토(2026-09-02): 지금 상자는 본문을 집었고 "
                          "PDF 기준 새 상자가 맞습니다 — 다시 잘라야 열립니다",
    ("564", "FIG2", "4"): "사람 검토(2026-09-02): 지금 상자는 본문을 집었고 "
                          "PDF 기준 새 상자가 맞습니다 — 다시 잘라야 열립니다",
    ("744", "FIG4", "6"): "사람 검토(2026-09-02): 지금 상자는 그림의 일부만 "
                          "집었고 PDF 기준 새 상자가 맞습니다 — 다시 잘라야 "
                          "열립니다",
}

#: `Crop_Source` when the crop was cut from a box A PERSON named - the three
#: proposers they may choose between, or one they drew themselves. The machine
#: writes `VALIDATED_REGION` for its own recuts, and those are deliberately NOT
#: this: two detectors agreeing is not a person looking, and a finding made by
#: looking is not answered by a machine agreeing with itself.
HUMAN_CUT = "HUMAN_CHOICE_"
#: What `apply_validated` writes when a person typed the figure number.
NUMBER_BY_HUMAN = "HUMAN"


def numbered_by_hand(row):
    """Did a person supply this row's figure number?"""
    return (str(row.get("Number_Source") or "").strip().upper()
            == NUMBER_BY_HUMAN)


def human_cut(row):
    """Which choice of the person's cut this crop, or '' if none did."""
    src = str(row.get("Crop_Source") or "").strip().upper()
    return src[len(HUMAN_CUT):] if src.startswith(HUMAN_CUT) else ""


def _defect_reason(defect):
    """The second audit's FAIL, in its own words - or '' if it is not one."""
    if not defect or str(defect.get("classification", "")).strip() != "FAIL":
        return ""
    kind = str(defect.get("kind", "")).strip()
    return "2차 감사 확인 — %s: %s" % (DEFECT_KIND.get(kind, kind),
                                   defect.get("screen", ""))


def lapsed(row, key, still_wrong=None, defect=None):
    """The finding this row no longer has to answer for, or ''.

    A finding lapses when the person REPLACED the picture it describes - they
    drew a box, or picked a proposer's box that was not the one the crop came
    from, and `apply_validated` recut it (which `roundtrip` then proves).

    IT DOES NOT LAPSE when their answer left the crop where it was. Choosing
    TEXT, or a box the crop already came from, says "this picture is right"
    about the very picture the finding says is wrong. That is a contradiction
    between two things a person said, not a statement that expired, and it is
    not the harness's to settle - so the row stays blocked and the reason says
    both halves out loud.
    """
    if not human_cut(row):
        return ""
    table = STILL_WRONG if still_wrong is None else still_wrong
    # BOTH TABLES HOLD THE SAME KIND OF SENTENCE. `STILL_WRONG` is the third
    # and fourth audits plus the person; `confirmed_image_defects.csv` is the
    # second. Every entry in either was written by looking at one crop. There
    # is no reason one expires when that crop is replaced and the other does
    # not - and treating them differently is what left row 554 blocked by
    # "the FIG4 bar chart is not visible" while the person's own box held
    # nothing but the FIG4 bar chart.
    return table.get(key, "") or _defect_reason(defect)


#: How much two boxes must overlap before they are the same picture. Measured,
#: not guessed: on 2026-09-03 a person's 210 answers produced 26 pairs of rows
#: that would have counted one figure twice, and every one of the 26 overlapped
#: between 0.54 and 0.97. Nothing legitimate came near this line.
DUPLICATE_IOU = 0.30

#: How strong a row's claim to a picture is, weakest first. Two rows cannot
#: count the same figure, and when they land on it the weaker claim yields.
#: This is not a judgement about which caption is real - that turned out to be
#: unreadable from the text ("Fig. 2). However, blood electrolytes…" is a
#: sentence; "Fig. 2 Protocol of centrifuge" is a caption; a regex that
#: catches the first catches half the second kind too). It is a statement
#: about EVIDENCE: a row placed by two independent detectors has more of it
#: than a row a person had to draw by hand, and a row that had to leave its
#: own page to find a picture has the least of all.
CLAIM_DRAWN_ELSEWHERE, CLAIM_DRAWN, CLAIM_PICKED, CLAIM_DETECTED = 0, 1, 2, 3


def claim_rank(row):
    """How strong this row's claim to its picture is (see CLAIM_* above)."""
    src = str(row.get("Crop_Source") or "").strip().upper()
    if not src.startswith(HUMAN_CUT):
        return CLAIM_DETECTED
    if src != HUMAN_CUT + "DRAWN":
        return CLAIM_PICKED
    return (CLAIM_DRAWN_ELSEWHERE if str(row.get("Moved_From_Page") or "").strip()
            else CLAIM_DRAWN)


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _corners(text):
    try:
        x0, y0, x1, y1 = [float(v) for v in str(text or "").split(",")]
    except ValueError:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def duplicate_map(rows, blocked_ids=()):
    """{Draft_ID: (winner Draft_ID, page)} for rows that count one picture twice.

    Two rows of the same document, carrying the same figure number, whose
    boxes overlap on the same page, are the same figure. One of them counts;
    the other must not, or that figure is in the corpus twice.

    THIS IS THE FACT THE HARNESS HAD NO WAY TO SEE. It knew a row's crop could
    be pixel-identical to another's (`shared_crop_map`), but two rows can point
    at one figure with slightly different boxes - the intake reads the body's
    mention of a figure as a caption, a person then draws the figure for it,
    and the figure's own row already had it. On 2026-09-03 that was 26 rows.

    The winner is the strongest claim (see `claim_rank`), ties going to the
    row that comes first in the document. Nothing is deleted: the loser is
    blocked with the winner's name, so a person who disagrees blocks the
    winner instead and the figure moves.

    AND IT MOVES BECAUSE A BLOCKED ROW TAKES NO PART. `blocked_ids` are the
    rows a person has marked BLOCKED - "none of these is the figure". Such a
    row holds no picture, so it can neither win one nor be a duplicate of one.
    Without this the promise above was empty: a detector-placed row kept its
    top claim after the person blocked it, went on winning, and the row the
    person had drawn stayed blocked as its duplicate - the person's answer
    to both rows ignored at once.
    """
    groups = {}
    blocked_ids = set(blocked_ids)
    for r in rows:
        if r.get("Draft_ID") in blocked_ids:
            continue
        box = _corners(r.get("Figure_BBox"))
        fig = str(r.get("Figure_Number") or "").strip()
        if not box or not fig:
            continue
        key = (r.get("Source_Document_ID"), fig, str(r.get("Page") or "").strip())
        groups.setdefault(key, []).append((r, box))
    out = {}
    for (_doc, _fig, page), members in groups.items():
        if len(members) < 2:
            continue
        # Cluster by overlap: a figure two rows both point at is one cluster,
        # two different figures sharing a label on one page are two.
        clusters = []
        for r, box in members:
            for c in clusters:
                if any(_iou(box, other_box) >= DUPLICATE_IOU for _o, other_box in c):
                    c.append((r, box))
                    break
            else:
                clusters.append([(r, box)])
        for c in clusters:
            if len(c) < 2:
                continue
            ranked = sorted(c, key=lambda rb: (-claim_rank(rb[0]), rb[0]["Draft_ID"]))
            winner = ranked[0][0]["Draft_ID"]
            for r, _b in ranked[1:]:
                out[r["Draft_ID"]] = (winner, page)
    return out


#: What a duplicate found by a person's own box is marked with in the map.
CONFIRMED_BY_BOX = "DRAWN"


def confirmed_duplicates(regions):
    """{Draft_ID: (winner, page, CONFIRMED_BY_BOX)} the person settled by drawing.

    `duplicate_map` sees two boxes on ONE page. This is the other way a row
    turns out to hold a figure some other row already counts: the caption sat
    on page N, the person leafed to page P and drew the figure there - and
    page P already had a row for that figure. `apply_validated` refuses the
    move (it would count the figure twice) and writes the twin it found into
    `Duplicate_Of` / `Duplicate_Page` on the regions row. Reading it back here
    turns a refusal into a reason.

    Before this the refusal was silent: the row kept its old HUMAN_BLOCKED
    reason ("the person said none of the three is a figure") while its
    Human_Choice said DRAWN, and nothing anywhere recorded that the person had
    in fact found the figure. On 2026-09-04 that was 20 of 47 answers.
    """
    out = {}
    for r in regions:
        twin = str(r.get("Duplicate_Of") or "").strip()
        if twin:
            out[r["Draft_ID"]] = (twin, str(r.get("Duplicate_Page") or "").strip(),
                                  CONFIRMED_BY_BOX)
    return out


#: What a person can supply on the decision page, and the trial row each one
#: produces. Named, because "would a box help" was one boolean and the page
#: could therefore only offer one kind of repair - a row needing a figure
#: number was told "a box will not help" and given nothing else to do.
REPAIR_BOX, REPAIR_NUMBER = "BOX", "NUMBER"
#: A number that is not any real figure's, used only to ask the rule whether
#: HAVING one would change its answer. Never written anywhere.
_TRIAL_NUMBER = "FIG?"


def repairs_that_open(row, key, **context):
    """The smallest set of person-supplied repairs that unblocks this row.

    Returns a tuple of REPAIR_* names, or () when nothing a person can enter
    on the page would change the answer.

    ASKED OF THE RULE ITSELF, not of a list of reason-strings kept beside it.
    A second list would be a copy of this function's behaviour maintained by
    hand, and the first time a gate changed the page would start asking for
    work that changes nothing - or, worse, stay silent about work that would.

    WHY A SET AND NOT A BOOLEAN. Seven of the eight rows blocked for an
    unread figure number are also THIN_CROP: a number alone leaves them
    blocked, a box alone leaves them blocked, and both together open them.
    Asked one repair at a time, each answer is "no", and the page said
    "a box will not help" and offered no other box to type in. The person
    answered anyway - once by writing the number into the free-text note,
    once by picking a proposer - and neither could reach the field.
    """
    for wanted in ((), (REPAIR_BOX,), (REPAIR_NUMBER,),
                   (REPAIR_BOX, REPAIR_NUMBER)):
        trial, ctx = dict(row), dict(context)
        if REPAIR_BOX in wanted:
            # What the row WOULD look like after `apply_validated` applies a
            # hand-drawn box: cut from a box the person named, so it
            # round-trips, the region is human-validated, the crop is
            # re-measured, and it is no longer pixel-identical to another
            # label's crop.
            trial.update(Crop_Source=HUMAN_CUT + "DRAWN",
                         Crop_Quality_Status="ACCEPTABLE")
            ctx.update(shared_with=(), roundtrip="MATCH",
                       agreement="HUMAN_VALIDATED", crop_sha="")
        if REPAIR_NUMBER in wanted:
            trial["Figure_Number"] = _TRIAL_NUMBER
            trial["Number_Source"] = NUMBER_BY_HUMAN
        # `duplicate` is NOT cleared by either repair: neither can stop
        # another row from already holding this figure - if anything a box is
        # how a row gets there.
        if not blocked_reason(trial, key, **ctx):
            return wanted
    return ()


def box_would_open(row, key, **context):
    """Would drawing a box on this row clear what is blocking it?

    ASKED OF THE RULE ITSELF, not of a list of reason-strings kept beside it.
    A second list would be a copy of this function's behaviour maintained by
    hand, and the first time a gate changed the page would start telling
    people "draw a box" for rows a box cannot help - or, worse, stay silent
    about rows it could.

    The trial row is what the row WOULD look like after `apply_validated`
    applies a hand-drawn box: the crop is cut from a box the person named, it
    round-trips (it was just cut from that box), the region is human-validated,
    the crop is re-measured, and it is no longer pixel-identical to another
    label's crop. What that leaves standing - no figure number, confidence
    zero, a census defect against a picture nobody has looked at yet - is
    exactly what a box cannot answer.
    """
    return REPAIR_BOX in repairs_that_open(row, key, **context)


def number_would_open(row, key, **context):
    """Is a figure number one of the things this row is waiting for?"""
    return REPAIR_NUMBER in repairs_that_open(row, key, **context)


#: Crop verdicts a person cannot count from, and what to tell them.
#: The statuses that mean the picture can be counted from. ACCEPTABLE is a
#: crop cut from a page and judged to hold its figure; PUBLISHER_FIGURE is the
#: publisher's own figure file, which cannot clip a figure or take in a
#: neighbour because it IS the figure. Widening this set is widening what a
#: person may be asked to count, so the two members are named one by one and
#: everything else is still refused by name.
COUNTABLE_CROPS = ("ACCEPTABLE", "PUBLISHER_FIGURE")
#: Kept for readers that ask for the crop case by name.
COUNTABLE_CROP = "ACCEPTABLE"

UNCOUNTABLE_CROPS = {
    "EDGE_CLIPPED": ("크롭이 그림을 자르고 있습니다 — 가장자리에 잉크가 걸립니다. "
                     "전체 페이지를 보고 세야 합니다."),
    "THIN_CROP": ("크롭이 납작함 — 2차 감사 표본 36건이 모두 계수 불가였습니다. "
                  "크롭 재생성 전까지 막아 둡니다."),
    "NO_CROP": "원문에 페이지 이미지가 없습니다 (XML·텍스트 원문).",
}

#: THE TWO SETS CANNOT OVERLAP. The gate answers "countable" before it answers
#: "uncountable", so a status listed in both is countable and its reason never
#: runs - which is how a safety rule gets reversed by an addition rather than
#: a deletion. Adding THIN_CROP to the countable set passed every scenario
#: there was; nothing compared the sets to each other.
_BOTH = sorted(set(COUNTABLE_CROPS) & set(UNCOUNTABLE_CROPS))
if _BOTH:
    raise AssertionError(
        "계수 가능과 계수 불가에 같은 상태가 있습니다: %s — 이 문에서는 "
        "계수 가능이 먼저 답하므로 막는 규칙이 아예 실행되지 않습니다"
        % ", ".join(_BOTH))


#: How the audits' findings are named, for the message.
DEFECT_KIND = {
    "mixed_figures": "다른 그림 혼입",
    "clipped_target": "대상 그림 잘림",
    "wrong_region": "대상이 아닌 영역",
    "foreign_axis_fragment": "이웃 축 조각 혼입",
}


def figure_key(pid, label, page):
    """The identity a finding is recorded against: what the page prints."""
    return (str(pid).strip(), str(label).strip().upper(), str(page).strip())


#: What `roundtrip.check` can say about a row, and which of those answers
#: mean the picture on the sheet cannot be traced back to its box. A crop that
#: cannot be cut again from the draft's own geometry is a crop nobody can
#: verify - a mirrored box, a stale crop, a row whose page size was never
#: recorded - and a person may not count from it.
ROUNDTRIP_UNVERIFIABLE = {
    "MISMATCH": ("상자대로 다시 자른 그림이 크롭 파일과 다릅니다 — 크롭이 어느 "
                 "상자에서 나왔는지 알 수 없으므로 셀 수 없습니다."),
    "NO_CUT": ("초안의 기하로는 이 크롭을 만들 수 없습니다 (쪽 크기나 상자가 "
               "없음) — 크롭이 어디서 나왔는지 확인할 길이 없으므로 셀 수 "
               "없습니다."),
}


#: What `validate_regions.agree` can say, and what each answer means for a
#: person about to type a number. AGREE_3 is the only answer under which the
#: crop on the sheet is a region two independent methods both point at; it
#: is therefore the only answer that is not a reason. AGREE_2 means the two
#: methods agree with each other and NOT with the crop on the sheet - the
#: crop is the odd one out, and `apply_validated.py` recuts it.
AGREEMENT_UNCOUNTABLE = {
    "AGREE_2_TEXT_DIFFERS": (
        "PDF 객체와 래스터 잉크가 같은 영역을 가리키는데 지금 크롭은 다른 곳을 "
        "잘랐습니다 — 검증 상자로 다시 자르기 전에는 셀 수 없습니다."),
    "DISAGREE": (
        "그림 영역을 찾는 두 방법(PDF 객체·래스터 잉크)이 서로 다른 곳을 "
        "가리킵니다 — 어느 쪽이 그림인지 사람이 정해야 합니다 (REVIEW_REQUIRED)."),
    "RASTER_ONLY": (
        "래스터 잉크만 그림 영역을 냈고 PDF 객체는 답이 없습니다 — 한 방법의 "
        "답은 제안일 뿐이므로 사람이 확인해야 합니다 (REVIEW_REQUIRED)."),
    "PDF_ONLY": (
        "PDF 객체만 그림 영역을 냈고 래스터 잉크는 답이 없습니다 — 한 방법의 "
        "답은 제안일 뿐이므로 사람이 확인해야 합니다 (REVIEW_REQUIRED)."),
    "NONE": (
        "어느 방법도 이 캡션에 답하는 그림 영역을 찾지 못했습니다 — 캡션 옆에 "
        "그림이 없거나 두 방법이 모두 놓친 배치입니다 (REVIEW_REQUIRED)."),
    "PENDING": "그림 영역 검증이 아직 이 행까지 오지 않았습니다.",
}
#: The answers that leave a row countable: the two detectors agreeing with the
#: crop, or a person having chosen the region after looking (`Human_Choice`
#: in the regions table, applied by `apply_validated.py`).
AGREEMENT_COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED")
AGREEMENT_UNCOUNTABLE["HUMAN_BLOCKED"] = (
    "사람이 이 행의 그림 영역을 정할 수 없다고 표시했습니다 — 세 제안 중 어느 것도 "
    "그림이 아닙니다.")


def blocked_reason(row, key, defect=None, shared_with=(), still_wrong=None,
                   census=None, crop_sha="", roundtrip=None, agreement=None,
                   codes=(), twin=None, duplicate=None):
    """Why this row may not take a panel count. Empty string means it may.

    `row` needs only the four fields the decision reads, so this can be tested
    without a draft: Figure_Number, Confidence, Confidence_Reason and
    Crop_Quality_Status.

    Order matters. The most ACTIONABLE reason comes first: "no number was
    read" tells a person what to do, where "confidence zero" only tells them
    not to.
    """
    table = STILL_WRONG if still_wrong is None else still_wrong
    if shared_with:
        return ("이 크롭은 %s 행과 픽셀까지 같습니다 — 상자가 두 라벨을 "
                "구분하지 못했으므로 어느 쪽 그림인지 알 수 없습니다."
                % ", ".join(shared_with))
    # THE SAME PICTURE, TWICE. Not the same file (that is `shared_with` above)
    # but the same region of the same page, reached by two rows. Counting both
    # puts one figure in the corpus twice.
    if duplicate:
        if len(duplicate) > 2 and duplicate[2] == CONFIRMED_BY_BOX:
            # THE PERSON FOUND IT - on a page where it was already counted.
            # That is an answer, not a question: the figure is held by the
            # row that lives there, and this row is the body's mention of it.
            return ("이 행의 그림을 p.%s에 그려 주셨는데, 그 그림은 그 쪽의 %s 행이 "
                    "이미 세고 있습니다 — 이 행은 그 그림을 본문에서 언급한 자리이고, "
                    "%s 행이 그 그림을 가집니다. 다시 묻지 않습니다. 이 행이 맞다고 "
                    "보시면 %s 행을 막으십시오."
                    % (duplicate[1], duplicate[0], duplicate[0], duplicate[0]))
        return ("이 행은 %s 행과 같은 쪽(p.%s)의 같은 그림을 가리킵니다 — 둘 다 세면 "
                "그 그림을 두 번 세는 것이므로 근거가 더 뚜렷한 %s 행이 그 그림을 "
                "가집니다. 이 행이 맞다고 보시면 %s 행을 막으십시오."
                % (duplicate[0], duplicate[1], duplicate[0], duplicate[0]))
    # NOT A FIGURE AT ALL - before any finding about the crop, because there
    # is no crop worth a finding: the row is the body's mention of a figure
    # that lives on the next page, where it already has a row.
    ghost = phantom_reason(row, codes, twin)
    if ghost:
        return ghost
    if key in table:
        # The crop this finding describes is gone, replaced by one the person
        # named themselves. `build_sheet2` still shows the finding on the card
        # (as a caution, via `lapsed`), so nothing is hidden - it just no
        # longer stops the count.
        if not human_cut(row):
            return table[key]
    _fail = _defect_reason(defect)
    if _fail and not human_cut(row):
        return _fail
    # WHAT SOMEBODY SAW IN THE CROP, after what the audits recorded about the
    # figure. `census.reason` is given the loaded record, never a path: this
    # module reads no files. It can only take a row out of counting - an agent
    # observation is a reason to stop, and only a person's `Human_Verdict`
    # puts one back.
    if census is not None:
        seen = _census.reason(census, row, crop_sha)
        if seen:
            return seen
    if not str(row.get("Figure_Number", "")).strip():
        return ("그림 번호를 읽지 못했습니다 — %s 사람이 번호를 정해야 합니다."
                % (row.get("Confidence_Reason") or ""))
    if str(row.get("Confidence", "")).strip() == "0.00":
        # THE SAME FINDING, SAID TWICE. Every row whose number would not parse
        # also carries confidence zero, and the machine's stated reason for
        # the zero IS the unread number. A person who types the number has
        # answered that; leaving the gate standing means the row is blocked
        # twice for one fact and no answer can ever reach it. Confidence zero
        # for any OTHER reason (one detector found the caption, the caption
        # text is too short) is untouched - a supplied number says nothing
        # about those.
        reason = str(row.get("Confidence_Reason") or "")
        if not (numbered_by_hand(row)
                and reason.startswith(UNREADABLE_NUMBER_REASON)):
            return ("기계가 스스로 신뢰도 0으로 표시한 행입니다 — %s"
                    % (reason or "사유 없음"))
    # CAN THE PICTURE BE TRACED TO ITS BOX. After the row's own defects (no
    # number, no confidence), which a person can act on directly; before the
    # crop status, because ACCEPTABLE is a measurement OF the crop and says
    # nothing about whether the crop is the one the box describes.
    if roundtrip in ROUNDTRIP_UNVERIFIABLE:
        return ROUNDTRIP_UNVERIFIABLE[roundtrip]
    # DO TWO INDEPENDENT METHODS POINT AT THIS CROP. A closed set again: an
    # agreement value this module has not heard of is a reason, not a pass.
    if agreement is not None and agreement not in AGREEMENT_COUNTABLE:
        return AGREEMENT_UNCOUNTABLE.get(
            agreement, "그림 영역 검증 결과를 해석할 수 없어 막았습니다 (%r)."
            % (agreement,))
    # THE CROP STATUS IS A CLOSED SET, so anything outside it is a value this
    # gate does not understand - and a gate that lets through what it cannot
    # read is not a gate. Listing only the dangerous statuses meant an empty
    # cell, a typo, or a status added upstream tomorrow all counted as safe.
    # `corpus_intake.CROP_QUALITY_STATUSES` is the set; ACCEPTABLE is the only
    # member that means "a person can count from this picture".
    status = str(row.get("Crop_Quality_Status", "")).strip()
    if status in COUNTABLE_CROPS:
        return ""
    if status in UNCOUNTABLE_CROPS:
        return UNCOUNTABLE_CROPS[status]
    return ("크롭 상태를 해석할 수 없어 막았습니다 (%s) — 아는 상태는 %s 뿐입니다."
            % (status or "빈 값",
               ", ".join(sorted(COUNTABLE_CROPS) + sorted(UNCOUNTABLE_CROPS))))


def shared_crop_map(digest_of_row, duplicate=None):
    """{Draft_ID: [other Draft_IDs]} for rows whose crop is byte-identical.

    Two labels resolving to the same picture means the box did not tell them
    apart, so at most one of them is that figure and nothing here knows which.
    `digest_of_row` is {Draft_ID: sha256 of the crop file}; rows with no crop
    are simply absent from it.

    EXCEPT WHEN SOMETHING HERE DOES KNOW WHICH. `duplicate` is `duplicate_map`'s
    answer: {loser: (winner, ...)}. A pair it names is ONE figure with two
    rows, and the cut snaps to the ink, so two boxes around one picture come
    out byte-identical by construction - the identity is explained, not a
    finding. Left in, it blocked the WINNER for being identical to its own
    loser: three figures a person had just drawn stayed uncounted, each
    "identical to" the row the rule had already decided was its duplicate.
    """
    duplicate = duplicate or {}

    def same_figure(a, b):
        return ((duplicate.get(a) or (None,))[0] == b
                or (duplicate.get(b) or (None,))[0] == a)

    by_digest = {}
    for draft_id, digest in digest_of_row.items():
        by_digest.setdefault(digest, []).append(draft_id)
    out = {}
    for ids in by_digest.values():
        if len(ids) > 1:
            for one in ids:
                others = sorted(x for x in ids if x != one and not same_figure(one, x))
                if others:
                    out[one] = others
    return out

# scenario: a rule changed

# scenario: a rule changed
