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
DECISIONS = "geometry_decisions.csv"

#: 사람이 할 수 있는 말. `geometry_page.js`의 `VERDICTS`와 같아야 하고,
#: `test_record_geometry.py`가 셋(논리·화면·관문)이 같은지 봅니다.
VERDICTS = ("CONFIRMED", "REJECTED", "HOLD")

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


def load_proposals(proposals):
    """{Proposal_ID: 제안 행} - 이 관문이 답을 붙일 수 있는 유일한 것."""
    path = os.path.join(proposals, PROPOSALS)
    if not os.path.exists(path):
        raise SystemExit("%s가 없습니다. 답을 붙일 제안이 없습니다." % path)
    return dict((r["Proposal_ID"], r) for r in
                csv.DictReader(io.open(path, encoding="utf-8-sig")))


def load_recorded(out_path):
    """이미 적힌 판정들. 다시 적으려면 --replace가 필요합니다."""
    if not os.path.exists(out_path):
        return []
    return list(csv.DictReader(io.open(out_path, encoding="utf-8-sig")))


def check_answer(answer, proposed):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다.

    문제는 코드와 사람이 읽을 말로 됩니다. 코드만 내면 사람은 무엇을 고쳐야
    하는지 모르고, 말만 내면 시나리오가 무엇을 붙잡는지 모릅니다.
    """
    problems = []
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
    if pid not in proposed:
        problems.append(("NOT_PROPOSED",
                         "%r은 이 폴더가 낸 제안이 아닙니다. 제안을 다시 낸 "
                         "뒤의 답이거나, 다른 그림의 답입니다."
                         % (pid or "(빈칸)")))

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
    elif top or bottom or pairs:
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
    out_path = out_path or os.path.join(proposals, DECISIONS)
    if answers_path and os.path.exists(answers_path) \
            and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s). 확인 페이지가 "
                         "내려준 파일은 geometry_answers.csv이고, 이 관문이 "
                         "적는 파일은 %s입니다." % (out_path, DECISIONS))
    existing = load_recorded(out_path)
    settled = set(r["Proposal_ID"] for r in existing)

    written, refused = [], []
    for answer in answers:
        pid = (answer.get("Proposal_ID") or "").strip()
        problems = check_answer(answer, proposed)
        if problems:
            refused.append((pid or "(빈칸)", problems))
            continue
        if pid in settled and not replace:
            refused.append((pid, [("ALREADY_RECORDED",
                                   "이 제안은 이미 판정되어 있습니다. 바꾸려면 "
                                   "--replace를 주십시오.")]))
            continue
        # 제안의 행을 그대로 들고 가고, 사람이 준 것만 얹습니다. 새 모양으로
        # 다시 적으면 `calibration_from`이 읽는 눈금 픽셀이 사라지고, 확인된
        # 기하가 계산으로 이어지지 않습니다.
        row = dict(proposed[pid])
        row.update({
            "Human_Verification_Status": (
                answer.get("Human_Verification_Status") or "").strip().upper(),
            "Y_Tick_Top_Value": (answer.get("Y_Tick_Top_Value") or "").strip(),
            "Y_Tick_Bottom_Value": (answer.get("Y_Tick_Bottom_Value") or "").strip(),
            PAIRS: (answer.get(PAIRS) or "").strip(),
            "Verified_By": (answer.get("Verified_By") or "").strip(),
            "Verified_At": when,
            "Note": (answer.get("Note") or "").strip(),
        })
        written.append(row)

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
        % (len(written), len(refused), len(keep)))
    for name, problems in refused:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, refused, out_path


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
