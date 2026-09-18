# -*- coding: utf-8 -*-
"""사람이 기하 제안을 보고 내린 판정을 제안 파일에 적습니다.

    python3 record_geometry.py --proposals DIR \\
        --answers DIR/geometry_answers.csv --when 2026-09-10

`geometry_page.py`가 내는 답 CSV를 받아, 그 답이 **실제로 낸 제안에 대한
것인지**, **사람이 오버레이를 보았다고 말했는지**, **누가 보았는지 말했는지**를
보고 나서 적습니다. `record_errorbar.py`·`record_decisions.py`와 같은 자리에
서 있습니다.

이 관문이 지키는 것은 눈금 값의 모양이 아니라 **누가 보았는가**입니다. 이제
`geometry_proposer`가 축을 읽으니 값은 대개 기계에서 옵니다 - 그럴수록 "이
값을 사람이 보고 통과시켰다"가 어디서 붙는지가 중요해집니다. 화면이
`Seen_By_Person`을 채워 보낼 수는 있지만 채운 것이 사람인지는 화면 밖에서 알
수 없어서, 여기서 한 번 더 봅니다: 이 답이 실제로 낸 제안과 짝이 맞는가,
이름이 붙어 있는가, `CONFIRMED`가 값을 들고 왔는가.

`HOLD`는 답이지만 적히지 않습니다. "아직 못 정하겠다"는 그 제안에 대해 사람이
한 말이고, 그것을 확인으로 적으면 정해진 것이 됩니다. 대신 이름을 대고
거절하므로 목록에서 사라지지 않습니다.

적는 파일은 `geometry_decisions.csv`이고, 제안의 열을 그대로 씁니다 - 그래야
`geometry_proposer.calibration_from`이 그 행을 바로 읽습니다. 답안지 이름과
다른 것은 규약입니다: 같으면 관문이 자기 출력을 답으로 읽습니다.
"""
import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import geometry_proposer as GP                                   # noqa: E402

PROPOSALS = "geometry_proposal.csv"
#: 리더가 프레임을 못 찾은 패널들. 제안이 아니지만 답이 올 수 있는 자리이고,
#: 그 답은 사람이 그린 프레임을 들고 옵니다.
REFUSALS = GP.REFUSED
DECISIONS = "geometry_decisions.csv"
#: 답이 들고 오는, 사람이 그린 프레임 'x0,x1,y0,y1'. 비어 있으면 리더의
#: 프레임입니다.
DRAWN = "Drawn_Frame"

#: 사람이 할 수 있는 말. `geometry_page.js`의 `VERDICTS`와 같아야 하고,
#: `test_record_geometry.py`가 셋(논리·화면·관문)이 같은지 봅니다.
VERDICTS = ("CONFIRMED", "SHARED", "REJECTED", "HOLD")

#: "이 패널엔 축이 없고 같은 그림의 다른 패널 축을 쓴다." 값은 사람이 치지
#: 않고, 그 패널의 확인된 짝을 이 관문이 옮겨 적습니다 - 같은 래스터의 같은
#: 픽셀 행이니 옮길 수 있고, 프레임이 어긋나 있으면 옮기지 않습니다.
SHARED = "SHARED"
TARGET = "Y_Axis_Shared_With"

#: 눈금 값이 있어야 적히는 판정.
NEEDS_VALUES = ("CONFIRMED",)

#: 아직 정하지 않았다는 답. 적히지 않습니다.
HELD = "HOLD"

ANSWER_REQUIRED = ("Proposal_ID", "Human_Verification_Status",
                   "Verified_By", "Seen_By_Person")

#: 계산이 서는 짝. 값만으로는 어느 눈금의 값인지 알 수 없고, 그것을
#: `Y_Tick_Pixels`의 양 끝이라고 짐작하던 것이 이 파이프라인에서 축척을
#: 20~50% 어긋나게 한 결함이었습니다.
PAIRS = "Confirmed_Tick_Values"

TRUE = ("1", "TRUE", "YES", "Y", "T")


def is_true(v):
    return str(v or "").strip().upper() in TRUE


def _numeric(*values):
    try:
        for v in values:
            float(v)
    except (TypeError, ValueError):
        return False
    return True


#: 프레임 높이의 이만큼은 프레임 밖이어도 봐줍니다 - 눈금이 프레임 선 바로
#: 위아래에 찍히는 것은 흔합니다. `geometry_page.js`의 FRAME_SLACK과 같습니다.
FRAME_SLACK = 0.10


def rows_outside_frame(proposal, rows):
    """프레임(위·아래 행 ± 여유) 밖에 선 픽셀 행들. 프레임을 모르면 빈 목록."""
    try:
        y0, y1 = float(proposal["Panel_Y0"]), float(proposal["Panel_Y1"])
    except (KeyError, TypeError, ValueError):
        return []
    slack = abs(y1 - y0) * FRAME_SLACK
    lo, hi = min(y0, y1) - slack, max(y0, y1) + slack
    return [r for r in rows if r < lo or r > hi]


def load_proposals(proposals):
    """{Proposal_ID: 제안 행} - 이 관문이 답을 붙일 수 있는 유일한 것."""
    path = os.path.join(proposals, PROPOSALS)
    if not os.path.exists(path):
        raise SystemExit("%s가 없습니다. 답을 붙일 제안이 없습니다." % path)
    return dict((r["Proposal_ID"], r) for r in
                csv.DictReader(io.open(path, encoding="utf-8-sig")))


def load_refusals(proposals):
    """{Proposal_ID: 거절 행} - 프레임 없이 답이 올 수 있는 자리들."""
    path = os.path.join(proposals, REFUSALS)
    if not os.path.exists(path):
        return {}
    return dict((r["Proposal_ID"], r) for r in
                csv.DictReader(io.open(path, encoding="utf-8-sig")))


def base_row_for(answer, proposed, refused):
    """(제안 모양의 행, 문제 목록) - 이 답이 서는 자리.

    리더의 제안이면 그 행이고, 사람이 프레임을 그렸으면 그 프레임 위에 다시
    지은 행입니다(제안이든 거절이든). 어느 쪽도 아니면 자리가 없습니다.
    """
    pid = (answer.get("Proposal_ID") or "").strip()
    drawn = (answer.get(DRAWN) or "").strip()
    origin = proposed.get(pid) if pid in proposed else refused.get(pid)
    if origin is None:
        return None, []
    if not drawn:
        return (origin if pid in proposed else None), []
    frame = GP.parse_frame(drawn)
    problems = GP.drawn_frame_problems(frame, origin.get("Region"))
    if problems:
        return None, problems
    return GP.with_drawn_frame(origin, frame), []


def load_recorded(out_path):
    """이미 적힌 판정들. 다시 적으려면 --replace가 필요합니다."""
    if not os.path.exists(out_path):
        return []
    return list(csv.DictReader(io.open(out_path, encoding="utf-8-sig")))


def check_answer(answer, proposed, refused=None):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다.

    문제는 코드와 사람이 읽을 말로 됩니다. 코드만 내면 사람은 무엇을 고쳐야
    하는지 모르고, 말만 내면 시나리오가 무엇을 붙잡는지 모릅니다.
    """
    problems = []
    refused = refused or {}
    pid = (answer.get("Proposal_ID") or "").strip()
    verdict = (answer.get("Human_Verification_Status") or "").strip().upper()
    who = (answer.get("Verified_By") or "").strip()
    top = (answer.get("Y_Tick_Top_Value") or "").strip()
    bottom = (answer.get("Y_Tick_Bottom_Value") or "").strip()
    pairs = GP.pairs_of({PAIRS: answer.get(PAIRS)})

    # 사람이 오버레이를 보았다고 말하지 않은 답은 답이 아닙니다. 이 문이
    # 지키는 것은 값의 모양이 아니라 "누가 보았는가"이고, 그것은 에이전트가
    # 대신 채울 수 없습니다.
    if not is_true(answer.get("Seen_By_Person")):
        problems.append(("NOT_SEEN_BY_PERSON",
                         "확인 페이지에서 \"이 오버레이를 직접 봤다\"를 "
                         "표시하지 않았습니다. 표시가 없는 답은 적지 않습니다."))
    # 그리고 그 사람이 누구인지. 이름 없는 확인은 되돌아볼 곳이 없는 확인이고,
    # `proposal_problems`가 그것을 PROPOSAL_VERDICT_UNATTRIBUTED로 부릅니다.
    if not who:
        problems.append(("UNATTRIBUTED",
                         "누가 보았는지 적혀 있지 않습니다. 이름 없는 확인은 "
                         "확인이 아닙니다."))

    if verdict not in VERDICTS:
        problems.append(("BAD_VERDICT",
                         "%r은 이 관문이 받는 답이 아닙니다. 받는 것: %s"
                         % (verdict or "(빈칸)", ", ".join(VERDICTS))))
        return problems

    # 낸 적 없는 제안에 답이 왔습니다. 답이 틀렸다는 말이 아니라, 이 답이 어느
    # 그림의 어느 자리에 대한 것인지 이 관문이 알 수 없다는 말입니다.
    if pid not in proposed and pid not in refused:
        problems.append(("NOT_PROPOSED",
                         "%r은 이 폴더가 낸 제안도, 프레임을 못 찾았다고 적은 "
                         "패널도 아닙니다. 제안을 다시 낸 뒤의 답이거나, 다른 "
                         "그림의 답입니다." % (pid or "(빈칸)")))
    # 프레임. 사람이 그렸으면 그 프레임이 서는지 보고, 리더가 못 찾은 패널에
    # 그리지 않은 확인은 붙일 자리가 없습니다.
    mine, frame_problems = base_row_for(answer, proposed, refused)
    problems.extend(frame_problems)
    drawn = (answer.get(DRAWN) or "").strip()
    if pid in refused and pid not in proposed and not drawn \
            and verdict in NEEDS_VALUES + (SHARED,):
        problems.append(("FRAME_NOT_DRAWN",
                         "리더가 프레임을 찾지 못한 패널입니다. 프레임을 그리지 "
                         "않은 %s은 붙일 자리가 없습니다." % verdict))
    if drawn and (answer.get("Value_Source") or "").strip().upper() == "READ":
        # 리더가 읽은 값은 리더의 프레임 옆에서 읽은 것입니다. 프레임을 새로
        # 그렸으면 그 값이 이 프레임의 눈금에 붙는다는 근거가 없습니다.
        problems.append(("READ_VALUES_ON_A_DRAWN_FRAME",
                         "프레임을 그렸는데 값은 리더가 읽은 것을 그대로 "
                         "씁니다. 그 값은 다른 프레임 옆에서 읽은 것입니다."))

    shared = (answer.get(TARGET) or "").strip()
    if verdict == SHARED:
        # 어느 패널의 축인지. 자기 자신은 공유가 아니고, 낸 적 없는 패널이나
        # 다른 그림의 패널은 옮겨 올 픽셀 행이 없으며, 프레임이 다른 행에
        # 서 있으면 그 패널의 눈금 행은 이 패널의 것이 아닙니다.
        if top or bottom or pairs:
            problems.append(("SHARED_WITH_A_TICK_VALUE",
                             "다른 패널의 축을 쓴다면서 이 패널의 눈금 값이 "
                             "붙어 있습니다. 어느 쪽이 답인지 이 관문은 모릅니다."))
        if not shared:
            problems.append(("SHARED_TARGET_MISSING",
                             "어느 패널의 축을 쓰는지 적혀 있지 않습니다."))
        elif shared == pid:
            problems.append(("SHARED_WITH_ITSELF",
                             "자기 자신의 축을 쓴다는 것은 공유가 아닙니다."))
        elif shared not in proposed and shared not in refused:
            problems.append(("SHARED_TARGET_UNKNOWN",
                             "%r은 이 폴더가 낸 제안도 프레임을 못 찾은 패널도 "
                             "아닙니다. 옮겨 올 축이 없습니다." % shared))
        elif mine is not None:
            # 빌려주는 패널의 프레임은 확인된 행의 것입니다 - 제안의 잰
            # 프레임일 수도, 사람이 그린 것일 수도 있고, 어느 쪽이든 옮겨
            # 적을 때(`record`) 그 행에 대고 봅니다. 여기서는 그림만 봅니다.
            theirs = proposed.get(shared) or refused[shared]
            if (mine.get("Raster") or "") != (theirs.get("Raster") or ""):
                problems.append(("SHARED_ACROSS_RASTERS",
                                 "%s은 다른 그림의 패널입니다. 픽셀 행은 그림의 "
                                 "것이라 옮겨 올 수 없습니다." % shared))
    elif shared:
        problems.append(("TARGET_WITHOUT_SHARING",
                         "%s인데 다른 패널의 축(%s)을 쓴다고도 적혀 있습니다. "
                         "둘 중 하나입니다." % (verdict, shared)))

    if verdict in NEEDS_VALUES:
        for label, value in (("맨 위", top), ("맨 아래", bottom)):
            try:
                float(value)
            except ValueError:
                problems.append(("TICK_VALUE_MISSING",
                                 "확인이라면서 %s 눈금 값이 %r입니다. 값 없는 "
                                 "기하는 계산이 되지 않습니다."
                                 % (label, value)))
        if top and bottom and top == bottom:
            problems.append(("TICK_VALUES_EQUAL",
                             "맨 위 눈금과 맨 아래 눈금이 둘 다 %s입니다. 축이 "
                             "아닙니다." % top))
        # 그리고 값이 어느 눈금 행에 붙는지. 값 둘만 받아 두면 픽셀은 다음
        # 단계가 짐작해야 하고, 그 짐작은 `Y_Tick_Pixels`의 양 끝이었습니다 -
        # 리더의 사다리가 눈금 전부를 읽지 못하면 그 짝은 틀리고, 잔차 0.1px에
        # 앞뒤가 맞는 채로 축척이 절반이 됩니다.
        if len(pairs) != 2:
            problems.append(("CALIBRATION_PAIRS_MISSING",
                             "확인인데 값@픽셀 짝이 %d개입니다. 계산은 둘이 "
                             "필요하고, 어느 눈금의 값인지는 눈금 목록에서 "
                             "짐작할 수 없습니다." % len(pairs)))
        elif pairs[0][1] == pairs[1][1]:
            problems.append(("CALIBRATION_PAIRS_ONE_ROW",
                             "두 값이 같은 픽셀 행 %g에 붙어 있습니다."
                             % pairs[0][1]))
        else:
            # 사람이 적은 값과 짝이 서로 다른 말을 하면 어느 쪽이 답인지 이
            # 관문은 모릅니다. 화면이 둘을 함께 만들지만, 답 CSV는 손으로
            # 고칠 수 있는 파일입니다.
            said = sorted((float(top), float(bottom))) if _numeric(top, bottom) else None
            if said and sorted(v for v, _px in pairs) != said:
                problems.append(("CALIBRATION_PAIRS_DISAGREE",
                                 "적으신 값(%s, %s)과 짝의 값(%s)이 다릅니다."
                                 % (top, bottom,
                                    ", ".join("%g" % v for v, _px in pairs))))
            # 그리고 짝의 행이 이 프레임 안에 있는지. 사람이 그림에 찍은 줄은
            # 어디든 찍힐 수 있고, 페이지가 먼저 막지만 답 CSV는 손으로 고칠
            # 수 있는 파일입니다. 프레임 밖의 눈금은 이 프레임의 눈금이 아니고,
            # 프레임이 틀린 것의 답은 "틀렸다"입니다.
            if mine is not None:
                outside = rows_outside_frame(mine, [px for _v, px in pairs])
                if outside:
                    problems.append(("CALIBRATION_ROW_OUTSIDE_FRAME",
                                     "짝의 픽셀 행 %s이 이 %s의 프레임(%s..%s) 밖입니다. "
                                     "프레임이 틀렸다면 답은 REJECTED입니다."
                                     % (", ".join("%g" % r for r in outside),
                                        "그린 프레임" if drawn else "제안",
                                        mine.get("Panel_Y0"), mine.get("Panel_Y1"))))
    elif verdict != SHARED and (top or bottom or pairs):
        # 거절과 보류에 값이 붙어 왔습니다. 붙은 값이 무엇을 뜻하는지 - 틀린
        # 프레임에서 읽은 값인지, 고쳐 준 값인지 - 이 관문은 모릅니다.
        problems.append(("VALUES_WITHOUT_CONFIRMATION",
                         "%s에 눈금 값이 붙어 있습니다. 확인하지 않은 기하의 "
                         "눈금 값이 무엇을 뜻하는지 이 관문은 모릅니다."
                         % verdict))

    if verdict == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 "
                                 "남겨 둡니다."))
    return problems


def record(proposals, answers, when, out_path=None, replace=False,
           log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로).

    `answers_path`는 답이 어느 파일에서 왔는지입니다. 그 파일이 곧 이 관문이
    적는 파일이면 멈춥니다 - 그러면 관문은 자기가 적어 둔 것을 답으로 읽고,
    같은 답을 전부 이미 적힌 것으로 거절한 뒤, 원본을 자기 모양으로
    덮어씁니다. 처분 관문에서 실제로 한 번 그렇게 덮어썼습니다.
    """
    missing = [c for c in ANSWER_REQUIRED
               if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 확인 페이지가 내려준 "
                         "파일이 맞습니까?" % ", ".join(missing))
    proposed = load_proposals(proposals)
    refused = load_refusals(proposals)
    out_path = out_path or os.path.join(proposals, DECISIONS)
    if answers_path and os.path.exists(answers_path) \
            and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s). 확인 페이지가 "
                         "내려준 파일은 geometry_answers.csv이고, 이 관문이 "
                         "적는 파일은 %s입니다." % (out_path, DECISIONS))
    existing = load_recorded(out_path)
    settled = set(r["Proposal_ID"] for r in existing)

    written, turned_away = [], []
    for answer in answers:
        pid = (answer.get("Proposal_ID") or "").strip()
        problems = check_answer(answer, proposed, refused)
        if problems:
            turned_away.append((pid or "(빈칸)", problems))
            continue
        if pid in settled and not replace:
            turned_away.append((pid, [("ALREADY_RECORDED",
                                       "이 제안은 이미 판정되어 있습니다. 바꾸려면 "
                                       "--replace를 주십시오.")]))
            continue
        # 제안의 행을 그대로 들고 가고, 사람이 준 것만 얹습니다. 새 모양으로
        # 다시 적으면 `calibration_from`이 읽는 눈금 픽셀이 사라지고, 확인된
        # 기하가 계산으로 이어지지 않습니다. 프레임을 그렸으면 그 프레임 위에
        # 지은 행이고, 거절과 보류에는 그릴 것이 없으니 원래 행(거절 목록의
        # 것이면 프레임 없는 제안 모양)입니다.
        base, _fp = base_row_for(answer, proposed, refused)
        if base is None:
            # 프레임 없는 패널의 거절. 프레임은 없고, 있는 척도 하지 않습니다.
            base = GP.refusal_as_proposal(refused[pid])
        row = dict(base)
        row.update({
            "Human_Verification_Status": (
                answer.get("Human_Verification_Status") or "").strip().upper(),
            "Y_Tick_Top_Value": (answer.get("Y_Tick_Top_Value") or "").strip(),
            "Y_Tick_Bottom_Value": (answer.get("Y_Tick_Bottom_Value") or "").strip(),
            PAIRS: (answer.get(PAIRS) or "").strip(),
            TARGET: (answer.get(TARGET) or "").strip(),
            "Verified_By": (answer.get("Verified_By") or "").strip(),
            "Verified_At": when,
            "Note": (answer.get("Note") or "").strip(),
        })
        written.append(row)

    # 축을 빌리는 줄은 빌려주는 패널이 확인된 뒤에야 적힙니다 - 이 묶음에서든,
    # 이미 적힌 것에서든. 옮겨 적는 것은 그 패널의 짝뿐이고, 값 두 칸은 비워
    # 둡니다: 이 패널의 값이 아닙니다. 그 패널이 아직 확인되지 않았으면 이
    # 줄은 거절되고, 그 패널이 확인된 뒤 다시 내면 됩니다.
    confirmed = dict((r["Proposal_ID"], r) for r in existing + written
                     if (r.get("Human_Verification_Status") or "").upper() == "CONFIRMED")
    still = []
    for row in written:
        if (row.get("Human_Verification_Status") or "").upper() != SHARED:
            still.append(row)
            continue
        target = confirmed.get(row.get(TARGET))
        if target is None:
            turned_away.append((row["Proposal_ID"], [("SHARED_TARGET_NOT_CONFIRMED",
                            "%s의 축을 쓴다는데 %s이 이 답 묶음에서도, 이미 적힌 "
                            "것에서도 CONFIRMED가 아닙니다. 그 패널이 확인된 뒤 "
                            "다시 내 주십시오." % (row.get(TARGET), row.get(TARGET)))]))
            continue
        # 확인된 행의 프레임에 대고 한 번 더. 빌려주는 패널이 사람이 그린
        # 프레임 위에 섰으면 그 프레임은 여기서 처음 보입니다.
        same, px = GP.frames_share_rows(row, target)
        if not same:
            turned_away.append((row["Proposal_ID"], [("SHARED_FRAME_MISALIGNED",
                                "이 패널의 프레임이 %s의 확인된 프레임과 %s px 어긋나 "
                                "있습니다." % (row.get(TARGET), "%.0f" % px if px is not None else "?"))]))
            continue
        row[PAIRS] = (target.get(PAIRS) or "").strip()
        still.append(row)
    written = still

    keep = [r for r in existing
            if r["Proposal_ID"] not in set(w["Proposal_ID"] for w in written)]
    rows = sorted(keep + written, key=lambda x: x["Proposal_ID"])
    # 적기 전에 마지막으로, 적으려는 파일 전체를 제안 규칙에 걸어 봅니다.
    # 여기서 걸리는 것은 이 관문의 버그이지 사람의 답이 아니고, 그 둘을 같은
    # 자리에서 잡지 않으면 버그가 사람의 실수처럼 보입니다.
    bad = GP.proposal_problems(rows)
    if bad:
        raise SystemExit("적으려는 파일이 제안 규칙을 어깁니다: %s"
                         % "; ".join("%s %s %s" % b for b in bad[:5]))
    GP.write_proposals(out_path, rows)

    log("적음 %d · 거절 %d · 이미 있던 것 %d"
        % (len(written), len(turned_away), len(keep)))
    for name, problems in turned_away:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, turned_away, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--when", required=True,
                    help="사람이 오버레이를 본 날짜. 오늘로 채우지 않습니다 - "
                         "언제 보았는지는 이 프로그램이 아는 것이 아닙니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(
        os.path.expanduser(a.proposals), answers, a.when, out_path=a.out,
        replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
