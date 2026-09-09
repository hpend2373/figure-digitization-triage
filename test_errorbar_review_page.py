# -*- coding: utf-8 -*-
"""판정 페이지가 사람에게 무엇을 내미는가.

    python3 test_errorbar_review_page.py     # exit 0 = all scenarios pass

이 페이지의 값은 답을 정하는 데 있지 않고 **묻는 방식**에 있습니다. 그래서
여기서 붙잡는 것도 계산이 아니라 화면의 성질입니다: 목록을 무엇이 정하는가,
종류 칸이 비어서 나가는가, 확인 칸이 눌린 채로 나가지는 않는가, 관문의 판정이
사람에게 보이는가.

브라우저 안의 움직임(라디오를 누르면 인용문이 채워진다)은 CI가 열 수 있는
브라우저가 없어 여기서 돌지 않습니다. 대신 그 움직임이 딛는 자리 - 이름이
겹치지 않는 속성 - 를 아래에서 붙잡습니다. 한 번 겹쳤고, 겹친 동안 화면은
인용문을 문서 이름으로 읽었습니다.
"""
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kernel                                                    # noqa: E402
import record_errorbar as RE                                     # noqa: E402
import errorbar_review_page as P                                 # noqa: E402

N = [0]
FAIL = []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


def write(path, columns, rows):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(dict((c, r.get(c, "")) for c in columns))


TMP = tempfile.mkdtemp(prefix="fdt-ebreview-")
RUN = os.path.join(TMP, "run")
os.makedirs(os.path.join(RUN, "crops"))

#: 인용문에 든 따옴표와 꺾쇠. 이것이 속성 밖으로 새면 카드 하나가 통째로
#: 깨지고, 깨진 카드는 답이 되지 않습니다.
NASTY = 'Bars are mean ± SD (n=6) <see "Methods">'

write(os.path.join(RUN, P.DRAFT),
      ["Draft_ID", "Source_Document_ID", "Source_File", "Page",
       "Figure_Number", "Figure_Crop"],
      [{"Draft_ID": "d1", "Source_Document_ID": "A", "Source_File": "a.pdf",
        "Page": "3", "Figure_Number": "FIG1",
        "Figure_Crop": os.path.join("crops", "a1.png")},
       {"Draft_ID": "d2", "Source_Document_ID": "A", "Source_File": "a.pdf",
        "Page": "4", "Figure_Number": "FIG2",
        "Figure_Crop": os.path.join("crops", "gone.png")},
       {"Draft_ID": "d3", "Source_Document_ID": "B", "Source_File": "b.pdf",
        "Page": "2", "Figure_Number": "FIG1",
        "Figure_Crop": os.path.join("crops", "b1.png")},
       {"Draft_ID": "d9", "Source_Document_ID": "Z", "Source_File": "z.pdf",
        "Page": "9", "Figure_Number": "FIG1",
        "Figure_Crop": os.path.join("crops", "b1.png")},
       {"Draft_ID": "dbad", "Source_Document_ID": "A", "Source_File": "a.pdf",
        "Page": "3", "Figure_Number": "FIG2",
        "Figure_Crop": os.path.join("crops", "b1.png")}])

write(os.path.join(RUN, P.QUEUE),
      ["Source_Document_ID", "Dispersion_Type", "Errorbar_Definition_Source",
       "Found_On_Page", "Verified_In_Source", "참고_그림", "참고_쪽",
       "참고_원본파일", "참고_기계가본것", "참고_찾을만한곳"],
      [{"Source_Document_ID": "A", "참고_그림": "FIG1, FIG2", "참고_쪽": "3, 4",
        "참고_원본파일": "a.pdf", "참고_기계가본것": "AMBIGUOUS"},
       {"Source_Document_ID": "B", "참고_그림": "FIG1", "참고_쪽": "2",
        "참고_원본파일": "b.pdf", "참고_기계가본것": "NOT_FOUND",
        "참고_찾을만한곳": "p2: mean age 29.3 ± 3.8 years"}])

write(os.path.join(RUN, P.CANDIDATES),
      ["Source_Document_ID", "Dispersion_Type", "Errorbar_Definition_Source",
       "Found_On_Page", "후보순위", "근거자리", "이문장이설명하는것", "쪽대조",
       "왜애매한가"],
      [{"Source_Document_ID": "A", "Dispersion_Type": "SD",
        "Errorbar_Definition_Source": NASTY, "Found_On_Page": "3",
        "후보순위": "1", "근거자리": "캡션",
        "이문장이설명하는것": "Fig.1의 오차 막대"},
       {"Source_Document_ID": "A", "Dispersion_Type": "SE",
        "Errorbar_Definition_Source": "Errors are standard errors.",
        "Found_On_Page": "3", "후보순위": "2", "근거자리": "본문",
        "왜애매한가": "어느 그림인지 안 말함"}])

#: 계수가 끝나기 전에 만들어진 목록. 여기에만 있는 논문이 페이지에 나오면
#: 사람은 계획에 없는 일을 합니다.
write(os.path.join(RUN, "errorbar_unstated.csv"),
      ["Source_Document_ID", "Draft_ID", "Page", "Figure_Number"],
      [{"Source_Document_ID": "Z", "Draft_ID": "d9", "Page": "9",
        "Figure_Number": "FIG1"}])

#: 그림마다 묻는 페이지가 읽는 두 파일. 하나는 캡션, 하나는 계수 상태입니다.
write(os.path.join(RUN, P.CAPTIONS),
      ["Draft_ID", "Source_Document_ID", "Page", "Figure_Number", "Caption_Line",
       "Caption_Full", "Caption_Full_Status", "Errorbar_Definition",
       "Doc_Errorbar_Definition", "Doc_Errorbar_Evidence", "Doc_Errorbar_Page"],
      [{"Draft_ID": "d1", "Source_Document_ID": "A", "Page": "3",
        "Figure_Number": "FIG1", "Caption_Line": "Fig. 1. 온전한 캡션.",
        "Caption_Full": "Fig. 1. 온전한 캡션.", "Caption_Full_Status": "BLOCK",
        "Errorbar_Definition": "UNSTATED",
        "Doc_Errorbar_Definition": "SEM",
        "Doc_Errorbar_Evidence": "Data are mean ± s.e.m for bar plots",
        "Doc_Errorbar_Page": "18"},
       # 쪽 글자층에 캡션이 없어 전문을 못 읽은 행. 인테이크가 잡은 줄만 있습니다.
       {"Draft_ID": "d2", "Source_Document_ID": "A", "Page": "4",
        "Figure_Number": "FIG2",
        "Caption_Line": "Fig. 2 | 인테이크만 잡은 줄.",
        "Caption_Full": "", "Caption_Full_Status": "BLOCK_NOT_FOUND",
        "Errorbar_Definition": ""},
       {"Draft_ID": "d3", "Source_Document_ID": "B", "Page": "2",
        "Figure_Number": "FIG1", "Caption_Line": "Fig. 1. 다른 논문.",
        "Caption_Full": "Fig. 1. 다른 논문.", "Caption_Full_Status": "BLOCK",
        "Errorbar_Definition": "UNSTATED"}])

write(os.path.join(RUN, P.COUNTS),
      ["Draft_ID", "Source_Document_ID", "Page", "Figure_Number",
       "Observed_Panel_Count", "Entry_Status"],
      [{"Draft_ID": "d1", "Source_Document_ID": "A", "Page": "3",
        "Figure_Number": "FIG1", "Observed_Panel_Count": "6",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "d2", "Source_Document_ID": "A", "Page": "4",
        "Figure_Number": "FIG2", "Observed_Panel_Count": "2",
        "Entry_Status": "ENTERED"},
       # 같은 그림 번호에 잡힌 나쁜 크롭. 계수 단계가 이미 걸렀습니다.
       {"Draft_ID": "dbad", "Source_Document_ID": "A", "Page": "3",
        "Figure_Number": "FIG2", "Observed_Panel_Count": "",
        "Entry_Status": "BLOCKED_BAD_CROP"}])

from PIL import Image                                            # noqa: E402
Image.new("RGB", (40, 30), (200, 40, 40)).save(
    os.path.join(RUN, "crops", "a1.png"))
Image.new("RGB", (40, 30), (40, 40, 200)).save(
    os.path.join(RUN, "crops", "b1.png"))

OUT = os.path.join(TMP, "judge.html")
RUN_CMD = subprocess.run(
    [sys.executable, os.path.join(HERE, "errorbar_review_page.py"),
     "--run", RUN, "--out", OUT],
    capture_output=True, text=True,
    env=dict(os.environ, PYTHONPYCACHEPREFIX=os.path.join(TMP, "pyc")))
check("페이지가 만들어진다",
      RUN_CMD.returncode == 0 and os.path.exists(OUT),
      "rc=%s %s" % (RUN_CMD.returncode, (RUN_CMD.stderr or "")[-300:]))
HTML = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""

# ------------------------------------------------------------------- 목록

# REVERT: 목록을 `errorbar_unstated.csv`가 정하게 한다. 그 파일은 계수가 끝나기
# 전에 만들어졌고 계획에서 빠진 논문까지 들고 있습니다 - 실제로 27편이어야 할
# 목록이 31편으로 나왔고, 남은 네 편은 아무도 답할 이유가 없는 논문이었습니다.
check("목록은 답안지가 정한다",
      "data-doc='A'" in HTML and "data-doc='B'" in HTML
      and "data-doc='Z'" not in HTML,
      "Z가 페이지에 있습니다" if "data-doc='Z'" in HTML else HTML[:200])

check("화면이 아는 문서와 카드가 같다",
      'var DOCS = ["A", "B"]' in HTML or 'var DOCS = ["B", "A"]' in HTML,
      [l for l in HTML.splitlines() if l.startswith("var DOCS")][:1])

check("그림은 답안지가 적어 준 것만, 없는 크롭은 없다고 적는다",
      HTML.count("class='fig'") == 3 and HTML.count("크롭 없음") == 1
      and HTML.count("data:image/jpeg;base64,") == 2,
      "그림칸 %d · 크롭없음 %d · 그림 %d"
      % (HTML.count("class='fig'"), HTML.count("크롭 없음"),
         HTML.count("data:image/jpeg;base64,")))

# ------------------------------------------------------------- 비워서 낸다

# REVERT: 후보의 종류를 골라 둔 채로 낸다. 그러면 사람이 하는 일은 판정이 아니라
# 동의가 되고, 후보를 낸 것이 무엇이든 - 규칙이든 다른 모형이든 - 그 답이
# 사람의 답으로 기록됩니다.
check("종류 칸은 아무것도 고르지 않은 채로 나간다",
      "selected" not in HTML and "<option value=''>고르지 않음</option>" in HTML)

# REVERT: 확인 칸을 눌린 채로 낸다. `Verified_In_Source`는 "내가 원문을 보았다"는
# 사람의 진술이고, 이 페이지가 있는 이유가 그 진술을 사람에게서만 받는 것입니다.
_verify = [l for l in HTML.splitlines() if "data-verified=" in l
           and "checkbox" in l]
check("확인 칸은 눌린 채로 나가지 않는다",
      len(_verify) == 2 and all("checked" not in l for l in _verify),
      _verify)

# ------------------------------------------------------------- 이름이 겹치지 않음

# REVERT: 라디오가 인용문을 `data-quote`에, 쪽을 `data-page`에 싣는다. 적는 칸과
# 이름이 같아지고, 화면이 문서 이름을 읽는 자리에서 라디오까지 붙잡아 인용문을
# 문서 이름으로 읽습니다. 그렇게 읽힌 이름은 `Source_Document_ID`가 되어 답
# CSV로 나가고, 관문은 그런 문서가 없다고만 합니다.
_radios = [l for l in HTML.splitlines() if "type='radio'" in l]
check("후보 라디오는 적는 칸과 다른 이름으로 인용문을 싣는다",
      bool(_radios)
      and all("data-quote=" not in l and "data-page=" not in l for l in _radios)
      and any("data-qtext=" in l and "data-ptext=" in l for l in _radios),
      _radios[:1])

check("따옴표와 꺾쇠가 든 인용문도 속성 밖으로 새지 않는다",
      "&quot;Methods&quot;" in HTML and "&lt;see" in HTML
      and NASTY not in HTML)

# --------------------------------------------------------------- 관문의 말

BLOCKS = [(3, 0, 0, 1, 1, "Bars are mean ± SD (n=6) <see \"Methods\">")]


def _verdicts(rows):
    keep = RE.read_source
    RE.read_source = lambda run, doc, root: (RE.Source(BLOCKS), "")
    try:
        return P.verdicts(RUN, "어딘가", rows)
    finally:
        RE.read_source = keep


_said = _verdicts([
    {"Source_Document_ID": "A", "Dispersion_Type": "SD",
     "Errorbar_Definition_Source": NASTY, "Found_On_Page": "3"},
    {"Source_Document_ID": "A", "Dispersion_Type": "SD",
     "Errorbar_Definition_Source": "Bars are mean ± SD, said nowhere.",
     "Found_On_Page": "3"},
])

# REVERT: 진단용 `Verified_In_Source='1'`을 빼고 후보를 그대로 관문에 넘긴다.
# 그러면 모든 후보의 판정이 `NOT_VERIFIED_BY_PERSON` 하나가 되고 - 사람이 아직
# 아무것도 안 눌렀으니 당연히 - 정작 보여 주려던 인용문 문제가 가려집니다.
# 사람은 고르고 나서야 그 문장이 논문에 없다는 말을 듣습니다.
check("관문의 판정은 인용문의 문제를 말한다",
      _said.get(0, ("", ""))[0] == "OK"
      and _said.get(1, ("", ""))[0] == "QUOTE_NOT_IN_SOURCE",
      _said)

check("판정을 대볼 원문이 없으면 아무 판정도 적지 않는다",
      P.verdicts(RUN, "", [{"Source_Document_ID": "A",
                            "Dispersion_Type": "SD"}]) == {})

# ------------------------------------------------------------------ 한 낱말

check("페이지가 내미는 종류는 계획서가 받는 종류다",
      all(("<option value='%s'>" % t) in HTML
          for t in kernel.FIG_DISPERSION_TYPES)
      and "<option value='DROP'>" in HTML)

_js = io.open(os.path.join(HERE, P.LOGIC), encoding="utf-8").read()
check("결정 파일의 종류도 같은 종류다",
      ("var TYPES = ['%s'];" % "', '".join(kernel.FIG_DISPERSION_TYPES)) in _js,
      [l for l in _js.splitlines() if l.startswith("var TYPES")][:1])

check("결정은 페이지 안에 실려 있다",
      "function answerOf" in HTML and "function buildCsv" in HTML)

# ------------------------------------------------- 그림마다 묻는 페이지

_FIGHTML, _FIGN = P.build_figures(RUN, ["A"], "", log=lambda *_a: None)

# REVERT: 초안을 그대로 편다. 한 그림 번호에 후보 크롭이 여럿 잡히고 계수 단계가
# 그중 하나만 남기는데, 초안을 그대로 펴면 이미 처리된 중복이 사람 앞에 다시
# 나타납니다. 실제로 그렇게 나타났고, 계획서에는 없는 문제를 있다고 보고했습니다.
check("차단된 크롭은 그림마다 묻는 페이지에 나오지 않는다",
      _FIGN == 2 and "dbad" not in _FIGHTML,
      "그림 %d개" % _FIGN)

check("열쇠는 논문::그림이고 이름은 META가 들고 있다",
      "data-doc='A::FIG1'" in _FIGHTML
      and '"A::FIG1": {"doc": "A", "figure": "FIG1"}' in _FIGHTML,
      [l for l in _FIGHTML.splitlines() if l.startswith("var META")][:1])

# REVERT: 캡션 전문이 없으면 아무것도 적지 않는다. 파이프라인은 확인되지 않은
# 줄을 `Caption_Full`로 승격하지 않는데(그건 옳습니다), 화면에서까지 감추면
# 사람은 빈칸을 보고 "논문이 아무 말도 안 했다"와 "우리가 못 읽었다"를 구별할
# 수 없습니다.
check("캡션 전문을 못 읽었으면 인테이크의 줄을 밝히고 보여 준다",
      "캡션 전문을 읽지 못했습니다" in _FIGHTML
      and "인테이크만 잡은 줄" in _FIGHTML
      and "BLOCK_NOT_FOUND" in _FIGHTML)

check("논문의 문서 진술을 머리에 걸어 둔다",
      "Data are mean ± s.e.m for bar plots" in _FIGHTML)

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
