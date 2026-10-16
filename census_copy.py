# -*- coding: utf-8 -*-
"""답을 적기 전에, 적으면 무엇이 되는지 - 런의 사본에 관문으로 적고 계획서 점검을 앞뒤로.

    python3 census_copy.py --run RUN --routed ROUTED/ --when 2026-10-16 \
        --reviewers reviewers.json --out OUT/ [--pdf-root PDFS] \
        [--identity-dir seg/identity600] [--geometry-dir seg/geometry600] \
        [--no-file-check] [--placeholder-missing-crops]

`bundle_route.py`가 낸 관문 답 파일(ROUTED)을, 런을 링크로 비춘 사본(OUT/run_after)에
**관문 그대로** 적습니다(record_dispositions, record_errorbar, record_identity --replace,
record_geometry --replace). 그다음 원래 런(before)과 사본(after) 각각에 make_plan ->
compile_plan.validate_plan -> compile_plan + run_batch를 돌려 문제 코드를 모으고,
무엇이 줄고 늘었는지 compare.json에 적습니다. 원래 런의 파일은 하나도 바뀌지 않습니다 -
관문이 쓰는 파일만 사본에서 실제 파일이고, 나머지는 원래 런을 가리키는 링크입니다. 끝에
원래 런의 그 파일들 지문이 처음과 같은지 다시 봅니다(RUN_CHANGED이면 멈춤).

관문이 사본에서 거절한 답이 하나라도 있으면 점검을 돌리지 않고 거절을 적습니다:
그 답들은 반영할 때도 거절됩니다. 카드(identity·geometry)는 확정된 카드를 고치는 답이라
--replace로 적고, 처분·오차 정의는 --replace 없이 적습니다 - 이미 적힌 그림을 다시 정하는 답은
ALREADY_DECIDED로 드러나고, 덮어쓸지는 사람이 정합니다.

**진단입니다.** `--placeholder-missing-crops`는 크롭이 없는 컴퓨터(크롭 일부만 가진 작업
공간)에서 없는 크롭을 자리표시로 풀어 컴파일을 이어 가게 합니다. 그렇게 만든 매니페스트는
크롭 지문이 틀리고, 쓰지 않습니다. `--no-file-check`는 run_batch의 파일 검사를 끕니다. 반영
판단은 크롭과 PDF가 다 있는 곳에서 두 옵션 없이 다시 돌린 결과로 합니다.
"""
import argparse
import collections
import csv
import glob
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

GATE_FILES = {"dispositions": ("figure_disposition_answers.csv", "figure_dispositions.csv"),
              "errorbar": ("errorbar_answers.csv", "errorbar_decisions.csv"),
              "identity": ("identity_answers.csv", "identity_decisions.csv"),
              "geometry": ("geometry_answers.csv", "geometry_decisions.csv")}


def rd(path):
    return list(csv.DictReader(io.open(path, encoding="utf-8-sig"))) if os.path.exists(path) else []


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else ""


def snapshot(run, rels):
    """{상대 경로: sha256} - 관문이 쓰는 파일이 있는 폴더들의 모든 파일(하위 폴더 제외). 관문이 적는 파일 말고
    다른 파일을 그 폴더에 쓰더라도, 링크를 타고 런에 닿았으면 여기서 보입니다."""
    out = {}
    for d in sorted(set(os.path.dirname(os.path.normpath(r)) for r in rels)):
        here = os.path.join(run, d)
        if not os.path.isdir(here):
            continue
        for name in sorted(os.listdir(here)):
            p = os.path.join(here, name)
            if os.path.isfile(p):
                out[os.path.join(d, name)] = sha(p)
    return out


def link_tree(src, dst, real):
    """dst가 src를 링크로 비춥니다. `real`의 상대 경로(와 그 상위 폴더)만 실제 사본입니다 - 원래 런에
    있으면 복사하고, 없으면 만들어질 자리만 둡니다."""
    if os.path.exists(dst):
        raise SystemExit("%s가 이미 있습니다." % dst)
    os.makedirs(dst)
    real = set(os.path.normpath(r) for r in real)
    parents = set()
    for r in real:
        parts = r.split(os.sep)
        for i in range(1, len(parts)):
            parents.add(os.sep.join(parts[:i]))

    def walk(rel):
        here = os.path.join(src, rel) if rel else src
        for name in sorted(os.listdir(here)):
            r = os.path.join(rel, name) if rel else name
            if r in parents:
                os.makedirs(os.path.join(dst, r))
                walk(r)
            elif r in real:
                shutil.copy2(os.path.join(src, r), os.path.join(dst, r))
            else:
                os.symlink(os.path.join(src, r), os.path.join(dst, r))
    walk("")
    for p in parents:
        os.makedirs(os.path.join(dst, p), exist_ok=True)


def record_on_copy(after, routed, when, plans, gate_dirs, pdf_root=None, log=print):
    """관문 그대로 사본에 적습니다. ({관문: [적은 수, 거절 [(이름, 문제)]]})."""
    import record_dispositions as RD
    import record_errorbar as RE
    import record_geometry as RG
    import record_identity as RI
    done = {}
    for gate, (ans_name, rec_name) in GATE_FILES.items():
        rows = rd(os.path.join(routed, ans_name))
        if not rows:
            continue
        quiet = lambda *_a: None
        try:
            if gate == "dispositions":
                w, refused, _p = RD.record(after, plans, rows, when, out_path=os.path.join(after, rec_name), via="BUNDLE", log=quiet)
            elif gate == "errorbar":
                w, refused, _p = RE.record(after, rows, pdf_root, when, out_path=os.path.join(after, rec_name), via="BUNDLE", log=quiet)
            else:
                d = os.path.join(after, gate_dirs[gate])
                mod = RI if gate == "identity" else RG
                w, refused, _p = mod.record(d, rows, when, out_path=os.path.join(d, rec_name), replace=True, log=quiet)
        except Exception as exc:                                     # noqa: BLE001
            # 관문이 넘어진 것도 거절입니다. 그대로 올려 보내면 recorded.json이 없고,
            # 앞선 관문이 사본에 적은 것과 점검 앞의 결과만 남습니다.
            w, refused = [], [("(%s)" % gate, [("GATE_FAILED", "%s: %s" % (type(exc).__name__, exc))])]
        done[gate] = [len(w), [[n, [list(x) for x in ps]] for n, ps in refused]]
        log("%s: 적음 %d · 거절 %d" % (gate, len(w), len(refused)))
    return done


def census(fdt, run, out, reviewers, file_root, run_date, no_file_check=False, placeholder=False, log=print):
    """{publication: {plan_problems, manifest_problems, manifest_where, run_exit}}, plan_panels 행."""
    import compile_plan as CP
    orig = CP._resolve
    if placeholder:
        stand_in = os.path.join(file_root, "figure_intake_draft.csv")

        def _resolve(path, root):
            r = orig(path, root)
            return r if r is not None or not str(path).startswith("crops/") else stand_in
        CP._resolve = _resolve
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        plans = os.path.join(out, "plans")
        cmd = [sys.executable, os.path.join(fdt, "make_plan.py"), "--run", run, "--out", plans, "--crop-root", file_root,
               "--run-date", run_date]
        if reviewers:
            cmd += ["--reviewers", reviewers]
        q = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=out)
        if q.returncode:
            raise SystemExit("make_plan: %s" % q.stderr[-800:])
        res = {}
        for p in sorted(glob.glob(plans + "/plan_*.json")):
            pub = os.path.basename(p)[5:-5]
            plan = json.load(io.open(p, encoding="utf-8"))
            probs = CP.validate_plan(plan, file_root=file_root)
            r = {"plan_problems": dict(collections.Counter(x["check"] for x in probs))}
            if not probs:
                md, od = os.path.join(out, "man_" + pub), os.path.join(out, "out_" + pub)
                CP.compile_plan(plan, md, file_root=file_root, run_date=run_date)
                cmd = [sys.executable, os.path.join(fdt, "run_batch.py"), md, od, "--file-root", file_root]
                if no_file_check:
                    cmd.append("--no-file-check")
                q = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=fdt, env=env)
                r["run_exit"] = q.returncode
                rows = rd(os.path.join(od, "manifest_problems.csv"))
                r["manifest_problems"] = dict(collections.Counter(x["check"] for x in rows))
                r["manifest_where"] = sorted("%s@%s" % (x["check"], x["where"].split(":")[0]) for x in rows)
            res[pub] = r
        log("%s: 계획서 %d" % (os.path.basename(out), len(res)))
        return res, rd(os.path.join(plans, "plan_panels.csv"))
    finally:
        CP._resolve = orig


def compare(before, after, panels_before=(), panels_after=()):
    """무엇이 줄고 늘었는가 - 합계, 논문마다, 처분이 바뀐 패널."""
    def total(res, k):
        c = collections.Counter()
        for r in res.values():
            c.update(r.get(k) or {})
        return c
    cmp = {"total": {}, "by_pub": {}, "grew": {}, "panel_changes": {}}
    for k in ("plan_problems", "manifest_problems"):
        a, b = total(before, k), total(after, k)
        cmp["total"][k] = dict((c, [a[c], b[c]]) for c in sorted(set(a) | set(b)) if a[c] != b[c])
        cmp["total"][k + "_sum"] = [sum(a.values()), sum(b.values())]
        cmp["grew"][k] = dict((c, [a[c], b[c]]) for c in sorted(set(b)) if b[c] > a[c])
    for pub in sorted(set(before) | set(after)):
        x, y = before.get(pub, {}), after.get(pub, {})
        d = {}
        for k in ("plan_problems", "manifest_problems"):
            p, q = collections.Counter(x.get(k) or {}), collections.Counter(y.get(k) or {})
            dd = dict((c, [p[c], q[c]]) for c in sorted(set(p) | set(q)) if p[c] != q[c])
            if dd:
                d[k] = dd
        if x.get("run_exit") != y.get("run_exit"):
            d["run_exit"] = [x.get("run_exit"), y.get("run_exit")]
        if pub not in before or pub not in after:
            d["present"] = [pub in before, pub in after]
        if d:
            cmp["by_pub"][pub] = d
    pa = dict((r.get("Panel_ID"), r) for r in panels_before)
    pb = dict((r.get("Panel_ID"), r) for r in panels_after)
    for k in sorted(set(pa) | set(pb)):
        if k not in pa or k not in pb:
            cmp["panel_changes"][k] = {"present": [k in pa, k in pb]}
            continue
        ch = dict((c, [pa[k][c], pb[k].get(c)]) for c in pa[k] if pa[k][c] != pb[k].get(c))
        if ch:
            cmp["panel_changes"][k] = ch
    return cmp


def main(argv=None, census_fn=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--routed", required=True, help="bundle_route.py의 출력 폴더")
    ap.add_argument("--when", required=True, help="답을 정한 날 (관문의 --when)")
    ap.add_argument("--reviewers")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf-root")
    ap.add_argument("--file-root", help="크롭·래스터를 찾는 곳 (기본: RUN)")
    ap.add_argument("--identity-dir", default=os.path.join("seg", "identity600"))
    ap.add_argument("--geometry-dir", default=os.path.join("seg", "geometry600"))
    ap.add_argument("--no-file-check", action="store_true")
    ap.add_argument("--placeholder-missing-crops", action="store_true")
    a = ap.parse_args(argv)
    run, out = os.path.abspath(os.path.expanduser(a.run)), os.path.abspath(os.path.expanduser(a.out))
    file_root = os.path.abspath(a.file_root) if a.file_root else run
    if out == run or out.startswith(run + os.sep):
        raise SystemExit("출력 폴더가 런 안에 있습니다.")
    gate_dirs = {"identity": a.identity_dir, "geometry": a.geometry_dir}
    written = {"dispositions": GATE_FILES["dispositions"][1], "errorbar": GATE_FILES["errorbar"][1],
               "identity": os.path.join(a.identity_dir, GATE_FILES["identity"][1]),
               "geometry": os.path.join(a.geometry_dir, GATE_FILES["geometry"][1])}
    want = [g for g in GATE_FILES if rd(os.path.join(a.routed, GATE_FILES[g][0]))]
    if not want:
        raise SystemExit("%s에 관문 답 파일이 없습니다." % a.routed)
    if "errorbar" in want:
        # 점검 앞에 멈춥니다 - 점검 한 번이 몇 분이고, 이 둘이 없으면 관문이 적지 못합니다.
        import record_errorbar as RE
        if not a.pdf_root:
            raise SystemExit("오차 정의 답은 원문에서 다시 찾아야 합니다 - --pdf-root가 필요합니다.")
        if not os.path.isfile(os.path.join(run, RE.UNSTATED)):
            raise SystemExit("오차 정의 관문이 읽는 %s가 런에 없습니다." % RE.UNSTATED)
    guard = snapshot(run, written.values())
    os.makedirs(out)
    after = os.path.join(out, "run_after")
    link_tree(run, after, [written[g] for g in want])
    run_census = census_fn or (lambda r, o: census(HERE, r, o, a.reviewers, file_root, a.when, a.no_file_check,
                                                   a.placeholder_missing_crops))
    os.makedirs(os.path.join(out, "before"))
    before, pan_b = run_census(run, os.path.join(out, "before"))
    recorded = record_on_copy(after, a.routed, a.when, os.path.join(out, "before", "plans"), gate_dirs, a.pdf_root)
    json.dump(recorded, io.open(os.path.join(out, "recorded.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    now = snapshot(run, written.values())
    changed = sorted(k for k in set(guard) | set(now) if guard.get(k) != now.get(k))
    if changed:
        raise SystemExit("RUN_CHANGED: %s가 바뀌었습니다 - 사본이 아니라 런에 적혔습니다." % ", ".join(changed))
    refused = dict((g, r[1]) for g, r in recorded.items() if r[1])
    if refused:
        print("관문이 사본에서 거절한 답이 있습니다 - 점검을 돌리지 않습니다: %s" % json.dumps(refused, ensure_ascii=False)[:2000])
        return 1
    os.makedirs(os.path.join(out, "after"))
    after_res, pan_a = run_census(after, os.path.join(out, "after"))
    cmp = compare(before, after_res, pan_b, pan_a)
    for name, obj in (("census_before.json", before), ("census_after.json", after_res), ("compare.json", cmp)):
        json.dump(obj, io.open(os.path.join(out, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    t = cmp["total"]
    print("계획서 점검 문제 %d -> %d · 계획 단계 문제 %d -> %d · 늘어난 코드 %s" % (
        t["manifest_problems_sum"][0], t["manifest_problems_sum"][1], t["plan_problems_sum"][0], t["plan_problems_sum"][1],
        json.dumps(cmp["grew"]["manifest_problems"], ensure_ascii=False) or "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
