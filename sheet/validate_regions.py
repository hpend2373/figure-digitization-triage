# -*- coding: utf-8 -*-
"""Second box for every draft row: the one the PDF's own drawings support.

    python3 validate_regions.py <run dir> [seconds]

Writes `<run>/validated_regions.csv` with one row per draft row. Three
proposers answer for every caption, and the answers are kept side by side:

    Proposal_Figure_BBox   the draft's `Figure_BBox` - the text walk's answer
    PDF_BBox / PDF_Code    `figure_regions` - clusters of what the PDF draws
    Raster_BBox / Raster_Code  `raster_regions` - connected ink on the page

and what they agree on:

    Agreement              AGREE_3 · AGREE_2_TEXT_DIFFERS · DISAGREE ·
                           RASTER_ONLY · PDF_ONLY · NONE
    Validated_Figure_BBox  set only when the PDF and raster proposers agree
                           (IoU >= AGREE_IOU): their union
    IoU                    the text walk's box against the validated one

THE RULE. A region anybody may count from exists only where two independent
methods point at the same place. One method's box is a proposal, whatever
the method. `AGREE_3` means the sheet's current crop is that region too;
`AGREE_2_TEXT_DIFFERS` means the current crop is not, and a recut from the
validated box would fix it; everything else is a row for a person.

All boxes in this file are in the draft's convention - y down from the top -
so they can be compared with `Figure_BBox` and drawn on the raster directly.

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
import raster_regions as RR                                      # noqa: E402

#: Two proposers agree when their boxes overlap at least this much. 0.6 is
#: past "roughly the same figure" and short of "identical": the object cluster
#: hugs the drawings, the raster blob includes tick labels, so identical boxes
#: are not expected even when both are right.
AGREE_IOU = 0.6
#: The text walk's box counts as agreeing with the validated region when it
#: overlaps it this much. Looser, because that box is padded by design.
TEXT_IOU = 0.5


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
    # 상자를 소비하는 도구는 먼저 자기 상자가 크롭을 재현하는지 증명합니다.
    import roundtrip
    roundtrip.selfcheck(run)
    draft = list(csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    ledger = {r["Source_Document_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "intake_document_status.csv"), encoding="utf-8"))}
    cache = os.path.join(run, ".regions3")
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
            # 넘깁니다 - 두 제안자 모두 PDF가 말하는 좌표로만 셈합니다.
            caps = []
            for r in rows:
                # A row a person moved to the page next door carries its
                # caption's box in the CAPTION page's coordinates. On this
                # page that box means nothing, and handing it to the
                # proposers would make them answer a question nobody asked.
                cap_page = str(r.get("Caption_Page") or "").strip()
                if cap_page and cap_page != str(r.get("Page") or "").strip():
                    caps.append(None)
                    continue
                b = _box(r.get("Caption_BBox"))
                try:
                    ph = float(r["Page_Height_Pt"])
                except ValueError:
                    ph = 0.0
                caps.append(to_raster(b, ph) if (b and ph > 0) else None)
            if not src or not os.path.exists(src) or not page.isdigit():
                for r in rows:
                    answers[r["Draft_ID"]] = {"pdf": ["NO_SOURCE", None],
                                              "raster": ["NO_SOURCE", None]}
                continue
            usable = [c for c in caps if c]
            try:
                graphics, texts, size = FR.page_objects(src, int(page))
                pdf_cands = FR.cluster(graphics, size, texts)
                pdf_got = [(pdf_cands[j] if j is not None else None, code)
                           for j, code in FR.assign(pdf_cands, usable)]
            except Exception as exc:                       # noqa: BLE001
                pdf_got = [(None, "NO_SOURCE")] * len(usable)
                size = (0.0, 0.0)
                texts = []
            raster_got = [(None, "NO_PAGE")] * len(usable)
            raster_path = rows[0].get("Page_Raster") or ""
            if raster_path and os.path.exists(raster_path) and size[0] > 0:
                try:
                    from PIL import Image
                    import numpy as np
                    grey = np.asarray(Image.open(raster_path).convert("L"))
                    raster_got = RR.regions(grey, texts, size, usable)
                except Exception as exc:                   # noqa: BLE001
                    raster_got = [(None, "RASTER_FAILED")] * len(usable)
            it_pdf, it_ras = iter(pdf_got), iter(raster_got)
            for r, cap in zip(rows, caps):
                if cap is None:
                    answers[r["Draft_ID"]] = {"pdf": ["NO_CAPTION_BOX", None],
                                              "raster": ["NO_CAPTION_BOX", None]}
                    continue
                try:
                    ph = float(r["Page_Height_Pt"])
                except ValueError:
                    ph = 0.0
                pb, pc = next(it_pdf)
                rb, rc = next(it_ras)
                pb = to_raster(pb, ph) if (pb and ph > 0) else None
                rb = to_raster(rb, ph) if (rb and ph > 0) else None
                answers[r["Draft_ID"]] = {"pdf": [pc, list(pb) if pb else None],
                                          "raster": [rc, list(rb) if rb else None]}
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
        got = have.get(d["Draft_ID"]) or {"pdf": ["PENDING", None],
                                          "raster": ["PENDING", None]}
        pc, pb = got["pdf"][0], (tuple(got["pdf"][1]) if got["pdf"][1] else None)
        rc, rb = got["raster"][0], (tuple(got["raster"][1]) if got["raster"][1]
                                    else None)
        prop = _box(d.get("Figure_BBox"))
        agreement, validated = agree(pc, pb, rc, rb, prop)
        rows.append({
            "Draft_ID": d["Draft_ID"],
            "Source_Document_ID": d["Source_Document_ID"],
            "Page": d["Page"],
            "Figure_Number": d["Figure_Number"],
            "Agreement": agreement,
            "Validated_Figure_BBox": _fmt(validated),
            "Proposal_Figure_BBox": d.get("Figure_BBox", ""),
            "PDF_Code": pc, "PDF_BBox": _fmt(pb),
            "Raster_Code": rc, "Raster_BBox": _fmt(rb),
            "IoU": "%.3f" % iou(validated, prop),
            "IoU_PDF_Raster": "%.3f" % iou(pb, rb),
            # kept for readers that still ask for the single-method answer
            "Region_Code": pc,
        })
    target = os.path.join(run, "validated_regions.csv")
    # WHAT A PERSON WROTE SURVIVES A RE-RUN OF THE MACHINES. Human_Choice,
    # the notes, the agent's proposals and the recut record are not this
    # tool's to produce, so they are not its to erase: they are carried over
    # from the table already on disk, row by row. A proposer that improved
    # must not cost somebody an afternoon of decisions.
    keep = ("Human_Choice", "Human_Box", "Human_Page", "Human_Note",
            "Agent_Choice", "Agent_Note", "Recut_On", "Recut_From",
            "Stale_Choice", "Stale_Reason", "Blocked_From")
    prior = {}
    if os.path.exists(target):
        prior = {r["Draft_ID"]: r for r in csv.DictReader(
            io.open(target, encoding="utf-8"))}
    fieldnames = list(rows[0]) + [k for k in keep if k not in rows[0]]
    for r in rows:
        old = prior.get(r["Draft_ID"], {})
        for k in keep:
            r[k] = old.get(k, "")
        # A human choice already applied is a HUMAN_VALIDATED / HUMAN_BLOCKED
        # agreement; the machines do not get to re-open it.
        if old.get("Agreement") in ("HUMAN_VALIDATED", "HUMAN_BLOCKED"):
            r["Agreement"] = old["Agreement"]
            r["Validated_Figure_BBox"] = old.get("Validated_Figure_BBox", "")
    with io.open(target, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    pending = sum(1 for r in rows if r["Agreement"] == "PENDING")
    tally = {}
    for r in rows:
        tally[r["Agreement"]] = tally.get(r["Agreement"], 0) + 1
    print("문서 %d편 처리 · 남은 행 %d · %s" % (done, pending, target))
    print("합의: " + ", ".join("%s %d" % kv for kv in sorted(tally.items())))
    return 0 if pending == 0 else 2


def _fmt(box):
    return "%.1f,%.1f,%.1f,%.1f" % tuple(box) if box else ""


def agree(pdf_code, pdf_box, raster_code, raster_box, proposal_box):
    """(Agreement, Validated_Figure_BBox|None) from the three proposers.

    A validated region exists only where the two independent detectors -
    what the PDF draws and where the ink is - point at the same place. The
    text walk's box is then measured against it, not the other way round.
    """
    if pdf_code == "PENDING" or raster_code == "PENDING":
        return "PENDING", None
    p_ok = pdf_code == "OK" and pdf_box is not None
    r_ok = raster_code == "OK" and raster_box is not None
    if p_ok and r_ok:
        if iou(pdf_box, raster_box) >= AGREE_IOU:
            v = (min(pdf_box[0], raster_box[0]), min(pdf_box[1], raster_box[1]),
                 max(pdf_box[2], raster_box[2]), max(pdf_box[3], raster_box[3]))
            if iou(v, proposal_box) >= TEXT_IOU:
                return "AGREE_3", v
            return "AGREE_2_TEXT_DIFFERS", v
        return "DISAGREE", None
    if r_ok:
        return "RASTER_ONLY", None
    if p_ok:
        return "PDF_ONLY", None
    return "NONE", None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 120))
