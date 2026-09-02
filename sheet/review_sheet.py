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
CHOICES = [("TEXT", "빨강 — 지금 크롭", "1", "#c42020"),
           ("PDF", "파랑 — PDF 객체", "2", "#0050eb"),
           ("RASTER", "초록 — 래스터 잉크", "3", "#00962a"),
           ("BLOCKED", "막음 — 셋 다 아님", "0", "#6b6b6b")]
BOX_COLUMN = {"TEXT": "Proposal_Figure_BBox", "PDF": "PDF_BBox",
              "RASTER": "Raster_BBox"}
PAGE_WIDTH = int(os.environ.get("FDT_REVIEW_PAGE_WIDTH", "900"))
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


def page_with_boxes(row, queue_row):
    """The page raster with each method's box outlined in its own colour."""
    from PIL import Image, ImageDraw
    raster = row.get("Page_Raster") or ""
    if not raster or not os.path.exists(raster):
        return ""
    try:
        pw, ph = float(row["Page_Width_Pt"]), float(row["Page_Height_Pt"])
    except (KeyError, ValueError):
        return ""
    if pw <= 0 or ph <= 0:
        return ""
    im = Image.open(raster).convert("RGB")
    draw = ImageDraw.Draw(im)
    sx, sy = im.width / pw, im.height / ph
    wide = max(3, im.width // 260)
    for name, _label, _key, colour in CHOICES[:3]:
        box = _box(queue_row.get(BOX_COLUMN[name]))
        if not box:
            continue
        rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
        draw.rectangle([box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy],
                       outline=rgb, width=wide)
    return _uri(im, PAGE_WIDTH, 75)


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


def build(run, out_dir):
    roundtrip.selfcheck(run)
    queue_path = os.path.join(run, "review", "review_queue.csv")
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
        page = page_with_boxes(row, q)
        shots = []
        for name, label, key, colour in CHOICES[:3]:
            box_text = q.get(BOX_COLUMN[name])
            cut = cut_for(row, box_text) if box_text else None
            shots.append((name, label, colour,
                          _uri(cut, CUT_WIDTH, 72) if cut is not None else ""))
        fp = fingerprint(q)
        buttons = "".join(
            "<button type='button' class='pick' data-id='%s' data-choice='%s' "
            "style='--c:%s'>%s <kbd>%s</kbd></button>"
            % (esc(q["Draft_ID"]), name, colour, esc(label), key)
            for name, label, key, colour in CHOICES)
        cuts = "".join(
            "<figure class='cut'%s><figcaption style='color:%s'>%s</figcaption>%s</figure>"
            % (" data-empty='1'" if not uri else "", colour, esc(label),
               ("<img src='%s' alt=''>" % uri) if uri
               else "<div class='none'>이 방법은 이 캡션에 답하지 않았습니다</div>")
            for name, label, colour, uri in shots)
        cards.append((q, fp,
            "<section class='card' data-id='%s' data-fp='%s' id='r%s'>"
            "<h2><span class='no'>%s</span> %s</h2>"
            "<div class='meta'>%s · p.%s · %s · 합의 <b>%s</b> "
            "(PDF %s · 래스터 %s)</div>"
            "%s<div class='cuts'>%s</div>"
            "<div class='picks'>%s</div>"
            "<label class='note'>메모 <input type='text' data-note='%s' maxlength='200'></label>"
            "<div class='agent' hidden>에이전트 제안: <b>%s</b> — %s</div>"
            "<div class='state' data-state='%s'></div></section>"
            % (esc(q["Draft_ID"]), fp, esc(q["No"]), esc(q["No"]),
               esc(q["Draft_ID"]), esc(q["Source_Document_ID"]), esc(q["Page"]),
               esc(q["Figure_Number"]), esc(q["Agreement"]), esc(q["PDF_Code"]),
               esc(q["Raster_Code"]),
               ("<img class='page' src='%s' alt=''>" % page) if page
               else "<div class='none'>페이지 이미지가 없습니다</div>",
               cuts, buttons, esc(q["Draft_ID"]), esc(q["Agent_Choice"]),
               esc(q["Agent_Note"]), esc(q["Draft_ID"]))))

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
.pick kbd{font:inherit;font-size:11px;opacity:.6;margin-left:4px}
.note{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--mut)}
.note input{flex:1;font:inherit;font-size:13px;padding:5px 7px;
border:1px solid var(--rule);border-radius:3px}
.agent{margin-top:8px;font-size:12.5px;color:#8a5a00;background:#fffaf0;
border:1px solid #e8d9b8;border-radius:3px;padding:6px 9px}
.warn{background:#fdf4f4;border:1px solid #e0bcbc;border-radius:4px;padding:10px 12px;
margin:0 0 16px;font-size:13.5px}
</style><div class='wrap'>
<h1>그림 영역 판정 <span style='color:var(--mut);font-weight:400'>__PART__</span></h1>
<p class='lede'>두 방법이 서로 확인해 주지 못한 %(n)d행입니다. 빨강은 지금 크롭이 잘린 상자,
파랑은 PDF가 그리는 객체, 초록은 페이지 잉크입니다. 아래 세 그림은 각 상자가
<b>실제로 잘라낼 것</b>입니다. 하나를 고르거나, 셋 다 그림이 아니면 막음을 고르십시오.
빈칸으로 두면 그 행은 막힌 채 남습니다.</p>
<div class='warn' id='warn' hidden></div>
<div class='bar'><button type='button' id='save'>고른 것 CSV로 내려받기</button>
<button type='button' id='next'>다음 빈 행</button>
<button type='button' id='toggle'>에이전트 제안 보기</button>
<span class='count' id='count'></span>
<span class='count'>키보드: 1 빨강 · 2 파랑 · 3 초록 · 0 막음 · n 다음</span></div>
<div class='build' style='color:var(--mut);font-size:12px;margin:-8px 0 14px'>빌드 %(build)s</div>
"""

TAIL = """</div><script>
const ROWS = __ROWS__, COLUMNS = __COLUMNS__, QUEUE = __QUEUE__, BUILD = __BUILD__;
const PART = __PARTNO__;
const KEY = 'fdt-review-' + BUILD;
const VALID = ['TEXT','PDF','RASTER','BLOCKED'];
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
function persist(){
  try { window.localStorage.setItem(KEY, JSON.stringify(store)); }
  catch (err) { complain('저장에 실패했습니다 (' +
    (err && err.name ? err.name : '알 수 없는 오류') + '). CSV로 내려받으십시오.'); }
}
// A stored answer belongs to the pictures it was made on. The fingerprint
// carries the crop digest and all three boxes; if any of them changed, the
// answer is not about what is on screen and is dropped.
const cards = Array.from(document.querySelectorAll('.card'));
const byId = {}; cards.forEach(c => byId[c.dataset.id] = c);
let dropped = 0;
Object.keys(store).forEach(id => {
  const card = byId[id];
  if (!card) return;
  if (!store[id] || store[id].fp !== card.dataset.fp) { delete store[id]; dropped++; }
  else if (VALID.indexOf(store[id].choice) < 0) { delete store[id]; dropped++; }
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
  const n = cards.filter(c => store[c.dataset.id]).length;
  document.getElementById('count').textContent = n + ' / ' + cards.length + ' 판정함';
}
function choose(card, choice){
  if (VALID.indexOf(choice) < 0) return;
  const id = card.dataset.id, note = card.querySelector('input[data-note]');
  if (store[id] && store[id].choice === choice) delete store[id];
  else store[id] = { choice: choice, fp: card.dataset.fp, note: note ? note.value : '' };
  persist(); paint(card);
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('.pick');
  if (b) choose(b.closest('.card'), b.dataset.choice);
});
document.addEventListener('input', ev => {
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
  const map = { '1':'TEXT', '2':'PDF', '3':'RASTER', '0':'BLOCKED' };
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
    q['Human_Note'] = kept && kept.note ? kept.note : '';
    out.push(COLUMNS.map(c => csvCell(q[c])).join(','));
  });
  const blob = new Blob(['\\ufeff' + out.join('\\n')], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'review_queue_' + PART + '.csv';
  document.body.appendChild(a); a.click(); a.remove();
});
cards.forEach(paint);
</script>
"""


if __name__ == "__main__":
    run = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(run, "review")
    sys.exit(build(run, out))
