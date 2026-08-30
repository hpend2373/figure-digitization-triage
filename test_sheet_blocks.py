# -*- coding: utf-8 -*-
"""Scenarios for the panel-count sheet's blocking rule.

    python3 test_sheet_blocks.py     # exit 0 = all scenarios pass

The rule decides whether a person may type a panel count against a picture, so
it is the one piece of the sheet that has to be reproducible from this
repository alone. It reads no files: the draft it is applied to comes from
publisher PDFs and cannot be published, and a safety rule that can only be
checked against data nobody else has is a safety rule nobody else can check.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "sheet"))
import block_rules as BR                                        # noqa: E402

FAILURES, PASSED = [], [0]


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name
          + ("" if ok else "  <- " + detail))
    if ok:
        PASSED[0] += 1
    else:
        FAILURES.append(name)


def row(**kw):
    base = dict(Figure_Number="FIG1", Confidence="1.00", Confidence_Reason="",
                Crop_Quality_Status="ACCEPTABLE")
    base.update(kw)
    return base


print("what the sheet will not let a person count")

_ok = BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"))
check("an ordinary row with an acceptable crop takes a number", _ok == "",
      "%r" % _ok)

# ---------------------------------------------------- the audits' own findings
check("a figure an audit judged still wrong is blocked",
      BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")) != "")
check("and the message is the audit's own words, not a category",
      "FIG3" in BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")))
check("every still-wrong entry carries a reason a person can act on",
      all(len(v) > 12 for v in BR.STILL_WRONG.values()))
check("the block holds even when the crop grader calls the crop fine",
      BR.blocked_reason(row(Crop_Quality_Status="ACCEPTABLE",
                            Confidence="1.00"),
                        BR.figure_key("99", "FIG1", "4")) != "")
check("a neighbouring figure in the same paper is NOT blocked by it",
      BR.blocked_reason(row(), BR.figure_key("99", "FIG2", "4")) == "")
check("nor the same figure on another page",
      BR.blocked_reason(row(), BR.figure_key("99", "FIG1", "9")) == "")

# ------------------------------------------------- the key is not the ordinal
check("the key is what the page prints, so a rebuilt draft still blocks it",
      BR.figure_key("437", "fig2", " 176 ")
      == BR.figure_key(437, "FIG2", 176))
check("every finding is keyed by (pid, label, page), never by an ordinal",
      all(isinstance(k, tuple) and len(k) == 3
          and not any(str(p).startswith("_D") or "_D0" in str(p) for p in k)
          for k in BR.STILL_WRONG))
check("a Draft_ID handed in as the key matches nothing",
      BR.blocked_reason(row(), "978_1_4419_5692_7_D058") == "")
check("while the figure that Draft_ID used to name is still blocked",
      BR.blocked_reason(row(), BR.figure_key("437", "FIG2", "176")) != "")

# ------------------------------------------------------ a confirmed defect row
_fail = dict(classification="FAIL", kind="mixed_figures",
             screen="FIG2의 산점도와 왼쪽 FIG1의 막대그래프가 함께 보임")
check("a FAIL defect blocks the row it names",
      BR.blocked_reason(row(), BR.figure_key("36", "FIG2", "4"),
                        defect=_fail) != "")
check("and names the kind in the message",
      "다른 그림 혼입" in BR.blocked_reason(row(), BR.figure_key("36", "FIG2", "4"),
                                     defect=_fail))
check("a WARNING defect does not block on its own",
      BR.blocked_reason(row(), BR.figure_key("36", "FIG1", "4"),
                        defect=dict(classification="WARNING", kind="x",
                                    screen="y")) == "")

# ------------------------------------------------- what the machine itself said
check("a row with no figure number is blocked",
      BR.blocked_reason(row(Figure_Number=""),
                        BR.figure_key("1", "", "2")) != "")
check("and the message says a person has to supply the number",
      "번호를 정해야" in BR.blocked_reason(row(Figure_Number=""),
                                    BR.figure_key("1", "", "2")))
check("the missing number is reported before the zero confidence, because it "
      "is the reason a person can act on",
      "번호를 읽지 못했습니다" in BR.blocked_reason(
          row(Figure_Number="", Confidence="0.00",
              Confidence_Reason="설명"), BR.figure_key("1", "", "2")))
check("a numbered row the machine put at zero confidence is blocked",
      BR.blocked_reason(row(Confidence="0.00",
                            Confidence_Reason="두 판독기가 갈렸습니다"),
                        BR.figure_key("1", "FIG1", "2")) != "")
check("and carries the machine's own reason",
      "두 판독기가 갈렸습니다" in BR.blocked_reason(
          row(Confidence="0.00", Confidence_Reason="두 판독기가 갈렸습니다"),
          BR.figure_key("1", "FIG1", "2")))
check("a low but non-zero confidence does NOT block - the sheet shows it "
      "instead, and a person decides",
      BR.blocked_reason(row(Confidence="0.40"),
                        BR.figure_key("1", "FIG1", "2")) == "")

# ------------------------------------------------------------ the crop verdict
for status in ("EDGE_CLIPPED", "THIN_CROP", "NO_CROP"):
    check("a %s crop takes no number" % status,
          BR.blocked_reason(row(Crop_Quality_Status=status),
                            BR.figure_key("1", "FIG1", "2")) != "")
check("every uncountable crop verdict has a message",
      all(v.strip() for v in BR.UNCOUNTABLE_CROPS.values()))
check("an unknown crop verdict does not silently block",
      BR.blocked_reason(row(Crop_Quality_Status="SOMETHING_NEW"),
                        BR.figure_key("1", "FIG1", "2")) == "")

# ------------------------------------------------------- two rows, one picture
_shared = BR.shared_crop_map({"A": "d1", "B": "d1", "C": "d2"})
check("rows whose crop is byte-identical find each other",
      _shared == {"A": ["B"], "B": ["A"]}, "%s" % _shared)
check("a row with its own picture is not in the map",
      "C" not in _shared)
check("and such a row is blocked, because the box did not tell them apart",
      BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"),
                        shared_with=["OTHER_D002"]) != "")
check("the message names the row it collides with",
      "OTHER_D002" in BR.blocked_reason(row(), BR.figure_key("1", "FIG1", "2"),
                                        shared_with=["OTHER_D002"]))
check("three rows sharing one picture all name the other two",
      BR.shared_crop_map({"A": "d", "B": "d", "C": "d"})["A"] == ["B", "C"])
check("an empty draft yields no collisions", BR.shared_crop_map({}) == {})

print()
print("FDT_SCENARIOS_RUN=%d" % PASSED[0])
print("%d scenarios run" % PASSED[0])
if FAILURES:
    print("%d FAILED: %s" % (len(FAILURES), FAILURES))
    raise SystemExit(1)
print("all scenarios passed")
