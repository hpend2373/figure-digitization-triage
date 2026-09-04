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
import block_rules as BR                                         # noqa: E402

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
        # 막힌 행 큐에서 오는 두 칸. 1번은 상자로 풀리는 행, 2번은 아닌 행.
        "Block_Reason": "시험용: 이 행이 막힌 이유 %d" % i,
        "Box_Would_Open": "1" if i == 1 else "0",
        # 2번 행에만 번호를 청합니다 - 번호 칸이 청한 행에만 붙는지 볼 수 있게.
        "Number_Would_Open": "1" if i == 2 else "0",
        "Human_Figure_Number": "",
        # 2번 행에만 "이 줄이 부르는 그림을 저 행이 세고 있다"를 붙입니다.
        "Mentions_Held": "FIG1=OTHER_D001;FIG2=OTHER_D002" if i == 2 else "",
        # 1번 행에만 옆 쪽을 실어, 띠가 그 행에만 붙는지 볼 수 있게 합니다.
        "Neighbours": ("%d:612.0x792.0" % (int(d["Page"]) + 1)) if i == 1 else "",
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

# 1번 행의 옆 쪽 래스터를 만들어 둡니다 - 파일이 없으면 쪽 넘김 띠는 그릴 것이
# 없고, 띠를 지키는 시나리오가 통과해 버립니다.
_nb_row = WITH_PAGE[0]
_nb_path = os.path.join(os.path.dirname(_nb_row["Page_Raster"]),
                        "page-%d.png" % (int(_nb_row["Page"]) + 1))
if not os.path.exists(_nb_path):
    from PIL import Image as _I0
    _I0.open(_nb_row["Page_Raster"]).save(_nb_path)

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
check("다섯 가지 선택 버튼이 행마다 있다",
      all(len(re.findall(r"data-id='%s' data-choice='%s'" % (re.escape(q["Draft_ID"]), c),
                         S)) == 1 for q in QUEUE
          for c in ("TEXT", "PDF", "RASTER", "DRAWN", "BLOCKED")))

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
      not re.search(r"data-note='[^']*'[^>]*(placeholder|value)=", S),
      re.findall(r"<input[^>]*data-note[^>]*>", S)[:1])
# 번호 칸의 placeholder는 값이 아니라 적는 법입니다 - 값으로 새면 사람이 적지
# 않은 번호가 답으로 나갑니다.
check("번호 칸의 예시는 placeholder일 뿐 값이 아니다",
      not re.search(r"data-number='[^']*'[^>]*value='[^']+'", S),
      re.findall(r"<input[^>]*data-number[^>]*>", S)[:1])

# ------------------------------------------------ 막힌 이유가 카드에 적히는가
# 막힌 행을 판정하러 온 사람은 무엇이 막고 있는지부터 알아야 합니다. 그리고
# 상자로 풀리지 않는 행에 "그리십시오"라고 말하면 헛수고를 시키는 것입니다.
check("행마다 막힌 이유가 적힌다",
      S.count("<b>막힌 이유</b>") == len(QUEUE), S.count("<b>막힌 이유</b>"))
check("그 이유는 시트가 준 문장 그대로다",
      all(("이 행이 막힌 이유 %d" % i) in S for i in (1, 2, 3)))
# 사람이 채울 것이 하나도 없는 행에만 "소용없다"고 적습니다. 번호를 청하는
# 행에까지 그렇게 적으면, 적을 자리를 주면서 헛수고라고 말하는 셈입니다.
_nothing = sum(1 for q in QUEUE
               if q["Box_Would_Open"] != "1" and q["Number_Would_Open"] != "1")
check("사람이 채울 것이 없는 행에만 '상자를 그려도 소용없다'고 적힌다",
      S.count("상자를 그려도 이 이유는 풀리지 않습니다") == _nothing,
      (S.count("상자를 그려도 이 이유는 풀리지 않습니다"), _nothing))
check("상자든 번호든 채울 것이 있는 행에는 그 말이 붙지 않는다",
      "class='why helps'" in S and S.count("class='why helps'")
      == sum(1 for q in QUEUE if q["Box_Would_Open"] == "1"
             or q["Number_Would_Open"] == "1"),
      S.count("class='why helps'"))

# ------------------------------------------------------- 세 상자와 세 그림
_cuts = re.findall(r"<figure class='cut'", S)
check("행마다 세 방법의 자리가 있다", len(_cuts) == 3 * len(QUEUE), len(_cuts))
check("상자가 없는 방법은 빈 자리로 표시된다 (그림 없이)",
      len(re.findall(r"data-empty='1'", S)) == 1)
check("상자가 있는 방법은 실제로 잘린 그림을 싣는다",
      len(re.findall(r"<figure class='cut'><figcaption[^>]*>[^<]*</figcaption><img", S))
      == 3 * len(QUEUE) - 1)
_pages = re.findall(r"<img class='page' data-page='\d+' src='data:image/jpeg;base64,", S)
check("행마다 상자를 그린 페이지가 있다", len(_pages) == len(QUEUE), len(_pages))

import base64                                                    # noqa: E402
from PIL import Image                                            # noqa: E402

# 세 상자가 실제로 페이지 위에 있는가 - 없으면 무엇을 고를지 알 수 없습니다.
# 상자는 그림에 굽지 않고 겹쳐 그립니다: 구워 넣으면 손으로 그린 크롭의
# 미리보기 안에까지 그 선들이 들어가, 실제 크롭에 없는 것을 보고 판단하게
# 됩니다. 그래서 픽셀이 아니라 좌표로 확인합니다 - 더 강한 검사이기도 합니다.
_ov = re.findall(r"<div class='pbox' data-box='([A-Z]+)' style='border-color:"
                 r"(#[0-9a-f]{6});left:([\d.]+)%;top:([\d.]+)%;"
                 r"width:([\d.]+)%;height:([\d.]+)%'", S)
_want = sum(1 for q in QUEUE for n in ("TEXT", "PDF", "RASTER")
            if (q.get(RS.BOX_COLUMN[n]) or "").strip())
check("상자가 있는 방법마다 겹친 테두리가 하나씩 있다 (%d개)" % _want,
      len(_ov) == _want, len(_ov))
check("세 색이 모두 쓰인다",
      {c for _n, c, *_r in _ov} == {"#c42020", "#0050eb", "#00962a"},
      sorted({c for _n, c, *_r in _ov}))
check("페이지 그림에는 상자를 굽지 않는다 (미리보기가 깨끗해야 한다)",
      "ImageDraw" not in io.open(os.path.join(HERE, "review_sheet.py"),
                                 encoding="utf-8").read())
# 테두리가 그 행이 말하는 상자 자리에 있는가 - 픽셀 표본은 "어딘가 빨간 점이
# 있다"까지만 말하지만, 이것은 자리를 말합니다.
_q0, _r0 = QUEUE[0], WITH_PAGE[0]
_pw0, _ph0 = float(_r0["Page_Width_Pt"]), float(_r0["Page_Height_Pt"])
_bx = [float(v) for v in _q0["PDF_BBox"].split(",")]
_mine_ov = [o for o in _ov if o[0] == "PDF"][0]
check("테두리가 그 행이 말하는 자리에 있다 (0.1%% 이내)",
      abs(float(_mine_ov[2]) - _bx[0] / _pw0 * 100) < 0.1
      and abs(float(_mine_ov[3]) - _bx[1] / _ph0 * 100) < 0.1
      and abs(float(_mine_ov[4]) - (_bx[2] - _bx[0]) / _pw0 * 100) < 0.1,
      _mine_ov)

# --------------------------------------------------------------- 저장과 내보내기
check("저장 키에 빌드 ID가 들어간다", "'fdt-review-' + BUILD" in S)
check("저장소를 쓰기로 탐지한다 (읽기 성공만 믿지 않음)", "setItem(probe" in S)
check("저장소 실패를 사용자에게 알리는 경로가 있다", "complain(" in S and "warn.hidden" in S)
check("빈 catch로 실패를 삼키지 않는다",
      not re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", S))
check("지문이 어긋난 저장값은 비운다",
      "store[id].fp !== needed(card, store[id].choice)" in S)
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
# 거부를 적어 두지 않으면 그 행은 아무 흔적 없이 사라집니다 - 사람이 답했다는
# 사실 자체가 없어지고, 기계가 그 사이 확정하면 다시 묻지도 않습니다.
check("merge가 무엇을 왜 거부했는지 검증표에 적는다",
      _after3[QUEUE[0]["Draft_ID"]].get(RP.STALE_CHOICE) == "PDF"
      and "상자" in (_after3[QUEUE[0]["Draft_ID"]].get(RP.STALE_REASON) or ""),
      {k: _after3[QUEUE[0]["Draft_ID"]].get(k)
       for k in (RP.STALE_CHOICE, RP.STALE_REASON)})

# 판정 페이지는 큐 파일을 읽습니다 - 검증표만 고치고 페이지를 만들면, 페이지는
# 옛 큐를 보게 됩니다. 실제 흐름대로 큐를 다시 씁니다.
def _rewrite_queue():
    rows = RP.queue(RUN)
    with io.open(QPATH, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in RP.FIELDS} for r in rows])
    return rows


# ------------------------------- 이미 적용된 선택은 지난 것이 아니다
# 선택을 적용하면 크롭이 다시 잘리고 digest가 바뀝니다. 같은 파일을 한 번 더
# merge하면 그 변화 때문에 "지났다"가 되어, 자기가 일으킨 변화로 자기를 무효로
# 만듭니다.
_ap_row = {"Human_Choice": "RASTER", "Raster_BBox": "10.0,20.0,30.0,40.0"}
check("고른 상자가 이미 초안의 상자면 적용된 것으로 본다",
      RP.already_applied(_ap_row, {"Figure_BBox": "10.0,20.0,30.0,40.0"}))
check("다른 상자면 적용된 것이 아니다",
      not RP.already_applied(_ap_row, {"Figure_BBox": "1.0,2.0,3.0,4.0"}))
check("BLOCKED은 상자를 지목하지 않으므로 적용 여부를 말할 수 없다",
      not RP.already_applied({"Human_Choice": "BLOCKED"},
                             {"Figure_BBox": "10.0,20.0,30.0,40.0"}))
_twice = os.path.join(TMP, "twice.csv")
_trows = [dict(q) for q in _rewrite_queue()]
_tid = _trows[0]["Draft_ID"]
_trows[0]["Human_Choice"] = "RASTER"
with io.open(_twice, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in RP.FIELDS} for r in _trows])
RP.merge(RUN, _twice)
import apply_validated as _AV
_AV.main(RUN)
_rc_twice = RP.merge(RUN, _twice)          # 적용한 뒤 같은 파일을 다시
_after_twice = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
check("적용한 뒤 같은 파일을 다시 merge해도 거부하지 않는다",
      _rc_twice == 0 and not (_after_twice[_tid].get(RP.STALE_CHOICE) or "").strip(),
      {k: _after_twice[_tid].get(k) for k in (RP.STALE_CHOICE, RP.STALE_REASON)})

# ---------------------------- 거부된 판정은 사라지지 않고 큐로 돌아온다
# 거부는 삭제가 아닙니다. 사람은 답했고, 그 답을 지금 그림에 적용할 수 없을
# 뿐입니다. 기계가 그 사이 합의했다고 행이 큐에서 빠지면, 사람이 가리킨 곳과
# 다른 자리로 확정돼도 아무도 다시 묻지 않습니다 — 2026-09-02에 10행이 그렇게
# 빠졌고 그중 3행은 기계가 다른 곳을 가리키고 있었습니다.
_target_id = QUEUE[0]["Draft_ID"]
_rows_now = list(csv.DictReader(io.open(_reg, encoding="utf-8")))
_cols_now = list(_rows_now[0])
for c in (RP.STALE_CHOICE, RP.STALE_REASON):
    if c not in _cols_now:
        _cols_now.append(c)
for r in _rows_now:
    r.setdefault(RP.STALE_CHOICE, "")
    r.setdefault(RP.STALE_REASON, "")
    if r["Draft_ID"] == _target_id:
        r["Agreement"] = "AGREE_3"          # 기계가 그 사이 확정
        r[RP.STALE_CHOICE], r[RP.STALE_REASON] = "PDF", "고른 PDF 상자가 바뀜"
with io.open(_reg, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols_now)
    w.writeheader()
    w.writerows(_rows_now)
_q_back = _rewrite_queue()
check("기계가 AGREE_3으로 확정했어도 거부된 판정이 있으면 큐에 남는다",
      any(r["Draft_ID"] == _target_id for r in _q_back),
      [r["Draft_ID"] for r in _q_back])
_back_row = [r for r in _q_back if r["Draft_ID"] == _target_id][0]
check("큐가 무엇이 거부됐는지 들고 온다",
      _back_row[RP.STALE_CHOICE] == "PDF" and "PDF 상자" in _back_row[RP.STALE_REASON])
_out2 = os.path.join(TMP, "out2")
subprocess.run([sys.executable, os.path.join(HERE, "review_sheet.py"), RUN, _out2],
               capture_output=True, text=True, cwd=HERE)
_S2 = "\n".join(io.open(os.path.join(_out2, f), encoding="utf-8").read()
                 for f in sorted(os.listdir(_out2)) if f.startswith("review_choose_"))
check("판정 페이지가 그 사실을 그 행에 적어 준다",
      "전에 <b>PDF</b>로 판정하셨는데" in _S2)
# 앞선 시나리오들이 이미 거부를 몇 건 남겨 두었으므로, 알림 수는 큐가 들고 있는
# 거부 수와 같아야 합니다 - 상수 1로 적으면 순서가 바뀔 때마다 깨집니다.
_stale_in_queue = sum(1 for r in _q_back if (r.get(RP.STALE_CHOICE) or "").strip())
check("거부가 있는 행에만 그 알림이 붙는다 (%d행)" % _stale_in_queue,
      _S2.count("class='stale'") == _stale_in_queue,
      (_S2.count("class='stale'"), _stale_in_queue))

# 다시 답하면 거부 표시가 지워진다
_clear = os.path.join(TMP, "clear.csv")
_crows = [dict(q) for q in _rewrite_queue()]
for r in _crows:
    if r["Draft_ID"] == _target_id:
        r["Human_Choice"] = "RASTER"
with io.open(_clear, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_crows[0]))
    w.writeheader()
    w.writerows(_crows)
RP.merge(RUN, _clear)
_after_clear = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg, encoding="utf-8"))}
check("다시 답하면 거부 표시가 지워진다",
      _after_clear[_target_id].get(RP.STALE_CHOICE, "") == ""
      and _after_clear[_target_id].get("Human_Choice") == "RASTER",
      {k: _after_clear[_target_id].get(k) for k in (RP.STALE_CHOICE, "Human_Choice")})
check("그러면 큐에서도 빠진다",
      not any(r["Draft_ID"] == _target_id for r in RP.queue(RUN))
      or _after_clear[_target_id].get("Agreement") not in RP.COUNTABLE)

# ============================== 사람이 직접 그리는 상자 (DRAWN) ==============================
# 세 제안자가 모두 실패한 페이지에도 그림은 있습니다. 2026-09-02에 막힌 10행 중
# 8행이 그랬습니다 - 캡션이 온전한 진짜 그림인데 TAKEN·NO_CANDIDATE·AMBIGUOUS로
# 아무도 상자를 내지 못한 페이지들. 막는 것은 그 그림을 버려서 탐지기의 실패를
# 기록하는 일이었습니다. DRAWN은 그 둘을 갈라 놓습니다.

# ------------------------------------------------------- 페이지에서 끌 수 있는가
check("행마다 끌 수 있는 층이 페이지 위에 있다",
      S.count("class='pagewrap'") == len(_pages), S.count("class='pagewrap'"))
check("그린 상자를 보여 줄 자리가 행마다 있다",
      S.count("<figure class='mine' hidden>") == len(_pages))
check("상자가 없으면 그리기 버튼은 눌리지 않는다",
      len(re.findall(r"data-choice='DRAWN'[^>]* disabled>", S)) == len(QUEUE),
      re.findall(r"data-choice='DRAWN'[^>]*>", S)[:1])
check("다른 선택 버튼까지 잠그지는 않는다",
      not re.search(r"data-choice='(TEXT|PDF|RASTER|BLOCKED)'[^>]* disabled>", S))
check("미리보기가 실제 크롭이 아님을 화면에서 밝힌다",
      "실제 크롭은 원본 해상도에서" in S)
check("카드가 페이지 지문을 들고 있다",
      len(re.findall(r"data-pfp='[0-9a-f]{12}'", S)) == len(QUEUE))
_pw = re.findall(r"data-pw='([^']*)' data-ph='([^']*)'", S)
check("카드가 페이지 크기를 pt로 들고 있다 (상자를 점으로 바꾸려면 필요)",
      len(_pw) == len(QUEUE) and all(float(a) > 0 and float(b) > 0 for a, b in _pw), _pw)
check("그린 상자를 화면 픽셀이 아니라 점(pt)으로 저장한다",
      "f[0] * pw" in S and "f[1] * ph" in S)
check("끌지 않은 클릭은 상자가 되지 않는다", "if (!moved)" in S)
# 상자를 고쳐 그리는 것은 답을 무르는 것이 아닙니다. 버튼을 두 번 누르면 무르는
# 것이 맞지만, 다시 끄는 사람은 답을 고치는 중입니다.
check("다시 끌어도 판정이 풀리지 않는다", "choose(card, 'DRAWN', false)" in S)
check("버튼을 두 번 누르면 여전히 풀린다", "again !== false && store[id]" in S)
check("상자 없는 DRAWN은 고를 수 없다", "choice === 'DRAWN' && !boxes[id]" in S)
check("그린 상자는 그것을 고른 행에서만 내보낸다",
      "q['Human_Box'] = (kept && kept.choice === 'DRAWN' && boxes[r.Draft_ID])" in S)
check("그린 상자를 지울 수 있다", "class='erase'" in S and "delete boxes[id]" in S)

# ----------------------------- 어떤 지문에 묶이는가 - 답이 무엇에 관한 것이냐로
# 제안자 상자에 묶으면, 탐지기가 좋아질 때마다 사람이 손으로 그린 답이 버려집니다.
# 그 답은 페이지에 관한 것이지 제안에 관한 것이 아닙니다.
check("DRAWN은 페이지 지문에, 나머지는 카드 지문에 묶인다",
      "if (choice !== 'DRAWN') return card.dataset.fp;" in S
      and "return b ? b.pfp : card.dataset.pfp;" in S)
check("페이지 지문이 어긋난 상자는 비운다", "boxes[id].pfp !== info.pfp" in S)
# 상자는 그린 쪽에 묶입니다 - 옆 쪽에 그렸으면 그 쪽의 지문이고, 그 쪽으로
# 돌아가야 보입니다.
check("상자가 자기가 그려진 쪽을 기억한다", "page: shownPage(card)," in S)
check("상자는 자기 쪽에서만 그려진다",
      "String(b0.page) === String(shownPage(card))" in S)
check("옆 쪽에 그린 상자는 그 쪽 번호로 나간다",
      "q['Human_Page'] = (drawnOn !== null" in S)
# 쪽 넘김 띠가 없으면 옆 쪽은 파일 안에 실려만 있고 아무도 갈 수 없습니다.
_nav = re.findall(r"<button type='button' class='goto[^']*' data-page='(\d+)'", S)
_navrows = [q for q in QUEUE if (q.get("Neighbours") or "").strip()]
check("옆 쪽이 실린 행에는 쪽 넘김 띠가 있다",
      bool(_navrows) == bool(_nav), (len(_navrows), len(_nav)))
if _navrows:
    _want = set()
    for q in _navrows:
        _want |= {x.split(":")[0] for x in q["Neighbours"].split(";") if x}
        _want.add(str(q["Page"]))
    check("띠에 캡션 쪽과 실린 쪽이 모두 있다 (그리로 갈 수 있어야 한다)",
          set(_nav) == _want, (sorted(set(_nav)), sorted(_want)))
    check("캡션 쪽 단추는 그렇게 표시된다", "class='goto cap'" in S)
check("캡션 쪽에 그린 상자는 쪽 번호 없이 나간다 (예전과 같이)",
      "String(drawnOn) !== String(capPage)) ? String(drawnOn) : ''" in S)
# 속성이 아니라 그림입니다: `display:block`은 브라우저의 [hidden] 규칙을 이기고,
# 숨긴 쪽이 그대로 보이면서 상자가 엉뚱한 쪽에 떨어집니다. 스크린샷이 잡았습니다.
# 넘겨 보는 쪽은 캡션 쪽보다 좁게 싣습니다 - 47장짜리 파일이 126MB였습니다.
# 상자는 화면에서 잰 점(pt)이라 래스터가 좁아도 정밀도는 그대로입니다.
check("넘겨 보는 쪽은 캡션 쪽보다 좁다", RS.WINDOW_WIDTH < RS.PAGE_WIDTH,
      (RS.WINDOW_WIDTH, RS.PAGE_WIDTH))
_capsrc = re.search(r"<img class='page' data-page='\d+' src='data:image/jpeg;base64,([^']+)'", S)
_capw = Image.open(io.BytesIO(base64.b64decode(_capsrc.group(1)))).width
_othw = [Image.open(io.BytesIO(base64.b64decode(m))).width for m in
         re.findall(r"<img class='page other' data-page='\d+' src='data:image/jpeg;base64,([^']+)'", S)]
check("실제로 그렇게 실린다 (캡션 %d px, 옆 쪽 %s)" % (_capw, _othw or "없음"),
      bool(_othw) and all(w <= RS.WINDOW_WIDTH for w in _othw) and _capw > RS.WINDOW_WIDTH,
      (_capw, _othw))
check("숨긴 페이지 그림은 실제로 사라진다 ([hidden]이 display:block을 이긴다)",
      "img.page[hidden]{display:none}" in S)
check("옆 쪽에서는 세 제안 상자를 숨긴다 (그 쪽의 상자가 아니다)",
      "b.hidden = !info.caption" in S)

# ------------------------------------------- 번호를 적는 칸이 페이지에 있는가
# 이 칸이 생기기 전, 카드는 "그림 번호를 적어 주십시오"라고 말하면서 적을 자리를
# 주지 않았습니다. 브라우저에서 실제로 타이핑해 보는 것은 `test_draw_browser.py`
# 이고, 여기서는 그 칸이 청한 행에만, 그리고 CSV까지 이어지도록 짜였는지 봅니다.
_num_cards = re.findall(r"data-number='([^']+)'", S)
# 카드가 아는 것을 말해 주는가. 여덟 행이 "번호를 적어 주십시오"만 달고 왔고,
# 그 줄들이 부르는 그림은 전부 이 논문이 이미 세고 있었습니다 - 말해 주지 않으면
# 사람은 무엇을 그려야 하는지 알 길이 없습니다.
check("이 줄이 부르는 그림을 누가 세고 있는지 카드가 말한다",
      S.count("이 줄이 부르는 그림") == 1, S.count("이 줄이 부르는 그림"))
check("그 행들의 이름을 대고 무엇을 하면 되는지도 말한다",
      "OTHER_D001" in S and "OTHER_D002" in S and "<b>막음</b>을 고르십시오" in S)
check("그런 사실이 없는 행에는 붙이지 않는다",
      S.count("이미 세고 있습니다") == 2, S.count("이미 세고 있습니다"))
check("번호를 청한 행에만 번호 칸이 붙는다",
      _num_cards == [QUEUE[1]["Draft_ID"]], _num_cards)
check("그 카드의 이유가 번호를 적으라고 말한다",
      "그림 번호를 적어 주십시오" in S)
check("번호를 청한 행은 '상자를 그려도 소용없다'고만 하지 않는다",
      S.count("상자를 그려도 이 이유는 풀리지 않습니다") == 1,
      S.count("상자를 그려도 이 이유는 풀리지 않습니다"))
check("내보내기가 적은 번호를 그 행에 싣는다",
      "q['Human_Figure_Number'] = numbers[r.Draft_ID] || '';" in S)
check("적은 번호는 고른 것과 따로 저장된다 (고르지 않아도 답이므로)",
      "const NUMKEY = 'fdt-review-num-' + BUILD;" in S
      and "if (v) numbers[id] = v; else delete numbers[id];" in S)
_r0 = WITH_PAGE[0]
check("같은 페이지면 페이지 지문이 같다",
      RS.page_fingerprint(_r0) == RS.page_fingerprint(dict(_r0)))
check("제안자 상자가 바뀌어도 페이지 지문은 그대로다",
      RS.page_fingerprint(dict(_r0, Figure_BBox="1,2,3,4")) == RS.page_fingerprint(_r0))
check("페이지가 바뀌면 페이지 지문이 달라진다",
      RS.page_fingerprint(dict(_r0, Page_Raster="/없는/페이지.png"))
      != RS.page_fingerprint(_r0))
check("페이지 크기가 바뀌면 페이지 지문이 달라진다",
      RS.page_fingerprint(dict(_r0, Page_Width_Pt="1.0")) != RS.page_fingerprint(_r0))

# --------------------------------------- 브라우저에서 온 상자는 검사받고 들어온다
import apply_validated as AV                                     # noqa: E402
_pg = {"Page_Width_Pt": "600", "Page_Height_Pt": "800"}
check("네 숫자면 받는다", AV.drawn_box("10,20,300,400", _pg)[0] == "10.0,20.0,300.0,400.0")
check("거꾸로 끌어도 바로 세운다", AV.drawn_box("300,400,10,20", _pg)[0] == "10.0,20.0,300.0,400.0")
check("페이지 밖으로 나간 만큼은 페이지 가장자리로 자른다",
      AV.drawn_box("-50,-50,900,900", _pg)[0] == "0.0,0.0,600.0,800.0")
# 건너뛴 이유는 사람이 읽고 고치는 문장입니다. 잘린 상자를 "숫자가 아니다"라고
# 부르면 틀린 곳을 찾게 만듭니다 - 네 개가 아닌 것과 숫자가 아닌 것은 다릅니다.
check("숫자가 셋이면 네 개가 아니라고 말한다",
      "네 숫자가 아님" in AV.drawn_box("10,20,300", _pg)[1],
      AV.drawn_box("10,20,300", _pg)[1])
check("숫자가 다섯이어도 네 개가 아니라고 말한다",
      "네 숫자가 아님" in AV.drawn_box("10,20,30,40,50", _pg)[1],
      AV.drawn_box("10,20,30,40,50", _pg)[1])
check("숫자가 아니면 그렇게 말한다",
      "숫자가 아닌" in AV.drawn_box("10,20,300,여기", _pg)[1],
      AV.drawn_box("10,20,300,여기", _pg)[1])
check("너무 작으면 받지 않는다 (마우스가 미끄러진 것)",
      "너무 작음" in AV.drawn_box("10,20,15,25", _pg)[1])
check("페이지 밖에만 있으면 받지 않는다",
      "페이지 밖" in AV.drawn_box("700,900,800,1000", _pg)[1])
check("페이지 크기를 모르면 받지 않는다", AV.drawn_box("10,20,300,400", {})[1] != "")
check("빈 값은 받지 않는다", AV.drawn_box("", _pg)[1] != "")

# ------------------------------- 그린 상자는 크롭이 바뀌어도 지나지 않는다
_dq = {"Human_Choice": "DRAWN", "Human_Box": "10,20,300,400",
       "Crop_SHA256": "a" * 64}
check("크롭이 다시 잘려도 그린 상자는 그대로 유효하다",
      RP.stale(_dq, {}, "z" * 64) == "", RP.stale(_dq, {}, "z" * 64))
check("제안자 상자가 바뀌어도 그린 상자는 그대로 유효하다",
      RP.stale(_dq, {"PDF_BBox": "1,2,3,4", "Human_Box": "10,20,300,400"},
               "a" * 64) == "")
check("상자 없이 DRAWN이라고만 하면 거부한다",
      "비어 있음" in RP.stale(dict(_dq, Human_Box=""), {}, "a" * 64))

# ------------------------------------ 끝에서 끝까지: 그린 상자로 다시 자른다
FX2 = make_fixture.write(os.path.join(TMP, "fx2"))
RUN2 = FX2["draft"]
D2 = list(csv.DictReader(io.open(os.path.join(RUN2, "figure_intake_draft.csv"),
                                 encoding="utf-8")))
_d2 = [d for d in D2 if d["Figure_Crop"] and d["Page_Raster"]][0]
_REG2 = os.path.join(RUN2, "validated_regions.csv")


def _reg2_rows():
    return list(csv.DictReader(io.open(_REG2, encoding="utf-8")))


def _write_reg2(rows, extra=()):
    cols = list(rows[0])
    for c in extra:
        if c not in cols:
            cols.append(c)
    with io.open(_REG2, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in rows])


_x0, _y0, _x1, _y1 = [float(v) for v in _d2["Figure_BBox"].split(",")]
_mine = "%.1f,%.1f,%.1f,%.1f" % (_x0, _y0, _x1 - 5, _y1 - 5)
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _d2["Draft_ID"]:
        r["Agreement"] = "DISAGREE"
        r["Human_Choice"] = "DRAWN"
        r["Human_Box"] = _mine
_write_reg2(_rows2, ("Human_Choice", "Human_Box"))
AV.main(RUN2)
_d2_after = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
    os.path.join(RUN2, "figure_intake_draft.csv"), encoding="utf-8"))}[_d2["Draft_ID"]]
_r2_after = {r["Draft_ID"]: r for r in _reg2_rows()}[_d2["Draft_ID"]]
check("그린 상자가 초안의 상자가 된다", _d2_after["Figure_BBox"] == _mine,
      _d2_after["Figure_BBox"])
check("옛 상자는 버리지 않고 남긴다",
      _d2_after["Proposal_Figure_BBox"] == _d2["Figure_BBox"])
check("크롭이 사람이 그린 것에서 나왔다고 적는다",
      _d2_after["Crop_Source"] == "HUMAN_CHOICE_DRAWN", _d2_after["Crop_Source"])
check("합의는 사람이 확인한 것으로 바뀐다",
      _r2_after["Agreement"] == "HUMAN_VALIDATED", _r2_after["Agreement"])
import roundtrip as RT                                           # noqa: E402
check("그린 상자로 자른 크롭이 그 상자에서 그대로 재현된다",
      RT.check(_d2_after, RUN2)[0] == "MATCH", RT.check(_d2_after, RUN2))

# 쓸 수 없는 상자는 행을 건드리지 않고 이름과 함께 건너뛴다
_bad = [d for d in D2 if d["Figure_Crop"] and d["Page_Raster"]
        and d["Draft_ID"] != _d2["Draft_ID"]][0]
_bx0, _by0 = [float(v) for v in _bad["Figure_BBox"].split(",")][:2]
# 8pt: `roundtrip.cut`은 이 상자로도 그림을 냅니다 (아래 시나리오가 그것을
# 확인합니다). 그러니 이 행을 지키는 것은 왕복 검사가 아니라 MIN_DRAWN_PT뿐입니다.
_slip = "%.1f,%.1f,%.1f,%.1f" % (_bx0, _by0, _bx0 + 8, _by0 + 8)
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _bad["Draft_ID"]:
        r["Agreement"] = "DISAGREE"
        r["Human_Choice"] = "DRAWN"
        r["Human_Box"] = _slip
_write_reg2(_rows2)
AV.main(RUN2)
_bad_after = {r["Draft_ID"]: r for r in _reg2_rows()}[_bad["Draft_ID"]]
_bad_draft = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
    os.path.join(RUN2, "figure_intake_draft.csv"), encoding="utf-8"))}[_bad["Draft_ID"]]
# 3pt짜리 상자도 PAD 때문에 잘리기는 합니다. 검사를 건너뛰면 그대로 크롭이 되고,
# 아무도 세지 못할 그림이 셀 수 있는 행이 됩니다.
check("그 상자로도 크롭은 나온다 - 왕복 검사가 막아 주는 게 아니다",
      RT.cut(Image.open(_bad["Page_Raster"]),
             dict(_bad, Figure_BBox=_slip)) is not None)
check("마우스가 미끄러진 상자는 확인된 것이 되지 않는다",
      _bad_after["Agreement"] != "HUMAN_VALIDATED", _bad_after["Agreement"])
check("그런 상자로 크롭을 바꾸지도 않는다",
      _bad_draft["Figure_BBox"] == _bad["Figure_BBox"], _bad_draft["Figure_BBox"])

# ================== 다시 자른 크롭은 다시 잰다 (THIN_CROP / EDGE_CLIPPED) ==================
# `Crop_Quality_Status`는 크롭에 대한 **측정값**입니다 - 페이지 대비 높이,
# 그림이 옆으로 잘렸는지. 사람이 상자를 바꾸면 그 측정값은 이제 없는 그림을
# 설명합니다. 그리고 이것은 시트가 마지막에 적용하는 관문이라, 다시 재지 않으면
# 막힌 210행 중 183행은 상자를 아무리 잘 그려도 막힌 채로 남습니다.
_pg_img = Image.open(_d2["Page_Raster"])
from PIL import ImageDraw as _ID                                 # noqa: E402


def _patch(w, h, ink=None):
    im = Image.new("RGB", (w, h), "white")
    if ink:
        _ID.Draw(im).rectangle(ink, fill=(10, 10, 10))
    return im


_page_h = _pg_img.height
_tall = _patch(200, int(_page_h * 0.5), (20, 20, 180, int(_page_h * 0.5) - 20))
check("페이지의 절반을 차지하는 크롭은 ACCEPTABLE",
      RT.grade(_tall, _pg_img) == "ACCEPTABLE", RT.grade(_tall, _pg_img))
_short = _patch(200, max(12, int(_page_h * 0.05)),
                (20, 2, 180, max(12, int(_page_h * 0.05)) - 2))
check("페이지의 5%%밖에 안 되는 크롭은 THIN_CROP",
      RT.grade(_short, _pg_img) == "THIN_CROP", RT.grade(_short, _pg_img))
# 옆면에 잉크가 닿아 있으면 상자가 그림을 자른 것입니다 - 여백을 털기 전에 봐야
# 답이 남아 있습니다.
_clip = _patch(200, int(_page_h * 0.5), (0, 20, 199, int(_page_h * 0.5) - 20))
check("옆면까지 잉크가 닿으면 EDGE_CLIPPED",
      RT.grade(_clip, _pg_img) == "EDGE_CLIPPED", RT.grade(_clip, _pg_img))
# 인테이크는 빈 사각형도 ACCEPTABLE이라고 부릅니다 - 페이지 대비 높이만 재니까.
# 인테이크는 그런 것을 만들지 않지만(run2의 644개 중 0개) 손으로 그린 상자는
# 만들 수 있습니다. 여백을 가로질러 끄는 것으로 행이 열려서는 안 됩니다.
check("잉크가 하나도 없는 그림은 크기와 무관하게 그림이 아니다",
      RT.grade(_patch(200, int(_page_h * 0.9)), _pg_img) == "NO_CROP",
      RT.grade(_patch(200, int(_page_h * 0.9)), _pg_img))
check("잉크가 한 점이라도 있으면 다시 재기로 돌아간다",
      RT.grade(_patch(200, int(_page_h * 0.5), (90, 90, 110, 110)), _pg_img)
      in ("ACCEPTABLE", "THIN_CROP"))
_g = RT.cut_and_grade(Image.open(_d2["Page_Raster"]), _d2)
check("cut_and_grade가 cut과 같은 그림을 낸다",
      _g is not None and _g[0].size == RT.cut(Image.open(_d2["Page_Raster"]),
                                              _d2)[0].size)
check("그리고 등급을 함께 준다", _g[2] in ("ACCEPTABLE", "THIN_CROP", "EDGE_CLIPPED"),
      _g[2])
check("상자가 쓸모없으면 아무것도 내지 않는다",
      RT.cut_and_grade(Image.open(_d2["Page_Raster"]),
                       dict(_d2, Figure_BBox="")) is None)

# 끝에서 끝까지: THIN_CROP인 행에 제대로 된 상자를 그리면 상태가 다시 매겨진다
FX3 = make_fixture.write(os.path.join(TMP, "fx3"))
RUN3 = FX3["draft"]
D3 = list(csv.DictReader(io.open(os.path.join(RUN3, "figure_intake_draft.csv"),
                                 encoding="utf-8")))
_d3 = [d for d in D3 if d["Figure_Crop"] and d["Page_Raster"]][0]
_p3 = Image.open(_d3["Page_Raster"])
_pw3, _ph3 = float(_d3["Page_Width_Pt"]), float(_d3["Page_Height_Pt"])
_full = "%.1f,%.1f,%.1f,%.1f" % (_pw3 * 0.05, _ph3 * 0.05, _pw3 * 0.95, _ph3 * 0.95)
_rows3 = list(csv.DictReader(io.open(os.path.join(RUN3, "figure_intake_draft.csv"),
                                     encoding="utf-8")))
_cols3 = list(_rows3[0])
for r in _rows3:
    if r["Draft_ID"] == _d3["Draft_ID"]:
        r["Crop_Quality_Status"] = "THIN_CROP"      # 옛 크롭에 대한 측정값
with io.open(os.path.join(RUN3, "figure_intake_draft.csv"), "w",
             encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols3)
    w.writeheader()
    w.writerows(_rows3)
_reg3 = os.path.join(RUN3, "validated_regions.csv")
_rr3 = list(csv.DictReader(io.open(_reg3, encoding="utf-8")))
_rc3 = list(_rr3[0]) + ["Human_Choice", "Human_Box"]
for r in _rr3:
    if r["Draft_ID"] == _d3["Draft_ID"]:
        r["Agreement"] = "DISAGREE"
        r["Human_Choice"] = "DRAWN"
        r["Human_Box"] = _full
with io.open(_reg3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_rc3)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _rc3} for r in _rr3])
AV.main(RUN3)
_after3 = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
    os.path.join(RUN3, "figure_intake_draft.csv"), encoding="utf-8"))}[_d3["Draft_ID"]]
check("사람이 큰 상자를 그리면 THIN_CROP이 다시 매겨진다",
      _after3["Crop_Quality_Status"] == "ACCEPTABLE",
      _after3["Crop_Quality_Status"])
check("그 크롭은 새 상자에서 왕복한다", RT.check(_after3, RUN3)[0] == "MATCH",
      RT.check(_after3, RUN3))
# 다시 재는 것은 통과시켜 주는 것이 아닙니다 - 작은 상자를 그리면 여전히 얇습니다.
_tiny_box = "%.1f,%.1f,%.1f,%.1f" % (_pw3 * 0.1, _ph3 * 0.1, _pw3 * 0.9,
                                     _ph3 * 0.1 + _ph3 * 0.04)
_rr3 = list(csv.DictReader(io.open(_reg3, encoding="utf-8")))
for r in _rr3:
    if r["Draft_ID"] == _d3["Draft_ID"]:
        r["Agreement"] = "DISAGREE"
        r["Human_Choice"] = "DRAWN"
        r["Human_Box"] = _tiny_box
with io.open(_reg3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr3[0]))
    w.writeheader()
    w.writerows(_rr3)
AV.main(RUN3)
_thin3 = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
    os.path.join(RUN3, "figure_intake_draft.csv"), encoding="utf-8"))}[_d3["Draft_ID"]]
check("얇은 상자를 그리면 THIN_CROP으로 다시 매겨진다 (통과가 아니라 측정)",
      _thin3["Crop_Quality_Status"] == "THIN_CROP",
      _thin3["Crop_Quality_Status"])

# =================== 그림이 옆 쪽에 있을 때: 행을 옮겨 자른다 ===================
# 2026-09-03: 아무도 자리를 못 잡은 57행의 옆 쪽에 탐지기를 돌리니 15행 옆에
# 그림이 있었습니다 - 본문의 언급을 캡션으로 잡은 행들. 그중 7행의 그림은 다른
# 행이 없어서, 옆 쪽에 그려 행을 옮기는 것만이 그 그림을 지키는 길입니다.
FX4 = make_fixture.write(os.path.join(TMP, "fx4"))
RUN4 = FX4["draft"]
D4 = list(csv.DictReader(io.open(os.path.join(RUN4, "figure_intake_draft.csv"),
                                 encoding="utf-8")))
_d4 = [d for d in D4 if d["Figure_Crop"] and d["Page_Raster"]][0]
_p4 = int(_d4["Page"])
_dir4 = os.path.dirname(_d4["Page_Raster"])
# 옆 쪽을 하나 만든다: 같은 문서, 다음 쪽, 그림 하나. 캡션 쪽의 축척으로 그린다.
_src_page = Image.open(_d4["Page_Raster"])
# 옆 쪽은 일부러 더 넓게 - run2에 쪽 크기가 다른 문서가 하나 있고, 옆 쪽의 크기를
# "이 쪽과 같다"고 베끼는 코드는 그 문서에서 상자를 엉뚱한 데 떨어뜨립니다.
_WIDER = 1.5
_next = Image.new("RGB", (int(_src_page.width * _WIDER), _src_page.height), "white")
_ID.Draw(_next).rectangle((_next.width * 0.15, _next.height * 0.20,
                           _next.width * 0.85, _next.height * 0.55),
                          fill=(20, 20, 20))
_next_path = os.path.join(_dir4, "page-%d.png" % (_p4 + 1))
_next.save(_next_path)
check("옆 쪽 래스터를 이름으로 찾는다 (page-N.png, 채움 자리 무관)",
      RT.sibling_raster(_d4["Page_Raster"], _p4 + 1) == _next_path
      and RT.sibling_raster(_d4["Page_Raster"], _p4 + 7) == "")
check("채워진 이름도 읽는다",
      RT.page_rasters(_dir4).get(_p4) == _d4["Page_Raster"])
_padded_dir = os.path.join(TMP, "padded")
os.makedirs(_padded_dir, exist_ok=True)
io.open(os.path.join(_padded_dir, "page-007.png"), "wb").write(b"x")
check("page-007.png은 7쪽이다", 7 in RT.page_rasters(_padded_dir))

# 큐가 옆 쪽을 실어 준다 - 두 탐지기가 후보를 못 냈고 유령이 아닌 행에만
_pw4, _ph4 = float(_d4["Page_Width_Pt"]), float(_d4["Page_Height_Pt"])
_npw4 = _pw4 * _WIDER                      # 옆 쪽의 진짜 폭 (pt)
_nb = RP.neighbours(_d4, RUN4)
check("큐가 그 쪽과 크기를 싣는다 - 래스터에서 유도한 크기로",
      ("%d:%.1fx%.1f" % (_p4 + 1, _npw4, _ph4)) in _nb.split(";"), _nb)
check("캡션 쪽 자신은 싣지 않는다 (카드가 이미 들고 있다)",
      not any(x.startswith("%d:" % _p4) for x in _nb.split(";")), _nb)
# 창은 문서 전체를 겨냥하되 한계가 있습니다 - 그 한계가 옮길 수 있는 거리와
# 같아야, 사람이 그릴 수 있는 쪽과 적용이 받아 주는 쪽이 어긋나지 않습니다.
check("판정 페이지가 보여 주는 범위와 옮길 수 있는 거리가 같다",
      AV.MOVE_REACH == RP.PAGE_WINDOW, (AV.MOVE_REACH, RP.PAGE_WINDOW))
check("창 안의 쪽만 실린다",
      all(abs(int(x.split(":")[0]) - _p4) <= RP.PAGE_WINDOW
          for x in _nb.split(";") if x), _nb)
check("옆 쪽이 없으면 빈 값이다",
      RP.neighbours(dict(_d4, Page=str(_p4 + 50)), RUN4) == "")

# 옮겨서 자른다. PDF 크기는 픽스처에 PDF가 없으므로 오라클을 꽂는다 - 실제
# 실행에서는 `figure_regions.page_objects`가 답합니다.
_BR4 = os.path.join(RUN4, RP.BLOCK_REASONS)
_reg4 = os.path.join(RUN4, "validated_regions.csv")
_asked = []
def _oracle(src, page):
    _asked.append((src, page))
    return (_npw4, _ph4)
AV.page_size_from_pdf = _oracle
_box_next = "%.1f,%.1f,%.1f,%.1f" % (_npw4 * 0.15, _ph4 * 0.20, _npw4 * 0.85, _ph4 * 0.55)


def _set4(did, **fields):
    rows = list(csv.DictReader(io.open(_reg4, encoding="utf-8")))
    cols = list(rows[0])
    for c in fields:
        if c not in cols:
            cols.append(c)
    for r in rows:
        if r["Draft_ID"] == did:
            r.update(fields)
    with io.open(_reg4, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in rows])


def _draft4(did):
    return {d["Draft_ID"]: d for d in csv.DictReader(io.open(
        os.path.join(RUN4, "figure_intake_draft.csv"), encoding="utf-8"))}[did]


_set4(_d4["Draft_ID"], Agreement="NONE", Human_Choice="DRAWN",
      Human_Box=_box_next, Human_Page=str(_p4 + 1))
AV.main(RUN4)
_m = _draft4(_d4["Draft_ID"])
check("옆 쪽에 그린 상자로 행이 그 쪽으로 옮겨진다", _m["Page"] == str(_p4 + 1), _m["Page"])
check("페이지 래스터도 그 쪽 것이 된다", _m["Page_Raster"] == _next_path, _m["Page_Raster"])
check("캡션이 있던 쪽을 잊지 않는다",
      _m["Caption_Page"] == str(_p4) and _m["Moved_From_Page"] == str(_p4))
check("옮긴 쪽의 크기는 PDF에 물어본 값이다 (캡션 쪽 크기가 아니다)",
      _asked and _asked[-1][1] == _p4 + 1 and
      abs(float(_m["Page_Width_Pt"]) - _npw4) < 0.01, (_asked[-1:], _m["Page_Width_Pt"]))
check("크롭은 옆 쪽 그림에서 잘렸고 그 상자에서 왕복한다",
      RT.check(_m, RUN4)[0] == "MATCH" and _m["Figure_BBox"] == _box_next,
      RT.check(_m, RUN4))
_cropped = Image.open(os.path.join(RUN4, _m["Figure_Crop"])).convert("L")
check("잘린 것이 옆 쪽의 검은 그림이다 (캡션 쪽 그림이 아니다)",
      __import__("numpy").asarray(_cropped).mean() < 60)
check("상태가 다시 매겨졌다", _m["Crop_Quality_Status"] == "ACCEPTABLE")

# 거부되는 것들 - 각각 이름으로
_d4b = [d for d in D4 if d["Figure_Crop"] and d["Page_Raster"]
        and d["Draft_ID"] != _d4["Draft_ID"]][0]
_p4b = int(_d4b["Page"])
_off = _p4b + AV.MOVE_REACH + 1
_far = os.path.join(os.path.dirname(_d4b["Page_Raster"]), "page-%d.png" % _off)
_next.save(_far)
_set4(_d4b["Draft_ID"], Agreement="NONE", Human_Choice="DRAWN",
      Human_Box=_box_next, Human_Page=str(_off))
AV.main(RUN4)
check("창 밖의 쪽으로는 옮기지 않는다",
      _draft4(_d4b["Draft_ID"])["Page"] == str(_p4b))
_next.save(os.path.join(os.path.dirname(_d4b["Page_Raster"]), "page-%d.png" % (_p4b + 1)))
AV.page_size_from_pdf = lambda src, page: (_npw4 + 30.0, _ph4)
_set4(_d4b["Draft_ID"], Human_Page=str(_p4b + 1))
AV.main(RUN4)
check("래스터로 유도한 크기가 PDF와 다르면 옮기지 않는다",
      _draft4(_d4b["Draft_ID"])["Page"] == str(_p4b))
AV.page_size_from_pdf = lambda src, page: None
AV.main(RUN4)
check("PDF에서 크기를 확인할 수 없어도 옮기지 않는다",
      _draft4(_d4b["Draft_ID"])["Page"] == str(_p4b))
AV.page_size_from_pdf = _oracle
# 그 쪽에 같은 그림의 행이 이미 있으면 - 유령 규칙이 막으려는 바로 그 중복
_twin_page = str(_p4b + 1)
_rows_d = list(csv.DictReader(io.open(os.path.join(RUN4, "figure_intake_draft.csv"),
                                      encoding="utf-8")))
_cols_d = list(_rows_d[0])
_twin = dict(_rows_d[0], Draft_ID=_d4b["Source_Document_ID"] + "_D900",
             Source_Document_ID=_d4b["Source_Document_ID"],
             Figure_Number=_d4b["Figure_Number"], Page=_twin_page,
             Figure_Crop="", Page_Raster="", Crop_Quality_Status="NO_CROP",
             Figure_BBox="")
_rows_d.append(_twin)
with io.open(os.path.join(RUN4, "figure_intake_draft.csv"), "w",
             encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=_cols_d)
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in _cols_d} for r in _rows_d])
_rr = list(csv.DictReader(io.open(_reg4, encoding="utf-8")))
_rr.append(dict(_rr[0], Draft_ID=_twin["Draft_ID"], Agreement="NONE",
                Human_Choice="", Human_Box="", Human_Page=""))
with io.open(_reg4, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr[0]))
    w.writeheader()
    w.writerows(_rr)
AV.main(RUN4)
check("옮겨 갈 쪽에 같은 그림의 행이 이미 있으면 옮기지 않는다 (두 번 세게 됨)",
      _draft4(_d4b["Draft_ID"])["Page"] == str(_p4b))
# 그런데 그 거부는 대답이기도 합니다: 사람이 그림을 찾았고, 그 쪽의 다른 행이
# 이미 세고 있다. 2026-09-04에 47개 답 중 20개가 이 경우였는데, 행은 옛
# HUMAN_BLOCKED 사유를 그대로 단 채 Human_Choice만 DRAWN이었습니다 - 사람이
# 그림을 찾았다는 사실이 아무 데도 적히지 않았습니다.
def _reg4_row(did):
    return {r["Draft_ID"]: r for r in csv.DictReader(
        io.open(_reg4, encoding="utf-8"))}[did]
_dup4 = _reg4_row(_d4b["Draft_ID"])
check("옮기지 못한 이유가 '그 그림은 저 행이 센다'이면 그 행을 적어 둔다",
      _dup4.get(AV.DUPLICATE_OF) == _twin["Draft_ID"], _dup4.get(AV.DUPLICATE_OF))
check("사람이 그린 쪽도 함께 적는다",
      _dup4.get(AV.DUPLICATE_PAGE) == _twin_page, _dup4.get(AV.DUPLICATE_PAGE))
check("행은 여전히 옮겨지지도 다시 잘리지도 않았다",
      _draft4(_d4b["Draft_ID"])["Page"] == str(_p4b)
      and not _draft4(_d4b["Draft_ID"]).get("Moved_From_Page"))
check("적어 둔 중복은 사람의 상자가 찾은 것으로 읽힌다",
      BR.confirmed_duplicates([_dup4]) ==
      {_d4b["Draft_ID"]: (_twin["Draft_ID"], _twin_page, BR.CONFIRMED_BY_BOX)},
      BR.confirmed_duplicates([_dup4]))
check("Duplicate_Of가 빈 행은 중복으로 읽히지 않는다",
      BR.confirmed_duplicates([dict(_dup4, Duplicate_Of="")]) == {})
# 다음 답이 오면 이전 답이 밝힌 중복은 함께 물러납니다 - 상자를 자기 쪽에 다시
# 그리면 그것이 무엇인지는 apply가 새로 판단합니다.
_set4(_d4b["Draft_ID"], Human_Page=str(_p4b))
AV.main(RUN4)
check("새 답이 오면 이전 답의 중복 기록은 지워진다",
      _reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_OF) == ""
      and _reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_PAGE) == "",
      (_reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_OF),))
# 병합도 같은 규칙: 사람이 다시 답하면 옛 중복 기록은 그 답과 함께 떠납니다.
_set4(_d4b["Draft_ID"], Human_Page=_twin_page)
AV.main(RUN4)
check("(다시 옆 쪽으로 답하면 중복이 다시 적힌다)",
      _reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_OF) == _twin["Draft_ID"])
_q4 = os.path.join(TMP, "q4.csv")
with io.open(_q4, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerow({c: "" for c in RP.FIELDS} | {
        "Draft_ID": _d4b["Draft_ID"], "Human_Choice": "BLOCKED",
        "Crop_SHA256": _sha(os.path.join(RUN4, _draft4(_d4b["Draft_ID"])["Figure_Crop"])),
        "Proposal_Figure_BBox": _draft4(_d4b["Draft_ID"])["Figure_BBox"],
        "Block_Reason": "x"})
RP.merge(RUN4, _q4)
check("병합된 새 답은 옛 중복 기록을 지운다",
      _reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_OF) == "",
      _reg4_row(_d4b["Draft_ID"]).get(AV.DUPLICATE_OF))
_set4(_d4b["Draft_ID"], Human_Choice="DRAWN", Human_Page=_twin_page)
AV.main(RUN4)
check("캡션 쪽 번호를 적어 보내면 옮기지 않고 그대로 자른다",
      AV.moved_page(_d4b, str(_p4b), RUN4, {}, {})[0]["Page"] == str(_p4b))
check("읽을 수 없는 쪽 번호는 이름으로 거부한다",
      "읽을 수 없음" in AV.moved_page(_d4b, "여섯", RUN4, {}, {})[1])
# 옮긴 행이 다시 검증표를 만들 때 캡션 상자를 엉뚱한 쪽에 넘기지 않는가
check("옮긴 행은 캡션 상자를 새 쪽의 제안자에게 넘기지 않는다",
      "cap_page != str(r.get(\"Page\")" in io.open(
          os.path.join(HERE, "validate_regions.py"), encoding="utf-8").read())

# ============================ 막힌 행 전부를 담는 큐 ============================
# 큐는 시트가 무엇을 막았는지 **시트가 적어 둔 것**을 읽어야 합니다. 다시 계산하면
# 부분적인 관점(빈 키·조사표 없음)으로 판단하게 되고, 그 불일치 때문에 사람이
# 답한 행이 무시된 적이 있습니다.
_BR3 = os.path.join(RUN3, RP.BLOCK_REASONS)
try:
    RP.blocked(RUN3)
    _closed = False
except SystemExit:
    _closed = True
check("사유 표가 없으면 목록을 지어내지 않고 멈춘다", _closed)
_ids3 = [d["Draft_ID"] for d in D3]
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    for i, did in enumerate(_ids3):
        w.writerow({"Draft_ID": did,
                    "Count_Blocked": "1" if i < 3 else "0",
                    "Reason": "시험용 사유 %d" % i,
                    "Box_Would_Open": "1" if i == 2 else "0"})
_blocked = RP.blocked(RUN3)
check("막힌 행만 큐에 담긴다", len(_blocked) == 3, len(_blocked))
# 중복은 질문이 아닙니다. 시트가 "저 행이 이 그림을 센다"고 적은 행에 사람이
# 할 수 있는 일은 없습니다 - 반대라면 이긴 행을 막고, 그 카드가 그 자리입니다.
# 2026-09-04에 47개 답 중 16개가 이 이유로 다시 질문받았습니다.
_rows_br0 = list(csv.DictReader(io.open(_BR3, encoding="utf-8")))
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open", "Duplicate_Of"])
    w.writeheader()
    for r in _rows_br0:
        r = dict(r, Duplicate_Of=_ids3[1] if r["Draft_ID"] == _ids3[0] else "")
        w.writerow(r)
_blocked_d = RP.blocked(RUN3)
check("다른 행이 세는 그림의 중복 행은 큐에 오르지 않는다",
      len(_blocked_d) == 2 and _ids3[0] not in {r["Draft_ID"] for r in _blocked_d},
      [r["Draft_ID"][-6:] for r in _blocked_d])
check("묻지 않은 중복의 수를 말한다", RP.blocked.settled == 1, RP.blocked.settled)

# ---------------------------------- 번호를 적는 칸: 큐 → 병합 → 적용까지 닿는가
check("적어 낸 번호가 저장 철자로 바뀐다",
      [AV.figure_number(t)[0] for t in
       ("4", "fig4", "Fig. 4", "Figure 4b", "Extended Data Fig 2", "그림 3")]
      == ["FIG4", "FIG4", "FIG4", "FIG4B", "EXTFIG2", "FIG3"],
      [AV.figure_number(t)[0] for t in ("4", "fig4", "Figure 4b")])
check("읽을 수 없는 번호는 이름으로 거부한다 (빈 값으로 삼키지 않는다)",
      AV.figure_number("넷")[0] == "" and "읽을 수 없음" in AV.figure_number("넷")[1])
check("빈 칸은 거부가 아니라 '적지 않음'이다",
      AV.figure_number("") == ("", "") and AV.figure_number(None) == ("", ""))
check("두 그림을 한꺼번에 적는 것은 받지 않는다",
      AV.figure_number("fig 4 and 5")[0] == "")

_numrow = [d for d in D4 if d["Figure_Crop"]][-1]
_set4(_numrow["Draft_ID"], **{AV.HUMAN_NUMBER: "Figure 7b"})
AV.main(RUN4)
check("적어 낸 번호가 초안의 Figure_Number가 된다",
      _draft4(_numrow["Draft_ID"])["Figure_Number"] == "FIG7B",
      _draft4(_numrow["Draft_ID"])["Figure_Number"])
check("그리고 그것이 사람의 것이라고 적힌다 (기계의 번호와 구분된다)",
      _draft4(_numrow["Draft_ID"])["Number_Source"] == BR.NUMBER_BY_HUMAN)
check("번호만 적은 행은 다시 잘리지 않는다 (상자를 건드리지 않았다)",
      _draft4(_numrow["Draft_ID"])["Figure_BBox"] == _numrow["Figure_BBox"])
_set4(_numrow["Draft_ID"], **{AV.HUMAN_NUMBER: "넷"})
_before_bad = _draft4(_numrow["Draft_ID"])["Figure_Number"]
AV.main(RUN4)
check("읽을 수 없는 번호는 초안을 바꾸지 않는다",
      _draft4(_numrow["Draft_ID"])["Figure_Number"] == _before_bad)
_set4(_numrow["Draft_ID"], **{AV.HUMAN_NUMBER: ""})

# 큐가 번호 칸을 들고 나가고, 병합이 그것을 받아 검증표에 남기는가
_qn = os.path.join(TMP, "qnum.csv")
_nid = _ids3[1]
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open", "Number_Would_Open"])
    w.writeheader()
    for i, did in enumerate(_ids3):
        w.writerow({"Draft_ID": did, "Count_Blocked": "1" if i < 3 else "0",
                    "Reason": "시험용 사유 %d" % i, "Box_Would_Open": "0",
                    "Number_Would_Open": "1" if did == _nid else "0"})
_bn = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("큐가 '번호가 필요한가'를 들고 나간다",
      _bn[_nid]["Number_Would_Open"] == "1"
      and all(r["Number_Would_Open"] == "0" for k, r in _bn.items() if k != _nid),
      [(k[-6:], r["Number_Would_Open"]) for k, r in _bn.items()])
check("번호가 필요한 행은 상자로 안 풀려도 앞에 온다 (사람이 할 일이 있다)",
      RP.blocked(RUN3)[0]["Draft_ID"] == _nid,
      [r["Draft_ID"][-6:] for r in RP.blocked(RUN3)])
with io.open(_qn, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    # 페이지가 하는 대로 - 큐 행을 그대로 되돌려 보내고 사람이 채운 칸만 덮습니다.
    w.writerow(dict({c: _bn[_nid].get(c, "") for c in RP.FIELDS},
                    **{RP.HUMAN_NUMBER: "fig 9"}))
RP.merge(RUN3, _qn)
_reg3_after = {r["Draft_ID"]: r for r in csv.DictReader(
    io.open(_reg3, encoding="utf-8"))}
check("병합이 적어 낸 번호를 검증표에 남긴다",
      _reg3_after[_nid].get(RP.HUMAN_NUMBER) == "fig 9",
      _reg3_after[_nid].get(RP.HUMAN_NUMBER))
check("번호만 적은 행도 '답했다'로 기록된다 (고른 것이 없어도)",
      _reg3_after[_nid].get(RP.ANSWERED_KEY, "") != "",
      _reg3_after[_nid].get(RP.ANSWERED_KEY))
# 그리고 그 행은 다음 큐에서 빠집니다.
check("번호를 적은 행은 같은 질문으로 다시 오지 않는다",
      _nid not in {r["Draft_ID"] for r in RP.blocked(RUN3)},
      [r["Draft_ID"][-6:] for r in RP.blocked(RUN3)])

# ------------------------------- 왜 다시 묻는지 카드가 말하는가
# 답이 질문을 바꾸는 경우가 있습니다: 행을 **막으면** 그 행에 문서 창이 붙고,
# 창이 붙은 것은 새 질문이므로 그 행이 곧바로 돌아옵니다. "답하셨을 때와
# 달라졌습니다"만으로는 무엇이 달라졌는지 알 수 없어, 두 번 물어보게 됐습니다.
_wf = {"Block_Reason": "r", "Crop_SHA256": "s", RP.NEIGHBOURS: "1:600x800"}
_rk = RP.reason_key(_wf)
check("창이 생겨서 돌아온 것이면 그렇게 말한다",
      RP.ask_again_why(_wf, "-", _rk) == RP.ASK_AGAIN_WHY["WINDOW"],
      RP.ask_again_why(_wf, "-", _rk))
check("막힌 이유가 달라진 것이면 그렇게 말한다",
      RP.ask_again_why(_wf, "W", "낡은값") == RP.ASK_AGAIN_WHY["REASON"])
check("이유가 달라졌으면 창보다 이유를 먼저 말한다 (더 큰 변화다)",
      RP.ask_again_why(_wf, "-", "낡은값") == RP.ASK_AGAIN_WHY["REASON"])
check("둘 다 그대로면 나머지가 달라진 것이다",
      RP.ask_again_why(_wf, "W", _rk) == RP.ASK_AGAIN_WHY["OTHER"])
# 기록이 없으면 지어내지 않습니다 - 이 칸이 생기기 전에 답한 행이 있습니다.
check("기록이 없으면 모른다고 말한다 (없는 이유를 지어내지 않는다)",
      RP.ask_again_why(_wf, "", "") == RP.ASK_AGAIN_WHY["UNKNOWN"])
check("네 문장이 서로 다르다",
      len(set(RP.ASK_AGAIN_WHY.values())) == 4)
check("창 표시는 쪽 목록이 아니라 있고 없음이다",
      RP.window_flag(_wf) == "W" and RP.window_flag({}) == "-")
check("이유 열쇠는 '다시 묻습니다' 머리말을 벗기고 만든다",
      RP.reason_key({"Block_Reason": RP.ASK_AGAIN + "r"})
      == RP.reason_key({"Block_Reason": "r"}))

# 그리고 답할 때의 두 부분이 실제로 기록되는가
_q5 = os.path.join(TMP, "q5.csv")
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open", "Number_Would_Open"])
    w.writeheader()
    for did in _ids3:
        w.writerow({"Draft_ID": did, "Count_Blocked": "1", "Reason": "왜인가",
                    "Box_Would_Open": "1", "Number_Would_Open": "0"})
_b5 = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
_wid = _ids3[0]
with io.open(_q5, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerow(dict({c: _b5[_wid].get(c, "") for c in RP.FIELDS},
                    **{"Human_Choice": "BLOCKED"}))
RP.merge(RUN3, _q5)
_r5 = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg3, encoding="utf-8"))}
check("답할 때의 창 여부를 기록한다",
      _r5[_wid].get(RP.ANSWERED_WINDOW) == RP.window_flag(_b5[_wid]),
      (_r5[_wid].get(RP.ANSWERED_WINDOW), RP.window_flag(_b5[_wid])))
check("답할 때의 이유도 기록한다",
      _r5[_wid].get(RP.ANSWERED_REASON) == RP.reason_key(_b5[_wid]),
      _r5[_wid].get(RP.ANSWERED_REASON))
check("같은 질문이면 그 행은 큐에 오지 않는다",
      _wid not in {r["Draft_ID"] for r in RP.blocked(RUN3)})

# 그리고 실제로 돌아올 때 큐가 그 문장을 들고 오는가 - 함수만 맞고 큐가 비어
# 있으면 카드에도 아무것도 실리지 않습니다.
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open", "Number_Would_Open"])
    w.writeheader()
    for did in _ids3:
        w.writerow({"Draft_ID": did, "Count_Blocked": "1",
                    "Reason": "이유가 달라졌습니다" if did == _wid else "왜인가",
                    "Box_Would_Open": "1", "Number_Would_Open": "0"})
_back5 = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("이유가 달라지면 그 행이 다시 온다", _wid in _back5)
check("돌아온 행이 무엇이 달라졌는지 들고 온다",
      _back5.get(_wid, {}).get("Ask_Again_Why") == RP.ASK_AGAIN_WHY["REASON"],
      _back5.get(_wid, {}).get("Ask_Again_Why"))

# ------------------------------- 저장할 수 없는 번호는 답이 아니다
# 번호 칸에 'x'를 적고 판정은 비워 보낸 행이 있었습니다. 뜻은 "고를 게 없다"였고
# 그것은 사람만 내릴 수 있는 판정인데, 아무 글자나 답으로 세면 그 행은 **막힌
# 채로** 큐에서 빠집니다 - 번호도 없고 판정도 없이, 다시 묻지도 않고.
check("저장할 수 없는 번호는 답이 아니다", not RP.answered({RP.HUMAN_NUMBER: "x"}))
check("읽히는 번호는 판정 없이도 답이다", RP.answered({RP.HUMAN_NUMBER: "fig4"}))
check("판정은 번호가 없어도 답이다", RP.answered({"Human_Choice": "BLOCKED"}))
check("둘 다 비면 답이 아니다", not RP.answered({}))

_b6 = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
_reg6 = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg3, encoding="utf-8"))}
# 앞선 시나리오들이 답을 남겨 둔 행은 피합니다 - 여기서 보려는 것은 "답으로
# 세는가"이므로, 이미 세어진 행에서는 아무것도 보이지 않습니다.
_uid = next((i for i in _b6
             if not (_reg6.get(i, {}).get(RP.ANSWERED_KEY) or "").strip()), "")
check("아직 답하지 않은 행이 큐에 있다", bool(_uid), sorted(_b6))
_q6 = os.path.join(TMP, "q6.csv")
with io.open(_q6, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerow(dict({c: _b6[_uid].get(c, "") for c in RP.FIELDS},
                    **{"Human_Choice": "", RP.HUMAN_NUMBER: "x"}))
RP.merge(RUN3, _q6)
_r6 = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg3, encoding="utf-8"))}
check("그 행은 답한 것으로 표시되지 않는다",
      not (_r6[_uid].get(RP.ANSWERED_KEY) or "").strip(),
      _r6[_uid].get(RP.ANSWERED_KEY))
check("그래서 그 행은 큐에 남는다 (판정 없이 사라지지 않는다)",
      _uid in {r["Draft_ID"] for r in RP.blocked(RUN3)})
check("적어 낸 글자는 버리지 않고 그대로 들고 있는다",
      _r6[_uid].get(RP.HUMAN_NUMBER) == "x", _r6[_uid].get(RP.HUMAN_NUMBER))

# 그리고 왜 안 됐는지 **사람이 보는 자리에** 있어야 합니다. 거부는 이미 이름을
# 달고 있었지만, 그 이름은 아무도 읽지 않는 터미널로 갔습니다.
check("거부 사유가 큐에 실린다",
      "x" in ({r["Draft_ID"]: r for r in RP.blocked(RUN3)}
              .get(_uid, {}).get("Number_Refused", "")),
      {r["Draft_ID"]: r for r in RP.blocked(RUN3)}.get(_uid, {}).get("Number_Refused"))
check("읽히는 번호에는 거부 사유가 없다", RP.number_refused("fig4") == "")
check("빈 칸은 거부가 아니다", RP.number_refused("") == "")

# 카드까지 오는가 - 픽스처 RUN의 큐에 거부를 하나 얹어 봅니다. 번호를 청하는
# 행에만 실려야 하므로, 청하는 행(QUEUE[2])에 얹습니다.
_q7 = _rewrite_queue()
_q7 = [{c: r.get(c, "") for c in RP.FIELDS} for r in _q7]
check("픽스처 큐에 행이 있다", bool(_q7))
_q7[0]["Number_Would_Open"] = "1"
_q7[0]["Number_Refused"] = RP.number_refused("x")
with io.open(QPATH, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows(_q7)
_out4 = os.path.join(TMP, "out4")
subprocess.run([sys.executable, os.path.join(HERE, "review_sheet.py"), RUN, _out4],
               capture_output=True, text=True, cwd=HERE)
_S4 = "\n".join(io.open(os.path.join(_out4, f), encoding="utf-8").read()
                for f in sorted(os.listdir(_out4))
                if f.startswith("review_choose_"))
check("거부 사유가 카드에 적힌다 (터미널이 아니라)",
      "class='numbad'" in _S4 and "를 읽을 수 없음" in _S4)
check("거부가 있는 행에만 붙는다 (1행)",
      _S4.count("class='numbad'") == 1, _S4.count("class='numbad'"))
_rewrite_queue()

# 그리고 그 문장이 카드에 실제로 실리는가 - 문장만 맞고 화면에 없으면 없는 것입니다.
_qa = _rewrite_queue()
_qa_rows = [{c: r.get(c, "") for c in RP.FIELDS} for r in _qa]
if _qa_rows:
    _qa_rows[0]["Ask_Again_Why"] = RP.ASK_AGAIN_WHY["WINDOW"]
    with io.open(QPATH, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
        w.writeheader()
        w.writerows(_qa_rows)
    _out3 = os.path.join(TMP, "out3")
    subprocess.run([sys.executable, os.path.join(HERE, "review_sheet.py"),
                    RUN, _out3], capture_output=True, text=True, cwd=HERE)
    _S3 = "\n".join(io.open(os.path.join(_out3, f), encoding="utf-8").read()
                    for f in sorted(os.listdir(_out3))
                    if f.startswith("review_choose_"))
    check("다시 묻는 이유가 카드에 적힌다",
          "다시 묻는 이유" in _S3
          and "막으신 행에는 문서 전체를 싣습니다" in _S3)
    check("이유가 적힌 행에만 그 알림이 붙는다 (1행)",
          _S3.count("class='again'") == 1, _S3.count("class='again'"))
    _rewrite_queue()

# 번호 칸이 생긴 것은 새 질문입니다 - 없던 자리가 생겼으니까.
_k_no = RP.question_key({"Block_Reason": "r", "Crop_SHA256": "s",
                         "Number_Would_Open": "0"})
_k_yes = RP.question_key({"Block_Reason": "r", "Crop_SHA256": "s",
                          "Number_Would_Open": "1"})
check("번호 칸이 생기면 새 질문이 된다", _k_no != _k_yes)
# 그러나 없는 행에는 아무것도 더하지 않습니다 - 그러지 않으면 코퍼스의 모든
# 행이 한꺼번에 다시 열립니다 (첫 시도에서 11행이 그렇게 돌아왔습니다).
check("번호 칸이 없는 행의 열쇠는 예전 그대로다",
      _k_no == RP.question_key({"Block_Reason": "r", "Crop_SHA256": "s"}))
# 그리고 그 값 자체를 못 박습니다. 위의 두 호출은 같은 함수를 두 번 부르는
# 것이라 조리법이 통째로 바뀌어도 서로 같습니다 - 실제로 첫 판에서 모든 행에
# 표시를 붙였다가 코퍼스 전체의 열쇠가 한꺼번에 움직였고, 아무도 답한 적 없는
# 11행이 큐로 돌아왔습니다. 이 상수가 움직이면 그것은 "다시 물어야 할 행이
# 늘었다"가 아니라 "모두에게 다시 묻는다"는 뜻이므로, 일부러 그럴 때만
# 바꿉니다.
check("그 열쇠 값은 못 박혀 있다 (조리법이 바뀌면 코퍼스 전체가 다시 열린다)",
      RP.question_key({"Block_Reason": "r", "Crop_SHA256": "s"})
      == "756c9168928be6d4",
      RP.question_key({"Block_Reason": "r", "Crop_SHA256": "s"}))
check("빈 행의 열쇠도 못 박혀 있다",
      RP.question_key({}) == "d6d8c3058386ff3e", RP.question_key({}))

# 번호만 적은 행은 크롭을 건드리지 않았으므로, 그 크롭이 자기 상자에서
# 재현되지 않더라도 이 실행의 책임이 아닙니다 - 그렇게 세면 번호를 받아 준
# 것이 "쓰기가 잘못됐다"로 보고됩니다.
# `selfcheck`는 앞에서 세 행만 표본으로 보므로, 뒤쪽 행의 낡은 크롭은 그 문을
# 지나갑니다 - 이 검사가 노리는 자리가 정확히 거기입니다.
_bad = [d for d in D4 if d["Figure_Crop"] and d["Page_Raster"]][-1]
_badpath = os.path.join(RUN4, _bad["Figure_Crop"])
_keep = io.open(_badpath, "rb").read()
Image.new("RGB", (7, 7), "white").save(_badpath)
check("(먼저 그 크롭이 왕복하지 않는 상태를 만든다)",
      RT.check(_draft4(_bad["Draft_ID"]), RUN4)[0] != "MATCH",
      RT.check(_draft4(_bad["Draft_ID"]), RUN4))
check("(그리고 그 행은 selfcheck의 표본 밖이다)",
      RT.selfcheck(RUN4) >= 3)
_set4(_bad["Draft_ID"], Human_Choice="", **{AV.HUMAN_NUMBER: "fig 6"})
try:
    AV.main(RUN4)
    _num_ok = True
except SystemExit:
    _num_ok = False
check("번호만 받은 행의 낡은 크롭을 이 실행의 잘못으로 보고하지 않는다", _num_ok)
check("그래도 번호는 들어갔다",
      _draft4(_bad["Draft_ID"])["Figure_Number"] == "FIG6",
      _draft4(_bad["Draft_ID"])["Figure_Number"])
io.open(_badpath, "wb").write(_keep)
_set4(_bad["Draft_ID"], **{AV.HUMAN_NUMBER: ""})

check("중복이 아닌 막힌 행은 그대로 묻는다",
      {r["Draft_ID"] for r in _blocked_d} == set(_ids3[1:3]))
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    w.writerows(_rows_br0)
check("시트의 사유를 그대로 들고 온다",
      all("시험용 사유" in r["Block_Reason"] for r in _blocked))
check("상자로 풀리는지도 들고 온다",
      sorted(r["Box_Would_Open"] for r in _blocked) == ["0", "0", "1"])
check("상자로 풀리는 행이 앞에 온다", _blocked[0]["Box_Would_Open"] == "1",
      [r["Box_Would_Open"] for r in _blocked])
check("번호는 1부터 다시 매겨진다",
      [r["No"] for r in _blocked] == [1, 2, 3])
# 사유 표가 초안보다 오래되면 조용히 일부만 내놓지 않고 멈춥니다.
_rows_br = list(csv.DictReader(io.open(_BR3, encoding="utf-8")))[:-1]
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    w.writerows(_rows_br)
try:
    RP.blocked(RUN3)
    _stale_ok = False
except SystemExit:
    _stale_ok = True
check("사유 표가 초안보다 오래되면 멈춘다", _stale_ok)
# 옆 쪽은 어느 제안자도 답하지 못한(NONE) 행에만 실립니다 - TAKEN·AMBIGUOUS도
# NONE입니다; 실제로 옆 쪽에서 그림이 나온 7행 중 3행이 TAKEN이었습니다.
_ids3b = [d["Draft_ID"] for d in D3 if d["Page_Raster"]]
_nbdir = os.path.dirname([d for d in D3 if d["Page_Raster"]][0]["Page_Raster"])
_d3n = [d for d in D3 if d["Page_Raster"]][0]
Image.new("RGB", Image.open(_d3n["Page_Raster"]).size, "white").save(
    os.path.join(_nbdir, "page-%d.png" % (int(_d3n["Page"]) + 1)))
with io.open(_BR3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    for did in _ids3:
        w.writerow({"Draft_ID": did, "Count_Blocked": "1", "Reason": "r",
                    "Box_Would_Open": "1"})
_rr3 = list(csv.DictReader(io.open(_reg3, encoding="utf-8")))
for r in _rr3:
    if r["Draft_ID"] == _d3n["Draft_ID"]:
        # 어느 탐지기도 상자를 내지 못한 행: 코드는 TAKEN이고 상자는 없습니다.
        r["Agreement"] = "NONE"
        r["PDF_BBox"] = r["Raster_BBox"] = ""
    else:
        r["Agreement"] = "AGREE_2_TEXT_DIFFERS"
    r["PDF_Code"] = r["Raster_Code"] = "TAKEN"
with io.open(_reg3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr3[0]))
    w.writeheader()
    w.writerows(_rr3)
_bq = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("어느 탐지기도 상자를 내지 못한 행에는 문서의 다른 쪽을 싣는다",
      _bq[_d3n["Draft_ID"]]["Neighbours"] != "", _bq[_d3n["Draft_ID"]]["Neighbours"])
check("탐지기가 상자를 낸 행에는 싣지 않는다 (그 쪽에 보여 줄 것이 있다)",
      all(r["Neighbours"] == "" for k, r in _bq.items() if k != _d3n["Draft_ID"]))
# 사람이 이미 막은 행이야말로 다시 볼 때 창이 필요합니다. 2026-09-03에 84행을
# 돌려받았을 때, 막힌 46행 중 창을 받은 행이 0이었습니다 - `Agreement`가
# HUMAN_BLOCKED로 바뀌면서 조건에서 빠졌기 때문입니다.
_rr3b = list(csv.DictReader(io.open(_reg3, encoding="utf-8")))
for r in _rr3b:
    if r["Draft_ID"] != _d3n["Draft_ID"]:
        r["Agreement"] = "HUMAN_BLOCKED"
        r["PDF_BBox"] = r["Raster_BBox"] = "10,10,200,200"
with io.open(_reg3, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(_rr3b[0]))
    w.writeheader()
    w.writerows(_rr3b)
_bq2 = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
# 한 쪽짜리 문서에는 실을 다른 쪽이 없습니다 - 그건 이 규칙과 무관합니다.
_multi = {d["Draft_ID"] for d in D3
          if (d.get("Page_Raster") or "").strip()
          and len(RT.page_rasters(os.path.dirname(d["Page_Raster"]))) > 1}
_others = [r for k, r in _bq2.items()
           if k != _d3n["Draft_ID"] and k in _multi]
check("사람이 막은 행은 상자가 있어도 창을 받는다 (다시 보라고 준 것이다)",
      _others and all(r["Neighbours"] != "" for r in _others),
      [(r["Draft_ID"][-8:], r["Neighbours"][:20]) for r in _others])

# ==================== 이미 답한 질문은 다시 묻지 않는다 ====================
# 2026-09-03: 막힌 행 큐를 세 번 냈는데, 세 번째에 79행이 나왔고 **79행 모두**
# 직전 라운드에서 답한 행이었습니다(78행은 그 전에도). 큐가 "막힌 행 전부"를
# 뜻하는 한, 답할수록 같은 것을 다시 받습니다. 사람이 말했습니다:
# "이미 골랐던 피규어 또 고르라고 하는데?"
_QK = dict(Block_Reason="이유", Crop_SHA256="a" * 64,
           Proposal_Figure_BBox="1,2,3,4", PDF_BBox="5,6,7,8",
           Raster_BBox="9,10,11,12", Neighbours="")
check("같은 질문은 같은 열쇠를 낸다", RP.question_key(_QK) == RP.question_key(dict(_QK)))
for _f in ("Block_Reason", "Crop_SHA256", "Proposal_Figure_BBox", "PDF_BBox",
           "Raster_BBox"):
    check("%s이(가) 바뀌면 새 질문이다" % _f,
          RP.question_key(dict(_QK, **{_f: "달라짐"})) != RP.question_key(_QK))
check("문서 창이 생기면 새 질문이다 (없던 것을 볼 수 있게 됐다)",
      RP.question_key(dict(_QK, Neighbours="4:1x1")) != RP.question_key(_QK))
check("창이 넓어진 것만으로는 새 질문이 아니다 (같은 것을 이미 볼 수 있었다)",
      RP.question_key(dict(_QK, Neighbours="4:1x1"))
      == RP.question_key(dict(_QK, Neighbours="3:1x1;4:1x1;5:1x1")))
check("답 자체는 열쇠에 들어가지 않는다 (질문이지 답이 아니다)",
      RP.question_key(dict(_QK, Human_Choice="BLOCKED", Human_Box="1,1,9,9"))
      == RP.question_key(_QK))

# 끝에서 끝까지: 답하면 큐에서 빠지고, 질문이 달라지면 돌아온다
_BR4 = os.path.join(RUN3, RP.BLOCK_REASONS)
with io.open(_BR4, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    for did in _ids3:
        w.writerow({"Draft_ID": did, "Count_Blocked": "1", "Reason": "그대로인 이유",
                    "Box_Would_Open": "1"})
_first = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("답하기 전에는 모두 묻는다", len(_first) == len(_ids3), len(_first))
_ans = os.path.join(TMP, "answered_once.csv")
_rows_a = [dict(r, Human_Choice="BLOCKED") for r in _first.values()]
with io.open(_ans, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows([{c: r.get(c, "") for c in RP.FIELDS} for r in _rows_a])
RP.merge(RUN3, _ans)
_after = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("답한 뒤에는 같은 질문을 다시 묻지 않는다", _after == {}, list(_after))
_saved = {r["Draft_ID"]: r for r in csv.DictReader(io.open(_reg3, encoding="utf-8"))}
check("무엇을 답했는지가 아니라 무엇을 물었는지가 적힌다",
      all((_saved[d].get(RP.ANSWERED_KEY) or "").strip() for d in _first), 
      {d: _saved[d].get(RP.ANSWERED_KEY) for d in list(_first)[:2]})
# 이유가 바뀌면 새 질문입니다.
with io.open(_BR4, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["Draft_ID", "Count_Blocked", "Reason",
                                       "Box_Would_Open"])
    w.writeheader()
    for i, did in enumerate(_ids3):
        w.writerow({"Draft_ID": did, "Count_Blocked": "1",
                    "Reason": "새 이유" if i == 0 else "그대로인 이유",
                    "Box_Would_Open": "1"})
_back = {r["Draft_ID"]: r for r in RP.blocked(RUN3)}
check("막힌 이유가 달라진 행만 돌아온다", set(_back) == {_ids3[0]}, list(_back))
check("돌아온 행에는 왜 다시 묻는지 적힌다",
      _back[_ids3[0]]["Block_Reason"].startswith("다시 묻습니다"),
      _back[_ids3[0]]["Block_Reason"][:40])
check("그 뒤에도 원래 이유가 그대로 남는다",
      "새 이유" in _back[_ids3[0]]["Block_Reason"])
# 다시 답하면 다시 조용해집니다 - 돌아온 행이 영영 돌아오지는 않습니다.
_ans2 = os.path.join(TMP, "answered_twice.csv")
with io.open(_ans2, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(RP.FIELDS))
    w.writeheader()
    w.writerows([{c: dict(_back[_ids3[0]], Human_Choice="BLOCKED").get(c, "")
                  for c in RP.FIELDS}])
RP.merge(RUN3, _ans2)
check("다시 답하면 다시 빠진다", RP.blocked(RUN3) == [],
      [r["Draft_ID"] for r in RP.blocked(RUN3)])
# 두 번째로 답할 때 그 행의 이유에는 "다시 묻습니다"가 붙어 있습니다. 그것까지
# 질문의 일부로 세면, 답할 때마다 이유가 길어지며 영영 돌아옵니다.
check("다시 묻는다는 머리말은 질문의 일부가 아니다",
      RP.question_key(dict(_QK, Block_Reason=RP.ASK_AGAIN + "이유"))
      == RP.question_key(_QK))
check("머리말이 여러 번 붙어도 마찬가지다",
      RP.question_key(dict(_QK, Block_Reason=RP.ASK_AGAIN * 3 + "이유"))
      == RP.question_key(_QK))

# ------------------------------- 막은 것을 되돌릴 수 있어야 한다
# 2026-09-02에 막힌 10행은 되돌릴 길이 없었습니다. 마음이 바뀌어도 그 행은
# 큐에 다시 오지 않고, 아무도 다시 묻지 않습니다.
_blk = D2[3] if len(D2) > 3 else D2[0]
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _blk["Draft_ID"]:
        r["Agreement"] = "DISAGREE"
        r["Human_Choice"] = "BLOCKED"
        r["Human_Box"] = ""
_write_reg2(_rows2)
AV.main(RUN2)
_blk_after = {r["Draft_ID"]: r for r in _reg2_rows()}[_blk["Draft_ID"]]
check("막으면 막히고", _blk_after["Agreement"] == "HUMAN_BLOCKED")
check("막기 전 상태를 적어 둔다 (되돌릴 수 있게)",
      _blk_after.get(RP.BLOCKED_FROM) == "DISAGREE", _blk_after.get(RP.BLOCKED_FROM))
check("막힌 행은 큐에 없다",
      not any(r["Draft_ID"] == _blk["Draft_ID"] for r in RP.queue(RUN2)))
RP.reopen(RUN2, [_blk["Draft_ID"]])
_reop = {r["Draft_ID"]: r for r in _reg2_rows()}[_blk["Draft_ID"]]
check("되돌리면 막기 전 상태로 돌아간다", _reop["Agreement"] == "DISAGREE",
      _reop["Agreement"])
check("되돌리면 그 답이 지워진다", (_reop.get("Human_Choice") or "") == "")
check("되돌린 행은 큐로 돌아온다",
      any(r["Draft_ID"] == _blk["Draft_ID"] for r in RP.queue(RUN2)))
check("되돌린 것만으로 세어지지는 않는다", _reop["Agreement"] not in RP.COUNTABLE)
# 큐에 다시 오게 하는 것은 합의가 아니라 "그 사람의 답이 지워졌다"는 사실입니다.
# 합의만 보면, 답을 지워도 HUMAN_BLOCKED인 행은 영영 묻히지 않습니다.
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _blk["Draft_ID"]:
        r["Agreement"] = "HUMAN_BLOCKED"
        r["Human_Choice"] = ""
_write_reg2(_rows2)
check("막힌 채여도 답이 비어 있으면 큐로 돌아온다",
      any(r["Draft_ID"] == _blk["Draft_ID"] for r in RP.queue(RUN2)),
      [r["Draft_ID"] for r in RP.queue(RUN2)])
# 큐가 그린 상자를 들고 오지 않으면, 판정 페이지는 사람이 이미 그린 상자를
# 모른 채 다시 그리라고 합니다.
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _blk["Draft_ID"]:
        r["Human_Box"] = "11.0,22.0,333.0,444.0"
_write_reg2(_rows2)
_q_box = [r for r in RP.queue(RUN2) if r["Draft_ID"] == _blk["Draft_ID"]]
check("큐가 전에 그린 상자를 들고 온다",
      _q_box and _q_box[0].get(RP.HUMAN_BOX) == "11.0,22.0,333.0,444.0",
      _q_box[0].get(RP.HUMAN_BOX) if _q_box else "없음")
# 되돌리기가 셀 수 있는 상태를 되살리면, 아무도 보지 않은 행이 세어집니다.
_rows2 = _reg2_rows()
for r in _rows2:
    if r["Draft_ID"] == _blk["Draft_ID"]:
        r["Agreement"] = "HUMAN_BLOCKED"
        r["Human_Choice"] = "BLOCKED"
        r[RP.BLOCKED_FROM] = "AGREE_3"
_write_reg2(_rows2)
RP.reopen(RUN2, [_blk["Draft_ID"]])
_reop2 = {r["Draft_ID"]: r for r in _reg2_rows()}[_blk["Draft_ID"]]
check("막기 전이 셀 수 있는 상태였으면 되돌리지 않는다",
      _reop2["Agreement"] == "HUMAN_BLOCKED", _reop2["Agreement"])
check("막히지 않은 행에 되돌리기를 걸어도 아무 일도 없다",
      RP.reopen(RUN2, [_d2["Draft_ID"]]) == 0
      and {r["Draft_ID"]: r for r in _reg2_rows()}[_d2["Draft_ID"]]["Agreement"]
          == "HUMAN_VALIDATED")

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
# 큐는 앞선 시나리오들이 답한 만큼 줄어 있으므로, 지금 큐의 행 수로 셉니다.
_queue_now = list(csv.DictReader(io.open(QPATH, encoding="utf-8")))
check("예산이 작으면 행마다 파일이 하나씩 나뉜다 (%d행)" % len(_queue_now),
      len(_sparts) == len(_queue_now), (len(_sparts), len(_queue_now)))
_ok_rows = _ok_queue = True
for _i, _p in enumerate(_sparts):
    _t = io.open(_p, encoding="utf-8").read()
    _cards_here = re.findall(r"<section class='card' data-id='([^']+)'", _t)
    _rows_here = re.search(r"const ROWS = (\[.*?\]), COLUMNS", _t, re.S).group(1)
    _queue_here = re.search(r"QUEUE = (\{.*?\}), BUILD", _t, re.S).group(1)
    _ids_in_rows = re.findall(r'"Draft_ID": "([^"]+)"', _rows_here)
    if _ids_in_rows != _cards_here:
        _ok_rows = False
    for _q in _queue_now:
        if (_q["Draft_ID"] in _queue_here) != (_q["Draft_ID"] in _cards_here):
            _ok_queue = False
check("파일의 내보내기 목록이 그 파일의 카드와 정확히 같다", _ok_rows)
check("파일에 없는 행의 데이터는 실리지 않는다", _ok_queue)
del _queue_now
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
