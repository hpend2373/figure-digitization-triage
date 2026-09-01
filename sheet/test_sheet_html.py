# -*- coding: utf-8 -*-
"""Checks on the built sheet. Each one is a finding from the second audit.

These assert on the shipped file, not on the builder's variables, because the
defect the audit found was in what reached the page.
"""
import collections
import csv
import io
import json
import re
import os
import sys

import paths as PATHS

# THE SHEET IS SEVERAL FILES NOW. The crops ride at the resolution they were
# cut at, so it fills to a byte budget and starts a new file; these checks are
# about the corpus, which is spread across all of them.
SHEET = "\n".join(io.open(f, encoding="utf-8").read()
                  for f in PATHS.parts_for(PATHS.SHEET))
DRAFT = list(csv.DictReader(io.open(
    os.path.join(PATHS.DRAFT, "figure_intake_draft.csv"), encoding="utf-8")))
LEDGER = list(csv.DictReader(io.open(
    os.path.join(PATHS.DRAFT, "intake_document_status.csv"), encoding="utf-8")))
WORK = list(csv.DictReader(io.open(PATHS.WORKLIST, encoding="utf-8")))

ran = failed = 0


def check(name, cond, detail=""):
    global ran, failed
    ran += 1
    if cond:
        print("ok    " + name)
    else:
        failed += 1
        print("FAIL  " + name + ("\n      " + str(detail) if detail else ""))


ids = re.findall(r"<div class='fig[^']*' data-id='([^']+)'", SHEET)
cards = re.findall(r"<h2>pid (\d+) ·", SHEET)
ROWS = json.loads(re.search(r"const ROWS=(\[.*?\]);const BUILD_ID=",
                            SHEET, re.S).group(1))

# --- W2: every document gets a card -----------------------------------------
check("문서 102편이 모두 카드를 가진다 (감사 지적: 94)",
      len(cards) == 102, "cards=%d" % len(cards))
check("카드 pid 집합이 워크리스트와 정확히 같다",
      sorted(cards, key=int) == sorted((w["pid"] for w in WORK), key=int))
# derived, not pinned: which documents produced no row is a property of the
# draft, and a walk that recovers one must not need this file edited to pass
_with_rows = {d["Source_Document_ID"] for d in DRAFT}
_empty = [L for L in LEDGER if L["Source_Document_ID"] not in _with_rows]
check("후보 0행 문서 %d편에 안내 블록이 있다" % len(_empty),
      SHEET.count("캡션 후보가 0행입니다") == len(_empty),
      "%d vs %d" % (SHEET.count("캡션 후보가 0행입니다"), len(_empty)))
_empty_docs = {L["Source_Document_ID"] for L in _empty}
# 124/416/710 were the documents no backend had read. The walk now retries
# with the other one, so they carry rows - and a card with rows must NOT be
# claiming its figures are missing.
_recovered = ("124", "416", "710", "147")
# bounded to that one card: a non-greedy match across the whole page finds
# the next document's empty block and calls it this one's
def _card(pid):
    m = re.search(r"<div class='doc'><h2>pid %s ·.*?(?=<div class='doc'>|$)"
                  % pid, SHEET, re.S)
    return m.group(0) if m else ""
for _pid in _recovered:
    check("캡션을 되찾은 pid %s는 더 이상 0행 안내를 달지 않는다" % _pid,
          "캡션 후보가 0행입니다" not in _card(_pid))
check("래스터가 없는 원문은 여전히 안내를 단다 — 문구를 지운 것이 아님",
      "캡션 후보가 0행입니다" in _card("82"))

# --- W3: a blank Page_Count is never printed as 0 ---------------------------
check("어떤 카드에도 '0쪽'이 없다 (감사 지적: 8편)",
      not re.search(r"(?<![0-9])0쪽", SHEET),
      re.findall(r".{30}(?<![0-9])0쪽", SHEET)[:3])
check("자릿수가 있는 쪽수는 정상 표시된다 — 위 검사가 '쪽' 자체를 지운 것이 아님",
      re.search(r"· 10쪽", SHEET) is not None)
blank = [L for L in LEDGER if not L["Page_Count"].strip()]
check("쪽수가 빈 12편은 '쪽수 없음'으로 표시된다",
      SHEET.count("쪽수 없음") == len(blank),
      "%d vs %d" % (SHEET.count("쪽수 없음"), len(blank)))

# --- no aggregate figure count anywhere -------------------------------------
check("고유 figure 합계가 페이지 어디에도 없다",
      not re.search(r"고유\s*(figure|라벨)", SHEET))
# what a reader actually sees: no scripts, no styles, no attributes
VISIBLE = re.sub(r"<[^>]+>", " ",
                 re.sub(r"<(script|style).*?</\1>", "", SHEET, flags=re.S))
check("화면에 보이는 곳 어디에도 448이라는 집계가 없다",
      "448" not in VISIBLE, re.findall(r".{30}448", VISIBLE)[:3])
check("집계를 대신할 행 수 표기는 있다 — 숫자를 통째로 지운 것이 아님",
      ("캡션 후보 %d행" % len(DRAFT)) in VISIBLE)

# --- W9: the intake's own doubt reaches the screen --------------------------
sent = list(csv.DictReader(io.open(
    os.path.join(PATHS.AUDIT, "sentence_warning_rows.csv"),
    encoding="utf-8-sig")))
_ids = {d["Draft_ID"] for d in DRAFT}
_sent_here = [r for r in sent if r["draft_id"] in _ids]
check("초안에 남아 있는 본문 문장 의심 %d행에 배지가 붙는다" % len(_sent_here),
      SHEET.count("본문 문장 의심") == len(_sent_here),
      "%d vs %d" % (SHEET.count("본문 문장 의심"), len(_sent_here)))
check("모든 행에 신뢰도가 표시된다",
      len(re.findall(r"신뢰도 \d\.\d\d", SHEET)) == len(DRAFT),
      len(re.findall(r"신뢰도 \d\.\d\d", SHEET)))
low = sum(1 for d in DRAFT if float(d["Confidence"]) < 0.6)
check("저신뢰 36행은 강조 배지를 받는다",
      SHEET.count("badge b-low") == low,
      "%d vs %d" % (SHEET.count("badge b-low"), low))

# --- W7: a crop the audit failed takes no number -----------------------------
defects = list(csv.DictReader(io.open(
    os.path.join(PATHS.AUDIT, "confirmed_image_defects.csv"),
    encoding="utf-8-sig")))
byid = {r["Draft_ID"]: r for r in ROWS}

# KEYED ON THE DOCUMENT'S OWN LABEL, not on the row ordinal. Checking the
# audit's Draft_ID is what let three wrong crops sit with their inputs open
# while eight fixed ones stayed blocked: recovering a caption shifts every
# later _D0NN in that document.
import urllib.parse
_pid_of = {}
for _w in WORK:
    _p = urllib.parse.unquote(_w["href"][len("file://"):]).replace(
        "/Users/minyeop/", "/mnt/user-data/uploads/")
    for _L in LEDGER:
        if _L["Input_Path"] == _p:
            _pid_of[_L["Source_Document_ID"]] = _w["pid"]
            break


def _rows_for(pid, label, page):
    return [r for r in ROWS
            if _pid_of.get(r["Source_Document_ID"]) == pid
            and r["Figure_Number"] == label and r["Page"] == page]


_fail_keys = [(d["pid"], d["label"], d["page"]) for d in defects
              if d["classification"] == "FAIL"]
_open_fails = [k for k in _fail_keys
               if not _rows_for(*k) or _rows_for(*k)[0]["Count_Blocked"] != "1"]
check("2차 감사 FAIL %d건이 모두 입력 차단이다 (라벨 기준)" % len(_fail_keys),
      not _open_fails, _open_fails)

#: What the third audit judged still wrong after the crop round.
_STILL = [("437", "FIG2", "176"), ("516", "FIG5", "6"), ("99", "FIG1", "4"),
          ("554", "FIG4", "5"), ("700", "FIG1", "3"), ("397", "FIG1", "4"),
          ("518", "FIG1", "3"), ("159", "FIG3", "5")]
_open_still = [k for k in _STILL
               if not _rows_for(*k) or _rows_for(*k)[0]["Count_Blocked"] != "1"]
check("3차 감사가 여전히 틀렸다고 한 %d건도 모두 차단이다" % len(_STILL),
      not _open_still, _open_still)
check("차단 판단이 Draft_ID 순번에 걸려 있지 않다",
      "Figure_Number" in SHEET and not re.search(r"DEFECT\.get\(d\[.Draft_ID", SHEET))
fails = {r["Draft_ID"] for r in ROWS
         if any(_pid_of.get(r["Source_Document_ID"]) == k[0]
                and r["Figure_Number"] == k[1] and r["Page"] == k[2]
                for k in _fail_keys)}
thin = {d["Draft_ID"] for d in DRAFT if d["Crop_Quality_Status"] == "THIN_CROP"}
check("THIN_CROP 151행이 모두 입력 차단이다",
      all(byid[i]["Count_Blocked"] == "1" for i in thin))
nocrop = {d["Draft_ID"] for d in DRAFT if d["Crop_Quality_Status"] == "NO_CROP"}
check("이미지 없는 45행이 모두 입력 차단이다",
      all(byid[i]["Count_Blocked"] == "1" for i in nocrop))
clipped = {d["Draft_ID"] for d in DRAFT
           if d["Crop_Quality_Status"] == "EDGE_CLIPPED"}
check("그림을 자르는 크롭 %d행이 모두 입력 차단이다" % len(clipped),
      all(byid[i]["Count_Blocked"] == "1" for i in clipped))
# the shipped set, and the categories that must be inside it
blocked = {r["Draft_ID"] for r in ROWS if r["Count_Blocked"] == "1"}
_must = fails | thin | nocrop | clipped
check("차단 집합이 그 네 범주를 모두 포함한다",
      _must <= blocked, sorted(_must - blocked)[:5])
check("차단 행 수만큼 disabled 입력칸이 있다",
      len(re.findall(r"<input type='number' disabled", SHEET)) == len(blocked),
      "%d vs %d" % (len(re.findall(r"<input type='number' disabled", SHEET)),
                    len(blocked)))
check("나머지 %d행은 차단되지 않는다 — 전부 막아 버린 것이 아님"
      % (len(DRAFT) - len(blocked)),
      sum(1 for r in ROWS if r["Count_Blocked"] == "0")
      == len(DRAFT) - len(blocked),
      sum(1 for r in ROWS if r["Count_Blocked"] == "0"))
_shared = re.findall(r"픽셀까지 같습니다", SHEET)
check("크롭이 픽셀까지 같은 행은 어느 쪽인지 알 수 없으므로 차단된다",
      len(_shared) >= 2, len(_shared))

# 4차 감사: 원문에 있는데 초안에 없던 캡션 2건이 노출되고, 노출된 채로 차단됨
_zero = [d for d in DRAFT if d["Confidence"] == "0.00"]
check("기계가 신뢰도 0으로 표시한 %d행이 모두 차단이다" % len(_zero),
      all(byid[d["Draft_ID"]]["Count_Blocked"] == "1" for d in _zero),
      [d["Draft_ID"] for d in _zero
       if byid[d["Draft_ID"]]["Count_Blocked"] != "1"])
_nonum = [d for d in DRAFT if not d["Figure_Number"]]
check("그림 번호를 읽지 못한 %d행이 모두 차단이다" % len(_nonum),
      all(byid[d["Draft_ID"]]["Count_Blocked"] == "1" for d in _nonum))
check("pid 563 FIG6이 초안에 있다 — 4차 감사가 원문에서 확인한 캡션",
      any(_pid_of.get(d["Source_Document_ID"]) == "563"
          and d["Figure_Number"] == "FIG6" and d["Page"] == "7"
          for d in DRAFT))
check("pid 554의 읽지 못한 캡션이 번호 없이라도 초안에 있다",
      any(_pid_of.get(d["Source_Document_ID"]) == "554"
          and not d["Figure_Number"] and d["Page"] == "3" for d in DRAFT))
check("둘 다 화면에서 사유와 함께 보인다",
      "기계가 스스로 신뢰도 0으로" in SHEET
      and "그림 번호를 읽지 못했습니다" in SHEET)
check("0 신뢰도 차단이 시트를 비우지 않았다 — 여전히 400행 넘게 입력 가능",
      sum(1 for r in ROWS if r["Count_Blocked"] == "0") > 400,
      sum(1 for r in ROWS if r["Count_Blocked"] == "0"))
check("차단이 과반을 넘지 않는다 — 안전을 이유로 시트를 비우지 않았다",
      len(blocked) < len(DRAFT) * 0.6, "%d/%d" % (len(blocked), len(DRAFT)))
check("차단 행마다 이유가 적혀 있다",
      SHEET.count("입력을 막았습니다") == len(blocked))

# --- W5/W6 regressions: the binding the audit passed ------------------------
check("그림 블록 수 = 초안 행 수", len(ids) == len(DRAFT), len(ids))
check("Draft_ID 중복 없음", len(ids) == len(set(ids)))
check("ROWS 길이 = 초안 행 수", len(ROWS) == len(DRAFT))
check("ROWS의 Draft_ID 집합 = DOM의 Draft_ID 집합",
      {r["Draft_ID"] for r in ROWS} == set(ids))
check("모든 블록에 지문이 실려 있다",
      len(re.findall(r"data-fp='[0-9a-f]{12}'", SHEET)) == len(DRAFT))
check("지문은 행마다 고유하다",
      len({r["Row_Fingerprint"] for r in ROWS}) == len(ROWS))
check("입력칸의 data-id가 블록의 data-id와 짝을 이룬다",
      set(re.findall(r"<input type='number'[^>]*data-id='([^']+)'", SHEET))
      == set(ids))
check("위치로 값을 맞추는 코드가 없다",
      not re.search(r"ROWS\[\s*i\s*\]\s*\]|inputs\[\s*idx", SHEET))

# --- W10: the sheet proposes nothing ----------------------------------------
check("미리 채워진 값이 없다", len(re.findall(r"<input[^>]*\bvalue=", SHEET)) == 0)
check("placeholder로 숫자를 흘리지 않는다",
      len(re.findall(r"<input[^>]*placeholder=", SHEET)) == 0)

# --- W11: self-contained, and storage failure is visible --------------------
body = re.sub(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+", "", SHEET)
check("외부 요청이 없다",
      not re.search(r"https?://|\bfetch\s*\(|XMLHttpRequest|@import", body),
      re.findall(r"https?://[^\s'\"]+", body)[:3])
check("저장소 실패를 사용자에게 알리는 경로가 있다",
      "showStorageWarning" in SHEET and "storagewarn" in SHEET)
check("저장소를 쓰기로 탐지한다 (읽기 성공만 믿지 않음)",
      "::probe" in SHEET)
check("저장 키에 빌드 ID가 들어간다",
      "fdt_panel_counts::' + BUILD_ID" in SHEET)
check("빈 catch로 실패를 삼키지 않는다",
      len(re.findall(r"catch\s*\([^)]*\)\s*\{\s*\}", SHEET)) <= 1,
      re.findall(r"catch\s*\([^)]*\)\s*\{\s*\}", SHEET))

print("\n%d/%d passed" % (ran - failed, ran))
sys.exit(1 if failed else 0)
