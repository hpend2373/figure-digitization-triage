# -*- coding: utf-8 -*-
"""Rebuild the panel-count contact sheet with the second audit's findings wired in.

What changed, and why each change exists:

  102 cards, not 94   Eight documents produced no caption row, and the old sheet
                      simply had no card for them - so four publications the
                      audit proved contain figures were invisible to whoever
                      works from this page. Every document gets a card; a card
                      with no rows says so and says what is known about it.

  blank is not zero   The ledger leaves Page_Count empty for the twelve sources
                      that have no pages at all. The old sheet read that column
                      through an int() that defaulted to 0 and printed "0쪽" on
                      eight cards - the exact confusion the report had just
                      finished warning downstream tools about.

  no figure total     Counting distinct Figure_Number across documents merged a
                      374-page book's chapters and 156 repeated numbers into one
                      meaningless sum. There is no aggregate on this page. Rows
                      are counted as rows and labelled as rows.

  the doubt is shown  The intake writes a Confidence and a reason for every row,
                      including 52 that say the text reads as a sentence about a
                      figure rather than a caption. None of it reached the
                      screen. It does now.

  a bad crop takes    Fifteen crops hold a neighbouring figure, clip the target,
  no number           or show the wrong region; the whisker-thin ones are
                      uncountable as a class. Those inputs are disabled and
                      export as BLOCKED_BAD_CROP - never as 0.

The value/row binding and the blank/zero handling in the export are the two
things the audit passed. They are in sheet_logic.js under test, not re-written
here.
"""
import base64
import collections
import csv
import datetime
import hashlib
import html
import io
import json
import os

from PIL import Image

import block_rules as BR
import census as CENSUS_MOD
import roundtrip as RT
import paths as PATHS

D = PATHS.DRAFT
AUDIT = PATHS.AUDIT
OUT = PATHS.SHEET


def esc(s):
    return html.escape("" if s is None else str(s))


def rd(path, **kw):
    return list(csv.DictReader(io.open(path, encoding=kw.pop("enc", "utf-8"))))


DRAFT = rd(os.path.join(D, "figure_intake_draft.csv"))
LEDGER = {r["Source_Document_ID"]: r
          for r in rd(os.path.join(D, "intake_document_status.csv"))}
WORK = rd(PATHS.WORKLIST)
#: KEYED ON WHAT THE DOCUMENT PRINTS, NOT ON THE ROW'S ORDINAL. `Draft_ID` is
#: `<document>_D001`, `_D002` - a position in one walk's output. Recovering a
#: caption inserts a row and every later ordinal shifts, so a defect recorded
#: against `_D058` lands on whatever figure now sits at that position. The
#: third audit found nine of sixteen defects had moved that way, which left
#: three crops it had judged wrong with their inputs open and eight it had
#: judged fixed still blocked.
_defect_key = BR.figure_key


_AUDIT_ROWS = rd(os.path.join(AUDIT, "confirmed_image_defects.csv"),
                 enc="utf-8-sig")
DEFECT = {_defect_key(r["pid"], r["label"], r["page"]): r for r in _AUDIT_ROWS}
SENTENCE = {r["draft_id"]: r
            for r in rd(os.path.join(AUDIT, "sentence_warning_rows.csv"),
                        enc="utf-8-sig")}


#: Documents the first audit proved carry figures the intake never proposed.
#: Named on the card so a blank document does not read as "nothing here".
KNOWN_PRESENT = {
    "124": "1차 감사: 원문 텍스트에 Fig. 1 · 2 · 3 캡션이 있음",
    "147": "1차 감사: 원문 텍스트에 Figure 1–4 캡션이 있음",
    "416": "1차 감사: 원문 텍스트에 Fig. 1 · 3 · 4 · 5 · 6 캡션이 있음",
    "710": "1차 감사: 원문 텍스트에 Fig. 1 · 2 · 4 캡션이 있음",
}

#: WHAT THE PAGE PRESENTS, NOT JUST THE ROWS IT LISTS. The id hashed the draft
#: alone, so a change to the BLOCKING RULES left it identical - and the stored
#: values, which are keyed by this id, came back onto a sheet that now refuses
#: two of the rows they were typed on. Whatever decides what a person sees and
#: may answer goes into it: the draft, the rule, the builder, the page's own
#: scripts, and the audit findings the rule reads.
_ID_INPUTS = [os.path.join(D, "figure_intake_draft.csv"),
              os.path.join(AUDIT, "confirmed_image_defects.csv"),
              os.path.join(AUDIT, "sentence_warning_rows.csv"),
              PATHS.CENSUS, PATHS.REGIONS]
_HERE0 = os.path.dirname(os.path.abspath(__file__))
_ID_INPUTS += [os.path.join(_HERE0, f) for f in
               ("block_rules.py", "census.py", "roundtrip.py",
                "build_sheet2.py", "sheet_logic.js", "sheet_page.js")]
_h = hashlib.sha256()
for _f in _ID_INPUTS:
    _h.update(os.path.basename(_f).encode("utf-8"))
    _h.update(io.open(_f, "rb").read() if os.path.exists(_f) else b"")
BUILD_ID = "sheet-%s-%s" % (datetime.date.today().isoformat(),
                            _h.hexdigest()[:8])


def fingerprint(d):
    """Identify a row by what it shows, not by where it sits.

    A rebuilt draft can hand the same Draft_ID to a different figure - that is
    exactly what splitting Extended Data out or renumbering a book's chapters
    would do. The stored value carries this, and comes back only if it still
    matches.
    """
    raw = "|".join([d["Draft_ID"], d["Figure_Number"], d["Page"],
                    (d["Caption_Text"] or "")[:80],
                    d["Crop_Quality_Status"]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


#: Rows whose crop is byte-for-byte another row's. Two labels resolving to the
#: same picture means the box did not tell them apart, so at most one of them
#: is that figure and nothing here knows which. The third audit found the pair
#: in publication 518 - both body sentences, both open for input. Found by
#: hashing, so it holds for any document rather than for the two it was
#: noticed in.
def _crop_digests(rows, root):
    out = {}
    for d in rows:
        rel = d.get("Figure_Crop") or ""
        path = os.path.join(root, rel) if rel else ""
        if path and os.path.exists(path):
            out[d["Draft_ID"]] = hashlib.sha256(
                io.open(path, "rb").read()).hexdigest()
    return out


CROP_SHA = _crop_digests(DRAFT, D)
#: Rows whose figure number has another row on the page next door.
TWIN = BR.twin_map(DRAFT)

#: WHAT THE THREE PROPOSERS AGREED ON, per row - or a stated reason there is
#: no such file yet. Same shape as the census: missing stops the build.
if os.path.exists(PATHS.REGIONS):
    _REG = list(csv.DictReader(io.open(PATHS.REGIONS, encoding="utf-8")))
    AGREEMENT = {r["Draft_ID"]: (r.get("Agreement") or "PENDING") for r in _REG}
    #: What each detector said about this page - the evidence `phantom_reason`
    #: needs that "nothing figure-sized is here".
    CODES = {r["Draft_ID"]: (r.get("PDF_Code", ""), r.get("Raster_Code", ""))
             for r in _REG}
elif PATHS.REGIONS_OPTIONAL:
    AGREEMENT = None
    CODES = {}
else:
    raise SystemExit(
        "그림 영역 검증표가 없습니다: %r\n"
        "python3 validate_regions.py <run> 으로 만들거나, FDT_REGIONS로 지정하거나, "
        "아직 돌리지 않은 코퍼스라면 FDT_REGIONS_OPTIONAL=1로 밝히십시오."
        % PATHS.REGIONS)

#: Rows that would count a picture another row already holds - found two
#: ways. Two boxes on one page (`duplicate_map`), and a person's box landing
#: on a page where the figure already has a row (`confirmed_duplicates`, from
#: what `apply_validated` wrote down when it refused the move). A row the
#: person BLOCKED takes no part: it holds no figure to win or to duplicate.
_BLOCKED_IDS = {i for i, a in (AGREEMENT or {}).items() if a == "HUMAN_BLOCKED"}
DUPLICATE = BR.duplicate_map(DRAFT, blocked_ids=_BLOCKED_IDS)
for _i, _v in BR.confirmed_duplicates(_REG if AGREEMENT is not None else []).items():
    DUPLICATE.setdefault(_i, _v)
#: Byte-identical crops - minus the pairs `DUPLICATE` already explains as one
#: figure, so the row that holds the figure is not blocked for resembling
#: the row that does not.
SHARED_CROP = BR.shared_crop_map(CROP_SHA, duplicate=DUPLICATE)

#: EVERY CROP CUT AGAIN FROM ITS BOX. `roundtrip.check` repeats the intake's
#: cut and compares with the file; a row whose crop cannot be reproduced from
#: the draft's own geometry is blocked by `block_rules`. This is the check that
#: would have caught a mirrored box on the first row - and it runs on every
#: build so that nobody has to remember to.
ROUNDTRIP = {d["Draft_ID"]: RT.check(d, D)[0] for d in DRAFT}

#: THE VISUAL CENSUS, OR A STATED REASON THERE IS NONE. `ACCEPTABLE` is a
#: measurement of the crop; this is a record of what is inside it, and without
#: it 336 of run2's 440 open rows are rows asking somebody to count panels in
#: a paragraph. A missing file therefore stops the build instead of quietly
#: reopening them; `FDT_CENSUS_OPTIONAL=1` is how a corpus nobody has looked
#: at yet says so out loud.
if os.path.exists(PATHS.CENSUS):
    try:
        CENSUS = CENSUS_MOD.load(PATHS.CENSUS)
    except CENSUS_MOD.CensusError as exc:
        raise SystemExit("육안 조사표를 읽을 수 없습니다 (%s): %s"
                         % (PATHS.CENSUS, exc))
elif PATHS.CENSUS_OPTIONAL:
    CENSUS = None
else:
    raise SystemExit(
        "육안 조사표가 없습니다: %r\n"
        "FDT_CENSUS로 지정하거나, 아직 아무도 보지 않은 코퍼스라면 "
        "FDT_CENSUS_OPTIONAL=1로 그렇다고 밝히십시오." % PATHS.CENSUS)

PID_OF_DOC = {}


def row_key(d):
    return _defect_key(PID_OF_DOC.get(d["Source_Document_ID"], ""),
                       d["Figure_Number"], d["Page"])


def blocked_reason(d):
    """Why this row cannot take a number - decided by the repository's rule.

    The rule itself is `sheet/block_rules.py`, which reads no files and is
    covered by `test_sheet_blocks.py`. It lives apart from this builder because
    the draft this builder reads is made from publisher PDFs and cannot be
    published: a safety rule only checkable against data nobody else has is a
    safety rule nobody else can check.
    """
    return BR.blocked_reason(d, row_key(d), defect=DEFECT.get(row_key(d)),
                             shared_with=SHARED_CROP.get(d["Draft_ID"], ()),
                             census=CENSUS,
                             crop_sha=CROP_SHA.get(d["Draft_ID"], ""),
                             roundtrip=ROUNDTRIP.get(d["Draft_ID"]),
                             agreement=(None if AGREEMENT is None else
                                        AGREEMENT.get(d["Draft_ID"], "PENDING")),
                             codes=CODES.get(d["Draft_ID"], ()),
                             twin=TWIN.get(d["Draft_ID"]),
                             duplicate=DUPLICATE.get(d["Draft_ID"]))


#: A publisher's figure file has no page and no box - it IS the figure - so
#: the page view is not missing for it, it does not apply. What such a row
#: must have instead is the file itself.
FIGURE_FILE_STATUS = "PUBLISHER_FIGURE"


def _needs_page(d):
    return (not blocked_reason(d)
            and str(d.get("Crop_Quality_Status") or "").strip()
            != FIGURE_FILE_STATUS)


def caution(d):
    # A LAPSED FINDING IS NOT A DELETED ONE. The row counts again because the
    # person replaced the picture the finding was about, but they should still
    # see what was once said about this figure - so it moves from the block to
    # the card, in the person's own words.
    gone = BR.lapsed(d, row_key(d), defect=DEFECT.get(row_key(d)))
    if gone:
        return ("지난 판정(지금은 만료) — %s · 그 뒤 사람이 상자를 %s로 정해 "
                "크롭이 바뀌었습니다" % (gone, BR.human_cut(d)))
    hit = DEFECT.get(row_key(d))
    if hit and hit["classification"] == "WARNING":
        return "2차 감사 경고 — %s" % hit["screen"]
    return ""


# worklist row -> the document the intake made from it (needed by row_key)
DOC_OF = {}
for w in WORK:
    import urllib.parse
    _p = urllib.parse.unquote(w["href"][len("file://"):])
    # ONE MACHINE'S HOME DIRECTORY WAS WRITTEN INTO THIS. The worklist is
    # authored on a laptop and the intake runs elsewhere, so the two name the
    # same file differently - and the rewrite that bridged them was a literal
    # `/Users/<name>/`. Anywhere else it matched nothing and the assert below
    # ended the build with a pair of integers and no idea which rows.
    _p = PATHS.rewrite(_p)
    for _did, _L in LEDGER.items():
        if _L["Input_Path"] == _p:
            DOC_OF[w["pid"]] = _did
            break
_missing = [w["pid"] for w in WORK if w["pid"] not in DOC_OF]
if _missing:
    raise SystemExit(
        "worklist에서 %d편의 문서를 찾지 못했습니다: pid %s\n"
        "워크리스트의 href와 인테이크 원장의 Input_Path가 같은 파일을 "
        "다르게 부르고 있습니다. FDT_PATH_REWRITE로 접두사를 맞추십시오 "
        "(지금 값: %r)."
        % (len(_missing), ", ".join(_missing[:8]), PATHS.PATH_REWRITE))
PID_OF_DOC.update({v: k for k, v in DOC_OF.items()})

ROWS, BLOCKED, COUNTABLE = [], 0, 0
for d in DRAFT:
    fp = fingerprint(d)
    br = blocked_reason(d)
    if br:
        BLOCKED += 1
    else:
        COUNTABLE += 1
    ROWS.append(dict(Draft_ID=d["Draft_ID"],
                     Source_Document_ID=d["Source_Document_ID"],
                     Source_File=d["Source_File"], Page=d["Page"],
                     Figure_Number=d["Figure_Number"],
                     Crop_Quality_Status=d["Crop_Quality_Status"],
                     Row_Fingerprint=fp,
                     Count_Blocked="1" if br else "0"))
FP = {r["Draft_ID"]: r["Row_Fingerprint"] for r in ROWS}
BLOCK = {r["Draft_ID"]: r["Count_Blocked"] for r in ROWS}

# WHAT THIS BUILD BLOCKED, AND WHY, AS A FILE. The reason lived only inside
# this process, so anything else that wanted to know had to reimplement the
# decision from a partial view - `review_packet.queue` calls the rule with a
# blank key and no census, which is why it once offered people rows the sheet
# then ignored. Writing it down makes the review queue read the SHEET'S answer
# instead of a second opinion about it.
#: 문서별 행 목록 - `mentions_held`가 "그 그림을 누가 세고 있나"를 볼 때 씁니다.
BYDOC_ROWS = {}
for _d in DRAFT:
    BYDOC_ROWS.setdefault(_d["Source_Document_ID"], []).append(_d)

_REASONS = os.path.join(D, "block_reasons.csv")
_reason_fields = ("Draft_ID", "Count_Blocked", "Reason", "Box_Would_Open",
                  "Number_Would_Open", "Duplicate_Of", "Mentions_Held")
with io.open(_REASONS, "w", encoding="utf-8", newline="") as _fh:
    _w = csv.DictWriter(_fh, fieldnames=list(_reason_fields))
    _w.writeheader()
    for _d in DRAFT:
        _br = blocked_reason(_d)
        # 사람이 무엇을 채우면 풀리는가 - 규칙에게 직접 물어봅니다. 한 번 물어
        # 두 답을 얻습니다: 같은 행에 대해 두 번 물으면 두 답이 어긋날 수 있고,
        # 그러면 페이지가 상자는 청하면서 번호는 청하지 않게 됩니다.
        _fix = BR.repairs_that_open(
            _d, row_key(_d), defect=DEFECT.get(row_key(_d)),
            census=CENSUS, codes=CODES.get(_d["Draft_ID"], ()),
            twin=TWIN.get(_d["Draft_ID"]),
            duplicate=DUPLICATE.get(_d["Draft_ID"])) if _br else ()
        _w.writerow({
            "Draft_ID": _d["Draft_ID"],
            "Count_Blocked": "1" if _br else "0",
            "Reason": _br,
            "Box_Would_Open": "1" if BR.REPAIR_BOX in _fix else "0",
            "Number_Would_Open": "1" if BR.REPAIR_NUMBER in _fix else "0",
            # 어느 행이 그 그림을 가지는가 - 큐가 산문을 읽지 않고 이 칸을 읽습니다.
            "Duplicate_Of": (DUPLICATE.get(_d["Draft_ID"]) or ("",))[0] if _br else "",
            # 이 줄이 부르는 그림을 이미 세고 있는 행들. 판정이 아니라 사람에게
            # 보여 줄 사실입니다 - 번호를 못 읽은 행은 중복 규칙에도 유령 규칙에도
            # 걸리지 않아, 사람이 여덟 행을 앞에 두고 무엇을 그려야 할지 알 길이
            # 없었습니다.
            "Mentions_Held": ";".join(
                "%s=%s" % kv for kv in BR.mentions_held(
                    _d, BYDOC_ROWS.get(_d["Source_Document_ID"], ()), BLOCK))
            if _br else ""})
print("막힌 사유 표: %s" % _REASONS)

BYDOC = collections.defaultdict(list)
for d in DRAFT:
    BYDOC[d["Source_Document_ID"]].append(d)

def thumb(path, width=300, quality=58):
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return ("data:image/jpeg;base64,"
            + base64.b64encode(buf.getvalue()).decode("ascii"))


#: WHAT THE COUNTING ACTUALLY NEEDS. The sheet embedded one 300px-wide JPEG
#: at quality 58 per row and nothing else, so 41% of the countable rows
#: rendered under 200px tall and there was no way to see more: no zoom, and no
#: pixels in the page to zoom into. A person was being asked to count axis
#: regions in a picture that cannot show them. The thumbnail still lays out
#: the grid; this is what opens when the picture is clicked.
ZOOM_QUALITY = int(os.environ.get("FDT_ZOOM_QUALITY", "85"))
#: 0 means "as large as the crop is". A cap exists only for the case where a
#: crop is a whole page raster at 600 dpi.
ZOOM_MAX_WIDTH = int(os.environ.get("FDT_ZOOM_MAX_WIDTH", "0"))


def zoom(path):
    im = Image.open(path).convert("RGB")
    if ZOOM_MAX_WIDTH and im.width > ZOOM_MAX_WIDTH:
        im = im.resize((ZOOM_MAX_WIDTH,
                        max(1, round(im.height * ZOOM_MAX_WIDTH / im.width))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=ZOOM_QUALITY, optimize=True)
    return ("data:image/jpeg;base64,"
            + base64.b64encode(buf.getvalue()).decode("ascii"))


#: THE CROP CANNOT ANSWER "IS THIS THE WHOLE FIGURE". Two of the run2 crops
#: were a full column wide, ACCEPTABLE, and open for input while holding a
#: page header and white space - the figure was beside them. Nothing on the
#: page could have shown that: a crop shows what the box caught, never what it
#: missed. The page, with the box drawn on it, is the only view that answers
#: it, and it belongs next to the count so the two are one look.
PAGE_VIEW_WIDTH = int(os.environ.get("FDT_PAGE_VIEW_WIDTH", "950"))
PAGE_VIEW_QUALITY = int(os.environ.get("FDT_PAGE_VIEW_QUALITY", "72"))


def page_view(row):
    """The whole page at reading size, with this row's box outlined."""
    raster = row.get("Page_Raster") or ""
    if not raster or not os.path.exists(raster):
        return ""
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
        x0, y0, x1, y1 = [float(v) for v in row["Figure_BBox"].split(",")]
    except (KeyError, ValueError):
        # No geometry means no box to draw, and a page with no box on it would
        # be worse than nothing here - it looks like the crop is fine.
        return ""
    from PIL import ImageDraw
    im = Image.open(raster).convert("RGB")
    W, H = im.size
    ImageDraw.Draw(im).rectangle(
        [x0 * W / pw, y0 * H / ph, x1 * W / pw, y1 * H / ph],
        outline=(196, 32, 32), width=max(3, W // 220))
    im.thumbnail((PAGE_VIEW_WIDTH, PAGE_VIEW_WIDTH * 4 // 3))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=PAGE_VIEW_QUALITY, optimize=True)
    return ("data:image/jpeg;base64,"
            + base64.b64encode(buf.getvalue()).decode("ascii"))


def pages_text(L):
    """The ledger's own blank, preserved. Never printed as a number."""
    v = (L.get("Page_Count") or "").strip()
    return (v + "쪽") if v else "쪽수 없음"


#: The page is assembled into whichever buffer is current, so the cards can be
#: collected per document and dealt out into files afterwards.
HEAD = []
BUF = HEAD


def w(x):
    BUF.append(x)


w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
w("<title>패널 수 확인 시트 (2판) — 102편 / %d행</title>" % len(DRAFT))
w("""<style>
:root{--bg:#fbfaf8;--ink:#1b1a18;--mut:#6c6862;--rule:#dedad3;--card:#fff;
--acc:#2b4c7e;--bad:#9a2f2f;--warn:#8a5a00;--ok:#1f6b3f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 120px}
h1{font-size:24px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13.5px;margin-bottom:18px}
.bar{position:sticky;top:0;z-index:9;background:rgba(251,250,248,.96);
border-bottom:1px solid var(--rule);padding:10px 0;margin-bottom:16px;
display:flex;gap:12px;align-items:center;flex-wrap:wrap;
backdrop-filter:saturate(180%) blur(8px)}
button{font:inherit;font-size:14px;padding:7px 14px;border-radius:4px;
border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.g{background:#fff;color:var(--acc)}
.count{font-size:13px;color:var(--mut)}
.doc{background:var(--card);border:1px solid var(--rule);border-radius:4px;
padding:14px 16px;margin:0 0 16px}
.doc>h2{font-size:15px;margin:0 0 4px}
.doc>.meta{font-size:12.5px;color:var(--mut);margin-bottom:12px}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));
gap:14px}
.fig{border:1px solid var(--rule);border-radius:3px;padding:9px;font-size:12px}
.fig img{width:100%;display:block;background:#fff;border:1px solid var(--rule)}
.fig .cap{color:var(--mut);margin:6px 0 8px}
.fig img.thumb{cursor:zoom-in}
.fig img.thumb[data-zoom]{outline:1px solid transparent}
.fig input:focus{outline:2px solid var(--acc);outline-offset:1px}
.fig label.unc{margin-top:5px;font-size:12px;color:var(--mut)}
.fig label.unc input{width:auto}
.fig .uncwhy{width:100%;margin-top:4px;font-size:12px}
.fig.unc{border-color:#c9b48a;background:#fffaf0}
.fig.here{box-shadow:0 0 0 3px rgba(43,76,126,.35)}
#lb{position:fixed;inset:0;background:rgba(20,19,17,.92);display:none;
z-index:50;overflow:auto;padding:24px}
#lb.on{display:block}
#lb img{display:block;margin:0 auto;background:#fff;max-width:none}
#lbbar{position:sticky;top:0;display:flex;gap:12px;align-items:center;
color:#fff;font-size:13px;margin-bottom:12px}
#lbbar button{background:#fff;color:var(--ink);border-color:#fff}
#lb .lbstep{color:#fff;font-size:13.5px;margin:14px auto 6px;max-width:1000px}
#lbpage{display:block;margin:0 auto 8px;background:#fff}
#lbnopage{color:#f0ece4;background:rgba(255,255,255,.10);border-radius:4px;
padding:12px 14px;margin:0 auto 8px;max-width:1000px;font-size:13.5px}
.fig label{display:flex;gap:7px;align-items:center;font-size:12.5px}
.fig input{width:66px;font:inherit;padding:4px 6px;border:1px solid var(--rule);
border-radius:3px}
.fig input:disabled{background:#f0eeea;color:#a5a09a;cursor:not-allowed}
.fig.done{border-color:#9dc2a2;background:#f4faf5}
.fig.blocked{border-color:#e0bcbc;background:#fdf4f4}
.fig.err input{border-color:var(--bad);background:#fff5f5}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:9px;
border:1px solid var(--rule);margin:0 4px 4px 0;white-space:nowrap}
.b-low{border-color:#e0c48a;background:#fff8e8;color:var(--warn)}
.b-sent{border-color:#e0bcbc;background:#fdf1f1;color:var(--bad)}
.b-block{border-color:#d9a5a5;background:#f8e6e6;color:var(--bad)}
.why{font-size:11.5px;color:var(--bad);margin:6px 0 0;line-height:1.45}
.msg{font-size:11.5px;color:var(--bad);margin:5px 0 0;min-height:0}
.empty{border:1px dashed var(--rule);border-radius:3px;padding:14px;
font-size:13px;color:var(--mut);background:#faf9f7}
code{font:12px ui-monospace,Menlo,monospace;background:#f0ede8;padding:1px 4px;
border-radius:3px}
.note{background:#fff8e8;border:1px solid #e8d9ae;border-radius:3px;
padding:14px 16px;margin:0 0 16px;font-size:14px}
.stop{background:#fdf1f1;border:2px solid #e0bcbc;border-radius:3px;
padding:14px 16px;margin:0 0 16px;font-size:14px}
#storagewarn{display:none;background:#fdf1f1;border:2px solid var(--bad);
border-radius:3px;padding:12px 14px;margin:0 0 16px;font-size:14px;
color:var(--bad)}
ul{margin:6px 0 0;padding-left:20px}li{margin:0 0 4px}
</style></head><body><div class='wrap'>""")

w("<h1>패널 수 확인 시트 <span class='count'>2판</span></h1>")
w("<div class='sub'>102편 · 캡션 후보 %d행 · 빌드 <code>%s</code> · "
  "P1 → P2 순</div>" % (len(DRAFT), esc(BUILD_ID)))

w("<div id='storagewarn'></div>")
# The picture, at the size it was cut. Sits outside the cards so opening it
# never moves the grid under the person's cursor.
w("<div id='lb'><div id='lbbar'><button id='lbclose'>닫기 (Esc)</button>"
  "<span id='lbcap'></span></div>"
  "<div class='lbstep'>① 상자가 목표 그림 전체를 담았습니까? "
  "— 페이지 전체, 빨간 상자가 이 행의 크롭입니다</div>"
  "<img id='lbpage' alt=''><div id='lbnopage'></div>"
  "<div class='lbstep'>② 담았다면, 이 그림에 축 영역이 몇 개입니까? "
  "— 크롭 원본 해상도</div><img id='lbimg' alt=''></div>")

# 이 칸은 예전에 "아직 계수를 시작하지 마십시오"라고 못박혀 있었습니다. 그
# 문장은 2판을 만들던 날의 상태였고, 그 뒤 크롭 재생성과 캡션·번호 확정이
# 끝났는데도 문장은 그대로 남아 시트를 여는 사람마다 멈추라고 말했습니다.
# 빌드 시점에 참인지 알 수 없는 말은 여기에 적지 않습니다 - 대신 이 시트가
# 어느 초안에서 나왔는지를 적고, 시작해도 되는지는 그 초안의 상태(검토 대기열,
# 왕복 대조)를 보고 정하게 합니다.
w("""<div class='stop'><b>이 시트는 초안 %s에서 나왔습니다.</b>
행마다 지문이 함께 저장되므로, 초안이 바뀌면 그 행의 입력은 되살아나지 않고
`merge_counts.py`가 합치기를 거부합니다. 시작하기 전에 그 초안의 검토
대기열이 비어 있고 왕복 대조가 맞는지 확인하십시오 — 이 칸은 그것을 대신
확인해 주지 않습니다. 확인된 결함이 있는 크롭은 입력을 막아 두었고,
<b>BLOCKED_BAD_CROP</b>으로 내보내집니다.</div>""" % BUILD_ID)

w("""<div class='note'>각 그림에 <b>축 영역(패널)이 몇 개</b> 인쇄되어
있는지 세어 입력합니다. 기계는 이 숫자를 제안하지 않습니다.
<ul>
<li><b>빈칸 = 아직 안 봤다</b>, <b>0 = 축 영역이 없다</b>. 둘은 다른
값이며 내보내기에서도 구별됩니다.</li>
<li>0 이상 %d 이하의 <b>정수만</b> 저장됩니다. 그 밖의 값은 저장되지도,
내보내지지도 않습니다.</li>
<li>보긴 봤는데 셀 수 없으면 <b>봤지만 셀 수 없음</b>에 표시하고 이유를
한 줄 적습니다. 빈칸으로 두면 아무도 안 본 것과 구별되지 않아, 다음 사람이
같은 자리에서 다시 막힙니다.</li>
<li><b>붉은 칸</b>은 크롭 결함이 확인되어 입력을 막은 행입니다.
숫자를 넣을 수 없고, <code>BLOCKED_BAD_CROP</code>으로 내보내집니다.</li>
<li>입력값은 브라우저에 저장되며, <b>행의 내용이 바뀌면 되살아나지
않습니다</b> — 지문이 다르면 다른 그림으로 보고 값을 버립니다.</li>
</ul></div>""" % 40)

w("<div class='bar'><button id='dl'>CSV 내려받기</button>"
  "<button class='g' id='clr'>입력 지우기</button>"
  "<span class='count' id='cnt'></span></div>")

CARDS = []
for wl in sorted(WORK, key=lambda r: (r["priority"], int(r["pid"]))):
    pid = wl["pid"]
    doc = DOC_OF[pid]
    L = LEDGER[doc]
    ds = BYDOC.get(doc, [])
    BUF = []
    w("<div class='doc'><h2>pid %s · %s <span class='count'>%s</span></h2>"
      % (esc(pid), esc(os.path.basename(L["Input_Path"])), esc(wl["priority"])))
    w("<div class='meta'>워크리스트: 추출대상 %s · 그림수 %s · 형태 %s · %s"
      "%s<br>인테이크: <code>%s</code> · 후보 %d행 · %s</div>"
      % (esc(wl["targets"]), esc(wl["figures"]), esc(wl["shapes"]),
         esc(wl["domains"]),
         (" · 메모: " + esc(wl["memo"])) if wl["memo"].strip() else "",
         esc(L["Text_Backend_Status"]), len(ds), esc(pages_text(L))))
    if not ds:
        extra = KNOWN_PRESENT.get(pid)
        w("<div class='empty'><b>이 문서는 캡션 후보가 0행입니다.</b> "
          "그림이 없다는 뜻이 아니라, 인테이크가 캡션을 찾지 못했다는 "
          "뜻입니다.%s<br>워크리스트는 이 논문에서 <b>그림 %s개</b>를 "
          "쓸 계획입니다. 2단계(캡션 인식 수정)에서 다시 잡습니다.</div>"
          % ((" <b style='color:#9a2f2f'>" + esc(extra) + ".</b>") if extra
             else "", esc(wl["figures"])))
        w("</div>")
        CARDS.append((pid, [], "\n".join(BUF)))
        continue
    w("<div class='gal'>")
    for d in ds:
        did = d["Draft_ID"]
        p = os.path.join(D, d["Figure_Crop"]) if d["Figure_Crop"] else ""
        has_img = bool(p) and os.path.exists(p)
        _open = has_img and not blocked_reason(d)
        # SEEING IS NOT COUNTING. The large copy used to ride along only for
        # rows that can take a number, to keep the file small - so all 75
        # blocked rows had a thumbnail and nothing behind it, and `openZoom`
        # returns at once without `data-zoom`. A person who wanted to know
        # whether a block was right had no way to look, and the 2026-09-06
        # audit found that 57 of those 75 are not the figure at all while 15
        # are the figure, blocked as a duplicate. Both of those are things a
        # person can only see by opening the picture. The input gate stays
        # exactly where it was; the pictures come along.
        big = ((" data-zoom='%s'" % zoom(p)) if has_img else "")
        if has_img:
            if not _needs_page(d):
                # Says what is true rather than leaving the first step blank:
                # there is no box to check because there is no box.
                big += (" data-nopage='이 행은 페이지에서 잘라낸 크롭이 "
                        "아니라 출판사가 낸 그림 파일입니다 — 상자가 없으므로 "
                        "잘리거나 이웃이 섞일 수 없습니다'")
            else:
                _pv = page_view(d)
                if _pv:
                    big += " data-page='%s'" % _pv
        img = (("<img class='thumb' src='%s' alt=''%s>" % (thumb(p), big))
               if has_img else
               # NOT A CLAIM ABOUT THE PAPER. This said "원문에 그림이
               # 포함되어 있지 않습니다" on 45 rows whose sources are JATS
               # XML - and those papers do have figures: one of them declares
               # fifteen <fig> elements, and the XML names the image files by
               # name. What is missing is a file we have, not a figure the
               # paper has. `block_rules.py` had this right all along; only
               # the sheet said otherwise.
               "<div class='cap'>[보여줄 이미지가 없습니다 — 이 원문은 "
               "XML·텍스트라 쪽 이미지가 없고, 그림 파일도 함께 받지 "
               "않았습니다. 그림을 보려면 이 논문의 PDF나 그림 파일이 "
               "필요합니다]</div>")
        br, ca = blocked_reason(d), caution(d)
        sent = SENTENCE.get(did)
        conf = float(d["Confidence"])
        badges = ["<span class='badge'>%s</span>" % esc(d["Crop_Quality_Status"])]
        badges.append("<span class='badge%s'>신뢰도 %.2f</span>"
                      % (" b-low" if conf < 0.6 else "", conf))
        if sent:
            badges.append("<span class='badge b-sent'>본문 문장 의심</span>")
        if br:
            badges.append("<span class='badge b-block'>계수 불가</span>")
        w("<div class='fig%s' data-id='%s' data-fp='%s'>%s"
          "<div class='cap'><b>%s</b> · p.%s<br>%s<br>%s</div>"
          % (" blocked" if br else "", esc(did), esc(FP[did]), img,
             esc(d["Figure_Number"]), esc(d["Page"]), "".join(badges),
             # THE CAPTION IS THE DOCUMENT'S OWN ACCOUNT OF ITS PANELS, and it
             # was cut at 120 characters - which is where "(A) ... (B) ..."
             # usually begins. Showing it whole is showing the source, not
             # suggesting a number.
             esc(d["Caption_Text"] or "")))
        if sent:
            w("<div class='why'><b>기계가 스스로 남긴 의심:</b> %s</div>"
              % esc(sent["reason"]))
        elif d["Confidence_Reason"].strip():
            w("<div class='why' style='color:#6c6862'>%s</div>"
              % esc(d["Confidence_Reason"]))
        if ca:
            w("<div class='why' style='color:#8a5a00'>%s</div>" % esc(ca))
        if br:
            w("<div class='why'><b>입력을 막았습니다.</b> %s</div>" % esc(br))
            w("<label>패널 수 <input type='number' disabled "
              "data-id='%s'></label>" % esc(did))
        else:
            w("<label>패널 수 <input type='number' min='0' max='40' "
              "step='1' data-id='%s'></label>" % esc(did))
            # A BLANK MEANT "NOT LOOKED AT YET" AND NOTHING MEANT "LOOKED,
            # CANNOT TELL". A figure someone studied and could not resolve
            # went back into the pile as unread - or the only way to make the
            # row stop asking was to type a number.
            w("<label class='unc'><input type='checkbox' data-unc='%s'> "
              "봤지만 셀 수 없음</label>"
              # NO placeholder. The sheet forbids them on inputs and it is
              # right to: a hint inside the box is read as a value that is
              # already there, and this page's whole argument is that an
              # empty box means nobody has answered yet.
              "<span class='uncwhy' data-uncwrap='%s' hidden>왜 셀 수 없는지 "
              "<input type='text' data-uncwhy='%s' maxlength='200'></span>"
              % (esc(did), esc(did), esc(did)))
        w("<div class='msg' data-msg='%s'></div></div>" % esc(did))
    w("</div>")
    w("</div>")
    CARDS.append((pid, [d["Draft_ID"] for d in ds], "\n".join(BUF)))

# beside this file, not at an absolute path: the third audit could not
# rebuild the sheet in a clean checkout because these two were pinned to
# /tmp/intake.
_HERE = os.path.dirname(os.path.abspath(__file__))
_LOGIC = io.open(os.path.join(_HERE, "sheet_logic.js"), encoding="utf-8").read()
_PAGE = io.open(os.path.join(_HERE, "sheet_page.js"), encoding="utf-8").read()
_BY_ID = {r["Draft_ID"]: r for r in ROWS}


def tail(ids):
    """The scripts, carrying ONLY the rows this file shows.

    A part that declared all 649 rows would count rows it does not display as
    outstanding, and would export them as NOT_REVIEWED - so two parts would
    each make a claim about the same row and the merge would have to arbitrate
    between a person's answer and a page that never asked the question.
    """
    return "\n".join([
        "<script>%s</script>" % _LOGIC,
        "<script>const ROWS=%s;const BUILD_ID=%s;</script>"
        % (json.dumps([_BY_ID[i] for i in ids], ensure_ascii=False),
           json.dumps(BUILD_ID)),
        _PAGE, "</div></body></html>"])


#: DOCUMENTS ARE NEVER SPLIT ACROSS FILES. A person works a document at a
#: time, and half its figures in another file is how one gets skipped. Sheets
#: fill to a byte budget and then start a new one.
#: A COUNTABLE ROW WITHOUT ITS PAGE IS NOT SHIPPABLE. The page view is how a
#: person answers "did the box catch the figure" - the question that let two
#: crops through - so a row that can take a number and cannot show its page is
#: a row being asked to be counted with the check removed. One row shipped
#: that way: a merge skipped a document whose directory already existed, and
#: the page it needed stayed behind in the part it was built in. Silence is
#: what made it survive, so this is loud and fatal.
_NO_PAGE = [d["Draft_ID"] for d in DRAFT
            if _needs_page(d)
            and not (str(d.get("Page_Raster") or "").strip()
                     and os.path.exists(d["Page_Raster"]))]
_NO_FILE = [d["Draft_ID"] for d in DRAFT
            if not blocked_reason(d) and not _needs_page(d)
            and not os.path.exists(os.path.join(D, d.get("Figure_Crop") or ""))]
if _NO_FILE:
    raise SystemExit(
        "출판사 그림 파일로 표시된 행 %d개에 그 파일이 없습니다:\n  %s"
        % (len(_NO_FILE), "\n  ".join(_NO_FILE[:10])))
if _NO_PAGE:
    raise SystemExit(
        "입력 가능한 행 %d개에 페이지 래스터가 없습니다 — 이 행들은 "
        "'상자가 그림을 담았는가'를 물을 수 없습니다:\n  %s%s\n"
        "인테이크 산출물이 온전한지 verify_intake_images.py로 확인하십시오."
        % (len(_NO_PAGE), "\n  ".join(_NO_PAGE[:10]),
           "\n  ... 그리고 %d개 더" % (len(_NO_PAGE) - 10)
           if len(_NO_PAGE) > 10 else ""))

PARTS, cur, cur_ids, cur_bytes, OVERSIZE = [], [], [], 0, []
_head = "\n".join(HEAD)
_base = len(_head.encode("utf-8")) + len(_LOGIC.encode("utf-8")) \
    + len(_PAGE.encode("utf-8"))
for pid, ids, card in CARDS:
    size = len(card.encode("utf-8"))
    # A DOCUMENT LARGER THAN THE BUDGET GETS ITS OWN FILE, OVER BUDGET. Never
    # splitting a document is the rule a person works by; the file that
    # results from a 137-figure book is then the size it is, and saying so
    # here is better than someone meeting it in a browser.
    if _base + size > PATHS.SHEET_BUDGET:
        OVERSIZE.append((pid, len(ids), size))
    if cur and _base + cur_bytes + size > PATHS.SHEET_BUDGET:
        PARTS.append((cur, cur_ids))
        cur, cur_ids, cur_bytes = [], [], 0
    cur.append(card)
    cur_ids.extend(ids)
    cur_bytes += size
if cur or not PARTS:
    PARTS.append((cur, cur_ids))

_written = []
for _i, (_cards, _ids) in enumerate(PARTS, 1):
    _out = OUT if len(PARTS) == 1 else PATHS.part_path(OUT, _i)
    _where = ("" if len(PARTS) == 1 else
              "<div class='sub'><b>%d / %d번째 시트</b> · 이 파일의 행 %d개 · "
              "입력은 시트마다 따로 저장되고, 시트마다 CSV를 내려받은 뒤 "
              "<code>merge_counts.py</code>로 합칩니다.</div>"
              % (_i, len(PARTS), len(_ids)))
    io.open(_out, "w", encoding="utf-8").write(
        "\n".join([_head, _where] + _cards + [tail(_ids)]))
    _written.append(_out)

# THE SHEET AND ITS DATA TRAVEL TOGETHER. The last delivery put a 639-row page
# beside a 604-row CSV from an older walk, so nothing in the bundle described
# what was on screen. Copying them here means the pair cannot drift again.
import shutil
for _name in ("figure_intake_draft.csv", "intake_document_status.csv",
              os.path.basename(PATHS.CENSUS), os.path.basename(PATHS.REGIONS)):
    _src = (PATHS.CENSUS if _name == os.path.basename(PATHS.CENSUS)
            else PATHS.REGIONS if _name == os.path.basename(PATHS.REGIONS)
            else os.path.join(D, _name))
    if not os.path.exists(_src):
        continue
    _dst = os.path.join(os.path.dirname(OUT), _name)
    # Building the sheet beside the draft it was built from is the ordinary
    # case, not an error - and copyfile raises on it.
    if os.path.abspath(_src) != os.path.abspath(_dst):
        shutil.copyfile(_src, _dst)
for _out in _written:
    print("%s  %.1f MB" % (_out, os.path.getsize(_out) / 1e6))
for _pid, _n, _sz in OVERSIZE:
    print("주의: pid %s 한 편이 %d행 · %.1f MB 로 예산(%.0f MB)을 넘습니다 — "
          "문서를 쪼개지 않으므로 그 파일만 큽니다"
          % (_pid, _n, _sz / 1e6, PATHS.SHEET_BUDGET / 1e6))
# 중복은 막힘이 아닙니다 - 그 그림은 다른 행이 세고 있고, 이 행에 물을 것이
# 없습니다. 한 숫자로 합치면 "사람이 할 일"이 실제보다 커 보입니다.
_DUP_BLOCKED = sum(1 for d in DRAFT if BLOCK[d["Draft_ID"]] == "1"
                   and d["Draft_ID"] in DUPLICATE)
print("행 %d · 카드 %d · 시트 %d · 입력 가능 %d · 막음 %d · 중복 %d "
      "(결함 %d + THIN %d + NO_CROP %d)"
      % (len(DRAFT), len(WORK), len(PARTS), COUNTABLE, BLOCKED - _DUP_BLOCKED,
         _DUP_BLOCKED,
         sum(1 for r in DEFECT.values() if r["classification"] == "FAIL"),
         sum(1 for d in DRAFT if d["Crop_Quality_Status"] == "THIN_CROP"),
         sum(1 for d in DRAFT if d["Crop_Quality_Status"] == "NO_CROP")))
_rt = {}
for _v in ROUNDTRIP.values():
    _rt[_v] = _rt.get(_v, 0) + 1
print("왕복 검사: %s" % ", ".join("%s %d" % kv for kv in sorted(_rt.items())))
if AGREEMENT is not None:
    _ag = {}
    for d in DRAFT:
        _v = AGREEMENT.get(d["Draft_ID"], "PENDING")
        _ag[_v] = _ag.get(_v, 0) + 1
    print("영역 합의: %s" % ", ".join("%s %d" % kv for kv in sorted(_ag.items())))
print("빌드 ID", BUILD_ID)
