# -*- coding: utf-8 -*-
"""누가 보았는가 - 사람이 본 답과, 사람이 승인한 남의 관찰.

판정 관문(`record_identity`, `record_geometry`, `record_errorbar`)은 오래 한 가지만
받았습니다: 사람이 오버레이를(또는 원문을) 직접 보았다는 표시(`Seen_By_Person`)가
있는 답. 그 표시는 에이전트가 대신 채울 수 없고, 지금도 그렇습니다.

그런데 사람이 판단할 것을 줄이려면, 사람이 직접 보지 않은 답도 받을 길이 있어야
합니다: 에이전트가 원문을 보고 판정을 내고, 사람이 그 판정들을 묶어서 승인하는 길.
2026-10-14 run2에서 결정 페이지 143항목을 Claude가 원문 PDF로 다시 보았고, 사람은
"판정대로 기록"이라는 한 번의 답으로 그 판정들을 승인했습니다. 이 모듈은 그 두 번째
길을 정의합니다 - 그리고 두 길이 기록에서 섞이지 않게 합니다.

받는 것은 둘 중 하나입니다.

    본 답:     Seen_By_Person=1, Verified_By=본 사람
    승인된 관찰: Seen_By_Person=0, Observed_By=본 것(사람 아님), Verified_By=승인한 사람,
               Approval_Ref=그 사람이 어디서 무엇을 승인했는가

승인된 관찰은 세 칸이 모두 있어야 하고(하나라도 비면 누가 보았는지, 누가 책임지는지,
그 승인을 어디서 확인하는지 중 하나가 사라집니다), 본 것과 승인한 사람이 같아서는
안 됩니다 - 같은 사람이 보았으면 그것은 본 답이고, `Seen_By_Person=0`이라고 적는
것은 기록을 흐리게 합니다.

기록에는 세 칸이 그대로 남습니다(`APPROVAL_COLUMNS`). 나중에 누가 "이 칠은 누가
보았나"를 물으면 기록이 답합니다: 사람, 또는 사람이 승인한 무엇.
"""

TRUE = ("1", "TRUE", "YES", "Y", "T")

#: 기록이 들고 다니는 칸. 판정 파일의 열 끝에 붙습니다.
APPROVAL_COLUMNS = ("Seen_By_Person", "Observed_By", "Approval_Ref")


def is_true(v):
    return str(v or "").strip().upper() in TRUE


def seen_problems(answer, who, not_seen_why):
    """(문제 목록). 본 답이거나 온전한 승인된 관찰이면 빈 목록.

    `not_seen_why`는 관문마다 다른 말입니다("이 오버레이를 직접 봤다" / "원문에서
    직접 확인했다") - 코드는 같게, 말은 그 관문의 화면에 맞게."""
    if is_true(answer.get("Seen_By_Person")):
        return []
    observed = (answer.get("Observed_By") or "").strip()
    ref = (answer.get("Approval_Ref") or "").strip()
    if not observed and not ref:
        return [("NOT_SEEN_BY_PERSON", not_seen_why)]
    problems = []
    if not observed:
        problems.append(("APPROVAL_INCOMPLETE", "사람이 보지 않은 답인데 누가 보았는지(Observed_By)가 없습니다. "
                                                "승인은 무엇을 승인했는지가 있어야 승인입니다."))
    if not ref:
        problems.append(("APPROVAL_INCOMPLETE", "사람이 보지 않은 답인데 승인을 어디서 했는지(Approval_Ref)가 "
                                                "없습니다. 되돌아볼 곳 없는 승인은 적지 않습니다."))
    if observed and who and observed.casefold() == who.strip().casefold():
        problems.append(("OBSERVER_IS_APPROVER", "본 것(%s)과 승인한 사람이 같습니다. 직접 보았다면 "
                                                 "Seen_By_Person=1로 적는 본 답입니다." % observed))
    return problems


def provenance(answer):
    """기록에 남길 세 칸."""
    seen = is_true(answer.get("Seen_By_Person"))
    return {"Seen_By_Person": "1" if seen else "0",
            "Observed_By": "" if seen else (answer.get("Observed_By") or "").strip(),
            "Approval_Ref": "" if seen else (answer.get("Approval_Ref") or "").strip()}
