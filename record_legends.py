# -*- coding: utf-8 -*-
"""한 그림에 범례가 여럿일 때, 어느 패널이 어느 범례를 쓰는지 적습니다.

    python3 record_legends.py --run RUN --plans PLANS \
        --answers legend_answers.csv --when 2026-10-16

흑백 막대의 계열은 칠로 알아봅니다. 칠이 무엇을 뜻하는지는 범례가 정하고,
계획서는 한 범례를 쓰는 패널들을 `Identity_Domain_ID` 하나로 묶습니다 - 그
안에서 같은 칠은 같은 계열이어야 합니다(`batch_manifests`의
IDENTITY_DOMAIN_FILL_CONFLICT). 기본은 그림 하나가 범례 하나입니다. 그런데
패널마다 범례를 따로 인쇄한 그림이 있습니다: Iwasaki 2000 그림 4는 같은 격자
빗금이 A에서는 '침상 전', B에서는 '이뇨제 전'입니다. 그 그림은 기본대로 묶으면
충돌로 멈추고, 칠을 바꿔 적으면 틀린 계열에 값이 붙습니다. 이 관문이 범례의
묶음을 `legend_decisions.csv`에 적고, `make_plan`이 묶음마다 다른
`Identity_Domain_ID`(`F_<그림>__L<번호>`)를 줍니다.

답(그림 하나에 한 줄):
    Draft_ID        그림
    Legend_Groups   범례마다 패널 번호, 범례 사이는 |   예: p1|p2, p1,p3,p5|p2,p4,p6
    Decision        LEGENDS (적음) 또는 HOLD (적지 않음)

받지 않는 것: 계획서에 없는 그림, 그 그림의 패널이 아닌 번호, 두 범례에 든 패널,
범례가 하나뿐인 묶음(그것은 기본값이고 적을 것이 없습니다), 그리고 누가 보았는지
없는 답(`approval`).
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

DECISIONS = "legend_decisions.csv"
CHOICES = ("LEGENDS", "HOLD")
HELD = "HOLD"
ANSWER_REQUIRED = ("Draft_ID", "Legend_Groups", "Decision", "Verified_By", "Seen_By_Person")
FIELDS = ("Draft_ID", "Publication_ID", "Legend_Groups", "Verified_By", "Seen_By_Person", "Observed_By",
          "Approval_Ref", "Recorded_Via", "Recorded_At", "Note")
TOKEN = re.compile(r"^p(\d+)$")


def load_planned(plans):
    """{Draft_ID: (Publication_ID, {패널 번호})} - 계획서들의 그림과 그 패널."""
    out = {}
    for path in sorted(glob.glob(os.path.join(plans, "plan_*.json"))):
        plan = json.load(io.open(path, encoding="utf-8"))
        for fig in plan.get("figures") or []:
            did = fig.get("source_figure_id") or ""
            idx = set()
            for p in fig.get("panels") or []:
                m = re.match(r"^(.+)_P(\d+)$", p.get("panel_id") or "")
                if m and m.group(1) == did:
                    idx.add(int(m.group(2)))
            out[did] = (plan.get("publication_id", ""), idx)
    return out


def parse_groups(text):
    """([[번호, ...], ...], 문제) - "p1,p3|p2"를 읽습니다."""
    groups = []
    for g in str(text or "").replace(" ", "").split("|"):
        idx = []
        for t in g.split(","):
            m = TOKEN.match(t.lower())
            if not m:
                return None, "%r은 패널 번호(p1, p2 …)가 아닙니다" % t
            idx.append(int(m.group(1)))
        groups.append(idx)
    return groups, ""


def canonical(groups):
    return "|".join(",".join("p%d" % i for i in sorted(g)) for g in sorted(groups, key=min))


def check_answer(answer, planned):
    """(문제 목록). 빈 목록이면 이 답은 적힐 수 있습니다."""
    problems = []
    did = (answer.get("Draft_ID") or "").strip()
    choice = (answer.get("Decision") or "").strip().upper()
    who = (answer.get("Verified_By") or "").strip()
    problems.extend(approval.seen_problems(answer, who, "그림의 범례를 직접 보았다는 표시가 없습니다. 표시가 없는 답은 적지 않습니다."))
    if not who:
        problems.append(("UNATTRIBUTED", "누가 보았는지(또는 승인했는지) 적혀 있지 않습니다."))
    if choice not in CHOICES:
        problems.append(("BAD_DECISION", "%r은 이 관문이 받는 답이 아닙니다. 받는 것: %s" % (choice or "(빈칸)", ", ".join(CHOICES))))
        return problems
    if choice == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않습니다."))
        return problems
    if did not in planned:
        problems.append(("NOT_PLANNED", "%r은 계획서의 그림이 아닙니다." % (did or "(빈칸)")))
        return problems
    groups, why = parse_groups(answer.get("Legend_Groups"))
    if groups is None:
        problems.append(("BAD_LEGEND_GROUPS", why))
        return problems
    flat = [i for g in groups for i in g]
    if len(groups) < 2:
        problems.append(("ONE_LEGEND", "범례가 하나뿐입니다. 그것은 기본값이라 적을 것이 없습니다."))
    twice = sorted(set(i for i in flat if flat.count(i) > 1))
    if twice:
        problems.append(("PANEL_IN_TWO_LEGENDS", "%s가 두 범례에 들어 있습니다. 패널 하나는 범례 하나를 씁니다."
                         % ", ".join("p%d" % i for i in twice)))
    unknown = sorted(set(flat) - planned[did][1])
    if unknown:
        problems.append(("NOT_A_PANEL", "%s는 계획서에서 %s의 패널이 아닙니다." % (", ".join("p%d" % i for i in unknown), did)))
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
    existing = list(csv.DictReader(io.open(out_path, encoding="utf-8-sig"))) if os.path.exists(out_path) else []
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
        problems = check_answer(answer, planned)
        if problems:
            refused.append((did or "(빈칸)", problems))
            continue
        if did in settled and not replace:
            refused.append((did, [("ALREADY_DECIDED", "이 그림의 범례는 이미 적혀 있습니다. 바꾸려면 --replace를 주십시오.")]))
            continue
        prov = approval.provenance(answer)
        written.append({
            "Draft_ID": did, "Publication_ID": planned[did][0],
            "Legend_Groups": canonical(parse_groups(answer.get("Legend_Groups"))[0]),
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
    ap.add_argument("--plans", required=True, help="이 답이 대답한 계획서 폴더 (plan_*.json)")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out")
    ap.add_argument("--via", default="BUNDLE")
    ap.add_argument("--when", required=True, help="범례를 본(또는 승인한) 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    answers = list(csv.DictReader(io.open(a.answers, encoding="utf-8-sig")))
    _w, refused, path = record(os.path.expanduser(a.run), os.path.expanduser(a.plans), answers, a.when,
                               out_path=a.out, via=a.via, replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
