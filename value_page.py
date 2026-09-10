# -*- coding: utf-8 -*-
"""사람이 읽힌 값을 보고 승인하거나 거절하는 페이지.

    python3 value_page.py --values DIR --out DIR/values.html --when 2026-09-10

`run_batch`는 `figure_values_machine_qc.csv`에서 멈춥니다. 그 파일은 기계가
아무 잘못도 못 찾았다는 뜻입니다 - 리더가 표시를 냈고, 격자 관문이 구멍도
모순도 못 찾았고, 출처 칸이 전부 풀렸다는 뜻이지, **표시가 어디에 앉았는지
누가 보았다**는 뜻이 아닙니다. 그 차이가 `finalize_batch`가 있는 까닭이고, 이
페이지는 그 문 앞에 서서 사람의 답을 받습니다.

보여 주는 것은 숫자가 아니라 **숫자가 앉은 자리**입니다. 상자의 세 규칙과
수염의 두 끝이 그림 위에 그려져 있고, 읽힌 값이 그 옆에 적혀 있습니다.
숫자만 보고 하는 승인은 산수에 동의하는 일이고, 그림을 보고 하는 승인은
표시가 옆 상자에 앉은 것을 잡아냅니다 - 그것이 이 문이 잡으라고 있는 것입니다.

무엇이 답이 되는지는 여기 없고 `value_page.js`에 있습니다.

내려받는 파일은 `value_review_answers.csv`이고, `finalize_batch`가 그것을
`--review`로 받습니다. **이 페이지는 관문이 아닙니다** - 승인이 실제로 값을
풀에 넣으려면 `finalize_batch`가 검토자가 등록된 사람인지, 실행이 손대지
않았는지, 지문이 이 실행의 것인지를 다시 봅니다. 여기서 통과한 답이 거기서
거절될 수 있고, 그것이 맞습니다.
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

VALUES = "read_values.csv"
LOGIC = "value_page.js"

#: 화면에 적는 말. `value_page.js`의 `DECISIONS`와 같아야 하고,
#: `test_value_page.py`가 둘이 같은지 봅니다.
LABELS = (
    ("APPROVED", "승인 — 표시가 값 위에 앉아 있다"),
    ("REJECTED", "거절 — 이 읽기는 쓰지 않는다"),
    ("HOLD", "아직 못 정하겠다"),
)

#: 확인 칸마다, 사람에게 묻는 말. 이름만 보여 주면 무엇을 확인하라는 것인지
#: 알 수 없고, 모르면 누르는 것이 확인이 아닙니다.
ASKS = (
    ("Marks_Checked", "표시가 인쇄된 상자와 수염 위에 앉아 있다"),
    ("Axis_Labels_Checked", "축 눈금 숫자가 그림에 인쇄된 것과 같다"),
    ("Calibration_Checked", "그려진 값이 그 자리의 눈금과 맞는다"),
)


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def data_url(path):
    """겹쳐 그린 그림 한 장을 data URL로. 못 읽으면 빈 문자열.

    줄이지 않습니다. 여기서 사람이 하는 일은 파란 줄이 인쇄된 상자 규칙 위에
    앉았는지 보는 것이고, 그러려면 둘 다 보여야 합니다.
    """
    if not path or not os.path.isfile(path):
        return ""
    with io.open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def build(values, when="", subjects=None, log=print):
    """(html, 패널 수). `subjects`는 {Panel_ID: 실행 지문}."""
    rows = _rows(os.path.join(values, VALUES))
    if not rows:
        raise SystemExit("%s에 읽힌 값이 없습니다."
                         % os.path.join(values, VALUES))
    subjects = subjects or {}

    panels = []
    for row in rows:
        pid = (row.get("Panel") or "").strip()
        if pid and pid not in [p for p, _r in panels]:
            panels.append((pid, [r for r in rows
                                 if (r.get("Panel") or "").strip() == pid]))

    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>값 검토 — 패널 %d개</title>" % len(panels))
    w(CSS)
    w("""<style>
[hidden]{display:none!important}
.opt{display:block;font-size:13px;margin:3px 0}
.side{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.side .pick{min-width:320px;flex:1}
.side img{max-width:660px;border:1px solid #ddd}
.chk{display:block;font-size:13px;margin:4px 0}
table.v{border-collapse:collapse;font-size:12px;margin:8px 0}
table.v th,table.v td{border:1px solid #e3e3e0;padding:2px 7px;text-align:right}
table.v th:first-child,table.v td:first-child{text-align:left}
.who{margin:8px 0}
</style>""")
    w("<header><h1>값 검토 <span class='count' id='left'></span></h1>")
    w("<p class='note'>읽힌 값이 <b>어디에 앉았는지</b>를 그림 위에 그렸습니다. "
      "파란 줄이 상자의 위·중앙값·아래, 주황 줄이 수염의 두 끝입니다. "
      "숫자만 보고 하는 승인은 산수에 동의하는 일이고, 그림을 보고 하는 승인은 "
      "표시가 옆 상자에 앉은 것을 잡아냅니다.</p>")
    w("<p class='note'><b>승인은 확인 칸이 전부 채워져야 승인입니다.</b> "
      "고르는 것은 동의이고 확인 칸은 무엇을 보았는가입니다 — 서로 다른 "
      "주장이라 한 번의 클릭으로 묶지 않습니다. 정하기 어려우면 "
      "<b>아직 못 정하겠다</b>도 답입니다.</p>")
    w("<p class='note'>이 페이지는 <b>관문이 아닙니다</b>. 승인이 값을 풀에 "
      "넣으려면 <code>finalize_batch</code>가 검토자가 등록된 사람인지, 실행이 "
      "손대지 않았는지를 다시 봅니다 — 여기서 통과한 답이 거기서 거절될 수 "
      "있고, 그것이 맞습니다.</p>")
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    for pid, cells in panels:
        ids.append(pid)
        meta[pid] = {"panel": pid, "subject": subjects.get(pid, ""),
                     "required": [name for name, _ask in ASKS]}
        w(card(values, pid, cells, subjects.get(pid, "")))

    w("</main><script>")
    w("var IDS = %s;" % json.dumps(ids, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    w("var WHEN = %s;" % json.dumps(str(when or ""), ensure_ascii=False))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    known = sum(1 for pid in ids if subjects.get(pid))
    log("패널 %d개 · 값 %d줄 · 실행 지문이 있는 패널 %d"
        % (len(ids), len(rows), known))
    return "\n".join(out), len(ids)


def card(values, pid, cells, subject):
    out = []
    w = out.append
    w("<div class='doc' data-id='%s'>" % esc(pid))
    w("<h2>%s · %s</h2>" % (esc(pid), esc((cells[0].get("Outcome") or ""))))
    w("<p class='sub'>상자 %d개%s</p>"
      % (len(cells), "" if subject else " · 실행 지문 없음"))

    w("<div class='side'>")
    w("<div class='figs'><div class='fig'>")
    src = data_url(os.path.join(values, "%s.png" % pid))
    if src:
        w("<img src='%s' alt='%s'>" % (src, esc(pid)))
    else:
        w("<div class='nofig'>겹쳐 그린 그림 없음 — 확인할 것이 없습니다</div>")
    w("</div></div>")

    w("<div class='pick'>")
    w("<table class='v'><tr><th>칸</th><th>수염 아래</th><th>Q1</th>"
      "<th>중앙값</th><th>Q3</th><th>수염 위</th></tr>")
    for c in cells:
        w("<tr><td>%s</td>%s</tr>"
          % (esc(c.get("Group")),
             "".join("<td>%s</td>" % esc(_g(c.get(k)))
                     for k in ("Whisker_Lower", "Q1", "Median", "Q3",
                               "Whisker_Upper"))))
    w("</table>")
    for value, label in LABELS:
        w("<label class='opt'><input type='radio' name='d-%s' "
          "data-decision='%s' value='%s'> %s</label>"
          % (esc(pid), esc(pid), esc(value), esc(label)))
    w("<div class='checks'>")
    for name, ask in ASKS:
        w("<label class='chk'><input type='checkbox' data-check='%s' "
          "data-name='%s'> %s</label>" % (esc(pid), esc(name), esc(ask)))
    w("</div>")
    w("<div class='who'>검토자 ID <input type='text' data-who='%s' size='16' "
      "placeholder='reviewer_registry.csv의 ID'></div>" % esc(pid))
    w("<label>메모 <input type='text' data-note='%s' size='28'></label>" % esc(pid))
    w("<div class='state' data-state='%s'></div>" % esc(pid))
    w("</div></div></div>")
    return "\n".join(out)


def _g(v):
    try:
        return "%.4g" % float(v)
    except (TypeError, ValueError):
        return ""


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_values';
  var states = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
  catch (e) { states = {}; }

  function st(id) {
    if (!states[id]) states[id] = { decision: '', checks: {}, note: '', who: '' };
    var m = META[id];
    // 패널 이름, 실행 지문, 무엇을 확인해야 하는가 - 셋 다 화면이 아니라
    // 페이지가 심어 둔 것에서 옵니다. 화면에서 읽으면 사람이 고칠 수 있고,
    // 실행 지문은 사람이 고칠 수 있어서는 안 되는 값입니다.
    if (m) { states[id].panel = m.panel; states[id].subject = m.subject;
             states[id].required = m.required; }
    if (!states[id].checks) states[id].checks = {};
    return states[id];
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {}
  }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  function spreadWho(who) {
    IDS.forEach(function (id) { if (!st(id).who) { st(id).who = who; } });
  }

  function paint(id) {
    var s = st(id);
    var got = reviewOf(id, s);
    var box = q("[data-state=\"" + esc(id) + "\"]");
    if (box) {
      box.textContent = got.ready
        ? '답이 되었습니다 — ' + got.row.Decision : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-id=\"" + esc(id) + "\"]");
    if (card) card.classList.toggle('done', got.ready);
    all("input[data-decision=\"" + esc(id) + "\"]").forEach(function (r) {
      r.checked = r.value === s.decision;
    });
    all("input[data-check=\"" + esc(id) + "\"]").forEach(function (c) {
      c.checked = !!s.checks[c.getAttribute('data-name')];
    });
    var ww = q("input[data-who=\"" + esc(id) + "\"]");
    if (ww && ww.value !== s.who) ww.value = s.who;
    var nn = q("input[data-note=\"" + esc(id) + "\"]");
    if (nn && nn.value !== s.note) nn.value = s.note;
    q('#left').textContent = '· 남은 것 ' + remaining(IDS, states)
      + ' / ' + IDS.length + ' · 보류 ' + held(IDS, states);
  }

  function bind(sel, attr, read, ev) {
    all(sel).forEach(function (el) {
      var id = el.getAttribute(attr);
      el.addEventListener(ev || 'input', function () {
        read(st(id), el); save(); IDS.forEach(paint);
      });
    });
  }
  bind('input[data-decision]', 'data-decision',
       function (s, el) { s.decision = el.value; }, 'change');
  bind('input[data-check]', 'data-check', function (s, el) {
    s.checks[el.getAttribute('data-name')] = el.checked; }, 'change');
  bind('input[data-who]', 'data-who',
       function (s, el) { s.who = el.value; spreadWho(el.value); });
  bind('input[data-note]', 'data-note', function (s, el) { s.note = el.value; });

  q('#dl').addEventListener('click', function () {
    var csv = buildCsv(IDS, states, WHEN);
    var n = IDS.length - remaining(IDS, states);
    if (!n) { q('#msg').textContent = '답이 된 줄이 아직 없습니다.'; return; }
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    // `finalize_batch`가 읽는 파일은 `value_review.csv`입니다. 같은 이름으로
    // 내려받으면 사람이 그 자리에 두게 되고, 실행이 만들어 둔 빈 대기열을
    // 덮어씁니다 - 처분 관문에서 실제로 한 번 그렇게 덮어썼습니다.
    a.download = 'value_review_answers.csv';
    a.click();
    q('#msg').textContent = n + '줄을 내려받았습니다.';
  });

  IDS.forEach(paint);
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--values", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--when", default="",
                    help="사람이 그림을 본 날짜. 브라우저 시계로 채우지 "
                         "않습니다 - 언제 보았는지는 이 프로그램이 아는 것이 "
                         "아닙니다.")
    ap.add_argument("--queue", help="run_batch가 낸 value_review.csv. "
                                    "패널마다의 실행 지문이 거기 있습니다.")
    a = ap.parse_args(argv)
    subjects = {}
    if a.queue:
        for row in _rows(os.path.expanduser(a.queue)):
            subjects[(row.get("Panel_ID") or "").strip()] = \
                (row.get("Review_Subject_SHA256") or "").strip()
    html, _n = build(os.path.expanduser(a.values), when=a.when,
                     subjects=subjects)
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
