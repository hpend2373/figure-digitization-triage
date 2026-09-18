# -*- coding: utf-8 -*-
"""사람이 정체 제안을 보고 확인하는 페이지.

    python3 identity_page.py --proposals DIR --out DIR/identity.html [--chunk i --of n]

`identity_proposer`가 낸 것은 전부 **제안**입니다: x 라벨과 그 위치, 범례의
계열과 색, y축 제목(결과변수·단위), 캡션의 n. 그림 위에 그려져 있고, 아무것도
확인되지 않았습니다.

이 페이지가 하는 일은 그 제안을 사람 앞에 놓는 것입니다. 사람이 하는 일은
대개 **보는 것**이고, 리더가 거절한 자리나 틀린 자리에서만 고칩니다. 그리고
리더가 읽을 수 없는 두 가지 - x축이 무슨 **요인**인지(TIMEPOINT? GROUP?),
계열이 무슨 요인인지(ARM? SEX?) - 는 사람만 적습니다. 계획서의 격자는 그
이름으로 섭니다.

무엇이 답이 되는지는 `identity_page.js`에 있습니다. 내려받는 파일은
`identity_answers.csv`이고, 관문 `record_identity.py`가 `identity_decisions.csv`를
적습니다.
"""
import argparse
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from page_bits import CSS, esc                                   # noqa: E402
import identity_proposer as IP                                   # noqa: E402
from geometry_page import chunk_of                               # noqa: E402

PROPOSALS = IP.PROPOSALS
LOGIC = "identity_page.js"

LABELS = (
    ("CONFIRMED", "맞다 — 이 위치·계열·이름으로 읽는다"),
    ("REJECTED", "이 패널은 읽지 않는다"),
    ("HOLD", "아직 못 정하겠다"),
)

#: 흔한 요인 이름. 목록은 도움말이고 자유롭게 적을 수 있습니다 - 계획서의
#: 격자는 여기 적힌 이름으로 섭니다.
X_FACTORS = ("TIMEPOINT", "GROUP", "CONDITION", "SESSION", "DOSE", "POSTURE")
SERIES_FACTORS = ("ARM", "GROUP", "SEX", "CONDITION", "POSTURE", "SESSION")

KEYS = (("#c81e1e", "프레임"),
        ("#1e64c8", "리더가 읽은 x 라벨과 그 위치, 범례 항목"),
        ("#149650", "프레임이 잰 x 앵커 (참고용 — 라벨과 어긋나면 라벨이 이깁니다)"),
        ("#be3cbe", "리더가 읽은 y축 제목"))


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def data_url(path):
    if not path or not os.path.isfile(path):
        return ""
    import base64
    with io.open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def read_summary(row):
    """(x, series, title, n) - 각각 (status, text, detail)."""
    return (
        (row.get("X_Label_Read_Status") or "", " · ".join(
            t for t, _px in IP.labels_of(row.get("X_Labels_Read"))), row.get("X_Label_Detail") or ""),
        (row.get("Series_Read_Status") or "", " · ".join(
            (n or "(이름 없음)") for n, _c in IP.series_of(row.get("Series_Read"))),
         row.get("Series_Detail") or ""),
        (row.get("Y_Title_Read_Status") or "", row.get("Y_Title_Read") or "",
         row.get("Y_Title_Detail") or ""),
        (row.get("N_Read_Status") or "", row.get("N_Read") or "", row.get("N_Detail") or ""),
    )


def build(proposals, log=print, chunk=1, of=1):
    everything = _rows(os.path.join(proposals, PROPOSALS))
    if not everything:
        raise SystemExit("%s에 제안이 없습니다." % os.path.join(proposals, PROPOSALS))
    rows = chunk_of(everything, chunk, of)
    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>정체 확인 — %d개%s</title>"
      % (len(rows), (" (%d/%d)" % (chunk, of)) if of > 1 else ""))
    w(CSS)
    w("""<style>
[hidden]{display:none!important}
.opt{display:block;font-size:13px;margin:3px 0}
.side{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.side .pick{min-width:340px;flex:1}
.side img{max-width:640px;border:1px solid #ddd}
.read{font-size:13px;margin:8px 0;padding:8px 10px;background:#faf7fb;border-left:3px solid #1e64c8}
.refused{background:#fdf6f3;border-left-color:#c86a1e}
.warn{background:#fff8dc;border-left-color:#c9a000}
.key{font-size:12px;color:#5a5a56;margin:6px 0 0}
.key i{display:inline-block;width:11px;height:11px;margin-right:4px;vertical-align:-1px}
.blk{margin:10px 0;padding:8px 10px;border:1px solid #e4e4e0;border-radius:4px;font-size:13px}
.blk h4{margin:0 0 6px;font-size:13px}
.blk input[type=text]{font-size:13px}
.plist div{margin:2px 0}
.chip{display:inline-block;width:14px;height:14px;border:1px solid #333;vertical-align:-2px;margin-right:4px}
.pickbtn{font-size:12px;margin-right:4px}
.pickbtn.on{background:#1e64c8;color:#fff}
.pickwrap{position:relative;display:inline-block}
.pickwrap.arming img{cursor:crosshair;outline:2px solid #1e64c8}
.xmark{position:absolute;top:0;bottom:0;width:0;border-left:2px dashed #1e64c8;pointer-events:none}
.who{margin:8px 0}
h1 #guidetoggle{font-size:12px;font-weight:normal;margin-left:10px;vertical-align:2px}
</style>""")
    w("<header><h1>정체 확인%s <span class='count' id='left'></span> "
      "<button id='guidetoggle'>안내 접기</button></h1>"
      % ((" — %d/%d 조각" % (chunk, of)) if of > 1 else ""))
    w("<div id='guide'>")
    w("<p class='note'><code>identity_proposer</code>가 읽은 것이 그림 위에 그려져 "
      "있습니다 — x 라벨과 그 위치(파란 점선), 범례의 계열과 색, y축 제목. 전부 "
      "<b>제안</b>이고, 아무것도 확인되지 않았습니다.</p>")
    w("<p class='note'>사람만 적을 수 있는 것이 둘 있습니다: x축이 <b>무슨 요인</b>인지"
      "(예: TIMEPOINT, GROUP)와, 계열이 <b>무슨 요인</b>인지(예: ARM, SEX). 계열이 하나뿐"
      "이어도 그 계열이 어느 군인지 — 요인과 이름(예: GROUP / ALL) — 적어 주세요: 값은 그 "
      "이름의 셀에 적힙니다. 계획서의 격자는 이 이름으로 서니, 같은 논문 안에서는 같은 "
      "요인을 같은 이름으로 불러 주세요.</p>")
    w("<p class='note'>리더가 라벨을 <b>못 읽었거나 틀리게</b> 읽었으면: 라벨 칸을 고치거나, "
      "\"x 위치 찍기\"를 누른 뒤 그림에서 각 위치를 차례로 누르고 라벨을 적어 주세요. "
      "계열도 같습니다 — 이름을 고치거나 \"계열 추가\"로 적어 주세요. 색으로 가르는 표는 "
      "계열마다 색이 있어야 하고(리더가 찾은 색을 씁니다), 선 모양·마커·채움 무늬로 "
      "가르는 표는 그것을 골라 주세요.</p>")
    w("<p class='note'>결과변수·단위·n은 비워 두면 리더가 읽은 것을 씁니다. n은 캡션에 "
      "없으면 비워 두세요 — 지어내지 않습니다. 막대 표는 값을 <b>어디서 읽는지</b>"
      "(윤곽선 중심 / 채움 가장자리)와 오차막대에 <b>세로 줄기</b>가 붙어 있는지도 "
      "골라 주세요.</p>")
    w("<p class='note'><b>직접 보셨을 때만</b> 확인 칸을 눌러 주세요. 이름을 적기 전에는 "
      "답이 되지 않습니다.</p>")
    w("<p class='key'>%s</p>" % " &nbsp; ".join(
        "<i style='background:%s'></i>%s" % (c, esc(t)) for c, t in KEYS))
    w("</div>")
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span> &nbsp; "
      "<button id='hidedone'>답이 된 패널 숨기기</button> "
      "<button id='showall'>숨긴 패널 모두 보기</button> "
      "<span class='count' id='hiddenN'></span></p>")
    w("</header><main>")
    for row in rows:
        pid = (row.get("Proposal_ID") or "").strip()
        if not pid:
            continue
        ids.append(pid)
        kind = (row.get("Panel_Kind") or "").strip().upper()
        meta[pid] = {
            "proposal": pid,
            "readLabels": (row.get("X_Labels_Read") or "").strip(),
            "readSeries": (row.get("Series_Read") or "").strip(),
            "readOutcome": (row.get("Outcome_Read") or "").strip(),
            "readUnit": (row.get("Unit_Read") or "").strip(),
            "readN": (row.get("N_Read") or "").strip(),
            "markProposed": (row.get("Mark_Type_Proposed") or "").strip(),
            "markChoices": list(IP.MARK_TYPES_FOR.get(kind, ())) + (
                ["LINE_MONO_STYLE"] if kind == "LINE" else []),
            "kind": kind,
            "frameX0": (row.get("Panel_X0") or "").strip(),
            "frameX1": (row.get("Panel_X1") or "").strip(),
            "originX": IP.overlay_origin(row)[0],
            "originY": IP.overlay_origin(row)[1],
            "colours": [[int(c) for c in v.split(",")]
                        for v in (row.get("Series_Colours") or "").split(";") if v],
        }
        w(card(proposals, pid, row))
    w("</main><script>")
    w("var IDS = %s;" % json.dumps(ids, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    w("var X_FACTORS = %s; var SERIES_FACTORS = %s;"
      % (json.dumps(X_FACTORS), json.dumps(SERIES_FACTORS)))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    log("제안 %d개" % len(ids))
    return "\n".join(out), len(ids)


def _block(status, title, text, detail, refused_hint):
    cls = "read" if status == IP.READ_OK else "read refused"
    if status == IP.READ_OK:
        body = "<b>%s:</b> %s<br><span class='sub'>%s</span>" % (
            esc(title), esc(text) if text else "<i>(이름 없음)</i>", esc(detail[:160]))
    else:
        body = "<b>%s — 리더가 읽지 못했습니다.</b><br><span class='sub'>%s</span><br>%s" % (
            esc(title), esc(detail[:160]), esc(refused_hint))
    return "<div class='%s'>%s</div>" % (cls, body)


def card(proposals, pid, row):
    out = []
    w = out.append
    w("<div class='doc' data-id='%s' id='p-%s'>" % (esc(pid), esc(pid)))
    w("<h2>%s <button class='hide' data-hide='%s'>이 패널 숨기기</button></h2>" % (esc(pid), esc(pid)))
    w("<p class='sub'>%s · %s · 프레임 %s,%s,%s,%s%s</p>"
      % (esc(row.get("Raster") or ""), esc(row.get("Panel_Kind") or "?"),
         esc(row.get("Panel_X0")), esc(row.get("Panel_X1")), esc(row.get("Panel_Y0")),
         esc(row.get("Panel_Y1")),
         (" · %s" % esc(row.get("Note"))) if (row.get("Note") or "").strip() else ""))
    w("<div class='side'><div class='figs'><div class='fig'>")
    src = data_url(os.path.join(proposals, "%s.png" % pid))
    if src:
        w("<div class='pickwrap' data-pick='%s'><img src='%s' alt='%s'>"
          "<div class='xmarks' data-xmarks='%s'></div></div>" % (esc(pid), src, esc(pid), esc(pid)))
    else:
        w("<div class='nofig'>오버레이 없음 — 확인할 그림이 없습니다</div>")
    w("</div></div><div class='pick'>")
    x, series, title, n = read_summary(row)
    w(_block(x[0], "리더가 읽은 x 라벨", x[1], x[2], "그림에서 x 위치를 찍고 라벨을 적어 주세요."))
    if x[0] == IP.READ_OK and "disagree" in x[2]:
        w("<div class='read warn'><b>먼저 보세요:</b> 프레임이 잰 x 앵커와 읽은 라벨이 "
          "어긋납니다 — 라벨의 수나 자리를 그림에서 확인해 주세요.</div>")
    w(_block(series[0], "리더가 읽은 계열", series[1], series[2],
             "범례를 보고 계열을 적어 주세요. 하나뿐이면 하나만."))
    w(_block(title[0], "리더가 읽은 y축 제목", title[1], title[2], "결과변수 이름과 단위를 적어 주세요."))
    w(_block(n[0], "캡션의 n", n[1], n[2], "캡션에 n이 없으면 비워 두세요."))

    # ---- x ----
    w("<div class='blk'><h4>x축</h4>")
    w("요인 <input type='text' list='xf' data-xfactor='%s' size='12' placeholder='TIMEPOINT'> "
      "<span class='sub'>x 위치마다 이 요인의 한 수준입니다</span>" % esc(pid))
    w("<div class='sub'><button class='pickbtn' data-arm-x='%s'>x 위치 찍기</button>"
      "<button class='pickbtn' data-x-reset='%s'>읽은 대로 되돌리기</button> "
      "<span data-xhint='%s'></span></div>" % (esc(pid), esc(pid), esc(pid)))
    w("<div class='plist' data-positions='%s'></div></div>" % esc(pid))
    # ---- series ----
    w("<div class='blk'><h4>계열</h4>")
    w("표 종류 <select data-mark='%s'></select> &nbsp; 계열 요인 <input type='text' list='sf' "
      "data-sfactor='%s' size='10' placeholder='ARM'> <span class='sub'>하나뿐이어도 (예: GROUP, 이름 ALL)</span>"
      % (esc(pid), esc(pid)))
    w("<div class='sub'><button class='pickbtn' data-s-add='%s'>계열 추가</button>"
      "<button class='pickbtn' data-s-reset='%s'>읽은 대로 되돌리기</button></div>"
      % (esc(pid), esc(pid)))
    w("<div class='plist' data-series='%s'></div></div>" % esc(pid))
    # ---- unit ----
    w("<div class='blk'><h4>결과변수 · 단위 · n</h4>")
    w("결과변수 <input type='text' data-outcome='%s' size='26' placeholder='%s'> "
      "단위 <input type='text' data-unit='%s' size='10' placeholder='%s'> "
      "n <input type='text' data-n='%s' size='4' placeholder='%s'>"
      "<div class='sub'>비워 두면 리더가 읽은 것(회색)을 그대로 씁니다.</div>"
      % (esc(pid), esc(row.get("Outcome_Read") or "읽지 못함"), esc(pid),
         esc(row.get("Unit_Read") or "없음"), esc(pid), esc(row.get("N_Read") or "없음")))
    w("<div data-barblk='%s'>막대의 값은 <select data-bartop='%s'><option value=''>— 고르세요 —</option>"
      "<option value='OUTLINE_CENTER'>윤곽선의 중심에서 읽는다 (보통)</option>"
      "<option value='FILL_EDGE'>채움의 가장자리에서 읽는다</option>"
      "<option value='MARKER_CENTER'>마커의 중심에서 읽는다</option></select></div>"
      % (esc(pid), esc(pid)))
    w("<div data-stemblk='%s'><label><input type='checkbox' data-stem='%s'> 오차막대에 세로 줄기가 "
      "마크에 붙어 있다 (유의성 기호를 캡으로 세지 않기 위한 확인)</label></div></div>"
      % (esc(pid), esc(pid)))

    for value, label in LABELS:
        w("<label class='opt'><input type='radio' name='v-%s' data-verdict='%s' value='%s'> %s</label>"
          % (esc(pid), esc(pid), esc(value), esc(label)))
    w("<div class='who'>보신 분 <input type='text' data-who='%s' size='12' placeholder='이름 또는 이니셜'></div>"
      % esc(pid))
    w("<div class='row'><label class='verify'><input type='checkbox' data-seen='%s'> "
      "<b>이 오버레이를 직접 봤다</b></label> <label>메모 <input type='text' data-note='%s' size='24'></label></div>"
      % (esc(pid), esc(pid)))
    w("<div class='state' data-state='%s'></div>" % esc(pid))
    w("</div></div></div>")
    return "\n".join(out)


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_identity', HKEY = 'fdt_identity_hidden', GKEY = 'fdt_identity_guide';
  var states = {}, hiddenIds = {}, arming = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { states = {}; }
  try { hiddenIds = JSON.parse(localStorage.getItem(HKEY) || '{}') || {}; } catch (e) { hiddenIds = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {} }
  function saveHidden() { try { localStorage.setItem(HKEY, JSON.stringify(hiddenIds)); } catch (e) {} }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }
  function h(s) { return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  var dl = document.createElement('datalist'); dl.id = 'xf';
  X_FACTORS.forEach(function (f) { var o = document.createElement('option'); o.value = f; dl.appendChild(o); });
  document.body.appendChild(dl);
  var dl2 = document.createElement('datalist'); dl2.id = 'sf';
  SERIES_FACTORS.forEach(function (f) { var o = document.createElement('option'); o.value = f; dl2.appendChild(o); });
  document.body.appendChild(dl2);

  function st(id) {
    if (!states[id]) {
      states[id] = { verdict: '', who: '', seen: false, note: '', xFactor: '', positions: [],
                     seriesFactor: '', series: [], markType: '', outcome: '', unit: '', n: '',
                     barTop: '', stem: false };
    }
    var m = META[id];
    if (m) {
      ['proposal', 'readLabels', 'readSeries', 'readOutcome', 'readUnit', 'readN', 'markProposed',
       'kind', 'frameX0', 'frameX1'].forEach(function (k) { states[id][k] = m[k]; });
    }
    return states[id];
  }
  function spreadWho(who) { IDS.forEach(function (id) { if (!st(id).who) st(id).who = who; }); }

  // 읽은 것을 사람의 목록으로 옮깁니다 - 고치기 시작할 때 한 번.
  function materialisePositions(s) {
    if (!s.positions.length) s.positions = positionsOf(s).map(function (p) { return { label: p.label, px: p.px }; });
  }
  function materialiseSeries(s) {
    if (!s.series.length) s.series = seriesOf(s).map(function (e) { return Object.assign({}, e); });
  }

  function renderPositions(id) {
    var s = st(id), box = q("[data-positions=\"" + esc(id) + "\"]");
    if (!box) return;
    var list = positionsOf(s), typed = !!s.positions.length;
    var html = '';
    list.forEach(function (p, i) {
      html += "<div>" + (i + 1) + ". <input type='text' data-plabel='" + h(i) + "' value='" + h(p.label) + "' size='14'> "
            + "<span class='sub'>x " + h(Math.round(p.px)) + " px</span> "
            + "<button class='pickbtn' data-pdel='" + h(i) + "'>지우기</button></div>";
    });
    box.innerHTML = html + (list.length ? "<div class='sub'>" + (typed ? '사람이 적은 목록' : '리더가 읽은 대로 (고치면 사람의 목록이 됩니다)') + "</div>" : "<div class='sub'>x 위치가 없습니다</div>");
    all("[data-positions=\"" + esc(id) + "\"] input[data-plabel]").forEach(function (el) {
      el.addEventListener('input', function () {
        materialisePositions(s); s.positions[Number(el.getAttribute('data-plabel'))].label = el.value; save(); paint(id, true);
      });
    });
    all("[data-positions=\"" + esc(id) + "\"] button[data-pdel]").forEach(function (el) {
      el.addEventListener('click', function () {
        materialisePositions(s); s.positions.splice(Number(el.getAttribute('data-pdel')), 1);
        if (!s.positions.length) s.positions = [{ label: '', px: NaN }];   // 빈 목록은 "읽은 대로"라서, 지운 자리를 남깁니다
        save(); paint(id);
      });
    });
  }

  function styleSelect(attr, i, options, value) {
    return "<select data-" + attr + "='" + h(i) + "'><option value=''>—</option>" + options.map(function (o) {
      return "<option value='" + o + "'" + (o === value ? ' selected' : '') + ">" + o + "</option>"; }).join('') + "</select>";
  }
  function renderSeries(id) {
    var s = st(id), box = q("[data-series=\"" + esc(id) + "\"]");
    if (!box) return;
    var mark = (s.markType || s.markProposed || '').toUpperCase();
    var list = seriesOf(s), typed = !!s.series.length, m = META[id] || {};
    var html = '';
    list.forEach(function (e, i) {
      html += "<div>" + (i + 1) + ". "
            + (e.colour ? "<span class='chip' style='background:" + hexOf(e.colour) + "'></span>" : '')
            + "<input type='text' data-sname='" + h(i) + "' value='" + h(e.name) + "' size='14' placeholder='계열 이름'> ";
      if (COLOUR_MARKS.indexOf(mark) >= 0 && !e.colour && (m.colours || []).length) {
        html += "색 <select data-scolour='" + h(i) + "'><option value=''>—</option>" + m.colours.map(function (c, ci) {
          return "<option value='" + ci + "'>rgb(" + c.join(',') + ")</option>"; }).join('') + "</select> ";
      }
      if (mark === 'LINE_MONO_STYLE') html += "선 " + styleSelect('sline', i, LINE_STYLES, e.line_style) + " ";
      if (mark === 'LINE_MONO') html += "마커 " + styleSelect('smarker', i, MARKER_SHAPES, e.marker) + " 채움 " + styleSelect('smfill', i, MARKER_FILLS, e.marker_fill) + " ";
      if (mark === 'BAR_MONO') html += "무늬 " + styleSelect('sbar', i, BAR_FILLS, e.bar_fill) + " ";
      html += "<button class='pickbtn' data-sdel='" + h(i) + "'>지우기</button></div>";
    });
    box.innerHTML = html + (list.length ? "<div class='sub'>" + (typed ? '사람이 적은 목록' : '리더가 읽은 대로 (고치면 사람의 목록이 됩니다)') + "</div>" : "<div class='sub'>계열이 없습니다</div>");
    function bindS(attr, fn) {
      all("[data-series=\"" + esc(id) + "\"] [data-" + attr + "]").forEach(function (el) {
        el.addEventListener(el.tagName === 'BUTTON' ? 'click' : (el.tagName === 'SELECT' ? 'change' : 'input'), function () {
          materialiseSeries(s); fn(s.series, Number(el.getAttribute('data-' + attr)), el); save(); paint(id, el.tagName === 'INPUT');
        });
      });
    }
    bindS('sname', function (ser, i, el) { ser[i].name = el.value; });
    bindS('scolour', function (ser, i, el) { ser[i].colour = el.value === '' ? null : (META[id].colours || [])[Number(el.value)]; });
    bindS('sline', function (ser, i, el) { ser[i].line_style = el.value; });
    bindS('smarker', function (ser, i, el) { ser[i].marker = el.value; });
    bindS('smfill', function (ser, i, el) { ser[i].marker_fill = el.value; });
    bindS('sbar', function (ser, i, el) { ser[i].bar_fill = el.value; });
    bindS('sdel', function (ser, i) { ser.splice(i, 1); if (!ser.length) ser.push({ name: '', colour: null, line_style: '', marker: '', marker_fill: '', bar_fill: '' }); });
  }

  function paint(id, light) {
    var s = st(id), m = META[id] || {};
    var got = verdictOf(id, s);
    var box = q("[data-state=\"" + esc(id) + "\"]");
    if (box) {
      box.textContent = got.ready ? '답이 되었습니다 — ' + got.row.Human_Verification_Status
        + (got.row.X_Factor ? ' (' + got.row.X_Factor + ' ' + JSON.parse(got.row.X_Labels).length + '자리 · 계열 ' + JSON.parse(got.row.Series).length + ' · ' + got.row.Mark_Type + ' · ' + got.row.Outcome_Name + (got.row.Unit ? ' [' + got.row.Unit + ']' : '') + (got.row.N_Outcome ? ' · n=' + got.row.N_Outcome : '') + ')' : '')
        : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-id=\"" + esc(id) + "\"]");
    if (card) { card.classList.toggle('done', got.ready); card.hidden = !!hiddenIds[id]; }
    all("input[data-verdict=\"" + esc(id) + "\"]").forEach(function (r) { r.checked = r.value === s.verdict; });
    var mk = q("select[data-mark=\"" + esc(id) + "\"]");
    if (mk) {
      if (!mk.options.length) {
        mk.innerHTML = "<option value=''>— 고르세요 —</option>" + (m.markChoices || MARK_TYPES).map(function (t) {
          return "<option value='" + t + "'>" + t + (t === m.markProposed ? ' (리더 제안)' : '') + "</option>"; }).join('');
      }
      var want = s.markType || m.markProposed || '';
      if (mk.value !== want) mk.value = want;
    }
    function setv(sel, val) { var el = q(sel); if (el && el.value !== val) el.value = val; }
    setv("input[data-xfactor=\"" + esc(id) + "\"]", s.xFactor);
    setv("input[data-sfactor=\"" + esc(id) + "\"]", s.seriesFactor);
    setv("input[data-outcome=\"" + esc(id) + "\"]", s.outcome);
    setv("input[data-unit=\"" + esc(id) + "\"]", s.unit);
    setv("input[data-n=\"" + esc(id) + "\"]", s.n);
    setv("select[data-bartop=\"" + esc(id) + "\"]", s.barTop);
    setv("input[data-who=\"" + esc(id) + "\"]", s.who);
    setv("input[data-note=\"" + esc(id) + "\"]", s.note);
    var mark = (s.markType || m.markProposed || '').toUpperCase();
    var bb = q("[data-barblk=\"" + esc(id) + "\"]"); if (bb) bb.hidden = mark.indexOf('BAR') !== 0;
    var sb = q("[data-stemblk=\"" + esc(id) + "\"]"); if (sb) sb.hidden = (mark === 'SCATTER' || mark === 'BOX_VIOLIN');
    var stc = q("input[data-stem=\"" + esc(id) + "\"]"); if (stc) stc.checked = !!s.stem;
    var sn = q("input[data-seen=\"" + esc(id) + "\"]"); if (sn) sn.checked = !!s.seen;
    if (!light) { renderPositions(id); renderSeries(id); }
    // 그림 위의 x 위치
    var wrap = q(".pickwrap[data-pick=\"" + esc(id) + "\"]");
    if (wrap) {
      var im = wrap.querySelector('img'), marks = wrap.querySelector('[data-xmarks]');
      if (marks && im.naturalWidth) {
        var kx = im.clientWidth / im.naturalWidth;
        marks.innerHTML = positionsOf(s).map(function (p) {
          return isFinite(p.px) ? "<div class='xmark' style='left:" + ((p.px - Number(m.originX || 0)) * kx) + "px'></div>" : ''; }).join('');
      }
      wrap.classList.toggle('arming', arming[id] === 'x');
      all("button[data-arm-x=\"" + esc(id) + "\"]").forEach(function (b) { b.classList.toggle('on', arming[id] === 'x'); });
    }
    var xh = q("[data-xhint=\"" + esc(id) + "\"]");
    if (xh) xh.textContent = arming[id] === 'x' ? '그림에서 x 위치를 차례로 눌러 주세요 (다시 누르면 끝)' : '';
    q('#left').textContent = '· 남은 것 ' + remaining(IDS, states) + ' / ' + IDS.length + ' · 보류 ' + held(IDS, states);
    var nh = IDS.filter(function (i) { return hiddenIds[i]; }).length;
    q('#hiddenN').textContent = nh ? '숨김 ' + nh + ' (세어지고 내려받기에 나갑니다)' : '';
  }
  function paintAll() { IDS.forEach(function (id) { paint(id); }); }

  function bind(sel, attr, read, ev, light) {
    all(sel).forEach(function (el) {
      var id = el.getAttribute(attr);
      el.addEventListener(ev || 'input', function () { read(st(id), el); save(); paint(id, light); });
    });
  }
  bind('input[data-verdict]', 'data-verdict', function (s, el) { s.verdict = el.value; }, 'change');
  bind('input[data-xfactor]', 'data-xfactor', function (s, el) { s.xFactor = el.value; }, 'input', true);
  bind('input[data-sfactor]', 'data-sfactor', function (s, el) { s.seriesFactor = el.value; }, 'input', true);
  bind('select[data-mark]', 'data-mark', function (s, el) { s.markType = el.value; }, 'change');
  bind('input[data-outcome]', 'data-outcome', function (s, el) { s.outcome = el.value; }, 'input', true);
  bind('input[data-unit]', 'data-unit', function (s, el) { s.unit = el.value; }, 'input', true);
  bind('input[data-n]', 'data-n', function (s, el) { s.n = el.value; }, 'input', true);
  bind('select[data-bartop]', 'data-bartop', function (s, el) { s.barTop = el.value; }, 'change');
  bind('input[data-stem]', 'data-stem', function (s, el) { s.stem = el.checked; }, 'change');
  bind('input[data-who]', 'data-who', function (s, el) { s.who = el.value; spreadWho(el.value); }, 'input', true);
  bind('input[data-seen]', 'data-seen', function (s, el) { s.seen = el.checked; }, 'change');
  bind('input[data-note]', 'data-note', function (s, el) { s.note = el.value; }, 'input', true);
  bind('button[data-arm-x]', 'data-arm-x', function (s, el) {
    var id = el.getAttribute('data-arm-x'); arming[id] = arming[id] === 'x' ? '' : 'x';
  }, 'click');
  bind('button[data-x-reset]', 'data-x-reset', function (s) { s.positions = []; }, 'click');
  bind('button[data-s-add]', 'data-s-add', function (s) {
    materialiseSeries(s); s.series.push({ name: '', colour: null, line_style: '', marker: '', marker_fill: '', bar_fill: '' });
  }, 'click');
  bind('button[data-s-reset]', 'data-s-reset', function (s) { s.series = []; }, 'click');
  all('.pickwrap[data-pick]').forEach(function (wrap) {
    var id = wrap.getAttribute('data-pick');
    wrap.querySelector('img').addEventListener('click', function (ev) {
      if (arming[id] !== 'x') return;
      var im = ev.currentTarget, m = META[id] || {}, rect = im.getBoundingClientRect();
      var col = Math.round(Number(m.originX || 0) + (ev.clientX - rect.left) * (im.naturalWidth / im.clientWidth));
      var s = st(id);
      materialisePositions(s);
      s.positions = s.positions.filter(function (p) { return isFinite(p.px) || p.label; });
      s.positions.push({ label: '', px: col });
      s.positions.sort(function (a, b) { return a.px - b.px; });
      save(); paint(id);
    });
  });
  q('#guidetoggle').addEventListener('click', function () {
    var g = q('#guide'); g.hidden = !g.hidden; q('#guidetoggle').textContent = g.hidden ? '안내 보기' : '안내 접기';
    try { localStorage.setItem(GKEY, g.hidden ? 'shut' : 'open'); } catch (e) {}
  });
  try { if (localStorage.getItem(GKEY) === 'shut') { q('#guide').hidden = true; q('#guidetoggle').textContent = '안내 보기'; } } catch (e) {}
  all('button[data-hide]').forEach(function (b) {
    b.addEventListener('click', function () { hiddenIds[b.getAttribute('data-hide')] = true; saveHidden(); paintAll(); });
  });
  q('#hidedone').addEventListener('click', function () {
    IDS.forEach(function (id) { if (verdictOf(id, st(id)).ready) hiddenIds[id] = true; }); saveHidden(); paintAll();
  });
  q('#showall').addEventListener('click', function () { hiddenIds = {}; saveHidden(); paintAll(); });
  q('#dl').addEventListener('click', function () {
    var csv = buildCsv(IDS, states);
    var n = IDS.length - remaining(IDS, states);
    if (!n) { q('#msg').textContent = '답이 된 줄이 아직 없습니다.'; return; }
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'identity_answers.csv';
    a.click();
    q('#msg').textContent = n + '줄을 내려받았습니다.';
  });
  paintAll();
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=1)
    ap.add_argument("--of", type=int, default=1)
    a = ap.parse_args(argv)
    html, _n = build(os.path.expanduser(a.proposals), chunk=a.chunk, of=a.of)
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)" % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
