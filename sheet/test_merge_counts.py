# -*- coding: utf-8 -*-
"""The merge, and every way a pile of exported CSVs can be wrong.

Splitting the sheet into files created this step, so this is where the ways
the split can go wrong have to be caught: a sheet nobody downloaded, a row
that turns up twice, exports from two different builds.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge_counts as M

N, FAIL = [0], []


def check(name, ok, detail=""):
    N[0] += 1
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name,
                         "" if ok else "  <- %s" % detail))
    if not ok:
        FAIL.append(name)


BUILD = "sheet-2026-09-01-abcdef12"


def row(did, status="ENTERED", value="4", build=BUILD, why="", objection=""):
    return {"Draft_ID": did, "Source_Document_ID": "DOC", "Source_File": "f.pdf",
            "Page": "3", "Figure_Number": "FIG1",
            "Crop_Quality_Status": "ACCEPTABLE", "Row_Fingerprint": "fp" + did,
            "Observed_Panel_Count": value, "Entry_Status": status,
            "Uncountable_Reason": why, "Objection_Reason": objection,
            "Sheet_Build_ID": build}


DRAFT = [{"Draft_ID": "A"}, {"Draft_ID": "B"}, {"Draft_ID": "C"}]


def codes(parts, draft=None):
    return [c for c, _d in M.merge(draft or DRAFT, parts)[1]]


_ok = [("p1.csv", [row("A"), row("B", "BLOCKED_BAD_CROP", "")]),
       ("p2.csv", [row("C", "NOT_REVIEWED", "")])]
_merged, _problems = M.merge(DRAFT, _ok)
check("빠짐도 겹침도 없으면 합쳐진다", _problems == [], "%s" % _problems)
check("합친 결과는 초안의 순서를 따른다",
      [r["Draft_ID"] for r in _merged] == ["A", "B", "C"])

check("한 시트를 안 내려받으면 그 행들이 이름으로 불린다",
      codes([_ok[0]]) == ["ROW_MISSING"])
check("같은 행이 두 파일에 있으면 거부한다",
      "ROW_IN_TWO_FILES" in codes([_ok[0], ("p2.csv", [row("A")]), _ok[1]]))
check("초안에 없는 행은 거부한다",
      "ROW_UNKNOWN" in codes([("p1.csv", [row("A"), row("Z")]), _ok[1]]))
check("빌드가 섞이면 거부한다 - 같은 이름이 다른 그림일 수 있다",
      "BUILD_MIXED" in codes([("p1.csv", [row("A"), row("B")]),
                              ("p2.csv", [row("C", build="sheet-other")])]))

check("정수가 아닌 입력값은 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A", value="네"), row("B"),
                                            row("C")])]))
check("한도를 넘는 값은 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A", value="41"), row("B"),
                                            row("C")])]))
check("막힌 행이 숫자를 달고 있으면 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A"),
                                            row("B", "BLOCKED_BAD_CROP", "2"),
                                            row("C", "NOT_REVIEWED", "")])]))
check("아직 안 본 행이 숫자를 달고 있으면 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A"), row("B"),
                                            row("C", "NOT_REVIEWED", "3")])]))
check("알 수 없는 상태는 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A", "DONE"), row("B"),
                                            row("C")])]))
check("0은 유효한 입력이다 - 빈칸과 다르다",
      M.merge(DRAFT, [("p1.csv", [row("A", value="0"), row("B"),
                                  row("C")])])[1] == [])

# ------------------------------- 봤지만 셀 수 없음: 이유가 있어야 한다
check("이유가 붙은 '셀 수 없음'은 통과한다",
      M.merge(DRAFT, [("p1.csv", [row("A", "SEEN_UNCOUNTABLE", "", why="인셋"),
                                  row("B"), row("C")])])[1] == [])
check("이유 없는 '셀 수 없음'은 거부한다 - 안 본 것과 같아진다",
      "REASON_MISSING" in codes([("p1.csv", [row("A", "SEEN_UNCOUNTABLE", ""),
                                             row("B"), row("C")])]))
check("'셀 수 없음'이 숫자를 달고 있으면 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A", "SEEN_UNCOUNTABLE", "3",
                                                why="인셋"),
                                            row("B"), row("C")])]))
check("숫자를 넣은 행이 이유를 달고 있으면 거부한다",
      "VALUE_INVALID" in codes([("p1.csv", [row("A", why="옛 이유"), row("B"),
                                            row("C")])]))

# ------------------------------------------------------- 명령줄 전체
TMP = tempfile.mkdtemp(prefix="fdt-merge-")


def dump(name, rows, cols):
    p = os.path.join(TMP, name)
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


_d = dump("draft.csv", DRAFT, ["Draft_ID"])
_p1 = dump("p1.csv", [row("A"), row("B", "BLOCKED_BAD_CROP", "")], M.COLUMNS)
_p2 = dump("p2.csv", [row("C", "NOT_REVIEWED", "")], M.COLUMNS)
_out = os.path.join(TMP, "merged.csv")
_rc = os.path.join(TMP, "receipt.json")
_code = M.main(["--draft", _d, "--out", _out, "--receipt", _rc, _p1, _p2])
check("정상 합치기는 0으로 끝난다", _code == 0)
check("합친 파일이 초안 행수만큼 있다",
      len(list(csv.DictReader(io.open(_out, encoding="utf-8-sig")))) == 3)
check("영수증이 상태별 수를 남긴다",
      json.load(io.open(_rc, encoding="utf-8"))["by_status"]
      == {"ENTERED": 1, "BLOCKED_BAD_CROP": 1, "NOT_REVIEWED": 1})

os.remove(_out)
_code = M.main(["--draft", _d, "--out", _out, "--receipt", _rc, _p1])
check("빠진 시트가 있으면 0이 아닌 코드로 끝난다", _code == 1)
check("거부하면 합친 파일을 쓰지 않는다", not os.path.exists(_out))
check("거부도 영수증에 남는다",
      json.load(io.open(_rc, encoding="utf-8"))["verdict"] == "REFUSED")

# --- 시트가 그 행에 대해 틀렸다는 답 ------------------------------------------
# 계수가 아니라 이 시트에 대한 이의입니다. 값을 달지 않고, 이유는 반드시 답니다 -
# 이유 없는 이의는 잘못 누른 것과 구별되지 않고, 잘못 누른 것이 이의로 보이면
# 없느니만 못합니다.
_disp = [("p1.csv", [row("A", "CROP_DISPUTED", "", objection="본문 문단이 보임"),
                     row("B", "BLOCK_DISPUTED", "", objection="그림이 멀쩡히 보임"),
                     row("C", "NOT_REVIEWED", "")])]
check("이유가 붙은 이의는 통과한다", codes(_disp) == [], codes(_disp))
# REVERT: 확인을 이의와 같은 무리에 넣는다. 그러면 이유를 요구하게 되고,
# 카드에 이미 인쇄된 사유에 동의하는 데까지 글을 쓰라고 하면 아무도
# 확인하지 않습니다. 확인은 답이지만 이의는 아닙니다.
_ok = [("p1.csv", [row("A", "BLOCK_CONFIRMED", ""),
                   row("B"), row("C")])]
check("이유 없는 차단 확인은 통과한다", codes(_ok) == [], codes(_ok))
check("확인은 사람이 답한 것으로 친다",
      M.is_answer({"Entry_Status": "BLOCK_CONFIRMED"})
      and not M.is_answer({"Entry_Status": "BLOCKED_BAD_CROP"}))
_okvalued = [("p1.csv", [row("A", "BLOCK_CONFIRMED", "3"),
                         row("B"), row("C")])]
check("확인하면서 값까지 달면 거부한다",
      "VALUE_INVALID" in codes(_okvalued), codes(_okvalued))
_noreason = [("p1.csv", [row("A", "CROP_DISPUTED", ""), row("B"), row("C")])]
check("이유 없는 이의는 거부한다",
      codes(_noreason) == ["OBJECTION_REASON_MISSING"], codes(_noreason))
_valued = [("p1.csv", [row("A", "CROP_DISPUTED", "3", objection="본문"),
                       row("B"), row("C")])]
check("이의를 달면서 값까지 달면 거부한다",
      "VALUE_INVALID" in codes(_valued), codes(_valued))
_stray = [("p1.csv", [row("A", "ENTERED", "3", objection="옛 이유"),
                      row("B"), row("C")])]
check("이의 상태가 아닌데 이의 이유가 붙어 있으면 거부한다",
      "VALUE_INVALID" in codes(_stray), codes(_stray))
_both = [("p1.csv", [row("A", "CROP_DISPUTED", "", why="거침", objection="본문"),
                     row("B"), row("C")])]
check("셀 수 없음 이유와 이의 이유가 같이 붙으면 거부한다",
      "VALUE_INVALID" in codes(_both), codes(_both))
check("이의 두 상태는 merge가 아는 상태다",
      set(M.DISPUTED) <= set(M.STATUSES) and len(M.DISPUTED) == 2)
check("내보내기 열에 이의 칸이 있다", "Objection_Reason" in M.COLUMNS)


# --- 한 번에 다 세지 않는다 --------------------------------------------------
# 시트가 열두 장이면 사람은 세 장을 세고, 며칠 뒤 네 장을 더 셉니다. 그때마다
# 나머지를 ROW_MISSING으로 거부하면 다 세기 전에는 아무것도 기록할 수 없습니다.
_three = [("p1.csv", [row("A")])]
check("다 세지 않았는데 말하지 않으면 예전처럼 거부한다",
      codes(_three) == ["ROW_MISSING", "ROW_MISSING"], codes(_three))
check("--partial이라고 밝히면 남은 행을 거부하지 않는다",
      [c for c, _d in M.merge(DRAFT, _three, partial=True)[1]] == [],
      [c for c, _d in M.merge(DRAFT, _three, partial=True)[1]])
_m, _p = M.merge(DRAFT, _three, partial=True)
check("  그리고 센 행만 합쳐진다",
      [r["Draft_ID"] for r in _m] == ["A"], [r["Draft_ID"] for r in _m])
# REVERT: drop the carried rows. 두 번째 합치기가 첫 번째를 지웁니다 - 세 시트를
# 센 사람이 네 시트를 더 세면 앞의 세 장이 없어집니다.
_carry = [row("A", "ENTERED", "9")]
_later = [("p2.csv", [row("B")])]
_m2, _p2 = M.merge(DRAFT, _later, carry=_carry, partial=True)
check("앞서 합쳐 둔 행은 그대로 남는다",
      sorted(r["Draft_ID"] for r in _m2) == ["A", "B"],
      [r["Draft_ID"] for r in _m2])
check("  남은 행의 값도 그대로다",
      [r["Observed_Panel_Count"] for r in _m2 if r["Draft_ID"] == "A"] == ["9"])
check("  들고 온 행은 ROW_MISSING이 아니다",
      [c for c, _d in M.merge(DRAFT, [("p2.csv", [row("B"), row("C")])],
                              carry=_carry)[1]] == [],
      [c for c, _d in M.merge(DRAFT, [("p2.csv", [row("B"), row("C")])],
                              carry=_carry)[1]])
# REVERT: let the carried row win. 다시 센 값이 옛 값에 덮이고, 사람이 고친
# 답이 조용히 사라집니다.
_again = [("p2.csv", [row("A", "ENTERED", "2")])]
_m3, _p3 = M.merge(DRAFT, _again, carry=_carry, partial=True)
check("다시 센 행은 새 값이 이긴다",
      [r["Observed_Panel_Count"] for r in _m3 if r["Draft_ID"] == "A"] == ["2"],
      [r["Observed_Panel_Count"] for r in _m3])
# REVERT: let the new export win whatever it says. 사람의 답 열셋이 실제로
# 이렇게 지워졌습니다 - 시트는 이미 답한 행을 막아서 보여 주므로 그 행이 다음
# 내보내기에 BLOCKED_BAD_CROP으로 값 없이 다시 나오고, 그것이 답을 덮습니다.
_blocked_again = [("p2.csv", [row("A", "BLOCKED_BAD_CROP", "")])]
_m4, _p4 = M.merge(DRAFT, _blocked_again, carry=_carry, partial=True)
check("답이 아닌 것은 답을 지우지 못한다",
      [(r["Entry_Status"], r["Observed_Panel_Count"]) for r in _m4
       if r["Draft_ID"] == "A"] == [("ENTERED", "9")],
      [(r["Entry_Status"], r["Observed_Panel_Count"]) for r in _m4])
_unread = [("p2.csv", [row("A", "NOT_REVIEWED", "")])]
check("  아직 안 본 것도 답을 지우지 못한다",
      [r["Observed_Panel_Count"] for r in
       M.merge(DRAFT, _unread, carry=_carry, partial=True)[0]
       if r["Draft_ID"] == "A"] == ["9"])
check("  그러나 다른 답은 답을 덮는다",
      [r["Observed_Panel_Count"] for r in
       M.merge(DRAFT, [("p2.csv", [row("A", "ENTERED", "2")])],
               carry=_carry, partial=True)[0]
       if r["Draft_ID"] == "A"] == ["2"])
check("  셀 수 없음도 답이므로 값을 덮는다",
      [r["Entry_Status"] for r in
       M.merge(DRAFT, [("p2.csv", [row("A", "SEEN_UNCOUNTABLE", "", why="거침")])],
               carry=_carry, partial=True)[0]
       if r["Draft_ID"] == "A"] == ["SEEN_UNCOUNTABLE"])
check("답이 아닌 기록끼리는 새것이 이긴다",
      [r["Entry_Status"] for r in
       M.merge(DRAFT, [("p2.csv", [row("A", "BLOCKED_BAD_CROP", "")])],
               carry=[row("A", "NOT_REVIEWED", "")], partial=True)[0]
       if r["Draft_ID"] == "A"] == ["BLOCKED_BAD_CROP"])
check("초안에 없는 행은 들고 오지 않는다",
      [r["Draft_ID"] for r in M.merge(DRAFT, _later,
                                      carry=[row("Z")], partial=True)[0]] == ["B"])


shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
