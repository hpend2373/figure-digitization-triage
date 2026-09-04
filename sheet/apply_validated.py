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
import re
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
#:   DRAWN          none of the three is right but the figure is there, and the
#:                  person drew its box themselves on the page (`Human_Box`)
#:   BLOCKED        there is nothing to count on this page; stays blocked
#:   (blank)        no decision yet
#:
#: DRAWN EXISTS BECAUSE BLOCKED WAS ANSWERING TWO DIFFERENT QUESTIONS. Of the
#: ten rows blocked on 2026-09-02, eight were pages with a whole figure on
#: them - the detectors had simply run out (TAKEN, NO_CANDIDATE, AMBIGUOUS).
#: Blocking them threw away the figure to record the detectors' failure. This
#: choice separates the two: DRAWN says "the figure is here, and here is
#: where", BLOCKED keeps its old meaning of "there is no figure to count".
HUMAN_CHOICES = ("", "RASTER", "PDF", "TEXT", "DRAWN", "BLOCKED")
CHOICE_BOX = {"RASTER": "Raster_BBox", "PDF": "PDF_BBox",
              "TEXT": "Proposal_Figure_BBox", "DRAWN": "Human_Box"}

#: A hand-drawn box shorter than this on a side is a slip of the mouse, not a
#: figure. `roundtrip.cut` would refuse most of them anyway (it needs 8 pixels
#: after padding); this refuses them by name, before anything is written.
MIN_DRAWN_PT = 12.0


def drawn_box(text, row):
    """('x0,y0,x1,y1', '') for a usable hand-drawn box, or ('', why not).

    The box arrives from a browser, so it is checked like anything else that
    comes from outside: four numbers, the right way round, big enough to be a
    figure, and ON THE PAGE it was drawn on. A box that fails any of these is
    named and the row is left alone - it is never quietly clamped into
    something the person did not draw.
    """
    parts = str(text or "").split(",")
    if len(parts) != 4:
        return "", "그린 상자가 네 숫자가 아님 (%r)" % (text,)
    try:
        x0, y0, x1, y1 = [float(v) for v in parts]
    except ValueError:
        return "", "그린 상자에 숫자가 아닌 값이 있음 (%r)" % (text,)
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except (KeyError, ValueError):
        return "", "페이지 크기를 몰라 그린 상자를 확인할 수 없음"
    if pw <= 0 or ph <= 0:
        return "", "페이지 크기가 0 이하"
    if x1 <= 0 or y1 <= 0 or x0 >= pw or y0 >= ph:
        return "", "그린 상자가 페이지 밖에 있음"
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(pw, x1), min(ph, y1)
    if x1 - x0 < MIN_DRAWN_PT or y1 - y0 < MIN_DRAWN_PT:
        return "", "그린 상자가 너무 작음 (%.0f x %.0f pt)" % (x1 - x0, y1 - y0)
    return "%.1f,%.1f,%.1f,%.1f" % (x0, y0, x1, y1), ""


#: How far a hand-drawn box may move a row. It must match what the decision
#: page offers (`review_packet.PAGE_WINDOW`) or a person draws on a page this
#: refuses; the scenario below holds the two together rather than trusting
#: the two numbers to be edited at once.
import review_packet as _rp                                      # noqa: E402
MOVE_REACH = _rp.PAGE_WINDOW

#: How far the raster-derived page size may sit from what the PDF says, in
#: points, before the move is refused. The intake renders a document at one
#: scale; a page that breaks that is a page whose boxes would land elsewhere.
PAGE_SIZE_TOL_PT = 1.0


def page_size_from_pdf(src, page):
    """(width, height) in points as the PDF itself states, or None."""
    try:
        import figure_regions as FR
        _g, _t, size = FR.page_objects(src, int(page))
    except Exception:                                   # noqa: BLE001
        return None
    if not size or size[0] <= 0 or size[1] <= 0:
        return None
    return float(size[0]), float(size[1])


#: How a person may spell the number they read off the page, and what it
#: becomes. The stored form is the intake's own (`FIG4`, `EXTFIG2`), so a row
#: a person numbered and a row the machine numbered are the same kind of fact
#: and the duplicate rule can compare them. Anything else is refused by name
#: rather than stored - a `Figure_Number` nothing can match is worse than none,
#: because the row then counts a figure no other row can be checked against.
HUMAN_NUMBER = "Human_Figure_Number"
NUMBER_SPELLING = re.compile(
    r"^\s*(?P<ext>(?:extended(?:\s+data)?|supplement(?:ary|al)?|online\s+resource)\s+)?"
    r"(?:fig(?:ure)?\.?|그림|도)?\s*(?P<n>[0-9]{1,2})\s*(?P<sub>[a-z])?\s*$", re.I)


def figure_number(text):
    """The stored spelling of a number a person typed, or ("", why).

    Accepts what a person actually types - `4`, `fig4`, `Fig. 4`, `Figure 4b`,
    `Extended Data Fig 2` - and refuses the rest by name.
    """
    raw = str(text or "").strip()
    if not raw:
        return "", ""
    m = NUMBER_SPELLING.match(raw)
    if not m:
        return "", ("그림 번호 %r를 읽을 수 없음 - 4, fig4, Figure 4b, "
                    "Extended Data Fig 2 처럼 적어 주십시오" % (raw,))
    return "%s%s%s" % ("EXTFIG" if m.group("ext") else "FIG", m.group("n"),
                       (m.group("sub") or "").upper()), ""


#: Where `apply_validated` records that a person's box landed on a figure
#: another row already counts. Read back by `block_rules.confirmed_duplicates`.
DUPLICATE_OF, DUPLICATE_PAGE = "Duplicate_Of", "Duplicate_Page"


def moved_page(d, human_page, run, ledger, twins):
    """The row's page fields for the page a person drew on, or (None, why[, twin]).

    The fourth refusal is the only one that is ALSO AN ANSWER, so it returns a
    third value - the Draft_ID of the row already holding the figure - for the
    caller to write down. The other refusals are typos, missing files and
    mismeasured pages; nothing about the figure was learned from them.

    A DRAWN box on the page next door moves the row there - `Page`,
    `Page_Raster` and the page size all change, and `Caption_Page` keeps
    where the caption was. Four refusals, each by name:

      not next door        the page offered ±1; anything else is a typo or a
                           file edited by hand
      no raster            nothing to cut from
      size disagrees       the raster's size over the document's scale must
                           match what the PDF says for that page, within a
                           point - the same check that would have caught a
                           mirrored box, applied to a moved one
      the figure is there  a row for the same figure already lives on that
                           page; moving this one there counts it twice, which
                           is the exact thing the phantom rule exists to stop
    """
    try:
        here, there = int(str(d.get("Page")).strip()), int(str(human_page).strip())
    except ValueError:
        return None, "그린 쪽 번호를 읽을 수 없음 (%r)" % (human_page,)
    if there == here:
        return dict(d), ""
    if abs(there - here) > MOVE_REACH:
        return None, ("그린 쪽 p.%d은 캡션 쪽 p.%d에서 %d쪽 넘게 떨어져 있음 "
                      "(판정 페이지가 보여 주는 범위 밖)"
                      % (there, here, MOVE_REACH))
    raster = str(d.get("Page_Raster") or "")
    target = roundtrip.sibling_raster(raster, there) if raster else ""
    if not raster or not os.path.exists(raster) or not target:
        return None, "p.%d의 페이지 래스터가 없음" % there
    try:
        pw, ph = float(d["Page_Width_Pt"]), float(d["Page_Height_Pt"])
    except (KeyError, ValueError):
        return None, "캡션 쪽의 크기를 몰라 축척을 낼 수 없음"
    if pw <= 0 or ph <= 0:
        return None, "캡션 쪽의 크기가 0 이하"
    from PIL import Image
    scale = Image.open(raster).width / pw
    o = Image.open(target)
    npw, nph = o.width / scale, o.height / scale
    src = (ledger.get(d["Source_Document_ID"]) or {}).get("Input_Path", "")
    said = page_size_from_pdf(src, there) if src and os.path.exists(src) else None
    if said is None:
        return None, "p.%d의 크기를 PDF에서 확인할 수 없어 옮기지 않음" % there
    if abs(said[0] - npw) > PAGE_SIZE_TOL_PT or abs(said[1] - nph) > PAGE_SIZE_TOL_PT:
        return None, ("p.%d의 래스터 크기(%.1fx%.1f)가 PDF의 쪽 크기(%.1fx%.1f)와 "
                      "다름 - 상자가 엉뚱한 데 떨어질 것이므로 옮기지 않음"
                      % (there, npw, nph, said[0], said[1]))
    twin = twins.get((d["Source_Document_ID"], d["Figure_Number"], str(there)))
    if twin:
        return None, ("p.%d에는 같은 그림(%s)의 행 %s이(가) 이미 있음 - 옮기면 두 번 "
                      "세게 되므로 거부; 이 행은 그 그림의 중복으로 적어 둠"
                      % (there, d["Figure_Number"], twin)), twin
    moved = dict(d)
    moved["Caption_Page"] = moved.get("Caption_Page") or str(here)
    moved["Page"] = str(there)
    moved["Page_Raster"] = target
    moved["Page_Width_Pt"] = "%.2f" % said[0]
    moved["Page_Height_Pt"] = "%.2f" % said[1]
    return moved, ""


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
    for col in ("Proposal_Figure_BBox", "Crop_Source", "Caption_Page",
                "Moved_From_Page", "Number_Source"):
        if col not in dcols:
            dcols.append(col)
    for col in ("Recut_On", "Recut_From", "Human_Choice", "Human_Box",
                "Human_Page", "Agent_Choice", "Blocked_From",
                DUPLICATE_OF, DUPLICATE_PAGE, HUMAN_NUMBER):
        if col not in rcols:
            rcols.append(col)
    ledger_path = os.path.join(run, "intake_document_status.csv")
    ledger = ({r["Source_Document_ID"]: r for r in csv.DictReader(
        io.open(ledger_path, encoding="utf-8"))} if os.path.exists(ledger_path) else {})
    # (document, figure, page) -> Draft_ID, so a move can see what is already
    # on the page it is moving to.
    twins = {}
    for d in draft:
        twins.setdefault((d["Source_Document_ID"], d["Figure_Number"], d["Page"]),
                         d["Draft_ID"])
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
        # THE NUMBER FIRST, AND ON ITS OWN. A person supplying the figure
        # number is answering a different question from "which box is the
        # figure", and the row may need both - seven of the eight rows the
        # machine could not number are also THIN_CROP. Applying it before the
        # choice means the box and the number land in one pass, and a row that
        # needs only the number needs no choice at all.
        want, why = figure_number(reg.get(HUMAN_NUMBER))
        if why:
            skipped.append((d["Draft_ID"], why))
        elif want and d.get("Figure_Number", "") != want:
            d["Figure_Number"] = want
            d["Number_Source"] = "HUMAN"
            done.append(d["Draft_ID"] + " (번호 %s)" % want)
        choice = str(reg.get("Human_Choice") or "").strip().upper()
        if choice:
            # A PERSON DECIDED. Their choice names which proposer's box is the
            # figure - or that none is - and is applied whatever the detectors
            # agreed on. The row's own defects (no number, a still-wrong
            # finding, the census) are other rules and still apply.
            if choice == "BLOCKED":
                if reg.get("Agreement") != "HUMAN_BLOCKED":
                    # Remember what the detectors had said, so the block can be
                    # undone (`review_packet.py reopen`). A block with nothing
                    # written down here is a door that only opens one way.
                    reg["Blocked_From"] = reg.get("Agreement") or ""
                    reg["Agreement"] = "HUMAN_BLOCKED"
                    done.append(d["Draft_ID"] + " (BLOCKED)")
                continue
            moved = None
            # WHATEVER THIS ANSWER TURNS OUT TO BE, it replaces the last one.
            # A duplicate recorded from an earlier box must not outlive the
            # box that earned it.
            if reg.get(DUPLICATE_OF) or reg.get(DUPLICATE_PAGE):
                reg[DUPLICATE_OF] = reg[DUPLICATE_PAGE] = ""
            if choice == "DRAWN":
                # THE PAGE FIRST, THEN THE BOX. A box is in the coordinates of
                # the page it was drawn on, so it can only be checked against
                # that page's size.
                human_page = str(reg.get("Human_Page") or "").strip()
                if human_page and human_page != str(d.get("Page")).strip():
                    got_move = moved_page(d, human_page, run, ledger, twins)
                    moved, why = got_move[0], got_move[1]
                    if why:
                        if len(got_move) > 2 and got_move[2]:
                            # THE PERSON FOUND THE FIGURE, where it was
                            # already counted. Write that down: the sheet
                            # turns it into a reason and the queue stops
                            # asking. Silence here left 20 rows in 47 with a
                            # stale HUMAN_BLOCKED reason and a DRAWN answer
                            # nobody could see had been understood.
                            reg[DUPLICATE_OF] = got_move[2]
                            reg[DUPLICATE_PAGE] = human_page
                            done.append(d["Draft_ID"] + " (DRAWN, 중복)")
                        skipped.append((d["Draft_ID"], why))
                        continue
                target_box, why = drawn_box(reg.get("Human_Box"), moved or d)
                if why:
                    skipped.append((d["Draft_ID"], why))
                    continue
            else:
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
            src_row = moved or d
            raster = src_row.get("Page_Raster") or ""
            if not raster or not os.path.exists(raster) or not d.get("Figure_Crop"):
                skipped.append((d["Draft_ID"], "페이지나 크롭 경로가 없음"))
                continue
            got = roundtrip.cut_and_grade(Image.open(raster),
                                          dict(src_row, Figure_BBox=target_box))
            if got is None:
                skipped.append((d["Draft_ID"], "%s 상자로는 크롭을 낼 수 없음" % choice))
                continue
            old_box = d["Figure_BBox"]
            if moved is not None:
                # The row lives on the other page from here on. Everything
                # downstream - round-trip, the sheet's page view, the block
                # rule's figure key - reads these fields and nothing else.
                d["Moved_From_Page"] = d.get("Moved_From_Page") or d["Page"]
                for col in ("Caption_Page", "Page", "Page_Raster",
                            "Page_Width_Pt", "Page_Height_Pt"):
                    d[col] = moved[col]
                twins[(d["Source_Document_ID"], d["Figure_Number"], d["Page"])] = d["Draft_ID"]
            got[0].save(os.path.join(run, d["Figure_Crop"]))
            d["Proposal_Figure_BBox"] = d.get("Proposal_Figure_BBox") or old_box
            d["Figure_BBox"] = target_box
            # MEASURE THE NEW PICTURE. `Crop_Quality_Status` says how tall this
            # crop is against its page and whether the drawing runs off its
            # sides - facts about the crop, not about the figure. Keeping the
            # old reading would describe a picture that no longer exists, and
            # it is the LAST gate the sheet applies: a person could draw the
            # right box on a THIN_CROP row and watch it stay blocked. This is
            # arithmetic redone, not a judgement overruled.
            d["Crop_Quality_Status"] = got[2]
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
    # A block and a recorded duplicate change the regions table, not a crop.
    recut_ids = {x.split(" (")[0] for x in done
                 if "BLOCKED" not in x and "중복" not in x and "(번호 " not in x}
    for d in draft:
        if d["Draft_ID"] in recut_ids:
            status, detail = roundtrip.check(d, run)
            if status != "MATCH":
                bad.append((d["Draft_ID"], status, detail))
    _dups = sum(1 for x in done if "중복" in x)
    _blocks = sum(1 for x in done if "BLOCKED" in x)
    _nums = sum(1 for x in done if "(번호 " in x)
    print("다시 자른 행 %d · 막음 %d · 중복으로 적은 행 %d · 번호를 받은 행 %d "
          "· 건너뛴 행 %d"
          % (len(done) - _dups - _blocks - _nums, _blocks, _dups, _nums,
             len(skipped)))
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
