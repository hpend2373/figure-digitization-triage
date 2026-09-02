# -*- coding: utf-8 -*-
"""The review packet: what a person needs to settle the rows the harness cannot.

    python3 review_packet.py make  <run> <out dir>      # sheets + review_queue.csv
    python3 review_packet.py merge <run> <review_queue.csv>

`make` lists every row that is countable by every other rule but has no
validated region (Agreement not AGREE_3 / HUMAN_VALIDATED), draws them twelve
to a sheet with the three proposers' boxes - red = TEXT (the crop now), blue =
PDF, green = RASTER - numbered to match `review_queue.csv`, and leaves two
columns to fill: `Human_Choice` (RASTER / PDF / TEXT / BLOCKED) and a note.
`Agent_Choice` is where an agent may write what IT would pick; nothing reads
that column but a person.

`merge` copies `Human_Choice`, `Agent_Choice` and the note back into
`validated_regions.csv`, matched by Draft_ID AND crop digest - a choice made
about a crop that has since been recut is refused, not applied.
"""
import csv
import hashlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PER_SHEET = 12
COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED")
FIELDS = ("No", "Sheet", "Draft_ID", "Source_Document_ID", "Page",
          "Figure_Number", "Agreement", "PDF_Code", "Raster_Code",
          "Proposal_Figure_BBox", "PDF_BBox", "Raster_BBox", "Crop_SHA256",
          "Human_Choice", "Human_Note", "Agent_Choice", "Agent_Note")


def _sha(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def queue(run):
    """Rows a person has to settle, in a stable order."""
    import block_rules as BR
    draft = list(csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    regions = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "validated_regions.csv"), encoding="utf-8"))}
    out = []
    for d in draft:
        reg = regions.get(d["Draft_ID"])
        if not reg or reg.get("Agreement") in COUNTABLE:
            continue
        if reg.get("Agreement") == "HUMAN_BLOCKED":
            continue
        # Only rows the OTHER rules would let through: a row with no figure
        # number or a still-wrong finding is somebody's to settle already,
        # and putting it here twice helps nobody.
        other = BR.blocked_reason(d, ("", "", ""), agreement=None)
        if other:
            continue
        crop = os.path.join(run, d.get("Figure_Crop") or "")
        out.append({
            "Draft_ID": d["Draft_ID"], "Source_Document_ID": d["Source_Document_ID"],
            "Page": d["Page"], "Figure_Number": d["Figure_Number"],
            "Agreement": reg.get("Agreement", ""),
            "PDF_Code": reg.get("PDF_Code", ""), "Raster_Code": reg.get("Raster_Code", ""),
            "Proposal_Figure_BBox": d.get("Figure_BBox", ""),
            "PDF_BBox": reg.get("PDF_BBox", ""), "Raster_BBox": reg.get("Raster_BBox", ""),
            "Crop_SHA256": _sha(crop) if os.path.exists(crop) else "",
            "Human_Choice": reg.get("Human_Choice", ""),
            "Human_Note": "", "Agent_Choice": reg.get("Agent_Choice", ""),
            "Agent_Note": "",
        })
    out.sort(key=lambda r: (r["Agreement"], r["Source_Document_ID"], r["Draft_ID"]))
    for i, r in enumerate(out, 1):
        r["No"] = i
        r["Sheet"] = "review_%02d.png" % ((i - 1) // PER_SHEET + 1)
    return out


def make(run, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = queue(run)
    path = os.path.join(out_dir, "review_queue.csv")
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        w.writerows(rows)
    sheets = sorted({r["Sheet"] for r in rows})
    for name in sheets:
        ids = [r["Draft_ID"] for r in rows if r["Sheet"] == name]
        first = min(r["No"] for r in rows if r["Sheet"] == name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "compare_regions.py"),
                            run, os.path.join(out_dir, name), "--first", str(first)] + ids,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("몽타주 실패 %s: %s" % (name, (r.stderr or "")[-300:]))
    print("검토 대기 %d행 · 장 %d · %s" % (len(rows), len(sheets), path))
    return 0


def merge(run, queue_path):
    regions_path = os.path.join(run, "validated_regions.csv")
    with io.open(regions_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        regions, cols = list(reader), list(reader.fieldnames)
    for col in ("Human_Choice", "Human_Note", "Agent_Choice", "Agent_Note"):
        if col not in cols:
            cols.append(col)
    by_id = {r["Draft_ID"]: r for r in regions}
    draft = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8"))}
    applied, refused = 0, []
    for q in csv.DictReader(io.open(queue_path, encoding="utf-8")):
        reg = by_id.get(q["Draft_ID"])
        if reg is None:
            refused.append((q["Draft_ID"], "검증표에 없는 행"))
            continue
        crop = os.path.join(run, draft[q["Draft_ID"]].get("Figure_Crop") or "")
        now = _sha(crop) if os.path.exists(crop) else ""
        if q.get("Crop_SHA256") and q["Crop_SHA256"] != now:
            refused.append((q["Draft_ID"], "판정한 크롭과 지금 크롭이 다름 - 다시 봐야 함"))
            continue
        changed = False
        for col in ("Human_Choice", "Human_Note", "Agent_Choice", "Agent_Note"):
            v = (q.get(col) or "").strip()
            if v and reg.get(col, "") != v:
                reg[col] = v
                changed = True
        applied += 1 if changed else 0
    tmp = regions_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in regions])
    os.replace(tmp, regions_path)
    print("반영 %d행 · 거부 %d행" % (applied, len(refused)))
    for did, why in refused[:20]:
        print("  거부 %s: %s" % (did, why))
    return 0 if not refused else 2


if __name__ == "__main__":
    if sys.argv[1] == "make":
        sys.exit(make(sys.argv[2], sys.argv[3]))
    if sys.argv[1] == "merge":
        sys.exit(merge(sys.argv[2], sys.argv[3]))
    raise SystemExit(__doc__)
