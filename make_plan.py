# -*- coding: utf-8 -*-
"""인테이크가 확정한 것으로 추출 계획서를 쓰고, 없는 것에 이름을 붙인다.

    python3 make_plan.py --run RUN --crop-root RUN --out PLANS \
                         --run-date 2026-09-05

파일럿 세 편은 손으로 쓰였습니다. 아흔여섯 편을 손으로 쓸 수는 없고, 손으로
쓰면 옮겨 적는 실수가 계획서 - 옮겨 적는 실수를 없애려고 있는 바로 그 문서 -
안으로 들어갑니다. 이 모듈은 인테이크가 이미 확정한 것만 계획서로 옮깁니다.

옮기지 않는 것이 이 모듈의 핵심입니다. 패널이 몇 개인지, 눈금이 어느 픽셀에
있는지, 표가 무슨 종류인지는 래스터를 눈으로 본 사람만 압니다. 그것들을
그럴듯하게 채우면 계획서는 통과하고 값은 틀립니다. 그래서 이 모듈은 그 자리를
비우되, 비운 자리마다 `compile_plan.validate_plan`이 이름을 부를 수 있는 모양으로
비웁니다 - `GEOMETRY_NOT_AUTHORED`는 "이 패널은 있고, 어디를 읽을지는 아직 아무도
쓰지 않았다"는 어휘가 이미 있는 말입니다.

검토자도 마찬가지입니다. 이 모듈이 적는 검토자는 `DEMO_IDENTITY`이고 그
증언은 `DEMO_EXAMPLE`입니다. 에이전트는 `HUMAN_CONFIRMED`를 적지 않습니다 -
사람이 보았다는 말을 사람 대신 할 수 있는 프로그램은 없습니다.
"""
import argparse
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import batch_manifests as BM                                     # noqa: E402
import caption_fulltext as CF                                    # noqa: E402
import compile_plan as CP                                        # noqa: E402
import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import kernel                                                    # noqa: E402
import record_errorbar as RE                                     # noqa: E402
import record_geometry as RG                                     # noqa: E402
import record_identity as RI                                     # noqa: E402
import record_inventory as RV                                    # noqa: E402
import record_block_reviews as RBR                               # noqa: E402

DRAFT = "figure_intake_draft.csv"
BLOCKS = "block_reasons.csv"
#: 막음 위에 얹는 답 (`record_block_reviews`, run2 2026-10-15). UNBLOCK으로 답한 행은
#: 막힌 행으로 치지 않습니다 - 막음 파일은 시트를 지을 때마다 다시 쓰여서, 그 안을
#: 고치는 것으로는 답이 남지 않습니다.
BLOCK_REVIEWS = RBR.BLOCK_REVIEWS
CAPTIONS = "caption_fulltext.csv"
DECISIONS = "errorbar_decisions.csv"
#: `record_decisions.py`가 적은 처분들. 사람이 그림을 보고 정한 것이고, 계획서가
#: 그것을 읽지 않으면 판정은 파일 안에만 있습니다.
FIGURE_DECISIONS = "figure_decisions.csv"
#: 그림 하나의 처분 (`record_dispositions`, run2 2026-10-14 R7). 같은 그림에
#: `figure_decisions.csv`의 판정이 있어도 이쪽이 이깁니다 - 나중에, 더 보고 정한 것.
FIGURE_DISPOSITIONS = "figure_dispositions.csv"
#: 패널마다 사람이 정한 결과의 이름, 또는 "결과 아님" (`record_outcomes.py`, R4).
OUTCOME_DECISIONS = "outcome_decisions.csv"
#: 한 그림에 범례가 여럿일 때 어느 패널이 어느 범례를 쓰는가 (`record_legends.py`).
LEGEND_DECISIONS = "legend_decisions.csv"
#: 계수 시트의 내보내기를 `sheet/merge_counts.py`가 합쳐 놓은 파일. 이름을
#: 새로 짓지 않습니다 - 파이프라인이 이미 쓰는 이름이 따로 있는데 여기서만
#: 다른 이름을 보면, 계수는 들어와 있는데 계획서는 영영 못 보게 됩니다.
COUNTS = "observed_panel_counts.csv"

#: 그 파일에서 수를 가져올 수 있는 유일한 상태. `SEEN_UNCOUNTABLE`은
#: "보았지만 셀 수 없다"이고 `NOT_REVIEWED`는 "아직 안 보았다"입니다 -
#: 둘 다 수가 아니고, 둘을 수로 바꾸면 그 그림은 세어진 것이 됩니다.
COUNTED = "ENTERED"

#: 수가 없는 까닭마다 사람이 다음에 할 일이 다릅니다. 아무도 보지 않은 행은
#: 세면 되지만, "보았지만 셀 수 없다"·"이 크롭은 대상 그림이 아니다"·"이
#: 차단이 틀렸다"는 **이미 답한 행**입니다. 그 세 가지에까지 "패널 계수"
#: 라고 적으면, 답한 사람에게 같은 질문을 다시 하는 대기열이 됩니다 -
#: 그리고 답한 사람은 그 줄을 보고 자기 답이 사라졌다고 읽습니다.
#: 답을 못 읽는 것과 답이 없는 것은 다릅니다.
COUNT_NEED = "패널 계수"

#: 열려 있던 행에만 붙을 수 있는 답들. 시트는 이미 답한 행을 다시 묻지
#: 않으려고 막아 두는데(`block_rules.recorded_reason`), 그 막음은 "이 행은
#: 그림이 아니다"가 아니라 "이 사람에게 또 묻지 않는다"입니다. 둘을 한 칸에
#: 담아 두어서, 계수가 끝나자 계획서의 그림이 310개에서 1개로 줄었습니다.
#: `BLOCK_CONFIRMED`·`BLOCK_DISPUTED`는 여기 없습니다 - 그 둘은 막힌 행에
#: 대고 한 답이고, 막힌 행은 여전히 막힌 행입니다.
ANSWERED_ON_AN_OPEN_ROW = ("ENTERED", "SEEN_UNCOUNTABLE", "CROP_DISPUTED")
ANSWERED_WITHOUT_A_NUMBER = {
    "SEEN_UNCOUNTABLE": "셀 수 없다고 하신 그림 — 처분 결정",
    "CROP_DISPUTED": "대상 그림이 아니라고 하신 크롭 — 처분 결정 또는 재크롭",
    "BLOCK_DISPUTED": "차단이 틀렸다고 하신 행 — 차단 재검토",
}
#: 사람의 처분이 계획서에서 무엇이 되는가. `NOT_DATA`는 셋 다 같은 뜻이라
#: 한 줄이고, 나머지는 아직 할 일이 남은 처분입니다.
DECIDED_NOT_DATA = "NOT_DATA"
#: "전부 데이터다" - 멈춰 두었던 그림이 보통 그림으로 돌아갑니다.
DECIDED_IS_DATA = "DATA"
DECIDED_NEEDS = {
    "RECROP": "다시 자르라고 하신 그림 — 재크롭",
    "COUNTABLE": "이제 셀 수 있다고 하신 그림 — 계수 다시",
    "PARTIAL": "일부 패널만 데이터라고 하신 그림 — 그 패널만 추출",
    "REDRAW": "패널을 다시 그리라고 하신 그림 — 패널 영역 다시 그리기",
}
#: 처분 파일(`figure_dispositions.csv`)의 이름이 곧 계획서의 처분인 것들. DIGITIZE는
#: `figure_decisions`의 DATA와 같은 말입니다.
DECIDED_DISPOSITION = {"DIGITIZE": "DIGITIZE", "NON_TARGET": "NON_TARGET_OUTCOME",
                       "ASSOCIATION": "ASSOCIATION_EXTRACT"}
#: 사람이 이미 처분해서, 계수·캡션 어긋남을 더 묻지 않는 그림.
SETTLED_DISPOSITIONS = ("NOT_DATA", "UNRESOLVED", "NON_TARGET_OUTCOME")
#: 오차 정의 판정이 처분인 그림의 패널 처분 (run2 2026-10-14 R6). DROP은 목표
#: 결과지만 요약 통계의 정의가 없어 닫는 것이고(397번 시험판의 선례), 그 그림을
#: UNRESOLVED에 두면 계획서는 아무도 다시 볼 일이 없는 그림을 '미정'이라 부릅니다.
ERRORBAR_DISPOSITION = {"DROP": "NO_SUMMARY_STATISTIC", "NOT_DATA": "NOT_DATA"}

READINESS = "plan_readiness.csv"
WORKSHEET = "plan_figures.csv"
#: 패널마다 한 줄: 기하는 어디까지, 정체는 어디까지, 무엇이 남았는지. 계획서는
#: 다 갖춘 패널만 읽게 하고, 갖추지 못한 패널은 여기서 이름을 부릅니다 -
#: 그림 단위 `Needs`로는 975장 중 어느 장이 왜 빠졌는지 알 수 없습니다.
PANELS = "plan_panels.csv"
PANEL_FIELDS = ("Publication_ID", "Draft_ID", "Panel_ID", "Proposal_ID", "Disposition",
                "Geometry", "Frame_Source", "Identity", "Dispersion_Type", "Authored", "Needs")

#: 사람이 확인한 것이 사는 곳 (런 디렉터리 기준). 기하는 `record_geometry`가,
#: 정체는 `record_identity`가 적고, 이 모듈은 읽기만 합니다.
GEOMETRY_DIR = os.path.join("seg", "geometry600")
IDENTITY_DIR = os.path.join("seg", "identity600")
REGIONS = os.path.join("seg", "regions600", "panel_regions_600.csv")
#: AI 에이전트가 사람이 MANUAL로 보낸 패널(`Read_Route=MANUAL`)의 표시를 600 DPI
#: 래스터 위에 찍은 자리 (2026-10-18 "1로 가자"). 계열과 x 위치는 정체 확인의
#: 이름(범례 이름, x 라벨)으로 적고, 이 모듈이 계획서의 계열·위치 id로 옮깁니다.
#: 값은 여기 없습니다 - `run_batch`가 패널의 눈금으로 만들고, `finalize_batch`가
#: 다시 만듭니다. 풀에 들어가려면 여전히 사람이 겹친 그림을 보고 승인합니다.
READINGS = os.path.join("seg", "readings600", "supplied_readings.csv")
READING_FIELDS = ("Proposal_ID", "Series", "X_Label", "Mark_X_Px", "Mark_Y_Px",
                  "Upper_Y_Px", "Lower_Y_Px", "Reader_Kind", "Read_By", "Read_At",
                  "Raster_SHA256", "Note")
#: 사람이 600 DPI 래스터 위에서 패널마다 그린 상자와 종류 (`record_panels.py`).
#: 이것이 있으면 그림의 패널 목록은 이것입니다 - 계수 시트의 수는 "몇 개"이고,
#: 이것은 "어느 것이 어디에, 무엇으로"입니다. 둘이 다르면 그림의 메모에 적습니다.
PANEL_DECISIONS = os.path.join("seg", "panel_decisions.csv")
PANELS_VERDICT = "PANELS"
NO_PANELS_VERDICT = "NO_PANELS"
NOT_A_PLOT = "NOT_DATA"
#: 인테이크가 문서마다 적어 둔 것: 그림이 몇 개인지(사람이 세면 VISUALLY_VERIFIED),
#: 그리고 사람이 정한 쪽 범위.
DOCUMENT_STATUS = "intake_document_status.csv"
DOCUMENT_SCOPE = "document_scope.csv"
#: 목록의 두 수(문서의 그림 수와 쪽 범위, 그림의 패널 수)를 적는 두 번째 길
#: (`record_inventory`, run2 2026-10-15 R1): 사람이 센 수, 또는 사람이 승인한 관찰.
#: 사람이 직접 센 것 - 인테이크의 문서 상태, 사람이 그린 패널 - 이 있으면 그것이 먼저입니다.
INVENTORY = RV.INVENTORY
#: 사람이 그린 패널을 그림의 목록으로 쓰지 않는 처분. 그 그림은 다시 자르거나 다시
#: 그리라고 정해졌고, 그린 것은 이전 크롭 위의 것입니다.
DRAWING_SUPERSEDED = ("RECROP", "REDRAW")
#: 그림을 다시 보라는 처분 가운데, 그 뒤에 사람이 그린 패널이 곧 그 처분의 답인 것
#: (run2 2026-10-16). PARTIAL("일부 패널만 데이터")은 사람이 고른 패널을 종류로,
#: 나머지를 '읽을 값 없음'으로 그리거나 결과 아님(`record_outcomes`)으로 닫으면
#: 실행된 것이고, REDRAW("다시 그려라")는 그 뒤에 그린 것이 다시 그린 것입니다.
#: RECROP은 아닙니다 - 크롭이 틀렸다는 처분이고, 같은 크롭 위에 다시 그려도 고쳐지지
#: 않습니다. 두 기록은 날짜만 들고 있어서, REDRAW는 처분보다 **뒤의 날**에 그린 것만
#: 받습니다(같은 날의 그림은 처분이 본 바로 그 그림일 수 있습니다). PARTIAL은 같은
#: 날도 받습니다 - 그 그림이 처분 전의 것이어도 패널의 자리는 맞고, 무엇을 읽을지는
#: 종류와 결과 기록이 정합니다.
DRAWING_ANSWERS = {"PARTIAL": "SAME_DAY_OR_LATER", "REDRAW": "LATER_DAY"}
#: 축 영역이 없는 그림의 한 패널. 읽을 축이 없으니 읽을 값도 없습니다.
WHOLE_LABEL = "WHOLE"
WHOLE_REASON = "make_plan: 축 영역이 없는 그림 (WHOLE) — 읽을 축이 없습니다 (캡션 경로 %s)"

#: 패널의 처분이 곧 정하는 대상 여부 (`batch_manifests.SOURCE_TARGET_STATUSES`).
TARGET_OF = {
    "NOT_DATA": "NOT_DATA", "DUPLICATE_OR_DECORATIVE": "NOT_DATA",
    "NON_TARGET_OUTCOME": "NON_TARGET", "UNRESOLVED": "UNCERTAIN",
}

#: 계획서가 실제로 읽게 되는 처분. 기하·정체·오차 정의가 다 있을 때만.
AUTHORED = "AUTO_DIGITIZE"
#: 확인이 선 600 DPI 래스터가 이 실행에 없음 - 크롭 위에 얹지 않고 계획 단계에서 멈춥니다.
RASTER_600_MISSING = "RASTER_600_MISSING"

#: 이 모듈이 적는 검토자. 사람이 아니고, 사람인 척하지 않습니다.
DEMO_REVIEWER = "R_DEMO_MAKE_PLAN"

#: 캡션 심사가 낸 경로를, 계획서가 아는 패널 처분으로. `GEOMETRY_NOT_AUTHORED`는
#: "읽을 값이 있고 어디를 읽을지는 아직 없다"이고, 나머지는 "읽지 않는다"의
#: 서로 다른 이유들입니다.
ROUTE_DISPOSITION = {
    "DIGITIZE": "GEOMETRY_NOT_AUTHORED",
    "PARTIAL_PANEL_TARGET": "GEOMETRY_NOT_AUTHORED",
    "NOT_DATA": "NOT_DATA",
    "ASSOCIATION_ONLY_NOT_TARGET": "ASSOCIATION_EXTRACT",
    "BINARY_EVENT_NOT_MEAN": "BINARY_EXTRACT",
    "NO_TARGET_OUTCOME": "NON_TARGET_OUTCOME",
    # 캡션이 스스로 어긋난 그림. 값이 있을 수도 없을 수도 있고, 캡션은 어느
    # 쪽인지 말해 주지 않습니다. 사람이 그림을 봐야 합니다.
    "MIXED_CAPTION_NOT_DECIDABLE": "UNRESOLVED",
}

#: 캡션 찾기가 쓰는 이름과 계획서가 쓰는 이름. `CI`는 계획서에서 `CI95`입니다.
DEFINITION_TO_DISPERSION = {"SD": "SD", "SE": "SE", "SEM": "SEM",
                            "CI": "CI95", "IQR": "IQR"}

#: 처분이 곧 정하는 통계 종류. 이름은 `grid_engine.FIG_STATISTIC_TYPES`의
#: 것을 그대로 씁니다 - 계획서가 부르는 이름과 검증기가 받는 이름이 다르면,
#: 계획서를 그대로 따라 채운 행이 관문에서 거부됩니다.
STATISTIC_BY_DISPOSITION = {
    "ASSOCIATION_EXTRACT": "ASSOCIATION",
    "BINARY_EXTRACT": "BINARY_EVENT",
}

#: 사분위 요약으로 그려진 값. `grid_engine`은 `QUANTILE_SUMMARY`에 IQR이나
#: RANGE만 받고, 그 행은 `Median`/`Q1`/`Q3`/`Whisker_*`에 적힙니다. 평평한
#: 연속형 템플릿에는 중앙값을 적을 자리가 없어서, 이 그림들을 그쪽으로 보내지
#: 않으면 중앙값이 `Mean`이라는 이름으로 들어갑니다.
QUANTILE_DISPERSIONS = ("IQR", "RANGE")

#: 정의의 출처. 어느 것이든 논문의 말이고, 어느 논문의 어디인지가 다릅니다.
FROM_DECISION, FROM_CAPTION, FROM_DOCUMENT = "DECISION", "CAPTION", "DOCUMENT"
#: 판정이 같은 논문의 다른 요소(표, 다른 그림)가 말한 정의를 이 그림에 쓴 것
#: (`record_errorbar`의 Definition_Basis=BORROWED, run2 2026-10-14 결정 R9·R10).
#: 인용문은 논문의 말 그대로이고, 그 말이 이 그림에 대한 것이라는 것이 가정입니다.
#: 그 가정은 계획서의 단위 메모(`BORROWED_NOTE`)로 값까지 따라가서, 민감도 분석에서
#: 이 값들만 뺄 수 있습니다.
FROM_DECISION_BORROWED = "DECISION_BORROWED"
BORROWED_NOTE = ("BORROWED_DEFINITION: the paper states this definition for another element (a table or "
                 "another figure), not for this figure; exclude in a sensitivity analysis")

WORKSHEET_FIELDS = ("Publication_ID", "Source_Figure_ID", "Draft_ID",
                    "Figure_Number", "Page", "Image", "Route", "Disposition",
                    "Observed_Panel_Count", "Statistic_Type", "Dispersion_Type",
                    "Errorbar_Definition_Source", "Errorbar_Source_Kind",
                    "Errorbar_Found_On_Page", "Needs")
READINESS_FIELDS = ("Publication_ID", "Figures", "Digitize_Figures",
                    "Panel_Counts_Known", "Dispersion_Known", "Dropped",
                    "Plan", "Problem_Count", "Problems")


def _rows(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8")))


def _by(rows, key):
    return dict((r[key], r) for r in rows if r.get(key))


def live_rows(run):
    """블록되지도 중복도 아닌 초안 행 - 트랙 A가 남긴 그림들."""
    draft = _rows(os.path.join(run, DRAFT))
    reasons = _by(_rows(os.path.join(run, BLOCKS)), "Draft_ID")
    answered = set(
        r["Draft_ID"] for r in _rows(os.path.join(run, COUNTS))
        if (r.get("Entry_Status") or "").strip() in ANSWERED_ON_AN_OPEN_ROW)
    unblocked = set(
        r["Draft_ID"] for r in _rows(os.path.join(run, BLOCK_REVIEWS))
        if (r.get("Decision") or "").strip().upper() == RBR.UNBLOCK)
    out = []
    for row in draft:
        reason = reasons.get(row["Draft_ID"], {})
        if (reason.get("Count_Blocked") == "1"
                and row["Draft_ID"] not in answered
                and row["Draft_ID"] not in unblocked):
            continue
        if (reason.get("Duplicate_Of") or "").strip():
            continue
        out.append(row)
    return out


def dispersion_for(draft_id, caption, decision):
    """(종류, 논문의 말, 어디서 온 말, 쪽). 아무 데도 없으면 ("", "", "", "").

    판정이 있으면 판정이 이깁니다 - 판정은 사람이 논문을 열어 보고 적은 것이고,
    캡션 찾기는 규칙이 읽은 것입니다. 규칙이 놓친 것을 사람이 채운 자리에서
    규칙을 다시 물으면 사람의 답이 지워집니다.
    """
    if decision:
        code = (decision.get("Dispersion_Type") or "").strip().upper()
        if code in RE.DISPOSITIONS:
            return code, "", FROM_DECISION, ""
        kind = FROM_DECISION_BORROWED if (decision.get("Definition_Basis") or "").strip().upper() \
            == RE.BORROWED else FROM_DECISION
        return (code, (decision.get("Errorbar_Definition_Source") or "").strip(),
                kind, (decision.get("Found_On_Page") or "").strip())
    if not caption:
        return "", "", "", ""
    # 상자그림은 캡션이 표시마다 따로 말합니다("Box plots indicate minimum,
    # 25th percentile, median, 75th percentile, and maximum"). 계획서가 나르는
    # 종류는 상자(IQR)이고, 중앙값과 수염은 `QUANTILE_SUMMARY`가 여는
    # `Median`/`Whisker_*` 열에 적힙니다. 이 읽기가 캡션의 일반 판정보다 먼저인
    # 것은, 같은 캡션이 다른 패널에 대해 SEM을 말할 수 있기 때문입니다 - 실제로
    # 그 논문의 문서 진술이 SEM이고, 그것이 상자그림에 붙어 있었습니다.
    if CF.box_elements_of(caption.get("Box_Elements")):
        return "IQR", (caption.get("Box_Evidence") or "").strip(), \
            FROM_CAPTION, (caption.get("Page") or "").strip()
    code = DEFINITION_TO_DISPERSION.get(
        (caption.get("Errorbar_Definition") or "").strip())
    if code:
        # 캡션이 말했으면 그 캡션 전문이 논문의 말입니다. 규칙이 맞춘 30자
        # 토막은 근거를 보여 주는 것이지 논문이 쓴 문장이 아닙니다.
        return code, (caption.get("Caption_Full") or "").strip(), FROM_CAPTION, \
            (caption.get("Page") or "").strip()
    code = DEFINITION_TO_DISPERSION.get(
        (caption.get("Doc_Errorbar_Definition") or "").strip())
    if code:
        return code, (caption.get("Doc_Errorbar_Evidence") or "").strip(), \
            FROM_DOCUMENT, (caption.get("Doc_Errorbar_Page") or "").strip()
    return "", "", "", ""


def count_need(status):
    """수가 없는 이 행에 대해 사람이 다음에 할 일의 이름."""
    return ANSWERED_WITHOUT_A_NUMBER.get(str(status or "").strip(),
                                         COUNT_NEED)


def disposition_for(route):
    """캡션 심사의 경로를 패널 처분으로. 모르는 경로는 추출 대상이 아닙니다.

    kernel이 경로를 하나 더 내기 시작하면 - 실제로 `PARTIAL_PANEL_TARGET`이
    그렇게 생겼습니다 - 이 표에 없는 이름이 여기로 들어옵니다. 그것을 읽을 수
    있는 것으로 치면, 아무도 무엇을 읽을지 말하지 않은 패널이 추출 대기열에
    섭니다. 모르면 `UNRESOLVED`입니다.
    """
    return ROUTE_DISPOSITION.get(route, "UNRESOLVED")


def statistic_type_for(disposition, code):
    """이 그림의 값이 어느 통계 종류로 적히는가. 빈 문자열이면 아직 모릅니다 -
    추출 대상이 아니거나 오차 정의가 없는 그림입니다.

    연속형과 사분위 요약을 여기서 가르는 것이 이 함수의 전부입니다. 가르지
    않으면 둘 다 평평한 연속형 템플릿으로 가고, 거기에는 중앙값 칸이 없습니다.
    """
    if disposition in STATISTIC_BY_DISPOSITION:
        return STATISTIC_BY_DISPOSITION[disposition]
    if disposition != "GEOMETRY_NOT_AUTHORED":
        return ""
    c = (code or "").strip().upper()
    if not c or c in RE.DISPOSITIONS:
        return ""
    return "QUANTILE_SUMMARY" if c in QUANTILE_DISPERSIONS else "CONTINUOUS"


def figure_of(row, caption, decision, count, crop_root, answer=("", ""),
              figure_decision=None):
    """(figure, needs). `needs`는 이 그림에 대해 사람이 아직 해야 할 일들."""
    needs = []
    text = (caption.get("Caption_Full") if caption else "") or row["Caption_Text"]
    # 캡션이 스스로 분산을 말했는가. 이 사실은 `caption_fulltext`가 이미 읽어
    # 두었고, kernel은 어휘를 들고 판정만 합니다 - 같은 정규식을 두 곳에 두면
    # 한쪽만 고쳐질 때 경로와 정의가 서로 다른 캡션을 보게 됩니다.
    said = (caption.get("Errorbar_Definition") or "").strip() if caption else ""
    own = said not in ("", "UNSTATED", "PM_UNNAMED") or bool(
        (caption or {}).get("Box_Elements", "").strip())
    route = kernel.fig_screen_caption(text, states_dispersion=own)[0]
    code, source, kind, where = dispersion_for(row["Draft_ID"], caption, decision)
    disposition = disposition_for(route)

    # 사람이 그림을 보고 정한 것이 있으면 그것이 이깁니다. 캡션 심사도 계수도
    # 그림을 보지 않고 한 판정이고, 이것은 보고 한 판정입니다. 이 갈래가
    # 없으면 `record_decisions`가 적어 둔 것은 파일 안에만 있고, 계획서는
    # 사람이 이미 답한 것을 계속 묻습니다.
    decided, decided_need = decided_for(figure_decision)
    if decided == "DIGITIZE":
        # "전부 데이터다" - 캡션이 어긋나 멈춰 두었던 그림이 보통 그림이
        # 됩니다. 기하와 오차 정의는 아래에서 여느 그림과 같이 붙습니다.
        route, disposition = "DIGITIZE", "GEOMETRY_NOT_AUTHORED"
    elif decided:
        disposition = decided
        if decided_need:
            needs.append(decided_need)
    #: 사람이 이미 처분한 그림. 아래의 물음들은 그 처분보다 앞설 수 없습니다.
    settled = decided in SETTLED_DISPOSITIONS

    if not settled and route == "MIXED_CAPTION_NOT_DECIDABLE" and count:
        # 할 일을 적지 않으면 이 그림들은 `UNRESOLVED`에 조용히 앉아 있습니다 -
        # `NOT_DATA`보다 나쁩니다. 그쪽은 적어도 판정된 처분이고, 이쪽은 아무도
        # 보지 않은 채로 아무 이름도 없이 남습니다.
        needs.append("캡션이 스스로 어긋난 그림 — 어느 패널이 데이터인지 확인")
    if disposition == "GEOMETRY_NOT_AUTHORED":
        if code in RE.DISPOSITIONS:
            # 정의를 못 찾아 풀에서 뺀 행. 기하를 쓸 일이 없습니다.
            disposition = ERRORBAR_DISPOSITION.get(code, "UNRESOLVED")
        elif count == 0:
            # 사람이 축 영역을 0개로 세었습니다. 기하는 패널마다 쓰는
            # 것이고 패널이 없으니 쓸 자리가 없습니다 - 여기에 할 일을
            # 적으면, 읽을 것이 없는 그림에 대해 사람이 무언가 쓰기를
            # 기다리는 줄이 생깁니다. 캡션이 읽을 값이 있다고 본 것과
            # 어긋나면 `Route`와 계수에 그대로 남아 보입니다 - 가리는
            # 것이 아니라, 할 일이 아닌 것을 할 일에서 빼는 것입니다.
            pass
        else:
            if not code:
                needs.append("오차 정의")
            needs.append("패널 기하 (읽을 자리·눈금·표 종류)")

    image = (row.get("Figure_Crop") or "").strip()
    path = os.path.join(crop_root, image) if image else ""
    if not image or not os.path.isfile(path):
        needs.append("잘린 그림 파일")
        image = image or ""

    figure = {
        "source_figure_id": row["Draft_ID"],
        "document_id": row["Source_Document_ID"],
        "figure_number": (row.get("Figure_Number") or "").strip(),
        "source_file": (row.get("Source_File") or "").strip(),
        "source_page": (row.get("Page") or "").strip(),
        "image": image,
        "caption": text,
        # 이 프로그램이 셀 수 없는 하나의 수. 없으면 없는 채로 둡니다 -
        # `validate_plan`이 PLAN_PANEL_COUNT_MISSING으로 이름을 부릅니다.
        "inventory_status": "PENDING",
        "reviewer_id": DEMO_REVIEWER,
        "panels": [],
    }
    status, reason = answer
    if count is None:
        if not settled:
            needs.append(count_need(status))
        if str(status or "").strip() in ANSWERED_WITHOUT_A_NUMBER:
            # 사람의 답을 계획서가 들고 가게 합니다. 여기 없으면 그 답은
            # 계수 시트에만 있고, 계획서를 읽는 쪽에서는 아무도 이 그림을
            # 보지 않은 것과 구별할 수 없습니다.
            figure["note"] = ("사람 답: %s%s"
                              % (status, (" — %s" % reason) if reason else ""))
    else:
        figure["observed_panel_count"] = count
        figure["panel_count_method"] = "HUMAN_VISUAL"
        figure["panels"] = [
            {"panel_id": "%s_P%d" % (row["Draft_ID"], i + 1),
             "disposition": disposition,
             "reason": "make_plan: 캡션 경로 %s" % route}
            for i in range(count)]
    return figure, needs, route, disposition, (code, source, kind, where)


def load_figure_decisions(run):
    """{Draft_ID: 처분 행} - 사람이 그림을 보고 정한 것.

    한 그림에 물음이 둘일 수는 있지만 처분은 하나입니다. 둘 다 적혀 있으면
    나중 것을 씁니다 - 그런 일이 생기면 `record_decisions`가 먼저 막습니다.
    """
    path = os.path.join(run, FIGURE_DECISIONS)
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(io.open(path, encoding="utf-8-sig")):
        out[r["Draft_ID"]] = r
    return out


def load_figure_dispositions(run):
    """{Draft_ID: 처분 행을 `decided_for`가 읽는 모양으로} - `record_dispositions`가 적은 것."""
    path = os.path.join(run, FIGURE_DISPOSITIONS)
    out = {}
    if not os.path.exists(path):
        return out
    for r in csv.DictReader(io.open(path, encoding="utf-8-sig")):
        out[r["Draft_ID"]] = dict(r, Decision=r.get("Disposition", ""), Question="DISPOSITION")
    return out


def load_outcomes(run):
    """{Panel_ID: 행} - `record_outcomes`가 적은 결과의 이름과 "결과 아님"."""
    return _by(_rows(os.path.join(run, OUTCOME_DECISIONS)), "Panel_ID")


def load_legends(run):
    """{Draft_ID: [[패널 번호, ...], ...]} - `record_legends`가 적은 범례 묶음."""
    out = {}
    for r in _rows(os.path.join(run, LEGEND_DECISIONS)):
        groups = [[int(x[1:]) for x in g.split(",") if x.strip()] for g in (r.get("Legend_Groups") or "").split("|") if g.strip()]
        if groups:
            out[r["Draft_ID"]] = groups
    return out


def legend_domain(view, groups, index):
    """이 패널이 쓰는 범례의 Identity_Domain_ID. 범례 기록이 없으면 그림 하나가 범례 하나입니다."""
    for k, g in enumerate(groups or [], 1):
        if index in g:
            return "%s__L%d" % (view, k)
    return ""


def apply_outcome(panel, said):
    """사람이 정한 결과의 이름(또는 결과 아님)을 패널에 얹습니다.

    읽을 준비가 된 패널(AUTO_DIGITIZE)에는 부르지 않습니다 - 그 이름은 정체 확인
    (Outcome_Name)이 정한 것입니다. 닫힌 패널에 이름을 붙이지는 않습니다 - 관문이 그런
    답을 받지 않지만, 처분이 나중에 바뀌었을 수 있습니다."""
    if not said:
        return
    decision = (said.get("Decision") or "").strip().upper()
    who = (said.get("Verified_By") or "").strip()
    if decision == "NON_TARGET":
        panel.update({"disposition": "NON_TARGET_OUTCOME", "target_status": "NON_TARGET",
                      "reason": "outcome_decisions: %s — 이 리뷰의 결과가 아님" % who})
    elif decision == "LABEL" and target_status_of(panel) == "TARGET":
        panel["outcome_label"] = (said.get("Outcome_Label") or "").strip()


def drawing_answers(figure_decision, drawn_all):
    """처분 뒤에 그린 패널이 그 처분을 대신하는가 (`DRAWING_ANSWERS`). 날짜가 빠진 쪽이 있으면 아닙니다."""
    choice = ((figure_decision or {}).get("Decision") or "").strip().upper()
    rule = DRAWING_ANSWERS.get(choice)
    decided_at = ((figure_decision or {}).get("Recorded_At") or "").strip()
    drawn_at = [(r.get("Verified_At") or "").strip() for r in drawn_all or []]
    if not rule or not decided_at or not drawn_at:
        return False
    first = min(drawn_at)          # 날이 빠진 줄이 있으면 ""이 가장 작아 받지 않습니다
    return first > decided_at if rule == "LATER_DAY" else first >= decided_at


def decided_for(figure_decision):
    """(처분, 할 일) - 사람의 판정이 계획서에서 무엇이 되는가.

    ("", None)이면 판정이 없습니다. 할 일이 `None`이면 더 할 일이 없다는
    뜻이고, 빈 문자열이 아니라 `None`인 것은 "없음"과 "빈 이름"을 가르기
    위해서입니다.
    """
    if not figure_decision:
        return "", None
    choice = (figure_decision.get("Decision") or "").strip().upper()
    if choice == DECIDED_NOT_DATA:
        return "NOT_DATA", None
    if choice == DECIDED_IS_DATA:
        return "DIGITIZE", None
    if choice in DECIDED_DISPOSITION:
        return DECIDED_DISPOSITION[choice], None
    need = DECIDED_NEEDS.get(choice)
    if need is None:
        return "", None
    which = (figure_decision.get("Which_Panels") or "").strip()
    return "UNRESOLVED", ("%s: %s" % (need, which)) if which else need


def load_reviewers(path):
    """({reviewer_id: 검토자 항목}, {Verified_By 이름: reviewer_id}).

    사람이 한 번 적는 파일입니다 - 누가 화면에서 패널을 세었는지 계획서가
    이름을 대려면, 그 이름이 등록된 사람이어야 합니다. 이 모듈은 항목을
    옮겨 적기만 하고, `human_attestation`은 그 파일에 사람이 적은 그대로입니다.

        {"reviewers": [{"reviewer_id": "RV_MC", "name": "...", "record_type": "HUMAN",
                        "contact_type": "ORCID", "contact": "0000-...",
                        "registered_by": "...", "registration_date": "2026-09-18",
                        "human_attestation": "HUMAN_CONFIRMED"}],
         "names": {"minyeop": "RV_MC"}}
    """
    if not path or not os.path.exists(path):
        return {}, {}
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    reviewers = dict((r["reviewer_id"], r) for r in data.get("reviewers") or [])
    names = dict((str(k).strip().lower(), v) for k, v in (data.get("names") or {}).items())
    for name, rid in names.items():
        if rid not in reviewers:
            raise SystemExit("%s: 이름 %r이 가리키는 검토자 %r이 목록에 없습니다" % (path, name, rid))
    return reviewers, names


def load_confirmations(run, geometry_dir=None, identity_dir=None, regions=None):
    """({Proposal_ID: 기하 행}, {Proposal_ID: 정체 행}, {Draft_ID: 영역 행들}).

    있는 것만 읽습니다. 파일이 없으면 빈 사전이고, 그러면 모든 패널은 아직
    아무도 확인하지 않은 채로 - `GEOMETRY_NOT_AUTHORED` - 남습니다.
    """
    geometry = _by(_rows(os.path.join(run, geometry_dir or GEOMETRY_DIR, RG.DECISIONS)),
                   "Proposal_ID")
    identity = _by(_rows(os.path.join(run, identity_dir or IDENTITY_DIR, RI.DECISIONS)),
                   "Proposal_ID")
    regions = {}
    for r in _rows(os.path.join(run, regions or REGIONS)):
        regions.setdefault(r["Draft_ID"], []).append(r)
    drawn = {}
    for r in _rows(os.path.join(run, PANEL_DECISIONS)):
        drawn.setdefault(r["Draft_ID"], []).append(r)
    for rows_ in drawn.values():
        rows_.sort(key=lambda r: int(r["Panel_Index"]) if str(r.get("Panel_Index") or "").isdigit() else 0)
    return geometry, identity, regions, drawn


def load_readings(run, path=None):
    """{Proposal_ID: [판독 행]} - 없으면 빈 사전, 그러면 MANUAL 패널은 전처럼 대기열로."""
    out = {}
    for r in _rows(os.path.join(run, path or READINGS)):
        out.setdefault((r.get("Proposal_ID") or "").strip(), []).append(r)
    return out


def load_inventory(run):
    """({Source_Document_ID: 행}, {Draft_ID: 행}) - `record_inventory`가 적은 것."""
    docs, figs = {}, {}
    for r in _rows(os.path.join(run, INVENTORY)):
        level = (r.get("Level") or "").strip().upper()
        if level == RV.DOCUMENT:
            docs[r["Target_ID"]] = r
        elif level == RV.FIGURE:
            figs[r["Target_ID"]] = r
    return docs, figs


def load_documents(run):
    """({Source_Document_ID: 인테이크 상태 행}, {Source_Document_ID: 쪽 범위 행})."""
    return (_by(_rows(os.path.join(run, DOCUMENT_STATUS)), "Source_Document_ID"),
            _by(_rows(os.path.join(run, DOCUMENT_SCOPE)), "Source_Document_ID"))


def target_status_of(panel):
    """대상 여부. 처분이 정하고, TARGET은 결과변수 이름이 있어야 배치층을 지납니다 -
    없는 것은 지어내지 않고, 배치층이 MISSING_TARGET_OUTCOME_LABEL로 이름 부릅니다."""
    return TARGET_OF.get((panel.get("disposition") or "").upper(), "TARGET")


def proposal_id_for(draft_id, index):
    """플롯 패널의 이름. `geometry_run`이 짓는 이름과 같아야 합니다 - 다르면
    확인은 파일에만 있고 계획서는 영영 못 봅니다."""
    return "%s__p%d" % (draft_id, index)


def _slug(text, fallback):
    out = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "")).strip("_").upper()
    return out or fallback


def _frames_agree(geometry, identity):
    try:
        return all(int(round(float(geometry.get(k)))) == int(round(float(identity.get(k))))
                   for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1"))
    except (TypeError, ValueError):
        return False


def geometry_state(row):
    """사람이 이 패널의 기하에 대해 한 말. (상태, 프레임 출처)."""
    if row is None:
        return "PENDING", ""
    status = (row.get("Human_Verification_Status") or "").strip().upper()
    source = (row.get("Frame_Source") or "").strip().upper()
    if status == "REJECTED" and not (row.get("Panel_X0") or "").strip():
        # 프레임을 못 찾은 패널에 "읽을 플롯이 없다"고 한 답.
        return "NO_PLOT", source
    return status or "PENDING", source


def authored_read(panel_id, draft_id, geometry, identity, dispersion, label, readings=()):
    """(read, unit, grid, view) - 기하·정체·오차 정의가 다 있는 패널의 계획.

    여기 있는 것은 전부 사람이 확인한 것에서 옮겨 온 것입니다: 프레임과 눈금
    짝은 기하 결정에서, x 위치·계열·요인·결과변수·단위·n은 정체 결정에서, 오차
    정의는 캡션 심사나 사람의 판정에서. 이 함수가 지어내는 것은 이름(unit_id,
    grid_id, position_id)뿐이고, 이름은 값이 아닙니다.
    """
    cal = GP.calibration_from(geometry)
    x0, x1, y0, y1 = [int(round(float(geometry[k]))) for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")]
    positions = json.loads(identity.get("X_Labels") or "[]")
    series = json.loads(identity.get("Series") or "[]")
    x_factor = (identity.get("X_Factor") or "").strip().upper()
    s_factor = (identity.get("Series_Factor") or "").strip().upper()
    mark = (identity.get("Mark_Type") or "").strip().upper()
    code, source, kind, where = dispersion
    unit_id, grid_id, view = "U_%s" % panel_id, "G_%s" % panel_id, "F_%s" % draft_id
    read = {
        "mark_type": mark, "unit_id": unit_id, "figure_view": view,
        "box": [x0, x1, y0, y1], "y_ticks": cal,
        "y_scale": "LINEAR", "x_scale": "LINEAR", "panel_mode": "AUTO",
        "note": "geometry %s %s by %s at %s%s; identity by %s at %s" % (
            geometry.get("Proposal_ID"), geometry.get("Human_Verification_Status"),
            geometry.get("Verified_By"), geometry.get("Verified_At"),
            (" (frame %s)" % geometry.get("Frame_Source")) if (geometry.get("Frame_Source") or "").strip() else "",
            identity.get("Verified_By"), identity.get("Verified_At")),
        "series": [], "positions": [],
    }
    for k in ("Axis_X_Region", "Axis_Y_Region"):
        if (geometry.get(k) or "").strip():
            read[k.lower()] = geometry[k].strip()
    # 사람이 읽는 패널 (`record_identity.READ_ROUTES`). 격자는 똑같이 서고, 값은
    # 판독 대기열로 갑니다. 계열의 표시는 판독기의 칸이 아니라 메모로 갑니다 - 그
    # 표시는 판독기가 못 가르는 것이라서 사람이 확인한 것이고, 판독기의 칸에 적으면
    # 배치층이 판독기의 규칙(구분 수단, 어휘)으로 다시 재판합니다.
    manual = (identity.get("Read_Route") or "").strip().upper() == "MANUAL"
    if manual:
        read["panel_mode"] = "MANUAL"
        read["note"] += "; values read by a person (Read_Route=MANUAL): no released reader separates these series"
    used = set()
    series_id_of, position_id_of = {}, {}
    for i, e in enumerate(series, 1):
        name = (e.get("name") or "").strip()
        sid = _slug(name, "S%d" % i)
        while sid in used:
            sid += "_"
        used.add(sid)
        series_id_of[name or sid] = sid
        # Every series carries its factor and level, the single one too: a
        # series without a level is no Cell_Key (MISSING_SERIES_IDENTITY).
        sp = {"series_id": sid, "factor": s_factor, "level": name or sid}
        # THE GROUP'S OWN n (`record_identity`: all series or none, never beside the
        # card's N_Outcome). Carried as written when it is not a positive whole
        # number, so the batch layer refuses it loudly (SERIES_N_BAD) rather than
        # this module dropping it.
        if e.get("n") not in (None, ""):
            sp["n_outcome"] = (RI.series_n_of([e])[0] if RI.series_n_ok(e.get("n")) else e.get("n"))
            sp["n_source"] = "identity card (per series)"
        drawn = []
        for src, dst in (("colour", "colour"), ("line_style", "line_style"), ("marker", "marker"),
                         ("marker_fill", "marker_fill"), ("bar_fill", "bar_fill")):
            if (e.get(src) or "").strip():
                if manual:
                    drawn.append("%s=%s" % (dst, e[src].strip()))
                elif src == "marker" and e[src].strip().upper() in RI.MANUAL_ONLY_SHAPES:
                    # 판독기 어휘 밖의 모양(▼ 등). 판독기 부류가 있으면(▼ -> TRIANGLE: 판독기의
                    # 삼각형은 방향을 보지 않음) 판독기 칸에 그 부류를, 없으면(색 표의 ×·별표 등,
                    # 색 판독기는 모양을 보지 않음) 판독기 칸을 비웁니다. 본 모양은 메모로.
                    seen = e[src].strip().upper()
                    if seen in RI.READER_CLASS:
                        sp[dst] = RI.READER_CLASS[seen]
                        drawn.append("%s=%s (read as the reader's %s)" % (dst, seen, RI.READER_CLASS[seen]))
                    else:
                        drawn.append("%s=%s (colour separates; not a reader shape)" % (dst, seen))
                else:
                    sp[dst] = e[src].strip()
        if name:
            sp["note"] = "legend: %s" % name
        if drawn and not manual:
            sp["note"] = "; ".join(x for x in (sp.get("note", ""), "drawn: %s" % ", ".join(drawn)) if x)
        if manual:
            cue = (e.get("cue") or "").strip()
            sp["note"] = "; ".join(x for x in (sp.get("note", ""), "drawn: %s" % ", ".join(drawn) if drawn else "",
                                               "cue: %s" % cue if cue else "") if x)
        read["series"].append(sp)
    used = set()
    for i, p in enumerate(positions):
        label_text = str(p.get("label") or "").strip()
        pid_ = _slug(label_text, "X%d" % (i + 1))
        while pid_ in used:
            pid_ += "_"
        used.add(pid_)
        position_id_of[label_text or pid_] = pid_
        read["positions"].append({"position_id": pid_, "factor": x_factor, "level": label_text,
                                  "x_pixel": float(p["px"]), "display_order": i})
    # 판독은 이름으로 적혀 있고 계획서는 id로 씁니다. 모르는 이름은 그대로 두어
    # 배치층이 크게 거절하게 합니다(SUPPLIED_READING_SERIES_UNKNOWN 등) - 조용히
    # 버리면 읽은 칸이 사라진 줄 아무도 모릅니다. AUTO 패널의 판독도 그대로
    # 옮겨서 거절되게 합니다(SUPPLIED_READING_ON_READER_PANEL).
    if readings:
        read["readings"] = []
        for r in readings:
            entry = {"series_id": series_id_of.get((r.get("Series") or "").strip(),
                                                   (r.get("Series") or "").strip()),
                     "position_id": position_id_of.get((r.get("X_Label") or "").strip(),
                                                       (r.get("X_Label") or "").strip()),
                     "reader_kind": (r.get("Reader_Kind") or "").strip(),
                     "read_by": (r.get("Read_By") or "").strip(),
                     "read_at": (r.get("Read_At") or "").strip(),
                     "raster_sha256": (r.get("Raster_SHA256") or "").strip(),
                     "note": (r.get("Note") or "").strip()}
            for src, dst in (("Mark_X_Px", "x_px"), ("Mark_Y_Px", "y_px"),
                             ("Upper_Y_Px", "upper_px"), ("Lower_Y_Px", "lower_px")):
                text = (r.get(src) or "").strip()
                entry[dst] = float(text) if _is_number(text) else (text or None)
            read["readings"].append(entry)
    factors = {x_factor: [str(p.get("label") or "").strip() for p in positions],
               s_factor: [(e.get("name") or "").strip() or ("S%d" % (i + 1)) for i, e in enumerate(series)]}
    grid = {"grid_id": grid_id, "factors": factors}
    statistic = statistic_type_for("GEOMETRY_NOT_AUTHORED", code)
    errorbar_source = source or ("%s: %s" % (kind, where) if kind else "")
    if mark == "BOX_VIOLIN":
        # A box is the interquartile range by construction; the caption says
        # what the whiskers are. The figure-level definition (an SEM for the
        # bar panels of the same figure) is not this panel's.
        statistic = "QUANTILE_SUMMARY"
        if code not in QUANTILE_DISPERSIONS:
            code = "IQR"
            errorbar_source = "box plot: the box is the IQR by construction; figure-level " \
                              "definition was %s (%s)" % (dispersion[0] or "none", errorbar_source)
    unit = {
        "unit_id": unit_id, "panel_id": panel_id, "figure_view": view, "grid_id": grid_id,
        "panel": label, "outcome_name": (identity.get("Outcome_Name") or "").strip(),
        "unit": (identity.get("Unit") or "").strip(),
        "statistic": statistic,
        "dispersion_type": code, "errorbar_source": errorbar_source,
        "extraction_method": "DIGITIZED",
    }
    # 상자그림이 상자로서 IQR을 받았으면 빌린 정의는 이 단위에 쓰이지 않았습니다.
    if kind == FROM_DECISION_BORROWED and not (mark == "BOX_VIOLIN" and dispersion[0] not in QUANTILE_DISPERSIONS):
        unit["note"] = BORROWED_NOTE
    n = (identity.get("N_Outcome") or "").strip()
    if n.isdigit():
        unit["n_outcome"] = int(n)
        unit["n_source"] = "identity page (caption)"
    # THE X CALIBRATION OF A CATEGORICAL AXIS is its slots: the first declared
    # position is slot 0 and the last is slot n-1, as the Beckers pilot wrote
    # by hand. The provenance columns need two points, and these are the
    # positions the person confirmed, not a scale anyone measured.
    if len(positions) >= 2:
        unit["x_calibration"] = [[0, float(positions[0]["px"])],
                                 [len(positions) - 1, float(positions[-1]["px"])]]
    # WHERE THE VALUE IS READ. A bar's is the person's answer; a box has none
    # (`NOT_A_BAR`, the vocabulary's own word for it, never a blank); a line or
    # a scatter is read at its marker's centre.
    if (identity.get("Bar_Top_Definition") or "").strip():
        unit["bar_top_definition"] = identity["Bar_Top_Definition"].strip()
    elif mark == "BOX_VIOLIN":
        unit["bar_top_definition"] = "NOT_A_BAR"
    elif mark.startswith("LINE") or mark == "SCATTER":
        unit["bar_top_definition"] = "MARKER_CENTER"
    if (identity.get("Errorbar_Stem_Confirmed") or "").strip():
        unit["errorbar_stem_confirmed"] = identity["Errorbar_Stem_Confirmed"].strip()
    return read, unit, grid, view


def _is_number(text):
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def panel_plan(draft_id, index, geometry, identity, dispersion, caption_text, kind="", raster_missing="",
               readings=None):
    """(panel, unit, grid, view, worksheet 행) - 한 패널의 처분과 남은 일.

    갖춘 것이 셋이어야 읽습니다: 확인된 기하(눈금 짝 둘), 확인된 정체(같은
    프레임 위의), 오차 정의. 하나라도 없으면 `GEOMETRY_NOT_AUTHORED`로 남고,
    무엇이 없는지는 worksheet 행에 적힙니다.

    `raster_missing` - 확인이 서 있는 600 DPI 래스터가 이 실행에 없으면 그 경로. 그 확인의 상자와
    눈금은 그 래스터의 픽셀이라, 200 DPI 크롭 위에서는 다른 그림의 자리입니다: 읽을 준비로 두지 않고
    `RASTER_600_MISSING`을 남깁니다(전에는 크롭으로 말없이 돌아가 읽을 때 INTERNAL_ERROR로 드러났음).
    """
    pid = proposal_id_for(draft_id, index)
    panel_id = "%s_P%d" % (draft_id, index)
    g, i = geometry.get(pid), identity.get(pid)
    g_state, frame_source = geometry_state(g)
    i_state = (i.get("Human_Verification_Status") or "").strip().upper() if i else "PENDING"
    code, _source, _kind, _where = dispersion
    needs = []
    disposition = "GEOMETRY_NOT_AUTHORED"
    reason = ""
    if g_state == "NO_PLOT":
        disposition, reason = "NOT_DATA", "geometry: 사람이 이 영역엔 읽을 플롯이 없다고 함"
    elif g_state == "REJECTED":
        needs.append("기하 거절됨 — 프레임 다시 그리기")
    elif g_state in ("PENDING", ""):
        needs.append("기하 확인")
    elif GP.calibration_from(g) is None:
        needs.append("기하 확인에 눈금 짝이 없음")
    if disposition != "NOT_DATA":
        if i_state == "REJECTED":
            disposition, reason = "MANUAL_DIGITIZE", "identity: 사람이 이 패널은 읽지 않는다고 함"
        elif i_state != "CONFIRMED":
            needs.append("정체 확인 (x 위치·계열·단위)")
        elif g is not None and g_state in ("CONFIRMED", "SHARED") and not _frames_agree(g, i):
            # 정체는 이 프레임 위에서 읽고 확인한 것입니다. 기하가 나중에 다시
            # 그려졌으면 그 x 위치는 다른 프레임의 것이라, 다시 확인해야 합니다.
            needs.append("정체가 다른 프레임 위에서 확인됨 — 정체 다시 확인")
        if not code:
            needs.append("오차 정의")
        elif code in RE.DISPOSITIONS:
            needs.append("오차 정의 없음으로 풀에서 뺀 그림")
        if raster_missing:
            needs.append("%s (%s)" % (RASTER_600_MISSING, raster_missing))
    panel = {"panel_id": panel_id, "label": "P%02d" % index, "disposition": disposition,
             "reason": reason or ("make_plan: %s%s" % (("%s · " % kind) if kind else "",
                                                       " · ".join(needs) if needs else "authored"))}
    unit = grid = view = None
    if disposition == "GEOMETRY_NOT_AUTHORED" and not needs:
        read, unit, grid, view = authored_read(panel_id, draft_id, g, i, dispersion, panel["label"],
                                               (readings or {}).get(pid, ()))
        panel.update({"disposition": AUTHORED, "reason": "make_plan: geometry and identity confirmed",
                      "target_status": "TARGET", "outcome_label": unit["outcome_name"], "read": read})
    row = dict(Draft_ID=draft_id, Panel_ID=panel_id, Proposal_ID=pid, Disposition=panel["disposition"],
               Geometry=g_state, Frame_Source=frame_source, Identity=i_state, Dispersion_Type=code,
               Authored="1" if panel["disposition"] == AUTHORED else "0", Needs=" · ".join(needs))
    return panel, unit, grid, view, row


def plan_for(run, publication, rows, captions, decisions, counts, crop_root,
             run_date, said=None, decided=None, confirmations=None, reviewers=None,
             documents_known=None, inventory=None, outcomes=None, legends=None,
             readings=None):
    """(plan, 그림별 (figure_id, needs, ...), 패널 행). 한 편의 계획서."""
    first = rows[0]
    said = said or {}
    registered, names = reviewers or ({}, {})
    doc_status, doc_scope = documents_known or ({}, {})
    inv_docs, inv_figs = inventory or ({}, {})
    used_reviewers = set()

    def reviewer_for(who):
        rid = names.get(str(who or "").strip().lower())
        if rid:
            used_reviewers.add(rid)
        return rid

    documents, seen = [], set()
    for row in rows:
        name = (row.get("Source_File") or "").strip()
        if name in seen:
            continue
        seen.add(name)
        doc = {
            "document_id": row["Source_Document_ID"],
            "role": "MAIN_ARTICLE",
            "source_file": name,
            "source_file_sha256": (row.get("Source_File_SHA256") or "").strip(),
            # 이 프로그램이 세지 않는 두 번째 수. 그림이 몇 개인지는 논문을
            # 넘겨 본 사람의 답이고, 인테이크가 찾은 개수가 아닙니다.
            "inventory_status": "PENDING",
            "reviewer_id": DEMO_REVIEWER,
        }
        status = doc_status.get(row["Source_Document_ID"]) or {}
        scope = doc_scope.get(row["Source_Document_ID"]) or {}
        inv = inv_docs.get(row["Source_Document_ID"])
        if (scope.get("Page_From") or "").strip() and (scope.get("Page_To") or "").strip():
            doc["page_range"] = "%s-%s" % (scope["Page_From"].strip(), scope["Page_To"].strip())
        elif inv and (inv.get("Article_Page_Range") or "").strip():
            doc["page_range"] = inv["Article_Page_Range"].strip()
        count = (status.get("Observed_Figure_Count") or "").strip()
        counted = False
        if (status.get("Document_Inventory_Status") or "").strip().upper() == "VISUALLY_VERIFIED" \
                and count.isdigit():
            rid = reviewer_for(status.get("Inventoried_By") or status.get("Verified_By"))
            if rid:
                doc.update({"observed_figure_count": int(count), "inventory_status": "VISUALLY_VERIFIED",
                            "figure_count_method": "HUMAN_VISUAL", "reviewer_id": rid,
                            "inspection_date": (status.get("Inventoried_At") or status.get("Verified_At") or "").strip()})
                counted = True
        if not counted and inv and (inv.get("Count") or "").strip().isdigit():
            # `record_inventory`가 적은 수. 방법은 그 관문이 누가 보았는지로 정한 것이고,
            # 승인한 사람이 등록되지 않았으면 PENDING인 채로 이름을 부릅니다.
            rid = reviewer_for(inv.get("Verified_By"))
            if rid:
                doc.update({"observed_figure_count": int(inv["Count"]), "inventory_status": "VISUALLY_VERIFIED",
                            "figure_count_method": (inv.get("Count_Method") or "").strip().upper(), "reviewer_id": rid,
                            "inspection_date": (inv.get("Inspection_Date") or "").strip()})
            else:
                doc["note"] = "검토자 등록: %s (--reviewers)" % (inv.get("Verified_By") or "").strip()
        documents.append(doc)
    geometry, identity, regions, drawn = confirmations or ({}, {}, {}, {})
    figures, notes, units, grids, views, panel_rows = [], [], [], [], {}, []
    for row in rows:
        cap = captions.get(row["Draft_ID"])
        dec = decisions.get(row["Draft_ID"])
        raw = counts.get(row["Draft_ID"])
        sheet = int(raw) if str(raw or "").strip().isdigit() else None
        figure_decision = (decided or {}).get(row["Draft_ID"])
        # 사람이 그린 패널 (`record_panels`). PANELS 줄의 수가 그 사람이 센 패널
        # 수이고, NO_PANELS는 "이 그림에는 읽을 패널이 없다" - 축 영역이 없는
        # 그림(WHOLE)입니다. 다시 자르거나 다시 그리라고 정해진 그림의 것은
        # 이전 크롭 위의 것이라 목록으로 쓰지 않습니다.
        drawn_all = drawn.get(row["Draft_ID"]) or []
        drawn_rows = [r for r in drawn_all if (r.get("Verdict") or "").strip().upper() == PANELS_VERDICT]
        no_panels = bool(drawn_all) and not drawn_rows and all(
            (r.get("Verdict") or "").strip().upper() == NO_PANELS_VERDICT for r in drawn_all)
        answered = drawing_answers(figure_decision, drawn_all)
        if answered:
            # 그린 것이 처분의 답입니다. 그림은 여느 읽을 그림처럼 그린 패널로 서고,
            # 처분이 무엇이었는지는 그림의 메모에 남습니다.
            said_before = figure_decision
            figure_decision = dict(figure_decision, Decision=DECIDED_IS_DATA)
        superseded = (figure_decision or {}).get("Decision", "").strip().upper() in DRAWING_SUPERSEDED
        inv = inv_figs.get(row["Draft_ID"])
        # 패널 수는 어디서 오는가: 사람이 그린 것(서 있으면) > 목록 기록 > 계수 시트.
        if (drawn_rows or no_panels) and not superseded:
            count, count_from = (len(drawn_rows) if drawn_rows else 1), "DRAWN"
        elif inv and (inv.get("Count") or "").strip().isdigit():
            count, count_from = int(inv["Count"]), "INVENTORY"
        else:
            count, count_from = sheet, "SHEET"
        figure, needs, route, disposition, dispersion = figure_of(
            row, cap, dec, count, crop_root,
            said.get(row["Draft_ID"], ("", "")), figure_decision)
        whole = (count_from == "DRAWN" and no_panels) or (
            count_from == "INVENTORY" and (inv.get("Count_Basis") or "").strip().upper() == RV.WHOLE)
        if count_from == "DRAWN" and not (disposition == "GEOMETRY_NOT_AUTHORED" and drawn_rows):
            # 사람이 그린 것이 그림의 목록이지만, 그 그림을 읽지는 않습니다 (닫힌
            # 처분, 또는 패널이 없다는 답). 목록은 그 사람의 것으로 적습니다.
            who = (drawn_all[0].get("Verified_By") or "").strip()
            rid = reviewer_for(who)
            figure["panel_count_method"] = "HUMAN_VISUAL"
            if rid:
                figure.update({"inventory_status": "VISUALLY_VERIFIED", "reviewer_id": rid,
                               "inspection_date": (drawn_all[0].get("Verified_At") or "").strip()})
            elif who:
                needs.append("검토자 등록: %s (--reviewers)" % who)
        elif count_from == "INVENTORY":
            rid = reviewer_for(inv.get("Verified_By"))
            figure["panel_count_method"] = (inv.get("Count_Method") or "").strip().upper()
            if rid:
                figure.update({"inventory_status": "VISUALLY_VERIFIED", "reviewer_id": rid,
                               "inspection_date": (inv.get("Inspection_Date") or "").strip()})
            else:
                needs.append("검토자 등록: %s (--reviewers)" % (inv.get("Verified_By") or "").strip())
            if sheet is not None and sheet != count:
                figure["note"] = ("inventory_records.csv: %d (%s, %s); the count sheet said %d"
                                  % (count, (inv.get("Count_Basis") or "").strip().upper(),
                                     figure["panel_count_method"], sheet))
        if whole:
            # 축 영역이 없는 그림은 한 패널로 닫습니다. 캡션 심사가 읽을 그림으로
            # 보았어도 읽을 축이 없으니 읽을 값이 없고, 그 패널을 TARGET으로 두면
            # 사람에게 결과 이름과 기하를 묻는 줄이 생깁니다.
            for panel in figure["panels"]:
                panel["label"] = WHOLE_LABEL
            if disposition == "GEOMETRY_NOT_AUTHORED":
                disposition = "NOT_DATA"
                for panel in figure["panels"]:
                    panel.update({"disposition": "NOT_DATA", "reason": WHOLE_REASON % route})
                needs = [x for x in needs if x != "오차 정의" and not x.startswith("패널 기하")]
        # 사람이 확인한 것이 있으면 패널마다 옮깁니다. 600 DPI 래스터 위에서
        # 확인했으니 계획서의 그림도 그 래스터입니다 - 상자와 눈금은 그 픽셀의
        # 것이고, 크롭 위에 얹으면 조용히 어긋납니다.
        if disposition == "GEOMETRY_NOT_AUTHORED" and drawn_rows:
            # 사람이 그린 패널 목록이 계수 시트의 수를 대신합니다. 계수는 "몇
            # 개"이고 이것은 "어느 것이 어디에, 무엇으로"입니다 - 그리고 이
            # 목록의 번호가 기하·정체 결정의 이름(`__p<번호>`)입니다.
            counted = sheet
            figure["observed_panel_count"] = len(drawn_rows)
            figure["panel_count_method"] = "HUMAN_VISUAL"
            if counted is not None and counted != len(drawn_rows):
                figure["note"] = ("panel_decisions.csv: %d panels drawn by %s; the count sheet "
                                  "said %s" % (len(drawn_rows), drawn_rows[0].get("Verified_By"), counted))
            # 누가 화면에서 세었는가. 등록된 사람이면 그 이름으로 VISUALLY_VERIFIED,
            # 아니면 PENDING인 채로 - 등록은 사람이 하고, 이름은 지어내지 않습니다.
            who = (drawn_rows[0].get("Verified_By") or "").strip()
            rid = reviewer_for(who)
            if rid:
                figure.update({"inventory_status": "VISUALLY_VERIFIED", "reviewer_id": rid,
                               "inspection_date": (drawn_rows[0].get("Verified_At") or "").strip()})
            elif who:
                needs.append("검토자 등록: %s (--reviewers)" % who)
            region_rows = regions.get(row["Draft_ID"]) or []
            raster_missing = ""
            if region_rows:
                raster = (region_rows[0].get("Raster_600") or "").strip()
                if raster and os.path.isfile(os.path.join(crop_root, raster)):
                    figure["image"] = raster
                    figure["image_sha256"] = (region_rows[0].get("Raster_600_SHA256") or "").strip()
                else:
                    # 확인은 600 DPI 래스터 위의 것인데 그 파일이 없습니다. 크롭으로 돌아가면 상자와 눈금이
                    # 다른 그림 위에 앉습니다 - 계획 단계에서 이름을 부르고 읽을 준비로 두지 않습니다.
                    raster_missing = raster or "(Raster_600 칸이 비어 있음)"
                    needs.append("%s: %s" % (RASTER_600_MISSING, raster_missing))
            figure["panels"] = []
            authored, plots = 0, 0
            for d in drawn_rows:
                index = int(d["Panel_Index"])
                kind = (d.get("Mark_Type") or "").strip().upper()
                if kind == NOT_A_PLOT:
                    figure["panels"].append({"panel_id": "%s_P%d" % (row["Draft_ID"], index),
                                             "label": "P%02d" % index, "disposition": "NOT_DATA",
                                             "reason": "panel_decisions: 사람이 데이터 아님으로 표시"})
                    continue
                said_outcome = (outcomes or {}).get("%s_P%d" % (row["Draft_ID"], index))
                if (said_outcome or {}).get("Decision", "").strip().upper() == "NON_TARGET":
                    # 결과가 아닌 패널은 닫습니다 - 기하와 정체를 물을 패널이 아니고,
                    # 읽을 준비가 되어 있었어도 읽지 않습니다.
                    closed = {"panel_id": "%s_P%d" % (row["Draft_ID"], index), "label": "P%02d" % index}
                    apply_outcome(closed, said_outcome)
                    figure["panels"].append(closed)
                    continue
                plots += 1
                panel, unit, grid, view, prow = panel_plan(
                    row["Draft_ID"], index, geometry, identity, dispersion, figure["caption"], kind, raster_missing,
                    readings=readings)
                if unit is not None and (legends or {}).get(row["Draft_ID"]):
                    domain = legend_domain(panel["read"]["figure_view"], legends[row["Draft_ID"]], index)
                    if domain:
                        panel["read"]["identity_domain"] = domain
                figure["panels"].append(panel)
                prow["Publication_ID"] = publication
                panel_rows.append(prow)
                if unit is not None:
                    units.append(unit)
                    grids.append(grid)
                    views[view] = {"caption": figure["caption"]}
                    authored += 1
            done_g = sum(1 for r in panel_rows if r["Draft_ID"] == row["Draft_ID"]
                         and r["Geometry"] in ("CONFIRMED", "SHARED", "NO_PLOT"))
            done_i = sum(1 for r in panel_rows if r["Draft_ID"] == row["Draft_ID"]
                         and r["Identity"] in ("CONFIRMED", "REJECTED"))
            needs = [x for x in needs if not x.startswith("패널 기하")]
            if authored < plots:
                needs.append("패널 기하·정체 확인 — 기하 %d/%d · 정체 %d/%d · 읽을 준비 %d/%d"
                             % (done_g, plots, done_i, plots, authored, plots))
        for panel in figure["panels"]:
            if (panel.get("disposition") or "") != AUTHORED:
                apply_outcome(panel, (outcomes or {}).get(panel["panel_id"]))
            panel.setdefault("target_status", target_status_of(panel))
        if answered:
            figure["note"] = "; ".join(x for x in (figure.get("note", ""), "figure_dispositions: %s%s (%s) answered by the "
                                                   "panels drawn on %s" % (
                                                       said_before.get("Decision", ""),
                                                       (" " + said_before.get("Which_Panels", "").strip())
                                                       if (said_before.get("Which_Panels") or "").strip() else "",
                                                       said_before.get("Recorded_At", ""),
                                                       min(r.get("Verified_At", "") for r in drawn_all))) if x)
        figures.append(figure)
        notes.append((figure, needs, route, disposition, dispersion, row))
    plan = {
        "schema": CP.PLAN_SCHEMA,
        "publication_id": publication,
        "reviewers": [{
            "reviewer_id": DEMO_REVIEWER,
            "name": "make_plan.py (도구)",
            "record_type": "DEMO_IDENTITY",
            # ORCID's fictional demonstration record, as the pilot plans use -
            # a demo row still needs a contact the registry can be asked about.
            "contact_type": "ORCID",
            "contact": "0000-0002-1825-0097",
            "registered_by": "make_plan.py",
            "human_attestation": "DEMO_EXAMPLE",
            "registration_date": run_date,
            "note": "사람이 아닙니다. 이 계획서의 그림·문서 항목은 아직 아무도 "
                    "눈으로 확인하지 않았다는 뜻으로 이 이름을 답니다.",
        }] + [dict(registered[rid]) for rid in sorted(used_reviewers)],
        "documents": documents,
        "grids": grids,
        "figures": figures,
        "units": units,
    }
    if views:
        plan["figure_views"] = views
    return plan, notes, panel_rows


def build(run, out_dir, crop_root, run_date, only=None, log=print,
          geometry_dir=None, identity_dir=None, regions=None, reviewers_path=None):
    rows = live_rows(run)
    confirmations = load_confirmations(run, geometry_dir, identity_dir, regions)
    reviewers = load_reviewers(reviewers_path)
    documents_known = load_documents(run)
    inventory = load_inventory(run)
    captions = _by(_rows(os.path.join(run, CAPTIONS)), "Draft_ID")
    decisions = _by(_rows(os.path.join(run, DECISIONS)), "Draft_ID")
    decided = load_figure_decisions(run)
    decided.update(load_figure_dispositions(run))
    outcomes = load_outcomes(run)
    legends = load_legends(run)
    readings = load_readings(run)
    answers = _rows(os.path.join(run, COUNTS))
    counts = dict((r["Draft_ID"], r.get("Observed_Panel_Count"))
                  for r in answers
                  if (r.get("Entry_Status") or COUNTED).strip() == COUNTED)
    # 수가 아닌 답도 읽습니다. 수만 읽으면 "셀 수 없다"고 답한 행과
    # 아무도 안 본 행이 계획서에서 같은 줄로 보입니다.
    said = dict((r["Draft_ID"],
                 ((r.get("Entry_Status") or "").strip(),
                  (r.get("Uncountable_Reason") or "").strip()
                  or (r.get("Objection_Reason") or "").strip()))
                for r in answers)
    by_pub = {}
    for row in rows:
        if only and row["Source_Document_ID"] not in only:
            continue
        by_pub.setdefault(row["Source_Document_ID"], []).append(row)

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    readiness, worksheet, panel_sheet = [], [], []
    for publication, pub_rows in sorted(by_pub.items()):
        if not BM.SAFE_ID.match(publication):
            log("건너뜀 %s: 계획서가 받는 이름이 아닙니다" % publication)
            continue
        plan, notes, panel_rows = plan_for(run, publication, pub_rows, captions, decisions,
                                           counts, crop_root, run_date, said, decided,
                                           confirmations, reviewers, documents_known, inventory,
                                           outcomes=outcomes, legends=legends,
                                           readings=readings)
        panel_sheet.extend(panel_rows)
        path = os.path.join(out_dir, "plan_%s.json" % publication)
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(plan, ensure_ascii=False, indent=1,
                                sort_keys=True))
        problems = CP.validate_plan(plan, file_root=crop_root)
        digitize = dropped = known_count = known_disp = 0
        for figure, needs, route, disposition, dispersion, row in notes:
            code, source, kind, where = dispersion
            if disposition == "GEOMETRY_NOT_AUTHORED":
                digitize += 1
            if code in RE.DISPOSITIONS:
                dropped += 1
            if "observed_panel_count" in figure:
                known_count += 1
            if code and code not in RE.DISPOSITIONS:
                known_disp += 1
            worksheet.append(dict(
                Publication_ID=publication,
                Source_Figure_ID=figure["source_figure_id"],
                Draft_ID=row["Draft_ID"],
                Figure_Number=figure["figure_number"],
                Page=figure["source_page"], Image=figure["image"],
                Route=route, Disposition=disposition,
                Observed_Panel_Count=figure.get("observed_panel_count", ""),
                Statistic_Type=statistic_type_for(disposition, code),
                Dispersion_Type=code, Errorbar_Definition_Source=source,
                Errorbar_Source_Kind=kind, Errorbar_Found_On_Page=where,
                Needs=" · ".join(needs)))
        readiness.append(dict(
            Publication_ID=publication, Figures=len(notes),
            Digitize_Figures=digitize, Panel_Counts_Known=known_count,
            Dispersion_Known=known_disp, Dropped=dropped,
            Plan=os.path.basename(path), Problem_Count=len(problems),
            Problems=" · ".join(sorted(set("%s %s" % (p["check"], p["where"])
                                           for p in problems))[:6])))
    _write(os.path.join(out_dir, READINESS), READINESS_FIELDS, readiness)
    _write(os.path.join(out_dir, WORKSHEET), WORKSHEET_FIELDS, worksheet)
    _write(os.path.join(out_dir, PANELS), PANEL_FIELDS, panel_sheet)
    log("계획서 %d편 · 그림 %d개 · 패널 계수가 있는 그림 %d개 · 오차 정의가 있는 그림 %d개"
        % (len(readiness), len(worksheet),
           sum(r["Panel_Counts_Known"] for r in readiness),
           sum(r["Dispersion_Known"] for r in readiness)))
    log("플롯 패널 %d개 · 기하 확인 %d · 정체 확인 %d · 읽을 준비 %d"
        % (len(panel_sheet),
           sum(1 for r in panel_sheet if r["Geometry"] in ("CONFIRMED", "SHARED")),
           sum(1 for r in panel_sheet if r["Identity"] == "CONFIRMED"),
           sum(1 for r in panel_sheet if r["Authored"] == "1")))
    return readiness, worksheet, out_dir


def _write(path, fields, rows):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            w.writerow(dict((k, row.get(k, "")) for k in fields))
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--crop-root")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--run-date", required=True,
                    help="이 계획서를 쓴 날. 오늘로 채우지 않습니다.")
    ap.add_argument("--geometry", help="geometry_decisions.csv가 있는 폴더 (런 기준, 기본 %s)" % GEOMETRY_DIR)
    ap.add_argument("--identity", help="identity_decisions.csv가 있는 폴더 (런 기준, 기본 %s)" % IDENTITY_DIR)
    ap.add_argument("--regions", help="panel_regions_600.csv (런 기준, 기본 %s)" % REGIONS)
    ap.add_argument("--reviewers", help="사람이 적은 검토자 등록 JSON (load_reviewers 참고). "
                                        "없으면 그림 인벤토리는 PENDING으로 남습니다.")
    args = ap.parse_args(argv)
    run = os.path.expanduser(args.run)
    build(run, os.path.expanduser(args.out),
          os.path.expanduser(args.crop_root or run), args.run_date,
          only=set(args.only or ()) or None,
          geometry_dir=args.geometry, identity_dir=args.identity, regions=args.regions,
          reviewers_path=os.path.expanduser(args.reviewers) if args.reviewers else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
