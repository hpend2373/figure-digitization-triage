# -*- coding: utf-8 -*-
"""결정 묶음의 답을 관문의 답으로 옮깁니다 - 기록은 쓰지 않습니다.

    python3 bundle_route.py --items ITEMS.json --answers bundle_answers.csv \
        [--identity seg/identity600/identity_decisions.csv] \
        [--geometry seg/geometry600/geometry_decisions.csv] --out ROUTED/

`bundle_page.py`의 항목은 선택지마다 무엇을 적는지(효과)를 들고 있습니다. 이 모듈은
사람이 보낸 답 줄마다 그 효과를 찾아, 기존 관문이 받는 답 파일로 옮깁니다:

    dispositions  -> figure_disposition_answers.csv   (record_dispositions.py)
    errorbar      -> errorbar_answers.csv             (record_errorbar.py)
    identity      -> identity_answers.csv             (record_identity.py --replace)
    geometry      -> geometry_answers.csv             (record_geometry.py --replace)
    (관문 없음)   -> unrouted.csv   아직 없는 길이 필요한 답. 그 길을 만들 때까지 그대로 둡니다.
    HOLD          -> held.csv

적는 것은 관문입니다. 관문은 이 파일들을 다른 답과 똑같이 대 보고(누가 보았는가,
제안에 대한 답인가), 사본에서 먼저 돌린 뒤(`census_copy.py`) 반영합니다.

카드(identity·geometry)의 답은 지금 기록의 그 행에 효과의 칸만 바꾼 온전한 행입니다.
한 카드에 두 항목이 닿으면 한 행으로 합치고, 같은 칸을 다르게 바꾸면 둘 다 거절합니다.

**한 줄이라도 거절되면 관문 파일을 하나도 쓰지 않습니다**(refused.csv만). 거절의
흔한 까닭은 답한 페이지가 이 항목 파일과 다른 것이고(STALE_ITEM), 그러면 나머지 줄도
같은 페이지에서 왔습니다.

거절하는 것:
    UNKNOWN_ITEM       항목 파일에 없는 항목
    STALE_ITEM         답이 들고 온 항목 지문이 이 항목 파일의 것과 다름
    BAD_DECISION       그 항목에 없는 답
    ANSWERED_TWICE     한 항목에 두 줄
    UNATTRIBUTED       누가 답했는지 없음
    NOT_SEEN_BY_PERSON / APPROVAL_INCOMPLETE / OBSERVER_IS_APPROVER   (`approval`)
    UNSEEN_CHANGE      보지 않은 줄이 제안과 다름 - 아무도 그렇게 보지 않은 판정
    OBSERVER_MISMATCH  승인된 줄의 Observed_By가 그 제안을 낸 것이 아님
    EDIT_NOT_SEEN / EDIT_WITHOUT_TEXT   사람이 쓴 이름은 본 답이어야 하고 글이 있어야 함
    MISSING_CARD / UNKNOWN_FIELD / UNKNOWN_SERIES   카드 효과가 가리키는 것이 기록에 없음
    CONFLICTING_EFFECTS  한 카드의 한 칸을 두 항목이 다르게 바꿈
    MIXED_PROVENANCE   한 카드에 본 답과 승인된 관찰이 섞임 - 한 행에는 한 출처만 적힙니다
"""
import argparse
import collections
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

import approval                                                  # noqa: E402

HOLD, EDIT = "HOLD", "EDIT"
OUT_FILES = {"dispositions": "figure_disposition_answers.csv", "errorbar": "errorbar_answers.csv",
             "identity": "identity_answers.csv", "geometry": "geometry_answers.csv"}
DISPOSITION_FIELDS = ("Draft_ID", "Disposition", "Which_Panels", "Verified_By", "Seen_By_Person",
                      "Observed_By", "Approval_Ref", "Note")
ERRORBAR_FIELDS = ("Source_Document_ID", "Draft_ID", "Figure_Number", "Page", "Dispersion_Type",
                   "Errorbar_Definition_Source", "Found_On_Page", "Definition_Basis", "Verified_In_Source",
                   "Verified_By", "Observed_By", "Approval_Ref", "Note")
UNROUTED_FIELDS = ("Item", "Target_ID", "Decision", "Text", "Unit", "Needs", "Seen_By_Person", "Verified_By",
                   "Observed_By", "Approval_Ref", "Decided_On", "Note")
PROV = ("Seen_By_Person", "Observed_By", "Approval_Ref")


def rd(path):
    if not path or not os.path.exists(path):
        return []
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig")))


def wr(path, rows, fields):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow(dict((c, r.get(c, "")) for c in fields))
    os.replace(tmp, path)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path and os.path.exists(path) else ""


def series_key(name):
    return re.sub(r"[^0-9a-z]+", " ", str(name).lower()).strip()


def effect_of(item, decision):
    for o in item.get("options") or []:
        if str(o[0]) == decision:
            return o[2] if len(o) > 2 else None
    return None


def answer_problems(a, item, twice):
    """(문제 목록) - 답 한 줄."""
    iid = (a.get("Item") or "").strip()
    if item is None:
        return [("UNKNOWN_ITEM", "%s는 이 항목 파일에 없습니다." % (iid or "(빈칸)"))]
    if iid in twice:
        return [("ANSWERED_TWICE", "%s에 답이 둘 있습니다." % iid)]
    p = []
    if (a.get("Item_SHA256") or "").strip() != item.get("sha"):
        p.append(("STALE_ITEM", "%s: 답한 페이지의 항목이 이 항목 파일의 것과 다릅니다. 같은 빌드의 페이지와 항목 파일인지 "
                                "확인하세요." % iid))
    d = (a.get("Decision") or "").strip().upper()
    if d not in [str(o[0]) for o in item.get("options") or []]:
        p.append(("BAD_DECISION", "%s: %s는 이 항목의 답이 아닙니다." % (iid, d or "(빈칸)")))
        return p
    who = (a.get("Verified_By") or "").strip()
    if not who:
        p.append(("UNATTRIBUTED", "%s: 누가 답했는지가 없습니다." % iid))
    if d == HOLD:
        return p
    seen = approval.is_true(a.get("Seen_By_Person"))
    p.extend(approval.seen_problems(a, who, "%s: 직접 보았다는 표시도, 승인된 관찰의 세 칸도 없습니다." % iid))
    if not seen:
        if d != str(item.get("proposal") or ""):
            p.append(("UNSEEN_CHANGE", "%s: 보지 않은 줄이 제안(%s)과 다른 %s입니다 - 아무도 그렇게 보지 않은 판정입니다."
                      % (iid, item.get("proposal"), d)))
        if (a.get("Observed_By") or "").strip() != str(item.get("observed_by") or "").strip():
            p.append(("OBSERVER_MISMATCH", "%s: 승인된 줄의 Observed_By가 이 제안을 낸 것(%s)이 아닙니다."
                      % (iid, item.get("observed_by"))))
    if d == EDIT:
        if not seen:
            p.append(("EDIT_NOT_SEEN", "%s: 고친 이름은 사람이 쓴 글이라 본 답이어야 합니다." % iid))
        if not (a.get("Text") or "").strip():
            p.append(("EDIT_WITHOUT_TEXT", "%s: 고친 이름이 비어 있습니다." % iid))
    return p


def note_of(a):
    n = "bundle %s: %s" % (a["Item"].strip(), a["Decision"].strip().upper())
    extra = (a.get("Note") or "").strip()
    return n + (" — " + extra if extra else "")


def route_one(eff, a, iid, item, d, prov, who, out, unrouted, cards, touched):
    """효과 하나를 옮깁니다. (문제 목록)."""
    gate = eff.get("gate")
    if gate is None:
        unrouted.append(dict(Item=iid, Target_ID=item.get("target", ""), Decision=d, Text=a.get("Text", ""),
                             Unit=a.get("Unit", ""), Needs=eff.get("needs", ""), Verified_By=who,
                             Decided_On=a.get("Decided_On", ""), Note=a.get("Note", ""), **prov))
        return []
    if gate == "dispositions":
        out[gate].append(dict(eff["row"], Verified_By=who, Note=note_of(a), **prov))
        return []
    if gate == "errorbar":
        out[gate].append(dict(eff["row"], Verified_By=who, Note=note_of(a),
                              Verified_In_Source="1" if prov["Seen_By_Person"] == "1" else "",
                              Observed_By=prov["Observed_By"], Approval_Ref=prov["Approval_Ref"]))
        return []
    pid = eff["proposal_id"]
    base = cards[gate].get(pid)
    if base is None:
        return [("MISSING_CARD", "%s: %s 기록에 %s 행이 없습니다." % (iid, gate, pid))]
    t = touched.setdefault((gate, pid), {"row": dict(base), "set": {}, "prov": [], "notes": [], "items": []})
    bad = []
    for f, v in (eff.get("set") or {}).items():
        if f not in base:
            bad.append(("UNKNOWN_FIELD", "%s: %s 기록에 %s 칸이 없습니다." % (iid, gate, f)))
            continue
        if f in t["set"] and t["set"][f][0] != str(v):
            bad.append(("CONFLICTING_EFFECTS", "%s와 %s가 %s의 %s를 다르게 바꿉니다." % (t["set"][f][1], iid, pid, f)))
        t["set"].setdefault(f, (str(v), iid))
    if eff.get("series"):
        ser = json.loads(t["row"].get("Series") or "[]")
        for s in eff["series"]:
            hit = [x for x in ser if series_key(x.get("name")) == series_key(s.get("name"))]
            if len(hit) != 1:
                bad.append(("UNKNOWN_SERIES", "%s: %s에 계열 %r가 하나로 있지 않습니다." % (iid, pid, s.get("name"))))
                continue
            for f, v in (s.get("set") or {}).items():
                k = "Series[%s].%s" % (hit[0]["name"], f)
                if k in t["set"] and t["set"][k][0] != str(v):
                    bad.append(("CONFLICTING_EFFECTS", "%s와 %s가 %s의 %s를 다르게 바꿉니다." % (t["set"][k][1], iid, pid, k)))
                t["set"].setdefault(k, (str(v), iid))
                hit[0][f] = v
        t["row"]["Series"] = json.dumps(ser, ensure_ascii=False, separators=(",", ":"))
    if not bad and iid not in t["items"]:
        t["prov"].append((prov, who)); t["notes"].append(note_of(a)); t["items"].append(iid)
    return bad


def route(items_doc, answers, identity_rows=(), geometry_rows=()):
    """({관문: [답 행]}, unrouted, held, refused [(항목, 문제)]).

    refused가 비어 있지 않으면 나머지 결과도 쓰지 마십시오 - 거절된 카드 효과의 일부가 이미
    그 카드 행에 들어갔을 수 있습니다. `main`은 그때 관문 파일을 하나도 쓰지 않습니다."""
    items = dict((i["id"], i) for i in items_doc["items"])
    count = collections.Counter((a.get("Item") or "").strip() for a in answers)
    twice = set(k for k, n in count.items() if n > 1)
    out = collections.defaultdict(list)
    unrouted, held, refused = [], [], []
    cards = {"identity": dict((r["Proposal_ID"], r) for r in identity_rows),
             "geometry": dict((r["Proposal_ID"], r) for r in geometry_rows)}
    touched = collections.OrderedDict()          # (gate, pid) -> {"row", "set": {field: (value, item)}, "prov": [..], "notes": [..]}
    for a in answers:
        iid = (a.get("Item") or "").strip()
        item = items.get(iid)
        probs = answer_problems(a, item, twice)
        if probs:
            refused.append((iid or "(빈칸)", probs))
            continue
        d = a["Decision"].strip().upper()
        prov = approval.provenance(a)
        who = a["Verified_By"].strip()
        if d == HOLD:
            held.append(dict(a))
            continue
        eff = effect_of(item, d)
        # 한 답이 여러 곳에 적힐 수 있습니다(그림 하나의 패널 모두를 MANUAL로, 기하와 정체의 상자를 함께).
        for e in (eff if isinstance(eff, list) else [eff or {}]):
            bad = route_one(e, a, iid, item, d, prov, who, out, unrouted, cards, touched)
            if bad:
                refused.append((iid, bad))
    for (gate, pid), t in touched.items():
        if not t["items"]:
            continue
        kinds = set(p["Seen_By_Person"] for p, _w in t["prov"])
        whos = set(w for _p, w in t["prov"])
        if len(kinds) > 1 or len(whos) > 1:
            refused.append((",".join(t["items"]), [("MIXED_PROVENANCE", "%s 카드 %s에 본 답과 승인된 관찰(또는 다른 사람)이 섞였습니다: %s. "
                                                    "한 행에는 한 출처만 적힙니다 - 모두 ‘직접 보았다’로 하거나 나눠 보내세요."
                                                    % (gate, pid, ", ".join(t["items"])))]))
            continue
        row = t["row"]
        for f, (v, _i) in t["set"].items():
            if not f.startswith("Series["):
                row[f] = v
        p0 = t["prov"][0][0]
        row["Verified_By"] = t["prov"][0][1]
        row["Seen_By_Person"] = p0["Seen_By_Person"]
        row["Observed_By"] = "; ".join(sorted(set(p["Observed_By"] for p, _w in t["prov"] if p["Observed_By"])))
        row["Approval_Ref"] = "; ".join(sorted(set(p["Approval_Ref"] for p, _w in t["prov"] if p["Approval_Ref"])))
        old = (row.get("Note") or "").strip()
        row["Note"] = (old + " | " if old else "") + "; ".join(t["notes"])
        out[gate].append(row)
    return out, unrouted, held, refused


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--items", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--identity")
    ap.add_argument("--geometry")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    for flag, path in (("--identity", a.identity), ("--geometry", a.geometry)):
        # 적었는데 없는 카드 파일을 빈 카드로 읽으면, 카드를 고치는 답이 모두
        # MISSING_CARD로 거절되고 이유는 파일 이름이 틀린 것입니다.
        if path and not os.path.isfile(path):
            raise SystemExit("%s 파일이 없습니다: %s" % (flag, path))
    items = json.load(io.open(a.items, encoding="utf-8"))
    answers = rd(a.answers)
    if answers and "Item_SHA256" not in answers[0]:
        raise SystemExit("답 파일에 Item_SHA256 열이 없습니다. 결정 묶음 페이지가 내려준 파일이 맞습니까?")
    out, unrouted, held, refused = route(items, answers, rd(a.identity), rd(a.geometry))
    os.makedirs(a.out, exist_ok=True)
    if os.path.abspath(a.answers).startswith(os.path.abspath(a.out) + os.sep):
        raise SystemExit("답 파일이 출력 폴더 안에 있습니다 (%s)." % a.answers)
    log = dict(items=sha(a.items), answers=sha(a.answers), identity=sha(a.identity), geometry=sha(a.geometry),
               routed=dict((g, len(r)) for g, r in out.items()), unrouted=len(unrouted), held=len(held),
               refused=[[i, [list(p) for p in ps]] for i, ps in refused],
               decided_on=sorted(set((x.get("Decided_On") or "").strip() for x in answers if (x.get("Decided_On") or "").strip())))
    if refused:
        wr(os.path.join(a.out, "refused.csv"), [dict(Item=i, Check=c, Why=m) for i, ps in refused for c, m in ps], ("Item", "Check", "Why"))
        json.dump(log, io.open(os.path.join(a.out, "route_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for i, ps in refused:
            for c, m in ps:
                print("거절 %s — %s: %s" % (i, c, m))
        print("거절 %d줄 - 관문 파일을 쓰지 않았습니다." % len(refused))
        return 1
    fields = {"dispositions": DISPOSITION_FIELDS, "errorbar": ERRORBAR_FIELDS}
    for gate, rows in out.items():
        cols = fields.get(gate) or list(collections.OrderedDict((k, 1) for r in rows for k in r))
        wr(os.path.join(a.out, OUT_FILES[gate]), rows, cols)
    wr(os.path.join(a.out, "unrouted.csv"), unrouted, UNROUTED_FIELDS)
    wr(os.path.join(a.out, "held.csv"), held, list(held[0].keys()) if held else ("Item",))
    json.dump(log, io.open(os.path.join(a.out, "route_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("옮김 %s · 길 없음 %d · 보류 %d · 결정한 날 %s" % (
        ", ".join("%s %d" % kv for kv in sorted(log["routed"].items())) or "없음", len(unrouted), len(held),
        ", ".join(log["decided_on"]) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
