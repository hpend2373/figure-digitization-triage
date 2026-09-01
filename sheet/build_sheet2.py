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

BUILD_ID = "sheet-%s-%s" % (
    datetime.date.today().isoformat(),
    hashlib.sha256(
        io.open(os.path.join(D, "figure_intake_draft.csv"), "rb").read()
    ).hexdigest()[:8])


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


SHARED_CROP = BR.shared_crop_map(_crop_digests(DRAFT, D))

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
                             shared_with=SHARED_CROP.get(d["Draft_ID"], ()))


def caution(d):
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


def pages_text(L):
    """The ledger's own blank, preserved. Never printed as a number."""
    v = (L.get("Page_Count") or "").strip()
    return (v + "쪽") if v else "쪽수 없음"


P = []
w = P.append
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

w("""<div class='stop'><b>아직 계수를 시작하지 마십시오.</b> 이 2판은
2차 감사가 지적한 <b>안전성 결함</b>(입력 검증 없음, 저장 실패 무경고,
빈칸을 0으로 표시, 의심 사유 미표시, 문서 8편 누락)을 고친 것입니다.
<b>캡션 인식과 그림 식별자(2단계), 크롭 재생성(3단계)은 아직입니다.</b>
확인된 결함이 있는 크롭은 입력을 막아 두었고, 계수는 4단계 재감사를
통과한 뒤에 시작합니다.</div>""")

w("""<div class='note'>각 그림에 <b>축 영역(패널)이 몇 개</b> 인쇄되어
있는지 세어 입력합니다. 기계는 이 숫자를 제안하지 않습니다.
<ul>
<li><b>빈칸 = 아직 안 봤다</b>, <b>0 = 축 영역이 없다</b>. 둘은 다른
값이며 내보내기에서도 구별됩니다.</li>
<li>0 이상 %d 이하의 <b>정수만</b> 저장됩니다. 그 밖의 값은 저장되지도,
내보내지지도 않습니다.</li>
<li><b>붉은 칸</b>은 크롭 결함이 확인되어 입력을 막은 행입니다.
숫자를 넣을 수 없고, <code>BLOCKED_BAD_CROP</code>으로 내보내집니다.</li>
<li>입력값은 브라우저에 저장되며, <b>행의 내용이 바뀌면 되살아나지
않습니다</b> — 지문이 다르면 다른 그림으로 보고 값을 버립니다.</li>
</ul></div>""" % 40)

w("<div class='bar'><button id='dl'>CSV 내려받기</button>"
  "<button class='g' id='clr'>입력 지우기</button>"
  "<span class='count' id='cnt'></span></div>")

for wl in sorted(WORK, key=lambda r: (r["priority"], int(r["pid"]))):
    pid = wl["pid"]
    doc = DOC_OF[pid]
    L = LEDGER[doc]
    ds = BYDOC.get(doc, [])
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
        continue
    w("<div class='gal'>")
    for d in ds:
        did = d["Draft_ID"]
        p = os.path.join(D, d["Figure_Crop"]) if d["Figure_Crop"] else ""
        img = (("<img src='%s' alt=''>" % thumb(p))
               if p and os.path.exists(p) else
               "<div class='cap'>[페이지 이미지 없음 — 원문에 그림이 "
               "포함되어 있지 않습니다]</div>")
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
             esc((d["Caption_Text"] or "")[:120])))
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
        w("<div class='msg' data-msg='%s'></div></div>" % esc(did))
    w("</div>")
    w("</div>")

# beside this file, not at an absolute path: the third audit could not
# rebuild the sheet in a clean checkout because these two were pinned to
# /tmp/intake.
_HERE = os.path.dirname(os.path.abspath(__file__))
w("<script>%s</script>" % io.open(os.path.join(_HERE, "sheet_logic.js"),
                                  encoding="utf-8").read())
w("<script>const ROWS=%s;const BUILD_ID=%s;</script>"
  % (json.dumps(ROWS, ensure_ascii=False), json.dumps(BUILD_ID)))
w(io.open(os.path.join(_HERE, "sheet_page.js"), encoding="utf-8").read())
w("</div></body></html>")

io.open(OUT, "w", encoding="utf-8").write("\n".join(P))

# THE SHEET AND ITS DATA TRAVEL TOGETHER. The last delivery put a 639-row page
# beside a 604-row CSV from an older walk, so nothing in the bundle described
# what was on screen. Copying them here means the pair cannot drift again.
import shutil
for _name in ("figure_intake_draft.csv", "intake_document_status.csv"):
    shutil.copyfile(os.path.join(D, _name),
                    os.path.join(os.path.dirname(OUT), _name))
print("%s  %.1f MB" % (OUT, os.path.getsize(OUT) / 1e6))
print("행 %d · 카드 %d · 입력 가능 %d · 막음 %d (결함 %d + THIN %d + NO_CROP %d)"
      % (len(DRAFT), len(WORK), COUNTABLE, BLOCKED,
         sum(1 for r in DEFECT.values() if r["classification"] == "FAIL"),
         sum(1 for d in DRAFT if d["Crop_Quality_Status"] == "THIN_CROP"),
         sum(1 for d in DRAFT if d["Crop_Quality_Status"] == "NO_CROP")))
print("빌드 ID", BUILD_ID)
