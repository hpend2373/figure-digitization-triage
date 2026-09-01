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

import paths as PATHS                                            # noqa: E402
PARTS = PATHS.parts_for(SHEET)
S = "\n".join(io.open(f, encoding="utf-8").read() for f in PARTS)
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
    m = re.search(r"<img class='thumb' src='data:image/jpeg;base64,([^']+)'",
                  BY_ID[did][3])
    return base64.b64decode(m.group(1)) if m else None


def _zoom(did):
    m = re.search(r"data-zoom='data:image/jpeg;base64,([^']+)'", BY_ID[did][3])
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

# ------------------------------------------------ 볼 수 있어야 셀 수 있다
# The sheet embedded one 300px JPEG per row and nothing else, so 41% of the
# countable rows rendered under 200px tall and there was no way to see more.
from PIL import Image                                            # noqa: E402


def _size(blob):
    return Image.open(io.BytesIO(blob)).size


for _did in _open:
    check("%s는 크롭 원본 해상도의 확대본을 함께 싣는다" % _did,
          _zoom(_did) is not None)
    if _zoom(_did):
        _t, _z = _size(_img(_did)), _size(_zoom(_did))
        _src = Image.open(os.path.join(
            FX["draft"],
            [d for d in DRAFT if d["Draft_ID"] == _did][0]["Figure_Crop"])).size
        check("  %s의 확대본이 썸네일보다 크다" % _did, _z[0] > _t[0],
              "%s vs %s" % (_z, _t))
        check("  %s의 확대본이 크롭을 줄이지 않는다" % _did, _z == _src,
              "%s vs 크롭 %s" % (_z, _src))

check("막힌 행에는 확대본을 싣지 않는다 - 셀 일이 없는 그림이다",
      all(_zoom(d) is None for d in BY_ID if d not in _open))
check("확대창과 닫기 수단이 페이지에 있다",
      "id='lb'" in S and "id='lbclose'" in S and "Esc" in S)
check("확대는 마우스 없이도 열린다",
      "'z'" in S and "openZoom" in S)
check("Enter가 다음 입력 가능 행으로 간다",
      "nextOpenId(ROWS, id)" in S)

# --------------------------------------------- 캡션은 잘리면 증거가 아니다
# "(A) ... (B) ..." is where a caption says how many panels there are, and it
# is also where a 120-character cut lands.
_long = [d for d in DRAFT if len(d["Caption_Text"]) > 120]
check("픽스처에 120자를 넘는 캡션이 있다", bool(_long))
for d in _long:
    check("%s의 캡션이 통째로 실린다" % d["Draft_ID"],
          d["Caption_Text"][-40:] in BY_ID[d["Draft_ID"]][3].replace("&#x27;", "'")
          or d["Caption_Text"][-40:] in S)
check("캡션을 접어 감추지 않는다",
      "max-height:46px" not in S and "text-overflow:ellipsis" not in S)

# ------------------------------------------------------------ 총계 없음
check("그림 총계를 지어내지 않는다",
      not re.search(r"그림 총\s*\d|총 그림\s*\d", S))

# ------------------------------------------ 빈칸이 감당하던 두 번째 뜻
for _did in _open:
    check("%s에 '봤지만 셀 수 없음'과 이유 칸이 있다" % _did,
          "data-unc='%s'" % _did in BY_ID[_did][3]
          and "data-uncwhy='%s'" % _did in BY_ID[_did][3])
check("막힌 행에는 그 칸을 두지 않는다 - 볼 그림이 없다",
      all("data-unc=" not in BY_ID[d][3] for d in BY_ID if d not in _open))
check("이유가 CSV 열로 나간다", "Uncountable_Reason" in S)
check("안내문이 빈칸과 '셀 수 없음'의 차이를 말한다",
      "봤지만 셀 수 없음" in S and "안 본 것과 구별되지 않아" in S)

# ------------------------------- 규칙이 바뀌면 빌드 ID도 바뀌어야 한다
# The id hashed the draft alone, so changing the BLOCKING RULES left it
# identical - and the stored values, keyed by that id, came back onto a sheet
# that now refuses rows they were typed on.
_ID0 = re.search(r'const BUILD_ID="([^"]+)"', S).group(1)
_rules = os.path.join(HERE, "block_rules.py")
_keep_rules = io.open(_rules, "rb").read()
io.open(_rules, "ab").write(b"\n# scenario: a rule changed\n")
_alt = os.path.join(TMP, "alt", "sheet.html")
os.makedirs(os.path.dirname(_alt), exist_ok=True)
try:
    _r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                        capture_output=True, text=True, cwd=HERE,
                        env=dict(ENV, FDT_SHEET=_alt))
finally:
    io.open(_rules, "wb").write(_keep_rules)
check("규칙 파일이 바뀌면 다시 빌드된다", _r.returncode == 0,
      (_r.stderr or "")[-300:])
_ID1 = re.search(r'const BUILD_ID="([^"]+)"',
                 io.open(PATHS.parts_for(_alt)[0], encoding="utf-8").read()
                 ).group(1)
check("차단 규칙이 바뀌면 빌드 ID도 바뀐다 - 옛 입력이 새 시트로 넘어오지 않게",
      _ID0 != _ID1, "%s == %s" % (_ID0, _ID1))
_r2 = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                     capture_output=True, text=True, cwd=HERE,
                     env=dict(ENV, FDT_SHEET=_alt))
_ID2 = re.search(r'const BUILD_ID="([^"]+)"',
                 io.open(PATHS.parts_for(_alt)[0], encoding="utf-8").read()
                 ).group(1)
check("아무것도 바뀌지 않으면 빌드 ID도 그대로다", _ID2 == _ID0,
      "%s vs %s" % (_ID2, _ID0))

# -------------------------------------------------- 배치로 쪼갤 때
# The crops now ride at the resolution they were cut at, so one file of 604 of
# them is not a file a browser opens. Sheets fill to a byte budget.
check("예산 안에 들어가면 한 파일 그대로다", len(PARTS) == 1, "%s" % PARTS)

SPLIT = os.path.join(TMP, "split", "sheet.html")
os.makedirs(os.path.dirname(SPLIT), exist_ok=True)
RUN2 = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                      capture_output=True, text=True, cwd=HERE,
                      env=dict(ENV, FDT_SHEET=SPLIT, FDT_SHEET_BUDGET="60000"))
check("작은 예산으로 다시 빌드된다", RUN2.returncode == 0,
      (RUN2.stderr or "")[-300:])
SP = PATHS.parts_for(SPLIT)
check("예산을 넘으면 여러 파일로 나온다", len(SP) > 1, "%s" % SP)

_part_rows, _part_cards = [], []
for _f in SP:
    _t = io.open(_f, encoding="utf-8").read()
    _part_rows.append([r["Draft_ID"] for r in json.loads(
        re.search(r"const ROWS=(\[.*?\]);const BUILD_ID=", _t, re.S).group(1))])
    _part_cards.append(re.findall(r"<h2>pid (\d+) ·", _t))

check("한 문서가 두 파일로 쪼개지지 않는다",
      all(len(set(c)) == len(c) for c in _part_cards)
      and len(set().union(*[set(c) for c in _part_cards]))
      == sum(len(c) for c in _part_cards))
check("모든 행이 정확히 한 파일에만 있다",
      sorted(sum(_part_rows, [])) == sorted(d["Draft_ID"] for d in DRAFT),
      "%s" % _part_rows)
check("각 파일은 자기가 보여주는 행만 ROWS로 싣는다",
      all(sorted(ids) == sorted(re.findall(r"data-id='([^']+)'",
                                io.open(f, encoding="utf-8").read())[:len(ids)])
          or set(ids) <= set(re.findall(r"data-id='([^']+)'",
                                        io.open(f, encoding="utf-8").read()))
          for f, ids in zip(SP, _part_rows)))
check("각 파일이 몇 번째 시트인지 말한다",
      all(("%d / %d번째 시트" % (i, len(SP)))
          in io.open(f, encoding="utf-8").read()
          for i, f in enumerate(SP, 1)))
check("나뉜 시트는 합치는 방법을 안내한다",
      "merge_counts.py" in io.open(SP[0], encoding="utf-8").read())
check("빌드 ID는 모든 파일에서 같다",
      len({re.search(r'const BUILD_ID="([^"]+)"',
                     io.open(f, encoding="utf-8").read()).group(1)
           for f in SP}) == 1)

# ---------------------------------- 끝까지 읽히지 않는 이미지는 증거가 아니다
# A render that is interrupted leaves a PNG with a valid header and a truncated
# body. Its size looks plausible, and Page_Raster_SHA256 hashes what reached
# disk as happily as it would hash the whole picture; the first thing to fail
# is whatever finally reads the last row of pixels. One of these survived a
# killed batch in run2 and was found by a measurement script, a day later.
import verify_intake_images as V                                # noqa: E402

check("정상 인테이크에는 못 읽는 이미지가 없다",
      V.unreadable(FX["draft"]) == [], "%s" % V.unreadable(FX["draft"]))

_victim = os.path.join(FX["draft"], "DOC_A", "DOC_A_D001.png")
_whole = io.open(_victim, "rb").read()
io.open(_victim, "wb").write(_whole[:len(_whole) // 2])
_found = V.unreadable(FX["draft"])
check("몸통이 잘린 PNG는 이름이 불린다",
      [os.path.basename(f) for f, _s, _e in _found] == ["DOC_A_D001.png"],
      "%s" % _found)
check("헤더만 보고 통과시키지 않는다 - Image.open은 그것을 열어 준다",
      _found and "open" not in _found[0][2].lower())
_rc = V.main([FX["draft"], os.path.join(TMP, "img.json")])
check("못 읽는 이미지가 있으면 0이 아닌 코드로 끝난다", _rc == 1)
check("영수증에 무엇이 몇 개 중 몇 개인지 남는다",
      json.load(io.open(os.path.join(TMP, "img.json"), encoding="utf-8"))
      ["verdict"] == "REFUSED")
io.open(_victim, "wb").write(_whole)
check("되돌리면 다시 깨끗하다", V.unreadable(FX["draft"]) == [])

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
