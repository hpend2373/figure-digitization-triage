# -*- coding: utf-8 -*-
"""Scenarios for the page a person decides the 149 rows on.

    python3 test_review_sheet.py

Built from `make_fixture` plus a queue written here, so it runs without the
corpus. What it asks is what the counting sheet's suite asks of the sheet:
that every queued row is on the page exactly once, that nothing is preselected,
that a stored answer cannot outlive the pictures it was made on, and that the
export is something `review_packet.py merge` can read back.
"""
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_fixture                                              # noqa: E402
import review_sheet as RS                                        # noqa: E402
import review_packet as RP                                       # noqa: E402

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % (detail,)))
    if not ok:
        FAIL.append(name)


TMP = tempfile.mkdtemp(prefix="fdt-review-")
FX = make_fixture.write(os.path.join(TMP, "fx"))
RUN = FX["draft"]
DRAFT = list(csv.DictReader(io.open(
    os.path.join(RUN, "figure_intake_draft.csv"), encoding="utf-8")))
WITH_PAGE = [d for d in DRAFT if d["Figure_Crop"] and d["Page_Raster"]]

#: A queue whose rows carry three different boxes, so the three cut pictures
#: are three different pictures and a scenario can tell them apart.
os.makedirs(os.path.join(RUN, "review"), exist_ok=True)
import hashlib                                                    # noqa: E402


def _sha(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


QUEUE = []
for i, d in enumerate(WITH_PAGE[:3], 1):
    x0, y0, x1, y1 = [float(v) for v in d["Figure_BBox"].split(",")]
    QUEUE.append({
        "No": str(i), "Sheet": "review_01.png", "Draft_ID": d["Draft_ID"],
        "Source_Document_ID": d["Source_Document_ID"], "Page": d["Page"],
        "Figure_Number": d["Figure_Number"], "Agreement": "DISAGREE",
        "PDF_Code": "OK", "Raster_Code": "OK",
        "Proposal_Figure_BBox": d["Figure_BBox"],
        "PDF_BBox": "%.1f,%.1f,%.1f,%.1f" % (x0 + 10, y0 + 10, x1 - 10, y1 - 10),
        "Raster_BBox": "" if i == 3 else
                       "%.1f,%.1f,%.1f,%.1f" % (x0 + 20, y0 + 20, x1 - 20, y1 - 20),
        # 실제 크롭의 digest여야 merge의 대조가 뜻을 가집니다 - 가짜 값을 넣으면
        # 모든 행이 거부되고, 반영 경로를 지키는 시나리오가 없어집니다.
        "Crop_SHA256": _sha(os.path.join(RUN, d["Figure_Crop"])),
        "Human_Choice": "", "Human_Note": "",
        "Agent_Choice": "RASTER", "Agent_Note": "초록이 그림 전체",
    })
# 큐는 검증표에서 나옵니다. 픽스처도 그렇게 두지 않으면, 큐와 검증표가 처음부터
# 어긋난 채로 "상자가 바뀌었다"를 시험하게 됩니다.
_REG = os.path.join(RUN, "validated_regions.csv")
_reg_rows = list(csv.DictReader(io.open(_REG, encoding="utf-8")))
_reg_cols = list(_reg_rows[0])
_by_q = {q["Draft_ID"]: q for q in QUEUE}
for r in _reg_rows:
    q = _by_q.get(r["Draft_ID"])
    if q:
        r["Agreement"] = q["Agreement"]
        r["PDF_BBox"], r["PDF_Code"] = q["PDF_BBox"], q["PDF_Code"]
        r["Raster_BBox"], r["Raster_Code"] = q["Raster_BBox"], q["Raster_Code"]
        r["Proposal_Figure_BBox"] = q["Proposal_Figure_BBox"]
with io.open(_REG, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_reg_cols)
    w.writeheader()
    w.writerows(_reg_rows)

QPATH = os.path.join(RUN, "review", "review_queue.csv")
with io.open(QPATH, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows(QUEUE)

OUT = os.path.join(TMP, "out")
RUN_RC = subprocess.run([sys.executable, os.path.join(HERE, "review_sheet.py"),
                         RUN, OUT], capture_output=True, text=True, cwd=HERE)
check("판정 페이지가 픽스처만으로 만들어진다", RUN_RC.returncode == 0,
      (RUN_RC.stderr or "")[-300:])
if RUN_RC.returncode != 0:
    print("%d/%d" % (N[0] - len(FAIL), N[0]))
    raise SystemExit(1)

PARTS = sorted(os.path.join(OUT, f) for f in os.listdir(OUT)
               if f.startswith("review_choose_"))
S = "\n".join(io.open(p, encoding="utf-8").read() for p in PARTS)

_ids = re.findall(r"<section class='card' data-id='([^']+)'", S)
check("큐의 행마다 카드가 하나씩 있다 (%d)" % len(_ids),
      _ids == [q["Draft_ID"] for q in QUEUE], _ids)
check("카드마다 지문이 붙어 있다",
      len(re.findall(r"data-fp='[0-9a-f]{12}'", S)) == len(QUEUE))
check("네 가지 선택 버튼이 행마다 있다",
      all(len(re.findall(r"data-id='%s' data-choice='%s'" % (re.escape(q["Draft_ID"]), c),
                         S)) == 1 for q in QUEUE for c in ("TEXT", "PDF", "RASTER", "BLOCKED")))

# ------------------------------------------------- 미리 고른 것이 없어야 한다
# CSS에도 같은 문자열이 있으므로 버튼 태그만 봅니다 - 문서 전체를 훑는 검사는
# 스타일시트 한 줄로 통과하거나 실패합니다.
_buttons = re.findall(r"<button type='button' class='pick'[^>]*>", S)
check("처음 열었을 때 눌린 버튼이 없다 (버튼 %d개)" % len(_buttons),
      _buttons and not any("aria-pressed='true'" in b for b in _buttons))
check("에이전트 제안은 감춰져 있다",
      len(re.findall(r"<div class='agent' hidden>", S)) == len(QUEUE))
check("에이전트 제안이 버튼의 값으로 새지 않는다",
      "data-choice='RASTER' aria-pressed" not in S and
      not re.search(r"value='(TEXT|PDF|RASTER|BLOCKED)'", S))
check("메모 칸이 비어 있고 placeholder로 값을 흘리지 않는다",
      "placeholder" not in S and not re.search(r"data-note='[^']*' value=", S))

# ------------------------------------------------------- 세 상자와 세 그림
_cuts = re.findall(r"<figure class='cut'", S)
check("행마다 세 방법의 자리가 있다", len(_cuts) == 3 * len(QUEUE), len(_cuts))
check("상자가 없는 방법은 빈 자리로 표시된다 (그림 없이)",
      len(re.findall(r"data-empty='1'", S)) == 1)
check("상자가 있는 방법은 실제로 잘린 그림을 싣는다",
      len(re.findall(r"<figure class='cut'><figcaption[^>]*>[^<]*</figcaption><img", S))
      == 3 * len(QUEUE) - 1)
_pages = re.findall(r"<img class='page' src='data:image/jpeg;base64,", S)
check("행마다 상자를 그린 페이지가 있다", len(_pages) == len(QUEUE), len(_pages))

# 페이지에 세 색이 실제로 그려졌는가 - 색을 그리지 않으면 무엇을 고를지 알 수 없다
import base64                                                    # noqa: E402
from PIL import Image                                            # noqa: E402
_first = re.search(r"<img class='page' src='data:image/jpeg;base64,([^']+)'", S).group(1)
_im = Image.open(io.BytesIO(base64.b64decode(_first))).convert("RGB")
_px = list(_im.getdata())


def _has(pred):
    return any(pred(*p) for p in _px)


check("페이지에 빨강 상자가 그려져 있다", _has(lambda r, g, b: r > 150 and g < 90 and b < 90))
check("페이지에 파랑 상자가 그려져 있다", _has(lambda r, g, b: b > 150 and r < 90 and g < 110))
check("페이지에 초록 상자가 그려져 있다", _has(lambda r, g, b: g > 120 and r < 90 and b < 90))

# --------------------------------------------------------------- 저장과 내보내기
check("저장 키에 빌드 ID가 들어간다", "'fdt-review-' + BUILD" in S)
check("저장소를 쓰기로 탐지한다 (읽기 성공만 믿지 않음)", "setItem(probe" in S)
check("저장소 실패를 사용자에게 알리는 경로가 있다", "complain(" in S and "warn.hidden" in S)
check("빈 catch로 실패를 삼키지 않는다",
      not re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", S))
check("지문이 어긋난 저장값은 비운다", "store[id].fp !== card.dataset.fp" in S)
check("모르는 선택 값은 저장에서 버린다", "VALID.indexOf(store[id].choice) < 0" in S)
check("내보내기는 큐의 칸을 그대로 쓴다 (merge가 읽을 수 있게)",
      "COLUMNS.map(c => csvCell(q[c]))" in S)
check("사람이 고르지 않은 행은 빈 값으로 나간다",
      "q['Human_Choice'] = kept ? kept.choice : ''" in S)
check("외부 요청이 없다",
      not re.search(r"(src|href)=['\"]https?://", S) and "fetch(" not in S)

# ------------------------------------ 내보낸 CSV를 merge가 실제로 읽는가 (端-to-端)
_export = os.path.join(TMP, "exported.csv")
_rows = [dict(q) for q in QUEUE]
_rows[0]["Human_Choice"] = "RASTER"
_rows[0]["Human_Note"] = "초록이 맞음"
with io.open(_export, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows(_rows)
_reg = os.path.join(RUN, "validated_regions.csv")
_rc = RP.merge(RUN, _export)
_after = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
check("내보낸 CSV를 merge가 그대로 반영한다",
      _rc == 0 and _after[QUEUE[0]["Draft_ID"]]["Human_Choice"] == "RASTER",
      _after[QUEUE[0]["Draft_ID"]].get("Human_Choice"))
check("고르지 않은 행에는 아무것도 쓰지 않는다",
      _after[QUEUE[1]["Draft_ID"]].get("Human_Choice", "") == "")

# 크롭이 바뀐 뒤의 판정은 merge가 거부한다 - 지문과 같은 규칙, 파일 쪽에서
_rows[1]["Human_Choice"] = "PDF"
_rows[1]["Crop_SHA256"] = "b" * 64
with io.open(_export, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows(_rows)
_rc2 = RP.merge(RUN, _export)
_after2 = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
check("판정한 크롭과 지금 크롭이 다르면 merge가 거부한다",
      _rc2 != 0 and _after2[QUEUE[1]["Draft_ID"]].get("Human_Choice", "") == "")

# ----------------------------------------------------- 지문은 상자에 묶여 있다
_fp_before = RS.fingerprint(QUEUE[0])
_moved = dict(QUEUE[0], Raster_BBox="1.0,2.0,3.0,4.0")
check("상자가 바뀌면 지문이 달라진다", RS.fingerprint(_moved) != _fp_before)
_recut = dict(QUEUE[0], Crop_SHA256="c" * 64)
check("크롭이 다시 잘려도 지문이 달라진다", RS.fingerprint(_recut) != _fp_before)

# --------------------------------------------------------- 상자 없이는 그림도 없다
check("상자가 없으면 자른 그림을 만들지 않는다",
      RS.cut_for(WITH_PAGE[0], "") is None)
check("상자가 있으면 인테이크와 같은 공식으로 자른다",
      RS.cut_for(WITH_PAGE[0], WITH_PAGE[0]["Figure_BBox"]).size
      == __import__("roundtrip").cut(Image.open(WITH_PAGE[0]["Page_Raster"]),
                                     WITH_PAGE[0])[0].size)

# ------------------------------- 고른 상자가 바뀌었으면 그 판정은 지났다
# 크롭 digest는 그림이 다시 잘린 것을 잡습니다. 제안자가 좋아진 것은 잡지
# 못합니다 - 실제로 PDF 제안자를 고친 뒤 돌려받은 48행 중 6행의 파랑 상자가
# 화면에 있던 것과 달랐습니다.
_reg_now = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
_q0 = dict(QUEUE[0], Human_Choice="PDF")
check("고른 상자가 그대로면 지나지 않았다",
      RP.stale(_q0, _reg_now[_q0["Draft_ID"]], _q0["Crop_SHA256"]) == "",
      RP.stale(_q0, _reg_now[_q0["Draft_ID"]], _q0["Crop_SHA256"]))
_moved_pdf = dict(_reg_now[_q0["Draft_ID"]], PDF_BBox="1.0,2.0,3.0,4.0")
check("고른 PDF 상자가 달라지면 지났다고 말한다",
      "고른 PDF 상자가" in RP.stale(_q0, _moved_pdf, _q0["Crop_SHA256"]))
check("고르지 않은 상자가 달라진 것은 지나지 않았다",
      RP.stale(dict(_q0, Human_Choice="RASTER"),
               _moved_pdf, _q0["Crop_SHA256"]) == "")
check("BLOCKED은 상자를 지목하지 않으므로 상자 변화에 지나지 않는다",
      RP.stale(dict(_q0, Human_Choice="BLOCKED"),
               _moved_pdf, _q0["Crop_SHA256"]) == "")
check("크롭이 바뀌면 어느 선택이든 지났다",
      RP.stale(dict(_q0, Human_Choice="BLOCKED"),
               _reg_now[_q0["Draft_ID"]], "z" * 64) != "")
check("고르지 않은 행은 지날 것도 없다",
      RP.stale(dict(_q0, Human_Choice=""), _moved_pdf, "z" * 64) == "")
_stale_export = os.path.join(TMP, "stale.csv")
_srows = [dict(q) for q in QUEUE]
_srows[0]["Human_Choice"] = "PDF"
with io.open(_stale_export, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows(_srows)
_rows_reg = list(csv.DictReader(io.open(_reg, encoding="utf-8")))
_cols_reg = list(_rows_reg[0])
for r in _rows_reg:
    if r["Draft_ID"] == QUEUE[0]["Draft_ID"]:
        r["PDF_BBox"] = "9.0,9.0,99.0,99.0"
with io.open(_reg, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols_reg)
    w.writeheader()
    w.writerows(_rows_reg)
_rc3 = RP.merge(RUN, _stale_export)
_after3 = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
check("상자가 바뀐 판정은 merge가 반영하지 않는다",
      _rc3 != 0 and _after3[QUEUE[0]["Draft_ID"]].get("Human_Choice", "") != "PDF")

# ------------------------------------------ 파일마다 자기 행만 내보낸다
# 예산을 낮춰 두 파일로 쪼개고, 각 파일이 자기 카드만 담고 자기 카드만
# 내보내는지 봅니다. 한 파일이 큐 전체를 내보내면, 한 파일을 채운 사람이
# 다 끝난 것처럼 보이는 CSV를 손에 쥡니다.
_split_out = os.path.join(TMP, "split")
_env = dict(os.environ, FDT_REVIEW_BUDGET="1", PYTHONPYCACHEPREFIX=os.path.join(TMP, "pyc"))
_rc_split = subprocess.run([sys.executable, os.path.join(HERE, "review_sheet.py"),
                            RUN, _split_out], capture_output=True, text=True,
                           cwd=HERE, env=_env)
_sparts = sorted(os.path.join(_split_out, f) for f in os.listdir(_split_out)
                 if f.startswith("review_choose_"))
check("예산이 작으면 파일이 나뉜다", len(_sparts) == len(QUEUE), len(_sparts))
_ok_rows = _ok_queue = True
for _i, _p in enumerate(_sparts):
    _t = io.open(_p, encoding="utf-8").read()
    _cards_here = re.findall(r"<section class='card' data-id='([^']+)'", _t)
    _rows_here = re.search(r"const ROWS = (\[.*?\]), COLUMNS", _t, re.S).group(1)
    _queue_here = re.search(r"QUEUE = (\{.*?\}), BUILD", _t, re.S).group(1)
    _ids_in_rows = re.findall(r'"Draft_ID": "([^"]+)"', _rows_here)
    if _ids_in_rows != _cards_here:
        _ok_rows = False
    for _q in QUEUE:
        if (_q["Draft_ID"] in _queue_here) != (_q["Draft_ID"] in _cards_here):
            _ok_queue = False
check("파일의 내보내기 목록이 그 파일의 카드와 정확히 같다", _ok_rows)
check("파일에 없는 행의 데이터는 실리지 않는다", _ok_queue)
check("파일마다 다른 이름으로 내려받는다",
      len({re.search(r"a\.download = 'review_queue_' \+ PART", io.open(p2, encoding='utf-8').read())
           is not None for p2 in _sparts}) == 1
      and len({re.search(r"const PART = \"(\d+)\"", io.open(p2, encoding='utf-8').read()).group(1)
               for p2 in _sparts}) == len(_sparts))

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
