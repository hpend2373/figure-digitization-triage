# -*- coding: utf-8 -*-
"""Second box for every draft row: the one the PDF's own drawings support.

    python3 validate_regions.py <run dir> [seconds]

Writes `<run>/validated_regions.csv` with one row per draft row:

    Draft_ID, Region_Code, Validated_Figure_BBox, Proposal_Figure_BBox, IoU

`Region_Code` is `figure_regions.assign`'s answer - OK, AMBIGUOUS,
NO_CANDIDATE, TAKEN - plus NO_SOURCE when the PDF could not be opened. The
proposal box (`Figure_BBox` in the draft) is kept beside it on purpose: the
two together are the whole point of separating a LOOK HERE from a region
anybody may count from, and their overlap is what says whether the old walk
was pointing anywhere near the figure.

Resumable: one JSON per document under `<run>/.regions/`, so a run that hits
the shell's time limit continues where it stopped.
"""
import csv
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figure_regions as FR                                      # noqa: E402


#: WHICH WAY IS UP. `Figure_BBox` in the draft is in the RASTER's convention -
#: y grows downward from the top of the page - because that is what the sheet
#: draws with and what `corpus_intake` cut the crops with. pdfminer answers in
#: the PDF's own convention, y growing upward from the bottom. Getting this
#: backwards does not fail: it mirrors every box about the middle of the page
#: and hands back a region that looks like a plausible answer to the wrong
#: question. It is converted here, once, so nothing downstream has to know.
def to_raster(box, page_height_pt):
    if not box:
        return None
    x0, y0, x1, y1 = box
    return (x0, page_height_pt - y1, x1, page_height_pt - y0)


def _box(text):
    try:
        x0, y0, x1, y1 = [float(v) for v in str(text).split(",")]
    except ValueError:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def iou(a, b):
    if not a or not b:
        return 0.0
    inter = FR.overlap(a, b, 0) * FR.overlap(a, b, 1)
    union = FR.area(a) + FR.area(b) - inter
    return inter / union if union > 0 else 0.0


def main(run, budget):
    draft = list(csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    ledger = {r["Source_Document_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "intake_document_status.csv"), encoding="utf-8"))}
    cache = os.path.join(run, ".regions")
    os.makedirs(cache, exist_ok=True)

    by_doc = {}
    for d in draft:
        by_doc.setdefault(d["Source_Document_ID"], []).append(d)

    started = time.time()
    done = 0
    for doc in sorted(by_doc):
        out_path = os.path.join(cache, doc + ".json")
        if os.path.exists(out_path):
            continue
        if time.time() - started > budget:
            break
        src = (ledger.get(doc) or {}).get("Input_Path", "")
        answers = {}
        pages = {}
        for d in by_doc[doc]:
            pages.setdefault(d["Page"], []).append(d)
        for page, rows in sorted(pages.items()):
            # 캡션 상자도 초안의 규약(위 기준)이므로 PDF 규약으로 되돌려
            # 넘깁니다 - figure_regions는 PDF가 말하는 좌표로만 셈합니다.
            caps = []
            for r in rows:
                b = _box(r.get("Caption_BBox"))
                try:
                    ph = float(r["Page_Height_Pt"])
                except ValueError:
                    ph = 0.0
                caps.append(to_raster(b, ph) if (b and ph > 0) else None)
            if not src or not os.path.exists(src) or not page.isdigit():
                for r in rows:
                    answers[r["Draft_ID"]] = ["NO_SOURCE", None]
                continue
            usable = [c for c in caps if c]
            try:
                got = FR.regions(src, int(page), usable)
            except Exception as exc:                       # noqa: BLE001
                for r in rows:
                    answers[r["Draft_ID"]] = ["NO_SOURCE", None,
                                              str(exc)[:80]]
                continue
            it = iter(got)
            for r, cap in zip(rows, caps):
                if cap is None:
                    answers[r["Draft_ID"]] = ["NO_CAPTION_BOX", None]
                    continue
                box, code = next(it)
                try:
                    ph = float(r["Page_Height_Pt"])
                except ValueError:
                    ph = 0.0
                box = to_raster(box, ph) if (box and ph > 0) else None
                answers[r["Draft_ID"]] = [code, list(box) if box else None]
        io.open(out_path, "w", encoding="utf-8").write(
            json.dumps(answers, ensure_ascii=False))
        done += 1

    have = {}
    for name in os.listdir(cache):
        if name.endswith(".json"):
            have.update(json.loads(io.open(os.path.join(cache, name),
                                           encoding="utf-8").read()))
    rows = []
    for d in draft:
        code, box = (have.get(d["Draft_ID"]) or ["PENDING", None])[:2]
        prop = _box(d.get("Figure_BBox"))
        rows.append({
            "Draft_ID": d["Draft_ID"],
            "Source_Document_ID": d["Source_Document_ID"],
            "Page": d["Page"],
            "Figure_Number": d["Figure_Number"],
            "Region_Code": code,
            "Validated_Figure_BBox": ("%.1f,%.1f,%.1f,%.1f" % tuple(box)
                                      if box else ""),
            "Proposal_Figure_BBox": d.get("Figure_BBox", ""),
            "IoU": "%.3f" % iou(tuple(box) if box else None, prop),
        })
    target = os.path.join(run, "validated_regions.csv")
    with io.open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    pending = sum(1 for r in rows if r["Region_Code"] == "PENDING")
    print("문서 %d편 처리 · 남은 행 %d · %s" % (done, pending, target))
    return 0 if pending == 0 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 120))
