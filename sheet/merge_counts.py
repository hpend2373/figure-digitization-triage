# -*- coding: utf-8 -*-
"""Put the sheets' CSV exports back together, or refuse to.

THE SPLIT MADE THIS NECESSARY. The crops ride at the resolution they were cut
at, so the sheet is several files, and each keeps its own entries and exports
its own CSV. Joining them by hand is how a row gets counted twice or dropped
between two spreadsheets - so it is done here, against the draft the sheets
were built from, and it fails closed.

What it refuses, and why each one is a way to be wrong:

  BUILD_MIXED       exports from two different builds. The row a value was
                    typed on is identified by a fingerprint from one draft;
                    across builds the same Draft_ID can be a different figure.
  ROW_IN_TWO_FILES  one row exported by two sheets. Sheets are disjoint by
                    construction, so this is not a merge conflict to resolve -
                    it means the files are not the set they claim to be.
  ROW_UNKNOWN       an exported row the draft does not have.
  ROW_MISSING       a draft row no export covers. A sheet was not downloaded,
                    and the gap is silent in a pile of CSVs.
  VALUE_INVALID     a count that is not a whole number in range, or a count on
                    a row the sheet had blocked.

Usage:
  python3 merge_counts.py --draft <figure_intake_draft.csv> \\
                          --out <observed_panel_counts.csv> <part CSVs...>
"""
import argparse
import collections
import csv
import io
import json
import os
import sys

PANEL_MAX = 40
COLUMNS = ["Draft_ID", "Source_Document_ID", "Source_File", "Page",
           "Figure_Number", "Crop_Quality_Status", "Row_Fingerprint",
           "Observed_Panel_Count", "Entry_Status", "Sheet_Build_ID"]
STATUSES = ("ENTERED", "NOT_REVIEWED", "BLOCKED_BAD_CROP")


def read(path):
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def merge(draft_rows, exports):
    """(merged rows, problems). `exports` is [(name, rows)]."""
    problems = []
    draft_ids = [d["Draft_ID"] for d in draft_rows]
    known = set(draft_ids)

    builds = {r.get("Sheet_Build_ID", "") for _n, rows in exports for r in rows}
    if len(builds) > 1:
        problems.append(("BUILD_MIXED",
                         "내보내기가 서로 다른 빌드에서 나왔습니다: %s"
                         % ", ".join(sorted(builds))))

    seen, where = {}, {}
    for name, rows in exports:
        for r in rows:
            did = r.get("Draft_ID", "")
            if did not in known:
                problems.append(("ROW_UNKNOWN",
                                 "%s: 초안에 없는 행 %s" % (name, did)))
                continue
            if did in seen:
                problems.append(("ROW_IN_TWO_FILES",
                                 "%s이(가) %s와 %s 양쪽에 있습니다"
                                 % (did, where[did], name)))
                continue
            seen[did] = r
            where[did] = name

    for did in draft_ids:
        if did not in seen:
            problems.append(("ROW_MISSING",
                             "어느 내보내기에도 없는 행 %s" % did))

    for did, r in sorted(seen.items()):
        status = (r.get("Entry_Status") or "").strip()
        value = (r.get("Observed_Panel_Count") or "").strip()
        if status not in STATUSES:
            problems.append(("VALUE_INVALID",
                             "%s: 알 수 없는 상태 %r" % (did, status)))
            continue
        if status == "ENTERED":
            if not value.isdigit() or int(value) > PANEL_MAX:
                problems.append(("VALUE_INVALID",
                                 "%s: 입력값 %r은 0 이상 %d 이하의 정수가 "
                                 "아닙니다" % (did, value, PANEL_MAX)))
        elif value:
            # A blocked or unreviewed row carrying a number is the two states
            # the sheet exists to keep apart, collapsed.
            problems.append(("VALUE_INVALID",
                             "%s: 상태가 %s인데 값 %r을 달고 있습니다"
                             % (did, status, value)))

    merged = [seen[d] for d in draft_ids if d in seen]
    return merged, problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--receipt", default="")
    ap.add_argument("parts", nargs="+")
    a = ap.parse_args(argv)

    draft = read(a.draft)
    exports = [(os.path.basename(p), read(p)) for p in a.parts]
    merged, problems = merge(draft, exports)

    counts = collections.Counter(r.get("Entry_Status", "") for r in merged)
    receipt = {"draft": os.path.abspath(a.draft),
               "parts": [os.path.abspath(p) for p in a.parts],
               "draft_rows": len(draft), "merged_rows": len(merged),
               "by_status": dict(counts),
               "problems": [list(x) for x in problems],
               "verdict": "REFUSED" if problems else "MERGED"}
    if a.receipt:
        json.dump(receipt, io.open(a.receipt, "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)

    for code, detail in problems[:20]:
        print("  %-18s %s" % (code, detail))
    if len(problems) > 20:
        print("  ... 그리고 %d건 더" % (len(problems) - 20))
    print("초안 %d행 · 합쳐진 %d행 · %s"
          % (len(draft), len(merged),
             " · ".join("%s %d" % kv for kv in sorted(counts.items()))))
    if problems:
        print("판정: REFUSED — 합친 파일을 쓰지 않았습니다")
        return 1

    with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(merged)
    print("판정: MERGED — %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
