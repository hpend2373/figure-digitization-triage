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

write(MP.COUNTS, ("Draft_ID", "Observed_Panel_Count", "Entry_Status"),
      [{"Draft_ID": "PUB_D001", "Observed_Panel_Count": "3",
        "Entry_Status": "ENTERED"},
       {"Draft_ID": "PUB_D003", "Observed_Panel_Count": "1",
        "Entry_Status": "ENTERED"},
       # 보았지만 셀 수 없다고 적힌 행. 수가 아닙니다.
       {"Draft_ID": "PUB_D004", "Observed_Panel_Count": "2",
        "Entry_Status": "SEEN_UNCOUNTABLE"},
       # 아직 안 본 행.
       {"Draft_ID": "PUB_D005", "Observed_Panel_Count": "",
        "Entry_Status": "NOT_REVIEWED"}])
_plan, _sheet, _ready = build()
_fig = dict((f["source_figure_id"], f) for f in _plan["figures"])
check("사람이 센 수는 그대로 적힌다", _fig["PUB_D001"]["observed_panel_count"] == 3)
check("계수 파일의 이름은 시트 합치기가 쓰는 그 이름이다",
      MP.COUNTS == "observed_panel_counts.csv", MP.COUNTS)
# REVERT: take the number whatever the status says. "보았지만 셀 수 없다"와
# "아직 안 보았다"가 세어진 것이 되고, 그 그림은 사람 손을 떠납니다.
check("셀 수 없다고 적힌 행의 수는 가져오지 않는다",
      "observed_panel_count" not in _fig["PUB_D004"],
      _fig["PUB_D004"].get("observed_panel_count"))
check("아직 안 본 행도 가져오지 않는다",
      "observed_panel_count" not in _fig["PUB_D005"])
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
      len([p for p in _left if p["check"] == "PLAN_PANEL_COUNT_MISSING"]) == 4,
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

# ---------------------------------------------------------------------------
shutil.rmtree(ROOT, ignore_errors=True)
print()
print("%d scenarios run" % (PASSED[0] + len(FAILURES)))
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
if FAILURES:
    print("FAILED: %s" % FAILURES)
    raise SystemExit(1)
print("all scenarios passed")
