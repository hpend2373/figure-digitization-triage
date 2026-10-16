# -*- coding: utf-8 -*-
"""남은 결정을 한 페이지로 - 모든 줄에 제안이 있는 결정 묶음.

    python3 bundle_page.py SPEC.json --out PAGE.html --items ITEMS.json

기록을 적고 계획서 점검(make_plan -> compile_plan -> run_batch)을 돌리면, 사람이 정할
것이 여러 관문에 흩어져 남습니다: 그림 처분, 오차 정의, 카드의 칠·기호·눈금, 결과
이름, 작은 기록 고침. run2(2026-10-15)에서 그것들을 페이지 여럿으로 내는 대신 한
페이지에 모으고, 모든 줄에 Claude의 제안을 달아, 사람은 "모두 제안대로"와 다르게 할
줄만 고르게 했습니다("내가 판단할 것을 줄여주는 게 목표"). 이 모듈은 그 페이지를
짓습니다. 무엇을 물을지는 SPEC이 정합니다 - `bundle_items.py`가 점검 결과에서 모으고
제안을 붙여 씁니다.

이 페이지가 지키는 것(어기면 SPEC을 거절합니다):

    모든 항목에 제안이 있다          제안 없는 줄은 사람에게 판단을 넘기는 줄이고, 이
                                    페이지가 줄이려는 것이 그것입니다(NO_PROPOSAL).
    제안에는 이유와 낸 것이 있다      이유 없는 제안은 승인할 수 없고(NO_REASON), 누가
                                    보았는지 없는 제안은 승인된 관찰이 될 수 없습니다
                                    (NO_OBSERVER, `approval`).
    모든 답은 무엇을 적는지 말한다    보류가 아닌 선택지마다 효과가 있습니다: 어느 관문에
                                    무엇을 적는지, 또는 아직 없는 어느 길이 필요한지
                                    (NO_EFFECT, BAD_EFFECT). 답이 무엇을 바꾸는지 모르는
                                    채 승인하는 일이 없게, 그리고 `bundle_route.py`가
                                    답을 관문의 답으로 기계적으로 옮길 수 있게.
    보류가 늘 있다                    "아직 못 정하겠다"를 말할 자리가 없는 물음은 사람을
                                    제안 쪽으로 밉니다(NO_HOLD).
    보여 준 그림은 지문을 남긴다      줄마다 그 항목(선택지와 효과까지)과 보여 준 그림 파일의
                                    sha256이 답에 실립니다 - 답이 어느 물음의 어느 그림에
                                    대한 것인지(IMAGE_MISSING).
    답 파일은 관문이 쓰는 파일이 아니다  같은 이름이면 사람이 답을 그 자리에 두고, 관문은
                                    자기 파일을 답으로 읽습니다(ANSWERS_FILE_IS_A_RECORD).

답이 되는 규칙(제안 그대로면 보지 않아도 승인된 관찰, 다르면 "직접 보았다")은
`bundle_page.js`에 있고 node로 시험합니다.

**출판사 그림이 든 페이지입니다.** 페이지 파일은 로컬에만 두고 공개 저장소나 공유
링크로 올리지 않습니다.
"""
import argparse
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from page_bits import esc, thumb                                  # noqa: E402

SCHEMA = "figure-digitization-triage/decision-bundle/1"
LOGIC = "bundle_page.js"
HOLD = "HOLD"
EDIT = "EDIT"

#: 답이 적힐 수 있는 관문과, 효과가 반드시 들고 와야 하는 것. `None`은 "아직 길이
#: 없다" - 그 답은 `bundle_route.py`가 옮기지 않고 할 일로 남깁니다.
GATES = {
    "dispositions": ("row", ("Draft_ID", "Disposition")),
    "errorbar": ("row", ("Source_Document_ID", "Dispersion_Type", "Errorbar_Definition_Source")),
    "identity": ("proposal_id", ()),
    "geometry": ("proposal_id", ()),
    "outcomes": ("row", ("Panel_ID", "Decision")),
    "legends": ("row", ("Draft_ID", "Legend_Groups", "Decision")),
}

#: 카드 관문이 답에서 받는 칸. 나머지는 관문이 제안 행에서 다시 짓습니다 - `record_identity`는
#: 정체 제안의 행에, `record_geometry`는 기하 제안의 행(또는 `Drawn_Frame`으로 그린 프레임)에
#: 사람이 준 칸만 얹습니다. 여기 없는 칸(예: Panel_X1)을 바꾸는 효과는 기록에 닿지 않고
#: 조용히 사라지므로 받지 않습니다. `test_bundle_route.py`가 두 관문의 코드와 대 봅니다.
CARD_TAKES = {
    "identity": ("Human_Verification_Status", "X_Factor", "X_Labels", "Series_Factor", "Series", "Mark_Type",
                 "Outcome_Name", "Unit", "N_Outcome", "Bar_Top_Definition", "Errorbar_Stem_Confirmed", "Read_Route"),
    "geometry": ("Human_Verification_Status", "Y_Tick_Top_Value", "Y_Tick_Bottom_Value", "Confirmed_Tick_Values",
                 "Y_Axis_Shared_With"),
}

#: 관문이 적는 파일 이름. 답 파일이 이 이름이면 거절합니다.
RECORD_FILES = ("figure_dispositions.csv", "figure_decisions.csv", "errorbar_decisions.csv",
                "identity_decisions.csv", "geometry_decisions.csv", "panel_decisions.csv",
                "inventory_records.csv", "block_reviews.csv", "outcome_decisions.csv", "legend_decisions.csv")


def load_spec(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def items_of(spec):
    for sec in spec.get("sections") or []:
        for it in sec.get("items") or []:
            yield sec, it


def effect_problems(iid, value, effect, item):
    """(문제 목록) - 선택지 하나의 효과."""
    out = []
    if not isinstance(effect, dict):
        return [("NO_EFFECT", "%s의 %s에는 무엇을 적는지(효과)가 없습니다." % (iid, value))]
    gate = effect.get("gate")
    if gate is None:
        if not str(effect.get("needs") or "").strip():
            out.append(("BAD_EFFECT", "%s의 %s: 관문이 없는 답은 어느 길이 필요한지(needs)를 말해야 합니다." % (iid, value)))
    elif gate not in GATES:
        out.append(("BAD_EFFECT", "%s의 %s: 모르는 관문 %r" % (iid, value, gate)))
    else:
        key, required = GATES[gate]
        if key == "row":
            row = effect.get("row") or {}
            miss = [c for c in required if not str(row.get(c) or "").strip()]
            if miss:
                out.append(("BAD_EFFECT", "%s의 %s: %s 행에 %s가 없습니다." % (iid, value, gate, ", ".join(miss))))
        else:
            if not str(effect.get("proposal_id") or "").strip():
                out.append(("BAD_EFFECT", "%s의 %s: %s 효과에 Proposal_ID가 없습니다." % (iid, value, gate)))
            if not effect.get("set") and not effect.get("series"):
                out.append(("BAD_EFFECT", "%s의 %s: 바꿀 칸(set)도 계열(series)도 없습니다." % (iid, value)))
            not_taken = sorted(f for f in (effect.get("set") or {}) if f not in CARD_TAKES[gate])
            if effect.get("series") and "Series" not in CARD_TAKES[gate]:
                not_taken.append("Series")
            if not_taken:
                out.append(("BAD_EFFECT", "%s의 %s: %s 관문은 답에서 %s를 받지 않습니다 - 적어도 기록에 닿지 않습니다."
                            % (iid, value, gate, ", ".join(not_taken))))
    if effect.get("uses_text") and not item.get("text"):
        out.append(("EDIT_WITHOUT_TEXT", "%s의 %s는 이름을 쓰는데 항목에 이름 칸이 없습니다." % (iid, value)))
    return out


def check_spec(spec, root="."):
    """(문제 목록). 빈 목록이면 이 SPEC으로 페이지를 지을 수 있습니다."""
    problems = []
    if spec.get("schema") != SCHEMA:
        problems.append(("BAD_SCHEMA", "schema가 %r가 아닙니다." % SCHEMA))
    ans = os.path.basename(str(spec.get("answers_file") or ""))
    if not ans.endswith(".csv"):
        problems.append(("BAD_ANSWERS_FILE", "answers_file은 .csv 이름이어야 합니다."))
    elif ans in RECORD_FILES:
        problems.append(("ANSWERS_FILE_IS_A_RECORD", "답 파일 이름 %s는 관문이 적는 파일입니다. 사람이 답을 그 자리에 "
                                                     "두면 관문이 자기 기록을 답으로 읽습니다." % ans))
    seen = set()
    n = 0
    for sec, it in items_of(spec):
        n += 1
        iid = str(it.get("id") or "").strip()
        if not iid:
            problems.append(("NO_ITEM_ID", "%s 묶음에 이름 없는 항목이 있습니다." % sec.get("id")))
            continue
        if iid in seen:
            problems.append(("DUPLICATE_ITEM", "%s가 둘입니다." % iid))
        seen.add(iid)
        opts = it.get("options") or []
        values = [str(o[0]) for o in opts]
        if not opts:
            problems.append(("NO_OPTIONS", "%s에 선택지가 없습니다." % iid))
            continue
        if len(set(values)) != len(values):
            problems.append(("OPTION_DUPLICATE", "%s의 선택지가 겹칩니다." % iid))
        if HOLD not in values:
            problems.append(("NO_HOLD", "%s에 보류가 없습니다. 정하지 못한다고 말할 자리가 있어야 합니다." % iid))
        prop = str(it.get("proposal") or "").strip()
        if not prop or prop == HOLD:
            problems.append(("NO_PROPOSAL", "%s에 제안이 없습니다. 이 페이지의 모든 줄에는 제안이 있어야 합니다." % iid))
        elif prop not in values:
            problems.append(("PROPOSAL_NOT_AN_OPTION", "%s의 제안 %s가 선택지에 없습니다." % (iid, prop)))
        if not str(it.get("why") or "").strip():
            problems.append(("NO_REASON", "%s의 제안에 이유가 없습니다." % iid))
        if not str(it.get("observed_by") or "").strip():
            problems.append(("NO_OBSERVER", "%s의 제안을 누가(무엇이) 보고 냈는지가 없습니다." % iid))
        if EDIT in values and not it.get("text"):
            problems.append(("EDIT_WITHOUT_TEXT", "%s는 이름 고치기를 받는데 이름 칸이 없습니다." % iid))
        for o in opts:
            if str(o[0]) == HOLD:
                continue
            eff = o[2] if len(o) > 2 else None
            # 한 답이 여러 곳에 적힐 수 있습니다(그림의 패널 모두를 MANUAL로, 기하와 정체의 상자를 함께) - 효과의 목록.
            if isinstance(eff, list):
                if not eff:
                    problems.append(("NO_EFFECT", "%s의 %s의 효과 목록이 비었습니다." % (iid, o[0])))
                for e in eff:
                    problems.extend(effect_problems(iid, o[0], e, it))
            else:
                problems.extend(effect_problems(iid, o[0], eff, it))
        for im in it.get("images") or []:
            p = os.path.join(root, im.get("path") or "")
            if not os.path.isfile(p):
                problems.append(("IMAGE_MISSING", "%s의 그림 %s가 없습니다." % (iid, im.get("path"))))
    if not n:
        problems.append(("NO_ITEMS", "묻는 항목이 없습니다."))
    return problems


def item_sha(it):
    """항목의 지문: 무엇을 묻고(대상·지금·선택지와 효과·제안·이름) 무엇을 적는지, 그리고 제안의
    이유와 낸 것. 승인된 관찰은 그 관찰(이유)을 승인한 것이라, 이유가 바뀌면 다른 항목입니다."""
    body = {k: it.get(k) for k in ("id", "target", "now", "options", "proposal", "text", "why", "observed_by")}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CSS = """<style>
:root{--bg:#f6f5f1;--fg:#1d1d1b;--dim:#66655f;--line:#dcd8cd;--card:#fff;--rec:#eef6ee;--now:#f1efe7;--ok:#2f855a;--no:#b3261e}
@media (prefers-color-scheme: dark){:root{--bg:#1b1b19;--fg:#ecebe6;--dim:#a3a29b;--line:#3a3935;--card:#242422;--rec:#1f2e22;--now:#2b2a26}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;margin:0;padding:0 16px 80px}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 0;z-index:5}
h1{font-size:19px;margin:4px 0}h2{font-size:16px;margin:4px 0 6px}.sec{font-size:18px;margin:28px 0 4px;max-width:1100px}
.item{background:var(--card);border:1px solid var(--line);border-left:4px solid #1f5fa8;border-radius:6px;padding:10px 14px;margin:14px 0;max-width:1100px;overflow-wrap:anywhere}
.iid{display:inline-block;font:600 13px ui-monospace,Menlo,monospace;color:#fff;background:#1f5fa8;border-radius:4px;padding:1px 6px;margin-right:4px}
.now{background:var(--now);padding:4px 8px;border-radius:4px;font-size:14px}.rec{background:var(--rec);border-left:3px solid var(--ok);padding:6px 10px;border-radius:4px;margin:8px 0}
.dim,.cap{color:var(--dim);font-size:13px}img{max-width:100%;height:auto;border:1px solid var(--line);background:#fff}figure{margin:8px 0}
.ctl{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;border-top:1px dashed var(--line);margin-top:8px;padding-top:8px}
.opt.recd{font-weight:600}.badge{font-size:11px;background:var(--ok);color:#fff;border-radius:8px;padding:0 6px}
.state{font-size:13px}.ok{color:var(--ok)}.no{color:var(--no)}input[type=text]{font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg);min-width:0}
.note{flex:1 1 200px}.txt{display:flex;gap:6px;flex-wrap:wrap}.txt .t{flex:1 1 240px}.txt .u{flex:0 1 110px}
table{border-collapse:collapse;font-size:13px}td,th{border:1px solid var(--line);padding:2px 6px}.tbl{overflow-x:auto}
button{font:inherit;padding:4px 10px;border-radius:5px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
.guide{max-width:1100px;font-size:14px}
</style>"""


def render(spec, root=".", log=print):
    """(html, 항목 파일). 거절할 SPEC이면 SystemExit."""
    problems = check_spec(spec, root)
    if problems:
        raise SystemExit("SPEC을 거절합니다:\n" + "\n".join("  %s: %s" % p for p in problems))
    items, out = [], []
    w = out.append
    w("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>%s</title>%s</head><body>" % (esc(spec.get("title") or "결정 묶음"), CSS))
    w("<header><h1>%s</h1><label>이름 <input type='text' id='who' size='12'></label> · 준비됨 <b id='count'></b> "
      "<button id='fillall'>모두 제안대로 채우기</button> <button id='dl'>%s 내려받기</button></header>"
      % (esc(spec.get("title") or "결정 묶음"), esc(spec["answers_file"])))
    w("<div class='guide'><p>모든 항목에 제안이 있고(<span class='badge'>제안</span>), 미리 골라 두지 않았습니다. "
      "이름을 적고 ‘모두 제안대로 채우기’ → 다르게 할 것만 바꾸고 ‘직접 보았다’ → 내려받기.</p>"
      "<ul><li>‘직접 보았다’ 없이 제안 그대로인 줄은 <b>승인된 관찰</b>로 나갑니다(Seen_By_Person=0, Observed_By=제안을 낸 것, "
      "Approval_Ref=이 답 파일). 제안과 다른 줄은 ‘직접 보았다’가 있어야 나갑니다. 보류는 그대로 나갑니다.</li>"
      "<li>이 페이지는 아무 파일도 고치지 않습니다.</li>%s</ul></div>"
      % "".join("<li>%s</li>" % esc(t) for t in spec.get("notes") or []))
    w("<main>")
    for sec in spec["sections"]:
        sid = esc(sec.get("id") or "")
        w("<h2 class='sec' id='sec-%s'>%s · %s <span class='dim' id='cnt-%s'></span> "
          "<button data-fillsec='%s'>이 묶음 제안대로</button></h2>" % (sid, sid, esc(sec.get("title") or ""), sid, sid))
        if sec.get("intro"):
            w("<p class='guide'>%s</p>" % esc(sec["intro"]))
        for it in sec["items"]:
            q = dict(it, sec=sec.get("id") or "", group=it.get("group") or it["id"])
            shas, figs = [], []
            for im in it.get("images") or []:
                p = os.path.join(root, im["path"])
                shas.append(file_sha(p))
                src = thumb(p, (int(im.get("max_width") or 760), 4 * int(im.get("max_width") or 760)))
                figs.append("<figure><img src='%s' alt='%s'><figcaption class='cap'>%s</figcaption></figure>"
                            % (src, esc(it["id"]), esc(im.get("caption") or "")))
            q["sha"], q["img_sha"] = item_sha(it), ";".join(shas)
            items.append({k: q.get(k) for k in ("id", "sec", "group", "target", "now", "options", "proposal",
                                                "observed_by", "text", "sha", "img_sha")})
            w(card(q, figs))
    w("</main><script>")
    w("var ITEMS = %s;" % json.dumps(items, ensure_ascii=False).replace("</", "<\\/"))
    w("var FILE = %s, KEY = %s;" % (json.dumps(spec["answers_file"]), json.dumps(spec.get("storage_key") or ("fdt_bundle:" + spec["answers_file"]))))
    with io.open(os.path.join(HERE, LOGIC), encoding="utf-8") as fh:
        w(fh.read())
    w(PAGE_JS)
    w("</script></body></html>")
    log("항목 %d개 · 그림 %d장" % (len(items), sum(len((i["img_sha"] or "").split(";")) for i in items if i["img_sha"])))
    return "\n".join(out), {"schema": SCHEMA, "answers_file": spec["answers_file"], "items": items}


def card(q, figs):
    out = []
    w = out.append
    w("<section class='item' id='%s'><h2><span class='iid'>%s</span> %s</h2>" % (esc(q["id"]), esc(q["id"]), esc(q.get("question") or q.get("target") or "")))
    if q.get("now"):
        w("<p class='now'><b>지금</b> %s</p>" % esc(q["now"]))
    w("<div class='rec'><b>제안</b> %s <span class='dim'>— 본 것: %s</span></div>" % (esc(q["why"]), esc(q["observed_by"])))
    if q.get("facts"):
        w("<p class='cap'>%s</p>" % esc(q["facts"]))
    w("".join(figs))
    if q.get("table"):
        w("<div class='tbl'><table>%s</table></div>" % "".join(
            "<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in row) for row in q["table"]))
    # "직접 보았다"는 묶음(group)마다 하나입니다 - 한 그림의 패널 넷을 보고 네 번 누르게 하면 사람은
    # 넷째에는 보지 않고 누릅니다. 같은 묶음의 칸들은 함께 켜지고 꺼지며, 그렇다고 말합니다.
    shared = q["group"] != q["id"]
    w("<div class='ctl'><label><input type='checkbox' data-seen='%s'> 직접 보았다%s</label></div>"
      % (esc(q["group"]), " <span class='dim'>(이 그림의 항목 모두)</span>" if shared else ""))
    radios = "".join("<label class='opt%s'><input type='radio' name='q_%s' value='%s' data-q='%s'> %s%s</label>" % (
        " recd" if str(o[0]) == q["proposal"] else "", esc(q["id"]), esc(o[0]), esc(q["id"]), esc(o[1]),
        " <span class='badge'>제안</span>" if str(o[0]) == q["proposal"] else "") for o in q["options"])
    txt = ""
    if q.get("text"):
        txt = ("<div class='txt'><input type='text' class='t' data-text='%s' value='%s' aria-label='이름'>"
               "<input type='text' class='u' data-unit='%s' value='%s' aria-label='단위'></div>"
               % (esc(q["id"]), esc(q["text"].get("value") or ""), esc(q["id"]), esc(q["text"].get("unit") or "")))
    w("<div class='ctl'>%s<input type='text' class='note' data-note='%s' placeholder='메모'> <span class='state' data-state='%s'></span></div>%s</section>"
      % (radios, esc(q["id"]), esc(q["id"]), txt))
    return "\n".join(out)


PAGE_JS = r"""
(function () {
  var st = {};
  try { st = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { st = {}; }
  st.q = st.q || {}; st.g = st.g || {};
  function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
  function today() { var d = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
                     return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }
  var BY = {}; ITEMS.forEach(function (x) { BY[x.id] = x; });
  function states() { var o = {}; ITEMS.forEach(function (x) { o[x.id] = Object.assign({}, st.q[x.id] || {}, { seen: !!st.g[x.group] }); }); return o; }
  function ctx() { return { who: st.who || '', file: FILE }; }
  function q1(sel) { return document.querySelector(sel); }
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function paint() {
    var S = states(), C = ctx(), sec = {};
    ITEMS.forEach(function (x) {
      var a = st.q[x.id] || {}, got = answerOf(x, S[x.id], C);
      sec[x.sec] = sec[x.sec] || [0, 0]; sec[x.sec][1]++; if (got.ready) sec[x.sec][0]++;
      all('input[data-q="' + x.id + '"]').forEach(function (r) { r.checked = r.value === a.choice; });
      var e = q1('[data-state="' + x.id + '"]');
      if (e) { e.className = 'state ' + (got.ready ? 'ok' : 'no');
               e.textContent = got.ready ? ('준비됨' + (got.approved ? ' · 승인' : '')) : got.why; }
      var n = q1('input[data-note="' + x.id + '"]'); if (n && document.activeElement !== n) n.value = a.note || '';
      var t = q1('input[data-text="' + x.id + '"]'); if (t && a.text != null && document.activeElement !== t) t.value = a.text;
      var u = q1('input[data-unit="' + x.id + '"]'); if (u && a.unit != null && document.activeElement !== u) u.value = a.unit;
    });
    all('input[data-seen]').forEach(function (c) { c.checked = !!st.g[c.getAttribute('data-seen')]; });
    var t = tally(ITEMS, S, C);
    q1('#count').textContent = t.ready + ' / ' + t.total + ' (승인 ' + t.approved + ' · 본 답 ' + t.seen + ' · 보류 ' + t.held + ')';
    Object.keys(sec).forEach(function (k) { var e = document.getElementById('cnt-' + k); if (e) e.textContent = sec[k][0] + ' / ' + sec[k][1]; });
    var w = q1('#who'); if (w && document.activeElement !== w) w.value = st.who || '';
  }
  function s(id) { return st.q[id] = st.q[id] || {}; }
  document.addEventListener('change', function (ev) {
    var el = ev.target, g = function (n) { return el.getAttribute && el.getAttribute(n); };
    if (g('data-q')) { var a = s(g('data-q')); a.choice = el.value; a.on = today(); }
    else if (g('data-seen')) { st.g[g('data-seen')] = el.checked; }
    else if (g('data-note')) { s(g('data-note')).note = el.value; }
    else if (g('data-text') || g('data-unit')) {
      var id = g('data-text') || g('data-unit'), x = BY[id], b = s(id);
      if (b.text == null) b.text = x.text.value; if (b.unit == null) b.unit = x.text.unit || '';
      if (g('data-text')) b.text = el.value; else b.unit = el.value;
      if (edited(x, b)) { b.choice = 'EDIT'; b.on = today(); }
    }
    else if (el.id === 'who') { st.who = el.value; }
    else return;
    save(); paint();
  });
  document.addEventListener('click', function (ev) {
    var t = ev.target, g = t.getAttribute && t.getAttribute('data-fillsec');
    if (g) { fillEmpty(ITEMS, st.q, function (x) { return x.sec === g; }, today()); save(); paint(); }
    else if (t.id === 'fillall') { fillEmpty(ITEMS, st.q, null, today()); save(); paint(); }
  });
  q1('#dl').addEventListener('click', function () {
    var blob = new Blob(['﻿' + buildCsv(ITEMS, states(), ctx())], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = FILE;
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  });
  paint();
})();
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("spec")
    ap.add_argument("--out", required=True, help="페이지(로컬에만 둘 것)")
    ap.add_argument("--items", required=True, help="항목 파일: bundle_route.py가 답을 대 보는 지문")
    ap.add_argument("--root", default=None, help="그림 경로의 기준 폴더 (기본: SPEC이 있는 폴더)")
    a = ap.parse_args(argv)
    spec = load_spec(a.spec)
    root = a.root or os.path.dirname(os.path.abspath(a.spec))
    html, items = render(spec, root)
    with io.open(a.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    with io.open(a.items, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    print("페이지: %s (%.1f MB) · 항목 파일: %s" % (a.out, os.path.getsize(a.out) / 1e6, a.items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
