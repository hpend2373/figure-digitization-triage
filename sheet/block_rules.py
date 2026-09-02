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

import census as _census

#: What the third and fourth audits judged still wrong after the crop round,
#: keyed by what the page prints. These take no number whatever the crop
#: grader says about them - the grader is an ink measurement and the finding
#: was made by looking. Removing one requires a person comparing the crop to
#: the source and saying so.
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


def blocked_reason(row, key, defect=None, shared_with=(), still_wrong=None,
                   census=None, crop_sha="", roundtrip=None):
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
    if key in table:
        return table[key]
    if defect and str(defect.get("classification", "")).strip() == "FAIL":
        kind = str(defect.get("kind", "")).strip()
        return "2차 감사 확인 — %s: %s" % (DEFECT_KIND.get(kind, kind),
                                       defect.get("screen", ""))
    # WHAT SOMEBODY SAW IN THE CROP, after what the audits recorded about the
    # figure. `census.reason` is given the loaded record, never a path: this
    # module reads no files. It can only take a row out of counting - an agent
    # observation is a reason to stop, and only a person's `Human_Verdict`
    # puts one back.
    if census is not None:
        seen = _census.reason(census, row, crop_sha)
        if seen:
            return seen
    # CAN THE PICTURE BE TRACED TO ITS BOX. Checked before the crop status,
    # because ACCEPTABLE is a measurement OF the crop and says nothing about
    # whether the crop is the one the box describes.
    if roundtrip in ROUNDTRIP_UNVERIFIABLE:
        return ROUNDTRIP_UNVERIFIABLE[roundtrip]
    if not str(row.get("Figure_Number", "")).strip():
        return ("그림 번호를 읽지 못했습니다 — %s 사람이 번호를 정해야 합니다."
                % (row.get("Confidence_Reason") or ""))
    if str(row.get("Confidence", "")).strip() == "0.00":
        return ("기계가 스스로 신뢰도 0으로 표시한 행입니다 — %s"
                % (row.get("Confidence_Reason") or "사유 없음"))
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


def shared_crop_map(digest_of_row):
    """{Draft_ID: [other Draft_IDs]} for rows whose crop is byte-identical.

    Two labels resolving to the same picture means the box did not tell them
    apart, so at most one of them is that figure and nothing here knows which.
    `digest_of_row` is {Draft_ID: sha256 of the crop file}; rows with no crop
    are simply absent from it.
    """
    by_digest = {}
    for draft_id, digest in digest_of_row.items():
        by_digest.setdefault(digest, []).append(draft_id)
    out = {}
    for ids in by_digest.values():
        if len(ids) > 1:
            for one in ids:
                out[one] = sorted(x for x in ids if x != one)
    return out
