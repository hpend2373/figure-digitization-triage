# -*- coding: utf-8 -*-
"""그림 하나의 처분을 적습니다 - 캡션 심사와 계수가 정하지 못한, 또는 잘못 정한 것.

    python3 fdt/record_dispositions.py --run RUN --plans PLANS \
        --answers figure_disposition_answers.csv --when 2026-10-14

`record_decisions`는 판정 페이지가 묻는 세 물음(셀 수 없음·캡션 어긋남·크롭
다툼)만 받습니다. run2 2026-10-14 결정 페이지(R7)에서 그 밖의 처분이 나왔습니다:
캡션 심사가 '연관 그림'(ASSOCIATION_ONLY_NOT_TARGET)이나 '이진 사건'으로 본 그림
35개를 사람이(그리고 사람이 승인한 PDF 조사가) 보니, 14개는 조건별 집단 평균을
그린 보통 그림이고 20개는 이 리뷰의 결과가 아니며 1개는 데이터가 없었습니다.
'패널 없음'으로 답했는데 계수는 패널이 있다고 한 그림은 다시 자르거나 다시
그려야 하고, '일부 패널만'의 그 패널이 다른 패널이었던 그림도 있습니다. 이
처분들을 적을 물음이 `record_decisions`에는 없어서, 그림 하나에 한 줄인 이 파일을
따로 둡니다(`figure_dispositions.csv`). `make_plan`은 이 파일을
`figure_decisions.csv`보다 먼저 읽습니다 - 같은 그림을 나중에, 더 보고 정한
것입니다.

받는 처분:
    DIGITIZE     값을 읽을 보통 그림이다 (캡션 심사가 다르게 보았어도)
    NON_TARGET   이 리뷰의 결과가 아니다 (NON_TARGET_OUTCOME)
    ASSOCIATION  두 변수의 관계를 그린 그림이다 (ASSOCIATION_EXTRACT)
    NOT_DATA     데이터 그림이 아니다
    RECROP       크롭을 다시 해야 한다
    REDRAW       패널 영역을 다시 그려야 한다
    PARTIAL      일부 패널만 데이터다 (Which_Panels에 어느 패널인지)

이 관문이 지키는 것은 `record_decisions`와 같이 **누가 보았는가**입니다. 사람이
그림을 보았다는 답(Seen_By_Person=1)이거나, 사람이 승인한 관찰(`approval`:
Verified_By·Observed_By·Approval_Ref가 모두 있는 답)만 받고, 기록에 그대로
남깁니다. 계획서에 없는 그림의 답, HOLD, 이미 적힌 그림의 답(--replace 없이)은
적지 않습니다.
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

DRAFT = "figure_intake_draft.csv"
DISPOSITIONS = "figure_dispositions.csv"
#: 계획서의 그림 목록 - 이 관문이 답을 붙일 수 있는 그림들.
PLAN_FIGURES = "plan_figures.csv"

CHOICES = ("DIGITIZE", "NON_TARGET", "ASSOCIATION", "NOT_DATA", "RECROP", "REDRAW", "PARTIAL", "HOLD")
NEEDS_PANELS = ("PARTIAL",)
HELD = "HOLD"

ANSWER_REQUIRED = ("Draft_ID", "Disposition", "Verified_By", "Seen_By_Person")

FIELDS = ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page", "Disposition", "Which_Panels",
          "Verified_By", "Seen_By_Person", "Observed_By", "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")


def load_planned(plans):
    """{Draft_ID: 계획서 행}."""
    path = os.path.join(plans, PLAN_FIGURES)
    return dict((r["Draft_ID"], r) for r in csv.DictReader(io.open(path, encoding="utf-8-sig")))


def load_recorded(out_path):
    if not os.path.exists(out_path):
        return []
    return list(csv.DictReader(io.open(out_path, encoding="utf-8-sig")))


def check_answer(answer, planned):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다."""
    problems = []
    draft = (answer.get("Draft_ID") or "").strip()
    choice = (answer.get("Disposition") or "").strip().upper()
    panels = (answer.get("Which_Panels") or "").strip()
    who = (answer.get("Verified_By") or "").strip()
    problems.extend(approval.seen_problems(answer, who, "그림을 직접 보았다는 표시가 없습니다. 표시가 없는 답은 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 보았는지(또는 승인했는지) 적혀 있지 않습니다."))
    if choice not in CHOICES:
        problems.append(("BAD_DISPOSITION", "%r은 이 관문이 받는 처분이 아닙니다. 받는 것: %s"
                         % (choice or "(빈칸)", ", ".join(CHOICES))))
        return problems
    if draft not in planned:
        problems.append(("NOT_PLANNED", "%r은 계획서의 그림이 아닙니다. 계획서를 다시 낸 뒤의 답이거나, "
                                        "다른 run의 답입니다." % (draft or "(빈칸)")))
    if choice in NEEDS_PANELS and not panels:
        problems.append(("PARTIAL_WITHOUT_PANELS", "일부 패널만 데이터라고 하면서 어느 패널인지 적지 않았습니다."))
    if choice not in NEEDS_PANELS and panels:
        problems.append(("PANELS_WITHOUT_PARTIAL", "%s에는 패널 이름이 붙지 않습니다 (%r)." % (choice, panels)))
    if choice == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 남겨 둡니다."))
    return problems


def record(run, plans, answers, when, out_path=None, via="DECISION_PAGE", replace=False, log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    planned = load_planned(plans)
    draft = dict((r["Draft_ID"], r) for r in csv.DictReader(io.open(os.path.join(run, DRAFT), encoding="utf-8-sig")))
    out_path = out_path or os.path.join(run, DISPOSITIONS)
    if answers_path and os.path.exists(answers_path) and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s)." % out_path)
    existing = load_recorded(out_path)
    settled = set(r["Draft_ID"] for r in existing)
    seen_here, twice = set(), set()
    for answer in answers:
        d = (answer.get("Draft_ID") or "").strip()
        if d in seen_here:
            twice.add(d)
        seen_here.add(d)

    written, refused = [], []
    for answer in answers:
        did = (answer.get("Draft_ID") or "").strip()
        if did in twice:
            refused.append((did, [("ANSWERED_TWICE", "%s에 답이 둘 있습니다. 그림 하나에 처분은 하나입니다." % did)]))
            continue
        problems = check_answer(answer, planned)
        if problems:
            refused.append((did or "(빈칸)", problems))
            continue
        if did in settled and not replace:
            refused.append((did, [("ALREADY_DECIDED", "이 그림은 이미 처분되어 있습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        plan = planned[did]
        prov = approval.provenance(answer)
        written.append({
            "Draft_ID": did, "Source_Document_ID": draft.get(did, {}).get("Source_Document_ID", ""),
            "Figure_Number": plan.get("Figure_Number", ""), "Page": plan.get("Page", ""),
            "Disposition": (answer.get("Disposition") or "").strip().upper(),
            "Which_Panels": (answer.get("Which_Panels") or "").strip(),
            "Verified_By": (answer.get("Verified_By") or "").strip(),
            "Seen_By_Person": prov["Seen_By_Person"], "Observed_By": prov["Observed_By"], "Approval_Ref": prov["Approval_Ref"],
            "Recorded_Via": via, "Recorded_At": when, "Note": (answer.get("Note") or "").strip(),
        })
    keep = [r for r in existing if r["Draft_ID"] not in set(w["Draft_ID"] for w in written)]
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in sorted(keep + written, key=lambda x: x["Draft_ID"]):
            w.writerow(dict((c, r.get(c, "")) for c in FIELDS))
    os.replace(tmp, out_path)
    log("적음 %d · 거절 %d · 이미 있던 것 %d" % (len(written), len(refused), len(keep)))
    for name, problems in refused:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, refused, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--plans", required=True, help="이 답이 대답한 계획서 폴더 (plan_figures.csv)")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="DECISION_PAGE")
    ap.add_argument("--when", required=True, help="그림을 본(또는 승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.run), os.path.expanduser(a.plans), answers, a.when,
                               out_path=a.out, via=a.via, replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
