# -*- coding: utf-8 -*-
"""사람이 오차 정의를 판정하는 페이지를 냅니다.

    python3 errorbar_review_page.py --run RUN --pdf-root ~/Downloads/pdfs \
                                    --out RUN/errorbar_review.html

`record_errorbar.py`가 docstring에서 이름을 대고 있던 그 페이지입니다. 오래
없었고, 그동안 답은 CSV를 손으로 채워 넣는 수밖에 없었습니다.

이 페이지가 답하게 하려는 질문은 하나입니다: **이 문장이 이 그림들의 오차
막대를 말하는가.** 관문(`record_errorbar`)은 문장이 논문에 있는지, 그 문장이
그 종류를 말하는지까지 봅니다. 관문이 볼 수 없는 것은 그 문장이 *이* 그림에
대한 것인지입니다 - 참가자 나이를 적은 "29.3 ± 3.8 years (SD)"도 논문에 있고
SD를 말하니까요. 그래서 페이지는 문장과 그림을 나란히 놓습니다.

세 가지를 하지 않습니다.

  * 종류를 대신 고르지 않습니다. 후보에 붙은 종류는 누가 제안했든 제안이고,
    고르는 칸은 비어서 나갑니다.
  * `Verified_In_Source`를 대신 채우지 않습니다. 사람이 누른 것만 1이 됩니다.
  * 기록하지 않습니다. 이 페이지가 내는 것은 CSV이고, 넣는 것은 사람이
    `record_errorbar.py`를 돌려서 합니다.
"""
import argparse
import base64
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kernel                                                    # noqa: E402

DRAFT = "figure_intake_draft.csv"
#: 무엇이 남았는지 정하는 파일. 계획서가 만든 답안지이고, 한 줄이 논문 한
#: 편입니다. `errorbar_unstated.csv`가 아닙니다 - 그 파일은 계수가 끝나기
#: 전에 만들어졌고, 지금은 계획에서 빠진 논문까지 들고 있습니다.
QUEUE = "errorbar_answers_TEMPLATE.csv"
CAPTIONS = "caption_fulltext.csv"
COUNTS = "observed_panel_counts.csv"
CANDIDATES = "errorbar_candidates.csv"
LOGIC = "errorbar_page.js"

#: 사람이 손댈 자리가 얼마나 되는지로 나눈 세 묶음. 순서를 바꾸는 것이지
#: 답을 바꾸는 것이 아닙니다.
GROUPS = (
    ("pass", "관문을 지나갈 후보가 있는 논문",
     "인용문·쪽·종류가 이미 맞습니다. 남은 것은 <b>이 문장이 이 그림에 "
     "대한 것인가</b> 하나입니다."),
    ("snag", "후보는 있으나 무언가 걸리는 논문",
     "관문이 무엇을 걸었는지 각 후보 아래에 적혀 있습니다. 고치거나, "
     "다른 문장을 찾거나, 처분(DROP/NOT_DATA)으로 답하십시오."),
    ("none", "후보가 없는 논문",
     "찾아 둔 문장이 없습니다. 논문을 보고 직접 적거나, 정의가 없다면 "
     "그렇게 답하십시오."),
)

#: 크롭을 페이지에 싣는 크기. 오차 막대가 무엇인지 보려면 막대가 보여야 하고,
#: 78개를 원본 크기로 실으면 브라우저가 열지 못합니다.
THUMB = (560, 560)


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def esc(text):
    return (str(text if text is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def thumb(path):
    """크롭 한 장을 data URL로. 못 읽으면 빈 문자열 - 없는 그림은 없다고 둡니다."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        from PIL import Image
    except Exception:                                   # pragma: no cover
        return ""
    try:
        im = Image.open(path)
        im.thumbnail(THUMB)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72)
    except Exception:                                   # noqa: BLE001
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def verdicts(run, pdf_root, candidates):
    """{후보 줄 번호: (코드, 말)} - 관문이 이 후보를 어떻게 볼지, 미리.

    사람이 고른 뒤에야 거부를 보면, 고르는 동안에는 알 수 없던 것을 나중에
    통보받는 셈입니다. 관문의 판정은 이 페이지가 먼저 물어봅니다 - 답을
    대신 정하지 않고, 무엇이 걸릴지만 보여 줍니다.
    """
    out = {}
    if not pdf_root:
        return out
    try:
        import record_errorbar as RE
    except Exception:                                   # pragma: no cover
        return out
    cache = {}
    for i, row in enumerate(candidates):
        doc = (row.get("Source_Document_ID") or "").strip()
        code = (row.get("Dispersion_Type") or "").strip()
        if not doc or not code:
            continue
        if doc not in cache:
            cache[doc] = RE.read_source(run, doc, pdf_root)
        source, _why = cache[doc]
        # `Verified_In_Source`를 참으로 두는 것은 진단이기 때문입니다. 이 값은
        # 화면에도 파일에도 나가지 않습니다 - 여기서 거짓으로 두면 모든 후보가
        # "사람이 확인하지 않았다" 하나로만 보이고, 정작 보여 주려던 인용문
        # 문제는 가려집니다.
        probe = dict(row, Verified_In_Source="1")
        problems = RE.check_answer(probe, source)
        out[i] = problems[0] if problems else ("OK", "관문을 지나갑니다")
    return out


CSS = """<style>
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;
margin:0;background:#f4f4f2;color:#1a1a1a}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #d8d8d4;
padding:14px 20px;z-index:5}
h1{font-size:17px;margin:0 0 4px}
.note{color:#5a5a56;font-size:13px;margin:6px 0 0;max-width:80ch}
main{padding:20px;max-width:1180px;margin:0 auto}
h3.sec{font-size:15px;margin:26px 0 2px;padding-top:8px;border-top:2px solid #ddddd6}
.sec-why{margin:0 0 12px}
.doc{background:#fff;border:1px solid #ddddd8;border-radius:8px;margin:0 0 22px;
padding:16px 18px}
.doc.done{border-color:#6b8f6b;background:#f6faf6}
h2{font-size:14px;margin:0 0 2px;font-family:ui-monospace,Menlo,monospace;
word-break:break-all}
.sub{color:#66665f;font-size:13px;margin:0 0 12px}
.figs{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 14px}
.fig{border:1px solid #e2e2dd;border-radius:6px;padding:6px;background:#fbfbfa}
.fig img{display:block;max-width:270px;height:auto;border-radius:3px}
.fig .nofig{width:120px;height:60px;display:flex;align-items:center;
justify-content:center;color:#9a9a92;font-size:12px}
.fig .cap{font-size:12px;color:#55554f;margin-top:5px}
.cand{border:1px solid #e2e2dd;border-radius:6px;padding:10px 12px;margin:0 0 9px;
background:#fbfbfa}
.cand.ok{border-color:#b7d3b9}
.cand.picked{border-color:#3b6ea5;background:#f2f7fd}
.cand.own{display:block;font-size:13px;color:#55554f}
blockquote{margin:6px 0;padding:8px 11px;background:#fff;border-left:3px solid #c9c9c2;
font-size:14px;white-space:pre-wrap}
.meta{font-size:12px;color:#55554f;margin-top:4px}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;
border:1px solid;margin-right:6px;vertical-align:1px}
.ok{color:#2f6b34;border-color:#9dc4a0;background:#eef7ef}
.warn{color:#8a5a12;border-color:#dcc08a;background:#fdf6e9}
.row{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:12px;
padding-top:12px;border-top:1px solid #eeeee9}
label{font-size:13px}
.verify{padding:3px 8px;border:1px solid #dcc08a;border-radius:5px;background:#fdf6e9}
select,input[type=text]{font:13px inherit;padding:5px 7px;border:1px solid #c9c9c2;
border-radius:4px;background:#fff}
.state{font-size:13px;color:#8a5a12;margin-top:9px}
.state.ready{color:#2f6b34}
button{font:14px inherit;padding:8px 15px;border:1px solid #b9b9b2;border-radius:5px;
background:#fff;cursor:pointer}
button:hover{background:#f2f2ee}
.count{font-variant-numeric:tabular-nums;color:#55554f;font-size:13px;font-weight:400}
</style></head><body>"""


def answer_row(key):
    """사람이 답을 적는 줄. 논문 단위 카드와 그림 단위 카드가 같은 줄을 씁니다.

    한 벌만 두는 것은 두 벌이 어긋나면 한쪽 화면에서만 확인 칸이 사라지는 일이
    실제로 일어나기 때문이고, 변이 하나가 두 곳에 걸려 무엇을 재는지 알 수
    없게 되기 때문입니다.
    """
    out = []
    w = out.append
    w("<div class='row'>")
    w("<label>종류 <select data-code='%s'><option value=''>고르지 않음</option>"
      % esc(key))
    for t in list(kernel.FIG_DISPERSION_TYPES) + ["DROP", "NOT_DATA", "HOLD"]:
        w("<option value='%s'>%s</option>" % (esc(t), esc(t)))
    w("</select></label>")
    w("<label>인용문 <input type='text' data-quote='%s' size='48'></label>"
      % esc(key))
    w("<label>쪽 <input type='text' data-page='%s' size='4'></label>" % esc(key))
    w("<label class='verify'><input type='checkbox' data-verified='%s'> "
      "<b>PDF에서 이 문장을 직접 봤다</b></label>" % esc(key))
    w("<label>메모 <input type='text' data-note='%s' size='22'></label>"
      % esc(key))
    w("</div>")
    w("<div class='state' data-state='%s'></div>" % esc(key))
    return "\n".join(out)


def fig_cell(run, row, num, page, wide=""):
    """그림 한 칸. 크롭이 없으면 없다고 적습니다 - 빈 자리는 아무 말도 안 합니다."""
    out = []
    w = out.append
    src = thumb(os.path.join(run, (row.get("Figure_Crop") or "") if row else ""))
    w("<div class='fig'>")
    if src:
        w("<img src='%s' alt='%s'%s>" % (src, esc(num), wide))
    else:
        w("<div class='nofig'>크롭 없음</div>")
    w("<div class='cap'>%s · p.%s</div>" % (esc(num), esc(page or "?")))
    w("</div>")
    return "\n".join(out)


def build(run, pdf_root="", log=print):
    """(html, 문서 수, 후보 수). 페이지 한 장과 그 안에 무엇이 들었는지."""
    draft = _rows(os.path.join(run, DRAFT))
    queue = _rows(os.path.join(run, QUEUE))
    cands = _rows(os.path.join(run, CANDIDATES))
    if not queue:
        raise SystemExit("%s에 기다리는 줄이 없습니다 — 이 페이지는 그 파일이 "
                         "정하는 목록만 보여 줍니다." % QUEUE)

    #: 한 그림 번호에 초안이 여러 후보를 잡아 두면, 보여 줄 것은 계수가 남긴
    #: 행이지 마지막 행이 아닙니다. 차단된 크롭을 집으면 사람은 본문 글자만
    #: 담긴 그림을 보고 판정하게 됩니다.
    blocked = set(r["Draft_ID"] for r in _rows(os.path.join(run, COUNTS))
                  if (r.get("Entry_Status") or "").strip()
                  in ("BLOCKED_BAD_CROP", "BLOCK_CONFIRMED"))
    fig_of = {}
    for r in draft:
        if r["Draft_ID"] in blocked:
            continue
        fig_of[(r["Source_Document_ID"], (r.get("Figure_Number") or "").strip())] = r

    said = verdicts(run, pdf_root, cands)
    cand_of = {}
    for i, c in enumerate(cands):
        cand_of.setdefault((c.get("Source_Document_ID") or "").strip(),
                           []).append((i, c))

    def group_of(doc):
        mine = cand_of.get(doc, [])
        if not mine:
            return "none"
        for i, _c in mine:
            if said.get(i, ("", ""))[0] == "OK":
                return "pass"
        return "snag" if said else "pass"

    buckets = dict((g, []) for g, _t, _w in GROUPS)
    for row in queue:
        buckets[group_of((row.get("Source_Document_ID") or "").strip())].append(row)

    out = []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>오차 정의 판정 — 논문 %d편</title>" % len(queue))
    w(CSS)
    w("<header><h1>오차 정의 판정 <span class='count' id='left'></span></h1>")
    w("<p class='note'><b>묻는 것은 하나입니다 — 이 문장이 <em>이 그림들</em>의 "
      "오차 막대를 말하는가.</b> 문장이 논문에 있는지, 그 문장이 그 종류를 "
      "말하는지는 관문이 이미 봤고 후보마다 적어 두었습니다. 관문이 볼 수 없는 "
      "것은 그 문장이 이 그림에 대한 것인지입니다 — 참가자 나이를 적은 "
      "\u201cmean age 29.3 \u00b1 3.8 years\u201d도 논문에 있고 SD처럼 "
      "보이니까요.</p>")
    w("<p class='note'>후보에 붙은 종류는 <b>제안</b>입니다. 고르는 칸은 비어 "
      "있고, 고르는 것은 사람이 합니다. 그리고 <b>PDF에서 그 문장을 직접 "
      "보셨을 때만</b> 확인 칸을 눌러 주세요 — 그 칸이 이 페이지가 있는 "
      "이유입니다.</p>")
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    docs_js = []
    for key, title, why in GROUPS:
        rows = buckets[key]
        if not rows:
            continue
        w("<h3 class='sec'>%s <span class='count'>%d편</span></h3>"
          % (esc(title), len(rows)))
        w("<p class='note sec-why'>%s</p>" % why)
        for row in rows:
            doc = (row.get("Source_Document_ID") or "").strip()
            docs_js.append(doc)
            w(card(run, doc, row, fig_of, cand_of.get(doc, []), said))

    w("</main><script>")
    w("var DOCS = %s;" % json.dumps(docs_js, ensure_ascii=False))
    #: 논문 단위로 물을 때는 열쇠가 곧 논문 이름이라 심을 것이 없습니다.
    w("var META = {};")
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    log("논문 %d편 · 후보 %d개 (관문 통과 %d) · 그림 %d개"
        % (len(queue), len(cands),
           sum(1 for v in said.values() if v[0] == "OK"),
           sum(len(figures(row)) for row in queue)))
    return "\n".join(out), len(queue), len(cands)


def figures(row):
    """이 논문에서 이 정의가 붙을 그림 번호들. 계획서가 적어 준 그대로."""
    return [f.strip() for f in (row.get("참고_그림") or "").split(",") if f.strip()]


def card(run, doc, row, fig_of, mine, said):
    out = []
    w = out.append
    w("<div class='doc' data-doc='%s'>" % esc(doc))
    w("<h2>%s</h2>" % esc(doc))
    w("<p class='sub'>%s · 이 정의가 붙을 그림 %d개 · 기계가 본 것: %s</p>"
      % (esc(row.get("참고_원본파일")), len(figures(row)),
         esc(row.get("참고_기계가본것") or "—")))

    w("<div class='figs'>")
    for num in figures(row):
        d = fig_of.get((doc, num), {})
        w(fig_cell(run, d, num, d.get("Page")))
    w("</div>")

    for i, c in mine:
        code, msg = said.get(i, ("", ""))
        quote = (c.get("Errorbar_Definition_Source") or "").strip()
        w("<div class='cand%s' data-cand='%s'>" % (" ok" if code == "OK" else "", i))
        w("<label class='pick'><input type='radio' name='pick-%s' data-pick='%s' "
          "data-doc='%s' data-qtext=\"%s\" data-ptext='%s'> "
          "<b>%s</b> · p.%s · 후보 %s</label>"
          % (esc(doc), i, esc(doc), esc(quote), esc(c.get("Found_On_Page")),
             esc(c.get("Dispersion_Type") or "종류 미정"),
             esc(c.get("Found_On_Page")), esc(c.get("후보순위") or "?")))
        if quote:
            w("<blockquote>%s</blockquote>" % esc(quote))
        if code:
            w("<div><span class='badge %s'>%s</span><span class='meta'>%s</span></div>"
              % ("ok" if code == "OK" else "warn", esc(code), esc(msg)))
        bits = []
        for label, key in (("어디", "근거자리"),
                           ("이 문장이 설명하는 것", "이문장이설명하는것"),
                           ("애매한 점", "왜애매한가")):
            if (c.get(key) or "").strip():
                bits.append("%s: %s" % (label, c[key].strip()))
        if bits:
            w("<div class='meta'>%s</div>" % esc(" · ".join(bits)))
        w("</div>")

    if not mine:
        hint = (row.get("참고_찾을만한곳") or "").strip()
        w("<div class='cand'><div class='meta'>찾아 둔 후보가 없습니다."
          "%s</div></div>"
          % ((" 기계가 건져 둔 조각: " + esc(hint)) if hint else ""))

    w("<label class='cand own'><input type='radio' name='pick-%s' "
      "data-pick='own' data-doc='%s'> 위에 맞는 것이 없다 — 직접 적기</label>"
      % (esc(doc), esc(doc)))

    w(answer_row(doc))
    w("</div>")
    return "\n".join(out)


def build_figures(run, docs, pdf_root="", log=print):
    """(html, 그림 수). 한 논문을 **그림마다** 묻는 페이지.

    논문이 그림의 종류에 따라 다르게 적었을 때 씁니다. 실제 문장:

        Data are presented as mean ± s.e.m for text and bar plots, and as
        minimum, 25th percentile, median, 75th percentile, and maximum for
        box plots

    이 문장은 논문 전체에 대해 참이지만 그림 하나에 대해서는 답이 아닙니다 -
    그 그림이 막대인지 상자인지는 그림을 본 사람만 압니다. 규칙으로 만들지
    않은 이유는 코퍼스 전체에서 이런 진술이 둘뿐이고 하나는 이미 옳게
    읽히기 때문입니다. 하나짜리 규칙은 이 저장소에서 장식입니다.

    답 CSV는 `Figure_Number`를 싣지만, `record_errorbar`는 아직 논문 단위로만
    적습니다. 그림마다 다른 답을 적으려면 관문을 고쳐야 하고, 그 고침은 실제로
    갈리는 그림이 있는지 본 뒤에 하는 것이 맞습니다.
    """
    draft = _rows(os.path.join(run, DRAFT))
    caption = dict(((r["Source_Document_ID"], (r.get("Figure_Number") or "").strip()), r)
                   for r in _rows(os.path.join(run, CAPTIONS)))
    want = set(docs)
    #: 차단된 크롭은 내놓지 않습니다. 초안에는 한 그림 번호에 후보가 여럿
    #: 잡히고 계수 단계가 그중 하나만 남기는데, 초안을 그대로 펴면 이미
    #: 처리된 중복이 사람 앞에 다시 나타납니다 - 실제로 그렇게 나타났고,
    #: 계획서에는 없는 문제를 있다고 보고했습니다.
    counted = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, COUNTS)))
    mine = []
    for r in draft:
        if r["Source_Document_ID"] not in want:
            continue
        status = (counted.get(r["Draft_ID"], {}).get("Entry_Status") or "").strip()
        if status in ("BLOCKED_BAD_CROP", "BLOCK_CONFIRMED"):
            continue
        mine.append(r)
    if not mine:
        raise SystemExit("초안에 %s가 없습니다." % ", ".join(sorted(want)))

    said = {}
    for r in _rows(os.path.join(run, CAPTIONS)):
        d = r["Source_Document_ID"]
        if d in want and d not in said:
            said[d] = ((r.get("Doc_Errorbar_Definition") or "").strip(),
                       (r.get("Doc_Errorbar_Evidence") or "").strip(),
                       (r.get("Doc_Errorbar_Page") or "").strip())

    out, meta, keys = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>그림마다 묻기 — %s</title>" % esc(", ".join(sorted(want))))
    w(CSS)
    w("<header><h1>그림마다 묻기 <span class='count' id='left'></span></h1>")
    w("<p class='note'>이 논문의 Methods는 <b>그림의 종류에 따라 다르게</b> "
      "적었습니다. 그래서 논문 전체에 하나의 답을 붙일 수 없습니다 — 그림이 "
      "막대인지 상자인지는 그림을 본 사람만 압니다.</p>")
    for doc in sorted(want):
        code, ev, page = said.get(doc, ("", "", ""))
        if ev:
            w("<p class='note'><b>%s</b> (지금 붙어 있는 값: %s, p.%s)</p>"
              % (esc(doc), esc(code or "없음"), esc(page)))
            w("<blockquote style='max-width:88ch'>%s</blockquote>" % esc(ev))
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    for r in sorted(mine, key=lambda x: (x["Source_Document_ID"],
                                         len((x.get("Figure_Number") or "")),
                                         x.get("Figure_Number") or "")):
        doc = r["Source_Document_ID"]
        num = (r.get("Figure_Number") or "").strip() or "번호 없음"
        key = "%s::%s" % (doc, num)
        keys.append(key)
        meta[key] = {"doc": doc, "figure": num}
        c = caption.get((doc, num), {})
        w("<div class='doc' data-doc='%s'>" % esc(key))
        w("<h2>%s · %s</h2>" % (esc(doc), esc(num)))
        w("<p class='sub'>p.%s · 패널 %s개 · 캡션이 말한 종류: %s</p>"
          % (esc(r.get("Page")),
             esc((counted.get(r["Draft_ID"], {}).get("Observed_Panel_Count")
                  or "?")),
             esc(c.get("Errorbar_Definition") or "—")))
        w("<div class='figs'>%s</div>"
          % fig_cell(run, r, num, r.get("Page"),
                     wide=" style='max-width:520px'"))
        # 캡션 전문이 비어 있어도 인테이크가 잡은 줄은 있습니다. 파이프라인은
        # 그 줄을 `Caption_Full`로 승격하지 않습니다 - 쪽 글자와 대조되지 않은
        # 줄이 답의 근거가 되면 안 되니까요(`test_caption_fulltext`가 그것을
        # 지킵니다). 그러나 화면에서까지 감추면 사람은 빈칸을 보고, 아무 말도
        # 하지 않는 캡션과 읽지 못한 캡션을 구별할 수 없습니다. 그래서 여기서만
        # 보여 주고, 확인되지 않았다고 이름을 붙입니다.
        cap = (c.get("Caption_Full") or "").strip()
        if cap:
            w("<div class='meta'>%s</div>" % esc(cap[:400]))
        else:
            line = (c.get("Caption_Line") or "").strip()
            if line:
                w("<div class='meta'><b>캡션 전문을 읽지 못했습니다</b> "
                  "(%s) — 인테이크가 잡은 줄: %s</div>"
                  % (esc(c.get("Caption_Full_Status") or "?"), esc(line[:300])))
            else:
                w("<div class='meta'><b>캡션이 없습니다</b> (%s) — 이 쪽의 "
                  "글자층에 캡션이 없습니다. PDF를 직접 보셔야 합니다.</div>"
                  % esc(c.get("Caption_Full_Status") or "?"))
        w(answer_row(key))
        w("</div>")

    w("</main><script>")
    w("var DOCS = %s;" % json.dumps(keys, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    log("논문 %d편 · 그림 %d개" % (len(want), len(keys)))
    return "\n".join(out), len(keys)


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_errorbar_review';
  var states = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
  catch (e) { states = {}; }

  function st(doc) {
    if (!states[doc]) states[doc] = { code: '', quote: '', page: '',
                                      verified: false, note: '' };
    // 열쇠가 "논문::그림"일 때, 답으로 나갈 이름은 여기서 정해집니다.
    var m = META[doc];
    if (m) { states[doc].doc = m.doc; states[doc].figure = m.figure; }
    return states[doc];
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {}
  }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  function paint(doc) {
    var s = st(doc);
    var got = answerOf(doc, s);
    var box = q("[data-state=\"" + esc(doc) + "\"]");
    if (box) {
      box.textContent = got.ready ? '답이 되었습니다 — ' + got.row.Dispersion_Type
                                  : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-doc=\"" + esc(doc) + "\"]");
    if (card) card.classList.toggle('done', got.ready);
    var sel = q("select[data-code=\"" + esc(doc) + "\"]");
    if (sel && sel.value !== s.code) sel.value = s.code;
    var qq = q("input[data-quote=\"" + esc(doc) + "\"]");
    if (qq && qq.value !== s.quote) qq.value = s.quote;
    var pp = q("input[data-page=\"" + esc(doc) + "\"]");
    if (pp && pp.value !== s.page) pp.value = s.page;
    var vv = q("input[data-verified=\"" + esc(doc) + "\"]");
    if (vv) vv.checked = !!s.verified;
    var nn = q("input[data-note=\"" + esc(doc) + "\"]");
    if (nn && nn.value !== s.note) nn.value = s.note;
    var left = remaining(DOCS, states);
    q('#left').textContent = '· 남은 문서 ' + left + ' / ' + DOCS.length;
  }

  all('input[data-pick]').forEach(function (r) {
    r.addEventListener('change', function () {
      var doc = r.getAttribute('data-doc');
      var s = st(doc);
      if (r.getAttribute('data-pick') !== 'own') {
        // 후보를 고르면 문장과 쪽은 그 후보의 것으로 채웁니다. 종류는 채우지
        // 않습니다 - 고르는 것이 이 페이지가 사람에게 청하는 일입니다.
        // 라디오가 들고 있는 이름은 `data-qtext`/`data-ptext`입니다. 적는
        // 칸과 같은 이름을 쓰면 아래 bind가 라디오까지 붙잡고, 라디오에서
        // 읽은 "문서 이름"이 실은 인용문이 됩니다.
        s.quote = r.getAttribute('data-qtext') || '';
        s.page = r.getAttribute('data-ptext') || '';
      }
      all('.cand').forEach(function (c) { c.classList.remove('picked'); });
      var card = r.closest('.cand');
      if (card) card.classList.add('picked');
      save(); paint(doc);
    });
  });
  function bind(sel, attr, read) {
    all(sel).forEach(function (el) {
      var doc = el.getAttribute(attr);
      var ev = el.type === 'checkbox' ? 'change' : 'input';
      el.addEventListener(ev, function () {
        var s = st(doc);
        read(s, el);
        save(); paint(doc);
      });
    });
  }
  bind('select[data-code]', 'data-code', function (s, el) { s.code = el.value; });
  bind('input[data-quote]', 'data-quote', function (s, el) { s.quote = el.value; });
  bind('input[data-page]', 'data-page', function (s, el) { s.page = el.value; });
  bind('input[data-verified]', 'data-verified',
       function (s, el) { s.verified = el.checked; });
  bind('input[data-note]', 'data-note', function (s, el) { s.note = el.value; });

  q('#dl').addEventListener('click', function () {
    var csv = buildCsv(DOCS, states);
    var n = DOCS.length - remaining(DOCS, states);
    if (!n) { q('#msg').textContent = '답이 된 줄이 아직 없습니다.'; return; }
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'errorbar_answers.csv';
    a.click();
    q('#msg').textContent = n + '줄을 내려받았습니다.';
  });

  DOCS.forEach(paint);
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--pdf-root", default="",
                    help="관문이 인용문을 대조할 PDF 뿌리. 없으면 관문 판정을 "
                         "적지 않고 후보만 보여 줍니다.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--figures", nargs="*", default=[],
                    help="이 논문들은 그림마다 묻습니다. 논문이 그림 종류에 "
                         "따라 다르게 적었을 때.")
    a = ap.parse_args(argv)
    if a.figures:
        html, _n = build_figures(os.path.expanduser(a.run), a.figures,
                                 os.path.expanduser(a.pdf_root))
    else:
        html, _docs, _cands = build(os.path.expanduser(a.run),
                                    os.path.expanduser(a.pdf_root))
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
