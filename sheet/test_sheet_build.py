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
                         "" if ok else "  <- %s" % (detail,)))
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
           FDT_REGIONS=FX["regions"], FDT_REGIONS_OPTIONAL="",
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

# --- 한 그림을 두 행이 세지 않는가 (빌드 끝에서 끝까지) -----------------------
# 2026-09-03: 사람이 210행에 답하자 26쌍이 같은 그림을 두 번 세게 됐습니다.
# 규칙은 `test_sheet_blocks.py`가 지키지만, 빌더가 그 규칙에 사실을 넘겨주지
# 않으면 규칙은 한 번도 불리지 않습니다 - 그것을 여기서 잡습니다.
_dup_root = os.path.join(TMP, "dup_root")
shutil.copytree(FX["draft"], _dup_root)
_dp = os.path.join(_dup_root, "figure_intake_draft.csv")
_drows = list(csv.DictReader(io.open(_dp, encoding="utf-8")))
_dcols = list(_drows[0])
_base = [r for r in _drows if r["Figure_Crop"] and r["Page_Raster"]][0]
_bx = [float(v) for v in _base["Figure_BBox"].split(",")]
# 같은 문서·같은 번호·같은 쪽에, 살짝 어긋난 상자로 한 행을 더 만듭니다 -
# 인테이크가 본문의 언급을 캡션으로 읽었을 때 실제로 생기는 모양입니다.
# 크롭 파일도 자기 상자에서 따로 잘라 줍니다. 같은 파일을 가리키면 픽셀까지
# 같은 크롭(shared_crop)으로 먼저 막혀, 중복 관문은 불리지도 않습니다.
import roundtrip as _RT_dup                                      # noqa: E402
from PIL import Image as _Img_dup                                # noqa: E402
_twin_box = "%.1f,%.1f,%.1f,%.1f" % (_bx[0] + 20, _bx[1] + 20, _bx[2] - 20, _bx[3] - 20)
_twin_rel = os.path.join(os.path.dirname(_base["Figure_Crop"]),
                         os.path.basename(_base["Figure_Crop"])[:-4] + "X.png")
_twin_cut = _RT_dup.cut(_Img_dup.open(_base["Page_Raster"]),
                        dict(_base, Figure_BBox=_twin_box))
_twin_cut[0].save(os.path.join(_dup_root, _twin_rel))
_twin_row = dict(_base, Draft_ID=_base["Draft_ID"] + "X",
                 Figure_BBox=_twin_box, Figure_Crop=_twin_rel,
                 Crop_Source="HUMAN_CHOICE_DRAWN")
_drows.append(_twin_row)
with io.open(_dp, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_dcols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _dcols} for r in _drows])
_rp2 = os.path.join(_dup_root, "validated_regions.csv")
_rr2 = list(csv.DictReader(io.open(_rp2, encoding="utf-8")))
_rr2.append(dict(_rr2[0], Draft_ID=_twin_row["Draft_ID"], Agreement="HUMAN_VALIDATED"))
with io.open(_rp2, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr2[0]))
    w.writeheader()
    w.writerows(_rr2)
_dup_out = os.path.join(TMP, "dup.html")
_rc_dup = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                         capture_output=True, text=True, cwd=HERE,
                         env=dict(ENV, FDT_DRAFT=_dup_root, FDT_SHEET=_dup_out,
                                  FDT_CENSUS=os.path.join(_dup_root,
                                                          "crop_visual_census.csv"),
                                  FDT_REGIONS=_rp2))
_dup_reasons = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_dup_root, "block_reasons.csv"), encoding="utf-8"))}     if _rc_dup.returncode == 0 else {}
check("중복 행이 있어도 빌드는 돈다", _rc_dup.returncode == 0,
      (_rc_dup.stderr or "")[-200:])
_pair = [_base["Draft_ID"], _twin_row["Draft_ID"]]
_blocked_pair = [d for d in _pair if _dup_reasons.get(d, {}).get("Count_Blocked") == "1"
                 and "두 번 세는 것" in _dup_reasons[d]["Reason"]]
check("빌더가 그 사실을 규칙에 넘겨, 둘 중 하나가 중복으로 막힌다",
      len(_blocked_pair) == 1, [(d, _dup_reasons.get(d, {}).get("Reason", "")[:40])
                                for d in _pair])
check("진 쪽은 손으로 그린 행이다 (근거가 약한 쪽)",
      _blocked_pair == [_twin_row["Draft_ID"]], _blocked_pair)
check("이긴 쪽은 막히지 않는다",
      _dup_reasons.get(_base["Draft_ID"], {}).get("Count_Blocked") == "0",
      _dup_reasons.get(_base["Draft_ID"], {}).get("Reason", "")[:60])
check("진 쪽에는 상자를 그려도 소용없다고 적힌다",
      _dup_reasons.get(_twin_row["Draft_ID"], {}).get("Box_Would_Open") == "0")
# 큐가 산문이 아니라 이 칸을 읽습니다 - 누가 그 그림을 가지는가.
check("사유 표가 이긴 행을 칸으로 적는다 (큐가 읽을 수 있게)",
      _dup_reasons.get(_twin_row["Draft_ID"], {}).get("Duplicate_Of") == _base["Draft_ID"]
      and _dup_reasons.get(_base["Draft_ID"], {}).get("Duplicate_Of") == "",
      (_dup_reasons.get(_twin_row["Draft_ID"], {}).get("Duplicate_Of"),
       _dup_reasons.get(_base["Draft_ID"], {}).get("Duplicate_Of")))
check("요약 줄이 중복을 막음과 따로 센다",
      re.search(r"막음 \d+ · 중복 1 ", _rc_dup.stdout or "") is not None,
      [l for l in (_rc_dup.stdout or "").splitlines() if l.startswith("행 ")])


def _rebuild_dup(tag):
    out = os.path.join(TMP, "dup_%s.html" % tag)
    rc = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                        capture_output=True, text=True, cwd=HERE,
                        env=dict(ENV, FDT_DRAFT=_dup_root, FDT_SHEET=out,
                                 FDT_CENSUS=os.path.join(_dup_root,
                                                         "crop_visual_census.csv"),
                                 FDT_REGIONS=_rp2))
    reasons = ({r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(_dup_root, "block_reasons.csv"), encoding="utf-8"))}
        if rc.returncode == 0 else {})
    return rc, reasons


# 한 그림, 두 행, 픽셀까지 같은 크롭 - 잉크에 맞춰 자르므로 한 그림을 둘러싼
# 두 상자는 그렇게 됩니다. 2026-09-04에 이긴 행 셋이 진 행과 "픽셀까지 같다"는
# 이유로 막혀 있었습니다 - 사람이 방금 그려 준 그림이 세어지지 않은 채로.
shutil.copyfile(os.path.join(_dup_root, _base["Figure_Crop"]),
                os.path.join(_dup_root, _twin_rel))
_rc_same, _same = _rebuild_dup("same")
check("크롭이 픽셀까지 같아도 빌드는 돈다", _rc_same.returncode == 0,
      (_rc_same.stderr or "")[-200:])
check("중복으로 설명되는 쌍은 이긴 행을 막지 않는다",
      _same.get(_base["Draft_ID"], {}).get("Count_Blocked") == "0",
      _same.get(_base["Draft_ID"], {}).get("Reason", "")[:80])
check("진 행은 '픽셀까지 같다'가 아니라 중복으로 막힌다",
      "두 번 세는 것" in _same.get(_twin_row["Draft_ID"], {}).get("Reason", ""),
      _same.get(_twin_row["Draft_ID"], {}).get("Reason", "")[:80])
_twin_cut[0].save(os.path.join(_dup_root, _twin_rel))

# 이긴 행을 사람이 막으면 그림은 진 행으로 넘어갑니다 - 메시지가 그렇게
# 약속하고, 이제 코드도 그렇게 합니다.
_rr2b = list(csv.DictReader(io.open(_rp2, encoding="utf-8")))
for r in _rr2b:
    if r["Draft_ID"] == _base["Draft_ID"]:
        r["Agreement"] = "HUMAN_BLOCKED"
with io.open(_rp2, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr2b[0]))
    w.writeheader()
    w.writerows(_rr2b)
_rc_blk, _blk = _rebuild_dup("blk")
check("이긴 행을 사람이 막으면 진 행은 중복이 아니게 된다",
      _rc_blk.returncode == 0 and _blk.get(_twin_row["Draft_ID"], {}).get("Duplicate_Of") == ""
      and "두 번 세는 것" not in _blk.get(_twin_row["Draft_ID"], {}).get("Reason", ""),
      _blk.get(_twin_row["Draft_ID"], {}).get("Reason", "")[:80])
check("그리고 그 행이 그림을 가진다 (셀 수 있다)",
      _blk.get(_twin_row["Draft_ID"], {}).get("Count_Blocked") == "0",
      _blk.get(_twin_row["Draft_ID"], {}).get("Reason", "")[:80])
for r in _rr2b:
    if r["Draft_ID"] == _base["Draft_ID"]:
        r["Agreement"] = "AGREE_3"
    if r["Draft_ID"] == _twin_row["Draft_ID"]:
        # 사람이 다른 쪽에 그렸는데 그 쪽의 행이 이미 세고 있었다고 apply가 적어 둔 행
        r["Duplicate_Of"] = "SOMEDOC_D777"
        r["Duplicate_Page"] = "9"
_cols2b = list(_rr2b[0]) + [c for c in ("Duplicate_Of", "Duplicate_Page")
                            if c not in _rr2b[0]]
with io.open(_rp2, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols2b)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _cols2b} for r in _rr2b])
_rc_cf, _cf = _rebuild_dup("cf")
# 같은 쪽의 중복(기계)이 먼저고, 적어 둔 것은 그것이 없을 때 읽습니다 - 여기서는
# 같은 쪽 중복이 있으므로 그쪽이 이유가 됩니다. 적어 둔 것만 있는 경우를 보려면
# 진 행을 다른 쪽으로 보냅니다.
_drows2 = list(csv.DictReader(io.open(_dp, encoding="utf-8")))
for r in _drows2:
    if r["Draft_ID"] == _twin_row["Draft_ID"]:
        r["Page"] = str(int(r["Page"]) + 40)
with io.open(_dp, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_dcols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _dcols} for r in _drows2])
_rc_cf2, _cf2 = _rebuild_dup("cf2")
check("apply가 적어 둔 중복을 빌더가 읽어 이유로 만든다",
      _rc_cf2.returncode == 0
      and _cf2.get(_twin_row["Draft_ID"], {}).get("Duplicate_Of") == "SOMEDOC_D777"
      and "다시 묻지 않습니다" in _cf2.get(_twin_row["Draft_ID"], {}).get("Reason", ""),
      (_cf2.get(_twin_row["Draft_ID"], {}).get("Duplicate_Of"),
       _cf2.get(_twin_row["Draft_ID"], {}).get("Reason", "")[:80]))

# --- 번호를 적어야 하는 행: 사유 표가 그 사실을 적는가 -----------------------
# 번호를 못 읽어 막힌 8행 중 7행은 크롭도 얇습니다. 상자와 번호를 따로 물으면
# 두 답이 다 "아니오"이고, 카드는 "상자를 그려도 소용없습니다"라고만 했습니다.
_num_root = os.path.join(TMP, "num_root")
shutil.copytree(FX["draft"], _num_root)
_np = os.path.join(_num_root, "figure_intake_draft.csv")
_nrows = list(csv.DictReader(io.open(_np, encoding="utf-8")))
_ncols = list(_nrows[0])
import block_rules as _BR_num                                    # noqa: E402
_unread = (_BR_num.UNREADABLE_NUMBER_REASON
           + " 's', which is not a number; a person has to supply it")
# 같은 논문에 크롭과 쪽이 있는 행이 둘 이상인 문서를 고릅니다: 앞의 행은 그
# 그림을 세는 쪽으로 남고, 뒤의 행이 번호를 못 읽은 행이 됩니다. 문서가 하나뿐인
# 행을 고르면 "누가 세고 있나"를 볼 상대가 없습니다.
_bydoc_n = {}
for r in _nrows:
    if r["Figure_Crop"] and r["Page_Raster"]:
        _bydoc_n.setdefault(r["Source_Document_ID"], []).append(r)
_pair = [v for v in _bydoc_n.values() if len(v) >= 2][0]
_hold_row, _nbase = _pair[0], _pair[1]
_nbase["Figure_Number"] = ""
_nbase["Confidence"] = "0.00"
_nbase["Confidence_Reason"] = _unread
with io.open(_np, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_ncols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _ncols} for r in _nrows])
_rc_num = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                         capture_output=True, text=True, cwd=HERE,
                         env=dict(ENV, FDT_DRAFT=_num_root,
                                  FDT_SHEET=os.path.join(TMP, "num.html"),
                                  FDT_CENSUS=os.path.join(_num_root,
                                                          "crop_visual_census.csv"),
                                  FDT_REGIONS=os.path.join(_num_root,
                                                           "validated_regions.csv")))
_num_reasons = ({r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_num_root, "block_reasons.csv"), encoding="utf-8"))}
    if _rc_num.returncode == 0 else {})
check("번호 없는 행이 있어도 빌드는 돈다", _rc_num.returncode == 0,
      (_rc_num.stderr or "")[-200:])
_nsaid = _num_reasons.get(_nbase["Draft_ID"], {})
check("번호를 못 읽은 행은 막힌다", _nsaid.get("Count_Blocked") == "1")
check("사유 표가 '번호가 필요하다'를 칸으로 적는다",
      _nsaid.get("Number_Would_Open") == "1", _nsaid.get("Number_Would_Open"))
check("그 행의 이유는 번호를 먼저 말한다 (사람이 할 수 있는 것)",
      "그림 번호를 읽지 못했습니다" in _nsaid.get("Reason", ""),
      _nsaid.get("Reason", "")[:60])
# 상자만 필요한 행과 번호만/둘 다 필요한 행이 갈라져야 두 칸이 서로 다른 것을
# 말합니다 - 한 칸을 다른 칸으로 적어도 둘 다 필요한 행에서는 티가 안 납니다.
_box_only = [k for k, r in _num_reasons.items()
             if r.get("Count_Blocked") == "1" and r.get("Box_Would_Open") == "1"
             and k != _nbase["Draft_ID"]]
check("상자만 필요한 행이 있고, 그 행에는 번호를 청하지 않는다",
      _box_only and all(_num_reasons[k].get("Number_Would_Open") == "0"
                        for k in _box_only),
      [(k[-6:], _num_reasons[k].get("Box_Would_Open"),
        _num_reasons[k].get("Number_Would_Open")) for k in _box_only[:4]])
# 그리고 그 행이 부르는 그림을 누가 세고 있는지 사유 표가 적는가. 여덟 행이
# "번호를 적어 주십시오"만 달고 왔고, 그 줄들이 부르는 그림은 전부 이 논문이
# 이미 세고 있었습니다 - 적어 주지 않으면 사람은 무엇을 그릴지 알 수 없습니다.
#
# 상황을 픽스처에서 만듭니다. 처음에는 "마침 그런 형제 행이 있으면"이라는 `if`
# 안에 두었는데, 그 조건이 늘 거짓이라 검사는 한 번도 돌지 않고 조용히
# 통과했습니다 - 실행되지 않는 시나리오는 시나리오가 아닙니다.
_hold, _holdnum = _hold_row["Draft_ID"], _hold_row["Figure_Number"]
check("(그 논문의 다른 행은 그 그림을 세고 있다)",
      _num_reasons.get(_hold, {}).get("Count_Blocked") == "0",
      (_hold, _num_reasons.get(_hold, {}).get("Reason", "")[:50]))
_nrows2 = list(csv.DictReader(io.open(_np, encoding="utf-8")))
for r in _nrows2:
    if r["Draft_ID"] == _nbase["Draft_ID"]:
        r["Caption_Text"] = "Figures %s and 99 show the effects" % (
            _holdnum.replace("FIG", ""),)
with io.open(_np, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_ncols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _ncols} for r in _nrows2])
_rc_h = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_DRAFT=_num_root,
                                FDT_SHEET=os.path.join(TMP, "held.html"),
                                FDT_CENSUS=os.path.join(_num_root,
                                                        "crop_visual_census.csv"),
                                FDT_REGIONS=os.path.join(_num_root,
                                                         "validated_regions.csv")))
_held = ({r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_num_root, "block_reasons.csv"), encoding="utf-8"))}
    if _rc_h.returncode == 0 else {})
_hv = _held.get(_nbase["Draft_ID"], {}).get("Mentions_Held", "")
check("사유 표가 그 그림을 세고 있는 행을 이름으로 적는다",
      _rc_h.returncode == 0 and _hold in _hv and _holdnum in _hv,
      (_rc_h.returncode, _hv, _hold, _holdnum))
check("이 논문에 없는 그림 번호는 적지 않는다", "FIG99" not in _hv, _hv)
check("다른 논문의 행을 끌어오지 않는다",
      all(v.split("=")[-1].startswith(_nbase["Source_Document_ID"])
          for v in _hv.split(";") if v), _hv)
# 다른 논문의 행은 끌어오지 않습니다. 앞의 검사는 같은 논문의 행이 먼저 나오면
# 통과해 버리므로, 그 번호가 **다른 논문에만** 있는 경우를 만듭니다.
_far = [k for k, r in _num_reasons.items()
        if r.get("Count_Blocked") == "0"
        and not k.startswith(_nbase["Source_Document_ID"])]
check("(픽스처에 다른 논문의 셀 수 있는 행이 있다)", bool(_far), list(_num_reasons))
_nrows3 = list(csv.DictReader(io.open(_np, encoding="utf-8")))
for r in _nrows3:
    if r["Draft_ID"] == _far[0]:
        r["Figure_Number"] = "FIG7"
    if r["Draft_ID"] == _nbase["Draft_ID"]:
        r["Caption_Text"] = "Figures 7 and 99 show the effects"
with io.open(_np, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_ncols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _ncols} for r in _nrows3])
_rc_f = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_DRAFT=_num_root,
                                FDT_SHEET=os.path.join(TMP, "far.html"),
                                FDT_CENSUS=os.path.join(_num_root,
                                                        "crop_visual_census.csv"),
                                FDT_REGIONS=os.path.join(_num_root,
                                                         "validated_regions.csv")))
_farheld = ({r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_num_root, "block_reasons.csv"), encoding="utf-8"))}
    if _rc_f.returncode == 0 else {})
_fv = _farheld.get(_nbase["Draft_ID"], {}).get("Mentions_Held", "")
check("그 번호가 다른 논문에만 있으면 아무도 세고 있지 않다고 답한다",
      _rc_f.returncode == 0 and _fv == "", (_rc_f.returncode, _fv))
# 그리고 원래 캡션으로 되돌립니다 - 다음 검사가 이 편집을 물려받지 않게.
for r in _nrows3:
    if r["Draft_ID"] == _nbase["Draft_ID"]:
        r["Caption_Text"] = "Figures %s and 99 show the effects" % (
            _holdnum.replace("FIG", ""),)
    if r["Draft_ID"] == _far[0]:
        r["Figure_Number"] = {x["Draft_ID"]: x["Figure_Number"]
                              for x in _nrows2}[_far[0]]
with io.open(_np, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_ncols)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _ncols} for r in _nrows3])

check("그리고 이 사실이 그 행을 막지는 않는다 (막힌 이유는 번호 그대로)",
      "그림 번호를 읽지 못했습니다"
      in _held.get(_nbase["Draft_ID"], {}).get("Reason", ""),
      _held.get(_nbase["Draft_ID"], {}).get("Reason", "")[:60])
check("번호가 있는 다른 행에는 번호를 청하지 않는다",
      all(r.get("Number_Would_Open") == "0"
          for k, r in _num_reasons.items() if k != _nbase["Draft_ID"]),
      [(k[-6:], r.get("Number_Would_Open")) for k, r in _num_reasons.items()
       if r.get("Number_Would_Open") == "1"])

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
                                                        "crop_visual_census.csv"),
                                FDT_REGIONS=os.path.join(root,
                                                         "validated_regions.csv")))
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

# ---------------------------------------------- 두 방법이 가리켜야 셀 수 있다
# 그림 영역은 세 제안자(글자 걸음·PDF 객체·래스터 잉크)가 각각 답하고, PDF와
# 래스터가 같은 곳을 가리키며 그곳이 지금 크롭일 때만(AGREE_3) 숫자를 받습니다.
def _regions_variant(name, agreement, validated=None):
    root = os.path.join(TMP, "reg_" + name)
    shutil.copytree(FX["draft"], root)
    rp = os.path.join(root, "validated_regions.csv")
    rows = list(csv.DictReader(io.open(rp, encoding="utf-8")))
    for r in rows:
        if r["Draft_ID"] == _target:
            r["Agreement"] = agreement
            if validated is not None:
                r["Validated_Figure_BBox"] = validated
    with io.open(rp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = os.path.join(TMP, "reg_%s.html" % name)
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_DRAFT=root, FDT_SHEET=out,
                                FDT_CENSUS=os.path.join(root, "crop_visual_census.csv"),
                                FDT_REGIONS=rp))
    text = ("\n".join(io.open(f, encoding="utf-8").read()
                      for f in _P.parts_for(out)) if r.returncode == 0 else "")
    return root, r, text


def _disabled(text, did):
    return re.search(r"<input[^>]*disabled[^>]*data-id='%s'" % re.escape(did),
                     text) is not None


def _open(text, did):
    return re.search(r"<input(?![^>]*disabled)[^>]*data-id='%s'" % re.escape(did),
                     text) is not None


_no_reg = subprocess.run(
    [sys.executable, os.path.join(HERE, "build_sheet2.py")],
    capture_output=True, text=True, cwd=HERE,
    env=dict(ENV, FDT_REGIONS=os.path.join(TMP, "no_such_regions.csv"),
             FDT_SHEET=os.path.join(TMP, "noreg.html")))
check("영역 검증표가 없으면 빌드가 멈춘다", _no_reg.returncode != 0)
check("멈추면서 만드는 명령과 밝히는 변수를 말한다",
      "validate_regions.py" in (_no_reg.stdout + _no_reg.stderr)
      and "FDT_REGIONS_OPTIONAL" in (_no_reg.stdout + _no_reg.stderr))
_waived_reg = subprocess.run(
    [sys.executable, os.path.join(HERE, "build_sheet2.py")],
    capture_output=True, text=True, cwd=HERE,
    env=dict(ENV, FDT_REGIONS=os.path.join(TMP, "no_such_regions.csv"),
             FDT_REGIONS_OPTIONAL="1", FDT_SHEET=os.path.join(TMP, "noreg2.html")))
check("아직 돌리지 않았다고 밝히면 빌드는 된다", _waived_reg.returncode == 0,
      (_waived_reg.stderr or "")[-200:])

check("AGREE_3인 행은 열려 있다",
      _open(_regions_variant("a3", "AGREE_3")[2], _target))
_dis = _regions_variant("dis", "DISAGREE")[2]
check("두 방법이 어긋난 행은 막힌다", _disabled(_dis, _target))
check("사유가 사람이 정해야 한다고 말한다", "REVIEW_REQUIRED" in _dis
      and "서로 다른 곳을" in _dis)
_a2 = _regions_variant("a2", "AGREE_2_TEXT_DIFFERS")[2]
check("두 방법은 일치하는데 크롭이 다른 행은 막힌다", _disabled(_a2, _target))
check("사유가 '다시 자르기 전에는'이라고 말한다", "다시 자르기 전에는" in _a2)
check("래스터만 답한 행은 막힌다",
      _disabled(_regions_variant("ro", "RASTER_ONLY")[2], _target))
check("PDF만 답한 행은 막힌다",
      _disabled(_regions_variant("po", "PDF_ONLY")[2], _target))
check("아무 방법도 답이 없는 행은 막힌다",
      _disabled(_regions_variant("none", "NONE")[2], _target))
_odd = _regions_variant("odd", "MOSTLY_FINE")[2]
check("모르는 합의 값은 통과가 아니라 차단이다", _disabled(_odd, _target))
check("그 사유가 값을 그대로 보여 준다", "MOSTLY_FINE" in _odd)
_id_a = re.search(r"sheet-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", _dis)
_id_b = re.search(r"sheet-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", _a2)
check("영역 검증표가 달라지면 빌드 ID가 달라진다",
      _id_a and _id_b and _id_a.group(0) != _id_b.group(0))

# ----------------------------------------------- 검증 상자로 다시 자르기
import hashlib as _hl                                            # noqa: E402
import apply_validated as AV                                     # noqa: E402

_tr = [d for d in _with_page if d["Draft_ID"] == _target][0]
_x0, _y0, _x1, _y1 = [float(v) for v in _tr["Figure_BBox"].split(",")]
# 같은 페이지 안의 다른 영역 - 실제 픽스처 그림이 있는 자리에서 20pt 안쪽으로
_new_box = "%.1f,%.1f,%.1f,%.1f" % (_x0 + 20, _y0 + 20, _x1 - 20, _y1 - 20)
_root_av, _, _ = _regions_variant("av", "AGREE_2_TEXT_DIFFERS", validated=_new_box)
_crop_path = os.path.join(_root_av, _tr["Figure_Crop"])
_sha_before = _hl.sha256(io.open(_crop_path, "rb").read()).hexdigest()
_rc_av = AV.main(_root_av)
_draft_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_root_av, "figure_intake_draft.csv"), encoding="utf-8"))}
_reg_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_root_av, "validated_regions.csv"), encoding="utf-8"))}
check("AGREE_2 행의 상자가 검증 상자로 바뀐다",
      _rc_av == 0 and _draft_after[_target]["Figure_BBox"] == _new_box,
      _draft_after[_target]["Figure_BBox"])
check("옛 상자는 Proposal_Figure_BBox에 남는다",
      _draft_after[_target]["Proposal_Figure_BBox"] == _tr["Figure_BBox"])
check("크롭 파일이 실제로 다시 잘렸다 (digest가 바뀜)",
      _hl.sha256(io.open(_crop_path, "rb").read()).hexdigest() != _sha_before)
check("다시 잘린 크롭은 새 상자에서 왕복한다",
      RT.check(_draft_after[_target], _root_av)[0] == "MATCH",
      RT.check(_draft_after[_target], _root_av))
check("영역 표는 이제 셋이 일치한다고 적는다",
      _reg_after[_target]["Agreement"] == "AGREE_3"
      and _reg_after[_target]["Recut_From"] == _tr["Figure_BBox"])
check("손대지 않은 행은 그대로다",
      all(_draft_after[d["Draft_ID"]]["Figure_BBox"] == d["Figure_BBox"]
          for d in DRAFT if d["Draft_ID"] != _target))
_r_after = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                          capture_output=True, text=True, cwd=HERE,
                          env=dict(ENV, FDT_DRAFT=_root_av,
                                   FDT_SHEET=os.path.join(TMP, "av.html"),
                                   FDT_CENSUS=os.path.join(_root_av, "crop_visual_census.csv"),
                                   FDT_REGIONS=os.path.join(_root_av, "validated_regions.csv")))
_av_text = "\n".join(io.open(f, encoding="utf-8").read()
                     for f in _P.parts_for(os.path.join(TMP, "av.html")))
check("다시 자른 뒤 그 행은 시트에서 열린다", _r_after.returncode == 0
      and _open(_av_text, _target), (_r_after.stderr or "")[-200:])
_sha_once = _hl.sha256(io.open(_crop_path, "rb").read()).hexdigest()
AV.main(_root_av)
check("두 번 돌려도 더 바뀌지 않는다",
      _hl.sha256(io.open(_crop_path, "rb").read()).hexdigest() == _sha_once)
# 검증 상자가 너무 작아 크롭이 나오지 않으면 건너뛰고 말한다
_root_tiny, _, _ = _regions_variant("tiny", "AGREE_2_TEXT_DIFFERS",
                                    validated="%.1f,%.1f,%.1f,%.1f"
                                    % (_x0, _y0, _x0 + 2, _y0 + 2))
AV.main(_root_tiny)
_tiny_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_root_tiny, "figure_intake_draft.csv"), encoding="utf-8"))}
check("크롭을 낼 수 없는 검증 상자는 적용하지 않는다",
      _tiny_after[_target]["Figure_BBox"] == _tr["Figure_BBox"])
# DISAGREE 행은 건드리지 않는다 - 사람의 몫
_root_d, _, _ = _regions_variant("keep", "DISAGREE", validated=_new_box)
AV.main(_root_d)
_d_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
    os.path.join(_root_d, "figure_intake_draft.csv"), encoding="utf-8"))}
check("DISAGREE 행은 검증 상자가 있어도 다시 자르지 않는다",
      _d_after[_target]["Figure_BBox"] == _tr["Figure_BBox"])
# THIN_CROP 행은 그 판정이 지금 크롭에 대한 것이므로 손대지 않는다
_thin_row = [d for d in _with_page if d["Crop_Quality_Status"] == "THIN_CROP"]
if _thin_row:
    _tid = _thin_row[0]["Draft_ID"]
    _root_t = os.path.join(TMP, "reg_thin")
    shutil.copytree(FX["draft"], _root_t)
    _rp_t = os.path.join(_root_t, "validated_regions.csv")
    _rows_t = list(csv.DictReader(io.open(_rp_t, encoding="utf-8")))
    for r in _rows_t:
        if r["Draft_ID"] == _tid:
            r["Agreement"] = "AGREE_2_TEXT_DIFFERS"
            r["Validated_Figure_BBox"] = _thin_row[0]["Figure_BBox"]
    with io.open(_rp_t, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_rows_t[0]))
        w.writeheader()
        w.writerows(_rows_t)
    AV.main(_root_t)
    _t_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(_root_t, "figure_intake_draft.csv"), encoding="utf-8"))}
    check("THIN_CROP 행은 AGREE_2여도 다시 자르지 않는다",
          "Crop_Source" not in _t_after[_tid] or
          _t_after[_tid].get("Crop_Source", "") == "")

# ------------------------------------------- 사람이 세 상자 중 하나를 고르면
def _choice_variant(name, agreement, choice, raster_box=None, pdf_box=None):
    root = os.path.join(TMP, "ch_" + name)
    shutil.copytree(FX["draft"], root)
    rp = os.path.join(root, "validated_regions.csv")
    rows = list(csv.DictReader(io.open(rp, encoding="utf-8")))
    cols = list(rows[0])
    if "Human_Choice" not in cols:
        cols.append("Human_Choice")
    for r in rows:
        r.setdefault("Human_Choice", "")
        if r["Draft_ID"] == _target:
            r["Agreement"] = agreement
            r["Human_Choice"] = choice
            if raster_box is not None:
                r["Raster_BBox"] = raster_box
            if pdf_box is not None:
                r["PDF_BBox"] = pdf_box
    with io.open(rp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return root


def _after(root):
    d = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(root, "figure_intake_draft.csv"), encoding="utf-8"))}
    g = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(root, "validated_regions.csv"), encoding="utf-8"))}
    out = os.path.join(root, "sheet.html")
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_sheet2.py")],
                       capture_output=True, text=True, cwd=HERE,
                       env=dict(ENV, FDT_DRAFT=root, FDT_SHEET=out,
                                FDT_CENSUS=os.path.join(root, "crop_visual_census.csv"),
                                FDT_REGIONS=os.path.join(root, "validated_regions.csv")))
    text = ("\n".join(io.open(f, encoding="utf-8").read()
                      for f in _P.parts_for(out)) if r.returncode == 0 else "")
    return d, g, text


_rc_root = _choice_variant("raster", "DISAGREE", "RASTER", raster_box=_new_box)
AV.main(_rc_root)
_d1, _g1, _t1 = _after(_rc_root)
check("사람이 RASTER를 고르면 DISAGREE 행이 래스터 상자로 다시 잘린다",
      _d1[_target]["Figure_BBox"] == _new_box and
      _d1[_target]["Crop_Source"] == "HUMAN_CHOICE_RASTER")
check("그 행은 HUMAN_VALIDATED가 되어 시트에서 열린다",
      _g1[_target]["Agreement"] == "HUMAN_VALIDATED" and _open(_t1, _target))
check("다시 잘린 크롭은 왕복한다", RT.check(_d1[_target], _rc_root)[0] == "MATCH")

_tx_root = _choice_variant("text", "DISAGREE", "TEXT")
AV.main(_tx_root)
_d2, _g2, _t2 = _after(_tx_root)
check("사람이 TEXT를 고르면 크롭은 그대로 두고 행만 연다",
      _d2[_target]["Figure_BBox"] == _tr["Figure_BBox"]
      and _g2[_target]["Agreement"] == "HUMAN_VALIDATED" and _open(_t2, _target))

_bl_root = _choice_variant("blocked", "AGREE_3", "BLOCKED")
AV.main(_bl_root)
_d3, _g3, _t3 = _after(_bl_root)
check("사람이 BLOCKED라고 하면 셋이 일치해도 막힌다",
      _g3[_target]["Agreement"] == "HUMAN_BLOCKED" and _disabled(_t3, _target))
check("그 사유가 사람의 판정이라고 말한다", "사람이 이 행의 그림 영역을" in _t3)

_bad_root = _choice_variant("typo", "DISAGREE", "raster?")
try:
    AV.main(_bad_root)
    _typo_stop = None
except SystemExit as exc:
    _typo_stop = str(exc)
check("Human_Choice에 모르는 값이 있으면 도구가 멈춘다",
      _typo_stop is not None and _target in _typo_stop, _typo_stop)

_ag_root = _choice_variant("agent", "DISAGREE", "")
_rp_ag = os.path.join(_ag_root, "validated_regions.csv")
_rows_ag = list(csv.DictReader(io.open(_rp_ag, encoding="utf-8")))
_cols_ag = list(_rows_ag[0]) + ["Agent_Choice"]
for r in _rows_ag:
    r["Agent_Choice"] = "RASTER" if r["Draft_ID"] == _target else ""
with io.open(_rp_ag, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols_ag)
    w.writeheader()
    w.writerows(_rows_ag)
AV.main(_ag_root)
_d4, _g4, _t4 = _after(_ag_root)
check("에이전트의 Agent_Choice만으로는 아무것도 열리지 않는다",
      _g4[_target]["Agreement"] == "DISAGREE" and _disabled(_t4, _target)
      and _d4[_target]["Figure_BBox"] == _tr["Figure_BBox"])

# ------------------------------------------------ 2단계: 화면이 파일을 보여 주는가
import display_checks as DC                                      # noqa: E402

_open_rows = [d for d in DRAFT if d["Figure_Crop"] and d["Page_Raster"]
              and not [r for r in ROWS_JSON if r["Draft_ID"] == d["Draft_ID"]
                       and r["Count_Blocked"] == "1"]] if "ROWS_JSON" in dir() else None
_probs, _seen = DC.check_run(FX["draft"], PARTS, DRAFT)
check("픽스처의 열린 카드가 확대·비율·페이지 상자 검사를 모두 통과한다",
      _probs == [] and _seen > 0, (_probs[:3], _seen))
_cards = [c for part in PARTS for c in DC.cards(io.open(part, encoding="utf-8").read())]
check("카드 수 = 초안 행 수 (파서가 카드를 빠뜨리지 않는다)",
      len(_cards) == len(DRAFT), (len(_cards), len(DRAFT)))
_with_zoom = [c for c in _cards if c["zoom"]]
check("열린 행에만 확대 이미지가 있다 (막힌 행은 없다)",
      len(_with_zoom) == _seen and 0 < _seen < len(DRAFT), (_seen, len(DRAFT)))

# 페이지 상자 검사가 실제로 거울을 잡는지: 좋은 카드에 뒤집힌 행을 대 본다.
_good = [c for c in _with_zoom if c["page"]][0]
_grow = [d for d in DRAFT if d["Draft_ID"] == _good["Draft_ID"]][0]
_ok_true, _det_true = DC.page_box_drawn_where_the_row_says(_good, _grow)
check("올바른 행에서는 빨간 상자가 네 변을 모두 덮는다", _ok_true, _det_true)
_ph = float(_grow["Page_Height_Pt"])
_bx0, _by0, _bx1, _by1 = [float(v) for v in _grow["Figure_BBox"].split(",")]
_mirrored = dict(_grow, Figure_BBox="%.1f,%.1f,%.1f,%.1f"
                 % (_bx0, _ph - _by1, _bx1, _ph - _by0))
_ok_mir, _det_mir = DC.page_box_drawn_where_the_row_says(_good, _mirrored)
check("아래 기준으로 뒤집힌 행에서는 검사가 실패한다", not _ok_mir, _det_mir)
_shifted = dict(_grow, Figure_BBox="%.1f,%.1f,%.1f,%.1f"
                % (_bx0 + 40, _by0 + 40, _bx1 + 40, _by1 + 40))
check("40pt 밀린 행에서도 실패한다",
      not DC.page_box_drawn_where_the_row_says(_good, _shifted)[0])

# 전체 경로: 한 카드의 페이지 뷰를 다른 행의 것으로 바꾼 HTML은 문제가 잡혀야 한다.
# 전체 경로: 페이지 뷰의 그림을 40px 아래로 밀어 다시 심은 HTML은 문제가 잡혀야
# 한다. (픽스처의 열린 두 행은 상자가 같은 자리라 서로 맞바꿔도 보이지 않는다.)
import base64 as _b64                                            # noqa: E402
_html0 = io.open(PARTS[0], encoding="utf-8").read()
_pv = DC.decode(_good["page"]).convert("RGB")
_moved = _Image.new("RGB", _pv.size, "white")
_moved.paste(_pv, (0, 40))
_buf = io.BytesIO()
_moved.save(_buf, "JPEG", quality=72)
_moved_uri = "data:image/jpeg;base64," + _b64.b64encode(_buf.getvalue()).decode("ascii")
_tmp_part = os.path.join(TMP, "moved.html")
io.open(_tmp_part, "w", encoding="utf-8").write(_html0.replace(_good["page"], _moved_uri, 1))
_p2, _ = DC.check_run(FX["draft"], [_tmp_part], DRAFT)
check("페이지 뷰 안의 상자가 40px 밀려 있으면 그 카드가 페이지 상자 문제로 잡힌다",
      any(d == _good["Draft_ID"] and n == "page_box" for d, n, _ in _p2), _p2)
_small = _html0.replace(_good["zoom"], _good["thumb"], 1)
io.open(_tmp_part, "w", encoding="utf-8").write(_small)
_p3, _ = DC.check_run(FX["draft"], [_tmp_part], DRAFT)
check("확대 이미지가 축소본이면 잡힌다",
      any(d == _good["Draft_ID"] and n == "zoom" for d, n, _ in _p3), _p3)
_sq = DC.decode(_good["thumb"]).convert("RGB").resize((300, 300))
_buf = io.BytesIO()
_sq.save(_buf, "JPEG", quality=58)
_sq_uri = "data:image/jpeg;base64," + _b64.b64encode(_buf.getvalue()).decode("ascii")
io.open(_tmp_part, "w", encoding="utf-8").write(_html0.replace(_good["thumb"], _sq_uri, 1))
_p4, _ = DC.check_run(FX["draft"], [_tmp_part], DRAFT)
check("썸네일이 비율을 잃으면 잡힌다",
      any(d == _good["Draft_ID"] and n == "thumb" for d, n, _ in _p4), _p4)

# ------------------------------- 제안자를 다시 돌려도 사람이 적은 것은 남는다
import validate_regions as VRG                                   # noqa: E402
_vr_root = os.path.join(TMP, "vr_keep")
shutil.copytree(FX["draft"], _vr_root)
_vr_path = os.path.join(_vr_root, "validated_regions.csv")
_vr_rows = list(csv.DictReader(io.open(_vr_path, encoding="utf-8")))
_vr_cols = list(_vr_rows[0]) + ["Human_Choice", "Human_Note", "Agent_Choice",
                                "Agent_Note", "Recut_On", "Recut_From"]
for r in _vr_rows:
    r.update(Human_Choice="", Human_Note="", Agent_Choice="", Agent_Note="",
             Recut_On="", Recut_From="")
    if r["Draft_ID"] == _target:
        r["Human_Choice"], r["Human_Note"] = "RASTER", "사람이 적은 메모"
        r["Agent_Choice"] = "PDF"
        r["Agreement"], r["Recut_On"] = "HUMAN_VALIDATED", "2026-09-02"
with io.open(_vr_path, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_vr_cols)
    w.writeheader()
    w.writerows(_vr_rows)
_vr_rc = VRG.main(_vr_root, 60)
_vr_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_vr_path, encoding="utf-8"))}
check("제안자를 다시 돌려도 Human_Choice와 메모가 남는다",
      _vr_after[_target].get("Human_Choice") == "RASTER"
      and _vr_after[_target].get("Human_Note") == "사람이 적은 메모",
      {k: _vr_after[_target].get(k) for k in ("Human_Choice", "Human_Note")})
check("에이전트 제안과 다시 자른 기록도 남는다",
      _vr_after[_target].get("Agent_Choice") == "PDF"
      and _vr_after[_target].get("Recut_On") == "2026-09-02")
check("사람이 확정한 합의(HUMAN_VALIDATED)는 기계가 되돌리지 못한다",
      _vr_after[_target].get("Agreement") == "HUMAN_VALIDATED",
      _vr_after[_target].get("Agreement"))
check("사람이 적지 않은 행은 빈칸 그대로다",
      all(_vr_after[d["Draft_ID"]].get("Human_Choice", "") == ""
          for d in DRAFT if d["Draft_ID"] != _target))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
