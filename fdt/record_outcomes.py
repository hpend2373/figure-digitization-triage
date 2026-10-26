# -*- coding: utf-8 -*-
"""패널 하나가 이 리뷰의 어느 결과인지 - 또는 결과가 아닌지 - 를 적습니다 (R4).

    python3 fdt/record_outcomes.py --run RUN --plans PLANS \
        --answers outcome_answers.csv --when 2026-10-16

계획서는 대상 패널(Target_Status=TARGET)마다 화면에 보이는 결과의 이름을
요구합니다(`batch_manifests`의 MISSING_TARGET_OUTCOME_LABEL). 기하와 정체를 다
확인해 읽을 준비가 된 패널은 그 이름을 정체 확인(Outcome_Name)에서 가져오지만,
사람이 손으로 읽기로 한 패널(MANUAL_DIGITIZE)이나 오차 정의가 없어 풀에서 뺀
그림의 패널(NO_SUMMARY_STATISTIC)은 이름을 받을 길이 없었습니다. run2에서 그런
패널이 126개였고, 2026-10-16 결정 묶음에서 사람이 110개에 이름을, 16개에 "목표
결과 아님"을 답했습니다. 이 관문이 그 답을 `outcome_decisions.csv`에 적고,
`make_plan`이 읽습니다.

받는 답(한 패널에 한 줄, Panel_ID는 계획서의 이름 `<Draft_ID>_P<번호>`):
    LABEL        Outcome_Label(과 Unit)이 이 패널의 결과다
    NON_TARGET   이 패널은 이 리뷰의 결과가 아니다 (NON_TARGET_OUTCOME으로 닫힘)
    HOLD         아직 정하지 않음 - 적지 않음

이 관문이 지키는 것은 다른 관문과 같습니다: **누가 보았는가**(사람이 본 답이거나
사람이 승인한 관찰, `approval`), 그리고 **이 계획서의 패널인가**. 이름은 논문이
그린 것의 이름이어야 하고, 추정의 표식("TBD", "unknown", "assumed" …)이 든
이름은 받지 않습니다 - 그런 이름이 붙은 패널은 이름이 없는 패널보다 나쁩니다.
닫힌 패널(NOT_DATA, NON_TARGET)에 이름을 붙이는 답도 받지 않습니다: 그 패널을
다시 여는 것은 그림의 처분(`record_dispositions`)이 할 일입니다.

예외 하나 - **이 관문이 스스로 닫은 패널**(REOPEN). 패널이 닫힌 까닭이 이 파일의 NON_TARGET
한 줄뿐이면(계획서의 그 패널 사유가 `outcome_decisions:`로 시작), `--replace`로 그 줄을 LABEL로
바꾸는 답은 받습니다: 그 패널을 닫은 것도 이 관문의 답이었으니, 되돌리는 것도 이 관문의 답입니다.
run2 2026-10-18: 한 그림의 SBP 패널을 다른 그림과 중복이라 닫았다가(H12), 그 다른 그림의 축을 믿을 수
없다는 것이 드러나(N02) 다시 열어야 했습니다. 그림의 처분이 닫은 패널, NOT_DATA, `--replace` 없는 답,
지금 기록에 NON_TARGET 줄이 없는 패널은 여전히 PANEL_CLOSED입니다.
"""
import argparse
import csv
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import approval                                                  # noqa: E402
import kernel                                                    # noqa: E402

DECISIONS = "outcome_decisions.csv"
CHOICES = ("LABEL", "NON_TARGET", "HOLD")
LABEL, NON_TARGET, HELD = "LABEL", "NON_TARGET", "HOLD"
#: 계획서에서 이미 닫힌 패널 - 이름을 붙일 자리가 아닙니다.
CLOSED = ("NOT_DATA", "NON_TARGET")

ANSWER_REQUIRED = ("Panel_ID", "Decision", "Verified_By", "Seen_By_Person")
FIELDS = ("Panel_ID", "Draft_ID", "Panel_Index", "Publication_ID", "Decision", "Outcome_Label", "Unit",
          "Verified_By", "Seen_By_Person", "Observed_By", "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")
PANEL_ID = re.compile(r"^(?P<draft>.+)_P(?P<index>\d+)$")


#: 계획서의 패널 사유가 이것으로 시작하면 그 패널을 닫은 것은 outcome_decisions의 NON_TARGET 줄입니다
#: (`make_plan.apply_outcome`).
CLOSED_BY_OUTCOME = "outcome_decisions:"


def load_planned(plans):
    """{Panel_ID: (Publication_ID, 계획서의 Target_Status, 이 관문의 NON_TARGET이 닫았는가)} - 계획서들의 모든 패널."""
    out = {}
    for path in sorted(glob.glob(os.path.join(plans, "plan_*.json"))):
        plan = json.load(io.open(path, encoding="utf-8"))
        for fig in plan.get("figures") or []:
            for p in fig.get("panels") or []:
                if not PANEL_ID.match(p.get("panel_id") or ""):
                    continue
                status = (p.get("target_status") or "").strip().upper()
                if not status:
                    status = "NOT_DATA" if (p.get("disposition") or "").upper() in ("NOT_DATA", "DUPLICATE_OR_DECORATIVE") \
                        else "NON_TARGET" if (p.get("disposition") or "").upper() == "NON_TARGET_OUTCOME" else "TARGET"
                by_outcome = status == "NON_TARGET" and str(p.get("reason") or "").startswith(CLOSED_BY_OUTCOME)
                out[p["panel_id"]] = (plan.get("publication_id", ""), status, by_outcome)
    return out


def load_recorded(out_path):
    if not os.path.exists(out_path):
        return []
    return list(csv.DictReader(io.open(out_path, encoding="utf-8-sig")))


def placeholder_in(text):
    """이름이 논문의 말이 아니라 추정을 담고 있으면 그 표식."""
    up = " %s " % re.sub(r"\s+", " ", str(text or "").upper())
    for marker in kernel.FIG_UNRESOLVED_MARKERS:
        if marker in up:
            return marker
    if str(text or "").strip().upper() in kernel.FIG_NULL_TOKENS:
        return str(text or "").strip() or "(빈칸)"
    return ""


def check_answer(answer, planned, reopen=()):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다. `reopen` - 다시 열 수 있는 패널(`record`가 정함)."""
    problems = []
    pid = (answer.get("Panel_ID") or "").strip()
    choice = (answer.get("Decision") or "").strip().upper()
    label = (answer.get("Outcome_Label") or "").strip()
    who = (answer.get("Verified_By") or "").strip()
    problems.extend(approval.seen_problems(answer, who, "패널을 직접 보았다는 표시가 없습니다. 표시가 없는 답은 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 보았는지(또는 승인했는지) 적혀 있지 않습니다."))
    if choice not in CHOICES:
        problems.append(("BAD_DECISION", "%r은 이 관문이 받는 답이 아닙니다. 받는 것: %s"
                         % (choice or "(빈칸)", ", ".join(CHOICES))))
        return problems
    if pid not in planned:
        problems.append(("NOT_PLANNED", "%r은 계획서의 패널이 아닙니다. 계획서를 다시 낸 뒤의 답이거나, "
                                        "다른 run의 답입니다." % (pid or "(빈칸)")))
    elif choice == LABEL and planned[pid][1] in CLOSED and pid not in reopen:
        problems.append(("PANEL_CLOSED", "%s는 계획서에서 %s로 닫힌 패널입니다. 다시 열려면 그림의 처분을 "
                                         "바꾸십시오(record_dispositions)." % (pid, planned[pid][1])))
    if choice == LABEL:
        if not label:
            problems.append(("LABEL_WITHOUT_TEXT", "결과의 이름이 비어 있습니다."))
        else:
            marker = placeholder_in(label)
            if marker:
                problems.append(("LABEL_IS_A_PLACEHOLDER", "이름에 \"%s\"가 들어 있습니다. 논문이 그린 것의 "
                                                           "이름이 아니라 추정입니다." % marker))
    elif choice == NON_TARGET and (label or (answer.get("Unit") or "").strip()):
        problems.append(("NON_TARGET_WITH_LABEL", "목표 결과가 아니라면서 이름(%r)이 붙어 있습니다." % label))
    if choice == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 남겨 둡니다."))
    return problems


def record(run, plans, answers, when, out_path=None, via="BUNDLE", replace=False, log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    planned = load_planned(plans)
    out_path = out_path or os.path.join(run, DECISIONS)
    if answers_path and os.path.exists(answers_path) and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s)." % out_path)
    existing = load_recorded(out_path)
    settled = set(r["Panel_ID"] for r in existing)
    # 이 관문이 닫은 패널만 이 관문이 다시 엽니다: --replace, 지금 기록의 NON_TARGET 줄, 계획서가 그 줄 때문에 닫음.
    reopen = set()
    if replace:
        said_not = set(r["Panel_ID"] for r in existing if (r.get("Decision") or "").strip().upper() == NON_TARGET)
        reopen = set(p for p in said_not if p in planned and planned[p][2])
    seen_here, twice = set(), set()
    for answer in answers:
        p = (answer.get("Panel_ID") or "").strip()
        if p in seen_here:
            twice.add(p)
        seen_here.add(p)

    written, refused = [], []
    for answer in answers:
        pid = (answer.get("Panel_ID") or "").strip()
        if pid in twice:
            refused.append((pid, [("ANSWERED_TWICE", "%s에 답이 둘 있습니다. 패널 하나에 답은 하나입니다." % pid)]))
            continue
        problems = check_answer(answer, planned, reopen)
        if problems:
            refused.append((pid or "(빈칸)", problems))
            continue
        if pid in settled and not replace:
            refused.append((pid, [("ALREADY_DECIDED", "이 패널은 이미 적혀 있습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        m = PANEL_ID.match(pid)
        choice = (answer.get("Decision") or "").strip().upper()
        prov = approval.provenance(answer)
        written.append({
            "Panel_ID": pid, "Draft_ID": m.group("draft"), "Panel_Index": m.group("index"),
            "Publication_ID": planned[pid][0], "Decision": choice,
            "Outcome_Label": (answer.get("Outcome_Label") or "").strip() if choice == LABEL else "",
            "Unit": (answer.get("Unit") or "").strip() if choice == LABEL else "",
            "Verified_By": (answer.get("Verified_By") or "").strip(),
            "Seen_By_Person": prov["Seen_By_Person"], "Observed_By": prov["Observed_By"], "Approval_Ref": prov["Approval_Ref"],
            "Recorded_Via": via, "Recorded_At": when, "Note": (answer.get("Note") or "").strip(),
        })
    keep = [r for r in existing if r["Panel_ID"] not in set(w["Panel_ID"] for w in written)]
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in sorted(keep + written, key=lambda x: (x["Draft_ID"], int(x["Panel_Index"] or 0))):
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
    ap.add_argument("--plans", required=True, help="이 답이 대답한 계획서 폴더 (plan_*.json)")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="BUNDLE")
    ap.add_argument("--when", required=True, help="패널을 본(또는 승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.run), os.path.expanduser(a.plans), answers, a.when,
                               out_path=a.out, via=a.via, replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
