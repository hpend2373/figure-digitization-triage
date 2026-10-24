# -*- coding: utf-8 -*-
"""한 패널의 값이 어떤 분포·척도인지 적습니다 (결정 D15, 2026-10-20).

    python3 record_shape.py --run RUN --answers shape_answers.csv --when 2026-10-20 [--replace]

격자 관문은 비율 척도에서 SE × √n이 평균의 1.5배를 넘는 칸을 막습니다(DISPERSION_IMPLIES_SKEW): 결과가
치우친 것이거나(스펙트럼 파워, 호르몬 농도 …) 숫자 하나가 틀린 것이고, 어느 쪽인지 말해 달라는 것입니다.
그 말을 적을 길이 없었습니다 - `compile_plan`은 Distribution_Shape를 늘 UNKNOWN으로, Value_Scale을 늘 RATIO로
썼습니다. 이 관문이 그 답을 `shape_decisions.csv`(런 바로 아래)에 적고, `make_plan`이 패널의 단위에 옮깁니다:

    Distribution_Shape   RIGHT_SKEWED / LEFT_SKEWED / SYMMETRIC / UNKNOWN (`grid_engine.FIG_DISTRIBUTION_SHAPES`)
    Value_Scale          RATIO / CHANGE (`grid_engine.FIG_VALUE_SCALES`) - 차이·변화량이면 CHANGE이고, 그러면
                         비율 척도의 검사가 묻지 않습니다
    Shape_Basis          왜 그런지 한두 문장(결과가 무엇인지, 논문의 말). 추정의 표식("probably", "assumed" …)이
                         든 근거는 받지 않습니다 - 그런 근거는 근거가 없는 것보다 나쁩니다.

다른 관문과 같이 **누가 보았는가**를 지킵니다(사람이 본 답이거나 사람이 승인한 관찰, `approval`). 그리고
그 패널의 정체 카드가 확인되어 있어야 합니다 - 확인되지 않은 패널에는 적을 단위가 없습니다.
"""
import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import approval                                                  # noqa: E402
import grid_engine                                               # noqa: E402
import kernel                                                    # noqa: E402

DECISIONS = "shape_decisions.csv"
IDENTITY = os.path.join("seg", "identity600", "identity_decisions.csv")
ANSWER_REQUIRED = ("Proposal_ID", "Distribution_Shape", "Value_Scale", "Shape_Basis", "Verified_By",
                   "Seen_By_Person")
FIELDS = ("Proposal_ID", "Distribution_Shape", "Value_Scale", "Shape_Basis", "Verified_By", "Seen_By_Person",
          "Observed_By", "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def check_answer(answer, cards):
    """(문제 목록). 빈 목록이면 적힐 수 있습니다."""
    problems = []
    pid = (answer.get("Proposal_ID") or "").strip()
    card = cards.get(pid)
    if card is None:
        problems.append(("UNKNOWN_PANEL", "%s는 정체 카드에 없습니다." % (pid or "(빈칸)")))
    elif (card.get("Human_Verification_Status") or "").strip().upper() != "CONFIRMED":
        problems.append(("PANEL_NOT_CONFIRMED", "%s의 정체 카드가 확인되지 않았습니다." % pid))
    shape = (answer.get("Distribution_Shape") or "").strip().upper()
    if shape not in grid_engine.FIG_DISTRIBUTION_SHAPES:
        problems.append(("BAD_DISTRIBUTION_SHAPE", "Distribution_Shape=%r (받는 값: %s)"
                         % (shape, "/".join(grid_engine.FIG_DISTRIBUTION_SHAPES))))
    scale = (answer.get("Value_Scale") or "").strip().upper()
    if scale not in grid_engine.FIG_VALUE_SCALES:
        problems.append(("BAD_VALUE_SCALE", "Value_Scale=%r (받는 값: %s)"
                         % (scale, "/".join(grid_engine.FIG_VALUE_SCALES))))
    basis = (answer.get("Shape_Basis") or "").strip()
    if not basis:
        problems.append(("NO_SHAPE_BASIS", "왜 그런 분포·척도인지(결과가 무엇인지, 논문의 말)를 적어야 합니다."))
    else:
        marker = kernel.fig_unresolved_marker(basis)
        if marker:
            problems.append(("UNRESOLVED_SHAPE_BASIS", "근거에 %r가 들어 있습니다 - 추정은 근거가 아닙니다." % marker))
    who = (answer.get("Verified_By") or "").strip()
    if not who:
        problems.append(("UNATTRIBUTED", "누가 정했는지(Verified_By)가 없습니다."))
    problems += approval.seen_problems(answer, who, "사람이 그 패널과 근거를 보았다고 표시하지 않았습니다.")
    return problems


def record(run, answers, when, out_path=None, via="DECISION_PAGE", replace=False, log=print):
    """(적힌 행, 거절된 (패널, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    cards = dict((r["Proposal_ID"], r) for r in _rows(os.path.join(run, IDENTITY)))
    out_path = out_path or os.path.join(run, DECISIONS)
    existing = _rows(out_path)
    settled = set(r["Proposal_ID"] for r in existing)
    written, refused = [], []
    for answer in answers:
        pid = (answer.get("Proposal_ID") or "").strip()
        problems = check_answer(answer, cards)
        if not problems and pid in settled and not replace:
            problems = [("ALREADY_RECORDED", "이미 적혀 있습니다. 바꾸려면 --replace.")]
        if problems:
            refused.append((pid or "(빈칸)", problems))
            continue
        prov = approval.provenance(answer)
        written.append(dict(Proposal_ID=pid,
                            Distribution_Shape=(answer.get("Distribution_Shape") or "").strip().upper(),
                            Value_Scale=(answer.get("Value_Scale") or "").strip().upper(),
                            Shape_Basis=(answer.get("Shape_Basis") or "").strip(),
                            Verified_By=(answer.get("Verified_By") or "").strip(),
                            Seen_By_Person=prov["Seen_By_Person"], Observed_By=prov["Observed_By"],
                            Approval_Ref=prov["Approval_Ref"], Recorded_Via=via, Recorded_At=when,
                            Note=(answer.get("Note") or "").strip()))
    now = set(w["Proposal_ID"] for w in written)
    merged = [r for r in existing if r["Proposal_ID"] not in now] + written
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for row in merged:
            w.writerow(dict((k, row.get(k, "")) for k in FIELDS))
    os.replace(tmp, out_path)
    for pid, problems in refused:
        log("거절 %s" % pid)
        for code, message in problems:
            log("     %-26s %s" % (code, message))
    log("적음 %d · 거절 %d · 이미 있던 것 %d" % (len(written), len(refused), len(existing)))
    return written, refused, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="DECISION_PAGE")
    ap.add_argument("--when", required=True, help="사람이 정한(또는 승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = _rows(a.answers)
    _w, refused, _p = record(a.run, answers, a.when, out_path=a.out, via=a.via, replace=a.replace)
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
