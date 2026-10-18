# -*- coding: utf-8 -*-
"""그린 패널의 출처(그림)를 바로잡습니다 - 상자·영역·카드·결과 이름을 함께, 값은 그대로.

    python3 move_panels.py --run RUN --from DRAFT_A --panels 2,4 --to DRAFT_B --when 2026-10-18 \
        --approval-ref "remaining_answers_2026-10-18.csv R01 MOVE: minyeop 승인" [--write] [--log moved.json]

크롭 하나에 그림 둘이 들어 있으면, 사람이 그 크롭(A)에 그린 패널 가운데 일부는 실은 다른 그림(B)의
것입니다. run2(2026-10-18 R01): 한 논문의 그림 4 크롭에 그림 5의 막대 둘이 함께 잘려 들어왔고, 2026-09-13에
그 크롭에 그린 패널 넷 가운데 오른쪽 둘(P2·P4)이 그림 5의 것이었습니다 - 이미 기하·정체가 확인되어 읽히고
있었으므로 값은 빠진 것이 아니라 **그림 번호가 틀린** 것이었고, 사람은 '출처 바로잡기(MOVE)'를 골랐습니다.

이 도구는 그 이름 바꾸기 하나를 모든 기록에서 한 번에 합니다. 패널 A의 i번째 것은 B의 j번째가 됩니다
(`--panels`에 적은 순서대로 j = 1, 2, …):

    seg/panel_decisions.csv              Draft_ID·Panel_Index  (B의 '패널 없음(NO_PANELS)' 줄은 지움 - 이제 있음)
    seg/regions600/panel_regions_600.csv Draft_ID·Panel_Index  (600 DPI 래스터 경로는 그대로 - 같은 그림 파일)
    seg/geometry600/*.csv, seg/identity600/*.csv   Proposal_ID `A__p<i>` → `B__p<j>` (다른 칸에 적힌 같은 이름도)
    outcome_decisions.csv                Panel_ID `A_P<i>` → `B_P<j>`, Draft_ID·Panel_Index
    seg/geometry600·identity600의 `<A__p<i>>.<ext>` 그림     `B__p<j>` 이름으로 복사 (지우지 않음)

옮긴 줄마다 Note(있으면)에 무엇에서 왔고 누가 승인했는지를 붙입니다. 값·상자·눈금·계열은 바꾸지 않습니다.
B의 처분(예: RECROP)을 바꾸는 것은 이 도구가 아니라 `record_dispositions`입니다 - 처분은 그 관문의 기록입니다.

멈추는 것(아무것도 쓰지 않음):
    SAME_DRAFT          A와 B가 같음
    OTHER_DOCUMENT      A와 B가 다른 논문 (figure_intake_draft.csv) - 논문을 건너는 출처는 없습니다
    NO_SUCH_PANEL       A에 그 번호의 그린 패널(PANELS)이 없음
    TARGET_HAS_PANELS   B에 이미 그린 패널이 있음 - 번호가 겹치거나 섞입니다
    ID_TAKEN            새 이름(B__p<j>, B_P<j>)이 어느 기록에 이미 있음
    LEGENDS             A에 범례 묶음 기록이 있음 - 그 묶음은 패널 번호로 적혀 있어 옮기면 뜻이 바뀝니다
    NO_APPROVAL         --approval-ref가 없음 - 누가 이 옮김을 정했는지 없는 옮김은 하지 않습니다
`--write` 없이는 무엇을 바꿀지 보이기만 합니다. 런을 바꾸기 전에 사본에서 돌리고, 백업은 부르는 쪽이 둡니다.
"""
import argparse
import csv
import io
import json
import os
import shutil
import sys

PANEL_DECISIONS = os.path.join("seg", "panel_decisions.csv")
REGIONS = os.path.join("seg", "regions600", "panel_regions_600.csv")
CARD_DIRS = (os.path.join("seg", "geometry600"), os.path.join("seg", "identity600"))
OUTCOMES = "outcome_decisions.csv"
LEGENDS = "legend_decisions.csv"
DRAFT = "figure_intake_draft.csv"
PANELS, NO_PANELS = "PANELS", "NO_PANELS"


class Refused(SystemExit):
    def __init__(self, code, why):
        SystemExit.__init__(self, "%s: %s" % (code, why))
        self.code = code


def rd(path):
    if not os.path.exists(path):
        return None, []
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def wr(path, fields, rows):
    tmp = path + ".move.tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(dict((k, row.get(k, "")) for k in fields))
    return tmp


def verdict(row):
    return (row.get("Verdict") or "").strip().upper()


def plan_move(run, src, panels, dst, when, approval_ref):
    """({경로: (열, 새 행들)}, [(원본 그림, 사본 그림)], 기록). 맞지 않으면 Refused."""
    if not approval_ref.strip():
        raise Refused("NO_APPROVAL", "누가 이 옮김을 정했는지(--approval-ref)가 없습니다.")
    if src == dst:
        raise Refused("SAME_DRAFT", "옮길 곳이 같은 그림입니다 (%s)." % src)
    _f, drafts = rd(os.path.join(run, DRAFT))
    doc = dict((r["Draft_ID"], r.get("Source_Document_ID", "")) for r in drafts)
    for d in (src, dst):
        if d not in doc:
            raise Refused("NO_SUCH_PANEL", "%s는 이 런의 그림 초안이 아닙니다." % d)
    if doc[src] != doc[dst]:
        raise Refused("OTHER_DOCUMENT", "%s(%s)와 %s(%s)는 다른 논문입니다." % (src, doc[src], dst, doc[dst]))
    _f, legend_rows = rd(os.path.join(run, LEGENDS))
    if any(r.get("Draft_ID") == src for r in legend_rows):
        raise Refused("LEGENDS", "%s에 범례 묶음 기록이 있습니다 - 패널 번호로 적힌 묶음이라 옮기면 뜻이 바뀝니다." % src)
    index = dict((int(i), j + 1) for j, i in enumerate(panels))
    if len(index) != len(panels):
        raise Refused("NO_SUCH_PANEL", "같은 패널 번호가 두 번 있습니다: %s" % panels)
    note = "moved from %s P%%d (%s, %s)" % (src, when, approval_ref.strip())
    out, copies = {}, []
    # 그린 상자
    pf, prow = rd(os.path.join(run, PANEL_DECISIONS))
    have = dict((int(r["Panel_Index"]), r) for r in prow if r["Draft_ID"] == src and verdict(r) == PANELS
                and str(r.get("Panel_Index") or "").isdigit())
    missing = [i for i in index if i not in have]
    if missing:
        raise Refused("NO_SUCH_PANEL", "%s에 그린 패널 %s가 없습니다." % (src, ", ".join("P%d" % i for i in missing)))
    if any(r["Draft_ID"] == dst and verdict(r) == PANELS for r in prow):
        raise Refused("TARGET_HAS_PANELS", "%s에는 이미 그린 패널이 있습니다." % dst)
    new_rows, dropped = [], []
    for r in prow:
        if r["Draft_ID"] == dst and verdict(r) == NO_PANELS:
            dropped.append(dict(r))
            continue
        if r["Draft_ID"] == src and verdict(r) == PANELS and str(r.get("Panel_Index") or "").isdigit() \
                and int(r["Panel_Index"]) in index:
            i = int(r["Panel_Index"])
            r = dict(r, Draft_ID=dst, Panel_Index=str(index[i]))
            if "Note" in pf:
                r["Note"] = "; ".join(x for x in ((r.get("Note") or "").strip(), note % i) if x)
        new_rows.append(r)
    out[PANEL_DECISIONS] = (pf, new_rows)
    # 600 DPI 영역
    gf, grow = rd(os.path.join(run, REGIONS))
    if gf:
        moved = []
        for r in grow:
            if r["Draft_ID"] == src and str(r.get("Panel_Index") or "").isdigit() and int(r["Panel_Index"]) in index:
                r = dict(r, Draft_ID=dst, Panel_Index=str(index[int(r["Panel_Index"])]))
            if r["Draft_ID"] == dst and str(r.get("Panel_Index") or "") in [str(j) for j in index.values()]:
                moved.append(r)
            out.setdefault(REGIONS, (gf, []))[1].append(r)
        if len(moved) > len(index):
            raise Refused("ID_TAKEN", "%s의 600 DPI 영역에 이미 같은 번호가 있습니다." % dst)
    # 카드 (기하·정체의 모든 CSV)
    ids = dict(("%s__p%d" % (src, i), "%s__p%d" % (dst, j)) for i, j in index.items())
    for d in CARD_DIRS:
        folder = os.path.join(run, d)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            stem, ext = os.path.splitext(name)
            if stem in ids:
                copies.append((path, os.path.join(folder, ids[stem] + ext)))
                if os.path.exists(os.path.join(folder, ids[stem] + ext)):
                    raise Refused("ID_TAKEN", "%s가 이미 있습니다." % os.path.join(d, ids[stem] + ext))
            if ext.lower() != ".csv":
                continue
            fields, rows = rd(path)
            if "Proposal_ID" not in (fields or []):
                continue
            taken = [r["Proposal_ID"] for r in rows if r["Proposal_ID"] in ids.values()]
            if taken:
                raise Refused("ID_TAKEN", "%s에 %s가 이미 있습니다." % (os.path.join(d, name), ", ".join(taken)))
            changed, new = False, []
            for r in rows:
                if r["Proposal_ID"] in ids:
                    old = r["Proposal_ID"]
                    r = dict((k, ids.get(v, v)) for k, v in r.items())
                    if "Note" in fields:
                        r["Note"] = "; ".join(x for x in ((r.get("Note") or "").strip(),
                                                         "moved from %s (%s, %s)" % (old, when, approval_ref.strip())) if x)
                    changed = True
                elif any(v in ids for v in r.values()):
                    r = dict((k, ids.get(v, v)) for k, v in r.items())
                    changed = True
                new.append(r)
            if changed:
                out[os.path.join(d, name)] = (fields, new)
    # 결과 이름
    of, orow = rd(os.path.join(run, OUTCOMES))
    if of:
        pids = dict(("%s_P%d" % (src, i), (dst, j)) for i, j in index.items())
        taken = [r["Panel_ID"] for r in orow if r["Panel_ID"] in ["%s_P%d" % (dst, j) for j in index.values()]]
        if taken:
            raise Refused("ID_TAKEN", "%s에 %s가 이미 있습니다." % (OUTCOMES, ", ".join(taken)))
        new, changed = [], False
        for r in orow:
            if r["Panel_ID"] in pids:
                d2, j = pids[r["Panel_ID"]]
                i = int(r["Panel_ID"].rsplit("_P", 1)[1])
                r = dict(r, Panel_ID="%s_P%d" % (d2, j), Draft_ID=d2, Panel_Index=str(j))
                if "Note" in of:
                    r["Note"] = "; ".join(x for x in ((r.get("Note") or "").strip(), note % i) if x)
                changed = True
            new.append(r)
        if changed:
            out[OUTCOMES] = (of, new)
    record = {"from": src, "to": dst, "panels": dict(("P%d" % i, "P%d" % j) for i, j in index.items()),
              "proposal_ids": ids, "when": when, "approval_ref": approval_ref.strip(),
              "files": sorted(out), "copies": [[os.path.relpath(a, run), os.path.relpath(b, run)] for a, b in copies],
              "dropped_no_panels_rows": len(dropped)}
    return out, copies, record


def apply_move(run, out, copies):
    """모두 임시 파일로 먼저 쓰고, 다 되면 한꺼번에 바꿉니다."""
    tmps = []
    try:
        for rel, (fields, rows) in out.items():
            tmps.append((wr(os.path.join(run, rel), fields, rows), os.path.join(run, rel)))
    except Exception:
        for t, _p in tmps:
            if os.path.exists(t):
                os.remove(t)
        raise
    for t, p in tmps:
        os.replace(t, p)
    for a, b in copies:
        shutil.copy2(a, b)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--panels", required=True, help="옮길 A의 패널 번호, 쉼표로 (적은 순서가 B의 번호 1, 2, …)")
    ap.add_argument("--to", dest="dst", required=True)
    ap.add_argument("--when", required=True, help="옮기기로 정한 날")
    ap.add_argument("--approval-ref", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--log")
    a = ap.parse_args(argv)
    run = os.path.expanduser(a.run)
    try:
        panels = [int(x) for x in a.panels.split(",") if x.strip()]
    except ValueError:
        raise Refused("NO_SUCH_PANEL", "패널 번호가 숫자가 아닙니다: %s" % a.panels)
    out, copies, record = plan_move(run, a.src, panels, a.dst, a.when, a.approval_ref)
    record["written"] = bool(a.write)
    if a.write:
        apply_move(run, out, copies)
    if a.log:
        json.dump(record, io.open(a.log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(record, ensure_ascii=False, indent=1))
    print("%s %d파일 · 그림 %d장" % ("옮김" if a.write else "(보이기만) 바꿀 것", len(out), len(copies)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
