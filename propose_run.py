# -*- coding: utf-8 -*-
"""600 DPI 패널에 기하·정체 제안을 돌리고, 다시 그린 프레임 위에서 정체를 다시 냅니다.

    python3 propose_run.py geometry --run RUN --regions REGIONS.csv --out GDIR [--budget S]
    python3 propose_run.py identity --run RUN --regions REGIONS.csv --geometry GDIR/geometry_proposal.csv \\
        --out IDIR [--budget S]
    python3 propose_run.py reframe  --run RUN --geometry GDIR/geometry_proposal.csv --identity IDIR \\
        --frames FRAMES.json

`panel_to_page.py`가 낸 `panel_regions_600.csv`를 받아, 패널마다

    geometry   geometry_proposer.propose_panel + read_tick_values + 오버레이
               (프레임을 못 찾은 패널은 refusal_row + 영역 그림 - 사람이 프레임을 그릴 자리)
    identity   identity_proposer.propose_identity(그 패널의 기하 행 프레임 위) + 오버레이
    reframe    누군가(사람이나 Claude) 기하 프레임을 다시 그린 패널의 정체 제안을 그 프레임
               위에서 다시 낸다

를 돕니다. 셋 다 판정하지 않습니다 - 나오는 것은 전부 제안이고, 확인은 확인 페이지
(`geometry_page`·`identity_page`, 또는 둘을 한 카드에 놓는 `axis_series_page`)와 관문
(`record_geometry`·`record_identity`)의 일입니다.

**셸이 몇 분에 끊기는 곳**(맥의 원격 셸은 3분)에서 돌리므로 `--budget`초가 지나면 패널
사이에서 멈추고, 다시 부르면 이미 적힌 패널을 건너뛰고 이어 갑니다. 패널 하나는 쪼개지
않습니다.

**정체는 기하 프레임 위에서만 읽힙니다.** `make_plan`은 확인된 기하와 확인된 정체의 프레임이
정수 픽셀로 같지 않으면 정체를 다시 묻습니다("정체가 다른 프레임 위에서 확인됨"). 그래서
기하 프레임을 다시 그릴 패널은 확인 페이지에 내기 **전에** `reframe`으로 정체 제안도 같은
프레임 위에서 다시 냅니다. 프레임은 정수여야 합니다 - 기하 관문은 반올림하고 정체 제안은
버림하므로 .5 프레임은 두 카드에서 갈립니다. 처음 정체 제안 파일은
`identity_proposal.reader_frames.csv`로 한 번만 남기고, `reframe`은 늘 그것에서 시작합니다
(두 번 돌려도 같은 결과).

FRAMES.json은 `{"<Proposal_ID>": "x0,x1,y0,y1"}`이거나, 확인 페이지가 받는 제안 파일
(`{"P": {"<Proposal_ID>": {"geo": {"frame": "x0,x1,y0,y1", ...}, ...}}}`)입니다 - 후자에서는
`frame`이 빈 패널을 건너뜁니다.

Proposal_ID = `<Draft_ID>__p<Panel_Index>`.
"""
import argparse
import csv
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402

READER_FRAMES = "identity_proposal.reader_frames.csv"


def load(path):
    if not path or not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def pid_of(r):
    return "%s__p%s" % (r["Draft_ID"], r["Panel_Index"])


def what(r):
    """오버레이와 카드가 사람에게 말하는 '어느 패널의 무엇인지'."""
    return "%s p%s %s%s" % (r["Draft_ID"], r["Panel_Index"], r.get("Mark_Type", ""),
                            (" x" + r["Mark_Count"]) if r.get("Mark_Count") else "")


def _open(path):
    from PIL import Image
    return Image.open(path)


def geometry_batch(run, regions_csv, out, budget=0, clock=time.time):
    """(이번에 한 수, 남은 수). 이미 제안이나 거절이 적힌 패널은 건너뜁니다."""
    os.makedirs(out, exist_ok=True)
    prop, ref = os.path.join(out, "geometry_proposal.csv"), os.path.join(out, GP.REFUSED)
    done = {r["Proposal_ID"] for r in load(prop)} | {r["Proposal_ID"] for r in load(ref)}
    todo = sorted((r for r in load(regions_csv) if pid_of(r) not in done),
                  key=lambda r: (r["Raster_600"], int(r["Panel_Index"])))
    t0, n, cache, new_rows, new_ref = clock(), 0, {}, [], []
    for r in todo:
        if budget and clock() - t0 > budget:
            break
        pid, rpath = pid_of(r), os.path.join(run, r["Raster_600"])
        if rpath not in cache:
            cache.clear()
            cache[rpath] = _open(rpath)
        im, sha = cache[rpath], r["Raster_600_SHA256"]
        reg = [int(v) for v in r["Region_600"].split(",")]
        reg = (max(0, reg[0]), max(0, reg[1]), min(im.width, reg[2]), min(im.height, reg[3]))
        row = GP.propose_panel(im, reg, proposal_id=pid, raster_path=r["Raster_600"], raster_sha256=sha)
        if row is None:
            refusal = GP.refusal_row(pid, r["Raster_600"], sha, reg, detail="영역 안에 축선이 하나도 없습니다",
                                     note=what(r))
            GP.refusal_picture(im, refusal, os.path.join(out, pid + ".png"))
            new_ref.append(refusal)
        else:
            try:
                GP.read_tick_values(im, row)
            except Exception as e:                                # noqa: BLE001
                row["Y_Tick_Read_Status"] = GP.READ_REFUSED
                row["Y_Tick_Read_Detail"] = "reader crashed: %r" % (e,)
            row["Note"] = what(r)
            GP.proposal_overlay(im, row, os.path.join(out, pid + ".png"))
            new_rows.append(row)
        n += 1
    GP.write_proposals(prop, load(prop) + [{c: v.get(c, "") for c in GP.PROPOSAL_COLUMNS} for v in new_rows])
    GP.write_refusals(ref, load(ref) + new_ref)
    return n, len(todo) - n


def identity_batch(run, regions_csv, geometry_csv, out, budget=0, clock=time.time):
    """(이번에 한 수, 남은 수). 프레임 없는 기하 행은 정체를 낼 자리가 없어 건너뜁니다."""
    os.makedirs(out, exist_ok=True)
    prop = os.path.join(out, IP.PROPOSALS)
    regs = {pid_of(r): r for r in load(regions_csv)}
    caps = {r["Draft_ID"]: r.get("Caption_Text", "") for r in load(os.path.join(run, "figure_intake_draft.csv"))}
    done = {r["Proposal_ID"] for r in load(prop)}
    todo = sorted((g for g in load(geometry_csv) if GP._frame_of(g) is not None and g["Proposal_ID"] not in done),
                  key=lambda g: (g["Raster"], g["Proposal_ID"]))
    t0, n, cache, new = clock(), 0, {}, []
    for g in todo:
        if budget and clock() - t0 > budget:
            break
        pid, rpath = g["Proposal_ID"], os.path.join(run, g["Raster"])
        if rpath not in cache:
            cache.clear()
            cache[rpath] = _open(rpath)
        im = cache[rpath]
        row = IP.propose_identity(im, g, kind=regs.get(pid, {}).get("Mark_Type", ""),
                                  caption=caps.get(pid.split("__p")[0], ""), raster_sha256=g.get("Raster_SHA256", ""))
        IP.overlay(im, row, os.path.join(out, pid + ".png"))
        new.append(row)
        n += 1
    IP.write_proposals(prop, load(prop) + [{c: v.get(c, "") for c in IP.IDENTITY_COLUMNS} for v in new])
    return n, len(todo) - n


def frames_from(path):
    """{Proposal_ID: 'x0,x1,y0,y1'} - 프레임 목록이거나 확인 페이지의 제안 파일에서."""
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("P"), dict):
        return {pid: v["geo"]["frame"] for pid, v in data["P"].items() if (v.get("geo") or {}).get("frame")}
    return dict(data)


def frame_problem(text):
    """프레임 글이 쓸 수 없으면 그 까닭, 쓸 수 있으면 ''."""
    parts = str(text or "").split(",")
    if len(parts) != 4:
        return "x0,x1,y0,y1 네 수가 아닙니다"
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return "수가 아닙니다"
    if any(v != int(v) for v in nums):
        return "정수가 아닙니다 - 기하 관문은 반올림, 정체 제안은 버림이라 두 카드의 프레임이 갈립니다"
    x0, x1, y0, y1 = nums
    if not (x0 < x1 and y0 < y1):
        return "왼쪽<오른쪽, 위<아래가 아닙니다"
    return ""


def reframe(run, geometry_csv, identity_dir, frames):
    """다시 그린 프레임 위의 정체 제안. [(pid, 옛 프레임, 새 프레임)]. 하나라도 못 하면 아무것도 쓰지 않습니다."""
    prop = os.path.join(identity_dir, IP.PROPOSALS)
    keep = os.path.join(identity_dir, READER_FRAMES)
    base = load(keep) or load(prop)                     # 늘 리더 프레임의 원본에서 시작
    geo = {g["Proposal_ID"]: g for g in load(geometry_csv)}
    at = {r["Proposal_ID"]: i for i, r in enumerate(base)}
    stops = []
    for pid, fr in sorted(frames.items()):
        why = frame_problem(fr)
        if pid not in geo:
            stops.append((pid, "UNKNOWN_PANEL", "기하 제안에 없는 패널"))
        elif pid not in at:
            stops.append((pid, "NO_IDENTITY_PROPOSAL", "정체 제안에 없는 패널"))
        elif why:
            stops.append((pid, "FRAME_MALFORMED", "%s: %s" % (fr, why)))
    if stops:
        raise SystemExit("\n".join("멈춤 %s — %s: %s" % s for s in stops) + "\n아무것도 쓰지 않았습니다.")
    if not os.path.exists(keep):
        shutil.copy2(prop, keep)
    caps = {r["Draft_ID"]: r.get("Caption_Text", "") for r in load(os.path.join(run, "figure_intake_draft.csv"))}
    rows, done = list(base), []
    for pid, fr in sorted(frames.items()):
        g = dict(geo[pid])
        x0, x1, y0, y1 = [str(int(float(v))) for v in fr.split(",")]
        g.update(Panel_X0=x0, Panel_X1=x1, Panel_Y0=y0, Panel_Y1=y1)
        old = base[at[pid]]
        im = _open(os.path.join(run, g["Raster"]))
        new = IP.propose_identity(im, g, kind=old.get("Panel_Kind", ""), caption=caps.get(pid.split("__p")[0], ""),
                                  raster_sha256=g.get("Raster_SHA256", ""))
        IP.overlay(im, new, os.path.join(identity_dir, pid + ".png"))
        rows[at[pid]] = {c: new.get(c, "") for c in IP.IDENTITY_COLUMNS}
        done.append((pid, ",".join(str(old.get(k, "")) for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1")),
                     ",".join(str(new[k]) for k in ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1"))))
    IP.write_proposals(prop, rows)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("geometry")
    g.add_argument("--run", required=True); g.add_argument("--regions", required=True)
    g.add_argument("--out", required=True); g.add_argument("--budget", type=float, default=0)
    i = sub.add_parser("identity")
    i.add_argument("--run", required=True); i.add_argument("--regions", required=True)
    i.add_argument("--geometry", required=True); i.add_argument("--out", required=True)
    i.add_argument("--budget", type=float, default=0)
    r = sub.add_parser("reframe")
    r.add_argument("--run", required=True); r.add_argument("--geometry", required=True)
    r.add_argument("--identity", required=True); r.add_argument("--frames", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "geometry":
        n, left = geometry_batch(a.run, a.regions, a.out, a.budget)
        print("기하: 이번 %d · 남음 %d" % (n, left))
    elif a.cmd == "identity":
        n, left = identity_batch(a.run, a.regions, a.geometry, a.out, a.budget)
        print("정체: 이번 %d · 남음 %d" % (n, left))
    else:
        done = reframe(a.run, a.geometry, a.identity, frames_from(a.frames))
        for pid, old, new in done:
            print("%s  %s -> %s" % (pid, old, new))
        print("다시 낸 정체 제안 %d개" % len(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
