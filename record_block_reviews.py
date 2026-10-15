# -*- coding: utf-8 -*-
"""막힌 초안 행을 다시 본 답을 적습니다 - 막음을 풀거나, 그대로 둡니다.

    python3 record_block_reviews.py --run RUN --plans PLANS \
        --answers block_review_answers.csv --when 2026-10-15

계수 시트는 사람에게 다시 묻지 않으려고, 그리고 크롭·캡션·번호가 미덥지 않은 행을
세지 않으려고 초안 행을 막습니다(`block_reasons.csv`, Count_Blocked=1). 막힌 행은
계획서의 그림이 되지 않습니다(`make_plan.live_rows`). 그 막음이 틀렸을 때 - 사람이
"이 차단이 틀렸다"고 답한 행(BLOCK_DISPUTED), 목록 조사에서 실제 그림으로 확인된
행 - 그 그림을 계획서로 돌려보낼 길이 없었습니다. `block_reasons.csv`는 시트를
지을 때마다 다시 쓰이는 파일이라 손으로 고친 것은 다음 빌드에서 사라지고, 계수
시트의 답은 "막힌 행에 대고 한 답"이라 행을 열지 않습니다. run2 2026-10-15 목록
조사에서 그런 행이 둘 나왔습니다(IWASAKI Fig. 6, MICROGRAVITY Fig. 2).

이 파일(`block_reviews.csv`)은 막음 위에 얹는 답입니다. 막음은 그대로 남고,
`make_plan`은 UNBLOCK으로 답한 행을 막힌 행으로 치지 않습니다.

받는 답:
    UNBLOCK   이 행은 실제 그림이다 - 계획서의 그림으로 돌려보낸다
    KEEP      막음이 맞다 (적어 두어 다시 묻지 않게)
    HOLD      아직 정하지 않았다 (적지 않음)

받는 것은 다른 관문과 같이 **누가 보았는가**가 있는 답뿐입니다(`approval`). 막히지
않은 행(이미 계획서에 있는 행 포함), 중복 행(Duplicate_Of - 한 그림을 두 번 세게
됩니다), 같은 문서에서 이미 계획서에 있는 그림과 번호가 같은 행, 초안에 없는 행,
한 행에 둘, --replace 없는 덮어쓰기는 적지 않습니다.
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
import batch_manifests as BM                                     # noqa: E402

BLOCK_REVIEWS = "block_reviews.csv"
DRAFT = "figure_intake_draft.csv"
BLOCKS = "block_reasons.csv"
COUNTS = "observed_panel_counts.csv"
PLAN_FIGURES = "plan_figures.csv"
#: `make_plan.ANSWERED_ON_AN_OPEN_ROW` - 막힌 행이어도 이 답이 붙어 있으면 계획서의 그림입니다.
#: 같은 이름을 두 곳에 두는 까닭은 관문이 make_plan 전체를 끌어오지 않게 하려는 것이고,
#: 둘이 같다는 것은 시나리오가 확인합니다.
ANSWERED_ON_AN_OPEN_ROW = ("ENTERED", "SEEN_UNCOUNTABLE", "CROP_DISPUTED")

UNBLOCK, KEEP, HELD = "UNBLOCK", "KEEP", "HOLD"
CHOICES = (UNBLOCK, KEEP, HELD)
ANSWER_REQUIRED = ("Draft_ID", "Decision", "Verified_By", "Seen_By_Person")
FIELDS = ("Draft_ID", "Source_Document_ID", "Figure_Number", "Page", "Decision", "Block_Reason", "Verified_By",
          "Seen_By_Person", "Observed_By", "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")


def _rows(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def _norm(number):
    """배치층이 같은 그림으로 치는 번호 (`FIG2`, `Fig. 2`, `Figure 2`는 한 그림)."""
    return BM.normalize_figure_number(number or "")


def load_context(run, plans):
    draft = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, DRAFT)))
    planned = dict((r["Draft_ID"], r) for r in _rows(os.path.join(plans, PLAN_FIGURES)))
    taken = set()
    for did in planned:
        row = draft.get(did) or {}
        taken.add((row.get("Source_Document_ID", ""), _norm(planned[did].get("Figure_Number") or row.get("Figure_Number"))))
    return {"draft": draft, "blocks": dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, BLOCKS))),
            "said": dict((r["Draft_ID"], (r.get("Entry_Status") or "").strip()) for r in _rows(os.path.join(run, COUNTS))),
            "planned": planned, "taken": taken}


def check_answer(answer, ctx):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다."""
    problems = []
    did = (answer.get("Draft_ID") or "").strip()
    choice = (answer.get("Decision") or "").strip().upper()
    who = (answer.get("Verified_By") or "").strip()
    problems.extend(approval.seen_problems(answer, who, "행을 직접 보았다는 표시가 없습니다. 표시가 없는 답은 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 보았는지(또는 승인했는지) 적혀 있지 않습니다."))
    if choice not in CHOICES:
        problems.append(("BAD_DECISION", "%r은 이 관문이 받는 답이 아닙니다. 받는 것: %s" % (choice or "(빈칸)", ", ".join(CHOICES))))
        return problems
    if did not in ctx["draft"]:
        problems.append(("NOT_A_DRAFT", "%r은 이 run의 초안 행이 아닙니다." % (did or "(빈칸)")))
        return problems
    block = ctx["blocks"].get(did) or {}
    if (block.get("Duplicate_Of") or "").strip():
        problems.append(("DUPLICATE_ROW", "%s는 %s의 중복 행입니다. 막음이 아니라 중복이고, 풀면 한 그림을 두 번 셉니다."
                         % (did, block["Duplicate_Of"].strip())))
    elif block.get("Count_Blocked") != "1" or ctx["said"].get(did) in ANSWERED_ON_AN_OPEN_ROW or did in ctx["planned"]:
        problems.append(("NOT_BLOCKED", "%s는 막힌 행이 아닙니다 - 이미 계획서의 그림입니다." % did))
    elif choice == UNBLOCK:
        row = ctx["draft"][did]
        if (row.get("Source_Document_ID", ""), _norm(row.get("Figure_Number"))) in ctx["taken"]:
            problems.append(("FIGURE_NUMBER_TAKEN", "%s의 %s는 이미 계획서에 있습니다. 풀면 같은 그림이 둘이 됩니다."
                             % (row.get("Source_Document_ID"), row.get("Figure_Number"))))
        if not _norm(row.get("Figure_Number")):
            problems.append(("NO_FIGURE_NUMBER", "%s에는 그림 번호가 없습니다. 번호 없는 그림은 계획서에 들어갈 수 없습니다." % did))
    if choice == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 남겨 둡니다."))
    return problems


def record(run, plans, answers, when, out_path=None, via="DECISION_PAGE", replace=False, log=print, answers_path=None):
    """(적힌 행, 거절된 (이름, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    ctx = load_context(run, plans)
    out_path = out_path or os.path.join(run, BLOCK_REVIEWS)
    if answers_path and os.path.exists(answers_path) and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s)." % out_path)
    existing = _rows(out_path)
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
            refused.append((did, [("ANSWERED_TWICE", "%s에 답이 둘 있습니다." % did)]))
            continue
        problems = check_answer(answer, ctx)
        if problems:
            refused.append((did or "(빈칸)", problems))
            continue
        if did in settled and not replace:
            refused.append((did, [("ALREADY_REVIEWED", "이 행의 막음은 이미 다시 보았습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        row = ctx["draft"][did]
        prov = approval.provenance(answer)
        written.append({
            "Draft_ID": did, "Source_Document_ID": row.get("Source_Document_ID", ""), "Figure_Number": row.get("Figure_Number", ""),
            "Page": row.get("Page", ""), "Decision": (answer.get("Decision") or "").strip().upper(),
            "Block_Reason": (ctx["blocks"].get(did, {}).get("Reason") or "").strip(),
            "Verified_By": (answer.get("Verified_By") or "").strip(), "Seen_By_Person": prov["Seen_By_Person"],
            "Observed_By": prov["Observed_By"], "Approval_Ref": prov["Approval_Ref"], "Recorded_Via": via,
            "Recorded_At": when, "Note": (answer.get("Note") or "").strip()})
    done = set(w["Draft_ID"] for w in written)
    keep = [r for r in existing if r["Draft_ID"] not in done]
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
    ap.add_argument("--when", required=True, help="행을 본(또는 승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.run), os.path.expanduser(a.plans), answers, a.when,
                               out_path=a.out, via=a.via, replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
