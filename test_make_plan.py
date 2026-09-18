# -*- coding: utf-8 -*-
"""Scenarios for make_plan.py - what a plan may say, and what it must not.

    python3 test_make_plan.py

The module writes ninety-eight plans nobody will read line by line, so the
scenarios are about the two ways that goes wrong: a plan that claims something
no program can know (a panel count, a person's inspection), and a plan that
stays silent about what it is missing. Both come out compiling.

No PDF is opened here - a plan is written from the intake's own CSVs, so the
fixtures are those CSVs.
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
import batch_manifests as BM                                     # noqa: E402
import compile_plan as CP                                        # noqa: E402
import make_plan as MP                                           # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else "  <- %s" % (detail,)))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


ROOT = tempfile.mkdtemp(prefix="fdt_makeplan_")
RUN = os.path.join(ROOT, "run")
OUT = os.path.join(ROOT, "plans")
os.makedirs(os.path.join(RUN, "crops"))

RUN_DATE = "2026-08-30"
BAR_LINE = "Figure 1. Heart rate during tilt."
BAR = BAR_LINE + " Values are means and standard deviations."
LINE = "Figure 2. Stroke volume during tilt."
SCHEMATIC = "Figure 3. Schematic of the tilt table protocol."
SCATTER = "Figure 4. Relationship between stroke volume and heart rate."
EVENT = "Figure 5. Incidence of presyncope in each arm."


def write(name, fields, rows):
    with io.open(os.path.join(RUN, name), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            w.writerow(dict((k, row.get(k, "")) for k in fields))


def draft_row(did, doc, fig, page, caption, crop="", blocked="", dup=""):
    return {"Draft_ID": did, "Source_Document_ID": doc, "Source_File": doc + ".pdf",
            "Source_File_SHA256": "0" * 64, "Page": page, "Figure_Number": fig,
            "Caption_Text": caption, "Figure_Crop": crop,
            "Extraction_Method": "PDFMINER_TEXT_BLOCKS",
            "_blocked": blocked, "_dup": dup}


DRAFT_FIELDS = ("Draft_ID", "Source_Document_ID", "Source_File",
                "Source_File_SHA256", "Page", "Figure_Number", "Caption_Text",
                "Figure_Crop", "Extraction_Method")
ROWS = [
    draft_row("PUB_D001", "PUB", "FIG1", "2", BAR_LINE, "crops/1.png"),
    draft_row("PUB_D002", "PUB", "FIG2", "3", LINE, "crops/2.png"),
    draft_row("PUB_D003", "PUB", "FIG3", "4", SCHEMATIC, "crops/3.png"),
    draft_row("PUB_D004", "PUB", "FIG4", "5", SCATTER, "crops/4.png"),
    draft_row("PUB_D005", "PUB", "FIG5", "6", EVENT, "crops/5.png"),
    draft_row("PUB_D006", "PUB", "FIG6", "7", LINE, "crops/6.png", blocked="1"),
    draft_row("PUB_D007", "PUB", "FIG2", "8", LINE, "crops/2.png", dup="PUB_D002"),
    draft_row("PUB_D008", "PUB", "FIG7", "9", LINE, "crops/gone.png"),
]
for i in range(1, 7):
    open(os.path.join(RUN, "crops", "%d.png" % i), "wb").write(b"\x89PNG\r\n")
write(MP.DRAFT, DRAFT_FIELDS, ROWS)
write(MP.BLOCKS, ("Draft_ID", "Count_Blocked", "Duplicate_Of"),
      [{"Draft_ID": r["Draft_ID"], "Count_Blocked": r["_blocked"],
        "Duplicate_Of": r["_dup"]} for r in ROWS])
CAPTION_FIELDS = ("Draft_ID", "Page", "Caption_Full", "Errorbar_Definition",
                  "Errorbar_Evidence", "Doc_Errorbar_Definition",
                  "Doc_Errorbar_Evidence", "Doc_Errorbar_Page")
DOC_SENTENCE = "All values are given as means with 95% confidence intervals."
write(MP.CAPTIONS, CAPTION_FIELDS, [
    # 캡션이 스스로 말하는 그림.
    {"Draft_ID": "PUB_D001", "Page": "2", "Caption_Full": BAR,
     "Errorbar_Definition": "SD", "Errorbar_Evidence": "means and standard dev",
     "Doc_Errorbar_Definition": "CI", "Doc_Errorbar_Evidence": DOC_SENTENCE,
     "Doc_Errorbar_Page": "1"},
    # 캡션은 말하지 않고 문서가 말하는 그림.
    {"Draft_ID": "PUB_D002", "Page": "3", "Caption_Full": LINE,
     "Errorbar_Definition": "UNSTATED", "Doc_Errorbar_Definition": "CI",
     "Doc_Errorbar_Evidence": DOC_SENTENCE, "Doc_Errorbar_Page": "1"},
    {"Draft_ID": "PUB_D003", "Page": "4", "Caption_Full": SCHEMATIC,
     "Errorbar_Definition": "UNSTATED"},
    {"Draft_ID": "PUB_D004", "Page": "5", "Caption_Full": SCATTER,
     "Errorbar_Definition": "UNSTATED"},
    {"Draft_ID": "PUB_D005", "Page": "6", "Caption_Full": EVENT,
     "Errorbar_Definition": "UNSTATED"},
    # 문서가 두 가지를 말하는 그림. AMBIGUOUS는 계획서의 값이 아닙니다.
    {"Draft_ID": "PUB_D008", "Page": "9", "Caption_Full": LINE,
     "Errorbar_Definition": "UNSTATED", "Doc_Errorbar_Definition": "AMBIGUOUS",
     "Doc_Errorbar_Evidence": "SD ... SEM", "Doc_Errorbar_Page": "1"},
])
write(MP.DECISIONS, ("Draft_ID", "Dispersion_Type",
                     "Errorbar_Definition_Source", "Found_On_Page"), [])
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status"), [])


def build(**kw):
    shutil.rmtree(OUT, ignore_errors=True)
    MP.build(RUN, OUT, RUN, RUN_DATE, log=lambda *_a: None, **kw)
    path = os.path.join(OUT, "plan_PUB.json")
    plan = json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else None
    sheet = list(csv.DictReader(
        io.open(os.path.join(OUT, MP.WORKSHEET), encoding="utf-8")))
    ready = list(csv.DictReader(
        io.open(os.path.join(OUT, MP.READINESS), encoding="utf-8")))
    return plan, dict((r["Source_Figure_ID"], r) for r in sheet), ready


PLAN, SHEET, READY = build()
FIG = dict((f["source_figure_id"], f) for f in PLAN["figures"])


# --- 무엇이 계획서에 들어오는가 ------------------------------------------------
check("블록된 행은 계획서의 그림이 되지 않는다", "PUB_D006" not in FIG, sorted(FIG))
check("중복으로 표시된 행은 계획서의 그림이 되지 않는다", "PUB_D007" not in FIG)
check("남은 행은 모두 그림이 된다",
      sorted(FIG) == ["PUB_D001", "PUB_D002", "PUB_D003", "PUB_D004",
                      "PUB_D005", "PUB_D008"], sorted(FIG))
check("schema는 compile_plan의 것이다", PLAN["schema"] == CP.PLAN_SCHEMA)
check("계획서가 모르는 열쇠는 쓰지 않는다",
      [p for p in CP.validate_plan(PLAN, file_root=RUN)
       if p["check"].startswith("PLAN_UNKNOWN")] == [],
      [p for p in CP.validate_plan(PLAN, file_root=RUN) if "UNKNOWN" in p["check"]])

# --- 캡션이 정하는 처분 --------------------------------------------------------
check("데이터 그림은 기하가 아직 쓰이지 않은 것으로 둔다",
      SHEET["PUB_D001"]["Disposition"] == "GEOMETRY_NOT_AUTHORED",
      SHEET["PUB_D001"]["Disposition"])
check("모식도는 NOT_DATA로 간다",
      SHEET["PUB_D003"]["Disposition"] == "NOT_DATA", SHEET["PUB_D003"]["Disposition"])
check("상관 그림은 연관 추출로 간다",
      SHEET["PUB_D004"]["Disposition"] == "ASSOCIATION_EXTRACT",
      SHEET["PUB_D004"]["Disposition"])
check("사건 발생 그림은 이항 추출로 간다",
      SHEET["PUB_D005"]["Disposition"] == "BINARY_EXTRACT",
      SHEET["PUB_D005"]["Disposition"])

# --- 오차 정의가 어디서 오는가 -------------------------------------------------
check("캡션이 말하면 캡션의 종류를 쓴다",
      SHEET["PUB_D001"]["Dispersion_Type"] == "SD", SHEET["PUB_D001"]["Dispersion_Type"])
check("캡션이 말하면 문서 진술보다 캡션이 앞선다",
      SHEET["PUB_D001"]["Errorbar_Source_Kind"] == MP.FROM_CAPTION)
check("캡션이 말하지 않으면 문서 진술을 쓴다",
      (SHEET["PUB_D002"]["Dispersion_Type"],
       SHEET["PUB_D002"]["Errorbar_Source_Kind"]) == ("CI95", MP.FROM_DOCUMENT),
      SHEET["PUB_D002"]["Dispersion_Type"])
check("CI는 계획서의 이름인 CI95로 적힌다",
      "CI95" in [r["Dispersion_Type"] for r in SHEET.values()]
      and "CI" not in [r["Dispersion_Type"] for r in SHEET.values()])
check("논문의 말은 규칙이 맞춘 토막이 아니라 문장으로 적힌다",
      SHEET["PUB_D002"]["Errorbar_Definition_Source"] == DOC_SENTENCE,
      SHEET["PUB_D002"]["Errorbar_Definition_Source"])
check("캡션이 말할 때도 적히는 것은 캡션 전문이지 맞춘 토막이 아니다",
      SHEET["PUB_D001"]["Errorbar_Definition_Source"] == BAR,
      SHEET["PUB_D001"]["Errorbar_Definition_Source"])
check("모르는 경로는 추출 대상이 아니다",
      MP.disposition_for("A_ROUTE_THIS_MODULE_DOES_NOT_KNOW") == "UNRESOLVED",
      MP.disposition_for("A_ROUTE_THIS_MODULE_DOES_NOT_KNOW"))
check("두 가지를 말하는 문서는 종류를 정해 주지 않는다",
      SHEET["PUB_D008"]["Dispersion_Type"] == "", SHEET["PUB_D008"]["Dispersion_Type"])
check("종류가 없는 데이터 그림은 오차 정의를 할 일로 남긴다",
      "오차 정의" in SHEET["PUB_D008"]["Needs"], SHEET["PUB_D008"]["Needs"])
check("종류가 있는 그림에는 오차 정의를 할 일로 남기지 않는다",
      "오차 정의" not in SHEET["PUB_D001"]["Needs"], SHEET["PUB_D001"]["Needs"])

# --- 사람의 판정이 이긴다 ------------------------------------------------------
write(MP.DECISIONS, ("Draft_ID", "Dispersion_Type",
                     "Errorbar_Definition_Source", "Found_On_Page"),
      [{"Draft_ID": "PUB_D001", "Dispersion_Type": "SEM",
        "Errorbar_Definition_Source": "Bars are standard errors of the mean.",
        "Found_On_Page": "2"},
       {"Draft_ID": "PUB_D002", "Dispersion_Type": "DROP"}])
_plan, _sheet, _ready = build()
# REVERT: ask the caption again. The one thing a person added by opening the
# paper is overwritten by the rule that failed to see it in the first place.
check("사람의 판정은 캡션 규칙을 이긴다",
      (_sheet["PUB_D001"]["Dispersion_Type"],
       _sheet["PUB_D001"]["Errorbar_Source_Kind"]) == ("SEM", MP.FROM_DECISION),
      _sheet["PUB_D001"]["Dispersion_Type"])
check("풀에서 뺀 행은 기하를 쓸 일로 남기지 않는다",
      _sheet["PUB_D002"]["Disposition"] == "UNRESOLVED",
      _sheet["PUB_D002"]["Disposition"])
check("풀에서 뺀 행은 셈에서도 빠진다", _ready[0]["Dropped"] == "1", _ready[0]["Dropped"])
write(MP.DECISIONS, ("Draft_ID", "Dispersion_Type",
                     "Errorbar_Definition_Source", "Found_On_Page"), [])

# --- 셀 수 없는 하나의 수 ------------------------------------------------------
check("패널 계수가 없으면 그 수를 적지 않는다",
      all("observed_panel_count" not in f for f in PLAN["figures"]),
      [f.get("observed_panel_count") for f in PLAN["figures"]])
check("패널 계수가 없으면 패널도 세우지 않는다",
      all(f["panels"] == [] for f in PLAN["figures"]))
_problems = CP.validate_plan(PLAN, file_root=RUN)
check("그래서 계획서는 그 수가 없다고 이름을 대며 멎는다",
      len([p for p in _problems if p["check"] == "PLAN_PANEL_COUNT_MISSING"])
      == len(PLAN["figures"]),
      [p["check"] for p in _problems])
check("멎게 하는 것은 사람이 대야 할 것들뿐이다",
      sorted(set(p["check"] for p in _problems))
      == ["PLAN_PANEL_COUNT_MISSING", "SOURCE_FILE_NOT_FOUND"],
      sorted(set(p["check"] for p in _problems)))
check("기하를 아직 아무도 쓰지 않았다는 것이 할 일에 적힌다",
      "패널 기하" in SHEET["PUB_D001"]["Needs"]
      and "패널 기하" not in SHEET["PUB_D003"]["Needs"],
      (SHEET["PUB_D001"]["Needs"], SHEET["PUB_D003"]["Needs"]))
check("계수가 필요하다는 것이 할 일에 적힌다",
      all("패널 계수" in r["Needs"] for r in SHEET.values()))

write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status",
                  "Uncountable_Reason", "Objection_Reason"),
      [{"Draft_ID": "PUB_D001", "Observed_Panel_Count": "3",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "PUB_D003", "Observed_Panel_Count": "1",
        "Entry_Status": "ENTERED"},
       # 축 영역이 없다고 사람이 센 행. 빈칸이 아니라 0입니다.
       {"Draft_ID": "PUB_D008", "Observed_Panel_Count": "0",
        "Entry_Status": "ENTERED"},
       # 보았지만 셀 수 없다고 적힌 행. 수가 아닙니다.
       {"Draft_ID": "PUB_D004", "Observed_Panel_Count": "2",
        "Entry_Status": "SEEN_UNCOUNTABLE",
        "Uncountable_Reason": "셀수없는그래프"},
       # 아직 안 본 행.
       {"Draft_ID": "PUB_D005", "Observed_Panel_Count": "",
        "Entry_Status": "NOT_REVIEWED"},
       # 크롭이 대상 그림이 아니라고 적힌 행. 이것도 답입니다.
       {"Draft_ID": "PUB_D002", "Observed_Panel_Count": "",
        "Entry_Status": "CROP_DISPUTED",
        "Objection_Reason": "개념그림"}])
_plan, _sheet, _ready = build()
_fig = dict((f["source_figure_id"], f) for f in _plan["figures"])
check("사람이 센 수는 그대로 적힌다", _fig["PUB_D001"]["observed_panel_count"] == 3)
# REVERT: 0으로 센 그림에도 기하를 할 일로 적는다. 읽을 자리가 없다고 사람이
# 센 그림에 대해 "읽을 자리를 쓰라"는 줄이 서고, 그 줄은 아무도 지울 수
# 없습니다 - 쓸 것이 없으니까요.
check("0은 빈칸이 아니라 세어진 수다",
      _fig["PUB_D008"]["observed_panel_count"] == 0
      and _fig["PUB_D008"]["panels"] == [])
check("0으로 센 그림에는 기하를 할 일로 적지 않는다",
      "패널 기하" not in _sheet["PUB_D008"]["Needs"],
      _sheet["PUB_D008"]["Needs"])
check("0으로 센 그림에는 오차 정의도 묻지 않는다",
      "오차 정의" not in _sheet["PUB_D008"]["Needs"],
      _sheet["PUB_D008"]["Needs"])
check("1개 이상으로 센 그림에는 여전히 기하를 묻는다",
      "패널 기하" in _sheet["PUB_D001"]["Needs"],
      _sheet["PUB_D001"]["Needs"])

# --- 다시 묻지 않는 것과 그림이 아닌 것 -----------------------------------------
# REVERT: 막힌 행은 답이 붙어 있어도 계획서에서 뺀다. 시트가 "이미 답하셨으니 또
# 묻지 않는다"고 막아 둔 행이 통째로 사라집니다 - run2에서 계수가 끝나자 계획서의
# 그림이 446개에서 1개로 줄었습니다. 다시 묻지 않는 것과 그림이 아닌 것은 다릅니다.
write(MP.BLOCKS, ("Draft_ID", "Count_Blocked", "Duplicate_Of"),
      [{"Draft_ID": "PUB_D006", "Count_Blocked": "1", "Duplicate_Of": ""},
       {"Draft_ID": "PUB_D007", "Count_Blocked": "1",
        "Duplicate_Of": "PUB_D002"}])
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status",
                  "Uncountable_Reason", "Objection_Reason"),
      [{"Draft_ID": "PUB_D006", "Observed_Panel_Count": "2",
        "Entry_Status": "ENTERED"}])
_p2, _s2, _r2 = build()
check("이미 답해서 막아 둔 행은 계획서의 그림으로 남는다",
      "PUB_D006" in dict((f["source_figure_id"], f) for f in _p2["figures"]),
      sorted(f["source_figure_id"] for f in _p2["figures"]))
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status",
                  "Uncountable_Reason", "Objection_Reason"),
      [{"Draft_ID": "PUB_D006", "Observed_Panel_Count": "",
        "Entry_Status": "BLOCK_CONFIRMED"}])
_p3, _s3, _r3 = build()
check("차단이 맞다고 확인한 행은 그대로 계획서 밖이다",
      "PUB_D006" not in dict((f["source_figure_id"], f) for f in _p3["figures"]),
      sorted(f["source_figure_id"] for f in _p3["figures"]))
check("중복으로 막힌 행은 답이 있어도 계획서 밖이다",
      "PUB_D007" not in dict((f["source_figure_id"], f) for f in _p2["figures"]))
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status",
                  "Uncountable_Reason", "Objection_Reason"),
      [{"Draft_ID": "PUB_D001", "Observed_Panel_Count": "3",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "PUB_D003", "Observed_Panel_Count": "1",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "PUB_D008", "Observed_Panel_Count": "0",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "PUB_D004", "Observed_Panel_Count": "2",
        "Entry_Status": "SEEN_UNCOUNTABLE",
        "Uncountable_Reason": "셀수없는그래프"},
       {"Draft_ID": "PUB_D005", "Observed_Panel_Count": "",
        "Entry_Status": "NOT_REVIEWED"},
       {"Draft_ID": "PUB_D002", "Observed_Panel_Count": "",
        "Entry_Status": "CROP_DISPUTED", "Objection_Reason": "개념그림"}])
write(MP.BLOCKS, ("Draft_ID", "Count_Blocked", "Duplicate_Of"),
      [{"Draft_ID": "PUB_D006", "Count_Blocked": "1", "Duplicate_Of": ""},
       {"Draft_ID": "PUB_D007", "Count_Blocked": "1",
        "Duplicate_Of": "PUB_D002"}])
_plan, _sheet, _ready = build()
_fig = dict((f["source_figure_id"], f) for f in _plan["figures"])
check("계수 파일의 이름은 시트 합치기가 쓰는 그 이름이다",
      MP.COUNTS == "observed_panel_counts.csv", MP.COUNTS)
# REVERT: take the number whatever the status says. "보았지만 셀 수 없다"와
# "아직 안 보았다"가 세어진 것이 되고, 그 그림은 사람 손을 떠납니다.
check("셀 수 없다고 적힌 행의 수는 가져오지 않는다",
      "observed_panel_count" not in _fig["PUB_D004"],
      _fig["PUB_D004"].get("observed_panel_count"))
check("아직 안 본 행도 가져오지 않는다",
      "observed_panel_count" not in _fig["PUB_D005"])

# --- 수가 아닌 답도 답이다 ------------------------------------------------------
# REVERT: 수가 없으면 무조건 "패널 계수"라고 적는다. 그러면 사람이 보고 답한
# 행과 아무도 보지 않은 행이 같은 줄로 나오고, 답한 사람은 자기 답이 사라진
# 것을 봅니다. 계획서를 읽는 쪽에서는 둘을 가를 방법이 없습니다.
check("셀 수 없다고 답한 행에는 세라고 적지 않는다",
      MP.COUNT_NEED not in _sheet["PUB_D004"]["Needs"],
      _sheet["PUB_D004"]["Needs"])
check("대상 그림이 아니라고 답한 행에도 세라고 적지 않는다",
      MP.COUNT_NEED not in _sheet["PUB_D002"]["Needs"],
      _sheet["PUB_D002"]["Needs"])
check("아직 아무도 보지 않은 행에는 여전히 세라고 적는다",
      MP.COUNT_NEED in _sheet["PUB_D005"]["Needs"],
      _sheet["PUB_D005"]["Needs"])
check("답한 행의 할 일은 사람이 다음에 무엇을 할지 이름을 댄다",
      "처분" in _sheet["PUB_D004"]["Needs"], _sheet["PUB_D004"]["Needs"])
check("사람이 뭐라 답했는지가 계획서에 실린다",
      "SEEN_UNCOUNTABLE" in _fig["PUB_D004"].get("note", ""),
      _fig["PUB_D004"].get("note"))
check("사람이 적은 까닭까지 함께 실린다",
      "셀수없는그래프" in _fig["PUB_D004"].get("note", ""),
      _fig["PUB_D004"].get("note"))
check("답을 실었다고 그것이 수가 되지는 않는다",
      "observed_panel_count" not in _fig["PUB_D004"]
      and _fig["PUB_D004"]["panels"] == [])
check("답을 실은 그림도 계획서가 받는 모양이다",
      not [p for p in CP.validate_plan(_plan, file_root=RUN)
           if p["check"] not in ("PLAN_PANEL_COUNT_MISSING",
                                 "SOURCE_FILE_NOT_FOUND")],
      [p["check"] for p in CP.validate_plan(_plan, file_root=RUN)])
check("아무도 답하지 않은 행에는 답이 실리지 않는다",
      "note" not in _fig["PUB_D005"], _fig["PUB_D005"].get("note"))
check("센 수만큼 패널이 선다", len(_fig["PUB_D001"]["panels"]) == 3,
      len(_fig["PUB_D001"]["panels"]))
check("패널 이름은 서로 다르다",
      len(set(p["panel_id"] for p in _fig["PUB_D001"]["panels"])) == 3)
check("패널 이름은 계획서가 받는 모양이다",
      all(BM.SAFE_ID.match(p["panel_id"]) for p in _fig["PUB_D001"]["panels"]))
_ids = [p["panel_id"] for f in _plan["figures"] for p in f["panels"]]
check("패널 이름은 그림이 달라도 서로 다르다",
      len(_ids) == len(set(_ids)) and len(_ids) == 4, _ids)
check("그래서 계획서가 같은 이름을 두 번 보지 않는다",
      not [p for p in CP.validate_plan(_plan, file_root=RUN)
           if p["check"] == "PLAN_DUPLICATE_ID"],
      [p for p in CP.validate_plan(_plan, file_root=RUN)
       if p["check"] == "PLAN_DUPLICATE_ID"])
check("처분은 계획서가 아는 어휘 안에 있다",
      set(p["disposition"] for f in _plan["figures"] for p in f["panels"])
      <= set(BM.SOURCE_PANEL_DISPOSITIONS)
      and set(p["disposition"] for f in _plan["figures"] for p in f["panels"]),
      set(p["disposition"] for f in _plan["figures"] for p in f["panels"]))
check("세어진 그림은 더 이상 계수를 할 일로 남기지 않는다",
      "패널 계수" not in _sheet["PUB_D001"]["Needs"], _sheet["PUB_D001"]["Needs"])
_left = CP.validate_plan(_plan, file_root=RUN)
check("세어진 그림은 계획서를 멎게 하지 않는다",
      not [p for p in _left if p["where"] == "figures[0]"],
      [p for p in _left if p["where"] == "figures[0]"])
check("세지 않은 그림은 여전히 멎게 한다",
      len([p for p in _left if p["check"] == "PLAN_PANEL_COUNT_MISSING"]) == 3,
      [p["where"] for p in _left])
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status"), [])

# --- 사람인 척하지 않는다 ------------------------------------------------------
_r = PLAN["reviewers"][0]
# REVERT: write a HUMAN record with HUMAN_CONFIRMED. Every figure in every plan
# then carries a person's word for something no person has looked at.
check("검토자는 사람이 아니라고 적힌다", _r["record_type"] == "DEMO_IDENTITY",
      _r["record_type"])
check("증언은 데모라고 적힌다", _r["human_attestation"] == "DEMO_EXAMPLE",
      _r["human_attestation"])
check("HUMAN_CONFIRMED는 계획서 어디에도 없다",
      "HUMAN_CONFIRMED" not in json.dumps(PLAN, ensure_ascii=False))
check("등록일은 --run-date가 준 날이지 오늘이 아니다",
      _r["registration_date"] == RUN_DATE
      and RUN_DATE != __import__("datetime").date.today().isoformat())
check("문서 목록은 아직 확인되지 않았다고 적힌다",
      all(d["inventory_status"] == "PENDING" for d in PLAN["documents"]))
check("그림 목록도 아직 확인되지 않았다고 적힌다",
      all(f["inventory_status"] == "PENDING" for f in PLAN["figures"]))
check("VISUALLY_VERIFIED는 계획서 어디에도 없다",
      "VISUALLY_VERIFIED" not in json.dumps(PLAN, ensure_ascii=False))

# --- 래스터 ------------------------------------------------------------------
check("없는 잘린 그림은 할 일로 적힌다",
      "잘린 그림 파일" in SHEET["PUB_D008"]["Needs"], SHEET["PUB_D008"]["Needs"])
check("있는 잘린 그림은 할 일이 아니다",
      "잘린 그림 파일" not in SHEET["PUB_D001"]["Needs"])

# --- 이름 --------------------------------------------------------------------
_rows = ROWS + [draft_row("BAD/ID_D001", "BAD/ID", "FIG1", "1", BAR)]
write(MP.DRAFT, DRAFT_FIELDS, _rows)
write(MP.BLOCKS, ("Draft_ID", "Count_Blocked", "Duplicate_Of"),
      [{"Draft_ID": r["Draft_ID"], "Count_Blocked": r["_blocked"],
        "Duplicate_Of": r["_dup"]} for r in _rows])
_said = []
shutil.rmtree(OUT, ignore_errors=True)
MP.build(RUN, OUT, RUN, RUN_DATE, log=_said.append)
check("계획서가 받지 못하는 이름의 편은 건너뛰고, 건너뛴다고 말한다",
      not os.path.exists(os.path.join(OUT, "plan_BAD/ID.json"))
      and any("BAD/ID" in s for s in _said), _said)
write(MP.DRAFT, DRAFT_FIELDS, ROWS)
write(MP.BLOCKS, ("Draft_ID", "Count_Blocked", "Duplicate_Of"),
      [{"Draft_ID": r["Draft_ID"], "Count_Blocked": r["_blocked"],
        "Duplicate_Of": r["_dup"]} for r in ROWS])

# --- 캡션은 전문이 있으면 전문 ---------------------------------------------------
check("캡션 전문이 있으면 초안의 한 줄이 아니라 전문을 넣는다",
      FIG["PUB_D001"]["caption"] == BAR and BAR != BAR_LINE,
      FIG["PUB_D001"]["caption"])
check("--only는 이름 댄 편만 쓴다",
      [r["Publication_ID"] for r in build(only={"NOPE"})[2]] == [],
      [r["Publication_ID"] for r in build(only={"NOPE"})[2]])

# ------------------------------------------------- 통계 종류를 가른다

_ST = MP.statistic_type_for

# REVERT: 사분위 요약을 연속형으로 보낸다. 평평한 연속형 템플릿에는 중앙값을
# 적을 자리가 없어서, 중앙값이 `Mean`이라는 이름의 칸에 들어가고 평균으로
# 합성됩니다. 이 코퍼스의 IQR 여덟 그림이 전부 자기 문장에 median이라고
# 적혀 있습니다.
check("IQR과 RANGE는 사분위 요약으로 간다",
      _ST("GEOMETRY_NOT_AUTHORED", "IQR") == "QUANTILE_SUMMARY"
      and _ST("GEOMETRY_NOT_AUTHORED", "RANGE") == "QUANTILE_SUMMARY")
check("나머지 분산은 연속형이다",
      all(_ST("GEOMETRY_NOT_AUTHORED", c) == "CONTINUOUS"
          for c in ("SD", "SE", "SEM", "CI95", "NO_ERRORBAR")))
check("처분이 정하는 종류는 처분을 따른다",
      _ST("ASSOCIATION_EXTRACT", "") == "ASSOCIATION"
      and _ST("BINARY_EXTRACT", "") == "BINARY_EVENT")
# REVERT: 오차 정의가 없어도 종류를 정한다. 아직 아무도 무엇을 읽을지 말하지
# 않은 그림이 추출 대기열에 서게 됩니다.
check("정의가 없거나 처분된 그림은 종류를 정하지 않는다",
      _ST("GEOMETRY_NOT_AUTHORED", "") == ""
      and _ST("GEOMETRY_NOT_AUTHORED", "DROP") == ""
      and _ST("NOT_DATA", "SD") == "")

# REVERT: 상자그림 읽기를 캡션의 일반 판정 뒤로 미룬다. 그 논문의 문서 진술이
# SEM이고 그것이 상자그림 그림들에 붙어 있었습니다 - 캡션이 상자라고 말하는데도.
_boxcap = {"Box_Elements": "CENTER=MEDIAN;BOX=P25_P75;WHISKER=MIN_MAX",
           "Box_Evidence": "Box plots indicate minimum, 25th percentile, median,"
                           " 75th percentile, and maximum values.",
           "Errorbar_Definition": "SEM", "Caption_Full": "…",
           "Doc_Errorbar_Definition": "SEM", "Page": "9"}
_code, _src, _kind, _where = MP.dispersion_for("d", _boxcap, None)
check("캡션이 상자그림이라고 말하면 그 말이 이깁니다",
      (_code, _kind, _where) == ("IQR", MP.FROM_CAPTION, "9")
      and _src.startswith("Box plots indicate"),
      (_code, _kind, _where))
check("그 그림은 사분위 요약으로 간다",
      _ST("GEOMETRY_NOT_AUTHORED", _code) == "QUANTILE_SUMMARY")

# --------------------------------- 캡션이 스스로 어긋난 그림은 사람에게

_MIXED_CAP = ("Fig. 8 | Endothelial and capillary state. a Soluble VEGF (n = 18). "
              "b Example of capillaroscopy, and capillary density per mm (n = 15). "
              "Box plots indicate minimum, 25th percentile, median, 75th "
              "percentile, and maximum.")

def _route(cap, count=4):
    row = {"Draft_ID": "d", "Source_Document_ID": "DOC", "Caption_Text": "",
           "Figure_Number": "FIG8", "Source_File": "a.pdf", "Page": "11",
           "Figure_Crop": ""}
    _fig, needs, route, disposition, _disp = MP.figure_of(
        row, cap, None, count, ROOT)
    return {"route": route, "disposition": disposition, "needs": needs}

# REVERT: 캡션이 스스로 분산을 말했는지 보지 않고 경로를 정한다. "Example of"
# 한 낱말이 패널 b 하나를 가리키는데 그림 전체가 NOT_DATA가 됩니다.
_own = _route({"Caption_Full": _MIXED_CAP, "Errorbar_Definition": "UNSTATED",
               "Box_Elements": "CENTER=MEDIAN;BOX=P25_P75;WHISKER=MIN_MAX",
               "Box_Evidence": "Box plots indicate minimum,", "Page": "11"})
check("상자그림을 말하는 캡션은 NOT_DATA로 가지 않는다",
      _own["route"] == "MIXED_CAPTION_NOT_DECIDABLE"
      and _own["disposition"] == "UNRESOLVED", _own)

_said = _route({"Caption_Full": "Fig. 4. Responses during the LBNP protocol. "
                                "Values are mean +- SD.",
                "Errorbar_Definition": "SD", "Box_Elements": "", "Page": "4"})
check("캡션이 분산을 말하면 낱말 하나로 빠지지 않는다",
      _said["route"] == "MIXED_CAPTION_NOT_DECIDABLE", _said["route"])

_quiet = _route({"Caption_Full": "Fig. 1. Study protocol and timeline.",
                 "Errorbar_Definition": "UNSTATED", "Box_Elements": "", "Page": "2"})
check("아무 말도 없는 캡션은 그대로 NOT_DATA다",
      _quiet["route"] == "NOT_DATA", _quiet["route"])

# REVERT: 할 일을 적지 않는다. 그림들이 `UNRESOLVED`에 이름 없이 앉아 있고,
# 사람은 그것들이 있다는 것조차 모릅니다 - `NOT_DATA`보다 나쁩니다.
check("그 그림은 사람이 볼 목록에 이름이 오른다",
      any("어긋난" in n for n in _own["needs"]), _own["needs"])
check("패널이 없으면 할 일도 없다",
      not any("어긋난" in n for n in _route(
          {"Caption_Full": _MIXED_CAP, "Errorbar_Definition": "SD",
           "Box_Elements": "", "Page": "11"}, count=0)["needs"]))

# ------------------------------------------- 사람이 보고 정한 것이 이깁니다

def _decided(choice, which="", cap=None, count=4):
    """그 처분이 적힌 그림 하나를 계획서에 태워 보고, 나온 것을 돌려준다."""
    row = {"Draft_ID": "d", "Source_Document_ID": "DOC", "Caption_Text": "",
           "Figure_Number": "FIG8", "Source_File": "a.pdf", "Page": "11",
           "Figure_Crop": ""}
    dec = {"Draft_ID": "d", "Decision": choice, "Which_Panels": which} if choice else None
    _fig, needs, route, disposition, _d = MP.figure_of(
        row, cap if cap is not None else {
            "Caption_Full": _MIXED_CAP, "Errorbar_Definition": "UNSTATED",
            "Box_Elements": "CENTER=MEDIAN;BOX=P25_P75;WHISKER=MIN_MAX",
            "Box_Evidence": "Box plots indicate minimum,", "Page": "11"},
        None, count, ROOT, figure_decision=dec)
    # 이 편에는 잘린 그림 파일이 없습니다. 그 할 일은 처분과 상관없이 늘
    # 붙고, 여기서 보려는 것이 아니라서 빼고 봅니다 - 지우는 것이 아니라
    # 다른 물음에 속한 줄이기 때문입니다.
    return {"route": route, "disposition": disposition,
            "needs": [n for n in needs if n != "잘린 그림 파일"]}

# REVERT: 사람의 처분을 읽지 않는다. `record_decisions`가 적어 둔 64개의 판정이
# 파일 안에만 있고, 계획서는 사람이 이미 답한 것을 계속 묻습니다.
_not_data = _decided("NOT_DATA")
check("데이터가 아니라고 하신 그림은 그렇게 처분된다",
      _not_data["disposition"] == "NOT_DATA", _not_data)
check("처분된 그림에는 더 물을 것이 없다",
      _not_data["needs"] == [], _not_data["needs"])

# REVERT: "전부 데이터다"를 그냥 처분으로 적는다. 사람이 데이터라고 한 그림이
# `DATA`라는 이름의 처분에 앉아서, 아무도 그 그림을 읽지 않습니다.
_data = _decided("DATA")
check("데이터라고 하신 그림은 보통 그림으로 돌아온다",
      _data["route"] == "DIGITIZE"
      and _data["disposition"] == "GEOMETRY_NOT_AUTHORED", _data)
check("돌아온 그림에는 기하 할 일이 붙는다",
      any("패널 기하" in n for n in _data["needs"]), _data["needs"])

_partial = _decided("PARTIAL", which="a")
check("일부 패널만이라고 하신 그림은 어느 패널인지까지 적힌다",
      _partial["disposition"] == "UNRESOLVED"
      and any(n.endswith(": a") for n in _partial["needs"]), _partial)
check("패널을 대지 않은 일부 처분은 이름만 적는다",
      _decided("PARTIAL")["needs"] == ["일부 패널만 데이터라고 하신 그림 — 그 패널만 추출"],
      _decided("PARTIAL")["needs"])
check("다시 세라·다시 자르라는 각자의 이름으로 적힌다",
      any("계수 다시" in n for n in _decided("COUNTABLE")["needs"])
      and any("재크롭" in n for n in _decided("RECROP")["needs"]))

# REVERT: 보류를 처분으로 친다. 사람이 "아직 모르겠다"고 누른 것이 판정이
# 되어서, 아무도 그 그림을 다시 보지 않습니다.
check("보류는 판정이 아니다",
      _decided("HOLD") == _decided(""), _decided("HOLD"))
check("판정이 없으면 전과 같다",
      _decided("")["disposition"] == "UNRESOLVED"
      and any("어긋난" in n for n in _decided("")["needs"]), _decided(""))

# REVERT: 처분된 그림에도 계수를 묻는다. 세지 않은 채로 "데이터가 아니다"라고
# 답한 그림에게 계획서가 "패널 계수"라고 다시 적습니다.
check("처분된 그림에는 계수도 묻지 않는다",
      _decided("NOT_DATA", count=None)["needs"] == [],
      _decided("NOT_DATA", count=None)["needs"])
check("판정이 없으면 계수는 그대로 묻는다",
      MP.COUNT_NEED in _decided("", count=None)["needs"])

_missing = MP.load_figure_decisions(os.path.join(ROOT, "no_such_run"))
check("처분 파일이 없는 실행도 계획서를 만든다", _missing == {}, _missing)

# ------------------------------------------ 사람이 확인한 기하·정체가 계획서가 된다
print("confirmed geometry and identity become a read block; anything less is named")
import json as _json                                             # noqa: E402
import geometry_proposer as GP                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402
import record_geometry as RG                                     # noqa: E402
import record_identity as RI                                     # noqa: E402
write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status"),
      [{"Draft_ID": "PUB_D001", "Observed_Panel_Count": "4", "Entry_Status": "ENTERED"}])
_SEG = os.path.join(RUN, "seg")
for sub in ("geometry600", "identity600", "regions600"):
    os.makedirs(os.path.join(_SEG, sub), exist_ok=True)
_RASTER = os.path.join("seg", "regions600", "PUB_D001_600.png")
open(os.path.join(RUN, _RASTER), "wb").write(b"\x89PNG\r\n")
import hashlib as _hashlib                                       # noqa: E402
_RASTER_SHA = _hashlib.sha256(open(os.path.join(RUN, _RASTER), "rb").read()).hexdigest()


def _seg_write(rel, fields, rows):
    with io.open(os.path.join(RUN, rel), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            w.writerow(dict((k, row.get(k, "")) for k in fields))


# 사람이 600 DPI 래스터 위에서 그린 패널 셋: 플롯, 데이터 아님, 플롯.
_seg_write(MP.PANEL_DECISIONS, ("Draft_ID", "Panel_Index", "Mark_Type", "Verdict", "Verified_By", "Verified_At"),
           [{"Draft_ID": "PUB_D001", "Panel_Index": "1", "Mark_Type": "BAR", "Verdict": "PANELS", "Verified_By": "minyeop", "Verified_At": "2026-09-13"},
            {"Draft_ID": "PUB_D001", "Panel_Index": "2", "Mark_Type": "NOT_DATA", "Verdict": "PANELS", "Verified_By": "minyeop", "Verified_At": "2026-09-13"},
            {"Draft_ID": "PUB_D001", "Panel_Index": "3", "Mark_Type": "BOX", "Verdict": "PANELS", "Verified_By": "minyeop", "Verified_At": "2026-09-13"}])
_seg_write(MP.REGIONS, ("Draft_ID", "Panel_Index", "Mark_Type", "Raster_600", "Raster_600_SHA256", "Region_600"),
           [{"Draft_ID": "PUB_D001", "Panel_Index": "1", "Mark_Type": "BAR", "Raster_600": _RASTER, "Raster_600_SHA256": _RASTER_SHA, "Region_600": "0,0,900,500"},
            {"Draft_ID": "PUB_D001", "Panel_Index": "3", "Mark_Type": "BOX", "Raster_600": _RASTER, "Raster_600_SHA256": _RASTER_SHA, "Region_600": "900,0,1800,500"}])


def _geom(pid, status="CONFIRMED", frame=(100, 700, 60, 460), pairs="100@80;0@440", **over):
    row = {c: "" for c in GP.PROPOSAL_COLUMNS}
    row.update({"Proposal_ID": pid, "Raster": _RASTER, "Raster_SHA256": _RASTER_SHA, "Region": "0,0,900,500",
                "Panel_X0": frame[0], "Panel_X1": frame[1], "Panel_Y0": frame[2], "Panel_Y1": frame[3],
                "Axis_X_Region": "100,700,460,500", "Axis_Y_Region": "0,100,60,460",
                "Y_Tick_Read_Status": GP.READ_OK, "Human_Verification_Status": status,
                "Verified_By": "MC", "Verified_At": "2026-09-18", "Y_Tick_Top_Value": "100",
                "Y_Tick_Bottom_Value": "0", "Confirmed_Tick_Values": pairs})
    row.update(over)
    return row


def _ident(pid, status="CONFIRMED", frame=(100, 700, 60, 460), mark="BAR_COLOR", **over):
    row = {c: "" for c in IP.IDENTITY_COLUMNS}
    row.update({"Proposal_ID": pid, "Raster": _RASTER, "Panel_Kind": mark.split("_")[0],
                "Panel_X0": frame[0], "Panel_X1": frame[1], "Panel_Y0": frame[2], "Panel_Y1": frame[3],
                "Human_Verification_Status": status, "Verified_By": "MC", "Verified_At": "2026-09-18",
                "X_Factor": "TIMEPOINT",
                "X_Labels": _json.dumps([{"label": "Pre", "px": 175}, {"label": "Post", "px": 625}]),
                "Series_Factor": "ARM",
                "Series": _json.dumps([{"name": "Fluid", "colour": "#DC2828"}, {"name": "Control", "colour": "#2850DC"}]),
                "Mark_Type": mark, "Outcome_Name": "Heart rate", "Unit": "bpm", "N_Outcome": "8",
                "Bar_Top_Definition": "OUTLINE_CENTER", "Errorbar_Stem_Confirmed": "TRUE"})
    row.update(over)
    return row


def _confirm(geometry, identity, **kw):
    GP.write_proposals(os.path.join(_SEG, "geometry600", RG.DECISIONS), geometry)
    IP.write_proposals(os.path.join(_SEG, "identity600", RI.DECISIONS), identity)
    plan, sheet, ready = build(**kw)
    panels = list(csv.DictReader(io.open(os.path.join(OUT, MP.PANELS), encoding="utf-8")))
    fig = dict((f["source_figure_id"], f) for f in plan["figures"])["PUB_D001"]
    return plan, sheet, fig, dict((r["Panel_ID"], r) for r in panels)


_plan, _sheet, _fig, _panels = _confirm([_geom("PUB_D001__p1")], [_ident("PUB_D001__p1")])
_p1 = [p for p in _fig["panels"] if p["panel_id"] == "PUB_D001_P1"][0]
check("the figure's panels are the ones a person drew, by their numbers, on the 600 DPI raster",
      [p["panel_id"] for p in _fig["panels"]] == ["PUB_D001_P1", "PUB_D001_P2", "PUB_D001_P3"]
      and _fig["observed_panel_count"] == 3 and _fig["image"] == _RASTER and _fig["image_sha256"] == _RASTER_SHA,
      "%s %s %s" % ([p["panel_id"] for p in _fig["panels"]], _fig.get("observed_panel_count"), _fig.get("image")))
check("the count sheet's number, when it differs, is kept in the note",
      "count sheet said 4" in _fig.get("note", ""), _fig.get("note"))
# REVERT: the confirmed geometry and identity stay in their files. The panel
# stays GEOMETRY_NOT_AUTHORED and nothing a person answered reaches a reader.
check("a panel with confirmed geometry and identity is AUTO_DIGITIZE with a read block",
      _p1["disposition"] == "AUTO_DIGITIZE" and _p1["target_status"] == "TARGET"
      and _p1["outcome_label"] == "Heart rate" and _p1["read"]["box"] == [100, 700, 60, 460]
      and _p1["read"]["y_ticks"] == [[100.0, 80.0], [0.0, 440.0]] and _p1["read"]["mark_type"] == "BAR_COLOR",
      "%s %s" % ({k: _p1.get(k) for k in ("disposition", "target_status")}, _p1.get("read", {}).get("box")))
check("positions carry the person's factor, level and pixel",
      [(q["factor"], q["level"], q["x_pixel"]) for q in _p1["read"]["positions"]] == [("TIMEPOINT", "Pre", 175.0), ("TIMEPOINT", "Post", 625.0)])
check("series carry factor, level and colour",
      [(q["factor"], q["level"], q["colour"]) for q in _p1["read"]["series"]] == [("ARM", "Fluid", "#DC2828"), ("ARM", "Control", "#2850DC")])
_u1 = [u for u in _plan["units"] if u["panel_id"] == "PUB_D001_P1"][0]
_g1 = [g for g in _plan["grids"] if g["grid_id"] == _u1["grid_id"]][0]
check("the unit binds the panel, names the outcome, unit, n, dispersion, bar top and stem",
      _u1["unit_id"] == _p1["read"]["unit_id"] and _u1["outcome_name"] == "Heart rate" and _u1["unit"] == "bpm"
      and _u1["n_outcome"] == 8 and _u1["dispersion_type"] == "SD" and _u1["statistic"] == "CONTINUOUS"
      and _u1["bar_top_definition"] == "OUTLINE_CENTER" and _u1["errorbar_stem_confirmed"] == "TRUE"
      and _u1["x_calibration"] == [[0, 175.0], [1, 625.0]], "%s" % _u1)
check("the grid declares both factors with the levels the person named",
      _g1["factors"] == {"TIMEPOINT": ["Pre", "Post"], "ARM": ["Fluid", "Control"]}, _g1["factors"])
_problems = [q for q in CP.validate_plan(_plan, file_root=RUN) if q["where"].startswith("figures[0]") or q["where"].startswith("units") or q["where"].startswith("grids")]
check("the authored figure, its unit and its grid validate", _problems == [], _problems[:3])
check("the person's view is in the figure views", "F_PUB_D001" in _plan.get("figure_views", {}))
check("a NOT_DATA panel the person drew stays NOT_DATA",
      [p for p in _fig["panels"] if p["panel_id"] == "PUB_D001_P2"][0]["disposition"] == "NOT_DATA"
      and [p for p in _fig["panels"] if p["panel_id"] == "PUB_D001_P2"][0]["target_status"] == "NOT_DATA")
check("an unconfirmed plot panel stays GEOMETRY_NOT_AUTHORED and is named in plan_panels.csv",
      _panels["PUB_D001_P3"]["Disposition"] == "GEOMETRY_NOT_AUTHORED" and _panels["PUB_D001_P3"]["Geometry"] == "PENDING"
      and "기하 확인" in _panels["PUB_D001_P3"]["Needs"] and _panels["PUB_D001_P1"]["Authored"] == "1"
      and _panels["PUB_D001_P3"]["Authored"] == "0", "%s" % _panels.get("PUB_D001_P3"))
check("the figure's Needs counts what is left", "기하 1/2 · 정체 1/2 · 읽을 준비 1/2" in _sheet["PUB_D001"]["Needs"], _sheet["PUB_D001"]["Needs"])
check("without a reviewers file the figure inventory stays PENDING and asks for the registration",
      _fig["inventory_status"] == "PENDING" and any("검토자 등록: minyeop" in n for n in _sheet["PUB_D001"]["Needs"].split(" · ")),
      "%s %s" % (_fig["inventory_status"], _sheet["PUB_D001"]["Needs"]))

# REVERT: a confirmed geometry alone authors the panel. The reader would have a
# frame and no idea which mark is which group, nor where on x to look.
_plan1b, _sheet1b, _fig1b, _panels1b = _confirm([_geom("PUB_D001__p1")], [])
check("a confirmed geometry without an identity is not read, and the identity is what is asked",
      _panels1b["PUB_D001_P1"]["Authored"] == "0" and _panels1b["PUB_D001_P1"]["Geometry"] == "CONFIRMED"
      and "정체 확인" in _panels1b["PUB_D001_P1"]["Needs"] and "기하 확인" not in _panels1b["PUB_D001_P1"]["Needs"],
      "%s" % _panels1b["PUB_D001_P1"])
# REVERT: the identity is taken on whatever frame. The x pixels were read on
# another frame - one the person later redrew - and land off the marks.
_plan2, _sheet2, _fig2, _panels2 = _confirm([_geom("PUB_D001__p1", frame=(120, 700, 60, 460))], [_ident("PUB_D001__p1")])
check("an identity confirmed on another frame does not author the panel, and says so",
      _panels2["PUB_D001_P1"]["Authored"] == "0" and "다른 프레임" in _panels2["PUB_D001_P1"]["Needs"], _panels2["PUB_D001_P1"]["Needs"])
_plan3, _sheet3, _fig3, _panels3 = _confirm(
    [_geom("PUB_D001__p1", status="REJECTED", Y_Tick_Top_Value="", Y_Tick_Bottom_Value="", Confirmed_Tick_Values=""),
     dict(_geom("PUB_D001__p3", status="REJECTED", Y_Tick_Top_Value="", Y_Tick_Bottom_Value="", Confirmed_Tick_Values=""),
          Panel_X0="", Panel_X1="", Panel_Y0="", Panel_Y1="")],
    [_ident("PUB_D001__p1", status="REJECTED")])
check("a rejected geometry with a frame asks for the frame to be redrawn",
      _panels3["PUB_D001_P1"]["Geometry"] == "REJECTED" and "다시 그리기" in _panels3["PUB_D001_P1"]["Needs"], _panels3["PUB_D001_P1"]["Needs"])
check("a refusal the person rejected - no plot here - is NOT_DATA",
      _panels3["PUB_D001_P3"]["Geometry"] == "NO_PLOT" and _panels3["PUB_D001_P3"]["Disposition"] == "NOT_DATA")
_plan4, _sheet4, _fig4, _panels4 = _confirm([_geom("PUB_D001__p1")], [_ident("PUB_D001__p1", status="REJECTED")])
check("an identity the person declined to read closes the panel as MANUAL_DIGITIZE",
      _panels4["PUB_D001_P1"]["Disposition"] == "MANUAL_DIGITIZE", _panels4["PUB_D001_P1"]["Disposition"])
# A box: the box is the IQR by construction, and a box has no bar top.
_plan5, _sheet5, _fig5, _panels5 = _confirm(
    [_geom("PUB_D001__p3", Region="900,0,1800,500")],
    [_ident("PUB_D001__p3", mark="BOX_VIOLIN", Panel_Kind="BOX", Bar_Top_Definition="", Errorbar_Stem_Confirmed="",
            Series_Factor="GROUP", Series=_json.dumps([{"name": "ALL", "colour": "#ED8B09"}]))])
_u5 = [u for u in _plan5["units"] if u["panel_id"] == "PUB_D001_P3"][0]
check("a box panel is QUANTILE_SUMMARY on IQR with NOT_A_BAR, whatever the figure's SD",
      _u5["statistic"] == "QUANTILE_SUMMARY" and _u5["dispersion_type"] == "IQR" and _u5["bar_top_definition"] == "NOT_A_BAR"
      and "SD" in _u5["errorbar_source"], "%s" % _u5)
check("a single series still carries its factor and level",
      [p for p in _fig5["panels"] if p["panel_id"] == "PUB_D001_P3"][0]["read"]["series"] == [
          {"series_id": "ALL", "factor": "GROUP", "level": "ALL", "colour": "#ED8B09", "note": "legend: ALL"}],
      [p for p in _fig5["panels"] if p["panel_id"] == "PUB_D001_P3"][0]["read"]["series"])
# The reviewers file: a person registers once, and the inventory names them.
_rev = os.path.join(ROOT, "reviewers.json")
_json.dump({"reviewers": [{"reviewer_id": "RV_MC", "name": "M. C.", "record_type": "HUMAN", "contact_type": "ORCID",
                           "contact": "0000-0002-1825-0097", "registered_by": "M. C.", "registration_date": "2026-09-18",
                           "human_attestation": "HUMAN_CONFIRMED"}],
            "names": {"minyeop": "RV_MC"}}, io.open(_rev, "w", encoding="utf-8"))
_plan6, _sheet6, _fig6, _panels6 = _confirm([_geom("PUB_D001__p1")], [_ident("PUB_D001__p1")], reviewers_path=_rev)
check("with the person registered, the figure inventory is VISUALLY_VERIFIED in their name, on their date",
      _fig6["inventory_status"] == "VISUALLY_VERIFIED" and _fig6["reviewer_id"] == "RV_MC" and _fig6["inspection_date"] == "2026-09-13"
      and any(r["reviewer_id"] == "RV_MC" and r["human_attestation"] == "HUMAN_CONFIRMED" for r in _plan6["reviewers"]),
      "%s %s" % (_fig6.get("inventory_status"), [r["reviewer_id"] for r in _plan6["reviewers"]]))
check("without the file, no reviewer but the demo one is written",
      [r["reviewer_id"] for r in _plan["reviewers"]] == [MP.DEMO_REVIEWER]
      and _plan["reviewers"][0]["human_attestation"] == "DEMO_EXAMPLE")
try:
    _json.dump({"reviewers": [], "names": {"minyeop": "RV_X"}}, io.open(_rev, "w", encoding="utf-8"))
    MP.load_reviewers(_rev)
    check("a name pointing at no registered reviewer stops the build", False, "did not stop")
except SystemExit as exc:
    check("a name pointing at no registered reviewer stops the build", "RV_X" in str(exc), str(exc))
check("the demo reviewer carries a contact the registry can be asked about",
      all(_plan["reviewers"][0].get(k) for k in ("contact_type", "contact", "registered_by")))

# ---------------------------------------------------------------------------
shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
