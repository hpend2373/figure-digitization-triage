# -*- coding: utf-8 -*-
"""목록(inventory)의 두 수를 적습니다 - 문서마다 그림이 몇 개인지, 그림마다 패널이 몇 개인지.

    python3 record_inventory.py --run RUN --plans PLANS \
        --answers inventory_answers.csv --when 2026-10-15

배치층은 값을 읽기 전에 두 수를 요구합니다(`batch_manifests`): 문서의
`Observed_Figure_Count`·`Article_Page_Range`와 그림의 `Observed_Panel_Count`,
그리고 그 둘을 누가 언제 어떻게 세었는지(`*_Count_Method`, `Reviewer_ID`,
`Inspection_Date`). 둘 중 하나라도 확인되지 않은 편은 값을 하나도 읽지 않습니다.
run2 2026-10-14까지 `make_plan`이 이 수를 VISUALLY_VERIFIED로 적는 길은 하나였습니다:
사람이 600 DPI 래스터 위에 그린 패널(`seg/panel_decisions.csv`). 문서의 그림 수는
적을 길이 없었고, 계수 시트의 수는 누가 언제 세었는지가 없어 PENDING으로 남았습니다.
그래서 98편이 모두 목록 문제로 멈춰 있었습니다(run2 결정 R1).

이 관문은 그 수를 적는 두 번째 길입니다. 받는 것은 `record_dispositions`와 같이
**누가 보았는가**가 있는 답뿐입니다(`approval`):

    본 답         Seen_By_Person=1, Verified_By=본 사람             -> HUMAN_VISUAL
    승인된 관찰   Seen_By_Person=0, Observed_By=본 것, Verified_By=승인한 사람,
                  Approval_Ref=승인한 곳                               -> MACHINE_PLUS_HUMAN

계수 방법은 답이 고르지 않습니다 - 누가 보았는지가 정합니다. 사람이 보지 않은 수를
HUMAN_VISUAL이라 적을 수 있으면, 배치층이 두 방법을 가르는 까닭이 없어집니다.

한 줄이 하나의 수입니다.

    Level=DOCUMENT  Target_ID=Source_Document_ID
                    Count = 그 논문(Article_Page_Range 안)에 인쇄된 번호 있는 그림의 수 (0 이상)
                    Article_Page_Range = "첫 쪽-끝 쪽" (PDF 쪽 번호). 사람이 정한 쪽 범위
                    (`document_scope.csv`)가 있으면 그것과 같아야 합니다.
    Level=FIGURE    Target_ID=Draft_ID (계획서의 그림)
                    Count = 축 영역(패널)의 수 (1 이상)
                    Count_Basis = AXIS_REGIONS (축 영역을 센 수) 또는 WHOLE (축 영역이 없는
                    그림 - 사진·도식·눈금 없는 개념 곡선 - 을 통째로 한 패널로; Count=1)

`Inspection_Date`는 본 날이고 적는 날(--when)보다 늦을 수 없습니다. 같은 수의 답이
둘이면 둘 다 적지 않고, 이미 적힌 수는 --replace 없이 바꾸지 않습니다.

`make_plan`은 이 파일(`inventory_records.csv`)을 읽어 문서와 그림의 목록을
VISUALLY_VERIFIED로 적습니다 - 사람이 직접 센 것(인테이크의 문서 상태, 사람이 그린
패널)이 있으면 그것이 먼저입니다.
"""
import argparse
import csv
import datetime
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import approval                                                  # noqa: E402

INVENTORY = "inventory_records.csv"
DRAFT = "figure_intake_draft.csv"
DOCUMENT_STATUS = "intake_document_status.csv"
DOCUMENT_SCOPE = "document_scope.csv"
#: 계획서의 그림 목록 - 이 관문이 패널 수를 붙일 수 있는 그림들.
PLAN_FIGURES = "plan_figures.csv"

DOCUMENT, FIGURE = "DOCUMENT", "FIGURE"
LEVELS = (DOCUMENT, FIGURE)
AXIS_REGIONS, WHOLE = "AXIS_REGIONS", "WHOLE"
BASES = (AXIS_REGIONS, WHOLE)
#: `batch_manifests.SOURCE_PANEL_COUNT_METHODS`의 두 이름.
HUMAN_VISUAL, MACHINE_PLUS_HUMAN = "HUMAN_VISUAL", "MACHINE_PLUS_HUMAN"

ANSWER_REQUIRED = ("Level", "Target_ID", "Count", "Inspection_Date", "Verified_By", "Seen_By_Person")
FIELDS = ("Level", "Target_ID", "Source_Document_ID", "Figure_Number", "Page", "Count", "Count_Basis",
          "Article_Page_Range", "Count_Method", "Inspection_Date", "Verified_By", "Seen_By_Person",
          "Observed_By", "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")
PAGE_RANGE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def _rows(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def method_of(answer):
    """누가 보았는가가 정하는 계수 방법."""
    return HUMAN_VISUAL if approval.is_true(answer.get("Seen_By_Person")) else MACHINE_PLUS_HUMAN


def load_context(run, plans):
    """관문이 답을 대어 볼 것들: 문서, 사람이 정한 쪽 범위, 계획서의 그림, 초안 행."""
    return {
        "documents": dict((r["Source_Document_ID"], r) for r in _rows(os.path.join(run, DOCUMENT_STATUS))),
        "scope": dict((r["Source_Document_ID"], r) for r in _rows(os.path.join(run, DOCUMENT_SCOPE))),
        "planned": dict((r["Draft_ID"], r) for r in _rows(os.path.join(plans, PLAN_FIGURES))),
        "draft": dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, DRAFT))),
    }


def _key(answer):
    return ((answer.get("Level") or "").strip().upper(), (answer.get("Target_ID") or "").strip())


def check_answer(answer, ctx, when):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다."""
    problems = []
    level, target = _key(answer)
    who = (answer.get("Verified_By") or "").strip()
    basis = (answer.get("Count_Basis") or "").strip().upper()
    pages = (answer.get("Article_Page_Range") or "").strip()
    problems.extend(approval.seen_problems(answer, who, "수를 직접 세었다는 표시가 없습니다. 표시가 없는 수는 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 세었는지(또는 승인했는지) 적혀 있지 않습니다."))
    if level not in LEVELS:
        problems.append(("BAD_LEVEL", "%r은 이 관문이 받는 단위가 아닙니다. 받는 것: %s" % (level or "(빈칸)", ", ".join(LEVELS))))
        return problems
    raw = (answer.get("Count") or "").strip()
    count = int(raw) if raw.isdigit() else None
    when_seen = (answer.get("Inspection_Date") or "").strip()
    try:
        seen_on = datetime.date.fromisoformat(when_seen)
    except ValueError:
        problems.append(("BAD_INSPECTION_DATE", "Inspection_Date=%r는 날짜(YYYY-MM-DD)가 아닙니다." % when_seen))
    else:
        if seen_on > datetime.date.fromisoformat(when):
            problems.append(("INSPECTED_AFTER_RECORDED", "본 날(%s)이 적는 날(%s)보다 늦습니다. 아직 보지 않은 것은 "
                                                         "센 것이 아닙니다." % (when_seen, when)))
    if level == DOCUMENT:
        if target not in ctx["documents"]:
            problems.append(("NOT_A_DOCUMENT", "%r은 이 run의 문서가 아닙니다." % (target or "(빈칸)")))
        if count is None:
            problems.append(("BAD_COUNT", "그림 수 %r은 0 이상의 정수가 아닙니다." % raw))
        if basis:
            problems.append(("BASIS_ON_DOCUMENT", "Count_Basis(%s)는 그림의 패널 수에 붙는 것입니다." % basis))
        m = PAGE_RANGE.match(pages)
        if not m:
            problems.append(("BAD_PAGE_RANGE", "Article_Page_Range=%r는 '첫 쪽-끝 쪽'이 아닙니다." % pages))
        else:
            first, last = int(m.group(1)), int(m.group(2))
            total = (ctx["documents"].get(target, {}).get("Page_Count") or "").strip()
            if first < 1 or last < first or (total.isdigit() and last > int(total)):
                problems.append(("BAD_PAGE_RANGE", "%d-%d은 이 PDF(%s쪽) 안의 범위가 아닙니다." % (first, last, total or "?")))
            scope = ctx["scope"].get(target) or {}
            want = ((scope.get("Page_From") or "").strip(), (scope.get("Page_To") or "").strip())
            if all(want) and (str(first), str(last)) != want:
                # 사람이 정한 범위가 있는 문서. 그 범위 밖의 그림을 센 수는 다른 문서의 수입니다.
                problems.append(("RANGE_DISAGREES_WITH_SCOPE", "사람이 정한 쪽 범위는 %s-%s인데 이 답은 %d-%d입니다."
                                 % (want[0], want[1], first, last)))
    else:
        if target not in ctx["planned"]:
            problems.append(("NOT_PLANNED", "%r은 계획서의 그림이 아닙니다. 계획서를 다시 낸 뒤의 답이거나, "
                                            "다른 run의 답입니다." % (target or "(빈칸)")))
        if count is None or count < 1:
            problems.append(("BAD_COUNT", "패널 수 %r은 1 이상의 정수가 아닙니다. 축 영역이 없는 그림은 "
                                          "Count_Basis=WHOLE, Count=1입니다." % raw))
        if basis not in BASES:
            problems.append(("BAD_COUNT_BASIS", "Count_Basis=%r. 받는 것: %s" % (basis or "(빈칸)", ", ".join(BASES))))
        elif basis == WHOLE and count is not None and count != 1:
            problems.append(("WHOLE_IS_ONE", "WHOLE은 그림 전체를 한 패널로 적는 것인데 Count=%d입니다." % count))
        if pages:
            problems.append(("RANGE_ON_FIGURE", "Article_Page_Range는 문서에 붙는 것입니다 (%r)." % pages))
    return problems


def record(run, plans, answers, when, out_path=None, via="INVENTORY_SURVEY", replace=False, log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    ctx = load_context(run, plans)
    out_path = out_path or os.path.join(run, INVENTORY)
    if answers_path and os.path.exists(answers_path) and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s)." % out_path)
    existing = _rows(out_path)
    settled = set((r["Level"], r["Target_ID"]) for r in existing)
    seen_here, twice = set(), set()
    for answer in answers:
        k = _key(answer)
        if k in seen_here:
            twice.add(k)
        seen_here.add(k)

    written, refused = [], []
    for answer in answers:
        k = _key(answer)
        name = "%s %s" % (k[0] or "?", k[1] or "(빈칸)")
        if k in twice:
            refused.append((name, [("ANSWERED_TWICE", "%s에 수가 둘 있습니다. 하나에 수는 하나입니다." % name)]))
            continue
        problems = check_answer(answer, ctx, when)
        if problems:
            refused.append((name, problems))
            continue
        if k in settled and not replace:
            refused.append((name, [("ALREADY_RECORDED", "이 수는 이미 적혀 있습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        level, target = k
        prov = approval.provenance(answer)
        row = {"Level": level, "Target_ID": target, "Count": str(int(answer["Count"].strip())),
               "Count_Method": method_of(answer), "Inspection_Date": answer["Inspection_Date"].strip(),
               "Verified_By": answer["Verified_By"].strip(), "Seen_By_Person": prov["Seen_By_Person"],
               "Observed_By": prov["Observed_By"], "Approval_Ref": prov["Approval_Ref"], "Recorded_Via": via,
               "Recorded_At": when, "Note": (answer.get("Note") or "").strip()}
        if level == DOCUMENT:
            m = PAGE_RANGE.match(answer["Article_Page_Range"])
            row.update({"Source_Document_ID": target, "Article_Page_Range": "%d-%d" % (int(m.group(1)), int(m.group(2)))})
        else:
            plan = ctx["planned"][target]
            row.update({"Source_Document_ID": ctx["draft"].get(target, {}).get("Source_Document_ID", ""),
                        "Figure_Number": plan.get("Figure_Number", ""), "Page": plan.get("Page", ""),
                        "Count_Basis": answer["Count_Basis"].strip().upper()})
        written.append(row)
    done = set((w["Level"], w["Target_ID"]) for w in written)
    keep = [r for r in existing if (r["Level"], r["Target_ID"]) not in done]
    tmp = out_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in sorted(keep + written, key=lambda x: (x["Level"], x["Target_ID"])):
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
    ap.add_argument("--via", default="INVENTORY_SURVEY")
    ap.add_argument("--when", required=True, help="적는(승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.run), os.path.expanduser(a.plans), answers, a.when,
                               out_path=a.out, via=a.via, replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
