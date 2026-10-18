# -*- coding: utf-8 -*-
"""AI가 확인할 수 있는 것은 AI가: 제안을 보지 않은 두 번째 검사와 맞춰 보고, 일치한 항목만 사람 없이 적습니다.

    python3 cross_check.py brief --spec SPEC.json --out BRIEF.json [--rules RULES.md]
    # 제안을 보지 않은 검사(제안을 낸 것과 다른 에이전트)가 BRIEF의 물음마다 답해 VERDICTS.json을 씀
    python3 cross_check.py split --spec SPEC.json --items ITEMS.json --verdicts VERDICTS.json \
        --approver minyeop --approval-ref "minyeop 채팅 2026-10-18 '이 정도 검사는 ai로 자동화'" \
        --when 2026-10-18 --answers-file remaining_answers_2026-10-18.csv --out OUT/
    python3 bundle_page.py --spec OUT/person_spec.json ...     # 사람에게 남은 항목만의 페이지
    python3 cross_check.py merge --auto OUT/auto_answers.csv --person PERSON_ANSWERS.csv \
        --record OUT/cross_check.json --out ANSWERS.csv           # -> bundle_route.py --items ITEMS.json (원래 것)

run2(2026-10-18)에서 사람이 남은 일 묶음 54항목을 다 보고 53항목을 제안대로 골랐고, "이 정도 검사는 ai로
자동화하는 게 좋을 거 같아"라고 했습니다. 이 모듈은 그 검사를 둘로 나눕니다.

    brief   결정 묶음 SPEC에서 '제안을 보지 않은' 물음지를 만듭니다: 물음·대상·선택지(효과 없이)·그림만.
            제안, 그 까닭(why), 제안을 낸 것이 찾은 사실(facts), 지금 상태 설명(now), 낸 것(observed_by)은
            빠집니다 - 두 번째 검사가 첫 번째의 답을 따라가면 일치는 아무것도 말하지 않습니다.
    split   두 번째 검사의 답(VERDICTS)을 제안과 맞춰 봅니다. 일치하고, 근거가 있고, 확신이 HIGH이며, 사람만
            정하는 항목이 아니면 → auto_answers.csv (결정 묶음 페이지가 내는 것과 같은 답 줄; `bundle_route.py`가
            그대로 받음). 나머지 → person_spec.json (사람에게 남은 항목만, 두 번째 검사의 답과 근거를 facts에
            붙여서) - `bundle_page.py`로 페이지를 지음. 항목마다 어디로 갔고 왜인지는 cross_check.json.

자동으로 적힌 줄은 **승인된 관찰**입니다(`approval`): Seen_By_Person=0, Observed_By=제안을 낸 것(항목의 그대로),
Verified_By=상시 승인을 한 사람, Approval_Ref=그 상시 승인이 어디 있는지와 일치한 검사. '직접 보았다'는 여기서도
채우지 않습니다 - 사람은 이 항목을 보지 않았고, 기록이 그렇게 말해야 합니다.

사람에게 가는 것 (cross_check.json의 code):
    PERSON_ONLY     새 길·코드 변경(대상이 `fdt:`로 시작), `person_only`로 표시된 항목, 제안이 EDIT인 항목
    NO_VERDICT / VERIFIER_HELD / UNKNOWN_CHOICE   두 번째 검사가 답하지 않았거나 보류했거나 없는 답을 씀
    DISAGREE        두 번째 검사의 답이 제안과 다름
    LOW_CONFIDENCE  확신이 HIGH가 아님
    NO_EVIDENCE     근거가 없음
    TEXT_DIFFERS    이름을 쓰는 답(LABEL)에서 두 번째 검사의 이름·단위가 제안과 (대소문자·공백을 빼고) 다름
    SHARED_CARD     사람에게 가는 항목과 같은 카드(identity·geometry 행)에 닿음 - 한 카드는 한 쪽에서만 적힙니다

멈추는 것: 두 번째 검사가 누구인지 없음, 상시 승인을 한 사람·자리가 없음, 한 항목에 두 답, 물음지에 없는
항목의 답, 두 번째 검사가 제안을 낸 것과 같은 이름, 제안을 낸 것이 승인한 사람과 같은 이름.

두 번째 검사의 독립은 물음지가 지킵니다(제안·까닭·사실·지금·낸 것이 실리지 않음 - 시나리오가 대 봄).
그 검사가 물음지 밖에서 무엇을 읽는지는 검사를 시키는 말이 정합니다: 그림, 원문, 런의 기록(지금 적힌
카드와 계획서)만, 결정 묶음의 SPEC·항목 파일·제안 메모는 열지 않음. 같은 모델의 두 인스턴스라면 서로
독립인 것은 본 것이지 모델이 아닙니다 - 같은 버릇의 실수는 둘 다 할 수 있고, 기록에는 둘의 이름이 남습니다.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HOLD, EDIT = "HOLD", "EDIT"
#: 물음지에 실리지 않는 칸 - 제안과 그 까닭, 제안을 낸 것이 본 것.
BLINDED = ("proposal", "why", "facts", "now", "observed_by")
#: 자동으로 적을 수 있는 확신.
CONFIDENT = "HIGH"
#: auto_answers.csv의 열 - `bundle_page.js`의 CSV_COLUMNS와 같아야 합니다(시나리오가 대 봅니다).
CSV_COLUMNS = ("Item", "Section", "Target_ID", "Proposal", "Decision", "Text", "Unit", "Seen_By_Person", "Verified_By",
               "Observed_By", "Approval_Ref", "Decided_On", "Item_SHA256", "Image_SHA256", "Note")


def sha(path, n=64):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:n]


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def spec_items(spec):
    for sec in spec.get("sections") or []:
        for it in sec.get("items") or []:
            yield sec, it


def option_uses_text(item, value):
    for o in item.get("options") or []:
        if str(o[0]) != value:
            continue
        eff = o[2] if len(o) > 2 else None
        effs = eff if isinstance(eff, list) else [eff]
        return any(isinstance(e, dict) and e.get("uses_text") for e in effs)
    return False


def brief(spec, rules=""):
    """제안을 보지 않은 물음지. `rules`는 리뷰의 규칙(무엇이 목표이고 언제 닫는지) - 제안이 아니라 규약입니다."""
    out = []
    for sec, it in spec_items(spec):
        b = {"id": it["id"], "section": sec.get("title", sec.get("id", "")), "target": it.get("target", ""),
             "question": it.get("question", ""),
             "options": [[str(o[0]), o[1], option_uses_text(it, str(o[0]))] for o in it.get("options") or []],
             "images": [{"path": im.get("path", ""), "caption": im.get("caption", "")} for im in it.get("images") or []]}
        if it.get("text"):
            b["names"] = "이름을 쓰는 답을 고르면 결과 이름과 단위를 직접 쓰십시오 (text, unit)."
        out.append(b)
    return {"schema": "figure-digitization-triage/cross-check-brief/1", "title": spec.get("title", ""),
            "instructions": "각 물음에 그림과 원문을 직접 보고 답하십시오. choice = 선택지의 값, confidence = HIGH 또는 LOW, "
                            "evidence = 근거(원문 인용과 쪽, 그림에서 잰 것) 목록. 확실하지 않으면 LOW 또는 HOLD.",
            "rules": rules, "items": out}


def card_keys(item):
    """이 항목의 선택지가 닿는 카드 (관문, 카드) - 어느 선택지든."""
    keys = set()
    for o in item.get("options") or []:
        eff = o[2] if len(o) > 2 else None
        for e in (eff if isinstance(eff, list) else [eff]):
            if isinstance(e, dict) and e.get("gate") in ("identity", "geometry") and e.get("proposal_id"):
                keys.add((e["gate"], e["proposal_id"]))
    return keys


def person_reason(item, v, verifier, observed):
    """(사람에게 보낼 까닭 코드, 말) 또는 (None, None)."""
    if str(item.get("target", "")).startswith("fdt:") or item.get("person_only"):
        return "PERSON_ONLY", "새 길·코드 변경이나 사람만 정하는 항목"
    if str(item.get("proposal") or "") == EDIT:
        return "PERSON_ONLY", "고친 이름은 사람이 쓴 글이라 본 답이어야 함"
    if v is None:
        return "NO_VERDICT", "두 번째 검사의 답이 없음"
    choice = str(v.get("choice") or "").strip().upper()
    values = [str(o[0]) for o in item.get("options") or []]
    if choice == HOLD:
        return "VERIFIER_HELD", "두 번째 검사가 보류"
    if choice not in values:
        return "UNKNOWN_CHOICE", "두 번째 검사의 답 %r는 이 항목의 선택지가 아님" % choice
    if choice != str(item.get("proposal") or ""):
        return "DISAGREE", "두 번째 검사는 %s, 제안은 %s" % (choice, item.get("proposal"))
    if str(v.get("confidence") or "").strip().upper() != CONFIDENT:
        return "LOW_CONFIDENCE", "두 번째 검사의 확신이 %s" % (v.get("confidence") or "(없음)")
    if not [e for e in (v.get("evidence") or []) if str(e).strip()]:
        return "NO_EVIDENCE", "두 번째 검사가 근거를 적지 않음"
    if option_uses_text(item, choice):
        t = item.get("text") or {}
        if norm(v.get("text")) != norm(t.get("value")) or norm(v.get("unit")) != norm(t.get("unit")):
            return "TEXT_DIFFERS", "이름이 다름: 제안 %r [%s], 두 번째 검사 %r [%s]" % (
                t.get("value"), t.get("unit"), v.get("text"), v.get("unit"))
    return None, None


def split(spec, items_doc, verdicts_doc, approver, approval_ref, when, answers_file, verdicts_sha=""):
    """(자동 답 줄, 사람에게 남은 SPEC, 기록). 맞지 않는 입력은 SystemExit."""
    verifier = str(verdicts_doc.get("verifier") or "").strip()
    if not verifier:
        raise SystemExit("VERDICTS에 두 번째 검사가 누구인지(verifier)가 없습니다.")
    if not approver.strip() or not approval_ref.strip():
        raise SystemExit("상시 승인을 한 사람(--approver)과 그 승인이 있는 자리(--approval-ref)가 있어야 합니다.")
    items = dict((i["id"], i) for i in items_doc["items"])
    verdicts = {}
    for v in verdicts_doc.get("verdicts") or []:
        if v.get("id") in verdicts:
            raise SystemExit("두 번째 검사가 %s에 두 번 답했습니다." % v.get("id"))
        verdicts[v.get("id")] = v
    unknown = sorted(k for k in verdicts if k not in items)
    if unknown:
        raise SystemExit("물음지에 없는 항목의 답: %s" % ", ".join(map(str, unknown)))
    rows, log, keep, cand = [], [], set(), []
    for sec, it in spec_items(spec):
        item = items.get(it["id"])
        if item is None:
            raise SystemExit("항목 파일에 %s가 없습니다 - 같은 빌드의 SPEC과 항목 파일인지 확인하세요." % it["id"])
        observed = str(item.get("observed_by") or "").strip()
        if verifier.casefold() == observed.casefold():
            raise SystemExit("두 번째 검사(%s)가 제안을 낸 것과 같습니다 - 같은 것이 두 번 본 것은 교차 검증이 아닙니다." % verifier)
        if observed and observed.casefold() == approver.strip().casefold():
            raise SystemExit("제안을 낸 것과 상시 승인을 한 사람이 같습니다 (%s)." % observed)
        v = verdicts.get(it["id"])
        code, why = person_reason(it, v, verifier, observed)
        if code:
            keep.add(it["id"])
            log.append({"id": it["id"], "to": "PERSON", "code": code, "why": why, "verifier": v})
            continue
        cand.append((sec, it, item, v))
    # 한 카드에 닿는 항목은 한쪽으로: 사람에게 가는 항목과 카드를 나누는 항목도 사람에게. 두 쪽이 따로 적으면
    # 나중에 적는 쪽이 먼저 적힌 카드 행 위에 다시 지어야 하는데, 같은 기록에서 지은 두 행은 서로를 지웁니다.
    held_cards = set()
    for sec, it in spec_items(spec):
        if it["id"] in keep:
            held_cards |= card_keys(it)
    moved = True
    while moved:
        moved = False
        for sec, it, item, v in list(cand):
            shared = card_keys(it) & held_cards
            if shared:
                cand.remove((sec, it, item, v))
                keep.add(it["id"])
                held_cards |= card_keys(it)
                log.append({"id": it["id"], "to": "PERSON", "code": "SHARED_CARD",
                            "why": "사람에게 가는 항목과 같은 카드(%s)에 닿음" % ", ".join("%s %s" % k for k in sorted(shared)),
                            "verifier": v})
                moved = True
    for sec, it, item, v in cand:
        observed = str(item.get("observed_by") or "").strip()
        choice = str(v["choice"]).strip().upper()
        text = unit = ""
        if option_uses_text(it, choice):
            text, unit = (it.get("text") or {}).get("value", ""), (it.get("text") or {}).get("unit", "")
        ev = "; ".join(str(e).strip() for e in v.get("evidence") if str(e).strip())
        rows.append({"Item": it["id"], "Section": item.get("sec", ""), "Target_ID": item.get("target", ""),
                     "Proposal": str(item.get("proposal") or ""), "Decision": choice, "Text": text, "Unit": unit,
                     "Seen_By_Person": "0", "Verified_By": approver.strip(), "Observed_By": observed,
                     "Approval_Ref": "%s: %s 상시 승인(%s) · AI 교차 검증 일치(%s%s)" % (
                         answers_file, approver.strip(), approval_ref.strip(), verifier,
                         (", 답 지문 %s" % verdicts_sha[:12]) if verdicts_sha else ""),
                     "Decided_On": when, "Item_SHA256": item.get("sha", ""), "Image_SHA256": item.get("img_sha", ""),
                     "Note": ("AI 교차 검증: " + ev)[:600]})
        log.append({"id": it["id"], "to": "AUTO", "code": "AGREE", "why": ev[:300], "verifier": v})
    order = dict((it["id"], n) for n, (_s, it) in enumerate(spec_items(spec)))
    log.sort(key=lambda r: order[r["id"]])
    person = json.loads(json.dumps(spec))
    secs = []
    for sec in person.get("sections") or []:
        its = []
        for it in sec.get("items") or []:
            if it["id"] not in keep:
                continue
            rec = [r for r in log if r["id"] == it["id"]][0]
            v = rec["verifier"] or {}
            add = "[AI 교차 검증 → 사람: %s — %s]" % (rec["code"], rec["why"])
            if v:
                add += " 두 번째 검사: %s (%s) %s" % (v.get("choice", ""), v.get("confidence", ""),
                                                  "; ".join(str(e) for e in v.get("evidence") or [])[:400])
            it["facts"] = (add + (" | " + it["facts"] if it.get("facts") else "")).strip()
            its.append(it)
        if its:
            sec["items"] = its
            secs.append(sec)
    person["sections"] = secs
    person["notes"] = ["AI 교차 검증(%s): %d항목은 제안과 일치해 사람 없이 적었고(%s 상시 승인), 남은 %d항목만 이 페이지에 있습니다."
                       % (verifier, len(rows), approver.strip(), len(keep))] + list(person.get("notes") or [])
    record = {"verifier": verifier, "verdicts_sha256": verdicts_sha, "approver": approver.strip(),
              "approval_ref": approval_ref.strip(), "when": when, "auto": len(rows), "person": len(keep),
              "items": [dict(r, verifier=None) for r in log]}
    return rows, person, record


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        missing = [c for c in CSV_COLUMNS if c not in (r.fieldnames or [])]
        if missing:
            raise SystemExit("%s는 결정 묶음의 답 파일이 아닙니다 (없는 열: %s)" % (path, ", ".join(missing)))
        return list(r)


def merge(auto_rows, person_rows, record):
    """자동 답과 사람 페이지의 답을 한 답 파일로 - 원래 항목 파일로 `bundle_route.py`에 한 번에.

    사람 페이지의 항목은 원래 항목과 지문이 같습니다(덧붙인 것은 facts뿐이고 지문은 facts를 보지 않음).
    사람이 자동으로 적힌 항목에 답했거나, 사람에게 간 항목의 답이 자동 쪽에 있으면 멈춥니다."""
    auto_ids = set(r["id"] for r in record["items"] if r["to"] == "AUTO")
    person_ids = set(r["id"] for r in record["items"] if r["to"] == "PERSON")
    a = [r["Item"].strip() for r in auto_rows]
    p = [r["Item"].strip() for r in person_rows]
    if set(a) != auto_ids or len(a) != len(set(a)):
        raise SystemExit("자동 답 파일이 cross_check.json의 자동 항목과 다릅니다.")
    stray = sorted(set(p) - person_ids)
    if stray:
        raise SystemExit("사람 페이지의 답에 사람에게 가지 않은 항목이 있습니다: %s" % ", ".join(stray))
    return list(auto_rows) + list(person_rows), sorted(person_ids - set(p))


def write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow(dict((k, r.get(k, "")) for k in CSV_COLUMNS))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("--spec", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--rules", help="리뷰의 규칙을 적은 글 파일 (물음지에 그대로 실림)")
    s = sub.add_parser("split")
    for k in ("--spec", "--items", "--verdicts", "--approver", "--approval-ref", "--when", "--answers-file", "--out"):
        s.add_argument(k, required=True)
    m = sub.add_parser("merge")
    for k in ("--auto", "--person", "--record", "--out"):
        m.add_argument(k, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "merge":
        rows, unanswered = merge(read_csv(a.auto), read_csv(a.person), json.load(io.open(a.record, encoding="utf-8")))
        write_csv(a.out, rows)
        print("답 %d줄 -> %s%s" % (len(rows), a.out, (" (사람이 아직 답하지 않은 항목: %s)" % ", ".join(unanswered))
                                                    if unanswered else ""))
        return 0
    spec = json.load(io.open(a.spec, encoding="utf-8"))
    if a.cmd == "brief":
        doc = brief(spec, io.open(a.rules, encoding="utf-8").read() if a.rules else "")
        json.dump(doc, io.open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("물음 %d -> %s" % (len(doc["items"]), a.out))
        return 0
    items_doc = json.load(io.open(a.items, encoding="utf-8"))
    verdicts_doc = json.load(io.open(a.verdicts, encoding="utf-8"))
    rows, person, record = split(spec, items_doc, verdicts_doc, a.approver, a.approval_ref, a.when, a.answers_file,
                                 sha(a.verdicts))
    os.makedirs(a.out, exist_ok=True)
    write_csv(os.path.join(a.out, "auto_answers.csv"), rows)
    json.dump(person, io.open(os.path.join(a.out, "person_spec.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(record, io.open(os.path.join(a.out, "cross_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("자동 %d · 사람 %d -> %s" % (record["auto"], record["person"], a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
