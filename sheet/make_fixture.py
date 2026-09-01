# -*- coding: utf-8 -*-
"""A small synthetic intake, so the builder can be run by anyone.

WHY THIS EXISTS. `build_sheet2.py` could only ever be run against one person's
`/tmp` and one publisher corpus that cannot be redistributed. Every change to
it was therefore checked by looking at the output of the one machine that
could produce output at all - and `test_sheet_html.py`, which asserts on the
real corpus (102 cards, the four recovered pids, pid 563's FIG6), cannot run
anywhere else either. Those assertions are worth keeping; they are just not a
way to test the builder.

So this writes an intake with the same shape and none of the content: crops
drawn here, captions written here, a ledger and a worklist that name each
other, and the two audit files. The figures carry a KNOWN number of axis
regions, drawn as plain rectangles, which is what makes a build testable
without a person: not to check anyone's counting, but to check that the page
shows the picture the row is about.

Usage:  python3 make_fixture.py <directory>
"""
import csv
import hashlib
import io
import json
import os
import sys

from PIL import Image, ImageDraw

#: (pid, document id, rows). Each row is
#: (figure number, page, panels, crop status, caption, confidence, reason).
DOCS = [
    ("11", "DOC_A", [
        ("FIG1", "2", 4, "ACCEPTABLE",
         "Figure 1. Kaplan-Meier estimates of biochemical recurrence-free "
         "survival among men treated with radical prostatectomy, stratified "
         "by renin-angiotensin system inhibitor use at baseline. "
         "(A) overall, (B) by stage, (C) by age at diagnosis, and "
         "(D) a sensitivity analysis excluding the first year of follow-up.",
         0.94, ""),
        ("FIG2", "5", 1, "ACCEPTABLE",
         "Figure 2. Forest plot of the adjusted hazard ratios.", 0.88, ""),
        ("FIG3", "7", 6, "THIN_CROP",
         "Figure 3. Six panels, whisker-thin crop.", 0.71, ""),
    ]),
    ("12", "DOC_B", [
        ("FIG1", "3", 2, "ACCEPTABLE",
         "Figure 1. (A) exposure over time and (B) the matched cohort.",
         0.91, ""),
        ("FIG2", "4", 0, "NO_CROP",
         "Figure 2. Study flow diagram.", 0.55,
         "본문 문장으로 읽힙니다"),
    ]),
    ("13", "DOC_C", [
        ("FIG1", "1", 3, "ACCEPTABLE",
         "Figure 1. Three axis regions side by side.", 0.83, ""),
        # the same picture under two labels - the shared-crop case
        ("FIG2", "1", 3, "ACCEPTABLE",
         "Figure 2. Three axis regions side by side.", 0.83, ""),
    ]),
    ("14", "DOC_D", []),          # a document the intake found nothing in
]

#: (pid, label, page, classification, screen) - the second audit's findings.
DEFECTS = [
    ("11", "FIG2", "5", "FAIL", "크롭이 이웃 그림을 담고 있습니다"),
    ("12", "FIG1", "3", "WARNING", "크롭이 캡션을 조금 자릅니다"),
]


#: A fixture page is a page, not just a crop. The sheet now shows the whole
#: page with the box drawn on it - the only view that can answer "did the box
#: catch the figure" - so the fixture has to carry pages, their size in points,
#: and each row's box, exactly as the intake records them.
PAGE_PT = (612.0, 792.0)
PAGE_PX = (850, 1100)


def page_png(path, figure_box_pt, panels, thin=False):
    """A page with some text-like marks and the figure at a known place."""
    im = Image.new("RGB", PAGE_PX, "white")
    dr = ImageDraw.Draw(im)
    sx, sy = PAGE_PX[0] / PAGE_PT[0], PAGE_PX[1] / PAGE_PT[1]
    for i in range(18):                      # a column of "text"
        y = 60 + i * 16
        dr.line([60, y, 300, y], fill=(90, 90, 90), width=3)
    x0, y0, x1, y1 = [v * s for v, s in zip(figure_box_pt, (sx, sy, sx, sy))]
    fig = _figure_image(panels, int(x1 - x0), int(y1 - y0), thin)
    im.paste(fig, (int(x0), int(y0)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def _figure_image(panels, w, h, thin=False):
    im = Image.new("RGB", (max(8, w), max(4, h)), "white")
    dr = ImageDraw.Draw(im)
    if thin or h < 40:
        dr.line([4, h // 2, w - 4, h // 2], fill="black", width=2)
        return im
    cols = min(panels, 3) or 1
    rows = max(1, (panels + cols - 1) // cols)
    cw, ch = w // cols, h // rows
    for i in range(panels):
        x, y = (i % cols) * cw, (i // cols) * ch
        dr.rectangle([x + 8, y + 6, x + cw - 6, y + ch - 12],
                     outline="black", width=2)
        dr.text((x + 12, y + 9), chr(ord("A") + i), fill="black")
    return im


def crop_png(path, panels, thin=False):
    """A figure with `panels` axis regions, drawn plainly.

    Deliberately not a picture of anything: boxes with tick marks, so the
    number of axis regions is unambiguous to a person and the file is small.
    """
    if thin:
        # A whisker-thin crop has nothing to count in it, which is the point:
        # the class is blocked, and the fixture has to carry one.
        im = Image.new("RGB", (420, 26), "white")
        ImageDraw.Draw(im).line([10, 13, 410, 13], fill="black", width=2)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path)
        return
    cols = min(panels, 3) or 1
    rows = max(1, (panels + cols - 1) // cols)
    cw, ch = 420, 300
    im = Image.new("RGB", (cols * cw, rows * ch), "white")
    dr = ImageDraw.Draw(im)
    for i in range(panels):
        x, y = (i % cols) * cw, (i // cols) * ch
        dr.rectangle([x + 40, y + 20, x + cw - 20, y + ch - 40],
                     outline="black", width=3)
        for t in range(5):                       # tick marks on both axes
            tx = x + 40 + t * (cw - 60) // 4
            dr.line([tx, y + ch - 40, tx, y + ch - 30], fill="black", width=2)
            ty = y + 20 + t * (ch - 60) // 4
            dr.line([x + 30, ty, x + 40, ty], fill="black", width=2)
        dr.text((x + 48, y + 26), chr(ord("A") + i), fill="black")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def write(root):
    draft_dir = os.path.join(root, "draft")
    os.makedirs(draft_dir, exist_ok=True)
    audit = os.path.join(root, "audit")
    os.makedirs(audit, exist_ok=True)

    draft, ledger, work = [], [], []
    for pid, doc, rows in DOCS:
        src = os.path.join(root, "pdf", "%s.pdf" % doc.lower())
        os.makedirs(os.path.dirname(src), exist_ok=True)
        io.open(src, "wb").write(("%s" % doc).encode("ascii"))
        ledger.append({
            "Source_Document_ID": doc, "Input_Path": src,
            "Source_File": os.path.basename(src),
            # one document with no page count at all, which must never
            # print as "0쪽"
            "Page_Count": "" if doc == "DOC_D" else str(4 + len(rows)),
            "Text_Backend": "fixture",
            "Text_Backend_Status": "TEXT_LAYER_OK",
            "Text_Block_Count": str(10 * len(rows)),
            "Caption_Candidate_Count": str(len(rows)),
            "Low_Confidence_Count": "0",
            "Page_Render_Status": "OK", "Page_Render_Count": str(len(rows)),
            "Page_Raster_Dir": "", "Required_Action": "", "Detail": "",
            "Pages_Checked": str(len(rows)),
            "Observed_Figure_Count": "", "Document_Inventory_Status": "DRAFT",
        })
        work.append({"pid": pid, "priority": "P1" if pid in ("11", "12")
                     else "P2", "targets": str(len(rows)),
                     "figures": str(len(rows)), "shapes": "B",
                     "domains": "FIXTURE", "memo": "",
                     "href": "file://" + src})
        for i, (fig, page, panels, status, cap, conf, why) in enumerate(rows, 1):
            did = "%s_D%03d" % (doc, i)
            rel = os.path.join(doc, "%s.png" % did)
            # Each row gets its own page, so a row's box is unambiguous.
            box = (306.0, 90.0 + 40.0 * i, 560.0,
                   (110.0 if status == "THIN_CROP" else 300.0) + 40.0 * i)
            page_rel = os.path.join("pages", doc, "%s_p%d.png" % (doc, i))
            page_abs = os.path.join(draft_dir, page_rel)
            if status != "NO_CROP":
                page_png(page_abs, box, panels,
                         thin=(status == "THIN_CROP"))
                crop_png(os.path.join(draft_dir, rel), panels,
                         thin=(status == "THIN_CROP"))
            draft.append({
                "Draft_ID": did, "Source_Document_ID": doc,
                "Source_File": os.path.basename(src),
                "Source_File_SHA256": hashlib.sha256(
                    io.open(src, "rb").read()).hexdigest(),
                "Page": page,
                "Page_Raster": page_abs if status != "NO_CROP" else "",
                "Page_Raster_SHA256": "",
                "Page_Width_Pt": "%.2f" % PAGE_PT[0],
                "Page_Height_Pt": "%.2f" % PAGE_PT[1],
                "Page_Geometry_Method": "PYPDF_MEDIABOX",
                "Figure_Crop": "" if status == "NO_CROP" else rel,
                "Figure_BBox": ",".join("%.1f" % v for v in box),
                "Crop_Quality_Status": status,
                "Figure_Number": fig, "Figure_Label_Raw": fig,
                "Label_Repeats_In_Document": "0",
                "Caption_Text": cap, "Caption_BBox": "",
                "Extraction_Method": "fixture", "Confidence": "%.2f" % conf,
                "Confidence_Reason": why,
                "Human_Verification_Status": "PENDING",
                "Verified_By": "", "Verified_At": "",
                "Observed_Panel_Count": "", "Note": "",
                "PANELS_FOR_TEST": str(panels),
            })

    def dump(path, rows, cols):
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows([{c: r.get(c, "") for c in cols} for r in rows])

    dump(os.path.join(draft_dir, "figure_intake_draft.csv"), draft,
         list(draft[0]))
    dump(os.path.join(draft_dir, "intake_document_status.csv"), ledger,
         list(ledger[0]))
    dump(os.path.join(root, "worklist.csv"), work, list(work[0]))
    dump(os.path.join(audit, "confirmed_image_defects.csv"),
         [{"pid": p, "label": l, "page": g, "classification": c, "screen": s}
          for p, l, g, c, s in DEFECTS],
         ["pid", "label", "page", "classification", "screen"])
    dump(os.path.join(audit, "sentence_warning_rows.csv"),
         [{"draft_id": "DOC_B_D002", "reason": "본문 문장으로 읽힙니다"}],
         ["draft_id", "reason"])
    return {"draft": draft_dir, "audit": audit,
            "worklist": os.path.join(root, "worklist.csv"),
            "rows": len(draft), "documents": len(DOCS)}


if __name__ == "__main__":
    out = write(sys.argv[1] if len(sys.argv) > 1 else "fixture")
    print(json.dumps(out, ensure_ascii=False, indent=2))
