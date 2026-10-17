# -*- coding: utf-8 -*-
"""축·계열 확인 페이지의 답을 관문으로 나누고, 새 제안을 런에 붙이는 결정들.

    python3 test_route_axis_series.py     # exit 0 = all scenarios pass
"""
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _blind_ocr():
    """tesseract가 있든 없든 같은 결과가 나오게: 아무 글자도 읽지 않는 pytesseract.

    이 실행기들이 볼 일은 제안을 어디에 어떻게 적는가이지 글자를 읽는가가 아닙니다. 진짜
    tesseract가 있는 작업과 없는 작업에서 시나리오가 갈리면, 같은 수가 두 뜻이 됩니다."""
    import types
    fake = types.ModuleType("pytesseract")

    class Output(object):
        DICT = "dict"
    fake.Output = Output
    fake.image_to_data = lambda *a, **k: {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
    sys.modules["pytesseract"] = fake


_blind_ocr()

from PIL import Image, ImageDraw                                 # noqa: E402

import route_axis_series as RT                                   # noqa: E402
import propose_run as PR                                         # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def write_csv(path, rows, cols=None):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols or list(rows[0]), extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


PROPS = {"D1__p1": {"geo": {"verdict": "CONFIRMED"}, "idn": {"verdict": "CONFIRMED"}},
         "D1__p2": {"geo": {"verdict": "CONFIRMED"}, "idn": {"verdict": "REJECTED"}}}
IDS = {"D1__p1", "D1__p2"}


def gate_row(pid, status="CONFIRMED", who="MY", seen="1"):
    return json.dumps({"Proposal_ID": pid, "Human_Verification_Status": status, "Verified_By": who,
                       "Seen_By_Person": seen, "Note": "n"})


def ans(pid="D1__p1", part="GEOMETRY", answer="ACCEPT", who="MY", seen="1", gate=None, note=""):
    if gate is None:
        gate = gate_row(pid) if answer == "ACCEPT" else ""
    return {"Proposal_ID": pid, "Part": part, "Answer": answer, "Verified_By": who, "Seen_By_Person": seen,
            "Note": note, "Gate_Row": gate}


def codes(rows):
    return [s[1] for s in RT.route(rows, PROPS, IDS, IDS)[3]]


print("관문 답의 열")
check("기하 답의 열은 geometry_page.js의 CSV_COLUMNS", RT.GEOMETRY_COLUMNS[:2] == ["Proposal_ID", "Human_Verification_Status"]
      and "Confirmed_Tick_Values" in RT.GEOMETRY_COLUMNS and "Drawn_Frame" in RT.GEOMETRY_COLUMNS, RT.GEOMETRY_COLUMNS)
check("정체 답의 열은 identity_page.js의 CSV_COLUMNS", "Read_Route" in RT.IDENTITY_COLUMNS
      and "Series" in RT.IDENTITY_COLUMNS and RT.IDENTITY_COLUMNS[0] == "Proposal_ID", RT.IDENTITY_COLUMNS)

print()
print("나누기")
rows = [ans(), ans(part="IDENTITY"), ans("D1__p2", "IDENTITY", gate=gate_row("D1__p2", "REJECTED")),
        ans("D1__p2", "GEOMETRY", "FIX", note="맨 아래 눈금은 20")]
geo, idn, other, stops = RT.route(rows, PROPS, IDS, IDS)
check("제안대로는 관문 줄로, 부분별로", not stops and [r["Proposal_ID"] for r in geo] == ["D1__p1"]
      and [(r["Proposal_ID"], r["Human_Verification_Status"]) for r in idn] == [("D1__p1", "CONFIRMED"), ("D1__p2", "REJECTED")],
      (stops, geo, idn))
check("고칠 곳은 메모와 함께 받지 않은 줄로", other == [{"Proposal_ID": "D1__p2", "Part": "GEOMETRY", "Answer": "FIX",
                                             "Verified_By": "MY", "Note": "맨 아래 눈금은 20"}], other)
# REVERT: 보았다는 말을 보지 않는다. 열지 않은 카드의 줄이 사람이 본 줄로 적힙니다.
check("직접 봤다고 하지 않은 답은 멈춤", codes([ans(seen="")]) == ["NOT_SEEN"])
# REVERT: 이름을 보지 않는다.
check("이름 없는 답은 멈춤", codes([ans(who=" ")]) == ["NO_REVIEWER"])
# REVERT: 같은 패널·부분의 답 둘을 받는다. 어느 쪽이 사람의 마지막 말인지 모릅니다.
check("같은 패널·부분의 답이 둘이면 멈춤", codes([ans(), ans()]) == ["DUPLICATE"])
check("제안 파일에 없는 패널은 멈춤", codes([ans("D9__p1")]) == ["UNKNOWN_PANEL"])
# REVERT: 관문이 받을 제안 CSV에 있는지 보지 않는다. 관문에서야 '모르는 제안'으로 떨어집니다.
check("관문이 받을 제안 CSV에 없는 패널은 멈춤", [s[1] for s in RT.route([ans()], PROPS, set(), IDS)[3]] == ["NOT_IN_PROPOSALS"])
check("부분 이름이 아니면 멈춤", codes([ans(part="AXES")]) == ["BAD_PART"])
check("답 이름이 아니면 멈춤", codes([ans(answer="YES", gate="")]) == ["BAD_ANSWER"])
# REVERT: 관문 줄 없는 제안대로를 받는다.
check("관문 줄 없는 제안대로는 멈춤", codes([ans(gate="")]) == ["GATE_ROW_MISSING"])
check("읽을 수 없는 관문 줄은 멈춤", codes([ans(gate="{not json")]) == ["GATE_ROW_BROKEN"])
# REVERT: 고칠 곳·보류에 붙은 관문 줄을 둔다. 손댄 답 파일에서 그 줄이 관문으로 갈 수 있습니다.
check("고칠 곳·보류에 관문 줄이 붙어 있으면 멈춤", codes([ans(answer="HOLD", gate=gate_row("D1__p1"))]) == ["GATE_ROW_ON_NON_ACCEPT"])
# REVERT: 관문 줄의 판정을 제안과 대 보지 않는다. '읽지 않는다' 제안이 CONFIRMED로 적힙니다.
check("관문 줄의 판정이 제안의 판정과 다르면 멈춤",
      codes([ans("D1__p2", "IDENTITY", gate=gate_row("D1__p2", "CONFIRMED"))]) == ["GATE_ROW_MISMATCH"])
# REVERT: 관문 줄의 이름을 답의 이름과 대 보지 않는다.
check("관문 줄의 보신 분이 답의 보신 분과 다르면 멈춤", codes([ans(gate=gate_row("D1__p1", who="OTHER"))]) == ["GATE_ROW_MISMATCH"])
check("관문 줄이 다른 패널의 것이면 멈춤", codes([ans(gate=gate_row("D1__p2"))]) == ["GATE_ROW_MISMATCH"])
check("관문 줄의 목격이 1이 아니면 멈춤", codes([ans(gate=gate_row("D1__p1", seen="0"))]) == ["GATE_ROW_MISMATCH"])

print()
print("이름 (등록부, 사람이 정한 고침)")
NAMES = {"minyeop": "minyeop"}
TYPO = lambda pid="D1__p1", part="GEOMETRY", answer="ACCEPT": ans(pid, part, answer, who="miyeop",
                                                                  gate=gate_row(pid, who="miyeop") if answer == "ACCEPT" else "")
# REVERT: 등록부를 보지 않는다. 오타 이름이 기록에 사람 하나를 더 만듭니다(run2 2026-10-17의 'miyeop').
check("등록부에 없는 이름은 멈춤", [s[1] for s in RT.route([TYPO()], PROPS, IDS, IDS, NAMES)[3]] == ["UNREGISTERED_REVIEWER"])
check("등록부의 이름은 대소문자와 관계없이", not RT.route([ans(who="Minyeop", gate=gate_row("D1__p1", who="Minyeop"))],
                                                  PROPS, IDS, IDS, NAMES)[3])
check("등록부를 주지 않으면 이름을 대 보지 않음", not RT.route([TYPO()], PROPS, IDS, IDS)[3])
geo, idn, other, stops = RT.route([TYPO(), TYPO("D1__p2", "GEOMETRY", "HOLD")], PROPS, IDS, IDS, NAMES, {"miyeop": "minyeop"})
# REVERT: 이름 고침을 관문 줄에 옮기지 않는다. 답과 관문 줄의 이름이 어긋나 멈춥니다.
check("이름 고침은 답과 관문 줄에 함께, 관문 줄의 Note에 남는다", not stops and geo[0]["Verified_By"] == "minyeop"
      and geo[0]["Note"].startswith("n | ") and "'miyeop' → 'minyeop'" in geo[0]["Note"], (stops, geo))
check("받지 않은 줄의 이름도 고치고 메모에 남긴다", other and other[0]["Verified_By"] == "minyeop"
      and "'miyeop' → 'minyeop'" in other[0]["Note"], other)
check("이름 고침은 그 이름의 줄에만", RT.route([ans()], PROPS, IDS, IDS, None, {"miyeop": "minyeop"})[0][0]["Verified_By"] == "MY")
# REVERT: 관문 줄의 이름이 무엇이든 고친다. 다른 사람의 관문 줄이 고친 이름으로 적힙니다.
check("관문 줄의 이름이 친 이름과 다르면 고치지 않고 멈춤",
      [s[1] for s in RT.route([ans(who="miyeop", gate=gate_row("D1__p1", who="OTHER"))], PROPS, IDS, IDS, None,
                              {"miyeop": "minyeop"})[3]] == ["GATE_ROW_MISMATCH"])

print()
print("쓰기와 관문")
TMP = tempfile.mkdtemp(prefix="fdt-route-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "seg", "r600"))
im = Image.new("RGB", (400, 320), "white")
d = ImageDraw.Draw(im)
d.rectangle((60, 30, 360, 270), outline="black")
for k in range(11):
    y = 30 + k * 24
    d.line((55, y, 59, y), fill="black")
for g in range(5):
    cx = 110 + 50 * g
    d.rectangle((cx - 9, 270 - 60 - 20 * g, cx + 9, 269), outline="black")
im.save(os.path.join(RUN, "seg", "r600", "D1_600.png"))
REG = os.path.join(RUN, "seg", "r600", "panel_regions_600.csv")
write_csv(REG, [{"Draft_ID": "D1", "Panel_Index": "1", "Mark_Type": "BAR", "Mark_Count": "5",
                 "Raster_600": "seg/r600/D1_600.png", "Raster_600_SHA256": "x", "Region_600": "0,0,400,320"}])
write_csv(os.path.join(RUN, "figure_intake_draft.csv"), [{"Draft_ID": "D1", "Caption_Text": ""}])
GDIR, IDIR = os.path.join(RUN, "seg", "g_new"), os.path.join(RUN, "seg", "i_new")
PR.geometry_batch(RUN, REG, GDIR)
PR.identity_batch(RUN, REG, os.path.join(GDIR, "geometry_proposal.csv"), IDIR)
g1 = PR.load(os.path.join(GDIR, "geometry_proposal.csv"))[0]
ticks = g1["Y_Tick_Pixels"].split(";")
PJ = os.path.join(TMP, "proposals.json")
with io.open(PJ, "w", encoding="utf-8") as fh:
    json.dump({"P": {"D1__p1": {"geo": {"verdict": "CONFIRMED"}, "idn": {"verdict": "REJECTED"}}}}, fh)
geo_row = {"Proposal_ID": "D1__p1", "Human_Verification_Status": "CONFIRMED", "Y_Tick_Top_Value": "100",
           "Y_Tick_Bottom_Value": "0", "Confirmed_Tick_Values": "100@%s;0@%s" % (ticks[0], ticks[-1]),
           "Y_Axis_Shared_With": "", "Verified_By": "MY", "Seen_By_Person": "1", "Value_Source": "TYPED",
           "Drawn_Frame": "", "Note": "[축·계열 확인 페이지] 제안대로"}
idn_row = {"Proposal_ID": "D1__p1", "Human_Verification_Status": "REJECTED", "Verified_By": "MY", "Seen_By_Person": "1",
           "Note": "읽지 않는다"}
ANS = os.path.join(TMP, "answers.csv")
write_csv(ANS, [ans(gate=json.dumps(geo_row)), ans(part="IDENTITY", gate=json.dumps(idn_row))], list(RT.ANSWER_COLUMNS))
OUT = os.path.join(TMP, "routed")
rc = RT.main(["route", "--answers", ANS, "--proposals", PJ, "--geometry", GDIR, "--identity", IDIR, "--out", OUT])
check("나눈 답 파일 셋을 쓴다", rc == 0 and all(os.path.isfile(os.path.join(OUT, f)) for f in
                                          ("geometry_answers.csv", "identity_answers.csv", "not_accepted.csv")), rc)
p = subprocess.run([sys.executable, os.path.join(HERE, "record_geometry.py"), "--proposals", GDIR,
                    "--answers", os.path.join(OUT, "geometry_answers.csv"), "--when", "2026-10-17"],
                   capture_output=True, text=True)
dec = PR.load(os.path.join(GDIR, "geometry_decisions.csv"))
check("나눈 기하 답을 record_geometry가 그대로 받는다", p.returncode == 0 and len(dec) == 1
      and dec[0]["Human_Verification_Status"] == "CONFIRMED" and dec[0]["Verified_By"] == "MY", (p.stdout[-400:], p.stderr[-400:]))
p = subprocess.run([sys.executable, os.path.join(HERE, "record_identity.py"), "--proposals", IDIR,
                    "--answers", os.path.join(OUT, "identity_answers.csv"), "--when", "2026-10-17"],
                   capture_output=True, text=True)
idec = PR.load(os.path.join(IDIR, "identity_decisions.csv"))
check("나눈 정체 답을 record_identity가 그대로 받는다", p.returncode == 0 and len(idec) == 1
      and idec[0]["Human_Verification_Status"] == "REJECTED", (p.stdout[-400:], p.stderr[-400:]))
REVS = os.path.join(TMP, "reviewers.json")
with io.open(REVS, "w", encoding="utf-8") as fh:
    json.dump({"reviewers": [{"reviewer_id": "minyeop", "name": "M", "record_type": "HUMAN"}], "names": {"minyeop": "minyeop"}}, fh)
ANS2 = os.path.join(TMP, "answers_typo.csv")
write_csv(ANS2, [ans(who="miyeop", gate=json.dumps(dict(geo_row, Verified_By="miyeop")))], list(RT.ANSWER_COLUMNS))
OUT3 = os.path.join(TMP, "routed_named")
base = ["route", "--answers", ANS2, "--proposals", PJ, "--geometry", GDIR, "--identity", IDIR, "--out", OUT3, "--reviewers", REVS]
rc = RT.main(base)
check("명령: 등록부에 없는 이름이면 아무것도 쓰지 않는다", rc == 1 and not os.path.exists(OUT3), rc)
rc = RT.main(base + ["--rename", "miyeop=minyeop"])
p = subprocess.run([sys.executable, os.path.join(HERE, "record_geometry.py"), "--proposals", GDIR,
                    "--answers", os.path.join(OUT3, "geometry_answers.csv"), "--when", "2026-10-17",
                    "--out", os.path.join(TMP, "geometry_decisions_named.csv")], capture_output=True, text=True)
dn = PR.load(os.path.join(TMP, "geometry_decisions_named.csv"))
check("명령: 고친 이름으로 나눈 답을 record_geometry가 받는다", rc == 0 and p.returncode == 0 and dn
      and dn[0]["Verified_By"] == "minyeop" and "'miyeop' → 'minyeop'" in dn[0]["Note"], (rc, p.stdout[-300:], p.stderr[-300:]))
try:
    RT.main(base + ["--rename", "miyeop"])
    check("명령: 꼴이 틀린 --rename은 멈춘다", False)
except SystemExit:
    check("명령: 꼴이 틀린 --rename은 멈춘다", True)
BAD = os.path.join(TMP, "answers_bad.csv")
write_csv(BAD, [ans(gate=json.dumps(geo_row)), ans(part="IDENTITY", seen="")], list(RT.ANSWER_COLUMNS))
OUT2 = os.path.join(TMP, "routed_bad")
rc = RT.main(["route", "--answers", BAD, "--proposals", PJ, "--geometry", GDIR, "--identity", IDIR, "--out", OUT2])
# REVERT: 멈춘 줄이 있어도 나머지를 쓴다. 고쳐서 다시 낸 답 파일이 반쪽짜리 위에 얹힙니다.
check("한 줄이라도 멈추면 아무것도 쓰지 않는다", rc == 1 and not os.path.exists(OUT2), rc)

print()
print("런에 붙이기")
SEG = os.path.join(RUN, "seg")
for d_ in ("geometry600", "identity600", "regions600"):
    os.makedirs(os.path.join(SEG, d_))
import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402
gcols = list(g1)
write_csv(os.path.join(SEG, "geometry600", "geometry_proposal.csv"), [dict(g1, Proposal_ID="OLD__p1")], gcols)
write_csv(os.path.join(SEG, "geometry600", GP.REFUSED), [], list(GP.REFUSED_COLUMNS))
i1 = PR.load(os.path.join(IDIR, IP.PROPOSALS))[0]
write_csv(os.path.join(SEG, "identity600", IP.PROPOSALS), [dict(i1, Proposal_ID="OLD__p1")], list(i1))
r1 = PR.load(REG)[0]
write_csv(os.path.join(SEG, "regions600", "panel_regions_600.csv"), [dict(r1, Draft_ID="OLD")], list(r1) + ["Verified_By"])
before = {f: io.open(os.path.join(SEG, f), encoding="utf-8").read()
          for f in ("geometry600/geometry_proposal.csv", "identity600/identity_proposal.csv", "regions600/panel_regions_600.csv")}
plan, pics, stops = RT.merge(RUN, GDIR, IDIR, REG, "2026-10-17")
# REVERT: 기본이 붙이기. 무엇을 붙일지 보지 않고 런이 바뀝니다.
check("기본은 무엇을 붙일지만 보인다", not stops and len(plan) == 3 and len(pics) == 2
      and all(io.open(os.path.join(SEG, f), encoding="utf-8").read() == t for f, t in before.items()), (stops, plan))
plan, pics, stops = RT.merge(RUN, GDIR, IDIR, REG, "2026-10-17", write_it=True)
gp = PR.load(os.path.join(SEG, "geometry600", "geometry_proposal.csv"))
rg = PR.load(os.path.join(SEG, "regions600", "panel_regions_600.csv"))
check("--write: 제안·영역 행을 붙이고 그림을 옮긴다", not stops and [r["Proposal_ID"] for r in gp] == ["OLD__p1", "D1__p1"]
      and [r["Draft_ID"] for r in rg] == ["OLD", "D1"]
      and os.path.isfile(os.path.join(SEG, "geometry600", "D1__p1.png"))
      and os.path.isfile(os.path.join(SEG, "identity600", "D1__p1.png")), (stops, gp))
# REVERT: 백업을 남기지 않는다.
check("붙이기 전 파일은 before_merge_<날>로 남는다",
      io.open(os.path.join(SEG, "geometry600", "geometry_proposal.csv.before_merge_2026-10-17"), encoding="utf-8").read()
      == before["geometry600/geometry_proposal.csv"])
check("대상에만 있는 열은 빈칸으로", rg[1].get("Verified_By", None) == "", rg[1])
plan, pics, stops = RT.merge(RUN, GDIR, IDIR, REG, "2026-10-18")
# REVERT: 이미 있는 패널을 다시 붙인다. 같은 Proposal_ID가 둘이면 관문이 어느 것에 답하는지 모릅니다.
check("이미 있는 패널은 멈춘다", sorted(set(s[1] for s in stops)) == ["ALREADY_THERE"], stops)

RUN2 = os.path.join(TMP, "run2")
shutil.copytree(os.path.join(RUN, "seg", "r600"), os.path.join(RUN2, "seg", "r600"))
for d_ in ("geometry600", "identity600", "regions600"):
    os.makedirs(os.path.join(RUN2, "seg", d_))
write_csv(os.path.join(RUN2, "seg", "geometry600", "geometry_proposal.csv"), [dict(g1, Proposal_ID="OLD__p1")], gcols[:-1])
write_csv(os.path.join(RUN2, "seg", "geometry600", GP.REFUSED), [], list(GP.REFUSED_COLUMNS))
write_csv(os.path.join(RUN2, "seg", "identity600", IP.PROPOSALS), [dict(i1, Proposal_ID="OLD__p1")], list(i1))
write_csv(os.path.join(RUN2, "seg", "regions600", "panel_regions_600.csv"), [dict(r1, Draft_ID="OLD")], list(r1))
_p, _q, stops = RT.merge(RUN2, GDIR, IDIR, REG, "2026-10-17")
check("대상에 없는 열이 새 줄에서 모두 비어 있으면 두고 간다", not stops and gcols[-1] not in _p[0][3]
      and not any((r.get(gcols[-1]) or "") for r in PR.load(os.path.join(GDIR, "geometry_proposal.csv"))), (stops, gcols[-1]))
GDIR2 = os.path.join(TMP, "g_filled")
shutil.copytree(GDIR, GDIR2)
filled = [dict(r, **{gcols[-1]: "x"}) for r in PR.load(os.path.join(GDIR, "geometry_proposal.csv"))]
write_csv(os.path.join(GDIR2, "geometry_proposal.csv"), filled, gcols)
_p, _q, stops = RT.merge(RUN2, GDIR2, IDIR, REG, "2026-10-17")
# REVERT: 대상에 없는 열을 보지 않는다. 새 제안의 그 열의 값이 조용히 버려집니다.
check("대상에 없는 열에 값이 있으면 멈춘다", [s[1] for s in stops] == ["COLUMNS_DIFFER"] and gcols[-1] in stops[0][2], stops)
with io.open(os.path.join(RUN2, "seg", "identity600", "D1__p1.png"), "wb") as fh:
    fh.write(b"other picture")
write_csv(os.path.join(RUN2, "seg", "geometry600", "geometry_proposal.csv"), [dict(g1, Proposal_ID="OLD__p1")], gcols)
_p, _q, stops = RT.merge(RUN2, GDIR, IDIR, REG, "2026-10-17")
# REVERT: 같은 이름의 다른 그림을 덮는다. 다른 제안의 오버레이가 사라집니다.
check("같은 이름의 다른 그림이 있으면 멈춘다", [s[1] for s in stops] == ["OVERLAY_EXISTS"], stops)
shutil.copy2(os.path.join(IDIR, "D1__p1.png"), os.path.join(RUN2, "seg", "identity600", "D1__p1.png"))
_p, pics, stops = RT.merge(RUN2, GDIR, IDIR, REG, "2026-10-17")
check("같은 그림이 이미 있으면 옮기지 않고 넘어간다", not stops and len(pics) == 1, (stops, pics))
bk = os.path.join(RUN2, "seg", "regions600", "panel_regions_600.csv.before_merge_2026-10-17")
shutil.copy2(os.path.join(RUN2, "seg", "regions600", "panel_regions_600.csv"), bk)
_p, _q, stops = RT.merge(RUN2, GDIR, IDIR, REG, "2026-10-17", write_it=True)
# REVERT: 이미 있는 백업을 덮는다. 그 날 앞서 붙이기 전의 파일이 사라집니다.
check("그 날의 백업이 이미 있으면 멈추고 아무것도 쓰지 않는다", [s[1] for s in stops] == ["BACKUP_EXISTS"]
      and len(PR.load(os.path.join(RUN2, "seg", "regions600", "panel_regions_600.csv"))) == 1, stops)
os.remove(bk)
reg_target = os.path.join(RUN2, "seg", "regions600", "panel_regions_600.csv")
os.replace(reg_target, reg_target + ".real")
os.symlink(reg_target + ".real", reg_target)
_p, _q, stops = RT.merge(RUN2, GDIR, IDIR, REG, "2026-10-17")
# REVERT: 링크인 대상을 따라 쓴다. 사본 점검의 링크 트리를 따라 진짜 런에 씁니다.
check("링크인 대상은 멈춘다", [s[1] for s in stops] == ["TARGET_NOT_A_FILE"], stops)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    sys.exit(1)
print("all scenarios passed")
