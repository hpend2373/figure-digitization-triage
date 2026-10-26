# -*- coding: utf-8 -*-
"""축·계열 확인 페이지의 답을 관문의 답으로 나누고, 새 제안을 런의 제안 파일에 붙입니다.

    python3 fdt/route_axis_series.py route --answers ANSWERS.csv --proposals PROPOSALS.json \\
        --geometry GDIR --identity IDIR --out OUT [--reviewers reviewers.json] [--rename OLD=NEW ...]
    python3 fdt/route_axis_series.py merge --run RUN --geometry GDIR --identity IDIR \\
        --regions REGIONS.csv --when 2026-10-17 [--write]

**route.** `axis_series_page`가 내려받게 하는 답 CSV(`Proposal_ID, Part, Answer, Verified_By,
Seen_By_Person, Note, Gate_Row`)를 받아

    OUT/geometry_answers.csv   '제안대로'의 기하 관문 줄 -> record_geometry --answers
    OUT/identity_answers.csv   '제안대로'의 정체 관문 줄 -> record_identity --answers
    OUT/not_accepted.csv       고칠 곳 있음·보류 - 메모와 함께. 관문에 가지 않고, 고쳐 다시 묻습니다

를 씁니다. 관문 줄은 페이지가 geometry_page.js·identity_page.js의 `verdictOf`로 지은 그대로
옮기고, 열 이름도 그 두 파일의 `CSV_COLUMNS`에서 읽습니다. 옮기기 전에 봅니다: 줄마다 사람이
보았다고 했는가, 이름이 있는가, 관문 줄이 그 패널·그 부분·그 이름의 것인가, 판정이 제안이 말한
판정인가. 하나라도 어긋나면 아무것도 쓰지 않습니다 - 답 파일은 사람이 손으로 열 수 있는
파일이고, 손댄 줄이 관문 줄과 어긋나면 어느 쪽이 사람의 말인지 이 도구가 정할 수 없습니다.

`--reviewers`(make_plan의 등록부 JSON)를 주면 이름이 등록부에 있는지도 봅니다
(UNREGISTERED_REVIEWER). 2026-10-17 run2의 답 192줄이 `miyeop`으로 들어왔고 기록과 등록부는
`minyeop`이었습니다 - 관문은 이름을 그대로 적으므로, 오타는 기록에 사람 하나를 더 만듭니다.
고치는 것은 사람이 정한 대로 `--rename miyeop=minyeop`: 답 줄과 관문 줄의 Verified_By를 함께
바꾸고, 관문 줄의 Note에 바꾼 사실을 남깁니다. 원래 답 파일은 그대로 둡니다(무엇을 쳤는지의 증거).

**merge.** 관문은 `--proposals DIR`의 제안 파일에 대해 답을 받고, `make_plan`은
`seg/geometry600`·`seg/identity600`·`seg/regions600`을 읽습니다. 그래서 새 폴더(예:
`seg/geometry600_2026-10-16`)에서 낸 제안은 기록 **전에** 그 세 파일에 붙입니다: 제안 행과
거절 행, 오버레이 그림, 600 DPI 영역 행. 이미 있는 Proposal_ID, 링크인 파일, 이미 있는 백업,
대상 파일에 없는 열은 멈춥니다. 기본은 무엇을 붙일지만 보여 주고, `--write`일 때 백업
(`<파일>.before_merge_<when>`)을 남기고 붙입니다. 런의 사본에서 먼저 하고, 관문과 점검을 돌려
본 뒤에 런에 합니다.
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

PARTS = {"GEOMETRY": "geo", "IDENTITY": "idn"}
ANSWERS = ("ACCEPT", "FIX", "HOLD")
ANSWER_COLUMNS = ("Proposal_ID", "Part", "Answer", "Verified_By", "Seen_By_Person", "Note", "Gate_Row")


def js_columns(name):
    """그 페이지 논리 파일의 CSV_COLUMNS - 관문 답 CSV의 열은 페이지가 정한 그대로입니다."""
    with io.open(os.path.join(HERE, name), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"var CSV_COLUMNS = \[(.*?)\];", text, re.S)
    return re.findall(r"'([^']+)'", m.group(1))


GEOMETRY_COLUMNS = js_columns("geometry_page.js")
IDENTITY_COLUMNS = js_columns("identity_page.js")


def load(path):
    if not path or not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def header(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return next(csv.reader(fh), [])


def write(path, columns, rows):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    os.replace(tmp, path)


# ---------------------------------------------------------------- route
def route(answers, proposals, geometry_ids, identity_ids, names=None, renames=None):
    """(기하 줄, 정체 줄, 받지 않은 줄, 멈춤 [(줄, 코드, 사유)]).

    names: 등록부의 {소문자 이름: reviewer_id} - 주면 이름이 그 안에 있어야 합니다.
    renames: {친 이름: 적을 이름} - 사람이 정한 이름 고침. 답과 관문 줄에 함께."""
    geo, idn, other, stops, seen = [], [], [], [], set()
    known = {"GEOMETRY": geometry_ids, "IDENTITY": identity_ids}
    renames = renames or {}
    for n, a in enumerate(answers, 2):
        pid, part = (a.get("Proposal_ID") or "").strip(), (a.get("Part") or "").strip().upper()
        ans, typed = (a.get("Answer") or "").strip().upper(), (a.get("Verified_By") or "").strip()
        who = renames.get(typed, typed)
        where = "%d행 %s %s" % (n, pid, part)

        def stop(code, why):
            stops.append((where, code, why))
        if part not in PARTS:
            stop("BAD_PART", "Part는 GEOMETRY 또는 IDENTITY"); continue
        if ans not in ANSWERS:
            stop("BAD_ANSWER", "Answer는 %s" % "/".join(ANSWERS)); continue
        if pid not in proposals:
            stop("UNKNOWN_PANEL", "제안 파일에 없는 패널"); continue
        if pid not in known[part]:
            stop("NOT_IN_PROPOSALS", "관문이 받을 제안 CSV에 없는 패널"); continue
        if (pid, part) in seen:
            stop("DUPLICATE", "같은 패널·부분의 답이 둘"); continue
        seen.add((pid, part))
        if (a.get("Seen_By_Person") or "").strip() != "1":
            stop("NOT_SEEN", "두 그림을 직접 봤다고 하지 않은 답"); continue
        if not who:
            stop("NO_REVIEWER", "보신 분 이름이 없는 답"); continue
        if names is not None and who.lower() not in names:
            stop("UNREGISTERED_REVIEWER", "등록부에 없는 이름 %r - 오타라면 사람이 정한 대로 --rename %s=<등록된 이름>"
                 % (who, typed)); continue
        raw = (a.get("Gate_Row") or "").strip()
        if ans != "ACCEPT":
            if raw:
                stop("GATE_ROW_ON_NON_ACCEPT", "'%s'에 관문 줄이 붙어 있습니다" % ans); continue
            note = (a.get("Note") or "").strip()
            if who != typed:
                note = (note + " | 검토자 이름 %r → %r" % (typed, who)).lstrip(" |")
            other.append({"Proposal_ID": pid, "Part": part, "Answer": ans, "Verified_By": who, "Note": note})
            continue
        if not raw:
            stop("GATE_ROW_MISSING", "'제안대로'인데 관문 줄이 없습니다"); continue
        try:
            row = json.loads(raw)
        except ValueError:
            stop("GATE_ROW_BROKEN", "관문 줄을 읽을 수 없습니다"); continue
        want = (proposals[pid].get(PARTS[part]) or {}).get("verdict", "")
        if who != typed and (row.get("Verified_By") or "").strip() == typed:
            row["Verified_By"] = who
            row["Note"] = ((row.get("Note") or "") + " | 검토자 이름 %r → %r (사람이 정한 이름 고침, 원래 답 파일에 친 그대로 있음)"
                           % (typed, who)).lstrip(" |")
        bad = [k for k, ok in (("Proposal_ID", row.get("Proposal_ID") == pid),
                               ("Verified_By", (row.get("Verified_By") or "").strip() == who),
                               ("Seen_By_Person", str(row.get("Seen_By_Person")) == "1"),
                               ("Human_Verification_Status", row.get("Human_Verification_Status") == want)) if not ok]
        if bad:
            stop("GATE_ROW_MISMATCH", "관문 줄이 답이나 제안과 다릅니다: %s" % ", ".join(bad)); continue
        (geo if part == "GEOMETRY" else idn).append(row)
    return geo, idn, other, stops


def run_route(a):
    with io.open(a.proposals, encoding="utf-8") as fh:
        proposals = json.load(fh)["P"]
    gids = {r["Proposal_ID"] for r in load(os.path.join(a.geometry, "geometry_proposal.csv"))}
    import identity_proposer as IP
    iids = {r["Proposal_ID"] for r in load(os.path.join(a.identity, IP.PROPOSALS))}
    names = None
    if a.reviewers:
        import make_plan as MP
        _r, names = MP.load_reviewers(a.reviewers)
    renames = {}
    for spec in a.rename or []:
        old, sep, new = spec.partition("=")
        if not sep or not old.strip() or not new.strip():
            raise SystemExit("--rename은 친이름=적을이름 꼴입니다: %r" % spec)
        renames[old.strip()] = new.strip()
    geo, idn, other, stops = route(load(a.answers), proposals, gids, iids, names, renames)
    if stops:
        for s in stops:
            print("멈춤 %s — %s: %s" % s)
        print("멈춘 줄이 있어 아무것도 쓰지 않았습니다.")
        return 1
    os.makedirs(a.out, exist_ok=True)
    write(os.path.join(a.out, "geometry_answers.csv"), GEOMETRY_COLUMNS, geo)
    write(os.path.join(a.out, "identity_answers.csv"), IDENTITY_COLUMNS, idn)
    write(os.path.join(a.out, "not_accepted.csv"), ("Proposal_ID", "Part", "Answer", "Verified_By", "Note"), other)
    print("기하 %d · 정체 %d · 받지 않음(고칠 곳·보류) %d -> %s" % (len(geo), len(idn), len(other), a.out))
    return 0


# ---------------------------------------------------------------- merge
def merge_plan(run, geometry, identity, regions):
    """[(대상, 원본, 붙일 줄들, 대상 열)], [(대상 그림, 원본 그림)], 멈춤 [(대상, 코드, 사유)]."""
    import geometry_proposer as GP
    import identity_proposer as IP
    seg = os.path.join(run, "seg")
    pairs = [(os.path.join(seg, "geometry600", "geometry_proposal.csv"), os.path.join(geometry, "geometry_proposal.csv"),
              "Proposal_ID"),
             (os.path.join(seg, "geometry600", GP.REFUSED), os.path.join(geometry, GP.REFUSED), "Proposal_ID"),
             (os.path.join(seg, "identity600", IP.PROPOSALS), os.path.join(identity, IP.PROPOSALS), "Proposal_ID"),
             (os.path.join(seg, "regions600", "panel_regions_600.csv"), regions, None)]
    plan, stops = [], []
    for target, source, key in pairs:
        new = load(source)
        if not new:
            continue
        if os.path.islink(target) or not os.path.isfile(target):
            stops.append((target, "TARGET_NOT_A_FILE", "붙일 파일이 보통 파일이 아닙니다")); continue
        cols = header(target)
        # 대상에 없는 열은 새 줄이 모두 비워 둘 때만 두고 갑니다 - 제안기가 나중에 늘린 열(결정 칸 등)은
        # 제안 줄에서 비어 있고, 옛 대상 파일에는 없습니다(2026-10-17 run2). 값이 하나라도 있으면 멈춥니다:
        # 그 값이 조용히 버려집니다.
        extra = [c for c in new[0] if c not in cols]
        filled = [c for c in extra if any((r.get(c) or "").strip() for r in new)]
        if filled:
            stops.append((target, "COLUMNS_DIFFER", "대상에 없는 열(값이 있음): %s" % ", ".join(filled))); continue
        ident = (lambda r: r[key]) if key else (lambda r: "%s__p%s" % (r["Draft_ID"], r["Panel_Index"]))
        have = {ident(r) for r in load(target)}
        dup = sorted({ident(r) for r in new} & have)
        if dup:
            stops.append((target, "ALREADY_THERE", "이미 있는 패널: %s" % ", ".join(dup[:5]))); continue
        plan.append((target, source, new, cols))
    pictures = []
    for src_dir, dst_dir in ((geometry, os.path.join(seg, "geometry600")), (identity, os.path.join(seg, "identity600"))):
        for f in sorted(os.listdir(src_dir)) if os.path.isdir(src_dir) else []:
            if not f.endswith(".png"):
                continue
            src, dst = os.path.join(src_dir, f), os.path.join(dst_dir, f)
            if os.path.lexists(dst):
                with io.open(src, "rb") as a_, io.open(dst, "rb") as b_:
                    if a_.read() != b_.read():
                        stops.append((dst, "OVERLAY_EXISTS", "같은 이름의 다른 그림이 있습니다"))
                continue
            pictures.append((dst, src))
    return plan, pictures, stops


def merge(run, geometry, identity, regions, when, write_it=False):
    plan, pictures, stops = merge_plan(run, geometry, identity, regions)
    for target, _src, _new, _cols in plan:
        backup = "%s.before_merge_%s" % (target, when)
        if os.path.lexists(backup):
            stops.append((target, "BACKUP_EXISTS", "%s가 이미 있습니다" % backup))
    if stops or not write_it:
        return plan, pictures, stops
    for target, _src, new, cols in plan:
        shutil.copy2(target, "%s.before_merge_%s" % (target, when))
        write(target, cols, load(target) + new)
    for dst, src in pictures:
        shutil.copy2(src, dst)
    return plan, pictures, stops


def run_merge(a):
    plan, pictures, stops = merge(a.run, a.geometry, a.identity, a.regions, a.when, a.write)
    for target, _src, new, _cols in plan:
        print("붙임 %s: %d줄" % (os.path.relpath(target, a.run), len(new)))
    print("그림 %d장" % len(pictures))
    for s in stops:
        print("멈춤 %s — %s: %s" % s)
    if stops:
        print("멈춘 것이 있어 아무것도 쓰지 않았습니다.")
        return 1
    print("붙였습니다 (백업 *.before_merge_%s)." % a.when if a.write else "무엇을 붙일지만 보였습니다 (--write로 붙임).")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route")
    r.add_argument("--answers", required=True); r.add_argument("--proposals", required=True)
    r.add_argument("--geometry", required=True); r.add_argument("--identity", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--reviewers", help="make_plan의 등록부 JSON - 이름이 거기 있어야 함")
    r.add_argument("--rename", action="append", metavar="OLD=NEW", help="사람이 정한 이름 고침 (여러 번)")
    m = sub.add_parser("merge")
    m.add_argument("--run", required=True); m.add_argument("--geometry", required=True)
    m.add_argument("--identity", required=True); m.add_argument("--regions", required=True)
    m.add_argument("--when", required=True); m.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    return run_route(a) if a.cmd == "route" else run_merge(a)


if __name__ == "__main__":
    sys.exit(main())
