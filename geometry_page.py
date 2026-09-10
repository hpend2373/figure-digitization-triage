# -*- coding: utf-8 -*-
"""사람이 기하 제안을 보고 확인하는 페이지.

    python3 geometry_page.py --proposals DIR --out DIR/geometry.html

`geometry_proposer`가 낸 것은 전부 **제안**입니다: 프레임, 눈금의 픽셀 행,
축이 무어라고 적혀 있는지, 상자의 x 위치. 오버레이에 그려져 있고, 아무것도
확인되지 않았습니다.

이 페이지가 하는 일은 그 제안을 사람 앞에 놓는 것이고, 사람이 하는 일은 대개
**보는 것**입니다. 리더가 읽어 낸 축은 인쇄된 숫자 옆에 자홍색으로 그려져
있어서, 확인은 두 줄을 나란히 보는 일이 됩니다. 리더가 거절한 축에서만 사람이
숫자를 칩니다 - 그것이 이 페이지에서 타이핑이 남아 있는 유일한 자리입니다.

묻는 것은 **맨 위 눈금**과 **맨 아래 눈금**이고, 각각 픽셀 행까지 적어
보여 줍니다. 처음엔 "첫 눈금 / 끝 눈금"이라고만 물었고, FIG9 여섯 패널이 전부
뒤집혀 돌아왔습니다 - 축은 아래에서 시작하니 아래부터 적는 것이 자연스럽고,
계산은 위부터 짝지었습니다. 물음이 위치를 말하면 애매한 데가 없습니다.

무엇이 답이 되는지는 여기 없고 `geometry_page.js`에 있습니다. 화면은 값을
옮기기만 합니다 - `errorbar_review_page`·`decision_page`와 같은 나눔이고, 같은
이유입니다: 브라우저 안에서만 사는 판단 논리는 아무도 시험할 수 없습니다.

내려받는 파일은 `geometry_answers.csv`이고, 관문 `record_geometry.py`가 그것을
받아 `geometry_decisions.csv`를 적습니다. 이름이 다른 것은 규약입니다 - 같은
이름으로 내려받으면 관문이 자기 출력을 답으로 읽습니다.
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
import geometry_proposer as GP                                   # noqa: E402

PROPOSALS = "geometry_proposal.csv"
LOGIC = "geometry_page.js"

#: 화면에 적는 말. `geometry_page.js`의 `VERDICTS`와 같아야 하고,
#: `test_geometry_page.py`가 둘이 같은지 봅니다 - 화면에만 있는 답은 고를 수
#: 있지만 답이 되지 않고, 논리에만 있는 답은 아무도 고를 수 없습니다.
LABELS = (
    ("CONFIRMED", "맞다 — 이 프레임과 이 눈금으로 읽는다"),
    ("REJECTED", "틀렸다 — 이 제안으로는 읽지 않는다"),
    ("HOLD", "아직 못 정하겠다"),
)

#: 오버레이의 색이 무슨 뜻인지. 그림 위의 색을 설명하지 않으면 사람은 자홍색
#: 숫자가 인쇄된 것인지 그려 넣은 것인지 알 수 없고, 그것을 모르면 확인이
#: 확인이 아닙니다.
KEYS = (("#c81e1e", "프레임 — 이 안이 읽을 자리"),
        ("#be3cbe", "리더가 잰 눈금과 읽은 값, 그리고 축 아래 상자 x 위치"),
        ("#149650", "잉크 기둥으로 찾은 x 위치 (다른 방법, 참고용)"))


def _rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def data_url(path):
    """오버레이 한 장을 data URL로. 못 읽으면 빈 문자열.

    줄이지 않습니다. 이 페이지에서 사람이 하는 일은 인쇄된 숫자와 리더가 쓴
    숫자를 나란히 읽는 것이고, 그러려면 둘 다 읽을 수 있어야 합니다 - 목록
    페이지의 섬네일과 다른 점입니다.
    """
    if not path or not os.path.isfile(path):
        return ""
    import base64
    with io.open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def build(proposals, log=print):
    """(html, 제안 수)."""
    rows = _rows(os.path.join(proposals, PROPOSALS))
    if not rows:
        raise SystemExit("%s에 제안이 없습니다."
                         % os.path.join(proposals, PROPOSALS))

    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>기하 확인 — %d개</title>" % len(rows))
    w(CSS)
    w("""<style>
[hidden]{display:none!important}
.opt{display:block;font-size:13px;margin:3px 0}
.side{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.side .pick{min-width:300px;flex:1}
.side img{max-width:620px;border:1px solid #ddd}
.read{font-size:13px;margin:8px 0;padding:8px 10px;background:#faf7fb;
      border-left:3px solid #be3cbe}
.refused{background:#fdf6f3;border-left-color:#c86a1e}
.key{font-size:12px;color:#5a5a56;margin:6px 0 0}
.key i{display:inline-block;width:11px;height:11px;margin-right:4px;
       vertical-align:-1px}
.vals{margin-top:6px;font-size:13px}
.vals input{width:8em}
.who{margin:8px 0}
</style>""")
    w("<header><h1>기하 확인 <span class='count' id='left'></span></h1>")
    w("<p class='note'><code>geometry_proposer</code>가 잰 것과 읽은 것이 "
      "그림 위에 그려져 있습니다. 전부 <b>제안</b>이고, 아무것도 확인되지 "
      "않았습니다.</p>")
    w("<p class='note'>대개 하실 일은 <b>보는 것</b>입니다 — 인쇄된 눈금 숫자 "
      "옆에 리더가 읽은 숫자가 자홍색으로 적혀 있으니, 두 줄이 같으면 맞는 "
      "것입니다. <b>리더가 읽지 못한 축에서만</b> 첫 눈금과 끝 눈금을 직접 "
      "적어 주세요.</p>")
    w("<p class='note'><b>직접 보셨을 때만</b> 확인 칸을 눌러 주세요 — 고르는 "
      "것은 판단이고, 그 칸은 목격입니다. 그리고 <b>누가 보았는지</b>가 없는 "
      "확인은 확인이 아니라서, 이름을 적기 전에는 답이 되지 않습니다.</p>")
    w("<p class='key'>%s</p>"
      % " &nbsp; ".join("<i style='background:%s'></i>%s" % (c, esc(t))
                        for c, t in KEYS))
    w("<p style='margin:10px 0 0'><button id='dl'>CSV 내려받기</button> "
      "<span class='count' id='msg'></span></p></header><main>")

    for row in rows:
        pid = (row.get("Proposal_ID") or "").strip()
        if not pid:
            continue
        ids.append(pid)
        read = GP.read_values_of(row)
        marks = [m for m in (row.get("Y_Tick_Pixels") or "").split(";") if m]
        meta[pid] = {
            "proposal": pid,
            # 리더가 읽은 것은 화면의 칸이 아니라 여기서 논리로 갑니다. 칸을
            # 미리 채워 두면 사람이 고치지 않은 값과 리더의 값이 구별되지
            # 않고, `Value_Source`가 아무것도 세지 못합니다.
            #
            # 값만이 아니라 **짝**을 넘깁니다. 리더가 맨 위·맨 아래 눈금을
            # 읽었다는 보장이 없어서, 값만 넘기면 그 값이 어느 눈금의 것인지
            # 논리가 짐작해야 합니다.
            "readPairs": (row.get("Y_Tick_Read_Values") or "").strip(),
            # 사람이 값을 칠 때 그 값이 붙는 자리.
            "topPixel": marks[0] if marks else "",
            "bottomPixel": marks[-1] if marks else "",
        }
        w(card(proposals, pid, row, read))

    w("</main><script>")
    w("var IDS = %s;" % json.dumps(ids, ensure_ascii=False))
    w("var META = %s;" % json.dumps(meta, ensure_ascii=False))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    n_read = sum(1 for r in rows if GP.read_values_of(r))
    log("제안 %d개 · 축을 읽은 것 %d · 사람이 값을 적어야 하는 것 %d"
        % (len(ids), n_read, len(ids) - n_read))
    return "\n".join(out), len(ids)


def card(proposals, pid, row, read):
    out = []
    w = out.append
    w("<div class='doc' data-id='%s'>" % esc(pid))
    w("<h2>%s</h2>" % esc(pid))
    w("<p class='sub'>%s · 프레임 %s,%s,%s,%s · 눈금 %s개 · 신뢰도 %s</p>"
      % (esc(row.get("Raster") or ""), esc(row.get("Panel_X0")),
         esc(row.get("Panel_X1")), esc(row.get("Panel_Y0")),
         esc(row.get("Panel_Y1")), esc(row.get("Y_Tick_Count")),
         esc(row.get("Confidence"))))

    w("<div class='side'>")
    w("<div class='figs'><div class='fig'>")
    src = data_url(os.path.join(proposals, "%s.png" % pid))
    if src:
        w("<img src='%s' alt='%s'>" % (src, esc(pid)))
    else:
        w("<div class='nofig'>오버레이 없음 — 확인할 그림이 없습니다</div>")
    w("</div></div>")

    w("<div class='pick'>")
    if read:
        w("<div class='read'><b>리더가 읽은 축:</b> %s<br><span class='sub'>%s</span></div>"
          % (esc(" · ".join("%g" % v for v, _px in read)),
             esc((row.get("Y_Tick_Read_Detail") or "")[:180])))
    else:
        # 거절은 흠이 아니라 이 페이지가 사람에게 물어야 할 자리입니다. 왜
        # 거절했는지를 함께 보여 주지 않으면, 사람은 자기가 무엇을 고치는지
        # 모르는 채로 숫자를 칩니다.
        w("<div class='read refused'><b>리더가 축을 읽지 못했습니다.</b><br>"
          "<span class='sub'>%s</span><br>첫 눈금과 끝 눈금을 적어 주세요.</div>"
          % esc((row.get("Y_Tick_Read_Detail") or "")[:180]))
    if (row.get("Box_Anchor_Count") or "").strip() not in ("", "0"):
        w("<div class='meta'>상자 x 위치 %s개 — %s</div>"
          % (esc(row.get("Box_Anchor_Count")),
             esc(row.get("Box_Anchor_Detail") or "")))
    if (row.get("Confidence_Reason") or "").strip():
        w("<div class='meta'>%s</div>" % esc(row["Confidence_Reason"]))

    for value, label in LABELS:
        w("<label class='opt'><input type='radio' name='v-%s' "
          "data-verdict='%s' value='%s'> %s</label>"
          % (esc(pid), esc(pid), esc(value), esc(label)))
    # 픽셀 행을 함께 적습니다. "맨 위"가 어느 줄인지는 그림에 그려져 있지만,
    # 숫자로도 보이면 사람이 자기가 어느 눈금을 말하는지 틀릴 수가 없습니다.
    marks = [m for m in (row.get("Y_Tick_Pixels") or "").split(";") if m]
    w("<div class='vals'>맨 <b>위</b> 눈금%s "
      "<input type='text' data-top='%s' placeholder='예: 40'> "
      "맨 <b>아래</b> 눈금%s "
      "<input type='text' data-bottom='%s' placeholder='예: 0'>"
      "<div class='sub'>비워 두면 리더가 읽은 값을 그대로 씁니다. "
      "위·아래를 바꿔 적으면 그 패널의 모든 값이 뒤집힙니다.</div></div>"
      % ((" (픽셀 행 %s)" % esc(marks[0])) if marks else "", esc(pid),
         (" (픽셀 행 %s)" % esc(marks[-1])) if marks else "", esc(pid)))
    w("<div class='who'>보신 분 <input type='text' data-who='%s' size='12' "
      "placeholder='이름 또는 이니셜'></div>" % esc(pid))
    w("<div class='row'>")
    w("<label class='verify'><input type='checkbox' data-seen='%s'> "
      "<b>이 오버레이를 직접 봤다</b></label>" % esc(pid))
    w("<label>메모 <input type='text' data-note='%s' size='24'></label>" % esc(pid))
    w("</div>")
    w("<div class='state' data-state='%s'></div>" % esc(pid))
    w("</div></div></div>")
    return "\n".join(out)


PAGE_JS = r"""
(function () {
  var KEY = 'fdt_geometry';
  var states = {};
  try { states = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; }
  catch (e) { states = {}; }

  function st(id) {
    if (!states[id]) {
      states[id] = { verdict: '', top: '', bottom: '', note: '', who: '',
                     seen: false };
    }
    var m = META[id];
    // 리더가 읽은 값과 나갈 이름은 화면이 아니라 페이지가 심어 둔 것에서
    // 옵니다. 화면의 칸에서 읽으면 사람이 고친 값과 구별되지 않습니다.
    if (m) {
      states[id].proposal = m.proposal;
      states[id].readPairs = m.readPairs;
      states[id].topPixel = m.topPixel;
      states[id].bottomPixel = m.bottomPixel;
    }
    return states[id];
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(states)); } catch (e) {}
  }
  function q(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  // 한 사람이 한 자리에서 여러 장을 봅니다. 이름을 장마다 다시 치게 하면
  // 치지 않게 되고, 치지 않으면 답이 되지 않습니다.
  function spreadWho(who) {
    IDS.forEach(function (id) {
      if (!st(id).who) { st(id).who = who; }
    });
  }

  function paint(id) {
    var s = st(id);
    var got = verdictOf(id, s);
    var box = q("[data-state=\"" + esc(id) + "\"]");
    if (box) {
      box.textContent = got.ready
        ? '답이 되었습니다 — ' + got.row.Human_Verification_Status
          + (got.row.Confirmed_Tick_Values
             ? ' (위 ' + got.row.Y_Tick_Top_Value + ' … 아래 '
               + got.row.Y_Tick_Bottom_Value + ', ' + got.row.Value_Source
               + ') — '
               // 리더가 못 읽은 축에서는 방향을 견줄 데가 없습니다. 막는 대신
               // 되읽어 줍니다: 자기가 방금 무슨 축을 만들었는지 글자로 보면
               // 위아래를 바꿔 적은 것이 눈에 걸립니다.
               + directionWord(parsePairs(got.row.Confirmed_Tick_Values))
             : '')
        : got.why;
      box.className = 'state' + (got.ready ? ' ready' : '');
    }
    var card = q(".doc[data-id=\"" + esc(id) + "\"]");
    if (card) card.classList.toggle('done', got.ready);
    all("input[data-verdict=\"" + esc(id) + "\"]").forEach(function (r) {
      r.checked = r.value === s.verdict;
    });
    var ff = q("input[data-top=\"" + esc(id) + "\"]");
    if (ff) { if (ff.value !== s.top) ff.value = s.top;
              ff.parentNode.hidden = !needsValues(s.verdict); }
    var ll = q("input[data-bottom=\"" + esc(id) + "\"]");
    if (ll && ll.value !== s.bottom) ll.value = s.bottom;
    var ww = q("input[data-who=\"" + esc(id) + "\"]");
    if (ww && ww.value !== s.who) ww.value = s.who;
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
        read(st(id), el); save(); IDS.forEach(paint);
      });
    });
  }
  bind('input[data-verdict]', 'data-verdict',
       function (s, el) { s.verdict = el.value; }, 'change');
  bind('input[data-top]', 'data-top', function (s, el) { s.top = el.value; });
  bind('input[data-bottom]', 'data-bottom', function (s, el) { s.bottom = el.value; });
  bind('input[data-who]', 'data-who',
       function (s, el) { s.who = el.value; spreadWho(el.value); });
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
    // 관문이 적는 파일은 `geometry_decisions.csv`입니다. 같은 이름으로
    // 내려받으면 관문이 자기 출력을 답으로 읽습니다 - 처분 페이지에서
    // 실제로 한 번 그렇게 만들었고, 64줄이 전부 거절된 뒤 원본이
    // 덮였습니다.
    a.download = 'geometry_answers.csv';
    a.click();
    q('#msg').textContent = n + '줄을 내려받았습니다.';
  });

  IDS.forEach(paint);
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    html, _n = build(os.path.expanduser(a.proposals))
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
