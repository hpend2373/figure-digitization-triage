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
    ("SHARED", "이 패널엔 축이 없다 — 같은 그림의 다른 패널 축을 쓴다"),
    ("REJECTED", "틀렸다 — 이 제안으로는 읽지 않는다"),
    ("HOLD", "아직 못 정하겠다"),
)

#: 오버레이의 색이 무슨 뜻인지. 그림 위의 색을 설명하지 않으면 사람은 자홍색
#: 숫자가 인쇄된 것인지 그려 넣은 것인지 알 수 없고, 그것을 모르면 확인이
#: 확인이 아닙니다.
KEYS = (("#c81e1e", "프레임 — 이 안이 읽을 자리"),
        ("#be3cbe", "리더가 잰 눈금과 읽은 값, 그리고 축 아래 상자 x 위치"),
        ("#149650", "잉크 기둥으로 찾은 x 위치 (다른 방법, 참고용)"),
        ("#e67814", "축 공유 후보 패널의 눈금 행 (점선) — 이 패널의 선과 맞는지 보세요"))


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


def chunk_of(rows, chunk, of):
    """조각 `chunk`(1부터)의 행들. 한 그림(래스터)의 패널은 같은 조각에 둡니다.

    축을 나눠 쓰는 패널은 같은 그림의 다른 패널을 가리키고, 관문은 그 패널의
    확인을 같은 답 묶음에서 찾습니다 - 그림이 두 조각에 걸리면 답이 두 파일에
    걸리고, 어느 한쪽을 먼저 적을 수 없습니다. 조각은 래스터 순서대로, 패널
    수가 고르게 나뉘도록 끊습니다.
    """
    if of <= 1:
        return list(rows)
    if not 1 <= chunk <= of:
        raise SystemExit("--chunk는 1..%d 사이여야 합니다 (%d)" % (of, chunk))
    groups, order = {}, []
    for r in rows:
        key = (r.get("Raster") or "").strip()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    total = len(rows)
    bins, cur, filled, target = [], [], 0, 0
    for key in order:
        if not cur:
            # 조각이 시작될 때 남은 것을 남은 조각 수로 나눈 목표. 그림 하나가
            # 크면 그 조각은 커지고, 다음 조각들이 그만큼 줄어듭니다 - 그림은
            # 자르지 않습니다.
            left_bins = of - len(bins)
            target = (total - filled) / float(left_bins) if left_bins else 0
        # 이 그림을 더하는 쪽과 여기서 끊는 쪽 중 목표에 가까운 쪽. "넘으면
        # 끊는다"로는 조각마다 조금씩 모자라고, 모자란 만큼이 마지막 조각에
        # 쌓입니다 - 975장을 열로 나눴더니 마지막이 183장이었습니다.
        if cur and of - len(bins) > 1 and \
                abs(len(cur) + len(groups[key]) - target) > abs(len(cur) - target):
            bins.append(cur)
            cur = []
            left_bins = of - len(bins)
            target = (total - filled) / float(left_bins)
        cur.extend(groups[key])
        filled += len(groups[key])
    if cur:
        bins.append(cur)
    while len(bins) < of:
        bins.append([])
    return bins[chunk - 1]


def build(proposals, log=print, chunk=1, of=1):
    """(html, 제안 수)."""
    everything = _rows(os.path.join(proposals, PROPOSALS))
    if not everything:
        raise SystemExit("%s에 제안이 없습니다."
                         % os.path.join(proposals, PROPOSALS))
    rows = chunk_of(everything, chunk, of)
    # 같은 그림의 패널들. 축을 빌려 올 수 있는 후보는 이 안에서만 고릅니다.
    by_raster = {}
    for r in everything:
        by_raster.setdefault((r.get("Raster") or "").strip(), []).append(
            (r.get("Proposal_ID") or "").strip())

    out, meta, ids = [], {}, []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>기하 확인 — %d개%s</title>"
      % (len(rows), (" (%d/%d)" % (chunk, of)) if of > 1 else ""))
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
.shared{background:#fff6ec;border-left-color:#e67814}
.share select{max-width:100%}
.pickwrap{position:relative;display:inline-block}
.pickwrap.arming img{cursor:crosshair;outline:2px solid #1e64c8}
.mark{position:absolute;left:0;right:0;height:0;border-top:2px dashed #1e64c8;
      pointer-events:none}
.mark span{position:absolute;right:2px;top:-14px;font-size:11px;color:#1e64c8;
           background:#fff;padding:0 3px}
.pickbtn{font-size:12px;margin-right:4px}
.pickbtn.on{background:#1e64c8;color:#fff}
</style>""")
    w("<header><h1>기하 확인%s <span class='count' id='left'></span></h1>"
      % ((" — %d/%d 조각" % (chunk, of)) if of > 1 else ""))
    w("<p class='note'><code>geometry_proposer</code>가 잰 것과 읽은 것이 "
      "그림 위에 그려져 있습니다. 전부 <b>제안</b>이고, 아무것도 확인되지 "
      "않았습니다.</p>")
    w("<p class='note'>대개 하실 일은 <b>보는 것</b>입니다 — 인쇄된 눈금 숫자 "
      "옆에 리더가 읽은 숫자가 자홍색으로 적혀 있으니, 두 줄이 같으면 맞는 "
      "것입니다. <b>리더가 읽지 못한 축에서만</b> 첫 눈금과 끝 눈금을 직접 "
      "적어 주세요.</p>")
    w("<p class='note'>y축이 <b>맨 왼쪽 패널에만</b> 있고 이 패널엔 눈금도 숫자도 "
      "없으면, 값을 지어내지 말고 <b>\"다른 패널 축을 쓴다\"</b>를 고른 뒤 어느 "
      "패널인지 골라 주세요. 그 패널이 확인되면 관문이 그 값을 옮겨 적습니다. "
      "리더가 후보를 댄 패널에는 그 패널의 눈금 행이 주황 점선으로 그려져 있으니, "
      "이 패널의 선과 맞는지 보세요.</p>")
    w("<p class='note'>리더가 <b>눈금 행을 못 잰</b> 패널(프레임은 맞는데 눈금이 없거나 "
      "안 잡힌 것)은 값을 붙일 자리가 없습니다. \"맨 위 눈금 찍기\"를 누른 뒤 그림에서 "
      "그 눈금을 누르고, 아래도 같이 찍은 다음 값을 적어 주세요. 찍은 줄이 프레임 "
      "밖이면 프레임이 틀린 것이니 <b>\"틀렸다\"</b>를 골라 주세요.</p>")
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
            # 축을 빌려 올 수 있는 패널들과, 리더가 댄 후보. 후보는 고르는
            # 칸에 미리 들어가지만 판정은 사람이 고릅니다.
            "siblings": [s for s in by_raster.get((row.get("Raster") or "").strip(), [])
                         if s and s != pid],
            "sharedCandidate": (row.get("Y_Axis_Shared_Candidate") or "").strip(),
            # 사람이 그림에 찍은 줄을 래스터 행으로 옮기는 데 필요한 것: 오버레이의
            # 원점(제안 모듈이 자른 자리, 짐작하지 않음)과 프레임의 위·아래.
            "originX": GP.overlay_origin(row)[0],
            "originY": GP.overlay_origin(row)[1],
            "frameTop": (row.get("Panel_Y0") or "").strip(),
            "frameBottom": (row.get("Panel_Y1") or "").strip(),
        }
        w(card(proposals, pid, row, read, meta[pid]["siblings"]))

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


def card(proposals, pid, row, read, siblings=()):
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
        # 그림 위에 사람이 눈금을 찍을 수 있습니다. 찍은 줄은 파란 점선으로
        # 그림 위에 남고, 래스터 행은 논리로 갑니다.
        w("<div class='pickwrap' data-pick='%s'><img src='%s' alt='%s'>"
          "<div class='mark' data-mark-top='%s' hidden><span>맨 위</span></div>"
          "<div class='mark' data-mark-bottom='%s' hidden><span>맨 아래</span></div></div>"
          % (esc(pid), src, esc(pid), esc(pid), esc(pid)))
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
    cand = (row.get("Y_Axis_Shared_Candidate") or "").strip()
    if cand:
        w("<div class='read shared'><b>축 공유 후보:</b> %s<br><span class='sub'>%s"
          "</span></div>"
          % (esc(cand), esc(row.get("Y_Axis_Shared_Detail") or "")))
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
      "위·아래를 바꿔 적으면 그 패널의 모든 값이 뒤집힙니다.</div>"
      "<div class='sub'><button class='pickbtn' data-arm-top='%s'>맨 위 눈금 찍기</button>"
      "<button class='pickbtn' data-arm-bottom='%s'>맨 아래 눈금 찍기</button>"
      "<button class='pickbtn' data-unpick='%s'>찍은 줄 지우기</button> "
      "<span data-picked='%s'></span></div></div>"
      % ((" (픽셀 행 %s)" % esc(marks[0])) if marks else " (잰 눈금 없음)", esc(pid),
         (" (픽셀 행 %s)" % esc(marks[-1])) if marks else " (잰 눈금 없음)", esc(pid),
         esc(pid), esc(pid), esc(pid), esc(pid)))
    # 어느 패널의 축을 쓰는지. 같은 그림의 패널만 고를 수 있고, 후보가 있으면
    # 미리 골라져 있습니다 - 고르는 것은 목록이고 판정은 위의 답입니다.
    w("<div class='vals share'>축을 쓰는 패널 <select data-shared='%s'>"
      "<option value=''>— 고르세요 —</option>%s</select>"
      "<div class='sub'>그 패널이 \"맞다\"로 확인되어야 이 패널의 값이 옮겨집니다. "
      "이 패널의 눈금 값은 적지 않습니다.</div></div>"
      % (esc(pid), "".join("<option value='%s'>%s</option>" % (esc(s), esc(s))
                           for s in siblings)))
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
                     seen: false, sharedWith: '', pickedTopPixel: '', pickedBottomPixel: '' };
    }
    var m = META[id];
    // 리더가 읽은 값과 나갈 이름은 화면이 아니라 페이지가 심어 둔 것에서
    // 옵니다. 화면의 칸에서 읽으면 사람이 고친 값과 구별되지 않습니다.
    if (m) {
      states[id].proposal = m.proposal;
      states[id].readPairs = m.readPairs;
      states[id].topPixel = m.topPixel;
      states[id].bottomPixel = m.bottomPixel;
      states[id].siblings = m.siblings || [];
      states[id].frameTop = m.frameTop;
      states[id].frameBottom = m.frameBottom;
      // 리더의 후보는 고르는 칸에 미리 들어갑니다. 판정은 사람이 고릅니다.
      if (!states[id].sharedWith && m.sharedCandidate) {
        states[id].sharedWith = m.sharedCandidate;
      }
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
          + (got.row.Y_Axis_Shared_With ? ' (' + got.row.Y_Axis_Shared_With + '의 축)' : '')
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
    // 찍은 줄. 그림 위의 파란 점선과 칸 옆의 글자, 둘 다 상태에서 옵니다.
    var wrap = q(".pickwrap[data-pick=\"" + esc(id) + "\"]");
    if (wrap) {
      var im = wrap.querySelector('img');
      var m = META[id] || {};
      ['top', 'bottom'].forEach(function (end) {
        var mk = wrap.querySelector('[data-mark-' + end + ']');
        var px = s[end === 'top' ? 'pickedTopPixel' : 'pickedBottomPixel'];
        if (!mk) return;
        if (px === '' || px === null || px === undefined || !im.naturalHeight) { mk.hidden = true; return; }
        // 래스터 행 -> 화면의 줄. 원점을 빼고 표시 배율을 곱합니다.
        var y = (Number(px) - Number(m.originY || 0)) * (im.clientHeight / im.naturalHeight);
        mk.style.top = y + 'px';
        mk.hidden = false;
      });
      wrap.classList.toggle('arming', !!arming[id]);
      all("button[data-arm-top=\"" + esc(id) + "\"]").forEach(function (b) { b.classList.toggle('on', arming[id] === 'top'); });
      all("button[data-arm-bottom=\"" + esc(id) + "\"]").forEach(function (b) { b.classList.toggle('on', arming[id] === 'bottom'); });
    }
    var pk = q("[data-picked=\"" + esc(id) + "\"]");
    if (pk) {
      var parts = [];
      if (s.pickedTopPixel !== '' && s.pickedTopPixel !== undefined) parts.push('맨 위 찍은 행 ' + s.pickedTopPixel);
      if (s.pickedBottomPixel !== '' && s.pickedBottomPixel !== undefined) parts.push('맨 아래 찍은 행 ' + s.pickedBottomPixel);
      pk.textContent = parts.length ? parts.join(' · ') + ' (찍은 줄이 잰 눈금보다 앞섭니다)'
                                    : (arming[id] ? '그림에서 그 눈금을 눌러 주세요' : '');
    }
    var sh = q("select[data-shared=\"" + esc(id) + "\"]");
    if (sh) { if (sh.value !== s.sharedWith) sh.value = s.sharedWith;
              sh.parentNode.hidden = s.verdict !== SHARED; }
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
  bind('select[data-shared]', 'data-shared',
       function (s, el) { s.sharedWith = el.value; }, 'change');

  // 눈금 찍기. 단추로 어느 끝인지 정하고, 그림을 누르면 그 줄이 래스터 행으로
  // 옮겨져 상태에 들어갑니다. 화면의 좌표는 표시 배율과 원점을 거쳐야 래스터
  // 행이고, 그 둘은 페이지가 심어 둔 것입니다.
  var arming = {};
  function arm(end) {
    return function (s, el) {
      var id = el.getAttribute(end === 'top' ? 'data-arm-top' : 'data-arm-bottom');
      arming[id] = arming[id] === end ? '' : end;
    };
  }
  bind('button[data-arm-top]', 'data-arm-top', arm('top'), 'click');
  bind('button[data-arm-bottom]', 'data-arm-bottom', arm('bottom'), 'click');
  bind('button[data-unpick]', 'data-unpick',
       function (s) { s.pickedTopPixel = ''; s.pickedBottomPixel = ''; }, 'click');
  all('.pickwrap[data-pick]').forEach(function (wrap) {
    var id = wrap.getAttribute('data-pick');
    wrap.querySelector('img').addEventListener('click', function (ev) {
      if (!arming[id]) return;
      var im = ev.currentTarget, m = META[id] || {};
      var rect = im.getBoundingClientRect();
      var yShown = ev.clientY - rect.top;
      var row = Math.round(Number(m.originY || 0) + yShown * (im.naturalHeight / im.clientHeight));
      var s = st(id);
      if (arming[id] === 'top') { s.pickedTopPixel = row; arming[id] = 'bottom'; }
      else { s.pickedBottomPixel = row; arming[id] = ''; }
      save(); IDS.forEach(paint);
    });
  });
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
    ap.add_argument("--chunk", type=int, default=1,
                    help="몇 번째 조각인가 (1부터). 한 그림의 패널은 같은 조각에 둡니다.")
    ap.add_argument("--of", type=int, default=1, help="조각의 수")
    a = ap.parse_args(argv)
    html, _n = build(os.path.expanduser(a.proposals), chunk=a.chunk, of=a.of)
    with io.open(os.path.expanduser(a.out), "w", encoding="utf-8") as fh:
        fh.write(html)
    print("페이지: %s (%.1f MB)"
          % (a.out, os.path.getsize(os.path.expanduser(a.out)) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
