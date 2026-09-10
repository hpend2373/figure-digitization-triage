# -*- coding: utf-8 -*-
"""사람이 그림 위에 그은 패널과 그 종류를 적습니다.

    python3 record_panels.py --run DIR --queue DIR/seg/dig.csv \\
        --answers ~/Downloads/panel_answers.csv --when 2026-09-10

`panel_page.py`가 내는 답 CSV를 받아, 그 답이 **실제로 낸 그림에 대한 것인지**,
**사람이 그림을 보았다고 말했는지**, **누가 보았는지 말했는지**, 그리고 상자가
**실제 크롭 안에 드는지**를 보고 나서 적습니다. `record_geometry.py`와 같은
자리에 서 있습니다.

상자의 크기는 페이지가 심어 둔 크기가 아니라 여기서 크롭을 다시 열어 봅니다.
페이지는 브라우저에 남아 있던 다른 묶음의 상태를 들고 있을 수 있고, 그 좌표가
어느 그림 위의 것인지 확인하는 마지막 자리가 이 관문입니다.

한 그림의 답은 한 덩어리입니다: `PANELS`면 1번부터 이어지는 패널 줄이고,
`NO_PANELS`면 0번 한 줄입니다. 덩어리가 깨져 있으면 - 2번만 있거나, 패널이
있다면서 상자가 없거나 - 그 그림 전체를 이름을 대고 돌려보냅니다. `HOLD`는
답이지만 적히지 않습니다.

적는 파일은 `panel_decisions.csv`입니다. 답안지 이름과 다른 것은 규약입니다:
같으면 관문이 자기 출력을 답으로 읽습니다.
"""
import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import panel_page as PP                                          # noqa: E402

DECISIONS = "panel_decisions.csv"

#: 사람이 할 수 있는 말. `panel_page.js`의 `VERDICTS`·`MARKS`와 같아야 하고,
#: `test_record_panels.py`가 셋(논리·화면·관문)이 같은지 봅니다.
VERDICTS = ("PANELS", "NO_PANELS", "HOLD")
MARKS = ("BAR", "LINE", "BOX", "SCATTER", "NOT_DATA")
HELD = "HOLD"

ANSWER_REQUIRED = ("Draft_ID", "Panel_Index", "Verdict", "Verified_By",
                   "Seen_By_Person")
COLUMNS = ("Draft_ID", "Panel_Index", "X0", "Y0", "X1", "Y1", "Mark_Type",
           "Region_Source", "Mark_Source", "Declared_Count", "Drawn_Count", "Verdict",
           "Seen_By_Person", "Verified_By", "Verified_At", "Note")

TRUE = ("1", "TRUE", "YES", "Y", "T")


def is_true(v):
    return str(v or "").strip().upper() in TRUE


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def crop_size(run, drafts, fid):
    """크롭의 (w, h). 크롭을 열 수 없으면 None - 그 그림에는 상자를 놓을 수 없습니다."""
    rel = (drafts.get(fid) or {}).get("Figure_Crop") or ""
    path = os.path.join(run, rel)
    if not rel or not os.path.isfile(path):
        return None
    try:
        from PIL import Image
        return Image.open(path).size
    except Exception:                                   # noqa: BLE001
        return None


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def check_figure(fid, rows, queued, size):
    """(문제 목록). 한 그림의 줄들을 한 덩어리로 봅니다."""
    problems = []
    verdicts = set((r.get("Verdict") or "").strip().upper() for r in rows)
    whos = set((r.get("Verified_By") or "").strip() for r in rows)

    if not all(is_true(r.get("Seen_By_Person")) for r in rows):
        problems.append(("NOT_SEEN_BY_PERSON",
                         "페이지에서 \"이 그림을 직접 봤다\"를 표시하지 "
                         "않았습니다. 표시가 없는 답은 적지 않습니다."))
    if "" in whos or len(whos) != 1:
        problems.append(("UNATTRIBUTED",
                         "누가 보았는지 비어 있거나 한 그림에 여럿입니다. "
                         "이름 없는 확인은 확인이 아닙니다."))
    if len(verdicts) != 1 or not verdicts <= set(VERDICTS):
        problems.append(("BAD_VERDICT",
                         "%s은 이 관문이 받는 답이 아닙니다. 받는 것: %s"
                         % (", ".join(sorted(v or "(빈칸)" for v in verdicts)),
                            ", ".join(VERDICTS))))
        return problems
    verdict = verdicts.pop()

    if fid not in queued:
        problems.append(("NOT_QUEUED",
                         "%r은 이 대기열의 그림이 아닙니다. 다른 묶음의 답이거나 "
                         "브라우저에 남아 있던 것입니다." % fid))

    idx = sorted(_int(r.get("Panel_Index")) for r in rows)
    if verdict == "PANELS":
        if idx != list(range(1, len(rows) + 1)):
            problems.append(("PANEL_INDEX_BROKEN",
                             "패널 번호가 1부터 이어지지 않습니다: %s. 한 그림의 "
                             "답이 반만 왔습니다." % idx))
        if size is None:
            problems.append(("CROP_UNREADABLE",
                             "이 그림의 크롭을 열 수 없어 상자가 어디에 드는지 "
                             "볼 수 없습니다."))
        for r in rows:
            b = [_int(r.get(k)) for k in ("X0", "Y0", "X1", "Y1")]
            if None in b:
                problems.append(("BOX_NOT_NUMERIC",
                                 "%s번 상자의 좌표가 수가 아닙니다." % r.get("Panel_Index")))
                continue
            if b[2] - b[0] < 4 or b[3] - b[1] < 4:
                problems.append(("BOX_EMPTY", "%s번 상자에 넓이가 없습니다."
                                 % r.get("Panel_Index")))
            if size and (b[0] < 0 or b[1] < 0 or b[2] > size[0] or b[3] > size[1]):
                problems.append(("BOX_OUTSIDE_CROP",
                                 "%s번 상자 %s가 크롭 %sx%s 밖으로 나갑니다. 다른 "
                                 "그림 위의 좌표입니다."
                                 % (r.get("Panel_Index"), b, size[0], size[1])))
            mark = (r.get("Mark_Type") or "").strip().upper()
            if mark not in MARKS:
                problems.append(("BAD_MARK",
                                 "%s번 패널의 종류 %r은 받는 것이 아닙니다. 받는 것: %s"
                                 % (r.get("Panel_Index"), mark or "(빈칸)",
                                    ", ".join(MARKS))))
    else:
        if idx != [0] or any((r.get("X0") or "").strip() for r in rows):
            problems.append(("ROWS_WITHOUT_PANELS",
                             "%s인데 상자 줄이 붙어 있습니다. 패널이 없다는 답에 "
                             "상자가 무엇을 뜻하는지 이 관문은 모릅니다." % verdict))
    if verdict == HELD:
        problems.append(("HELD", "아직 정하지 않은 답입니다. 적지 않고 목록에 "
                                 "남겨 둡니다."))
    return problems


def record(run, queue, answers, when, out_path, replace=False, log=print,
           answers_path=None):
    """(적힌 행, 거절된 (그림, 문제) 목록, 파일 경로)."""
    missing = [c for c in ANSWER_REQUIRED
               if c not in (answers[0] if answers else {})]
    if answers and missing:
        raise SystemExit("답 CSV에 %s 열이 없습니다. 패널 페이지가 내려준 "
                         "파일이 맞습니까?" % ", ".join(missing))
    if answers_path and os.path.exists(answers_path) \
            and os.path.exists(out_path) \
            and os.path.samefile(answers_path, out_path):
        raise SystemExit("답 파일과 적는 파일이 같습니다 (%s). 페이지가 내려준 "
                         "파일은 panel_answers.csv이고, 이 관문이 적는 파일은 "
                         "%s입니다." % (out_path, DECISIONS))
    drafts = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, PP.DRAFTS)))
    queued = set(q["fig"] for q in queue)
    existing = _rows(out_path)
    settled = set(r["Draft_ID"] for r in existing)

    by_fig = {}
    for a in answers:
        by_fig.setdefault((a.get("Draft_ID") or "").strip(), []).append(a)

    written, refused = [], []
    for fid in sorted(by_fig):
        rows = by_fig[fid]
        problems = check_figure(fid, rows, queued, crop_size(run, drafts, fid))
        if problems:
            refused.append((fid or "(빈칸)", problems))
            continue
        if fid in settled and not replace:
            refused.append((fid, [("ALREADY_RECORDED",
                                   "이 그림은 이미 적혀 있습니다. 바꾸려면 "
                                   "--replace를 주십시오.")]))
            continue
        for r in sorted(rows, key=lambda x: _int(x.get("Panel_Index"))):
            row = dict((c, (r.get(c) or "").strip()) for c in COLUMNS)
            row["Verdict"] = row["Verdict"].upper()
            row["Mark_Type"] = row["Mark_Type"].upper()
            row["Verified_At"] = when
            written.append(row)

    done = set(w["Draft_ID"] for w in written)
    keep = [r for r in existing if r["Draft_ID"] not in done]
    rows = sorted(keep + written,
                  key=lambda x: (x["Draft_ID"], _int(x.get("Panel_Index")) or 0))
    with io.open(out_path, "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(COLUMNS), extrasaction="ignore")
        wr.writeheader()
        wr.writerows(rows)

    log("적음 그림 %d장 (패널 %d) · 거절 %d · 이미 있던 것 %d줄"
        % (len(done), sum(1 for w in written if w["Verdict"] == "PANELS"),
           len(refused), len(keep)))
    for name, problems in refused:
        for code, why in problems:
            log("  거절 %s — %s: %s" % (name, code, why))
    return written, refused, out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--queue", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", help="기본은 --queue 옆의 %s" % DECISIONS)
    ap.add_argument("--when", required=True,
                    help="사람이 그림을 본 날짜. 오늘로 채우지 않습니다.")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args(argv)
    queue_path = os.path.expanduser(a.queue)
    out = os.path.expanduser(a.out) if a.out else \
        os.path.join(os.path.dirname(queue_path), DECISIONS)
    answers = _rows(os.path.expanduser(a.answers))
    _w, refused, path = record(
        os.path.expanduser(a.run), _rows(queue_path), answers, a.when, out,
        replace=a.replace, answers_path=os.path.expanduser(a.answers))
    print(path)
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
