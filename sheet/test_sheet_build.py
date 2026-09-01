# -*- coding: utf-8 -*-
"""The builder, checked against an intake anyone can make.

`test_sheet_html.py` asserts on the real corpus - 102 cards, the four
recovered pids, pid 563's FIG6 - and those are worth keeping. They are also
unrunnable anywhere but the one machine that holds publisher PDFs, which left
the BUILDER itself with no test at all: every change to it was checked by
looking at the output of the only run that could be produced.

This builds from `make_fixture.py` and asserts what must hold for any corpus.
"""
import base64
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_fixture

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % detail))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-sheet-")
FX = make_fixture.write(os.path.join(TMP, "fx"))
SHEET = os.path.join(TMP, "sheet.html")
ENV = dict(os.environ, FDT_DRAFT=FX["draft"], FDT_WORKLIST=FX["worklist"],
           FDT_AUDIT=FX["audit"], FDT_SHEET=SHEET, FDT_PATH_REWRITE="",
           PYTHONPYCACHEPREFIX=os.path.join(TMP, "pyc"))
RUN = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                     capture_output=True, text=True, env=ENV, cwd=HERE)
check("빌더가 공개 픽스처만으로 돌아간다", RUN.returncode == 0,
      (RUN.stderr or "")[-400:])
if RUN.returncode != 0:
    print("%d/%d" % (N[0] - len(FAIL), N[0]))
    raise SystemExit(1)

S = io.open(SHEET, encoding="utf-8").read()
DRAFT = list(csv.DictReader(io.open(
    os.path.join(FX["draft"], "figure_intake_draft.csv"), encoding="utf-8")))
WORK = list(csv.DictReader(io.open(FX["worklist"], encoding="utf-8")))
ROWS = json.loads(re.search(r"const ROWS=(\[.*?\]);const BUILD_ID=",
                            S, re.S).group(1))
FIGS = re.findall(r"<div class='fig([^']*)' data-id='([^']+)' "
                  r"data-fp='([^']*)'>(.*?)(?=<div class='fig'|</div></div>)",
                  S, re.S)
BY_ID = {f[1]: f for f in FIGS}

# ---------------------------------------------------------------- 뼈대
check("워크리스트의 모든 pid가 카드를 가진다",
      sorted(re.findall(r"<h2>pid (\d+) ·", S), key=int)
      == sorted((w["pid"] for w in WORK), key=int))
check("카드는 P1 먼저, 그다음 pid 순서",
      re.findall(r"<h2>pid (\d+) ·", S)
      == [w["pid"] for w in sorted(WORK, key=lambda r: (r["priority"],
                                                        int(r["pid"])))])
check("초안의 모든 행이 정확히 한 번씩 나온다",
      sorted(BY_ID) == sorted(d["Draft_ID"] for d in DRAFT),
      "%d개 블록 / %d개 행" % (len(BY_ID), len(DRAFT)))
check("ROWS가 초안과 같은 행들을 같은 수만큼 담는다",
      [r["Draft_ID"] for r in ROWS] == [d["Draft_ID"] for d in DRAFT])
check("모든 행에 지문이 있다",
      all(len(r["Row_Fingerprint"]) >= 8 for r in ROWS))
check("빌드 ID가 페이지에 있다", bool(re.search(r"const BUILD_ID=\"[^\"]+\"", S)))

# ------------------------------------------------- 빈칸은 0이 아니다
_empty_card = re.search(r"<h2>pid 14 ·.*?(?=<div class='doc'>|<script)", S, re.S)
check("행이 0인 문서는 '없다'가 아니라 '못 찾았다'라고 말한다",
      "캡션 후보가 0행입니다" in (_empty_card.group(0) if _empty_card else ""))
check("쪽수가 빈 문서에 0쪽이라고 쓰지 않는다",
      "0쪽" not in S and "쪽수 없음" in S)

# ------------------------------------------------------ 막힘과 열림
_blocked = {d["Draft_ID"] for d in DRAFT
            if d["Crop_Quality_Status"] in ("THIN_CROP", "NO_CROP")}
for did in sorted(_blocked):
    check("%s는 계수 불가이므로 입력이 잠겨 있다" % did,
          "disabled" in BY_ID[did][3])
_open = [r["Draft_ID"] for r in ROWS if r["Count_Blocked"] == "0"]
check("입력 가능한 행에는 잠기지 않은 숫자칸이 있다",
      all("disabled" not in BY_ID[d][3] and "type='number'" in BY_ID[d][3]
          for d in _open), "%s" % _open)
check("막힌 행은 이유를 함께 보여준다",
      all("입력을 막았습니다" in BY_ID[d][3]
          for d in BY_ID if d not in _open))

# -------------------------------------------- 같은 그림, 같은 이미지
def _img(did):
    m = re.search(r"<img src='data:image/jpeg;base64,([^']+)'", BY_ID[did][3])
    return base64.b64decode(m.group(1)) if m else None


check("같은 크롭을 쓰는 두 행은 같은 이미지를 보여준다",
      _img("DOC_C_D001") == _img("DOC_C_D002") is not None)
check("서로 다른 크롭은 서로 다른 이미지다",
      _img("DOC_A_D001") != _img("DOC_A_D002"))
check("크롭이 없는 행은 이미지 대신 그 사실을 말한다",
      _img("DOC_B_D002") is None
      and "페이지 이미지 없음" in BY_ID["DOC_B_D002"][3])
check("바이트가 같은 크롭 두 행은 둘 다 막힌다",
      "disabled" in BY_ID["DOC_C_D001"][3]
      and "disabled" in BY_ID["DOC_C_D002"][3])

# ------------------------------------------------------------ 총계 없음
check("그림 총계를 지어내지 않는다",
      not re.search(r"그림 총\s*\d|총 그림\s*\d", S))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
