# -*- coding: utf-8 -*-
"""사람이 그림 위에 패널을 긋고, 패널마다 무엇이 그려졌는지 말하는 페이지.

    python3 panel_page.py --run DIR --queue DIR/seg/dig.csv \\
        --proposals DIR/seg/boxes.jsonl --out DIR/seg/panels_1.html \\
        --chunk 1 --of 10

계획서 뒤에 남은 일의 대부분이 이것입니다. 그림 297장에 패널 1019개가 있고,
그 패널마다 **어디**인지와 **무엇**인지를 아무도 적어 두지 않았습니다. 고르는
것은 기계의 몫입니다: 자리는 그림을 본 모형이 제안하고 잉크 분할이 축 틀에
맞추며, 종류(막대냐 선이냐 상자냐 점이냐, 축은 있지만 읽을 값이 없는 패널이냐)도
같은 제안에 들어 있습니다. 그 제안이 크롭 위에 그려지고 종류가 미리 골라진 채로
나갑니다. 사람의 몫은 **확인**입니다 - 맞으면 그대로 두고, 틀리면 지우고 다시
긋거나 종류를 바꿉니다. 그대로 받았는지 고쳤는지는 `Region_Source`·`Mark_Source`
로 따로 적힙니다.

눈금 값은 이 페이지에 없습니다. 확인된 자리가 600 DPI로 옮겨진 뒤
`geometry_proposer`가 축을 읽고, 그것을 `geometry_page`가 사람에게 내밉니다.
여기서 정하는 것은 자리와 종류뿐입니다.

무엇이 답이 되는지는 여기 없고 `panel_page.js`에 있습니다. 좌표는 크롭 픽셀
(200 DPI)이고, 화면은 그림을 줄여 보이되 좌표는 줄이기 전으로 돌려서 내보냅니다.

내려받는 파일은 `panel_answers.csv`이고, `record_panels.py`가 그것을 받습니다.
**이 페이지는 관문이 아닙니다** - 그 관문이 답이 실제로 낸 그림에 대한 것인지,
상자가 실제 크롭 안에 드는지를 다시 봅니다.
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

from page_bits import CSS, esc                                   # noqa: E402

DRAFTS = "figure_intake_draft.csv"
LOGIC = "panel_page.js"

#: 화면에 보이는 그림의 가장 큰 너비. 상자를 긋기엔 이만하면 되고, 크롭을
#: 원본대로 실으면 한 묶음이 수십 MB가 됩니다.
SHOW_WIDTH = 900

#: 화면에 적는 말. `panel_page.js`의 `VERDICTS`·`MARKS`와 같아야 하고,
#: `test_panel_page.py`가 둘이 같은지 봅니다.
LABELS = (
    ("PANELS", "패널이 있다 — 아래에 그은 상자가 패널이다"),
    ("NO_PANELS", "이 그림에는 읽을 패널이 없다"),
    ("HOLD", "아직 못 정하겠다"),
)
MARK_LABELS = (
    ("BAR", "막대"),
    ("LINE", "선"),
    ("BOX", "상자(박스플롯)"),
    ("SCATTER", "점"),
    ("NOT_DATA", "축은 있지만 읽을 값 없음"),
)


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_proposals(path):
    """{Draft_ID: {"size": [w, h], "verdict": ..., "boxes": [{x0,y0,x1,y1,mark}, ...]}}.

    상자는 `[x0,y0,x1,y1]`(잉크 분할만 있던 때)이든 `{x0,y0,x1,y1,mark}`이든
    받습니다 - 둘 다 이 그림의 크기 위의 좌표입니다."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec["fig"]] = rec
    return out


def crop_image(path):
    """(data URL, 원본 (w, h), 보이는 (w, h)). 못 읽으면 ('', None, None).

    화면에는 줄여서 싣고 원본 크기를 함께 돌려줍니다 - 상자 좌표는 원본
    픽셀로 나가야 600 DPI로 옮길 수 있습니다.
    """
    if not path or not os.path.isfile(path):
        return "", None, None
    try:
        from PIL import Image
        im = Image.open(path)
        size = im.size
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.size[0] > SHOW_WIDTH:
            h = int(round(im.size[1] * SHOW_WIDTH / float(im.size[0])))
            im = im.resize((SHOW_WIDTH, h))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
    except Exception:                                   # noqa: BLE001
        return "", None, None
    return ("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            size, im.size)


def pick_chunk(queue, chunk, of):
    """묶음 `chunk`/`of`에 드는 줄. 순서는 대기열의 순서이고, 묶음은 앞에서부터
    같은 크기로 자릅니다 - 같은 논문의 그림이 한 묶음에 모이도록."""
    if of < 1 or chunk < 1 or chunk > of:
        raise SystemExit("--chunk %s --of %s는 묶음이 아닙니다." % (chunk, of))
    n = len(queue)
    per = -(-n // of)
    return queue[(chunk - 1) * per: chunk * per]


def build(run, queue, proposals=None, chunk=1, of=1, log=print):
    """(html, 그림 수). `queue`는 dig.csv의 줄들 (fig, axes, pid)."""
    drafts = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, DRAFTS)))
    proposals = proposals or {}
    part = pick_chunk(queue, chunk, of)
    if not part:
        raise SystemExit("묶음 %d/%d에 드는 그림이 없습니다." % (chunk, of))

    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>패널 확인 %d/%d — 그림 %d장</title>" % (chunk, of, len(part)))
    w(CSS)
    w("""<style>
[hidden]{display:none!important}
.opt{display:block;font-size:13px;margin:3px 0}
.wrap{position:relative;display:inline-block;border:1px solid #ccc;background:#fff}
.wrap img{display:block;max-width:100%%;height:auto}
.wrap canvas{position:absolute;left:0;top:0;cursor:crosshair;touch-action:none}
.boxes{margin:8px 0;font-size:13px}
.boxes .b{display:flex;gap:8px;align-items:center;margin:3px 0}
.boxes .b.sel{background:#fff3c4}
.boxes .tag{font-family:ui-monospace,Menlo,monospace;min-width:150px}
.boxes .src{color:#8a8a82;font-size:12px}
.who{margin:8px 0}
.cap{font-size:12px;color:#55554f;margin:4px 0 10px;max-width:%dpx}
.hint{font-size:12px;color:#8a8a82}
</style>""" % SHOW_WIDTH)
    w("<header><h1>패널 확인 <span class='count' id='left'></span></h1>")
    w("<p class='note'>그림마다 <b>패널의 자리</b>와 <b>무엇이 그려졌는지</b>가 "
      "기계의 제안으로 미리 채워져 있습니다 (파란 상자 = 제안). 맞으면 그대로 두고 "
      "<b>직접 봤다</b>와 이름만 채우면 됩니다. 틀리면 상자를 눌러 고르고 "
      "<b>지우기</b> 단추나 Delete로 지운 뒤 그림 위를 끌어 다시 긋고(주황 = 그음), "
      "종류는 목록에서 바꿉니다.</p>")
    w("<p class='note'>눈금 값은 여기서 묻지 않습니다 — 확인된 자리에서 리더가 "
      "읽고, 다음 페이지가 그것을 다시 보입니다. 정하기 어려우면 "
      "<b>아직 못 정하겠다</b>도 답입니다.</p>")
    w("<p class='note'>이 페이지는 <b>관문이 아닙니다</b>. "
      "<code>record_panels</code>가 답이 실제로 낸 그림에 대한 것인지, 상자가 "
      "크롭 안에 드는지를 다시 봅니다.</p>")
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    for q in part:
        fid = q["fig"]
        d = drafts.get(fid, {})
        src, size, shown = crop_image(os.path.join(run, d.get("Figure_Crop") or ""))
        prop = proposals.get(fid, {})
        boxes = [proposed_box(b) for b in prop.get("boxes", [])]
        # 제안의 상자는 제안이 잰 크기 위의 좌표입니다. 그 크기가 크롭의 크기와
        # 다르면 그 제안은 이 그림의 것이 아니고, 싣지 않습니다.
        if size and list(prop.get("size") or []) != list(size):
            boxes = []
        ids.append(fid)
        verdict = str(prop.get("verdict") or "").upper()
        meta[fid] = {"draft": fid,
                     "size": {"w": size[0], "h": size[1]} if size else None,
                     "shown": {"w": shown[0], "h": shown[1]} if shown else None,
                     "declared": q.get("axes") or "",
                     "proposed": boxes,
                     # 제안된 판정도 미리 골라져 나갑니다. 사람이 하는 일은
                     # "직접 봤다"와 이름이지, 이미 제안된 것을 다시 고르는 일이
                     # 아닙니다. 다만 이 페이지의 어휘에 없는 판정은 싣지 않습니다.
                     "proposedVerdict": verdict if verdict in dict(LABELS) else ""}
        w(card(fid, d, q, src, shown, len(boxes)))

    w("</main><script>")
    w("var IDS = %s;" % json.dumps(ids, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    with_crop = sum(1 for fid in ids if meta[fid]["size"])
    with_prop = sum(1 for fid in ids if meta[fid]["proposed"])
    log("묶음 %d/%d · 그림 %d장 · 크롭 있음 %d · 제안 있음 %d"
        % (chunk, of, len(ids), with_crop, with_prop))
    return "\n".join(out), len(ids)


def proposed_box(b):
    """제안 상자 하나를 화면이 드는 모양으로. 종류가 딸려 오면 미리 골라집니다."""
    if isinstance(b, dict):
        mark = str(b.get("mark") or "").upper()
        return {"x0": b["x0"], "y0": b["y0"], "x1": b["x1"], "y1": b["y1"],
                "mark": mark if mark in dict(MARK_LABELS) else "",
                "source": "PROPOSED",
                "markSource": "PROPOSED" if mark in dict(MARK_LABELS) else ""}
    return {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3],
            "mark": "", "source": "PROPOSED", "markSource": ""}


def card(fid, draft, q, src, shown, n_prop):
    out = []
    w = out.append
    w("<div class='doc' data-id='%s'>" % esc(fid))
    w("<h2>%s · %s</h2>" % (esc(fid), esc(draft.get("Figure_Number") or "")))
    w("<p class='sub'>전에 센 패널 수 %s · 제안 상자 %d개</p>"
      % (esc(q.get("axes") or "?"), n_prop))
    cap = (draft.get("Caption_Text") or "").strip()
    if cap:
        w("<p class='cap'>%s</p>" % esc(cap[:400] + ("…" if len(cap) > 400 else "")))
    if src:
        w("<div class='wrap' data-wrap='%s'><img src='%s' alt='%s' width='%d' "
          "height='%d'><canvas data-canvas='%s' width='%d' height='%d'></canvas></div>"
          % (esc(fid), src, esc(fid), shown[0], shown[1], esc(fid), shown[0], shown[1]))
    else:
        w("<div class='nofig'>크롭 없음 — 그을 그림이 없습니다</div>")
    w("<div class='boxes' data-boxes='%s'></div>" % esc(fid))
    w("<p class='hint'><button data-del='%s'>고른 상자 지우기</button> "
      "<button data-reset='%s'>제안으로 되돌리기</button></p>"
      % (esc(fid), esc(fid)))
    w("<div class='pick'>")
    for value, label in LABELS:
        w("<label class='opt'><input type='radio' name='v-%s' data-verdict='%s' "
          "value='%s'> %s</label>" % (esc(fid), esc(fid), esc(value), esc(label)))
    w("<label class='opt'><input type='checkbox' data-seen='%s'> "
      "이 그림을 직접 봤다</label>" % esc(fid))
    w("<div class='who'>본 사람 <input type='text' data-who='%s' size='16' "
      "placeholder='reviewer_registry.csv의 ID'></div>" % esc(fid))
    w("<label>메모 <input type='text' data-note='%s' size='28'></label>" % esc(fid))
    w("<div class='state' data-state='%s'></div>" % esc(fid))
    w("</div></div>")
    return "\n".join(out)


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_panels';
  var states = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
  catch (e) { states = {}; }
  var MARK_LABELS = %s;

  function fromProposal(m) {
    return (m.proposed || []).map(function (b) {
      return { x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, mark: b.mark || '',
               source: 'PROPOSED', markSource: b.mark ? 'PROPOSED' : '' };
    });
  }
  function st(id) {
    var m = META[id] || {};
    if (!states[id]) {
      // 처음 여는 그림은 제안의 상자를 들고 시작합니다. 사람이 지우거나 더
      // 그으면 그때부터는 사람의 것입니다.
      states[id] = { verdict: m.proposedVerdict || '', boxes: fromProposal(m),
                     seen: false, who: '', note: '', sel: -1 };
    }
    // 그림의 크기와 이름은 화면이 아니라 페이지가 심어 둔 것에서 옵니다.
    states[id].draft = m.draft; states[id].size = m.size; states[id].declared = m.declared;
    if (!states[id].boxes) states[id].boxes = [];
    return states[id];
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {} }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }
  function scaleOf(id) {
    var m = META[id] || {};
    return (m.size && m.shown) ? m.size.w / m.shown.w : 1;
  }

  function drawBoxes(id) {
    var c = q("canvas[data-canvas=\"" + esc(id) + "\"]");
    if (!c) return;
    var s = st(id), k = 1 / scaleOf(id), ctx = c.getContext('2d');
    ctx.clearRect(0, 0, c.width, c.height);
    s.boxes.forEach(function (b, i) {
      ctx.lineWidth = i === s.sel ? 3 : 2;
      ctx.strokeStyle = b.source === 'PROPOSED' ? '#2a7fd4' : '#d4572a';
      ctx.strokeRect(b.x0 * k, b.y0 * k, (b.x1 - b.x0) * k, (b.y1 - b.y0) * k);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = 'bold 14px sans-serif';
      ctx.fillText(String(i + 1) + (b.mark ? ' ' + b.mark : ''), b.x0 * k + 4, b.y0 * k + 16);
    });
    if (drag && drag.id === id) {
      ctx.strokeStyle = '#d4572a'; ctx.setLineDash([4, 3]);
      ctx.strokeRect(drag.x0, drag.y0, drag.x1 - drag.x0, drag.y1 - drag.y0);
      ctx.setLineDash([]);
    }
  }

  function listBoxes(id) {
    var host = q("[data-boxes=\"" + esc(id) + "\"]");
    if (!host) return;
    var s = st(id);
    host.innerHTML = '';
    s.boxes.forEach(function (b, i) {
      var row = document.createElement('div');
      row.className = 'b' + (i === s.sel ? ' sel' : '');
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = (i + 1) + ': ' + Math.round(b.x0) + ',' + Math.round(b.y0)
        + ' – ' + Math.round(b.x1) + ',' + Math.round(b.y1);
      tag.addEventListener('click', function () { s.sel = i; save(); paint(id); });
      row.appendChild(tag);
      var sel = document.createElement('select');
      var none = document.createElement('option');
      none.value = ''; none.textContent = '무엇이 그려졌나?';
      sel.appendChild(none);
      MARK_LABELS.forEach(function (ml) {
        var o = document.createElement('option');
        o.value = ml[0]; o.textContent = ml[1]; sel.appendChild(o);
      });
      sel.value = b.mark || '';
      sel.addEventListener('change', function () {
        // 사람이 바꾼 종류는 사람의 것입니다 - 제안과 같은 값으로 되돌려도.
        b.mark = sel.value; b.markSource = 'TYPED'; save(); paint(id);
      });
      row.appendChild(sel);
      var src = document.createElement('span');
      src.className = 'src';
      src.textContent = (b.source === 'PROPOSED' ? '제안' : '그음')
        + (b.mark ? (b.markSource === 'PROPOSED' ? ' · 종류 제안' : ' · 종류 고름') : '');
      row.appendChild(src);
      host.appendChild(row);
    });
  }

  function paint(id) {
    var s = st(id);
    var got = panelsOf(id, s);
    var box = q("[data-state=\"" + esc(id) + "\"]");
    if (box) {
      box.textContent = got.ready
        ? '답이 되었습니다 — ' + got.rows[0].Verdict + ' · 패널 ' + (got.rows[0].Verdict === 'PANELS' ? got.rows.length : 0) + '개'
        : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-id=\"" + esc(id) + "\"]");
    if (card) card.classList.toggle('done', got.ready);
    all("input[data-verdict=\"" + esc(id) + "\"]").forEach(function (r) {
      r.checked = r.value === s.verdict;
    });
    var seen = q("input[data-seen=\"" + esc(id) + "\"]");
    if (seen) seen.checked = !!s.seen;
    var ww = q("input[data-who=\"" + esc(id) + "\"]");
    if (ww && ww.value !== s.who) ww.value = s.who;
    var nn = q("input[data-note=\"" + esc(id) + "\"]");
    if (nn && nn.value !== s.note) nn.value = s.note;
    drawBoxes(id); listBoxes(id);
    q('#left').textContent = '· 남은 것 ' + remaining(IDS, states)
      + ' / ' + IDS.length + ' · 보류 ' + held(IDS, states);
  }

  function bind(sel, attr, read, ev) {
    all(sel).forEach(function (el) {
      var id = el.getAttribute(attr);
      el.addEventListener(ev || 'input', function () {
        read(st(id), el); save(); paint(id); IDS.forEach(function (o) { if (o !== id) paint(o); });
      });
    });
  }
  bind('input[data-verdict]', 'data-verdict', function (s, el) { s.verdict = el.value; }, 'change');
  bind('input[data-seen]', 'data-seen', function (s, el) { s.seen = el.checked; }, 'change');
  bind('input[data-who]', 'data-who', function (s, el) {
    s.who = el.value;
    IDS.forEach(function (o) { if (!st(o).who) st(o).who = el.value; });
  });
  bind('input[data-note]', 'data-note', function (s, el) { s.note = el.value; });
  bind('button[data-del]', 'data-del', function (s) {
    if (s.sel >= 0 && s.sel < s.boxes.length) { s.boxes.splice(s.sel, 1); s.sel = -1; }
  }, 'click');
  bind('button[data-reset]', 'data-reset', function (s, el) {
    s.boxes = fromProposal(META[el.getAttribute('data-reset')] || {});
    s.sel = -1;
  }, 'click');

  // 그림 위를 끌면 상자가 생깁니다. 끈 거리가 짧으면 상자가 아니라 고르기입니다.
  var drag = null;
  function pos(c, ev) {
    var r = c.getBoundingClientRect();
    return { x: Math.max(0, Math.min(c.width, ev.clientX - r.left)),
             y: Math.max(0, Math.min(c.height, ev.clientY - r.top)) };
  }
  all('canvas[data-canvas]').forEach(function (c) {
    var id = c.getAttribute('data-canvas');
    c.addEventListener('pointerdown', function (ev) {
      var p = pos(c, ev);
      drag = { id: id, x0: p.x, y0: p.y, x1: p.x, y1: p.y };
      c.setPointerCapture(ev.pointerId);
    });
    c.addEventListener('pointermove', function (ev) {
      if (!drag || drag.id !== id) return;
      var p = pos(c, ev); drag.x1 = p.x; drag.y1 = p.y; drawBoxes(id);
    });
    c.addEventListener('pointerup', function (ev) {
      if (!drag || drag.id !== id) return;
      var s = st(id), k = scaleOf(id);
      var x0 = Math.min(drag.x0, drag.x1), x1 = Math.max(drag.x0, drag.x1);
      var y0 = Math.min(drag.y0, drag.y1), y1 = Math.max(drag.y0, drag.y1);
      if (x1 - x0 < 6 || y1 - y0 < 6) {
        // 고르기: 누른 자리를 품는 가장 작은 상자.
        var best = -1, area = Infinity;
        s.boxes.forEach(function (b, i) {
          var bx0 = b.x0 / k, by0 = b.y0 / k, bx1 = b.x1 / k, by1 = b.y1 / k;
          if (drag.x0 >= bx0 && drag.x0 <= bx1 && drag.y0 >= by0 && drag.y0 <= by1) {
            var a = (bx1 - bx0) * (by1 - by0);
            if (a < area) { area = a; best = i; }
          }
        });
        s.sel = best;
      } else {
        s.boxes.push({ x0: Math.round(x0 * k), y0: Math.round(y0 * k),
                       x1: Math.round(x1 * k), y1: Math.round(y1 * k),
                       mark: '', source: 'DRAWN', markSource: 'TYPED' });
        s.sel = s.boxes.length - 1;
      }
      drag = null; save(); paint(id);
    });
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Delete' && ev.key !== 'Backspace') return;
    if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
    IDS.forEach(function (id) {
      var s = st(id);
      if (s.sel >= 0 && s.sel < s.boxes.length) {
        s.boxes.splice(s.sel, 1); s.sel = -1; save(); paint(id);
      }
    });
  });

  q('#dl').addEventListener('click', function () {
    var csv = buildCsv(IDS, states);
    var n = IDS.length - remaining(IDS, states);
    if (!n) { q('#msg').textContent = '답이 된 그림이 아직 없습니다.'; return; }
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    // `record_panels`가 적는 파일은 `panel_decisions.csv`입니다. 같은 이름으로
    // 내려받으면 사람이 그 자리에 두게 되고, 관문이 자기 출력을 답으로 읽습니다.
    a.download = 'panel_answers.csv';
    a.click();
    q('#msg').textContent = n + '장의 답을 내려받았습니다.';
  });

  IDS.forEach(paint);
})();
""" % json.dumps(MARK_LABELS, ensure_ascii=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="figure_intake_draft.csv와 crops/가 있는 폴더")
    ap.add_argument("--queue", required=True, help="fig,axes 열이 있는 대기열 CSV")
    ap.add_argument("--proposals", help="자동 분할의 boxes.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=1)
    ap.add_argument("--of", type=int, default=1)
    a = ap.parse_args(argv)
    queue = _rows(os.path.expanduser(a.queue))
    html, _n = build(os.path.expanduser(a.run), queue,
                     load_proposals(os.path.expanduser(a.proposals) if a.proposals else None),
                     chunk=a.chunk, of=a.of)
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
