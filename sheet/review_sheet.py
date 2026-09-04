# -*- coding: utf-8 -*-
"""The 149 rows nobody's second method confirmed, as a page a person decides on.

    python3 review_sheet.py <run dir> [out dir]

`review_packet.py make` writes the queue and the contact sheets that go with
it; those sheets are for reading. This is for DECIDING: one card per queued
row, carrying

    the page with all three boxes drawn   red = TEXT (the crop now),
                                          blue = PDF objects, green = raster ink
    what each box would actually cut      the same three, side by side, cut
                                          with the intake's own formula
    four buttons                          TEXT · PDF · RASTER · BLOCKED

and an export that `review_packet.py merge` reads back.

WHY THE CUT PICTURES ARE HERE. The boxes on the page say where each method
points; they do not say what a person would be counting panels in. Two boxes
that look alike on a 900px page view can differ by a whole panel row, and the
only way to see that is to look at what each one cuts. They are made with
`roundtrip.cut`, so what this page shows is what `apply_validated.py` will
write - not an approximation of it.

WHAT THIS PAGE WILL NOT DO. It does not preselect anything, including the
agent's own proposal: that is behind a toggle, off by default, because a
choice shown next to an empty button is not a blank page. Nothing is stored
against a row whose crop or boxes have changed since the page was built - the
fingerprint carries them, so a stale answer is dropped rather than applied to
a picture nobody looked at.
"""
import base64
import csv
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roundtrip                                                 # noqa: E402

#: The choices, in the order the buttons and the keyboard use them.
#:
#: DRAWN IS NOT A PROPOSER. The first three are answers to "which of these
#: three is the figure"; DRAWN is what a person says when the honest answer is
#: "none of them, and it is HERE" - they drag a box on the page themselves.
#: It exists because BLOCKED was carrying that meaning too, and blocking a
#: page that has a figure on it throws the figure away to record a detector's
#: failure. BLOCKED now means only what it says: nothing here to count.
CHOICES = [("TEXT", "빨강 — 지금 크롭", "1", "#c42020"),
           ("PDF", "파랑 — PDF 객체", "2", "#0050eb"),
           ("RASTER", "초록 — 래스터 잉크", "3", "#00962a"),
           ("DRAWN", "보라 — 내가 그린 상자", "4", "#8800cc"),
           ("BLOCKED", "막음 — 셀 그림이 없음", "0", "#6b6b6b")]
#: The three the detectors propose - what gets drawn on the page and cut.
PROPOSERS = CHOICES[:3]
BOX_COLUMN = {"TEXT": "Proposal_Figure_BBox", "PDF": "PDF_BBox",
              "RASTER": "Raster_BBox"}
PAGE_WIDTH = int(os.environ.get("FDT_REVIEW_PAGE_WIDTH", "900"))
#: The pages a person LEAFS THROUGH looking for a figure, narrower than the
#: caption's own page. A document window of 25 pages costs 25 page images per
#: card, and at the caption page's width 47 cards came to 126 MB - a file that
#: opens slowly enough to be its own obstacle. Narrower costs nothing that
#: matters here: the drawn box is measured in POINTS from where the pointer
#: sits over the displayed image, so its precision is the page's size on
#: screen, not the raster's. A blurrier page is still a page you can find a
#: figure on and drag across.
WINDOW_WIDTH = int(os.environ.get("FDT_REVIEW_WINDOW_WIDTH", "640"))
CUT_WIDTH = int(os.environ.get("FDT_REVIEW_CUT_WIDTH", "460"))
BUDGET = int(os.environ.get("FDT_REVIEW_BUDGET", str(17 * 1024 * 1024)))


def esc(text):
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;"))


def _uri(image, width, quality):
    from PIL import Image
    if image.width > width:
        image = image.resize((width, max(1, round(image.height * width / image.width))),
                             Image.LANCZOS)
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _box(text):
    try:
        x0, y0, x1, y1 = [float(v) for v in str(text).split(",")]
    except ValueError:
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def page_image(row):
    """The page raster, CLEAN - no box burned into it.

    The boxes used to be drawn into this JPEG, which put them inside the
    preview of the hand-drawn crop as well: a person judging "does my box
    catch the figure" was looking at red, blue and green lines that the real
    crop will not contain, over the part of the picture they were judging.
    The preview cuts from this image, so this image has to be the page and
    nothing else; the boxes go on top as an overlay (`box_overlays`).
    """
    from PIL import Image
    raster = row.get("Page_Raster") or ""
    if not raster or not os.path.exists(raster):
        return ""
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except (KeyError, ValueError):
        return ""
    if pw <= 0 or ph <= 0:
        return ""
    return _uri(Image.open(raster).convert("RGB"), PAGE_WIDTH, 75)


def neighbour_pages(row, queue_row):
    """[(page, uri, pw, ph, fingerprint)] for the pages the queue offers.

    Embedded like the caption page, so the file stays self-contained - a
    person opens these from wherever they saved them, and a picture that
    loads only from one folder is a picture that is sometimes not there.
    Offered only on rows where `review_packet.blocked` said it is plausible
    that the figure is next door; everywhere else this is empty and the card
    has no page buttons.
    """
    from PIL import Image
    spec = (queue_row.get("Neighbours") or "").strip()
    raster = row.get("Page_Raster") or ""
    if not spec or not raster:
        return []
    out = []
    for item in spec.split(";"):
        try:
            page, size = item.split(":")
            pw, ph = [float(v) for v in size.split("x")]
            page = int(page)
        except ValueError:
            continue
        path = roundtrip.sibling_raster(raster, page)
        if not path or pw <= 0 or ph <= 0:
            continue
        fp = page_fingerprint({"Page_Raster": path, "Page_Width_Pt": "%.1f" % pw,
                               "Page_Height_Pt": "%.1f" % ph})
        out.append((page, _uri(Image.open(path).convert("RGB"), WINDOW_WIDTH, 72),
                    pw, ph, fp))
    return out


def box_overlays(row, queue_row):
    """Each proposer's box as a positioned outline over the page image."""
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except (KeyError, ValueError):
        return ""
    if pw <= 0 or ph <= 0:
        return ""
    out = []
    for name, _label, _key, colour in PROPOSERS:
        box = _box(queue_row.get(BOX_COLUMN[name]))
        if not box:
            continue
        out.append(
            "<div class='pbox' data-box='%s' style='border-color:%s;"
            "left:%.3f%%;top:%.3f%%;width:%.3f%%;height:%.3f%%'></div>"
            % (name, colour, box[0] / pw * 100, box[1] / ph * 100,
               (box[2] - box[0]) / pw * 100, (box[3] - box[1]) / ph * 100))
    return "".join(out)


def cut_for(row, box_text):
    """What `apply_validated` would write for this box, or None."""
    from PIL import Image
    raster = row.get("Page_Raster") or ""
    if not raster or not os.path.exists(raster):
        return None
    # An empty or unparseable box is `roundtrip.cut`'s own answer (None), and
    # a second check here would be one no scenario could fail. What this
    # function must not do is cut differently from the intake - that is what
    # the scenario holds it to.
    got = roundtrip.cut(Image.open(raster), dict(row, Figure_BBox=box_text))
    return got[0] if got else None


def fingerprint(queue_row):
    """What this card SHOWS, so a stored answer cannot outlive it."""
    raw = "|".join([queue_row["Draft_ID"], queue_row.get("Crop_SHA256", ""),
                    queue_row.get("Proposal_Figure_BBox", ""),
                    queue_row.get("PDF_BBox", ""), queue_row.get("Raster_BBox", "")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def page_fingerprint(row):
    """What a DRAWN answer is about: the page, not the proposals.

    A box a person drags is a statement about the page raster and nothing
    else. Binding it to `fingerprint()` would throw it away every time a
    detector improved - discarding the one answer that cost a hand to make,
    for a change that cannot affect it. So it is bound to the page instead,
    and it survives exactly as long as the picture it was drawn on.
    """
    raster = str(row.get("Page_Raster") or "")
    size = os.path.getsize(raster) if raster and os.path.exists(raster) else -1
    raw = "|".join([raster, str(size), str(row.get("Page_Width_Pt", "")),
                    str(row.get("Page_Height_Pt", ""))])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


#: Which queue this page is built from. The default is the review packet's;
#: `review_packet.py blocked` writes another one - every row the sheet refused
#: - and this is how that one gets in without a second copy of the builder.
QUEUE_PATH = os.environ.get("FDT_REVIEW_QUEUE", "")


def build(run, out_dir, queue_path=None):
    roundtrip.selfcheck(run)
    queue_path = (queue_path or QUEUE_PATH
                  or os.path.join(run, "review", "review_queue.csv"))
    if not os.path.exists(queue_path):
        raise SystemExit("판정할 큐가 없습니다: %s" % queue_path)
    with io.open(queue_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        queue, columns = list(reader), list(reader.fieldnames)
    draft = {d["Draft_ID"]: d for d in csv.DictReader(io.open(
        os.path.join(run, "figure_intake_draft.csv"), encoding="utf-8"))}
    os.makedirs(out_dir, exist_ok=True)

    ident = hashlib.sha256()
    for path in (queue_path, os.path.join(HERE, "review_sheet.py")):
        ident.update(os.path.basename(path).encode("utf-8"))
        ident.update(io.open(path, "rb").read())
    build_id = "review-%s" % ident.hexdigest()[:10]

    cards = []
    for q in queue:
        row = draft.get(q["Draft_ID"])
        if row is None:
            continue
        page = page_image(row)
        overlays = box_overlays(row, q)
        others = neighbour_pages(row, q)
        try:
            this_page = int(str(q.get("Page") or "").strip())
        except ValueError:
            this_page = 0
        # Every page the card can show, with what a box on it is bound to.
        # The caption page is first and is the one the file starts on.
        pages_js = [{"page": this_page, "pw": row.get("Page_Width_Pt", ""),
                     "ph": row.get("Page_Height_Pt", ""),
                     "pfp": page_fingerprint(row), "caption": True}]
        pages_js += [{"page": p, "pw": "%.1f" % pw, "ph": "%.1f" % ph,
                      "pfp": fp, "caption": False} for p, _u, pw, ph, fp in others]
        page_nav = ""
        if others:
            # THE WHOLE PAPER, not just next door. With up to 25 pages the
            # buttons are page numbers, in reading order, with the caption's
            # own page marked - a strip a person scans rather than a sentence
            # they read.
            seen = sorted([p for p, _u, _pw, _ph, _fp in others] + [this_page])
            page_nav = ("<div class='pagenav'>"
                        "<span class='navhint'>이 쪽에서 그림을 찾지 못했습니다 — "
                        "문서의 다른 쪽을 넘겨 보고 그리십시오:</span>"
                        "<span class='strip'>"
                        + "".join(
                            "<button type='button' class='goto%s' data-page='%d'>%s</button>"
                            % (" cap" if p == this_page else "", p,
                               ("캡션 p.%d" % p) if p == this_page else str(p))
                            for p in seen)
                        + "</span></div>")
        hidden_pages = "".join(
            "<img class='page other' data-page='%d' src='%s' alt='' hidden>" % (p, u)
            for p, u, _pw, _ph, _fp in others)
        shots = []
        for name, label, key, colour in PROPOSERS:
            box_text = q.get(BOX_COLUMN[name])
            cut = cut_for(row, box_text) if box_text else None
            shots.append((name, label, colour,
                          _uri(cut, CUT_WIDTH, 72) if cut is not None else ""))
        fp = fingerprint(q)
        pfp = page_fingerprint(row)
        buttons = "".join(
            "<button type='button' class='pick' data-id='%s' data-choice='%s' "
            "style='--c:%s'%s>%s <kbd>%s</kbd></button>"
            % (esc(q["Draft_ID"]), name, colour,
               # NOTHING TO DRAW ON, NOTHING TO DRAW: the drawing button is
               # dead until this card actually holds a box, so it can never be
               # an answer that names nothing.
               " disabled" if name == "DRAWN" else "", esc(label), key)
            for name, label, key, colour in CHOICES)
        cuts = "".join(
            "<figure class='cut'%s><figcaption style='color:%s'>%s</figcaption>%s</figure>"
            % (" data-empty='1'" if not uri else "", colour, esc(label),
               ("<img src='%s' alt=''>" % uri) if uri
               else "<div class='none'>이 방법은 이 캡션에 답하지 않았습니다</div>")
            for name, label, colour, uri in shots)
        page_block = (
            "%s<div class='pagewrap'><img class='page' data-page='%d' src='%s' alt=''>"
            "%s%s<div class='drawn' hidden></div></div>"
            "<p class='hint'>세 방법이 다 그림을 못 잡았으면 "
            "<b>페이지 위를 끌어</b> 상자를 직접 그리십시오 (보라).</p>"
            "<figure class='mine' hidden><figcaption>내가 그린 상자 "
            "<span class='px'></span> "
            "<button type='button' class='erase'>지우기</button></figcaption>"
            "<canvas></canvas>"
            "<div class='caveat'>이 미리보기는 화면에 보이는 축소된 페이지에서 "
            "잘라낸 것입니다. 실제 크롭은 원본 해상도에서, 바깥의 빈 여백을 "
            "털어낸 뒤 다시 잘립니다.</div></figure>"
            % (page_nav, this_page, page, hidden_pages, overlays)) if page else \
            "<div class='none'>페이지 이미지가 없습니다</div>"
        # WHY THIS ROW IS HERE. A blocked row is not a row with a hard
        # question about which box is right; it is a row the sheet refused,
        # and the person needs to see WHAT it refused before deciding. When a
        # box cannot answer the refusal - no figure number was read, the
        # machine called its own confidence zero - the card says so rather
        # than letting somebody drag a rectangle for nothing.
        why = (q.get("Block_Reason") or "").strip()
        helps = (q.get("Box_Would_Open") or "").strip() == "1"
        # A ROW CAN NEED A NUMBER AS WELL AS A BOX, and seven of the eight
        # rows the machine could not number also need one. Until this field
        # existed the card said "a box will not help" and offered nothing
        # else; the person answered anyway - once in the free-text note, once
        # by picking a proposer - and neither could reach `Figure_Number`.
        needs_number = (q.get("Number_Would_Open") or "").strip() == "1"
        block_block = ("<div class='why %s'><b>막힌 이유</b> %s%s</div>"
                       % ("helps" if (helps or needs_number) else "nohelp",
                          esc(why),
                          ("" if helps or needs_number else
                           " <b>— 상자를 그려도 이 이유는 풀리지 않습니다.</b>")
                          + (" <b>— 그림 번호를 적어 주십시오%s.</b>"
                             % ("(상자도 함께 그려야 합니다)" if helps else "")
                             if needs_number else ""))) if why else ""
        # WHAT THE HARNESS ALREADY KNOWS ABOUT THIS LINE. Not a verdict - the
        # person still decides - but eight rows arrived with "supply the
        # figure number" and nothing else, and every one of them named
        # figures this document had already counted. Saying so is the
        # difference between a question and a riddle.
        held = [p.split("=", 1) for p in
                (q.get("Mentions_Held") or "").split(";") if "=" in p]
        held_block = (
            "<div class='held'><b>이 줄이 부르는 그림</b> — "
            + " · ".join("%s는 <code>%s</code> 행이 이미 세고 있습니다"
                         % (esc(lab), esc(other)) for lab, other in held)
            + ". 이 줄이 그 그림의 캡션이 아니라 본문의 언급이라면 "
              "<b>막음</b>을 고르십시오.</div>") if held else ""
        number_block = (
            "<label class='fignum'>그림 번호 "
            "<input type='text' data-number='%s' maxlength='24' "
            "placeholder='4 · fig4 · Figure 4b' value='%s'></label>"
            % (esc(q["Draft_ID"]), esc(q.get("Human_Figure_Number", "")))
        ) if needs_number else ""
        # 거부는 사람이 보는 자리에 있어야 합니다 - 적어 낸 칸 바로 옆에.
        number_block = ((number_block + "<div class='numbad'>%s</div>"
                         % esc(q.get("Number_Refused")))
                        if (q.get("Number_Refused") or "").strip()
                        and needs_number else number_block)
        # WHY IT CAME BACK. "답하셨을 때와 달라졌습니다" alone made somebody
        # ask what had changed - and the answer, twice, was that blocking the
        # row is what gave it a document window.
        again_block = ("<div class='again'><b>다시 묻는 이유</b> %s</div>"
                       % esc(q.get("Ask_Again_Why"))) if (
            q.get("Ask_Again_Why") or "").strip() else ""
        stale_block = (
            "<div class='stale'>이 행은 전에 <b>%s</b>로 판정하셨는데 "
            "그때의 그림이 바뀌어 반영되지 않았습니다: %s</div>"
            % (esc(q.get("Stale_Choice")), esc(q.get("Stale_Reason")))
        ) if (q.get("Stale_Choice") or "").strip() else ""
        # Named placeholders: this block grew a per-cent sign away from being
        # unreadable, and TAIL already learned that lesson the hard way.
        cards.append((q, fp, CARD % {
            "id": esc(q["Draft_ID"]), "fp": fp, "pfp": pfp,
            "pw": esc(row.get("Page_Width_Pt", "")),
            "ph": esc(row.get("Page_Height_Pt", "")),
            "pages": esc(json.dumps(pages_js)),
            "number": number_block,
            "held": held_block,
            "again": again_block,
            "page_no_int": this_page,
            "no": esc(q["No"]), "doc": esc(q["Source_Document_ID"]),
            "page_no": esc(q["Page"]), "fig": esc(q["Figure_Number"]),
            "agree": esc(q["Agreement"]), "pdf": esc(q["PDF_Code"]),
            "raster": esc(q["Raster_Code"]), "page": page_block, "cuts": cuts,
            "buttons": buttons, "stale": stale_block, "why": block_block,
            "agent_choice": esc(q["Agent_Choice"]),
            "agent_note": esc(q["Agent_Note"])}))

    head = HEAD % {"build": esc(build_id), "n": len(cards)}

    parts, current, size = [], [], 0
    base = len(head.encode("utf-8")) + 4000
    for card in cards:
        html = card[2]
        if current and base + size + len(html.encode("utf-8")) > BUDGET:
            parts.append(current)
            current, size = [], 0
        current.append(card)
        size += len(html.encode("utf-8"))
    if current:
        parts.append(current)

    written = []
    for i, part in enumerate(parts, 1):
        # EACH FILE EXPORTS ITS OWN ROWS AND NO OTHERS. A part carrying the
        # whole queue would export 149 rows from a page showing 41, and a
        # person who filled one file would hold a CSV that looks finished.
        # `%` formatting is not used for the tail: named placeholders survive
        # any per-cent sign the script grows later.
        rows_js = [{"Draft_ID": q["Draft_ID"], "No": q["No"], "fp": fp}
                   for q, fp, _h in part]
        tail = (TAIL.replace("__ROWS__", json.dumps(rows_js, ensure_ascii=False))
                    .replace("__COLUMNS__", json.dumps(columns, ensure_ascii=False))
                    .replace("__QUEUE__",
                             json.dumps({q["Draft_ID"]: q for q, _fp, _h in part},
                                        ensure_ascii=False))
                    .replace("__BUILD__", json.dumps(build_id))
                    .replace("__PARTNO__", json.dumps("%02d" % i)))
        path = os.path.join(out_dir, "review_choose_%02d.html" % i)
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(head.replace("__PART__", "%d / %d — 이 파일 %d행"
                                  % (i, len(parts), len(part))))
            fh.write("".join(h for _q, _fp, h in part))
            fh.write(tail)
        written.append(path)
    for path in written:
        print("%s  %.1f MB" % (path, os.path.getsize(path) / 1e6))
    print("행 %d · 파일 %d · 빌드 %s" % (len(cards), len(written), build_id))
    return 0


CARD = ("<section class='card' data-id='%(id)s' data-fp='%(fp)s' "
        "data-pfp='%(pfp)s' data-pw='%(pw)s' data-ph='%(ph)s' "
        "data-page='%(page_no_int)s' data-pages='%(pages)s' id='r%(no)s'>"
        "<h2><span class='no'>%(no)s</span> %(id)s</h2>"
        "<div class='meta'>%(doc)s · p.%(page_no)s · %(fig)s · 합의 <b>%(agree)s</b> "
        "(PDF %(pdf)s · 래스터 %(raster)s)</div>"
        "%(why)s%(again)s"
        "%(page)s<div class='cuts'>%(cuts)s</div>"
        "<div class='picks'>%(buttons)s</div>"
        "%(held)s%(number)s"
        "<label class='note'>메모 "
        "<input type='text' data-note='%(id)s' maxlength='200'></label>"
        "%(stale)s"
        "<div class='agent' hidden>에이전트 제안: <b>%(agent_choice)s</b> — "
        "%(agent_note)s</div>"
        "<div class='state' data-state='%(id)s'></div></section>")

HEAD = """<!doctype html><html lang='ko'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>그림 영역 판정 — %(n)d행</title><style>
:root{--ink:#1a1917;--mut:#6b665f;--rule:#d8d2c8;--bg:#fbf9f6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:20px 18px 140px}
h1{font-size:19px;margin:0 0 4px}
.lede{color:var(--mut);font-size:13.5px;margin:0 0 18px}
.bar{position:sticky;top:0;z-index:9;background:var(--bg);border-bottom:1px solid var(--rule);
padding:10px 0;margin-bottom:16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.bar button{font:inherit;padding:6px 12px;border:1px solid var(--rule);background:#fff;
border-radius:4px;cursor:pointer}
.bar .count{color:var(--mut);font-size:13.5px}
.card{border:1px solid var(--rule);border-radius:5px;background:#fff;padding:14px;margin:0 0 22px}
.card.done{border-color:#9dc2a2;background:#f6fbf7}
.card.blocked{border-color:#cfcfcf;background:#f6f6f5}
h2{font-size:15px;margin:0 0 3px;font-weight:600}
h2 .no{display:inline-block;min-width:34px;color:var(--mut);font-variant-numeric:tabular-nums}
.meta{color:var(--mut);font-size:12.5px;margin:0 0 10px}
img.page{width:100%%;display:block;border:1px solid var(--rule);background:#fff}
/* `display:block` above would beat the browser's own [hidden] rule, and two
   pages would show stacked - the box then lands on the wrong one. Seen in a
   screenshot after every DOM check had passed. */
img.page[hidden]{display:none}
.pagewrap{position:relative;touch-action:none;cursor:crosshair}
.pagewrap .drawn{position:absolute;border:2px solid #8800cc;
background:rgba(136,0,204,.12);pointer-events:none;box-sizing:border-box}
.pagewrap .pbox{position:absolute;border:2px solid;pointer-events:none;
box-sizing:border-box}
.pagenav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px;
font-size:12.5px;color:#6b4a00;background:#fffaf0;border:1px solid #e8d9b8;
border-radius:3px;padding:6px 9px}
.pagenav .strip{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.pagenav .goto{font:inherit;font-size:12.5px;padding:3px 8px;border:1px solid #d2b878;
background:#fff;border-radius:3px;cursor:pointer;min-width:28px}
.pagenav .goto.cap{font-weight:600}
.pagenav .goto[aria-pressed='true']{background:#8a5a00;color:#fff;border-color:#8a5a00}
.pagewrap .onpage{position:absolute;right:8px;top:8px;font-size:12px;font-weight:600;
color:#fff;background:#8a5a00;border-radius:3px;padding:3px 8px;pointer-events:none}
.hint{color:var(--mut);font-size:12.5px;margin:6px 0 0}
.mine{margin:10px 0 0;border:1px solid #d9b8e8;background:#fbf5fe;
border-radius:4px;padding:9px 10px}
.mine figcaption{font-size:12.5px;font-weight:600;color:#7a1aa0;margin:0 0 6px}
.mine .px{font-weight:400;color:var(--mut)}
.mine canvas{max-width:100%%;display:block;border:1px solid var(--rule);background:#fff}
.mine .caveat{color:var(--mut);font-size:11.5px;margin-top:5px}
.mine .erase{font:inherit;font-size:11.5px;padding:2px 7px;margin-left:6px;
border:1px solid var(--rule);background:#fff;border-radius:3px;cursor:pointer}
.card.drawn-on{border-color:#c79ae0;background:#fdf9ff}
.cuts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:10px 0}
.cut{margin:0}
.cut figcaption{font-size:12px;font-weight:600;margin:0 0 4px}
.cut img{width:100%%;display:block;border:1px solid var(--rule);background:#fff}
.cut .none,.card>.none{color:var(--mut);font-size:12.5px;background:#f4f2ee;
border:1px dashed var(--rule);border-radius:4px;padding:14px;text-align:center}
.picks{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 6px}
.pick{font:inherit;font-size:13.5px;padding:7px 12px;border:1.5px solid var(--rule);
background:#fff;border-radius:4px;cursor:pointer;color:var(--ink)}
.pick:hover{border-color:var(--c)}
.pick[aria-pressed='true']{border-color:var(--c);background:var(--c);color:#fff}
.pick[disabled]{opacity:.42;cursor:not-allowed}
.pick kbd{font:inherit;font-size:11px;opacity:.6;margin-left:4px}
.note{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--mut)}
.again{font-size:12.5px;border-radius:3px;padding:7px 10px;margin:0 0 10px;
       background:#fff6e5;border:1px solid #e3c68a;color:#7a5312}
.held{font-size:12.5px;border-radius:3px;padding:7px 10px;margin:0 0 10px;
      background:#eef4ff;border:1px solid #b9ccef;color:#1c3f7a}
.held code{background:#dce7fb;padding:0 3px;border-radius:2px}
.fignum{display:flex;gap:8px;align-items:center;font-size:12.5px;margin:0 0 8px;
        font-weight:600;color:#8a4b00}
.fignum input{border:2px solid #d98324;border-radius:3px;padding:3px 6px;width:14em}
.numbad{font-size:12.5px;border-radius:3px;padding:6px 9px;margin:-4px 0 10px;
        background:#fdf4f4;border:1px solid #e0bcbc;color:#8a2a2a}
.card.needs-number{border-left:4px solid #d98324}
.note input{flex:1;font:inherit;font-size:13px;padding:5px 7px;
border:1px solid var(--rule);border-radius:3px}
.agent{margin-top:8px;font-size:12.5px;color:#8a5a00;background:#fffaf0;
border:1px solid #e8d9b8;border-radius:3px;padding:6px 9px}
.stale{margin-top:8px;font-size:12.5px;color:#8a2a2a;background:#fdf4f4;
border:1px solid #e0bcbc;border-radius:3px;padding:6px 9px}
.why{font-size:12.5px;border-radius:3px;padding:7px 10px;margin:0 0 10px}
.why b{font-weight:600}
.why.helps{color:#6b4a00;background:#fffaf0;border:1px solid #e8d9b8}
.why.nohelp{color:#5a5a5a;background:#f1f1ef;border:1px solid #d5d5d0}
.card.nohelp-card{opacity:.94}
.warn{background:#fdf4f4;border:1px solid #e0bcbc;border-radius:4px;padding:10px 12px;
margin:0 0 16px;font-size:13.5px}
</style><div class='wrap'>
<h1>그림 영역 판정 <span style='color:var(--mut);font-weight:400'>__PART__</span></h1>
<p class='lede'>두 방법이 서로 확인해 주지 못한 %(n)d행입니다. 빨강은 지금 크롭이 잘린 상자,
파랑은 PDF가 그리는 객체, 초록은 페이지 잉크입니다. 아래 세 그림은 각 상자가
<b>실제로 잘라낼 것</b>입니다. 하나를 고르십시오.
셋 다 그림을 못 잡았으면 <b>페이지 위를 끌어 상자를 직접 그리고</b> 보라를 고르십시오.
그 페이지에 셀 그림이 아예 없을 때만 막음입니다.
빈칸으로 두면 그 행은 막힌 채 남습니다.</p>
<div class='warn' id='warn' hidden></div>
<div class='bar'><button type='button' id='save'>고른 것 CSV로 내려받기</button>
<button type='button' id='next'>다음 빈 행</button>
<button type='button' id='toggle'>에이전트 제안 보기</button>
<span class='count' id='count'></span>
<span class='count'>키보드: 1 빨강 · 2 파랑 · 3 초록 · 4 내가 그린 · 0 막음 · n 다음</span></div>
<div class='build' style='color:var(--mut);font-size:12px;margin:-8px 0 14px'>빌드 %(build)s</div>
"""

TAIL = """</div><script>
const ROWS = __ROWS__, COLUMNS = __COLUMNS__, QUEUE = __QUEUE__, BUILD = __BUILD__;
const PART = __PARTNO__;
const KEY = 'fdt-review-' + BUILD;
const VALID = ['TEXT','PDF','RASTER','DRAWN','BLOCKED'];
const BOXKEY = 'fdt-review-box-' + BUILD;
// A NUMBER IS ITS OWN ANSWER, so it is stored apart from `store`, which
// only ever holds rows that have a choice. Eight rows are blocked only
// because nobody could read the figure number, and one of them needs no
// choice at all - kept inside `store` it could never be given.
const NUMKEY = 'fdt-review-num-' + BUILD;
const warn = document.getElementById('warn');
function complain(text){ warn.textContent = text; warn.hidden = false; }
let store = {};
try {
  const probe = '__fdt__';
  window.localStorage.setItem(probe, '1');
  window.localStorage.removeItem(probe);
  store = JSON.parse(window.localStorage.getItem(KEY) || '{}') || {};
} catch (err) {
  store = {};
  complain('브라우저 저장소를 쓸 수 없어 고른 값이 이 창을 닫으면 사라집니다 (' +
           (err && err.name ? err.name : '알 수 없는 오류') + '). ' +
           '판정을 마치면 CSV로 내려받으십시오.');
}
let boxes = {};
try { boxes = JSON.parse(window.localStorage.getItem(BOXKEY) || '{}') || {}; }
catch (err) { boxes = {}; }
let numbers = {};
try { numbers = JSON.parse(window.localStorage.getItem(NUMKEY) || '{}') || {}; }
catch (err) { numbers = {}; }
function persist(){
  try {
    window.localStorage.setItem(KEY, JSON.stringify(store));
    window.localStorage.setItem(BOXKEY, JSON.stringify(boxes));
    window.localStorage.setItem(NUMKEY, JSON.stringify(numbers));
  }
  catch (err) { complain('저장에 실패했습니다 (' +
    (err && err.name ? err.name : '알 수 없는 오류') + '). CSV로 내려받으십시오.'); }
}
// A stored answer belongs to the pictures it was made on. The fingerprint
// carries the crop digest and all three boxes; if any of them changed, the
// answer is not about what is on screen and is dropped.
const cards = Array.from(document.querySelectorAll('.card'));
const byId = {}; cards.forEach(c => byId[c.dataset.id] = c);
let dropped = 0;
// WHICH FINGERPRINT depends on what the answer is ABOUT. The three proposer
// choices are about the crops and boxes on this card, so they die when those
// change. A hand-drawn box is about the page, which no tool rewrites - it
// dies only when the page does. Using one rule for both would silently throw
// away the answers that took a person the longest to make.
// WHICH PAGE THE CARD IS SHOWING. A card starts on the caption's page; the
// buttons swap in a neighbouring page. A drawn box belongs to the page it was
// drawn on - its coordinates are in that page's points, and its fingerprint
// is that page's - so the box carries its page, and the card follows the box.
function pagesOf(card){
  try { return JSON.parse(card.dataset.pages || '[]'); } catch (e) { return []; }
}
function pageInfo(card, page){
  return pagesOf(card).find(p => String(p.page) === String(page)) || null;
}
function shownPage(card){ return parseInt(card.dataset.page, 10); }
function showPage(card, page){
  const info = pageInfo(card, page);
  if (!info) return;
  card.dataset.page = String(info.page);
  card.dataset.pw = String(info.pw); card.dataset.ph = String(info.ph);
  card.dataset.pfp = info.pfp;
  card.querySelectorAll('img.page').forEach(im => {
    im.hidden = String(im.dataset.page) !== String(info.page);
  });
  // The three proposer boxes were found on the caption's page and mean
  // nothing on another; the cut pictures below stay, labelled as they are.
  card.querySelectorAll('.pbox').forEach(b => { b.hidden = !info.caption; });
  card.querySelectorAll('.goto').forEach(b => {
    b.setAttribute('aria-pressed', String(String(b.dataset.page) === String(info.page)));
  });
  let tag = card.querySelector('.onpage');
  if (!tag && !info.caption) {
    tag = document.createElement('div'); tag.className = 'onpage';
    card.querySelector('.pagewrap').appendChild(tag);
  }
  if (tag) { tag.textContent = '옆 쪽 p.' + info.page; tag.hidden = !!info.caption; }
  overlay(card);
}
function needed(card, choice){
  if (choice !== 'DRAWN') return card.dataset.fp;
  const b = boxes[card.dataset.id];
  return b ? b.pfp : card.dataset.pfp;
}
Object.keys(store).forEach(id => {
  const card = byId[id];
  if (!card) return;
  if (!store[id] || VALID.indexOf(store[id].choice) < 0) { delete store[id]; dropped++; }
  else if (store[id].fp !== needed(card, store[id].choice)) { delete store[id]; dropped++; }
});
Object.keys(boxes).forEach(id => {
  const card = byId[id];
  if (!card) return;
  // A box is bound to the page it was drawn on, which may be a neighbour.
  const info = boxes[id] && pageInfo(card, boxes[id].page);
  if (!boxes[id] || !info || boxes[id].pfp !== info.pfp) {
    delete boxes[id];
    if (store[id] && store[id].choice === 'DRAWN') { delete store[id]; dropped++; }
  } else if (String(info.page) !== String(shownPage(card))) {
    showPage(card, info.page);
  }
});
if (dropped) complain(dropped + '행의 저장된 판정이 지금 화면의 그림과 맞지 않아 비웠습니다 — 다시 보십시오.');
function paint(card){
  const id = card.dataset.id, kept = store[id];
  card.querySelectorAll('.pick').forEach(b => {
    b.setAttribute('aria-pressed', String(!!kept && kept.choice === b.dataset.choice));
  });
  card.classList.toggle('done', !!kept && kept.choice !== 'BLOCKED');
  card.classList.toggle('blocked', !!kept && kept.choice === 'BLOCKED');
  const note = card.querySelector('input[data-note]');
  if (note && kept && typeof kept.note === 'string' && note.value !== kept.note) note.value = kept.note;
  const num = card.querySelector('input[data-number]');
  if (num) {
    if (num.value !== (numbers[id] || '')) num.value = numbers[id] || '';
    // A row waiting on a number is not answered until it has one, however
    // many buttons were pressed on it.
    card.classList.toggle('needs-number', !numbers[id]);
    if (!numbers[id]) card.classList.remove('done');
  }
  // 답한 행 = 고른 행 + 번호만으로 되는 행. 번호를 적어야 하는 행은 번호가
  // 있어야 셉니다 - 없으면 사람이 "다 했다"고 볼 화면에서 빠진 게 안 보입니다.
  const n = cards.filter(c => {
    const cid = c.dataset.id, wants = !!c.querySelector('input[data-number]');
    return wants ? !!numbers[cid] && (!!store[cid] || !c.querySelector(
      ".pick[data-choice='DRAWN']:not([disabled])")) : !!store[cid];
  }).length;
  document.getElementById('count').textContent = n + ' / ' + cards.length + ' 판정함';
}
// `again` is what the second click on a button means: unsay it. Drawing a
// box is never that - a person redrawing a box is correcting it, not
// withdrawing the answer, and toggling them off there loses the decision
// silently at the moment they are trying to improve it.
function choose(card, choice, again){
  if (VALID.indexOf(choice) < 0) return;
  const id = card.dataset.id, note = card.querySelector('input[data-note]');
  // A DRAWN answer that names no box is not an answer. The button is
  // disabled for exactly this reason, and the keyboard has to obey it too.
  if (choice === 'DRAWN' && !boxes[id]) {
    complain('먼저 페이지 위를 끌어 상자를 그리십시오.');
    return;
  }
  if (again !== false && store[id] && store[id].choice === choice) delete store[id];
  else store[id] = { choice: choice, fp: needed(card, choice),
                     note: note ? note.value : '' };
  persist(); paint(card);
}
function overlay(card){
  const div = card.querySelector('.drawn'), fig = card.querySelector('.mine'),
        b0 = boxes[card.dataset.id],
        // The box is drawn only on the page it belongs to.
        b = (b0 && String(b0.page) === String(shownPage(card))) ? b0 : null,
        pw = parseFloat(card.dataset.pw), ph = parseFloat(card.dataset.ph);
  if (div) {
    if (b && pw > 0 && ph > 0) {
      const p = b.box.split(',').map(Number);
      div.style.left = (p[0] / pw * 100) + '%';
      div.style.top = (p[1] / ph * 100) + '%';
      div.style.width = ((p[2] - p[0]) / pw * 100) + '%';
      div.style.height = ((p[3] - p[1]) / ph * 100) + '%';
      div.hidden = false;
    } else { div.hidden = true; }
  }
  const btn = card.querySelector(".pick[data-choice='DRAWN']");
  if (btn) btn.disabled = !b0;
  card.classList.toggle('drawn-on', !!b0);
  if (!fig) return;
  const img = card.querySelector('img.page:not([hidden])');
  if (!b || !img || !img.naturalWidth || !(pw > 0) || !(ph > 0)) {
    fig.hidden = true;
    return;
  }
  const p = b.box.split(',').map(Number),
        sx = img.naturalWidth / pw, sy = img.naturalHeight / ph,
        w = Math.max(1, Math.round((p[2] - p[0]) * sx)),
        h = Math.max(1, Math.round((p[3] - p[1]) * sy)),
        cv = fig.querySelector('canvas');
  cv.width = w; cv.height = h;
  cv.getContext('2d').drawImage(img, Math.round(p[0] * sx), Math.round(p[1] * sy),
                                w, h, 0, 0, w, h);
  fig.querySelector('.px').textContent =
    '(' + Math.round(p[2] - p[0]) + ' x ' + Math.round(p[3] - p[1]) + ' pt'
    + (pageInfo(card, b.page) && !pageInfo(card, b.page).caption ? ', p.' + b.page : '') + ')';
  fig.hidden = false;
}
document.addEventListener('click', ev => {
  const g = ev.target.closest('.goto');
  if (!g) return;
  showPage(g.closest('.card'), g.dataset.page);
});
// ------------------------------------------------ 페이지 위에서 상자를 그린다
// The box is stored in POINTS, the same unit `Figure_BBox` is in, computed
// from where the pointer was over the displayed image. It is clamped to the
// page: a drag that runs off the edge means the edge, not a box outside the
// paper.
const MIN_DRAG = 6;
let drag = null;
function fractions(ev){
  const r = drag.rect, cl = v => Math.min(1, Math.max(0, v));
  const ax = cl((drag.x - r.left) / r.width), ay = cl((drag.y - r.top) / r.height),
        bx = cl((ev.clientX - r.left) / r.width),
        by = cl((ev.clientY - r.top) / r.height);
  return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)];
}
document.addEventListener('pointerdown', ev => {
  const wrap = ev.target.closest('.pagewrap');
  if (!wrap || ev.button) return;
  const img = wrap.querySelector('img.page:not([hidden])');
  if (!img) return;
  drag = { card: wrap.closest('.card'), rect: img.getBoundingClientRect(),
           x: ev.clientX, y: ev.clientY, moved: false };
  ev.preventDefault();
});
document.addEventListener('pointermove', ev => {
  if (!drag) return;
  const f = fractions(ev), div = drag.card.querySelector('.drawn');
  drag.moved = Math.abs(ev.clientX - drag.x) >= MIN_DRAG
            || Math.abs(ev.clientY - drag.y) >= MIN_DRAG;
  if (!div) return;
  div.style.left = (f[0] * 100) + '%'; div.style.top = (f[1] * 100) + '%';
  div.style.width = ((f[2] - f[0]) * 100) + '%';
  div.style.height = ((f[3] - f[1]) * 100) + '%';
  div.hidden = false;
});
document.addEventListener('pointerup', ev => {
  if (!drag) return;
  const card = drag.card, f = fractions(ev), moved = drag.moved;
  drag = null;
  if (!moved) { overlay(card); return; }   // a click is not a box
  const pw = parseFloat(card.dataset.pw), ph = parseFloat(card.dataset.ph);
  if (!(pw > 0) || !(ph > 0)) {
    complain('이 행은 페이지 크기를 몰라 상자를 그릴 수 없습니다.');
    overlay(card); return;
  }
  boxes[card.dataset.id] = { pfp: card.dataset.pfp, page: shownPage(card),
    box: [f[0] * pw, f[1] * ph, f[2] * pw, f[3] * ph]
           .map(v => v.toFixed(1)).join(',') };
  persist();
  choose(card, 'DRAWN', false);
  overlay(card);
});
document.addEventListener('click', ev => {
  const b = ev.target.closest('.erase');
  if (!b) return;
  const card = b.closest('.card'), id = card.dataset.id;
  delete boxes[id];
  if (store[id] && store[id].choice === 'DRAWN') delete store[id];
  persist(); overlay(card); paint(card);
});
document.addEventListener('click', ev => {
  const b = ev.target.closest('.pick');
  if (b) choose(b.closest('.card'), b.dataset.choice);
});
document.addEventListener('input', ev => {
  const num = ev.target.closest('input[data-number]');
  if (num) {
    const id = num.closest('.card').dataset.id, v = num.value.trim();
    if (v) numbers[id] = v; else delete numbers[id];
    persist();
    paint(num.closest('.card'));
    return;
  }
  const note = ev.target.closest('input[data-note]');
  if (!note) return;
  const card = note.closest('.card'), kept = store[card.dataset.id];
  if (kept) { kept.note = note.value; persist(); }
});
function current(){
  let seen = null;
  for (const c of cards) { const r = c.getBoundingClientRect();
    if (r.top < window.innerHeight * 0.4) seen = c; }
  return seen || cards[0];
}
function nextEmpty(from){
  const start = cards.indexOf(from);
  for (let i = 1; i <= cards.length; i++) {
    const c = cards[(start + i) % cards.length];
    if (!store[c.dataset.id]) return c;
  }
  return null;
}
document.addEventListener('keydown', ev => {
  if (ev.target && ev.target.tagName === 'INPUT') return;
  const map = { '1':'TEXT', '2':'PDF', '3':'RASTER', '4':'DRAWN', '0':'BLOCKED' };
  if (map[ev.key]) { const c = current(); choose(c, map[ev.key]);
    const nx = nextEmpty(c); if (nx) nx.scrollIntoView({block:'start'}); ev.preventDefault(); }
  else if (ev.key === 'n') { const nx = nextEmpty(current());
    if (nx) nx.scrollIntoView({block:'start'}); ev.preventDefault(); }
});
document.getElementById('next').addEventListener('click', () => {
  const nx = nextEmpty(current()); if (nx) nx.scrollIntoView({block:'start'});
});
document.getElementById('toggle').addEventListener('click', ev => {
  const on = document.querySelector('.agent[hidden]') !== null;
  document.querySelectorAll('.agent').forEach(a => { a.hidden = !on; });
  ev.target.textContent = on ? '에이전트 제안 숨기기' : '에이전트 제안 보기';
});
function csvCell(v){ v = (v === undefined || v === null) ? '' : String(v);
  return /[",\\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
document.getElementById('save').addEventListener('click', () => {
  const out = [COLUMNS.join(',')];
  ROWS.forEach(r => {
    const q = Object.assign({}, QUEUE[r.Draft_ID]), kept = store[r.Draft_ID];
    // Only what a person did goes out. A row nobody answered exports blank,
    // and `review_packet.py merge` leaves it alone.
    q['Human_Choice'] = kept ? kept.choice : '';
    // The drawn box travels only with the answer that names it. A box left
    // over from an answer the person changed their mind about is not a
    // decision, and must not arrive at `apply_validated` looking like one.
    q['Human_Box'] = (kept && kept.choice === 'DRAWN' && boxes[r.Draft_ID])
                     ? boxes[r.Draft_ID].box : '';
    // The page the box was drawn on, only when it is not the caption's own -
    // blank means "this row's page", as it always has.
    const drawnOn = (kept && kept.choice === 'DRAWN' && boxes[r.Draft_ID])
                    ? boxes[r.Draft_ID].page : null;
    const card = byId[r.Draft_ID];
    const capPage = card ? (pagesOf(card).find(p => p.caption) || {}).page : null;
    q['Human_Page'] = (drawnOn !== null && capPage !== null
                       && String(drawnOn) !== String(capPage)) ? String(drawnOn) : '';
    q['Human_Note'] = kept && kept.note ? kept.note : '';
    // The number travels whether or not the row also has a choice.
    q['Human_Figure_Number'] = numbers[r.Draft_ID] || '';
    out.push(COLUMNS.map(c => csvCell(q[c])).join(','));
  });
  const blob = new Blob(['\\ufeff' + out.join('\\n')], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review_queue_' + PART + '.csv';
  document.body.appendChild(a); a.click(); a.remove();
});
cards.forEach(c => { overlay(c); paint(c); });
</script>
"""


if __name__ == "__main__":
    run = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(run, "review")
    sys.exit(build(run, out, sys.argv[3] if len(sys.argv) > 3 else None))
