# -*- coding: utf-8 -*-
"""사람이 그림을 보고 처분을 정하는 페이지.

    python3 decision_page.py --run RUN --plans RUN/plans_YYYY-MM-DD \
                             --out RUN/decisions.html

계획서가 사람에게 남긴 일은 다섯 가지인데, 그중 넷은 **판단**이고 하나는
**작업**입니다. 패널 기하는 읽을 자리와 눈금을 쓰는 일이라 화면의 단추로
답할 수 없고, 오차 정의는 `errorbar_review_page.py`가 이미 묻습니다. 여기
남는 셋이 이 페이지의 물음입니다:

    UNCOUNTABLE   셀 수 없다고 하신 그림 - 다시 자를까, 데이터가 아닌가,
                  아니면 이제 셀 수 있는가
    MIXED         캡션이 스스로 어긋난 그림 - 어느 패널이 데이터인가
    CROP_DISPUTE  대상 그림이 아니라고 하신 크롭

`worklist_page.py`와 다른 점은 이것입니다: 그쪽은 무엇이 남았는지 보여 주기만
하고, 이 페이지는 답을 받습니다. 그래서 규율도 다릅니다 - 그림을 직접
보았다고 누르지 않으면 그 줄은 답이 되지 않습니다.

**적히는 것은 내려받은 CSV이고, 그것을 파이프라인에 넣는 관문은 아직
없습니다.** 처분을 기록하는 자리는 `errorbar_decisions.csv`처럼 따로 있어야
하고, 그 관문을 만들기 전에 이 답들이 어떤 모양인지 먼저 보는 것이 순서입니다.
"""
import argparse
import collections
import csv
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from page_bits import CSS, esc, thumb                            # noqa: E402

FIGURES = "plan_figures.csv"
COUNTS = "observed_panel_counts.csv"
CAPTIONS = "caption_fulltext.csv"
LOGIC = "decision_page.js"

#: 계획서가 적는 할 일 → 이 페이지의 물음. 여기 없는 할 일은 이 페이지가 묻지
#: 않습니다 - 패널 기하는 단추로 답할 수 없고, 오차 정의는 다른 페이지가
#: 이미 묻습니다. 묻지 않는 것을 화면에 올리면 사람은 답할 수 없는 칸 앞에
#: 앉습니다.
QUESTIONS = collections.OrderedDict([
    ("셀 수 없다고 하신 그림 — 처분 결정", "UNCOUNTABLE"),
    ("캡션이 스스로 어긋난 그림 — 어느 패널이 데이터인지 확인", "MIXED"),
    ("대상 그림이 아니라고 하신 크롭 — 처분 결정 또는 재크롭", "CROP_DISPUTE"),
])

#: 물음마다, 화면에 적는 말. `decision_page.js`의 `CHOICES`와 같아야 하고,
#: `test_decision_page.py`가 둘이 같은지 봅니다 - 화면에만 있는 답은 고를 수
#: 있지만 답이 되지 않고, 논리에만 있는 답은 아무도 고를 수 없습니다.
LABELS = {
    "UNCOUNTABLE": [
        ("RECROP", "다시 자르기 — 크롭이 잘못됐다"),
        ("NOT_DATA", "데이터가 아니다 — 추출하지 않는다"),
        ("COUNTABLE", "이제 셀 수 있다 — 계수로 되돌린다"),
        ("HOLD", "아직 못 정하겠다"),
    ],
    # 순서도 `decision_page.js`의 `CHOICES`와 같습니다. 두 곳에 있는 목록이
    # 순서까지 같아야 시나리오가 정확히 비교할 수 있고, 정확히 비교해야 한쪽에만
    # 생긴 선택지를 잡습니다.
    "MIXED": [
        ("DATA", "전부 데이터다 — 추출 대상"),
        ("NOT_DATA", "데이터가 아니다"),
        ("PARTIAL", "일부 패널만 데이터다"),
        ("HOLD", "아직 못 정하겠다"),
    ],
    "CROP_DISPUTE": [
        ("RECROP", "다시 자르기"),
        ("NOT_DATA", "데이터가 아니다"),
        ("HOLD", "아직 못 정하겠다"),
    ],
}

ASKS = {
    "UNCOUNTABLE": "축 영역을 셀 수 없다고 적어 두셨습니다. 이 그림을 어떻게 할까요?",
    "MIXED": "캡션에 “데이터가 아니다”를 뜻하는 낱말과 오차 막대 정의가 "
             "같이 있습니다. 그림을 보고 정해 주세요.",
    "CROP_DISPUTE": "이 크롭이 대상 그림이 아니라고 적어 두셨습니다.",
}


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def asked(row):
    """이 그림에 대해 이 페이지가 묻는 물음들. 계획서의 할 일에서만 옵니다."""
    out = []
    for need in (row.get("Needs") or "").split(" · "):
        kind = QUESTIONS.get(need.strip())
        if kind and kind not in out:
            out.append(kind)
    return out


def build(run, plans, log=print):
    """(html, 물음 수)."""
    figs = _rows(os.path.join(plans, FIGURES))
    counted = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, COUNTS)))
    caps = dict((r["Draft_ID"], r) for r in _rows(os.path.join(run, CAPTIONS)))

    items = []
    for r in figs:
        for kind in asked(r):
            items.append((kind, r))
    if not items:
        raise SystemExit("%s에 이 페이지가 묻는 일이 없습니다."
                         % os.path.join(plans, FIGURES))

    by_kind = collections.OrderedDict()
    for kind in QUESTIONS.values():
        rows = [r for k, r in items if k == kind]
        if rows:
            by_kind[kind] = rows

    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>처분 판정 — %d건</title>" % len(items))
    w(CSS)
    w("""<style>
[hidden]{display:none!important}
.opt{display:block;font-size:13px;margin:3px 0}
.ask{font-size:13px;color:#5a5a56;margin:0 0 12px;max-width:80ch}
.side{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.side .figs{margin:0}
.side .pick{min-width:290px;flex:1}
.which{margin-top:6px}
</style>""")
    w("<header><h1>처분 판정 <span class='count' id='left'></span></h1>")
    w("<p class='note'>계획서가 남긴 일 중 <b>그림을 보고 정하는 것</b>만 "
      "모았습니다. 패널 기하는 단추로 답할 수 없어 빠졌고, 오차 정의는 "
      "<code>errorbar_review_page.py</code>가 내는 판정 페이지에서 묻습니다.</p>")
    w("<p class='note'><b>그림을 직접 보셨을 때만</b> 확인 칸을 눌러 주세요 — "
      "고르는 것은 판단이고, 그 칸은 목격입니다. 정하기 어려우면 "
      "<b>아직 못 정하겠다</b>도 답입니다. 아무 말도 하지 않는 것과 다릅니다.</p>")
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    for kind, rows in by_kind.items():
        w("<h3 class='sec'>%s <span class='count'>%d</span></h3>"
          % (esc([k for k, v in QUESTIONS.items() if v == kind][0]), len(rows)))
        w("<p class='ask'>%s</p>" % ASKS[kind])
        for r in sorted(rows, key=lambda x: (x["Publication_ID"],
                                             len(x["Figure_Number"]),
                                             x["Figure_Number"])):
            key = "%s::%s" % (kind, r["Draft_ID"])
            ids.append(key)
            meta[key] = {"kind": kind, "draft": r["Draft_ID"]}
            w(card(run, key, kind, r, counted.get(r["Draft_ID"], {}),
                   caps.get(r["Draft_ID"], {})))

    w("</main><script>")
    w("var IDS = %s;" % json.dumps(ids, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    log("물음 %d건 · 그림 %d개" % (len(items), len(set(r["Draft_ID"] for _k, r in items))))
    return "\n".join(out), len(items)


def card(run, key, kind, row, count, cap):
    out = []
    w = out.append
    w("<div class='doc' data-id='%s'>" % esc(key))
    w("<h2>%s · %s</h2>" % (esc(row["Publication_ID"]), esc(row["Figure_Number"])))
    w("<p class='sub'>p.%s · 패널 %s · %s</p>"
      % (esc(row["Page"]), esc(row.get("Observed_Panel_Count") or "?"),
         esc(row.get("Disposition") or "")))

    w("<div class='side'>")
    w("<div class='figs'><div class='fig'>")
    src = thumb(os.path.join(run, (row.get("Image") or "")))
    if src:
        w("<img src='%s' alt='%s' style='max-width:460px'>"
          % (src, esc(row["Figure_Number"])))
    else:
        w("<div class='nofig'>크롭 없음</div>")
    w("</div></div>")

    w("<div class='pick'>")
    # 사람이 계수 시트에 적어 둔 말. 자기가 왜 이 그림을 여기 세웠는지는
    # 자기 말로 다시 보는 것이 가장 빠릅니다.
    said = (count.get("Uncountable_Reason") or "").strip() \
        or (count.get("Objection_Reason") or "").strip()
    if said:
        w("<div class='meta'><b>적어 두신 말:</b> %s</div>" % esc(said))
    full = (cap.get("Caption_Full") or "").strip()
    if kind == "MIXED" and full:
        w("<blockquote>%s</blockquote>" % esc(full[:600]))
        if (row.get("Errorbar_Definition_Source") or "").strip():
            w("<div class='meta'>오차 정의: <b>%s</b> — %s</div>"
              % (esc(row.get("Dispersion_Type")),
                 esc(row["Errorbar_Definition_Source"][:160])))
    for value, label in LABELS[kind]:
        w("<label class='opt'><input type='radio' name='c-%s' "
          "data-choice='%s' value='%s'> %s</label>"
          % (esc(key), esc(key), esc(value), esc(label)))
    if any(v == "PARTIAL" for v, _l in LABELS[kind]):
        w("<label class='which'>어느 패널 "
          "<input type='text' data-which='%s' size='22' "
          "placeholder='예: a, c'></label>" % esc(key))
    w("<div class='row'>")
    w("<label class='verify'><input type='checkbox' data-seen='%s'> "
      "<b>이 그림을 직접 봤다</b></label>" % esc(key))
    w("<label>메모 <input type='text' data-note='%s' size='26'></label>" % esc(key))
    w("</div>")
    w("<div class='state' data-state='%s'></div>" % esc(key))
    w("</div></div></div>")
    return "\n".join(out)


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_decisions';
  var states = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
  catch (e) { states = {}; }

  function st(id) {
    if (!states[id]) states[id] = { choice: '', which: '', note: '', seen: false };
    var m = META[id];
    // 물음과 나갈 이름은 화면이 아니라 페이지가 심어 둔 것에서 옵니다.
    if (m) { states[id].kind = m.kind; states[id].draft = m.draft; }
    return states[id];
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {}
  }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  function paint(id) {
    var s = st(id);
    var got = decisionOf(id, s);
    var box = q("[data-state=\"" + esc(id) + "\"]");
    if (box) {
      box.textContent = got.ready ? '답이 되었습니다 — ' + got.row.Decision : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-id=\"" + esc(id) + "\"]");
    if (card) card.classList.toggle('done', got.ready);
    all("input[data-choice=\"" + esc(id) + "\"]").forEach(function (r) {
      r.checked = r.value === s.choice;
    });
    var ww = q("input[data-which=\"" + esc(id) + "\"]");
    if (ww) { if (ww.value !== s.which) ww.value = s.which;
              ww.parentNode.hidden = !needsWhich(s.choice); }
    var vv = q("input[data-seen=\"" + esc(id) + "\"]");
    if (vv) vv.checked = !!s.seen;
    var nn = q("input[data-note=\"" + esc(id) + "\"]");
    if (nn && nn.value !== s.note) nn.value = s.note;
    q('#left').textContent = '· 남은 것 ' + remaining(IDS, states)
      + ' / ' + IDS.length + ' · 보류 ' + held(IDS, states);
  }

  function bind(sel, attr, read, ev) {
    all(sel).forEach(function (el) {
      var id = el.getAttribute(attr);
      el.addEventListener(ev || 'input', function () {
        read(st(id), el); save(); paint(id);
      });
    });
  }
  bind('input[data-choice]', 'data-choice',
       function (s, el) { s.choice = el.value; }, 'change');
  bind('input[data-which]', 'data-which', function (s, el) { s.which = el.value; });
  bind('input[data-seen]', 'data-seen',
       function (s, el) { s.seen = el.checked; }, 'change');
  bind('input[data-note]', 'data-note', function (s, el) { s.note = el.value; });

  q('#dl').addEventListener('click', function () {
    var csv = buildCsv(IDS, states);
    var n = IDS.length - remaining(IDS, states);
    if (!n) { q('#msg').textContent = '답이 된 줄이 아직 없습니다.'; return; }
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    // 관문이 적는 파일은 `figure_decisions.csv`입니다. 같은 이름으로
    // 내려받으면 사람이 답을 그 자리에 두게 되고, 관문은 자기가 적어
    // 둔 것을 답으로 읽어 전부 ALREADY_DECIDED로 거절한 뒤 원본을
    // 덮어씁니다. `errorbar_answers.csv`/`errorbar_decisions.csv`와
    // 같은 규약입니다.
    a.download = 'figure_decision_answers.csv';
    a.click();
    q('#msg').textContent = n + '줄을 내려받았습니다.';
  });

  IDS.forEach(paint);
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--plans", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    html, _n = build(os.path.expanduser(a.run), os.path.expanduser(a.plans))
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
