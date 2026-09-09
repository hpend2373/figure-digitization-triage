# -*- coding: utf-8 -*-
"""사람이 그림을 보고 내린 처분을 적습니다.

    python3 record_decisions.py --run RUN --plans PLANS \
        --answers RUN/figure_decisions_in.csv --when 2026-09-09

`decision_page.py`가 내는 답 CSV를 받아, 그 답이 **계획서가 실제로 물은
것인지**, **사람이 그림을 보았다고 말했는지**, **그 물음이 받는 답인지**를
보고 나서 적습니다. `record_errorbar.py`와 같은 자리에 서 있습니다.

이 관문이 지키는 것은 처분의 모양이 아니라 **누가 보았는가**입니다. 화면이
`Seen_By_Person`을 채워 보낼 수는 있지만, 채운 것이 사람인지 프로그램인지는
화면 밖에서 알 수 없습니다 - 그래서 여기서 한 번 더, 이 답이 계획서가 그
사람에게 물은 것과 짝이 맞는지 봅니다. 짝이 맞지 않는 답은 어디서 왔든
적히지 않습니다.

`HOLD`는 답이지만 적히지 않습니다. "아직 못 정하겠다"는 그 그림에 대해 사람이
한 말이고, 그것을 처분으로 적으면 정해진 것이 됩니다. 대신 이름을 대고
거절하므로, 목록에서 사라지지 않습니다.
"""
import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import decision_page as DP                                       # noqa: E402

DRAFT = "figure_intake_draft.csv"
DECISIONS = "figure_decisions.csv"

#: 물음마다 받는 답. `decision_page.js`의 `CHOICES`와 같아야 하고,
#: `test_record_decisions.py`가 셋(논리·화면·관문)이 같은지 봅니다.
CHOICES = {
    "UNCOUNTABLE": ("RECROP", "NOT_DATA", "COUNTABLE", "HOLD"),
    "MIXED": ("DATA", "NOT_DATA", "PARTIAL", "HOLD"),
    "CROP_DISPUTE": ("RECROP", "NOT_DATA", "HOLD"),
}

#: 어느 패널인지 적어야만 답이 되는 처분.
NEEDS_PANELS = ("PARTIAL",)

#: 아직 정하지 않았다는 답. 적히지 않습니다.
HELD = "HOLD"

ANSWER_REQUIRED = ("Draft_ID", "Question", "Decision", "Seen_By_Person")

FIELDS = ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page",
          "Question", "Decision", "Which_Panels", "Seen_By_Person",
          "Recorded_Via", "Recorded_At", "Note")

TRUE = ("1", "TRUE", "YES", "Y", "T")


def is_true(v):
    return str(v or "").strip().upper() in TRUE


def load_asked(run, plans):
    """{(Draft_ID, 물음): 계획서 행} - 계획서가 실제로 물은 것."""
    out = {}
    path = os.path.join(plans, DP.FIGURES)
    for row in csv.DictReader(io.open(path, encoding="utf-8-sig")):
        for kind in DP.asked(row):
            out[(row["Draft_ID"], kind)] = row
    return out


def load_recorded(run, out_path):
    """이미 적힌 처분들. 다시 적으려면 --replace가 필요합니다."""
    path = out_path or os.path.join(run, DECISIONS)
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def check_answer(answer, asked):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다.

    문제는 코드와 사람이 읽을 말로 됩니다. 코드만 내면 사람은 무엇을 고쳐야
    하는지 모르고, 말만 내면 시나리오가 무엇을 붙잡는지 모릅니다.
    """
    problems = []
    draft = (answer.get("Draft_ID") or "").strip()
    kind = (answer.get("Question") or "").strip().upper()
    choice = (answer.get("Decision") or "").strip().upper()
    panels = (answer.get("Which_Panels") or "").strip()

    # 사람이 그림을 보았다고 말하지 않은 답은 답이 아닙니다. 이 문이 지키는
    # 것은 처분의 모양이 아니라 "누가 보았는가"이고, 그것은 에이전트가 대신
    # 채울 수 없습니다.
    if not is_true(answer.get("Seen_By_Person")):
        problems.append(("NOT_SEEN_BY_PERSON",
                         "판정 페이지에서 \"이 그림을 직접 봤다\"를 표시하지 "
                         "않았습니다. 표시가 없는 답은 적지 않습니다."))

    if kind not in CHOICES:
        problems.append(("BAD_QUESTION",
                         "%r은 이 관문이 아는 물음이 아닙니다. 아는 것: %s"
                         % (kind or "(빈칸)", ", ".join(sorted(CHOICES)))))
        return problems

    if choice not in CHOICES[kind]:
        problems.append(("BAD_DECISION",
                         "%s 물음에 %r은 받는 답이 아닙니다. 받는 것: %s"
                         % (kind, choice or "(빈칸)", ", ".join(CHOICES[kind]))))
        return problems

    # 계획서가 묻지 않은 것에 답이 왔습니다. 답이 틀렸다는 말이 아니라, 이
    # 답이 어느 물음에 대한 것인지 이 관문이 알 수 없다는 말입니다.
    if (draft, kind) not in asked:
        problems.append(("NOT_ASKED",
                         "계획서는 %s에 대해 %s를 묻지 않았습니다. 계획서를 "
                         "다시 낸 뒤의 답이거나, 다른 run의 답입니다."
                         % (draft or "(빈칸)", kind)))

    if choice in NEEDS_PANELS and not panels:
        problems.append(("PARTIAL_WITHOUT_PANELS",
                         "일부 패널만 데이터라고 하면서 어느 패널인지 적지 "
                         "않았습니다. 어느 패널인지 모르는 \"일부\"는 다음 "
                         "사람에게 아무 말도 하지 않습니다."))
    if choice not in NEEDS_PANELS and panels:
        problems.append(("PANELS_WITHOUT_PARTIAL",
                         "%s에는 패널 이름이 붙지 않습니다. 붙은 이름(%r)이 "
                         "무엇을 뜻하는지 이 관문은 모릅니다." % (choice, panels)))

    if choice == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 "
                                 "남겨 둡니다."))
    return problems


def record(run, plans, answers, when, out_path=None, via="DECISION_PAGE",
           replace=False, log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로).

    `answers_path`는 답이 어느 파일에서 왔는지입니다. 그 파일이 곧 이 관문이
    적는 파일이면 멈춥니다 - 그러면 관문은 자기가 적어 둔 것을 답으로 읽고,
    같은 답을 전부 `ALREADY_DECIDED`로 거절한 뒤, 원본을 자기 모양으로
    덮어씁니다. 실제로 한 번 그렇게 덮어썼습니다.
    """
    missing = [c for c in ANSWER_REQUIRED
               if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 판정 페이지가 내려준 "
                         "파일이 맞습니까?" % ", ".join(missing))
    asked = load_asked(run, plans)
    draft = dict((r["Draft_ID"], r) for r in
                 csv.DictReader(io.open(os.path.join(run, DRAFT),
                                        encoding="utf-8-sig")))
    out_path = out_path or os.path.join(run, DECISIONS)
    if answers_path and os.path.exists(answers_path) \
            and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s). 판정 페이지가 "
                         "내려준 파일은 figure_decision_answers.csv이고, 이 "
                         "관문이 적는 파일은 %s입니다." % (out_path, DECISIONS))
    existing = load_recorded(run, out_path)
    settled = set((r["Draft_ID"], r["Question"]) for r in existing)

    written, refused = [], []
    for answer in answers:
        key = ((answer.get("Draft_ID") or "").strip(),
               (answer.get("Question") or "").strip().upper())
        problems = check_answer(answer, asked)
        if problems:
            refused.append(("%s/%s" % key, problems))
            continue
        if key in settled and not replace:
            refused.append(("%s/%s" % key,
                            [("ALREADY_DECIDED",
                              "이 물음은 이미 판정되어 있습니다. 바꾸려면 "
                              "--replace를 주십시오.")]))
            continue
        d = draft.get(key[0], {})
        plan = asked[key]
        written.append({
            "Draft_ID": key[0],
            "Source_Document_ID": d.get("Source_Document_ID", ""),
            "Figure_Number": plan.get("Figure_Number", ""),
            "Page": plan.get("Page", ""),
            "Question": key[1],
            "Decision": (answer.get("Decision") or "").strip().upper(),
            "Which_Panels": (answer.get("Which_Panels") or "").strip(),
            "Seen_By_Person": "1",
            "Recorded_Via": via,
            "Recorded_At": when,
            "Note": (answer.get("Note") or "").strip(),
        })

    keep = [r for r in existing
            if (r["Draft_ID"], r["Question"]) not in
            set((w["Draft_ID"], w["Question"]) for w in written)]
    with io.open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in sorted(keep + written,
                        key=lambda x: (x["Draft_ID"], x["Question"])):
            w.writerow(dict((c, r.get(c, "")) for c in FIELDS))

    log("적음 %d · 거절 %d · 이미 있던 것 %d"
        % (len(written), len(refused), len(keep)))
    for name, problems in refused:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, refused, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--plans", required=True,
                    help="이 답이 대답한 계획서. 무엇을 물었는지가 거기 있습니다.")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="DECISION_PAGE")
    ap.add_argument("--when", required=True,
                    help="사람이 그림을 본 날짜. 오늘로 채우지 않습니다 - "
                         "언제 보았는지는 이 프로그램이 아는 것이 아닙니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(
        os.path.expanduser(a.run), os.path.expanduser(a.plans), answers,
        a.when, out_path=a.out, via=a.via, replace=a.replace,
        answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
