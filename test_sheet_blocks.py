# -*- coding: utf-8 -*-
"""Scenarios for the panel-count sheet's blocking rule.

    python3 test_sheet_blocks.py     # exit 0 = all scenarios pass

The rule decides whether a person may type a panel count against a picture, so
it is the one piece of the sheet that has to be reproducible from this
repository alone. It reads no files: the draft it is applied to comes from
publisher PDFs and cannot be published, and a safety rule that can only be
checked against data nobody else has is a safety rule nobody else can check.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import block_rules as BR                                        # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name
          + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def row(**kw):
    base = dict(Figure_Number="FIG1", Confidence="1.00", Confidence_Reason="",
                Crop_Quality_Status="ACCEPTABLE")
    base.update(kw)
    return base


print("what the sheet will not let a person count")

_ok = BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"))
check("an ordinary row with an acceptable crop takes a number", _ok == "",
      "%r" % _ok)

# ---------------------------------------------------- the audits' own findings
check("a figure an audit judged still wrong is blocked",
      BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")) != "")
check("and the message is the audit's own words, not a category",
      "FIG3" in BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")))
check("every still-wrong entry carries a reason a person can act on",
      all(len(v) > 12 for v in BR.STILL_WRONG.values()))
check("the block holds even when the crop grader calls the crop fine",
      BR.blocked_reason(row(Crop_Quality_Status="ACCEPTABLE",
                            Confidence="1.00"),
                        BR.figure_key("99", "FIG1", "4")) != "")
check("a neighbouring figure in the same paper is NOT blocked by it",
      BR.blocked_reason(row(), BR.figure_key("99", "FIG2", "4")) == "")
check("nor the same figure on another page",
      BR.blocked_reason(row(), BR.figure_key("99", "FIG1", "9")) == "")

# ------------------------------- a finding is about a picture, and pictures go
# 2026-09-02: 사람이 열 행의 상자를 손으로 그렸는데 그중 둘이 계속 막혀
# 있었습니다. 막고 있던 판정은 **이제 존재하지 않는 크롭**에 대한 것이었고,
# 표가 그림 번호로만 묶여 있어 어떤 크롭보다도 오래 살았습니다. 세 항목은
# 본문에서 스스로 만료 조건을 말하고 있었는데("다시 자르면 열립니다",
# "사람이 지정하기 전에는") 코드가 그것을 읽을 수 없었습니다.
_KEY = BR.figure_key("99", "FIG1", "4")
check("a finding still blocks a crop nobody replaced",
      BR.blocked_reason(row(), _KEY) != "")
check("a machine recut does NOT lapse it (agreeing with itself is not looking)",
      BR.blocked_reason(row(Crop_Source="VALIDATED_REGION"), _KEY) != "")
check("but a box the person drew themselves does",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _KEY) == "",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _KEY))
check("so does a proposer's box the person picked and the crop was recut from",
      all(BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_%s" % c), _KEY) == ""
          for c in ("PDF", "RASTER")))
# TEXT은 "지금 크롭이 맞다"입니다 - 판정이 틀렸다고 말한 바로 그 그림에 대해서.
# 그림이 바뀐 것이 아니라 사람의 두 말이 부딪친 것이고, 그것은 하네스가 정할
# 일이 아닙니다. `apply_validated`가 TEXT에는 `Crop_Source`를 남기지 않으므로
# 이 행은 막힌 채로 남습니다.
check("choosing TEXT does not lapse it - the picture did not change",
      BR.blocked_reason(row(Crop_Source=""), _KEY) != "")
check("nor does a crop source the rule has never heard of",
      BR.blocked_reason(row(Crop_Source="SOMETHING_ELSE"), _KEY) != "")
check("nor one that merely mentions a human choice",
      BR.blocked_reason(row(Crop_Source="WAS_HUMAN_CHOICE_DRAWN"), _KEY) != "")
check("the lapse does not open a row nothing was ever recorded against",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"),
                        BR.figure_key("99", "FIG9", "4")) == "")
# 만료는 삭제가 아닙니다: 시트가 카드에 남길 수 있도록 무엇이 만료됐는지
# 돌려줘야 하고, 만료되지 않은 행에 대해서는 아무것도 말하지 않아야 합니다.
check("a lapsed finding is still readable, so the card can show it",
      "PSD" in BR.lapsed(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _KEY))
check("nothing is reported lapsed while it still blocks",
      BR.lapsed(row(Crop_Source="VALIDATED_REGION"), _KEY) == "")
check("nor for a figure with no finding at all",
      BR.lapsed(row(Crop_Source="HUMAN_CHOICE_DRAWN"),
                BR.figure_key("99", "FIG9", "4")) == "")
check("the choice that cut the crop is named, so the card can say which",
      BR.human_cut(row(Crop_Source="HUMAN_CHOICE_RASTER")) == "RASTER"
      and BR.human_cut(row(Crop_Source="VALIDATED_REGION")) == ""
      and BR.human_cut(row()) == "")
# 만료는 STILL_WRONG 한 곳에만 적용됩니다. 다른 관문들은 지금 그림에 대한
# 사실이지 지나간 그림에 대한 판정이 아닙니다 - 사람이 상자를 그렸다고
# 그림 번호가 읽히거나 크롭이 두 라벨을 구분하게 되지는 않습니다.
check("drawing a box does not lapse the other gates",
      all(BR.blocked_reason(r, BR.figure_key("99", "FIG9", "4")) != ""
          for r in (row(Crop_Source="HUMAN_CHOICE_DRAWN", Figure_Number=""),
                    row(Crop_Source="HUMAN_CHOICE_DRAWN", Confidence="0.00"),
                    row(Crop_Source="HUMAN_CHOICE_DRAWN",
                        Crop_Quality_Status="THIN_CROP"))))
# 2차 감사의 FAIL도 같은 문장입니다 - 누군가 크롭 하나를 보고 무엇이 잘못됐는지
# 적은 것. 한쪽은 만료되고 한쪽은 영원한 이유가 없고, 실제로 그 차이 때문에
# 554행이 "FIG4 막대그래프가 보이지 않음"으로 막힌 채였습니다 - 사람이 직접
# 그린 상자 안에는 그 막대그래프밖에 없는데도.
_D = dict(classification="FAIL", kind="wrong_region", screen="대부분 빈 영역")
_NOKEY = BR.figure_key("99", "FIG9", "4")
check("a FAIL defect still blocks a crop nobody replaced",
      BR.blocked_reason(row(), _NOKEY, defect=_D) != "")
check("a machine recut does not lapse a FAIL defect either",
      BR.blocked_reason(row(Crop_Source="VALIDATED_REGION"), _NOKEY,
                        defect=_D) != "")
check("but a box the person drew themselves lapses it",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _NOKEY,
                        defect=_D) == "",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _NOKEY, defect=_D))
check("and the card can still show what the audit had said",
      "대부분 빈 영역" in BR.lapsed(row(Crop_Source="HUMAN_CHOICE_DRAWN"),
                                _NOKEY, defect=_D))
check("a WARNING is not a block, so it is not reported as lapsed either",
      BR.lapsed(row(Crop_Source="HUMAN_CHOICE_DRAWN"), _NOKEY,
                defect=dict(_D, classification="WARNING")) == "")
check("nothing is reported lapsed while the defect still blocks",
      BR.lapsed(row(Crop_Source="VALIDATED_REGION"), _NOKEY, defect=_D) == "")
check("nor a crop shared with another label",
      BR.blocked_reason(row(Crop_Source="HUMAN_CHOICE_DRAWN"),
                        BR.figure_key("99", "FIG9", "4"),
                        shared_with=("X_D002",)) != "")

_NOKEY_A = BR.figure_key("99", "FIG9", "4")

# ============================ 한 그림을 두 행이 세는 것 ============================
# 2026-09-03: 사람이 막힌 210행에 답한 뒤, 26쌍이 **같은 그림**을 두 번 세게
# 됐습니다. 26쌍 전부 상자가 겹쳤고(IoU 0.54~0.97) 겹치지 않는 쌍은 하나도
# 없었습니다. 캡션 문장으로는 가릴 수 없었습니다 — "Fig. 2). However, blood
# electrolytes…"는 본문이고 "Fig. 2 Protocol of centrifuge"는 캡션인데, 앞을
# 잡는 정규식은 뒤도 절반쯤 잡습니다. 가릴 수 있는 것은 상자입니다.
def _r(did, doc="D", fig="FIG1", page="3", box="100,100,300,300", **kw):
    base = dict(Draft_ID=did, Source_Document_ID=doc, Figure_Number=fig,
                Page=page, Figure_BBox=box)
    base.update(kw)
    return base


_dup = BR.duplicate_map([
    _r("A", box="100,100,300,300", Crop_Source=""),                    # 탐지기가 놓음
    _r("B", box="105,102,298,305", Crop_Source="HUMAN_CHOICE_DRAWN"),  # 사람이 그림
])
check("겹치는 두 행 중 하나가 진다", set(_dup) == {"B"}, _dup)
check("이긴 행과 쪽을 이름으로 말한다", _dup["B"] == ("A", "3"), _dup.get("B"))
check("근거가 뚜렷한 쪽이 이긴다 (탐지기 > 사람이 그림)",
      BR.claim_rank(_r("x", Crop_Source="")) >
      BR.claim_rank(_r("x", Crop_Source="HUMAN_CHOICE_DRAWN")))
check("사람이 제안 상자를 고른 것이 손으로 그린 것보다 앞선다",
      BR.claim_rank(_r("x", Crop_Source="HUMAN_CHOICE_RASTER")) >
      BR.claim_rank(_r("x", Crop_Source="HUMAN_CHOICE_DRAWN")))
check("자기 쪽을 떠나 그린 행이 가장 약하다",
      BR.claim_rank(_r("x", Crop_Source="HUMAN_CHOICE_DRAWN", Moved_From_Page="2")) <
      BR.claim_rank(_r("x", Crop_Source="HUMAN_CHOICE_DRAWN")))
_dup2 = BR.duplicate_map([
    _r("B", box="105,102,298,305", Crop_Source="HUMAN_CHOICE_DRAWN"),
    _r("A", box="100,100,300,300", Crop_Source="HUMAN_CHOICE_DRAWN", Moved_From_Page="2"),
])
check("약한 쪽이 지고, 목록 순서와 무관하다", set(_dup2) == {"A"}, _dup2)
_tie = BR.duplicate_map([
    _r("Z", box="100,100,300,300", Crop_Source="HUMAN_CHOICE_DRAWN"),
    _r("Y", box="102,101,299,302", Crop_Source="HUMAN_CHOICE_DRAWN"),
])
check("근거가 같으면 문서에서 앞선 행이 가진다 (그림을 잃지 않게)",
      set(_tie) == {"Z"} and _tie["Z"][0] == "Y", _tie)
# 겹치지 않으면 다른 그림입니다 - 한 쪽에 같은 라벨이 둘 있는 경우가 실제로 있고,
# 그것까지 막으면 진짜 그림이 사라집니다.
check("겹치지 않는 두 상자는 중복이 아니다",
      BR.duplicate_map([_r("A", box="40,40,200,200"),
                        _r("B", box="300,300,500,500")]) == {})
check("다른 쪽이면 중복이 아니다",
      BR.duplicate_map([_r("A", page="3"), _r("B", page="4")]) == {})
check("다른 그림 번호면 중복이 아니다",
      BR.duplicate_map([_r("A", fig="FIG1"), _r("B", fig="FIG2")]) == {})
check("다른 문서면 중복이 아니다",
      BR.duplicate_map([_r("A", doc="D1"), _r("B", doc="D2")]) == {})
check("번호를 못 읽은 행은 짝지을 수 없다",
      BR.duplicate_map([_r("A", fig=""), _r("B", fig="")]) == {})
check("상자가 없는 행도 짝지을 수 없다",
      BR.duplicate_map([_r("A", box=""), _r("B", box="")]) == {})
# 세 행이 한 그림을 가리키면 하나만 남습니다.
_three = BR.duplicate_map([_r("A", box="100,100,300,300", Crop_Source=""),
                           _r("B", box="104,104,301,301", Crop_Source="HUMAN_CHOICE_DRAWN"),
                           _r("C", box="98,99,299,298", Crop_Source="HUMAN_CHOICE_DRAWN")])
check("셋이 한 그림을 가리키면 둘이 진다", set(_three) == {"B", "C"}, _three)
# 한 쪽에 같은 라벨의 다른 그림이 둘 있고, 그중 하나에 중복이 붙는 경우
_mixed = BR.duplicate_map([_r("A", box="40,40,200,200", Crop_Source=""),
                           _r("B", box="44,44,204,204", Crop_Source="HUMAN_CHOICE_DRAWN"),
                           _r("C", box="300,300,500,500", Crop_Source="")])
check("떨어져 있는 세 번째 행은 말려들지 않는다", set(_mixed) == {"B"}, _mixed)

check("중복인 행은 막힌다",
      BR.blocked_reason(row(), _NOKEY_A, duplicate=("OTHER_D005", "7")) != "")
check("그 이유가 이긴 행과 쪽, 그리고 바꾸는 법을 말한다",
      all(s in BR.blocked_reason(row(), _NOKEY_A, duplicate=("OTHER_D005", "7"))
          for s in ("OTHER_D005", "p.7", "두 번", "막으십시오")))
check("중복은 상자를 그려도 풀리지 않는다 (상자가 바로 그 원인이다)",
      not BR.box_would_open(row(), _NOKEY_A, duplicate=("OTHER_D005", "7")))
check("중복이 아니면 이 관문은 아무 말도 하지 않는다",
      BR.blocked_reason(row(), _NOKEY_A, duplicate=None) == "")

# 사람이 막은 행은 그림을 갖지 않으므로 이 겨루기에 끼지 못합니다. 메시지가
# "이 행이 맞다고 보시면 이긴 행을 막으십시오"라고 약속하는데, 막힌 행이 탐지기
# 순위를 그대로 들고 계속 이기면 그 약속은 빈말입니다.
_two = [_r("A", box="100,100,300,300", Crop_Source=""),
        _r("B", box="105,102,298,305", Crop_Source="HUMAN_CHOICE_DRAWN")]
check("이긴 행을 사람이 막으면 진 행은 더 이상 중복이 아니다",
      BR.duplicate_map(_two, blocked_ids={"A"}) == {},
      "%s" % BR.duplicate_map(_two, blocked_ids={"A"}))
check("막힌 행은 중복으로 지지도 않는다 (가진 그림이 없다)",
      BR.duplicate_map(_two, blocked_ids={"B"}) == {},
      "%s" % BR.duplicate_map(_two, blocked_ids={"B"}))
check("막힌 행이 없으면 예전과 같다",
      BR.duplicate_map(_two, blocked_ids=()) == {"B": ("A", "3")})
_thr = [_r("A", box="100,100,300,300", Crop_Source=""),
        _r("B", box="104,104,301,301", Crop_Source="HUMAN_CHOICE_DRAWN"),
        _r("C", box="98,99,299,298", Crop_Source="HUMAN_CHOICE_RASTER")]
check("셋 중 이긴 행을 막으면 다음 근거가 그 그림을 가진다",
      BR.duplicate_map(_thr, blocked_ids={"A"}) == {"B": ("C", "3")},
      "%s" % BR.duplicate_map(_thr, blocked_ids={"A"}))

# 사람의 상자가 다른 쪽에서 그림을 찾았고, 그 쪽의 행이 이미 세고 있을 때.
# `apply_validated`가 적어 둔 것을 읽어 이유로 바꿉니다.
_conf = BR.confirmed_duplicates([
    {"Draft_ID": "X_D003", "Duplicate_Of": "X_D004", "Duplicate_Page": "6"},
    {"Draft_ID": "X_D009", "Duplicate_Of": "", "Duplicate_Page": ""},
    {"Draft_ID": "X_D010"}])
check("적어 둔 중복만 읽고, 사람의 상자가 찾은 것으로 표시한다",
      _conf == {"X_D003": ("X_D004", "6", BR.CONFIRMED_BY_BOX)}, "%s" % _conf)
_why_c = BR.blocked_reason(row(), _NOKEY_A, duplicate=("X_D004", "6", BR.CONFIRMED_BY_BOX))
check("사람이 찾은 중복은 그렇게 말한다 - 그린 쪽, 세는 행, 다시 묻지 않음",
      all(t in _why_c for t in ("p.6", "X_D004", "그려 주셨는데", "다시 묻지 않습니다", "막으십시오")),
      _why_c)
check("그리고 기계가 찾은 중복의 문장과는 다르다",
      _why_c != BR.blocked_reason(row(), _NOKEY_A, duplicate=("X_D004", "6")))
check("사람이 찾은 중복도 상자로는 풀리지 않는다",
      not BR.box_would_open(row(), _NOKEY_A,
                            duplicate=("X_D004", "6", BR.CONFIRMED_BY_BOX)))

# ------------------ 번호가 숫자로 안 읽히는 줄이야말로 본문 문장일 때가 많습니다
# 본문 문장 판정이 `\d+`에 키를 걸고 있어서, 번호가 숫자로 안 읽히는 줄 - 바로
# 그 판정이 가장 필요한 줄 - 을 하나도 보지 못했습니다. run2의 여덟 행이 전부
# 그랬습니다: `Figures 1 and 2 show...`, `Fig. I shows that...`, `Figs 3 and 4.`
check("복수형 문장을 본문으로 읽는다",
      BR.body_reference("Figures 1 and 2 show the contrasting effects"))
check("OCR이 1을 l이나 I로 읽은 것도 본문으로 읽는다",
      BR.body_reference("Fig. I shows that head-down tilt did not")
      and BR.body_reference("Figs l and 2 show"))
check("여러 그림을 부르는 줄은 동사가 없어도 문장이다",
      BR.body_reference("Figs 3 and 4. All the LBNP tests caused"))
check("괄호로 닫히는 인용도 문장이다",
      BR.body_reference("Figures 1 &2) which would suggest that"))
# 그리고 진짜 캡션은 여전히 캡션입니다 - 이 판정이 캡션을 삼키면 그림이 사라집니다.
for _cap in ("Fig. 1. Mean arterial pressure during tilt",
             "Figure 3 Protocol of the centrifuge run",
             "Fig. 2 Protocol of centrifuge",
             "Figure 10. Heart rate and blood pressure",
             "Fig.l. Mean changes (Mean±SE) in time and frequency"):
    check("진짜 캡션은 본문으로 읽지 않는다: %s" % _cap[:28],
          not BR.body_reference(_cap), _cap)

check("문장이 부르는 그림 번호를 전부 읽는다",
      BR.mentioned_figures("Figures 2, 3, and 4 show time courses")
      == ("FIG2", "FIG3", "FIG4"),
      "%s" % (BR.mentioned_figures("Figures 2, 3, and 4 show time courses"),))
check("마지막 앞의 ', and'가 그림 하나를 삼키지 않는다",
      len(BR.mentioned_figures("Figures 1, 2, 3 and 4 were")) == 4,
      "%s" % (BR.mentioned_figures("Figures 1, 2, 3 and 4 were"),))
check("l과 I는 1로 읽는다",
      BR.mentioned_figures("Fig. I shows that") == ("FIG1",))
check("캡션에서는 아무 번호도 읽지 않는다",
      BR.mentioned_figures("Fig. 2 Protocol of centrifuge") == ())

# 그 그림을 이미 누가 세고 있는가 - 사람에게 보여 줄 사실이지 판정이 아닙니다.
_others = [{"Draft_ID": "B", "Figure_Number": "FIG1"},
           {"Draft_ID": "C", "Figure_Number": "FIG2"},
           {"Draft_ID": "A", "Figure_Number": ""}]
_line = {"Draft_ID": "A", "Caption_Text": "Figures 1 and 2 show the effects"}
check("문장이 부르는 그림을 세고 있는 행을 찾아 준다",
      BR.mentions_held(_line, _others, {"B": "0", "C": "0"})
      == (("FIG1", "B"), ("FIG2", "C")),
      "%s" % (BR.mentions_held(_line, _others, {"B": "0", "C": "0"}),))
check("막힌 행은 '세고 있다'로 치지 않는다",
      BR.mentions_held(_line, _others, {"B": "0", "C": "1"}) == (("FIG1", "B"),),
      "%s" % (BR.mentions_held(_line, _others, {"B": "0", "C": "1"}),))
# "0"은 비어 있지 않은 문자열입니다 - 참거짓으로 읽으면 모든 행이 막힌 것이
# 되고, 이 검사는 조용히 아무것도 돌려주지 않습니다.
check("막힘 표시는 참거짓이 아니라 값으로 읽는다",
      BR.mentions_held(_line, _others, {"B": "0", "C": "0"}) != ()
      and BR.BLOCKED_MARK == "1")
check("자기 자신은 세고 있는 행이 아니다",
      BR.mentions_held({"Draft_ID": "B", "Caption_Text": "Figures 1 and 2 show"},
                       _others, {"B": "0", "C": "0"}) == (("FIG2", "C"),),
      "%s" % (BR.mentions_held({"Draft_ID": "B",
                                "Caption_Text": "Figures 1 and 2 show"},
                               _others, {"B": "0", "C": "0"}),))
check("진짜 캡션에는 아무것도 붙이지 않는다",
      BR.mentions_held({"Draft_ID": "A", "Caption_Text": "Fig. 1. Mean changes"},
                       _others, {"B": "0"}) == ())
# 그리고 이것은 막지 않습니다. 캡션인지 문장인지는 글자만으로 정할 수 없고,
# 이 저장소는 그 교훈을 이미 한 번 치렀습니다.
check("이 사실은 그 자체로 행을 막지 않는다",
      BR.blocked_reason(row(), _NOKEY_A) == "")

# ---------------------------- 사람이 채우면 풀리는가 - 상자·번호를 따로 묻지 않는다
# 번호를 못 읽어 막힌 8행 중 7행은 크롭도 얇습니다. 한 번에 하나씩 물으면 두 답이
# 다 "아니오"이고, 페이지는 "상자를 그려도 소용없습니다"라고만 하고 번호를 적을
# 자리는 주지 않았습니다. 사람은 두 번 답을 시도했습니다 - 한 번은 메모 칸에,
# 한 번은 제안자를 골라서 - 둘 다 Figure_Number에 닿을 수 없었습니다.
_UNREAD = (BR.UNREADABLE_NUMBER_REASON
           + " 's', which is not a number; a person has to supply it")
_no_num = row(Figure_Number="", Confidence="0.00", Confidence_Reason=_UNREAD,
              Crop_Quality_Status="THIN_CROP")
check("번호도 크롭도 없는 행은 둘 다 필요하다고 답한다",
      BR.repairs_that_open(_no_num, _NOKEY_A)
      == (BR.REPAIR_BOX, BR.REPAIR_NUMBER),
      "%s" % (BR.repairs_that_open(_no_num, _NOKEY_A),))
check("그래서 상자도 번호도 각각 '필요한 것'으로 보고된다",
      BR.box_would_open(_no_num, _NOKEY_A)
      and BR.number_would_open(_no_num, _NOKEY_A))
check("크롭이 멀쩡하면 번호만 필요하다",
      BR.repairs_that_open(dict(_no_num, Crop_Quality_Status="ACCEPTABLE"),
                           _NOKEY_A) == (BR.REPAIR_NUMBER,))
check("번호가 있으면 상자만 필요하다",
      BR.repairs_that_open(dict(_no_num, Figure_Number="FIG1", Confidence="1.00"),
                           _NOKEY_A) == (BR.REPAIR_BOX,))
check("아무것도 필요 없으면 빈 튜플이다 (이미 열린 행)",
      BR.repairs_that_open(row(), _NOKEY_A) == ())

# 같은 사실을 두 번 말하는 문. 번호를 못 읽은 행은 **전부** 신뢰도 0이고, 그
# 0의 사유가 바로 읽지 못한 번호입니다 - 사람이 번호를 적으면 그 사유는 답해진
# 것입니다. 이것이 없으면 번호를 받아도 행은 여전히 막히고, 어떤 답도 닿지
# 못합니다 (run2에서 8행 전부).
check("사람이 번호를 적으면 '번호를 못 읽어 신뢰도 0'은 더 이상 막지 않는다",
      BR.blocked_reason(dict(_no_num, Figure_Number="FIG3",
                             Number_Source=BR.NUMBER_BY_HUMAN,
                             Crop_Quality_Status="ACCEPTABLE"), _NOKEY_A) == "",
      BR.blocked_reason(dict(_no_num, Figure_Number="FIG3",
                             Number_Source=BR.NUMBER_BY_HUMAN,
                             Crop_Quality_Status="ACCEPTABLE"), _NOKEY_A))
check("기계가 번호를 넣은 것으로는 그 문이 열리지 않는다 (사람이 적어야 한다)",
      "신뢰도 0" in BR.blocked_reason(
          dict(_no_num, Figure_Number="FIG3",
               Crop_Quality_Status="ACCEPTABLE"), _NOKEY_A))
_other0 = dict(_no_num, Figure_Number="FIG3", Number_Source=BR.NUMBER_BY_HUMAN,
               Crop_Quality_Status="ACCEPTABLE",
               Confidence_Reason="only POPPLER_BBOX_LAYOUT found this caption")
check("다른 사유의 신뢰도 0은 번호를 적어도 그대로 막는다",
      "신뢰도 0" in BR.blocked_reason(_other0, _NOKEY_A),
      BR.blocked_reason(_other0, _NOKEY_A)[:50])
check("그리고 그런 행은 사람이 채울 것이 없다고 답한다",
      BR.repairs_that_open(_other0, _NOKEY_A) == ())
# 사유 문자열은 인테이크의 것입니다 - 두 곳에서 손으로 맞추면 어긋납니다.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from corpus_intake import UNREADABLE_NUMBER_REASON as _CI_REASON
    check("차단 규칙이 아는 사유 문자열이 인테이크의 것과 같다",
          BR.UNREADABLE_NUMBER_REASON == _CI_REASON,
          (BR.UNREADABLE_NUMBER_REASON, _CI_REASON))
except ImportError:                                       # pragma: no cover
    print("  SKIP 인테이크를 임포트할 수 없어 사유 문자열을 대조하지 못했습니다")

# ------------------------------ 본문에서 그림을 언급한 문장이 캡션으로 잡힌 행
# 2026-09-03, 사람의 질문 "설명은 뒷장에 있고 그림은 앞장에 있는 경우도 있지
# 않나"에서 나온 것입니다. 57행의 이웃 쪽에 탐지기를 돌리니 15행 옆에 그림이
# 있었고, 그 행들의 "캡션"은 "Figure 4 shows the hemodynamic and neural
# responses" - Results의 문장이었습니다. 진짜 캡션은 옆 쪽 그림 밑에 있고,
# 그중 8행은 이미 자기 행을 갖고 있었습니다. 이 행을 세면 두 번 세는 것입니다.
_NC = ("NO_CANDIDATE", "NO_CANDIDATE")
_TW = ("DOC_X_D005", 5)
_ghost = row(Caption_Text="Figure 4 shows the hemodynamic and neural responses",
             Page="4")
check("본문 문장 + 이 쪽에 후보 없음 + 옆 쪽에 같은 그림 행 → 막힌다",
      BR.blocked_reason(_ghost, _NOKEY_A, codes=_NC, twin=_TW) != "")
check("그 이유가 어느 행이 진짜인지 말한다",
      "D005" in BR.blocked_reason(_ghost, _NOKEY_A, codes=_NC, twin=_TW)
      and "두 번" in BR.blocked_reason(_ghost, _NOKEY_A, codes=_NC, twin=_TW))
# 세 조건은 각각 무죄입니다 - 하나라도 빠지면 막지 않습니다.
check("옆 쪽에 같은 그림 행이 없으면 막지 않는다 (그 그림은 회수해야 할 손실)",
      BR.blocked_reason(_ghost, _NOKEY_A, codes=_NC, twin=None) == "")
check("이 쪽에서 탐지기가 그림을 찾았으면 막지 않는다",
      BR.blocked_reason(_ghost, _NOKEY_A, codes=("OK", "OK"), twin=_TW) == ""
      and BR.blocked_reason(_ghost, _NOKEY_A, codes=("NO_CANDIDATE", "OK"),
                            twin=_TW) == "")
check("캡션이 문장처럼 읽히지 않으면 막지 않는다",
      BR.blocked_reason(row(Caption_Text="Fig. 4. Hemodynamic responses (n=8)."),
                        _NOKEY_A, codes=_NC, twin=_TW) == "")
# 진짜 캡션을 문장으로 쓰는 책이 run2에 있습니다 - "Fig. 1 Shows the Transient
# Inspiratory Occlusion (TIO) paradigm". 그 그림은 캡션 바로 위에 있고 탐지기가
# 찾습니다. 문장 패턴만으로 막았다면 그 두 행이 잘못 막혔을 것입니다.
check("문장형 진짜 캡션은 탐지기가 그림을 찾았으므로 막히지 않는다",
      BR.blocked_reason(row(Caption_Text="Fig. 1 Shows the Transient Inspiratory "
                                         "Occlusion (TIO) paradigm"),
                        _NOKEY_A, codes=("OK", "OK"), twin=("DOC_D002", 2)) == "")
check("탐지기 코드가 없으면(검증표 없음) 막지 않는다",
      BR.blocked_reason(_ghost, _NOKEY_A, codes=(), twin=_TW) == "")
for _t in ("Fig. 5, and separate analysis for pre- and post-bed rest",
           "Figure 1 contrasts the depressive effect of halothane",
           "Figure 2, bottom, shows the evolution of the spontaneous",
           "FIGURE 3 illustrates the time course",
           "Figure 2 confirms the expected effect of hypoxia"):
    check("본문 문장으로 읽힌다: %r" % _t[:28], BR.body_reference(_t))
for _t in ("Fig. 3. Pressure-emptying curves for the leg (A) and the arm (B)",
           "Figure 2 | The DI model in MEDES space clinic",
           "Fig. 6 Preflight and postspaceflight distributions of delay",
           ""):
    check("캡션으로 읽힌다: %r" % _t[:28], not BR.body_reference(_t))
check("상자를 그려도 유령 행은 풀리지 않는다 (그릴 것은 옆 쪽 그림뿐)",
      not BR.box_would_open(_ghost, _NOKEY_A, codes=_NC, twin=_TW))
check("유령 판정은 다른 판정보다 먼저다 (크롭에 대한 판정은 그림이 있어야 뜻이 있다)",
      "두 번" in BR.blocked_reason(dict(_ghost, Crop_Source="HUMAN_CHOICE_DRAWN"),
                                  BR.figure_key("99", "FIG1", "4"),
                                  codes=_NC, twin=_TW))
# 이웃 찾기: 같은 문서, 같은 번호, 바로 옆 쪽만. 350쪽짜리 책은 장마다 FIG1이
# 있어서 번호만으로는 마흔 개가 잡히고, 뜻이 있는 것은 옆 쪽 하나뿐입니다.
_draft = [dict(Draft_ID="B_D001", Source_Document_ID="B", Figure_Number="FIG1", Page="30"),
          dict(Draft_ID="B_D077", Source_Document_ID="B", Figure_Number="FIG1", Page="209"),
          dict(Draft_ID="B_D079", Source_Document_ID="B", Figure_Number="FIG1", Page="210"),
          dict(Draft_ID="B_D080", Source_Document_ID="B", Figure_Number="FIG2", Page="210"),
          dict(Draft_ID="C_D001", Source_Document_ID="C", Figure_Number="FIG1", Page="211"),
          dict(Draft_ID="B_D999", Source_Document_ID="B", Figure_Number="FIG1", Page="")]
_tm = BR.twin_map(_draft)
check("옆 쪽의 같은 번호 행을 찾는다", _tm.get("B_D077") == ("B_D079", 210), _tm.get("B_D077"))
check("그리고 반대 방향으로도", _tm.get("B_D079") == ("B_D077", 209))
check("멀리 있는 같은 번호는 이웃이 아니다", "B_D001" not in _tm)
check("다른 번호는 이웃이 아니다", "B_D080" not in _tm)
check("다른 문서는 이웃이 아니다", "C_D001" not in _tm)
check("쪽 번호가 없는 행은 조용히 건너뛴다", "B_D999" not in _tm)

# ------------------------------- 상자를 그리면 이 행이 풀리는가 (규칙에게 묻는다)
# 판정 페이지가 210개의 막힌 행을 내놓으면서 "상자를 그리십시오"라고 말할 때,
# 그 말이 참인 행에만 그렇게 말해야 합니다. 이유 문자열 목록을 따로 두면 관문이
# 바뀔 때마다 거짓말이 되므로, 규칙에게 직접 물어봅니다.
# 이 시나리오는 이름과 다른 것을 재고 있었습니다 - `agreement`를 넘기지 않아
# 막히지도 않은 행을 재면서 "합의가 없어 막힌 행"이라고 불렀고, 옛 구현이 막히지
# 않은 행에 무조건 참을 돌려주는 바람에 통과했습니다. 관문을 실제로 켭니다.
check("합의가 없어 막힌 행은 상자로 풀린다",
      BR.box_would_open(row(), _NOKEY_A, agreement="NONE"))
check("크롭이 얇아 막힌 행도 상자로 풀린다 (다시 재니까)",
      BR.box_would_open(row(Crop_Quality_Status="THIN_CROP"), _NOKEY_A))
check("크롭이 그림을 자르고 있어도 상자로 풀린다",
      BR.box_would_open(row(Crop_Quality_Status="EDGE_CLIPPED"), _NOKEY_A))
check("옛 판정으로 막힌 행도 상자로 풀린다",
      BR.box_would_open(row(), BR.figure_key("99", "FIG1", "4")))
check("2차 감사 FAIL로 막힌 행도 상자로 풀린다",
      BR.box_would_open(row(), _NOKEY_A, defect=_D))
check("크롭이 다른 라벨과 픽셀까지 같아 막힌 행도 상자로 풀린다",
      BR.box_would_open(row(), _NOKEY_A, shared_with=("X_D002",)))
# 그리고 풀리지 않는 것들 - 여기서 참이라고 말하면 사람이 헛수고를 합니다.
check("그림 번호를 읽지 못한 행은 상자로 풀리지 않는다",
      not BR.box_would_open(row(Figure_Number=""), _NOKEY_A))
check("신뢰도 0인 행도 상자로 풀리지 않는다",
      not BR.box_would_open(row(Confidence="0.00"), _NOKEY_A))
# 막히지 않은 행은 사람이 채울 것이 없습니다 - 옛 구현은 여기에 "상자가 도움이
# 된다"고 답했는데, 물어본 적 없는 질문에 대한 답이었습니다.
check("막히지 않은 행은 아무것도 필요하지 않다고 답한다",
      BR.repairs_that_open(row(), _NOKEY_A) == ()
      and not BR.box_would_open(row(), _NOKEY_A))
# 시험용 행을 더럽히지 않는가 - 이 함수는 물어보기만 해야 합니다.
_probe = row(Crop_Quality_Status="THIN_CROP")
BR.box_would_open(_probe, _NOKEY_A)
check("물어보는 것이 그 행을 고치지는 않는다",
      _probe["Crop_Quality_Status"] == "THIN_CROP" and "Crop_Source" not in _probe,
      _probe)

# ------------------------------------------------- the key is not the ordinal
check("the key is what the page prints, so a rebuilt draft still blocks it",
      BR.figure_key("437", "fig2", " 176 ")
      == BR.figure_key(437, "FIG2", 176))
check("every finding is keyed by (pid, label, page), never by an ordinal",
      all(isinstance(k, tuple) and len(k) == 3
          and not any(str(p).startswith("_D") or "_D0" in str(p) for p in k)
          for k in BR.STILL_WRONG))
check("a Draft_ID handed in as the key matches nothing",
      BR.blocked_reason(row(), "978_1_4419_5692_7_D058") == "")
check("while the figure that Draft_ID used to name is still blocked",
      BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")) != "")

# ------------------------------------------------------ a confirmed defect row
_fail = dict(classification="FAIL", kind="mixed_figures",
             screen="FIG2의 산점도와 왼쪽 FIG1의 막대그래프가 함께 보임")
check("a FAIL defect blocks the row it names",
      BR.blocked_reason(row(), BR.figure_key("36", "FIG2", "4"),
                        defect=_fail) != "")
check("and names the kind in the message",
      "다른 그림 혼입" in BR.blocked_reason(row(), BR.figure_key("36", "FIG2", "4"),
                                     defect=_fail))
check("a WARNING defect does not block on its own",
      BR.blocked_reason(row(), BR.figure_key("36", "FIG1", "4"),
                        defect=dict(classification="WARNING", kind="x",
                                    screen="y")) == "")

# ------------------------------------------------- what the machine itself said
check("a row with no figure number is blocked",
      BR.blocked_reason(row(Figure_Number=""),
                        BR.figure_key("1", "", "2")) != "")
check("and the message says a person has to supply the number",
      "번호를 정해야" in BR.blocked_reason(row(Figure_Number=""),
                                    BR.figure_key("1", "", "2")))
check("the missing number is reported before the zero confidence, because it "
      "is the reason a person can act on",
      "번호를 읽지 못했습니다" in BR.blocked_reason(
          row(Figure_Number="", Confidence="0.00",
              Confidence_Reason="설명"), BR.figure_key("1", "", "2")))
check("a numbered row the machine put at zero confidence is blocked",
      BR.blocked_reason(row(Confidence="0.00",
                            Confidence_Reason="두 판독기가 갈렸습니다"),
                        BR.figure_key("1", "FIG1", "2")) != "")
check("and carries the machine's own reason",
      "두 판독기가 갈렸습니다" in BR.blocked_reason(
          row(Confidence="0.00", Confidence_Reason="두 판독기가 갈렸습니다"),
          BR.figure_key("1", "FIG1", "2")))
check("a low but non-zero confidence does NOT block - the sheet shows it "
      "instead, and a person decides",
      BR.blocked_reason(row(Confidence="0.40"),
                        BR.figure_key("1", "FIG1", "2")) == "")

# ------------------------------------------------------------ the crop verdict
for status in ("EDGE_CLIPPED", "THIN_CROP", "NO_CROP"):
    check("a %s crop takes no number" % status,
          BR.blocked_reason(row(Crop_Quality_Status=status),
                            BR.figure_key("1", "FIG1", "2")) != "")
check("every uncountable crop verdict has a message",
      all(v.strip() for v in BR.UNCOUNTABLE_CROPS.values()))
# A GATE THAT PASSES WHAT IT CANNOT READ IS NOT A GATE. This scenario used to
# assert the opposite - that an unrecognised status fell through to countable -
# which pinned the fail-open in place. The status column is a closed set, so
# anything outside it is a value this rule does not understand, and the honest
# answer to a value it does not understand is no.
check("an unknown crop verdict is blocked, not waved through",
      BR.blocked_reason(row(Crop_Quality_Status="SOMETHING_NEW"),
                        BR.figure_key("1", "FIG1", "2")) != "")
check("an empty crop verdict is blocked too",
      BR.blocked_reason(row(Crop_Quality_Status=""),
                        BR.figure_key("1", "FIG1", "2")) != "")
check("the refusal names the value it could not read",
      "SOMETHING_NEW" in BR.blocked_reason(
          row(Crop_Quality_Status="SOMETHING_NEW"),
          BR.figure_key("1", "FIG1", "2")))
check("and ACCEPTABLE still passes, or the gate blocks everything",
      BR.blocked_reason(row(Crop_Quality_Status=BR.COUNTABLE_CROP),
                        BR.figure_key("1", "FIG1", "2")) == "")
# WIDENING WHAT MAY BE COUNTED IS A CHANGE TO A SAFETY RULE, so both members
# are named here one by one. A publisher's figure file cannot clip its figure
# or take in a neighbour - it IS the figure - which is why it counts; a crop
# from a page can do both, which is why every other crop status does not.
check("출판사 그림 파일은 계수 가능하다",
      BR.blocked_reason({"Figure_Number": "FIG1", "Confidence": "1.00",
                         "Crop_Quality_Status": "PUBLISHER_FIGURE"},
                        BR.figure_key("1", "FIG1", "2")) == "")
check("계수 가능과 계수 불가는 겹치지 않는다 - 겹치면 막는 규칙이 죽는다",
      not (set(BR.COUNTABLE_CROPS) & set(BR.UNCOUNTABLE_CROPS)),
      "%s" % sorted(set(BR.COUNTABLE_CROPS) & set(BR.UNCOUNTABLE_CROPS)))
_overlap_caught = False
try:
    import importlib, types
    _src = io.open(BR.__file__, encoding="utf-8").read().replace(
        'COUNTABLE_CROPS = ("ACCEPTABLE", "PUBLISHER_FIGURE")',
        'COUNTABLE_CROPS = ("ACCEPTABLE", "PUBLISHER_FIGURE", "THIN_CROP")')
    _m = types.ModuleType("block_rules_overlap")
    exec(compile(_src, BR.__file__, "exec"), _m.__dict__)
except AssertionError:
    _overlap_caught = True
check("겹치게 만들면 모듈이 아예 열리지 않는다", _overlap_caught)

check("계수 가능한 상태는 이 둘뿐이다",
      sorted(BR.COUNTABLE_CROPS) == ["ACCEPTABLE", "PUBLISHER_FIGURE"],
      "%s" % (BR.COUNTABLE_CROPS,))
for _bad in ("PUBLISHER", "publisher_figure", "FIGURE_FILE", ""):
    check("비슷하지만 다른 값 %r은 여전히 막힌다" % _bad,
          BR.blocked_reason({"Figure_Number": "FIG1", "Confidence": "1.00",
                             "Crop_Quality_Status": _bad},
                            BR.figure_key("1", "FIG1", "2")) != "")

# THE SET THIS GATE KNOWS IS THE SET THE INTAKE WRITES. A status added upstream
# without a rule here would be blocked - safe - but silently, so this fails
# loudly instead.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
try:
    import corpus_intake as _CI
    check("every status the intake can write has a rule here",
          set(_CI.CROP_QUALITY_STATUSES)
          == set(BR.COUNTABLE_CROPS) | set(BR.UNCOUNTABLE_CROPS),
          "intake %s vs rules %s" % (sorted(_CI.CROP_QUALITY_STATUSES),
                                     sorted(set(BR.COUNTABLE_CROPS)
                                            | set(BR.UNCOUNTABLE_CROPS))))
except ImportError:
    print("  SKIP the intake status cross-check: corpus_intake did not import")

# ------------------------------------------------------- two rows, one picture
_shared = BR.shared_crop_map({"A": "d1", "B": "d1", "C": "d2"})
check("rows whose crop is byte-identical find each other",
      _shared == {"A": ["B"], "B": ["A"]}, "%s" % _shared)
check("a row with its own picture is not in the map",
      "C" not in _shared)
check("and such a row is blocked, because the box did not tell them apart",
      BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"),
                        shared_with=["OTHER_D002"]) != "")
check("the message names the row it collides with",
      "OTHER_D002" in BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"),
                                        shared_with=["OTHER_D002"]))
check("three rows sharing one picture all name the other two",
      BR.shared_crop_map({"A": "d", "B": "d", "C": "d"})["A"] == ["B", "C"])
check("an empty draft yields no collisions", BR.shared_crop_map({}) == {})
# ONE FIGURE, TWO ROWS, IDENTICAL CROPS - BY CONSTRUCTION. The cut snaps to the
# ink, so any two boxes around one picture come out byte-identical. When
# `duplicate_map` has already said the pair is one figure, the identity is
# explained, and the row that HOLDS the figure must not be blocked for
# resembling the row that does not. On 2026-09-04 three figures a person had
# just drawn stayed uncounted this way.
_dup_pair = {"B": ("A", "3")}
_expl = BR.shared_crop_map({"A": "d1", "B": "d1", "C": "d2"}, duplicate=_dup_pair)
check("a pair the duplicate rule already explains is not a collision",
      _expl == {}, "%s" % _expl)
check("the winner of that pair is therefore not blocked for it",
      BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"),
                        shared_with=_expl.get("A", ())) == "")
_expl3 = BR.shared_crop_map({"A": "d", "B": "d", "C": "d"}, duplicate=_dup_pair)
check("a third row with the same bytes is still a collision for both",
      _expl3 == {"A": ["C"], "B": ["C"], "C": ["A", "B"]}, "%s" % _expl3)
check("without the duplicate map nothing changes",
      BR.shared_crop_map({"A": "d1", "B": "d1"}, duplicate=None)
      == {"A": ["B"], "B": ["A"]})

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
