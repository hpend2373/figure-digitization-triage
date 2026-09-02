# -*- coding: utf-8 -*-
"""Recut the rows whose two independent detectors agree against the crop.

    python3 apply_validated.py <run dir>

`AGREE_2_TEXT_DIFFERS` in `validated_regions.csv` means: the PDF's drawings
and the page's ink both point at one region, and the crop on the sheet - cut
from the text walk's box - is somewhere else. The crop is the odd one out.
This tool moves it: `Figure_BBox` becomes the validated region, the old box
is kept in `Proposal_Figure_BBox`, the crop file is cut again with the
intake's own formula (`roundtrip.cut`, so the round-trip check still holds),
and the regions table is updated to say the three now agree.

WHAT IT REFUSES. A run whose boxes do not already round-trip (a mirrored or
stale draft) - `roundtrip.selfcheck` first. A validated box the formula cannot
cut a picture from - the row is left alone and named. Anything but
`AGREE_2_TEXT_DIFFERS` - a DISAGREE row is a person's to settle, not a tool's.

WHAT IT DOES NOT DO. It does not decide the region is right. Two methods
agreeing is the harness's best evidence, and the census still holds what a
person saw: a recut crop has a new digest, so any verdict bound to the old
one stops applying and a defect once recorded against this figure comes back
as REVIEW_REQUIRED until somebody looks again.
"""
import csv
import datetime
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roundtrip                                                 # noqa: E402

RECUT_FROM = "AGREE_2_TEXT_DIFFERS"

#: What a person may write in `Human_Choice` after looking at the three boxes
#: side by side (the review packet draws them: red = TEXT, blue = PDF,
#: green = RASTER). A closed set: anything else stops the tool, because a
#: choice nobody can read must not become a crop somebody counts from.
#:
#:   RASTER / PDF   recut from that proposer's box; the row becomes countable
#:   TEXT           the crop on the sheet is right as it is; countable
#:   BLOCKED        none of the three is the figure; stays blocked
#:   (blank)        no decision yet
HUMAN_CHOICES = ("", "RASTER", "PDF", "TEXT", "BLOCKED")
CHOICE_BOX = {"RASTER": "Raster_BBox", "PDF": "PDF_BBox",
              "TEXT": "Proposal_Figure_BBox"}


def _write(path, rows, fieldnames):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in fieldnames} for r in rows])
    os.replace(tmp, path)


def main(run):
    from PIL import Image
    roundtrip.selfcheck(run)
    draft_path = os.path.join(run, "figure_intake_draft.csv")
    regions_path = os.path.join(run, "validated_regions.csv")
    with io.open(draft_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        draft, dcols = list(reader), list(reader.fieldnames)
    with io.open(regions_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        regions, rcols = list(reader), list(reader.fieldnames)
    by_id = {r["Draft_ID"]: r for r in regions}
    missing = [d["Draft_ID"] for d in draft if d["Draft_ID"] not in by_id]
    if missing:
        raise SystemExit("영역 검증표에 없는 초안 행 %d개 (예: %s) — 표를 다시 "
                         "만드십시오" % (len(missing), missing[0]))
    for col in ("Proposal_Figure_BBox", "Crop_Source"):
        if col not in dcols:
            dcols.append(col)
    for col in ("Recut_On", "Recut_From", "Human_Choice", "Agent_Choice"):
        if col not in rcols:
            rcols.append(col)
    for reg in regions:
        choice = str(reg.get("Human_Choice") or "").strip().upper()
        if choice not in HUMAN_CHOICES:
            raise SystemExit(
                "%s 행의 Human_Choice가 %r입니다 — 쓸 수 있는 값은 %s 뿐입니다"
                % (reg["Draft_ID"], reg.get("Human_Choice"),
                   ", ".join(v or "(빈칸)" for v in HUMAN_CHOICES)))
    today = datetime.date.today().isoformat()
    done, skipped = [], []
    for d in draft:
        reg = by_id[d["Draft_ID"]]
        choice = str(reg.get("Human_Choice") or "").strip().upper()
        if choice:
            # A PERSON DECIDED. Their choice names which proposer's box is the
            # figure - or that none is - and is applied whatever the detectors
            # agreed on. The row's own defects (no number, a still-wrong
            # finding, the census) are other rules and still apply.
            if choice == "BLOCKED":
                if reg.get("Agreement") != "HUMAN_BLOCKED":
                    reg["Agreement"] = "HUMAN_BLOCKED"
                    done.append(d["Draft_ID"] + " (BLOCKED)")
                continue
            target_box = reg.get(CHOICE_BOX[choice]) or ""
            if not target_box:
                skipped.append((d["Draft_ID"], "%s 상자가 비어 있음" % choice))
                continue
            if target_box == d["Figure_BBox"]:
                if reg.get("Agreement") != "HUMAN_VALIDATED":
                    reg["Agreement"] = "HUMAN_VALIDATED"
                    reg["Recut_On"] = today
                    done.append(d["Draft_ID"] + " (%s, 그대로)" % choice)
                continue
            raster = d.get("Page_Raster") or ""
            if not raster or not os.path.exists(raster) or not d.get("Figure_Crop"):
                skipped.append((d["Draft_ID"], "페이지나 크롭 경로가 없음"))
                continue
            got = roundtrip.cut(Image.open(raster), dict(d, Figure_BBox=target_box))
            if got is None:
                skipped.append((d["Draft_ID"], "%s 상자로는 크롭을 낼 수 없음" % choice))
                continue
            old_box = d["Figure_BBox"]
            got[0].save(os.path.join(run, d["Figure_Crop"]))
            d["Proposal_Figure_BBox"] = d.get("Proposal_Figure_BBox") or old_box
            d["Figure_BBox"] = target_box
            d["Crop_Source"] = "HUMAN_CHOICE_%s" % choice
            reg["Agreement"] = "HUMAN_VALIDATED"
            reg["Validated_Figure_BBox"] = target_box
            reg["Recut_On"] = today
            reg["Recut_From"] = old_box
            done.append(d["Draft_ID"] + " (%s)" % choice)
            continue
        if reg.get("Agreement") != RECUT_FROM:
            continue
        # ONLY ROWS THE INTAKE CALLED ACCEPTABLE. THIN_CROP and EDGE_CLIPPED
        # are verdicts about the crop that is there now; recutting under them
        # would leave a verdict describing a picture that no longer exists.
        # Those rows are blocked already and stay a person's to reopen.
        if str(d.get("Crop_Quality_Status") or "").strip() != "ACCEPTABLE":
            skipped.append((d["Draft_ID"], "상태가 %s인 행은 손대지 않음"
                            % (d.get("Crop_Quality_Status") or "빈 값")))
            continue
        validated = reg.get("Validated_Figure_BBox") or ""
        raster = d.get("Page_Raster") or ""
        if (not validated or not raster or not os.path.exists(raster)
                or not d.get("Figure_Crop")):
            skipped.append((d["Draft_ID"], "검증 상자·페이지·크롭 경로 중 빠진 것"))
            continue
        trial = dict(d, Figure_BBox=validated)
        got = roundtrip.cut(Image.open(raster), trial)
        if got is None:
            skipped.append((d["Draft_ID"], "검증 상자로는 크롭을 낼 수 없음"))
            continue
        image, _pixel_box = got
        old_box = d["Figure_BBox"]
        image.save(os.path.join(run, d["Figure_Crop"]))
        d["Proposal_Figure_BBox"] = d.get("Proposal_Figure_BBox") or old_box
        d["Figure_BBox"] = validated
        d["Crop_Source"] = "VALIDATED_REGION"
        reg["Agreement"] = "AGREE_3"
        reg["Proposal_Figure_BBox"] = validated
        reg["IoU"] = "1.000"
        reg["Recut_On"] = today
        reg["Recut_From"] = old_box
        done.append(d["Draft_ID"])
    if done:
        _write(draft_path, draft, dcols)
        _write(regions_path, regions, rcols)
    # AND PROVE IT. Every recut row must round-trip, or the write was wrong.
    bad = []
    recut_ids = {x.split(" (")[0] for x in done if "BLOCKED" not in x}
    for d in draft:
        if d["Draft_ID"] in recut_ids:
            status, detail = roundtrip.check(d, run)
            if status != "MATCH":
                bad.append((d["Draft_ID"], status, detail))
    print("다시 자른 행 %d · 건너뛴 행 %d" % (len(done), len(skipped)))
    for did, why in skipped[:20]:
        print("  건너뜀 %s: %s" % (did, why))
    if bad:
        for did, status, detail in bad[:10]:
            print("  왕복 실패 %s: %s %s" % (did, status, detail))
        raise SystemExit("다시 자른 크롭이 자기 상자에서 재현되지 않습니다 — 쓰기가 "
                         "잘못됐습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
