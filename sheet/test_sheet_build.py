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
           FDT_CENSUS=FX["census"], FDT_CENSUS_OPTIONAL="",
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
      sorted(r["Draft_ID"] for r in ROWS)
      == sorted(d["Draft_ID"] for d in DRAFT))
# The order that matters is the page's, not the CSV's: the cards run P1 before
# P2 and then by pid, and ROWS has to follow what a person sees. Comparing to
# the draft's own order passed only while the fixture happened to list its
# documents in pid order.
check("ROWS의 순서가 화면의 순서와 같다",
      [r["Draft_ID"] for r in ROWS]
      == re.findall(r"<div class='fig[^']*' data-id='([^']+)'", S))
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
# AND IT SAYS WHAT IS TRUE. The message read "원문에 그림이 포함되어 있지
# 않습니다" on 45 rows whose sources are JATS XML - papers that do have
# figures, one of them fifteen, named file by file inside the XML. What is
# absent is a file in this corpus, not a figure in the paper.
_nocrop_text = BY_ID["DOC_B_D002"][3]
check("크롭이 없는 행은 이미지 대신 그 사실을 말한다",
      _img("DOC_B_D002") is None and "보여줄 이미지가 없습니다" in _nocrop_text)
check("  그 문구가 논문에 그림이 없다고 주장하지 않는다",
      "그림이 포함되어 있지 않" not in S and "그림이 없습니다" not in S,
      "%s" % _nocrop_text[:120])
check("  무엇을 구하면 되는지 말한다",
      "PDF" in _nocrop_text and "그림 파일" in _nocrop_text)
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
# A publisher's figure file has no page to show; it is checked on its own
# terms further down.
_page_backed = [d for d in _open
                if {r["Draft_ID"]: r for r in DRAFT}[d]["Crop_Quality_Status"]
                != "PUBLISHER_FIGURE"]
for _did in _page_backed:
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


for _did in _page_backed:
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

# --- 페이지가 없는 출처: 출판사 그림 파일 -----------------------------------
# Eight of the corpus's sources are JATS XML with no pages to cut from. For one
# of them the publisher's own figure files are on hand, and a file that IS the
# figure cannot clip it or take in a neighbour - so the first question does not
# arise, and saying so is not the same as leaving it blank.
_pubfig = [d["Draft_ID"] for d in DRAFT
           if d["Crop_Quality_Status"] == "PUBLISHER_FIGURE"]
check("픽스처에 출판사 그림 파일 행이 있다", len(_pubfig) == 1, "%s" % _pubfig)
for _did in _pubfig:
    check("%s는 입력이 열려 있다" % _did, _did in _open, "%s" % _open)
    check("  페이지 뷰 대신 사유를 싣는다",
          _pageview(_did) is None and "data-nopage=" in BY_ID[_did][3])
    check("  그 사유가 상자가 없다는 사실을 말한다",
          "상자가 없으므로" in BY_ID[_did][3])
    check("  확대본은 그대로 싣는다 - 셀 그림이니까",
          _zoom(_did) is not None)
check("페이지 뷰를 싣는 행은 사유를 싣지 않는다",
      all("data-nopage=" not in BY_ID[d][3]
          for d in _open if d not in _pubfig))

# The build refuses a figure-file row whose file is not there, the way it
# refuses a page-backed row with no page.
_pf_csv = os.path.join(FX["draft"], "figure_intake_draft.csv")
_pf_keep = io.open(_pf_csv, "rb").read()
_rr = list(csv.DictReader(io.open(_pf_csv, encoding="utf-8")))
for _row in _rr:
    if _row["Draft_ID"] == _pubfig[0]:
        _row["Figure_Crop"] = os.path.join("DOC_E", "gone.png")
with io.open(_pf_csv, "w", encoding="utf-8", newline="") as _fh:
    _w = csv.DictWriter(_fh, fieldnames=list(_rr[0])); _w.writeheader()
    _w.writerows(_rr)
_pf = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                     capture_output=True, text=True, cwd=HERE,
                     env=dict(ENV, FDT_SHEET=os.path.join(TMP, "pf", "s.html")))
io.open(_pf_csv, "wb").write(_pf_keep)
check("그림 파일이 없는 그림파일 행은 빌드를 멈춘다",
      _pf.returncode != 0
      and "그 파일이 없습니다" in (_pf.stderr or "") + (_pf.stdout or ""),
      "rc=%s %s" % (_pf.returncode, (_pf.stderr or "")[-160:]))

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

# ------------------------------------------- 육안 조사표를 통과한 것만 계수 가능
# ACCEPTABLE은 크롭에 대한 측정이고, 조사표는 그 안에 무엇이 들어 있는지에 대한
# 기록입니다. run2에서 열려 있던 440행 중 336행이 본문·표·잘린 그림이었으므로,
# 이 파일이 사라지면 그 336행이 조용히 다시 열립니다. 그래서 없으면 멈춥니다.
import hashlib                                                   # noqa: E402


def _census_run(rows, extra_env=None, path=None):
    """조사표를 쓴 뒤 빌드를 돌리고 (결과, 시트 텍스트)를 준다."""
    target = path or os.path.join(TMP, "census.csv")
    with io.open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(make_fixture.CENSUS_FIELDS))
        w.writeheader()
        w.writerows(rows)
    out = os.path.join(TMP, "census_sheet.html")
    env = dict(ENV, FDT_CENSUS=target, FDT_SHEET=out)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, env=env, cwd=HERE)
    text = "\n".join(io.open(f, encoding="utf-8").read()
                      for f in _P.parts_for(out)) if r.returncode == 0 else ""
    return r, text


#: 픽스처에서 열려 있는 아무 행 하나와 그 크롭의 digest.
_open_row = [d for d in DRAFT
             if d["Crop_Quality_Status"] == "ACCEPTABLE" and d["Figure_Crop"]][0]
_open_sha = hashlib.sha256(io.open(
    os.path.join(FX["draft"], _open_row["Figure_Crop"]), "rb").read()).hexdigest()


def _entry(**kw):
    base = dict(Draft_ID=_open_row["Draft_ID"],
                Source_Document_ID=_open_row["Source_Document_ID"],
                Page=_open_row["Page"], Figure_Number=_open_row["Figure_Number"],
                Crop_SHA256=_open_sha, Figure_BBox=_open_row["Figure_BBox"],
                Agent_Visual_Code="NO_FIGURE",
                Agent_Visual_Note="상자 안이 본문뿐", Human_Verdict="",
                Human_Note="")
    base.update(kw)
    return base


_no_file = subprocess.run(
    [sys.executable, os.path.join(HERE, "build_sheet2.py")],
    capture_output=True, text=True, cwd=HERE,
    env=dict(ENV, FDT_CENSUS=os.path.join(TMP, "gone.csv"),
             FDT_SHEET=os.path.join(TMP, "gone.html")))
check("조사표가 없으면 빌드가 멈춘다", _no_file.returncode != 0,
      (_no_file.stdout or "")[-200:])
check("멈추면서 어떻게 밝히면 되는지까지 말한다",
      "FDT_CENSUS_OPTIONAL" in (_no_file.stdout + _no_file.stderr))
_waived = subprocess.run(
    [sys.executable, os.path.join(HERE, "build_sheet2.py")],
    capture_output=True, text=True, cwd=HERE,
    env=dict(ENV, FDT_CENSUS=os.path.join(TMP, "gone.csv"),
             FDT_CENSUS_OPTIONAL="1",
             FDT_SHEET=os.path.join(TMP, "waived.html")))
check("아직 아무도 보지 않았다고 밝히면 빌드는 된다", _waived.returncode == 0,
      (_waived.stderr or "")[-300:])

_blocked_run, _blocked_text = _census_run([_entry()])
check("조사표가 결함으로 본 행은 빌드가 되고도 입력이 막힌다",
      _blocked_run.returncode == 0
      and ("data-id='%s'" % _open_row["Draft_ID"]) in _blocked_text
      and re.search(r"<input[^>]*disabled[^>]*data-id='%s'"
                    % re.escape(_open_row["Draft_ID"]), _blocked_text)
      is not None, (_blocked_run.stderr or "")[-300:])
check("막은 이유가 화면에 그대로 적힌다",
      "상자 안이 본문뿐" in _blocked_text)
check("사람이 COUNTABLE로 바꾸면 다시 열린다",
      re.search(r"<input(?![^>]*disabled)[^>]*data-id='%s'"
                % re.escape(_open_row["Draft_ID"]),
                _census_run([_entry(Human_Verdict="COUNTABLE")])[1]) is not None)
check("사람이 BLOCKED로 적으면 코드가 OK라도 막힌다",
      re.search(r"<input[^>]*disabled[^>]*data-id='%s'"
                % re.escape(_open_row["Draft_ID"]),
                _census_run([_entry(Agent_Visual_Code="OK",
                                    Human_Verdict="BLOCKED",
                                    Human_Note="사람이 다시 봤더니 잘림")])[1])
      is not None)
check("OK로 본 행은 조사표가 막지 않는다",
      re.search(r"<input(?![^>]*disabled)[^>]*data-id='%s'"
                % re.escape(_open_row["Draft_ID"]),
                _census_run([_entry(Agent_Visual_Code="OK",
                                    Agent_Visual_Note="온전")])[1]) is not None)

# 픽셀이 달라졌으면 그 판정은 이 크롭에 대한 판정이 아니다.
_moved = _census_run([_entry(Crop_SHA256="0" * 64)])[1]
check("같은 그림을 결함으로 본 기록이 있는데 크롭이 바뀌었으면 다시 막는다",
      re.search(r"<input[^>]*disabled[^>]*data-id='%s'"
                % re.escape(_open_row["Draft_ID"]), _moved) is not None)
check("그 이유는 '다시 봐야 한다'라고 적힌다", "REVIEW_REQUIRED" in _moved)
_moved_ok = _census_run([_entry(Crop_SHA256="0" * 64,
                                Agent_Visual_Code="OK")])[1]
check("온전하다고 본 그림은 크롭이 바뀌어도 막지 않는다",
      re.search(r"<input(?![^>]*disabled)[^>]*data-id='%s'"
                % re.escape(_open_row["Draft_ID"]), _moved_ok) is not None)

_typo = _census_run([_entry(Human_Verdict="ok")])[0]
check("사람 칸에 모르는 값이 있으면 빌드가 멈춘다", _typo.returncode != 0)
check("멈추면서 어느 행인지 말한다",
      _open_row["Draft_ID"] in (_typo.stdout + _typo.stderr))
_badcode = _census_run([_entry(Agent_Visual_Code="LOOKS_FINE")])[0]
check("모르는 판정 코드도 멈춘다 (오타가 '계수 가능'으로 읽히지 않게)",
      _badcode.returncode != 0)
# 멈추는 것만으로는 부족합니다. 어휘 검사를 지워도 뒤쪽에서 KeyError로 죽기
# 때문에 "멈췄다"는 검사는 가드가 없어도 통과합니다. 가드가 하는 일은 무엇이
# 잘못됐고 아는 값이 무엇인지 말해 주는 것이므로, 그것을 봅니다.
_badout = _badcode.stdout + _badcode.stderr
check("모르는 코드를 이름으로 부르고 아는 어휘를 함께 알려 준다",
      "LOOKS_FINE" in _badout and "NO_FIGURE" in _badout and
      "Traceback" not in _badout, _badout[-200:])
_shortsha = _census_run([_entry(Crop_SHA256="deadbeef")])[0]
check("판정이 64자 digest에 묶여 있지 않으면 멈춘다", _shortsha.returncode != 0,
      (_shortsha.stdout or "")[-160:])
_conflict = _census_run([_entry(Agent_Visual_Code="OK"),
                         _entry(Draft_ID=_open_row["Draft_ID"] + "_B",
                                Agent_Visual_Code="NO_FIGURE")])[0]
check("같은 크롭에 서로 다른 판정이 있으면 멈춘다", _conflict.returncode != 0,
      (_conflict.stdout or "")[-160:])

# 조사표는 빌드 ID에 들어간다: 규칙이 바뀌면 저장된 값이 새 화면으로 돌아오면 안 된다.
_id1 = re.search(r"sheet-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}",
                 _census_run([_entry()])[1])
_id2 = re.search(r"sheet-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}",
                 _census_run([_entry(Agent_Visual_Code="OK")])[1])
check("조사표가 달라지면 빌드 ID가 달라진다",
      _id1 and _id2 and _id1.group(0) != _id2.group(0),
      "%s vs %s" % (_id1 and _id1.group(0), _id2 and _id2.group(0)))

# ------------------------------------------------ 상자대로 다시 자르면 크롭인가
# 2026-09-02에 상자를 거울처럼 뒤집어 그린 판정 461개가 모든 게이트를 통과했습니다.
# 게이트는 시트를 시트와 대조했고, 상자를 그 상자가 가리킨다는 그림과 대조하는
# 검사는 없었습니다. 이것이 그 검사입니다.
import roundtrip as RT                                           # noqa: E402
from PIL import Image as _Image                                  # noqa: E402

_with_page = [d for d in DRAFT if d["Figure_Crop"] and d["Page_Raster"]]
_rt = {d["Draft_ID"]: RT.check(d, FX["draft"]) for d in _with_page}
check("픽스처의 모든 크롭이 자기 상자에서 다시 만들어진다 (%d행)" % len(_with_page),
      all(v[0] == "MATCH" for v in _rt.values()),
      {k: v for k, v in _rt.items() if v[0] != "MATCH"})
check("MATCH는 잘라낸 픽셀 상자를 함께 돌려준다",
      all(len(v[1].split(",")) == 4 for v in _rt.values()))


def _variant(name, mutate):
    """픽스처 초안의 사본을 바꾼 뒤 그 사본으로 빌드한다. (초안 dict, 결과, 시트)"""
    root = os.path.join(TMP, "var_" + name)
    shutil.copytree(FX["draft"], root)
    rows = list(csv.DictReader(io.open(
        os.path.join(root, "figure_intake_draft.csv"), encoding="utf-8")))
    mutate(rows, root)
    with io.open(os.path.join(root, "figure_intake_draft.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = os.path.join(TMP, "var_%s.html" % name)
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_DRAFT=root, FDT_SHEET=out,
                                FDT_CENSUS=os.path.join(root,
                                                        "crop_visual_census.csv")))
    text = ("\n".join(io.open(f, encoding="utf-8").read()
                      for f in _P.parts_for(out)) if r.returncode == 0 else "")
    return rows, r, text


_target = _with_page[0]["Draft_ID"]


def _flip(rows, root):
    for r in rows:
        if r["Draft_ID"] == _target:
            ph = float(r["Page_Height_Pt"])
            x0, y0, x1, y1 = [float(v) for v in r["Figure_BBox"].split(",")]
            r["Figure_BBox"] = "%.1f,%.1f,%.1f,%.1f" % (x0, ph - y1, x1, ph - y0)


_flipped_rows, _flip_run, _flip_text = _variant("flip", _flip)
_flip_row = [r for r in _flipped_rows if r["Draft_ID"] == _target][0]
check("상자를 아래 기준으로 뒤집으면 왕복 검사가 MISMATCH를 낸다",
      RT.check(_flip_row, os.path.join(TMP, "var_flip"))[0] == "MISMATCH",
      RT.check(_flip_row, os.path.join(TMP, "var_flip")))
check("뒤집힌 상자의 행은 시트에서 막힌다",
      _flip_run.returncode == 0 and re.search(
          r"<input[^>]*disabled[^>]*data-id='%s'" % re.escape(_target),
          _flip_text) is not None, (_flip_run.stderr or "")[-300:])
check("막은 이유가 '다시 자른 그림이 크롭 파일과 다르다'고 말한다",
      "다시 자른 그림이 크롭 파일과 다릅니다" in _flip_text)
try:
    RT.selfcheck(os.path.join(TMP, "var_flip"))
    _sc = None
except SystemExit as exc:
    _sc = str(exc)
check("상자를 쓰는 도구는 뒤집힌 초안 위에서 시작하기를 거부한다", _sc is not None)
check("거부하면서 어느 행인지 말한다", _sc is not None and _target in _sc, _sc)


def _shift(rows, root):
    for r in rows:
        if r["Draft_ID"] == _target:
            x0, y0, x1, y1 = [float(v) for v in r["Figure_BBox"].split(",")]
            r["Figure_BBox"] = "%.1f,%.1f,%.1f,%.1f" % (x0, y0 + 30, x1, y1 + 30)


_shift_rows = _variant("shift", _shift)[0]
check("상자가 30pt만 밀려도 MISMATCH다",
      RT.check([r for r in _shift_rows if r["Draft_ID"] == _target][0],
               os.path.join(TMP, "var_shift"))[0] == "MISMATCH")


def _tamper(rows, root):
    for r in rows:
        if r["Draft_ID"] == _target:
            path = os.path.join(root, r["Figure_Crop"])
            im = _Image.open(path).convert("L")
            _Image.eval(im, lambda v: 255 - v).save(path)   # 같은 크기, 다른 내용


_tamper_rows, _tamper_run, _tamper_text = _variant("tamper", _tamper)
check("크기는 같고 내용만 다른 크롭도 MISMATCH다",
      RT.check([r for r in _tamper_rows if r["Draft_ID"] == _target][0],
               os.path.join(TMP, "var_tamper"))[0] == "MISMATCH")
check("바뀐 크롭의 행은 시트에서 막힌다",
      _tamper_run.returncode == 0 and re.search(
          r"<input[^>]*disabled[^>]*data-id='%s'" % re.escape(_target),
          _tamper_text) is not None)


def _nogeom(rows, root):
    for r in rows:
        if r["Draft_ID"] == _target:
            r["Page_Width_Pt"] = r["Page_Height_Pt"] = ""


_ng_rows, _ng_run, _ng_text = _variant("nogeom", _nogeom)
check("크롭은 있는데 쪽 크기가 없는 행은 NO_CUT이다",
      RT.check([r for r in _ng_rows if r["Draft_ID"] == _target][0],
               os.path.join(TMP, "var_nogeom"))[0] == "NO_CUT")
check("그 행은 시트에서 '기하로는 만들 수 없다'는 이유로 막힌다",
      _ng_run.returncode == 0 and "초안의 기하로는 이 크롭을 만들 수 없습니다" in _ng_text
      and re.search(r"<input[^>]*disabled[^>]*data-id='%s'" % re.escape(_target),
                    _ng_text) is not None, (_ng_run.stderr or "")[-300:])

# 상자 바깥으로 잉크가 이어질 때만 pad가 결과에 드러납니다. 그래서 그런 그림을
# 여기서 하나 그립니다 - 픽스처의 그림은 상자 안에 들어 있어 pad를 증명하지 못합니다.
_pg = _Image.new("L", (400, 400), 255)
for _yy in range(100, 300):
    for _xx in range(100, 300):
        _pg.putpixel((_xx, _yy), 0)                       # 200x200 검은 사각형
_bleed_row = {"Figure_BBox": "150,150,250,250", "Page_Width_Pt": "400",
              "Page_Height_Pt": "400"}                    # 그 안쪽 100x100 상자
_bl = RT.cut(_pg, _bleed_row)
# 숫자 8은 인테이크의 `pad=8`입니다. RT.PAD로 쓰면 그 상수를 바꿔도 시나리오가
# 따라 바뀌어 통과하므로, 계약은 숫자로 적습니다.
check("잉크가 상자 밖으로 이어지면 잘라낸 것이 인테이크의 pad 8px만큼 더 크다",
      _bl is not None and _bl[1] == (142, 142, 258, 258), _bl and _bl[1])

# 1단계 검사기가 이 결함을 REFUSED로 낸다.
import verify_intake_images as _VI                                # noqa: E402
_vi_rc = _VI.main([os.path.join(TMP, "var_nogeom"),
                   os.path.join(TMP, "var_nogeom_receipt.json")])
_vi = json.loads(io.open(os.path.join(TMP, "var_nogeom_receipt.json"),
                         encoding="utf-8").read())
check("파일 무결성 검사기가 재현 불가 크롭을 REFUSED로 낸다",
      _vi_rc != 0 and _vi["verdict"] == "REFUSED"
      and any(_target in x[0] for x in _vi["roundtrip_mismatched"]), _vi)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
