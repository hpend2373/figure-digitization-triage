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


def row(did, status="ENTERED", value="4", build=BUILD):
    return {"Draft_ID": did, "Source_Document_ID": "DOC", "Source_File": "f.pdf",
            "Page": "3", "Figure_Number": "FIG1",
            "Crop_Quality_Status": "ACCEPTABLE", "Row_Fingerprint": "fp" + did,
            "Observed_Panel_Count": value, "Entry_Status": status,
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

shutil.rmtree(TMP, ignore_errors=True)
print()
print("FDT_SCENARIOS_RUN=%d" % N[0])
print("%d scenarios run" % N[0])
if FAIL:
    print("%d FAILED: %s" % (len(FAIL), FAIL))
    raise SystemExit(1)
print("all scenarios passed")
