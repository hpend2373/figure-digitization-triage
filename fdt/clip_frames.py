# -*- coding: utf-8 -*-
"""사람이 그린 프레임이 그림 밖으로 나간 만큼을 잘라, 기하와 정체 카드를 함께 고칩니다.

    python3 fdt/clip_frames.py --run RUN --answers clip_answers.csv --when 2026-10-16 \
        [--geometry-dir seg/geometry600] [--identity-dir seg/identity600]

기하 페이지는 그린 프레임이 패널의 영역을 조금(`DRAWN_FRAME_SLACK`) 넘는 것을 받습니다 -
손으로 그은 선이니까요. 그런데 영역이 그림 끝까지일 때는 그 몇 픽셀이 그림 밖이고,
실제 판독은 그런 상자를 PANEL_BOX_OUTSIDE_IMAGE로 멈춥니다(run2 DOWNLOAD_4 D010 p4:
오른쪽 끝 2159, 그림의 폭 2156). 고치는 것은 쉬워 보이지만 두 카드가 함께 움직여야
합니다: `make_plan`은 정체가 기하와 같은 프레임 위에서 확인되었을 때만 읽고, 정체
관문(`record_identity`)은 상자를 답에서 받지 않고 정체 제안의 행에서 짓습니다.

그래서 이 도구는:
  1. 두 카드의 프레임이 같은지 봅니다(다르면 손대지 않습니다 - 그것은 다른 문제입니다).
  2. 그 프레임을 그림의 크기로 자릅니다. 잘리는 것은 그림 밖의 픽셀뿐이라 그 위에서 읽은
     것은 아무것도 바뀌지 않습니다(정체 제안기를 잘린 프레임으로 다시 돌리면 프레임 칸만
     다릅니다 - run2에서 확인). 그림 안으로 들어가는 자르기는 하지 않습니다.
  3. 기하 카드는 기하 관문으로 다시 적습니다(그린 프레임 = 잘린 프레임, `--replace`).
  4. 정체 제안의 그 행의 프레임 칸을 잘린 프레임으로 바꾸고(원래 제안 파일은 옆에
     남깁니다), 정체 카드를 정체 관문으로 다시 적습니다 - 사람이 확인한 칸은 카드 그대로.
  5. 3·4를 먼저 임시 폴더에서 해 보고, 다시 적힌 두 카드가 프레임(과 축 띠, 이 기록의
     누가·언제)밖의 칸에서 옛 카드와 같을 때만 실제로 씁니다. 하나라도 거절되면 아무
     파일도 바뀌지 않습니다.

답 줄마다 누가 이 자르기를 보았거나 승인했는지(`approval`)가 있어야 합니다. 카드에는 카드와
자르기 중 약한 쪽이 남습니다(`kept_provenance`): 승인된 관찰이던 카드는 자르기를 사람이 보았어도
승인된 관찰입니다. 처음 확인한 사람과 날짜는 메모에 남습니다. 적는 것은 관문들이고, 이 도구는 답과 제안을 만들어 넘길 뿐입니다.
"""
import argparse
import csv
import io
import os
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import approval                                                  # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import record_geometry as RG                                     # noqa: E402
import record_identity as RI                                     # noqa: E402

FRAME = ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")
ANSWER_REQUIRED = ("Proposal_ID", "Verified_By", "Seen_By_Person")
#: 정체 관문이 답에서 받는 칸 - 카드에 있던 사람의 확인을 그대로 옮깁니다.
IDENTITY_CARRY = ("Human_Verification_Status", "X_Factor", "X_Labels", "Series_Factor", "Series", "Mark_Type",
                  "Outcome_Name", "Unit", "N_Outcome", "Bar_Top_Definition", "Errorbar_Stem_Confirmed", "Read_Route")
GEOMETRY_CARRY = ("Human_Verification_Status", "Y_Tick_Top_Value", "Y_Tick_Bottom_Value", "Confirmed_Tick_Values",
                  "Y_Axis_Shared_With")


def rd(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig"))) if os.path.exists(path) else []


def frame_of(row):
    try:
        return [int(round(float(row[k]))) for k in FRAME]
    except (KeyError, TypeError, ValueError):
        return None


def clipped(frame, size):
    """그림 (w, h) 안으로 자른 프레임. 그림 밖만 잘리고, 안은 그대로입니다."""
    w, h = size
    x0, x1, y0, y1 = frame
    return [max(0, x0), min(w, x1), max(0, y0), min(h, y1)]


def plan(run, answers, gdir, idir):
    """([(Proposal_ID, 답, 기하 카드, 정체 카드, 잘린 프레임)], 거절 [(이름, 문제)])."""
    gcards = dict((r["Proposal_ID"], r) for r in rd(os.path.join(run, gdir, RG.DECISIONS)))
    icards = dict((r["Proposal_ID"], r) for r in rd(os.path.join(run, idir, RI.DECISIONS)))
    todo, refused = [], []
    for a in answers:
        pid = (a.get("Proposal_ID") or "").strip()
        # 누가 보았는지(`approval`)는 두 관문이 리허설에서 봅니다 - 같은 규칙을 여기 또 두지 않습니다.
        problems = []
        g, i = gcards.get(pid), icards.get(pid)
        if g is None or i is None:
            problems.append(("MISSING_CARD", "%s의 %s 카드가 없습니다." % (pid, "기하" if g is None else "정체")))
        if problems:
            refused.append((pid or "(빈칸)", problems))
            continue
        gf, if_ = frame_of(g), frame_of(i)
        if gf is None or gf != if_:
            refused.append((pid, [("CARDS_DISAGREE", "기하 %s와 정체 %s의 프레임이 다릅니다. 자르기가 고칠 문제가 "
                                                     "아닙니다 - 정체를 그 프레임 위에서 다시 확인하십시오." % (gf, if_))]))
            continue
        raster = os.path.join(run, g.get("Raster") or "")
        if not os.path.isfile(raster):
            refused.append((pid, [("RASTER_MISSING", "%s가 없습니다." % g.get("Raster"))]))
            continue
        size = Image.open(raster).size
        new = clipped(gf, size)
        if new == gf:
            refused.append((pid, [("NOTHING_TO_CLIP", "프레임 %s가 이미 그림 %s 안에 있습니다." % (gf, size))]))
            continue
        todo.append((pid, a, g, i, new))
    return todo, refused


#: 다시 적은 카드가 옛 카드와 달라도 되는 칸. 프레임과 프레임에서 바로 나오는 축 띠,
#: 그리고 이 기록 자체(누가·언제·어떻게)뿐입니다. 그 밖의 칸이 달라지면 제안 파일이 카드를
#: 적은 뒤에 다시 만들어진 것이고, 자르기가 그 차이까지 카드에 싣게 됩니다 - 멈춥니다.
MAY_CHANGE = FRAME + ("Axis_X_Region", "Axis_Y_Region", "Verified_By", "Verified_At", "Note") \
    + approval.APPROVAL_COLUMNS


def kept_provenance(card, answer):
    """다시 적은 카드의 '누가 보았는가'. 카드와 자르기 중 약한 쪽이 남습니다.

    카드가 승인된 관찰(Seen_By_Person=0)이면 - 예를 들어 계열 칸 하나를 규칙으로 바꾸고 사람이 승인한
    카드 - 자르기를 사람이 직접 보았어도 그 카드는 여전히 승인된 관찰입니다: 자르기는 프레임을 보았을
    뿐, 그 계열 칸을 본 것이 아닙니다. 둘 다 승인된 관찰이면 둘 다 적습니다. 카드가 본 답이면(빈칸은
    이 칸이 생기기 전의 기록이고, 그때 관문은 본 답만 받았습니다) 자르기의 것이 남습니다."""
    clip = approval.provenance(answer)
    if (card.get("Seen_By_Person") or "").strip() != "0":
        return clip
    if clip["Seen_By_Person"] == "1":
        return dict((k, card.get(k, "")) for k in approval.APPROVAL_COLUMNS)
    return {"Seen_By_Person": "0",
            "Observed_By": " ; ".join(x for x in (card.get("Observed_By", ""), clip["Observed_By"]) if x),
            "Approval_Ref": " ; ".join(x for x in (card.get("Approval_Ref", ""), clip["Approval_Ref"]) if x)}


def how_seen(card):
    seen = (card.get("Seen_By_Person") or "").strip()
    return "본 답" if seen == "1" else "본 답, 이 칸이 생기기 전 기록" if not seen \
        else "승인된 관찰: %s" % (card.get("Observed_By") or "?")


def _answers(todo):
    gans, ians = [], []
    for pid, a, g, i, new in todo:
        said = (a.get("Note") or "").strip()

        def note(card):
            was = "원래 확인: %s %s (%s)" % (card.get("Verified_By", ""), card.get("Verified_At", ""), how_seen(card))
            return " | ".join(x for x in ("clip_frames: %s -> %s (그림 밖만 자름)" % (frame_of(card), new), was,
                                          said, (card.get("Note") or "").strip()) if x)
        gans.append(dict([(k, g.get(k, "")) for k in GEOMETRY_CARRY], Proposal_ID=pid,
                         Drawn_Frame=",".join(str(v) for v in new), Verified_By=a["Verified_By"].strip(),
                         Note=note(g), **kept_provenance(g, a)))
        ians.append(dict([(k, i.get(k, "")) for k in IDENTITY_CARRY], Proposal_ID=pid,
                         Verified_By=a["Verified_By"].strip(), Note=note(i), **kept_provenance(i, a)))
    return gans, ians


def _drift(old, new):
    """다시 적은 카드가 옛 카드와 달라진, 달라지면 안 되는 칸."""
    return sorted(c for c in set(old) | set(new) if c not in MAY_CHANGE and (old.get(c) or "") != (new.get(c) or ""))


def apply(run, todo, when, gdir, idir, log=print):
    """기하·정체 관문으로 적습니다. (적힌 기하 행, 적힌 정체 행, 거절).

    먼저 임시 폴더에서 두 관문을 그대로 돌려 봅니다(리허설). 어느 관문이든 거절하거나,
    다시 적힌 카드가 프레임 밖의 칸에서 옛 카드와 다르면 아무것도 쓰지 않습니다. 둘 다
    통과하면 리허설이 쓴 파일을 그대로 옮깁니다 - 확인한 것이 곧 적히는 것입니다."""
    if not todo:
        return [], [], []
    import tempfile
    gans, ians = _answers(todo)
    gpath, ipath = os.path.join(run, gdir, RG.DECISIONS), os.path.join(run, idir, RI.DECISIONS)
    ppath = os.path.join(run, idir, IP.PROPOSALS)
    rows = rd(ppath)
    clip = dict((pid, new) for pid, _a, _g, _i, new in todo)
    for r in rows:
        if r["Proposal_ID"] in clip:
            r.update(dict(zip(FRAME, [str(v) for v in clip[r["Proposal_ID"]]])))
    fields = list(rows[0].keys()) if rows else list(IP.IDENTITY_COLUMNS)
    tmp = tempfile.mkdtemp(prefix="clip_frames_")
    try:
        tprop = os.path.join(tmp, "identity")
        os.makedirs(tprop)
        with io.open(os.path.join(tprop, IP.PROPOSALS), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        tg, ti = os.path.join(tmp, RG.DECISIONS), os.path.join(tmp, RI.DECISIONS)
        shutil.copy2(gpath, tg)
        shutil.copy2(ipath, ti)
        quiet = lambda *_a: None                                      # noqa: E731
        try:
            gw, gref, _p = RG.record(os.path.join(run, gdir), gans, when, out_path=tg, replace=True, log=quiet)
            iw, iref, _p = RI.record(tprop, ians, when, out_path=ti, replace=True, log=quiet)
        except SystemExit as exc:
            # 관문이 파일 전체를 보고 멈춘 것(예: 제안 규칙 위반). 리허설이니 아무것도 쓰이지 않았습니다.
            bad = [(pid, [("GATE_STOPPED", str(exc))]) for pid in sorted(clip)]
            for pid, ps in bad:
                log("  거절 %s — %s: %s" % (pid, ps[0][0], ps[0][1]))
            return [], [], bad
        bad = list(gref) + list(iref)
        old = {"g": dict((r["Proposal_ID"], r) for r in rd(gpath)), "i": dict((r["Proposal_ID"], r) for r in rd(ipath))}
        new = {"g": dict((r["Proposal_ID"], r) for r in rd(tg)), "i": dict((r["Proposal_ID"], r) for r in rd(ti))}
        for side, what in (("g", "기하"), ("i", "정체")):
            for pid in sorted(set(old[side]) | set(new[side])):
                if pid in clip:
                    moved = _drift(old[side].get(pid, {}), new[side].get(pid, {}))
                    if moved:
                        bad.append((pid, [("PROPOSAL_DRIFTED", "%s 카드를 다시 적으면 프레임 밖의 칸(%s)도 바뀝니다. 제안 "
                                                              "파일이 카드를 적은 뒤에 다시 만들어진 것입니다 - 자르기가 "
                                                              "고칠 문제가 아닙니다." % (what, ", ".join(moved[:6])))]))
                elif old[side].get(pid) != new[side].get(pid):
                    bad.append((pid, [("OTHER_CARD_CHANGED", "자르지 않는 %s 카드가 바뀝니다." % what)]))
        for pid, ps in bad:
            for c, m in ps:
                log("  거절 %s — %s: %s" % (pid, c, m))
        if bad:
            return [], [], bad
        keep = ppath + ".before_clip_%s" % when
        if not os.path.exists(keep):
            shutil.copy2(ppath, keep)
        shutil.copy2(os.path.join(tprop, IP.PROPOSALS), ppath + ".tmp")
        os.replace(ppath + ".tmp", ppath)
        for src, dst in ((tg, gpath), (ti, ipath)):
            shutil.copy2(src, dst + ".tmp")
            os.replace(dst + ".tmp", dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    log("기하 %d · 정체 %d 다시 적음 (원래 정체 제안: %s)" % (len(gw), len(iw), os.path.basename(keep)))
    return gw, iw, []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--when", required=True, help="자르기를 본(또는 승인한) 날짜")
    ap.add_argument("--geometry-dir", default=os.path.join("seg", "geometry600"))
    ap.add_argument("--identity-dir", default=os.path.join("seg", "identity600"))
    a = ap.parse_args(argv)
    answers = rd(a.answers)
    missing = [c for c in ANSWER_REQUIRED if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다." % ", ".join(missing))
    todo, refused = plan(a.run, answers, a.geometry_dir, a.identity_dir)
    if refused:
        for name, ps in refused:
            for c, m in ps:
                print("거절 %s — %s: %s" % (name, c, m))
        print("거절이 있어 아무것도 고치지 않았습니다.")
        return 1
    _gw, _iw, bad = apply(a.run, todo, a.when, a.geometry_dir, a.identity_dir)
    if bad:
        print("거절이 있어 아무것도 고치지 않았습니다.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
