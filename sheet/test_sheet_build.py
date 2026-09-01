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


def _raises_named():
    """paths.require names the variable rather than failing on a bare path."""
    import paths as _p
    keep = _p.DRAFT
    _p.DRAFT = os.path.join(tempfile.gettempdir(), "fdt-no-such-run")
    try:
        _p.require("DRAFT", "인테이크 산출 디렉터리")
    except SystemExit as exc:
        return "FDT_DRAFT" in str(exc) and "FDT_RUN" in str(exc)
    finally:
        _p.DRAFT = keep
    return False


TMP = tempfile.mkdtemp(prefix="fdt-sheet-")
#: A file with one machine's path in it, so the scan above can be shown to
#: find one. A scan that has nothing to find proves nothing.
TMP_PORT = os.path.join(TMP, "port")
os.makedirs(TMP_PORT, exist_ok=True)
io.open(os.path.join(TMP_PORT, "planted.py"), "w", encoding="utf-8").write(
    '"""A docstring naming /home/claude, which must NOT count."""\n'
    "P = \"/home/\" + \"claude/geo/verify\"\n"
    "Q = \"/tmp/intake6/draft\"\n")
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


def _pageview(did):
    m = re.search(r"data-page='data:image/jpeg;base64,([^']+)'", BY_ID[did][3])
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

# ------------------------- 크롭은 "이게 그림 전체인가"에 답할 수 없다
# Two run2 crops were a full column wide, ACCEPTABLE and open for input while
# holding a page header and white space; the figure was beside them. A crop
# shows what the box caught and never what it missed, so the page - with the
# box drawn on it - rides along beside the count.
for _did in _open:
    check("%s는 상자를 그린 페이지 전체를 함께 싣는다" % _did,
          _pageview(_did) is not None)
    if _pageview(_did):
        check("  %s의 페이지 뷰는 크롭이 아니다" % _did,
              _pageview(_did) != _zoom(_did))
        _pv = Image.open(io.BytesIO(_pageview(_did)))
        _cr = Image.open(io.BytesIO(_zoom(_did)))
        check("  %s의 페이지 뷰가 크롭보다 넓은 영역이다" % _did,
              _pv.size[1] > _cr.size[1] or _pv.size[0] > _cr.size[0],
              "%s vs %s" % (_pv.size, _cr.size))
def _red(blob):
    """How much of this image is the outline's red. The box is the view."""
    im = Image.open(io.BytesIO(blob)).convert("RGB")
    im.thumbnail((300, 300))
    px = list(im.getdata())
    return sum(1 for r, g, b in px if r > 120 and r - g > 60 and r - b > 60)


for _did in _open:
    if _pageview(_did):
        check("  %s의 페이지에 상자가 실제로 그려져 있다" % _did,
              _red(_pageview(_did)) > 0, "붉은 화소 0")
        check("  그 붉은 선은 원본 페이지에 없던 것이다",
              _red(io.open([d for d in DRAFT
                            if d["Draft_ID"] == _did][0]["Page_Raster"],
                           "rb").read()) == 0)

# A COUNTABLE ROW WITHOUT ITS PAGE SHIPPED ONCE, IN SILENCE. The build has to
# stop instead: such a row asks to be counted with the one check that catches
# a box that missed its figure removed.
_draft_csv = os.path.join(FX["draft"], "figure_intake_draft.csv")
_keep_csv = io.open(_draft_csv, "rb").read()
_r = list(csv.DictReader(io.open(_draft_csv, encoding="utf-8")))
for _row in _r:
    if _row["Draft_ID"] == _open[0]:
        _row["Page_Raster"] = os.path.join(FX["draft"], "no_such_page.png")
with io.open(_draft_csv, "w", encoding="utf-8", newline="") as _fh:
    _w = csv.DictWriter(_fh, fieldnames=list(_r[0])); _w.writeheader()
    _w.writerows(_r)
_bad = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                      capture_output=True, text=True, cwd=HERE,
                      env=dict(ENV, FDT_SHEET=os.path.join(TMP, "np", "s.html")))
io.open(_draft_csv, "wb").write(_keep_csv)
check("입력 가능한 행에 페이지 래스터가 없으면 빌드가 실패한다",
      _bad.returncode != 0 and _open[0] in (_bad.stderr or "") + (_bad.stdout or ""),
      "rc=%s %s" % (_bad.returncode, (_bad.stderr or "")[-200:]))
check("  그리고 어느 행인지 이름을 댄다",
      "페이지 래스터가 없습니다" in (_bad.stderr or "") + (_bad.stdout or ""))
os.makedirs(os.path.join(TMP, "np2"), exist_ok=True)
_again = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                        capture_output=True, text=True, cwd=HERE,
                        env=dict(ENV,
                                 FDT_SHEET=os.path.join(TMP, "np2", "s.html")))
check("되돌리면 다시 빌드된다", _again.returncode == 0,
      (_again.stderr or "")[-200:])

check("막힌 행에는 페이지 뷰도 싣지 않는다",
      all(_pageview(d) is None for d in BY_ID if d not in _open))
check("확대창이 두 단계를 그 순서로 묻는다",
      S.index("상자가 목표 그림 전체를 담았습니까") < S.index("축 영역이 몇 개입니까"))
check("페이지 뷰 자리와 크롭 자리가 각각 있다",
      "id='lbpage'" in S and "id='lbimg'" in S)
check("기하가 없으면 상자 없는 페이지를 보여주지 않는다",
      "return \"\"" in io.open(os.path.join(HERE, "build_sheet2.py"),
                              encoding="utf-8").read())

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
os.makedirs(os.path.join(TMP, "tiny"), exist_ok=True)
_tiny = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_SHEET=os.path.join(TMP, "tiny",
                                                            "s.html"),
                                FDT_SHEET_BUDGET="1000"))
check("예산보다 큰 문서 하나는 자기 파일을 가지되 그 사실을 말한다",
      "예산" in (_tiny.stdout or "") and "주의" in (_tiny.stdout or ""),
      (_tiny.stdout or _tiny.stderr or "")[-300:])

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

# DECODING WHAT IS THERE SAYS NOTHING ABOUT WHAT IS NOT. The walk reported
# every file it found as fine while a page raster the draft names sat in the
# part it was built in - a merge had skipped the document because its
# directory already existed at the destination.
_want = V.expected(FX["draft"])
check("기대 목록은 초안이 부르는 크롭과 페이지를 모두 담는다",
      _want and len(_want) >= len([d for d in DRAFT if d["Figure_Crop"]]),
      "%s" % (len(_want or {}),))
check("정상 상태에서는 부르는 것이 전부 디스크에 있다",
      not [r for r in _want if r not in V.on_disk(FX["draft"])])
_moved = os.path.join(FX["draft"], "DOC_A", "DOC_A_D002.png")
_body = io.open(_moved, "rb").read()
os.remove(_moved)
_rc2 = V.main([FX["draft"], os.path.join(TMP, "img2.json")])
_rep = json.load(io.open(os.path.join(TMP, "img2.json"), encoding="utf-8"))
check("초안이 부르는 파일이 사라지면 거부한다", _rc2 == 1)
check("  그리고 어느 행이 부르던 파일인지 말한다",
      [d for _f, d in _rep["named_but_absent"]] == ["DOC_A_D002"],
      "%s" % _rep["named_but_absent"])
io.open(_moved, "wb").write(_body)

_extra = os.path.join(FX["draft"], "DOC_A", "leftover_from_an_old_run.png")
shutil.copyfile(_moved, _extra)
_rc3 = V.main([FX["draft"], os.path.join(TMP, "img3.json")])
_rep3 = json.load(io.open(os.path.join(TMP, "img3.json"), encoding="utf-8"))
check("초안이 부르지 않는 파일은 세기만 하고 거부하지 않는다",
      _rc3 == 0 and _rep3["on_disk_not_named"] >= 1,
      "%s %s" % (_rc3, _rep3["on_disk_not_named"]))
os.remove(_extra)

# --- 다른 사람의 기기에서도 도는가 -------------------------------------------
# The module that exists so no path is written into a file still handed out
# one machine's paths as its defaults, and the crop harness required a JSON
# map nothing in this repository writes - made by hand, once, on that machine.
import portability as _PORT                                     # noqa: E402
import paths as _P                                              # noqa: E402

_offenders = _PORT.machine_paths(HERE, skip=("test_sheet_build.py",))
check("어떤 파일도 한 기기의 절대경로를 코드에 담지 않는다",
      not _offenders, "%s" % _offenders[:4])
check("그 검사가 실제로 무언가를 볼 수 있다 - 심어 두면 잡는다",
      bool(_PORT.machine_paths(TMP_PORT)), "심은 파일을 못 잡음")

# THE DEFAULT IS THE THING THAT TRAVELS, so these read paths.DEFAULTS rather
# than the effective values: with FDT_* set - as any real run sets them - the
# effective values say what this run was pointed at, not what the repository
# ships to somebody who sets nothing.
_bad_defaults = {k: v for k, v in _P.DEFAULTS.items()
                 if isinstance(v, str)
                 and any(str(v).startswith(h)
                         for h in _PORT.MACHINE_PREFIXES + ("/tmp/",))}
check("경로 기본값이 저장소 밖 절대경로가 아니다",
      not _bad_defaults, "%s" % _bad_defaults)
check("한 사람의 홈 디렉터리가 경로 치환 기본값이 아니다",
      not any(h in _P.DEFAULTS.get("FDT_PATH_REWRITE", "")
              for h in _PORT.MACHINE_PREFIXES),
      _P.DEFAULTS.get("FDT_PATH_REWRITE"))
check("기본값 목록이 실제로 변수들을 담고 있다 - 빈 목록은 통과가 아니다",
      len(_P.DEFAULTS) >= 8, sorted(_P.DEFAULTS))
check("없는 경로는 어떤 변수를 세우라고 말하며 멈춘다",
      _raises_named())

# The map the crop harness needed, derived from the two files that say it.
_work = list(csv.DictReader(io.open(FX["worklist"], encoding="utf-8")))
_ledger = list(csv.DictReader(io.open(
    os.path.join(FX["draft"], "intake_document_status.csv"), encoding="utf-8")))
_map = _P.pid_of_document(_work, _ledger)
check("pid-문서 지도를 워크리스트와 원장에서 유도한다",
      len(_map) == len(_work) and set(_map.values()) == {w["pid"]
                                                         for w in _work},
      "%s" % _map)
check("접두사가 어긋나면 빈 지도가 나오고, 그것이 신호다",
      _P.pid_of_document([dict(w, href="file:///elsewhere/x.pdf")
                          for w in _work], _ledger) == {})

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
