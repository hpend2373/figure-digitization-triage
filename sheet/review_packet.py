# -*- coding: utf-8 -*-
"""The review packet: what a person needs to settle the rows the harness cannot.

    python3 review_packet.py make   <run> <out dir>      # sheets + review_queue.csv
    python3 review_packet.py merge  <run> <review_queue.csv>
    python3 review_packet.py reopen <run> <Draft_ID> [...]   # 막은 행을 큐로 되돌림
    python3 review_packet.py blocked <run> <out dir>        # 막힌 행 전부를 큐로

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
import roundtrip                                                 # noqa: E402

PER_SHEET = 12
COUNTABLE = ("AGREE_3", "HUMAN_VALIDATED")
#: 사람이 적어 주는 그림 번호. 기계가 캡션에서 읽지 못했을 때 이 칸으로 옵니다.
#: 저장되는 철자는 `apply_validated.figure_number`가 정합니다.
HUMAN_NUMBER = "Human_Figure_Number"
FIELDS = ("No", "Sheet", "Draft_ID", "Source_Document_ID", "Page",
          "Figure_Number", "Agreement", "PDF_Code", "Raster_Code",
          "Proposal_Figure_BBox", "PDF_BBox", "Raster_BBox", "Crop_SHA256",
          "Human_Choice", "Human_Box", "Human_Page", "Human_Note",
          "Agent_Choice", "Agent_Note", "Stale_Choice", "Stale_Reason",
          "Block_Reason", "Box_Would_Open", "Number_Would_Open",
          HUMAN_NUMBER, "Number_Refused", "Mentions_Held", "Ask_Again_Why",
          "Neighbours", "Answered_Key")

#: The page a hand-drawn box was drawn on, when it is NOT the caption's page.
#: Blank means the caption's own page. 2026-09-03: fifteen of the rows nobody
#: could place had their figure on the page next door, because the intake had
#: taken the body's mention of the figure for its caption. Seven of those
#: figures have no other row, so the only way to keep them is to let the
#: person draw on the neighbouring page and move the row there.
HUMAN_PAGE = "Human_Page"

#: What `blocked()` writes so the decision page can offer other pages of the
#: document: "4:612.0x792.0;6:612.0x792.0" - page number and its size in
#: points. Offered only where no proposer placed the figure at all.
NEIGHBOURS = "Neighbours"

#: What a person was answering, as one short string. A row leaves the blocked
#: queue once it is answered and comes back only when this changes.
#:
#: WHY THIS EXISTS. `blocked()` returned EVERY blocked row, with no memory of
#: who had answered what, so each round handed the person back everything they
#: had just done. On 2026-09-03 the queue came back with 79 rows and ALL 79
#: had been answered the round before; 78 of them twice. The person said:
#: "이미 골랐던 피규어 또 고르라고 하는데?" - and they were right.
#:
#: The key is the QUESTION, not the answer: the reason the row is blocked, the
#: crop they were looking at, the three boxes they were choosing between, and
#: whether the card offered the rest of the document. Change any of those and
#: it is a new question, worth asking. Change none and it is the same one.
ANSWERED_KEY = "Answered_Key"
#: WHAT THE QUESTION LOOKED LIKE WHEN THEY ANSWERED, in the two parts a person
#: can recognise. The key is a digest: it can say "this changed" and never
#: which part. Twice now somebody has answered a row, seen it come straight
#: back under "답하셨을 때와 달라졌습니다", and had to ask what had changed -
#: once because their own BLOCKED answer is what gave the row its document
#: window. A prompt that cannot say what moved is asking them to guess.
ANSWERED_WINDOW = "Answered_Window"
ANSWERED_REASON = "Answered_Reason_Key"
DUPLICATE_OF, DUPLICATE_PAGE = "Duplicate_Of", "Duplicate_Page"

#: What `blocked()` puts in front of a reason when it asks again. It is how the
#: row READS, not what it IS, so `question_key` strips it - otherwise a row
#: answered on its second time round comes back a third, because the reason it
#: was answered under now carries a prefix the run itself never has.
ASK_AGAIN = "다시 묻습니다 (답하셨을 때와 달라졌습니다) — "


def _reason_of(fields):
    """The row's block reason with any "we are asking again" prefix removed."""
    reason = str(fields.get("Block_Reason") or "").strip()
    while reason.startswith(ASK_AGAIN):
        reason = reason[len(ASK_AGAIN):]
    return reason


def reason_key(fields):
    """A digest of the block reason alone, so a change in it can be named."""
    return hashlib.sha256(
        _reason_of(fields).encode("utf-8")).hexdigest()[:16]


def window_flag(fields):
    """Whether the card could show the rest of the document. "W" or "-"."""
    return "W" if str(fields.get(NEIGHBOURS) or "").strip() else "-"


#: What to tell somebody whose answer is coming back to them, per part that
#: moved. The window one is the common case and the one nobody could guess:
#: blocking a row is what gives it a window, so their own answer changed the
#: question.
ASK_AGAIN_WHY = {
    "WINDOW": "이제 이 카드에서 문서의 다른 쪽을 넘겨 볼 수 있습니다 — "
              "막으신 행에는 문서 전체를 싣습니다.",
    "REASON": "막힌 이유가 달라졌습니다.",
    "OTHER": "그림이나 제안 상자가 달라졌습니다.",
    # NOT A GUESS. Rows answered before these two columns existed have no
    # record of what the question looked like, and naming a part that moved
    # would be inventing one. Saying so costs a line; saying the wrong thing
    # costs the person's trust in every other line on the card.
    "UNKNOWN": "무엇이 달라졌는지는 기록이 없습니다 — 이 안내가 생기기 전에 "
               "답하신 행입니다.",
}


def ask_again_why(fields, was_window, was_reason):
    """Which part of the question moved since they answered, in their words."""
    if was_reason and was_reason != reason_key(fields):
        return ASK_AGAIN_WHY["REASON"]
    if was_window == "-" and window_flag(fields) == "W":
        return ASK_AGAIN_WHY["WINDOW"]
    if not was_window and not was_reason:
        return ASK_AGAIN_WHY["UNKNOWN"]
    return ASK_AGAIN_WHY["OTHER"]


def readable_number(text):
    """Whether a typed figure number is one the run could actually store."""
    import apply_validated                                        # noqa: E402
    return bool(apply_validated.figure_number(text)[0])


def number_refused(text):
    """Why a typed figure number could not be stored, or "" if it could."""
    import apply_validated                                        # noqa: E402
    return apply_validated.figure_number(text)[1]


def answered(q):
    """Whether this returned row carries an answer at all.

    A NUMBER NOBODY CAN STORE IS NOT AN ANSWER. Counting it as one marks the
    question answered, and the row then leaves the queue while it is still
    blocked and still has no number - it disappears with no verdict and
    nobody is ever asked again. Somebody typing `x` in the number box is
    saying they have nothing to pick, which is a verdict, and a verdict is
    theirs to enter on the card.
    """
    if (q.get("Human_Choice") or "").strip():
        return True
    return readable_number((q.get(HUMAN_NUMBER) or "").strip())


def question_key(fields):
    """A short digest of what a person is being asked about this row."""
    reason = _reason_of(fields)
    raw = "|".join([reason] + [str(fields.get(k) or "").strip() for k in (
        "Crop_SHA256", "Proposal_Figure_BBox", "PDF_BBox", "Raster_BBox")])
    # Not the pages themselves - whether the card could show the document at
    # all. Gaining that window is a new question; the window growing is not.
    raw += "|" + ("W" if str(fields.get(NEIGHBOURS) or "").strip() else "-")
    # AND A FIELD THE CARD DID NOT USED TO HAVE. A row that could only be
    # drawn on, and can now also be numbered, is being asked something new -
    # the reason string is unchanged, so without this the person who answered
    # it before never sees the field that was added for them.
    #
    # ONLY WHEN THERE IS ONE. Appending an empty marker unconditionally would
    # change the key of every row in the corpus at once, and eleven rows that
    # nobody can do anything about - and that this person had already been
    # shown - came back into the queue on the first try. A component that
    # fires for rows it does not describe is not a key, it is a reset.
    if str(fields.get("Number_Would_Open") or "").strip() == "1":
        raw += "|N"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


#: How far from the caption's page the decision page will show. It began at
#: one page either side, because the fifteen cases that prompted it were all
#: next door. Then a person answering 210 rows said: "if you cannot find it,
#: let me look through the whole paper." Most papers here are under 25 pages,
#: so this window IS the whole paper for them; the one 374-page book gets a
#: window around the caption instead of nothing.
PAGE_WINDOW = 12

#: `build_sheet2.py` writes this beside the draft: what the sheet blocked, why,
#: and whether a hand-drawn box would clear it. The blocked queue reads it
#: rather than deciding again - `queue()` below calls the rule with a blank key
#: and no census, which is a PARTIAL view, and the two disagreeing is how ten
#: rows once got asked about and then ignored.
BLOCK_REASONS = "block_reasons.csv"

#: Where a box the person drew THEMSELVES is carried. `Human_Choice = DRAWN`
#: is the only choice that names a box no detector proposed, so it is the only
#: one needing a column of its own; the other three name a column already here.
HUMAN_BOX = "Human_Box"

#: What `Agreement` said before a person blocked the row. Without it BLOCKED is
#: a one-way door: on 2026-09-02 ten rows were blocked, eight of them pages
#: with a real figure on them, and nothing in the harness could ask again.
BLOCKED_FROM = "Blocked_From"

#: Where a refused answer is written down. A refusal is not a deletion: the
#: person answered, the answer could not be applied to the picture in front of
#: them any more, and the row therefore has an unanswered question on it - even
#: if the machines have since agreed among themselves. Without this the row
#: leaves the queue on machine authority alone, which is exactly what happened
#: to 10 rows on 2026-09-02: 3 of them the machine had placed somewhere the
#: person had NOT pointed, and nobody would have been asked again.
STALE_CHOICE, STALE_REASON = "Stale_Choice", "Stale_Reason"


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
        if not reg:
            continue
        # A refused answer puts the row back, whatever the machines now say.
        pending = bool((reg.get(STALE_CHOICE) or "").strip())
        if not pending and reg.get("Agreement") in COUNTABLE:
            continue
        # A blocked row stays out of the queue only while the person's answer
        # still SAYS blocked. Clearing `Human_Choice` - what `reopen` does -
        # puts the question back on the page.
        if (not pending and reg.get("Agreement") == "HUMAN_BLOCKED"
                and (reg.get("Human_Choice") or "").strip().upper() == "BLOCKED"):
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
            "Crop_SHA256": _sha(crop) if os.path.isfile(crop) else "",
            "Human_Choice": reg.get("Human_Choice", ""),
            HUMAN_BOX: reg.get(HUMAN_BOX, ""),
            "Human_Note": "", "Agent_Choice": reg.get("Agent_Choice", ""),
            "Agent_Note": "",
            STALE_CHOICE: reg.get(STALE_CHOICE, ""),
            STALE_REASON: reg.get(STALE_REASON, ""),
        })
    out.sort(key=lambda r: (r["Agreement"], r["Source_Document_ID"], r["Draft_ID"]))
    for i, r in enumerate(out, 1):
        r["No"] = i
        r["Sheet"] = "review_%02d.png" % ((i - 1) // PER_SHEET + 1)
    return out


def neighbours(row, run, window=None):
    """Pages of this row's document near the caption, with their sizes.

    THE SIZE COMES FROM THE RASTER, NOT FROM THIS ROW. The intake renders a
    whole document at one scale (2.778 px/pt in run2, 98 documents of 98), but
    one document in run2 has pages of two different sizes - so the neighbour's
    size in points is its raster's pixels over the document's scale, never
    this page's size copied across. `apply_validated` derives it the same way
    and cross-checks it against the PDF before moving a row.
    """
    from PIL import Image
    raster = str(row.get("Page_Raster") or "")
    try:
        page = int(str(row.get("Page") or "").strip())
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except (KeyError, ValueError):
        return ""
    if not raster or not os.path.exists(raster) or pw <= 0 or ph <= 0:
        return ""
    im = Image.open(raster)
    scale = im.width / pw
    out = []
    reach = PAGE_WINDOW if window is None else window
    for other in range(page - reach, page + reach + 1):
        if other < 1 or other == page:
            continue
        path = roundtrip.sibling_raster(raster, other)
        if not path:
            continue
        o = Image.open(path)
        out.append("%d:%.1fx%.1f" % (other, o.width / scale, o.height / scale))
    return ";".join(out)


def blocked(run):
    """Every row the sheet blocked, with the sheet's own reason attached.

    A person may draw a box on any of them. Some reasons a box cannot answer -
    a caption whose figure number was never read, a row the machine marked
    confidence zero - and those rows carry `Box_Would_Open = 0` so the page can
    say so instead of asking for work that will change nothing.
    """
    path = os.path.join(run, BLOCK_REASONS)
    if not os.path.exists(path):
        raise SystemExit(
            "%s가 없습니다 — 먼저 build_sheet2.py를 돌려 시트가 무엇을 막았는지 "
            "적게 하십시오. 이 파일 없이 목록을 다시 계산하면 시트와 다른 답이 "
            "나옵니다." % path)
    said = {r["Draft_ID"]: r for r in csv.DictReader(io.open(path, encoding="utf-8"))}
    draft = list(csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8")))
    regions = {r["Draft_ID"]: r for r in csv.DictReader(io.open(
        os.path.join(run, "validated_regions.csv"), encoding="utf-8"))}
    missing = [d["Draft_ID"] for d in draft if d["Draft_ID"] not in said]
    if missing:
        raise SystemExit("막힌 사유 표에 없는 초안 행 %d개 (예: %s) — 표가 이 "
                         "초안보다 오래됐습니다" % (len(missing), missing[0]))
    out = []
    settled = 0
    for d in draft:
        say = said[d["Draft_ID"]]
        if say["Count_Blocked"] != "1":
            continue
        # A DUPLICATE IS NOT A QUESTION. The sheet says another row holds
        # this figure; nothing a person does on THIS row changes that - if
        # they disagree, they block the winner, and its card is where that
        # happens. Asking here sent 16 rows in 47 back to a person who had
        # already drawn the figure, to draw it again, to be told again.
        # Read from the sheet's own column, not from the shape of its prose.
        if (say.get("Duplicate_Of") or "").strip():
            settled += 1
            continue
        reg = regions.get(d["Draft_ID"], {})
        crop = os.path.join(run, d.get("Figure_Crop") or "")
        out.append({
            "Draft_ID": d["Draft_ID"], "Source_Document_ID": d["Source_Document_ID"],
            "Page": d["Page"], "Figure_Number": d["Figure_Number"],
            "Agreement": reg.get("Agreement", ""),
            "PDF_Code": reg.get("PDF_Code", ""), "Raster_Code": reg.get("Raster_Code", ""),
            "Proposal_Figure_BBox": d.get("Figure_BBox", ""),
            "PDF_BBox": reg.get("PDF_BBox", ""), "Raster_BBox": reg.get("Raster_BBox", ""),
            "Crop_SHA256": _sha(crop) if os.path.isfile(crop) else "",
            "Human_Choice": reg.get("Human_Choice", ""),
            HUMAN_BOX: reg.get(HUMAN_BOX, ""),
            "Human_Note": "", "Agent_Choice": reg.get("Agent_Choice", ""),
            "Agent_Note": "",
            STALE_CHOICE: reg.get(STALE_CHOICE, ""),
            STALE_REASON: reg.get(STALE_REASON, ""),
            "Block_Reason": say.get("Reason", ""),
            "Box_Would_Open": say.get("Box_Would_Open", ""),
            "Number_Would_Open": say.get("Number_Would_Open", ""),
            "Mentions_Held": say.get("Mentions_Held", ""),
            HUMAN_NUMBER: reg.get(HUMAN_NUMBER, ""),
            # AND WHY IT WAS NOT TAKEN, if it was not. `apply_validated`
            # refuses a number it cannot read **by name** - and said so to a
            # terminal nobody reading these cards will ever see. Somebody
            # typed `x` for "there is nothing here to pick"; the run refused
            # it, kept asking, and never told them why. A refusal that does
            # not reach the person is the same as no refusal.
            "Number_Refused": number_refused(reg.get(HUMAN_NUMBER, "")),
            HUMAN_PAGE: reg.get(HUMAN_PAGE, ""),
            # 이 캡션에 보여 줄 그림이 이 쪽에 없을 때 문서의 다른 쪽을 싣습니다.
            # 그런 경우는 둘입니다: 어느 탐지기도 상자를 내지 못했거나, 탐지기가
            # 낸 상자를 사람이 보고 "어느 것도 그림이 아니다"라고 했거나.
            #
            # 처음에는 `Agreement == "NONE"`으로 걸렀는데, 사람이 막은 행은 그때
            # `HUMAN_BLOCKED`가 되므로 **다시 봐야 할 바로 그 행들이** 창을 받지
            # 못했습니다. 2026-09-03에 84행을 다시 돌려받았을 때, 막힌 46행 중
            # 창을 받은 행은 0이었습니다. 사람이 그대로 말했습니다: "내가 여전히
            # 막은 것은, 해당 페이지에 그림이 없고, 전체 페이지를 여기서 확인할
            # 수 없는 경우야."
            NEIGHBOURS: neighbours(d, run) if (
                say.get("Box_Would_Open") == "1"
                and (not ((reg.get("PDF_BBox") or "").strip()
                          or (reg.get("Raster_BBox") or "").strip())
                     or reg.get("Agreement") == "HUMAN_BLOCKED")) else "",
        })
    # 이미 답한 질문은 다시 묻지 않습니다. 답할 때와 지금이 같은 질문이면
    # 빼고, 달라졌으면 무엇이 달라졌는지 적어 돌려보냅니다.
    kept = []
    for r in out:
        was = (regions.get(r["Draft_ID"], {}) or {}).get(ANSWERED_KEY, "")
        now = question_key(r)
        if was and was == now:
            continue
        if was:
            r["Block_Reason"] = ASK_AGAIN + r["Block_Reason"]
            reg = regions.get(r["Draft_ID"], {}) or {}
            r["Ask_Again_Why"] = ask_again_why(
                r, reg.get(ANSWERED_WINDOW, ""), reg.get(ANSWERED_REASON, ""))
        kept.append(r)
    out = kept
    # 상자로 풀리는 행을 앞에, 그 안에서는 문서별로 - 사람이 같은 논문을 잇달아
    # 보게 되고, 헛수고가 될 행은 뒤로 갑니다.
    out.sort(key=lambda r: (r["Box_Would_Open"] != "1"
                            and r["Number_Would_Open"] != "1",
                            r["Source_Document_ID"], r["Draft_ID"]))
    for i, r in enumerate(out, 1):
        r["No"] = i
        r["Sheet"] = "blocked_%02d.png" % ((i - 1) // PER_SHEET + 1)
    blocked.settled = settled
    return out


def write_queue(rows, path):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in FIELDS} for r in rows])
    return path


def make_blocked(run, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = blocked(run)
    path = write_queue(rows, os.path.join(out_dir, "review_queue.csv"))
    helps = sum(1 for r in rows if r["Box_Would_Open"] == "1")
    again = sum(1 for r in rows if r["Block_Reason"].startswith(ASK_AGAIN))
    print("물어볼 행 %d (상자로 풀리는 행 %d · 안 풀리는 행 %d · 그중 다시 묻는 "
          "행 %d) · 묻지 않는 중복 %d · %s"
          % (len(rows), helps, len(rows) - helps, again,
             getattr(blocked, "settled", 0), path))
    return 0


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


#: Which box each choice names. A choice is a statement about ONE of the three
#: boxes, so it is that box - not all three - whose change invalidates it.
CHOICE_BOX = {"TEXT": "Proposal_Figure_BBox", "PDF": "PDF_BBox",
              "RASTER": "Raster_BBox", "DRAWN": HUMAN_BOX}


def already_applied(queue_row, draft_row):
    """True when the crop is ALREADY cut from the box this answer names.

    Applying an answer recuts the crop, which changes its digest - so an
    answer re-merged after `apply_validated` would look stale against the very
    change it caused. A choice whose box is the draft's box is not stale: it
    is done. (This is the ordinary flow only when a file is merged twice; the
    first merge always runs before the recut.)
    """
    choice = (queue_row.get("Human_Choice") or "").strip().upper()
    column = CHOICE_BOX.get(choice)
    if column is None or not draft_row:
        return False
    box = (queue_row.get(column) or "").strip()
    return bool(box) and box == (draft_row.get("Figure_BBox") or "").strip()


def stale(queue_row, region_row, crop_sha):
    """Why this answer is no longer about what the person saw, or ''.

    TWO THINGS CAN GO STALE, and the first version only checked one. The crop
    digest catches a picture that was recut under the answer. It does NOT
    catch a proposer that improved: after the PDF fix, 6 of the 48 rows in the
    first returned file had a different blue box than the one on screen when
    somebody chose, and merge would have applied a choice to a box nobody had
    looked at. The box a choice NAMES is compared too - only that one, because
    "the green box is the figure" stays true however the blue box moved.
    """
    choice = (queue_row.get("Human_Choice") or "").strip().upper()
    if not choice:
        return ""
    # A DRAWN answer describes THE PAGE, and no tool here rewrites a page
    # raster. Neither a recut crop nor a proposer that improved can make it
    # wrong, so neither refuses it - refusing would throw away the one answer
    # that cost the person a hand. What CAN be wrong is that no box came with
    # it, and that is said by name rather than passed through as an answer.
    if choice == "DRAWN":
        if not (queue_row.get(HUMAN_BOX) or "").strip():
            return "직접 그림으로 표시됐는데 그린 상자가 비어 있음"
        page = (queue_row.get(HUMAN_PAGE) or "").strip()
        if page and not page.isdigit():
            return "그린 쪽 번호를 읽을 수 없음 (%r)" % (page,)
        return ""
    if queue_row.get("Crop_SHA256") and queue_row["Crop_SHA256"] != crop_sha:
        return "판정한 크롭과 지금 크롭이 다름 - 다시 봐야 함"
    column = CHOICE_BOX.get(choice)
    if column is None:                     # BLOCKED names no box
        return ""
    was, now = queue_row.get(column, ""), (region_row or {}).get(column, "")
    if was != now:
        return ("고른 %s 상자가 판정할 때와 다름 (%s → %s) - 다시 봐야 함"
                % (choice, was or "빈칸", now or "빈칸"))
    return ""


def merge(run, queue_path):
    regions_path = os.path.join(run, "validated_regions.csv")
    with io.open(regions_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        regions, cols = list(reader), list(reader.fieldnames)
    for col in ("Human_Choice", HUMAN_BOX, HUMAN_PAGE, "Human_Note",
                "Agent_Choice", "Agent_Note", STALE_CHOICE, STALE_REASON,
                BLOCKED_FROM, ANSWERED_KEY, DUPLICATE_OF, DUPLICATE_PAGE,
                HUMAN_NUMBER, ANSWERED_WINDOW, ANSWERED_REASON):
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
        now = _sha(crop) if os.path.isfile(crop) else ""
        why = "" if already_applied(q, draft.get(q["Draft_ID"])) else stale(q, reg, now)
        if why:
            refused.append((q["Draft_ID"], why))
            reg[STALE_CHOICE] = (q.get("Human_Choice") or "").strip().upper()
            reg[STALE_REASON] = why
            continue
        changed = False
        for col in ("Human_Choice", HUMAN_BOX, HUMAN_PAGE, "Human_Note",
                    "Agent_Choice", "Agent_Note", HUMAN_NUMBER):
            v = (q.get(col) or "").strip()
            if v and reg.get(col, "") != v:
                reg[col] = v
                changed = True
        # An answer that lands clears the refusal it replaces - and the
        # duplicate the previous answer may have been found to be. What this
        # answer turns out to be is for `apply_validated` to decide again.
        # A SUPPLIED NUMBER IS AN ANSWER TOO, with or without a choice: eight
        # rows are blocked only because nobody could read the figure number,
        # and one of them needs nothing else.
        if answered(q):
            if reg.get(STALE_CHOICE) or reg.get(STALE_REASON):
                reg[STALE_CHOICE] = reg[STALE_REASON] = ""
                changed = True
            if reg.get(DUPLICATE_OF) or reg.get(DUPLICATE_PAGE):
                reg[DUPLICATE_OF] = reg[DUPLICATE_PAGE] = ""
                changed = True
            # AND RECORDS WHAT THEY WERE ANSWERING, so the same question is
            # not put to them again. Taken from the queue row they sent back -
            # the state on their screen - not from the run as it is now.
            key = question_key(q)
            if reg.get(ANSWERED_KEY, "") != key:
                reg[ANSWERED_KEY] = key
                changed = True
            # AND THE TWO PARTS A PERSON CAN RECOGNISE, so that if this row
            # does come back the card can say which one moved.
            for col, value in ((ANSWERED_WINDOW, window_flag(q)),
                               (ANSWERED_REASON, reason_key(q))):
                if reg.get(col, "") != value:
                    reg[col] = value
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


def reopen(run, ids):
    """Undo a block: the row loses its BLOCKED answer and returns to the queue.

    THIS IS NOT A VERDICT. It restores the `Agreement` the detectors had
    reached before the person blocked the row - never a countable one, because
    a row is only ever blocked from an uncountable state - and empties
    `Human_Choice` so the question is asked again. Nothing becomes countable
    here; the person decides that on the page, as before.
    """
    regions_path = os.path.join(run, "validated_regions.csv")
    with io.open(regions_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        regions, cols = list(reader), list(reader.fieldnames)
    for col in ("Human_Choice", HUMAN_BOX, HUMAN_PAGE, BLOCKED_FROM):
        if col not in cols:
            cols.append(col)
    by_id = {r["Draft_ID"]: r for r in regions}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit("검증표에 없는 행: %s" % ", ".join(unknown[:5]))
    done, left = [], []
    for i in ids:
        reg = by_id[i]
        if reg.get("Agreement") != "HUMAN_BLOCKED":
            left.append((i, "막힌 행이 아님 (%s)" % reg.get("Agreement")))
            continue
        was = (reg.get(BLOCKED_FROM) or "").strip()
        if was in COUNTABLE:
            # Restoring a countable agreement would make the row count again
            # without anybody looking - the opposite of asking the question.
            left.append((i, "막기 전 상태가 %s여서 되돌리면 세어짐 - 손대지 않음" % was))
            continue
        reg["Agreement"] = was or "NONE"
        reg["Human_Choice"] = ""
        reg[HUMAN_PAGE] = ""
        reg[BLOCKED_FROM] = ""
        done.append(i)
    tmp = regions_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in regions])
    os.replace(tmp, regions_path)
    print("되돌린 행 %d · 손대지 않은 행 %d" % (len(done), len(left)))
    for did, why in left:
        print("  그대로 %s: %s" % (did, why))
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "blocked":
        sys.exit(make_blocked(sys.argv[2], sys.argv[3]))
    if sys.argv[1] == "reopen":
        sys.exit(reopen(sys.argv[2], sys.argv[3:]))
    if sys.argv[1] == "make":
        sys.exit(make(sys.argv[2], sys.argv[3]))
    if sys.argv[1] == "merge":
        sys.exit(merge(sys.argv[2], sys.argv[3]))
    raise SystemExit(__doc__)
